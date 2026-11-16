import csv, re
from pathlib import Path
import pytest
EP = Path("data/deep_episodes.csv"); PX = Path("data/deep_proxies.csv")
EP_COLS = ["episode_id", "title_en", "description_en", "start", "end", "trigger_date", "kind", "family", "place",
           "lat", "lon", "source_title", "source_url", "verified_on", "census"]
IDS = ["oil_embargo_1973", "volcker_1979", "crash_1987", "gulf_war_1990", "bond_rout_1994", "russia_ltcm_1998",
       "dotcom_2000", "gfc_2008", "euro_2011", "taper_2013", "covid_2020"]
UNIVERSE = ["RY.TO", "TD.TO", "MFC.TO", "ENB.TO", "CNQ.TO", "CNR.TO", "FTS.TO", "ATD.TO", "SHOP.TO", "CSU.TO", "AAPL",
            "MSFT", "NVDA", "GOOGL", "AMZN", "TSLA", "JPM", "JNJ", "PG", "XOM", "XIU.TO", "SPY", "QQQ", "ESGV", "XBB.TO",
            "ZST.TO", "AGG", "TLT", "GLD", "BTC-USD", "ETH-USD"]
PROXY_IDS = {"CA_EQ", "CAD_BOND", "CAD_TBILL", "GOLD", "US_MKT", "BUSEQ", "CHIPS", "SOFTW", "HARDW", "RTAIL", "AUTOS",
             "BANKS", "DRUGS", "HSHLD", "OIL"}
ADVICE = re.compile(r"\b(buy|sell|hold|should|recommend)\b", re.I)
def rows(p): return list(csv.DictReader(p.open(encoding="utf-8")))

def test_episodes_shape_and_order():
    r = rows(EP)
    assert list(r[0].keys()) == EP_COLS and [x["episode_id"] for x in r] == IDS
    for x in r:
        assert re.fullmatch(r"\d{4}-\d{2}", x["start"]) and re.fullmatch(r"\d{4}-\d{2}", x["end"])
        assert "1973-01" <= x["start"] < x["end"] <= "2021-10"
        assert x["start"][:7] <= x["trigger_date"][:7] <= x["end"]
        assert x["kind"] in {"oil_shock", "rate_shock", "crash", "credit_crisis", "pandemic"}
        assert x["family"] in {"", "tariffs", "war_oil", "chips", "rates"} and x["census"] in {"ca_equity", "cad_bonds", "both", "none"}
        assert x["source_url"].startswith("https://") and x["verified_on"] == "2026-11-14" and x["place"]
        assert -90 <= float(x["lat"]) <= 90 and -180 <= float(x["lon"]) <= 180
        assert x["title_en"].strip() and x["description_en"].strip()
        assert not ADVICE.search(x["title_en"]) and not ADVICE.search(x["description_en"])

# Review of 2026-11-14: a description says only what its cited page says (regression for the named defects).
# No primary page was found that states the trigger date of these three rows, so their description carries the note
# (dotcom_2000: the Nasdaq Composite closing high of 2000-03-10 is FRED NASDAQCOM data, not the NBER page).
DATE_NOT_ON_PAGE = {"russia_ltcm_1998", "dotcom_2000", "gfc_2008"}
NOTE = "trigger date not stated on the cited page"      # jury-visible wording (review fix round 1)
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
DATE_RE = re.compile(rf"(?:\d{{1,2}} )?(?:(?:{MONTHS}) )?\d{{4}}")      # "19 October 1973", "March 2001", "1989"
PAGE_DATES = {   # the only dates a description may name; each is stated on that row's cited page (read live 2026-11-14)
    "oil_embargo_1973": {"19 October 1973"}, "volcker_1979": {"6 October 1979"}, "crash_1987": {"19 October 1987"},
    "gulf_war_1990": {"2 August 1990", "16 January 1991"}, "bond_rout_1994": {"4 February 1994", "1989"},
    "russia_ltcm_1998": {"August 1998"}, "dotcom_2000": {"26 November 2001", "March 2001"},
    "gfc_2008": {"2007", "December 2007", "2008", "September 2008"}, "euro_2011": {"7 August 2011"},
    "taper_2013": {"22 May 2013"}, "covid_2020": {"11 March 2020"}}

def test_descriptions_match_their_cited_pages():
    d = {x["episode_id"]: x for x in rows(EP)}
    assert not [i for i, x in d.items() if "began purchasing" in x["description_en"].lower()]
    euro = d["euro_2011"]                    # the ECB page: "the ECB will actively implement its Securities Markets Programme"
    assert "will actively implement its Securities Markets Programme" in euro["description_en"]
    assert "downgrade" not in (euro["title_en"] + " " + euro["description_en"]).lower()
    assert "Governing Council" in euro["description_en"] and "President" not in euro["description_en"]   # page: "The Governing Council ... welcomes"
    oil = d["oil_embargo_1973"]              # Fed History "Oil Shock of 1973-74": "On October 19, 1973 ... OAPEC instituted an oil embargo"
    assert oil["source_url"] == "https://www.federalreservehistory.org/essays/oil-shock-of-1973-74"
    assert oil["trigger_date"] == "1973-10-19" and oil["source_title"] == "Federal Reserve History: Oil Shock of 1973-74"
    assert "On 19 October 1973" in oil["description_en"] and "OAPEC" in oil["description_en"]
    for i, x in d.items():                   # the note appears exactly where the cited page does not state the date
        assert (NOTE in x["description_en"].lower()) == (i in DATE_NOT_ON_PAGE), i

def test_descriptions_carry_no_figures_only_dates_their_pages_state():
    """Plan C Global Constraints: description figures only from the cited page; the app computes market effects itself."""
    assert set(PAGE_DATES) == set(IDS)
    for x in rows(EP):
        text = x["description_en"]
        assert not re.search(r"[%$]|percent|billion|million", text, re.I), x["episode_id"]
        found = {m.group(0) for m in DATE_RE.finditer(text)}
        assert found <= PAGE_DATES[x["episode_id"]], (x["episode_id"], found)
        assert not re.search(r"\d", DATE_RE.sub("", text).replace("COVID-19", "")), x["episode_id"]   # no other number at all

def test_descriptions_fit_the_episode_card():
    """The card shows description_en whole (review of 2026-11-14): every description is under 420 characters."""
    assert [x["episode_id"] for x in rows(EP) if len(x["description_en"]) >= 420] == []

# Spec 23 census rule: ca_equity when the trough of a Canadian stock fall deeper than 15 % lies inside the window, cad_bonds for a
# CAD bond-ladder fall deeper than 10 %, both when each does, none otherwise. Re-derived on the monthly panel (2026-11-14): the bond
# falls near oil_embargo_1973 (-7.3 %, 1974-02 to 06), crash_1987 (-6.6 %, 1987-03 to 09) and gulf_war_1990 (-5.3 %, trough 1990-04,
# before its window starts) are all under 10 %, so those three rows are ca_equity, not both.
EXPECTED_CENSUS = {"oil_embargo_1973": "ca_equity", "volcker_1979": "both", "crash_1987": "ca_equity", "gulf_war_1990": "ca_equity",
                   "bond_rout_1994": "cad_bonds", "russia_ltcm_1998": "ca_equity", "dotcom_2000": "ca_equity",
                   "gfc_2008": "ca_equity", "euro_2011": "ca_equity", "taper_2013": "none", "covid_2020": "ca_equity"}

def test_census_labels_follow_the_section_23_rule():
    assert {x["episode_id"]: x["census"] for x in rows(EP)} == EXPECTED_CENSUS

def test_families_are_cross_references_only():
    fam = {x["episode_id"]: x["family"] for x in rows(EP)}
    assert fam["oil_embargo_1973"] == fam["gulf_war_1990"] == "war_oil"
    assert fam["volcker_1979"] == fam["bond_rout_1994"] == fam["taper_2013"] == "rates"
    assert {fam[i] for i in ["crash_1987", "russia_ltcm_1998", "dotcom_2000", "gfc_2008", "euro_2011", "covid_2020"]} == {""}

def test_proxy_map_covers_the_universe_and_crypto_has_none():
    r = {x["ticker"]: x for x in rows(PX)}
    assert list(rows(PX)[0].keys()) == ["ticker", "proxy", "label", "source", "note"] and sorted(r) == sorted(UNIVERSE)
    assert {x["proxy"] for x in r.values()} - {""} <= PROXY_IDS
    assert r["BTC-USD"]["proxy"] == r["ETH-USD"]["proxy"] == ""          # Can't say, never filled
    assert (r["XIU.TO"]["proxy"], r["XBB.TO"]["proxy"], r["ZST.TO"]["proxy"], r["GLD"]["proxy"]) == ("CA_EQ", "CAD_BOND", "CAD_TBILL", "GOLD")
    assert (r["NVDA"]["proxy"], r["MSFT"]["proxy"], r["QQQ"]["proxy"], r["CNQ.TO"]["proxy"], r["SPY"]["proxy"]) == ("CHIPS", "SOFTW", "BUSEQ", "OIL", "US_MKT")

# --- C Task 13: scripts/fetch_deep.py, the downloader (offline: every download is faked) -----------------------------
import hashlib, json, zipfile
import pandas as pd

def _xlsx(path, rows):                    # a minimal workbook: one sheet "Monthly Prices", shared strings for text
    strings, xml_rows = [], []
    for i, row in enumerate(rows, start=1):
        cells = []
        for j, v in enumerate(row):
            ref = f"{chr(65 + j)}{i}"
            if isinstance(v, str):
                strings.append(v); cells.append(f'<c r="{ref}" t="s"><v>{len(strings) - 1}</v></c>')
            else:
                cells.append(f'<c r="{ref}"><v>{v}</v></c>')
        xml_rows.append(f'<row r="{i}">{"".join(cells)}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    rel = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook {ns} {rel}><sheets><sheet name="Monthly Prices" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="worksheet"/></Relationships>')
        z.writestr("xl/sharedStrings.xml", f"<sst {ns}>" + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>")
        z.writestr("xl/worksheets/sheet1.xml", f"<worksheet {ns}><sheetData>{''.join(xml_rows)}</sheetData></worksheet>")

def _one_row_panel(raw):
    return pd.DataFrame({"CA_EQ": [0.01]}, index=pd.DatetimeIndex(["1973-01-31"], name="month"))

def test_gold_from_xlsx_reads_the_monthly_gold_column(tmp_path):
    from scripts.fetch_deep import gold_from_xlsx
    _xlsx(tmp_path / "c.xlsx", [["World Bank Commodity Price Data (The Pink Sheet)"], ["", "Crude oil", "Gold"],
                                ["", "($/bbl)", "($/troy oz)"], ["1960M01", 1.63, 35.0], ["1960M02", 1.63, 35.1], ["Note", "x", "y"]])
    assert gold_from_xlsx(tmp_path / "c.xlsx") == [("1960-01", 35.0), ("1960-02", 35.1)]

def test_fetch_puts_each_source_in_its_own_dir_with_a_manifest(tmp_path, monkeypatch):
    from scripts import fetch_deep
    def fake_download(url, dest):
        if dest.suffix == ".xlsx":
            _xlsx(dest, [["", "Gold"], ["1960M01", 35.0]]); return dest.read_bytes()
        dest.write_bytes(url.encode()); return url.encode()
    monkeypatch.setattr(fetch_deep, "download", fake_download)
    monkeypatch.setattr(fetch_deep, "_page", lambda url: None)          # no page → the pinned World Bank URL
    monkeypatch.setattr("tools.deep.build_panel", _one_row_panel)
    assert fetch_deep.main(["--dest", str(tmp_path)]) == 0
    assert sorted(p.name for p in (tmp_path / "raw").iterdir()) == sorted(s["id"] for s in fetch_deep.SOURCES)
    man = json.loads((tmp_path / "manifest.json").read_text())
    assert len(man["files"]) == 9 and all(f["licence"] and f["sha256"] == hashlib.sha256(Path(f["path"]).read_bytes()).hexdigest() for f in man["files"])
    assert next(f for f in man["files"] if f["id"] == "worldbank_gold")["url"] == fetch_deep.WB_PINNED
    assert (man["panel"]["rows"], man["panel"]["first"]) == (1, "1973-01")
    assert (tmp_path / "raw/worldbank_gold/gold_monthly.csv").read_text() == "month,gold_usd_oz\n1960-01,35.0\n"

def test_offline_rebuilds_without_the_network(tmp_path, monkeypatch):
    from scripts import fetch_deep
    g = tmp_path / "raw/worldbank_gold"; g.mkdir(parents=True)
    _xlsx(g / "CMO-Historical-Data-Monthly.xlsx", [["", "Gold"], ["1960M01", 35.0]])
    def no_network(*a): raise AssertionError("offline must not download")
    monkeypatch.setattr(fetch_deep, "download", no_network); monkeypatch.setattr("tools.deep.build_panel", _one_row_panel)
    assert fetch_deep.main(["--dest", str(tmp_path), "--offline"]) == 0 and (tmp_path / "panel.csv").exists()

def test_fetch_script_never_executes_what_it_downloads():
    src = Path("scripts/fetch_deep.py").read_text()
    assert not [b for b in ("exec(", "eval(", "subprocess", "os.system", "runpy", "import_module", "pickle", "build_dataset") if b in src]

# Task 13 extras (not in the plan's four): the page link, the HTTP guards, a text cell in the gold column, all-or-nothing runs.
def test_world_bank_url_takes_the_page_link_else_the_pinned_one():
    from scripts.fetch_deep import WB_PINNED, world_bank_url
    new = "https://thedocs.worldbank.org/en/doc/0123abcd-0060012026/related/CMO-Historical-Data-Monthly.xlsx"
    assert world_bank_url(f'<p><a href="{new}">Monthly prices</a></p>') == new
    assert world_bank_url('<a href="/en/doc/x/related/CMO-Historical-Data-Monthly.xlsx">m</a>') == \
        "https://www.worldbank.org/en/doc/x/related/CMO-Historical-Data-Monthly.xlsx"
    assert world_bank_url('<a href="https://example.org/CMO-Historical-Data-Monthly.xlsx">elsewhere</a>') == WB_PINNED
    assert world_bank_url('<a href="http://thedocs.worldbank.org/CMO-Historical-Data-Monthly.xlsx">plain http</a>') == WB_PINNED
    assert world_bank_url("<html>no link</html>") == WB_PINNED and world_bank_url(None) == WB_PINNED

class _Resp:                                                      # the least urlopen returns that download() uses
    def __init__(self, body, url="https://example.org/x", length=None):
        self.body, self.url, self.headers = body, url, ({} if length is None else {"Content-Length": str(length)})
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def geturl(self): return self.url
    def read(self, n=-1): return self.body if n < 0 else self.body[:n]

def test_download_writes_the_file_with_an_honest_user_agent_and_refuses_what_it_should_not(tmp_path, monkeypatch):
    from scripts import fetch_deep
    seen = []
    def fake_urlopen(request, timeout=None): seen.append(request); return _Resp(b"abc")
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert fetch_deep.download("https://example.org/x", tmp_path / "x") == b"abc" and (tmp_path / "x").read_bytes() == b"abc"
    assert seen[0].get_header("User-agent") == "EPICENTRE-datathon/1.0"
    with pytest.raises(ValueError, match="https"):                # no request at all for a plain-http address
        fetch_deep.download("http://example.org/x", tmp_path / "y")
    assert len(seen) == 1 and not (tmp_path / "y").exists()
    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=None: _Resp(b"abc", "http://example.org/x"))
    with pytest.raises(ValueError, match="unencrypted"):          # a redirect that drops to http
        fetch_deep.download("https://example.org/x", tmp_path / "z")
    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=None: _Resp(b"a" * (fetch_deep.MAX_BYTES + 5)))
    with pytest.raises(ValueError, match="larger"):
        fetch_deep.download("https://example.org/x", tmp_path / "z")
    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=None: _Resp(b"abc", length=10))
    with pytest.raises(ValueError, match="cut short"):            # fewer bytes than the server announced (read(n) alone never says)
        fetch_deep.download("https://example.org/x", tmp_path / "z")
    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=None: _Resp(b"abc", length=3))
    assert fetch_deep.download("https://example.org/x", tmp_path / "w") == b"abc"
    assert not (tmp_path / "z").exists()

def test_gold_from_xlsx_skips_a_text_cell_in_the_gold_column_never_a_zero(tmp_path):
    from scripts.fetch_deep import gold_from_xlsx
    _xlsx(tmp_path / "c.xlsx", [["", "Gold"], ["1960M01", 35.0], ["1960M02", ".."], ["1960M03", 35.2], ["1960Q1", 99.0]])
    assert gold_from_xlsx(tmp_path / "c.xlsx") == [("1960-01", 35.0), ("1960-03", 35.2)]     # February stays a hole

def _tree(root):                                                  # every file under root: relative name -> bytes
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}

def _fake_net(monkeypatch, run):          # the nine downloads, their bytes depending on run[0]; no page; build_panel gives one row
    from scripts import fetch_deep
    def fake_download(url, dest):
        if dest.suffix == ".xlsx": _xlsx(dest, [["", "Gold"], ["1960M01", 34.0 + run[0]]]); return dest.read_bytes()
        body = url.encode() + f" run {run[0]}".encode(); dest.write_bytes(body); return body
    monkeypatch.setattr(fetch_deep, "download", fake_download); monkeypatch.setattr(fetch_deep, "_page", lambda url: None)
    monkeypatch.setattr("tools.deep.build_panel", _one_row_panel)
    return fake_download

def test_a_second_run_replaces_the_raw_files_and_the_manifest(tmp_path, monkeypatch):
    from scripts import fetch_deep
    run = [1]; _fake_net(monkeypatch, run)
    assert fetch_deep.main(["--dest", str(tmp_path)]) == 0
    first = json.loads((tmp_path / "manifest.json").read_text())
    run[0] = 2
    assert fetch_deep.main(["--dest", str(tmp_path)]) == 0
    second = json.loads((tmp_path / "manifest.json").read_text())
    assert (tmp_path / "raw/french_12/12_Industry_Portfolios_CSV.zip").read_bytes().endswith(b" run 2")
    assert (tmp_path / "raw/worldbank_gold/gold_monthly.csv").read_text() == "month,gold_usd_oz\n1960-01,36.0\n"
    assert all(a["sha256"] != b["sha256"] for a, b in zip(first["files"], second["files"]))
    assert all(f["sha256"] == hashlib.sha256(Path(f["path"]).read_bytes()).hexdigest() for f in second["files"])
    assert sorted(p.name for p in tmp_path.iterdir()) == ["manifest.json", "panel.csv", "raw"]

def test_offline_keeps_the_files_and_the_retrieval_time_of_the_last_download(tmp_path, monkeypatch):
    from scripts import fetch_deep
    _fake_net(monkeypatch, [1])
    assert fetch_deep.main(["--dest", str(tmp_path)]) == 0
    before = json.loads((tmp_path / "manifest.json").read_text())
    def no_network(*a): raise AssertionError("offline must not touch the network")
    monkeypatch.setattr(fetch_deep, "download", no_network); monkeypatch.setattr(fetch_deep, "_page", no_network)
    assert fetch_deep.main(["--dest", str(tmp_path), "--offline"]) == 0
    after = json.loads((tmp_path / "manifest.json").read_text())
    assert len(after["files"]) == 9 and (after["files"], after["retrieved_at"]) == (before["files"], before["retrieved_at"])
    assert after["panel"]["rows"] == 1 and after["retrieved_at"].endswith("Z")

@pytest.mark.parametrize("fault", ["download", "panel"])
def test_a_failed_run_leaves_the_previous_files_manifest_and_panel_untouched(tmp_path, monkeypatch, fault, capsys):
    from scripts import fetch_deep
    run = [1]                                                     # the bytes differ per run, so "untouched" means untouched
    fake_download = _fake_net(monkeypatch, run)
    assert fetch_deep.main(["--dest", str(tmp_path)]) == 0
    before = _tree(tmp_path)
    run[0] = 2
    def broken(url, dest):                                        # seven sources arrive, then the eighth fails
        if "id=EXCAUS" in url: raise OSError("the server stopped answering")
        return fake_download(url, dest)
    def bad_panel(raw): raise ValueError("no data at all for ['GOLD']")
    if fault == "download": monkeypatch.setattr(fetch_deep, "download", broken)
    else: monkeypatch.setattr("tools.deep.build_panel", bad_panel)
    assert fetch_deep.main(["--dest", str(tmp_path)]) == 1
    assert _tree(tmp_path) == before and sorted(p.name for p in tmp_path.iterdir()) == ["manifest.json", "panel.csv", "raw"]
    out = capsys.readouterr().out
    assert "Could not" in out and "Traceback" not in out

def test_the_sources_and_the_default_cache_match_what_tools_deep_reads():
    import inspect
    from scripts.fetch_deep import DEFAULT_DEST, GOLD_CSV, SOURCES
    from tools.deep import DEEP_DIR, MANIFEST_PATH, PANEL_PATH, build_panel
    assert (DEFAULT_DEST, DEFAULT_DEST / "panel.csv", DEFAULT_DEST / "manifest.json") == (DEEP_DIR, PANEL_PATH, MANIFEST_PATH)
    code = inspect.getsource(build_panel)
    wanted = [f'{s["id"]}/{s["file"]}' for s in SOURCES if s["id"] != "worldbank_gold"] + [f"worldbank_gold/{GOLD_CSV}"]
    assert [w for w in wanted if w not in code] == [] and len(SOURCES) == 9 and all(s["licence"] and s["url"].startswith("https://") for s in SOURCES)

def test_panel_csv_reads_back_through_the_loader_with_its_holes(tmp_path, monkeypatch):
    from scripts import fetch_deep
    from tools.deep import load_panel
    idx = pd.DatetimeIndex(["1973-01-31", "1973-02-28", "1973-03-31"], name="month")
    panel = pd.DataFrame({"CA_EQ": [0.012345678901234567, None, -0.5], "USDCAD_END": [1.0, 1.0045, 0.9987]}, index=idx)
    _fake_net(monkeypatch, [1]); monkeypatch.setattr("tools.deep.build_panel", lambda raw: panel)
    assert fetch_deep.main(["--dest", str(tmp_path)]) == 0
    assert (tmp_path / "panel.csv").read_text().splitlines()[:2] == ["month,CA_EQ,USDCAD_END", "1973-01,0.012345678901234567,1.0"]
    pd.testing.assert_frame_equal(load_panel(path=tmp_path / "panel.csv"), panel, check_freq=False)      # the hole stays a hole
    man = json.loads((tmp_path / "manifest.json").read_text())["panel"]
    assert (man["rows"], man["first"], man["last"]) == (3, "1973-01", "1973-03")

# --- Task 13 fix round 1: the swap into place is all-or-nothing; --offline records licences and re-hashes; plain errors --------
import zlib

def _failing_moves(monkeypatch, first, last):     # moves number `first`..`last` (1-based) raise OSError; every other move really moves
    from scripts import fetch_deep
    real, calls = fetch_deep._move, []
    def flaky(src, dst):
        calls.append((src, dst))
        if first <= len(calls) <= last: raise OSError("the disk stopped answering")
        real(src, dst)
    monkeypatch.setattr(fetch_deep, "_move", flaky)
    return calls

@pytest.mark.parametrize("fresh, nth", [(True, 5), (False, 5), (False, 22)])      # 22 = the very last move of a second run (the manifest)
def test_a_failure_while_moving_the_new_files_in_puts_every_old_one_back(tmp_path, monkeypatch, capsys, fresh, nth):
    from scripts import fetch_deep
    run = [1]; _fake_net(monkeypatch, run)
    if not fresh:
        assert fetch_deep.main(["--dest", str(tmp_path)]) == 0
        run[0] = 2
    before = _tree(tmp_path)
    calls = _failing_moves(monkeypatch, nth, nth)
    assert fetch_deep.main(["--dest", str(tmp_path)]) == 1
    assert len(calls) > nth                                            # the fault was reached, and the moves made before it were undone
    assert _tree(tmp_path) == before                                   # raw/, panel.csv and manifest.json byte for byte as they were
    assert sorted(p.name for p in tmp_path.iterdir()) == ([] if fresh else ["manifest.json", "panel.csv", "raw"])
    out = capsys.readouterr().out
    assert out.splitlines()[-1] == "Could not build the deep-history panel: the disk stopped answering." and "Traceback" not in out

def test_when_the_undo_fails_too_the_previous_files_are_kept_and_named(tmp_path, monkeypatch, capsys):
    from scripts import fetch_deep
    run = [1]; _fake_net(monkeypatch, run)
    assert fetch_deep.main(["--dest", str(tmp_path)]) == 0
    before = _tree(tmp_path); run[0] = 2
    _failing_moves(monkeypatch, 5, 10**6)                              # the fifth move fails, and so does every undo after it
    assert fetch_deep.main(["--dest", str(tmp_path)]) == 1
    kept = [p for p in tmp_path.iterdir() if p.name.startswith(".incoming-")]
    assert len(kept) == 1 and any((kept[0] / "old").iterdir())         # the staging directory stays, with the old files in old/
    assert str(kept[0] / "old") in capsys.readouterr().out
    on_disk = list(_tree(tmp_path).values())
    assert all(body in on_disk for body in before.values())            # nothing of the previous run was lost

def _no_network(monkeypatch):
    from scripts import fetch_deep
    def refuse(*a): raise AssertionError("offline must not touch the network")
    monkeypatch.setattr(fetch_deep, "download", refuse); monkeypatch.setattr(fetch_deep, "_page", refuse)

def test_offline_with_no_manifest_records_each_file_found_with_its_licence_and_a_fresh_hash(tmp_path, monkeypatch):
    from scripts import fetch_deep
    found = ["french_factors", "statcan_10100122", "fred_EXCAUS"]                  # SOURCES order; the other six are not on disk
    for s in fetch_deep.SOURCES:
        if s["id"] in found:
            (tmp_path / "raw" / s["id"]).mkdir(parents=True); (tmp_path / "raw" / s["id"] / s["file"]).write_bytes(b"by hand " + s["id"].encode())
    monkeypatch.setattr("tools.deep.build_panel", _one_row_panel); _no_network(monkeypatch)
    assert fetch_deep.main(["--dest", str(tmp_path), "--offline"]) == 0
    man = json.loads((tmp_path / "manifest.json").read_text())
    by_id = {s["id"]: s for s in fetch_deep.SOURCES}
    assert [f["id"] for f in man["files"]] == found
    assert all((f["url"], f["licence"]) == (by_id[f["id"]]["url"], by_id[f["id"]]["licence"]) and f["licence"] for f in man["files"])
    assert all(f["sha256"] == hashlib.sha256(Path(f["path"]).read_bytes()).hexdigest() and f["bytes"] == len(Path(f["path"]).read_bytes())
               for f in man["files"])
    assert man["retrieved_at"] == "not recorded" and man["panel"]["rows"] == 1      # a missing date is that phrase, never null or "None"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["manifest.json", "panel.csv", "raw"]

def test_offline_rehashes_the_files_and_keeps_the_urls_and_the_date_of_the_last_download(tmp_path, monkeypatch):
    from scripts import fetch_deep
    _fake_net(monkeypatch, [1])
    assert fetch_deep.main(["--dest", str(tmp_path)]) == 0
    first = json.loads((tmp_path / "manifest.json").read_text())
    first["files"][0]["url"] = "https://example.org/the-address-used.zip"        # what the manifest holds and SOURCES does not
    (tmp_path / "manifest.json").write_text(json.dumps(first))
    (tmp_path / "raw/french_12/12_Industry_Portfolios_CSV.zip").write_bytes(b"replaced by hand")
    _no_network(monkeypatch)
    assert fetch_deep.main(["--dest", str(tmp_path), "--offline"]) == 0
    after = json.loads((tmp_path / "manifest.json").read_text())
    rows, was = {f["id"]: f for f in after["files"]}, {f["id"]: f for f in first["files"]}
    assert rows["french_factors"]["url"] == "https://example.org/the-address-used.zip" and len(rows) == 9
    assert rows["french_12"]["sha256"] == hashlib.sha256(b"replaced by hand").hexdigest() != was["french_12"]["sha256"]
    assert rows["french_12"]["bytes"] == len(b"replaced by hand") and after["retrieved_at"] == first["retrieved_at"]

@pytest.mark.parametrize("error", [TypeError, IndexError, zlib.error, NotImplementedError, RuntimeError])
def test_odd_failures_on_a_corrupt_download_end_in_one_plain_sentence(tmp_path, monkeypatch, capsys, error):
    from scripts import fetch_deep
    _fake_net(monkeypatch, [1])
    def corrupt(raw): raise error("a part of the file cannot be read")
    monkeypatch.setattr("tools.deep.build_panel", corrupt)
    assert fetch_deep.main(["--dest", str(tmp_path)]) == 1                           # returns 1; a raised error would fail this test
    assert capsys.readouterr().out.splitlines()[-1] == "Could not build the deep-history panel: a part of the file cannot be read."
    assert list(tmp_path.iterdir()) == []                                            # no staging directory left behind
