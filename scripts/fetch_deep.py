"""Download the public long-history series into data/cache/deep/ and build the monthly proxy panel (plan C Task 13).

    python scripts/fetch_deep.py [--dest DIR] [--offline]

Nine public sources, each in its own new directory raw/<id>/ (gitignored; about 3.5 MB; the licence of each is in SOURCES):
the Kenneth French Data Library (4 zips), Statistics Canada tables 10-10-0122-01 and 10-10-0125-01 (2 zips), FRED USD/CAD
(2 csv) and the World Bank Pink Sheet monthly prices (1 xlsx, from which gold_monthly.csv is cut). Then
tools.deep.build_panel writes panel.csv, and manifest.json records the URL, bytes, SHA-256 and licence line of every file
and the retrieval time. The raw files are never committed (licences: spec section 23, ledger 17).
The downloads are untrusted data: they are only parsed (zipfile, xml.etree, pandas), never run or imported. A run replaces
all nine sources, the panel and the manifest, or none of them: everything lands in a staging directory first (the panel is
built there, and panel.csv and manifest.json are written there), so a failed download or an unreadable file leaves the previous
files as they were; the swap into place moves each old item aside first and puts them all back if any move fails.
--offline rebuilds panel.csv from the raw files on disk (no network at all) and writes a new manifest with one row per file
found: its SHA-256 read from disk, its licence from SOURCES, its URL from the previous manifest when there is one, and the
previous retrieval time, or "not recorded".
Exit 0 on success; 1 after one plain sentence for a failure (never a response body).
"""
from __future__ import annotations

import argparse
import hashlib
import html
import http.client
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # `python scripts/fetch_deep.py` puts scripts/, not the repo root, first
    sys.path.insert(0, str(ROOT))

DEFAULT_DEST = ROOT / "data" / "cache" / "deep"
USER_AGENT = "EPICENTRE-datathon/1.0"
TIMEOUT = 60
MAX_BYTES = 50_000_000       # the nine files total about 3.5 MB; an answer near this size is not one of them
MAX_PAGE = 2_000_000
WB_PAGE = "https://www.worldbank.org/en/research/commodity-markets"
WB_FILE = "CMO-Historical-Data-Monthly.xlsx"
WB_PINNED = "https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/" + WB_FILE
GOLD_CSV = "gold_monthly.csv"    # read by tools.deep.build_panel: columns `month` ("YYYY-MM") and `gold_usd_oz`
NOT_RECORDED = "not recorded"    # the manifest's retrieved_at when no download time is known (never null)

_FRENCH = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
_FRENCH_LICENCE = ("Kenneth R. French Data Library; no stated licence (Copyright Eugene F. Fama and Kenneth R. French): "
                   "kept local, never committed")
_STATCAN = "https://www150.statcan.gc.ca/n1/tbl/csv/"
_STATCAN_LICENCE = ('Source: Statistics Canada, Table {table}. Reproduced and distributed on an "as is" basis with the '
                    "permission of Statistics Canada (Open Licence)")
_FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
_FRED_LICENCE = "Board of Governors of the Federal Reserve System (US) via FRED; Public Domain: Citation Requested"
_WB_LICENCE = "World Bank Commodity Price Data (The Pink Sheet), CC BY 4.0; the gold price is the LBMA fix (third-party input)"
SOURCES = [   # `file` is the name tools.deep.build_panel expects inside raw/<id>/
    {"id": "french_factors", "url": _FRENCH + "F-F_Research_Data_Factors_CSV.zip", "file": "F-F_Research_Data_Factors_CSV.zip",
     "licence": _FRENCH_LICENCE},
    {"id": "french_12", "url": _FRENCH + "12_Industry_Portfolios_CSV.zip", "file": "12_Industry_Portfolios_CSV.zip",
     "licence": _FRENCH_LICENCE},
    {"id": "french_49", "url": _FRENCH + "49_Industry_Portfolios_CSV.zip", "file": "49_Industry_Portfolios_CSV.zip",
     "licence": _FRENCH_LICENCE},
    {"id": "french_countries", "url": _FRENCH + "F-F_International_Countries.zip", "file": "F-F_International_Countries.zip",
     "licence": _FRENCH_LICENCE},
    {"id": "statcan_10100122", "url": _STATCAN + "10100122-eng.zip", "file": "10100122-eng.zip",
     "licence": _STATCAN_LICENCE.format(table="10-10-0122-01")},
    {"id": "statcan_10100125", "url": _STATCAN + "10100125-eng.zip", "file": "10100125-eng.zip",
     "licence": _STATCAN_LICENCE.format(table="10-10-0125-01")},
    {"id": "fred_DEXCAUS", "url": _FRED + "DEXCAUS", "file": "DEXCAUS.csv", "licence": _FRED_LICENCE},
    {"id": "fred_EXCAUS", "url": _FRED + "EXCAUS", "file": "EXCAUS.csv", "licence": _FRED_LICENCE},
    {"id": "worldbank_gold", "url": WB_PINNED, "file": WB_FILE, "licence": _WB_LICENCE},
]
_ERRORS = (OSError, ValueError, KeyError, IndexError, TypeError, RuntimeError, NotImplementedError, zlib.error,   # a corrupt file
           zipfile.BadZipFile, ET.ParseError, http.client.HTTPException)
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


# --- input ------------------------------------------------------------------------------------------------------------
def _get(url: str, limit: int) -> bytes:
    """GET an https address with the honest User-Agent.

    ValueError: plain http, a redirect to http, a body over `limit`, or a body shorter than the Content-Length the server
    announced (read(n) alone returns a cut-short body without complaint, and a cut-short CSV would shorten a series)."""
    if not url.startswith("https://"):
        raise ValueError("only https addresses are fetched")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        if not response.geturl().startswith("https://"):
            raise ValueError("the server redirected to an unencrypted address")
        body = response.read(limit + 1)
        declared = response.headers.get("Content-Length")
    if len(body) > limit:
        raise ValueError(f"the answer is larger than {limit:,} bytes")
    if declared and declared.isdigit() and len(body) != int(declared):
        raise ValueError(f"the download was cut short ({len(body):,} of {int(declared):,} bytes)")
    return body


def download(url: str, dest: Path) -> bytes:
    """GET `url` and write the body to `dest`, a file inside a new directory. Returns the bytes; raises, writing nothing, on any failure."""
    body = _get(url, MAX_BYTES)
    dest.write_bytes(body)
    return body


def _page(url: str) -> str | None:
    """The text of a web page, or None on any error (the caller then falls back to a pinned address)."""
    try:
        return _get(url, MAX_PAGE).decode("utf-8", errors="replace")
    except (OSError, ValueError, http.client.HTTPException):
        return None


def world_bank_url(page_html: str | None) -> str:
    """The CMO-Historical-Data-Monthly.xlsx link on the commodity-markets page (its document hash changes monthly).

    Only an https link on worldbank.org counts; no page, no link or any other link gives the pinned address."""
    for href in re.findall(r"""href\s*=\s*["']([^"']*""" + re.escape(WB_FILE) + r""")["']""", page_html or "", flags=re.I):
        url = urljoin(WB_PAGE, html.unescape(href))
        parts = urlparse(url)
        host = parts.hostname or ""
        if parts.scheme == "https" and (host == "worldbank.org" or host.endswith(".worldbank.org")):
            return url
    return WB_PINNED


# --- the gold workbook (zipfile + xml.etree: no openpyxl, no new dependency) ----------------------------------------------
def _column(ref: str) -> int:
    """0-based column number of a cell reference such as "AB12"."""
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def gold_from_xlsx(path) -> list[tuple[str, float]]:
    """[(month "YYYY-MM", USD per troy ounce)] from the "Monthly Prices" sheet of the World Bank Pink Sheet workbook.

    The gold column is the one headed "Gold". A row counts when its first cell reads like 1960M01 and its gold cell is a
    number; a text cell there (the file's "..") is a missing month, left out, never a zero.
    """
    with zipfile.ZipFile(path) as z:
        if any(info.file_size > MAX_BYTES for info in z.infolist()):
            raise ValueError("a part of the workbook is larger than a Pink Sheet can be")
        book = ET.fromstring(z.read("xl/workbook.xml"))
        rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
        sheet = next((s for s in book.find("m:sheets", _NS) if s.get("name") == "Monthly Prices"), None)
        if sheet is None:
            raise ValueError('no sheet named "Monthly Prices" in the workbook')
        target = rels[sheet.get("{%s}id" % _NS["r"])]
        part = target.lstrip("/") if target.startswith("/") else "xl/" + target
        strings = []
        if "xl/sharedStrings.xml" in z.namelist():
            strings = ["".join(t.text or "" for t in si.iter("{%s}t" % _NS["m"]))
                       for si in ET.fromstring(z.read("xl/sharedStrings.xml"))]
        rows = []
        for row in ET.fromstring(z.read(part)).iter("{%s}row" % _NS["m"]):
            cells = {}
            for c in row.findall("m:c", _NS):
                v = c.find("m:v", _NS)
                if v is not None and v.text is not None:
                    cells[_column(c.get("r"))] = strings[int(v.text)] if c.get("t") == "s" else v.text
            rows.append(cells)
    head = next((i for i, r in enumerate(rows) if any(v.strip().lower() == "gold" for v in r.values())), None)
    if head is None:
        raise ValueError('no column headed "Gold" on the "Monthly Prices" sheet')
    col = next(k for k, v in rows[head].items() if v.strip().lower() == "gold")
    out = []
    for r in rows[head + 1:]:
        month = r.get(0, "")
        if re.fullmatch(r"\d{4}M\d{2}", month) and col in r:
            try:
                out.append((f"{month[:4]}-{month[5:]}", float(r[col])))
            except ValueError:
                pass                                   # ".." and other text: a missing month stays missing
    return out


# --- output -------------------------------------------------------------------------------------------------------------
def _why(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"the server answered HTTP {exc.code}"
    return str(exc)[:120] or type(exc).__name__


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _shown(path: Path) -> str:
    """The path as the manifest writes it: relative to the repository root when inside it."""
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _cut_gold(folder: Path) -> None:
    """Write gold_monthly.csv (month,gold_usd_oz) beside the workbook in `folder`."""
    rows = gold_from_xlsx(folder / WB_FILE)
    if not rows:
        raise ValueError("no monthly gold price found in the workbook")
    _write_atomic(folder / GOLD_CSV, ("month,gold_usd_oz\n" + "".join(f"{m},{v}\n" for m, v in rows)).encode())


def _previous_manifest(path: Path) -> dict:
    """The manifest of the last run, or {} when there is none or it cannot be read."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _previous_urls(previous: dict) -> dict:
    """{source id: url} from the files of the previous manifest; entries that are not a pair of strings are left out."""
    files = previous.get("files")
    if not isinstance(files, list):
        return {}
    return {f["id"]: f["url"] for f in files if isinstance(f, dict) and isinstance(f.get("id"), str) and isinstance(f.get("url"), str)}


def _rows(raw: Path, where: Path, urls: dict) -> list[dict]:
    """The manifest row of every source whose file is on disk, in SOURCES order.

    `path` is the file's place under `raw`; `bytes` and `sha256` are read from the file under `where` (the staging copy of raw
    before the swap, raw itself offline); `url` comes from `urls`, else SOURCES; `licence` always from SOURCES (red gate 8)."""
    return [{"id": s["id"], "url": urls.get(s["id"], s["url"]), "path": _shown(raw / s["id"] / s["file"]),
             "bytes": (where / s["id"] / s["file"]).stat().st_size, "sha256": _sha256(where / s["id"] / s["file"]),
             "licence": s["licence"]} for s in SOURCES if (where / s["id"] / s["file"]).is_file()]


def _fetch(stage: Path) -> list[str] | None:
    """Download the nine sources, each into its own new directory under `stage`, and cut the gold file.

    The URLs used, in SOURCES order; None after one printed sentence."""
    page = _page(WB_PAGE)
    urls = []
    for src in SOURCES:
        url = world_bank_url(page) if src["id"] == "worldbank_gold" else src["url"]
        folder = stage / src["id"]
        folder.mkdir()                                   # its own new, empty directory
        try:
            download(url, folder / src["file"])
            if src["id"] == "worldbank_gold":
                _cut_gold(folder)
        except _ERRORS as exc:
            print(f"Could not download {src['id']} from {url.split('?')[0]}: {_why(exc)}.")
            return None
        urls.append(url)
        print(f"{src['id']}: {(folder / src['file']).stat().st_size:,} bytes")
    return urls


def _move(src: Path, dst: Path) -> None:
    """One rename inside one directory tree: it happens whole or not at all. The swap in _commit is made of these."""
    os.replace(src, dst)


def _commit(stage: Path, dest: Path, ids: list[str]) -> None:
    """Move the staged raw/<id> directories named in `ids`, then panel.csv and manifest.json, into `dest`; or change nothing.

    Each old item first goes into stage/old/. On ANY exception (a full disk, Ctrl-C) every move made is undone, last first, and
    the exception is raised again; a move that cannot be undone is skipped and its file stays in stage/old (see _drop)."""
    raw, old, undo = dest / "raw", stage / "old", []
    pairs = [(raw / i, stage / i) for i in ids] + [(dest / name, stage / name) for name in ("panel.csv", "manifest.json")]

    def move(src: Path, dst: Path) -> None:
        _move(src, dst)
        undo.append(lambda: _move(dst, src))
    try:
        old.mkdir()
        if ids and not raw.exists():
            raw.mkdir()
            undo.append(raw.rmdir)                   # a first run: raw/ itself is new, and goes again if the run fails
        for target, new in pairs:
            if target.exists():
                move(target, old / target.name)
            move(new, target)
    except BaseException:
        for back in reversed(undo):
            try:
                back()
            except OSError:
                pass                                 # put back as much as possible
        raise
    shutil.rmtree(old, ignore_errors=True)           # the swap is whole: the previous files are no longer needed


def _drop(stage: Path) -> None:
    """Delete the staging directory, unless a failed swap left files of the previous run in stage/old (then say where)."""
    if any((stage / "old").glob("*")):
        print(f"The previous files could not all be put back; they are kept in {stage / 'old'}.")
    else:
        shutil.rmtree(stage, ignore_errors=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Download the deep-history sources and build the monthly proxy panel.")
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST, help="cache directory (default: data/cache/deep)")
    parser.add_argument("--offline", action="store_true", help="rebuild panel.csv from the raw files on disk; no network")
    args = parser.parse_args(argv)
    dest, offline = args.dest, args.offline
    raw, panel_path, manifest_path = dest / "raw", dest / "panel.csv", dest / "manifest.json"
    from tools import deep                               # inside main: the repo root is on sys.path, and tests patch deep.build_panel
    dest.mkdir(parents=True, exist_ok=True)
    previous = _previous_manifest(manifest_path)
    stage = Path(tempfile.mkdtemp(prefix=".incoming-", dir=dest))       # new and empty; offline it holds only panel.csv and manifest.json
    try:
        if offline:
            if (raw / "worldbank_gold" / WB_FILE).exists():
                _cut_gold(raw / "worldbank_gold")
            panel, where, urls, ids = deep.build_panel(raw), raw, _previous_urls(previous), []
            retrieved_at = previous.get("retrieved_at")
            if not isinstance(retrieved_at, str) or not retrieved_at:
                retrieved_at = NOT_RECORDED
        else:
            fetched = _fetch(stage)
            if fetched is None:
                return 1
            panel = deep.build_panel(stage)              # an unreadable or re-laid-out file fails here, before anything is replaced
            ids = [s["id"] for s in SOURCES]
            where, urls = stage, dict(zip(ids, fetched))
            retrieved_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        table = panel.copy()
        table.index = table.index.strftime("%Y-%m")
        table.index.name = "month"
        (stage / "panel.csv").write_bytes(table.to_csv(lineterminator="\n").encode())
        first, last = (table.index[0], table.index[-1]) if len(table) else (None, None)
        manifest = {"retrieved_at": retrieved_at, "files": _rows(raw, where, urls),
                    "panel": {"path": _shown(panel_path), "rows": len(table), "first": first, "last": last,
                              "sha256": _sha256(stage / "panel.csv")}}
        (stage / "manifest.json").write_bytes((json.dumps(manifest, indent=2) + "\n").encode())
        _commit(stage, dest, ids)                        # the one step that touches dest: all of it, or none
    except _ERRORS as exc:
        print(f"Could not build the deep-history panel: {_why(exc)}.")
        return 1
    finally:
        _drop(stage)
    print(f"panel: {len(table):,} months, {first} to {last}, written to {_shown(panel_path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
