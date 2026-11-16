"""Risk metrics of a portfolio series, the policy-rate regime and the trailing yield (spec
section 10; plan A Tasks 4 and 5).

Every verdict and the explanation rest on these numbers, so the definitions are the spec's and
nothing else:
  - years = calendar days / 365.25, CAGR = (last / first) ** (1 / years) - 1;
  - volatility = daily standard deviation (ddof 1) x sqrt(252) of the returns between points (or x sqrt of
    `per_year`: another number, or the series' own sessions a year, see risk_metrics);
  - max drawdown = min(value / running high - 1); `peak_date` is the first date of that running
    high, `trough_date` the first date of the lowest point;
  - `recovery_days` = calendar days from the trough to the first later date at or above the peak
    value (None = not recovered). This is the rule's definition (ledger 14); time under water
    (peak to recovery) is a different number and is not computed here;
  - Sharpe = (CAGR - rf) / volatility, `rf` the mean policy rate over the period as a fraction;
  - drawdown series = value / running high - 1 on every date (fractions, 0 or below);
  - a hiking spell (`rate_regime`) = consecutive increases of the Bank of Canada policy rate with
    no cut between them and at most 183 calendar days between two increases (the 2023 pause is
    bridged); it needs 2 increases at least (a lone hike is not a cycle); `start` and `end` are the
    effective dates of its first and last increase: the rows of V39079 are the day AFTER the Bank's
    announcement (2022-03-03 for the hike announced 2022-03-02), so no rate is used before it is known;
  - trailing yield = dividends per share that went ex-dividend in the 365 days to `as_of` (ex-dates, CAD;
    special or extra distributions included; the date exactly 365 days back is out, `as_of` is in) over
    the unadjusted CAD close of the last trading day on or before `as_of`; the portfolio's yield is
    the weighted sum.

A series is {"dates": ISO strings, "values": floats above 0} as built by tools.portfolio. The
series functions are pure: they read only the series they are given, so a series cut at `as_of`
gives metrics that cannot see past it (red gate 3). `rate_regime` and `trailing_yield` read the
market bundle of tools.data and drop everything dated after `as_of` themselves, whatever the
bundle holds. A malformed series is a programming error (ValueError); a series too short for a
number gives None for it, never a division by zero.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from tools.data import DATASET_END, SOURCE as DATA_SOURCE, load_market
from tools.portfolio import _held      # the one weight check: tickers upper-cased, none below 0, sum 1
from tools.portfolio import series_from_market

DAYS_PER_YEAR = 365.25
TRADING_DAYS = 252
_ZERO_VOL = 1e-12            # an annualised volatility below this is zero (float noise on a flat line)
METRICS_SOURCE = ("Computed from the portfolio series: CAGR over calendar days / 365.25; volatility "
                  "= daily standard deviation x sqrt(252); drawdown against the running high; "
                  "recovery = calendar days from the trough back to the previous peak")
HIKE_PAUSE_DAYS = 183        # the longest pause between two increases that still belongs to one spell
RATE_SOURCE = "Bank of Canada V39079 (macro_rates.csv)"
YIELD_WINDOW_DAYS = 365
YIELD_SOURCE = ("History, not a forecast: dividends per share that went ex-dividend in the 365 days to "
                "as_of (starter corporate_actions.csv, Yahoo Finance ex-dates, retrieved 2026-11-13; "
                "special or extra distributions included; may be incomplete for ETFs), USD amounts "
                "converted with the Bank of Canada USD/CAD rate of the ex-date, divided by the unadjusted "
                "CAD close of the last trading day, weighted by the portfolio")


def _arrays(series: dict) -> tuple[pd.DatetimeIndex, np.ndarray]:
    """(dates, values) of a series, checked: same length, finite values above 0, dates increasing."""
    dates = pd.DatetimeIndex(pd.to_datetime(list(series["dates"])))
    values = np.asarray(list(series["values"]), dtype=float)
    if len(dates) != len(values):
        raise ValueError(f"The series has {len(dates)} dates but {len(values)} values.")
    if len(values) and not (np.isfinite(values).all() and (values > 0).all()):
        raise ValueError("The series needs finite values above 0.")
    if not (dates.is_monotonic_increasing and dates.is_unique):
        raise ValueError("The series dates must be increasing, one value per date.")
    return dates, values


def _iso(day) -> str | None:
    return None if day is None else pd.Timestamp(day).strftime("%Y-%m-%d")


def _max_drawdown(values: np.ndarray) -> tuple[float, int | None, int | None]:
    """(depth, peak index, trough index); depth 0.0 and no indexes when the series never falls."""
    if not len(values):
        return 0.0, None, None
    running_high = np.maximum.accumulate(values)
    depth = values / running_high - 1.0
    trough = int(np.argmin(depth))                          # the first lowest point
    if depth[trough] >= 0.0:
        return 0.0, None, None
    peak = int(np.argmax(values[: trough + 1] == running_high[trough]))   # first date of that high
    return float(depth[trough]), peak, trough


def risk_metrics(series: dict, rf: float = 0.0, *, per_year: float | str = TRADING_DAYS) -> dict:
    """Spec section 12: {cagr, volatility, max_drawdown, peak_date, trough_date, recovery_days,
    days_since_trough, sharpe, source, as_of}; percents are fractions, `as_of` = the last date.

    With no drawdown: peak_date/trough_date None, recovery_days 0, days_since_trough None. Fewer
    than 2 points: cagr None; fewer than 3 points: volatility and sharpe None (the standard
    deviation needs 2 returns, which is 3 points); zero volatility: sharpe None. `rf` is a
    fraction (mean_policy_rate over the same period). `per_year` = the sessions a year the daily
    standard deviation is annualised with: 252 (the default), another number, or "sessions" = the
    series' own, its returns / its years (calendar days / 365.25): 1,281 returns over 1,826 days on
    the 2021-26 replay = 256.2 a year (ruling R36, finance F9: Robert's move 22.37 %, not 22.18 %).
    """
    dates, values = _arrays(series)
    n = len(values)
    cagr = vol = sharpe = None
    if n >= 2:
        span = (dates[-1] - dates[0]).days
        try:
            cagr = float(float(values[-1] / values[0]) ** (DAYS_PER_YEAR / span) - 1.0)
        except OverflowError:
            cagr = None
    if n >= 3:
        k = (n - 1) * DAYS_PER_YEAR / span if per_year == "sessions" and span > 0 else per_year
        k = TRADING_DAYS if k == "sessions" else float(k)
        vol = float(np.std(values[1:] / values[:-1] - 1.0, ddof=1) * math.sqrt(k))
    if cagr is not None and vol is not None and vol > _ZERO_VOL:
        sharpe = float((cagr - rf) / vol)

    depth, peak, trough = _max_drawdown(values)
    recovery, since = 0, None
    if trough is not None:
        back = np.nonzero(values[trough + 1:] >= values[peak])[0]
        recovery = int((dates[trough + 1 + back[0]] - dates[trough]).days) if len(back) else None
        since = int((dates[-1] - dates[trough]).days)
    source = METRICS_SOURCE
    if vol is not None and k != TRADING_DAYS:          # the basis is named in the source when it is not 252
        basis = f"{k:.1f}, the sessions a year in the series" if per_year == "sessions" else f"{k:g}"
        source = METRICS_SOURCE.replace("sqrt(252)", f"sqrt({basis})")
    source += f"; series: {series['source']}" if series.get("source") else ""
    return {"cagr": cagr, "volatility": vol, "max_drawdown": depth,
            "peak_date": _iso(None if peak is None else dates[peak]),
            "trough_date": _iso(None if trough is None else dates[trough]),
            "recovery_days": recovery, "days_since_trough": since, "sharpe": sharpe,
            "source": source, "as_of": _iso(dates[-1]) if n else None}


def worst_rolling_drop(series: dict, window_days: int = 365) -> dict:
    """The worst fall from a high set at most `window_days` calendar days earlier (the "worst
    rolling 12-month drop" of spec section 2, so the start date does not do the work).

    For every date t: value(t) / highest value in [t - window_days, t] - 1 (the date exactly
    `window_days` back counts); the minimum is `value`, `peak_date` the first date of its high.
    No fall: {"value": 0.0, "peak_date": None, "trough_date": None}.
    """
    if window_days < 0:
        raise ValueError("window_days must be 0 or more.")
    dates, values = _arrays(series)
    best, peak, trough = 0.0, None, None
    if len(values):
        offset = (dates - dates[0]).days.to_numpy()
        start = np.searchsorted(offset, offset - window_days, side="left")
        for t in range(len(values)):
            window = values[start[t]: t + 1]
            top = int(np.argmax(window))                    # the first date of the window's high
            drop = float(values[t] / window[top] - 1.0)
            if drop < best:
                best, peak, trough = drop, int(start[t]) + top, t
    return {"value": best, "peak_date": _iso(None if peak is None else dates[peak]),
            "trough_date": _iso(None if trough is None else dates[trough])}


def calendar_year_returns(series: dict) -> dict:
    """{year: return}: the last value of the year over the last value of the previous year - 1;
    the first year runs from the first value, the last year may be partial (year to date).

    A year the data cannot support is left out, not guessed: the first year with a single point,
    or a year whose previous calendar year has no data (it would be a multi-year return).
    """
    dates, values = _arrays(series)
    if not len(values):
        return {}
    by_year = pd.Series(values, index=dates).groupby(dates.year)
    last, count = by_year.last(), by_year.size()
    first_year, out = int(dates[0].year), {}
    for year in last.index:
        if year == first_year and count[year] >= 2:
            out[int(year)] = float(last[year] / values[0] - 1.0)
        elif year != first_year and (year - 1) in last.index:
            out[int(year)] = float(last[year] / last[year - 1] - 1.0)
    return out


def drawdown_series(series: dict) -> dict:
    """{"dates", "values"}: on every date, value / running high - 1 (fractions, 0 or below), the
    same dates as the series. Its minimum is `risk_metrics`' max_drawdown.
    """
    dates, values = _arrays(series)
    depth = values / np.maximum.accumulate(values) - 1.0 if len(values) else values
    return {"dates": dates.strftime("%Y-%m-%d").tolist(), "values": [float(v) for v in depth]}


# --- the Bank of Canada policy-rate regime (the flight paths' backdrop) ----------------------------
def rate_regime(as_of, *, market: dict | None = None) -> dict:
    """{"hiking": [{"start", "end"}], "series": {"dates", "values"}, "source", "as_of"} from the
    policy rate (V39079 / 100, in `market["rf_daily"]`), never past `as_of`.

    A hiking spell is a run of increases with no cut between them and at most 183 days between two
    of them, so the 2023 pause is bridged; it needs 2 increases (a lone hike is not a cycle);
    `start` and `end` are the effective dates of its first and last increase (the day after the
    Bank's announcement, which is how V39079 dates its rows); a spell still running at `as_of`
    ends at its last hike. `series` is the first date, every date the rate changed and the
    last date, values as fractions (draw it as steps). `as_of` is the last date in the data (the
    request itself when there is no rate yet).
    """
    m = market if market is not None else load_market(as_of)
    end = pd.Timestamp(as_of)
    rf = m["rf_daily"].dropna().sort_index()
    rf = rf[rf.index <= end]                              # never past as_of, whatever the bundle holds
    moves = rf[rf.ne(rf.shift())]                         # the first row, then every date the rate changed
    spells: list[list[pd.Timestamp]] = [[]]
    for day, rate, before in zip(moves.index[1:], moves.iloc[1:], rf.shift().loc[moves.index].iloc[1:]):
        if rate < before:                                 # a cut ends the spell
            spells.append([])
        else:
            if spells[-1] and (day - spells[-1][-1]).days > HIKE_PAUSE_DAYS:
                spells.append([])                         # a pause too long: a new spell
            spells[-1].append(day)
    hiking = [{"start": _iso(run[0]), "end": _iso(run[-1])} for run in spells if len(run) >= 2]
    shown = rf.loc[moves.index.union(rf.index[[0, -1]].unique())] if len(rf) else rf   # a single row once
    return {"hiking": hiking,
            "series": {"dates": [_iso(d) for d in shown.index], "values": [float(v) for v in shown]},
            "source": RATE_SOURCE, "as_of": _iso(rf.index[-1] if len(rf) else end)}


# --- the trailing dividend yield (spec section 5 income, section 10) --------------------------------
def trailing_yield(weights: dict, as_of, *, market: dict | None = None) -> dict:
    """{"value", "by_ticker": {ticker: y}, "source", "as_of"}: the dividends of the 365 days to
    `as_of` (`market["dividends"]`, CAD, ex-dates; the date exactly 365 days back is out, `as_of` is
    in) over the unadjusted CAD close of the last calendar day on or before `as_of`; `value` is the
    weighted sum. History, not a forecast.

    A line that paid nothing (gold, crypto, a payer outside the window) is 0.0. A line that paid but
    has no close that day is None, and so is the total: the data cannot give the number, and 0 would
    be made up. Before the first day of data every number is None. `as_of` is the date of the close
    used (the request itself with no data); when the data starts less than 12 months before
    `as_of`, `source` says the window is shorter. The weights are checked like the series does
    (sum 1, tickers upper-cased, unknown ticker raises ValueError).
    """
    m = market if market is not None else load_market(as_of)
    held = _held(weights)
    close = m["close_cad"]
    for t in held:
        if t not in close.columns:
            raise ValueError(f"Unknown ticker: {t}")
    end = pd.Timestamp(as_of)
    div = m["dividends"]
    paid = div[(div["date"] > end - pd.Timedelta(days=YIELD_WINDOW_DAYS)) & (div["date"] <= end)
               ].groupby("ticker")["amount_cad"].sum()
    seen = close.loc[:end]
    if seen.empty:                                         # before any data: nothing can be said
        return {"value": None, "by_ticker": {t: None for t in held}, "source": YIELD_SOURCE,
                "as_of": _iso(end)}
    last, by_ticker = seen.iloc[-1], {}
    for t in held:
        amount, price = float(paid.get(t, 0.0)), float(last[t])
        if amount == 0.0:
            by_ticker[t] = 0.0                            # paid nothing: 0 is true whatever the close
        else:
            by_ticker[t] = amount / price if price > 0 else None      # no close (NaN) means no number
    value = None if None in by_ticker.values() else float(sum(held[t] * y for t, y in by_ticker.items()))
    source = YIELD_SOURCE
    if end - pd.Timedelta(days=YIELD_WINDOW_DAYS - 1) < seen.index[0]:
        source += (f"; the data starts {_iso(seen.index[0])}, so this window covers less than 12 "
                   "months")
    return {"value": value, "by_ticker": by_ticker, "source": source, "as_of": _iso(seen.index[-1])}


FACTS_SOURCE = (f"{DATA_SOURCE}; per asset, in CAD: total return = last / first - 1; volatility = daily "
                "standard deviation x sqrt(the asset's own sessions a year) (ruling R36); worst fall against the "
                "running high; each asset on the days its own exchange traded, crypto on its own UTC days")


def asset_facts(tickers=None, as_of=DATASET_END, *, market=None) -> dict:
    """Per-asset facts for the move picker (plan A Task 17; ledger data/asset_facts.json): {"as_of",
    "period": [first date, as_of], "currency": "CAD", "source", "assets": {ticker: {"total_return",
    "ann_vol", "max_drawdown", "dd_peak", "dd_trough", "days"}}, "flags": {ticker: [ISO dates still
    missing after the 3-day fill]}}. Derived numbers only, never a price; `tickers=None` = the universe.

    Each asset is a one-line portfolio (series_from_market: the union calendar, the days its own
    exchange traded, prices carried over a gap); crypto runs on its own UTC rows (`crypto_daily`).
    `ann_vol` is annualised with the asset's own sessions a year (risk_metrics per_year="sessions",
    ruling R36); `days` = the priced days the facts rest on. Everything after `as_of` is cut first.
    """
    m = market if market is not None else load_market(as_of)
    hi = pd.Timestamp(as_of)
    uni = m["universe"]
    names = list(uni["ticker"]) if tickers is None else list(dict.fromkeys(tickers))
    crypto = set(uni.loc[uni["asset_class"] == "crypto", "ticker"])
    cut = {**m, "prices": m["prices"].loc[:hi], "traded": m["traded"].loc[:hi]}
    assets, flags, starts = {}, {}, []
    for t in names:
        if t not in m["prices"].columns:
            raise ValueError(f"Unknown ticker: {t}")
        if t in crypto:
            own = m["crypto_daily"][t].loc[:hi].dropna()
            s = 100.0 * own / own.iloc[0] if len(own) else own
        else:
            s = series_from_market({t: 1.0}, cut)
        values = s.tolist()
        r = risk_metrics({"dates": s.index.strftime("%Y-%m-%d").tolist(), "values": values}, per_year="sessions")
        assets[t] = {"total_return": float(values[-1] / values[0] - 1.0) if len(values) >= 2 else None,
                     "ann_vol": r["volatility"], "max_drawdown": r["max_drawdown"],
                     "dd_peak": r["peak_date"], "dd_trough": r["trough_date"], "days": len(values)}
        flags[t] = [d for d in m["flags"].get(t, []) if pd.Timestamp(d) <= hi]
        starts += [s.index[0]] if len(s) else []
    seen = m["calendar"][m["calendar"] <= hi]
    label = seen[-1] if len(seen) else min(hi, pd.Timestamp(m["as_of"]))
    return {"as_of": _iso(label), "period": [_iso(min(starts)) if starts else None, _iso(label)],
            "currency": "CAD", "source": FACTS_SOURCE, "assets": assets, "flags": flags}
