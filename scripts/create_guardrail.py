"""EPICENTRE guardrail: create or update the one Bedrock guardrail, idempotent (spec section 7, section 11).

    python scripts/create_guardrail.py                  # find, then create or update (DRAFT); wait for READY
    python scripts/create_guardrail.py --detect         # calibration: every action NONE, assessments still report
    python scripts/create_guardrail.py --publish        # the numbered version at the Sun 14:00 freeze (waits for READY)
    python scripts/create_guardrail.py --with-ar ARN    # attach an Automated Reasoning policy version (P1)
    python scripts/create_guardrail.py --print-ar-doc   # print the rules text for that policy; no AWS call

Run it in a terminal that holds your AWS keys. It prints the guardrail id and version as two export lines
(identifiers, not secrets) and never a credential, an account id or an ARN. Re-running is safe: the script
declares the whole DRAFT configuration, so repeat the flags you want to keep (--with-ar in particular).
Creating or updating the guardrail is an AWS change: the lead approves it first.
Sources: spec section 7 (Guardrail), section 11 (AWS steps), plan B Task 3.
"""
import argparse
import time

try:
    from scripts import check_bedrock  # imported as a package module (pytest, python -m scripts.create_guardrail)
except ModuleNotFoundError:  # `python scripts/create_guardrail.py`: scripts/ leads sys.path, not the repo root
    import check_bedrock  # importing it puts the repo root on sys.path: the one bootstrap, reused

import boto3  # noqa: E402
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError  # noqa: E402

import config  # noqa: E402

DESCRIPTION = "EPICENTRE: blocks trade instructions, prompt attacks and personal data; scores grounding"
# narrow on purpose (pitfall 2): a generic "investment advice" topic blocks our own demo questions. B Task 7 fix,
# tuned live on 66 scripted and benign eval inputs and 8 must-block rows (all passed / all blocked, twice in a row):
# the classifier reads the name ("PersonalTradeInstruction" blocked the bare move "add 10 % SPY"), every example
# widened it, and no wording of a lone topic cleared every what-if. So the input topic asks for the answer itself,
# the reply side is its own output-only topic, and four detect-only input topics describe the benign questions.
TOPIC_NAME = "BuySellHoldVerdictRequest"
TOPIC_DEFINITION = ("A person asking the assistant a question whose answer is buy, sell or hold for a real trade in a "
                    "specific security.")
TOPIC_EXAMPLES = ()
REPLY_TOPIC_NAME = "BuySellHoldVerdictReply"  # OUTPUT only, action NONE: flags a reply that tells someone what to do
REPLY_TOPIC_DEFINITION = "A reply that tells a person to buy, sell or hold a specific real security now."
# Detect-only input topics (action NONE, never block, never on OUTPUT). The classifier files each input under one
# topic, so a what-if lands here instead of under the denied topic. guardrail.py never counts them as a topic hit.
DECOY_TOPICS = (
    ("WhatIfReplayQuestion", "A person asking what a hypothetical change to their portfolio, or a market shock, "
                             "would have done to it, replayed on past market history."),
    ("PortfolioFitQuestion", "A person asking whether their portfolio, or a change to it, fits the goals, horizon "
                             "and limits they set."),
    ("PortfolioChangeNote", "A short note naming a hypothetical change to a portfolio, such as adding a percentage "
                            "of a fund or replacing one holding with another."),
    ("VagueQuestion", "A short, vague question that names no security, amount, event or goal, so what it asks is "
                      "unclear."),
)
DECOY_TOPIC_NAMES = frozenset(name for name, _ in DECOY_TOPICS)
PII_TYPES = ("CA_SOCIAL_INSURANCE_NUMBER", "CREDIT_DEBIT_CARD_NUMBER", "INTERNATIONAL_BANK_ACCOUNT_NUMBER",
             "EMAIL", "PHONE")
# shown to the user on a block, so red gate 1 applies: no buy / sell / hold / should anywhere in it (a test pins this)
BLOCKED_INPUT = ("EPICENTRE replays a move against the limits you set; it doesn't tell anyone what to do with a "
                 "specific security, and it doesn't take personal data. "
                 "Try: \"What if I put 40 % in NVIDIA and the tariff war flares up again?\"")
BLOCKED_OUTPUT = ("This explanation was withheld by the safety check. "
                  "The verdict and charts come straight from the data.")
AR_CONFIDENCE = 0.8  # automatedReasoningPolicyConfig.confidenceThreshold (0 to 1)
VERSION_DESCRIPTION = "freeze Sun 14:00"
POLL_SECONDS = 2  # botocore 1.44.3 has no waiter for guardrails: we poll get_guardrail
WAIT_SECONDS = 60


class GuardrailFailed(RuntimeError):
    """The guardrail ended FAILED, or was not READY within WAIT_SECONDS; the message says why."""


def guardrail_config(detect: bool = False, ar_policy_arn: str | None = None) -> dict:
    """The keyword arguments shared by create_guardrail and update_guardrail (a fresh dict on every call).

    Input: the narrow denied topic, PROMPT_ATTACK HIGH and five PII types, all BLOCK, plus the detect-only
    DECOY_TOPICS (NONE). Output: contextual grounding and relevance at 0.7 with action NONE (flag, never block),
    the reply topic and PII start at NONE.
    detect=True sets every blocking action to NONE for calibration; the assessments still report detected.
    """
    act = "NONE" if detect else "BLOCK"
    cfg = {
        "name": config.GUARDRAIL_NAME,
        "description": DESCRIPTION,
        "crossRegionConfig": {"guardrailProfileIdentifier": config.GUARDRAIL_PROFILE},
        "topicPolicyConfig": {
            "tierConfig": {"tierName": "STANDARD"},
            "topicsConfig": [  # the order is part of the tuned configuration (the AWS docs: order can change outcomes)
                {"name": TOPIC_NAME, "type": "DENY", "definition": TOPIC_DEFINITION, "examples": list(TOPIC_EXAMPLES),
                 "inputAction": act, "inputEnabled": True, "outputAction": "NONE", "outputEnabled": False},
                {"name": REPLY_TOPIC_NAME, "type": "DENY", "definition": REPLY_TOPIC_DEFINITION, "examples": [],
                 "inputAction": "NONE", "inputEnabled": False, "outputAction": "NONE", "outputEnabled": True},
                *({"name": name, "type": "DENY", "definition": text, "examples": [], "inputAction": "NONE",
                   "inputEnabled": True, "outputAction": "NONE", "outputEnabled": False} for name, text in DECOY_TOPICS)]},
        "contentPolicyConfig": {
            "tierConfig": {"tierName": "STANDARD"},
            "filtersConfig": [{
                "type": "PROMPT_ATTACK", "inputStrength": "HIGH", "outputStrength": "NONE",
                "inputAction": act, "inputEnabled": True, "outputEnabled": False}]},
        "sensitiveInformationPolicyConfig": {"piiEntitiesConfig": [
            {"type": t, "action": act, "inputAction": act, "inputEnabled": True,
             "outputAction": "NONE", "outputEnabled": True} for t in PII_TYPES]},
        "contextualGroundingPolicyConfig": {"filtersConfig": [  # no tierConfig: the default tier is kept
            {"type": "GROUNDING", "threshold": config.GROUNDING_THRESHOLD, "action": "NONE", "enabled": True},
            {"type": "RELEVANCE", "threshold": config.RELEVANCE_THRESHOLD, "action": "NONE", "enabled": True}]},
        "blockedInputMessaging": BLOCKED_INPUT,
        "blockedOutputsMessaging": BLOCKED_OUTPUT,
    }
    if ar_policy_arn:
        cfg["automatedReasoningPolicyConfig"] = {"policies": [ar_policy_arn], "confidenceThreshold": AR_CONFIDENCE}
    return cfg


# ---- the rules text for the Automated Reasoning policy (spec section 5; built once in the Bedrock console) ----

MIN_SHOCK_EPISODES = 2  # spec section 5 numbers that config.py does not carry
PRICE_GAP_DAYS = 3
_BANDS = tuple(config.DEFAULT_LIMITS)  # high, moderate, low
_REACTION_WORDS = {"sold": "sold", "held": "stayed invested", "bought": "bought more"}


def _pct(value: float) -> str:
    """0.225 -> '22.5 %' (the product writes a space before the percent sign; limits are stored as signed fractions)."""
    return f"{abs(value) * 100:g} %"


def _per_band(values: dict) -> str:
    """{'high': 0.45, 'moderate': 0.25, 'low': 0.15} -> '45 % for a high band, 25 % for a moderate band and ...'."""
    parts = [f"{_pct(values[band])} for a {band} band" for band in _BANDS]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def ar_policy_document() -> str:
    """The section 5 rules as plain numbered sentences, rendered from config (no buy / sell / hold words).

    Upload it as a .txt source when you create the Automated Reasoning policy in the Bedrock console. One
    sentence per rule id in config.RULE_IDS order, then the verdict rule. Every number comes from
    config.DEFAULT_LIMITS / DEFAULT_THRESHOLDS, so the policy cannot drift from the checklist.
    """
    lim, th, words = config.DEFAULT_LIMITS, config.DEFAULT_THRESHOLDS, config.VERDICT_WORDS

    def per(key: str) -> str:
        return _per_band({band: lim[band][key] for band in _BANDS})

    floor = {band: lim[band]["max_drawdown"] for band in _BANDS}
    stress = {band: floor[band] * th["scenario_stress_fraction"] for band in _BANDS}
    reaction = ", ".join(f"{_REACTION_WORDS[k]} gives {v}" for k, v in config.REACTION_TO_RISK.items())
    intro = [
        "EPICENTRE checklist rules. They are documented assumptions, not regulation, and history is evidence, "
        "not a forecast.",
        f"The tolerance band comes from the answer to \"In 2022, when markets fell, you\": {reaction}; it can also "
        "be picked directly.",
        f"A check fails only when its value is strictly beyond its limit after rounding to {th['rounding_pp']:g} "
        "percentage point; a value exactly at the limit passes; failures caused by the same position count once.",
    ]
    sentences = {
        "max_drawdown": (
            f"Hard rule, the floor: the floor is a drop of {_per_band(floor)}, and the floor is the stricter of the "
            "band floor and the capacity floor (largest absorbable loss divided by the portfolio amount); the rule "
            "fails when the worst drop of the portfolio from the period start to the as-of date, at constant "
            "weights, is strictly beyond the floor."),
        "scenario_stress": (
            "Soft rule, the shock check: the worst drop among the known, clean shock episodes of the question's "
            f"families must be no larger than {_pct(th['scenario_stress_fraction'])} of the floor, which is a drop "
            f"of {_per_band(stress)}, and the rule fails when that drop is larger; it is only a warning, never a "
            f"pass or a fail, when those families have fewer than {MIN_SHOCK_EPISODES} known, clean episodes at the "
            "as-of date."),
        "single_stock": (
            "Soft rule, one company: its direct position plus its share inside funds may be at most this share of "
            f"the portfolio: {per('max_single_stock')}."),
        "sector": (
            "Soft rule, one sector: counted through funds, for equities only, a sector may be at most this share of "
            f"the whole portfolio: {per('max_sector')}; bonds, gold and crypto are asset classes, not sectors."),
        "crypto": (
            "Soft rule, crypto: the crypto share may be at most this share of the portfolio: "
            f"{per('max_crypto')}; when the investor said no to crypto, it is a preference rule instead."),
        "esg_direct": (
            "Preference rule, values: when the investor asked for values screening, owning an excluded company "
            "directly (sector Energy, or a company on the ESG flags list) fails the rule."),
        "esg_indirect": (
            "Warning, values inside funds: when the investor asked for values screening and the excluded names "
            f"inside funds reach {_pct(th['esg_indirect_warn'])} of the portfolio or more, the rule warns."),
        "risk_concentration": (
            "Warning, risk concentration: when one line carries more than "
            f"{_pct(th['risk_share_warn'])} of the portfolio's total risk, the rule warns."),
        "recovery": (
            "Warning, recovery: when the calendar days from the trough back to the previous peak exceed the horizon "
            f"in years times 365 times {th['recovery_fraction_of_horizon']:g}, and only if the drop is worse than "
            f"{_pct(th['scenario_stress_fraction'])} of the floor, the rule warns."),
        "short_horizon": (
            f"Warning, short horizon: when the money is needed in fewer than {th['short_horizon_years']} years, "
            "the rule warns."),
        "missing_data": (
            f"Warning, missing data: when an owned asset has a price gap of more than {PRICE_GAP_DAYS} days, "
            "the rule warns."),
    }
    if set(sentences) != set(config.RULE_IDS):
        drift = sorted(set(sentences) ^ set(config.RULE_IDS))
        raise ValueError(f"ar_policy_document and config.RULE_IDS disagree on: {drift}")
    verdict = (f"If any hard rule fails the verdict is {words['Incompatible']}; otherwise any soft or preference "
               f"failure, or two or more warnings, gives {words['Tension']}; otherwise {words['Compatible']}.")
    numbered = [f"{i}. {text}" for i, text in enumerate([*(sentences[r] for r in config.RULE_IDS), verdict], start=1)]
    closing = f"Without limits there is no verdict and the answer is {words[None]}."
    return "\n".join([*intro, "", *numbered, "", closing]) + "\n"


# ---- find, create or update, wait for READY, optionally publish a numbered version ----

def find_guardrail(client) -> str | None:
    """The id of our guardrail. The current name wins; else the first one still carrying a legacy name (it is
    then renamed in place by update_guardrail, so no duplicate resource); None when there is neither."""
    legacy = None
    for page in client.get_paginator("list_guardrails").paginate():  # no identifier: one DRAFT entry per guardrail
        for item in page.get("guardrails", []):
            if item.get("name") == config.GUARDRAIL_NAME:
                return item["id"]
            if legacy is None and item.get("name") in config.LEGACY_GUARDRAIL_NAMES:
                legacy = item["id"]
    return legacy


def _wait_until_ready(client, guardrail_id: str, sleep=time.sleep, version: str = "DRAFT") -> None:
    """Poll a guardrail version (the DRAFT, or a numbered one) every POLL_SECONDS until READY.

    GuardrailFailed on FAILED, or after WAIT_SECONDS of waiting. A new numbered version passes through VERSIONING
    first; the ids it prints must not be used before it is READY."""
    what = "Guardrail" if version == "DRAFT" else f"Guardrail version {version}"
    waited = 0
    while True:
        got = client.get_guardrail(guardrailIdentifier=guardrail_id, guardrailVersion=version)
        status = got.get("status")
        if status == "READY":
            return
        if status == "FAILED":
            reasons = "; ".join(str(r) for r in got.get("statusReasons") or []) or "no reason given"
            raise GuardrailFailed(f"{what} FAILED: {check_bedrock._redact(reasons)}")
        if waited >= WAIT_SECONDS:
            raise GuardrailFailed(f"{what} was not READY after {WAIT_SECONDS} s (last status {status}).")
        sleep(POLL_SECONDS)
        waited += POLL_SECONDS


def ensure_guardrail(client, detect: bool = False, publish: bool = False, ar_policy_arn: str | None = None,
                     *, sleep=time.sleep) -> dict:
    """Create the guardrail, or update it in place (this also renames a legacy-named one), wait for READY.

    Returns {"id", "version", "action": "created" | "updated"}. version is "DRAFT" unless publish, which
    freezes the DRAFT as a numbered version (the Sun 14:00 freeze) and returns that number as a string.
    `sleep` is only a seam for the tests.
    """
    cfg = guardrail_config(detect=detect, ar_policy_arn=ar_policy_arn)
    found = find_guardrail(client)
    if found:
        client.update_guardrail(guardrailIdentifier=found, **cfg)
        guardrail_id, action = found, "updated"
    else:
        guardrail_id, action = client.create_guardrail(**cfg)["guardrailId"], "created"
    _wait_until_ready(client, guardrail_id, sleep)
    version = "DRAFT"
    if publish:
        made = client.create_guardrail_version(guardrailIdentifier=guardrail_id, description=VERSION_DESCRIPTION)
        version = made["version"]
        _wait_until_ready(client, guardrail_id, sleep, version)  # the export line must name a version that is READY
    return {"id": guardrail_id, "version": version, "action": action}


# ---- command line ----

def _hint(code: str, message: str) -> str:
    if code == "AccessDeniedException":  # plan B Task 3 decision: stop, do not look for a workaround
        return ("Stop and tell the lead: this role may not create or update the guardrail "
                "(docs/iam/admin-policy.json lists the actions the admin role needs).")
    if code.startswith(("ExpiredToken", "UnrecognizedClient")):
        return check_bedrock.HINT_EXPIRED
    return check_bedrock._redact(message) or "-"  # ValidationException: the message names the rejected field


def _failure(error: str, hint: str, request_id: str | None = None) -> int:
    lines = [f"error        {error}", f"hint         {hint}"]
    if request_id:
        lines.append(f"RequestId    {request_id}")
    print("\n".join(lines))
    return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="create_guardrail.py", description="Create or update the EPICENTRE Bedrock guardrail (idempotent: find, "
        "then create or update the DRAFT, wait for READY). Prints the id and version as two export lines.")
    parser.add_argument("--detect", action="store_true",
                        help="calibration: every blocking action NONE (the assessments still report detected)")
    parser.add_argument("--publish", action="store_true",
                        help="also create the numbered version (the Sun 14:00 freeze)")
    parser.add_argument("--with-ar", metavar="ARN", default=None,
                        help="attach this Automated Reasoning policy version ARN (P1; built once in the console)")
    parser.add_argument("--print-ar-doc", action="store_true",
                        help="print the rules text for the Automated Reasoning policy and exit (no AWS call)")
    args = parser.parse_args(argv)
    if args.print_ar_doc:
        print(ar_policy_document(), end="")
        return 0
    try:
        client = boto3.client("bedrock", config=config.boto_config())  # the control plane, not bedrock-runtime
        result = ensure_guardrail(client, detect=args.detect, publish=args.publish, ar_policy_arn=args.with_ar)
    except GuardrailFailed as exc:
        return _failure("GuardrailFailed", str(exc))
    except ClientError as exc:
        error = exc.response.get("Error", {})
        code = error.get("Code") or type(exc).__name__
        return _failure(code, _hint(code, error.get("Message") or ""),
                        exc.response.get("ResponseMetadata", {}).get("RequestId"))
    except NoCredentialsError as exc:
        return _failure(type(exc).__name__, check_bedrock.HINT_NO_CREDENTIALS)
    except BotoCoreError as exc:
        return _failure(type(exc).__name__, check_bedrock._redact(str(exc)) or "-")
    print("\n".join([
        "EPICENTRE - guardrail",
        f"region       {config.REGION}",
        f"guardrail    {config.GUARDRAIL_NAME} ({result['action']})",
        f"mode         {'detect (every blocking action NONE)' if args.detect else 'block'}",
        f"automated reasoning  {'attached' if args.with_ar else 'not attached'}",
        f"version      {result['version']}",
        f"export {config.ENV_GUARDRAIL_ID}={result['id']}",
        f"export {config.ENV_GUARDRAIL_VERSION}={result['version']}",
    ]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
