"""Lane navcheck (Sun Nov 15): the navigator on real-world future-scenario questions, offline (no AWS call).

Three defects the live check of 14 questions found: a plan for "a big AI sell-off" was refused as advice ("sell" in the
investor's own noun), a rate-cut question could not abstain (the catalog's rate shocks are all rises), and the prompt
let "the US elections cause chaos" become tariffs and rates. The keyword fallback is untouched (ruling R10)."""
import agents.scenario as sc

UNIV = [{"ticker": t, "name": n} for t, n in (("XIU.TO", "iShares S&P/TSX 60 Index ETF"), ("XBB.TO", "iShares Core Canadian "
        "Universe Bond Index ETF"), ("GLD", "SPDR Gold Shares"), ("ZST.TO", "BMO Ultra Short-Term Bond ETF"),
        ("NVDA", "NVIDIA Corp"))]
ROBERT_W = {"XIU.TO": 0.45, "XBB.TO": 0.35, "GLD": 0.1, "ZST.TO": 0.1}
EXPO = {"countries": {"CAN": 0.8, "USA": 0.2}}


def _ev(event_id, date, family, sign="negative", regions=("USA",), title="t", description="d"):
    return {"event_id": event_id, "date": date, "title": title, "description": description, "family": family,
            "sign": sign, "episode": event_id, "regions": list(regions), "known": True}


CAT = [_ev("fed_75_2022", "2022-06-15", "rates", title="Fed raises rates by 0.75 point"),
       _ev("boc_100_2022", "2022-07-13", "rates", regions=("CAN",), title="Bank of Canada raises its rate by 1 point"),
       _ev("deepseek_2025", "2025-01-27", "chips", regions=("CHN", "USA"), title="DeepSeek AI shock"),
       _ev("ceasefire_2026", "2026-04-08", "war_oil", sign="positive", regions=("USA", "IRN"), title="Two-week ceasefire")]
ABSTAIN = {"type": "shock", "families": [], "regions": [], "event_ids": [], "event_whys": {}, "change": None,
           "intent": None, "clarify_reason": None, "widened_from": None}


def _validate(plan, question, seen=None):
    return sc.validate_plan(plan, question=question, portfolio=ROBERT_W, catalog=sc.shock_catalog(CAT, question),
                            universe=UNIV, seen=seen or {}, exposure=EXPO, as_of="2026-11-12")


def test_a_sell_off_is_the_investors_market_noun_not_an_advice_word():
    for s in ("test an AI sell-off", "AI sell off risk", "chip sell-offs", "a selloff in AI"):
        assert not sc._ADVICE.search(s), s
    for s in ("sell NVIDIA", "you should wait", "buy more chips", "hold the line", "should I sell?"):
        assert sc._ADVICE.search(s), s


def test_a_plan_for_an_ai_sell_off_is_used_not_refused_as_advice():
    q = "What if there's a big AI sell-off?"
    row = sc.search_events(q, family="chips", catalog=CAT, exposure=EXPO)[0]
    plan = {**ABSTAIN, "families": ["chips"], "event_ids": ["deepseek_2025"], "intent": "test an AI sell-off",
            "event_whys": {"deepseek_2025": "a chip sell-off driven by an AI model"}}
    out, why = _validate(plan, q, seen={"deepseek_2025": row})
    assert why is None and "chips" in out["families"] and out["event_ids"] == ["deepseek_2025"]   # widened: one chip episode
    assert out["intent"] == "test an AI sell-off"
    bad, why = _validate({**plan, "intent": "sell your chip stocks"}, q, seen={"deepseek_2025": row})
    assert bad is None and why == "the plan used advice words or markup"                  # advice is still refused


def test_a_rate_cut_question_may_abstain_when_every_rate_event_is_a_rise():
    q = "What if the Fed cuts rates to zero?"
    assert sc.asks_for_relief(q)
    out, why = _validate(ABSTAIN, q)
    assert why is None and out["weather"]["no_precedent"] is True and out["event_ids"] == []
    rise = "What if rates go extremely high again?"                              # a rise still has its precedents
    out, why = _validate(ABSTAIN, rise)
    assert out is None and why == "the navigator said no precedent but the catalog has some"
    calm = "What if a ceasefire holds in the war?"                               # relief asked, a relief event on record
    out, why = _validate(ABSTAIN, calm)
    assert out is None and why == "the navigator said no precedent but the catalog has some"


def test_the_prompt_names_elections_and_the_rate_cut_and_stays_static():
    p = sc.NAVIGATOR_PROMPT
    assert "(a pandemic, an election, a solar storm) has no close precedent" in p
    assert "Choose a family only for a shock the words name; rate rises are no precedent for a rate cut." in p
    assert len(p + sc.CONVERSE_SUFFIX) / 4 < 1024              # still under the fallback model's cache minimum (test_agents)
    assert 'no close precedent: answer type "shock" with families [] and event_ids []' in p   # test_agents' pins kept
    assert "That is the answer, not a question." in p and "2026" not in p and "XIU" not in p


def test_the_keyword_fallback_is_unchanged_for_these_questions():                # ruling R10: never broadened here
    assert sc.families_from_text("What if there's a big AI sell-off?") == []
    assert sc.families_from_text("What happens to my money if the US elections cause chaos?") == []
    assert sc.families_from_text("What if Washington slaps new levies on Canadian goods?") == []
