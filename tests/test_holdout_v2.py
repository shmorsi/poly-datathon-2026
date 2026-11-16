"""The blind held-out v2 runner (scripts/run_holdout_v2.py), offline: the pin, the two scoring rules, the first pass
kept as recorded, and every reading kept whole (lane ev audit, 2026-11-15; design doc ruling R10)."""
import json

import pytest

from scripts import run_holdout_v2 as H

CATALOG = [{"event_id": "t1", "family": "tariffs", "date": "2025-04-03"},
           {"event_id": "o1", "family": "war_oil", "date": "2022-02-24"}]
CTX = {"portfolio": {"XIU.TO": 1.0}, "profile": {}, "amount": None, "exposure": {}, "universe": None,
       "catalog": CATALOG}


def _q(**kw):
    q = {"id": "x", "group": "g", "pilot": "robert", "text": "t", "families": ["tariffs"], "type": "shock",
         "change": None, "clarify": False, "precedent": True}
    q.update(kw)
    return q


def test_the_committed_file_matches_its_pin():
    questions, sha = H.load_v2_questions()
    assert len(questions) == 48 and sha.startswith("4203c7181dccf177")


def test_a_changed_prompt_breaks_the_pin(tmp_path, monkeypatch):
    data = json.loads((H.ROOT / "data" / "eval_holdout_v2.json").read_text(encoding="utf-8"))
    data["questions"][0][3] = data["questions"][0][3] + " (edited)"
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "eval_holdout_v2.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(H, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        H.load_v2_questions()


def test_a_clarifying_question_is_not_an_abstention():
    """families [] matches a no-precedent label, but only a 'shock' reading with no question is the abstention."""
    q = _q(families=[], precedent=False)
    asked = {"type": "shock", "families": [], "event_ids": [], "clarify": "Which shock or move?", "change": None}
    abstained = {"type": "shock", "families": [], "event_ids": [], "clarify": None, "change": None}
    assert H.score_row(q, asked, CTX)["families_ok"] is True
    assert H.score_row(q, asked, CTX)["whole_ok"] is False
    assert H.score_row(q, abstained, CTX)["whole_ok"] is True


def test_the_move_is_graded_in_the_whole_reading():
    q = _q(type="change", change=["set", "NVDA", 0.3, None])
    right = {"type": "change", "families": ["tariffs"], "event_ids": ["t1"], "clarify": None,
             "change": {"op": "set", "ticker": "NVDA", "weight": 0.3}}
    wrong_size = dict(right, change={"op": "set", "ticker": "NVDA", "weight": 0.15})
    assert H.score_row(q, right, CTX)["whole_ok"] is True
    assert H.score_row(q, wrong_size, CTX) == {**H.score_row(q, wrong_size, CTX), "families_ok": True, "whole_ok": False}


def test_a_precedent_of_another_family_fails_the_whole_reading():
    q = _q()
    plan = {"type": "shock", "families": ["tariffs"], "event_ids": ["o1"], "clarify": None, "change": None}
    assert H.score_row(q, plan, CTX)["families_ok"] is True and H.score_row(q, plan, CTX)["whole_ok"] is False


def test_the_first_pass_is_never_overwritten():
    with pytest.raises(SystemExit, match="kept as recorded"):
        H.main(["--out", str(H.ROOT / "data" / "eval_holdout_v2_results.json")])


def test_every_reading_is_kept_whole_and_the_fallback_is_counted(tmp_path, monkeypatch):
    """A navigator row the keyword rules answered (method keyword) is recorded as not answered by the model."""
    monkeypatch.setattr(H.E, "pilot_context", lambda pilot: CTX)

    def read_one(arm, text, ctx):
        plan = {"type": "shock", "families": ["tariffs"], "event_ids": ["t1"], "clarify": None, "change": None,
                "method": "bedrock" if arm == "converse" else "keyword", "usage": None}
        return plan, None, 1.0

    monkeypatch.setattr(H.E, "read_one", read_one)
    out = tmp_path / "rerun.json"
    assert H.main(["--limit", "2", "--out", str(out)]) == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    nav, kw = saved["navigator"], saved["keyword"]
    assert [r["id"] for r in nav] == ["hv2_fr01", "hv2_fr02"] and len(kw) == 2
    assert nav[0]["model_answered"] is True and kw[0]["model_answered"] is False
    assert nav[0]["reading"]["event_ids"] == ["t1"] and nav[0]["method"] == "bedrock"
    assert saved["summary"]["overall"]["navigator"]["families"]["rate"] == "1 / 2"   # fr02 is labelled war_oil
    assert saved["meta"]["engine"] == "converse" and saved["meta"]["sha256"].startswith("4203c718")
