"""Deep history (spec section 23, ledger 17 and 30). Part (a), plan A Task 15: bond maths, source readers, the
monthly proxy panel, the loaders. Part (b), Task 16 (end of file): the replay, the proxy check, the Result fragment.

Deep history replays a portfolio through 11 crises before the starter data (1973-2020) with public
stand-ins ("proxies"). It is a disclosure (an assumption, never the verdict). This module turns the
public downloads into ONE monthly table, `panel.csv`, and loads that table and the two catalogues:
  1. a proxy is a monthly TOTAL return in CAD, as a fraction; months are month-end Timestamps (the
     index `tools.data.make_market` accepts); in the file the `month` column is "YYYY-MM";
  2. US lines (Fama/French market and industries) x the month-end USD/CAD move (FRED DEXCAUS); gold
     (World Bank monthly average) x the monthly-average move (FRED EXCAUS); Canada is already CAD;
  3. CA_EQ is Fama/French Canada (local currency) from 1977-01; before, the TSX composite close return
     plus the previous month's dividend yield / 12 (Statistics Canada 10-10-0125-01);
  4. CAD_BOND is the Government of Canada par-bond ladder `LADDER` (10-10-0122-01); CAD_TBILL accrues the
     previous month's 3-month bill yield / 12 (v122531; the auction series v122541 fills what it lacks);
  5. a missing value stays NaN: nothing is filled, carried forward or set to zero. A hole in one ladder
     leg is a hole in CAD_BOND, and the replay then says "Can't say" instead of inventing a return.
Downloads are untrusted data: read with zipfile and pandas only, never executed. The raw files stay in
data/cache/deep/raw/ (gitignored, licences); the tests use small synthetic fixtures.
"""
from __future__ import annotations

import copy
import csv
import io
import json
import re
import zipfile
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import numpy as np
import pandas as pd

from tools.data import DATASET_END, load_market, make_market
from tools.portfolio import series_from_market

ROOT = Path(__file__).resolve().parents[1]
DEEP_DIR = ROOT / "data" / "cache" / "deep"
PANEL_PATH = DEEP_DIR / "panel.csv"
MANIFEST_PATH = DEEP_DIR / "manifest.json"
EPISODES_PATH = ROOT / "data" / "deep_episodes.csv"
PROXIES_PATH = ROOT / "data" / "deep_proxies.csv"
DEEP_START, DEEP_END, OVERLAP_START = "1973-01", "2021-10", "2021-12"
STRONG = {"min_months": 24, "corr": 0.95, "te_ann": 0.05, "drawdown_gap": 0.03}
LADDER = {"v122558": (2.0, 0.28), "v122485": (4.0, 0.22), "v122486": (7.5, 0.21), "v122487": (20.0, 0.29)}
PROXY_IDS = ("CA_EQ", "CAD_BOND", "CAD_TBILL", "GOLD", "US_MKT", "BUSEQ", "CHIPS", "SOFTW", "HARDW", "RTAIL",
             "AUTOS", "BANKS", "DRUGS", "HSHLD", "OIL")
SOURCE = ("Proxy replay (assumption): Fama/French US industry and Canada returns, Bank of Canada yields via "
          "Statistics Canada tables 10-10-0122-01 and 10-10-0125-01, World Bank gold, FRED USD/CAD; monthly, CAD")

_INDUSTRY_49 = {"CHIPS": "Chips", "SOFTW": "Softw", "HARDW": "Hardw", "RTAIL": "Rtail", "AUTOS": "Autos",
                "BANKS": "Banks", "DRUGS": "Drugs", "HSHLD": "Hshld", "OIL": "Oil"}
_MISSING = -99.99              # Fama/French write -99.99 or -999 for "no value"; Statistics Canada, -99.999
_CANADA_FROM = pd.Timestamp("1977-01-01")   # Fama/French Canada starts here; the TSX splice covers the months before


# --- small helpers ------------------------------------------------------------------------------------
def _month_end(periods):
    """Month-end Timestamps from "YYYY-MM" strings, Periods or datetimes (midnight, one per month)."""
    return pd.PeriodIndex(periods, freq="M").to_timestamp(how="end").normalize()


def _complete(x):
    """`x` (Series or frame, month-end index) on every month from its first to its last: a gap becomes a NaN
    row, so shift(1) is always the previous calendar month."""
    if x.empty:
        return x
    span = pd.period_range(x.index.min().to_period("M"), x.index.max().to_period("M"), freq="M")
    return x.reindex(_month_end(span))


def _growth(levels):
    """Month-on-month change of a level series; a missing month gives NaN, never a longer-period change."""
    levels = _complete(levels)
    return levels / levels.shift(1) - 1


def _mask(x):
    """The "no value" markers (see _MISSING) become NaN, never a -100 % return."""
    return x.mask(x <= _MISSING)


def _read_zip(zip_path, name=None):
    """The bytes of one zip member: `name`, or the only data file (not a *MetaData* file)."""
    with zipfile.ZipFile(zip_path) as z:
        names = [name] if name else [n for n in z.namelist() if n.lower().endswith(".csv") and "metadata" not in n.lower()]
        if not names:
            raise ValueError(f"no data file in {zip_path}")
        return z.read(names[0])


# --- bond maths --------------------------------------------------------------------------------------
def par_bond_return(yields_pct, maturity_years):
    """Monthly total return of a constant-maturity par bond (semiannual coupons) from monthly yields in percent.

    At each month-end the investor holds a bond bought at par one month earlier, at the previous month's
    yield y0 (so its coupon is y0), now `maturity_years - 1/12` from maturity and priced at the new yield y1:
    price = (y0/y1)(1 - v) + v with v = (1 + y1/2)^(-2(T - 1/12)); return = price - 1 + y0/12 (a month of
    coupon). Closed form, no duration shortcut. The first value, and any month next to a missing yield, is NaN.
    """
    y = pd.Series(yields_pct, dtype="float64") / 100.0
    y0, y1 = y.shift(1), y
    v = (1 + y1 / 2) ** (-2 * (maturity_years - 1 / 12))
    return (y0 / y1) * (1 - v) + v - 1 + y0 / 12


# --- source readers (each returns month-end indexed fractions or raw levels) -------------------------------
def read_french_monthly(zip_path, columns):
    """The FIRST table (value-weighted, monthly) of a Fama/French CSV zip: the `columns` asked for, as fractions.

    Header names are matched without their padding ("Food " is "Food"); -99.99 / -999 are NaN. The equal-
    weighted and annual tables that follow in the same file are never read.
    """
    lines = _read_zip(zip_path).decode("latin-1").splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith(",")), None)
    if start is None:
        raise ValueError(f"no table header in {zip_path}")
    header = [c.strip() for c in lines[start].split(",")[1:]]
    rows = []
    for line in lines[start + 1:]:
        cells = [c.strip() for c in line.split(",")]
        if not re.fullmatch(r"\d{6}", cells[0]):
            break                                            # the blank line that ends the first table
        rows.append(cells)
    table = pd.DataFrame([[float(c) for c in r[1:]] for r in rows], columns=header,
                         index=_month_end([f"{r[0][:4]}-{r[0][4:]}" for r in rows]))
    missing = [c for c in columns if c not in table.columns]
    if missing:
        raise KeyError(f"{missing} not in the table of {Path(zip_path).name}: {list(table.columns)}")
    return _mask(table[list(columns)]) / 100.0


def read_french_country(zip_path, country="Canada"):
    """One country's value-weight market return in LOCAL currency ("Local Returns, All 4 Data Items Not Reqd"
    block, column Mkt) from the Fama/French international zip, as fractions; -99.99 is NaN."""
    lines = _read_zip(zip_path, f"{country}.Dat").decode("latin-1").splitlines()
    title = next((i for i, line in enumerate(lines) if "Local" in line and "Not Reqd" in line), None)
    head = None if title is None else next((i for i in range(title, len(lines)) if "Mkt" in lines[i].split()), None)
    if head is None:
        raise ValueError(f"no local-currency Mkt block in {country}.Dat of {zip_path}")
    col = lines[head].split().index("Mkt") + 1               # the date is the first field of a row
    rows = []
    for line in lines[head + 1:]:
        cells = line.split()
        if not (cells and re.fullmatch(r"\d{6}", cells[0])):
            break
        rows.append((cells[0], float(cells[col])))
    series = pd.Series([v for _, v in rows], index=_month_end([f"{d[:4]}-{d[4:]}" for d, _ in rows]),
                       name=country, dtype="float64")
    return _mask(series) / 100.0


def read_statcan(zip_path, vectors):
    """Monthly values (percent or index points, as published) of the `vectors` asked for from a Statistics
    Canada table zip: one column per vector in the order asked, every month from the first to the last.

    A vector the file lacks, a blank value and the table's placeholder -99.999 are NaN (never filled).
    """
    table = pd.read_csv(io.BytesIO(_read_zip(zip_path)), dtype=str, encoding="utf-8-sig",
                        usecols=["REF_DATE", "VECTOR", "VALUE"])
    table = table[table["VECTOR"].isin(list(vectors))]
    wide = table.assign(VALUE=pd.to_numeric(table["VALUE"], errors="coerce")).pivot(
        index="REF_DATE", columns="VECTOR", values="VALUE")      # a duplicated (month, vector) raises: loud
    wide.index = _month_end(wide.index)
    return _complete(_mask(wide.reindex(columns=list(vectors))))


def read_fred(csv_path):
    """A FRED download (observation date, value) as a float Series sorted by date; "." and blank values dropped."""
    raw = pd.read_csv(csv_path, na_values=["."])
    series = pd.Series(raw.iloc[:, 1].to_numpy(dtype="float64"), index=pd.to_datetime(raw.iloc[:, 0]), name=raw.columns[1])
    return series.dropna().sort_index()


# --- the panel -----------------------------------------------------------------------------------------
def build_panel(raw_dir):
    """The monthly proxy panel from the raw downloads (layout written by scripts/fetch_deep.py).

    Index: month-end Timestamps named `month`, the union of the sources' months (rows before DEEP_START are
    kept and never used). Columns: PROXY_IDS + USDCAD_END (the month-end USD/CAD level). Values: monthly
    total returns in CAD, as fractions; NaN where a source has no value. Raises KeyError when a source file
    lacks a column it must have, ValueError when a proxy ends up with no value at all (a changed layout).
    """
    raw = Path(raw_dir)
    ff = read_french_monthly(raw / "french_factors/F-F_Research_Data_Factors_CSV.zip", ["Mkt-RF", "RF"])
    i12 = read_french_monthly(raw / "french_12/12_Industry_Portfolios_CSV.zip", ["BusEq"])
    i49 = read_french_monthly(raw / "french_49/49_Industry_Portfolios_CSV.zip", list(_INDUSTRY_49.values()))
    usd = pd.DataFrame({"US_MKT": ff["Mkt-RF"] + ff["RF"], "BUSEQ": i12["BusEq"],
                        **{k: i49[v] for k, v in _INDUSTRY_49.items()}})
    daily = read_fred(raw / "fred_DEXCAUS/DEXCAUS.csv")
    fx_end = daily.groupby(daily.index.to_period("M")).last()          # last quote of each month
    fx_end.index = _month_end(fx_end.index)
    fx_avg = read_fred(raw / "fred_EXCAUS/EXCAUS.csv")
    fx_avg.index = _month_end(fx_avg.index.to_period("M"))             # monthly averages, dated the 1st
    in_cad = (1 + usd).mul(1 + _growth(fx_end).reindex(usd.index), axis=0) - 1      # a US line seen from Canada

    tsx = read_statcan(raw / "statcan_10100125/10100125-eng.zip", ["v122620", "v122628"])
    early = tsx["v122620"] / tsx["v122620"].shift(1) - 1 + tsx["v122628"].shift(1) / 100 / 12
    french = read_french_country(raw / "french_countries/F-F_International_Countries.zip")
    ca_eq = pd.concat([early[early.index < _CANADA_FROM], french[french.index >= _CANADA_FROM]])

    yields = read_statcan(raw / "statcan_10100122/10100122-eng.zip", [*LADDER, "v122531", "v122541"])
    # the ladder is NaN as soon as one leg is (a Series sum, never a skip-NaN row sum that would re-weight it)
    bond = sum(par_bond_return(yields[v], years) * weight for v, (years, weight) in LADDER.items())
    # a bill earns last month's yield / 12; the auction series fills the months the bill series lacks
    bill = yields["v122531"].combine_first(yields["v122541"]).shift(1) / 100 / 12

    gold = pd.read_csv(raw / "worldbank_gold/gold_monthly.csv")
    usd_oz = pd.Series(gold["gold_usd_oz"].to_numpy(dtype="float64"), index=_month_end(gold["month"]))
    gold_cad = (1 + _growth(usd_oz)) * (1 + _growth(fx_avg).reindex(usd_oz.index)) - 1

    panel = pd.concat({"CA_EQ": ca_eq, "CAD_BOND": bond, "CAD_TBILL": bill, "GOLD": gold_cad,
                       **{c: in_cad[c] for c in in_cad.columns}}, axis=1).sort_index()
    panel["USDCAD_END"] = fx_end.reindex(panel.index)
    panel = panel[[*PROXY_IDS, "USDCAD_END"]]
    panel.index.name = "month"
    empty = [c for c in PROXY_IDS if panel[c].notna().sum() == 0]
    if empty:
        raise ValueError(f"no data at all for {empty}: the raw files in {raw} do not have the expected layout")
    return panel


# --- loaders (the cache may be absent; the two catalogues are tracked files) --------------------------------
def load_panel(*, path=None):
    """The cached panel (data/cache/deep/panel.csv: `month` "YYYY-MM" + the columns of build_panel) with a
    month-end index named `month`, or None when the file is absent (the app works without deep history)."""
    p = Path(path) if path else PANEL_PATH
    if not p.exists():
        return None
    panel = pd.read_csv(p)
    panel.index = _month_end(panel.pop("month"))
    panel.index.name = "month"
    return panel


def load_episodes(*, path=None):
    """The rows of data/deep_episodes.csv as dicts of text, except `lat`/`lon` (floats) and an empty `family` (None)."""
    with open(path or EPISODES_PATH, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row["lat"], row["lon"], row["family"] = float(row["lat"]), float(row["lon"]), row["family"] or None
    return rows


def load_proxy_map(*, path=None):
    """{ticker: {"proxy": id or None, "label", "note"}} from data/deep_proxies.csv; an empty proxy cell is None
    (no stand-in: the replay says "Can't say" for any mix holding that ticker)."""
    with open(path or PROXIES_PATH, encoding="utf-8-sig", newline="") as f:
        return {r["ticker"]: {"proxy": (r["proxy"] or "").strip() or None, "label": r["label"] or "", "note": r["note"] or ""}
                for r in csv.DictReader(f)}


# === part (b): the replay, the proxy check, the Result fragment (plan A Task 16) ===========================
# Deep history is a disclosure (an assumption, kind "assumption"): nothing here enters `checks`, the verdict,
# `turbulence` or any 2021-26 number, and nothing says buy / sell / hold / "you should" (red gate 1). Every number
# is computed here; the sentence is written by `deep_sentence`; counts read "3 of 11", never a frequency.
MINUS = "−"                  # the sign every displayed negative number uses (U+2212)
_DUST = 1e-12                     # a weight this small is a line at 0 (as in tools.portfolio)
NOT_RECORDED = "not recorded"     # the manifest's retrieved_at when no download time is known (scripts/fetch_deep.py)
_NO_REPLAY = ("depth", "peak", "trough", "peak_value", "trough_value", "loss_dollars", "recovery_months", "beyond_floor")


def _round_pp(x):
    """A fraction as percent, ROUND_HALF_UP to 0.1 pp, through repr so float noise cannot tip a limit (pitfall 5):
    -0.1500004 -> Decimal('-15.0'). The same rule as governance.round_pp, kept here because tools never import it."""
    return (Decimal(repr(float(x))) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _iso(day):
    return pd.Timestamp(day).strftime("%Y-%m-%d")


def _lines(weights):
    """The held lines: tickers stripped and upper-cased, a line at 0 is not held (it cannot make a replay 'Can't say')."""
    out = {}
    for ticker, weight in (weights or {}).items():
        if float(weight) > _DUST:
            key = str(ticker).strip().upper()
            out[key] = out.get(key, 0.0) + float(weight)
    return out


def _end_of(month):
    """The month-end Timestamp of a "YYYY-MM" string."""
    return _month_end([month])[0]


def proxy_levels(tickers, start, end, *, panel=None, proxy_map=None):
    """Proxy levels, one column per ticker, base 1.0 at the month-end before `start` ("YYYY-MM"), through `end`.

    A ticker without a proxy, or with no panel at all, is NaN everywhere. After the first month the panel lacks (or
    holds as NaN) a ticker is NaN as well: a level is never carried across an unknown month (no zero-fill).
    """
    panel = load_panel() if panel is None else panel
    pmap = load_proxy_map() if proxy_map is None else proxy_map
    first = pd.Period(start, "M") - 1
    months = _month_end(pd.period_range(first, pd.Period(end, "M"), freq="M"))
    out = {}
    for t in tickers:
        col = (pmap.get(t) or {}).get("proxy")
        if panel is None or col is None or col not in panel.columns or len(months) == 0:
            out[t] = pd.Series(np.nan, index=months, dtype="float64")
            continue
        grown = (1.0 + panel[col].reindex(months[1:])).cumprod(skipna=False)
        out[t] = pd.concat([pd.Series([1.0], index=months[:1]), grown])
    return pd.DataFrame(out, index=months, columns=list(tickers))


def _money(amount, depth):
    """Dollars the fall would have cost: amount x drawdown, whole dollars, ROUND_HALF_UP (ledger 30: one definition
    everywhere, so a path that grew before its peak still reads amount x depth). Fictional money, never a forecast."""
    cost = Decimal(repr(float(amount))) * Decimal(repr(float(-depth)))
    return int(cost.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def episode_replay(weights, episode, as_of=DATASET_END, *, amount, floor, panel=None, proxy_map=None):
    """One mix through one earlier crisis by proxy: the worst peak-to-trough fall inside the window, monthly, CAD.

    Coverage is checked BEFORE any series is built: a held line with no proxy, or with a month missing between the
    base (the month-end before `start`) and `end`, makes the episode `replayable: False` and names the line in
    `uncovered` (series_from_market would read a missing price as a 0 % return: never let it). The panel is cut at
    min(`as_of`, DEEP_END) first, so no month after either reaches the maths (red gate 3); a window not yet over
    at that date is therefore not replayable, and `recovery_months` is None until the peak is regained by then.
    `depth` is a fraction <= 0; `peak`/`trough` are "YYYY-MM" (the peak may be the base month); values are base 100
    at the base month; `loss_dollars` = amount x depth (ledger 30); `beyond_floor` compares both to 0.1 pp.
    """
    panel = load_panel() if panel is None else panel
    pmap = load_proxy_map() if proxy_map is None else proxy_map
    held = _lines(weights)
    cut = min(pd.Timestamp(as_of), _end_of(DEEP_END))
    if panel is not None:
        panel = panel.loc[:cut]
    end = _end_of(episode["end"])
    levels = proxy_levels(list(held), episode["start"], max(episode["end"], cut.strftime("%Y-%m")),
                          panel=panel, proxy_map=pmap)
    window = levels.loc[:end]
    uncovered = [t for t in held if window[t].isna().any()]
    out = {"episode_id": episode["episode_id"], "replayable": not uncovered, "uncovered": uncovered,
           **dict.fromkeys(_NO_REPLAY), "source": SOURCE, "as_of": _iso(as_of)}
    if uncovered:
        return out
    path = series_from_market(held, make_market(levels.loc[:cut].dropna()))   # a hole ends the usable months
    fall = path.loc[:end]
    drawdown = fall / fall.cummax() - 1.0
    trough = drawdown.idxmin()
    peak = fall.loc[:trough].idxmax()
    depth = float(drawdown.min())
    regained = path.loc[trough:]
    regained = regained[regained >= fall[peak]]
    out.update(depth=depth, peak=peak.strftime("%Y-%m"), trough=trough.strftime("%Y-%m"),
               peak_value=float(fall[peak]), trough_value=float(fall[trough]), loss_dollars=_money(amount, depth),
               recovery_months=(regained.index[0].to_period("M") - trough.to_period("M")).n if len(regained) else None,
               beyond_floor=bool(_round_pp(depth) < _round_pp(floor)))
    return out


def _worst_fall(returns):
    """Worst peak-to-trough fall (a fraction <= 0) of a mix compounded from monthly returns, from a base of 1.0."""
    level = np.concatenate([[1.0], np.cumprod(1.0 + np.asarray(returns, dtype="float64"))])
    return float((level / np.maximum.accumulate(level) - 1.0).min())


def proxy_check(weights, as_of, *, market=None, panel=None, proxy_map=None):
    """The honesty badge: the same weights on real prices vs on proxies, month by month since OVERLAP_START.

    Months run from 2021-12 to the last FULL month <= `as_of`, and no later than the last month every held
    proxy has (Canada ends 2025-12 today); the real side is the month-end CAD price of the starter data
    (`market`, cut at `as_of`), both sides rebalanced to the weights every month. `strong` iff n >= 24 and corr >=
    0.95 and annualised tracking error <= 5 % and |worst-fall gap| <= 3 pp, else `weak` (`direction` "gentler"
    when the proxy fell less than the real mix, "harsher" when more); fewer than 24 months, a hole in either
    side (the window stops before it), or a line without a proxy is "can't say" (never a guess).
    """
    panel = load_panel() if panel is None else panel
    pmap = load_proxy_map() if proxy_map is None else proxy_map
    held = _lines(weights)
    out = {"strength": "can't say", "direction": None, "n_months": 0, "window": None, "corr": None, "te_ann": None,
           "drawdown_real": None, "drawdown_proxy": None, "drawdown_gap": None, "uncovered": [], "source": SOURCE,
           "as_of": _iso(as_of)}
    cols = {t: (pmap.get(t) or {}).get("proxy") for t in held}
    out["uncovered"] = [t for t, c in cols.items() if c is None or panel is None or c not in panel.columns]
    if out["uncovered"]:
        return out
    market = load_market(as_of) if market is None else market
    asof = pd.Timestamp(as_of)
    unknown = [t for t in held if t not in market["prices"].columns]
    if unknown:                                              # as series_from_market: not a coverage gap, a bad input
        raise ValueError(f"Unknown ticker: {unknown[0]}")
    prices = market["prices"].loc[:asof, list(held)]                       # nothing after as_of (red gate 3)
    monthly = prices.groupby(prices.index.to_period("M")).last()          # the last price of each calendar month
    real = monthly.pct_change(fill_method=None)
    proxy = pd.DataFrame({t: panel[c].to_numpy() for t, c in cols.items()}, index=panel.index.to_period("M"))
    weight = pd.Series(held)
    mix = {"real": (real * weight).sum(axis=1, min_count=len(held)),
           "proxy": (proxy * weight).sum(axis=1, min_count=len(held))}
    is_full = asof.normalize() == asof.to_period("M").to_timestamp(how="end").normalize()
    ends = [asof.to_period("M") if is_full else asof.to_period("M") - 1]
    ends += [panel[c].last_valid_index().to_period("M") for c in set(cols.values()) if panel[c].last_valid_index() is not None]
    both = pd.DataFrame(mix).reindex(pd.period_range(OVERLAP_START, min(ends), freq="M"))   # an absent month is NaN
    good = both.notna().all(axis=1).to_numpy()
    both = both.iloc[: len(good) if good.all() else int(good.argmin())]     # stop before the first hole
    out["n_months"] = len(both)
    if len(both):
        out["window"] = {"start": str(both.index[0]), "end": str(both.index[-1])}
    if len(both) < STRONG["min_months"]:
        return out
    r, p = both["real"].to_numpy(dtype="float64"), both["proxy"].to_numpy(dtype="float64")
    if not (r.std() > 0 and p.std() > 0):
        return out                                           # a flat side has no correlation: nothing to conclude
    corr, te = float(np.corrcoef(r, p)[0, 1]), float(np.std(p - r, ddof=1) * np.sqrt(12))
    real_fall, proxy_fall = _worst_fall(r), _worst_fall(p)
    gap = proxy_fall - real_fall                             # > 0: the proxy fell less than the real mix
    strong = (corr >= STRONG["corr"] and te <= STRONG["te_ann"] and abs(gap) <= STRONG["drawdown_gap"])
    out.update(strength="strong" if strong else "weak", corr=corr, te_ann=te, drawdown_real=real_fall,
               drawdown_proxy=proxy_fall, drawdown_gap=gap,
               direction=None if strong or gap == 0 else ("gentler" if gap > 0 else "harsher"))
    return out


# --- the Result fragment ------------------------------------------------------------------------------------
def _summary(episodes, side):
    """Counts for one side ("today" or "after") over the replayable episodes: how many fell beyond the floor, and
    the deepest one with its dollars. The "after" side is None when there was no move (nothing was replayed)."""
    if side == "after" and all(e.get(side) is None for e in episodes):
        return None
    ok = [(e["episode_id"], e[side]) for e in episodes if e[side] and e[side]["replayable"]]
    worst = min(ok, key=lambda pair: pair[1]["depth"], default=None)
    return {"breaches": sum(1 for _, r in ok if r["beyond_floor"]), "replayable": len(ok),
            "worst_episode": worst[0] if worst else None, "worst_depth": worst[1]["depth"] if worst else None,
            "worst_loss_dollars": worst[1]["loss_dollars"] if worst else None}


def _pct(x, whole=False):
    """A fraction as percent to 0.1 pp (the rounding that decides the floor), U+2212 for the minus, a space before
    the sign; `whole` drops a trailing .0 (a floor of -15 %). A drop that rounds to zero is "0.0 %", never "−0.0 %"."""
    shown = _round_pp(x)
    text = f"{abs(shown):.1f}"
    if whole and text.endswith(".0"):
        text = text[:-2]
    return f"{MINUS}{text} %" if shown < 0 else f"{text} %"


def _cant_say(fragment, side):
    """Why a side has no replayable crisis, naming the lines (never a guess)."""
    named = list(((fragment.get("proxy") or {}).get(side) or {}).get("uncovered") or [])
    if named:
        return f"no proxy for {', '.join(named)}"
    lines = sorted({t for e in fragment["episodes"] for t in ((e.get(side) or {}).get("uncovered") or [])})
    return f"no proxy data for {', '.join(lines)} in these crises" if lines else "no crisis could be replayed"


def deep_sentence(fragment, floor):
    """The code-written row sentence: marked ◐, says "proxies, monthly", counts "k of n" (never a rate), the worst
    episode with its percent and dollars, then the badge clause. Pure; no data access. Never advice."""
    summary, proxy = fragment["summary"], fragment.get("proxy") or {}
    titles, total = {e["episode_id"]: e["title"] for e in fragment["episodes"]}, len(fragment["episodes"])

    def worst(s):
        return f"worst: {titles[s['worst_episode']]}, {_pct(s['worst_depth'])}, ${s['worst_loss_dollars']:,}"

    def missed(s):
        return f" {total - s['replayable']} of {total} could not be replayed." if s["replayable"] < total else ""

    text = "◐ Older history (proxies, monthly; not used in the verdict): "
    today = summary["today"]
    if today["replayable"]:
        text += (f"your mix today fell beyond your floor of {_pct(floor, whole=True)} in {today['breaches']} of "
                 f"{today['replayable']} earlier crises ({worst(today)}).{missed(today)}")
    else:
        text += f"your mix today: can't say ({_cant_say(fragment, 'today')})."
    after = summary.get("after")
    if after is not None:
        if after["replayable"]:
            text += f" The move: {after['breaches']} of {after['replayable']} ({worst(after)}).{missed(after)}"
        else:
            text += f" The move: can't say ({_cant_say(fragment, 'after')})."
    for side, who in (("today", "your mix today"), ("after", "the move")):
        check = proxy.get(side)
        if check is None or summary.get(side) is None or not summary[side]["replayable"]:
            continue
        if check["strength"] == "weak":
            case = f"the {check['direction']} case" if check["direction"] else "rough"
            text += f" Proxy weak for {who}: read the older episodes as {case}."
        elif check["strength"] == "can't say":
            why = (f"only {check['n_months']} months to compare" if check["n_months"] < STRONG["min_months"]
                   else "no variation to compare")
            text += f" Proxy check for {who}: can't say ({why})."
    return text


def rejudge(fragment, floor):
    """The same fragment judged against another floor, from the stored depths only (no data access): every
    `beyond_floor`, the `summary` and the `sentence` are recomputed; nothing else changes. None stays None."""
    if fragment is None:
        return None
    out = copy.deepcopy(fragment)
    for episode in out["episodes"]:
        for side in ("today", "after"):
            record = episode.get(side)
            if record and record["replayable"]:
                record["beyond_floor"] = bool(_round_pp(record["depth"]) < _round_pp(floor))
    out["summary"] = {side: _summary(out["episodes"], side) for side in ("today", "after")}
    out["sentence"] = deep_sentence(out, floor)
    return out


def _retrieved_at():
    """When the raw files were downloaded, as the manifest wrote it. "not recorded" (what scripts/fetch_deep.py writes
    when it does not know), an absent or unreadable manifest and a non-text value all read "not recorded": a source
    line prints this as is, never "None"."""
    try:
        value = json.loads(Path(MANIFEST_PATH).read_text(encoding="utf-8")).get("retrieved_at")
    except (OSError, ValueError, AttributeError):
        value = None
    return value.strip() if isinstance(value, str) and value.strip() else NOT_RECORDED


def deep_history(weights_today, weights_after, as_of, *, amount, floor, market=None, panel=None, episodes=None,
                 proxy_map=None):
    """The `deep_history` Result fragment (ledger 17): both mixes through the 11 earlier crises, the proxy check, the
    counts and the code-written sentence. None when the panel cache is absent (the app works without it).

    A disclosure only: it is never an input of `checks`, the verdict, `kpis`, `turbulence` or `scenario_stress`.
    `weights_after` may be None (no move): the `after` sides are then None. `amount` and `floor` are the run's.
    """
    panel = load_panel() if panel is None else panel
    if panel is None:
        return None
    pmap = load_proxy_map() if proxy_map is None else proxy_map
    after = _lines(weights_after) or None
    rows = []
    for e in (load_episodes() if episodes is None else episodes):
        rows.append({"episode_id": e["episode_id"], "title": e["title_en"], "start": e["start"], "end": e["end"],
                     "kind": e["kind"], "family": e["family"], "place": e["place"], "lat": e["lat"], "lon": e["lon"],
                     "source_url": e["source_url"],
                     "today": episode_replay(weights_today, e, as_of, amount=amount, floor=floor, panel=panel, proxy_map=pmap),
                     "after": None if after is None else
                     episode_replay(after, e, as_of, amount=amount, floor=floor, panel=panel, proxy_map=pmap)})
    fragment = {"frequency": "monthly", "window": {"start": DEEP_START, "end": DEEP_END},
                "proxy": {"today": proxy_check(weights_today, as_of, market=market, panel=panel, proxy_map=pmap),
                          "after": None if after is None else
                          proxy_check(after, as_of, market=market, panel=panel, proxy_map=pmap)},
                "episodes": rows, "summary": {side: _summary(rows, side) for side in ("today", "after")},
                "sentence": "",
                "source": (f"{SOURCE}. Data retrieved: {_retrieved_at()}. "
                           "This already happened to markets like these; it is not a forecast."),
                "as_of": _iso(as_of)}
    fragment["sentence"] = deep_sentence(fragment, floor)
    return fragment
