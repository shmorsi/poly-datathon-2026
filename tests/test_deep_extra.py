"""Tasks 15 and 16 tests: tools/deep.py, the deep-history proxy panel and the replay, the proxy check and the Result
fragment (spec section 23, ledger 17 and 30; plan A Tasks 15 and 16; the Task 16 tests start at the "Task 16" comment).

Offline: every source file is a small synthetic fixture written to tmp_path (the real downloads are
local only, licences). The first five tests are the plan's; the rest pin the real files' layouts
that the plan's tiny fixture does not show (header padding, placeholders, gaps, byte-order mark).
"""
import zipfile
import pandas as pd, pytest
from tools.deep import (LADDER, PROXY_IDS, build_panel, load_panel, load_proxy_map, par_bond_return)

def _zip(path, member, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z: z.writestr(member, text)

def _french(cols, vals, months=("197612", "197701", "197702")):
    body = "\n".join(f"{m}," + ",".join(f"{v:.2f}" for v in row) for m, row in zip(months, vals))
    junk = "\n".join(f"{m}," + ",".join("9.99" for _ in cols) for m in months)
    hdr = "," + ",".join(cols)
    return (f"This file was created using the 202609 CRSP database.\n\n  Average Value Weighted Returns -- Monthly\n"
            f"{hdr}\n{body}\n\n  Average Equal Weighted Returns -- Monthly\n{hdr}\n{junk}\n")

def make_raw(root):
    _zip(root / "french_factors/F-F_Research_Data_Factors_CSV.zip", "F-F_Research_Data_Factors.csv",
         _french(["Mkt-RF", "SMB", "HML", "RF"], [[1.0, 0, 0, 0.5], [-2.0, 0, 0, 0.5], [3.0, 0, 0, 0.5]]))
    _zip(root / "french_12/12_Industry_Portfolios_CSV.zip", "12_Industry_Portfolios.csv",
         _french(["NoDur", "BusEq"], [[0, 1.0], [0, -1.0], [0, 2.0]]))
    cols = ["Chips", "Softw", "Hardw", "Rtail", "Autos", "Banks", "Drugs", "Hshld", "Oil"]
    _zip(root / "french_49/49_Industry_Portfolios_CSV.zip", "49_Industry_Portfolios.csv",
         _french(cols, [[10.0] * 9, [-20.0] * 9, [-99.99] + [5.0] * 8]))
    _zip(root / "french_countries/F-F_International_Countries.zip", "Canada.Dat",
         "\n     Value-Weight Dollar Returns      All 4 Data Items Not Reqd\n          Mkt   High\n197701   9.00   9.00\n"
         "197702   9.00   9.00\n\n     Value-Weight Local  Returns      All 4 Data Items Not Reqd\n          Mkt   High\n"
         "197701   2.00   1.00\n197702  -4.00   1.00\n")
    ys = {"v122558": [4, 4, 4], "v122485": [4, 4, 4], "v122486": [4, 4, 4], "v122487": [4, 5, 5], "v122531": [3, 3, 3]}
    _zip(root / "statcan_10100122/10100122-eng.zip", "10100122.csv", "REF_DATE,GEO,VECTOR,VALUE\n" + "".join(
        f"{d},Canada,{v},{y}\n" for v, row in ys.items() for d, y in zip(["1976-12", "1977-01", "1977-02"], row)))
    _zip(root / "statcan_10100125/10100125-eng.zip", "10100125.csv", "REF_DATE,GEO,VECTOR,VALUE\n"
         "1976-11,Canada,v122620,100\n1976-12,Canada,v122620,110\n1977-01,Canada,v122620,121\n"
         "1976-11,Canada,v122628,6.0\n1976-12,Canada,v122628,6.0\n1977-01,Canada,v122628,6.0\n")
    for sid, rows in {"DEXCAUS": [("1976-12-31", 1.0), ("1977-01-31", 1.1), ("1977-02-28", 1.1)],
                      "EXCAUS": [("1976-12-01", 1.0), ("1977-01-01", 1.0), ("1977-02-01", 1.0)]}.items():
        p = root / f"fred_{sid}/{sid}.csv"; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"observation_date,{sid}\n" + "".join(f"{d},{v}\n" for d, v in rows))
    g = root / "worldbank_gold/gold_monthly.csv"; g.parent.mkdir(parents=True, exist_ok=True)
    g.write_text("month,gold_usd_oz\n1976-12,100\n1977-01,110\n1977-02,99\n")

def test_par_bond_flat_yield_earns_its_coupon():
    assert par_bond_return(pd.Series([4.0, 4.0]), 20).iloc[1] == pytest.approx(0.04 / 12)

def test_par_bond_reprices_exactly():                         # closed-form par-bond pricing, no duration shortcut
    assert par_bond_return(pd.Series([4.0, 5.0]), 20).iloc[1] == pytest.approx(-0.121873, abs=1e-6)
    assert par_bond_return(pd.Series([3.0, 4.0]), 2).iloc[1] == pytest.approx(-0.015775, abs=1e-6)
    assert par_bond_return(pd.Series([5.0, 4.0]), 7.5).iloc[1] == pytest.approx(0.067799, abs=1e-6)

def test_ladder_is_the_issuer_duration_mix():
    assert sum(w for _, w in LADDER.values()) == pytest.approx(1.0)
    assert {v: t for v, (t, _) in LADDER.items()} == {"v122558": 2.0, "v122485": 4.0, "v122486": 7.5, "v122487": 20.0}

def test_build_panel_converts_splices_and_masks(tmp_path):
    make_raw(tmp_path); p = build_panel(tmp_path); j = pd.Timestamp("1977-01-31"); f = pd.Timestamp("1977-02-28")
    assert list(p.columns) == list(PROXY_IDS) + ["USDCAD_END"] and p.index.name == "month"
    assert p.loc[j, "US_MKT"] == pytest.approx((1 - 0.015) * 1.1 - 1)        # (Mkt-RF + RF) in USD x the loonie move
    assert p.loc[j, "BUSEQ"] == pytest.approx(0.99 * 1.1 - 1) and p.loc[j, "CHIPS"] == pytest.approx(0.8 * 1.1 - 1)
    assert pd.isna(p.loc[f, "CHIPS"]) and p.loc[f, "SOFTW"] == pytest.approx(0.05)   # -99.99 = missing, never -100 %
    assert p.loc[pd.Timestamp("1976-12-31"), "CA_EQ"] == pytest.approx(0.10 + 0.06 / 12)   # TSX close + yield/12 before 1977
    assert (p.loc[j, "CA_EQ"], p.loc[f, "CA_EQ"]) == (pytest.approx(0.02), pytest.approx(-0.04))   # French local from 1977
    assert p.loc[j, "CAD_TBILL"] == pytest.approx(0.03 / 12)
    assert p.loc[j, "CAD_BOND"] == pytest.approx(0.71 * 0.04 / 12 + 0.29 * -0.121873, abs=1e-6)
    assert (p.loc[j, "GOLD"], p.loc[f, "GOLD"]) == (pytest.approx(0.10), pytest.approx(-0.10))

def test_missing_cache_is_none_and_empty_proxy_is_none(tmp_path):
    assert load_panel(path=tmp_path / "absent.csv") is None
    (tmp_path / "px.csv").write_text("ticker,proxy,label,source,note\nBTC-USD,,No proxy,,x\nGLD,GOLD,Gold,WB,\n")
    assert load_proxy_map(path=tmp_path / "px.csv") == {"BTC-USD": {"proxy": None, "label": "No proxy", "note": "x"},
                                                         "GLD": {"proxy": "GOLD", "label": "Gold", "note": ""}}

# --- beyond the plan: the real files' layouts, holes, placeholders, the CSV contract -----------------
import tools.deep as deep
from tools.deep import load_episodes, read_fred, read_french_country, read_french_monthly, read_statcan

def _ts(*days): return [pd.Timestamp(d) for d in days]

def test_ledger_17_constants():
    assert (deep.DEEP_START, deep.DEEP_END, deep.OVERLAP_START) == ("1973-01", "2021-10", "2021-12")
    assert deep.STRONG == {"min_months": 24, "corr": 0.95, "te_ann": 0.05, "drawdown_gap": 0.03}
    assert PROXY_IDS == ("CA_EQ", "CAD_BOND", "CAD_TBILL", "GOLD", "US_MKT", "BUSEQ", "CHIPS", "SOFTW", "HARDW", "RTAIL",
                         "AUTOS", "BANKS", "DRUGS", "HSHLD", "OIL")
    assert deep.DEEP_DIR.parts[-3:] == ("data", "cache", "deep") and deep.PANEL_PATH == deep.DEEP_DIR / "panel.csv"
    assert deep.MANIFEST_PATH == deep.DEEP_DIR / "manifest.json"
    assert deep.EPISODES_PATH.parts[-2:] == ("data", "deep_episodes.csv") and deep.PROXIES_PATH.name == "deep_proxies.csv"
    assert deep.SOURCE.startswith("Proxy replay (assumption)") and deep.SOURCE.endswith("monthly, CAD")

def test_par_bond_keeps_the_index_and_a_missing_yield_is_nan_on_both_sides():
    y = pd.Series([4.0, None, 5.0, 5.0], index=list("abcd"))
    r = par_bond_return(y, 7.5)
    assert list(r.index) == list("abcd")
    assert r.isna().tolist() == [True, True, True, False]       # no previous month, the hole, the month after the hole
    assert r.iloc[3] == pytest.approx(0.05 / 12)

REAL_49 = ("This file was created using the 202609 CRSP database.\nIt contains value- and equal-weighted returns for 49 "
           "industry portfolios.\n\nMissing data are indicated by -99.99 or -999.\n\n\n  Average Value Weighted Returns -- Monthly\n"
           ",Agric,Food ,Fun  ,Oil  \n192607,   1.00,  -2.50,-99.99,  4.00\n192608,  -999,   0.50,   1.50,  -3.00\n\n"
           "  Average Equal Weighted Returns -- Monthly\n,Agric,Food ,Fun  ,Oil  \n192607,   9.00,   9.00,   9.00,  9.00\n\n"
           "  Average Value Weighted Returns -- Annual\n,Agric,Food ,Fun  ,Oil  \n  1927,   7.00,   7.00,   7.00,  7.00\n")

def test_french_monthly_reads_the_first_table_strips_header_padding_and_masks(tmp_path):
    _zip(tmp_path / "f.zip", "49_Industry_Portfolios.csv", REAL_49)
    d = read_french_monthly(tmp_path / "f.zip", ["Oil", "Food", "Fun", "Agric"])
    assert list(d.columns) == ["Oil", "Food", "Fun", "Agric"]      # "Food " is matched stripped; order as asked
    assert d.index.tolist() == _ts("1926-07-31", "1926-08-31")      # value-weighted monthly only: no equal-weight, no annual
    assert d["Oil"].tolist() == pytest.approx([0.04, -0.03]) and d["Food"].tolist() == pytest.approx([-0.025, 0.005])
    assert d["Fun"].isna().tolist() == [True, False] and d["Agric"].isna().tolist() == [False, True]   # -99.99 and -999
    with pytest.raises(KeyError, match="Nope"):
        read_french_monthly(tmp_path / "f.zip", ["Oil", "Nope"])

CANADA = ("\n     Value-Weight Dollar Returns      All 4 Data Items Not Reqd\n                -- BE/ME --   --- E/P ---\n"
          "          Mkt   High    Low   High    Low\n197701  -3.24  -2.23  -4.14  -3.17  -2.49\n197702  -0.36   0.82  -1.67   1.76  -2.03\n\n"
          "     Value-Weight Local  Returns      All 4 Data Items Not Reqd\n                -- BE/ME --   --- E/P ---\n"
          "          Mkt   High    Low   High    Low\n197701  -2.09  -1.06  -3.00  -2.02  -1.33\n197702 -99.99   3.29   0.74   4.25   0.37\n"
          "197703   1.54   2.67   0.81   2.40   3.66\n\n     Value-Weight Local  Returns      All 4 Data Items Required\n"
          "          Mkt   High\n197701   7.00   7.00\n")

def test_french_country_reads_the_local_not_reqd_block_and_the_mkt_column(tmp_path):
    with zipfile.ZipFile(tmp_path / "c.zip", "w") as z:
        z.writestr("Austria.Dat", CANADA.replace("-2.09", "-8.88")); z.writestr("Canada.Dat", CANADA)
    s = read_french_country(tmp_path / "c.zip")
    assert s.index.tolist() == _ts("1977-01-31", "1977-02-28", "1977-03-31")
    assert s.isna().tolist() == [False, True, False] and s.iloc[0] == pytest.approx(-0.0209) and s.iloc[2] == pytest.approx(0.0154)
    assert read_french_country(tmp_path / "c.zip", "Austria").iloc[0] == pytest.approx(-0.0888)

def test_statcan_reader_handles_the_real_layout_placeholder_hole_and_absent_vector(tmp_path):
    head = '"REF_DATE","GEO","DGUID","Rates","UOM","VECTOR","COORDINATE","VALUE","STATUS","SYMBOL"\n'
    row = lambda d, v, x, st="": f'"{d}","Canada","2021A","label","Percent","{v}","1.1","{x}","{st}",""\n'
    text = ("\ufeff" + head + row("1973-02", "v122531", "4.00") + row("1973-03", "v122531", "4.42") + row("1973-04", "v122531", "", "..")
            + row("1973-05", "v122531", "5.20") + row("1973-07", "v122531", "6.00") + row("1973-02", "v122541", "-99.999")
            + row("1973-04", "v122541", "4.900") + row("1973-02", "v999999", "7.0"))
    with zipfile.ZipFile(tmp_path / "s.zip", "w") as z:
        z.writestr("10100122_MetaData.csv", "Cube Title,x\n"); z.writestr("10100122.csv", text)
    w = read_statcan(tmp_path / "s.zip", ["v122531", "v122541", "v122487"])
    assert list(w.columns) == ["v122531", "v122541", "v122487"]
    assert w.index.tolist() == _ts("1973-02-28", "1973-03-31", "1973-04-30", "1973-05-31", "1973-06-30", "1973-07-31")
    assert w["v122531"].isna().tolist() == [False, False, True, False, True, False]      # blank value, and a month with no row
    assert w["v122531"].iloc[1] == pytest.approx(4.42)                                # percent stays percent
    assert w["v122541"].isna().tolist() == [True, True, False, True, True, True]         # -99.999 is a placeholder, not a yield
    assert w["v122487"].isna().all()                                                  # a vector the file lacks: NaN, not an error

def test_fred_reader_drops_missing_observations_and_sorts(tmp_path):
    (tmp_path / "d.csv").write_text("observation_date,DEXCAUS\n1977-01-06,1.2\n1977-01-04,1.1\n1977-01-05,.\n1977-01-03,\n")
    s = read_fred(tmp_path / "d.csv")
    assert s.index.tolist() == _ts("1977-01-04", "1977-01-06") and s.tolist() == [1.1, 1.2]

def test_build_panel_holes_stay_holes_and_tbill_falls_back_to_the_auction_series(tmp_path):
    make_raw(tmp_path)
    months = ["1976-12", "1977-01", "1977-02", "1977-03", "1977-04"]
    rows = {"v122558": [4] * 5, "v122485": [4] * 5, "v122486": [4, None, 4, 4, 4], "v122487": [4] * 5,
            "v122531": [3, 3, None, None, 3], "v122541": [2, 2, 2.5, -99.999, 2]}
    _zip(tmp_path / "statcan_10100122/10100122-eng.zip", "10100122.csv", "REF_DATE,GEO,VECTOR,VALUE\n" + "".join(
        f"{d},Canada,{v},{'' if y is None else y}\n" for v, ys in rows.items() for d, y in zip(months, ys)))
    p = build_panel(tmp_path); at = lambda s: pd.Timestamp(s)
    assert pd.isna(p.loc[at("1977-01-31"), "CAD_BOND"]) and pd.isna(p.loc[at("1977-02-28"), "CAD_BOND"])   # a leg is out: no partial ladder
    assert p.loc[at("1977-03-31"), "CAD_BOND"] == pytest.approx(0.04 / 12)
    assert p.loc[at("1977-02-28"), "CAD_TBILL"] == pytest.approx(0.03 / 12)
    assert p.loc[at("1977-03-31"), "CAD_TBILL"] == pytest.approx(0.025 / 12)    # 1977-02 yield from the auction series
    assert pd.isna(p.loc[at("1977-04-30"), "CAD_TBILL"])                         # both series out in 1977-03: a hole, never a placeholder

def test_pre_1977_canada_is_the_tsx_with_last_months_yield_and_the_splice_date_decides(tmp_path):
    make_raw(tmp_path)
    _zip(tmp_path / "statcan_10100125/10100125-eng.zip", "10100125.csv", "REF_DATE,GEO,VECTOR,VALUE\n"
         "1976-10,Canada,v122620,100\n1976-11,Canada,v122620,110\n1976-12,Canada,v122620,121\n"
         "1976-10,Canada,v122628,6.0\n1976-11,Canada,v122628,9.0\n1976-12,Canada,v122628,3.0\n")
    _zip(tmp_path / "french_countries/F-F_International_Countries.zip", "Canada.Dat",       # the file also covers 1976-12
         "\n     Value-Weight Local  Returns      All 4 Data Items Not Reqd\n          Mkt   High\n197612   7.00   7.00\n197701   2.00   1.00\n")
    p = build_panel(tmp_path)
    assert p.loc[pd.Timestamp("1976-11-30"), "CA_EQ"] == pytest.approx(0.10 + 0.06 / 12)    # the yield of 1976-10
    assert p.loc[pd.Timestamp("1976-12-31"), "CA_EQ"] == pytest.approx(0.10 + 0.09 / 12)    # the yield of 1976-11, not 1976-12's, not French 7 %
    assert p.loc[pd.Timestamp("1977-01-31"), "CA_EQ"] == pytest.approx(0.02)

# --- fix round 1 (review I2): CAD timing and gap handling, the behaviours no fixture above could tell apart -------------
def test_cad_conversion_uses_the_last_quote_of_the_month_and_gold_the_monthly_average(tmp_path):
    make_raw(tmp_path)         # January has two quotes (0.7 on the 3rd, 1.2 on the 28th) and a "." on the 31st; December has 0.5 and 1.0
    (tmp_path / "fred_DEXCAUS/DEXCAUS.csv").write_text("observation_date,DEXCAUS\n1976-12-01,0.5\n1976-12-31,1.0\n"
        "1977-01-03,0.7\n1977-01-28,1.2\n1977-01-31,.\n1977-02-28,1.2\n")
    (tmp_path / "fred_EXCAUS/EXCAUS.csv").write_text("observation_date,EXCAUS\n1976-12-01,1.0\n1977-01-01,1.2\n1977-02-01,1.2\n")
    p = build_panel(tmp_path); j = pd.Timestamp("1977-01-31")
    assert p.loc[j, "USDCAD_END"] == 1.2                                   # last non-missing quote, not first, not mean
    assert p.loc[j, "US_MKT"] == pytest.approx((1 - 0.015) * 1.2 - 1)      # a US line moves with the last quote of each month
    assert p.loc[j, "GOLD"] == pytest.approx(1.10 * 1.2 - 1)               # gold x the move of the monthly average

def test_a_missing_gold_month_is_two_nan_months_never_a_two_month_change(tmp_path):
    make_raw(tmp_path)
    (tmp_path / "worldbank_gold/gold_monthly.csv").write_text("month,gold_usd_oz\n1976-11,100\n1976-12,100\n1977-02,99\n1977-03,120\n")
    (tmp_path / "fred_EXCAUS/EXCAUS.csv").write_text("observation_date,EXCAUS\n" + "".join(f"{m}-01,1.0\n" for m in ("1976-11", "1976-12", "1977-01", "1977-02", "1977-03")))
    p = build_panel(tmp_path)
    assert p.loc[[pd.Timestamp("1977-01-31"), pd.Timestamp("1977-02-28")], "GOLD"].isna().all()   # the hole, and the month after it
    assert p.loc[pd.Timestamp("1977-03-31"), "GOLD"] == pytest.approx(120 / 99 - 1)

def test_build_panel_stops_when_a_source_gives_nothing_for_a_proxy(tmp_path):
    make_raw(tmp_path)
    _zip(tmp_path / "statcan_10100122/10100122-eng.zip", "10100122.csv", "REF_DATE,GEO,VECTOR,VALUE\n1976-12,Canada,v122531,3\n1977-01,Canada,v122531,3\n")
    with pytest.raises(ValueError, match="CAD_BOND"):
        build_panel(tmp_path)
    make_raw(tmp_path)
    _zip(tmp_path / "french_49/49_Industry_Portfolios_CSV.zip", "49_Industry_Portfolios.csv", _french(["Chips"], [[1.0]] * 3))
    with pytest.raises(KeyError, match="Softw"):
        build_panel(tmp_path)

def test_panel_csv_contract_round_trips_through_load_panel(tmp_path):
    make_raw(tmp_path); p = build_panel(tmp_path)
    out = p.copy(); out.index = out.index.strftime("%Y-%m"); out.index.name = "month"          # ledger 17: month "YYYY-MM"
    out.to_csv(tmp_path / "panel.csv")
    q = load_panel(path=tmp_path / "panel.csv")
    assert q.index.name == "month" and q.index[0] == pd.Timestamp("1976-11-30") and q.index.is_monotonic_increasing
    assert (q.index == q.index.to_period("M").to_timestamp(how="end").normalize()).all()      # month-end, midnight
    pd.testing.assert_frame_equal(q, p, check_freq=False)

def test_panel_levels_feed_make_market_on_the_month_end_index(tmp_path):      # the decision behind "month-end Timestamp"
    from tools.data import make_market
    make_raw(tmp_path); p = build_panel(tmp_path)
    levels = (1 + p[["CA_EQ", "GOLD"]].loc["1977-01-31":]).cumprod()
    m = make_market(levels)
    assert m["prices"].index.equals(levels.index) and m["flags"] == {"CA_EQ": [], "GOLD": []}

def test_load_panel_follows_the_module_path_at_call_time(tmp_path, monkeypatch):
    monkeypatch.setattr(deep, "PANEL_PATH", tmp_path / "absent.csv")
    assert deep.load_panel() is None

def test_episode_loader_reads_utf8_with_or_without_a_bom_and_casts(tmp_path):
    csv = ('episode_id,title_en,start,end,lat,lon,family\nx,"Oil embargo, the 1973–74 bear market",1973-01,1974-12,29.3759,47.9774,war_oil\n'
           'y,Plain,1979-09,1982-07,38.9,-77.04,\n')
    for name, enc in (("bom.csv", "utf-8-sig"), ("plain.csv", "utf-8")):
        (tmp_path / name).write_text(csv, encoding=enc)
        a, b = load_episodes(path=tmp_path / name)
        assert a["title_en"] == "Oil embargo, the 1973–74 bear market" and a["episode_id"] == "x"
        assert (a["lat"], a["lon"], a["family"]) == (29.3759, 47.9774, "war_oil")
        assert b["family"] is None and b["lat"] == 38.9 and b["lon"] == -77.04 and b["start"] == "1979-09"

def test_the_shipped_catalogue_loads_through_the_loaders():
    eps, pm = load_episodes(), load_proxy_map()
    assert len(eps) == 11 and [e["start"] for e in eps] == sorted(e["start"] for e in eps)
    assert all(isinstance(e["lat"], float) and isinstance(e["lon"], float) for e in eps)
    assert {e["family"] for e in eps} <= {None, "tariffs", "war_oil", "chips", "rates"} and None in {e["family"] for e in eps}
    assert len(pm) == 31 and pm["BTC-USD"]["proxy"] is None and pm["XIU.TO"]["proxy"] == "CA_EQ"
    assert {v["proxy"] for v in pm.values()} - {None} <= set(PROXY_IDS)

# --- Task 16: the replay, the proxy check, the Result fragment (plan A Task 16; ledger 17, 30) -------------
import json
from decimal import Decimal
from pathlib import Path
import numpy as np
from tools.data import make_market
from tools.deep import deep_history, deep_sentence, episode_replay, proxy_check, proxy_levels, rejudge

def ME(*m): return pd.PeriodIndex(list(m), freq="M").to_timestamp(how="end").normalize()
TOY = ME("1999-12", "2000-01", "2000-02", "2000-03", "2000-04")
PANEL = pd.DataFrame({"A": [0.0, 0.10, -0.20, -0.10, 0.50], "B": [0.0] * 5}, index=TOY)
PM = {"X": {"proxy": "A", "label": "a", "note": ""}, "Y": {"proxy": "B", "label": "b", "note": ""},
      "Z": {"proxy": None, "label": "none", "note": ""}}
EPI = {"episode_id": "toy", "title_en": "Toy crash", "start": "2000-01", "end": "2000-03", "kind": "crash",
       "family": None, "place": "Nowhere", "lat": 0.0, "lon": 0.0, "source_url": "https://example.org"}

def test_replay_worst_fall_inside_the_window_in_exact_dollars():
    r = episode_replay({"X": .5, "Y": .5}, EPI, amount=600000, floor=-0.15, panel=PANEL, proxy_map=PM)
    assert r["replayable"] and r["depth"] == pytest.approx(89.775 / 105 - 1)       # 100 -> 105 -> 94.5 -> 89.775
    assert (r["peak"], r["trough"]) == ("2000-01", "2000-03")
    assert (r["peak_value"], r["trough_value"]) == (pytest.approx(105), pytest.approx(89.775))
    assert r["loss_dollars"] == 87000 and r["recovery_months"] == 1 and r["beyond_floor"] is False   # amount x drawdown (ledger 30)
    assert episode_replay({"X": .5, "Y": .5}, EPI, amount=1, floor=-0.14, panel=PANEL, proxy_map=PM)["beyond_floor"] is True

def test_no_proxy_or_a_hole_is_cant_say_never_a_zero_fill():
    r = episode_replay({"X": .5, "Z": .5}, EPI, amount=1, floor=-0.15, panel=PANEL, proxy_map=PM)
    assert r["replayable"] is False and r["uncovered"] == ["Z"] and r["depth"] is None and r["loss_dollars"] is None
    holed = PANEL.assign(B=[0.0, 0.0, np.nan, 0.0, 0.0])
    assert episode_replay({"X": .5, "Y": .5}, EPI, amount=1, floor=-0.15, panel=holed, proxy_map=PM)["uncovered"] == ["Y"]

def test_peak_can_be_the_window_base_and_the_floor_rounds_to_a_tenth():
    r = episode_replay({"X": 1.0}, EPI, amount=100, floor=-0.15, panel=PANEL.assign(A=[0, -0.10, 0, 0, 0.30]), proxy_map=PM)
    assert (r["peak"], r["trough"], r["recovery_months"]) == ("1999-12", "2000-01", 3) and r["depth"] == pytest.approx(-0.10)
    for a, beyond in [(-0.15049, False), (-0.15051, True)]:
        p = PANEL.assign(A=[0.0, a, 0.0, 0.0, 0.0])
        assert episode_replay({"X": 1.0}, EPI, amount=1, floor=-0.15, panel=p, proxy_map=PM)["beyond_floor"] is beyond

def test_rows_after_as_of_never_change_a_replay():
    late = PANEL.copy(); late.loc[TOY[-1], "A"] = -0.99
    a = episode_replay({"X": .5, "Y": .5}, EPI, "2000-03-31", amount=1, floor=-0.15, panel=PANEL, proxy_map=PM)
    b = episode_replay({"X": .5, "Y": .5}, EPI, "2000-03-31", amount=1, floor=-0.15, panel=late, proxy_map=PM)
    assert a == b and a["recovery_months"] is None and a["as_of"] == "2000-03-31"

def _panel_and_market():
    idx = pd.period_range("1999-12", "2024-06", freq="M").to_timestamp(how="end").normalize()
    a = pd.Series(np.random.default_rng(7).normal(0.005, 0.04, len(idx)), index=idx)
    a.loc[TOY] = [0.0, 0.10, -0.20, -0.10, 0.50]
    ov = idx[idx >= pd.Timestamp("2021-11-30")]
    prices = pd.DataFrame({"X": 100 * (1 + a.loc[ov].where(ov > ov[0], 0.0)).cumprod(), "Y": 100.0}, index=ov)
    return pd.DataFrame({"A": a, "B": 0.0}, index=idx), make_market(prices)

def test_proxy_check_strong_weak_and_cant_say():
    panel, m = _panel_and_market()
    s = proxy_check({"X": .5, "Y": .5}, "2024-06-30", market=m, panel=panel, proxy_map=PM)
    assert (s["strength"], s["n_months"], s["window"]) == ("strong", 31, {"start": "2021-12", "end": "2024-06"})
    assert s["corr"] == pytest.approx(1.0) and s["te_ann"] == pytest.approx(0.0, abs=1e-12)
    w = proxy_check({"X": .5, "Y": .5}, "2024-06-30", market=m, panel=panel.assign(A=panel["A"] * 2), proxy_map=PM)
    assert (w["strength"], w["direction"]) == ("weak", "harsher") and w["drawdown_gap"] < 0
    assert proxy_check({"X": .5, "Y": .5}, "2023-06-30", market=m, panel=panel, proxy_map=PM)["strength"] == "can't say"
    assert proxy_check({"X": .5, "Z": .5}, "2024-06-30", market=m, panel=panel, proxy_map=PM)["uncovered"] == ["Z"]

def test_deep_history_fragment_counts_and_sentence(monkeypatch, tmp_path):
    panel, m = _panel_and_market()
    f = deep_history({"X": .5, "Y": .5}, {"X": 1.0}, "2024-06-30", amount=600000, floor=-0.15, market=m,
                     panel=panel, episodes=[EPI], proxy_map=PM)
    assert set(f) == {"frequency", "window", "proxy", "episodes", "summary", "sentence", "source", "as_of"}
    assert f["window"] == {"start": "1973-01", "end": "2021-10"} and f["episodes"][0]["title"] == "Toy crash"
    assert f["summary"]["today"] == {"breaches": 0, "replayable": 1, "worst_episode": "toy",
                                     "worst_depth": pytest.approx(-0.145), "worst_loss_dollars": 87000}
    assert f["summary"]["after"]["breaches"] == 1 and f["episodes"][0]["after"]["loss_dollars"] == 168000
    assert f["sentence"] == ("◐ Older history (proxies, monthly; not used in the verdict): your mix today fell beyond "
                             "your floor of −15 % in 0 of 1 earlier crises (worst: Toy crash, −14.5 %, $87,000). "
                             "The move: 1 of 1 (worst: Toy crash, −28.0 %, $168,000).")
    r = rejudge(f, -0.10)
    assert r["summary"]["today"]["breaches"] == 1 and r["episodes"][0]["today"]["depth"] == f["episodes"][0]["today"]["depth"]
    assert "floor of −10 %" in r["sentence"]
    monkeypatch.setattr(deep, "PANEL_PATH", tmp_path / "absent.csv")
    assert deep_history({"X": 1.0}, None, "2024-06-30", amount=1, floor=-0.15, market=m, episodes=[EPI], proxy_map=PM) is None

def test_fake_result_carries_a_fake_deep_fragment():
    d = json.loads(Path("data/fake/result.json").read_text())["deep_history"]
    assert set(d) == {"frequency", "window", "proxy", "episodes", "summary", "sentence", "source", "as_of"}
    assert "FAKE" in d["source"] and len(d["episodes"]) == 11

# --- beyond the plan: the rulings of Nov 14 (dollars, labelling, Can't say, retrieved_at) and the edges ---------
def test_dollars_are_amount_times_the_drawdown_even_when_the_path_grew_before_its_peak():   # ledger 30, board seat 3
    r = episode_replay({"X": .5, "Y": .5}, EPI, amount=600000, floor=-0.15, panel=PANEL, proxy_map=PM)
    assert r["peak_value"] > 100                                  # the path grew 5 % before its peak
    assert r["loss_dollars"] == round(600000 * -r["depth"]) == 87000
    assert r["loss_dollars"] != round(600000 * (r["peak_value"] - r["trough_value"]) / 100)   # 91,350: the older definition

def test_round_pp_is_the_governance_rounding_and_takes_numpy_floats():
    cases = [(-0.15049, "-15.0"), (-0.15051, "-15.1"), (-0.1500004, "-15.0"), (-0.345, "-34.5"), (0.08, "8.0")]
    assert [deep._round_pp(x) for x, _ in cases] == [Decimal(t) for _, t in cases]
    assert deep._round_pp(np.float64(-0.15051)) == Decimal("-15.1")

def test_a_line_without_a_proxy_is_cant_say_naming_it_and_a_line_at_zero_is_not_held():
    pm = {**PM, "BTC-USD": {"proxy": None, "label": "No proxy", "note": ""}, "ETH-USD": {"proxy": None, "label": "No proxy", "note": ""}}
    r = episode_replay({"X": .5, "BTC-USD": .3, "ETH-USD": .2}, EPI, amount=1, floor=-0.15, panel=PANEL, proxy_map=pm)
    assert r["replayable"] is False and r["uncovered"] == ["BTC-USD", "ETH-USD"]
    zero = episode_replay({"X": 1.0, "BTC-USD": 0.0}, EPI, amount=1, floor=-0.15, panel=PANEL, proxy_map=pm)
    assert zero["replayable"] is True and zero["uncovered"] == []
    shipped = deep.load_proxy_map()
    assert shipped["BTC-USD"]["proxy"] is None and shipped["ETH-USD"]["proxy"] is None

def test_a_window_not_over_at_as_of_is_not_replayable_never_a_peek_at_later_months():
    r = episode_replay({"X": .5, "Y": .5}, EPI, "2000-02-29", amount=1, floor=-0.15, panel=PANEL, proxy_map=PM)
    assert r["replayable"] is False and r["depth"] is None and r["uncovered"] == ["X", "Y"]

def test_proxy_levels_base_one_a_missing_proxy_and_a_hole_that_never_heals():
    holed = PANEL.assign(A=[0.0, 0.10, np.nan, 0.10, 0.10])
    lv = proxy_levels(["X", "Y", "Z"], "2000-01", "2000-04", panel=holed, proxy_map=PM)
    assert list(lv.index) == list(TOY) and lv.loc[TOY[0], "X"] == 1.0 and lv["Y"].eq(1.0).all()
    assert lv["X"].iloc[1] == pytest.approx(1.10) and lv["X"].iloc[2:].isna().all() and lv["Z"].isna().all()

def test_proxy_check_uses_only_months_up_to_as_of_and_only_full_months():
    panel, m = _panel_and_market()
    cut = make_market(m["prices"].loc[:"2024-03-31"])
    a = proxy_check({"X": .5, "Y": .5}, "2024-03-31", market=m, panel=panel, proxy_map=PM)      # m holds rows after as_of
    b = proxy_check({"X": .5, "Y": .5}, "2024-03-31", market=cut, panel=panel, proxy_map=PM)
    assert a == b and a["window"] == {"start": "2021-12", "end": "2024-03"} and a["n_months"] == 28
    day = m["prices"].iloc[[-2]].rename(index={m["prices"].index[-2]: pd.Timestamp("2024-06-14")})   # a June price, mid-month
    mid_market = make_market(pd.concat([m["prices"], day]).sort_index().loc[:"2024-06-14"])
    mid = proxy_check({"X": .5, "Y": .5}, "2024-06-15", market=mid_market, panel=panel, proxy_map=PM)   # June is not over yet
    assert mid["window"]["end"] == "2024-05" and mid["n_months"] == 30
    late = panel.copy(); late.loc[late.index > "2024-03-31", "A"] = -0.5                          # later proxy rows: poison
    assert proxy_check({"X": .5, "Y": .5}, "2024-03-31", market=m, panel=late, proxy_map=PM) == a

def test_proxy_check_stops_at_the_last_month_every_held_proxy_has():
    panel, m = _panel_and_market()
    short = panel.copy(); short.loc[short.index > "2023-12-31", "A"] = np.nan                    # the Canada series ends early
    s = proxy_check({"X": .5, "Y": .5}, "2024-06-30", market=m, panel=short, proxy_map=PM)
    assert s["window"] == {"start": "2021-12", "end": "2023-12"} and s["n_months"] == 25 and s["strength"] == "strong"
    short.loc[short.index > "2023-05-31", "A"] = np.nan                                           # 18 months left: not enough
    assert proxy_check({"X": .5, "Y": .5}, "2024-06-30", market=m, panel=short, proxy_map=PM)["strength"] == "can't say"

def test_a_hole_ends_the_window_it_is_never_skipped_over():
    panel, m = _panel_and_market()
    holed = panel.copy(); holed.loc[pd.Timestamp("2023-09-30"), "A"] = np.nan
    h = proxy_check({"X": .5, "Y": .5}, "2024-06-30", market=m, panel=holed, proxy_map=PM)
    assert h["n_months"] == 21 and h["window"]["end"] == "2023-08" and h["strength"] == "can't say"   # not 30 skipped months
    assert h["corr"] is None and h["te_ann"] is None and h["drawdown_gap"] is None

def test_a_flat_side_has_no_correlation_so_the_badge_cant_say():
    panel, m = _panel_and_market()
    flat = proxy_check({"Y": 1.0}, "2024-06-30", market=m, panel=panel, proxy_map=PM)           # Y never moves, on both sides
    assert flat["strength"] == "can't say" and flat["corr"] is None and flat["n_months"] == 31

def test_a_gentler_proxy_is_labelled_gentler():
    panel, m = _panel_and_market()
    g = proxy_check({"X": .5, "Y": .5}, "2024-06-30", market=m, panel=panel.assign(A=panel["A"] * 0.1), proxy_map=PM)
    assert (g["strength"], g["direction"]) == ("weak", "gentler") and g["drawdown_gap"] > 0
    assert g["drawdown_proxy"] > g["drawdown_real"]

import re
ADVICE = re.compile(r"\b(buy|sell|hold|should)\b", re.I)
RATE_WORDS = re.compile(r"worst ever|ever recorded|probab|chance|likel|expected|average|mean|per cent of the time", re.I)

def _frag(**kw):
    panel, m = _panel_and_market()
    args = dict(weights_today={"X": .5, "Y": .5}, weights_after={"X": 1.0}, as_of="2024-06-30", amount=600000,
                floor=-0.15, market=m, panel=kw.pop("panel", panel), episodes=[EPI], proxy_map=kw.pop("proxy_map", PM))
    args.update(kw)
    return deep_history(args.pop("weights_today"), args.pop("weights_after"), args.pop("as_of"), **args)

def test_rejudge_is_the_fragment_recomputed_at_the_new_floor_and_leaves_the_input_alone():
    f = _frag(); before = json.dumps(f, sort_keys=True)
    for floor in (-0.10, -0.145, -0.30):
        r = rejudge(f, floor)
        assert r == _frag(floor=floor)                       # the stored depths are enough: no data, same answer
    assert json.dumps(f, sort_keys=True) == before and rejudge(None, -0.1) is None
    assert rejudge(f, -0.145)["summary"]["today"]["breaches"] == 0    # -14.5 % is not beyond -14.5 % (strictly beyond)
    assert rejudge(f, -0.144)["summary"]["today"]["breaches"] == 1
    assert rejudge(f, -0.1449)["summary"]["today"]["breaches"] == 0 == _frag(floor=-0.1449)["summary"]["today"]["breaches"]

def test_the_fragment_is_json_safe_and_does_not_touch_its_inputs():
    wt, wa = {"X": .5, "Y": .5}, {"X": 1.0}
    f = _frag(weights_today=wt, weights_after=wa)
    assert wt == {"X": .5, "Y": .5} and wa == {"X": 1.0}
    assert json.loads(json.dumps(f)) == f                     # no numpy scalar, no NaN leaks into the Result

def test_no_move_means_no_after_side_anywhere():
    f = _frag(weights_after=None)
    assert f["proxy"]["after"] is None and f["summary"]["after"] is None and f["episodes"][0]["after"] is None
    assert "The move" not in f["sentence"] and f["sentence"].startswith("◐ Older history (proxies, monthly;")
    assert rejudge(f, -0.2)["summary"]["after"] is None

def test_the_sentence_is_labelled_counts_stress_tests_and_never_gives_advice_or_a_rate():
    sentences = [_frag()["sentence"], _frag(panel=_panel_and_market()[0].assign(A=lambda d: d["A"] * 2))["sentence"],
                 _frag(weights_today={"X": .5, "Z": .5})["sentence"]]
    for s in sentences:
        assert s.startswith("◐ Older history (proxies, monthly; not used in the verdict): ")
        assert "monthly" in s and re.search(r"\bprox(y|ies)\b", s) and not ADVICE.search(s) and not RATE_WORDS.search(s)
        assert s.endswith(".") and not re.search(r"\d+ %\s*(of|chance)", s)

def test_cant_say_names_the_line_weak_names_the_case_and_a_short_overlap_says_so():
    z = _frag(weights_today={"X": .5, "Z": .5})
    assert "your mix today: can't say (no proxy for Z)." in z["sentence"] and z["summary"]["today"]["replayable"] == 0
    assert z["summary"]["today"]["worst_episode"] is None and z["summary"]["today"]["worst_loss_dollars"] is None
    harsh = _frag(panel=_panel_and_market()[0].assign(A=lambda d: d["A"] * 2))["sentence"]
    assert "Proxy weak for your mix today: read the older episodes as the harsher case." in harsh
    short = _frag(as_of="2023-06-30")["sentence"]
    assert "Proxy check for your mix today: can't say (only 19 months to compare)." in short

def test_a_partly_replayable_side_says_how_many_could_not_be_replayed():
    other = {**EPI, "episode_id": "toy2", "title_en": "Toy two", "start": "2000-02", "end": "2000-04"}
    holed = PANEL.assign(B=[0.0, 0.0, 0.0, np.nan, 0.0])
    f = deep_history({"X": .5, "Y": .5}, None, "2000-12-31", amount=1000, floor=-0.15, market=_panel_and_market()[1],
                     panel=holed, episodes=[EPI, other], proxy_map=PM)
    assert f["summary"]["today"]["replayable"] == 0 and "can't say (no proxy data for Y in these crises)" in f["sentence"]
    mixed = deep_history({"X": 1.0}, None, "2000-12-31", amount=1000, floor=-0.15, market=_panel_and_market()[1],
                         panel=PANEL.assign(A=[0.0, 0.1, -0.2, -0.1, np.nan]), episodes=[EPI, other], proxy_map=PM)
    assert (mixed["summary"]["today"]["replayable"], mixed["episodes"][1]["today"]["replayable"]) == (1, False)
    assert mixed["episodes"][0]["today"]["recovery_months"] is None          # the hole ends the months that can be used
    assert " 1 of 2 could not be replayed." in mixed["sentence"] and "of 1 earlier crises" in mixed["sentence"]

def test_the_source_line_prints_retrieved_at_as_written_never_none(monkeypatch, tmp_path):
    manifest = tmp_path / "manifest.json"
    monkeypatch.setattr(deep, "MANIFEST_PATH", manifest)
    for written, shown in [('{"retrieved_at": "not recorded"}', "not recorded"),
                           ('{"retrieved_at": "2026-11-14T21:11:03Z"}', "2026-11-14T21:11:03Z"),
                           ('{"retrieved_at": null}', "not recorded"), ('{"retrieved_at": ""}', "not recorded"),
                           ('{"files": []}', "not recorded"), ('[1, 2]', "not recorded"), ("not json", "not recorded")]:
        manifest.write_text(written)
        src = _frag()["source"]
        assert f"Data retrieved: {shown}." in src and "None" not in src and src.startswith(deep.SOURCE)
        assert "This already happened to markets like these; it is not a forecast." in src
    manifest.unlink()                                          # no manifest at all (a fresh clone, an old cache)
    assert "Data retrieved: not recorded." in _frag()["source"]

ROBERT = {"XIU.TO": .45, "XBB.TO": .35, "GLD": .10, "ZST.TO": .10}
REAL_PANEL = pytest.mark.skipif(not Path("data/cache/deep/panel.csv").exists(),
                                reason="needs the output of scripts/fetch_deep.py (local only, licences)")

@REAL_PANEL
def test_real_robert_today_reproduces_spec_23_depths_and_the_dollars_are_amount_times_drawdown():
    pm, panel = deep.load_proxy_map(), deep.load_panel()
    eps = {e["episode_id"]: e for e in deep.load_episodes()}
    got = {k: episode_replay(ROBERT, eps[k], amount=600000, floor=-0.15, panel=panel, proxy_map=pm)
           for k in ("oil_embargo_1973", "volcker_1979", "gfc_2008")}
    assert [got[k]["depth"] for k in got] == [pytest.approx(x, abs=5e-5) for x in (-0.1522, -0.1614, -0.1696)]
    g = got["gfc_2008"]
    assert g["loss_dollars"] == 101760 == round(600000 * -g["depth"])       # not the data file's $110,859 (board seat 3)
    assert (g["peak"], g["trough"], g["recovery_months"], g["beyond_floor"]) == ("2008-05", "2009-02", 12, True)
    assert all(r["beyond_floor"] for r in got.values())                      # all three are beyond -15 % after rounding

def test_the_worst_episode_is_the_deepest_not_the_first_or_the_last_listed():
    early = {**EPI, "episode_id": "early", "title_en": "Early", "start": "2000-01", "end": "2000-02"}    # X alone: -20 %
    deeper = {**EPI, "episode_id": "deeper", "title_en": "Deeper", "start": "2000-02", "end": "2000-04"}   # X alone: -28 %
    tail = {**EPI, "episode_id": "tail", "title_en": "Tail", "start": "1999-12", "end": "2000-01"}         # X alone: no fall
    panel, m = _panel_and_market()
    f = deep_history({"X": 1.0}, None, "2024-06-30", amount=1000, floor=-0.25, market=m, panel=panel,
                     episodes=[early, deeper, tail], proxy_map=PM)
    s = f["summary"]["today"]
    assert (s["breaches"], s["replayable"], s["worst_episode"], s["worst_loss_dollars"]) == (1, 3, "deeper", 280)
    assert s["worst_depth"] == pytest.approx(-0.28) and "(worst: Deeper, −28.0 %, $280)" in f["sentence"]
    assert f["episodes"][2]["today"]["depth"] == 0.0 and "−0.0" not in f["sentence"]

def test_every_strong_criterion_is_wired_and_a_short_overlap_is_never_strong(monkeypatch):
    panel, m = _panel_and_market()
    args = ({"X": .5, "Y": .5}, "2024-06-30")
    base = proxy_check(*args, market=m, panel=panel, proxy_map=PM)
    assert (base["strength"], base["n_months"]) == ("strong", 31)
    for key, value in [("corr", 1.01), ("te_ann", -1.0), ("drawdown_gap", -1.0)]:
        monkeypatch.setitem(deep.STRONG, key, value)
        assert proxy_check(*args, market=m, panel=panel, proxy_map=PM)["strength"] == "weak", key
        monkeypatch.undo()
    monkeypatch.setitem(deep.STRONG, "min_months", 31)
    assert proxy_check(*args, market=m, panel=panel, proxy_map=PM)["strength"] == "strong"      # n >= 31 counts
    monkeypatch.setitem(deep.STRONG, "min_months", 32)
    assert proxy_check(*args, market=m, panel=panel, proxy_map=PM)["strength"] == "can't say"

def test_an_empty_catalogue_is_a_plain_cant_say_not_a_crash():
    f = _frag(episodes=[], weights_after=None)
    assert f["summary"] == {"today": {"breaches": 0, "replayable": 0, "worst_episode": None, "worst_depth": None,
                                      "worst_loss_dollars": None}, "after": None}
    assert "can't say (no crisis could be replayed)" in f["sentence"]

def test_a_ticker_the_market_does_not_know_is_a_bad_input_not_a_coverage_gap():
    panel, m = _panel_and_market()
    pm = {**PM, "W": {"proxy": "A", "label": "w", "note": ""}}
    with pytest.raises(ValueError, match="Unknown ticker: W"):
        proxy_check({"X": .5, "W": .5}, "2024-06-30", market=m, panel=panel, proxy_map=pm)
