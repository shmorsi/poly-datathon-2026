"""Shared helpers of the two language jobs (navigator, debrief): JSON out of model text, AWS failures as plain
sentences, the Bedrock runtime client. Contract of plan B Task 9 (agents/common.py); the debrief (Task 10) uses
the same three names, so main stays importable whichever task lands first.

No user text and no credential is ever printed or logged here: an error sentence carries the error code only,
never the AWS message (it can name a caller ARN or an account id).
"""
import json

import boto3
from botocore.exceptions import BotoCoreError, ClientError, ConnectTimeoutError, EndpointConnectionError, ReadTimeoutError

import config


def extract_json(text) -> dict | None:
    """The first balanced `{...}` of `text` that parses as a JSON object, else None.

    Prose and ``` fences around it are fine; braces inside JSON strings do not count. A balanced span that does
    not parse is skipped whole (its inner objects are never returned as if they were the answer); a span that
    never closes (cut off) gives None.
    """
    if not isinstance(text, str):
        return None
    i = text.find("{")
    while i != -1:
        end = _balanced_end(text, i)
        if end is None:
            return None
        try:
            value = json.loads(text[i:end + 1])
        except ValueError:
            value = None
        if isinstance(value, dict):
            return value
        i = text.find("{", end + 1)
    return None


def _balanced_end(text: str, start: int) -> int | None:
    """Index of the `}` that closes the `{` at `start`, ignoring braces inside strings; None if it never closes."""
    depth, in_string, escaped = 0, False, False
    for pos in range(start, len(text)):
        ch = text[pos]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return pos
    return None


def aws_error_sentence(exc: BaseException, subject: str) -> str:
    """One plain sentence for an AWS failure; `subject` is "The navigator" or "The debrief". Never the AWS message."""
    code = ""
    if isinstance(exc, ClientError):
        code = str((exc.response.get("Error") or {}).get("Code") or "")
    if code.startswith(("ExpiredToken", "UnrecognizedClient")):
        return f"AWS keys expired: {subject.lower()} could not run."
    if code.startswith("AccessDenied"):
        return f"{subject} was denied by AWS permissions."
    if code.startswith("Throttling"):
        return f"{subject} is busy (throttled); try again in a moment."
    if isinstance(exc, (ReadTimeoutError, ConnectTimeoutError, EndpointConnectionError)):
        return f"{subject} timed out."
    if isinstance(exc, (ClientError, BotoCoreError)):
        return f"{subject} could not run ({code or type(exc).__name__})."
    return f"{subject} could not run ({type(exc).__name__})."


def runtime_client():
    """A bedrock-runtime client on the standard credential chain with the spec section 11 settings."""
    return boto3.client("bedrock-runtime", config=config.boto_config())
