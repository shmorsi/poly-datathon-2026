"""EPICENTRE proofs (plan P, spec section 21, ledger sections 15 and 18): code that lets a juror see the claims hold.

Task P1, the sealed envelope: `seal` and `scramble_future`.
Task P2, switch the navigator off: `navigator_effect` (what the model changed against the keyword rules; see its docstring).
Task P3, days below your floor: `below_floor` (how many days of the replay the mix was below the floor, and the longest run).
Task P8, the evidence drawer: `evidence_rows` (the few data rows the code read for one fact's number).

What they prove, and what they do not (never claim more than this):
  - `seal` is a SHA-256 of the canonical JSON of the five inputs of a decision made at a past date. The same
    inputs give the same 64 hex digits. A plain hash match proves determinism. Python is the reference for
    the canonical form and the seal is only ever computed here: floats are written with `format(x, ".10f")`,
    which rounds an exact tie to even, while a JS `toFixed(10)` rounds it up, so a port can differ only on
    odd multiples of 2^-11 (such as 1/2048); a port follows this code, never the other way round.
  - `scramble_future` re-runs the decision on a copy of the data in which every row dated after `as_of` has had
    its date re-dealt (fixed seed), and shows the same seal. A match means the decision read nothing dated
    after `as_of` in the files that were copied: prices (adjusted and unadjusted close), FX rates, macro series,
    dividends and the shock catalog. It does not mean the decision is right, and it predicts nothing: history
    is not a forecast. With no row after `as_of` there is nothing to scramble: the result says so
    (`nothing_to_scramble`) and the page must not present that match as a proof.
  - What the scramble does NOT cover (the spec says the same). Not copied, so not scrambled: the ESG
    controversy flags and their source dates, the ETF holdings snapshot, the deep-history panel, and the
    release dates of macro series (a monthly value is dated to its reference month, so a value released
    after `as_of` but dated before it stays where it is). Not caught because only dates move: a figure that
    does not depend on which date a row carries (a sum or a maximum over all later rows), a filter with the
    wrong cutoff whose set of ids is the same after the dates move, and, with fewer than two different later
    dates, anything at all (nothing moves). Nor what a model remembers.
  - `evidence_rows` lists, for one fact, the rows its number was read from: the portfolio's value on the fact's dates (a replay, base
    100), the largest line's `adj_close` on its last real trading row, and USD/CAD from the file row it came from. It recomputes nothing
    and proves nothing by itself. For a worst drop, a worst 12-month drop and growth per year the printed rows are enough to redo the
    arithmetic by hand (a drop is the later value over the earlier one, less one; growth per year is that ratio taken to the power of
    one over the years between the two dates). For the days below your floor they are only the first and last day of the longest
    stretch: they say where it was, they do not count the days. It is history, not a forecast. Raw prices are licensed (red gate 8):
    with `public=True` it returns no row and reads no price.
  - The data folder is the organizers' untrusted download: it is read with pandas only, never run, and never
    written. The copy lives in a temporary folder that is deleted afterwards.
No model and no AWS call is made here. Dates are ISO `YYYY-MM-DD` strings, which sort like dates.
"""
import copy
import hashlib
import json
import math
import shutil
import tempfile
import time
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from xml.etree import ElementTree

import numpy as np
import pandas as pd

import config
from tools import data as market_data

SCRAMBLE_SEED = ROBUST_SEED = 20261114     # fixed seeds: the date re-deal here, the bootstrap in task P5
N_PATHS = 2000                             # bootstrap paths (P5)
BLOCK_DAYS = 20                            # bootstrap block length in trading days (P5)
FLOOR_STEP = -0.05                         # step between the floors compared, a fraction (P4)
HEADLINE_CLASSES = ("equity", "crypto")    # asset classes ranked as headline names (P7)
INVESTORS = ("robert", "mateo", "amira")   # the three personas, in display order (P4, P6)
ENVELOPE_AS_OF = "2025-01-31"              # the past date of the saved sealed envelope (P10)
EVAL_RESULTS_JSON = config.ROOT / "docs" / "eval_results.json"          # written by scripts/eval.py (B Task 11)
TEST_TALLY_JSON = config.DEMO_RUNS_DIR / "test_tally.json"              # written by scripts/record_tally.py (P9)
LOOKAHEAD_NAME = "scramble the future"     # the look-ahead proof the tally reports on (the three tests below)
LOOKAHEAD_TESTS = ("tests/test_proofs.py::test_scramble_keeps_the_seal_of_an_honest_decision",
                   "tests/test_proofs.py::test_scramble_breaks_the_seal_of_a_leaky_decision",
                   "tests/test_data.py::test_perturbation_scrambles_every_later_row_and_every_key_stays_identical")
TALLY_KEYS = ("passed", "failed", "errors", "skipped", "total", "seconds", "commit", "date")   # the tally file's own keys

# The dated tables of the starter pack: (file, key in the counts, the column that says "after as_of",
# the date columns re-dealt together). The catalog is passed in by path and written as events.csv; the
# dividends file is optional (the FAKE pack has none). They are drawn in this order, dividends last, so the
# draws of the first four files do not depend on whether the dividends file exists.
_PACK_TABLES = (("prices_daily.csv", "prices", "date", ("date",)),
                ("fx_usdcad_daily.csv", "fx", "date", ("date",)),
                ("macro_rates.csv", "macro", "date", ("date",)))
_CATALOG_TABLE = ("events.csv", "events", "date", ("date", "announced", "announced_at"))
_DIVIDENDS_TABLE = ("corporate_actions.csv", "corporate_actions", "ex_date", ("ex_date",))


# --- the seal -----------------------------------------------------------------------------------
def _canon(x) -> str:
    """One value in the canonical form (ledger section 10); the browser builds the same bytes."""
    if x is None:
        return "null"
    if isinstance(x, (bool, np.bool_)):                    # before int: True is an int in Python
        return "true" if x else "false"
    if isinstance(x, (int, np.integer)):
        return str(int(x))
    if isinstance(x, (float, np.floating)):
        x = float(x)
        if x.is_integer():                                 # 600000.0 -> 600000, -0.0 -> 0
            return str(int(x))
        text = format(x, ".10f").rstrip("0").rstrip(".")
        return "0" if text in ("", "-0") else text
    if isinstance(x, str):
        return json.dumps(x, ensure_ascii=False)
    if isinstance(x, dict):
        if not all(isinstance(k, str) for k in x):
            raise TypeError("canonical_json: object keys must be strings")
        return "{" + ",".join(json.dumps(k, ensure_ascii=False) + ":" + _canon(v)
                              for k, v in sorted(x.items(), key=lambda kv: kv[0])) + "}"
    if isinstance(x, (list, tuple)):
        return "[" + ",".join(_canon(v) for v in x) + "]"
    raise TypeError(f"canonical_json: cannot write a {type(x).__name__}")


def canonical_json(obj) -> str:
    """Keys sorted, no spaces, integral floats as integers, other floats `.10f` stripped, `-0` as `0`."""
    return _canon(obj)


def seal(flight_plan, as_of, known_event_ids, checks, verdict) -> str:
    """64-hex SHA-256 of the canonical JSON of the five inputs (event ids sorted), encoded as UTF-8."""
    body = {"flight_plan": flight_plan, "as_of": as_of, "known_event_ids": sorted(known_event_ids),
            "checks": checks, "verdict": verdict}
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


# --- scramble the future ------------------------------------------------------------------------
def _redeal(path: Path, out: Path, as_of: str, key: str, columns: tuple, rng) -> int:
    """Write `path` to `out` with the `columns` of every row whose `key` is after `as_of` re-dealt along ONE
    random cycle (with two or more later rows, none keeps its own slot); rows on or before `as_of` are
    untouched. All cells are read as text, so no number takes a float round trip. Returns the number of
    later rows."""
    table = pd.read_csv(path, dtype=str, keep_default_na=False)
    later = (table[key] > as_of).to_numpy()
    n = int(later.sum())
    p = rng.permutation(n)
    for col in columns:
        old = table.loc[later, col].to_numpy(dtype=object)
        new = old.copy()
        new[p] = old[np.roll(p, 1)]
        table.loc[later, col] = new
    table.to_csv(out, index=False)
    return n


def _guard_sources(pairs) -> None:
    """The starter data and the committed catalog are never written: refuse a target that is its source."""
    for source, target in pairs:
        if target.exists() and target.samefile(source):
            raise ValueError(f"scramble_copy: refusing to write over its source {source}")


def scramble_copy(src, dst, as_of, *, events_path=None, seed=SCRAMBLE_SEED) -> dict:
    """Copy the starter pack in `src` to `dst` with every row dated after `as_of` re-dealt (fixed seed).

    `assets_universe.csv` is copied as is. Prices, FX, macro, the shock catalog (only with `events_path`,
    written as events.csv) and the dividends (only if corporate_actions.csv exists, by `ex_date`) are
    re-dealt one file after the other from one generator. Only the date moves: a price row keeps its ticker
    and all its prices, `close` as much as `adj_close`, so a late read of either sees other numbers.
    Returns the rows re-dealt per file: {"prices", "fx", "macro"[, "events"][, "corporate_actions"]}.
    `src` is never written.
    """
    src, dst, as_of = Path(src), Path(dst), pd.Timestamp(as_of).strftime("%Y-%m-%d")
    jobs = [(src / spec[0], dst / spec[0], *spec[1:]) for spec in _PACK_TABLES]
    if events_path is not None:
        jobs.append((Path(events_path), dst / _CATALOG_TABLE[0], *_CATALOG_TABLE[1:]))
    if (src / _DIVIDENDS_TABLE[0]).is_file():
        jobs.append((src / _DIVIDENDS_TABLE[0], dst / _DIVIDENDS_TABLE[0], *_DIVIDENDS_TABLE[1:]))
    universe = "assets_universe.csv"
    dst.mkdir(parents=True, exist_ok=True)
    _guard_sources([(path, out) for path, out, *_ in jobs] + [(src / universe, dst / universe)])
    shutil.copyfile(src / universe, dst / universe)
    rng, counts = np.random.default_rng(seed), {}
    for path, out, count, key, cols in jobs:
        counts[count] = _redeal(path, out, as_of, key, cols, rng)
    return counts


def scramble_future(decide, as_of, sha256, *, data_dir=None, events_path=None, seed=SCRAMBLE_SEED) -> dict:
    """Re-run `decide` on a scrambled copy of the data and compare its seal with `sha256`.

    `decide({"data_dir": Path, "events": Path})` returns the five seal inputs. Returns {"rows_shuffled",
    "seed", "sha256" (the seal of the copy), "match", "nothing_to_scramble", "ms"}. `nothing_to_scramble` is
    True when no row is dated after `as_of` (the copy equals the source): `match` is then a plain hash match
    and the page says "nothing to scramble at this date", never "same seal with the future scrambled".
    With no starter data or no catalog: {"error": one plain sentence}, before anything is copied.
    """
    src = Path(market_data.DATA_DIR if data_dir is None else data_dir)
    events = Path(config.EVENTS_CSV if events_path is None else events_path)
    if not (all((src / name).is_file() for name in market_data._FILES) and events.is_file()):
        return {"error": f"The scramble needs the starter data in {src} and the shock catalog."}
    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="epicentre-scramble-") as tmp:
        counts = scramble_copy(src, tmp, as_of, events_path=events, seed=seed)
        decided = decide({"data_dir": Path(tmp), "events": Path(tmp) / _CATALOG_TABLE[0]})
        sha = seal(**decided)
    return {"rows_shuffled": counts, "seed": seed, "sha256": sha, "match": sha == sha256,
            "nothing_to_scramble": sum(counts.values()) == 0,
            "ms": int(round((time.perf_counter() - t0) * 1000))}


# --- switch the navigator off (Task P2) -----------------------------------------------------------
WHAT = ("change", "families", "precedents", "clarify", "verdict")    # the rows of the diff, always in this order (ledger section 18)
_WEIGHT_TOLERANCE = 0.0005     # two sizes of one move are the same within this (ledger section 8, dollars to weight; the eval's tolerance)


def _same_change(a, b) -> bool:
    """True when two moves are the same: no move equals no move; otherwise the op, the ticker (any case) and
    `from_ticker` are equal and the two sizes are both missing or within 0.0005 of each other."""
    if not a and not b:
        return True
    if not a or not b:
        return False

    def name(move, key):
        value = move.get(key)
        return None if value is None else str(value).upper()

    if name(a, "op") != name(b, "op") or name(a, "ticker") != name(b, "ticker") or name(a, "from_ticker") != name(b, "from_ticker"):
        return False
    wa, wb = a.get("weight"), b.get("weight")
    if wa is None or wb is None:
        return wa is None and wb is None
    try:
        return abs(float(wa) - float(wb)) <= _WEIGHT_TOLERANCE + 1e-12      # the epsilon only absorbs float noise at the edge
    except (TypeError, ValueError):
        return False


def _clarify_of(scenario: dict):
    """What the reading asked, as the page may show it: the reason code, else True when a question was set, else None.
    The question's own text is never shown (ledger section 15)."""
    return scenario.get("clarify_reason") or (True if scenario.get("clarify") else None)


def _judged(scenario: dict):
    """What the judge is given by a reading: the mix it replays (None = today's mix, when there is no move) and the shocks
    (an empty list means all four families), as `pipeline._compare` reads them. None when a move came without its mix.
    The precedents (`event_ids`) do not reach the judge."""
    if scenario.get("change") and not scenario.get("portfolio"):
        return None
    move = bool(scenario.get("change") and scenario.get("portfolio"))
    return (dict(scenario["portfolio"]) if move else None, frozenset(scenario.get("families") or config.FAMILIES))


def navigator_effect(nav: dict, fb: dict) -> dict:
    """What the navigator changed in this run: the model's reading of the question against the keyword rules' reading.

    Each reading is `{"scenario": run_scenario | keyword_fallback output, "verdict", "binding_rule", "checks"}`. `nav` is the
    run's own. `fb` is the keyword reading D Task 6 stores beside every Bedrock run (`scenario.keyword_result`), so the diff
    needs no second engine run. Pure and offline: it reads two dicts, calls no model and touches no data. One row per
    differing `WHAT`, in `WHAT` order, `{"what", "navigator", "fallback"}`:
      change      the two moves (dicts), unless `_same_change`;
      families    the two sorted family lists;
      precedents  the two `event_ids` lists as given, when the sets differ;
      clarify     the `clarify_reason` code, else True for a question set without a code, else None (the text is never shown);
      verdict     the two verdict enums, when the verdict without the navigator is known (below).
    `same` is "no row". It says the readings agree on what the page can show. It never says the numbers, the checklist or
    the debrief are the same with the AI on or off, and nothing built on it may be worded so (spec 24, meeting 2, resolution 4).
    The page card is titled "What the navigator changed in this run".

    `verdict_without`, `binding_without` and `checks_without` are what the real judge says for the keyword reading's own
    mix and shocks, never a guess and never the navigator's verdict lent to a reading that differs (D Task 6 concern 1).
    In this order: (1) `fb` carries a "verdict" key: P10 replayed the keyword reading through the pipeline (governance and
    the tools) and the three fields are taken as they are, a None meaning that replay gave no verdict; (2) the keyword
    reading set a question (`clarify`): the run stops before any judge runs, so no verdict and no checks; (3) both readings hand
    the judge the same mix and the same shocks (`_judged`): the navigator's own three fields, because the same judge on the
    same inputs gives the same answer; (4) otherwise all three are None and there is no verdict row, because the verdict is
    unknown. The Result has no key for the reason: a None with no `clarify_reason` on the `fallback` means "not replayed
    yet" (governance.evaluate is parked; P10 supplies the replay). A caller must never build `fb` as `{**nav, "scenario": kw}`.
    """
    nav, fb = nav if isinstance(nav, dict) else {}, fb if isinstance(fb, dict) else {}
    n, f = nav.get("scenario") or {}, fb.get("scenario") or {}
    if "verdict" in fb:
        known, without = True, (fb.get("verdict"), fb.get("binding_rule"), fb.get("checks"))
    elif f.get("clarify"):
        known, without = True, (None, None, None)
    elif _judged(n) is not None and _judged(n) == _judged(f):
        known, without = True, (nav.get("verdict"), nav.get("binding_rule"), nav.get("checks"))
    else:
        known, without = False, (None, None, None)
    nav_fams, fb_fams = list(n.get("families") or []), list(f.get("families") or [])
    nav_ids, fb_ids = list(n.get("event_ids") or []), list(f.get("event_ids") or [])
    rows = {"change": (n.get("change"), f.get("change"), not _same_change(n.get("change"), f.get("change"))),
            "families": (sorted(nav_fams), sorted(fb_fams), sorted(nav_fams) != sorted(fb_fams)),
            "precedents": (nav_ids, fb_ids, set(nav_ids) != set(fb_ids)),
            "clarify": (_clarify_of(n), _clarify_of(f), _clarify_of(n) != _clarify_of(f)),
            "verdict": (nav.get("verdict"), without[0], known and nav.get("verdict") != without[0])}
    diffs = [{"what": w, "navigator": copy.deepcopy(rows[w][0]), "fallback": copy.deepcopy(rows[w][1])} for w in WHAT if rows[w][2]]
    return {"same": not diffs, "diffs": diffs, "verdict": nav.get("verdict"), "verdict_without": without[0],
            "binding_rule": nav.get("binding_rule"), "binding_without": without[1],
            "checks_without": copy.deepcopy(without[2]),
            "fallback": {"type": f.get("type"), "change": copy.deepcopy(f.get("change")), "families": fb_fams,
                         "event_ids": fb_ids, "clarify_reason": f.get("clarify_reason")}}


# --- days below your floor (Task P3) --------------------------------------------------------------
BELOW_FLOOR_SOURCE = "Drawdown path (value / running high - 1) vs the floor, compared after rounding to 0.1 pp"


def _round_pp(x: float) -> Decimal:
    """A fraction as percent, ROUND_HALF_UP to 0.1 pp, through `repr` so float noise cannot tip a limit:
    -0.1500004 -> Decimal('-15.0'), -0.1505 -> Decimal('-15.1'). The exact twin of `governance.round_pp` (a test pins the two
    on a grid): proofs.py imports nothing from B's module (ledger section 18), and P10 swaps this for the import."""
    return (Decimal(repr(float(x))) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _breaks(value, floor) -> bool:
    """True when `value` is below `floor` after both are rounded to 0.1 pp, the rule's own comparison (pitfall 5): exactly at
    the limit passes, so -15.00004 % does not break -15.0 %. An unknown value (None) is never counted."""
    return value is not None and _round_pp(value) < _round_pp(floor)


def below_floor(drawdown: dict, floor) -> dict:
    """On how many days of the replay the mix was below the investor's floor, and the longest run of such days.

    `drawdown` is `{"dates", "values"}`: on every date the fall from the running high (value / running high - 1, a fraction at or
    below 0, the fall view of ledger section 14), as `tools.metrics.drawdown_series` gives it for a path already cut at `as_of`
    (this function filters nothing and reads no data). `floor` is a negative fraction, `limits["floor"]`. A day is below when
    `_breaks(value, floor)`, so the count is 0 whenever the floor check passes (Robert at 8 % NVDA: 0 days).

    Returns `{"days", "of_days", "floor", "longest", "stretches", "source", "as_of"}` (ledger section 18, BF): `days` and `of_days`
    are trading days, the rows of the path (a weekend or a holiday with no row is not a day); `stretches` are the maximal runs of
    consecutive below rows as `[start, end]` in date order; `longest` is `{"days", "start", "end"}` of the longest one, the earliest
    on a tie, or None when no day is below; `as_of` is the last date. A history, not a forecast: it says how many days of the replay
    were below the floor, nothing about the days to come. No dollars here: a loss in dollars is amount x drawdown (ledger section 30).
    An empty path gives `{"error": <one plain sentence>}`. Programming errors raise ValueError: dates and values of different
    lengths, and a floor above 0 (the floor is a fall; 0.15 for -0.15 would count every day as below).
    """
    dates, values = list(drawdown["dates"]), list(drawdown["values"])
    if float(floor) > 0:
        raise ValueError("The floor is a fall, so it must be a fraction at or below zero.")
    if len(dates) != len(values):
        raise ValueError(f"The drawdown path has {len(dates)} dates but {len(values)} values.")
    if not dates:
        return {"error": "The replay has no days to count."}
    below = [_breaks(v, floor) for v in values]
    runs, first = [], None                      # (first row, last row) of each maximal run of below days
    for i, flag in enumerate(below):
        if flag and first is None:
            first = i
        elif not flag and first is not None:
            runs.append((first, i - 1))
            first = None
    if first is not None:
        runs.append((first, len(below) - 1))
    longest = max(runs, key=lambda r: r[1] - r[0], default=None)         # max keeps the first of equal runs: the earliest on a tie
    return {"days": sum(below), "of_days": len(dates), "floor": float(floor),
            "longest": None if longest is None else {"days": longest[1] - longest[0] + 1, "start": dates[longest[0]], "end": dates[longest[1]]},
            "stretches": [[dates[a], dates[b]] for a, b in runs],
            "source": BELOW_FLOOR_SOURCE, "as_of": dates[-1]}


# --- the data rows behind each fact (Task P8, the evidence drawer) -----------------------------------
EVIDENCE_LIMIT = 5                                              # data rows per fact in the drawer (spec section 21 item 4)
PORTFOLIO_FILE = "computed: portfolio_series (base 100, CAD)"   # a portfolio value is a replay, not a row of a file
PRICES_FILE, FX_FILE = "prices_daily.csv", "fx_usdcad_daily.csv"
CNQ_PRICES_FILE = f"{PRICES_FILE} (adj_close x {market_data.CNQ_FIX_FACTOR}, spec 9)"   # pitfall 1: the value the code used
_SIDES = ("today", "after")                                     # the two paths of a Result; `aligned` has no evidence rows


def _dig(obj, *keys):
    """obj[k1][k2]... or None as soon as a step is missing or not a dict."""
    for key in keys:
        obj = obj.get(key) if isinstance(obj, dict) else None
    return obj


def _finite_float(x):
    """x as a plain float, or None for a missing, boolean, non-numeric or non-finite value."""
    if isinstance(x, (bool, np.bool_)) or not isinstance(x, (int, float, np.number)):
        return None
    x = float(x)
    return x if np.isfinite(x) else None


def _fact_dates(path, result: dict) -> tuple:
    """`(side, dates)` for a fact's `inputs.path`: the path it is about ("today" or "after") and the dates whose data rows are its
    evidence. `metrics.<w>.max_drawdown` and `worst_rolling.<w>.value` -> that entry's peak and trough dates; `metrics.<w>.cagr` ->
    the first and last date of the series; `below_floor.<w>.days` and `.longest.days` -> the start and end of the longest stretch.
    Any other path (an input, a limit, a count, a share) has no dated rows: `(None, [])`. A date after the Result's `as_of` is
    dropped (red gate 3), and with no `as_of` to check against every date is; a repeated date stays once, in order."""
    parts = path.split(".") if isinstance(path, str) else []
    if len(parts) < 3 or parts[1] not in _SIDES:
        return None, []
    (head, side), tail = parts[:2], tuple(parts[2:])
    if (head, tail) in (("metrics", ("max_drawdown",)), ("worst_rolling", ("value",))):
        dates = [_dig(result, head, side, "peak_date"), _dig(result, head, side, "trough_date")]
    elif (head, tail) == ("metrics", ("cagr",)):                      # growth per year runs from the first day to the last
        span = _dig(result, "series", "dates") or []
        dates = [span[0], span[-1]] if len(span) else []
    elif head == "below_floor" and tail in (("days",), ("longest", "days")):
        dates = [_dig(result, head, side, "longest", "start"), _dig(result, head, side, "longest", "end")]
    else:
        return None, []
    as_of, kept = result.get("as_of"), []
    for day in dates:
        if isinstance(as_of, str) and isinstance(day, str) and day <= as_of and str(day) not in kept:
            kept.append(str(day))
    return side, kept


def _portfolio_rows(side: str, dates: list, result: dict) -> list:
    """The portfolio's value on each date, base 100: the number the chart draws, read from the Result's own series (a value
    per date or nothing, so a short list can never shift a number onto the wrong day)."""
    span, values = _dig(result, "series", "dates"), _dig(result, "series", side)
    if not isinstance(span, (list, tuple)) or not isinstance(values, (list, tuple, np.ndarray)) or len(span) != len(values):
        return []
    at, rows = dict(zip(span, values)), []
    for day in dates:
        value = _finite_float(at.get(day))
        if value is not None:
            rows.append({"file": PORTFOLIO_FILE, "date": day, "ticker": f"portfolio ({side})", "value": value})
    return rows


def _largest_line(side: str, result: dict):
    """The ticker of the biggest line of the mix the path was run on: `after` is the Result's `portfolio`; `today` is
    `baseline.portfolio` when the move changed the mix, else that same `portfolio`. Equal weights go to the first ticker in
    alphabetical order, not in the order of the dict."""
    mix = _dig(result, "baseline", "portfolio") if side == "today" else None
    mix = mix if isinstance(mix, dict) and mix else result.get("portfolio")
    held = []
    for ticker, weight in (mix.items() if isinstance(mix, dict) else ()):
        weight = _finite_float(weight)
        if weight is not None and weight > 0:
            held.append((-weight, str(ticker)))
    return min(held)[1] if held else None


def _price_rows(ticker: str, dates: list, market: dict) -> list:
    """The listing-currency `adj_close` the code used for `ticker`, on its last real trading row on or before each date (`traded`
    True; the row's own date, never a forward-filled one). CNQ.TO before 2022-08-22 carries the name of its correction (pitfall 1)."""
    local, traded = market.get("local"), market.get("traded")
    if not isinstance(local, pd.DataFrame) or not isinstance(traded, pd.DataFrame) or ticker not in local or ticker not in traded:
        return []
    cutoff, rows = pd.Timestamp(market_data.CNQ_FIX_BEFORE), []
    for day in dates:
        seen = traded[ticker].loc[:pd.Timestamp(day)]
        real = seen.index[seen.to_numpy(dtype=bool)]                 # the days on or before `day` with a row of its own
        row_day = real[-1] if len(real) else None
        value = None if row_day is None else _finite_float(local[ticker].get(row_day))
        if value is not None:
            fixed = ticker == market_data.CNQ_TICKER and row_day < cutoff
            rows.append({"file": CNQ_PRICES_FILE if fixed else PRICES_FILE, "date": row_day.strftime("%Y-%m-%d"),
                         "ticker": ticker, "value": value})
    return rows


def _usd_listed(ticker: str, market: dict) -> bool:
    """True when the bundle's universe lists `ticker` in USD (its price is then converted with USD/CAD)."""
    universe = market.get("universe")
    return (isinstance(universe, pd.DataFrame) and {"ticker", "currency"} <= set(universe.columns)
            and bool((universe.loc[universe["ticker"] == ticker, "currency"] == "USD").any()))


def _fx_rows(day: str, market: dict) -> list:
    """USD/CAD as the code used it on `day`, dated by the row of `fx_usdcad_daily.csv` it came from. The bundle carries the last
    published rate over a day the file does not list (a Canadian holiday), so its value on `day` can belong to an earlier row. A
    carried series changes value only on a listed day (the bundle's calendar has every listed day: a test checks it on the starter
    data), so walking back while the rate is unchanged ends on the first day of that rate: a row of the file with this very rate.
    When the file repeats a rate on the next day, the earlier of the two is cited. Only days on or before `day` are read (red gate 3)."""
    fx = market.get("fx")
    known = fx.loc[:pd.Timestamp(day)].dropna() if isinstance(fx, pd.Series) else ()
    value = _finite_float(known.iloc[-1]) if len(known) else None
    if value is None:
        return []
    other = np.flatnonzero(known.to_numpy() != known.iloc[-1])             # the days with another rate; the run of this one starts after the last
    first = known.index[other[-1] + 1 if len(other) else 0]
    return [{"file": FX_FILE, "date": first.strftime("%Y-%m-%d"), "ticker": "USDCAD", "value": value}]


def evidence_rows(fact_id, result: dict, market, *, public: bool = False) -> list:
    """The data rows behind one fact, for the evidence drawer: `[{"file", "date", "ticker", "value"}]`, at most `EVIDENCE_LIMIT`.

    `fact_id` is the fact's [T#], the id of its trace row; the row's `inputs.path` says which number it is (`_fact_dates` has the
    paths that have dates; any other fact, an input, a limit, a count, gives `[]`). Rows come in this order: (1) the portfolio's
    value on each of the fact's dates, base 100, read from the Result's own series (`file` = PORTFOLIO_FILE); (2) the largest
    line of that mix, as listed, from the market bundle: `adj_close` in its listing currency on its last real trading row on or
    before each date (the row's own date); (3) when that line is USD-listed, USD/CAD for the last date, dated by the file row the
    rate came from (on a day the file does not list, the row the rate was carried from). A bundle without prices (`local` and
    `traded`) gives the portfolio rows only. Nothing is computed here: the dates are the tools' own (a drawdown's peak and trough,
    the first and last day of the series, a stretch's start and end), the values are what the tools read, and a date after the
    Result's `as_of` is dropped (red gate 3). A row shows what the code read, in the past: no forecast.

    The rows are prices and rates only, never the fictional dollar amount: a dollar loss (○ fiction, ledger section 30) gets the rows
    of its drawdown (● fact). `public=True` gives `[]` without reading the bundle (`market` may be None): the licence of the starter
    prices (red gate 8) forbids a per-asset price in the public demo and in a committed saved run (ledger section 10), so those
    callers ask for the public cut.
    """
    if public:
        return []
    fact = next((t for t in result.get("trace") or [] if isinstance(t, dict) and t.get("id") == fact_id), None)
    side, dates = _fact_dates(_dig(fact, "inputs", "path"), result)
    if not dates:
        return []
    rows = _portfolio_rows(side, dates, result)
    ticker = _largest_line(side, result)
    if ticker and isinstance(market, dict):
        priced = _price_rows(ticker, dates, market)
        rows += priced + (_fx_rows(dates[-1], market) if priced and _usd_listed(ticker, market) else [])
    return rows[:EVIDENCE_LIMIT]


# --- the Proof block inputs (Task P9) -----------------------------------------------------------------
def tally_from_junit(xml_text: str, *, commit, date) -> dict:
    """The test tally of one pytest run, from its `--junitxml` text: the counts, how long it took, which commit and day it was
    recorded on, and whether the look-ahead tests (`LOOKAHEAD_TESTS`, the "scramble the future" proof) passed.

    Counts come from the `testsuite` attributes (`passed` = tests - failures - errors - skipped). A test's node id is its
    `classname` with the dots turned into `/`, then `.py::` and its `name`. `lookahead["passed"]` is False when any of the three
    tests failed or errored, None when one is missing or was skipped (the run does not show the proof either way), else True.
    A tally says how many tests ran green on that commit. It does not say the code is right, and it is not a forecast of anything.
    """
    root = ElementTree.fromstring(xml_text)
    suites = list(root.iter("testsuite"))                     # pytest writes one; the sum also reads several
    total, failed, errors, skipped = (sum(int(s.get(k) or 0) for s in suites) for k in ("tests", "failures", "errors", "skipped"))
    seconds = sum(float(s.get("time") or 0) for s in suites)
    state = {}                                                # node id -> passed | failed | skipped
    for case in root.iter("testcase"):
        kinds = {child.tag for child in case}
        node = f"{(case.get('classname') or '').replace('.', '/')}.py::{case.get('name') or ''}"
        state[node] = "failed" if kinds & {"failure", "error"} else "skipped" if "skipped" in kinds else "passed"
    seen = [state.get(node) for node in LOOKAHEAD_TESTS]
    proof = False if "failed" in seen else None if (None in seen or "skipped" in seen) else True
    return {"passed": total - failed - errors - skipped, "failed": failed, "errors": errors, "skipped": skipped, "total": total,
            "seconds": round(seconds, 2), "commit": commit, "date": date,
            "lookahead": {"name": LOOKAHEAD_NAME, "passed": proof, "tests": list(LOOKAHEAD_TESTS)}}


_USAGE_KEYS = (("inputTokens", "input_tokens"), ("outputTokens", "output_tokens"),
               ("cacheReadInputTokens", "cache_read_input_tokens"), ("cacheWriteInputTokens", "cache_write_input_tokens"))


def _tokens(usage: dict) -> tuple:
    """(input, output, cache read, cache write) tokens of one usage dict; camelCase (Bedrock) or snake_case keys."""
    return tuple(int(usage.get(camel) or usage.get(snake) or 0) for camel, snake in _USAGE_KEYS)


def run_cost(trace) -> dict:
    """The model calls of one run and their cost at published, dated prices.

    Bedrock rows are the trace rows with `service == "Amazon Bedrock"` and a `usage`. usd = the sum over them of
    (input x p_in + output x p_out + cache read x p_in x CACHE_READ_MULT + cache write x p_in x CACHE_WRITE_MULT) / 1e6,
    with (p_in, p_out) = `config.PRICE_USD_PER_MTOK[row["model"]]`, rounded to 6 decimals. usd is None when a row's
    model has no price, or when `config.PRICES_AS_OF` is missing: no undated price claim. An estimate at list price;
    Bedrock bills separately.
    """
    rows = [r for r in trace or [] if r.get("service") == "Amazon Bedrock" and r.get("usage")]
    price_date = getattr(config, "PRICES_AS_OF", None)
    usd = 0.0
    for row in rows:
        price = config.PRICE_USD_PER_MTOK.get(row.get("model"))
        if price is None:
            usd = None
            break
        p_in, p_out = price
        tin, tout, tread, twrite = _tokens(row["usage"])
        usd += (tin * p_in + tout * p_out + tread * p_in * config.CACHE_READ_MULT
                + twrite * p_in * config.CACHE_WRITE_MULT) / 1e6
    if price_date is None:
        usd = None
    return {"calls": len(rows), "usd": None if usd is None else round(usd, 6),
            "price_date": price_date, "price_source": getattr(config, "PRICES_SOURCE", None)}


def _read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def proof_block(result: dict, *, eval_path=EVAL_RESULTS_JSON, tally_path=TEST_TALLY_JSON) -> dict:
    """The Proof block of one run: its receipt, the eval summary (or "eval pending"), the last test tally with the
    look-ahead tests apart, and the run's model calls and cost (`run_cost`).

    receipt = {"verified", "total", "first_try": {"verified", "total"} | None} from `result["receipt"]`, else None.
    eval = the JSON at `eval_path` when it parses and holds n, model, date and arms, else None and eval_note
    "eval pending". tally = the JSON at `tally_path` without its lookahead; lookahead = that lookahead (both None when
    the file is absent or unreadable).
    """
    rec = result.get("receipt")
    receipt = None
    if isinstance(rec, dict):
        first = rec.get("first_try")
        receipt = {"verified": rec.get("verified"), "total": rec.get("total"),
                   "first_try": {"verified": first.get("verified"), "total": first.get("total")}
                   if isinstance(first, dict) else None}
    ev = _read_json(eval_path)
    if not (isinstance(ev, dict) and all(k in ev for k in ("n", "model", "date", "arms"))):
        ev = None
    tally = _read_json(tally_path)
    tally = tally if isinstance(tally, dict) else None
    lookahead = None
    if tally is not None:
        tally = dict(tally)
        lookahead = tally.pop("lookahead", None)
    return {"receipt": receipt, "eval": ev, "eval_note": None if ev is not None else "eval pending",
            "tally": tally, "lookahead": lookahead, "telemetry": run_cost(result.get("trace"))}
