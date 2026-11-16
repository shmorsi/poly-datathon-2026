"""Universe, CAD prices and the market bundle (spec section 9; plan A Task 2).

Every other tool reads market data through this module. The processing, in this order:
  1. read the starter CSVs once per data_dir (cached) and apply the CNQ.TO fix (pitfall 1);
  2. drop every row dated after `as_of` BEFORE any pivot, fill or FX join (red gate 3: a test
     scrambles every later row and must see identical prices);
  3. calendar = the union of TSX and US trading days (crypto rows never add a day);
  4. `traded` = the asset has a real row that day; prices are forward-filled at most 3 days, the
     dates still missing after that are listed in `flags` and their values stay NaN;
  5. USD/CAD is carried forward to the calendar; USD lines x usdcad -> CAD. It is NEVER
     back-filled: a day before the first rate has a price but no rate, so its CAD price stays NaN
     and the date is flagged (no look-ahead, red gate 3; ledger 14);
  6. `close_cad` is the unadjusted `close` column through steps 3-5 (no CNQ factor: pitfall 1 is
     about adj_close only). `dividends` are the `dividend` rows of corporate_actions.csv (optional:
     no file, no dividends) dated <= as_of, cut BEFORE the conversion; USD amounts x the rate in
     force on the ex-date (the last one known on or before it, never a later one).

The market bundle is shared between callers (it is cached): never mutate its frames.
Starter data is an untrusted download (pitfall 13): it is read with pandas only.
"""
from __future__ import annotations

import functools
import os
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("EPICENTRE_DATA_DIR") or ROOT / "data" / "starter")
DATASET_END = "2026-11-12"

UNIVERSE_COLUMNS = ["ticker", "name", "asset_class", "market", "currency", "sector", "country"]
POLICY_RATE_ID = "V39079"                  # Bank of Canada target for the overnight rate
MAX_FILL_DAYS = 3                          # spec 9: forward-fill at most 3 days, else flag
CNQ_TICKER, CNQ_FIX_BEFORE, CNQ_FIX_FACTOR = "CNQ.TO", "2022-08-22", 1.021   # pitfall 1
US_MARKETS = frozenset({"NASDAQ", "NYSE", "NYSE Arca", "Cboe BZX"})
SOURCE = ("Yahoo Finance adjusted closes (AlphaForge starter pack, retrieved 2026-11-13); USD "
          "lines converted to CAD with the Bank of Canada USD/CAD rate carried forward; CNQ.TO "
          "corrected for the 2022-08-22 special distribution")
_FILES = ("assets_universe.csv", "prices_daily.csv", "fx_usdcad_daily.csv", "macro_rates.csv")
_OPTIONAL_FILES = ("corporate_actions.csv",)       # dividends; a pack without it (data/fake/starter) has none


# --- small helpers -------------------------------------------------------------------------------
def _iso(day) -> str:
    return pd.Timestamp(day).strftime("%Y-%m-%d")


def _country(ticker: str, asset_class: str, market: str) -> str:
    """Listing country (spec 9): TSX -> CAN; NASDAQ/NYSE/NYSE Arca/Cboe -> USA; crypto -> CRYPTO.

    GLD stays USA here (its listing); the exposure tools put gold in GLOBAL (plan A Tasks 6-7).
    """
    if asset_class == "crypto" or ticker.endswith("-USD"):
        return "CRYPTO"
    if market == "TSX" or ticker.endswith(".TO"):
        return "CAN"
    return "USA" if market in US_MARKETS else "UNKNOWN"


def _infer_universe(tickers) -> pd.DataFrame:
    """Universe rows for in-memory frames: .TO -> TSX, -USD -> crypto, else NASDAQ/USD (spec 9)."""
    rows = []
    for t in tickers:
        if t.endswith(".TO"):
            rows.append((t, t, "equity", "TSX", "CAD", "Unknown", "CAN"))
        elif t.endswith("-USD"):
            rows.append((t, t, "crypto", "Crypto (24/7)", "USD", "Unknown", "CRYPTO"))
        else:
            rows.append((t, t, "equity", "NASDAQ", "USD", "Unknown", "USA"))
    return pd.DataFrame(rows, columns=UNIVERSE_COLUMNS)


def _flags(prices: pd.DataFrame, local: pd.DataFrame | None = None) -> dict:
    """{ticker: [ISO dates still missing after the asset's first valid price]}.

    A leading gap (before the first price) is not a gap, it is "no history yet". With `local`
    (the listing-currency prices) a day that HAS a local price but no CAD price is flagged too,
    even at the start: it is a USD price with no USD/CAD rate yet (never filled, ledger 14).
    """
    seen = prices.notna().astype(int).cummax().astype(bool)
    gap = prices.isna() & seen
    if local is not None:
        gap = gap | (prices.isna() & local.notna())
    return {t: prices.index[gap[t].to_numpy()].strftime("%Y-%m-%d").tolist()
            for t in prices.columns}


def _carry(usdcad: pd.Series, index: pd.Index) -> pd.Series:
    """USD/CAD on `index`: the last known rate (holidays, weekends, blank rows). Days before the
    first rate stay NaN: they are never back-filled with a later rate, because a past day's value
    would then depend on how far as_of extends (look-ahead, red gate 3; ledger 14). Blank rows are
    dropped first for the same reason: a blank carries the last known rate, not a later one."""
    return usdcad.dropna().sort_index().reindex(index, method="ffill").rename("usdcad")


def _to_cad(frame: pd.DataFrame, fx: pd.Series, currency: dict) -> pd.DataFrame:
    """USD columns x usdcad (aligned to frame.index); CAD columns are returned unchanged."""
    out = frame.copy()
    usd = [t for t in frame.columns if currency.get(t) == "USD"]
    if usd:
        out[usd] = frame[usd].mul(fx, axis=0)
    return out


def _bundle(*, calendar, prices, local, traded, fx, crypto_daily, rf_daily, universe, flags,
            as_of, dividends, close_cad) -> dict:
    """The market bundle, built in one place: later tasks add keys here."""
    return {"calendar": calendar, "prices": prices, "local": local, "traded": traded, "fx": fx,
            "crypto_daily": crypto_daily, "rf_daily": rf_daily, "universe": universe,
            "flags": flags, "as_of": as_of, "dividends": dividends, "close_cad": close_cad}


def _dividend_rows(frame: pd.DataFrame, date_col: str, amount_col: str, known) -> pd.DataFrame:
    """date, ticker, amount (per share, listing currency) of the payouts worth keeping.

    Rows of tickers outside `known`, blank (NaN), zero or negative amounts, and exact duplicate rows
    are dropped: the file is an untrusted download and a doubled row would inflate a yield.
    """
    rows = pd.DataFrame({"date": pd.to_datetime(frame[date_col]), "ticker": frame["ticker"],
                         "amount": pd.to_numeric(frame[amount_col], errors="coerce")})
    rows = rows[rows["ticker"].isin(set(known)) & (rows["amount"] > 0)]
    return rows.drop_duplicates().reset_index(drop=True)


def _dividends_cad(rows: pd.DataFrame, fx: pd.Series, currency: dict) -> pd.DataFrame:
    """date, ticker, amount_cad: USD amounts x the rate in force on the ex-date (the last rate known
    on or before it, so a Saturday uses Friday's), CAD amounts as they are. A USD dividend dated
    before the first rate has no CAD value and is left out: it is never converted with a later
    rate (red gate 3; ledger 14). Sorted by date, then ticker.
    """
    usd = rows["ticker"].map(currency).eq("USD").to_numpy()
    rate = np.where(usd, fx.asof(pd.DatetimeIndex(rows["date"])).to_numpy(float), 1.0)
    out = rows.assign(amount_cad=rows["amount"] * rate).drop(columns="amount")
    return out[out["amount_cad"].notna()].sort_values(["date", "ticker"]).reset_index(drop=True)


# --- reading the starter files (once per data_dir) -----------------------------------------------
def _resolve(data_dir) -> Path:
    return Path(DATA_DIR if data_dir is None else data_dir).expanduser().resolve()


def _signature(path: Path) -> tuple:
    """(name, mtime, size) of the starter files: the cache key changes if a file is rewritten, or if
    the optional corporate_actions.csv appears or disappears (then it is (name, None, None))."""
    sig = []
    for name in _FILES:
        try:
            st = (path / name).stat()
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Starter data not found: {path / name}. Copy the organizers' alphaforge_starter "
                "folder to data/starter/ (see the README).") from None
        sig.append((name, st.st_mtime_ns, st.st_size))
    for name in _OPTIONAL_FILES:
        try:
            st = (path / name).stat()
            sig.append((name, st.st_mtime_ns, st.st_size))
        except FileNotFoundError:
            sig.append((name, None, None))
    return tuple(sig)


@functools.lru_cache(maxsize=4)
def _raw(dir_str: str, signature: tuple) -> dict:
    """The starter CSVs, read once: universe (+ country), adj_close (CNQ fixed) and close, usdcad,
    rate, and the dividend rows of the optional corporate_actions.csv (listing currency)."""
    d = Path(dir_str)
    uni = pd.read_csv(d / "assets_universe.csv")
    uni["country"] = [_country(t, c, m) for t, c, m in zip(uni["ticker"], uni["asset_class"],
                                                           uni["market"])]
    uni = uni[UNIVERSE_COLUMNS].reset_index(drop=True)
    odd = sorted(set(uni["currency"]) - {"CAD", "USD"})
    if odd:
        raise ValueError(f"Unsupported listing currency in the universe file: {', '.join(odd)}")

    px = pd.read_csv(d / "prices_daily.csv", usecols=["date", "ticker", "adj_close", "close"],
                     dtype={"date": str})
    px = px[px["ticker"].isin(set(uni["ticker"]))].drop_duplicates(["date", "ticker"], keep="last")
    px["date"] = pd.to_datetime(px["date"])
    cnq = (px["ticker"] == CNQ_TICKER) & (px["date"] < pd.Timestamp(CNQ_FIX_BEFORE))
    px.loc[cnq, "adj_close"] *= CNQ_FIX_FACTOR            # a constant: it cannot look ahead; `close` is untouched
    px = px.reset_index(drop=True)

    fx = pd.read_csv(d / "fx_usdcad_daily.csv", usecols=["date", "usdcad"], dtype={"date": str})
    fx = fx.drop_duplicates("date", keep="last")
    usdcad = pd.Series(fx["usdcad"].to_numpy(float), index=pd.to_datetime(fx["date"]),
                       name="usdcad").sort_index().rename_axis("date")

    macro = pd.read_csv(d / "macro_rates.csv", usecols=["date", "series_id", "value"],
                        dtype={"date": str})
    rate = macro[macro["series_id"] == POLICY_RATE_ID].drop_duplicates("date", keep="last")
    rf = pd.Series(rate["value"].to_numpy(float) / 100.0, index=pd.to_datetime(rate["date"]),
                   name="rf_daily").sort_index().rename_axis("date")
    actions = d / "corporate_actions.csv"
    ca = (pd.read_csv(actions, usecols=["ex_date", "ticker", "action", "value"], dtype={"ex_date": str})
          if actions.exists() else pd.DataFrame({"ex_date": [], "ticker": [], "action": [], "value": []}))
    dividends = _dividend_rows(ca[ca["action"] == "dividend"], "ex_date", "value", uni["ticker"])
    return {"universe": uni, "prices": px, "usdcad": usdcad, "rf": rf, "dividends": dividends}


def _raw_for(data_dir) -> dict:
    path = _resolve(data_dir)
    return _raw(str(path), _signature(path))


# --- the market bundle ---------------------------------------------------------------------------
@functools.lru_cache(maxsize=16)
def _market(as_of: str, dir_str: str, signature: tuple) -> dict:
    raw = _raw(dir_str, signature)
    cutoff = pd.Timestamp(as_of)
    uni = raw["universe"]
    tickers = uni["ticker"].tolist()
    currency = dict(zip(uni["ticker"], uni["currency"]))
    crypto = [t for t, c in zip(uni["ticker"], uni["asset_class"]) if c == "crypto"]

    px = raw["prices"]
    px = px[px["date"] <= cutoff]                          # before any pivot, fill or FX join
    usdcad = raw["usdcad"][raw["usdcad"].index <= cutoff]
    rf_daily = raw["rf"][raw["rf"].index <= cutoff]
    dividends = raw["dividends"][raw["dividends"]["date"] <= cutoff]     # cut BEFORE the conversion

    calendar = pd.DatetimeIndex(px.loc[~px["ticker"].isin(crypto), "date"].unique())
    calendar = calendar.sort_values().rename("date")
    wide = px.pivot(index="date", columns="ticker", values="adj_close").reindex(columns=tickers)
    on_calendar = wide.reindex(calendar)                   # crypto: the row dated D for day D
    traded = on_calendar.notna()                           # a real row that day, before filling
    local = on_calendar.ffill(limit=MAX_FILL_DAYS)         # listing currency, NaN where flagged
    fx = _carry(usdcad, calendar)
    prices = _to_cad(local, fx, currency)
    close = px.pivot(index="date", columns="ticker", values="close").reindex(columns=tickers)
    close_cad = _to_cad(close.reindex(calendar).ffill(limit=MAX_FILL_DAYS), fx, currency)

    if crypto:                                             # every UTC day, for event baselines
        cpx = wide.loc[:, crypto].dropna(how="all")
        crypto_daily = _to_cad(cpx, _carry(usdcad, cpx.index), currency)
    else:
        crypto_daily = pd.DataFrame(index=calendar)
    return _bundle(calendar=calendar, prices=prices, local=local, traded=traded, fx=fx,
                   crypto_daily=crypto_daily, rf_daily=rf_daily, universe=uni,
                   flags=_flags(prices, local), as_of=as_of,
                   dividends=_dividends_cad(dividends, fx, currency), close_cad=close_cad)


def load_universe(*, data_dir=None) -> pd.DataFrame:
    """The 31 assets: ticker, name, asset_class, market, currency, sector, country."""
    return _raw_for(data_dir)["universe"].copy()


def load_market(as_of: str, *, data_dir=None) -> dict:
    """The market bundle with everything dated <= as_of (spec 9). Cached per (as_of, data_dir).

    Keys: calendar, prices (CAD), local (listing currency), traded (a real row that day), fx
    (usdcad on the calendar; NaN before the first rate), crypto_daily (CAD, every UTC day),
    rf_daily (policy rate as a fraction), universe, flags ({ticker: [ISO dates missing for more
    than 3 days, or a USD price with no rate yet]}), as_of, dividends (date, ticker, amount_cad:
    the dividend rows dated <= as_of, CAD per share), close_cad (the unadjusted close on the same
    calendar and fill as `prices`).
    The frames are shared with the cache: callers must not mutate them.
    """
    path = _resolve(data_dir)
    bundle = _market(_iso(as_of), str(path), _signature(path))
    return {**bundle, "flags": {t: list(v) for t, v in bundle["flags"].items()}}


def make_market(prices, *, local=None, fx=None, traded=None, universe=None, crypto_daily=None,
                rf=0.0, as_of=None, dividends=None, close=None) -> dict:
    """The same bundle from in-memory frames (tests): `prices` is CAD, indexed by date.

    Defaults: local = prices, fx = 1.0, traded = prices.notna(), universe inferred from the
    tickers (.TO -> TSX/CAD/CAN, -USD -> crypto/CRYPTO, else NASDAQ/USD/USA, sector "Unknown"),
    crypto_daily = the crypto columns of `prices`, rf = a constant policy rate (fraction).
    `dividends` = DataFrame date, ticker, amount (per share, listing currency; default none) and
    `close` = the unadjusted close in listing currency (default `local` when given; with neither
    `local` nor `close` the CAD `prices` themselves, so nothing is converted twice): the bundle
    converts them like `load_market` does (`dividends` -> amount_cad with the rate in force on the
    date, `close_cad` = close x fx for USD lines).
    Nothing is filled or converted: the frames are taken as given (an `fx` Series is only carried
    forward to the calendar; days before its first rate stay NaN, never back-filled). `flags` is
    computed as in `load_market`: the dates still NaN after the 3-day forward fill, after an
    asset's first price (a one-day closed-exchange hole is not "missing data"). With `as_of`,
    everything later is cut.
    """
    if not isinstance(prices.index, pd.DatetimeIndex):
        raise TypeError("make_market needs prices indexed by date (a DatetimeIndex)")
    cutoff = None if as_of is None else pd.Timestamp(as_of)

    def cut(obj):
        return obj if cutoff is None else obj[obj.index <= cutoff]

    prices = cut(prices)
    calendar = prices.index
    universe = _infer_universe(prices.columns) if universe is None else universe
    if fx is None or np.isscalar(fx):
        fx_series = pd.Series(1.0 if fx is None else float(fx), index=calendar, name="usdcad")
    else:
        fx_series = _carry(fx, calendar)
    crypto = set(universe.loc[universe["asset_class"] == "crypto", "ticker"])
    if crypto_daily is None:
        crypto_daily = prices[[t for t in prices.columns if t in crypto]]
    last = calendar[-1] if len(calendar) else pd.Timestamp(DATASET_END)
    prices_only = local is None and close is None            # only CAD `prices` exist: they are the CAD close
    local = prices if local is None else cut(local)
    currency = dict(zip(universe["ticker"], universe["currency"]))
    no_dividends = dividends is None or dividends.empty
    rows = _dividend_rows(pd.DataFrame({"date": [], "ticker": [], "amount": []}) if no_dividends
                          else dividends, "date", "amount", universe["ticker"])
    if cutoff is not None:
        rows = rows[rows["date"] <= cutoff]
    return _bundle(
        calendar=calendar, prices=prices, local=local,
        traded=prices.notna() if traded is None else cut(traded), fx=fx_series,
        crypto_daily=cut(crypto_daily),
        rf_daily=pd.Series(float(rf), index=calendar, name="rf_daily"),
        universe=universe, flags=_flags(prices.ffill(limit=MAX_FILL_DAYS)),
        as_of=_iso(last if cutoff is None else cutoff),
        dividends=_dividends_cad(rows, fx_series, currency),
        close_cad=prices.copy() if prices_only
        else _to_cad(local if close is None else cut(close), fx_series, currency))


# --- the section 12 contract ---------------------------------------------------------------------
def load_prices_cad(tickers, start, end, as_of, *, data_dir=None, market=None) -> dict:
    """CAD adj_close for `tickers` over [start, end], never past `as_of` (spec 12).

    Returns {"prices": DataFrame (date index, one column per ticker), "flags": {ticker: [ISO
    dates in the window with no price after the 3-day fill]}, "source", "as_of"}; `as_of` names
    the last calendar day in the data on or before the requested one (a Saturday is labelled the
    Friday before, a date past the data DATASET_END; before the first day, the request itself),
    like every other tool. An unknown ticker raises ValueError("Unknown ticker: X").
    """
    m = market if market is not None else load_market(as_of, data_dir=data_dir)
    tickers = list(dict.fromkeys(tickers))
    for t in tickers:
        if t not in m["prices"].columns:
            raise ValueError(f"Unknown ticker: {t}")
    lo, hi = pd.Timestamp(start), min(pd.Timestamp(end), pd.Timestamp(as_of))
    window = m["prices"].loc[lo:hi, tickers]
    flags = {t: [d for d in m["flags"].get(t, []) if lo <= pd.Timestamp(d) <= hi] for t in tickers}
    seen = m["calendar"][m["calendar"] <= pd.Timestamp(as_of)]
    label = seen[-1] if len(seen) else min(pd.Timestamp(as_of), pd.Timestamp(m["as_of"]))
    return {"prices": window, "flags": flags, "source": SOURCE, "as_of": _iso(label)}


def mean_policy_rate(start, end, as_of, *, market=None) -> float:
    """Mean Bank of Canada policy rate (V39079 / 100, a fraction) over [start, end], <= as_of.

    The mean of the rows inside the period (daily rows in the real file, monthly in the fake one).
    A period with no row (a short window on a monthly series) takes the last rate before it;
    no rate at all before the period ends gives 0.0.
    """
    m = market if market is not None else load_market(as_of)
    rf = m["rf_daily"].dropna()
    # never past as_of, whatever the bundle holds
    lo, hi = pd.Timestamp(start), min(pd.Timestamp(end), pd.Timestamp(as_of))
    inside = rf[(rf.index >= lo) & (rf.index <= hi)]
    if len(inside):
        return float(inside.mean())
    before = rf[rf.index <= hi]
    return float(before.iloc[-1]) if len(before) else 0.0
