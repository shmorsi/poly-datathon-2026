"""Run-to-run stability, live (ruling R37; the agentic flaw report F4): the four investors' own questions and the
"Test the AI" questions (data/demo_scripted.json), each asked N times through pipeline.run with Bedrock and the input
guardrail on. Stable = the same plan (status, type, move, families, precedents, clarify or not), the same verdict and
the same receipt outcome in every repeat.

    python scripts/eval_stability.py run --repeats 8 --max-minutes 22 --max-usd 3.5 --out <rows.json>
    python scripts/eval_stability.py render <rows.json>

`run` writes the rows after every run (a crash loses one run). It starts a new repeat only when the slowest repeat so
far would still end inside --max-minutes and the spend so far plus the dearest repeat stays inside --max-usd; the
limits are written into the rows before the first call. Repeats are interleaved (repeat 1 of every input, then repeat
2, ...). Each run starts from the same named-defect memory: the file as it was before the first run is put back
before every run (pipeline.MEMORY_PATH), so the repeats differ only by what the models return. Inputs that are the
same (pilot, question) are asked once per repeat and listed under every label they carry (the Canadian investor's own
question is also the "reframe" test). `render` prints the markdown lines of docs/eval_results.md section 4a, every
number computed from the rows.

Nothing here prints a credential, an account id, an ARN or the guardrail id; the rows keep no request id.
"""
import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:      # `python scripts/eval_stability.py` puts scripts/, not the repo root, first
    sys.path.insert(0, ROOT.as_posix())

import config  # noqa: E402
from scripts import eval as ev  # noqa: E402

SCRIPTED_JSON = ROOT / "data" / "demo_scripted.json"
DEFAULT_PILOT = "robert"            # pipeline.DEFAULT_PILOT: a test that names no investor runs on Robert (record_demo)
WEIGHT_DIGITS = 3                   # a move's size compared to 0.1 percentage point
PARTS = ("plan", "verdict", "receipt")
PART_SHORT = {"plan": "plan", "verdict": "verdict", "receipt": "receipt outcome"}


# ---- the inputs ----
def inputs(personas=None, scripted=None) -> list:
    """The distinct (pilot, question) inputs, each with every label it carries: "investor:<pilot>" for the investors'
    own questions (data/personas.json), "test:<id>" for the Test-the-AI questions (data/demo_scripted.json)."""
    personas = personas if personas is not None else ev.personas()
    scripted = scripted if scripted is not None else json.loads(SCRIPTED_JSON.read_text(encoding="utf-8"))
    rows = [(f"investor:{pid}", pid, p["question"]) for pid, p in personas["pilots"].items()]
    rows += [(f"test:{t['id']}", t.get("pilot") or DEFAULT_PILOT, t["question"]) for t in scripted.get("tests") or []]
    out = {}
    for label, pilot, question in rows:
        item = out.setdefault((pilot, question), {"id": label, "labels": [], "pilot": pilot, "question": question})
        item["labels"].append(label)
    return list(out.values())


def flight_plan(pilot, personas=None) -> dict:
    """The flight plan the saved runs use (scripts/record_demo.py _flight_plan): the pilot's own inputs, no limits."""
    p = (personas if personas is not None else ev.personas())["pilots"][pilot]
    return {"portfolio": dict(p["portfolio"]), "amount": p["amount"], "profile": dict(p["profile"]), "limits": None,
            "pilot": pilot}


# ---- one run's fingerprint ----
def _move(change):
    if not isinstance(change, dict) or not change:
        return None
    w = change.get("weight")
    return [change.get("op"), change.get("ticker"), None if w is None else round(float(w), WEIGHT_DIGITS),
            change.get("from_ticker")]


def _digest(value):
    """A short hash of a text (None when there is none): enough to tell two texts apart, never the text itself."""
    if value in (None, ""):
        return None
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


def fingerprint(result) -> dict:
    """What a repeat is compared on (PARTS), plus what is shown but not compared (receipt counts, checks, the
    navigator's method, the explanation's words and the message, as hashes)."""
    res = result if isinstance(result, dict) else {}
    sc = res.get("scenario") if isinstance(res.get("scenario"), dict) else {}
    rc = res.get("receipt") if isinstance(res.get("receipt"), dict) else None
    first = rc.get("first_try") if rc and isinstance(rc.get("first_try"), dict) else None
    deb = res.get("debrief") if isinstance(res.get("debrief"), dict) else None
    return {
        "plan": {"status": res.get("status"), "type": sc.get("type"), "move": _move(sc.get("change")),
                 "families": sorted(sc.get("families") or []), "precedents": list(sc.get("event_ids") or []),
                 "clarify": bool(sc.get("clarify"))},
        "verdict": res.get("verdict"),
        "receipt": None if rc is None else {"clean": rc.get("defects") == [] and not rc.get("unverified"),
                                            "all_verified": rc.get("verified") == rc.get("total")},
        "receipt_counts": None if rc is None else {
            "verified": rc.get("verified"), "total": rc.get("total"), "drafts": rc.get("drafts"),
            "first_try_clean": None if first is None else first.get("defects") == []},
        "checks": sorted([str(c.get("rule")), str(c.get("status"))] for c in res.get("checks") or []
                         if isinstance(c, dict)),
        "method": sc.get("method"),
        "words": _digest(deb.get("text")) if deb else None,
        "message": _digest(res.get("message")),
    }


# ---- comparing the repeats ----
def _key(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def same(values) -> bool:
    return len({_key(v) for v in values}) <= 1


def stability(item) -> dict:
    """Per input: is each part the same in every repeat? `stable` = plan, verdict and receipt outcome all the same.
    `matched_first` counts the repeats after the first whose three parts equal the first repeat's."""
    fps = [r["fingerprint"] for r in item.get("repeats") or []]
    out = {part: same([f[part] for f in fps]) for part in (*PARTS, "receipt_counts", "checks", "method")}
    out["stable"] = bool(fps) and all(out[p] for p in PARTS)
    out["n"] = len(fps)
    out["matched_first"] = sum(1 for f in fps[1:] if all(_key(f[p]) == _key(fps[0][p]) for p in PARTS))
    out["words_distinct"] = len({f["words"] for f in fps if f["words"]})
    out["words_shown"] = sum(1 for f in fps if f["words"])
    out["variants"] = {part: len({_key(f[part]) for f in fps}) for part in PARTS}
    return out


def summary(data) -> dict:
    """The rates of the run: inputs stable in every repeat (each part and all three), repeats matching the first."""
    items = data.get("items") or []
    st = {it["id"]: stability(it) for it in items}
    model, day = data.get("model") or config.MODEL_ID, data.get("date")
    n_rep = sorted({s["n"] for s in st.values()})
    window = f" in one {data['minutes']:g}-minute window" if data.get("minutes") else ""
    lim = (f"{len(items)} distinct inputs x {'/'.join(map(str, n_rep)) or 0} repeats, one after another{window}, through "
           f"pipeline.run live (guardrail version {data.get('guardrail_version') or 'unset'}); the same memory before "
           f"each run; stable = the same in every repeat")
    out = {"inputs": len(items), "repeats": n_rep, "per_input": st,
           "stable": ev.rate(sum(1 for s in st.values() if s["stable"]), len(st), model=model, limit=lim, day=day)}
    for part in (*PARTS, "receipt_counts", "checks"):
        out[part] = ev.rate(sum(1 for s in st.values() if s[part]), len(st), model=model, limit=lim, day=day)
    later = sum(max(0, s["n"] - 1) for s in st.values())
    out["matched_first"] = ev.rate(sum(s["matched_first"] for s in st.values()), later, model=model, day=day,
                                   limit=lim.replace("stable = the same in every repeat",
                                                     "a repeat matches when its plan, verdict and receipt outcome "
                                                     "equal the first repeat's; repeats of the same inputs, not "
                                                     "independent trials"))
    runs = [r for it in items for r in it.get("repeats") or []]
    usd = [r.get("usd") for r in runs]
    out["usd_total"] = None if any(u is None for u in usd) else sum(usd)
    out["runs"] = len(runs)
    out["errors"] = sum(1 for r in runs if r.get("error"))
    out["ms"] = [r.get("ms") for r in runs]
    out["calls"] = sum(r.get("calls") or 0 for r in runs)
    out["guard_calls"] = sum(r.get("guard_calls") or 0 for r in runs)
    read = [r["fingerprint"]["method"] for r in runs if r["fingerprint"].get("method")]
    out["own_plan"] = (sum(1 for m in read if m == "bedrock"), len(read))
    return out


# ---- the live run ----
def _usd_calls(res):
    return ev._result_cost(res, config.model_for("navigator"), config.model_for("debrief"))


def one_run(item, personas=None, *, run=None) -> dict:
    """One pipeline run of an input: its fingerprint, latency and cost; an exception is recorded, never raised."""
    if run is None:
        import pipeline
        run = pipeline.run
    t0 = time.perf_counter()
    try:
        res, err = run(flight_plan(item["pilot"], personas), item["question"], ev.AS_OF) or {}, None
    except Exception as exc:                                   # a live failure is data, not a crash of the eval
        res, err = {}, type(exc).__name__
    usd, calls = _usd_calls(res)
    return {"fingerprint": fingerprint(res), "error": err, "ms": round((time.perf_counter() - t0) * 1000, 1),
            "usd": usd, "calls": calls,
            "guard_calls": sum(1 for t in res.get("trace") or [] if t.get("service") == "Bedrock Guardrails"),
            "engine": (res.get("scenario") or {}).get("engine") if isinstance(res.get("scenario"), dict) else None,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def _save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def run_live(out, *, repeats, max_minutes, max_usd, run=None, memory_path=None, log=print) -> dict:
    if os.environ.get(config.ENV_DEMO) == "1":
        raise SystemExit("EPICENTRE_DEMO=1 replays the saved runs: unset it for a live measurement")
    if memory_path is None:
        import pipeline
        memory_path = pipeline.MEMORY_PATH
    memory_path = Path(memory_path)
    seed = memory_path.read_bytes() if memory_path.exists() else None
    items = inputs()
    data = {"what": "run-to-run stability, live (scripts/eval_stability.py)", "date": ev.RUN_DATE,
            "commit": ev._commit(), "as_of": ev.AS_OF, "model": config.model_for("navigator"),
            "models": {"navigator": config.model_for("navigator"), "debrief": config.model_for("debrief")},
            "engine": config.scenario_engine(), "guardrail_version": os.environ.get(config.ENV_GUARDRAIL_VERSION) or None,
            "guardrail_on": bool(os.environ.get(config.ENV_GUARDRAIL_ID)),
            "planned": {"repeats": repeats, "max_minutes": max_minutes, "max_usd": max_usd},
            "memory_seed": None if seed is None else json.loads(seed.decode("utf-8")),
            "started": datetime.now(timezone.utc).isoformat(timespec="seconds"), "stopped_early": None,
            "items": [{**it, "repeats": []} for it in items]}
    _save(out, data)
    t_start, spent, slowest, dearest = time.perf_counter(), 0.0, 0.0, 0.0
    for rep in range(repeats):
        elapsed = time.perf_counter() - t_start
        if rep and (elapsed + slowest > max_minutes * 60 or spent + dearest > max_usd):
            data["stopped_early"] = (f"after {rep} repeats: the next would pass {max_minutes} min or ${max_usd} "
                                     f"(elapsed {elapsed / 60:.1f} min, spent ${spent:.2f})")
            log(f"stability: {data['stopped_early']}")
            break
        t_rep, usd_rep = time.perf_counter(), 0.0
        for it in data["items"]:
            if seed is not None:                       # the same named-defect memory before every run
                memory_path.parent.mkdir(parents=True, exist_ok=True)
                memory_path.write_bytes(seed)
            row = one_run(it, run=run)
            it["repeats"].append(row)
            usd_rep += row["usd"] or 0.0
            fp = row["fingerprint"]
            log(f"stability: repeat {rep + 1} {it['id']}: {fp['plan']['status']} · verdict {fp['verdict']} · "
                f"families {fp['plan']['families']} · move {fp['plan']['move']} · precedents "
                f"{len(fp['plan']['precedents'])} · receipt {fp['receipt']} {fp['receipt_counts']} · "
                f"{row['ms'] / 1000:.1f} s · ${(row['usd'] or 0):.4f}{' · error ' + row['error'] if row['error'] else ''}")
            _save(out, data)
        spent += usd_rep
        slowest, dearest = max(slowest, time.perf_counter() - t_rep), max(dearest, usd_rep)
    if seed is not None:
        memory_path.write_bytes(seed)                  # leave the memory file as it was found
    data["finished"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data["minutes"] = round((time.perf_counter() - t_start) / 60, 1)
    _save(out, data)
    return data


# ---- the doc section ----
def _plan_text(fp) -> str:
    p = fp["plan"]
    if p["status"] != "ok":
        return p["status"] or "no result"
    move = p["move"]
    m = "no move" if not move else (f"{move[0]} {move[1]}" + ("" if move[2] is None else f" {move[2] * 100:g} %")
                                    + (f" from {move[3]}" if move[3] else ""))
    return f"{m}; {', '.join(p['families']) or 'no family'}; {len(p['precedents'])} precedents"


def what_changed(item) -> str:
    """One plain clause per part that moved, each against the most common version: the plan's families, precedents,
    move or status, and the receipt outcome (a withheld explanation said as such). Empty when nothing moved."""
    fps = [r["fingerprint"] for r in item.get("repeats") or []]
    n, out = len(fps), []
    plans = [f["plan"] for f in fps]
    modal = max(plans, key=lambda p: sum(_key(q) == _key(p) for q in plans))
    for v in {_key(p): p for p in plans if _key(p) != _key(modal)}.values():
        k, bits = sum(_key(q) == _key(v) for q in plans), []
        if v["families"] != modal["families"]:
            bits.append(f"families {', '.join(v['families']) or 'none'} instead of {', '.join(modal['families']) or 'none'}")
        add = [e for e in v["precedents"] if e not in modal["precedents"]]
        gone = [e for e in modal["precedents"] if e not in v["precedents"]]
        if add and gone and len(add) == len(gone):
            bits.append(f"precedent {', '.join(add)} instead of {', '.join(gone)}")
        elif add or gone:
            bits.append(" and ".join(x for x in (f"added precedent {', '.join(add)}" if add else "",
                                                 f"dropped {', '.join(gone)}" if gone else "") if x)
                        + f" ({len(v['precedents'])} precedents, not {len(modal['precedents'])})")
        elif v["precedents"] != modal["precedents"]:
            bits.append("the same precedents in another order")
        if v["move"] != modal["move"]:
            bits.append(f"move {v['move']} instead of {modal['move']}")
        if v["status"] != modal["status"]:
            bits.append(f"status {v['status']} instead of {modal['status']}")
        out.append(f"{k} of {n} runs: {'; '.join(bits) or 'another reading'}")
    bad = [i for i, f in enumerate(fps) if f["receipt"] is not None
           and f["receipt"] != {"clean": True, "all_verified": True}]
    if bad and len(bad) < n:
        held = sum(1 for i in bad if fps[i]["words"] is None)
        counts = ", ".join(f"{fps[i]['receipt_counts']['verified']} / {fps[i]['receipt_counts']['total']}" for i in bad)
        off = {i for i, q in enumerate(plans) if _key(q) != _key(modal)}
        out.append(f"{'in the same run' if set(bad) <= off else f'{len(bad)} of {n} runs:'} the receipt was not clean "
                   f"after the re-ask ({counts} numbers verified)"
                   + (f", so code withheld the explanation{' each time' if held > 1 else ''}" if held else ""))
    return "; ".join(out)


VERDICT_WORDS = {"Incompatible": "Outside your limits", "Tension": "Inside, with caveats",
                 "Compatible": "Inside your limits"}          # governance.verdict -> the page's words


def _verdict_text(fp) -> str:
    v = (fp or {}).get("verdict")
    return "none" if not v else f"{VERDICT_WORDS.get(v, v)} ({v})"


def _same(st, part) -> str:
    return "same" if st[part] else f"changed ({st['variants'][part]} versions)"


def _counts_text(fps, st) -> str:
    counts = [f["receipt_counts"] for f in fps if f["receipt_counts"]]
    if not counts:
        return "no receipt"
    totals = sorted({c["total"] for c in counts if c["total"] is not None})
    drafts = sorted({c["drafts"] for c in counts if c["drafts"] is not None})
    span = f"{totals[0]}" if len(totals) == 1 else f"{totals[0]} to {totals[-1]}"
    return (f"{'same' if st['receipt_counts'] else 'changed'}: {span} numbers checked, "
            f"{' or '.join(map(str, drafts))} draft{'s' if drafts != [1] else ''}")


def render(data) -> list:
    s = summary(data)
    reps = "/".join(map(str, s["repeats"]))
    lines = ["", f"## 4a. Run-to-run stability, live (the questions on the page, {reps} repeats each)", ""]
    labels = sorted({lb for it in data["items"] for lb in it["labels"]})
    lines.append(f"- **Context:** the four investors' own questions and the Test-the-AI questions of "
                 f"data/demo_scripted.json ({len(labels)} labels, {s['inputs']} distinct inputs: the Canadian "
                 f"investor's question is also the reframe test), each asked {reps} times through pipeline.run, live "
                 f"on Amazon Bedrock (navigator engine {data.get('engine')}, navigator and debrief "
                 f"{data['models']['navigator']}) with Amazon Bedrock Guardrails version {data.get('guardrail_version')} on the "
                 f"question and on the explanation, "
                 f"code {data.get('commit')}, {data.get('date')}, as_of {data.get('as_of')}; one run at a time, "
                 f"repeats interleaved, the same named-defect memory before every run. Runner: "
                 f"scripts/eval_stability.py; rows: data/eval_stability_results.json.")
    lines.append(f"- **Stable inputs** (the same plan, verdict and receipt outcome in every repeat): "
                 f"{ev.fmt_rate(s['stable'])}")
    lines.append(f"- **Repeats that matched the input's first run** (plan, verdict and receipt outcome): "
                 f"{ev.fmt_rate(s['matched_first'])}")
    lines.append("- By part, inputs the same in every repeat: " + "; ".join(
        f"{name} {ev.fmt_cell(s[part])}" for part, name in (("plan", "plan (status, type, move, families, "
                                                                     "precedents in order, clarify or not)"),
                                                             ("verdict", "verdict"),
                                                             ("receipt", "receipt outcome (clean, every number "
                                                                         "verified)"),
                                                             ("checks", "every check's status"),
                                                             ("receipt_counts", "receipt counts (numbers checked, "
                                                                                "first try clean, drafts)"))))
    per = s["per_input"]
    moved = [it for it in data["items"] if not per[it["id"]]["stable"]]
    lines.append("- **What changed:** " + (" · ".join(f"{it['id']}: {what_changed(it)}" for it in moved) or "nothing")
                 + ". The verdict was the same in every repeat of every input"
                 + ("" if s["verdict"]["k"] == s["verdict"]["n"] else " except the ones above")
                 + (", and so was every check's status." if s["checks"]["k"] == s["checks"]["n"] else "."))
    shown = [per[it["id"]] for it in data["items"] if per[it["id"]]["words_shown"]]
    lines.append(f"- The explanation's words (the model's) differed between every two runs that showed one on "
                 f"{sum(1 for st in shown if st['words_distinct'] == st['words_shown'] > 1)} of the {len(shown)} inputs "
                 f"that got one; the receipt checked them each time.")
    own, reached = s["own_plan"]
    lines.append(f"- The navigator's own plan (not the keyword rules after code refused it) in {own} / {reached} runs "
                 f"that reached the navigator.")
    lines += ["", "| input | labels | first repeat: plan | first repeat: verdict | plan | verdict | receipt outcome | "
                  "receipt counts |", "|---|---|---|---|---|---|---|---|"]
    for it in data["items"]:
        st = per[it["id"]]
        fps = [r["fingerprint"] for r in it["repeats"]]
        first = fps[0] if fps else None
        lines.append(f"| {it['id']} | {', '.join(it['labels'])} | {_plan_text(first) if first else 'n/a'} | "
                     f"{_verdict_text(first)} | {_same(st, 'plan')} | {_same(st, 'verdict')} | "
                     f"{'no receipt' if not first or first['receipt'] is None else _same(st, 'receipt')} | "
                     f"{_counts_text(fps, st)} |")
    ms = s["ms"]
    lines += ["", f"- Latency per run p50 {ev._secs(ev.percentile(ms, 50))}, p95 {ev._secs(ev.percentile(ms, 95))} "
                  f"(N = {s['runs']}); cost {ev._usd(s['usd_total'])} in all ({ev.price_label()}); model calls "
                  f"{s['calls']}, guardrail calls {s['guard_calls']}; AWS errors {s['errors']}"
                  + (f"; {data['stopped_early']}" if data.get("stopped_early") else "")]
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="EPICENTRE run-to-run stability, live (ruling R37).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--repeats", type=int, default=8)
    r.add_argument("--max-minutes", type=float, default=22.0)
    r.add_argument("--max-usd", type=float, default=3.5)
    r.add_argument("--out", required=True)
    d = sub.add_parser("render")
    d.add_argument("rows")
    args = ap.parse_args(argv)
    if args.cmd == "run":
        run_live(Path(args.out), repeats=args.repeats, max_minutes=args.max_minutes, max_usd=args.max_usd,
                 log=lambda line: print(line, flush=True))
        data = json.loads(Path(args.out).read_text(encoding="utf-8"))
    else:
        data = json.loads(Path(args.rows).read_text(encoding="utf-8"))
    print("\n".join(render(data)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
