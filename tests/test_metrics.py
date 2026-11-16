"""Finance truth for the portfolio metrics (workstream C, plan C Task 6) and the issuer reconciliation.

the data lead's tools.metrics, tools.portfolio and tools.risk must pass this file; the implementer fixes the code, never
these tests. Part 1 pins the definitions (peak, trough, calendar-day recovery, CAGR over calendar days / 365.25,
volatility, Sharpe, the drawdown series, the worst rolling drop, calendar years, the risk share and the count of
independent bets) on synthetic series. Part 2 pins the spec section 3 values on the real starter data (Robert today
and after the 40 % NVDA move, Mateo, Amira, the CNQ.TO special distribution counted once). Part 3 reconciles our
total returns with the figures the issuers publish; `reconciliation_rows()` and `reconciliation_markdown()` feed the
table of docs/finance_methods.md (plan C Task 10), so a published number is always a tested number.

The real-data cases skip without data/starter/ (it is never committed). Everything else runs offline.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

NEEDS_DATA = pytest.mark.skipif(not Path("data/starter/prices_daily.csv").exists(), reason="starter data not present")


# --- 1. the definitions, on synthetic series -----------------------------------------------------------------
def ser(values, start="2024-01-01"):
    return {"dates": pd.date_range(start, periods=len(values), freq="D").strftime("%Y-%m-%d").tolist(), "values": values}


def test_drawdown_peak_trough_and_calendar_day_recovery():
    m = pytest.importorskip("tools.metrics").risk_metrics(ser([100, 90, 80, 90, 100, 110]))
    assert m["max_drawdown"] == pytest.approx(-0.20)
    assert (m["peak_date"], m["trough_date"], m["recovery_days"], m["days_since_trough"]) == ("2024-01-01", "2024-01-03", 2, 3)


def test_recovery_and_days_since_trough_count_calendar_days_across_a_weekend():
    # Thu 4, Fri 5, Mon 8, Tue 9 January 2024. The trough is Fri 5; the value is back at the peak on Mon 8 (3 calendar
    # days, one row later) and the series ends Tue 9 (4 calendar days, two rows later). A count of rows reads 1 and 2.
    s = {"dates": ["2024-01-04", "2024-01-05", "2024-01-08", "2024-01-09"], "values": [100, 80, 100, 110]}
    m = pytest.importorskip("tools.metrics").risk_metrics(s)
    assert (m["peak_date"], m["trough_date"], m["recovery_days"], m["days_since_trough"]) == ("2024-01-04", "2024-01-05", 3, 4)


def test_not_recovered_is_none():
    assert pytest.importorskip("tools.metrics").risk_metrics(ser([100, 80, 90]))["recovery_days"] is None


def test_max_drawdown_is_from_the_running_high_not_from_the_first_value():
    # [100, 80, 120, 90]: the deepest fall is 120 -> 90 (-25 %); measured from the first value it would be 100 -> 80 (-20 %).
    m = pytest.importorskip("tools.metrics").risk_metrics(ser([100, 80, 120, 90]))
    assert m["max_drawdown"] == pytest.approx(-0.25)
    assert (m["peak_date"], m["trough_date"], m["recovery_days"]) == ("2024-01-03", "2024-01-04", None)


def test_cagr_volatility_sharpe_definitions():
    tm = pytest.importorskip("tools.metrics")
    assert tm.risk_metrics({"dates": ["2022-01-01", "2024-01-01"], "values": [100, 121]})["cagr"] == pytest.approx(1.21 ** (365.25 / 730) - 1)
    s = ser([100, 101, 100, 102, 101]); r = pd.Series(s["values"]).pct_change().dropna()
    m = tm.risk_metrics(s, rf=0.03)
    assert m["volatility"] == pytest.approx(r.std(ddof=1) * 252 ** 0.5)
    assert m["sharpe"] == pytest.approx((m["cagr"] - 0.03) / m["volatility"])


def test_drawdown_series_rolling_drop_and_calendar_years():
    tm = pytest.importorskip("tools.metrics")
    assert tm.drawdown_series(ser([100, 80, 120, 90]))["values"] == pytest.approx([0.0, -0.2, 0.0, -0.25])
    assert tm.worst_rolling_drop(ser([200] + [100] * 400 + [90]))["value"] == pytest.approx(-0.50)
    assert tm.worst_rolling_drop(ser([100] * 400 + [90]))["value"] == pytest.approx(-0.10)
    s = {"dates": ["2022-01-03", "2022-12-30", "2023-12-29"], "values": [100, 110, 99]}
    assert tm.calendar_year_returns(s) == pytest.approx({2022: 0.10, 2023: -0.10})


def test_worst_rolling_drop_is_a_fall_from_a_high_inside_the_window():
    # The fall 100 -> 60 happens on day 1 and the value is back at 100 for the next 400 days. A point-to-point return over
    # 365 days (value / value 365 days earlier - 1) never sees it and reads 0.0 here; the contract's fall is -40 %.
    w = pytest.importorskip("tools.metrics").worst_rolling_drop(ser([100, 60] + [100] * 400))
    assert w["value"] == pytest.approx(-0.40)
    assert (w["peak_date"], w["trough_date"]) == ("2024-01-01", "2024-01-02")


def test_risk_share_sums_to_one_and_counts_independent_bets():
    rk, data = pytest.importorskip("tools.risk"), pytest.importorskip("tools.data")
    # Daily vol 1 % and 2 %, weights 2/3 and 1/3 (inverse to vol): the risk splits 50/50 while the money does not, so a
    # risk share that echoes the money fails. With equal vols at 50/50 the two eigenvalues of the sample covariance were
    # only 6 % apart, noise rotated the principal axes and the Meucci ENB read 1.08 on seed 1; unequal vols keep the axes
    # on the assets (ledger section 26).
    # 10,000 returns, not 2,000: a variance estimated on 2,000 days carries about 3 % error and the 0.5 +- 0.02 bound
    # failed on 42 of 500 seeds; on 10,000 it holds on 500 of 500 (max deviation 0.0148; ENB within 0.0054 of 2.0).
    # This fixture cannot tell the count of bets from the risk shares: the retired 1 / sum(RC^2) and a covariance-blind
    # count also read 2.0 on it. So C = A + noise of a tenth of A's vol is a near-duplicate of A, drawn after b (a and b
    # keep their draws): the 50/50 mix of A and C splits its risk 50 / 50 like two real bets, yet it is one bet (Meucci
    # ENB 1.00, 1 / sum(RC^2) 2.00; ledger sections 14 and 26: never switch back to 1 / sum(RC^2)).
    n = 10_000
    rng = np.random.default_rng(1)
    a, b = rng.normal(0, 0.01, n), rng.normal(0, 0.02, n)
    c = a + rng.normal(0, 0.001, n)
    idx = pd.bdate_range(end="2025-12-31", periods=n + 1)
    px = pd.DataFrame({"A": 100 * np.cumprod(np.r_[1, 1 + a]), "B": 100 * np.cumprod(np.r_[1, 1 + b]),
                       "C": 100 * np.cumprod(np.r_[1, 1 + c])}, index=idx)
    out = rk.risk_contributions({"A": 2 / 3, "B": 1 / 3}, idx[-1].strftime("%Y-%m-%d"), market=data.make_market(px))
    assert sum(out["shares"].values()) == pytest.approx(1.0)
    assert out["shares"] == pytest.approx({"A": 0.5, "B": 0.5}, abs=0.02) and out["bets"] == pytest.approx(2.0, abs=0.05)
    one = rk.risk_contributions({"A": 1.0}, idx[-1].strftime("%Y-%m-%d"), market=data.make_market(px))
    assert one["shares"] == pytest.approx({"A": 1.0}) and one["bets"] == pytest.approx(1.0)
    twin = rk.risk_contributions({"A": 0.5, "C": 0.5}, idx[-1].strftime("%Y-%m-%d"), market=data.make_market(px))
    assert twin["bets"] < 1.1, f"a near-duplicate pair is one bet, not {twin['bets']:.2f} (Meucci ENB, ledger section 26)"


# --- 2. the spec section 3 values on the real starter data ----------------------------------------------------
ROBERT = {"XIU.TO": 0.45, "XBB.TO": 0.35, "GLD": 0.10, "ZST.TO": 0.10}
ROBERT_AFTER = {"NVDA": 0.40, "XIU.TO": 0.27, "XBB.TO": 0.21, "GLD": 0.06, "ZST.TO": 0.06}


def _metrics(weights, **kw):
    tp, tm = pytest.importorskip("tools.portfolio"), pytest.importorskip("tools.metrics")
    return tm.risk_metrics(tp.portfolio_series(weights, **kw))


@NEEDS_DATA
def test_robert_today_and_after_on_real_data():
    today, after = _metrics(ROBERT), _metrics(ROBERT_AFTER)
    assert today["max_drawdown"] == pytest.approx(-0.1061, abs=0.001) and abs(today["recovery_days"] - 416) <= 2
    assert after["max_drawdown"] == pytest.approx(-0.3452, abs=0.001)
    assert (after["peak_date"], after["trough_date"]) == ("2021-11-29", "2022-10-14")
    assert (after["cagr"], today["cagr"]) == (pytest.approx(0.2522, abs=0.002), pytest.approx(0.0873, abs=0.002))


@NEEDS_DATA
def test_the_move_breaks_the_floor_again_without_2022():
    m = _metrics(ROBERT_AFTER, start="2023-01-01")
    assert m["max_drawdown"] == pytest.approx(-0.1692, abs=0.001) and m["trough_date"] == "2025-04-08"


@NEEDS_DATA
def test_mateo_and_amira_drawdowns():
    assert _metrics({"XIU.TO": 0.35, "XBB.TO": 0.35, "CNQ.TO": 0.08, "MSFT": 0.10, "GLD": 0.12})["max_drawdown"] == pytest.approx(-0.1143, abs=0.001)
    amira = {"NVDA": 0.15, "QQQ": 0.15, "SHOP.TO": 0.10, "BTC-USD": 0.15, "XIU.TO": 0.30, "XBB.TO": 0.15}
    assert _metrics(amira)["max_drawdown"] == pytest.approx(-0.4135, abs=0.002)


@NEEDS_DATA
def test_cnq_special_distribution_is_counted_once():
    local = pytest.importorskip("tools.data").load_market("2026-11-12")["local"]["CNQ.TO"]
    assert local[pd.Timestamp("2022-08-22")] / local[pd.Timestamp("2022-08-19")] - 1 == pytest.approx(0.0067, abs=0.0005)


# --- 3. our total returns against the figures the issuers publish ----------------------------------------------
# Read on the fund pages on 2026-11-14, in the issuer's own basis: iShares Canada shows NAV returns, State Street
# shows market-value returns; they are the only ones the pages show. Sources: XIU.TO
# https://www.blackrock.com/ca/investors/en/products/239832/ishares-sptsx-60-index-etf , XBB.TO
# https://www.blackrock.com/ca/investors/en/products/239493/ishares-core-canadian-universe-bond-index-etf (both in
# docs/research/etf-holdings-sources.md), SPY https://www.ssga.com/us/en/intermediary/etfs/state-street-spdr-sp-500-etf-trust-spy ,
# GLD https://www.ssga.com/us/en/intermediary/etfs/spdr-gold-shares-gld . The pages publish no calendar-year table,
# so these trailing windows replace the calendar years of spec section 15 (said in plan C Task 10).
# Ours = the dataset's adjusted close in the listing currency (no FX): the last price dated on or before the start
# date over the last price dated on or before the end date; a "3 years a year" row is annualized, (1 + r) ** (1/3) - 1.
# Columns: ETF, start, end, window as the issuer labels it, issuer figure in percentage points.
ISSUER = [
    ("XIU.TO", "2025-12-31", "2026-11-12", "YTD to 2026-11-12, NAV", 17.93),
    ("XBB.TO", "2025-12-31", "2026-11-12", "YTD to 2026-11-12, NAV", 0.69),
    ("SPY", "2025-12-31", "2026-10-31", "YTD to 2026-10-31, market", 11.67),
    ("SPY", "2025-10-31", "2026-10-31", "1 year to 2026-10-31, market", 11.97),
    ("SPY", "2025-12-31", "2026-09-30", "YTD to 2026-09-30, market", 12.66),
    ("SPY", "2025-09-30", "2026-09-30", "1 year to 2026-09-30, market", 15.66),
    ("SPY", "2023-10-31", "2026-10-31", "3 years a year to 2026-10-31, market", 23.25),
    ("GLD", "2025-12-31", "2026-10-31", "YTD to 2026-10-31, market", -10.23),
    ("GLD", "2025-10-31", "2026-10-31", "1 year to 2026-10-31, market", -3.35),
    ("GLD", "2025-12-31", "2026-09-30", "YTD to 2026-09-30, market", -3.90),
    ("GLD", "2025-09-30", "2026-09-30", "1 year to 2026-09-30, market", 7.14),
    ("GLD", "2023-10-31", "2026-10-31", "3 years a year to 2026-10-31, market", 24.54),
]
TOLERANCE_PP = 0.15   # independent recompute, Sat 19:00: the largest gap was 0.06 pp; the CNQ.TO-type error is 2.1 pp


def reconciliation_rows():
    local = pytest.importorskip("tools.data").load_market("2026-11-12")["local"]
    rows = []
    for etf, start, end, window, issuer in ISSUER:
        px = local[etf].dropna()
        r = px[:end].iloc[-1] / px[:start].iloc[-1] - 1
        if window.startswith("3 years"):
            r = (1 + r) ** (1 / 3) - 1
        ours = round(100 * r, 2)
        rows.append({"etf": etf, "window": window, "basis": "NAV" if "NAV" in window else "market price",
                     "issuer": issuer, "ours": ours, "diff": round(ours - issuer, 2), "tolerance": TOLERANCE_PP,
                     "ok": abs(ours - issuer) <= TOLERANCE_PP})
    return rows


def reconciliation_markdown():
    head = "| ETF | Window (issuer basis) | Issuer % | Ours % | Gap pp | Within 0.15 pp |\n|---|---|---:|---:|---:|---|\n"
    return head + "".join(f"| {r['etf']} | {r['window']} | {r['issuer']:.2f} | {r['ours']:.2f} | {r['diff']:+.2f} | {'yes' if r['ok'] else 'NO'} |\n"
                          for r in reconciliation_rows())


@NEEDS_DATA
def test_total_returns_reconcile_with_issuer_published_figures():
    bad = [r for r in reconciliation_rows() if not r["ok"]]
    assert not bad, bad
