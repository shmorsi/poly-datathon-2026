"""Task 1 tests: the FAKE starter files and the FAKE sample Result (spec section 12).

The Result key sets below are the spec section 12 contract.
The page, the pipeline and the rules engine build against
data/fake/result.json, so a key added or dropped here is a contract change (ask the lead).
"""
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tools.data import (DATA_DIR, DATASET_END, load_market, load_prices_cad, load_universe,
                        make_market, mean_policy_rate)

FAKE_RESULT = Path("data/fake/result.json")
FAKE_TM = Path("data/fake/result_time_machine.json")
FAKE = "data/fake/starter"          # Task 2: the synthetic starter pack (6 tickers, section 9 format)


# --- Task 2 helpers: tiny starter packs written to tmp_path --------------------------------------
def write_starter(dst, adj, *, usdcad=1.25):
    """Write the four starter CSVs (section 9 columns) for {ticker: {iso date: adj_close}}.

    close == adj_close, one FX row per price date, a one-row policy-rate file. `.TO` and `-USD`
    tickers get TSX/CAD and Crypto/USD universe rows; everything else NASDAQ/USD.
    """
    dst = Path(dst)
    dst.mkdir(parents=True, exist_ok=True)
    uni, rows = [], []
    for i, (t, pts) in enumerate(adj.items(), 1):
        crypto, cad = t.endswith("-USD"), t.endswith(".TO")
        uni.append((f"A{i:02d}", t, t, "crypto" if crypto else "equity",
                    "Crypto (24/7)" if crypto else "TSX" if cad else "NASDAQ",
                    "CAD" if cad else "USD", "Energy" if t == "CNQ.TO" else "Unknown"))
        rows += [(d, t, v, v, v, v, v, 1000, "CAD" if cad else "USD") for d, v in pts.items()]
    pd.DataFrame(uni, columns=["asset_id", "ticker", "name", "asset_class", "market", "currency",
                               "sector"]).to_csv(dst / "assets_universe.csv", index=False)
    pd.DataFrame(rows, columns=["date", "ticker", "open", "high", "low", "close", "adj_close",
                                "volume", "currency"]).sort_values(["ticker", "date"]).to_csv(
        dst / "prices_daily.csv", index=False)
    days = sorted({d for pts in adj.values() for d in pts})
    pd.DataFrame({"date": days, "usdcad": usdcad, "cadusd": round(1 / usdcad, 6)}).to_csv(
        dst / "fx_usdcad_daily.csv", index=False)
    pd.DataFrame([(days[0], "V39079", 4.0, "percent", "daily", "policy rate", "test")],
                 columns=["date", "series_id", "value", "unit", "frequency", "label", "source"]
                 ).to_csv(dst / "macro_rates.csv", index=False)
    return dst


def scramble_after(src, dst, as_of):
    """Copy the starter files, then permute adj_close, close, the dividend/split values and usdcad
    among the rows dated after as_of (and shift the later policy-rate values: every later row is
    poison, red gate 3)."""
    src, dst = Path(src), Path(dst)
    dst.mkdir(parents=True, exist_ok=True)
    for name in ("assets_universe", "prices_daily", "fx_usdcad_daily", "macro_rates"):
        shutil.copy(src / f"{name}.csv", dst / f"{name}.csv")
    rng = np.random.default_rng(0)
    prices = pd.read_csv(dst / "prices_daily.csv", dtype={"date": str})
    late = (prices.date > as_of).to_numpy()
    prices.loc[late, "adj_close"] = rng.permutation(prices.loc[late, "adj_close"].to_numpy())
    prices.loc[late, "close"] = rng.permutation(prices.loc[late, "close"].to_numpy())
    prices.to_csv(dst / "prices_daily.csv", index=False)
    if (src / "corporate_actions.csv").exists():                 # the optional file (the fake pack has none)
        shutil.copy(src / "corporate_actions.csv", dst / "corporate_actions.csv")
        actions = pd.read_csv(dst / "corporate_actions.csv", dtype={"ex_date": str})
        late = (actions.ex_date > as_of).to_numpy()
        actions.loc[late, "value"] = rng.permutation(actions.loc[late, "value"].to_numpy())
        actions.to_csv(dst / "corporate_actions.csv", index=False)
    fx = pd.read_csv(dst / "fx_usdcad_daily.csv", dtype={"date": str})
    late = (fx.date > as_of).to_numpy()
    fx.loc[late, "usdcad"] = rng.permutation(fx.loc[late, "usdcad"].to_numpy())
    fx.to_csv(dst / "fx_usdcad_daily.csv", index=False)
    macro = pd.read_csv(dst / "macro_rates.csv", dtype={"date": str})
    late = ((macro.date > as_of) & (macro.series_id == "V39079")).to_numpy()
    macro.loc[late, "value"] = macro.loc[late, "value"].to_numpy() + rng.uniform(1.0, 5.0, late.sum())
    macro.to_csv(dst / "macro_rates.csv", index=False)
    return dst

RESULT_KEYS = {
    "run_id", "as_of", "mode", "status", "message", "question", "question_type", "pilot", "amount",
    "profile", "limits", "portfolio", "baseline", "aligned", "scenario", "events", "turbulence",
    "series", "metrics", "worst_rolling", "kpis", "risk", "diversification", "lookthrough", "checks",
    "verdict", "tipping_point", "variations", "sensitivity", "attribution", "compare",
    "price_of_values", "time_machine", "deep_history", "facts", "debrief", "receipt", "redteam", "guardrail",
    "trace", "figures", "realized",
}
EVENT_KEYS = {
    "event_id", "date", "title", "description", "family", "sign", "regions", "lat", "lon",
    "source_url", "known", "in_progress", "episode", "confounded", "t0", "window_end", "trough_date",
    "today", "after", "exposed",
}
IMPACT_KEYS = {"trough", "ret_20", "fx_effect", "percentile"}
LIMIT_KEYS = {"floor", "floor_source", "single_stock", "sector", "crypto", "scenario_stress",
              "recovery_days", "risk_share"}
SCENARIO_KEYS = {"type", "families", "event_ids", "reasons", "rejected", "tool_calls", "method",
                 "intent", "check_order", "clarify", "widened", "weather"}
CHECK_KEYS = {"rule", "tier", "status", "value", "limit", "holding", "reason"}
FAMILIES = ["tariffs", "war_oil", "chips", "rates"]
TURB_KEYS = {"n", "worst_today", "worst_after", "mean_after", "evidence", "episodes"}
TRACE_KEYS = {"id", "step", "tool", "inputs", "outputs", "source", "as_of", "ms", "service", "model",
              "usage", "request_id"}
FIGURE_KEYS = {"flight_paths", "storm_map", "turbulence", "risk_share", "diversification",
               "size_curve"}


def load(path):
    return json.loads(Path(path).read_text())


def check_shape(r):
    """Assertions shared by both fake Results (same shape, spec section 12)."""
    assert set(r) - {"_note"} == RESULT_KEYS and "FAKE" in r["_note"]
    assert all(set(e) == EVENT_KEYS for e in r["events"]) and len(r["events"]) >= 4
    assert all(set(e["today"]) == IMPACT_KEYS and set(e["after"]) == IMPACT_KEYS for e in r["events"])
    assert set(r["limits"]) == LIMIT_KEYS and r["limits"]["floor_source"] in ("capacity", "band")
    assert set(r["scenario"]) == SCENARIO_KEYS and "lead_check" not in r["scenario"]
    assert set(r["baseline"]) == {"portfolio", "verdict", "checks", "metrics", "kpis"}
    assert all(set(c) == CHECK_KEYS for c in r["checks"])
    assert all(set(c) == CHECK_KEYS for c in r["baseline"]["checks"])
    assert set(r["turbulence"]) == set(FAMILIES)
    assert all(set(t) == TURB_KEYS for t in r["turbulence"].values())
    assert set(r["series"]) == {"dates", "today", "after", "aligned"}
    assert set(r["metrics"]) == {"today", "after", "aligned"}
    assert set(r["kpis"]) == {"max_drawdown", "scenario_stress", "recovery_days", "exposure_canada"}
    assert all(set(k) == {"value", "limit"} for k in r["kpis"].values())
    assert r["kpis"]["exposure_canada"]["limit"] is None
    assert set(r["risk"]) == {"today", "after"} and all(
        set(v) == {"shares", "bets"} for v in r["risk"].values())
    assert set(r["diversification"]) == {"today", "after"} and all(
        set(v) == {"countries", "currencies", "sectors", "can_risk_share"}
        for v in r["diversification"].values())
    assert set(r["lookthrough"]) == {"today", "after"}
    assert set(r["tipping_point"]) == {"ticker", "max_weight", "curve", "still_failing"}
    assert set(r["tipping_point"]["curve"][0]) == {"weight", "verdict", "fails", "max_drawdown",
                                                   "scenario_shock"}
    assert len(r["variations"]) == 3 and all(
        set(v) == {"label", "change", "verdict", "binding_rule", "max_drawdown", "scenario_shock"}
        for v in r["variations"])
    assert set(r["sensitivity"]) == {"floor_flip", "sentence"}
    assert [c["pilot"] for c in r["compare"]] == ["robert", "mateo", "amira"] and all(
        set(c) == {"pilot", "name", "verdict", "binding_rule", "reason"} for c in r["compare"])
    assert set(r["debrief"]) == {"verdict_sentence", "sections", "sentences"}
    assert set(r["debrief"]["sections"]) == {"data", "why", "limits", "would_change"}
    assert all(set(s) == {"text", "kind", "refs"} for s in r["debrief"]["sentences"])
    assert set(r["guardrail"]) == {"input", "output", "automated_reasoning"}
    assert all(set(f) == {"label", "value", "unit", "entity", "sign", "kind"}
               for f in r["facts"].values())
    assert all(set(t) == TRACE_KEYS for t in r["trace"])
    assert set(r["figures"]) == FIGURE_KEYS and all(
        set(f) == {"data", "layout"} for f in r["figures"].values())
    # Trace and facts share one id space (one trace row per fact).
    assert set(r["facts"]) <= {t["id"] for t in r["trace"]}
    assert len({t["id"] for t in r["trace"]}) == len(r["trace"])
    # Series: monthly, base 100, equal lengths.
    n = len(r["series"]["dates"])
    assert n == 61 or r["as_of"] < "2026-11-12"
    assert all(len(r["series"][k]) == n for k in ("today", "after", "aligned"))
    assert r["series"]["today"][0] == 100.0 and r["series"]["after"][0] == 100.0


def test_fake_result_matches_contract():
    r = load(FAKE_RESULT)
    check_shape(r)
    assert r["as_of"] == "2026-11-12" and r["mode"] == "demo_replay" and r["status"] == "ok"
    assert r["question_type"] == "change" and r["pilot"] == "robert" and r["amount"] == 600000
    assert r["profile"] == {"goal": "preservation", "horizon_years": 4, "risk": "moderate",
                            "esg": False, "crypto": False, "capacity": 90000,
                            "reaction_2022": "held"}
    assert r["limits"]["floor"] == -0.15 and r["limits"]["floor_source"] == "capacity"
    assert abs(sum(r["portfolio"].values()) - 1) < 1e-9 and r["portfolio"]["NVDA"] == 0.40
    assert abs(sum(r["baseline"]["portfolio"].values()) - 1) < 1e-9
    assert r["baseline"]["verdict"] == "Compatible" and r["verdict"] == "Incompatible"
    assert r["tipping_point"]["ticker"] == "NVDA" and r["tipping_point"]["max_weight"] == 0.08
    assert [p["weight"] for p in r["tipping_point"]["curve"]] == [i / 100 for i in range(41)]
    assert r["risk"]["after"]["shares"]["NVDA"] == 0.86
    assert r["realized"] is None and r["redteam"] is None
    assert len(r["facts"]) == 14 and set(r["facts"]) == {f"T{i}" for i in range(1, 15)}
    # Every fact is also a trace row: the receipt's id space.
    assert {t["id"] for t in r["trace"]} >= set(r["facts"])


def test_fake_time_machine_result():
    r = load(FAKE_TM)
    check_shape(r)
    assert r["as_of"] == "2025-01-31"
    assert set(r["realized"]) == {"max_drawdown_after", "drop_from_decision", "date", "limit",
                                  "events", "series"}
    assert max(r["series"]["dates"]) <= "2025-01-31"
    assert r["verdict"] == "Incompatible"


def test_fake_starter_has_starter_columns():
    p = pd.read_csv("data/fake/starter/prices_daily.csv")
    assert list(p.columns) == ["date", "ticker", "open", "high", "low", "close", "adj_close",
                               "volume", "currency"]
    assert set(p.ticker) == {"XIU.TO", "XBB.TO", "GLD", "ZST.TO", "NVDA", "BTC-USD"}


# --- invariants a UI developer relies on (the fake must not contradict itself) -------------------
import re  # noqa: E402


def test_fake_checks_follow_the_tiers():
    """Spec 5: any hard fail -> Incompatible; one cause, one fail (NVDA breaks two rules)."""
    r = load(FAKE_RESULT)
    fails = [c for c in r["checks"] if c["status"] == "fail"]
    assert {c["rule"] for c in fails} == {"max_drawdown", "scenario_stress", "single_stock", "sector"}
    assert {c["rule"] for c in fails if c["tier"] == "hard"} == {"max_drawdown"}
    assert {c["holding"] or c["rule"] for c in fails} == {"max_drawdown", "scenario_stress", "NVDA"}
    assert r["verdict"] == "Incompatible" and r["tipping_point"]["still_failing"] is None
    assert all(c["status"] == "pass" for c in r["baseline"]["checks"])
    assert {c["rule"] for c in r["checks"]} == set(r["scenario"]["check_order"])
    assert r["scenario"]["check_order"][0] == "max_drawdown"   # the binding rule leads


def test_fake_numbers_agree_across_the_result():
    r = load(FAKE_RESULT)
    f, m, k = r["facts"], r["metrics"], r["kpis"]
    assert f["T1"]["value"] == m["after"]["max_drawdown"] == k["max_drawdown"]["value"] == -0.345
    assert f["T5"]["value"] == m["today"]["max_drawdown"] == r["baseline"]["kpis"]["max_drawdown"]["value"]
    assert f["T6"]["value"] == r["turbulence"]["tariffs"]["worst_after"] == k["scenario_stress"]["value"]
    assert f["T7"]["value"] == r["turbulence"]["tariffs"]["worst_today"]
    assert f["T3"]["value"] == r["limits"]["floor"] and f["T4"]["value"] == r["profile"]["capacity"]
    assert f["T2"]["value"] == round(-r["amount"] * f["T1"]["value"])
    assert r["limits"]["scenario_stress"] == r["limits"]["floor"] / 2 == f["T8"]["value"]
    assert f["T9"]["value"] == r["portfolio"]["NVDA"]
    assert f["T10"]["value"] == r["risk"]["after"]["shares"]["NVDA"] == 0.86
    assert f["T11"]["value"] == r["tipping_point"]["max_weight"]
    assert f["T12"]["value"] == r["attribution"]["shares"]["rates"]
    assert f["T13"]["value"] == m["after"]["cagr"] and f["T14"]["value"] == m["today"]["cagr"]
    for side in ("today", "after"):
        assert abs(sum(r["risk"][side]["shares"].values()) - 1) < 1e-9
    assert k["exposure_canada"]["value"] == r["diversification"]["after"]["countries"]["CAN"]


def test_fake_events_and_turbulence_are_consistent():
    r = load(FAKE_RESULT)
    ids = {e["event_id"] for e in r["events"]}
    assert set(r["scenario"]["event_ids"]) <= ids
    assert all(set(ep["event_ids"]) <= ids for t in r["turbulence"].values() for ep in t["episodes"])
    assert all(e["family"] in FAMILIES and e["sign"] in ("negative", "positive") for e in r["events"])
    pause = next(e for e in r["events"] if e["event_id"] == "tariff_pause_2025")
    assert pause["sign"] == "positive" and pause["after"]["trough"] == 0.0   # never a loss
    tariffs = r["turbulence"]["tariffs"]
    clean = [ep for ep in tariffs["episodes"] if not ep["confounded"]]
    assert tariffs["n"] == len(clean) and any(ep["confounded"] for ep in tariffs["episodes"])
    assert tariffs["worst_after"] == min(ep["trough_after"] for ep in clean)
    for t in r["turbulence"].values():
        assert t["evidence"] == ("Measured" if t["n"] >= 3 else "Indicative" if t["n"] else "Can't say")
    assert all(e["known"] != e["in_progress"] for e in r["events"])


def test_fake_receipt_matches_the_debrief():
    """Spec 7: each number sits in a sentence that cites its [T#]; fact sentences cite fact rows."""
    for path in (FAKE_RESULT, FAKE_TM):
        r = load(path)
        d, rc = r["debrief"], r["receipt"]
        assert rc["verified"] == rc["total"] == len(rc["matches"]) == 14 and rc["defects"] == []
        assert sorted(i for ix in d["sections"].values() for i in ix) == list(range(len(d["sentences"])))
        for m in rc["matches"]:
            text = (d["verdict_sentence"] if m["sentence"] == "verdict"
                    else d["sentences"][m["sentence"]]["text"])
            assert m["number"] in text and f"[{m['ref']}]" in text and m["ref"] in r["facts"]
        for s in d["sentences"]:
            assert set(s["refs"]) <= set(r["facts"]) and all(f"[{x}]" in s["text"] for x in s["refs"])
            if s["kind"] == "fact":
                assert all(r["facts"][x]["kind"] == "fact" for x in s["refs"])
        words = len(d["verdict_sentence"].split()) + sum(len(s["text"].split()) for s in d["sentences"])
        assert words <= 180   # spec 7: the debrief stays within ~180 words


def test_fake_text_never_gives_advice_words():
    """Red gate: nothing the app shows says buy / sell / hold / should."""
    for path in (FAKE_RESULT, FAKE_TM):
        assert not re.search(r"\b(buy|sell|hold|should)\b", Path(path).read_text(), re.I)


def test_fake_time_machine_has_no_future_dates():
    """Spec 6 / 15: nothing dated after as_of in the envelope except `realized` (shown on opening)."""
    r = load(FAKE_TM)
    realized = r.pop("realized")
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", json.dumps(r))
    assert dates and max(dates) <= r["as_of"]
    assert realized["max_drawdown_after"] == -0.159 and realized["drop_from_decision"] == -0.113
    assert realized["series"]["dates"][0] == r["as_of"]
    deepseek = next(e for e in r["events"] if e["event_id"] == "deepseek_2025")
    assert deepseek["in_progress"] and not deepseek["known"] and deepseek["today"]["trough"] is None
    assert r["turbulence"]["tariffs"]["n"] == 1   # "only 1 tariff storm known: too few to conclude"
    assert next(c for c in r["checks"] if c["rule"] == "scenario_stress")["status"] == "warn"
    assert r["lookthrough"]["after"]["mode"] == "direct"   # past dates use direct holdings only
    # the size curve agrees with the one-episode stress value and still flips between 8 % and 9 %
    curve = {p["weight"]: p for p in r["tipping_point"]["curve"]}
    assert curve[0.4]["scenario_shock"] == r["kpis"]["scenario_stress"]["value"]
    assert r["tipping_point"]["max_weight"] == 0.08 and curve[0.09]["fails"] == 1


def test_fake_starter_exercises_the_edge_cases():
    """Plan decisions: TSX-only / US-only holidays, 5-day ZST.TO gap, 7/7 crypto, monthly policy rate."""
    p = pd.read_csv("data/fake/starter/prices_daily.csv")
    rows = lambda t: set(p[p.ticker == t].date)
    assert "2023-10-09" not in rows("XIU.TO") and "2023-10-09" in rows("NVDA")
    assert "2023-11-23" in rows("XIU.TO") and "2023-11-23" not in rows("NVDA")
    assert "2022-12-26" not in rows("XIU.TO") | rows("NVDA") and "2022-12-26" in rows("BTC-USD")
    assert not rows("ZST.TO") & {f"2024-03-0{d}" for d in range(4, 9)}
    assert len(rows("BTC-USD")) == (pd.Timestamp("2026-11-12") - pd.Timestamp("2021-11-12")).days + 1
    assert (p.close == p.adj_close).all()
    assert ((p.currency == "CAD") == p.ticker.str.endswith(".TO")).all()   # listing currency
    fx = pd.read_csv("data/fake/starter/fx_usdcad_daily.csv")
    assert list(fx.columns) == ["date", "usdcad", "cadusd"] and "2023-10-09" not in set(fx.date)
    assert (abs(fx.usdcad * fx.cadusd - 1) < 1e-4).all()
    macro = pd.read_csv("data/fake/starter/macro_rates.csv")
    assert set(macro.series_id) == {"V39079"} and set(macro.value) == {0.25, 4.0}
    assert macro[macro.date <= "2022-02-28"].value.eq(0.25).all()
    assert macro[macro.date >= "2022-03-01"].value.eq(4.0).all()
    u = pd.read_csv("data/fake/starter/assets_universe.csv")
    assert list(u.columns) == ["asset_id", "ticker", "name", "asset_class", "market", "currency", "sector"]


def test_committed_fake_files_are_in_sync_with_the_generator(tmp_path):
    """data/fake/* must be exactly what `python data/fake/make_fake.py` writes (seed 7)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("make_fake", "data/fake/make_fake.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert load(FAKE_RESULT) == json.loads(json.dumps(mod.build_result(False)))
    assert load(FAKE_TM) == json.loads(json.dumps(mod.build_result(True)))
    mod.write_starter(tmp_path)
    for name in ("assets_universe", "prices_daily", "fx_usdcad_daily", "macro_rates"):
        assert (tmp_path / f"{name}.csv").read_bytes() == Path(f"data/fake/starter/{name}.csv").read_bytes()


# =================================================================================================
# Task 2: tools/data.py (spec section 9 processing; pitfalls 1, 6, 7, 13)
# =================================================================================================
def test_union_calendar_and_cad_conversion():
    m = load_market("2026-11-12", data_dir=FAKE)
    cal = set(m["calendar"].strftime("%Y-%m-%d"))
    assert {"2023-10-09", "2023-11-23"} <= cal and "2022-12-26" not in cal
    d = pd.Timestamp("2024-05-01")
    assert m["prices"].at[d, "NVDA"] == pytest.approx(m["local"].at[d, "NVDA"] * m["fx"][d])
    assert m["prices"].at[d, "XIU.TO"] == m["local"].at[d, "XIU.TO"]


def test_ffill_max_3_days_then_flag():
    m = load_market("2026-11-12", data_dir=FAKE)
    assert m["flags"]["ZST.TO"] == ["2024-03-07", "2024-03-08"]
    assert m["prices"]["ZST.TO"]["2024-03-04":"2024-03-06"].notna().all()


def test_fx_forward_filled_on_canadian_holiday():
    m = load_market("2026-11-12", data_dir=FAKE)
    assert m["fx"][pd.Timestamp("2023-10-09")] == m["fx"][pd.Timestamp("2023-10-06")]


def test_cnq_special_distribution_corrected(tmp_path):
    # synthetic: close flat, adj_close jumps 2.1 % on 2022-08-22 (the phantom gain), pitfall 1
    write_starter(tmp_path, {"CNQ.TO": {"2022-08-19": 100.0, "2022-08-22": 102.1, "2022-08-23": 102.1}})
    p = load_prices_cad(["CNQ.TO"], "2022-08-19", "2022-08-23", "2022-08-23", data_dir=tmp_path)["prices"]
    assert p["CNQ.TO"].tolist() == pytest.approx([102.1, 102.1, 102.1])


def test_nothing_after_as_of():
    m = load_market("2025-01-31", data_dir=FAKE)
    for key in ("prices", "local", "traded", "crypto_daily"):
        assert m[key].index.max() <= pd.Timestamp("2025-01-31")
    assert m["fx"].index.max() <= pd.Timestamp("2025-01-31")


def test_perturbation_after_as_of_changes_nothing(tmp_path):
    scramble_after(FAKE, tmp_path, "2025-01-31")   # shuffles adj_close and usdcad of rows dated > as_of
    a, b = load_market("2025-01-31", data_dir=FAKE), load_market("2025-01-31", data_dir=tmp_path)
    pd.testing.assert_frame_equal(a["prices"], b["prices"])
    pd.testing.assert_frame_equal(a["close_cad"], b["close_cad"])


def test_universe_country():
    u = load_universe(data_dir=FAKE).set_index("ticker")["country"]
    assert (u["XIU.TO"], u["NVDA"], u["BTC-USD"], u["GLD"]) == ("CAN", "USA", "CRYPTO", "USA")


def test_mean_policy_rate():
    assert mean_policy_rate("2023-01-01", "2023-12-31", "2023-12-31", market=load_market("2023-12-31", data_dir=FAKE)) == pytest.approx(0.04)


@pytest.mark.skipif(not Path("data/starter/prices_daily.csv").exists(), reason="starter data not present")
def test_real_calendar_has_1282_days():
    assert len(load_market("2026-11-12")["calendar"]) == 1282


# --- Task 2 extras: pin the decisions the nine plan tests leave open -----------------------------
BUNDLE_KEYS = {"calendar", "prices", "local", "traded", "fx", "crypto_daily", "rf_daily", "universe",
               "flags", "as_of", "dividends", "close_cad"}
REAL = pytest.mark.skipif(not Path("data/starter/prices_daily.csv").exists(),
                          reason="starter data not present")


def test_bundle_has_exactly_the_plan_keys_and_types():
    m = load_market("2026-11-12", data_dir=FAKE)
    assert set(m) == BUNDLE_KEYS and m["as_of"] == "2026-11-12"
    assert isinstance(m["calendar"], pd.DatetimeIndex) and m["calendar"].is_monotonic_increasing
    for key in ("prices", "local", "traded"):
        assert m[key].index.equals(m["calendar"])
    assert list(m["prices"].columns) == list(m["universe"]["ticker"]) == list(m["traded"].columns)
    assert (m["traded"].dtypes == bool).all()
    assert m["fx"].index.equals(m["calendar"]) and m["fx"].notna().all()
    assert list(m["universe"].columns) == ["ticker", "name", "asset_class", "market", "currency",
                                           "sector", "country"]
    assert set(m["rf_daily"].unique()) == {0.0025, 0.04}          # percent / 100, fractions


def test_traded_is_a_real_row_and_the_price_is_carried_over_a_holiday():
    m = load_market("2026-11-12", data_dir=FAKE)
    tsx_closed, us_closed = pd.Timestamp("2023-10-09"), pd.Timestamp("2023-11-23")
    assert not m["traded"].at[tsx_closed, "XIU.TO"] and m["traded"].at[tsx_closed, "NVDA"]
    assert not m["traded"].at[us_closed, "NVDA"] and m["traded"].at[us_closed, "XIU.TO"]
    before = pd.Timestamp("2023-10-06")
    assert m["local"].at[tsx_closed, "XIU.TO"] == m["local"].at[before, "XIU.TO"]   # ffill, 1 day
    # a USD line on a Canadian holiday is converted with the carried-forward rate (pitfall 6)
    assert m["prices"].at[tsx_closed, "NVDA"] == pytest.approx(
        m["local"].at[tsx_closed, "NVDA"] * m["fx"][before])
    assert m["traded"]["BTC-USD"].all()                            # crypto trades on every calendar day


def test_crypto_daily_keeps_every_utc_day_in_cad():
    m = load_market("2026-11-12", data_dir=FAKE)
    cd = m["crypto_daily"]
    assert list(cd.columns) == ["BTC-USD"]
    assert len(cd) == (pd.Timestamp("2026-11-12") - pd.Timestamp("2021-11-12")).days + 1
    assert pd.Timestamp("2022-12-26") in cd.index and pd.Timestamp("2022-12-25") in cd.index
    # 2022-12-26: both exchanges closed, so the rate is the last one known (pitfall 7 needs these rows)
    usd = pd.read_csv(f"{FAKE}/prices_daily.csv", dtype={"date": str}).query(
        "ticker == 'BTC-USD' and date == '2022-12-26'").adj_close.iloc[0]
    fx = pd.read_csv(f"{FAKE}/fx_usdcad_daily.csv", dtype={"date": str}).set_index("date").usdcad
    assert cd.at[pd.Timestamp("2022-12-26"), "BTC-USD"] == pytest.approx(usd * fx["2022-12-23"])


def test_gap_longer_than_three_days_stays_nan_and_is_flagged_after_the_first_price(tmp_path):
    days = pd.bdate_range("2024-01-01", "2024-01-26").strftime("%Y-%m-%d").tolist()
    ry = {d: 100.0 + i for i, d in enumerate(days) if d not in days[5:10]}   # 5 missing rows
    late = {d: 50.0 for d in days[3:]}                                      # starts on the 4th day
    write_starter(tmp_path, {"RY.TO": ry, "TD.TO": {d: 1.0 for d in days}, "LATE.TO": late})
    m = load_market("2024-01-26", data_dir=tmp_path)
    assert m["flags"]["RY.TO"] == days[8:10]                      # 3 filled (days 5-7), 2 flagged
    assert m["flags"]["LATE.TO"] == [] and m["flags"]["TD.TO"] == []   # leading NaN is not a gap
    assert m["prices"]["RY.TO"].iloc[5:8].tolist() == [m["prices"]["RY.TO"].iloc[4]] * 3
    assert m["prices"]["RY.TO"].iloc[8:10].isna().all() and m["prices"]["RY.TO"].iloc[10] == 110.0
    assert m["prices"]["LATE.TO"].iloc[:3].isna().all()
    assert not m["traded"]["RY.TO"].iloc[5:10].any()


def test_cnq_fix_touches_only_cnq_and_only_before_2022_08_22(tmp_path):
    pts = {"2022-08-19": 100.0, "2022-08-22": 110.0, "2022-08-23": 120.0}
    write_starter(tmp_path, {"CNQ.TO": pts, "ENB.TO": pts})
    p = load_prices_cad(["CNQ.TO", "ENB.TO"], "2022-08-19", "2022-08-23", "2022-08-23",
                        data_dir=tmp_path)["prices"]
    assert p["CNQ.TO"].tolist() == pytest.approx([102.1, 110.0, 120.0])
    assert p["ENB.TO"].tolist() == [100.0, 110.0, 120.0]


def test_missing_starter_folder_gives_a_plain_sentence(tmp_path):
    with pytest.raises(FileNotFoundError, match="Starter data not found"):
        load_market("2026-11-12", data_dir=tmp_path / "nope")
    with pytest.raises(FileNotFoundError, match="data/starter"):
        load_universe(data_dir=tmp_path)


def test_load_prices_cad_window_columns_flags_and_unknown_ticker():
    out = load_prices_cad(["NVDA", "ZST.TO"], "2024-03-01", "2024-03-12", "2024-03-12", data_dir=FAKE)
    assert list(out["prices"].columns) == ["NVDA", "ZST.TO"]            # the order asked for
    assert out["prices"].index.min() >= pd.Timestamp("2024-03-01")
    assert out["prices"].index.max() <= pd.Timestamp("2024-03-12")
    assert out["flags"] == {"NVDA": [], "ZST.TO": ["2024-03-07", "2024-03-08"]}
    assert out["as_of"] == "2024-03-12" and out["source"]
    # flags outside the requested window are not reported
    early = load_prices_cad(["ZST.TO"], "2024-03-01", "2024-03-06", "2024-03-12", data_dir=FAKE)
    assert early["flags"] == {"ZST.TO": []}
    with pytest.raises(ValueError, match="Unknown ticker: ZAG.TO"):
        load_prices_cad(["XIU.TO", "ZAG.TO"], "2024-01-01", "2024-02-01", "2024-02-01", data_dir=FAKE)


def test_load_prices_cad_never_returns_a_row_after_as_of():
    out = load_prices_cad(["XIU.TO"], "2024-01-01", "2026-11-12", "2024-06-28", data_dir=FAKE)
    assert out["prices"].index.max() <= pd.Timestamp("2024-06-28") and out["as_of"] == "2024-06-28"
    m = load_market("2026-11-12", data_dir=FAKE)                         # a wider bundle is cut too
    wide = load_prices_cad(["XIU.TO"], "2024-01-01", "2026-11-12", "2024-06-28", market=m)
    assert wide["prices"].index.max() <= pd.Timestamp("2024-06-28")


def test_as_of_is_inclusive_and_an_early_as_of_does_not_crash():
    m = load_market("2022-03-01", data_dir=FAKE)
    assert m["calendar"].max() == pd.Timestamp("2022-03-01") and m["as_of"] == "2022-03-01"
    empty = load_market("2021-11-01", data_dir=FAKE)                    # before the first row
    assert len(empty["calendar"]) == 0 and empty["prices"].empty and empty["flags"]["NVDA"] == []


def test_perturbation_scrambles_every_later_row_and_every_key_stays_identical(tmp_path):
    scramble_after(FAKE, tmp_path, "2025-01-31")
    later = pd.read_csv(tmp_path / "prices_daily.csv").query("date > '2025-01-31'").adj_close
    orig = pd.read_csv(f"{FAKE}/prices_daily.csv").query("date > '2025-01-31'").adj_close
    assert not later.equals(orig)                                        # the scramble really happened
    a, b = load_market("2025-01-31", data_dir=FAKE), load_market("2025-01-31", data_dir=tmp_path)
    for key in ("prices", "local", "traded", "crypto_daily", "close_cad", "dividends"):
        pd.testing.assert_frame_equal(a[key], b[key])
    for key in ("fx", "rf_daily"):
        pd.testing.assert_series_equal(a[key], b[key])
    assert a["flags"] == b["flags"] and a["calendar"].equals(b["calendar"])
    assert mean_policy_rate("2022-01-01", "2025-01-31", "2025-01-31", market=a) == pytest.approx(
        mean_policy_rate("2022-01-01", "2025-01-31", "2025-01-31", market=b))


def test_mean_policy_rate_rows_in_period_empty_period_and_as_of_cut():
    m = load_market("2026-11-12", data_dir=FAKE)
    # 2022 has two monthly rows at 0.25 % (Jan, Feb) and ten at 4 %: the mean of the rows
    assert mean_policy_rate("2022-01-01", "2022-12-31", "2022-12-31", market=m) == pytest.approx(
        (2 * 0.0025 + 10 * 0.04) / 12)
    assert mean_policy_rate("2022-01-01", "2022-12-31", "2022-02-28", market=m) == pytest.approx(0.0025)
    # a window with no monthly row inside takes the rate in force (the last row before it)
    assert mean_policy_rate("2023-05-02", "2023-05-20", "2026-11-12", market=m) == pytest.approx(0.04)
    assert mean_policy_rate("2021-01-01", "2021-06-30", "2026-11-12", market=m) == 0.0   # nothing yet


def test_make_market_defaults_and_inference():
    idx = pd.bdate_range("2024-01-01", periods=5)
    prices = pd.DataFrame({"XIU.TO": [1.0, 2.0, np.nan, np.nan, 5.0], "NVDA": 10.0, "BTC-USD": 7.0},
                          index=idx)
    m = make_market(prices, rf=0.03)
    assert set(m) == BUNDLE_KEYS and m["as_of"] == "2024-01-05" and m["calendar"].equals(idx)
    assert m["local"] is m["prices"] and (m["fx"] == 1.0).all() and m["fx"].index.equals(idx)
    assert m["traded"].equals(prices.notna()) and not m["traded"].at[idx[2], "XIU.TO"]
    assert (m["rf_daily"] == 0.03).all() and m["rf_daily"].index.equals(idx)
    assert list(m["crypto_daily"].columns) == ["BTC-USD"]
    assert m["flags"] == {"XIU.TO": [], "NVDA": [], "BTC-USD": []}      # a 2-day hole is inside the 3-day fill
    u = m["universe"].set_index("ticker")
    assert tuple(u.loc["XIU.TO", ["market", "currency", "country"]]) == ("TSX", "CAD", "CAN")
    assert tuple(u.loc["BTC-USD", ["asset_class", "country"]]) == ("crypto", "CRYPTO")
    assert tuple(u.loc["NVDA", ["market", "currency", "country", "sector"]]) == (
        "NASDAQ", "USD", "USA", "Unknown")
    assert mean_policy_rate("2024-01-01", "2024-01-05", "2024-01-05", market=m) == pytest.approx(0.03)


def test_make_market_overrides_and_as_of_cut():
    idx = pd.bdate_range("2024-01-01", periods=5)
    local = pd.DataFrame({"NVDA": 8.0}, index=idx)
    prices = local * 1.25
    fx = pd.Series(1.25, index=idx[[0, 3]])                              # sparse: carried forward
    m = make_market(prices, local=local, fx=fx, as_of="2024-01-03")
    assert m["as_of"] == "2024-01-03" and m["calendar"].max() == pd.Timestamp("2024-01-03")
    assert m["local"].index.max() == m["prices"].index.max() == pd.Timestamp("2024-01-03")
    assert (m["fx"] == 1.25).all() and m["fx"].index.equals(m["calendar"])   # carried forward from the first rate
    with pytest.raises(TypeError):
        make_market(pd.DataFrame({"A": [1.0]}))                          # not indexed by date


def test_load_market_hands_out_independent_dicts_and_notices_rewritten_files(tmp_path):
    a = load_market("2026-11-12", data_dir=FAKE)
    a["flags"]["ZST.TO"].append("1999-01-01")
    a["rf_daily"] = None
    b = load_market("2026-11-12", data_dir=FAKE)
    assert b["flags"]["ZST.TO"] == ["2024-03-07", "2024-03-08"] and b["rf_daily"] is not None
    assert b["prices"] is load_market("2026-11-12", data_dir=FAKE)["prices"]   # the read happens once
    write_starter(tmp_path, {"RY.TO": {"2024-01-02": 10.0, "2024-01-03": 11.0}})
    assert load_market("2024-01-03", data_dir=tmp_path)["prices"]["RY.TO"].tolist() == [10.0, 11.0]
    write_starter(tmp_path, {"RY.TO": {"2024-01-02": 20.0, "2024-01-03": 22.0, "2024-01-04": 23.0}})
    assert load_market("2024-01-04", data_dir=tmp_path)["prices"]["RY.TO"].tolist() == [20.0, 22.0, 23.0]


def test_universe_is_a_fresh_copy_with_the_listing_country(tmp_path):
    u = load_universe(data_dir=FAKE)
    assert list(u.columns) == ["ticker", "name", "asset_class", "market", "currency", "sector",
                               "country"]
    u.loc[:, "country"] = "XXX"
    assert set(load_universe(data_dir=FAKE)["country"]) == {"CAN", "USA", "CRYPTO"}
    write_starter(tmp_path, {"NEW.TO": {"2024-01-02": 1.0}, "ZZZ": {"2024-01-02": 1.0}})
    odd = pd.read_csv(tmp_path / "assets_universe.csv")
    odd.loc[odd.ticker == "ZZZ", "market"] = "Euronext"
    odd.to_csv(tmp_path / "assets_universe.csv", index=False)
    assert load_universe(data_dir=tmp_path).set_index("ticker")["country"].to_dict() == {
        "NEW.TO": "CAN", "ZZZ": "UNKNOWN"}                               # an unknown market is said so


def test_constants_and_data_dir_default(tmp_path):
    import subprocess
    import sys
    assert DATASET_END == "2026-11-12"
    env = {k: v for k, v in __import__("os").environ.items() if k != "EPICENTRE_DATA_DIR"}
    show = [sys.executable, "-c", "from tools.data import DATA_DIR; print(DATA_DIR)"]
    default = subprocess.run(show, env=env, capture_output=True, text=True, check=True).stdout.strip()
    assert Path(default) == Path(__file__).resolve().parents[1] / "data" / "starter"
    env["EPICENTRE_DATA_DIR"] = str(tmp_path)
    assert subprocess.run(show, env=env, capture_output=True, text=True,
                          check=True).stdout.strip() == str(tmp_path)
    assert isinstance(DATA_DIR, Path)


def test_fx_row_after_as_of_never_fills_a_leading_gap(tmp_path):
    days = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    write_starter(tmp_path, {"NVDA": {d: 10.0 for d in days}, "RY.TO": {d: 5.0 for d in days}})
    # the first Bank of Canada rate is dated 2024-01-05, after the as_of below
    pd.DataFrame({"date": ["2024-01-05"], "usdcad": [9.99], "cadusd": [0.1001]}).to_csv(
        tmp_path / "fx_usdcad_daily.csv", index=False)
    early = load_market("2024-01-04", data_dir=tmp_path)
    assert early["fx"].isna().all() and early["prices"]["NVDA"].isna().all()   # a gap, not 9.99
    assert early["prices"]["RY.TO"].tolist() == [5.0, 5.0, 5.0]
    late = load_market("2024-01-05", data_dir=tmp_path)       # the rate exists now, still not for the days before it
    assert late["prices"]["NVDA"].isna().tolist() == [True, True, True, False]   # ledger 14: never back-filled
    assert late["prices"]["NVDA"].iloc[-1] == pytest.approx(99.9)
    assert early["flags"]["NVDA"] == days[:3] and late["flags"]["NVDA"] == days[:3]   # flagged, not filled


def test_blank_fx_row_never_borrows_a_later_rate(tmp_path):
    """Task 3 hardening: a blank Bank of Canada row carries the last known rate, not a future one."""
    days = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]
    write_starter(tmp_path, {"NVDA": {d: 10.0 for d in days}, "RY.TO": {d: 5.0 for d in days}})
    pd.DataFrame({"date": days, "usdcad": [1.30, 1.32, np.nan, np.nan, 1.40], "cadusd": 0.75}
                 ).to_csv(tmp_path / "fx_usdcad_daily.csv", index=False)
    early = load_market("2024-01-05", data_dir=tmp_path)
    late = load_market("2024-01-08", data_dir=tmp_path)
    assert early["fx"].tolist() == [1.30, 1.32, 1.32, 1.32]               # carried from 2024-01-03
    assert late["fx"].tolist() == [1.30, 1.32, 1.32, 1.32, 1.40]          # the past does not move
    assert early["prices"]["NVDA"].tolist() == pytest.approx([13.0, 13.2, 13.2, 13.2])
    idx = pd.bdate_range("2024-01-01", periods=5)
    fx = pd.Series([np.nan, 1.30, np.nan, 1.32, 1.40], index=idx)         # a leading gap stays a gap (ledger 14)
    m = make_market(pd.DataFrame({"NVDA": 10.0}, index=idx), fx=fx)
    assert np.isnan(m["fx"].iloc[0]) and m["fx"].iloc[1:].tolist() == [1.30, 1.30, 1.32, 1.40]


def test_make_market_flags_follow_the_three_day_fill_like_load_market():
    """Task 3 hardening: a one-day closed-exchange hole is not 'missing data'; more than 3 days is."""
    idx = pd.bdate_range("2024-01-01", periods=10)
    nan = np.nan
    prices = pd.DataFrame({
        "ONE.TO": [1, 1, nan, 1, 1, 1, 1, 1, 1, 1],                       # a closed-exchange day
        "THREE.TO": [1, nan, nan, nan, 1, 1, 1, 1, 1, 1],                 # exactly 3 days: filled
        "FIVE.TO": [1, 1, nan, nan, nan, nan, nan, 1, 1, 1],              # 5 days: the last 2 flagged
        "LATE.TO": [nan] * 4 + [1.0] * 6,                                 # no history yet is not a gap
    }, index=idx)
    flags = make_market(prices)["flags"]
    assert flags["ONE.TO"] == [] and flags["THREE.TO"] == [] and flags["LATE.TO"] == []
    assert flags["FIVE.TO"] == idx[5:7].strftime("%Y-%m-%d").tolist()


# --- Task 2 extras on the real starter pack (skipped when data/starter/ is absent) ---------------
@REAL
def test_real_universe_and_countries():
    u = load_universe()
    assert len(u) == 31 and u["country"].value_counts().to_dict() == {"USA": 16, "CAN": 13, "CRYPTO": 2}
    assert u.set_index("ticker").at["GLD", "country"] == "USA"          # listing rule; gold -> GLOBAL later


@REAL
def test_real_pack_spec_9_processing_facts():
    m = load_market("2026-11-12")
    assert len(m["calendar"]) == 1282 and m["as_of"] == "2026-11-12"
    assert all(v == [] for v in m["flags"].values())                    # spec 9: no asset needs more than 3 days
    assert m["prices"].notna().all().all() and m["fx"].notna().all()
    assert m["traded"].sum().drop(["BTC-USD", "ETH-USD"]).eq(1255).all()
    assert m["traded"][["BTC-USD", "ETH-USD"]].all().all()
    assert len(m["crypto_daily"]) == 1827 and m["crypto_daily"].notna().all().all()
    fx_rows = set(pd.read_csv("data/starter/fx_usdcad_daily.csv", dtype={"date": str}).date)
    assert len(set(m["calendar"].strftime("%Y-%m-%d")) - fx_rows) == 37   # spec 9: FX carried forward
    assert m["fx"][pd.Timestamp("2023-10-09")] == m["fx"][pd.Timestamp("2023-10-06")]


@REAL
def test_real_cnq_phantom_gain_is_gone():
    """Pitfall 1: raw +2.78 % on 2022-08-22, fixed +0.67 %; the neighbouring days are untouched."""
    m = load_market("2026-11-12")
    p = m["prices"]["CNQ.TO"]
    raw = pd.read_csv("data/starter/prices_daily.csv", dtype={"date": str}).query(
        "ticker == 'CNQ.TO'").set_index("date").adj_close
    assert raw["2022-08-22"] / raw["2022-08-19"] - 1 == pytest.approx(0.0278, abs=0.0001)
    ret = p.pct_change()
    assert ret[pd.Timestamp("2022-08-22")] == pytest.approx(0.0067, abs=0.0001)
    assert ret[pd.Timestamp("2022-08-23")] == pytest.approx(raw["2022-08-23"] / raw["2022-08-22"] - 1)
    after = p.index[(p.index >= pd.Timestamp("2022-08-22")) & m["traded"]["CNQ.TO"].to_numpy()]
    assert p[after].tolist() == pytest.approx(raw[after.strftime("%Y-%m-%d")].tolist())   # CAD, unchanged
    assert p[pd.Timestamp("2022-08-19")] == pytest.approx(raw["2022-08-19"] * 1.021)      # scaled before


@REAL
def test_real_perturbation_after_as_of_changes_nothing(tmp_path):
    scramble_after("data/starter", tmp_path, "2025-01-31")
    a, b = load_market("2025-01-31"), load_market("2025-01-31", data_dir=tmp_path)
    assert (tmp_path / "corporate_actions.csv").exists() and len(a["dividends"]) > 100   # the dividends are really scrambled
    for key in ("prices", "local", "traded", "crypto_daily", "close_cad", "dividends"):
        pd.testing.assert_frame_equal(a[key], b[key])
    for key in ("fx", "rf_daily"):
        pd.testing.assert_series_equal(a[key], b[key])
    assert a["flags"] == b["flags"] and a["calendar"].max() == pd.Timestamp("2025-01-31")


@REAL
def test_real_policy_rate_changes_on_the_effective_date():
    day_before, hike = load_market("2022-03-02")["rf_daily"], load_market("2022-03-03")["rf_daily"]
    assert day_before.iloc[-1] == 0.0025 and hike.iloc[-1] == 0.005     # percent / 100
    now = load_market("2026-11-12")["rf_daily"]
    assert now.iloc[-1] == 0.025 and now.index.max() == pd.Timestamp("2026-11-12")
    assert 0.0025 < mean_policy_rate("2022-01-01", "2022-12-31", "2022-12-31") < 0.0425


# --- Task 4: ledger 14 data hygiene, FX is never back-filled -----------------------------------------
def test_an_early_price_day_without_fx_is_flagged_not_filled(tmp_path):
    """Days before the first Bank of Canada row have a price but no rate: NaN and flagged, never
    converted with a later rate (red gate 3: the rate of 2024-01-05 did not exist on 2024-01-02)."""
    days = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]
    write_starter(tmp_path, {"NVDA": {d: 10.0 for d in days}, "RY.TO": {d: 5.0 for d in days},
                             "BTC-USD": {d: 20.0 for d in days}})
    pd.DataFrame({"date": days[3:], "usdcad": [1.30, 1.40], "cadusd": 0.75}).to_csv(
        tmp_path / "fx_usdcad_daily.csv", index=False)               # the first rate is dated 2024-01-05
    m = load_market("2024-01-08", data_dir=tmp_path)
    assert m["fx"].isna().tolist() == [True, True, True, False, False]
    assert m["prices"]["NVDA"].isna().tolist() == [True, True, True, False, False]
    assert m["prices"]["NVDA"].iloc[3:].tolist() == pytest.approx([13.0, 14.0])      # the rate of its own day
    assert m["crypto_daily"]["BTC-USD"].isna().tolist() == [True, True, True, False, False]
    assert m["flags"]["NVDA"] == days[:3] and m["flags"]["BTC-USD"] == days[:3]      # flagged, although it is a leading gap
    assert m["flags"]["RY.TO"] == [] and m["prices"]["RY.TO"].notna().all()           # CAD lines need no rate
    assert not m["local"]["NVDA"].isna().any()                                       # the USD price itself is there
    cad = load_prices_cad(["NVDA", "RY.TO"], "2024-01-03", "2024-01-08", "2024-01-08", data_dir=tmp_path)
    assert cad["flags"] == {"NVDA": days[1:3], "RY.TO": []} and cad["prices"]["NVDA"].isna().sum() == 2
    # the early days do not depend on any later rate: scramble the rates after them, same NaN days
    pd.DataFrame({"date": days[3:], "usdcad": [9.0, 2.0], "cadusd": 0.75}).to_csv(
        tmp_path / "fx_usdcad_daily.csv", index=False)
    other = load_market("2024-01-08", data_dir=tmp_path)
    assert other["prices"]["NVDA"].isna().tolist() == [True, True, True, False, False]


def test_a_missing_rate_gap_is_not_hidden_by_the_three_day_fill(tmp_path):
    """The flags list a USD day without a rate even when its own price is carried forward."""
    days = ["2024-01-02", "2024-01-03", "2024-01-04"]
    write_starter(tmp_path, {"NVDA": {d: 10.0 for d in days}, "RY.TO": {d: 5.0 for d in days}})
    pd.DataFrame({"date": days[2:], "usdcad": [1.30], "cadusd": 0.77}).to_csv(
        tmp_path / "fx_usdcad_daily.csv", index=False)
    m = load_market("2024-01-04", data_dir=tmp_path)
    assert m["flags"]["NVDA"] == days[:2] and m["flags"]["RY.TO"] == []


# =================================================================================================
# Task 5: the bundle gains `dividends` (CAD, dated <= as_of) and `close_cad` (the unadjusted close)
# =================================================================================================
def write_actions(dst, rows):
    """corporate_actions.csv in the starter format from [(ex_date, ticker, action, value)]."""
    unit = {"dividend": "per share", "split": "split ratio (new:old)"}
    pd.DataFrame([(d, t, a, v, unit[a]) for d, t, a, v in rows],
                 columns=["ex_date", "ticker", "action", "value", "unit"]).to_csv(
        Path(dst) / "corporate_actions.csv", index=False)


def write_rates(dst, rates):
    pd.DataFrame({"date": list(rates), "usdcad": list(rates.values()), "cadusd": 0.75}).to_csv(
        Path(dst) / "fx_usdcad_daily.csv", index=False)


DIV_COLUMNS = ["date", "ticker", "amount_cad"]


def test_dividends_are_cad_per_share_cut_at_as_of_and_ignore_splits(tmp_path):
    days = pd.bdate_range("2024-01-02", "2024-03-01").strftime("%Y-%m-%d").tolist()
    write_starter(tmp_path, {"RY.TO": {d: 100.0 for d in days}, "MSFT": {d: 50.0 for d in days}})
    write_rates(tmp_path, {"2024-01-02": 1.30, "2024-02-01": 1.40})
    write_actions(tmp_path, [("2024-01-03", "RY.TO", "dividend", 1.0),            # CAD: as it is
                             ("2024-01-10", "MSFT", "dividend", 0.75),            # USD x 1.30
                             ("2024-02-05", "MSFT", "dividend", 0.75),            # USD x 1.40
                             ("2024-02-03", "MSFT", "dividend", 0.50),            # a Saturday: the rate carried from Friday
                             ("2024-01-15", "MSFT", "split", 10.0),               # a split is not a dividend
                             ("2024-03-01", "RY.TO", "dividend", 9.0)])           # the last day
    m = load_market("2024-02-29", data_dir=tmp_path)
    assert list(m["dividends"].columns) == DIV_COLUMNS and m["dividends"]["amount_cad"].dtype == float
    assert isinstance(m["dividends"]["date"].dtype, np.dtype) and m["dividends"]["date"].dtype.kind == "M"
    got = [(d.strftime("%Y-%m-%d"), t, round(a, 6)) for d, t, a in m["dividends"].itertuples(index=False)]
    assert got == [("2024-01-03", "RY.TO", 1.0), ("2024-01-10", "MSFT", 0.975),
                   ("2024-02-03", "MSFT", 0.7), ("2024-02-05", "MSFT", 1.05)]        # sorted; 03-01 is after as_of
    assert len(load_market("2024-02-03", data_dir=tmp_path)["dividends"]) == 3       # as_of is inclusive
    assert len(load_market("2024-01-02", data_dir=tmp_path)["dividends"]) == 0
    assert len(load_market("2024-03-01", data_dir=tmp_path)["dividends"]) == 5


def test_dividend_rows_that_cannot_be_trusted_are_left_out(tmp_path):
    days = pd.bdate_range("2024-01-02", "2024-02-01").strftime("%Y-%m-%d").tolist()
    write_starter(tmp_path, {"RY.TO": {d: 100.0 for d in days}, "NVDA": {d: 50.0 for d in days}})
    write_rates(tmp_path, {"2024-01-10": 1.30})                                       # the first rate is dated 2024-01-10
    write_actions(tmp_path, [("2024-01-03", "NVDA", "dividend", 1.0),                 # USD, no rate yet: no CAD value, never back-filled
                             ("2024-01-11", "NVDA", "dividend", 1.0),
                             ("2024-01-11", "NVDA", "dividend", 1.0),                 # an exact duplicate row
                             ("2024-01-04", "RY.TO", "dividend", 1.0),
                             ("2024-01-05", "RY.TO", "dividend", 0.0),                # zero is not a payout
                             ("2024-01-08", "RY.TO", "dividend", -2.0),               # nor is a negative one
                             ("2024-01-09", "RY.TO", "dividend", float("nan")),
                             ("2024-01-10", "ZZZ.TO", "dividend", 1.0)])              # not in the universe
    got = load_market("2024-02-01", data_dir=tmp_path)["dividends"]
    assert [(d.strftime("%Y-%m-%d"), t, round(a, 6)) for d, t, a in got.itertuples(index=False)] == [
        ("2024-01-04", "RY.TO", 1.0), ("2024-01-11", "NVDA", 1.3)]


def test_corporate_actions_is_optional_and_noticed_when_it_appears(tmp_path):
    days = ["2024-01-02", "2024-01-03"]
    write_starter(tmp_path, {"RY.TO": {d: 100.0 for d in days}})
    none = load_market("2024-01-03", data_dir=tmp_path)                                # the fake pack has none either
    assert none["dividends"].empty and list(none["dividends"].columns) == DIV_COLUMNS
    assert load_market("2026-11-12", data_dir=FAKE)["dividends"].empty
    write_actions(tmp_path, [("2024-01-03", "RY.TO", "dividend", 1.0)])
    assert len(load_market("2024-01-03", data_dir=tmp_path)["dividends"]) == 1         # the cache key saw the new file
    (tmp_path / "corporate_actions.csv").unlink()
    assert load_market("2024-01-03", data_dir=tmp_path)["dividends"].empty


def test_close_cad_is_the_unadjusted_close_through_the_same_pipeline(tmp_path):
    days = pd.bdate_range("2022-08-17", "2022-08-31").strftime("%Y-%m-%d").tolist()
    adj = {"RY.TO": {d: 100.0 for d in days}, "NVDA": {d: 50.0 for d in days},
           "CNQ.TO": {d: (102.1 if d >= "2022-08-22" else 100.0) for d in days}}     # the special-distribution phantom
    del adj["RY.TO"][days[6]], adj["RY.TO"][days[7]], adj["RY.TO"][days[8]], adj["RY.TO"][days[9]]   # a 4-day hole
    write_starter(tmp_path, adj, usdcad=1.25)
    px = pd.read_csv(tmp_path / "prices_daily.csv")
    px["close"] = px["adj_close"] * 1.1                                                # close differs from adj_close
    px.to_csv(tmp_path / "prices_daily.csv", index=False)
    m = load_market("2022-08-31", data_dir=tmp_path)
    cc, pr = m["close_cad"], m["prices"]
    assert cc.index.equals(m["calendar"]) and list(cc.columns) == list(pr.columns)
    assert cc.isna().equals(pr.isna())                                                 # same fill (<= 3 days) and same holes
    assert cc["RY.TO"].iloc[0] == pytest.approx(110.0) and cc["NVDA"].iloc[0] == pytest.approx(50.0 * 1.1 * 1.25)
    assert pr["NVDA"].iloc[0] == pytest.approx(50.0 * 1.25)                            # prices still read adj_close
    assert cc["CNQ.TO"].iloc[0] == pytest.approx(110.0) and pr["CNQ.TO"].iloc[0] == pytest.approx(102.1)   # pitfall 1: adj_close only
    assert cc["CNQ.TO"].iloc[-1] == pytest.approx(102.1 * 1.1) and pr["CNQ.TO"].iloc[-1] == pytest.approx(102.1)
    assert cc["RY.TO"].iloc[6:9].tolist() == pytest.approx([110.0] * 3)                # 3 days carried forward ...
    assert np.isnan(cc["RY.TO"].iloc[9]) and cc["RY.TO"].iloc[10] == pytest.approx(110.0)   # ... the 4th is a hole


def test_make_market_takes_listing_currency_dividends_and_close():
    idx = pd.bdate_range("2024-01-01", periods=5)
    local = pd.DataFrame({"NVDA": 8.0, "RY.TO": 100.0}, index=idx)
    plain = make_market(local * 1.0, local=local, fx=1.25)
    assert plain["dividends"].empty and list(plain["dividends"].columns) == DIV_COLUMNS
    assert plain["close_cad"]["NVDA"].tolist() == [10.0] * 5 and plain["close_cad"]["RY.TO"].tolist() == [100.0] * 5
    close = pd.DataFrame({"NVDA": [7.0, 7.0, 8.0, 8.0, 9.0], "RY.TO": 90.0}, index=idx)
    div = pd.DataFrame({"date": pd.to_datetime(["2024-01-02", "2024-01-04", "2024-01-05", "2024-02-01"]),
                        "ticker": ["NVDA", "RY.TO", "NVDA", "NVDA"], "amount": [1.0, 2.0, 4.0, 8.0]})
    fx = pd.Series([1.0, 1.0, 1.5, 2.0, 2.0], idx)
    m = make_market(local * 1.0, local=local, fx=fx, close=close, dividends=div, as_of="2024-01-05")
    assert m["close_cad"]["NVDA"].tolist() == pytest.approx([7.0, 7.0, 12.0, 16.0, 18.0])   # close x fx (USD only)
    assert m["close_cad"]["RY.TO"].tolist() == [90.0] * 5
    assert [(d.strftime("%Y-%m-%d"), t, a) for d, t, a in m["dividends"].itertuples(index=False)] == [
        ("2024-01-02", "NVDA", 1.0), ("2024-01-04", "RY.TO", 2.0), ("2024-01-05", "NVDA", 8.0)]  # cut at as_of; USD x fx
    assert m["close_cad"].index.max() == pd.Timestamp("2024-01-05")


@REAL
def test_real_dividends_and_unadjusted_close_facts():
    m = load_market("2026-11-12")
    div, raw = m["dividends"], pd.read_csv("data/starter/corporate_actions.csv", dtype={"ex_date": str})
    uni = load_universe().set_index("ticker")
    pay = raw[raw["action"] == "dividend"]
    assert len(pay) == 651 and len(div) == 651 and div["date"].max() <= pd.Timestamp("2026-11-12")
    # the conversion rests on one assumption: every dividend is in its ticker's listing currency
    assert (pay["unit"].str.split().str[0] == pay["ticker"].map(uni["currency"])).all()
    fx = pd.read_csv("data/starter/fx_usdcad_daily.csv", dtype={"date": str}).set_index("date")["usdcad"]
    first = div[(div["ticker"] == "AAPL")].iloc[0]
    assert first["date"] == pd.Timestamp("2022-02-04") and first["amount_cad"] == pytest.approx(0.22 * fx["2022-02-04"])
    ry = div[(div["ticker"] == "RY.TO")]
    assert ry["amount_cad"].tolist() == pytest.approx(pay[pay["ticker"] == "RY.TO"]["value"].tolist())   # CAD as it is
    assert len(load_market("2022-12-31")["dividends"]) == (pay["ex_date"] <= "2022-12-31").sum()
    # close_cad: Yahoo's split-adjusted close, which does NOT embed later dividends (adj_close does)
    px = pd.read_csv("data/starter/prices_daily.csv", dtype={"date": str}).set_index(["ticker", "date"])
    c, a = m["close_cad"], m["prices"]
    assert c.at[pd.Timestamp("2021-12-31"), "XIU.TO"] == pytest.approx(px.loc[("XIU.TO", "2021-12-31"), "close"])
    assert c.at[pd.Timestamp("2021-12-31"), "XIU.TO"] > a.at[pd.Timestamp("2021-12-31"), "XIU.TO"] * 1.1   # 32.52 vs 28.36
    assert c.at[pd.Timestamp("2024-06-07"), "NVDA"] == pytest.approx(
        px.loc[("NVDA", "2024-06-07"), "close"] * m["fx"][pd.Timestamp("2024-06-07")])
    assert c.index.equals(m["calendar"]) and c.isna().equals(a.isna()) and c.notna().all().all()
    pre = c["CNQ.TO"][:"2022-08-19"]                                      # pitfall 1 touches adj_close only
    assert pre.iloc[-1] == pytest.approx(px.loc[("CNQ.TO", "2022-08-19"), "close"])


# Task 6 (the Task 5 review minors): one `as_of` convention for the tools, and a test helper that converts once
def test_load_prices_cad_labels_as_of_with_the_last_data_date():
    saturday = load_prices_cad(["XIU.TO"], "2024-03-01", "2024-03-12", "2024-03-09", data_dir=FAKE)
    assert saturday["as_of"] == "2024-03-08" and saturday["prices"].index.max() == pd.Timestamp("2024-03-08")
    future = load_prices_cad(["XIU.TO"], "2026-11-01", "2030-12-31", "2030-01-01", data_dir=FAKE)
    assert future["as_of"] == DATASET_END                                  # the data ends there, whatever was asked
    wide = load_prices_cad(["XIU.TO"], "2024-03-01", "2024-03-12", "2024-03-09",
                           market=load_market("2026-11-12", data_dir=FAKE))
    assert wide["as_of"] == "2024-03-08"                                   # a wider bundle gives the same label
    before = load_prices_cad(["XIU.TO"], "2021-01-01", "2021-06-30", "2021-06-30", data_dir=FAKE)
    assert before["prices"].empty and before["as_of"] == "2021-06-30"      # no data yet: the request itself


def test_make_market_close_defaults_to_the_cad_prices_without_a_double_conversion():
    idx = pd.bdate_range("2024-01-01", periods=5)
    cad = pd.DataFrame({"NVDA": 10.0, "RY.TO": 100.0}, index=idx)
    m = make_market(cad, fx=1.25)                            # no `local`, no `close`: the CAD prices are all there is
    assert m["close_cad"]["NVDA"].tolist() == [10.0] * 5 and m["close_cad"]["RY.TO"].tolist() == [100.0] * 5
    assert m["local"]["NVDA"].tolist() == [10.0] * 5         # `local` is still the frame as given
    usd = make_market(cad, local=cad * 0.8, fx=1.25)         # a listing-currency `local` is converted once
    assert usd["close_cad"]["NVDA"].tolist() == pytest.approx([10.0] * 5) and usd["close_cad"]["RY.TO"].tolist() == [80.0] * 5
