"""The sealed decision record vault (ruling R6, lane B6): a record the investor explicitly seals, stored in a private,
versioned S3 bucket. It is the one input this project ever stores (red gate 6's one exception), and only on the
investor's own action (POST /api/record, from the record card).

    put_record(record: dict, *, expected_sha256=None, client=None, now=None) -> dict
    seal(record) -> str        # 64-hex SHA-256 of proofs.canonical_json(record) as UTF-8: the card's seal, byte for byte

What is stored: the canonical JSON bytes of the record (proofs.canonical_json: keys sorted, no spaces) under
`records/<run_id>/<sha256>.json`, so the key names the run and the seal, and the bytes hash to their own key. S3 checks
the upload against the same SHA-256 (x-amz-checksum-sha256) and keeps it with the object; the object's metadata carries
it too (x-amz-meta-sha256). With EPICENTRE_RECORD_LOCK_DAYS set to a whole number from 1 to 30, the upload asks for an
Object Lock retention in GOVERNANCE mode until now + that many days (the vault's own default retention applies anyway).
COMPLIANCE is never used, so an administrator can always remove a record before the account closes.

The answer always has the same six keys: status ("stored", "off" or "error"), key, version_id, sha256, retain_until
(ISO 8601 UTC, or None) and message (one plain sentence). Storage off (EPICENTRE_RECORD_BUCKET unset or empty, or a
server replaying saved runs with EPICENTRE_DEMO=1) and an AWS failure are answers, never exceptions. Only a record that
is not a JSON object, has no safe run id, holds a non-finite number or a value with no JSON form, or does not match the
seal it was sent with raises ValueError, with a plain sentence the API may show.

Nothing here prints or logs the record, the bucket name or an AWS error message (one can carry an ARN or an account
id): a failure logs its error code only.
"""
import base64
import hashlib
import logging
import math
import os
import re
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import BotoCoreError, ClientError

import config
import proofs

log = logging.getLogger("epicentre.records")

BUCKET_ENV = "EPICENTRE_RECORD_BUCKET"
LOCK_DAYS_ENV = "EPICENTRE_RECORD_LOCK_DAYS"
LOCK_MODE = "GOVERNANCE"
MAX_LOCK_DAYS = 30                                   # the vault's lifecycle expires records after 30 days
PREFIX = "records/"
_RUN_ID_RX = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
_CODE_RX = re.compile(r"[A-Za-z0-9.]{1,64}")

MSG_STORED = "Stored in the private, versioned record vault."
MSG_OFF = "Record storage is off on this server; download the record instead."
MSG_DEMO = "This server replays saved runs, so it stores no record; download the record instead."
MSG_FAILED = "The record vault did not accept the record, so nothing was stored; download the record instead."
MSG_NOT_OBJECT = "The record must be a JSON object."
MSG_RUN_ID = "The record needs its run id: letters, digits, '-' or '_', at most 64."
MSG_NOT_FINITE = "The record holds a number that is not finite."
MSG_NOT_JSON = "The record holds a value that has no plain JSON form."
MSG_SEAL = "The seal does not match the record: it changed after it was sealed, so it was not stored."


def _check_finite(record) -> None:
    stack = [record]
    while stack:                                     # no recursion: any depth the body cap lets through
        item = stack.pop()
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError(MSG_NOT_FINITE)
        if isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, (list, tuple)):
            stack.extend(item)


def _canonical(record) -> bytes:
    _check_finite(record)
    try:
        return proofs.canonical_json(record).encode("utf-8")
    except (TypeError, ValueError, RecursionError):  # UnicodeEncodeError (a lone surrogate) is a ValueError
        raise ValueError(MSG_NOT_JSON) from None


def seal(record) -> str:
    """64-hex SHA-256 of the record's canonical JSON as UTF-8 (lane U9's card computes the same digest)."""
    return hashlib.sha256(_canonical(record)).hexdigest()


def _run_id(record: dict) -> str:
    run = record.get("run")
    value = run.get("run_id") if isinstance(run, dict) else None
    if value is None:
        value = record.get("run_id")
    if not (isinstance(value, str) and _RUN_ID_RX.fullmatch(value)):
        raise ValueError(MSG_RUN_ID)
    return value


def _lock_days() -> int:
    raw = os.environ.get(LOCK_DAYS_ENV, "").strip()
    days = int(raw) if raw.isascii() and raw.isdigit() else 0
    return days if 1 <= days <= MAX_LOCK_DAYS else 0


def storage_off_reason() -> str | None:
    """The plain sentence when this server stores no record, else None."""
    if os.environ.get(config.ENV_DEMO) == "1":
        return MSG_DEMO
    if not os.environ.get(BUCKET_ENV, "").strip():
        return MSG_OFF
    return None


def _answer(status: str, sha: str, message: str, key=None, version_id=None, retain_until=None) -> dict:
    return {"status": status, "key": key, "version_id": version_id, "sha256": sha, "retain_until": retain_until,
            "message": message}


def _code(exc: Exception) -> str:
    code = exc.response.get("Error", {}).get("Code") if isinstance(exc, ClientError) else None
    return code if isinstance(code, str) and _CODE_RX.fullmatch(code) else type(exc).__name__


def put_record(record, *, expected_sha256: str | None = None, client=None, now: datetime | None = None) -> dict:
    """Store one sealed record; see the module docstring for the answer and what raises."""
    if not isinstance(record, dict):
        raise ValueError(MSG_NOT_OBJECT)
    run_id = _run_id(record)
    body = _canonical(record)
    sha = hashlib.sha256(body).hexdigest()
    if expected_sha256 is not None and expected_sha256 != sha:
        raise ValueError(MSG_SEAL)
    off = storage_off_reason()
    if off:
        return _answer("off", sha, off)
    key = f"{PREFIX}{run_id}/{sha}.json"
    params = {"Bucket": os.environ[BUCKET_ENV].strip(), "Key": key, "Body": body, "ContentType": "application/json",
              "ChecksumSHA256": base64.b64encode(bytes.fromhex(sha)).decode("ascii"), "Metadata": {"sha256": sha}}
    retain_until = None
    days = _lock_days()
    if days:
        until = ((now or datetime.now(timezone.utc)).astimezone(timezone.utc) + timedelta(days=days)).replace(microsecond=0)
        params.update(ObjectLockMode=LOCK_MODE, ObjectLockRetainUntilDate=until)
        retain_until = until.strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        s3 = client if client is not None else boto3.client("s3", config=config.boto_config())
        response = s3.put_object(**params)
    except (ClientError, BotoCoreError) as exc:
        log.error("record not stored (%s)", _code(exc))
        return _answer("error", sha, MSG_FAILED)
    return _answer("stored", sha, MSG_STORED, key=key, version_id=response.get("VersionId"), retain_until=retain_until)
