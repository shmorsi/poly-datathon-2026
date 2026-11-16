"""Look through ETFs: what the money is really in (spec sections 9 and 10; plan A Task 6).

"You own NVIDIA three times": a direct line plus the slice of every ETF that holds it. Exposure only,
never returns, and a snapshot of today's holdings: for a past `as_of` the answer is direct mode (pass
`as_of=`, or `holdings=pd.DataFrame()`). The processing, in this order:
  1. `data/etf_holdings.csv` (local, never committed: issuers forbid redistribution, pitfall 10) is read
     once per call; rows are `etf, kind (holding | sector | country), name, ticker, weight, as_of`;
  2. each (etf, kind) group whose weights add up to more than 1.5 is in percent and is divided by 100
     (a fraction file is untouched); sector names go ICB -> GICS (weights unchanged, spec 9); a holding with
     no dataset ticker stays "" (it still counts toward `coverage`); Alphabet Class C (GOOG) is Alphabet,
     so it is GOOGL (ledger 14): one company, not understated by about 45 %; rows with a blank, zero or
     negative weight, rows of another kind and rows without an ISO date are dropped; of two snapshots of
     one (etf, kind) only the newest is kept (before the percent test: a doubled group is never shrunk);
  3. weights are shares of the whole portfolio and must add up to 1 (normalize first);
  4. `stocks` = dataset equities only: the direct line plus, per ETF, ETF weight x the holding weight;
     `sectors` = direct equities by their universe sector plus equity ETFs by their sector rows without
     `NON_SECTORS` (bonds, gold, crypto and cash are asset classes, not sectors, spec 5); `countries` =
     listing countries, gold in GLOBAL, an ETF with country rows by those rows (an unexplained remainder of
     0.1 % or more is "OTHER"; rows adding up to more than 100 % are scaled to 100 %);
  5. no file, an empty or zero-byte file, or `holdings=pd.DataFrame()`: direct mode, `mode == "direct"`,
     equity ETFs add nothing to `sectors` (broad-market ETFs are exempt, spec 5), `coverage`, `snapshot`
     and `gaps` are empty;
  6. `as_of` (default DATASET_END) is the run's date: it labels the output and dates the ESG flags (never
     the newest row of the file: the static GLD / ZST.TO label rows are stamped with the fetch day); rows
     dated after it are ignored, and a holdings snapshot newer than it is direct mode, `source` saying so.
"Unknown is never a pass": `coverage` is the share of each held ETF that its holding rows list (a held
equity ETF with no rows at all is 0.0), so the caller can say how much of a fund it could not see; `gaps`
names a held equity ETF that has no holding rows or no sector rows (its sectors are unknown, not zero).
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from tools.data import DATASET_END, load_universe
from tools.portfolio import _held      # the one weight check: tickers upper-cased, none below 0, sum 1

ROOT = Path(__file__).resolve().parents[1]
HOLDINGS_CSV = ROOT / "data" / "etf_holdings.csv"
ICB_TO_GICS = {"Technology": "Information Technology", "Telecommunications": "Communication Services",
               "Basic Materials": "Materials"}
NON_SECTORS = {"Bonds", "Gold", "Crypto", "Cash", "Cash and/or Derivatives"}
TICKER_ALIASES = {"GOOG": "GOOGL"}                 # Alphabet Class C is the same company as Class A
COLUMNS = ["etf", "kind", "name", "ticker", "weight", "as_of", "source_url"]
KINDS = ("holding", "sector", "country")
PERCENT_ABOVE = 1.5                                # a group adding up to more than this is in percent
OTHER_FROM = 0.001                                 # an unexplained country share below this is rounding
DIRECT_SOURCE = "assets_universe.csv (direct holdings, no ETF holdings file)"
LOOKTHROUGH_SOURCE = ("ETF holdings from data/etf_holdings.csv (local file; issuer fund files: top holdings plus "
                      "sector and country splits; `snapshot` is the holdings date per ETF, the splits can be "
                      "older); exposure only, a snapshot of today's holdings, never a return or a forecast")
_KIND_WORDS = (("holding", "holdings"), ("sector", "sectors"), ("country", "countries"))
_ALPHABET_C = re.compile(r"\balphabet\b.*\b(?:cl|class)\.?\s*c\b", re.IGNORECASE)


def _normalize(frame: pd.DataFrame) -> pd.DataFrame:
    """A clean copy of holdings rows (see the module docstring, step 2); an empty frame comes back as is."""
    if frame.empty:
        return frame
    missing = [c for c in COLUMNS[:6] if c not in frame.columns]
    if missing:
        raise ValueError(f"The ETF holdings need the columns {', '.join(COLUMNS)} (missing: {', '.join(missing)}).")
    out = frame.copy()
    if "source_url" not in out.columns:
        out["source_url"] = ""
    for col in ("etf", "kind", "name", "ticker", "as_of", "source_url"):
        out[col] = out[col].fillna("").astype(str).str.strip()
    out["etf"], out["kind"], out["ticker"] = out["etf"].str.upper(), out["kind"].str.lower(), out["ticker"].str.upper()
    out["weight"] = pd.to_numeric(out["weight"], errors="coerce")
    out["as_of"] = out["as_of"].str[:10]
    out = out[out["kind"].isin(KINDS) & out["weight"].between(0.0, float("inf"), inclusive="neither")
              & out["as_of"].str.fullmatch(r"\d{4}-\d{2}-\d{2}")].copy()
    out = out[out["as_of"] == out.groupby(["etf", "kind"])["as_of"].transform("max")]   # two snapshots: the newest
    total = out.groupby(["etf", "kind"])["weight"].transform("sum")
    out["weight"] = out["weight"].where(total <= PERCENT_ABOVE, out["weight"] / 100.0)
    sector = out["kind"] == "sector"
    out.loc[sector, "name"] = out.loc[sector, "name"].replace(ICB_TO_GICS)
    out["ticker"] = out["ticker"].replace(TICKER_ALIASES)
    alphabet_c = (out["kind"] == "holding") & (out["ticker"] == "") & out["name"].str.contains(_ALPHABET_C)
    out.loc[alphabet_c, "ticker"] = "GOOGL"
    return out[COLUMNS].reset_index(drop=True)


def load_holdings(path=None) -> pd.DataFrame | None:
    """`data/etf_holdings.csv` as clean rows (module docstring, step 2); None when the file is absent.

    Columns: etf, kind, name, ticker ("" when the holding is not a dataset ticker), weight (a fraction),
    as_of (ISO string), source_url. The path is read at call time, so tests can point HOLDINGS_CSV elsewhere.
    """
    target = Path(path) if path is not None else HOLDINGS_CSV
    if not target.exists():
        return None
    try:
        return _normalize(pd.read_csv(target, dtype=str))
    except pd.errors.EmptyDataError:               # a zero-byte file: no holdings, so direct mode
        return pd.DataFrame(columns=COLUMNS)


def _country_shares(rows: pd.DataFrame) -> dict:
    """{ISO3: share of the ETF} from its country rows ({} without rows). Rows adding up to more than 100 %
    (the issuer's rounding) are scaled to 100 %; an unexplained remainder of OTHER_FROM or more is "OTHER"."""
    shares: dict[str, float] = {}
    for name, share in zip(rows["name"].str.upper(), rows["weight"]):
        shares[name or "OTHER"] = shares.get(name or "OTHER", 0.0) + float(share)
    total = sum(shares.values())
    if total > 1.0:
        return {name: share / total for name, share in shares.items()}
    if shares and 1.0 - total >= OTHER_FROM - 1e-12:
        shares["OTHER"] = shares.get("OTHER", 0.0) + 1.0 - total
    return shares


def _flagged(esg_flags, as_of: str) -> set:
    """The values-screen tickers: the caller's set, else data/esg_flags.csv as known at `as_of` (B's reader)."""
    if esg_flags is None:
        import governance          # only when asked: the flag reader lives with the rules (ledger 16)
        esg_flags = governance.load_esg_flags(as_of)
    return {str(t).strip().upper() for t in esg_flags}


def _dates_note(by_etf: dict, held: dict) -> str:
    """"; snapshot dates by ETF: QQQ holdings 2026-11-12, sectors 2026-10-31, ..." for the held ETFs with rows."""
    parts = []
    for etf in sorted(t for t in held if t in by_etf):
        newest = by_etf[etf].groupby("kind")["as_of"].max()
        parts.append(f"{etf} " + ", ".join(f"{word} {newest[kind]}" for kind, word in _KIND_WORDS if kind in newest))
    return "; snapshot dates by ETF: " + "; ".join(parts) if parts else ""


def look_through(weights, *, holdings=None, universe=None, esg_flags=None, as_of=None) -> dict:
    """Exposure of a portfolio (weights summing to 1) direct and inside its ETFs, as shares of the whole.

    Returns {"stocks": {ticker: {"direct", "via": [{"etf", "weight"}], "total"}}, "sectors": {name: w},
    "countries": {ISO3: w}, "esg_indirect": {ticker: w}, "energy_via_etfs", "coverage": {etf: share},
    "snapshot": {etf: date}, "gaps": [{"etf", "missing", "coverage"}], "mode": "lookthrough" | "direct",
    "source", "as_of"}; the dicts are ordered by size. `esg_indirect` = the names inside ETFs whose
    universe sector is Energy or that are in `esg_flags` (a set of tickers; None reads data/esg_flags.csv
    through governance.load_esg_flags at the run's date); `energy_via_etfs` = the sum of ETF weight x the
    ETF's Energy share. `coverage` and `snapshot` name every held ETF that has holding rows (a held equity
    ETF with none: 0.0, no date). `gaps` names what a held equity ETF lacks, `missing` "holdings" or
    "sectors" (coverage 0.0 for both): its sectors are then unknown, not zero, so the caller must say so.
    `as_of` is the run's date (default DATASET_END): it is the output label and the flag date, rows dated
    after it are ignored, and a holdings snapshot newer than it gives direct mode (spec 10: a past date
    uses direct holdings only). `holdings=None` reads the file; None or empty rows also give direct mode.
    Unknown ticker, a bad date or weights not summing to 1: ValueError. Module docstring: the rules.
    """
    held = _held(weights)
    uni = (load_universe() if universe is None else universe).set_index("ticker")
    for t in held:
        if t not in uni.index:
            raise ValueError(f"Unknown ticker: {t}")
    run = DATASET_END if as_of is None else pd.Timestamp(as_of).strftime("%Y-%m-%d")
    frame = load_holdings() if holdings is None else _normalize(holdings)
    look, source = frame is not None and not frame.empty, DIRECT_SOURCE
    if look:
        newest = frame.loc[frame["kind"] == "holding", "as_of"].max()      # NaN without holding rows
        if isinstance(newest, str) and newest > run:                        # a past run: today's snapshot is not its picture
            look, source = False, (f"assets_universe.csv (direct holdings: the ETF holdings snapshot is dated "
                                   f"{newest}, after as_of {run})")
        else:
            frame = frame[frame["as_of"] <= run]                            # nothing dated after the run reaches the output
            look = not frame.empty
            if not look:
                source = f"assets_universe.csv (direct holdings, no ETF holdings dated on or before {run})"
    by_etf = dict(iter(frame.groupby("etf"))) if look else {}

    stocks: dict[str, dict] = {}
    sectors: dict[str, float] = {}
    countries: dict[str, float] = {}
    coverage: dict[str, float] = {}
    snapshot: dict[str, str] = {}
    gaps: list[dict] = []
    energy = 0.0

    def add(book: dict, key: str, amount: float) -> None:
        book[key] = book.get(key, 0.0) + float(amount)

    for t, w in held.items():
        asset, rows = str(uni.at[t, "asset_class"]), by_etf.get(t)
        listing = "GLOBAL" if asset == "etf_commodity" else str(uni.at[t, "country"])    # gold is global, not USA
        if asset == "equity":
            stocks.setdefault(t, {"direct": 0.0, "via": []})["direct"] += w
            add(sectors, str(uni.at[t, "sector"]), w)
        holds = rows[rows["kind"] == "holding"] if rows is not None else None
        splits = rows[rows["kind"] == "sector"] if rows is not None else None
        if look and asset == "etf_equity":                       # unknown is never a pass: name what is missing
            for what, part in (("holdings", holds), ("sectors", splits)):
                if part is None or part.empty:
                    gaps.append({"etf": t, "missing": what, "coverage": 0.0})
            if holds is None or holds.empty:
                coverage[t] = 0.0                                # held, but nothing of it is known
        if rows is None or not asset.startswith("etf"):
            add(countries, listing, w)
            continue
        if not holds.empty:
            coverage[t], snapshot[t] = float(holds["weight"].sum()), str(holds["as_of"].max())
            for ticker, share in holds.groupby("ticker")["weight"].sum().items():
                if ticker and ticker in uni.index and uni.at[ticker, "asset_class"] == "equity":
                    stocks.setdefault(ticker, {"direct": 0.0, "via": []})["via"].append(
                        {"etf": t, "weight": float(w * share)})
        if asset == "etf_equity":
            for name, share in splits.groupby("name")["weight"].sum().items():
                if name not in NON_SECTORS:
                    add(sectors, name, w * share)
                    energy += float(w * share) if name == "Energy" else 0.0
        shares = {} if asset == "etf_commodity" else _country_shares(rows[rows["kind"] == "country"])
        for country, share in (shares or {listing: 1.0}).items():        # no country rows: the listing country
            add(countries, country, w * share)

    for entry in stocks.values():
        entry["via"].sort(key=lambda v: (-v["weight"], v["etf"]))
        entry["total"] = float(entry["direct"] + sum(v["weight"] for v in entry["via"]))
    gaps.sort(key=lambda g: (g["etf"], g["missing"]))
    flagged = _flagged(esg_flags, run) if look else set()
    inside = {t: sum(v["weight"] for v in e["via"]) for t, e in stocks.items()
              if e["via"] and (uni.at[t, "sector"] == "Energy" or t in flagged)}

    def ranked(book: dict) -> dict:
        return dict(sorted(book.items(), key=lambda kv: (-kv[1], kv[0])))

    return {"stocks": dict(sorted(stocks.items(), key=lambda kv: (-kv[1]["total"], kv[0]))),
            "sectors": ranked(sectors), "countries": ranked(countries), "esg_indirect": ranked(inside),
            "energy_via_etfs": float(energy), "coverage": coverage, "snapshot": snapshot, "gaps": gaps,
            "mode": "lookthrough" if look else "direct",
            "source": LOOKTHROUGH_SOURCE + _dates_note(by_etf, held) if look else source, "as_of": run}


SPLIT_RANGE = (0.98, 1.02)                         # a sector or country split must add up to about 100 %
VALIDATE_SOURCE = ("data/etf_holdings.csv (local file; issuer fund files), checked per ETF after normalizing "
                   "(percent groups divided by 100); exposure data only, never a return")


def validate_holdings(as_of=DATASET_END, *, holdings=None) -> dict:
    """Per ETF in the holdings file (plan A Task 18): {"etfs": {etf: {"snapshot", "coverage", "sector_sum",
    "country_sum", "rows", "flags"}}, "source", "as_of"}.

    `snapshot` = the newest date of its holding rows (None without any, as in look_through); `coverage` = the
    sum of its holding weights (0.0 without any); a split sum is None without rows; `rows` = its clean rows.
    `flags` names in plain words a holdings snapshot dated after `as_of` (no look-ahead; as in look_through, the
    static label rows stamped with the fetch day are not a snapshot), a split outside 98-102 % and a missing split.
    Rows are cleaned first (module docstring, step 2). No file or no rows: no ETF, never a crash.
    """
    run = pd.Timestamp(as_of).strftime("%Y-%m-%d")
    frame = load_holdings() if holdings is None else _normalize(holdings)
    if frame is None or frame.empty:
        state = "absent" if frame is None else "without rows"
        return {"etfs": {}, "source": f"data/etf_holdings.csv is {state}: nothing to check (direct mode)", "as_of": run}
    etfs = {}
    for etf, rows in frame.groupby("etf"):
        sums = {kind: float(part["weight"].sum()) if len(part) else None
                for kind, part in ((k, rows[rows["kind"] == k]) for k in KINDS)}
        holds = rows.loc[rows["kind"] == "holding", "as_of"]
        snapshot, flags = (str(holds.max()) if len(holds) else None), []
        if snapshot is not None and snapshot > run:
            flags.append(f"dated {snapshot}, after as_of {run}")
        for kind in ("sector", "country"):
            total = sums[kind]
            if total is None:
                flags.append(f"no {kind} split")
            elif not SPLIT_RANGE[0] <= total <= SPLIT_RANGE[1]:
                flags.append(f"{kind} split sums to {total * 100:.1f} %")
        etfs[etf] = {"snapshot": snapshot, "coverage": sums["holding"] or 0.0,
                     "sector_sum": sums["sector"], "country_sum": sums["country"], "rows": int(len(rows)),
                     "flags": flags}
    return {"etfs": etfs, "source": VALIDATE_SOURCE, "as_of": run}
