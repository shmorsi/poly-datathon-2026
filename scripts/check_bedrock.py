"""EPICENTRE Bedrock access check: one Converse call with the exact settings of spec section 11.

Run it in a terminal that holds your AWS keys (the event export lines, or AWS_PROFILE); never paste
keys anywhere else:

    python scripts/check_bedrock.py                                  # the configured model
    python scripts/check_bedrock.py --model global.anthropic.claude-sonnet-5

It prints the model id, ok, latency, token usage, stopReason and RequestId, and never credentials, an
account id or a caller ARN. Exit code 0 only when the call returned stopReason "end_turn".
`ping` is also what scripts/preflight.py (Task 12) calls for the navigator and the debrief models.
Sources: spec section 11 (model, request fields, boto3 settings), plan B Task 2.
"""
import argparse
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # `python scripts/check_bedrock.py` puts scripts/, not the repo root, first
    sys.path.insert(0, str(ROOT))

import boto3  # noqa: E402
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError  # noqa: E402

import config  # noqa: E402

PROMPT = "Reply with the single word: ready"
HINT_ACCESS_DENIED = ("Make a first call from CloudShell, wait a few minutes; meanwhile ask the lead to switch "
                      "MODEL_ID + REQUEST_FIELDS to global.anthropic.claude-sonnet-5.")
HINT_EXPIRED = "Your event keys expired: paste fresh export lines."
HINT_NO_CREDENTIALS = ("No AWS credentials found in this terminal: paste the event export lines "
                       "(or set AWS_PROFILE), then run it again.")

# AWS error messages can name the caller: an ARN, an account id or an access key id. Never print those.
_ARN = re.compile(r"arn:aws[\w-]*:[^\s\"'<>(),;]*")
_KEY_ID = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
# A 12-digit run touching a word character or a hyphen is NOT treated as an account id: the last group of a UUID
# RequestId (8-4-4-4-12) can be all digits, and the RequestId is the one identifier the report exists to show.
# Trade-off, pinned by a test: an account id glued to a hyphen ("acct-<12 digits>") survives; the ones AWS
# messages actually carry sit inside ARNs, which _ARN removes first.
_ACCOUNT_ID = re.compile(r"(?<![\w-])\d{12}(?![\w-])")


def _redact(text: str) -> str:
    """text with every ARN, access key id and 12-digit account id replaced by a placeholder."""
    return _ACCOUNT_ID.sub("<account-id>", _KEY_ID.sub("<access-key-id>", _ARN.sub("<arn>", text)))


def _outcome(model_id: str, started: float, **fields) -> dict:
    """The one result shape of `ping`: every key is always present, failures carry None / "" defaults."""
    result = {"ok": False, "model_id": model_id, "latency_ms": round((time.perf_counter() - started) * 1000),
              "server_latency_ms": None, "usage": None, "stop_reason": None, "request_id": None, "text": "",
              "error": None, "hint": None}
    result.update(fields)
    return result


def _client_error_hint(code: str, message: str) -> str | None:
    if code == "AccessDeniedException":
        return HINT_ACCESS_DENIED
    if code.startswith(("ExpiredToken", "UnrecognizedClient")):
        return HINT_EXPIRED
    return _redact(message) or None  # ValidationException: the message names the rejected field


def ping(model_id: str | None = None, client=None) -> dict:
    """One Converse call to `model_id` (default: config.current_model_id()) with the section 11 settings.

    Returns {ok, model_id, latency_ms (client wall clock), server_latency_ms (Converse metrics), usage,
    stop_reason, request_id, text, error, hint}. ok = the call returned and stopReason is "end_turn".
    An expected failure (expired keys, AccessDenied, ValidationException, timeout, unknown model id)
    comes back as ok False with `error` (the error code or the exception class name) and a `hint`; only
    programming errors raise. `client` defaults to a bedrock-runtime client built with config.boto_config().
    """
    model = model_id or config.current_model_id()
    started = time.perf_counter()  # what a failure before the call reports: the time since entry
    try:
        fields = config.request_fields(model)  # ValueError for an id config does not know
    except ValueError as exc:
        return _outcome(model, started, error=type(exc).__name__, hint=str(exc))
    try:
        if client is None:  # built inside the try: a missing AWS_PROFILE raises here
            client = boto3.client("bedrock-runtime", config=config.boto_config())
        started = time.perf_counter()  # latency_ms is the Converse call: the client build is not Bedrock time
        resp = client.converse(
            modelId=model,
            messages=[{"role": "user", "content": [{"text": PROMPT}]}],
            inferenceConfig={"maxTokens": config.MAX_TOKENS_SCENARIO},
            additionalModelRequestFields=fields)
    except ClientError as exc:
        error = exc.response.get("Error", {})
        code = error.get("Code") or type(exc).__name__
        request_id = exc.response.get("ResponseMetadata", {}).get("RequestId")
        return _outcome(model, started, error=code, request_id=request_id,
                        hint=_client_error_hint(code, error.get("Message") or ""))
    except NoCredentialsError as exc:
        return _outcome(model, started, error=type(exc).__name__, hint=HINT_NO_CREDENTIALS)
    except BotoCoreError as exc:
        return _outcome(model, started, error=type(exc).__name__, hint=_redact(str(exc)) or None)
    content = resp.get("output", {}).get("message", {}).get("content", [])
    text = "".join(block["text"] for block in content if "text" in block).strip()  # reasoningContent is ignored
    stop_reason = resp.get("stopReason")
    ok = stop_reason == "end_turn"
    return _outcome(
        model, started, ok=ok, stop_reason=stop_reason, text=text,
        usage=dict(resp["usage"]) if resp.get("usage") else None,
        server_latency_ms=resp.get("metrics", {}).get("latencyMs"),
        request_id=resp.get("ResponseMetadata", {}).get("RequestId"),
        error=None if ok else "UnexpectedStopReason",
        hint=None if ok else (f"The model stopped with {stop_reason!r} instead of 'end_turn' (thinking counts "
                              "toward maxTokens on Sonnet 5.5): check REQUEST_FIELDS and the token cap."))


def _show(value) -> str:
    return "-" if value is None else str(value)


def report(result: dict) -> str:
    """The lines `main` prints: identifiers and numbers only, no credentials, account id or ARN."""
    usage = result["usage"]
    server = "" if result["server_latency_ms"] is None else f" (server {result['server_latency_ms']} ms)"
    lines = [
        "EPICENTRE - Bedrock access check",
        f"region       {config.REGION}",
        f"model        {result['model_id']}",
        f"ok           {result['ok']}",
        f"latency      {result['latency_ms']} ms{server}",
        f"usage        {' '.join(f'{k}={v}' for k, v in usage.items()) if usage else '-'}",
        f"stopReason   {_show(result['stop_reason'])}",
        f"RequestId    {_show(result['request_id'])}",
        f"text         {result['text'] or '-'}",
    ]
    if result["error"]:
        lines += [f"error        {result['error']}", f"hint         {_show(result['hint'])}"]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_bedrock.py", description="EPICENTRE Bedrock access check: one Converse call with the "
        "section 11 settings. Exit code 0 only when the call returned stopReason end_turn.")
    parser.add_argument("--model", default=None, metavar="MODEL_ID",
                        help="model id to check (default: EPICENTRE_MODEL_ID, else the configured Sonnet 5.5 id)")
    args = parser.parse_args(argv)
    result = ping(args.model)
    print(report(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
