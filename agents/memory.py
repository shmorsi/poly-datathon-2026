"""The named-defect memory (the organizers' technical workshop, level 10; plan B Task 9b).

The checkers name each defect of a debrief (verify.py, the receipt; agents.explainer's structural lines). This file
keeps how many runs made each TYPE of defect, and the next debrief opens with "Earlier runs made these mistakes:
{types}. Do not repeat them." ("it improves without guaranteeing": B Task 11 measures it before it is a default).

What the file can hold (red gate 6): counts of defect TYPES from the closed list DEFECT_TYPES, never a sentence, a
number from a debrief, a question or a name. `record` drops anything else; `load` re-checks the file, so a hand-edited
memory cannot put text into a prompt. The file keeps every type's count (so at most the 15 of DEFECT_TYPES): a new
defect keeps counting and can pass an old one. `load`, and so the prompt, names at most MAX_TYPES types (the most
frequent; a tie goes to the latest seen).
The write is atomic (a temporary file in the same folder, then os.replace) and a failed write keeps the old memory:
the memory never breaks a run. The caller chooses the path (a local, gitignored place).
"""
import json
import os
import re
import tempfile
import threading
from pathlib import Path

DEFECT_TYPES = (
    "unverified_number",      # a number no cited row holds (receipt)
    "wrong_entity",           # the row's entity is not named in the sentence (receipt)
    "wrong_kind",             # a sentence kind that may not cite that row (receipt)
    "wrong_side",             # today vs after crossed (receipt)
    "wrong_direction",        # "fell" on a rising row, or the reverse (receipt)
    "advice",                 # buy / sell / hold as an instruction / should / recommend / a forecast (both checkers)
    "future_date",            # something dated after as_of (receipt)
    "spelled_number",         # "half", "ten percent": numbers are written in digits (receipt)
    "unknown_ref",            # a [T#] that is not in the facts (receipt)
    "verdict_words",          # the verdict sentence does not use the exact verdict words (both checkers)
    "missing_failed_limit",   # a failed limit the debrief does not name (receipt)
    "missing_caveat_phrase",  # a caveat phrase the debrief must say (receipt)
    "missing_section",        # one of the four questions is not answered (both checkers)
    "missing_limits_phrase",  # "this already happened; it is not a forecast" not said (explainer)
    "too_long",               # over the word budget (explainer)
)
MAX_TYPES = 5
# Ruling R36 (d): the memory line names each type's plain rule, not only its identifier ("wrong_kind" alone taught
# nothing: first try with it stayed 0 / 12). Static text written here, never words from a run (red gate 6).
PLAIN_RULES = {
    "unverified_number": "every number is the value of a row the sentence cites",
    "wrong_entity": "a sentence names what each cited row is about, and a limit's name comes right before its number "
                    "(\"your floor of\", \"the shock limit of\")",
    "wrong_kind": "a sentence that cites a limit is an assumption and one that cites the fictional amount or the move "
                  "is a scenario, never a fact",
    "wrong_side": "a number about the portfolio after the move says \"after the move\", one about today says \"today\"",
    "wrong_direction": "a negative row fell or lost, a positive row rose or gained",
    "advice": "no buy, sell, hold, should, recommend, forecast or suggestion to act (\"consider holding\")",
    "future_date": "nothing dated after the decision date",
    "spelled_number": "every number in digits, never in words",
    "unknown_ref": "cite only the facts given",
    "verdict_words": "the verdict sentence starts with the exact verdict words",
    "missing_failed_limit": "name every rule of the Failed rules line",
    "missing_caveat_phrase": "say each caveat in exactly its words",
    "missing_section": "answer all four questions",
    "missing_limits_phrase": "say \"This already happened; it is not a forecast.\"",
    "too_long": "at most 180 words",
}
_LOCK = threading.Lock()                 # one writer at a time in this process; os.replace keeps the file whole


def _ranked(path) -> list:
    """[(type, count)] for EVERY type the file holds (most frequent first, a tie: the latest seen first), checked
    again: unknown names, non-integer or non-positive counts are dropped. A missing, broken or deeply nested file, or
    a path that is not a path (None from an unset setting), is an empty memory."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, RecursionError):
        return []
    counts = data.get("counts") if isinstance(data, dict) else None
    if not isinstance(counts, dict):
        return []
    rows = [(t, c) for t, c in counts.items()
            if t in DEFECT_TYPES and isinstance(c, int) and not isinstance(c, bool) and c > 0]
    return sorted(rows, key=lambda row: -row[1])                      # stable: the file's order breaks ties


def load(path) -> list[str]:
    """The remembered defect types for the prompt, most frequent first: at most MAX_TYPES (the file keeps them all).
    Never raises."""
    return [t for t, _ in _ranked(path)][:MAX_TYPES]


def record(path, defect_types) -> list[str]:
    """Count one more run for each defect type named (once per run, whatever the repeats); anything that is not one
    of DEFECT_TYPES is dropped, never written. Returns the memory as it now stands (as `load`). With nothing to add,
    or when the write fails (a path that is not a path included), the file is left as it was. Every type's count is
    kept (the closed list bounds the file at 15 entries); only the answer is capped at MAX_TYPES. Never raises."""
    try:
        named = list(defect_types or [])
    except TypeError:
        named = []
    fresh = list(dict.fromkeys(t for t in named if isinstance(t, str) and t in DEFECT_TYPES))
    if not fresh:
        return load(path)
    with _LOCK:
        old = dict(_ranked(path))
        rows = [(t, old.get(t, 0) + 1) for t in fresh] + [(t, c) for t, c in old.items() if t not in fresh]
        rows = sorted(rows, key=lambda row: -row[1])                  # stable: this run's types win a tie
        try:
            _write(Path(path), {"counts": dict(rows)})
        except (OSError, TypeError, ValueError):
            return list(old)[:MAX_TYPES]
    return [t for t, _ in rows][:MAX_TYPES]


def _write(path: Path, data: dict) -> None:
    """Atomic: a temporary file next to the target, flushed to disk, then os.replace; the temporary file never stays."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# The receipt's buckets (verify.verify_numbers, ledger section 30) -> types, in this order.
_BUCKETS = (("unverified", "unverified_number"), ("wrong_entity", "wrong_entity"), ("wrong_kind", "wrong_kind"),
            ("wrong_side", "wrong_side"), ("wrong_direction", "wrong_direction"), ("advice", "advice"),
            ("future_refs", "future_date"))
# The checkers' fixed defect sentences -> types: the receipt's `missing` and `defects` lines, then the explainer's
# structural lines (agents.explainer._defects). Only the code-written shape is read, never the quoted words.
_LINES = (
    (re.compile(r"^The verdict must read "), "verdict_words"),
    (re.compile(r"^The debrief does not name the failed limit "), "missing_failed_limit"),
    (re.compile(r"^The debrief must say "), "missing_caveat_phrase"),
    (re.compile(r"^The section “[^”]*” is missing\."), "missing_section"),
    (re.compile(r"^Sentence \d+ spells out a number "), "spelled_number"),
    (re.compile(r"^Sentence \d+ cites T\d+, which is not in the facts\."), "unknown_ref"),
    (re.compile(r"^Sentence \d+ refers to something dated after "), "future_date"),
    (re.compile(r"^Sentence \d+ gives advice or a forecast "), "advice"),
    (re.compile(r"^The section 'What limits\?' must say "), "missing_limits_phrase"),
    (re.compile(r"^The section '[^']*' is missing\.$"), "missing_section"),
    (re.compile(r"^Sentence \d+ uses the words? '"), "advice"),
    (re.compile(r"^The debrief has \d+ words; "), "too_long"),
    (re.compile(r"^The verdict sentence must start with "), "verdict_words"),
    # the receipt's number lines (verify._number_line; ruling R36 d): without them a draft's entity and kind defects
    # never reached the eval's types
    (re.compile(r"^Sentence \d+ cites T\d+ for .+ but does not name "), "wrong_entity"),
    (re.compile(r"^Sentence \d+ is marked \w+ but cites T\d+, which is "), "wrong_kind"),
    (re.compile(r"^Sentence \d+ is about (?:today|the portfolio after the move) but "), "wrong_side"),
    (re.compile(r"^Sentence \d+ says the value (?:rose|fell) but "), "wrong_direction"),
    (re.compile(r"^Sentence \d+ says .+(?: and cites T\d+, whose value is | but cites no \[T#\]|, but none of )"),
     "unverified_number"),
)


def types_from(receipt=None, defects=None) -> list[str]:
    """The defect types of one debrief, each once, in a fixed order: the receipt's non-empty buckets, then its
    `missing` and `defects` lines, then the explainer's structural `defects` lines. A line of any other shape is not
    a type and is left out."""
    receipt = receipt if isinstance(receipt, dict) else {}
    found = [kind for key, kind in _BUCKETS if receipt.get(key)]
    lines = list(receipt.get("missing") or []) + list(receipt.get("defects") or []) + list(defects or [])
    for line in lines:
        found += [kind for rx, kind in _LINES if isinstance(line, str) and rx.search(line)][:1]
    return list(dict.fromkeys(found))
