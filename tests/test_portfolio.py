"""Task 3 tests: tools/portfolio.py (spec section 10: the one weight operator, constant weights).

Offline: synthetic bundles from tools.data.make_market. The real-data case skips when
data/starter/ is absent.
"""
import numpy as np
import pandas as pd
import pytest

from tools.data import DATA_DIR, DATASET_END, load_market, make_market
from tools.portfolio import (apply_change, normalize, parse_weights, portfolio_series,
                             series_from_market)

TICKERS_31 = (
    "RY.TO TD.TO MFC.TO ENB.TO CNQ.TO CNR.TO FTS.TO ATD.TO SHOP.TO CSU.TO "
    "AAPL MSFT NVDA GOOGL AMZN TSLA JPM JNJ PG XOM "
    "XIU.TO SPY QQQ ESGV XBB.TO ZST.TO AGG TLT GLD BTC-USD ETH-USD").split()
UNIVERSE_31 = pd.DataFrame({"ticker": TICKERS_31})
ROBERT = {"XIU.TO": 0.45, "XBB.TO": 0.35, "GLD": 0.10, "ZST.TO": 0.10}
REAL = pytest.mark.skipif(not (DATA_DIR / "prices_daily.csv").exists(),
                          reason="data/starter/ is absent")


def prices_frame(cols):
    """Consecutive business days from 2024-01-01; None becomes NaN."""
    n = len(next(iter(cols.values())))
    data = {k: [np.nan if v is None else float(v) for v in vals] for k, vals in cols.items()}
    return pd.DataFrame(data, index=pd.bdate_range("2024-01-01", periods=n))


# --- parse_weights and normalize -----------------------------------------------------------------
def test_parse_weights_flags_unknown_and_reads_percent():
    out = parse_weights([{"ticker": "xiu.to", "weight": 45}, {"ticker": "ZAG.TO", "weight": 35},
                         {"ticker": "GLD", "weight": 20}], universe=UNIVERSE_31)
    assert out["weights"] == {"XIU.TO": 0.45, "GLD": 0.20}
    assert out["unknown"] == ["ZAG.TO"] and out["sum"] == pytest.approx(0.65)
    assert out["source"] and out["as_of"] == DATASET_END


def test_parse_weights_fractions_duplicates_blank_rows_and_nonpositive():
    rows = [{"ticker": " nvda ", "weight": 0.25}, {"ticker": "NVDA", "weight": 0.25},
            {"ticker": "SPY", "weight": 0.5}, {"ticker": "GLD", "weight": 0},
            {"ticker": "TLT", "weight": -0.1}, {"ticker": "", "weight": 0.3},
            {"ticker": "AGG", "weight": None}, {"ticker": float("nan"), "weight": 0.2}, {"weight": 0.1}]
    out = parse_weights(rows, universe=UNIVERSE_31)
    assert out["weights"] == {"NVDA": 0.5, "SPY": 0.5} and out["unknown"] == []
    assert out["sum"] == pytest.approx(1.0)
    with pytest.raises(ValueError):
        parse_weights([{"ticker": "SPY", "weight": "lots"}], universe=UNIVERSE_31)
    assert parse_weights([{"ticker": "SPY", "weight": "60%"}, {"ticker": "GLD", "weight": "40"}],
                         universe=UNIVERSE_31)["weights"] == {"SPY": 0.6, "GLD": 0.4}


def test_normalize_scales_to_one_and_refuses_an_empty_portfolio():
    out = normalize({"A": 30, "B": 50, "C": 0, "D": -1})
    assert out == pytest.approx({"A": 0.375, "B": 0.625}) and sum(out.values()) == pytest.approx(1)
    with pytest.raises(ValueError):
        normalize({"A": 0.0})


# --- the one weight operator ---------------------------------------------------------------------
def test_set_on_a_ticker_already_held():          # section 15 weight operator test
    w = apply_change({"NVDA": 0.15, "XIU.TO": 0.85}, {"op": "set", "ticker": "NVDA", "weight": 0.40})
    assert w == pytest.approx({"NVDA": 0.40, "XIU.TO": 0.60}) and sum(w.values()) == pytest.approx(1)


def test_set_robert_request():
    w = apply_change(ROBERT, {"op": "set", "ticker": "NVDA", "weight": 0.40})
    assert w == pytest.approx({"NVDA": 0.40, "XIU.TO": 0.27, "XBB.TO": 0.21, "GLD": 0.06, "ZST.TO": 0.06})
    assert sum(w.values()) == pytest.approx(1, abs=1e-12) and ROBERT["XIU.TO"] == 0.45   # input untouched


def test_add_and_replace():
    assert apply_change({"NVDA": 0.10, "SPY": 0.90}, {"op": "add", "ticker": "NVDA", "weight": 0.10}) == pytest.approx({"NVDA": 0.20, "SPY": 0.80})
    assert apply_change({"CNQ.TO": 0.08, "XIU.TO": 0.92}, {"op": "replace", "ticker": "ESGV", "from_ticker": "CNQ.TO"}) == pytest.approx({"ESGV": 0.08, "XIU.TO": 0.92})
    assert apply_change({"CNQ.TO": 0.08, "XIU.TO": 0.92}, {"op": "replace", "ticker": "XIU.TO", "from_ticker": "CNQ.TO"}) == pytest.approx({"XIU.TO": 1.0})
    assert apply_change({"SPY": 0.9, "NVDA": 0.1}, {"op": "add", "ticker": "TSLA", "weight": 0.1}) == pytest.approx({"SPY": 0.81, "NVDA": 0.09, "TSLA": 0.1})


def test_operator_edge_cases():
    assert apply_change(ROBERT, {"op": "set", "ticker": "NVDA", "weight": 1.0}) == {"NVDA": 1.0}
    assert "NVDA" not in apply_change({"NVDA": 0.2, "SPY": 0.8}, {"op": "set", "ticker": "NVDA", "weight": 0.0})
    with pytest.raises(ValueError):
        apply_change({"NVDA": 1.0}, {"op": "set", "ticker": "NVDA", "weight": 0.4})
    assert apply_change({"NVDA": 1.0}, {"op": "set", "ticker": "NVDA", "weight": 1.0}) == {"NVDA": 1.0}
    assert apply_change({"SPY": 0.7, "GLD": 0.3}, {"op": "add", "ticker": "GLD", "weight": 0.7}) == pytest.approx({"GLD": 1.0})   # 0.3 + 0.7 float dust


def test_operator_refuses_impossible_changes_with_a_plain_sentence():
    held = {"NVDA": 0.6, "SPY": 0.4}
    bad = [{"op": "add", "ticker": "NVDA", "weight": 0.5},                  # 110 %
           {"op": "set", "ticker": "NVDA", "weight": 1.2},
           {"op": "set", "ticker": "NVDA", "weight": -0.1},
           {"op": "set", "ticker": "NVDA", "weight": float("nan")},
           {"op": "set", "ticker": "NVDA"},                                   # no weight
           {"op": "replace", "ticker": "TSLA", "from_ticker": "AAPL"},       # AAPL not held
           {"op": "replace", "ticker": "TSLA"},                              # no from_ticker
           {"op": "swap", "ticker": "NVDA", "weight": 0.1},
           {"op": "set", "weight": 0.1}]
    for change in bad:
        with pytest.raises(ValueError):
            apply_change(held, change)
    with pytest.raises(ValueError):
        apply_change({"NVDA": 0.6, "SPY": 0.1}, {"op": "set", "ticker": "NVDA", "weight": 0.5})   # input sums to 0.7
    with pytest.raises(ValueError):
        apply_change({}, {"op": "set", "ticker": "NVDA", "weight": 0.5})


def test_every_slider_step_sums_to_one_and_keeps_the_requested_weight():
    for k in range(0, 101):
        w = apply_change(ROBERT, {"op": "set", "ticker": "NVDA", "weight": k / 100})
        assert sum(w.values()) == pytest.approx(1, abs=1e-12) and w.get("NVDA", 0.0) == pytest.approx(k / 100)
        assert all(v > 0 for v in w.values())


def test_operator_properties_on_random_portfolios():
    """Seeded fuzz: sums to 1, the requested weight is exact, the others keep their ratios."""
    rng = np.random.default_rng(7)
    for _ in range(300):
        names = [str(t) for t in rng.choice(TICKERS_31, size=int(rng.integers(2, 8)), replace=False)]
        held = normalize(dict(zip(names, rng.uniform(0.01, 1.0, len(names)))))
        target, other = str(rng.choice(TICKERS_31)), names[0]
        x = float(rng.uniform(0.0, 0.99))
        out = apply_change(held, {"op": "set", "ticker": target, "weight": x})
        assert sum(out.values()) == pytest.approx(1, abs=1e-12) and out.get(target, 0.0) == pytest.approx(x, abs=1e-12)
        keep = [t for t in names if t != target]
        if len(keep) >= 2:                                   # the pro-rata rule: ratios between the others never change
            assert out[keep[0]] / out[keep[1]] == pytest.approx(held[keep[0]] / held[keep[1]], rel=1e-9)
        room = 1.0 - held.get(target, 0.0)
        y = float(rng.uniform(0.0, room))
        assert apply_change(held, {"op": "add", "ticker": target, "weight": y}) == pytest.approx(
            apply_change(held, {"op": "set", "ticker": target, "weight": held.get(target, 0.0) + y}), abs=1e-12)
        swapped = apply_change(held, {"op": "replace", "ticker": target, "from_ticker": other})
        assert sum(swapped.values()) == pytest.approx(1, abs=1e-12)
        assert other == target or other not in swapped
        assert swapped[target] == pytest.approx(held[other] + (held.get(target, 0.0) if target != other else 0.0), abs=1e-12)


# --- constant-weight series ----------------------------------------------------------------------
def test_constant_weights_rebalance_daily():
    # A doubles then halves, B flat; 50/50 rebalanced: 100 -> 150 -> 112.5 (buy-and-hold would give 100)
    m = make_market(prices_frame({"A": [1, 2, 1], "B": [1, 1, 1]}))
    assert series_from_market({"A": 0.5, "B": 0.5}, m).tolist() == pytest.approx([100, 150, 112.5])


def test_day_without_any_held_exchange_open_is_dropped():
    p = prices_frame({"A": [1, 1.1, 1.1, 1.2]})
    traded = p.notna(); traded.iloc[2] = False
    s = series_from_market({"A": 1.0}, make_market(p, traded=traded))
    assert len(s) == 3


def test_unfilled_gap_counts_as_zero_return():
    s = series_from_market({"A": 0.5, "B": 0.5}, make_market(prices_frame({"A": [1, None, 1.2], "B": [1, 1, 1]})))
    assert s.tolist() == pytest.approx([100, 100, 110])   # the move across the gap is booked when trading resumes


def test_series_start_base_and_unknown_or_unbalanced_weights():
    m = make_market(prices_frame({"A": [1, 1, 2, 4], "B": [1, 1, 1, 1]}))
    s = series_from_market({"A": 0.5, "B": 0.5}, m, start="2024-01-03")
    assert s.index[0] == pd.Timestamp("2024-01-03") and s.tolist() == pytest.approx([100, 150])
    assert series_from_market({"A": 1.0}, m, start="2030-01-01").empty
    with pytest.raises(ValueError, match="Unknown ticker: ZZZ"):
        series_from_market({"A": 0.5, "ZZZ": 0.5}, m)
    with pytest.raises(ValueError):
        series_from_market({"A": 0.5, "B": 0.2}, m)                 # sums to 70 %


def test_a_move_on_a_dropped_day_is_booked_when_trading_resumes():
    # USD line on a US holiday: the exchange is closed (day dropped) but the CAD price moved with the FX
    p = prices_frame({"U": [10.0, 11.0, 12.0]})
    traded = p.notna(); traded.iloc[1] = False
    s = series_from_market({"U": 1.0}, make_market(p, traded=traded))
    assert s.index.tolist() == [p.index[0], p.index[2]] and s.tolist() == pytest.approx([100, 120])


def test_portfolio_series_contract_cut_and_as_of():
    m = make_market(prices_frame({"A": [1, 2, 3, 4, 5]}))
    out = portfolio_series({"A": 1.0}, "2024-01-02", "2024-01-04", as_of="2024-01-03", market=m)
    assert out["dates"] == ["2024-01-02", "2024-01-03"] and out["values"] == pytest.approx([100, 150])
    assert out["as_of"] == "2024-01-03" and out["source"] and set(out) == {"dates", "values", "source", "as_of"}
    full = portfolio_series({"A": 1.0}, as_of="2024-01-05", market=m)
    assert full["dates"][0] == "2024-01-01" and full["values"][0] == 100.0 and len(full["dates"]) == 5


@REAL
def test_real_series_for_robert_starts_at_100_and_ends_at_the_as_of_cut():
    out = portfolio_series(ROBERT, as_of="2025-01-31")
    assert out["values"][0] == 100.0 and out["dates"][-1] <= "2025-01-31"
    assert out["dates"] == sorted(out["dates"]) and all(np.isfinite(out["values"]))
    assert len(portfolio_series(ROBERT, as_of=DATASET_END)["dates"]) > len(out["dates"])


@REAL
def test_real_single_line_series_is_the_exact_cad_price_ratio_across_us_holidays():
    # NVDA-only drops the 27 days when only the TSX traded; their USD/CAD moves must still be booked
    m = load_market(DATASET_END)
    s = series_from_market({"NVDA": 1.0}, m)
    p = m["prices"]["NVDA"]
    assert len(s) == 1255 < len(m["calendar"]) == 1282
    assert s.iloc[-1] == pytest.approx(100 * p.iloc[-1] / p.iloc[0], rel=1e-9)


@REAL
def test_real_robert_today_and_after_match_the_spec_preview_drawdowns():
    # spec section 3 preview (constant weights): today about -10.6 %, with 40 % NVDA about -34.5 %
    m = load_market(DATASET_END)
    for weights, expected in ((ROBERT, -0.106), (apply_change(ROBERT, {"op": "set", "ticker": "NVDA", "weight": 0.40}), -0.345)):
        s = series_from_market(weights, m)
        assert len(s) == 1282 and (s / s.cummax() - 1).min() == pytest.approx(expected, abs=0.0005)


# --- Task 4: the Task 3 review hardening (amendments a, b, c) --------------------------------------
def test_held_tickers_are_stripped_and_upper_cased_so_no_duplicate_line():
    out = apply_change({"nvda": 0.2, " spy ": 0.8}, {"op": "set", "ticker": "NVDA", "weight": 0.4})
    assert set(out) == {"NVDA", "SPY"} and out == pytest.approx({"NVDA": 0.4, "SPY": 0.6})
    out = apply_change({"nvda": 0.1, "SPY": 0.9}, {"op": "add", "ticker": "nvda", "weight": 0.1})
    assert set(out) == {"NVDA", "SPY"} and out == pytest.approx({"NVDA": 0.2, "SPY": 0.8})
    out = apply_change({"cnq.to": 0.08, "xiu.to": 0.92}, {"op": "replace", "ticker": "xiu.to", "from_ticker": "CNQ.TO"})
    assert out == {"XIU.TO": pytest.approx(1.0)}
    # two spellings of one ticker are one line (their weights add up), not two lines
    out = apply_change({"nvda": 0.1, "NVDA": 0.2, "SPY": 0.7}, {"op": "set", "ticker": "SPY", "weight": 0.5})
    assert set(out) == {"NVDA", "SPY"} and out == pytest.approx({"NVDA": 0.5, "SPY": 0.5})


def test_a_none_or_unreadable_held_weight_is_a_value_error_not_a_type_error():
    change = {"op": "set", "ticker": "NVDA", "weight": 0.4}
    for bad in ({"NVDA": None, "SPY": 1.0}, {"NVDA": "lots", "SPY": 1.0}, {"NVDA": [0.5], "SPY": 0.5}):
        with pytest.raises(ValueError):
            apply_change(bad, change)
    with pytest.raises(ValueError):
        series_from_market({"A": None, "B": 1.0}, make_market(prices_frame({"A": [1, 2], "B": [1, 1]})))


def test_the_series_reads_lower_case_held_tickers_like_the_operator_does():
    m = make_market(prices_frame({"A": [1, 2, 3], "B": [1, 1, 1]}))
    assert series_from_market({"a": 0.5, " b ": 0.5}, m).tolist() == pytest.approx([100, 150, 187.5])


def test_parse_weights_rejects_infinite_and_nan_text_but_still_drops_blank_cells():
    for bad in ("inf", "-inf", "Infinity", "nan", "NaN%", float("inf"), float("-inf")):
        with pytest.raises(ValueError, match="Cannot read the weight for SPY"):
            parse_weights([{"ticker": "SPY", "weight": bad}, {"ticker": "GLD", "weight": 50}], universe=UNIVERSE_31)
    kept = parse_weights([{"ticker": "SPY", "weight": 60}, {"ticker": "GLD", "weight": float("nan")},
                          {"ticker": "AGG", "weight": ""}, {"ticker": "TLT", "weight": None}, {"ticker": "QQQ", "weight": 40}],
                         universe=UNIVERSE_31)
    assert kept["weights"] == {"SPY": 0.6, "QQQ": 0.4} and kept["sum"] == pytest.approx(1.0)   # blank cells are not rows
    with pytest.raises(ValueError):
        parse_weights([{"ticker": "ZZZ", "weight": "inf"}], universe=UNIVERSE_31)              # unknown ticker too


def test_portfolio_series_labels_as_of_with_the_bundle_end_when_the_bundle_ends_earlier():
    cut = make_market(prices_frame({"A": [1, 2, 3, 4, 5]}), as_of="2024-01-03")
    out = portfolio_series({"A": 1.0}, market=cut)                    # the default as_of is DATASET_END
    assert out["dates"][-1] == "2024-01-03" and out["as_of"] == "2024-01-03"
    full = make_market(prices_frame({"A": [1, 2, 3, 4, 5]}))
    assert portfolio_series({"A": 1.0}, as_of="2024-01-03", market=full)["as_of"] == "2024-01-03"   # asked earlier: kept
    assert portfolio_series({"A": 1.0}, as_of="2030-01-01", market=full)["as_of"] == "2024-01-05"   # asked later: the bundle end


def test_portfolio_series_label_is_the_last_data_date_not_the_cutoff_of_a_load_market_bundle():
    """Task 4 review minor 4 (ruling d): a load_market bundle's `as_of` is the cutoff it was built for;
    the series says the last date actually in the data."""
    fake = "data/fake/starter"
    wide = load_market("2030-01-01", data_dir=fake)
    assert wide["as_of"] == "2030-01-01" and wide["calendar"][-1] == pd.Timestamp(DATASET_END)
    out = portfolio_series({"XIU.TO": 1.0}, as_of="2030-01-01", market=wide)
    assert out["dates"][-1] == DATASET_END and out["as_of"] == DATASET_END       # not 2030-01-01
    # a weekend as_of is labelled with the last day it can see, whatever the width of the bundle
    now = load_market(DATASET_END, data_dir=fake)
    assert portfolio_series({"XIU.TO": 1.0}, as_of="2026-11-14", market=now)["as_of"] == DATASET_END
    mid = portfolio_series({"XIU.TO": 1.0}, as_of="2025-03-02", market=now)       # a Sunday, a wider bundle
    narrow = portfolio_series({"XIU.TO": 1.0}, as_of="2025-03-02", market=load_market("2025-03-02", data_dir=fake))
    assert mid["as_of"] == narrow["as_of"] == mid["dates"][-1] == "2025-02-28"
    before = portfolio_series({"XIU.TO": 1.0}, as_of="2021-11-01", market=now)    # before any data: the request
    assert before["dates"] == [] and before["as_of"] == "2021-11-01"
