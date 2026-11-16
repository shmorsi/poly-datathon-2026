"""A move from one holding into another (Sun Nov 15, the lead: "which part of the portfolio would the 40 % replace? It
matters."): op move takes N % from A alone and adds it to T; a source that cannot pay for it is one plain question."""
import pytest

import pipeline
from agents import scenario as sc
from tools.portfolio import SourceShort, apply_change

ROBERT = {"XIU.TO": 0.45, "XBB.TO": 0.35, "GLD": 0.10, "ZST.TO": 0.10}
UNIV = [{"ticker": t, "name": n} for t, n in [("NVDA", "NVIDIA"), ("XIU.TO", "iShares S&P/TSX 60 Index ETF"),
        ("XBB.TO", "iShares Core Canadian Universe Bond Index ETF"), ("GLD", "SPDR Gold Shares"),
        ("ZST.TO", "BMO Ultra Short-Term Bond ETF"), ("BTC-USD", "Bitcoin")]]
MOVE = {"op": "move", "ticker": "NVDA", "weight": 0.40, "from_ticker": "XIU.TO"}


def test_move_takes_n_points_from_one_holding_and_adds_them_to_the_ticker():
    assert apply_change(ROBERT, MOVE) == pytest.approx({"XIU.TO": 0.05, "XBB.TO": 0.35, "GLD": 0.10, "ZST.TO": 0.10, "NVDA": 0.40})
    held = apply_change({"NVDA": 0.15, "XIU.TO": 0.85}, {**MOVE, "weight": 0.10})
    assert held == pytest.approx({"NVDA": 0.25, "XIU.TO": 0.75}) and sum(held.values()) == pytest.approx(1.0)
    with pytest.raises(SourceShort, match=r"XBB.TO is 35 % of your money; 40 % cannot come from there alone"):
        apply_change(ROBERT, {**MOVE, "from_ticker": "XBB.TO"})                       # never a silent clamp
    with pytest.raises(ValueError, match="not in the portfolio"):
        apply_change(ROBERT, {**MOVE, "from_ticker": "SPY", "weight": 0.1})
    with pytest.raises(ValueError, match="needs the holding"):
        apply_change(ROBERT, {**MOVE, "from_ticker": None})
    assert apply_change(ROBERT, {**MOVE, "op": "set", "from_ticker": None})["XIU.TO"] == pytest.approx(0.27)   # set: pro rata


@pytest.mark.parametrize("question, src", [
    ("What if I move 40 % of my money from my Canadian stocks into NVIDIA?", "XIU.TO"),
    ("Move 40 % from XIU into NVDA?", "XIU.TO"),
    ("What if I shift 40 % from my Canadian stocks to NVIDIA?", "XIU.TO"),
    ("Et si je déplaçais 40 % de mon argent de mes actions canadiennes vers NVIDIA ?", "XIU.TO"),
    ("Et si je transférais 40 % de mes obligations canadiennes dans NVIDIA ?", "XBB.TO")])
def test_the_keyword_rules_read_a_move_in_english_and_french(question, src):
    assert sc.read_move(question, UNIV, 600000) == {"kind": "change", "request": {"op": "move", "ticker": "NVDA",
                                                                                  "weight": 0.4, "from_ticker": src}}


def _plan(op="move", source="XIU.TO", weight=0.4):
    return {"type": "change", "families": [], "regions": [], "event_ids": [], "event_whys": None, "intent": None,
            "change": {"op": op, "ticker": "NVDA", "weight": weight, "from_ticker": source},
            "clarify_reason": None, "widened_from": None}


def _check(question, plan):
    return sc.validate_plan(plan, question=question, portfolio=ROBERT, catalog=[], universe=UNIV, seen={},
                            amount=600000, exposure={"countries": {}}, as_of="2026-11-12")


def test_the_navigators_plan_is_checked_like_the_other_ops_and_a_short_source_asks_one_question():
    fields, why = _check("What if I move 40 % of my money from my Canadian stocks into NVIDIA?", _plan())
    assert why is None and fields["change"] == MOVE and fields["portfolio"]["XIU.TO"] == pytest.approx(0.05)
    fr, why = _check("Et si je déplaçais 30 % de mes obligations canadiennes vers NVIDIA ?", _plan(source="XBB.TO", weight=0.3))
    assert why is None and fr["change"]["from_ticker"] == "XBB.TO" and fr["portfolio"]["XBB.TO"] == pytest.approx(0.05)
    short, why = _check("What if I move 40 % of my money from my Canadian bonds into NVIDIA?", _plan(source="XBB.TO"))
    assert why is None and short["clarify_reason"] == "source_short" and short["change"] is None
    assert short["clarify"] == ("Canadian bonds (XBB.TO) is 35 % of your money; 40 % can’t come from there alone. Take "
                                "the rest equally, or name another holding?")
    assert "You hold" not in short["clarify"]                                     # never "hold" as a verb (red gate 1)
    frs, _ = _check("Et si je déplaçais 40 % de mes obligations canadiennes vers NVIDIA ?", _plan(source="XBB.TO"))
    assert frs["clarify"].startswith("Canadian bonds (XBB.TO) is 35 % of your money;")     # the page is English
    wrong, why = _check("What if I move 40 % of my money from my Canadian stocks into NVIDIA?", _plan(source="XBB.TO"))
    assert why is None and wrong["clarify_reason"] == "ticker_unknown"           # the model's source is not the investor's
    kw = sc.keyword_fallback("What if I move 40 % of my money from my Canadian bonds into NVIDIA?", ROBERT, [], "2026-11-12",
                             universe=UNIV, exposure={"countries": {}}, amount=600000)
    assert kw["clarify_reason"] == "source_short" and kw["change"] is None
    assert pipeline._move_text(MOVE) == pipeline.verify.fmt_number(0.4, "pct") + " moved from XIU.TO into NVDA"
