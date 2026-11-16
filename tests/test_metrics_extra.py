"""Tasks 4 and 5 tests: tools/metrics.py (spec section 10: risk metrics, calendar-day CAGR and
recovery; the drawdown series, the policy-rate regime and the trailing dividend yield).

the data lead's tests pin the section 10 definitions; the finance lead's tests/test_metrics.py carries the finance
truth (run it too when it lands). Offline: synthetic series. The real-data cases skip when
data/starter/ is absent.
"""
import json
import math
import time

import numpy as np
import pandas as pd
import pytest


def _quiet_machine_only():
    """The performance budgets are measured on a quiet machine (approved, Sun 17:35): skip them when the load is high."""
    import os
    if os.getloadavg()[0] > 6:
        pytest.skip("machine busy (load > 6): the performance budget is measured on a quiet machine")

from tools.data import DATA_DIR, DATASET_END, load_market, make_market
from tools.events import event_impact, load_events, scenario_stress, turbulence
from tools.lookthrough import look_through
from tools.metrics import (asset_facts, calendar_year_returns, drawdown_series, rate_regime, risk_metrics,
                           trailing_yield, worst_rolling_drop)
from tools.portfolio import apply_change, portfolio_series, series_from_market
from tools.risk import diversification, risk_contributions

ROBERT = {"XIU.TO": 0.45, "XBB.TO": 0.35, "GLD": 0.10, "ZST.TO": 0.10}
REAL = pytest.mark.skipif(not (DATA_DIR / "prices_daily.csv").exists(),
                          reason="data/starter/ is absent")


def ser(values, start="2024-01-01", freq="D"):
    return {"dates": pd.date_range(start, periods=len(values), freq=freq).strftime("%Y-%m-%d").tolist(), "values": values}


# --- the plan's seven tests (verbatim) -----------------------------------------------------------
def test_drop_20_then_recover():
    m = risk_metrics(ser([100, 90, 80, 90, 100, 110]))
    assert m["max_drawdown"] == pytest.approx(-0.20)
    assert (m["peak_date"], m["trough_date"]) == ("2024-01-01", "2024-01-03")
    assert m["recovery_days"] == 2 and m["days_since_trough"] == 3      # calendar days


def test_not_recovered_is_none():
    m = risk_metrics(ser([100, 80, 90]))
    assert m["recovery_days"] is None and m["days_since_trough"] == 1


def test_cagr_uses_calendar_days_over_365_25():
    m = risk_metrics({"dates": ["2022-01-01", "2024-01-01"], "values": [100, 121]})
    assert m["cagr"] == pytest.approx(1.21 ** (365.25 / 730) - 1)


def test_volatility_and_sharpe():
    s = ser([100, 101, 100, 101, 100])
    r = pd.Series(s["values"]).pct_change().dropna()
    m = risk_metrics(s, rf=0.03)
    assert m["volatility"] == pytest.approx(r.std(ddof=1) * 252 ** 0.5)
    assert m["sharpe"] == pytest.approx((m["cagr"] - 0.03) / m["volatility"])


def test_flat_and_one_point_series_do_not_divide_by_zero():
    flat = risk_metrics(ser([100, 100, 100]))
    assert flat["max_drawdown"] == 0.0 and flat["peak_date"] is None and flat["sharpe"] is None
    one = risk_metrics(ser([100]))
    assert one["cagr"] is None and one["volatility"] is None and one["max_drawdown"] == 0.0


def test_worst_rolling_drop_ignores_older_peaks():
    s = ser([200] + [100] * 400 + [90], freq="D")       # the 200 peak is > 365 days before the end
    w = worst_rolling_drop(s)
    assert w["value"] == pytest.approx(-0.50)            # 200 -> 100 inside the first year
    assert worst_rolling_drop(ser([100] * 400 + [90]))["value"] == pytest.approx(-0.10)


def test_calendar_year_returns():
    s = {"dates": ["2022-01-03", "2022-12-30", "2023-12-29"], "values": [100, 110, 99]}
    assert calendar_year_returns(s) == pytest.approx({2022: 0.10, 2023: -0.10})


# --- risk_metrics: the contract, the dates, the decisions the plan leaves open -------------------
KEYS = {"cagr", "volatility", "max_drawdown", "peak_date", "trough_date", "recovery_days",
        "days_since_trough", "sharpe", "source", "as_of"}


def test_contract_keys_types_and_as_of_is_the_last_date():
    s = ser([100, 90, 80, 90, 100, 110])
    s["source"] = "SERIES-SOURCE"
    m = risk_metrics(s)
    assert set(m) == KEYS and m["as_of"] == "2024-01-06"
    assert isinstance(m["source"], str) and "SERIES-SOURCE" in m["source"]
    assert type(m["recovery_days"]) is int and type(m["days_since_trough"]) is int
    assert all(type(m[k]) is float for k in ("cagr", "volatility", "max_drawdown", "sharpe"))
    assert all(type(m[k]) is str for k in ("peak_date", "trough_date", "as_of"))
    assert risk_metrics(ser([100, 90]))["source"]                 # no series source: still cites the method


def test_peak_is_the_first_date_of_the_running_high_and_ties_keep_the_first_trough():
    m = risk_metrics(ser([100, 100, 80, 90, 80]))
    assert (m["peak_date"], m["trough_date"]) == ("2024-01-01", "2024-01-03")
    assert m["recovery_days"] is None and m["days_since_trough"] == 2


def test_only_the_deepest_drawdown_counts_and_reaching_the_peak_again_is_recovery():
    m = risk_metrics(ser([100, 50, 100, 120, 100]))                # -50 %, then a new high, then -16.7 %
    assert m["max_drawdown"] == pytest.approx(-0.5)
    assert (m["peak_date"], m["trough_date"]) == ("2024-01-01", "2024-01-02")
    assert m["recovery_days"] == 1                                 # value 100 >= peak 100 (equal counts)
    assert m["days_since_trough"] == 3


def test_recovery_and_days_since_trough_are_calendar_days_across_weekends():
    s = ser([100, 80, 90, 100], start="2024-01-03", freq="B")      # Wed, Thu, Fri, Mon
    assert s["dates"] == ["2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]
    m = risk_metrics(s)
    assert m["recovery_days"] == 4 and m["days_since_trough"] == 4


def test_no_drawdown_means_no_dates_and_zero_recovery():
    m = risk_metrics(ser([100, 101, 103, 103, 110]))
    assert m["max_drawdown"] == 0.0 and m["peak_date"] is None and m["trough_date"] is None
    assert m["recovery_days"] == 0 and m["days_since_trough"] is None
    assert m["cagr"] > 0 and m["volatility"] > 0 and m["sharpe"] is not None


def test_constant_growth_is_zero_volatility_not_a_huge_sharpe():
    s = ser([100 * 1.01 ** k for k in range(30)])                 # identical returns up to float noise
    m = risk_metrics(s, rf=0.0)
    assert m["volatility"] < 1e-9 and m["sharpe"] is None and m["cagr"] > 0


def test_two_points_have_a_cagr_but_no_volatility_or_sharpe():
    m = risk_metrics(ser([100, 110]))
    assert m["cagr"] == pytest.approx(1.1 ** 365.25 - 1) and m["volatility"] is None and m["sharpe"] is None


def test_empty_series_is_all_none_not_an_error():
    m = risk_metrics({"dates": [], "values": []})
    assert m["cagr"] is None and m["volatility"] is None and m["sharpe"] is None
    assert m["max_drawdown"] == 0.0 and m["peak_date"] is None and m["as_of"] is None
    assert m["recovery_days"] == 0 and m["days_since_trough"] is None


def test_a_malformed_series_is_a_programming_error():
    for bad in ({"dates": ["2024-01-01"], "values": [100, 101]},                    # lengths differ
                {"dates": ["2024-01-02", "2024-01-01"], "values": [100, 101]},      # not increasing
                {"dates": ["2024-01-01", "2024-01-02"], "values": [100, float("nan")]},
                {"dates": ["2024-01-01", "2024-01-02"], "values": [100, 0]}):
        with pytest.raises(ValueError):
            risk_metrics(bad)


def test_a_negative_rf_and_a_loss_give_a_negative_sharpe_and_rf_is_a_fraction():
    s = ser([100, 99, 98, 99, 97])
    m0, m3 = risk_metrics(s), risk_metrics(s, rf=0.03)
    assert m0["sharpe"] < 0 and m3["sharpe"] == pytest.approx(m0["sharpe"] - 0.03 / m0["volatility"])


# --- worst_rolling_drop --------------------------------------------------------------------------
def test_worst_rolling_drop_dates_and_the_window_edge_is_inclusive():
    s = ser([200] + [100] * 400 + [90])
    w = worst_rolling_drop(s)
    assert set(w) == {"value", "peak_date", "trough_date"}
    assert (w["peak_date"], w["trough_date"]) == ("2024-01-01", "2024-01-02")
    # a peak exactly 365 calendar days before the trough still counts; 366 days no longer does
    edge = ser([200] + [150] * 364 + [100])                      # trough on day 365
    assert worst_rolling_drop(edge)["value"] == pytest.approx(-0.5)
    assert worst_rolling_drop(edge)["trough_date"] == "2024-12-31"
    late = ser([200] + [150] * 365 + [100])                      # trough on day 366: only 150 -> 100
    assert worst_rolling_drop(late)["value"] == pytest.approx(-1 / 3)    # not -0.5: the 200 is 366 days back


def test_worst_rolling_drop_window_days_and_no_drop():
    s = ser([100, 90, 90, 90, 90, 90, 63])
    assert worst_rolling_drop(s, window_days=2)["value"] == pytest.approx(-0.30)     # 90 -> 63
    assert worst_rolling_drop(s, window_days=10)["value"] == pytest.approx(-0.37)    # 100 -> 63
    none = worst_rolling_drop(ser([100, 101, 102]))
    assert none == {"value": 0.0, "peak_date": None, "trough_date": None}
    assert worst_rolling_drop({"dates": [], "values": []})["value"] == 0.0


def test_a_window_longer_than_the_series_is_the_max_drawdown():
    s = ser([100, 120, 90, 95, 130, 70, 80], start="2023-03-01", freq="W")
    m, w = risk_metrics(s), worst_rolling_drop(s, window_days=10_000)
    assert w["value"] == pytest.approx(m["max_drawdown"])
    assert (w["peak_date"], w["trough_date"]) == (m["peak_date"], m["trough_date"])


# --- calendar_year_returns -----------------------------------------------------------------------
def test_calendar_year_returns_partial_first_year_and_partial_last_year():
    s = {"dates": ["2021-11-12", "2021-12-31", "2022-06-30", "2022-12-30", "2023-03-31"],
         "values": [100, 105, 90, 84, 92.4]}
    out = calendar_year_returns(s)
    assert list(out) == [2021, 2022, 2023] and all(type(y) is int for y in out)
    assert out == pytest.approx({2021: 0.05, 2022: 84 / 105 - 1, 2023: 92.4 / 84 - 1})


def test_calendar_year_returns_say_nothing_when_the_data_cannot_support_a_year():
    one = {"dates": ["2021-12-31", "2022-12-30"], "values": [100, 110]}
    assert calendar_year_returns(one) == pytest.approx({2022: 0.10})       # 2021 has a single point: no return
    assert calendar_year_returns({"dates": ["2024-05-01"], "values": [100]}) == {}
    assert calendar_year_returns({"dates": [], "values": []}) == {}
    gap = {"dates": ["2020-01-02", "2020-12-31", "2022-06-30"], "values": [100, 110, 120]}
    assert calendar_year_returns(gap) == pytest.approx({2020: 0.10})       # 2021 missing: 2022 is not 2 years in one


# --- brute force agreement (seeded), JSON safety -------------------------------------------------
def _brute(values, dates):
    """The section 10 definitions as plain loops, written independently of tools/metrics.py."""
    best, peak_i, trough_i = 0.0, None, None
    for t in range(len(values)):
        hi = max(range(t + 1), key=lambda k: (values[k], -k))        # first index of the running high
        dd = values[t] / values[hi] - 1
        if dd < best:
            best, peak_i, trough_i = dd, hi, t
    if trough_i is None:
        return best, None, None, 0, None
    rec = next((j for j in range(trough_i + 1, len(values)) if values[j] >= values[peak_i]), None)
    day = lambda i: pd.Timestamp(dates[i])                           # noqa: E731
    return (best, dates[peak_i], dates[trough_i], None if rec is None else (day(rec) - day(trough_i)).days,
            (day(len(values) - 1) - day(trough_i)).days)


def test_drawdown_matches_a_brute_force_loop_on_random_walks():
    rng = np.random.default_rng(11)
    for _ in range(60):
        n = int(rng.integers(2, 40))
        values = (100 * np.cumprod(1 + rng.normal(0, 0.03, n))).round(4).tolist()
        s = {"dates": pd.bdate_range("2024-01-01", periods=n).strftime("%Y-%m-%d").tolist(), "values": values}
        dd, peak, trough, rec, since = _brute(values, s["dates"])
        m = risk_metrics(s)
        assert m["max_drawdown"] == pytest.approx(dd, abs=1e-12)
        assert (m["peak_date"], m["trough_date"]) == (peak, trough)
        if trough is None:
            assert m["recovery_days"] == 0 and m["days_since_trough"] is None
        else:
            assert (m["recovery_days"], m["days_since_trough"]) == (rec, since)


def test_the_result_is_json_safe_for_numpy_inputs():
    import json
    s = {"dates": pd.date_range("2024-01-01", periods=5), "values": np.array([100, 90, 80, 90, 100])}
    text = json.dumps(risk_metrics({"dates": [d.strftime("%Y-%m-%d") for d in s["dates"]], "values": s["values"]}))
    assert "NaN" not in text and "Infinity" not in text
    json.dumps(worst_rolling_drop({"dates": [d.strftime("%Y-%m-%d") for d in s["dates"]], "values": s["values"]}))
    json.dumps(calendar_year_returns({"dates": ["2023-12-29", "2024-12-31"], "values": np.array([100, 110])}))


def test_calendar_years_compound_to_the_whole_period_return():
    rng = np.random.default_rng(5)
    days = pd.bdate_range("2021-11-12", "2024-05-31")
    values = (100 * np.cumprod(1 + rng.normal(0, 0.01, len(days)))).tolist()
    s = {"dates": days.strftime("%Y-%m-%d").tolist(), "values": values}
    out = calendar_year_returns(s)
    assert list(out) == [2021, 2022, 2023, 2024]
    assert np.prod([1 + r for r in out.values()]) == pytest.approx(values[-1] / values[0])


# --- real data (skipped when data/starter/ is absent): the independent red team's numbers --------
@REAL
def test_real_robert_today_and_after_reproduce_the_red_team_numbers():
    from tools.portfolio import apply_change, portfolio_series
    after_w = apply_change(ROBERT, {"op": "set", "ticker": "NVDA", "weight": 0.40})
    today, after = (risk_metrics(portfolio_series(w, as_of=DATASET_END)) for w in (ROBERT, after_w))
    assert round(today["max_drawdown"] * 100, 2) == -10.61 and round(today["cagr"] * 100, 2) == 8.73
    assert round(after["max_drawdown"] * 100, 2) == -34.52 and round(after["cagr"] * 100, 2) == 25.22
    assert (today["peak_date"], today["trough_date"]) == ("2022-03-04", "2022-10-11")
    assert (after["peak_date"], after["trough_date"]) == ("2021-11-29", "2022-10-14")
    assert (today["recovery_days"], after["recovery_days"]) == (416, 187)        # trough -> previous peak
    assert (today["days_since_trough"], after["days_since_trough"]) == (1493, 1490)
    assert round(600_000 * after["max_drawdown"]) == -207_146            # ledger 14: dollars = amount x drawdown
    assert today["as_of"] == after["as_of"] == DATASET_END
    # both falls sit inside one year, so the worst rolling 12-month drop is the same fall
    for m, w in ((today, ROBERT), (after, after_w)):
        wr = worst_rolling_drop(portfolio_series(w, as_of=DATASET_END))
        assert wr["value"] == pytest.approx(m["max_drawdown"])
        assert (wr["peak_date"], wr["trough_date"]) == (m["peak_date"], m["trough_date"])


# --- a few weeks into the data (plan A review focus 3): nothing divides by zero -------------------
def test_a_few_weeks_into_the_data_gives_finite_numbers_or_none():
    from tools.portfolio import portfolio_series
    fake = "data/fake/starter"
    for as_of in ("2021-11-12", "2021-11-15", "2021-11-17", "2021-12-15"):
        s = portfolio_series({"XIU.TO": 0.5, "NVDA": 0.5}, as_of=as_of, market=load_market(as_of, data_dir=fake))
        assert s["dates"][0] == "2021-11-12" and s["dates"][-1] <= as_of
        for out in (risk_metrics(s), worst_rolling_drop(s)):
            assert all(v is None or isinstance(v, (str, int)) or math.isfinite(v) for v in out.values())
        assert all(math.isfinite(r) for r in calendar_year_returns(s).values())
    one = portfolio_series({"XIU.TO": 1.0}, as_of="2021-11-12", market=load_market("2021-11-12", data_dir=fake))
    assert len(one["dates"]) == 1 and risk_metrics(one)["cagr"] is None and calendar_year_returns(one) == {}


# =================================================================================================
# Task 5: drawdown_series, rate_regime (Bank of Canada hiking spells), trailing_yield (CAD dividends)
# =================================================================================================
def test_drawdown_series():
    d = drawdown_series(ser([100, 120, 90, 120, 60]))
    assert d["dates"] == ser([0] * 5)["dates"]
    assert d["values"] == pytest.approx([0, 0, -0.25, 0, -0.5])


def test_drawdown_series_farhats_case_keys_and_json():
    d = drawdown_series(ser([100, 80, 120, 90]))                            # tests/test_metrics.py (plan C Task 6)
    assert d["values"] == pytest.approx([0.0, -0.2, 0.0, -0.25]) and set(d) == {"dates", "values"}
    assert all(type(v) is float and v <= 0.0 for v in d["values"]) and all(type(x) is str for x in d["dates"])
    json.dumps(drawdown_series({"dates": pd.date_range("2024-01-01", periods=3), "values": np.array([5, 4, 6])}))
    assert drawdown_series({"dates": [], "values": []}) == {"dates": [], "values": []}
    with pytest.raises(ValueError):
        drawdown_series({"dates": ["2024-01-02", "2024-01-01"], "values": [100, 101]})   # same checks as risk_metrics


def test_drawdown_series_agrees_with_risk_metrics_and_does_not_touch_its_input():
    rng = np.random.default_rng(3)
    for _ in range(25):
        n = int(rng.integers(2, 60))
        values = (100 * np.cumprod(1 + rng.normal(0, 0.03, n))).tolist()
        s = {"dates": pd.bdate_range("2024-01-01", periods=n).strftime("%Y-%m-%d").tolist(), "values": list(values)}
        d = drawdown_series(s)
        assert min(d["values"]) == pytest.approx(risk_metrics(s)["max_drawdown"], abs=1e-12)
        assert d["dates"] == s["dates"] and s["values"] == values and len(d["values"]) == n
        assert all(v <= 0.0 for v in d["values"])


# --- rate_regime ---------------------------------------------------------------------------------
def _rf_market():
    idx = pd.bdate_range("2022-01-03", "2024-12-31")
    m = make_market(pd.DataFrame({"XIU.TO": 1.0}, index=idx))
    rf = pd.Series(0.0025, idx)
    for d, v in [("2022-03-03", 0.005), ("2022-06-02", 0.015), ("2022-10-27", 0.0375),
                 ("2023-03-30", 0.045), ("2024-06-06", 0.0425), ("2024-10-01", 0.045)]:
        rf[d:] = v
    m["rf_daily"] = rf
    return m


def _rates(moves, first=0.0, start="2022-01-01", end="2023-03-31"):
    """A bundle on EVERY calendar day whose policy rate (a fraction) steps to each value on its date."""
    idx = pd.date_range(start, end)
    m = make_market(pd.DataFrame({"XIU.TO": 1.0}, index=idx))
    rf = pd.Series(first, idx)
    for d, v in moves:
        rf[d:] = v
    m["rf_daily"] = rf
    return m


def test_rate_regime_bridges_pauses_and_drops_single_hikes():
    r = rate_regime("2024-12-31", market=_rf_market())
    assert r["hiking"] == [{"start": "2022-03-03", "end": "2023-03-30"}]     # 2024-10-01 is a lone hike
    assert r["series"]["dates"] == ["2022-01-03", "2022-03-03", "2022-06-02", "2022-10-27",
                                    "2023-03-30", "2024-06-06", "2024-10-01", "2024-12-31"]
    assert r["series"]["values"][1] == pytest.approx(0.005) and r["as_of"] == "2024-12-31"


def test_rate_regime_sees_nothing_after_as_of():
    r = rate_regime("2022-08-31", market=_rf_market())
    assert r["hiking"] == [{"start": "2022-03-03", "end": "2022-06-02"}]
    assert max(r["series"]["dates"]) <= "2022-08-31"


def test_rate_regime_contract_types_and_source():
    r = rate_regime("2024-12-31", market=_rf_market())
    assert set(r) == {"hiking", "series", "source", "as_of"} and set(r["series"]) == {"dates", "values"}
    assert r["source"] == "Bank of Canada V39079 (macro_rates.csv)"
    assert all(set(h) == {"start", "end"} for h in r["hiking"])
    assert all(type(v) is float for v in r["series"]["values"]) and len(r["series"]["dates"]) == len(r["series"]["values"])
    json.dumps(r)


def test_a_cut_ends_a_spell_and_the_next_hikes_start_another():
    m = _rates([("2022-03-03", 0.005), ("2022-04-14", 0.01), ("2022-05-26", 0.0075),     # up, up, CUT
                ("2022-07-14", 0.01), ("2022-09-08", 0.0125)])                           # up, up
    assert rate_regime("2023-03-31", market=m)["hiking"] == [
        {"start": "2022-03-03", "end": "2022-04-14"}, {"start": "2022-07-14", "end": "2022-09-08"}]


def test_the_pause_limit_is_183_days_between_two_hikes():
    bridged = rate_regime("2023-03-31", market=_rates([("2022-01-06", 0.01), ("2022-07-08", 0.02)]))   # 183 days
    split = rate_regime("2023-03-31", market=_rates([("2022-01-06", 0.01), ("2022-07-09", 0.02)]))     # 184 days
    assert bridged["hiking"] == [{"start": "2022-01-06", "end": "2022-07-08"}]
    assert split["hiking"] == []                                          # two lone hikes are not a cycle


def test_no_move_means_no_spell_and_the_first_row_is_not_a_hike():
    flat = rate_regime("2023-03-31", market=_rates([], first=0.05))
    assert flat["hiking"] == [] and flat["series"] == {"dates": ["2022-01-01", "2023-03-31"], "values": [0.05, 0.05]}
    one = rate_regime("2022-01-01", market=_rates([], first=0.05))        # a single row: its date once, not twice
    assert one["series"] == {"dates": ["2022-01-01"], "values": [0.05]} and one["as_of"] == "2022-01-01"


def test_a_spell_still_running_ends_at_its_last_hike_and_a_lone_hike_is_not_one_yet():
    m = _rates([("2022-03-03", 0.005), ("2022-04-14", 0.01), ("2022-06-02", 0.015)])
    assert rate_regime("2023-03-31", market=m)["hiking"] == [{"start": "2022-03-03", "end": "2022-06-02"}]
    assert rate_regime("2022-03-03", market=m)["hiking"] == []            # one hike so far
    assert rate_regime("2022-04-14", market=m)["hiking"] == [{"start": "2022-03-03", "end": "2022-04-14"}]


def test_rate_regime_before_the_first_rate_and_on_a_weekend():
    empty = rate_regime("2021-12-31", market=_rf_market())               # the first policy-rate row is 2022-01-03
    assert empty["hiking"] == [] and empty["series"] == {"dates": [], "values": []} and empty["as_of"] == "2021-12-31"
    saturday = rate_regime("2022-08-27", market=_rf_market())
    assert saturday["as_of"] == "2022-08-26" and saturday["series"]["dates"][-1] == "2022-08-26"   # last date in the data


def test_rate_regime_on_the_fake_pack_monthly_rows_one_jump_is_not_a_cycle():
    fake = load_market("2026-11-12", data_dir="data/fake/starter")        # monthly rows: 0.25 % then 4 %
    r = rate_regime("2026-11-12", market=fake)
    assert r["hiking"] == [] and r["series"]["values"][0] == 0.0025 and r["series"]["values"][-1] == 0.04
    assert r["as_of"] == r["series"]["dates"][-1] == "2026-11-01"          # the last rate row (monthly in the fake pack)


# --- trailing_yield ------------------------------------------------------------------------------
def _yield_market():
    idx = pd.bdate_range("2024-01-01", "2024-12-31")
    local = pd.DataFrame({"RY.TO": 100.0, "MSFT": 50.0, "GLD": 200.0}, index=idx)
    fx = pd.Series(1.25, idx)
    cad = local.assign(MSFT=62.5, GLD=250.0)
    div = pd.DataFrame({"date": pd.to_datetime(["2024-01-01", "2024-06-03", "2024-08-01"]),
                        "ticker": ["RY.TO", "RY.TO", "MSFT"], "amount": [1.0, 1.0, 0.5]})
    return make_market(cad, local=local, fx=fx, dividends=div)


def test_trailing_yield_cad_window_and_weights():
    w = {"RY.TO": 0.5, "MSFT": 0.3, "GLD": 0.2}
    y = trailing_yield(w, "2024-12-31", market=_yield_market())
    # window (as_of - 365 d, as_of]: RY 2024-01-01 is out; MSFT 0.5 USD x 1.25 / 62.5 CAD
    assert y["by_ticker"] == pytest.approx({"RY.TO": 0.01, "MSFT": 0.01, "GLD": 0.0})
    assert y["value"] == pytest.approx(0.008)


def test_trailing_yield_ignores_dividends_after_as_of():
    y = trailing_yield({"RY.TO": 0.5, "MSFT": 0.5}, "2024-06-30", market=_yield_market())
    assert y["by_ticker"] == pytest.approx({"RY.TO": 0.02, "MSFT": 0.0})     # both RY payouts are inside
    assert y["value"] == pytest.approx(0.01)


def _one_payer(dates, amount=1.0, price=100.0, start="2023-12-01", end="2025-01-31"):
    idx = pd.bdate_range(start, end)
    div = pd.DataFrame({"date": pd.to_datetime(dates), "ticker": "RY.TO", "amount": amount})
    return make_market(pd.DataFrame({"RY.TO": price}, index=idx), dividends=div)


def test_trailing_yield_window_edges_are_365_days_exclusive_and_as_of_inclusive():
    # as_of 2024-12-31: 2024-01-01 is exactly 365 days back (out), 2024-01-02 is 364 (in), as_of itself is in
    m = _one_payer(["2023-12-29", "2024-01-01", "2024-01-02", "2024-12-31", "2025-01-02"])
    y = trailing_yield({"RY.TO": 1.0}, "2024-12-31", market=m)
    assert y["by_ticker"]["RY.TO"] == pytest.approx(0.02) and y["value"] == pytest.approx(0.02)


def test_trailing_yield_uses_the_last_calendar_close_on_a_weekend_as_of():
    idx = pd.bdate_range("2024-06-06", periods=3)                          # Thu, Fri, Mon
    prices = pd.DataFrame({"RY.TO": [100.0, 125.0, 200.0]}, index=idx)
    div = pd.DataFrame({"date": pd.to_datetime(["2024-06-06"]), "ticker": "RY.TO", "amount": 2.5})
    y = trailing_yield({"RY.TO": 1.0}, "2024-06-09", market=make_market(prices, dividends=div))   # a Sunday
    assert y["value"] == pytest.approx(2.5 / 125.0)                        # not the Monday close, not the Thursday one
    assert y["as_of"] == "2024-06-07"                                      # the last date actually in the data


def test_trailing_yield_contract_keys_types_and_json():
    y = trailing_yield({"RY.TO": 0.5, "MSFT": 0.3, "GLD": 0.2}, "2024-12-31", market=_yield_market())
    assert set(y) == {"value", "by_ticker", "source", "as_of"} and y["as_of"] == "2024-12-31"
    assert list(y["by_ticker"]) == ["RY.TO", "MSFT", "GLD"] and type(y["value"]) is float
    assert all(type(v) is float for v in y["by_ticker"].values())
    assert "history" in y["source"].lower() and "corporate_actions" in y["source"]
    json.dumps(y)


def test_trailing_yield_checks_the_weights_like_the_series_does():
    m = _yield_market()
    with pytest.raises(ValueError, match="add up to 100"):
        trailing_yield({"RY.TO": 0.5}, "2024-12-31", market=m)
    with pytest.raises(ValueError, match="Unknown ticker: ZZZ"):
        trailing_yield({"ZZZ": 1.0}, "2024-12-31", market=m)
    y = trailing_yield({"ry.to": 0.5, " msft ": 0.5}, "2024-12-31", market=m)    # read like apply_change reads them
    assert list(y["by_ticker"]) == ["RY.TO", "MSFT"]


def test_a_payer_without_a_close_is_none_not_a_made_up_zero():
    idx = pd.bdate_range("2024-01-01", "2024-03-29")
    prices = pd.DataFrame({"RY.TO": 100.0, "TD.TO": 50.0, "GAP.TO": 10.0}, index=idx)
    prices.loc[idx[-6:], ["TD.TO", "GAP.TO"]] = np.nan                    # stale for more than 3 days at as_of
    div = pd.DataFrame({"date": pd.to_datetime(["2024-02-01", "2024-02-01"]), "ticker": ["RY.TO", "TD.TO"],
                        "amount": [1.0, 1.0]})
    y = trailing_yield({"RY.TO": 0.5, "TD.TO": 0.25, "GAP.TO": 0.25}, "2024-03-29", market=make_market(prices, dividends=div))
    assert y["by_ticker"]["RY.TO"] == pytest.approx(0.01)
    assert y["by_ticker"]["TD.TO"] is None                                # paid 1.0, but no close to divide by
    assert y["by_ticker"]["GAP.TO"] == 0.0 and y["value"] is None         # paid nothing: 0 is true; the total cannot be said
    json.dumps(y)


def test_the_short_window_caveat_appears_exactly_when_the_data_starts_inside_the_window():
    m = _one_payer(["2024-01-02"])                                         # the calendar starts 2023-12-01
    full = trailing_yield({"RY.TO": 1.0}, "2024-11-29", market=m)          # (2023-11-30, 2024-11-29]: day 1 of the data is in
    short = trailing_yield({"RY.TO": 1.0}, "2024-11-28", market=m)
    assert "starts" not in full["source"] and "the data starts 2023-12-01" in short["source"]
    assert full["value"] == short["value"] == pytest.approx(0.01)


def test_before_the_first_day_of_data_every_yield_is_none_not_zero():
    y = trailing_yield({"RY.TO": 1.0}, "2023-11-01", market=_one_payer(["2024-01-02"]))   # the calendar starts 2023-12-01
    assert y["value"] is None and y["by_ticker"] == {"RY.TO": None} and y["as_of"] == "2023-11-01"
    json.dumps(y)


def test_trailing_yield_on_a_pack_without_corporate_actions_is_zero_everywhere():
    fake = load_market("2026-11-12", data_dir="data/fake/starter")        # the fake pack has no corporate_actions.csv
    y = trailing_yield({"XIU.TO": 0.6, "NVDA": 0.4}, "2026-11-12", market=fake)
    assert y["by_ticker"] == {"XIU.TO": 0.0, "NVDA": 0.0} and y["value"] == 0.0 and y["as_of"] == "2026-11-12"


# --- real data (skipped when data/starter/ is absent) --------------------------------------------
@REAL
def test_real_hiking_cycle_is_2022_03_to_2023_07():
    assert rate_regime("2026-11-12")["hiking"] == [{"start": "2022-03-03", "end": "2023-07-13"}]


@REAL
def test_real_rate_regime_series_and_what_the_investor_could_see_on_each_date():
    r = rate_regime(DATASET_END)
    assert r["as_of"] == DATASET_END and r["source"] == "Bank of Canada V39079 (macro_rates.csv)"
    d, v = r["series"]["dates"], r["series"]["values"]
    assert (d[0], v[0]) == ("2021-11-12", 0.0025) and (d[-1], v[-1]) == (DATASET_END, 0.025)
    assert len(d) == 22 and max(v) == 0.05 and d[v.index(0.05)] == "2023-07-13"      # 20 changes + first + last row
    # the lone hike of 2026-10-29 (after a long run of cuts) is not a second cycle
    assert [h["start"] for h in r["hiking"]] == ["2022-03-03"]
    # no look-ahead: what each earlier date could show (a hike on the day counts, the next one does not exist yet)
    assert rate_regime("2022-03-02")["hiking"] == []                       # the day before the first hike
    assert rate_regime("2022-03-03")["hiking"] == []                       # one hike is not a cycle yet
    assert rate_regime("2022-04-14")["hiking"] == [{"start": "2022-03-03", "end": "2022-04-14"}]
    assert rate_regime("2023-03-01")["hiking"] == [{"start": "2022-03-03", "end": "2023-01-26"}]
    assert rate_regime("2023-06-08")["hiking"] == [{"start": "2022-03-03", "end": "2023-06-08"}]   # the pause is bridged
    assert max(rate_regime("2023-03-01")["series"]["dates"]) <= "2023-03-01"


@REAL
def test_real_trailing_yield_for_robert_today_and_after_from_the_unadjusted_close():
    from tools.portfolio import apply_change
    after_w = apply_change(ROBERT, {"op": "set", "ticker": "NVDA", "weight": 0.40})
    today, after = (trailing_yield(w, DATASET_END) for w in (ROBERT, after_w))
    # independent recompute from the raw CSVs (/tmp probe, Nov 14): dividends over the 365 days to 2026-11-12 in CAD
    # (USD x the rate of the ex-date) over the CAD close of 2026-11-12, close not adj_close
    assert today["by_ticker"] == pytest.approx({"XIU.TO": 0.020825, "XBB.TO": 0.035125, "GLD": 0.0, "ZST.TO": 0.025046},
                                               abs=1e-6)
    assert after["by_ticker"]["NVDA"] == pytest.approx(0.003041, abs=1e-6)
    assert today["value"] == pytest.approx(0.024170, abs=1e-6) and after["value"] == pytest.approx(0.015718, abs=1e-6)
    assert today["as_of"] == after["as_of"] == DATASET_END
    # gold and crypto pay nothing
    assert trailing_yield({"GLD": 0.5, "BTC-USD": 0.5}, DATASET_END)["value"] == 0.0
    # an early as_of sees only the payouts already made (0.196 on 2021-11-23) over that day's UNadjusted close
    # (32.52; adj_close is 28.36 because it embeds the dividends paid since: that would be a look-ahead)
    early = trailing_yield({"XIU.TO": 1.0}, "2021-12-31")
    assert early["by_ticker"]["XIU.TO"] == pytest.approx(0.196 / 32.52) and "starts 2021-11-12" in early["source"]
    assert "starts" not in today["source"]                                 # a full 12 months of data: no caveat


@REAL
def test_real_robert_volatility_and_sharpe_reproduce_the_independent_recompute():
    """Task 4 review minor 7: volatility and Sharpe were not pinned. Recomputed Nov 14 with a from-scratch
    script (own pivot, FX, ffill, series and formulas; /tmp/epi_a5/probe_vol.py): 7.4117 % / 22.1806 % and
    Sharpe 0.74716 / 0.993263 with rf = the mean V39079 over the period, 3.1906 %."""
    from tools.data import mean_policy_rate
    from tools.portfolio import apply_change, portfolio_series
    after_w = apply_change(ROBERT, {"op": "set", "ticker": "NVDA", "weight": 0.40})
    out = []
    for w in (ROBERT, after_w):
        s = portfolio_series(w, as_of=DATASET_END)
        rf = mean_policy_rate(s["dates"][0], s["dates"][-1], DATASET_END)
        assert round(rf * 100, 4) == 3.1906
        out.append(risk_metrics(s, rf=rf))
    today, after = out
    assert (round(today["volatility"] * 100, 3), round(after["volatility"] * 100, 3)) == (7.412, 22.181)
    assert (round(today["sharpe"], 4), round(after["sharpe"], 4)) == (0.7472, 0.9933)


@REAL
def test_real_labels_for_a_future_as_of_are_the_last_date_in_the_data():
    """Task 4 review minor 4 (ruling d): a request for 2030-01-01 is labelled with the last data date."""
    from tools.portfolio import portfolio_series
    s = portfolio_series(ROBERT, as_of="2030-01-01")
    assert s["dates"][-1] == DATASET_END and s["as_of"] == DATASET_END == risk_metrics(s)["as_of"]
    assert trailing_yield(ROBERT, "2030-01-01")["as_of"] == rate_regime("2030-01-01")["as_of"] == DATASET_END


def test_risk_metrics_and_the_series_it_reads_name_the_same_last_date_for_a_future_as_of():
    from tools.portfolio import portfolio_series
    fake = "data/fake/starter"
    s = portfolio_series({"XIU.TO": 0.5, "NVDA": 0.5}, as_of="2030-01-01", market=load_market("2030-01-01", data_dir=fake))
    assert s["as_of"] == risk_metrics(s)["as_of"] == s["dates"][-1] == DATASET_END
    assert trailing_yield({"XIU.TO": 1.0}, "2030-01-01", market=load_market("2030-01-01", data_dir=fake))["as_of"] == DATASET_END


# Task 6 (the Task 5 review minors): the hiking dates are effective dates; the yield counts ex-dividend rows
def test_labels_say_effective_dates_and_ex_dividend():
    import tools.metrics as metrics
    assert "effective" in metrics.__doc__ and "effective" in rate_regime.__doc__
    assert metrics.RATE_SOURCE == "Bank of Canada V39079 (macro_rates.csv)"       # pinned verbatim
    assert "ex-dividend" in metrics.YIELD_SOURCE and "special or extra" in metrics.YIELD_SOURCE
    assert "paid" not in metrics.YIELD_SOURCE and "went ex-dividend" in metrics.__doc__


@REAL
def test_per_year_annualises_with_the_series_own_sessions_and_252_stays_the_default():
    """Ruling R36 (finance F9, fix wave lane fin-backend): Robert's move has 1,281 daily returns over 1,826 calendar
    days, 256.2 sessions a year, so 22.37 % rather than 22.18 % (the default, kept for every other caller)."""
    from tools.portfolio import apply_change, portfolio_series
    s = portfolio_series(apply_change(ROBERT, {"op": "set", "ticker": "NVDA", "weight": 0.40}), as_of=DATASET_END)
    r = pd.Series(s["values"]).pct_change().dropna()
    k = len(r) / ((pd.Timestamp(s["dates"][-1]) - pd.Timestamp(s["dates"][0])).days / 365.25)
    own, default = risk_metrics(s, per_year="sessions"), risk_metrics(s)
    assert (len(r), round(k, 1)) == (1281, 256.2) and own["volatility"] == pytest.approx(r.std(ddof=1) * k ** 0.5)
    assert (round(own["volatility"] * 100, 2), round(default["volatility"] * 100, 2)) == (22.37, 22.18)
    assert risk_metrics(s, per_year=252) == default and "sqrt(256.2, the sessions a year in the series)" in own["source"]
    assert {key: v for key, v in own.items() if key not in ("volatility", "sharpe", "source")} == {
        key: v for key, v in default.items() if key not in ("volatility", "sharpe", "source")}
    assert risk_metrics(ser([100, 90]), per_year="sessions")["volatility"] is None


# --- Task 14: real-data smoke tests (spec §3/§10 values) and the performance budget (spec §8) -------
AFTER = apply_change(ROBERT, {"op": "set", "ticker": "NVDA", "weight": 0.40})
AMIRA = {"NVDA": .15, "QQQ": .15, "SHOP.TO": .10, "BTC-USD": .15, "XIU.TO": .30, "XBB.TO": .15}
MATEO = {"XIU.TO": .35, "XBB.TO": .35, "CNQ.TO": .08, "MSFT": .10, "GLD": .12}


def mdd(w, m):
    s = series_from_market(w, m)
    return risk_metrics({"dates": s.index.strftime("%Y-%m-%d").tolist(), "values": s.tolist()})


@REAL
def test_real_pilot_drawdowns_match_spec():                      # spec §3 ✓ values
    m = load_market("2026-11-12")
    today, after = mdd(ROBERT, m), mdd(AFTER, m)
    assert today["max_drawdown"] == pytest.approx(-0.106, abs=0.001) and today["recovery_days"] == 416
    assert after["max_drawdown"] == pytest.approx(-0.345, abs=0.001)
    assert (after["peak_date"], after["trough_date"]) == ("2021-11-29", "2022-10-14")
    assert (after["cagr"], today["cagr"]) == (pytest.approx(0.252, abs=0.001), pytest.approx(0.087, abs=0.001))
    assert mdd(AMIRA, m)["max_drawdown"] == pytest.approx(-0.413, abs=0.002)
    assert mdd(MATEO, m)["max_drawdown"] == pytest.approx(-0.114, abs=0.001)


@REAL
def test_real_size_edge_8_and_9_percent():                       # spec §10, pitfall 5
    m = load_market("2026-11-12")
    at = lambda x: mdd(apply_change(ROBERT, {"op": "set", "ticker": "NVDA", "weight": x}), m)["max_drawdown"]
    assert at(0.08) == pytest.approx(-0.15, abs=0.0005) and at(0.09) == pytest.approx(-0.156, abs=0.001)


@REAL
def test_real_sealed_envelope_drops():                           # spec §10 ✓ −15.9 % and −11.3 %
    s = portfolio_series(AFTER, "2025-01-31", "2026-01-31", as_of="2026-11-12")
    v = s["values"]
    assert risk_metrics(s)["max_drawdown"] == pytest.approx(-0.159, abs=0.002)
    assert min(v) / v[0] - 1 == pytest.approx(-0.113, abs=0.002)


@REAL
def test_perf_robert_full_a_path():
    _quiet_machine_only()
    load_market("2026-11-12")                                     # warm the cache
    t = time.perf_counter()
    m = load_market("2026-11-12")
    ev = load_events("2026-11-12", market=m)
    for w in (ROBERT, AFTER):
        mdd(w, m); look_through(w); risk_contributions(w, "2026-11-12", market=m)
        diversification(w, "2026-11-12", market=m)
        turbulence(w, None, "2026-11-12", market=m, events=ev)
        for e in ev:
            if e["known"]:
                event_impact(w, e["event_id"], as_of="2026-11-12", market=m, events=ev)
    assert time.perf_counter() - t < 2.0


@REAL
def test_perf_size_curve_41_weights():
    _quiet_machine_only()
    m = load_market("2026-11-12")
    ev = load_events("2026-11-12", market=m)
    t = time.perf_counter()
    for k in range(41):
        w = apply_change(ROBERT, {"op": "set", "ticker": "NVDA", "weight": k / 100})
        mdd(w, m); scenario_stress(w, ["tariffs"], "2026-11-12", market=m, events=ev)
    assert time.perf_counter() - t < 3.0


# --- Task 17: per-asset 2021–26 facts for the move picker (ledger: data/asset_facts.json) -----------
FACT_KEYS = {"total_return", "ann_vol", "max_drawdown", "dd_peak", "dd_trough", "days"}


def test_asset_facts_are_exact_on_a_known_series():
    idx = pd.bdate_range("2024-01-01", periods=5)                  # Mon 1 to Fri 5 January
    m = make_market(pd.DataFrame({"XIU.TO": [100.0, 110.0, 99.0, 121.0, 115.0]}, index=idx))
    f = asset_facts(as_of="2024-01-05", market=m)
    a = f["assets"]["XIU.TO"]
    r = np.array([110 / 100, 99 / 110, 121 / 99, 115 / 121]) - 1
    k = 4 * 365.25 / 4                                             # ruling R36: 4 returns over 4 calendar days
    assert set(a) == FACT_KEYS
    assert a["total_return"] == pytest.approx(0.15)
    assert a["ann_vol"] == pytest.approx(r.std(ddof=1) * math.sqrt(k))
    assert (a["max_drawdown"], a["dd_peak"], a["dd_trough"]) == (pytest.approx(99 / 110 - 1), "2024-01-02", "2024-01-03")
    assert a["days"] == 5
    assert (f["as_of"], f["period"], f["currency"]) == ("2024-01-05", ["2024-01-01", "2024-01-05"], "CAD")
    assert f["source"] and f["flags"] == {"XIU.TO": []}


def test_asset_facts_a_4_day_price_gap_stays_finite_and_is_flagged():
    idx = pd.bdate_range("2024-01-01", periods=10)
    px = [100.0, 101.0, np.nan, np.nan, np.nan, np.nan, 104.0, 103.0, 105.0, 106.0]
    m = make_market(pd.DataFrame({"XIU.TO": px}, index=idx))
    f = asset_facts(as_of="2024-01-12", market=m)
    a = f["assets"]["XIU.TO"]
    assert all(math.isfinite(a[key]) for key in ("total_return", "ann_vol", "max_drawdown"))
    assert a["total_return"] == pytest.approx(0.06) and a["days"] == 6
    assert f["flags"] == {"XIU.TO": ["2024-01-08"]}                # the 4th missing day, after the 3-day fill


def test_asset_facts_see_nothing_after_as_of():
    idx = pd.bdate_range("2024-01-01", periods=6)
    m = make_market(pd.DataFrame({"XIU.TO": [100.0, 102.0, 104.0, 106.0, 50.0, 40.0]}, index=idx))
    f = asset_facts(as_of="2024-01-04", market=m)                 # the crash on 5 and 8 January is later
    a = f["assets"]["XIU.TO"]
    assert a["total_return"] == pytest.approx(0.06) and a["max_drawdown"] == 0.0 and a["days"] == 4
    assert (a["dd_peak"], a["dd_trough"]) == (None, None)
    assert (f["as_of"], f["period"]) == ("2024-01-04", ["2024-01-01", "2024-01-04"])


@REAL
def test_real_asset_facts_cover_the_31_assets_and_crypto_uses_its_own_utc_rows():
    m = load_market(DATASET_END)
    f = asset_facts(market=m)
    assert set(f["assets"]) == set(m["universe"]["ticker"]) and len(f["assets"]) == 31
    assert all(set(a) == FACT_KEYS for a in f["assets"].values())
    assert all(math.isfinite(a[key]) for a in f["assets"].values() for key in ("total_return", "ann_vol", "max_drawdown"))
    btc = f["assets"]["BTC-USD"]
    assert btc["days"] == m["crypto_daily"]["BTC-USD"].dropna().size
    assert btc["days"] > len(m["calendar"]) >= f["assets"]["SPY"]["days"]
