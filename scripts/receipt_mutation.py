"""How much does the receipt catch? (board resolution 4, spec 24; plan D Task 1b)

    python scripts/receipt_mutation.py [--out docs/receipt_mutation.md]

Starts from one clean debrief that the receipt (verify.py) passes with no defect, injects ONE defect per copy (direction
flips, today/after swaps, number nudges of 0.1 pp / 1 / 10 %, spelled-out numbers, advice and forecast insertions, dropped
[T#]), and counts the copies on which verify_numbers names a defect for the changed sentence. The recall k / N of each class
comes with a Wilson 95 % interval. Benign rewrites of the same debrief give the false-alarm rate. A second table lists what
the receipt does not check on purpose (causal and invented qualitative claims, advice wording outside its list).

Deterministic: fixed seed, no clock, no network, no model; the output is byte-identical on every run for the same verify.py.
The date in the table is the constant MEASURED_ON (set it by hand when you regenerate), and every rate carries its evidence
level from its own N (the docs rule). The classes and the clean debrief are chosen by the author, so the recall
describes the receipt on these injected defects, not on a model's real mistakes (those are measured by the eval)."""
import argparse
import contextlib
import math
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:      # `python scripts/receipt_mutation.py` puts scripts/, not the repo root, first
    sys.path.insert(0, ROOT.as_posix())

import verify  # noqa: E402

SEED = 20261114
OUT = ROOT / "docs" / "receipt_mutation.md"
AS_OF = "2026-11-12"
MEASURED_ON = "2026-11-14"        # the day the published table was generated; the script has no clock, so set it by hand
MEASURED_FROM_N = 30              # the docs rule: Measured when N >= 30, Indicative below


def evidence(n):
    """The evidence level of a rate measured on n cases: Measured from 30, Indicative below."""
    return "Measured" if n >= MEASURED_FROM_N else "Indicative"


def wilson(k, n, z=1.96):
    """(low, high) of the Wilson score interval for k successes in n trials."""
    if n == 0:
        return 0.0, 1.0
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def _row(label, value, unit, entity, kind):
    sign = "negative" if value < 0 else "positive" if value > 0 else "zero"
    return dict(label=label, value=value, unit=unit, entity=entity, sign=sign, kind=kind)


FACTS = {"T1": _row("Fictional amount", 600000, "CAD", "your amount", "fiction"),
         "T3": _row("Your floor", -0.15, "pct", "your floor", "assumption"),
         "T4": _row("What you said you could absorb", -90000, "CAD", "your floor", "assumption"),
         "T6": _row("The move: NVDA set to", 0.40, "pct", "NVDA", "fiction"),
         "T9": _row("Worst drop today", -0.106, "pct", "today", "fact"),
         "T10": _row("Worst drop after the move", -0.345, "pct", "after", "fact"),
         "T11": _row("Dollar loss at the worst drop after the move", -207000.4, "CAD", "after", "fact"),
         "T14": _row("Growth per year today", 0.087, "pct", "today", "fact"),
         "T15": _row("Growth per year after the move", 0.252, "pct", "after", "fact"),
         "T16": _row("Worst clean tariff shock after the move", -0.0905, "pct", "tariffs", "fact"),
         "T17": _row("Shock limit (half your floor)", -0.075, "pct", "shock check", "assumption"),
         "T19": _row("Largest NVDA size inside your limits in this history", 0.08, "pct", "NVDA", "fact"),
         "T20": _row("Clean tariff shocks known", 4, "count", "tariffs", "fact"),
         "T23": _row("Days to recover today", 487, "days", "today", "fact")}
RESULT = {"as_of": AS_OF, "verdict": "Incompatible", "events": [],
          "checks": [{"rule": "max_drawdown", "tier": "hard", "status": "fail", "value": -0.345, "limit": -0.15}]}
VERDICT = ("Outside your limits: with 40 % [T6] in NVIDIA, the portfolio after the move fell 34.5 % [T10], "
           "past your floor of 15 % [T3].")
SENTENCES = [  # (section, kind, text); the receipt numbers them 2.. after the verdict sentence
    ("data", "fact", "Today your portfolio fell at most 10.6 % [T9] and took 487 days [T23] to recover."),
    ("data", "fact", "After the move the portfolio fell 34.5 % [T10], a loss of $207,000 [T11]."),
    ("data", "fact", "Today the portfolio grew 8.7 % [T14] a year, and after the move it grew 25.2 % [T15] a year."),
    ("why", "assumption", "Your floor is 15 % [T3], the $90,000 [T4] set as your limit (assumed for this fictional profile)."),
    ("why", "assumption", "The worst clean tariff shock after the move cost 9.1 % [T16], past the shock limit of 7.5 % [T17]."),
    ("limits", "limit", "This already happened; it is not a forecast."),
    ("limits", "limit", "The shock check rests on 4 clean tariff shocks [T20], so read it as measured on few episodes."),
    ("would_change", "scenario", "In this history your floor breaks above 8 % [T19] NVIDIA, on a fictional amount of $600,000 [T1].")]


def build(sentences=SENTENCES, verdict=VERDICT):
    sections = {}
    for k, (name, _, _) in enumerate(sentences):
        sections.setdefault(name, []).append(k)
    return {"verdict_sentence": verdict, "sections": sections,
            "sentences": [{"text": t, "kind": kind, "refs": []} for _, kind, t in sentences]}


def check(sentences=SENTENCES, verdict=VERDICT):
    return verify.verify_numbers(build(sentences, verdict), FACTS, as_of=AS_OF, result=RESULT)


# ---- mutations: every record is one defect injected into one sentence of the clean debrief --------------------------
TEXTS = [VERDICT] + [t for _, _, t in SENTENCES]          # index 0 = the verdict sentence (receipt sentence 1)
_TAG = r"\[T\d+(?:\s*[,;]\s*T\d+)*\]"
_NUM = re.compile(rf"{_TAG}|(?P<num>\$?\d[\d,]*(?:\.\d+)?)(?P<unit>\s?%|\s?days)?")


def _record(cls, label, texts, target):
    return {"class": cls, "label": label, "texts": texts, "target": target + 1}      # target: receipt sentence number


def _with(i, text):
    texts = list(TEXTS)
    texts[i] = text
    return texts


def _replace_at(text, start, end, new):
    return text[:start] + new + text[end:]


FLIPS = {"fell": ["rose", "gained", "grew", "climbed", "increased", "jumped"],
         "grew": ["fell", "lost", "dropped", "declined", "shrank", "slid"],
         "a loss of": ["a gain of", "a rise of", "an increase of"],
         "cost": ["gained", "earned"]}


def direction_flips():
    out = []
    for i, text in enumerate(TEXTS):
        for word, others in FLIPS.items():
            for m in re.finditer(rf"\b{word}\b", text):
                out += [_record("direction flip", f"{word} -> {new}", _with(i, _replace_at(text, m.start(), m.end(), new)), i)
                        for new in others]
    return out


SWAPS = [  # (text index, old, new, label)
    (1, "Today your portfolio fell", "After the move your portfolio fell", "today -> after the move (sentence 2)"),
    (1, "Today your portfolio fell", "With the move your portfolio fell", "today -> with the move (sentence 2)"),
    (2, "After the move the portfolio fell", "Today the portfolio fell", "after the move -> today (sentence 3)"),
    (2, "After the move the portfolio fell", "As it is the portfolio fell", "after the move -> as it is (sentence 3)"),
    (0, "the portfolio after the move fell", "today's portfolio fell", "after the move -> today's (verdict)"),
    (3, "Today the portfolio grew", "After the move the portfolio grew", "today -> after the move (sentence 4)"),
    (3, "after the move it grew", "today it grew", "after the move -> today (sentence 4)"),
    (1, "[T9]", "[T10]", "cite today's row -> the move's row (sentence 2)"),
    (2, "[T10]", "[T9]", "cite the move's row -> today's row (sentence 3)"),
    (3, "[T14]", "[T15]", "cite today's growth -> the move's (sentence 4)"),
    (3, "[T15]", "[T14]", "cite the move's growth -> today's (sentence 4)"),
    (1, "fell at most 10.6 % [T9]", "fell 34.5 % [T10] after rates rose", "today's sentence carries the move's number (juror)"),
    (3, "grew 8.7 % [T14] a year, and after the move it grew 25.2 % [T15]",
     "grew 25.2 % [T15] a year, and after the move it grew 8.7 % [T14]", "the two growth numbers trade clauses"),
    (3, "grew 8.7 % [T14] a year, and after the move it grew 25.2 % [T15]",
     "grew 25.2 % [T14] a year, and after the move it grew 8.7 % [T15]", "the two growth numbers trade places, cites stay"),
    (8, "NVIDIA", "Tesla", "NVIDIA -> Tesla (sentence 9)"),
    (0, "in NVIDIA", "in Tesla", "NVIDIA -> Tesla (verdict)"),
    (5, "tariff shock", "oil shock", "tariff -> oil (sentence 6)"),
    (7, "tariff shocks", "oil shocks", "tariff -> oil (sentence 8)"),
    (5, "after the move cost", "today cost", "after the move -> today on the shock row"),
]


def entity_swaps():
    out = []
    for i, old, new, label in SWAPS:
        assert old in TEXTS[i], (i, old)
        out.append(_record("entity swap", label, _with(i, TEXTS[i].replace(old, new, 1)), i))
    return out


def _write(value, decimals, unit, dollar):
    body = f"{value:,.{decimals}f}"
    return f"${body}" if dollar else body + (unit or "")


def number_nudges():
    """Every number of the clean debrief moved by the smallest step the reader could miss (0.1 pp, $1, 1 day, 1) and by
    10 % of itself."""
    out = []
    for i, text in enumerate(TEXTS):
        for m in _NUM.finditer(text):
            if not m["num"]:
                continue
            raw, unit = m["num"], m["unit"] or ""
            dollar, value = raw.startswith("$"), float(raw.lstrip("$").replace(",", ""))
            decimals = len(raw.split(".")[1]) if "." in raw else 0
            small = 0.1 if "%" in unit else 1.0
            steps = [("%+.1f pp" % s if "%" in unit else "%+g" % s, value + s) for s in (small, -small)]
            for pct, factor in (("+10 %", 1.1), ("-10 %", 0.9)):
                steps.append((pct, value * factor))
            for label, new in steps:
                d = max(decimals, 1) if "%" in unit else decimals
                written = _write(new, d, unit, dollar)
                if written != m.group(0):
                    out.append(_record("number nudge", f"{m.group(0).strip()} {label}", _with(i, _replace_at(text, m.start(), m.end(), written)), i))
    return out


SPELLED = {"40 %": ["forty percent", "about forty per cent"], "34.5 %": ["about a third", "thirty-four and a half percent"],
           "15 %": ["fifteen percent", "fifteen per cent"], "10.6 %": ["about eleven percent", "ten point six percent"],
           "487 days": ["four hundred and eighty-seven days"], "$207,000": ["two hundred and seven thousand dollars"],
           "8.7 %": ["about nine percent"], "25.2 %": ["about a quarter", "twenty-five percent"],
           "$90,000": ["ninety thousand dollars"], "9.1 %": ["about nine percent"],
           "7.5 %": ["seven and a half percent"], "8 %": ["eight percent"], "$600,000": ["six hundred thousand dollars"]}


def spelled_numbers():
    out = []
    for i, text in enumerate(TEXTS):
        for token, forms in SPELLED.items():
            at = text.find(token)
            if at >= 0:
                out += [_record("spelled-out number", f"{token} -> {form}", _with(i, _replace_at(text, at, at + len(token), form)), i)
                        for form in forms]
    return out


ADVICE = ["so you should keep it smaller", "and we recommend a smaller size", "so consider selling part of it",
          "so buy XBB instead", "so hold on to it", "so cut it to a smaller size", "and it will fall again",
          "and it will rise again next year", "and it will cost more", "and we expect a recovery",
          "and this plan is unsuitable for you", "so you should not hold it",
          "and we do not recommend it", "so it is not recommended", "and it is never recommended"]   # negated verb forms (fix round 1)


def advice_insertions(rng):
    out = []
    for phrase in ADVICE:
        for i in sorted(rng.sample(range(5), 2)):                  # two of: the verdict and one sentence of each section
            idx = (0, 1, 5, 6, 8)[i]
            out.append(_record("advice or forecast", f"+ \"{phrase}\" (sentence {idx + 1})", _with(idx, TEXTS[idx][:-1] + ", " + phrase + "."), idx))
    return out


# Spec ruling R1 (Sun Nov 15): "safe", "fits", "allowed", "you can", "holds ... up to" and "you said you could absorb"
# are named defects now ("safe for a retiree" was a stated gap of the invented-claim class until then).
UNQUALIFIED = [(2, " and safe for a retiree"), (1, " and the mix fits your limits"), (5, ", the most your profile allowed"),
               (8, ", and you can go up to it")]


def unqualified_claims():
    return [_record("unqualified claim (R1)", f"+ \"{p.strip(' ,')}\" (sentence {i + 1})", _with(i, TEXTS[i][:-1] + p + "."), i)
            for i, p in UNQUALIFIED]


def dropped_tags():
    out = []
    for i, text in enumerate(TEXTS):
        for m in re.finditer(r"\s?" + _TAG, text):
            out.append(_record("dropped [T#]", f"- {m.group(0).strip()} (sentence {i + 1})", _with(i, _replace_at(text, m.start(), m.end(), "")), i))
    return out


# ---- what the receipt does not check on purpose (reported, never hidden) -----------------------------------------
GAPS = {
    "causal claim, no new number": [(1, ", because the Fed raised rates"), (2, ", caused by inflation"), (4, ", which proves the plan is risky"),
                                    (5, ", driven by the chip ban"), (8, ", as bond yields climbed")],
    "invented qualitative claim": [(1, " and the mix is well diversified"),
                                   (4, " and the company is the best in its sector"), (8, " and every bank stock is steadier")],
    "direction word outside the list": [(1, "fell", "bounced"), (1, "fell", "improved"), (2, "fell", "recovered"),
                                        (3, "grew 8.7", "slipped 8.7"), (3, "it grew", "it eased"), (5, "cost", "added")],
    "advice wording outside the list": [(1, ", so reduce NVIDIA"), (2, ", so trim it"), (4, ", so switch to a bond fund"),
                                        (5, ", so avoid NVIDIA"), (8, ", so add more bonds"), (1, " and prices are likely to bounce back")],
}


def known_gaps():
    out = []
    for cls, edits in GAPS.items():
        for edit in edits:
            idx = edit[0]
            if len(edit) == 3:                                     # (index, old, new): a word swapped for one the receipt does not read
                out.append(_record(cls, f"{edit[1]} -> {edit[2]} (sentence {idx + 1})", _with(idx, TEXTS[idx].replace(edit[1], edit[2], 1)), idx))
            else:
                out.append(_record(cls, f"+ \"{edit[1].strip(' ,')}\" (sentence {idx + 1})", _with(idx, TEXTS[idx][:-1] + edit[1] + "."), idx))
    return out


# ---- benign rewrites: the same facts said another way; the receipt must not complain --------------------------------
BENIGN = [(1, "fell at most", "dropped at most"), (1, "fell at most", "lost at most"), (1, "fell at most", "was down at most"),
          (1, "fell at most", "fell roughly"), (2, "fell 34.5 %", "dropped 34.5 %"), (2, "fell 34.5 %", "was down 34.5 %"),
          (2, "a loss of", "a fall of"), (2, "a loss of", "a drop of"), (3, "grew 8.7 %", "gained 8.7 %"),
          (3, "it grew 25.2 %", "it rose 25.2 %"), (3, "it grew 25.2 %", "it was up 25.2 %"), (3, "it grew 25.2 %", "it climbed 25.2 %"),
          (1, "Today your portfolio", "Your portfolio today"), (1, "Today your portfolio", "As it is, your portfolio"),
          (2, "After the move the portfolio", "With the move the portfolio"), (3, "after the move it grew", "with the move it grew"),
          (1, "Today your portfolio", "In this history, today your portfolio"), (5, "cost 9.1 %", "fell 9.1 %"),
          (5, "past the shock limit", "beyond the shock limit"), (7, "4 clean tariff shocks", "four clean tariff shocks"),
          (6, "it is not a forecast.", "it is not a forecast and not a recommendation."),
          (4, "the $90,000 [T4] set as your limit", "the $90,000 [T4] that was set as your limit"),
          (0, "with 40 % [T6] in NVIDIA, ", ""), (2, "the portfolio fell 34.5 %", "your mix fell 34.5 %"),
          (8, "In this history your floor breaks above", "In this history your floor is crossed above")]


def benign_rewrites():
    out = []
    for i, old, new in BENIGN:
        assert old in TEXTS[i], (i, old)
        out.append(_record("benign rewrite", f"{old} -> {new or '(removed)'}", _with(i, TEXTS[i].replace(old, new, 1)), i))
    out.append(_record("benign rewrite", "a Fictional illustration label sentence is added", TEXTS + ["Fictional illustration, not a recommendation."], len(TEXTS)))
    out.append(_record("benign rewrite", "the two data sentences swap places", [TEXTS[0], TEXTS[2], TEXTS[1]] + TEXTS[3:], 1))
    return out


# ---- running the receipt over them -----------------------------------------------------------------------------------
IN_SCOPE = ("direction flip", "entity swap", "number nudge", "spelled-out number", "advice or forecast", "dropped [T#]",
            "unqualified claim (R1)")
RULES = (("says the value", "direction word against the row's sign"), ("is about today but", "today / after side"),
         ("is about the portfolio after the move but", "today / after side"), ("does not name", "entity not named"),
         ("spells out", "spelled-out number"), ("gives advice", "advice or forecast word"), ("cites no [T#]", "number without a [T#]"),
         ("whose value is", "number differs from the cited row"), ("none of", "number differs from the cited rows"),
         ("is marked", "kind of the row"), ("not in the facts", "unknown [T#]"),
         ("in the past tense", "unqualified or present-tense claim (R1)"))


def run_receipt(texts):
    sentences = [(sec, kind, t) for (sec, kind, _), t in zip(SENTENCES, texts[1:])]
    sentences += [("limits", "limit", t) for t in texts[1 + len(SENTENCES):]]
    return check(sentences, texts[0])


def judge(rec):
    """(caught, rule): did the receipt name a defect for the changed sentence, and which rule said it first."""
    lines = [d for d in run_receipt(rec["texts"])["defects"] if d.startswith(f"Sentence {rec['target']} ")]
    for line in lines:
        for marker, name in RULES:
            if marker in line:
                return True, name
    return bool(lines), "other"


def evaluate(records):
    """{class: {n, k, rule counts, misses}} in the order the classes first appear."""
    out = {}
    for rec in records:
        got, rule = judge(rec)
        row = out.setdefault(rec["class"], {"n": 0, "k": 0, "rules": {}, "misses": []})
        row["n"] += 1
        row["k"] += got
        if got:
            row["rules"][rule] = row["rules"].get(rule, 0) + 1
        else:
            row["misses"].append(rec["label"])
    return out


def false_alarms(records):
    flagged = [rec["label"] for rec in records if run_receipt(rec["texts"])["defects"]]
    return {"n": len(records), "k": len(flagged), "flagged": flagged}


MEANING_RULES = {"direction": ("_bad_direction", lambda *a, **k: False), "side": ("_side_of_row", lambda row: None),
                 "advice": ("_advice", lambda text: [])}


@contextlib.contextmanager
def meaning_rules_off():
    """The same receipt with the three meaning rules (direction, side, advice) switched off: what a number-only check says."""
    saved = {name: getattr(verify, attr) for name, (attr, _) in MEANING_RULES.items()}
    try:
        for attr, off in MEANING_RULES.values():
            setattr(verify, attr, off)
        yield
    finally:
        for name, (attr, _) in MEANING_RULES.items():
            setattr(verify, attr, saved[name])


def collect(seed=SEED):
    rng = random.Random(seed)
    clean = check()
    if clean["defects"]:                                     # a clean receipt is `defects == []` (spec 24 resolution 7)
        raise SystemExit("the clean debrief must pass the receipt: " + "; ".join(clean["defects"]))
    mutated = (direction_flips() + entity_swaps() + number_nudges() + spelled_numbers() + advice_insertions(rng) + dropped_tags()
               + unqualified_claims())
    with meaning_rules_off():
        number_only = evaluate(mutated)
    return {"clean": clean, "in_scope": evaluate(mutated), "number_only": number_only, "gaps": evaluate(known_gaps()),
            "benign": false_alarms(benign_rewrites())}


# ---- the published table -----------------------------------------------------------------------------------------------
def _pct(x):
    return f"{100 * x:.1f} %"


def _interval(k, n):
    lo, hi = wilson(k, n)
    return f"{_pct(lo)} to {_pct(hi)}"


def _table(rows, last=None):
    lines = ["| Class | N | Caught (k) | Recall k / N | Wilson 95 % interval | Evidence | Caught by |", "|---|---:|---:|---:|---|---|---|"]
    for name, v in rows.items():
        by = ", ".join(f"{rule} ({c})" for rule, c in sorted(v["rules"].items(), key=lambda kv: (-kv[1], kv[0]))) or "nothing"
        lines.append(f"| {name} | {v['n']} | {v['k']} | {_pct(v['k'] / v['n'])} | {_interval(v['k'], v['n'])} | {evidence(v['n'])} | {by} |")
    if last:
        lines.append(last)
    return lines


def _limit(text):
    """The one-line limit under a table (the docs rule): a blank line, then one line that starts with Limit."""
    return ["", f"**Limit.** {text}"]


def render(data):
    inn, gaps, benign = data["in_scope"], data["gaps"], data["benign"]
    n, k = sum(v["n"] for v in inn.values()), sum(v["k"] for v in inn.values())
    least = min(v["n"] for v in inn.values())
    clean = data["clean"]
    misses = [f"- {cls}: {label}" for cls, v in inn.items() for label in v["misses"]]
    out = ["# Receipt mutation test",
           "",
           "Generated by `python scripts/receipt_mutation.py` (seed %d; no clock, no network, no model). Do not edit by hand: "
           "`tests/test_verify.py` fails when this file no longer matches the receipt." % SEED,
           "",
           "- Model: none, deterministic code",
           f"- Measured on: {MEASURED_ON}",
           f"- Evidence level: Measured when N is {MEASURED_FROM_N} or more, Indicative when N is below {MEASURED_FROM_N}; "
           "the Evidence column follows each row's own N",
           "",
           "**What it measures.** One clean debrief passes the receipt (`verify.py`) with no defect (%d of %d numbers traced). "
           "Each copy below has exactly one defect injected into one sentence; a copy counts as caught when `verify_numbers` "
           "names a defect for that sentence. Recall is k / N with a Wilson 95 %% interval. The false-alarm row rewrites the "
           "same debrief in other words and counts the copies the receipt wrongly flags." % (clean["verified"], clean["total"]),
           "",
           "**The clean debrief** (facts rows shaped as `pipeline.build_facts` builds them):",
           "",
           "```text", *(f"{i}. {t}" for i, t in enumerate(TEXTS, 1)), "```",
           "",
           "## Recall on injected defects", ""]
    out += _table(inn, f"| **All seven classes** | {n} | {k} | {_pct(k / n)} | {_interval(k, n)} | {evidence(n)} | |")
    out += _limit("The defects are injected by the author, who knows the rules: this is a regression table for the receipt, "
                  "not a measure of how often a model's real drafts go wrong.")
    out += ["", "## What the three meaning rules add", "",
            "The same seven classes with the direction, side and advice rules switched off (a receipt that checks numbers, "
            "units, entities and kinds only), against the full receipt:", "",
            "| Class | N | Number-only receipt k / N | Wilson 95 % interval | Full receipt k / N | Wilson 95 % interval | Evidence |",
            "|---|---:|---:|---|---:|---|---|"]
    for name, v in inn.items():
        nok = data["number_only"][name]["k"]
        out.append(f"| {name} | {v['n']} | {nok} / {v['n']} | {_interval(nok, v['n'])} | {v['k']} / {v['n']} | "
                   f"{_interval(v['k'], v['n'])} | {evidence(v['n'])} |")
    nk = sum(v["k"] for v in data["number_only"].values())
    out.append(f"| **All seven classes** | {n} | {nk} / {n} | {_interval(nk, n)} | {k} / {n} | {_interval(k, n)} | {evidence(n)} |")
    out += _limit("The number-only column is this same `verify.py` with its direction, side and advice functions switched off, "
                  "not another product, run on the author's own copies.")
    out += ["", "## False alarms on benign rewrites", "",
            "| Rewrites | Wrongly flagged (k) | False-alarm rate k / N | Wilson 95 % interval | Evidence |", "|---:|---:|---:|---|---|",
            f"| {benign['n']} | {benign['k']} | {_pct(benign['k'] / benign['n'])} | {_interval(benign['k'], benign['n'])} | "
            f"{evidence(benign['n'])} |"]
    out += _limit(f"{benign['n']} rewrites chosen by the author: {benign['k']} flagged still allows a true false-alarm rate up to "
                  f"{_pct(wilson(benign['k'], benign['n'])[1])} on other wording.")
    out += ["", "Rewrites: synonyms of the direction words, \"Today\" / \"As it is\" / \"With the move\", a Fictional-illustration "
            "label, \"not a recommendation\", \"sell-off\"-style prose, \"four\" for 4 before a counted noun, reordered sentences."
            if not benign["flagged"] else "Flagged: " + "; ".join(benign["flagged"]),
            "", "## What the receipt does not check (known gaps, measured the same way)", ""]
    out += _table(gaps)
    out += _limit(f"N is {min(v['n'] for v in gaps.values())} to {max(v['n'] for v in gaps.values())} per row, and 0 / N means the "
                  "receipt does not read this wording, by design; it says nothing about how often real drafts use it.")
    out += ["", "A causal or qualitative claim carries no number, so the receipt has nothing to trace; only the output "
            "guardrail's grounding score (when it ran) looks at it. A direction or advice word outside the receipt's lists "
            "passes: the lists are in `verify.py` (`_V_UP`, `_V_DOWN`, `_N_UP`, `_N_DOWN`, `_ADVICE_WORDS`, `_HOLD`, `_CUT_TO`).",
            "", "## Reading this table", "",
            "- The eval (`docs/eval_results.md`, receipt section) reports how often a model's real drafts pass the receipt; this table does not.",
            f"- N = {n} in the seven classes; the pooled row is partly by construction, read the classes. A class with all N caught "
            f"still has a Wilson lower bound below 100 %: with N = {least} the lower bound is {_pct(wilson(least, least)[0])}.",
            "- First run of this harness: direction flips 34 / 35 (\"cost\" to \"earned\" passed). \"earned\" joined the direction "
            "words and the case joined `tests/test_verify.py`; the table above is the run after that fix.",
            "- \"Caught\" means the receipt found a number, a direction word, a side (today or after the move), a unit or an "
            "advice word that does not match what the debrief cites. It does not say the claim is wise.",
            "", "## Misses in the seven classes", ""]
    out += misses or ["None in this run."]
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=OUT.as_posix(), help="where to write the table (default docs/receipt_mutation.md)")
    args = ap.parse_args(argv)
    text = render(collect())
    Path(args.out).write_text(text, encoding="utf-8")
    sys.stdout.write(f"wrote {args.out}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
