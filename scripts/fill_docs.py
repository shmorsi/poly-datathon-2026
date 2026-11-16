"""Fill the number slots of the docs from the saved runs, so no number in a document is typed by hand (lane D1).

    python scripts/fill_docs.py [--runs DIR] [--eval FILE] [--out DIR] [--final] [FILE ...]

Reads every template docs/templates/<name>.md (or the FILEs named), fills each slot from the saved runs
(data/demo_runs: Robert's default.json and the others' default_<pilot>.json, or --runs DIR) and docs/eval_results.json,
and writes the filled doc to docs/<name>.md, the file a reader opens (its links work from there); the README's template
(docs/templates/README.md) fills the repository's README.md. A FILE outside docs/templates/ is filled in place. --out DIR
writes every filled file to DIR instead.
Nothing is written unless every slot of every file fills: a missing key, a null value, an unknown investor or format,
or any other angle-bracket placeholder left in the text fails the build, naming file:line for each.

The slot grammar (one form; the |FORMAT part is optional), as docs/templates/video_script.md "How the numbers get in"
defines it:
    ⟨run:INVESTOR:PATH|FORMAT⟩   reads <runs>/INVESTOR.json (robert, mateo, amira, canadian)
    ⟨eval:PATH|FORMAT⟩           reads docs/eval_results.json
PATH is keys joined by dots; an all-digit segment indexes a list; `field=value` picks the first list item whose field
equals value as text, and `f=v&g=w` the first item that matches every condition. Two derived roots read a run:
    @fact.LABEL.id | .row | .trace | .sentence | .evidence
        the facts row with that label, its id, the trace row with the same id, the text of the first debrief sentence
        that cites it, and result.evidence[id]; they copy what the run holds and compute nothing.
    @cost.calls | .input | .output | .cache_read | .cache_write | .usd
        the run's Amazon Bedrock calls and their tokens from the trace; usd is the formula of proofs.run_cost (tokens x
        config.PRICE_USD_PER_MTOK, cache reads and writes at config.CACHE_READ_MULT / CACHE_WRITE_MULT): an estimate at
        list price, since Bedrock bills separately.
    @wilson(K_PATH,N_PATH).lo | .hi | .k | .n     (either source)
        the Wilson 95 % interval of k successes in n trials, by the formula of scripts/eval.py (z = 1.96).
FORMATS lists the format codes. `⟨to capture⟩` (AWS evidence that only exists after the live window) is reported and
passes; with --final it fails too. An inline code span is left as written (a doc may show the grammar in one).
"""
import argparse
import json
import math
import re
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INVESTORS = ("robert", "mateo", "amira", "canadian")
SLOT = re.compile(r"⟨(run|eval):([^⟩|]+?)(?:\|([a-z0-9]+))?⟩")
TO_CAPTURE = "⟨to capture⟩"
LEFTOVER = re.compile(r"[⟨⟩]")
CODE_SPAN = re.compile(r"(`[^`\n]*`)")
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
NBSP, MINUS = " ", "−"


class SlotError(Exception):
    """A slot that cannot be filled; the message says why."""


def _q(x, places):
    return Decimal(x).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def _signed(d):
    return f"{MINUS}{abs(d)}" if d < 0 else f"{d}"


def _date(v, need_day=False):
    """(year, month name, day or None) of an ISO date or an ISO month ("2021-11")."""
    parts = str(v)[:10].split("-")
    if len(parts) not in (2, 3) or not all(p.isdigit() for p in parts) or not 1 <= int(parts[1]) <= 12:
        raise SlotError(f"not an ISO date: {v!r}")
    if need_day and len(parts) != 3:
        raise SlotError(f"not a full ISO date: {v!r}")
    return int(parts[0]), MONTHS[int(parts[1]) - 1], int(parts[2]) if len(parts) == 3 else None


FORMATS = {
    "pct": lambda v: f"{_q(abs(Decimal(str(v))) * 100, 1)}{NBSP}%",       # size of a fraction, one decimal: -0.3452 -> 34.5 %
    "pct0": lambda v: f"{_q(abs(Decimal(str(v))) * 100, 0)}{NBSP}%",      # whole percent: 0.09 -> 9 %
    "spct": lambda v: f"{_signed(_q(Decimal(str(v)) * 100, 1))}{NBSP}%",  # signed, U+2212 minus: -0.058 -> −5.8 %
    "usd": lambda v: f"${_q(abs(Decimal(str(v))), 0):,}",                 # size in dollars, to the dollar: $207,146
    "usd2": lambda v: f"${_q(abs(Decimal(str(v))), 2):,}",                # to the cent
    "usd4": lambda v: f"${_q(abs(Decimal(str(v))), 4):,}",                # a fraction of a cent: $0.0189
    "int": lambda v: f"{_q(Decimal(str(v)), 0):,}".replace("-", MINUS),   # whole number: 2522.0 -> 2,522
    "x1": lambda v: _signed(_q(Decimal(str(v)), 1)),                      # one decimal
    "x2": lambda v: _signed(_q(Decimal(str(v)), 2)),                      # two decimals: a guardrail score
    "x4": lambda v: _signed(_q(Decimal(str(v)), 4)),                      # four decimals: an exact p value, 0.0002
    "len": len,                                                           # items in a list or dict
    "year": lambda v: str(_date(v)[0]),                                   # 2025-04-08 -> 2025
    "month": lambda v: "{1} {0}".format(*_date(v)),                       # -> Apr 2025
    "date": lambda v: "{2} {1} {0}".format(*_date(v, need_day=True)),     # -> 8 Apr 2025 (a month alone fails)
}


def _verdict_words(v):
    sys.path.insert(0, str(ROOT))
    import config                                            # the page's own words for each verdict id
    if v not in config.VERDICT_WORDS:
        raise SlotError(f"not a verdict id: {v!r}")
    return config.VERDICT_WORDS[v]


FORMATS["verdict"] = _verdict_words                                      # Incompatible -> Outside your limits
WILSON = re.compile(r"@wilson\(([^,()]+),([^,()]+)\)(?:\.(.+))?$")


def wilson(k, n, z=1.96):
    """{k, n, lo, hi}: the Wilson score interval, the same formula as scripts/eval.py."""
    k, n = int(k), int(n)
    if n <= 0 or not 0 <= k <= n:
        raise SlotError(f"no rate for k={k}, n={n}")
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return {"k": k, "n": n, "lo": max(0.0, centre - half), "hi": min(1.0, centre + half)}


def fmt(value, code):
    """One value written with one format code (None = the value as text)."""
    if code is None:
        return str(value)
    if code not in FORMATS:
        raise SlotError(f"unknown format {code!r} (known: {', '.join(FORMATS)})")
    try:
        return str(FORMATS[code](value))
    except SlotError:
        raise
    except Exception as exc:
        raise SlotError(f"format {code!r} cannot write {value!r} ({type(exc).__name__})") from None


def _matches(item, conditions):
    return isinstance(item, dict) and all(f in item and str(item[f]) == v for f, v in conditions)


def dig(obj, path):
    """The value at PATH: dict keys, list indexes, and `field=value[&field=value]` selectors on lists."""
    for seg in path.split("."):
        if isinstance(obj, list) and seg.isdigit():
            if int(seg) >= len(obj):
                raise SlotError(f"index {seg} is past the end of a list of {len(obj)}")
            obj = obj[int(seg)]
        elif isinstance(obj, list) and "=" in seg:
            conditions = [c.split("=", 1) for c in seg.split("&")]
            if any(len(c) != 2 for c in conditions):
                raise SlotError(f"bad selector {seg!r}")
            obj = next((it for it in obj if _matches(it, conditions)), None)
            if obj is None:
                raise SlotError(f"no list item matches {seg!r}")
        elif isinstance(obj, dict) and seg in obj:
            obj = obj[seg]
        else:
            raise SlotError(f"no key {seg!r}")
    return obj


def _fact_view(run, label):
    """@fact.LABEL: the facts row with that label and what links to it, copied from the run."""
    hits = [(fid, row) for fid, row in (run.get("facts") or {}).items() if isinstance(row, dict) and row.get("label") == label]
    if not hits:
        raise SlotError(f"no facts row labelled {label!r}")
    fid, row = hits[0]
    view = {"id": fid, "row": row}
    trace = next((t for t in run.get("trace") or [] if isinstance(t, dict) and t.get("id") == fid), None)
    if trace is not None:
        view["trace"] = trace
    cited = next((s for s in (run.get("debrief") or {}).get("sentences") or []
                  if isinstance(s, dict) and fid in (s.get("refs") or [])), None)
    if cited is not None:
        view["sentence"] = cited.get("text")
    evidence = (run.get("evidence") or {}).get(fid) if isinstance(run.get("evidence"), dict) else None
    if evidence is not None:
        view["evidence"] = evidence
    return view


def _cost_view(run):
    """@cost: the run's Bedrock calls and tokens, and their list-price cost by the formula of proofs.run_cost."""
    sys.path.insert(0, str(ROOT))
    import config                                            # the prices live in config.py, never in a doc
    rows = [t for t in run.get("trace") or [] if isinstance(t, dict) and t.get("service") == "Amazon Bedrock" and t.get("usage")]
    if not rows:
        raise SlotError("the run has no Amazon Bedrock call in its trace")
    keys = {"input": "inputTokens", "output": "outputTokens", "cache_read": "cacheReadInputTokens",
            "cache_write": "cacheWriteInputTokens"}
    view, usd = {"calls": len(rows), **{k: 0 for k in keys}}, Decimal(0)
    for t in rows:
        if t.get("model") not in config.PRICE_USD_PER_MTOK:
            raise SlotError(f"no list price in config.py for model {t.get('model')!r}")
        p_in, p_out = (Decimal(str(p)) for p in config.PRICE_USD_PER_MTOK[t["model"]])
        n = {k: int(t["usage"].get(v) or 0) for k, v in keys.items()}
        for k in keys:
            view[k] += n[k]
        usd += (n["input"] * p_in + n["output"] * p_out + n["cache_read"] * p_in * Decimal(str(config.CACHE_READ_MULT))
                + n["cache_write"] * p_in * Decimal(str(config.CACHE_WRITE_MULT))) / Decimal(10**6)
    view["usd"] = float(usd)
    return view


def _with(kind, body, path):
    """The slot body that reads PATH from the same source as BODY."""
    return path.strip() if kind == "eval" else f"{body.partition(':')[0]}:{path.strip()}"


def resolve(kind, body, runs, eval_results):
    """The raw value of one slot body."""
    m = WILSON.match(body if kind == "eval" else body.partition(":")[2])
    if m:
        rate = wilson(resolve(kind, _with(kind, body, m.group(1)), runs, eval_results),
                      resolve(kind, _with(kind, body, m.group(2)), runs, eval_results))
        return dig(rate, m.group(3)) if m.group(3) else rate
    if kind == "eval":
        if eval_results is None:
            raise SlotError("docs/eval_results.json was not found")
        return dig(eval_results, body)
    investor, _, path = body.partition(":")
    if investor not in INVESTORS:
        raise SlotError(f"unknown investor {investor!r} (known: {', '.join(INVESTORS)})")
    if investor not in runs:
        raise SlotError(f"no saved run for {investor} (record the final runs, or pass --runs DIR)")
    run = runs[investor]
    if path.startswith("@fact."):
        label, _, rest = path[len("@fact."):].partition(".")
        view = _fact_view(run, label)
        return dig(view, rest) if rest else view
    if path.startswith("@cost"):
        rest = path[len("@cost"):].lstrip(".")
        return dig(_cost_view(run), rest) if rest else _cost_view(run)
    return dig(run, path)


def fill_text(text, runs, eval_results, *, name="text", final=False):
    """(filled text, problems, captures): every slot filled, every problem as 'name:line: slot: why'.

    An inline code span (`...`) is left exactly as written, neither filled nor checked: that is where a doc may show
    the grammar itself. Everything else, fenced blocks included, is filled and checked."""
    problems, captures = [], 0
    out = []
    for n, line in enumerate(text.split("\n"), 1):
        def one(m):
            try:
                value = resolve(m.group(1), m.group(2), runs, eval_results)
                if value is None:
                    raise SlotError("the value is null")
                return fmt(value, m.group(3))
            except SlotError as exc:
                problems.append(f"{name}:{n}: {m.group(0)}: {exc}")
                return m.group(0)
        parts = CODE_SPAN.split(line)                       # odd items are code spans
        for i in range(0, len(parts), 2):
            filled = SLOT.sub(one, parts[i])
            captures += filled.count(TO_CAPTURE)
            if final and TO_CAPTURE in filled:
                problems.append(f"{name}:{n}: evidence still marked to capture (--final)")
            rest = SLOT.sub("", filled.replace(TO_CAPTURE, ""))   # failed slots are already named above
            if LEFTOVER.search(rest):
                problems.append(f"{name}:{n}: a placeholder that is not a slot: {line.strip()[:120]}")
            parts[i] = filled
        out.append("".join(parts))
    return "\n".join(out), problems, captures


def load_runs(runs_dir):
    """{investor: Result}: `<investor>.json` (a bare Result), else the saved run record_demo writes (Robert's own question
    is `default.json`, the others `default_<pilot>.json`; the Result is its "result")."""
    runs = {}
    for investor in INVESTORS:
        for name in (f"{investor}.json", "default.json" if investor == "robert" else f"default_{investor}.json"):
            p = Path(runs_dir) / name
            if p.is_file():
                data = json.loads(p.read_text(encoding="utf-8"))
                runs[investor] = data["result"] if isinstance(data.get("result"), dict) else data
                break
    return runs


TEMPLATES = ROOT / "docs" / "templates"          # the docs with their slots; the filled copies are docs/<name>.md


def default_files():
    return sorted(TEMPLATES.glob("*.md"))


def target(path: Path, out) -> Path:
    """Where a filled file goes: --out DIR if given, else docs/<name>.md for a template, else the file itself."""
    if out is not None:
        return Path(out) / path.name
    if path.resolve().parent == TEMPLATES.resolve():
        return ROOT / "README.md" if path.name == "README.md" else TEMPLATES.parent / path.name
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fill the templates' number slots from the saved runs into docs/<name>.md.")
    ap.add_argument("files", nargs="*", type=Path, help="markdown files (default: every docs/templates/*.md)")
    ap.add_argument("--runs", type=Path, default=ROOT / "data" / "demo_runs", help="folder of <investor>.json Results")
    ap.add_argument("--eval", type=Path, default=ROOT / "docs" / "eval_results.json", help="the eval results JSON")
    ap.add_argument("--out", type=Path, default=None, help="write the filled files here (default: docs/<name>.md for a "
                                                             "template, in place for any other file)")
    ap.add_argument("--final", action="store_true", help="also fail on any evidence still marked to capture")
    args = ap.parse_args(argv)
    runs = load_runs(args.runs)
    eval_results = json.loads(args.eval.read_text(encoding="utf-8")) if args.eval.is_file() else None
    files = args.files or default_files()
    built, problems, captures = {}, [], 0
    for f in files:
        text, bad, cap = fill_text(f.read_text(encoding="utf-8"), runs, eval_results, name=f.name, final=args.final)
        built[target(f, args.out)], captures = text, captures + cap
        problems += bad
    if problems:
        print(f"fill_docs: {len(problems)} slot(s) did not fill; nothing was written.", file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        return 1
    for path, text in built.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    where = sorted({str(p.parent) for p in built})
    print(f"fill_docs: {len(built)} file(s) written to {', '.join(where)}; runs: {', '.join(sorted(runs)) or 'none'}; "
          f"evidence still to capture: {captures}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
