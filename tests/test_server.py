"""Tests for server.py (plan D Task 4): the API, the NDJSON stream, plain-English errors.

Two layers. (1) Contract tests: `pipeline` functions are recording fakes, so the server is tested alone
(framing, validation, error envelope, LRU, headers, password hook). (2) The plan's integration tests run
the real pipeline on tests/fake_engine.py; they skip until pipeline.py and tests/fake_engine.py are on main.
While pipeline.py is missing, a stand-in module with the ledger names is put in sys.modules for this file only.
"""
import asyncio
import base64
import json
import sys
import threading
import types

import numpy as np
import pytest
from fastapi.testclient import TestClient

try:
    import pipeline
    STUBBED = False
except ModuleNotFoundError:        # D Task 2 is not on main yet: a stand-in with the ledger names
    pipeline = types.ModuleType("pipeline")
    pipeline.DATASET_END = "2026-11-12"
    pipeline.STEPS = ("OBSERVE", "UNDERSTAND", "COMPARE", "EXPLAIN", "VERIFY")
    sys.modules["pipeline"] = pipeline
    STUBBED = True
import server


def teardown_module(module):
    if STUBBED:                     # leave no stand-in behind for other test files
        sys.modules.pop("pipeline", None)
        sys.modules.pop("server", None)


def _jsonable_double(obj, _top=True):
    """Same contract as pipeline.jsonable (Task 3): numpy to Python, NaN/inf to None, tuples to lists,
    top-level keys starting with '_' dropped."""
    if isinstance(obj, dict):
        return {k: _jsonable_double(v, False) for k, v in obj.items() if not (_top and str(k).startswith("_"))}
    if isinstance(obj, (list, tuple)):
        return [_jsonable_double(v, False) for v in obj]
    if isinstance(obj, np.generic):
        obj = obj.item()
    if isinstance(obj, float) and not np.isfinite(obj):
        return None
    return obj


STEPS = tuple(pipeline.STEPS)
ROBERT = {"XIU.TO": 0.45, "XBB.TO": 0.35, "GLD": 0.10, "ZST.TO": 0.10}
PROFILE = {"goal": "preservation", "horizon_years": 4, "risk": "moderate", "esg": False, "crypto": False,
           "capacity": 90000, "reaction_2022": "held"}
BODY = {"portfolio": ROBERT, "amount": 600000, "profile": PROFILE, "question": "What if I put 40 % in NVIDIA?",
        "pilot": "robert"}
EXPIRED = "This check has expired. Run it again."
GENERIC_500 = "Something went wrong on the server. Try again in a moment; if it repeats, restart the server."


@pytest.fixture(autouse=True)
def _jsonable_available(monkeypatch):
    if not hasattr(pipeline, "jsonable"):          # Task 3 is not on main yet: the double has the same contract
        monkeypatch.setattr(pipeline, "jsonable", _jsonable_double, raising=False)


@pytest.fixture(autouse=True)
def _a_commit_without_git(monkeypatch):
    """A saved run names the commit of its code. In a copy with no .git (a ZIP download, the Docker image) that comes
    from EPICENTRE_COMMIT, so the static-build tests pass with or without .git; in a checkout git HEAD still wins."""
    monkeypatch.setenv(pipeline.COMMIT_ENV, "0123456789abcdef0123456789abcdef01234567")


@pytest.fixture()
def api(monkeypatch):
    """TestClient with recording fakes for every pipeline function the server calls."""
    calls = types.SimpleNamespace(run=[], recheck=[], recompute=[])

    def fake_run(flight_plan, question, as_of=pipeline.DATASET_END, *, progress=None, use_bedrock=True,
                 redteam=False, engine=None):
        calls.run.append(dict(flight_plan=flight_plan, question=question, as_of=as_of, use_bedrock=use_bedrock,
                              redteam=redteam, progress=progress))
        for step in STEPS:
            progress({"type": "progress", "step": step, "label": step.title(), "status": "done", "ms": 1,
                      "service": "Python", "detail": None})
        return {"run_id": "r1", "status": "ok", "verdict": "Tension", "as_of": as_of, "ratio": np.float64(0.5),
                "bad": float("nan"), "_analysis": {"private": True}}

    def fake(name, answer):
        def call(*args, **kwargs):
            getattr(calls, name).append((args, kwargs))
            return answer
        return call

    monkeypatch.setattr(pipeline, "run", fake_run, raising=False)
    monkeypatch.setattr(pipeline, "recheck", fake("recheck", {"checks": [], "verdict": "Tension", "kpis": {},
                                                                "sensitivity": None}), raising=False)
    monkeypatch.setattr(pipeline, "recompute", fake("recompute", {"id": "T1", "value": 1.0, "same": True}),
                        raising=False)
    monkeypatch.setattr(pipeline, "default_demo_run", lambda: None, raising=False)
    monkeypatch.delenv("EPICENTRE_NO_BEDROCK", raising=False)
    monkeypatch.delenv(server.PASSWORD_ENV, raising=False)
    monkeypatch.delenv(server.ORIGIN_SECRET_ENV, raising=False)         # a developer's shell must not leak in
    monkeypatch.delenv(server.REQUIRE_PASSWORD_ENV, raising=False)
    server.RUNS.clear()
    server.clear_health_cache()
    client = TestClient(server.app)
    client.calls = calls
    return client


def ndjson(client, body):
    with client.stream("POST", "/api/run", json=body) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/x-ndjson")
        return [json.loads(line) for line in r.iter_lines() if line]


def error_of(r, status):
    assert r.status_code == status, r.text
    body = r.json()
    assert set(body) == {"status", "message"} and body["status"] == "error"
    assert "Traceback" not in r.text and "secret internals" not in r.text
    return body["message"]


# ---- POST /api/run: the stream ----

def test_run_streams_progress_then_the_result_and_keeps_it(api):
    lines = ndjson(api, BODY)
    assert [l["type"] for l in lines] == ["progress"] * len(STEPS) + ["result"]
    assert [l["step"] for l in lines[:-1]] == list(STEPS)
    result = lines[-1]["result"]
    assert result["run_id"] == "r1" and result["ratio"] == 0.5 and result["bad"] is None
    assert "_analysis" not in result                                  # server-side only keys never reach the browser
    assert server.RUNS.get("r1")["_analysis"] == {"private": True}    # but the server keeps them for recheck


def test_run_response_headers(api):
    with api.stream("POST", "/api/run", json=BODY) as r:
        r.read()
        assert r.headers["cache-control"] == "no-store" and r.headers["x-accel-buffering"] == "no"
        assert r.headers["content-type"].startswith("application/x-ndjson")


def test_run_hands_the_normalized_flight_plan_to_the_pipeline(api):
    sloppy = {**ROBERT, "XIU.TO": 0.448}                   # sums to 0.998: inside the 0.5 pp tolerance
    ndjson(api, {**BODY, "portfolio": sloppy, "limits": {"floor": -0.2}, "redteam": True})
    call = api.calls.run[0]
    plan = call["flight_plan"]
    assert set(plan) == {"portfolio", "amount", "profile", "limits", "pilot"}
    assert sum(plan["portfolio"].values()) == pytest.approx(1.0, abs=1e-12)
    assert plan["portfolio"]["XIU.TO"] == pytest.approx(0.448 / 0.998)
    assert plan["amount"] == 600000 and plan["pilot"] == "robert" and plan["limits"] == {"floor": -0.2}
    assert plan["profile"] == PROFILE
    assert call["question"] == BODY["question"] and call["as_of"] == pipeline.DATASET_END
    assert call["use_bedrock"] is True and call["redteam"] is True and callable(call["progress"])


def test_run_uses_the_given_as_of_and_the_no_bedrock_switch(api, monkeypatch):
    monkeypatch.setenv("EPICENTRE_NO_BEDROCK", "1")
    ndjson(api, {**BODY, "as_of": "2025-01-31"})
    assert api.calls.run[0]["as_of"] == "2025-01-31" and api.calls.run[0]["use_bedrock"] is False


def test_run_without_a_profile_or_question_is_allowed(api):
    ndjson(api, {"portfolio": ROBERT, "amount": 1000})
    call = api.calls.run[0]
    assert call["flight_plan"]["profile"] is None and call["flight_plan"]["limits"] is None
    assert call["question"] == "" and call["flight_plan"]["pilot"] is None


def test_lines_arrive_while_the_run_is_still_working():
    release = threading.Event()

    def work(progress):
        progress({"type": "progress", "step": "OBSERVE"})
        assert release.wait(5), "the reader never got the first line"
        return {"run_id": "x", "status": "ok"}

    stream = server.ndjson_lines(work)
    raw = next(stream)                                           # delivered before the run finished
    assert raw.endswith("\n") and "\n" not in raw[:-1]           # one JSON document per line
    assert json.loads(raw) == {"type": "progress", "step": "OBSERVE"}
    release.set()
    rest = list(stream)
    assert all(l.endswith("\n") for l in rest)
    assert [json.loads(l)["type"] for l in rest] == ["result"] and json.loads(rest[0])["result"]["run_id"] == "x"


def test_a_crashing_run_ends_the_stream_with_a_plain_error_result(api, monkeypatch):
    def boom(*a, **k):
        raise ValueError("secret internals")
    monkeypatch.setattr(pipeline, "run", boom)
    lines = ndjson(api, BODY)
    assert lines[-1] == {"type": "result", "result": {"status": "error", "message": GENERIC_500}}
    assert "secret" not in json.dumps(lines)


def test_a_progress_event_that_cannot_be_serialized_is_dropped_not_fatal():
    def work(progress):
        progress({"type": "progress", "bad": object()})
        progress({"type": "progress", "step": "OBSERVE"})
        return {"run_id": "y", "status": "ok"}
    lines = [json.loads(l) for l in server.ndjson_lines(work)]
    assert [l["type"] for l in lines] == ["progress", "result"] and lines[0]["step"] == "OBSERVE"


# ---- POST /api/run: input checks, before any work ----

@pytest.mark.parametrize("patch, words", [
    ({"portfolio": {"XIU.TO": 0.5, "XBB.TO": 0.4}}, "Your weights add up to 90 %; they must add up to 100 %."),
    ({"portfolio": {"ZAG.TO": 1.0}}, "ZAG.TO is not in the dataset. Pick one of the 31 tickers."),
    ({"portfolio": {"xiu.to": 1.0}}, "xiu.to is not in the dataset. Pick one of the 31 tickers."),
    ({"portfolio": {"XIU.TO": 0.6, "XBB.TO": 0.6}}, "add up to 120 %"),
    ({"portfolio": {}}, "add up to 0 %"),
    ({"amount": 0}, "Enter a fictional amount above $0."),
    ({"amount": -5}, "Enter a fictional amount above $0."),
    ({"question": "x" * 2001}, "Keep the question under 2,000 characters."),
    ({"as_of": "2030-01-01"}, "Pick a date between 12 Nov 2021 and 12 Nov 2026."),
    ({"as_of": "2021-11-11"}, "Pick a date between 12 Nov 2021 and 12 Nov 2026."),
    ({"as_of": "yesterday"}, "Pick a date between 12 Nov 2021 and 12 Nov 2026."),
    ({"as_of": "20250131"}, "Pick a date between 12 Nov 2021 and 12 Nov 2026."),
])
def test_bad_flight_plans_are_refused_in_plain_english_before_any_work(api, patch, words):
    msg = error_of(api.post("/api/run", json={**BODY, **patch}), 422)
    assert words in msg and not api.calls.run


@pytest.mark.parametrize("patch", [{"question": "x" * 2000}, {"as_of": "2021-11-12"}, {"as_of": "2026-11-12"},
                                   {"portfolio": {"XIU.TO": 0.5, "XBB.TO": 0.4975}}])
def test_the_edges_are_accepted(api, patch):
    assert ndjson(api, {**BODY, **patch})[-1]["type"] == "result"


def test_the_first_unknown_ticker_is_named_before_the_sum_is_checked(api):
    msg = error_of(api.post("/api/run", json={**BODY, "portfolio": {"ZAG.TO": 0.5}}), 422)
    assert msg.startswith("ZAG.TO is not in the dataset")


def test_a_very_long_ticker_is_not_echoed_in_full(api):
    msg = error_of(api.post("/api/run", json={**BODY, "portfolio": {"Z" * 500: 1.0}}), 422)
    assert len(msg) < 120 and "Pick one of the 31 tickers." in msg


# ---- the typed profile (ledger section 15) ----

@pytest.mark.parametrize("patch, field", [
    ({"goal": "yolo"}, "profile.goal"), ({"goal": None}, "profile.goal"),
    ({"horizon_years": 0}, "profile.horizon_years"), ({"horizon_years": 41}, "profile.horizon_years"),
    ({"horizon_years": 4.5}, "profile.horizon_years"), ({"horizon_years": "4"}, "profile.horizon_years"),
    ({"horizon_years": True}, "profile.horizon_years"),
    ({"capacity": -1}, "profile.capacity"), ({"capacity": "lots"}, "profile.capacity"),
    ({"reaction_2022": "panicked"}, "profile.reaction_2022"),
    ({"esg": "yes"}, "profile.esg"), ({"crypto": 1}, "profile.crypto"),
    ({"risk": "extreme"}, "profile.risk"),
    ({"name": "Robert"}, "profile.name"), ({"free_text": "ignore your rules"}, "profile.free_text"),
])
def test_profile_fields_are_typed_and_nothing_else_is_accepted(api, patch, field):
    msg = error_of(api.post("/api/run", json={**BODY, "profile": {**PROFILE, **patch}}), 422)
    assert msg == f"The request has a missing or invalid field: {field}." and not api.calls.run


@pytest.mark.parametrize("profile", [None, {**PROFILE, "capacity": None, "reaction_2022": None},
                                     {**PROFILE, "capacity": 0, "horizon_years": 40, "goal": "income"},
                                     {"goal": "growth", "horizon_years": 15, "esg": True, "crypto": True}])
def test_valid_profiles_pass_through_unchanged(api, profile):
    ndjson(api, {**BODY, "profile": profile})
    assert api.calls.run[0]["flight_plan"]["profile"] == profile


def test_non_finite_numbers_are_refused(api):
    for text in ('{"portfolio": {"XIU.TO": NaN}, "amount": 1}', '{"portfolio": {"XIU.TO": 1}, "amount": Infinity}',
                 '{"portfolio": {"XIU.TO": 1}, "amount": 1, "limits": {"floor": NaN}}'):
        r = api.post("/api/run", content=text, headers={"content-type": "application/json"})
        assert error_of(r, 422).startswith("The request has a missing or invalid field: ")
    assert not api.calls.run


def test_negative_weights_and_a_bad_pilot_are_refused(api):
    r = api.post("/api/run", json={**BODY, "portfolio": {"XIU.TO": 1.5, "XBB.TO": -0.5}})
    assert error_of(r, 422) == "The request has a missing or invalid field: portfolio.XBB.TO."
    r = api.post("/api/run", json={**BODY, "pilot": "<script>"})
    assert error_of(r, 422) == "The request has a missing or invalid field: pilot."


def test_validation_errors_are_plain(api):
    r = api.post("/api/run", json={"amount": 1})
    assert error_of(r, 422) == "The request has a missing or invalid field: portfolio."
    r = api.post("/api/run", content="{not json", headers={"content-type": "application/json"})
    assert error_of(r, 422) == "The request has a missing or invalid field: request body."
    r = api.post("/api/recheck", json={"limits": {}})
    assert error_of(r, 422) == "The request has a missing or invalid field: run_id."


# ---- the other POST routes ----

def stored(api):
    return ndjson(api, BODY)[-1]["result"]["run_id"]


def test_recheck_answers_from_the_stored_run(api):
    run_id = stored(api)
    r = api.post("/api/recheck", json={"run_id": run_id, "limits": {"floor": -0.4}})
    assert r.status_code == 200 and r.json()["verdict"] == "Tension"
    (result, limits), _ = api.calls.recheck[0]
    assert result is server.RUNS.get(run_id) and limits == {"floor": -0.4}


def test_recompute_returns_the_value_or_the_pipelines_sentence(api, monkeypatch):
    run_id = stored(api)
    assert api.post("/api/recompute", json={"run_id": run_id, "id": "T1"}).json()["same"] is True
    monkeypatch.setattr(pipeline, "recompute", lambda result, tid: {"error": "This number has no recorded tool step."})
    r = api.post("/api/recompute", json={"run_id": run_id, "id": "T999"})
    assert error_of(r, 404) == "This number has no recorded tool step."
    monkeypatch.setattr(pipeline, "recompute", lambda result, tid: {"error": "The tools could not run.", "reason": "unavailable"})
    assert error_of(api.post("/api/recompute", json={"run_id": run_id, "id": "T1"}), 503) == "The tools could not run."


@pytest.mark.parametrize("path, body", [("/api/recheck", {"limits": {}}), ("/api/recompute", {"id": "T1"})])
def test_an_unknown_or_evicted_run_id_is_a_plain_404(api, path, body):
    assert error_of(api.post(path, json={"run_id": "nope", **body}), 404) == EXPIRED


@pytest.mark.parametrize("path, body, name", [("/api/recheck", {"limits": {}}, "recheck"),
                                              ("/api/recompute", {"id": "T1"}, "recompute")])
def test_unexpected_errors_never_leak(api, monkeypatch, path, body, name):
    def boom(*a, **k):
        raise ValueError("secret internals")
    monkeypatch.setattr(pipeline, name, boom)
    r = api.post(path, json={"run_id": stored(api), **body})
    assert error_of(r, 500) == GENERIC_500


# ---- the real pipeline behind the API (the fake engine): recompute answers, and no route ends in a 500 ----
@pytest.fixture()
def live(monkeypatch):
    """TestClient over the real pipeline functions; only the engine is the offline fake (tests/fake_engine.py)."""
    if STUBBED:
        pytest.skip("pipeline.py is not on this checkout")
    from fake_engine import fake_engine
    engine = fake_engine()
    monkeypatch.setattr(pipeline, "real_engine", lambda: engine)
    monkeypatch.setenv("EPICENTRE_NO_BEDROCK", "1")
    for name in (server.PASSWORD_ENV, server.ORIGIN_SECRET_ENV, server.REQUIRE_PASSWORD_ENV):
        monkeypatch.delenv(name, raising=False)
    server.RUNS.clear()
    server.clear_health_cache()
    return TestClient(server.app)


def test_recompute_reruns_every_number_of_a_real_run_and_finds_the_stored_value(live):
    result = ndjson(live, BODY)[-1]["result"]
    assert result["status"] == "ok" and result["facts"]
    for tid, fact in result["facts"].items():
        r = live.post("/api/recompute", json={"run_id": result["run_id"], "id": tid})
        assert r.status_code == 200, (tid, r.text)
        out = r.json()
        assert (out["id"], out["same"], out["value"], out["stored"]) == (tid, True, fact["value"], fact["value"]), out
        assert out["label"] == fact["label"] and out["how"] and out["tool"] and out["recipe"]
    assert error_of(live.post("/api/recompute", json={"run_id": result["run_id"], "id": "T999"}), 404) == \
        "This run has no number T999."


API_ROUTES = {("GET", "/api/pilots"), ("GET", "/api/wire"), ("GET", "/api/health"), ("GET", "/api/demo-run"),
              ("POST", "/api/run"), ("POST", "/api/recheck"), ("POST", "/api/recompute"), ("POST", "/api/record"),
              ("POST", "/api/scenario/read"), ("POST", "/api/scenario"), ("POST", "/api/profile/read")}
SCENARIO_BODY = {"portfolio": {"XIU.TO": 0.6, "XBB.TO": 0.4}, "limits": {"floor": -0.15}, "amount": 600000,
                 "shocks": {"tech": -0.3}}           # lane sc-b; without the starter data the engine answers 503, never 500


def test_every_route_answers_valid_input_without_a_500(live, monkeypatch):
    """Every route server.py exposes, called once with valid input through the real pipeline: none is a 500. The
    time machine and the challenge had routes but no pipeline function behind them; they are gone (not in this build)."""
    routes = {(m, route.path) for route in server.router.routes for m in getattr(route, "methods", None) or ()}
    assert routes == API_ROUTES
    lines = ndjson(live, BODY)
    result = lines[-1]["result"]
    assert result["status"] == "ok" and all(line["type"] in ("progress", "result") for line in lines)
    run_id, first = result["run_id"], next(iter(result["facts"]))
    monkeypatch.delenv("EPICENTRE_RECORD_BUCKET", raising=False)       # the vault is off here: /api/record answers "off"
    from agents import scenario_builder                                 # lane sc-a: a tiny book, no starter data needed
    monkeypatch.setattr(scenario_builder, "book_for", lambda as_of=None: scenario_builder.make_book(
        scenario_builder.FACTORS, [{"id": "tech_2022", "label": "Tech stocks' largest fall in 2022", "shocks": {"tech": -0.25}}]))
    answers = {
        "/api/pilots": live.get("/api/pilots"), "/api/wire": live.get("/api/wire"), "/api/health": live.get("/api/health"),
        "/api/demo-run": live.get("/api/demo-run"), "/api/demo-run?pilot": live.get("/api/demo-run?pilot=mateo"),
        "/api/recheck": live.post("/api/recheck", json={"run_id": run_id, "limits": {"floor": -0.4}}),
        "/api/recompute": live.post("/api/recompute", json={"run_id": run_id, "id": first}), "/": live.get("/"),
        "/api/record": live.post("/api/record", json={"record": {"run": {"run_id": run_id}, "verdict": result["verdict"]}}),
        "/api/scenario/read": live.post("/api/scenario/read", json={"text": "What if AI stocks sell off?"}),
        "/api/scenario": live.post("/api/scenario", json=SCENARIO_BODY),
        "/api/profile/read": live.post("/api/profile/read", json={"text": "I'm 45 with $200,000; I could lose $40,000."}),
    }
    no_data = set() if (server.WEB_DIR.parent / "data" / "starter" / "prices_daily.csv").is_file() else {"/api/scenario"}
    no_bedrock = {"/api/profile/read"}                   # lane profile-ai: Bedrock off is a 503 whose body is the whole
    for path, r in answers.items():                      # keyword reading; no starter data: the scenario engine is a 503
        assert r.status_code < 500 or (path in no_data | no_bedrock and r.status_code == 503), (path, r.status_code,
                                                                                               r.text[:200])
    assert {p for p, r in answers.items() if r.status_code != 200} <= \
        {"/api/demo-run", "/api/demo-run?pilot"} | no_data | no_bedrock                  # no saved run yet
    profile = answers["/api/profile/read"].json()
    assert (profile["method"], profile["ai"], profile["status"], profile["amount"]) == ("keyword", "off", "ok", 200000.0)
    assert answers["/api/recheck"].json()["verdict"] and answers["/api/recompute"].json()["same"] is True
    for gone in ("/api/time-machine", "/api/challenge"):
        assert live.post(gone, json={"run_id": run_id, "as_of": None, "argument": "x"}).status_code in (404, 405)


# ---- headers, the error envelope everywhere, the LRU, to_json ----

def test_every_response_carries_the_two_security_headers(api, monkeypatch):
    run_id = stored(api)
    monkeypatch.setattr(pipeline, "recheck", lambda *a: (_ for _ in ()).throw(ValueError("secret internals")))
    responses = [api.get("/api/health"), api.get("/"), api.get("/nope.txt"), api.post("/api/run", json={}),
                 api.post("/api/recheck", json={"run_id": "nope", "limits": {}}),
                 api.post("/api/recheck", json={"run_id": run_id, "limits": {}}), api.put("/api/health")]
    with api.stream("POST", "/api/run", json=BODY) as r:
        r.read()
        responses.append(r)
    assert [x.status_code for x in responses][2:7] == [404, 422, 404, 500, 405]
    for x in responses:
        assert x.headers["x-content-type-options"] == "nosniff" and x.headers["referrer-policy"] == "no-referrer"


def test_unknown_paths_and_methods_use_the_plain_envelope_and_never_the_framework_text(api):
    msg = error_of(api.get("/api/nope"), 404)
    assert "detail" not in msg and msg.endswith(".")
    assert api.get("/api/run").status_code in (404, 405) and api.get("/api/run").json()["status"] == "error"
    assert api.get("/docs").status_code == 404 and api.get("/openapi.json").status_code == 404


def test_lru_keeps_the_last_50():
    server.RUNS.clear()
    assert server.RUNS.maxlen == 50
    for i in range(51):
        server.RUNS.put({"run_id": str(i)})
    assert server.RUNS.get("0") is None and server.RUNS.get("50") is not None


def test_lru_get_refreshes_recency_and_clear_empties():
    server.RUNS.clear()
    for i in range(50):
        server.RUNS.put({"run_id": str(i)})
    assert server.RUNS.get("0") is not None            # "0" is now the freshest
    server.RUNS.put({"run_id": "50"})
    assert server.RUNS.get("1") is None and server.RUNS.get("0") is not None
    server.RUNS.clear()
    assert server.RUNS.get("0") is None


def test_lru_is_thread_safe_and_ignores_results_without_an_id():
    server.RUNS.clear()
    server.RUNS.put({"status": "error"})
    errors = []

    def writer(base):
        try:
            for i in range(200):
                server.RUNS.put({"run_id": f"{base}-{i}"})
                server.RUNS.get(f"{base}-{i // 2}")
        except Exception as exc:       # pragma: no cover
            errors.append(exc)
    threads = [threading.Thread(target=writer, args=(n,)) for n in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors and len(server.RUNS) == 50


def test_to_json_is_compact_strict_and_delegates_to_jsonable(monkeypatch):
    monkeypatch.setattr(pipeline, "jsonable", lambda obj: obj, raising=False)
    assert server.to_json({"a": 1, "b": [1, 2], "c": "é"}) == '{"a":1,"b":[1,2],"c":"\\u00e9"}'
    with pytest.raises(ValueError):
        server.to_json({"a": float("nan")})            # never a bare NaN: the browser's JSON.parse rejects it


@pytest.mark.skipif(STUBBED or not hasattr(pipeline, "jsonable"), reason="pipeline.jsonable (Task 3) is not on main yet")
def test_to_json_cleans_numpy_and_nan():
    assert json.loads(server.to_json({"a": np.float64(0.5), "b": float("nan"), "c": (1, 2)})) == \
        {"a": 0.5, "b": None, "c": [1, 2]}


# ---- GET routes ----

def test_health_never_needs_aws_and_reports_five_booleans(api, monkeypatch, tmp_path):
    starter = tmp_path / "prices_daily.csv"
    monkeypatch.setattr(server, "STARTER_PRICES", starter)
    monkeypatch.delenv("EPICENTRE_GUARDRAIL_ID", raising=False)
    creds, files = {"value": None}, {"value": False}
    monkeypatch.setattr(server.boto3, "Session", lambda: types.SimpleNamespace(get_credentials=lambda: creds["value"]))
    monkeypatch.setattr(server, "_holdings_usable", lambda: files["value"])
    monkeypatch.setattr(server, "_deep_panel", lambda: files["value"])
    assert api.get("/api/health").json() == {"data": False, "bedrock": False, "guardrail": False, "holdings": False,
                                             "deep": False}
    starter.write_text("date,ticker\n")
    server.clear_health_cache()
    creds["value"], files["value"] = object(), True
    monkeypatch.setenv("EPICENTRE_GUARDRAIL_ID", "abc123")
    assert api.get("/api/health").json() == {"data": True, "bedrock": True, "guardrail": True, "holdings": True,
                                             "deep": True}


def test_health_says_whether_this_replay_can_look_through_the_fund_holdings_and_has_the_deep_panel(monkeypatch,
                                                                                                    tmp_path):
    """Lane B6 (controller ruling, Sun 15 Nov): `holdings` is tools.lookthrough's own rule (a holdings snapshot dated
    after the replay's last day is direct mode, red gate 3), so the live page can say so in one line; `deep` is the
    deep-history panel where result_extras looks for it."""
    from datetime import date, timedelta
    import result_extras
    from tools import data as market_data, lookthrough
    fake = server.WEB_DIR.parent / "data" / "fake" / "starter"            # synthetic universe: no licensed data needed
    monkeypatch.setattr(lookthrough, "load_universe", lambda: market_data.load_universe(data_dir=fake))
    holdings = tmp_path / "etf_holdings.csv"
    monkeypatch.setattr(lookthrough, "HOLDINGS_CSV", holdings)

    def snapshot(day):
        holdings.write_text("etf,kind,name,ticker,weight,as_of,source_url\n"
                            f"XIU.TO,holding,A bank,RY.TO,0.07,{day},https://example.org/x\n")

    assert server._holdings_usable() is False                                # no file: direct mode
    snapshot(market_data.DATASET_END)
    assert server._holdings_usable() is True                                 # dated on the replay's last day
    snapshot((date.fromisoformat(market_data.DATASET_END) + timedelta(days=1)).isoformat())
    assert server._holdings_usable() is False                                # dated after it: direct mode
    monkeypatch.setattr(result_extras, "REPO_ROOT", tmp_path)
    monkeypatch.delenv(result_extras.PANEL_ENV, raising=False)
    assert server._deep_panel() is False
    (tmp_path / "data" / "cache" / "deep").mkdir(parents=True)
    (tmp_path / "data" / "cache" / "deep" / "panel.csv").write_text("month\n")
    assert server._deep_panel() is True


def test_wire_returns_the_first_eight_items_or_an_empty_list(api, monkeypatch, tmp_path):
    path = tmp_path / "wire.json"
    monkeypatch.setattr(server, "WIRE_PATH", path)
    assert api.get("/api/wire").json() == {"items": []}                   # no file
    path.write_text("{broken")
    assert api.get("/api/wire").json() == {"items": []}                   # unreadable file
    path.write_text(json.dumps({"not": "a list"}))
    assert api.get("/api/wire").json() == {"items": []}
    items = [{"title": f"t{i}", "date": "2026-11-01", "url": "https://example.org", "source": "s",
              "retrieved_at": "2026-11-14T10:00:00Z"} for i in range(12)]
    path.write_text(json.dumps(items))
    assert api.get("/api/wire").json() == {"items": items[:8]}


def test_pilots_serves_only_the_two_keys_and_503s_when_not_ready(api, monkeypatch, tmp_path):
    path = tmp_path / "personas.json"
    monkeypatch.setattr(server, "PERSONAS_PATH", path)
    assert error_of(api.get("/api/pilots"), 503) == "The pilots file is not ready yet."          # no file
    path.write_text(json.dumps({"pilots": {"robert": {}}}))                                      # keys absent
    assert error_of(api.get("/api/pilots"), 503) == "The pilots file is not ready yet."
    path.write_text(json.dumps({"pilots": {"robert": {"name": "Robert"}}, "storm_cards": {"tariffs": {}},
                                "risk_levels": {"low": {}}, "illustration_mixes": {}}))
    assert api.get("/api/pilots").json() == {"pilots": {"robert": {"name": "Robert"}}, "storm_cards": {"tariffs": {}}}


def test_the_real_personas_file_is_served_or_refused_plainly(api):
    r = api.get("/api/pilots")
    assert r.status_code in (200, 503)
    if r.status_code == 200:
        assert set(r.json()) == {"pilots", "storm_cards"}


def test_demo_run_is_a_plain_404_until_a_run_is_saved(api, monkeypatch):
    assert error_of(api.get("/api/demo-run"), 404) == "There are no saved runs yet."
    monkeypatch.delattr(pipeline, "default_demo_run")              # Task 3 not on main at all
    assert error_of(api.get("/api/demo-run"), 404) == "There are no saved runs yet."


def test_demo_run_serves_the_saved_run_and_keeps_it_for_later_calls(api, monkeypatch):
    saved = {"run_id": "demo1", "mode": "demo_replay", "status": "ok", "_analysis": {"x": 1}}
    monkeypatch.setattr(pipeline, "default_demo_run", lambda: saved)
    r = api.get("/api/demo-run")
    assert r.status_code == 200 and r.json() == {"run_id": "demo1", "mode": "demo_replay", "status": "ok"}
    assert api.post("/api/recheck", json={"run_id": "demo1", "limits": {}}).status_code == 200


def test_universe_has_the_31_tickers_of_spec_section_9():
    assert len(server.UNIVERSE_TICKERS) == 31 and len(set(server.UNIVERSE_TICKERS)) == 31
    assert {"RY.TO", "NVDA", "XIU.TO", "XBB.TO", "ZST.TO", "GLD", "BTC-USD", "ETH-USD"} <= set(server.UNIVERSE_TICKERS)
    assert "ZAG.TO" not in server.UNIVERSE_TICKERS


@pytest.mark.skipif(not __import__("pathlib").Path("data/starter/assets_universe.csv").exists(),
                    reason="starter data not present")
def test_universe_constant_matches_the_dataset():
    import pandas as pd
    assert set(server.UNIVERSE_TICKERS) == set(pd.read_csv("data/starter/assets_universe.csv").ticker)


# ---- the optional password (live deployment, Task 14): off unless the environment variable is set ----

def basic(user, password):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()}


def test_there_is_no_default_password(api, monkeypatch):
    assert server.PASSWORD_ENV == "EPICENTRE_PASSWORD"
    assert api.get("/api/pilots").status_code != 401            # unset: open
    monkeypatch.setenv(server.PASSWORD_ENV, "")
    assert api.get("/api/pilots").status_code != 401            # empty means unset, never a blank password
    assert api.get("/", headers=basic("a", "")).status_code != 401


def test_with_a_password_every_route_asks_for_it(api, monkeypatch):
    monkeypatch.setenv(server.PASSWORD_ENV, "correct horse")
    for r in (api.get("/"), api.get("/api/pilots"), api.get("/api/demo-run"), api.post("/api/run", json=BODY),
              api.post("/api/recheck", json={"run_id": "x", "limits": {}})):
        assert error_of(r, 401) == "Enter the password to open EPICENTRE."
        assert r.headers["www-authenticate"].startswith("Basic realm=") and r.headers["x-content-type-options"] == "nosniff"
    assert not api.calls.run                                      # nothing ran without the password
    for header in (basic("any", "wrong"), basic("any", "correct horse "), {"Authorization": "Basic %%%"},
                   {"Authorization": "Bearer correct horse"}, {"Authorization": "Basic"}):
        assert api.get("/api/pilots", headers=header).status_code == 401


def test_the_right_password_opens_everything_whatever_the_user_name(api, monkeypatch):
    monkeypatch.setenv(server.PASSWORD_ENV, "pässword: with colon")
    for user in ("", "judge", "x"):
        assert api.get("/", headers=basic(user, "pässword: with colon")).status_code == 200
    assert api.get("/api/pilots", headers=basic("j", "pässword: with colon")).status_code in (200, 503)
    assert ndjson_with(api, basic("j", "pässword: with colon"))[-1]["type"] == "result"


def ndjson_with(client, headers):
    with client.stream("POST", "/api/run", json=BODY, headers=headers) as r:
        assert r.status_code == 200
        return [json.loads(line) for line in r.iter_lines() if line]


def test_the_container_health_check_stays_open(api, monkeypatch):
    monkeypatch.setenv(server.PASSWORD_ENV, "pw")                 # the Dockerfile HEALTHCHECK sends no credentials
    r = api.get("/api/health")
    assert r.status_code == 200 and set(r.json()) == {"data", "bedrock", "guardrail", "holdings", "deep"}


# ---- the page ----

def test_the_page_is_served_and_the_api_wins_over_the_static_mount(api):
    page = api.get("/")
    assert page.status_code == 200 and "<html" in page.text.lower()
    assert api.get("/api/health").json().keys() == {"data", "bedrock", "guardrail", "holdings", "deep"}


def test_the_static_mount_exists_only_when_the_web_folder_does(tmp_path):
    (tmp_path / "index.html").write_text("<html>hi</html>")
    with_web = TestClient(server.create_app(web_dir=tmp_path))
    assert with_web.get("/").text == "<html>hi</html>" and with_web.get("/api/health").status_code == 200
    without = TestClient(server.create_app(web_dir=tmp_path / "missing"))
    assert error_of(without.get("/"), 404).endswith(".") and without.get("/api/health").status_code == 200


def test_no_credentials_or_default_password_in_the_source():
    import pathlib, re
    src = pathlib.Path(server.__file__).read_text()
    assert not re.search(r"AKIA[0-9A-Z]{12}|aws_secret|aws_access_key|\b(?:password|passwd|pwd)\s*=\s*['\"][^'\"]+['\"]", src, re.I)


def test_inputs_are_never_logged_or_printed(api, monkeypatch, caplog, capfd):
    import logging
    caplog.set_level(logging.DEBUG)
    marker = "ZEBRA-MOON-4711"
    run_id = ndjson(api, {**BODY, "question": f"What if {marker}?"})[-1]["result"]["run_id"]
    api.post("/api/run", json={**BODY, "question": marker * 400})                  # refused
    api.post("/api/run", json={**BODY, "portfolio": {marker: 1.0}})                # refused
    monkeypatch.setattr(pipeline, "run", lambda *a, **k: (_ for _ in ()).throw(KeyError(marker)))
    ndjson(api, {**BODY, "question": marker})                                      # a crash that carries the input
    monkeypatch.setattr(pipeline, "recheck", lambda *a: (_ for _ in ()).throw(KeyError(marker)))
    api.post("/api/recheck", json={"run_id": run_id, "limits": {}})
    out, err = capfd.readouterr()
    assert marker not in caplog.text and marker not in out and marker not in err


# ---- integration: the real pipeline on the fake engine (skipped while pipeline.py or tests/fake_engine.py is missing;
# until Task 3 lands, the jsonable double above stands in for pipeline.jsonable) ----

def _integration_ready():
    if STUBBED:
        return False
    try:
        import fake_engine  # noqa: F401
    except ImportError:
        return False
    return all(hasattr(pipeline, n) for n in ("Engine", "real_engine", "STEPS", "run"))


READY = _integration_ready()


@pytest.fixture()
def client(monkeypatch, tmp_path):
    if not READY:
        pytest.skip("pipeline.py (Task 2) and tests/fake_engine.py are not on main yet")
    from fake_engine import fake_engine, ROBERT_Q
    monkeypatch.setattr(pipeline, "demo_questions", lambda: {" ".join(ROBERT_Q.lower().split())})   # the scripted questions
    monkeypatch.setattr(pipeline, "real_engine", lambda: fake_engine())
    monkeypatch.setattr(pipeline, "DEMO_DIR", tmp_path, raising=False)      # Task 3 name; absent until it lands
    monkeypatch.delenv("EPICENTRE_DEMO", raising=False)
    monkeypatch.delenv(server.PASSWORD_ENV, raising=False)
    monkeypatch.delenv(server.ORIGIN_SECRET_ENV, raising=False)
    monkeypatch.delenv(server.REQUIRE_PASSWORD_ENV, raising=False)
    server.RUNS.clear()
    server.clear_health_cache()
    return TestClient(server.app)


def robert_body():
    from fake_engine import ROBERT_PLAN, ROBERT_Q
    return {"portfolio": ROBERT_PLAN["portfolio"], "amount": 600000, "profile": ROBERT_PLAN["profile"],
            "question": ROBERT_Q, "pilot": "robert"}


def test_integration_run_streams_progress_then_the_result(client):
    lines = ndjson(client, robert_body())
    assert lines[0]["type"] == "progress" and lines[-1]["type"] == "result"
    assert {l["step"] for l in lines[:-1]} == set(pipeline.STEPS)
    r = lines[-1]["result"]
    assert r["verdict"] == "Incompatible" and server.RUNS.get(r["run_id"]) is not None
    assert "_analysis" not in r and r["disclaimer"] == pipeline.DISCLAIMER


@pytest.mark.parametrize("patch, words", [({"portfolio": {"XIU.TO": 0.5, "XBB.TO": 0.4}}, "add up to 90 %"),
                                          ({"portfolio": {"ZAG.TO": 1.0}}, "ZAG.TO is not in the dataset"),
                                          ({"amount": 0}, "above $0"), ({"as_of": "2030-01-01"}, "Pick a date")])
def test_integration_bad_flight_plans_are_refused_in_plain_english(client, patch, words):
    r = client.post("/api/run", json={**robert_body(), **patch})
    assert r.status_code == 422 and r.json()["status"] == "error" and words in r.json()["message"]


def test_integration_recheck_is_fast_and_expired_runs_are_plain(client, monkeypatch):
    import time
    monkeypatch.setattr(pipeline, "recheck", lambda result, limits: {"checks": [], "verdict": "Tension", "kpis": {},
                                                                     "sensitivity": None}, raising=False)
    run_id = ndjson(client, robert_body())[-1]["result"]["run_id"]

    def no_rerun(*a, **k):
        raise AssertionError("a recheck must not run the pipeline again")

    monkeypatch.setattr(pipeline, "run", no_rerun)             # "fast" = no new run, no model: a fact, not a clock
    t = time.perf_counter()
    r = client.post("/api/recheck", json={"run_id": run_id, "limits": {"floor": -0.40}})
    assert r.status_code == 200 and r.json()["verdict"] == "Tension" and time.perf_counter() - t < 10      # ledger 29: >= 10 s
    gone = client.post("/api/recheck", json={"run_id": "nope", "limits": {}})
    assert gone.status_code == 404 and gone.json()["message"] == EXPIRED


def test_integration_unexpected_errors_never_leak(client, monkeypatch):
    def boom(*a, **k):
        raise ValueError("secret internals")
    monkeypatch.setattr(pipeline, "recheck", boom, raising=False)
    run_id = ndjson(client, robert_body())[-1]["result"]["run_id"]
    r = client.post("/api/recheck", json={"run_id": run_id, "limits": {}})
    assert r.status_code == 500 and "secret" not in r.text and "Traceback" not in r.text


def test_integration_validation_errors_are_plain(client):
    r = client.post("/api/run", json={"amount": 1})
    assert r.status_code == 422 and r.json()["message"].startswith("The request has a missing or invalid field: ")


def test_integration_health_wire_and_pilots_shapes(client):
    assert set(client.get("/api/health").json()) == {"data", "bedrock", "guardrail", "holdings", "deep"}
    assert isinstance(client.get("/api/wire").json()["items"], list)
    assert client.get("/api/pilots").status_code in (200, 503)


# ---- integration: saved runs and the demo replay through the API (plan D Task 3) ----

def _record_robert():
    """Save the fake engine's live Robert run (it has a debrief) the way scripts/record_demo.py does."""
    from fake_engine import ROBERT_PLAN, ROBERT_Q
    live = pipeline.run(ROBERT_PLAN, ROBERT_Q)                       # the `client` fixture puts the fake engine behind real_engine
    return live, pipeline.save_run(live, ROBERT_PLAN, ROBERT_Q)


def test_integration_demo_run_is_a_plain_404_until_robert_is_saved_then_a_replay_that_can_be_rechecked(client, monkeypatch):
    import shutil
    monkeypatch.setattr(pipeline, "recheck", lambda result, limits: {"checks": [], "verdict": "Tension", "kpis": {},
                                                                     "sensitivity": None}, raising=False)
    assert error_of(client.get("/api/demo-run"), 404) == "There are no saved runs yet."
    live, path = _record_robert()
    shutil.copy(path, pipeline.DEMO_DIR / "default.json")            # what scripts/record_demo.py does for Robert
    r = client.get("/api/demo-run")
    body = r.json()
    assert r.status_code == 200 and body["mode"] == "demo_replay" and body["verdict"] == live["verdict"]
    assert body["message"].startswith("Demo mode: this is the saved run for this exact question, recorded on ")
    assert server.RUNS.get(body["run_id"]) is not None and body["run_id"] != live["run_id"]
    assert client.post("/api/recheck", json={"run_id": body["run_id"], "limits": {}}).status_code == 200


def test_integration_demo_mode_replays_the_saved_run_through_the_api(client, monkeypatch):
    """The API turns 600000 into 600000.0 and normalizes the weights; the replay must still find the recorded run."""
    _record_robert()
    monkeypatch.setenv("EPICENTRE_DEMO", "1")
    with monkeypatch.context() as m:
        m.setattr(pipeline, "real_engine", lambda: (_ for _ in ()).throw(AssertionError("no engine in a replay")))
        lines = ndjson(client, robert_body())
    assert [(l["step"], l["status"], l["detail"]) for l in lines[:-1]] == [(s, "done", "saved run") for s in pipeline.STEPS]
    result = lines[-1]["result"]
    assert result["mode"] == "demo_replay" and result["verdict"] == "Incompatible" and "_analysis" not in result
    assert server.RUNS.get(result["run_id"]) is not None
    other = ndjson(client, {**robert_body(), "question": "What if the chip war heats up?"})[-1]["result"]
    assert other["mode"] == "live" and other["debrief"] is None and other["message"].startswith("Demo mode: no saved run")


# ---- fix round 1: the stream always ends; a user key is capped in the message; body cap; health cache ----

def drain(stream, seconds=5):
    """Read a stream to its end in a helper thread, so a hang fails this test instead of freezing the suite."""
    lines = []
    reader = threading.Thread(target=lambda: lines.extend(stream), daemon=True)
    reader.start()
    reader.join(seconds)
    assert not reader.is_alive(), "the stream never ended"
    return [json.loads(line) for line in lines]


@pytest.mark.parametrize("exc_type", [asyncio.CancelledError, SystemExit, KeyboardInterrupt])
def test_the_stream_ends_with_a_plain_error_when_the_run_raises_a_base_exception(monkeypatch, exc_type):
    escaped = []
    monkeypatch.setattr(threading, "excepthook", lambda args: escaped.append(args.exc_type))

    def work(progress):
        progress({"type": "progress", "step": "OBSERVE"})
        raise exc_type("secret internals")

    lines = drain(server.ndjson_lines(work))
    assert lines == [{"type": "progress", "step": "OBSERVE"},
                     {"type": "result", "result": {"status": "error", "message": GENERIC_500}}]
    for worker in threading.enumerate():
        if worker.name == "epicentre-run":
            worker.join(5)
    # exit requests are passed on once the stream is closed; a cancellation is only an error line
    assert escaped == ([exc_type] if exc_type in (SystemExit, KeyboardInterrupt) else [])


def test_a_long_user_key_is_capped_at_40_characters_in_the_validation_message(api):
    msg = error_of(api.post("/api/run", json={**BODY, "portfolio": {"Z" * 500: -1.0}}), 422)
    assert msg.startswith("The request has a missing or invalid field: portfolio.")
    assert msg.endswith("Z" * 40 + "….") and "Z" * 41 not in msg and len(msg) < 110
    short = error_of(api.post("/api/run", json={**BODY, "portfolio": {"XBB.TO": -1.0}}), 422)
    assert short == "The request has a missing or invalid field: portfolio.XBB.TO."      # short keys are untouched


def test_a_body_over_64_kb_is_refused_before_any_work(api):
    msg = error_of(api.post("/api/run", json={**BODY, "padding": "x" * 70_000}), 413)
    assert msg == "That request is too large." and not api.calls.run
    assert api.post("/api/recheck", json={"run_id": "nope", "limits": {}, "padding": "x" * 70_000}).status_code == 413
    assert ndjson(api, {**BODY, "padding": "x" * 60_000})[-1]["type"] == "result"      # under the cap: normal


def test_the_cap_also_holds_without_a_content_length_header(api):
    def chunks():                                           # sent as Transfer-Encoding: chunked, no Content-Length
        yield b'{"portfolio": {"XIU.TO": 1}, "amount": 1, "padding": "'
        for _ in range(8):
            yield b"x" * 10_000
        yield b'"}'
    r = api.post("/api/run", content=chunks(), headers={"content-type": "application/json"})
    assert "content-length" not in r.request.headers and error_of(r, 413) == "That request is too large."
    assert not api.calls.run


def test_the_cap_does_not_hide_the_password(api, monkeypatch):
    monkeypatch.setenv(server.PASSWORD_ENV, "pw")
    assert error_of(api.post("/api/run", json={**BODY, "padding": "x" * 70_000}), 401) == MSG_401
    big = api.post("/api/run", json={**BODY, "padding": "x" * 70_000}, headers=basic("u", "pw"))
    assert big.status_code == 413 and big.headers["x-content-type-options"] == "nosniff"


MSG_401 = "Enter the password to open EPICENTRE."


def test_health_is_cached_for_30_seconds_and_probes_once(api, monkeypatch):
    probes = []

    def session():
        probes.append(1)
        return types.SimpleNamespace(get_credentials=lambda: object())
    monkeypatch.setattr(server.boto3, "Session", session)
    clock = {"t": 1000.0}
    monkeypatch.setattr(server, "_now", lambda: clock["t"])
    assert server.HEALTH_TTL == 30
    first = api.get("/api/health").json()
    clock["t"] += 29.9
    assert api.get("/api/health").json() == first and len(probes) == 1
    clock["t"] += 0.2                                                  # 30.1 s after the first probe
    api.get("/api/health")
    assert len(probes) == 2


def test_a_burst_of_health_calls_makes_one_probe(api, monkeypatch):
    import time
    probes = []

    def session():
        probes.append(1)
        time.sleep(0.2)                                               # a slow credential probe
        return types.SimpleNamespace(get_credentials=lambda: None)
    monkeypatch.setattr(server.boto3, "Session", session)
    results = []
    threads = [threading.Thread(target=lambda: results.append(server.health_payload())) for _ in range(8)]
    [t.start() for t in threads]
    [t.join(10) for t in threads]
    assert len(probes) == 1 and len(results) == 8 and all(r == results[0] for r in results)
    assert set(results[0]) == {"data", "bedrock", "guardrail", "holdings", "deep"} and results[0]["bedrock"] is False


# ---- one saved run per investor: GET /api/demo-run?pilot=<id>; a replay keeps what a recheck needs (plan D Task 3) ----

def test_demo_run_asks_the_loader_for_the_investor_in_the_query(api, monkeypatch):
    asked = []

    def loader(pilot="robert"):
        asked.append(pilot)
        return {"run_id": f"demo-{pilot}", "mode": "demo_replay", "status": "ok"} if pilot == "mateo" else None

    monkeypatch.setattr(pipeline, "default_demo_run", loader)
    r = api.get("/api/demo-run?pilot=mateo")
    assert r.status_code == 200 and r.json()["run_id"] == "demo-mateo" and asked == ["mateo"]
    assert server.RUNS.get("demo-mateo") is not None
    assert error_of(api.get("/api/demo-run?pilot=amira"), 404) == "There is no saved run for that investor."
    assert error_of(api.get("/api/demo-run?pilot=robert"), 404) == "There is no saved run for that investor."
    assert error_of(api.get("/api/demo-run"), 404) == "There are no saved runs yet." and asked[-1] == "robert"


def test_integration_each_investor_gets_their_own_saved_run_and_an_unknown_one_a_plain_404(client):
    import shutil
    from fake_engine import ROBERT_PLAN, ROBERT_Q
    live, path = _record_robert()
    shutil.copy(path, pipeline.DEMO_DIR / "default.json")
    plan = {**ROBERT_PLAN, "pilot": "mateo", "amount": 100000}                   # his own run: his own amount, key and pilot id
    shutil.copy(pipeline.save_run(pipeline.run(plan, ROBERT_Q), plan, ROBERT_Q), pipeline.DEMO_DIR / "default_mateo.json")
    assert client.get("/api/demo-run").json()["mode"] == client.get("/api/demo-run?pilot=robert").json()["mode"] == "demo_replay"
    mateo = client.get("/api/demo-run?pilot=mateo")
    assert mateo.status_code == 200 and mateo.json()["verdict"] == live["verdict"] and mateo.json()["pilot"] == "mateo"
    assert client.get("/api/demo-run").json()["pilot"] == "robert"
    for pilot in ("amira", "../secret", "Mateo", "x" * 80):
        assert error_of(client.get("/api/demo-run", params={"pilot": pilot}), 404) == "There is no saved run for that investor."


def test_integration_a_replay_served_by_demo_run_keeps_its_analysis_for_a_recheck(client):
    """The page rechecks the first paint like any run: the stored replay has `_analysis`, the browser never does."""
    import shutil
    from fake_engine import ROBERT_PLAN, ROBERT_Q
    live = pipeline.run(ROBERT_PLAN, ROBERT_Q)
    live["_analysis"] = {"after": {"metrics": {"max_drawdown": -0.345}, "esg_flags": {"NVDA", "XOM"}, "limits": {"floor": -0.15},
                                   "market": {"XIU.TO": [1, 2]}}, "today": None}
    shutil.copy(pipeline.save_run(live, ROBERT_PLAN, ROBERT_Q), pipeline.DEMO_DIR / "default.json")
    body = client.get("/api/demo-run").json()
    assert "_analysis" not in body and "analysis" not in body
    kept = server.RUNS.get(body["run_id"])["_analysis"]
    assert kept == {"after": {"metrics": {"max_drawdown": -0.345}, "esg_flags": {"NVDA"}, "limits": {"floor": -0.15}}, "today": None}

# ---- Task 5: the page is served, offline-safe, in EPICENTRE words, and never falls back to fake data ----
import re
from pathlib import Path

def test_page_and_vendor_are_served(client):
    page = client.get("/")
    assert page.status_code == 200 and "EPICENTRE" in page.text
    assert client.get("/vendor/three/three.module.min.js").status_code == 200    # W-S1: three.js replaced plotly on the page
    assert client.get("/api/health").status_code == 200          # the API wins over the static mount

def test_no_network_assets_and_licences_listed():
    html, css, js = [(Path("web") / f).read_text() for f in ("index.html", "styles.css", "app.js")]
    assert not re.search(r'(?:src|href)=["\']https?://', html) and not re.search(r"url\(\s*['\"]?https?://", css)
    assert not re.search(r"fetch\(\s*['\"`]https?://", js) and "innerHTML" not in js
    lic = Path("web/vendor/LICENSES.md").read_text()
    assert all(name in lic for name in ("three/three.module.min.js", "black-marble-2016-4096.jpg", "earth-poster.jpg", "B612", "Archivo"))

def test_live_page_never_falls_back_to_fake_data():
    js = Path("web/data.js").read_text()                       # the Replay's data layer (lane U0) asks for every saved run
    assert "/api/demo-run" in js and not re.search(r"demo-run[^\n]*catch[^\n]*fake_result", js) and "fake_result" not in js

BANNED = re.compile(r"\b(preflight|pilots?|flight plan|flight recorder|flight paths?|weather briefing|turbulence (?:map|check)|take[- ]off|storms?|captain)\b", re.I)

def visible_strings():
    html = Path("web/index.html").read_text()
    text = re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", html, flags=re.S)
    attrs = re.findall(r'(?:aria-label|title|placeholder|alt|content)="([^"]*)"', html)
    js = Path("web/app.js").read_text() + Path("web/lib.js").read_text()
    lits = [m.group(2) for m in re.finditer(r"([\"'`])((?:\\.|(?!\1).)*)\1", js)]
    return [text, *attrs, *[l for l in lits if not l.startswith("/api/") and not re.fullmatch(r"[a-z_]+", l)]]

def test_visible_words_are_epicentre():      # identifiers (known_storms, storm_map, /api/pilots) never match: no word boundary or excluded
    assert sorted({m.group(0) for s in visible_strings() for m in BANNED.finditer(s)}) == []


# ---- Task 15: scripts/record_demo.py and the static read-only demo ----
from scripts import record_demo


def _personas(tmp_path, monkeypatch, pilots=("robert", "mateo", "amira", "canadian")):
    from fake_engine import ROBERT_PLAN
    data = {"pilots": {k: {"name": k.title(), "amount": 100000 + 1000 * i, "profile": ROBERT_PLAN["profile"],
                           "portfolio": ROBERT_PLAN["portfolio"], "request": None, "question": f"{k} question"}
                       for i, k in enumerate(pilots)},
            "storm_cards": {f: {"label": f, "families": [f], "question": f"{f} question"}
                            for f in ("tariffs", "war_oil", "chips", "rates")}}
    path = tmp_path / "personas.json"
    path.write_text(json.dumps(data))
    monkeypatch.setattr(pipeline, "PERSONAS_PATH", path, raising=False)      # D Task 6 name; absent until it lands
    monkeypatch.setattr(server, "PERSONAS_PATH", path)


def test_record_plan_is_four_pilots_by_five_questions(tmp_path, monkeypatch):
    _personas(tmp_path, monkeypatch)
    plan = record_demo.plan_runs(["robert", "mateo", "amira", "canadian"], ["tariffs", "war_oil", "chips", "rates"])
    assert len(plan) == 20 and plan[0]["question"] == "robert question" and plan[1]["question"] == "tariffs question"
    assert [p["pilot"] for p in plan[:6]] == ["robert"] * 5 + ["mateo"] and plan[5]["question"] == "mateo question"
    assert set(plan[0]["flight_plan"]) == {"portfolio", "amount", "profile", "limits", "pilot"}
    assert plan[0]["flight_plan"]["pilot"] == "robert" and plan[0]["flight_plan"]["limits"] is None


def test_record_plan_refuses_an_unknown_investor_or_storm(tmp_path, monkeypatch):
    _personas(tmp_path, monkeypatch)
    for pilots, storms in ((["nobody"], ["tariffs"]), (["robert"], ["floods"])):
        with pytest.raises(record_demo.RecordError):
            record_demo.plan_runs(pilots, storms)


def test_record_saves_only_real_runs(tmp_path, monkeypatch):
    from fake_engine import ROBERT_PLAN, ROBERT_Q, fake_engine
    _personas(tmp_path, monkeypatch)
    monkeypatch.setattr(pipeline, "DEMO_DIR", tmp_path)
    real = pipeline.run(ROBERT_PLAN, ROBERT_Q, engine=fake_engine())            # fake engine: has a debrief
    monkeypatch.setattr(pipeline, "run", lambda plan, q, *a, **k: dict(real, question=q, debrief=None if "chips" in q else real["debrief"]))
    monkeypatch.setattr(pipeline, "time_machine", lambda r, as_of, open=False: {"months": []}, raising=False)
    out = record_demo.record(record_demo.plan_runs(["robert"], ["tariffs", "chips"]))
    assert [o["saved"] is not None for o in out] == [True, True, False] and out[2]["why"]
    assert (tmp_path / "default.json").exists()
    assert out[0]["receipt"]["total"] == real["receipt"]["total"] and out[0]["mode"] == "live" and out[0]["verdict"]


def test_record_writes_each_investors_default_and_fills_the_month_table(tmp_path, monkeypatch):
    from fake_engine import ROBERT_PLAN, ROBERT_Q, fake_engine
    _personas(tmp_path, monkeypatch)
    monkeypatch.setattr(pipeline, "DEMO_DIR", tmp_path)
    real = pipeline.run(ROBERT_PLAN, ROBERT_Q, engine=fake_engine())
    monkeypatch.setattr(pipeline, "run", lambda plan, q, *a, **k: dict(real, question=q, pilot=plan["pilot"]))
    months = {"months": [{"as_of": "2025-01-31", "verdict": "Compatible"}]}
    monkeypatch.setattr(pipeline, "time_machine", lambda r, as_of, open=False: months, raising=False)
    out = record_demo.record(record_demo.plan_runs(["robert", "mateo"], ["tariffs"]))
    assert all(o["saved"] for o in out) and len(out) == 4
    assert (tmp_path / "default.json").exists() and (tmp_path / "default_mateo.json").exists()
    assert not (tmp_path / "default_robert.json").exists()
    saved = json.loads((tmp_path / "default_mateo.json").read_text())
    assert saved["result"]["time_machine"] == months and saved["result"]["pilot"] == "mateo"


def test_record_calls_the_proof_hooks_when_plan_p_has_landed(tmp_path, monkeypatch):
    from fake_engine import ROBERT_PLAN, ROBERT_Q, fake_engine
    _personas(tmp_path, monkeypatch)
    monkeypatch.setattr(pipeline, "DEMO_DIR", tmp_path)
    real = pipeline.run(ROBERT_PLAN, ROBERT_Q, engine=fake_engine())
    monkeypatch.setattr(pipeline, "run", lambda plan, q, *a, **k: dict(real, question=q))
    monkeypatch.setattr(pipeline, "time_machine", lambda r, as_of, open=False: {"months": []}, raising=False)
    monkeypatch.setattr(pipeline, "precompute_proofs", lambda r, **k: {**r, "envelope": {"as_of": "2025-01-31", "seal": "x"}},
                        raising=False)
    out = record_demo.record(record_demo.plan_runs(["robert"], []))
    assert out[0]["saved"] and json.loads(open(out[0]["saved"]).read())["result"]["envelope"]["seal"] == "x"


def test_record_reports_a_failing_hook_and_does_not_save(tmp_path, monkeypatch):
    from fake_engine import ROBERT_PLAN, ROBERT_Q, fake_engine
    _personas(tmp_path, monkeypatch)
    monkeypatch.setattr(pipeline, "DEMO_DIR", tmp_path)
    real = pipeline.run(ROBERT_PLAN, ROBERT_Q, engine=fake_engine())
    monkeypatch.setattr(pipeline, "run", lambda plan, q, *a, **k: dict(real, question=q))
    monkeypatch.setattr(pipeline, "time_machine", lambda r, as_of, open=False: 1 / 0, raising=False)
    monkeypatch.setattr(pipeline, "DEMO_DIR", tmp_path / "saved")
    (tmp_path / "saved").mkdir()
    out = record_demo.record(record_demo.plan_runs(["robert"], []))
    assert out[0]["saved"] is None and "ZeroDivisionError" in out[0]["why"] and not list((tmp_path / "saved").iterdir())


def test_record_dry_run_runs_nothing(tmp_path, monkeypatch):
    _personas(tmp_path, monkeypatch)
    monkeypatch.setattr(pipeline, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("a dry run runs nothing")))
    out = record_demo.record(record_demo.plan_runs(["robert", "mateo"], ["tariffs"]), dry_run=True)
    assert len(out) == 4 and all(o["saved"] is None and o["why"] == "dry run" for o in out)


def _tiny_web(tmp_path, monkeypatch):
    """A small stand-in for web/ (the build reads server.WEB_DIR at call time)."""
    web = tmp_path / "web_src"
    (web / "vendor").mkdir(parents=True)
    (web / "index.html").write_text('<!doctype html><html><head><meta charset="utf-8"><title>EPICENTRE</title></head>'
                                    "<body></body></html>")
    for name in ("app.js", "lib.js", "styles.css", "vendor/x.js"):
        (web / name).write_text("// ok")
    for name in ("fake_result.json", "fake_extras.json", "story-data.js", ".DS_Store", "etf_holdings.csv"):
        (web / name).write_text("{}")
    monkeypatch.setattr(server, "WEB_DIR", web)
    return web


REAL_SOURCE = "prices_daily.csv, fx_usdcad_daily.csv, macro_rates.csv (data/starter, a test stand-in for the real pack)"


def _real_sources(obj):
    """In place: every `source` text that names fake data becomes a real-looking source (the fake engine writes FAKE sources)."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "source" and isinstance(value, str) and "fake" in value.lower():
                obj[key] = REAL_SOURCE
            else:
                _real_sources(value)
    elif isinstance(obj, list):
        for value in obj:
            _real_sources(value)
    return obj


def _real_run(monkeypatch, tmp_path, plan=None, question=None, mutate=None):
    """A saved run that says REAL (the fake engine writes FAKE sources, so they are rewritten and the label function patched)."""
    from fake_engine import ROBERT_PLAN, ROBERT_Q, fake_engine
    plan, question = plan or ROBERT_PLAN, question or ROBERT_Q
    monkeypatch.setattr(pipeline, "DEMO_DIR", tmp_path / "runs_src")
    (tmp_path / "runs_src").mkdir(exist_ok=True)
    monkeypatch.setattr(pipeline, "_data_label", lambda result: "REAL")
    monkeypatch.setattr(pipeline, "demo_questions", lambda: {" ".join(question.lower().split())})     # a scripted question
    r = _real_sources(pipeline.run(plan, question, engine=fake_engine()))
    if mutate:
        mutate(r)
    return r, pipeline.save_run(r, plan, question)


def _series(n=300):
    return [100.0 + i * 0.1 for i in range(n)]


def _leaky(r):
    """What a live run can carry beyond the portfolio: ETF constituents, issuer rows, a per-asset price table."""
    r["events"] = [{"event_id": "e1", "family": "tariffs", "exposed": [
        {"ticker": "CNQ.TO", "channel": "sector", "via": "XIU.TO"},
        {"ticker": "XIU.TO", "channel": "country", "via": None},
        {"ticker": "NVDA", "channel": "country", "via": "direct"}]}]
    r["lookthrough"]["after"]["stocks"] = {"NVDA": {"direct": 0.4, "via": [], "total": 0.4},
                                         "RY.TO": {"direct": 0.0, "via": [{"etf": "XIU.TO", "weight": 0.02}], "total": 0.02}}
    r["lookthrough"]["after"]["esg_indirect"] = {"CNQ.TO": 0.012}
    r["trace"][0]["rows"] = [{"file": "prices_daily.csv", "date": "2022-10-14", "ticker": "NVDA", "value": 11.19}]


def _no_leaks(obj, path="$"):
    """An independent check of the public-content rule: no per-asset price series, no holdings row, no `via`."""
    found = []
    if isinstance(obj, dict):
        if "via" in obj or {"etf", "weight"} <= set(obj) or "holdings" in obj:
            found.append(path)
        for k, v in obj.items():
            if k in server.UNIVERSE_TICKERS and isinstance(v, list) and len(v) >= 20 and all(isinstance(x, (int, float)) for x in v):
                found.append(f"{path}.{k}")
            found += _no_leaks(v, f"{path}.{k}")
        if obj.get("name") in server.UNIVERSE_TICKERS and any(isinstance(v, list) and len(v) >= 20 for v in obj.values()):
            found.append(path)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found += _no_leaks(v, f"{path}[{i}]")
    return found


def test_static_build_is_read_only(tmp_path, monkeypatch):
    _tiny_web(tmp_path, monkeypatch)
    _real_run(monkeypatch, tmp_path)
    out = record_demo.build_static(tmp_path / "site")
    assert '<meta name="epicentre-mode" content="static">' in (out / "index.html").read_text()
    assert not (out / "fake_result.json").exists() and not (out / "fake_extras.json").exists()
    index = json.loads((out / "runs/index.json").read_text())
    assert index and set(index[0]) >= {"key", "pilot", "question", "as_of", "file"}
    assert (out / index[0]["file"]).exists() and (out / "runs/default.json").exists()
    assert all('"_analysis"' not in f.read_text() and '"via"' not in f.read_text() for f in (out / "runs").glob("*.json"))


def test_static_build_opens_each_investor_on_the_run_their_default_file_names(tmp_path, monkeypatch):
    """Two saved runs of Robert's own question (a twin with other inputs, saved first): runs/robert.json is the run that
    default.json names, as /api/demo-run serves it, never the older twin (the static demo opened on Robert's technology-cap
    variant on 15 Nov: 13 of 13 on the page, 15 of 15 in the docs)."""
    import shutil
    from fake_engine import ROBERT_PLAN
    _tiny_web(tmp_path, monkeypatch)
    _, twin = _real_run(monkeypatch, tmp_path, plan={**ROBERT_PLAN, "amount": 500000})
    _, plain = _real_run(monkeypatch, tmp_path)
    data = json.loads(twin.read_text())
    data["saved_at"] = "2026-11-01T00:00:00+00:00"                 # the twin is older, so it ranks first in the build order
    twin.write_text(json.dumps(data))
    shutil.copyfile(plain, plain.parent / "default.json")
    out = record_demo.build_static(tmp_path / "site")
    page = json.loads((out / "runs/robert.json").read_text())
    assert page["run_id"] == json.loads((out / "runs/default.json").read_text())["run_id"]
    assert page["run_id"] != json.loads((out / f"runs/{data['key']}.json").read_text())["run_id"]


def test_static_build_copies_the_web_folder_without_fake_data_or_junk(tmp_path, monkeypatch):
    _tiny_web(tmp_path, monkeypatch)
    _real_run(monkeypatch, tmp_path)
    out = record_demo.build_static(tmp_path / "site")
    names = {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}
    assert {"index.html", "app.js", "lib.js", "styles.css", "vendor/x.js", "runs/index.json", "runs/default.json"} <= names
    assert not {"fake_result.json", "fake_extras.json", "story-data.js", ".DS_Store", "etf_holdings.csv"} & names
    assert not [n for n in names if n.endswith(".csv") or "starter" in n]


def test_static_build_refuses_a_run_that_is_not_real(tmp_path, monkeypatch):
    from fake_engine import ROBERT_PLAN, ROBERT_Q, fake_engine
    _tiny_web(tmp_path, monkeypatch)
    monkeypatch.setattr(pipeline, "DEMO_DIR", tmp_path / "runs_src")
    (tmp_path / "runs_src").mkdir()
    path = pipeline.save_run(pipeline.run(ROBERT_PLAN, ROBERT_Q, engine=fake_engine()), ROBERT_PLAN, ROBERT_Q)
    assert json.loads(path.read_text())["data"] == "FAKE"
    with pytest.raises(record_demo.StaticBuildError, match="FAKE"):
        record_demo.build_static(tmp_path / "site")
    saved = json.loads(path.read_text())
    saved["data"] = "REAL"                                   # a hand-edited label cannot hide FAKE sources in the Result
    path.write_text(json.dumps(saved))
    with pytest.raises(record_demo.StaticBuildError, match="FAKE"):
        record_demo.build_static(tmp_path / "site")
    assert not (tmp_path / "site").exists()


def test_one_unfit_run_stops_the_whole_build(tmp_path, monkeypatch):
    _tiny_web(tmp_path, monkeypatch)
    _real_run(monkeypatch, tmp_path)
    bad = tmp_path / "runs_src" / ("0" * 16 + ".json")
    bad.write_text("{not json")
    with pytest.raises(record_demo.StaticBuildError, match=bad.name):
        record_demo.build_static(tmp_path / "site")
    assert not (tmp_path / "site").exists()


def test_static_build_needs_at_least_one_saved_run(tmp_path, monkeypatch):
    _tiny_web(tmp_path, monkeypatch)
    monkeypatch.setattr(pipeline, "DEMO_DIR", tmp_path / "empty")
    (tmp_path / "empty").mkdir()
    (tmp_path / "empty" / "test_tally.json").write_text("{}")             # other files of the folder are not runs
    with pytest.raises(record_demo.StaticBuildError, match="no saved runs"):
        record_demo.build_static(tmp_path / "site")


def test_static_build_strips_constituents_rows_and_evidence_rows(tmp_path, monkeypatch):
    _tiny_web(tmp_path, monkeypatch)
    _real_run(monkeypatch, tmp_path, mutate=_leaky)
    out = record_demo.build_static(tmp_path / "site")
    result = json.loads((out / "runs/default.json").read_text())
    assert result["events"][0]["exposed"] == [{"ticker": "XIU.TO", "channel": "country"}, {"ticker": "NVDA", "channel": "country"}]
    assert list(result["lookthrough"]["after"]["stocks"]) == ["NVDA"] and result["lookthrough"]["after"]["esg_indirect"] == {}
    assert "via" not in result["lookthrough"]["after"]["stocks"]["NVDA"] and result["trace"][0]["rows"] is None
    assert result["lookthrough"]["after"]["sectors"] and result["lookthrough"]["after"]["countries"]       # aggregates stay
    for f in (out / "runs").glob("*.json"):
        assert _no_leaks(json.loads(f.read_text())) == [], f.name


def _price_tables(r):
    r["trace"][1]["outputs"] = {"NVDA": _series(), "XIU.TO": _series()}                    # a per-asset price table
    r["figures"] = {"flight_paths": {"data": [{"name": "NVDA", "type": "scatter", "y": _series()}], "layout": {}}}


def test_static_build_refuses_a_per_asset_price_series_it_cannot_strip(tmp_path, monkeypatch):
    _tiny_web(tmp_path, monkeypatch)
    _real_run(monkeypatch, tmp_path, mutate=_price_tables)
    with pytest.raises(record_demo.StaticBuildError, match="price series"):
        record_demo.build_static(tmp_path / "site")
    assert not (tmp_path / "site").exists()


def test_the_leak_check_flags_what_it_must_and_passes_the_reference_result():
    ref = json.loads(Path("data/fake/result.json").read_text())
    assert record_demo.find_leaks(ref)                                                      # the reference carries `via`
    assert record_demo.find_leaks(record_demo.public_result(ref)) == []
    assert record_demo.find_leaks({"NVDA": _series()}) and record_demo.find_leaks({"name": "NVDA", "y": _series()})
    assert record_demo.find_leaks({"rows": [{"etf": "XIU.TO", "ticker": "RY.TO", "weight": 0.1}]})
    assert record_demo.find_leaks({"series": {"today": _series(), "after": _series()}}) == []          # portfolio series stay
    assert record_demo.find_leaks({"risk": {"shares": {"NVDA": 0.86, "XIU.TO": 0.07}}}) == []


def test_a_nested_fallback_result_gets_the_same_rules_and_the_proof_keys_survive(tmp_path, monkeypatch):
    proofs = {"consistency": {"held": 3, "total": 3, "rows": []}, "robustness": {"n_break": 4, "variants": []},
              "envelope": {"as_of": "2025-01-31", "scramble_check": {"match": True}}, "navigator_effect": {"same": False},
              "proof_block": {"receipt": {"verified": 22, "total": 22}}}

    def mutate(r):
        _leaky(r)
        r.update(proofs)
        r["fallback_result"] = {"events": [{"event_id": "e1", "exposed": [{"ticker": "CNQ.TO", "channel": "sector", "via": "XIU.TO"}]}],
                                "portfolio": {"XIU.TO": 0.6, "XBB.TO": 0.4}, "trace": [{"id": "T1", "rows": [{"value": 1}]}],
                                "verdict": "Compatible"}

    _tiny_web(tmp_path, monkeypatch)
    _real_run(monkeypatch, tmp_path, mutate=mutate)
    out = record_demo.build_static(tmp_path / "site")
    result = json.loads((out / "runs/default.json").read_text())
    assert all(result[k] == v for k, v in proofs.items())
    fb = result["fallback_result"]
    assert fb["events"][0]["exposed"] == [] and fb["trace"][0]["rows"] is None and fb["verdict"] == "Compatible"
    assert _no_leaks(result) == []


def test_every_replayed_run_is_a_saved_run_with_its_own_labels(tmp_path, monkeypatch):
    _tiny_web(tmp_path, monkeypatch)
    _, path = _real_run(monkeypatch, tmp_path)
    saved = json.loads(path.read_text())
    out = record_demo.build_static(tmp_path / "site")
    index = json.loads((out / "runs/index.json").read_text())
    assert index[0]["key"] == saved["key"] and index[0]["file"] == f"runs/{saved['key']}.json"
    assert index[0]["as_of"] == saved["as_of"] == "2026-11-12" and index[0]["commit"] == saved["commit"]
    run = json.loads((out / index[0]["file"]).read_text())
    assert run == json.loads((out / "runs/default.json").read_text())
    assert run["mode"] == "demo_replay" and run["as_of"] == "2026-11-12" and run["run_id"] == saved["key"][:12]
    assert run["message"].startswith("Demo mode: this is the saved run for this exact question, recorded on ")
    assert "·" not in (out / "runs/index.json").read_text() and "·" not in (out / "index.html").read_text()


def test_the_page_carries_the_commit_and_the_live_app_metas(tmp_path, monkeypatch):
    web = _tiny_web(tmp_path, monkeypatch)
    web.joinpath("index.html").write_text('<html><head><meta name="epicentre-mode" content="live">'
                                          '<meta name="epicentre-commit" content="old"></head><body></body></html>')
    _, path = _real_run(monkeypatch, tmp_path)
    commit = json.loads(path.read_text())["commit"]
    page = (record_demo.build_static(tmp_path / "a") / "index.html").read_text()
    assert page.count("epicentre-mode") == 1 and 'content="live"' not in page and 'content="old"' not in page
    assert f'<meta name="epicentre-commit" content="{commit[:7]}">' in page and "epicentre-live" not in page
    page = (record_demo.build_static(tmp_path / "b", live_url="https://d111.cloudfront.net/") / "index.html").read_text()
    assert '<meta name="epicentre-live" content="https://d111.cloudfront.net/">' in page
    for bad in ("http://x.example", "javascript:alert(1)", 'https://x.example/"><script>', "https://x y", "https://:@",
                "https://admin:secret@d111.cloudfront.net/"):
        with pytest.raises(record_demo.StaticBuildError, match="live"):
            record_demo.build_static(tmp_path / "c", live_url=bad)
    assert not (tmp_path / "c").exists()


def test_a_run_saved_without_a_commit_cannot_be_labelled_so_the_build_refuses(tmp_path, monkeypatch):
    _tiny_web(tmp_path, monkeypatch)
    _, path = _real_run(monkeypatch, tmp_path)
    saved = json.loads(path.read_text())
    saved["commit"] = "unknown"
    path.write_text(json.dumps(saved))
    with pytest.raises(record_demo.StaticBuildError, match="commit"):
        record_demo.build_static(tmp_path / "site")


def test_the_index_follows_the_recording_plan_and_default_is_roberts_own_run(tmp_path, monkeypatch):
    from fake_engine import ROBERT_PLAN, ROBERT_Q, fake_engine
    _tiny_web(tmp_path, monkeypatch)
    _personas(tmp_path, monkeypatch, pilots=("robert", "mateo"))
    monkeypatch.setattr(pipeline, "DEMO_DIR", tmp_path / "runs_src")
    (tmp_path / "runs_src").mkdir()
    monkeypatch.setattr(pipeline, "_data_label", lambda result: "REAL")
    real = _real_sources(pipeline.run(ROBERT_PLAN, ROBERT_Q, engine=fake_engine()))
    monkeypatch.setattr(pipeline, "run", lambda plan, q, *a, **k: dict(real, question=q, pilot=plan["pilot"]))
    plan = record_demo.plan_runs(["robert", "mateo"], ["tariffs"])
    assert all(o["saved"] for o in record_demo.record(list(reversed(plan))))               # saved in a different order
    out = record_demo.build_static(tmp_path / "site")
    index = json.loads((out / "runs/index.json").read_text())
    assert [(e["pilot"], e["question"]) for e in index] == [("robert", "robert question"), ("robert", "tariffs question"),
                                                              ("mateo", "mateo question"), ("mateo", "tariffs question")]
    default = json.loads((out / "runs/default.json").read_text())
    assert default["question"] == "robert question" and default["pilot"] == "robert"


def test_nothing_secret_or_licensed_reaches_the_output(tmp_path, monkeypatch):
    web = _tiny_web(tmp_path, monkeypatch)
    _real_run(monkeypatch, tmp_path)
    (web / "starter").mkdir()
    (web / "starter" / "prices_daily.csv").write_text("date,ticker,close\n")
    out = record_demo.build_static(tmp_path / "site")
    assert not [p for p in out.rglob("*") if p.suffix == ".csv" or "starter" in p.parts or p.name == "etf_holdings.csv"]
    (web / "app.js").write_text("const k = 'AKIAABCDEFGHIJKLMNOP';")                          # a canary access key id
    with pytest.raises(record_demo.StaticBuildError, match="credential"):
        record_demo.build_static(tmp_path / "second")
    assert not (tmp_path / "second").exists() and not list(tmp_path.glob("second*"))


def test_a_build_replaces_an_earlier_build_but_never_a_foreign_folder(tmp_path, monkeypatch):
    web = _tiny_web(tmp_path, monkeypatch)
    _real_run(monkeypatch, tmp_path)
    site = tmp_path / "site"
    record_demo.build_static(site)
    (site / "stale.txt").write_text("left over")
    record_demo.build_static(site)
    assert not (site / "stale.txt").exists() and (site / "runs/index.json").exists()
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "notes.txt").write_text("mine")
    with pytest.raises(record_demo.StaticBuildError, match="not an empty folder"):
        record_demo.build_static(foreign)
    assert (foreign / "notes.txt").read_text() == "mine"
    empty = tmp_path / "empty_site"
    empty.mkdir()
    assert record_demo.build_static(empty) == empty
    for inside in (web / "site", web, tmp_path):                                              # never into or over the source
        with pytest.raises(record_demo.StaticBuildError):
            record_demo.build_static(inside)
    assert (web / "index.html").exists()


def test_main_prints_the_plan_builds_the_site_and_exits_plainly(tmp_path, monkeypatch, capsys):
    _tiny_web(tmp_path, monkeypatch)
    _personas(tmp_path, monkeypatch)
    assert record_demo.main(["--dry-run"]) == 0
    lines = [l for l in capsys.readouterr().out.splitlines() if l.strip()]
    assert len(lines) == 20 and lines[0].split()[1] == "robert" and "robert question" in lines[0]
    assert record_demo.main(["--dry-run", "--pilots", "robert", "--storms", "chips"]) == 0
    assert len([l for l in capsys.readouterr().out.splitlines() if l.strip()]) == 2
    monkeypatch.setattr(pipeline, "DEMO_DIR", tmp_path / "none")
    assert record_demo.main(["--static", str(tmp_path / "site")]) == 1
    assert "no saved runs" in capsys.readouterr().out and not (tmp_path / "site").exists()
    _real_run(monkeypatch, tmp_path)
    assert record_demo.main(["--static", str(tmp_path / "site"), "--live", "https://d111.cloudfront.net/"]) == 0
    printed = capsys.readouterr().out
    assert "1 saved run" in printed and str(tmp_path / "site") in printed and (tmp_path / "site/runs/default.json").exists()
    with pytest.raises(SystemExit):
        record_demo.main(["--static", str(tmp_path / "x"), "--dry-run"])


def test_main_records_one_printed_line_per_run_and_exits_zero_only_when_all_saved(tmp_path, monkeypatch, capsys):
    from fake_engine import ROBERT_PLAN, ROBERT_Q, fake_engine
    _personas(tmp_path, monkeypatch)
    monkeypatch.setattr(pipeline, "DEMO_DIR", tmp_path)
    real = pipeline.run(ROBERT_PLAN, ROBERT_Q, engine=fake_engine())
    monkeypatch.setattr(pipeline, "run", lambda plan, q, *a, **k: dict(real, question=q, debrief=None if "chips" in q else real["debrief"]))
    monkeypatch.setattr(pipeline, "time_machine", lambda r, as_of, open=False: {"months": []}, raising=False)
    assert record_demo.main(["--pilots", "robert", "--storms", "tariffs"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2 and lines[0].startswith("robert   Incompatible 15/15 live        ") and lines[0].endswith(".json")
    assert record_demo.main(["--pilots", "robert", "--storms", "tariffs,chips"]) == 1
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 3 and "not saved: " in lines[2] and "chips" not in lines[2]


def _daily_dates(obj, path="$"):
    """An independent check of the public cut (ledger 29): a list of 20 or more dates whose gaps are mostly under four calendar
    days is a daily series."""
    from datetime import date
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            found += _daily_dates(v, f"{path}.{k}")
    elif isinstance(obj, list):
        if len(obj) >= 20 and all(isinstance(d, str) and len(d) >= 10 and d[4] == "-" and d[7] == "-" for d in obj):
            days = [date.fromisoformat(d[:10]) for d in obj]
            if sum((b - a).days < 4 for a, b in zip(days, days[1:])) * 2 > len(days) - 1:
                found.append(path)
        for i, v in enumerate(obj):
            found += _daily_dates(v, f"{path}[{i}]")
    return found


def _source_texts(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "source" and isinstance(v, str):
                yield v
            else:
                yield from _source_texts(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _source_texts(v)


@pytest.mark.skipif(not list(Path("data/demo_runs").glob("*.json")), reason="no saved runs on this machine yet")
def test_committed_saved_runs_are_public_safe():
    """Red gate 8 and ledger 23, 29: whatever is committed in data/demo_runs carries no constituent, holdings row or price table,
    no daily series, no company named by a check, no one-line side, and is REAL by its own file (a source, none naming fake)."""
    for path in sorted(Path("data/demo_runs").glob("*.json")):
        saved = json.loads(path.read_text())
        if "result" not in saved:                                       # test_tally.json and the like
            continue
        result = saved["result"]
        assert saved["data"] == "REAL", path.name
        assert _no_leaks(result) == [] and _daily_dates(result) == [], path.name
        assert "figures" not in result and "bdata" not in json.dumps(result), path.name          # ledger 30: no charts, no base64
        sources = [s for s in _source_texts(result) if s.strip()]
        assert sources and not [s for s in sources if "fake" in s.lower()], path.name
        today = (result.get("baseline") or {}).get("portfolio") or result.get("portfolio") or {}
        lines = set(today) | set(result.get("portfolio") or {})
        for mix in (today, result.get("portfolio") or {}):
            assert len([w for w in mix.values() if w > 0]) >= 2 and max(mix.values()) / sum(mix.values()) < 0.995, path.name
        for checks in (result.get("checks"), (result.get("baseline") or {}).get("checks")):
            assert all(c.get("holding") in {None, *lines} for c in checks or []), path.name


def test_the_independent_checks_of_the_committed_runs_see_what_they_must():
    daily = [f"2022-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(60)]
    assert _daily_dates({"series": {"dates": daily}}) == ["$.series.dates"]
    assert _daily_dates({"series": {"dates": daily[::5]}}) == [] and _daily_dates({"d": daily[:19]}) == []
    assert list(_source_texts({"a": [{"source": "x"}], "b": {"source": "y"}})) == ["x", "y"]


def test_record_cuts_constituents_and_rows_before_anything_is_saved(tmp_path, monkeypatch):
    from fake_engine import ROBERT_PLAN, ROBERT_Q, fake_engine
    _personas(tmp_path, monkeypatch)
    monkeypatch.setattr(pipeline, "DEMO_DIR", tmp_path / "saved")
    (tmp_path / "saved").mkdir()
    real = pipeline.run(ROBERT_PLAN, ROBERT_Q, engine=fake_engine())
    _leaky(real)
    real["_analysis"] = {"after": {"metrics": {"max_drawdown": -0.345}, "esg_flags": set(), "amount": 600000,
                                   "lookthrough": {"stocks": {"NVDA": {"direct": 0.4, "via": [], "total": 0.4},
                                                              "RY.TO": {"direct": 0.0, "via": [{"etf": "XIU.TO", "weight": 0.02}], "total": 0.02}}}},
                         "today": None}
    monkeypatch.setattr(pipeline, "run", lambda plan, q, *a, **k: dict(real, question=q))
    monkeypatch.setattr(pipeline, "time_machine", lambda r, as_of, open=False: {"months": []}, raising=False)
    before = json.dumps(pipeline.jsonable(real), sort_keys=True)
    out = record_demo.record(record_demo.plan_runs(["robert"], []))
    saved = json.loads(Path(out[0]["saved"]).read_text())
    assert '"via"' not in json.dumps(saved) and _no_leaks(saved["result"]) == [] and _no_leaks(saved["analysis"]) == []
    assert list(saved["result"]["lookthrough"]["after"]["stocks"]) == ["NVDA"] and saved["result"]["trace"][0]["rows"] is None
    assert list(saved["analysis"]["after"]["lookthrough"]["stocks"]) == ["NVDA"] and saved["analysis"]["after"]["metrics"]
    assert json.dumps(pipeline.jsonable(real), sort_keys=True) == before           # the run itself was not changed


def test_the_plan_reads_investors_through_pipeline_load_pilots_when_it_exists(tmp_path, monkeypatch):
    _personas(tmp_path, monkeypatch)
    asked = []

    def load_pilots(path=None):
        asked.append(path)
        return {"robert": {"name": "Robert", "amount": 1, "profile": {"goal": "growth"}, "portfolio": {"XIU.TO": 1.0},
                           "question": "from the loader"}}

    monkeypatch.setattr(pipeline, "load_pilots", load_pilots, raising=False)
    plan = record_demo.plan_runs(["robert"], ["tariffs"])
    assert asked and [p["question"] for p in plan] == ["from the loader", "tariffs question"]
    assert plan[0]["flight_plan"]["amount"] == 1 and plan[0]["own"] and not plan[1]["own"]


def test_building_never_changes_the_web_folder_or_the_saved_runs(tmp_path, monkeypatch):
    web = _tiny_web(tmp_path, monkeypatch)
    _, path = _real_run(monkeypatch, tmp_path)
    snap = lambda root: {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}  # noqa: E731
    web_before, runs_before = snap(web), snap(path.parent)
    record_demo.build_static(tmp_path / "site")
    assert snap(web) == web_before and snap(path.parent) == runs_before


def test_the_real_web_folder_builds_into_a_static_site(tmp_path, monkeypatch):
    _real_run(monkeypatch, tmp_path)                                        # the real server.WEB_DIR is used
    out = record_demo.build_static(tmp_path / "site")
    page = (out / "index.html").read_text()
    assert page.count('<meta name="epicentre-mode" content="static">') == 1 and page.index("epicentre-mode") < page.index("</head>")
    names = {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}
    assert {"index.html", "app.js", "lib.js", "styles.css", "runs/index.json", "runs/default.json"} <= names
    assert not [n for n in names if "fake" in n.lower() or n.endswith(".csv") or n.endswith("story-data.js") or "/." in "/" + n]
    assert any(n.startswith("vendor/") for n in names)


def test_the_script_runs_from_any_folder(tmp_path):
    import subprocess
    done = subprocess.run([sys.executable, str(Path("scripts/record_demo.py").resolve()), "--dry-run", "--pilots", "robert",
                           "--storms", "tariffs"], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0 and len(done.stdout.strip().splitlines()) == 2 and "tariff" in done.stdout.lower(), done.stderr


def test_a_folder_inside_the_repository_is_fine_but_the_repository_itself_is_not(tmp_path, monkeypatch):
    _tiny_web(tmp_path, monkeypatch)
    _real_run(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(record_demo, "ROOT", repo)
    assert record_demo.build_static(repo / "site") == repo / "site" and (repo / "site" / "index.html").exists()
    for bad in (repo, tmp_path):
        with pytest.raises(record_demo.StaticBuildError, match="repository|source"):
            record_demo.build_static(bad)


def test_a_nested_result_keeps_no_private_keys(tmp_path, monkeypatch):
    def mutate(r):
        r["fallback_result"] = {"portfolio": {"XIU.TO": 0.6, "XBB.TO": 0.4}, "verdict": "Compatible",
                                "_analysis": {"after": {"market": {"XIU.TO": _series()}}}}

    _tiny_web(tmp_path, monkeypatch)
    _real_run(monkeypatch, tmp_path, mutate=mutate)
    out = record_demo.build_static(tmp_path / "site")
    result = json.loads((out / "runs/default.json").read_text())
    assert result["fallback_result"] == {"portfolio": {"XIU.TO": 0.6, "XBB.TO": 0.4}, "verdict": "Compatible"}


def test_record_runs_identical_inputs_once(tmp_path, monkeypatch):
    from fake_engine import ROBERT_PLAN, ROBERT_Q, fake_engine
    _personas(tmp_path, monkeypatch)
    path = tmp_path / "personas.json"
    data = json.loads(path.read_text())
    data["storm_cards"]["chips"]["question"] = data["pilots"]["robert"]["question"]      # Amira's real case: own question = a card
    path.write_text(json.dumps(data))
    monkeypatch.setattr(pipeline, "DEMO_DIR", tmp_path / "saved")
    real = pipeline.run(ROBERT_PLAN, ROBERT_Q, engine=fake_engine())
    asked = []
    monkeypatch.setattr(pipeline, "run", lambda plan, q, *a, **k: asked.append(q) or dict(real, question=q))
    monkeypatch.setattr(pipeline, "time_machine", lambda r, as_of, open=False: {"months": []}, raising=False)
    out = record_demo.record(record_demo.plan_runs(["robert"], ["tariffs", "chips"]))
    assert len(out) == 3 and len(asked) == 2 and out[2]["saved"] == out[0]["saved"] and out[2]["question"] == out[0]["question"]
    assert len(list((tmp_path / "saved").glob("[0-9a-f]" * 16 + ".json"))) == 2

# ---- Task 15 fix round 1 (ledger 29): the public series are weekly and rounded, single-line sides are refused ----
def _daily_result(n=1250, w=0.4, amount=100000, today_mix=None, seed=7):
    """A Result-like dict with a long DAILY series built the way tools/portfolio.py does (constant weights, rebalanced every
    day): today = XIU.TO/XBB.TO/GLD, after = (1 - w) of today plus w in NVDA. Returns (result, the true daily returns of NVDA)."""
    import pandas as pd
    rng = np.random.default_rng(seed)
    rets = {"NVDA": rng.normal(0.0012, 0.03, n - 1), "XIU.TO": rng.normal(0.0004, 0.008, n - 1),
            "XBB.TO": rng.normal(0.0001, 0.004, n - 1), "GLD": rng.normal(0.0003, 0.009, n - 1)}
    today = today_mix or {"XIU.TO": 0.5, "XBB.TO": 0.3, "GLD": 0.2}
    after = {**{t: (1 - w) * x for t, x in today.items()}, "NVDA": w}
    dates = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2021-11-12", periods=n)]

    def level(mix):
        return 100 * np.concatenate([[1.0], np.cumprod(1 + sum(x * rets[t] for t, x in mix.items()))])

    lt, la = level(today), level(after)
    dd = la / np.maximum.accumulate(la) - 1
    trough = int(np.argmin(dd))
    peak = int(np.argmax(la[:trough + 1]))
    below = np.where(dd < -0.15)[0]
    steps = [0.0, 0.1, 0.2, 0.3, 0.4]
    paths = [[round(amount * v / 100, 2) for v in level({**{t: (1 - s) * x for t, x in today.items()}, "NVDA": s})] for s in steps]
    r = {"amount": amount, "portfolio": after, "baseline": {"portfolio": today},
         "series": {"dates": dates, "today": lt.tolist(), "after": la.tolist(), "aligned": None},
         "breaches": [{"peak_date": dates[peak], "trough_date": dates[trough], "recovery_date": None, "depth": float(dd[trough]),
                       "below_floor": [[dates[int(below[0])], dates[int(below[-1])]]]}],
         "tipping_point": {"ticker": "NVDA", "paths": {"weights": steps, "values": paths}},
         "figures": {"flight_paths": {"data": [
             {"name": "Today", "x": dates, "y": [amount * v / 100 for v in lt]},
             {"name": "After the move", "x": dates, "y": [amount * v / 100 for v in la]},
             {"name": "Your floor", "x": [dates[0], dates[-1]], "y": [-15000.0, -15000.0]}], "layout": {}}}}
    return r, rets["NVDA"]


def _probe(r):
    """The reviewer's isolation probe: from the published today and after paths, the returns of the added line
    X = (r_after - (1 - w) r_today) / w between consecutive published points. Returns [(first date, last date, estimate)]."""
    s, w = r["series"], r["portfolio"]["NVDA"]
    t, a, d = s["today"], s["after"], s["dates"]
    return [(d[i], d[i + 1], ((a[i + 1] / a[i] - 1) - (1 - w) * (t[i + 1] / t[i] - 1)) / w) for i in range(len(d) - 1)]


def test_the_public_series_are_weekly_with_the_exact_trough_breach_and_end_days():
    r, _ = _daily_result()
    pub = record_demo.public_result(r)
    dates, full = pub["series"]["dates"], r["series"]["dates"]
    assert len(full) == 1250 and len(dates) <= 1250 // 5 + 12 and dates == sorted(set(dates))
    assert set(full[::5]) <= set(dates) and full[-1] in dates                       # every 5th trading day, and the end day
    b = r["breaches"][0]
    assert {b["peak_date"], b["trough_date"], *b["below_floor"][0]} <= set(dates)   # the exact trough and breach days
    for key in ("today", "after"):                                                  # each path's own worst-drop days
        v = np.array(r["series"][key])
        trough = int(np.argmin(v / np.maximum.accumulate(v) - 1))
        assert full[trough] in dates and full[int(np.argmax(v[:trough + 1]))] in dates
        assert len(pub["series"][key]) == len(dates)
    paths = pub["tipping_point"]["paths"]
    assert paths["weights"] == r["tipping_point"]["paths"]["weights"] and all(len(row) == len(dates) for row in paths["values"])
    assert pub["breaches"] == r["breaches"] and pub["portfolio"] == r["portfolio"]  # quoted rows are not touched


def test_the_kept_days_are_the_week_grid_the_end_the_named_days_and_every_paths_worst_drop():
    dates = [f"2022-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(137)]             # a made-up calendar of 137 days
    flat = [100.0 + i for i in range(137)]
    dip = [100.0 + i if i != 61 else 40.0 for i in range(137)]                             # a lone drop on day 61
    assert record_demo._keep(dates, [], set()) == sorted({*range(0, 137, 5), 136})        # the grid and the end day, nothing else
    assert record_demo._keep(dates, [flat], {dates[12]}) == sorted({*range(0, 137, 5), 136, 12})
    assert {60, 61} <= set(record_demo._keep(dates, [dip], set()))                         # the peak (day 60) and the trough
    assert 2 in record_demo._keep(dates, [[0.0, -0.1, -0.3, -0.2] + [0.0] * 133], set())      # a drawdown path: its lowest point


def test_the_dollar_paths_of_the_size_slider_keep_their_own_worst_drop_days():
    dates = [f"2022-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(137)]
    up = [100.0 + i for i in range(137)]
    r = {"amount": 100000, "portfolio": {"A": 0.6, "B": 0.4}, "baseline": {"portfolio": {"A": 0.5, "B": 0.5}},
         "series": {"dates": dates, "today": up, "after": up, "aligned": None},
         "tipping_point": {"paths": {"weights": [0.1, 0.2], "values": [[1000.0 * v for v in up],
                                                                       [1000.0 * (v if i != 53 else 40.0) for i, v in enumerate(up)]]}}}
    pub = record_demo.public_result(r)
    assert dates[53] in pub["series"]["dates"] and dates[52] in pub["series"]["dates"]       # the second path's peak and trough
    rows = pub["tipping_point"]["paths"]["values"]
    assert len(rows[0]) == len(rows[1]) == len(pub["series"]["dates"]) and min(rows[1]) == 40000


def test_a_dated_group_with_timestamps_is_weekly_too():
    r, _ = _daily_result()
    v = np.array(r["series"]["after"])
    stamped = [d + "T00:00:00" for d in r["series"]["dates"]]                        # a pandas Timestamp written out by plotly
    group = {"dates": stamped, "values": (v / np.maximum.accumulate(v) - 1).tolist()}
    r["metrics"] = {"after": {"drawdown": group}}
    assert record_demo.find_leaks(group)                                              # a daily list of timestamps is a leak
    pub = record_demo.public_result(r)["metrics"]["after"]["drawdown"]
    assert len(pub["dates"]) == len(pub["values"]) <= 1250 // 5 + 12 and pub["dates"][-1].endswith("T00:00:00")
    assert r["breaches"][0]["trough_date"] + "T00:00:00" in pub["dates"]              # the named days are found under their times
    assert record_demo.find_leaks(pub) == []


def test_a_dollar_path_of_another_length_is_thinned_when_the_series_is_daily():
    r, _ = _daily_result()
    r["tipping_point"]["paths"]["values"].append(r["tipping_point"]["paths"]["values"][0][1:])        # one day shorter
    once = record_demo.public_result(r)
    rows = once["tipping_point"]["paths"]["values"]
    assert len(rows[0]) == len(rows[1]) and len(rows[-1]) <= 1249 // 5 + 12
    assert record_demo.public_result(once) == once                                    # the thinned paths are not thinned again
    short = [100000.0 + 1000 * i for i in range(12)]                                  # fewer than 20 points is not a daily path
    out = record_demo.public_result({**r, "tipping_point": {"paths": {"weights": [0.1], "values": [short]}}})
    assert out["tipping_point"]["paths"]["values"] == [short]


def _daily(r):
    """Put a long daily history (series, breaches, size paths, charts) on a fake-engine run."""
    long, _ = _daily_result(amount=r["amount"] or 100000)
    r.update(series=long["series"], breaches=long["breaches"], figures=long["figures"],
             tipping_point={**(r.get("tipping_point") or {}), "paths": long["tipping_point"]["paths"]})


def test_the_build_thins_a_daily_run_a_saver_left_uncut(tmp_path, monkeypatch):
    _tiny_web(tmp_path, monkeypatch)
    _, path = _real_run(monkeypatch, tmp_path, mutate=_daily)
    assert len(json.loads(path.read_text())["result"]["series"]["dates"]) == 1250          # the saved file is daily
    out = record_demo.build_static(tmp_path / "site")
    built = json.loads((out / "runs/default.json").read_text())
    assert len(built["series"]["dates"]) <= 1250 // 5 + 12 and record_demo.find_leaks(built) == []
    assert len(built["tipping_point"]["paths"]["values"][0]) == len(built["series"]["dates"])
    assert "figures" in json.loads(path.read_text())["result"] and "figures" not in built      # the saver kept them, the build drops them


def test_record_saves_weekly_series_so_the_committed_files_are_already_public(tmp_path, monkeypatch):
    from fake_engine import ROBERT_PLAN, ROBERT_Q, fake_engine
    _personas(tmp_path, monkeypatch)
    monkeypatch.setattr(pipeline, "DEMO_DIR", tmp_path / "saved")
    real = pipeline.run(ROBERT_PLAN, ROBERT_Q, engine=fake_engine())
    _daily(real)
    monkeypatch.setattr(pipeline, "run", lambda plan, q, *a, **k: dict(real, question=q))
    out = record_demo.record(record_demo.plan_runs(["robert"], []))
    saved = json.loads(Path(out[0]["saved"]).read_text())["result"]
    assert len(saved["series"]["dates"]) <= 1250 // 5 + 12 and record_demo.find_leaks(saved) == []
    assert "figures" not in saved and "figures" in real                                      # the saved file has no charts
    assert len(real["series"]["dates"]) == 1250                                              # the live Result is not changed


def test_the_public_series_are_rounded_to_a_hundred_dollars():
    r, _ = _daily_result(amount=100000)
    pub = record_demo.public_result(r)
    index = {d: (t, a) for d, t, a in zip(pub["series"]["dates"], pub["series"]["today"], pub["series"]["after"])}
    for d, (t, a) in index.items():                                                 # the page shows amount x index / 100
        assert abs(100000 * t / 100 / 100 - round(100000 * t / 100 / 100)) < 1e-6
        i = r["series"]["dates"].index(d)
        assert abs(100000 * (a - r["series"]["after"][i]) / 100) <= 50 + 1e-6       # within half of $100
    assert all(abs(v / 100 - round(v / 100)) < 1e-9 for row in pub["tipping_point"]["paths"]["values"] for v in row)
    assert "figures" not in pub                                                      # the charts' traces carry daily paths: dropped


def test_drawdown_series_are_rounded_to_a_tenth_of_a_point():
    r, _ = _daily_result()
    v = np.array(r["series"]["after"])
    r["metrics"] = {"after": {"drawdown": {"dates": list(r["series"]["dates"]), "values": (v / np.maximum.accumulate(v) - 1).tolist()}}}
    pub = record_demo.public_result(r)["metrics"]["after"]["drawdown"]
    assert len(pub["dates"]) == len(pub["values"]) <= 1250 // 5 + 12
    assert all(abs(x * 1000 - round(x * 1000)) < 1e-9 and -1 <= x <= 0 for x in pub["values"])


def test_the_cut_is_idempotent_and_changes_nothing_passed_in():
    r, _ = _daily_result()
    before = json.dumps(r, sort_keys=True)
    once = record_demo.public_result(r)
    assert json.dumps(r, sort_keys=True) == before
    assert record_demo.public_result(once) == once
    assert once["series"]["today"] is not r["series"]["today"]


def test_the_isolation_probe_cannot_recover_a_daily_asset_path():
    r, nvda = _daily_result(amount=100000)
    daily = _probe(r)
    assert len(daily) == 1249 and max(abs(e - x) for (_, _, e), x in zip(daily, nvda)) < 1e-6         # the probe works on a daily path
    pub = record_demo.public_result(r)
    found = _probe(pub)
    assert len(found) <= 1250 // 5 + 12                                       # at most a weekly path of the added line, not a daily one
    full = r["series"]["dates"]
    gaps = [full.index(b) - full.index(a) for a, b, _ in found]
    assert sum(g == 1 for g in gaps) <= 12 and sorted(gaps)[len(gaps) // 2] == 5       # published points are a week apart
    errors = []
    for (a, b, est) in found:                                                   # the added line's true return over each published week
        i, j = full.index(a), full.index(b)
        errors.append(abs(est - (np.prod(1 + nvda[i:j]) - 1)))
    assert float(np.median(errors)) > 1e-4 and max(errors) > 1e-3             # rounded and compounded: no exact recovery either


@pytest.mark.parametrize("side,mix", [
    ("today", {"NVDA": 1.0}), ("today", {"NVDA": 1.0, "XIU.TO": 0.0}), ("today", {"NVDA": 0.996, "XIU.TO": 0.004}),
    ("after", {"NVDA": 1.0}), ("after", {"NVDA": 0.995, "XBB.TO": 0.005}), ("after", {}),
])
def test_a_side_with_one_line_is_refused(side, mix):
    r, _ = _daily_result()
    if side == "today":
        r["baseline"]["portfolio"] = mix
    else:
        r["portfolio"] = mix
    with pytest.raises(record_demo.NotPublic, match="one line|no line"):
        record_demo.public_result(r)


def test_two_real_lines_are_not_a_single_asset_path():
    r, _ = _daily_result()
    r["baseline"]["portfolio"] = {"NVDA": 0.994, "XIU.TO": 0.006}                       # below 99.5 %: still a mix
    r["portfolio"] = {"NVDA": 0.5, "XIU.TO": 0.5}
    assert record_demo.public_result(r)["series"]["dates"]
    no_series = {"portfolio": {"XIU.TO": 0.6, "XBB.TO": 0.4}, "verdict": "Compatible"}   # a real mix with no series passes as it is
    assert record_demo.public_result(no_series) == no_series


def test_a_nested_result_with_a_single_line_and_a_series_is_refused_too():
    r, _ = _daily_result()
    nested, _ = _daily_result(seed=8)
    nested["portfolio"] = {"NVDA": 1.0}
    r["fallback_result"] = nested
    with pytest.raises(record_demo.NotPublic, match="one line"):
        record_demo.public_result(r)


def test_the_build_refuses_a_single_line_run_in_plain_words(tmp_path, monkeypatch):
    _tiny_web(tmp_path, monkeypatch)
    _real_run(monkeypatch, tmp_path, mutate=lambda r: r.update(portfolio={"NVDA": 1.0}))
    with pytest.raises(record_demo.StaticBuildError, match="one line"):
        record_demo.build_static(tmp_path / "site")
    assert not (tmp_path / "site").exists()


def test_record_reports_a_single_line_run_and_does_not_save_it(tmp_path, monkeypatch):
    from fake_engine import ROBERT_PLAN, ROBERT_Q, fake_engine
    _personas(tmp_path, monkeypatch)
    monkeypatch.setattr(pipeline, "DEMO_DIR", tmp_path / "saved")
    real = pipeline.run(ROBERT_PLAN, ROBERT_Q, engine=fake_engine())
    monkeypatch.setattr(pipeline, "run", lambda plan, q, *a, **k: dict(real, question=q, portfolio={"NVDA": 1.0}))
    out = record_demo.record(record_demo.plan_runs(["robert"], []))
    assert out[0]["saved"] is None and "one line" in out[0]["why"] and not list((tmp_path / "saved").glob("*.json"))


# one canary per credential pattern (ledger 29: the scan is case-insensitive and also knows the Bedrock key, GitHub and project names)
CANARIES = {
    "access key id": "const k = 'AKIAABCDEFGHIJKLMNOP';",
    "temporary key id": "const k = 'ASIAABCDEFGHIJKLMNOP';",
    "key id glued to a word": "const k = 'xAKIAABCDEFGHIJKLMNOP';",
    "secret key, upper case": "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    "secret key, lower case": "aws_secret_access_key = 'x'",
    "secret key, mixed case": "Aws_Secret_Access_Key: x",
    "session token": "AWS_SESSION_TOKEN=IQoJb3JpZ2luX2VjEXAMPLE",
    "bedrock bearer token": "AWS_BEARER_TOKEN_BEDROCK=abc",
    "bedrock api key": "const key = 'ABSKQmVkcm9ja0FQSUtleS1leGFtcGxlMDEyMzQ1Njc4OQ==';",
    "github token": "const t = 'ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8';",
    "github fine-grained token": "const t = 'github_pat_" + "11ABCDEFG0abcdefghijkl_0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ';",
    "github fine-grained token, lower case": "TOKEN=GITHUB_PAT_" + "11abcdefg0abcdefghijkl_0123456789abcdefghijklmnopqrstuv",
    "signed url token": "https://x.example/?X-Amz-Security-Token=IQoJb3JpZ2luX2VjEXAMPLE",
    "signed url token, lower case": "x-amz-security-token: abc",
    "server password": "EPICENTRE_PASSWORD=hunter2",
    "server password, lower case": "epicentre_password = 'x'",
    "private key": "-----BEGIN RSA PRIVATE KEY-----",
}


@pytest.mark.parametrize("what", sorted(CANARIES))
def test_each_credential_pattern_has_a_canary_the_build_refuses(tmp_path, monkeypatch, what):
    web = _tiny_web(tmp_path, monkeypatch)
    _real_run(monkeypatch, tmp_path)
    (web / "app.js").write_text(CANARIES[what])
    with pytest.raises(record_demo.StaticBuildError, match="credential"):
        record_demo.build_static(tmp_path / "site")
    assert not (tmp_path / "site").exists() and not list(tmp_path.glob("site*"))


def test_ordinary_words_about_keys_and_passwords_are_not_credentials(tmp_path, monkeypatch):
    web = _tiny_web(tmp_path, monkeypatch)
    _real_run(monkeypatch, tmp_path)
    (web / "app.js").write_text("// Asia and the AWS key idea; a password field; ghp is not a token; github_pat is a name; absk; the Amazon region\n"
                                "const label = 'Access key: not stored'; const f = 'asia pacific';")
    assert record_demo.build_static(tmp_path / "site").is_dir()


def _edit_saved(path, edit):
    saved = json.loads(path.read_text())
    edit(saved)
    path.write_text(json.dumps(saved))


def _set_sources(obj, text):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "source" and isinstance(value, str):
                obj[key] = text
            else:
                _set_sources(value, text)
    elif isinstance(obj, list):
        for value in obj:
            _set_sources(value, text)


def test_the_real_gate_is_a_pure_function_of_the_run_file(tmp_path, monkeypatch):
    _tiny_web(tmp_path, monkeypatch)
    _real_run(monkeypatch, tmp_path)
    boom = lambda *a, **k: pytest.fail("the build must not look at the data folder of the machine")      # noqa: E731
    monkeypatch.setattr(pipeline, "_data_label", boom)
    monkeypatch.setattr(pipeline, "_data_dir", boom)
    monkeypatch.setattr(pipeline, "REAL_DATA_DIR", tmp_path / "no_such_pack")
    assert record_demo.build_static(tmp_path / "site").is_dir()            # a fresh clone with no data/starter builds from the files


@pytest.mark.parametrize("edit,says,never", [
    (lambda s: s.update(data="FAKE"), "labelled FAKE", None),
    (lambda s: s.update(data="UNKNOWN"), "labelled UNKNOWN", "sources say FAKE"),
    (lambda s: s.pop("data"), "no data label", "sources say FAKE"),
    (lambda s: s.update(data="real"), "not REAL", "sources say FAKE"),
    (lambda s: _set_sources(s["result"], ""), "names no source", "FAKE"),
    (lambda s: _set_sources(s["result"], "   "), "names no source", "FAKE"),
    (lambda s: _set_sources(s["result"], "FAKE: tests/fake_engine.py"), "names fake data", None),
    (lambda s: _set_sources(s["result"], "data/fake/prices_daily.csv"), "names fake data", None),
    (lambda s: _set_sources(s["result"], "Fake sample prices"), "names fake data", None),
])
def test_the_real_gate_says_what_failed(tmp_path, monkeypatch, edit, says, never):
    _tiny_web(tmp_path, monkeypatch)
    _, path = _real_run(monkeypatch, tmp_path)
    _edit_saved(path, edit)
    with pytest.raises(record_demo.StaticBuildError) as caught:
        record_demo.build_static(tmp_path / "site")
    text = str(caught.value)
    assert path.name in text and says in text and (never is None or never not in text)
    assert not (tmp_path / "site").exists()


def test_one_fake_source_among_real_ones_is_refused(tmp_path, monkeypatch):
    _tiny_web(tmp_path, monkeypatch)
    _, path = _real_run(monkeypatch, tmp_path)
    _edit_saved(path, lambda s: s["result"]["trace"][0].update(source="FAKE: one step on the sample data"))
    with pytest.raises(record_demo.StaticBuildError, match="names fake data"):
        record_demo.build_static(tmp_path / "site")


# ---- a check that names a company inside the investor's fund (D Task 3's rule, applied again here as a gate of its own) ----
def test_a_check_that_names_a_company_inside_a_fund_is_cut_to_another_company():
    ref = json.loads(Path("data/fake/result.json").read_text())             # baseline.checks[2] holds RY.TO, a company inside XIU.TO
    assert ref["baseline"]["checks"][2]["holding"] == "RY.TO" and "XIU.TO" in ref["baseline"]["portfolio"]
    pub = record_demo.public_result(ref)
    cut = pub["baseline"]["checks"][2]
    assert cut["holding"] is None and "RY.TO" not in cut["reason"] and "another company" in cut["reason"]
    assert pub["checks"][2]["holding"] == "NVDA" and "NVDA" in pub["checks"][2]["reason"]       # a line of the portfolio stays named
    assert "RY.TO" not in json.dumps(pub["baseline"]["checks"])
    assert ref["baseline"]["checks"][2]["holding"] == "RY.TO"                                    # nothing passed in is changed
    saver = pipeline._publishable(ref)                                                          # the same rule as D Task 3's save_run
    assert pub["checks"] == saver["checks"] and pub["baseline"]["checks"] == saver["baseline"]["checks"]


def test_the_illustration_mix_counts_as_the_investors_lines_for_the_checks():
    r = {"portfolio": {"NVDA": 0.5, "XIU.TO": 0.5}, "aligned": {"weights": {"SPY": 0.6, "XBB.TO": 0.4}},
         "checks": [{"rule": "single_stock", "holding": "SPY", "reason": "SPY is 60 %."},
                    {"rule": "single_stock", "holding": "RY.TO", "reason": "RY.TO is 3 %."}]}
    cut = record_demo.public_result(r)["checks"]
    assert cut[0]["holding"] == "SPY" and cut[1]["holding"] is None and cut[1]["reason"] == "another company is 3 %."


def test_the_build_cuts_a_company_a_saver_left_in_a_check(tmp_path, monkeypatch):
    _tiny_web(tmp_path, monkeypatch)
    _, path = _real_run(monkeypatch, tmp_path)

    def put_back(saved):                                                    # a run saved by an older or other saver
        for checks in (saved["result"]["checks"], saved["result"]["baseline"]["checks"]):
            checks[2].update(holding="RY.TO", reason="The largest single company, RY.TO, is 3.4 % of the money.")

    _edit_saved(path, put_back)
    out = record_demo.build_static(tmp_path / "site")
    built = json.loads((out / "runs/default.json").read_text())
    assert "RY.TO" not in json.dumps(built["checks"]) and "RY.TO" not in json.dumps(built["baseline"]["checks"])
    assert built["checks"][2]["holding"] is None and "another company" in built["checks"][2]["reason"]


# ---- Task 15 fix round 2 (ledger 30): the public cut drops `figures`; a typed array (bdata) is never published ----
def _plotly_figure(n=400):
    """What the pipeline stores in `figures`: json.loads(fig.to_json()) of a chart built from numpy. Plotly writes numpy
    arrays as typed arrays ({"dtype", "bdata"}); here a daily dollar path."""
    import plotly.graph_objects as go
    r, _ = _daily_result(n=n)
    fig = go.Figure(go.Scatter(x=r["series"]["dates"], y=np.array(r["series"]["after"]) * 1000, name="After the move"))
    return json.loads(fig.to_json())


def test_plotly_writes_numpy_as_typed_arrays_that_a_list_cut_cannot_read():
    blob = _plotly_figure()["data"][0]["y"]
    assert set(blob) >= {"dtype", "bdata"} and len(blob["bdata"]) > 400                  # the whole daily path, in base64


def test_the_public_cut_drops_figures_and_no_typed_array_is_left():
    r, _ = _daily_result()
    r["figures"] = {"flight_paths": _plotly_figure()}
    assert "bdata" in json.dumps(r) and record_demo.find_leaks(json.loads(json.dumps(r)))
    pub = record_demo.public_result(r)
    assert "figures" not in pub and "bdata" not in json.dumps(pub)
    assert record_demo.find_leaks(json.loads(json.dumps(pub))) == []
    nested, _ = _daily_result(seed=8)
    nested["figures"] = {"fall": _plotly_figure()}
    cut = record_demo.public_result({**r, "fallback_result": nested})
    assert "figures" not in cut["fallback_result"] and "bdata" not in json.dumps(cut)
    assert "figures" in r and "figures" in nested                                       # nothing passed in is changed


def test_a_run_with_a_numpy_chart_is_built_without_figures_or_base64(tmp_path, monkeypatch):
    _tiny_web(tmp_path, monkeypatch)
    _, path = _real_run(monkeypatch, tmp_path, mutate=lambda r: r.update(figures={"flight_paths": _plotly_figure()}))
    assert "bdata" in path.read_text()                                                  # a saver left the typed array in the file
    out = record_demo.build_static(tmp_path / "site")
    assert not [f.name for f in (out / "runs").glob("*.json") if "bdata" in f.read_text() or '"figures"' in f.read_text()]


@pytest.mark.parametrize("where", ["trace", "kpis", "facts"])
def test_a_typed_array_planted_elsewhere_fails_the_build(tmp_path, monkeypatch, where):
    blob = _plotly_figure()["data"][0]["y"]
    plant = {"trace": lambda r: r["trace"][0].update(outputs={"path": blob}), "kpis": lambda r: r["kpis"].update(path=blob),
             "facts": lambda r: r["facts"].update(extra={"label": "x", "value": blob})}[where]
    _tiny_web(tmp_path, monkeypatch)
    _real_run(monkeypatch, tmp_path, mutate=plant)
    with pytest.raises(record_demo.StaticBuildError, match="typed array"):
        record_demo.build_static(tmp_path / "site")
    assert not (tmp_path / "site").exists()


def test_find_leaks_refuses_any_typed_array_anywhere():
    blob = {"dtype": "f8", "bdata": "AAAAAAAA8D8="}
    for obj in ({"y": blob}, {"a": [{"b": {"c": blob}}]}, {"bdata": "AAAA"}, [blob]):
        assert any("typed array" in leak for leak in record_demo.find_leaks(obj)), obj
    assert record_demo.find_leaks({"dtype": "f8", "values": [1.0]}) == []


@pytest.mark.parametrize("series", [None, {}, {"dates": []}, {"dates": ["2026-11-12"]}, {"dates": np.array(["2021-11-12", "2021-11-15"])}, "x"])
def test_a_one_line_side_is_refused_whatever_the_series_looks_like(series):
    r = {"portfolio": {"NVDA": 1.0}, "baseline": {"portfolio": {"NVDA": 0.5, "XIU.TO": 0.5}}, "series": series}
    with pytest.raises(record_demo.NotPublic, match="one line"):
        record_demo.public_result(r)
    del r["series"]                                                                     # and with no series key at all
    with pytest.raises(record_demo.NotPublic, match="one line"):
        record_demo.public_result(r)


@pytest.mark.parametrize("result", [{}, {"portfolio": None}, {"portfolio": {}}, {"portfolio": "x"}, {"portfolio": {"A": 0}}])
def test_a_result_with_no_readable_mix_is_refused_not_skipped(result):
    with pytest.raises(record_demo.NotPublic, match="no line"):
        record_demo.public_result(result)


# ---- Task 14: the container is non-root and secret-free; the runbook carries the ledger section 19 ruling ----
def test_container_is_non_root_and_secret_free():
    df = Path("Dockerfile").read_text()
    assert df.splitlines()[0] == "FROM python:3.12-slim" and "USER epicentre" in df
    assert 'CMD ["uvicorn", "server:app"' in df and "AWS_" not in df and "ARG" not in df
    ignored = Path(".dockerignore").read_text().split()
    assert {"data/starter", "data/etf_holdings.csv", ".env", ".aws", "credentials", ".git"} <= set(ignored)
    deploy = Path("docs/deploy.md").read_text()
    assert "0.0.0.0/0" in deploy and "never 0.0.0.0/0" in deploy and "runtime-policy.json" in deploy

def test_runbook_carries_the_cloudfront_ruling_and_the_evidence_pack():
    deploy = Path("docs/deploy.md").read_text()
    for needed in ("com.amazonaws.global.cloudfront.origin-facing", "EPICENTRE_PASSWORD", "/api/health",
                   "Authorization", "AmazonSSMManagedInstanceCore", "terminate-instances", "delete-distribution",
                   "price to be checked", "CloudWatch", "simulate-principal-policy"):
        assert needed in deploy, needed

def test_integration_first_paints_do_not_push_other_runs_out_of_the_store(client):
    """A replay keeps one run_id, so a public page load is one slot in the 50-run store, not a new one each time."""
    import shutil
    _, path = _record_robert()
    shutil.copy(path, pipeline.DEMO_DIR / "default.json")
    server.RUNS.put({"run_id": "someone-else"})
    ids = {client.get("/api/demo-run").json()["run_id"] for _ in range(60)}
    assert len(ids) == 1 and server.RUNS.get("someone-else") is not None and len(server.RUNS) == 2


def test_private_keys_never_reach_the_browser():
    assert "_analysis" not in json.loads(server.to_json({"_analysis": {}, "verdict": "Tension"}))


# ---- deploy hardening (ledger section 30, D Task 14 fix round 1): fail closed + the secret origin header ----

def test_deploy_mode_refuses_to_start_without_a_password(monkeypatch):
    """Ledger section 30 (a): EPICENTRE_REQUIRE_PASSWORD=1 makes an empty or unset password a start-up error."""
    assert server.REQUIRE_PASSWORD_ENV == "EPICENTRE_REQUIRE_PASSWORD"
    monkeypatch.setenv(server.REQUIRE_PASSWORD_ENV, "1")
    monkeypatch.delenv(server.PASSWORD_ENV, raising=False)
    for value in (None, ""):
        if value is None:
            monkeypatch.delenv(server.PASSWORD_ENV, raising=False)
        else:
            monkeypatch.setenv(server.PASSWORD_ENV, value)
        with pytest.raises(RuntimeError) as refused:
            server.create_app()
        message = str(refused.value)
        assert "EPICENTRE_PASSWORD" in message and "Traceback" not in message and message.endswith(".")
    monkeypatch.setenv(server.PASSWORD_ENV, "a real one")
    assert TestClient(server.create_app()).get("/api/health").status_code == 200       # with a password it starts


def test_without_the_deploy_flag_local_dev_starts_open_as_before(monkeypatch):
    for flag in (None, "", "0"):
        if flag is None:
            monkeypatch.delenv(server.REQUIRE_PASSWORD_ENV, raising=False)
        else:
            monkeypatch.setenv(server.REQUIRE_PASSWORD_ENV, flag)
        for password in (None, ""):
            if password is None:
                monkeypatch.delenv(server.PASSWORD_ENV, raising=False)
            else:
                monkeypatch.setenv(server.PASSWORD_ENV, password)
            client = TestClient(server.create_app())                    # no error, and still no gate
            assert client.get("/api/pilots").status_code != 401


ORIGIN_SECRET = "origin-secret-5f2c1e9a-TEST-ONLY"
ORIGIN_OK = {"X-Origin-Verify": ORIGIN_SECRET}
MSG_403 = "This server only answers requests that come through its public address."
ALL_ROUTES = [("GET", "/"), ("GET", "/api/pilots"), ("GET", "/api/wire"), ("GET", "/api/demo-run"),
              ("GET", "/api/no-such-route"), ("POST", "/api/run"), ("POST", "/api/recheck"),
              ("POST", "/api/recompute")]


@pytest.fixture()
def gated(api, monkeypatch):
    """The `api` client as deployed: the origin secret and a password both set."""
    monkeypatch.setenv(server.ORIGIN_SECRET_ENV, ORIGIN_SECRET)
    monkeypatch.setenv(server.PASSWORD_ENV, "pw")
    return api


def test_the_origin_check_is_off_unless_the_variable_exists(api, monkeypatch):
    """Ledger section 30 (b): local dev has no secret, so a stray X-Origin-Verify header means nothing."""
    assert server.ORIGIN_SECRET_ENV == "EPICENTRE_ORIGIN_SECRET"
    monkeypatch.delenv(server.ORIGIN_SECRET_ENV, raising=False)
    for headers in (None, {"X-Origin-Verify": "anything"}):
        assert api.get("/", headers=headers).status_code == 200
        assert api.get("/api/pilots", headers=headers).status_code in (200, 503)


@pytest.mark.parametrize("method, path", ALL_ROUTES)
def test_no_origin_header_is_403_on_every_route_before_anything_runs(gated, method, path):
    r = gated.request(method, path, json=BODY if method == "POST" else None, headers=basic("u", "pw"))
    assert error_of(r, 403) == MSG_403                       # even with the right password
    assert "www-authenticate" not in r.headers and r.headers["x-content-type-options"] == "nosniff"
    assert not gated.calls.run and not gated.calls.recheck


def test_a_wrong_origin_header_is_403(gated):
    wrong = [ORIGIN_SECRET + "x", ORIGIN_SECRET[:-1], ORIGIN_SECRET.upper(), "", "WRONG-ORIGIN-MARKER-0042",
             ORIGIN_SECRET.replace("5", "6"), b"\xff\xfe\x00"]
    for value in wrong:
        for path in ("/", "/api/pilots"):
            r = gated.get(path, headers={**basic("u", "pw"), "X-Origin-Verify": value})
            assert error_of(r, 403) == MSG_403, repr(value)
    assert not gated.calls.run


def test_the_right_header_and_the_password_open_everything(gated):
    both = {**basic("judge", "pw"), **ORIGIN_OK}
    assert gated.get("/", headers=both).status_code == 200
    assert gated.get("/api/pilots", headers=both).status_code in (200, 503)
    assert gated.get("/", headers={**basic("judge", "pw"), "x-origin-verify": ORIGIN_SECRET}).status_code == 200
    assert ndjson_with(gated, both)[-1]["type"] == "result"
    assert error_of(gated.get("/api/pilots", headers=ORIGIN_OK), 401) == MSG_401          # the header is not the password
    assert error_of(gated.get("/api/pilots", headers={**basic("u", "wrong"), **ORIGIN_OK}), 401) == MSG_401


def test_health_stays_open_without_the_header_or_the_password_and_only_that_exact_path(gated):
    for headers in (None, {"X-Origin-Verify": "wrong"}, ORIGIN_OK):
        r = gated.get("/api/health", headers=headers)
        assert r.status_code == 200 and set(r.json()) == {"data", "bedrock", "guardrail", "holdings", "deep"}
    for path in ("/api/health/", "/api/healthz", "/api/health/x", "/api//health"):    # the exemption is one exact path
        assert gated.get(path).status_code == 403, path


def test_an_empty_origin_secret_locks_the_door_instead_of_opening_it(api, monkeypatch):
    """A secret that exists but is empty is a deployment mistake: refuse everything but /api/health."""
    monkeypatch.setenv(server.ORIGIN_SECRET_ENV, "")
    for headers in (None, {"X-Origin-Verify": ""}, {"X-Origin-Verify": "x"}):
        assert error_of(api.get("/api/pilots", headers=headers), 403) == MSG_403
    assert api.get("/api/health").status_code == 200


def test_the_origin_header_is_compared_with_hmac_compare_digest(gated, monkeypatch):
    seen = []
    real = server.hmac.compare_digest

    def spy(a, b):
        seen.append((a, b))
        return real(a, b)

    monkeypatch.setattr(server.hmac, "compare_digest", spy)
    secret = ORIGIN_SECRET.encode()
    gated.get("/api/pilots", headers={**basic("u", "pw"), **ORIGIN_OK})
    gated.get("/api/pilots", headers={**basic("u", "pw"), "X-Origin-Verify": "nope"})
    assert any(pair == (secret, secret) for pair in seen)                    # bytes on both sides, never str
    assert any(set(pair) == {b"nope", secret} for pair in seen)


def test_the_origin_gate_comes_before_the_size_cap(gated):
    padded = {**BODY, "padding": "x" * 70_000}
    assert error_of(gated.post("/api/run", json=padded, headers=basic("u", "pw")), 403) == MSG_403
    assert gated.post("/api/run", json=padded, headers={**basic("u", "pw"), **ORIGIN_OK}).status_code == 413


def test_the_origin_secret_never_reaches_a_log_a_response_or_the_console(gated, caplog, capfd):
    import logging
    caplog.set_level(logging.DEBUG)
    marker = "WRONG-ORIGIN-MARKER-0042"
    responses = [
        gated.get("/api/pilots"),
        gated.get("/api/pilots", headers={**basic("u", "pw"), "X-Origin-Verify": marker}),
        gated.get("/api/pilots", headers=ORIGIN_OK),
        gated.get("/api/pilots", headers={**basic("u", "pw"), **ORIGIN_OK}),
        gated.post("/api/run", json=BODY, headers={"X-Origin-Verify": marker}),
        gated.post("/api/run", json=BODY, headers={**basic("u", "pw"), **ORIGIN_OK}),
    ]
    out, err = capfd.readouterr()
    for text in [caplog.text, out, err] + [r.text + str(dict(r.headers)) for r in responses]:
        assert ORIGIN_SECRET not in text and marker not in text


# ---- the runbook's hardening (ledger section 30): the commands, not only the words ----

DEPLOY_MD = Path("docs/deploy.md")


def _fenced_blocks(text: str) -> list[str]:
    """Every fenced block of the runbook, without the fence lines."""
    blocks, current = [], None
    for line in text.splitlines():
        if line.startswith("```"):
            if current is None:
                current = []
            else:
                blocks.append("\n".join(current))
                current = None
        elif current is not None:
            current.append(line)
    return blocks


def _logical_lines(block: str) -> list[str]:
    """The block with backslash continuations joined and spaces collapsed: a multi-line command is one line."""
    return [" ".join(line.split()) for line in block.replace("\\\n", " ").splitlines()]


def _block_with(text: str, needle: str) -> str:
    found = [b for b in _fenced_blocks(text) if needle in b]
    assert found, f"no fenced block contains {needle!r}"
    return found[0]


WORLD_TOKENS = ("0.0.0.0/0", "::/0", "--cidr", "CidrIp", "IpRanges")


def test_no_runbook_command_opens_the_world():
    """Nothing inbound is ever world-open. The one allowed 0.0.0.0/0 is the OUTBOUND rule on TCP 443 (ruling R20:
    no inbound 0.0.0.0/0, outbound TCP 443 only): exactly one logical line, an egress authorize for tcp 443."""
    text = DEPLOY_MD.read_text()
    hits = [line for block in _fenced_blocks(text) for line in _logical_lines(block)
            if any(token in line for token in WORLD_TOKENS)]
    assert len(hits) == 1, hits                                                          # only the outbound HTTPS rule names a CIDR
    rule = hits[0]
    assert rule.startswith("aws ec2 authorize-security-group-egress "), rule              # outbound, never ingress
    assert "IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges=[{CidrIp=0.0.0.0/0," in rule, rule
    assert "::/0" not in rule and "--cidr" not in rule and "ingress" not in rule, rule
    assert text.index("authorize-security-group-egress") < text.index("aws ec2 run-instances")   # narrowed before the instance exists


def test_runbook_starts_the_container_fail_closed_with_both_secrets_passed_by_name():
    block = _block_with(DEPLOY_MD.read_text(), "docker run -d --name epicentre")
    run = next(line for line in _logical_lines(block) if "docker run -d --name epicentre" in line)
    assert "-e EPICENTRE_REQUIRE_PASSWORD=1" in run                                   # ledger section 30 (a)
    for name in ("EPICENTRE_PASSWORD", "EPICENTRE_ORIGIN_SECRET"):
        assert re.search(rf"-e {name}(?![=\w])", run), name                            # the name only, never NAME=value
        assert re.search(rf"read -rs {name}\b", block), name                           # typed silently, never echoed
        assert f"export {name}" in block, name                                         # exported, so -e NAME can pass it
    # the guards are chained to docker run with &&, so a failed guard stops it even when the block is pasted whole
    guards = ['$' + '{EPICENTRE_PASSWORD:?type the password first}', '$' + '{EPICENTRE_ORIGIN_SECRET:?type the origin secret first}']
    start = block.index(f': "{guards[0]}"')
    chain = " ".join(block[start:block.index("docker run -d --name epicentre")].replace("\\\n", " ").split())
    assert chain == f': "{guards[0]}" && : "{guards[1]}" &&'
    assert block.index("docker build") < start                                         # the build is outside the chain



def test_the_redeploy_block_reads_the_secrets_from_the_root_only_file_and_starts_fail_closed():
    """Re-review r1 open item B: a redeploy (git pull + rebuild + guarded run) in a fresh root shell, the two secrets
    from /root/epicentre.env (written at the first start by the printf builtin under umask 077), never typed again."""
    text = DEPLOY_MD.read_text()
    first = _block_with(text, "read -rs EPICENTRE_PASSWORD")
    assert "(umask 077; printf 'EPICENTRE_PASSWORD=%s" in first and "> /root/epicentre.env)" in first
    assert "openssl rand" not in text.split("## 4. Install and run", 1)[1].split("\n## 5.", 1)[0]   # 3b made them once
    block = _block_with(text.split("**Redeploy**", 1)[1], "docker run -d --name epicentre")
    run = next(line for line in _logical_lines(block) if "docker run -d --name epicentre" in line)
    assert run.startswith("awk -F= 'length($2) { n++ } END { exit n != 2 }' /root/epicentre.env && docker run"), run
    assert "--env-file /root/epicentre.env" in run and "-e EPICENTRE_REQUIRE_PASSWORD=1" in run
    assert "-e EPICENTRE_PASSWORD" not in run and "-e EPICENTRE_ORIGIN_SECRET" not in run     # by the file, by name
    assert block.index("git pull --ff-only") < block.index("docker build") < block.index("docker run")
    assert "# 403" in block and "# 401" in block and "-K - http://127.0.0.1:8000/" in block

def test_no_runbook_line_puts_a_secret_on_a_command_line():
    text = DEPLOY_MD.read_text()
    for block in _fenced_blocks(text):
        for line in _logical_lines(block):
            # no NAME=value, ever. Three shapes are not a value: a printf format (`=%s`), a bare name before a closing
            # quote or the end of the line (the env-file key), and a sed capture group (`=\(`) that reads the file
            assert not re.search(r"EPICENTRE_(PASSWORD|ORIGIN_SECRET)=(?!%s|['\"]|\\\(|\s|$)", line), line
            assert not re.search(r"curl[^#]* (-u|--user) ", line), line                    # -u shows in the process list
            assert not re.search(r"curl[^#]*-H[^#]*X-Origin-Verify", line), line          # nor does -H with the secret
            assert "echo $EPICENTRE" not in line and 'echo "$EPICENTRE' not in line, line


def test_cloudfront_config_adds_the_secret_header_and_is_valid_json():
    block = _block_with(DEPLOY_MD.read_text(), '"CallerReference"')
    before, raw = block.split("<<JSON\n", 1)
    raw = raw.split("\nJSON", 1)[0]
    assert "$ORIGIN_SECRET" in raw                                                      # the variable, never a literal
    rendered = (raw.replace("$(date +%s)", "1").replace("$ORIGIN_DNS", "ec2-203-0-113-9.compute-1.amazonaws.com")
                .replace("$ORIGIN_SECRET", "S3CRET").replace("$CACHE_POLICY_ID", "cache-id")
                .replace("$ORIGIN_POLICY_ID", "origin-id"))
    assert "$" not in rendered                                                          # a new variable must be rendered here too
    body = json.loads(rendered)                                                         # the create-distribution-with-tags shape
    assert body["Tags"] == {"Items": [{"Key": "Project", "Value": "epicentre"}]}        # tagged from its first second (fix round 2)
    cfg = body["DistributionConfig"]
    origin = cfg["Origins"]["Items"][0]
    assert cfg["Origins"]["Quantity"] == 1 and len(cfg["Origins"]["Items"]) == 1
    assert origin["CustomHeaders"] == {"Quantity": 1, "Items": [{"HeaderName": "X-Origin-Verify", "HeaderValue": "S3CRET"}]}
    assert origin["CustomOriginConfig"]["OriginProtocolPolicy"] == "http-only" and origin["CustomOriginConfig"]["HTTPPort"] == 8000
    behavior = cfg["DefaultCacheBehavior"]
    assert behavior["ViewerProtocolPolicy"] == "redirect-to-https" and behavior["CachePolicyId"] == "cache-id"
    assert behavior["OriginRequestPolicyId"] == "origin-id"
    assert 'chmod 600 "$CF_JSON"' in before and "CF_JSON=~/.epicentre/cf.json" in before   # the file holds the secret: owner-only, outside the repo
    assert "~/.epicentre/secrets.env" in before                                         # the origin secret is read from the owner-only file


def test_the_policy_name_check_is_a_hard_gate_before_create_distribution():
    text = DEPLOY_MD.read_text()
    block = _block_with(text, "aws cloudfront create-distribution")
    lines = _logical_lines(block)
    create = next(line for line in lines if "aws cloudfront create-distribution" in line)
    for call in ("get-cache-policy", "get-origin-request-policy"):
        assert any(call in line for line in lines[:lines.index(create)]), call          # both lookups run first
    gate = '[ "$CACHE_NAME / $ORIGIN_NAME" = "Managed-CachingDisabled / Managed-AllViewer" ] && DIST_ID='
    assert create.startswith(gate)                                                      # create runs only if the gate passes
    assert '|| echo "GATE FAILED' in create                                             # and a failed gate says so
    assert block.index("unset DIST_ID") < block.index("create-distribution")            # no stale id can pass the next line
    assert block.index('rm -f "$CF_JSON"') < block.index("DIST_ID:?")                    # the secret file is gone at once
    assert "create-distribution-with-tags" in create and "--distribution-config-with-tags" in create   # tagged at creation
    assert text.index("aws cloudfront get-cache-policy") < text.index("aws cloudfront create-distribution")   # no earlier create


def _smoke_pairs(text: str) -> set:
    """(target, expected status) for every curl line that prints a status code and says what it expects."""
    pairs = set()
    for block in _fenced_blocks(text):
        for line in _logical_lines(block):
            if "%{http_code}" in line:
                expected = re.search(r"#\s*(\d{3})\b", line.split("%{http_code}", 1)[1])
                target = re.search(r"(127\.0\.0\.1:8000|\$CF_DOMAIN|\$ORIGIN_DNS)", line)
                if expected and target:
                    pairs.add((target.group(1), expected.group(1)))
    return pairs


def test_the_smoke_tests_expect_403_then_401_then_200():
    assert {("127.0.0.1:8000", "403"),     # straight to the instance, no header: the app refuses (gate 2)
            ("127.0.0.1:8000", "401"),     # straight to the instance, right header, no password (gate 3)
            ("$CF_DOMAIN", "401"),         # through CloudFront: it adds the header, the app asks for the password
            ("$CF_DOMAIN", "200"),         # through CloudFront with the password
            ("$ORIGIN_DNS", "000"),        # laptop straight to the instance: the security group drops it (gate 1)
            } <= _smoke_pairs(DEPLOY_MD.read_text())


def test_the_cost_headline_is_one_number_and_labelled():
    """Fix round 2: recomputed for the Sat 23:55 to Mon 13:59 run (38 h 4 min, 39 billed hours); the old 0.80 is gone."""
    text = DEPLOY_MD.read_text()
    assert set(re.findall(r"about (\d+\.\d+)", text)) == {"1.10"} and "about 1 USD" not in text
    assert "about 0.80" not in text and "28 hours at most" not in text
    label = "to be checked against the dated AWS price pages"
    for heading in ("## 1. Go / no-go", "## 9. Cost estimate"):
        section = " ".join(text.split(heading, 1)[1].split("\n## ", 1)[0].split())         # prose wraps: compare unwrapped
        assert "about 1.10" in section and label in section, heading
    # the rows add up to the headline, and the hours follow from the window the section states
    rows = [float(m) for m in re.findall(r"\| up to 39 h \| (\d\.\d\d) \|", text)]
    rows += [float(m) for m in re.findall(r"\| 39 h of a 730-hour month \| (\d\.\d\d) \|", text)]
    assert len(rows) == 3 and round(sum(rows), 2) == 1.10
    assert "38 h 4 min" in text and "39 billed hours" in text


def test_unverified_ids_and_prices_say_verify_on_the_console():
    text, marker = DEPLOY_MD.read_text(), "verify on the AWS console before use"
    for unverified in ("4135ea2d-6df8-44a3-9df3-4b5a84be39ad", "216adef6-5c7f-47e4-b989-5492eafa07d3", "about 55"):
        lines = [line for line in text.splitlines() if unverified in line]
        assert lines and all(marker in line for line in lines), unverified
    assert marker in text.split("## 9. Cost estimate", 1)[1].split("\n## ", 1)[0]


def test_teardown_rotates_the_secret_and_the_evidence_pack_never_holds_it():
    text = DEPLOY_MD.read_text()
    teardown = _block_with(text, "aws cloudfront delete-distribution")
    disable = next(line for line in _logical_lines(teardown) if 'c["Enabled"]=False' in line)
    assert "secrets.token_hex" in disable and '["CustomHeaders"]["Items"][0]["HeaderValue"]' in disable
    assert "rm -f /tmp/epicentre-cf.json" in teardown and "unset EPICENTRE_ORIGIN_SECRET EPICENTRE_PASSWORD" in text
    pack = _logical_lines(text.split("## 10.", 1)[1])
    saved = next(line for line in pack if "08-cloudfront.json" in line and "aws cloudfront" in line)
    assert "--query" in saved and "CustomHeaderNames" in saved and "HeaderValue" not in saved     # names, never the value
    greps = [line for line in pack if "grep" in line and "~/epicentre-evidence" in line]
    assert any("EPICENTRE_ORIGIN_SECRET" in line and "EPICENTRE_PASSWORD" in line for line in greps)
    for line in greps:
        if "$EPICENTRE" in line:                                                                  # a pipe, never argv
            assert "<(printf" in line and line.index("<(printf") < line.index("$EPICENTRE"), line


def test_the_architecture_names_the_three_gates_in_order():
    head = DEPLOY_MD.read_text().split("## 1. Go / no-go", 1)[0]
    g1, g2, g3 = (head.index(f"Gate {n}") for n in (1, 2, 3))
    assert g1 < g2 < g3
    assert "origin-facing" in head[g1:g2]
    assert "X-Origin-Verify" in head[g2:g3] and "403" in head[g2:g3] and "EPICENTRE_ORIGIN_SECRET" in head[g2:g3]
    assert "HTTP Basic" in head[g3:] and "EPICENTRE_REQUIRE_PASSWORD=1" in head


# ---- lane sector-limits (Sun Nov 15): limits by industry and no limits, through /api/run and /api/recheck ----
# The offline fake engine, judged by the REAL rules (governance.load_limits, check_profile, verdict) on its canned numbers
# (its look-through: Financials 14 %, NVIDIA 40 % with the move), so the rows below are governance's own.

def _real_rules_engine():
    import governance
    from fake_engine import _evaluator, fake_engine
    canned = _evaluator()
    universe = [{"ticker": "NVDA", "asset_class": "equity", "sector": "Information Technology"},
                {"ticker": "RY.TO", "asset_class": "equity", "sector": "Financials"},
                {"ticker": "XIU.TO", "asset_class": "etf_equity", "sector": "Broad market (Canada)"}]

    def evaluate(profile, weights, families, as_of, **kw):
        ev = canned(profile, weights, families, as_of, **kw)
        lim = governance.load_limits(profile, kw.get("limits"), amount=kw.get("amount")) if profile else None
        analysis = {**ev["analysis"], "lookthrough": ev["lookthrough"], "universe": universe, "esg_flags": [],
                    "limits": lim}
        checks = governance.check_profile(profile, weights, analysis)
        return {**ev, "analysis": analysis, "checks": checks, "verdict": governance.verdict(checks), "limits": lim}

    return fake_engine(load_limits=governance.load_limits, check_profile=governance.check_profile,
                       verdict=governance.verdict, evaluate=evaluate)


@pytest.fixture()
def ruled(monkeypatch, tmp_path):
    if not READY:
        pytest.skip("pipeline.py and tests/fake_engine.py are not on this checkout")
    engine = _real_rules_engine()
    monkeypatch.setattr(pipeline, "real_engine", lambda: engine)
    monkeypatch.setattr(pipeline, "DEMO_DIR", tmp_path, raising=False)
    monkeypatch.setenv("EPICENTRE_NO_BEDROCK", "1")
    for name in ("EPICENTRE_DEMO", server.PASSWORD_ENV, server.ORIGIN_SECRET_ENV, server.REQUIRE_PASSWORD_ENV):
        monkeypatch.delenv(name, raising=False)
    server.RUNS.clear()
    server.clear_health_cache()
    return TestClient(server.app)


def _rows(checks, prefix="sector_cap:"):
    return {c["rule"]: c for c in checks if c["rule"].startswith(prefix)}


def test_an_industry_limit_goes_through_the_run_and_the_recheck(ruled):
    body = {**robert_body(), "limits": {"sector_caps": {"financials": 0.2, "Energy": 0},
                                        "from_words": ["sector_caps.Energy"]}}
    r = ndjson(ruled, body)[-1]["result"]
    assert r["status"] == "ok" and r["limits"]["sector_caps"] == {"Energy": 0.0, "Financials": 0.2}
    assert "sector_caps" in r["limits"]["edited"] and r["limits"]["from_words"] == ["sector_caps.Energy"]
    rows = _rows(r["checks"])
    assert list(rows) == ["sector_cap:Energy", "sector_cap:Financials"]
    assert (rows["sector_cap:Energy"]["tier"], rows["sector_cap:Energy"]["status"]) == ("hard", "pass")
    assert (rows["sector_cap:Financials"]["status"], rows["sector_cap:Financials"]["value"]) == ("pass", 0.14)
    assert rows["sector_cap:Financials"]["name"] == "Your Financials limit"
    assert (rows["sector_cap:Energy"]["source"], rows["sector_cap:Financials"]["source"]) == ("words", "you")
    assert {c["rule"]: c["source"] for c in r["checks"]}["max_drawdown"] == "assumed"     # Robert's card: R13
    assert "Your Financials limit" in {f["label"] for f in r["facts"].values()}     # citable: a facts row each
    assert any(f["value"] == 0.14 and f["unit"] == "pct" for f in r["facts"].values())  # the share (one number, one row)
    rc = ruled.post("/api/recheck", json={"run_id": r["run_id"], "limits": {"sector_caps": {"Financials": 0.1}}})
    assert rc.status_code == 200, rc.text
    fin = _rows(rc.json()["checks"])
    assert list(fin) == ["sector_cap:Financials"] and fin["sector_cap:Financials"]["status"] == "fail"
    assert fin["sector_cap:Financials"]["source"] == "you"
    assert fin["sector_cap:Financials"]["reason"] == ("In this replay the mix held 14.0 % in Financials, past the "
                                                      "10 % you set.")
    assert _rows((rc.json()["baseline"] or {}).get("checks") or [])["sector_cap:Financials"]["status"] == "fail"
    plain = ruled.post("/api/recheck", json={"run_id": r["run_id"], "limits": {"floor": -0.4}}).json()
    assert not _rows(plain["checks"])                          # no caps sent, no industry rows: nothing kept or invented


def test_an_industry_the_replay_does_not_know_is_refused_in_one_plain_sentence(ruled):
    r = ruled.post("/api/run", json={**robert_body(), "limits": {"sector_caps": {"Crypto": 0.1}}})
    assert r.status_code == 422 and r.json()["message"].startswith("“Crypto” is not an industry this replay knows")
    run_id = ndjson(ruled, robert_body())[-1]["result"]["run_id"]
    bad = ruled.post("/api/recheck", json={"run_id": run_id, "limits": {"sector_caps": {"Energy": 2}}})
    assert error_of(bad, 422) == "The Energy limit is a share of the money, so it must be between 0 % and 100 %."


def test_no_limits_runs_end_to_end_with_every_replay_number_and_no_verdict(ruled):
    r = ndjson(ruled, {**robert_body(), "limits": {"none": True}})[-1]["result"]
    assert r["status"] == "ok" and r["verdict"] is None and r["checks"] == [] and r["limits"] is None
    assert r["metrics"]["after"]["max_drawdown"] == -0.345 and r["series"]["dates"] and r["facts"]
    assert (r["baseline"] or {}).get("checks") in ([], None)
    rc = ruled.post("/api/recheck", json={"run_id": r["run_id"], "limits": {"none": True}}).json()
    assert rc["checks"] == [] and rc["verdict"] is None


# ---- lane backend-fix (Sun Nov 15, jury QA K3): a floor with its sign slipped is the drop it names; never a 500 ----

def test_a_positive_floor_is_the_drop_it_names_and_a_bad_limit_is_422_in_one_plain_sentence(ruled):
    run_id = ndjson(ruled, robert_body())[-1]["result"]["run_id"]
    slipped = ruled.post("/api/recheck", json={"run_id": run_id, "limits": {"floor": 0.35}})
    assert slipped.status_code == 200, slipped.text                       # K3: was a 500 ("35 %" typed as 0.35)
    signed = ruled.post("/api/recheck", json={"run_id": run_id, "limits": {"floor": -0.35}}).json()
    assert slipped.json()["checks"] == signed["checks"] and slipped.json()["verdict"] == signed["verdict"]
    assert {c["rule"]: c["limit"] for c in signed["checks"]}["max_drawdown"] == -0.35
    for limits, words in (({"floor": 35}, "The floor is a drop, so it must be between −100 % and 0 %."),
                          ({"floor": "a lot"}, "The floor must be a number."),
                          ({"scenario_stress": 0.1}, "The shock-check limit is a drop, so it must be between −100 % "
                                                     "and 0 %."),
                          ({"recovery_days": -1}, "The recovery limit must be zero days or more.")):
        said = error_of(ruled.post("/api/recheck", json={"run_id": run_id, "limits": limits}), 422)
        assert said.replace("\xa0", " ").replace("\u202f", " ") == words           # governance's own sentence
