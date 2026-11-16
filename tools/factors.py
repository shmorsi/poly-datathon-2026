"""The scenario engine of "Build your own shock" (lane sc-b, Sun Nov 15): a made-up future, written as explicit factor
shocks, becomes a move of the investor's mix through each holding's MEASURED sensitivities. Pure: no network, no model.

  FACTORS               the 7 factors (id, label, unit); every value in this module is a fraction ("pct": a return,
                        "pp": a change of the 10-year yield, 0.01 = 1 point), shown x 100
  factor_levels         the factors' daily levels (CAD), read from the starter data cut at as_of BEFORE any computation
                        (red gate 3); weekly_factors: their weekly returns (rates: the weekly change of the yield)
  sensitivities         each holding's betas: OLS with light ridge shrinkage on the 7 weekly factors (a holding that IS a
                        factor gets 1 on itself and 0 elsewhere), at least MIN_WEEKS weeks of history
  apply_shocks          the instantaneous move of a mix under one shock vector: sum of beta x shock per holding (a
                        holding cannot lose more than all of it), weight x move per holding, and the total
  presets               5 named shocks, magnitudes measured from the record, each with its source window
  validation            the engine fed real episodes' factor moves, against the mix's real move over the same window
  result_key            result.scenarios (result_extras calls it; facts rows through its `fact` callable)
  custom                POST /api/scenario: the same shape for one shock vector (bounds checked, plain-English errors)

A linear model: the sensitivities are averages of 2021-26 weekly co-movements, applied at once to a scenario's size. A
scenario is the investor's own fiction, not a forecast; nothing here says how likely it is.
"""
from __future__ import annotations

import functools
import math
import os
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import numpy as np
import pandas as pd

from governance import round_pp
from tools import data as data_mod
from tools.portfolio import portfolio_series

FACTORS = (
    {"id": "ca_stocks", "label": "Canadian stocks", "unit": "pct", "source": "XIU.TO (iShares S&P/TSX 60), in CAD"},
    {"id": "us_stocks", "label": "US stocks", "unit": "pct", "source": "SPY (S&P 500), in CAD"},
    {"id": "tech", "label": "Tech stocks", "unit": "pct", "source": "QQQ (Nasdaq-100), in CAD"},
    {"id": "energy", "label": "Energy stocks", "unit": "pct",
     "source": "XOM, CNQ.TO and ENB.TO, equal weights, in CAD"},
    {"id": "rates", "label": "Canada 10-year yield", "unit": "pp",
     "source": "Government of Canada 10-year benchmark yield (Bank of Canada), change in points"},
    {"id": "usd_cad", "label": "US dollar vs Canadian dollar", "unit": "pct",
     "source": "USD/CAD (Bank of Canada); up = the Canadian dollar slides"},
    {"id": "gold", "label": "Gold", "unit": "pct", "source": "GLD (SPDR Gold Shares), in CAD"},
)
IDS = tuple(f["id"] for f in FACTORS)
UNIT = {f["id"]: f["unit"] for f in FACTORS}
LABEL = {f["id"]: f["label"] for f in FACTORS}
SELF = {"XIU.TO": "ca_stocks", "SPY": "us_stocks", "QQQ": "tech", "GLD": "gold"}     # a holding that IS a factor
ENERGY = ("XOM", "CNQ.TO", "ENB.TO")
YIELD_ID = "BD.CDN.10YR.DQ.YLD"
START = "2021-11-12"                 # the starter data's first day
RIDGE = 0.05                         # light shrinkage: lambda = RIDGE x n on standardised factors (z-scored columns)
MIN_WEEKS = 52                       # fewer weeks of a holding's own history: no sensitivities (not covered)
BOUND_X = 3                          # a custom shock may reach 3 times the factor's largest measured move, no more
BOUND_TOL = 1e-6                     # the page reads bounds rounded to 6 decimals: a slider at its end stays inside
BOUND_WEEKS = 52                     # "largest measured move": the largest rise or fall within any 52-week stretch
TOUCH_PP = Decimal("1.0")            # R11: beyond the floor by 1 point or less is "touched"
LIBERATION_DAY = "2025-04-02"        # the tariff announcement, after the close: the window starts at that close
TARIFF_DAYS = 5                      # ... and ends at US stocks’ lowest close within the next 5 trading days
MIN_COVERED = 0.90                   # below this share of the mix with sensitivities, a result says it is partial
KIND = "hypothetical"
TOO_CLOSE = "too_close"              # red gate 4: closer to the floor than the engine's own miss on real windows
FACT_GROUPS = ("betas", "presets", "validation")   # the facts rows result.facts gets (the debrief's input): drop a group here
METHOD = ("A scenario you build, not a forecast. Each holding’s sensitivity to the 7 factors is measured on weekly "
          "returns in Canadian dollars from 2021-11 to the decision date (least squares with light ridge shrinkage; "
          "a holding that is itself a factor moves one for one with it). The engine is linear: a holding’s move is the "
          "sum of its sensitivities times the shocks, applied at once to today’s value (no path, no rebalancing, a "
          "holding cannot lose more than all of it); the mix’s move is the weighted sum. Preset sizes are measured "
          "moves from the record; the factors a preset does not name move with it as they did on average week to "
          "week (the measured co-movement). What the 7 factors do not explain (a company\u2019s own news) is outside the "
          "engine: the check replays real windows, with sensitivities measured on data that includes them (in "
          "sample), and shows the gap. A fall closer to your floor than the widest gap for that mix is too close to "
          "call: the engine cannot tell the two sides apart.")


class FactorDataMissing(Exception):
    """The data has no series for a factor (the fake pack): there is no scenario engine, never a guess."""


class ShockError(ValueError):
    """A custom shock the engine refuses, with a plain-English message for the investor."""


# --- the data, cut at as_of before anything (red gate 3) ------------------------------------------------------------
def _iso(day) -> str:
    return pd.Timestamp(day).strftime("%Y-%m-%d")


@functools.lru_cache(maxsize=4)
def _yield_file(path_str: str, mtime: int, size: int) -> pd.Series:
    frame = pd.read_csv(path_str, usecols=["date", "series_id", "value"], dtype={"date": str})
    frame = frame[frame["series_id"] == YIELD_ID].drop_duplicates("date", keep="last")
    values = pd.to_numeric(frame["value"], errors="coerce").to_numpy(float) / 100.0
    return pd.Series(values, index=pd.to_datetime(frame["date"]), name="rates").sort_index().dropna()


def ten_year(as_of, *, data_dir=None) -> pd.Series:
    """The Government of Canada 10-year yield (a fraction: 0.0325 = 3.25 %), every row dated <= as_of."""
    path = Path(data_dir or data_mod.DATA_DIR).expanduser().resolve() / "macro_rates.csv"
    if not path.is_file():
        return pd.Series(dtype=float, name="rates")
    st = path.stat()
    raw = _yield_file(str(path), st.st_mtime_ns, st.st_size)
    return raw[raw.index <= pd.Timestamp(as_of)].copy()


def factor_levels(market: dict, yield10: pd.Series, as_of=None) -> pd.DataFrame:
    """The 7 factors' daily levels on the market calendar: prices in CAD (energy: an index of the three, equal weights
    rebalanced daily), the 10-year yield (carried forward, never back-filled) and USD/CAD. Raises FactorDataMissing when
    a factor has no series at all."""
    cut = _cut(market, as_of)
    px, cal = market["prices"].loc[:cut], market["calendar"][market["calendar"] <= cut]
    need = [*SELF, *ENERGY]
    missing = [t for t in need if t not in px.columns or px[t].dropna().empty]
    if missing:
        raise FactorDataMissing(f"no prices for {', '.join(missing)}")
    y = yield10[yield10.index <= cut].dropna()
    fx = market["fx"].loc[:cut]
    if y.empty or fx.dropna().empty:
        raise FactorDataMissing("no 10-year yield or no USD/CAD")
    out = pd.DataFrame(index=cal)
    for t, f in SELF.items():
        out[f] = px[t]
    daily = px[list(ENERGY)].pct_change(fill_method=None).mean(axis=1, skipna=True)
    first = px[list(ENERGY)].dropna(how="all").index.min()
    out["energy"] = (100.0 * (1.0 + daily.where(daily.index > first, 0.0).fillna(0.0)).cumprod()).where(
        out.index >= first)
    out["rates"] = y.reindex(y.index.union(cal)).ffill().reindex(cal)
    out["usd_cad"] = fx.reindex(cal)
    return out[list(IDS)].loc[:cut]


def weekly(levels: pd.DataFrame) -> pd.DataFrame:
    """Weekly changes (week ending Friday, the last level of each week): returns for prices, the change for rates."""
    w = levels.resample("W-FRI").last()
    out = w.pct_change(fill_method=None)
    if "rates" in w.columns:
        out["rates"] = w["rates"].diff()
    return out.iloc[1:]


def move(levels: pd.DataFrame, start, end) -> dict:
    """Each factor's move from the close of `start` to the close of `end` (the last level on or before each date)."""
    a, b = levels.loc[:pd.Timestamp(start)].ffill().iloc[-1], levels.loc[:pd.Timestamp(end)].ffill().iloc[-1]
    return {f: float(b[f] - a[f]) if UNIT[f] == "pp" else float(b[f] / a[f] - 1.0) for f in IDS}


# --- the sensitivities (betas) ----------------------------------------------------------------------------------------
def _cut(market: dict, as_of=None) -> pd.Timestamp:
    """The last day any computation may see: the requested as_of, never past the bundle's own cut (red gate 3)."""
    own = pd.Timestamp(market["as_of"])
    return own if as_of is None else min(own, pd.Timestamp(as_of))


def holding_weekly(market: dict, tickers, as_of=None) -> pd.DataFrame:
    """Each holding's weekly CAD return (the last price of each week ending Friday), on the market bundle's prices."""
    px = market["prices"].loc[:_cut(market, as_of)]
    cols = [t for t in dict.fromkeys(tickers) if t in px.columns]
    w = px[cols].resample("W-FRI").last()
    return w.pct_change(fill_method=None).iloc[1:]


def _ridge(y: np.ndarray, x: np.ndarray) -> tuple:
    """Least squares with light ridge shrinkage on z-scored factors (intercept unpenalised): betas in the factors' own
    units, and the share of the holding's weekly variance the fit explains (R squared)."""
    mu, sd = x.mean(axis=0), x.std(axis=0)
    sd = np.where(sd > 0, sd, 1.0)
    z, yc = (x - mu) / sd, y - y.mean()
    n, k = z.shape
    bz = np.linalg.solve(z.T @ z + RIDGE * n * np.eye(k), z.T @ yc)
    resid = yc - z @ bz
    ss = float(yc @ yc)
    return bz / sd, (1.0 - float(resid @ resid) / ss) if ss > 0 else 0.0


def sensitivities(tickers, factors_weekly: pd.DataFrame, holdings_weekly: pd.DataFrame) -> dict:
    """{ticker: {"betas": {factor: beta}, "weeks": n, "r2": share explained, "self": factor id or None}}, or None for a
    holding with fewer than MIN_WEEKS weeks of its own history (it is then not covered). A holding that IS a factor
    (XIU.TO, SPY, QQQ, GLD) gets 1 on itself and 0 elsewhere."""
    out = {}
    for t in dict.fromkeys(tickers):
        if t in SELF:
            out[t] = {"betas": {f: 1.0 if f == SELF[t] else 0.0 for f in IDS}, "weeks": None, "r2": 1.0, "self": SELF[t]}
            continue
        if t not in holdings_weekly.columns:
            out[t] = None
            continue
        frame = pd.concat([holdings_weekly[t].rename("y"), factors_weekly[list(IDS)]], axis=1).dropna()
        if len(frame) < MIN_WEEKS:
            out[t] = None
            continue
        b, r2 = _ridge(frame["y"].to_numpy(float), frame[list(IDS)].to_numpy(float))
        out[t] = {"betas": {f: float(v) for f, v in zip(IDS, b)}, "weeks": int(len(frame)), "r2": r2, "self": None}
    return out


# --- one shock vector applied to one mix ------------------------------------------------------------------------------
def apply_shocks(weights: dict, sens: dict, shocks: dict) -> dict:
    """The instantaneous move of a mix: per holding, sum(beta x shock) (never below -100 %); its contribution, weight x
    move; the total over the covered holdings. A holding without sensitivities is listed in `uncovered` and adds 0."""
    shocks = {f: float(shocks.get(f) or 0.0) for f in IDS}
    moves, contrib, uncovered, covered = {}, {}, [], 0.0
    for t, w in weights.items():
        s = sens.get(t)
        if not s or float(w) == 0.0:
            if float(w) != 0.0:
                uncovered.append(t)
            continue
        r = max(-1.0, sum(s["betas"][f] * shocks[f] for f in IDS))
        moves[t], contrib[t] = r, float(w) * r
        covered += float(w)
    total = float(sum(float(w) for w in weights.values())) or 1.0
    return {"move": float(sum(contrib.values())), "holdings": moves, "contributions": contrib,
            "uncovered": uncovered, "covered": covered / total}


def fill(shocks: dict, factors_weekly: pd.DataFrame) -> dict:
    """The factors a shock does not name, moved with the named ones as they did on average week to week (the
    conditional mean of a joint normal fitted to the weekly factor changes, no drift): E[other | named] =
    S_on S_nn^-1 named. Named values are kept as given. A linear rule, applied to the scenario's size."""
    named = [f for f in IDS if f in shocks and shocks[f] is not None]
    if not named or len(named) == len(IDS):
        return {f: float(shocks.get(f) or 0.0) for f in IDS}
    cov = factors_weekly[list(IDS)].dropna().cov()
    others = [f for f in IDS if f not in named]
    s_n = np.array([float(shocks[f]) for f in named])
    implied = cov.loc[others, named].to_numpy() @ np.linalg.solve(cov.loc[named, named].to_numpy(), s_n)
    out = {f: float(shocks[f]) for f in named}
    out.update({f: float(v) for f, v in zip(others, implied)})
    return {f: out[f] for f in IDS}


# --- sizes the record shows: the largest move, the bounds -------------------------------------------------------------
def largest_moves(levels: pd.DataFrame, weeks: int = BOUND_WEEKS) -> dict:
    """{factor: the largest rise or fall (absolute) between two weekly closes at most `weeks` apart}."""
    w = levels.resample("W-FRI").last().dropna(how="all")
    out = {}
    for f in IDS:
        v = w[f].dropna().to_numpy(float)
        best = 0.0
        for lag in range(1, min(weeks, len(v) - 1) + 1):
            d = (v[lag:] - v[:-lag]) if UNIT[f] == "pp" else (v[lag:] / v[:-lag] - 1.0)
            best = max(best, float(np.max(np.abs(d))) if len(d) else 0.0)
        out[f] = best
    return out


def bounds(largest: dict) -> dict:
    """{factor: [lo, hi]}: BOUND_X times the largest measured move either way; a price cannot fall more than 100 %."""
    out = {}
    for f in IDS:
        span = BOUND_X * float(largest[f])
        out[f] = [max(-span, -1.0) if UNIT[f] == "pct" else -span, span]
    return out


def check_shocks(shocks, bnds: dict) -> dict:
    """The custom shock vector, validated: known factor ids, finite numbers, each inside its bounds. Raises ShockError
    with a plain-English message naming the first problem. Factors not given are left out (None)."""
    if not isinstance(shocks, dict) or not shocks:
        raise ShockError("Give at least one factor move, for example {\"tech\": -0.30}.")
    unknown = [str(k) for k in shocks if k not in IDS]
    if unknown:
        raise ShockError(f"Unknown factor: {unknown[0]}. The factors are: {', '.join(IDS)}.")
    out = {}
    for f, v in shocks.items():
        if v is None:
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)):
            raise ShockError(f"The move for {LABEL[f]} must be a number (a fraction: -0.30 is a 30 % fall).")
        lo, hi = bnds[f]
        if not lo - BOUND_TOL <= float(v) <= hi + BOUND_TOL:
            unit = "\u00a0points" if UNIT[f] == "pp" else "\u00a0%"
            txt = lambda x: f"{x * 100:.1f}".replace("-", "\u2212")              # noqa: E731 (the page's minus sign)
            raise ShockError(f"{LABEL[f]}: a move of {txt(float(v))}{unit} is outside the range this engine accepts "
                             f"({txt(lo)}{unit} to {txt(hi)}{unit}, 3 times the largest move measured in the 2021-26 "
                             "data).")
        out[f] = float(v)
    if not out:
        raise ShockError("Give at least one factor move, for example {\"tech\": -0.30}.")
    return out


# --- the floor, as the rest of the page judges it ---------------------------------------------------------------------
def floor_status(move, floor) -> str | None:
    """'held' / 'touched' / 'broke' (R11, web/lib/status.js FLOOR_WORDS): the move against the floor after rounding both
    to 0.1 pp with governance.round_pp (the verdict's floor rule); beyond it by 1 point or less is 'touched'."""
    if move is None or floor is None:
        return None
    d, f = round_pp(move), round_pp(floor)
    if d >= f:
        return "held"
    return "touched" if d >= f - TOUCH_PP else "broke"


def judge(move, floor, gap=None) -> tuple:
    """(floor_status, margin_pp). margin_pp = round_pp(move) - round_pp(floor), in points (positive: above the floor).
    When |margin| <= gap (the engine's widest miss on the real check windows for that mix, points) the engine cannot
    tell the two sides apart: "too_close" (red gate 4: say when the data cannot support a conclusion). Otherwise the
    floor classes of floor_status. (None, None) without a move or a floor."""
    if move is None or floor is None:
        return None, None
    margin = round_pp(move) - round_pp(floor)
    if gap is not None and abs(margin) <= Decimal(repr(float(gap))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP):
        return TOO_CLOSE, float(margin) + 0.0
    return floor_status(move, floor), float(margin) + 0.0


def widest_gaps(validation) -> dict:
    """{"today", "after"}: the widest engine-minus-real gap (absolute, points) over the check windows, per mix; None
    for a mix with no check."""
    out = {}
    for s in ("today", "after"):
        gaps = [abs(float(v[f"gap_pp_{s}"])) for v in validation or [] if v.get(f"gap_pp_{s}") is not None]
        out[s] = max(gaps) if gaps else None
    return out


def dollars(amount, move) -> int | None:
    """amount x move, whole dollars, ROUND_HALF_UP (negative for a fall)."""
    if amount is None or move is None:
        return None
    return int((Decimal(repr(float(amount))) * Decimal(repr(float(move)))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


# --- windows the record shows (presets and the check) ----------------------------------------------------------------
def _fall(s: pd.Series):
    """(peak, trough, move) of the largest peak-to-trough fall of a level series."""
    s = s.dropna()
    trough = (s / s.cummax() - 1.0).idxmin()
    peak = s.loc[:trough].idxmax()
    return peak, trough, float(s[trough] / s[peak] - 1.0)


def _rise(s: pd.Series, diff: bool = False):
    """(trough, peak, move) of the largest trough-to-peak rise (a difference for rates, else a ratio)."""
    s = s.dropna()
    up = (s - s.cummin()) if diff else (s / s.cummin() - 1.0)
    peak = up.idxmax()
    trough = s.loc[:peak].idxmin()
    return trough, peak, float(s[peak] - s[trough]) if diff else float(s[peak] / s[trough] - 1.0)


def _rise_3m(s: pd.Series):
    """(start, end, move): the largest rise from one close to the last close within the next 3 months."""
    s = s.dropna()
    idx, vals, best = s.index, s.to_numpy(float), (None, None, -np.inf)
    ends = idx.searchsorted(idx + pd.DateOffset(months=3), side="right") - 1
    for i, j in enumerate(ends):
        if j > i and vals[j] / vals[i] - 1.0 > best[2]:
            best = (idx[i], idx[j], float(vals[j] / vals[i] - 1.0))
    return best


def _tariff_window(levels: pd.DataFrame):
    """From the close of Liberation Day (2025-04-02) to US stocks’ lowest close in the next TARIFF_DAYS trading days."""
    day = pd.Timestamp(LIBERATION_DAY)
    after = levels["us_stocks"].loc[day:].dropna()
    if len(after) < TARIFF_DAYS + 1 or after.index[0] != day:
        return None
    return day, after.iloc[1:TARIFF_DAYS + 1].idxmin()


def windows(levels: pd.DataFrame) -> dict:
    """{id: (start, end, headline factor or None, measured move of that factor)} for the presets and the check, each
    from data <= the levels' last day; a window the data does not reach yet is left out."""
    out, y22 = {}, levels.loc[:"2022-12-31"]
    last = levels.index[-1]
    if last >= pd.Timestamp("2022-12-30"):
        p, t, v = _fall(y22["tech"])
        out["tech_2022"] = (p, t, "tech", v)
        a, b, v = _rise(y22["energy"])
        out["oil_2022"] = (a, b, "energy", v)
        a, b, v = _rise(y22["rates"], diff=True)
        out["rates_2022"] = (a, b, "rates", v)
        p, t, v = _fall(y22["us_stocks"])
        out["drawdown_2022"] = (p, t, "us_stocks", v)
    if last >= pd.Timestamp("2023-12-29"):
        a, b, v = _rise(levels["rates"].loc["2023-01-01":"2023-12-31"], diff=True)
        out["rates_2023"] = (a, b, "rates", v)
    tw = _tariff_window(levels)
    if tw:
        out["tariffs_2025"] = (tw[0], tw[1], None, None)
    a, b, v = _rise_3m(levels["usd_cad"])
    if a is not None:
        out["cad_slide"] = (a, b, "usd_cad", v)
    return out


PRESETS = (   # id, label, the measured size it carries (its source episode), red gate 1: no "sell" in any label
    ("tech_2022", "AI and chip slump like 2022", "Tech stocks’ largest fall in 2022 (QQQ in CAD)"),
    ("oil_2022", "Oil spike like 2022", "Energy stocks’ largest rise in 2022 (XOM, CNQ.TO, ENB.TO, in CAD)"),
    ("rates_2022", "Rates up like 2022", "The Canada 10-year yield’s largest rise in 2022"),
    ("tariffs_2025", "Tariff shock like Apr 2025",
     "Every factor’s move from the close of 2025-04-02 (Liberation Day) to US stocks’ lowest close of the next 5 "
     "trading days"),
    ("cad_slide", "Canadian dollar slide", "USD/CAD’s largest 3-month rise in the 2021-26 data"),
)
CHECKS = (    # the engine fed real windows' factor moves (all 7 measured), against the mix's real move
    ("drawdown_2022", "The 2022 drawdown", "US stocks’ (SPY in CAD) largest fall in 2022"),
    ("tariffs_2025", "Liberation Day, Apr 2025", "Liberation Day to US stocks’ lowest close of the next 5 trading days"),
    ("rates_2023", "Rates up in 2023", "The Canada 10-year yield’s largest rise in 2023"),
)


def real_move(weights: dict, start, end, as_of, market: dict) -> float | None:
    """The mix's real move from the close of `start` to the close of `end` (tools.portfolio, constant weights)."""
    s = portfolio_series(weights, start, end, as_of, market=market)
    v = s["values"]
    return float(v[-1] / v[0] - 1.0) if len(v) > 1 and v[0] else None


# --- the engine for one decision date ---------------------------------------------------------------------------------
def context(as_of, tickers, *, market=None, yield10=None, data_dir=None) -> dict:
    """Everything one decision date needs: the factor levels and weekly changes, each holding's sensitivities, the
    largest measured moves and the bounds, the windows. All from data <= as_of. Raises FactorDataMissing."""
    m = market if market is not None else data_mod.load_market(as_of, data_dir=data_dir)
    cut = _cut(m, as_of)
    y = yield10 if yield10 is not None else ten_year(cut, data_dir=data_dir)
    levels = factor_levels(m, y[y.index <= cut], cut)
    fw = weekly(levels).dropna()
    if len(fw) < MIN_WEEKS:
        raise FactorDataMissing(f"only {len(fw)} weeks of factor history")
    largest = largest_moves(levels)
    return {"market": m, "as_of": _iso(levels.index[-1]), "levels": levels, "weekly": fw,
            "sens": sensitivities(tickers, fw, holding_weekly(m, tickers, cut)), "largest": largest,
            "bounds": bounds(largest), "windows": windows(levels)}


def side(weights, ctx, shocks, amount, floor, gap=None) -> dict | None:
    """One mix under one shock vector: fall (the signed move: negative is a fall), dollars, floor_status (with
    "too_close" when the margin is inside `gap`), margin_pp and the gap_pp it was judged with, coverage."""
    if not weights:
        return None
    r = apply_shocks(weights, ctx["sens"], shocks)
    status, margin = judge(r["move"], floor, gap)
    return {"fall": r["move"], "dollars": dollars(amount, r["move"]), "floor_status": status, "margin_pp": margin,
            "gap_pp": gap, "covered": r["covered"], "uncovered": r["uncovered"], "partial": r["covered"] < MIN_COVERED,
            "_contributions": r["contributions"]}


def _strip(s):
    return {k: v for k, v in s.items() if not k.startswith("_")} if s else None


def _scenario(ctx, shocks, named, today, after, amount, floor, gaps=None) -> dict:
    full = fill({f: shocks[f] for f in named}, ctx["weekly"])
    gaps = gaps or {}
    t = side(today, ctx, full, amount, floor, gaps.get("today"))
    a = side(after, ctx, full, amount, floor, gaps.get("after")) if after else None
    main = a or t
    return {"shocks": full, "measured": [f for f in IDS if f in named], "implied": [f for f in IDS if f not in named],
            "today": _strip(t), "after": _strip(a), "contributions": dict(main["_contributions"]) if main else {},
            "contributions_mix": "after" if a else "today",
            "contributions_today": dict(t["_contributions"]) if (a and t) else None}


def preset_rows(ctx, today, after, amount, floor, gaps=None) -> list:
    rows, win = [], ctx["windows"]
    for pid, label, source in PRESETS:
        if pid not in win:
            continue
        start, end, headline, value = win[pid]
        shocks = move(ctx["levels"], start, end) if headline is None else {headline: value}
        named = list(IDS) if headline is None else [headline]
        rows.append({"id": pid, "label": label, "source": source, "window": {"start": _iso(start), "end": _iso(end)},
                     "headline": headline, **_scenario(ctx, shocks, named, today, after, amount, floor, gaps)})
    return rows


def _gap(model, real):
    return float(round_pp(model - real)) + 0.0 if model is not None and real is not None else None


def validation_rows(ctx, today, after) -> list:
    rows, win, m = [], ctx["windows"], ctx["market"]
    for cid, label, source in CHECKS:
        if cid not in win:
            continue
        start, end = win[cid][0], win[cid][1]
        shocks = move(ctx["levels"], start, end)
        row = {"episode": cid, "label": label, "source": source, "window": {"start": _iso(start), "end": _iso(end)},
               "shocks": shocks}
        for name, mix in (("today", today), ("after", after)):
            model = apply_shocks(mix, ctx["sens"], shocks)["move"] if mix else None
            real = real_move(mix, start, end, ctx["as_of"], m) if mix else None
            row[f"real_{name}"], row[f"model_{name}"], row[f"gap_pp_{name}"] = real, model, _gap(model, real)
        row["gap_pp"] = row["gap_pp_after"] if after else row["gap_pp_today"]
        rows.append(row)
    return rows


def _num(x, nd=6):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return round(x, nd) if math.isfinite(x) else None


def _clean(obj):
    """Finite floats rounded to 6 decimals (JSON with allow_nan=False), dates as ISO strings."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        return _num(obj)
    if isinstance(obj, pd.Timestamp):
        return _iso(obj)
    return obj


def _factor_rows(ctx) -> list:
    """FACTORS as the page reads them: id, label, unit, source, and each factor's own bounds [lo, hi] and largest move."""
    return [{**{k: f[k] for k in ("id", "label", "unit", "source")}, "bounds": list(ctx["bounds"][f["id"]]),
             "largest": ctx["largest"][f["id"]]} for f in FACTORS]


def build(as_of, today, after=None, *, amount=None, floor=None, market=None, yield10=None, data_dir=None) -> dict:
    """result.scenarios for one decision date and one or two mixes (today, and with the move): factors, betas, fit,
    largest moves, bounds, presets, validation, method, kind. Raises FactorDataMissing without the factor data."""
    today, after = dict(today or {}), (dict(after) if after else None)
    tickers = list(dict.fromkeys([*today, *(after or {})]))
    ctx = context(as_of, tickers, market=market, yield10=yield10, data_dir=data_dir)
    sens = ctx["sens"]
    checks = validation_rows(ctx, today, after)
    gaps = widest_gaps(checks)
    out = {"kind": KIND, "as_of": ctx["as_of"], "method": METHOD,
           "factors": _factor_rows(ctx),
           "betas": {t: dict(s["betas"]) for t, s in sens.items() if s},
           "fit": {t: {"r2": s["r2"], "weeks": s["weeks"], "self": s["self"]} for t, s in sens.items() if s},
           "uncovered": [t for t, s in sens.items() if not s],
           "largest": dict(ctx["largest"]), "bounds": dict(ctx["bounds"]),
           "presets": preset_rows(ctx, today, after, amount, floor, gaps),
           "validation": checks, "gaps": gaps,
           "source": ("Starter prices (adjusted close, CAD), Bank of Canada USD/CAD and 10-year yield, weekly from "
                      f"{START} to {ctx['as_of']}; tools.factors (lane sc-b)")}
    return _clean(out)


# --- result.scenarios and its facts rows (result_extras calls result_key) --------------------------------------------
def _pct_words(f) -> str:
    return "a 1-point rise of the Canada 10-year yield" if UNIT[f] == "pp" else f"a 1 % move of {LABEL[f].lower()}"


def add_facts(sc: dict, fact) -> dict:
    """One facts row per number the section shows (fact(label, value, unit, entity, kind, path=, source=) -> id): the
    scenario results and contributions are fiction, the sensitivities and the implied co-moves assumptions, the measured
    sizes and the real moves facts. Returns {path: fact id}."""
    ids, src = {}, sc["source"]

    def put(path, label, value, unit, entity, kind):
        if path.split(".")[0] not in FACT_GROUPS:
            return
        tid = fact(label, value, unit, entity, kind, path=f"scenarios.{path}", source=src)
        if tid:
            ids[path] = tid

    for t, b in sc["betas"].items():
        for f in IDS:
            if b[f]:
                put(f"betas.{t}.{f}", f"Measured sensitivity (weekly, 2021-26): {t}’s move for {_pct_words(f)}",
                    b[f] * 0.01, "pct", t, "assumption")
    for p in sc["presets"]:
        name = f"Made-up scenario “{p['label']}”"
        for f in IDS:
            kind = "fact" if f in p["measured"] else "assumption"
            put(f"presets.{p['id']}.shocks.{f}", f"{name}: {LABEL[f]} move"
                + ("" if kind == "fact" else " (moving with the named factor, measured co-movement)"),
                p["shocks"][f], UNIT[f], LABEL[f], kind)
        for s, words in (("today", "your mix today"), ("after", "your mix with the move")):
            if p.get(s):
                put(f"presets.{p['id']}.{s}.fall", f"{name}: {words} would move about", p[s]["fall"], "pct", s, "fiction")
                put(f"presets.{p['id']}.{s}.dollars", f"{name}: {words}, on your fictional amount", p[s]["dollars"],
                    "CAD", s, "fiction")
                if p[s].get("margin_pp") is not None:
                    put(f"presets.{p['id']}.{s}.margin_pp", f"{name}: {words}, distance to your floor (points)",
                        p[s]["margin_pp"] / 100, "pp", s, "fiction")
        mix = "your mix with the move" if p["contributions_mix"] == "after" else "your mix today"
        for t, v in p["contributions"].items():
            put(f"presets.{p['id']}.contributions.{t}", f"{name}: {t}’s part of the move of {mix}", v, "pct", t, "fiction")
    for s, words in (("today", "your mix today"), ("after", "your mix with the move")):
        if (sc.get("gaps") or {}).get(s) is not None:
            put(f"validation.widest_gap_{s}", f"Engine check: the widest gap between the engine and the real move, "
                f"{words} (points)", sc["gaps"][s] / 100, "pp", s, "assumption")
    for v in sc["validation"]:
        span = f"Engine check, {v['label']} ({v['window']['start']} to {v['window']['end']})"
        for s, words in (("today", "your mix today"), ("after", "your mix with the move")):
            if v.get(f"real_{s}") is None:
                continue
            put(f"validation.{v['episode']}.real_{s}", f"{span}: {words}, real move", v[f"real_{s}"], "pct", s, "fact")
            put(f"validation.{v['episode']}.model_{s}", f"{span}: {words}, the engine’s move", v[f"model_{s}"], "pct", s,
                "assumption")
            if v.get(f"gap_pp_{s}") is not None:
                put(f"validation.{v['episode']}.gap_pp_{s}", f"{span}: {words}, engine minus real (points)",
                    v[f"gap_pp_{s}"] / 100, "pp", s, "assumption")
    return ids


def _reuse(result: dict, fact):
    """A fact callable that keeps a recomputed key's rows (result_extras --refresh scenarios): a path already registered
    for result.scenarios gets its row updated in place (same id, never twice); a new path gets a new row."""
    facts = result.get("facts") if isinstance(result.get("facts"), dict) else {}
    known = {(t.get("inputs") or {}).get("path"): t for t in result.get("trace") or []
             if isinstance(t, dict) and t.get("tool") == "result_extras.scenarios" and t.get("id") in facts}

    def put(label, value, unit, entity, kind, *, path, source):
        row = known.get(path)
        if row is None or value is None:
            return fact(label, value, unit, entity, kind, path=path, source=source)
        value = value if unit in ("count", "CAD", "months") else _num(value, 10)
        facts[row["id"]].update({"label": label, "value": value, "unit": unit, "entity": entity, "kind": kind,
                                 "sign": "negative" if value < 0 else "positive" if value > 0 else "zero"})
        row["outputs"] = {"value": value}
        return row["id"]
    return put


def result_key(ins: dict, fact=None, *, market=None, yield10=None, result=None) -> dict | None:
    """result.scenarios from result_extras.inputs(result): today's mix, the mix with the move, amount, floor, as_of.
    None when the data has no factor series (the fake pack): there is then no scenario engine, never a guess. With
    `result`, a key computed again reuses its facts rows (same ids) and adds rows only for new numbers."""
    if not ins.get("today") or not ins.get("as_of"):
        return None
    try:
        sc = build(ins["as_of"], ins["today"], ins.get("after"), amount=ins.get("amount"), floor=ins.get("floor"),
                   market=market, yield10=yield10)
    except FactorDataMissing:
        return None
    if callable(fact) and isinstance(result, dict):
        fact = _reuse(result, fact)
    sc["facts"] = add_facts(sc, fact) if callable(fact) else {}
    return sc


# --- POST /api/scenario: one custom shock vector ----------------------------------------------------------------------
def _custom_facts(out: dict) -> dict:
    """{path: facts row} for the numbers of one custom answer (no Result, so no trace ids): the investor's own moves and
    every result are fiction, the co-moves and the sensitivities assumptions."""
    rows = {}

    def put(path, label, value, unit, entity, kind):
        if value is not None:
            rows[path] = {"label": label, "value": value, "unit": unit, "entity": entity,
                          "sign": "negative" if value < 0 else "positive" if value > 0 else "zero", "kind": kind}

    for f in IDS:
        own = f in out["measured"]
        put(f"shocks.{f}", f"Your made-up scenario: {LABEL[f]} move" + ("" if own else " (moving with your moves, "
            "measured co-movement)"), out["shocks"][f], UNIT[f], LABEL[f], "fiction" if own else "assumption")
    for s, words in (("today", "your mix today"), ("after", "your mix with the move")):
        if out.get(s):
            put(f"{s}.fall", f"Your made-up scenario: {words} would move about", out[s]["fall"], "pct", s, "fiction")
            put(f"{s}.dollars", f"Your made-up scenario: {words}, on your fictional amount", out[s]["dollars"], "CAD", s,
                "fiction")
            if out[s].get("margin_pp") is not None:
                put(f"{s}.margin_pp", f"Your made-up scenario: {words}, distance to your floor (points)",
                    out[s]["margin_pp"] / 100, "pp", s, "fiction")
            if out[s].get("gap_pp") is not None:
                put(f"{s}.gap_pp", f"Engine check: the widest gap between the engine and the real move, {words} "
                    "(points)", out[s]["gap_pp"] / 100, "pp", s, "assumption")
    for t, v in out["contributions"].items():
        put(f"contributions.{t}", f"Your made-up scenario: {t}’s part of the move", v, "pct", t, "fiction")
    for t, b in out["betas"].items():
        for f in IDS:
            if b[f]:
                put(f"betas.{t}.{f}", f"Measured sensitivity (weekly, 2021-26): {t}’s move for {_pct_words(f)}",
                    b[f] * 0.01, "pct", t, "assumption")
    return _clean(rows)


def custom(portfolio: dict, shocks: dict, *, baseline=None, amount=None, floor=None, as_of=None, fill_others=True,
           market=None, yield10=None, data_dir=None) -> dict:
    """One custom shock vector (POST /api/scenario) in the shape of one preset: `portfolio` is the mix the scenario is
    about; with `baseline` (today's mix) the answer has today and after, else today only (the Result's convention).
    `shocks` = {factor id: fraction} (rates: a change of the yield, 0.01 = 1 point); each is checked against BOUND_X
    times the factor's largest measured move (ShockError, plain words, otherwise). With `fill_others` the factors not
    given move with the given ones (measured co-movement, listed in `implied`); without it they stay at 0. Raises
    FactorDataMissing when the data has no factor series."""
    as_of = as_of or data_mod.DATASET_END
    today, after = (dict(baseline), dict(portfolio)) if baseline else (dict(portfolio), None)
    tickers = list(dict.fromkeys([*today, *(after or {})]))
    ctx = context(as_of, tickers, market=market, yield10=yield10, data_dir=data_dir)
    named = check_shocks(shocks, ctx["bounds"])
    checks = validation_rows(ctx, today, after)
    gaps = widest_gaps(checks)
    if fill_others:
        sc = _scenario(ctx, named, list(named), today, after, amount, floor, gaps)
    else:
        full = {f: float(named.get(f, 0.0)) for f in IDS}
        sc = _scenario(ctx, full, list(IDS), today, after, amount, floor, gaps)
        sc["measured"], sc["implied"] = [f for f in IDS if f in named], []
    out = {"kind": KIND, "as_of": ctx["as_of"], "method": METHOD, "label": "Your made-up scenario",
           "factors": _factor_rows(ctx), **sc,
           "betas": {t: dict(s["betas"]) for t, s in ctx["sens"].items() if s},
           "uncovered": [t for t, s in ctx["sens"].items() if not s],
           "largest": dict(ctx["largest"]), "bounds": dict(ctx["bounds"]), "validation": checks, "gaps": gaps,
           "source": ("Starter prices (adjusted close, CAD), Bank of Canada USD/CAD and 10-year yield, weekly from "
                      f"{START} to {ctx['as_of']}; tools.factors (lane sc-b)")}
    out = _clean(out)
    out["facts"] = _custom_facts(out)
    return out


# --- anchors for the navigator (lane sc-a): the measured sizes a made-up scenario may lean on -------------------------
def anchors(as_of=None, *, market=None, yield10=None, data_dir=None) -> dict:
    """{"as_of", "factors", "bounds", "largest", "anchors": [{"factor", "value", "label", "source", "window"}]}: every
    measured precedent size of the presets and of the check windows (a factor's move over a real window), each with
    its window, for a prompt to quote as data; bounds are what check_shocks accepts. No mix needed."""
    as_of = as_of or data_mod.DATASET_END
    ctx = context(as_of, [], market=market, yield10=yield10, data_dir=data_dir)
    rows = []
    named = {pid: (label, source) for pid, label, source in PRESETS} | {cid: (label, source) for cid, label, source in CHECKS}
    for wid, (start, end, headline, value) in ctx["windows"].items():
        label, source = named.get(wid, (wid, ""))
        moves = move(ctx["levels"], start, end) if headline is None else {headline: value}
        for f, v in moves.items():
            rows.append({"factor": f, "value": v, "label": label, "source": source, "id": wid,
                         "window": {"start": _iso(start), "end": _iso(end)}})
    return _clean({"as_of": ctx["as_of"], "factors": _factor_rows(ctx),
                   "bounds": dict(ctx["bounds"]), "largest": dict(ctx["largest"]), "anchors": rows})
