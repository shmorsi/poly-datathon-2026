"""The run: OBSERVE -> UNDERSTAND -> COMPARE -> EXPLAIN -> VERIFY (spec 7 and 12; plan D Task 2).

pipeline.py never computes a market number itself. It calls the ledger functions of workstreams A and B
through one seam, the `Engine` dataclass: `real_engine()` imports the real modules, tests pass
tests/fake_engine.py. It keeps one trace row per step and per fact (one id space, T1, T2, ...), and returns a
plain dict, the Result of spec 12. Expected failures become `status "error"` with one plain sentence; a stack
trace or an unexpected exception's text never leaves this module.

Saved runs (plan D Task 3): a live run that really reached Bedrock, asked one of the scripted demo questions, can be
saved by scripts/record_demo.py (the server never writes inputs) and replayed for the same inputs, badged `mode
"demo_replay"`. A replay is only ever a run that happened; with EPICENTRE_DEMO=1 `run` replays it without touching any
engine. A saved file names no company inside the investor's funds (red gate 8) and says what it was computed on.
"""
import contextlib
import functools
import hashlib
import importlib
import json
import math
import numbers
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Callable

import numpy as np

import verify

DATASET_END = "2026-11-12"
FAMILIES = ("tariffs", "war_oil", "chips", "rates")
FAMILY_LABELS = {"tariffs": "Tariff war", "war_oil": "War & oil", "chips": "Chip war", "rates": "Rate shock"}
STEPS = ("OBSERVE", "UNDERSTAND", "COMPARE", "EXPLAIN", "VERIFY")
STEP_LABELS = {
    "OBSERVE": "Read your plan and screen the question",
    "UNDERSTAND": "The navigator turns your words into a move and picks the shocks",
    "COMPARE": "Replay your mix and the move on Nov 2021 to Nov 2026",
    "EXPLAIN": "Write the explanation from the computed facts only",
    "VERIFY": "Trace every number to data",
}
# Board resolution 5 (spec 24): VERIFY's label says "grounding" only once the output guardrail has scored the explanation.
GROUNDED_LABEL = "Trace every number to data and score grounding"
DISCLAIMER = "Educational simulation. This is not financial advice."
NOT_A_PLAN = "Your plan could not be read. It must hold your mix, your amount and your answers."
BAD_WEIGHT = "Every weight must be a number."
TOOLS_DOWN = "Something went wrong while loading the tools."
BEDROCK_OFF = ("Amazon Bedrock is off for this run: the checklist and the charts are computed the same way.")
SERVICES = {"OBSERVE": "Python", "UNDERSTAND": "Python", "COMPARE": "Python", "EXPLAIN": "Amazon Bedrock",
            "VERIFY": "Python"}
GUARD_DOWN = ("The safety check did not answer, so this run uses no AI. The checklist and the charts are computed "
              "the same way.")                                # ledger 8 and 10: an input check that cannot run fails closed
BLOCKED = "The safety check stopped this question."           # only when the guardrail gives no sentence of its own
STOPPED = {"blocked": "Stopped: the safety check blocked this question, so no model saw it.",
           "clarify": "Stopped: the navigator needs one answer first.",
           "weights": "Stopped: your weights need one answer first."}
WEIGHT_TOLERANCE = 0.005            # ruling R22 (the server's own bound): further from 100 % is a question, never normalized
WEIGHTS_SHORT = "Your weights add up to {total}; what is the other {gap}?"
WEIGHTS_OVER = "Your weights add up to {total}, {gap} over 100 %; what are the right weights?"
NO_PRECEDENT = "No sourced shock known at {as_of} is close to this headline, so no shock is replayed."
STEP_DEADLINE_S = 25                # one model step (ledger 15 and 29): an explanation later than this did not answer
RUN_DEADLINE_S = 60                 # one run (ledger 15, ruling R10): no step starts after it, no model call waits past it
RUN_LATE = ("This run passed its {limit} s limit, so it stopped before the {step} step. The steps that finished are kept "
            "in the trace.")
RUN_CUT = (f"This run reached its {RUN_DEADLINE_S} s limit before its last model or safety call answered; the checklist "
           "and the charts are computed the same way.")
RUN_CUT_DRAFT = f"Amazon Bedrock did not answer before the run's {RUN_DEADLINE_S} s limit."
RUN_CUT_CHECK = f"The safety check did not run: the run reached its {RUN_DEADLINE_S} s limit."
_now = time.monotonic               # the run deadline's clock (a test moves it instead of sleeping)
COMPARE_PILOTS = ("robert", "mateo", "amira")                 # the Compare block, in this order
IN_2022 = {"sold": "sold", "held": "held", "bought": "bought more"}
HIKING = {"kind": "hiking", "label": "Bank of Canada raising rates", "source": "macro_rates.csv, series V39079"}
PATH_EVERY = 5                      # the size slider's dollar paths keep every 5th trading day and the last (ledger 9)
# Epicentre labels for an event row without its own `place` (ledger 9): the nearest one within PLACE_DEGREES.
PLACES = {"Washington": (38.90, -77.04), "Federal Reserve": (38.89, -77.05), "Ottawa": (45.42, -75.70),
          "Beijing": (39.90, 116.40), "Kyiv": (50.45, 30.52), "Gaza": (31.50, 34.47), "Jerusalem": (31.78, 35.23),
          "Tehran": (35.69, 51.39), "Hangzhou": (30.27, 120.15), "Riyadh": (24.64, 46.72), "Taipei": (25.04, 121.56),
          "Nuuk": (64.18, -51.74), "Strait of Hormuz": (26.60, 56.50), "Islamabad": (33.69, 73.06)}
PLACE_DEGREES = 0.05
EVENT_KEYS = ("event_id", "date", "title", "description", "family", "sign", "regions", "lat", "lon", "source_url",
              "known", "in_progress", "episode", "confounded", "t0", "window_end")

# Saved runs and the demo replay (config.ENV_DEMO and config.DEMO_RUNS_DIR name the same variable and folder).
REPO_ROOT = Path(__file__).resolve().parent
DEMO_ENV = "EPICENTRE_DEMO"
DEMO_DIR = REPO_ROOT / "data" / "demo_runs"
DATA_DIR_ENV = "EPICENTRE_DATA_DIR"                  # tools/data.py: the data pack the tools read
REAL_DATA_DIR = REPO_ROOT / "data" / "starter"       # the real starter pack (licensed, never committed)
FAKE_DATA_DIR = REPO_ROOT / "data" / "fake"          # the synthetic pack and the fake reference Result
PERSONAS_PATH = REPO_ROOT / "data" / "personas.json"  # the investors and the shock cards, and their scripted questions
MEMORY_PATH = REPO_ROOT / "data" / "cache" / "defect_memory.json"   # ruling R4: defect types only; data/cache/ is gitignored
MEMORY_SOURCE = "agents.memory: the defect types earlier debriefs made (types and counts only, never text)"
ANOTHER_COMPANY = "Another company"                  # what a saved run calls a company it may not name (red gate 8)
DEFAULT_PILOT = "robert"            # the investor whose saved run the page opens on
PILOT_RX = re.compile(r"[a-z][a-z0-9_]{0,31}")      # an investor id (the same pattern as server.RunBody.pilot)
# What a saved run keeps of the private `_analysis` (plan B's `analysis`, per side): the summaries `check_profile` and
# `sensitivity` read, so a recheck works on a replay. Anything else, a price table above all, is left out.
ANALYSIS_KEYS = ("metrics", "lookthrough", "universe", "esg_flags", "scenario_stress", "scenario_family",
                 "scenario_episodes", "scenario_label", "scenario_label_shown", "loss_dollars", "missing_data", "risk",
                 "limits", "amount")
REPLAY_MESSAGES = {
    "bedrock": ("Amazon Bedrock did not answer, so this is the saved run for this exact question, recorded on {date}. "
                "The checklist and the charts were computed the same way."),
    "demo": "Demo mode: this is the saved run for this exact question, recorded on {date}.",
}
DEMO_NO_SAVED_RUN = ("Demo mode: no saved run for this exact question, so the explanation is off. "
                     "The checklist and the charts are computed the same way.")

# Spec 12 keys + ledger 9 (breaches, backdrops) + the additive disclaimer. `figures` holds the six builders of
# ledger 1 and `fall` (ledger 14).
RESULT_KEYS = (
    "run_id", "as_of", "mode", "status", "message", "question", "question_type", "pilot", "amount", "profile",
    "limits", "portfolio", "baseline", "aligned", "scenario", "events", "turbulence", "series", "metrics",
    "worst_rolling", "kpis", "risk", "yield", "rate_regime", "diversification", "lookthrough", "checks", "verdict",
    "tipping_point", "variations", "sensitivity", "attribution", "compare", "price_of_values", "time_machine",
    "facts", "debrief", "receipt", "redteam", "guardrail", "trace", "figures", "realized", "breaches", "backdrops",
    "disclaimer",
)
CHARTS_ABSENT = "charts are drawn by the web from the series"
FIGURE_BUILDERS = {"flight_paths": "flight_paths_figure", "storm_map": "storm_map_figure",
                   "turbulence": "turbulence_figure", "risk_share": "risk_share_figure",
                   "diversification": "diversification_figure", "size_curve": "size_curve_figure",
                   "fall": "fall_figure"}


# ---- the seam to workstreams A and B ----
class EngineUnavailable(Exception):
    """A module of workstream A or B is not on this machine yet. The message is the plain sentence shown."""


@dataclass
class Engine:
    apply_guardrail: Callable            # guardrail
    run_scenario: Callable               # agents.scenario
    keyword_fallback: Callable
    explain: Callable                    # agents.explainer
    load_limits: Callable                # governance
    evaluate: Callable
    check_profile: Callable
    verdict: Callable
    check_order: Callable
    aligned_allocation: Callable         # tools.allocation
    tipping_point: Callable
    comparison_menu: Callable
    sensitivity: Callable
    price_of_values: Callable
    binding_rule: Callable
    load_universe: Callable              # tools.data
    load_market: Callable
    apply_change: Callable               # tools.portfolio
    normalize: Callable                  # additive (ledger 12: callers normalize before apply_change)
    portfolio_series: Callable
    rate_regime: Callable                # tools.metrics
    trailing_yield: Callable
    load_events: Callable                # tools.events
    event_impact: Callable
    drawdown_attribution: Callable
    transmission_report: Callable        # tools.geo (ledger 30: the rows with the look-through's mode and gaps)
    figures_json: Callable               # ui.charts
    figures: dict                        # Result figure key -> ui.charts builder
    memory: object = None                # agents.memory (load, record, types_from), or None: no named-defect memory
    grounding_source: Callable = None    # guardrail.grounding_source, or None: the facts rows go as they are


@functools.cache
def real_engine() -> Engine:
    """The real tools, imported when first needed. A missing module is `EngineUnavailable`, never a traceback."""
    def module(name):
        try:
            return importlib.import_module(name)
        except ImportError as exc:
            raise EngineUnavailable(f"The {exc.name or name} module is not installed yet.") from None

    def pick(mod, name):
        try:
            return getattr(mod, name)
        except AttributeError:
            raise EngineUnavailable(f"The {mod.__name__} module is not ready yet.") from None

    guard, scen, expl, gov, alloc, data, port, met, evs, geo = (module(n) for n in (
        "guardrail", "agents.scenario", "agents.explainer", "governance", "tools.allocation", "tools.data",
        "tools.portfolio", "tools.metrics", "tools.events", "tools.geo"))
    try:                                   # optional (ledger 30): without it the web draws the charts from the series
        charts = importlib.import_module("ui.charts")
    except ImportError:
        charts = None
    if not callable(getattr(charts, "figures_json", None)):
        charts = None
    builders = {key: getattr(charts, fn) for key, fn in FIGURE_BUILDERS.items() if hasattr(charts, fn)} if charts else {}
    try:                                   # optional (ruling R4): without it the debrief is asked exactly as before
        memory = importlib.import_module("agents.memory")
    except ImportError:
        memory = None
    return Engine(
        apply_guardrail=pick(guard, "apply_guardrail"), run_scenario=pick(scen, "run_scenario"),
        keyword_fallback=pick(scen, "keyword_fallback"), explain=pick(expl, "explain"),
        load_limits=pick(gov, "load_limits"), evaluate=pick(gov, "evaluate"),
        check_profile=pick(gov, "check_profile"), verdict=pick(gov, "verdict"), check_order=pick(gov, "check_order"),
        aligned_allocation=pick(alloc, "aligned_allocation"), tipping_point=pick(alloc, "tipping_point"),
        comparison_menu=pick(alloc, "comparison_menu"), sensitivity=pick(alloc, "sensitivity"),
        price_of_values=pick(alloc, "price_of_values"), binding_rule=pick(alloc, "binding_rule"),
        load_universe=pick(data, "load_universe"), load_market=pick(data, "load_market"),
        apply_change=pick(port, "apply_change"), normalize=pick(port, "normalize"),
        portfolio_series=pick(port, "portfolio_series"), rate_regime=pick(met, "rate_regime"),
        trailing_yield=pick(met, "trailing_yield"), load_events=pick(evs, "load_events"),
        event_impact=pick(evs, "event_impact"), drawdown_attribution=pick(evs, "drawdown_attribution"),
        transmission_report=pick(geo, "transmission_report"),
        figures_json=charts.figures_json if charts else _no_figures_json, figures=builders, memory=memory,
        grounding_source=getattr(guard, "grounding_source", None))


def _no_figures_json(fig):
    """The seam's chart serialiser when ui.charts is not installed: never called (there are no builders)."""
    raise EngineUnavailable(CHARTS_ABSENT)


# ---- the trace: one id space for steps, tool calls and facts ----
class Trace:
    """Rows `{id, step, tool, inputs, outputs, source, as_of, ms, service, model, usage, request_id}`; ids are
    T1, T2, ... in creation order, and every facts key is one of them."""

    def __init__(self, as_of=DATASET_END, rows=None):
        self.as_of, self.rows = as_of, [] if rows is None else rows

    def add(self, step, tool, *, inputs=None, outputs=None, source="", ms=0, service="Python", model=None,
            usage=None, request_id=None, detail=None) -> str:
        tid = f"T{len(self.rows) + 1}"
        self.rows.append({"id": tid, "step": step, "tool": tool, "inputs": inputs or {}, "outputs": outputs or {},
                          "source": source, "as_of": self.as_of, "ms": int(ms), "service": service, "model": model,
                          "usage": usage, "request_id": request_id, **({"detail": detail} if detail else {})})
        return tid


def ensure_disclaimer(text: str) -> str:
    """Every answer ends with the disclaimer; code appends it when it is missing (idempotent)."""
    body = str(text or "").rstrip()
    return body if body.endswith(DISCLAIMER) else (body + "\n\n" + DISCLAIMER if body else DISCLAIMER)


def _blank() -> dict:
    return {
        "run_id": None, "as_of": None, "mode": "live", "status": "ok", "message": None, "question": None,
        "question_type": None, "pilot": None, "amount": None, "profile": None, "limits": None, "portfolio": {},
        "baseline": None, "aligned": None, "scenario": None, "events": [], "turbulence": {},
        "series": {"dates": [], "today": [], "after": None, "aligned": None},
        "metrics": {"today": None, "after": None, "aligned": None}, "worst_rolling": {"today": None, "after": None},
        "kpis": {}, "risk": {"today": None, "after": None}, "yield": {"today": None, "after": None},
        "rate_regime": {"hiking": []}, "diversification": {"today": None, "after": None},
        "lookthrough": {"today": None, "after": None}, "checks": [], "verdict": None, "tipping_point": None,
        "variations": [], "sensitivity": None, "attribution": None, "compare": [], "price_of_values": None,
        "time_machine": None, "facts": {}, "debrief": None, "receipt": None, "redteam": None,
        "guardrail": {"input": None, "output": None, "automated_reasoning": None}, "trace": [], "figures": {},
        "realized": None, "breaches": [], "backdrops": [], "disclaimer": DISCLAIMER,
    }


def _new_result(flight_plan: dict, question: str, as_of: str) -> dict:
    r = _blank()
    r.update(run_id=uuid.uuid4().hex[:12], as_of=as_of, question=question, pilot=flight_plan.get("pilot"),
             amount=flight_plan.get("amount"))
    return r


# ---- the typed profile (ledger 15): the question is the only free text ----
PROFILE_KEYS = ("goal", "horizon_years", "risk", "esg", "crypto", "capacity", "reaction_2022")
_ENUMS = {"goal": ("growth", "balance", "preservation", "income"), "risk": ("low", "moderate", "high", None),
          "reaction_2022": ("sold", "held", "bought", None)}
_PROFILE_ERRORS = {
    "goal": "The goal must be one of growth, balance, preservation or income.",
    "horizon_years": "The horizon must be a whole number of years from 1 to 40.",
    "risk": "The risk level must be low, moderate or high.",
    "reaction_2022": "The 2022 reaction must be sold, held or bought.",
    "capacity": "The loss you could absorb must be a number of dollars, 0 or more.",
    "esg": "The values answer must be yes or no.",
    "crypto": "The crypto answer must be yes or no.",
}


def _profile_error(profile) -> str | None:
    """None when every field has its type, else one plain sentence naming the first wrong field."""
    if profile is None:
        return None
    if not isinstance(profile, dict):
        return "The profile must be answers to the questions, not free text."
    for key in PROFILE_KEYS:
        if key not in profile:
            continue
        v = profile[key]
        if key in _ENUMS:
            ok = isinstance(v, str) and v in _ENUMS[key] or v is None and None in _ENUMS[key]
        elif key == "horizon_years":
            ok = type(v) is int and 1 <= v <= 40
        elif key == "capacity":
            ok = v is None or (type(v) in (int, float) and math.isfinite(v) and v >= 0)
        else:
            ok = type(v) is bool
        if not ok:
            return _PROFILE_ERRORS[key]
    return None


def _is_weight(value) -> bool:
    return isinstance(value, numbers.Real) and not isinstance(value, bool) and math.isfinite(value)


def _weights_gap(weights) -> str | None:
    """The one sentence naming how far the weights are from 100 % (ruling R22), or None inside WEIGHT_TOLERANCE. An
    empty or all-zero portfolio is left to normalize's own sentence."""
    total = sum(float(w) for w in weights.values())
    if total <= 0 or abs(total - 1) <= WEIGHT_TOLERANCE:
        return None
    total = round(total, 4)                    # 0.4 + 0.2 is 0.6000000000000001: the sentence says 60 %
    words = WEIGHTS_SHORT if total < 1 else WEIGHTS_OVER
    return words.format(total=_size_words(total), gap=_size_words(round(abs(1 - total), 4)))


def _sign(value) -> str:
    return "negative" if value < 0 else "positive" if value > 0 else "zero"


# ---- pure helpers of the wiring (plan D Task 6) ----
def load_pilots(path=None) -> dict:
    """{pilot_id: card} from data/personas.json (ledger 3): every card that has a name, an amount, a profile and a
    portfolio. {} when the file is missing, unreadable or still has the old keys."""
    try:
        data = json.loads(Path(path or PERSONAS_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    cards = data.get("pilots") if isinstance(data, dict) else None
    if not isinstance(cards, dict):
        return {}
    return {pid: card for pid, card in cards.items()
            if isinstance(card, dict) and all(k in card for k in ("name", "amount", "profile", "portfolio"))}


def _pp(x) -> Decimal:
    """A fraction as percent, ROUND_HALF_UP to 0.1 pp, through repr: the exact twin of governance.round_pp."""
    return (Decimal(repr(float(x))) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _beyond(drop, floor) -> bool:
    """Deeper than the floor, as the checklist rounds it (pitfall 5: -15.00004 % is inside a -15 % floor)."""
    return _pp(drop) < _pp(floor)


def _whole(x) -> int:
    """To the unit, ties away from zero (dollars to the dollar, days to the day)."""
    return int(Decimal(repr(float(x))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _dollars(amount, value) -> float:
    """A base-100 path value in dollars on the fictional amount, to the cent (no float noise)."""
    return round(amount * value / 100, 2)


def _breaches(dates, values, floor, amount) -> list:
    """Every drop deeper than the floor on one base-100 path (ledger 9): from a peak to the first day back at that peak
    (`recovery_date`, None if it never comes back), its lowest day, the depth (trough / peak - 1), the dollars on the
    fictional amount (amount x value / 100; `loss_dollars` = amount x depth, the one rule of the KPI and the facts,
    ledger 30) and the stretches below
    the floor ([first day below, first day back inside], or the last day when it never comes back inside)."""
    out, i, n = [], 0, min(len(dates), len(values))
    while i < n:
        peak, j = i, i + 1
        while j < n and values[j] < values[peak]:
            j += 1
        if j > peak + 1:                                       # an underwater stretch: peak .. j (exclusive)
            low = min(range(peak + 1, j), key=lambda k: values[k])
            depth = round(values[low] / values[peak] - 1, 10)
            if _beyond(depth, floor):
                below, start = [], None
                for k in range(peak + 1, j):
                    under = _beyond(values[k] / values[peak] - 1, floor)
                    if under and start is None:
                        start = k
                    elif not under and start is not None:
                        below.append([dates[start], dates[k]])
                        start = None
                if start is not None:
                    below.append([dates[start], dates[j] if j < n else dates[n - 1]])
                top, bottom = _dollars(amount, values[peak]), _dollars(amount, values[low])
                out.append({"peak_date": dates[peak], "trough_date": dates[low], "recovery_date": dates[j] if j < n else None,
                            "depth": depth, "peak_value": top, "trough_value": bottom,
                            "loss_dollars": round(amount * depth, 2), "below_floor": below})
        i = j
    return out


def _place(lat, lon) -> str:
    """The nearest PLACES label within PLACE_DEGREES of (lat, lon), else ""."""
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return ""
    near = [(abs(lat - a) ** 2 + abs(lon - b) ** 2, name) for name, (a, b) in PLACES.items()
            if abs(lat - a) <= PLACE_DEGREES and abs(lon - b) <= PLACE_DEGREES]
    return min(near)[1] if near else ""


def _limit_source(rule, limits, profile):
    """governance.limit_source (lane sector-limits; LIMITS_MODEL 16:55: every row says where its limit came from), or
    None when the rules engine cannot be read here."""
    try:
        return importlib.import_module("governance").limit_source(rule, limits, profile)
    except Exception as exc:                          # an extra: the checklist still answers without it
        _crash_note("governance.limit_source", exc)
        return None


def _annotate_checks(checks, limits=None, profile=None) -> list:
    """New rows with the plain name (spec 5), `same_cause_as`: for a fail, the rule of the first earlier fail with
    the same holding (one cause, one fail), else None; and, given the limits judged with, `source`: where the row's
    limit came from ("assumed" | "words" | "you", governance.limit_source; None for a row with no limit)."""
    out, first = [], {}
    for c in checks or []:
        holding, fail = c.get("holding"), c.get("status") == "fail"
        cause = first.get(holding) if fail and holding is not None else None
        out.append({**c, "name": verify.RULE_NAMES.get(c.get("rule"), c.get("rule")), "same_cause_as": cause,
                    **({"source": _limit_source(c.get("rule"), limits, profile)} if isinstance(limits, dict) else {})})
        if fail and holding is not None:
            first.setdefault(holding, c.get("rule"))
    return out


def _variation_kind(row, change) -> str | None:
    """What one code-built variation of the move is: `funded_from` (the move funded from one line), `threshold` (the
    same security at another size), or None for another security in its place, which is never shown (spec 24,
    resolution 7)."""
    rc = (row or {}).get("change") or {}
    if rc.get("op") == "fund":
        return "funded_from"
    same = str(rc.get("ticker") or "").upper() == str((change or {}).get("ticker") or "").upper()
    return "threshold" if same and rc.get("ticker") else None


class _Late(Exception):
    """A model step ran past STEP_DEADLINE_S."""


def _with_deadline(fn, seconds):
    """fn() in a worker thread; _Late after `seconds` (the abandoned call ends on botocore's own read timeout)."""
    if float(seconds) <= 0:                             # no time left: the call is never started
        raise _Late()
    box = {}

    def work():
        try:
            box["value"] = fn()
        except BaseException as exc:                    # handed back to the caller's thread
            box["error"] = exc

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    worker.join(max(float(seconds), 0.001))
    if worker.is_alive():
        raise _Late()
    if "error" in box:
        raise box["error"]
    return box.get("value")


def _call_seconds(run) -> tuple:
    """(seconds, by_run): how long one model or safety call may wait, the step deadline or what is left of the run's
    (ledger 15), and whether the run's deadline is the one that binds."""
    left = run.deadline - _now()
    return (left, True) if left < STEP_DEADLINE_S else (STEP_DEADLINE_S, False)


def _past_deadline(run, step) -> None:
    """Ledger 15: the run is past RUN_DEADLINE_S before `step` starts. It stops with one plain sentence; the finished
    steps' trace and numbers stay, and a draft no receipt has checked is never kept (red gate 2)."""
    message = RUN_LATE.format(limit=RUN_DEADLINE_S, step=step.lower())
    run.r["status"], run.r["message"], run.r["debrief"] = "error", message, None
    run.emit(step, "error", ms=0, detail=message)


def _summary(value) -> str:
    """A tool's output summary for a progress line: a dict as "k v, k v", anything else as text."""
    if isinstance(value, dict):
        return ", ".join(f"{k} {v}" for k, v in value.items())
    return "" if value is None else str(value)


# ---- running a step ----
class _Plain(Exception):
    """An expected failure carrying the one plain sentence the page shows."""


def _ms(t0) -> int:
    return int((time.perf_counter() - t0) * 1000)


def _crash_note(what: str, exc: Exception) -> None:
    """One stderr line for an unexpected exception: its type and where it happened, never its text (it could hold the
    user's inputs)."""
    tb = exc.__traceback__
    while tb and tb.tb_next:
        tb = tb.tb_next
    where = f"{tb.tb_frame.f_code.co_filename}:{tb.tb_lineno}" if tb else "?"
    print(f"pipeline: {type(exc).__name__} in {what} at {where}", file=sys.stderr)


class _Run:
    """What the five steps share: the Result, the trace, the engine, the progress callback."""

    def __init__(self, result, engine, progress, use_bedrock, flight_plan):
        self.r, self.engine, self.progress, self.use_bedrock = result, engine, progress, use_bedrock
        self.limits_in = flight_plan.get("limits")
        self.trace = Trace(result["as_of"], result["trace"])
        self.service = dict(SERVICES)
        if use_bedrock:                        # the navigator is the whole UNDERSTAND step: no flip from run to done
            self.service["UNDERSTAND"] = "Amazon Bedrock"
        self.today, self.catalog, self.families = {}, [], list(FAMILIES)
        self.has_change, self.ev_a = False, None
        self.profile = self.limits = self.ev0 = self.exposure = None     # the typed answers and limits the tools get
        self.stopped = None             # "blocked" or "clarify": the steps after it are skipped (STOPPED)
        self.no_model = None if use_bedrock else BEDROCK_OFF    # why EXPLAIN and VERIFY are skipped, if they are
        self.replay = None              # a saved run that replaces this Result (the input check did not answer)
        self.question, self.redteam, self.plan = None, False, flight_plan
        self.context, self.out1, self.planted = None, None, None     # EXPLAIN -> VERIFY: draft 1 and the red-team plant
        self.memory = None              # the defect types earlier runs made (agents.memory), read before draft 1
        self.deadline, self.cut = _now() + RUN_DEADLINE_S, False     # ledger 15; cut: a call stopped by the deadline
        self.labels = dict(STEP_LABELS)

    def emit(self, step, status, *, ms=None, detail=None):
        event = {"type": "progress", "step": step, "label": self.labels[step], "status": status, "ms": ms,
                 "service": self.service[step], "detail": detail}
        try:
            if self.progress:
                self.progress(event)
        except Exception:                      # a broken listener must never stop the run
            pass

    def detail(self, step, text):
        self.emit(step, "detail", detail=text)


def _step(run, step, fn, skip=None) -> bool:
    """Run one step: emit run, time it, emit done / skipped (fn may return ("skipped", sentence)) or error.
    `skip` (a sentence) skips the step up front: one `skipped` event, no `run`. True when the run may go on.
    An unexpected exception becomes one fixed sentence; its text, which could hold the user's inputs, is never
    shown or logged."""
    if skip:
        run.emit(step, "skipped", ms=0, detail=skip)
        return True
    run.emit(step, "run")
    t0, status, detail = time.perf_counter(), "done", None
    try:
        out = fn()
        if out:
            status, detail = out
    except (EngineUnavailable, _Plain) as exc:
        message = str(exc)
    except Exception as exc:
        _crash_note(f"the {step} step", exc)
        message = f"Something went wrong in the {step.lower()} step. The page keeps the last result."
    else:
        run.emit(step, status, ms=_ms(t0), detail=detail)
        return True
    run.r["status"], run.r["message"] = "error", message
    run.emit(step, "error", ms=_ms(t0), detail=message)
    return False


# ---- OBSERVE: read the plan, screen the question, judge today once (spec 7 steps 0 and 0b) ----
def _shown_profile(profile, pilot) -> dict:
    """The typed answers plus the display keys of ledger 9 (the tools and the models only ever get the typed ones)."""
    card = load_pilots().get(pilot) if isinstance(pilot, str) else None
    return {**profile, "name": (card or {}).get("name"), "age": (card or {}).get("age"),
            "in_2022": IN_2022.get(profile.get("reaction_2022")), "capacity_dollars": profile.get("capacity")}


def _observe(run, flight_plan, question):
    r, e = run.r, run.engine
    problem = _profile_error(flight_plan.get("profile"))
    if problem:
        raise _Plain(problem)
    raw = flight_plan.get("profile")
    run.profile = {k: raw[k] for k in PROFILE_KEYS if k in raw} if raw else None
    r["profile"] = dict(run.profile) if run.profile else None
    weights = flight_plan.get("portfolio") or {}
    if not isinstance(weights, dict) or not all(_is_weight(w) for w in weights.values()):
        raise _Plain(BAD_WEIGHT)               # never the tool's own text for a value like "abc"
    gap = _weights_gap(weights)
    if gap:                                    # ruling R22: ask for the rest; nothing runs, no model sees the question
        r["status"], r["message"], run.stopped = "clarify", ensure_disclaimer(gap), "weights"
        return
    try:
        run.today = e.normalize(weights)
    except ValueError as exc:                  # the tool's own plain sentence ("Nothing to normalize: ...")
        raise _Plain(str(exc)) from None
    r["portfolio"] = dict(run.today)
    run.trace.add("OBSERVE", "flight plan (your input)", inputs={"tickers": sorted(run.today)},
                  outputs={"amount": r["amount"], "lines": len(run.today)}, source="Entered by you (fictional, never stored)")
    if run.profile:
        run.limits = e.load_limits(run.profile, run.limits_in, amount=r["amount"])
        r["limits"] = None if run.limits is None else {
            **run.limits, "appetite_floor": run.limits.get("band_floor"), "capacity_dollars": run.profile.get("capacity")}
        run.trace.add("OBSERVE", "governance.load_limits", inputs={"limits_edited": sorted(run.limits_in or {})},
                      outputs={k: (run.limits or {}).get(k) for k in ("floor", "floor_source", "scenario_stress")},
                      source="Your answers and the limits table")
        r["profile"] = _shown_profile(run.profile, r["pilot"])
    else:
        r["status"] = "limits_missing"
        run.detail("OBSERVE", "No answers to the five questions yet, so there is no verdict. Everything else still runs.")
    if not _screen(run, flight_plan, question):
        return
    run.ev0 = _judge(run, run.today, FAMILIES, "today", step="OBSERVE")         # 0b: the navigator reads its exposure
    div, risk = run.ev0.get("diversification") or {}, run.ev0.get("risk") or {}
    run.exposure = {"countries": dict(div.get("countries") or {}), "currencies": dict(div.get("currencies") or {}),
                    "sectors": dict(div.get("sectors") or {}), "risk_shares": dict(risk.get("shares") or {})}


def _screen(run, flight_plan, question) -> bool:
    """Step 0, the one input guardrail call on the question (before any computation). False when the run stops here:
    a blocked question (status "blocked", the guardrail's own sentence; no model ever sees the text), or a check that
    did not answer while a saved run exists for these exact inputs (it replaces the Result). A check that did not
    answer otherwise fails closed: no model runs at all and the keyword rules read the question (ledger 8 and 10).
    Whatever the guardrail let through (or with Bedrock off) then meets the advice check, `_advice_gate`."""
    r, e = run.r, run.engine
    if not run.use_bedrock:
        run.detail("OBSERVE", BEDROCK_OFF)
        return _advice_gate(run, question)
    run.service["OBSERVE"] = "Bedrock Guardrails"
    t0 = time.perf_counter()
    g = e.apply_guardrail(question, "INPUT") or {}
    r["guardrail"]["input"] = g
    run.trace.add("OBSERVE", "guardrail.apply_guardrail(INPUT)", inputs={"text": "<question>"},
                  outputs={k: g.get(k) for k in ("action", "blocked", "error")}, source="Amazon Bedrock Guardrails",
                  ms=g.get("latency_ms") or _ms(t0), service="Bedrock Guardrails", usage=g.get("usage"),
                  request_id=g.get("request_id"))
    if g.get("blocked"):
        r["status"], r["message"] = "blocked", ensure_disclaimer(g.get("message") or BLOCKED)
        run.detail("OBSERVE", "The safety check blocked this question: nothing was sent to a model.")
        run.stopped, run.service["UNDERSTAND"] = "blocked", "Python"         # no navigator ran: no Bedrock badge
        return False
    if g.get("error"):
        saved = load_saved_run(flight_plan, question, r["as_of"], run.redteam, reason="bedrock")
        if saved is not None:
            run.replay = saved
            return False
        run.use_bedrock, run.no_model, r["message"] = False, GUARD_DOWN, GUARD_DOWN
        run.service["UNDERSTAND"] = "Python"
        run.detail("OBSERVE", GUARD_DOWN)
    return _advice_gate(run, question)


def _advice_gate(run, question) -> bool:
    """Code's own advice check (advice_guard.screen), after the input guardrail passed or could not run, and alone when
    Bedrock is off: a request for advice, a size or a forecast stops here as "blocked" with the guardrail's own sentence,
    and no model sees it (red gate 1; lane ev measured 22 / 47 must-block inputs through the live guardrail). One trace
    row, only when it stops. A question it lets through that asks for approval of a move (advice_guard.approval_seeking)
    runs on reframed: Result `reframe` {reason} and one trace row; the page says EPICENTRE can't tell whether a move is
    right for you, and the receipt names a yes / no answer (controller ruling, 2026-11-15)."""
    import advice_guard
    t0 = time.perf_counter()
    s = advice_guard.screen(question)
    if s["ok"]:
        why = advice_guard.approval_seeking(question)
        if why:
            run.r["reframe"] = {"reason": why}
            run.trace.add("OBSERVE", "advice_guard.approval_seeking", inputs={"text": "<question>"},
                          outputs=dict(run.r["reframe"]), source="advice_guard.py (code)", ms=_ms(t0))
        return True
    r = run.r
    run.trace.add("OBSERVE", "advice_guard.screen", inputs={"text": "<question>"},
                  outputs={"ok": False, "kind": s["kind"], "rule": s["rule"]}, source="advice_guard.py (code)", ms=_ms(t0))
    r["status"], r["message"] = "blocked", ensure_disclaimer(s["message"])
    run.detail("OBSERVE", "The advice check stopped this question: nothing was sent to a model.")
    run.stopped, run.service["UNDERSTAND"] = "blocked", "Python"
    return False


# ---- UNDERSTAND: the navigator turns the question into a move and picks the shocks ----
def _move_text(change) -> str:
    """The navigator's change in words, for the progress line: set / add / replace (tools.portfolio.apply_change)."""
    ticker, weight = change.get("ticker"), change.get("weight")
    size = verify.fmt_number(weight, "pct") if weight is not None else None
    if change.get("op") == "replace":
        return f"{change.get('from_ticker')} replaced with {ticker}"
    if change.get("op") == "add" and size:
        return f"{size} added to {ticker}"
    if change.get("op") == "move" and size:                   # a move from one holding alone (Sun Nov 15)
        return f"{size} moved from {change.get('from_ticker')} into {ticker}"
    return f"{ticker} set to {size}" if size else str(ticker)


_SCENARIO_KEYS = ("type", "families", "event_ids", "reasons", "rejected", "tool_calls", "method", "intent",
                  "clarify", "clarify_reason", "widened", "weather", "change", "portfolio", "fallback_reason", "error",
                  "model_calls", "decisions", "engine", "read_from")   # ledger 29: failure keys kept; B Task 9b: decisions,
                                                                   # engine; Sun Nov 15: read_from (the stage's "read from")
_READING_KEYS = ("type", "families", "event_ids", "reasons", "change", "portfolio", "clarify", "clarify_reason",
                 "weather", "method")                # what the keyword rules alone read (board resolution 3)
_NAV_SOURCE = "data/events.csv (sourced shocks known at as_of)"
_REFUSED_CALL = "Refused by code before it ran: nothing was computed"      # a loop call with `error` (B Task 9b)


def _understand(run, question):
    r, e = run.r, run.engine
    run.catalog = e.load_events(r["as_of"])
    navigate = e.run_scenario if run.use_bedrock else e.keyword_fallback
    args = (question, run.today, run.catalog, r["as_of"])
    kwargs = {"profile": run.profile, "limits": run.limits, "universe": e.load_universe(), "exposure": run.exposure,
              "amount": r["amount"]}
    t0 = time.perf_counter()
    sc = navigate(*args, **kwargs) or {}
    took = sc.get("ms") or _ms(t0)
    r["scenario"] = {k: sc.get(k) for k in _SCENARIO_KEYS}
    r["scenario"].update(tool_calls=[dict(c) for c in sc.get("tool_calls") or [] if isinstance(c, dict)],
                         model_calls=[dict(c) for c in sc.get("model_calls") or [] if isinstance(c, dict)],
                         keyword_result=None)
    bedrock = sc.get("method") == "bedrock"
    run.service["UNDERSTAND"] = "Amazon Bedrock" if bedrock else "Python"     # the one that answered
    r["question_type"] = sc.get("type")
    _flight_recorder(run, r["scenario"])
    change, turns = sc.get("change"), bool(r["scenario"]["model_calls"])
    name = "run_scenario" if bedrock else "keyword_fallback"
    run.trace.add("UNDERSTAND", f"agents.scenario.{name}", inputs={"question": "<question>", "as_of": r["as_of"]},
                  outputs={"type": sc.get("type"), "families": sc.get("families"), "event_ids": sc.get("event_ids"),
                           "change": change, "method": sc.get("method")}, source=_NAV_SOURCE, ms=took,
                  service="Amazon Bedrock" if bedrock and not turns else "Python",       # model turns are their own rows
                  usage=None if turns else sc.get("usage"), request_id=None if turns else sc.get("request_id"))
    if bedrock:
        _switch_off(run, sc, args, kwargs)
    if sc.get("clarify"):
        r["status"], r["message"] = "clarify", ensure_disclaimer(sc["clarify"])
        run.stopped = "clarify"
        return
    labels = [FAMILY_LABELS.get(f, f) for f in sc.get("families") or FAMILIES]
    run.detail("UNDERSTAND", NO_PRECEDENT.format(as_of=r["as_of"]) if _abstains(sc)
               else "Shocks to replay: " + ", ".join(labels) + ".")
    if change:
        run.detail("UNDERSTAND", "The move: " + _move_text(change) + ".")


def _flight_recorder(run, sc):
    """Ledger 9 badging: one Python row per navigator tool call (its id written back as `trace_id`), one Bedrock row per
    model turn, one progress line per tool call and per rejected family."""
    for call in sc["tool_calls"]:
        tool, summary = str(call.get("tool") or "tool"), _summary(call.get("output_summary"))
        if call.get("error"):                  # refused (a bad argument, the tool budget): never badged as computed
            error = str(call["error"])
            call["trace_id"] = run.trace.add("UNDERSTAND", f"navigator.{tool}", inputs=dict(call.get("input") or {}),
                                             outputs={"error": error}, source=_REFUSED_CALL, ms=call.get("ms") or 0,
                                             detail="asked for by the navigator; not run")
            run.detail("UNDERSTAND", f"{tool}: not run ({error.rstrip('.')})")
            continue
        call["trace_id"] = run.trace.add("UNDERSTAND", f"navigator.{tool}", inputs=dict(call.get("input") or {}),
                                         outputs={"summary": summary}, source="Read-only tool, computed by code",
                                         ms=call.get("ms") or 0, detail="called by the navigator")
        run.detail("UNDERSTAND", f"{tool}: {summary}")
    for call in sc["model_calls"]:
        run.trace.add("UNDERSTAND", "navigator.model_turn", source="Amazon Bedrock (the navigator chooses words only)",
                      ms=call.get("latency_ms") or 0, service="Amazon Bedrock", model=call.get("model_id") or call.get("model"),
                      usage=call.get("usage"), request_id=call.get("request_id"))
    rejected = sc.get("rejected")
    for fam, why in rejected.items() if isinstance(rejected, dict) else ():
        label, text = FAMILY_LABELS.get(fam, fam), str(why or "").strip()
        text = text[len(label) + 1:].strip() if text.startswith(label + ":") else text
        run.detail("UNDERSTAND", f"Rejected {label}: {text}")


def _switch_off(run, sc, args, kwargs):
    """Board resolution 3: beside every Bedrock run, what the keyword rules alone read on the same inputs. The real
    navigator brings it (`keyword_result`); otherwise it is read here. A failure is a trace row, never the run's."""
    t0 = time.perf_counter()
    kw = sc.get("keyword_result")
    try:
        if not isinstance(kw, dict):
            kw = run.engine.keyword_fallback(*args, **kwargs) or {}
    except Exception as exc:
        _crash_note("the keyword reading", exc)
        run.trace.add("UNDERSTAND", "agents.scenario.keyword_fallback", outputs={"error": f"{type(exc).__name__}: not read"},
                      source=_NAV_SOURCE, ms=_ms(t0))
        return
    run.r["scenario"]["keyword_result"] = {k: kw.get(k) for k in _READING_KEYS}
    run.trace.add("UNDERSTAND", "agents.scenario.keyword_fallback",
                  inputs={"question": "<question>", "as_of": run.r["as_of"], "beside": "agents.scenario.run_scenario"},
                  outputs={k: kw.get(k) for k in ("type", "families", "event_ids", "change", "method")},
                  source=_NAV_SOURCE, ms=kw.get("ms") or _ms(t0))


# ---- COMPARE: judge today and after with the one judge, then the extras ----
def _judge(run, weights, families, which, *, step="COMPARE"):
    """The one judge on one mix with the investor's own limits. Its own sentence (`{"error"}`) stops the run."""
    r = run.r
    t0 = time.perf_counter()
    ev = run.engine.evaluate(run.profile, weights, families, r["as_of"], limits=run.limits_in, amount=r["amount"])
    if not isinstance(ev, dict) or ev.get("error"):
        raise _Plain((ev or {}).get("error") or "The checklist could not be computed.")
    metrics = ev.get("metrics") or {}
    run.trace.add(step, "governance.evaluate", inputs={"which": which, "families": list(families)},
                  outputs={"verdict": ev.get("verdict"), "max_drawdown": metrics.get("max_drawdown")},
                  source=metrics.get("source", ""), ms=_ms(t0))
    return ev


def _judge_extra(run, profile, weights, which, *, amount, limits=None):
    """An evaluation that is not the verdict's own (the illustration mix, another investor): a failure is a trace row
    (the tool's sentence or an exception's type, never its text) and the run goes on."""
    t0 = time.perf_counter()
    try:
        ev = run.engine.evaluate(profile, weights, run.families, run.r["as_of"], limits=limits, amount=amount)
        failure = (ev.get("error") if isinstance(ev, dict) else "not a result") or None
    except Exception as exc:
        _crash_note("governance.evaluate", exc)
        ev, failure = None, f"{type(exc).__name__}: not computed"
    metrics = {} if failure else ev.get("metrics") or {}
    run.trace.add("COMPARE", "governance.evaluate", inputs={"which": which, "families": list(run.families)},
                  outputs={"error": str(failure)} if failure else {"verdict": ev.get("verdict"),
                                                                    "max_drawdown": metrics.get("max_drawdown")},
                  source=metrics.get("source", ""), ms=_ms(t0))
    return None if failure else ev


def _kpis(ev) -> dict:
    """The judge's KPI pairs, copied, with the dollars of the worst drop next to it (amount x drawdown, from the
    judge's analysis), so the page never multiplies amount by percent."""
    kpis = {k: dict(v) if isinstance(v, dict) else v for k, v in ((ev or {}).get("kpis") or {}).items()}
    loss = _clean(((ev or {}).get("analysis") or {}).get("loss_dollars"))
    if loss is not None and isinstance(kpis.get("max_drawdown"), dict):
        kpis["max_drawdown"]["loss_dollars"] = -abs(loss)
    return kpis


def _merge_turbulence(today_ev, after_ev) -> dict:
    """Spec 12 turbulence: per family n, worst_today, worst_after, mean_after, evidence, episodes matched by id."""
    t, a = (today_ev or {}).get("turbulence") or {}, (after_ev or {}).get("turbulence") or {}
    out = {}
    for fam in dict.fromkeys([*a, *t]):
        if fam not in FAMILIES:
            continue
        fa, ft = a.get(fam) or {}, t.get(fam) or {}
        episodes = {}
        for side, src in (("after", fa), ("today", ft)):
            for ep in src.get("episodes") or []:
                row = episodes.setdefault(ep["episode"], {"episode": ep["episode"], "event_ids": ep.get("event_ids", []),
                                                          "trough_today": None, "trough_after": None,
                                                          "confounded": ep.get("confounded", False)})
                row["trough_" + side] = ep.get("trough")
        base = fa or ft
        out[fam] = {"n": base.get("n"), "worst_today": ft.get("worst"), "worst_after": fa.get("worst"),
                    "mean_after": fa.get("mean"), "evidence": base.get("evidence"), "episodes": list(episodes.values())}
    return out


def _slots(today_ev, after_ev, key, pick=lambda x: x):
    """{"today": ..., "after": ...} for a Result key; `after` stays None when the question has no change."""
    return {"today": pick(today_ev.get(key)) if today_ev else None,
            "after": pick(after_ev.get(key)) if after_ev else None}


def _abstains(sc) -> bool:
    """Ledger 30: the navigator's abstention is a weather card with no close precedent and no event picked, never an
    empty family list (which alone still means every family)."""
    return bool(((sc or {}).get("weather") or {}).get("no_precedent")) and not (sc or {}).get("event_ids")


def _compare(run):
    r, e = run.r, run.engine
    sc = r["scenario"]
    families = [] if _abstains(sc) else list(sc.get("families") or FAMILIES)     # no precedent: nothing is replayed
    change = sc.get("change")
    has_change = bool(change and sc.get("portfolio"))
    evaluated = dict(sc["portfolio"]) if has_change else dict(run.today)
    run.has_change, run.families = has_change, families
    ev_after = _judge(run, evaluated, families, "after") if has_change else None
    reuse = run.ev0 is not None and set(families) == set(FAMILIES)        # OBSERVE already judged today on all four
    ev_t = run.ev0 if reuse else _judge(run, run.today, families, "today")
    ev_a = ev_after or ev_t
    today_ev, after_ev = ev_t, ev_after
    paths = (ev_t["series"], ev_a["series"])
    if has_change and paths[0]["dates"] != paths[1]["dates"]:      # one mix trades on one exchange only (ruling R3)
        paths = _one_calendar(run, evaluated)
    r["portfolio"] = dict(evaluated)
    r["series"] = {"dates": list(paths[1]["dates"]), "today": list(paths[0]["values"]),
                   "after": list(paths[1]["values"]) if after_ev else None, "aligned": None}
    r["metrics"] = {**_slots(today_ev, after_ev, "metrics"), "aligned": None}
    r["worst_rolling"] = _slots(today_ev, after_ev, "worst_rolling")
    r["risk"] = _slots(today_ev, after_ev, "risk")
    r["diversification"] = _slots(today_ev, after_ev, "diversification")
    r["lookthrough"] = _slots(today_ev, after_ev, "lookthrough")
    r["turbulence"] = _merge_turbulence(today_ev, after_ev)
    r["kpis"], r["verdict"] = _kpis(ev_a), ev_a.get("verdict")
    r["checks"] = _annotate_checks(_shock_counts(ev_a.get("checks"), ev_a.get("analysis")), ev_a.get("limits"), run.profile)
    if has_change:
        r["baseline"] = {"portfolio": dict(run.today), "verdict": ev_t.get("verdict"),
                         "checks": _annotate_checks(_shock_counts(ev_t.get("checks"), ev_t.get("analysis")),
                                                    ev_t.get("limits"), run.profile),
                         "metrics": ev_t.get("metrics"),
                         "kpis": _kpis(ev_t)}
    sc["check_order"] = e.check_order(r["checks"], run.profile) if r["checks"] else []
    run.ev_a = ev_a
    r["_analysis"] = {"after": ev_a.get("analysis"), "today": ev_t.get("analysis") if has_change else None}   # recheck
    if sc["check_order"] and r["verdict"] in ("Incompatible", "Tension"):
        run.detail("COMPARE", "The check that decided the verdict: "
                   + verify.RULE_NAMES.get(sc["check_order"][0], sc["check_order"][0]) + ".")
    _aligned(run)
    with _judge_memo():                     # the size curve and the variations judge the same mixes once (jury QA S6)
        _compare_extras(run)
        _variations(run)
    _judgement_extras(run)
    _events(run)
    _weather(run)
    _compare_pilots(run)
    floor, path = (run.limits or {}).get("floor"), r["series"]["after"] if has_change else r["series"]["today"]
    if floor is not None and r["amount"]:
        r["breaches"] = _breaches(r["series"]["dates"], path, floor, r["amount"])
    build_facts(r)
    _figures(run)


def _judge_memo():
    """tools.allocation.judge_memo when the module has it (same answers, each mix judged once), else no reuse."""
    try:
        return importlib.import_module("tools.allocation").judge_memo()
    except Exception:                                 # noqa: BLE001 (an engine without it simply judges every mix)
        return contextlib.nullcontext()


def _one_calendar(run, after) -> tuple:
    """Today's path and the after path on the market's union calendar (tools.portfolio, union=True): a mix that trades
    on one exchange keeps its last value on the other exchange's days, so both paths share their dates; the values on
    each mix's own days are the ones judged. A failure is the one plain sentence."""
    t0 = time.perf_counter()
    try:
        today, moved = (run.engine.portfolio_series(mix, as_of=run.r["as_of"], union=True) for mix in (run.today, after))
    except Exception as exc:
        _crash_note("tools.portfolio.portfolio_series", exc)
        today = moved = None
    if not today or not moved or not today.get("dates") or today["dates"] != moved["dates"]:
        raise _Plain("The two paths could not be put on one set of dates.")
    run.trace.add("COMPARE", "tools.portfolio.portfolio_series", inputs={"which": ["today", "after"], "calendar": "union"},
                  outputs={"points": len(today["dates"])}, source=today.get("source", ""), ms=_ms(t0))
    return today, moved


def _extra(run, tool, call):
    """One optional COMPARE extra: the tool's answer ({} when it has nothing to say), or None when it failed. A failure
    goes to the trace like a chart that was not built: the tool's own `{"error": sentence}`, or an exception's type
    (never its text), so a missing curve or backdrop is never unexplained."""
    t0 = time.perf_counter()
    try:
        out = call()
        failure = str(out["error"]) if isinstance(out, dict) and out.get("error") else None
    except Exception as exc:
        _crash_note(tool, exc)
        out, failure = None, f"{type(exc).__name__}: not computed"
    if failure:
        run.trace.add("COMPARE", tool, outputs={"error": failure}, source="", ms=_ms(t0))
        return None
    return out or {}


def _compare_extras(run):
    """The rate backdrop, trailing yields, the size curve and the drawdown attribution: each one tool call."""
    r, e, sc = run.r, run.engine, run.r["scenario"]
    t0 = time.perf_counter()
    rr = _extra(run, "tools.metrics.rate_regime", lambda: e.rate_regime(r["as_of"]))
    r["rate_regime"] = {"hiking": list((rr or {}).get("hiking") or [])}
    r["backdrops"] = [{**HIKING, "start": spell.get("start"), "end": spell.get("end")}
                      for spell in r["rate_regime"]["hiking"] if isinstance(spell, dict)]
    if rr is not None:
        run.trace.add("COMPARE", "tools.metrics.rate_regime", outputs={"hiking_spells": len(r["rate_regime"]["hiking"])},
                      source=rr.get("source", ""), ms=_ms(t0))
    ty_t = _extra(run, "tools.metrics.trailing_yield", lambda: e.trailing_yield(run.today, r["as_of"]))
    ty_a = _extra(run, "tools.metrics.trailing_yield", lambda: e.trailing_yield(r["portfolio"], r["as_of"])) \
        if run.has_change else None
    r["yield"] = {"today": (ty_t or {}).get("value"), "after": (ty_a or {}).get("value")}
    if ty_t is not None:
        run.trace.add("COMPARE", "tools.metrics.trailing_yield", outputs=r["yield"], source=ty_t.get("source", ""))
    if run.has_change and run.profile:
        _tipping(run, sc.get("change"))
    t0 = time.perf_counter()
    att = _extra(run, "tools.events.drawdown_attribution", lambda: e.drawdown_attribution(
        run.ev_a["series"], run.catalog, r["as_of"], metrics=run.ev_a.get("metrics")))
    if att:
        r["attribution"] = att
        run.trace.add("COMPARE", "tools.events.drawdown_attribution", outputs={"shares": att.get("shares")},
                      source=att.get("source", ""), ms=_ms(t0))


def _size_words(x) -> str:
    """A size as the copy writes it: whole percents without decimals ("8 %"), else one decimal ("8.5 %")."""
    q = Decimal(repr(float(x))) * 100
    return verify.fmt_number(x, "pct", 0 if q == q.to_integral_value() else None)


SIZE_BREAK_PATH = "tipping_point.curve.verdict=Incompatible.weight"     # scripts/fill_docs.py's selector: the first Outside


def _size_fact(tp, floor) -> tuple | None:
    """(label, value, path) of the size fact, phrased as history, never as a target (spec 24 resolution 7; design doc
    R2, which replaces ledger 29's "breaks above x"): the FIRST size of the curve judged Outside your limits, the number
    the dial's notch shows (web/lib/dial.js breakAt), never the last size that held. A size of Tension is not a break.
    No size Outside: the floor held up to the curve's top. None without a curve, or when 0 % was already Outside."""
    curve = [p for p in (tp or {}).get("curve") or [] if isinstance(p, dict) and _clean(p.get("weight")) is not None]
    if not curve:
        return None
    i = next((i for i, p in enumerate(curve) if p.get("verdict") == "Incompatible"), None)
    if i is None:
        top = curve[-1]["weight"]
        return f"In this replay, your floor held at every size up to {_size_words(top)}", top, f"tipping_point.curve.{len(curve) - 1}.weight"
    if i == 0:
        return None
    at, drop = curve[i]["weight"], _clean(curve[i].get("max_drawdown"))
    who = "limits" if floor is not None and drop is not None and not _beyond(drop, floor) else "floor"   # another limit first
    return f"In this replay, your {who} first broke at {_size_words(at)}", at, SIZE_BREAK_PATH


def _tipping(run, change):
    """The size curve of the move's own security (max_weight = the size asked) and, for the slider, one dollar path
    per size of the curve (ledger 9), so moving it needs no request."""
    r, e, sc = run.r, run.engine, run.r["scenario"]
    ticker = change["ticker"]
    asked = change.get("weight") if change.get("op") == "set" else r["portfolio"].get(ticker)
    t0 = time.perf_counter()
    tp = _extra(run, "tools.allocation.tipping_point", lambda: e.tipping_point(
        run.profile, run.today, ticker, sc.get("event_ids") or [], r["as_of"], families=run.families,
        limits=run.limits_in, amount=r["amount"], max_weight=asked))
    if not tp:
        return
    tp = {**tp, "curve": [dict(p) for p in tp.get("curve") or [] if isinstance(p, dict)]}
    r["tipping_point"] = tp
    run.trace.add("COMPARE", "tools.allocation.tipping_point", inputs={"ticker": ticker},
                  outputs={"max_weight": tp.get("max_weight"), "still_failing": tp.get("still_failing")},
                  source="governance.evaluate at each size, on the same replay data", ms=_ms(t0))
    size = _size_fact(tp, (run.limits or {}).get("floor"))
    run.detail("COMPARE", f"{size[0]} {ticker}." if size else f"In this replay, your limits broke even without {ticker}.")
    t0 = time.perf_counter()
    paths = _extra(run, "tools.portfolio.portfolio_series", lambda: _size_paths(run, tp, ticker))
    if paths:
        tp["paths"] = paths
        run.trace.add("COMPARE", "tools.portfolio.portfolio_series", inputs={"ticker": ticker, "sizes": len(paths["weights"])},
                      outputs={"paths": len(paths["values"]), "points": len(paths["dates"])},
                      source="tools.portfolio.apply_change + portfolio_series at each size of the curve", ms=_ms(t0))


def _size_paths(run, tp, ticker) -> dict:
    """{weights, values, dates}: at each curve size, today's mix with the security set to it, in dollars on the
    fictional amount (to the dollar), every PATH_EVERY-th trading day and the last. Sets curve[i]["end_value"]."""
    r, e = run.r, run.engine
    weights, values, dates = [], [], None
    for point in tp["curve"]:
        mix = e.apply_change(run.today, {"op": "set", "ticker": ticker, "weight": point.get("weight"), "from_ticker": None})
        path = e.portfolio_series(mix, as_of=r["as_of"], union=True)      # every size on one calendar (ruling R3)
        own = list(path["dates"])
        keep = sorted(set(range(0, len(own), PATH_EVERY)) | ({len(own) - 1} if own else set()))
        if dates is None:
            dates = [own[i] for i in keep]
        elif [own[i] for i in keep] != dates:
            raise ValueError("the size paths are not on one calendar")
        weights.append(point.get("weight"))
        values.append([_whole(r["amount"] * path["values"][i] / 100) for i in keep])
    for point, dollars in zip(tp["curve"], values):
        point["end_value"] = dollars[-1] if dollars else None
    return {"weights": weights, "values": values, "dates": dates or []}


NOT_IN_PACK = "The illustration mix holds {names}, which {verb} not in this data pack, so it was not replayed."


def _and(names) -> str:
    """["A"] -> "A", ["A", "B"] -> "A and B", ["A", "B", "C"] -> "A, B and C"."""
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _not_priced(run, weights) -> list:
    """The tickers of `weights` the data pack has no prices for (the fake pack lacks SPY, QQQ and ESGV), read from the
    market bundle's own columns; [] when the bundle does not list them (a fake market) or cannot be read."""
    try:
        prices = (run.engine.load_market(run.r["as_of"]) or {}).get("prices")
        cols = set(prices.columns) if hasattr(prices, "columns") else None
    except Exception as exc:
        _crash_note("tools.data.load_market", exc)
        cols = None
    return [] if cols is None else sorted(t for t in weights if t not in cols)


def _aligned(run):
    """The fictional illustration mix of the profile (`aligned`, labelled as such) and its path on the same dates."""
    r, e = run.r, run.engine
    if not run.profile:
        return
    al = _extra(run, "tools.allocation.aligned_allocation", lambda: e.aligned_allocation(run.profile))
    if not al or not isinstance(al.get("weights"), dict):
        return
    r["aligned"] = {"weights": dict(al["weights"]), "label": al.get("label")}
    missing = _not_priced(run, r["aligned"]["weights"])
    if missing:                                # D Task 6b item 9: one plain sentence, never an exception's type or text
        run.trace.add("COMPARE", "governance.evaluate", inputs={"which": "illustration", "families": list(run.families)},
                      outputs={"error": NOT_IN_PACK.format(names=_and(missing), verb="is" if len(missing) == 1 else "are")})
        return
    ev = _judge_extra(run, run.profile, r["aligned"]["weights"], "illustration", amount=r["amount"], limits=run.limits_in)
    if ev and list((ev.get("series") or {}).get("dates") or []) == r["series"]["dates"]:
        r["series"]["aligned"], r["metrics"]["aligned"] = list(ev["series"]["values"]), ev.get("metrics")


def _variation_note(row) -> str:
    words, drop = verify.VERDICT_WORDS.get(row.get("verdict"), verify.VERDICT_WORDS[None]), _clean(row.get("max_drawdown"))
    return (f"In this history: worst drop {verify.fmt_number(drop, 'pct')}, {words}." if drop is not None
            else f"In this history: {words}.")


def _variation_label(row, kind) -> str:
    """The variation's name, written by code from its kind and numbers (ledger 30: an allocation label is never passed
    through): "NVDA at 8 %" or "NVDA at 40 %, funded from XIU.TO"."""
    rc = row.get("change") or {}
    size = _size_words(rc["weight"]) if _clean(rc.get("weight")) is not None else None
    name = f"{rc.get('ticker')} at {size}" if size else str(rc.get("ticker"))
    return f"{name}, funded from {rc.get('from_ticker')}" if kind == "funded_from" and rc.get("from_ticker") else name


def _variations(run):
    """The code's variations of the investor's own move (comparison_menu), never ranked; another security in its
    place is left out (spec 24 resolution 7) and counted in the trace."""
    r, e, change = run.r, run.engine, (run.r["scenario"] or {}).get("change")
    if not (run.has_change and run.profile):
        return
    t0 = time.perf_counter()
    menu = _extra(run, "tools.allocation.comparison_menu", lambda: e.comparison_menu(
        run.profile, run.today, change, run.families, r["as_of"], limits=run.limits_in, amount=r["amount"]))
    if menu is None:
        return
    rows = [row for row in menu if isinstance(row, dict)] if isinstance(menu, list) else []
    kept = [{**row, "kind": kind, "label": _variation_label(row, kind), "note": _variation_note(row)} for row in rows
            for kind in [_variation_kind(row, change)] if kind is not None]
    r["variations"] = kept
    run.trace.add("COMPARE", "tools.allocation.comparison_menu", inputs={"ticker": change.get("ticker")},
                  outputs={"rows": len(kept), "left_out": len(rows) - len(kept)},
                  source="governance.evaluate on each variation, on the same replay data", ms=_ms(t0))


_FLIP_LEAD = re.compile(r"^(?:FAKE: )?Outside your limits until your floor is [^;]*?(?:; (?P<rest>.*))?$", re.S)


def _sensitivity_sentence(r, sens) -> str | None:
    """CTO review (Sun Nov 15): what would change the answer, from Result keys: "Only a floor of −34.5 % or lower would
    change this answer." (floor_flip). R35 (the controller, 17:41): the % rule is never priced in the capacity's dollars,
    which belong to the capacity row. The tool's own clause after "; " follows as its own sentence. None: keep the tool's."""
    flip = _clean((sens or {}).get("floor_flip"))
    m = _FLIP_LEAD.match(str((sens or {}).get("sentence") or ""))
    if flip is None or not m:
        return None
    # R35 (controller, 17:41): the % rule is never priced in the capacity's dollars ("instead of the $90,000 ...")
    out = f"Only a floor of {verify.fmt_number(flip, 'pct')} or lower would change this answer."
    rest = (m.group("rest") or "").strip().rstrip(".")
    return out + (f" {rest[0].upper()}{rest[1:]}." if rest else "")


def _judgement_extras(run):
    """Where the verdict would flip (sensitivity) and, for a values screen, its price (price_of_values)."""
    r, e = run.r, run.engine
    analysis = (run.ev_a or {}).get("analysis")
    if run.profile and analysis:
        t0 = time.perf_counter()
        sens = _extra(run, "tools.allocation.sensitivity", lambda: e.sensitivity(
            run.profile, r["portfolio"], analysis, limits=run.limits))
        if sens:
            cost = _sensitivity_sentence(r, sens)
            r["sensitivity"] = {**sens, "sentence": cost} if cost else sens
            run.trace.add("COMPARE", "tools.allocation.sensitivity", outputs={"floor_flip": sens.get("floor_flip")},
                          source="governance.check_profile at each floor, no data reread", ms=_ms(t0))
    if (run.profile or {}).get("esg"):           # ruling R3: on the mix the verdict is about, flagged names removed
        t0 = time.perf_counter()
        pv = _extra(run, "tools.allocation.price_of_values", lambda: e.price_of_values(
            run.profile, dict(r["portfolio"]), r["as_of"]))
        if pv:
            r["price_of_values"] = {**pv, "removed": list(pv.get("removed") or [])}
            run.trace.add("COMPARE", "tools.allocation.price_of_values", outputs={
                "removed": r["price_of_values"]["removed"], "sides": [k for k in ("esg", "non_esg") if pv.get(k)]},
                source=pv.get("source", ""), ms=_ms(t0))


_IMPACT_KEYS = ("trough", "ret_20", "fx_effect", "percentile")


def _impact(run, weights, row):
    """One known event replayed on one mix, or None when it is not measured (its own sentence, or an exception)."""
    try:
        out = run.engine.event_impact(weights, row.get("event_id"), as_of=run.r["as_of"], events=run.catalog)
    except Exception as exc:
        _crash_note("tools.events.event_impact", exc)
        return None
    return out if isinstance(out, dict) and not out.get("error") else None


def _exposure(run, row, look) -> dict:
    """How one event reaches the evaluated mix (tools.geo.transmission_report, ledger 30): `exposed` = its rows, with the
    look-through's `mode` and `gaps` beside them (an empty list in direct mode or with gaps is "not known from holdings",
    never "no exposure"). A failure (a future-dated or unreadable event date, bad weights) is `exposed: None`."""
    try:
        rep = run.engine.transmission_report(run.r["portfolio"], row, lookthrough=look, as_of=run.r["as_of"])
        rows = [dict(x) for x in rep["rows"]]
    except Exception as exc:
        _crash_note("tools.geo.transmission_report", exc)
        return {"exposed": None, "exposed_mode": None, "exposed_gaps": None}
    return {"exposed": rows, "exposed_mode": rep.get("mode"), "exposed_gaps": list(rep.get("gaps") or [])}


def _events(run):
    """Every catalog row known at as_of (spec 12): the move's own replay of each known event, today and after (an event
    still in progress is never measured), the exposure channels on the evaluated mix, whether the navigator picked it,
    and its place."""
    r, e = run.r, run.engine
    picked = set(r["scenario"].get("event_ids") or [])
    look = r["lookthrough"]["after"] if run.has_change else r["lookthrough"]["today"]
    out, measured, unmeasured, links, failed, t0 = [], 0, 0, 0, 0, time.perf_counter()
    for row in run.catalog:
        ev = {k: row.get(k) for k in EVENT_KEYS}
        ev.update(trough_date=None, today=None, after=None, picked=row.get("event_id") in picked,
                  place=row.get("place") or _place(row.get("lat"), row.get("lon")))
        if row.get("known") and not row.get("in_progress"):
            today = _impact(run, run.today, row)
            after = _impact(run, r["portfolio"], row) if run.has_change else None
            side = after or today
            measured, unmeasured = measured + bool(side), unmeasured + (not side)
            ev["today"], ev["after"] = ({k: x.get(k) for k in _IMPACT_KEYS} if x else None for x in (today, after))
            if side:
                ev.update({k: side.get(k) for k in ("episode", "confounded", "t0", "window_end", "trough_date")})
        else:
            ev["window_end"] = None                                    # ledger 6: in progress, never measured
        ev.update(_exposure(run, row, look))
        failed += ev["exposed"] is None
        links += len(ev["exposed"] or [])
        out.append(ev)
    r["events"] = out
    run.trace.add("COMPARE", "tools.events.event_impact", inputs={"events": len(out)},
                  outputs={"measured": measured, "not_measured": unmeasured, "exposed_links": links,
                           "exposure_failed": failed},
                  source="data/events.csv replayed on your mix (tools.events, tools.geo)", ms=_ms(t0))


def _headline(question):
    """The headline the question carries after "Headline:", else None."""
    found = re.search(r"(?:^|\s)Headline:\s*(.+)$", str(question or ""), re.S)
    return found.group(1).strip() or None if found else None


def _weather(run):
    """The weather card (ledger 9): the navigator's, else built by code for a headline or picked shocks; with code's
    why, the precedents and their troughs on the evaluated mix (min to max)."""
    r, sc = run.r, run.r["scenario"]
    ids, w = list(sc.get("event_ids") or []), sc.get("weather")
    if not isinstance(w, dict):
        headline = _headline(run.question)
        if headline is None and not ids:
            return
        rows = [ev for ev in r["events"] if ev["event_id"] in ids]
        w = {"headline": headline, "families": list(run.families), "no_precedent": not ids,
             "regions": sorted({x for ev in rows for x in ev.get("regions") or []})}
    side = "after" if run.has_change else "today"
    troughs = [t for t in (_clean((ev.get(side) or {}).get("trough")) for ev in r["events"] if ev["picked"]) if t is not None]
    labels = " and ".join(FAMILY_LABELS.get(f, f) for f in w.get("families") or run.families or FAMILIES)
    why = (NO_PRECEDENT.format(as_of=r["as_of"]) if _abstains(sc) else
           f"{labels}: the closest sourced shocks known at {r['as_of']}, ranked by code on family, region and your exposure.")
    sc["weather"] = {**w, "why": why,
                     "precedents": [{"event_id": i, "why": (sc.get("reasons") or {}).get(i)} for i in ids],
                     "range_after": {"min": min(troughs), "max": max(troughs)} if troughs else None}


def _binding(checks):
    """The row that decides an investor's verdict: the first fail by tier (hard, soft, preference), else the first warn."""
    for tier in ("hard", "soft", "preference"):
        hit = next((c for c in checks if c.get("status") == "fail" and c.get("tier") == tier), None)
        if hit:
            return hit
    return next((c for c in checks if c.get("status") == "fail"), None) or next(
        (c for c in checks if c.get("status") == "warn"), None)


def _compare_pilots(run):
    """Compare: the evaluated mix judged with each example investor's own answers and amount (data/personas.json)."""
    r, pilots, rows = run.r, load_pilots(), []
    for pid in COMPARE_PILOTS:
        card = pilots.get(pid)
        if not isinstance(card, dict) or not isinstance(card.get("profile"), dict):
            continue
        profile = {k: card["profile"][k] for k in PROFILE_KEYS if k in card["profile"]}
        ev = _judge_extra(run, profile, r["portfolio"], f"compare {pid}", amount=card.get("amount"))
        if ev is None:
            continue
        hit = _binding(ev.get("checks") or [])
        rows.append({"pilot": pid, "name": card.get("name"), "floor": (ev.get("limits") or {}).get("floor"),
                     "verdict": ev.get("verdict"), "binding_rule": hit.get("rule") if hit else None,
                     "reason": hit.get("reason") if hit else "Every limit passes."})
    r["compare"] = rows


def _figures(run):
    """Every chart as plotly JSON, built last from the finished Result. A builder that fails is left out and named."""
    r, e = run.r, run.engine
    if not e.figures:                      # ui.charts is optional (ledger 30): one note, never an error
        run.trace.add("COMPARE", "ui.charts", outputs={"figures": 0, "note": CHARTS_ABSENT}, source="ui.charts (not installed)")
        return
    for key, build in e.figures.items():
        t0 = time.perf_counter()
        try:
            r["figures"][key] = e.figures_json(build(r))
        except Exception as exc:
            run.trace.add("COMPARE", f"ui.charts.{key}", outputs={"error": f"{type(exc).__name__}: not built"},
                          source="ui.charts", ms=_ms(t0))


def _caveats(checks) -> list:
    """The caveat phrases the debrief must say: verify.py's own list (one rule for the explainer and the receipt)."""
    return verify.caveat_phrases(checks)


def _shock_counts(checks, analysis) -> list:
    """New rows; the shock check's row gains the counts its caveat is said with (governance keeps them in the
    analysis, B Task 5): `n_episodes` (clean episodes), `family` (the families replayed) and `evidence`."""
    a = analysis if isinstance(analysis, dict) else {}
    return [{**c, "n_episodes": a.get("scenario_episodes"), "family": a.get("scenario_family"),
             "evidence": a.get("scenario_label_shown") or a.get("scenario_label")}     # titles, never an event id
            if c.get("rule") == "scenario_stress" else c for c in checks or []]


# ---- facts: every number the debrief may quote, one trace row each ----
_USER = "Entered by you (fictional, never stored)"
_LIMITS = "Your answers and the limits table (governance.load_limits)"
_SHOCKS = "Sourced shocks in data/events.csv, replayed on your mix (tools.events.turbulence)"


def _dig(obj, *keys):
    for k in keys:
        obj = obj.get(k) if isinstance(obj, dict) else None
    return obj


def _clean(value):
    """A plain Python int or float, or None for a missing, non-numeric or non-finite value."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return int(value) if isinstance(value, numbers.Integral) else number


CAPACITY_ASSUMED = "What you can afford to lose (assumed for this fictional profile)"     # rulings R13, R35
CAPACITY_TYPED = "What you said you can afford to lose"
FLOOR_LABEL = "Your floor: no fall of more than this from any high"                         # ruling R35 (tolerance)
# R35: a fall in dollars is the path's own; the amount x drawdown rows stay for the page's KPI, never for the explanation
EXPLAIN_LEFT_OUT = ("Dollar loss at the worst drop after the move", "The same drop on your fictional amount",
                    "In this replay, your floor held at every size")       # R20: a size that held is never a pass mark


def _capacity_label(r) -> str:
    """Spec ruling R13: an investor card's dollar limit is an assumption of that fictional profile; a limit the user
    typed is theirs. Assumed when the run's typed answers are exactly a card's (the rule of governance.profile_is_card,
    which words the floor check's reason the same way)."""
    try:
        cards = load_pilots()
    except Exception:                                       # an unreadable personas file never breaks the facts
        cards = {}
    mine = [(r.get("profile") or {}).get(k) for k in PROFILE_KEYS]
    assumed = r.get("profile") is not None and any(
        isinstance(card, dict) and isinstance(card.get("profile"), dict)
        and [card["profile"].get(k) for k in PROFILE_KEYS] == mine for card in (cards or {}).values())
    return CAPACITY_ASSUMED if assumed else CAPACITY_TYPED


def _fact_specs(r) -> list:
    """(label, value, unit, entity, kind, step, tool, path, recipe, source, formula) in the order of plan D Task 2.
    `path` is a Result path, or (path, key) when the last step is a dict key that may hold dots (a ticker like XIU.TO)."""
    lim, prof, sc = r.get("limits") or {}, r.get("profile") or {}, r.get("scenario") or {}
    change = sc.get("change") or {}
    ticker = change.get("ticker")
    m_t, m_a = _dig(r, "metrics", "today") or {}, _dig(r, "metrics", "after") or {}
    fam = None if _abstains(sc) else (sc.get("families") or FAMILIES)[0]     # an abstention replays no family
    word = FAMILY_LABELS.get(fam, fam).lower() if fam else "shock"
    after = "evaluate.after" if m_a else "evaluate.today"
    drop_a, amount = m_a.get("max_drawdown"), r.get("amount")
    loss = round(-abs(amount * drop_a), 2) if drop_a is not None and amount else None   # ledger 14: amount x drawdown
    capacity = prof.get("capacity")
    move = change.get("weight") if change.get("op") == "set" else (r.get("portfolio") or {}).get(ticker)
    turb = (_dig(r, "turbulence", fam) or {}) if fam else {}
    nav = "run_scenario" if sc.get("method") == "bedrock" else "keyword_fallback"
    size = _size_fact(r.get("tipping_point"), lim.get("floor")) or (None, None, SIZE_BREAK_PATH)   # history (R2)
    ev, ds = "governance.evaluate", "COMPARE"
    src_a, src_t = m_a.get("source", ""), m_t.get("source", "")
    return [
        ("Fictional amount", amount, "CAD", "your amount", "fiction", "OBSERVE", "flight plan (your input)", "amount", "flight_plan", _USER, None),
        (f"{FLOOR_LABEL} ({'assumed for this fictional profile' if _capacity_label(r) == CAPACITY_ASSUMED else 'set by you'})", lim.get("floor"), "pct", "your floor", "assumption", "OBSERVE", "governance.load_limits", "limits.floor", "limits", _LIMITS, None),
        (_capacity_label(r), None if capacity is None else -capacity, "CAD", "your capacity", "assumption", "OBSERVE", "flight plan (your input)", "profile.capacity", "flight_plan", _USER, "-profile.capacity"),
        (f"The move: {ticker} set to", move if ticker else None, "pct", ticker, "fiction", "UNDERSTAND", f"agents.scenario.{nav}", "scenario.change.weight", "flight_plan", "Your question, read by the navigator", None),
        ("Worst drop today", m_t.get("max_drawdown"), "pct", "today", "fact", ds, ev, "metrics.today.max_drawdown", "evaluate.today", src_t, None),
        ("Worst drop after the move", drop_a, "pct", "after", "fact", ds, ev, "metrics.after.max_drawdown", "evaluate.after", src_a, None),
        ("Dollar loss at the worst drop after the move", loss, "CAD", "after", "fiction", ds, "amount × drawdown", "metrics.after.max_drawdown", "evaluate.after", src_a, "amount * metrics.after.max_drawdown"),
        ("Worst 12-month drop after the move", _dig(r, "worst_rolling", "after", "value"), "pct", "after", "fact", ds, ev, "worst_rolling.after.value", "evaluate.after", src_a, None),
        ("Growth per year today", m_t.get("cagr"), "pct", "today", "fact", ds, ev, "metrics.today.cagr", "evaluate.today", src_t, None),
        ("Growth per year after the move", m_a.get("cagr"), "pct", "after", "fact", ds, ev, "metrics.after.cagr", "evaluate.after", src_a, None),
        (f"Worst clean {word} shock after the move", turb.get("worst_after"), "pct", fam, "fact", ds, ev, f"turbulence.{fam}.worst_after", "evaluate.after", _SHOCKS, None),
        ("Shock limit (half your floor)", lim.get("scenario_stress"), "pct", "shock check", "assumption", "OBSERVE", "governance.load_limits", "limits.scenario_stress", "limits", _LIMITS, None),
        (f"Clean {word} shocks known", turb.get("n"), "count", fam, "fact", ds, ev, f"turbulence.{fam}.n", after, _SHOCKS, None),
        (f"{ticker} share of the risk after the move", _dig(r, "risk", "after", "shares", ticker) if ticker else None, "pct", ticker, "fact", ds, ev, ("risk.after.shares", ticker), "evaluate.after", _dig(r, "risk", "after", "source") or "", None),
        ("Independent bets after the move", _dig(r, "risk", "after", "bets"), "count", "after", "fact", ds, ev, "risk.after.bets", "evaluate.after", _dig(r, "risk", "after", "source") or "", None),
        (size[0] or "In this replay, your floor first broke at", size[1], "pct", ticker, "fact", ds, "tools.allocation.tipping_point", size[2], "tipping_point", "governance.evaluate at each size, on the same replay data", None),
        ("Days to recover today", m_t.get("recovery_days"), "days", "today", "fact", ds, ev, "metrics.today.recovery_days", "evaluate.today", src_t, None),
        ("Share of the worst drop inside rate-shock windows", _dig(r, "attribution", "shares", "rates"), "pct", "rates", "fact", ds, "tools.events.drawdown_attribution", "attribution.shares.rates", "attribution", _dig(r, "attribution", "source") or "", None),
    ]


# rule -> (value label, unit, limit label, limit entity): every check's value and its limit are facts rows (board
# resolution 6; ledger 30: years and days are facts units, so all 11 rules are citable). short_horizon's value is the
# investor's own answer (◐, entered by you), not a measure of the mix.
CHECK_FACTS = verify._PerIndustry({     # + one pair per industry the investor limited ("sector_cap:<sector>", governance)
    "max_drawdown": ("Worst drop", "pct", "Your floor", "your floor"),
    "scenario_stress": ("Worst clean shock in the shock check", "pct", "Shock limit (half your floor)", "shock check"),
    "single_stock": ("Largest single-company share", "pct", "One-company limit", "one company"),
    "sector": ("Largest sector share", "pct", "One-sector limit", "one sector"),
    "crypto": ("Crypto share", "pct", "Crypto limit", "crypto"),
    "esg_direct": ("Share owned directly against your values", "pct", "Values limit for companies owned directly", "values"),
    "esg_indirect": ("Share inside your funds against your values", "pct", "Values warning level inside your funds", "values"),
    "risk_concentration": ("Largest line's share of the risk", "pct", "Risk-share warning level", "risk"),
    "recovery": ("Days counted by the recovery check", "days", "Recovery days your horizon gives", "recovery"),
    "missing_data": ("Lines with a price gap", "count", "Price gaps allowed", "price gap"),
    "short_horizon": ("Your horizon", "years", "Short-horizon level", "horizon"),
}, lambda sector: (f"{sector} share", "pct", f"Your {sector} limit", f"{sector} limit"))


def _check_specs(r) -> list:
    """One value row and one limit row per check of the evaluated mix, in the checklist's order (same tuple as
    `_fact_specs`). Days are whole days, as the sentences write them."""
    side = "after" if _dig(r, "metrics", "after") else "today"
    words, src = "after the move" if side == "after" else "today", _dig(r, "metrics", side, "source") or ""
    out = []
    for c in r.get("checks") or []:
        spec = CHECK_FACTS.get(c.get("rule"))
        if not spec:
            continue
        label, unit, limit_label, entity = spec
        value, limit = (_clean(c.get(k)) for k in ("value", "limit"))
        if unit == "days":
            value, limit = (None if v is None else _whole(v) for v in (value, limit))
        if c["rule"] == "short_horizon":                      # the answer you gave, not a measure of the mix
            out.append((label, value, unit, entity, "assumption", "OBSERVE", "flight plan (your input)",
                        ("checks.value", c["rule"]), "flight_plan", _USER, None))
        else:
            named, held = f"{label} {words}", c.get("holding")
            if c["rule"] == "esg_direct" and held and held in (r.get("portfolio") or {}):
                named += f" (largest: {held})"      # a line of the mix, so the debrief can name it; never a fund's company
            out.append((named, value, unit, side, "fact", "COMPARE", "governance.evaluate",
                        ("checks.value", c["rule"]), f"evaluate.{side}", src, None))
        out.append((limit_label, limit, unit, entity, "assumption", "OBSERVE", "governance.load_limits",
                    ("checks.limit", c["rule"]), "limits", _LIMITS, None))
    shock = next((c for c in r.get("checks") or [] if c.get("rule") == "scenario_stress"), None)
    n = (shock or {}).get("n_episodes")
    if (shock and shock.get("status") == "warn" and shock.get("value") is not None and isinstance(n, int)
            and not isinstance(n, bool) and n >= verify.MIN_SHOCK_EPISODES):      # the caveat says the count: its own [T#]
        out.append(("Separate earlier episodes the shock check replayed", n, "count", "episodes", "fact", "COMPARE",
                    "governance.evaluate", ("checks.n_episodes", "scenario_stress"), f"evaluate.{side}", src, None))
    return out


def _same_fact(row) -> tuple:
    """What makes two facts rows one number: value, unit, kind and side (a row's entity, or "after"/"today" in its
    label for a ticker or a shock family)."""
    label = row["label"].lower()
    side = row["entity"] if row["entity"] in ("after", "today") else (
        "after" if "after the move" in label else "today" if label.endswith(" today") else row["entity"])
    return row["value"], row["unit"], row["kind"], side


def build_facts(result: dict) -> dict:
    """{"T#": {label, value, unit, entity, sign, kind}} from the Result, one trace row per fact (same id space).
    A fact whose value is None is skipped, and so is a check row whose number is already a row. Idempotent: a Result
    that has facts returns them unchanged."""
    if result.get("facts"):
        return result["facts"]
    trace, facts, seen = Trace(result["as_of"], result["trace"]), {}, set()
    for checked, specs in ((False, _fact_specs(result)), (True, _check_specs(result))):
        for label, value, unit, entity, kind, step, tool, path, recipe, source, formula in specs:
            value = _clean(value)
            if value is None:
                continue
            row = {"label": label, "value": value, "unit": unit, "entity": entity, "sign": _sign(value), "kind": kind}
            if checked and row["unit"] != "years" and _same_fact(row) in seen:   # a horizon of 3 and a level of 3
                continue
            seen.add(_same_fact(row))
            path, key = path if isinstance(path, tuple) else (path, None)
            inputs = {"path": path, **({"key": key} if key else {}), "recipe": recipe,
                      **({"formula": formula} if formula else {})}
            facts[trace.add(step, tool, inputs=inputs, outputs={"value": value}, source=source, ms=0)] = row
    result["facts"] = facts
    return facts


# ---- EXPLAIN and VERIFY (plan D Task 7): one draft, one receipt, at most one re-ask, one output guardrail call ----
BEDROCK_DOWN = "Amazon Bedrock did not answer, so the explanation is off. The checklist and the charts are computed the same way."
WITHHELD = ("The explanation is withheld: it still gave advice after one rewrite. The checklist and the charts are "
            "computed the same way.")            # ledger 15 and red gate 1: advice is never shown, the numbers stay
RETRY_LOW = "The grounding check scored {score:.2f}, under {threshold:.2f}. Use only the facts given."
# Ruling R21 (final, Sun 01:00): output grounding is ADVISORY. The clean control scored 0.52 < 0.70 and 12 of 21
# known-gap copies scored the same (B Task 11; /tmp/epi_stress/receipt/diagnosis.md section 6), so the score cannot
# tell clean from defective text. It stays in VERIFY ("Grounding 0.52 (threshold 0.70)") and in guardrail.output, but
# a low score no longer re-asks or flags; the deterministic receipt (verify.py) is the gate. A check that could not
# run and a denied topic still re-ask. Turn it back on only when a better grounding source puts the clean text at or
# above the threshold and every defective copy below it. Lane gr (Sun Nov 15, live, guardrail version 1): the plain-
# sentence source (guardrail.grounding_source) puts the clean text above it (the control 0.90, the four saved runs
# 0.79 to 0.87; the facts JSON gave them 0.06 to 0.13), but 18 of the 20 known-gap copies too (0.42 to 0.91, median
# 0.85): it still does not separate them, so it stays off (docs/eval_results.md section 8).
GROUNDING_GATES = False
RETRY_NO_CHECK = "The grounding check could not run, so use only the facts given, each with its [T#]."
RETRY_TOPIC = "The safety check found advice about a security. Describe what happened in this history instead."
NOT_SHOWN = "Not shown: this draft gave advice, which the checks named."
PLANTED = "planted by code on request (red-team draft): one wrong number, never written by the model"
GROUNDING_MAX_CHARS, QUERY_MAX_CHARS = 20000, 1000      # spec 7: the facts (as sentences) and the question it reads


def grounding_context(r) -> dict:
    """The verdict words, the limits that broke (in the navigator's check order: the first decided the verdict), the
    caveats and as_of of a Result: what the debrief is given beside the facts, and what the output check's grounding
    source opens with (guardrail.grounding_source). Reads a bare Result too (no scenario: the checks' own order)."""
    order = (r.get("scenario") or {}).get("check_order") or []
    fails = sorted((c for c in r.get("checks") or [] if c.get("status") == "fail"),
                   key=lambda c: order.index(c["rule"]) if c.get("rule") in order else len(order))
    return {"verdict_words": verify.VERDICT_WORDS.get(r.get("verdict")),
            "failed_rules": list(dict.fromkeys(verify.RULE_NAMES.get(c["rule"], c["rule"]) for c in fails)),
            "caveats": _caveats(r.get("checks") or []), "as_of": r.get("as_of"),
            "warnings": list(dict.fromkeys(verify.RULE_NAMES.get(c["rule"], c["rule"]) for c in r.get("checks") or []
                                           if c.get("status") == "warn"))}


def status_context(r) -> dict:
    """In code's words, for the debrief (Sun Nov 15 reviews): which failed rules broke (hard limits: the only ones that
    "broke", web/lib/status.js) and which raised a caution (soft limits and preferences), and the shock check's result
    ("could not conclude" when it had no close precedent or too few separate episodes: never "stayed inside")."""
    order = (r.get("scenario") or {}).get("check_order") or []
    fails = sorted((c for c in r.get("checks") or [] if c.get("status") == "fail"),
                   key=lambda c: order.index(c["rule"]) if c.get("rule") in order else len(order))
    name = lambda c: verify.RULE_NAMES.get(c["rule"], c["rule"])                          # noqa: E731
    out = {"broke": list(dict.fromkeys(name(c) for c in fails if c.get("tier") == "hard")),
           "cautions": list(dict.fromkeys(name(c) for c in fails if c.get("tier") != "hard"))}
    shock = next((c for c in r.get("checks") or [] if c.get("rule") == "scenario_stress"), None)
    if shock is not None:
        n = shock.get("n_episodes")
        if shock.get("value") is None:
            out["shock_check"] = "could not conclude: no close precedent at this date"
        elif isinstance(n, int) and not isinstance(n, bool) and n < verify.MIN_SHOCK_EPISODES:
            out["shock_check"] = "could not conclude: too few separate episodes"
        elif shock.get("status") == "pass":
            out["shock_check"] = "inside the shock limit"
        else:
            out["shock_check"] = "beyond the shock limit (a caution, never a break)"
    return out


def _context(run) -> dict:
    """What the debrief gets beside the facts (never series, chart arrays, trace rows or `realized`)."""
    r = run.r
    return {**grounding_context(r), **status_context(r), "goal": (run.profile or {}).get("goal"),
            "question": r["question"], "intent": r["scenario"].get("intent")}


def _debrief_facts(r) -> dict:
    """The facts rows the debrief is written from (both drafts, and the output check's grounding): result.facts without
    the ids lane sc-b's tools.factors registered for result.scenarios (its `facts` map, never a label). The made-up
    scenarios are fiction and assumptions; the debrief explains the replay (ruling, Sun Nov 15 13:00). The rows stay
    in result.facts for the page's threads and the receipt."""
    facts, sc = r.get("facts") or {}, r.get("scenarios")
    own = sc.get("facts") if isinstance(sc, dict) else None
    ids = {v for v in own.values() if isinstance(v, str)} if isinstance(own, dict) else set()
    return {k: v for k, v in facts.items() if k not in ids and not str(v.get("label", "")).startswith(EXPLAIN_LEFT_OUT)}


def _draft(run, retry_numbers=None, previous=None) -> dict:
    """One explain() call under the step deadline (ledger 15 and 29) and its trace row (id in `_row`); {"error"} when
    it is late. The re-ask also sends draft 1 (`previous`: the model's own verdict sentence, sections and sentences)
    in the context, so the model fixes the named sentences and keeps the rest (Sun Nov 15: a full rewrite made new
    defects in 1 of 12 live re-asks and in Robert's flagship run)."""
    r, e = run.r, run.engine
    t0 = time.perf_counter()
    seconds, by_run = _call_seconds(run)
    context, facts = run.context, _debrief_facts(r)
    if retry_numbers and isinstance(previous, dict):
        context = {**(run.context or {}), "previous": {
            "verdict_sentence": previous.get("verdict_sentence"), "sections": previous.get("sections"),
            "sentences": [{k: s.get(k) for k in ("section", "kind", "text")} for s in previous.get("sentences") or []
                          if isinstance(s, dict)]}}
    try:
        mem = {"memory": run.memory} if e.memory is not None else {}         # ruling R4: both drafts get the memory
        out = _with_deadline(lambda: e.explain(facts, retry_numbers=retry_numbers, argument=None,
                                               context=context, **mem), seconds) or {}
    except _Late:
        run.cut = run.cut or by_run
        out = {"error": RUN_CUT_DRAFT if by_run else f"Amazon Bedrock did not answer within {STEP_DEADLINE_S} s."}
    out = dict(out) if isinstance(out, dict) else {"error": "The explanation was not readable."}
    debrief = out.get("debrief") if isinstance(out.get("debrief"), dict) else None
    text = out.get("text") or (debrief or {}).get("verdict_sentence") or ""
    out["_row"] = run.trace.add(
        "EXPLAIN", "explain.draft", inputs={"facts": len(facts), **({"retry_numbers": list(retry_numbers)} if retry_numbers else {})},
        outputs={"text": text, **({"error": str(out["error"])} if out.get("error") else {})},
        source="Amazon Bedrock, from the facts only", ms=out.get("ms") or _ms(t0), service="Amazon Bedrock",
        model=out.get("model"), usage=out.get("usage"), request_id=out.get("request_id"))
    return out


def _failed(out) -> bool:
    """Bedrock did not give a usable draft: an error, a stop before the end of the turn, or no debrief."""
    return bool(out.get("error")) or out.get("stop_reason") not in (None, "end_turn") or not isinstance(out.get("debrief"), dict)


def _shown(out) -> dict | None:
    """A draft as the page shows it (the disclaimer appended by code), or None when there is no usable debrief."""
    if _failed(out):
        return None
    debrief = out["debrief"]
    return {**debrief, "text": ensure_disclaimer(out.get("text") or debrief.get("verdict_sentence") or ""), "flagged": False}


_PCT_RX = re.compile(r"(?<![\w.])(?P<sign>[−-])?(?P<num>\d+(?:\.\d+)?)(?P<sp>\s?)%")


def _pool_index(debrief, i) -> int | None:
    """The index in `sentences` of the receipt's sentence number i (verify numbers the verdict 1, then the sections in
    order), or None when that sentence is not a pool entry the sections list by index."""
    n = 1 if debrief.get("verdict_sentence") else 0
    for name in verify.SECTION_ORDER:
        val = (debrief.get("sections") or {}).get(name)
        for e in [val] if isinstance(val, (str, dict)) or type(val) is int else list(val or []):
            if type(e) is not int:                # a text or dict entry: verify numbers it its own way, stop here
                return None
            n += 1
            if n == i:
                return e
    return None


def _inject_redteam(debrief, facts) -> tuple:
    """The red-team draft (plan D Task 7, only on request): in the first sentence after the verdict that has a % number
    and cites exactly one row, the number equal to that row's value is written 0.1 pp higher, in the same format
    ("10.6 %" -> "10.7 %"). Returns (new debrief, {"sentence", "from", "to"}) or (debrief, None); never in place."""
    for item in verify._sentences(debrief):
        k = _pool_index(debrief, item["i"]) if item["section"] != "verdict" else None
        row = facts.get(item["refs"][0]) if len(item["refs"]) == 1 else None
        if k is None or not row or row.get("unit") not in ("pct", "pp"):
            continue
        for m in _PCT_RX.finditer(item["text"]):
            places = len(m["num"].split(".")[1]) if "." in m["num"] else 0
            if Decimal(m["num"]) != verify._quant(abs(Decimal(str(row["value"]))) * 100, places):
                continue
            step = max(places, 1)
            bigger = verify._quant(Decimal(m["num"]) + Decimal("0.1"), step)
            planted = f"{m['sign'] or ''}{bigger:.{step}f}{m['sp']}%"
            text = item["text"][:m.start()] + planted + item["text"][m.end():]
            sentences = [dict(s) if isinstance(s, dict) else {"text": s} for s in debrief.get("sentences") or []]
            sentences[k] = {**sentences[k], "text": text}
            return ({**debrief, "sentences": sentences},
                    {"sentence": item["i"], "from": m.group(0), "to": planted, "_old": item["text"], "_new": text})
    return debrief, None


def _redteam(run, out) -> dict:
    """Plant the red-team number in draft 1 and trace it as planted (one Python row right after the draft's)."""
    debrief, injected = _inject_redteam(out["debrief"], run.r["facts"])
    if injected is None:
        run.trace.add("EXPLAIN", "redteam.inject", outputs={"planted": False, "reason": "no sentence with one % row"},
                      source="pipeline._inject_redteam", detail=PLANTED)
        return out
    old, new = injected.pop("_old"), injected.pop("_new")
    text = (out.get("text") or "").replace(old, new, 1)
    run.planted = injected
    run.trace.add("EXPLAIN", "redteam.inject", inputs={"sentence": injected["sentence"]},
                  outputs={"planted": True, "from": injected["from"], "to": injected["to"], "text": text},
                  source="pipeline._inject_redteam", detail=PLANTED)
    return {**out, "debrief": debrief, "text": text}


def _number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _guard_text(debrief) -> str:
    """What the output guardrail scores: the sentences joined, without the [T#] tags and the disclaimer."""
    text = " ".join(item["text"] for item in verify._sentences(debrief))
    return " ".join(verify._TAG_RE.sub(" ", text).replace(DISCLAIMER, " ").split())


def _scored(g) -> bool:
    """The output check answered with a grounding score (it ran and scored, not an error)."""
    gr = (g or {}).get("grounding") if isinstance((g or {}).get("grounding"), dict) else {}
    return bool(g) and not g.get("error") and _number(gr.get("score")) and _number(gr.get("threshold"))


def _output_check(run, debrief, draft) -> dict:
    """One output guardrail call on the draft that is (or would be) shown (ledger 15 and 30). Grounding source = what
    the explainer was given, as plain sentences (guardrail.grounding_source: the verdict and the limits that broke,
    then one sentence per facts row; <= 20,000 characters), never the facts JSON (lane gr: it scored clean,
    receipt-verified explanations 0.06 to 0.13 live); query = the question (<= 1,000). The last call is the shown
    draft's. An engine without the builder sends the facts rows, which the guardrail writes as sentences itself."""
    r, t0 = run.r, time.perf_counter()
    facts, build = jsonable(_debrief_facts(r)), run.engine.grounding_source
    if callable(build):
        try:
            facts = build(facts, run.context or grounding_context(r))[:GROUNDING_MAX_CHARS]
        except Exception as exc:          # a builder bug never costs the check: the guardrail writes the rows itself
            _crash_note("guardrail.grounding_source", exc)
    text, query = _guard_text(debrief), str(r["question"] or "")[:QUERY_MAX_CHARS]
    seconds, by_run = _call_seconds(run)
    try:
        g = _with_deadline(lambda: run.engine.apply_guardrail(text, "OUTPUT", facts=facts, query=query), seconds)
    except _Late:                                         # a hung check holds VERIFY no longer than one model step
        run.cut = run.cut or by_run
        g = {"error": RUN_CUT_CHECK if by_run else f"The safety check did not answer within {STEP_DEADLINE_S} s."}
    except Exception as exc:
        _crash_note("guardrail.apply_guardrail(OUTPUT)", exc)
        g = None
    g = {**(g if isinstance(g, dict) else {"error": "The safety check could not run."}), "draft": draft}
    r["guardrail"]["output"], r["guardrail"]["automated_reasoning"] = g, g.get("automated_reasoning")
    gr = g.get("grounding") if isinstance(g.get("grounding"), dict) else {}
    run.trace.add("VERIFY", "guardrail.output", inputs={"draft": draft},
                  outputs={"score": gr.get("score"), "threshold": gr.get("threshold"), "detected": gr.get("detected"),
                           "latency": g.get("latency_ms"), "topic_hit": g.get("topic_hit"), "error": g.get("error")},
                  source="Amazon Bedrock Guardrails (contextual grounding against the facts, as plain sentences)",
                  ms=g.get("latency_ms") or _ms(t0), service="Bedrock Guardrails", usage=g.get("usage"),
                  request_id=g.get("request_id"))
    if _scored(g):
        run.detail("VERIFY", f"Grounding {gr['score']:.2f} (threshold {gr['threshold']:.2f})")
    return g


def _guard_lines(g) -> list:
    """The output check's findings as re-ask lines (plan B's contract): no check, low grounding, the denied topic.
    [] when it passed. No Automated Reasoning policy is attached (spec 24 res. 10, spec 7 honest claims): a finding
    it reports is carried in `guardrail.automated_reasoning`, never turned into a claim or a re-ask."""
    if not g:
        return []
    if g.get("error"):
        return [RETRY_NO_CHECK]
    out, gr = [], g.get("grounding") if isinstance(g.get("grounding"), dict) else {}
    score, threshold = gr.get("score"), gr.get("threshold")
    low = _number(score) and _number(threshold) and score < threshold
    if GROUNDING_GATES and (gr.get("detected") or low):
        out.append(RETRY_LOW.format(score=score, threshold=threshold) if _number(score) and _number(threshold)
                   else RETRY_NO_CHECK)
    if g.get("topic_hit"):
        out.append(RETRY_TOPIC)
    return out


def _receipt(run, debrief, catalog, draft) -> dict:
    t0 = time.perf_counter()
    receipt = verify.verify_numbers(debrief, run.r["facts"], as_of=run.r["as_of"], result=run.r, catalog=catalog)
    run.trace.add("VERIFY", "verify.receipt", inputs={"draft": draft},
                  outputs={"verified": receipt["verified"], "total": receipt["total"], "defects": receipt["defects"]},
                  source="verify.py (deterministic, no model)", ms=_ms(t0))
    return receipt


def _not_shown(run, row_id) -> None:
    """Red gate 1: a draft that gave advice keeps its trace row, without its text."""
    for row in run.r["trace"]:
        if row["id"] == row_id or (row_id == run.out1.get("_row") and row["tool"] == "redteam.inject"):
            row["outputs"] = {**row["outputs"], "text": NOT_SHOWN}


def _memory_load(run) -> None:
    """Level 10 (ruling R4): the defect types earlier runs made, read once before draft 1 (a re-ask gets the same). No
    memory on the engine: nothing is read and explain() is asked exactly as before. A failure is one trace row and the
    run goes on with no memory."""
    mem = run.engine.memory
    if mem is None:
        return
    try:
        loaded = mem.load(MEMORY_PATH)
        run.memory = [t for t in loaded if isinstance(t, str)] if isinstance(loaded, (list, tuple)) else []
        outputs = {"types": list(run.memory)}
    except Exception as exc:
        _crash_note("agents.memory.load", exc)
        run.memory, outputs = None, {"error": f"{type(exc).__name__}: not read"}
    run.trace.add("EXPLAIN", "agents.memory.load", inputs={"file": MEMORY_PATH.name}, outputs=outputs, source=MEMORY_SOURCE)


def _memory_record(run, rc1, out1, rc2, out2) -> None:
    """After the final receipt (ruling R4): one more run counted for each defect type the model's drafts made (the
    receipts' buckets and lines, the explainer's structural lines). A red-team draft 1 holds a number code planted, so
    only its explainer lines count. Types only, never text (red gate 6). A failure is one trace row."""
    mem = run.engine.memory
    if mem is None:
        return
    try:
        found = list(mem.types_from(receipt=None if run.planted else rc1, defects=(out1 or {}).get("defects")))
        if rc2 is not None:
            found += list(mem.types_from(receipt=rc2, defects=(out2 or {}).get("defects")))
        types = list(dict.fromkeys(found))
        mem.record(MEMORY_PATH, types)
        outputs = {"types": types}
    except Exception as exc:
        _crash_note("agents.memory.record", exc)
        outputs = {"error": f"{type(exc).__name__}: not recorded"}
    run.trace.add("VERIFY", "agents.memory.record", inputs={"file": MEMORY_PATH.name}, outputs=outputs, source=MEMORY_SOURCE)


def _explain(run):
    """Draft 1 (and, on request, the red-team plant). A draft Bedrock did not give replays the saved run of these exact
    inputs, else the explanation is off with one plain sentence and every number stays."""
    r = run.r
    run.context = _context(run)
    _memory_load(run)
    t0 = time.perf_counter()
    out = _draft(run)
    if _failed(out):
        saved = load_saved_run(run.plan, run.question, r["as_of"], run.redteam, reason="bedrock")
        if saved is not None:
            run.replay = saved
            return "done", "Amazon Bedrock did not answer: the saved run of this exact question answers."
        r["message"] = BEDROCK_DOWN
        return "skipped", BEDROCK_DOWN
    if run.redteam:
        out = _redteam(run, out)
    run.out1 = out
    r["debrief"] = {**_with_code_lead(run, _shown(out)), "flagged": True}    # unchecked until VERIFY's receipt clears it
    run.detail("EXPLAIN", f"Draft written in {out.get('ms') or _ms(t0)} ms")


def _verify(run):
    """Receipt 1; the output guardrail on the draft that will be shown; ONE re-ask when the receipt, the explainer's
    structural check or the output check names a defect (ledger 29: keyed on `defects`, never on verified == total);
    receipt 2. The text shown is always the text scored (ledger 30): a second output call only when the guardrail itself
    asked for the re-ask. No loop: at most two drafts and two output checks per run."""
    r = run.r
    if r["debrief"] is None or run.out1 is None:
        return "skipped", "There is no explanation to trace."
    catalog = [{"event_id": x.get("event_id"), "title": x.get("title"), "date": x.get("date")}
               for x in run.engine.load_events(DATASET_END)]      # read by the checker only, never sent to an agent
    out1 = run.out1
    first = {k: v for k, v in r["debrief"].items() if k != "flagged"}
    rc1 = _receipt(run, first, catalog, 1)
    if run.planted:
        said = f"Sentence {run.planted['sentence']} says {run.planted['to']}"
        r["redteam"] = {"injected": dict(run.planted), "fixed": False,
                        "defect": next((d for d in rc1["defects"] if d.startswith(said)), None)}
    named = list(dict.fromkeys([*rc1["defects"], *(str(d) for d in out1.get("defects") or [])]))
    g1 = None if named else _output_check(run, first, 1)       # draft 1 is the one shown unless it is re-asked
    named = named or _guard_lines(g1)
    shown, out, rc, drafts, g = first, out1, rc1, 1, g1
    if named:
        run.detail("VERIFY", f"Re-asked once with {len(named)} named defects")
        out2 = _draft(run, retry_numbers=named, previous=first)
        second = _with_code_lead(run, _shown(out2))
        if second is not None:
            shown, out, drafts = {k: v for k, v in second.items() if k != "flagged"}, out2, 2
            rc = _receipt(run, shown, catalog, 2)
        if g1 is None or drafts == 2:                         # the text shown is the text scored (ledger 30)
            g = _output_check(run, shown, drafts)
    _finish(run, shown, out, rc, rc1, g1, g, drafts, catalog=catalog)
    _memory_record(run, rc1, out1, rc if drafts == 2 else None, out if drafts == 2 else None)


_BANNED_LINE = re.compile(r"^Sentence \d+ uses the words? '")    # agents/explainer.py `_banned_line` (buy, sell, hold...)


def _gave_advice(receipt, out) -> bool:
    """Advice left in a draft (ledger 30 withholding): the receipt's advice and forecast words, or one of the
    explainer's banned-word lines (B is stricter on an instruction-form "hold" than the receipt)."""
    return bool(receipt["advice"]) or any(_BANNED_LINE.match(str(d)) for d in (out or {}).get("defects") or [])


# Guarantees, not rates (CTO review, Sun Nov 15, approved): a sentence whose defect survives the one re-ask is
# removed from the explanation shown, and the receipt lists what was removed; with fewer than 2 clean sentences left (or
# the verdict sentence itself named) the explanation is not shown and the checks' own sentences, written by code, stand
# in for it. A shown explanation never contains a defect the receipt or the explainer's check named.
CODE_SHOWN = ("The explanation is not shown: after the one re-ask, fewer than 2 of its sentences passed the receipt, so "
              "the checks' own sentences, written by code, stand in for it.")
DROPPED_DETAIL = "Removed {n} sentence{s} the receipt still named after the re-ask"
_NAMED = re.compile(r"^Sentence (\d+) ")


def _named_sentences(lines) -> set:
    """The sentence numbers (the receipt's numbering: the verdict is 1) that defect lines name."""
    return {int(m.group(1)) for line in lines or [] if isinstance(line, str) for m in [_NAMED.match(line)] if m}


def _without(debrief, numbers) -> dict:
    """The debrief without the named sentences (2.. in the receipt's order: the sections in order), re-indexed, and its
    text rendered again the way the explainer renders it (the verdict, each answered question, the disclaimer)."""
    sections = debrief.get("sections") or {}
    order = [i for name in verify.SECTION_ORDER for i in sections.get(name) or []]
    drop = {order[n - 2] for n in numbers if 2 <= n < len(order) + 2}
    rows = list(debrief.get("sentences") or [])
    kept = [i for i in range(len(rows)) if i not in drop]
    new = {old: k for k, old in enumerate(kept)}
    sentences = [rows[i] for i in kept]
    secs = {name: [new[i] for i in sections.get(name) or [] if i in new] for name in verify.SECTION_ORDER}
    blocks = [str(debrief.get("verdict_sentence") or "")]
    blocks += [verify.SECTION_TITLES[name] + "\n" + " ".join(sentences[i]["text"] for i in secs[name])
               for name in verify.SECTION_ORDER if secs[name]]
    return {**debrief, "sentences": sentences, "sections": secs, "text": ensure_disclaimer("\n\n".join(blocks))}


_RULE_WORDS_SHOWN = {"Your floor": "your floor", "Shock check": "the shock check", "One company": "the one-company limit",
                     "One sector": "the one-sector limit", "Crypto share": "the crypto limit", "Values": "your values limit"}


def _consequence_lead(r, words, side) -> str | None:
    """The cold first-time user (Sun Nov 15, 17:50: "the why goes in a circle"): when the floor decided it and the mix
    went below your capacity line, the lead says what that meant, in the path's own dollars, from keys only (capacity.
    <side>.low_value and low_date, capacity.line, profile.horizon_years), each number with the [T#] of its row: "Outside
    your limits: in Oct 2022 the mix with the move fell to $408,174 [T206], below your capacity line of $510,000 [T202],
    and your horizon is 4 years [T54]." None (the plain lead) when the low stayed above the line or a row is missing."""
    cap = r.get("capacity") if isinstance(r.get("capacity"), dict) else {}
    part = cap.get("today" if side == "today" else "after") or {}
    low, line, when = part.get("low_value"), cap.get("line"), str(part.get("low_date") or "")
    number = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)          # noqa: E731
    if not (number(low) and number(line) and low < line and re.fullmatch(r"\d{4}-\d{2}-\d{2}", when)):
        return None
    facts = r.get("facts") or {}
    mix = "your mix today" if side == "today" else "your mix with the move"

    def tag(test):
        return next((t for t, row in facts.items() if isinstance(row, dict) and test(row)), None)

    t_low = tag(lambda row: row.get("unit") == "CAD" and str(row.get("label") or "").startswith(f"Lowest value of {mix}")
                and abs(float(row.get("value") or 0) - low) < 0.5)
    t_line = tag(lambda row: row.get("unit") == "CAD" and str(row.get("label") or "").startswith("Your capacity line")
                 and abs(float(row.get("value") or 0) - line) < 0.5)
    t_years = tag(lambda row: row.get("unit") == "years" and row.get("label") == "Your horizon")
    if not (t_low and t_line):
        return None
    years = facts[t_years]["value"] if t_years else None
    horizon = (f", and your horizon is {verify.fmt_number(Decimal(str(years)), 'years')} [{t_years}]"
               if number(years) and years > 0 else "")
    month = datetime.strptime(when, "%Y-%m-%d").strftime("%b %Y")
    who = "your mix today" if side == "today" else "the mix with the move"
    return f"{words}: in {month} {who} fell to ${low:,.0f} [{t_low}], below your capacity line of ${line:,.0f} [{t_line}]{horizon}."


def _code_verdict(run) -> str:
    """The lead sentence, written by CODE from the deciding check (ruling R39, Sun Nov 15: Robert's 2022 fall decided,
    not "the tariff replay"), in the past tense (R1), with no number (so the receipt has nothing to trace in it):
    a hard limit that broke decided it ("the 2022 fall decided it: your floor broke after the move"); a soft limit, a
    preference or a warning raised the caution; with none, none of your limits broke."""
    r = run.r
    words = verify.VERDICT_WORDS.get(r.get("verdict")) or verify.VERDICT_WORDS[None]
    order = (r.get("scenario") or {}).get("check_order") or []
    def abstained(c):          # ruling R51: a shock check that could not conclude never moves the verdict, and it is
        n = c.get("n_episodes")                 # never a caution or a warning either (jury QA, the aliens card)
        return c.get("rule") == "scenario_stress" and c.get("status") == "warn" and (
            c.get("value") is None or (isinstance(n, int) and not isinstance(n, bool) and n < verify.MIN_SHOCK_EPISODES))

    quiet = next((c for c in r.get("checks") or [] if abstained(c)), None)
    rows = sorted((c for c in r.get("checks") or [] if c.get("status") in ("fail", "warn") and not abstained(c)),
                  key=lambda c: (c.get("status") != "fail", c.get("tier") != "hard",
                                 order.index(c["rule"]) if c.get("rule") in order else len(order)))
    side = "after the move" if _dig(r, "metrics", "after") else "today"
    if not rows and quiet is not None:
        why = "no close precedent" if quiet.get("value") is None else "too few separate episodes"
        return f"{words}: none of your limits broke; the shock check could not conclude ({why})."
    if not rows:
        return f"{words}: none of your limits broke in this replay."
    c = rows[0]
    if r.get("verdict") == "Compatible":          # a warning level crossed is not a limit (and not a caveat here)
        wname = verify.RULE_NAMES.get(c["rule"], c["rule"]).lower()
        return f"{words}: no limit broke. One warning level was crossed, {wname}, and a warning is not a limit."
    name = _RULE_WORDS_SHOWN.get(verify.RULE_NAMES.get(c["rule"], ""), verify.RULE_NAMES.get(c["rule"], c["rule"]).lower())
    if c["status"] == "fail" and c.get("tier") == "hard":
        if c["rule"] == "max_drawdown":
            said = _consequence_lead(r, words, side)                # the floor that decided it, in the path's dollars
            if said:
                return said
            when = str(_dig(r, "metrics", "after" if side != "today" else "today", "trough_date") or "")[:4]
            fall = f"the {when} fall" if when.isdigit() else "the worst fall"
            return f"{words}: {fall} decided it; your floor broke with the mix {side}."
        if c["rule"] == "esg_direct" and c.get("holding"):
            return f"{words}: your values screen decided it; you own {c['holding']} directly."
        return f"{words}: {name} broke and decided it."
    if c["status"] == "fail":                    # a soft limit the mix went past (jury QA: never "never broke")
        return f"{words}: none of your hard limits broke; the mix {side} went past {name}, a soft limit: a caution."
    return f"{words}: none of your hard limits broke; {name} raised the caution."


def ai_off_sentence(effect, checks) -> str | None:
    """Ruling R37 (honest AI value), from Result keys only: whether switching the AI off changes the verdict, then the
    question the shock check answers with and without it ("... replays all 26 episodes (worst −13.6 %) instead of the 6
    tariff war episodes you asked about (worst −9.0 %)"). None when the verdict without the AI is unknown."""
    effect = effect if isinstance(effect, dict) else {}
    v, vw = effect.get("verdict"), effect.get("verdict_without")
    if v is None or vw is None:
        return None
    word = lambda x: verify.VERDICT_WORDS.get(x) or str(x)                       # noqa: E731
    out = (f"Switching the AI off changes no verdict here: {word(v)} either way." if v == vw
           else f"Switching the AI off changes the verdict: {word(v)} with it, {word(vw)} without.")
    pick = lambda rows: next((dict(c) for c in rows or [] if isinstance(c, dict) and c.get("rule") == "scenario_stress"),
                             None)          # noqa: E731  (copies: the Result's rows are never changed)
    a, b = pick(checks), pick(effect.get("checks_without"))
    if not (a and b) or a.get("value") is None or b.get("value") is None:
        return out
    if (a.get("n_episodes"), a.get("family")) == (b.get("n_episodes"), b.get("family")):
        return out
    def counted(row):
        """(n, family) from the row, else from its own reason ("In the 26 separate earlier Tariff war + ... episodes")."""
        n, fam = row.get("n_episodes"), row.get("family")
        m = re.search(r"In the (\d+) separate earlier (.+?) episodes", str(row.get("reason") or ""))
        if (n is None or not fam) and m:
            n, fam = (int(m.group(1)) if n is None else n), (fam or m.group(2))
        return n, fam
    for row in (a, b):
        row["n_episodes"], row["family"] = counted(row) if row is not None else (None, None)
    if any(row.get("n_episodes") is None or not row.get("family") for row in (a, b)):
        return out                                 # nothing honest to compare: the first sentence alone

    def which(row, own):
        fams = [f for f in str(row.get("family") or "").split(" + ") if f]
        n = row.get("n_episodes")
        what = f"all {n} episodes" if len(fams) == len(FAMILIES) else f"the {n} {' + '.join(fams).lower()} episodes"
        return f"{what}{' you asked about' if own else ''} (worst {verify.fmt_number(row['value'], 'pct')})"
    return (out + f" It changes the question answered: without it, the shock check replays {which(b, False)} instead of "
            f"{which(a, True)}.")


def _ai_off_sentence(result) -> None:
    effect = result.get("navigator_effect")
    if isinstance(effect, dict):
        said = ai_off_sentence(effect, result.get("checks"))
        if said:
            effect["sentence"] = said


def _with_code_lead(run, debrief):
    """R39: the draft's lead sentence replaced by code's own (_code_verdict), before the receipt and the output check
    read it, so the text scored is the text shown (ledger 30). None stays None."""
    if not isinstance(debrief, dict):
        return debrief
    said, old, text = _code_verdict(run), str(debrief.get("verdict_sentence") or ""), str(debrief.get("text") or "")
    new_text = text.replace(old, said, 1) if old and old in text else ensure_disclaimer(said + ("\n\n" + text if text else ""))
    return {**debrief, "verdict_sentence": said, "text": new_text, "lead_by": "code"}


def _finish(run, shown, out, rc, rc1, g1, g, drafts, catalog=None):
    """The final receipt and debrief: flagged when a defect is left on the shown draft (receipt, structural, or its own
    output check, including one that could not run), withheld when advice or a denied topic is left (red gate 1,
    ledger 15 and 30), never hidden otherwise. `g` is the shown draft's output check; VERIFY says "grounding" only when
    it scored."""
    r = run.r
    left = rc["defects"] or list(out.get("defects") or []) or _guard_lines(g)
    flagged = bool(left or (run.planted and drafts == 1))
    if r["redteam"] is not None:
        r["redteam"]["fixed"] = drafts == 2 and not any(
            d.startswith(f"Sentence {run.planted['sentence']} ") for d in rc["defects"])
    r["receipt"] = {**rc, "first_try": {k: rc1[k] for k in ("verified", "total", "defects")}, "drafts": drafts}
    if _gave_advice(rc1, run.out1) or (g1 or {}).get("topic_hit"):
        _not_shown(run, run.out1.get("_row"))
    if _gave_advice(rc, out) or (g or {}).get("topic_hit"):
        _not_shown(run, out.get("_row"))
        r["debrief"], r["message"] = None, WITHHELD
        run.detail("VERIFY", WITHHELD)
    else:
        named = _named_sentences(rc["defects"]) | _named_sentences(out.get("defects"))
        if not named:
            r["debrief"] = {**shown, "flagged": flagged}
        else:
            base = {**shown, "verdict_sentence": _code_verdict(run)} if 1 in named else shown   # the verdict is replaced
            kept = _without(base, named - {1})
            rk = verify.verify_numbers(kept, r["facts"], as_of=r["as_of"], result=r, catalog=catalog)
            gone = [d for d in [*rc["defects"], *(str(x) for x in out.get("defects") or [])]
                    if _NAMED.match(d) and int(_NAMED.match(d).group(1)) in named]
            if len(kept["sentences"]) >= 2 and not rk["defects"]:
                r["debrief"] = {**kept, "flagged": bool(_guard_lines(g)), "dropped": sorted(named - {1}),
                                "code_verdict": 1 in named}
                r["receipt"] = {**rk, "first_try": r["receipt"]["first_try"], "drafts": drafts, "dropped": gone}
                run.detail("VERIFY", DROPPED_DETAIL.format(n=len(named), s="" if len(named) == 1 else "s"))
            else:
                r["debrief"], r["message"] = None, CODE_SHOWN
                r["receipt"] = {**r["receipt"], "dropped": gone, "shown": False}
                run.detail("VERIFY", CODE_SHOWN)
    rc = r["receipt"]
    run.detail("VERIFY", f"{rc['verified']} of {rc['total']} numbers traced to data")
    shown_scored = _scored(g) and r["debrief"] is not None            # board resolution 5: last, on what is shown
    run.labels["VERIFY"] = GROUNDED_LABEL if shown_scored else STEP_LABELS["VERIFY"]


# ---- recheck: new limits on a stored run, no model call and no series recompute (plan D Task 7) ----
_RUN_ENGINES = OrderedDict()        # run_id -> the engine that computed it, the last RUN_ENGINES_MAX runs (recheck)
RUN_ENGINES_MAX = 64


def _rejudge_deep(result, limits2):
    """Ledger 17: the deep-history fragment judged again for the new floor, when the run has one (else None)."""
    fragment = result.get("deep_history")
    if not fragment or not limits2:
        return None
    try:
        return importlib.import_module("tools.deep").rejudge(fragment, limits2["floor"])
    except Exception as exc:                          # not built yet, or a fragment it cannot read: no deep row
        _crash_note("tools.deep.rejudge", exc)
        return None


def _with_label_shown(part, events):
    """A saved run's analysis kept no scenario_label_shown before Sun 17:15 (limits-QA): the shock check's evidence is
    named again by title and date (governance.label_shown), never by an event id, so a recheck says what the run said."""
    if not isinstance(part, dict) or part.get("scenario_label_shown") or not part.get("scenario_label"):
        return part
    try:
        shown = importlib.import_module("governance").label_shown(part["scenario_label"], events)
    except Exception as exc:                          # the id stays: the page's readReason names it by its title
        _crash_note("governance.label_shown", exc)
        return part
    return {**part, "scenario_label_shown": shown}


def _daily(dates) -> bool:
    """True when the dates are trading days (the median gap is at most 3 calendar days), not a weekly cut of them."""
    try:
        days = sorted({datetime.fromisoformat(str(d)[:10]).date() for d in dates})
    except ValueError:
        return False
    gaps = sorted((b - a).days for a, b in zip(days, days[1:]))
    return bool(gaps) and gaps[len(gaps) // 2] <= 3


def _recheck_capacity(r, limits):
    """R35 (the controller, 17:41): a capacity typed in the editor ("The most you could lose") moves the capacity line, never
    the 15 % rule: lane fin-backend's result_extras.capacity on the run's own stored paths with the dollars typed. None
    when no capacity was typed, or it is not above $0 and below the amount (the page then draws no line)."""
    cap = limits.get("capacity") if isinstance(limits, dict) else None
    if not isinstance(cap, numbers.Real) or isinstance(cap, bool) or not math.isfinite(cap):
        return None
    if not _daily(((r.get("series") or {}).get("dates")) or []):      # limits-QA 18:05: a saved run keeps weekly paths, and
        return None                                                    # weeks are not sessions: no line rather than a wrong count
    try:
        extras = importlib.import_module("result_extras")
        moved = {**r, "profile": {**(r.get("profile") or {}), "capacity": float(cap)}}
        return extras.capacity(moved, extras.inputs(moved))
    except Exception as exc:                          # an extra: the checks still answer
        _crash_note("result_extras.capacity", exc)
        return None


def recheck(result, limits, *, engine=None) -> dict:
    """{checks, verdict, kpis, sensitivity, baseline: {checks, verdict} | None, deep_history} for the stored run judged
    with new limits: `load_limits` -> `check_profile` on the private `_analysis` (after, and today when the run has a
    move) -> `verdict`; the stored KPI values with the new limits; `sensitivity`. The stored Result is not changed. No
    answers (or no analysis) -> no checks and no verdict."""
    r = result if isinstance(result, dict) else {}
    kpis = {k: dict(v) if isinstance(v, dict) else v for k, v in (r.get("kpis") or {}).items()}
    raw, analysis = r.get("profile"), r.get("_analysis") if isinstance(r.get("_analysis"), dict) else {}
    profile = {k: raw[k] for k in PROFILE_KEYS if k in raw} if isinstance(raw, dict) else None
    out = {"checks": [], "verdict": None, "kpis": kpis, "sensitivity": None, "baseline": None, "deep_history": None,
           "capacity": _recheck_capacity(r, limits)}
    if profile is None or not isinstance(analysis.get("after"), dict):
        return out
    e = engine or _RUN_ENGINES.get(r.get("run_id")) or real_engine()
    limits2 = e.load_limits(profile, limits or None, amount=r.get("amount"))

    def judge(portfolio, part):
        part = _with_label_shown(part, r.get("events"))
        checks = e.check_profile(profile, dict(portfolio or {}), {**part, "limits": limits2})
        return _annotate_checks(_shock_counts(checks, part), limits2, profile), e.verdict(checks)

    out["checks"], out["verdict"] = judge(r.get("portfolio"), analysis["after"])
    for key, name in (("max_drawdown", "floor"), ("scenario_stress", "scenario_stress"), ("recovery_days", "recovery_days")):
        if isinstance(kpis.get(key), dict):
            kpis[key]["limit"] = (limits2 or {}).get(name)
    try:
        out["sensitivity"] = e.sensitivity(profile, dict(r.get("portfolio") or {}), analysis["after"], limits=limits2)
    except Exception as exc:                          # the flip point is an extra: the checklist still answers
        _crash_note("tools.allocation.sensitivity", exc)
    if isinstance(analysis.get("today"), dict):
        checks, verdict_today = judge((r.get("baseline") or {}).get("portfolio") or r.get("portfolio"), analysis["today"])
        out["baseline"] = {"checks": checks, "verdict": verdict_today}
    out["deep_history"] = _rejudge_deep(r, limits2)
    return out


# ---- recompute one number (spec 8 "living numbers", ledger 9: POST /api/recompute {run_id, id}) ----
RECOMPUTE_UNKNOWN = "This run has no number {id}."
RECOMPUTE_NO_RECIPE = "Number {id} has no recorded recipe, so it cannot be recomputed."
RECOMPUTE_FAILED = ("The tools could not recompute number {id} on this machine; the data it was computed on may "
                    "be missing.")
_RECIPE_WORDS = {
    "flight_plan": "Read back from your inputs: no tool computes this number.",
    "limits": "Recomputed by governance.load_limits from your answers and the limits table.",
    "evaluate.today": "Recomputed by governance.evaluate on today's mix, on the data up to {as_of}.",
    "evaluate.after": "Recomputed by governance.evaluate on the mix after the move, on the data up to {as_of}.",
    "tipping_point": "Recomputed by tools.allocation.tipping_point (governance.evaluate at each size), on the data up "
                     "to {as_of}.",
    "attribution": "Recomputed by tools.events.drawdown_attribution on the mix's path and the shocks known at {as_of}.",
}


def _spec_key(path, recipe, formula) -> tuple:
    path, key = path if isinstance(path, tuple) else (path, None)
    return path, key, recipe, formula


def _recompute_inputs(r) -> dict:
    """What the COMPARE step was given, read back from the stored Result: the typed answers, the edited limits (the
    whole limits dict goes back in: load_limits keeps only its `edited` keys), the two mixes and the families."""
    sc = r.get("scenario") or {}
    raw = r.get("profile")
    profile = {k: raw[k] for k in PROFILE_KEYS if k in raw} if isinstance(raw, dict) else None
    families = [] if _abstains(sc) else list(sc.get("families") or FAMILIES)
    has_change = isinstance(_dig(r, "metrics", "after"), dict)
    after = dict(r.get("portfolio") or {})
    today = dict((r.get("baseline") or {}).get("portfolio") or after) if has_change else after
    return {"profile": profile, "limits": r.get("limits"), "families": families, "has_change": has_change,
            "today": today, "after": after, "amount": r.get("amount"), "as_of": r.get("as_of")}


def _reevaluate(e, inp, side) -> dict:
    """The judge of `_compare` on one side, with the same arguments (today on all four families in their own order
    when the question names all four, as OBSERVE judged it)."""
    families = inp["families"]
    if side == "today" and set(families) == set(FAMILIES):
        families = list(FAMILIES)
    ev = e.evaluate(inp["profile"], inp[side], families, inp["as_of"], limits=inp["limits"], amount=inp["amount"])
    if not isinstance(ev, dict) or ev.get("error"):
        raise _Plain((ev or {}).get("error") or "The checklist could not be computed.")
    return ev


def _recomputed(r, e, recipe, path) -> dict:
    """A copy of the Result whose keys behind `recipe` are computed again, the way the run computed them."""
    inp, mini = _recompute_inputs(r), dict(r)
    side = "after" if inp["has_change"] else "today"
    if recipe == "limits" and path in ("limits.floor", "limits.scenario_stress"):
        limits = e.load_limits(inp["profile"], inp["limits"], amount=inp["amount"]) if inp["profile"] else None
        mini["limits"] = None if limits is None else {
            **limits, "appetite_floor": limits.get("band_floor"), "capacity_dollars": inp["profile"].get("capacity")}
        return mini
    if recipe in ("evaluate.today", "evaluate.after", "limits", "attribution"):
        which = side if recipe in ("limits", "attribution") else recipe.split(".", 1)[1]
        ev = _reevaluate(e, inp, which)
        for key in ("metrics", "worst_rolling", "risk"):
            mini[key] = {**(r.get(key) or {}), which: ev.get(key)}
        mini["turbulence"] = _merge_turbulence(ev if which == "today" else None, ev if which == "after" else None)
        if which == side:
            mini["checks"] = _annotate_checks(_shock_counts(ev.get("checks"), ev.get("analysis")), ev.get("limits"),
                                              inp["profile"])
        if recipe == "attribution":
            catalog = e.load_events(inp["as_of"])
            mini["attribution"] = e.drawdown_attribution(ev["series"], catalog, inp["as_of"], metrics=ev.get("metrics"))
        return mini
    if recipe == "tipping_point":
        change = (r.get("scenario") or {}).get("change") or {}
        ticker = change.get("ticker")
        asked = change.get("weight") if change.get("op") == "set" else inp["after"].get(ticker)
        tp = e.tipping_point(inp["profile"], inp["today"], ticker, (r.get("scenario") or {}).get("event_ids") or [],
                             inp["as_of"], families=inp["families"], limits=inp["limits"], amount=inp["amount"],
                             max_weight=asked)
        if not isinstance(tp, dict) or tp.get("error"):
            raise _Plain((tp or {}).get("error") or "The size curve could not be computed.")
        mini["tipping_point"] = {**tp, "curve": [dict(p) for p in tp.get("curve") or [] if isinstance(p, dict)]}
        return mini
    return mini                                         # flight_plan: the inputs themselves, read back


def recompute(result, tid, *, engine=None) -> dict:
    """One number of a run computed again from the run's own inputs, by the same tool and the same code path
    (`_fact_specs` / `_check_specs` read the value out of the recomputed keys), and compared with the stored value.

    {id, label, unit, kind, stored, value, same, text, recipe, tool, path, formula, source, as_of, how, ms}: `value`
    is the recomputed number, `same` whether it equals the stored one (to 1e-9 relative), `text` the value written
    the way the debrief writes it, `how` one plain sentence. A number entered by the investor is read back, not
    computed. An unknown id or a row with no recipe: {"error", "reason": "unknown"}; tools or data missing on this
    machine: {"error", "reason": "unavailable"}. The stored Result is not changed and no model is called."""
    r = result if isinstance(result, dict) else {}
    tid = str(tid or "")
    fact = (r.get("facts") or {}).get(tid)
    row = next((t for t in r.get("trace") or [] if isinstance(t, dict) and t.get("id") == tid), None)
    if not isinstance(fact, dict) or row is None:
        return {"error": RECOMPUTE_UNKNOWN.format(id=tid or "?"), "reason": "unknown"}
    inputs = row.get("inputs") or {}
    recipe, path, key, formula = inputs.get("recipe"), inputs.get("path"), inputs.get("key"), inputs.get("formula")
    if recipe not in _RECIPE_WORDS or not path:
        return {"error": RECOMPUTE_NO_RECIPE.format(id=tid), "reason": "unknown"}
    t0 = time.perf_counter()
    try:
        e = engine or _RUN_ENGINES.get(r.get("run_id")) or (None if recipe == "flight_plan" else real_engine())
        mini = _recomputed(r, e, recipe, path)
        want = (path, key, recipe, formula)
        found = [s for s in (*_fact_specs(mini), *_check_specs(mini)) if _spec_key(s[7], s[8], s[10]) == want]
    except Exception as exc:                            # EngineUnavailable, _Plain or a tool's failure: one sentence
        _crash_note("recompute", exc)
        return {"error": RECOMPUTE_FAILED.format(id=tid), "reason": "unavailable"}
    value, stored = (_clean(found[0][1]) if found else None), _clean(fact.get("value"))
    same = value is not None and stored is not None and math.isclose(value, stored, rel_tol=1e-9, abs_tol=1e-12)
    unit = fact.get("unit")
    return {"id": tid, "label": fact.get("label"), "unit": unit, "kind": fact.get("kind"), "stored": stored,
            "value": value, "same": same, "text": None if value is None else verify.fmt_number(value, unit),
            "recipe": recipe, "tool": row.get("tool"), "path": f"{path}[{key}]" if key else path,
            "formula": formula, "source": row.get("source"), "as_of": r.get("as_of"),
            "how": _RECIPE_WORDS[recipe].format(as_of=r.get("as_of")), "ms": _ms(t0)}


# ---- JSON for the browser and for saved runs ----
def _json_key(key):
    return key.item() if isinstance(key, np.generic) else key


def jsonable(obj, _top=True):
    """Plain JSON types, recursively and into new containers (`obj` is never changed): numpy scalars become Python
    numbers, arrays and tuples lists, NaN and infinity None. Keys starting with `_` are server-side only: they are
    dropped from the top-level dict, and only there."""
    if isinstance(obj, dict):
        return {_json_key(k): jsonable(v, False) for k, v in obj.items()
                if not (_top and isinstance(k, str) and k.startswith("_"))}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v, False) for v in obj]
    if isinstance(obj, np.ndarray):
        return jsonable(obj.tolist(), False)
    if isinstance(obj, np.generic):
        return jsonable(obj.item(), False)
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


# ---- saved runs: recorded once on a live machine, replayed for exactly the same inputs ----
def _norm_question(question) -> str:
    """A question as the run key and the save guard compare it: lower case, one space between words."""
    return " ".join(str(question or "").lower().split())


def _canonical(value):
    """The same JSON for the same numbers: 600000 and 600000.0 are one amount (the API turns integers into floats)."""
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_canonical(v) for v in value]
    return int(value) if isinstance(value, float) and value.is_integer() else value


def run_key(flight_plan, question, as_of=DATASET_END, redteam=False) -> str:
    """16 hex characters naming one run: the same weights (any order), amount, answers, limits, question (any case or
    spacing), date and red-team flag are the same run. The pilot's name is not an input."""
    plan = flight_plan or {}
    profile = plan.get("profile")
    if isinstance(profile, dict):
        profile = {k: v for k, v in profile.items() if v is not None}      # an answer left out and one left null agree
    inputs = {"portfolio": {t: round(float(w), 6) for t, w in (plan.get("portfolio") or {}).items()},
              "amount": plan.get("amount"), "profile": profile or None, "limits": plan.get("limits") or None,
              "question": _norm_question(question), "as_of": as_of, "redteam": bool(redteam)}
    text = json.dumps(_canonical(jsonable(inputs)), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


COMMIT_ENV = "EPICENTRE_COMMIT"           # the commit, for a copy with no .git (the Docker image: docker run -e)
COMMIT_FILE = REPO_ROOT / ".commit"       # "$Format:%H$" in git; `git archive` (GitHub's ZIP download) writes the hash
_FULL_HASH = re.compile(r"[0-9a-f]{40}")


def _git_head():
    """HEAD of the git repository whose top folder is REPO_ROOT, or None (no git, no repository, or a repository
    around an unpacked ZIP, whose HEAD is some other code)."""
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel", "HEAD"], cwd=REPO_ROOT, capture_output=True,
                             text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    lines = out.stdout.split()
    if out.returncode != 0 or len(lines) != 2 or not _FULL_HASH.fullmatch(lines[1]):
        return None
    try:
        same = Path(lines[0]).resolve() == REPO_ROOT.resolve()
    except OSError:
        return None
    return lines[1] if same else None


def _commit() -> str:
    """The commit this code is at: git HEAD when REPO_ROOT is a git checkout; else `EPICENTRE_COMMIT` from the
    environment; else the hash `git archive` wrote into `.commit` (a ZIP download from GitHub, `.gitattributes`
    export-subst); else "unknown". Only a full 40-character hash counts."""
    head = _git_head()
    if head:
        return head
    env = os.environ.get(COMMIT_ENV, "").strip().lower()
    if _FULL_HASH.fullmatch(env):
        return env
    try:
        text = COMMIT_FILE.read_text(encoding="utf-8").strip().lower()
    except (OSError, UnicodeDecodeError):
        text = ""
    return text if _FULL_HASH.fullmatch(text) else "unknown"


def _sources(obj):
    """Every string under a `source` key, anywhere in the Result."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "source" and isinstance(value, str):
                yield value
            else:
                yield from _sources(value)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            yield from _sources(value)


def _data_dir() -> Path:
    """The data pack the tools read: tools.data.DATA_DIR once that module is loaded (it honours EPICENTRE_DATA_DIR),
    else the same rule from the environment."""
    module = sys.modules.get("tools.data")
    loaded = getattr(module, "DATA_DIR", None) if module is not None else None
    return Path(loaded or os.environ.get(DATA_DIR_ENV) or REAL_DATA_DIR).expanduser().resolve()


def _data_label(result) -> str:
    """What a saved run was computed on, failing closed. "FAKE" when a source in the Result says FAKE or the pack in use
    is data/fake (the real tools read the synthetic pack and still describe it as the starter pack). "REAL" only on
    positive evidence: the real starter folder with its prices file, and sources that say where the numbers came from.
    Anything else is "UNKNOWN", which build_static refuses."""
    sources = [source for source in _sources(result) if source.strip()]
    folder, fake, real = Path(_data_dir()).resolve(), Path(FAKE_DATA_DIR).resolve(), Path(REAL_DATA_DIR).resolve()
    if any(source.startswith("FAKE") for source in sources) or folder == fake or fake in folder.parents:
        return "FAKE"
    return "REAL" if folder == real and (folder / "prices_daily.csv").is_file() and sources else "UNKNOWN"


def _held_tickers(result: dict, flight_plan) -> set:
    """The investor's own lines: the plan, the evaluated mix, today's mix and the illustration mix of the Result."""
    held = set((flight_plan or {}).get("portfolio") or {}) if isinstance(flight_plan, dict) else set()
    for lines in (result.get("portfolio"), (result.get("baseline") or {}).get("portfolio"),
                  (result.get("aligned") or {}).get("weights")):
        held |= set(lines) if isinstance(lines, dict) else set()
    return held


def _cut_lookthrough(look, held: set, hidden: set) -> None:
    """In place, on a copy made by `jsonable`. Red gate 8: no company inside the investor's funds is ever named. The
    look-through keeps the investor's own lines (without their per-ETF `via` lists); the largest share among the others
    becomes `top_company_share`, a share with no name; `esg_indirect` merges them into one unnamed entry. Sectors,
    countries and the other aggregates stay. The names that were cut go into `hidden`."""
    if not isinstance(look, dict):
        return
    stocks = look.get("stocks")
    if isinstance(stocks, dict):
        gone = {t: e for t, e in stocks.items() if t not in held}
        look["stocks"] = {t: {k: v for k, v in e.items() if k != "via"} for t, e in stocks.items()
                          if t in held and isinstance(e, dict)}
        hidden.update(gone)
        shares = [e["total"] for e in gone.values() if isinstance(e, dict) and isinstance(e.get("total"), (int, float))]
        if shares:
            look["top_company_share"] = max(shares)
    inside = look.get("esg_indirect")
    if isinstance(inside, dict) and any(t not in held for t in inside):
        gone = {t: v for t, v in inside.items() if t not in held}
        hidden.update(gone)
        look["esg_indirect"] = {**{t: v for t, v in inside.items() if t in held},
                                ANOTHER_COMPANY: sum(v for v in gone.values() if isinstance(v, (int, float)))}


def _anonymise(obj, hidden: set):
    """Into new containers: no `via` key anywhere and no key that names a company that was cut. Texts are not touched
    here: a sentence of the debrief is what the receipt verified, and a short ticker ("A", "T") is also a word."""
    if isinstance(obj, dict):
        return {k: _anonymise(v, hidden) for k, v in obj.items() if k != "via" and k not in hidden}
    if isinstance(obj, list):
        return [_anonymise(v, hidden) for v in obj]
    return obj


def _unnamed(text, name):
    """A check's own reason with the one company it names replaced by "another company"."""
    if not isinstance(text, str):
        return text
    return re.sub(r"(?<![\w.-])" + re.escape(name) + r"(?![\w-])", ANOTHER_COMPANY.lower(), text)


def _publishable(result: dict, flight_plan=None) -> dict:
    """The Result as it may be committed and published (red gate 8): plain JSON without the server-side keys, without
    `via` anywhere, without the evidence rows of the trace, and without any company inside the investor's funds
    (see `_cut_lookthrough`; the same goes for `events[].exposed[]` and for a check's `holding`, whose reason then says
    "another company")."""
    saved, hidden, held = jsonable(result), set(), _held_tickers(result, flight_plan)
    saved.pop("funds_private", None)                    # live only (server._with_funds): the issuers' companies, never saved
    for side in ("today", "after"):
        _cut_lookthrough((saved.get("lookthrough") or {}).get(side), held, hidden)
    for event in saved.get("events") if isinstance(saved.get("events"), list) else []:
        exposed = event.get("exposed") if isinstance(event, dict) else None
        if isinstance(exposed, list):
            hidden.update(x["ticker"] for x in exposed if isinstance(x, dict) and x.get("ticker") not in held and x.get("ticker"))
            event["exposed"] = [x for x in exposed if isinstance(x, dict) and x.get("ticker") in held]
    for checks in (saved.get("checks"), (saved.get("baseline") or {}).get("checks")):
        for check in checks if isinstance(checks, list) else []:
            if isinstance(check, dict) and check.get("holding") and check["holding"] not in held:
                hidden.add(check["holding"])
                check["reason"] = _unnamed(check.get("reason"), check["holding"])
                check["holding"] = None
    for row in saved.get("trace") if isinstance(saved.get("trace"), list) else []:
        if isinstance(row, dict):
            if "rows" in row:
                row["rows"] = None                      # the evidence rows are per-asset data: the public demo gets none
    return _anonymise(saved, hidden)


def _saved_analysis(analysis, held: set) -> dict | None:
    """The private `_analysis` as a saved run keeps it: per side ("after", "today") only the ANALYSIS_KEYS, the
    look-through cut like the Result's, the universe and the values-screen names cut to the investor's own lines,
    `esg_flags` as a sorted list. None when the Result has no `_analysis`."""
    if not isinstance(analysis, dict):
        return None
    out = {}
    for side in ("after", "today"):
        part = analysis.get(side)
        kept = {k: part[k] for k in ANALYSIS_KEYS if k in part} if isinstance(part, dict) else None
        if kept is not None:
            kept["esg_flags"] = sorted(t for t in kept.get("esg_flags") or () if t in held)
            if isinstance(kept.get("universe"), list):
                kept["universe"] = [row for row in kept["universe"] if isinstance(row, dict) and row.get("ticker") in held]
            kept, hidden = jsonable(kept), set()
            _cut_lookthrough(kept.get("lookthrough"), held, hidden)
            kept = _anonymise(kept, hidden)
        out[side] = kept
    return out if any(part is not None for part in out.values()) else None


def _restored_analysis(saved) -> dict:
    """The saved analysis as `check_profile` expects it again: `esg_flags` a set, and the unnamed largest company back
    among the look-through stocks (as ANOTHER_COMPANY) so the single-company rule still sees its share. Raises
    ValueError when the saved analysis is not what `_saved_analysis` writes."""
    if not isinstance(saved, dict):
        raise ValueError("the saved analysis is not a dict")
    out = {}
    for side in ("after", "today"):
        part = saved.get(side)
        if part is None:
            out[side] = None
            continue
        flags = part.get("esg_flags", []) if isinstance(part, dict) else None
        if not isinstance(flags, (list, tuple)) or not all(isinstance(t, str) for t in flags):
            raise ValueError("the saved analysis has a bad side")
        part = {**part, "esg_flags": set(flags)}
        look = part.get("lookthrough")
        if look is not None:
            top = look.get("top_company_share") if isinstance(look, dict) else None
            stocks = look.get("stocks", {}) if isinstance(look, dict) else None
            if not isinstance(stocks, dict) or isinstance(top, bool) or not (top is None or isinstance(top, (int, float))):
                raise ValueError("the saved analysis has a bad look-through")
            part["lookthrough"] = {**look, "stocks": stocks if top is None else {
                **stocks, ANOTHER_COMPANY: {"direct": 0.0, "total": top}}}
        out[side] = part
    return out


def _really_happened(result) -> bool:
    """A live Result that reached Bedrock and was explained: the only kind that is saved, and the only kind replayed."""
    return (isinstance(result, dict) and result.get("mode") == "live" and result.get("status") == "ok"
            and result.get("debrief") is not None)


SCRIPTED_PATH = REPO_ROOT / "data" / "demo_scripted.json"   # the curated moves and "Test the AI" questions (Sun Nov 15)


def demo_questions() -> set:
    """The scripted, fictional demo questions: each investor's own and each shock card's (data/personas.json), and the
    curated moves and "Test the AI" questions (data/demo_scripted.json), written like the run key writes a question.
    Empty when the files are missing or unreadable."""
    out = set()
    try:
        scripted = json.loads(Path(SCRIPTED_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        scripted = {}
    for section in ("moves", "tests") if isinstance(scripted, dict) else ():
        for item in scripted.get(section) or []:
            question = item.get("question") if isinstance(item, dict) else None
            if isinstance(question, str) and question.strip():
                out.add(_norm_question(question))
    try:
        data = json.loads(Path(PERSONAS_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    for section in ("pilots", "storm_cards") if isinstance(data, dict) else ():
        cards = data.get(section)
        for card in cards.values() if isinstance(cards, dict) else ():
            question = card.get("question") if isinstance(card, dict) else None
            if isinstance(question, str) and question.strip():
                out.add(_norm_question(question))
    return out


def save_run(result, flight_plan, question, as_of=DATASET_END, redteam=False) -> Path | None:
    """Write `DEMO_DIR/<run_key>.json` = {key, saved_at, question, as_of, commit, data, result[, analysis]} for a run that
    really reached Bedrock and was asked one of the scripted demo questions (red gate 6: a saved file carries the
    question, so a typed one is never written); any other run returns None. `commit` is the code's git HEAD and `data`
    says FAKE, REAL or UNKNOWN. The Result is saved without constituents (`_publishable`). `analysis` is the Result's
    private `_analysis`, cut to its summaries (ANALYSIS_KEYS), so that a recheck works on the replay; it is stored
    without the leading underscore. Only scripts/record_demo.py calls this: the server never writes inputs (spec 6)."""
    if not _really_happened(result) or (result.get("redteam") is not None) != bool(redteam):
        return None                                         # a red-team Result is only ever saved under its own key
    asked = _norm_question(question)
    if asked != _norm_question(result.get("question")) or asked not in demo_questions():
        return None
    key = run_key(flight_plan, question, as_of, redteam)
    shown = _publishable(result, flight_plan)
    saved = {"key": key, "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "question": question,
             "as_of": as_of, "commit": _commit(), "data": _data_label(shown), "result": shown}
    analysis = _saved_analysis(result.get("_analysis"), _held_tickers(result, flight_plan))
    if analysis is not None:
        saved["analysis"] = analysis
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    path = DEMO_DIR / f"{key}.json"
    path.write_text(json.dumps(saved, allow_nan=False, separators=(",", ":")), encoding="utf-8")
    return path


def _read_saved(path: Path, *, key=None, as_of=None, pilot=None) -> dict | None:
    """The saved file when it is whole, holds a real live run, and belongs to what was asked: its own key and date for
    a lookup by inputs, its investor for a default file. None when it is missing, half-written, edited, mis-copied, or
    its analysis cannot be restored. The restored analysis is added as `_analysis`."""
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        datetime.fromisoformat(saved["saved_at"])
        name, result, analysis = saved["key"], saved["result"], saved.get("analysis")
        saved["_analysis"] = None if analysis is None else _restored_analysis(analysis)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None
    if not _really_happened(result) or not (isinstance(name, str) and re.fullmatch(r"[0-9a-f]{16}", name)):
        return None
    if (key is not None and name != key) or (as_of is not None and saved.get("as_of") != as_of):
        return None
    return None if pilot is not None and result.get("pilot") != pilot else saved


def _as_replay(saved: dict, template: str) -> dict:
    """The saved Result as a replay: a stable run_id (the first 12 characters of its key, so a page load does not push
    other runs out of the server's store), `mode "demo_replay"`, the one sentence saying where it came from, and the
    private `_analysis` back (so `recheck` works). `saved` was just read from disk: every caller gets its own copy."""
    when = datetime.fromisoformat(saved["saved_at"])
    result = saved["result"]
    result.update(run_id=saved["key"][:12], mode="demo_replay", message=template.format(date=when.strftime("%d %b %Y")))
    if saved["_analysis"] is not None:
        result["_analysis"] = saved["_analysis"]
    return result


def load_saved_run(flight_plan, question, as_of=DATASET_END, redteam=False, *, reason="bedrock") -> dict | None:
    """The saved run for exactly these inputs as a replay (`reason` "bedrock" or "demo" picks the sentence), else None."""
    template = REPLAY_MESSAGES[reason]                      # an unknown reason is a bug, not a missing run
    try:
        key = run_key(flight_plan, question, as_of, redteam)
    except (AttributeError, TypeError, ValueError):         # a plan that cannot be keyed has no saved run
        return None
    saved = _read_saved(DEMO_DIR / f"{key}.json", key=key, as_of=as_of)
    return None if saved is None else _as_replay(saved, template)


def default_demo_run(pilot: str = DEFAULT_PILOT) -> dict | None:
    """An investor's saved run for the page (GET /api/demo-run?pilot=<id>): a copy of that investor's saved file that
    scripts/record_demo.py writes, `default.json` for Robert (the page's first paint) and `default_<id>.json` for the
    others, and the Result's `pilot` must be that investor. None for an unknown id, an id that is not a plain name, a
    file that belongs to someone else, or until the file exists."""
    if not isinstance(pilot, str) or not PILOT_RX.fullmatch(pilot):
        return None
    saved = _read_saved(DEMO_DIR / ("default.json" if pilot == DEFAULT_PILOT else f"default_{pilot}.json"), pilot=pilot)
    return None if saved is None else _as_replay(saved, REPLAY_MESSAGES["demo"])


def _replay_progress(progress, flight_plan, question, as_of):
    """One `done` line per step for a replay. Nothing ran, so each step says Python and "saved run"."""
    lines = _Run(_new_result(flight_plan, question, as_of), None, progress, False, flight_plan)
    lines.service = dict.fromkeys(STEPS, "Python")
    for step in STEPS:
        lines.emit(step, "done", ms=0, detail="saved run")


# ---- the run ----
def _stop_early(result, message, progress, flight_plan) -> dict:
    """A run that cannot start: the Result carries the one plain sentence and a single OBSERVE error line. Nothing ran,
    so the service is Python."""
    result.update(status="error", message=message)
    _Run(result, None, progress, False, flight_plan).emit("OBSERVE", "error", detail=message)
    return result


def run(flight_plan, question, as_of=DATASET_END, *, progress=None, use_bedrock=True, redteam=False,
        engine=None) -> dict:
    """OBSERVE -> UNDERSTAND -> COMPARE -> EXPLAIN -> VERIFY; returns the Result of spec 12 and never raises.
    `progress(event)` is called per step (a listener that raises is ignored). `redteam` is read by Task 7.
    With EPICENTRE_DEMO=1 the saved run for exactly these inputs comes back as a replay (one `done` line per step, no
    engine touched); with none, the run is computed with Bedrock off and `message` says so."""
    flight_plan = flight_plan or {}
    if not isinstance(flight_plan, dict):
        return _stop_early(_new_result({}, question, as_of), NOT_A_PLAN, progress, {})
    demo = os.environ.get(DEMO_ENV) == "1"
    if demo:
        saved = load_saved_run(flight_plan, question, as_of, redteam, reason="demo")
        if saved is not None:
            _replay_progress(progress, flight_plan, question, as_of)
            return saved
        use_bedrock = False
    result = _new_result(flight_plan, question, as_of)
    try:
        engine = engine if engine is not None else real_engine()
    except EngineUnavailable as exc:
        return _stop_early(result, str(exc), progress, flight_plan)
    except Exception as exc:
        _crash_note("loading the tools", exc)
        return _stop_early(result, TOOLS_DOWN, progress, flight_plan)
    state = _Run(result, engine, progress, use_bedrock, flight_plan)
    state.question, state.redteam = question, redteam
    _RUN_ENGINES[result["run_id"]] = engine              # recheck(result, limits) judges with the same engine
    while len(_RUN_ENGINES) > RUN_ENGINES_MAX:
        _RUN_ENGINES.popitem(last=False)

    def compare():      # lane B3 (Replay): COMPARE, then result_extras' keys inside the same step, with the real tools
        _compare(state)  # only (a test's fake engine has canned numbers); a failure there never stops the run
        cached = getattr(real_engine, "cache_info", None)
        if cached and cached().currsize and state.engine is real_engine():
            try:
                importlib.import_module("result_extras").extend(result, engine=state.engine)
                _ai_off_sentence(result)
            except Exception as exc:
                _crash_note("result_extras.extend", exc)

    steps = {"OBSERVE": lambda: _observe(state, flight_plan, question), "UNDERSTAND": lambda: _understand(state, question),
             "COMPARE": compare, "EXPLAIN": lambda: _explain(state), "VERIFY": lambda: _verify(state)}
    for step in STEPS:
        if state.replay is not None:                        # the saved run of these inputs answers: nothing else runs
            state.service[step] = "Python"
            state.emit(step, "done", ms=0, detail="saved run")
            continue
        skip = STOPPED.get(state.stopped) or (state.no_model if step in ("EXPLAIN", "VERIFY") else None)
        if not skip and _now() > state.deadline:            # ledger 15: no step starts after the run's deadline
            _past_deadline(state, step)
            break
        if not _step(state, step, steps[step], skip):
            break
    if state.replay is not None:
        return state.replay
    if state.cut and result["message"] is None:             # a call the deadline stopped: the page says so in one line
        result["message"] = RUN_CUT
    if demo and result["message"] is None:                  # a real error sentence is never replaced
        result["message"] = DEMO_NO_SAVED_RUN
    return result
