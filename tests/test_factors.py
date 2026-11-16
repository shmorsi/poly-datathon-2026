"""tools/factors.py (lane sc-b, "Build your own shock"): the pure rules on synthetic bundles first (tools.data.make_market,
never real files), the look-ahead scramble (red gate 3), then Robert on the real data (skips without the starter)."""
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tools import data
from tools import factors as F

STARTER = (Path(__file__).resolve().parents[1] / "data" / "starter" / "prices_daily.csv").is_file()
NEEDS_DATA = pytest.mark.skipif(not STARTER, reason="starter data not present")
ADVICE = re.compile(r"\b(buy|sell|hold|should|recommend|safe|allowed|you can)\b", re.I)
ROBERT_TODAY = {"XIU.TO": 0.45, "XBB.TO": 0.35, "GLD": 0.1, "ZST.TO": 0.1}
ROBERT_AFTER = {"XIU.TO": 0.27, "XBB.TO": 0.21, "GLD": 0.06, "ZST.TO": 0.06, "NVDA": 0.4}


def _synthetic(seed=7, end="2026-11-12"):
    """Prices (CAD) for the factor tickers plus NVDA (1.5 x QQQ) and XBB.TO (-6 x the yield's change), USD/CAD and a
    10-year yield, on business days from the starter's first day."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(F.START, end)
    n = len(days)
    mkt = rng.normal(0.0003, 0.009, n)
    r = {"SPY": mkt + rng.normal(0, 0.003, n), "XIU.TO": 0.7 * mkt + rng.normal(0, 0.006, n),
         "GLD": rng.normal(0.0002, 0.008, n), "XOM": rng.normal(0.0004, 0.015, n),
         "CNQ.TO": rng.normal(0.0004, 0.016, n), "ENB.TO": rng.normal(0.0002, 0.009, n)}
    r["QQQ"] = 1.2 * mkt + rng.normal(0, 0.006, n)
    dy = rng.normal(0, 0.0006, n)
    r["NVDA"] = 1.5 * r["QQQ"] + rng.normal(0, 0.004, n)
    r["XBB.TO"] = -6.0 * dy + rng.normal(0, 0.0005, n)
    prices = pd.DataFrame({t: 100 * np.cumprod(1 + v) for t, v in r.items()}, index=days)
    yld = pd.Series(0.02 + np.cumsum(dy), index=days, name="rates")
    fx = pd.Series(1.3 * np.exp(np.cumsum(rng.normal(0, 0.003, n))), index=days, name="usdcad")
    return prices, yld, fx


def _market(prices, fx):
    return data.make_market(prices, fx=fx)


@pytest.fixture(scope="module")
def synth():
    prices, yld, fx = _synthetic()
    return {"prices": prices, "yield": yld, "fx": fx, "market": _market(prices, fx)}


# --- the pure rules -----------------------------------------------------------------------------------------------
def test_apply_shocks_sums_beta_times_shock_and_clamps_a_holding_at_minus_100():
    sens = {"A": {"betas": {f: 0.0 for f in F.IDS} | {"tech": 2.0, "rates": -5.0}},
            "B": {"betas": {f: 0.0 for f in F.IDS} | {"tech": 4.0}}}
    r = F.apply_shocks({"A": 0.5, "B": 0.3, "C": 0.2}, sens, {"tech": -0.3, "rates": 0.01})
    assert r["holdings"]["A"] == pytest.approx(2.0 * -0.3 - 5.0 * 0.01)
    assert r["holdings"]["B"] == -1.0                                    # 4 x -30 % is -120 %: never below -100 %
    assert r["contributions"]["A"] == pytest.approx(0.5 * -0.65) and r["uncovered"] == ["C"]
    assert r["move"] == pytest.approx(0.5 * -0.65 + 0.3 * -1.0) and r["covered"] == pytest.approx(0.8)


def test_floor_status_rounds_both_sides_like_the_verdict():
    assert F.floor_status(-0.15, -0.15) == "held"
    assert F.floor_status(-0.1500004, -0.15) == "held"                 # pitfall 5: rounded to 0.1 pp first
    assert F.floor_status(-0.1505, -0.15) == "touched"                 # -15.1 %: beyond by 0.1 point
    assert F.floor_status(-0.16, -0.15) == "touched"                   # beyond by exactly 1 point (R11)
    assert F.floor_status(-0.161, -0.15) == "broke"
    assert F.floor_status(0.06, -0.15) == "held" and F.floor_status(None, -0.15) is None


def test_dollars_are_whole_and_round_half_up():
    assert F.dollars(600000, -0.2412775) == -144767 and F.dollars(None, -0.1) is None and F.dollars(1000, 0.0005) == 1


def test_bounds_are_three_times_the_largest_move_and_a_price_never_falls_past_100():
    b = F.bounds({f: (0.02 if F.UNIT[f] == "pp" else 0.5) for f in F.IDS})
    assert b["rates"] == pytest.approx([-0.06, 0.06]) and b["tech"] == pytest.approx([-1.0, 1.5])
    assert b["usd_cad"] == pytest.approx([-1.0, 1.5])


def test_check_shocks_refuses_with_plain_words():
    b = F.bounds({f: (0.02 if F.UNIT[f] == "pp" else 0.2) for f in F.IDS})
    assert F.check_shocks({"tech": -0.3, "rates": None}, b) == {"tech": -0.3}
    for bad, words in (({"techno": -0.1}, "Unknown factor: techno"), ({"tech": "x"}, "must be a number"),
                       ({"tech": True}, "must be a number"), ({"tech": float("nan")}, "must be a number"),
                       ({"rates": 0.07}, "outside the range"), ({}, "at least one"), (None, "at least one")):
        with pytest.raises(F.ShockError, match=words):
            F.check_shocks(bad, b)


def test_largest_moves_reads_weekly_closes_within_52_weeks():
    days = pd.bdate_range("2022-01-03", "2023-12-29")
    lv = pd.DataFrame({f: 100.0 for f in F.IDS}, index=days)
    lv["rates"] = 0.02
    lv.loc["2022-06-01":"2022-09-30", "tech"] = 70.0                   # a 30 % fall, then back
    lv.loc["2022-06-01":"2022-09-30", "rates"] = 0.035                 # 1.5 points
    got = F.largest_moves(lv)
    assert got["tech"] == pytest.approx(100 / 70 - 1) and got["rates"] == pytest.approx(0.015) and got["gold"] == 0.0


def test_sensitivities_recover_the_betas_and_a_factor_holding_is_one_on_itself(synth):
    m, y = synth["market"], synth["yield"]
    lv = F.factor_levels(m, y)
    fw = F.weekly(lv).dropna()
    s = F.sensitivities(["NVDA", "XBB.TO", "SPY", "NOPE"], fw, F.holding_weekly(m, ["NVDA", "XBB.TO", "SPY"]))
    # NVDA is 1.5 x QQQ: shrinkage shares that exposure among the collinear stock factors, so the check is the engine's
    # response to a tech shock whose other factors move with it (fill), not one coefficient
    hit = F.apply_shocks({"NVDA": 1.0}, s, F.fill({"tech": -0.3}, fw))["move"]
    assert hit == pytest.approx(1.5 * -0.3, rel=0.1) and s["NVDA"]["r2"] > 0.8
    assert s["XBB.TO"]["betas"]["rates"] == pytest.approx(-6.0, rel=0.12)
    assert s["SPY"]["betas"] == {f: (1.0 if f == "us_stocks" else 0.0) for f in F.IDS} and s["NOPE"] is None


def test_fill_keeps_the_named_moves_and_moves_the_others_with_them(synth):
    fw = F.weekly(F.factor_levels(synth["market"], synth["yield"])).dropna()
    got = F.fill({"tech": -0.3}, fw)
    cov = fw.cov()
    assert got["tech"] == -0.3 and set(got) == set(F.IDS)
    assert got["us_stocks"] == pytest.approx(cov.loc["us_stocks", "tech"] / cov.loc["tech", "tech"] * -0.3)
    assert got["us_stocks"] < -0.1                                     # the market moves with tech
    assert F.fill({f: 0.01 for f in F.IDS}, fw) == {f: 0.01 for f in F.IDS}


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def test_build_on_a_synthetic_bundle_has_the_contract_shape(synth):
    sc = F.build("2026-11-12", {"XIU.TO": 0.45, "XBB.TO": 0.35, "GLD": 0.2}, {"NVDA": 0.4, "XIU.TO": 0.6},
                 amount=600000, floor=-0.15, market=synth["market"], yield10=synth["yield"])
    assert sc["kind"] == "hypothetical" and [f["id"] for f in sc["factors"]] == list(F.IDS)
    assert [p["id"] for p in sc["presets"]] == [p[0] for p in F.PRESETS]
    assert [v["episode"] for v in sc["validation"]] == [c[0] for c in F.CHECKS]
    for p in sc["presets"]:
        assert set(p["shocks"]) == set(F.IDS) and set(p["today"]) >= {"fall", "dollars", "floor_status"}
        assert p["today"]["floor_status"] in ("held", "touched", "broke") and p["contributions_mix"] == "after"
        assert sum(p["contributions"].values()) == pytest.approx(p["after"]["fall"], abs=1e-5)
        assert p["after"]["dollars"] == F.dollars(600000, p["after"]["fall"]) or abs(
            p["after"]["dollars"] - 600000 * p["after"]["fall"]) <= 1
        lo_hi = sc["bounds"]
        assert all(lo_hi[f][0] <= p["shocks"][f] <= lo_hi[f][1] for f in F.IDS)
    tariff = next(p for p in sc["presets"] if p["id"] == "tariffs_2025")
    assert tariff["measured"] == list(F.IDS) and tariff["implied"] == []
    assert tariff["window"]["start"] == "2025-04-02" and "2025-04-03" <= tariff["window"]["end"] <= "2025-04-09"
    tech = next(p for p in sc["presets"] if p["id"] == "tech_2022")
    assert tech["measured"] == ["tech"] and tech["shocks"]["tech"] < 0 and tech["window"]["end"] <= "2022-12-31"
    gaps = [v for v in sc["validation"] if v["gap_pp"] is not None]
    assert gaps and all(v["gap_pp"] == v["gap_pp_after"] for v in gaps)
    json.dumps(sc, allow_nan=False)
    words = list(_strings(sc))
    assert not [s for s in words if ADVICE.search(s)]                   # red gate 1
    assert not [s for s in words if any(m in s for m in "●◐○")]         # R16: the markers are drawn, never text


def test_no_look_ahead_rows_after_as_of_change_nothing(synth):
    """Red gate 3: every price, rate and yield dated after as_of is scrambled; the scenarios are identical."""
    as_of = "2024-06-28"
    prices, yld, fx = synth["prices"], synth["yield"], synth["fx"]
    rng = np.random.default_rng(1)
    later = prices.index > pd.Timestamp(as_of)
    p2 = prices.copy()
    p2.loc[later] = rng.uniform(1, 500, size=p2.loc[later].shape)
    y2, fx2 = yld.copy(), fx.copy()
    y2[later], fx2[later] = rng.uniform(0, 0.2, later.sum()), rng.uniform(0.5, 3, later.sum())
    args = dict(amount=600000, floor=-0.15)
    a = F.build(as_of, {"XIU.TO": 0.5, "XBB.TO": 0.5}, {"NVDA": 0.4, "XBB.TO": 0.6},
                market=_market(prices, fx), yield10=yld, **args)
    b = F.build(as_of, {"XIU.TO": 0.5, "XBB.TO": 0.5}, {"NVDA": 0.4, "XBB.TO": 0.6},
                market=_market(p2, fx2), yield10=y2, **args)
    assert a == b and a["as_of"] == as_of
    assert "tariffs_2025" not in [p["id"] for p in a["presets"]]        # a window the date does not reach is left out


def test_facts_rows_carry_every_number_with_its_kind_and_unique_labels(synth):
    rows = {}

    def fact(label, value, unit, entity, kind, *, path, source):
        tid = f"T{len(rows) + 1}"
        rows[tid] = {"label": label, "value": value, "unit": unit, "entity": entity, "kind": kind, "path": path}
        return tid

    sc = F.result_key({"today": {"XIU.TO": 0.5, "XBB.TO": 0.5}, "after": {"NVDA": 0.4, "XBB.TO": 0.6},
                       "amount": 600000, "floor": -0.15, "as_of": "2026-11-12"}, fact,
                      market=synth["market"], yield10=synth["yield"])
    labels = [r["label"] for r in rows.values()]
    assert len(labels) == len(set(labels)) and set(sc["facts"].values()) == set(rows)
    kinds = {r["path"].split(".")[1]: set() for r in rows.values()}
    for r in rows.values():
        kinds[r["path"].split(".")[1]].add(r["kind"])
    assert kinds["betas"] == {"assumption"} and kinds["validation"] == {"fact", "assumption"}
    assert kinds["presets"] == {"fact", "assumption", "fiction"}
    tid = sc["facts"]["presets.tech_2022.after.fall"]
    assert rows[tid]["value"] == next(p for p in sc["presets"] if p["id"] == "tech_2022")["after"]["fall"]
    assert rows[tid]["kind"] == "fiction" and not [s for s in labels if ADVICE.search(s)]


def test_without_the_factor_series_there_is_no_engine_never_a_guess(synth):
    small = data.make_market(synth["prices"][["XIU.TO", "XBB.TO", "GLD"]])
    assert F.result_key({"today": {"XIU.TO": 1.0}, "after": None, "as_of": "2026-11-12"}, None, market=small,
                        yield10=synth["yield"]) is None
    assert F.result_key({"today": {}, "as_of": "2026-11-12"}) is None


# --- Robert on the real data ----------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def robert():
    if not STARTER:
        pytest.skip("starter data not present")
    return F.build("2026-11-12", ROBERT_TODAY, ROBERT_AFTER, amount=600000, floor=-0.15)


@NEEDS_DATA
def test_robert_presets_are_measured_from_the_record(robert):
    m = data.load_market("2026-11-12")
    tech = next(p for p in robert["presets"] if p["id"] == "tech_2022")
    w = tech["window"]
    qqq = m["prices"]["QQQ"]
    assert tech["shocks"]["tech"] == pytest.approx(qqq[w["end"]] / qqq[w["start"]] - 1, abs=1e-6)
    assert w["start"] < w["end"] <= "2022-12-31" and tech["shocks"]["tech"] < -0.25
    rates = next(p for p in robert["presets"] if p["id"] == "rates_2022")
    y = F.ten_year("2026-11-12")
    assert rates["shocks"]["rates"] == pytest.approx(y[:rates["window"]["end"]].iloc[-1] - y[:rates["window"]["start"]].iloc[-1], abs=1e-9)
    cad = next(p for p in robert["presets"] if p["id"] == "cad_slide")
    assert cad["shocks"]["usd_cad"] > 0.05 and cad["headline"] == "usd_cad"
    assert robert["betas"]["XBB.TO"]["rates"] < -4 and robert["fit"]["XBB.TO"]["r2"] > 0.8   # a bond fund falls as yields rise


@NEEDS_DATA
def test_robert_ai_slump_holds_today_and_is_too_close_to_call_with_the_move(robert):
    """The section's example: a made-up AI and chip slump of 2022's size. Today's mix stays 9.7 points above his floor,
    beyond the engine's widest miss for it (1.2 points): held. With 40 % NVDA the mix falls 9.1 points past the floor,
    but the engine missed that mix by up to 11.5 points on a real window (NVDA's own 2023 rally): too close to call."""
    tech = next(p for p in robert["presets"] if p["id"] == "tech_2022")
    assert (tech["today"]["floor_status"], tech["today"]["margin_pp"], tech["today"]["gap_pp"]) == ("held", 9.7, 1.2)
    assert (tech["after"]["floor_status"], tech["after"]["margin_pp"], tech["after"]["gap_pp"]) == ("too_close", -9.1, 11.5)
    assert robert["gaps"] == {"today": 1.2, "after": 11.5}
    assert tech["after"]["dollars"] == F.dollars(600000, tech["after"]["fall"])
    assert min(tech["contributions"], key=tech["contributions"].get) == "NVDA"


@NEEDS_DATA
def test_robert_engine_check_reproduces_the_real_windows_within_a_few_points(robert):
    rows = {v["episode"]: v for v in robert["validation"]}
    assert set(rows) == {"drawdown_2022", "tariffs_2025", "rates_2023"}
    for ep in ("drawdown_2022", "tariffs_2025"):
        assert abs(rows[ep]["gap_pp_today"]) <= 3.0 and abs(rows[ep]["gap_pp_after"]) <= 4.0
    m = data.load_market("2026-11-12")
    v = rows["tariffs_2025"]
    s = F.portfolio_series(ROBERT_TODAY, v["window"]["start"], v["window"]["end"], "2026-11-12", market=m)["values"]
    assert v["real_today"] == pytest.approx(s[-1] / s[0] - 1, abs=1e-6)


@NEEDS_DATA
def test_result_extras_adds_the_key_with_its_facts_rows_in_the_result(monkeypatch):
    """The one hunk in result_extras: result.scenarios, its numbers as facts rows (trace ids), evidence for each."""
    import pipeline
    import result_extras as rx
    r = {"as_of": "2026-11-12", "amount": 600000, "portfolio": dict(ROBERT_AFTER),
         "baseline": {"portfolio": dict(ROBERT_TODAY)}, "limits": {"floor": -0.15},
         "metrics": {"today": {"max_drawdown": -0.1}, "after": {"max_drawdown": -0.3}},
         "tipping_point": {"ticker": "NVDA"}, "trace": [], "facts": {},
         "scenario": {"change": {"op": "set", "ticker": "NVDA", "weight": 0.4}}}
    monkeypatch.setattr(rx, "KEYS", ("scenarios", "evidence"))
    rx.extend(r, engine=pipeline.real_engine())
    sc = r["scenarios"]
    assert sc["kind"] == "hypothetical" and set(sc["facts"].values()) <= set(r["facts"])
    assert set(r["evidence"]) == set(r["facts"]) and not [t for t in r["trace"] if "error" in t["outputs"]]
    row = r["facts"][sc["facts"]["presets.tech_2022.after.fall"]]
    tech = next(p for p in sc["presets"] if p["id"] == "tech_2022")
    assert row["kind"] == "fiction" and row["value"] == pytest.approx(tech["after"]["fall"]) and row["unit"] == "pct"
    assert r["facts"][sc["facts"]["betas.XBB.TO.rates"]]["kind"] == "assumption"
    mine = lambda: [t for t in r["trace"] if t["tool"] == "result_extras.scenarios"]       # noqa: E731
    n = len(mine())
    rx.extend(r, engine=pipeline.real_engine())                          # a later pass (deep keys) adds no row of ours
    assert len(mine()) == n and r["scenarios"] is sc
    json.dumps(pipeline.jsonable(r), allow_nan=False)


# --- POST /api/scenario -------------------------------------------------------------------------------------------
@pytest.fixture()
def client(monkeypatch):
    import server
    from fastapi.testclient import TestClient
    for name in (server.PASSWORD_ENV, server.ORIGIN_SECRET_ENV, server.REQUIRE_PASSWORD_ENV):
        monkeypatch.delenv(name, raising=False)
    return TestClient(server.app)


ROUTE_BODY = {"portfolio": ROBERT_AFTER, "baseline": ROBERT_TODAY, "limits": {"floor": -0.15}, "amount": 600000,
              "shocks": {"energy": 0.5, "tech": -0.3}}


@NEEDS_DATA
def test_the_route_answers_one_custom_shock_in_the_shape_of_a_preset(client):
    r = client.post("/api/scenario", json=ROUTE_BODY)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["kind"] == "hypothetical" and out["measured"] == ["tech", "energy"] and set(out["shocks"]) == set(F.IDS)
    assert out["shocks"]["tech"] == -0.3 and out["shocks"]["energy"] == 0.5 and out["implied"]
    assert out["after"]["floor_status"] == "too_close" and out["today"]["floor_status"] == "held"   # -4.8 points vs 11.5
    assert out["after"]["gap_pp"] == out["gaps"]["after"] and out["after"]["margin_pp"] < 0 and out["validation"]
    assert out["after"]["dollars"] == F.dollars(600000, out["after"]["fall"]) or abs(
        out["after"]["dollars"] - 600000 * out["after"]["fall"]) <= 1
    assert out["facts"]["after.fall"]["kind"] == "fiction" and out["facts"]["shocks.tech"]["kind"] == "fiction"
    assert out["facts"]["shocks.us_stocks"]["kind"] == "assumption"
    flat = client.post("/api/scenario", json={**ROUTE_BODY, "fill": False}).json()
    assert flat["shocks"]["us_stocks"] == 0.0 and flat["implied"] == []
    assert not [s for s in _strings(out) if ADVICE.search(s)]


@NEEDS_DATA
@pytest.mark.parametrize("change, words", [
    ({"shocks": {"rates": 0.09}}, "outside the range this engine accepts"),
    ({"shocks": {"oil": 0.5}}, "Unknown factor: oil"),
    ({"shocks": {"tech": True}}, "must be a number"),
    ({"shocks": {"tech": "-0.3"}}, "must be a number"),
    ({"shocks": {}}, "at least one"),
    ({"portfolio": {"XIU.TO": 0.5}}, "add up to 50 %"),
    ({"portfolio": {"ZZZ": 1.0}}, "not in the dataset"),
    ({"limits": {"floor": 0.2}}, "The floor must be a fall"),
    ({"as_of": "2031-01-01"}, ""),
])
def test_the_route_refuses_in_plain_words(client, change, words):
    r = client.post("/api/scenario", json={**ROUTE_BODY, **change})
    assert r.status_code == 422, r.text
    assert words in r.json()["message"] and "Traceback" not in r.text


def test_the_route_without_the_starter_data_is_503_never_500(client, monkeypatch, tmp_path):
    monkeypatch.setattr(data, "DATA_DIR", tmp_path)
    r = client.post("/api/scenario", json=ROUTE_BODY)
    assert r.status_code == 503 and "starter data" in r.json()["message"]


def test_anchors_are_measured_moves_inside_the_bounds_and_never_after_as_of(synth):
    a = F.anchors("2026-11-12", market=synth["market"], yield10=synth["yield"])
    assert a["anchors"] and {r["factor"] for r in a["anchors"]} <= set(F.IDS)
    assert all(a["bounds"][r["factor"]][0] <= r["value"] <= a["bounds"][r["factor"]][1] for r in a["anchors"])
    assert all(r["window"]["start"] < r["window"]["end"] <= a["as_of"] for r in a["anchors"])
    assert {r["id"] for r in a["anchors"]} >= {"tech_2022", "tariffs_2025", "cad_slide", "rates_2023"}
    early = F.anchors("2022-12-15", market=synth["market"], yield10=synth["yield"])
    assert all(r["window"]["end"] <= "2022-12-15" for r in early["anchors"])
    assert "tech_2022" not in {r["id"] for r in early["anchors"]}        # 2022 is not over on that date


def test_each_factor_row_carries_the_bounds_the_route_accepts(synth):
    """Lane sc-u's sliders read factors[i].bounds: the same [lo, hi] as result.scenarios.bounds and check_shocks."""
    sc = F.build("2026-11-12", {"XIU.TO": 1.0}, None, market=synth["market"], yield10=synth["yield"])
    for f in sc["factors"]:
        assert f["bounds"] == sc["bounds"][f["id"]] and f["largest"] == sc["largest"][f["id"]]
        assert F.check_shocks({f["id"]: f["bounds"][1]}, sc["bounds"]) == {f["id"]: f["bounds"][1]}


def test_the_debrief_is_written_without_the_scenario_rows_and_result_facts_keeps_them(synth, monkeypatch):
    """Ruling (Sun Nov 15, 13:00): the explainer (draft 1 and the re-ask) and the output check's grounding get
    result.facts minus the ids result.scenarios.facts names (never matched on labels); result.facts keeps every row,
    so the section's numbers keep their ids and threads and the receipt can trace them."""
    import types

    import pipeline
    trace = pipeline.Trace("2026-11-12")
    r = {"as_of": "2026-11-12", "question": "What if I put 40 % in NVIDIA?", "facts": {}, "trace": trace.rows,
         "guardrail": {}}
    hist = trace.add("COMPARE", "evaluate.today", inputs={"path": "metrics.today.max_drawdown"})
    r["facts"][hist] = {"label": "Worst drop today", "value": -0.1, "unit": "pct", "entity": "today", "kind": "fact"}

    def fact(label, value, unit, entity, kind, *, path, source):
        tid = trace.add("COMPARE", "result_extras.scenarios", inputs={"path": path}, outputs={"value": value})
        r["facts"][tid] = {"label": label, "value": value, "unit": unit, "entity": entity, "kind": kind}
        return tid

    r["scenarios"] = F.result_key({"today": {"XIU.TO": 0.5, "XBB.TO": 0.5}, "after": {"NVDA": 0.4, "XBB.TO": 0.6},
                                   "amount": 600000, "floor": -0.15, "as_of": "2026-11-12"}, fact,
                                  market=synth["market"], yield10=synth["yield"])
    mine = {t["id"] for t in trace.rows if str(t["inputs"].get("path", "")).startswith("scenarios.")}
    assert len(mine) > 20 and mine <= set(r["facts"]) and set(r["scenarios"]["facts"].values()) == mine
    seen = []
    eng = types.SimpleNamespace(explain=lambda facts, **kw: seen.append(dict(facts)) or {"text": "x", "debrief": {}},
                                memory=None, apply_guardrail=lambda *a, **kw: {},
                                grounding_source=lambda facts, context: seen.append(dict(facts)) or "grounding")
    run = types.SimpleNamespace(r=r, engine=eng, context={"verdict_words": "Inside your limits"}, memory=None,
                                trace=trace, deadline=pipeline._now() + 600, cut=None)
    pipeline._draft(run)
    pipeline._draft(run, retry_numbers=["a named defect"], previous={"verdict_sentence": "x", "sections": {},
                                                                     "sentences": []})
    monkeypatch.setattr(pipeline, "_guard_text", lambda debrief: "x")
    pipeline._output_check(run, {}, 1)
    assert len(seen) == 3 and all(set(f) == set(r["facts"]) - mine and hist in f for f in seen)
    assert not [f for f in seen for tid in f if tid in mine] and mine <= set(r["facts"])    # still in result.facts
    drafts = [t for t in trace.rows if t["tool"] == "explain.draft"]
    assert [d["inputs"]["facts"] for d in drafts] == [len(r["facts"]) - len(mine)] * 2     # the count actually sent
    assert pipeline._debrief_facts({"facts": {"T1": {}}, "scenarios": None}) == {"T1": {}}  # no scenarios: unchanged
    assert pipeline._debrief_facts({"facts": {"T1": {}}, "scenarios": {"facts": ["T1"]}}) == {"T1": {}}


def test_too_close_when_the_margin_is_inside_the_engines_own_miss():
    """Red gate 4 (controller, 13:15): |fall - floor| in points after round_pp <= the widest validation gap for that
    mix reads too_close; beyond it the floor classes stand."""
    assert F.judge(-0.145, -0.15, 3.3) == ("too_close", 0.5)              # Robert's open scenario: 0.5 vs 3.3 points
    assert F.judge(-0.20, -0.15, 3.3) == ("broke", -5.0)                  # 5 points past it: beyond the miss
    assert F.judge(-0.05, -0.15, 3.3) == ("held", 10.0)                   # clear held
    assert F.judge(-0.25, -0.15, 3.3) == ("broke", -10.0)                 # clear broke
    assert F.judge(-0.183, -0.15, 3.3) == ("too_close", -3.3)             # the edge counts as too close
    assert F.judge(-0.145, -0.15, None) == ("held", 0.5) and F.judge(None, -0.15, 1.0) == (None, None)


def test_too_close_held_and_broke_on_a_fixture_sized_book(synth):
    """The same rule through the engine on the synthetic book: the floor set at the fall itself, far below it, far above."""
    mix, shocks = {"NVDA": 0.4, "XBB.TO": 0.6}, {"tech": -0.3}
    args = dict(baseline={"XIU.TO": 0.5, "XBB.TO": 0.5}, amount=600000, market=synth["market"], yield10=synth["yield"])
    probe = F.custom(mix, shocks, floor=-0.5, **args)
    fall, gap = probe["after"]["fall"], probe["gaps"]["after"]
    assert gap is not None and probe["after"]["gap_pp"] == gap and fall < -0.05
    at = F.custom(mix, shocks, floor=round(fall, 4), **args)["after"]
    assert at["floor_status"] == "too_close" and abs(at["margin_pp"]) <= gap
    held = F.custom(mix, shocks, floor=max(-1.0, fall - (gap + 5) / 100), **args)["after"]
    assert held["floor_status"] == "held" and held["margin_pp"] > gap
    broke = F.custom(mix, shocks, floor=min(0.0, fall + (gap + 5) / 100), **args)["after"]
    assert broke["floor_status"] == "broke" and broke["margin_pp"] < -gap
    sc = F.build("2026-11-12", {"XIU.TO": 0.5, "XBB.TO": 0.5}, mix, amount=600000, floor=round(fall, 4),
                 market=synth["market"], yield10=synth["yield"])
    assert sc["gaps"] == F.widest_gaps(sc["validation"]) and all(
        p["after"]["gap_pp"] == sc["gaps"]["after"] for p in sc["presets"])


def test_a_refresh_reuses_the_rows_and_adds_only_the_new_numbers(synth):
    """result_extras --refresh scenarios: the same paths keep their ids (never twice), values follow the new answer, a
    number an older pass did not register (here: the margins) gets its row."""
    import pipeline
    trace = pipeline.Trace("2026-11-12")
    r = {"facts": {}, "trace": trace.rows}

    def fact(label, value, unit, entity, kind, *, path, source):
        tid = trace.add("COMPARE", "result_extras.scenarios", inputs={"path": path}, outputs={"value": value})
        r["facts"][tid] = {"label": label, "value": value, "unit": unit, "entity": entity, "kind": kind}
        return tid

    ins = {"today": {"XIU.TO": 0.5, "XBB.TO": 0.5}, "after": {"NVDA": 0.4, "XBB.TO": 0.6}, "amount": 600000,
           "floor": -0.15, "as_of": "2026-11-12"}
    kw = dict(market=synth["market"], yield10=synth["yield"], result=r)
    first = F.result_key(ins, fact, **kw)
    n = len(r["facts"])
    old = {k: v for k, v in first["facts"].items() if k.endswith(".margin_pp")}       # an older pass lacked these
    for tid in old.values():
        del r["facts"][tid]
    second = F.result_key({**ins, "floor": -0.3}, fact, **kw)
    assert len(r["facts"]) == n and {k: v for k, v in second["facts"].items() if k not in old} == {
        k: v for k, v in first["facts"].items() if k not in old}
    labels = [f["label"] for f in r["facts"].values()]
    assert len(labels) == len(set(labels))
    tech = next(p for p in second["presets"] if p["id"] == "tech_2022")
    assert r["facts"][second["facts"]["presets.tech_2022.after.margin_pp"]]["value"] == pytest.approx(
        tech["after"]["margin_pp"] / 100)
