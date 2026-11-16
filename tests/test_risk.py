"""Task 8 tests: tools/risk.py, the diversification logic (spec section 10; plan A Task 8; ledger 1, 7, 14, 26).

Offline: synthetic bundles from `make_market` and the Task 6 universe `UNI`. The cases on the real starter data
and the local ETF holdings skip when those files are absent (neither is ever committed, red gate 8).
Finance truth for the same functions: tests/test_metrics.py (the finance lead), which this file never edits.
"""
import numpy as np, pandas as pd, pytest
from pathlib import Path

import tools.lookthrough as ltmod
from tools.data import make_market
from tools.lookthrough import look_through
from tools.portfolio import portfolio_series
from tools.risk import asset_returns, capacity_line, diversification, risk_contributions
from tests.test_lookthrough import UNI, H          # the Task 6 universe and holdings builder (Task 7's Decision: reuse, never copy)

IDX = pd.bdate_range("2024-01-01", periods=9)

def px(rets):                                       # daily returns -> price path starting at 100
    # The brief printed np.cumprod([1.0] + list(rets)): that multiplies the returns themselves (prices 100, 1, -0.01, ...
    # and "returns" of -0.99 / -1.01). The growth factor is 1 + r; every test below is written for that path.
    return 100 * np.cumprod([1.0] + [1 + r for r in rets])

def mk(cols):
    return make_market(pd.DataFrame({t: px(r) for t, r in cols.items()}, index=IDX), universe=UNI)

A = [0.01, -0.01, 0.01, -0.01, 0.01, -0.01, 0.01, -0.01]
B = [0.01, 0.01, -0.01, -0.01, 0.01, 0.01, -0.01, -0.01]          # uncorrelated with A, same vol


# --- the brief's tests, verbatim -------------------------------------------------------------------
def test_two_uncorrelated_equal_vol_assets():                      # spec §15
    out = risk_contributions({"NVDA": 0.5, "XIU.TO": 0.5}, "2024-01-11", market=mk({"NVDA": A, "XIU.TO": B}))
    assert out["shares"] == pytest.approx({"NVDA": 0.5, "XIU.TO": 0.5}, abs=1e-9)
    assert out["bets"] == pytest.approx(2.0) and out["degenerate"] is False

def test_single_asset_and_sum_to_one_with_a_hedge():
    assert risk_contributions({"NVDA": 1.0}, "2024-01-11", market=mk({"NVDA": A}))["shares"] == pytest.approx({"NVDA": 1.0})
    hedge = [-r / 2 for r in A]
    out = risk_contributions({"NVDA": 0.8, "GLD": 0.2}, "2024-01-11", market=mk({"NVDA": A, "GLD": hedge}))
    assert sum(out["shares"].values()) == pytest.approx(1.0) and out["shares"]["GLD"] < 0

def test_flat_prices_do_not_divide_by_zero():
    out = risk_contributions({"NVDA": 0.6, "XIU.TO": 0.4}, "2024-01-11", market=mk({"NVDA": [0] * 8, "XIU.TO": [0] * 8}))
    assert out["degenerate"] is True and out["shares"] == pytest.approx({"NVDA": 0.6, "XIU.TO": 0.4})
    assert out["bets"] == pytest.approx(1 / (0.36 + 0.16))

def test_risk_uses_nothing_after_as_of():
    m = mk({"NVDA": A, "XIU.TO": B})
    a = risk_contributions({"NVDA": 0.5, "XIU.TO": 0.5}, "2024-01-08", market=m)
    m2 = mk({"NVDA": A[:5] + [0.5, -0.5, 0.5], "XIU.TO": B})     # wild moves only after 2024-01-08
    assert risk_contributions({"NVDA": 0.5, "XIU.TO": 0.5}, "2024-01-08", market=m2)["shares"] == pytest.approx(a["shares"])

def test_diversification_currencies_countries_and_can_risk():
    # Ruled after the brief (controller, ledger 30): `lt` is dated 2026-11-12 (look_through's default), AFTER the decision
    # 2024-01-11, so it is not used (red gate 3): direct mode, flagged in `source`. The brief's numbers hold because
    # the fallback is the same direct picture; the last two lines are the deviation from the plan.
    w = {"XIU.TO": 0.5, "NVDA": 0.3, "XBB.TO": 0.2}
    m = mk({"XIU.TO": B, "NVDA": A, "XBB.TO": [0.001] * 8})
    lt = look_through(w, holdings=pd.DataFrame(), universe=UNI, esg_flags=set())
    out = diversification(w, "2024-01-11", lookthrough=lt, universe=UNI, market=m)
    assert out["currencies"] == pytest.approx({"CAD": 0.7, "USD": 0.3, "OTHER": 0.0})
    assert out["countries"] == pytest.approx({"CAN": 0.7, "USA": 0.3})
    assert list(out["sectors"]) == ["Information Technology"]
    rc = risk_contributions(w, "2024-01-11", market=m)["shares"]
    assert out["can_risk_share"] == pytest.approx(1 - rc["NVDA"])
    assert lt["as_of"] == "2026-11-12" and out["as_of"] == "2024-01-11"
    assert "direct" in out["source"] and "after the decision date 2024-01-11" in out["source"]


# --- asset_returns, the ledger 7 form: (weights, as_of, *, market=None) ----------------------------------
def test_asset_returns_are_the_daily_returns_behind_portfolio_series():     # ledger 12: the risk matches the series judged
    w = {"XIU.TO": 0.6, "NVDA": 0.4}
    m = mk({"XIU.TO": B, "NVDA": A})
    r = asset_returns(w, "2024-01-11", market=m)
    assert list(r.columns) == ["XIU.TO", "NVDA"] and len(r) == 8
    assert r.index[0] == IDX[1] and r.index[-1] == IDX[-1]                  # the first row is dropped
    assert r["NVDA"].to_numpy() == pytest.approx(A) and r["XIU.TO"].to_numpy() == pytest.approx(B)
    values = portfolio_series(w, as_of="2024-01-11", market=m)["values"]
    daily = r.to_numpy() @ np.array([0.6, 0.4])
    assert 100 * np.cumprod(1 + daily) == pytest.approx(values[1:])

def test_a_us_line_keeps_the_usdcad_move_of_a_tsx_only_day():               # ledger 12, the Task 3 convention
    idx = pd.bdate_range("2024-01-02", periods=5)
    usd = pd.DataFrame({"XIU.TO": [100, 101, 102, 103, 104.0], "NVDA": [10, 10.5, 10.5, 11, 11.5]}, index=idx)
    fx = pd.Series([1.30, 1.31, 1.33, 1.32, 1.34], index=idx)
    cad = usd.copy(); cad["NVDA"] = usd["NVDA"] * fx                         # the US market is closed on idx[2]: price carried, rate moves
    traded = pd.DataFrame(True, index=idx, columns=usd.columns); traded.loc[idx[2], "NVDA"] = False
    m = make_market(cad, local=usd, fx=fx, traded=traded, universe=UNI)
    alone = asset_returns({"NVDA": 1.0}, "2024-01-10", market=m)
    assert list(alone.index) == [idx[1], idx[3], idx[4]]                     # a day nobody held traded is not counted
    assert (1 + alone["NVDA"]).prod() == pytest.approx((11.5 * 1.34) / (10 * 1.30))   # ends at the true CAD price ratio
    both = asset_returns({"XIU.TO": 0.5, "NVDA": 0.5}, "2024-01-10", market=m)
    assert both.loc[idx[2], "NVDA"] == pytest.approx(1.33 / 1.31 - 1)       # the loonie moved while Wall Street was shut

def test_a_price_gap_books_the_move_when_trading_resumes():                  # Task 3's rule: carried forward, a gap never loses the move
    idx = pd.bdate_range("2024-01-02", periods=8)
    gap = pd.DataFrame({"XIU.TO": [100, 101, 102, 103, 104, 105, 106, 107.0],
                        "NVDA": [10, 11, np.nan, np.nan, np.nan, np.nan, 13, 13.5]}, index=idx)   # four days with no price
    r = asset_returns({"XIU.TO": 0.5, "NVDA": 0.5}, "2024-01-11", market=make_market(gap, universe=UNI))
    assert r["NVDA"].iloc[1:5].tolist() == [0.0, 0.0, 0.0, 0.0]            # nothing is invented inside the gap
    assert r.loc[idx[6], "NVDA"] == pytest.approx(13 / 11 - 1)             # the whole move is booked on the day it resumes
    assert (1 + r["NVDA"]).prod() == pytest.approx(13.5 / 10)

def test_asset_returns_cut_at_as_of_and_ignore_the_future():
    w = {"NVDA": 0.5, "XIU.TO": 0.5}
    a = asset_returns(w, "2024-01-08", market=mk({"NVDA": A, "XIU.TO": B}))
    assert len(a) == 5 and a.index[-1] == pd.Timestamp("2024-01-08")
    scrambled = asset_returns(w, "2024-01-08", market=mk({"NVDA": A[:5] + [0.5, -0.5, 0.5], "XIU.TO": B}))
    pd.testing.assert_frame_equal(a, scrambled)

def test_asset_returns_refuse_an_unknown_ticker_and_weights_that_do_not_add_up():
    m = mk({"NVDA": A, "XIU.TO": B})
    with pytest.raises(ValueError, match="Unknown ticker: ZZZ"):
        asset_returns({"NVDA": 0.5, "ZZZ": 0.5}, "2024-01-11", market=m)
    with pytest.raises(ValueError, match="add up to 100 %"):
        risk_contributions({"NVDA": 0.5, "XIU.TO": 0.2}, "2024-01-11", market=m)

def test_every_output_carries_source_and_the_last_data_day_as_as_of():      # ledger 0
    m = mk({"NVDA": A, "XIU.TO": B})
    out = risk_contributions({"NVDA": 0.5, "XIU.TO": 0.5}, "2024-01-13", market=m)       # a Saturday
    assert out["as_of"] == "2024-01-11" and out["source"]
    assert risk_contributions({"NVDA": 0.5, "XIU.TO": 0.5}, "2024-01-08", market=m)["as_of"] == "2024-01-08"
    assert risk_contributions({"NVDA": 0.5, "XIU.TO": 0.5}, "2030-01-01", market=m)["as_of"] == "2024-01-11"


# --- independent bets = Meucci's effective number of bets (ledger 14 and 26; spec 10) ---------------------
WALSH = [A, B, [0.01, 0.01, 0.01, 0.01, -0.01, -0.01, -0.01, -0.01]]   # three orthogonal zero-mean +-1 % patterns

def test_two_lines_0_99_correlated_behave_like_one_bet():                  # ledger 14: ENB < 1.1
    rng = np.random.default_rng(7)
    x = rng.normal(0, 0.01, 600)
    y = 0.99 * x + np.sqrt(1 - 0.99 ** 2) * rng.normal(0, 0.01, 600)
    assert np.corrcoef(x, y)[0, 1] > 0.98                                  # the fixture is what it says
    idx = pd.bdate_range("2020-01-01", periods=601)
    m = make_market(pd.DataFrame({"NVDA": px(x), "QQQ": px(y)}, index=idx))
    out = risk_contributions({"NVDA": 0.5, "QQQ": 0.5}, idx[-1].strftime("%Y-%m-%d"), market=m)
    assert 1.0 <= out["bets"] < 1.1 and out["degenerate"] is False

def test_equal_risk_uncorrelated_lines_are_as_many_bets_as_lines_for_any_money_split():
    names = ["NVDA", "XIU.TO", "GLD"]                                       # an isotropic covariance: every axis choice is a PCA,
    w = np.array([0.5, 0.3, 0.2])                                           # so the lines' own axes are the answer, not float noise
    out = risk_contributions(dict(zip(names, w)), "2024-01-11", market=mk(dict(zip(names, WALSH))))
    p = w ** 2 / np.sum(w ** 2)
    assert out["shares"] == pytest.approx(dict(zip(names, p)), abs=1e-9)
    assert out["bets"] == pytest.approx(float(np.exp(-np.sum(p * np.log(p)))), abs=1e-9)

def test_one_source_of_risk_is_one_bet_however_many_lines_carry_it():
    hedge = risk_contributions({"NVDA": 0.8, "GLD": 0.2}, "2024-01-11", market=mk({"NVDA": A, "GLD": [-r / 2 for r in A]}))
    assert hedge["bets"] == pytest.approx(1.0, abs=1e-6)                    # a perfect hedge is the same bet, turned around
    flat = risk_contributions({"NVDA": 0.5, "XIU.TO": 0.5}, "2024-01-11", market=mk({"NVDA": A, "XIU.TO": [0] * 8}))
    assert flat["degenerate"] is False                                      # one line still moves, so there is a risk to share
    assert flat["shares"] == pytest.approx({"NVDA": 1.0, "XIU.TO": 0.0}, abs=1e-9)
    assert flat["bets"] == pytest.approx(1.0, abs=1e-6)
    assert risk_contributions({"NVDA": 1.0}, "2024-01-11", market=mk({"NVDA": A}))["bets"] == pytest.approx(1.0)

def test_the_unequal_vol_fixture_of_ledger_26_holds_across_seeds():        # C Task 6 pins seed 1; ENB holds on 500 of 500 seeds
    idx = pd.bdate_range("2018-01-01", periods=2001)
    for seed in range(12):
        rng = np.random.default_rng(seed)
        a, b = rng.normal(0, 0.01, 2000), rng.normal(0, 0.02, 2000)
        out = risk_contributions({"A": 2 / 3, "B": 1 / 3}, idx[-1].strftime("%Y-%m-%d"),
                                 market=make_market(pd.DataFrame({"A": px(a), "B": px(b)}, index=idx)))
        assert out["bets"] == pytest.approx(2.0, abs=0.05), seed
        assert sum(out["shares"].values()) == pytest.approx(1.0)


# --- degenerate inputs: never a division by zero (spec 15, Review Focus 3) ---------------------------------
def test_one_return_day_is_too_few_for_a_covariance_and_before_the_data_is_nothing():
    m = mk({"NVDA": A, "XIU.TO": B})
    out = risk_contributions({"NVDA": 0.7, "XIU.TO": 0.3}, "2024-01-02", market=m)       # one return day
    assert out["degenerate"] is True and out["shares"] == pytest.approx({"NVDA": 0.7, "XIU.TO": 0.3})
    assert out["bets"] == pytest.approx(1 / (0.49 + 0.09))
    before = risk_contributions({"NVDA": 0.7, "XIU.TO": 0.3}, "2023-12-01", market=m)    # no data yet
    assert before["degenerate"] is True and before["as_of"] == "2023-12-01"

def test_a_constant_growth_path_has_no_variance_to_share():     # 0.1 % a day exactly: only rounding noise is left
    out = risk_contributions({"XBB.TO": 1.0}, "2024-01-11", market=mk({"XBB.TO": [0.001] * 8}))
    assert out["degenerate"] is True and out["shares"] == pytest.approx({"XBB.TO": 1.0}) and out["bets"] == pytest.approx(1.0)

def test_shares_come_biggest_first_and_are_plain_floats():
    out = risk_contributions({"XIU.TO": 0.2, "NVDA": 0.8}, "2024-01-11", market=mk({"XIU.TO": B, "NVDA": A}))
    assert list(out["shares"]) == ["NVDA", "XIU.TO"]                                     # 0.8 of the money carries 0.94 of the risk
    assert out["shares"]["NVDA"] == pytest.approx(0.8 ** 2 / (0.8 ** 2 + 0.2 ** 2))
    assert all(type(v) is float for v in out["shares"].values()) and type(out["bets"]) is float


# --- diversification: where the money and the risk really are ----------------------------------------------
IDX2 = pd.bdate_range("2026-11-02", periods=9)                  # ends on DATASET_END, so today's holdings snapshot is not "future"
UNI_X = pd.concat([UNI, pd.DataFrame([r.split(",") for r in [
    "SAP.DE,SAP,equity,XETRA,EUR,Information Technology,DEU"]], columns=UNI.columns)], ignore_index=True)

def mk2(cols, universe=UNI):
    return make_market(pd.DataFrame({t: px(r) for t, r in cols.items()}, index=IDX2), universe=universe)

def test_diversification_reports_the_ledger_keys_and_other_currencies():
    w = {"XIU.TO": 0.5, "NVDA": 0.3, "SAP.DE": 0.2}
    m = make_market(pd.DataFrame({"XIU.TO": px(B), "NVDA": px(A), "SAP.DE": px(WALSH[2])}, index=IDX), universe=UNI_X)
    lt = look_through(w, holdings=pd.DataFrame(), universe=UNI_X, esg_flags=set())
    out = diversification(w, "2024-01-11", lookthrough=lt, universe=UNI_X, market=m)
    assert set(out) == {"countries", "currencies", "sectors", "can_risk_share", "source", "as_of"} and out["source"]
    assert list(out["currencies"]) == ["CAD", "USD", "OTHER"]
    assert out["currencies"] == pytest.approx({"CAD": 0.5, "USD": 0.3, "OTHER": 0.2})
    assert out["as_of"] == "2024-01-11" and all(type(v) is float for v in out["currencies"].values())

def test_sectors_are_the_five_largest_biggest_first():
    names = [f"S{i}" for i in range(1, 8)]
    uni = pd.DataFrame([(t, t, "equity", "NASDAQ", "USD", f"Sector {i}", "USA") for i, t in enumerate(names, 1)], columns=UNI.columns)
    w = dict(zip(names, [0.03, 0.30, 0.09, 0.22, 0.13, 0.06, 0.17]))                  # unsorted on purpose; sums to 1
    m = make_market(pd.DataFrame({t: px(WALSH[i % 3]) for i, t in enumerate(names)}, index=IDX), universe=uni)
    lt = look_through(w, holdings=pd.DataFrame(), universe=uni, esg_flags=set())
    out = diversification(w, "2024-01-11", lookthrough=lt, universe=uni, market=m)
    assert list(out["sectors"]) == ["Sector 2", "Sector 4", "Sector 7", "Sector 5", "Sector 3"]
    assert out["sectors"] == pytest.approx({"Sector 2": 0.30, "Sector 4": 0.22, "Sector 7": 0.17, "Sector 5": 0.13, "Sector 3": 0.09})

def test_diversification_uses_nothing_after_as_of():
    w = {"XIU.TO": 0.5, "NVDA": 0.5}
    lt = look_through(w, holdings=pd.DataFrame(), universe=UNI, esg_flags=set())
    a = diversification(w, "2024-01-08", lookthrough=lt, universe=UNI, market=mk({"XIU.TO": B, "NVDA": A}))
    b = diversification(w, "2024-01-08", lookthrough=lt, universe=UNI, market=mk({"XIU.TO": B, "NVDA": A[:5] + [0.5, -0.5, 0.5]}))
    assert a["can_risk_share"] == pytest.approx(b["can_risk_share"])


def test_a_hedge_has_negative_risk_so_the_canadian_risk_share_is_not_clamped():     # documented in diversification
    w = {"XIU.TO": 0.9, "GLD": 0.1}
    m = mk({"XIU.TO": A, "GLD": [-r / 2 for r in A]})
    lt = look_through(w, holdings=pd.DataFrame(), universe=UNI, esg_flags=set(), as_of="2024-01-11")
    gld = risk_contributions(w, "2024-01-11", market=m)["shares"]["GLD"]
    out = diversification(w, "2024-01-11", lookthrough=lt, universe=UNI, market=m)
    assert gld < 0 and out["can_risk_share"] == pytest.approx(1 - gld) and out["can_risk_share"] > 1.0
    assert OFFSET_ABOVE in out["source"] and OFFSET_BELOW not in out["source"]       # red gate 4: a number above 100 % says why

def test_degenerate_risk_leaves_the_money_weights_as_the_canadian_risk_share():
    w = {"XIU.TO": 0.7, "NVDA": 0.3}
    lt = look_through(w, holdings=pd.DataFrame(), universe=UNI, esg_flags=set())
    out = diversification(w, "2024-01-11", lookthrough=lt, universe=UNI, market=mk({"XIU.TO": [0] * 8, "NVDA": [0] * 8}))
    assert out["can_risk_share"] == pytest.approx(0.7)


# --- what `source` says when a number is not what its method claims (red gate 4) ----------------------------
NOT_MEASURED = "risk could not be measured on these dates (too few or flat returns), so it is shown at the money weights"
OFFSET_ABOVE = "above 100 % because a line with negative risk offsets the others"
OFFSET_BELOW = "below 0 % because the Canadian lines carry negative risk, which offsets the others"

def test_degenerate_risk_is_said_in_source_not_hidden_behind_the_covariance_method(monkeypatch, tmp_path):
    monkeypatch.setattr(ltmod, "HOLDINGS_CSV", tmp_path / "none.csv")           # no holdings file: direct mode, nothing local read
    w = {"XIU.TO": 0.7, "NVDA": 0.3}
    for day, m in (("2024-01-02", mk({"XIU.TO": B, "NVDA": A})),                # the first trading days: one return day
                   ("2023-12-01", mk({"XIU.TO": B, "NVDA": A})),                # before the data
                   ("2024-01-11", mk({"XIU.TO": [0] * 8, "NVDA": [0] * 8}))):   # flat lines
        risk, out = risk_contributions(w, day, market=m), diversification(w, day, universe=UNI, market=m)
        assert risk["degenerate"] is True and out["can_risk_share"] == pytest.approx(0.7), day   # the money weights
        for source in (risk["source"], out["source"]):
            assert NOT_MEASURED in source, (day, source)
            assert "sample covariance" not in source and "Meucci" not in source, (day, source)
        assert OFFSET_ABOVE not in out["source"] and OFFSET_BELOW not in out["source"]

def test_measured_risk_still_names_its_method_and_an_ordinary_share_needs_no_caveat(monkeypatch, tmp_path):
    monkeypatch.setattr(ltmod, "HOLDINGS_CSV", tmp_path / "none.csv")
    w = {"XIU.TO": 0.5, "NVDA": 0.5}
    m = mk({"XIU.TO": B, "NVDA": A})
    risk, out = risk_contributions(w, "2024-01-11", market=m), diversification(w, "2024-01-11", universe=UNI, market=m)
    assert risk["degenerate"] is False
    for source in (risk["source"], out["source"]):
        assert "sample covariance" in source and "Meucci" in source and NOT_MEASURED not in source
    assert OFFSET_ABOVE not in out["source"] and OFFSET_BELOW not in out["source"] and 0 <= out["can_risk_share"] <= 1
    for k in (0.05, 0.25, 0.35):          # all Canadian: 100 % of the risk. At these weights the float sum is 1 + 2.2e-16: not a hedge
        full = diversification({"XIU.TO": k, "XBB.TO": 1 - k}, "2024-01-11", universe=UNI, market=mk({"XIU.TO": B, "XBB.TO": A}))
        assert full["can_risk_share"] == pytest.approx(1.0) and OFFSET_ABOVE not in full["source"], k

def test_a_canadian_hedge_is_said_in_source_when_the_canadian_risk_share_is_below_zero():
    w = {"NVDA": 0.9, "XBB.TO": 0.1}                                            # bonds that move against the US stock
    m = mk({"NVDA": A, "XBB.TO": [-r / 2 for r in A]})
    lt = look_through(w, holdings=pd.DataFrame(), universe=UNI, esg_flags=set(), as_of="2024-01-11")
    bonds = risk_contributions(w, "2024-01-11", market=m)["shares"]["XBB.TO"]
    out = diversification(w, "2024-01-11", lookthrough=lt, universe=UNI, market=m)
    assert bonds < 0 and out["can_risk_share"] == pytest.approx(bonds) and out["can_risk_share"] < 0
    assert OFFSET_BELOW in out["source"] and OFFSET_ABOVE not in out["source"]


SPLIT = [("XIU.TO", "country", "CAN", "", 0.7), ("XIU.TO", "country", "USA", "", 0.3),
         ("ETF1", "country", "USA", "", 1.0), ("ETF1", "holding", "NVIDIA", "NVDA", 0.10)]    # snapshot dated 2026-11-12

def _holdings_file(monkeypatch, tmp_path):
    path = tmp_path / "etf_holdings.csv"
    H(SPLIT).to_csv(path, index=False)
    monkeypatch.setattr(ltmod, "HOLDINGS_CSV", path)             # holdings=None reads this file

def test_can_risk_share_follows_the_etf_country_rows_when_the_look_through_is_real(monkeypatch, tmp_path):
    _holdings_file(monkeypatch, tmp_path)
    w = {"XIU.TO": 0.6, "ETF1": 0.4}
    m = mk2({"XIU.TO": B, "ETF1": A})
    out = diversification(w, "2026-11-12", universe=UNI, market=m)           # no look-through given: it builds its own
    assert out["countries"] == pytest.approx({"USA": 0.6 * 0.3 + 0.4, "CAN": 0.6 * 0.7})
    rc = risk_contributions(w, "2026-11-12", market=m)["shares"]
    assert out["can_risk_share"] == pytest.approx(rc["XIU.TO"] * 0.7)        # a fund is as Canadian as its country rows say
    given = look_through(w, universe=UNI, esg_flags=set(), as_of="2026-11-12")
    assert given["mode"] == "lookthrough"
    assert diversification(w, "2026-11-12", lookthrough=given, universe=UNI, market=m) == out

def test_a_past_as_of_never_sees_todays_holdings(monkeypatch, tmp_path):     # red gate 3: the snapshot is dated 2026-11-12
    _holdings_file(monkeypatch, tmp_path)
    w = {"XIU.TO": 0.6, "ETF1": 0.4}
    m = mk({"XIU.TO": B, "ETF1": A})
    out = diversification(w, "2024-01-11", universe=UNI, market=m)           # lookthrough=None, as B's evaluate passes for a past date
    assert out["countries"] == pytest.approx({"CAN": 0.6, "USA": 0.4})       # direct holdings: each fund by its listing country
    rc = risk_contributions(w, "2024-01-11", market=m)["shares"]
    assert out["can_risk_share"] == pytest.approx(rc["XIU.TO"])


# --- a supplied look-through is only as good as its date (ledger 30, red gate 3) ---------------------------
SECTORS = [("ETF1", "sector", "Information Technology", "", 0.6), ("ETF1", "sector", "Financials", "", 0.4)]

def test_a_look_through_dated_after_the_decision_is_not_used(monkeypatch, tmp_path):
    path = tmp_path / "etf_holdings.csv"
    H(SPLIT + SECTORS).to_csv(path, index=False)                             # a snapshot dated 2026-11-12
    monkeypatch.setattr(ltmod, "HOLDINGS_CSV", path)
    w = {"XIU.TO": 0.6, "ETF1": 0.4}
    today = look_through(w, universe=UNI, esg_flags=set(), as_of="2026-11-12")
    assert today["mode"] == "lookthrough" and "Information Technology" in today["sectors"]
    m = mk({"XIU.TO": B, "ETF1": A})
    out = diversification(w, "2024-01-11", lookthrough=today, universe=UNI, market=m)    # the decision is dated 2024-01-11
    assert out["countries"] == pytest.approx({"CAN": 0.6, "USA": 0.4})      # each fund by its listing country
    assert out["sectors"] == {}                                              # no ETF slice leaks in from the later snapshot
    rc = risk_contributions(w, "2024-01-11", market=m)["shares"]
    assert out["can_risk_share"] == pytest.approx(rc["XIU.TO"])             # CAN_i from listing countries, not the ETF's rows
    assert "direct" in out["source"] and "2026-11-12" in out["source"]
    assert "after the decision date 2024-01-11" in out["source"] and out["as_of"] == "2024-01-11"
    built = diversification(w, "2024-01-11", universe=UNI, market=m)                     # what lookthrough=None gives
    assert {k: v for k, v in out.items() if k != "source"} == {k: v for k, v in built.items() if k != "source"}

def test_a_look_through_dated_on_or_before_the_decision_is_used_as_given(monkeypatch, tmp_path):
    path = tmp_path / "etf_holdings.csv"
    H(SPLIT + SECTORS).assign(as_of="2024-01-05").to_csv(path, index=False)   # a snapshot that was known on 2024-01-11
    monkeypatch.setattr(ltmod, "HOLDINGS_CSV", path)
    w = {"XIU.TO": 0.6, "ETF1": 0.4}
    m = mk({"XIU.TO": B, "ETF1": A})
    rc = risk_contributions(w, "2024-01-11", market=m)["shares"]
    for dated in ("2024-01-11", "2024-01-08"):                               # the decision day itself, and an earlier day
        given = look_through(w, universe=UNI, esg_flags=set(), as_of=dated)
        assert given["mode"] == "lookthrough" and given["as_of"] == dated
        out = diversification(w, "2024-01-11", lookthrough=given, universe=UNI, market=m)
        assert out["countries"] == pytest.approx({"USA": 0.6 * 0.3 + 0.4, "CAN": 0.6 * 0.7})
        assert out["sectors"] == pytest.approx({"Information Technology": 0.4 * 0.6, "Financials": 0.4 * 0.4})
        assert out["can_risk_share"] == pytest.approx(rc["XIU.TO"] * 0.7)
        assert "after the decision date" not in out["source"] and out["as_of"] == "2024-01-11"
        if dated == "2024-01-11":
            assert "earlier than" not in out["source"]                       # as fresh as the decision: nothing to say
        else:                                                                # an older picture says both dates (ledger 30)
            assert f"the look-through is dated {dated}, earlier than the decision date 2024-01-11" in out["source"]


def test_a_late_look_through_means_direct_mode_even_with_an_older_snapshot_on_file(monkeypatch, tmp_path):   # ledger 30: "direct"
    path = tmp_path / "etf_holdings.csv"
    H(SPLIT + SECTORS).assign(as_of="2024-01-05").to_csv(path, index=False)   # the file on disk was known on 2024-01-11 ...
    monkeypatch.setattr(ltmod, "HOLDINGS_CSV", path)
    w = {"XIU.TO": 0.6, "ETF1": 0.4}
    late = look_through(w, holdings=H(SPLIT + SECTORS), universe=UNI, esg_flags=set(), as_of="2026-11-12")   # ... this one is dated later
    assert late["mode"] == "lookthrough"
    out = diversification(w, "2024-01-11", lookthrough=late, universe=UNI, market=mk({"XIU.TO": B, "ETF1": A}))
    assert out["countries"] == pytest.approx({"CAN": 0.6, "USA": 0.4}) and out["sectors"] == {}   # direct, not a rebuild from the file


# --- the real starter data and the local holdings (skip when absent; neither is ever committed) -------------
NEEDS_DATA = pytest.mark.skipif(not Path("data/starter/prices_daily.csv").exists(), reason="starter data not present")
NEEDS_HOLDINGS = pytest.mark.skipif(not ltmod.HOLDINGS_CSV.exists(), reason="local ETF holdings absent")
ROBERT = {"XIU.TO": 0.45, "XBB.TO": 0.35, "GLD": 0.10, "ZST.TO": 0.10}
ROBERT_AFTER = {"NVDA": 0.40, "XIU.TO": 0.27, "XBB.TO": 0.21, "GLD": 0.06, "ZST.TO": 0.06}

@NEEDS_DATA
def test_real_robert_after_the_move_nvidia_is_40_percent_of_the_money_and_about_90_percent_of_the_risk():
    after = risk_contributions(ROBERT_AFTER, "2026-11-12")                 # ledger 14: 89.6 % (the video script's 86 % was a draft)
    assert after["shares"]["NVDA"] == pytest.approx(0.896, abs=0.002) and list(after["shares"])[0] == "NVDA"
    assert 1.1 < after["bets"] < 1.25 and after["degenerate"] is False     # five lines, about one bet
    today = risk_contributions(ROBERT, "2026-11-12")
    assert today["shares"]["XIU.TO"] == pytest.approx(0.711, abs=0.005) and 2.3 < today["bets"] < 2.6
    assert after["as_of"] == "2026-11-12" and after["source"]

@NEEDS_DATA
def test_real_asset_returns_rebuild_the_judged_series():                   # ledger 12: the risk is measured on the series judged
    from tools.data import load_market
    m = load_market("2026-11-12")
    r = asset_returns(ROBERT_AFTER, "2026-11-12", market=m)
    values = portfolio_series(ROBERT_AFTER, as_of="2026-11-12", market=m)["values"]
    daily = r.to_numpy() @ np.array([ROBERT_AFTER[c] for c in r.columns])
    assert len(r) == len(values) - 1
    assert 100 * np.cumprod(1 + daily) == pytest.approx(values[1:], rel=1e-9)

@NEEDS_DATA
@NEEDS_HOLDINGS
def test_real_robert_money_and_risk_in_canada_before_and_after():          # NBDB's "too Canadian?" question
    today, after = diversification(ROBERT, "2026-11-12"), diversification(ROBERT_AFTER, "2026-11-12")
    assert today["currencies"] == pytest.approx({"CAD": 0.90, "USD": 0.10, "OTHER": 0.0})
    assert after["currencies"] == pytest.approx({"CAD": 0.54, "USD": 0.46, "OTHER": 0.0})
    assert today["can_risk_share"] == pytest.approx(0.85, abs=0.02) and after["can_risk_share"] == pytest.approx(0.09, abs=0.02)
    assert sum(after["countries"].values()) == pytest.approx(1.0, abs=2e-4) and len(after["sectors"]) == 5
    assert next(iter(after["sectors"])) == "Information Technology"       # NVDA direct plus its slice of the ETFs

@NEEDS_DATA
@NEEDS_HOLDINGS
def test_real_past_date_is_direct_holdings():                              # today's ETF snapshot is not a 2024 picture (red gate 3)
    out = diversification(ROBERT, "2024-06-28")
    assert out["countries"] == pytest.approx({"CAN": 0.90, "GLOBAL": 0.10}) and out["as_of"] == "2024-06-28"
    assert 0.0 < out["can_risk_share"] <= 1.0

@NEEDS_DATA
@NEEDS_HOLDINGS
def test_real_todays_look_through_is_not_used_for_a_past_decision():       # ledger 30: direct mode, flagged
    today = look_through(ROBERT, esg_flags=set(), as_of="2026-11-12")
    assert today["mode"] == "lookthrough"
    out = diversification(ROBERT, "2024-06-28", lookthrough=today)
    assert out["countries"] == pytest.approx({"CAN": 0.90, "GLOBAL": 0.10}) and out["as_of"] == "2024-06-28"
    assert "direct" in out["source"] and "after the decision date 2024-06-28" in out["source"]


# --- Task 20: the capacity line as a pure function (ruling R35; result_extras' `capacity` key) -------
DAYS = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]


def test_capacity_line_lowest_value_sessions_below_and_dates():
    out = capacity_line({"dates": DAYS, "values": [100, 90, 80, 84, 95, 101]}, 1000, 150)   # line: $850
    assert out == {"line": 850, "low_value": 800, "low_date": "2024-01-03", "sessions_below": 2,
                   "first_below": "2024-01-03", "last_below": "2024-01-04"}


def test_capacity_line_a_path_that_stays_above_has_no_dates_below():
    out = capacity_line({"dates": DAYS, "values": [100, 99, 98, 97, 96, 95]}, 1000, 150)
    assert (out["sessions_below"], out["first_below"], out["last_below"]) == (0, None, None)
    assert (out["low_value"], out["low_date"]) == (950, "2024-01-08")


def test_capacity_line_compares_to_the_cent():
    just_under = 85.0 * (1 - 1e-9)                       # $509,999.9995: $510,000.00 to the cent, at the line, not below
    out = capacity_line({"dates": DAYS[:2], "values": [100.0, just_under]}, 600_000, 90_000)
    assert out["sessions_below"] == 0 and out["low_value"] == 510_000


def test_capacity_line_rejects_a_capacity_outside_the_amount():
    for amount, capacity in ((1000, 0), (1000, 1000), (1000, -5)):
        with pytest.raises(ValueError):
            capacity_line({"dates": DAYS, "values": [100] * 6}, amount, capacity)


@NEEDS_DATA
def test_real_robert_capacity_line_reproduces_the_saved_run():          # 16:50 update: same numbers as result_extras
    out = capacity_line(portfolio_series(ROBERT_AFTER, as_of="2026-11-12", union=True), 600_000, 90_000)
    assert out == {"line": 510_000, "low_value": 408_174, "low_date": "2022-10-14", "sessions_below": 188,
                   "first_below": "2022-04-22", "last_below": "2023-01-19"}
    assert capacity_line(portfolio_series(ROBERT, as_of="2026-11-12", union=True), 600_000, 90_000)["sessions_below"] == 0
