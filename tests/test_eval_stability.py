"""scripts/eval_stability.py: run-to-run stability, live (ruling R37; the agentic flaw report F4). Offline: a fake
pipeline.run, no AWS call."""
import json

import pytest

from scripts import eval_stability as es

PERSONAS = {"pilots": {
    "robert": {"question": "Q robert", "portfolio": {"XIU.TO": 1.0}, "amount": 600000, "profile": {"risk": "low"}},
    "canadian": {"question": "Q canadian", "portfolio": {"XIU.TO": 1.0}, "amount": 250000, "profile": {}}}}
SCRIPTED = {"tests": [{"id": "advice", "question": "Should I buy NVIDIA now?", "pilot": "robert"},
                      {"id": "reframe", "question": "Q canadian", "pilot": "canadian"},
                      {"id": "nopilot", "question": "Q other"}]}


def result(verdict="Incompatible", families=("tariffs",), events=("e1", "e2"), weight=0.4, defects=(), verified=15,
           total=15, text="words", status="ok"):
    return {"status": status, "verdict": verdict, "message": None,
            "scenario": {"type": "change", "families": list(families), "event_ids": list(events), "clarify": None,
                         "change": {"op": "set", "ticker": "NVDA", "weight": weight, "from_ticker": None},
                         "method": "bedrock", "engine": "converse"},
            "receipt": {"verified": verified, "total": total, "unverified": [], "defects": list(defects),
                        "first_try": {"defects": []}, "drafts": 1},
            "debrief": {"text": text}, "checks": [{"rule": "max_drawdown", "status": "fail"}],
            "trace": [{"service": "Amazon Bedrock", "step": "UNDERSTAND", "usage": {"inputTokens": 1000,
                                                                                  "outputTokens": 100}},
                      {"service": "Bedrock Guardrails"}]}


def item(*results, rid="x"):
    return {"id": rid, "labels": [rid], "repeats": [{"fingerprint": es.fingerprint(r)} for r in results]}


def test_inputs_dedupe_the_same_pilot_and_question_and_keep_every_label():
    rows = es.inputs(PERSONAS, SCRIPTED)
    assert [r["id"] for r in rows] == ["investor:robert", "investor:canadian", "test:advice", "test:nopilot"]
    assert rows[1]["labels"] == ["investor:canadian", "test:reframe"]
    assert rows[3]["pilot"] == "robert"                       # a test that names no investor runs on Robert


def test_flight_plan_is_the_saved_runs_shape():
    assert es.flight_plan("robert", PERSONAS) == {"portfolio": {"XIU.TO": 1.0}, "amount": 600000,
                                                  "profile": {"risk": "low"}, "limits": None, "pilot": "robert"}


def test_fingerprint_keeps_hashes_never_the_texts():
    fp = es.fingerprint(result(text="The replay put NVDA at 40.0 %"))
    assert fp["plan"] == {"status": "ok", "type": "change", "move": ["set", "NVDA", 0.4, None],
                          "families": ["tariffs"], "precedents": ["e1", "e2"], "clarify": False}
    assert fp["receipt"] == {"clean": True, "all_verified": True}
    assert "NVDA" not in json.dumps(fp["words"]) and len(fp["words"]) == 12
    blocked = es.fingerprint({"status": "blocked", "message": "Stopped."})
    assert blocked["receipt"] is None and blocked["verdict"] is None and blocked["plan"]["move"] is None


def test_the_words_may_change_and_the_input_stays_stable():
    st = es.stability(item(result(text="a"), result(text="b"), result(text="c", verified=13, total=13)))
    assert st["stable"] and st["n"] == 3 and st["matched_first"] == 2
    assert st["words_distinct"] == 3 and not st["receipt_counts"]


@pytest.mark.parametrize("changed, part", [({"verdict": "Compatible"}, "verdict"), ({"events": ("e2", "e1")}, "plan"),
                                           ({"weight": 0.3}, "plan"), ({"defects": ("too_long",)}, "receipt")])
def test_one_changed_part_makes_the_input_unstable(changed, part):
    st = es.stability(item(result(), result(**changed), result()))
    assert not st["stable"] and not st[part] and st["matched_first"] == 1


def test_summary_rates_are_k_over_n_with_wilson():
    data = {"items": [item(result(), result(), rid="a"), item(result(), result(verdict="Compatible"), rid="b")],
            "date": "2026-11-15",
            "model": "m", "guardrail_version": "1"}
    s = es.summary(data)
    assert (s["stable"]["k"], s["stable"]["n"]) == (1, 2) and s["stable"]["level"] == "Indicative"
    assert (s["matched_first"]["k"], s["matched_first"]["n"]) == (1, 2)
    assert s["runs"] == 4 and s["usd_total"] is None           # these rows carry no cost


def test_run_live_puts_the_same_memory_back_before_every_run_and_stops_on_budget(tmp_path, monkeypatch):
    real_inputs = es.inputs
    monkeypatch.setattr(es, "inputs", lambda: real_inputs(PERSONAS, SCRIPTED))
    monkeypatch.setattr(es.ev, "personas", lambda: PERSONAS)
    monkeypatch.delenv("EPICENTRE_DEMO", raising=False)
    mem = tmp_path / "defect_memory.json"
    mem.write_text('{"counts": {"too_long": 1}}')
    seen = []

    def fake_run(flight_plan, question, as_of):
        seen.append(mem.read_text())
        mem.write_text('{"counts": {"too_long": 9}}')            # the pipeline records into it
        return result()
    out = tmp_path / "rows.json"
    data = es.run_live(out, repeats=5, max_minutes=60, max_usd=0.0001, run=fake_run, memory_path=mem, log=lambda s: None)
    assert set(seen) == {'{"counts": {"too_long": 1}}'} and mem.read_text() == '{"counts": {"too_long": 1}}'
    assert [len(it["repeats"]) for it in data["items"]] == [1, 1, 1, 1]       # the second repeat would pass $0.0001
    assert data["stopped_early"].startswith("after 1 repeats")
    assert json.loads(out.read_text())["planned"] == {"repeats": 5, "max_minutes": 60, "max_usd": 0.0001}
    assert "e1" not in json.dumps(data["items"][0]["repeats"][0]["fingerprint"]["words"])


def test_run_live_refuses_the_saved_run_replay(tmp_path, monkeypatch):
    monkeypatch.setenv("EPICENTRE_DEMO", "1")
    with pytest.raises(SystemExit):
        es.run_live(tmp_path / "rows.json", repeats=1, max_minutes=1, max_usd=1, run=lambda *a: {}, memory_path=tmp_path / "m")


def test_render_writes_k_over_n_wilson_model_date_level_and_limit():
    data = {"items": [{**item(result(), result()), "id": "investor:robert", "labels": ["investor:robert"]}],
            "date": "2026-11-15", "model": "us.anthropic.claude-sonnet-5-5", "guardrail_version": "1",
            "models": {"navigator": "us.anthropic.claude-sonnet-5-5", "debrief": "us.anthropic.claude-sonnet-5-5"},
            "engine": "converse", "commit": "abc1234", "as_of": "2026-11-12"}
    text = "\n".join(es.render(data))
    assert "1 / 1 (95 % Wilson" in text and "us.anthropic.claude-sonnet-5-5 · 2026-11-15 · Indicative · limit:" in text
    assert "| investor:robert |" in text and "set NVDA 40 %" in text


def test_what_changed_names_each_moved_part_against_the_most_common_version():
    withheld = result(families=("chips", "tariffs"), defects=("Sentence 5 cites T32",), verified=12, total=13)
    withheld["debrief"] = None
    rows = item(result(), result(), withheld, result(events=("e1", "e3")), result(events=("e1", "e2", "e4")))
    text = es.what_changed(rows)
    assert "1 of 5 runs: families chips, tariffs instead of tariffs" in text
    assert "in the same run the receipt was not clean after the re-ask (12 / 13 numbers verified), so code withheld" in text
    assert "1 of 5 runs: precedent e3 instead of e2" in text
    assert "1 of 5 runs: added precedent e4 (3 precedents, not 2)" in text
    assert es.what_changed(item(result(), result())) == ""
