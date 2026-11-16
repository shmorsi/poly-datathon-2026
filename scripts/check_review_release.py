#!/usr/bin/env python3
"""Exercise the deployed portfolio review over its authenticated loopback API."""

import argparse
import base64
import json
import math
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]


def check(port, *, require_bedrock):
    base = f"http://127.0.0.1:{port}"
    headers = {"Content-Type": "application/json"}
    if password := os.environ.get("EPICENTRE_PASSWORD"):
        encoded = base64.b64encode(f"review:{password}".encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"
    if origin := os.environ.get("EPICENTRE_ORIGIN_SECRET"):
        headers["X-Origin-Verify"] = origin

    def request(path, payload=None):
        body = json.dumps(payload).encode() if payload is not None else None
        with urlopen(Request(base + path, data=body, headers=headers), timeout=40) as result:
            return result.read()

    health = json.loads(request("/api/health"))
    assert health["data"] and health["holdings"], "Market or ETF snapshot unavailable"
    if require_bedrock:
        assert health["bedrock"] and health["guardrail"], "AWS identity or input guardrail unavailable"
    assert b"Test your move before you make it" in request("/review.html"), "Wrong page revision"
    inputs = json.loads((ROOT / "web" / "review-demo.json").read_text())["examples"]
    replies = {item["id"]: json.loads(request("/api/review", item["input"])) for item in inputs}
    robert, mateo, amira, canadian = (replies[key] for key in ("robert", "mateo", "amira", "canadian"))

    assert robert["before"]["points"][0] == robert["after"]["points"][0]
    assert [p[0] for p in robert["before"]["points"]] == [p[0] for p in robert["after"]["points"]]
    assert robert["after"]["capacity_sessions"] == 188 and robert["after"]["limit_breached"]
    assert math.isclose(robert["after"]["lowest_value"], 408173.70, abs_tol=.01)
    assert robert["allocation"]["after"]["industries"], "Proposed allocation missing"
    assert any(row["id"] == "values" and row["status"] == "breached" for row in mateo["before"]["checks"])
    assert any(row["id"] == "crypto" and row["status"] == "breached" for row in amira["before"]["checks"])
    nvda = next(row for row in amira["exposure"]["before"] if row["ticker"] == "NVDA")
    assert nvda["direct_share"] < nvda["share"] and any(f["ticker"] == "QQQ" for f in nvda["funds"])
    assert canadian["after"]["canada_share"] < canadian["before"]["canada_share"]
    custom = json.loads(request("/api/review", {"amount": 100000, "portfolio": {"XIU.TO": .8, "BTC-USD": .2}}))
    assert custom["before"]["limit_breached"] is None and custom["after"] is None
    print("Four cases, optional limits, paired history, and company overlap verified.", flush=True)

    goal = "Explain which historical evidence matters if I am retiring and want to limit losses."
    payload = {"review_id": robert["review_id"], "goal": goal}
    answer = json.loads(request("/api/review/explain", payload))
    if require_bedrock:
        assert answer["mode"] == "bedrock" and answer["request_id"], "Bedrock returned no live tool trace"
    evidence = {row["id"]: row["detail"] for row in robert["evidence"]}
    assert answer["summary"] == evidence[answer["evidence_id"]]
    assert all(item["summary"] == evidence[item["evidence_id"]] for item in answer["suggestions"])
    print(json.dumps({"mode": answer["mode"], "evidence_id": answer["evidence_id"],
                      "related": [item["evidence_id"] for item in answer["suggestions"]],
                      "request_id": answer["request_id"]}), flush=True)

    try:
        request("/api/review/explain", {**payload, "goal": "My email is demo@example.com. Explain drawdown."})
    except HTTPError as error:
        assert error.code == 422, f"Unexpected privacy response: {error.code}"
    else:
        raise AssertionError("An account identifier passed the input screen")
    print("A synthetic contact-detail request was stopped.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--require-bedrock", action="store_true")
    args = parser.parse_args()
    check(args.port, require_bedrock=args.require_bedrock)
