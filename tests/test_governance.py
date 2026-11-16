"""Finance truth for the rules engine (workstream C). Section 1: data/personas.json (plan C Task 1).

data/personas.json is read by B's governance.load_limits and aligned_allocation and by D's GET /api/pilots,
so its shape is the interface ledger section 3 and its numbers are spec sections 3, 5 and 10. Plan C Tasks 3
and 7 append their sections to this file and reuse UNIVERSE_31, PERSONAS and ADVICE_WORDS. Section 1 is
offline: it reads only the JSON file. Section 2 (plan C Task 3, data/esg_flags.csv) is offline too, except one
test that reads the starter universe and skips without it. Section 3 (plan C Task 4, scripts/fetch_holdings.py)
tests the issuer-file parsers on synthetic fixtures built in the tests (no issuer file is committed) and, when the
local never-committed data/etf_holdings.csv exists, the facts it carries; that test skips on a fresh clone.
Section 4 (plan C Task 7) is the checklist truth: the limits, the section 5 rows, the verdict, offline on hand-built
`analysis` dicts, then the real-data pilots through governance.evaluate (they need the local data and skip without it).
"""
import io
import json
import os
import re
import struct
import tracemalloc
import zipfile
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse
from xml.sax.saxutils import escape

import pandas as pd
import pytest

NEEDS_DATA = pytest.mark.skipif(not Path("data/starter/prices_daily.csv").exists(), reason="starter data not present")
NEEDS_HOLDINGS = pytest.mark.skipif(
    not (Path("data/starter/prices_daily.csv").exists() and Path("data/etf_holdings.csv").exists()),
    reason="starter data or local ETF holdings not present")
PERSONAS = json.loads(Path("data/personas.json").read_text(encoding="utf-8"))
ADVICE_WORDS = re.compile(r"\b(buy|sell|hold|should)\b", re.I)
# The 31 tickers of data/starter/assets_universe.csv (spec section 9): 10 CA equities, 10 US equities, 9 ETFs, 2 crypto.
UNIVERSE_31 = {
    "RY.TO", "TD.TO", "MFC.TO", "ENB.TO", "CNQ.TO", "CNR.TO", "FTS.TO", "ATD.TO", "SHOP.TO", "CSU.TO",
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "TSLA", "JPM", "JNJ", "PG", "XOM",
    "XIU.TO", "SPY", "QQQ", "ESGV", "XBB.TO", "ZST.TO", "AGG", "TLT", "GLD",
    "BTC-USD", "ETH-USD",
}
assert len(UNIVERSE_31) == 31

PROFILE_KEYS = {"goal", "horizon_years", "risk", "esg", "crypto", "capacity", "reaction_2022"}
REACTION_TO_RISK = {"sold": "low", "held": "moderate", "bought": "high"}  # spec section 5: "In 2022, when markets fell, you..."

# Spec section 3 (the plans), with the lead's ruling of Sat 18:50: the "too Canadian" investor holds 60 % XIU.TO,
# 30 % XBB.TO and 10 % ZST.TO (no single stock, so the diversification lesson is clean), with Mateo's band and
# capacity and no ESG screen.
EXPECTED_PROFILES = {
    "robert": {"goal": "preservation", "horizon_years": 4, "risk": "moderate", "esg": False, "crypto": False,
               "capacity": 90000, "reaction_2022": "held"},
    "mateo": {"goal": "balance", "horizon_years": 10, "risk": "moderate", "esg": True, "crypto": False,
              "capacity": 62500, "reaction_2022": "held"},
    "amira": {"goal": "growth", "horizon_years": 15, "risk": "high", "esg": False, "crypto": True,
              "capacity": 36000, "reaction_2022": "bought"},
    "canadian": {"goal": "balance", "horizon_years": 10, "risk": "moderate", "esg": False, "crypto": False,
                 "capacity": 62500, "reaction_2022": "held"},
}
# Spec section 10 `aligned_allocation`. The earlier `high` line summed to 95 %; the lead's fix (Sat 18:50) is
# 15 XBB.TO / 30 XIU.TO / 20 SPY / 25 QQQ / 10 GLD (not ZST.TO), crypto yes takes 10 % BTC-USD out of QQQ, and
# ESG yes lets ESGV replace SPY and take XIU.TO's share. high_esg was re-ruled by the lead (Sat 19:20) to
# 20 XBB.TO / 50 ESGV / 20 QQQ / 10 GLD: at 25 % QQQ the look-through Information Technology share was 41.4 %,
# over the high band's 40 % cap, and a mix must pass its own profile (adjust the mix, never the limits).
EXPECTED_MIXES = {
    "low": {"XBB.TO": 0.25, "ZST.TO": 0.25, "XIU.TO": 0.25, "SPY": 0.15, "GLD": 0.10},
    "moderate": {"XBB.TO": 0.30, "XIU.TO": 0.35, "SPY": 0.25, "GLD": 0.10},
    "moderate_esg": {"XBB.TO": 0.35, "ESGV": 0.55, "GLD": 0.10},
    "high": {"XBB.TO": 0.15, "XIU.TO": 0.30, "SPY": 0.20, "QQQ": 0.25, "GLD": 0.10},
    "high_crypto": {"XBB.TO": 0.15, "XIU.TO": 0.30, "SPY": 0.20, "QQQ": 0.15, "BTC-USD": 0.10, "GLD": 0.10},
    "high_esg": {"XBB.TO": 0.20, "ESGV": 0.50, "QQQ": 0.20, "GLD": 0.10},
}


def _strings(x):
    """Every string value in a nested dict/list (keys excluded)."""
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from _strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from _strings(v)


def test_personas_top_level_and_limits_match_spec_5():
    assert set(PERSONAS) == {"_note", "risk_levels", "thresholds", "pilots", "storm_cards", "illustration_mixes"}
    assert PERSONAS["risk_levels"] == {
        "low": {"max_drawdown": -0.15, "max_single_stock": 0.10, "max_sector": 0.30, "max_crypto": 0.0},
        "moderate": {"max_drawdown": -0.25, "max_single_stock": 0.10, "max_sector": 0.35, "max_crypto": 0.0},
        "high": {"max_drawdown": -0.45, "max_single_stock": 0.20, "max_sector": 0.40, "max_crypto": 0.10}}
    assert PERSONAS["thresholds"] == {
        "scenario_stress_fraction": 0.5, "esg_indirect_warn": 0.01, "rounding_pp": 0.1,
        "recovery_fraction_of_horizon": 0.3333, "short_horizon_years": 3, "risk_share_warn": 0.5}


def test_pilots_flight_plans_match_spec_3():
    p = PERSONAS["pilots"]
    assert set(p) == {"robert", "mateo", "amira", "canadian"}
    for pilot in p.values():
        assert set(pilot) == {"name", "age", "blurb", "amount", "profile", "portfolio", "request", "question", "lesson"}
        assert set(pilot["profile"]) == PROFILE_KEYS
        assert pilot["profile"]["risk"] == REACTION_TO_RISK[pilot["profile"]["reaction_2022"]]
        assert set(pilot["portfolio"]) <= UNIVERSE_31 and abs(sum(pilot["portfolio"].values()) - 1) < 1e-9
        assert pilot["question"].endswith("?")
    assert {k: v["profile"] for k, v in p.items()} == EXPECTED_PROFILES
    assert {k: (v["name"], v["age"], v["amount"]) for k, v in p.items()} == {
        "robert": ("Robert", 59, 600000), "mateo": ("Mateo", 41, 250000),
        "amira": ("Amira", 26, 80000), "canadian": ("Too Canadian?", None, 250000)}
    # capacity / amount = the capacity floor: Robert -15 % (stricter than his -25 % band), Mateo and Amira equal their band
    assert {k: round(v["profile"]["capacity"] / v["amount"], 4) for k, v in p.items()} == {
        "robert": 0.15, "mateo": 0.25, "amira": 0.45, "canadian": 0.25}
    r = p["robert"]
    assert (r["amount"], r["profile"]["capacity"], r["profile"]["horizon_years"]) == (600000, 90000, 4)
    assert r["portfolio"] == {"XIU.TO": 0.45, "XBB.TO": 0.35, "GLD": 0.10, "ZST.TO": 0.10}
    assert r["request"] == {"op": "set", "ticker": "NVDA", "weight": 0.40, "from_ticker": None}
    assert (p["mateo"]["amount"], p["mateo"]["profile"]["capacity"], p["mateo"]["profile"]["esg"]) == (250000, 62500, True)
    assert p["mateo"]["portfolio"] == {"XIU.TO": 0.35, "XBB.TO": 0.35, "CNQ.TO": 0.08, "MSFT": 0.10, "GLD": 0.12}
    assert p["mateo"]["portfolio"]["CNQ.TO"] == 0.08 and "ZAG.TO" not in json.dumps(PERSONAS)
    assert p["mateo"]["request"] is None
    assert (p["amira"]["amount"], p["amira"]["profile"]["capacity"], p["amira"]["profile"]["crypto"]) == (80000, 36000, True)
    assert p["amira"]["portfolio"] == {"NVDA": 0.15, "QQQ": 0.15, "SHOP.TO": 0.10, "BTC-USD": 0.15, "XIU.TO": 0.30, "XBB.TO": 0.15}
    assert p["amira"]["request"] is None
    assert p["canadian"]["portfolio"] == {"XIU.TO": 0.60, "XBB.TO": 0.30, "ZST.TO": 0.10}
    assert p["canadian"]["request"] == {"op": "add", "ticker": "SPY", "weight": 0.20, "from_ticker": None}


def test_storm_cards_are_the_four_families():
    cards = PERSONAS["storm_cards"]
    assert set(cards) == {"tariffs", "war_oil", "chips", "rates"}
    assert {k: c["label"] for k, c in cards.items()} == {
        "tariffs": "Tariff war", "war_oil": "War & oil", "chips": "Chip war", "rates": "Rate shock"}
    assert all(c["families"] == [k] and c["question"].endswith("?") for k, c in cards.items())


def test_illustration_mixes_sum_to_one_and_respect_preferences():
    mixes = PERSONAS["illustration_mixes"]
    assert set(mixes) == {"low", "moderate", "moderate_esg", "high", "high_crypto", "high_esg"}
    for name, w in mixes.items():
        assert set(w) <= UNIVERSE_31 and abs(sum(w.values()) - 1) < 1e-9, name
        assert ("BTC-USD" in w) == (name == "high_crypto"), name
    for name in ("moderate_esg", "high_esg"):
        assert not {"XIU.TO", "SPY", "CNQ.TO", "ENB.TO", "XOM"} & set(mixes[name])
    assert mixes == EXPECTED_MIXES


def test_no_advice_words_in_personas():
    assert not [s for s in _strings(PERSONAS) if ADVICE_WORDS.search(s)]


# ---------------------------------------------------------------------------------------------------------------
# Section 2 (plan C Task 3): data/esg_flags.csv, the values screen behind Mateo's persona test.
# Two kinds of row. Category rows: ESGV's published exclusion categories applied to our energy stocks (Vanguard page,
# read 2026-11-14). Controversy rows: only where the company's OWN annual filing discloses an environmental or social
# legal proceeding or regulatory action (filing date = the flag's as_of, URL, filing type and one exact quoted
# sentence; no disclosure, no flag). Every reason says "exclusion/disclosure screen, not an ESG score". The filings are
# read on each company's own investor site, never on sec.gov or SEDAR+ (hosts that require declared automation).
# ---------------------------------------------------------------------------------------------------------------
ESG = pd.read_csv("data/esg_flags.csv", dtype=str, keep_default_na=False)
ESGV_PAGE = "https://investor.vanguard.com/investment-products/etfs/profile/esgv"
DATASET_END = "2026-11-12"
CATEGORY_FLAGS = {"fossil_reserves", "fuel_pipelines"}
CONTROVERSY_FLAGS = {"controversy_env", "controversy_social"}
STOCKS_20 = UNIVERSE_31 - {"XIU.TO", "SPY", "QQQ", "ESGV", "XBB.TO", "ZST.TO", "AGG", "TLT", "GLD", "BTC-USD", "ETH-USD"}
# Words that judge. The reasons we write may not use them; a quoted sentence is the filing's own words and is exempt.
JUDGMENT_WORDS = re.compile(
    r"\b(controvers\w*|scandal\w*|unethical|irresponsible|reckless|negligen\w*|misconduct|guilty|polluter\w*|"
    r"dirty|toxic|bad|worst|shameful|harmful)\b", re.I)
QUOTED = re.compile(r'"([^"]+)"')
CATEGORY = ESG[ESG.flag.isin(CATEGORY_FLAGS)]
CONTROVERSY = ESG[ESG.flag.isin(CONTROVERSY_FLAGS)]
# The pinned outcome of the research (Sat Nov 14 2026): each single stock's latest annual document dated <= DATASET_END was read
# on the company's own investor site. A generic "ordinary course" sentence is not a disclosure. Changing any line is a decision.
CONTROVERSY_ROWS = {  # ticker: (flag, filing date = the flag's as_of, host that serves the document)
    "CNR.TO": ("controversy_env", "2026-02-04", "www.cn.ca"),
    "ENB.TO": ("controversy_env", "2026-02-13", "www.enbridge.com"),
    "JNJ": ("controversy_social", "2026-02-11", "d18rn0p25nwr6d.cloudfront.net"),   # IR vendor CDN, linked from investor.jnj.com
    "PG": ("controversy_env", "2026-08-04", "d18rn0p25nwr6d.cloudfront.net"),       # IR vendor CDN, linked from pginvestor.com
    "XOM": ("controversy_env", "2026-02-18", "investor.exxonmobil.com"),
}
READ_NO_FLAG = {"AAPL", "AMZN", "ATD.TO", "CNQ.TO", "FTS.TO", "GOOGL", "JPM", "MFC.TO", "MSFT", "NVDA", "SHOP.TO", "TD.TO"}
# The significance rule (Sun Nov 15 2026; docs/finance_methods.md section 6): the brief asks for SIGNIFICANT
# environmental or social controversies. Environmental enforcement (a government authority's action, penalty, order,
# agreement or liability designation, or a government lawsuit, over harm to air, water, land or climate) and major
# social harm (injury to people's health or safety at scale, human-rights abuses) qualify; employment and pay disputes,
# contract, commercial, securities, tax and competition litigation do not. Read, disclosed, not significant: no row.
READ_NOT_SIGNIFICANT = {"RY.TO": "Annual Report 2025-12-02, Note 24, vacation pay class action: an employment-pay dispute"}
NOT_READ = {"TSLA": "ir.tesla.com answers HTTP 403 to automated reads",
            "CSU.TO": "its FY2025 annual information form is on SEDAR+ only; csisoftware.com hosts none"}


def test_esg_flags_columns_and_row_kinds():
    assert list(ESG.columns) == ["ticker", "flag", "reason_en", "reason_fr", "source_url", "source_date"]
    assert set(ESG.flag) <= CATEGORY_FLAGS | CONTROVERSY_FLAGS and len(CATEGORY) + len(CONTROVERSY) == len(ESG)
    assert set(ESG.ticker) <= STOCKS_20, "flags apply to single stocks of the dataset only"
    assert not ESG.duplicated(["ticker", "flag"]).any()
    assert all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) for d in ESG.source_date)
    assert (ESG[["reason_en", "reason_fr", "source_url"]] != "").all().all()


def test_esg_category_rows_are_sourced_vanguard_exclusions():
    assert set(zip(CATEGORY.ticker, CATEGORY.flag)) == {
        ("CNQ.TO", "fossil_reserves"), ("XOM", "fossil_reserves"), ("ENB.TO", "fuel_pipelines")}
    assert set(CATEGORY.source_url) == {ESGV_PAGE} and set(CATEGORY.source_date) == {"2026-11-14"}
    assert all("not an ESG score" in r for r in CATEGORY.reason_en)


def test_esg_controversy_rows_are_the_pinned_research_outcome():
    got = {r.ticker: (r.flag, r.source_date, urlparse(r.source_url).netloc) for r in CONTROVERSY.itertuples()}
    assert got == CONTROVERSY_ROWS


def test_every_single_stock_has_a_recorded_research_outcome():
    parts = [set(CONTROVERSY_ROWS), READ_NO_FLAG, set(READ_NOT_SIGNIFICANT), set(NOT_READ)]
    assert sum(len(p) for p in parts) == len(STOCKS_20) == 20 and set().union(*parts) == STOCKS_20   # a partition: none unexamined
    assert not set(NOT_READ) & set(ESG.ticker), "nothing is flagged without a document read"
    assert not READ_NO_FLAG & set(CONTROVERSY.ticker) and not set(READ_NOT_SIGNIFICANT) & set(ESG.ticker)


def test_esg_controversy_rows_quote_the_companys_own_filing():
    for r in CONTROVERSY.itertuples():
        who = (r.ticker, r.flag)
        url = urlparse(r.source_url)
        assert url.scheme == "https" and url.netloc not in {"www.sec.gov", "www.sedarplus.ca"}, who   # the company's own site
        assert r.source_date <= DATASET_END, who   # the flag's as_of is the filing date: no look-ahead, none after the dataset
        quotes = QUOTED.findall(r.reason_en)
        assert len(quotes) == 1 and 20 <= len(quotes[0]) <= 450, who          # one exact sentence, short (CNR.TO's is 438)
        assert quotes[0] in r.reason_fr, who                                 # the English quote is kept verbatim in the French text
        assert re.search(r"\b(Form 10-K|Form 40-F|Annual Information Form|Annual Report)\b", r.reason_en), who
        assert "annual filing discloses" in r.reason_en and r.source_date in r.reason_en, who
        assert "not an ESG score" in r.reason_en, who
        assert not JUDGMENT_WORDS.search(QUOTED.sub("", r.reason_en)), who   # our own words never judge
        assert re.search(r"\b(environmental|social)\b", QUOTED.sub("", r.reason_en)), who


# Task 3 review amendments (the lead's ruling, Sat Nov 14 2026): a quote must be self-contained on screen. CNR.TO: the first sentence of
# its "Environmental matters" paragraph (the old quote began mid-paragraph, with "PRP" and "the Site" undefined). RY.TO (row dropped
# Sun Nov 15 by the significance rule, READ_NOT_SIGNIFICANT): the first
# sentence of its "Vacation pay class action" paragraph (the old quote began "The action ...", with no antecedent). Both were re-checked
# on 2026-11-14 as exact substrings of the cited PDFs (research-time check, not a test; whitespace-normalised, PDFKit text).
AMENDED_QUOTES = {
    "CNR.TO": ("Under the Comprehensive Environmental Response, Compensation and Liability Act of 1980 (CERCLA), the Company through one of its "
               "subsidiaries was notified by the U.S. Environmental Protection Agency (EPA) on February 28, 2024 that the EPA considers it a "
               "potentially responsible party (PRP), along with at least five other previously notified parties, with respect to the "
               "Matthiessen & Hegeler Zinc Company Site (Site) in LaSalle, Illinois."),
}


def test_amended_quotes_are_self_contained_and_say_where_they_come_from():
    rows = {r.ticker: r for r in CONTROVERSY.itertuples()}
    for ticker, sentence in AMENDED_QUOTES.items():
        r = rows[ticker]
        assert QUOTED.findall(r.reason_en) == [sentence] and sentence in r.reason_fr, ticker   # exactly this sentence, in both languages
        assert sentence[0].isupper() and sentence.endswith(".") and not sentence.startswith("The action"), ticker
    cnr = rows["CNR.TO"]                      # RY.TO's amended quote went with its row (the significance rule, Sun Nov 15)
    assert "the report's own date" in cnr.reason_en and "date du rapport lui-même" in cnr.reason_fr   # source_date is the report's date


def test_no_advice_words_in_the_esg_text():
    """Red gate: the UI shows these reasons, and nothing the app shows says buy / sell / hold / should."""
    hits = [(r.ticker, r.flag, m.group(0)) for r in ESG.itertuples() for col in ("reason_en", "reason_fr")
            for m in ADVICE_WORDS.finditer(getattr(r, col))]
    assert not hits, hits


@NEEDS_DATA
def test_every_energy_equity_has_its_category_flag_and_only_those():
    data = pytest.importorskip("tools.data")
    u = data.load_universe()
    energy = set(u[(u.asset_class == "equity") & (u.sector == "Energy")].ticker)
    assert energy == set(CATEGORY.ticker)


# ---------------------------------------------------------------------------------------------------------------
# Section 3 (plan C Task 4): scripts/fetch_holdings.py, the issuers' holdings downloaded into the local, never committed
# data/etf_holdings.csv. The parsers are tested offline on synthetic fixtures built here (no issuer file is ever committed);
# the last test reads the local file's facts and skips on a fresh clone.
# ---------------------------------------------------------------------------------------------------------------
def _xlsx(cells):
    """An in-memory XLSX with one sheet (xl/worksheets/sheet1.xml only); every cell is an inline string at A1, B1, ..."""
    rows = "".join(
        f'<row r="{i}">' + "".join(f'<c r="{chr(65 + j)}{i}" t="inlineStr"><is><t>{escape(v)}</t></is></c>' for j, v in enumerate(row)) + "</row>"
        for i, row in enumerate(cells, start=1))
    xml = ('<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
           f"<sheetData>{rows}</sheetData></worksheet>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", xml)
    return buf.getvalue()


ISHARES = (
    'iShares S&P/TSX 60 Index ETF\nFund Holdings as of,"Nov 12, 2026"\n\n'
    'Ticker,Name,Sector,Asset Class,Market Value,Weight (%),Notional Value,Shares,Price,Location,Exchange,Currency\n'
    + "".join(f'T{i},NAME {i},Financials,Equity,1,{3.0 - i * 0.05:.2f},1,1,1,Canada,TSX,CAD\n' for i in range(27))
    + 'FTS,FORTIS,Utilities,Equity,1,1.03,1,1,1,Canada,TSX,CAD\n'
    + 'BIP_UN,BROOKFIELD INFRA,Utilities,Equity,1,0.61,1,1,1,Bermuda,TSX,CAD\n'
    + 'X1,XYZ COMM,Communication,Equity,1,0.40,1,1,1,United States,TSX,CAD\n'
    + 'CAD,CAD CASH,Cash and/or Derivatives,Cash,1,0.30,1,1,1,Canada,-,CAD\n'
    + '\n"The content contained herein is owned or licensed by BlackRock"\n')


def test_parse_ishares_csv_top25_plus_dataset_names_sectors_countries():
    fh = pytest.importorskip("scripts.fetch_holdings")
    rows = fh.parse_ishares_csv(ISHARES, "XIU.TO", UNIVERSE_31, "https://x")
    hold = [r for r in rows if r["kind"] == "holding"]
    assert len(hold) == 26 and hold[-1]["ticker"] == "FTS.TO" and hold[-1]["weight"] == pytest.approx(0.0103)
    assert {r["as_of"] for r in rows} == {"2026-11-12"} and {r["source_url"] for r in rows} == {"https://x"}
    sectors = {r["name"]: r["weight"] for r in rows if r["kind"] == "sector"}
    assert "Communication Services" in sectors and sectors["Cash and/or Derivatives"] == pytest.approx(0.003)
    countries = {r["name"]: r["weight"] for r in rows if r["kind"] == "country"}
    assert set(countries) == {"CAN", "BMU"}          # United States 0.40 % < 0.5 % is left out


def test_dataset_ticker_mapping():
    fh = pytest.importorskip("scripts.fetch_holdings")
    assert [fh.dataset_ticker(s, UNIVERSE_31) for s in ("RY", "SHOP", "XOM", "GOOG", "BRK.B")] == ["RY.TO", "SHOP.TO", "XOM", "", ""]


def test_parse_ssga_xlsx_from_a_minimal_workbook():
    fh = pytest.importorskip("scripts.fetch_holdings")
    cells = [["Fund Name:", "SPDR S&P 500 ETF Trust"], ["Holdings:", "As of 12-Nov-2026"], [],
             ["Name", "Ticker", "Identifier", "SEDOL", "Weight", "Sector"],
             ["NVIDIA CORP", "NVDA", "x", "x", "6.137977", "-"], ["ALPHABET INC CL C", "GOOG", "x", "x", "2.142682", "-"]]
    rows = fh.parse_ssga_xlsx(_xlsx(cells), "SPY", UNIVERSE_31, "https://y")
    assert [(r["ticker"], r["weight"]) for r in rows] == [("NVDA", pytest.approx(0.06137977)), ("", pytest.approx(0.02142682))]
    assert {r["kind"] for r in rows} == {"holding"} and {r["as_of"] for r in rows} == {"2026-11-12"}


def test_merge_replaces_only_refreshed_etf_kinds():
    fh = pytest.importorskip("scripts.fetch_holdings")
    old = [{"etf": "SPY", "kind": "sector", "name": "Energy", "weight": 0.0358}, {"etf": "SPY", "kind": "holding", "name": "OLD", "weight": 0.1},
           {"etf": "QQQ", "kind": "holding", "name": "Q", "weight": 0.2}]
    new = [{"etf": "SPY", "kind": "holding", "name": "NEW", "weight": 0.2}]
    assert [r["name"] for r in fh.merge(old, new)] == ["Energy", "Q", "NEW"]


def test_main_keeps_the_local_file_when_every_source_fails(tmp_path, monkeypatch):
    fh = pytest.importorskip("scripts.fetch_holdings")
    out = tmp_path / "etf_holdings.csv"; out.write_text("etf,kind,name,ticker,weight,as_of,source_url\nSPY,holding,X,,0.1,2026-11-12,https://y\n")
    monkeypatch.setattr(fh, "fetch", lambda url, timeout=30: None)
    before = out.read_bytes()
    assert fh.main(["--out", str(out)]) == 1 and out.read_bytes() == before


HOLDINGS = Path("data/etf_holdings.csv")


def _holdings_with_manual_etfs(path):
    """True when the local file holds QQQ and ESGV rows. Issuer terms make those two manual-only (a --manual file typed by a
    human), so a fresh clone that ran scripts/fetch_holdings.py has the file but not these rows: the facts test then skips."""
    try:
        return {"QQQ", "ESGV"} <= set(pd.read_csv(path, usecols=["etf"]).etf)
    except (OSError, ValueError):    # absent or unreadable
        return False


@pytest.mark.skipif(not _holdings_with_manual_etfs(HOLDINGS), reason="local ETF holdings absent, or without the manual QQQ/ESGV rows (never committed)")
def test_local_holdings_file_carries_the_spec_facts():
    h = pd.read_csv(HOLDINGS, dtype={"ticker": str}, keep_default_na=False)
    assert list(h.columns) == ["etf", "kind", "name", "ticker", "weight", "as_of", "source_url"]
    assert set(h.kind) == {"holding", "sector", "country"} and h.weight.between(0, 1).all()
    w = {(r.etf, r.kind, r.ticker or r.name): r.weight for r in h.itertuples()}
    assert w[("SPY", "holding", "NVDA")] == pytest.approx(0.0614, abs=5e-5)
    assert w[("QQQ", "holding", "NVDA")] == pytest.approx(0.0653, abs=5e-5)
    assert w[("ESGV", "holding", "NVDA")] == pytest.approx(0.0658, abs=5e-5)
    assert (w[("XIU.TO", "holding", "ENB.TO")], w[("XIU.TO", "holding", "CNQ.TO")]) == (pytest.approx(0.0359), pytest.approx(0.0345))
    # the fund page's breakdown (16.65 %) and the sum of the CSV's rounded line weights (16.66 %) differ by up to 0.06 pp per sector
    assert w[("XIU.TO", "sector", "Energy")] == pytest.approx(0.1665, abs=1e-3)
    for etf in ("XIU.TO", "SPY", "QQQ", "ESGV"):
        assert h[(h.etf == etf) & (h.kind == "sector")].weight.sum() == pytest.approx(1.0, abs=0.02), etf


# Behaviour beyond the plan's five parser tests: the XLSX reader's shared strings, and main's three other exits.
GOOD_FILE = "etf,kind,name,ticker,weight,as_of,source_url\nSPY,holding,X,,0.1,2026-11-12,https://y\nQQQ,holding,OLD,,0.2,2026-11-12,https://q\n"
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def test_read_xlsx_rows_resolves_shared_strings_and_places_cells_by_column_and_row():
    fh = pytest.importorskip("scripts.fetch_holdings")
    sheet = (f'<worksheet xmlns="{MAIN_NS}"><sheetData><row r="2"><c r="B2" t="s"><v>1</v></c><c r="D2"><v>3.5</v></c></row>'
             '<row r="4"><c r="A4" t="inlineStr"><is><t>x</t></is></c></row></sheetData></worksheet>')
    shared = f'<sst xmlns="{MAIN_NS}"><si><t>zero</t></si><si><r><t>one</t></r><r><t>!</t></r></si></sst>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/sharedStrings.xml", shared); z.writestr("xl/worksheets/sheet1.xml", sheet)
    assert fh.read_xlsx_rows(buf.getvalue()) == [[], ["", "one!", "", "3.5"], [], ["x"]]


def test_main_offline_manual_rows_replace_their_group_and_add_the_static_labels(tmp_path):
    fh = pytest.importorskip("scripts.fetch_holdings")
    out, manual = tmp_path / "h.csv", tmp_path / "qqq.csv"
    out.write_text(GOOD_FILE)
    manual.write_text("etf,kind,name,ticker,weight,as_of,source_url\nQQQ,holding,NVIDIA CORP,NVDA,0.0653,2026-11-12,https://q\n"
                      "QQQ,sector,Information Technology,,0.64,2026-10-31,https://q\n")
    assert fh.main(["--out", str(out), "--offline", "--manual", str(manual)]) == 0
    h = pd.read_csv(out, dtype={"ticker": str}, keep_default_na=False)
    assert not (tmp_path / "h.csv.tmp").exists() and list(dict.fromkeys(h.etf)) == ["SPY", "QQQ", "ZST.TO", "AGG", "TLT", "GLD"]
    assert list(h[h.etf == "QQQ"].name) == ["NVIDIA CORP", "Information Technology"]      # the OLD QQQ holding was replaced
    assert list(h[h.etf == "SPY"].name) == ["X"] and set(h[h.etf == "GLD"].name) == {"Gold", "GLOBAL"}


def test_main_refuses_static_rows_alone_and_a_malformed_manual_file(tmp_path, capsys):
    fh = pytest.importorskip("scripts.fetch_holdings")
    out, bad = tmp_path / "h.csv", tmp_path / "bad.csv"
    out.write_text(GOOD_FILE); bad.write_text("etf,kind,name\nQQQ,holding,X\n")
    before = out.read_bytes()
    assert fh.main(["--out", str(out), "--offline"]) == 1 and out.read_bytes() == before        # labels alone are not a refresh
    assert fh.main(["--out", str(out), "--offline", "--manual", str(bad)]) == 1 and out.read_bytes() == before
    assert "Traceback" not in capsys.readouterr().out and not (tmp_path / "h.csv.tmp").exists()


def test_main_labels_xbb_as_bonds_and_keeps_only_its_downloaded_countries(tmp_path, monkeypatch):
    fh = pytest.importorskip("scripts.fetch_holdings")
    monkeypatch.setattr(fh, "fetch", lambda url, timeout=30: ISHARES.encode() if "239493" in url else None)
    monkeypatch.setattr(fh, "_universe", lambda: set(UNIVERSE_31))
    out = tmp_path / "h.csv"
    assert fh.main(["--out", str(out)]) == 0
    x = pd.read_csv(out, keep_default_na=False).query("etf == 'XBB.TO'")
    assert [(r.kind, r.name) for r in x.itertuples()] == [("sector", "Bonds"), ("country", "CAN"), ("country", "BMU")]


# --- Task 4 fix round 1 (review of 38c45fa): plain XLSX failures, streaming size cap, weights, safe temp file, manual rows ---------
SHEET_XML = (f'<worksheet xmlns="{MAIN_NS}"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Ticker</t></is></c></row></sheetData></worksheet>')


def _member(payload, name="xl/worksheets/sheet1.xml"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(name, payload)
    return buf.getvalue()


def _patch_central(data, offset, fmt, value):
    """Overwrite one field of the central-directory record (offset counted from its PK\\x01\\x02 signature)."""
    at = data.index(b"PK\x01\x02") + offset
    return data[:at] + struct.pack(fmt, value) + data[at + struct.calcsize(fmt):]


def _hostile_xlsx(kind):
    data = _member(SHEET_XML)
    if kind == "corrupt_deflate":      # the first deflate byte says "block type 3", which does not exist: zlib.error
        start = 30 + struct.unpack("<HH", data[26:30])[0] + struct.unpack("<HH", data[26:30])[1]
        return data[:start] + b"\x07" + data[start + 1:]
    if kind == "encrypted":            # general-purpose flag bit 0: RuntimeError (password required)
        return _patch_central(data, 8, "<H", 0x0001)
    return _patch_central(data, 10, "<H", 99)       # an unknown compression method: NotImplementedError


@pytest.mark.parametrize("kind", ["corrupt_deflate", "encrypted", "unknown_compression"])
def test_read_xlsx_rows_turns_every_zip_failure_into_a_plain_valueerror(kind):
    fh = pytest.importorskip("scripts.fetch_holdings")
    with pytest.raises(ValueError, match="not a readable XLSX"):
        fh.read_xlsx_rows(_hostile_xlsx(kind))


def test_main_keeps_the_other_etfs_when_the_spy_workbook_is_corrupt(tmp_path, monkeypatch, capsys):
    fh = pytest.importorskip("scripts.fetch_holdings")
    bad = _hostile_xlsx("corrupt_deflate")
    monkeypatch.setattr(fh, "fetch", lambda url, timeout=30: bad if url.endswith(".xlsx") else ISHARES.encode())
    monkeypatch.setattr(fh, "_universe", lambda: set(UNIVERSE_31))
    out = tmp_path / "h.csv"
    assert fh.main(["--out", str(out)]) == 0
    got = set(pd.read_csv(out, keep_default_na=False).etf)
    said = capsys.readouterr().out
    assert {"XIU.TO", "XBB.TO"} <= got and "SPY" not in got and "SPY was not refreshed" in said and "Traceback" not in said


def test_read_xlsx_rows_never_inflates_past_the_cap_even_when_the_declared_size_lies():
    fh = pytest.importorskip("scripts.fetch_holdings")
    liar = _patch_central(_member(b"\0" * 32_000_000), 24, "<I", 100)     # declares 100 bytes, inflates to 32 MB
    tracemalloc.start()
    try:
        with pytest.raises(ValueError):
            fh.read_xlsx_rows(liar)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < 8_000_000, f"inflated {peak} bytes before refusing"


def test_read_xlsx_rows_refuses_an_honest_member_over_the_cap(monkeypatch):
    fh = pytest.importorskip("scripts.fetch_holdings")
    monkeypatch.setattr(fh, "MAX_BYTES", 10_000)
    with pytest.raises(ValueError, match="unreasonable size"):
        fh.read_xlsx_rows(_member(b"<a>" + b"x" * 200_000 + b"</a>"))


@pytest.mark.parametrize("cell, message", [('"1,500.00"', "outside 0-100"), ('"1,50"', "unreadable"), ("abc", "unreadable"), ("150", "outside 0-100")])
def test_parse_ishares_csv_refuses_a_weight_it_cannot_read_or_that_is_over_100_percent(cell, message):
    fh = pytest.importorskip("scripts.fetch_holdings")
    text = ISHARES.replace("T0,NAME 0,Financials,Equity,1,3.00,", f"T0,NAME 0,Financials,Equity,1,{cell},")
    assert text != ISHARES
    with pytest.raises(ValueError, match=message):
        fh.parse_ishares_csv(text, "XIU.TO", UNIVERSE_31, "https://x")


def test_weights_accept_scientific_notation_and_skip_dash_cells():
    fh = pytest.importorskip("scripts.fetch_holdings")
    cells = [["Holdings:", "As of 12-Nov-2026"], ["Name", "Ticker", "Weight"], ["NVIDIA CORP", "NVDA", "6.137977"],
             ["TINY CO", "TINY", "3.0E-6"], ["CASH", "-", "0.5"], ["NO WEIGHT", "ZZZ", "-"]]       # SPY's file really has a 3.0E-6 cell
    rows = fh.parse_ssga_xlsx(_xlsx(cells), "SPY", UNIVERSE_31, "https://y")
    assert [(r["name"], r["weight"]) for r in rows] == [("NVIDIA CORP", pytest.approx(0.06137977)), ("TINY CO", pytest.approx(3e-8))]


def test_a_sector_or_country_total_is_capped_at_100_percent_so_the_file_stays_readable():
    fh = pytest.importorskip("scripts.fetch_holdings")
    one_sector = ('Fund Holdings as of,"Nov 12, 2026"\n\nTicker,Name,Sector,Asset Class,Weight (%),Location\n'
                  "AAA,AAA CORP,Financials,Equity,60.01,Canada\nBBB,BBB CORP,Financials,Equity,40.01,Canada\n")   # the file's own total is 100.02 %
    rows = fh.parse_ishares_csv(one_sector, "XIU.TO", UNIVERSE_31, "https://x")
    assert [(r["kind"], r["name"], r["weight"]) for r in rows if r["kind"] != "holding"] == [("sector", "Financials", 1.0), ("country", "CAN", 1.0)]


def _rows_file(tmp_path, name, *lines):
    path = tmp_path / name
    path.write_text("etf,kind,name,ticker,weight,as_of,source_url\n" + "".join(x + "\n" for x in lines))
    return path


@pytest.mark.parametrize("kind", ["file", "symlink", "dangling_symlink"])
def test_main_refuses_a_leftover_or_symlinked_tmp_and_writes_nothing(tmp_path, kind, capsys):
    fh = pytest.importorskip("scripts.fetch_holdings")
    out, victim = tmp_path / "h.csv", tmp_path / "victim.txt"
    out.write_text(GOOD_FILE); victim.write_text("keep me")
    tmp = tmp_path / "h.csv.tmp"
    {"file": lambda: tmp.write_text("stale"), "symlink": lambda: tmp.symlink_to(victim),
     "dangling_symlink": lambda: tmp.symlink_to(tmp_path / "nowhere.txt")}[kind]()
    manual = _rows_file(tmp_path, "m.csv", "QQQ,holding,NVIDIA CORP,NVDA,0.0653,2026-11-12,https://q")
    assert fh.main(["--out", str(out), "--offline", "--manual", str(manual)]) == 1
    assert out.read_text() == GOOD_FILE and victim.read_text() == "keep me" and os.path.lexists(tmp) and not (tmp_path / "nowhere.txt").exists()
    assert "temporary file" in capsys.readouterr().out          # said up front, before any download


def test_write_rows_creates_its_tmp_exclusively_and_never_removes_one_it_did_not_create(tmp_path):
    fh = pytest.importorskip("scripts.fetch_holdings")
    out, tmp = tmp_path / "h.csv", tmp_path / "h.csv.tmp"
    tmp.write_text("not ours")
    with pytest.raises(FileExistsError):
        fh._write_rows(out, [{"etf": "SPY", "kind": "holding", "name": "X", "ticker": "", "weight": 0.1, "as_of": "2026-11-12", "source_url": "u"}])
    assert tmp.read_text() == "not ours" and not out.exists()


def test_main_manual_rows_replace_a_downloaded_and_a_static_group_never_duplicate_it(tmp_path, monkeypatch):
    fh = pytest.importorskip("scripts.fetch_holdings")
    monkeypatch.setattr(fh, "fetch", lambda url, timeout=30: ISHARES.encode() if "239832" in url else None)    # XIU.TO only
    monkeypatch.setattr(fh, "_universe", lambda: set(UNIVERSE_31))
    manual = _rows_file(tmp_path, "m.csv", "XIU.TO,sector,Financials,,0.5,2026-11-12,https://m", "AGG,sector,Treasuries,,1.0,2026-11-12,https://m")
    out = tmp_path / "h.csv"
    assert fh.main(["--out", str(out), "--manual", str(manual)]) == 0
    h = pd.read_csv(out, keep_default_na=False)
    assert list(h[(h.etf == "XIU.TO") & (h.kind == "sector")].name) == ["Financials"]       # not the downloaded sectors plus this one
    assert list(h[(h.etf == "AGG") & (h.kind == "sector")].name) == ["Treasuries"]          # not the static Bonds row as well
    assert len(h[(h.etf == "XIU.TO") & (h.kind == "holding")]) == 26                        # the other XIU.TO groups stay as downloaded


def test_main_refuses_a_manual_ticker_that_is_not_in_the_dataset(tmp_path, capsys):
    fh = pytest.importorskip("scripts.fetch_holdings")
    out = tmp_path / "h.csv"; out.write_text(GOOD_FILE)
    manual = _rows_file(tmp_path, "m.csv", "QQQ,holding,BROADCOM INC,AVGO,0.03,2026-11-12,https://q")
    assert fh.main(["--out", str(out), "--offline", "--manual", str(manual)]) == 1
    assert out.read_text() == GOOD_FILE and "AVGO" in capsys.readouterr().out


# ---------------------------------------------------------------------------------------------------------------
# Section 4 (plan C Task 7): the checklist truth. The finance definitions of spec section 5 (limits, rows, verdict) with
# the rulings of ledger sections 14, 22, 29 and 30 and spec section 24; governance.py must pass them, never the other way
# round. Limits are always read through governance.load_limits (pitfall 8), never typed into a fixture. The first
# groups build the `analysis` dict by hand (plan B Task 4's shape plus `risk` and `limits`) and need no data file; the
# real-data pilots judge through governance.evaluate (B Task 5, with A Tasks 8 and 10 behind it) and need the local data.
# Ledger 30 (Sat 23:35) rules the shock check: beyond its threshold it is a warn ("Caution" on the page), never a fail.
# ---------------------------------------------------------------------------------------------------------------
ROBERT_P = {"goal": "preservation", "horizon_years": 4, "risk": "moderate", "esg": False, "crypto": False, "capacity": 90000, "reaction_2022": "held"}
MATEO_P = {"goal": "balance", "horizon_years": 10, "risk": "moderate", "esg": True, "crypto": False, "capacity": 62500, "reaction_2022": "held"}
AMIRA_P = {"goal": "growth", "horizon_years": 15, "risk": "high", "esg": False, "crypto": True, "capacity": 36000, "reaction_2022": "bought"}
UNI = [{"ticker": "NVDA", "asset_class": "equity", "sector": "Information Technology"},
       {"ticker": "CNQ.TO", "asset_class": "equity", "sector": "Energy"},
       {"ticker": "XIU.TO", "asset_class": "etf_equity", "sector": "Broad market (Canada)"},
       {"ticker": "XBB.TO", "asset_class": "etf_bond", "sector": "Bonds (Canada aggregate)"},
       {"ticker": "BTC-USD", "asset_class": "crypto", "sector": "Crypto asset"}]
FORECAST_WORDS = re.compile(r"\b(will|expect\w*|predict\w*|recommend\w*)\b", re.I)   # the shock check is history, never a forecast
CALM_RISK = {"XIU.TO": 0.45, "XBB.TO": 0.35, "GLD": 0.20}   # no line carries more than half the risk: no risk_concentration warn


def _gov():
    return pytest.importorskip("governance")


def _says_count(reason, n):
    """True when the sentence states the whole number n as a count (not the digits inside 7.5 or 6.0)."""
    return re.search(rf"(?<![\d.,]){n}(?!\d|[.,]\d)", reason) is not None


def _analysis(profile, amount, dd=-0.10, stress=-0.05, n=3, stocks=None, sectors=None, esg_indirect=None, risk=None, rec=200, since=900, **over):
    look = {"stocks": stocks or {}, "sectors": sectors or {}, "countries": {}, "esg_indirect": esg_indirect or {},
            "coverage": {}, "snapshot": {}, "mode": "lookthrough"}
    a = {"metrics": {"max_drawdown": dd, "peak_date": "2021-11-29", "trough_date": "2022-10-14", "recovery_days": rec, "days_since_trough": since},
         "lookthrough": look, "universe": UNI, "esg_flags": {"CNQ.TO", "XOM", "ENB.TO"}, "scenario_stress": stress,
         "scenario_family": "tariffs", "scenario_episodes": n, "missing_data": [],
         "limits": _gov().load_limits(profile, over or None, amount=amount)}
    if risk is not None:
        a["risk"] = {"shares": risk, "bets": 1.0}
    return a


def _row(checks, rule):
    return next(c for c in checks if c["rule"] == rule)


def _status(profile, amount, weights=None, **kw):
    checks = _gov().check_profile(profile, weights or {"XIU.TO": 1.0}, _analysis(profile, amount, **kw))
    return checks, _gov().verdict(checks)


def _line(rule, tier, status, holding=None):
    """A bare checklist row, for the verdict rule on its own."""
    return {"rule": rule, "tier": tier, "status": status, "value": 0, "limit": 0, "holding": holding, "reason": "."}


def test_floor_is_the_stricter_of_capacity_and_band():
    g = _gov()
    r = g.load_limits(ROBERT_P, amount=600000)
    assert (r["floor"], r["floor_source"], r["band_floor"], r["capacity_floor"]) == (-0.15, "capacity", -0.25, -0.15)
    assert (r["scenario_stress"], r["single_stock"], r["sector"], r["crypto"], r["risk_share"]) == (-0.075, 0.10, 0.35, 0.0, 0.5)
    assert (r["esg_indirect_warn"], r["short_horizon_years"]) == (0.01, 3) and r["recovery_days"] == pytest.approx(486.6, abs=0.2)
    loose = g.load_limits({**ROBERT_P, "risk": "low", "capacity": 150000}, amount=600000)
    assert (loose["floor"], loose["floor_source"]) == (-0.15, "band")
    none = g.load_limits({**ROBERT_P, "capacity": None}, amount=600000)
    assert (none["floor"], none["floor_source"], none["capacity_floor"]) == (-0.25, "band", None)
    tie = g.load_limits(MATEO_P, amount=250000)
    assert (tie["floor"], tie["floor_source"]) == (-0.25, "capacity")


def test_band_from_the_2022_reaction_crypto_tier_and_override():
    g = _gov()
    assert g.load_limits({**ROBERT_P, "risk": None, "reaction_2022": "sold", "capacity": None})["band_floor"] == -0.15
    assert g.load_limits({**ROBERT_P, "risk": None, "reaction_2022": "bought", "capacity": None})["band_floor"] == -0.45
    assert (g.load_limits(AMIRA_P, amount=80000)["crypto"], g.load_limits(AMIRA_P, amount=80000)["crypto_tier"]) == (0.10, "soft")
    no = g.load_limits({**AMIRA_P, "crypto": False}, amount=80000)
    assert (no["crypto"], no["crypto_tier"]) == (0.0, "preference")
    edited = g.load_limits(ROBERT_P, {"floor": -0.20}, amount=600000)
    assert (edited["floor"], edited["scenario_stress"]) == (-0.20, -0.10)


def test_tiers_give_the_three_verdicts_and_their_words():
    assert _status(ROBERT_P, 600000, dd=-0.20)[1] == "Incompatible"
    assert _status(ROBERT_P, 600000, stocks={"NVDA": {"direct": 0.12, "via": [], "total": 0.12}})[1] == "Tension"
    assert _status(ROBERT_P, 600000, weights={"BTC-USD": 0.05, "XIU.TO": 0.95})[1] == "Tension"
    assert _status(ROBERT_P, 600000, risk={"XIU.TO": 0.71, "XBB.TO": 0.29})[1] == "Compatible"
    assert _status({**ROBERT_P, "horizon_years": 2}, 600000, risk={"XIU.TO": 0.71, "XBB.TO": 0.29})[1] == "Tension"
    assert _gov().check_profile(None, {"XIU.TO": 1.0}, _analysis(ROBERT_P, 600000)) == [] and _gov().verdict([]) is None
    assert {k: v for k, v in pytest.importorskip("config").VERDICT_WORDS.items() if k is not None} == {"Compatible": "Inside your limits", "Tension": "Inside, with caveats", "Incompatible": "Outside your limits"}  # None → "Limits missing" is the 4th key (ruling Sat 22:35)


def test_round_half_up_at_the_limit():
    g = _gov()
    assert (g.round_pp(-0.1500004), g.round_pp(0.08)) == (Decimal("-15.0"), Decimal("8.0"))
    for dd, status in ((-0.1500004, "pass"), (-0.15049, "pass"), (-0.15051, "fail")):
        assert _row(_status(ROBERT_P, 600000, dd=dd)[0], "max_drawdown")["status"] == status, dd
    edge = {"NVDA": {"direct": 0.1000000001, "via": [], "total": 0.1000000001}}
    assert _row(_status(ROBERT_P, 600000, stocks=edge)[0], "single_stock")["status"] == "pass"
    for share, status in ((0.5004, "pass"), (0.5006, "warn")):
        assert _row(_status(ROBERT_P, 600000, risk={"XIU.TO": share, "XBB.TO": 1 - share})[0], "risk_concentration")["status"] == status


def test_one_cause_one_fail():
    nvda = {"NVDA": {"direct": 0.40, "via": [], "total": 0.40}}
    checks, v = _status(ROBERT_P, 600000, weights={"NVDA": 0.4, "XIU.TO": 0.6}, stocks=nvda, sectors={"Information Technology": 0.426})
    assert _row(checks, "single_stock")["holding"] == _row(checks, "sector")["holding"] == "NVDA"
    assert _row(checks, "single_stock")["status"] == _row(checks, "sector")["status"] == "fail"
    assert _gov().count_fails(checks) == 1 and v == "Tension"
    cnq = {"CNQ.TO": {"direct": 0.12, "via": [], "total": 0.12}}
    checks, _ = _status(MATEO_P, 250000, weights={"CNQ.TO": 0.12, "XIU.TO": 0.88}, stocks=cnq)
    assert {c["rule"] for c in checks if c["status"] == "fail"} == {"single_stock", "esg_direct"} and _gov().count_fails(checks) == 1


def test_turbulence_check_warns_without_enough_clean_storms():
    none = _row(_status(ROBERT_P, 600000, stress=None, n=0)[0], "scenario_stress")
    assert none["status"] == "warn" and "no close precedent" in none["reason"].lower()
    few = _row(_status(ROBERT_P, 600000, stress=-0.20, n=1)[0], "scenario_stress")
    assert few["status"] == "warn" and "too few separate episodes to conclude" in few["reason"].lower()   # ledger 30 (spec 5: "shocks")
    assert _row(_status(ROBERT_P, 600000, stress=-0.075, n=2)[0], "scenario_stress")["status"] == "pass"   # exactly half the floor
    assert _row(_status(ROBERT_P, 600000, stress=-0.076, n=2)[0], "scenario_stress")["status"] == "warn"   # beyond: a Caution, never a fail


def test_recovery_is_a_warn_only_beyond_half_the_floor():
    assert _row(_status(ROBERT_P, 600000, dd=-0.05, rec=None, since=900)[0], "recovery")["status"] == "pass"
    slow = _row(_status(ROBERT_P, 600000, dd=-0.12, rec=None, since=900)[0], "recovery")
    assert (slow["tier"], slow["status"]) == ("warn", "warn")


def test_values_rules_direct_fail_indirect_warn():
    checks, v = _status(MATEO_P, 250000, weights={"CNQ.TO": 0.08, "XIU.TO": 0.92}, esg_indirect={"XIU.TO": 0.0583},
                        stocks={"CNQ.TO": {"direct": 0.08, "via": [{"etf": "XIU.TO", "weight": 0.0317}], "total": 0.0917}})
    assert (_row(checks, "esg_direct")["tier"], _row(checks, "esg_direct")["status"], _row(checks, "esg_direct")["holding"]) == ("hard", "fail", "CNQ.TO")
    assert _row(checks, "esg_indirect")["status"] == "warn" and _row(checks, "single_stock")["status"] == "pass" and v == "Incompatible"
    assert _row(_status(MATEO_P, 250000, esg_indirect={"XIU.TO": 0.009})[0], "esg_indirect")["status"] == "pass"
    off = _status(ROBERT_P, 600000, weights={"CNQ.TO": 0.08, "XIU.TO": 0.92})[0]
    assert all(c["status"] == "pass" for c in off if c["rule"].startswith("esg"))


def test_every_row_is_one_plain_sentence_with_number_and_limit():
    checks, _ = _status(ROBERT_P, 600000, dd=-0.345)
    for c in checks:
        assert set(c) == {"rule", "tier", "status", "value", "limit", "holding", "reason"}
        assert c["tier"] in {"hard", "soft", "preference", "warn"} and c["status"] in {"pass", "warn", "fail"}
        assert c["reason"] and not ADVICE_WORDS.search(c["reason"])
        assert "\n" not in c["reason"] and c["reason"].rstrip().endswith("."), c["rule"]    # one sentence on one line
    dd = _row(checks, "max_drawdown")
    assert (dd["tier"], dd["status"], dd["limit"]) == ("hard", "fail", -0.15)
    assert _gov().fmt_pct(-0.345) in dd["reason"] and _gov().fmt_pct(-0.15) in dd["reason"]


def test_the_verdict_is_decided_by_tier_and_warn_count_alone():
    v = _gov().verdict
    hard_fail, soft_fail = _line("max_drawdown", "hard", "fail"), _line("single_stock", "soft", "fail", "NVDA")
    pref_fail, ok = _line("esg_direct", "preference", "fail", "CNQ.TO"), _line("sector", "soft", "pass")
    warn_a, warn_b = _line("risk_concentration", "warn", "warn", "XIU.TO"), _line("short_horizon", "warn", "warn")
    assert v([]) is None                                                      # no limits, no verdict
    assert v([ok]) == v([ok, warn_a]) == "Compatible"                         # one warn alone does not move it
    # Ruling R8 (Sun 00:45): a shock warn that cannot conclude never moves the verdict ALONE, but it still counts toward two warns.
    assert v([ok, warn_a, warn_b]) == v([_line("scenario_stress", "soft", "warn"), warn_a]) == "Tension"   # two warns, whatever their tier
    assert v([soft_fail]) == v([pref_fail]) == v([soft_fail, pref_fail, warn_a]) == "Tension"
    assert v([hard_fail]) == v([ok, hard_fail]) == v([hard_fail, soft_fail, pref_fail, warn_a, warn_b]) == "Incompatible"


def test_the_shock_check_beyond_its_limit_is_a_caution_never_a_fail():
    # Ledger 30 and spec 24 res 9 and 11: the soft shock check shows "Caution" with its episode count, never "Fail". Its status
    # is warn and its tier stays soft, so a breach adds no fail. The verdict it gave as a soft fail does not move: a Caution
    # keeps "Inside, with caveats" (res 11: soft rows say "Caution" under it), never "Outside". The sentence carries the count
    # of separate earlier episodes ("in the 6 separate earlier tariffs episodes, this mix lost up to 9.0 %"), never says fail,
    # never forecasts.
    for stress, status, verdict in ((-0.05, "pass", "Compatible"), (-0.09, "warn", "Tension")):
        checks, v = _status(ROBERT_P, 600000, stress=stress, n=6)
        row = _row(checks, "scenario_stress")
        assert (row["tier"], row["status"], row["value"], row["limit"]) == ("soft", status, stress, -0.075)
        assert _says_count(row["reason"], 6) and not re.search(r"\bfail", row["reason"], re.I), row["reason"]
        assert not ADVICE_WORDS.search(row["reason"]) and not FORECAST_WORDS.search(row["reason"]), row["reason"]
        assert v == verdict and _gov().count_fails(checks) == 0
    for n in (2, 4, 26):                                     # a breach is a Caution however many episodes back it
        assert _row(_status(ROBERT_P, 600000, stress=-0.09, n=n)[0], "scenario_stress")["status"] == "warn", n


def test_no_close_precedent_exactly_without_a_value_and_too_few_exactly_under_two_episodes():
    # Ledger 30: "no close precedent" iff the tool gave no value; "too few separate episodes to conclude" iff a value rests on
    # fewer than 2 clean episodes. Both are warns whatever the value says; with a value and 2 or more episodes, neither phrase.
    def read(stress, n):
        row = _row(_status(ROBERT_P, 600000, stress=stress, n=n)[0], "scenario_stress")
        return row["status"], row["reason"].lower()
    for n in (0, 1, 2, 5):                                   # no value: no close precedent, whatever the count says
        status, text = read(None, n)
        assert status == "warn" and "no close precedent" in text and "too few" not in text, n
    for n in (0, 1):                                         # a value on fewer than 2 clean episodes: too few, even inside the limit
        for stress in (-0.01, -0.20):
            status, text = read(stress, n)
            assert status == "warn" and "too few separate episodes to conclude" in text and "no close precedent" not in text, (stress, n)
    assert _says_count(read(-0.20, 1)[1], 1)                 # "only 1 clean ... episode": the count is stated
    for n in (2, 3):
        for stress in (-0.01, -0.20):
            text = read(stress, n)[1]
            assert "too few" not in text and "no close precedent" not in text, (stress, n)


def test_a_shock_check_that_cannot_conclude_never_moves_the_verdict_alone():
    # Ledger 30, "Verdict and direct mode" (lines 663-664), and ruling R8 (Sun 00:45): "no close precedent" (no value) and
    # "too few separate episodes to conclude" (under 2 episodes, whatever value they carry, even one beyond the limit) are
    # plain warns. ALONE they never move the verdict, so a lone one reads "Inside your limits"; a Caution that concludes
    # (beyond the limit on 2 or more episodes, the test above) is the one that lifts it. R51: it never counts toward the
    # two warns.
    g, words = _gov(), pytest.importorskip("config").VERDICT_WORDS
    for stress, n in ((None, 0), (None, 3), (-0.05, 0), (-0.05, 1), (-0.20, 0), (-0.20, 1)):
        checks, v = _status(ROBERT_P, 600000, stress=stress, n=n)
        row = _row(checks, "scenario_stress")
        assert (row["tier"], row["status"]) == ("soft", "warn") and g.count_fails(checks) == 0, (stress, n)
        assert [c["rule"] for c in checks if c["status"] != "pass"] == ["scenario_stress"], (stress, n)   # it really is alone
        assert v == "Compatible" and words[v] == "Inside your limits", (stress, n)
    assert _status(ROBERT_P, 600000, stress=-0.20, n=2)[1] == "Tension"       # the same value on 2 separate episodes concludes
    for stress, n in ((None, 0), (-0.20, 1)):                                 # next to a second warn (a 2-year horizon): R51,
        checks, v = _status({**ROBERT_P, "horizon_years": 2}, 600000, stress=stress, n=n)   # only short_horizon counts
        assert {c["rule"] for c in checks if c["status"] == "warn"} == {"scenario_stress", "short_horizon"} and v == "Compatible", (stress, n)


ROUNDING_CASES = [   # rule, profile, amount, limit key (None = 0 %), ((offset from the limit, status), ...), builder: value -> _status keywords
    ("scenario_stress", ROBERT_P, 600000, "scenario_stress", ((-0.00004, "pass"), (-0.0006, "warn")), lambda x: {"stress": x, "n": 3}),
    ("single_stock", ROBERT_P, 600000, "single_stock", ((0.00004, "pass"), (0.0006, "fail")),
     lambda x: {"stocks": {"NVDA": {"direct": x, "via": [], "total": x}}}),
    ("sector", ROBERT_P, 600000, "sector", ((0.00004, "pass"), (0.0006, "fail")), lambda x: {"sectors": {"Information Technology": x}}),
    ("crypto", ROBERT_P, 600000, "crypto", ((0.00004, "pass"), (0.0006, "fail")), lambda x: {"weights": {"BTC-USD": x, "XIU.TO": 1 - x}}),
    ("esg_direct", MATEO_P, 250000, None, ((0.00004, "pass"), (0.0006, "fail")), lambda x: {"weights": {"CNQ.TO": x, "XIU.TO": 1 - x}}),
    ("esg_indirect", MATEO_P, 250000, "esg_indirect_warn", ((-0.00051, "pass"), (-0.00049, "warn")),
     lambda x: {"esg_indirect": {"XIU.TO": x}}),
]


@pytest.mark.parametrize("rule, profile, amount, key, pairs, build", ROUNDING_CASES, ids=[c[0] for c in ROUNDING_CASES])
def test_every_percent_threshold_compares_after_rounding_to_a_tenth_of_a_point(rule, profile, amount, key, pairs, build):
    # Pitfall 5: strictly beyond the limit AFTER round_pp, so 0.004 pp over passes and 0.06 pp over does not. The values-screen
    # warning is "reaches 1 %": 0.949 % (0.9 % after rounding) does not warn, 0.951 % (1.0 %) does. The limit is read from
    # load_limits, never typed in.
    limit = 0.0 if key is None else _gov().load_limits(profile, amount=amount)[key]
    for offset, status in pairs:
        assert _row(_status(profile, amount, **build(limit + offset))[0], rule)["status"] == status, (rule, offset)


def test_limits_are_read_from_personas_json_through_load_limits():
    g, th = _gov(), PERSONAS["thresholds"]                                    # section 1 pins the file to spec 5
    for band, level in PERSONAS["risk_levels"].items():
        plain = g.load_limits({**ROBERT_P, "risk": band, "capacity": None})
        assert (plain["floor"], plain["floor_source"], plain["band_floor"]) == (level["max_drawdown"], "band", level["max_drawdown"])
        assert (plain["single_stock"], plain["sector"]) == (level["max_single_stock"], level["max_sector"])
        assert plain["scenario_stress"] == pytest.approx(level["max_drawdown"] * th["scenario_stress_fraction"])
        assert (plain["crypto"], plain["crypto_tier"]) == (0.0, "preference")      # crypto = no is 0 % in every band
        wants = g.load_limits({**ROBERT_P, "risk": band, "capacity": None, "crypto": True})
        assert (wants["crypto"], wants["crypto_tier"]) == (level["max_crypto"], "soft")
    robert = g.load_limits(ROBERT_P, amount=600000)
    assert robert["recovery_days"] == pytest.approx(ROBERT_P["horizon_years"] * 365 * th["recovery_fraction_of_horizon"])
    assert (robert["risk_share"], robert["esg_indirect_warn"], robert["short_horizon_years"]) == (
        th["risk_share_warn"], th["esg_indirect_warn"], th["short_horizon_years"])


def test_the_limits_follow_the_personas_file_when_it_changes(tmp_path, monkeypatch):
    # Pitfall 8: nothing is hardcoded. A copy of the file with every number different must change every limit (the real file
    # and the defaults agree, so only a different file can tell a read from a typed-in value).
    config = pytest.importorskip("config")
    data = json.loads(json.dumps(PERSONAS))
    data["risk_levels"]["moderate"] = {"max_drawdown": -0.30, "max_single_stock": 0.12, "max_sector": 0.33, "max_crypto": 0.04}
    data["thresholds"].update(scenario_stress_fraction=0.4, esg_indirect_warn=0.02, recovery_fraction_of_horizon=0.25,
                              short_horizon_years=5, risk_share_warn=0.6)
    moved = tmp_path / "personas.json"
    moved.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(config, "PERSONAS_JSON", moved)
    lim = _gov().load_limits({**ROBERT_P, "capacity": None, "crypto": True})
    assert (lim["floor"], lim["single_stock"], lim["sector"], lim["crypto"]) == (-0.30, 0.12, 0.33, 0.04)
    assert lim["scenario_stress"] == pytest.approx(-0.12) and lim["recovery_days"] == pytest.approx(4 * 365 * 0.25)
    assert (lim["esg_indirect_warn"], lim["short_horizon_years"], lim["risk_share"]) == (0.02, 5, 0.6)


def test_a_missing_data_row_exists_only_when_a_held_line_is_flagged():
    assert all(c["rule"] != "missing_data" for c in _status(ROBERT_P, 600000)[0])
    a = _analysis(ROBERT_P, 600000)
    a["missing_data"] = ["XIU.TO"]
    row = _row(_gov().check_profile(ROBERT_P, {"XIU.TO": 1.0}, a), "missing_data")
    assert (row["tier"], row["status"]) == ("warn", "warn") and "XIU.TO" in row["reason"]


def _starter_folder(dst, lines, first_rate):
    """The four starter CSVs (spec 9 columns) for {ticker: (currency, {iso date: price})}; USD/CAD exists from `first_rate` on."""
    days = sorted({d for _, points in lines.values() for d in points})
    universe = [(f"A{i:02d}", t, t, "equity", "TSX" if cur == "CAD" else "NASDAQ", cur, "Industrials")
                for i, (t, (cur, _)) in enumerate(lines.items(), 1)]
    prices = [(d, t, v, v, v, v, v, 1000, cur) for t, (cur, points) in lines.items() for d, v in points.items()]
    pd.DataFrame(universe, columns=["asset_id", "ticker", "name", "asset_class", "market", "currency", "sector"]
                 ).to_csv(dst / "assets_universe.csv", index=False)
    pd.DataFrame(prices, columns=["date", "ticker", "open", "high", "low", "close", "adj_close", "volume", "currency"]
                 ).to_csv(dst / "prices_daily.csv", index=False)
    pd.DataFrame({"date": [d for d in days if d >= first_rate], "usdcad": 1.3, "cadusd": 0.77}
                 ).to_csv(dst / "fx_usdcad_daily.csv", index=False)
    pd.DataFrame([(days[0], "V39079", 4.0, "percent", "daily", "policy rate", "test")],
                 columns=["date", "series_id", "value", "unit", "frequency", "label", "source"]
                 ).to_csv(dst / "macro_rates.csv", index=False)


def test_missing_data_names_its_real_cause(tmp_path):
    # Ledger 30 (line 667): the sentence names the cause the data layer found. Spec 5 and tools.data: a price gap of more than
    # 3 days (a hole in a line's prices), or a USD price with no USD/CAD rate yet (days before the first rate). Built through the
    # real tools.data.load_market on a small starter folder and judged by evaluate, so the flag is the data layer's own, and each
    # ticker must stand beside its own cause. A flagged line held at 0 is not held, so it is not named (ledger 22).
    days = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2024-01-02", periods=40)]
    lines = {"NVDA": ("USD", {d: 100 + i * 0.1 for i, d in enumerate(days)}),
             "RY.TO": ("CAD", {d: 50 + i * 0.05 for i, d in enumerate(days) if not 10 <= i <= 16})}     # 7 days with no price
    _starter_folder(tmp_path, lines, first_rate=days[3])                                                  # NVDA: 3 days before a rate
    market = pytest.importorskip("tools.data").load_market(days[-1], data_dir=tmp_path)
    assert market["flags"]["NVDA"] and market["flags"]["RY.TO"]                                          # the premise: both are flagged

    def reason(held):
        out = _gov().evaluate(ROBERT_P, held, [], days[-1], market=market, events=[], today=False, esg_flags=set(), amount=600000)
        rows = [c for c in out["checks"] if c["rule"] == "missing_data"]
        assert len(rows) == 1 and (rows[0]["tier"], rows[0]["status"]) == ("warn", "warn"), held
        return rows[0]["reason"]
    gap, rate = reason({"RY.TO": 1.0, "NVDA": 0.0}), reason({"NVDA": 1.0, "RY.TO": 0.0})      # the line at 0 is flagged, not held
    both = reason({"NVDA": 0.5, "RY.TO": 0.5})
    assert "RY.TO has a price gap of more than 3 days" in gap and "USD/CAD" not in gap and "NVDA" not in gap
    assert "NVDA has a USD price with no USD/CAD rate yet" in rate and "price gap" not in rate and "RY.TO" not in rate
    clause = {t: next(part for part in both.split(";") if t in part) for t in ("NVDA", "RY.TO")}
    assert "price gap of more than 3 days" in clause["RY.TO"] and "USD/CAD" not in clause["RY.TO"]
    assert "no USD/CAD rate" in clause["NVDA"] and "price gap" not in clause["NVDA"]


def test_partial_look_through_coverage_is_a_disclosure_never_a_warn():
    a = _analysis(ROBERT_P, 600000, risk=CALM_RISK)
    a["lookthrough"]["coverage"], a["lookthrough"]["gaps"] = {"XIU.TO": 0.779}, []     # the real file lists 77.9 % of XIU.TO
    checks = _gov().check_profile(ROBERT_P, {"XIU.TO": 1.0}, a)
    assert [c["rule"] for c in checks if c["status"] != "pass"] == [] and _gov().verdict(checks) == "Compatible"


def test_a_missing_data_warn_lifts_the_verdict_to_caveats_at_best():
    # Ruling (spec 5, ledger 29 and 30, spec 21 move 4): "unknown is never a pass". One missing_data warn is enough for
    # "Inside, with caveats"; it never softens a hard fail.
    g = _gov()
    gap = _line("missing_data", "warn", "warn")
    assert g.verdict([gap]) == g.verdict([_line("sector", "soft", "pass"), gap]) == "Tension"
    assert g.verdict([_line("max_drawdown", "hard", "fail"), gap]) == "Incompatible"
    a = _analysis(ROBERT_P, 600000, risk=CALM_RISK)
    a["missing_data"] = ["XIU.TO"]
    checks = g.check_profile(ROBERT_P, {"XIU.TO": 1.0}, a)
    assert [c["rule"] for c in checks if c["status"] != "pass"] == ["missing_data"] and g.verdict(checks) == "Tension"


def test_a_look_through_gap_is_a_named_caveat():
    # A held equity ETF with no holdings rows, or no sector rows, has unknown (not zero) exposure: a named caveat (ledger 29).
    g = _gov()
    for missing in ("holdings", "sectors"):
        a = _analysis(ROBERT_P, 600000, risk=CALM_RISK)
        a["lookthrough"]["gaps"] = [{"etf": "XIU.TO", "missing": missing, "coverage": 0.0}]
        checks = g.check_profile(ROBERT_P, {"XIU.TO": 1.0}, a)
        caveats = [c for c in checks if c["status"] == "warn"]
        assert len(caveats) == 1 and "XIU.TO" in caveats[0]["reason"] and g.verdict(checks) == "Tension", missing


def test_the_recovery_limit_is_compared_unrounded():
    # Ledger 10: four years = 4 x 365 x 0.3333 = 486.618 days. Only the display rounds, so 487 days is beyond it and 486 is not.
    inside, beyond = (_row(_status(ROBERT_P, 600000, dd=-0.12, rec=days)[0], "recovery") for days in (486, 487))
    assert (inside["status"], beyond["status"]) == ("pass", "warn")
    assert beyond["limit"] == pytest.approx(486.6, abs=0.2) and inside["value"] == 486


def test_recovery_sentences_state_whole_days():
    # Spec 24 res 7 ("whole days"): 486.618 shows as 487 days, Mateo's 1,216.545 as 1,217; never a fraction of a day.
    g = _gov()
    for profile, amount, dd, whole in ((ROBERT_P, 600000, -0.12, 487), (MATEO_P, 250000, -0.20, 1217)):
        for rec, since in ((200, 900), (whole + 400, 900), (None, whole + 400)):    # recovered fast, recovered slowly, not yet
            row = _row(g.check_profile(profile, {"XIU.TO": 1.0}, _analysis(profile, amount, dd=dd, rec=rec, since=since)), "recovery")
            text = row["reason"].replace(",", "")
            assert re.search(rf"\b{whole}[\s\u00a0]days\b", text), text
            assert not re.search(r"\d\.\d+[\s\u00a0]days", text), text


def test_a_horizon_is_short_only_below_three_years():
    # Spec 5: "money needed in < 3 years"; the level (3) is in personas.json, so exactly 3 years is not short.
    assert PERSONAS["thresholds"]["short_horizon_years"] == 3
    for years, status in ((1, "warn"), (2, "warn"), (3, "pass"), (4, "pass")):
        row = _row(_status({**ROBERT_P, "horizon_years": years}, 600000)[0], "short_horizon")
        assert (row["status"], row["value"], row["limit"]) == (status, years, 3), years


def test_only_equity_sectors_count_and_a_past_date_uses_direct_lines():
    # Spec 5: bonds, gold and crypto are asset classes, not sectors; a past date (Sealed envelope, walk-forward) has no
    # look-through, so only direct lines count and broad-market and bond ETFs are exempt from the sector rule.
    g = _gov()
    seen = _row(_status(ROBERT_P, 600000, weights={"XBB.TO": 0.7, "XIU.TO": 0.3},
                        sectors={"Bonds (Canada aggregate)": 0.70, "Gold": 0.05, "Crypto asset": 0.04, "Financials": 0.20})[0], "sector")
    assert seen["status"] == "pass" and seen["value"] == pytest.approx(0.20)       # the biggest EQUITY sector, not the bond fund
    past = {**_analysis(ROBERT_P, 600000), "lookthrough": None}
    checks = g.check_profile(ROBERT_P, {"NVDA": 0.12, "XIU.TO": 0.60, "XBB.TO": 0.28}, past)
    single, sector = _row(checks, "single_stock"), _row(checks, "sector")
    assert (single["holding"], single["status"]) == ("NVDA", "fail")               # 12 % direct > 10 %
    assert sector["status"] == "pass" and sector["value"] == pytest.approx(0.12)   # NVDA only: XIU.TO 60 % and XBB.TO 28 % are exempt


def test_a_company_is_excluded_by_a_flag_row_or_by_the_energy_sector():
    # Spec 5: "excluded company held directly (only if ESG = yes): sector Energy or data/esg_flags.csv".
    g = _gov()
    no_flags = {**_analysis(MATEO_P, 250000), "esg_flags": set()}
    row = _row(g.check_profile(MATEO_P, {"CNQ.TO": 0.08, "XIU.TO": 0.92}, no_flags), "esg_direct")
    assert (row["tier"], row["status"], row["holding"]) == ("hard", "fail", "CNQ.TO")      # Energy, no flag row needed
    flagged = {**_analysis(MATEO_P, 250000), "esg_flags": {"NVDA"}}
    row = _row(g.check_profile(MATEO_P, {"NVDA": 0.08, "XIU.TO": 0.92}, flagged), "esg_direct")
    assert (row["status"], row["holding"]) == ("fail", "NVDA")                                    # a flag row alone is enough


def test_no_profile_means_limits_missing():
    g = _gov()
    assert g.load_limits(None) is None and g.check_profile(None, {"XIU.TO": 1.0}, _analysis(ROBERT_P, 600000)) == []
    assert g.verdict([]) is None                              # spec 5: no limits, no verdict ...
    assert pytest.importorskip("config").VERDICT_WORDS[None] == "Limits missing"      # ... and the page says so


def _direct_mode(profile, amount):
    """A run on a fresh clone: today's look-through opened no fund (mode direct), XIU.TO held."""
    base = _analysis(profile, amount)
    return {**base, "lookthrough": {**base["lookthrough"], "mode": "direct"}}


def test_a_fresh_clone_says_its_funds_were_not_looked_through():
    # Ledger 30: a fresh clone without the holdings list runs in direct mode, and the checklist says so as a caveat on the
    # look-through rows, so a missing look-through is never read as "no exposure". A run that looked through, and a past date
    # (direct by design, spec 5), have nothing to say.
    g = _gov()
    for profile, amount in ((ROBERT_P, 600000), (MATEO_P, 250000)):
        checks = g.check_profile(profile, {"XIU.TO": 1.0}, _direct_mode(profile, amount))
        for rule in ("single_stock", "sector"):
            assert "XIU.TO" in _row(checks, rule)["reason"] and "looked through" in _row(checks, rule)["reason"], (profile["esg"], rule)
        assert all(not ADVICE_WORDS.search(c["reason"]) and not FORECAST_WORDS.search(c["reason"]) for c in checks)
        base = _analysis(profile, amount)
        for plain in (g.check_profile(profile, {"XIU.TO": 1.0}, base),
                      g.check_profile(profile, {"XIU.TO": 1.0}, {**base, "lookthrough": None})):
            assert not [c for c in plain if "looked through" in c["reason"]]


def test_the_fresh_clone_caveat_stays_inside_one_sentence():
    checks = _gov().check_profile(ROBERT_P, {"XIU.TO": 1.0}, _direct_mode(ROBERT_P, 600000))
    for rule in ("single_stock", "sector"):
        assert len(re.findall(r"[.!?](?=\s|$)", _row(checks, rule)["reason"])) == 1, rule


def test_direct_mode_rows_are_warns_with_no_value_never_a_pass():
    # Ledger 30, "Verdict and direct mode" (lines 665-667): with no holdings file (mode "direct") and an equity fund held,
    # the single-company, sector and indirect-values rows never read pass with a 0.0 or None value: each is a warn with no
    # value whose ONE sentence says the fund was not looked through, so the companies inside it are not known from holdings.
    # Unknown is never a pass (spec 5).
    g = _gov()
    for profile, amount, rules in ((ROBERT_P, 600000, ("single_stock", "sector")),
                                   (MATEO_P, 250000, ("single_stock", "sector", "esg_indirect"))):
        checks = g.check_profile(profile, {"XIU.TO": 1.0}, _direct_mode(profile, amount))
        for rule in rules:
            row = _row(checks, rule)
            assert (row["status"], row["value"], row["holding"]) == ("warn", None, None), rule
            assert "XIU.TO was not looked through" in row["reason"] and "not known from holdings" in row["reason"], rule
            assert len(re.findall(r"[.!?](?=\s|$)", row["reason"])) == 1, rule        # a clause of the sentence, not a second one
        assert g.verdict(checks) == "Tension", profile["esg"]                         # never "Inside your limits"
    small = _analysis(ROBERT_P, 600000, stocks={"NVDA": {"direct": 0.05, "via": [], "total": 0.05}},
                      sectors={"Information Technology": 0.05})
    small["lookthrough"]["mode"] = "direct"
    inside = g.check_profile(ROBERT_P, {"NVDA": 0.05, "XIU.TO": 0.95}, small)         # a direct 5 % says nothing about what XIU.TO holds
    assert [(_row(inside, r)["status"], _row(inside, r)["value"]) for r in ("single_stock", "sector")] == [("warn", None)] * 2
    bonds = g.check_profile(ROBERT_P, {"XBB.TO": 1.0}, _direct_mode(ROBERT_P, 600000))   # no equity fund held: nothing was left unopened
    assert [_row(bonds, r)["status"] for r in ("single_stock", "sector")] == ["pass", "pass"]
    assert not [c for c in bonds if "looked through" in c["reason"]]


def test_a_company_beyond_its_limit_stays_a_fail_in_direct_mode():
    # Ledger 30 (lines 665-667): what is known is still said. NVIDIA held directly at 40 % is beyond the one-company and the one-sector
    # limit whatever is inside XIU.TO, so both rows stay fails (one cause, one fail), still one sentence each.
    g = _gov()
    a = _analysis(ROBERT_P, 600000, stocks={"NVDA": {"direct": 0.40, "via": [], "total": 0.40}},
                  sectors={"Information Technology": 0.40})
    a["lookthrough"]["mode"] = "direct"
    checks = g.check_profile(ROBERT_P, {"NVDA": 0.40, "XIU.TO": 0.60}, a)
    for rule in ("single_stock", "sector"):
        row = _row(checks, rule)
        assert (row["status"], row["holding"], row["value"]) == ("fail", "NVDA", 0.40), rule
        assert len(re.findall(r"[.!?](?=\s|$)", row["reason"])) == 1, rule
    assert g.count_fails(checks) == 1 and g.verdict(checks) == "Tension"


def _checklists():
    """Checklists in many states (rules passing, warning and failing, past date, the navigator's abstention), so every
    sentence the page can show is read. The fresh clone's direct mode has its own tests below."""
    nvda = {"NVDA": {"direct": 0.40, "via": [], "total": 0.40}}
    cnq = {"CNQ.TO": {"direct": 0.08, "via": [{"etf": "XIU.TO", "weight": 0.0317}], "total": 0.0917}}
    short = {**ROBERT_P, "horizon_years": 2}
    yield ROBERT_P, {"XIU.TO": 1.0}, {**_analysis(ROBERT_P, 600000, dd=-0.345), "loss_dollars": 207146.0}
    yield short, {"NVDA": 0.4, "BTC-USD": 0.05, "XIU.TO": 0.55}, {**_analysis(
        short, 600000, dd=-0.20, rec=None, stress=-0.09, n=5, stocks=nvda, sectors={"Information Technology": 0.426},
        risk={"XIU.TO": 0.7, "XBB.TO": 0.3}), "missing_data": ["XIU.TO", "XBB.TO"]}
    yield ROBERT_P, {"XIU.TO": 1.0}, _analysis(ROBERT_P, 600000, stress=None, n=0)
    yield ROBERT_P, {"XIU.TO": 1.0}, {**_analysis(ROBERT_P, 600000, stress=-0.2, n=1), "scenario_label": "Indicative (mixed with h20_2025)"}
    yield MATEO_P, {"CNQ.TO": 0.08, "XIU.TO": 0.92}, _analysis(MATEO_P, 250000, stocks=cnq, esg_indirect={"XIU.TO": 0.0583})
    yield MATEO_P, {"XIU.TO": 1.0}, _analysis(MATEO_P, 250000)
    yield ROBERT_P, {"XIU.TO": 1.0}, {**_analysis(ROBERT_P, 600000, stress=None, n=0), "scenario_family": ""}   # the abstention (ledger 30)
    yield AMIRA_P, {"BTC-USD": 0.15, "XIU.TO": 0.85}, _analysis(AMIRA_P, 80000)
    yield AMIRA_P, {"BTC-USD": 0.00004, "XIU.TO": 0.99996}, _analysis(AMIRA_P, 80000)
    yield MATEO_P, {"CNQ.TO": 0.00004, "XIU.TO": 0.99996}, _analysis(MATEO_P, 250000)
    yield ROBERT_P, {"NVDA": 0.12, "XIU.TO": 0.88}, {**_analysis(ROBERT_P, 600000), "lookthrough": None}


def test_every_sentence_in_every_state_is_one_plain_sentence_without_advice_or_forecast():
    g, seen = _gov(), 0
    for profile, weights, analysis in _checklists():
        for c in g.check_profile(profile, weights, analysis):
            seen += 1
            assert len(re.findall(r"[.!?](?=\s|$)", c["reason"])) == 1 and c["reason"].rstrip().endswith("."), (c["rule"], c["reason"])
            assert "\n" not in c["reason"] and c["reason"].strip(), (c["rule"], c["reason"])
            assert not ADVICE_WORDS.search(c["reason"]) and not FORECAST_WORDS.search(c["reason"]), (c["rule"], c["reason"])
    assert seen > 40                                   # the states really covered the rules


# ---- the real-data pilots (plan C Task 7 step 2). Expected values recomputed Sat 18:30-19:00 by an independent script (spec
# sections 9-10 processing, the 37-row catalog): Robert today tariffs worst clean storm -6.0 % (5 clean episodes), after
# -9.0 %; XIU.TO carries 71 % of Robert's risk today (one warn); Mateo's XIU.TO risk share 46 %; Mateo CNQ.TO look-through
# 9.21 %; Amira IT 37.5 %. Ledger 30 (Sat 23:35) amends two of them: the code's tariff numbers stand over the previews
# (6 separate earlier episodes, evidence Indicative, -6.0 % today and -9.0 % after) and the shock check beyond its
# threshold is a warn, so Robert after fails three checks that count as two causes. Re-run with every real tool
# (governance.evaluate, A Tasks 8 and 10). They need the local data and skip without it. ----
ROBERT = {"XIU.TO": 0.45, "XBB.TO": 0.35, "GLD": 0.10, "ZST.TO": 0.10}
ROBERT_AFTER = {"NVDA": 0.40, "XIU.TO": 0.27, "XBB.TO": 0.21, "GLD": 0.06, "ZST.TO": 0.06}
MATEO = {"XIU.TO": 0.35, "XBB.TO": 0.35, "CNQ.TO": 0.08, "MSFT": 0.10, "GLD": 0.12}
AMIRA = {"NVDA": 0.15, "QQQ": 0.15, "SHOP.TO": 0.10, "BTC-USD": 0.15, "XIU.TO": 0.30, "XBB.TO": 0.15}


def _judge(profile, weights, families, amount, as_of="2026-11-12", **kw):
    out = _gov().evaluate(profile, weights, families, as_of, amount=amount, **kw)
    return out, {c["rule"] for c in out["checks"] if c["status"] == "fail"}, {c["rule"] for c in out["checks"] if c["status"] == "warn"}


@NEEDS_HOLDINGS
def test_robert_inside_today_outside_after():
    today, fails, warns = _judge(ROBERT_P, ROBERT, ["tariffs"], 600000)
    assert today["verdict"] == "Compatible" and not fails and warns == {"risk_concentration"}
    assert (today["limits"]["floor"], today["limits"]["floor_source"]) == (-0.15, "capacity")
    assert today["kpis"]["scenario_stress"]["value"] == pytest.approx(-0.060, abs=0.003)
    after, fails, warns = _judge(ROBERT_P, ROBERT_AFTER, ["tariffs"], 600000)
    # Ledger 30: the shock check beyond its threshold is a Caution (warn), never a fail. One cause, one fail: NVDA's
    # single-stock and sector fails share the holding NVDA and count once, the floor is the other cause.
    assert after["verdict"] == "Incompatible" and fails == {"max_drawdown", "single_stock", "sector"} and "scenario_stress" in warns
    assert _row(after["checks"], "single_stock")["holding"] == _row(after["checks"], "sector")["holding"] == "NVDA"
    assert _gov().count_fails(after["checks"]) == 2
    assert after["kpis"]["max_drawdown"]["value"] == pytest.approx(-0.345, abs=0.001)
    assert after["kpis"]["scenario_stress"]["value"] == pytest.approx(-0.090, abs=0.003)
    # The shock line rests on 6 separate earlier episodes with evidence Indicative (a mixed episode counts; ledger 30: the
    # code's numbers stand over the earlier previews of 5) and says how many.
    for out in (today, after):
        assert out["stress"]["n_episodes"] == 6 and out["turbulence"]["tariffs"]["evidence"] == "Indicative"
        assert _says_count(_row(out["checks"], "scenario_stress")["reason"], 6)


@NEEDS_HOLDINGS
def test_mateo_values_say_no():
    out, fails, warns = _judge(MATEO_P, MATEO, ["war_oil"], 250000)
    assert out["verdict"] == "Incompatible" and fails == {"esg_direct"} and "esg_indirect" in warns   # values on: a direct line is a hard limit
    # CNQ.TO is 8 % direct plus 1.21 % inside XIU.TO = 9.21 % of the money (the look-through total) ...
    assert out["lookthrough"]["stocks"]["CNQ.TO"]["total"] == pytest.approx(0.0921, abs=0.0005)
    # ... but the one-company row reports the LARGEST company, MSFT at exactly 10 %, and exactly at the limit passes
    single = _row(out["checks"], "single_stock")
    assert (single["holding"], single["status"]) == ("MSFT", "pass") and single["value"] == pytest.approx(0.10, abs=1e-6)
    # The significance rule (Sun Nov 15): the warning inside his funds names energy names, never a bank's pay dispute.
    inside = out["lookthrough"]["esg_indirect"]
    assert set(inside) == {"ENB.TO", "CNQ.TO", "CNR.TO"} and "RY.TO" not in inside
    indirect = _row(out["checks"], "esg_indirect")
    assert (indirect["status"], indirect["holding"]) == ("warn", "ENB.TO") and indirect["value"] == pytest.approx(0.033, abs=0.0005)
    assert _row(out["checks"], "esg_direct")["holding"] == "CNQ.TO"


def test_every_controversy_row_meets_the_significance_rule():
    """Environmental enforcement or major social harm; never an employment or pay dispute (Sun Nov 15 rule)."""
    for r in CONTROVERSY.itertuples():
        ours = QUOTED.sub("", r.reason_en).lower()
        assert not re.search(r"\b(pay|wage|wages|employee|employment|overtime|vacation)\b", ours), r.ticker
        assert ("environmental" in ours and r.flag == "controversy_env") or \
            ("social" in ours and r.flag == "controversy_social" and re.search(r"injury|human rights", ours)), r.ticker


@NEEDS_HOLDINGS
def test_amira_high_risk_accepted_crypto_capped():
    out, fails, _ = _judge(AMIRA_P, AMIRA, ["chips"], 80000)
    assert out["verdict"] == "Tension" and fails == {"crypto"}
    assert _row(out["checks"], "sector")["value"] == pytest.approx(0.375, abs=0.002)
    assert out["kpis"]["max_drawdown"]["value"] == pytest.approx(-0.4135, abs=0.002)


@NEEDS_HOLDINGS
def test_same_move_three_pilots():
    assert _judge(MATEO_P, ROBERT_AFTER, ["tariffs"], 250000)[0]["verdict"] == "Incompatible"
    assert _judge(AMIRA_P, ROBERT_AFTER, ["tariffs"], 80000)[0]["verdict"] == "Tension"


@NEEDS_HOLDINGS
def test_robert_floor_breaks_between_8_and_9_percent_of_nvidia():
    # Ledger 14 and spec 10: at 8 % the fall is -15.00004 % (-$90,000, the capacity itself), which rounds to the floor and
    # passes; at 9 % it is -15.6 %. The page says "crossed between 8 % and 9 %", never "you can hold up to 8 %".
    g, apply_change = _gov(), pytest.importorskip("tools.portfolio").apply_change
    judged = {}
    for pct in (8, 9):
        mix = apply_change(ROBERT, {"op": "set", "ticker": "NVDA", "weight": pct / 100, "from_ticker": None})
        judged[pct] = _judge(ROBERT_P, mix, ["tariffs"], 600000)[0]
    dd8, dd9 = (judged[pct]["kpis"]["max_drawdown"]["value"] for pct in (8, 9))
    assert dd8 == pytest.approx(-0.15, abs=1e-4) and g.round_pp(dd8) == Decimal("-15.0")
    assert _row(judged[8]["checks"], "max_drawdown")["status"] == "pass"
    assert judged[8]["analysis"]["loss_dollars"] == pytest.approx(90000, abs=1)
    assert g.round_pp(dd9) == Decimal("-15.6") and _row(judged[9]["checks"], "max_drawdown")["status"] == "fail"


@NEEDS_HOLDINGS
def test_a_headline_with_no_precedent_leaves_the_shock_check_a_warn_with_no_value():
    # Spec 5 and 24 res 5: no family to replay is "no close precedent at this date": a warn, never a pass or a fail. On Robert's
    # own mix it sits next to his 71 % risk share, and the verdict reads "Inside your limits": R51, it never counts toward the
    # two warns (jury QA N1-N3, H5: the missing precedent alone moved his mix to "Inside, with caveats").
    out, fails, warns = _judge(ROBERT_P, ROBERT, [], 600000)
    row = _row(out["checks"], "scenario_stress")
    assert (row["status"], row["value"]) == ("warn", None) and "no close precedent" in row["reason"].lower()
    assert out["kpis"]["scenario_stress"]["value"] is None and not fails
    assert warns == {"risk_concentration", "scenario_stress"} and out["verdict"] == "Compatible"


@NEEDS_DATA
def test_sealed_envelope_date_cannot_conclude_on_tariffs():
    out, _, warns = _judge(ROBERT_P, ROBERT_AFTER, ["tariffs"], 600000, as_of="2025-01-31", today=False)
    assert "scenario_stress" in warns and out["verdict"] in {"Incompatible", "Tension"}
    assert out["turbulence"]["tariffs"]["evidence"] == "Indicative"
    assert out["lookthrough"] is None                      # a past date uses direct holdings only: today's ETF snapshot never leaks in


@NEEDS_DATA
def test_a_fresh_clone_judges_the_pilots_in_direct_mode_through_evaluate(monkeypatch, tmp_path):
    # Ledger 30 (lines 665-667) on the real path of a fresh clone: no holdings file (tools.lookthrough.HOLDINGS_CSV points at a missing
    # path), today's run, real prices. The single-company, sector and indirect-values rows are warns with no value that say
    # the fund was not looked through, so Robert's mix, "Inside your limits" with the file, reads "Inside, with caveats". A
    # company already beyond its limit stays a fail: NVIDIA at 40 % is held directly, so Robert's move is still Outside.
    monkeypatch.setattr(pytest.importorskip("tools.lookthrough"), "HOLDINGS_CSV", tmp_path / "no_such_holdings.csv")
    today, fails, _ = _judge(ROBERT_P, ROBERT, ["tariffs"], 600000)
    assert today["lookthrough"]["mode"] == "direct" and not fails                       # the premise: no fund was opened
    mateo, mateo_fails, _ = _judge(MATEO_P, MATEO, ["war_oil"], 250000)
    for out, rules in ((today, ("single_stock", "sector")), (mateo, ("single_stock", "sector", "esg_indirect"))):
        for rule in rules:
            row = _row(out["checks"], rule)
            assert (row["status"], row["value"], row["holding"]) == ("warn", None, None), rule
            assert "XIU.TO was not looked through" in row["reason"] and "not known from holdings" in row["reason"], rule
            assert len(re.findall(r"[.!?](?=\s|$)", row["reason"])) == 1, rule
    assert today["verdict"] == "Tension"                                                # Compatible when the file is there
    assert mateo["verdict"] == "Incompatible" and mateo_fails == {"esg_direct"}              # the direct CNQ.TO line is still known
    after, after_fails, _ = _judge(ROBERT_P, ROBERT_AFTER, ["tariffs"], 600000)
    assert after["lookthrough"]["mode"] == "direct" and after["verdict"] == "Incompatible"
    assert after_fails == {"max_drawdown", "single_stock", "sector"} and _gov().count_fails(after["checks"]) == 2
    for rule in ("single_stock", "sector"):
        row = _row(after["checks"], rule)
        assert (row["status"], row["holding"]) == ("fail", "NVDA") and row["value"] == pytest.approx(0.40, abs=1e-6), rule
