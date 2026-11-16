"""Tests for agents/profile_reader.py (lane profile-ai): the fifth profile, "You", built from the investor's own words.

No AWS call: the Converse client, the guardrail and (where named) the advice gate are fakes. Every number in an
answer must come from the investor's words, read by code; anything the words do not say is a labelled default.
"""
import json
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

from agents import profile_reader as pr

SAMPLE_WORDS = ("I'm 45, saving for my kids' university in 8 years. I have about $200,000 and could live with losing "
          "$40,000 at most. No oil companies, no crypto.")


class FakeClient:
    def __init__(self, text=None, stop="end_turn", exc=None):
        self.text, self.stop, self.exc, self.calls = text, stop, exc, []

    def converse(self, **request):
        self.calls.append(request)
        if self.exc:
            raise self.exc
        return {"output": {"message": {"content": [{"text": self.text}]}}, "stopReason": self.stop,
                "usage": {"inputTokens": 10, "outputTokens": 5}, "ResponseMetadata": {"RequestId": "req-1"}}


PASS = lambda text, source: {"action": "NONE", "blocked": False, "error": None}   # noqa: E731
ADVICE_OK = lambda text: {"ok": True, "kind": None, "rule": None, "message": None}   # noqa: E731


def model(answers=None, refuse=None):
    return FakeClient(json.dumps({"refuse": refuse, "answers": answers or {}}))


def a(value, words):
    return {"value": value, "words": words}


SAMPLE_ANSWERS = {"age": a(45, "I'm 45"), "horizon_years": a(8, "in 8 years"), "amount": a("$200,000", "about $200,000"),
                  "capacity": a("$40,000", "losing $40,000 at most"), "crypto": a(False, "no crypto"),
                  "sector_caps": [{"sector": "Energy", "value": None, "words": "No oil companies"}]}


def read(text, answers=None, **kw):
    client = kw.pop("client", None) or model(answers)
    return pr.read_profile(text, client=client, guard=kw.pop("guard", PASS), advice=kw.pop("advice", ADVICE_OK), **kw)


# ---- the model path: the model points at the words, code reads every value ----
def test_sherifs_example_is_read_from_the_words_and_the_rest_is_labelled_assumed():
    client = model(SAMPLE_ANSWERS)
    r = read(SAMPLE_WORDS, client=client)
    assert (r["status"], r["can_run"], r["method"], r["ai"], r["request_id"]) == ("ok", True, "bedrock", "read", "req-1")
    assert r["profile"] == {"goal": "balance", "horizon_years": 8, "risk": "moderate", "esg": True, "crypto": False,
                            "capacity": 40000.0, "reaction_2022": None}
    assert (r["age"], r["amount"], r["clarify"]) == (45, 200000.0, None)
    assert r["assumed"] == ["goal", "risk"]                       # the words give no goal and no risk level
    assert r["limits_hint"] == {"crypto": 0.0, "sector_caps": {"Energy": 0.0},
                                "from_words": ["crypto", "sector_caps.Energy", "capacity", "esg", "horizon_years"]}
    assert r["read_from"]["esg"] == r["read_from"]["sector_caps.Energy"] == "No oil companies"
    for key, words in r["read_from"].items():                     # every quote is the investor's own text
        assert words in SAMPLE_WORDS, key
    assert set(r["profile"]) == set(pr.PROFILE_KEYS)               # exactly server.Profile: /api/run takes it unchanged
    (req,) = client.calls
    assert req["system"][0]["text"] == pr.READER_PROMPT and "temperature" not in json.dumps(req)
    assert "toolChoice" not in req                                 # pitfall 3
    assert req["messages"][0]["content"][0]["text"].endswith(f"<words>{SAMPLE_WORDS}</words>")


def test_the_profile_is_accepted_by_the_run_route_unchanged():
    import server
    r = read(SAMPLE_WORDS, SAMPLE_ANSWERS)
    server.Profile(**r["profile"])                                 # extra="forbid": no age, no unknown key


def test_no_value_is_invented_a_number_must_be_in_the_words_and_match_them():
    text = "I'm 45 and I have about $200,000 to invest."
    r = read(text, {"age": a(46, "I'm 45"),                          # the model's number disagrees with the words
                    "amount": a(250000, "about $200,000"),           # same
                    "horizon_years": a(12, "for twelve years"),      # words that are not in the text
                    "goal": a("speculation", "to invest"),           # not one of the four goals
                    "capacity": a("$30,000", "I have about")})       # words holding no dollar amount
    assert r["age"] is None and r["amount"] is None and r["profile"]["capacity"] is None
    assert r["profile"]["horizon_years"] == 10 and r["profile"]["goal"] == "balance"      # the neutral defaults
    assert {"goal", "horizon_years", "risk", "esg", "crypto", "limits"} <= set(r["assumed"])
    reasons = {x["field"]: x["reason"] for x in r["rejected"]}
    assert reasons["age"] == reasons["amount"] == "the number does not match the words"
    assert reasons["horizon_years"] == "those words are not in the description"
    assert reasons["goal"] == "not one of the allowed answers"
    assert reasons["capacity"] == "those words do not hold exactly one dollar amount"
    shown = json.dumps(r)
    for invented in ("46", "250000", "12", "30000", "speculation"):
        assert invented not in shown.replace("req-1", ""), invented
    assert r["status"] == "clarify" and r["clarify"] == pr.CLARIFY_BOTH


def test_a_horizon_is_read_in_whole_years_from_numbers_words_a_year_or_months():
    assert pr._years_in("in 8 years") == 8 and pr._years_in("for the next ten years") == 10
    assert pr._years_in("until 2034") == 8 and pr._years_in("in two decades") == 20
    assert pr._years_in("in 18 months") == 2 and pr._years_in("between 5 and 8 years") is None
    assert pr.money_values("about $200,000") == [200000.0] and pr.money_values("40k or $1.5 million") == [40000.0, 1.5e6]
    assert pr.money_values("200 000 $") == [200000.0] and pr.money_values("8 years") == []


# ---- the one question ----
def test_clarify_asks_one_question_when_the_amount_or_the_capacity_is_missing():
    r = read("I'm 34 and want to grow my money over 15 years.",
             {"age": a(34, "I'm 34"), "goal": a("growth", "grow my money"), "horizon_years": a(15, "over 15 years")})
    assert (r["status"], r["can_run"], r["clarify"]) == ("clarify", False, pr.CLARIFY_BOTH)
    assert r["profile"]["goal"] == "growth" and r["profile"]["horizon_years"] == 15   # filled with what was read
    r = read("I have $80,000.", {"amount": a("$80,000", "$80,000")})
    assert (r["status"], r["can_run"], r["clarify"]) == ("clarify", True, pr.CLARIFY_CAPACITY)
    r = read("I have $80,000 and could lose $90,000.",
             {"amount": a("$80,000", "$80,000"), "capacity": a("$90,000", "could lose $90,000")})
    assert r["profile"]["capacity"] is None and r["clarify"] == pr.CAPACITY_NOT_BELOW + " " + pr.CLARIFY_CAPACITY
    assert {"field": "capacity", "reason": pr.CAPACITY_NOT_BELOW} in r["rejected"]
    for q in (pr.CLARIFY_BOTH, pr.CLARIFY_AMOUNT, pr.CLARIFY_CAPACITY):
        assert q.count("?") == 1                                   # ONE question


# ---- no limits: none is ever invented ----
def test_no_limits_in_the_words_sets_none_and_never_invents_one():
    r = read("I have $50,000 for 20 years and no limits.",
             {"amount": a("$50,000", "$50,000"), "horizon_years": a(20, "for 20 years"), "no_limits": a(True, "no limits")})
    assert (r["status"], r["clarify"], r["profile"]["capacity"]) == ("ok", None, None)   # no capacity question
    assert r["limits_hint"] == {"none": True} and "limits" in r["assumed"] and r["read_from"]["limits"] == "no limits"
    r = pr.read_profile("I'm 30 and have $50,000.", use_bedrock=False)                  # silent about limits
    assert "limits" in r["assumed"] and not set(r["limits_hint"]) & set(pr.CHECKED_LIMITS)
    assert r["status"] == "clarify" and r["clarify"] == pr.CLARIFY_CAPACITY             # one question, nothing invented


# ---- values in words ----
VALUES = "I care about ESG: no oil companies, no weapons, no more than 20 % in tech, no crypto. I have $90,000."


def test_values_words_switch_the_screen_on_and_only_a_named_sector_is_capped():
    r = read(VALUES, {"esg": a(True, "I care about ESG"), "crypto": a(False, "no crypto"),
                      "amount": a("$90,000", "$90,000"),
                      "sector_caps": [{"sector": "Energy", "value": None, "words": "no oil companies"},
                                      {"sector": "Information Technology", "value": 20, "words": "no more than 20 % in tech"},
                                      {"sector": "Industrials", "value": None, "words": "Weapons"}]})
    assert r["profile"]["esg"] is True and r["profile"]["crypto"] is False
    assert r["limits_hint"]["sector_caps"] == {"Energy": 0.0, "Information Technology": 0.2}
    assert r["limits_hint"]["crypto"] == 0.0
    assert {"esg", "crypto", "sector_caps.Energy", "sector_caps.Information Technology"} <= set(r["limits_hint"]["from_words"])
    assert {"field": "sector_caps.Industrials", "reason": "those words do not name that industry"} in r["rejected"]
    k = pr.read_profile(VALUES, use_bedrock=False)                 # the keyword rules read the same words
    assert k["profile"]["esg"] is True and k["limits_hint"]["crypto"] == 0.0
    assert k["limits_hint"]["sector_caps"] == {"Energy": 0.0, "Information Technology": 0.2}
    assert k["read_from"]["sector_caps.Energy"] == "no oil companies"
    w = pr.read_profile("No weapons, no tobacco. I have $90,000.", use_bedrock=False)
    assert w["profile"]["esg"] is True and "sector_caps" not in w["limits_hint"]          # no sector is guessed


# ---- a sentence with a move and a limit: the move goes to the navigator, the limit to the limits ----
MOVE = "Put 40 % in NVIDIA, but I can't lose more than $50,000. I have $300,000."


def test_a_move_and_a_limit_in_one_sentence_are_split():
    r = pr.read_profile(MOVE, use_bedrock=False)                  # the keyword rules
    assert r["move"] == {"words": "Put 40 % in NVIDIA"} and r["read_from"]["move"] == "Put 40 % in NVIDIA"
    assert (r["amount"], r["profile"]["capacity"], r["status"]) == (300000.0, 50000.0, "ok")
    assert "floor" not in r["limits_hint"] and "crypto" not in r["limits_hint"]      # the move's 40 % is no limit
    r = read(MOVE, {"move": {"words": "Put 40 % in NVIDIA"}, "amount": a("$300,000", "I have $300,000"),
                    "capacity": a("$50,000", "can't lose more than $50,000"), "floor": a(40, "40 %")})
    assert r["move"] == {"words": "Put 40 % in NVIDIA"} and r["profile"]["capacity"] == 50000.0
    assert {"field": "floor", "reason": "those words are the move, not a profile answer"} in r["rejected"]
    assert "floor" not in r["limits_hint"]


# ---- blocked: advice requests and real account details; the guardrail first ----
@pytest.mark.parametrize("text, found", [
    ("I'm 45, card 4111 1111 1111 1111, $200,000.", "a card number"),
    ("Reach me at jane.doe@example.com, I have $200,000.", "an email address"),
    ("My account number is 12345678 and I have $200,000.", "an account number"),
    ("My SIN is 046 454 286, I have $200,000.", "a social insurance number"),
    ("Call me at (514) 555-0199. I have $200,000.", "a phone number"),
])
def test_real_account_details_are_refused_before_any_network_call(text, found):
    def no_guard(t, s):
        raise AssertionError("the words must not leave the server")
    client = model(SAMPLE_ANSWERS)
    r = pr.read_profile(text, client=client, guard=no_guard, advice=ADVICE_OK)
    assert (r["status"], r["message"], r["profile"], r["read_from"]) == ("blocked", pr.ACCOUNT_STOP, None, {})
    assert r["screen"]["account"] == {"ok": False, "found": found} and client.calls == []


def test_an_advice_request_is_refused_by_the_advice_gate_and_no_model_runs():
    client = model(SAMPLE_ANSWERS)
    r = pr.read_profile("I'm 45 with $200,000. Should I buy NVIDIA?", client=client, guard=PASS)
    assert r["status"] == "blocked" and r["message"] == pr.ADVICE_STOP and client.calls == []
    assert r["screen"]["advice"]["kind"] == "advice" and r["can_run"] is False
    for word in ("buy", "sell", "hold", "should"):                 # red gate 1: the refusal says none of them
        assert word not in pr.ADVICE_STOP.lower() and word not in pr.ACCOUNT_STOP.lower()


def test_the_guardrail_reads_first_and_its_block_is_its_own_sentence():
    client, seen = model(SAMPLE_ANSWERS), []
    r = pr.read_profile(SAMPLE_WORDS, client=client, advice=lambda t: seen.append(t) or ADVICE_OK(t),
                        guard=lambda t, s: {"blocked": True, "message": "The guardrail's own sentence."})
    assert (r["status"], r["message"]) == ("blocked", "The guardrail's own sentence.")
    assert client.calls == [] and seen == []


def test_a_model_refusal_is_a_block_too():
    r = read(SAMPLE_WORDS, client=FakeClient(json.dumps({"refuse": "real_account", "answers": {}})))
    assert r["status"] == "blocked" and r["message"] == pr.ACCOUNT_STOP and r["method"] == "bedrock"


# ---- failures: fail closed, then the keyword rules (same shape) ----
def test_a_guardrail_that_does_not_answer_fails_closed_and_the_keyword_rules_read():
    client = model(SAMPLE_ANSWERS)
    r = pr.read_profile(SAMPLE_WORDS, client=client, advice=ADVICE_OK,
                        guard=lambda t, s: {"blocked": False, "error": "The safety check timed out."})
    assert client.calls == [] and (r["method"], r["ai"], r["message"]) == ("keyword", "down", pr.GUARD_DOWN)
    assert r["profile"]["capacity"] == 40000.0 and r["amount"] == 200000.0 and r["age"] == 45


def test_bedrock_off_makes_no_aws_call_and_reads_sherifs_example_with_keywords():
    def no_guard(t, s):
        raise AssertionError("the guardrail must not be called with Bedrock off")
    r = pr.read_profile(SAMPLE_WORDS, guard=no_guard, client=FakeClient(exc=AssertionError("no model")), use_bedrock=False)
    assert (r["method"], r["ai"], r["message"], r["status"]) == ("keyword", "off", pr.BEDROCK_OFF, "ok")
    assert r["profile"] == {"goal": "balance", "horizon_years": 8, "risk": "moderate", "esg": True, "crypto": False,
                            "capacity": 40000.0, "reaction_2022": None}
    assert r["limits_hint"]["sector_caps"] == {"Energy": 0.0} and r["limits_hint"]["crypto"] == 0.0
    assert r["read_from"]["amount"] == "about $200,000" and r["read_from"]["capacity"] == "losing $40,000 at most"


@pytest.mark.parametrize("client, reason, ai", [
    (FakeClient("no json here"), "had no JSON object", "not_used"),
    (FakeClient("{}", stop="max_tokens"), "stopped with max_tokens", "not_used"),
    (FakeClient(json.dumps({"answers": []})), "shape", "not_used"),
    (FakeClient(exc=ClientError({"Error": {"Code": "ThrottlingException", "Message": "arn:aws:iam::123:x"}}, "Converse")),
     "busy (throttled)", "down"),
])
def test_any_model_failure_answers_with_the_keyword_reading_and_one_plain_reason(client, reason, ai):
    r = read(SAMPLE_WORDS, client=client)
    assert (r["method"], r["ai"], r["amount"]) == ("keyword", ai, 200000.0)
    assert reason in r["fallback_reason"] and "arn:" not in json.dumps(r)


def test_empty_or_too_long_words_are_a_plain_value_error():
    for text in ("", "   ", None):
        with pytest.raises(ValueError, match="Describe yourself"):
            pr.read_profile(text, guard=PASS)
    with pytest.raises(ValueError, match="under 1,500 characters"):
        pr.read_profile("x" * (pr.MAX_TEXT_CHARS + 1), guard=PASS)


def test_the_keyword_rules_read_common_phrasings():
    r = pr.read_profile("J'ai 52 ans. In 2022 I sold everything. I need income in 6 years; I have $500k and can "
                        "absorb a $75k loss. No more than 10 % in one stock, no drop of more than 15 %.", use_bedrock=False)
    assert (r["age"], r["amount"], r["profile"]["capacity"]) == (52, 500000.0, 75000.0)
    assert r["profile"]["reaction_2022"] == "sold" and r["profile"]["risk"] == "low"      # governance's own rule
    assert r["profile"]["goal"] == "income" and r["profile"]["horizon_years"] == 6
    assert r["limits_hint"]["single_stock"] == 0.1 and r["limits_hint"]["floor"] == -0.15
    assert r["read_from"]["risk"] == r["read_from"]["reaction_2022"]
    assert pr.read_profile("I earn $90,000 a year.", use_bedrock=False)["amount"] is None   # an income is no amount


# ---- red gate 6: the words are never logged or written ----
def test_nothing_is_logged_and_the_module_writes_nothing(caplog):
    caplog.set_level("DEBUG")
    read(SAMPLE_WORDS, SAMPLE_ANSWERS)
    pr.read_profile(SAMPLE_WORDS, use_bedrock=False)
    assert not any("university" in rec.getMessage() for rec in caplog.records)
    src = Path(pr.__file__).read_text(encoding="utf-8")
    assert "import logging" not in src and "open(" not in src and "print(" not in src


# ---- the route ----
def _api(monkeypatch, no_bedrock=True):
    from fastapi.testclient import TestClient
    import server
    if no_bedrock:
        monkeypatch.setenv("EPICENTRE_NO_BEDROCK", "1")
    else:
        monkeypatch.delenv("EPICENTRE_NO_BEDROCK", raising=False)
    monkeypatch.delenv("EPICENTRE_PASSWORD", raising=False)
    return TestClient(server.create_app(web_dir=None))


def test_the_route_answers_503_without_bedrock_with_the_keyword_reading_and_422_on_bad_input(monkeypatch):
    api = _api(monkeypatch)
    r = api.post("/api/profile/read", json={"text": SAMPLE_WORDS})
    assert r.status_code == 503 and r.json()["method"] == "keyword" and r.json()["ai"] == "off"
    assert r.json()["amount"] == 200000.0 and r.json()["status"] == "ok"
    for body, words in (({"text": ""}, "Describe yourself"), ({"text": "x" * 1501}, "1,500 characters"),
                        ({"text": 12}, "invalid field: text"), ({"text": SAMPLE_WORDS, "extra": 1}, "invalid field")):
        bad = api.post("/api/profile/read", json=body)
        assert bad.status_code == 422 and bad.json()["status"] == "error" and words in bad.json()["message"]


def test_the_route_answers_200_when_the_model_read_the_words(monkeypatch):
    import guardrail
    api = _api(monkeypatch, no_bedrock=False)
    monkeypatch.setattr(guardrail, "apply_guardrail", PASS)
    monkeypatch.setattr(pr, "runtime_client", lambda: model(SAMPLE_ANSWERS))
    r = api.post("/api/profile/read", json={"text": SAMPLE_WORDS})
    assert r.status_code == 200 and r.json()["method"] == "bedrock" and r.json()["profile"]["capacity"] == 40000.0
    blocked = api.post("/api/profile/read", json={"text": "My account number is 12345678."})
    assert blocked.status_code == 200 and blocked.json()["status"] == "blocked"


# ---- live (opt-in: .venv/bin/python -m pytest -m live tests/test_profile_reader.py) ----
@pytest.mark.live
def test_live_sherifs_example_on_bedrock_and_guardrail_v1():
    r = pr.read_profile(SAMPLE_WORDS)
    assert r["method"] == "bedrock" and r["status"] == "ok", r.get("fallback_reason")
    assert (r["amount"], r["profile"]["capacity"], r["profile"]["horizon_years"]) == (200000.0, 40000.0, 8)
    assert r["profile"]["esg"] is True and r["profile"]["crypto"] is False and r["limits_hint"].get("crypto") == 0.0
