"""Workstream B evidence tests (plan B Tasks 11 and 12). Task 12 = the preflight section and the policy-simulator
section below; Task 11 (scripts/eval.py) appends its own section above or below, it never replaces this file.

Offline only: no test here calls AWS (plan B, Global Constraints); every AWS client is a MagicMock.
"""
import fnmatch
import json
import pathlib
import re
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

import config
from scripts import preflight as pf
from scripts import simulate_policy as sp


# ---------------------------------------------------------------------------------------------------------------
# Task 12: scripts/preflight.py, the canaries before recording and before submitting
# ---------------------------------------------------------------------------------------------------------------
def test_offline_marks_aws_checks_not_run_and_fails(monkeypatch, capsys):
    monkeypatch.setattr(pf, "CHECKS", [("credentials", lambda: (True, "x")), ("dataset", lambda: (True, "ok"))])
    monkeypatch.setattr(pf, "AWS_CHECKS", {"credentials"})
    rows = pf.run_checks(offline=True)
    assert [r["status"] for r in rows] == ["NOT RUN", "PASS"]
    assert pf.main(["--offline"]) == 1 and "not a preflight pass" in capsys.readouterr().out


def test_exception_in_a_check_is_a_fail_not_a_crash(monkeypatch):
    def boom():
        raise RuntimeError("secret AKIAXXXX must not leak")
    monkeypatch.setattr(pf, "CHECKS", [("dataset", boom)])
    monkeypatch.setattr(pf, "AWS_CHECKS", set())
    row = pf.run_checks()[0]
    assert row["status"] == "FAIL" and row["detail"] == "RuntimeError" and "AKIA" not in str(row)


def test_all_pass_exits_zero(monkeypatch, capsys):
    monkeypatch.setattr(pf, "CHECKS", [("a", lambda: (True, "fine")), ("b", lambda: (True, "fine"))])
    monkeypatch.setattr(pf, "AWS_CHECKS", set())
    assert pf.main([]) == 0 and "Epicentre: 2 / 2 passed" in capsys.readouterr().out


def test_cache_check_needs_a_real_read(monkeypatch):
    calls = iter([{"usage": {"cacheReadInputTokens": 0}, "stopReason": "end_turn"},
                  {"usage": {"cacheReadInputTokens": 812}, "stopReason": "end_turn"}])
    client = MagicMock(); client.converse.side_effect = lambda **kw: next(calls)
    monkeypatch.setattr(pf, "runtime_client", lambda: client)
    ok, detail = pf.check_prompt_cache()
    assert ok and "812" in detail
    assert client.converse.call_args.kwargs["system"][1] == {"cachePoint": {"type": "default"}}


# ---- structure: names, order, the AWS set, one check_<name> function each ----
EXPECTED_NAMES = [
    "credentials", "region", "model_navigator", "model_debrief", "guardrail_ids", "guardrail_exists",
    "guardrail_blocks_advice", "guardrail_passes_pilot", "navigator_live", "prompt_cache",
    "dataset", "holdings", "tests", "server",
]


def test_the_checks_are_named_and_ordered_and_each_has_its_function():
    assert [name for name, _ in pf.CHECKS] == EXPECTED_NAMES
    for name, fn in pf.CHECKS:
        assert fn is getattr(pf, "check_" + name), name


def test_aws_checks_are_exactly_the_ten_that_need_aws():
    assert pf.AWS_CHECKS == set(EXPECTED_NAMES[:10])
    assert not pf.AWS_CHECKS & {"dataset", "holdings", "tests", "server"}


def test_row_shape_and_nothing_is_printed_by_run_checks(monkeypatch, capsys):
    monkeypatch.setattr(pf, "CHECKS", [("a", lambda: (True, "fine")), ("b", lambda: (False, "bad"))])
    monkeypatch.setattr(pf, "AWS_CHECKS", set())
    rows = pf.run_checks()
    assert rows == [{"name": "a", "status": "PASS", "detail": "fine"},
                    {"name": "b", "status": "FAIL", "detail": "bad"}]
    assert capsys.readouterr().out == ""


def test_each_row_is_handed_over_as_soon_as_its_check_is_done(monkeypatch):
    seen = []

    def slow():
        assert seen == ["a"]                      # the first row was already delivered when the second check runs
        return True, "fine"
    monkeypatch.setattr(pf, "CHECKS", [("a", lambda: (True, "fine")), ("b", slow)])
    monkeypatch.setattr(pf, "AWS_CHECKS", set())
    rows = pf.run_checks(on_row=lambda row: seen.append(row["name"]))
    assert seen == ["a", "b"] and [r["status"] for r in rows] == ["PASS", "PASS"]


def test_output_is_one_line_per_check_then_the_tally_and_nothing_else(monkeypatch, capsys):
    monkeypatch.setattr(pf, "CHECKS", [("a", lambda: (True, "fine")), ("b", lambda: (False, "bad"))])
    monkeypatch.setattr(pf, "AWS_CHECKS", set())
    assert pf.main([]) == 1
    assert capsys.readouterr().out.splitlines() == ["PASS  a  fine", "FAIL  b  bad", "Epicentre: 1 / 2 passed"]


def test_an_offline_run_never_exits_zero_and_says_so_after_the_tally(monkeypatch, capsys):
    monkeypatch.setattr(pf, "CHECKS", [("credentials", lambda: (True, "x")), ("dataset", lambda: (True, "ok"))])
    monkeypatch.setattr(pf, "AWS_CHECKS", {"credentials"})
    assert pf.main(["--offline"]) == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("NOT RUN  credentials  ") and lines[1] == "PASS  dataset  ok"
    assert lines[2:] == ["Epicentre: 1 / 2 passed", "Offline run: not a preflight pass."]


def test_a_check_that_does_not_return_true_is_not_a_pass(monkeypatch):
    monkeypatch.setattr(pf, "CHECKS", [("a", lambda: (MagicMock(), "truthy but not True")), ("b", lambda: None)])
    monkeypatch.setattr(pf, "AWS_CHECKS", set())
    rows = pf.run_checks()
    assert [r["status"] for r in rows] == ["FAIL", "FAIL"]
    assert rows[1]["detail"] == "TypeError"


def test_details_are_one_plain_line_without_arns_account_ids_or_key_ids(monkeypatch, capsys):
    leaky = ("denied for arn:aws:sts::123456789012:assumed-role/x/y\nkey AKIAABCDEFGHIJKLMNOP\n"
             "account 123456789012 " + "word " * 80)
    monkeypatch.setattr(pf, "CHECKS", [("a", lambda: (False, leaky))])
    monkeypatch.setattr(pf, "AWS_CHECKS", set())
    row = pf.run_checks()[0]
    assert "\n" not in row["detail"] and len(row["detail"]) <= 240
    for secret in ("arn:aws", "123456789012", "AKIAABCDEFGHIJKLMNOP"):
        assert secret not in row["detail"]


# ---- credentials and region: nothing secret is ever read into a detail ----
class _Creds:
    method = "env"
    access_key = "AKIASECRETSECRETSECR"
    secret_key = "do-not-print-this-secret"
    token = "do-not-print-this-token"


def _session(creds=None, region="us-east-1"):
    stub = MagicMock(get_credentials=lambda: creds, region_name=region)
    return lambda: stub


def test_credentials_found_names_the_source_and_never_a_secret(monkeypatch):
    monkeypatch.setattr(pf, "aws_session", _session(_Creds()))
    ok, detail = pf.check_credentials()
    assert ok and "env" in detail
    for secret in (_Creds.access_key, _Creds.secret_key, _Creds.token):
        assert secret not in detail


def test_no_credentials_is_a_plain_fail(monkeypatch):
    monkeypatch.setattr(pf, "aws_session", _session(None))
    ok, detail = pf.check_credentials()
    assert not ok and "No AWS credentials" in detail


@pytest.mark.parametrize("session_region, ok", [("us-east-1", True), (None, True), ("us-west-2", False)])
def test_region_is_us_east_1_for_the_app_and_the_shell(monkeypatch, session_region, ok):
    monkeypatch.setattr(pf, "aws_session", _session(_Creds(), session_region))
    got, detail = pf.check_region()
    assert got is ok and "us-east-1" in detail
    if not ok:
        assert "us-west-2" in detail and "AWS_REGION" in detail


def test_region_fails_if_the_app_client_would_use_another_region(monkeypatch):
    monkeypatch.setattr(pf, "aws_session", _session(_Creds(), "us-east-1"))
    monkeypatch.setattr(pf, "runtime_client", lambda: MagicMock(meta=MagicMock(region_name="eu-west-1")))
    got, detail = pf.check_region()
    assert not got and "eu-west-1" in detail


# ---- models: scripts.check_bedrock.ping is the one availability probe ----
def _ping_result(**kw):
    out = {"ok": True, "model_id": "m", "latency_ms": 812, "stop_reason": "end_turn", "error": None, "hint": None}
    out.update(kw)
    return out


@pytest.mark.parametrize("job, check", [("navigator", "check_model_navigator"), ("debrief", "check_model_debrief")])
def test_model_check_pings_the_jobs_model_and_reports_id_and_latency(monkeypatch, job, check):
    ping = MagicMock(return_value=_ping_result(model_id=config.model_for(job)))
    monkeypatch.setattr(pf, "ping", ping)
    ok, detail = getattr(pf, check)()
    assert ok and config.model_for(job) in detail and "812 ms" in detail
    ping.assert_called_once_with(config.model_for(job))


def test_model_check_fails_with_the_plain_error_and_hint(monkeypatch):
    monkeypatch.setattr(pf, "ping", lambda m: _ping_result(
        ok=False, stop_reason=None, error="ExpiredTokenException",
        hint="Your event keys expired: paste fresh export lines."))
    ok, detail = pf.check_model_navigator()
    assert not ok and "ExpiredTokenException" in detail and "event keys expired" in detail


def test_model_check_needs_end_turn_even_if_ping_says_ok(monkeypatch):
    monkeypatch.setattr(pf, "ping", lambda m: _ping_result(ok=True, stop_reason="max_tokens"))
    ok, detail = pf.check_model_debrief()
    assert not ok and "max_tokens" in detail


# ---- the guardrail: ids, existence (read-only get-guardrail), the block canary, the pilot canary ----
GUARDRAIL_ID, GUARDRAIL_VERSION = "g1d2e3f4a5b6", "3"


@pytest.fixture
def guardrail_env(monkeypatch):
    monkeypatch.setenv(config.ENV_GUARDRAIL_ID, GUARDRAIL_ID)
    monkeypatch.setenv(config.ENV_GUARDRAIL_VERSION, GUARDRAIL_VERSION)


def _client_error(code, message="User: arn:aws:sts::123456789012:assumed-role/x/y is not authorized"):
    return ClientError({"Error": {"Code": code, "Message": message}, "ResponseMetadata": {"RequestId": "r"}},
                       "GetGuardrail")


def _guardrail(**kw):
    out = {"status": "READY", "version": GUARDRAIL_VERSION, "name": config.GUARDRAIL_NAME, "guardrailId": GUARDRAIL_ID,
           "guardrailArn": "arn:aws:bedrock:us-east-1:123456789012:guardrail/" + GUARDRAIL_ID}
    out.update(kw)
    return out


def test_guardrail_ids_prints_the_version_only(monkeypatch, guardrail_env):
    ok, detail = pf.check_guardrail_ids()
    assert ok and GUARDRAIL_VERSION in detail and GUARDRAIL_ID not in detail


@pytest.mark.parametrize("missing", [config.ENV_GUARDRAIL_ID, config.ENV_GUARDRAIL_VERSION])
def test_guardrail_ids_fails_when_either_variable_is_missing(monkeypatch, guardrail_env, missing):
    monkeypatch.delenv(missing)
    ok, detail = pf.check_guardrail_ids()
    assert not ok and config.ENV_GUARDRAIL_ID in detail and config.ENV_GUARDRAIL_VERSION in detail


def test_guardrail_exists_reads_it_with_get_guardrail_and_prints_no_id_or_arn(monkeypatch, guardrail_env):
    client = MagicMock(); client.get_guardrail.return_value = _guardrail()
    monkeypatch.setattr(pf, "control_client", lambda: client)
    ok, detail = pf.check_guardrail_exists()
    assert ok and "READY" in detail and "version 3" in detail and "us-east-1" in detail
    assert GUARDRAIL_ID not in detail and "arn:" not in detail and "123456789012" not in detail
    client.get_guardrail.assert_called_once_with(guardrailIdentifier=GUARDRAIL_ID, guardrailVersion=GUARDRAIL_VERSION)


def test_guardrail_exists_refuses_draft_because_the_evidence_pack_needs_a_numbered_version(monkeypatch, guardrail_env):
    monkeypatch.setenv(config.ENV_GUARDRAIL_VERSION, "DRAFT")
    client = MagicMock(); client.get_guardrail.return_value = _guardrail(version="DRAFT")
    monkeypatch.setattr(pf, "control_client", lambda: client)
    ok, detail = pf.check_guardrail_exists()
    assert not ok and "DRAFT" in detail and "numbered version" in detail


@pytest.mark.parametrize("resp, word", [(_guardrail(status="UPDATING"), "UPDATING"),
                                        (_guardrail(version="2"), "version"),
                                        (_guardrail(name="someone-elses-guardrail"), "name")])
def test_guardrail_exists_fails_when_not_ready_or_not_ours(monkeypatch, guardrail_env, resp, word):
    client = MagicMock(); client.get_guardrail.return_value = resp
    monkeypatch.setattr(pf, "control_client", lambda: client)
    ok, detail = pf.check_guardrail_exists()
    assert not ok and word in detail


@pytest.mark.parametrize("code, word", [("ResourceNotFoundException", "not found"), ("AccessDeniedException", "denied"),
                                        ("ExpiredTokenException", "expired")])
def test_guardrail_exists_turns_aws_errors_into_plain_sentences(monkeypatch, guardrail_env, code, word):
    client = MagicMock(); client.get_guardrail.side_effect = _client_error(code)
    monkeypatch.setattr(pf, "control_client", lambda: client)
    ok, detail = pf.check_guardrail_exists()
    assert not ok and word in detail.lower() and "arn:" not in detail and "123456789012" not in detail


def test_guardrail_exists_without_ids_makes_no_call(monkeypatch):
    monkeypatch.delenv(config.ENV_GUARDRAIL_ID, raising=False)
    monkeypatch.delenv(config.ENV_GUARDRAIL_VERSION, raising=False)
    boom = MagicMock(side_effect=AssertionError("no AWS call without ids"))
    monkeypatch.setattr(pf, "control_client", boom)
    ok, detail = pf.check_guardrail_exists()
    assert not ok and config.ENV_GUARDRAIL_ID in detail


def _applied(**kw):
    out = {"action": "NONE", "blocked": False, "error": None, "latency_ms": 640, "message": None}
    out.update(kw)
    return out


def test_the_block_canary_needs_a_real_block(monkeypatch):
    apply = MagicMock(return_value=_applied(action="GUARDRAIL_INTERVENED", blocked=True))
    monkeypatch.setattr(pf, "apply_guardrail", apply)
    ok, detail = pf.check_guardrail_blocks_advice()
    assert ok and "640 ms" in detail
    apply.assert_called_once_with("Should I buy NVDA now?", "INPUT")
    monkeypatch.setattr(pf, "apply_guardrail", lambda *a, **k: _applied())
    assert pf.check_guardrail_blocks_advice()[0] is False


def test_the_block_canary_error_is_a_fail_with_the_plain_sentence(monkeypatch):
    sentence = "AWS keys expired: the safety check could not run."
    monkeypatch.setattr(pf, "apply_guardrail", lambda *a, **k: _applied(action="ERROR", error=sentence))
    ok, detail = pf.check_guardrail_blocks_advice()
    assert not ok and sentence in detail


def test_the_pilot_canary_sends_roberts_scripted_question_and_wants_no_block_no_error(monkeypatch):
    question = json.loads(config.PERSONAS_JSON.read_text(encoding="utf-8"))["pilots"]["robert"]["question"]
    apply = MagicMock(return_value=_applied())
    monkeypatch.setattr(pf, "apply_guardrail", apply)
    ok, detail = pf.check_guardrail_passes_pilot()
    assert ok and "640 ms" in detail
    apply.assert_called_once_with(question, "INPUT")
    for bad in (_applied(blocked=True, action="GUARDRAIL_INTERVENED"), _applied(error="The safety check timed out.")):
        monkeypatch.setattr(pf, "apply_guardrail", lambda *a, _bad=bad, **k: _bad)
        assert pf.check_guardrail_passes_pilot()[0] is False


# ---- the navigator canary: Robert's scripted question, the whole path, method must be "bedrock" ----
def test_navigator_live_runs_roberts_question_on_his_portfolio_and_wants_bedrock(monkeypatch):
    from tools.data import DATASET_END
    from tools.portfolio import normalize
    robert = json.loads(config.PERSONAS_JSON.read_text(encoding="utf-8"))["pilots"]["robert"]
    events, universe = [{"id": "e1"}], object()
    run = MagicMock(return_value={"method": "bedrock", "ms": 2700.4, "families": ["tariffs"], "fallback_reason": None})
    load = MagicMock(return_value=events)
    monkeypatch.setattr(pf, "run_scenario", run)
    monkeypatch.setattr(pf, "load_events", load)
    monkeypatch.setattr(pf, "load_universe", lambda: universe)
    ok, detail = pf.check_navigator_live()
    assert ok and "bedrock" in detail
    load.assert_called_once_with(DATASET_END)
    assert run.call_args.args == (robert["question"], normalize(robert["portfolio"]), events, DATASET_END)
    assert run.call_args.kwargs == {"universe": universe}


def test_navigator_live_fallback_is_a_fail_that_says_why(monkeypatch):
    why = "AWS keys expired: the navigator could not run. The keyword rules answered."
    monkeypatch.setattr(pf, "run_scenario", lambda *a, **k: {"method": "fallback", "fallback_reason": why})
    monkeypatch.setattr(pf, "load_events", lambda as_of: [])
    monkeypatch.setattr(pf, "load_universe", lambda: None)
    ok, detail = pf.check_navigator_live()
    assert not ok and why in detail


# ---- prompt cache: a claim needs a measured read ----
def _cache_client(first, second):
    replies = iter([{"usage": {"cacheReadInputTokens": first}, "stopReason": "end_turn"},
                    {"usage": {"cacheReadInputTokens": second}, "stopReason": "end_turn"}])
    client = MagicMock(); client.converse.side_effect = lambda **kw: next(replies)
    return client


def test_cache_check_sends_the_debriefs_request_twice_identically(monkeypatch):
    from agents.explainer import DEBRIEF_PROMPT
    client = _cache_client(0, 1264)
    monkeypatch.setattr(pf, "runtime_client", lambda: client)
    ok, detail = pf.check_prompt_cache()
    assert ok and detail == "caching proven: 1264 tokens read"
    first, second = (c.kwargs for c in client.converse.call_args_list)
    assert first == second and len(client.converse.call_args_list) == 2
    model = config.model_for("debrief")
    assert first["modelId"] == model
    assert first["system"] == [{"text": DEBRIEF_PROMPT}, {"cachePoint": {"type": "default"}}]
    assert first["messages"] == [{"role": "user", "content": [{"text": "Reply with the single word: ready"}]}]
    assert first["inferenceConfig"] == {"maxTokens": 1500}
    assert first["additionalModelRequestFields"] == config.request_fields(model)
    assert not {"toolConfig", "outputConfig"} & set(first) and "temperature" not in first["inferenceConfig"]


@pytest.mark.parametrize("second", [0, None])
def test_cache_check_without_a_read_makes_no_caching_claim(monkeypatch, second):
    client = _cache_client(0, 0)
    if second is None:
        client = MagicMock(); client.converse.return_value = {"usage": {}, "stopReason": "end_turn"}
    monkeypatch.setattr(pf, "runtime_client", lambda: client)
    ok, detail = pf.check_prompt_cache()
    assert not ok and detail == "no cache read: make no caching claim"


def test_cache_check_reports_an_aws_failure_as_one_plain_sentence(monkeypatch):
    client = MagicMock(); client.converse.side_effect = _client_error("ThrottlingException")
    monkeypatch.setattr(pf, "runtime_client", lambda: client)
    ok, detail = pf.check_prompt_cache()
    assert not ok and "busy" in detail and "arn:" not in detail and "123456789012" not in detail
    assert client.converse.call_count == 1


# ---- local checks: dataset, holdings, tests, server ----
def test_dataset_check_looks_for_prices_daily(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "STARTER_DIR", tmp_path)
    assert pf.check_dataset()[0] is False
    (tmp_path / "prices_daily.csv").write_text("date\n")
    assert pf.check_dataset()[0] is True


def test_holdings_check_says_what_to_run_when_the_file_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ETF_HOLDINGS_CSV", tmp_path / "etf_holdings.csv")
    ok, detail = pf.check_holdings()
    assert not ok and "scripts/fetch_holdings.py" in detail
    (tmp_path / "etf_holdings.csv").write_text("etf\n")
    assert pf.check_holdings()[0] is True


def test_tests_check_runs_the_full_suite_and_reports_its_last_line(monkeypatch):
    import subprocess, sys
    done = subprocess.CompletedProcess([], 0, stdout="....\n1518 passed, 2 deselected in 95.12s\n", stderr="")
    run = MagicMock(return_value=done)
    monkeypatch.setattr(pf.subprocess, "run", run)
    assert pf.check_tests() == (True, "1518 passed, 2 deselected in 95.12s")
    assert run.call_args.args[0] == [sys.executable, "-m", "pytest", "-q"]
    assert run.call_args.kwargs["cwd"] == config.ROOT and run.call_args.kwargs["capture_output"] is True
    run.return_value = subprocess.CompletedProcess([], 1, stdout="1 failed, 5 passed in 3s\n", stderr="")
    assert pf.check_tests() == (False, "1 failed, 5 passed in 3s")


def test_tests_check_timeout_is_a_plain_fail(monkeypatch):
    import subprocess
    monkeypatch.setattr(pf.subprocess, "run", MagicMock(side_effect=subprocess.TimeoutExpired("pytest", 1)))
    ok, detail = pf.check_tests()
    assert not ok and "time" in detail


def test_server_check_gets_api_health_through_the_test_client(monkeypatch):
    import sys, types
    from fastapi import FastAPI
    app = FastAPI()
    app.get("/api/health")(lambda: {"data": True})
    monkeypatch.setitem(sys.modules, "server", types.SimpleNamespace(app=app))
    ok, detail = pf.check_server()
    assert ok and "200" in detail
    broken = FastAPI()
    monkeypatch.setitem(sys.modules, "server", types.SimpleNamespace(app=broken))
    ok, detail = pf.check_server()
    assert not ok and "404" in detail


# ---------------------------------------------------------------------------------------------------------------
# Task 12: scripts/simulate_policy.py, read-only IAM simulation + Access Analyzer validation (spec section 24)
# ---------------------------------------------------------------------------------------------------------------
IAM_DIR = pathlib.Path(__file__).resolve().parents[1] / "docs" / "iam"


class FakeIam:
    """The part of iam:SimulateCustomPolicy the repo's policies need: Allow statements with exact or `*` resources
    and StringEquals conditions. Anything not allowed is implicitDeny. Records every call."""

    def __init__(self, decide=None):
        self.calls, self.decide = [], decide

    @staticmethod
    def _allowed(policy, action, resource, context):
        for st in policy["Statement"]:
            if st.get("Effect") != "Allow":
                continue
            actions = [st["Action"]] if isinstance(st["Action"], str) else st["Action"]
            resources = [st["Resource"]] if isinstance(st["Resource"], str) else st["Resource"]
            if not any(fnmatch.fnmatchcase(action.lower(), a.lower()) for a in actions):
                continue
            if not any(fnmatch.fnmatchcase(resource, r) for r in resources):
                continue
            conditions = (st.get("Condition") or {}).get("StringEquals", {})
            if all(value in context.get(key, []) for key, value in conditions.items()):
                return True
        return False

    def simulate_custom_policy(self, **kw):
        self.calls.append(kw)
        policy = json.loads(kw["PolicyInputList"][0])
        context = {e["ContextKeyName"]: e["ContextKeyValues"] for e in kw.get("ContextEntries") or []}
        out = []
        for action in kw["ActionNames"]:
            for resource in kw.get("ResourceArns") or ["*"]:
                decision = (self.decide(action, resource) if self.decide else None) or (
                    "allowed" if self._allowed(policy, action, resource, context) else "implicitDeny")
                out.append({"EvalActionName": action, "EvalResourceName": resource, "EvalDecision": decision,
                            "MatchedStatements": [], "MissingContextValues": []})
        return {"EvaluationResults": out, "IsTruncated": False}


class FakeAnalyzer:
    def __init__(self, findings=()):
        self.findings, self.validated = list(findings), []

    def get_paginator(self, name):
        assert name == "validate_policy", name
        return self

    def paginate(self, **kw):
        self.validated.append(kw)
        return [{"findings": self.findings[:1]}, {"findings": self.findings[1:]}]


def _finding(kind, code, detail="detail text"):
    return {"findingType": kind, "issueCode": code, "findingDetails": detail,
            "locations": [{"path": [{"value": "Statement"}, {"index": 0}], "span": {}}],
            "learnMoreLink": "https://docs.aws.amazon.com/example"}


def _runtime_text():
    return (IAM_DIR / "runtime-policy.json").read_text(encoding="utf-8")


def test_every_probe_matches_the_runtime_policy_in_the_repo():
    rows = sp.simulate(FakeIam(), sp.concrete(_runtime_text()), sp.probes())
    wrong = [(r["action"], r["resource"], r["decision"], r["expected"]) for r in rows if not r["ok"]]
    assert rows and not wrong, wrong


def test_probes_cover_the_two_actions_the_app_uses_and_several_it_must_not_have():
    probes = sp.probes()
    allowed = {p["action"] for p in probes if p["expected"] == "allowed"}
    policy = json.loads(_runtime_text())
    policy_actions = {a for st in policy["Statement"]
                      for a in ([st["Action"]] if isinstance(st["Action"], str) else st["Action"])}
    assert allowed == policy_actions == {"bedrock:InvokeModel", "bedrock:ApplyGuardrail"}
    denied = {p["action"] for p in probes if p["expected"] == "implicitDeny"}
    not_in_policy = {"bedrock:CreateGuardrail", "bedrock:ListFoundationModels", "cloudwatch:PutMetricData"}
    assert not_in_policy <= denied and not not_in_policy & policy_actions
    assert {p["expected"] for p in probes} == {"allowed", "implicitDeny"}
    keys = [(p["action"], p["resource"], p["context"]) for p in probes]
    assert len(keys) == len(set(keys))                     # no probe is asked twice with two different answers


def test_probes_follow_config_so_a_model_id_that_drifts_from_the_policy_shows_as_a_mismatch(monkeypatch):
    monkeypatch.setattr(config, "MODEL_ID", "us.anthropic.claude-sonnet-9-9")
    rows = sp.simulate(FakeIam(), sp.concrete(_runtime_text()), sp.probes())
    wrong = [r for r in rows if not r["ok"]]
    assert wrong and all("claude-sonnet-9-9" in r["resource"] for r in wrong)


def test_the_global_foundation_model_needs_the_unspecified_region_context():
    rows = sp.simulate(FakeIam(), sp.concrete(_runtime_text()), sp.probes())
    global_fm = [r for r in rows if r["resource"].startswith("arn:aws:bedrock:::foundation-model/")]
    assert {r["expected"] for r in global_fm} == {"allowed", "implicitDeny"}   # unspecified allowed, us-east-1 not
    assert all(r["ok"] for r in global_fm)


def test_main_prints_the_table_with_masked_ids_and_exits_zero(capsys):
    iam, analyzer = FakeIam(), FakeAnalyzer()
    assert sp.main([], iam=iam, analyzer=analyzer) == 0
    out = capsys.readouterr().out
    assert "action" in out and "decision" in out and "expected" in out
    assert "bedrock:InvokeModel" in out and "bedrock:ApplyGuardrail" in out and "bedrock:CreateGuardrail" in out
    assert "<ACCOUNT_ID>" in out and "<GUARDRAIL_ID>" in out
    assert not re.search(r"(?<!\d)\d{12}(?!\d)", out) and sp.DUMMY_GUARDRAIL not in out
    n = len(sp.probes())
    assert f"{n} / {n}" in out and "as expected" in out
    assert "Traceback" not in out


def test_the_policy_text_sent_to_aws_has_no_placeholder_and_each_call_asks_one_action_on_one_resource():
    iam = FakeIam()
    sp.simulate(iam, sp.concrete(_runtime_text()), sp.probes())
    assert iam.calls and all("<ACCOUNT_ID>" not in c["PolicyInputList"][0] and "<GUARDRAIL_ID>" not in
                             c["PolicyInputList"][0] for c in iam.calls)
    assert all(len(c["ActionNames"]) == 1 and len(c["ResourceArns"]) == 1 for c in iam.calls)
    assert len(iam.calls) == len(sp.probes())   # one answer per (action, resource, context) pair
    assert all("<ACCOUNT_ID>" not in arn for c in iam.calls for arn in c.get("ResourceArns", []))
    contexts = [c.get("ContextEntries") for c in iam.calls if c.get("ContextEntries")]
    assert contexts and all(e["ContextKeyName"] == "aws:RequestedRegion" and e["ContextKeyType"] == "string"
                            for ctx in contexts for e in ctx)


def test_a_wrong_decision_is_marked_and_exits_one(capsys):
    iam = FakeIam(decide=lambda action, resource: "allowed" if action == "bedrock:CreateGuardrail" else None)
    assert sp.main([], iam=iam, analyzer=FakeAnalyzer()) == 1
    out = capsys.readouterr().out
    assert "MISMATCH" in out and out.count("MISMATCH") == 1


def test_a_question_the_simulator_rejects_is_its_own_row_and_the_rest_of_the_table_still_prints(capsys):
    class OneRejected(FakeIam):
        def simulate_custom_policy(self, **kw):
            if kw["ActionNames"] == ["bedrock:CreateGuardrail"]:
                raise _client_error("InvalidInput", "Action name is not valid")
            return super().simulate_custom_policy(**kw)
    assert sp.main([], iam=OneRejected(), analyzer=FakeAnalyzer()) == 1
    out = capsys.readouterr().out
    assert "error InvalidInput" in out and out.count("MISMATCH") == 1 and "bedrock:ApplyGuardrail" in out
    n = len(sp.probes())
    assert f"{n - 1} / {n}" in out


def test_access_denied_is_one_plain_line_not_a_traceback(capsys):
    class Denied:
        def simulate_custom_policy(self, **kw):
            raise _client_error("AccessDenied", "User: arn:aws:sts::123456789012:assumed-role/x/y is not authorized")
    assert sp.main([], iam=Denied(), analyzer=FakeAnalyzer()) == 1
    out = capsys.readouterr().out
    assert "iam:SimulateCustomPolicy" in out and "denied" in out.lower()
    assert "Traceback" not in out and "arn:aws:sts" not in out and "123456789012" not in out


def test_findings_are_listed_errors_fail_and_suggestions_do_not(capsys):
    soft = FakeAnalyzer([_finding("SUGGESTION", "EMPTY_ARRAY_ACTION")])
    assert sp.main([], iam=FakeIam(), analyzer=soft) == 0
    assert "SUGGESTION" in capsys.readouterr().out
    hard = FakeAnalyzer([_finding("SUGGESTION", "EMPTY_ARRAY_ACTION"), _finding("ERROR", "INVALID_ARN", "bad arn")])
    assert sp.main([], iam=FakeIam(), analyzer=hard) == 1
    out = capsys.readouterr().out
    assert "ERROR" in out and "INVALID_ARN" in out and "bad arn" in out


def test_access_analyzer_validates_both_repo_policies_as_identity_policies(capsys):
    analyzer = FakeAnalyzer()
    sp.main([], iam=FakeIam(), analyzer=analyzer)
    assert [kw["policyType"] for kw in analyzer.validated] == ["IDENTITY_POLICY", "IDENTITY_POLICY"]
    texts = [kw["policyDocument"] for kw in analyzer.validated]
    assert all("<ACCOUNT_ID>" not in t and "<GUARDRAIL_ID>" not in t for t in texts)
    assert {json.dumps(json.loads(t), sort_keys=True) for t in texts} == {
        json.dumps(json.loads(sp.concrete((IAM_DIR / n).read_text(encoding="utf-8"))), sort_keys=True)
        for n in ("runtime-policy.json", "admin-policy.json")}


def test_the_analyzer_failure_is_a_plain_line_and_the_table_still_prints(capsys):
    class Broken(FakeAnalyzer):
        def paginate(self, **kw):
            raise _client_error("AccessDeniedException")
    assert sp.main([], iam=FakeIam(), analyzer=Broken()) == 1
    out = capsys.readouterr().out
    assert "bedrock:InvokeModel" in out and "access-analyzer:ValidatePolicy" in out and "Traceback" not in out


def test_clients_come_from_the_standard_chain_in_the_configured_region(monkeypatch, capsys):
    built = []

    def fake_client(service, **kwargs):
        built.append((service, kwargs))
        return FakeIam() if service == "iam" else FakeAnalyzer()
    monkeypatch.setattr(sp.boto3, "client", fake_client)
    assert sp.main([]) == 0
    assert [s for s, _ in built] == ["iam", "accessanalyzer"]
    for _, kwargs in built:
        assert set(kwargs) == {"config"} and kwargs["config"].region_name == config.REGION == "us-east-1"
    capsys.readouterr()


def test_the_two_scripts_make_no_call_that_creates_changes_or_deletes_anything():
    import ast
    write_verb = re.compile(r"^(create|update|delete|put|attach|detach|tag|untag|start|stop|import|publish|register|"
                            r"deregister|modify|enable|disable|associate|disassociate|ensure)_")
    for name in ("preflight.py", "simulate_policy.py"):
        tree = ast.parse((pathlib.Path(__file__).resolve().parents[1] / "scripts" / name).read_text(encoding="utf-8"))
        called = {n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
                  for n in ast.walk(tree) if isinstance(n, ast.Call)}
        assert not {c for c in called if write_verb.match(c)}, (name, called)
        imported = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
                    for a in n.names} | {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        assert not {i for i in imported if "create_guardrail" in i}, (name, imported)


def test_the_script_documents_that_it_creates_and_changes_nothing():
    doc = sp.__doc__
    assert "creates and changes nothing" in doc and "iam:SimulateCustomPolicy" in doc
    assert "access-analyzer:ValidatePolicy" in doc and "account id" in doc


# ---------------------------------------------------------------------------------------------------------------
# Task 11: scripts/eval.py, the measured answer to "why does this agent exist?" (spec §24 resolutions 6 and 12;
# ledger §29 and §30). Offline: every model, guardrail and pipeline call is a seam the tests replace.
# ---------------------------------------------------------------------------------------------------------------
import hashlib  # noqa: E402
from pathlib import Path  # noqa: E402

import pandas as pd  # noqa: E402

from scripts import eval as ev  # noqa: E402
from tools.data import make_market  # noqa: E402


def test_wilson_and_evidence_levels():
    lo, hi = ev.wilson(8, 10)
    assert (round(lo, 3), round(hi, 3)) == (0.490, 0.943) and ev.wilson(0, 0) == (None, None)
    assert ev.evidence_level(30) == "Measured" and ev.evidence_level(29) == "Indicative"
    r = ev.rate(8, 10, model="m", limit="one line")
    assert r["text"] == "8 / 10" and r["level"] == "Indicative" and r["model"] == "m"


def test_question_set_is_frozen_and_balanced():
    assert len(ev.QUESTIONS) == 40 and len({q["id"] for q in ev.QUESTIONS}) == 40
    for g in ("rephrase", "headline", "combined", "vague"):
        assert sum(q["group"] == g for q in ev.QUESTIONS) == 10
    assert all(set(q["families"]) <= {"tariffs", "war_oil", "chips", "rates"} for q in ev.QUESTIONS)
    assert all(q["clarify"] for q in ev.QUESTIONS if q["group"] == "vague")
    assert all(q["change"] for q in ev.QUESTIONS if q["group"] == "combined") and len(ev.ADVERSARIAL) == 6


def test_score_plan():
    c01 = next(q for q in ev.QUESTIONS if q["id"] == "c01")
    plan = {"type": "change", "families": ["tariffs"], "event_ids": ["e1"], "clarify": None,
            "change": {"op": "set", "ticker": "NVDA", "weight": 0.40, "from_ticker": None}}
    fam = {"e1": "tariffs"}
    assert all(ev.score_plan(plan, c01, families_of=fam).values())
    assert ev.score_plan({**plan, "change": {**plan["change"], "weight": 0.30}}, c01, families_of=fam)["change_ok"] is False


def test_invented_numbers_ignores_question_numbers_and_years():
    ans = "In 2022 NVIDIA fell 62 %; with 40 % in it you could lose $90,000."
    assert ev.invented_numbers(ans, "What if I put 40 % in NVIDIA?", {"XIU.TO": 0.45}) == 2


def test_main_writes_rates_with_n_and_model(tmp_path, monkeypatch):
    def perfect(question, portfolio, catalog, as_of, **kw):
        q = next(x for x in ev.QUESTIONS if x["question"] == question)
        ch = q["change"] and dict(zip(("op", "ticker", "weight", "from_ticker"), q["change"]))
        return {"type": q["type"], "families": q["families"], "event_ids": ["e1"] if q["precedent"] else [],
                "clarify": "Which one?" if q["clarify"] else None, "change": ch, "ms": 900,
                "usage": {"inputTokens": 1000, "outputTokens": 100, "totalTokens": 1100}, "method": "bedrock"}
    monkeypatch.setattr(ev, "navigator", perfect)
    monkeypatch.setattr(ev, "fallback", lambda *a, **k: {"type": "fit", "families": [], "event_ids": [], "clarify": None,
                                                          "change": None, "ms": 1, "usage": None, "method": "fallback"})
    monkeypatch.setattr(ev, "pilot_context", lambda p: {"portfolio": {"XIU.TO": 1.0}, "profile": None, "amount": 1.0,
        "exposure": None, "universe": None, "catalog": [{"event_id": "e1", "family": "tariffs", "known": True}]})
    out = tmp_path / "eval.md"
    assert ev.main(["--only", "B,C", "--limit", "3", "--out", str(out)]) == 0
    text = out.read_text()
    assert "3 / 3" in text and "0 / 3" in text and "Wilson" in text and "Indicative" in text
    assert "did not beat" not in text.splitlines()[0]


def test_walk_forward_uses_month_ends_and_reports_breaches():
    dates = pd.bdate_range("2022-01-03", periods=500)
    prices = pd.DataFrame({"AAA": [100 - 0.05 * i for i in range(500)]}, index=dates)
    m = make_market(prices, as_of=dates[-1].strftime("%Y-%m-%d"))
    pilots = {"x": {"profile": {"goal": "preservation", "horizon_years": 4, "risk": "low", "esg": False, "crypto": False,
                                "capacity": None, "reaction_2022": None},
                    "portfolio": {"AAA": 1.0}, "amount": 100_000, "request": None}}
    rows = ev.walk_forward(pilots, start="2022-02-28", end="2022-06-30", market=m, events=[])
    assert [r["as_of"] for r in rows] == ["2022-02-28", "2022-03-31", "2022-04-29", "2022-05-31", "2022-06-30"]
    assert set(rows[0]) == {"pilot", "as_of", "verdict", "realized_drop", "floor", "breached"}
    assert all(isinstance(r["breached"], bool) for r in rows)


# ---- extras (the AI lead's file): the rulings the brief could not know (dispatch of B Task 11; ledger §29, §30) ----
HELDOUT_SOURCE = Path("/tmp/epi_eval/heldout.json")


def test_heldout_is_imported_verbatim_and_frozen():
    """The 10 blind items are frozen by hash; when the source file is on this machine it must parse to the same data."""
    assert hashlib.sha256(ev.HELDOUT_TEXT.encode("utf-8")).hexdigest() == ev.HELDOUT_SHA256
    assert [h["id"] for h in ev.HELDOUT] == [f"h{i:02d}" for i in range(1, 11)]
    assert sum(h["expect"]["blocked"] for h in ev.HELDOUT) == 2
    if HELDOUT_SOURCE.exists():
        assert json.loads(HELDOUT_SOURCE.read_text(encoding="utf-8")) == ev.HELDOUT


def test_score_heldout_conventions():
    """Weight is a fraction; a replace is scored on the share moved; families is a set; no precedent means no event;
    a clarify item must not carry an invented weight."""
    by_id = {h["id"]: h for h in ev.HELDOUT}
    fam = {"e1": "rates", "e2": "war_oil", "e3": "tariffs"}
    swap = {"type": "change", "families": ["rates"], "event_ids": ["e1"], "clarify": None,
            "change": {"op": "replace", "ticker": "XBB.TO", "weight": None, "from_ticker": "TD.TO"}}
    assert all(ev.score_heldout(swap, by_id["h09"], families_of=fam, portfolio={"TD.TO": 0.20, "XIU.TO": 0.80}).values())
    assert not ev.score_heldout(swap, by_id["h09"], families_of=fam, portfolio={"TD.TO": 0.30, "XIU.TO": 0.70})["change_ok"]
    two = {"type": "change", "families": ["tariffs", "war_oil"], "event_ids": ["e2", "e3"], "clarify": None,
           "change": {"op": "set", "ticker": "GLD", "weight": 0.10, "from_ticker": None}}
    assert all(ev.score_heldout(two, by_id["h10"], families_of=fam, portfolio={"GLD": 0.05}).values())
    storm = {"type": "change", "families": [], "event_ids": [], "clarify": None,
             "change": {"op": "add", "ticker": "XIU.TO", "weight": 0.10, "from_ticker": None}}
    assert all(ev.score_heldout(storm, by_id["h05"], families_of=fam, portfolio={"XIU.TO": 0.5}).values())
    ask = {"type": "change", "families": [], "event_ids": [], "clarify": "How large is the portfolio?", "change": None}
    scored = ev.score_heldout(ask, by_id["h06"], families_of=fam, portfolio={})
    assert scored["clarify_ok"] and scored["change_ok"] and not scored["families_ok"]


def test_receipt_pass_keys_on_defects_never_on_verified_total():
    """Ledger §30: clean = defects == [], never verified == total."""
    looks_clean = {"verified": 5, "total": 5, "defects": ["Sentence 2 says the value fell"],
                   "first_try": {"verified": 5, "total": 5, "defects": ["Sentence 2 says the value fell"]}, "drafts": 2}
    assert ev.receipt_pass({"receipt": looks_clean}) == {"first_try": False, "final": False, "drafts": 2}
    fixed = {"verified": 4, "total": 5, "defects": [], "first_try": {"verified": 3, "total": 5, "defects": ["x"]},
             "drafts": 2}
    assert ev.receipt_pass({"receipt": fixed}) == {"first_try": False, "final": True, "drafts": 2}
    assert ev.receipt_pass({"receipt": None}) == {"first_try": None, "final": None, "drafts": None}


def test_cost_is_priced_per_model_with_a_dated_list_price():
    sonnet, haiku = ev.config.MODEL_ID, ev.config.MODEL_ID_HAIKU
    usage = {"inputTokens": 1_000_000, "outputTokens": 100_000, "cacheReadInputTokens": 1_000_000,
             "cacheWriteInputTokens": 0}
    assert ev.cost_usd(usage, sonnet) == pytest.approx(2.00 + 1.00 + 0.20)
    assert ev.cost_usd({"inputTokens": 1_000_000, "outputTokens": 0}, haiku) == pytest.approx(0.10)
    assert ev.cost_usd(usage, "some.unpriced-model") is None and ev.cost_usd(None, sonnet) is None
    assert "list price as of " + ev.PRICE_AS_OF in ev.price_label() and "Bedrock bills separately" in ev.price_label()


class _FakeRuntime:
    def __init__(self, text="With 40 % in NVIDIA you could lose 62 %. You should hold."):
        self.text, self.requests = text, []

    def converse(self, **request):
        self.requests.append(request)
        return {"output": {"message": {"content": [{"text": self.text}]}}, "stopReason": "end_turn",
                "usage": {"inputTokens": 120, "outputTokens": 30, "totalTokens": 150}, "metrics": {"latencyMs": 800}}


def test_model_alone_is_one_plain_converse_call_with_the_same_request_fields(monkeypatch):
    monkeypatch.delenv("EPICENTRE_NAVIGATOR_MODEL_ID", raising=False)
    monkeypatch.delenv("EPICENTRE_MODEL_ID", raising=False)
    fake = _FakeRuntime()
    out = ev.model_alone("What if I put 40 % in NVIDIA?", {"XIU.TO": 0.45, "XBB.TO": 0.55}, client=fake)
    (req,) = fake.requests
    assert req["system"] == [{"text": ev.SYSTEM_A}] and req["inferenceConfig"] == {"maxTokens": 1500}
    assert req["additionalModelRequestFields"] == ev.config.request_fields(ev.config.MODEL_ID)
    assert '"XIU.TO": 0.45' in req["messages"][0]["content"][0]["text"] and "tools" not in req
    assert out["model"] == ev.config.MODEL_ID and out["text"] == fake.text and out["usage"]["outputTokens"] == 30
    assert ev.advice_words(out["text"]) == 2


def _arm(k_fam, n=40):
    rows = [{"id": f"q{i}", "group": "rephrase", "scores": {"families_ok": i < k_fam, "events_ok": True, "change_ok": True,
             "clarify_ok": True, "type_ok": True}, "ms": 10.0, "usd": 0.001, "method": "bedrock"} for i in range(n)]
    return {"rows": rows, "model": "m", "date": "2026-11-15"}


def test_first_line_says_so_when_the_navigator_does_not_beat_the_fallback():
    meta = {"date": "2026-11-15", "commit": "abc1234", "models": {}}
    lost = ev.render({"meta": meta, "B": _arm(30), "C": _arm(30)})
    assert lost.splitlines()[0] == ev.DID_NOT_BEAT
    won = ev.render({"meta": meta, "B": _arm(20), "C": _arm(31)})
    assert ev.DID_NOT_BEAT not in won and "no-data baseline" not in won.splitlines()[0]
    assert "31 / 40" in won and "Measured" in won


def test_stability_needs_the_same_reading_three_times():
    a = {"families": ["tariffs"], "clarify": None, "change": {"op": "set", "ticker": "NVDA", "weight": 0.4,
                                                              "from_ticker": None}}
    assert ev.same_reading([a, dict(a), dict(a)]) is True
    assert ev.same_reading([a, {**a, "families": ["tariffs", "chips"]}, a]) is False
    assert ev.same_reading([a, {**a, "change": {**a["change"], "weight": 0.400001}}, a]) is True


def test_the_loop_arm_joins_when_its_engine_is_built(monkeypatch):
    monkeypatch.setattr(ev.scenario, "ENGINES_BUILT", ("converse",))
    assert ev.engine_arms() == ["converse"]
    monkeypatch.setattr(ev.scenario, "ENGINES_BUILT", ("converse", "loop"))
    assert ev.engine_arms() == ["converse", "loop"]


def test_a_guardrail_check_that_did_not_answer_is_neither_a_block_nor_a_pass():
    """Regression (dry run, 2026-11-14): with no guardrail id exported every check errored and read as "not blocked"."""
    ok = {"id": "r01", "expect_blocked": False, "blocked": False, "action": "NONE", "topic_hit": False,
          "prompt_attack": False, "error": None, "grounding": None, "relevance": None}
    hit = {**ok, "id": "pilot:robert", "blocked": True, "topic_hit": True, "action": "GUARDRAIL_INTERVENED"}
    down = {**ok, "id": "r02", "action": "ERROR", "error": "The safety check is not configured."}
    text = ev.render({"meta": {}, "guardrail": {"rows": [ok, hit, down], "date": "2026-11-15", "version": "DRAFT"}})
    assert "- False blocks: 1 / 2 " in text and "did not answer" in text and "pilot:robert (denied topic)" in text


def test_memory_is_the_earlier_runs_defect_types_most_frequent_first():
    rows = [{"types": ["advice", "too_long"]}, {"types": ["too_long"]}, {"types": []}, {"types": ["wrong_side", "advice",
            "too_long"]}, {"types": ["unknown_ref", "future_date", "spelled_number"]}]
    assert ev.remembered(rows) == ["too_long", "advice", "wrong_side", "future_date", "spelled_number"]
    assert ev.remembered([{"types": []}]) == [] and ev.run_memory({"rows": [{"types": []}]})["skipped"]


def test_the_memory_engine_opens_every_debrief_with_the_remembered_types(monkeypatch):
    import dataclasses
    import pipeline

    @dataclasses.dataclass
    class Fake:
        explain: object
        load_events: object = None
        memory: object = "agents.memory"          # the product's engine reads and records data/cache/defect_memory.json
    seen = []
    monkeypatch.setattr(pipeline, "real_engine", lambda: Fake(explain=lambda facts, *a, **kw: seen.append(kw) or {}))
    engine = ev.memory_engine(["advice", "too_long"])
    engine.explain({"T1": {}}, ["a defect"], None, context=None)
    assert seen == [{"memory": ["advice", "too_long"], "context": None}]
    assert engine.memory is None                   # so the pipeline never replaces these types with the file's


def test_the_receipt_arms_never_read_or_record_the_products_memory_file(monkeypatch):
    """Ruling R4 wired the memory into the pipeline: the real engine reads data/cache/defect_memory.json before draft 1
    and records into it after each run. The "without memory" arm would then carry the types of the runs before it (and
    write the file): both arms run on an engine with no memory, so section 10 compares exactly what it says."""
    import dataclasses
    import pipeline

    @dataclasses.dataclass
    class Fake:
        explain: object
        memory: object = "agents.memory"
    monkeypatch.setattr(pipeline, "real_engine", lambda: Fake(explain=lambda *a, **kw: {}))
    seen = []
    monkeypatch.setattr(ev, "_one_run", lambda rid, fp, q, engine=None: seen.append((rid, engine)) or {"types": []})
    monkeypatch.setattr(ev, "_flight", lambda pilot: {"pilot": pilot})
    monkeypatch.setattr(ev, "personas", lambda: {"storm_cards": {"tariffs": {"question": "q"}}})
    ev.run_receipt()
    assert [rid for rid, _ in seen] == ["robert:tariffs", "mateo:tariffs", "amira:tariffs"]
    assert all(isinstance(e, Fake) and e.memory is None for _, e in seen)
    assert ev.receipt_engine().memory is None


def test_defect_types_reads_types_only():
    rc = {"defects": ["The debrief has 230 words; the limit is 180."], "unverified": [{"sentence": 2}],
          "first_try": {"verified": 3, "total": 5, "defects": ["Sentence 3 refers to something dated after 2026-11-12."]}}
    assert ev.defect_types(rc) == ["unverified_number", "too_long", "future_date"]
    assert ev.defect_types(None) == []


def test_loop_is_compared_with_the_one_call_engine_on_the_same_questions():
    meta = {"date": "2026-11-15", "commit": "abc1234", "models": {}, "engines": ["converse", "loop"]}
    same = {"meta": meta, "B": _arm(10), "C": _arm(30), "loop": _arm(30)}
    assert ev.loop_at_least_as_good(same) and "at least as good" in ev.render(same)
    worse = {**same, "loop": _arm(29)}
    assert not ev.loop_at_least_as_good(worse) and "not as good" in ev.render(worse)


def test_the_calls_table_counts_from_the_rows():
    rows = [{"calls": 2, "guard_calls": 2}, {"calls": 1, "guard_calls": 1}]
    text = ev.render({"meta": {}, "receipt": {"rows": [{**r, "first_try": True, "final": True, "steps": {}, "ms": 1.0,
                                                       "usd": 0.0} for r in rows], "model": "m", "date": "d"},
                      "A": {"rows": [{"id": "r01", "group": "rephrase", "invented": 0, "advice": 0, "ms": 1.0,
                                      "usd": 0.0, "error": None}], "model": "m", "date": "d"}})
    assert "| receipt | 3 | 3 |" in text and "| A | 1 | 0 |" in text


def test_a_flagged_clean_control_means_the_gap_flags_do_not_discriminate():
    row = {"class": "causal claim, no new number", "label": "x", "grounding": 0.5, "threshold": 0.7,
           "grounding_flag": True, "relevance": 0.99, "relevance_flag": False, "topic_hit": False, "error": None}
    gaps = {"rows": [{**row, "class": "clean debrief (control)"}, row], "date": "2026-11-15", "threshold": 0.7}
    text = ev.render({"meta": {}, "gaps": gaps})
    assert "1 / 1 (95 % Wilson" in text and "do not tell a known-gap copy from a clean debrief" in text
    clean = {**gaps, "rows": [{**row, "class": "clean debrief (control)", "grounding": 0.9, "grounding_flag": False}, row]}
    assert "do not tell" not in ev.render({"meta": {}, "gaps": clean})


def _scored(score, *, cls="causal claim, no new number", label="x", relevance=0.5):
    return {"class": cls, "label": label, "grounding": score, "threshold": 0.7, "grounding_flag": score < 0.7,
            "relevance": relevance, "relevance_flag": relevance < 0.7, "topic_hit": False, "error": None}


def test_section_8_says_plainly_when_clean_text_passes_but_the_copies_pass_too():
    """Lane gr (Sun Nov 15): grounding and relevance are counted apart; clean above and most copies above too means
    the score does not separate them, so it stays advisory and the receipt stays the gate."""
    rows = [_scored(0.89, cls="clean debrief (control)", label="no change"),
            _scored(0.87, cls="clean saved run", label="robert", relevance=1.0),
            _scored(0.38), _scored(0.88), _scored(0.85, cls="advice wording outside the list")]
    text = ev.render({"meta": {}, "gaps": {"rows": rows, "date": "2026-11-15", "threshold": 0.7, "source": "sentences",
                                           "commit": "abc1234", "version": "1"}})
    assert "- Measured on 2026-11-15 at commit abc1234, guardrail version 1" in text
    assert "- Grounding source: the facts rows as plain sentences, opened by the verdict" in text
    assert "- The clean debrief (control): grounding 0.89, relevance 0.50" in text
    assert "- The clean debriefs of the saved runs (receipt clean): grounding robert 0.87; relevance robert 1.00" in text
    assert "- Known-gap copies under the grounding threshold: 1 / 3 (95 % Wilson" in text
    assert "- causal claim, no new number: 1 / 2 under the grounding threshold" in text
    assert "- Grounding scores of the copies: 0.38 to 0.88 (median 0.85)" in text
    assert ("- Relevance (not shown on the page): 3 / 3 copies under its threshold, and 1 / 2 clean debriefs, so a "
            "low relevance does not single out a copy either") in text
    assert "does not separate them: it stays advisory" in text and "do not tell" not in text


def test_section_8_names_a_separation_only_when_the_copies_score_below_and_old_rows_say_json():
    rows = [_scored(0.89, cls="clean debrief (control)", label="no change"), _scored(0.4), _scored(0.5)]
    text = ev.render({"meta": {}, "gaps": {"rows": rows, "date": "2026-11-15", "threshold": 0.7, "source": "sentences"}})
    assert "the grounding score separates them on these copies" in text and "does not separate" not in text
    most = [rows[0], _scored(0.4), _scored(0.5), _scored(0.9)]
    text = ev.render({"meta": {}, "gaps": {"rows": most, "date": "2026-11-15", "threshold": 0.7, "source": "sentences"}})
    assert "most known-gap copies below it (2 / 3): a real signal, still advisory" in text
    old = ev.render({"meta": {}, "gaps": {"rows": rows, "date": "2026-11-14", "threshold": 0.7}})
    assert "- Grounding source: the facts JSON; scored: the sentences with their [T#] tags (the measurement" in old


def test_section_8_keeps_the_earlier_json_measurement_under_its_own_heading():
    """The re-score supersedes the facts-JSON measurement; both stay readable (the receipt_earlier pattern)."""
    new = {"rows": [_scored(0.89, cls="clean debrief (control)", label="no change"), _scored(0.88)],
           "date": "2026-11-15", "threshold": 0.7, "source": "sentences", "commit": "aaa1111", "version": "1"}
    old = {"rows": [_scored(0.52, cls="clean debrief (control)", label="no change"), _scored(0.4)],
           "date": "2026-11-14", "threshold": 0.7, "commit": "b4a21e2"}
    sec8 = ev.render({"meta": {}, "gaps": new, "gaps_earlier": old}).split("## 8.")[1].split("## 9.")[0]
    head = "Earlier measurement (2026-11-14, code at commit b4a21e2), superseded by the lines above:"
    assert sec8.index("at commit aaa1111, guardrail version 1") < sec8.index("does not separate") < sec8.index(head)
    later = sec8[sec8.index(head):]
    assert "- Grounding source: the facts JSON; scored: the sentences with their [T#] tags" in later
    assert "- The clean debrief (control): grounding 0.52" in later and "do not tell a known-gap copy" in later
    assert "Earlier measurement" not in ev.render({"meta": {}, "gaps": new})
    assert "Measured on 2026-11-14" not in later        # no version on record: the heading carries date and commit


def test_run_gaps_scores_each_copy_the_way_the_pipeline_scores_a_shown_draft(monkeypatch, tmp_path):
    import guardrail
    import pipeline
    from scripts import receipt_mutation as rm
    seen = []

    def guard(text, source, facts=None, query=None, **k):
        seen.append((text, source, facts, query))
        return {"grounding": {"score": 0.9, "threshold": 0.7, "detected": False}, "topic_hit": False, "error": None,
                "relevance": {"score": 0.8, "threshold": 0.7, "detected": False}}
    monkeypatch.setattr(ev, "guard", guard)
    clean = {"question": "What if?", "as_of": "2026-11-12", "verdict": "Compatible", "checks": [],
             "facts": {"T1": {"label": "Worst drop today", "value": -0.1, "unit": "pct", "kind": "fact"}},
             "debrief": {"verdict_sentence": "Inside your limits: none broke.", "sections": {"data": [0]},
                         "sentences": [{"text": "The portfolio today fell 10.0 % [T1].", "kind": "fact"}]},
             "receipt": {"defects": []}}
    (tmp_path / "robert.json").write_text(json.dumps(clean), encoding="utf-8")
    (tmp_path / "flagged.json").write_text(json.dumps({**clean, "receipt": {"defects": ["x"]}}), encoding="utf-8")
    monkeypatch.setenv(config.ENV_GUARDRAIL_VERSION, "1")
    out = ev.run_gaps(tmp_path)
    assert out["source"] == "sentences" and out["version"] == "1" and len(out["rows"]) == 1 + len(rm.known_gaps()) + 1
    assert [r["class"] for r in out["rows"]][0] == "clean debrief (control)" and out["rows"][-1]["label"] == "robert"
    want = guardrail.grounding_source(rm.FACTS, pipeline.grounding_context(rm.RESULT))
    assert want.startswith("These results replay real market history up to the decision date, 2026-11-12.")
    question = ev.personas()["pilots"]["robert"]["question"]
    assert all(src == "OUTPUT" and facts == want and q == question for _, src, facts, q in seen[:-1])
    assert all("[T" not in text for text, *_ in seen)
    assert seen[0][0] == pipeline._guard_text(rm.build())                     # the control: the clean debrief as shown
    text, _, facts, q = seen[-1]
    assert text == pipeline._guard_text(clean["debrief"]) and "[T" not in text and q == "What if?"
    assert facts.startswith("These results replay real market history up to the decision date, 2026-11-12.")
    assert "Worst drop today: a fall of 10.0 % (T1, fact)." in facts and "None of your limits broke." in facts
    assert ev.run_gaps(tmp_path / "missing")["rows"][-1]["class"] != "clean saved run"   # no folder: the copies only


def test_the_walk_forward_is_never_measured_its_windows_overlap():
    rows = [{"pilot": "x", "as_of": f"2022-{m:02d}-28", "verdict": "Incompatible", "realized_drop": -0.3, "floor": -0.15,
             "breached": m % 2 == 0} for m in range(1, 13)] * 3
    text = ev.render({"meta": {}, "walk": {"rows": rows, "date": "2026-11-15"}})
    line = next(x for x in text.splitlines() if "Outside your limits" in x)
    assert "18 / 36" in line and "Measured" not in line and "Indicative (overlapping" in line
    assert "no month-end gave this verdict" in text


def test_the_json_summary_carries_the_measurement_date_and_commit():
    c = {**_arm(31), "commit": "b4a21e2", "date": "2026-11-14"}
    out = ev.summary_json({"meta": {"date": "2026-11-15", "commit": "e6502f8", "models": {}}, "C": c, "B": _arm(20)})
    assert (out["date"], out["commit"], out["rendered_at"]) == ("2026-11-14", "b4a21e2", "e6502f8")
    assert [a["arm"] for a in out["arms"]] == ["navigator", "keyword_fallback"] and out["arms"][0]["k"] == 31


# ---------------------------------------------------------------------------------------------------------------
# Task 11 fix round 1 (review of 2026-11-15): Wilson on every group rate, the two sets read together, each arm names
# its engine, the walk-forward is portfolios not dates, the known defects of the measured runs are in the limit lines.
# ---------------------------------------------------------------------------------------------------------------
_CTX = {"portfolio": {"XIU.TO": 1.0}, "profile": None, "amount": None, "exposure": None, "universe": None,
        "catalog": []}


def test_every_navigator_arm_passes_its_engine_by_name_so_a_flipped_default_cannot_relabel_a_rate(monkeypatch):
    """Review Important 3: "converse" used to mean "whatever the default engine is"."""
    seen = []

    def fake(question, portfolio, catalog, as_of, **kw):
        seen.append(kw.get("engine"))
        return {"type": "shock", "families": [], "event_ids": [], "clarify": None, "change": None}
    monkeypatch.setattr(ev, "navigator", fake)
    monkeypatch.setattr(ev.config, "SCENARIO_ENGINE", "loop")            # the default flipped: arms must not follow it
    monkeypatch.setenv("EPICENTRE_SCENARIO_ENGINE", "loop")
    ev.read_one("converse", "q", _CTX)
    ev.read_one("loop", "q", _CTX)
    assert seen == ["converse", "loop"]


def test_stability_and_the_model_per_job_read_the_converse_engine_by_name(monkeypatch):
    seen = []

    def fake(question, portfolio, catalog, as_of, **kw):
        seen.append(kw.get("engine"))
        return {"type": "shock", "families": ["tariffs"], "event_ids": [], "clarify": None, "change": None}
    monkeypatch.setattr(ev, "navigator", fake)
    monkeypatch.setattr(ev, "pilot_context", lambda p: _CTX)
    monkeypatch.setenv("EPICENTRE_SCENARIO_ENGINE", "loop")
    ev.run_stability(None)
    assert seen and set(seen) == {"converse"}
    seen.clear()
    ev.run_models([ev.QUESTIONS[0]], jobs=("navigator",))
    assert seen == ["converse"]


def _grp_arm(spec, model="m", day="2026-11-14"):
    """Rows per group: spec = {group: (families right, whole reading right, n)}."""
    rows = []
    for g, (kf, kw, n) in spec.items():
        for i in range(n):
            rows.append({"id": f"{g}{i}", "group": g, "ms": 10.0, "usd": 0.001, "method": "bedrock",
                         "scores": {"families_ok": i < kf, "events_ok": True, "change_ok": True, "clarify_ok": True,
                                    "type_ok": i < kw}})
    return {"rows": rows, "model": model, "date": day}


SPEC_B = {"rephrase": (0, 0, 10), "headline": (10, 8, 10), "combined": (10, 8, 10), "vague": (9, 9, 10)}
SPEC_C = {"rephrase": (9, 9, 10), "headline": (10, 10, 10), "combined": (8, 8, 10), "vague": (10, 10, 10)}
SONNET = "us.anthropic.claude-sonnet-5-5"


def _two_arms(**extra):
    return {"meta": {}, "B": _grp_arm(SPEC_B, "no model"), "C": _grp_arm(SPEC_C, SONNET), **extra}


def test_every_group_cell_carries_its_wilson_interval_and_the_legend_names_model_date_level_limit():
    """Review Important 1: the group rates (N = 10) had no interval."""
    text = ev.render(_two_arms())
    row = next(x for x in text.splitlines() if x.startswith("| rephrase |"))
    assert "0 / 10 (0.0–27.8 %)" in row and "9 / 10 (59.6–98.2 %)" in row
    assert "10 / 10 (72.2–100.0 %)" in next(x for x in text.splitlines() if x.startswith("| headline |"))
    legend = next(x for x in text.splitlines() if "each cell is k / N (95 % Wilson" in x)
    assert "Indicative" in legend and SONNET in legend and "no model" in legend and "2026-11-14" in legend
    assert "limit:" in legend


def test_the_40_are_labelled_the_development_set_and_the_rephrase_group_is_named_by_design():
    """Review Important 2: 37 / 40 against 29 / 40 is one group built to defeat the keyword rules."""
    text = ev.render(_two_arms())
    assert "## 1. The 40 development questions" in text and "development set" in text
    assert "no keyword of the fallback" in text and "by design" in text
    assert "(the finance lead reviews" not in text            # the finance lead has left; no finance review is on record


def test_the_other_30_questions_are_read_apart_with_the_full_rate_pattern():
    text = ev.render(_two_arms())
    lines = [x for x in text.splitlines() if "other 30" in x]
    kw = next(x for x in lines if "keyword" in x and "families right" in x)
    assert "29 / 30 (95 % Wilson 83.3–99.4 %)" in kw and "no model" in kw and "Measured" in kw and "limit:" in kw
    cv = next(x for x in lines if "converse" in x and "families right" in x)
    assert "28 / 30 (95 % Wilson 78.7–98.2 %)" in cv and SONNET in cv and "2026-11-14" in cv
    assert any("within one question of each other" in x for x in lines)           # 29 vs 28: level on families
    whole = next(x for x in lines if "whole reading" in x and "spread" in x)
    assert "3 questions" in whole                                                   # keyword 25 vs converse 28


def test_an_earlier_receipt_measurement_stays_labelled_with_its_date_and_commit():
    """Sections 5 and 10 re-measured on later code keep the earlier numbers, computed from their own rows and labelled
    with the date and commit they were measured on (results["receipt_earlier"] / ["memory_earlier"]); the current
    measurement comes first and the earlier one is said to be superseded."""
    def sec(first, final, day, commit, memory=None):
        rows = [{"first_try": f, "final": g, "drafts": 1 if f else 2, "types": [] if f else ["wrong_entity"],
                 "steps": {"EXPLAIN": 9000.0}, "ms": 15000.0, "usd": 0.03, **({"named": 0 if f else 1} if day > "2026-11-14" else {})}
                for f, g in zip(first, final)]
        return {"rows": rows, "model": "m", "date": day, "commit": commit, **({"memory": memory} if memory else {})}
    new, old = sec([True, True, False], [True, True, True], "2026-11-15", "c0ffee1"), \
        sec([False] * 3, [False, False, True], "2026-11-14", "b4a21e2")
    results = {"meta": {}, "receipt": new, "memory": {**new, "memory": ["wrong_entity"]},
               "receipt_earlier": old, "memory_earlier": {**sec([False] * 3, [True, True, False], "2026-11-14",
                                                                "b4a21e2"), "memory": ["wrong_entity", "wrong_kind"]}}
    text = ev.render(results)
    s5, s10 = text.split("\n## 5. ")[1].split("\n## 6")[0], text.split("\n## 10. ")[1].split("\n## 11")[0]
    now5, then5 = s5.split("Earlier measurement")
    assert "first-try receipt pass (the receipt names no defect on draft 1): 2 / 3" in now5 and "2026-11-15" in now5
    assert then5.startswith(" (2026-11-14, code at commit b4a21e2), superseded by the lines above:")
    assert "first-try receipt pass (the receipt names no defect on draft 1): 0 / 3" in then5 and "after the one re-ask: 1 / 3" in then5
    assert "first draft shown as written (no check named a defect, so no re-ask): 2 / 3" in now5
    assert "first draft shown as written (no check named a defect, so no re-ask): 0 / 3" in then5
    assert "- Defect types named on a draft (the receipt and the explainer's own checks; runs showing each, types only): wrong_entity 1 / 3" in now5
    assert "- Defect types the receipt named (runs showing each, types only): wrong_entity 3 / 3" in then5
    now10, then10 = s10.split("Earlier measurement")
    assert "Remembered types: wrong_entity" in now10 and "First-try receipt pass with memory: 2 / 3" in now10
    assert then10.startswith(" (2026-11-14, code at commit b4a21e2), superseded by the lines above:")
    assert "Remembered types: wrong_entity, wrong_kind" in then10 and "Receipt pass after the one re-ask with memory: 2 / 3" in then10
    assert "First-try receipt pass without memory: 0 / 3" in then10                  # its own base: the earlier receipt rows
    assert "Earlier measurement" not in ev.render({**results, "receipt_earlier": None, "memory_earlier": None})
    assert "| receipt | 0 | not recorded |" in text and "receipt_earlier" not in text  # the calls table: this run only


def test_a_run_counts_the_defects_named_for_its_re_ask_as_the_product_remembers_them(monkeypatch):
    """A draft the receipt passes can still be re-asked: the explainer's own checks (a debrief too long...) or the
    output check named a defect. Those lines are the second draft's retry_numbers in the trace, and the product's
    memory records their types (pipeline._memory_record), so a run's `types` holds them too (types only, never text)."""
    too_long = "The debrief has 230 words; the limit is 180."
    res = {"status": "ok", "debrief": {"sections": {}}, "scenario": {"method": "bedrock"},
           "receipt": {"verified": 9, "total": 9, "defects": [], "drafts": 2,
                       "first_try": {"verified": 9, "total": 9, "defects": []}},
           "trace": [{"step": "EXPLAIN", "tool": "explain.draft", "inputs": {"facts": 30}, "outputs": {"text": "x"}},
                     {"step": "EXPLAIN", "tool": "explain.draft", "inputs": {"facts": 30, "retry_numbers": [too_long]},
                      "outputs": {"text": "y"}}]}
    monkeypatch.setattr(ev, "pipeline_run", lambda *a, **k: res)
    row = ev._one_run("mateo:tariffs", {}, "q")
    assert (row["first_try"], row["final"], row["drafts"], row["types"]) == (True, True, 2, ["too_long"])
    assert too_long not in json.dumps({k: v for k, v in row.items() if k != "result"})
    clean = {**res, "receipt": {**res["receipt"], "drafts": 1}, "trace": res["trace"][:1]}
    monkeypatch.setattr(ev, "pipeline_run", lambda *a, **k: clean)
    assert ev._one_run("robert:tariffs", {}, "q")["types"] == []


def test_the_blind_advice_sets_json_keys_are_the_numbers_their_sections_print():
    """docs/eval_results.json advice_redteam.blind_v1 / blind_v2 (the pitch Q&A and technical.md cite them) are counted
    from each set's rows by its own script's rules and equal the headline its subsection of section 6a prints; both
    are blind measurements, never the in-sample pins (advice_redteam.advice_check_in_sample)."""
    from scripts import advice_blind_eval as v1
    from scripts import advice_blind_v2_eval as v2
    written = json.loads((pathlib.Path(ev.ROOT) / "docs" / "eval_results.json").read_text(encoding="utf-8"))["advice_redteam"]
    for key, mod in (("blind_v1", v1), ("blind_v2", v2)):
        s, text = mod.summary(), mod.render()
        assert f"- **Must-block stopped by either check:** {s['must_block_stopped_k']} / {s['must_block_n']} (" in text
        assert f"- **Benign passed both checks:** {s['benign_passed_k']} / {s['benign_n']} (" in text
        assert s["in_sample"] is False and written[key] == s, key


def test_several_earlier_measurements_are_kept_newest_first_each_with_its_own_base():
    """A list in receipt_earlier keeps every earlier run of section 5 (newest first, each with its date, commit and an
    optional note); section 10's earlier block is judged against the receipt rows of its own commit."""
    def sec(first, day, commit, **extra):
        rows = [{"first_try": f, "final": True, "drafts": 1 if f else 2, "types": [], "steps": {}, "ms": 1.0, "usd": 0.0}
                for f in first]
        return {"rows": rows, "model": "m", "date": day, "commit": commit, **extra}
    results = {"meta": {}, "receipt": sec([True] * 3, "2026-11-15", "c46d72b"),
               "memory": {**sec([True] * 3, "2026-11-15", "c46d72b"), "memory": ["too_long"]},
               "receipt_earlier": [sec([True, False, False], "2026-11-15", "f865bc5",
                                       note="the eval did not yet record what the re-ask was told"),
                                   sec([False] * 3, "2026-11-14", "b4a21e2")],
               "memory_earlier": {**sec([True, True, False], "2026-11-14", "b4a21e2"), "memory": ["wrong_entity"]}}
    text = ev.render(results)
    s5, s10 = text.split("\n## 5. ")[1].split("\n## 6")[0], text.split("\n## 10. ")[1].split("\n## 11")[0]
    heads = [ln for ln in s5.splitlines() if ln.startswith("Earlier measurement")]
    assert heads == ["Earlier measurement (2026-11-15, code at commit f865bc5; the eval did not yet record what the re-ask "
                     "was told), superseded by the lines above:",
                     "Earlier measurement (2026-11-14, code at commit b4a21e2), superseded by the lines above:"]
    assert s5.split(heads[0])[1].split(heads[1])[0].count("first draft shown as written (no check named a defect, so no re-ask): 1 / 3")
    then10 = s10.split("Earlier measurement")[1]
    assert "First-try receipt pass without memory: 0 / 3" in then10 and "First-try receipt pass with memory: 2 / 3" in then10
    assert "First draft shown as written (no re-ask) without memory: 0 / 3" in then10
    assert "First draft shown as written (no re-ask) with memory: 2 / 3" in then10
    assert "First draft shown as written (no re-ask) with memory: 3 / 3" in s10.split("Earlier measurement")[0]
    assert "(sections measured at b4a21e2, c46d72b, f865bc5)" in text.splitlines()[2]           # list entries count too
