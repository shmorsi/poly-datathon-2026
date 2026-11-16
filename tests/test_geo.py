"""Task 7 tests: tools/geo.py, the shockwave (spec section 10; plan A Task 7).

Offline: the Task 6 fixtures (`UNI`, `H`, `ETF1`) and synthetic holdings frames. The cases on the real
local data/etf_holdings.csv skip when it is absent (issuers forbid redistributing it, pitfall 10).
"""
import json

import pandas as pd, pytest
import tools.lookthrough as lt
from tools.geo import FAMILY_SECTORS, country_exposure, transmission, transmission_report
from tools.lookthrough import look_through
from tests.test_lookthrough import UNI, H, ETF1     # reuse the Task 6 fixtures

DIRECT = pd.DataFrame()                                # empty holdings -> direct mode
NEEDS_HOLDINGS = pytest.mark.skipif(not lt.HOLDINGS_CSV.exists(), reason="local ETF holdings absent")


def test_borderless_split():
    w = {"XIU.TO": 0.45, "XBB.TO": 0.35, "GLD": 0.10, "BTC-USD": 0.10}
    out = country_exposure(w, lookthrough=look_through(w, holdings=DIRECT, universe=UNI, esg_flags=set()))
    assert out["countries"] == pytest.approx({"CAN": 0.80})
    assert out["borderless"] == pytest.approx({"CRYPTO": 0.10, "GLOBAL": 0.10})

def test_tariff_event_country_and_currency_channels():
    w = {"XIU.TO": 0.5, "NVDA": 0.3, "GLD": 0.2}
    lk = look_through(w, holdings=DIRECT, universe=UNI, esg_flags=set())
    rows = transmission(w, {"family": "tariffs", "regions": ["USA", "CAN"]}, lookthrough=lk, universe=UNI)
    got = {(r["ticker"], r["channel"], r["via"]): r["weight"] for r in rows}
    assert got == pytest.approx({("XIU.TO", "country", None): 0.5, ("NVDA", "country", None): 0.3,
                                 ("NVDA", "currency", None): 0.3, ("GLD", "currency", None): 0.2})
    assert [r["weight"] for r in rows] == sorted((r["weight"] for r in rows), reverse=True)

def test_chip_event_reaches_a_stock_inside_an_etf():
    w = {"ETF1": 0.5, "XBB.TO": 0.5}
    lk = look_through(w, holdings=H(ETF1), universe=UNI, esg_flags=set())
    rows = transmission(w, {"family": "chips", "regions": "CHN;TWN"}, lookthrough=lk, universe=UNI)
    assert rows == [{"ticker": "NVDA", "channel": "sector", "via": "ETF1", "weight": pytest.approx(0.05)}]

def test_oil_event_direct_and_inside_etf():
    xiu = [("XIU.TO", "holding", "CNQ", "CNQ.TO", 0.0345), ("XIU.TO", "country", "CAN", "", 1.0)]
    w = {"XIU.TO": 0.35, "CNQ.TO": 0.08, "XBB.TO": 0.57}
    lk = look_through(w, holdings=H(xiu), universe=UNI, esg_flags=set())
    rows = transmission(w, {"family": "war_oil", "regions": ["ISR", "IRN"]}, lookthrough=lk, universe=UNI)
    assert {(r["ticker"], r["via"]) for r in rows if r["channel"] == "sector"} == {("CNQ.TO", None), ("CNQ.TO", "XIU.TO")}


# --- beyond the brief: the rules written down in tools/geo.py ------------------------------------------
UNI2 = pd.concat([UNI, pd.DataFrame([r.split(",") for r in [
    "ETF2,Second ETF,etf_equity,NASDAQ,USD,Broad market,USA",
    "XOM,Exxon Mobil,equity,NYSE,USD,Energy,USA",
    "RY.TO,Royal Bank,equity,TSX,CAD,Financials,CAN",
    "ETH-USD,Ether,crypto,Crypto (24/7),USD,Crypto asset,CRYPTO"]], columns=UNI.columns)], ignore_index=True)

def _rows(rows):
    return {(r["ticker"], r["channel"], r["via"]): r["weight"] for r in rows}

def test_family_sectors_are_the_ledger_values():
    assert FAMILY_SECTORS == {"war_oil": "Energy", "chips": "Information Technology"}

def test_gold_is_global_whatever_the_universe_says():       # ruling: load_universe keeps GLD as USA (the listing rule)
    assert UNI.set_index("ticker").at["GLD", "country"] == "USA"
    w = {"GLD": 0.2, "XBB.TO": 0.8}
    out = country_exposure(w, universe=UNI, holdings=DIRECT)
    assert out["countries"] == pytest.approx({"CAN": 0.8}) and out["borderless"] == pytest.approx({"CRYPTO": 0.0, "GLOBAL": 0.2})
    rows = transmission(w, {"family": "tariffs", "regions": ["USA"]}, universe=UNI, holdings=DIRECT)
    assert _rows(rows) == pytest.approx({("GLD", "currency", None): 0.2})      # a USD price, never the USA's country channel

def test_none_reads_the_look_through_and_a_run_before_the_snapshot_is_direct_mode_and_says_so():
    split = [("ETF1", "holding", "NVIDIA", "NVDA", 0.10), ("ETF1", "country", "USA", "", 0.6), ("ETF1", "country", "CAN", "", 0.4)]
    w = {"ETF1": 0.5, "XBB.TO": 0.3, "BTC-USD": 0.2}
    now = country_exposure(w, universe=UNI, holdings=H(split))
    assert now["countries"] == pytest.approx({"CAN": 0.5, "USA": 0.3}) and now["mode"] == "lookthrough"
    assert now["as_of"] == "2026-11-12" and "etf_holdings" in now["source"]
    assert now["gaps"] == [{"etf": "ETF1", "missing": "sectors", "coverage": 0.0}]     # no sector rows for ETF1: said, not dropped
    past = country_exposure(w, universe=UNI, holdings=H(split), as_of="2025-01-31")
    assert past["mode"] == "direct" and past["as_of"] == "2025-01-31"             # holdings are exposure, never a return
    assert past["countries"] == pytest.approx({"USA": 0.5, "CAN": 0.3}) and past["borderless"] == pytest.approx({"CRYPTO": 0.2, "GLOBAL": 0.0})
    assert "2026-11-12" in past["source"] and "2025-01-31" in past["source"]       # the flag says why
    stamp = country_exposure(w, universe=UNI, holdings=H(split), as_of=pd.Timestamp("2026-12-01"))
    assert stamp["as_of"] == "2026-12-01" and stamp["mode"] == "lookthrough"

def test_named_gaps_reach_both_outputs_unchanged_and_as_copies():
    no_sectors = [r for r in ETF1 if r[1] != "sector"]                           # holdings and countries, no sector split
    w = {"ETF1": 0.5, "ETF2": 0.2, "XBB.TO": 0.3}
    lk = look_through(w, holdings=H(no_sectors), universe=UNI2, esg_flags=set())
    want = [{"etf": "ETF1", "missing": "sectors", "coverage": 0.0}, {"etf": "ETF2", "missing": "holdings", "coverage": 0.0},
            {"etf": "ETF2", "missing": "sectors", "coverage": 0.0}]
    assert lk["gaps"] == want
    exp = country_exposure(w, lookthrough=lk)
    assert exp["gaps"] == want and exp["mode"] == "lookthrough" and exp["gaps"] is not lk["gaps"]
    exp["gaps"][0]["missing"] = "changed"
    assert lk["gaps"] == want                                                    # the caller's look-through is never touched
    rows = transmission(w, {"family": "chips", "regions": ["CHN"]}, lookthrough=lk, universe=UNI2, holdings=H(no_sectors))
    assert rows.gaps == want and rows.mode == "lookthrough" and rows.as_of == lk["as_of"] and rows.source == lk["source"]
    own = country_exposure(w, universe=UNI2, holdings=H(no_sectors))             # the same gaps through the None path
    assert own["gaps"] == want
    assert transmission(w, {"family": "chips", "regions": ["CHN"]}, universe=UNI2, holdings=H(no_sectors)).gaps == want
    direct = country_exposure(w, universe=UNI2, holdings=DIRECT)
    assert direct["mode"] == "direct" and direct["gaps"] == []                   # direct mode is its own flag

def test_an_etf_counts_by_its_country_rows_and_a_line_without_rows_by_its_listing_country(monkeypatch, tmp_path):
    split = [("ETF2", "holding", "NVIDIA", "NVDA", 0.10), ("ETF2", "country", "CAN", "", 0.6), ("ETF2", "country", "USA", "", 0.4)]
    w = {"ETF2": 0.5, "XBB.TO": 0.3, "ETF1": 0.2}
    frame, event = H(split), {"family": "rates", "regions": ["CAN"]}
    lk = look_through(w, holdings=frame, universe=UNI2, esg_flags=set())
    rows = transmission(w, event, lookthrough=lk, universe=UNI2, holdings=frame)
    assert _rows(rows) == pytest.approx({("ETF2", "country", None): 0.5 * 0.6, ("XBB.TO", "country", None): 0.3,
                                         ("ETF2", "currency", None): 0.5, ("ETF1", "currency", None): 0.2})
    path = tmp_path / "etf_holdings.csv"
    frame.to_csv(path, index=False)
    monkeypatch.setattr(lt, "HOLDINGS_CSV", path)                       # holdings=None reads the local file
    assert transmission(w, event, lookthrough=lk, universe=UNI2) == rows
    assert transmission(w, event, universe=UNI2) == rows                  # lookthrough=None builds the same look-through
    direct = look_through(w, holdings=DIRECT, universe=UNI2, esg_flags=set())
    flat = transmission(w, event, lookthrough=direct, universe=UNI2, holdings=frame)
    assert ("ETF2", "country", None) not in _rows(flat) and flat.mode == "direct"   # a direct look-through never mixes rows in
    assert _rows(flat)[("XBB.TO", "country", None)] == pytest.approx(0.3)

def test_the_country_rows_of_an_etf_are_read_at_the_look_throughs_own_date():
    fresh = H([("ETF2", "holding", "NVIDIA", "NVDA", 0.10), ("ETF2", "country", "CAN", "", 0.6),
               ("ETF2", "country", "USA", "", 0.4)]).assign(as_of="2026-11-14")     # a snapshot newer than DATASET_END
    w, event = {"ETF2": 1.0}, {"family": "rates", "regions": ["CAN"]}
    lk = look_through(w, holdings=fresh, universe=UNI2, esg_flags=set(), as_of="2026-12-01")
    assert lk["mode"] == "lookthrough"
    rows = transmission(w, event, lookthrough=lk, universe=UNI2, holdings=fresh)
    assert _rows(rows) == pytest.approx({("ETF2", "country", None): 0.6, ("ETF2", "currency", None): 1.0}) and rows.mode == "lookthrough"
    assert _rows(transmission(w, event, universe=UNI2, holdings=fresh, as_of="2026-12-01")) == _rows(rows)
    early = transmission(w, event, universe=UNI2, holdings=fresh, as_of="2026-11-13")     # the snapshot is newer than this run
    assert early.mode == "direct" and ("ETF2", "country", None) not in _rows(early)

def test_other_crypto_and_gold_are_never_inside_an_events_regions():
    half = [("ETF2", "country", "CAN", "", 0.5)]                          # the other 50 % of ETF2 becomes "OTHER"
    w = {"ETF2": 0.6, "XBB.TO": 0.4}
    rows = transmission(w, {"family": "rates", "regions": ["CAN", "OTHER"]}, universe=UNI2, holdings=H(half))
    assert _rows(rows) == pytest.approx({("ETF2", "country", None): 0.3, ("XBB.TO", "country", None): 0.4, ("ETF2", "currency", None): 0.6})
    mix = {"BTC-USD": 0.2, "GLD": 0.2, "ETH-USD": 0.1, "NVDA": 0.5}
    rows = transmission(mix, {"family": "tariffs", "regions": "CRYPTO;GLOBAL;USA"}, universe=UNI2, holdings=DIRECT)
    got = _rows(rows)
    assert {k for k in got if k[1] == "country"} == {("NVDA", "country", None)}
    assert {k[0] for k in got if k[1] == "currency"} == {"BTC-USD", "GLD", "ETH-USD", "NVDA"}      # USD-priced, crypto included

def test_currency_channel_needs_the_usa_or_canada_and_only_usd_lines():
    w = {"NVDA": 0.3, "BTC-USD": 0.1, "GLD": 0.1, "RY.TO": 0.3, "XBB.TO": 0.2}
    asia = transmission(w, {"family": "chips", "regions": ["CHN", "TWN"]}, universe=UNI2, holdings=DIRECT)
    assert [r for r in asia if r["channel"] == "currency"] == []             # the loonie moves on US or Canadian news only
    usd = {"NVDA", "BTC-USD", "GLD"}
    for regions in (["can"], " TWN; can ", "TWN,usa", ("USA",), {"CHN", "usa"}):   # case, spaces, ; or , strings, tuple, set
        rows = transmission(w, {"family": "rates", "regions": regions}, universe=UNI2, holdings=DIRECT)
        assert {r["ticker"] for r in rows if r["channel"] == "currency"} == usd
        assert all(r["via"] is None for r in rows if r["channel"] == "currency")
    euro = pd.concat([UNI2, pd.DataFrame([["SAP.DE", "SAP", "equity", "Xetra", "EUR", "Information Technology", "DEU"]], columns=UNI2.columns)], ignore_index=True)
    mixed = transmission({"SAP.DE": 0.5, "NVDA": 0.5}, {"family": "rates", "regions": ["CAN"]}, universe=euro, holdings=DIRECT)
    assert _rows(mixed) == pytest.approx({("NVDA", "currency", None): 0.5})     # USD-priced only: a euro line is not the loonie's business
    for blank in ({"family": "rates"}, {"family": "rates", "regions": None}, {"family": "rates", "regions": ""},
                  {"family": "rates", "regions": float("nan")}, {"family": "rates", "regions": []}):
        assert transmission(w, blank, universe=UNI2, holdings=DIRECT) == []     # no region, no channel

def test_sector_channel_follows_the_family_and_names_the_etf():
    xom = [("ETF1", "holding", "CNQ", "CNQ.TO", 0.0009), ("ETF1", "holding", "Exxon", "XOM", 0.0011),
           ("ETF1", "holding", "NVIDIA", "NVDA", 0.10), ("ETF2", "holding", "NVIDIA", "NVDA", 0.10)]
    w = {"ETF1": 0.5, "ETF2": 0.3, "XOM": 0.2}
    frame = H(xom)
    oil = transmission(w, {"family": " War_Oil ", "regions": ["IRN"]}, universe=UNI2, holdings=frame)
    assert _rows(oil) == pytest.approx({("XOM", "sector", None): 0.2, ("XOM", "sector", "ETF1"): 0.5 * 0.0011})   # CNQ.TO: 0.00045 < 0.0005
    chips = transmission(w, {"family": "chips", "regions": ["TWN"]}, universe=UNI2, holdings=frame)
    assert [(r["ticker"], r["via"]) for r in chips] == [("NVDA", "ETF1"), ("NVDA", "ETF2")]    # 0.05 then 0.03: size order
    for family in ("tariffs", "rates", "weather", None):
        event = {"family": family, "regions": ["IRN"]}
        assert [r for r in transmission(w, event, universe=UNI2, holdings=frame) if r["channel"] == "sector"] == []
    assert [r for r in transmission(w, {"regions": ["IRN"]}, universe=UNI2, holdings=frame) if r["channel"] == "sector"] == []

def test_rows_are_sorted_by_size_then_deterministically_and_dust_is_dropped():
    both = [("ETF1", "holding", "NVIDIA", "NVDA", 0.10), ("ETF2", "holding", "NVIDIA", "NVDA", 0.10),
            ("ETF1", "holding", "Exxon", "XOM", 0.0099), ("ETF2", "holding", "Exxon", "XOM", 0.0101)]
    w = {"ETF2": 0.5, "ETF1": 0.5}
    rows = transmission(w, {"family": "chips", "regions": ["CHN"]}, universe=UNI2, holdings=H(both))
    assert [(r["ticker"], r["channel"], r["via"]) for r in rows] == [("NVDA", "sector", "ETF1"), ("NVDA", "sector", "ETF2")]   # a tie: by ETF
    oil = transmission(w, {"family": "war_oil", "regions": ["IRN"]}, universe=UNI2, holdings=H(both))
    assert [(r["via"], round(r["weight"], 5)) for r in oil] == [("ETF2", 0.00505), ("ETF1", 0.00495)]
    assert all(r["weight"] >= 0.0005 for r in rows + oil)
    tie = transmission({"XOM": 0.5, "NVDA": 0.5}, {"family": "tariffs", "regions": ["USA"]}, universe=UNI2, holdings=DIRECT)
    assert [(r["ticker"], r["channel"]) for r in tie] == [("NVDA", "country"), ("NVDA", "currency"), ("XOM", "country"), ("XOM", "currency")]

def test_an_event_dated_after_the_runs_date_is_refused_red_gate_3():
    w = {"NVDA": 1.0}
    late = {"family": "tariffs", "regions": ["USA"], "date": "2025-03-04"}
    lk = look_through(w, holdings=DIRECT, universe=UNI2, esg_flags=set(), as_of="2025-01-31")
    with pytest.raises(ValueError, match="2025-03-04.*2025-01-31"):
        transmission(w, late, lookthrough=lk, universe=UNI2)
    with pytest.raises(ValueError, match="2025-03-04.*2025-01-31"):          # the None path takes the run's date too
        transmission(w, late, universe=UNI2, holdings=DIRECT, as_of="2025-01-31")
    same_day = transmission(w, {**late, "date": "2025-01-31"}, lookthrough=lk, universe=UNI2)
    assert same_day.as_of == "2025-01-31" and len(same_day) == 2             # the day itself is known
    for date in (None, "", float("nan")):                                    # no date at all (a headline): nothing to refuse on
        assert len(transmission(w, {**late, "date": date}, lookthrough=lk, universe=UNI2)) == 2

def test_wrong_weights_and_unknown_tickers_raise_plain_errors_and_tickers_are_upper_cased():
    event = {"family": "tariffs", "regions": ["USA"]}
    lk = look_through({"NVDA": 1.0}, holdings=DIRECT, universe=UNI2, esg_flags=set())
    for bad in ({"NVDA": 0.5}, {"NVDA": 1.2, "ETF1": -0.2}):
        with pytest.raises(ValueError, match="100 %|0 or more"):
            transmission(bad, event, lookthrough=lk, universe=UNI2)
        with pytest.raises(ValueError, match="100 %|0 or more"):
            transmission(bad, event, universe=UNI2, holdings=DIRECT)
        with pytest.raises(ValueError, match="100 %|0 or more"):
            country_exposure(bad, universe=UNI2, holdings=DIRECT)
    with pytest.raises(ValueError, match="Unknown ticker: FOO"):
        transmission({"NVDA": 0.5, "foo": 0.5}, event, lookthrough=lk, universe=UNI2)
    with pytest.raises(ValueError, match="Unknown ticker: FOO"):
        country_exposure({"NVDA": 0.5, "foo": 0.5}, universe=UNI2, holdings=DIRECT)
    assert [r["ticker"] for r in transmission({"nvda": 1.0}, event, universe=UNI2, holdings=DIRECT)] == ["NVDA", "NVDA"]

def test_countries_and_borderless_add_up_to_one_other_stays_in_countries():
    w = {"ETF1": 0.6, "GLD": 0.1, "BTC-USD": 0.1, "XBB.TO": 0.2}
    out = country_exposure(w, universe=UNI, holdings=H([("ETF1", "country", "USA", "", 0.9)]))
    assert out["countries"] == pytest.approx({"USA": 0.54, "CAN": 0.2, "OTHER": 0.06})
    assert list(out["countries"]) == ["USA", "CAN", "OTHER"]                  # biggest first, as the look-through orders them
    assert out["borderless"] == pytest.approx({"CRYPTO": 0.1, "GLOBAL": 0.1}) and list(out["borderless"]) == ["CRYPTO", "GLOBAL"]
    assert sum(out["countries"].values()) + sum(out["borderless"].values()) == pytest.approx(1.0)

def test_outputs_are_json_safe_the_ledger_shape_plus_mode_and_gaps_and_rows_stay_a_plain_list():
    import copy
    w = {"ETF1": 0.5, "NVDA": 0.2, "BTC-USD": 0.2, "XBB.TO": 0.1}
    lk = look_through(w, holdings=H(ETF1), universe=UNI, esg_flags=set())
    exp = country_exposure(w, lookthrough=lk)
    assert set(exp) == {"countries", "borderless", "source", "as_of", "mode", "gaps"} and json.loads(json.dumps(exp)) == exp
    rows = transmission(w, {"family": "chips", "regions": "CHN;TWN"}, lookthrough=lk, universe=UNI)
    assert isinstance(rows, list) and json.loads(json.dumps(rows)) == rows
    assert all(set(r) == {"ticker", "channel", "via", "weight"} for r in rows) and len(rows) == 2     # NVDA direct and inside ETF1
    clone = copy.deepcopy(rows)
    assert clone == rows and clone.gaps == rows.gaps and clone.mode == "lookthrough"


# --- fix round 1 (review of a330ecc): the run's date wins, the report carries the flags, an unreadable date is refused ---
def test_the_runs_date_wins_over_a_supplied_look_through():
    w = {"NVDA": 0.6, "XBB.TO": 0.4}
    lk = look_through(w, holdings=DIRECT, universe=UNI2, esg_flags=set())      # the brief's recipe for a past run: labelled 2026-11-12
    assert lk["as_of"] == "2026-11-12"
    late = {"family": "tariffs", "regions": ["USA"], "date": "2025-03-04"}
    for call in (transmission, transmission_report):
        with pytest.raises(ValueError, match="2025-03-04.*2025-01-31"):          # a later event never reaches the output
            call(w, late, lookthrough=lk, universe=UNI2, holdings=DIRECT, as_of="2025-01-31")
    with pytest.raises(ValueError, match="2025-03-04.*2025-01-31"):
        transmission(w, late, lookthrough=lk, universe=UNI2, as_of="2025-01-31")  # the brief's call shape, no holdings=
    rows = transmission(w, {**late, "date": "2025-01-31"}, lookthrough=lk, universe=UNI2, holdings=DIRECT, as_of="2025-01-31")
    assert rows.as_of == "2025-01-31" and rows.mode == "direct" and len(rows) == 2     # the day itself is known
    out = country_exposure(w, lookthrough=lk, universe=UNI2, holdings=DIRECT, as_of=pd.Timestamp("2025-01-31"))
    assert out["as_of"] == "2025-01-31" and out["mode"] == "direct" and out["countries"] == pytest.approx({"USA": 0.6, "CAN": 0.4})
    with pytest.raises(ValueError):
        country_exposure(w, lookthrough=lk, universe=UNI2, as_of="not a date")

def test_a_real_look_through_dated_after_the_run_is_never_relabelled_it_is_rebuilt_as_direct_holdings():
    split = [("ETF1", "holding", "NVIDIA", "NVDA", 0.10), ("ETF1", "country", "USA", "", 0.6), ("ETF1", "country", "CAN", "", 0.4)]
    mix, frame = {"ETF1": 0.5, "XBB.TO": 0.5}, H(split)
    real = look_through(mix, holdings=frame, universe=UNI2, esg_flags=set())
    assert real["mode"] == "lookthrough" and real["countries"] == pytest.approx({"CAN": 0.7, "USA": 0.3})
    out = country_exposure(mix, lookthrough=real, universe=UNI2, holdings=frame, as_of="2025-01-31")
    assert out["mode"] == "direct" and out["as_of"] == "2025-01-31"             # holdings are exposure, never a return (spec 10)
    assert out["countries"] == pytest.approx({"USA": 0.5, "CAN": 0.5})           # the ETF is its listing market, not a 2026 country split
    assert "2026-11-12" in out["source"] and "2025-01-31" in out["source"]
    rows = transmission(mix, {"family": "rates", "regions": ["CAN"]}, lookthrough=real, universe=UNI2, holdings=frame, as_of="2025-01-31")
    assert rows.mode == "direct" and rows.as_of == "2025-01-31" and ("ETF1", "country", None) not in _rows(rows)

def test_a_look_through_dated_like_the_run_is_used_as_it_is_and_an_older_one_keeps_its_earlier_date():
    split = [("ETF1", "holding", "NVIDIA", "NVDA", 0.10), ("ETF1", "country", "USA", "", 0.6), ("ETF1", "country", "CAN", "", 0.4)]
    mix, frame = {"ETF1": 0.5, "XBB.TO": 0.5}, H(split)
    real = look_through(mix, holdings=frame, universe=UNI2, esg_flags=set())
    marked = {**real, "source": "the caller's own look-through"}
    for stated in ("2026-11-12", pd.Timestamp("2026-11-12"), None):
        kept = country_exposure(mix, lookthrough=marked, universe=UNI2, holdings=frame, as_of=stated)
        assert kept["source"] == "the caller's own look-through" and kept["mode"] == "lookthrough" and kept["as_of"] == "2026-11-12"
    # ledger 30: when both are given, the EARLIER date guards and labels the output
    old = look_through(mix, holdings=frame, universe=UNI2, esg_flags=set(), as_of="2025-01-31")
    assert old["mode"] == "direct" and old["as_of"] == "2025-01-31"
    june = {"family": "tariffs", "regions": ["USA"], "date": "2026-06-01"}
    for stated in (None, "2026-11-12"):
        with pytest.raises(ValueError, match="2026-06-01.*2025-01-31"):          # the look-through's date is the earlier one
            transmission(mix, june, lookthrough=old, universe=UNI2, holdings=frame, as_of=stated)
    january = {**june, "date": "2025-01-15"}
    rows = transmission(mix, january, lookthrough=old, universe=UNI2, holdings=frame, as_of="2026-11-12")
    assert rows.as_of == "2025-01-31" and rows.mode == "direct"
    assert _rows(rows)[("ETF1", "country", None)] == pytest.approx(0.5)             # its listing market, not 0.5 x the 60 % USA split
    out = country_exposure(mix, lookthrough=old, universe=UNI2, holdings=frame, as_of="2026-11-12")
    assert out["as_of"] == "2025-01-31" and out["mode"] == "direct" and out["countries"] == pytest.approx({"USA": 0.5, "CAN": 0.5})
    # and the later look-through is replaced by one built at the earlier date (test above): the earlier date wins both ways
    later = transmission(mix, january, lookthrough=real, universe=UNI2, holdings=frame, as_of="2025-01-31")
    assert later.as_of == "2025-01-31" and later.mode == "direct"

def test_transmission_report_carries_the_flags_with_the_rows_through_json_and_reshaping():
    no_sectors = [r for r in ETF1 if r[1] != "sector"]                           # holdings and countries, no sector split
    w, frame = {"ETF1": 0.5, "ETF2": 0.2, "XBB.TO": 0.3}, H(no_sectors)
    lk = look_through(w, holdings=frame, universe=UNI2, esg_flags=set())
    event = {"family": "chips", "regions": "CHN;TWN;USA"}
    report = transmission_report(w, event, lookthrough=lk, universe=UNI2, holdings=frame)
    assert set(report) == {"rows", "gaps", "mode", "source", "as_of"}
    assert type(report["rows"]) is list and report["rows"] and all(set(r) == {"ticker", "channel", "via", "weight"} for r in report["rows"])
    assert type(report["rows"][0]) is dict
    assert report["gaps"] == lk["gaps"] != [] and report["gaps"] is not lk["gaps"]
    assert (report["mode"], report["source"], report["as_of"]) == (lk["mode"], lk["source"], lk["as_of"])
    assert json.loads(json.dumps(report)) == report                              # the saved Result keeps rows and flags together
    compat = transmission(w, event, lookthrough=lk, universe=UNI2, holdings=frame)
    assert list(compat) == report["rows"] and compat.gaps == report["gaps"] and compat.mode == report["mode"]
    assert json.loads(json.dumps(compat)) == report["rows"]                      # the list subclass loses them in JSON: why the report exists
    assert not hasattr(list(compat), "gaps") and not hasattr(compat[:1], "gaps") and not hasattr([x for x in compat], "mode")
    assert transmission_report(w, event, universe=UNI2, holdings=frame) == report         # lookthrough=None builds the same one
    flat = transmission_report(w, event, universe=UNI2, holdings=DIRECT)
    assert flat["mode"] == "direct" and flat["gaps"] == [] and all(r["via"] is None for r in flat["rows"])
    with pytest.raises(ValueError, match="Unknown ticker: FOO"):
        transmission_report({"NVDA": 0.5, "foo": 0.5}, event, universe=UNI2, holdings=DIRECT)

def test_an_unreadable_event_date_is_refused_but_a_missing_one_is_not():       # red gate 3: a date we cannot read could be a later one
    w = {"NVDA": 1.0}
    lk = look_through(w, holdings=DIRECT, universe=UNI2, esg_flags=set(), as_of="2025-01-31")
    base = {"family": "tariffs", "regions": ["USA"]}
    for date in ("soon", "2025/03/04", "03-04-2025", "2024-02-30", "2024-00-10", "2024-13-01", "20240304", 20240304):
        with pytest.raises(ValueError, match="is not a date"):                      # also the unreadable dates that sort before the run
            transmission(w, {**base, "date": date}, lookthrough=lk, universe=UNI2)
        with pytest.raises(ValueError, match="is not a date"):
            transmission_report(w, {**base, "date": date}, universe=UNI2, holdings=DIRECT, as_of="2025-01-31")
    for date in (None, "", "  ", float("nan"), pd.Timestamp("2025-01-31"), "2025-01-31 10:00"):
        assert len(transmission(w, {**base, "date": date}, lookthrough=lk, universe=UNI2)) == 2
    assert len(transmission(w, base, lookthrough=lk, universe=UNI2)) == 2         # no date key at all: a headline
    with pytest.raises(ValueError, match="2025-03-04"):
        transmission(w, {**base, "date": pd.Timestamp("2025-03-04")}, lookthrough=lk, universe=UNI2)


# --- the real local file and the real catalog (skipped on a fresh clone) --------------------------------
def _event(event_id):                          # a data/events.csv row as the pipeline passes it: regions is the ";" string
    table = pd.read_csv(lt.ROOT / "data" / "events.csv", dtype=str, keep_default_na=False)
    row = table[table.event_id == event_id].iloc[0]
    return {"event_id": event_id, "family": row.family, "regions": row.regions, "date": row.date}

def _oracle_country(mix, regions):             # w x (the share of the line inside the regions), from one-line look-throughs
    inside = set(regions.split(";")) - {"GLOBAL", "CRYPTO", "OTHER"}
    got = {(t, "country", None): w * sum(v for c, v in look_through({t: 1.0})["countries"].items() if c in inside)
           for t, w in mix.items()}
    return {k: v for k, v in got.items() if v >= 0.0005}

MIXES = [{"XIU.TO": .45, "XBB.TO": .35, "GLD": .10, "ZST.TO": .10},
         {"XIU.TO": .35, "XBB.TO": .35, "CNQ.TO": .08, "MSFT": .10, "GLD": .12},
         {"NVDA": .15, "QQQ": .15, "SHOP.TO": .10, "BTC-USD": .15, "XIU.TO": .30, "XBB.TO": .15},
         {"XIU.TO": .6, "XBB.TO": .3, "ZST.TO": .1}, {"SPY": .5, "ESGV": .5}]

@NEEDS_HOLDINGS
def test_real_mateo_oil_shock_reaches_canadian_energy_inside_xiu_and_the_dollar():
    mateo, event = MIXES[1], _event("iran_2026")                              # war_oil; USA;ISR;IRN
    rows = transmission(mateo, event)
    xiu, got = look_through({"XIU.TO": 1.0})["stocks"], _rows(rows)
    by = lambda channel: {k: v for k, v in got.items() if k[1] == channel}
    assert by("sector") == pytest.approx({("CNQ.TO", "sector", None): 0.08, ("CNQ.TO", "sector", "XIU.TO"): 0.35 * xiu["CNQ.TO"]["total"],
                                          ("ENB.TO", "sector", "XIU.TO"): 0.35 * xiu["ENB.TO"]["total"]})
    assert by("country") == pytest.approx(_oracle_country(mateo, event["regions"])) and ("MSFT", "country", None) in got
    assert by("currency") == pytest.approx({("MSFT", "currency", None): 0.10, ("GLD", "currency", None): 0.12})
    assert ("GLD", "country", None) not in got                                 # gold is global, not the USA
    assert rows.mode == "lookthrough" and rows.gaps == [] and rows.as_of == "2026-11-12"

@NEEDS_HOLDINGS
def test_real_robert_tariff_shock_and_amira_chip_shock_follow_the_one_line_look_throughs():
    robert, event = MIXES[0], _event("canada_50_2026")                        # tariffs; USA;CAN
    got = _rows(transmission(robert, event))
    assert {k: v for k, v in got.items() if k[1] == "country"} == pytest.approx(_oracle_country(robert, event["regions"]))
    assert {k: v for k, v in got.items() if k[1] == "currency"} == pytest.approx({("GLD", "currency", None): 0.10})
    assert not [k for k in got if k[1] == "sector"]                            # tariffs have no sector link
    amira, chips = MIXES[2], _event("chips_2022")                              # chips; USA;CHN;TWN
    rows = transmission(amira, chips)
    sectors = {(r["ticker"], r["via"]) for r in rows if r["channel"] == "sector"}
    assert {("NVDA", None), ("SHOP.TO", None)} <= sectors and ("NVDA", "QQQ") in sectors and ("AAPL", "QQQ") in sectors
    assert {k: v for k, v in _rows(rows).items() if k[1] == "country"} == pytest.approx(_oracle_country(amira, chips["regions"]))
    assert _rows(rows)[("BTC-USD", "currency", None)] == pytest.approx(0.15) and ("BTC-USD", "country", None) not in _rows(rows)

@NEEDS_HOLDINGS
def test_real_country_exposure_recombines_the_look_through_for_every_persona_mix():
    for mix in MIXES:
        look, out = look_through(mix), country_exposure(mix)
        assert out["mode"] == "lookthrough" and out["gaps"] == [] and out["as_of"] == look["as_of"] == "2026-11-12"
        recombined = {**out["countries"], **{k: v for k, v in out["borderless"].items() if v}}
        assert recombined == pytest.approx(look["countries"]) and sum(recombined.values()) == pytest.approx(1.0, abs=1e-9)
        assert not {"CRYPTO", "GLOBAL"} & set(out["countries"]) and country_exposure(mix, lookthrough=look) == out
    assert country_exposure(MIXES[2])["borderless"] == pytest.approx({"CRYPTO": 0.15, "GLOBAL": 0.0})
    assert country_exposure(MIXES[0])["borderless"] == pytest.approx({"CRYPTO": 0.0, "GLOBAL": 0.10})

@NEEDS_HOLDINGS
def test_real_run_before_the_snapshot_uses_direct_holdings_flagged_and_names_no_stock_inside_an_etf():
    amira, event = MIXES[2], _event("tariff_threat_2024")                      # 2024-11-26, before the 2025-01-31 run
    rows = transmission(amira, event, as_of="2025-01-31")
    assert rows.mode == "direct" and rows.as_of == "2025-01-31" and "2026-11-12" in rows.source and all(r["via"] is None for r in rows)
    out = country_exposure(amira, as_of="2025-01-31")
    assert out["mode"] == "direct" and out["as_of"] == "2025-01-31" and out["gaps"] == []
    assert out["countries"] == pytest.approx({"CAN": 0.55, "USA": 0.30}) and out["borderless"]["CRYPTO"] == pytest.approx(0.15)
    with pytest.raises(ValueError, match="after"):
        transmission(amira, _event("tariffs_order_2025"), as_of="2025-01-31")  # dated 2025-02-03: not known on 2025-01-31

@NEEDS_HOLDINGS
def test_real_report_matches_the_list_and_survives_json_with_its_flags():
    mateo, event = MIXES[1], _event("iran_2026")
    report = transmission_report(mateo, event)
    assert set(report) == {"rows", "gaps", "mode", "source", "as_of"} and type(report["rows"]) is list
    assert report["rows"] == list(transmission(mateo, event)) and report["mode"] == "lookthrough" and report["gaps"] == []
    assert report["as_of"] == "2026-11-12" and "etf_holdings" in report["source"]
    assert json.loads(json.dumps(report)) == report
    past = transmission_report(MIXES[2], _event("tariff_threat_2024"), as_of="2025-01-31")        # before the snapshot: direct, flagged
    assert past["mode"] == "direct" and past["as_of"] == "2025-01-31" and "2026-11-12" in past["source"]
    assert json.loads(json.dumps(past)) == past and all(r["via"] is None for r in past["rows"])
    stale = look_through(MIXES[2])                                                                  # dated 2026-11-12, after the run
    again = transmission_report(MIXES[2], _event("tariff_threat_2024"), lookthrough=stale, as_of="2025-01-31")
    assert again == past                                                                            # the earlier date wins: same report
