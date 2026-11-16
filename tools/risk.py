"""Risk share, independent bets and diversification (spec sections 5 and 10; plan A Task 8; ledger 1, 7, 14, 26).

"x % of your money, y % of your risk" and "behaves like n independent bets": money and risk are spread
differently, and ten tech stocks are not ten bets. History of the past only, never a forecast. The rules:
  1. `asset_returns` = the held lines' daily CAD returns with exactly the day rule of
     `tools.portfolio.series_from_market`: prices cut to `date <= as_of` FIRST (red gate 3), carried forward,
     a day counts only if at least one held exchange traded, the return runs between consecutive counted
     days (a US line keeps the USD/CAD move of a TSX-only day), no price yet = 0, the first row dropped. So the
     risk is measured on the very series that is judged (ledger 12).
  2. `risk_contributions`: sigma = the sample covariance (ddof 1) of those returns; RC_i = w_i (sigma w)_i /
     (w' sigma w), which sums to 1 and is negative for a hedge. Independent bets = Meucci's effective number of
     bets, ENB = exp(-sum p_k ln p_k) with p_k = lambda_k (w' e_k)^2 / (w' sigma w) over the principal
     components of sigma (ledger 14: 1/sum(RC^2) is retired), computed on the direct lines.
     The axes of EQUAL eigenvalues are not unique (two uncorrelated lines of equal volatility are an isotropic
     sigma: every rotation is a valid PCA, and float noise of about 1e-14 would pick one at random). So sigma is
     rounded to 10 significant digits of its largest entry before the eigen-decomposition: such lines then form an
     exactly diagonal matrix, keep their own axes and count as independent bets (2.0) on any platform. Other
     exact ties (three equicorrelated lines, say) are still decided by float noise: real covariances do not tie,
     and the PCA entropy is sensitive near a tie by definition (ledger 14).
  3. Fewer than 2 return days, or a variance of rounding noise only (a flat or constant-growth path): `shares`
     = the money weights, `bets` = 1 / sum(w^2), `degenerate` True. Never a division by zero.
  4. `diversification`: look-through countries (borderless crypto and gold included, they sum to 1), the money
     share by listing currency (CAD, USD, OTHER), the 5 largest look-through sectors, and `can_risk_share` =
     sum_i RC_i x CAN_i, the share of the RISK that sits in Canada (the workshop's "too Canadian?" question):
     CAN_i is line i's own Canadian share, from the same holdings mode as the look-through (an ETF by its
     country rows, else its listing country). Without a look-through it builds one at `as_of`, so a past date
     is direct holdings, flagged (today's snapshot is never a past picture). A supplied look-through dated
     AFTER `as_of` is not used either (red gate 3, ledger 30): direct mode, flagged in `source`; one dated on or
     before `as_of` is used as given (an older one names its date in `source`). The six-key output has no
     `degenerate` flag, so `source` carries the caveats (red gate 4): "risk could not be measured" when the risk is
     degenerate (then `can_risk_share` is the money-weighted Canadian share), and one sentence when the share is
     above 100 % or below 0 % because a hedge has negative risk. `risk_contributions` says the same in its `source`.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import numpy as np
import pandas as pd

from tools.data import SOURCE, load_market
from tools.lookthrough import load_holdings, look_through
from tools.portfolio import _held      # the one weight check: tickers upper-cased, none below 0, sum 1

MIN_DAYS = 2                           # a sample covariance needs two return days
NO_VARIANCE = 1e-24                    # a portfolio variance below this (a daily vol of 1e-12) is rounding noise
TIE_DIGITS = 10                        # sigma is rounded to this many digits of its largest entry before the PCA
RISK_SOURCE = ("Daily CAD returns of the held lines up to as_of, constant weights rebalanced daily; risk share = "
               "w_i (cov w)_i / (w' cov w) with the sample covariance; independent bets = Meucci's effective "
               "number of bets over the principal components; history, not a forecast. " + SOURCE)
NOT_MEASURED = ("risk could not be measured on these dates (too few or flat returns), so it is shown at the money "
                "weights")           # red gate 4: when the data cannot support a conclusion, say so
DEGENERATE_SOURCE = ("Not measured: " + NOT_MEASURED + "; independent bets are then 1 / (sum of the squared money "
                     "weights)")
OFFSET_ABOVE = "above 100 % because a line with negative risk offsets the others"
OFFSET_BELOW = "below 0 % because the Canadian lines carry negative risk, which offsets the others"
OUTSIDE = 1e-9                         # a Canadian risk share this far outside 0 to 100 % is an offset, not rounding


def _iso(day) -> str:
    return pd.Timestamp(day).strftime("%Y-%m-%d")


def _label(market: dict, day: str) -> str:
    """The last calendar day in the data on or before `day` (the request itself before the first day)."""
    seen = market["calendar"][market["calendar"] <= pd.Timestamp(day)]
    return _iso(seen[-1]) if len(seen) else _iso(min(pd.Timestamp(day), pd.Timestamp(market["as_of"])))


def asset_returns(weights, as_of, *, market=None) -> pd.DataFrame:
    """Daily CAD returns of the held lines (columns in the order of `weights`), dates <= `as_of` only.

    The day rule is `series_from_market`'s (module docstring, rule 1), so `returns @ weights` is the daily
    return of `portfolio_series` from its second day on. Unknown ticker or weights not summing to 1: ValueError.
    """
    day = _iso(as_of)
    m = market if market is not None else load_market(day)
    held = _held(weights)
    cols = list(held)
    for t in cols:
        if t not in m["prices"].columns:
            raise ValueError(f"Unknown ticker: {t}")
    end = pd.Timestamp(day)
    prices = m["prices"].loc[:end, cols].ffill()                       # nothing after as_of reaches the fill
    prices = prices[m["traded"].loc[:end, cols].any(axis=1)]
    return prices.pct_change(fill_method=None).fillna(0.0).iloc[1:]


def _effective_bets(cov: np.ndarray, w: np.ndarray) -> float:
    """Meucci's effective number of bets (module docstring, rule 2); between 1 and the number of lines."""
    scale = float(np.max(np.abs(cov)))
    tidy = np.round(cov / scale, TIE_DIGITS) * scale                    # float noise gone: a tie stays a tie
    values, axes = np.linalg.eigh(tidy)                                 # principal portfolios (columns of axes)
    p = np.clip(values, 0.0, None) * (axes.T @ w) ** 2                  # variance carried by each of them
    p = p[p > 0.0] / p.sum()
    return float(np.clip(np.exp(-np.sum(p * np.log(p))), 1.0, len(w)))


def risk_contributions(weights, as_of, *, market=None) -> dict:
    """{"shares": {ticker: RC}, "bets": float, "degenerate": bool, "source", "as_of"} (ledger 1, 7, 14).

    `shares` sum to 1, biggest first (a hedge is negative); `bets` is the effective number of independent
    bets (1.0 = one bet, the number of lines = all independent and equally risky). Both from the covariance of
    `asset_returns` dated <= `as_of`. `degenerate` True (fewer than 2 return days, or no variance at all) means
    the risk could not be measured: `shares` are then the money weights and `bets` = 1 / sum(w^2), so the
    caller can say so. Unknown ticker or weights not summing to 1: ValueError. Module docstring: the rules.
    """
    day = _iso(as_of)
    m = market if market is not None else load_market(day)
    r = asset_returns(weights, day, market=m)
    money = {t: float(w) for t, w in _held(weights).items()}
    w = np.array([money[t] for t in r.columns])
    cov = np.atleast_2d(np.cov(r.to_numpy(), rowvar=False, ddof=1)) if len(r) >= MIN_DAYS else None
    var = float(w @ cov @ w) if cov is not None else 0.0
    degenerate = not (np.isfinite(var) and var > NO_VARIANCE)
    if degenerate:
        shares, bets = money, float(1.0 / np.sum(w ** 2))
    else:
        shares = dict(zip(r.columns, (w * (cov @ w) / var).tolist()))
        bets = _effective_bets(cov, w)
    ranked = dict(sorted(shares.items(), key=lambda kv: (-kv[1], kv[0])))
    return {"shares": ranked, "bets": bets, "degenerate": degenerate,
            "source": DEGENERATE_SOURCE if degenerate else RISK_SOURCE, "as_of": _label(m, day)}


def _look(held: dict, lookthrough, universe: pd.DataFrame, day: str) -> dict:
    """The look-through behind `diversification` (module docstring, rule 4).

    The caller's own when it is dated on or before the decision `day`; none given: one built at `day`. One dated AFTER
    `day` is a picture of later holdings, so it is not used (red gate 3, ledger 30): the answer is direct mode (each
    fund counts as its listing country), and `source` says so. One dated EARLIER is used as given, and `source` names
    both dates (the output is labelled with the decision day, so the older picture must not pass for a fresh one).
    """
    if lookthrough is None:
        return look_through(held, universe=universe, esg_flags=set(), as_of=day)
    dated = lookthrough.get("as_of")
    if dated is None or _iso(dated) == day:
        return lookthrough
    if _iso(dated) < day:
        return {**lookthrough, "source": (f"{lookthrough['source']} (the look-through is dated {_iso(dated)}, earlier "
                                          f"than the decision date {day})")}
    direct = look_through(held, holdings=pd.DataFrame(), universe=universe, esg_flags=set(), as_of=day)
    return {**direct, "source": (f"direct holdings: the look-through is dated {_iso(dated)}, after the decision date "
                                 f"{day}, so it is not used and each fund counts as its listing country "
                                 "(assets_universe.csv)")}


def _can_shares(held: dict, look: dict, universe: pd.DataFrame, day: str) -> dict:
    """Each held line's own share in Canada, from the same holdings mode as the look-through `look`."""
    frame = pd.DataFrame()                                  # direct mode: a line is its listing country
    if look["mode"] == "lookthrough":
        found = load_holdings()                             # read once; the file is local (pitfall 10)
        frame = frame if found is None else found
    return {t: float(look_through({t: 1.0}, holdings=frame, universe=universe, esg_flags=set(),
                                  as_of=look.get("as_of") or day)["countries"].get("CAN", 0.0)) for t in held}


def _risk_words(degenerate: bool, can_risk: float) -> str:
    """How the Canadian risk share's `source` says it was measured (red gate 4): not measured, offset, or the method."""
    if degenerate:
        return NOT_MEASURED                                 # the shares are the money weights: no covariance behind them
    if can_risk > 1.0 + OUTSIDE:
        return f"{OFFSET_ABOVE}; {RISK_SOURCE}"
    if can_risk < -OUTSIDE:
        return f"{OFFSET_BELOW}; {RISK_SOURCE}"
    return RISK_SOURCE


def diversification(weights, as_of, *, lookthrough=None, universe=None, market=None) -> dict:
    """{"countries", "currencies": {"CAD", "USD", "OTHER"}, "sectors" (5 largest), "can_risk_share", "source", "as_of"}.

    `countries` and `sectors` are the look-through's, biggest first (`countries` keeps CRYPTO and GLOBAL, so
    it sums to 1); `currencies` = the money share by the listing currency of the direct lines;
    `can_risk_share` = sum of RC_i x the line's Canadian share (module docstring, rule 4); it is not clamped:
    a non-Canadian hedge has a negative RC, so the Canadian lines can carry more than 100 %, and when the
    risk is degenerate the RCs are the money weights. `source` says so in each case (red gate 4): "risk could
    not be measured ..." instead of the covariance method when degenerate, and one sentence when the share is
    above 100 % or below 0 % because a line with negative risk offsets the others. `lookthrough=None` builds the
    look-through at `as_of`; a supplied one dated on or before `as_of` is used as given (an older date is named in
    `source`), one dated after it is not used (direct mode, flagged in `source`: red gate 3, ledger 30). A supplied
    look-through must come from the local holdings file: the per-line Canadian shares are read from that file (or
    are listing countries in direct mode). `universe=None` takes the bundle's. `as_of` labels the decision date's
    last data day. Unknown ticker or weights not summing to 1: ValueError.
    """
    day = _iso(as_of)
    m = market if market is not None else load_market(day)
    held = _held(weights)
    uni_df = m["universe"] if universe is None else universe
    listing = uni_df.set_index("ticker")["currency"]
    for t in held:
        if t not in listing.index:
            raise ValueError(f"Unknown ticker: {t}")
    look = _look(held, lookthrough, uni_df, day)
    risk = risk_contributions(held, day, market=m)
    currencies = {"CAD": 0.0, "USD": 0.0, "OTHER": 0.0}
    for t, w in held.items():
        currencies[str(listing[t]) if str(listing[t]) in ("CAD", "USD") else "OTHER"] += w
    can = _can_shares(held, look, uni_df, day)

    def ranked(book: dict) -> dict:
        return {k: float(v) for k, v in sorted(book.items(), key=lambda kv: (-kv[1], kv[0]))}

    can_risk = float(sum(risk["shares"][t] * can[t] for t in held))
    return {"countries": ranked(look["countries"]), "currencies": {k: float(v) for k, v in currencies.items()},
            "sectors": dict(list(ranked(look["sectors"]).items())[:5]), "can_risk_share": can_risk,
            "source": ("Look-through exposure: " + look["source"] + "; currencies: the listing currency of each "
                       "direct line (assets_universe.csv); Canadian risk share: "
                       + _risk_words(risk["degenerate"], can_risk)),
            "as_of": risk["as_of"]}


def _whole(x) -> int:
    """To the dollar, ROUND_HALF_UP through repr (the rounding of result_extras' capacity key)."""
    return int(Decimal(repr(float(x))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def capacity_line(series: dict, amount, capacity) -> dict:
    """Ruling R35's second limit as a pure function: a base-100 series {"dates", "values"} in dollars (amount x
    value / 100, to the cent) against the line amount - capacity. Returns {"line", "low_value" (whole dollars),
    "low_date" (the first lowest day), "sessions_below", "first_below", "last_below"} (None when it never goes
    below). ValueError unless 0 < capacity < amount, or for a series without values or without one date per value."""
    if not 0 < capacity < amount:
        raise ValueError("The capacity for loss must be above 0 and below the amount.")
    dates, values = list(series["dates"]), np.asarray(list(series["values"]), dtype="float64")
    if not len(values) or len(dates) != len(values):
        raise ValueError("The series needs one value per date, and at least one.")
    line = amount - capacity
    dollars = np.round(amount * values / 100.0, 2)
    below = np.nonzero(dollars < line)[0]
    low = int(np.argmin(dollars))
    return {"line": line, "low_value": _whole(dollars[low]), "low_date": dates[low], "sessions_below": int(len(below)),
            "first_below": dates[below[0]] if len(below) else None,
            "last_below": dates[below[-1]] if len(below) else None}
