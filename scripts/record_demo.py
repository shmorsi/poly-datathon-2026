"""Record the demo runs live, and build the static read-only demo (plan D Task 15).

    python scripts/record_demo.py [--pilots robert,mateo,amira,canadian] [--storms tariffs,war_oil,chips,rates]
                                  [--dry-run]                   # print the 20 planned runs, run nothing
    python scripts/record_demo.py --static OUT_DIR [--live URL]  # build the GitHub Pages site from the saved runs

Recording: for each investor, its own question, then each storm card's question on the same flight plan (4 x 5 = 20
runs), one after the other (the guardrail quota), live (`use_bedrock=True`). A run that did not reach Bedrock, or has no
explanation, is reported and never saved. Before saving, the month table and, once plan P has landed, the proofs are
computed, and the Result is cut to what may be published (below). Exit 0 only if every run was saved.

The static demo (`build_static`) copies web/ (never the FAKE sample data, the lanes' web/dev/ harness pages or the frozen classic
page), marks the page as the read-only demo and writes `runs/index.json`, `runs/default.json`, `runs/<key>.json` (each saved
real run as a replay) and `runs/<investor>.json` (each investor's own run, the one the Replay page's data.js reads). What it publishes
(ledger 10, 15, 21, 23, 29; red gate 8): portfolio-level derived series only, and those weekly and rounded. No per-asset
price series, no ETF holdings row, no ETF-constituent identifier (a company in a fund, also as a check's `holding`) unless
the company is itself a line of the portfolio, no evidence-drawer rows (the page says "not in the public demo: data
licence"), and no `figures` at all (ledger 30: plotly writes numpy as typed arrays, `bdata`, base64 that no cut can read and
that can hold a whole daily path; the page draws every chart from `series`, `breaches`, `events` and `tipping_point`; the
build refuses any `bdata` it finds). Why weekly and rounded: today vs after for an "add X" move isolates X's daily returns,
which would redistribute licensed prices. So every published series keeps every 5th trading day plus its exact worst-drop,
breach and end days, drawdowns are rounded to 0.1 pp and dollars to $100, and a run whose today or after mix is one line
(fewer than 2 lines, or one at 99.5 % or more) is refused. Every number the page quotes still comes from the Result. The
build refuses a saved run that is not REAL (the file says REAL, names a source, and no source names fake data: a function of
the file alone), a run it cannot label with a commit, and anything that still looks like a price table, a holdings row, a
daily series or a typed array after the cut. It never reads or writes credentials, data/starter/ or data/etf_holdings.csv.
Publishing is a separate step that needs the lead's yes.

The pipeline is called through the module (`pipeline.run(...)`), never `from pipeline import run`, so tests can
replace it; the hooks plan P adds (`pipeline.time_machine`, `pipeline.precompute_proofs`) are used when they exist.
"""
import argparse
import html
import json
import math
import numbers
import re
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # `python scripts/record_demo.py` puts scripts/, not the repo root, first
    sys.path.insert(0, str(ROOT))

import pipeline  # noqa: E402
import server  # noqa: E402

DEFAULT_PILOTS = ("robert", "mateo", "amira", "canadian")
DEFAULT_STORMS = ("tariffs", "war_oil", "chips", "rates")
KEY_FILE = re.compile(r"[0-9a-f]{16}\.json")        # a saved run's file name; default*.json and test_tally.json are not runs
COMMIT = re.compile(r"[0-9a-f]{40}")
LIVE_URL = re.compile(r"https://[^\s\"'<>]{1,300}")
SHORT_COMMIT = 7
# The public cut (ledger 29, red gate 8): today vs after for an "add X" move isolates X's daily returns, which would
# redistribute licensed prices. So a published series is weekly and rounded, and a side that is one line is refused.
WEEK = 5                    # a published series keeps every 5th trading day, plus its exact worst-drop, breach and end days
DOLLARS = 100               # dollars are published to the nearest $100
DRAWDOWN_DECIMALS = 3       # drawdowns (fractions) are published to 0.1 pp
ONE_LINE = 0.995            # a mix with one line at or above this share of the money is that asset's own path
ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?")      # plotly writes a Timestamp as 2022-03-01T00:00:00
SERIES_MIN = 20             # a list of this many numbers under a company's name is a price table; this many dates, a series
DRY_RUN = "dry run"
NO_EXPLANATION = "no explanation was written (Amazon Bedrock did not answer), so there is no run to keep"
NOT_BEDROCK = "Amazon Bedrock did not answer, so this is not a real live run"


class RecordError(Exception):
    """A plain sentence for the person at the terminal."""


class StaticBuildError(RecordError):
    """The static demo was refused; nothing was published and no output folder was left behind."""


class NotPublic(RecordError):
    """A run that cannot be published, and why (a plain sentence): the public cut refuses it."""


# ---- the plan ----
def _personas() -> dict:
    path = Path(getattr(pipeline, "PERSONAS_PATH", None) or server.PERSONAS_PATH)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise RecordError(f"{path.name} could not be read.") from None
    if not (isinstance(data, dict) and isinstance(data.get("pilots"), dict) and isinstance(data.get("storm_cards"), dict)):
        raise RecordError(f"{path.name} must hold `pilots` and `storm_cards`.")
    loader = getattr(pipeline, "load_pilots", None)       # D Task 6; the same `pilots` dict, checked
    pilots = (loader(path) if callable(loader) else None) or data["pilots"]
    return {"pilots": pilots, "storm_cards": data["storm_cards"]}


def plan_runs(pilots, storms) -> list:
    """[{"pilot", "flight_plan", "question", "own"}]: per investor its own question, then each storm card's question on the
    same flight plan. `own` marks the investor's own question (its saved run is the one `default*.json` copies)."""
    data = _personas()
    known, cards = data["pilots"], data["storm_cards"]
    bad = [p for p in pilots if p not in known or not pipeline.PILOT_RX.fullmatch(str(p))]
    if bad:
        raise RecordError(f"Unknown investor: {', '.join(map(str, bad))}. Known: {', '.join(known)}.")
    bad = [s for s in storms if s not in cards]
    if bad:
        raise RecordError(f"Unknown storm card: {', '.join(map(str, bad))}. Known: {', '.join(cards)}.")
    plan = []
    for pid in pilots:
        pilot = known[pid]
        for field in ("portfolio", "amount", "profile", "question"):
            if not pilot.get(field):
                raise RecordError(f"{pid} has no {field} in personas.json.")
        flight_plan = {"portfolio": pilot["portfolio"], "amount": pilot["amount"], "profile": pilot["profile"],
                       "limits": None, "pilot": pid}
        asked = [(pilot["question"], True)] + [(cards[s]["question"], False) for s in storms]
        for question, own in asked:
            plan.append({"pilot": pid, "flight_plan": json.loads(json.dumps(flight_plan)), "question": question, "own": own})
    return plan


# ---- what may be published ----
def _part(value, key):
    return value.get(key) if isinstance(value, dict) else None


def _lines(result: dict) -> set:
    """The tickers the investor holds: the mix after the move, today's mix and the illustration mix (the same set as
    `pipeline._held_tickers`, minus the flight plan, which a saved Result no longer carries)."""
    lines = set()
    for mix in (result.get("portfolio"), _part(result.get("baseline"), "portfolio"), _part(result.get("aligned"), "weights")):
        if isinstance(mix, dict):
            lines |= set(mix)
    return lines


def _cut_checks(checks, lines: set):
    """A check's `holding` is the largest company inside the investor's funds (governance.py), and its `reason` names it. Unless
    it is a line of the portfolio, `holding` becomes None and the reason says "another company": D Task 3's rule (6d7a54d),
    applied here again as a gate of its own (red gate 8). A new list; nothing passed in is changed."""
    if not isinstance(checks, list):
        return checks
    return [{**c, "reason": pipeline._unnamed(c.get("reason"), c["holding"]), "holding": None}
            if isinstance(c, dict) and c.get("holding") and c["holding"] not in lines else c for c in checks]


def _number(value) -> bool:
    return isinstance(value, numbers.Real) and not isinstance(value, bool)


def _one_line(mix, which: str) -> str | None:
    """Why a mix would publish one asset's own price path (fewer than 2 lines with a weight, or one line at 99.5 % or more of
    the money), else None. Such a mix has a value path that IS that asset's licensed price path (ledger 29, red gate 8)."""
    weights = {t: float(w) for t, w in mix.items() if _number(w) and w > 0} if isinstance(mix, dict) else {}
    if not weights:
        return f"The mix {which} has no line with a weight, so it cannot be checked and cannot be published."
    top = max(weights, key=weights.get)
    share = weights[top] / sum(weights.values())
    if len(weights) < 2 or share >= ONE_LINE:       # the ruling's two clauses (the first is the second's special case)
        return (f"The mix {which} is one line ({top}, {share:.1%}), so its value path would be that asset's own price path, "
                "which is licensed data: it cannot be published.")
    return None


def _check_sides(result: dict) -> None:
    """Raises NotPublic when a side of the Result is one line, or has no readable mix at all (see `_one_line`). It never looks
    at the series first: a series that is missing, short or not a plain list (an array at record time) is no proof that
    nothing is published, so it is never a reason to skip the check."""
    today = _part(result.get("baseline"), "portfolio")
    sides = [("after the move", result.get("portfolio")), ("today", today)] if isinstance(today, dict) else \
        [("today", result.get("portfolio"))]
    illustration = _part(result.get("aligned"), "weights")
    if isinstance(illustration, dict) and _part(result.get("series"), "aligned") is not None:
        sides.append(("of the illustration", illustration))
    for which, mix in sides:
        problem = _one_line(mix, which)
        if problem:
            raise NotPublic(problem)


def _is_company_map(d: dict) -> bool:
    """{ticker: {direct, via, total}}: the look-through's per-company entries, wherever a trace row or a tool call copied them."""
    return bool(d) and all(isinstance(v, dict) and {"direct", "total"} <= set(v) for v in d.values())


def _clean(value, lines: set, key=None):
    """A copy of `value` without `via` anywhere, with per-company look-through entries and the indirect ESG names kept only
    for portfolio lines, and the exposed rows of a shock kept only for portfolio lines (a row that comes through an ETF names
    one of its constituents, and constituent identifiers come from the issuer's holdings, red gate 8). Containers are rebuilt,
    leaves are shared, nothing passed in is changed."""
    if isinstance(value, dict):
        if key == "esg_indirect" or _is_company_map(value):
            value = {t: e for t, e in value.items() if t in lines}
        return {k: _clean(v, lines, k) for k, v in value.items() if k != "via"}
    if isinstance(value, list):
        if key == "exposed":
            rows, seen = [], set()
            for row in value:
                ident = (row.get("ticker"), row.get("channel")) if isinstance(row, dict) else None
                if ident is not None and ident[0] in lines and ident not in seen:
                    seen.add(ident)
                    rows.append(_clean(row, lines))
            return rows
        return [_clean(v, lines) for v in value]
    return value


# ---- the published series: weekly points, drawdowns to 0.1 pp, dollars to $100 (ledger 29) ----
VALUE_KEYS = ("y", "values", "today", "after", "aligned")      # the arrays of a dated group that hold a path's values


def _listy(value):
    """A numpy array or a tuple as a list (a live Result is not yet plain JSON); anything else as it is."""
    if isinstance(value, tuple):
        return list(value)
    return value.tolist() if hasattr(value, "tolist") and not isinstance(value, (list, dict, str)) else value


def _is_dates(value) -> bool:
    """A list of at least SERIES_MIN ISO dates: the calendar of a series."""
    return isinstance(value, list) and len(value) >= SERIES_MIN and all(isinstance(d, str) and ISO_DAY.fullmatch(d) for d in value)


def _is_weekly(dates: list) -> bool:
    """True when the dates are already weekly points: at most half of the gaps are shorter than four calendar days (a daily
    calendar has nearly all of them shorter; the exact worst-drop and breach days add a few). It makes the cut idempotent."""
    try:
        days = [date.fromisoformat(d[:10]) for d in dates]
    except ValueError:
        return True                                          # not a calendar: nothing to thin
    return sum((b - a).days < 4 for a, b in zip(days, days[1:])) * 2 <= len(days) - 1


def _dated(obj) -> set:
    """Every ISO date anywhere under `obj`, as the day (YYYY-MM-DD)."""
    if isinstance(obj, str):
        return {obj[:10]} if ISO_DAY.fullmatch(obj) else set()
    items = list(obj.values()) if isinstance(obj, dict) else obj if isinstance(obj, (list, tuple)) else []
    return set().union(*(_dated(v) for v in items)) if items else set()


def _worst_drop(values) -> set:
    """The indices of the peak and the trough of a path's worst drop: for a level path its lowest point against its running
    high; for a loss or drawdown path (it reaches 0 or below) its lowest point."""
    nums = [(i, float(v)) for i, v in enumerate(values) if _number(v) and math.isfinite(v)]
    if len(nums) < 2:
        return set()
    if min(v for _, v in nums) <= 0:
        return {min(nums, key=lambda p: p[1])[0]}
    found, worst, peak_i, peak = set(), 0.0, nums[0][0], nums[0][1]
    for i, v in nums:
        if v > peak:
            peak_i, peak = i, v
        if v / peak - 1 < worst:
            worst, found = v / peak - 1, {peak_i, i}
    return found


def _keep(dates: list, paths: list, must: set) -> list:
    """The indices a weekly series keeps: every 5th trading day, the last day, the days the Result names for its breaches, and
    the peak and trough of each path's worst drop (so the markers, the quoted drops and the end value stay on the line)."""
    n = len(dates)
    keep = set(range(0, n, WEEK)) | {n - 1} | {i for i, d in enumerate(dates) if str(d)[:10] in must}
    for values in paths:
        keep |= _worst_drop(values)
    return sorted(keep)


def _slice(obj, keep: list, n: int):
    """Every list of exactly n items (the dates and what is aligned with them) cut to the kept indices, into new containers."""
    if isinstance(obj, list):
        return [obj[i] for i in keep] if len(obj) == n else obj
    if isinstance(obj, dict):
        return {k: _slice(v, keep, n) for k, v in obj.items()}
    return obj


def _rounded(values: list, one) -> list:
    return [one(v) if _number(v) and math.isfinite(v) else v for v in values]


def _is_drawdown(values: list) -> bool:
    nums = [v for v in values if _number(v) and math.isfinite(v)]
    return bool(nums) and -1 <= min(nums) < 0 and max(nums) <= 0


def _round_dollars(values: list) -> list:
    return _rounded(values, lambda v: round(v / DOLLARS) * DOLLARS)


def _round_group(group: dict, path: tuple, amount) -> dict:
    """The value arrays of a dated group rounded: a drawdown (fractions from -1 to 0) to 0.1 pp, and the `series` arrays (index
    points, start = 100) to whole hundreds of the dollars they stand for (`amount` x index / 100). The size slider's dollar
    paths are rounded by `_dollar_path`; there are no charts (`figures` is dropped), and a level path of any other group has
    no known unit, so it is thinned but not rounded."""
    index = path == ("series",) and _number(amount) and amount > 0
    out = dict(group)
    for key in VALUE_KEYS:
        values = group.get(key)
        if not (isinstance(values, list) and values and all(v is None or _number(v) for v in values)):
            continue
        if _is_drawdown(values):
            out[key] = _rounded(values, lambda v: round(v, DRAWDOWN_DECIMALS))
        elif index:
            step = DOLLARS * 100 / amount
            out[key] = _rounded(values, lambda v: round(round(v / step) * step, 10))
    return out


def _dollar_path(row, shared, amount):
    """One dollar path of the size slider: while the main calendar is still daily (`shared` = its length and kept indices) it
    keeps the same days as `series`, or, if it is on another calendar, every 5th point, its last and its worst drop; then
    it is rounded to $100. An already-weekly set of paths (`shared` is None) is only rounded again."""
    if not isinstance(row, list):
        return row
    if shared and len(row) == shared[0]:
        row = _slice(row, shared[1], shared[0])
    elif shared and len(row) >= SERIES_MIN:
        row = [row[i] for i in _keep(list(range(len(row))), [row], set())]
    return _round_dollars(row) if _number(amount) and amount > 0 and all(v is None or _number(v) for v in row) else row


def _publish_series(result: dict) -> dict:
    """A copy of the Result with every dated series thinned to weekly points and rounded (see `_keep`, `_round_group`): the
    `series` arrays, the dollar paths of `tipping_point.paths` (the same days as `series`, so the slider's path and today's
    path line up), and any other group that pairs a list of dates with value arrays (a drawdown path). Already-weekly series
    are only rounded again, so the cut is idempotent. A nested `fallback_result` was cut by its own call. Quoted rows
    (`breaches`, `kpis`, `facts`, the size curve) are never touched. (`figures` never gets here: `public_result` drops it.)"""
    amount = result.get("amount")
    must = _dated(result.get("breaches")) | _dated(result.get("below_floor"))
    series = _part(result, "series")
    rows = _part(_part(result.get("tipping_point"), "paths"), "values")
    rows = [_listy(r) for r in _listy(rows)] if isinstance(_listy(rows), list) else []
    shared = None                        # (n, kept indices) of the main calendar, when it is still daily
    if isinstance(series, dict) and _is_dates(_listy(series.get("dates"))) and not _is_weekly(_listy(series["dates"])):
        n, found = len(series["dates"]), [_listy(series.get(k)) for k in ("today", "after", "aligned")]
        shared = (n, _keep(_listy(series["dates"]), [v for v in found if isinstance(v, list)]
                           + [r for r in rows if isinstance(r, list) and len(r) == n], must))

    def cut(node, path):
        node = _listy(node)
        if isinstance(node, list):
            return [cut(v, path) for v in node]
        if not isinstance(node, dict):
            return node
        if path == ("tipping_point", "paths") and isinstance(_listy(node.get("values")), list):
            own = _listy(node.get("dates"))
            if _is_dates(own) and _is_weekly(own):   # paths on their own weekly calendar (dates[258]): rounded, never thinned,
                node = {**node, "values": [_dollar_path(_listy(row), None, amount) for row in _listy(node["values"])]}   # so rows match dates
            else:
                node = {**node, "values": [_dollar_path(_listy(row), shared, amount) for row in _listy(node["values"])]}
        key = next((k for k, v in node.items() if _is_dates(_listy(v))), None)
        if key is not None:
            node, dates = {k: _listy(v) for k, v in node.items()}, _listy(node[key])
            if path == ("series",) and shared and shared[0] == len(dates):
                node = _slice(node, shared[1], len(dates))
            elif not _is_weekly(dates):
                node = _slice(node, _keep(dates, [node[k] for k in VALUE_KEYS if isinstance(node.get(k), list)], must), len(dates))
            node = _round_group(node, path, amount)
        return {k: v if (path == () and k == "fallback_result") else cut(v, path + (k,)) for k, v in node.items()}

    return cut(result, ())


def public_result(result: dict, *, nested: bool = False) -> dict:
    """The Result as it may be saved and published: ETF-constituent identifiers and `via` lists cut unless the company is a
    portfolio line (see `_clean`; the private `_analysis` is cut the same way), a check's `holding` that is such a company
    nulled with its reason saying "another company" (`_cut_checks`), and no evidence-drawer rows (`trace[].rows`).
    Aggregates (sectors, countries, currencies, coverage) stay. Every dated series is weekly and rounded (`_publish_series`),
    and a side that is one line, or has no readable mix, is refused: NotPublic (`_check_sides`). There is no `figures` at all
    (ledger 30): plotly writes numpy as typed arrays ({"dtype", "bdata"}), which would carry a daily path as base64 past any cut,
    and the ported page draws every chart from `series`, `breaches`, `events` and `tipping_point`. A new top-level dict; nothing
    passed in is changed; a nested `fallback_result` (plan P) follows the same rules with its own portfolio lines and loses its
    private `_` keys (only the top level of a saved Result may keep `_analysis`, and the saved file keeps it cut)."""
    _check_sides(result)
    lines = _lines(result)
    out = {}
    for key, value in result.items():
        if key == "figures" or (nested and isinstance(key, str) and key.startswith("_")):
            continue
        if key == "trace" and isinstance(value, list):
            value = [({**t, "rows": None} if isinstance(t, dict) and "rows" in t else t) for t in value]
            out[key] = _clean(value, lines)
        elif key == "fallback_result" and isinstance(value, dict):
            out[key] = public_result(value, nested=True)
        elif key == "_analysis" and isinstance(value, dict):
            out[key] = {side: ({**part, "lookthrough": _clean(part["lookthrough"], lines)}
                               if isinstance(part, dict) and "lookthrough" in part else part) for side, part in value.items()}
        elif isinstance(key, str) and key.startswith("_"):
            out[key] = value
        elif key == "checks":
            out[key] = _clean(_cut_checks(value, lines), lines, key)
        elif key == "baseline" and isinstance(value, dict) and "checks" in value:
            out[key] = _clean({**value, "checks": _cut_checks(value["checks"], lines)}, lines, key)
        else:
            out[key] = _clean(value, lines, key)
    return _publish_series(out)


FORBIDDEN_KEYS = ("via", "holdings", "per_asset", "adj_close", "prices", "_analysis", "funds_private")   # funds_private: live only


def _is_series(value) -> bool:
    return (isinstance(value, list) and len(value) >= SERIES_MIN
            and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in value))


def find_leaks(obj, path: str = "$") -> list:
    """What the public demo must never carry, found anywhere in plain JSON, as `"<path>: <what>"` strings:
    a per-asset price series (a list of numbers under a dataset ticker, or in a chart trace named after one), a holdings row
    (`etf` with `weight`), a key that only issuer data or the private analysis uses, a daily series (a calendar of 20 or more
    dates that is not weekly: the public cut keeps weekly points), or a typed array (any `bdata`: plotly writes numpy arrays as
    base64, which no cut can read; ledger 30). Portfolio-level series (`series`, the dollar paths) are not named after a
    company, and pass once they are weekly."""
    found = []
    if isinstance(obj, dict):
        tickers = set(server.UNIVERSE_TICKERS)
        for key in FORBIDDEN_KEYS:
            if key in obj:
                found.append(f"{path}.{key}: key that only issuer data or the private analysis uses")
        if {"etf", "weight"} <= set(obj):
            found.append(f"{path}: holdings row")
        if "bdata" in obj:
            found.append(f"{path}: typed array (bdata), base64 that can hide a whole daily path")
        for key, value in obj.items():
            if key in tickers and _is_series(value):
                found.append(f"{path}.{key}: per-asset price series")
            if _is_dates(value) and not _is_weekly(value):
                found.append(f"{path}.{key}: daily series (the public demo keeps weekly points)")
            found += find_leaks(value, f"{path}.{key}")
        if obj.get("name") in tickers or obj.get("ticker") in tickers:
            if any(_is_series(v) for v in obj.values()):
                found.append(f"{path}: per-asset price series")
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            found += find_leaks(value, f"{path}[{i}]")
    return found


# ---- recording ----
def _unfit(result) -> str | None:
    """Why a run is not a real live run with an explanation (the only kind that is kept), else None."""
    if not isinstance(result, dict):
        return "the run returned nothing"
    if result.get("status") != "ok":
        return result.get("message") or "the run did not finish"
    if result.get("mode") != "live":
        return NOT_BEDROCK
    if result.get("debrief") is None:
        return NO_EXPLANATION
    return None


def _prepare(result: dict) -> dict:
    """Fill what the static page cannot ask a server for: the month table, then (plan P) the proofs. Both are looked up on
    the module at call time and used only when they exist."""
    month_table = getattr(pipeline, "time_machine", None)
    if callable(month_table):
        table = month_table(result, None)
        if isinstance(table, dict) and table.get("months") is not None and not (result.get("time_machine") or {}).get("months"):
            result["time_machine"] = table
    proofs = getattr(pipeline, "precompute_proofs", None)
    if callable(proofs):
        done = proofs(result)
        if isinstance(done, dict):
            result = done
    return result


def _record_one(item: dict, dry_run: bool) -> dict:
    entry = {"pilot": item["pilot"], "question": item["question"], "verdict": None, "receipt": None, "mode": None,
             "saved": None, "why": None}
    if dry_run:
        entry["why"] = DRY_RUN
        return entry
    try:
        result = pipeline.run(item["flight_plan"], item["question"], use_bedrock=True)
    except Exception as exc:                  # pipeline.run never raises; one odd run must not end the recording
        entry["why"] = f"the run stopped ({type(exc).__name__})"
        return entry
    if isinstance(result, dict):
        entry.update(verdict=result.get("verdict"), receipt=result.get("receipt"), mode=result.get("mode"))
    entry["why"] = _unfit(result)
    if entry["why"]:
        return entry
    try:
        ready = public_result(_prepare(result))
    except NotPublic as exc:                  # a plain sentence of ours: a side that is one line cannot be published
        entry["why"] = str(exc)
        return entry
    except Exception as exc:                  # only the type: a message could carry the user's input
        entry["why"] = f"the month table or the proofs could not be computed ({type(exc).__name__})"
        return entry
    ready["recorded_at"] = recorded_at()           # R15: every saved Result says when it was recorded (Eastern time)
    path = pipeline.save_run(ready, item["flight_plan"], item["question"])
    if path is None:
        entry["why"] = NOT_BEDROCK
        return entry
    entry["saved"], entry["why"] = str(path), None
    if item.get("own"):
        _copy_default(item["pilot"], path)
    return entry


def _copy_default(pilot: str, path) -> None:
    """What GET /api/demo-run serves: Robert's own-question run is default.json, the others' default_<id>.json."""
    name = "default.json" if pilot == pipeline.DEFAULT_PILOT else f"default_{pilot}.json"
    shutil.copyfile(path, Path(pipeline.DEMO_DIR) / name)


def _run_key(item: dict) -> str | None:
    try:
        return pipeline.run_key(item["flight_plan"], item["question"])
    except (AttributeError, TypeError, ValueError):
        return None


def record(plan, *, dry_run: bool = False, on_result=None) -> list:
    """Run the plan in order, one run at a time, and return one entry per run:
    {"pilot", "question", "verdict", "receipt", "mode", "saved": path | None, "why": sentence | None}.
    `on_result(entry)` is called as each run ends. Never invents a run: a run without an explanation is reported, not saved.
    Two plan items with the same inputs (same flight plan and question) are one run: the second reuses the first's file."""
    out, recorded = [], {}
    for item in plan:
        key = None if dry_run else _run_key(item)
        if key in recorded:                   # the same inputs are the same run (Amira's own question is the chip-war card): kept once
            entry = {**recorded[key], "pilot": item["pilot"], "question": item["question"]}
            if item.get("own"):
                _copy_default(item["pilot"], entry["saved"])
        else:
            entry = _record_one(item, dry_run)
            if key is not None and entry["saved"]:
                recorded[key] = entry
        out.append(entry)
        if on_result:
            on_result(entry)
    return out


# ---- the static read-only demo ----
FAKE_NAME = re.compile(r"fake", re.I)
FAKE_FILES = {"story-data.js"}                  # the story's FAKE sample data, loaded only under ?fake=1
SKIP_NAMES = {"__pycache__", "node_modules", "starter", "etf_holdings.csv",
              "dev",                                             # web/dev/: the lanes' harness pages, never published
              "classic.html", "classic.js", "classic.css", "classic-globe.js"}   # the frozen classic page stays out of the demo
PILOT_FILE = re.compile(r"[a-z][a-z0-9_-]{0,31}")                 # runs/<investor>.json, the Replay page's static read
SKIP_SUFFIXES = {".csv", ".pem", ".key"}
TEXT_SUFFIXES = {".html", ".js", ".mjs", ".json", ".css", ".svg", ".txt", ".md", ".map"}
# What a credential looks like in a text file, in any letter case (ledger 29): an access key id (permanent or temporary,
# even glued to a word), the names of the AWS secret, session token and Bedrock bearer token, a Bedrock API key (ABSK...),
# a GitHub token (classic `ghp_`... or fine-grained `github_pat_`...), the signed-URL token, the server password's name, a
# private key block.
CREDENTIALS = re.compile(
    r"(?:AKIA|ASIA)[0-9A-Z]{16}(?![0-9A-Z])"
    r"|aws_secret_access_key|aws_session_token|aws_bearer_token_bedrock"
    r"|ABSK[A-Za-z0-9+/=]{20,}"
    r"|gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,}"
    r"|x-amz-security-token|epicentre_password"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----", re.I)
META_TAGS = re.compile(r'[ \t]*<meta\s+name="epicentre-(?:mode|commit|live)"[^>]*>[ \t]*\n?')


def _eastern():
    """Montreal's clock (the datathon's): America/Toronto, else the fixed EST offset when this machine has no time zone data."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("America/Toronto")
    except Exception:                                    # no tzdata (a slim image): November is EST
        return timezone(timedelta(hours=-5), "EST")


def recorded_at(saved_at=None) -> str:
    """When a run was recorded, ISO 8601 to the second in Eastern time (R15: saved runs say "recorded on <date>"): the saved
    file's own UTC `saved_at` when given, else now."""
    when = datetime.fromisoformat(saved_at) if isinstance(saved_at, str) and saved_at else datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(_eastern()).isoformat(timespec="seconds")


def _skipped(name: str, path: Path) -> bool:
    return (name.startswith(".") or name in SKIP_NAMES or name in FAKE_FILES or bool(FAKE_NAME.search(name))
            or path.suffix.lower() in SKIP_SUFFIXES or path.is_symlink())


def _skip(directory, names):
    return {n for n in names if _skipped(n, Path(directory) / n)}


def _not_real(name: str, saved: dict) -> str | None:
    """Why a saved run may not be published as a real one (a sentence naming the file and what failed), else None. A pure
    function of the run file (ledger 29): the label says REAL, the Result names at least one source, and no source names fake
    data. It never looks at the data folder of this machine, so a fresh clone builds from the committed files alone."""
    label = saved.get("data")
    if label != "REAL":
        if label is None:
            return f"{name} has no data label: only runs labelled REAL are published."
        note = " (the recording machine could not confirm the real starter pack)" if label == "UNKNOWN" else ""
        return f"{name} is labelled {label}, not REAL{note}: only runs on the real dataset are published."
    sources = [s for s in pipeline._sources(saved["result"]) if s.strip()]
    if not sources:
        return f"{name} says REAL but its Result names no source, so nothing shows where its numbers came from."
    fake = next((s for s in sources if FAKE_NAME.search(s)), None)
    if fake is not None:
        return f"{name} says REAL but a source names fake data ({fake.strip()[:60]})."
    return None


def _saved_runs() -> list:
    """Every saved run in DEMO_DIR (files named by their 16-hex key), checked. Raises StaticBuildError listing every fault."""
    folder = Path(pipeline.DEMO_DIR)
    runs, problems = [], []
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        if not KEY_FILE.fullmatch(path.name):
            continue                                     # default*.json are copies; test_tally.json is not a run
        saved = pipeline._read_saved(path)
        if saved is None:
            problems.append(f"{path.name} is not a whole saved run (a real live run with an explanation).")
            continue
        why = _not_real(path.name, saved)
        if why:
            problems.append(why)
        if not COMMIT.fullmatch(str(saved.get("commit"))):
            problems.append(f"{path.name} has no commit ({saved.get('commit')}): the page could not say which code made it.")
        if saved.get("key") != path.stem or not all(isinstance(saved.get(k), str) for k in ("question", "as_of")):
            problems.append(f"{path.name} does not match its own key, question and date.")
        runs.append({"path": path, "saved": saved})
    if problems:
        raise StaticBuildError("The static demo was refused:\n- " + "\n- ".join(problems))
    if not runs:
        raise StaticBuildError("There are no saved runs to publish. Record them first: python scripts/record_demo.py")
    return runs


def _order(runs: list) -> list:
    """The recording plan's order: investors as in personas.json, each one's own question first, then the storm cards."""
    try:
        data = _personas()
    except Exception:                                    # the order is cosmetic: an unreadable personas file must not stop a build
        data = {"pilots": {}, "storm_cards": {}}
    norm = lambda q: " ".join(str(q).lower().split())      # noqa: E731
    pilots = list(data["pilots"])
    storms = [norm(c.get("question")) for c in data["storm_cards"].values()]

    def rank(run):
        pilot = run["saved"]["result"].get("pilot")
        own = norm((data["pilots"].get(pilot) or {}).get("question"))
        questions = [own] + storms
        q = norm(run["saved"]["question"])
        return (pilots.index(pilot) if pilot in pilots else len(pilots), questions.index(q) if q in questions else len(questions),
                run["saved"]["saved_at"], run["saved"]["key"])

    return sorted(runs, key=rank)


def _default_name(pilot: str) -> str:
    """The saved default file of one investor: default.json for Robert (his own question), default_<id>.json for the others."""
    return "default.json" if pilot == pipeline.DEFAULT_PILOT else f"default_{pilot}.json"


def _default_run(ordered: list) -> dict:
    """The run `runs/default.json` copies: the saved default.json (Robert's own question), else Robert's first run."""
    kept = pipeline._read_saved(Path(pipeline.DEMO_DIR) / "default.json")
    for run in ordered:
        if kept is not None and run["saved"]["key"] == kept.get("key"):
            return run
    return next((r for r in ordered if r["saved"]["result"].get("pilot") == pipeline.DEFAULT_PILOT), ordered[0])


def _replayed(saved: dict) -> dict:
    """One saved run as the page opens it: a replay, public, plain JSON (no private keys), checked for leaks."""
    replay = pipeline._as_replay(saved, pipeline.REPLAY_MESSAGES["demo"])
    replay["run_id"] = saved["key"][:12]                 # stable, so a rebuild changes nothing
    if not isinstance(replay.get("recorded_at"), str):   # R15: a file saved before recorded_at existed: its own saved_at
        replay["recorded_at"] = recorded_at(saved.get("saved_at"))
    try:
        cut = public_result(replay)
    except NotPublic as exc:
        raise StaticBuildError(f"{saved['key']}.json cannot be published. {exc} Nothing was built.") from None
    final = pipeline.jsonable(cut)
    leaks = find_leaks(final)
    if leaks:
        raise StaticBuildError(f"{saved['key']}.json still carries data that is not public ({leaks[0]}); nothing was built.")
    return final


def _meta_tags(commit: str, live_url) -> str:
    tags = ['<meta name="epicentre-mode" content="static">',
            f'<meta name="epicentre-commit" content="{html.escape(commit[:SHORT_COMMIT], quote=True)}">']
    if live_url:
        tags.append(f'<meta name="epicentre-live" content="{html.escape(live_url, quote=True)}">')
    return "".join(f"{t}\n" for t in tags)


def _check_output(folder: Path) -> None:
    for path in folder.rglob("*"):
        parts = {p.lower() for p in path.relative_to(folder).parts}
        if path.is_symlink() or "starter" in parts or path.name == "etf_holdings.csv" or path.suffix.lower() == ".csv":
            raise StaticBuildError(f"{path.name} must never be published; nothing was built.")
        if FAKE_NAME.search(path.name) or path.name in FAKE_FILES:
            raise StaticBuildError(f"{path.name} is FAKE sample data; nothing was built.")
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES and CREDENTIALS.search(path.read_text(encoding="utf-8", errors="ignore")):
            raise StaticBuildError(f"{path.name} looks like it holds credentials; nothing was built.")


def _out_folder(out_dir) -> Path:
    """The folder to build into: new, empty, or an earlier static build; never the source, the repository or the saved runs."""
    out = Path(out_dir).resolve()
    for guarded in (Path(server.WEB_DIR), Path(pipeline.DEMO_DIR)):          # not inside, not equal, not around the source
        g = guarded.resolve()
        if out == g or g in out.parents or out in g.parents:
            raise StaticBuildError(f"{out_dir} is the source or holds it: choose a new folder for the site.")
    if out == ROOT.resolve() or out in ROOT.resolve().parents:                 # a folder inside the repository is fine
        raise StaticBuildError(f"{out_dir} is the repository or holds it: choose a new folder for the site.")
    if out.exists():
        earlier = (out / "runs" / "index.json").is_file() and (out / "index.html").is_file() and \
            'name="epicentre-mode"' in (out / "index.html").read_text(encoding="utf-8", errors="ignore")
        if not out.is_dir() or (any(out.iterdir()) and not earlier):
            raise StaticBuildError(f"{out_dir} is not an empty folder or an earlier static build: choose a new folder.")
    return out


def build_static(out_dir, *, live_url: str | None = None) -> Path:
    """Build the read-only site into `out_dir` from web/ and the saved runs; returns the folder. All or nothing: every
    saved run and the target are checked first, the site is built beside the target and moved in once it is checked.
    `live_url` (https only) becomes `<meta name="epicentre-live">`, the link the page offers for live-only actions."""
    if live_url is not None:
        parts = urlsplit(live_url) if LIVE_URL.fullmatch(live_url) else None
        if parts is None or not parts.hostname or "@" in parts.netloc:
            raise StaticBuildError("The live app address must be a plain https:// address: no spaces, quotes, user name or password.")
    runs = _saved_runs()
    web = Path(server.WEB_DIR)
    if not (web / "index.html").is_file():
        raise StaticBuildError("web/index.html is missing, so there is no page to publish.")
    out = _out_folder(out_dir)
    ordered = _order(runs)
    default = _default_run(ordered)
    texts = {run["saved"]["key"]: server.to_json(_replayed(run["saved"])) for run in ordered}
    building = out.with_name(out.name + ".building")
    shutil.rmtree(building, ignore_errors=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(web, building, ignore=_skip)
        page = META_TAGS.sub("", (building / "index.html").read_text(encoding="utf-8"))
        head_end = page.find("</head>")
        if head_end < 0:
            raise StaticBuildError("web/index.html has no </head>, so the demo marker cannot be added.")
        tags = _meta_tags(default["saved"]["commit"], live_url)
        (building / "index.html").write_text(page[:head_end] + tags + page[head_end:], encoding="utf-8")
        evals = ROOT / "docs" / "eval_results.json"           # the measured eval the page quotes (#why, #how): always the canonical copy
        if evals.is_file():
            shutil.copyfile(evals, building / "eval_results.json")
        (building / "runs").mkdir()
        for key, text in texts.items():
            (building / "runs" / f"{key}.json").write_text(text, encoding="utf-8")
        (building / "runs" / "default.json").write_text(texts[default["saved"]["key"]], encoding="utf-8")
        mine = {}                                    # runs/<investor>.json: the investor's saved default (default.json,
        for r in ordered:                            # default_<id>.json), else their first run (their own question first)
            pid = r["saved"]["result"].get("pilot")
            if isinstance(pid, str) and PILOT_FILE.fullmatch(pid) and pid not in ("index", "default") and pid not in mine:
                kept = pipeline._read_saved(Path(pipeline.DEMO_DIR) / _default_name(pid))
                key = kept.get("key") if isinstance(kept, dict) else None
                mine[pid] = key if key in texts else r["saved"]["key"]   # a run with the same question (typed limits) never wins
        for pid, key in mine.items():
            (building / "runs" / f"{pid}.json").write_text(texts[key], encoding="utf-8")
        index = [{"key": r["saved"]["key"], "pilot": r["saved"]["result"].get("pilot"), "question": r["saved"]["question"],
                  "as_of": r["saved"]["as_of"], "file": f"runs/{r['saved']['key']}.json", "commit": r["saved"]["commit"]}
                 for r in ordered]
        (building / "runs" / "index.json").write_text(json.dumps(index, indent=1, ensure_ascii=False), encoding="utf-8")
        _check_output(building)
        shutil.rmtree(out, ignore_errors=True)
        building.rename(out)
    except BaseException:
        shutil.rmtree(building, ignore_errors=True)
        raise
    return Path(out_dir)


# ---- command line ----
def format_line(entry: dict) -> str:
    """One printed line per run: "{pilot:8} {verdict or '-':12} {verified}/{total} {mode:11} {saved file or 'not saved: ' + why}"."""
    receipt = entry["receipt"] if isinstance(entry.get("receipt"), dict) else {}
    verified, total = receipt.get("verified"), receipt.get("total")
    counts = f"{verified}/{total}" if isinstance(verified, int) and isinstance(total, int) else "-/-"
    where = Path(entry["saved"]).name if entry["saved"] else f"not saved: {entry['why'] or 'unknown'}"
    return f"{entry['pilot']:8} {entry['verdict'] or '-':12} {counts} {entry['mode'] or '-':11} {where}"


def _names(text, default) -> list:
    return list(default) if text is None else [name.strip() for name in text.split(",") if name.strip()]


# ---- the scripted extras (Sun Nov 15): the move picker's curated moves and the "Test the AI" questions ----
def _flight_plan(pid: str) -> dict:
    pilot = _personas()["pilots"][pid]
    return {"portfolio": pilot["portfolio"], "amount": pilot["amount"], "profile": pilot["profile"], "limits": None, "pilot": pid}


def scripted_plan() -> tuple:
    """(defaults, moves, tests) from data/personas.json and data/demo_scripted.json: the four investors' own questions
    (own=True), the curated moves, and the tests (kind run, blocked or clarify), each a plan item with its flight plan."""
    path = Path(getattr(pipeline, "SCRIPTED_PATH", ROOT / "data" / "demo_scripted.json"))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise RecordError(f"{path.name} could not be read.") from None
    defaults = plan_runs(list(DEFAULT_PILOTS), [])
    moves = [{"pilot": m["pilot"], "flight_plan": _flight_plan(m["pilot"]), "question": m["question"], "own": False, "move": m}
             for m in data.get("moves") or []]
    tests = [{"pilot": t.get("pilot") or pipeline.DEFAULT_PILOT, "flight_plan": _flight_plan(t.get("pilot") or pipeline.DEFAULT_PILOT),
              "question": t["question"], "own": False, "test": t} for t in data.get("tests") or []]
    return defaults, moves, tests


def _key_of(entry) -> str | None:
    return Path(entry["saved"]).stem if entry.get("saved") else None


def _inline(item) -> dict:
    """A blocked or clarify answer as the API returns it (server._public: the Result as JSON), with when it was recorded."""
    result = pipeline.jsonable(pipeline.run(item["flight_plan"], item["question"], use_bedrock=True))
    return {**result, "recorded_at": recorded_at()}


def record_scripted(on_result=None) -> tuple:
    """Record the defaults, the moves and the tests; write data/demo_runs/moves.json and tests.json. Returns
    (ok, entries): ok only when every run was saved and every blocked / clarify answer came back as labelled."""
    defaults, moves, tests = scripted_plan()
    runs = [t for t in tests if t["test"]["kind"] == "run"]
    entries = record(defaults + moves + runs, on_result=on_result)
    by_question = {(e["pilot"], e["question"]): e for e in entries}
    ok = all(e["saved"] for e in entries)
    listed = []
    for item in defaults:
        e = by_question[(item["pilot"], item["question"])]
        saved = json.loads(Path(e["saved"]).read_text(encoding="utf-8")) if e.get("saved") else {}
        change = ((saved.get("result") or {}).get("scenario") or {}).get("change")
        listed.append({"pilot": item["pilot"], "ticker": (change or {}).get("ticker"), "weight": (change or {}).get("weight"),
                       "question": item["question"], "key": _key_of(e), "default": True})
    for item in moves:
        m, e = item["move"], by_question[(item["pilot"], item["question"])]
        listed.append({"pilot": m["pilot"], "ticker": m["ticker"], "weight": m["weight"], "question": m["question"],
                       "key": _key_of(e), **({"from": m["from"]} if m.get("from") else {})})   # "from": a funded move
    shown = []
    for item in tests:
        t = item["test"]
        row = {k: t.get(k) for k in ("id", "label", "question", "shows", "kind", "pilot")}
        if t["kind"] == "run":
            row["key"] = _key_of(by_question[(item["pilot"], item["question"])])
        else:
            row["response"] = _inline(item)
            ok = ok and row["response"].get("status") == t["kind"]
            if on_result:
                on_result({"pilot": item["pilot"], "question": item["question"], "verdict": None, "receipt": None,
                           "mode": row["response"].get("mode"), "saved": None,
                           "why": f"{t['kind']}: status {row['response'].get('status')}"})
        shown.append(row)
    folder = Path(pipeline.DEMO_DIR)
    (folder / "moves.json").write_text(json.dumps({"version": 1, "as_of": pipeline.DATASET_END, "moves": listed},
                                                  indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (folder / "tests.json").write_text(json.dumps({"version": 1, "tests": shown}, indent=1, ensure_ascii=False, allow_nan=False)
                                       + "\n", encoding="utf-8")
    return ok, entries


def _record_main(args) -> int:
    plan = plan_runs(_names(args.pilots, DEFAULT_PILOTS), _names(args.storms, DEFAULT_STORMS))
    if args.dry_run:
        for n, entry in enumerate(record(plan, dry_run=True), 1):
            print(f"{n:2} {entry['pilot']:8} {entry['question']}")
        return 0
    entries = record(plan, on_result=lambda entry: print(format_line(entry), flush=True))
    return 0 if all(entry["saved"] for entry in entries) else 1


def _static_main(args) -> int:
    out = build_static(args.static, live_url=args.live)
    index = json.loads((out / "runs" / "index.json").read_text(encoding="utf-8"))
    commits = sorted({entry["commit"][:SHORT_COMMIT] for entry in index})
    head = re.search(r'name="epicentre-commit" content="([0-9a-f]+)"', (out / "index.html").read_text(encoding="utf-8"))
    print(f"Built {out} from {len(index)} saved run{'' if len(index) == 1 else 's'}, code {head.group(1) if head else '-'}.")
    if len(commits) > 1:
        print(f"Warning: the runs were recorded at {len(commits)} different commits ({', '.join(commits)}); the page names "
              "one, runs/index.json names each run's own. Record the others again to publish a single commit.")
    if not args.live:
        print("No --live address: the page will not link to the live app.")
    print("This only built the folder. Publishing needs the lead's yes.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="record_demo.py", description="Record the demo runs live, or build the static demo.")
    parser.add_argument("--pilots", help=f"investors to record, comma separated (default {','.join(DEFAULT_PILOTS)})")
    parser.add_argument("--storms", help=f"storm cards to ask each investor, comma separated (default {','.join(DEFAULT_STORMS)})")
    parser.add_argument("--dry-run", action="store_true", help="print the planned runs and run nothing")
    parser.add_argument("--scripted", action="store_true",
                        help="record the four defaults, the curated moves and the Test-the-AI questions (data/demo_scripted.json) "
                             "and write data/demo_runs/moves.json and tests.json")
    parser.add_argument("--static", metavar="OUT_DIR", help="build the read-only site from web/ and the saved runs into OUT_DIR")
    parser.add_argument("--live", metavar="URL", help="with --static: the https address of the live app, for the page to link to")
    args = parser.parse_args(argv)
    if args.static and args.dry_run:
        parser.error("--static builds from saved runs; it cannot be combined with --dry-run")
    if args.live and not args.static:
        parser.error("--live is only used with --static")
    try:
        if args.scripted and not args.static:
            ok, _ = record_scripted(on_result=lambda entry: print(format_line(entry), flush=True))
            return 0 if ok else 1
        return _static_main(args) if args.static else _record_main(args)
    except RecordError as exc:
        print(exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
