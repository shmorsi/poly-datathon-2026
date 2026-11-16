"""FAKE engine for offline tests; not market data.

Every value below is invented so that pipeline.py can be built and tested before the real tools land (plan D
Task 2). The shapes follow the interface ledger; the numbers follow the spec's Robert example (40 % in NVIDIA)
but are FAKE. `fake_engine(**overrides)` returns a pipeline.Engine whose callables record (name, args, kwargs)
in `engine.calls`; pass a callable as an override to replace one (for example one that raises).
"""
import json

import plotly.graph_objects as go

import pipeline
import verify

ROBERT_PLAN = {
    "portfolio": {"XIU.TO": 0.45, "XBB.TO": 0.35, "GLD": 0.10, "ZST.TO": 0.10},
    "amount": 600000,
    "profile": {"goal": "preservation", "horizon_years": 4, "risk": "moderate", "esg": False, "crypto": False,
                "capacity": 90000, "reaction_2022": "held"},
    "limits": None,
    "pilot": "robert",
}
ROBERT_Q = "Everyone is talking about NVIDIA. What if I put 40 % in it and Washington slaps new levies on Canadian goods?"  # personas.json (Sun Nov 15 ruling: the keyword rules miss "levies")

FAKE_SOURCE = "FAKE: tests/fake_engine.py"
AS_OF = "2026-11-12"
DATES = ["2021-11-12", "2022-10-14", "2026-11-12"]
AFTER_WEIGHTS = {"XIU.TO": 0.27, "XBB.TO": 0.21, "GLD": 0.06, "ZST.TO": 0.06, "NVDA": 0.40}
CHANGE = {"op": "set", "ticker": "NVDA", "weight": 0.40}
EVENT_IDS = ["liberation_day_2025", "tariffs_canada_2025"]


def _held(weights):
    return weights.get("NVDA", 0) > 0


def _limits(profile=None, overrides=None, *, amount=None):
    """The canned limits with the user's edits over them (listed in `edited`); an edited floor also sets the shock
    limit to half of it, as governance does (plan D Task 7)."""
    out = {"floor": -0.15, "floor_source": "capacity", "band_floor": -0.25, "capacity_floor": -0.15,
           "single_stock": 0.10, "sector": 0.30, "crypto": 0.0, "scenario_stress": -0.075,
           "recovery_days": 487, "risk_share": 0.5, "edited": []}
    edits = {k: v for k, v in (overrides or {}).items() if k in out and k != "edited"}
    out.update(edits, edited=sorted(edits))
    if "floor" in edits and "scenario_stress" not in edits:
        out["scenario_stress"] = round(edits["floor"] * 0.5, 10)
    return out


def _check(rule, tier, status, value, limit, holding=None, reason=""):
    return {"rule": rule, "tier": tier, "status": status, "value": value, "limit": limit, "holding": holding,
            "reason": reason}


def _checks(held):
    if not held:
        return [_check("max_drawdown", "hard", "pass", -0.106, -0.15, reason="FAKE: inside the floor."),
                _check("scenario_stress", "soft", "pass", -0.06, -0.075, reason="FAKE: inside the shock limit."),
                _check("single_stock", "soft", "pass", 0.0, 0.10, reason="FAKE: no company above the limit.")]
    return [_check("max_drawdown", "hard", "fail", -0.345, -0.15, reason="FAKE: the fall is past the floor."),
            _check("scenario_stress", "soft", "fail", -0.09, -0.075, reason="FAKE: the tariff shock is past the limit."),
            _check("single_stock", "soft", "fail", 0.40, 0.10, "NVDA", "FAKE: one company is above the limit.")]


def _lookthrough(held):
    stocks = {"RY.TO": {"direct": 0.0, "via": [{"etf": "XIU.TO", "weight": 0.026}], "total": 0.026}}
    if held:
        stocks["NVDA"] = {"direct": 0.40, "via": [], "total": 0.40}
    return {"stocks": stocks, "sectors": {"Financials": 0.14}, "countries": {"CAN": 0.9, "GLOBAL": 0.1},
            "esg_indirect": {}, "coverage": {"XIU.TO": 0.77}, "snapshot": {"XIU.TO": AS_OF}, "mode": "lookthrough",
            "source": FAKE_SOURCE, "as_of": AS_OF}


def _risk(held):
    shares = ({"NVDA": 0.86, "XIU.TO": 0.08, "XBB.TO": 0.03, "GLD": 0.02, "ZST.TO": 0.01} if held
              else {"XIU.TO": 0.50, "XBB.TO": 0.20, "GLD": 0.20, "ZST.TO": 0.10})
    return {"shares": shares, "bets": 1.3 if held else 3.1, "degenerate": False, "source": FAKE_SOURCE,
            "as_of": AS_OF}


def _no_precedent(ev):
    """The shock check with no close precedent at this date: a warn without a value, and no episode to count."""
    ev["checks"] = [{**c, "status": "warn", "value": None, "reason": "No close precedent at this date."}
                    if c["rule"] == "scenario_stress" else c for c in ev["checks"]]
    ev["turbulence"] = {"tariffs": {"n": 0, "worst": None, "mean": None, "evidence": "Can't say", "episodes": []}}
    ev["stress"] = {**ev["stress"], "value": None, "n_episodes": 0, "worst_event_id": None}
    ev["kpis"] = {**ev["kpis"], "scenario_stress": {"value": None, "limit": -0.075}}
    ev["verdict"] = _verdict(ev["checks"])
    return ev


def _evaluator(no_precedent=False):
    def evaluate(profile, weights, families, *args, **kwargs):
        ev = _evaluate(profile, weights, families, *args, **kwargs)
        # no shock family to replay (the navigator's abstention, ledger 30): the shock check has no close precedent
        return _no_precedent(ev) if (no_precedent or list(families) == []) and profile else ev
    return evaluate


def _evaluate(profile, weights, families, as_of, *, market=None, events=None, today=None, limits=None,
              amount=None, detail=True):
    held = _held(weights)
    drop, stress = (-0.345, -0.09) if held else (-0.106, -0.06)
    metrics = {"cagr": 0.252 if held else 0.087, "volatility": 0.21 if held else 0.07, "max_drawdown": drop,
               "peak_date": "2021-11-29", "trough_date": "2022-10-14", "recovery_days": 640 if held else 416,
               "days_since_trough": 1491, "sharpe": 0.9, "source": FAKE_SOURCE, "as_of": AS_OF}
    lim = _limits(profile, limits, amount=amount) if profile else None
    loss = 207000 if held else 63600
    checks = _checks(held) if profile else []
    return {"weights": dict(weights),
            "series": {"dates": list(DATES), "values": [100, 65.5, 306.9] if held else [100, 89.4, 150.6],
                       "source": FAKE_SOURCE, "as_of": AS_OF},
            "metrics": metrics,
            "worst_rolling": {"value": -0.30 if held else -0.09, "peak_date": "2021-11-29",
                              "trough_date": "2022-10-14"},
            "stress": {"value": stress, "n_episodes": 4, "worst_event_id": "liberation_day_2025", "episodes": [],
                       "excluded": [], "label": "Measured", "source": FAKE_SOURCE, "as_of": AS_OF},
            "turbulence": {"tariffs": {"n": 4, "worst": stress, "mean": -0.04, "evidence": "Measured",
                                       "episodes": []}},
            "lookthrough": _lookthrough(held),
            "exposure": {"countries": {"CAN": 0.9, "GLOBAL": 0.1}, "borderless": {"CRYPTO": 0.0, "GLOBAL": 0.1},
                         "source": FAKE_SOURCE, "as_of": AS_OF},
            "risk": _risk(held),
            "diversification": {"countries": {"CAN": 0.9, "USA": 0.1},
                                "currencies": {"CAD": 0.9, "USD": 0.1, "OTHER": 0.0},
                                "sectors": {"Financials": 0.14}, "can_risk_share": True, "source": FAKE_SOURCE,
                                "as_of": AS_OF},
            "analysis": {"metrics": metrics, "limits": lim, "loss_dollars": loss, "amount": amount or 600000},
            "checks": checks,
            "verdict": (None if not profile else ("Incompatible" if held else "Compatible")),
            "kpis": {"max_drawdown": {"value": drop, "limit": -0.15},
                     "scenario_stress": {"value": stress, "limit": -0.075},
                     "recovery_days": {"value": metrics["recovery_days"], "limit": 487},
                     "exposure_canada": {"value": 0.9, "limit": None}},
            "limits": lim}


TOOL_CALLS = [{"tool": "search_events", "input": {"query": "<question>", "family": "tariffs", "regions": ["USA", "CAN"]},
               "output_summary": "2 known events; best liberation_day_2025 (0.9)", "ms": 0.4},
              {"tool": "propose_change", "input": {"op": "set", "ticker": "NVDA", "weight": 0.4},
               "output_summary": {"ticker": "NVDA", "weight": 0.4}, "ms": 0.2}]
REJECTED = {"war_oil": "War & oil: no words in your question point to it; best score 0.20."}
NAV_MODEL = "global.anthropic.claude-sonnet-5-5"     # agents.scenario writes `model_id` on every model turn (B Task 9b)
MODEL_CALLS = [{"turn": 1, "model_id": NAV_MODEL, "request_id": "req-nav-1", "usage": {"inputTokens": 900, "outputTokens": 120},
                "latency_ms": 800}]


def _scenario(method, *, clarify=None, no_precedent=False):
    """The navigator (method "bedrock") or the keyword rules ("fallback"), switched by the fake_engine options."""
    def navigate(question, portfolio, catalog, as_of, *, profile=None, limits=None, universe=None, exposure=None,
                 amount=None, engine=None, agent=None):
        out = {"type": "change", "families": ["tariffs"], "event_ids": list(EVENT_IDS),
               "reasons": {i: "FAKE: matched on family and region." for i in EVENT_IDS}, "rejected": dict(REJECTED),
               "change": dict(CHANGE), "portfolio": dict(AFTER_WEIGHTS), "intent": "FAKE: put 40 % in NVIDIA",
               "clarify": None, "clarify_reason": None, "widened": None, "weather": None,
               "tool_calls": [dict(c) for c in TOOL_CALLS], "match_features": {}, "method": method, "usage": None,
               "request_id": None, "ms": 0, "fallback_reason": None, "error": None,
               "model_calls": [dict(c) for c in MODEL_CALLS] if method == "bedrock" else []}
        if clarify:
            out.update(type="change", families=[], event_ids=[], reasons={}, change=None, portfolio=None,
                       clarify=clarify, clarify_reason="amount_unknown")
        elif no_precedent:
            out.update(type="shock", families=["tariffs"], event_ids=[], reasons={}, change=None, portfolio=None,
                       weather={"headline": question, "families": ["tariffs"], "regions": ["CAN"], "no_precedent": True})
        return out
    return navigate


BLOCKED_MESSAGE = ("EPICENTRE runs simulations, not trades, so it won't say whether to buy or sell. "
                   "Ask what a move would have done instead.")


GOOD_GROUNDING = {"score": 0.92, "threshold": 0.7, "detected": False}
LOW_GROUNDING = {"score": 0.4, "threshold": 0.7, "detected": True}


def _guardrail(*, blocked=False, guard_error=False, low_grounding=False):
    def apply_guardrail(text, source, facts=None, query=None, *, client=None):
        out = {"action": "NONE", "blocked": False, "topic_hit": False, "prompt_attack": False, "pii_hit": False,
               "grounding": None, "relevance": None, "automated_reasoning": None, "message": None, "error": None,
               "latency_ms": 1, "usage": {"textUnits": 1}}
        if source == "OUTPUT":                    # the explanation is scored, never blocked (spec 7)
            return {**out, "grounding": dict(LOW_GROUNDING if low_grounding else GOOD_GROUNDING),
                    "relevance": {"score": 0.88, "threshold": 0.7, "detected": False}}
        if blocked:
            out.update(blocked=True, action="GUARDRAIL_INTERVENED", topic_hit=True, message=BLOCKED_MESSAGE)
        elif guard_error:
            out = {"error": "The safety check did not answer."}
        return out
    return apply_guardrail


def _normalize(weights):
    kept = {t: float(w) for t, w in weights.items() if w and float(w) > 0}
    total = sum(kept.values())
    return {t: w / total for t, w in kept.items()}


def _apply_change(weights, change):
    held = dict(weights)
    held[change["ticker"]] = change["weight"]
    return _normalize(held)


def _portfolio_series(weights, start=None, end=None, as_of=AS_OF, *, market=None, union=False):
    return {"dates": list(DATES), "values": [100, 65.5, 306.9] if _held(weights) else [100, 89.4, 150.6],
            "source": FAKE_SOURCE, "as_of": as_of}


def _tipping_point(profile, weights, ticker, event_ids, as_of, *, market=None, events=None, families=None,
                   limits=None, amount=None, max_weight=None):
    curve = [{"weight": k / 100, "verdict": "Compatible" if k <= 8 else "Incompatible", "fails": 0 if k <= 8 else 1,
              "max_drawdown": -0.106 - 0.006 * k, "scenario_shock": -0.06 - 0.0008 * k} for k in range(0, 41)]
    return {"ticker": ticker, "max_weight": 0.08, "curve": curve, "still_failing": None}


def _attribution(series, events, as_of, *, metrics=None):
    return {"shares": {"rates": 0.249, "tariffs": 0.0, "war_oil": 0.0, "chips": 0.0},
            "days_share": {"rates": 0.323, "tariffs": 0.0, "war_oil": 0.0, "chips": 0.0},
            "peak_date": "2021-11-29", "trough_date": "2022-10-14", "source": FAKE_SOURCE, "as_of": as_of}


def _check_order(checks, profile):
    fails = [c["rule"] for c in checks if c.get("status") == "fail"]
    return fails + [c["rule"] for c in checks if c.get("status") != "fail"]


def _binding_rule(checks):
    return next((c["rule"] for c in checks if c.get("status") == "fail"), None)


def _figure(name):
    def build(result, *args, **kwargs):
        return go.Figure(layout={"title": {"text": f"FAKE figure: {name}"}})
    return build


def _figures_json(fig):
    return json.loads(fig.to_json())


# ---- the fake debrief: built only from the facts it receives, so it passes the receipt (verify.py) ----
_NAMES = {"NVDA": "NVIDIA", "TSLA": "Tesla", "MSFT": "Microsoft", "SHOP.TO": "Shopify", "BTC-USD": "Bitcoin"}


def _words(row):
    """A facts row's value written the way the debrief writes it: absolute value, whole percents when exact."""
    from decimal import Decimal
    v, unit = abs(row["value"]), row["unit"]
    if unit in ("pct", "pp"):
        q = Decimal(str(v)) * 100
        return verify.fmt_number(v, unit, 0 if q == q.to_integral_value() else None)
    return verify.fmt_number(v, unit)


DOWN = {"error": "Amazon Bedrock did not answer (ExpiredTokenException)."}
REWRITTEN = "This draft was rewritten once, from the checker's named defects."


def _explainer(*, bad_first=False, always_bad=False, bedrock_down=False):
    """The fake debrief, switched by the fake_engine options: `bad_first` makes the first draft cite the T# of "Worst
    drop today" for the after value, `always_bad` every draft, `bedrock_down` answers with Bedrock's error."""
    drafts = []

    def explain(facts, retry_numbers=None, argument=None, *, context=None, client=None, memory=None):
        drafts.append(retry_numbers)
        if bedrock_down:
            return dict(DOWN)
        return _explain(facts, retry_numbers, argument, context=context, bad=always_bad or (bad_first and len(drafts) == 1))
    return explain


def _explain(facts, retry_numbers=None, argument=None, *, context=None, client=None, bad=False):
    ctx, rows = context or {}, {f["label"]: (tid, f) for tid, f in facts.items()}

    def find(label=None, prefix="", suffix=""):
        for lab, hit in rows.items():
            if (lab == label) if label else (lab.startswith(prefix) and lab.endswith(suffix)):
                return hit
        return None

    def w(hit):                                   # "34.5 % [T7]"
        return f"{_words(hit[1])} [{hit[0]}]"

    move, after = find(prefix="The move: "), find("Worst drop after the move")
    floor, cap = find(prefix="Your floor, set by"), (find("The amount set as your limit (assumed for this fictional profile)") or find("The amount you typed as your limit"))
    today, loss = find("Worst drop today"), find("Dollar loss at the worst drop after the move")
    if bad and today and after:                   # the after value cited with today's row: the receipt names it
        after = (today[0], after[1])
    g_today, g_after = find("Growth per year today"), find("Growth per year after the move")
    shock, n_shocks = find(prefix="Worst clean ", suffix=" shock after the move"), find(prefix="Clean ", suffix=" shocks known")
    limit, share = find("Shock limit (half your floor)"), find(suffix=" share of the risk after the move")
    bets, biggest = find("Independent bets after the move"), find(prefix="In this replay, your floor first broke at")
    days, rates, amount = find("Days to recover today"), find("Share of the worst drop inside rate-shock windows"), find("Fictional amount")
    name = _NAMES.get(move[1]["entity"], move[1]["entity"]) if move else "the company"
    fam = shock[1]["label"][len("Worst clean "):-len(" shock after the move")] if shock else "tariff war"
    words, failed = ctx.get("verdict_words") or "Limits missing", list(ctx.get("failed_rules") or [])
    S = []

    def add(section, kind, *parts):
        S.append((section, kind, " ".join(parts)))

    if today:
        add("data", "fact", f"Today the worst drop was {w(today)}" + (f" and the mix grew {w(g_today)} per year." if g_today else "."))
    if after:
        add("data", "fact", f"After the move the worst drop would have been {w(after)}.")
    if after and loss:                            # the dollars are on the fictional amount: a scenario sentence (spec 24)
        add("data", "scenario", f"On the fictional amount, the move would have lost {w(loss)}.")
    if g_after:
        add("data", "fact", f"After the move the mix grew {w(g_after)} per year.")
    if shock and n_shocks:
        add("data", "fact", f"The shock check found {w(n_shocks)} clean {fam} shocks; the worst one cost {w(shock)} after the move.")
    if days:
        add("data", "fact", f"Today the mix needed {w(days)} to recover its worst drop.")
    if rates:
        add("data", "fact", f"About {w(rates)} of the worst drop happened inside rate-shock windows; that is a correlation, not a cause.")
    for rule in failed:
        if rule == "Your floor" and after and floor:
            add("why", "assumption", f"The check that decided the verdict is your floor: the worst drop after the move was {w(after)}, past your floor of {w(floor)}"
                + (f", which comes from the {w(cap)} set as your limit." if cap else "."))
        elif rule == "Shock check" and shock and limit:
            add("why", "assumption", f"The shock check also failed: the worst {fam} shock cost {w(shock)} after the move, past the shock limit of {w(limit)}.")
        elif rule == "One company" and share:
            add("why", "assumption", f"One company is above its limit: after the move {name} would carry {w(share)} of the risk"
                + (f" and the mix would count {w(bets)} independent bets." if bets else "."))
        else:
            add("why", "assumption", f"The {rule.lower()} limit is also crossed.")
    if words == "Limits missing":
        add("why", "assumption", "There is no verdict because the questions about your limits are not answered.")
    elif not failed:
        add("why", "assumption", "No limit is crossed in this replay.")
    for phrase in ctx.get("caveats") or []:
        add("why", "assumption", f"Caveat: {phrase}.")
    add("limits", "limit", "This replay shows what already happened in the data; it is not a forecast.")
    if retry_numbers:                             # a re-asked draft reads differently, so a test can tell the two apart
        add("limits", "limit", REWRITTEN)
    if n_shocks:
        add("limits", "limit", f"The shock check rests on {w(n_shocks)} clean {fam} shocks, so read it as measured on few episodes.")
    if biggest and amount:
        add("would_change", "scenario", f"In this replay, your floor first broke at {w(biggest)} {name}, and the replay uses a fictional amount of {w(amount)}.")
    else:
        add("would_change", "scenario", "A different mix, amount or limit would change this answer.")
    if move and after and floor and words == "Outside your limits":
        vs = f"{words}: with {w(move)} in {name}, the move would have fallen {w(after)}, past your floor of {w(floor)}."
    elif after and floor:
        vs = f"{words}: the worst drop after the move was {w(after)}, against your floor of {w(floor)}."
    else:
        vs = f"{words}."
    import re
    sentences = [{"text": t, "kind": k, "refs": re.findall(r"T\d+", t)} for _, k, t in S]
    sections = {n: [i for i, (s, _, _) in enumerate(S) if s == n] for n in verify.SECTION_ORDER}
    body = [vs] + [f"{verify.SECTION_TITLES[n]}\n" + " ".join(sentences[i]["text"] for i in ix) for n, ix in sections.items()]
    return {"debrief": {"verdict_sentence": vs, "sections": sections, "sentences": sentences},
            "text": "\n\n".join(body + [pipeline.DISCLAIMER]), "model": "FAKE", "usage": {"inputTokens": 1200, "outputTokens": 300},
            "ms": 1, "stop_reason": "end_turn", "request_id": "req-fake-explain-1", "error": None}


# ---- minimal ledger-shaped answers for the tools the skeleton does not judge with ----
def _check_profile(profile, weights, analysis):
    """The canned checks; the floor row is judged on the rounded values against the limits it is given (governance's
    round_pp, so a recheck with another floor moves it), the other rows stay canned."""
    if not profile:
        return []
    floor = ((analysis or {}).get("limits") or {}).get("floor")
    out = []
    for c in _checks(_held(weights)):
        if c["rule"] == "max_drawdown" and floor is not None:
            fail = pipeline._pp(c["value"]) < pipeline._pp(floor)
            c = {**c, "limit": floor, "status": "fail" if fail else "pass"}
        out.append(c)
    return out


def _verdict(checks):
    """A hard fail is Incompatible; any other fail or a warn is Tension (the governance order, simplified)."""
    if not checks:
        return None
    if any(c["status"] == "fail" and c.get("tier") == "hard" for c in checks):
        return "Incompatible"
    return "Tension" if any(c["status"] in ("fail", "warn") for c in checks) else "Compatible"


def _aligned_allocation(profile):
    return {"weights": {"XIU.TO": 0.40, "XBB.TO": 0.40, "GLD": 0.10, "ZST.TO": 0.10},
            "label": "Fictional illustration, not a recommendation", "rule": "FAKE", "source": FAKE_SOURCE,
            "as_of": AS_OF}


def _comparison_menu(profile, weights, change, families, as_of, *, market=None, events=None, limits=None, amount=None):
    return [{"label": "FAKE: NVDA at 8 %, the last size before your floor broke in this history",
             "change": {"op": "set", "ticker": "NVDA", "weight": 0.08, "from_ticker": None},
             "weights": {"XIU.TO": 0.414, "XBB.TO": 0.322, "GLD": 0.092, "ZST.TO": 0.092, "NVDA": 0.08},
             "verdict": "Compatible", "binding_rule": None, "max_drawdown": -0.14, "scenario_shock": -0.066},
            {"label": "FAKE: NVDA at 40 %, funded from XIU.TO only",
             "change": {"op": "fund", "ticker": "NVDA", "weight": 0.40, "from_ticker": "XIU.TO"},
             "weights": {"XIU.TO": 0.05, "XBB.TO": 0.35, "GLD": 0.10, "ZST.TO": 0.10, "NVDA": 0.40},
             "verdict": "Incompatible", "binding_rule": "max_drawdown", "max_drawdown": -0.351, "scenario_shock": -0.093}]


def _sensitivity(profile, weights, analysis, *, limits=None):
    return {"floor_flip": -0.40, "sentence": "FAKE: Outside your limits until your floor is 40.0 % or lower."}


def _event_row(event_id, date, title, lat, lon):
    return {"event_id": event_id, "date": date, "title": title, "description": "FAKE: not a real event row.",
            "family": "tariffs", "sign": "negative", "regions": ["USA"], "lat": lat, "lon": lon,
            "source_url": "https://example.invalid/fake", "known": True, "in_progress": False, "episode": event_id,
            "confounded": False, "t0": date, "window_end": "2025-05-02"}


def _load_events(as_of, *, path=None, market=None):
    return [_event_row("liberation_day_2025", "2025-04-02", "FAKE: Liberation Day tariffs", 38.90, -77.04),
            _event_row("tariffs_canada_2025", "2025-03-04", "FAKE: tariffs on Canada", 45.42, -75.70)]


def _event_impact(weights, event_id, window=(-5, 20), as_of=AS_OF, *, market=None, events=None):
    return {"event_id": event_id, "episode": event_id, "sign": "negative", "confounded": False, "t0": "2025-04-02",
            "window_end": "2025-05-02", "trough": -0.09, "trough_date": "2025-04-08", "ret_20": -0.05,
            "fx_effect": 0.0, "percentile": 0.1, "by_ticker": {}, "overlaps": [], "chart": {}, "source": FAKE_SOURCE,
            "as_of": as_of}


def fake_engine(*, blocked=False, guard_error=False, clarify=None, no_precedent=False, bad_first=False,
                always_bad=False, low_grounding=False, bedrock_down=False, **overrides):
    """A pipeline.Engine of fakes. `engine.calls` lists (name, args, kwargs); an override replaces one callable.
    The options switch the canned answers (plan D Task 6): `blocked` (the input guardrail intervenes), `guard_error`
    (the input guardrail does not answer), `clarify` (the navigator asks this question and proposes no change) and
    `no_precedent` (a shock with no close precedent: no picked event, the shock check warns without a value); and
    (plan D Task 7) `bad_first` / `always_bad` (the first / every draft cites today's row for the after value),
    `low_grounding` (the output guardrail scores 0.40 under 0.70) and `bedrock_down` (explain answers an error)."""
    calls = []
    impl = {
        "apply_guardrail": _guardrail(blocked=blocked, guard_error=guard_error, low_grounding=low_grounding),
        "run_scenario": _scenario("bedrock", clarify=clarify, no_precedent=no_precedent),
        "keyword_fallback": _scenario("fallback", clarify=clarify, no_precedent=no_precedent),
        "explain": _explainer(bad_first=bad_first, always_bad=always_bad, bedrock_down=bedrock_down),
        "load_limits": _limits, "evaluate": _evaluator(no_precedent), "check_profile": _check_profile, "verdict": _verdict, "check_order": _check_order,
        "aligned_allocation": _aligned_allocation, "tipping_point": _tipping_point,
        "comparison_menu": _comparison_menu, "sensitivity": _sensitivity, "price_of_values": lambda *a, **k: None,
        "binding_rule": _binding_rule, "load_universe": lambda **k: [{"ticker": "NVDA", "sector": "Technology"}],
        "load_market": lambda as_of, **k: {"as_of": as_of, "source": FAKE_SOURCE}, "apply_change": _apply_change,
        "normalize": _normalize, "portfolio_series": _portfolio_series,
        "rate_regime": lambda as_of, **k: {"hiking": [{"start": "2022-03-03", "end": "2023-07-13"}], "series": [],
                                           "source": FAKE_SOURCE, "as_of": as_of},
        "trailing_yield": lambda weights, as_of, **k: {"value": 0.021 if _held(weights) else 0.016, "by_ticker": {},
                                                       "source": FAKE_SOURCE, "as_of": as_of},
        "load_events": _load_events, "event_impact": _event_impact, "drawdown_attribution": _attribution,
        "transmission_report": lambda weights, event, **k: {"rows": [], "gaps": [], "mode": "lookthrough",
                                                            "source": FAKE_SOURCE, "as_of": k.get("as_of")},
        "figures_json": _figures_json,
    }
    unknown = set(overrides) - set(impl)
    if unknown:
        raise TypeError(f"fake_engine has no callable named {sorted(unknown)}")
    impl.update(overrides)

    def recording(name, fn):
        def call(*args, **kwargs):
            calls.append((name, args, kwargs))
            return fn(*args, **kwargs)
        return call

    figures = {key: _figure(key) for key in ("flight_paths", "storm_map", "turbulence", "risk_share",
                                             "diversification", "size_curve", "fall")}
    engine = pipeline.Engine(**{name: recording(name, fn) for name, fn in impl.items()}, figures=figures)
    engine.calls = calls
    return engine
