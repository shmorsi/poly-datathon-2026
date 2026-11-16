"""Plan B Task 6 (the AI lead): tools/allocation.py. The size curve, the code's variations of the investor's own move, the
floor sensitivity, the price of values and the illustration mixes (ledger 2, 6, 29, 30; spec 10; spec 24 resolution 7).
Every verdict here comes from governance.evaluate, the one judge."""
import json

import pandas as pd
import pytest

import config
import governance
import tools.allocation as allocation
from tools.allocation import (aligned_allocation, binding_rule, comparison_menu, price_of_values, sensitivity,
                              tipping_point)
from tools.data import make_market
from tools.portfolio import apply_change

LOW = {"goal": "preservation", "horizon_years": 4, "risk": "low", "esg": False, "crypto": False,
       "capacity": None, "reaction_2022": None}
NB = "\u00a0"   # governance.fmt_pct writes a no-break space before every percent sign


def _market():
    dates = pd.bdate_range("2024-01-01", periods=320)
    hot = ([100 - 0.5 * i for i in range(101)] + [50 + 0.5 * i for i in range(1, 101)] + [100.0] * 320)[:320]
    safe = [100 * (1 + 0.001 * (-1) ** i) for i in range(320)]
    rows = [("HOT", "equity", "Industrials"), ("SAFE", "etf_bond", "Bonds (Canada aggregate)"), ("OIL", "equity", "Energy")]
    uni = pd.DataFrame([{"ticker": t, "name": t, "asset_class": c, "market": "TSX", "currency": "CAD",
                         "sector": s, "country": "CAN"} for t, c, s in rows])
    prices = pd.DataFrame({"HOT": hot, "SAFE": safe, "OIL": safe}, index=dates)
    as_of = dates[-1].strftime("%Y-%m-%d")
    return make_market(prices, universe=uni, as_of=as_of), as_of


def test_illustration_mixes():
    low = aligned_allocation(LOW)
    assert low["weights"] == pytest.approx({"XBB.TO": 0.25, "ZST.TO": 0.25, "XIU.TO": 0.25, "SPY": 0.15, "GLD": 0.10})
    assert low["label"] == "Fictional illustration, not a recommendation"
    assert low["source"] == "tools.allocation" and low["as_of"] and low["rule"]
    esg = aligned_allocation({**LOW, "risk": "moderate", "esg": True})
    assert esg["weights"] == pytest.approx({"XBB.TO": 0.35, "ESGV": 0.55, "GLD": 0.10})
    high = aligned_allocation({**LOW, "risk": "high", "crypto": True})
    assert sum(high["weights"].values()) == pytest.approx(1.0) and "BTC-USD" in high["weights"]
    assert aligned_allocation(None) is None


def test_mixes_missing_from_personas_follow_the_two_rules(monkeypatch):
    """Built-in fallback: ESGV replaces SPY and takes XIU.TO's share; 10 % BTC-USD is taken from QQQ (spec 10)."""
    monkeypatch.setattr(allocation, "_personas_mixes", lambda: {})
    assert aligned_allocation({**LOW, "esg": True})["weights"] == pytest.approx(
        {"XBB.TO": 0.25, "ZST.TO": 0.25, "ESGV": 0.40, "GLD": 0.10})
    assert aligned_allocation({**LOW, "risk": "high", "esg": True})["weights"] == pytest.approx(
        {"XBB.TO": 0.15, "ESGV": 0.50, "QQQ": 0.25, "GLD": 0.10})
    both = aligned_allocation({**LOW, "risk": "high", "esg": True, "crypto": True})["weights"]
    assert both == pytest.approx({"XBB.TO": 0.15, "ESGV": 0.50, "QQQ": 0.15, "BTC-USD": 0.10, "GLD": 0.10})
    assert "BTC-USD" not in aligned_allocation({**LOW, "crypto": True})["weights"]      # crypto only in the high band
    assert aligned_allocation({**LOW, "risk": None, "reaction_2022": "bought"})["weights"] == pytest.approx(
        {"XBB.TO": 0.15, "XIU.TO": 0.30, "SPY": 0.20, "QQQ": 0.25, "GLD": 0.10})        # the band from 2022


def test_size_curve_from_today_with_the_single_stock_cap():
    m, as_of = _market()
    tp = tipping_point(LOW, {"SAFE": 1.0}, "HOT", [], as_of, market=m, events=[], max_weight=0.40)
    assert len(tp["curve"]) == 41 and tp["curve"][0]["weight"] == 0.0 and tp["curve"][0]["fails"] == 0
    assert set(tp["curve"][5]) == {"weight", "verdict", "fails", "max_drawdown", "scenario_shock"}
    assert tp["max_weight"] == pytest.approx(0.10) and tp["still_failing"] is None
    assert tp["ticker"] == "HOT" and isinstance(tp["curve"][11]["fails"], int) and tp["curve"][11]["fails"] == 1


def test_size_curve_still_failing_when_today_already_fails():
    m, as_of = _market()
    tp = tipping_point({**LOW, "esg": True}, {"OIL": 0.05, "SAFE": 0.95}, "HOT", [], as_of,
                       market=m, events=[], max_weight=0.03)
    assert tp["max_weight"] is None and tp["still_failing"] == "esg_direct"


def test_each_curve_point_is_the_one_judges_answer():
    """Ledger 30 / plan D Task 5: the curve's verdict per size is governance.evaluate's, never a second formula."""
    m, as_of = _market()
    tp = tipping_point(LOW, {"SAFE": 1.0}, "HOT", [], as_of, market=m, events=[], max_weight=0.40, amount=100000)
    for p in (tp["curve"][0], tp["curve"][10], tp["curve"][11], tp["curve"][40]):
        mix = apply_change({"SAFE": 1.0}, {"op": "set", "ticker": "HOT", "weight": p["weight"]})
        ev = governance.evaluate(LOW, mix, None, as_of, market=m, events=[], amount=100000, detail=False)
        assert (p["verdict"], p["fails"]) == (ev["verdict"], governance.count_fails(ev["checks"]))
        assert (p["max_drawdown"], p["scenario_shock"]) == (ev["metrics"]["max_drawdown"], ev["stress"]["value"])



def _spy_families(monkeypatch):
    """Records the families every evaluate call receives (the replay itself runs with no storms)."""
    seen, judge = [], governance.evaluate

    def spy(profile, weights, families, as_of, **kw):
        seen.append(None if families is None else list(families))
        return judge(profile, weights, families, as_of, **{**kw, "events": []})
    monkeypatch.setattr(allocation.governance, "evaluate", spy)
    return seen


def test_the_navigators_families_pass_through_unchanged(monkeypatch):
    """Ruling 4: families go to the judge as given; [] is the navigator's abstention (B Task 5), never "all four"."""
    m, as_of = _market()
    seen = _spy_families(monkeypatch)
    out = tipping_point(LOW, {"SAFE": 1.0}, "HOT", [], as_of, market=m, events=[], families=[], max_weight=0.02)
    assert seen == [[], [], []] and all(p["scenario_shock"] is None for p in out["curve"])
    seen.clear()
    tipping_point(LOW, {"SAFE": 1.0}, "HOT", ["x"], as_of, market=m, events=[], families=["war_oil"], max_weight=0.01)
    assert seen == [["war_oil"], ["war_oil"]]
    seen.clear()
    storms = [{"event_id": "e1", "family": "chips"}, {"event_id": "e2", "family": "tariffs"}]
    tipping_point(LOW, {"SAFE": 1.0}, "HOT", ["e2"], as_of, market=m, events=storms, max_weight=0.0)
    tipping_point(LOW, {"SAFE": 1.0}, "HOT", ["zz"], as_of, market=m, events=storms, max_weight=0.0)
    assert seen == [["tariffs"], None]          # no family named: the families of the event ids, else all four


def test_comparison_menu_is_code_built_and_unranked():
    m, as_of = _market()
    rows = comparison_menu(LOW, {"SAFE": 1.0}, {"op": "set", "ticker": "HOT", "weight": 0.40}, [], as_of,
                           market=m, events=[])
    assert [r["kind"] for r in rows] == ["threshold", "funded_from"]
    assert [r["change"]["op"] for r in rows] == ["set", "fund"]
    assert all(set(r) == {"kind", "change", "weights", "verdict", "binding_rule", "max_drawdown", "scenario_shock"}
               for r in rows)                   # no label: the pipeline writes it from the kind and numbers (ledger 30)
    assert rows[0]["change"]["ticker"] == "HOT" and rows[0]["change"]["weight"] == pytest.approx(0.10)
    assert rows[0]["binding_rule"] == "scenario_stress"           # the abstention's warn; nothing fails at 10 %
    assert rows[1]["change"]["from_ticker"] == "SAFE" and rows[1]["weights"]["HOT"] == pytest.approx(0.40)
    assert rows[1]["weights"] == pytest.approx({"HOT": 0.40, "SAFE": 0.60})
    assert (rows[1]["verdict"], rows[1]["binding_rule"]) == ("Incompatible", "max_drawdown")
    assert {r["change"]["ticker"] for r in rows} == {"HOT"}          # never another security in its place (res. 7)
    assert comparison_menu(LOW, {"SAFE": 1.0}, None, [], as_of, market=m, events=[]) == []
    assert comparison_menu(LOW, {"SAFE": 1.0}, {"op": "replace", "ticker": "HOT", "weight": 1.0, "from_ticker": "SAFE"},
                           [], as_of, market=m, events=[]) == []


def test_menu_rows_are_judged_by_evaluate_and_skip_what_does_not_apply():
    m, as_of = _market()
    today = {"SAFE": 0.92, "HOT": 0.05, "OIL": 0.03}
    rows = comparison_menu(LOW, today, {"op": "add", "ticker": "HOT", "weight": 0.03}, None, as_of, market=m, events=[])
    assert [r["kind"] for r in rows] == ["funded_from"]          # 8 % has no fail: no threshold row below it
    assert rows[0]["weights"] == pytest.approx({"SAFE": 0.89, "HOT": 0.08, "OIL": 0.03})
    ev = governance.evaluate(LOW, rows[0]["weights"], None, as_of, market=m, events=[], detail=False)
    assert (rows[0]["verdict"], rows[0]["max_drawdown"]) == (ev["verdict"], ev["metrics"]["max_drawdown"])
    assert comparison_menu(LOW, today, {"op": "set", "ticker": "HOT", "weight": 0.02}, None, as_of,
                           market=m, events=[]) == []         # a smaller size: nothing to fund, nothing fails below it
    wide = {"single_stock": 0.5, "sector": 0.6}                 # the user's edits reach every judgement
    small = {"SAFE": 0.55, "OIL": 0.45}
    rows = comparison_menu(LOW, small, {"op": "set", "ticker": "HOT", "weight": 0.60}, None, as_of,
                           market=m, events=[], limits=wide)
    tp = tipping_point(LOW, small, "HOT", [], as_of, market=m, events=[], limits=wide, max_weight=0.60)
    assert [r["kind"] for r in rows] == ["threshold"]           # the largest line (SAFE, 55 %) cannot fund 60 %
    assert 0 < tp["max_weight"] < 0.60 and rows[0]["change"]["weight"] == tp["max_weight"]


def _analysis(drop, *, universe=(), stress=-0.05):
    m = {"max_drawdown": drop, "peak_date": "2021-11-29", "trough_date": "2022-10-14",
         "recovery_days": 200, "days_since_trough": 900}
    return {"metrics": m, "lookthrough": None, "universe": list(universe), "esg_flags": set(), "scenario_stress": stress,
            "scenario_family": "Tariff war", "scenario_episodes": 3}


UNI = [{"ticker": "HOT", "asset_class": "equity", "sector": "Industrials"},
       {"ticker": "SAFE", "asset_class": "etf_bond", "sector": "Bonds (Canada aggregate)"}]


def test_sensitivity_names_the_flip_floor():
    out = sensitivity(LOW, {"SAFE": 1.0}, _analysis(-0.345))
    assert out["floor_flip"] == pytest.approx(-0.345)
    assert out["sentence"] == (f"Outside your limits until your floor is −34.5{NB}% or lower; "
                               "at that floor the verdict would be Inside your limits.")


def test_sensitivity_says_which_limit_still_fails_and_scans_stricter_floors():
    out = sensitivity(LOW, {"HOT": 0.40, "SAFE": 0.60}, _analysis(-0.345, universe=UNI))
    assert out["floor_flip"] == pytest.approx(-0.345)
    assert out["sentence"] == (f"Outside your limits until your floor is −34.5{NB}% or lower; at that floor the verdict "
                               "would be Inside, with caveats because HOT would still be beyond the single-company limit.")
    near = sensitivity(LOW, {"SAFE": 1.0}, _analysis(-0.12, stress=None))      # inside -15 %: a stricter floor flips it
    assert near["floor_flip"] == pytest.approx(-0.119)
    assert near["sentence"] == (f"Inside your limits until your floor is −11.9{NB}% or stricter; "
                                "at that floor the verdict would be Outside your limits.")
    edited = sensitivity(LOW, {"SAFE": 1.0}, _analysis(-0.12, stress=None), limits={"floor": -0.30})
    assert edited["floor_flip"] == pytest.approx(-0.119)                         # the scan starts from your own floor


def test_sensitivity_without_a_flip_or_without_limits():
    still = sensitivity(LOW, {"HOT": 0.40, "SAFE": 0.60}, _analysis(-0.0004, universe=UNI, stress=None))
    assert still == {"floor_flip": None,
                     "sentence": f"No floor between −0.1{NB}% and −60{NB}% changes the verdict: another limit decides it."}
    assert sensitivity(None, {"SAFE": 1.0}, _analysis(-0.345)) == {"floor_flip": None, "sentence": "Limits missing."}


def test_binding_rule_is_the_check_that_decides():
    row = lambda rule, tier, status: {"rule": rule, "tier": tier, "status": status, "holding": None}
    assert binding_rule([row("recovery", "warn", "warn"), row("sector", "soft", "fail"),
                         row("max_drawdown", "hard", "fail")]) == "max_drawdown"
    assert binding_rule([row("recovery", "warn", "warn"), row("esg_direct", "preference", "fail"),
                         row("sector", "soft", "fail")]) == "esg_direct"
    assert binding_rule([row("max_drawdown", "hard", "pass"), row("recovery", "warn", "warn")]) == "recovery"
    assert binding_rule([row("max_drawdown", "hard", "pass")]) is None and binding_rule([]) is None


def test_price_of_values_only_for_esg():
    m, as_of = _market()
    assert price_of_values(LOW, {"SAFE": 1.0}, as_of, market=m, events=[]) is None
    assert price_of_values(None, {"SAFE": 1.0}, as_of, market=m, events=[]) is None


def test_price_of_values_is_your_own_mix_without_the_flagged_names():
    """Spec 24 resolution 7: the flagged names removed, the rest scaled up, no new security, no model mix."""
    m, as_of = _market()
    esg = {**LOW, "esg": True}
    own = {"SAFE": 0.60, "OIL": 0.20, "HOT": 0.20}
    pv = price_of_values(esg, own, as_of, market=m, events=[])
    assert pv["removed"] == ["OIL"] and pv["source"] == "tools.allocation" and pv["as_of"] == as_of
    assert pv["non_esg"]["weights"] == pytest.approx(own)
    assert pv["esg"]["weights"] == pytest.approx({"SAFE": 0.75, "HOT": 0.25})
    for side in ("esg", "non_esg"):
        ev = governance.evaluate(None, pv[side]["weights"], ["war_oil"], as_of, market=m, events=[], detail=False)
        assert set(pv[side]) == {"weights", "label", "max_drawdown", "war_oil_worst", "cagr"}
        assert (pv[side]["max_drawdown"], pv[side]["cagr"]) == (ev["metrics"]["max_drawdown"], ev["metrics"]["cagr"])
        assert pv[side]["war_oil_worst"] == ev["stress"]["value"]
    judged = governance.evaluate(esg, pv["esg"]["weights"], ["war_oil"], as_of, market=m, events=[], detail=False)
    assert next(c for c in judged["checks"] if c["rule"] == "esg_direct")["status"] == "pass"   # the one judge agrees
    assert "OIL" in pv["esg"]["label"] and "recommend" not in json.dumps(pv).lower()
    clean = price_of_values(esg, {"SAFE": 0.8, "HOT": 0.2}, as_of, market=m, events=[])
    assert clean["removed"] == [] and clean["esg"]["weights"] == clean["non_esg"]["weights"]
    assert "error" in price_of_values(esg, {"OIL": 1.0}, as_of, market=m, events=[])


def test_no_output_names_a_target_size_or_gives_advice():
    """Spec 24 resolution 7 and red gate 1: no output phrases the size as a target, and none gives advice."""
    m, as_of = _market()
    outs = [tipping_point(LOW, {"SAFE": 1.0}, "HOT", [], as_of, market=m, events=[], max_weight=0.12),
            comparison_menu(LOW, {"SAFE": 1.0}, {"op": "set", "ticker": "HOT", "weight": 0.12}, [], as_of,
                            market=m, events=[]),
            sensitivity(LOW, {"HOT": 0.40, "SAFE": 0.60}, _analysis(-0.345, universe=UNI)),
            price_of_values({**LOW, "esg": True}, {"SAFE": 0.6, "OIL": 0.4}, as_of, market=m, events=[])]
    text = json.dumps(outs, default=str).lower()
    assert "largest size" not in text and "inside your limits in this history" not in text
    assert not any(f" {w} " in text.replace('"', " ") for w in ("buy", "sell", "hold", "should", "recommend"))



def test_a_date_with_no_prices_is_one_plain_sentence():
    """Ledger 0: an expected failure is {"error": sentence}, never an exception or a silent empty curve."""
    m, _ = _market()
    tp = tipping_point(LOW, {"SAFE": 1.0}, "HOT", [], "2023-06-30", market=m, events=[], max_weight=0.05)
    assert set(tp) == {"error"} and tp["error"].endswith(".")
    menu = comparison_menu(LOW, {"SAFE": 1.0}, {"op": "set", "ticker": "HOT", "weight": 0.05}, [], "2023-06-30",
                           market=m, events=[])
    assert menu == tp
    m2, as_of = _market()
    ok = tipping_point(LOW, {"SAFE": 1.0}, "HOT", [], as_of, market=m2, events=[], max_weight=0.0)
    assert (ok["source"], ok["as_of"]) == ("tools.allocation", as_of)

ROBERT_P = {"goal": "preservation", "horizon_years": 4, "risk": "moderate", "esg": False, "crypto": False,
            "capacity": 90000, "reaction_2022": "held"}
ROBERT = {"XIU.TO": 0.45, "XBB.TO": 0.35, "GLD": 0.10, "ZST.TO": 0.10}
NEEDS_DATA = pytest.mark.skipif(not (config.STARTER_DIR / "prices_daily.csv").exists(), reason="starter data not present")
NEEDS_HOLDINGS = pytest.mark.skipif(        # ruling R12 (D Task 6b): without the list today's funds are not looked through
    not (config.STARTER_DIR.parent / "etf_holdings.csv").exists(),
    reason="data/etf_holdings.csv not present: a fresh clone runs in direct mode, so today's verdict has caveats")


@NEEDS_DATA
@NEEDS_HOLDINGS
def test_robert_floor_breaks_between_8_and_9_percent_nvda():
    """Spec 3 and pitfall 5: at 8 % NVDA the worst drop is −15.00004 %, inside −15 % after the 0.1 pp rounding; 9 %
    breaks it. The film's slider beat."""
    tp = tipping_point(ROBERT_P, ROBERT, "NVDA", [], "2026-11-12", families=["tariffs"], amount=600000, max_weight=0.40)
    pts = {round(p["weight"], 2): p for p in tp["curve"]}
    assert tp["max_weight"] == pytest.approx(0.08) and len(tp["curve"]) == 41 and tp["still_failing"] is None
    assert pts[0.08]["fails"] == 0 and pts[0.08]["max_drawdown"] == pytest.approx(-0.15, abs=1e-4)
    assert pts[0.08]["max_drawdown"] < -0.15 and governance.round_pp(pts[0.08]["max_drawdown"]) == -15   # rounded, it passes
    assert pts[0.09]["fails"] >= 1 and pts[0.09]["max_drawdown"] == pytest.approx(-0.1564, abs=0.001)
    assert pts[0.0]["verdict"] == "Compatible" and pts[0.0]["max_drawdown"] == pytest.approx(-0.1061, abs=0.001)
    after = apply_change(ROBERT, {"op": "set", "ticker": "NVDA", "weight": 0.40})
    ev = governance.evaluate(ROBERT_P, after, ["tariffs"], "2026-11-12", amount=600000, detail=False)
    s = sensitivity(ROBERT_P, after, ev["analysis"], limits=ev["limits"])
    assert s["floor_flip"] == pytest.approx(-0.345, abs=0.001) and "floor" in s["sentence"]
