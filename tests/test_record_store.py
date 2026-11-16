"""Tests for record_store.py and POST /api/record (lane B6, ruling R6): the sealed decision record vault.

No test reaches AWS. boto3.client is replaced by a recording fake, or the module gets a real botocore S3 client wrapped
in botocore.stub.Stubber, which checks every parameter against the S3 service model and sends nothing.
"""
import base64
import datetime as dt
import hashlib
import logging

import boto3
import pytest
from botocore import UNSIGNED
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError
from botocore.stub import Stubber
from fastapi.testclient import TestClient

import proofs
import record_store
import server

# the shape lane U9's record card builds (schema epicentre.decision-record/1), cut down; every value is fictional
RECORD = {
    "schema": "epicentre.decision-record/1",
    "statement": "Client-run simulation, not a recommendation or a suitability assessment.",
    "run": {"run_id": "a1b2c3d4e5f6", "as_of": "2026-11-12", "mode": "live", "status": "ok"},
    "investor": {"name": "Robert", "age": 59, "fictional": True, "amount": 600000},
    "question": "What if I put 40 % in NVIDIA?",
    "verdict": {"today": "inside", "with_move": "outside"},
    "money": {"end_today": 689123.45, "end_with_move": 802345.5,
              "breaches": [{"depth": -0.169, "loss_dollars": 101548.0}]},
    "numbers": [{"id": "T3", "value": -0.345, "source": "tools.metrics.max_drawdown"}],
}
CANONICAL = proofs.canonical_json(RECORD).encode("utf-8")
SHA = hashlib.sha256(CANONICAL).hexdigest()
KEY = f"records/a1b2c3d4e5f6/{SHA}.json"
BUCKET = "epicentre-records-test"
NOW = dt.datetime(2026, 11, 15, 15, 0, 7, 123456, tzinfo=dt.timezone.utc)
SECRET_TEXT = "arn:aws:iam::123456789012:role/epicentre-runtime"     # what an AWS error message can carry
ANSWER_KEYS = {"status", "key", "version_id", "sha256", "retain_until", "message"}


class FakeS3:
    """Records each put_object call; answers like S3 or raises the error it was given."""

    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def put_object(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return {"VersionId": "v-1", "ETag": '"etag"'}


def _access_denied():
    return ClientError({"Error": {"Code": "AccessDenied", "Message": f"User: {SECRET_TEXT} is not authorized"},
                        "ResponseMetadata": {"RequestId": "REQ1"}}, "PutObject")


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv(record_store.BUCKET_ENV, BUCKET)
    for name in (record_store.LOCK_DAYS_ENV, "EPICENTRE_DEMO", server.PASSWORD_ENV, server.ORIGIN_SECRET_ENV,
                 server.REQUIRE_PASSWORD_ENV):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.fixture
def fake(env):
    s3 = FakeS3()
    made = []

    def client(service, **kwargs):
        made.append((service, kwargs))
        return s3

    env.setattr(record_store.boto3, "client", client)
    s3.made = made
    return s3


def _no_client(*args, **kwargs):
    raise AssertionError("no AWS client may be created here")


# ---- the seal and the answer shape ----

def test_seal_is_the_sha256_of_proofs_canonical_json_whatever_the_key_order():
    assert record_store.seal(RECORD) == SHA
    assert record_store.seal(dict(reversed(list(RECORD.items())))) == SHA       # canonical: keys sorted
    assert record_store.seal({**RECORD, "verdict": {"today": "inside", "with_move": "inside"}}) != SHA


def test_storage_off_without_a_bucket_is_an_answer_never_an_exception(env):
    env.setattr(record_store.boto3, "client", _no_client)
    for value in (None, "", "   "):
        if value is None:
            env.delenv(record_store.BUCKET_ENV, raising=False)
        else:
            env.setenv(record_store.BUCKET_ENV, value)
        answer = record_store.put_record(RECORD)
        assert answer == {"status": "off", "key": None, "version_id": None, "sha256": SHA, "retain_until": None,
                          "message": record_store.MSG_OFF}


def test_a_server_replaying_saved_runs_stores_nothing(env):
    env.setenv("EPICENTRE_DEMO", "1")
    env.setattr(record_store.boto3, "client", _no_client)
    answer = record_store.put_record(RECORD)
    assert (answer["status"], answer["message"], answer["sha256"]) == ("off", record_store.MSG_DEMO, SHA)


# ---- what is stored, and where ----

def test_put_stores_the_canonical_bytes_under_the_run_id_and_the_seal(fake):
    answer = record_store.put_record(RECORD)
    assert answer == {"status": "stored", "key": KEY, "version_id": "v-1", "sha256": SHA, "retain_until": None,
                      "message": record_store.MSG_STORED}
    (call,) = fake.calls
    assert call == {"Bucket": BUCKET, "Key": KEY, "Body": CANONICAL, "ContentType": "application/json",
                    "ChecksumSHA256": base64.b64encode(hashlib.sha256(CANONICAL).digest()).decode("ascii"),
                    "Metadata": {"sha256": SHA}}
    assert hashlib.sha256(call["Body"]).hexdigest() in call["Key"]           # the bytes hash to their own key
    ((service, kwargs),) = fake.made
    assert service == "s3" and kwargs["config"].region_name == "us-east-1"


def test_object_lock_headers_when_lock_days_are_set(fake, env):
    env.setenv(record_store.LOCK_DAYS_ENV, "7")
    answer = record_store.put_record(RECORD, now=NOW)
    (call,) = fake.calls
    until = dt.datetime(2026, 11, 22, 15, 0, 7, tzinfo=dt.timezone.utc)      # whole seconds
    assert (call["ObjectLockMode"], call["ObjectLockRetainUntilDate"]) == ("GOVERNANCE", until)
    assert answer["retain_until"] == "2026-11-22T15:00:07Z" and answer["status"] == "stored"


@pytest.mark.parametrize("value", ["", "0", "-3", "seven", "7.5", "31", "36500"])
def test_lock_days_outside_1_to_30_send_no_lock_headers(fake, env, value):
    env.setenv(record_store.LOCK_DAYS_ENV, value)
    answer = record_store.put_record(RECORD, now=NOW)
    (call,) = fake.calls
    assert not {"ObjectLockMode", "ObjectLockRetainUntilDate"} & set(call)
    assert answer["retain_until"] is None


def test_the_request_passes_the_s3_service_model(env):
    """A real botocore client behind Stubber: every parameter name and type is checked against S3's model."""
    env.setenv(record_store.LOCK_DAYS_ENV, "7")
    s3 = boto3.client("s3", region_name="us-east-1", config=Config(signature_version=UNSIGNED))   # no credentials at all
    version = "3sL4kqtJlcpXroDTDmJ+rmSpXd3dIbrHY+MTRCxf3vjVBH40Nr8X8gdRQBpUMLUo"
    with Stubber(s3) as stub:
        stub.add_response("put_object", {"VersionId": version, "ETag": '"etag"'}, {
            "Bucket": BUCKET, "Key": KEY, "Body": CANONICAL, "ContentType": "application/json",
            "ChecksumSHA256": base64.b64encode(hashlib.sha256(CANONICAL).digest()).decode("ascii"),
            "Metadata": {"sha256": SHA}, "ObjectLockMode": "GOVERNANCE",
            "ObjectLockRetainUntilDate": dt.datetime(2026, 11, 22, 15, 0, 7, tzinfo=dt.timezone.utc)})
        answer = record_store.put_record(RECORD, client=s3, now=NOW)
        stub.assert_no_pending_responses()
    assert (answer["status"], answer["version_id"], answer["key"]) == ("stored", version, KEY)


def test_the_run_id_may_also_sit_at_the_top_of_the_record(fake):
    flat = {k: v for k, v in RECORD.items() if k != "run"} | {"run_id": "saved_robert-1"}
    answer = record_store.put_record(flat)
    assert answer["key"] == f"records/saved_robert-1/{record_store.seal(flat)}.json"


# ---- what is refused, before any AWS call ----

@pytest.mark.parametrize("run", [None, {}, {"run_id": None}, {"run_id": ""}, {"run_id": "../etc"}, {"run_id": "a/b"},
                                 {"run_id": "a b"}, {"run_id": "x" * 65}, {"run_id": 123456789012}, {"run_id": "-lead"}])
def test_a_record_without_a_safe_run_id_is_refused(env, run):
    env.setattr(record_store.boto3, "client", _no_client)
    record = {k: v for k, v in RECORD.items() if k != "run"} | ({"run": run} if run is not None else {})
    with pytest.raises(ValueError) as err:
        record_store.put_record(record)
    assert str(err.value) == record_store.MSG_RUN_ID


@pytest.mark.parametrize("value", [["a", "list"], "text", 7, None])
def test_a_record_that_is_not_an_object_is_refused(env, value):
    env.setattr(record_store.boto3, "client", _no_client)
    with pytest.raises(ValueError) as err:
        record_store.put_record(value)
    assert str(err.value) == record_store.MSG_NOT_OBJECT


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_a_record_with_a_non_finite_number_is_refused(env, bad):
    env.setattr(record_store.boto3, "client", _no_client)
    with pytest.raises(ValueError) as err:
        record_store.put_record({**RECORD, "money": {"breaches": [{"depth": bad}]}})
    assert str(err.value) == record_store.MSG_NOT_FINITE


def test_a_record_that_is_not_plain_json_is_refused(env):
    env.setattr(record_store.boto3, "client", _no_client)
    with pytest.raises(ValueError) as err:
        record_store.put_record({**RECORD, "question": "\ud800"})                 # a lone surrogate: no UTF-8 form
    assert str(err.value) == record_store.MSG_NOT_JSON


def test_a_broken_seal_is_refused_and_a_matching_one_is_stored(fake):
    with pytest.raises(ValueError) as err:
        record_store.put_record(RECORD, expected_sha256="0" * 64)
    assert str(err.value) == record_store.MSG_SEAL and fake.calls == []
    assert record_store.put_record(RECORD, expected_sha256=SHA)["status"] == "stored"


# ---- AWS failures are answers, and only their code is logged ----

@pytest.mark.parametrize("error", [_access_denied(), EndpointConnectionError(endpoint_url="https://s3.amazonaws.com")])
def test_an_aws_failure_is_an_error_answer_that_logs_the_code_only(fake, caplog, error):
    fake.error = error
    caplog.set_level(logging.DEBUG)
    answer = record_store.put_record(RECORD)
    assert set(answer) == ANSWER_KEYS
    assert (answer["status"], answer["key"], answer["version_id"], answer["sha256"], answer["message"]) == (
        "error", None, None, SHA, record_store.MSG_FAILED)
    logged = caplog.text
    assert ("AccessDenied" in logged) or ("EndpointConnectionError" in logged)
    for leak in (SECRET_TEXT, "123456789012", BUCKET, "Robert", "NVIDIA", "s3.amazonaws.com"):
        assert leak not in logged


# ---- POST /api/record ----

@pytest.fixture
def api(fake):
    return TestClient(server.create_app(web_dir=None))


def test_route_stores_a_sealed_record_and_answers_its_key_version_and_seal(api, fake):
    response = api.post("/api/record", json={"record": RECORD, "sha256": SHA})
    assert response.status_code == 200
    assert response.json() == {"status": "stored", "key": KEY, "version_id": "v-1", "sha256": SHA,
                               "retain_until": None, "message": record_store.MSG_STORED}
    assert fake.calls[0]["Body"] == CANONICAL


def test_route_with_storage_off_answers_200_status_off(api, fake, monkeypatch):
    monkeypatch.delenv(record_store.BUCKET_ENV)
    response = api.post("/api/record", json={"record": RECORD})
    assert response.status_code == 200 and response.json()["status"] == "off" and fake.calls == []


def test_route_refuses_a_broken_seal_with_one_plain_sentence(api, fake):
    response = api.post("/api/record", json={"record": RECORD, "sha256": "f" * 64})
    assert response.status_code == 422
    assert response.json() == {"status": "error", "message": record_store.MSG_SEAL} and fake.calls == []


@pytest.mark.parametrize("body", [{}, {"record": [1, 2]}, {"record": "text"}, {"record": RECORD, "sha256": "XYZ"}])
def test_route_refuses_a_malformed_body(api, fake, body):
    response = api.post("/api/record", json=body)
    assert response.status_code == 422 and response.json()["status"] == "error" and fake.calls == []


def test_route_answers_502_with_a_plain_sentence_when_aws_fails(api, fake):
    fake.error = _access_denied()
    response = api.post("/api/record", json={"record": RECORD})
    assert response.status_code == 502
    assert response.json()["message"] == record_store.MSG_FAILED and "arn:" not in response.text


def test_route_takes_a_record_up_to_128_kb_and_refuses_more(api, fake):
    """Controller ruling (the lead, Sun 15 Nov): /api/record's cap is 128 KB (a sealed record is 15-50 KB and grows);
    every other route keeps MAX_BODY_BYTES (64 KB)."""
    assert server.RECORD_MAX_BODY_BYTES == 128 * 1024 and server.MAX_BODY_BYTES == 64 * 1024
    big = {**RECORD, "question": "x" * (100 * 1024)}                      # over the old 64 KB, under 128 KB
    assert api.post("/api/record", json={"record": big}).status_code == 200 and len(fake.calls) == 1
    too_big = {**RECORD, "question": "x" * server.RECORD_MAX_BODY_BYTES}
    assert api.post("/api/record", json={"record": too_big}).status_code == 413 and len(fake.calls) == 1
    other = api.post("/api/recheck", json={"run_id": "nope", "limits": {}, "padding": "x" * (100 * 1024)})
    assert other.status_code == 413                                        # the other routes keep 64 KB


@pytest.mark.parametrize("pieces, status", [(10, 200), (14, 413)])        # 100 KB passes, 140 KB is refused
def test_route_cap_holds_for_a_body_without_a_content_length(api, fake, pieces, status):
    def chunks():                                           # sent as Transfer-Encoding: chunked, no Content-Length
        yield b'{"record": {"run": {"run_id": "a1b2c3d4e5f6"}, "question": "'
        for _ in range(pieces):
            yield b"x" * 10_240
        yield b'"}}'
    response = api.post("/api/record", content=chunks(), headers={"content-type": "application/json"})
    assert "content-length" not in response.request.headers and response.status_code == status
    assert len(fake.calls) == (1 if status == 200 else 0)


def test_route_never_logs_the_record(api, fake, caplog):
    caplog.set_level(logging.DEBUG)
    marked = {**RECORD, "question": "SENTINEL-INVESTOR-WORDS"}
    api.post("/api/record", json={"record": marked})
    fake.error = _access_denied()
    api.post("/api/record", json={"record": marked})
    api.post("/api/record", json={"record": marked, "sha256": "0" * 64})
    assert "SENTINEL-INVESTOR-WORDS" not in caplog.text and BUCKET not in caplog.text


def test_route_sits_behind_the_password_like_every_route(fake, monkeypatch):
    monkeypatch.setenv(server.PASSWORD_ENV, "pw")
    response = TestClient(server.create_app(web_dir=None)).post("/api/record", json={"record": RECORD})
    assert response.status_code == 401 and fake.calls == []
