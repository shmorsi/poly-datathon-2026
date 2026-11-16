"""The Replay keys (lane B3, Sun Nov 15; design rulings R5,
R11, R12 and R13). One call, `extend(result, engine=...)`, adds to a computed Result (pipeline.run calls it right after
COMPARE, so the debrief may cite the new facts and the receipt checks them):

  deep_windows      every H-month stretch of the proxy panel (H = the investor's horizon), the worst fall per start ◐
  deep_history      the 11 sourced crises by proxy (tools.deep), each side broke / touched / held, the robust claims ◐
  deep_validation   the proxies beside the real engine on 2021-11 -> 2025-12 ◐
  navigator_effect  proofs.navigator_effect: the navigator's reading against the keyword rules' reading
  evidence          {fact_id: rows}: the public cut (the portfolio's own values; never a licensed price or rate)
  tipping_band      the first size that breaks the floor, per start month Nov 2021 ... Nov 2023 (floor rule only) ●
  not_2022          the worst fall using only dates from 2023-01-01 ●
  ladder            the same move weight in SPY, QQQ and the moved ticker, judged by governance.evaluate ●
  reconciliation    our returns beside the issuers' published ones (the table of tests/test_metrics.py) ●
  tipping_point.curve[i].loss_dollars   amount x curve[i].max_drawdown, whole dollars ○
  fix wave (R35, R36; lane fin-backend):
  capacity          the second limit: each side's path against amount - capacity ($510,000 for Robert), sessions below ○●
  breaches[i].fall_dollars   the low less the high, the path's own dollars (never amount x depth) ○
  peer_check        the move's size in each of the pack's 20 stocks: how many ended above today, how many broke the floor ●
  never_rebalanced  the mix after the move bought once and never rebalanced: the moved line's largest share, the breaks ●
  funding_check     the move funded in proportion, from the largest holding, from bonds and cash: the worst falls, verdicts ●
  volatility        each side annualised with the replay's own sessions a year (tools.metrics per_year="sessions") ●
  hedge_compare.hedged_carry   the hedged stand-in plus the rate-gap carry of a CAD hedge, hedged like XSP ◐

Every number is computed here, in Python (red gate 2). Nothing dated after `as_of` is read (red gate 3). Deep history
is a disclosure: it never enters the checks, the verdict, the kpis or the dial (R5), and its facts are "assumption".
Never raises: a key that fails is None and leaves one trace row with the exception's type (never its text).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import numpy as np
import pandas as pd

KEYS = ("deep_windows", "deep_history", "deep_validation", "navigator_effect", "evidence", "tipping_band", "not_2022",
        "ladder", "reconciliation", "hedge_compare", "end_values", "scenarios", "capacity", "peer_check",
        "never_rebalanced", "funding_check", "volatility", "funds")
FAMILIES = ("tariffs", "war_oil", "chips", "rates")
MINUS = "−"
TOUCH_PP = Decimal("1.0")            # R11: a break within 1 point of the floor is "touched", not "broke"
WHY_NEAR = "within 1 point of your floor"
COVERED_MIN = 0.90                   # deep history runs on the covered part of a mix only when >= 90 % has a proxy
FROM_2023 = "2023-01-01"             # not_2022: the dates kept
BAND_STARTS = ("2021-11", "2023-11")  # tipping_band: the first and last start month
VALIDATION = ("2021-11", "2025-12")  # deep_validation: base = the end of the first month, through the last
SENS_FLOOR = 0.02                    # robust claims: the floor 2 points either side
SENS_MONTHS = 12                     # robust claims: the episode window 12 months longer at either end
LADDER = (("SPY", "the broad US market"), ("QQQ", "the Nasdaq-100 fund"))
PROXY_LABEL = {"CHIPS": "the US chip industry", "US_MKT": "the US stock market", "BUSEQ": "US business equipment",
               "SOFTW": "the US software industry", "HARDW": "the US computer hardware industry", "OIL": "the US oil industry",
               "RTAIL": "the US retail industry", "AUTOS": "the US auto industry", "BANKS": "the US bank industry",
               "DRUGS": "the US drug industry", "HSHLD": "the US household products industry",
               "CA_EQ": "the Canadian stock market", "CAD_BOND": "Canadian government bonds", "GOLD": "gold",
               "CAD_TBILL": "Canadian T-bills"}
# Our returns beside the issuers' published returns (R12): five rows of the twelve in tests/test_metrics.py ISSUER (read on
# the fund pages on 2026-11-14, in the issuer's basis; a test pins these to that table). Ours is computed at run time.
RECONCILIATION = (
    ("XIU.TO", "2025-12-31", "2026-11-12", "YTD to 2026-11-12, NAV", 17.93,
     "https://www.blackrock.com/ca/investors/en/products/239832/ishares-sptsx-60-index-etf"),
    ("XBB.TO", "2025-12-31", "2026-11-12", "YTD to 2026-11-12, NAV", 0.69,
     "https://www.blackrock.com/ca/investors/en/products/239493/ishares-core-canadian-universe-bond-index-etf"),
    ("SPY", "2025-10-31", "2026-10-31", "1 year to 2026-10-31, market", 11.97,
     "https://www.ssga.com/us/en/intermediary/etfs/state-street-spdr-sp-500-etf-trust-spy"),
    ("SPY", "2023-10-31", "2026-10-31", "3 years a year to 2026-10-31, market", 23.25,
     "https://www.ssga.com/us/en/intermediary/etfs/state-street-spdr-sp-500-etf-trust-spy"),
    ("GLD", "2025-10-31", "2026-10-31", "1 year to 2026-10-31, market", -3.35,
     "https://www.ssga.com/us/en/intermediary/etfs/spdr-gold-shares-gld"),
)
RECONCILIATION_TOLERANCE_PP = 0.15   # tests/test_metrics.py TOLERANCE_PP (docs/finance_methods.md section 7)
RECONCILIATION_READ_ON = "2026-11-14"
SOURCES = {
    "deep": "Proxy replay (assumption): monthly, CAD, constant weights rebalanced monthly; tools.deep panel",
    "band": "tools.portfolio.portfolio_series at each size of the curve, from each start month; floor rule only, 0.1 pp",
    "not_2022": "tools.portfolio.portfolio_series from 2023-01-01; tools.metrics.risk_metrics",
    "ladder": "tools.portfolio.apply_change + governance.evaluate at the move’s weight, on the same replay data",
    "reconciliation": "Ours: the dataset’s adjusted close in the listing currency; published: the issuer’s fund page",
    "evidence": "proofs.evidence_rows, public cut (the portfolio’s own values from the Result’s series)",
    "navigator": "proofs.navigator_effect (the navigator’s reading against the keyword rules’ reading)",
}


# --- small helpers ------------------------------------------------------------------------------------------------
def _pp(x) -> Decimal:
    """A fraction as percent to 0.1 pp, ROUND_HALF_UP through repr (governance.round_pp; pitfall 5)."""
    return (Decimal(repr(float(x))) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _beyond(depth, floor) -> bool:
    """The verdict's floor rule: deeper than the floor after rounding both to 0.1 pp."""
    return _pp(depth) < _pp(floor)


def classify(depth, floor) -> str | None:
    """'broke' (beyond the floor by more than 1 point), 'touched' (beyond it by 1 point or less) or 'held' (R11)."""
    if depth is None or floor is None:
        return None
    d, f = _pp(depth), _pp(floor)
    if d >= f:
        return "held"
    return "touched" if d >= f - TOUCH_PP else "broke"


def _dollars(amount, depth) -> int | None:
    """amount x depth, whole dollars, ROUND_HALF_UP (negative for a fall): "the same fall on his $600,000" (R13)."""
    if amount is None or depth is None:
        return None
    return int((Decimal(repr(float(amount))) * Decimal(repr(float(depth)))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _num(x, nd=6):
    """A finite float rounded to `nd` decimals, else None."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return round(x, nd) if math.isfinite(x) else None


def _dig(obj, *keys):
    for k in keys:
        obj = obj.get(k) if isinstance(obj, dict) else None
    return obj


def _pct_text(x, whole=False) -> str:
    """-0.1696 -> "−17.0 %"; whole=True -> "−17 %" (0.1 pp rounding, U+2212, a space before %)."""
    shown = _pp(x)
    text = f"{abs(shown):.0f}" if whole else f"{abs(shown):.1f}"
    return f"{MINUS}{text} %" if shown < 0 else f"{text} %"


def _and(items) -> str:
    items = list(items)
    if not items:
        return ""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _month(ts) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m")


def _month_end(month: str) -> pd.Timestamp:
    return pd.Period(month, "M").to_timestamp(how="end").normalize()


# --- what a computed Result says (the inputs every key reads back) ----------------------------------------------------
def inputs(result: dict) -> dict:
    """The run's own inputs, read back from the Result: today's mix (baseline.portfolio after a move, else the
    portfolio), the evaluated mix after the move (None without one), the moved ticker, amount, floor, horizon, the typed
    answers, the limits as stored (load_limits keeps only their `edited` keys), the families judged, as_of."""
    r = result if isinstance(result, dict) else {}
    sc = r.get("scenario") or {}
    change = sc.get("change") or {}
    has_change = isinstance(_dig(r, "metrics", "after"), dict)
    after = dict(r.get("portfolio") or {}) if has_change else None
    today = dict(_dig(r, "baseline", "portfolio") or r.get("portfolio") or {}) if has_change else dict(r.get("portfolio") or {})
    ticker = (_dig(r, "tipping_point", "ticker") or change.get("ticker")) if has_change else None
    raw = r.get("profile")
    profile = {k: raw[k] for k in ("goal", "horizon_years", "risk", "esg", "crypto", "capacity", "reaction_2022")
               if k in raw} if isinstance(raw, dict) else None
    abstains = bool((sc.get("weather") or {}).get("no_precedent")) and not sc.get("event_ids")
    years = (profile or {}).get("horizon_years")
    return {"today": today, "after": after, "ticker": str(ticker).upper() if ticker else None,
            "weight": (after or {}).get(str(ticker).upper()) if ticker else None, "change": change or None,
            "amount": r.get("amount"), "floor": _dig(r, "limits", "floor"), "limits": r.get("limits"),
            "profile": profile, "horizon_months": int(round(float(years) * 12)) if isinstance(years, (int, float)) and years > 0 else None,
            "families": [] if abstains else list(sc.get("families") or FAMILIES), "as_of": r.get("as_of"),
            "curve": [p for p in (_dig(r, "tipping_point", "curve") or []) if isinstance(p, dict)]}


# --- the trace and the facts (one id space with pipeline.Trace) --------------------------------------------------------
class _Rows:
    """Adds trace rows (and facts keyed by their ids) to a Result, in pipeline.Trace's format."""

    def __init__(self, result):
        self.r = result
        self.r.setdefault("trace", [])
        if not isinstance(self.r.get("facts"), dict):
            self.r["facts"] = {}

    def add(self, tool, *, inputs=None, outputs=None, source="", ms=0) -> str:
        rows = self.r["trace"]
        tid = f"T{len(rows) + 1}"
        rows.append({"id": tid, "step": "COMPARE", "tool": tool, "inputs": inputs or {}, "outputs": outputs or {},
                     "source": source, "as_of": self.r.get("as_of"), "ms": int(ms), "service": "Python", "model": None,
                     "usage": None, "request_id": None})
        return tid

    def fact(self, label, value, unit, entity, kind, *, path, source, key=None) -> str | None:
        """One facts row (a trace row of its own, recipe "result_extras"); None for a missing value."""
        value = _num(value, 10) if unit not in ("count", "CAD", "months") else value
        if value is None or isinstance(value, bool):
            return None
        tid = self.add(f"result_extras.{path.split('.')[0]}", inputs={"path": path, **({"key": key} if key else {}),
                                                                       "recipe": "result_extras"},
                       outputs={"value": value}, source=source)
        self.r["facts"][tid] = {"label": label, "value": value, "unit": unit, "entity": entity,
                                "sign": "negative" if value < 0 else "positive" if value > 0 else "zero", "kind": kind}
        return tid

    def failed(self, key, exc) -> None:
        self.add(f"result_extras.{key}", outputs={"error": f"{type(exc).__name__}: not computed"},
                 source="result_extras (lane B3)")


# --- the deep-history data (the cache may be absent: every deep key is then None) ---------------------------------------
def _deep():
    import tools.deep as deep               # noqa: PLC0415 (the engine's own module; imported when first needed)
    return deep


def _proxy_columns(weights, pmap, panel):
    """({proxy column: summed weight} for the covered lines, [uncovered tickers], covered share of the weight)."""
    cols, missing, covered = {}, [], 0.0
    for ticker, w in (weights or {}).items():
        w = float(w)
        if w <= 1e-12:
            continue
        col = (pmap.get(str(ticker).upper()) or {}).get("proxy")
        if col is None or panel is None or col not in panel.columns:
            missing.append(str(ticker).upper())
            continue
        cols[col] = cols.get(col, 0.0) + w
        covered += w
    return cols, missing, covered


def _cut(panel, as_of):
    """The panel up to the last month whose month-end is on or before as_of (red gate 3)."""
    return panel.loc[: pd.Timestamp(as_of)] if panel is not None else None


def _mix_returns(panel, cols: dict) -> pd.Series:
    """Monthly returns of a constant-weight mix of proxy columns, rebalanced monthly; NaN where a column has none."""
    w = pd.Series(cols, dtype="float64")
    w = w / w.sum()
    return (panel[list(w.index)] * w).sum(axis=1, min_count=len(w))


def _worst_paths(r: np.ndarray, base=True) -> tuple:
    """(depth, peak index, trough index) of the worst fall of one path of monthly returns (index into the level path:
    0 = the base month when `base`)."""
    level = np.concatenate([[1.0], np.cumprod(1.0 + r)]) if base else np.cumprod(1.0 + r)
    high = np.maximum.accumulate(level)
    dd = level / high - 1.0
    t = int(np.argmin(dd))
    p = int(np.argmax(level[: t + 1] == high[t]))
    return float(dd[t]), p, t


def _window_worst(r: np.ndarray, h: int) -> np.ndarray:
    """The worst fall of every h-month window of a return array (base 1.0 before each window's first month)."""
    if len(r) < h:
        return np.array([])
    win = np.lib.stride_tricks.sliding_window_view(r, h)                      # (n, h)
    level = np.concatenate([np.ones((len(win), 1)), np.cumprod(1.0 + win, axis=1)], axis=1)
    return (level / np.maximum.accumulate(level, axis=1) - 1.0).min(axis=1)


# === group 1: the dial and the money (real 2021-26 data, daily, the verdict's own floor rule) =========================
def curve_dollars(result: dict) -> None:
    """In place, on every point of tipping_point.curve: loss_dollars = amount x max_drawdown (whole dollars, negative) and
    floor_margin_pp = round_pp(max_drawdown) - round_pp(floor), in points (positive = held above your floor, 0.0 = held
    at it, negative = beyond it): the dial and the stage read this one key for "touched" (pitfall 5 rounding)."""
    amount, floor = result.get("amount"), _dig(result, "limits", "floor")
    for point in _dig(result, "tipping_point", "curve") or []:
        if isinstance(point, dict) and "max_drawdown" in point:
            point["loss_dollars"] = _dollars(amount, point.get("max_drawdown"))
            dd = point.get("max_drawdown")
            point["floor_margin_pp"] = None if dd is None or floor is None else float(_pp(dd) - _pp(floor))


def floor_class(depth, floor):
    """(class, why) of one fall against your floor, the rule of deep_history's rows for one replay: round_pp both
    (pitfall 5); within 1 point of your floor either side = "touched" (why: "within 1 point of your floor"), else
    "broke" below it or "held" above it. (None, None) when either number is missing."""
    if depth is None or floor is None:
        return None, None
    margin = _pp(depth) - _pp(floor)
    if abs(margin) <= TOUCH_PP:
        return "touched", WHY_NEAR
    return ("broke" if margin < 0 else "held"), None


def turbulence_classes(result: dict) -> None:
    """In place, on every family of result.turbulence (the 2021-26 shocks on the real funds): today_class / after_class
    from worst_today / worst_after by `floor_class`, with *_why and *_floor_margin_pp (rounded points, positive = held
    above), so the page never judges a number against your floor itself (pitfall 5)."""
    floor = _dig(result, "limits", "floor")
    for row in (result.get("turbulence") or {}).values():
        if not isinstance(row, dict):
            continue
        for side in ("today", "after"):
            depth = row.get(f"worst_{side}")
            row[f"{side}_class"], row[f"{side}_why"] = floor_class(depth, floor)
            row[f"{side}_floor_margin_pp"] = None if depth is None or floor is None else float(_pp(depth) - _pp(floor))


def _series(engine, weights, as_of, start=None):
    """The engine's own daily path (tools.portfolio.portfolio_series, the judge's call: own calendar, base 100)."""
    s = engine.portfolio_series(weights, start=start, as_of=as_of)
    return list(s["dates"]), np.asarray(s["values"], dtype="float64")


def _many_paths(market, mixes) -> list:
    """[(dates, values)] for many mixes at once, exactly as tools.portfolio.series_from_market computes each one
    (prices carried forward, the days when one held line's exchange traded, daily returns @ weights, base 100):
    the price work is done once per set of held lines instead of once per mix."""
    out, groups = [None] * len(mixes), {}
    for i, mix in enumerate(mixes):
        held = {str(t).strip().upper(): float(w) for t, w in mix.items() if float(w) > 1e-12}
        groups.setdefault(tuple(sorted(held)), []).append((i, held))
    for cols, members in groups.items():
        prices = market["prices"][list(cols)].ffill()
        prices = prices[market["traded"][list(cols)].any(axis=1)]
        rets = prices.pct_change(fill_method=None).fillna(0.0).to_numpy()
        dates = prices.index.strftime("%Y-%m-%d").tolist()
        for i, held in members:
            daily = rets @ np.array([held[c] for c in cols])
            out[i] = (dates, 100.0 * np.cumprod(1.0 + daily))
    return out


def end_values(result) -> dict | None:
    """What your fictional amount ended at on the last day of the replay: amount x the last level of each path / 100 (the
    Result's own series, base 100), whole dollars, ROUND_HALF_UP; `after` only with a move. So a run with no move has a
    dollar end too (lane u3's race), not only a growth rate."""
    s, amount = result.get("series") or {}, result.get("amount")
    dates, today, after = s.get("dates") or [], s.get("today") or [], s.get("after")
    if not amount or not dates or not today:
        return None
    whole = lambda level: int(Decimal(repr(float(amount * level / 100))).quantize(Decimal("1"), ROUND_HALF_UP))  # noqa: E731
    return {"today": whole(today[-1]), "after": whole(after[-1]) if after else None, "date": dates[-1], "amount": amount,
            "kind": "fiction", "source": "amount × the last value of the Result's own series (base 100)",
            "as_of": result.get("as_of")}


def not_2022(ins, engine) -> dict | None:
    """The worst fall of the mix after the move (today's mix without one) on the dates from 2023-01-01 only."""
    mix, side = (ins["after"], "after") if ins["after"] else (ins["today"], "today")
    if not mix or not ins["as_of"] or ins["as_of"] < FROM_2023:
        return None
    from tools.metrics import risk_metrics         # noqa: PLC0415
    dates, values = _series(engine, mix, ins["as_of"], start=FROM_2023)
    if len(values) < 2:
        return None
    m = risk_metrics({"dates": dates, "values": values.tolist(), "source": ""})
    depth = m["max_drawdown"]
    recovery = None
    if m["trough_date"]:
        i, p = dates.index(m["trough_date"]), dates.index(m["peak_date"])
        back = np.nonzero(values[i + 1:] >= values[p])[0]
        recovery = dates[i + 1 + back[0]] if len(back) else None
    floor = ins["floor"]
    return {"side": side, "from": FROM_2023, "to": dates[-1], "depth": depth, "peak_date": m["peak_date"],
            "trough_date": m["trough_date"], "recovery_date": recovery, "loss_dollars": _dollars(ins["amount"], depth),
            "amount": ins["amount"], "floor": floor, "beyond_floor": None if floor is None else _beyond(depth, floor),
            "kind": "fact", "source": SOURCES["not_2022"], "as_of": ins["as_of"]}


def tipping_band(ins, engine) -> dict | None:
    """The first curve size whose worst fall breaks the floor (the verdict's rule after 0.1 pp rounding, pitfall 5), for
    each start month Nov 2021 ... Nov 2023: a path from the first trading day of that month to as_of. With daily
    rebalancing a later start is the same path cut there, so each size's path is computed once. lo/hi = the smallest and
    largest first-breaking size over the start months that break at all; `holds` = the start months where no size up
    to the asked one breaks it (their first_break is None)."""
    if not ins["after"] or not ins["ticker"] or ins["floor"] is None or len(ins["curve"]) < 2:
        return None
    weights = [p["weight"] for p in ins["curve"]]
    mixes = [engine.apply_change(ins["today"], {"op": "set", "ticker": ins["ticker"], "weight": w, "from_ticker": None})
             for w in weights]
    paths = _many_paths(engine.load_market(ins["as_of"]), mixes)
    days = [np.array(d, dtype="datetime64[D]") for d, _ in paths]
    first_month = pd.Period(BAND_STARTS[0], "M")
    months = pd.period_range(max(first_month, pd.Period(paths[0][0][0], "M")),
                             min(pd.Period(BAND_STARTS[1], "M"), pd.Period(paths[0][0][-1], "M")), freq="M")
    starts = []
    for m in months:
        day0 = np.datetime64(m.to_timestamp().strftime("%Y-%m-%d"), "D")
        rows = []
        for (d, v), when, w in zip(paths, days, weights):
            seg = v[int(np.searchsorted(when, day0)):]
            rows.append((w, float((seg / np.maximum.accumulate(seg) - 1.0).min()) if len(seg) else 0.0))
        hit = next(((w, x) for w, x in rows if _beyond(x, ins["floor"])), None)
        starts.append({"start": str(m), "first_day": paths[0][0][int(np.searchsorted(days[0], day0))],
                       "first_break": None if hit is None else hit[0],
                       "depth_at_break": None if hit is None else hit[1],
                       "depth_at_asked": rows[-1][1]})
    breaking = [s["first_break"] for s in starts if s["first_break"] is not None]
    return {"ticker": ins["ticker"], "rule": "max_drawdown", "floor": ins["floor"],
            "lo": min(breaking) if breaking else None, "hi": max(breaking) if breaking else None,
            "holds": [s["start"] for s in starts if s["first_break"] is None], "n_starts": len(starts),
            "asked": weights[-1], "starts": starts, "kind": "fact", "source": SOURCES["band"], "as_of": ins["as_of"]}


# === group 2: the AI's work and the evidence ========================================================================
def _judged(scenario):
    """The mix and the shocks a reading hands the judge (as proofs._judged): (sorted mix items | None, families)."""
    move = bool(scenario.get("change") and scenario.get("portfolio"))
    mix = tuple(sorted((str(k), round(float(v), 9)) for k, v in scenario["portfolio"].items())) if move else None
    return mix, frozenset(scenario.get("families") or FAMILIES)


def _titles(result, ids):
    by_id = {e.get("event_id"): e for e in result.get("events") or [] if isinstance(e, dict)}
    return [{"event_id": i, "title": (by_id.get(i) or {}).get("title"), "date": (by_id.get(i) or {}).get("date")}
            for i in ids]


_READING_KEYS = ("type", "families", "event_ids", "reasons", "change", "portfolio", "clarify", "clarify_reason",
                 "weather", "method")                # pipeline._READING_KEYS: what the keyword rules alone read


def _keyword_reading(result, ins, engine) -> dict:
    """agents.scenario.keyword_fallback on the run's own inputs (the question, today's mix, the shocks known at as_of,
    the typed answers, the limits, the universe and today's exposure as OBSERVE gave it), as pipeline._switch_off
    reads it. No model is called."""
    div, risk = _dig(result, "diversification", "today") or {}, _dig(result, "risk", "today") or {}
    exposure = {"countries": dict(div.get("countries") or {}), "currencies": dict(div.get("currencies") or {}),
                "sectors": dict(div.get("sectors") or {}), "risk_shares": dict(risk.get("shares") or {})}
    kw = engine.keyword_fallback(result.get("question"), ins["today"], engine.load_events(ins["as_of"]), ins["as_of"],
                                 profile=ins["profile"], limits=ins["limits"], universe=engine.load_universe(),
                                 exposure=exposure, amount=ins["amount"]) or {}
    return {k: kw.get(k) for k in _READING_KEYS}


def navigator_effect(result, ins, engine) -> dict | None:
    """proofs.navigator_effect(the navigator's reading, the keyword rules' reading of the same words) for a run the
    navigator answered (None otherwise). The keyword reading is the one the run kept (scenario.keyword_result); when it
    hands the judge another mix or other shocks, the judge runs on that reading (proofs case 1), never lending it the
    navigator's verdict. `added` / `dropped`: the precedents only the navigator / only the keywords picked, titled."""
    sc = result.get("scenario") or {}
    if sc.get("method") != "bedrock":
        return None
    kw = sc.get("keyword_result")
    if not isinstance(kw, dict):                   # a run saved before the reading was kept: read it now, offline
        kw = _keyword_reading(result, ins, engine)
    from proofs import navigator_effect as effect          # noqa: PLC0415
    checks = result.get("checks") or []
    nav = {"scenario": sc, "verdict": result.get("verdict"), "binding_rule": engine.binding_rule(checks) if checks else None,
           "checks": checks}
    fb = {"scenario": kw}
    if not kw.get("clarify") and _judged(sc) != _judged(kw) and ins["profile"]:
        mix = dict(kw["portfolio"]) if kw.get("change") and kw.get("portfolio") else ins["today"]
        ev = engine.evaluate(ins["profile"], mix, list(kw.get("families") or FAMILIES), ins["as_of"],
                             limits=ins["limits"], amount=ins["amount"])
        if isinstance(ev, dict) and not ev.get("error"):
            fb.update(verdict=ev.get("verdict"), binding_rule=engine.binding_rule(ev.get("checks") or []),
                      checks=ev.get("checks"))
    out = effect(nav, fb)
    nav_ids, kw_ids = list(sc.get("event_ids") or []), list(kw.get("event_ids") or [])
    out.update(added=_titles(result, [i for i in nav_ids if i not in kw_ids]),
               dropped=_titles(result, [i for i in kw_ids if i not in nav_ids]),
               navigator={"families": list(sc.get("families") or []), "event_ids": nav_ids, "change": sc.get("change")},
               label="What the navigator changed in this run", source=SOURCES["navigator"], as_of=ins["as_of"])
    return out


def evidence(result) -> dict:
    """{fact_id: rows} for every fact: proofs.evidence_rows with no market bundle, so only the portfolio's own values
    (base 100, read from the Result's series) can appear; never a licensed per-asset price or rate (red gate 8)."""
    from proofs import evidence_rows                       # noqa: PLC0415
    return {fid: evidence_rows(fid, result, None) for fid in (result.get("facts") or {})}


# === group 3: the ladder and the outside world (real 2021-26 data) ==================================================
def _same_mix(a, b) -> bool:
    a, b = a or {}, b or {}
    return set(a) == set(b) and all(abs(float(a[k]) - float(b[k])) <= 1e-9 for k in a)


def ladder(ins, engine, own_run=None) -> dict | None:
    """R11: the move's own weight put in SPY, in QQQ and in the moved ticker instead (tools.portfolio.apply_change, the
    one weight operator), each judged by governance.evaluate with the run's limits and shocks: worst fall, its dollars,
    the end value of the amount, the verdict and the rule that decided it. `own_run` ({metrics, series, verdict,
    checks} of the run itself) answers the moved ticker's row when it is the run's own mix (the same judge on the same
    inputs gives the same answer), so only SPY and QQQ are judged again."""
    if not ins["after"] or not ins["ticker"] or ins["weight"] is None or not ins["profile"] or not ins["amount"]:
        return None
    w, names, rows = float(ins["weight"]), {}, []
    try:
        uni = engine.load_universe()
        names = dict(zip(uni["ticker"], uni["name"]))
    except Exception:                                      # names are a label only
        pass
    for ticker, label in [*LADDER, (ins["ticker"], None)]:
        if any(r["ticker"] == ticker for r in rows):
            continue
        mix = engine.apply_change(ins["today"], {"op": "set", "ticker": ticker, "weight": w, "from_ticker": None})
        own = ticker == ins["ticker"] and own_run is not None and _same_mix(mix, ins["after"])
        ev = own_run if own else engine.evaluate(ins["profile"], mix, ins["families"], ins["as_of"], limits=ins["limits"],
                                                 amount=ins["amount"])
        if not isinstance(ev, dict) or ev.get("error"):
            rows.append({"ticker": ticker, "error": (ev or {}).get("error") or "not computed"})
            continue
        m, values = ev["metrics"], ev["series"]["values"]
        rows.append({"ticker": ticker, "name": names.get(ticker), "label": label, "is_move": ticker == ins["ticker"],
                     "weight": w, "max_drawdown": m["max_drawdown"], "peak_date": m["peak_date"],
                     "trough_date": m["trough_date"], "loss_dollars": _dollars(ins["amount"], m["max_drawdown"]),
                     "end_value": int(Decimal(repr(float(ins["amount"] * values[-1] / 100))).quantize(Decimal("1"), ROUND_HALF_UP)),
                     "cagr": m["cagr"], "verdict": ev.get("verdict"), "binding_rule": engine.binding_rule(ev.get("checks") or []),
                     "beyond_floor": None if ins["floor"] is None else _beyond(m["max_drawdown"], ins["floor"])})
    return {"weight": w, "families": ins["families"], "amount": ins["amount"], "rows": rows, "kind": "fact",
            "source": SOURCES["ladder"], "as_of": ins["as_of"]}


def period_text(window: str) -> str:
    """The issuer's window label (tests/test_metrics.py ISSUER) as the page says it: "YTD to D, NAV" -> "Year to date to D
    (NAV)"; "1 year to D, market" -> "1 year to D (market price)"; "3 years a year to D, market" -> "Per year over the 3
    years to D (market price)"."""
    span, _, basis = window.partition(", ")
    basis = {"NAV": "NAV", "market": "market price"}.get(basis.strip(), basis.strip())
    if span.startswith("YTD to "):
        span = "Year to date to " + span[len("YTD to "):]
    elif span.startswith("3 years a year to "):
        span = "Per year over the 3 years to " + span[len("3 years a year to "):]
    return f"{span} ({basis})" if basis else span


def _pct2(points) -> str:
    return f"{MINUS}{abs(points):.2f} %" if points < 0 else f"{points:.2f} %"


def reconciliation(ins, engine) -> dict | None:
    """R12: our total return of four funds beside the figure the issuer publishes (RECONCILIATION): ours = the last
    adjusted close in the listing currency on or before the end date over the one on or before the start date, a "3
    years a year" row annualised. Rows ending after as_of are left out (red gate 3). `ours` and `published` are
    fractions; `gap_pp` is in points (ours - published)."""
    if not ins["as_of"]:
        return None
    local = engine.load_market(ins["as_of"])["local"]
    rows = []
    for ticker, start, end, window, published, url in RECONCILIATION:
        if end > ins["as_of"] or ticker not in local:
            continue
        px = local[ticker].dropna()
        r = float(px[:end].iloc[-1] / px[:start].iloc[-1] - 1)
        if window.startswith("3 years"):
            r = (1 + r) ** (1 / 3) - 1
        ours = round(100 * r, 2)
        rows.append({"ticker": ticker, "start": start, "end": end, "period": period_text(window), "window": window,
                     "basis": "NAV" if "NAV" in window else "market price", "ours": round(r, 6),
                     "published": round(published / 100, 6), "gap_pp": round(ours - published, 2),
                     "ours_text": _pct2(ours), "published_text": _pct2(published),
                     "ok": abs(ours - published) <= RECONCILIATION_TOLERANCE_PP + 1e-9, "source_url": url,
                     "read_on": RECONCILIATION_READ_ON})
    return {"rows": rows, "n": len(rows), "within": sum(r["ok"] for r in rows), "tolerance_pp": RECONCILIATION_TOLERANCE_PP,
            "kind": "fact", "source": SOURCES["reconciliation"], "as_of": ins["as_of"]}


# === group 4: deep history by proxy (◐ assumption; never the verdict, the hero or the dial: R5) ======================
PANEL_ENV = "EPICENTRE_DEEP_PANEL"     # a panel.csv elsewhere (a worktree without its own gitignored data/cache/deep)
REPO_ROOT = Path(__file__).resolve().parent


def deep_dir() -> Path:
    """Where the deep cache is: the folder of $EPICENTRE_DEEP_PANEL when it names a file, else this checkout's own
    data/cache/deep, resolved from this file (never from the working directory)."""
    env = os.environ.get(PANEL_ENV, "").strip()
    if env and Path(env).expanduser().is_file():
        return Path(env).expanduser().resolve().parent
    return REPO_ROOT / "data" / "cache" / "deep"


def deep_inputs(ins, engine, *, panel=None, proxy_map=None, episodes=None) -> dict:
    """The panel, the proxy map, the 11 episodes and the market bundle (for the proxy check); {"panel": None} when the
    deep cache is absent (the app works without it)."""
    d = _deep()
    panel = d.load_panel(path=deep_dir() / "panel.csv") if panel is None else panel
    if panel is None:
        return {"panel": None}
    return {"mod": d, "panel": panel, "pmap": d.load_proxy_map() if proxy_map is None else proxy_map,
            "episodes": d.load_episodes() if episodes is None else episodes, "market": engine.load_market(ins["as_of"]),
            "engine": engine}


def _raw_dir():
    return deep_dir() / "raw"


_EW_TABLE = "Average Equal Weighted Returns -- Monthly"
_EW_COLUMNS = {"french_49/49_Industry_Portfolios_CSV.zip": {"CHIPS": "Chips", "SOFTW": "Softw", "HARDW": "Hardw",
                                                            "RTAIL": "Rtail", "AUTOS": "Autos", "BANKS": "Banks",
                                                            "DRUGS": "Drugs", "HSHLD": "Hshld", "OIL": "Oil"},
               "french_12/12_Industry_Portfolios_CSV.zip": {"BUSEQ": "BusEq"}}


def _read_french_table(zip_path, title, columns) -> pd.DataFrame:
    """One named monthly table of a Fama/French CSV zip (e.g. the equal-weighted one), as fractions, month-end index;
    -99.99 / -999 are NaN. Read with zipfile and pandas only (untrusted download)."""
    d = _deep()
    lines = d._read_zip(zip_path).decode("latin-1").splitlines()
    at = next(i for i, line in enumerate(lines) if line.strip() == title)
    head = next(i for i in range(at, len(lines)) if lines[i].startswith(","))
    names = [c.strip() for c in lines[head].split(",")[1:]]
    rows = []
    for line in lines[head + 1:]:
        cells = [c.strip() for c in line.split(",")]
        if not (cells and len(cells[0]) == 6 and cells[0].isdigit()):
            break
        rows.append(cells)
    table = pd.DataFrame([[float(c) for c in r[1:len(names) + 1]] for r in rows], columns=names,
                         index=d._month_end([f"{r[0][:4]}-{r[0][4:]}" for r in rows]))
    return table[list(columns)].mask(table[list(columns)] <= -99.99) / 100.0


_EW_CACHE = {}


def equal_weighted_panel(panel):
    """The panel with every US industry proxy replaced by its EQUAL-weighted Fama/French return in CAD (x the same
    month-end USD/CAD move the panel uses); the market, Canada, bonds, bills and gold are unchanged (Fama/French publish
    no equal-weighted market factor). None when the raw downloads are not on this machine."""
    raw = _raw_dir()
    key = (str(raw), panel.shape, str(panel.index[0]), str(panel.index[-1]), float(np.nansum(panel.to_numpy())))
    if key in _EW_CACHE:
        return _EW_CACHE[key]
    _EW_CACHE.clear()                                       # one panel at a time (the server reloads it per run)
    out = None
    if all((raw / f).exists() for f in _EW_COLUMNS):
        fx = panel["USDCAD_END"]
        fx_move = fx / fx.shift(1) - 1
        out = panel.copy()
        for f, cols in _EW_COLUMNS.items():
            ew = _read_french_table(raw / f, _EW_TABLE, list(cols.values()))
            for pid, col in cols.items():
                usd = ew[col].reindex(panel.index)
                out[pid] = (1 + usd) * (1 + fx_move) - 1
    _EW_CACHE[key] = out
    return out


_ARRAYS = {}


def _array(panel):
    """The panel as (values, {"YYYY-MM": row}, {column: index}, ["YYYY-MM"]) for fast month slices; the last few panels
    only (a run makes two: as sourced and equal-weighted)."""
    key = id(panel)
    hit = _ARRAYS.get(key)
    if hit is not None and hit[0] is panel:
        return hit[1]
    months = [_month(m) for m in panel.index]
    out = (panel.to_numpy(dtype="float64"), {m: i for i, m in enumerate(months)},
           {c: j for j, c in enumerate(panel.columns)}, months)
    if len(_ARRAYS) > 4:
        _ARRAYS.clear()
    _ARRAYS[key] = (panel, out)
    return out


def _episode_depth(panel, cols, start, end, cut):
    """(depth, trough "YYYY-MM") of a mix of proxy columns over the months start..end, base 1.0 at the month-end before
    `start`, rebalanced monthly (tools.deep.episode_replay's numbers); None when a month is missing or `end` > cut."""
    if not cols or _month_end(end) > cut:
        return None
    values, rows, where, months = _array(panel)
    i, j = rows.get(start), rows.get(end)
    n = (pd.Period(end, "M") - pd.Period(start, "M")).n + 1
    if i is None or j is None or j - i + 1 != n or any(c not in where for c in cols):
        return None
    w = np.array([float(x) for x in cols.values()])
    block = values[i:j + 1, [where[c] for c in cols]]
    if np.isnan(block).any():
        return None
    depth, _, trough = _worst_paths(block @ (w / w.sum()))
    return depth, months[i + trough - 1] if trough > 0 else months[i]


def _shift(month: str, n: int) -> str:
    return str(pd.Period(month, "M") + n)


def _detail(record):
    if not record:
        return None
    if not record.get("replayable"):
        return {"replayable": False, "uncovered": record.get("uncovered") or []}
    return {"replayable": True, "peak": record["peak"], "trough": record["trough"], "loss_dollars": record["loss_dollars"],
            "recovery_months": record["recovery_months"]}


def _depth(record):
    return record["depth"] if record and record.get("replayable") else None


def deep_history(ins, deep) -> dict | None:
    """The 11 sourced crises (data/deep_episodes.csv) by proxy: tools.deep.deep_history's fragment (its replays, its
    proxy check, its counts and its sentence), each episode also carrying the moved ticker's proxy alone and each side
    classified broke / touched / held (R11), plus the gentle case and the claims that survive the sensitivity runs."""
    d, panel, pmap, eps = deep["mod"], deep["panel"], deep["pmap"], deep["episodes"]
    floor, amount, ticker = ins["floor"], ins["amount"], ins["ticker"]
    if floor is None or not amount:
        return None
    frag = d.deep_history(ins["today"], ins["after"], ins["as_of"], amount=amount, floor=floor, market=deep["market"],
                          panel=panel, episodes=eps, proxy_map=pmap)
    if frag is None:
        return None
    src = {e["episode_id"]: e for e in eps}
    cut = min(pd.Timestamp(ins["as_of"]), d._end_of(d.DEEP_END))
    col = (pmap.get(ticker) or {}).get("proxy") if ticker else None
    cut_panel, rows = panel.loc[:cut], []
    for row in frag["episodes"]:
        e = src[row["episode_id"]]
        alone = _episode_depth(cut_panel, {col: 1.0}, e["start"], e["end"], cut) if col in panel.columns else None
        t, a, s = _depth(row["today"]), _depth(row["after"]), None if alone is None else alone[0]
        rows.append({"id": row["episode_id"], "title": row["title"], "start": row["start"], "end": row["end"],
                     "trigger_date": e.get("trigger_date"), "kind": row["kind"], "family": row["family"],
                     "place": row["place"], "lat": row["lat"], "lon": row["lon"], "source_url": row["source_url"],
                     "source_title": e.get("source_title"), "today": t, "after": a, "proxy_alone": s,
                     "today_class": None, "after_class": None, "today_why": None, "after_why": None,
                     "direction": None, "move_worse": None,
                     "today_detail": _detail(row["today"]), "after_detail": _detail(row["after"]),
                     "alone_trough": None if alone is None else alone[1]})
    out = {"episodes": rows, "floor": floor, "amount": amount,
           "moved": None if not ticker else {"ticker": ticker, "weight": ins["weight"], "proxy": col,
                                             "label": PROXY_LABEL.get(col) or (pmap.get(ticker) or {}).get("label")},
           "proxy_check": frag["proxy"], "summary": frag["summary"], "sentence": frag["sentence"],
           "frequency": frag["frequency"], "window": frag["window"], "in_verdict": False, "kind": "assumption",
           "source": frag["source"], "as_of": frag["as_of"]}
    if all(r["today"] is None for r in rows):
        gone = sorted({x for r in rows for x in ((r["today_detail"] or {}).get("uncovered") or [])})
        out.update(status="cant_say", reason=f"no history before Nov 2021 for {_and(gone) or 'your mix'}: Can’t say",
                   counts=_counts(rows, ins), gentle_case=None, robust_claims=None)
        return out
    claims = robust_claims(ins, deep, rows)
    by_id = {x["id"]: x for x in claims["rows"]}
    for r in rows:                         # ONE classification: the table shows exactly what the sentence counts
        rc = by_id[r["id"]]
        for side in ("today", "after"):
            r[f"{side}_class"], r[f"{side}_why"] = rc[side]["status"], rc[side]["why"]
        r["direction"] = rc["direction"]
        r["move_worse"] = None if rc["direction"] is None else rc["direction"] == "further"
    out.update(status="ok", reason=None, counts=_counts(rows, ins), gentle_case=gentle_case(ins, deep), robust_claims=claims)
    return out


def _counts(rows, ins) -> dict:
    """The table's counts, from the rows' one classification (broke / touched / held) and their direction."""
    counts = {"n": len(rows)}
    for side in ("today", "after"):
        if side == "after" and ins["after"] is None:
            counts.update({f"after_{k}": None for k in ("broke", "touched", "held", "replayable")})
            continue
        classes = [r[f"{side}_class"] for r in rows]
        counts.update({f"{side}_broke": classes.count("broke"), f"{side}_touched": classes.count("touched"),
                       f"{side}_held": classes.count("held"), f"{side}_replayable": sum(c is not None for c in classes)})
    dirs = [r["direction"] for r in rows]
    known = ins["after"] is not None
    counts.update(move_worse=dirs.count("further") if known else None,
                  move_no_worse=dirs.count("no_further") if known else None,
                  move_close=sum(1 for r in rows if r["direction"] is None and r["today"] is not None
                                 and r["after"] is not None) if known else None)
    return counts


VARIANTS = (("base", "the episode windows as sourced"), ("start-12", "each window starting 12 months earlier"),
            ("end+12", "each window ending 12 months later"), ("equal", "equal-weighted industries"))


WHY = {"near": WHY_NEAR, "runs": "changes with the window or the weighting",
       "floor": "changes with your floor 2 points either side"}


def _robust_status(depths, floor):
    """ONE classification for a side of a crisis (rows, counts and sentence all use it): "broke" when it broke by more
    than 1 point in every run even at the looser floor; "held" when it held in every run even at the tighter floor;
    else "touched" (too close to call), with why. Decided on the runs that could be replayed (the sourced run must be);
    None when the sourced run cannot be."""
    if not depths or depths[0] is None:
        return None, None
    avail = [x for x in depths if x is not None]
    if all(classify(x, floor - SENS_FLOOR) == "broke" for x in avail):
        return "broke", None
    if all(classify(x, floor + SENS_FLOOR) == "held" for x in avail):
        return "held", None
    if abs(_pp(floor) - _pp(depths[0])) <= TOUCH_PP:
        return "touched", "near"
    return "touched", "runs" if len({_beyond(x, floor) for x in avail}) > 1 else "floor"


def robust_claims(ins, deep, rows) -> dict | None:
    """R11: only the directions that survive the sensitivity runs. Each episode is replayed four ways (as sourced; the
    window 12 months earlier at its start; 12 months later at its end; equal-weighted industries) and judged against
    three floors (yours and 2 points either side), by `_robust_status` (broke / held / touched). The move "fell
    further" / "no further" than your mix today only when every run agrees."""
    panel, pmap, floor = deep["panel"], deep["pmap"], ins["floor"]
    d = _deep()
    cut = min(pd.Timestamp(ins["as_of"]), d._end_of(d.DEEP_END))
    ew = equal_weighted_panel(panel)
    runs = [(vid, panel, a, b) for vid, a, b in (("base", 0, 0), ("start-12", -SENS_MONTHS, 0), ("end+12", 0, SENS_MONTHS))]
    if ew is not None:
        runs.append(("equal", ew, 0, 0))
    loose, tight = floor - SENS_FLOOR, floor + SENS_FLOOR
    cols = {}
    for side, mix in (("today", ins["today"]), ("after", ins["after"])):
        c, missing, _ = _proxy_columns(mix, pmap, panel) if mix else ({}, [], 0)
        cols[side] = None if (missing or not c) else c
    src = {e["episode_id"]: e for e in deep["episodes"]}
    out_rows = []
    for row in rows:
        e, rec = src[row["id"]], {"id": row["id"], "title": row["title"], "kind": row["kind"]}
        depth = {}
        for side in ("today", "after"):
            got = [None if cols[side] is None else _episode_depth(p, cols[side], _shift(e["start"], a), _shift(e["end"], b), cut)
                   for _, p, a, b in runs]
            depth[side] = [g[0] if g else None for g in got]
            status, why = _robust_status(depth[side], floor)
            rec[side] = {"status": status, "why": WHY.get(why), "depths": depth[side],
                         "runs": sum(x is not None for x in depth[side]),
                         "trough": got[0][1] if got and got[0] else None,
                         "margin_pp": None if depth[side][0] is None else float(_pp(floor) - _pp(depth[side][0]))}
        pairs = [(a, b) for a, b in zip(depth["today"], depth["after"]) if a is not None and b is not None]
        if depth["today"][0] is not None and depth["after"][0] is not None:
            rec["direction"] = ("further" if all(_pp(b) < _pp(a) for a, b in pairs)
                                else "no_further" if all(_pp(b) >= _pp(a) for a, b in pairs) else None)
        else:
            rec["direction"] = None
        out_rows.append(rec)
    return _claims(ins, deep, out_rows, [v for v in VARIANTS if v[0] in {r[0] for r in runs}], (loose, floor, tight))


def _whole_pp(x) -> int:
    return int(Decimal(repr(float(x))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _claims(ins, deep, rows, variants, floors) -> dict:
    """The claims and the code-written headline sentence (past tense; every number a key of this block)."""
    has_after, n = ins["after"] is not None, len(rows)
    pick = lambda side, status: [r for r in rows if r[side]["status"] == status]   # noqa: E731
    a_broke, a_held = (pick("after", "broke"), pick("after", "held")) if has_after else ([], [])
    no_further = [r for r in rows if r.get("direction") == "no_further"]
    further = [r for r in rows if r.get("direction") == "further"]
    t_broke, t_held, t_close = pick("today", "broke"), pick("today", "held"), pick("today", "touched")
    year = lambda r, side: (r[side]["trough"] or "")[:4]                             # noqa: E731
    claims, parts = [], []
    col = (deep["pmap"].get(ins["ticker"]) or {}).get("proxy") if ins["ticker"] else None
    label = PROXY_LABEL.get(col, "its stand-in")
    if a_broke:
        margins = [r["after"]["margin_pp"] for r in a_broke]
        lo, hi = _whole_pp(min(margins)), _whole_pp(max(margins))
        years = sorted({year(r, "after") for r in a_broke})
        claims.append({"id": "after_broke", "episodes": [r["id"] for r in a_broke], "years": years, "lo_pp": lo, "hi_pp": hi})
        by = f"by {lo} points" if lo == hi else f"by {lo} to {hi} points"
        parts.append(f"broke your floor {by} in {_and(years)}")
    if no_further:
        years = [year(r, "after") for r in no_further]
        rate = {r["kind"] for r in no_further} == {"rate_shock"}
        claims.append({"id": "no_further", "episodes": [r["id"] for r in no_further], "years": years, "n": len(no_further)})
        what = (f"the {len(no_further)} rate shocks" if rate and len(no_further) > 1 else
                "the rate shock" if rate else f"{len(no_further)} {'crisis' if len(no_further) == 1 else 'crises'}")
        parts.append(f"fell no further than your mix today in {what} ({_and(years)})")
    today = []
    if t_broke:
        years = sorted({year(r, "today") for r in t_broke})
        claims.append({"id": "today_broke", "episodes": [r["id"] for r in t_broke], "years": years, "n": len(t_broke)})
        today.append(f"broke it by more than 1 point in {_and(years)}")
    if t_held:
        claims.append({"id": "today_held", "episodes": [r["id"] for r in t_held], "n": len(t_held)})
        today.append(f"held in {len(t_held)}")
    if t_close:
        years = sorted({year(r, "today") for r in t_close})
        claims.append({"id": "today_touched", "episodes": [r["id"] for r in t_close], "years": years, "n": len(t_close)})
        today.append(f"came within reach of your floor in {len(t_close)} ({_and(years)}): too close to call")
    if a_held:
        claims.append({"id": "after_held", "episodes": [r["id"] for r in a_held], "n": len(a_held)})
    if further:
        claims.append({"id": "further", "episodes": [r["id"] for r in further], "n": len(further)})
    if parts:
        lead = f"with {_pct_text(ins['weight'], whole=True)} in {label}, your mix "
        sentence = f"By proxy, in the {n} earlier crises: " + lead + "; it ".join(parts) + "." + (
            " Your mix today " + _and(today) + "." if today else "")
    elif today:
        sentence = f"By proxy, in the {n} earlier crises, your mix today " + _and(today) + "."
    else:
        sentence = "By proxy, no direction held in every sensitivity run, so the table is shown without a headline."
    tested = "; ".join(label for _, label in variants)
    return {"sentence": sentence, "claims": claims, "rows": rows, "variants": [{"id": v, "label": l} for v, l in variants],
            "floors": list(floors), "test": (f"Each statement held in every run: your floor and 2 points either side; {tested}."
                                             if claims else ""),
            "n": n, "kind": "assumption"}


def _monthly_real(prices, mix, start, end):
    """The real mix on month-end CAD prices (rebalanced monthly), months start+1..end, base = the end of `start`."""
    held = {t: float(w) for t, w in mix.items() if float(w) > 1e-12}
    px = prices[list(held)]
    monthly = px.groupby(px.index.to_period("M")).last()
    monthly = monthly.loc[pd.Period(start, "M"):pd.Period(end, "M")]
    r = monthly.pct_change(fill_method=None).iloc[1:]
    if r.isna().to_numpy().any() or not len(r):
        return None
    w = pd.Series(held) / sum(held.values())
    depth, p, t = _worst_paths((r * w).sum(axis=1).to_numpy())
    months = [str(monthly.index[0]), *[str(m) for m in r.index]]
    return {"depth": depth, "peak": months[p], "trough": months[t]}


def gentle_case(ins, deep) -> dict | None:
    """The moved ticker alone on the overlap months, real (month-end CAD prices) beside its stand-in: the stand-in is an
    industry or an index, and one company can fall further than its industry (the gentle case)."""
    ticker, start, end = ins["ticker"], *VALIDATION
    col = (deep["pmap"].get(ticker) or {}).get("proxy") if ticker else None
    prices = deep["market"]["prices"]
    if not col or ticker not in prices.columns or col not in deep["panel"].columns:
        return None
    cut = deep["panel"].loc[: pd.Timestamp(ins["as_of"])]
    end = min(pd.Period(end, "M"), cut[col].last_valid_index().to_period("M"))
    real = _monthly_real(prices, {ticker: 1.0}, start, str(end))
    proxy = _episode_depth(cut, {col: 1.0}, _shift(start, 1), str(end), cut.index[-1])
    if real is None or proxy is None:
        return None
    uni = deep["market"].get("universe")
    kind = None
    if isinstance(uni, pd.DataFrame) and "asset_class" in uni:
        hit = uni.loc[uni["ticker"] == ticker, "asset_class"]
        kind = str(hit.iloc[0]) if len(hit) else None
    return {"ticker": ticker, "proxy": col, "label": PROXY_LABEL.get(col), "asset_class": kind,
            "window": {"start": start, "end": str(end)}, "real": real["depth"], "real_peak": real["peak"],
            "real_trough": real["trough"], "stand_in": proxy[0], "stand_in_trough": proxy[1],
            "gentler": bool(proxy[0] > real["depth"]), "kind": "assumption", "frequency": "monthly"}


_CANADA = {}


def canada_series(panel) -> dict:
    """R11: the Canada line checked. Fama/French Canada is read from its LOCAL-currency block (CAD) and starts 1977-01;
    the months before are the TSX composite close plus the previous month's dividend yield / 12 (Statistics Canada
    10-10-0125-01, CAD). The splice is compared with Fama/French on the months both have."""
    if "out" in _CANADA:
        return _CANADA["out"]
    d, raw = _deep(), _raw_dir()
    s = panel["CA_EQ"].dropna()
    out = {"panel_first": _month(s.index[0]), "panel_last": _month(s.index[-1]), "french_first": None,
           "currency": "CAD: the local-currency block of Fama/French Canada; the TSX splice is in CAD",
           "splice": {"to": _month(d._CANADA_FROM - pd.offsets.MonthEnd(1)),
                      "source": "Statistics Canada 10-10-0125-01: TSX composite close + the previous month’s dividend yield / 12"},
           "splice_check": None}
    try:
        french = d.read_french_country(raw / "french_countries/F-F_International_Countries.zip").dropna()
        tsx = d.read_statcan(raw / "statcan_10100125/10100125-eng.zip", ["v122620", "v122628"])
        early = (tsx["v122620"] / tsx["v122620"].shift(1) - 1 + tsx["v122628"].shift(1) / 100 / 12).dropna()
        both = pd.concat({"tsx": early, "ff": french}, axis=1).dropna()
        out["french_first"] = _month(french.index[0])
        if len(both) >= 24:
            out["splice_check"] = {"months": len(both), "start": _month(both.index[0]), "end": _month(both.index[-1]),
                                   "corr": round(float(both["tsx"].corr(both["ff"])), 4),
                                   "mean_gap_pp": round(float((both["tsx"] - both["ff"]).mean() * 100), 3)}
    except Exception:                                       # noqa: BLE001 (the raw files may be absent: say nothing)
        pass
    _CANADA["out"] = out
    return out


NOTES = ("Monthly month-end returns in CAD, constant weights rebalanced monthly; the real engine is daily and rebalanced daily.",
         "US lines: Fama/French returns x the month-end USD/CAD move (FRED DEXCAUS).",
         "Gold: the World Bank’s monthly AVERAGE price x the monthly-average USD/CAD (FRED EXCAUS); no month-end gold "
         "price is in the panel, and averages smooth gold’s falls.",
         "Bonds: a Government of Canada par-bond ladder (2, 4, 7.5 and 20 years) from Statistics Canada 10-10-0122-01 "
         "yields; T-bills earn the previous month’s 3-month yield / 12. Government bonds only: credit is not replayed.",
         "A single company is replayed as its US industry, which falls less than one company can: a lower bound, never "
         "the company’s own history.")


def deep_validation(result, ins, deep) -> dict | None:
    """R11: the proxies run over 2021-11 -> 2025-12 beside the real engine. `*_real` = the verdict's own worst fall
    (daily, the whole run); `*_real_window` = the engine's daily path cut to the same months; `*_real_monthly` = the real
    lines on month-end CAD prices; `*_proxy` = the stand-ins. gap_pp = proxy - real (points; > 0: the proxy fell less)."""
    p, pmap, market = deep["panel"], deep["pmap"], deep["market"]
    start, end = VALIDATION
    as_of = pd.Timestamp(ins["as_of"])
    end = str(min(pd.Period(end, "M"), (as_of + pd.offsets.Day(1)).to_period("M") - 1))
    out = {"window": {"start": start, "end": end}, "gap_pp": {}, "within_2pp": {}, "covered": {}}
    for side, mix in (("today", ins["today"]), ("after", ins["after"])):
        keys = [f"{side}_real", f"{side}_real_window", f"{side}_real_monthly", f"{side}_proxy"]
        if not mix:
            out.update(dict.fromkeys(keys))
            continue
        real = _dig(result, "metrics", side, "max_drawdown")
        dates, values = _series(deep["engine"], mix, ins["as_of"])
        keep = [i for i, day in enumerate(dates) if day <= _month_end(end).strftime("%Y-%m-%d")]
        seg = values[keep] if keep else values[:0]
        window = float((seg / np.maximum.accumulate(seg) - 1.0).min()) if len(seg) else None
        cols, missing, covered = _proxy_columns(mix, pmap, p)
        total = sum(float(w) for w in mix.values() if float(w) > 1e-12)
        share = covered / total if total else 0.0
        proxy = _episode_depth(p.loc[:as_of], cols, _shift(start, 1), end, as_of) if share >= COVERED_MIN - 1e-9 else None
        monthly = _monthly_real(market["prices"], {t: w for t, w in mix.items() if t.upper() not in missing}, start, end) \
            if share >= COVERED_MIN - 1e-9 else None
        out.update({keys[0]: real, keys[1]: window, keys[2]: None if monthly is None else monthly["depth"],
                    keys[3]: None if proxy is None else proxy[0]})
        out["covered"][side] = {"share": round(share, 4), "missing": missing}
        if real is not None and proxy is not None:
            gap = float(_pp(proxy[0]) - _pp(real))
            out["gap_pp"][side], out["within_2pp"][side] = gap, abs(gap) <= 2.0
    out.update(canada=canada_series(p), method_notes=list(NOTES), kind="assumption", source=SOURCES["deep"],
               as_of=ins["as_of"])
    return out


def _side_summary(worst, starts, floor) -> dict:
    """Counts over the stretches of one mix: the verdict's rule (`breach_share`), broke by more than 1 point
    (`broke_share`), touched (`touched_share`), the worst stretch and the share per start decade (verdict's rule)."""
    classes = [classify(x, floor) for x in worst]
    beyond = [c in ("broke", "touched") for c in classes]
    n, i = len(worst), int(np.argmin(worst))
    decades = {}
    for s, b in zip(starts, beyond):
        decades.setdefault(f"{s[:3]}0s", []).append(b)
    return {"n": n, "breaches": int(sum(beyond)), "breach_share": round(sum(beyond) / n, 4),
            "broke_share": round(classes.count("broke") / n, 4), "touched_share": round(classes.count("touched") / n, 4),
            "worst": round(float(worst[i]), 4), "worst_start": starts[i],
            "by_decade": {k: round(sum(v) / len(v), 4) for k, v in decades.items()}}


def deep_windows(ins, deep) -> dict | None:
    """Every H-month stretch (H = the horizon in months) from the first month all the proxies of the run's mixes have a
    value through the last such month on or before as_of: per start month, the worst fall from the stretch's running
    high (the month before it = 1.0), monthly, CAD, constant weights rebalanced monthly. A mix with a line that has no
    proxy runs on its covered part only when >= 90 % of its weight is covered (said in `coverage`); else "cant_say".
    The UI keeps the stripes off by default (R5): no share of stretches is ever a headline."""
    panel, pmap, floor, h = deep["panel"], deep["pmap"], ins["floor"], ins["horizon_months"]
    if floor is None or not h:
        return {"status": "cant_say", "reason": "this run has no floor or no horizon", "kind": "assumption"}
    p = panel.loc[: pd.Timestamp(ins["as_of"])]
    cols, coverage = {}, {}
    for side, mix in (("today", ins["today"]), ("after", ins["after"])):
        if not mix:
            continue
        c, missing, covered = _proxy_columns(mix, pmap, p)
        total = sum(float(w) for w in mix.values() if float(w) > 1e-12)
        share = covered / total if total else 0.0
        coverage[side] = {"covered_share": round(share, 4), "missing": missing}
        cols[side] = c if c and share >= COVERED_MIN - 1e-9 else None
    if cols.get("today") is None:
        gone = coverage.get("today", {}).get("missing") or []
        return {"status": "cant_say", "reason": f"no history before Nov 2021 for {_and(gone) or 'your mix'}: Can’t say",
                "coverage": coverage, "kind": "assumption"}
    ticker = ins["ticker"]
    alone = (pmap.get(ticker) or {}).get("proxy") if ticker else None
    need = sorted(set(cols["today"]) | set(cols.get("after") or {}) | ({alone} if alone in p.columns else set()))
    ok = p[need].notna().all(axis=1)
    if not ok.any():
        return {"status": "cant_say", "reason": "no month has every proxy", "coverage": coverage, "kind": "assumption"}
    last = ok[ok].index[-1]
    holes = ok.loc[:last][~ok.loc[:last]]
    first = ok.loc[:last][ok.loc[:last].index > holes.index[-1]].index[0] if len(holes) else ok[ok].index[0]
    block = p.loc[first:last]
    starts_all = [_month(m) for m in block.index]
    if len(block) < h:
        return {"status": "cant_say", "reason": f"fewer than {h} months of proxies", "coverage": coverage, "kind": "assumption"}
    starts = starts_all[: len(block) - h + 1]
    worst = {side: _window_worst(_mix_returns(block, c).to_numpy(), h) for side, c in cols.items() if c}
    out = {"status": "ok", "horizon_months": h, "floor": floor, "first_start": starts[0], "last_start": starts[-1],
           "last_month": starts_all[-1], "n": len(starts),
           "stripes": {"starts": starts, **{side: [round(float(x), 4) for x in w] for side, w in worst.items()}},
           **{side: _side_summary(w, starts, floor) for side, w in worst.items()}}
    out.setdefault("after", None)
    by_weight = None
    if ticker and alone in block.columns and ins["curve"] and ins["after"]:
        by_weight = []
        for point in ins["curve"]:
            mix = deep["engine"].apply_change(ins["today"], {"op": "set", "ticker": ticker, "weight": point["weight"],
                                                            "from_ticker": None})
            c, missing, _ = _proxy_columns(mix, pmap, p)
            if missing:
                by_weight = None
                break
            w = _window_worst(_mix_returns(block, c).to_numpy(), h)
            by_weight.append({"weight": point["weight"], "breach_share": round(float(np.mean([_beyond(x, floor) for x in w])), 4),
                              "worst": round(float(w.min()), 4)})
    proxies = []
    for t in sorted({*(ins["today"] or {}), *(ins["after"] or {})}):
        entry = pmap.get(t.upper()) or {}
        strength = None
        if entry.get("proxy"):
            try:
                strength = deep["mod"].proxy_check({t: 1.0}, ins["as_of"], market=deep["market"], panel=panel,
                                                   proxy_map=pmap)["strength"]
            except Exception:                               # noqa: BLE001 (a badge only)
                strength = None
        proxies.append({"ticker": t, "proxy": entry.get("proxy"), "label": entry.get("label"),
                        "strength": strength or ("can't say" if not entry.get("proxy") else None), "note": entry.get("note")})
    out.update(by_weight=by_weight, proxies=proxies, coverage={**coverage, "missing": sorted(
        {m for c in coverage.values() for m in c["missing"]})}, kind="assumption", frequency="monthly",
        source=SOURCES["deep"], as_of=ins["as_of"])
    return out


# === R19(b): "Too Canadian?" answers the workshop's XSP question (unhedged SPY vs a CAD-hedged stand-in) ============
HEDGE_TICKERS = ("SPY",)
HEDGE_METHOD = ("Unhedged: your mix with SPY converted to Canadian dollars every day at the Bank of Canada rate (the "
                "engine’s own path, real data). Hedged stand-in (an assumption): the same mix with SPY’s line on its US-dollar "
                "returns, as if the USD/CAD move were removed, the way a CAD-hedged S&P 500 fund such as XSP is built. No "
                "hedging cost or gain is counted (a real hedge pays or earns the gap between the two currencies’ interest "
                "rates), so this is a stand-in, never XSP’s own record. Hedged like XSP (hedged_carry, an assumption): the "
                "same stand-in plus that carry, as a currency forward books it: each day the Bank of Canada target less the "
                "US effective federal funds rate known the day before, accrued by calendar day (a cost while US rates are "
                "higher). XSP’s fees, its monthly hedge resets and its tracking are not counted.")


def _path_numbers(dates, values, amount, floor) -> dict:
    """Worst fall from the running high (with its dates), the 2022 numbers and the end value of one daily path."""
    depth, peak, trough = 0.0, None, None
    high = np.maximum.accumulate(values)
    dd = values / high - 1.0
    t = int(np.argmin(dd))
    if dd[t] < 0:
        depth, trough = float(dd[t]), dates[t]
        peak = dates[int(np.argmax(values[: t + 1] == high[t]))]
    in22 = [i for i, d in enumerate(dates) if d.startswith("2022")]
    worst22 = ret22 = None
    if in22 and in22[0] > 0:
        seg = values[in22[0] - 1: in22[-1] + 1]                          # from the last day of 2021
        worst22 = float((seg / np.maximum.accumulate(seg) - 1.0).min())
        ret22 = float(values[in22[-1]] / values[in22[0] - 1] - 1.0)
    end = int(Decimal(repr(float(amount * values[-1] / 100))).quantize(Decimal("1"), ROUND_HALF_UP)) if amount else None
    return {"worst_fall": depth, "peak_date": peak, "trough_date": trough, "loss_dollars": _dollars(amount, depth),
            "beyond_floor": None if floor is None else _beyond(depth, floor), "worst_2022": worst22, "return_2022": ret22,
            "end_value": end, "end_date": dates[-1]}


def _hedge_carry(market, as_of) -> pd.Series:
    """The cumulative carry of a CAD hedge on the market calendar (finance F5): each day, the Bank of Canada target
    (rf_daily) less the US effective federal funds rate (DFF in the starter macro_rates.csv), both as known the day
    before, accrued by calendar day (gap x days / 365); 0 on a day without both rates. Nothing after as_of is read."""
    from tools.data import DATA_DIR                         # noqa: PLC0415
    cal = market["prices"].index
    mac = pd.read_csv(DATA_DIR / "macro_rates.csv", usecols=["date", "series_id", "value"], parse_dates=["date"])
    dff = mac.loc[mac["series_id"] == "DFF"].drop_duplicates("date", keep="last").set_index("date")["value"].sort_index()
    dff = dff[dff.index <= pd.Timestamp(as_of)] / 100.0
    usd = dff.reindex(cal.union(dff.index)).ffill().reindex(cal)
    gap = (market["rf_daily"].reindex(cal).ffill() - usd).shift(1).fillna(0.0)
    days = pd.Series(cal, index=cal).diff().dt.days.fillna(0.0)
    return (1.0 + gap * days / 365.0).cumprod()


def hedge_compare(ins, engine) -> dict | None:
    """For a move into SPY: the mix after the move unhedged (SPY in CAD, as the verdict judged it) beside a CAD-hedged
    stand-in (SPY's USD returns, no hedging cost), on the real daily data, and SPY's own 2022 return in USD and in CAD."""
    ticker = ins["ticker"]
    if not ins["after"] or ticker not in HEDGE_TICKERS:
        return None
    market = engine.load_market(ins["as_of"])
    if ticker not in market["local"].columns or ticker not in market["prices"].columns:
        return None
    hedged = {**market, "prices": market["prices"].copy()}
    hedged["prices"][ticker] = market["local"][ticker]               # the line moves with its USD price only
    carry = _hedge_carry(market, ins["as_of"])
    xsp = {**market, "prices": market["prices"].copy()}
    xsp["prices"][ticker] = market["local"][ticker] * carry         # its USD price, plus the forward's rate-gap carry
    out = {"ticker": ticker, "weight": ins["weight"], "amount": ins["amount"], "floor": ins["floor"]}
    for side, bundle, kind in (("unhedged", market, "fact"), ("hedged_standin", hedged, "assumption"),
                               ("hedged_carry", xsp, "assumption")):
        s = engine.portfolio_series(ins["after"], as_of=ins["as_of"], market=bundle)
        out[side] = {**_path_numbers(list(s["dates"]), np.asarray(s["values"], dtype="float64"), ins["amount"],
                                     ins["floor"]), "kind": kind}
    spy = {}
    for cur, frame in (("usd", market["local"]), ("cad", market["prices"])):
        px = frame[ticker].dropna()
        spy[cur] = (float(px[:"2022-12-31"].iloc[-1] / px[:"2021-12-31"].iloc[-1] - 1)
                    if len(px[:"2021-12-31"]) and len(px[:"2022-12-31"]) and ins["as_of"] >= "2022-12-31" else None)
    out["spy_2022"] = {**spy, "currency_effect_pp": None if None in spy.values() else
                       round((spy["cad"] - spy["usd"]) * 100, 2), "kind": "fact"}
    out["hedge_carry"] = {"total": float(carry.iloc[-1] - 1.0), "from": carry.index[0].strftime("%Y-%m-%d"),
                          "to": carry.index[-1].strftime("%Y-%m-%d"), "kind": "assumption",
                          "source": "Bank of Canada V39079 less the US DFF (starter macro_rates.csv), accrued by calendar day"}
    out.update(method=HEDGE_METHOD, kind="assumption", source="tools.portfolio.portfolio_series on the starter prices; "
               "the stand-in replaces SPY’s CAD price by its listing-currency (USD) adjusted close", as_of=ins["as_of"])
    return out


# === R35 / R36 (fix wave, lane fin-backend): the two limits, the path's own dollars, the robustness facts ============
FIX_KEYS = ("capacity", "peer_check", "never_rebalanced", "funding_check", "volatility")
PEER_CLASS = "equity"                  # the pack's 20 stocks (assets_universe.csv asset_class)
BOND_CLASSES = ("etf_bond",)           # the pack's bond funds; ZST.TO (ultra short-term bonds) is the mixes' cash line
FUNDING_WAYS = (("in_proportion", "in proportion, from every other line"), ("largest", "from the largest holding"),
                ("bonds_cash", "from bonds and cash"))
FIX_SOURCES = {
    "capacity": ("The Result's own daily paths in dollars (amount × value / 100, to the cent) against the line amount − "
                 "capacity (the profile's capacity for loss); the falls past the floor: pipeline._breaches on the same path"),
    "breaches": "The path's own values on your fictional amount at the high and at the low (amount × value / 100)",
    "peer": ("The run's own change with the ticker swapped, tools.portfolio.apply_change; each path as "
             "tools.portfolio.series_from_market computes it, on the same days; the floor rule after 0.1 pp rounding"),
    "never": ("The mix after the move bought on the first day and never rebalanced: each line grows with its own CAD "
              "price (the engine's prices and days); falls past the floor: pipeline._breaches"),
    "funding": "tools.portfolio.apply_change (set, or move from one line) + governance.evaluate, on the same replay data",
    "volatility": ("tools.metrics.risk_metrics(per_year=\"sessions\"): the daily standard deviation × √(the replay's own "
                   "sessions a year: its daily returns / its calendar days × 365.25)"),
}


def _whole(x) -> int:
    """To the dollar, ROUND_HALF_UP through repr."""
    return int(Decimal(repr(float(x))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def breach_dollars(result) -> None:
    """In place, on every row of result.breaches: fall_dollars = trough_value − peak_value, both the path's own value on
    the fictional amount to the dollar (R35: never amount × depth). Robert 2025: $1,473,670 → $1,224,257 = −$249,413."""
    for b in result.get("breaches") or []:
        if isinstance(b, dict) and b.get("peak_value") is not None and b.get("trough_value") is not None:
            b["fall_dollars"] = _whole(b["trough_value"]) - _whole(b["peak_value"])


def _floor_breaks(dates, values, floor, amount, line=None) -> list:
    """The falls past the floor on one base-100 path (pipeline._breaches, the rule of result.breaches) with their own
    dollars; with a capacity `line`, whether each fall's low stayed above it."""
    import pipeline                                         # noqa: PLC0415 (loaded already when pipeline.run calls)
    out = []
    for b in pipeline._breaches(list(dates), [float(v) for v in values], floor, amount) if floor is not None else []:
        top, low = _whole(b["peak_value"]), _whole(b["trough_value"])
        row = {"peak_date": b["peak_date"], "trough_date": b["trough_date"], "recovery_date": b["recovery_date"],
               "depth": b["depth"], "peak_value": top, "trough_value": low, "fall_dollars": low - top}
        if line is not None:
            row.update(margin_dollars=low - line, capacity_status="broke" if b["trough_value"] < line else "held")
        out.append(row)
    return out


def _capacity_side(dates, values, amount, line, floor) -> dict:
    """One side's path against the capacity line: its lowest value, the sessions below the line (first, last), how
    many separate falls went below it (a fall runs from a high to the first day back at it) and the floor's breaks."""
    v = np.asarray(values, dtype="float64")
    dollars = np.round(amount * v / 100.0, 2)
    below = np.nonzero(dollars < line)[0]
    start, high = np.zeros(len(v), dtype=int), np.maximum.accumulate(v)
    for i in range(1, len(v)):                                # the high each day's fall started from
        start[i] = i if v[i] >= high[i - 1] else start[i - 1]
    low, groups = int(np.argmin(dollars)), {}
    for i in below:
        groups.setdefault(int(start[i]), []).append(int(i))
    episodes = []
    for ix in groups.values():                                # one row per fall that went below the line
        j = min(ix, key=lambda k: dollars[k])
        episodes.append({"first_date": dates[ix[0]], "last_date": dates[ix[-1]], "low_date": dates[j],
                         "low_value": _whole(dollars[j]), "sessions": len(ix)})
    return {"amount": amount, "capacity": amount - line, "line": line, "low_value": _whole(dollars[low]),
            "low_date": dates[low], "margin_dollars": _whole(dollars[low]) - line, "sessions": len(v),
            "sessions_below": int(len(below)), "first_below": dates[below[0]] if len(below) else None,
            "last_below": dates[below[-1]] if len(below) else None, "falls_below": len(episodes), "episodes": episodes,
            "status": "broke" if len(below) else "held", "end_date": dates[-1],
            "floor_breaks": _floor_breaks(dates, v, floor, amount, line)}


def capacity(result, ins) -> dict | None:
    """R35's second limit, the persona's own words ("could absorb a $90,000 loss"): stay above amount − capacity
    ($600,000 − $90,000 = $510,000), on each side's own daily path (the Result's series, every day <= as_of). The floor
    (no fall of more than 15 % from any high) stays the verdict's rule; this is a separate fact, never a verdict input.
    None without a positive capacity below the amount or without the series."""
    amount, s = ins["amount"], result.get("series") or {}
    cap = (ins["profile"] or {}).get("capacity")
    cap = _dig(result, "limits", "capacity_dollars") if cap is None else cap
    dates = list(s.get("dates") or [])
    if not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (amount, cap)) or not 0 < cap < amount:
        return None
    if not dates or len(s.get("today") or []) != len(dates):
        return None
    line = amount - cap
    after = s.get("after") if ins["after"] and len(s.get("after") or []) == len(dates) else None
    out = {"amount": amount, "capacity": cap, "line": line, "floor": ins["floor"],
           "today": _capacity_side(dates, s["today"], amount, line, ins["floor"]),
           "after": _capacity_side(dates, after, amount, line, ins["floor"]) if after else None}
    run = out["after"] or out["today"]                    # the run's own path (with the move when there is one), as breaches
    out.update(side="after" if out["after"] else "today", status=run["status"], times=run["falls_below"],
               episodes=run["episodes"], min_value=run["low_value"], min_date=run["low_date"], kind="fiction",
               source=FIX_SOURCES["capacity"], as_of=ins["as_of"])
    return out


def never_row(result) -> bool:
    """In place: the never-rebalanced variation also as a row of result.variations (kind "never_rebalanced"), the shape
    the stage reads (FIXWAVE R36: "a variations row"); once. True when a row was added."""
    if _never_row_missing(result):
        result["variations"].append({**result["never_rebalanced"], "kind": "never_rebalanced", "id": "never_rebalanced"})
        return True
    return False


def _never_row_missing(result) -> bool:
    rows = result.get("variations")
    return isinstance(result.get("never_rebalanced"), dict) and isinstance(rows, list) and not any(
        isinstance(x, dict) and x.get("kind") == "never_rebalanced" for x in rows)


def peer_check(ins, engine) -> dict | None:
    """R36 (finance F2): the run's own move at the same size in each of the pack's 20 stocks (the run's change with
    the ticker swapped), each path as the engine computes it on the same days <= as_of: how many ended above your mix
    today, how many broke your floor (the verdict's rule after 0.1 pp rounding), and the list. The 20 are the stocks
    in the pack today (today's survivors), so a high count reads the window, not the pick. Only for a move into one of
    them (None otherwise)."""
    change, ticker = ins["change"], ins["ticker"]
    if not ins["after"] or not ticker or not change or ins["floor"] is None or not ins["amount"]:
        return None
    uni = engine.load_universe()
    stocks = [str(t).upper() for t in uni.loc[uni["asset_class"] == PEER_CLASS, "ticker"]]
    if ticker not in stocks:
        return None
    names = dict(zip(uni["ticker"].astype(str).str.upper(), uni["name"]))
    mixes = [engine.apply_change(ins["today"], {**change, "ticker": t}) for t in stocks]
    paths = _many_paths(engine.load_market(ins["as_of"]), mixes + [ins["today"]])
    amount, (days, base) = ins["amount"], paths[-1]
    today_end, rows = _whole(amount * base[-1] / 100), []
    for t, (d, v) in zip(stocks, paths[:-1]):
        depth, end = float((v / np.maximum.accumulate(v) - 1.0).min()), _whole(amount * v[-1] / 100)
        rows.append({"ticker": t, "name": names.get(t), "end_value": end, "max_drawdown": depth,
                     "ended_higher": end > today_end, "broke_floor": bool(_beyond(depth, ins["floor"])),
                     "is_move": t == ticker})
    rows.sort(key=lambda x: (-x["end_value"], x["ticker"]))
    return {"ticker": ticker, "weight": ins["weight"], "n": len(rows), "today_end": today_end,
            "higher": sum(x["ended_higher"] for x in rows), "broke": sum(x["broke_floor"] for x in rows),
            "lower": [x["ticker"] for x in rows if not x["ended_higher"]],
            "broke_list": [x["ticker"] for x in rows if x["broke_floor"]], "rows": rows, "floor": ins["floor"],
            "start_date": days[0], "end_date": days[-1], "kind": "fact", "source": FIX_SOURCES["peer"],
            "as_of": ins["as_of"]}


def never_rebalanced(ins, engine, run_breaks=None) -> dict | None:
    """R36 (finance F3): the mix after the move bought once on the first day and never rebalanced (each line grows with
    its own CAD price, the engine's prices and days <= as_of), so the moved line's share drifts: its largest share and
    when, its share at the end and at each fall's high, the falls past the floor (the rule of result.breaches), the
    worst fall and the end value. `run_breaks` = how many the daily-rebalanced replay has (result.breaches)."""
    t = ins["ticker"]
    if not ins["after"] or not t or ins["floor"] is None or not ins["amount"]:
        return None
    market = engine.load_market(ins["as_of"])
    held = {str(k).strip().upper(): float(w) for k, w in ins["after"].items() if float(w) > 1e-12}
    cols = sorted(held)
    prices = market["prices"][cols].ffill()
    prices = prices[market["traded"][cols].any(axis=1)]
    if len(prices) < 2 or prices.iloc[0].isna().any() or t not in cols:
        return None                                       # a line with no price on day one cannot be bought then
    lines = prices.to_numpy() / prices.iloc[0].to_numpy() * np.array([held[c] for c in cols])
    total, dates = lines.sum(axis=1), prices.index.strftime("%Y-%m-%d").tolist()
    share, values = lines[:, cols.index(t)] / total, 100.0 * total
    high = np.maximum.accumulate(values)
    k, tr = int(np.argmax(share)), int(np.argmin(values / high - 1.0))
    depth, p = float(values[tr] / high[tr] - 1.0), int(np.argmax(values[: tr + 1] == high[tr]))
    falls = _floor_breaks(dates, values, ins["floor"], ins["amount"])
    for f in falls:
        f["share_at_high"] = float(share[dates.index(f["peak_date"])])
    return {"ticker": t, "weight": ins["weight"], "peak_weight": float(share[k]), "peak_weight_date": dates[k],
            "end_weight": float(share[-1]), "breaks": len(falls), "falls": falls, "worst_fall": depth,
            "worst_peak_date": dates[p], "worst_trough_date": dates[tr], "end_value": _whole(ins["amount"] * values[-1] / 100),
            "rebalanced_breaks": run_breaks, "floor": ins["floor"], "start_date": dates[0], "end_date": dates[-1],
            "kind": "fact", "source": FIX_SOURCES["never"], "as_of": ins["as_of"]}


def funding_check(ins, engine, own_run=None) -> dict | None:
    """R36 (finance F9 + the funding question): the move funded three ways, each judged by governance.evaluate with the
    run's limits and shocks: in proportion from every other line (tools.portfolio's `set`), from the largest holding
    alone, from the bond and cash lines in proportion (`move`, line by line). A way that cannot pay for the move (a
    source too small, no bond line) is kept with possible False and left out of the range. mildest / deepest = the
    worst falls' range; same_verdict = every possible way gets the run's verdict. `own_run` answers the run's own mix."""
    t = ins["ticker"]
    if not ins["after"] or not t or not ins["profile"] or not ins["amount"]:
        return None
    today = {str(k).strip().upper(): float(w) for k, w in ins["today"].items() if float(w) > 1e-12}
    size = float(ins["after"].get(t, 0.0)) - today.get(t, 0.0)
    others = {k: w for k, w in today.items() if k != t}
    if size <= 1e-9 or not others:
        return None
    uni = engine.load_universe()
    cls = dict(zip(uni["ticker"].astype(str).str.upper(), uni["asset_class"]))
    largest = min(others, key=lambda k: (-others[k], k))
    bonds = {k: w for k, w in sorted(others.items()) if cls.get(k) in BOND_CLASSES}
    ways = []
    for wid, words in FUNDING_WAYS:
        src = sorted(others) if wid == "in_proportion" else [largest] if wid == "largest" else list(bonds)
        row = {"id": wid, "words": words, "from": src}
        try:
            if wid == "in_proportion":
                mix = engine.apply_change(ins["today"], {"op": "set", "ticker": t, "weight": float(ins["after"][t]),
                                                         "from_ticker": None})
            else:
                pool = {k: others[k] for k in src}
                if not pool or sum(pool.values()) < size - 1e-9:
                    raise ValueError("the source cannot pay for the move")
                mix = dict(ins["today"])
                for k in src:
                    mix = engine.apply_change(mix, {"op": "move", "ticker": t, "weight": size * pool[k] / sum(pool.values()),
                                                    "from_ticker": k})
        except ValueError:
            ways.append({**row, "possible": False})
            continue
        own = own_run is not None and _same_mix(mix, ins["after"])
        ev = own_run if own else engine.evaluate(ins["profile"], mix, ins["families"], ins["as_of"], limits=ins["limits"],
                                                 amount=ins["amount"])
        if not isinstance(ev, dict) or ev.get("error") or not isinstance(ev.get("metrics"), dict):
            ways.append({**row, "possible": False})
            continue
        ways.append({**row, "possible": True, "mix": {k: float(w) for k, w in mix.items()}, "is_run": _same_mix(mix, ins["after"]),
                     "max_drawdown": ev["metrics"]["max_drawdown"], "verdict": ev.get("verdict"),
                     "beyond_floor": None if ins["floor"] is None else bool(_beyond(ev["metrics"]["max_drawdown"], ins["floor"]))})
    ok = [w for w in ways if w["possible"]]
    if not ok:
        return None
    falls, verdicts = [w["max_drawdown"] for w in ok], list(dict.fromkeys(w["verdict"] for w in ok))
    return {"ticker": t, "weight": ins["weight"], "size": size, "ways": ways, "n": len(ok), "mildest": max(falls),
            "deepest": min(falls), "verdicts": verdicts, "same_verdict": len(verdicts) == 1, "families": ins["families"],
            "kind": "fact", "source": FIX_SOURCES["funding"], "as_of": ins["as_of"]}


def volatility(ins, engine) -> dict | None:
    """R36 (finance F9): each side's volatility over the replay, annualised with its own sessions a year
    (tools.metrics.risk_metrics(per_year="sessions")), on the path the verdict's metrics are computed from (the mix's
    own days, tools.portfolio.portfolio_series), beside the 252 convention (value_252 = metrics.<side>.volatility).
    Robert's move: 1,281 daily returns over 1,826 calendar days = 256.2 a year, so 22.37 %, not 22.18 %."""
    from tools.metrics import risk_metrics                 # noqa: PLC0415
    out = {}
    for side in ("today", "after"):
        mix = ins[side]
        dates, values = _series(engine, mix, ins["as_of"]) if mix else ([], [])
        if len(dates) < 3:
            out[side] = None
            continue
        series = {"dates": dates, "values": [float(v) for v in values]}
        own, std = risk_metrics(series, per_year="sessions"), risk_metrics(series)
        days = (pd.Timestamp(dates[-1]) - pd.Timestamp(dates[0])).days
        out[side] = {"value": own["volatility"], "value_252": std["volatility"], "returns": len(dates) - 1,
                     "calendar_days": days, "sessions_per_year": (len(dates) - 1) * 365.25 / days,
                     "start_date": dates[0], "end_date": dates[-1]}
    if out["today"] is None:
        return None
    return {**out, "kind": "fact", "source": FIX_SOURCES["volatility"], "as_of": ins["as_of"]}


# === the facts rows of the numbers the page shows from these keys ================================================
def _bare(label):
    """A label as a fact's entity, the words a sentence names it by (verify._names_entity): "the US chip industry" ->
    "US chip industry"."""
    return re.sub(r"^the\s+", "", label) if isinstance(label, str) and label else None


def add_facts(rows: _Rows, result: dict, ins: dict, keys=KEYS) -> None:
    """One facts row per number the UI shows from the new keys (trace ids appended after COMPARE's own): ● for the
    2021-26 replays, ○ for fictional dollars, ◐ ("assumption") for everything computed by proxy. Only the rows of
    `keys` (a later pass adds the rows of what it computed, never twice)."""
    f, ticker = rows.fact, ins["ticker"]
    got = lambda key: result.get(key) if key in keys else None             # noqa: E731
    ev = got("end_values")
    if ev:
        f(f"Ended at, your mix today ({ev['date']}, on your fictional amount)", ev["today"], "CAD", "today", "fiction",
          path="end_values.today", source=ev["source"])
        f(f"Ended at, your mix with the move ({ev['date']}, on your fictional amount)", ev["after"], "CAD", "after",
          "fiction", path="end_values.after", source=ev["source"])
    n2 = got("not_2022")
    if n2:
        words = "after the move" if n2["side"] == "after" else "today"
        f(f"Worst drop {words} on the dates from 2023 on (2022 left out)", n2["depth"], "pct", n2["side"], "fact",
          path="not_2022.depth", source=SOURCES["not_2022"])
        f(f"The same drop on your fictional amount (amount × drawdown), dates from 2023 on", n2["loss_dollars"], "CAD",
          n2["side"], "fiction", path="not_2022.loss_dollars", source=SOURCES["not_2022"])
    band = got("tipping_band")
    if band and band.get("lo") is not None:
        span = f"start months {band['starts'][0]['start']} to {band['starts'][-1]['start']}"
        f(f"In this replay, the first {ticker} size that broke your floor: the smallest over {span}", band["lo"], "pct",
          ticker, "fact", path="tipping_band.lo", source=SOURCES["band"])
        f(f"In this replay, the first {ticker} size that broke your floor: the largest over {span}", band["hi"], "pct",
          ticker, "fact", path="tipping_band.hi", source=SOURCES["band"])
    hc = got("hedge_compare")
    if hc:
        w, t = _pct_text(hc["weight"], whole=True), hc["ticker"]
        for side, words in (("unhedged", "unhedged (in Canadian dollars)"),
                            ("hedged_standin", "CAD-hedged stand-in (US-dollar returns, no hedging cost)"),
                            ("hedged_carry", "hedged like XSP (US-dollar returns plus the rate-gap carry)")):
            if side not in hc:                               # a Result extended before hedged_carry existed
                continue
            x, kind, src = hc[side], hc[side]["kind"], hc["source"]
            f(f"Worst drop after the move ({w} in {t}), {words}", x["worst_fall"], "pct", "after", kind,
              path=f"hedge_compare.{side}.worst_fall", source=src)
            f(f"Worst fall in 2022 after the move ({w} in {t}), {words}", x["worst_2022"], "pct", "after", kind,
              path=f"hedge_compare.{side}.worst_2022", source=src)
            f(f"Your fictional amount at the end after the move ({w} in {t}), {words}", x["end_value"], "CAD", "after",
              "fiction", path=f"hedge_compare.{side}.end_value", source=src)
        if hc.get("hedge_carry"):
            f(f"The CAD hedge’s carry over the replay ({hc['hedge_carry']['from']} to {hc['hedge_carry']['to']}, the rate "
              f"gap)", hc["hedge_carry"]["total"], "pct", "hedged like XSP", "assumption", path="hedge_compare.hedge_carry.total",
              source=hc["hedge_carry"]["source"])
        f(f"{t}’s 2022 return in US dollars", hc["spy_2022"]["usd"], "pct", t, "fact", path="hedge_compare.spy_2022.usd",
          source="Starter prices: the listing-currency adjusted close, 2021-12-31 to 2022-12-31")
        f(f"{t}’s 2022 return in Canadian dollars", hc["spy_2022"]["cad"], "pct", t, "fact", path="hedge_compare.spy_2022.cad",
          source="Starter prices converted at the Bank of Canada USD/CAD rate, 2021-12-31 to 2022-12-31")
    side_words = (("today", "your mix today"), ("after", "your mix with the move"))
    if "breaches" in keys:
        moved = isinstance(_dig(result, "metrics", "after"), dict)
        for i, b in enumerate(result.get("breaches") or []):
            if not isinstance(b, dict) or b.get("fall_dollars") is None:
                continue
            head, src = f"Fall {i + 1} deeper than your floor ({b['peak_date']} to {b['trough_date']})", FIX_SOURCES["breaches"]
            for key, words in (("peak_value", "the high"), ("trough_value", "the low")):
                f(f"{head}: {words}, on your fictional amount", _whole(b[key]), "CAD", "after" if moved else "today",
                  "fiction", path=f"breaches.{i}.{key}", source=src)
            f(f"{head}: the fall in dollars (the low less the high)", b["fall_dollars"], "CAD", "after" if moved else "today",
              "fiction", path=f"breaches.{i}.fall_dollars", source=src)
    cap = got("capacity")
    if cap:
        src = cap["source"]
        f(f"Your capacity line: your fictional amount less the capacity for loss in your profile (${cap['capacity']:,.0f})",
          cap["line"], "CAD",
          "your capacity", "assumption", path="capacity.line", source=src)
        for side, words in side_words:
            x = cap.get(side)
            if not x:
                continue
            f(f"Lowest value of {words}, on your fictional amount ({x['low_date']})", x["low_value"], "CAD", side, "fiction",
              path=f"capacity.{side}.low_value", source=src)
            f(f"Sessions {words} spent below your capacity line", x["sessions_below"], "count", side, "fact",
              path=f"capacity.{side}.sessions_below", source=src)
            f(f"Separate falls of {words} below your capacity line", x["falls_below"], "count", side, "fact",
              path=f"capacity.{side}.falls_below", source=src)
            for i, b in enumerate(x["floor_breaks"]):
                f(f"Fall {i + 1} of {words} deeper than your floor ({b['trough_date']}): its low above your capacity line "
                  f"(below it when negative)", b["margin_dollars"], "CAD", side, "fiction",
                  path=f"capacity.{side}.floor_breaks.{i}.margin_dollars", source=src)
    pc = got("peer_check")
    if pc:
        w, src = _pct_text(pc["weight"], whole=True), pc["source"]
        f(f"Stocks in the pack, each replayed at the same {w} as {pc['ticker']}", pc["n"], "count", "the pack's stocks",
          "fact", path="peer_check.n", source=src)
        f(f"Of the pack's stocks at the same {w}: how many ended above your mix today", pc["higher"], "count",
          "the pack's stocks", "fact", path="peer_check.higher", source=src)
        f(f"Of the pack's stocks at the same {w}: how many broke your floor", pc["broke"], "count", "the pack's stocks",
          "fact", path="peer_check.broke", source=src)
    nr = got("never_rebalanced")
    if nr:
        t, src = nr["ticker"], nr["source"]
        f(f"Never rebalanced: the largest share of the money in {t} ({nr['peak_weight_date']})", nr["peak_weight"], "pct",
          t, "fact", path="never_rebalanced.peak_weight", source=src)
        f(f"Never rebalanced: the share of the money in {t} at the end ({nr['end_date']})", nr["end_weight"], "pct", t,
          "fact", path="never_rebalanced.end_weight", source=src)
        f("Never rebalanced: falls deeper than your floor with the move", nr["breaks"], "count", "after", "fact",
          path="never_rebalanced.breaks", source=src)
        f(f"Never rebalanced: worst drop with the move ({nr['worst_peak_date']} to {nr['worst_trough_date']})",
          nr["worst_fall"], "pct", "after", "fact", path="never_rebalanced.worst_fall", source=src)
        f(f"Never rebalanced: your fictional amount at the end ({nr['end_date']})", nr["end_value"], "CAD", "after",
          "fiction", path="never_rebalanced.end_value", source=src)
    fc = got("funding_check")
    if fc:
        src = fc["source"]
        f(f"Ways the move was funded and judged (the move funded {fc['n']} ways)", fc["n"], "count", "after", "fact",
          path="funding_check.n", source=src)
        for i, x in enumerate(fc["ways"]):
            if x["possible"]:
                f(f"The move funded {x['words']} ({', '.join(x['from'])}): worst drop", x["max_drawdown"], "pct", "after",
                  "fact", path=f"funding_check.ways.{i}.max_drawdown", source=src)
    vol = got("volatility")
    if vol:
        for side, words in side_words:
            x = vol.get(side)
            if not x:
                continue
            f(f"Volatility, a year, {words} (annualised with this replay's own sessions a year)", x["value"], "pct", side,
              "fact", path=f"volatility.{side}.value", source=vol["source"])
            f(f"Trading sessions a year in this replay, {words}", round(x["sessions_per_year"], 1), "count", side, "fact",
              path=f"volatility.{side}.sessions_per_year", source=vol["source"])
    deep = got("deep_history")
    if deep:
        src, c = deep["source"], deep["counts"]
        alone = _bare((deep.get("moved") or {}).get("label")) or "stand-in"
        f("By proxy: earlier crises replayed (1973 to 2020)", c["n"], "count", "earlier crises", "assumption",
          path="deep_history.counts.n", source=src)
        for side, words in (("today", "your mix today"), ("after", "your mix with the move")):
            if c.get(f"{side}_broke") is None:
                continue
            f(f"By proxy: crises where {words} broke your floor by more than 1 point in every sensitivity run",
              c[f"{side}_broke"], "count", side, "assumption", path=f"deep_history.counts.{side}_broke", source=src)
            f(f"By proxy: crises where {words} held in every sensitivity run", c[f"{side}_held"], "count", side,
              "assumption", path=f"deep_history.counts.{side}_held", source=src)
            f(f"By proxy: crises too close to call for {words} (within 1 point of your floor, or changing with the "
              f"sensitivity runs)", c[f"{side}_touched"], "count", side, "assumption",
              path=f"deep_history.counts.{side}_touched", source=src)
        if c.get("move_no_worse") is not None:
            f("By proxy: crises where your mix with the move fell no further than your mix today in every sensitivity run",
              c["move_no_worse"], "count", "after", "assumption", path="deep_history.counts.move_no_worse", source=src)
        for e in deep["episodes"]:
            for side, words in (("today", "your mix today"), ("after", "your mix with the move"), ("proxy_alone", f"{alone} alone")):
                entity = "today" if side == "today" else "after" if side == "after" else alone
                f(f"By proxy, {e['title']}: worst fall, {words}", e[side], "pct", entity, "assumption",
                  path=f"deep_history.episodes.{e['id']}.{side}", source=src)
        for claim in (deep.get("robust_claims") or {}).get("claims") or []:
            if claim["id"] == "after_broke":
                f("By proxy: the smallest margin by which the move broke your floor in every run (points)",
                  claim["lo_pp"] / 100, "pp", "after", "assumption", path="deep_history.robust_claims.after_broke.lo_pp", source=src)
                f("By proxy: the largest margin by which the move broke your floor in every run (points)",
                  claim["hi_pp"] / 100, "pp", "after", "assumption", path="deep_history.robust_claims.after_broke.hi_pp", source=src)
        gc = deep.get("gentle_case")
        if gc:
            span = f"{gc['window']['start']} to {gc['window']['end']}, month-end"
            f(f"{ticker} alone ({span}): worst fall on its real prices", gc["real"], "pct", ticker, "fact",
              path="deep_history.gentle_case.real", source="Starter prices, month-end, CAD")
            name = (gc["label"] or "its stand-in")
            f(f"{name[0].upper() + name[1:]} ({span}): worst fall, the stand-in for {ticker}", gc["stand_in"], "pct",
              _bare(gc["label"]) or "stand-in", "assumption", path="deep_history.gentle_case.stand_in", source=src)
    val = got("deep_validation")
    if val:
        span = f"{val['window']['start']} to {val['window']['end']}"
        for side, words in (("today", "your mix today"), ("after", "your mix with the move")):
            f(f"Check of the stand-ins ({span}): {words} by proxy, worst fall", val.get(f"{side}_proxy"), "pct", side,
              "assumption", path=f"deep_validation.{side}_proxy", source=SOURCES["deep"])
    win = got("deep_windows")
    if win and win.get("status") == "ok":
        years = win["horizon_months"] / 12
        span = f"{int(years)}-year" if years == int(years) else f"{win['horizon_months']}-month"
        for side, words in (("today", "your mix today"), ("after", "your mix with the move")):
            if win.get(side):
                f(f"By proxy since {win['first_start'][:4]}: worst fall of {words} in any {span} stretch",
                  win[side]["worst"], "pct", side, "assumption", path=f"deep_windows.{side}.worst", source=SOURCES["deep"])


# === the one entry point ==========================================================================================
# --- the funds, broken down as a fund page shows one (lane funds, Sun Nov 15; the lead: "like TradingView") --------------
# Red gate 8: the issuers (BlackRock/iShares, State Street, Invesco, Vanguard) forbid redistributing fund holdings "in whole
# or in part" (docs/research/etf-holdings-sources.md). The public key `funds` carries fund-level aggregates only (the date,
# the coverage, how many rows the file lists, the sector and country splits, the issuer's page); the companies inside a fund
# with their weights are `funds_private`, which only server.py adds to a live response, never to a saved run.
FUND_ISSUERS = {"XIU.TO": "BlackRock Canada (iShares)", "XBB.TO": "BlackRock Canada (iShares)", "AGG": "BlackRock (iShares)",
                "TLT": "BlackRock (iShares)", "SPY": "State Street Global Advisors (SPDR)",
                "GLD": "State Street Global Advisors (SPDR)", "QQQ": "Invesco", "ESGV": "Vanguard",
                "ZST.TO": "BMO Global Asset Management"}       # public facts: who runs each fund of the starter universe
FUNDS_TOP = 10                       # funds_private: the largest positions of each fund, by the issuer's weight
OWNING_TOP = 12                      # funds_private.owning: the companies named one by one; the rest as one count and sum
CONCENTRATION_TOP = 10               # funds: the share of a fund in its 10 largest positions (one aggregate, published)
CONCENTRATED_FROM = 0.4              # funds: "concentrated" when its 10 largest positions are 40 % of the fund or more
FUND_SIDES = ("today", "after")
_SMALL_WORDS = {"OF", "AND", "THE", "DE", "DU", "LA", "LE", "ET", "FOR", "IN"}
_KEEP_UPPER = {"ETF", "REIT", "PLC", "AG", "SA", "NV", "SE", "ASA", "AB", "LP", "LLC", "II", "III", "US", "USA", "ADR", "CAD",
               "USD", "CIBC", "BCE", "TC", "CGI", "TMX", "BMO", "TD", "IGM", "RBC", "CL", "NA", "ASML", "AMD", "AT&T"}
FUNDS_DATED = "Fund files dated on or before {d}, the replay’s last day: nothing dated later is used."
FUNDS_SOURCE = ("The issuers’ own fund files (data/etf_holdings.csv: local, never published); per fund only its date, how much "
                "of it the listed positions cover, how many rows the file lists and its sector and country splits; your "
                "dollars = amount × the fund’s weight, by sector and country = amount × the look-through’s share, computed by code")
FUNDS_PRIVATE_SOURCE = ("Live only, never saved or published (the issuers’ licence): the largest positions in the issuers’ "
                        "files dated on or before the replay’s last day; your dollars in a company = amount × the fund’s "
                        "weight × the company’s weight in the fund, computed by code")


def _fund_frame(as_of, holdings=None):
    """(rows dated on or before `as_of`, mode, the newest holdings date in the file, {etf: issuer page}, {etf: the newest
    date of its rows dated after `as_of`}) by tools.lookthrough's own rule: no file, no rows or a holdings snapshot newer
    than `as_of` is direct mode (rows None)."""
    from tools import lookthrough as lt     # noqa: PLC0415
    frame = lt.load_holdings() if holdings is None else lt._normalize(holdings)
    if frame is None or frame.empty:
        return None, "direct", None, {}, {}
    pages = {etf: next((u for u in grp["source_url"] if u), "") for etf, grp in frame.groupby("etf")}
    later = frame[frame["as_of"] > as_of].groupby("etf")["as_of"].max().to_dict()
    newest = frame.loc[frame["kind"] == "holding", "as_of"].max()
    newest = newest if isinstance(newest, str) else None
    if newest is not None and newest > as_of:
        return None, "direct", newest, pages, later
    kept = frame[frame["as_of"] <= as_of]
    return (kept if not kept.empty else None), ("lookthrough" if not kept.empty else "direct"), newest, pages, later


def _side_weights(ins) -> dict:
    return {"today": dict(ins.get("today") or {}), "after": dict(ins["after"]) if ins.get("after") else None}


def _money(amount, share):
    return {"share": _num(share, 6), "dollars": _whole(float(amount) * float(share))} if isinstance(amount, (int, float)) else \
        {"share": _num(share, 6), "dollars": None}


def _split(book: dict, amount, top=None) -> list:
    """[{name, share, dollars}] by size from a {name: share} map (the look-through's sectors or countries)."""
    items = sorted(((str(k), float(v)) for k, v in (book or {}).items() if isinstance(v, (int, float)) and v > 0),
                   key=lambda kv: (-kv[1], kv[0]))
    return [{"name": k, **_money(amount, v)} for k, v in (items[:top] if top else items)]


def funds(result, ins, *, holdings=None, universe=None) -> dict | None:
    """The public key: every fund held today or with the move, as a fund page shows it, and the money by sector and
    country per side. {as_of, mode, dated, newest, source, funds: [{ticker, name, issuer, asset_class, holds, page, date,
    dates {positions, sectors, countries}, listed {positions, sectors, countries}, coverage, sectors [{name, share}],
    countries [{name, share}], later (a file of this fund dated after as_of: its date, not used), today/after {share,
    dollars} | None}], sides: {today, after: {in_funds, direct [{ticker, name, share, dollars}], sectors, countries,
    unlisted} | None}}. Fund-level aggregates only: no company inside a fund is named (red gate 8); dates <= as_of only."""
    as_of = str(ins.get("as_of") or "")[:10]
    sides = _side_weights(ins)
    if not sides["today"] or not as_of:
        return None
    from tools.data import load_universe   # noqa: PLC0415
    from tools import lookthrough as lt     # noqa: PLC0415
    uni = (load_universe() if universe is None else universe).set_index("ticker")
    frame, mode, newest, pages, later_by = _fund_frame(as_of, holdings)
    held = [t for t in dict.fromkeys([*sides["today"], *(sides["after"] or {})]) if t in uni.index]
    amount = ins.get("amount")
    order = sorted((t for t in held if str(uni.at[t, "asset_class"]).startswith("etf")),
                   key=lambda t: (-(sides["today"].get(t) or 0.0), -((sides["after"] or {}).get(t) or 0.0), t))
    rows_by = dict(iter(frame.groupby("etf"))) if frame is not None else {}
    out = []
    for t in order:
        rows = rows_by.get(t)
        part = {k: (rows[rows["kind"] == k] if rows is not None else None) for k in lt.KINDS}
        dates = {w: (str(p["as_of"].max()) if p is not None and not p.empty else None)
                 for w, p in (("positions", part["holding"]), ("sectors", part["sector"]), ("countries", part["country"]))}
        listed = {w: int(len(p)) if p is not None else 0
                  for w, p in (("positions", part["holding"]), ("sectors", part["sector"]), ("countries", part["country"]))}
        secs = ({} if part["sector"] is None or part["sector"].empty
                else part["sector"].groupby("name")["weight"].sum().to_dict())
        ctry = ({} if part["country"] is None or part["country"].empty else lt._country_shares(part["country"]))
        known = [d for d in dates.values() if d]
        largest = (_by_company(part["holding"])["weight"].sum().sort_values(ascending=False)
                   if listed["positions"] else None)                    # one company once (Alphabet A and C are one)
        top10 = ({"count": int(min(CONCENTRATION_TOP, len(largest))), "share": _num(float(largest.iloc[:CONCENTRATION_TOP].sum()), 6)}
                 if largest is not None and len(largest) else None)
        out.append({
            "ticker": t, "name": str(uni.at[t, "name"]), "issuer": FUND_ISSUERS.get(t), "asset_class": str(uni.at[t, "asset_class"]),
            "holds": str(uni.at[t, "sector"]), "page": pages.get(t) or None, "date": max(known) if known else None,
            "dates": dates, "listed": listed,
            "coverage": _num(float(part["holding"]["weight"].sum()), 6) if listed["positions"] else None,
            "sectors": [{"name": k, "share": _num(v, 6)} for k, v in sorted(secs.items(), key=lambda kv: (-kv[1], kv[0]))],
            "countries": [{"name": k, "share": _num(v, 6)} for k, v in sorted(ctry.items(), key=lambda kv: (-kv[1], kv[0]))],
            "later": later_by.get(t),
            "top10": top10, "concentrated": bool(top10 and top10["share"] >= CONCENTRATED_FROM),   # one aggregate, no name
            **{side: (_money(amount, w[t]) if w and w.get(t) else None) for side, w in sides.items()}})
    look = result.get("lookthrough") if isinstance(result.get("lookthrough"), dict) else {}
    side_out = {}
    for side, w in sides.items():
        if not w:
            side_out[side] = None
            continue
        lk = look.get(side) if isinstance(look.get(side), dict) else {}
        in_funds = sum(v for t, v in w.items() if t in uni.index and str(uni.at[t, "asset_class"]).startswith("etf"))
        unlisted = sum(v * (1.0 - min(1.0, float((next((f for f in out if f["ticker"] == t), {}) or {}).get("coverage") or 0.0)))
                       for t, v in w.items() if t in uni.index and str(uni.at[t, "asset_class"]) == "etf_equity")
        stocks = lk.get("stocks") if isinstance(lk.get("stocks"), dict) else {}
        total = lambda t, v: (stocks.get(t) or {}).get("total") if isinstance((stocks.get(t) or {}).get("total"), (int, float)) else v  # noqa: E731
        direct = [{"ticker": t, "name": str(uni.at[t, "name"]), **_money(amount, v), "total": _money(amount, total(t, v))}
                  for t, v in sorted(w.items(), key=lambda kv: (-kv[1], kv[0]))
                  if t in uni.index and str(uni.at[t, "asset_class"]) in ("equity", "crypto")]
        side_out[side] = {"in_funds": _money(amount, in_funds), "direct": direct,
                          "sectors": _split(lk.get("sectors"), amount), "countries": _split(lk.get("countries"), amount),
                          "unlisted": _money(amount, unlisted), "mode": lk.get("mode")}
    return {"as_of": as_of, "mode": mode, "dated": FUNDS_DATED.format(d=as_of), "newest": newest, "source": FUNDS_SOURCE,
            "funds": out, "sides": side_out}


def _by_company(rows):
    """Holding rows grouped by company: the dataset ticker when the file gives one (GOOG is GOOGL already), else the name."""
    key = rows["ticker"].where(rows["ticker"] != "", rows["name"].str.upper())
    return rows.assign(company=key).groupby("company")


def _company_name(name: str, ticker: str, uni) -> str:
    """The company as a reader says it: the universe's own name for a dataset ticker, else the file's name in title case."""
    if ticker and ticker in uni.index:
        return str(uni.at[ticker, "name"])
    words = str(name or "").split()
    if not words or any(c.islower() for c in name):
        return str(name or "")
    return " ".join(w if w in _KEEP_UPPER else (w.lower() if i and w in _SMALL_WORDS else w.capitalize())
                    for i, w in enumerate(words))


def funds_private(result, *, holdings=None, universe=None, top=FUNDS_TOP, owning_top=OWNING_TOP) -> dict | None:
    """LIVE ONLY. Never saved, committed or published (red gate 8): pipeline.save_run cuts it and record_demo.find_leaks
    refuses it, so publish_pages fails if it ever appears. For each fund held today or with the move: the `top` largest
    positions in the issuer's file dated on or before as_of, {name, ticker, share (of the fund), today, after (your
    dollars = amount × fund weight × share, whole dollars, None on a side without the fund)}; and `owning` per side: every
    company you end up with (your direct lines plus every listed position of your funds, merged by ticker, else by name),
    by dollars. None without the holdings file, for a snapshot newer than as_of, or without a mix."""
    if not isinstance(result, dict):
        return None
    ins = inputs(result)
    as_of = str(ins.get("as_of") or "")[:10]
    sides = _side_weights(ins)
    amount = ins.get("amount")
    if not sides["today"] or not as_of or not isinstance(amount, (int, float)) or isinstance(amount, bool):
        return None
    frame, mode, _, _, _ = _fund_frame(as_of, holdings)
    if frame is None or mode != "lookthrough":
        return None
    from tools.data import load_universe   # noqa: PLC0415
    uni = (load_universe() if universe is None else universe).set_index("ticker")
    pos = frame[frame["kind"] == "holding"]
    held = list(dict.fromkeys([*sides["today"], *(sides["after"] or {})]))
    by_fund = {}
    owning = {side: {} for side in FUND_SIDES}
    for side, w in sides.items():
        for t, v in (w or {}).items():
            if t in uni.index and str(uni.at[t, "asset_class"]) in ("equity", "crypto"):
                e = owning[side].setdefault(t, {"name": str(uni.at[t, "name"]), "ticker": t, "dollars": 0.0, "direct": 0.0, "funds": []})
                e["dollars"] += float(amount) * v
                e["direct"] += float(amount) * v
    for t in held:
        rows = pos[pos["etf"] == t]
        if rows.empty:
            continue
        grouped = _by_company(rows).agg(ticker=("ticker", "first"), name=("name", "first"), names=("name", "nunique"),
                                        weight=("weight", "sum")).reset_index().sort_values(["weight", "name"], ascending=[False, True])
        listed = []
        for _, row in grouped.iterrows():
            tk, share = str(row["ticker"] or ""), float(row["weight"])
            name = _company_name(str(row["name"]), tk, uni)
            if int(row["names"]) > 1:                                   # two share classes of one company: its name, no class
                name = re.sub(r"\s*\((?:Class|Cl\.?)\s+[A-Z]\)", "", name)
            dollars = {side: (_whole(float(amount) * w[t] * share) if w and w.get(t) else None) for side, w in sides.items()}
            listed.append({"name": name, "ticker": tk or None, "share": _num(share, 6), **dollars})
            for side, w in sides.items():
                if w and w.get(t):
                    key = tk or name.upper()
                    e = owning[side].setdefault(key, {"name": name, "ticker": tk or None, "dollars": 0.0, "direct": 0.0, "funds": []})
                    e["dollars"] += float(amount) * w[t] * share
                    e["funds"].append(t)
                    e.setdefault("inside", {}).setdefault(t, 0.0)
                    e["inside"][t] += float(amount) * w[t] * share
        by_fund[t] = {"date": str(rows["as_of"].max()), "listed": len(listed), "coverage": _num(float(rows["weight"].sum()), 6),
                      "top": listed[:top]}
    own = {}
    for side, book in owning.items():
        if side == "after" and not sides["after"]:
            own[side] = None
            continue
        ranked = sorted(book.values(), key=lambda e: (-e["dollars"], e["name"]))
        limit = len(ranked) if owning_top is None else owning_top
        rest = ranked[limit:]
        total = lambda es: {"count": len(es), **_money(amount, sum(e["dollars"] for e in es) / float(amount))}   # noqa: E731
        own[side] = {"top": [{"name": e["name"], "ticker": e["ticker"], "dollars": _whole(e["dollars"]), "direct": _whole(e["direct"]),
                              "share": _num(e["dollars"] / float(amount), 6), "funds": sorted(set(e["funds"])),
                              "inside": [{"fund": f, **_money(amount, d / float(amount))} for f, d in sorted((e.get("inside") or {}).items())]}
                             for e in ranked[:limit]],
                     "rest": total(rest), "named": total(ranked)}
    return {"as_of": as_of, "top": top, "funds": by_fund, "owning": own, "source": FUNDS_PRIVATE_SOURCE}


def _own_run(result):
    """The run's own judgement of the mix after the move, as governance.evaluate returned it (metrics, path, verdict, checks)."""
    m, s = _dig(result, "metrics", "after"), result.get("series") or {}
    if not isinstance(m, dict) or not s.get("after"):
        return None
    return {"metrics": m, "series": {"dates": s.get("dates"), "values": s["after"]}, "verdict": result.get("verdict"),
            "checks": result.get("checks") or []}


def _engine():
    import pipeline                                         # noqa: PLC0415 (already loaded when pipeline.run calls)
    return pipeline.real_engine()


DEEP_KEYS = ("deep_history", "deep_validation", "deep_windows")
IN_PLACE = ("curve", "turbulence", "breaches", "variations")     # computed on rows the Result already has (no key of their own)


def _extended(result) -> bool:
    return any(isinstance(t, dict) and str(t.get("tool") or "").startswith("result_extras") for t in result.get("trace") or [])


def _deep_missing(result) -> bool:
    """The deep keys are all None and no pass failed on them (the cache was absent): a later pass may fill them."""
    failed = {f"result_extras.{k}" for k in DEEP_KEYS}
    return all(result.get(k) is None for k in DEEP_KEYS) and not any(
        isinstance(t, dict) and t.get("tool") in failed for t in result.get("trace") or [])


def _turbulence_missing(result) -> bool:
    return any(isinstance(r, dict) and "today_class" not in r for r in (result.get("turbulence") or {}).values())


def _curve_missing(result) -> bool:
    curve = _dig(result, "tipping_point", "curve") or []
    return any(isinstance(p, dict) and ("loss_dollars" not in p or "floor_margin_pp" not in p) for p in curve)


def _breaches_missing(result) -> bool:
    return any(isinstance(b, dict) and "fall_dollars" not in b for b in result.get("breaches") or [])


def _todo(result, refresh=()) -> set:
    """The keys a pass computes: all of them the first time; later, the keys a Result lacks (added to this module after
    the Result was extended), the deep keys left None by a machine without the deep cache, the curve's own keys when a
    point lacks one, and any key asked to be refreshed."""
    if not _extended(result):
        return set(KEYS) | set(IN_PLACE)
    return ({k for k in KEYS if k not in result} | (set(DEEP_KEYS) if _deep_missing(result) else set())
            | ({"curve"} if _curve_missing(result) else set())
            | ({"turbulence"} if _turbulence_missing(result) else set())
            | ({"breaches"} if _breaches_missing(result) else set())
            | ({"variations"} if _never_row_missing(result) else set()) | (set(refresh) & set(KEYS)))


def _has_facts(result, key) -> bool:
    return any(isinstance(t, dict) and t.get("tool") == f"result_extras.{key}" and "path" in (t.get("inputs") or {})
               for t in result.get("trace") or [])


def extend(result, *, engine=None, panel=None, proxy_map=None, episodes=None, refresh=(), only=None) -> dict:
    """Adds KEYS (and tipping_point.curve[i].loss_dollars, and the facts rows of the numbers the page shows from them)
    to a computed Result, in place; returns it. Never raises: a key that fails is None plus one trace row. A Result
    with no mix (a run stopped before COMPARE) gets every key as None. Idempotent: a Result already extended only gets
    what it lacks (`_todo`: keys added since, deep keys left None by an absent cache), with their facts, under one
    `result_extras.fill` row. `panel` / `proxy_map` / `episodes` default to tools.deep's."""
    if not isinstance(result, dict):
        return result
    again, todo = _extended(result), _todo(result, refresh)
    if only is not None:                                              # a frozen fixture: exactly these, nothing new
        todo = set(only) & (set(KEYS) | set(IN_PLACE))
    facts_for = {k for k in todo if not _has_facts(result, k)}       # a refreshed key keeps its facts rows (never twice)
    if not todo:
        return result
    if only is None:                                                  # --only adds no key a frozen fixture lacks
        for key in KEYS:
            result.setdefault(key, None)
    t0, done = time.perf_counter(), []
    try:
        rows, ins = _Rows(result), inputs(result)
        if not ins["today"] or not ins["as_of"]:
            return result
        engine = engine if engine is not None else _engine()
    except Exception:                                       # nothing readable: the keys stay None
        return result

    def put(key, fn):
        if key not in todo:
            return
        try:
            result[key] = fn()
            done.append(key)
        except Exception as exc:                            # noqa: BLE001 (the run never stops for an extra)
            result[key] = None
            rows.failed(key, exc)

    if "curve" in todo:
        try:
            curve_dollars(result)
            done.append("curve")
        except Exception as exc:                            # noqa: BLE001
            rows.failed("tipping_point.curve.loss_dollars", exc)
    if "turbulence" in todo:
        try:
            turbulence_classes(result)
            done.append("turbulence")
        except Exception as exc:                            # noqa: BLE001
            rows.failed("turbulence.classes", exc)
    if "breaches" in todo:
        try:
            breach_dollars(result)
            done.append("breaches")
        except Exception as exc:                            # noqa: BLE001
            rows.failed("breaches.fall_dollars", exc)
    put("end_values", lambda: end_values(result))
    put("not_2022", lambda: not_2022(ins, engine))
    put("tipping_band", lambda: tipping_band(ins, engine))
    put("ladder", lambda: ladder(ins, engine, _own_run(result)))
    put("reconciliation", lambda: reconciliation(ins, engine))
    put("navigator_effect", lambda: navigator_effect(result, ins, engine))
    put("hedge_compare", lambda: hedge_compare(ins, engine))
    put("capacity", lambda: capacity(result, ins))                          # fix wave lane fin-backend (R35, R36)
    put("peer_check", lambda: peer_check(ins, engine))
    put("never_rebalanced", lambda: never_rebalanced(ins, engine, len(result.get("breaches") or []) if ins["after"] else None))
    if "variations" in todo or "never_rebalanced" in done:
        try:
            if never_row(result):
                done.append("variations")
        except Exception as exc:                            # noqa: BLE001
            rows.failed("variations.never_rebalanced", exc)
    put("funding_check", lambda: funding_check(ins, engine, _own_run(result)))
    put("volatility", lambda: volatility(ins, engine))
    put("funds", lambda: funds(result, ins))                                # lane funds: fund-level aggregates only
    put("scenarios", lambda: __import__("tools.factors", fromlist=["result_key"]).result_key(  # lane sc-b
        ins, rows.fact, result=result))
    deep = {}
    if todo & set(DEEP_KEYS):
        try:
            deep = deep_inputs(ins, engine, panel=panel, proxy_map=proxy_map, episodes=episodes)
        except Exception as exc:                            # noqa: BLE001
            rows.failed("deep_history", exc)
    if deep.get("panel") is not None:
        put("deep_history", lambda: deep_history(ins, deep))
        put("deep_validation", lambda: deep_validation(result, ins, deep))
        put("deep_windows", lambda: deep_windows(ins, deep))
    if again and not done and not (todo & set(DEEP_KEYS) and not _deep_missing(result)):
        return result                                       # nothing new: no second summary row
    n_facts = len(result.get("facts") or {})
    try:
        add_facts(rows, result, ins, keys=facts_for)
    except Exception as exc:                                # noqa: BLE001
        rows.failed("facts", exc)
    if not again or len(result.get("facts") or {}) != n_facts:   # the evidence follows the facts (a public cut keeps its own)
        todo.add("evidence")
        put("evidence", lambda: evidence(result))
    rows.add("result_extras.fill" if again else "result_extras", inputs={"keys": sorted(todo)}, outputs={"computed": done},
             source="result_extras.extend (lane B3): the Replay keys, computed by code", ms=(time.perf_counter() - t0) * 1000)
    return result


def main(argv=None) -> int:
    """Offline (no AWS): add the Replay keys to saved Results. A file may be a Result or a saved run {..., "result"}."""
    ap = argparse.ArgumentParser(description=main.__doc__)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--out", help="write the extended copies to this directory (default: replace each file)")
    ap.add_argument("--refresh", default="", help="comma-separated keys to compute again (their facts rows are kept)")
    ap.add_argument("--only", default=None, help="comma-separated keys (or 'curve') to compute, and nothing else")
    args = ap.parse_args(argv)
    from pipeline import jsonable                           # noqa: PLC0415
    for name in args.paths:
        path = Path(name)
        data = json.loads(path.read_text(encoding="utf-8"))
        res = data["result"] if isinstance(data.get("result"), dict) else data
        t0 = time.perf_counter()
        only = None if args.only is None else tuple(k.strip() for k in args.only.split(",") if k.strip())
        extend(res, refresh=tuple(k.strip() for k in args.refresh.split(",") if k.strip()), only=only)
        out = Path(args.out) / path.name if args.out else path
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(out.name + ".tmp")
        tmp.write_text(json.dumps(jsonable(data), allow_nan=False, separators=(",", ":")), encoding="utf-8")   # server.to_json
        tmp.replace(out)
        print(f"{path.name}: {', '.join(k for k in KEYS if res.get(k) is not None)} ({time.perf_counter() - t0:.1f} s) -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
