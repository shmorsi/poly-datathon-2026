"""result_extras.py (lane B3, the Replay keys): pure rules first, then Robert on the real data (skips without the starter
pack or the deep-history cache). Every number checked here is recomputed by another path of the engine, never typed."""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import pipeline
import result_extras as rx
from fake_engine import ROBERT_PLAN, ROBERT_Q

STARTER = Path("data/starter/prices_daily.csv").exists()
DEEP = Path("data/cache/deep/panel.csv").exists()
NEEDS_DATA = pytest.mark.skipif(not STARTER, reason="starter data not present")
NEEDS_DEEP = pytest.mark.skipif(not (STARTER and DEEP), reason="starter data or the deep-history cache not present")
ADVICE = re.compile(r"\b(buy|sell|hold|should|recommend|safe|allowed|you can)\b", re.I)


# --- pure rules ----------------------------------------------------------------------------------------------------
def test_classify_is_the_verdicts_rounding_with_a_one_point_touch_band():
    assert rx.classify(-0.15000039923614295, -0.15) == "held"            # pitfall 5: -15.00004 % is inside
    assert rx.classify(-0.1505, -0.15) == "touched"                      # -15.1 % after ROUND_HALF_UP
    assert rx.classify(-0.16, -0.15) == "touched" and rx.classify(-0.1605, -0.15) == "broke"
    assert rx.classify(-0.02, -0.15) == "held" and rx.classify(None, -0.15) is None


def test_curve_dollars_are_amount_times_depth_to_the_dollar():
    r = {"amount": 600000, "tipping_point": {"curve": [{"weight": 0.08, "max_drawdown": -0.15000039923614295},
                                                       {"weight": 0.4, "max_drawdown": -0.3452439040250206}]}}
    rx.curve_dollars(r)
    assert [p["loss_dollars"] for p in r["tipping_point"]["curve"]] == [-90000, -207146]


class _Broken:
    def __getattr__(self, name):
        def boom(*a, **k):
            raise RuntimeError("secret input text")
        return boom


def _minimal():
    return {"as_of": "2026-11-12", "amount": 600000, "portfolio": dict(ROBERT_PLAN["portfolio"]), "limits": {"floor": -0.15},
            "profile": dict(ROBERT_PLAN["profile"]), "metrics": {"today": {"max_drawdown": -0.1}, "after": None},
            "scenario": {"method": "fallback", "families": ["tariffs"]}, "trace": [], "facts": {}}


def test_extend_never_raises_a_failure_is_none_plus_one_trace_row_and_it_runs_once():
    assert rx.extend(None) is None
    stopped = rx.extend({"as_of": "2026-11-12", "portfolio": {}, "trace": []})
    assert all(stopped[k] is None for k in rx.KEYS) and stopped["trace"] == []
    r = rx.extend(_minimal(), engine=_Broken(), panel=None)
    errors = [t for t in r["trace"] if "error" in t["outputs"]]
    assert errors and all(t["outputs"]["error"].endswith(": not computed") for t in errors)
    assert "secret" not in json.dumps(r) and all(r[k] is None for k in ("not_2022", "reconciliation"))
    assert [t["id"] for t in r["trace"]] == [f"T{i}" for i in range(1, len(r["trace"]) + 1)]
    n = len(r["trace"])
    assert rx.extend(r, engine=_Broken())["trace"][n:] == []                  # idempotent


def test_evidence_is_the_public_cut_portfolio_values_only():
    r = {"as_of": "2026-11-12", "series": {"dates": ["2022-01-03", "2022-10-14"], "today": [100.0, 91.0], "after": [100.0, 70.0]},
         "metrics": {"after": {"peak_date": "2022-01-03", "trough_date": "2022-10-14"}}, "portfolio": {"NVDA": 0.4, "XIU.TO": 0.6},
         "trace": [{"id": "T1", "inputs": {"path": "metrics.after.max_drawdown"}}, {"id": "T2", "inputs": {"path": "amount"}}],
         "facts": {"T1": {"value": -0.3}, "T2": {"value": 600000}}}
    ev = rx.evidence(r)
    assert set(ev) == {"T1", "T2"} and ev["T2"] == [] and [row["value"] for row in ev["T1"]] == [100.0, 70.0]
    assert {row["file"] for row in ev["T1"]} == {"computed: portfolio_series (base 100, CAD)"}   # never a licensed row


def test_navigator_effect_only_when_the_navigator_ran_and_titles_what_it_added():
    sc = {"method": "bedrock", "families": ["tariffs"], "event_ids": ["a", "b"], "change": None, "portfolio": None,
          "keyword_result": {"type": "question", "families": ["tariffs"], "event_ids": ["a"], "change": None}}
    r = {"scenario": sc, "verdict": "Compatible", "checks": [], "events": [{"event_id": "b", "title": "B day", "date": "2025-04-03"}]}
    ins = {"profile": None, "today": {}, "as_of": "2026-11-12", "limits": None, "amount": 1}
    out = rx.navigator_effect(r, ins, _Broken())
    assert [d["what"] for d in out["diffs"]] == ["precedents"] and out["added"] == [{"event_id": "b", "title": "B day",
                                                                                      "date": "2025-04-03"}]
    assert rx.navigator_effect({**r, "scenario": {**sc, "method": "fallback"}}, ins, _Broken()) is None


def test_the_reconciliation_rows_are_rows_of_the_finance_truth_table():
    sys.path.insert(0, str(Path(__file__).parent))
    import test_metrics
    table = {(t, s, e, w): v for t, s, e, w, v in test_metrics.ISSUER}
    assert 3 <= len(rx.RECONCILIATION) <= 5 and rx.RECONCILIATION_TOLERANCE_PP == test_metrics.TOLERANCE_PP
    for ticker, start, end, window, published, url in rx.RECONCILIATION:
        assert table[(ticker, start, end, window)] == published and url.startswith("https://")


# --- Robert on the real data ------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def robert():
    if not STARTER:
        pytest.skip("starter data not present")
    try:
        pipeline.real_engine()
    except pipeline.EngineUnavailable as exc:
        pytest.skip(str(exc))
    return pipeline.run(ROBERT_PLAN, ROBERT_Q, use_bedrock=False)


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


@NEEDS_DATA
def test_robert_run_carries_every_key_inside_compare(robert):
    r = robert
    assert r["status"] == "ok" and all(k in r for k in rx.KEYS)
    assert r["navigator_effect"] is None                       # use_bedrock=False: the navigator did not run
    assert all(r[k] is not None for k in ("not_2022", "tipping_band", "ladder", "reconciliation", "evidence"))
    assert set(r["evidence"]) == set(r["facts"]) and [t["id"] for t in r["trace"]] == [f"T{i}" for i in range(1, len(r["trace"]) + 1)]
    (summary,) = [t for t in r["trace"] if t["tool"] == "result_extras"]
    assert summary["step"] == "COMPARE" and not [t for t in r["trace"] if t["tool"].startswith("result_extras.")
                                                  and "error" in t["outputs"]]
    assert not [s for k in rx.KEYS for s in _strings(r[k]) if ADVICE.search(s)]       # red gate 1
    json.dumps(pipeline.jsonable(r), allow_nan=False)


@NEEDS_DATA
def test_robert_dial_band_and_not_2022_match_the_engines_own_numbers(robert):
    r, curve = robert, robert["tipping_point"]["curve"]
    band = r["tipping_band"]
    first = next(p["weight"] for p in curve if pipeline._beyond(p["max_drawdown"], -0.15))
    assert band["starts"][0]["start"] == "2021-11" and band["starts"][0]["first_break"] == first == 0.09
    assert band["starts"][0]["depth_at_asked"] == pytest.approx(r["metrics"]["after"]["max_drawdown"], abs=1e-12)
    assert band["lo"] == min(s["first_break"] for s in band["starts"]) and band["n_starts"] == 25
    assert [p["loss_dollars"] for p in curve[8:10]] == [-90000, round(600000 * curve[9]["max_drawdown"])]
    n2 = r["not_2022"]
    assert n2["depth"] == pytest.approx(-0.1692, abs=0.001) and n2["trough_date"] == "2025-04-08"
    assert n2["peak_date"] >= "2023-01-01" and n2["loss_dollars"] == round(600000 * n2["depth"])


@NEEDS_DATA
def test_robert_ladder_and_reconciliation(robert):
    rows = {row["ticker"]: row for row in robert["ladder"]["rows"]}
    assert list(rows) == ["SPY", "QQQ", "NVDA"] and robert["ladder"]["weight"] == 0.4
    assert rows["NVDA"]["max_drawdown"] == robert["metrics"]["after"]["max_drawdown"] and rows["NVDA"]["verdict"] == "Incompatible"
    assert rows["NVDA"]["end_value"] == robert["tipping_point"]["curve"][-1]["end_value"]
    assert rows["SPY"]["max_drawdown"] > rows["QQQ"]["max_drawdown"] > rows["NVDA"]["max_drawdown"]
    rec = robert["reconciliation"]
    assert rec["n"] == rec["within"] == 5 and all(abs(row["gap_pp"]) <= 0.15 for row in rec["rows"])


@NEEDS_DEEP
def test_robert_deep_history_is_tools_deep_with_classes_and_robust_claims(robert):
    import tools.deep as deep
    h, eps = robert["deep_history"], {e["episode_id"]: e for e in deep.load_episodes()}
    assert h["kind"] == "assumption" and h["in_verdict"] is False and len(h["episodes"]) == 11
    for e in h["episodes"]:
        for side, mix in (("today", ROBERT_PLAN["portfolio"]), ("after", robert["portfolio"])):
            own = deep.episode_replay(mix, eps[e["id"]], robert["as_of"], amount=600000, floor=-0.15)["depth"]
            assert e[side] == pytest.approx(own, abs=1e-12) and e[f"{side}_class"] in ("broke", "touched", "held")
    claims = h["robust_claims"]
    assert claims["sentence"] and [v["id"] for v in claims["variants"]] == ["base", "start-12", "end+12", "equal"]
    for row in claims["rows"]:                                 # the base run of the claims is the table's own number
        assert row["after"]["depths"][0] == pytest.approx(next(e["after"] for e in h["episodes"] if e["id"] == row["id"]))
    g = h["gentle_case"]
    assert (round(g["real"], 3), round(g["stand_in"], 3)) == (-0.602, -0.27) and g["gentler"]


@NEEDS_DEEP
def test_robert_deep_validation_and_windows(robert):
    v, w = robert["deep_validation"], robert["deep_windows"]
    assert v["today_real"] == robert["metrics"]["today"]["max_drawdown"] and v["within_2pp"]["today"] is True
    assert v["after_proxy"] > v["after_real"] and v["canada"]["french_first"] == "1977-01"
    assert v["canada"]["splice_check"]["corr"] > 0.95
    assert (w["status"], w["horizon_months"], w["first_start"], w["last_start"], w["n"]) == ("ok", 48, "1971-02", "2022-01", 612)
    assert len(w["stripes"]["today"]) == len(w["stripes"]["after"]) == len(w["stripes"]["starts"]) == 612
    assert w["by_weight"][0]["breach_share"] == w["today"]["breach_share"] and len(w["by_weight"]) == 41
    assert w["today"]["worst"] == round(float(np.min(w["stripes"]["today"])), 4)
    facts = [f for f in robert["facts"].values() if f["label"].startswith("By proxy")]
    assert facts and all(f["kind"] == "assumption" for f in facts)


@NEEDS_DEEP
def test_a_mix_with_too_much_unproxied_weight_cannot_say():
    card = pipeline.load_pilots()["amira"]
    eng = pipeline.real_engine()
    limits = eng.load_limits(card["profile"], None, amount=card["amount"])
    r = {"as_of": "2026-11-12", "amount": card["amount"], "portfolio": dict(card["portfolio"]), "limits": limits,
         "profile": dict(card["profile"]), "metrics": {"today": {"max_drawdown": -0.41}, "after": None},
         "scenario": {"method": "fallback", "families": ["chips"]}, "trace": [], "facts": {}}
    rx.extend(r, engine=eng)
    assert r["deep_windows"]["status"] == "cant_say" and "BTC-USD" in r["deep_windows"]["reason"]
    assert all(e["today"] is None for e in r["deep_history"]["episodes"]) and r["tipping_band"] is None


@NEEDS_DATA
def test_no_look_ahead_in_a_past_run():
    eng = pipeline.real_engine()
    r = pipeline.run(ROBERT_PLAN, ROBERT_Q, "2025-01-31", use_bedrock=False)
    assert r["status"] == "ok" and r["not_2022"]["to"] <= "2025-01-31"
    assert all(s["first_day"] <= "2025-01-31" for s in r["tipping_band"]["starts"])
    assert all(row["end"] <= "2025-01-31" for row in r["reconciliation"]["rows"]) and eng is pipeline.real_engine()
    assert {t["as_of"] for t in r["trace"]} == {"2025-01-31"}


@NEEDS_DATA
def test_the_keyword_reading_read_again_offline_is_the_one_the_run_kept(robert):
    """A saved run without scenario.keyword_result gets the same reading pipeline._switch_off keeps (no model)."""
    eng, r = pipeline.real_engine(), json.loads(json.dumps(pipeline.jsonable(robert)))
    kept = eng.keyword_fallback(r["question"], dict(ROBERT_PLAN["portfolio"]), eng.load_events(r["as_of"]), r["as_of"],
                                profile=ROBERT_PLAN["profile"], limits=None, universe=eng.load_universe(),
                                exposure=None, amount=600000)
    fresh = rx._keyword_reading(r, rx.inputs(r), eng)
    assert (fresh["families"], fresh["change"], fresh["method"]) == (kept["families"], kept["change"], "fallback")
    nav = {**r, "scenario": {**r["scenario"], "method": "bedrock", "keyword_result": None}}
    out = rx.navigator_effect(nav, rx.inputs(nav), eng)
    assert out["label"] == "What the navigator changed in this run" and out["verdict"] == r["verdict"]


@NEEDS_DEEP
def test_deep_keys_left_null_by_an_absent_cache_are_filled_later_once(monkeypatch):
    """A run made on a machine without data/cache/deep gets the deep keys (and only their facts) on a later pass."""
    import copy
    import tools.deep as deep
    eng = pipeline.real_engine()
    card = pipeline.load_pilots()["mateo"]
    limits = eng.load_limits(card["profile"], None, amount=card["amount"])
    base = {"as_of": "2026-11-12", "amount": card["amount"], "portfolio": dict(card["portfolio"]), "limits": limits,
            "profile": dict(card["profile"]), "metrics": {"today": {"max_drawdown": -0.11}, "after": None},
            "scenario": {"method": "fallback", "families": ["war_oil"]}, "trace": [], "facts": {}}
    with monkeypatch.context() as m:
        m.setattr(deep, "load_panel", lambda **k: None)
        r = rx.extend(copy.deepcopy(base), engine=eng)
    assert r["deep_history"] is None and r["not_2022"] is not None
    n_facts = len(r["facts"])
    rx.extend(r, engine=eng)
    assert r["deep_history"]["status"] == "ok" and r["deep_windows"]["status"] == "ok"
    labels = [f["label"] for f in r["facts"].values()]
    assert len(r["facts"]) > n_facts and sum(lab.startswith("Worst drop today on the dates from 2023") for lab in labels) == 1
    assert [t["tool"] for t in r["trace"]].count("result_extras.fill") == 1 and set(r["evidence"]) == set(r["facts"])
    trace = len(r["trace"])
    assert rx.extend(r, engine=eng)["trace"][trace:] == []


@NEEDS_DEEP
def test_regression_a_real_robert_run_made_without_the_cache_gets_all_three_deep_keys_later(robert, monkeypatch, tmp_path):
    """Controller bug of 10:01 (Sun): wt-ai ran Robert with B3's code but no data/cache/deep, so the three deep keys were
    null, and a second pass refused to touch an extended Result. Now: the native run has all three; a run made without
    the cache gets them on the next pass; the panel is found from this file's folder or from $EPICENTRE_DEEP_PANEL."""
    import tools.deep as deep
    assert all(robert[k] and robert[k].get("status", "ok") == "ok" for k in rx.DEEP_KEYS)        # the native run
    real_panel = rx.deep_dir() / "panel.csv"
    assert real_panel.is_file() and rx.deep_dir() == Path(rx.__file__).resolve().parent / "data" / "cache" / "deep"
    monkeypatch.setattr(rx, "REPO_ROOT", tmp_path)                       # a checkout without its own cache
    monkeypatch.delenv(rx.PANEL_ENV, raising=False)
    r = pipeline.run(ROBERT_PLAN, ROBERT_Q, use_bedrock=False)
    assert all(r[k] is None for k in rx.DEEP_KEYS) and r["not_2022"] is not None
    assert not [t for t in r["trace"] if "error" in t["outputs"] and t["tool"].startswith("result_extras")]
    monkeypatch.setenv(rx.PANEL_ENV, str(real_panel))                    # the override names the panel
    assert rx.deep_dir() == real_panel.parent
    rx.extend(r)
    assert all(r[k] and r[k].get("status", "ok") == "ok" for k in rx.DEEP_KEYS)
    assert r["deep_history"]["robust_claims"]["sentence"] == robert["deep_history"]["robust_claims"]["sentence"]
    assert r["deep_windows"]["n"] == robert["deep_windows"]["n"] and set(r["evidence"]) == set(r["facts"])
    assert len(r["facts"]) == len(robert["facts"]) and [t["tool"] for t in r["trace"]].count("result_extras.fill") == 1
    assert deep.PANEL_PATH.is_file()                                     # tools.deep's own default is untouched


@NEEDS_DATA
def test_hedge_compare_for_the_workshops_xsp_question():
    """R19(b), Too Canadian? (add 20 % SPY): unhedged is the verdict's own path (SPY in CAD); the CAD-hedged stand-in moves
    SPY's line with its USD returns only (no hedging cost, said in `method`); SPY's 2022 return in USD and in CAD comes
    from the prices themselves; the facts rows carry both sides, the stand-in as an assumption."""
    eng = pipeline.real_engine()
    card = pipeline.load_pilots()["canadian"]
    today, as_of = dict(card["portfolio"]), "2026-11-12"
    after = eng.apply_change(today, card["request"])
    ev = eng.evaluate(card["profile"], after, ["tariffs"], as_of, limits=None, amount=card["amount"])
    r = {"as_of": as_of, "amount": card["amount"], "portfolio": after, "baseline": {"portfolio": today},
         "limits": eng.load_limits(card["profile"], None, amount=card["amount"]), "profile": dict(card["profile"]),
         "metrics": {"today": {"max_drawdown": -0.12}, "after": ev["metrics"]}, "trace": [], "facts": {},
         "scenario": {"method": "fallback", "families": ["tariffs"], "change": dict(card["request"])}}
    hc = rx.hedge_compare(rx.inputs(r), eng)
    assert hc["unhedged"]["worst_fall"] == pytest.approx(ev["metrics"]["max_drawdown"], abs=1e-12)
    assert hc["unhedged"]["end_value"] == round(card["amount"] * ev["series"]["values"][-1] / 100)
    m = eng.load_market(as_of)
    for cur, frame in (("usd", m["local"]), ("cad", m["prices"])):
        px = frame["SPY"].dropna()
        assert hc["spy_2022"][cur] == pytest.approx(px[:"2022-12-31"].iloc[-1] / px[:"2021-12-31"].iloc[-1] - 1, abs=1e-12)
    assert hc["hedged_standin"]["kind"] == "assumption" and "No hedging cost" in hc["method"]
    carry = rx._hedge_carry(m, as_of)                                    # finance F5: hedged like XSP, the rate-gap carry
    assert carry.index.max() <= pd.Timestamp(as_of) and hc["hedge_carry"]["total"] == pytest.approx(carry.iloc[-1] - 1)
    assert -0.05 < hc["hedge_carry"]["total"] < 0 and hc["hedged_carry"]["kind"] == "assumption"
    assert round(hc["hedged_carry"]["worst_fall"], 3) == round(hc["hedged_standin"]["worst_fall"], 3) == -0.142
    assert hc["hedged_carry"]["end_value"] < hc["hedged_standin"]["end_value"] and "federal funds rate" in hc["method"]
    assert hc["hedged_standin"]["worst_fall"] != hc["unhedged"]["worst_fall"]
    assert rx.hedge_compare({**rx.inputs(r), "ticker": "NVDA"}, eng) is None
    rx.extend(r, engine=eng)
    rows = {f["label"]: f for f in r["facts"].values()}
    assert rows["SPY’s 2022 return in US dollars"]["value"] == pytest.approx(hc["spy_2022"]["usd"])
    stand_in = [f for label, f in rows.items() if "stand-in (US-dollar returns" in label]
    assert len(stand_in) == 3 and {f["kind"] for f in stand_in} == {"assumption", "fiction"}
    like = [f for label, f in rows.items() if "hedged like XSP (US-dollar returns plus" in label or label.startswith("The CAD hedge")]
    assert len(like) == 4 and {f["kind"] for f in like} == {"assumption", "fiction"}
    assert not [s for k in rx.KEYS for s in _strings(r[k]) if ADVICE.search(s)] and "'" not in r["hedge_compare"]["method"]
    mine = [s for k in rx.KEYS for s in _strings(r[k]) if s is not (r["deep_history"] or {}).get("sentence")]
    assert not [s for s in mine if any(m in s for m in "●◐○")]                       # R16: markers are SVG, never text


@NEEDS_DATA
def test_a_key_added_after_a_result_was_extended_is_computed_on_the_next_pass(monkeypatch):
    """Saved runs extended before hedge_compare existed get it (and its facts, once) from the CLI's next pass."""
    eng = pipeline.real_engine()
    card = pipeline.load_pilots()["canadian"]
    today = dict(card["portfolio"])
    after = eng.apply_change(today, card["request"])
    ev = eng.evaluate(card["profile"], after, ["tariffs"], "2026-11-12", limits=None, amount=card["amount"])
    r = {"as_of": "2026-11-12", "amount": card["amount"], "portfolio": after, "baseline": {"portfolio": today},
         "limits": eng.load_limits(card["profile"], None, amount=card["amount"]), "profile": dict(card["profile"]),
         "metrics": {"today": {"max_drawdown": -0.12}, "after": ev["metrics"]}, "trace": [], "facts": {},
         "scenario": {"method": "fallback", "families": ["tariffs"], "change": dict(card["request"])}}
    with monkeypatch.context() as m:
        m.setattr(rx, "KEYS", tuple(k for k in rx.KEYS if k != "hedge_compare"))
        rx.extend(r, engine=eng, panel=None)
    assert "hedge_compare" not in r
    rx.extend(r, engine=eng)
    assert r["hedge_compare"]["ticker"] == "SPY" and [t["tool"] for t in r["trace"]].count("result_extras.fill") == 1
    labels = [f["label"] for f in r["facts"].values()]
    assert labels.count("SPY’s 2022 return in US dollars") == 1 and len(labels) == len(set(labels))
    assert set(r["evidence"]) == set(r["facts"])


@NEEDS_DEEP
def test_the_table_and_the_sentence_come_from_one_classification(robert):
    """Lane u8, Sun 10:40: the sentence said "too close to call" for 1982 and 2009 while the rows said "Broke". Now each
    row's class IS its robust status (broke / held / touched, with why), and the counts and the sentence are read from
    the same rows."""
    import re as _re
    h = robert["deep_history"]
    claims, rows = h["robust_claims"], h["episodes"]
    by_id = {x["id"]: x for x in claims["rows"]}
    for e in rows:
        for side in ("today", "after"):
            assert e[f"{side}_class"] == by_id[e["id"]][side]["status"]
            assert (e[f"{side}_why"] is not None) == (e[f"{side}_class"] == "touched")
        assert e["direction"] == by_id[e["id"]]["direction"]
    year = lambda e, side: by_id[e["id"]][side]["trough"][:4]                    # noqa: E731
    touched = sorted({year(e, "today") for e in rows if e["today_class"] == "touched"})
    broke = sorted({year(e, "after") for e in rows if e["after_class"] == "broke"})
    s = claims["sentence"]
    assert f"held in {sum(e['today_class'] == 'held' for e in rows)} " in s and h["counts"]["today_held"] == 8
    assert rx._and(touched) in s and rx._and(broke) in s and not [e for e in rows if e["today_class"] == "broke"]
    assert {e["id"] for e in rows if e["today_class"] == "touched"} >= {"volcker_1979", "gfc_2008"}
    assert h["counts"]["today_touched"] == len([e for e in rows if e["today_class"] == "touched"])
    assert h["counts"]["move_no_worse"] == sum(e["direction"] == "no_further" for e in rows)
    assert _re.search(r"\bby (\d+) to (\d+) points\b", s)


def test_end_values_are_amount_times_the_last_level_and_after_only_with_a_move():
    r = {"amount": 250000, "series": {"dates": ["2021-11-12", "2026-11-12"], "today": [100.0, 152.2002], "after": None},
         "as_of": "2026-11-12"}
    assert rx.end_values(r)["today"] == 380501 and rx.end_values(r)["after"] is None
    assert rx.end_values({**r, "series": {**r["series"], "after": [100.0, 161.529]}})["after"] == 403823
    assert rx.end_values({"amount": None, "series": r["series"]}) is None


@NEEDS_DATA
def test_robert_end_values_match_the_size_curve_and_carry_facts(robert):
    ev, curve = robert["end_values"], robert["tipping_point"]["curve"]
    assert (ev["today"], ev["after"]) == (curve[0]["end_value"], curve[-1]["end_value"])
    assert ev["date"] == robert["series"]["dates"][-1] == robert["as_of"]
    rows = {f["label"]: f for f in robert["facts"].values()}
    assert rows[f"Ended at, your mix today ({ev['date']}, on your fictional amount)"]["value"] == ev["today"]


def test_reconciliation_periods_read_as_the_page_says_them():
    assert rx.period_text("3 years a year to 2026-10-31, market") == "Per year over the 3 years to 2026-10-31 (market price)"
    assert rx.period_text("YTD to 2026-11-12, NAV") == "Year to date to 2026-11-12 (NAV)"
    assert rx.period_text("1 year to 2026-10-31, market") == "1 year to 2026-10-31 (market price)"


def test_curve_floor_margin_is_rounded_points_positive_above_the_floor():
    r = {"amount": 600000, "limits": {"floor": -0.15}, "tipping_point": {"curve": [
        {"weight": 0.0, "max_drawdown": -0.1060653581864397}, {"weight": 0.08, "max_drawdown": -0.15000039923614295},
        {"weight": 0.09, "max_drawdown": -0.15640878366610977}]}}
    rx.curve_dollars(r)
    assert [p["floor_margin_pp"] for p in r["tipping_point"]["curve"]] == [4.4, 0.0, -0.6]       # -10.6, -15.0, -15.6 vs -15.0


@NEEDS_DATA
def test_robert_reconciliation_and_curve_keys_and_a_refresh_adds_no_facts(robert):
    import copy
    rows = robert["reconciliation"]["rows"]
    assert not [x for x in rows if "a year" in x["period"]] and all(x["period"] == rx.period_text(x["window"]) for x in rows)
    curve = robert["tipping_point"]["curve"]
    assert all(p["floor_margin_pp"] == float(rx._pp(p["max_drawdown"]) - rx._pp(-0.15)) for p in curve)
    assert (curve[8]["floor_margin_pp"], curve[9]["floor_margin_pp"]) == (0.0, -0.6)
    r = copy.deepcopy(robert)
    for p in r["tipping_point"]["curve"]:
        p.pop("floor_margin_pp")
    r["reconciliation"]["rows"][0]["period"] = "3 years a year"
    n_facts = len(r["facts"])
    rx.extend(r, refresh=("reconciliation",))
    assert r["tipping_point"]["curve"][9]["floor_margin_pp"] == -0.6 and len(r["facts"]) == n_facts
    assert r["reconciliation"]["rows"][0]["period"] == rows[0]["period"]


def test_only_computes_exactly_the_keys_named_for_a_frozen_fixture():
    r = {"as_of": "2026-11-12", "amount": 600000, "portfolio": {"XIU.TO": 1.0}, "limits": {"floor": -0.15},
         "tipping_point": {"curve": [{"weight": 0.0, "max_drawdown": -0.16}]}, "metrics": {"today": {}, "after": None},
         "trace": [{"id": "T1", "tool": "result_extras", "inputs": {}, "outputs": {}}], "facts": {}, "evidence": {"T1": []}}
    rx.extend(r, engine=_Broken(), only=("curve",))
    assert r["tipping_point"]["curve"][0]["floor_margin_pp"] == -1.0 and "hedge_compare" not in r and "end_values" not in r
    assert r["evidence"] == {"T1": []} and [t["tool"] for t in r["trace"]] == ["result_extras", "result_extras.fill"]


def test_turbulence_rows_carry_the_servers_floor_class_never_the_browsers():
    """Pitfall 5 / lane u8's shock matrix: round_pp both sides; within 1 point either side = touched."""
    falls = (-0.0899, -0.1389, -0.1399, -0.15000039923614295, -0.16, -0.1605)   # -9.0, -13.9, -14.0, -15.0, -16.0, -16.1
    assert [rx.floor_class(x, -0.15)[0] for x in falls] == ["held", "held", "touched", "touched", "touched", "broke"]
    assert rx.floor_class(-0.1405, -0.15)[1] == "within 1 point of your floor" and rx.floor_class(None, -0.15) == (None, None)
    r = {"limits": {"floor": -0.15}, "turbulence": {"tariffs": {"worst_today": -0.0596, "worst_after": -0.159},
                                                    "rates": {"worst_today": None, "worst_after": -0.17}}}
    rx.turbulence_classes(r)
    t, k = r["turbulence"]["tariffs"], r["turbulence"]["rates"]
    assert (t["today_class"], t["after_class"], t["after_why"], t["after_floor_margin_pp"]) == ("held", "touched", rx.WHY_NEAR, -0.9)
    assert (k["today_class"], k["after_class"], k["after_why"]) == (None, "broke", None)


@NEEDS_DATA
def test_robert_turbulence_classes_come_with_the_run(robert):
    for fam, row in robert["turbulence"].items():
        assert row["after_class"] == rx.floor_class(row["worst_after"], -0.15)[0] and "today_why" in row, fam


# --- fix wave lane fin-backend (R35 two limits, R36 robustness facts) --------------------------------------------------
def _small_run():
    """A two-mix Result on 8 days: the move falls 26.7 % from its high (1,200 -> 880 on a 1,000 amount), below the
    900 line (1,000 - a 100 capacity) on two sessions; today's mix never goes below 950."""
    dates = [f"2024-01-0{i}" for i in range(1, 9)]
    after, today = [100, 120, 95, 88, 91, 89, 100, 121], [100, 99, 98, 97, 96, 95, 96, 97]
    r = {"as_of": "2024-01-08", "amount": 1000, "profile": {"capacity": 100}, "limits": {"floor": -0.15},
         "portfolio": {"A": 1.0}, "baseline": {"portfolio": {"B": 1.0}}, "metrics": {"today": {}, "after": {}},
         "series": {"dates": dates, "today": today, "after": after}, "trace": [], "facts": {},
         "scenario": {"change": {"op": "set", "ticker": "A", "weight": 1.0, "from_ticker": None}}}
    r["breaches"] = pipeline._breaches(dates, after, -0.15, 1000)
    return r


def test_capacity_is_a_dollar_line_on_each_sides_own_path_and_breaches_carry_path_dollars():
    r = _small_run()
    cap = rx.capacity(r, rx.inputs(r))
    assert (cap["amount"], cap["capacity"], cap["line"]) == (1000, 100, 900)
    a, t = cap["after"], cap["today"]
    assert (a["low_value"], a["low_date"], a["sessions_below"], a["first_below"], a["last_below"]) == (880, "2024-01-04", 2,
                                                                                                         "2024-01-04", "2024-01-06")
    assert (a["status"], a["falls_below"], a["margin_dollars"]) == ("broke", 1, -20)
    assert [(b["peak_value"], b["trough_value"], b["fall_dollars"], b["capacity_status"]) for b in a["floor_breaks"]] == [
        (1200, 880, -320, "broke")]
    assert (t["status"], t["sessions_below"], t["first_below"], t["low_value"], t["floor_breaks"]) == ("held", 0, None, 950, [])
    assert (a["line"], a["capacity"], a["amount"], t["line"]) == (900, 100, 1000, 900)              # each side reads alone
    assert a["episodes"] == [{"first_date": "2024-01-04", "last_date": "2024-01-06", "low_date": "2024-01-04",
                              "low_value": 880, "sessions": 2}] and t["episodes"] == []
    assert (cap["side"], cap["times"], cap["min_value"], cap["status"]) == ("after", 1, 880, "broke")   # the run's own path
    rx.breach_dollars(r)
    assert [b["fall_dollars"] for b in r["breaches"]] == [-320] and r["breaches"][0]["loss_dollars"] != -320
    assert rx.capacity({**r, "profile": {"capacity": None}, "limits": {"floor": -0.15}}, rx.inputs(r) | {"profile": {}}) is None
    rx.extend(r, engine=_Broken(), only=("capacity", "breaches"))
    rows = {f["label"]: f for f in r["facts"].values()}
    line = next(f for label, f in rows.items() if label.startswith("Your capacity line"))
    assert (line["value"], line["kind"]) == (900, "assumption")
    assert {f["value"] for label, f in rows.items() if label.startswith("Fall 1 deeper than your floor")} == {1200, 880, -320}
    assert all(f["kind"] == "fiction" for label, f in rows.items() if label.startswith("Fall 1 deeper"))


@NEEDS_DATA
def test_robert_capacity_broke_once_in_2022_and_held_in_2025_today_held(robert):
    """R35: the move fell to $408,174 (2022-10-14), 188 sessions below $510,000 (2022-04-22 to 2023-01-19), one fall;
    the 2025 break of the 15 % rule stayed $714,257 above the line. Recomputed on the engine's own path."""
    cap, eng = robert["capacity"], pipeline.real_engine()
    assert (cap["capacity"], cap["line"], cap["kind"]) == (90000, 510000, "fiction")
    a, t = cap["after"], cap["today"]
    assert (a["low_value"], a["low_date"], a["sessions_below"], a["first_below"], a["last_below"], a["falls_below"]) == (
        408174, "2022-10-14", 188, "2022-04-22", "2023-01-19", 1)
    v = np.round(600000 * np.asarray(eng.portfolio_series(robert["portfolio"], as_of=robert["as_of"])["values"]) / 100, 2)
    assert a["sessions_below"] == int((v < 510000).sum()) and a["low_value"] == round(float(v.min()))
    assert [(b["trough_date"][:4], b["capacity_status"]) for b in a["floor_breaks"]] == [("2022", "broke"), ("2025", "held")]
    assert a["floor_breaks"][1]["margin_dollars"] == 714257 and (t["status"], t["sessions_below"]) == ("held", 0)
    assert (cap["times"], [e["first_date"][:4] for e in cap["episodes"]], cap["min_value"]) == (1, ["2022"], 408174)
    assert a["episodes"][0]["sessions"] == 188 and (a["line"], t["line"], a["capacity"]) == (510000, 510000, 90000)
    b = robert["breaches"][1]
    assert (round(b["peak_value"]), round(b["trough_value"]), b["fall_dollars"]) == (1473670, 1224257, -249413)
    assert [x["fall_dollars"] for x in robert["breaches"]] == [x["fall_dollars"] for x in a["floor_breaks"]]


@NEEDS_DATA
def test_robert_peer_check_19_of_20_ended_higher_12_broke_the_floor(robert):
    """R36 (finance F2): 40 % in each of the pack's 20 stocks, the run's own change with the ticker swapped."""
    pc, eng = robert["peer_check"], pipeline.real_engine()
    assert (pc["n"], pc["higher"], pc["broke"], pc["today_end"], pc["lower"]) == (20, 19, 12, robert["end_values"]["today"],
                                                                                 ["CNR.TO"])
    rows = {x["ticker"]: x for x in pc["rows"]}
    assert rows["NVDA"]["is_move"] and rows["NVDA"]["end_value"] == robert["end_values"]["after"]
    assert rows["NVDA"]["max_drawdown"] == pytest.approx(robert["metrics"]["after"]["max_drawdown"], abs=1e-12)
    shop = eng.portfolio_series(eng.apply_change(ROBERT_PLAN["portfolio"], {"op": "set", "ticker": "SHOP.TO", "weight": 0.4,
                                                                             "from_ticker": None}), as_of=robert["as_of"])
    assert rows["SHOP.TO"]["end_value"] == round(600000 * shop["values"][-1] / 100) == 962045 and rows["SHOP.TO"]["ended_higher"]
    assert rows["FTS.TO"]["broke_floor"] and not rows["ATD.TO"]["broke_floor"]          # -15.2 % and -9.9 % (pitfall 5)
    assert sorted(pc["broke_list"]) == sorted(t for t, x in rows.items() if x["broke_floor"])


@NEEDS_DATA
def test_robert_never_rebalanced_and_funded_three_ways(robert):
    """R36 (finance F3, F9): bought once and never rebalanced, NVIDIA reaches 79 % of the money (75 % by 2025-01-23)
    and the floor breaks 5 times; funded in proportion, from XIU.TO or from bonds and cash: -33.8 % to -34.7 %, one verdict."""
    nr = robert["never_rebalanced"]
    assert (nr["ticker"], nr["breaks"], round(nr["peak_weight"], 3), nr["peak_weight_date"]) == ("NVDA", 5, 0.794, "2026-10-07")
    assert round(nr["worst_fall"], 4) == -0.3252 and (nr["falls"][2]["peak_date"], round(nr["falls"][2]["share_at_high"], 3)) == ("2025-01-06", 0.759)
    assert [f["trough_date"][:7] for f in nr["falls"]][-1] == "2026-11" and nr["falls"][-1]["recovery_date"] is None
    assert nr["rebalanced_breaks"] == len(robert["breaches"]) == 2
    (row,) = [v for v in robert["variations"] if v["kind"] == "never_rebalanced"]                  # FIXWAVE: a variations row
    assert row["breaks"] == 5 and row["peak_weight"] == nr["peak_weight"] and len(robert["variations"]) == 3
    fc = robert["funding_check"]
    assert [w["id"] for w in fc["ways"]] == ["in_proportion", "largest", "bonds_cash"] and fc["ways"][0]["is_run"]
    assert fc["ways"][0]["max_drawdown"] == robert["metrics"]["after"]["max_drawdown"]
    assert fc["ways"][1]["from"] == ["XIU.TO"] and fc["ways"][1]["mix"]["XIU.TO"] == pytest.approx(0.05)
    assert fc["ways"][2]["from"] == ["XBB.TO", "ZST.TO"] and fc["ways"][2]["mix"]["XIU.TO"] == pytest.approx(0.45)
    assert (round(fc["mildest"], 3), round(fc["deepest"], 3)) == (-0.338, -0.347)
    assert fc["same_verdict"] is True and fc["verdicts"] == [robert["verdict"]] == ["Incompatible"]


@NEEDS_DATA
def test_robert_volatility_uses_the_replays_own_sessions_per_year(robert):
    """R36 (finance F9): 1,281 daily returns over 1,826 calendar days = 256.2 sessions a year, so 22.37 %, not 22.18 %."""
    vol = robert["volatility"]
    assert vol["after"]["sessions_per_year"] == pytest.approx(1281 / (1826 / 365.25)) and vol["after"]["returns"] == 1281
    assert (round(vol["after"]["value"] * 100, 2), round(vol["today"]["value"] * 100, 2)) == (22.37, 7.47)
    assert vol["after"]["value_252"] == pytest.approx(robert["metrics"]["after"]["volatility"], abs=1e-12)
    rows = [f for f in robert["facts"].values() if f["label"].startswith("Volatility, a year")]
    assert sorted(round(f["value"], 4) for f in rows) == [0.0747, 0.2237] and {f["kind"] for f in rows} == {"fact"}
    labels = [f["label"] for f in robert["facts"].values()]
    for words in ("ended above your mix today", "broke your floor", "Never rebalanced", "the move funded 3 ways"):
        assert any(words in label for label in labels), words
    assert len(labels) == len(set(labels)) and set(robert["evidence"]) == set(robert["facts"])
    assert not [s for k in rx.KEYS for s in _strings(robert[k]) if ADVICE.search(s)]


@NEEDS_DATA
def test_the_fix_wave_keys_never_read_past_as_of():
    """A run judged on 2022-06-30: every path, peer, drift and funding mix stops there (red gate 3)."""
    eng, card, as_of = pipeline.real_engine(), pipeline.load_pilots()["robert"], "2022-06-30"
    today, after = dict(card["portfolio"]), eng.apply_change(card["portfolio"], card["request"])
    ev_a, ev_t = (eng.evaluate(card["profile"], mix, ["tariffs"], as_of, limits=None, amount=card["amount"]) for mix in (after, today))
    r = {"as_of": as_of, "amount": card["amount"], "portfolio": after, "baseline": {"portfolio": today},
         "limits": eng.load_limits(card["profile"], None, amount=card["amount"]), "profile": dict(card["profile"]),
         "metrics": {"today": ev_t["metrics"], "after": ev_a["metrics"]}, "trace": [], "facts": {}, "verdict": ev_a["verdict"],
         "series": {"dates": ev_a["series"]["dates"], "today": ev_t["series"]["values"], "after": ev_a["series"]["values"]},
         "scenario": {"method": "fallback", "families": ["tariffs"], "change": dict(card["request"])}}
    r["breaches"] = pipeline._breaches(r["series"]["dates"], r["series"]["after"], -0.15, card["amount"])
    rx.extend(r, engine=eng, only=("capacity", "breaches", "peer_check", "never_rebalanced", "funding_check", "volatility"))
    assert r["capacity"]["after"]["last_below"] <= as_of and r["peer_check"]["end_date"] <= as_of
    assert r["never_rebalanced"]["end_date"] <= as_of and r["never_rebalanced"]["peak_weight_date"] <= as_of
    assert r["volatility"]["after"]["end_date"] <= as_of and r["funding_check"]["as_of"] == as_of
    assert r["peer_check"]["today_end"] == round(card["amount"] * r["series"]["today"][-1] / 100)
