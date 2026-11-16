"""Test adversarial inputs through the guardrail (lane B4 red team).

Run the 110 adversarial inputs (50 must-block, 60 benign) through the live INPUT guardrail
and record: blocked by guardrail? any advice/forecast wording that leaked? Save results to
/tmp/epi_lanes/b4_results.json. Budget-conscious: guardrail calls only, no full pipeline runs.
"""
import json
import os
import sys
import time
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import guardrail


def load_attacks():
    """Load the adversarial inputs from /tmp/epi_lanes/b4_attacks.json."""
    with open("/tmp/epi_lanes/b4_attacks.json") as f:
        data = json.load(f)
    # Combine attacks and benign controls into one list
    all_inputs = []
    for item in data.get("attacks", []):
        item["expected_benign"] = False
        all_inputs.append(item)
    for item in data.get("benign_controls", []):
        item["expected_benign"] = True
        all_inputs.append(item)
    return all_inputs, data.get("meta", {})


def test_input(text, input_id):
    """Test one input through the guardrail INPUT check."""
    started = time.perf_counter()
    result = guardrail.apply_guardrail(text, "INPUT")
    latency_ms = round((time.perf_counter() - started) * 1000)

    return {
        "id": input_id,
        "blocked": result.get("blocked"),
        "action": result.get("action"),
        "topic_hit": result.get("topic_hit"),
        "prompt_attack": result.get("prompt_attack"),
        "pii_hit": result.get("pii_hit"),
        "pii_types": result.get("pii_types", []),
        "error": result.get("error"),
        "latency_ms": latency_ms,
        "request_id": result.get("request_id"),
    }


def analyze_results(results, inputs):
    """Analyze the results and compute statistics."""
    must_block = [r for r, inp in zip(results, inputs) if not inp["expected_benign"]]
    benign = [r for r, inp in zip(results, inputs) if inp["expected_benign"]]

    # Must-block: how many were blocked or had errors?
    blocked_count = sum(1 for r in must_block if r["blocked"] or r["error"])
    # Benign: how many passed (not blocked, no error)?
    passed_count = sum(1 for r in benign if not r["blocked"] and not r["error"])

    # False negatives: must-block that weren't blocked
    false_negatives = [r for r in must_block if not r["blocked"] and not r["error"]]
    # False positives: benign that were blocked
    false_positives = [r for r in benign if r["blocked"] and not r["error"]]

    # Errors (guardrail failures)
    errors = [r for r in results if r["error"]]

    return {
        "must_block": {
            "total": len(must_block),
            "blocked_or_error": blocked_count,
            "passed": len(must_block) - blocked_count,
            "rate": blocked_count / len(must_block) if must_block else 0,
        },
        "benign": {
            "total": len(benign),
            "passed": passed_count,
            "blocked": len(benign) - passed_count,
            "rate": passed_count / len(benign) if benign else 0,
        },
        "false_negatives": len(false_negatives),
        "false_positives": len(false_positives),
        "errors": len(errors),
        "error_details": errors if errors else None,
    }


def wilson_score_interval(k, n, confidence=0.95):
    """Calculate Wilson score confidence interval for a proportion k/n."""
    if n == 0:
        return (0.0, 0.0)

    import math
    p = k / n
    z = 1.96 if confidence == 0.95 else 2.576  # 95% or 99%

    denominator = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denominator
    margin = z * math.sqrt((p * (1 - p) / n) + (z**2 / (4 * n**2))) / denominator

    return (max(0.0, centre - margin), min(1.0, centre + margin))


def main():
    # Check that guardrail is configured
    if not os.environ.get("EPICENTRE_GUARDRAIL_ID"):
        print("ERROR: EPICENTRE_GUARDRAIL_ID not set. Export it first.")
        print("This test requires the live guardrail to be configured.")
        return 1

    if not os.environ.get("EPICENTRE_GUARDRAIL_VERSION"):
        print("ERROR: EPICENTRE_GUARDRAIL_VERSION not set. Export it first.")
        return 1

    print("Lane B4: Adversarial red team guardrail test")
    print(f"Guardrail: {os.environ.get('EPICENTRE_GUARDRAIL_ID')}")
    print(f"Version: {os.environ.get('EPICENTRE_GUARDRAIL_VERSION')}")
    print()

    # Load inputs
    inputs, meta = load_attacks()
    print(f"Loaded {len(inputs)} inputs ({meta.get('must_block', 0)} must-block, {meta.get('benign', 0)} benign)")
    print()

    # Test each input
    results = []
    for i, inp in enumerate(inputs, 1):
        print(f"[{i}/{len(inputs)}] Testing {inp['id']}... ", end="", flush=True)
        result = test_input(inp["text"], inp["id"])
        results.append(result)

        status = "BLOCKED" if result["blocked"] else "ERROR" if result["error"] else "PASSED"
        print(status)

        # Small delay to avoid rate limiting
        if i < len(inputs):
            time.sleep(0.1)

    print()

    # Analyze results
    analysis = analyze_results(results, inputs)

    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print()
    print(f"Must-block inputs ({analysis['must_block']['total']}):")
    print(f"  Blocked or errored: {analysis['must_block']['blocked_or_error']}")
    print(f"  Leaked (passed): {analysis['must_block']['passed']}")
    print(f"  Block rate: {analysis['must_block']['rate']:.1%}")

    if analysis['must_block']['total'] > 0:
        lo, hi = wilson_score_interval(
            analysis['must_block']['blocked_or_error'],
            analysis['must_block']['total']
        )
        print(f"  Wilson 95%: {lo:.1%} - {hi:.1%}")
    print()

    print(f"Benign inputs ({analysis['benign']['total']}):")
    print(f"  Passed: {analysis['benign']['passed']}")
    print(f"  False blocked: {analysis['benign']['blocked']}")
    print(f"  Pass rate: {analysis['benign']['rate']:.1%}")

    if analysis['benign']['total'] > 0:
        lo, hi = wilson_score_interval(
            analysis['benign']['passed'],
            analysis['benign']['total']
        )
        print(f"  Wilson 95%: {lo:.1%} - {hi:.1%}")
    print()

    print(f"False negatives (must-block that passed): {analysis['false_negatives']}")
    print(f"False positives (benign that blocked): {analysis['false_positives']}")
    print(f"Guardrail errors: {analysis['errors']}")
    print()

    # Save results
    output = {
        "meta": {
            **meta,
            "test_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "guardrail_id": os.environ.get("EPICENTRE_GUARDRAIL_ID"),
            "guardrail_version": os.environ.get("EPICENTRE_GUARDRAIL_VERSION"),
        },
        "inputs": inputs,
        "results": results,
        "analysis": analysis,
    }

    output_path = "/tmp/epi_lanes/b4_results.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Results saved to {output_path}")
    print()

    # Report leaks (false negatives)
    if analysis['false_negatives'] > 0:
        print("=" * 60)
        print("LEAKS FOUND (must-block inputs that passed)")
        print("=" * 60)
        for r, inp in zip(results, inputs):
            if not inp["expected_benign"] and not r["blocked"] and not r["error"]:
                print(f"  {inp['id']}: {inp['text'][:60]}...")
        print()

    # Report false positives
    if analysis['false_positives'] > 0:
        print("=" * 60)
        print("FALSE POSITIVES (benign inputs that blocked)")
        print("=" * 60)
        for r, inp in zip(results, inputs):
            if inp["expected_benign"] and r["blocked"]:
                print(f"  {inp['id']}: {inp['text'][:60]}...")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
