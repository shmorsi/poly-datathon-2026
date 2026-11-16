"""Task 6 tests: tools/lookthrough.py (spec sections 9-10; plan A Task 6).

Offline: synthetic holdings frames (`H`) and a small universe (`UNI`). The real-data cases skip when
the local data/etf_holdings.csv is absent (issuers forbid redistributing it, pitfall 10).
tests/test_geo.py and tests/test_risk.py import UNI, H and ETF1 from here.
"""
import json

import pandas as pd, pytest
from pathlib import Path
import tools.lookthrough as lt
from tools.lookthrough import look_through, load_holdings

UNI = pd.DataFrame([r.split(",") for r in [
    "NVDA,NVIDIA,equity,NASDAQ,USD,Information Technology,USA",
    "CNQ.TO,Canadian Natural,equity,TSX,CAD,Energy,CAN",
    "ETF1,Test ETF,etf_equity,NYSE Arca,USD,Broad market,USA",
    "XIU.TO,TSX 60,etf_equity,TSX,CAD,Broad market (Canada),CAN",
    "XBB.TO,Bonds,etf_bond,TSX,CAD,Bonds,CAN",
    "GLD,Gold,etf_commodity,NYSE Arca,USD,Gold,USA",
    "BTC-USD,Bitcoin,crypto,Crypto (24/7),USD,Crypto asset,CRYPTO"]],
    columns=["ticker", "name", "asset_class", "market", "currency", "sector", "country"])

NEEDS_HOLDINGS = pytest.mark.skipif(not lt.HOLDINGS_CSV.exists(), reason="local ETF holdings absent")

def H(rows):   # (etf, kind, name, ticker, weight) -> holdings frame dated 2026-11-12
    return pd.DataFrame([(*r, "2026-11-12", "https://example.test") for r in rows],
                        columns=["etf", "kind", "name", "ticker", "weight", "as_of", "source_url"])

ETF1 = [("ETF1", "holding", "NVIDIA", "NVDA", 0.10), ("ETF1", "sector", "Information Technology", "", 0.6),
        ("ETF1", "sector", "Financials", "", 0.4), ("ETF1", "country", "USA", "", 1.0)]

def test_nvda_direct_plus_inside_etf():            # spec §15 look-through test
    out = look_through({"NVDA": 0.40, "ETF1": 0.50, "XBB.TO": 0.10}, holdings=H(ETF1), universe=UNI, esg_flags=set())
    assert out["stocks"]["NVDA"]["total"] == pytest.approx(0.45)
    assert out["stocks"]["NVDA"]["via"] == [{"etf": "ETF1", "weight": pytest.approx(0.05)}]
    assert out["sectors"] == pytest.approx({"Information Technology": 0.70, "Financials": 0.20})
    assert out["countries"] == pytest.approx({"USA": 0.90, "CAN": 0.10})
    assert out["mode"] == "lookthrough" and out["coverage"] == pytest.approx({"ETF1": 0.10})
    assert out["snapshot"] == {"ETF1": "2026-11-12"}

def test_percent_weights_and_icb_names_are_normalized():
    pct = [("ETF1", "holding", "NVIDIA", "NVDA", 10.0), ("ETF1", "sector", "Technology", "", 60.0),
           ("ETF1", "sector", "Telecommunications", "", 40.0), ("ETF1", "country", "USA", "", 100.0)]
    out = look_through({"ETF1": 1.0}, holdings=H(pct), universe=UNI, esg_flags=set())
    assert out["stocks"]["NVDA"]["total"] == pytest.approx(0.10)
    assert out["sectors"] == pytest.approx({"Information Technology": 0.6, "Communication Services": 0.4})

def test_energy_inside_etf_cash_row_and_gold():
    xiu = [("XIU.TO", "holding", "CNQ", "CNQ.TO", 0.0345), ("XIU.TO", "sector", "Energy", "", 0.1665),
           ("XIU.TO", "sector", "Cash and/or Derivatives", "", 0.0031), ("XIU.TO", "country", "CAN", "", 0.98)]
    out = look_through({"XIU.TO": 0.35, "CNQ.TO": 0.08, "GLD": 0.57}, holdings=H(xiu), universe=UNI, esg_flags=set())
    assert out["esg_indirect"] == pytest.approx({"CNQ.TO": 0.35 * 0.0345})
    assert out["energy_via_etfs"] == pytest.approx(0.35 * 0.1665)
    assert out["stocks"]["CNQ.TO"]["total"] == pytest.approx(0.08 + 0.35 * 0.0345)
    assert "Cash and/or Derivatives" not in out["sectors"] and "Gold" not in out["sectors"]
    assert out["countries"]["GLOBAL"] == pytest.approx(0.57)
    assert out["countries"]["OTHER"] == pytest.approx(0.35 * 0.02)      # unexplained 2 % of XIU.TO

def test_absent_file_falls_back_to_direct(monkeypatch, tmp_path):
    monkeypatch.setattr(lt, "HOLDINGS_CSV", tmp_path / "missing.csv")
    assert load_holdings() is None
    out = look_through({"XIU.TO": 0.5, "NVDA": 0.2, "GLD": 0.1, "BTC-USD": 0.2}, universe=UNI, esg_flags=set())
    assert out["mode"] == "direct" and out["coverage"] == {} and out["snapshot"] == {}
    assert out["countries"] == pytest.approx({"CAN": 0.5, "USA": 0.2, "GLOBAL": 0.1, "CRYPTO": 0.2})
    assert out["sectors"] == pytest.approx({"Information Technology": 0.2})

@NEEDS_HOLDINGS
def test_real_amira_tech_and_mateo_energy():
    amira = {"NVDA": .15, "QQQ": .15, "SHOP.TO": .10, "BTC-USD": .15, "XIU.TO": .30, "XBB.TO": .15}
    assert look_through(amira)["sectors"]["Information Technology"] == pytest.approx(0.375, abs=0.002)
    mateo = look_through({"XIU.TO": .35, "XBB.TO": .35, "CNQ.TO": .08, "MSFT": .10, "GLD": .12})
    assert mateo["esg_indirect"]["ENB.TO"] == pytest.approx(0.35 * 0.0359, abs=1e-4)   # >= 1 % -> warn


# --- beyond the brief: the rules written down in tools/lookthrough.py ----------------------------------
UNI2 = pd.concat([UNI, pd.DataFrame([r.split(",") for r in [
    "GOOGL,Alphabet (Class A),equity,NASDAQ,USD,Communication Services,USA",
    "ETF2,Second ETF,etf_equity,NASDAQ,USD,Broad market,USA"]], columns=UNI.columns)], ignore_index=True)

def test_alphabet_class_c_rows_count_as_googl():    # ledger 14: one company, so GOOGL is not understated by ~45 %
    rows = [("ETF1", "holding", "ALPHABET INC CL A", "GOOGL", 0.03), ("ETF1", "holding", "ALPHABET INC CL C", "", 0.02),
            ("ETF2", "holding", "Alphabet Inc Class C", "GOOG", 0.04), ("ETF2", "holding", "Alphabet Inc Class A", "GOOGL", 0.03)]
    out = look_through({"ETF1": 0.5, "ETF2": 0.5}, holdings=H(rows), universe=UNI2, esg_flags=set())
    assert out["stocks"]["GOOGL"]["total"] == pytest.approx(0.5 * 0.05 + 0.5 * 0.07)
    assert out["stocks"]["GOOGL"]["via"] == [{"etf": "ETF2", "weight": pytest.approx(0.035)},
                                             {"etf": "ETF1", "weight": pytest.approx(0.025)}]   # one entry per ETF
    assert out["coverage"] == pytest.approx({"ETF1": 0.05, "ETF2": 0.07})
    named = [("ETF1", "holding", "ALPHABET INC CL C", "", 0.02), ("ETF1", "holding", "Alphabet Inc Class A", "", 0.03)]
    assert "GOOGL" in look_through({"ETF1": 1.0}, holdings=H(named), universe=UNI2, esg_flags=set())["stocks"]
    # only the Class C line is Alphabet's second share class: the Class A line without a ticker stays unknown
    assert look_through({"ETF1": 1.0}, holdings=H(named), universe=UNI2, esg_flags=set())["stocks"]["GOOGL"]["total"] == pytest.approx(0.02)

def test_only_dataset_equities_enter_stocks_but_every_row_counts_toward_coverage():
    rows = [("ETF1", "holding", "NVIDIA", "NVDA", 0.10), ("ETF1", "holding", "Unlisted Corp", "", 0.20),
            ("ETF1", "holding", "Gold fund", "GLD", 0.05), ("ETF1", "holding", "Elsewhere", "ZZZ", 0.05)]
    out = look_through({"ETF1": 0.5, "CNQ.TO": 0.5}, holdings=H(rows), universe=UNI, esg_flags=set())
    assert set(out["stocks"]) == {"NVDA", "CNQ.TO"}                        # a dataset ETF is not a company
    assert out["stocks"]["CNQ.TO"] == {"direct": 0.5, "via": [], "total": 0.5}
    assert out["coverage"] == pytest.approx({"ETF1": 0.40})

def test_sector_rows_count_for_equity_etfs_only_and_non_sectors_never():
    rows = ETF1 + [("XBB.TO", "sector", "Financials", "", 0.3), ("XBB.TO", "sector", "Bonds", "", 0.7),
                   ("ETF1", "sector", "Crypto", "", 0.1), ("ETF1", "sector", "Cash", "", 0.1)]
    out = look_through({"ETF1": 0.5, "XBB.TO": 0.3, "BTC-USD": 0.2}, holdings=H(rows), universe=UNI, esg_flags=set())
    assert out["sectors"] == pytest.approx({"Information Technology": 0.30, "Financials": 0.20})   # bonds are an asset class
    assert not set(out["sectors"]) & lt.NON_SECTORS

def test_country_rows_remainder_overshoot_and_listing_fallback():
    rows = [("ETF1", "country", "USA", "", 0.90), ("ETF2", "country", "usa", "", 0.5004), ("ETF2", "country", "CAN", "", 0.5),
            ("XBB.TO", "country", "CAN", "", 0.9996), ("GLD", "country", "USA", "", 1.0)]
    out = look_through({"ETF1": 0.3, "ETF2": 0.3, "XBB.TO": 0.2, "GLD": 0.1, "XIU.TO": 0.1},
                       holdings=H(rows + ETF1[:1]), universe=UNI2, esg_flags=set())
    c = out["countries"]
    assert c["OTHER"] == pytest.approx(0.3 * 0.10)                        # ETF1: 10 % unexplained; XBB.TO: 0.04 % is below 0.1 %
    assert c["GLOBAL"] == pytest.approx(0.1)                              # gold is global whatever the file says
    assert c["CAN"] == pytest.approx(0.3 * 0.5 / 1.0004 + 0.2 * 0.9996 + 0.1)   # ETF2 scaled to 100 %; XIU.TO has no rows: listing country
    assert c["USA"] == pytest.approx(0.3 * 0.9 + 0.3 * 0.5004 / 1.0004)
    assert sum(c.values()) == pytest.approx(1.0, abs=2e-4)                # never above 1: rounding overshoot is scaled away
    assert sum(c.values()) <= 1.0 + 1e-12

def test_coverage_and_snapshot_name_held_etfs_with_holding_rows_only():
    rows = [("ETF1", "holding", "NVIDIA", "NVDA", 0.10), ("ETF1", "holding", "Other", "", 0.15),
            ("XIU.TO", "holding", "CNQ", "CNQ.TO", 0.03)]
    frame = H(rows)
    frame.loc[frame.etf == "XIU.TO", "as_of"] = "2026-10-31"
    frame = pd.concat([frame, H([("ETF1", "sector", "Financials", "", 1.0)]).assign(as_of="2026-09-30")], ignore_index=True)
    out = look_through({"ETF1": 0.5, "ETF2": 0.2, "XBB.TO": 0.3}, holdings=frame, universe=UNI2, esg_flags=set())
    assert out["coverage"] == pytest.approx({"ETF1": 0.25, "ETF2": 0.0})  # XIU.TO is not held; ETF2 is held but unknown: 0, not absent
    assert out["snapshot"] == {"ETF1": "2026-11-12"}                      # the holdings' date, not the older sector date
    assert out["as_of"] == "2026-11-12" and "etf_holdings" in out["source"]

def test_esg_indirect_is_energy_or_flagged_names_inside_etfs_only():
    rows = [("ETF1", "holding", "NVIDIA", "NVDA", 0.10), ("ETF1", "holding", "CNQ", "CNQ.TO", 0.02)]
    w = {"ETF1": 0.5, "NVDA": 0.2, "CNQ.TO": 0.3}
    out = look_through(w, holdings=H(rows), universe=UNI, esg_flags={"NVDA"})
    assert out["esg_indirect"] == pytest.approx({"NVDA": 0.05, "CNQ.TO": 0.01})      # the direct lines are esg_direct's job
    assert look_through(w, holdings=H(rows), universe=UNI, esg_flags=set())["esg_indirect"] == pytest.approx({"CNQ.TO": 0.01})

def test_esg_flags_none_reads_the_flag_file_as_of_the_runs_date(monkeypatch):
    import governance
    seen = []
    monkeypatch.setattr(governance, "load_esg_flags", lambda as_of, **kw: seen.append(as_of) or {"NVDA"})
    out = look_through({"ETF1": 1.0}, holdings=H(ETF1), universe=UNI)
    assert out["esg_indirect"] == pytest.approx({"NVDA": 0.10}) and seen == ["2026-11-12"]

def test_wrong_weights_raise_a_plain_error_and_tickers_are_upper_cased():
    for bad in ({"NVDA": 0.5}, {"NVDA": 1.2, "ETF1": -0.2}):
        with pytest.raises(ValueError, match="100 %|0 or more"):
            look_through(bad, holdings=H(ETF1), universe=UNI, esg_flags=set())
    with pytest.raises(ValueError, match="Unknown ticker: FOO"):
        look_through({"NVDA": 0.5, "foo": 0.5}, holdings=H(ETF1), universe=UNI, esg_flags=set())
    assert look_through({"nvda": 1.0}, holdings=H(ETF1), universe=UNI, esg_flags=set())["stocks"]["NVDA"]["direct"] == 1.0

def test_empty_frame_forces_direct_mode_and_none_reads_the_file(monkeypatch, tmp_path):
    path = tmp_path / "etf_holdings.csv"
    H(ETF1).to_csv(path, index=False)
    monkeypatch.setattr(lt, "HOLDINGS_CSV", path)
    w = {"NVDA": 0.4, "ETF1": 0.5, "XBB.TO": 0.1}
    past = look_through(w, holdings=pd.DataFrame(), universe=UNI, esg_flags=set())      # a past as_of: the caller says so
    assert past["mode"] == "direct" and past["stocks"]["NVDA"]["via"] == [] and past["as_of"] == "2026-11-12"
    assert past["source"] == "assets_universe.csv (direct holdings, no ETF holdings file)"
    assert past["energy_via_etfs"] == 0.0 and past["esg_indirect"] == {} and past["sectors"] == pytest.approx({"Information Technology": 0.4})
    now = look_through(w, universe=UNI, esg_flags=set())
    assert now["mode"] == "lookthrough" and now["as_of"] == "2026-11-12" and "data/etf_holdings.csv" in now["source"]
    assert look_through(w, holdings=H(ETF1).iloc[0:0], universe=UNI, esg_flags=set())["mode"] == "direct"

def test_direct_mode_as_of_is_the_dataset_end():
    from tools.data import DATASET_END
    assert look_through({"NVDA": 1.0}, holdings=pd.DataFrame(), universe=UNI, esg_flags=set())["as_of"] == DATASET_END

def test_load_holdings_normalizes_each_group_and_cleans_the_file(tmp_path):
    rows = [("XIU.TO", "holding", "ROYAL BANK", "RY.TO", "9.58"), ("XIU.TO", "holding", "BANK OF MONTREAL", "", "68.28"),
            ("XIU.TO", "sector", "Technology", "", "60"), ("XIU.TO", "sector", "Basic Materials", "", "40"),
            ("SPY", "holding", "ALPHABET INC CL C", "", "0.021"), ("SPY", "holding", "APPLE INC", "AAPL", "0.079"),
            ("SPY", "country", "USA", "", "1.0002"), ("SPY", "sector", "Bonds", "", "x"), ("SPY", "sector", "Energy", "", "0"),
            ("SPY", "oddity", "Skipped", "", "0.5")]
    frame = pd.DataFrame([(*r, "2026-11-12", "https://example.test") for r in rows],
                         columns=["etf", "kind", "name", "ticker", "weight", "as_of", "source_url"])
    path = tmp_path / "h.csv"
    frame.to_csv(path, index=False)
    out = load_holdings(path)
    assert list(out.columns) == ["etf", "kind", "name", "ticker", "weight", "as_of", "source_url"]
    xiu = out[out.etf == "XIU.TO"]
    assert xiu.loc[xiu.kind == "holding", "weight"].tolist() == pytest.approx([0.0958, 0.6828])    # percent group: / 100
    assert xiu.loc[xiu.kind == "sector", "name"].tolist() == ["Information Technology", "Materials"]   # ICB -> GICS
    assert xiu.loc[xiu.kind == "sector", "weight"].tolist() == pytest.approx([0.6, 0.4])
    assert xiu.loc[xiu.name == "BANK OF MONTREAL", "ticker"].tolist() == [""]                    # blank ticker is "", never NaN
    spy = out[out.etf == "SPY"]
    assert spy.loc[spy.kind == "country", "weight"].tolist() == [1.0002]                         # a fraction file is untouched
    assert spy.loc[spy.name.str.contains("CL C"), "ticker"].tolist() == ["GOOGL"]                # Alphabet Class C
    assert set(out.kind) == {"holding", "sector", "country"} and (out.weight > 0).all()          # junk rows dropped
    assert load_holdings(tmp_path / "missing.csv") is None

def test_load_holdings_refuses_a_file_without_the_columns(tmp_path):
    path = tmp_path / "h.csv"
    path.write_text("etf,kind,weight\nSPY,holding,0.1\n")
    with pytest.raises(ValueError, match="columns"):
        load_holdings(path)

def test_result_is_json_safe_and_ordered_by_size():
    rows = [("ETF1", "holding", "NVIDIA", "NVDA", 0.10), ("ETF1", "holding", "CNQ", "CNQ.TO", 0.20)]
    out = look_through({"ETF1": 0.6, "NVDA": 0.2, "BTC-USD": 0.2}, holdings=H(rows), universe=UNI, esg_flags=set())
    assert json.loads(json.dumps(out)) == out
    assert list(out["stocks"]) == ["NVDA", "CNQ.TO"]                                           # 0.26 then 0.12
    assert [round(v["total"], 2) for v in out["stocks"].values()] == [0.26, 0.12]


# --- the real local file (skipped on a fresh clone) -----------------------------------------------------
def _raw():
    raw = pd.read_csv(lt.HOLDINGS_CSV, dtype=str, keep_default_na=False)
    return raw.assign(w=raw["weight"].astype(float))

@NEEDS_HOLDINGS
def test_real_file_loads_clean_and_class_c_is_alphabet():
    from tools.data import load_universe
    h = load_holdings()
    assert set(h.kind) == {"holding", "sector", "country"} and h["weight"].between(0, 1.5).all()
    assert set(h.ticker) - {""} <= set(load_universe().ticker)                    # every ticker named is a dataset ticker
    class_c = h[h.name.str.contains("CL C|Class C", case=False) & h.name.str.contains("Alphabet", case=False)]
    assert set(class_c.etf) == {"SPY", "QQQ", "ESGV"} and set(class_c.ticker) == {"GOOGL"}

@NEEDS_HOLDINGS
def test_real_coverage_snapshot_and_alphabet_from_the_raw_rows():
    raw = _raw()
    for etf in ("XIU.TO", "SPY", "QQQ", "ESGV"):
        listed = raw[(raw.etf == etf) & (raw.kind == "holding")]
        out = look_through({etf: 1.0})
        assert out["coverage"] == pytest.approx({etf: listed.w.sum()}) and out["snapshot"] == {etf: listed.as_of.max()}
    assert look_through({"XIU.TO": 1.0})["coverage"]["XIU.TO"] == pytest.approx(0.7786, abs=1e-4)
    assert look_through({"QQQ": 1.0})["coverage"]["QQQ"] == pytest.approx(0.7219, abs=1e-4)      # the red team's 77.9 % / 72.2 %
    for etf in ("SPY", "QQQ", "ESGV"):
        alphabet = raw[(raw.etf == etf) & (raw.kind == "holding") & raw.name.str.contains("alphabet", case=False)]
        assert len(alphabet) == 2                                                    # Class A and Class C
        assert look_through({etf: 1.0})["stocks"]["GOOGL"]["total"] == pytest.approx(alphabet.w.sum())

@NEEDS_HOLDINGS
def test_real_spec_facts_nvidia_inside_the_funds_and_energy_inside_xiu():
    pct = lambda etf, t: round(look_through({etf: 1.0})["stocks"][t]["total"] * 100, 1)
    assert (pct("SPY", "NVDA"), pct("QQQ", "NVDA"), pct("ESGV", "NVDA")) == (6.1, 6.5, 6.6)     # spec 9
    xiu = look_through({"XIU.TO": 1.0})
    assert (round(xiu["stocks"]["ENB.TO"]["total"] * 100, 1), round(xiu["stocks"]["CNQ.TO"]["total"] * 100, 1)) == (3.6, 3.5)
    assert round(xiu["energy_via_etfs"] * 100, 1) == 16.7 and xiu["sectors"]["Energy"] == pytest.approx(xiu["energy_via_etfs"])

@NEEDS_HOLDINGS
def test_real_personas_countries_add_up_to_one_and_robert_after_the_move():
    from tools.portfolio import apply_change
    mixes = [{"XIU.TO": .45, "XBB.TO": .35, "GLD": .10, "ZST.TO": .10},
             {"XIU.TO": .35, "XBB.TO": .35, "CNQ.TO": .08, "MSFT": .10, "GLD": .12},
             {"NVDA": .15, "QQQ": .15, "SHOP.TO": .10, "BTC-USD": .15, "XIU.TO": .30, "XBB.TO": .15},
             {"XIU.TO": .6, "XBB.TO": .3, "ZST.TO": .1}, {"SPY": .5, "ESGV": .5}]
    for mix in mixes:
        out = look_through(mix)
        assert out["mode"] == "lookthrough" and sum(out["countries"].values()) == pytest.approx(1.0, abs=1e-9)
        assert all(v > 0 for v in out["sectors"].values()) and not set(out["sectors"]) & lt.NON_SECTORS
    robert = {"XIU.TO": .45, "XBB.TO": .35, "GLD": .10, "ZST.TO": .10}
    after = look_through(apply_change(robert, {"op": "set", "ticker": "NVDA", "weight": 0.40}))
    assert after["stocks"]["NVDA"] == {"direct": pytest.approx(0.40), "via": [], "total": pytest.approx(0.40)}   # no fund of his holds it
    assert after["sectors"]["Information Technology"] == pytest.approx(0.4259, abs=1e-4) and after["countries"]["GLOBAL"] == pytest.approx(0.06)


# --- fix round 1: as_of is the run's date; a missing sector split is a named gap ------------------------
def test_as_of_is_the_runs_date_and_later_rows_never_reach_the_output(monkeypatch):
    import governance
    from tools.data import DATASET_END
    seen = []
    monkeypatch.setattr(governance, "load_esg_flags", lambda as_of, **kw: seen.append(as_of) or set())
    labels = H([("XBB.TO", "country", "USA", "", 1.0), ("GLD", "sector", "Gold", "", 1.0)]).assign(as_of="2026-11-14")
    frame = pd.concat([H(ETF1), labels], ignore_index=True)             # the fetch day stamps the static label rows
    out = look_through({"ETF1": 0.5, "XBB.TO": 0.3, "GLD": 0.2}, holdings=frame, universe=UNI)
    assert out["as_of"] == DATASET_END == "2026-11-12" and seen == ["2026-11-12"]
    assert out["mode"] == "lookthrough" and out["countries"]["CAN"] == pytest.approx(0.3)   # the 2026-11-14 USA row is ignored
    assert out["countries"]["USA"] == pytest.approx(0.5)

def test_as_of_keyword_names_the_run_and_the_flag_date(monkeypatch):
    import governance
    seen = []
    monkeypatch.setattr(governance, "load_esg_flags", lambda as_of, **kw: seen.append(as_of) or {"NVDA"})
    out = look_through({"ETF1": 1.0}, holdings=H(ETF1), universe=UNI, as_of="2026-12-01")
    assert out["as_of"] == "2026-12-01" and seen == ["2026-12-01"] and out["mode"] == "lookthrough"
    assert look_through({"ETF1": 1.0}, holdings=H(ETF1), universe=UNI, esg_flags=set(), as_of=pd.Timestamp("2026-11-12"))["as_of"] == "2026-11-12"

def test_a_run_before_the_holdings_snapshot_is_direct_mode_and_says_why():
    w = {"NVDA": 0.4, "ETF1": 0.5, "XBB.TO": 0.1}
    past = look_through(w, holdings=H(ETF1), universe=UNI, esg_flags=set(), as_of="2025-01-31")
    assert past["mode"] == "direct" and past["as_of"] == "2025-01-31" and past["gaps"] == []
    assert past["stocks"]["NVDA"]["via"] == [] and past["coverage"] == {} and past["snapshot"] == {}
    assert past["sectors"] == pytest.approx({"Information Technology": 0.4}) and past["energy_via_etfs"] == 0.0
    assert "2026-11-12" in past["source"] and "2025-01-31" in past["source"] and "no ETF holdings file" not in past["source"]
    eve = look_through(w, holdings=H(ETF1), universe=UNI, esg_flags=set(), as_of="2026-11-11")
    same = look_through(w, holdings=H(ETF1), universe=UNI, esg_flags=set(), as_of="2026-11-12")
    assert eve["mode"] == "direct" and same["mode"] == "lookthrough"       # the snapshot day itself is allowed
    with pytest.raises(ValueError):
        look_through(w, holdings=H(ETF1), universe=UNI, esg_flags=set(), as_of="not a date")

def test_rows_without_a_valid_date_are_not_used():
    frame = H(ETF1 + [("ETF1", "holding", "CNQ", "CNQ.TO", 0.2), ("ETF2", "holding", "NVIDIA", "NVDA", 0.3)])
    frame.loc[frame.name == "CNQ", "as_of"] = ""
    frame.loc[frame.etf == "ETF2", "as_of"] = "soon"                         # a whole group with no usable date
    out = look_through({"ETF1": 0.5, "ETF2": 0.5}, holdings=frame, universe=UNI2, esg_flags=set())
    assert "CNQ.TO" not in out["stocks"] and out["coverage"] == pytest.approx({"ETF1": 0.10, "ETF2": 0.0})
    assert out["stocks"]["NVDA"]["total"] == pytest.approx(0.05)              # ETF2's undated row is not evidence

def test_missing_sector_rows_are_a_named_gap_not_a_silent_zero():
    no_sectors = [r for r in ETF1 if r[1] != "sector"]                       # holdings and countries, no sector split
    w = {"ETF1": 0.5, "ETF2": 0.2, "XBB.TO": 0.3}
    out = look_through(w, holdings=H(no_sectors), universe=UNI2, esg_flags=set())
    assert out["gaps"] == [{"etf": "ETF1", "missing": "sectors", "coverage": 0.0},
                           {"etf": "ETF2", "missing": "holdings", "coverage": 0.0},
                           {"etf": "ETF2", "missing": "sectors", "coverage": 0.0}]
    assert out["mode"] == "lookthrough" and out["sectors"] == {}               # unknown, and said so: not a pass
    assert out["stocks"]["NVDA"]["total"] == pytest.approx(0.05)                # the holdings it does list still count
    assert out["coverage"] == pytest.approx({"ETF1": 0.10, "ETF2": 0.0})
    full = look_through({"ETF1": 0.5, "XBB.TO": 0.5}, holdings=H(ETF1), universe=UNI2, esg_flags=set())
    assert full["gaps"] == []                                                   # a bond ETF has no sector split to miss
    direct = look_through(w, holdings=pd.DataFrame(), universe=UNI2, esg_flags=set())
    assert direct["mode"] == "direct" and direct["gaps"] == []                  # direct mode is its own flag

@NEEDS_HOLDINGS
def test_real_file_has_no_gaps_and_a_file_without_the_qqq_sector_split_names_one():
    mix = {"QQQ": .5, "XIU.TO": .3, "XBB.TO": .2}
    full = look_through(mix)
    assert full["gaps"] == [] and full["sectors"]["Information Technology"] == pytest.approx(0.3509, abs=1e-4)
    h = load_holdings()
    partial = look_through(mix, holdings=h[~((h.etf == "QQQ") & (h.kind == "sector"))])
    assert partial["gaps"] == [{"etf": "QQQ", "missing": "sectors", "coverage": 0.0}]
    assert partial["sectors"]["Information Technology"] == pytest.approx(0.3 * 0.0961, abs=1e-4)   # only XIU.TO's share is known

def test_zero_byte_file_is_direct_mode_not_an_error(monkeypatch, tmp_path):
    path = tmp_path / "etf_holdings.csv"
    path.write_bytes(b"")
    assert load_holdings(path).empty
    monkeypatch.setattr(lt, "HOLDINGS_CSV", path)
    out = look_through({"NVDA": 0.5, "XBB.TO": 0.5}, universe=UNI, esg_flags=set())
    assert out["mode"] == "direct" and out["source"] == "assets_universe.csv (direct holdings, no ETF holdings file)"

def test_two_snapshots_of_one_group_keep_the_newest_and_never_shrink_100x():
    old = H([("XIU.TO", "holding", "CNQ", "CNQ.TO", 0.0300), ("XIU.TO", "holding", "Others", "", 0.7500)]).assign(as_of="2026-10-31")
    new = H([("XIU.TO", "holding", "CNQ", "CNQ.TO", 0.0345), ("XIU.TO", "holding", "Others", "", 0.7441)])
    for frame in (pd.concat([old, new], ignore_index=True), pd.concat([new, old], ignore_index=True)):
        out = look_through({"XIU.TO": 0.5, "XBB.TO": 0.5}, holdings=frame, universe=UNI, esg_flags=set())
        assert out["coverage"] == pytest.approx({"XIU.TO": 0.7786}) and out["snapshot"] == {"XIU.TO": "2026-11-12"}
        assert out["stocks"]["CNQ.TO"]["total"] == pytest.approx(0.5 * 0.0345)
    assert len(lt._normalize(pd.concat([old, new], ignore_index=True))) == 2

def test_source_names_each_snapshot_date_per_kind():
    frame = pd.concat([H(ETF1).assign(as_of="2026-11-12"),
                       H([("ETF1", "sector", "Financials", "", 1.0), ("ETF1", "country", "USA", "", 1.0)]).assign(as_of="2026-10-31"),
                       H([("ETF2", "holding", "NVIDIA", "NVDA", 0.1)])], ignore_index=True)
    frame = frame[~((frame.etf == "ETF1") & frame.kind.isin(["sector", "country"]) & (frame.as_of == "2026-11-12"))]
    out = look_through({"ETF1": 0.5, "ETF2": 0.3, "XBB.TO": 0.2}, holdings=frame, universe=UNI2, esg_flags=set())
    assert "ETF1 holdings 2026-11-12, sectors 2026-10-31, countries 2026-10-31" in out["source"]
    assert "ETF2 holdings 2026-11-12" in out["source"] and "data/etf_holdings.csv" in out["source"]
    assert "one snapshot date per ETF" not in out["source"] and out["snapshot"] == {"ETF1": "2026-11-12", "ETF2": "2026-11-12"}

@NEEDS_HOLDINGS
def test_real_source_lists_the_older_qqq_and_esgv_splits():
    out = look_through({"QQQ": .4, "ESGV": .4, "XIU.TO": .2})
    assert "QQQ holdings 2026-11-12, sectors 2026-10-31, countries 2026-10-31" in out["source"]
    assert "ESGV holdings 2026-11-12, sectors 2026-09-30, countries 2026-11-12" in out["source"]
    assert look_through({"NVDA": 0.5, "QQQ": 0.5}, as_of="2025-01-31")["mode"] == "direct"      # the default demo date
    assert look_through({"NVDA": 0.5, "QQQ": 0.5})["as_of"] == "2026-11-12"


# --- Task 18: ETF look-through validation (snapshot <= as_of, coverage, split sums) -----------------
def test_validate_holdings_reports_coverage_split_sums_and_rows():
    v = lt.validate_holdings("2026-11-12", holdings=H([*ETF1, ("ETF1", "holding", "Apple", "", 0.08)]))
    e = v["etfs"]["ETF1"]
    assert (e["snapshot"], e["rows"], e["flags"]) == ("2026-11-12", 5, [])
    assert (e["coverage"], e["sector_sum"], e["country_sum"]) == (pytest.approx(0.18), pytest.approx(1.0), pytest.approx(1.0))
    assert v["as_of"] == "2026-11-12" and v["source"]


def test_validate_holdings_flags_a_snapshot_after_as_of():
    late = H(ETF1).assign(as_of="2026-11-13")                      # no look-ahead: a later snapshot is flagged
    e = lt.validate_holdings("2026-11-12", holdings=late)["etfs"]["ETF1"]
    assert e["snapshot"] == "2026-11-13" and e["flags"] == ["dated 2026-11-13, after as_of 2026-11-12"]


def test_validate_holdings_normalizes_percent_weights():
    e = lt.validate_holdings("2026-11-12", holdings=H([
        ("XIU.TO", "holding", "Royal Bank", "RY.TO", 7.0), ("XIU.TO", "holding", "Shopify", "SHOP.TO", 6.0),
        ("XIU.TO", "sector", "Financials", "", 33.0), ("XIU.TO", "sector", "Energy", "", 17.0),
        ("XIU.TO", "sector", "Information Technology", "", 50.0), ("XIU.TO", "country", "CAN", "", 100.0)]))["etfs"]["XIU.TO"]
    assert (e["coverage"], e["sector_sum"], e["country_sum"]) == (pytest.approx(0.13), pytest.approx(1.0), pytest.approx(1.0))
    assert e["flags"] == []


def test_validate_holdings_flags_a_missing_or_off_split_and_never_crashes(monkeypatch, tmp_path):
    e = lt.validate_holdings("2026-11-12", holdings=H([
        ("ESGV", "holding", "Apple", "", 0.07), ("ESGV", "sector", "Information Technology", "", 0.90)]))["etfs"]["ESGV"]
    assert (e["sector_sum"], e["country_sum"]) == (pytest.approx(0.90), None)
    assert e["flags"] == ["sector split sums to 90.0 %", "no country split"]
    assert lt.validate_holdings("2026-11-12", holdings=pd.DataFrame())["etfs"] == {}
    monkeypatch.setattr(lt, "HOLDINGS_CSV", tmp_path / "missing.csv")
    absent = lt.validate_holdings()
    assert absent["etfs"] == {} and "absent" in absent["source"]


def test_validate_holdings_does_not_flag_static_label_rows_stamped_with_the_fetch_day():
    labels = H([("GLD", "sector", "Gold", "", 1.0), ("GLD", "country", "GLOBAL", "", 1.0)]).assign(as_of="2026-11-14")
    e = lt.validate_holdings("2026-11-12", holdings=labels)["etfs"]["GLD"]
    assert (e["snapshot"], e["coverage"], e["flags"]) == (None, 0.0, [])     # as look_through: only the holdings snapshot is dated
