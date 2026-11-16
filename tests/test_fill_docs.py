"""scripts/fill_docs.py: every format, every selector, the derived roots, loud failures, and the repo's docs are well formed."""
import json

import pytest

from scripts import fill_docs as fd

NB, MINUS = " ", "−"

RUN = {
    "amount": 600000, "as_of": "2026-11-12",
    "events": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
    "tipping_point": {"curve": [{"weight": 0.0, "verdict": "Tension", "end_value": 700000.4},
                                {"weight": 0.08, "verdict": "Tension", "end_value": 710000.0},
                                {"weight": 0.09, "verdict": "Incompatible", "end_value": 720000.0},
                                {"weight": 0.1, "verdict": "Incompatible", "end_value": 730000.0}]},
    "checks": [{"rule": "max_drawdown", "tier": "hard", "status": "fail"},
               {"rule": "crypto", "tier": "hard", "status": "pass", "value": 0.0}],
    "facts": {"T1": {"label": "Worst drop after the move", "value": -0.3452439040250206, "unit": "pct", "kind": "fact"},
              "T2": {"label": "Unused row", "value": 1, "unit": "count", "kind": "fact"}},
    "trace": [{"id": "T1", "step": "COMPARE", "tool": "governance.evaluate", "service": "Python", "ms": 3,
               "inputs": {"path": "metrics.after.max_drawdown", "recipe": "evaluate.after"}},
              {"id": "T9", "step": "UNDERSTAND", "service": "Amazon Bedrock", "model": "us.anthropic.claude-sonnet-5-5",
               "ms": 2675, "usage": {"inputTokens": 2151, "outputTokens": 331, "cacheReadInputTokens": 1306}},
              {"id": "T10", "step": "EXPLAIN", "service": "Amazon Bedrock", "model": "us.anthropic.claude-sonnet-5-5",
               "ms": 5619, "usage": {"inputTokens": 2069, "outputTokens": 635, "cacheReadInputTokens": 2727,
                                     "cacheWriteInputTokens": 0}}],
    "debrief": {"sentences": [{"text": "The replay starts here [T2].", "refs": ["T2"]},
                              {"text": "The move fell up to 34.5 % [T1] at its worst.", "refs": ["T1"]}]},
    "evidence": {"T1": [{"file": "portfolio", "date": "2022-01-03", "value": 100.0}]},
    "nothing": None,
}
EVAL = {"arms": [{"arm": "navigator", "k": 37, "n": 40}, {"arm": "keyword_fallback", "k": 29, "n": 40}]}


def fill(text, **kw):
    return fd.fill_text(text, {"robert": RUN}, EVAL, name="t.md", **kw)


@pytest.mark.parametrize("value,code,want", [
    (-0.3452439040250206, "pct", f"34.5{NB}%"), (0.0125, "pct", f"1.3{NB}%"),         # size, ROUND_HALF_UP
    (0.09, "pct0", f"9{NB}%"), (0.345, "pct0", f"35{NB}%"),
    (-0.058, "spct", f"{MINUS}5.8{NB}%"), (0.058, "spct", f"5.8{NB}%"),
    (-207146.34241501236, "usd", "$207,146"), (1234.5, "usd", "$1,235"),
    (0.018906, "usd4", "$0.0189"), (1234.565, "usd2", "$1,234.57"),
    (2522.0, "int", "2,522"), (-3.5, "int", f"{MINUS}4"),
    (2.25, "x1", "2.3"), (-2.25, "x1", f"{MINUS}2.3"), (0.155, "x2", "0.16"),
    ([1, 2, 3], "len", "3"), ({"a": 1, "b": 2}, "len", "2"),
    ("2025-04-08", "year", "2025"), ("2025-04-08", "month", "Apr 2025"), ("2025-04-08", "date", "8 Apr 2025"),
    ("2025-04-08T00:00:00", "date", "8 Apr 2025"), ("2021-11", "month", "Nov 2021"), ("1973-01", "year", "1973"), (12, None, "12"), ("Tariff war", None, "Tariff war"),
    ("Incompatible", "verdict", "Outside your limits"), ("Tension", "verdict", "Inside, with caveats"),
    ("Compatible", "verdict", "Inside your limits"),
])
def test_every_format(value, code, want):
    assert fd.fmt(value, code) == want


@pytest.mark.parametrize("value,code", [(1, "pct1"), ("2025-13-01", "month"), ("soon", "year"), ("x", "usd"), ("2021-11", "date"),
                                        ("Maybe", "verdict")])
def test_a_bad_format_or_value_fails(value, code):
    with pytest.raises(fd.SlotError):
        fd.fmt(value, code)


@pytest.mark.parametrize("path,want", [
    ("amount", 600000), ("tipping_point.curve.3.end_value", 730000.0),               # a key, a list index
    ("tipping_point.curve.verdict=Incompatible.weight", 0.09),                     # the first item that matches
    ("checks.rule=crypto&tier=hard.status", "pass"),                               # every condition must match
    ("trace.step=EXPLAIN&service=Amazon Bedrock.ms", 5619),
])
def test_every_selector(path, want):
    assert fd.dig(RUN, path) == want


@pytest.mark.parametrize("path", ["nope", "tipping_point.curve.9", "checks.rule=sector.status",
                                  "checks.rule=crypto&tier=soft.status", "amount.x", "checks.bad"])
def test_a_missing_key_fails(path):
    with pytest.raises(fd.SlotError):
        fd.dig(RUN, path)


def test_the_fact_view_follows_one_number_from_its_sentence_to_its_rows():
    def one(path):
        return fd.resolve("run", f"robert:@fact.Worst drop after the move.{path}", {"robert": RUN}, EVAL)
    assert one("id") == "T1"
    assert one("row.kind") == "fact"
    assert one("trace.inputs.recipe") == "evaluate.after"
    assert one("sentence") == "The move fell up to 34.5 % [T1] at its worst."
    assert one("evidence.0.date") == "2022-01-03"
    with pytest.raises(fd.SlotError):
        fd.resolve("run", "robert:@fact.No such label.id", {"robert": RUN}, EVAL)


def test_wilson_is_the_interval_eval_py_publishes():
    """37 / 40 is the navigator's dev-set row of docs/eval_results.json: lo 0.8013546984090248, hi 0.9741644432281419."""
    lo = fd.resolve("eval", "@wilson(arms.arm=navigator.k,arms.arm=navigator.n).lo", {}, EVAL)
    hi = fd.resolve("eval", "@wilson(arms.0.k, arms.0.n).hi", {}, EVAL)
    assert lo == pytest.approx(0.8013546984090248, abs=1e-12) and hi == pytest.approx(0.9741644432281419, abs=1e-12)
    text, problems, _ = fill("⟨eval:@wilson(arms.0.k,arms.0.n).lo|pct⟩–⟨eval:@wilson(arms.0.k,arms.0.n).hi|pct⟩")
    assert problems == [] and text == f"80.1{NB}%–97.4{NB}%"
    with pytest.raises(fd.SlotError):
        fd.wilson(41, 40)


def test_the_cost_view_is_the_formula_of_proofs_run_cost():
    cost = fd.resolve("run", "robert:@cost", {"robert": RUN}, EVAL)
    assert (cost["calls"], cost["input"], cost["output"], cost["cache_read"]) == (2, 4220, 966, 4033)
    # (4220 x 2.00 + 966 x 10.00 + 4033 x 2.00 x 0.1) / 1e6 at config.PRICE_USD_PER_MTOK for Sonnet 5.5
    assert cost["usd"] == pytest.approx(0.0189066)
    assert fd.fmt(cost["usd"], "usd4") == "$0.0189"


def test_a_slot_fills_and_a_bad_one_is_named_with_its_line():
    text, problems, _ = fill("Robert has ⟨run:robert:amount|usd⟩ and ⟨run:robert:events|len⟩ shocks.\n"
                             "Navigator ⟨eval:arms.arm=navigator.k⟩ / ⟨eval:arms.0.n⟩.")
    assert problems == []
    assert text == "Robert has $600,000 and 3 shocks.\nNavigator 37 / 40."
    _, problems, _ = fill("ok\n⟨run:robert:nothing⟩ ⟨run:mateo:amount⟩ ⟨run:nobody:amount⟩ ⟨run:robert:amount|pc⟩")
    assert len(problems) == 4 and all(p.startswith("t.md:2: ") for p in problems)
    assert "null" in problems[0] and "no saved run for mateo" in problems[1]


def test_placeholders_code_spans_and_evidence_to_capture():
    _, problems, _ = fill("Cost ⟨to measure⟩.")
    assert problems and "not a slot" in problems[0]
    text, problems, captures = fill("Shown as `⟨run:‹investor›:‹path›|‹format›⟩` and ⟨to capture⟩.")
    assert problems == [] and captures == 1 and "`⟨run:‹investor›:‹path›|‹format›⟩`" in text
    _, problems, _ = fill("Request ids: ⟨to capture⟩.", final=True)
    assert problems and "to capture" in problems[0]


def test_main_writes_nothing_unless_every_slot_fills(tmp_path):
    runs, out = tmp_path / "runs", tmp_path / "build"
    runs.mkdir()
    (runs / "robert.json").write_text(json.dumps(RUN), encoding="utf-8")
    ev = tmp_path / "eval.json"
    ev.write_text(json.dumps(EVAL), encoding="utf-8")
    good, bad = tmp_path / "good.md", tmp_path / "bad.md"
    good.write_text("Data to ⟨run:robert:as_of|date⟩.", encoding="utf-8")
    bad.write_text("⟨run:robert:missing.key⟩", encoding="utf-8")
    assert fd.main([str(good), str(bad), "--runs", str(runs), "--eval", str(ev), "--out", str(out)]) == 1
    assert not out.exists()
    assert fd.main([str(good), "--runs", str(runs), "--eval", str(ev), "--out", str(out)]) == 0
    assert (out / "good.md").read_text(encoding="utf-8") == "Data to 12 Nov 2026."


def _slots(path):
    for line in path.read_text(encoding="utf-8").split("\n"):
        for part in fd.CODE_SPAN.split(line)[0::2]:
            yield from fd.SLOT.finditer(part)


D1_DOCS = ["technical.md", "aws.md"]          # lane D1's docs; each joins this list once it is written in the slot grammar


def test_the_default_files_are_the_templates_that_hold_a_slot():
    files = fd.default_files()
    assert files and all(p.parent == fd.TEMPLATES and p.suffix == ".md" and fd.SLOT.search(p.read_text(encoding="utf-8"))
                         for p in files)


def test_the_docs_a_judge_reads_are_their_templates_filled_from_the_committed_runs():
    """docs/<name>.md is the filled copy of docs/templates/<name>.md (the final saved runs in data/demo_runs and
    docs/eval_results.json, both committed), byte for byte, and no doc and no README shows a slot or an angle bracket:
    a judge browsing GitHub never sees one. Edit the template, then run scripts/fill_docs.py."""
    runs = fd.load_runs(fd.ROOT / "data" / "demo_runs")
    ev = json.loads((fd.ROOT / "docs" / "eval_results.json").read_text(encoding="utf-8"))
    for t in fd.default_files():
        filled, problems, _ = fd.fill_text(t.read_text(encoding="utf-8"), runs, ev, name=t.name, final=True)
        assert problems == [], problems
        assert fd.target(t, None).read_text(encoding="utf-8") == filled, f"{fd.target(t, None)} is not its template filled"
    for doc in [*sorted((fd.ROOT / "docs").glob("*.md")), fd.ROOT / "README.md"]:
        assert "\u27e8" not in doc.read_text(encoding="utf-8"), doc.name


def test_a_template_fills_into_docs_and_another_file_in_place(tmp_path, monkeypatch):
    runs, ev = tmp_path / "runs", tmp_path / "eval.json"
    runs.mkdir()
    (runs / "robert.json").write_text(json.dumps(RUN), encoding="utf-8")
    ev.write_text(json.dumps(EVAL), encoding="utf-8")
    monkeypatch.setattr(fd, "TEMPLATES", tmp_path / "docs" / "templates")
    fd.TEMPLATES.mkdir(parents=True)
    (fd.TEMPLATES / "tech.md").write_text("Data to ⟨run:robert:as_of|date⟩.", encoding="utf-8")
    readme = tmp_path / "README.md"
    readme.write_text("Robert's ⟨run:robert:amount|usd⟩.", encoding="utf-8")
    assert fd.main([str(fd.TEMPLATES / "tech.md"), str(readme), "--runs", str(runs), "--eval", str(ev)]) == 0
    assert (tmp_path / "docs" / "tech.md").read_text(encoding="utf-8") == "Data to 12 Nov 2026."
    assert (fd.TEMPLATES / "tech.md").read_text(encoding="utf-8") == "Data to ⟨run:robert:as_of|date⟩."   # untouched
    assert readme.read_text(encoding="utf-8") == "Robert's $600,000."


def test_the_readme_template_fills_the_readme_at_the_root():
    """docs/templates/README.md is the README's template (its numbers change with every recording); the filled copy is the
    repository's README.md, so a judge opening the repository reads numbers, never a slot."""
    assert (fd.TEMPLATES / "README.md").is_file()
    assert fd.target(fd.TEMPLATES / "README.md", None) == fd.ROOT / "README.md"
    assert fd.target(fd.TEMPLATES / "technical.md", None) == fd.ROOT / "docs" / "technical.md"


@pytest.mark.parametrize("name", D1_DOCS)
def test_lane_d1_docs_are_well_formed_and_their_eval_slots_resolve(name):
    """Known investor and format; eval slots fill from the committed docs/eval_results.json; no placeholder that is
    not a slot outside a code span (⟨to capture⟩ apart). Run slots fill at build time, from the final saved runs."""
    doc = fd.TEMPLATES / name
    ev = json.loads((fd.ROOT / "docs" / "eval_results.json").read_text(encoding="utf-8"))
    for m in _slots(doc):
        if m.group(1) == "run":
            assert m.group(2).split(":", 1)[0] in fd.INVESTORS, m.group(0)
        else:
            fd.fmt(fd.resolve("eval", m.group(2), {}, ev), m.group(3))
        assert m.group(3) is None or m.group(3) in fd.FORMATS, m.group(0)
    _, problems, _ = fd.fill_text(doc.read_text(encoding="utf-8"), {}, ev, name=name)
    assert [p for p in problems if "not a slot" in p] == []


def test_the_runs_are_read_as_record_demo_saves_them(tmp_path):
    """data/demo_runs holds saved runs ({key, saved_at, ..., result}) named as record_demo writes them: Robert's own
    question is default.json, the others default_<pilot>.json. A folder of bare Results named <investor>.json (the
    rehearsal copies) still works, and wins when both exist."""
    (tmp_path / "default.json").write_text(json.dumps({"key": "k", "saved_at": "t", "result": {**RUN, "who": "robert"}}))
    (tmp_path / "default_mateo.json").write_text(json.dumps({"key": "m", "result": {"who": "mateo"}}))
    (tmp_path / "amira.json").write_text(json.dumps({"who": "amira bare"}))
    (tmp_path / "default_amira.json").write_text(json.dumps({"result": {"who": "amira saved"}}))
    runs = fd.load_runs(tmp_path)
    assert sorted(runs) == ["amira", "mateo", "robert"]
    assert (runs["robert"]["who"], runs["mateo"]["who"], runs["amira"]["who"]) == ("robert", "mateo", "amira bare")
    assert fd.resolve("run", "robert:tipping_point.curve.verdict=Incompatible.weight", runs, None) == 0.09


def test_four_decimals_for_a_p_value_and_the_paired_counts_are_the_rows():
    """x4 writes an exact p value (0.000244 -> 0.0002); docs/eval_results.json holdout_v2.paired is computed from the
    committed rows by scripts/format_holdout_v2_results.py (13 only the navigator, 0 only the keyword rules)."""
    assert fd.fmt(0.000244140625, "x4") == "0.0002"
    from scripts import format_holdout_v2_results as H
    first, second = H.load()
    ev = json.loads((fd.ROOT / "docs" / "eval_results.json").read_text(encoding="utf-8"))
    assert ev["holdout_v2"]["paired"] == H.summary_json(first, second)["paired"]


def test_the_stability_keys_are_the_live_runs_summary():
    """docs/eval_results.json stability (cited by technical.md) is scripts/eval_stability.py's own summary of the
    committed rows (data/eval_stability_results.json), never typed."""
    from scripts import eval_stability as S
    summ = S.summary(json.loads((fd.ROOT / "data" / "eval_stability_results.json").read_text(encoding="utf-8")))
    ev = json.loads((fd.ROOT / "docs" / "eval_results.json").read_text(encoding="utf-8"))
    assert ev["stability"] == {k: summ[k] for k in ("inputs", "repeats", "runs", "errors", "stable", "verdict", "matched_first")}


def test_the_evidence_pack_lists_the_saved_runs_request_ids():
    """docs/aws_evidence/01-request-ids.txt carries the block scripts/evidence_request_ids.py writes from the committed
    saved runs (AWS juror): the request ids on the page and in the docs are in the evidence pack too."""
    from scripts import evidence_request_ids as X
    text = (fd.ROOT / "docs" / "aws_evidence" / "01-request-ids.txt").read_text(encoding="utf-8")
    block = X.block(fd.ROOT / "data" / "demo_runs")
    assert block in text and text.count(X.BEGIN) == 1
    robert = json.loads((fd.ROOT / "data" / "demo_runs" / "default.json").read_text(encoding="utf-8"))["result"]
    ids = [t["request_id"] for t in robert["trace"] if t.get("service") in X.SERVICES]
    assert ids and all(i in block for i in ids)
