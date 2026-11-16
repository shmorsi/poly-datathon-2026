"""EPICENTRE runtime guardrail: one Bedrock ApplyGuardrail call on the way in and one on the way out (spec section 7).

    apply_guardrail(text, source, facts=None, query=None, *, client=None) -> dict

INPUT checks what the investor typed, the one free-text field: the narrow denied topic (a request to tell a specific
person to buy, sell or hold a specific real security), prompt attacks and personal data. OUTPUT scores the explanation
against what it was written from, in the same single call: contextual grounding and relevance (flag, never block), the
denied topic and PII (detect only) and, when the guardrail has a policy attached, the Automated Reasoning finding. The
grounding source is plain sentences (`grounding_source`: the explainer's verdict and failed rules, then one sentence
per facts row), never raw JSON: the JSON scored clean, receipt-verified explanations 0.06 to 0.13 against 0.70.
The guardrail id and version come from EPICENTRE_GUARDRAIL_ID / EPICENTRE_GUARDRAIL_VERSION, never from code.

The result always has the same 13 keys: the ledger's twelve and the additive `pii_types` (entity types only; the
matched text is the user's personal data and is never copied), plus `request_id` whenever AWS returned one (the
response's or the AWS error's ResponseMetadata.RequestId; ruling R26). An expected failure (keys expired, access denied,
throttling, timeout, no configuration) comes back as one plain `error` sentence; only a wrong `source` raises.

Contract for the pipeline (ledger sections 8, 10 and 15):
  * An INPUT result with `error` means the text must not reach any model: keyword fallback and the deterministic
    answer. `blocked` stays False when `error` is set, so the pipeline must read `error`, not `blocked` alone.
  * An OUTPUT result with `error`, or with `grounding.detected` true, is shown flagged in VERIFY and counts as one
    named defect for the single re-ask. So does `topic_hit` on OUTPUT; if it persists after the re-ask the explanation
    is withheld with one plain sentence and the numbers stay.
  * Check the draft that is actually shown: the final draft after any re-ask.

Nothing here prints or logs the text, the facts, the question or the response.
Sources: spec section 7 (Guardrail) and section 11, ledger section 15, plan B Task 7.
"""
import math
import os
import re
import threading
import time

import boto3
from botocore.exceptions import (BotoCoreError, ClientError, ConnectTimeoutError, EndpointConnectionError,
                                 ReadTimeoutError)

import config
import verify  # fmt_number: the source writes each value the way the debrief and the receipt write it
from scripts.check_bedrock import _redact  # the one place that strips ARNs, access key ids and account ids
from scripts.create_guardrail import DECOY_TOPIC_NAMES  # detect-only input topics: never a denied-topic hit

SOURCES = ("INPUT", "OUTPUT")
NOT_CONFIGURED = "The safety check is not configured (EPICENTRE_GUARDRAIL_ID / _VERSION)."
NO_FACTS = "No facts were computed for this answer."
# Automated Reasoning finding kinds, worst first; a kind this list does not know ranks worse than all of them
_AR_ORDER = ("invalid", "impossible", "satisfiable", "translationAmbiguous", "tooComplex", "noTranslations", "valid")
_AR_RULES = {"invalid": "contradictingRules", "impossible": "contradictingRules", "valid": "supportingRules"}
_ACTED = ("BLOCKED", "ANONYMIZED")  # an action that was taken: some responses carry the action without `detected`
# boto3's default session is not thread-safe and the server runs the pipeline in threads: build clients one at a time
_client_lock = threading.Lock()


def _result(**fields) -> dict:
    """The one result shape: every key is always present, a path sets only what it knows."""
    out = {"action": "NONE", "blocked": False, "topic_hit": False, "prompt_attack": False, "pii_hit": False,
           "pii_types": [], "grounding": None, "relevance": None, "automated_reasoning": None, "latency_ms": 0,
           "usage": None, "message": None, "error": None}
    out.update(fields)
    return out


def _request_id(resp) -> dict:
    """{"request_id": ...} when AWS returned one (ResponseMetadata.RequestId of a response or of a ClientError's), else
    {}: the 13 keys stay as they are and `.get("request_id")` reads None (D Task 6b, ruling R26). Never raises."""
    meta = resp.get("ResponseMetadata") if isinstance(resp, dict) else None
    rid = meta.get("RequestId") if isinstance(meta, dict) else None
    return {"request_id": rid} if isinstance(rid, str) and rid else {}


def _hit(entry: dict) -> bool:
    """A policy entry that fired: detected, or its blocking / masking action was taken."""
    return bool(entry.get("detected")) or entry.get("action") in _ACTED


def _entries(assessments: list, policy: str, key: str) -> list:
    """Every entry of one policy list (topics, filters, piiEntities, findings) across all assessment objects."""
    return [entry for a in assessments for entry in (a.get(policy) or {}).get(key) or []]


def _score(filters: list, kind: str):
    """{"score", "threshold", "detected"} of the contextual grounding filter of this type (the lowest score wins)."""
    found = [f for f in filters if f.get("type") == kind]
    if not found:
        return None
    worst = min(found, key=lambda f: f.get("score") or 0.0)
    return {"score": worst.get("score"), "threshold": worst.get("threshold"),
            "detected": any(bool(f.get("detected")) for f in found)}


def _kind(finding: dict) -> str:
    """The one key of an Automated Reasoning finding (a tagged union)."""
    return next((k for k in _AR_ORDER if k in finding), None) or next(iter(finding), "unknown")


def _rank(kind: str) -> int:
    return _AR_ORDER.index(kind) if kind in _AR_ORDER else -1


def _reasoning(findings: list):
    """None without findings, else the worst finding, the rules it names (identifiers only) and how many there were."""
    if not findings:
        return None
    kinds = [_kind(f) for f in findings]
    worst = min(kinds, key=_rank)
    rules = [rule.get("identifier") for f, k in zip(findings, kinds) if k == worst
             for rule in ((f.get(k) or {}).get(_AR_RULES.get(k, "")) or [])]
    return {"finding": re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", worst).upper(),
            "rules": list(dict.fromkeys(r for r in rules if r)), "n_findings": len(findings)}


def _parse(resp: dict) -> dict:
    """The ledger fields of one ApplyGuardrail response (botocore 1.44.3 shape); every assessment entry is merged."""
    assessments = [a for a in resp.get("assessments") or [] if isinstance(a, dict)]
    action = resp.get("action") or "NONE"
    blocked = action == "GUARDRAIL_INTERVENED"
    outputs = resp.get("outputs") or []
    pii = [e for e in _entries(assessments, "sensitiveInformationPolicy", "piiEntities") if _hit(e)]
    grounding = _entries(assessments, "contextualGroundingPolicy", "filters")
    return {
        "action": action,
        "blocked": blocked,
        "topic_hit": any(_hit(t) for t in _entries(assessments, "topicPolicy", "topics")
                         if t.get("name") not in DECOY_TOPIC_NAMES),
        "prompt_attack": any(f.get("type") == "PROMPT_ATTACK" and _hit(f)
                             for f in _entries(assessments, "contentPolicy", "filters")),
        "pii_hit": bool(pii),
        "pii_types": sorted({e["type"] for e in pii if e.get("type")}),  # the type, never the `match` text
        "grounding": _score(grounding, "GROUNDING"),
        "relevance": _score(grounding, "RELEVANCE"),
        "automated_reasoning": _reasoning(_entries(assessments, "automatedReasoningPolicy", "findings")),
        "usage": dict(resp["usage"]) if resp.get("usage") else None,
        "message": outputs[0].get("text") if blocked and outputs else None,
    }


def _t_order(tid) -> tuple:
    """T-number order (T2 before T10); any other key after them, by name."""
    m = re.fullmatch(r"T(\d+)", str(tid))
    return (0, int(m.group(1)), "") if m else (1, 0, str(tid))


def _one_line(x) -> str:
    return " ".join(str(x).split())


def _value_words(value, unit) -> str:
    """The value as the debrief writes it (verify.fmt_number: "34.5 %", "$207,146", "416 days", "6"). A negative pct or
    pp value reads "a fall of 34.5 %" and a negative CAD value "a loss of $207,146": the direction is a word, as in the
    explanation ("fell 34.5 %"), never a minus sign the grounding check has to match against "fell"."""
    if not (isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)):
        return _one_line(value)
    if value < 0 and unit in ("pct", "pp", "CAD"):
        return ("a loss of " if unit == "CAD" else "a fall of ") + verify.fmt_number(abs(value), unit)
    return verify.fmt_number(value, unit)


def _row_sentence(tid, row) -> str:
    """One facts row as one sentence, "<label>: <value> (T#, kind).", or "<label> <value>" after a label that ends
    in "to" ("The move: NVDA set to 40.0 % (T27, fiction)."). A row that is not a dict is said as it is."""
    if not isinstance(row, dict):
        return f"{tid}: {_one_line(row)}."
    label = _one_line(row.get("label") or "").rstrip(" :.")
    kind = _one_line(row.get("kind") or "")
    ref = f" ({tid}, {kind})" if label and kind else f" ({tid})" if label else f" ({kind})" if kind else ""
    label = label or str(tid)
    if row.get("value") is None:
        return f"{label}{ref}."
    joiner = " " if re.search(r"\bto$", label) else ": "
    return f"{label}{joiner}{_value_words(row.get('value'), row.get('unit'))}{ref}."


def _context_sentences(context) -> list:
    """The explainer's own context (pipeline._context) as sentences: the frame, the verdict, the limits that broke in
    the order checked (the first decided the verdict) and each caveat. Other keys (goal, question, intent) are not read:
    the question goes in the `query` block."""
    c = context if isinstance(context, dict) else {}
    out = []
    if c.get("as_of"):
        out.append(f"These results replay real market history up to the decision date, {_one_line(c['as_of'])}. "
                   "This already happened; it is not a forecast.")
    verdict = _one_line(c.get("verdict_words") or "")
    if verdict:
        out.append(f"The verdict, computed by code: {verdict}.")
    failed = [_one_line(f) for f in c.get("failed_rules") or [] if _one_line(f)]
    if failed:
        out.append(f"The limits that broke, in the order checked: {', '.join(failed)}. "
                   f"The first one, {failed[0]}, was the check that decided the verdict.")
    elif verdict and verdict != verify.VERDICT_WORDS[None]:
        out.append("None of your limits broke.")
    out += [f"Caveat: {_one_line(x).rstrip('.')}." for x in c.get("caveats") or [] if _one_line(x)]
    out += [f"A warning level was crossed, {_one_line(w)}; a warning is not a limit." for w in c.get("warnings") or []
            if _one_line(w)]                       # Sun Nov 15: the lead names it, so the source must say it too
    return out


def grounding_source(facts, context=None) -> str:
    """The OUTPUT check's grounding source: plain sentences, never raw JSON (lane gr, Sun Nov 15; measured live in
    docs/eval_results.md section 8: the facts JSON scored clean, receipt-verified explanations 0.06 to 0.13 against
    0.70). `context` (optional) is the explainer's context (pipeline._context: as_of, verdict_words, failed_rules,
    caveats): its sentences come first. Then one sentence per facts row in T order, "<label>: <value> (T#, kind).",
    the value written the way the debrief and the receipt write it. No rows at all is said in one sentence, so the
    block still goes out and an answer with numbers is scored ungrounded, never skipped."""
    rows = facts if isinstance(facts, dict) else {}
    sentences = _context_sentences(context) + [_row_sentence(t, rows[t]) for t in sorted(rows, key=_t_order)]
    return " ".join(sentences + ([] if rows else [NO_FACTS]))


def _content(text: str, source: str, facts, query) -> list:
    """The request's content blocks. INPUT: the text, whole. OUTPUT: the facts as plain sentences (grounding_source;
    a str is used as is) as the grounding source and the question as the query (each only when given), then the text
    as the guarded content, cut to what Bedrock scores."""
    if source == "INPUT":
        return [{"text": {"text": text}}]
    blocks = []
    if facts is not None:
        grounding = facts if isinstance(facts, str) else grounding_source(facts)
        grounding = grounding[:config.GROUNDING_MAX_CHARS]
        if grounding.strip():
            blocks.append({"text": {"text": grounding, "qualifiers": ["grounding_source"]}})
    question = ("" if query is None else str(query))[:config.QUERY_MAX_CHARS]
    if question.strip():
        blocks.append({"text": {"text": question, "qualifiers": ["query"]}})
    blocks.append({"text": {"text": text[:config.GUARD_CONTENT_MAX_CHARS], "qualifiers": ["guard_content"]}})
    return blocks


def _error_sentence(exc: Exception) -> str:
    """One plain sentence for an expected AWS failure. Never the AWS message: it can name a caller or a resource."""
    code = str((exc.response.get("Error") or {}).get("Code") or "") if isinstance(exc, ClientError) else ""
    code = code or type(exc).__name__
    if code.startswith(("ExpiredToken", "UnrecognizedClient")):
        return "AWS keys expired: the safety check could not run."
    if code.startswith("AccessDenied"):
        return "The safety check was denied by AWS permissions."
    if code.startswith("Throttl"):
        return "The safety check is busy (throttled); try again in a moment."
    if isinstance(exc, (ReadTimeoutError, ConnectTimeoutError, EndpointConnectionError)):
        return "The safety check timed out."
    return _redact(f"The safety check could not run ({code}).")


def _ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def apply_guardrail(text, source, facts=None, query=None, *, client=None) -> dict:
    """Check `text` with the guardrail; `source` is "INPUT" (the question) or "OUTPUT" (the explanation).

    OUTPUT also takes `facts` (the facts rows the explanation was written from: a dict, sent as `grounding_source`
    sentences, or a str used as is, such as `grounding_source(facts, context)`) and `query` (the question it answers);
    without them only the text is scored. Returns the dict
    described in the module docstring. No call is made for blank text (nothing to check, action NONE), for INPUT
    over config.INPUT_MAX_CHARS (refused whole, action TOO_LONG: cutting would let the tail through unchecked) or
    without an id and version in the environment. `client` defaults to a bedrock-runtime client built per call.
    """
    if source not in SOURCES:
        raise ValueError(f"source must be one of {SOURCES}, got {source!r}")
    text = "" if text is None else str(text)
    if not text.strip():
        return _result()
    if source == "INPUT" and len(text) > config.INPUT_MAX_CHARS:
        return _result(action="TOO_LONG", blocked=True, message=(
            f"That text is too long to check (over {config.INPUT_MAX_CHARS:,} characters). Please shorten it."))
    guardrail_id = (os.environ.get(config.ENV_GUARDRAIL_ID) or "").strip()
    version = (os.environ.get(config.ENV_GUARDRAIL_VERSION) or "").strip()
    if not (guardrail_id and version):
        return _result(action="ERROR", error=NOT_CONFIGURED)
    content = _content(text, source, facts, query)
    started = None
    try:
        if client is None:  # inside the try: a missing profile or keys raise here; latency below is the call alone
            with _client_lock:
                client = boto3.client("bedrock-runtime", config=config.boto_config())
        started = time.perf_counter()
        resp = client.apply_guardrail(
            guardrailIdentifier=guardrail_id, guardrailVersion=version, source=source, content=content,
            outputScope="FULL" if source == "OUTPUT" else "INTERVENTIONS")  # FULL: passing scores come back too
    except (ClientError, BotoCoreError) as exc:
        return _result(action="ERROR", error=_error_sentence(exc), latency_ms=0 if started is None else _ms(started),
                       **_request_id(getattr(exc, "response", None)))
    return _result(latency_ms=_ms(started), **_parse(resp), **_request_id(resp))
