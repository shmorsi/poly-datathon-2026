"""Task 1 (plan D): the receipt. Every number of the debrief must trace to a facts row the sentence cites,
with that row's entity named and its kind allowed; named defects are one plain sentence each (spec 10, 7 VERIFY).
Offline and pure: no market data, no AWS."""
import datetime
import functools

import pytest

from verify import verify_numbers, VERDICT_WORDS, NAME_TOKENS

F = {"T3": dict(label="Your floor", value=-0.15, unit="pct", entity="your floor", sign="negative", kind="assumption"),
     "T6": dict(label="The move: NVDA set to", value=0.40, unit="pct", entity="NVDA", sign="none", kind="fiction"),
     "T9": dict(label="Worst drop today", value=-0.106, unit="pct", entity="today", sign="negative", kind="fact"),
     "T10": dict(label="Worst drop after the move", value=-0.345, unit="pct", entity="after", sign="negative", kind="fact"),
     "T11": dict(label="Dollar loss at the worst drop after the move", value=-207000.4, unit="CAD", entity="after", sign="negative", kind="fact"),
     "T16": dict(label="Worst clean tariff episode after the move", value=-0.0905, unit="pct", entity="tariffs", sign="negative", kind="fact"),
     "T19": dict(label="Largest NVDA size inside your limits", value=0.08, unit="pct", entity="NVDA", sign="none", kind="fact"),
     "T20": dict(label="Clean tariff episodes known", value=4, unit="count", entity="tariffs", sign="none", kind="fact")}
R = {"as_of": "2026-11-12", "verdict": "Incompatible", "events": [],
     "checks": [{"rule": "max_drawdown", "tier": "hard", "status": "fail", "value": -0.345, "limit": -0.15, "holding": None, "reason": ""}]}
VS = "Outside your limits: with 40 % [T6] in NVIDIA, the move fell 34.5 % [T10], past your floor of 15 % [T3]."
ROWS = [("data", "fact", "Your portfolio today fell at most 10.6 % [T9]."),
        ("why", "assumption", "Your floor is 15 % [T3], what you could absorb; the move lost $207,000 [T11]."),
        ("limits", "limit", "This already happened, it is not a forecast: four tariff shocks [T20], the worst 9.1 % [T16]."),
        ("would_change", "scenario", "In this history your floor breaks above 8 % [T19] NVIDIA.")]


def deb(rows=ROWS, vs=VS):
    sec = {}
    for i, (s, _, _) in enumerate(rows):
        sec.setdefault(s, []).append(i)
    return {"verdict_sentence": vs, "sections": sec, "sentences": [{"text": t, "kind": k, "refs": []} for _, k, t in rows]}


def swap(i, text, kind=None):
    rows = list(ROWS); s, k, _ = rows[i]; rows[i] = (s, kind or k, text); return deb(rows)


def test_clean_debrief_is_fully_traced():
    r = verify_numbers(deb(), F, as_of="2026-11-12", result=R)
    assert (r["verified"], r["total"], r["defects"]) == (9, 9, [])


def test_right_number_wrong_ref_is_named():
    r = verify_numbers(swap(0, "Your portfolio today fell at most 34.5 % [T9]."), F, as_of="2026-11-12", result=R)
    assert r["unverified"][0]["sentence"] == 2
    assert r["defects"] == ["Sentence 2 says 34.5 % and cites T9, whose value is 10.6 %. Use T9's value or remove the number."]


def test_number_without_ref_and_unknown_ref():
    assert "cites no [T#]" in verify_numbers(swap(0, "Today it fell at most 10.6 %."), F, result=R)["defects"][0]
    assert "T99, which is not in the facts" in verify_numbers(swap(0, "Today 10.6 % [T99]."), F, result=R)["defects"][0]


def test_chart_value_never_verifies():
    R2 = {**R, "trace": [{"id": "T9", "outputs": {"values": [12.3]}}]}
    assert verify_numbers(swap(0, "Today it fell 12.3 % [T9]."), F, result=R2)["unverified"]


def test_entity_and_kind():
    r = verify_numbers(swap(2, "Four shocks [T20] are known."), F, result=R)
    assert r["wrong_entity"] and "does not name tariffs" in r["defects"][0]
    r = verify_numbers(swap(0, "Your floor is 15 % [T3].", kind="fact"), F, result=R)
    assert r["defects"] == ["Sentence 2 is marked fact but cites T3, which is an assumption. Change the sentence's kind or its citation."]


def test_round_half_up_and_dollars():
    assert verify_numbers(swap(2, "Tariff shocks: the worst 9.0 % [T16]."), F, result=R)["unverified"]   # 9.05 -> 9.1
    assert not verify_numbers(swap(1, "Floor 15.0 % [T3]; the move lost $207,000 [T11]."), F, result=R)["unverified"]
    assert verify_numbers(swap(1, "The move lost $207,001 [T11]."), F, result=R)["unverified"]


def test_dates_years_tags_and_descriptors_are_not_numbers():
    # ledger 16 (2) supersedes the plan's "over 20-day windows": a hyphenated quantity is a number (tested below)
    r = verify_numbers(swap(0, "Today, from 2021-11-29 to Oct 2022 and in 2022, it fell 10.6 % [T9]."), F, result=R)
    assert r["total"] == 9 and not r["defects"]


def test_odd_formats_are_counted_never_skipped():
    r = verify_numbers(swap(0, "Today: $1.2M, 34,5 %, −10.6% [T9], 9.0pp."), F, result=R)
    assert r["total"] == 8 + 5 and len(r["matches"]) + len(r["unverified"]) == r["total"]


def test_future_dates_and_unknown_events():
    cat = [{"event_id": "liberation_day_2025", "title": "Liberation Day tariffs", "date": "2025-04-03"}]
    r = verify_numbers(swap(0, "Today it fell 10.6 % [T9] in April 2025, after Liberation Day tariffs."), F, as_of="2025-01-31", result=R, catalog=cat)
    assert len(r["future_refs"]) == 2 and "Sentence 2 refers to something dated after 2025-01-31. Remove it." in r["defects"]
    assert "April" not in " ".join(r["defects"])


def test_verdict_rules_caveats_sections():
    r = verify_numbers(deb(vs=VS.replace("Outside your limits", "Inside your limits")), F, result=R)
    assert "The verdict must read “Outside your limits”. Use exactly these words." in r["defects"]
    R2 = {**R, "checks": R["checks"] + [{"rule": "single_stock", "status": "fail"}, {"rule": "scenario_stress", "status": "warn", "value": None}]}
    d = verify_numbers(deb(ROWS[:3]), F, result=R2)["defects"]
    assert "The debrief does not name the failed limit “One company”. Name it." in d
    assert "The debrief must say “no close precedent at this date”." in d          # governance's own words (B Task 5)
    assert "The section “What would change the answer?” is missing. Write one sentence for it." in d


def test_verdict_words_match_config():
    config = pytest.importorskip("config")
    assert VERDICT_WORDS == config.VERDICT_WORDS


def test_bare_list_and_string_sections_are_accepted():
    bare = verify_numbers([{"text": "Today it fell 10.6 % [T9].", "kind": "fact", "refs": []}], F, result=R)
    assert bare["verified"] == 1 and "The verdict must read “Outside your limits”. Use exactly these words." in bare["defects"]
    assert sum("is missing" in d for d in bare["defects"]) == 4
    text = {"verdict_sentence": VS, "sentences": [], "sections": {
        "data": "Your portfolio today fell at most 10.6 % [T9].", "why": "Your floor is 15 % [T3] and the move lost $207,000 [T11].",
        "limits": "This already happened: four tariff shocks [T20].", "would_change": "Your floor breaks above 8 % [T19] NVIDIA."}}
    assert verify_numbers(text, F, result=R)["defects"] == []


def test_two_cited_rows_and_a_range_hyphen():
    r = verify_numbers(swap(1, "Your floor is 30 % [T3] and the move lost $207,000 [T11]."), F, result=R)
    assert r["defects"] == ["Sentence 3 says 30 %, but none of T3, T11 holds that value. Use a cited value or remove the number."]
    r = verify_numbers(swap(0, "Today it fell 9-12 % [T9]."), F, result=R)    # the hyphen is a range, not a minus
    assert [u["number"] for u in r["unverified"]] == ["9", "12 %"]


def test_name_tokens_are_masked_but_other_numbers_still_need_a_ref():     # ledger 13
    assert len(NAME_TOKENS) == 14
    for name in NAME_TOKENS:                                             # (a) a name alone is not a number
        r = verify_numbers(swap(0, f"Today it moved less than the {name} did."), F, result=R)
        assert (r["total"], r["unverified"], r["defects"]) == (8, [], []), name
    r = verify_numbers(swap(0, "Today it moved less than the S&P 500, the G7 and Q3 did, and COVID-19 hurt."), F, result=R)
    assert r["total"] == 8 and not r["defects"]
    r = verify_numbers(swap(0, "Today the S&P 500 fell 25 %."), F, result=R)    # (b) the other number is still checked
    assert [u["number"] for u in r["unverified"]] == ["25 %"] and "cites no [T#]" in r["defects"][0]


def test_name_tokens_match_whole_tokens_only():                          # (c) partial words, other case: not names
    r = verify_numbers(swap(0, "Today Q3x and G70 and XQ3 and S&P 5000 look odd."), F, result=R)
    assert [u["number"] for u in r["unverified"]] == ["3", "70", "3", "5000"]
    assert [u["number"] for u in verify_numbers(swap(0, "Today the s&p 500 fell."), F, result=R)["unverified"]] == ["500"]


# ---- fix round 1 (ledger 16): the receipt parser gaps -------------------------------------------------------------
MINUS_GLYPHS = "−-‐‑‒–—﹣－"   # U+2212 - U+2010 U+2011 U+2012 U+2013 U+2014 U+FE63 U+FF0D
F2 = {**F, "T24": dict(label="Gain today", value=0.0067, unit="pct", entity="today", sign="positive", kind="fact"),
      "T25": dict(label="Fall today", value=-0.0067, unit="pct", entity="today", sign="negative", kind="fact")}


def read(text, facts=F, **kw):
    """The receipt's reading of one sentence (sentence 2 of the plan debrief): (numbers as written, whole result)."""
    r = verify_numbers(swap(0, text), facts, result=R, **kw)
    return [x["number"] for x in r["unverified"] + r["matches"] if x["sentence"] == 2], r


def test_a_number_after_a_year_is_its_own_number():                           # (1)
    for text, nums in [("Today in 2022 -15 % it fell.", ["-15 %"]), ("Today in 2022 – 15 % it fell.", ["15 %"]),
                       ("Today in 2022 -25 pp it fell.", ["-25 pp"]), ("Today in 2022 -10.6 % it fell.", ["-10.6 %"]),
                       ("Today in 2022-15 % it fell.", ["-15 %"]), ("Today in 2022 –15 days it fell.", ["–15 days"]),
                       ("Today in 2022 - 15 % it fell.", ["15 %"])]:
        assert read(text)[0] == nums, text
    r = verify_numbers(swap(0, "After the move, in 2022 -34.5 % [T10] it fell."), F, as_of="2026-11-12", result=R)
    assert (r["verified"], r["total"], r["future_refs"], r["defects"]) == (9, 9, [], [])


def test_year_ranges_and_months_are_still_masked():
    for text in ("Today over 2021–2026 it fell.", "Today over 2022–23 it fell.", "Today in 2022-12 it fell.",
                 "Today over 2022-2023 it fell."):
        assert read(text)[0] == [], text


def test_every_minus_form_is_a_minus():                                       # (4)
    for g in MINUS_GLYPHS:
        nums, r = read(f"Today it fell {g}0.67 % [T24].", F2)
        assert nums == [f"{g}0.67 %"] and r["unverified"][-1]["number"] == f"{g}0.67 %", repr(g)
        assert "whose value is 0.7 %" in r["defects"][0], repr(g)
        r = read(f"Today it fell {g}0.67 % [T25].", F2)[1]
        assert (r["verified"], r["total"], r["defects"]) == (9, 9, []), repr(g)


def test_a_dash_between_numbers_or_after_a_word_is_not_a_sign():
    for sep in "-–—−":
        assert read(f"Today the range was 7{sep}8 % it fell.")[0] == ["7", "8 %"], sep
    for sep in "–—":
        r = verify_numbers(swap(0, f"Today it fell{sep}10.6 %{sep}a lot [T9]."), F, result=R)
        assert (r["verified"], r["total"], r["defects"]) == (9, 9, [])


F3 = {**F, "T23": dict(label="Days to recover today", value=487, unit="days", entity="today", sign="none", kind="fact"),
      "T26": dict(label="Months back to the peak today", value=12, unit="months", entity="today", sign="none", kind="fact"),
      "T27": dict(label="Years of history today", value=5, unit="years", entity="today", sign="none", kind="fact")}


def test_hyphenated_quantities_are_counted_and_verified():                    # (2)
    for text, num, ok in [("Today a 487-day recovery [T23] followed.", "487-day", True),
                          ("Today a 400-day recovery [T23] followed.", "400-day", False),
                          ("Today a 400-trading-day recovery [T23] followed.", "400-trading-day", False),
                          ("Today a 487-trading-day recovery [T23] followed.", "487-trading-day", True),
                          ("Today a 12-month rebound [T26] followed.", "12-month", True),
                          ("Today a 13-month rebound [T26] followed.", "13-month", False),
                          ("Today a 5-year window [T27] was used.", "5-year", True),
                          ("Today a 6-year window [T27] was used.", "6-year", False),
                          ("Today a 487-day recovery [T26] followed.", "487-day", False),   # a months row never holds days
                          ("Today a 20-day window it fell.", "20-day", False)]:
        nums, r = read(text, F3)
        assert nums == [num], text
        assert (r["verified"], r["total"]) == ((9, 9) if ok else (8, 9)), text
    assert "Sentence 2 says 20-day but cites no [T#]." in read("Today a 20-day window it fell.", F3)[1]["defects"][0]


def test_percent_words_map_to_percent_and_points():                           # (3)
    for w in ("percent", "per cent", "pct", "percentage points", "percentage point", "Percent", "PCT"):
        nums, r = read(f"Today it fell 10.6 {w} [T9].")
        assert nums == [f"10.6 {w}"] and (r["verified"], r["total"], r["defects"]) == (9, 9, []), w
    nums, r = read("Today it fell 10.6 percent [T3].")                   # the unit is still checked against the row
    assert r["defects"] == ["Sentence 2 says 10.6 percent and cites T3, whose value is 15.0 %. Use T3's value or remove the number."]
    assert read("Today it fell 487 percent [T23].", F3)[1]["unverified"]  # percent never matches a days row


SPELLED = ("ten percent", "twenty-five percent", "twelve shocks", "thirty-seven shocks", "a hundred years", "half", "a third",
           "two thirds", "three quarters", "½", "¾", "twenty", "ninety-day", "zero", "a dozen shocks", "Twelve shocks", "HALF",
           "one hundred and five days", "ten per cent", "five percentage points")


def test_spelled_out_quantities_and_fractions_are_a_named_defect():          # (3)
    for words in SPELLED:
        r = verify_numbers(swap(0, f"Today it fell 10.6 % [T9], and {words} followed."), F, result=R)
        assert [u["number"] for u in r["unverified"]] == [words], words
        assert (r["verified"], r["total"]) == (9, 10), words
        assert r["defects"] == [f"Sentence 2 spells out a number (“{words}”): write the number in digits and "
                                "cite the row that holds it, or remove it."], words


def test_plain_words_that_are_not_quantities_are_left_alone():
    for text in ("Today one company fell 10.6 % [T9].", "Today no one fell 10.6 % [T9].", "One company fell 10.6 % [T9] today.",
                 "Today a third party fell 10.6 % [T9].", "Today the third shock fell 10.6 % [T9].",
                 "Today the shock check, half your floor, fell 10.6 % [T9].", "Today one of the biggest fell 10.6 % [T9].",
                 "Today at one point the book fell 10.6 % [T9].",
                 "Today in the second half of 2022 it fell 10.6 % [T9].", "Today in the First Half of 2023 it fell 10.6 % [T9]."):
        r = verify_numbers(swap(0, text), F, result=R)
        assert (r["verified"], r["total"], r["defects"]) == (9, 9, []), text


def test_ratios_and_counting_words_are_a_named_defect():                       # (3) never silently skipped
    for words in ("one in four", "three out of ten", "twice", "a decade", "a pair", "a couple", "fifty fifty"):
        r = verify_numbers(swap(0, f"Today it fell 10.6 % [T9], and {words} followed."), F, result=R)
        assert [u["number"] for u in r["unverified"]] == [words], words
        assert r["defects"] == [f"Sentence 2 spells out a number (“{words}”): write the number in digits and "
                                "cite the row that holds it, or remove it."], words


def test_a_dash_after_a_unit_is_a_range_not_a_sign():
    for sep in "-–—":
        assert read(f"Today the range was 9 %{sep}12 % it fell.")[0] == ["9 %", "12 %"], sep
        assert read(f"Today the range was 5 pp{sep}8 pp it fell.")[0] == ["5 pp", "8 pp"], sep


def test_an_explicit_plus_must_match_the_rows_sign():                          # minors
    for g in "+＋﹢":
        nums, r = read(f"Today it gained {g}10.6 % [T9].")                     # T9 is -10.6 %: the plus contradicts it
        assert nums == [f"{g}10.6 %"] and r["unverified"], g
        assert f"Sentence 2 says {g}10.6 % and cites T9, whose value is 10.6 %." in r["defects"][0], g
        r = read(f"Today it gained {g}0.67 % [T24].", F2)[1]
        assert (r["verified"], r["total"], r["defects"]) == (9, 9, []), g
        assert read(f"Today it gained {g}0.67 % [T25].", F2)[1]["unverified"], g
    assert read("Today it fell 10.6 % [T9].")[1]["defects"] == []             # no sign written: the abs value is fine
    assert read("Today it gained 10.6 % [T9].")[1]["defects"] == [ROSE_FELL]  # Task 1b: but "gained" on a falling row is not
    assert read("Today it was A+5 % [T9].")[0] == ["5 %"]                    # a plus after a letter or digit is no sign


F4 = {**F, "T30": dict(label="Amount replayed today", value=214000.4, unit="CAD", entity="today", sign="none", kind="fact"),
      "T31": dict(label="Account today", value=1200000, unit="CAD", entity="today", sign="none", kind="fact"),
      "T32": dict(label="Loss today", value=-214000, unit="CAD", entity="today", sign="negative", kind="fact")}


def test_k_and_m_after_a_dollar_amount_multiply_it():                          # minors
    for text, ok in [("Today $214k [T30] was replayed.", True), ("Today $214K [T30] was replayed.", True),
                     ("Today $214 thousand [T30] was replayed.", True), ("Today $215k [T30] was replayed.", False),
                     ("Today $214 [T30] was replayed.", False), ("Today $1.2M [T31] was replayed.", True),
                     ("Today $1.2 million [T31] was replayed.", True), ("Today $1.2 Million [T31] was replayed.", True),
                     ("Today $1.3M [T31] was replayed.", False), ("Today $1.2 [T31] was replayed.", False),
                     ("Today $1,200k [T31] was replayed.", True), ("Today −$214k [T32] was lost.", True),
                     ("Today $214k [T32] was lost.", True), ("Today +$214k [T32] was lost.", False)]:
        nums, r = read(text, F4)
        assert (r["verified"], r["total"]) == ((9, 9) if ok else (8, 9)), text
        assert not any("spells out" in d for d in r["defects"]), text         # "$1.2 million" is digits, not words
    assert read("Today $1.2M [T31] was replayed.", F4)[0] == ["$1.2M"]


F5 = {**F, "T40": dict(label="RY weight", value=0.12, unit="pct", entity="RY.TO", sign="none", kind="fact"),
      "T41": dict(label="Lone letter", value=0.12, unit="pct", entity="T", sign="none", kind="fact")}


def test_entities_match_whole_words_or_known_aliases_only():                   # minors
    for text, ok in [("In this history it was 12 % [T40].", False), ("Every holding was 12 % [T40].", False),
                     ("The recovery was 12 % [T40].", False), ("RY.TO was 12 % [T40].", True), ("RY was 12 % [T40].", True),
                     ("Your ry.to holding was 12 % [T40].", True), ("The total was 12 % [T41].", False),
                     ("T was 12 % [T41].", False), ("Thereafter it fell 34.5 % [T10].", False),
                     ("After the move it fell 34.5 % [T10].", True), ("With the move's mix it fell 34.5 % [T10].", True),
                     ("Today's mix fell 10.6 % [T9].", True), ("The tariffs episode was 9.1 % [T16].", True),
                     ("Tariff-driven drops were 9.1 % [T16].", True), ("A tariffless year was 9.1 % [T16].", False),
                     ("NVIDIA at 8 % [T19] is the largest size.", True), ("Invidia at 8 % [T19] is the largest size.", False)]:
        r = read(text, F5)[1]
        assert bool(r["wrong_entity"]) == (not ok), text
        assert (r["verified"], r["total"]) == ((9, 9) if ok else (8, 9)), text


# ---- Task 1b (board resolution 4, spec 24): the receipt checks meaning, not only magnitude --------------------------
# Rule 1: a direction word must agree with the cited row's sign.
F6 = {**F, "T21": dict(label="Growth per year after the move", value=0.252, unit="pct", entity="after", sign="positive", kind="fact"),
      "T22": dict(label="Growth per year today", value=0.087, unit="pct", entity="today", sign="positive", kind="fact")}
ROSE_FELL = "Sentence 2 says the value rose but [T9] fell. Write that it fell, or cite the row that rose."


def meaning(text, facts=F6, **kw):
    """(verified, total, defects) of sentence 2 of the plan debrief."""
    r = verify_numbers(swap(0, text), facts, as_of="2026-11-12", result=R, **kw)
    return r["verified"], r["total"], r["defects"]


def test_a_rise_word_on_a_falling_row_is_a_named_defect():                      # the juror's probe
    for word in ("gained", "rose", "grew", "climbed", "jumped", "increased", "advanced", "earned", "was up", "went up by", "up"):
        v, t, d = meaning(f"Your portfolio today {word} 10.6 % [T9].")
        assert (v, t, d) == (8, 9, [ROSE_FELL]), word


def test_a_qualifier_before_the_number_does_not_hide_the_direction():
    for q in ("more than", "less than", "nearly", "roughly", "about", "over", "at least", "as much as", "a full"):
        assert meaning(f"Your portfolio today gained {q} 10.6 % [T9].")[2] == [ROSE_FELL], q
        assert meaning(f"Your portfolio today fell {q} 10.6 % [T9].")[2] == [], q
    for level in ("to", "from", "below", "above", "past", "beyond"):               # a level is not a change
        assert meaning(f"Your portfolio today rose {level} 10.6 % [T9].")[2] == [], level


def test_a_fall_word_on_a_rising_row_is_a_named_defect():
    for word in ("fell", "lost", "dropped", "declined", "slid", "sank", "shrank", "was down", "went down by", "down"):
        v, t, d = meaning(f"After the move the portfolio {word} 25.2 % per year [T21].")
        assert (v, t, d) == (8, 9, ["Sentence 2 says the value fell but [T21] rose. Write that it rose, or cite the row that fell."]), word


def test_direction_words_that_agree_with_the_row_pass():
    for text in ("Your portfolio today fell at most 10.6 % [T9].", "Today your portfolio lost 10.6 % [T9].",
                 "Today your portfolio dropped by 10.6 % [T9].", "Today your portfolio was down 10.6 % [T9].",
                 "Today your portfolio fell −10.6 % [T9].", "After the move the portfolio grew 25.2 % [T21] per year.",
                 "After the move the mix rose 25.2 % [T21] a year.", "After the move it gained 25.2 % [T21].",
                 "After the move it was up 25.2 % [T21].", "After the move the move lost $207,000 [T11].",
                 "After the move a $207,000 [T11] fall.", "After the move a 34.5 % [T10] drop.",
                 "Today a 10.6 % [T9] drop.", "After the move a 25.2 % [T21] gain."):
        v, t, d = meaning(text)
        assert (v, t, d) == (9, 9, []), text


def test_the_rows_sign_field_decides_and_the_value_is_the_fallback():
    base = dict(label="Gain", unit="pct", entity="today", kind="fact")
    rows = {"T9": {**base, "value": -0.106, "sign": "none"},                       # no usable sign: the value's sign
            "T14": {**base, "value": 0.087, "sign": "negative"},                   # the sign field wins (older mocks store a magnitude)
            "T50": {**base, "value": 0, "sign": "zero"}}
    facts = {**F6, **rows}
    assert meaning("Today it gained 10.6 % [T9].", facts)[2] == [ROSE_FELL]
    assert meaning("Today it lost 8.7 % [T14].", facts)[:2] == (9, 9)
    assert meaning("Today it gained 8.7 % [T14].", facts)[2] == ["Sentence 2 says the value rose but [T14] fell. Write that it fell, or cite the row that rose."]
    assert meaning("Today it gained 0.0 % [T50].", facts)[2] == ["Sentence 2 says the value rose but [T50] did not move. Remove the direction word, or cite the row that rose."]


def test_a_direction_flip_is_found_in_the_verdict_sentence_and_is_not_a_traced_number():
    r = verify_numbers(deb(vs=VS.replace("fell 34.5", "rose 34.5")), F6, as_of="2026-11-12", result=R)
    assert r["defects"] == ["Sentence 1 says the value rose but [T10] fell. Write that it fell, or cite the row that rose."]
    assert (r["verified"], r["total"]) == (8, 9)
    r = verify_numbers(swap(0, "Your portfolio today gained 10.6 % [T9]."), F6, as_of="2026-11-12", result=R)
    assert [x["number"] for x in r["wrong_direction"]] == ["10.6 %"] and r["unverified"] == [] and r["wrong_side"] == []
    assert [x["sentence"] for x in r["wrong_direction"]] == [2] and r["wrong_direction"][0] in r["matches"]
    assert (r["verified"], r["total"]) == (8, 9)                                  # the juror's "gained 10.6 %" is no longer "traced"


# Rule 2: a clause about today must cite today's row, a clause about the move must cite the move's row.
TODAY_ROW = ("Sentence 2 is about today but [T10] is about the portfolio after the move. "
             "Say it is after the move, or cite today's row.")
AFTER_ROW = ("Sentence 2 is about the portfolio after the move but [T9] is about today. "
             "Say it is today, or cite the row for after the move.")


def test_today_attributed_to_the_after_row_is_a_named_defect():                  # the juror's probe
    v, t, d = meaning("Today your portfolio fell 34.5 % [T10] after rates rose.")
    assert (v, t, d) == (8, 9, [TODAY_ROW])
    v, t, d = meaning("Your mix as it is fell 34.5 % [T10].")                    # no other word names the move
    assert d and v == 8
    v, t, d = meaning("Today your mix lost $207,000 [T11] after rates rose.")
    assert (v, t) == (8, 9) and "is about today but [T11] is about the portfolio after the move" in d[0]


def test_the_move_attributed_to_todays_row_is_a_named_defect():
    v, t, d = meaning("After the move your portfolio fell 10.6 % [T9], while today is calm.")
    assert (v, t, d) == (8, 9, [AFTER_ROW])
    v, t, d = meaning("After the move, your portfolio fell 10.6 % [T9], no better than today.")   # an opening phrase sets the side
    assert (v, t, d) == (8, 9, [AFTER_ROW])


def test_each_clause_is_judged_on_its_own_side():
    ok = "Today your portfolio fell 10.6 % [T9] and after the move 34.5 % [T10]."
    assert meaning(ok) == (10, 10, [])
    assert meaning("Today it fell 10.6 % [T9]; after the move it fell 34.5 % [T10].") == (10, 10, [])
    assert meaning("The worst drop was 10.6 % [T9] today against 34.5 % [T10] after the move.") == (10, 10, [])
    swapped = meaning("Today your portfolio fell 34.5 % [T10] and after the move 10.6 % [T9].")
    assert swapped[:2] == (8, 10) and len(swapped[2]) == 2


def test_clauses_that_name_both_sides_or_neither_are_not_second_guessed():
    for text in ("Today it fell 10.6 % [T9], and the move fell 34.5 % [T10].",
                 "After the move it fell 34.5 % [T10], past your limit.",
                 "With the move your mix fell 34.5 % [T10] from its high in 2022.",
                 "The portfolio fell 10.6 % [T9] today."):
        v, t, d = meaning(text)
        assert v == t and d == [], text
    assert meaning("Today it fell 10.6 % [T9], with the move at 34.5 % [T10].")[2] == []


def test_entities_written_with_a_side_word_accept_that_sides_aliases():
    F7 = {**F, "T9": dict(F["T9"], entity="portfolio today"), "T10": dict(F["T10"], entity="portfolio after")}
    assert meaning("Today it fell 10.6 % [T9]; after the move it fell 34.5 % [T10].", F7) == (10, 10, [])
    v, t, d = meaning("Today your portfolio fell 34.5 % [T10] after rates rose.", F7)
    assert v == 8 and d == [TODAY_ROW]


# Rule 3: advice and forecast words are named defects even when every number is traced.
def advice_line(i, word):
    return f"Sentence {i} gives advice or a forecast (“{word}”): describe what happened in this history instead."


ADVICE = [("You should cut NVIDIA to 8 % [T19] and buy XBB.", ["should", "cut to", "buy"]),     # the juror's probe, whole
          ("Today your portfolio fell 10.6 % [T9], so we recommend a smaller size.", ["recommend"]),
          ("Today you could sell part of it after it fell 10.6 % [T9].", ["sell"]),
          ("Buy more XBB, because today it fell 10.6 % [T9].", ["buy"]),
          ("Hold NVIDIA: today it fell 10.6 % [T9].", ["hold"]),
          ("Today it fell 10.6 % [T9]; hold on to your shares.", ["hold"]),
          ("Today it fell 10.6 % [T9]; keep holding it.", ["hold"]),
          ("Today it fell 10.6 % [T9], so you could hold the position.", ["hold"]),
          ("Cut NVIDIA to 8 % [T19] and today's drop of 10.6 % [T9] is smaller.", ["cut to"]),
          ("NVIDIA will fall 34.5 % [T10] after the move in the next tariff war.", ["will fall"]),   # the juror's probe
          ("After the move the mix will rise 25.2 % [T21] a year.", ["will rise"]),
          ("After the move the mix will cost you $207,000 [T11].", ["will cost"]),
          ("After the move the mix is going to drop 34.5 % [T10].", ["is going to drop"]),
          ("After the move we expect a drop of 34.5 % [T10].", ["expect"]),
          ("After the move a loss of 34.5 % [T10] is expected to repeat.", ["expected"]),
          ("After the move, 34.5 % [T10] is unsuitable for you.", ["unsuitable"]),
          ("After the move, 34.5 % [T10] is not suitable for your floor.", ["not suitable"]),
          # "recommend" is a board-named word (spec 24 resolution 4): the verb forms stay advice when they are negated,
          # only the label noun "not a recommendation" is exempt (fix round 1)
          ("Today it fell 10.6 % [T9], which is not recommended.", ["recommended"]),
          ("After the move, 34.5 % [T10] is never recommended for your floor.", ["recommended"]),
          ("We do not recommend NVIDIA at 8 % [T19] after the move.", ["recommend"]),
          ("Today it fell 10.6 % [T9], so we don't recommend it.", ["recommend"]),
          ("Today it fell 10.6 % [T9], so it isn’t recommended.", ["recommended"]),
          ("Today it fell 10.6 % [T9], and this doesn't recommend NVIDIA.", ["recommend"])]


def test_advice_and_forecast_words_are_named_defects_even_when_every_number_is_traced():
    for text, words in ADVICE:
        r = verify_numbers(swap(0, text), F6, as_of="2026-11-12", result=R)
        assert r["verified"] == r["total"], text            # every number is traced, so `verified == total` is NOT "clean" ...
        assert r["defects"] == [advice_line(2, w) for w in words], text            # ... clean is `defects == []`; the words are a defect
        assert [a["word"] for a in r["advice"]] == words and r["advice"][0]["sentence"] == 2, text


def test_advice_is_found_in_the_verdict_sentence_and_every_section():
    vs = VS.replace("past your floor", "so you should cut it to your floor")
    r = verify_numbers(deb(vs=vs), F6, as_of="2026-11-12", result=R)
    assert r["defects"] == [advice_line(1, "should"), advice_line(1, "cut to")]
    for k in range(4):
        r = verify_numbers(swap(k, ROWS[k][2][:-1] + ", so buy now."), F6, as_of="2026-11-12", result=R)
        assert advice_line(k + 2, "buy") in r["defects"]


LEGIT = ["Today it fell 10.6 % [T9], a Fictional illustration, not a recommendation.",
         "Today it fell 10.6 % [T9] in the 2022 sell-off.", "Today it fell 10.6 % [T9] in the selloff.",
         "After the move the mix would hold 4 independent bets [T20].", "Today your holdings fell 10.6 % [T9].",
         "Today you hold a mix that fell 10.6 % [T9].", "The Fed cut rates to a high in this history and today it fell 10.6 % [T9].",
         "Today it fell 10.6 % [T9] and an unexpected shock followed.", "Today it fell 10.6 % [T9]: expected shortfall is not computed.",
         "This already happened, it is not a forecast: today it fell 10.6 % [T9].",
         "Today it fell 10.6 % [T9]; nobody can know future prices.", "Today the buyback and the buyer fell 10.6 % [T9].",
         "Today it fell 10.6 % [T9], and the shock check is half your floor."]


def test_descriptive_uses_of_the_same_words_are_left_alone():
    for text in LEGIT:
        r = verify_numbers(swap(0, text), F6, as_of="2026-11-12", result=R)
        assert r["advice"] == [] and not [d for d in r["defects"] if "advice" in d], text


# The deferred minors of Task 1 (ledger 20): the receipt never skips a spelled-out quantity.
def spelled_only(text):
    r = verify_numbers(swap(0, text), F6, result=R)
    return [u["number"] for u in r["unverified"]], r["defects"]


def test_half_your_floor_is_exempt_only_beside_shock():                         # ledger 20
    for ok in ("Today the shock check, half your floor, fell 10.6 % [T9].", "Today the shock limit is half the floor, 10.6 % [T9].",
               "Today the shock limit (half your floor) was 10.6 % [T9]."):
        assert spelled_only(ok) == ([], []), ok
    for bad in ("Today half your floor fell 10.6 % [T9].", "Today it fell 10.6 % [T9], half the floor.",
                "Today it fell 10.6 % [T9]. The limit is half your floor."):
        nums, defects = spelled_only(bad)
        assert nums and nums[-1].lower() == "half" and "spells out a number (“half”)" in defects[-1], bad


def test_spelled_percent_signs_weeks_dozens_and_doublings_are_named_defects():
    for text, token in (("ten %", "ten %"), ("five weeks", "five weeks"), ("two hours", "two hours"), ("2 dozen", "2 dozen"),
                        ("3 hundred", "3 hundred"), ("doubled", "doubled"), ("tripled", "tripled"), ("halved", "halved"),
                        ("Doubled", "Doubled"), ("hundreds of shocks", "hundreds"), ("thousands of days", "thousands"),
                        ("dozens of events", "dozens"), ("a couple of days", "a couple")):
        nums, defects = spelled_only(f"Today it fell 10.6 % [T9], and {text} followed.")
        assert nums == [token], (text, nums)
        assert defects == [f"Sentence 2 spells out a number (“{token}”): write the number in digits and "
                           "cite the row that holds it, or remove it."], (text, defects)


def test_hyphenated_percent_is_a_percent_and_weeks_are_not_counts():
    assert read("Today it fell a 10.6-percent drop [T9].")[1]["defects"] == []
    assert read("Today it fell a 10.6-pct drop [T9].")[1]["verified"] == 9
    F8 = {**F, "T20": dict(F["T20"], entity="today")}
    nums, r = read("Today 4 weeks [T20] passed.", F8)
    assert nums == ["4 weeks"] and r["unverified"]                              # 4 weeks is not the row's 4 episodes
    nums, r = read("Today four weeks [T20] passed.", F8)
    assert [u["number"] for u in r["unverified"] if u["sentence"] == 2] == ["four weeks"]


def test_a_row_whose_entity_is_a_ticker_or_family_takes_its_side_from_its_label():
    F9 = {**F6, "T16": dict(F6["T16"], label="Worst clean tariff shock after the move")}
    v, t, d = meaning("Today the worst tariff shock cost 9.1 % [T16].", F9)
    assert (v, t, d) == (8, 9, [TODAY_ROW.replace("[T10]", "[T16]")])
    assert meaning("After the move the worst tariff shock cost 9.1 % [T16].", F9) == (9, 9, [])
    assert meaning("The worst tariff shock cost 9.1 % [T16].", F9) == (9, 9, [])            # no side said: nothing to compare


def test_the_move_row_belongs_to_neither_side():                              # fix round 1: the hero question's sentence
    """The move row ("The move: NVDA set to", kind fiction) is what the investor asked about, not a measure of today or
    of the move: its label says "the move", but a clause about today that quotes it is not a wrong side (it tripped a
    needless re-ask on the hero question)."""
    move = dict(label="The move: NVDA set to", value=0.40, unit="pct", entity="NVDA", sign="positive", kind="fiction")
    F10 = {**F6, "T4": move}
    for text in ("Today you are asking about 40 % [T4] in NVIDIA.", "Your mix as it is has you asking about 40 % [T4] in NVIDIA.",
                 "After the move you would ask about 40 % [T4] in NVIDIA.", "You are asking about 40 % [T4] in NVIDIA."):
        r = verify_numbers(swap(3, text), F10, as_of="2026-11-12", result=R)
        assert (r["verified"], r["total"], r["wrong_side"], r["defects"]) == (9, 9, [], []), text
    # the label route still works for the rows that measure a side (their entity is a ticker or a family)
    F11 = {**F10, "T5": dict(label="NVDA share of the risk after the move", value=0.61, unit="pct", entity="NVDA", sign="positive", kind="fact")}
    r = verify_numbers(swap(0, "Today NVIDIA carried 61 % [T5] of the risk."), F11, as_of="2026-11-12", result=R)
    assert r["defects"] == [TODAY_ROW.replace("[T10]", "[T5]")] and [x["number"] for x in r["wrong_side"]] == ["61 %"]


# ---- scripts/receipt_mutation.py: the recall table is deterministic, big enough, and published ------------------------
def _mutation():
    from scripts import receipt_mutation
    return receipt_mutation


@functools.lru_cache(maxsize=1)
def _collected():
    return _mutation().collect()


def test_wilson_interval_matches_known_values():
    rm = _mutation()
    assert [round(x, 4) for x in rm.wilson(5, 10)] == [0.2366, 0.7634]
    assert [round(x, 4) for x in rm.wilson(0, 10)] == [0.0, 0.2775]
    assert [round(x, 4) for x in rm.wilson(10, 10)] == [0.7225, 1.0]
    assert rm.wilson(0, 0) == (0.0, 1.0)


def test_the_mutation_table_is_deterministic_and_published():
    rm = _mutation()
    data, again = _collected(), rm.collect()
    assert rm.render(data) == rm.render(again)
    assert data["clean"]["defects"] == []                     # a clean receipt is `defects == []` (spec 24 resolution 7) ...
    assert (data["clean"]["verified"], data["clean"]["total"]) == (16, 16)       # ... the fixture's own count, quoted in the doc
    assert sum(v["n"] for v in data["in_scope"].values()) >= 60
    assert set(data["in_scope"]) == set(rm.IN_SCOPE)
    published = (rm.OUT).read_text(encoding="utf-8")
    assert published == rm.render(data), "docs/receipt_mutation.md is stale: run python scripts/receipt_mutation.py"


def _doc_tables(text):
    """[(header cells, data rows as cell lists, the paragraph right after the table)] for every markdown table of `text`;
    the paragraph is the lines up to the next blank line, so a limit that wraps onto a second line shows as two lines."""
    def cells(line):
        return [c.strip() for c in line.strip().strip("|").split("|")]
    lines, out, k = text.splitlines(), [], 0
    while k < len(lines):
        if not lines[k].startswith("|"):
            k += 1
            continue
        start = k
        while k < len(lines) and lines[k].startswith("|"):
            k += 1
        rows = [cells(line) for line in lines[start:k]]                  # header, separator, data rows
        while k < len(lines) and not lines[k].strip():
            k += 1
        end = k
        while end < len(lines) and lines[end].strip():
            end += 1
        out.append((rows[0], rows[2:], "\n".join(lines[k:end])))
    return out


def test_the_published_table_carries_the_docs_rule_fields():                   # the docs rule, fix round 1
    """Every measured rate: k / N, Wilson 95 % interval, model, date, evidence level (Measured N >= 30, Indicative N < 30)
    and a one-line limit. The date is a constant (the script has no clock); the evidence level follows each row's own N."""
    rm = _mutation()
    text = rm.OUT.read_text(encoding="utf-8")
    assert datetime.date.fromisoformat(rm.MEASURED_ON).isoformat() == rm.MEASURED_ON
    assert f"Measured on: {rm.MEASURED_ON}" in text and "Model: none, deterministic code" in text
    assert rm.evidence(29) == "Indicative" and rm.evidence(30) == "Measured" and rm.evidence(178) == "Measured"
    tables = _doc_tables(text)
    assert len(tables) == 4                      # injected defects, what the rules add, false alarms, known gaps
    seen = set()
    for header, rows, after in tables:
        n_col, ev_col = next(i for i, h in enumerate(header) if h in ("N", "Rewrites")), header.index("Evidence")
        assert any("Wilson 95 %" in h for h in header), header
        assert rows and after.startswith("**Limit.** ") and "\n" not in after, (header, after)
        for cells in rows:
            seen.add(cells[ev_col])
            assert cells[ev_col] == ("Measured" if int(cells[n_col]) >= 30 else "Indicative"), cells
    assert seen == {"Measured", "Indicative"}                                  # both levels occur: the column is not a constant


def test_every_injected_defect_class_is_caught_and_benign_rewrites_are_not_flagged():
    data = _collected()
    for cls, v in data["in_scope"].items():
        assert v["k"] == v["n"], (cls, v["misses"])
    assert data["benign"]["k"] == 0 and data["benign"]["n"] >= 20, data["benign"]["flagged"]
    assert all(v["k"] == 0 for v in data["gaps"].values())          # the stated gaps stay stated: a fix moves the case into a class


# The juror's probe table (/tmp/epi_jury2/juror-3-scripts/probe_verify.py): what the receipt now says to each probe.
J = {**F6, "T6": dict(F["T6"], sign="positive"), "T19": dict(F["T19"], sign="positive"), "T20": dict(F["T20"], sign="positive")}
J_BASE = [("data", "fact", "Your portfolio today fell at most 10.6 % [T9]."),
          ("why", "assumption", "Your floor is 15 % [T3]; the move lost $207,000 [T11]."),
          ("limits", "limit", "This already happened, it is not a forecast: 4 tariff shocks [T20]."),
          ("would_change", "scenario", "In this history your floor breaks above 8 % [T19] NVIDIA.")]


def juror(index, text):
    rows = list(J_BASE)
    sec, kind, _ = rows[index]
    rows[index] = (sec, kind, text)
    return verify_numbers(deb(rows), J, as_of="2026-11-12", result=R)


def test_the_jurors_probes():
    assert juror(0, J_BASE[0][2])["defects"] == []
    assert juror(0, "Your portfolio today gained 10.6 % [T9].")["defects"] == [ROSE_FELL]
    r = juror(0, "Today your portfolio fell 34.5 % [T10] after rates rose.")
    assert r["defects"] == [TODAY_ROW] and r["verified"] == r["total"] - 1
    r = juror(0, "After the move the portfolio lost 25.2 % [T21] per year.")
    assert r["defects"] == ["Sentence 2 says the value fell but [T21] rose. Write that it rose, or cite the row that fell."]
    r = juror(3, "You should cut NVIDIA to 8 % [T19] and buy XBB.")
    assert [a["word"] for a in r["advice"]] == ["should", "cut to", "buy"] and r["verified"] == r["total"]   # was "8 of 8 traced"
    r = juror(2, "NVIDIA will fall 34.5 % [T10] after the move in the next tariff war.")
    assert [d for d in r["defects"] if "advice" in d] == [advice_line(4, "will fall")]


def test_what_the_receipt_still_does_not_read_is_pinned():                     # claims without a number: the known gaps
    for k, text in ((1, "The 2022 loss after the move was caused by the Fed's rate hikes [T10]."),
                    (0, "Today your portfolio is well diversified."),
                    (0, "Today your portfolio fell at most 10.6 % [T9], far less than any bank stock.")):
        assert juror(k, text)["defects"] == [], text
    assert juror(0, "Today your portfolio is well diversified and safe.")["defects"]      # ruling R1 names "safe" now


def test_the_meaning_rules_are_what_catches_the_meaning_defects():
    data = _collected()
    off, on = data["number_only"], data["in_scope"]
    assert (off["direction flip"]["k"], off["advice or forecast"]["k"]) == (0, 0)            # the juror's two probes, as a class
    assert off["entity swap"]["k"] < on["entity swap"]["k"]
    for same in ("number nudge", "spelled-out number", "dropped [T#]"):
        assert off[same]["k"] == on[same]["k"] == on[same]["n"], same


def test_the_shock_check_caveat_follows_the_rows_own_fields():
    """B Task 5 (ledger 30): beyond its threshold the shock check is a warn with a value ("Caution"), not a fail. No
    value: "no close precedent at this date"; fewer than 2 clean episodes: "too few separate episodes to conclude";
    otherwise the soft line with its count, (Indicative) when mixed episodes count."""
    from verify import caveat_phrases
    row = lambda **k: {"rule": "scenario_stress", "status": "warn", "value": -0.09, "limit": -0.075, **k}
    assert caveat_phrases([row(value=None, n_episodes=0)]) == ["no close precedent at this date"]
    assert caveat_phrases([row(n_episodes=1, family="Tariff war")]) == ["too few separate episodes to conclude"]
    assert caveat_phrases([row(n_episodes=5, family="Tariff war", evidence="Measured")]) == [
        "in the 5 separate earlier tariff war episodes, this mix lost up to 9.0 %"]
    assert caveat_phrases([row(n_episodes=6, family="Tariff war", evidence="Indicative (mixed with saudi_pipeline_2026)"),
                           {"rule": "missing_data", "status": "warn"},
                           {"rule": "scenario_stress", "status": "pass", "value": -0.01}]) == [
        "in the 6 separate earlier tariff war episodes, this mix lost up to 9.0 % (Indicative)", "missing data"]
    R3 = {**R, "checks": [row(n_episodes=5, family="Tariff war", evidence="Measured")]}
    said = deb(ROWS + [("why", "assumption", "In the 5 [T12] separate earlier tariff war episodes, this mix lost up to 9.0 % [T13].")])
    assert not [x for x in verify_numbers(said, F, result=R3)["defects"] if x.startswith("The debrief must say")]
    assert "The debrief must say “in the 5 separate earlier tariff war episodes, this mix lost up to 9.0 %”." in \
        verify_numbers(deb(ROWS), F, result=R3)["defects"]


# ---- Sun Nov 15 receipt fix (ruling R36 c and e; /tmp/epi_stress/receipt/diagnosis.md patterns E2, E3, U1) ----------
# Four narrow over-strict rules found in the live drafts: each true sentence below got exactly one defect line before.
def _r36_row(label, value, unit, entity, kind):
    return dict(label=label, value=value, unit=unit, entity=entity, kind=kind,
                sign="negative" if value < 0 else "positive" if value > 0 else "zero")


# A run with no move: every row is a today row (ledger: "Entity `today` replaces `after` when there is no change").
R36_NO_MOVE = {"T17": _r36_row("Fictional amount", 80000, "CAD", "your amount", "fiction"),
               "T22": _r36_row("Shock limit (half your floor)", -0.075, "pct", "shock check", "assumption"),
               "T23": _r36_row("Clean rate shock shocks known", 3, "count", "rates", "fact"),
               "T26": _r36_row("Worst clean shock in the shock check today", -0.046, "pct", "today", "fact"),
               "T27": _r36_row("Largest single-company share today", 0.043, "pct", "today", "fact"),
               "T28": _r36_row("One-company limit", 0.10, "pct", "one company", "assumption"),
               "T31": _r36_row("Crypto share today", 0.15, "pct", "today", "fact")}
R36_WITH_MOVE = {**R36_NO_MOVE, "T10": _r36_row("Worst drop after the move", -0.345, "pct", "after", "fact")}


def _r36(text, facts=R36_NO_MOVE):
    return verify_numbers([{"text": text, "kind": "scenario"}], facts)


def test_r36_true_sentences_from_the_live_drafts_pass():
    for text in (
            "We replayed a fictional $80,000 [T17] portfolio on real market history up to the decision date.",   # E2b
            "The largest single-company share today is 4.3 % [T27] against a limit of 10.0 % [T28].",             # E2a
            "The one-company limit is 10.0 % [T28].",                                                             # E2a
            "The single stock limit is 10.0 % [T28].",
            "The crypto share is brought from 15.0 % [T31] down to the limit.",                                   # E3
            "For rates, there are 3 separate earlier episodes [T23], and the worst clean one in the shock check "
            "today was a loss of 4.6 % [T26] against a shock limit of 7.5 % [T22]."):                             # U1
        lines = [d for d in _r36(text)["defects"] if d.startswith("Sentence")]   # a bare list has no sections
        assert lines == [], (text, lines)


def test_r36_the_rules_still_catch_what_they_are_for():
    assert _r36("The crypto share is 15.0 % [T31].", R36_WITH_MOVE)["wrong_entity"]      # with a move, name the side
    assert _r36("Bonds are 10.0 % [T28] of the mix.")["wrong_entity"]                   # the limit is not named
    assert _r36("The worst drop grew past 7.5 % [T22].")["wrong_entity"]                # E1 stays a defect
    assert _r36("Only one shock [T23] broke the floor.")["unverified"]                  # a count, not a pronoun
    assert _r36("Thereafter it fell 34.5 % [T10].", R36_WITH_MOVE)["wrong_entity"]       # "thereafter" is not "after"
    assert _r36("Your amount was $80,000 [T17].", {**R36_NO_MOVE, "T17": {**R36_NO_MOVE["T17"], "entity": "after"}}
                )["wrong_entity"]                                                    # "fictional" names no side


def test_r36_recover_names_the_recovery_limit():
    """Live robert:rates draft 1 (Sun Nov 15): the verb names the recovery limit as surely as the noun."""
    facts = {"T24": _r36_row("Days to recover today", 416, "days", "today", "fact"),
             "T35": _r36_row("Recovery days your horizon gives", 487, "days", "recovery", "assumption")}
    ok = "The portfolio took 416 days [T24] to recover, within the 487 days [T35] your horizon gives."
    assert [d for d in _r36(ok, facts)["defects"] if d.startswith("Sentence")] == []
    assert _r36("The portfolio stayed within 487 days [T35].", facts)["wrong_entity"]     # unnamed: still a defect


def test_r27_advice_by_suggestion_is_advice():
    for text, word in (("Consider holding NVDA [T3] through the shock.", "consider holding"),
                       ("You may want to add SPY.", "you may want to add"),
                       ("Think about trimming NVDA.", "think about trimming"),
                       ("Investors might wish to keep the position.", "investors might wish to keep")):
        found = verify_numbers([{"text": text, "kind": "scenario"}], {"T3": _r36_row("NVDA share", 0.4, "pct", "NVDA", "fact")})
        assert word in [a["word"] for a in found["advice"]], (text, found["advice"])
        assert any("gives advice or a forecast" in d for d in found["defects"]), text
    for text in ("Consider the 2022 fall: the portfolio lost 34.5 % [T3].", "Think about your horizon of 4 years [T3].",
                 "The holding period was long."):
        assert verify_numbers([{"text": text, "kind": "scenario"}], {})["advice"] == [], text


def test_a_hyphenated_limit_name_names_the_failed_limit():
    """Live, Sun Nov 15 (the past-tense prompt): "the one-company limit all broke" was read as not naming One company."""
    result = {"verdict": "Incompatible", "checks": [{"rule": "single_stock", "status": "fail"},
                                                    {"rule": "sector", "status": "fail"}]}
    said = [{"text": "Outside your limits: your floor, the one-company limit and the one-sector limit all broke.",
             "kind": "verdict"}]
    assert not [d for d in verify_numbers(said, {}, result=result)["missing"] if "failed limit" in d]
    bare = [{"text": "Outside your limits: your floor broke.", "kind": "verdict"}]
    assert "The debrief does not name the failed limit “One company”. Name it." in verify_numbers(bare, {}, result=result)["missing"]


def test_a_yes_or_no_answer_to_an_approval_seeking_question_is_advice():
    """The reframe (controller ruling, Sun 2026-11-15): when the Result carries `reframe`, the explanation must not
    answer yes or no; the receipt names it like an advice word, so it is re-asked once and withheld if it stays."""
    reframed = {**R, "reframe": {"reason": "asks whether a move or a size is right for you"}}
    for s in ("Yes, it stayed inside your limits.", "No — your floor broke in this replay.",
              "● No, that move was outside your limits.", "The short answer is no: your floor broke.", "In short, yes."):
        rc = verify_numbers([s], {}, result=reframed)
        assert [a["word"] for a in rc["advice"]] == ["yes / no"], s
        assert any("answers yes or no" in d for d in rc["defects"]), s
    assert verify_numbers(["Yes, it stayed inside your limits."], {}, result=R)["advice"] == []   # no reframe: no rule
    for s in ("No limit was crossed in this replay.", "Nobody can say what comes next.", "No-one sold in this history."):
        assert verify_numbers([s], {}, result=reframed)["advice"] == [], s


def test_an_industry_limit_is_named_by_its_industry_in_plain_words():
    """Lane sector-limits: governance's row per industry the investor limited ("sector_cap:<GICS sector>"). The debrief
    names it with the industry's plain words ("your technology limit", "the energy you excluded"), never the rule id."""
    result = {"verdict": "Incompatible", "checks": [{"rule": "sector_cap:Information Technology", "status": "fail"},
                                                    {"rule": "sector_cap:Energy", "status": "fail"}]}
    said = [{"text": "Outside your limits: your technology limit and the energy you excluded both broke.", "kind": "verdict"}]
    assert not [d for d in verify_numbers(said, {}, result=result)["missing"] if "failed limit" in d]
    bare = [{"text": "Outside your limits: your floor broke.", "kind": "verdict"}]
    missing = verify_numbers(bare, {}, result=result)["missing"]
    assert "The debrief does not name the failed limit “Your Information Technology limit”. Name it." in missing
    assert "The debrief does not name the failed limit “Your Energy limit”. Name it." in missing
    import verify
    assert verify.RULE_NAMES["sector_cap:Health Care"] == "Your Health Care limit"
    assert "health" in verify.RULE_WORDS.get("sector_cap:Health Care") and "sector_cap:Energy" not in verify.RULE_NAMES
