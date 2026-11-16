"""Finance truth for the storm catalog (workstream C). Section 1: data/events.csv (plan C Task 2).

data/events.csv is read by A's tools.events.load_events, B's navigator (catalog prefix) and D's map, so its
columns are spec section 9 plus the `place` epicentre label of the interface ledger section 10 (last column).
Plan C Task 8 appends the method tests to this file. The first four tests read only the CSV; the two that need
the union trading calendar read the starter prices and skip without them.
"""
import re
from pathlib import Path

import pandas as pd
import pytest

NEEDS_DATA = pytest.mark.skipif(not Path("data/starter/prices_daily.csv").exists(), reason="starter data not present")

COLUMNS = ["event_id", "date", "announced", "announced_at", "title_en", "description_en", "title_fr",
           "description_fr", "category", "family", "sign", "episode", "regions", "lat", "lon", "source_url",
           "verified_on", "place"]

CAT = pd.read_csv("data/events.csv", dtype=str, keep_default_na=False)
FAMILY_OF = {"tarifs": "tariffs", "guerre": "war_oil", "energie": "war_oil", "puces": "chips", "taux": "rates"}
POSITIVE = {"tariff_pause_2025", "scotus_ieepa_2026", "ceasefire_2026", "peace_deal_2026"}
ADVICE_WORDS = re.compile(r"\b(buy|sell|hold|should)\b", re.I)
# The 24 ISO3 codes the catalog uses (country of the epicentre or of a party): a typo or a bloc such as EUR must fail.
REGION_CODES = {"CAN", "CHN", "DEU", "DNK", "FIN", "FRA", "GBR", "GRL", "IRN", "IRQ", "ISR", "JPN", "MEX", "NLD", "NOR",
                "PAK", "PSE", "RUS", "SAU", "SWE", "TWN", "UKR", "USA", "YEM"}
TEXT_COLUMNS = ["title_en", "description_en", "title_fr", "description_fr", "place"]   # the columns the UI shows as words


def test_catalog_columns_and_rows():
    assert list(CAT.columns) == COLUMNS and len(CAT) == 37 and CAT.event_id.is_unique
    assert CAT.family.value_counts().to_dict() == {"tariffs": 13, "war_oil": 12, "chips": 7, "rates": 5}
    assert set(CAT.loc[CAT.sign == "positive", "event_id"]) == POSITIVE and set(CAT.sign) == {"negative", "positive"}
    assert list(CAT.sort_values(["date", "event_id"]).event_id) == list(CAT.event_id)


def test_catalog_rows_are_sourced_dated_and_in_range():
    for r in CAT.itertuples():
        assert r.source_url.startswith("https://") and r.title_en and r.description_en, r.event_id
        assert r.verified_on <= "2026-11-14" and r.announced <= r.date <= "2026-11-12", r.event_id
        assert pd.Timestamp(r.date).weekday() < 5, r.event_id
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", r.announced_at) and r.announced_at[:10] == r.announced
        assert set(r.regions.split(";")) <= REGION_CODES, (r.event_id, r.regions)
        assert -90 <= float(r.lat) <= 90 and -180 <= float(r.lon) <= 180
        assert {FAMILY_OF[c] for c in r.category.split(";")} == {r.family}, r.event_id
    # epicentre = the central bank that decided; svb_2023 is the one named exception: the shock began at the bank
    decisions = CAT[(CAT.family == "rates") & (CAT.event_id != "svb_2023")]
    assert set(zip(decisions.lat, decisions.lon)) <= {("38.89", "-77.05"), ("45.42", "-75.70")}
    svb = CAT[CAT.event_id == "svb_2023"].iloc[0]
    assert (svb.lat, svb.lon, svb.place) == ("37.35", "-121.97", "Santa Clara, California, United States")


def test_catalog_place_label_is_the_last_column_and_names_each_epicentre_once():
    assert list(CAT.columns)[-1] == "place"
    assert (CAT.place != "").all() and (CAT.place.str.strip() == CAT.place).all()
    labels = CAT.groupby(["lat", "lon"]).place.nunique()
    assert (labels == 1).all(), labels[labels > 1].to_dict()   # one label per epicentre point on the map


def test_no_advice_words_in_the_catalog_text():
    """Red gate: the UI shows these texts, and nothing the app shows says buy / sell / hold / should."""
    hits = [(r.event_id, col, m.group(0)) for r in CAT.itertuples() for col in TEXT_COLUMNS
            for m in ADVICE_WORDS.finditer(getattr(r, col))]
    assert not hits, hits


@NEEDS_DATA
def test_dates_follow_the_dating_rule_on_the_union_calendar():
    data = pytest.importorskip("tools.data")
    cal = list(data.load_market("2026-11-12")["calendar"].strftime("%Y-%m-%d"))
    for r in CAT.itertuples():
        day, hhmm = r.announced_at.split("T")
        first = next(d for d in cal if d > day or (d == day and hhmm < "16:00"))
        assert r.date == first, (r.event_id, r.date, first)


@NEEDS_DATA
def test_episode_column_is_the_campaign_rule():
    data = pytest.importorskip("tools.data")
    cal = list(data.load_market("2026-11-12")["calendar"].strftime("%Y-%m-%d"))
    for (fam, sign), g in CAT.groupby(["family", "sign"]):
        end, current = None, None
        for r in g.sort_values("date").itertuples():
            i = cal.index(r.date)
            start = cal[i - 1]
            if end is None or start > end:
                current = r.event_id
            end = max(end or "", cal[min(i + 20, len(cal) - 1)])
            assert r.episode == current, (r.event_id, r.episode, current)
