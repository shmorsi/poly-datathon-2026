"""Run the blind held-out v2 evaluation (48 prompts) on the navigator (converse) and the keyword fallback.

Usage: python scripts/run_holdout_v2.py [--limit N] [--out data/eval_holdout_v2_rerun.json]

Lane ev audit (2026-11-15): the first pass (lane b5, data/eval_holdout_v2_results.json) called the navigator without
the pipeline's exposure, kept only the families of each reading and scored families alone, so a reading the keyword
rules answered after a refused model plan, a clarifying question and an abstention all scored the same way, and the
move was never graded. This runner uses scripts/eval.py's own harness (pilot_context, read_one: the same inputs the
pipeline gives the navigator) and keeps every reading whole (method, type, families, event_ids, clarify, change). Each
row is scored twice under the frozen labels: families right (set equality, the first pass's rule) and whole reading
right (scripts/eval.score_plan: families, precedents, move, clarify, type; the dev set's rule). It names the commit
the code ran at. It never overwrites the first pass. Needs AWS keys for the navigator arm.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, ROOT.as_posix())

import config  # noqa: E402
from scripts import eval as E  # noqa: E402  (the dev and held-out eval's own harness and scoring)

AS_OF = E.AS_OF
ARMS = (("navigator", "converse"), ("keyword", "B"))      # the navigator's engine is named, never "the default"
DEFAULT_OUT = ROOT / "data" / "eval_holdout_v2_rerun.json"


def wilson(k, n, z=1.96):
    """Wilson score interval for k successes in n trials (scripts/eval.py's)."""
    return E.wilson(k, n, z)


def evidence_level(n):
    return E.evidence_level(n)


def load_v2_questions():
    """Load and verify the v2 holdout questions (the SHA-256 is of the file with `_sha256` blanked)."""
    path = ROOT / "data" / "eval_holdout_v2.json"
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    stated_sha = data.get('_sha256', '')
    data_copy = dict(data)
    data_copy['_sha256'] = ''
    canonical = json.dumps(data_copy, sort_keys=True, ensure_ascii=False)
    computed_sha = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    if computed_sha != stated_sha:
        raise ValueError(f"SHA-256 mismatch: stated {stated_sha}, computed {computed_sha}")
    questions = []
    for row in data['questions']:
        qid, group, pilot, text, families, qtype, change, clarify, precedent = row
        questions.append({'id': qid, 'group': group, 'pilot': pilot, 'text': text, 'families': families,
                          'type': qtype, 'change': change, 'clarify': clarify, 'precedent': precedent})
    return questions, stated_sha


def score_families(got_families, expected_families):
    """The first pass's rule: the families as sets."""
    return set(got_families or []) == set(expected_families)


def git(*args) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def score_row(q, plan, ctx) -> dict:
    whole = E.score_plan(plan, q, families_of=E._families_of(ctx))
    return {"families_ok": score_families(plan.get("families"), q["families"]), "whole": whole,
            "whole_ok": E.all_ok(whole)}


def rate(rows, key) -> dict:
    k, n = sum(1 for r in rows if r[key]), len(rows)
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate": f"{k} / {n}", "wilson_low": lo, "wilson_high": hi, "level": evidence_level(n)}


def summarize(questions, results) -> dict:
    out = {"overall": {}, "by_category": {}}
    for arm, _ in ARMS:
        rows = results[arm]
        out["overall"][arm] = {"families": rate(rows, "families_ok"), "whole": rate(rows, "whole_ok")}
        if arm == "navigator":
            out["overall"][arm]["model_answered"] = rate(rows, "model_answered")
    for cat in sorted({q["group"] for q in questions}):
        ids = {q["id"] for q in questions if q["group"] == cat}
        out["by_category"][cat] = {arm: {"families": rate([r for r in results[arm] if r["id"] in ids], "families_ok"),
                                         "whole": rate([r for r in results[arm] if r["id"] in ids], "whole_ok")}
                                   for arm, _ in ARMS}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run blind held-out v2 eval")
    ap.add_argument("--limit", type=int, default=None, help="First N questions only")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args(argv)
    out_path = Path(args.out)
    if out_path.resolve() == (ROOT / "data" / "eval_holdout_v2_results.json").resolve():
        sys.exit("The first pass (data/eval_holdout_v2_results.json) is kept as recorded: write elsewhere.")
    try:
        questions, sha = load_v2_questions()
        if args.limit:
            questions = questions[:args.limit]
        print(f"Running {len(questions)} questions (SHA-256: {sha[:16]}...)", flush=True)
        results = {"meta": {"sha256": sha, "date": E.RUN_DATE, "model": config.model_for("navigator"),
                            "engine": "converse", "as_of": str(AS_OF), "commit": git("rev-parse", "HEAD"),
                            "on_main": git("merge-base", "HEAD", "origin/main"),
                            "dirty": bool(git("status", "--porcelain", "--", "agents", "tools", "config.py",
                                              "governance.py", "data/events.csv")),
                            "navigator_code_commit": git("log", "-1", "--format=%H", "--", "agents/scenario.py"),
                            "harness": "scripts/eval.py pilot_context + read_one (portfolio, profile, amount, "
                                       "exposure, universe, catalog at as_of)",
                            "scoring": {"families_ok": "set(families) == set(label families)",
                                        "whole_ok": "scripts/eval.score_plan: families, events (each of a labelled "
                                                    "family; any iff a precedent is labelled), change (op, ticker, "
                                                    "weight within 0.005, or none), clarify, type"}},
                   "navigator": [], "keyword": []}
        for i, q in enumerate(questions, 1):
            ctx = E.pilot_context(q["pilot"])
            for arm, engine in ARMS:
                model = None if engine == "B" else config.model_for("navigator")
                plan, err, wall = E.read_one(engine, q["text"], ctx)
                row = E._plan_row(q, plan, err, wall, {}, model)
                row.pop("scores", None), row.pop("ok", None)
                row.update(text=q["text"], pilot=q["pilot"],
                           expected={k: q[k] for k in ("families", "type", "change", "clarify", "precedent")},
                           model_answered=plan.get("method") == "bedrock", **score_row(q, plan, ctx))
                results[arm].append(row)
            n, k = results["navigator"][-1], results["keyword"][-1]
            print(f"  {i:2d}/{len(questions)} {q['id']:<15} nav {n['reading']['families']} fam={n['families_ok']} "
                  f"whole={n['whole_ok']} method={n['method']} | kw {k['reading']['families']} fam={k['families_ok']} "
                  f"whole={k['whole_ok']}", flush=True)
        results["summary"] = summarize(questions, results)
        out_path.write_text(json.dumps(results, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
        s = results["summary"]["overall"]
        for arm, _ in ARMS:
            print(f"{arm}: families {s[arm]['families']['rate']}, whole reading {s[arm]['whole']['rate']}")
        print(f"navigator readings the model answered: {s['navigator']['model_answered']['rate']}")
        print(f"saved {out_path}")
        return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
