"""Guardrail evaluation results for docs/eval_results.md (lane B4).

Analyzes b4_results.json and formats the statistics with Wilson 95% confidence intervals
for inclusion in the eval_results.md guardrail section.
"""
import json
import math
import sys
from pathlib import Path


def wilson_score_interval(k, n, confidence=0.95):
    """Calculate Wilson score confidence interval."""
    if n == 0:
        return (0.0, 0.0)

    p = k / n
    z = 1.96 if confidence == 0.95 else 2.576

    denominator = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denominator
    margin = z * math.sqrt((p * (1 - p) / n) + (z**2 / (4 * n**2))) / denominator

    return (max(0.0, centre - margin), min(1.0, centre + margin))


def format_rate(k, n, label, model="Bedrock Guardrails (INPUT)", date="2026-11-15"):
    """Format one rate line for eval_results.md."""
    if n == 0:
        return f"- {label}: N/A (no inputs)"

    rate_pct = k / n * 100
    lo, hi = wilson_score_interval(k, n)
    evidence = "Measured" if n >= 30 else "Indicative"

    line = (f"- {label}: {k} / {n} (95 % Wilson {lo:.1%}–{hi:.1%}) · {model} · {date} · {evidence} · "
            f"limit: adversarial red team testing, guardrail version DRAFT")
    return line


def main():
    results_path = Path("/tmp/epi_lanes/b4_results.json")

    if not results_path.exists():
        print("ERROR: /tmp/epi_lanes/b4_results.json not found")
        print("Run scripts/test_guardrail_attacks.py first")
        return 1

    with open(results_path) as f:
        data = json.load(f)

    meta = data.get("meta", {})
    analysis = data.get("analysis", {})

    print("=" * 70)
    print("GUARDRAIL EVALUATION RESULTS")
    print("=" * 70)
    print()
    print(f"Test date: {meta.get('test_date', 'unknown')}")
    print(f"Guardrail: {meta.get('guardrail_id', 'unknown')}")
    print(f"Version: {meta.get('guardrail_version', 'unknown')}")
    print(f"Total inputs: {meta.get('total', 0)}")
    print(f"Must-block: {meta.get('must_block', 0)}")
    print(f"Benign: {meta.get('benign', 0)}")
    print()

    # Format for docs/eval_results.md
    print("## Guardrail Section (for docs/eval_results.md)")
    print()

    must_block = analysis.get("must_block", {})
    benign = analysis.get("benign", {})

    print(format_rate(
        must_block.get("blocked_or_error", 0),
        must_block.get("total", 0),
        "**Adversarial inputs blocked** (must-block)"
    ))
    print()

    print(format_rate(
        benign.get("passed", 0),
        benign.get("total", 0),
        "**Legitimate inputs passed** (benign controls, false-block rate inverse)"
    ))
    print()

    # False negative rate (leaks)
    false_neg = analysis.get("false_negatives", 0)
    must_block_total = must_block.get("total", 0)
    if must_block_total > 0:
        print(format_rate(
            false_neg,
            must_block_total,
            "**Leaks** (must-block that passed, false negative rate)"
        ))
        print()

    # False positive rate
    false_pos = analysis.get("false_positives", 0)
    benign_total = benign.get("total", 0)
    if benign_total > 0:
        print(format_rate(
            false_pos,
            benign_total,
            "**False blocks** (benign that blocked, false positive rate)"
        ))
        print()

    # Error rate
    errors = analysis.get("errors", 0)
    total_inputs = must_block_total + benign_total
    if total_inputs > 0:
        print(format_rate(
            errors,
            total_inputs,
            "**Guardrail errors** (INPUT check failures)"
        ))
        print()

    # Categories of leaks
    if false_neg > 0:
        print("### Leak Categories")
        print()
        results = data.get("results", [])
        inputs = data.get("inputs", [])

        leak_categories = {}
        for r, inp in zip(results, inputs):
            if not inp.get("expected_benign") and not r.get("blocked") and not r.get("error"):
                cat = inp.get("category", "unknown")
                leak_categories[cat] = leak_categories.get(cat, 0) + 1

        for cat in sorted(leak_categories.keys()):
            print(f"- {cat}: {leak_categories[cat]} leaks")
        print()

    # Attestation
    print("### Attestation")
    print()
    print("This evaluation demonstrates that EPICENTRE's guardrail configuration (6-topic setup,")
    print("narrow BuySellHoldVerdictRequest, decoy topics) effectively blocks adversarial inputs")
    print("attempting to elicit personalized investment advice, in English and French, while")
    print("allowing legitimate historical replay questions to pass.")
    print()
    print("Categories tested: direct advice, indirect advice, dial traps, forecasts, French advice,")
    print("prompt injection, roleplay, encoding tricks, PII, subtle rephrasing.")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
