"""The size curve, the code's variations of the investor's own move, the floor sensitivity, the price of values and
the fictional illustration mixes (plan B Task 6; ledger 2, 6, 29, 30; spec 10; spec 24 resolution 7).

Every verdict here is governance.evaluate's, the one judge: no second formula, no browser arithmetic. Nothing here
writes a target size: the pipeline phrases the size fact as history ("in this history, your floor breaks above x"),
and the variations carry their kind and numbers, never a label the page prints (ledger 30). No row puts another
security in the investor's place, and the price of values runs on the investor's own portfolio (resolution 7).
"""
import contextlib
import copy
import functools
import json
import threading

import config
import governance
from tools.data import DATASET_END, load_market
from tools.events import load_events
from tools.portfolio import apply_change, normalize

SOURCE = "tools.allocation"
LABEL = "Fictional illustration, not a recommendation"
LOOSEST_TENTHS, STRICTEST_TENTHS = -600, -1      # the floor scan, in tenths of a percent point: -60 % ... -0.1 %
STILL_BEYOND = {"single_stock": "single-company", "sector": "single-sector", "crypto": "crypto",
                "scenario_stress": "turbulence", "esg_direct": "values"}
DUST = 1e-9                                       # a weight change smaller than this is no change

# spec 10, the fallback when data/personas.json has no `illustration_mixes` (C Task 1, e6b84a3, is the truth);
# a key missing from both is built from its band's mix by the two rules (_with_esg, _with_crypto)
BUILT_IN_MIXES = {
    "low": {"XBB.TO": 25, "ZST.TO": 25, "XIU.TO": 25, "SPY": 15, "GLD": 10},
    "moderate": {"XBB.TO": 30, "XIU.TO": 35, "SPY": 25, "GLD": 10},
    "moderate_esg": {"XBB.TO": 35, "ESGV": 55, "GLD": 10},
    "high": {"XBB.TO": 15, "XIU.TO": 30, "SPY": 20, "QQQ": 25, "GLD": 10},
}


def binding_rule(checks: list[dict]) -> str | None:
    """The check that decides the verdict: the first failing hard row, else the first failing soft or preference row,
    else the first warn, in row order (governance.check_order's binding row). None when every row passes."""
    rows = checks or []
    hit = (next((c for c in rows if c["status"] == "fail" and c["tier"] == "hard"), None)
           or next((c for c in rows if c["status"] == "fail"), None)
           or next((c for c in rows if c["status"] == "warn"), None))
    return hit["rule"] if hit else None


# ---- the illustration mixes (fiction, never on screen: spec 24 resolution 7; the pipeline keeps them computed) ----

@functools.lru_cache(maxsize=1)
def _personas_file_mixes() -> tuple:
    try:
        with open(config.PERSONAS_JSON, encoding="utf-8") as handle:
            found = json.load(handle).get("illustration_mixes") or {}
    except FileNotFoundError:
        found = {}
    return tuple((key, tuple(sorted(mix.items()))) for key, mix in sorted(found.items()))


def _personas_mixes() -> dict:
    """data/personas.json `illustration_mixes` ({} when the file or the key is missing)."""
    return {key: dict(mix) for key, mix in _personas_file_mixes()}


def _with_esg(mix: dict) -> dict:
    """ESGV replaces SPY and takes XIU.TO's share (spec 10)."""
    out = {t: w for t, w in mix.items() if t not in ("SPY", "XIU.TO")}
    out["ESGV"] = out.get("ESGV", 0) + mix.get("SPY", 0) + mix.get("XIU.TO", 0)
    return out


def _with_crypto(mix: dict) -> dict:
    """10 % BTC-USD taken from QQQ (spec 10; the high band only)."""
    total = sum(mix.values())
    take = min(0.10 * total, mix.get("QQQ", 0))
    out = {**mix, "QQQ": mix.get("QQQ", 0) - take, "BTC-USD": mix.get("BTC-USD", 0) + take}
    return {t: w for t, w in out.items() if w > 0}


def _band(profile: dict) -> str | None:
    return profile.get("risk") or config.REACTION_TO_RISK.get(profile.get("reaction_2022"))


def aligned_allocation(profile: dict | None) -> dict | None:
    """The fictional illustration mix of the profile's band: key = band (+ "_crypto" when crypto and the band is high)
    (+ "_esg" with the values screen). personas.json first, then the built-in table, then the band's mix with the
    rules applied. Normalized to sum 1. None without a profile or a band."""
    band = _band(profile) if profile else None
    if band not in BUILT_IN_MIXES:
        return None
    crypto, esg = bool(profile.get("crypto")) and band == "high", bool(profile.get("esg"))
    key = band + ("_crypto" if crypto else "") + ("_esg" if esg else "")
    known = {**BUILT_IN_MIXES, **_personas_mixes()}
    if key in known:
        mix, rule = known[key], f"illustration mix {key!r}"
    else:
        mix = dict(known[band])
        mix = _with_crypto(mix) if crypto else mix
        mix = _with_esg(mix) if esg else mix
        steps = (["10 % BTC-USD taken from QQQ"] if crypto else []) + (
            ["ESGV replaces SPY and takes XIU.TO's share"] if esg else [])
        rule = f"illustration mix {band!r}, " + "; ".join(steps)
    return {"weights": normalize(mix), "label": LABEL, "rule": rule, "source": SOURCE, "as_of": DATASET_END}


# ---- one replay bundle, one judge ----

def _bundle(as_of: str, market, events):
    """The market and the storm catalog, loaded once per call and passed to every judgement (red gate 3: both are
    cut at `as_of`)."""
    market = load_market(as_of) if market is None else market
    events = load_events(as_of, market=market) if events is None else events
    return market, events


def _families(families, event_ids, events):
    """The navigator's families exactly as given (`[]` is its abstention, ledger 30); none given: the families of
    `event_ids` found in the catalog, else None (governance replays all four: the shock check judges whole
    families, spec 5)."""
    if families is not None:
        return list(families)
    wanted = set(event_ids or ())
    found = {e.get("family") for e in events or () if e.get("event_id") in wanted}
    named = [f for f in config.FAMILIES if f in found]
    return named or None


_MEMO = threading.local()          # .judged: one run's judged mixes while `judge_memo` is open (else no reuse)


@contextlib.contextmanager
def judge_memo():
    """Within one run (the pipeline's COMPARE extras) the same mix is judged once: the move's size curve and the
    variations' own curve are the same 0-100 % points (jury QA S6: 100 % NVIDIA judged ~200 mixes twice, 60 s live).
    The same inputs give the same answer (a copy each time), so no number changes; nothing is kept after the block."""
    outer = getattr(_MEMO, "judged", None)
    _MEMO.judged = {} if outer is None else outer
    try:
        yield
    finally:
        _MEMO.judged = outer


def _judge(profile, weights, families, as_of, market, events, limits, amount) -> dict:
    judged, key = getattr(_MEMO, "judged", None), None
    if judged is not None:                 # the market and events objects a run passes stay put (and alive) while it runs
        key = json.dumps([profile, sorted((str(t), float(w)) for t, w in weights.items()), families, str(as_of),
                          limits, amount, id(market), id(events)], sort_keys=True, default=str)
        hit = judged.get(key)
        if hit is not None and hit[0] is market and hit[1] is events:
            return copy.deepcopy(hit[2])
    ev = governance.evaluate(profile, weights, families, as_of, market=market, events=events, limits=limits,
                             amount=amount, detail=False)
    if key is not None:
        judged[key] = (market, events, copy.deepcopy(ev))
    return ev


def _today(weights: dict) -> dict:
    """Today's weights as apply_change keeps them: tickers stripped and upper-cased, summing to 1 (ledger 12:
    callers normalize first)."""
    merged: dict[str, float] = {}
    for t, w in normalize(weights).items():
        key = str(t).strip().upper()
        merged[key] = merged.get(key, 0.0) + w
    return normalize(merged)


def _curve(profile, today, ticker, upper, families, as_of, market, events, limits, amount):
    """[(row, checks)] for w = 0 %, 1 %, ... round(upper x 100) %, each mix = apply_change(today, set ticker w), so
    0 % is today without the ticker (today exactly when it is not held); a size apply_change refuses is skipped. Stops at the first `{"error"}` and returns it."""
    points = []
    for k in range(int(round(upper * 100)) + 1):
        w = k / 100
        try:
            mix = apply_change(today, {"op": "set", "ticker": ticker, "weight": w, "from_ticker": None})
        except ValueError:
            continue
        ev = _judge(profile, mix, families, as_of, market, events, limits, amount)
        if ev.get("error"):
            return ev
        row = {"weight": w, "verdict": ev["verdict"], "fails": governance.count_fails(ev["checks"]),
               "max_drawdown": ev["metrics"]["max_drawdown"], "scenario_shock": ev["stress"]["value"]}
        points.append((row, ev["checks"]))
    return points


def tipping_point(profile, weights, ticker, event_ids, as_of, *, market=None, events=None, families=None,
                  limits=None, amount=None, max_weight=None) -> dict:
    """The size curve of one security (spec 10; the slider never recomputes): `curve` = [{weight, verdict, fails,
    max_drawdown, scenario_shock}] from 0 % to `max_weight` (else today's weight of the ticker) in 1 % steps, each
    judged by governance.evaluate on today's weights with the ticker set to that size. `max_weight` = the last size of
    the curve with no fail (`fails` counts one cause once, ledger 6): every size above it, to the end of the curve,
    crosses a limit in this history. None when every size fails, and then `still_failing` = the rule that decides today's verdict (binding_rule at 0 %).
    Robert: 8 % (-15.00004 % passes after the 0.1 pp rounding), 9 % breaks. A date with no prices: `{"error"}`."""
    market, events = _bundle(as_of, market, events)
    today, symbol = _today(weights), str(ticker).strip().upper()
    upper = max_weight if max_weight is not None else today.get(symbol, 0.0)
    points = _curve(profile, today, symbol, upper, _families(families, event_ids, events), as_of, market, events,
                    limits, amount)
    if isinstance(points, dict):
        return points
    passing = [row["weight"] for row, _ in points if row["fails"] == 0]
    top = max(passing) if passing else None
    still = binding_rule(points[0][1]) if top is None and points else None
    return {"ticker": symbol, "max_weight": top, "curve": [row for row, _ in points], "still_failing": still,
            "source": SOURCE, "as_of": as_of}


# ---- the code's variations of the investor's own move (never ranked, never another security) ----

def _target(today: dict, change) -> tuple[str, float] | None:
    """(ticker, size asked) for a `set` or `add` change, else None (any other change has no variation here)."""
    if not isinstance(change, dict) or str(change.get("op") or "").strip().lower() not in ("set", "add"):
        return None
    symbol = str(change.get("ticker") or "").strip().upper()
    try:
        size = float(change.get("weight"))
    except (TypeError, ValueError):
        return None
    x = size if str(change["op"]).strip().lower() == "set" else today.get(symbol, 0.0) + size
    return (symbol, x) if symbol and 0.0 <= x <= 1.0 + DUST else None


def _variation(kind, change, weights, ev) -> dict:
    return {"kind": kind, "change": change, "weights": weights, "verdict": ev["verdict"],
            "binding_rule": binding_rule(ev["checks"]), "max_drawdown": ev["metrics"]["max_drawdown"],
            "scenario_shock": ev["stress"]["value"]}


def comparison_menu(profile, weights, change, families, as_of, *, market=None, events=None, limits=None,
                    amount=None) -> list[dict] | dict:
    """The code-built what-ifs of a `set`/`add` move of ticker T to size x, in this fixed order and never ranked:
    1. `threshold`: T at the size where the curve last has no fail (tipping_point with max_weight=x), only when it
       is below x; 2. `funded_from`: T at x funded from L only, L = today's largest other line (skipped when L is
       too small); `op: "fund"` is a menu-only change, so the row carries its `weights`. Each row judged by
       governance.evaluate. No label (the pipeline writes it, ledger 30); no substitute security (resolution 7).
    A date with no prices: `{"error"}` (ledger 0)."""
    today = _today(weights)
    target = _target(today, change)
    if target is None:
        return []
    symbol, x = target
    market, events = _bundle(as_of, market, events)
    fams, rows = _families(families, (), events), []
    tp = tipping_point(profile, today, symbol, (), as_of, market=market, events=events, families=fams, limits=limits,
                       amount=amount, max_weight=x)
    if tp.get("error"):
        return tp
    top = tp["max_weight"]
    if top is not None and top < x - DUST:
        step = {"op": "set", "ticker": symbol, "weight": top, "from_ticker": None}
        mix = apply_change(today, step)
        rows.append(_variation("threshold", step, mix, _judge(profile, mix, fams, as_of, market, events, limits, amount)))
    others = {t: w for t, w in today.items() if t != symbol}
    if others:
        lead = min(others.items(), key=lambda kv: (-kv[1], kv[0]))[0]       # ties broken by ticker
        need = x - today.get(symbol, 0.0)
        if need > DUST and others[lead] >= need - DUST:
            mix = normalize({**today, symbol: x, lead: max(others[lead] - need, 0.0)})
            step = {"op": "fund", "ticker": symbol, "weight": x, "from_ticker": lead}
            rows.append(_variation("funded_from", step, mix,
                                   _judge(profile, mix, fams, as_of, market, events, limits, amount)))
    return rows


# ---- where the verdict would flip (pure: no data reread) ----

def sensitivity(profile, weights, analysis, *, limits=None) -> dict:
    """The nearest floor, in 0.1 pp steps from the current one (looser down to -60 %, stricter up to -0.1 %), at which
    governance.check_profile gives another verdict (tie: the looser one), and the sentence that says so. The scan
    starts from `limits` (the user's edits or a whole limits dict), else the limits the analysis was judged with."""
    if profile is None or not analysis:
        return {"floor_flip": None, "sentence": "Limits missing."}
    start, amount = (limits if limits is not None else analysis.get("limits")), analysis.get("amount")
    base = governance.load_limits(profile, start, amount=amount)
    if base is None:
        return {"floor_flip": None, "sentence": "Limits missing."}

    def judged(lim):
        checks = governance.check_profile(profile, weights, {**analysis, "limits": lim})
        return checks, governance.verdict(checks)

    now = judged(base)[1]
    origin = int(governance.round_pp(base["floor"]) * 10)          # tenths of a percent point: -15 % -> -150

    def first(steps, looser):
        for n in steps:
            checks, found = judged(governance.load_limits(profile, {**(start or {}), "floor": n / 1000}, amount=amount))
            if found != now:
                return abs(n - origin), not looser, n / 1000, checks, found
        return None

    hits = [h for h in (first(range(origin - 1, LOOSEST_TENTHS - 1, -1), True),
                        first(range(origin + 1, STRICTEST_TENTHS + 1), False)) if h]
    if not hits:
        return {"floor_flip": None, "sentence": f"No floor between {governance.MINUS}0.1{governance.PCT} and "
                                                f"{governance.MINUS}60{governance.PCT} changes the verdict: another "
                                                "limit decides it."}
    _, stricter, floor, checks, found = min(hits)                   # nearest; a tie goes to the looser floor
    floor_row = next((c for c in checks if c["rule"] == "max_drawdown"), None)
    left = next((c for c in checks if c["status"] == "fail" and c["rule"] != "max_drawdown"), None)
    because = ""
    if left and not (floor_row and floor_row["status"] == "fail"):  # what keeps the new verdict from a plain inside
        because = (f" because {left.get('holding') or 'the mix'} would still be beyond the "
                   f"{STILL_BEYOND.get(left['rule'], left['rule'].replace('_', ' '))} limit")
    return {"floor_flip": floor,
            "sentence": f"{config.VERDICT_WORDS[now]} until your floor is {governance.fmt_pct(floor)} "
                        f"{'or stricter' if stricter else 'or lower'}; at that floor the verdict would be "
                        f"{config.VERDICT_WORDS[found]}{because}."}


# ---- the price of values: the investor's own portfolio, without the names the values screen excludes ----

def _excluded(weights: dict, analysis: dict) -> list[str]:
    """Held names the values screen excludes, read the way governance's esg_direct row reads them: an Energy-sector
    line, or a ticker of data/esg_flags.csv known at as_of (`analysis["esg_flags"]`)."""
    uni = {r["ticker"]: r for r in analysis.get("universe") or ()}
    flags = set(analysis.get("esg_flags") or ())
    return sorted(t for t, w in weights.items() if w > 0 and (uni.get(t, {}).get("sector") == "Energy" or t in flags))


def _side(weights: dict, label: str, ev: dict) -> dict:
    return {"weights": weights, "label": label, "max_drawdown": ev["metrics"]["max_drawdown"],
            "war_oil_worst": ev["stress"]["value"], "cagr": ev["metrics"]["cagr"]}


def price_of_values(profile, weights, as_of, *, market=None, events=None) -> dict | None:
    """What the values screen costs on the investor's own portfolio (spec 24 resolution 7): `non_esg` = the portfolio
    as it is, `esg` = the same portfolio with the excluded names removed and the rest scaled up (no new security,
    no model mix). Each side: worst drop, the worst War & oil shock and growth (cagr), from governance.evaluate
    with no profile. None without the values screen; `{"error"}` when every line is excluded."""
    if not profile or not profile.get("esg"):
        return None
    market, events = _bundle(as_of, market, events)
    own = _today(weights)
    as_is = governance.evaluate(None, own, ["war_oil"], as_of, market=market, events=events, detail=False)
    if as_is.get("error"):
        return as_is
    removed = _excluded(own, as_is["analysis"])
    kept = {t: w for t, w in own.items() if t not in removed}
    if not kept:
        return {"error": "Every line of this portfolio is excluded by your values screen, so nothing is left to "
                         "scale up."}
    screened = normalize(kept) if removed else dict(own)
    ev = governance.evaluate(None, screened, ["war_oil"], as_of, market=market, events=events,
                             detail=False) if removed else as_is
    label = (f"Your portfolio without {', '.join(removed)} (excluded by your values screen), the rest scaled up"
             if removed else "Your portfolio: no line is excluded by your values screen")
    return {"esg": _side(screened, label, ev), "non_esg": _side(own, "Your portfolio as it is", as_is),
            "removed": removed, "source": SOURCE, "as_of": as_of}
