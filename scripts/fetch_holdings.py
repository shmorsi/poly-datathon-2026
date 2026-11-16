"""Download the ETF issuers' published holdings into the local data/etf_holdings.csv (plan C Task 4).

    python scripts/fetch_holdings.py [--out PATH] [--manual CSV ...] [--offline]

What it reads, with each issuer's terms in one line (the output is never committed: it is gitignored, pitfall 10):
  XIU.TO, XBB.TO      iShares Canada holdings CSV. BlackRock Canada terms: personal, non-commercial use; no redistribution or public reuse.
  SPY                 State Street daily holdings XLSX. Printed in the file: no reproduction or disclosure to third parties without consent.
  QQQ                 Invesco's terms bar "data mining, robots, or similar" tools: rows are typed by a human from the fund page (--manual).
  ESGV                Vanguard: holdings may not be reproduced or distributed, in whole or in part, without permission; no file (--manual).
  AGG TLT GLD ZST.TO  no holdings file is read: static asset-class labels (Bonds / Gold; USA / GLOBAL / CAN), not issuer data.
SPY's sector rows (only its fund page shows them) also come from --manual. Without a --manual file the existing local rows are kept.
The downloaded files are untrusted data: they are only parsed (csv, zipfile, ElementTree), never executed, and a workbook is
inflated in chunks and refused beyond 25 MB whatever size it declares. The script writes nothing except --out and its .tmp, and
prints one plain sentence per failure, never a response body or a traceback. A source it cannot read (corrupt or encrypted
workbook, a weight it cannot parse or outside 0-100 %) is skipped with one sentence and its existing rows are kept.
Exit 0 after an atomic write when at least one (etf, kind) was refreshed; exit 1 with the existing file untouched otherwise.
A --manual (etf, kind) group replaces the downloaded or static rows of that group; its tickers must be dataset tickers or empty.
The .tmp file is created exclusively: a leftover or symlinked <out>.tmp stops the run (delete it by hand). An --out that is a
symlink is replaced by the new regular file; the link's target is not written.
Sources, dates and processing: docs/research/etf-holdings-sources.md.
"""
from __future__ import annotations

import argparse
import csv
import http.client
import io
import os
import re
import sys
import urllib.error
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
import zlib
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # `python scripts/fetch_holdings.py` puts scripts/, not the repo root, first
    sys.path.insert(0, str(ROOT))

COLUMNS = ["etf", "kind", "name", "ticker", "weight", "as_of", "source_url"]
KINDS = ("holding", "sector", "country")
DEFAULT_OUT = ROOT / "data" / "etf_holdings.csv"
USER_AGENT = "EPICENTRE-datathon/1.0 (education project)"
TIMEOUT = 30
MAX_BYTES = 25_000_000          # a holdings file is well under 5 MB; anything larger is not one
MAX_ROWS, MAX_COLUMNS = 1_048_576, 16_384    # the worksheet limits of the XLSX format
MIN_COUNTRY = 0.005             # countries under 0.5 % are left out (disclosed as coverage, like the research file)
OUTPUT_ORDER = ("XIU.TO", "SPY", "QQQ", "ESGV", "XBB.TO", "ZST.TO", "AGG", "TLT", "GLD")
# The 31 tickers of spec section 9 (the fallback when tools.data cannot load the starter universe).
UNIVERSE_31 = frozenset({
    "RY.TO", "TD.TO", "MFC.TO", "ENB.TO", "CNQ.TO", "CNR.TO", "FTS.TO", "ATD.TO", "SHOP.TO", "CSU.TO",
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "TSLA", "JPM", "JNJ", "PG", "XOM",
    "XIU.TO", "SPY", "QQQ", "ESGV", "XBB.TO", "ZST.TO", "AGG", "TLT", "GLD", "BTC-USD", "ETH-USD"})
ISO3 = {"Canada": "CAN", "United States": "USA", "Bermuda": "BMU", "United Kingdom": "GBR", "Germany": "DEU", "France": "FRA",
        "Netherlands": "NLD", "Switzerland": "CHE", "Luxembourg": "LUX", "Brazil": "BRA", "China": "CHN"}
_ISHARES_CA = "https://www.blackrock.com/ca/investors/en/products/{id}/{slug}"
_ISHARES_FILE = "/1464253357814.ajax?fileType=csv&fileName={name}_holdings&dataType=fund"
_BLACKROCK_TERMS = "BlackRock Canada: personal, non-commercial use; no redistribution or public reuse (blackrock.com/ca terms-and-conditions)"
SOURCES = {
    "XIU.TO": {"page": _ISHARES_CA.format(id=239832, slug="ishares-sptsx-60-index-etf"), "mode": "download", "terms": _BLACKROCK_TERMS,
               "download": _ISHARES_CA.format(id=239832, slug="ishares-sptsx-60-index-etf") + _ISHARES_FILE.format(name="XIU")},
    "XBB.TO": {"page": _ISHARES_CA.format(id=239493, slug="ishares-core-canadian-universe-bond-index-etf"), "mode": "download",
               "terms": _BLACKROCK_TERMS,
               "download": _ISHARES_CA.format(id=239493, slug="ishares-core-canadian-universe-bond-index-etf") + _ISHARES_FILE.format(name="XBB")},
    "SPY": {"page": "https://www.ssga.com/us/en/intermediary/etfs/state-street-spdr-sp-500-etf-trust-spy", "mode": "download",
            "terms": "State Street: no reproduction, copying or disclosure to third parties without express written consent (printed in the file)",
            "download": "https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx"},
    "QQQ": {"page": "https://www.invesco.com/qqq-etf/en/about.html", "mode": "manual", "download": "",
            "terms": "Invesco: personal or internal use; bars data mining, robots and similar extraction tools (invesco.com terms-of-use)"},
    "ESGV": {"page": "https://investor.vanguard.com/investment-products/etfs/profile/esgv", "mode": "manual", "download": "",
             "terms": "Vanguard: holdings may not be reproduced or distributed, in whole or in part, without written permission"},
    "AGG": {"page": "https://www.ishares.com/us/products/239458/ishares-core-u-s-aggregate-bond-etf", "mode": "static", "download": "",
            "terms": "iShares US: the page serves no holdings file; the rows are asset-class labels, not issuer data"},
    "TLT": {"page": "https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf", "mode": "static", "download": "",
            "terms": "iShares US: the page serves no holdings file; the rows are asset-class labels, not issuer data"},
    "GLD": {"page": "https://www.ssga.com/us/en/intermediary/etfs/spdr-gold-shares-gld", "mode": "static", "download": "",
            "terms": "State Street: gold bullion, investment geography Global; the rows are labels, not issuer data"},
    "ZST.TO": {"page": "https://bmogam.com/ca-en/products/exchange-traded-fund/bmo-ultra-short-term-bond-etf-zst/", "mode": "static",
               "download": "", "terms": "BMO: fund data is not readable from the page; CAN is an assumption (listing market), to verify"},
}
# Static asset-class labels: etf -> (sector name, {country code: weight}). as_of = the run date.
STATIC = {"AGG": ("Bonds", {"USA": 1.0}), "TLT": ("Bonds", {"USA": 1.0}), "GLD": ("Gold", {"GLOBAL": 1.0}),
          "ZST.TO": ("Bonds", {"CAN": 1.0})}
BOND_FUND_SECTOR = {"XBB.TO": "Bonds"}   # the iShares sector column lists bond types: keep its countries, label the sector Bonds


# --- parsers: pure functions, tested offline on synthetic fixtures ------------------------------------------------------
def dataset_ticker(symbol: str, universe) -> str:
    """The dataset ticker of an issuer symbol: itself, else symbol + ".TO", else "" (RY -> RY.TO, XOM -> XOM, GOOG -> "")."""
    s = (symbol or "").strip()
    if s in universe:
        return s
    return s + ".TO" if s and s + ".TO" in universe else ""


def _row(etf, kind, name, ticker, weight, as_of, source_url) -> dict:
    """One output row. State Street weights carry 6 decimals of percent: 8 decimals as a fraction keep them all (and drop float noise)."""
    if kind != "holding":    # a file's own total can be 100.02 %: a sector or country row is capped at 100 % so the file stays readable
        weight = min(weight, 1.0)
    return {"etf": etf, "kind": kind, "name": name, "ticker": ticker, "weight": round(weight, 8), "as_of": as_of, "source_url": source_url}


_NUMBER = re.compile(r"[-+]?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?")      # SPY's file has "3.0E-6"
_THOUSANDS = re.compile(r"[-+]?\d{1,3}(,\d{3})+(\.\d+)?")               # a comma is only ever a thousands separator


def _weight(text) -> float | None:
    """A percent cell as a fraction: "6.05" -> 0.0605, "3.0E-6" -> 3e-08, "1,500.00" -> 15.0 (rejected below). None for a blank or
    dash cell. ValueError (the source is refused with one sentence) for any other text, and for a weight outside +-100 %."""
    cell = str(text if text is not None else "").strip()
    if cell in ("", "-", "--"):
        return None
    if _THOUSANDS.fullmatch(cell):
        cell = cell.replace(",", "")
    if not _NUMBER.fullmatch(cell):
        raise ValueError(f"unreadable weight {cell[:20]!r}")
    value = float(cell) / 100
    if abs(value) > 1:
        raise ValueError(f"weight {cell[:20]!r} is outside 0-100 %")
    return value


def _iso(text: str, fmt: str) -> str:
    return datetime.strptime(text.strip(), fmt).date().isoformat()


def _top_rows(etf, lines, universe, as_of, url, top) -> list[dict]:
    """Holding rows: the `top` largest lines, then every later line that has a dataset ticker. lines = [(name, symbol, fraction)]."""
    lines = sorted((x for x in lines if x[2] > 0), key=lambda x: -x[2])
    keep = lines[:top] + [x for x in lines[top:] if dataset_ticker(x[1], universe)]
    return [_row(etf, "holding", " ".join(n.split()), dataset_ticker(s, universe), w, as_of, url) for n, s, w in keep]


def parse_ishares_csv(text: str, etf: str, universe, source_url: str, *, top: int = 25) -> list[dict]:
    """Holding, sector and country rows of an iShares holdings CSV (a title, the "Fund Holdings as of" line, a blank line,
    the table up to the next blank line, then a legal footer). Sectors and countries are summed over every line of the file."""
    lines = text.lstrip("\ufeff").splitlines()
    start = next((i for i, x in enumerate(lines) if x.startswith("Ticker,") and "Weight (%)" in x), None)
    stamp = next((re.match(r'Fund Holdings as of,\s*"?([^"]+?)"?\s*$', x) for x in lines if x.startswith("Fund Holdings as of")), None)
    if start is None or stamp is None:
        raise ValueError("not an iShares holdings file")
    as_of = _iso(stamp.group(1), "%b %d, %Y")
    table = []
    for x in lines[start + 1:]:
        if not x.strip():
            break
        table.append(x)
    equities, sectors, countries = [], {}, {}
    for r in csv.DictReader([lines[start]] + table):
        w = _weight(r.get("Weight (%)"))
        if w is None:
            continue
        if r.get("Asset Class") == "Equity":
            equities.append(((r.get("Name") or "").strip(), r.get("Ticker") or "", w))
        sector = (r.get("Sector") or "").strip()
        if sector not in ("", "-"):
            sector = "Communication Services" if sector == "Communication" else sector
            sectors[sector] = sectors.get(sector, 0.0) + w
        code = ISO3.get((r.get("Location") or "").strip())
        if code:
            countries[code] = countries.get(code, 0.0) + w
    rows = _top_rows(etf, equities, universe, as_of, source_url, top)
    rows += [_row(etf, "sector", n, "", w, as_of, source_url) for n, w in sorted(sectors.items(), key=lambda kv: -kv[1]) if w > 0]
    rows += [_row(etf, "country", c, "", w, as_of, source_url) for c, w in sorted(countries.items(), key=lambda kv: -kv[1]) if w >= MIN_COUNTRY]
    return rows


_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _column(ref: str) -> int:
    """Zero-based column of a cell reference: "A1" -> 0, "B7" -> 1, "AA3" -> 26."""
    m = re.match(r"([A-Z]+)", ref or "")
    if not m:
        raise ValueError("bad cell reference")
    n = 0
    for ch in m.group(1):
        n = n * 26 + ord(ch) - 64
    return n - 1


def _read_member(z: zipfile.ZipFile, name: str) -> bytes:
    """One member of the workbook, inflated in chunks and never beyond MAX_BYTES: the size the zip declares is not trusted."""
    out = bytearray()
    with z.open(name) as f:
        while chunk := f.read(65536):
            out += chunk
            if len(out) > MAX_BYTES:
                raise ValueError("the workbook expands to an unreasonable size")
    return bytes(out)


def read_xlsx_rows(data: bytes) -> list[list[str]]:
    """The first worksheet (xl/worksheets/sheet1.xml) of an XLSX as rows of strings: shared strings, inline strings and plain
    values; cells are placed by their column letters and rows by their number (a missing row is an empty list)."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            shared = []
            if "xl/sharedStrings.xml" in z.namelist():
                root = ET.fromstring(_read_member(z, "xl/sharedStrings.xml"))
                shared = ["".join(t.text or "" for t in si.iter(_NS + "t")) for si in root.iter(_NS + "si")]
            sheet = ET.fromstring(_read_member(z, "xl/worksheets/sheet1.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError, zlib.error, RuntimeError, NotImplementedError, EOFError) as exc:
        # corrupt deflate (zlib.error), encrypted member (RuntimeError), unknown compression (NotImplementedError), truncated stream
        raise ValueError("not a readable XLSX workbook") from exc
    by_number: dict[int, list[str]] = {}
    for n, row in enumerate(sheet.iter(_NS + "row"), start=1):
        cells, col = {}, -1
        for c in row.iter(_NS + "c"):
            col = _column(c.get("r")) if c.get("r") else col + 1
            if col >= MAX_COLUMNS:
                raise ValueError("a cell lies outside the worksheet limits")
            v = c.find(_NS + "v")
            if c.get("t") == "inlineStr":
                cells[col] = "".join(t.text or "" for t in c.iter(_NS + "t"))
            elif c.get("t") == "s":
                i = int(v.text) if v is not None and v.text else -1
                cells[col] = shared[i] if 0 <= i < len(shared) else ""
            else:
                cells[col] = (v.text or "") if v is not None else ""
        number = int(row.get("r") or n)
        if not 1 <= number <= MAX_ROWS:
            raise ValueError("a row lies outside the worksheet limits")
        by_number[number] = [cells.get(j, "") for j in range(max(cells) + 1)] if cells else []
    return [by_number.get(i, []) for i in range(1, max(by_number, default=0) + 1)]


def parse_ssga_xlsx(data: bytes, etf: str, universe, source_url: str, *, top: int = 25) -> list[dict]:
    """Holding rows of a State Street daily holdings XLSX. Its Sector column is "-", so there are no sector rows."""
    rows = read_xlsx_rows(data)
    stamp = next((m for row in rows for cell in row if (m := re.search(r"As of (\d{2}-[A-Za-z]{3}-\d{4})", cell))), None)
    head = next((i for i, row in enumerate(rows) if {"Ticker", "Weight"} <= {c.strip() for c in row}), None)
    if stamp is None or head is None:
        raise ValueError("not a State Street holdings file")
    as_of = _iso(stamp.group(1), "%d-%b-%Y")
    names = [c.strip() for c in rows[head]]
    at = {key: names.index(key) if key in names else None for key in ("Name", "Ticker", "Weight")}

    def cell(row, key):
        return row[at[key]].strip() if at[key] is not None and at[key] < len(row) else ""
    lines = []
    for row in rows[head + 1:]:
        if not any(c.strip() for c in row):
            break
        w, symbol = _weight(cell(row, "Weight")), cell(row, "Ticker")
        if symbol not in ("", "-") and w is not None and w > 0:
            lines.append((cell(row, "Name"), symbol, w))
    return _top_rows(etf, lines, universe, as_of, source_url, top)


def merge(existing: list[dict], fresh: list[dict]) -> list[dict]:
    """For each (etf, kind) present in `fresh`, the fresh rows replace the existing ones; every other existing row is kept."""
    covered = {(r["etf"], r["kind"]) for r in fresh}
    return [r for r in existing if (r["etf"], r["kind"]) not in covered] + list(fresh)


# --- input and output --------------------------------------------------------------------------------------------------
def fetch(url: str, timeout: int = TIMEOUT) -> bytes | None:
    """GET an https address with the honest User-Agent. The body, or None after one printed sentence (never the body)."""
    try:
        if not url.startswith("https://"):
            raise ValueError("only https addresses are fetched")
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("the answer is larger than a holdings file can be")
        return body
    except urllib.error.HTTPError as exc:
        reason = f"the server answered HTTP {exc.code}"
    except (OSError, ValueError, http.client.HTTPException) as exc:
        reason = str(exc)[:120] or type(exc).__name__
    print(f"Could not download {url.split('?')[0]}: {reason}.")
    return None


def _universe() -> set[str]:
    """The dataset tickers: tools.data.load_universe() when the starter data loads, else the 31 tickers of spec section 9."""
    try:
        from tools import data
        return set(data.load_universe().ticker)
    except Exception:    # noqa: BLE001  any failure to load the starter data (absent, unreadable) falls back to the 31 tickers
        return set(UNIVERSE_31)


def _read_rows(path: Path, *, strict: bool = False, universe=None) -> list[dict]:
    """Rows of a file in this module's own format, weight as a float. `strict` (a --manual file) also needs a known ETF, ISO dates
    and, given the dataset `universe`, a dataset ticker or an empty one (spec 05)."""
    with open(path, newline="", encoding="utf-8-sig") as f:    # utf-8-sig: a spreadsheet may add a byte-order mark
        reader = csv.DictReader(f)
        if reader.fieldnames != COLUMNS:
            raise ValueError("the columns must be " + ",".join(COLUMNS))
        rows = []
        for r in reader:
            if None in r or None in r.values():
                raise ValueError("a row does not have 7 columns")
            weight = float(r["weight"])
            if r["kind"] not in KINDS or not 0 <= weight <= 1:
                raise ValueError(f"a {r['etf']} row has kind {r['kind']!r} and weight {r['weight']}")
            if strict:
                if r["etf"] not in SOURCES:
                    raise ValueError(f"{r['etf']!r} is not one of the nine ETFs")
                _iso(r["as_of"], "%Y-%m-%d")
                if r["ticker"] and universe is not None and r["ticker"] not in universe:
                    raise ValueError(f"the ticker {r['ticker']!r} of a {r['etf']} row is not in the dataset (leave it empty)")
            rows.append({**r, "weight": weight})
    return rows


def _static_rows(today: str) -> list[dict]:
    """The asset-class labels of AGG, TLT, GLD and ZST.TO (as_of = the run date): labels, not issuer data."""
    rows = []
    for etf, (sector, countries) in STATIC.items():
        url = SOURCES[etf]["page"]
        rows.append(_row(etf, "sector", sector, "", 1.0, today, url))
        rows += [_row(etf, "country", code, "", w, today, url) for code, w in countries.items()]
    return rows


def _fmt(weight: float) -> str:
    s = f"{float(weight):.8f}".rstrip("0")
    return s + "0" if s.endswith(".") else s


def _tmp_path(path: Path) -> Path:
    return path.with_name(path.name + ".tmp")


def _write_rows(path: Path, rows: list[dict]) -> None:
    """Atomic write: <path>.tmp, then os.replace. Rows are grouped by ETF and kind (stable: each group keeps its order)."""
    order = {etf: i for i, etf in enumerate(OUTPUT_ORDER)}
    rows = sorted(rows, key=lambda r: (order.get(r["etf"], len(order)), KINDS.index(r["kind"])))
    tmp = _tmp_path(path)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)    # exclusive: a leftover or symlinked tmp raises FileExistsError
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows({**r, "weight": _fmt(r["weight"])} for r in rows)
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)             # ours (created above with O_EXCL); already gone after a successful replace
        except FileNotFoundError:
            pass


def _download_rows(universe: set[str]) -> list[dict]:
    """Rows from every issuer file we may download (mode "download"). A failed or unreadable file is skipped with one sentence."""
    fresh = []
    for etf, src in SOURCES.items():
        if src["mode"] != "download":
            continue
        body = fetch(src["download"], timeout=TIMEOUT)
        if body is None:
            continue
        try:
            if src["download"].endswith(".xlsx"):
                rows = parse_ssga_xlsx(body, etf, universe, src["page"])
            else:
                rows = parse_ishares_csv(body.decode("utf-8", errors="replace"), etf, universe, src["page"])
            if etf in BOND_FUND_SECTOR:    # keep the downloaded countries, label the sector (the file's own sectors are bond types)
                rows = [r for r in rows if r["kind"] == "country"]
                if rows:
                    rows.insert(0, _row(etf, "sector", BOND_FUND_SECTOR[etf], "", 1.0, rows[0]["as_of"], src["page"]))
            if not rows:
                raise ValueError("no rows")
        except (ValueError, csv.Error) as exc:
            print(f"The file downloaded for {etf} is not in the expected format ({exc}), so {etf} was not refreshed.")
            continue
        fresh += rows
    return fresh


def _missing(rows: list[dict]) -> list[str]:
    """What the equity ETFs still lack (the bond and gold funds have no holdings by design)."""
    gaps = []
    for etf, src in SOURCES.items():
        if src["mode"] == "static" or etf in BOND_FUND_SECTOR:
            continue
        have = {r["kind"] for r in rows if r["etf"] == etf}
        lacking = [k for k in KINDS if k not in have]
        if lacking:
            gaps.append(f"{etf} {'/'.join(lacking)}")
    return gaps


def _fail(message: str) -> int:
    print(message)
    return 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Refresh the local data/etf_holdings.csv from the ETF issuers' published holdings.")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="the file to write (default: data/etf_holdings.csv)")
    ap.add_argument("--manual", action="append", default=[], metavar="CSV",
                    help="rows typed by a human from a fund page, in the file's own format (repeatable)")
    ap.add_argument("--offline", action="store_true", help="download nothing")
    args = ap.parse_args(argv)
    out = Path(args.out)
    if os.path.lexists(_tmp_path(out)):    # lexists: a dangling symlink counts. Said before any download.
        return _fail(f"The temporary file {_tmp_path(out)} already exists (left by an earlier run, or a link), so nothing was written; "
                     "delete it and run again.")
    universe = _universe()
    try:
        existing = _read_rows(out) if out.exists() else []
    except (OSError, ValueError, csv.Error) as exc:
        return _fail(f"The existing file {out} cannot be read ({exc}), so nothing was written.")
    manual = []
    for path in args.manual:
        try:
            manual += _read_rows(Path(path), strict=True, universe=universe)
        except (OSError, ValueError, csv.Error) as exc:
            return _fail(f"The manual file {path} cannot be used ({exc}), so nothing was written.")
    downloaded = [] if args.offline else _download_rows(universe)
    covered = sorted({(r["etf"], r["kind"]) for r in downloaded + manual})
    if not covered:
        return _fail(f"No source could be refreshed, so {out} was left unchanged.")
    # a manual (etf, kind) group replaces the downloaded or static rows of that group: never both, so weights cannot add up past 100 %
    merged = merge(existing, merge(downloaded + _static_rows(date.today().isoformat()), manual))
    try:
        _write_rows(out, merged)
    except OSError as exc:
        return _fail(f"Could not write {out} ({exc.strerror or type(exc).__name__}), so it was left unchanged.")
    print(f"Wrote {len(merged)} rows to {out}. Refreshed: " + ", ".join(f"{etf} {kind}" for etf, kind in covered) + ".")
    gaps = _missing(merged)
    if gaps:
        print("Still missing, so look-through falls back for them (give --manual files typed from the fund pages): " + "; ".join(gaps) + ".")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
