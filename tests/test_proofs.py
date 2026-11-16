"""Plan P tests: proofs.py (spec §21 items 2, 3, 5-9; ledger §18). Offline unless marked REAL."""
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import config
import proofs
from tools.data import CNQ_FIX_FACTOR, UNIVERSE_COLUMNS, load_market, make_market
from tools.metrics import drawdown_series, risk_metrics, trailing_yield
from tools.portfolio import apply_change, portfolio_series

FAKE = Path("data/fake/starter")          # A's committed synthetic pack (6 tickers, FAKE numbers)
REAL = pytest.mark.skipif(not Path("data/starter/prices_daily.csv").exists(), reason="starter data not present")
AS_OF = "2025-01-31"
ROBERT_TODAY = {"XIU.TO": 0.45, "XBB.TO": 0.35, "GLD": 0.1, "ZST.TO": 0.1}
ROBERT_AFTER = {"NVDA": 0.4, "XIU.TO": 0.27, "XBB.TO": 0.21, "GLD": 0.06, "ZST.TO": 0.06}

SEAL_FIXTURE = {"flight_plan": {"portfolio": {"NVDA": 0.4, "XIU.TO": 0.27, "XBB.TO": 0.21, "GLD": 0.06, "ZST.TO": 0.06}, "amount": 600000.0,
    "profile": {"goal": "preservation", "horizon_years": 4, "risk": "moderate", "esg": False, "crypto": False, "capacity": 90000, "reaction_2022": "held"}, "limits": None},
  "as_of": "2025-01-31", "known_event_ids": ["chips_2022", "tariff_threat_2024", "ukraine_2022"],
  "checks": [{"rule": "max_drawdown", "tier": "hard", "status": "fail", "value": -0.15000000000000002, "limit": -0.15, "holding": None,
              "reason": "In this history the mix fell −34.5 % ($207,000), beyond your floor."}], "verdict": "Incompatible"}


def test_seal_matches_the_pinned_cross_language_hash():      # same vector as plan D Task 8 and tests/web_lib_test.cjs
    assert proofs.seal(**SEAL_FIXTURE) == "d092269a44891603a6da1a38eca43a28dfa3cead54c889182a6c91c21600cea8"
    text = proofs.canonical_json(SEAL_FIXTURE)
    assert '"amount":600000,' in text and '"value":-0.15}' in text and '"limits":null' in text


def test_canonical_json_rules():
    assert proofs.canonical_json({"b": [1.0, -0.0, 0.1 + 0.2, True, None, 7], "a": "é"}) == '{"a":"é","b":[1,0,0.3,true,null,7]}'


def test_seal_ignores_key_and_event_order_but_not_values():
    a = proofs.seal({"portfolio": {"SPY": 1.0}, "amount": 1}, AS_OF, ["y", "x"], [], "Compatible")
    assert a == proofs.seal({"amount": 1, "portfolio": {"SPY": 1.0}}, AS_OF, ["x", "y"], [], "Compatible")
    assert a != proofs.seal({"portfolio": {"SPY": 1.0}, "amount": 2}, AS_OF, ["x", "y"], [], "Compatible")


def _events(tmp_path):
    p = tmp_path / "events.csv"
    pd.DataFrame({"event_id": ["a_2022", "b_2025", "c_2026"], "date": ["2022-03-01", "2025-04-02", "2026-02-27"],
                  "announced": ["2022-03-01", "2025-04-02", "2026-02-27"],
                  "announced_at": ["2022-03-01T09:00", "2025-04-02T16:30", "2026-02-27T08:00"]}).to_csv(p, index=False)
    return p


def honest(paths):                     # a decision that reads only rows dated <= AS_OF
    m = load_market(AS_OF, data_dir=paths["data_dir"])
    ev = pd.read_csv(paths["events"], dtype=str)
    return {"flight_plan": {"portfolio": ROBERT_AFTER, "amount": 600000}, "as_of": AS_OF,
            "known_event_ids": sorted(ev.loc[ev["date"] <= AS_OF, "event_id"]),
            "checks": [{"rule": "max_drawdown", "value": risk_metrics(portfolio_series(ROBERT_AFTER, as_of=AS_OF, market=m))["max_drawdown"]}],
            "verdict": "Incompatible"}


def leaky(paths):                      # the negative control: it also reads the last data day
    out = honest(paths)
    out["checks"][0]["end_value"] = portfolio_series(ROBERT_AFTER, market=load_market("2026-11-12", data_dir=paths["data_dir"]))["values"][-1]
    return out


def test_scramble_keeps_the_seal_of_an_honest_decision(tmp_path):
    paths = {"data_dir": FAKE, "events": _events(tmp_path)}
    sha = proofs.seal(**honest(paths))
    out = proofs.scramble_future(honest, AS_OF, sha, data_dir=FAKE, events_path=paths["events"])
    assert out["match"] is True and out["sha256"] == sha and out["seed"] == proofs.SCRAMBLE_SEED == 20261114
    assert out["rows_shuffled"] == {"prices": 2961, "fx": 463, "macro": 22, "events": 2} and out["ms"] >= 0


def test_scramble_breaks_the_seal_of_a_leaky_decision(tmp_path):
    paths = {"data_dir": FAKE, "events": _events(tmp_path)}
    out = proofs.scramble_future(leaky, AS_OF, proofs.seal(**leaky(paths)), data_dir=FAKE, events_path=paths["events"])
    assert out["match"] is False


def test_scramble_copy_moves_only_later_rows_and_never_the_source(tmp_path):
    before = hashlib.sha256((FAKE / "prices_daily.csv").read_bytes()).hexdigest()
    counts = proofs.scramble_copy(FAKE, tmp_path / "x", AS_OF, events_path=_events(tmp_path))
    a = pd.read_csv(FAKE / "prices_daily.csv", dtype={"date": str})
    b = pd.read_csv(tmp_path / "x" / "prices_daily.csv", dtype={"date": str})
    early = a["date"] <= AS_OF
    pd.testing.assert_frame_equal(a[early], b[early])
    assert (b.loc[~early, "date"] > AS_OF).all() and sorted(b.loc[~early, "date"]) == sorted(a.loc[~early, "date"])
    assert int((a.loc[~early, "date"].to_numpy() != b.loc[~early, "date"].to_numpy()).sum()) == 2959
    ev = pd.read_csv(tmp_path / "x" / "events.csv", dtype=str).set_index("event_id")["date"].to_dict()
    assert ev == {"a_2022": "2022-03-01", "b_2025": "2026-02-27", "c_2026": "2025-04-02"}     # one cycle: no later row keeps its date
    assert counts["prices"] == 2961 and hashlib.sha256((FAKE / "prices_daily.csv").read_bytes()).hexdigest() == before


def test_scramble_without_data_is_a_plain_error(tmp_path):
    out = proofs.scramble_future(honest, AS_OF, "0" * 64, data_dir=tmp_path, events_path=_events(tmp_path))
    assert set(out) == {"error"} and "starter data" in out["error"]


@REAL
def test_real_scramble_counts_and_seal():
    events = Path("data/events.csv")
    paths = {"data_dir": Path("data/starter"), "events": events}
    out = proofs.scramble_future(honest, AS_OF, proofs.seal(**honest(paths)), events_path=events)
    n_after = int((pd.read_csv(events, dtype=str)["date"] > AS_OF).sum())          # 19 of 37 on the committed catalog
    rows = out["rows_shuffled"]
    assert out["match"] is True and {k: rows[k] for k in ("prices", "fx", "macro", "events")} == {"prices": 14279, "fx": 443, "macro": 2943, "events": n_after}
    assert set(rows) == {"prices", "fx", "macro", "events", "corporate_actions"}     # + the dividends file of the starter pack (course correction after A Task 5)
    assert out["ms"] < 10_000          # ledger section 29: a timing bound never fails a correctness test (10 s or more)


# --- a leak control for every re-dealt file: prices, close, FX, macro, dividends, the catalog's three dates ---
def _pack(tmp_path):
    """The FAKE pack, plus FAKE monthly CAD dividends of two funds (Jan 2022 to Oct 2026) and a rising FAKE policy rate."""
    pack = tmp_path / "pack"
    pack.mkdir()
    for f in FAKE.glob("*.csv"):
        shutil.copy(f, pack / f.name)
    rows = [(f"{d + pd.Timedelta(days=14):%Y-%m-%d}", t, "dividend", f"{base + step * i:.4f}", "CAD per share")
            for i, d in enumerate(pd.date_range("2022-01-01", "2026-10-31", freq="MS"))
            for t, base, step in (("XIU.TO", 0.2, 0.001), ("XBB.TO", 0.07, 0.0005))]
    pd.DataFrame(rows, columns=["ex_date", "ticker", "action", "value", "unit"]).to_csv(pack / "corporate_actions.csv", index=False)
    macro = pd.read_csv(FAKE / "macro_rates.csv", dtype=str, keep_default_na=False)
    macro["value"] = [f"{0.25 + 0.05 * i:.2f}" for i in range(len(macro))]        # the FAKE rate is flat 4.0 and could not show a macro leak
    macro.to_csv(pack / "macro_rates.csv", index=False)
    return pack


def honest_yield(paths):               # honest, plus the trailing yield at AS_OF (reads dividends and the unadjusted close <= AS_OF)
    out = honest(paths)
    out["checks"][0]["yield"] = trailing_yield(ROBERT_AFTER, AS_OF, market=load_market(AS_OF, data_dir=paths["data_dir"]))["value"]
    return out


def _late_dividends(paths):            # reads the dividends paid in the last year of the data, all dated after AS_OF
    d = load_market("2026-11-12", data_dir=paths["data_dir"])["dividends"]
    return float(d.loc[d["date"] > pd.Timestamp("2025-11-12"), "amount_cad"].sum())


def _late_close(paths):                # reads the last five unadjusted closes of the CAD funds
    c = load_market("2026-11-12", data_dir=paths["data_dir"])["close_cad"]
    return float(np.nansum(c[["XIU.TO", "XBB.TO", "ZST.TO"]].iloc[-5:].to_numpy(float)))


def _late_fx(paths):                   # reads the USD/CAD rate of the last five days of the data
    return float(np.nansum(load_market("2026-11-12", data_dir=paths["data_dir"])["fx"].iloc[-5:].to_numpy(float)))


def _late_rate(paths):                 # reads the policy rate in force on the last data day
    return float(load_market("2026-11-12", data_dir=paths["data_dir"])["rf_daily"].iloc[-1])


def _latest_by(column):
    def read(paths):                   # reads which event is the latest by `column`, after AS_OF or not
        return pd.read_csv(paths["events"], dtype=str).sort_values(column)["event_id"].iloc[-1]
    return read


LATE_READS = {"dividends": _late_dividends, "close": _late_close, "fx": _late_fx, "macro": _late_rate,
              "catalog_date": _latest_by("date"), "catalog_announced": _latest_by("announced"),
              "catalog_announced_at": _latest_by("announced_at")}


def leaky_through(name):               # a negative control: honest_yield plus one late read of one re-dealt file
    def decide(paths):
        out = honest_yield(paths)
        out["checks"][0]["leak"] = LATE_READS[name](paths)
        return out
    return decide


def test_scramble_keeps_the_seal_of_a_decision_that_reads_dividends_and_closes(tmp_path):
    pack, ev = _pack(tmp_path), _events(tmp_path)
    paths = {"data_dir": pack, "events": ev}
    assert honest_yield(paths)["checks"][0]["yield"] > 0                  # control: a real number built from the dividends file
    out = proofs.scramble_future(honest_yield, AS_OF, proofs.seal(**honest_yield(paths)), data_dir=pack, events_path=ev)
    assert out["match"] is True and out["rows_shuffled"]["corporate_actions"] == 42      # 21 months x 2 funds after AS_OF
    assert {k: out["rows_shuffled"][k] for k in ("prices", "fx", "macro", "events")} == {"prices": 2961, "fx": 463, "macro": 22, "events": 2}


@pytest.mark.parametrize("leak", list(LATE_READS))
def test_scramble_breaks_the_seal_of_a_decision_that_reads_a_late_row_of_any_re_dealt_file(tmp_path, leak):
    pack, ev = _pack(tmp_path), _events(tmp_path)
    paths, decide = {"data_dir": pack, "events": ev}, leaky_through(leak)
    control = proofs.scramble_future(honest_yield, AS_OF, proofs.seal(**honest_yield(paths)), data_dir=pack, events_path=ev)
    out = proofs.scramble_future(decide, AS_OF, proofs.seal(**decide(paths)), data_dir=pack, events_path=ev)
    assert control["match"] is True and out["match"] is False        # the honest part matches, so the late read alone breaks the seal


def test_scramble_copy_re_deals_dividend_dates_after_as_of_only(tmp_path):
    pack = _pack(tmp_path)
    counts = proofs.scramble_copy(pack, tmp_path / "x", AS_OF)
    a, b = (pd.read_csv(d / "corporate_actions.csv", dtype=str) for d in (pack, tmp_path / "x"))
    early = a["ex_date"] <= AS_OF
    pd.testing.assert_frame_equal(a[early], b[early])
    pd.testing.assert_frame_equal(a.drop(columns="ex_date"), b.drop(columns="ex_date"))     # tickers and amounts stay on their rows
    assert (b.loc[~early, "ex_date"] > AS_OF).all() and sorted(b.loc[~early, "ex_date"]) == sorted(a.loc[~early, "ex_date"])
    assert counts == {"prices": 2961, "fx": 463, "macro": 22, "corporate_actions": 42}
    assert int((a.loc[~early, "ex_date"].to_numpy() != b.loc[~early, "ex_date"].to_numpy()).sum()) > 21


def test_scramble_copy_moves_the_three_catalog_dates_together(tmp_path):
    proofs.scramble_copy(FAKE, tmp_path / "x", AS_OF, events_path=_events(tmp_path))
    ev = pd.read_csv(tmp_path / "x" / "events.csv", dtype=str).set_index("event_id")      # columns: date, announced, announced_at
    assert ev.loc["a_2022"].tolist() == ["2022-03-01", "2022-03-01", "2022-03-01T09:00"]            # before AS_OF: untouched
    assert ev.loc["b_2025"].tolist() == ["2026-02-27", "2026-02-27", "2026-02-27T08:00"]            # took c_2026's whole triple
    assert ev.loc["c_2026"].tolist() == ["2025-04-02", "2025-04-02", "2025-04-02T16:30"]            # and gave up its own


def test_scramble_says_when_there_is_nothing_to_scramble(tmp_path):
    ev = _events(tmp_path)
    sha = proofs.seal(**honest({"data_dir": FAKE, "events": ev}))
    last_day = proofs.scramble_future(honest, "2026-11-12", sha, data_dir=FAKE, events_path=ev)    # the last data day: no row is later
    assert last_day["rows_shuffled"] == {"prices": 0, "fx": 0, "macro": 0, "events": 0}
    assert last_day["nothing_to_scramble"] is True and last_day["match"] is True          # a plain match, which the page must not present as a proof
    earlier = proofs.scramble_future(honest, AS_OF, sha, data_dir=FAKE, events_path=ev)
    assert earlier["nothing_to_scramble"] is False and earlier["match"] is True


def test_scramble_copy_refuses_to_write_over_its_source(tmp_path):
    pack = _pack(tmp_path)
    before = (pack / "prices_daily.csv").read_bytes()
    with pytest.raises(ValueError, match="refusing"):
        proofs.scramble_copy(pack, pack, AS_OF)
    assert (pack / "prices_daily.csv").read_bytes() == before
    out = tmp_path / "y"
    out.mkdir()
    catalog = _events(out)
    catalog_before = catalog.read_bytes()
    with pytest.raises(ValueError, match="refusing"):
        proofs.scramble_copy(pack, out, AS_OF, events_path=catalog)
    assert catalog.read_bytes() == catalog_before and not (out / "prices_daily.csv").exists()


def test_scramble_copy_is_the_same_every_time_and_the_seed_changes_it(tmp_path):
    ev = _events(tmp_path)
    for name in ("one", "two"):
        proofs.scramble_copy(FAKE, tmp_path / name, AS_OF, events_path=ev)
    proofs.scramble_copy(FAKE, tmp_path / "other", AS_OF, events_path=ev, seed=1)
    prices = [(tmp_path / name / "prices_daily.csv").read_bytes() for name in ("one", "two", "other")]
    assert prices[0] == prices[1] != prices[2]


def test_canonical_json_takes_numpy_scalars_and_refuses_other_types():
    value = {"a": np.int64(3), "b": np.float64(0.5), "c": np.bool_(True), "d": (1, np.float32(2.0)), "e": np.str_("x")}
    assert proofs.canonical_json(value) == '{"a":3,"b":0.5,"c":true,"d":[1,2],"e":"x"}'
    for bad in ({1, 2}, pd.Timestamp(AS_OF), Path("x"), {1: "a"}):
        with pytest.raises(TypeError):
            proofs.canonical_json(bad)


@REAL
def test_real_scramble_breaks_a_late_read_of_every_re_dealt_file():
    events = Path("data/events.csv")
    paths = {"data_dir": Path("data/starter"), "events": events}
    out = proofs.scramble_future(honest_yield, AS_OF, proofs.seal(**honest_yield(paths)), events_path=events)
    n_div = int((pd.read_csv("data/starter/corporate_actions.csv", dtype=str)["ex_date"] > AS_OF).sum())
    assert out["match"] is True and out["rows_shuffled"]["corporate_actions"] == n_div > 0
    for leak in LATE_READS:
        decide = leaky_through(leak)
        assert proofs.scramble_future(decide, AS_OF, proofs.seal(**decide(paths)), events_path=events)["match"] is False, leak


# --- Task P2: what the navigator changed ------------------------------------------------------------
FAKE_RESULT = json.loads(Path("data/fake/result.json").read_text())


def reading(**scenario):               # a Result-shaped reading: the scenario + its verdict and checks (a REPLAYED reading)
    base = {"type": "change", "change": {"op": "set", "ticker": "TSLA", "weight": 0.0833, "from_ticker": None},
            "families": ["tariffs"], "event_ids": ["liberation_day_2025", "tariffs_order_2025"], "clarify": None, "clarify_reason": None}
    verdict = scenario.pop("verdict", "Incompatible")
    return {"scenario": {**base, **scenario}, "verdict": verdict, "binding_rule": "max_drawdown" if verdict == "Incompatible" else None,
            "checks": [{"rule": "max_drawdown", "status": "fail" if verdict == "Incompatible" else "pass"}]}


def bare(r):                           # the keyword reading as D Task 6 stores it: the scenario only, no verdict (not replayed)
    return {"scenario": r["scenario"]}


def test_navigator_effect_same_reading():
    out = proofs.navigator_effect(reading(), reading(event_ids=["tariffs_order_2025", "liberation_day_2025"],
                                  change={"op": "set", "ticker": "tsla", "weight": 0.08333, "from_ticker": None}))
    assert out["same"] is True and out["diffs"] == [] and out["verdict_without"] == out["verdict"] == "Incompatible"


def test_navigator_effect_names_each_difference_in_a_fixed_order():
    assert proofs.WHAT == ("change", "families", "precedents", "clarify", "verdict")
    nav = reading(families=["tariffs", "rates"])
    fb = reading(type=None, change=None, families=[], event_ids=[], clarify="Please give the move as a share of your portfolio.",
                 clarify_reason="size_ambiguous", verdict=None)
    out = proofs.navigator_effect(nav, fb)
    assert out["same"] is False and [d["what"] for d in out["diffs"]] == ["change", "families", "precedents", "clarify", "verdict"]
    assert out["diffs"][1] == {"what": "families", "navigator": ["rates", "tariffs"], "fallback": []}
    assert out["diffs"][3] == {"what": "clarify", "navigator": None, "fallback": "size_ambiguous"}
    assert out["diffs"][4] == {"what": "verdict", "navigator": "Incompatible", "fallback": None}
    assert (out["verdict"], out["verdict_without"], out["binding_without"]) == ("Incompatible", None, None)
    assert out["fallback"] == {"type": None, "change": None, "families": [], "event_ids": [], "clarify_reason": "size_ambiguous"}
    assert out["checks_without"] == fb["checks"]


def test_navigator_effect_on_the_fake_result():
    nav = {"scenario": {**FAKE_RESULT["scenario"], "change": {"op": "set", "ticker": "NVDA", "weight": 0.4}},
           "verdict": FAKE_RESULT["verdict"], "binding_rule": "max_drawdown", "checks": FAKE_RESULT["checks"]}
    wide = {**nav["scenario"], "families": ["tariffs", "war_oil", "chips", "rates"]}
    out = proofs.navigator_effect(nav, bare({"scenario": wide}))          # ruling 2: the keyword reading was not replayed
    assert [d["what"] for d in out["diffs"]] == ["families"] and out["verdict"] == "Incompatible"
    assert (out["verdict_without"], out["binding_without"], out["checks_without"]) == (None, None, None)     # unknown, never borrowed
    replayed = proofs.navigator_effect(nav, {**nav, "scenario": wide})    # a replay that found the same verdict is passed through
    assert [d["what"] for d in replayed["diffs"]] == ["families"] and replayed["verdict_without"] == "Incompatible"
    assert replayed["checks_without"] == FAKE_RESULT["checks"]


# Ruling 2 (Sat 23:00): a verdict "without the navigator" comes from a real replay of the keyword reading, or it is null.
TODAY = {"XIU.TO": 0.45, "XBB.TO": 0.35, "GLD": 0.1, "ZST.TO": 0.1}


def judged(portfolio, **scenario):     # a reading whose evaluated mix is `portfolio` (what the judge sees besides the shocks)
    return reading(portfolio=portfolio, **scenario)


def test_a_reading_that_was_not_replayed_never_borrows_the_navigators_verdict():
    nav = judged(ROBERT_AFTER)
    fb = {"scenario": judged(TODAY, change=None, type="diversification", event_ids=[])["scenario"]}   # keyword rules: no move
    out = proofs.navigator_effect(nav, fb)
    assert out["same"] is False and [d["what"] for d in out["diffs"]] == ["change", "precedents"]       # no verdict row: unknown
    assert (out["verdict"], out["verdict_without"], out["binding_without"], out["checks_without"]) == ("Incompatible", None, None, None)


def test_the_same_judge_inputs_give_the_navigators_own_verdict():
    nav = judged(ROBERT_AFTER)
    out = proofs.navigator_effect(nav, bare(judged(dict(ROBERT_AFTER), event_ids=["tariffs_order_2025"])))
    assert [d["what"] for d in out["diffs"]] == ["precedents"]                                          # the precedents do not reach the judge
    assert (out["verdict_without"], out["binding_without"], out["checks_without"]) == ("Incompatible", "max_drawdown", nav["checks"])
    near = {**ROBERT_AFTER, "NVDA": 0.4001, "XIU.TO": 0.2699}                                           # within the tolerance, not the same mix
    out = proofs.navigator_effect(nav, bare(judged(near)))
    assert out["diffs"] == [] and out["same"] is True and out["verdict_without"] is None                # equal reading, unreplayed: not borrowed
    wider = proofs.navigator_effect(nav, bare(judged(dict(ROBERT_AFTER), families=["tariffs", "rates"])))
    assert [d["what"] for d in wider["diffs"]] == ["families"] and wider["verdict_without"] is None     # other shocks: another judgement


def test_a_keyword_question_stops_the_run_before_any_judge():
    ask = reading(type="fit", change=None, families=[], event_ids=[], clarify="Which storm or move should I check?",
                  clarify_reason="headline_vague")
    out = proofs.navigator_effect(judged(ROBERT_AFTER), bare(ask))
    assert [d["what"] for d in out["diffs"]] == ["change", "families", "precedents", "clarify", "verdict"]
    assert out["diffs"][4] == {"what": "verdict", "navigator": "Incompatible", "fallback": None}       # known: the run stops to ask
    assert (out["verdict_without"], out["binding_without"], out["checks_without"]) == (None, None, None)
    assert out["fallback"]["clarify_reason"] == "headline_vague" and "storm" not in json.dumps(out)     # the model's text is never shown


def test_a_clarify_without_a_code_is_shown_as_true():
    out = proofs.navigator_effect(reading(), reading(clarify="Which one?", clarify_reason=None))
    assert {"what": "clarify", "navigator": None, "fallback": True} in out["diffs"]


@pytest.mark.parametrize("a, b, same", [
    (None, None, True), ({}, None, True), (None, {"op": "add", "ticker": "SPY", "weight": 0.2}, False),
    ({"op": "add", "ticker": "spy", "weight": 0.2}, {"op": "add", "ticker": "SPY", "weight": 0.2, "from_ticker": None}, True),
    ({"op": "add", "ticker": "SPY", "weight": 0.2}, {"op": "add", "ticker": "SPY", "weight": 0.2005}, True),     # 0.0005: inside
    ({"op": "add", "ticker": "SPY", "weight": 0.2}, {"op": "add", "ticker": "SPY", "weight": 0.2006}, False),
    ({"op": "add", "ticker": "SPY", "weight": 0.2}, {"op": "set", "ticker": "SPY", "weight": 0.2}, False),
    ({"op": "add", "ticker": "SPY", "weight": 0.2}, {"op": "add", "ticker": "QQQ", "weight": 0.2}, False),
    ({"op": "replace", "ticker": "ESGV", "weight": None, "from_ticker": "cnq.to"},
     {"op": "replace", "ticker": "ESGV", "weight": None, "from_ticker": "CNQ.TO"}, True),
    ({"op": "replace", "ticker": "ESGV", "weight": None, "from_ticker": "CNQ.TO"},
     {"op": "replace", "ticker": "ESGV", "weight": None, "from_ticker": "ENB.TO"}, False),
    ({"op": "add", "ticker": "SPY", "weight": None}, {"op": "add", "ticker": "SPY", "weight": 0.2}, False)])
def test_same_change_rules(a, b, same):
    assert proofs._same_change(a, b) is same and proofs._same_change(b, a) is same


# The two showcase questions (spec 24 meeting 2, resolution 4), read by the REAL keyword rules (offline, no model).
def keyword_reading(question):
    """The reading D Task 6 stores beside a Bedrock run (`scenario.keyword_result`), as the keyword rules give it."""
    import pipeline
    from agents import scenario as rules
    universe = [{"ticker": t, "name": n} for t, n in (("SPY", "SPDR S&P 500 ETF Trust"), ("XIU.TO", "iShares S&P/TSX 60 Index ETF"),
                ("XBB.TO", "iShares Core Canadian Universe Bond Index ETF"), ("GLD", "SPDR Gold Shares"), ("ZST.TO", "BMO Ultra Short-Term Bond ETF"))]
    kw = rules.keyword_fallback(question, TODAY, [], AS_OF, universe=universe, amount=600000)
    return {"scenario": {k: kw.get(k) for k in pipeline._READING_KEYS}}


ADD_SPY = {"op": "add", "ticker": "SPY", "weight": 0.2, "from_ticker": None}


def navigator_reading(**scenario):    # what a validated model plan looks like once code has applied it (no shock families)
    base = {"type": "change", "change": ADD_SPY, "families": [], "event_ids": [], "clarify": None, "clarify_reason": None,
            "portfolio": apply_change(TODAY, ADD_SPY)}
    return reading(**{**base, **scenario})


def test_showcase_too_canadian_the_keyword_rules_miss_a_paraphrase():
    # Sun Nov 15: the keyword rules now read "adding 20 % SPY" as the add move (the "Too Canadian?" run gets its after
    # path without the model); the showcase is a paraphrase they still miss: no move verb, only a size and a ticker.
    kw = keyword_reading("My portfolio seems very Canadian. Would a 20 % slice of SPY improve my diversification?")
    assert kw["scenario"]["change"] is None and kw["scenario"]["clarify_reason"] is None              # no verb, no move
    out = proofs.navigator_effect(navigator_reading(), kw)
    assert [d["what"] for d in out["diffs"]] == ["change"] and out["diffs"][0] == {"what": "change", "navigator": ADD_SPY, "fallback": None}
    assert out["verdict_without"] is None and out["fallback"]["change"] is None       # today's mix would be judged: not replayed here
    hit = keyword_reading("My portfolio seems very Canadian. Would adding 20 % SPY improve my diversification?")
    assert hit["scenario"]["change"] == ADD_SPY                                       # control: "adding" is read now
    assert [d["what"] for d in proofs.navigator_effect(navigator_reading(), hit)["diffs"]] == []


def test_showcase_levy_the_keyword_rules_find_no_shock():
    q = "What if the White House puts a 25 % levy on everything Canada ships south?"      # eval question r05
    kw = keyword_reading(q)
    assert kw["scenario"]["families"] == [] and kw["scenario"]["clarify_reason"] == "headline_vague"
    nav = navigator_reading(type="shock", change=None, portfolio=None, families=["tariffs"], event_ids=["liberation_day_2025"])
    out = proofs.navigator_effect(nav, kw)
    assert [d["what"] for d in out["diffs"]] == ["families", "precedents", "clarify", "verdict"]
    assert out["diffs"][0] == {"what": "families", "navigator": ["tariffs"], "fallback": []}
    assert out["diffs"][2] == {"what": "clarify", "navigator": None, "fallback": "headline_vague"}
    assert out["verdict_without"] is None and q not in json.dumps(out) and "Which storm" not in json.dumps(out)


def test_navigator_effect_copies_and_never_edits_its_inputs():
    nav, fb = reading(families=["tariffs", "rates"]), reading(families=["rates"], change=None, verdict=None)
    before = json.dumps([nav, fb], sort_keys=True)
    out = proofs.navigator_effect(nav, fb)
    out["diffs"][0]["navigator"]["ticker"] = "X"
    out["checks_without"].append("x")
    out["fallback"]["families"].append("x")
    assert json.dumps([nav, fb], sort_keys=True) == before
    assert json.loads(json.dumps(proofs.navigator_effect(nav, fb))) == proofs.navigator_effect(nav, fb)      # plain JSON


def test_navigator_effect_survives_readings_without_a_scenario():
    out = proofs.navigator_effect({}, {"scenario": None})
    assert out["same"] is True and out["diffs"] == [] and out["verdict"] is None and out["verdict_without"] is None


def test_the_order_of_families_and_precedents_is_not_a_difference():
    a = reading(families=["tariffs", "rates"], event_ids=["liberation_day_2025", "tariffs_order_2025"])
    b = reading(families=["rates", "tariffs"], event_ids=["tariffs_order_2025", "liberation_day_2025"])
    assert proofs.navigator_effect(a, b)["diffs"] == []


# --- Task P3: days below the floor ------------------------------------------------------------------
def dd(values, start="2022-01-03"):
    return {"dates": pd.bdate_range(start, periods=len(values)).strftime("%Y-%m-%d").tolist(), "values": list(values)}


def dd_of(weights, m):                 # the drawdown path of A's series (value / running high - 1): A's own function, not a copy
    return drawdown_series(portfolio_series(weights, market=m))


def test_below_floor_rounds_like_the_rule_and_finds_the_longest_run():
    d = dd([0.0, -0.10, -0.1500004, -0.16, -0.20, -0.149, -0.151])
    out = proofs.below_floor(d, -0.15)
    assert (out["days"], out["of_days"], out["floor"], out["as_of"]) == (3, 7, -0.15, d["dates"][-1])
    assert out["longest"] == {"days": 2, "start": d["dates"][3], "end": d["dates"][4]}
    assert out["stretches"] == [[d["dates"][3], d["dates"][4]], [d["dates"][6], d["dates"][6]]]


def test_below_floor_never_below_and_equal_runs():
    never = proofs.below_floor(dd([0.0, -0.05]), -0.15)
    assert (never["days"], never["longest"], never["stretches"]) == (0, None, [])
    tie = proofs.below_floor(dd([-0.2, 0.0, -0.2]), -0.15)
    assert tie["longest"] == {"days": 1, "start": tie["stretches"][0][0], "end": tie["stretches"][0][0]}


@REAL
def test_real_days_below_robert_floor():
    m = load_market("2026-11-12")
    after = proofs.below_floor(dd_of(ROBERT_AFTER, m), -0.15)
    assert (after["days"], after["of_days"], len(after["stretches"])) == (203, 1282, 7)
    assert after["longest"] == {"days": 195, "start": "2022-04-20", "end": "2023-01-20"}
    assert proofs.below_floor(dd_of(ROBERT_TODAY, m), -0.15)["days"] == 0
    at8 = apply_change(ROBERT_TODAY, {"op": "set", "ticker": "NVDA", "weight": 0.08})
    assert proofs.below_floor(dd_of(at8, m), -0.15)["days"] == 0          # pitfall 5: -15.00004 % is not below -15.0 %


# P3 self-review additions (not in the brief): the rule pinned to B's, the ledger shape, the edges, an oracle, the real stretches.
BF_KEYS = {"days", "of_days", "floor", "longest", "stretches", "source", "as_of"}                   # ledger section 18, BF
BF_SOURCE = "Drawdown path (value / running high - 1) vs the floor, compared after rounding to 0.1 pp"


def test_the_local_rounding_is_the_exact_twin_of_governance_round_pp():       # ledger section 18: one rounding rule until P10
    import governance
    grid = [0.0, -0.0, 1e-9, 0.08, -0.08, -0.15, -0.1500004, -0.15000000000000002, -0.1499999, -0.1504999, -0.1505, -0.1495, -0.2, -1.0, 0.0005]
    grid += np.random.default_rng(7).uniform(-1.0, 0.1, 2000).tolist()
    assert all(proofs._round_pp(x) == governance.round_pp(x) for x in grid)
    floors = [-0.05, -0.15, -0.15000000000000002, -0.1505, -0.25, -0.45]
    assert all(proofs._breaks(v, f) == (governance.round_pp(v) < governance.round_pp(f)) for v in grid for f in floors)
    assert proofs._breaks(None, -0.15) is False                     # an unknown value is not counted as a break here
    assert proofs._breaks(-0.1500004, -0.15) is False              # pitfall 5: -15.00004 % rounds to -15.0 %, exactly at the limit
    assert proofs._breaks(-0.1505, -0.15) is True                  # a tie rounds away from zero: -15.05 % is -15.1 %


def test_below_floor_shape_is_the_ledger_one_and_plain_json():
    d = dd([0.0, -0.2, -0.3, 0.0])
    d["values"] = np.array(d["values"])                             # numpy in, plain Python out
    out = proofs.below_floor(d, np.float64(-0.15))
    assert set(out) == BF_KEYS and out["source"] == BF_SOURCE
    assert json.loads(json.dumps(out)) == out                       # lists, not tuples; nothing numpy
    assert (type(out["days"]), type(out["of_days"]), type(out["floor"]), type(out["longest"]["days"])) == (int, int, float, int)
    assert d["values"].tolist() == [0.0, -0.2, -0.3, 0.0]           # the input path is not edited


def test_below_floor_runs_at_the_start_the_end_and_over_the_whole_path():
    d = dd([-0.2, -0.3, 0.0, -0.1, -0.4])
    out = proofs.below_floor(d, -0.15)
    assert out["stretches"] == [[d["dates"][0], d["dates"][1]], [d["dates"][4], d["dates"][4]]]
    assert out["longest"] == {"days": 2, "start": d["dates"][0], "end": d["dates"][1]}
    w = dd([-0.2, -0.3, -0.4])
    whole = proofs.below_floor(w, -0.15)
    assert (whole["days"], whole["of_days"], whole["stretches"]) == (3, 3, [[w["dates"][0], w["dates"][2]]])
    assert whole["longest"] == {"days": 3, "start": w["dates"][0], "end": w["dates"][2]}


def test_the_longest_run_is_the_earliest_on_a_tie_and_the_later_one_when_it_is_longer():
    t = dd([-0.2, -0.2, 0.0, -0.3, -0.3])
    assert proofs.below_floor(t, -0.15)["longest"] == {"days": 2, "start": t["dates"][0], "end": t["dates"][1]}
    g = dd([-0.2, 0.0, -0.3, -0.3])
    assert proofs.below_floor(g, -0.15)["longest"] == {"days": 2, "start": g["dates"][2], "end": g["dates"][3]}


def test_a_run_goes_on_over_a_weekend_the_path_has_no_row_for():       # consecutive means consecutive rows of the path (trading days)
    d = {"dates": ["2022-01-06", "2022-01-07", "2022-01-10", "2022-01-11"], "values": [-0.2, -0.2, -0.2, 0.0]}    # Thu Fri Mon Tue
    out = proofs.below_floor(d, -0.15)
    assert out["stretches"] == [["2022-01-06", "2022-01-10"]] and out["longest"]["days"] == 3 and out["of_days"] == 4


def test_below_floor_counts_a_value_at_the_limit_as_inside_and_rounds_ties_away_from_zero():     # pitfall 5
    at = dd([-0.15, -0.1500004, -0.15000000000000002, -0.1504999, -0.1499999])      # each rounds to -15.0 % or -14.9..: none is below -15.0 %
    assert proofs.below_floor(at, -0.15)["days"] == 0
    assert proofs.below_floor(dd([-0.1505]), -0.15)["days"] == 1                    # -15.05 % rounds to -15.1 %
    assert proofs.below_floor(dd([-0.15]), -0.1505)["days"] == 0                    # the floor is rounded too: -15.05 % is -15.1 %
    assert proofs.below_floor(dd([-0.1505]), -0.15000000000000002)["days"] == 1     # the float-noise limit of the seal fixture


def test_below_floor_says_so_when_there_is_nothing_to_count_and_refuses_a_ragged_path():
    out = proofs.below_floor({"dates": [], "values": []}, -0.15)
    assert list(out) == ["error"] and out["error"].endswith(".")                    # a plain sentence, never "0 of 0 days"
    with pytest.raises(ValueError):
        proofs.below_floor({"dates": ["2022-01-03", "2022-01-04"], "values": [0.0]}, -0.15)
    with pytest.raises(ValueError):                                                 # 0.15 for -0.15 would count every day as below
        proofs.below_floor(dd([0.0, -0.05]), 0.15)
    assert proofs.below_floor(dd([0.0, -0.05]), 0.0)["days"] == 1                   # a floor of 0 % is allowed (governance allows it)


def test_below_floor_agrees_with_a_brute_force_count_on_random_paths():
    import itertools
    import governance
    rng = np.random.default_rng(20261114)
    for floor in (-0.05, -0.15, -0.25):
        d = dd(rng.uniform(-0.3, 0.0, 400).tolist())
        flag = [governance.round_pp(v) < governance.round_pp(floor) for v in d["values"]]
        runs = []
        for below, rows in itertools.groupby(range(len(flag)), key=flag.__getitem__):
            rows = list(rows)
            if below:
                runs.append((d["dates"][rows[0]], d["dates"][rows[-1]], len(rows)))
        out = proofs.below_floor(d, floor)
        assert (out["days"], out["of_days"]) == (sum(flag), 400) and 0 < out["days"] < 400
        assert out["stretches"] == [[s, e] for s, e, _ in runs]
        best = max(runs, key=lambda r: r[2])                  # max keeps the first of equal runs: the earliest on a tie
        assert out["longest"] == {"days": best[2], "start": best[0], "end": best[1]}


@REAL
def test_real_stretches_three_floors_and_what_a_raw_comparison_would_have_said():
    m = load_market("2026-11-12")
    path = dd_of(ROBERT_AFTER, m)
    after = proofs.below_floor(path, -0.15)
    assert after["stretches"][-2:] == [["2025-04-04", "2025-04-08"], ["2025-04-21", "2025-04-21"]]
    assert after["as_of"] == path["dates"][-1] and after["floor"] == -0.15
    assert sum(any(s <= day <= e for s, e in after["stretches"]) for day in path["dates"]) == after["days"]
    assert [proofs.below_floor(path, f)["days"] for f in (-0.15, -0.25, -0.45)] == [203, 84, 0]       # ledger 18: Robert, Mateo, Amira floors
    at8 = dd_of(apply_change(ROBERT_TODAY, {"op": "set", "ticker": "NVDA", "weight": 0.08}), m)
    assert [day for day, v in zip(at8["dates"], at8["values"]) if v < -0.15] == ["2022-10-14"]        # a raw comparison would count this day
    assert proofs.below_floor(at8, -0.15)["days"] == 0 and round(min(at8["values"]), 4) == -0.15


# --- Task P8: evidence rows behind each fact ---------------------------------------------------------
def evidence_case():
    dates = pd.bdate_range("2022-01-03", periods=4)
    px = pd.DataFrame({"AAA": [100.0, 120.0, np.nan, 90.0], "BBB.TO": [50.0, 50.0, 50.0, 50.0]}, index=dates)
    m = make_market(px, fx=pd.Series([1.25, 1.26, 1.27, 1.28], index=dates))
    iso = dates.strftime("%Y-%m-%d").tolist()
    result = {"as_of": iso[-1], "series": {"dates": iso, "today": [100.0] * 4, "after": [100.0, 110.0, 90.0, 95.0]},
              "metrics": {"after": {"peak_date": iso[1], "trough_date": iso[2]}},
              "portfolio": {"AAA": 0.6, "BBB.TO": 0.4}, "baseline": {"portfolio": {"BBB.TO": 1.0}},
              "trace": [{"id": "T5", "inputs": {"path": "metrics.after.max_drawdown"}}, {"id": "T1", "inputs": {"path": "amount"}},
                        {"id": "T9", "inputs": {"path": "metrics.today.cagr"}}]}
    return m, result, iso


def test_evidence_rows_behind_a_drawdown_fact():
    m, r, iso = evidence_case()
    assert proofs.evidence_rows("T5", r, m) == [
        {"file": proofs.PORTFOLIO_FILE, "date": iso[1], "ticker": "portfolio (after)", "value": 110.0},
        {"file": proofs.PORTFOLIO_FILE, "date": iso[2], "ticker": "portfolio (after)", "value": 90.0},
        {"file": "prices_daily.csv", "date": iso[1], "ticker": "AAA", "value": 120.0},
        {"file": "prices_daily.csv", "date": iso[1], "ticker": "AAA", "value": 120.0},       # no AAA row on the trough day: its last real row
        {"file": "fx_usdcad_daily.csv", "date": iso[2], "ticker": "USDCAD", "value": 1.27}]


def test_evidence_rows_today_cad_line_inputs_and_public():
    m, r, iso = evidence_case()
    assert [(x["ticker"], x["date"]) for x in proofs.evidence_rows("T9", r, m)] == [
        ("portfolio (today)", iso[0]), ("portfolio (today)", iso[3]), ("BBB.TO", iso[0]), ("BBB.TO", iso[3])]
    assert proofs.evidence_rows("T1", r, m) == [] and proofs.evidence_rows("T5", r, m, public=True) == []
    assert len(proofs.evidence_rows("T5", r, {"as_of": r["as_of"]})) == 2           # a market without prices: the portfolio rows only


@REAL
def test_real_evidence_rows_for_robert_worst_drop():
    m = load_market("2026-11-12")
    s = portfolio_series(ROBERT_AFTER, market=m)
    r = {"as_of": "2026-11-12", "series": {"dates": s["dates"], "after": s["values"]}, "metrics": {"after": risk_metrics(s)},
         "portfolio": ROBERT_AFTER, "baseline": {"portfolio": ROBERT_TODAY}, "trace": [{"id": "T6", "inputs": {"path": "metrics.after.max_drawdown"}}]}
    rows = proofs.evidence_rows("T6", r, m)
    assert [(x["file"], x["date"], x["ticker"]) for x in rows] == [
        (proofs.PORTFOLIO_FILE, "2021-11-29", "portfolio (after)"), (proofs.PORTFOLIO_FILE, "2022-10-14", "portfolio (after)"),
        ("prices_daily.csv", "2021-11-29", "NVDA"), ("prices_daily.csv", "2022-10-14", "NVDA"), ("fx_usdcad_daily.csv", "2022-10-14", "USDCAD")]
    assert [x["value"] for x in rows] == pytest.approx([103.8997, 68.0290, 33.2296, 11.1867, 1.3856], abs=1e-4)


def only(rows, file):
    return [x for x in rows if x["file"] == file]


def test_evidence_constants():
    assert proofs.EVIDENCE_LIMIT == 5 and proofs.PORTFOLIO_FILE == "computed: portfolio_series (base 100, CAD)"


def test_evidence_dates_follow_the_path_of_the_fact():           # the Decision: which dates, by inputs.path
    m, r, iso = evidence_case()
    r["worst_rolling"] = {"after": {"value": -0.1, "peak_date": iso[0], "trough_date": iso[1]}}
    r["below_floor"] = {"today": None, "after": {"days": 3, "of_days": 4, "longest": {"days": 2, "start": iso[1], "end": iso[2]}}}
    r["trace"] += [{"id": f"T{i}", "inputs": {"path": p}} for i, p in enumerate((
        "worst_rolling.after.value", "below_floor.after.days", "below_floor.after.longest.days", "below_floor.after.of_days",
        "below_floor.today.days", "metrics.after.recovery_days", "metrics.aligned.cagr", "risk.after.shares", "limits.floor"), 20)]
    dates = lambda fid: [x["date"] for x in only(proofs.evidence_rows(fid, r, m), proofs.PORTFOLIO_FILE)]
    assert dates("T20") == [iso[0], iso[1]]                       # the worst 12-month window, not the all-time drop
    assert dates("T21") == dates("T22") == [iso[1], iso[2]]       # the longest stretch's start and end
    for fid in ("T23", "T24", "T25", "T26", "T27", "T28"):        # a count, no stretch (today is null), days to recover, aligned, a share, a limit
        assert proofs.evidence_rows(fid, r, m) == [], fid


def test_a_one_day_stretch_and_a_stretch_that_is_null_give_one_date_and_none():
    m, r, iso = evidence_case()
    r["below_floor"] = {"after": {"days": 1, "longest": {"days": 1, "start": iso[1], "end": iso[1]}}, "today": {"days": 0, "longest": None}}
    r["trace"] += [{"id": "T30", "inputs": {"path": "below_floor.after.days"}}, {"id": "T31", "inputs": {"path": "below_floor.today.days"}}]
    assert [(x["ticker"], x["date"]) for x in proofs.evidence_rows("T30", r, m)] == [
        ("portfolio (after)", iso[1]), ("AAA", iso[1]), ("USDCAD", iso[1])]       # one date, never the same row twice
    assert proofs.evidence_rows("T31", r, m) == []                                 # no day below the floor: no dates


def test_evidence_rows_drop_every_date_after_as_of():            # red gate 3: the market below runs to iso[3], the decision to iso[1]
    m, r, iso = evidence_case()
    r["as_of"] = iso[1]
    rows = proofs.evidence_rows("T5", r, m)
    assert [(x["ticker"], x["date"], x["value"]) for x in rows] == [("portfolio (after)", iso[1], 110.0), ("AAA", iso[1], 120.0), ("USDCAD", iso[1], 1.26)]
    r["as_of"] = iso[0]
    assert proofs.evidence_rows("T5", r, m) == [] and proofs.evidence_rows("T9", r, m) != []        # T9 starts on iso[0]: only its first date stays
    assert {x["date"] for x in proofs.evidence_rows("T9", r, m)} == {iso[0]}


def test_the_fact_dates_helper_returns_the_side_and_the_kept_dates():
    m, r, iso = evidence_case()
    assert proofs._fact_dates("metrics.after.max_drawdown", r) == ("after", [iso[1], iso[2]])
    assert proofs._fact_dates("metrics.today.cagr", r) == ("today", [iso[0], iso[3]])
    assert proofs._fact_dates("amount", r) == (None, []) and proofs._fact_dates(None, r) == (None, [])
    assert proofs._fact_dates("metrics.after.cagr.extra", r) == (None, []) and proofs._fact_dates(["metrics"], r) == (None, [])


def test_the_largest_line_is_chosen_per_side_and_ties_go_to_the_first_ticker():
    m, r, iso = evidence_case()
    line = lambda fid: [x["ticker"] for x in proofs.evidence_rows(fid, r, m) if x["file"] == "prices_daily.csv"]
    assert line("T5") == ["AAA", "AAA"] and line("T9") == ["BBB.TO", "BBB.TO"]       # after = portfolio; today = baseline.portfolio (a change)
    r["baseline"] = None                                                                # no change: today is the evaluated mix too
    assert line("T9") == ["AAA", "AAA"]
    r["portfolio"] = {"BBB.TO": 0.5, "AAA": 0.5}                                        # equal weights: the first ticker in alphabetical order, not in dict order
    assert line("T5") == ["AAA", "AAA"]
    r["portfolio"] = {"AAA": 0.3, "BBB.TO": 0.7}                                        # the heavier line wins whatever its name
    assert line("T5") == ["BBB.TO", "BBB.TO"]
    r["portfolio"] = {"AAA": 0.0, "ZZZ": 0.0, "BBB.TO": 0.0}                            # no line above 0: no price rows, and no crash
    assert line("T5") == [] and len(proofs.evidence_rows("T5", r, m)) == 2


def test_a_usd_line_adds_the_rate_of_its_last_date_and_a_cad_line_does_not():
    m, r, iso = evidence_case()
    fx = lambda fid: only(proofs.evidence_rows(fid, r, m), "fx_usdcad_daily.csv")
    assert fx("T5") == [{"file": "fx_usdcad_daily.csv", "date": iso[2], "ticker": "USDCAD", "value": 1.27}]          # the last of the two dates
    assert fx("T9") == []                                                                                           # BBB.TO is listed in CAD
    dates = pd.DatetimeIndex(iso)
    px = pd.DataFrame({"AAA": [100.0, 120.0, np.nan, 90.0], "BBB.TO": [50.0] * 4}, index=dates)
    late = make_market(px, fx=pd.Series([1.31], index=dates[3:]))                                                   # the first rate comes on iso[3]
    assert [x["ticker"] for x in proofs.evidence_rows("T5", r, late)] == ["portfolio (after)"] * 2 + ["AAA"] * 2   # never a later rate back-filled
    assert [x["value"] for x in only(proofs.evidence_rows("T9", {**r, "baseline": None}, late), "fx_usdcad_daily.csv")] == [1.31]


def fx_case(published):
    """A six-day market whose file lists USD/CAD only on the days of `published` ({day number: rate}); the bundle carries the last rate
    over a day without one, as `load_market` does."""
    dates = pd.bdate_range("2022-01-03", periods=6)
    px = pd.DataFrame({"AAA": [100.0 + i for i in range(6)]}, index=dates)
    return make_market(px, fx=pd.Series(list(published.values()), index=dates[list(published)])), dates.strftime("%Y-%m-%d").tolist(), dates


def fx_rows_at(market, iso, day):
    """(date, value) of the USD/CAD rows for a drop whose trough is the day with the number `day`."""
    r = {"as_of": iso[-1], "series": {"dates": iso, "after": [100.0] * 6}, "portfolio": {"AAA": 1.0}, "baseline": None,
         "metrics": {"after": {"peak_date": iso[0], "trough_date": iso[day]}}, "trace": [{"id": "T5", "inputs": {"path": "metrics.after.max_drawdown"}}]}
    return [(x["date"], x["value"]) for x in only(proofs.evidence_rows("T5", r, market), "fx_usdcad_daily.csv")]


def test_the_usd_cad_row_is_dated_by_the_file_row_it_came_from_not_the_day_it_was_carried_to():
    market, iso, dates = fx_case({0: 1.25, 1: 1.26, 4: 1.30, 5: 1.30})              # the file has no row for iso[2] and iso[3]
    assert market["fx"].tolist() == [1.25, 1.26, 1.26, 1.26, 1.30, 1.30]             # what the bundle holds: the rate carried over the hole
    rate = lambda day, m=market: fx_rows_at(m, iso, day)
    assert rate(0) == [(iso[0], 1.25)] and rate(1) == [(iso[1], 1.26)]               # a listed day cites itself
    assert rate(2) == [(iso[1], 1.26)] and rate(3) == [(iso[1], 1.26)]               # a day with no row: the row the rate came from, one day or two
    assert rate(4) == [(iso[4], 1.30)]                                               # the next listed day is its own row, not the rate before it
    assert rate(5) == [(iso[4], 1.30)]                                               # the same rate twice: the first day of it, a row of the file for sure
    only_one, iso1, _ = fx_case({1: 1.26})                                           # a single rate, carried to the end of the calendar
    assert [rate(day, only_one) for day in (0, 1, 4, 5)] == [[], [(iso1[1], 1.26)], [(iso1[1], 1.26)], [(iso1[1], 1.26)]]     # none before it, never a later one
    blank = {**market, "fx": pd.Series([1.25, 1.26, np.nan, np.nan, 1.30, 1.30], index=dates)}      # a bundle made by hand: blanks, nothing carried
    assert rate(2, blank) == [(iso[1], 1.26)] and rate(3, blank) == [(iso[1], 1.26)] and rate(5, blank) == [(iso[4], 1.30)]
    assert rate(0, {**market, "fx": pd.Series([np.nan, 1.26, 1.26, 1.30, 1.30, 1.30], index=dates)}) == []        # a blank first day: no rate yet


def test_a_filled_price_is_never_cited_the_last_real_row_is():
    dates = pd.bdate_range("2022-01-03", periods=4)
    iso = dates.strftime("%Y-%m-%d").tolist()
    filled = pd.DataFrame({"AAA": [100.0, 120.0, 120.0, 90.0]}, index=dates)                 # the loader forward-fills the day AAA did not trade
    m = make_market(filled, traded=pd.DataFrame({"AAA": [True, True, False, True]}, index=dates), fx=1.25)
    r = {"as_of": iso[3], "series": {"dates": iso, "after": [100.0, 110.0, 90.0, 95.0]}, "portfolio": {"AAA": 1.0},
         "metrics": {"after": {"peak_date": iso[0], "trough_date": iso[2]}}, "trace": [{"id": "T1", "inputs": {"path": "metrics.after.max_drawdown"}}]}
    assert [(x["date"], x["value"]) for x in only(proofs.evidence_rows("T1", r, m), "prices_daily.csv")] == [(iso[0], 100.0), (iso[1], 120.0)]
    r["metrics"]["after"]["peak_date"] = iso[3]                                               # a traded day cites itself
    assert [x["date"] for x in only(proofs.evidence_rows("T1", r, m), "prices_daily.csv")] == [iso[3], iso[1]]
    solo = make_market(filled.iloc[1:], traded=pd.DataFrame({"AAA": [False, False, True]}, index=dates[1:]), fx=1.25)
    r["metrics"]["after"] = {"peak_date": iso[1], "trough_date": iso[2]}                      # no real row on or before either date: no price row
    assert [x["ticker"] for x in proofs.evidence_rows("T1", r, solo)] == ["portfolio (after)"] * 2       # and no rate of its own: a rate belongs to a price


def test_the_cnq_correction_is_named_for_that_ticker_and_the_rows_own_date():          # pitfall 1: x 1.021 before 2022-08-22, no other ticker
    dates = pd.to_datetime(["2022-08-18", "2022-08-19", "2022-08-22", "2022-08-23"])
    iso = dates.strftime("%Y-%m-%d").tolist()
    px = pd.DataFrame({"CNQ.TO": [51.0, 52.0, 53.0, 54.0], "RY.TO": [10.0, 11.0, 12.0, 13.0]}, index=dates)
    m = make_market(px, traded=pd.DataFrame({"CNQ.TO": [True, True, False, True], "RY.TO": [True] * 4}, index=dates))
    corrected, plain = "prices_daily.csv (adj_close x 1.021, spec 9)", "prices_daily.csv"
    r = {"as_of": iso[3], "series": {"dates": iso, "after": [100.0, 101.0, 102.0, 103.0]}, "portfolio": {"CNQ.TO": 1.0},
         "metrics": {"after": {"peak_date": iso[1], "trough_date": iso[3]}}, "trace": [{"id": "T1", "inputs": {"path": "metrics.after.max_drawdown"}}]}
    assert [(x["file"], x["date"], x["value"]) for x in proofs.evidence_rows("T1", r, m)[2:]] == [(corrected, iso[1], 52.0), (plain, iso[3], 54.0)]
    r["metrics"]["after"] = {"peak_date": iso[2], "trough_date": iso[3]}                      # iso[2]: no CNQ row, so its last real row (before the cutoff) is cited
    assert [(x["file"], x["date"]) for x in proofs.evidence_rows("T1", r, m)[2:]] == [(corrected, iso[1]), (plain, iso[3])]
    r["portfolio"] = {"RY.TO": 1.0}
    assert {x["file"] for x in proofs.evidence_rows("T1", r, m)[2:]} == {plain}               # no other ticker is labelled
    assert corrected == f"prices_daily.csv (adj_close x {CNQ_FIX_FACTOR}, spec 9)"


def test_evidence_rows_are_plain_json_and_edit_nothing():
    m, r, iso = evidence_case()
    r["series"]["after"] = np.array(r["series"]["after"])                                # numpy in, plain Python out
    r["metrics"]["after"] = {k: np.str_(v) for k, v in r["metrics"]["after"].items()}
    frames = {k: m[k].copy() for k in ("local", "traded", "fx")}
    mix = {"portfolio": dict(r["portfolio"]), "trace": [dict(t) for t in r["trace"]]}
    rows = proofs.evidence_rows("T5", r, m)
    assert len(rows) == 5 and all(list(x) == ["file", "date", "ticker", "value"] for x in rows)
    assert all(type(x["value"]) is float and type(x["date"]) is str and type(x["ticker"]) is str for x in rows)
    assert json.loads(json.dumps(rows)) == rows
    assert (r["portfolio"], r["trace"]) == (mix["portfolio"], mix["trace"])
    assert all(m[k].equals(frames[k]) for k in frames)                                    # the shared bundle is never mutated
    assert proofs.evidence_rows("T5", r, m) == rows                                       # the same call twice gives the same rows


def test_the_cap_keeps_the_portfolio_rows_first(monkeypatch):
    m, r, iso = evidence_case()
    monkeypatch.setattr(proofs, "EVIDENCE_LIMIT", 3)
    assert [x["ticker"] for x in proofs.evidence_rows("T5", r, m)] == ["portfolio (after)", "portfolio (after)", "AAA"]


def test_evidence_rows_say_nothing_when_a_piece_is_missing():
    m, r, iso = evidence_case()
    assert proofs.evidence_rows("T404", r, m) == []                                       # not a trace row
    assert proofs.evidence_rows("T5", {**r, "trace": [{"id": "T5"}]}, m) == []            # no inputs
    assert proofs.evidence_rows("T5", {**r, "trace": [{"id": "T5", "inputs": None}]}, m) == []
    assert proofs.evidence_rows("T5", {k: v for k, v in r.items() if k != "trace"}, m) == []
    assert proofs.evidence_rows("T5", {**r, "metrics": {"after": None}}, m) == []         # the side has no metrics
    assert proofs.evidence_rows("T5", {**r, "metrics": {"after": {"peak_date": None, "trough_date": None}}}, m) == []
    assert [x["ticker"] for x in proofs.evidence_rows("T5", r, None)] == ["portfolio (after)"] * 2       # no bundle: portfolio rows only
    assert [x["ticker"] for x in proofs.evidence_rows("T5", r, {**m, "traded": None})] == ["portfolio (after)"] * 2
    assert [x["ticker"] for x in proofs.evidence_rows("T5", {**r, "series": None}, m)] == ["AAA", "AAA", "USDCAD"]
    assert [x["ticker"] for x in proofs.evidence_rows("T5", {**r, "portfolio": None}, m)] == ["portfolio (after)"] * 2
    ragged = {**r, "series": {"dates": r["series"]["dates"], "after": [100.0, 110.0]}}      # a value per date or nothing: never a shifted one
    assert only(proofs.evidence_rows("T5", ragged, m), proofs.PORTFOLIO_FILE) == []
    unknown = {**r, "portfolio": {"ZZZ": 1.0}}                                            # a line the bundle does not know: no price row, no rate
    assert [x["ticker"] for x in proofs.evidence_rows("T5", unknown, m)] == ["portfolio (after)"] * 2


def test_evidence_rows_without_an_as_of_to_check_against_say_nothing():       # red gate 3 fails closed: no cutoff, no date can be kept
    m, r, iso = evidence_case()
    assert proofs.evidence_rows("T5", {k: v for k, v in r.items() if k != "as_of"}, m) == []
    assert proofs.evidence_rows("T5", {**r, "as_of": None}, m) == []


def test_public_rows_are_empty_and_never_read_the_bundle():       # licence (red gate 8): D Task 15 and P10 call it with market=None
    m, r, iso = evidence_case()
    assert proofs.evidence_rows("T5", r, None, public=True) == [] and proofs.evidence_rows("T9", {}, None, public=True) == []

    class Boom(dict):
        def get(self, *a):
            raise AssertionError("the public cut must not read prices")
        __getitem__ = get
    assert proofs.evidence_rows("T5", r, Boom(m), public=True) == []


def test_the_dollar_loss_gets_the_drawdowns_data_rows_and_the_fictional_amount_none():   # ledger 30: dollars are ○, the drawdown ●
    m, r, iso = evidence_case()
    r["amount"] = 600000
    r["trace"] += [{"id": "T7", "inputs": {"path": "metrics.after.max_drawdown", "recipe": "evaluate.after", "formula": "amount * metrics.after.max_drawdown"}},
                   {"id": "T2", "inputs": {"path": "amount", "recipe": "flight_plan"}}]
    rows = proofs.evidence_rows("T7", r, m)
    assert rows == proofs.evidence_rows("T5", r, m) and rows                 # the same replay rows, base 100 and prices, never dollars
    assert {x["file"] for x in rows} <= {proofs.PORTFOLIO_FILE, "prices_daily.csv", "fx_usdcad_daily.csv"}
    assert proofs.evidence_rows("T2", r, m) == []                            # the amount is the user's input, not a data row


@REAL
def test_real_evidence_rows_for_growth_per_year_the_first_and_last_day():          # plan P, s7_evidence_catalog.py
    m = load_market("2026-11-12")
    s = portfolio_series(ROBERT_AFTER, market=m)
    r = {"as_of": "2026-11-12", "series": {"dates": s["dates"], "after": s["values"]}, "metrics": {"after": risk_metrics(s)},
         "portfolio": ROBERT_AFTER, "baseline": {"portfolio": ROBERT_TODAY}, "trace": [{"id": "T10", "inputs": {"path": "metrics.after.cagr"}}]}
    rows = proofs.evidence_rows("T10", r, m)
    assert [(x["date"], x["ticker"]) for x in rows] == [("2021-11-12", "portfolio (after)"), ("2026-11-12", "portfolio (after)"),
                                                        ("2021-11-12", "NVDA"), ("2026-11-12", "NVDA"), ("2026-11-12", "USDCAD")]
    assert [x["value"] for x in rows] == pytest.approx([100.0, 307.8461, 30.256729, 166.190002, 1.4255], abs=1e-4)


@REAL
def test_real_evidence_rows_today_with_a_change_cite_the_baseline_line_and_no_rate():
    m = load_market("2026-11-12")
    s = portfolio_series(ROBERT_TODAY, market=m)
    r = {"as_of": "2026-11-12", "series": {"dates": s["dates"], "today": s["values"]}, "metrics": {"today": risk_metrics(s)},
         "portfolio": ROBERT_AFTER, "baseline": {"portfolio": ROBERT_TODAY}, "trace": [{"id": "T5", "inputs": {"path": "metrics.today.max_drawdown"}}]}
    rows = proofs.evidence_rows("T5", r, m)                                       # XIU.TO is the largest line of today's mix (45 %), listed in CAD
    assert [(x["file"], x["ticker"]) for x in rows] == [(proofs.PORTFOLIO_FILE, "portfolio (today)")] * 2 + [("prices_daily.csv", "XIU.TO")] * 2
    assert [x["date"] for x in rows] == [r["metrics"]["today"]["peak_date"], r["metrics"]["today"]["trough_date"]] * 2
    by_date = dict(zip(s["dates"], s["values"]))
    assert [x["value"] for x in rows[:2]] == [by_date[x["date"]] for x in rows[:2]]


@REAL
def test_real_evidence_rows_for_the_longest_stretch_below_the_floor():
    m = load_market("2026-11-12")
    s = portfolio_series(ROBERT_AFTER, market=m)
    bf = proofs.below_floor(drawdown_series(s), -0.15)
    r = {"as_of": "2026-11-12", "series": {"dates": s["dates"], "after": s["values"]}, "below_floor": {"after": bf, "today": None},
         "portfolio": ROBERT_AFTER, "baseline": {"portfolio": ROBERT_TODAY},
         "trace": [{"id": "T11", "inputs": {"path": "below_floor.after.days"}}, {"id": "T12", "inputs": {"path": "below_floor.after.longest.days"}}]}
    rows = proofs.evidence_rows("T11", r, m)
    assert rows == proofs.evidence_rows("T12", r, m) and len(rows) == 5
    assert [x["date"] for x in rows] == ["2022-04-20", "2023-01-20", "2022-04-20", "2023-01-20", "2023-01-20"]
    assert [x["value"] for x in rows[:2]] == pytest.approx([87.9664, 85.8659], abs=1e-4)


@REAL
def test_real_evidence_rows_cite_the_last_real_row_on_a_us_holiday_and_the_cnq_correction():
    m = load_market("2026-11-12")
    iso = lambda rows: [(x["file"], x["date"], x["ticker"]) for x in rows]
    at = lambda day, mix: {"as_of": "2026-11-12", "series": {"dates": [day], "after": [100.0]}, "portfolio": mix,
                           "metrics": {"after": {"peak_date": day, "trough_date": day}}, "trace": [{"id": "T1", "inputs": {"path": "metrics.after.max_drawdown"}}]}
    rows = proofs.evidence_rows("T1", at("2022-01-17", {"NVDA": 1.0}), m)         # Martin Luther King Day: the TSX is open, NASDAQ is closed
    assert iso(rows) == [(proofs.PORTFOLIO_FILE, "2022-01-17", "portfolio (after)"), ("prices_daily.csv", "2022-01-14", "NVDA"), ("fx_usdcad_daily.csv", "2022-01-17", "USDCAD")]
    assert rows[1]["value"] == pytest.approx(26.827137, abs=1e-6)
    raw = pd.read_csv("data/starter/prices_daily.csv", usecols=["date", "ticker", "adj_close"], dtype={"date": str})
    cnq = lambda day: raw.loc[(raw["ticker"] == "CNQ.TO") & (raw["date"] == day), "adj_close"].iloc[0]
    before, after = (proofs.evidence_rows("T1", at(day, {"CNQ.TO": 1.0}), m)[1] for day in ("2022-08-19", "2022-08-22"))
    assert before["file"] == "prices_daily.csv (adj_close x 1.021, spec 9)" and before["value"] == pytest.approx(cnq("2022-08-19") * 1.021, abs=1e-9)
    assert after["file"] == "prices_daily.csv" and after["value"] == pytest.approx(cnq("2022-08-22"), abs=1e-9)    # the first day without the correction


@REAL
def test_real_evidence_rows_never_pass_the_decision_date():
    m = load_market("2025-01-31")                                                  # the sealed envelope's past date
    s = portfolio_series(ROBERT_AFTER, as_of="2025-01-31", market=m)
    r = {"as_of": "2025-01-31", "series": {"dates": s["dates"], "after": s["values"]}, "metrics": {"after": risk_metrics(s)},
         "portfolio": ROBERT_AFTER, "baseline": {"portfolio": ROBERT_TODAY}, "trace": [{"id": "T6", "inputs": {"path": "metrics.after.cagr"}}]}
    rows = proofs.evidence_rows("T6", r, m)
    assert len(rows) == 5 and max(x["date"] for x in rows) == "2025-01-31"
    r["trace"].append({"id": "T7", "inputs": {"path": "metrics.after.max_drawdown"}})
    r["metrics"]["after"]["trough_date"] = "2026-11-12"                              # a date from the future of this decision is dropped
    assert {x["date"] for x in proofs.evidence_rows("T7", r, m)} == {r["metrics"]["after"]["peak_date"]}


@REAL
def test_real_worst_drop_rows_let_a_reader_redo_the_arithmetic_by_hand():       # the point of the drawer: trough over peak, less one
    m = load_market("2026-11-12")
    s = portfolio_series(ROBERT_AFTER, market=m)
    metrics = risk_metrics(s)
    r = {"as_of": "2026-11-12", "series": {"dates": s["dates"], "after": s["values"]}, "metrics": {"after": metrics}, "portfolio": ROBERT_AFTER,
         "baseline": {"portfolio": ROBERT_TODAY}, "trace": [{"id": "T6", "inputs": {"path": "metrics.after.max_drawdown"}}]}
    peak, trough = proofs.evidence_rows("T6", r, m)[:2]
    assert trough["value"] / peak["value"] - 1 == pytest.approx(metrics["max_drawdown"], abs=1e-12)
    assert round(metrics["max_drawdown"], 3) == -0.345                           # the -34.5 % of the spec, read off two printed numbers


def one_day_result(day, mix):
    """A Result one day long: a drop whose peak and trough are `day`, on the mix `mix`."""
    return {"as_of": "2026-11-12", "series": {"dates": [day], "after": [100.0]}, "portfolio": mix, "metrics": {"after": {"peak_date": day, "trough_date": day}},
            "trace": [{"id": "T1", "inputs": {"path": "metrics.after.max_drawdown"}}]}


def starter_fx():
    return pd.read_csv("data/starter/fx_usdcad_daily.csv", usecols=["date", "usdcad"], dtype={"date": str}).set_index("date")["usdcad"]


@REAL
def test_real_usd_cad_row_on_a_canadian_holiday_cites_the_file_row_it_was_carried_from():
    m, file_rate = load_market("2026-11-12"), starter_fx()
    assert "2022-10-10" not in file_rate.index                                         # Thanksgiving in Canada: the Bank of Canada lists no rate, Wall Street is open
    assert file_rate["2022-10-07"] == pytest.approx(1.3712, abs=1e-12) and file_rate["2022-10-11"] == pytest.approx(1.3775, abs=1e-12)
    rows = proofs.evidence_rows("T1", one_day_result("2022-10-10", {"NVDA": 1.0}), m)
    assert [(x["file"], x["date"], x["ticker"]) for x in rows] == [
        (proofs.PORTFOLIO_FILE, "2022-10-10", "portfolio (after)"), ("prices_daily.csv", "2022-10-10", "NVDA"), ("fx_usdcad_daily.csv", "2022-10-07", "USDCAD")]
    assert rows[2]["value"] == pytest.approx(1.3712, abs=1e-12)                        # the Friday's rate, not the Tuesday's 1.3775


@REAL
def test_real_every_usd_cad_row_is_a_row_of_the_file_with_the_rate_of_that_day():
    m, file_rate = load_market("2026-11-12"), starter_fx()
    days = m["calendar"].strftime("%Y-%m-%d").tolist()
    carried = [day for day in days if day not in file_rate.index]
    assert set(file_rate.index) <= set(days) and carried                               # the premise: every listed day is on the calendar; some calendar days are not listed (37)
    for day in days:
        (row,) = proofs._fx_rows(day, m)
        assert row["date"] <= day and row["date"] in file_rate.index, day              # a day the file lists, never a later one
        assert row["value"] == pytest.approx(file_rate[row["date"]], abs=1e-12), day   # that row's own rate...
        assert row["value"] == pytest.approx(m["fx"][pd.Timestamp(day)], abs=1e-12), day       # ...which is the rate the code used on `day`
    assert all(proofs._fx_rows(day, m)[0]["date"] < day for day in carried)            # a day with no row is never cited as one


# --- Task P9: the Proof block inputs ------------------------------------------------------------------
JUNIT = """<testsuites><testsuite name="pytest" errors="0" failures="1" skipped="1" tests="5" time="2.5">
<testcase classname="tests.test_proofs" name="test_scramble_keeps_the_seal_of_an_honest_decision" time="0.1"/>
<testcase classname="tests.test_proofs" name="test_scramble_breaks_the_seal_of_a_leaky_decision" time="0.1"/>
<testcase classname="tests.test_data" name="test_perturbation_scrambles_every_later_row_and_every_key_stays_identical" time="0.1"/>
<testcase classname="tests.test_x" name="test_fails" time="0.1"><failure message="x"/></testcase>
<testcase classname="tests.test_x" name="test_skipped" time="0.1"><skipped message="s"/></testcase>
</testsuite></testsuites>"""


def test_tally_from_junit_counts_and_the_lookahead_tests():
    t = proofs.tally_from_junit(JUNIT, commit="4e154b3", date="2026-11-15")
    assert {k: t[k] for k in ("passed", "failed", "errors", "skipped", "total", "seconds", "commit", "date")} == {
        "passed": 3, "failed": 1, "errors": 0, "skipped": 1, "total": 5, "seconds": 2.5, "commit": "4e154b3", "date": "2026-11-15"}
    assert t["lookahead"] == {"name": "scramble the future", "passed": True, "tests": list(proofs.LOOKAHEAD_TESTS)}
    leak = JUNIT.replace('leaky_decision" time="0.1"/>', 'leaky_decision" time="0.1"><failure message="x"/></testcase>')
    assert proofs.tally_from_junit(leak, commit=None, date="2026-11-15")["lookahead"]["passed"] is False
    gone = JUNIT.replace("test_perturbation_scrambles", "test_other")
    assert proofs.tally_from_junit(gone, commit=None, date="2026-11-15")["lookahead"]["passed"] is None


def test_run_cost_at_dated_prices(monkeypatch):
    trace = [{"service": "Amazon Bedrock", "model": config.MODEL_ID, "usage": {"inputTokens": 900, "outputTokens": 120}},
             {"service": "Amazon Bedrock", "model": config.MODEL_ID, "usage": {"inputTokens": 3000, "outputTokens": 700, "cacheReadInputTokens": 2500}},
             {"service": "Python", "model": None, "usage": None}]
    p_in, p_out = config.PRICE_USD_PER_MTOK[config.MODEL_ID]
    monkeypatch.setattr(config, "PRICES_AS_OF", "2026-11-01", raising=False)
    monkeypatch.setattr(config, "PRICES_SOURCE", "Amazon Bedrock pricing page", raising=False)
    assert proofs.run_cost(trace) == {"calls": 2, "usd": pytest.approx((3900 * p_in + 820 * p_out + 2500 * p_in * config.CACHE_READ_MULT) / 1e6),
                                      "price_date": "2026-11-01", "price_source": "Amazon Bedrock pricing page"}
    assert proofs.run_cost(trace + [{"service": "Amazon Bedrock", "model": "unknown-model", "usage": {"inputTokens": 1}}])["usd"] is None
    monkeypatch.delattr(config, "PRICES_AS_OF")
    assert proofs.run_cost(trace)["usd"] is None                       # no undated price claim


def test_proof_block_reads_the_result_and_two_files(tmp_path):
    r = {"receipt": {"verified": 14, "total": 14, "first_try": {"verified": 13, "total": 14}}, "trace": []}
    out = proofs.proof_block(r, eval_path=tmp_path / "none.json", tally_path=tmp_path / "none.json")
    assert out["receipt"] == {"verified": 14, "total": 14, "first_try": {"verified": 13, "total": 14}} and out["telemetry"]["calls"] == 0
    assert (out["eval"], out["eval_note"], out["tally"], out["lookahead"]) == (None, "eval pending", None, None)
    ev = {"n": 40, "model": "us.anthropic.claude-sonnet-5-5", "date": "2026-11-15", "metric": "families and verdict both right",
          "arms": [{"arm": "navigator", "k": 37, "n": 40, "lo": 0.801, "hi": 0.974}], "adversarial": {"k": 10, "n": 10}}
    (tmp_path / "eval.json").write_text(json.dumps(ev))
    (tmp_path / "tally.json").write_text(json.dumps(proofs.tally_from_junit(JUNIT, commit="4e154b3", date="2026-11-15")))
    out = proofs.proof_block({"receipt": None, "trace": []}, eval_path=tmp_path / "eval.json", tally_path=tmp_path / "tally.json")
    assert out["eval"] == ev and out["eval_note"] is None and out["receipt"] is None
    assert out["tally"]["passed"] == 3 and "lookahead" not in out["tally"] and out["lookahead"]["passed"] is True


def test_record_tally_writes_the_file_even_when_a_test_fails(tmp_path, monkeypatch):
    import scripts.record_tally as rt
    def fake_run(cmd, **kw):
        Path(cmd[cmd.index("--junitxml") + 1]).write_text(JUNIT)
        return subprocess.CompletedProcess(cmd, 1)
    monkeypatch.setattr(rt.subprocess, "run", fake_run)
    monkeypatch.setattr(rt, "git_commit", lambda: "4e154b3")
    out = tmp_path / "tally.json"
    assert rt.main(["--out", str(out)]) == 1
    assert json.loads(out.read_text())["failed"] == 1 and json.loads(out.read_text())["commit"] == "4e154b3"
