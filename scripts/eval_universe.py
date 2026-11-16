"""Universe-wide reading: does every one of the 31 starter assets get read right? (Sun 2026-11-15)

    python scripts/eval_universe.py [--arms keyword,navigator] [--out data/eval_universe_results.json] [--limit N]

Each question of data/eval_universe.json ("What if I put 15 % in <name | ticker | alias>?", and in French) is read by
the keyword rules (arm B, no model) and by the navigator (one Converse call, the engine named), with the pipeline's
own inputs for the question's pilot (scripts/eval.py pilot_context + read_one). A reading is right when it is a
change with op "set", the expected ticker and the weight 0.15 (within 0.0005). Rates are k / N with Wilson 95 %.
The navigator arm also says how often the model's own plan was used (method "bedrock"); a reading the keyword rules
gave after a refused plan still counts as the product's reading. Needs AWS keys for the navigator arm.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, ROOT.as_posix())

import config  # noqa: E402
from scripts import eval as E  # noqa: E402

QUESTIONS = ROOT / "data" / "eval_universe.json"
DEFAULT_OUT = ROOT / "data" / "eval_universe_results.json"
ARMS = {"keyword": "B", "navigator": "converse"}


def right(plan, ticker, weight) -> bool:
    ch = (plan or {}).get("change") or {}
    w = ch.get("weight")
    return (ch.get("op") == "set" and ch.get("ticker") == ticker and isinstance(w, (int, float))
            and abs(w - weight) <= 0.0005)


def rate(rows, key="ok") -> dict:
    k, n = sum(1 for r in rows if r[key]), len(rows)
    lo, hi = E.wilson(k, n)
    return {"k": k, "n": n, "rate": f"{k} / {n}", "wilson_low": lo, "wilson_high": hi, "level": E.evidence_level(n)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Universe-wide reading: the keyword rules and the navigator on the 31 assets")
    ap.add_argument("--arms", default="keyword,navigator")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)
    data = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    questions = data["questions"][:args.limit] if args.limit else data["questions"]
    arms = [a for a in args.arms.split(",") if a in ARMS]
    ctx = E.pilot_context(data["pilot"])
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    out = {"meta": {"date": E.RUN_DATE, "model": config.model_for("navigator"), "engine": "converse", "commit": commit,
                    "pilot": data["pilot"], "as_of": str(E.AS_OF), "questions": len(questions),
                    "rule": "change op set, the expected ticker, weight 0.15 within 0.0005"}}
    for arm in arms:
        rows = []
        for q in questions:
            plan, err, wall = E.read_one(ARMS[arm], q["text"], ctx)
            ch = plan.get("change") or {}
            rows.append({"id": q["id"], "kind": q["kind"], "ticker": q["ticker"], "text": q["text"],
                         "ok": right(plan, q["ticker"], data["weight"]), "method": plan.get("method"),
                         "model_answered": plan.get("method") == "bedrock", "read": {k: ch.get(k) for k in ("op", "ticker", "weight")},
                         "clarify_reason": plan.get("clarify_reason"), "fallback_reason": plan.get("fallback_reason"),
                         "error": err or plan.get("error"), "ms": wall})
            if arm == "navigator":
                time.sleep(0.2)                                   # gentle on the Converse quota
        out[arm] = {"rows": rows, "overall": rate(rows),
                    "by_kind": {k: rate([r for r in rows if r["kind"] == k]) for k in ("name", "ticker", "alias", "french")}}
        if arm == "navigator":
            out[arm]["model_answered"] = rate(rows, "model_answered")
        o = out[arm]["overall"]
        print(f"{arm}: {o['rate']} ({o['wilson_low']:.3f}-{o['wilson_high']:.3f}) "
              + " ".join(f"{k} {v['rate']}" for k, v in out[arm]["by_kind"].items()), flush=True)
        for r in rows:
            if not r["ok"]:
                print(f"   miss {r['id']}: read {r['read']} clarify={r['clarify_reason']} method={r['method']}", flush=True)
    Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("saved", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
