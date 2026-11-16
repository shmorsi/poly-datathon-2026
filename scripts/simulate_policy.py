"""EPICENTRE policy simulator: what the repo's IAM policy allows and denies, asked of AWS, read-only.

    python scripts/simulate_policy.py

It creates and changes nothing. Two evaluate-only calls on the policy text of docs/iam/*.json, nothing else:
  * iam:SimulateCustomPolicy on docs/iam/runtime-policy.json: the actions the app uses (bedrock:InvokeModel on the model
    ids of config.py, bedrock:ApplyGuardrail on the guardrail and its cross-Region profiles) must come back `allowed`,
    and actions the app must not have (guardrail management, model listing, custom metrics, storage, the eval-only
    model, another guardrail, the global model outside its documented condition) must come back `implicitDeny`;
  * access-analyzer:ValidatePolicy on both policy files (identity policies): ERROR and SECURITY_WARNING findings fail
    the run, WARNING and SUGGESTION findings are listed.
The policy files hold `<ACCOUNT_ID>` and `<GUARDRAIL_ID>`; the calls use stand-in values, so this script never looks
up, sends or prints your real account id, and it prints the placeholders. It prints no credential and no ARN of yours.
Run it in a terminal that holds your AWS keys (the standard credential chain; AWS_PROFILE works). Exit code 0 only when
every decision is as expected and no finding is an ERROR or SECURITY_WARNING. Save the output as the evidence-pack item
`04-simulator.txt` (docs/aws.md, item 4).
Sources: spec section 24 (meeting 1 resolution 11, meeting 2 resolution 2), docs/aws.md item 4, docs/iam/*.json.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # `python scripts/simulate_policy.py` puts scripts/, not the repo root, first
    sys.path.insert(0, str(ROOT))

import boto3  # noqa: E402
from botocore.exceptions import BotoCoreError, ClientError  # noqa: E402

import config  # noqa: E402
from agents.common import aws_error_sentence  # noqa: E402

RUNTIME_POLICY = ROOT / "docs" / "iam" / "runtime-policy.json"
ADMIN_POLICY = ROOT / "docs" / "iam" / "admin-policy.json"
US_REGIONS = ("us-east-1", "us-east-2", "us-west-2")  # where the US cross-Region profiles may route (spec section 11)
# The files hold placeholders; AWS evaluates ARN text, so stand-ins give the same decisions. Real ids are never needed.
DUMMY_ACCOUNT, DUMMY_GUARDRAIL, DUMMY_OTHER_GUARDRAIL = "123456789012", "abcd1234efgh", "zzzz9999yyyy"
PLACEHOLDERS = {"<ACCOUNT_ID>": DUMMY_ACCOUNT, "<GUARDRAIL_ID>": DUMMY_GUARDRAIL,
                "<OTHER_GUARDRAIL_ID>": DUMMY_OTHER_GUARDRAIL}
BLOCKING_FINDINGS = ("ERROR", "SECURITY_WARNING")
FINDING_ORDER = ("ERROR", "SECURITY_WARNING", "WARNING", "SUGGESTION")
ALLOWED, DENIED = "allowed", "implicitDeny"
GLOBAL_REFUSALS = ("AccessDenied", "ExpiredToken", "UnrecognizedClient", "InvalidClientTokenId", "Throttl")


def concrete(text: str) -> str:
    """`text` with the placeholders replaced by stand-in values (what is sent to AWS)."""
    for placeholder, value in PLACEHOLDERS.items():
        text = text.replace(placeholder, value)
    return text


def masked(text: str) -> str:
    """`text` with the stand-in values turned back into placeholders (what is printed)."""
    for placeholder, value in PLACEHOLDERS.items():
        text = text.replace(value, placeholder)
    return text


def probes() -> list[dict]:
    """The questions put to the simulator: {action, resource, context, expected}. The allowed ones come from config.py
    (the ids the app really calls), so a model id that drifts from the policy shows up as a mismatch."""
    region, account, rows = config.REGION, "<ACCOUNT_ID>", []

    def add(action, resource, expected, **context):
        row = {"action": action, "resource": resource, "context": tuple(sorted(context.items())), "expected": expected}
        # the us. and global. ids of one model share their foundation-model ARNs: ask each question once
        if all((r["action"], r["resource"], r["context"]) != (action, resource, row["context"]) for r in rows):
            rows.append(row)

    for model in (config.MODEL_ID, config.MODEL_ID_GLOBAL, config.MODEL_ID_FALLBACK):
        scope, _, base = model.partition(".")
        add("bedrock:InvokeModel", f"arn:aws:bedrock:{region}:{account}:inference-profile/{model}", ALLOWED)
        add("bedrock:InvokeModel", f"arn:aws:bedrock:{region}::foundation-model/{base}", ALLOWED)
        if scope == "global":  # the documented pattern: a region-less model ARN, condition aws:RequestedRegion
            add("bedrock:InvokeModel", f"arn:aws:bedrock:::foundation-model/{base}", ALLOWED,
                **{"aws:RequestedRegion": "unspecified"})
        else:
            for other in (r for r in US_REGIONS if r != region):
                add("bedrock:InvokeModel", f"arn:aws:bedrock:{other}::foundation-model/{base}", ALLOWED)
    guardrail = f"arn:aws:bedrock:{region}:{account}:guardrail/<GUARDRAIL_ID>"
    add("bedrock:ApplyGuardrail", guardrail, ALLOWED)
    for each in US_REGIONS:
        add("bedrock:ApplyGuardrail", f"arn:aws:bedrock:{each}:{account}:guardrail-profile/{config.GUARDRAIL_PROFILE}",
            ALLOWED)
    # what the app must NOT be able to do (docs/aws.md, "IAM: least privilege")
    global_base = config.MODEL_ID_GLOBAL.partition(".")[2]
    add("bedrock:InvokeModel", f"arn:aws:bedrock:::foundation-model/{global_base}", DENIED,
        **{"aws:RequestedRegion": region})
    add("bedrock:InvokeModel", f"arn:aws:bedrock:{region}:{account}:inference-profile/{config.MODEL_ID_HAIKU}", DENIED)
    add("bedrock:ApplyGuardrail", f"arn:aws:bedrock:{region}:{account}:guardrail/<OTHER_GUARDRAIL_ID>", DENIED)
    add("bedrock:CreateGuardrail", "*", DENIED)
    add("bedrock:UpdateGuardrail", guardrail, DENIED)
    add("bedrock:ListGuardrails", "*", DENIED)
    add("bedrock:ListFoundationModels", "*", DENIED)
    add("cloudwatch:PutMetricData", "*", DENIED)
    add("s3:GetObject", "arn:aws:s3:::example-bucket/example-object", DENIED)
    return rows


def _context_entries(context) -> list[dict]:
    return [{"ContextKeyName": key, "ContextKeyValues": [value], "ContextKeyType": "string"} for key, value in context]


def _decision(iam, policy_text: str, question: dict):
    """The simulator's decision for one (action, resource, context). One resource per call on purpose: asked about
    several resources at once, SimulateCustomPolicy returns ONE overall decision for the action (seen live), not one
    per resource, and the evidence table needs a decision for each pair."""
    resource = concrete(question["resource"])
    request = {"PolicyInputList": [policy_text], "ActionNames": [question["action"]], "ResourceArns": [resource]}
    if question["context"]:
        request["ContextEntries"] = _context_entries(question["context"])
    results = iam.simulate_custom_policy(**request).get("EvaluationResults") or []
    asked = [r for r in results
             if r.get("EvalActionName") == question["action"] and r.get("EvalResourceName") == resource]
    return (asked or results or [{}])[0].get("EvalDecision")


def simulate(iam, policy_text: str, questions: list[dict]) -> list[dict]:
    """Each question with its `decision` and `ok`, in the order given: one call per question. `policy_text` must
    already be concrete (no placeholders). A question the simulator rejects (say, an action name it does not know)
    becomes its own row `error <code>`; a refusal that would hit every call (no permission, expired keys, throttling)
    is raised."""
    rows = []
    for question in questions:
        try:
            decision = _decision(iam, policy_text, question)
        except ClientError as exc:
            code = str((exc.response.get("Error") or {}).get("Code") or type(exc).__name__)
            if code.startswith(GLOBAL_REFUSALS):
                raise
            decision = f"error {code}"
        rows.append({**question, "decision": decision or "no answer", "ok": decision == question["expected"]})
    return rows


def _where(locations) -> str:
    """A finding's place in the policy, like Statement[0].Resource[2]."""
    parts = []
    for step in ((locations or [{}])[0].get("path") or []):
        if "index" in step:
            parts.append(f"[{step['index']}]")
        elif "value" in step or "key" in step:
            parts.append(("." if parts else "") + str(step.get("value", step.get("key"))))
    return "".join(parts)


def validate(analyzer, policy_text: str) -> list[dict]:
    """Access Analyzer findings for one identity policy: {type, code, where, detail}, worst first."""
    pages = analyzer.get_paginator("validate_policy").paginate(policyDocument=policy_text, policyType="IDENTITY_POLICY")
    findings = [{"type": f.get("findingType"), "code": f.get("issueCode"), "where": _where(f.get("locations")),
                 "detail": masked(" ".join(str(f.get("findingDetails") or "").split()))}
                for page in pages for f in page.get("findings") or []]
    return sorted(findings, key=lambda f: FINDING_ORDER.index(f["type"]) if f["type"] in FINDING_ORDER else -1)


def render_table(rows: list[dict]) -> str:
    """The evidence table: action, decision, expected, then the resource (and the condition context, if any)."""
    cells = [(r["action"], r["decision"], r["expected"],
              masked(r["resource"]) + "".join(f"  [{k}={v}]" for k, v in r["context"])
              + ("" if r["ok"] else "  MISMATCH"))
             for r in rows]
    head = ("action", "decision", "expected", "resource")
    widths = [max(len(head[i]), *(len(c[i]) for c in cells)) for i in range(3)]
    line = "{:<%d}  {:<%d}  {:<%d}  {}" % tuple(widths)
    return "\n".join([line.format(*head)] + [line.format(*c) for c in cells])


def _failure(call: str, subject: str, exc: Exception) -> str:
    return f"{call} did not run: {aws_error_sentence(exc, subject)}"


def main(argv=None, *, iam=None, analyzer=None) -> int:
    argparse.ArgumentParser(
        prog="simulate_policy.py", description="Read-only IAM policy simulation and Access Analyzer validation of "
        "docs/iam/*.json. Creates and changes nothing. Exit code 0 only when everything is as expected."
    ).parse_args(argv)
    try:
        iam = boto3.client("iam", config=config.boto_config()) if iam is None else iam
        analyzer = boto3.client("accessanalyzer", config=config.boto_config()) if analyzer is None else analyzer
    except BotoCoreError as exc:
        print(_failure("The AWS clients", "The policy simulator", exc))
        return 1
    clean = True
    print("EPICENTRE policy simulator (read-only: nothing is created or changed; "
          "account id and guardrail id are masked)")
    print(f"region {config.REGION}  policy docs/iam/{RUNTIME_POLICY.name}  call iam:SimulateCustomPolicy\n")
    try:
        rows = simulate(iam, concrete(RUNTIME_POLICY.read_text(encoding="utf-8")), probes())
    except (ClientError, BotoCoreError) as exc:
        print(_failure("iam:SimulateCustomPolicy", "The policy simulator", exc))
        clean = False
    else:
        print(render_table(rows))
        good = sum(row["ok"] for row in rows)
        print(f"\nSimulation: {good} / {len(rows)} decisions as expected.")
        clean = good == len(rows)
    for path in (RUNTIME_POLICY, ADMIN_POLICY):
        print("\nAccess Analyzer validate-policy (access-analyzer:ValidatePolicy, identity policy) "
              f"on docs/iam/{path.name}")
        try:
            findings = validate(analyzer, concrete(path.read_text(encoding="utf-8")))
        except (ClientError, BotoCoreError) as exc:
            print(_failure("access-analyzer:ValidatePolicy", "The policy validator", exc))
            clean = False
            continue
        for f in findings:
            print(f"  {f['type']}  {f['code']}  {f['where']}  {f['detail']}")
        blocking = [f for f in findings if f["type"] in BLOCKING_FINDINGS]
        print(f"  {len(findings)} finding(s), {len(blocking)} blocking (ERROR or SECURITY_WARNING).")
        clean = clean and not blocking
    print("\n" + ("All decisions as expected and no blocking finding." if clean else "Not clean: see the lines above."))
    return 0 if clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
