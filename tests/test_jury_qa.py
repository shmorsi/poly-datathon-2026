"""The jury-QA campaign's findings in the navigator and the explainer (Sun Nov 15, /tmp/epi_lanes/juryqa): two moves in
one question, dollars against a known amount, a long question read to its end, the shock caveat's count as its own
fact, the investor's own numbers never cited as facts, "never broke" about a soft limit the mix went past, and the
code-written lead when the shock check could not conclude."""
import pytest

import pipeline
import verify
from agents import scenario as sc

ROBERT = {"XIU.TO": 0.45, "XBB.TO": 0.35, "GLD": 0.10, "ZST.TO": 0.10}
UNIV = [{"ticker": t, "name": n} for t, n in [("NVDA", "NVIDIA"), ("XIU.TO", "iShares S&P/TSX 60 Index ETF"),
        ("XBB.TO", "iShares Core Canadian Universe Bond Index ETF"), ("GLD", "SPDR Gold Shares"),
        ("ZST.TO", "BMO Ultra Short-Term Bond ETF"), ("ETH-USD", "Ethereum"), ("AAPL", "Apple"), ("SPY", "SPDR S&P 500 ETF")]]


def _check(question, plan, amount=600000):
    return sc.validate_plan(plan, question=question, portfolio=ROBERT, catalog=[], universe=UNIV, seen={},
                            amount=amount, exposure={"countries": {}}, as_of="2026-11-12")


def _plan(change=None, reason=None):
    return {"type": "change", "families": [], "regions": [], "event_ids": [], "event_whys": None, "intent": None,
            "change": change, "clarify_reason": reason, "widened_from": None}


@pytest.mark.parametrize("question, both", [
    ("What if I put 10 % in Ether and 10 % in Apple?", "10 % in Ether or 10 % in Apple"),              # X1
    ("What if I put 20 % in NVIDIA and 20 % in Apple?", "20 % in NVIDIA or 20 % in Apple"),            # X2
    ("What if I put 20 % in NVIDIA, 10 % in Apple?", "20 % in NVIDIA or 10 % in Apple")])
def test_two_moves_in_one_question_ask_one_honest_question_and_never_drop_the_second(question, both):
    want = f"EPICENTRE replays one move at a time. Which first: {both}?"
    assert sc.read_move(question, UNIV, 600000) == {"kind": "clarify", "reason": "two_moves", "name": both}
    kw = sc.keyword_fallback(question, ROBERT, [], "2026-11-12", universe=UNIV, amount=600000)
    assert (kw["clarify"], kw["clarify_reason"], kw["change"], kw["portfolio"]) == (want, "two_moves", None, None)
    first = _plan({"op": "set", "ticker": "ETH-USD" if "Ether" in question else "NVDA",
                   "weight": 0.1 if "10 % in Ether" in question else 0.2, "from_ticker": None})
    fields, why = _check(question, first)                       # the navigator replayed one move: code asks instead
    assert why is None and fields["clarify"] == want and fields["change"] is None


@pytest.mark.parametrize("question", [
    "What if I put 40 % in NVIDIA and Washington slaps new levies on Canadian goods?",
    "Everyone is talking about NVIDIA. What if I put 40 % in it and Washington slaps new levies on Canadian goods?",
    "What if I put 40 % in NVIDIA and the market falls 20 % in a week?",
    "What if I put 40 % in NVIDIA and 40 % in it?"])
def test_one_move_and_a_shock_is_still_one_move(question):
    assert sc.read_move(question, UNIV, 600000)["kind"] == "change"


def test_dollars_are_read_against_a_known_amount_and_a_size_question_is_refused():          # S5
    question = "What if I put $60k in NVIDIA?"
    nvda = {"op": "set", "ticker": "NVDA", "weight": 0.1, "from_ticker": None}
    assert sc.read_move(question, UNIV, 600000) == {"kind": "change", "request": nvda}
    kw = sc.keyword_fallback(question, ROBERT, [], "2026-11-12", universe=UNIV, amount=600000)
    assert kw["clarify"] is None and kw["change"] == nvda
    fields, why = _check(question, _plan(reason="size_ambiguous"))
    assert fields is None and why == "the plan asked a question about a move the code can read"   # -> the keyword rules
    fields, why = _check(question, _plan({"op": "set", "ticker": "NVDA", "weight": "$60k"}))
    assert why is None and fields["change"] == nvda
    assert sc.read_move(question, UNIV, None)["reason"] == "amount_unknown"            # no amount known: one question


def test_the_navigator_reads_the_whole_question_up_to_the_apis_limit():                    # L1
    import server
    filler = "I have been reading the news every morning, and my neighbour says the markets have been wild. " * 19
    question = filler + "So here is my question. What if I put 40 % in NVIDIA and Washington slaps new levies?"
    assert 1500 < len(question) <= server.MAX_TEXT == sc.MAX_QUESTION_CHARS
    msg = sc.user_message(question, ROBERT, "2026-11-12", None, amount=600000, universe=UNIV)
    assert "What if I put 40 % in NVIDIA and Washington slaps new levies?" in msg


SHOCK_ROW = {"rule": "scenario_stress", "status": "warn", "tier": "soft", "value": -0.095, "limit": -0.075,
             "n_episodes": 26, "family": "Tariff war + War & oil + Chip war + Rate shock", "evidence": "Indicative: mixed"}


def test_the_shock_caveats_count_has_its_own_fact_row_and_the_caveat_is_traced():         # M1 / M9 / X2
    r = {"checks": [SHOCK_ROW], "metrics": {"today": {"source": "s"}}}
    rows = [spec for spec in pipeline._check_specs(r) if spec[0].startswith("Separate earlier episodes")]
    assert [(s[1], s[2], s[3], s[4]) for s in rows] == [(26, "count", "episodes", "fact")]
    for quiet in ({**SHOCK_ROW, "status": "pass"}, {**SHOCK_ROW, "value": None}, {**SHOCK_ROW, "n_episodes": 1}):
        assert not [s for s in pipeline._check_specs({"checks": [quiet]}) if s[0].startswith("Separate earlier")]
    facts = {"T1": {"label": "Separate earlier episodes the shock check replayed", "value": 26, "unit": "count",
                    "entity": "episodes", "sign": "positive", "kind": "fact"},
             "T2": {"label": "Worst clean tariff war shock after the move", "value": -0.095, "unit": "pct",
                    "entity": "tariffs", "sign": "negative", "kind": "fact"}}
    text = ("In the 26 [T1] separate earlier tariff war + war & oil + chip war + rate shock episodes, this mix lost up "
            "to 9.5 % [T2] (Indicative).")
    rc = verify.verify_numbers([{"text": text, "kind": "fact", "section": "limits"}], facts,
                               result={"checks": [SHOCK_ROW]})
    assert rc["verified"] == rc["total"] == 2 and not [d for d in rc["defects"] if "must say" in d]


def test_a_number_from_the_investors_question_is_never_cited_as_a_fact():                 # H4
    facts = {"T26": {"label": "Clean rate shock shocks known", "value": 3, "unit": "count", "entity": "rates",
                     "sign": "positive", "kind": "fact"}}
    item = {"text": "The Fed hiked rates by 75 [T26] basis points.", "kind": "fact"}
    rc = verify.verify_numbers([item], facts, result={"question": "What if the Fed hikes rates by 75 basis points again?"})
    assert "Sentence 1 says 75, a number from the investor's question, not a fact: remove it." in rc["defects"]
    plain = verify.verify_numbers([item], facts, result={"question": "What if the Fed hikes rates again?"})
    assert "Sentence 1 says 75 and cites T26, whose value is 3. Use T26's value or remove the number." in plain["defects"]


def test_never_broke_about_a_soft_limit_the_mix_went_past_is_named():
    result = {"checks": [{"rule": "max_drawdown", "tier": "hard", "status": "fail"},
                         {"rule": "single_stock", "tier": "soft", "status": "fail"}]}
    for text in ("Your floor broke; the one-company limit raised a caution and never broke.",
                 "The one-company limit raised a caution and did not break."):
        rc = verify.verify_numbers([{"text": text, "kind": "fact"}], {}, result=result)
        assert any("but the mix went past" in d and "write “went past your soft limit: a caution”" in d
                   for d in rc["defects"]), text
    for text in ("Your floor never broke.", "The mix went past your soft one-company limit: a caution."):
        rc = verify.verify_numbers([{"text": text, "kind": "fact"}], {}, result=result)
        assert not any("but the mix went past" in d for d in rc["defects"]), text


def test_allowed_is_a_named_defect_in_both_checkers():                                     # E5 (ruling R1)
    from agents import explainer as ex
    assert ex._R1.search("The one-company limit allowed 10 %.") and verify._R1.search("It was allowed.")


class _Run:
    def __init__(self, r):
        self.r = r


@pytest.mark.parametrize("checks, verdict, lead", [
    ([{**SHOCK_ROW, "value": None, "n_episodes": 0}], "Tension",
     "Inside, with caveats: none of your limits broke; the shock check could not conclude (no close precedent)."),
    ([{**SHOCK_ROW, "n_episodes": 1}], "Tension",
     "Inside, with caveats: none of your limits broke; the shock check could not conclude (too few separate episodes)."),
    ([{**SHOCK_ROW, "value": None, "n_episodes": 0}], "Compatible",          # R51: the aliens card, never "a warning"
     "Inside your limits: none of your limits broke; the shock check could not conclude (no close precedent)."),
    ([{**SHOCK_ROW, "value": None, "n_episodes": 0}, {"rule": "risk_concentration", "tier": "warn", "status": "warn"}],
     "Compatible", "Inside your limits: no limit broke. One warning level was crossed, risk concentration, and a warning "
     "is not a limit."),
    ([{"rule": "single_stock", "tier": "soft", "status": "fail"}, SHOCK_ROW], "Tension",
     "Inside, with caveats: none of your hard limits broke; the mix after the move went past the one-company limit, "
     "a soft limit: a caution."),
    ([SHOCK_ROW], "Tension", "Inside, with caveats: none of your hard limits broke; the shock check raised the caution.")])
def test_the_code_lead_never_calls_an_abstention_a_caution_and_names_a_soft_limit_the_mix_went_past(checks, verdict, lead):
    r = {"verdict": verdict, "checks": checks, "metrics": {"after": {"max_drawdown": -0.2}}, "scenario": {}}
    said = pipeline._code_verdict(_Run(r))
    assert said == lead and "never broke" not in said


def test_no_floor_sentence_carries_the_capacitys_dollars():                 # bank juror: "beyond the -15.0 % ($90,000)"
    facts = {"T4": {"label": "Your floor", "value": -0.15, "unit": "pct", "entity": "your floor", "sign": "negative",
                    "kind": "assumption"},
             "T5": {"label": "What you can afford to lose", "value": -90000, "unit": "CAD", "entity": "your capacity",
                    "sign": "negative", "kind": "assumption"}}
    merged = verify.verify_numbers([{"text": "The mix went past your floor of 15.0 % [T4] ($90,000 [T5]).", "kind": "fact"}],
                                   facts)
    assert any("puts your capacity’s dollars beside your floor" in d for d in merged["defects"])
    apart = verify.verify_numbers([{"text": "Your floor is 15.0 % [T4]: no fall of more than that from any high.",
                                    "kind": "fact"}, {"text": "You could lose up to $90,000 [T5] of your capacity.",
                                                      "kind": "fact"}], facts)
    assert not any("beside your floor" in d for d in apart["defects"])
    from agents import explainer as ex
    assert "never put your capacity's dollars in a sentence about your floor" in ex.DEBRIEF_PROMPT


def test_the_lead_says_what_the_floor_meant_in_the_paths_own_dollars():       # the cold first-time user (17:50)
    facts = {"T54": {"label": "Your horizon", "value": 4, "unit": "years", "entity": "horizon", "sign": "positive",
                     "kind": "assumption"},
             "T202": {"label": "Your capacity line: your fictional amount less the capacity for loss in your profile "
                               "($90,000)", "value": 510000, "unit": "CAD", "entity": "your capacity", "sign": "positive",
                      "kind": "assumption"},
             "T206": {"label": "Lowest value of your mix with the move, on your fictional amount (2022-10-14)",
                      "value": 408174, "unit": "CAD", "entity": "after", "sign": "positive", "kind": "fiction"}}
    r = {"verdict": "Incompatible", "checks": [{"rule": "max_drawdown", "tier": "hard", "status": "fail"}], "scenario": {},
         "metrics": {"after": {"trough_date": "2022-10-14"}}, "facts": facts, "as_of": "2026-11-12",
         "capacity": {"line": 510000, "after": {"low_value": 408174, "low_date": "2022-10-14"}}}
    lead = pipeline._code_verdict(_Run(r))
    assert lead == ("Outside your limits: in Oct 2022 the mix with the move fell to $408,174 [T206], below your capacity "
                    "line of $510,000 [T202], and your horizon is 4 years [T54].")
    rc = verify.verify_numbers({"verdict_sentence": lead, "sentences": [], "sections": {}}, facts, as_of="2026-11-12",
                               result=r)
    assert rc["verified"] == rc["total"] == 3 and not [d for d in rc["defects"] if d.startswith("Sentence 1 ")]
    above = {**r, "capacity": {"line": 510000, "after": {"low_value": 538784, "low_date": "2022-10-11"}}}
    plain = "Outside your limits: the 2022 fall decided it; your floor broke with the mix after the move."
    assert pipeline._code_verdict(_Run(above)) == plain                      # the low stayed above the line
    assert pipeline._code_verdict(_Run({**r, "facts": {}})) == plain          # no row to cite: no number
