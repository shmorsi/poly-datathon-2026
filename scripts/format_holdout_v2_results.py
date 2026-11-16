"""Render docs/eval_results.md section 2a and the eval_results.json held-out keys from the two passes' rows.

    python scripts/format_holdout_v2_results.py            # the markdown of section 2a
    python scripts/format_holdout_v2_results.py --json     # {"holdout_v2": ..., "examples": [...]} for eval_results.json

Rows: data/eval_holdout_v2_results.json (first pass, lane b5: families only) and data/eval_holdout_v2_rerun.json
(second pass, lane ev: every reading whole). Every number printed here is counted from those rows.
"""
import argparse
import json
import sys
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, ROOT.as_posix())

from scripts import eval as E  # noqa: E402

FIRST = ROOT / "data" / "eval_holdout_v2_results.json"
SECOND = ROOT / "data" / "eval_holdout_v2_rerun.json"
FIRST_CODE = "a504964"          # lane b5's worktree base when it ran (its commit 4a68537 was rebased to bbf70fb)
CATEGORY_ORDER = ("french", "paraphrase", "slang", "typos", "headline", "rambling", "no_precedent", "advice_bait",
                  "two_moves")
LIMIT = ("48 blind prompts on each pilot's own portfolio, one pass per arm, the reading step alone (no input "
         "guardrail, no advice check); labels frozen with the prompts")


def load():
    return json.loads(FIRST.read_text(encoding="utf-8")), json.loads(SECOND.read_text(encoding="utf-8"))


def k_of(rows, key):
    return sum(1 for r in rows if r[key])


def line(label, k, n, model, day):
    return f"- **{label}**: {E.fmt_rate(E.rate(k, n, model=model, limit=LIMIT, day=day))}"


def cell(rows, key):
    k, n = k_of(rows, key), len(rows)
    lo, hi = E.wilson(k, n)
    return f"{k} / {n} ({100 * lo:.1f}–{100 * hi:.1f} %)"


def mcnemar_exact(b, c) -> float:
    """Two-sided exact McNemar p: the binomial test of the b and c discordant pairs at one half."""
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def _p(p) -> str:
    return "p < 0.0001" if p < 0.0001 else f"p = {p:.4f}"


def paired_counts(nav, kw, key) -> dict:
    """The same prompts read by both arms: right for the navigator only (b), for the keyword rules only (c), both,
    neither, and b by category (CATEGORY_ORDER)."""
    k = {r["id"]: r for r in kw}
    b = [r for r in nav if r[key] and not k[r["id"]][key]]
    c = [r for r in nav if k[r["id"]][key] and not r[key]]
    groups = [(g, sum(1 for r in b if r["group"] == g)) for g in CATEGORY_ORDER]
    return {"b": len(b), "c": len(c), "ids": [r["id"] for r in b], "groups": [(g, n) for g, n in groups if n],
            "both": sum(1 for r in nav if r[key] and k[r["id"]][key]),
            "neither": sum(1 for r in nav if not r[key] and not k[r["id"]][key]), "p": mcnemar_exact(len(b), len(c))}


def paired_line(nav, kw, n) -> str:
    f, w = paired_counts(nav, kw, "families_ok"), paired_counts(nav, kw, "whole_ok")
    more = [r for r in nav if r["id"] in set(w["ids"]) - set(f["ids"])]
    extra = ", ".join(f"{g} {sum(1 for r in more if r['group'] == g)}" for g in CATEGORY_ORDER
                      if any(r["group"] == g for r in more))
    return (f"- **Paired, on the same {n} prompts (families right):** {f['b']} questions only the AI reader (the "
            f"navigator) got right, {f['c']} the other way (exact McNemar {_p(f['p'])}, two-sided): "
            + ", ".join(f"{g} {k}" for g, k in f["groups"]) + f"; both right {f['both']}, both wrong {f['neither']}. "
            f"Whole reading right: {w['b']} only the AI reader, {w['c']} the other way (exact McNemar {_p(w['p'])})"
            + (f"; the {len(more)} more: {extra}" if more else "") + ".")


def changed(first, second):
    a = {r["id"]: set(r["families_got"]) for r in first["navigator"]}
    return [r["id"] for r in second["navigator"] if set(r["reading"]["families"]) != a[r["id"]]]


def examples(first, second) -> list:
    """Prompts where, in BOTH passes, the keyword rules named no family or the wrong one and the navigator named the
    labelled one (English first); then the navigator's misses, labelled as such."""
    f_nav = {r["id"]: r for r in first["navigator"]}
    f_kw = {r["id"]: r for r in first["keyword"]}
    s_kw = {r["id"]: r for r in second["keyword"]}
    good, bad = [], []
    for n in second["navigator"]:
        i, kw = n["id"], s_kw[n["id"]]
        row = {"id": i, "category": n["group"], "text": n["text"], "expected_families": n["expected"]["families"],
               "keyword_got": kw["reading"]["families"], "keyword_clarify": kw["reading"]["clarify_reason"],
               "navigator_got": n["reading"]["families"], "navigator_method": n["method"],
               "first_pass": {"navigator_got": f_nav[i]["families_got"], "keyword_got": f_kw[i]["families_got"]}}
        if (n["families_ok"] and f_nav[i]["families_ok"] and not kw["families_ok"] and not f_kw[i]["families_ok"]
                and n["method"] == "bedrock"):
            good.append(dict(row, label="Keyword rules miss the shock, navigator reads it (both passes)"))
        elif not n["families_ok"] or not f_nav[i]["families_ok"]:
            bad.append(dict(row, label="Navigator wrong in " + ("both passes" if not n["families_ok"] and not
                                                                f_nav[i]["families_ok"] else
                                                                "the second pass" if not n["families_ok"] else
                                                                "the first pass")))
    good.sort(key=lambda r: (r["category"] == "french", CATEGORY_ORDER.index(r["category"])))
    return good + bad


def summary_json(first, second) -> dict:
    nav, kw = second["navigator"], second["keyword"]
    n, m = len(nav), second["meta"]
    out = {"sha256": m["sha256"], "date": m["date"], "n": n, "model": m["model"], "engine": m["engine"],
           "as_of": m["as_of"], "code": m["on_main"], "navigator_code": m["navigator_code_commit"],
           "rows": "data/eval_holdout_v2_rerun.json",
           "navigator_k": k_of(nav, "families_ok"), "keyword_k": k_of(kw, "families_ok"),
           "navigator_rate": f"{k_of(nav, 'families_ok')} / {n}", "keyword_rate": f"{k_of(kw, 'families_ok')} / {n}",
           "navigator_whole_k": k_of(nav, "whole_ok"), "keyword_whole_k": k_of(kw, "whole_ok"),
           "navigator_model_answered_k": k_of(nav, "model_answered"),
           "metric": "families right (set equality); whole reading right = scripts/eval.score_plan",
           "first_pass": {"by": "lane b5", "code": FIRST_CODE, "rows": "data/eval_holdout_v2_results.json",
                          "scored": "families only", "navigator_k": k_of(first["navigator"], "families_ok"),
                          "keyword_k": k_of(first["keyword"], "families_ok")},
           "navigator_changed_between_passes": changed(first, second)}
    out["by_category"] = {}
    for cat in CATEGORY_ORDER:                     # web/lib/how.js reads {n, navigator: {k}, keyword: {k}} (families)
        nv, kv = [r for r in nav if r["group"] == cat], [r for r in kw if r["group"] == cat]
        out["by_category"][cat] = {"n": len(nv),
                                   "navigator": {"k": k_of(nv, "families_ok"), "whole_k": k_of(nv, "whole_ok")},
                                   "keyword": {"k": k_of(kv, "families_ok"), "whole_k": k_of(kv, "whole_ok")}}
    for arm in ("navigator", "keyword"):
        for key, name in (("families_ok", "families"), ("whole_ok", "whole")):
            lo, hi = E.wilson(k_of(second[arm], key), n)
            out[f"{arm}_{name}_wilson"] = [lo, hi]
    out["paired"] = paired(nav, kw)
    return out


def paired(nav, kw, key="families_ok") -> dict:
    """The two arms on the same questions (matched by id): how many only the navigator got right, how many only the
    keyword rules, and the exact two-sided McNemar p (a binomial test on those discordant pairs, p = 0.5)."""
    from math import comb
    by_id = {r["id"]: r for r in kw}
    b = sum(1 for r in nav if r[key] and not by_id[r["id"]][key])
    c = sum(1 for r in nav if not r[key] and by_id[r["id"]][key])
    t = b + c
    p = 1.0 if t == 0 else min(1.0, 2 * sum(comb(t, i) for i in range(min(b, c) + 1)) / 2 ** t)
    return {"only_navigator": b, "only_keyword": c, "mcnemar_exact_p": p, "metric": key}


def markdown(first, second) -> str:
    s, m = second, second["meta"]
    nav, kw, n, day, model = s["navigator"], s["keyword"], len(s["navigator"]), m["date"], m["model"]
    fb = [r for r in nav if not r["model_answered"]]
    flips = changed(first, second)
    nopre = [r for r in kw if r["group"] == "no_precedent"]
    out = ["## 2a. Held-out v2 (blind, 48 prompts; ruling R10)", "",
           f"- **Context:** 48 prompts written by lane B5 (a separate Claude agent of ours, not an independent person), "
           f"blind by its own account (without reading the development or "
           f"the earlier held-out questions), in data/eval_holdout_v2.json (SHA-256 {m['sha256']}, checked at every "
           f"load: the prompts and labels are unchanged since they were pinned), each on its pilot's own portfolio and "
           f"profile. Navigator engine converse, {model}, as_of {m['as_of']}. This is the navigator alone: the input "
           "guardrail and the advice check are measured in sections 6 and 6a.",
           f"- **Two passes, no tuning between them.** First pass: lane B5, {first['meta']['date']}, code {FIRST_CODE} "
           f"(the branch's base when it ran; its commit was rebased to bbf70fb), families only kept "
           f"(data/eval_holdout_v2_results.json). Second pass: lane ev, {day}, code {m['on_main'][:7]} on main "
           f"(navigator code {m['navigator_code_commit'][:7]}; the only change to agents/scenario.py since {FIRST_CODE} is "
           f"the keyword fallback's precedent order, 22dff56), every reading kept whole (data/eval_holdout_v2_rerun.json), "
           "read through scripts/eval.py's own harness (the inputs the pipeline gives the navigator).", "",
           "Second pass:", "",
           line("navigator (converse), families right", k_of(nav, "families_ok"), n, model, day),
           line("navigator, whole reading right (families, precedents, move, clarify, type)", k_of(nav, "whole_ok"), n,
                model, day),
           line("keyword, families right", k_of(kw, "families_ok"), n, "no model", day),
           line("keyword, whole reading right (families, precedents, move, clarify, type)", k_of(kw, "whole_ok"), n,
                "no model", day),
           paired_line(nav, kw, n),
           f"- Navigator readings that are the model's own plan: {k_of(nav, 'model_answered')} / {n}. In the other "
           f"{len(fb)} code refused the plan and the keyword rules answered: "
           + "; ".join(f"{r['id']} ({r['fallback_reason'].split('(')[1].split(')')[0]})" for r in fb) + ".",
           "",
           "First pass (lane B5's rule: families right; recounted from its rows, the counts are right):", "",
           line("navigator (converse), families right", k_of(first["navigator"], "families_ok"), n, model,
                first["meta"]["date"]),
           line("keyword, families right", k_of(first["keyword"], "families_ok"), n, "no model", first["meta"]["date"]),
           "",
           f"- Between the passes the navigator's families changed on {len(flips)} / {n} prompts ({', '.join(flips)}); "
           "the keyword rules are code and read every prompt the same way.",
           "- **Grading audit (lane ev).** The first pass scored the families alone and stored nothing else, so: a "
           "clarifying question with no family scored as a correct no-precedent answer (the keyword rules asked a "
           f"question on all {len(nopre)} no-precedent prompts: families right {k_of(nopre, 'families_ok')} / "
           f"{len(nopre)}, whole reading right {k_of(nopre, 'whole_ok')} / {len(nopre)}; the navigator abstained on all "
           f"{len(nopre)}, a shock with no precedent and no question); the move was never graded; and a reading the "
           "keyword rules gave after code refused the model's plan counted as the navigator's. It also called the "
           "navigator without the investor's exposure, which the pipeline passes. The second pass uses the pipeline's "
           "inputs, keeps the method and scores the whole reading as section 1 does.",
           "- **Label notes (the labels stay frozen).** The 3 two-move prompts are labelled type \"move\", which no reader "
           "returns (change, shock, fit, diversification), so neither arm can read them whole-right; each label holds one "
           "of its two moves, and the navigator kept one move each (hv2_multi01: NVIDIA 30 %, the QQQ 15 % dropped). "
           "hv2_advice05 (\"Tell me exactly what percentage to hold in US stocks vs Canadian\") names no shock and is "
           "labelled tariffs. The advice-bait prompts are labelled with the shock they name; in the app the advice check "
           "stops all 5 before the navigator (section 6a).", "",
           "Per category (second pass unless marked; every category rate is Indicative, N < 30):", "",
           "| category | n | navigator families, 1st pass | navigator families | navigator whole | keyword families | "
           "keyword whole |", "|---|---|---|---|---|---|---|"]
    f_nav = {r["id"]: r for r in first["navigator"]}
    for cat in CATEGORY_ORDER:
        nv = [r for r in nav if r["group"] == cat]
        kv = [r for r in kw if r["group"] == cat]
        fv = [f_nav[r["id"]] for r in nv]
        out.append(f"| {cat} | {len(nv)} | {cell(fv, 'families_ok')} | {cell(nv, 'families_ok')} | {cell(nv, 'whole_ok')} "
                   f"| {cell(kv, 'families_ok')} | {cell(kv, 'whole_ok')} |")
    ex = examples(first, second)
    out += ["", "**Where the keyword rules miss the shock and the navigator reads it, in both passes** (docs/eval_results.json "
            "\"examples_checked\"; the page's \"examples\" are the English ones below, then hv2_fr01 and hv2_fr03; "
            "hv2_fr02, which lane B5 listed, is dropped: it did not reproduce in the second pass):"]
    for e in [x for x in ex if x["label"].startswith("Keyword")]:
        kwt = "no family (it asked a question)" if not e["keyword_got"] else str(e["keyword_got"])
        out.append(f"- **{e['id']}** ({e['category']}): \"{e['text']}\" · labelled {e['expected_families']} · keyword "
                   f"{kwt} · navigator {e['navigator_got']}")
    out += ["", "**Where the navigator is wrong:**"]
    for e in [x for x in ex if x["label"].startswith("Navigator")]:
        out.append(f"- **{e['id']}** ({e['category']}, {e['label'][len('Navigator wrong in '):]}): \"{e['text']}\" · "
                   f"labelled {e['expected_families']} · navigator first pass {e['first_pass']['navigator_got']}, "
                   f"second pass {e['navigator_got']} ({e['navigator_method']}) · keyword {e['keyword_got']}")
    out += ["", "The earlier correction: the first version of this section listed hv2_para01, hv2_para02 and hv2_para03 as "
            "prompts the keyword rules missed; its own rows show the keyword rules read all three right (tariffs, war_oil, "
            "chips), in both passes."]
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    first, second = load()
    if args.json:
        print(json.dumps({"holdout_v2": summary_json(first, second), "examples": examples(first, second)}, indent=1,
                         ensure_ascii=False))
    else:
        print(markdown(first, second), end="")


if __name__ == "__main__":
    main()
