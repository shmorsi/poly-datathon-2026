"""EPICENTRE preflight: the canaries to run before recording and before submitting (plan B Task 12).

    python scripts/preflight.py            # every check; exit code 0 only when every one of them is a PASS
    python scripts/preflight.py --offline  # the checks that need AWS are NOT RUN; an offline run is never a pass

Run it in a terminal that holds your AWS keys and exports EPICENTRE_GUARDRAIL_ID and EPICENTRE_GUARDRAIL_VERSION
(scripts/create_guardrail.py prints both). Use an admin shell: the guardrail lookup needs bedrock:GetGuardrail,
which the runtime role does not have, by design.

Output: one line per check, `PASS|FAIL|NOT RUN  name  detail`, then `Epicentre: k / N passed`; nothing else.
A check that cannot run is a FAIL or NOT RUN, never a PASS. An exception inside a check is a FAIL whose detail is the
exception's class name (never a traceback, never the exception's text, which can carry a key or an ARN).

Read-only: it never creates, updates or deletes an AWS resource. The AWS calls are Converse (the two model pings, the
navigator and the cache canary), ApplyGuardrail (two input canaries) and one GetGuardrail. A detail never carries a key,
an account id, an ARN or the guardrail id. Prompt caching is claimed only when the second identical call reads from the
cache (ledger section 30 measured 1,264 tokens once, on Sonnet 5.5); otherwise the detail says to make no claim.
Sources: spec section 11 (models, region), section 7 (guardrail), section 24 resolutions 2 and 3, plan B Task 12.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # `python scripts/preflight.py` puts scripts/, not the repo root, first
    sys.path.insert(0, str(ROOT))

import boto3  # noqa: E402
from botocore.exceptions import BotoCoreError, ClientError  # noqa: E402

import config  # noqa: E402
from agents.common import aws_error_sentence, runtime_client  # noqa: E402  (tests patch runtime_client here)
from agents.explainer import DEBRIEF_PROMPT  # noqa: E402
from agents.scenario import run_scenario  # noqa: E402
from guardrail import apply_guardrail  # noqa: E402
from scripts.check_bedrock import HINT_NO_CREDENTIALS, PROMPT, _redact, ping  # noqa: E402
from tools.data import DATASET_END, load_universe  # noqa: E402
from tools.events import load_events  # noqa: E402
from tools.portfolio import normalize  # noqa: E402

EXPECTED_REGION = "us-east-1"  # spec section 11; the IAM policies and the guardrail profile are written for it
ADVICE_CANARY = "Should I buy NVDA now?"  # the guardrail must block it (pitfall 2: the narrow denied topic)
CANARY_MAX_TOKENS = config.MAX_TOKENS_SCENARIO  # 1500, as scripts/check_bedrock.ping
TESTS_TIMEOUT_S = 1800
DETAIL_MAX_CHARS = 240


def _plain(detail) -> str:
    """One line with no ARN, access key id or account id, cut to DETAIL_MAX_CHARS."""
    line = _redact(" ".join(str(detail).split()))
    return line if len(line) <= DETAIL_MAX_CHARS else line[:DETAIL_MAX_CHARS - 3].rstrip() + "..."


def _robert() -> dict:
    """Robert's card from data/personas.json (the scripted question and portfolio are never hardcoded here)."""
    return json.loads(config.PERSONAS_JSON.read_text(encoding="utf-8"))["pilots"]["robert"]


def _guardrail_env() -> tuple[str, str]:
    return ((os.environ.get(config.ENV_GUARDRAIL_ID) or "").strip(),
            (os.environ.get(config.ENV_GUARDRAIL_VERSION) or "").strip())


def aws_session():
    """The default boto3 session (standard credential chain); tests patch it."""
    return boto3.Session()


def control_client():
    """A bedrock (control plane) client on the standard credential chain; tests patch it. Only GetGuardrail is
    called on it."""
    return boto3.client("bedrock", config=config.boto_config())


# ---- 1-2. credentials and region ----
def check_credentials():
    creds = aws_session().get_credentials()
    if creds is None:
        return False, HINT_NO_CREDENTIALS
    return True, f"credentials found via {getattr(creds, 'method', None) or 'an unknown source'}"


def check_region():
    app, shell = runtime_client().meta.region_name, aws_session().region_name
    if app == EXPECTED_REGION and shell in (None, EXPECTED_REGION):
        where = "the app client and this shell" if shell else "the app client (this shell sets no default region)"
        return True, f"{EXPECTED_REGION} for {where}"
    return False, (f"the app client uses {app}, this shell uses {shell or 'no default region'}; both must be "
                   f"{EXPECTED_REGION}: set AWS_REGION={EXPECTED_REGION}")


# ---- 3-4. the two models, through the one availability probe (scripts/check_bedrock.ping) ----
def _check_model(job: str):
    model = config.model_for(job)
    res = ping(model)
    if res.get("ok") is True and res.get("stop_reason") == "end_turn":
        return True, f"{res.get('model_id') or model} answered in {res.get('latency_ms')} ms"
    parts = [str(res.get("error") or f"stop reason {res.get('stop_reason')!r}")]
    if res.get("hint"):
        parts.append(str(res["hint"]))
    return False, f"{model}: " + ": ".join(parts)


def check_model_navigator():
    return _check_model("navigator")


def check_model_debrief():
    return _check_model("debrief")


# ---- 5-6. the guardrail: ids, then a read-only GetGuardrail ----
def check_guardrail_ids():
    guardrail_id, version = _guardrail_env()
    if not (guardrail_id and version):
        return False, (f"export {config.ENV_GUARDRAIL_ID} and {config.ENV_GUARDRAIL_VERSION} "
                       "(scripts/create_guardrail.py prints both)")
    return True, f"version {version}"  # the id stays out of the output


def _lookup_failure(exc: ClientError) -> str:
    code = str((exc.response.get("Error") or {}).get("Code") or "")
    if code == "ResourceNotFoundException":
        return f"guardrail not found in {config.REGION}: check the id and version in your environment"
    if code.startswith("AccessDenied"):
        return ("denied: reading a guardrail needs bedrock:GetGuardrail, which the runtime role does not have "
                "by design; run preflight in an admin shell")
    return aws_error_sentence(exc, "The guardrail lookup")


def check_guardrail_exists():
    guardrail_id, version = _guardrail_env()
    if not (guardrail_id and version):
        return False, f"needs {config.ENV_GUARDRAIL_ID} and {config.ENV_GUARDRAIL_VERSION}; no AWS call was made"
    try:
        got = control_client().get_guardrail(guardrailIdentifier=guardrail_id, guardrailVersion=version)
    except ClientError as exc:
        return False, _lookup_failure(exc)
    except BotoCoreError as exc:
        return False, aws_error_sentence(exc, "The guardrail lookup")
    status, found, name = got.get("status"), str(got.get("version")), got.get("name")
    if name not in (config.GUARDRAIL_NAME, *config.LEGACY_GUARDRAIL_NAMES):
        return False, f"the id in your environment is a guardrail named {name!r}, not {config.GUARDRAIL_NAME!r}"
    if status != "READY":
        return False, f"status {status}, not READY: wait for it, then run preflight again"
    if found != version:
        return False, f"asked for version {version}, AWS answered version {found}"
    if version == "DRAFT":
        return False, ("version is DRAFT: publish a numbered version (scripts/create_guardrail.py --publish) before "
                       "recording; the evidence pack never uses DRAFT")
    return True, f"{status}, version {found}, {name}, {config.REGION}"


# ---- 7-8. the input canaries ----
def check_guardrail_blocks_advice():
    res = apply_guardrail(ADVICE_CANARY, "INPUT")
    if res.get("error"):
        return False, res["error"]
    if res.get("blocked") is True:
        return True, f"blocked in {res.get('latency_ms')} ms"
    return False, "not blocked: the trade-instruction topic did not fire; do not record"


def check_guardrail_passes_pilot():
    res = apply_guardrail(_robert()["question"], "INPUT")
    if res.get("error"):
        return False, res["error"]
    if res.get("blocked") is True:
        return False, "Robert's scripted question was blocked (a false block): do not record"
    return True, f"Robert's question passed in {res.get('latency_ms')} ms"


# ---- 9. the navigator, whole path, on Robert's question ----
def check_navigator_live():
    card = _robert()
    res = run_scenario(card["question"], normalize(card["portfolio"]), load_events(DATASET_END), DATASET_END,
                       universe=load_universe())
    if res.get("method") == "bedrock":
        ms = res.get("ms")
        return True, "method bedrock" + (f", {round(ms)} ms" if isinstance(ms, (int, float)) else "")
    return False, res.get("fallback_reason") or f"method {res.get('method')!r}, not 'bedrock'"


# ---- 10. prompt caching: a claim needs a measured read ----
def check_prompt_cache():
    model = config.model_for("debrief")
    request = {"modelId": model, "system": [{"text": DEBRIEF_PROMPT}, {"cachePoint": {"type": "default"}}],
               "messages": [{"role": "user", "content": [{"text": PROMPT}]}],
               "inferenceConfig": {"maxTokens": CANARY_MAX_TOKENS},
               "additionalModelRequestFields": config.request_fields(model)}
    client = runtime_client()
    try:
        client.converse(**request)
        second = client.converse(**request)
    except (ClientError, BotoCoreError) as exc:
        return False, aws_error_sentence(exc, "The cache canary")
    read = int(((second or {}).get("usage") or {}).get("cacheReadInputTokens") or 0)
    if read > 0:
        return True, f"caching proven: {read} tokens read"
    return False, "no cache read: make no caching claim"


# ---- 11-14. local checks ----
def check_dataset():
    if (config.STARTER_DIR / "prices_daily.csv").exists():
        return True, "data/starter/prices_daily.csv found"
    return False, "data/starter/prices_daily.csv is missing: put the starter files in data/starter/"


def check_holdings():
    if config.ETF_HOLDINGS_CSV.exists():
        return True, "data/etf_holdings.csv found"
    return False, ("data/etf_holdings.csv is missing: run scripts/fetch_holdings.py "
                   "(without it look-through falls back to direct holdings)")


def check_tests():
    try:
        done = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=config.ROOT, capture_output=True,
                              text=True, timeout=TESTS_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return False, f"the test suite timed out after {TESTS_TIMEOUT_S // 60} minutes"
    lines = [line.strip() for line in (done.stdout or "").splitlines() if line.strip()]
    return done.returncode == 0, lines[-1] if lines else "pytest printed nothing"


def check_server():
    from fastapi.testclient import TestClient

    import server
    status = TestClient(server.app).get("/api/health").status_code
    return status == 200, f"GET /api/health answered {status}"


# ---- the table, in running order ----
CHECKS = [
    ("credentials", check_credentials),
    ("region", check_region),
    ("model_navigator", check_model_navigator),
    ("model_debrief", check_model_debrief),
    ("guardrail_ids", check_guardrail_ids),
    ("guardrail_exists", check_guardrail_exists),
    ("guardrail_blocks_advice", check_guardrail_blocks_advice),
    ("guardrail_passes_pilot", check_guardrail_passes_pilot),
    ("navigator_live", check_navigator_live),
    ("prompt_cache", check_prompt_cache),
    ("dataset", check_dataset),
    ("holdings", check_holdings),
    ("tests", check_tests),
    ("server", check_server),
]
# `--offline` marks these NOT RUN: they read the AWS credential chain or call AWS. The other four run offline.
AWS_CHECKS = {"credentials", "region", "model_navigator", "model_debrief", "guardrail_ids", "guardrail_exists",
              "guardrail_blocks_advice", "guardrail_passes_pilot", "navigator_live", "prompt_cache"}


def _row(name: str, status: str, detail) -> dict:
    return {"name": name, "status": status, "detail": _plain(detail)}


def run_checks(offline: bool = False, *, on_row=None) -> list[dict]:
    """[{name, status "PASS"|"FAIL"|"NOT RUN", detail}] in CHECKS order. Prints nothing itself (`on_row`, if given, is
    called with each row as soon as its check is done) and never raises for a check: an exception is a FAIL whose
    detail is the exception's class name (its text can carry a key or an ARN)."""
    rows = []
    for name, check in CHECKS:
        if offline and name in AWS_CHECKS:
            row = _row(name, "NOT RUN", "offline: this check needs AWS")
        else:
            try:
                ok, detail = check()
                row = _row(name, "PASS" if ok is True else "FAIL", detail)
            except Exception as exc:  # a check that cannot run is a FAIL, never a pass and never a traceback
                row = _row(name, "FAIL", type(exc).__name__)
        rows.append(row)
        if on_row is not None:
            on_row(row)
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="preflight.py", description="EPICENTRE preflight canaries. Exit code 0 only when every check is a PASS.")
    parser.add_argument("--offline", action="store_true",
                        help="do not call AWS: the checks that need it are NOT RUN, and the run is never a pass")
    args = parser.parse_args(argv)
    # each line appears as soon as its check is done: the test suite and the model calls take a while
    rows = run_checks(offline=args.offline,
                      on_row=lambda row: print(f"{row['status']}  {row['name']}  {row['detail']}", flush=True))
    passed = sum(row["status"] == "PASS" for row in rows)
    print(f"Epicentre: {passed} / {len(rows)} passed")
    if args.offline:
        print("Offline run: not a preflight pass.")
    return 0 if rows and passed == len(rows) and not args.offline else 1


if __name__ == "__main__":
    raise SystemExit(main())
