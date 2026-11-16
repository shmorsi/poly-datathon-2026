"""Portfolio weights, the one weight operator and the constant-weight series (spec section 10).

Weights are fractions that sum to 1. Every change the product makes to a portfolio (the size
slider, the comparison menu, the navigator's "put 40 % in NVIDIA") goes through `apply_change`,
so the weights a rule checks are the weights the series measures. Nothing here reads a price
dated after `as_of`: the series functions take the market bundle of tools.data.
"""
from __future__ import annotations

import math

import pandas as pd

from tools.data import DATASET_END, SOURCE, load_market, load_universe

PERCENT_ABOVE = 1.5        # typed rows whose total is above this are percent, else fractions
TOLERANCE = 1e-6           # "sums to 1" and "at most 100 %" hold within this
_DUST = 1e-12              # a line this small is a line at 0
PARSE_SOURCE = ("Entered by the user (fictional portfolio, never stored); tickers checked against "
                "the 31 assets of the starter universe")
SERIES_SOURCE = f"{SOURCE}; constant weights rebalanced every day, base 100"


# --- reading and cleaning weights ----------------------------------------------------------------
def _number(raw, label: str) -> float:
    """A typed weight as a float: 45, '45', '45 %', 0.45. Blank, None or an empty cell (a float
    NaN) gives NaN (row dropped). Typed text that is not a finite number ("lots", "inf", "-inf",
    "nan") raises ValueError: it is an invalid row, never a weight.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return math.nan
    try:
        value = float(raw.strip().rstrip("%").strip()) if isinstance(raw, str) else float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"Cannot read the weight for {label}: {raw!r}.") from None
    if math.isinf(value) or (math.isnan(value) and isinstance(raw, str)):
        raise ValueError(f"Cannot read the weight for {label}: {raw!r}.")
    return value


def parse_weights(rows, *, universe=None) -> dict:
    """Typed rows [{"ticker", "weight"}] -> {"weights", "unknown", "sum", "source", "as_of"}.

    Tickers are stripped and upper-cased, duplicates add up, rows at 0 or below (and blank rows)
    are dropped. The rows are read as percent when their total is above 1.5, else as fractions
    (the table and the CSV show %, a file of fractions still works). Tickers outside the universe
    go to `unknown` and are excluded. Weights are NOT normalized: `sum` feeds the sum badge.
    """
    known = set((load_universe() if universe is None else universe)["ticker"])
    entered: dict[str, float] = {}
    for row in rows:
        raw = row.get("ticker")
        ticker = "" if raw is None or raw != raw else str(raw).strip().upper()   # None/NaN = blank cell
        weight = _number(row.get("weight"), ticker or "a blank row")
        if ticker and weight > 0:                       # NaN > 0 is False: blank cells drop out
            entered[ticker] = entered.get(ticker, 0.0) + weight
    scale = 100.0 if sum(entered.values()) > PERCENT_ABOVE else 1.0
    weights = {t: w / scale for t, w in entered.items() if t in known}
    return {"weights": weights, "unknown": [t for t in entered if t not in known],
            "sum": float(sum(weights.values())), "source": PARSE_SOURCE, "as_of": DATASET_END}


def normalize(weights: dict) -> dict:
    """Scale to sum 1 (the "Normalize" button). Lines at 0 or below are dropped."""
    kept = {t: float(w) for t, w in weights.items() if w and float(w) > _DUST}
    total = sum(kept.values())
    if total <= 0:
        raise ValueError("Nothing to normalize: enter at least one weight above 0.")
    return {t: w / total for t, w in kept.items()}


# --- the one weight operator ---------------------------------------------------------------------
def _held(weights: dict) -> dict:
    """A copy of the lines above 0, checked: tickers stripped and upper-cased (two spellings of
    one ticker are one line, their weights add up), weights numbers, finite, none negative,
    summing to 1.
    """
    held: dict[str, float] = {}
    for t, w in weights.items():
        ticker = str(t).strip().upper()
        try:
            value = float(w)
        except (TypeError, ValueError):
            raise ValueError(f"The weight of {ticker} must be a number (got {w!r}).") from None
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"The weight of {ticker} must be 0 or more.")
        if value > _DUST:
            held[ticker] = held.get(ticker, 0.0) + value
    total = sum(held.values())
    if abs(total - 1.0) > TOLERANCE:
        raise ValueError(f"The weights must add up to 100 % (they add up to {total * 100:.1f} %); "
                         "use Normalize first.")
    return held


def _fraction(change: dict) -> float:
    raw = change.get("weight")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"The change needs a weight between 0 % and 100 % (got {raw!r}).") from None
    if not math.isfinite(value) or not -TOLERANCE <= value <= 1 + TOLERANCE:
        raise ValueError(f"The weight must be between 0 % and 100 % (got {value * 100:.1f} %).")
    return min(max(value, 0.0), 1.0)


def _set(held: dict, ticker: str, x: float) -> dict:
    """T = x and every other line x (1 - x) / (1 - T_old), so the weights still sum to 1."""
    old = held.get(ticker, 0.0)
    if x >= 1.0 - _DUST:
        return {ticker: 1.0}
    if old >= 1.0 - _DUST:
        raise ValueError(f"Nothing else to scale: {ticker} is the only line, so it cannot be set "
                         "below 100 %.")
    factor = (1.0 - x) / (1.0 - old)
    out = {t: w * factor for t, w in held.items() if t != ticker}
    out[ticker] = x
    return out


class SourceShort(ValueError):
    """A funded move asks more of its source than the portfolio holds there (the reader asks one question instead)."""

    def __init__(self, source, held, asked):
        self.source, self.held, self.asked = source, held, asked
        super().__init__(f"{source} is {held * 100:.0f} % of your money; {asked * 100:.0f} % cannot come from there alone.")


def _move(held: dict, ticker: str, w: float, source: str) -> dict:
    """move w from A into T (Sun Nov 15, the lead: "which part of the portfolio would the 40 % replace? It matters."):
    A loses w, T gains w, every other line unchanged. A must be held and hold at least w: never a silent clamp."""
    if not source:
        raise ValueError("A move needs the holding it is taken from.")
    if source == ticker:
        raise ValueError(f"{ticker} cannot be moved into itself.")
    if source not in held:
        raise ValueError(f"Cannot take it from {source}: it is not in the portfolio.")
    if w > held[source] + TOLERANCE:
        raise SourceShort(source, held[source], w)
    out = dict(held)
    out[source] = max(0.0, held[source] - w)
    out[ticker] = held.get(ticker, 0.0) + w
    return out


def _finish(out: dict) -> dict:
    """Drop the lines at 0 and renormalize, so the weights sum to 1 to the last digit."""
    kept = {t: w for t, w in out.items() if w > _DUST}
    total = sum(kept.values())
    return {t: w / total for t, w in kept.items()}


def apply_change(weights: dict, change: dict) -> dict:
    """The one weight operator (spec section 10). Returns a new dict; the input is untouched.

    change = {"op": "set|add|replace|move", "ticker", "weight", "from_ticker"}:
      set      T to x      -> T = x, every other line x (1 - x) / (1 - T_old) (T_old = 0 if not held)
      move     x from A    -> A loses x and T gains x, every other line unchanged (A must hold at least x)
      add      x of T      -> set T to T_old + x (more than 100 % is refused)
      replace  A with B    -> B takes A's weight (added to B if B is held); A must be held
    Held tickers are stripped and upper-cased, so "nvda" and "NVDA" are one line. Lines at 0 are
    removed and the result sums to 1. An impossible change raises ValueError with
    a plain sentence: unknown op or ticker missing, weight outside 0-100 %, input not summing
    to 100 %, A not held, or `set` below 100 % when T is the only line.
    """
    held = _held(weights)
    op = str(change.get("op") or "").strip().lower()
    ticker = str(change.get("ticker") or "").strip().upper()
    if op not in ("set", "add", "replace", "move"):
        raise ValueError(f"Unknown change {change.get('op')!r}: use set, add, replace or move.")
    if not ticker:
        raise ValueError("The change needs a ticker.")
    if op == "move":
        return _finish(_move(held, ticker, _fraction(change), str(change.get("from_ticker") or "").strip().upper()))
    if op == "set":
        return _finish(_set(held, ticker, _fraction(change)))
    if op == "add":
        total = held.get(ticker, 0.0) + _fraction(change)
        if total > 1.0 + TOLERANCE:
            raise ValueError(f"That would put {ticker} at {total * 100:.1f} %, above 100 %.")
        return _finish(_set(held, ticker, min(total, 1.0)))
    source = str(change.get("from_ticker") or "").strip().upper()
    if source not in held:
        raise ValueError(f"Cannot replace {source or 'a ticker that was not named'}: it is not in "
                         "the portfolio.")
    out = {t: w for t, w in held.items() if t != source}
    out[ticker] = out.get(ticker, 0.0) + held[source]
    return _finish(out)


# --- the constant-weight series ------------------------------------------------------------------
def series_from_market(weights: dict, market: dict, start=None) -> pd.Series:
    """Portfolio value, base 100 on the first counted day on or after `start` (pure, CAD).

    Constant weights: the portfolio is rebalanced to its target every day, so the daily return is
    returns @ weights. A day counts only if at least one held asset's exchange traded (`traded`;
    crypto trades every day). Prices are carried forward over any gap and the return runs from
    one counted day to the next, so a move across an unfilled gap (or a closed-exchange day's FX
    move) is booked when trading resumes; an asset with no price yet returns 0.
    """
    held = pd.Series(_held(weights), dtype=float)
    cols = list(held.index)
    for t in cols:
        if t not in market["prices"].columns:
            raise ValueError(f"Unknown ticker: {t}")
    prices = market["prices"][cols].ffill()
    prices = prices[market["traded"][cols].any(axis=1)]
    if start is not None:
        prices = prices.loc[pd.Timestamp(start):]
    daily = (prices.pct_change(fill_method=None).fillna(0.0) * held).sum(axis=1)
    return (100.0 * (1.0 + daily).cumprod()).rename("portfolio").rename_axis("date")


def portfolio_series(weights, start=None, end=None, as_of=DATASET_END, *, market=None, union=False) -> dict:
    """Spec section 12: {"dates" (ISO), "values" (base 100), "source", "as_of"}, never past as_of.

    `as_of` names the last date actually in the data: the last calendar day on or before the
    requested as_of (a bundle's own `as_of` is only the cutoff it was built for), so a request for
    2030-01-01 is labelled DATASET_END and a Saturday is labelled the Friday before it. Before the
    first data day it is the request itself.

    `union=True` (D Task 6b, ruling R3) reports the series on every day of the bundle's calendar (the
    union of TSX and US trading days) from `start` to the cut, so every mix of one comparison (today,
    after, each size of the slider) has the same dates: a day none of the mix's lines traded keeps
    the last value (its move is booked on the next counted day, as across any gap) and a day before
    the first counted day is the base 100. The values on the mix's own counted days are unchanged.
    """
    m = market if market is not None else load_market(as_of)
    hi = pd.Timestamp(as_of) if end is None else min(pd.Timestamp(end), pd.Timestamp(as_of))
    cut = {**m, "prices": m["prices"].loc[:hi], "traded": m["traded"].loc[:hi]}
    s = series_from_market(weights, cut, start)
    if union and len(s):
        days = m["calendar"][m["calendar"] <= hi]
        days = days[days >= pd.Timestamp(start)] if start is not None else days
        s = s.reindex(days).ffill().fillna(100.0)
    seen = m["calendar"][m["calendar"] <= pd.Timestamp(as_of)]
    label = seen[-1] if len(seen) else min(pd.Timestamp(as_of), pd.Timestamp(m["as_of"]))
    return {"dates": s.index.strftime("%Y-%m-%d").tolist(), "values": s.tolist(),
            "source": SERIES_SOURCE, "as_of": label.strftime("%Y-%m-%d")}
