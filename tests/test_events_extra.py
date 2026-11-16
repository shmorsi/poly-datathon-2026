"""Task 9 and 10 tests: tools/events.py: the shock catalog loader, the time rule, campaign episodes, one shock's
impact on a portfolio (Task 9) and the shock check: turbulence by family, the stress value, drawdown attribution
(Task 10, the section at the end); spec section 10; ledger sections 1, 7, 14.

the data lead's tests pin the plan's rules on synthetic markets; the finance lead's tests/test_events.py carries the finance
truth of the catalog itself (run it too). Offline: `make_market` frames and a CSV written to tmp_path.
The real-data cases skip when data/starter/ is absent.
"""
import numpy as np, pandas as pd, pytest
from pathlib import Path
from tools.data import make_market
from tools.portfolio import portfolio_series
from tools.events import load_events, episodes, event_impact

CAL = pd.bdate_range("2023-09-01", "2023-12-29")
COLS = "event_id,date,announced,title_fr,category,regions,lat,lon,description_fr,source_url,verified_on"

def write_events(tmp_path, rows):          # rows: (id, date, announced, category) in the old CSV format
    lines = [COLS] + [f"{i},{d},{a},Titre {i},{c},USA;CAN,38.9,-77.0,Desc,https://x.test,2026-11-14" for i, d, a, c in rows]
    (tmp_path / "events.csv").write_text("\n".join(lines) + "\n")
    return tmp_path / "events.csv"

def market(xiu=None, nvda=None, btc_days=None):
    p = pd.DataFrame({"XIU.TO": 100.0, "NVDA": 100.0}, index=CAL)
    for col, pts in (("XIU.TO", xiu), ("NVDA", nvda)):
        for d, v in (pts or {}).items():
            p.loc[d:, col] = v
    p.loc["2023-10-09", "XIU.TO"] = np.nan                       # TSX closed (Thanksgiving)
    crypto = pd.DataFrame({"BTC-USD": 100.0}, index=pd.date_range("2023-09-01", "2023-12-31"))
    for d, v in (btc_days or {}).items():
        crypto.loc[d:, "BTC-USD"] = v
    p["BTC-USD"] = crypto["BTC-USD"].reindex(CAL)
    return make_market(p, traded=p.notna(), crypto_daily=crypto)

ROWS = [("t1", "2023-09-05", "2023-09-05", "tarifs"), ("w1", "2023-10-09", "2023-10-08", "guerre;energie"),
        ("t2", "2023-09-12", "2023-09-11", "tarifs"), ("c1", "2023-12-20", "2023-12-20", "puces"),
        ("r1", "2024-01-15", "2024-01-15", "taux")]

# --- the plan's tests (verbatim) ---------------------------------------------------------------
def test_family_from_category_time_rule_and_no_future_rows(tmp_path):
    ev = {e["event_id"]: e for e in load_events("2023-12-29", path=write_events(tmp_path, ROWS), market=market())}
    assert set(ev) == {"t1", "w1", "t2", "c1"}                                  # r1 is after as_of
    assert (ev["t1"]["family"], ev["w1"]["family"], ev["c1"]["family"]) == ("tariffs", "war_oil", "chips")
    assert ev["t1"]["known"] and ev["t1"]["sign"] == "negative" and ev["t1"]["regions"] == ["USA", "CAN"]
    assert ev["c1"]["in_progress"] and not ev["c1"]["known"] and ev["c1"]["window_end"] is None
    assert ev["t1"]["title"] == "Titre t1" and ev["t1"]["window_end"] == "2023-10-03"   # t+20 union days

def test_campaign_episode_and_overlaps(tmp_path):
    ev = load_events("2023-12-29", path=write_events(tmp_path, ROWS), market=market())
    tar = episodes(ev, "tariffs")
    assert [(e["episode"], e["event_ids"]) for e in tar] == [("t1", ["t1", "t2"])]
    assert (tar[0]["start"], tar[0]["end"]) == ("2023-09-04", "2023-10-10")      # first t-1, last t+20
    assert tar[0]["confounded_by"] == ["w1"] and tar[0]["confounded"] is None

def test_by_ticker_t0_and_crypto_baseline(tmp_path):
    m = market(xiu={"2023-10-12": 90.0}, btc_days={"2023-10-07": 110.0, "2023-10-08": 88.0})
    out = event_impact({"XIU.TO": 0.5, "BTC-USD": 0.5}, "w1", as_of="2023-12-29", market=m,
                       events=load_events("2023-12-29", path=write_events(tmp_path, ROWS), market=m))
    assert out["by_ticker"]["XIU.TO"]["t0"] == "2023-10-10"                     # pitfall 6
    assert out["by_ticker"]["BTC-USD"]["trough"] == pytest.approx(-0.20)        # vs the 2023-10-07 row (pitfall 7)
    assert out["by_ticker"]["XIU.TO"]["trough"] == pytest.approx(-0.10)
    assert out["trough"] == pytest.approx(0.5 * -0.10 + 0.5 * -0.20) and out["trough_date"] == "2023-10-12"
    assert max(out["chart"]["dates"]) <= out["window_end"] <= "2023-12-29"

def test_rise_is_clipped_and_unknown_event_is_an_error(tmp_path):
    m = market(nvda={"2023-09-06": 120.0})
    ev = load_events("2023-12-29", path=write_events(tmp_path, ROWS), market=m)
    up = event_impact({"NVDA": 1.0}, "t1", as_of="2023-12-29", market=m, events=ev)
    assert up["trough"] == 0.0 and up["trough_date"] is None and up["ret_20"] == pytest.approx(0.20)
    assert "error" in event_impact({"NVDA": 1.0}, "c1", as_of="2023-12-29", market=m, events=ev)

def test_scrambling_after_as_of_changes_nothing(tmp_path):
    path = write_events(tmp_path, ROWS)
    def run(m):
        out = event_impact({"XIU.TO": 1.0}, "w1", as_of="2023-11-30", market=m,
                           events=load_events("2023-11-30", path=path, market=m))
        return {k: out[k] for k in ("trough", "ret_20", "percentile", "chart")}
    assert run(market(xiu={"2023-10-12": 90.0})) == run(market(xiu={"2023-10-12": 90.0, "2023-12-01": 10.0}))

@pytest.mark.skipif(not Path("data/starter/prices_daily.csv").exists(), reason="starter data not present")
def test_real_look_ahead_2025_01_31():                                          # spec §15
    ev = {e["event_id"]: e for e in load_events("2025-01-31")}
    assert ev["deepseek_2025"]["in_progress"] and not ev["deepseek_2025"]["known"]
    assert all(e["date"] <= "2025-01-31" for e in ev.values())
    assert event_impact({"XIU.TO": 1.0}, "israel_2023", as_of="2025-01-31")["by_ticker"]["XIU.TO"]["t0"] == "2023-10-10"


# --- the data lead's additions: the catalog format, the time rule, episodes ------------------------------------
NEW_COLS = ("event_id,date,announced,title_en,description_en,title_fr,description_fr,category,family,sign,"
            "episode,regions,lat,lon,source_url,verified_on,place")

def write_catalog(tmp_path, rows):          # rows: (id, date, category, family, sign, title_en) in the finance lead's format
    lines = [NEW_COLS] + [f"{i},{d},{d},{t},Words {i},Titre {i},Mots {i},{c},{f},{s},{i},USA,38.9,-77.0,"
                          f"https://x.test,2026-11-14,Washington" for i, d, c, f, s, t in rows]
    (tmp_path / "catalog.csv").write_text("\n".join(lines) + "\n")
    return tmp_path / "catalog.csv"

def test_csv_family_and_sign_win_english_text_wins_unknown_rows_are_dropped(tmp_path):
    rows = [("a", "2023-09-05", "xyz", "chips", "positive", "English a"), ("b", "2023-09-06", "taux", "", "", "English b"),
            ("c", "2023-09-07", "xyz", "", "", "English c"), ("d", "2023-09-08", "taux", "nonsense", "", "English d")]
    ev = {e["event_id"]: e for e in load_events("2023-12-29", path=write_catalog(tmp_path, rows), market=market())}
    assert set(ev) == {"a", "b"}                                        # c: unknown category, d: unknown family
    assert (ev["a"]["family"], ev["a"]["sign"], ev["a"]["title"], ev["a"]["description"]) == ("chips", "positive", "English a", "Words a")
    assert (ev["b"]["family"], ev["b"]["sign"]) == ("rates", "negative")  # family from category, sign defaults

def test_in_progress_storm_keeps_title_and_date_but_loses_every_description(tmp_path):
    ev = {e["event_id"]: e for e in load_events("2023-12-29", path=write_events(tmp_path, ROWS), market=market())}
    assert (ev["c1"]["title"], ev["c1"]["date"]) == ("Titre c1", "2023-12-20")
    assert ev["c1"]["description"] == "" and ev["c1"]["description_fr"] == ""
    assert ev["t1"]["description"] == "Desc" and ev["t1"]["description_fr"] == "Desc"

def test_a_date_the_calendar_has_not_reached_is_in_progress_and_before_the_data_is_empty(tmp_path):
    path = write_events(tmp_path, ROWS)
    ev = {e["event_id"]: e for e in load_events("2023-09-05", path=path, market=market())}
    assert set(ev) == {"t1"} and ev["t1"]["in_progress"] and ev["t1"]["t0"] == "2023-09-05" and ev["t1"]["window_end"] is None
    assert load_events("2023-08-01", path=path, market=market()) == []

def test_episodes_keep_signs_apart_and_leave_out_storms_in_progress(tmp_path):
    rows = [("n1", "2023-09-05", "tarifs"), ("p1", "2023-09-07", "tarifs"), ("n2", "2023-11-01", "tarifs"),
            ("n3", "2023-12-20", "tarifs")]
    path = write_events(tmp_path, [(i, d, d, c) for i, d, c in rows])
    ev = load_events("2023-12-29", path=path, market=market())
    for e in ev:
        if e["event_id"] == "p1":
            e["sign"] = "positive"
    got = [(e["episode"], e["sign"], e["event_ids"]) for e in episodes(ev)]
    assert got == [("n1", "negative", ["n1"]), ("p1", "positive", ["p1"]), ("n2", "negative", ["n2"])]   # n3: in progress
    assert episodes(ev, "rates") == [] and episodes(ev, "tariffs")[0]["confounded_by"] == []

def test_stale_events_cannot_see_past_this_calls_as_of(tmp_path):
    m = market()
    ev = load_events("2023-12-29", path=write_events(tmp_path, ROWS), market=m)      # a later as_of than the call
    ok = event_impact({"NVDA": 1.0}, "t1", as_of="2023-10-05", market=m, events=ev)   # t+20 = 2023-10-03: known
    assert ok["window_end"] == "2023-10-03" and max(ok["chart"]["dates"]) <= "2023-10-05"
    assert "in progress" in event_impact({"NVDA": 1.0}, "t2", as_of="2023-10-05", market=m, events=ev)["error"]   # t+20 = 10-10
    assert "error" in event_impact({"NVDA": 1.0}, "w1", as_of="2023-10-05", market=m, events=ev)                # dated 10-09
    assert "error" in event_impact({"NVDA": 1.0}, "nope", as_of="2023-12-29", market=m, events=ev)


# --- the data lead's additions: the impact numbers ---------------------------------------------------------------
def usd_market(local_pts, fx_pts):
    """NVDA (USD) and XIU.TO (CAD) flat at 100; NVDA's USD price and USD/CAD step on the given dates."""
    local, fx = pd.Series(100.0, index=CAL), pd.Series(1.30, index=CAL)
    for d, v in local_pts.items():
        local.loc[d:] = v
    for d, v in fx_pts.items():
        fx.loc[d:] = v
    cad = pd.DataFrame({"XIU.TO": 100.0, "NVDA": local * fx}, index=CAL)
    return make_market(cad, local=pd.DataFrame({"XIU.TO": 100.0, "NVDA": local}, index=CAL), fx=fx)

def test_fx_effect_is_the_cad_return_minus_the_usd_return_on_usd_lines_only(tmp_path):
    path, w = write_events(tmp_path, ROWS), {"NVDA": 0.5, "XIU.TO": 0.5}
    m = usd_market({}, {"2023-09-20": 1.43})                                         # loonie falls 10 %: USD line gains in CAD
    up = event_impact(w, "t1", as_of="2023-12-29", market=m, events=load_events("2023-12-29", path=path, market=m))
    assert up["trough"] == 0.0 and up["ret_20"] == pytest.approx(0.05) and up["fx_effect"] == pytest.approx(0.05)
    m = usd_market({"2023-09-25": 90.0}, {"2023-09-20": 1.43})                       # USD -10 % on top: CAD -1 %
    down = event_impact(w, "t1", as_of="2023-12-29", market=m, events=load_events("2023-12-29", path=path, market=m))
    assert down["trough_date"] == "2023-09-25" and down["trough"] == pytest.approx(0.5 * (0.99 - 1))
    assert down["fx_effect"] == pytest.approx(0.5 * (-0.01 - -0.10))                  # at the trough date
    assert down["by_ticker"]["NVDA"]["trough"] == pytest.approx(-0.01) and down["by_ticker"]["XIU.TO"]["trough"] == 0.0

def test_percentile_is_the_share_of_milder_21_day_windows(tmp_path):
    m = market(xiu={"2023-10-12": 90.0})
    out = event_impact({"XIU.TO": 1.0}, "w1", as_of="2023-12-29", market=m,
                       events=load_events("2023-12-29", path=write_events(tmp_path, ROWS), market=m))
    v = portfolio_series({"XIU.TO": 1.0}, as_of="2023-12-29", market=m)["values"]
    low = [min(0.0, min(v[b + 1:b + 22]) / v[b] - 1) for b in range(len(v) - 21)]
    assert out["trough"] == pytest.approx(-0.10) and out["percentile"] == pytest.approx(sum(x > -0.10 + 1e-12 for x in low) / len(low))
    assert 0 < out["percentile"] < 1
    flat = event_impact({"NVDA": 1.0}, "t1", as_of="2023-12-29", market=m, events=load_events("2023-12-29", path=write_events(tmp_path, ROWS), market=m))
    assert flat["trough"] == 0.0 and flat["percentile"] == 0.0

def test_overlaps_and_rule_b_flag_on_one_storm(tmp_path):
    m = market(xiu={"2023-10-10": 90.0})                                              # the first TSX price after w1 (10-09)
    ev = load_events("2023-12-29", path=write_events(tmp_path, ROWS), market=m)
    t2 = event_impact({"XIU.TO": 1.0}, "t2", as_of="2023-12-29", market=m, events=ev)     # w1 (10-09) lies in t2's window
    assert t2["overlaps"] == ["w1"] and t2["episode"] == "t1" and t2["sign"] == "negative"
    assert t2["trough_date"] == "2023-10-10" and t2["confounded"] is True                # w1 is dated before the low
    w1 = event_impact({"XIU.TO": 1.0}, "w1", as_of="2023-12-29", market=m, events=ev)
    assert w1["overlaps"] == [] and w1["confounded"] is False and w1["episode"] == "w1"

def test_weights_are_normalized_unknown_tickers_raise_and_a_first_day_storm_is_an_error(tmp_path):
    m = market(xiu={"2023-10-12": 90.0}, btc_days={"2023-10-07": 110.0, "2023-10-08": 88.0})
    ev = load_events("2023-12-29", path=write_events(tmp_path, ROWS), market=m)
    one = event_impact({"XIU.TO": 1, "BTC-USD": 1}, "w1", as_of="2023-12-29", market=m, events=ev)
    half = event_impact({"XIU.TO": 0.5, "BTC-USD": 0.5}, "w1", as_of="2023-12-29", market=m, events=ev)
    assert one == half
    with pytest.raises(ValueError, match="Unknown ticker"):
        event_impact({"NOPE": 1.0}, "w1", as_of="2023-12-29", market=m, events=ev)
    first = write_events(tmp_path, [("f1", "2023-09-01", "2023-09-01", "puces")])
    out = event_impact({"NVDA": 1.0}, "f1", as_of="2023-12-29", market=m, events=load_events("2023-12-29", path=first, market=m))
    assert "no price before" in out["error"]


# --- the data lead's additions: the real files (skipped without data/starter/) -----------------------------------
REAL = pytest.mark.skipif(not Path("data/starter/prices_daily.csv").exists(), reason="starter data not present")
ROBERT = {"XIU.TO": 0.45, "XBB.TO": 0.35, "GLD": 0.10, "ZST.TO": 0.10}

@REAL
def test_real_catalog_all_known_today_and_episodes_match_the_csv_episode_column():
    from tools.data import DATASET_END
    ev = load_events(DATASET_END)
    assert len(ev) == 37 and all(e["known"] and not e["in_progress"] for e in ev)
    held = {i: ep["episode"] for ep in episodes(ev) for i in ep["event_ids"]}
    assert {e["event_id"]: e["episode"] for e in ev} == held                       # the finance lead's column = the campaign rule
    assert {e["event_id"] for e in ev if e["sign"] == "positive"} == {"tariff_pause_2025", "scotus_ieepa_2026", "ceasefire_2026", "peace_deal_2026"}
    early = {e["event_id"] for e in load_events("2025-01-31") if e["family"] == "tariffs"}
    assert early == {"tariff_threat_2024"}                                         # spec 9: one tariff storm known

@REAL
def test_real_robert_tariff_storms_today_and_after_forty_percent_nvidia():
    from tools.data import DATASET_END
    from tools.portfolio import apply_change
    after = apply_change(ROBERT, {"op": "set", "ticker": "NVDA", "weight": 0.4})
    ev = load_events(DATASET_END)
    today = event_impact(ROBERT, "liberation_day_2025", as_of=DATASET_END, events=ev)
    move = event_impact(after, "liberation_day_2025", as_of=DATASET_END, events=ev)
    assert today["trough"] == pytest.approx(-0.0596, abs=5e-4) and move["trough"] == pytest.approx(-0.0899, abs=5e-4)
    assert move["trough_date"] == "2025-04-08" and move["confounded"] is False and move["percentile"] > 0.9
    tariffs = [ep for ep in episodes(ev, "tariffs") if ep["sign"] == "negative"]
    assert len(tariffs) == 8                                                       # the spec's "separate earlier episodes"

@REAL
def test_real_crypto_baseline_is_the_row_dated_the_day_before_the_announcement():
    from tools.data import DATASET_END, load_market
    m = load_market(DATASET_END)
    ev = {e["event_id"]: e for e in load_events(DATASET_END, market=m)}["svb_2023"]   # announced Wed 2023-03-08 18:00
    out = event_impact({"BTC-USD": 1.0}, "svb_2023", as_of=DATASET_END, market=m)
    window = m["prices"]["BTC-USD"].loc[ev["t0"]:ev["window_end"]].min()
    right, same_day = (window / m["crypto_daily"]["BTC-USD"].loc[d] - 1 for d in ("2023-03-07", "2023-03-08"))
    assert ev["t0"] == "2023-03-09" and ev["t_minus_1"] == "2023-03-08" and out["by_ticker"]["BTC-USD"]["t0"] == "2023-03-09"
    assert out["trough"] == pytest.approx(min(0.0, right)) and abs(right - same_day) > 0.005   # the rule matters here

def test_a_rise_that_starts_on_t0_is_a_zero_trough_not_a_positive_one(tmp_path):
    m = market(nvda={"2023-09-05": 120.0})                                            # gaps up on t1's own t0
    up = event_impact({"NVDA": 1.0}, "t1", as_of="2023-12-29", market=m,
                      events=load_events("2023-12-29", path=write_events(tmp_path, ROWS), market=m))
    assert up["trough"] == 0.0 and up["trough_date"] is None and up["by_ticker"]["NVDA"]["trough"] == 0.0
    assert up["ret_20"] == pytest.approx(0.20) and up["percentile"] == 0.0


# === Task 10: turbulence, the shock check value, drawdown attribution ====================================
import math
from tools.events import turbulence, scenario_stress, drawdown_attribution, FAMILIES as FAMILIES_ALL
from tools.metrics import risk_metrics

ROWS2 = [("t1", "2023-09-05", "2023-09-05", "tarifs"), ("p1", "2023-09-07", "2023-09-07", "tarifs"),
         ("wA", "2023-09-25", "2023-09-25", "guerre"), ("t2", "2023-10-16", "2023-10-16", "tarifs"),
         ("t3", "2023-11-20", "2023-11-20", "tarifs"), ("wB", "2023-11-22", "2023-11-22", "guerre")]
XIU = {"2023-09-20": 90.0, "2023-09-27": 100.0, "2023-10-20": 95.0, "2023-10-25": 100.0,
       "2023-11-24": 80.0, "2023-12-01": 100.0}

def storms(tmp_path, drop=()):
    m = market(xiu=XIU)
    ev = [e for e in load_events("2023-12-29", path=write_events(tmp_path, ROWS2), market=m) if e["event_id"] not in drop]
    for e in ev:
        if e["event_id"] == "p1":
            e["sign"] = "positive"
    return m, ev

# --- the plan's tests (verbatim) ---------------------------------------------------------------------
def test_rule_b_and_the_mixed_rule(tmp_path):
    m, ev = storms(tmp_path, drop=("t2",))
    tar = turbulence({"XIU.TO": 1.0}, ["tariffs"], "2023-12-29", market=m, events=ev)["tariffs"]
    by = {e["episode"]: e for e in tar["episodes"]}
    assert by["t1"]["confounded"] is False                     # wA is dated after t1's low (rule B)
    assert by["t3"]["confounded"] is True and by["t3"]["confounded_by"] == ["wB"]
    assert tar["n"] == 1 and tar["worst"] == pytest.approx(-0.20) and tar["mixed"] == ["t3"]
    assert (tar["evidence"], tar["label"]) == ("Indicative", "Indicative (mixed with wB)")
    assert all("p1" not in e["event_ids"] for e in tar["episodes"])            # positive: never a loss range

def test_two_clean_episodes_leave_the_mixed_one_out(tmp_path):
    m, ev = storms(tmp_path)
    s = scenario_stress({"XIU.TO": 1.0}, ["tariffs"], "2023-12-29", market=m, events=ev)
    assert s["value"] == pytest.approx(-0.10) and s["n_episodes"] == 2 and s["worst_event_id"] == "t1"
    assert [e["episode"] for e in s["excluded"]] == ["t3"] and s["label"] == "Indicative"
    t = turbulence({"XIU.TO": 1.0}, None, "2023-12-29", market=m, events=ev)
    assert t["tariffs"]["mean"] == pytest.approx(-0.075)
    assert t["war_oil"]["n"] == 2 and t["war_oil"]["worst"] == pytest.approx(-0.20)
    assert (t["chips"]["n"], t["chips"]["worst"], t["chips"]["evidence"]) == (0, None, "Can't say")

def test_no_precedent_and_early_as_of(tmp_path):
    m, ev = storms(tmp_path)
    assert scenario_stress({"XIU.TO": 1.0}, ["chips"], "2023-12-29", market=m, events=ev)["value"] is None
    early = load_events("2023-09-15", path=write_events(tmp_path, ROWS2), market=m)
    t = turbulence({"XIU.TO": 1.0}, None, "2023-09-15", market=m, events=early)
    assert all(t[f]["n"] == 0 and t[f]["evidence"] == "Can't say" for f in ("tariffs", "war_oil", "chips", "rates"))

def test_drawdown_attribution_days_and_log_loss():
    s = {"dates": pd.date_range("2024-01-01", periods=8).strftime("%Y-%m-%d").tolist(),
         "values": [100, 110, 105, 99, 94.5, 92, 88, 90]}
    ev = [{"event_id": "r1", "family": "rates", "known": True, "t0": "2024-01-04", "window_end": "2024-01-05"}]
    a = drawdown_attribution(s, ev, "2024-01-08")
    assert (a["peak_date"], a["trough_date"]) == ("2024-01-02", "2024-01-07")
    assert a["days_share"]["rates"] == pytest.approx(2 / 5) and a["days_share"]["tariffs"] == 0.0
    assert a["shares"]["rates"] == pytest.approx(math.log(0.9) / math.log(0.8))
    assert drawdown_attribution({"dates": s["dates"][:3], "values": [100, 101, 102]}, ev, "2024-01-03") is None


# --- the review's two missing offline guards (Task 9 review, Minor 1) -----------------------------------
def test_a_co_event_after_the_low_cannot_explain_it_one_on_or_before_it_can(tmp_path):      # rule B, both paths
    path = write_events(tmp_path, [("t1", "2023-09-05", "2023-09-05", "tarifs"), ("w1", "2023-09-26", "2023-09-26", "guerre")])
    for low, expected in (("2023-09-20", False), ("2023-09-26", True), ("2023-09-28", True)):   # the low vs w1 (09-26)
        m = market(xiu={low: 90.0})
        ev = load_events("2023-12-29", path=path, market=m)
        card = event_impact({"XIU.TO": 1.0}, "t1", as_of="2023-12-29", market=m, events=ev)
        assert card["overlaps"] == ["w1"] and card["trough_date"] == low and card["confounded"] is expected
        row = turbulence({"XIU.TO": 1.0}, ["tariffs"], "2023-12-29", market=m, events=ev)["tariffs"]["episodes"][0]
        assert row["confounded"] is expected and row["confounded_by"] == (["w1"] if expected else [])

def test_a_co_event_on_the_first_t0_is_not_after_it_and_a_fall_less_episode_is_never_confounded(tmp_path):
    same_day = write_events(tmp_path, [("t1", "2023-09-05", "2023-09-05", "tarifs"), ("w1", "2023-09-05", "2023-09-05", "guerre")])
    m = market(xiu={"2023-09-20": 90.0})
    row = turbulence({"XIU.TO": 1.0}, ["tariffs"], "2023-12-29", market=m, events=load_events("2023-12-29", path=same_day, market=m))["tariffs"]["episodes"][0]
    assert row["confounded"] is False and row["confounded_by"] == []
    rows = [("t1", "2023-09-05", "2023-09-05", "tarifs"), ("w1", "2023-09-12", "2023-09-12", "guerre")]
    flat = market()                                                                    # no fall at all: nothing to explain
    row = turbulence({"XIU.TO": 1.0}, ["tariffs"], "2023-12-29", market=flat, events=load_events("2023-12-29", path=write_events(tmp_path, rows), market=flat))["tariffs"]["episodes"][0]
    assert row["trough"] == 0.0 and row["trough_date"] is None and row["confounded"] is False

def test_a_list_from_a_later_as_of_gives_the_fresh_list_result_everywhere(tmp_path):
    m, path, w = market(xiu={"2023-09-20": 90.0}), write_events(tmp_path, ROWS), {"XIU.TO": 1.0}
    stale = load_events("2023-12-29", path=path, market=m)                            # built later than the calls
    fresh = load_events("2023-10-05", path=path, market=m)
    card = event_impact(w, "t1", as_of="2023-10-05", market=m, events=stale)
    assert card["overlaps"] == [] and card["episode"] == "t1"                         # t2 (t+20 = 10-10) is still in progress
    assert card == event_impact(w, "t1", as_of="2023-10-05", market=m, events=fresh)
    now, then = (turbulence(w, None, "2023-10-05", market=m, events=ev) for ev in (stale, fresh))
    assert now == then and [r["episode"] for r in now["tariffs"]["episodes"]] == ["t1"]       # t2 and w1 do not exist yet
    assert scenario_stress(w, None, "2023-10-05", market=m, events=stale) == scenario_stress(w, None, "2023-10-05", market=m, events=fresh)


# --- the mixed rule (ledger 14): a mixed episode is scored on its drop before the co-event ------------------
def mixed_family(tmp_path, co_date, xiu):
    """tariffs episode a1 (t0 2023-09-05) with a war storm c1 on `co_date`, XIU steps as given."""
    rows = [("a1", "2023-09-05", "2023-09-05", "tarifs"), ("c1", co_date, co_date, "guerre")]
    m = market(xiu=xiu)
    ev = load_events("2023-12-29", path=write_events(tmp_path, rows), market=m)
    return turbulence({"XIU.TO": 1.0}, ["tariffs"], "2023-12-29", market=m, events=ev)["tariffs"]

FALLS = {"2023-09-08": 95.0, "2023-09-18": 80.0}        # -5 % alone, then c1's -20 % on the same base

def test_five_trading_days_before_the_co_event_count_as_clean_on_that_drop(tmp_path):
    tar = mixed_family(tmp_path, "2023-09-12", FALLS)      # 09-05 .. 09-11 = 5 days before c1's t0
    row = tar["episodes"][0]
    assert (row["scored"], row["scored_days"]) == ("truncated", 5) and row["trough"] == pytest.approx(-0.05)
    assert row["trough_date"] == "2023-09-08" and row["trough_full"] == pytest.approx(-0.20) and row["trough_full_date"] == "2023-09-18"
    assert row["confounded"] is True and row["confounded_by"] == ["c1"] and row["counted"] is True
    assert tar["n"] == 1 and tar["worst"] == pytest.approx(-0.05) and tar["mixed"] == ["a1"]
    assert (tar["evidence"], tar["label"]) == ("Indicative", "Indicative (mixed with c1)")

def test_four_days_are_too_few_so_the_full_mixed_trough_is_added_as_a_mixed_episode(tmp_path):
    tar = mixed_family(tmp_path, "2023-09-11", FALLS)      # 09-05 .. 09-08 = 4 days before c1's t0
    row = tar["episodes"][0]
    assert row["scored"] == "full" and row["scored_days"] == 21 and row["trough"] == pytest.approx(-0.20)
    assert row["trough_full"] == row["trough"] and row["confounded"] is True and row["counted"] is True
    assert tar["n"] == 0 and tar["worst"] == pytest.approx(-0.20) and tar["mixed"] == ["a1"] and tar["label"] == "Indicative (mixed with c1)"

def test_a_truncated_window_with_no_fall_scores_zero_and_keeps_the_full_trough_alongside(tmp_path):
    tar = mixed_family(tmp_path, "2023-09-12", {"2023-09-18": 80.0})
    row = tar["episodes"][0]
    assert row["scored"] == "truncated" and row["trough"] == 0.0 and row["trough_date"] is None
    assert row["trough_full"] == pytest.approx(-0.20) and tar["n"] == 1 and tar["worst"] == 0.0

def test_the_stress_value_counts_a_truncated_mixed_episode_as_clean_and_names_the_co_event(tmp_path):
    rows = [("a1", "2023-09-05", "2023-09-05", "tarifs"), ("c1", "2023-09-12", "2023-09-12", "guerre")]
    m = market(xiu=FALLS)
    s = scenario_stress({"XIU.TO": 1.0}, ["tariffs"], "2023-12-29", market=m, events=load_events("2023-12-29", path=write_events(tmp_path, rows), market=m))
    assert s["value"] == pytest.approx(-0.05) and s["n_episodes"] == 1 and s["worst_event_id"] == "a1"
    assert s["excluded"] == [] and [e["episode"] for e in s["episodes"]] == ["a1"] and s["label"] == "Indicative (mixed with c1)"


# --- red gate 3, the inputs, and the output shapes ---------------------------------------------------------
def test_scrambling_prices_after_as_of_changes_no_shock_check_number(tmp_path):
    path, w = write_events(tmp_path, ROWS2), {"XIU.TO": 1.0}
    def run(m):
        ev = load_events("2023-11-30", path=path, market=m)
        return turbulence(w, None, "2023-11-30", market=m, events=ev), scenario_stress(w, None, "2023-11-30", market=m, events=ev)
    assert run(market(xiu=XIU)) == run(market(xiu={**XIU, "2023-12-01": 10.0, "2023-12-15": 500.0}))
    t, s = run(market(xiu=XIU))
    assert [r["episode"] for r in t["tariffs"]["episodes"]] == ["t1", "t2"] and s["as_of"] == "2023-11-30"       # t3, wB: in progress

def test_unknown_tickers_and_families_are_programming_errors(tmp_path):
    m, ev = storms(tmp_path)
    with pytest.raises(ValueError, match="Unknown ticker"):
        turbulence({"NOPE": 1.0}, None, "2023-12-29", market=m, events=ev)
    with pytest.raises(ValueError, match="Unknown family"):
        scenario_stress({"XIU.TO": 1.0}, ["tariffs", "weather"], "2023-12-29", market=m, events=ev)
    assert set(turbulence({"XIU.TO": 1.0}, [], "2023-12-29", market=m, events=ev)) == {"tariffs", "war_oil", "chips", "rates", "source", "as_of"}
    assert set(turbulence({"XIU.TO": 1.0}, ["rates", "rates"], "2023-12-29", market=m, events=ev)) == {"rates", "source", "as_of"}

def test_weights_are_normalized_and_every_output_is_plain_json(tmp_path):
    import json
    m, ev = storms(tmp_path)
    one, half = (turbulence(w, None, "2023-12-29", market=m, events=ev) for w in ({"XIU.TO": 1, "NVDA": 1}, {"XIU.TO": 0.5, "NVDA": 0.5}))
    assert one == half
    s = {"dates": CAL.strftime("%Y-%m-%d").tolist(), "values": list(np.linspace(100, 90, len(CAL)))}
    for out in (one, scenario_stress({"XIU.TO": 1.0}, ["tariffs"], "2023-12-29", market=m, events=ev), drawdown_attribution(s, ev, "2023-12-29")):
        assert json.loads(json.dumps(out, allow_nan=False)) == out

def test_a_family_asked_with_a_family_that_has_no_precedent_is_the_weakest_evidence(tmp_path):
    m, ev = storms(tmp_path)
    both = scenario_stress({"XIU.TO": 1.0}, ["tariffs", "chips"], "2023-12-29", market=m, events=ev)
    assert both["value"] == pytest.approx(-0.10) and both["n_episodes"] == 2 and both["label"] == "Can't say"
    pair = scenario_stress({"XIU.TO": 1.0}, ["tariffs", "war_oil"], "2023-12-29", market=m, events=ev)
    assert pair["value"] == pytest.approx(-0.20) and pair["worst_event_id"] == "wB" and pair["n_episodes"] == 4 and pair["label"] == "Indicative"


# --- drawdown attribution: the cut at as_of, the storms it may use ---------------------------------------------
ATT_DATES = pd.date_range("2024-01-01", periods=9).strftime("%Y-%m-%d").tolist()
ATT_VALUES = [100, 110, 105, 99, 94.5, 92, 88, 90, 50]          # the crash on 01-09 lies after as_of

def test_attribution_ignores_the_series_and_the_storms_after_as_of():
    ev = [{"event_id": "r1", "family": "rates", "known": True, "t0": "2024-01-04", "window_end": "2024-01-05"},
          {"event_id": "p1", "family": "rates", "known": True, "sign": "positive", "t0": "2024-01-06", "window_end": "2024-01-06"},
          {"event_id": "c1", "family": "chips", "known": True, "t0": "2024-01-06", "window_end": "2024-01-09"},   # ends after as_of
          {"event_id": "w1", "family": "war_oil", "known": False, "t0": "2024-01-03", "window_end": "2024-01-04"},  # in progress
          {"event_id": "x1", "family": "nonsense", "known": True, "t0": "2024-01-03", "window_end": "2024-01-04"}]
    a = drawdown_attribution({"dates": ATT_DATES, "values": ATT_VALUES}, ev, "2024-01-08")
    assert (a["peak_date"], a["trough_date"], a["as_of"]) == ("2024-01-02", "2024-01-07", "2024-01-08")
    assert a["days_share"] == pytest.approx({"tariffs": 0.0, "war_oil": 0.0, "chips": 0.0, "rates": 3 / 5})   # both signs count
    assert a["shares"]["rates"] == pytest.approx((math.log(94.5 / 105) + math.log(92 / 94.5)) / math.log(0.8))
    assert a["shares"]["chips"] == 0.0 and math.copysign(1.0, a["shares"]["tariffs"]) == 1.0                # never -0.0
    calm = {"dates": ATT_DATES, "values": ATT_VALUES[:-1] + [500]}                                           # the future scrambled
    assert drawdown_attribution(calm, ev, "2024-01-08") == a

def test_attribution_uses_given_metrics_only_when_they_fit_the_cut_series():
    s, ev = {"dates": ATT_DATES, "values": ATT_VALUES}, []
    full = risk_metrics({"dates": ATT_DATES, "values": ATT_VALUES})                  # its trough is 01-09, after as_of
    assert full["trough_date"] == "2024-01-09"
    assert drawdown_attribution(s, ev, "2024-01-08", metrics=full)["trough_date"] == "2024-01-07"
    fit = risk_metrics({"dates": ATT_DATES[:8], "values": ATT_VALUES[:8]})
    assert drawdown_attribution(s, ev, "2024-01-08", metrics=fit) == drawdown_attribution(s, ev, "2024-01-08")
    assert drawdown_attribution(s, ev, "2023-12-01") is None                         # nothing on or before as_of


# --- the real files (skipped without data/starter/): the numbers the first view quotes -----------------------
@REAL
def test_real_robert_tariff_shock_check_today_and_after_forty_percent_nvidia():
    from tools.data import DATASET_END, load_market
    from tools.portfolio import apply_change
    m = load_market(DATASET_END)
    ev = load_events(DATASET_END, market=m)
    after = apply_change(ROBERT, {"op": "set", "ticker": "NVDA", "weight": 0.4})
    now, move = (turbulence(w, ["tariffs"], DATASET_END, market=m, events=ev)["tariffs"] for w in (ROBERT, after))
    assert len(now["episodes"]) == 8 and sum(not r["confounded"] for r in now["episodes"]) == 5      # 8 loss episodes, 5 strictly clean
    assert [r["episode"] for r in now["episodes"] if r["confounded"]] == ["tariff_threat_2024", "cusma_2026", "canada_50_2026"]
    assert now["n"] == move["n"] == 6 and now["mixed"] == move["mixed"] == ["canada_50_2026"]        # + 1 mixed one, clean for its first 12 days
    assert (move["evidence"], move["label"]) == ("Indicative", "Indicative (mixed with saudi_pipeline_2026)")
    assert now["worst"] == pytest.approx(-0.0596, abs=5e-4) and move["worst"] == pytest.approx(-0.0899, abs=5e-4)
    worst = {r["episode"]: r for r in move["episodes"]}["liberation_day_2025"]
    assert worst["trough_date"] == "2025-04-08" and worst["confounded"] is False and worst["event_ids"] == ["liberation_day_2025"]
    s = scenario_stress(after, ["tariffs"], DATASET_END, market=m, events=ev)
    assert s["worst_event_id"] == "liberation_day_2025" and s["n_episodes"] == 6
    assert [e["episode"] for e in s["excluded"]] == ["tariff_threat_2024", "cusma_2026"]

@REAL
def test_real_early_as_of_has_no_clean_tariff_episode_so_the_count_is_below_two():
    from tools.data import load_market
    m = load_market("2025-01-31")
    s = scenario_stress(ROBERT, ["tariffs"], "2025-01-31", market=m, events=load_events("2025-01-31", market=m))
    assert s["n_episodes"] == 0 and s["worst_event_id"] == "tariff_threat_2024"                       # the one known storm is mixed (hbm_2024)
    assert s["label"] == "Indicative (mixed with hbm_2024)" and s["value"] == pytest.approx(-0.0137, abs=5e-4)

@REAL
def test_real_a_one_storm_episode_shows_exactly_the_storm_cards_trough_and_jackson_hole_is_scored_before_chips_2022():
    from tools.data import DATASET_END, load_market
    from tools.portfolio import apply_change
    m = load_market(DATASET_END)
    ev = load_events(DATASET_END, market=m)
    after = apply_change(ROBERT, {"op": "set", "ticker": "NVDA", "weight": 0.4})
    t = turbulence(after, None, DATASET_END, market=m, events=ev)
    singles = [r for f in FAMILIES_ALL for r in t[f]["episodes"] if len(r["event_ids"]) == 1 and r["scored"] == "full"]
    assert len(singles) >= 15
    for r in singles:
        assert r["trough"] == pytest.approx(event_impact(after, r["event_ids"][0], as_of=DATASET_END, market=m, events=ev)["trough"], abs=1e-12)
    jh = {r["episode"]: r for r in t["rates"]["episodes"]}["jackson_hole_2022"]                       # ledger 14: -13.6 % for Robert after
    assert jh["scored"] == "truncated" and jh["confounded_by"] == ["chips_2022"] and jh["trough"] == pytest.approx(-0.136, abs=5e-4)
    assert jh["trough_full"] < jh["trough"] and jh["trough_full"] == pytest.approx(-0.155, abs=5e-4)
    assert t["rates"]["worst"] == pytest.approx(jh["trough"]) and t["rates"]["label"] == "Indicative (mixed with chips_2022)"

@REAL
def test_real_attribution_quotes_the_committed_catalog_for_the_2022_fall():
    from tools.data import DATASET_END, load_market
    from tools.portfolio import apply_change, portfolio_series
    m = load_market(DATASET_END)
    after = apply_change(ROBERT, {"op": "set", "ticker": "NVDA", "weight": 0.4})
    a = drawdown_attribution(portfolio_series(after, as_of=DATASET_END, market=m), load_events(DATASET_END, market=m), DATASET_END)
    assert (a["peak_date"], a["trough_date"]) == ("2021-11-29", "2022-10-14")
    assert a["days_share"]["rates"] == pytest.approx(0.323, abs=5e-4) and a["shares"]["rates"] == pytest.approx(0.249, abs=5e-4)
    assert a["days_share"]["tariffs"] == 0.0 and a["shares"]["tariffs"] == 0.0           # no tariff storm in the 2022 fall


# --- the evidence levels (spec 10): Measured needs 3 clean episodes and no mixed one -----------------------------
def long_market(xiu):
    cal = pd.bdate_range("2023-01-02", "2023-12-29")
    p = pd.DataFrame({"XIU.TO": 100.0, "NVDA": 100.0}, index=cal)
    for d, v in xiu.items():
        p.loc[d:, "XIU.TO"] = v
    crypto = pd.DataFrame({"BTC-USD": 100.0}, index=pd.date_range("2023-01-01", "2023-12-31"))
    p["BTC-USD"] = crypto["BTC-USD"].reindex(cal)
    return make_market(p, traded=p.notna(), crypto_daily=crypto)

FOUR = [("e1", "2023-02-01", "2023-02-01", "tarifs"), ("e2", "2023-03-15", "2023-03-15", "tarifs"),
        ("e3", "2023-05-01", "2023-05-01", "tarifs"), ("e4", "2023-07-03", "2023-07-03", "tarifs")]
STEPS = {"2023-02-06": 97.0, "2023-03-20": 90.0, "2023-05-04": 85.0, "2023-07-05": 80.0, "2023-07-14": 70.0}

def four_episodes(tmp_path, keep, co=None):
    rows = [r for r in FOUR if r[0] in keep] + ([("c4", co, co, "guerre")] if co else [])
    m = long_market(STEPS)
    return turbulence({"XIU.TO": 1.0}, ["tariffs"], "2023-12-29", market=m, events=load_events("2023-12-29", path=write_events(tmp_path, rows), market=m))["tariffs"]

def test_measured_needs_three_clean_episodes_two_are_indicative(tmp_path):
    three = four_episodes(tmp_path, ("e1", "e2", "e3"))
    assert (three["n"], three["evidence"], three["label"], three["mixed"]) == (3, "Measured", "Measured", [])
    assert three["worst"] == pytest.approx(90 / 97 - 1) and three["mean"] == pytest.approx(np.mean([-0.03, 90 / 97 - 1, 85 / 90 - 1]))
    two = four_episodes(tmp_path, ("e1", "e2"))
    assert (two["n"], two["evidence"], two["label"]) == (2, "Indicative", "Indicative")
    assert four_episodes(tmp_path, ())["evidence"] == "Can't say"

def test_a_mixed_episode_in_the_count_keeps_the_family_at_indicative_naming_the_co_event(tmp_path):
    tar = four_episodes(tmp_path, ("e1", "e2", "e3", "e4"), co="2023-07-12")        # e4: 7 days alone before c4, then -12.5 % more
    row = {r["episode"]: r for r in tar["episodes"]}["e4"]
    assert (row["scored"], row["scored_days"], row["confounded_by"]) == ("truncated", 7, ["c4"])
    assert row["trough"] == pytest.approx(80 / 85 - 1) and row["trough_full"] == pytest.approx(70 / 85 - 1)
    assert tar["n"] == 4 and tar["mixed"] == ["e4"] and (tar["evidence"], tar["label"]) == ("Indicative", "Indicative (mixed with c4)")
    assert tar["worst"] == pytest.approx(90 / 97 - 1)                                  # the mixed episode did not set the worst
    clean = four_episodes(tmp_path, ("e1", "e2", "e3", "e4"))
    assert (clean["n"], clean["evidence"], clean["mixed"]) == (4, "Measured", [])

def test_a_co_event_on_the_same_day_is_not_after_the_first_t0_on_the_storm_card_either(tmp_path):
    path = write_events(tmp_path, [("t1", "2023-09-05", "2023-09-05", "tarifs"), ("w1", "2023-09-05", "2023-09-05", "guerre")])
    m = market(xiu={"2023-09-20": 90.0})
    card = event_impact({"XIU.TO": 1.0}, "t1", as_of="2023-12-29", market=m, events=load_events("2023-12-29", path=path, market=m))
    assert card["overlaps"] == ["w1"] and card["confounded"] is False

def test_the_windows_come_from_this_calls_calendar_not_from_the_list(tmp_path):
    m, ev = storms(tmp_path)
    bent = [{**e, "t_minus_1": "2023-09-05", "t0": "2023-09-06", "window_end": "2023-10-07"} if e["event_id"] == "t1" else e for e in ev]
    w = {"XIU.TO": 1.0}                                                               # 10-07 is a Saturday: no such trading day
    assert turbulence(w, None, "2023-12-29", market=m, events=bent) == turbulence(w, None, "2023-12-29", market=m, events=ev)
    long = [{**e, "window_end": "2023-12-01"} if e["event_id"] == "t1" else e for e in ev]      # a window that would swallow t2 and t3
    card = event_impact(w, "t2", as_of="2023-12-29", market=m, events=long)
    assert card["episode"] == "t2" and card == event_impact(w, "t2", as_of="2023-12-29", market=m, events=ev)

def test_a_one_storm_episode_shows_the_storm_cards_trough_with_per_asset_t0_and_the_crypto_baseline(tmp_path):
    m = market(xiu={"2023-10-12": 90.0}, btc_days={"2023-10-07": 110.0, "2023-10-08": 88.0})
    ev, w = load_events("2023-12-29", path=write_events(tmp_path, ROWS), market=m), {"XIU.TO": 0.5, "BTC-USD": 0.5}
    row = turbulence(w, ["war_oil"], "2023-12-29", market=m, events=ev)["war_oil"]["episodes"][0]
    card = event_impact(w, "w1", as_of="2023-12-29", market=m, events=ev)
    assert row["episode"] == "w1" and row["trough"] == card["trough"] == pytest.approx(-0.15)
    assert row["trough_date"] == card["trough_date"] == "2023-10-12"

def test_a_storm_a_held_line_has_no_price_before_is_skipped_and_named_not_guessed(tmp_path):
    m = market()
    first = write_events(tmp_path, [("f1", "2023-09-01", "2023-09-01", "puces")])               # the first day of the data
    chips = turbulence({"NVDA": 1.0}, ["chips"], "2023-12-29", market=m, events=load_events("2023-12-29", path=first, market=m))["chips"]
    assert chips["skipped"] == ["f1"] and chips["episodes"] == [] and (chips["n"], chips["worst"], chips["evidence"]) == (0, None, "Can't say")
