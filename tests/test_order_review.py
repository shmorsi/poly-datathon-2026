from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import create_app
from tools import data, lookthrough


ROOT = Path(__file__).resolve().parents[1]
PORTFOLIO = {"XIU.TO": .45, "XBB.TO": .35, "GLD": .10, "ZST.TO": .10}


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "DATA_DIR", ROOT / "data/fake/starter")
    monkeypatch.setenv("EPICENTRE_NO_BEDROCK", "1")
    holdings = tmp_path / "holdings.csv"
    holdings.write_text(
        "etf,kind,name,ticker,weight,as_of,source_url\n"
        "XIU.TO,holding,Illustrative issuer,NVDA,0.10,2026-11-12,https://example.com/holdings\n"
        "XIU.TO,sector,Financials,,0.60,2026-11-12,https://example.com/sectors\n"
        "XIU.TO,sector,Technology,,0.40,2026-11-12,https://example.com/sectors\n"
    )
    monkeypatch.setattr(lookthrough, "HOLDINGS_CSV", holdings)
    return TestClient(create_app())


def payload(**changes):
    return {"portfolio": PORTFOLIO, "amount": 600000, "drawdown_limit": .15,
            "capacity": 90000, **changes}


def test_order_preview_preserves_same_dollar_base_and_names_fund_exposure(api):
    response = api.post("/api/review", json=payload(order={
        "ticker": "NVDA", "weight": .30, "from_ticker": "XBB.TO",
    }))
    assert response.status_code == 200
    result = response.json()
    before, after = result["before"], result["after"]
    assert before["points"][0] == after["points"][0]
    assert before["points"][0][1] == 600000
    assert [p[0] for p in before["points"]] == [p[0] for p in after["points"]]
    target = next(x for x in after["holdings"] if x["ticker"] == "NVDA")
    assert target["weight"] == pytest.approx(.30)
    fund = next(f for f in result["funds"] if f["ticker"] == "XIU.TO")
    assert fund["industries"] == [{"name": "Financials", "share": .60},
                                  {"name": "Information Technology", "share": .40}]
    assert fund["companies"][0]["before_share"] == pytest.approx(.045)
    company = next(c for c in result["exposure"]["after"] if c["ticker"] == "NVDA")
    assert company["share"] == pytest.approx(.345)
    assert company["funds"] == [{"ticker": "XIU.TO", "share": pytest.approx(.045)}]


def test_order_preview_rejects_an_order_its_selected_holding_cannot_fund(api):
    response = api.post("/api/review", json=payload(order={
        "ticker": "NVDA", "weight": .40, "from_ticker": "XBB.TO",
    }))
    assert response.status_code == 422
    assert "cannot come from there alone" in response.json()["message"]


def test_own_portfolio_review_survives_without_an_order_and_evidence_can_be_selected(api):
    result = api.post("/api/review", json=payload()).json()
    assert result["after"] is None
    response = api.post("/api/review/explain", json={
        "review_id": result["review_id"], "goal": "I am retiring and need to limit losses",
    })
    assert response.status_code == 200
    assert response.json()["mode"] == "rules"
    assert response.json()["evidence_id"] == "drawdown"
    assert any(row["id"] == "drawdown" for row in result["evidence"])


def test_explanation_refuses_unknown_review_id(api):
    response = api.post("/api/review/explain", json={"review_id": "0" * 32, "goal": "risk"})
    assert response.status_code == 404


def test_review_applies_an_investor_defined_crypto_cap(api):
    response = api.post("/api/review", json=payload(
        portfolio={"NVDA": .85, "BTC-USD": .15}, crypto_limit=.10,
    ))
    assert response.status_code == 200
    check = next(row for row in response.json()["before"]["checks"] if row["id"] == "crypto")
    assert check["status"] == "breached"
    assert "15.0%" in check["detail"] and "10.0%" in check["detail"]


def test_values_review_reports_unavailable_etf_company_coverage(api, monkeypatch, tmp_path):
    monkeypatch.setattr(lookthrough, "HOLDINGS_CSV", tmp_path / "missing.csv")
    response = api.post("/api/review", json=payload(values_screen=True))
    assert response.status_code == 200
    check = next(row for row in response.json()["before"]["checks"] if row["id"] == "values")
    assert check["status"] == "limited"
    assert "ETF" in check["detail"]


def test_bedrock_may_select_an_existing_card_and_cannot_supply_its_own_claim(api, monkeypatch):
    import agents.common
    import guardrail
    import order_review

    class Bedrock:
        def converse(self, **request):
            spec = request["toolConfig"]["tools"][0]["toolSpec"]
            assert spec["name"] == "open_evidence"
            assert "risk" in spec["inputSchema"]["json"]["properties"]["evidence_id"]["enum"]
            assert "600000" not in str(request["messages"])
            return {
                "stopReason": "tool_use",
                "output": {"message": {"content": [
                    {"toolUse": {"name": "open_evidence", "input": {"evidence_id": "risk"}}},
                    {"text": "A fabricated amount of $999,999."},
                ]}},
                "ResponseMetadata": {"RequestId": "tested-request"},
            }

    monkeypatch.setattr(agents.common, "runtime_client", Bedrock)
    monkeypatch.setattr(guardrail, "apply_guardrail", lambda *_a: {"action": "NONE", "blocked": False})
    result = api.post("/api/review", json=payload()).json()
    reply = order_review.explain_review(result["evidence"], "What explains the largest risk?", use_bedrock=True)
    risk = next(row for row in result["evidence"] if row["id"] == "risk")
    assert reply["mode"] == "bedrock"
    assert reply["request_id"] == "tested-request"
    assert reply["summary"] == risk["detail"]


def test_explanation_rejects_account_details_without_calling_bedrock(api):
    result = api.post("/api/review", json=payload()).json()
    response = api.post("/api/review/explain", json={
        "review_id": result["review_id"], "goal": "My contact is investor@example.com. Show the losses.",
    })
    assert response.status_code == 422
    assert "account or contact" in response.json()["message"]


def test_full_portfolio_review_does_not_require_an_investor_to_enter_a_limit(api):
    result = api.post("/api/review", json=payload(drawdown_limit=None, capacity=None))
    assert result.status_code == 200
    data = result.json()
    assert data["before"]["max_drawdown"] is not None
    assert data["before"]["limit_breached"] is None
    assert data["before"]["capacity_breached"] is None
    assert data["limits"]["drawdown"] is None
    assert any(row["id"] == "method" for row in data["evidence"])


def test_method_question_opens_method_and_offers_relevant_source_links(api):
    data = api.post("/api/review", json=payload()).json()
    response = api.post("/api/review/explain", json={
        "review_id": data["review_id"], "goal": "How was the historical drawdown calculated?",
    })
    assert response.status_code == 200
    reply = response.json()
    assert reply["evidence_id"] == "method"
    assert [item["evidence_id"] for item in reply["suggestions"]] == ["drawdown", "risk"]
    assert all(item["summary"] for item in reply["suggestions"])


def test_agent_can_explain_the_current_mix_before_revealing_a_saved_order(api):
    data = api.post("/api/review", json=payload(order={"ticker": "NVDA", "weight": .40})).json()
    before = api.post("/api/review/explain", json={
        "review_id": data["before_review_id"], "goal": "What was my worst loss?",
    }).json()
    after = api.post("/api/review/explain", json={
        "review_id": data["review_id"], "goal": "What was my worst loss?",
    }).json()
    assert data["before_review_id"] != data["review_id"]
    assert before["summary"] == next(row["detail"] for row in data["before_evidence"] if row["id"] == "drawdown")
    assert after["summary"] != before["summary"]


def test_proposed_portfolio_shows_each_asset_type_and_company_coverage(api):
    data = api.post("/api/review", json=payload(order={
        "ticker": "NVDA", "weight": .30, "from_ticker": "XBB.TO",
    })).json()
    current, proposed = data["allocation"]["before"], data["allocation"]["after"]
    assert sum(row["share"] for row in current["industries"]) == pytest.approx(1)
    assert sum(row["share"] for row in proposed["industries"]) == pytest.approx(1)
    assets = {row["name"]: row["share"] for row in proposed["industries"]}
    assert assets["Bonds"] == pytest.approx(.15)
    assert assets["Information Technology"] == pytest.approx(.48)
    assert current["equity_company_coverage"] == pytest.approx(.10)
    assert proposed["equity_company_coverage"] == pytest.approx(.46)
