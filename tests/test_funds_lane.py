"""Lane funds (Sun Nov 15; the lead: "put each ETF like TradingView"): the public `funds` key (fund-level aggregates only)
and the live-only `funds_private` (the companies inside each fund with the investor's dollars in each), with red gate 8
enforced at every exit: never in a saved run, refused by the static build's leak check. Synthetic holdings and a
synthetic universe: no licensed row is read or written here (the last test only reads the committed saved runs)."""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

import pipeline
import result_extras as rx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import publish_pages  # noqa: E402
import record_demo  # noqa: E402

UNI = pd.DataFrame([
    {"ticker": "XIU.TO", "name": "iShares S&P/TSX 60 Index ETF", "asset_class": "etf_equity", "country": "CAN", "sector": "Broad market (Canada)"},
    {"ticker": "XBB.TO", "name": "iShares Core Canadian Universe Bond Index ETF", "asset_class": "etf_bond", "country": "CAN", "sector": "Bonds (Canada aggregate)"},
    {"ticker": "GLD", "name": "SPDR Gold Shares", "asset_class": "etf_commodity", "country": "USA", "sector": "Gold"},
    {"ticker": "NVDA", "name": "NVIDIA", "asset_class": "equity", "country": "USA", "sector": "Information Technology"},
    {"ticker": "RY.TO", "name": "Royal Bank of Canada", "asset_class": "equity", "country": "CAN", "sector": "Financials"},
])
URL = "https://issuer.example/xiu"


def _rows():
    r = lambda etf, kind, name, ticker, w, d="2026-11-12", url=URL: {  # noqa: E731
        "etf": etf, "kind": kind, "name": name, "ticker": ticker, "weight": w, "as_of": d, "source_url": url}
    return pd.DataFrame([
        r("XIU.TO", "holding", "ROYAL BANK OF CANADA", "RY.TO", 0.10), r("XIU.TO", "holding", "BANK OF SOMEWHERE", "", 0.06),
        r("XIU.TO", "holding", "NVIDIA CORP", "NVDA", 0.04), r("XIU.TO", "holding", "SMALL CO", "", 0.02),
        r("XIU.TO", "sector", "Financials", "", 0.5), r("XIU.TO", "sector", "Energy", "", 0.3), r("XIU.TO", "sector", "Basic Materials", "", 0.2),
        r("XIU.TO", "country", "CAN", "", 0.95), r("XIU.TO", "country", "USA", "", 0.05),
        r("XBB.TO", "sector", "Bonds", "", 1.0, url="https://issuer.example/xbb"), r("XBB.TO", "country", "CAN", "", 0.96, url="https://issuer.example/xbb"),
        r("GLD", "sector", "Gold", "", 1.0, "2026-11-14", "https://issuer.example/gld"),       # stamped after the replay's last day
    ])


def _result(after=True):
    today = {"XIU.TO": 0.5, "XBB.TO": 0.3, "GLD": 0.2}
    moved = {"XIU.TO": 0.3, "XBB.TO": 0.18, "GLD": 0.12, "NVDA": 0.4}
    return {"as_of": "2026-11-12", "amount": 600000, "status": "ok", "portfolio": moved if after else today,
            "baseline": {"portfolio": today}, "metrics": {"today": {}, "after": {} if after else None},
            "lookthrough": {"today": {"sectors": {"Financials": 0.25, "Energy": 0.15}, "countries": {"CAN": 0.8, "GLOBAL": 0.2}, "mode": "lookthrough"},
                            "after": {"sectors": {"Information Technology": 0.412}, "countries": {"USA": 0.415}, "mode": "lookthrough"}},
            "tipping_point": {"ticker": "NVDA"} if after else None, "scenario": {}, "trace": [], "facts": {}}


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def test_the_public_key_is_one_fund_page_per_fund_held_today_or_with_the_move():
    r = _result()
    f = rx.funds(r, rx.inputs(r), holdings=_rows(), universe=UNI)
    assert f["mode"] == "lookthrough" and f["as_of"] == "2026-11-12" and "nothing dated later is used" in f["dated"]
    xiu, xbb, gld = f["funds"]                                         # by today's weight: 50 %, 30 %, 20 %
    assert [xiu["ticker"], xbb["ticker"], gld["ticker"]] == ["XIU.TO", "XBB.TO", "GLD"]
    assert xiu["name"] == "iShares S&P/TSX 60 Index ETF" and xiu["issuer"].startswith("BlackRock") and xiu["page"] == URL
    assert xiu["holds"] == "Broad market (Canada)" and xiu["date"] == "2026-11-12"
    assert xiu["listed"] == {"positions": 4, "sectors": 3, "countries": 2}
    assert xiu["coverage"] == pytest.approx(0.22)                      # 10 + 6 + 4 + 2 % of the fund is listed
    assert [s["name"] for s in xiu["sectors"]] == ["Financials", "Energy", "Materials"]       # ICB -> GICS, by size
    assert xiu["countries"] == [{"name": "CAN", "share": 0.95}, {"name": "USA", "share": 0.05}]
    assert xiu["today"] == {"share": 0.5, "dollars": 300000} and xiu["after"] == {"share": 0.3, "dollars": 180000}
    assert xiu["top10"] == {"count": 4, "share": pytest.approx(0.22)} and xiu["concentrated"] is False   # one aggregate, no name
    assert xbb["top10"] is None and xbb["concentrated"] is False
    assert xbb["coverage"] is None and xbb["listed"]["positions"] == 0 and xbb["sectors"] == [{"name": "Bonds", "share": 1.0}]
    assert [c["name"] for c in xbb["countries"]] == ["CAN", "OTHER"]   # the unexplained 4 % is OTHER, as the look-through says
    assert gld["date"] is None and gld["sectors"] == [] and gld["later"] == "2026-11-14"     # dated after as_of: not used
    today, after = f["sides"]["today"], f["sides"]["after"]
    assert today["in_funds"] == {"share": 1.0, "dollars": 600000} and today["direct"] == []
    assert after["direct"] == [{"ticker": "NVDA", "name": "NVIDIA", "share": 0.4, "dollars": 240000,
                                "total": {"share": 0.4, "dollars": 240000}}]          # no lookthrough.stocks: the line itself
    assert today["unlisted"]["dollars"] == round(600000 * 0.5 * (1 - 0.22))                   # the stock fund's unlisted part
    assert today["sectors"][0] == {"name": "Financials", "share": 0.25, "dollars": 150000}
    assert after["countries"] == [{"name": "USA", "share": 0.415, "dollars": 249000}]


def test_the_public_key_names_no_company_inside_a_fund_and_passes_the_leak_check():
    r = _result()
    f = rx.funds(r, rx.inputs(r), holdings=_rows(), universe=UNI)
    text = " ".join(_strings(f)).upper()
    assert not any(n in text for n in ("ROYAL BANK", "BANK OF SOMEWHERE", "SMALL CO"))
    assert "RY.TO" not in text and record_demo.find_leaks({"funds": f}) == []
    assert not any(isinstance(d, dict) and {"etf", "weight"} <= set(d) for d in _dicts(f))


def _dicts(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _dicts(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _dicts(v)


def test_a_snapshot_newer_than_the_replay_or_no_file_is_direct_mode():
    r = _result()
    newer = _rows().assign(as_of="2026-11-13")
    f = rx.funds(r, rx.inputs(r), holdings=newer, universe=UNI)
    assert f["mode"] == "direct" and f["newest"] == "2026-11-13" and all(x["date"] is None for x in f["funds"])
    assert all(x["later"] == "2026-11-13" for x in f["funds"])
    empty = rx.funds(r, rx.inputs(r), holdings=pd.DataFrame(columns=_rows().columns), universe=UNI)
    assert empty["mode"] == "direct" and empty["funds"][0]["page"] is None
    assert rx.funds_private(r, holdings=newer, universe=UNI) is None
    assert rx.funds_private(r, holdings=pd.DataFrame(columns=_rows().columns), universe=UNI) is None


def test_the_private_key_is_amount_times_fund_weight_times_company_weight_and_what_you_end_up_owning():
    r = _result()
    p = rx.funds_private(r, holdings=_rows(), universe=UNI, top=3)
    xiu = p["funds"]["XIU.TO"]
    assert xiu["listed"] == 4 and xiu["date"] == "2026-11-12" and len(xiu["top"]) == 3
    first = xiu["top"][0]
    assert first == {"name": "Royal Bank of Canada", "ticker": "RY.TO", "share": 0.1, "today": round(600000 * 0.5 * 0.1),
                     "after": round(600000 * 0.3 * 0.1)}
    assert xiu["top"][1]["name"] == "Bank of Somewhere" and xiu["top"][1]["ticker"] is None
    assert "XBB.TO" not in p["funds"] and "GLD" not in p["funds"]     # no positions listed (bonds) or dated after as_of
    after = p["owning"]["after"]
    nv = next(o for o in after["top"] if o["ticker"] == "NVDA")
    assert nv["dollars"] == round(600000 * 0.4 + 600000 * 0.3 * 0.04) and nv["direct"] == 240000 and nv["funds"] == ["XIU.TO"]
    assert nv["inside"] == [{"fund": "XIU.TO", "share": pytest.approx(0.3 * 0.04), "dollars": round(600000 * 0.3 * 0.04)}]   # counted twice
    today = p["owning"]["today"]["top"]
    assert after["top"][0]["ticker"] == "NVDA" and [o["dollars"] for o in today] == sorted((o["dollars"] for o in today), reverse=True)
    assert after["named"]["count"] == 4 and after["rest"] == {"count": 0, "share": 0.0, "dollars": 0}
    assert after["named"]["dollars"] == round(600000 * 0.4 + 600000 * 0.3 * 0.22)     # NVDA direct + every listed position
    assert rx.funds_private(_result(after=False), holdings=_rows(), universe=UNI)["owning"]["after"] is None
    monkey = rx.OWNING_TOP
    try:
        rx.OWNING_TOP = 2
        two = rx.funds_private(r, holdings=_rows(), universe=UNI)["owning"]["today"]
        assert len(two["top"]) == 2 and two["rest"]["count"] == 2 and two["rest"]["dollars"] == round(600000 * 0.5 * (0.04 + 0.02))
    finally:
        rx.OWNING_TOP = monkey


def test_funds_private_never_reaches_a_saved_run_and_the_static_build_refuses_it(tmp_path, monkeypatch):
    r = {**_result(), "funds_private": {"funds": {"XIU.TO": {"top": [{"name": "Royal Bank of Canada", "share": 0.1}]}}}}
    assert "funds_private" not in pipeline._publishable(r)
    assert any("funds_private" in leak for leak in record_demo.find_leaks({"result": r}))
    (tmp_path / "moves.json").write_text(json.dumps({"moves": [{"x": {"funds_private": {"a": 1}}}]}), encoding="utf-8")
    site = tmp_path / "site"
    (site / "runs").mkdir(parents=True)
    (site / "index.html").write_text("<html><head></head></html>", encoding="utf-8")
    monkeypatch.setattr(pipeline, "DEMO_DIR", tmp_path)
    with pytest.raises(SystemExit, match="not public"):
        publish_pages.add_extras(site)


def test_the_server_adds_it_to_a_live_answer_only_and_never_to_the_stored_run(monkeypatch):
    import server
    calls = []
    monkeypatch.setattr(rx, "funds_private", lambda shown: calls.append(shown) or {"funds": {}, "owning": {}})
    stored = _result()
    shown = server._with_funds(stored)
    assert shown["funds_private"] == {"funds": {}, "owning": {}} and "funds_private" not in stored and calls == [stored]
    assert server._with_funds({"status": "error"}) == {"status": "error"}
    monkeypatch.setattr(rx, "funds_private", lambda shown: None)       # no holdings file on this machine: nothing added
    assert "funds_private" not in server._with_funds(_result())
    monkeypatch.setattr(rx, "funds_private", lambda shown: 1 / 0)      # never stops the answer
    assert "funds_private" not in server._with_funds(_result())


def test_no_committed_saved_run_carries_funds_private():
    for path in sorted((ROOT / "data" / "demo_runs").glob("*.json")):
        assert "funds_private" not in path.read_text(encoding="utf-8"), path.name


def test_a_direct_company_also_inside_a_fund_is_counted_twice_from_the_published_look_through_total():
    r = _result()
    r["lookthrough"]["after"]["stocks"] = {"NVDA": {"direct": 0.4, "total": 0.412}}    # the public cut keeps a line's own total
    after = rx.funds(r, rx.inputs(r), holdings=_rows(), universe=UNI)["sides"]["after"]
    assert after["direct"][0]["total"] == {"share": 0.412, "dollars": 247200} and after["direct"][0]["dollars"] == 240000


@pytest.mark.skipif(not (ROOT / "data" / "etf_holdings.csv").exists() or not (ROOT / "data" / "demo_runs" / "default.json").exists(),
                    reason="the licensed holdings file or the saved runs are not on this machine")
def test_the_live_demo_run_answer_carries_funds_private_and_the_saved_file_never_does():
    from fastapi.testclient import TestClient
    import server
    answer = TestClient(server.create_app()).get("/api/demo-run").json()
    assert answer["funds"]["funds"] and answer["funds_private"]["funds"]               # live: the companies, with your dollars
    assert "funds_private" not in (ROOT / "data" / "demo_runs" / "default.json").read_text(encoding="utf-8")
