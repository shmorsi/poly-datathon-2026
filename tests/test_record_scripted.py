"""scripts/record_demo.py --scripted (Sun Nov 15): the four defaults, the 16 curated moves and the six "Test the AI"
questions; data/demo_runs/moves.json and tests.json in the shapes of the lanes' contract (no model call here)."""
import json
from pathlib import Path

import pipeline
from scripts import record_demo


def test_the_scripted_questions_are_demo_questions_and_the_plan_has_them_all():
    data = json.loads(Path(pipeline.SCRIPTED_PATH).read_text(encoding="utf-8"))
    asked = pipeline.demo_questions()
    assert len(data["moves"]) == 19 and len(data["tests"]) == 7
    assert all(pipeline._norm_question(x["question"]) in asked for x in data["moves"] + data["tests"])
    assert {t["kind"] for t in data["tests"]} == {"run", "blocked", "clarify"}
    for t in data["tests"]:                                       # the card's line: past tense, no advice word
        assert not record_demo.pipeline.verify._advice(t["shows"]), t["id"]
    defaults, moves, tests = record_demo.scripted_plan()
    assert [d["pilot"] for d in defaults] == list(record_demo.DEFAULT_PILOTS) and all(d["own"] for d in defaults)
    assert len(moves) == 19 and len(tests) == 7 and all(m["flight_plan"]["pilot"] == m["pilot"] for m in moves)


def test_record_scripted_writes_moves_and_tests_in_the_contract_shape(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "DEMO_DIR", tmp_path)
    keys = iter(f"{i:016x}" for i in range(100))

    def fake_record(plan, *, dry_run=False, on_result=None):
        out = []
        for item in plan:
            path = tmp_path / f"{next(keys)}.json"
            change = {"op": "set", "ticker": "NVDA", "weight": 0.4, "from_ticker": None} if item["pilot"] == "robert" else None
            path.write_text(json.dumps({"result": {"scenario": {"change": change}}}))
            out.append({"pilot": item["pilot"], "question": item["question"], "saved": str(path), "why": None})
        return out
    monkeypatch.setattr(record_demo, "record", fake_record)
    monkeypatch.setattr(pipeline, "run", lambda plan, q, **k: {"status": "blocked" if "buy" in q else "clarify",
                                                                 "message": "x", "guardrail": {"input": {"blocked": "buy" in q}}})
    ok, entries = record_demo.record_scripted()
    moves = json.loads((tmp_path / "moves.json").read_text())
    tests = json.loads((tmp_path / "tests.json").read_text())
    assert ok and moves["version"] == 1 and moves["as_of"] == pipeline.DATASET_END and len(moves["moves"]) == 23
    first = moves["moves"][0]
    assert first == {"pilot": "robert", "ticker": "NVDA", "weight": 0.4, "question": first["question"], "key": first["key"],
                     "default": True} and len(first["key"]) == 16
    assert all(set(m) - {"from"} == {"pilot", "ticker", "weight", "question", "key"} for m in moves["moves"][4:])
    assert [m.get("from") for m in moves["moves"][-3:]] == ["XIU.TO", "XBB.TO", None]
    by = {t["id"]: t for t in tests["tests"]}
    assert set(by) == {"advice", "french", "alias", "no_precedent", "clarify", "reframe", "source_short"}
    assert tests["version"] == 1 and by["source_short"]["response"]["status"] == "clarify"
    assert by["advice"]["response"]["status"] == "blocked" and by["clarify"]["response"]["status"] == "clarify"
    assert all(len(by[i]["key"]) == 16 for i in ("french", "alias", "no_precedent", "reframe"))
    assert by["reframe"]["pilot"] == "canadian" and "recorded_at" in by["advice"]["response"]
