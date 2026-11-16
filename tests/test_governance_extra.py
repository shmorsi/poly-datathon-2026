"""Workstream B rules-engine tests (plan B Tasks 4 and 5): limits, section 5 rows, verdict, check order, evaluate.

Offline and pure on synthetic markets; the real-data tests at the end skip without data/starter. the finance lead's finance
truth lives in tests/test_governance.py.
"""
import json
import re
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from governance import check_order, check_profile, count_fails, evaluate, fmt_pct, load_limits, verdict
from tools.data import make_market

LOW = {"goal": "preservation", "horizon_years": 4, "risk": "low", "esg": False, "crypto": False,
       "capacity": None, "reaction_2022": None}
ROBERT = {**LOW, "risk": None, "reaction_2022": "held", "capacity": 90_000}
UNI = [{"ticker": "NVDA", "asset_class": "equity", "sector": "Information Technology"},
       {"ticker": "XIU.TO", "asset_class": "etf_equity", "sector": "Broad market (Canada)"},
       {"ticker": "XBB.TO", "asset_class": "etf_bond", "sector": "Bonds (Canada aggregate)"},
       {"ticker": "CNQ.TO", "asset_class": "equity", "sector": "Energy"},
       {"ticker": "BTC-USD", "asset_class": "crypto", "sector": "Crypto asset"},
       {"ticker": "QQQ", "asset_class": "etf_equity", "sector": "Broad market (US tech)"}]


def _a(dd=-0.10, stress=-0.05, n=3, stocks=None, sectors=None, lt=True, **extra):
    m = {"max_drawdown": dd, "peak_date": "2021-11-29", "trough_date": "2022-10-14",
         "recovery_days": 200, "days_since_trough": 900}
    look = {"stocks": stocks or {}, "sectors": sectors or {}, "countries": {}, "esg_indirect": {},
            "coverage": {}, "snapshot": {}, "mode": "lookthrough"} if lt else None
    return {"metrics": m, "lookthrough": look, "universe": UNI, "esg_flags": {"CNQ.TO"},
            "scenario_stress": stress, "scenario_family": "Tariff war", "scenario_episodes": n, **extra}


def _row(checks, rule):
    return next(c for c in checks if c["rule"] == rule)


# ---- the plan's tests (Task 4, Step 1); recovery_days is the unrounded 486.6 (ledger section 10) ----

def test_capacity_binds_for_robert():
    lim = load_limits(ROBERT, amount=600_000)
    assert (lim["band"], lim["band_floor"], lim["capacity_floor"]) == ("moderate", -0.25, -0.15)
    assert (lim["floor"], lim["floor_source"], lim["scenario_stress"]) == (-0.15, "capacity", -0.075)
    assert lim["recovery_days"] == pytest.approx(486.6, abs=0.2) and lim["edited"] == []
    edited = load_limits(ROBERT, {"floor": -0.20}, amount=600_000)
    assert (edited["floor"], edited["scenario_stress"], edited["edited"]) == (-0.20, -0.10, ["floor"])
    assert load_limits(None) is None


def test_hard_fail_is_outside_with_dollars():
    checks = check_profile(ROBERT, {"XIU.TO": 1.0}, _a(dd=-0.345, amount=600_000, loss_dollars=207_012.4))
    row = _row(checks, "max_drawdown")
    assert set(row) == {"rule", "tier", "status", "value", "limit", "holding", "reason"}
    assert (row["tier"], row["status"], row["limit"]) == ("hard", "fail", -0.15)
    assert "34.5\u00a0%" in row["reason"] and "$" not in row["reason"]     # R35: the floor's reason carries no dollars
    assert "2021-11-29" in row["reason"] and "should" not in row["reason"]
    assert verdict(checks) == "Incompatible"
    no_dollars = _row(check_profile(ROBERT, {"XIU.TO": 1.0}, _a(dd=-0.345, amount=600_000)), "max_drawdown")
    assert "$207" not in no_dollars["reason"]                     # dollars only when given (evaluate supplies them)


def test_float_noise_at_limits_passes():
    stocks = {"NVDA": {"direct": 0.1000000001, "via": [], "total": 0.1000000001}}
    checks = check_profile(LOW, {"NVDA": 0.1, "XIU.TO": 0.9},
                           _a(dd=-0.1500004, stress=-0.075, stocks=stocks, sectors={"Information Technology": 0.30000001}))
    assert all(c["status"] == "pass" for c in checks if c["tier"] != "warn") and verdict(checks) == "Compatible"


def test_one_cause_one_fail():
    stocks = {"NVDA": {"direct": 0.40, "via": [], "total": 0.40}}
    checks = check_profile(LOW, {"NVDA": 0.4, "XIU.TO": 0.6}, _a(stocks=stocks, sectors={"Information Technology": 0.40}))
    assert _row(checks, "single_stock")["holding"] == _row(checks, "sector")["holding"] == "NVDA"
    assert count_fails(checks) == 1 and verdict(checks) == "Tension"


def test_scenario_stress_no_precedent_too_few_and_caution():
    # ledger 30 (Sat 23:35): the soft shock check is a warn ("Caution") beyond its threshold, never a fail
    assert _row(check_profile(LOW, {"XIU.TO": 1.0}, _a(stress=None, n=0)), "scenario_stress")["status"] == "warn"
    few = _row(check_profile(LOW, {"XIU.TO": 1.0}, _a(stress=-0.20, n=1)), "scenario_stress")
    assert few["status"] == "warn" and "too few separate episodes to conclude" in few["reason"]
    assert _row(check_profile(LOW, {"XIU.TO": 1.0}, _a(stress=-0.090, n=4)), "scenario_stress")["status"] == "warn"
    assert _row(check_profile(LOW, {"XIU.TO": 1.0}, _a(stress=-0.075, n=4)), "scenario_stress")["status"] == "pass"
    for n in (2, 4, 26):                                           # a breach is a Caution however many episodes back it
        assert _row(check_profile(LOW, {"XIU.TO": 1.0}, _a(stress=-0.30, n=n)), "scenario_stress")["status"] == "warn"


def test_recovery_warns_only_beyond_half_floor():
    for dd, expected in ((-0.05, "pass"), (-0.12, "warn")):
        a = _a(dd=dd)
        a["metrics"].update({"recovery_days": None, "days_since_trough": 900})
        assert _row(check_profile(LOW, {"XIU.TO": 1.0}, a), "recovery")["status"] == expected


def test_crypto_no_is_a_preference_fail():
    row = _row(check_profile(LOW, {"BTC-USD": 0.05, "XIU.TO": 0.95}, _a()), "crypto")
    assert (row["tier"], row["status"], row["limit"], row["holding"]) == ("preference", "fail", 0.0, "BTC-USD")


def test_risk_concentration_warn():
    a = _a(risk={"shares": {"NVDA": 0.86, "XIU.TO": 0.14}, "bets": 1.3})
    row = _row(check_profile(LOW, {"NVDA": 0.4, "XIU.TO": 0.6}, a), "risk_concentration")
    assert (row["tier"], row["status"], row["holding"]) == ("warn", "warn", "NVDA")
    flat = _a(risk={"shares": {"XIU.TO": 1.0}, "bets": 1.0, "degenerate": True})
    assert all(c["rule"] != "risk_concentration" for c in check_profile(LOW, {"XIU.TO": 1.0}, flat))


def test_past_date_exempts_broad_and_bond_etfs():
    checks = check_profile(LOW, {"XIU.TO": 0.6, "XBB.TO": 0.4}, _a(lt=False))
    assert _row(checks, "sector")["status"] == "pass" and verdict(checks) == "Compatible"


def test_no_profile_and_check_order():
    assert check_profile(None, {"XIU.TO": 1.0}, _a()) == [] and verdict([]) is None
    checks = check_profile(LOW, {"XIU.TO": 1.0}, _a(stress=-0.09, n=4))
    order = check_order(checks, LOW)
    assert order[:2] == ["scenario_stress", "max_drawdown"] and sorted(order) == sorted(c["rule"] for c in checks)
    growth = check_profile({**LOW, "goal": "growth"}, {"XIU.TO": 1.0}, _a(risk={"shares": {"XIU.TO": 0.3}, "bets": 3.0}))
    assert check_order(growth, {**LOW, "goal": "growth"})[0] == "risk_concentration" and check_order([], LOW) == []


def test_fmt_pct():
    assert fmt_pct(-0.345) == "−34.5\u00a0%" and fmt_pct(0.08) == "8.0\u00a0%"


# ---- limits: typed profile, tie, overrides, personas.json fallback (ledger sections 10 and 15) ----

MATEO = {"goal": "balance", "horizon_years": 10, "risk": "moderate", "esg": True, "crypto": False,
         "capacity": 62_500, "reaction_2022": "held"}
AMIRA = {"goal": "growth", "horizon_years": 15, "risk": "high", "esg": False, "crypto": True,
         "capacity": 36_000, "reaction_2022": "bought"}


@pytest.mark.parametrize("change", [
    {"goal": "speculation"}, {"goal": None}, {"horizon_years": 0}, {"horizon_years": 41}, {"horizon_years": 4.5},
    {"horizon_years": "4"}, {"horizon_years": True}, {"capacity": -1}, {"capacity": "90000"}, {"capacity": True},
    {"capacity": float("nan")}, {"reaction_2022": "panicked"}, {"risk": "extreme"}, {"esg": "yes"}, {"esg": None},
    {"crypto": 1}])
def test_typed_profile_fields_only_else_a_plain_error(change):
    with pytest.raises(ValueError) as caught:
        load_limits({**ROBERT, **change}, amount=600_000)
    message = str(caught.value)
    assert message.endswith(".") and "Traceback" not in message and "KeyError" not in message
    with pytest.raises(ValueError):
        check_profile({**ROBERT, **change}, {"XIU.TO": 1.0}, _a())      # check_profile never trusts a profile either


def test_typed_profile_accepts_every_allowed_value():
    for goal in ("growth", "balance", "preservation", "income"):
        for reaction in ("sold", "held", "bought", None):
            assert load_limits({**LOW, "goal": goal, "risk": None, "reaction_2022": reaction}) is not None or reaction is None
    for years in (1, 40):
        assert load_limits({**LOW, "horizon_years": years})["recovery_days"] == pytest.approx(years * 365 * 0.3333)
    assert load_limits({**LOW, "capacity": 0})["capacity_floor"] is None            # zero is "not given"
    assert load_limits({**LOW, "capacity": 12.5}, amount=100)["capacity_floor"] == -0.125


def test_no_band_means_limits_missing():
    nothing = {**LOW, "risk": None, "reaction_2022": None}
    assert load_limits(nothing) is None and check_profile(nothing, {"XIU.TO": 1.0}, _a()) == []


def test_band_from_the_2022_reaction_and_a_direct_pick_wins():
    for reaction, floor in (("sold", -0.15), ("held", -0.25), ("bought", -0.45)):
        assert load_limits({**LOW, "risk": None, "reaction_2022": reaction})["band_floor"] == floor
    assert load_limits({**LOW, "risk": "high", "reaction_2022": "sold"})["band"] == "high"


def test_a_tie_names_the_capacity_and_a_looser_capacity_names_the_band():
    tie = load_limits(MATEO, amount=250_000)                         # $62,500 of $250,000 = the moderate band's -25 %
    assert (tie["floor"], tie["floor_source"], tie["capacity_floor"]) == (-0.25, "capacity", -0.25)
    loose = load_limits({**ROBERT, "capacity": 200_000}, amount=600_000)
    assert (loose["floor"], loose["floor_source"]) == (-0.25, "band")
    no_amount = load_limits(ROBERT)                                  # a capacity needs an amount to become a floor
    assert (no_amount["floor"], no_amount["floor_source"], no_amount["capacity_floor"]) == (-0.25, "band", None)
    assert load_limits({**ROBERT, "capacity": None}, amount=600_000)["capacity_floor"] is None


def test_crypto_tier_and_the_other_limits_per_band():
    amira = load_limits(AMIRA, amount=80_000)
    assert (amira["crypto"], amira["crypto_tier"], amira["floor"], amira["floor_source"]) == (0.10, "soft", -0.45, "capacity")
    assert (amira["single_stock"], amira["sector"], amira["scenario_stress"]) == (0.20, 0.40, -0.225)
    no = load_limits({**AMIRA, "crypto": False}, amount=80_000)
    assert (no["crypto"], no["crypto_tier"]) == (0.0, "preference")
    lim = load_limits(ROBERT, amount=600_000)
    assert (lim["single_stock"], lim["sector"], lim["risk_share"], lim["esg_indirect_warn"],
            lim["short_horizon_years"]) == (0.10, 0.35, 0.5, 0.01, 3)


def test_overrides_replace_values_in_canonical_order_and_validate():
    out = load_limits(ROBERT, {"sector": 0.5, "floor": -0.30, "risk_share": None}, amount=600_000)
    assert out["edited"] == ["floor", "sector"] and out["sector"] == 0.5 and out["floor"] == -0.30
    assert out["scenario_stress"] == -0.15 and out["floor_source"] == "capacity"       # the profile's source stays
    both = load_limits(ROBERT, {"floor": -0.30, "scenario_stress": -0.05}, amount=600_000)
    assert both["scenario_stress"] == -0.05                                           # an explicit edit wins
    for bad in ({"floor": "x"}, {"floor": 0.2}, {"sector": 1.5}, {"recovery_days": -1}, {"crypto": True}):
        with pytest.raises(ValueError):
            load_limits(ROBERT, bad, amount=600_000)


def test_limits_fall_back_key_by_key_when_personas_json_lacks_them(tmp_path, monkeypatch):
    import config
    partial = tmp_path / "personas.json"
    partial.write_text('{"risk_levels": {"low": {"max_drawdown": -0.12, "max_single_stock": "ten"}}, '
                       '"thresholds": {"short_horizon_years": 5}}', encoding="utf-8")
    monkeypatch.setattr(config, "PERSONAS_JSON", partial)
    lim = load_limits(LOW)
    assert lim["floor"] == -0.12 and lim["single_stock"] == 0.10 and lim["sector"] == 0.30   # file, then default
    assert lim["short_horizon_years"] == 5 and lim["risk_share"] == 0.5
    monkeypatch.setattr(config, "PERSONAS_JSON", tmp_path / "missing.json")
    assert load_limits(LOW)["floor"] == -0.15                                               # no file: all defaults
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(config, "PERSONAS_JSON", broken)
    assert load_limits(LOW)["floor"] == -0.15


# ---- rows and reasons ----

ADVICE = __import__("re").compile(r"\b(buy|sell|hold|held|holding|holds|should)\b", __import__("re").I)


def _rows(profile, weights, **kw):
    return check_profile(profile, weights, _a(**kw))


def test_rows_come_in_rule_id_order_and_values_rows_need_esg_yes():
    import config
    a = _a(risk={"shares": {"XIU.TO": 0.3}, "bets": 3.0}, missing_data=["BTC-USD"])
    for profile, expect_esg in ((LOW, False), ({**LOW, "esg": True}, True)):
        rules = [c["rule"] for c in check_profile(profile, {"XIU.TO": 1.0}, a)]
        assert rules == [r for r in config.RULE_IDS if expect_esg or not r.startswith("esg")]
        assert all(set(c) == {"rule", "tier", "status", "value", "limit", "holding", "reason"} for c in
                   check_profile(profile, {"XIU.TO": 1.0}, a))
    no_look = [c["rule"] for c in check_profile({**LOW, "esg": True}, {"XIU.TO": 1.0}, _a(lt=False))]
    assert "esg_direct" in no_look and "esg_indirect" not in no_look           # indirect needs the look-through
    plain = [c["rule"] for c in check_profile(LOW, {"XIU.TO": 1.0}, _a())]
    assert "risk_concentration" not in plain and "missing_data" not in plain   # optional keys absent: no row
    assert "scenario_stress" not in [c["rule"] for c in check_profile(
        LOW, {"XIU.TO": 1.0}, {k: v for k, v in _a().items() if not k.startswith("scenario")})]


def test_tiers_per_rule():
    tiers = {c["rule"]: c["tier"] for c in check_profile(
        {**LOW, "esg": True}, {"XIU.TO": 1.0}, _a(risk={"shares": {"XIU.TO": 0.3}}, missing_data=["XBB.TO"]))}
    assert tiers == {"max_drawdown": "hard", "scenario_stress": "soft", "single_stock": "soft", "sector": "soft",
                     "crypto": "preference", "esg_direct": "hard", "esg_indirect": "warn",
                     "risk_concentration": "warn", "recovery": "warn", "short_horizon": "warn", "missing_data": "warn"}
    amira = {c["rule"]: c["tier"] for c in check_profile(AMIRA, {"XIU.TO": 1.0}, _a())}
    assert amira["crypto"] == "soft"


def test_drawdown_reasons_name_the_source_of_the_floor():
    fail = _row(check_profile(ROBERT, {"XIU.TO": 1.0}, _a(dd=-0.345, loss_dollars=207_012.4, amount=600_000)),
                "max_drawdown")["reason"]
    assert fail == ("In this history the mix's worst drop was −34.5\u00a0% from 2021-11-29 to 2022-10-14, "
                    "beyond the −15.0\u00a0% floor from what you said you could lose.")     # R35: no dollars on the % rule
    band = _row(check_profile({**LOW, "risk": "moderate"}, {"XIU.TO": 1.0}, _a(dd=-0.30)), "max_drawdown")["reason"]
    assert band.endswith("beyond the −25.0\u00a0% floor of your tolerance band.") and "$" not in band
    edited = check_profile(ROBERT, {"XIU.TO": 1.0}, _a(dd=-0.30, limits=load_limits(ROBERT, {"floor": -0.2}, amount=600_000)))
    assert _row(edited, "max_drawdown")["reason"].endswith("beyond the −20.0\u00a0% floor you set.")
    ok = _row(check_profile(LOW, {"XIU.TO": 1.0}, _a(dd=-0.10)), "max_drawdown")
    assert ok["status"] == "pass" and ok["reason"].endswith("inside the −15.0\u00a0% floor you set.")


def test_a_drop_beyond_the_floor_fails_only_after_rounding():
    for dd, status in ((-0.15049, "pass"), (-0.1505, "fail"), (-0.15051, "fail"), (-0.1499, "pass")):
        assert _row(_rows(LOW, {"XIU.TO": 1.0}, dd=dd), "max_drawdown")["status"] == status, dd


def test_scenario_stress_reasons_carry_the_family_the_count_and_the_label():
    fail = _row(_rows(LOW, {"XIU.TO": 1.0}, stress=-0.09, n=4, scenario_label="Indicative (mixed with h20_2025)"),
                "scenario_stress")
    assert (fail["tier"], fail["status"]) == ("soft", "warn") and (fail["value"], fail["limit"]) == (-0.09, -0.075)
    assert fail["reason"] == ("In the 4 separate earlier Tariff war episodes the worst clean one cost 9.0\u00a0%, beyond half "
                              "your floor (7.5\u00a0%) (Indicative (mixed with h20_2025)).")
    measured = _row(_rows(LOW, {"XIU.TO": 1.0}, stress=-0.05, n=4, scenario_label="Measured"), "scenario_stress")
    assert measured["status"] == "pass" and "Measured" not in measured["reason"] and "inside half" in measured["reason"]
    none = _row(_rows(LOW, {"XIU.TO": 1.0}, stress=None, n=0), "scenario_stress")
    assert "no close precedent at this date" in none["reason"] and none["tier"] == "soft" and none["value"] is None
    assert "no close precedent" in _row(_rows(LOW, {"XIU.TO": 1.0}, stress=None, n=1), "scenario_stress")["reason"]
    # a value with no clean episode (as_of 2025-01-31: only a mixed episode counted) is "too few", not "no precedent"
    zero = _row(_rows(LOW, {"XIU.TO": 1.0}, stress=-0.05, n=0, scenario_label="Indicative (mixed with h20_2025)"),
                "scenario_stress")
    assert zero["status"] == "warn" and "no close precedent" not in zero["reason"]
    assert zero["reason"] == ("No clean Tariff war episodes are known at this date (Indicative (mixed with h20_2025)): "
                              "too few separate episodes to conclude.")
    one = _row(_rows(LOW, {"XIU.TO": 1.0}, stress=-0.05, n=1), "scenario_stress")
    assert one["reason"] == "Only 1 clean Tariff war episode is known at this date: too few separate episodes to conclude."
    unknown_count = {k: v for k, v in _a(stress=-0.09).items() if k != "scenario_episodes"}
    assert _row(check_profile(LOW, {"XIU.TO": 1.0}, unknown_count), "scenario_stress")["status"] == "warn"


def test_single_stock_and_sector_use_the_look_through_and_name_the_cause():
    stocks = {"NVDA": {"direct": 0.15, "via": [{"etf": "QQQ", "weight": 0.03}], "total": 0.18},
              "CNQ.TO": {"direct": 0.0, "via": [], "total": 0.05}}
    sectors = {"Information Technology": 0.31, "Energy": 0.05, "Bonds": 0.60, "Broad market": 0.99}
    rows = _rows(LOW, {"NVDA": 0.15, "XIU.TO": 0.85}, stocks=stocks, sectors=sectors)
    one, sector = _row(rows, "single_stock"), _row(rows, "sector")
    assert (one["status"], one["holding"], one["value"], one["limit"]) == ("fail", "NVDA", 0.18, 0.10)
    assert one["reason"] == "NVDA is 18.0\u00a0% of the money, beyond the 10\u00a0% limit for one company."
    assert (sector["status"], sector["holding"], sector["value"]) == ("fail", "NVDA", 0.31)   # Bonds/Broad: not sectors
    assert sector["reason"] == "Information Technology is 31.0\u00a0% of the money, beyond the 30\u00a0% limit for one sector."
    empty = _rows(LOW, {"XIU.TO": 1.0})
    assert (_row(empty, "single_stock")["status"], _row(empty, "single_stock")["holding"]) == ("pass", None)
    assert (_row(empty, "sector")["value"], _row(empty, "sector")["holding"]) == (0.0, None)


def test_past_dates_use_direct_equities_and_gics_funds_only():
    past = _a(lt=False)
    rows = check_profile(LOW, {"NVDA": 0.4, "XIU.TO": 0.4, "BTC-USD": 0.2}, past)
    assert (_row(rows, "single_stock")["value"], _row(rows, "single_stock")["holding"]) == (0.4, "NVDA")
    assert (_row(rows, "sector")["value"], _row(rows, "sector")["holding"]) == (0.4, "NVDA")
    uni = [*UNI, {"ticker": "XLK", "asset_class": "etf_equity", "sector": "Information Technology"}]
    funds = check_profile(LOW, {"XLK": 0.5, "XBB.TO": 0.5}, {**past, "universe": uni})
    assert _row(funds, "sector")["value"] == 0.5 and _row(funds, "single_stock")["value"] == 0.0


def test_crypto_soft_cap_and_preference_wording():
    amira = _row(check_profile(AMIRA, {"BTC-USD": 0.15, "XIU.TO": 0.85}, _a()), "crypto")
    assert (amira["tier"], amira["status"], amira["limit"], amira["value"]) == ("soft", "fail", 0.10, 0.15)
    assert amira["reason"] == "Crypto is 15.0\u00a0% of the money, beyond the 10\u00a0% limit."
    pref = _row(_rows(LOW, {"BTC-USD": 0.05, "XIU.TO": 0.95}), "crypto")
    assert pref["reason"] == "BTC-USD makes crypto 5.0\u00a0% of the money, but you said no to crypto."
    none = _row(_rows(LOW, {"XIU.TO": 1.0}), "crypto")
    assert (none["status"], none["value"], none["holding"]) == ("pass", 0, None)


def test_values_rules_direct_fails_indirect_warns_at_one_percent():
    esg = {**LOW, "esg": True}
    a = _a(stocks={"CNQ.TO": {"direct": 0.08, "via": [], "total": 0.08}})
    a["lookthrough"]["esg_indirect"] = {"XOM": 0.0583}
    rows = check_profile(esg, {"CNQ.TO": 0.08, "XIU.TO": 0.92}, a)
    direct, indirect = _row(rows, "esg_direct"), _row(rows, "esg_indirect")
    assert (direct["tier"], direct["status"], direct["holding"], direct["limit"]) == ("hard", "fail", "CNQ.TO", 0.0)
    assert direct["value"] == pytest.approx(0.08) and "CNQ.TO is owned directly (8.0\u00a0% of the money)" in direct["reason"]
    assert (indirect["tier"], indirect["status"], indirect["holding"]) == ("warn", "warn", "XOM")
    for share, status in ((0.0094, "pass"), (0.0095, "warn"), (0.0099, "warn"), (0.0100, "warn")):   # after 0.1 pp rounding
        a["lookthrough"]["esg_indirect"] = {"XOM": share}
        assert _row(check_profile(esg, {"XIU.TO": 1.0}, a), "esg_indirect")["status"] == status, share
    clean = _row(check_profile(esg, {"XIU.TO": 1.0}, _a()), "esg_direct")
    assert (clean["status"], clean["holding"], clean["value"]) == ("pass", None, 0.0)
    assert "No company excluded by your values screen is owned directly" in clean["reason"]   # never a clean bill (ledger 20)
    assert "excluded by the values screen you asked for" in direct["reason"]
    assert "Companies excluded by your values screen add up to" in indirect["reason"]


def test_energy_sector_counts_as_excluded_even_when_not_in_the_flags():
    uni = [*UNI, {"ticker": "XOM", "asset_class": "equity", "sector": "Energy"}]
    a = {**_a(), "universe": uni, "esg_flags": set()}
    row = _row(check_profile({**LOW, "esg": True}, {"XOM": 0.05, "XIU.TO": 0.95}, a), "esg_direct")
    assert (row["status"], row["holding"]) == ("fail", "XOM")
    off = [c for c in check_profile(LOW, {"XOM": 0.05, "XIU.TO": 0.95}, a) if c["rule"].startswith("esg")]
    assert off == []


def test_risk_concentration_compares_after_rounding_and_skips_degenerate():
    for share, status in ((0.5004, "pass"), (0.5006, "warn"), (0.5, "pass"), (0.86, "warn")):
        row = _row(check_profile(LOW, {"XIU.TO": 1.0}, _a(risk={"shares": {"A": share, "B": 1 - share}})), "risk_concentration")
        assert row["status"] == status, share
    row = _row(check_profile(LOW, {"XIU.TO": 1.0}, _a(risk={"shares": {"NVDA": 0.86, "XIU.TO": 0.14}})), "risk_concentration")
    assert row["reason"] == "NVDA carries 86\u00a0% of the portfolio's risk, beyond the 50\u00a0% warning level."
    assert all(c["rule"] != "risk_concentration" for c in check_profile(LOW, {"XIU.TO": 1.0}, _a(risk={})))


def test_recovery_uses_the_unrounded_horizon_limit_and_the_right_day_count():
    def recovery(dd, rec, since=900, profile=LOW):
        a = _a(dd=dd)
        a["metrics"].update({"recovery_days": rec, "days_since_trough": since})
        return _row(check_profile(profile, {"XIU.TO": 1.0}, a), "recovery")
    slow = recovery(-0.12, 487)                                   # 4 years x 365 x 0.3333 = 486.618
    assert (slow["status"], slow["value"]) == ("warn", 487) and slow["limit"] == pytest.approx(486.618)
    # whole days only (ruling of Sat 22:30, ledger 29: "487 days", never "486.6 days"); the comparison stays unrounded
    # (ledger 10), so exactly 487 days is a fraction of a day beyond 486.618 and the sentence says so, never "487 beyond 487"
    assert slow["reason"] == ("The worst drop took 487 days to recover; your horizon gives about 487 days, so that was "
                              "a fraction of a day beyond it.")
    assert recovery(-0.12, 512)["reason"] == ("The worst drop took 512 days to recover; your horizon gives about 487 days, "
                                              "so that was beyond it.")
    assert recovery(-0.12, 486)["reason"] == ("The worst drop took 486 days to recover; your horizon gives about 487 days, "
                                              "so that was inside it.")
    assert recovery(-0.12, 486)["status"] == "pass"
    unrecovered = recovery(-0.12, None, since=900)
    assert unrecovered["status"] == "warn" and "900 days past its low and had not recovered" in unrecovered["reason"]
    assert recovery(-0.12, None, since=300)["status"] == "pass"
    shallow = recovery(-0.05, 5000)                               # not deeper than half the floor: never asked
    assert shallow["status"] == "pass" and "not deeper than half your floor (−7.5\u00a0%)" in shallow["reason"]
    assert recovery(-0.12, 500, profile={**LOW, "horizon_years": 10})["status"] == "pass"   # 10 y allows 1,216 days
    assert (shallow["tier"], shallow["holding"]) == ("warn", None)


def test_short_horizon_and_missing_data_rows():
    short = _row(check_profile({**LOW, "horizon_years": 2}, {"XIU.TO": 1.0}, _a()), "short_horizon")
    assert (short["status"], short["value"], short["limit"]) == ("warn", 2, 3)
    assert short["reason"] == "You need the money in 2 years, sooner than the 3-year short-horizon level."
    assert _row(check_profile({**LOW, "horizon_years": 3}, {"XIU.TO": 1.0}, _a()), "short_horizon")["status"] == "pass"
    one = _row(check_profile({**LOW, "horizon_years": 1}, {"XIU.TO": 1.0}, _a()), "short_horizon")
    assert "in 1 year," in one["reason"]
    gap = _row(check_profile(LOW, {"XIU.TO": 1.0}, _a(missing_data=["XBB.TO", "CNQ.TO"])), "missing_data")
    assert (gap["tier"], gap["status"], gap["value"]) == ("warn", "warn", 2)
    assert gap["reason"].startswith("CNQ.TO, XBB.TO have a price gap of more than 3 days")
    assert all(c["rule"] != "missing_data" for c in check_profile(LOW, {"XIU.TO": 1.0}, _a(missing_data=[])))


def test_verdict_tiers_and_warn_counting():
    def row(tier, status):
        return {"rule": "x", "tier": tier, "status": status, "value": 0, "limit": 0, "holding": None, "reason": "."}
    assert verdict([row("hard", "pass"), row("warn", "warn")]) == "Compatible"
    assert verdict([row("warn", "warn"), row("warn", "warn")]) == "Tension"
    assert verdict([row("soft", "warn"), row("warn", "warn")]) == "Tension"          # a soft row can warn too
    assert verdict([row("preference", "fail")]) == "Tension"
    assert verdict([row("soft", "fail"), row("hard", "fail")]) == "Incompatible"
    assert verdict([row("hard", "warn")]) == "Compatible"


def test_count_fails_counts_each_cause_once():
    def fail(holding):
        return {"rule": "x", "tier": "soft", "status": "fail", "value": 0, "limit": 0, "holding": holding, "reason": "."}
    assert count_fails([]) == 0
    assert count_fails([fail("NVDA"), fail("NVDA"), fail(None), fail(None), fail("BTC-USD")]) == 4
    passing = {**fail("NVDA"), "status": "pass"}
    assert count_fails([passing, fail("NVDA")]) == 1


def test_check_order_binding_row_then_goal_lead_then_fails_warns_passes():
    def order(profile, weights, **kw):
        checks = check_profile(profile, weights, _a(**kw))
        return check_order(checks, profile), checks
    # a hard fail binds first, even though the goal's lead is the same rule here
    got, checks = order(LOW, {"XIU.TO": 1.0}, dd=-0.30, stress=-0.20, n=4)
    assert got[:2] == ["max_drawdown", "scenario_stress"] and len(got) == len(set(got)) == len(checks)
    # a balance investor: the soft fail binds, then turbulence (the goal lead) comes right after it
    balance = {**LOW, "goal": "balance"}
    got, _ = order(balance, {"BTC-USD": 0.05, "XIU.TO": 0.95}, stress=-0.05)
    assert got[:2] == ["crypto", "scenario_stress"]
    # only warns: the first warn binds, then the goal lead, then the other warns, then the passes
    got, checks = order({**LOW, "horizon_years": 2}, {"XIU.TO": 1.0}, risk={"shares": {"NVDA": 0.9}})
    statuses = [next(c for c in checks if c["rule"] == r)["status"] for r in got]
    assert got[0] == "risk_concentration" and got[1] == "max_drawdown" and statuses[0] == "warn"
    assert statuses[2:] == sorted(statuses[2:], key={"fail": 0, "warn": 1, "pass": 2}.get)
    assert check_order(checks, None)[0] == "risk_concentration"                    # no profile: no goal lead


def test_no_reason_ever_gives_advice_or_uses_held_words():
    amira = check_profile(AMIRA, {"NVDA": 0.5, "BTC-USD": 0.2, "XIU.TO": 0.3}, _a(
        dd=-0.5, stress=-0.3, n=4, stocks={"NVDA": {"direct": 0.5, "via": [], "total": 0.5}},
        sectors={"Information Technology": 0.5}, risk={"shares": {"NVDA": 0.9}}, loss_dollars=40_000.0,
        missing_data=["NVDA"], amount=80_000))
    esg = check_profile({**MATEO, "horizon_years": 2}, {"CNQ.TO": 0.1, "XIU.TO": 0.9}, _a(
        stocks={"CNQ.TO": {"direct": 0.1, "via": [], "total": 0.1}}, stress=None, n=0, amount=250_000))
    assert len(amira) >= 9 and len(esg) >= 9
    for row in [*amira, *esg]:
        assert row["reason"].endswith(".") and not ADVICE.search(row["reason"]), row


# ---- esg flags as known at a date (ruling of Sat 20:40: category flags always, controversy flags by filing date) ----

ESG_CSV = ("ticker,flag,reason_en,reason_fr,source_url,source_date\n"
           "CNQ.TO,fossil_reserves,x,y,https://example.org/esgv,2026-11-14\n"
           "ENB.TO,fuel_pipelines,x,y,https://example.org/esgv,2026-11-14\n"
           "TSLA,controversy_social,x,y,https://example.org/10k,2025-02-05\n"
           "XOM,controversy_env,x,y,https://example.org/10k,2026-02-20\n"
           "MSFT,controversy_env,x,y,https://example.org/10k,\n")


def test_category_flags_apply_at_every_date_and_controversy_flags_wait_for_their_filing(tmp_path):
    from governance import load_esg_flags
    path = tmp_path / "esg_flags.csv"
    path.write_text(ESG_CSV, encoding="utf-8")
    assert load_esg_flags("2021-11-12", path=path) == {"CNQ.TO", "ENB.TO"}              # the sources are dated later: still apply
    assert load_esg_flags("2025-02-04", path=path) == {"CNQ.TO", "ENB.TO"}
    assert load_esg_flags("2025-02-05", path=path) == {"CNQ.TO", "ENB.TO", "TSLA"}       # filed that day: known
    assert load_esg_flags("2026-11-12", path=path) == {"CNQ.TO", "ENB.TO", "TSLA", "XOM"}  # MSFT: no filing date, no flag


def test_esg_flags_old_schema_missing_file_and_bad_date(tmp_path):
    from governance import load_esg_flags
    old = tmp_path / "old.csv"
    old.write_text("ticker,flag,reason_fr,source_url\nCNQ.TO,energie_fossile,x,dataset:assets_universe.csv#sector\n",
                   encoding="utf-8")
    assert load_esg_flags("2022-01-03", path=old) == {"CNQ.TO"}                         # no source_date column: category rows
    assert load_esg_flags("2026-11-12", path=tmp_path / "nope.csv") == set()
    for bad in ("12 Nov 2026", "", None, 20261112):
        with pytest.raises(ValueError):
            load_esg_flags(bad, path=old)


def test_the_real_esg_file_follows_the_same_rule_at_every_date():
    import csv

    import config
    from governance import load_esg_flags
    with open(config.ESG_FLAGS_CSV, encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    category = {r["ticker"] for r in rows if not r["flag"].startswith("controversy_")}
    listed = {r["ticker"] for r in rows}
    assert "CNQ.TO" in category                                       # the oil producer, in either file schema
    assert load_esg_flags("2021-11-12") == category                   # no filing is known yet: category flags only
    today = load_esg_flags("2026-11-12")
    assert category <= today <= listed                                # later dates know more, never fewer


# ---- helpers, constants, and the numbers other files repeat ----

def test_round_pp_and_money_helpers():
    from governance import fmt_money, round_pp
    assert (round_pp(-0.1500004), round_pp(0.08), round_pp(0.0)) == (Decimal("-15.0"), Decimal("8.0"), Decimal("0.0"))
    assert round_pp(0.12345) == Decimal("12.3") and round_pp(0.12349) == Decimal("12.3")
    assert round_pp(-0.1505) == Decimal("-15.1") and round_pp(0.1505) == Decimal("15.1")      # half up, away from zero
    assert round_pp(-0.15049) == Decimal("-15.0") and isinstance(round_pp(1), Decimal)
    assert fmt_money(207000.4) == "$207,000" and fmt_money(207000.5) == "$207,001" and fmt_money(-90000) == "−$90,000"
    assert fmt_money(0) == "$0" and fmt_pct(0.0) == "0.0\u00a0%" and fmt_pct(-0.15) == "−15.0\u00a0%" and fmt_pct(0.1) == "10.0\u00a0%"
    assert fmt_pct(-0.0004) == "0.0\u00a0%" and fmt_pct(-0.0005) == "−0.1\u00a0%"                  # no negative zero


def test_constants_the_checklist_shares_with_the_rest_of_the_project():
    import config
    import governance
    from scripts import create_guardrail
    assert len(governance.GICS_SECTORS) == len(set(governance.GICS_SECTORS)) == 11
    assert {"Energy", "Information Technology", "Health Care"} <= set(governance.GICS_SECTORS)
    assert governance.GOAL_LEAD == {"preservation": "max_drawdown", "income": "max_drawdown",
                                    "balance": "scenario_stress", "growth": "risk_concentration"}
    assert set(governance.GOAL_LEAD.values()) <= set(config.RULE_IDS)
    # the Automated Reasoning text (scripts/create_guardrail.py) repeats these two numbers: they must not drift
    assert create_guardrail.MIN_SHOCK_EPISODES == governance.MIN_SHOCK_EPISODES == 2
    assert create_guardrail.PRICE_GAP_DAYS == governance.PRICE_GAP_DAYS == 3
    assert [rule for rule, _ in governance._RULES] == list(config.RULE_IDS)


def test_limits_default_to_the_spec_5_table_and_match_personas_json():
    import config
    for band, floor in (("low", -0.15), ("moderate", -0.25), ("high", -0.45)):
        lim = load_limits({**LOW, "risk": band})
        assert lim["band_floor"] == floor == config.DEFAULT_LIMITS[band]["max_drawdown"]
        assert lim["scenario_stress"] == pytest.approx(floor / 2)
        assert lim["single_stock"] == config.DEFAULT_LIMITS[band]["max_single_stock"]
        assert lim["sector"] == config.DEFAULT_LIMITS[band]["max_sector"]


def test_check_profile_prefers_the_limits_it_is_given_and_never_mutates_its_inputs():
    import copy
    edits = load_limits(LOW, {"single_stock": 0.5})
    stocks = {"NVDA": {"direct": 0.3, "via": [], "total": 0.3}}
    a = _a(stocks=stocks, limits=edits)
    weights = {"NVDA": 0.3, "XIU.TO": 0.7}
    before = copy.deepcopy((LOW, weights, a))
    rows = check_profile(LOW, weights, a)
    assert _row(rows, "single_stock")["status"] == "pass" and _row(rows, "single_stock")["limit"] == 0.5
    assert (LOW, weights, a) == before
    assert check_profile(LOW, weights, a) == rows                                       # deterministic: same inputs, same rows


# ---- Task 4 fix round 1: full limits dicts as overrides, honest pass rows, wording ----

def test_a_full_limits_dict_is_accepted_and_only_real_edits_count():
    """pipeline.recheck(r, {**r["limits"], "floor": -0.60}) and the sensitivity scan {**limits, "floor": f}."""
    base = load_limits(ROBERT, amount=600_000)
    out = load_limits(ROBERT, {**base, "floor": -0.60}, amount=600_000)             # the recheck call, nothing raises
    assert (out["floor"], out["edited"]) == (-0.60, ["floor"])
    assert out["scenario_stress"] == -0.30                                          # follows the floor, not pinned at -0.075
    assert out["floor_source"] == "capacity" and out["band"] == "moderate"          # derived keys come from the profile
    assert {k: out[k] for k in ("single_stock", "sector", "crypto", "recovery_days", "risk_share")} == \
        {k: base[k] for k in ("single_stock", "sector", "crypto", "recovery_days", "risk_share")}
    assert load_limits(ROBERT, dict(base), amount=600_000) == base                  # an untouched full dict is no edit


def test_a_full_limits_dict_keeps_earlier_edits_and_does_not_pin_the_derived_stress():
    earlier = load_limits(ROBERT, {"sector": 0.5, "floor": -0.30}, amount=600_000)   # edited ["floor", "sector"]
    assert (earlier["scenario_stress"], earlier["edited"]) == (-0.15, ["floor", "sector"])
    scan = load_limits(ROBERT, {**earlier, "floor": -0.20}, amount=600_000)          # the scan moves the floor again
    assert (scan["floor"], scan["scenario_stress"], scan["sector"]) == (-0.20, -0.10, 0.5)
    assert scan["edited"] == ["floor", "sector"]
    pinned = load_limits(ROBERT, {**earlier, "scenario_stress": -0.05, "edited": ["floor", "scenario_stress"]},
                         amount=600_000)                                              # listed in edited: it IS an edit
    assert (pinned["floor"], pinned["scenario_stress"]) == (-0.30, -0.05)
    assert pinned["edited"] == ["floor", "sector", "scenario_stress"] and pinned["sector"] == 0.5   # a changed value is never dropped


def test_keys_outside_the_seven_are_ignored_but_the_seven_are_still_validated():
    base = load_limits(ROBERT, amount=600_000)
    ignored = load_limits(ROBERT, {"max_drawdown": -0.2, "nonsense": 1, "band": "high", "edited": []}, amount=600_000)
    assert ignored == base
    for bad in ({**base, "floor": "x"}, {**base, "sector": 2.0}, {**base, "floor": 0.1}):
        with pytest.raises(ValueError):
            load_limits(ROBERT, bad, amount=600_000)


def test_override_errors_use_the_minus_sign_and_plain_names():
    messages = []
    for bad in ({"floor": 0.2}, {"scenario_stress": 0.1}, {"sector": 1.5}, {"risk_share": -0.1}, {"recovery_days": -5},
                {"single_stock": "ten"}):
        with pytest.raises(ValueError) as caught:
            load_limits(ROBERT, bad, amount=600_000)
        messages.append(str(caught.value))
    for text in messages:
        assert text.endswith(".") and "_" not in text and not __import__("re").search(r"-\d", text), text
    assert "−100\u00a0% and 0\u00a0%" in messages[0] and "one-sector limit" in messages[2]
    assert "floor" in messages[0] and "shock-check limit" in messages[1] and "risk-share warning level" in messages[3]


def test_a_capacity_needs_a_positive_amount_to_become_a_floor():
    for amount in (0, -1, -600_000, None):
        lim = load_limits(ROBERT, amount=amount)
        assert (lim["capacity_floor"], lim["floor"], lim["floor_source"]) == (None, -0.25, "band"), amount


def test_every_verdict_is_a_key_of_the_ui_words():
    import config
    def row(tier, status):
        return {"rule": "x", "tier": tier, "status": status, "value": 0, "limit": 0, "holding": None, "reason": "."}
    outs = {verdict([]), verdict([row("hard", "fail")]), verdict([row("soft", "fail")]), verdict([row("hard", "pass")])}
    assert outs == {None, "Incompatible", "Tension", "Compatible"} == set(config.VERDICT_WORDS)


def test_a_sliver_of_an_excluded_name_or_of_crypto_is_not_claimed_as_held():
    sliver = 0.0004                                                                 # 0.04 %: rounds to 0.0 %
    esg = check_profile({**LOW, "esg": True}, {"CNQ.TO": sliver, "XIU.TO": 1 - sliver}, _a())
    direct = _row(esg, "esg_direct")
    assert (direct["status"], direct["holding"], direct["value"]) == ("pass", "CNQ.TO", pytest.approx(sliver))
    assert "owned directly" not in direct["reason"] and "under 0.05\u00a0%" in direct["reason"] and "CNQ.TO" in direct["reason"]
    coin = _row(check_profile(LOW, {"BTC-USD": sliver, "XIU.TO": 1 - sliver}, _a()), "crypto")
    assert coin["status"] == "pass" and "No crypto is in the mix" not in coin["reason"] and "under 0.05\u00a0%" in coin["reason"]
    amira = _row(check_profile(AMIRA, {"BTC-USD": sliver, "XIU.TO": 1 - sliver}, _a()), "crypto")
    assert amira["status"] == "pass" and "under 0.05\u00a0%" in amira["reason"]
    real = _row(check_profile({**LOW, "esg": True}, {"CNQ.TO": 0.0005, "XIU.TO": 0.9995}, _a()), "esg_direct")
    assert real["status"] == "fail" and "owned directly (0.1\u00a0% of the money)" in real["reason"]   # 0.05 % rounds up: counts


def test_esg_indirect_says_so_when_the_funds_were_not_looked_through():
    direct_mode = _a()
    direct_mode["lookthrough"]["mode"] = "direct"                                   # fresh clone: no holdings file
    row = _row(check_profile({**LOW, "esg": True}, {"XIU.TO": 1.0}, direct_mode), "esg_indirect")
    # ledger 30 (B Task 5 review): unknown is never a pass, so a held fund that was not opened makes this row a warn, no value
    assert (row["status"], row["tier"], row["value"], row["limit"], row["holding"]) == ("warn", "warn", None, 0.01, None)
    assert row["reason"] == ("The 1\u00a0% warning level for excluded companies inside your funds cannot be checked: XIU.TO "
                             "was not looked through, so the companies inside it are not known from holdings.")
    assert verdict(check_profile({**LOW, "esg": True}, {"XIU.TO": 1.0}, direct_mode)) == "Tension"
    # a bond fund has no company inside it to be unknown: the row reads as it does after a real look-through
    bond = check_profile({**LOW, "esg": True}, {"XBB.TO": 1.0}, direct_mode)
    assert verdict(bond) == "Compatible" and "looked through" not in _row(bond, "esg_indirect")["reason"]
    assert (_row(bond, "esg_indirect")["status"], _row(bond, "esg_indirect")["value"]) == ("pass", 0)
    normal = _row(check_profile({**LOW, "esg": True}, {"XIU.TO": 1.0}, _a()), "esg_indirect")
    assert normal["value"] == 0 and "inside your funds" in normal["reason"]


def test_the_shock_check_counts_separate_earlier_episodes():
    for n, words in ((5, "In the 5 separate earlier Tariff war episodes"), (None, "In the separate earlier Tariff war episodes")):
        a = {k: v for k, v in _a(stress=-0.05).items() if k != "scenario_episodes" or n is not None}
        if n is not None:
            a["scenario_episodes"] = n
        assert words in _row(check_profile(LOW, {"XIU.TO": 1.0}, a), "scenario_stress")["reason"]


# ---- Task 5: governance.evaluate, the one judge (plan B Task 5; the three plan tests, verbatim) ----

KEYS = {"weights", "series", "metrics", "worst_rolling", "stress", "turbulence", "lookthrough", "exposure",
        "risk", "diversification", "analysis", "checks", "verdict", "kpis", "limits"}


def _market():
    dates = pd.bdate_range("2024-01-01", periods=260)
    down = [100 - 0.4 * i for i in range(51)]                    # 100 -> 80: a 20 % drop
    up = [80 + 0.4 * i for i in range(1, 51)]                    # back to 100
    aaa = (down + up + [100.0] * 260)[:260]
    prices = pd.DataFrame({"AAA": aaa, "BBB": [50.0] * 260}, index=dates)
    uni = pd.DataFrame([
        {"ticker": "AAA", "name": "Synthetic A", "asset_class": "equity", "market": "TSX", "currency": "CAD",
         "sector": "Industrials", "country": "CAN"},
        {"ticker": "BBB", "name": "Synthetic B", "asset_class": "etf_bond", "market": "TSX", "currency": "CAD",
         "sector": "Bonds (Canada aggregate)", "country": "CAN"}])
    return make_market(prices, universe=uni, as_of=dates[-1].strftime("%Y-%m-%d")), dates[-1].strftime("%Y-%m-%d")


def test_evaluate_judges_with_the_floor_and_no_storms():
    m, as_of = _market()
    out = evaluate(LOW, {"AAA": 1.0}, [], as_of, market=m, events=[], today=False, amount=100_000)
    assert set(out) == KEYS and out["lookthrough"] is None
    assert out["metrics"]["max_drawdown"] == pytest.approx(-0.20, abs=1e-9)
    assert out["kpis"]["max_drawdown"] == {"value": pytest.approx(-0.20, abs=1e-9), "limit": -0.15}
    assert out["kpis"]["scenario_stress"]["value"] is None and out["kpis"]["scenario_stress"]["limit"] == -0.075
    row = next(c for c in out["checks"] if c["rule"] == "scenario_stress")
    assert row["status"] == "warn" and "no close precedent" in row["reason"]
    assert out["verdict"] == "Incompatible" and out["analysis"]["scenario_family"] == ""   # [] = no family (ledger 30), see below
    assert out["analysis"]["loss_dollars"] == pytest.approx(20_000)          # 100 -> 80 on $100,000, exact
    assert "$" not in next(c for c in out["checks"] if c["rule"] == "max_drawdown")["reason"]      # R35


def test_evaluate_without_profile_and_light_mode():
    m, as_of = _market()
    out = evaluate(None, {"AAA": 0.5, "BBB": 0.5}, ["chips"], as_of, market=m, events=[], today=False, detail=False)
    assert out["verdict"] is None and out["checks"] == [] and out["limits"] is None
    assert out["kpis"]["max_drawdown"]["limit"] is None
    assert out["turbulence"] is None and out["diversification"] is None
    assert out["analysis"]["scenario_family"] == "Chip war"


def test_limit_edit_moves_the_verdict():
    m, as_of = _market()
    out = evaluate(LOW, {"AAA": 1.0}, [], as_of, market=m, events=[], today=False, limits={"floor": -0.25})
    assert out["limits"]["edited"] == ["floor"]
    assert next(c for c in out["checks"] if c["rule"] == "max_drawdown")["status"] == "pass"


# ---- Task 5 rulings: sentences shown to the investor (Sat 22:30): U+00A0 before every %, whole days, no advice ----

NB = "\u00a0"


def _every_reason(**extra):
    """One row of every kind of sentence: failing, passing, warning and the caveat row."""
    amira = check_profile(AMIRA, {"NVDA": 0.5, "BTC-USD": 0.2, "XIU.TO": 0.3}, _a(
        dd=-0.5, stress=-0.3, n=4, stocks={"NVDA": {"direct": 0.5, "via": [], "total": 0.5}},
        sectors={"Information Technology": 0.5}, risk={"shares": {"NVDA": 0.9}}, loss_dollars=40_000.0,
        missing_data=["NVDA"], amount=80_000, **extra))
    esg = check_profile({**MATEO, "horizon_years": 2}, {"CNQ.TO": 0.0004, "XIU.TO": 0.9996}, _a(
        stress=None, n=0, amount=250_000, **extra))
    sliver = check_profile({**LOW, "esg": True}, {"BTC-USD": 0.0004, "XIU.TO": 0.9996}, _a(**extra))
    fresh = check_profile({**MATEO, "esg": True}, {"NVDA": 0.4, "XIU.TO": 0.6}, _direct(      # a fresh clone: funds not opened
        stocks={"NVDA": {"direct": 0.4, "via": [], "total": 0.4}}, sectors={"Information Technology": 0.4}, **extra))
    unopened = check_profile({**LOW, "esg": True}, {"XIU.TO": 0.6, "QQQ": 0.4}, _direct(**extra))
    return [*amira, *esg, *sliver, *fresh, *unopened]


def test_every_percent_in_a_sentence_follows_a_no_break_space():
    import re
    assert fmt_pct(-0.345) == f"−34.5{NB}%" and fmt_pct(0.08) == f"8.0{NB}%"
    rows = _every_reason()
    assert len(rows) >= 25
    for row in rows:
        assert " %" not in row["reason"] and not re.search(r"(?<!\u00a0)%", row["reason"]), row["reason"]
    with pytest.raises(ValueError) as caught:
        load_limits(ROBERT, {"floor": -2}, amount=600_000)
    assert f"between −100{NB}% and 0{NB}%" in str(caught.value) and " %" not in str(caught.value)
    with pytest.raises(ValueError) as caught:
        load_limits(ROBERT, {"sector": 2}, amount=600_000)
    assert f"between 0{NB}% and 100{NB}%" in str(caught.value) and " %" not in str(caught.value)


def test_days_in_a_sentence_are_whole_days():
    import re
    for row in _every_reason():
        assert not re.search(r"\d\.\d+ days?\b", row["reason"]), row["reason"]
    unrecovered = _a(dd=-0.20)
    unrecovered["metrics"].update({"recovery_days": None, "days_since_trough": 900})
    row = _row(check_profile(ROBERT, {"XIU.TO": 1.0}, unrecovered), "recovery")
    assert row["reason"] == ("The worst drop was 900 days past its low and had not recovered; your horizon gives about "
                             "487 days, so that was beyond it.")
    assert row["limit"] == pytest.approx(486.618)                  # the row keeps the unrounded limit (ledger 10)
    ten = _a(dd=-0.30)
    ten["metrics"].update({"recovery_days": 1300, "days_since_trough": 900})
    long_horizon = _row(check_profile({**LOW, "horizon_years": 10}, {"XIU.TO": 1.0}, ten), "recovery")
    assert "your horizon gives about 1,217 days, so that was beyond it" in long_horizon["reason"]      # 10 y: 1,216.545, shown to the day


# ---- Task 5 rulings: unknown is never a pass (ledger 29, spec 21 move 4): gaps are named caveats in `missing_data` ----

GAP_H = {"etf": "XIU.TO", "missing": "holdings", "coverage": 0.0}
GAP_S = {"etf": "XIU.TO", "missing": "sectors", "coverage": 0.0}


def _gap_row(gaps=(), tickers=(), vol="absent"):
    a = _a(missing_data=list(tickers))
    a["lookthrough"]["gaps"] = list(gaps)
    if vol != "absent":
        a["metrics"]["volatility"] = vol
    checks = check_profile(LOW, {"XIU.TO": 1.0}, a)
    return checks, next((c for c in checks if c["rule"] == "missing_data"), None)


def test_a_lookthrough_gap_is_a_named_caveat_and_the_verdict_is_inside_with_caveats_at_best():
    checks, row = _gap_row(gaps=[GAP_H, GAP_S])
    assert (row["tier"], row["status"], row["value"], row["limit"], row["holding"]) == ("warn", "warn", 1, 0, None)
    assert "XIU.TO" in row["reason"] and "holdings" in row["reason"] and "sector split" in row["reason"]
    assert "unknown" in row["reason"] and "less certain" in row["reason"] and not ADVICE.search(row["reason"])
    assert verdict(checks) == "Tension"                           # one warn alone is Compatible; a caveat never is
    only_sectors = _gap_row(gaps=[GAP_S])[1]["reason"]
    assert "sector split" in only_sectors and "holdings" not in only_sectors
    assert _gap_row(gaps=[])[1] is None and verdict(_gap_row(gaps=[])[0]) == "Compatible"


def test_a_price_gap_keeps_its_sentence_and_is_a_caveat_too():
    checks, row = _gap_row(tickers=["XBB.TO", "CNQ.TO"])
    assert row["value"] == 2 and row["reason"] == (
        "CNQ.TO, XBB.TO have a price gap of more than 3 days in this history, so results that rest on it are less certain.")
    assert verdict(checks) == "Tension"
    both = _gap_row(gaps=[GAP_H], tickers=["XIU.TO"])[1]            # one line with two kinds of gap counts once
    assert both["value"] == 1 and "price gap" in both["reason"] and "holdings" in both["reason"]


def test_a_flat_or_too_short_series_is_a_named_caveat_never_a_pass():
    for vol in (0.0, 1e-15, None):
        checks, row = _gap_row(vol=vol)
        assert row["status"] == "warn" and "too short or too flat" in row["reason"] and verdict(checks) == "Tension", vol
    assert _gap_row(vol=0.12)[1] is None                           # a series that moves is not a caveat
    assert _gap_row()[1] is None                                   # no volatility key at all: nothing to read, no row
    assert _gap_row(vol=0.0)[1]["value"] == 1


def test_only_a_caveat_row_lifts_a_single_warn_to_tension():
    def row(rule):
        return {"rule": rule, "tier": "warn", "status": "warn", "value": 0, "limit": 0, "holding": None, "reason": "."}
    assert verdict([row("risk_concentration")]) == "Compatible" and verdict([row("missing_data")]) == "Tension"
    assert verdict([{**row("missing_data"), "status": "pass"}]) == "Compatible"


# ---- Task 5: what evaluate composes (synthetic markets; the collaborators it does not own are replaced where noted) ----

def _uni(*rows):
    base = {"name": "x", "market": "TSX", "currency": "CAD", "sector": "Industrials", "country": "CAN"}
    return pd.DataFrame([{**base, "ticker": t, "asset_class": c, **extra} for t, c, extra in rows])


def _mk(columns, universe, periods=260):
    dates = pd.bdate_range("2024-01-01", periods=periods)
    frame = pd.DataFrame({t: (list(v) + [v[-1]] * periods)[:periods] for t, v in columns.items()}, index=dates)
    return make_market(frame, universe=universe, as_of=dates[-1].strftime("%Y-%m-%d")), dates


@pytest.fixture
def clean_shocks(monkeypatch):
    """A shock check that concludes (three clean episodes, inside half the floor), so only the thing under test warns."""
    import governance
    monkeypatch.setattr(governance, "scenario_stress", lambda *a, **k: {
        "value": -0.01, "n_episodes": 3, "worst_event_id": "x", "episodes": [], "excluded": [], "label": "Measured"})


def test_loss_dollars_is_amount_times_drawdown_never_peak_minus_trough():
    grew = [100 + i for i in range(51)] + [150 - 0.6 * i for i in range(1, 51)]        # 100 -> 150, then 150 -> 120
    m, dates = _mk({"AAA": grew}, _uni(("AAA", "equity", {})))
    as_of = dates[-1].strftime("%Y-%m-%d")
    out = evaluate(LOW, {"AAA": 1.0}, ["tariffs"], as_of, market=m, events=[], today=False, amount=100_000)
    assert out["metrics"]["max_drawdown"] == pytest.approx(-0.20)
    assert out["analysis"]["loss_dollars"] == pytest.approx(20_000)                 # peak - trough would be $30,000
    assert "$" not in next(c for c in out["checks"] if c["rule"] == "max_drawdown")["reason"]      # R35
    assert evaluate(LOW, {"AAA": 1.0}, ["tariffs"], as_of, market=m, events=[], today=False)["analysis"]["loss_dollars"] is None
    rising, _ = _mk({"AAA": [100 + i for i in range(60)]}, _uni(("AAA", "equity", {})))
    up = evaluate(LOW, {"AAA": 1.0}, [], rising["as_of"], market=rising, events=[], today=False, amount=100_000)
    assert up["analysis"]["loss_dollars"] is None and up["metrics"]["max_drawdown"] == 0.0


def test_families_default_to_all_four_and_the_label_joins_them():
    m, as_of = _market()
    out = evaluate(LOW, {"AAA": 1.0}, None, as_of, market=m, events=[], today=False)
    assert out["analysis"]["scenario_family"] == "Tariff war + War & oil + Chip war + Rate shock"
    assert evaluate(LOW, {"AAA": 1.0}, ("rates", "tariffs"), as_of, market=m, events=[], today=False)[
        "analysis"]["scenario_family"] == "Rate shock + Tariff war"


def test_only_today_looks_through_and_a_past_date_gets_direct_lines_only(monkeypatch):
    import governance
    seen = []
    real = governance.country_exposure
    monkeypatch.setattr(governance, "country_exposure", lambda w, **k: seen.append(k["lookthrough"]) or real(w, **k))
    m, as_of = _market()
    past = evaluate(LOW, {"AAA": 1.0}, [], as_of, market=m, events=[], today=False)
    assert past["lookthrough"] is None and seen[-1]["mode"] == "direct"          # never today's ETF snapshot on a past date
    assert evaluate(LOW, {"AAA": 1.0}, [], as_of, market=m, events=[])["lookthrough"] is None   # as_of is not DATASET_END
    now = evaluate(LOW, {"AAA": 1.0}, [], as_of, market=m, events=[], today=True)
    assert now["lookthrough"]["mode"] in ("direct", "lookthrough") and seen[-1] is now["lookthrough"]
    assert now["kpis"]["exposure_canada"] == {"value": pytest.approx(1.0), "limit": None}


def test_light_mode_skips_only_turbulence_and_diversification():
    m, as_of = _market()
    full = evaluate(LOW, {"AAA": 0.5, "BBB": 0.5}, ["chips"], as_of, market=m, events=[], today=False)
    light = evaluate(LOW, {"AAA": 0.5, "BBB": 0.5}, ["chips"], as_of, market=m, events=[], today=False, detail=False)
    assert full["turbulence"] is not None and full["diversification"] is not None
    assert (light["turbulence"], light["diversification"]) == (None, None)
    for key in KEYS - {"turbulence", "diversification"}:
        assert light[key] is not None or key in ("lookthrough",)
    assert light["checks"] == full["checks"] and light["verdict"] == full["verdict"] and light["kpis"] == full["kpis"]


def test_recovery_kpi_falls_back_to_days_since_the_low_and_a_bad_input_is_one_plain_sentence():
    down = [100 - 0.4 * i for i in range(51)]                                             # 100 -> 80
    for end, recovered in ((105.0, True), (85.0, False)):
        m, dates = _mk({"AAA": down + [80 + (end - 80) * i / 50 for i in range(1, 51)]}, _uni(("AAA", "equity", {})))
        out = evaluate(LOW, {"AAA": 1.0}, [], dates[-1].strftime("%Y-%m-%d"), market=m, events=[], today=False)
        k, mt = out["kpis"]["recovery_days"], out["metrics"]
        assert k["limit"] == pytest.approx(486.618)
        assert (mt["recovery_days"] is not None) == recovered
        assert k["value"] == (mt["recovery_days"] if recovered else mt["days_since_trough"]) and k["value"] > 0
    m, as_of = _market()
    for bad, words in (({"as_of": "12 Nov 2026"}, "as_of"), ({"amount": "600000"}, "amount"),
                       ({"esg_flags": "CNQ.TO"}, "flags")):
        with pytest.raises(ValueError) as caught:
            evaluate(LOW, {"AAA": 1.0}, [], **{"as_of": as_of, "market": m, "events": [], "today": False, **bad})
        assert words in str(caught.value) and str(caught.value).endswith(".")


def test_flags_from_the_data_layer_become_a_caveat_but_only_those_dated_up_to_as_of(clean_shocks):
    broad = {"sector": "Broad market (Canada)"}
    m, dates = _mk({"EEE": [100 + (i % 3) for i in range(260)], "FFF": [50 + (i % 2) for i in range(260)]},
                   _uni(("EEE", "etf_equity", broad), ("FFF", "etf_equity", broad)))
    mid, last = dates[100].strftime("%Y-%m-%d"), dates[-1].strftime("%Y-%m-%d")
    m["flags"] = {"EEE": [dates[150].strftime("%Y-%m-%d")], "FFF": [dates[50].strftime("%Y-%m-%d")]}   # what the loader writes
    early = evaluate(LOW, {"EEE": 1.0}, ["tariffs"], mid, market=m, events=[], today=False)
    assert early["analysis"]["missing_data"] == [] and early["verdict"] == "Compatible"       # EEE's gap is after mid
    late = evaluate(LOW, {"EEE": 1.0}, ["tariffs"], last, market=m, events=[], today=False)
    assert late["analysis"]["missing_data"] == ["EEE"] and late["verdict"] == "Tension"
    row = next(c for c in late["checks"] if c["rule"] == "missing_data")
    assert row["status"] == "warn" and "EEE has a price gap of more than 3 days" in row["reason"]
    unheld = evaluate(LOW, {"EEE": 1.0, "FFF": 0.0}, ["tariffs"], mid, market=m, events=[], today=False)
    assert unheld["analysis"]["missing_data"] == []                      # FFF is flagged before mid but is a line at 0


def test_a_latent_flat_series_is_a_named_caveat_never_a_pass(clean_shocks):
    m, as_of = _market()
    out = evaluate(LOW, {"BBB": 1.0}, ["tariffs"], as_of, market=m, events=[], today=False)          # BBB never moves
    assert out["metrics"]["max_drawdown"] == 0.0 and out["metrics"]["volatility"] == 0.0
    row = next(c for c in out["checks"] if c["rule"] == "missing_data")
    assert row["status"] == "warn" and "too short or too flat" in row["reason"]
    assert next(c for c in out["checks"] if c["rule"] == "max_drawdown")["status"] == "pass"
    assert out["verdict"] == "Tension"                                 # "inside the floor" on a flat line is unknown, not safe
    moving = evaluate(LOW, {"AAA": 1.0}, ["tariffs"], as_of, market=m, events=[], today=False, limits={"floor": -0.25})
    assert all(c["rule"] != "missing_data" for c in moving["checks"])


def test_a_fund_with_no_holdings_or_sector_rows_is_a_named_caveat(monkeypatch, clean_shocks):
    import governance
    from tools.lookthrough import COLUMNS, look_through
    uni = _uni(("AAA", "equity", {}), ("EEE", "etf_equity", {"sector": "Broad market (Canada)"}),
               ("FFF", "etf_equity", {"sector": "Broad market (Canada)"}))
    m, dates = _mk({"AAA": [100 + (i % 5) for i in range(260)], "EEE": [50 + (i % 4) for i in range(260)],
                    "FFF": [20 + (i % 3) for i in range(260)]}, uni)
    rows = pd.DataFrame([["FFF", "holding", "Alpha", "AAA", 0.5, "2026-11-12", ""], ["FFF", "sector", "Industrials", "", 1.0, "2026-11-12", ""],
                         ["FFF", "country", "CAN", "", 1.0, "2026-11-12", ""]], columns=COLUMNS)
    monkeypatch.setattr(governance, "look_through", lambda w, **k: look_through(w, holdings=rows, **k))
    out = evaluate(LOW, {"AAA": 0.4, "EEE": 0.3, "FFF": 0.3}, ["tariffs"], "2026-11-12", market=m, events=[], today=True,
                   esg_flags=set())
    assert out["lookthrough"]["gaps"] == [{"etf": "EEE", "missing": "holdings", "coverage": 0.0},
                                          {"etf": "EEE", "missing": "sectors", "coverage": 0.0}]
    row = next(c for c in out["checks"] if c["rule"] == "missing_data")
    assert row["value"] == 1 and "EEE" in row["reason"] and "FFF" not in row["reason"]
    assert "unknown" in row["reason"] and out["verdict"] == "Tension"
    whole = evaluate(LOW, {"AAA": 0.4, "FFF": 0.6}, ["tariffs"], "2026-11-12", market=m, events=[], today=True, esg_flags=set())
    assert whole["lookthrough"]["gaps"] == [] and all(c["rule"] != "missing_data" for c in whole["checks"])


def test_the_shock_check_is_passed_on_as_the_tool_gave_it(monkeypatch):
    import governance
    tool = {"value": -0.04, "n_episodes": 1, "worst_event_id": "h20_2025", "episodes": [], "excluded": [],
            "label": "Indicative (mixed with h20_2025)"}
    monkeypatch.setattr(governance, "scenario_stress", lambda *a, **k: tool)
    m, as_of = _market()
    out = evaluate(LOW, {"AAA": 1.0}, ["tariffs"], as_of, market=m, events=[], today=False)
    assert out["stress"] is tool and out["kpis"]["scenario_stress"] == {"value": -0.04, "limit": -0.075}
    assert (out["analysis"]["scenario_stress"], out["analysis"]["scenario_episodes"]) == (-0.04, 1)
    assert out["analysis"]["scenario_label"] == "Indicative (mixed with h20_2025)"
    assert "too few separate episodes to conclude" in next(c for c in out["checks"] if c["rule"] == "scenario_stress")["reason"]


def test_values_flags_are_read_as_of_or_passed_in(tmp_path, monkeypatch):
    import config
    table = tmp_path / "esg_flags.csv"
    table.write_text("ticker,flag,reason_en,reason_fr,source_url,source_date\n"
                     "AAA,energie_fossile,r,r,u,\nBBB,controversy_x,r,r,u,2099-06-30\n", encoding="utf-8")
    monkeypatch.setattr(config, "ESG_FLAGS_CSV", table)
    m, as_of = _market()
    values = {**LOW, "esg": True}
    out = evaluate(values, {"AAA": 0.5, "BBB": 0.5}, [], as_of, market=m, events=[], today=False)
    assert out["analysis"]["esg_flags"] == {"AAA"}                      # the BBB filing is dated after as_of: unknown then
    assert next(c for c in out["checks"] if c["rule"] == "esg_direct")["holding"] == "AAA"
    passed = evaluate(values, {"AAA": 0.5, "BBB": 0.5}, [], as_of, market=m, events=[], today=False, esg_flags=["BBB"])
    assert passed["analysis"]["esg_flags"] == {"BBB"}
    assert next(c for c in passed["checks"] if c["rule"] == "esg_direct")["holding"] == "BBB"


def _same(a, b) -> bool:
    """Equality that sees through NaN and sets: both sides written as sorted JSON text."""
    def dump(x):
        return json.dumps(x, sort_keys=True, default=lambda o: sorted(o) if isinstance(o, set) else str(o))
    return dump(a) == dump(b)


def _storm(event_id, day, family="tariffs"):
    return {"event_id": event_id, "family": family, "category": "tarifs", "sign": "negative", "date": day, "t0": day,
            "t_minus_1": day, "known": True, "in_progress": False, "window_end": day, "regions": ["USA"],
            "title": event_id, "description": "d"}


def test_nothing_dated_after_as_of_reaches_the_judgement(monkeypatch, tmp_path):
    import tools.lookthrough as lookthrough
    monkeypatch.setattr(lookthrough, "HOLDINGS_CSV", tmp_path / "no_holdings.csv")   # today's look-through: direct on both sides
    columns = {"AAA": [100 - 0.4 * i for i in range(51)] + [80 + 0.4 * i for i in range(1, 70)],
               "BBB": [50 + (i % 4) for i in range(260)]}
    m, dates = _mk(columns, _uni(("AAA", "equity", {}), ("BBB", "etf_bond", {"sector": "Bonds (Canada aggregate)"})))
    as_of = dates[120].strftime("%Y-%m-%d")
    # every price after as_of becomes a crash (a 40 % cliff, then a slide): a leak into a trough, a drawdown or a risk share shows
    scrambled = {t: v[:121] + [v[120] * (0.6 - 0.002 * i) for i in range(139)] for t, v in
                 ((k, list(pd.Series(columns[k]).reindex(range(260), method="ffill"))) for k in columns)}
    m2, _ = _mk(scrambled, m["universe"])
    day = lambda i: dates[i].strftime("%Y-%m-%d")
    # two storms replayed in full before as_of, one whose window ends after it (still unknown), one dated after it
    catalog = [_storm("t_early", day(25)), _storm("t_late", day(65)), _storm("t_open", day(110)), _storm("t_after", day(130))]
    w = {"AAA": 0.6, "BBB": 0.4}
    for today in (False, True):
        one = evaluate(ROBERT, w, ["tariffs"], as_of, market=m, events=catalog, today=today, amount=600_000)
        two = evaluate(ROBERT, w, ["tariffs"], as_of, market=m2, events=catalog, today=today, amount=600_000)
        assert set(one) == KEYS == set(two)
        for key in sorted(KEYS):                                   # all 15, the shock tools and both look-throughs included
            assert _same(one[key], two[key]), (today, key)
        assert one["series"]["dates"][-1] == as_of and one["metrics"]["as_of"] == as_of
        assert one["stress"]["n_episodes"] == 2 and one["stress"]["value"] is not None       # the storms really were replayed
        assert one["turbulence"]["tariffs"]["n"] == 2 and (one["lookthrough"] is None) == (not today)


def test_a_date_with_no_price_history_is_one_plain_sentence_not_a_crash():
    m, as_of = _market()
    out = evaluate(LOW, {"AAA": 1.0}, [], "2023-01-02", market=m, events=[], today=False)
    assert set(out) == {"error"} and out["error"] == "There is no price history on or before 2023-01-02, so there is nothing to replay."


# ---- Task 5 on the real data (skipped where data/starter is absent; the numbers are spec 3 and ledger 14) ----

NEEDS_DATA = pytest.mark.skipif(not Path("data/starter/prices_daily.csv").exists(), reason="starter data not present")
ROBERT_REAL = {"goal": "preservation", "horizon_years": 4, "risk": None, "reaction_2022": "held", "esg": False,
               "crypto": False, "capacity": 90_000}
ROBERT_MIX = {"XIU.TO": 0.45, "XBB.TO": 0.35, "GLD": 0.10, "ZST.TO": 0.10}


@NEEDS_DATA
def test_robert_after_is_outside_his_limits_in_dollars_on_the_real_data():
    after = {"XIU.TO": 0.27, "XBB.TO": 0.21, "GLD": 0.06, "ZST.TO": 0.06, "NVDA": 0.40}
    out = evaluate(ROBERT_REAL, after, ["tariffs"], "2026-11-12", amount=600_000)
    assert out["verdict"] == "Incompatible" and out["limits"]["floor_source"] == "capacity"
    assert out["kpis"]["max_drawdown"]["value"] == pytest.approx(-0.345, abs=0.001)
    assert out["kpis"]["max_drawdown"]["limit"] == -0.15
    assert round(out["analysis"]["loss_dollars"]) == 207_146                    # amount x drawdown (ledger 14)
    reason = next(c for c in out["checks"] if c["rule"] == "max_drawdown")["reason"]
    assert f"−34.5{NB}%" in reason and "$" not in reason and " %" not in reason        # R35: the dollars are capacity's


@NEEDS_DATA
def test_roberts_floor_breaks_between_8_and_9_percent_in_nvidia():
    from tools.portfolio import apply_change
    seen = {}
    for weight in (0.07, 0.08, 0.09, 0.10):
        mix = apply_change(ROBERT_MIX, {"op": "set", "ticker": "NVDA", "weight": weight, "from_ticker": None})
        out = evaluate(ROBERT_REAL, mix, ["tariffs"], "2026-11-12", amount=600_000, detail=False)
        seen[weight] = next(c for c in out["checks"] if c["rule"] == "max_drawdown")
    assert {w: row["status"] for w, row in seen.items()} == {0.07: "pass", 0.08: "pass", 0.09: "fail", 0.10: "fail"}
    from governance import round_pp
    assert seen[0.08]["value"] < -0.15 and round_pp(seen[0.08]["value"]) == round_pp(-0.15)   # -15.00004 % passes (pitfall 5)


def test_the_caveat_sentences_give_no_advice_and_no_forecast():
    import re
    words = re.compile(r"\b(buy|sell|hold|held|holding|holds|should|will|expect\w*|recommend\w*|unsuitable)\b", re.I)
    sentences = [row["reason"] for row in _every_reason()]
    for gaps, tickers, vol in (([GAP_H, GAP_S], ["CNQ.TO"], 0.0), ([GAP_S], [], None), ([GAP_H], ["A", "B"], 0.2)):
        sentences.append(_gap_row(gaps=gaps, tickers=tickers, vol=vol)[1]["reason"])
    assert len(sentences) >= 28
    for text in sentences:
        assert text.endswith(".") and not words.search(text), text
        assert " %" not in text and not re.search(r"\d\.\d+ days?", text), text


def test_evaluate_changes_nothing_it_is_given_and_gives_the_same_answer_twice():
    import copy
    m, as_of = _market()
    before = {k: m[k].copy() for k in ("prices", "traded", "universe")}
    weights, edits = {"AAA": 0.6, "BBB": 0.4}, {"floor": -0.2}
    kept = copy.deepcopy((weights, edits))
    one = evaluate(ROBERT, weights, ["tariffs"], as_of, market=m, events=[], today=False, limits=edits, amount=600_000)
    two = evaluate(ROBERT, weights, ["tariffs"], as_of, market=m, events=[], today=False, limits=edits, amount=600_000)
    assert one == two and (weights, edits) == kept
    assert all(m[k].equals(frame) for k, frame in before.items())


def test_a_row_never_leaves_an_ordinary_space_before_a_percent_sign():
    import governance
    row = governance._row("x", "warn", "warn", 0, 0, None, "It is 5 % of the money, and 12.5 % of the risk.")
    assert row["reason"] == f"It is 5{NB}% of the money, and 12.5{NB}% of the risk."


# ---- ledger 30 and spec 5: a shock Caution lifts the verdict to "Inside, with caveats" only on >= 2 separate episodes ----

def test_a_shock_check_caution_lifts_the_verdict_only_when_it_rests_on_two_separate_episodes():
    # The soft fail's verdict is kept for a Caution that concludes (the label changed, the verdict did not); "too few
    # separate episodes to conclude" (n < 2) and "no close precedent" (no value) are plain warns that never move the
    # verdict, even when the value they carry is beyond the limit: a row that declines to conclude cannot move the headline.
    breach = check_profile(LOW, {"XIU.TO": 1.0}, _a(stress=-0.09, n=4))
    row = _row(breach, "scenario_stress")
    assert (row["tier"], row["status"]) == ("soft", "warn") and count_fails(breach) == 0
    assert verdict(breach) == "Tension"
    assert check_order(breach, LOW)[0] == "scenario_stress"       # "the check that decided the verdict"
    assert verdict(check_profile(LOW, {"XIU.TO": 1.0}, _a(stress=-0.09, n=2))) == "Tension"       # two is enough
    assert verdict(check_profile(LOW, {"XIU.TO": 1.0}, _a(stress=-0.05, n=4))) == "Compatible"
    for stress, n in ((None, 0), (None, 3), (-0.05, 1), (-0.05, 0), (-0.20, 1), (-0.20, 0)):
        checks = check_profile(LOW, {"XIU.TO": 1.0}, _a(stress=stress, n=n))
        warn = _row(checks, "scenario_stress")
        assert (warn["tier"], warn["status"]) == ("soft", "warn") and count_fails(checks) == 0, (stress, n)
        assert verdict(checks) == "Compatible", (stress, n)        # a plain warn, alone, never moves the verdict
    few = _row(check_profile(LOW, {"XIU.TO": 1.0}, _a(stress=-0.20, n=1)), "scenario_stress")
    assert few["value"] == -0.20 and "too few separate episodes to conclude" in few["reason"]   # the value stays the tool's


def _quiet_market():
    """Two identical bond-class lines that fall 20 % and recover: no company, sector, crypto or risk-share rule can fire,
    so the shock check is the only row that can move the verdict (the test edits the floor to -25 %: the drop passes it)."""
    path = [100 - 0.4 * i for i in range(51)] + [80 + 0.4 * i for i in range(1, 70)]
    bond = {"sector": "Bonds (Canada aggregate)"}
    m, dates = _mk({"AAA": path, "CCC": path}, _uni(("AAA", "etf_bond", bond), ("CCC", "etf_bond", bond)))
    return m, dates[-1].strftime("%Y-%m-%d")


def test_evaluate_lifts_the_verdict_on_a_shock_caution_only_with_two_episodes(monkeypatch):
    import governance
    m, as_of = _quiet_market()
    for n, want in ((0, "Compatible"), (1, "Compatible"), (2, "Tension"), (6, "Tension")):
        tool = {"value": -0.20, "n_episodes": n, "worst_event_id": "x", "episodes": [], "excluded": [], "label": "Measured"}
        monkeypatch.setattr(governance, "scenario_stress", lambda *a, _t=tool, **k: _t)
        out = evaluate(LOW, {"AAA": 0.5, "CCC": 0.5}, ["tariffs"], as_of, market=m, events=[], today=False,
                       limits={"floor": -0.25})
        assert [c["rule"] for c in out["checks"] if c["status"] != "pass"] == ["scenario_stress"], n
        assert out["verdict"] == want == verdict(out["checks"]), n
        assert ("too few separate episodes to conclude" in out["checks"][1]["reason"]) == (n < 2), n


# ---- ledger 30: a fresh clone without holdings runs in direct mode; the checklist says so as a caveat ----

def _direct(**kw):
    a = _a(**kw)
    a["lookthrough"]["mode"] = "direct"
    return a


def test_direct_mode_on_a_fresh_clone_is_a_caveat_on_the_lookthrough_rows():
    mix = {"XIU.TO": 0.6, "XBB.TO": 0.4}
    checks = check_profile({**LOW, "esg": True}, mix, _direct())
    gap = _row(checks, "missing_data")
    assert (gap["tier"], gap["status"], gap["value"], gap["holding"]) == ("warn", "warn", 1, None)
    assert gap["reason"] == ("XIU.TO could not be looked through (no ETF holdings list for this run), so the companies and "
                             "sectors inside it are unknown, so results that rest on it are less certain.")
    assert verdict(checks) == "Tension"
    # ledger 30 (review of Task 5): unknown is never a pass, and never a 0.0 or a None dressed as one. Each look-through row is
    # a warn with no value, and its ONE sentence says the companies inside the fund are not known from holdings.
    for rule, tier in (("single_stock", "soft"), ("sector", "soft"), ("esg_indirect", "warn")):
        row = _row(checks, rule)
        assert (row["tier"], row["status"], row["value"], row["holding"]) == (tier, "warn", None, None), rule
        assert len(re.findall(r"[.!?](?=\s|$)", row["reason"])) == 1 and "not known from holdings" in row["reason"], rule
    assert _row(checks, "single_stock")["reason"] == (
        f"The 10{NB}% limit for one company cannot be checked: XIU.TO was not looked through, so the companies inside it "
        "are not known from holdings.")
    assert _row(checks, "sector")["reason"] == (
        f"The 30{NB}% limit for one sector cannot be checked: XIU.TO was not looked through, so the companies inside it, "
        "and their sectors, are not known from holdings.")
    two = check_profile(LOW, {"XIU.TO": 0.5, "QQQ": 0.3, "XBB.TO": 0.2}, _direct())
    assert _row(two, "single_stock")["reason"] == (
        f"The 10{NB}% limit for one company cannot be checked: QQQ, XIU.TO were not looked through, so the companies "
        "inside them are not known from holdings.")


def test_a_company_beyond_its_limit_stays_a_fail_when_a_fund_was_not_opened():
    # What is known is still said: NVDA held directly is a fail whatever is inside XIU.TO (one cause, one fail); the clause
    # keeps the row to one sentence and says what is not known. A direct line inside its limit is no conclusion: a warn.
    stocks, sectors = {"NVDA": {"direct": 0.4, "via": [], "total": 0.4}}, {"Information Technology": 0.4}
    checks = check_profile(LOW, {"NVDA": 0.4, "XIU.TO": 0.6}, _direct(stocks=stocks, sectors=sectors))
    one, sec = _row(checks, "single_stock"), _row(checks, "sector")
    assert (one["status"], one["value"], one["holding"]) == ("fail", 0.4, "NVDA")
    assert (sec["status"], sec["value"], sec["holding"]) == ("fail", 0.4, "NVDA") and count_fails(checks) == 1
    assert one["reason"] == (f"NVDA is 40.0{NB}% of the money, beyond the 10{NB}% limit for one company; XIU.TO was not "
                             "looked through, so the companies inside it are not known from holdings.")
    assert sec["reason"] == (f"Information Technology is 40.0{NB}% of the money, beyond the 30{NB}% limit for one sector; "
                             "XIU.TO was not looked through, so the companies inside it, and their sectors, are not known "
                             "from holdings.")
    small = {"NVDA": {"direct": 0.05, "via": [], "total": 0.05}}
    inside = check_profile(LOW, {"NVDA": 0.05, "XIU.TO": 0.95}, _direct(stocks=small, sectors={"Information Technology": 0.05}))
    for rule in ("single_stock", "sector"):
        assert (_row(inside, rule)["status"], _row(inside, rule)["value"], _row(inside, rule)["holding"]) == ("warn", None, None)


def test_direct_mode_says_nothing_where_there_is_nothing_to_open_up():
    bonds = check_profile(LOW, {"XBB.TO": 0.7, "NVDA": 0.3}, _direct())
    assert all(c["rule"] != "missing_data" for c in bonds)
    assert all("looked through" not in c["reason"] for c in bonds)
    mix = {"XIU.TO": 0.6, "XBB.TO": 0.4}
    for case in (_a(), _a(lt=False)):                              # a real look-through, or a past date (direct by design)
        rows = check_profile(LOW, mix, case)
        assert all(c["rule"] != "missing_data" and "looked through" not in c["reason"] for c in rows)
    sold = check_profile(LOW, {"XIU.TO": 1.0, "QQQ": 0.0}, _direct())            # a line at 0 is not held
    assert "QQQ" not in _row(sold, "missing_data")["reason"]


def test_a_fresh_clone_through_evaluate_names_the_unopened_fund_on_every_row(monkeypatch, tmp_path):
    # The real path: no holdings file (tools.lookthrough.HOLDINGS_CSV missing), today's run, an equity fund held. Review of
    # B Task 5, minor 3: the caveat used to be tested only through check_profile on a hand-built `mode: "direct"`.
    import tools.lookthrough as lookthrough
    monkeypatch.setattr(lookthrough, "HOLDINGS_CSV", tmp_path / "no_such_holdings.csv")
    path = [100 - 0.4 * i for i in range(51)] + [80 + 0.4 * i for i in range(1, 70)]
    m, dates = _mk({"EQF": path, "BND": [50 + (i % 3) for i in range(120)]},
                   _uni(("EQF", "etf_equity", {"sector": "Broad market (Canada)"}),
                        ("BND", "etf_bond", {"sector": "Bonds (Canada aggregate)"})))
    as_of, mix, values = dates[-1].strftime("%Y-%m-%d"), {"EQF": 0.5, "BND": 0.5}, {**LOW, "esg": True}
    out = evaluate(values, mix, [], as_of, market=m, events=[], today=True, esg_flags=set(), limits={"floor": -0.25})
    assert out["lookthrough"]["mode"] == "direct" and out["lookthrough"]["gaps"] == []
    rows = {c["rule"]: c for c in out["checks"]}
    for rule in ("single_stock", "sector", "esg_indirect"):
        assert (rows[rule]["status"], rows[rule]["value"], rows[rule]["holding"]) == ("warn", None, None), rule
        assert "EQF was not looked through, so the companies inside it" in rows[rule]["reason"], rule
        assert len(re.findall(r"[.!?](?=\s|$)", rows[rule]["reason"])) == 1, rule
    assert rows["missing_data"]["status"] == "warn" and "EQF could not be looked through" in rows["missing_data"]["reason"]
    assert out["verdict"] == "Tension" == verdict(out["checks"])
    assert check_profile(values, mix, out["analysis"]) == out["checks"]                  # a recheck writes the same rows
    held_bonds = evaluate(values, {"BND": 1.0}, [], as_of, market=m, events=[], today=True, esg_flags=set(), limits={"floor": -0.25})
    assert all("looked through" not in c["reason"] for c in held_bonds["checks"])        # nothing to open up: nothing to say


def test_missing_data_names_its_real_cause():
    # Ledger 30: the data layer flags a held line for a price gap of more than 3 days, or for a USD price with no USD/CAD
    # rate yet; the sentence says which. A plain ticker is a gap; an entry written with `governance.NO_RATE` is the rate case.
    import governance
    gap = _row(check_profile(LOW, {"XIU.TO": 1.0}, _a(missing_data=["XIU.TO"])), "missing_data")
    assert gap["reason"] == ("XIU.TO has a price gap of more than 3 days in this history, so results that rest on it are "
                             "less certain.") and gap["value"] == 1
    rate = _row(check_profile(LOW, {"NVDA": 1.0}, _a(missing_data=["NVDA" + governance.NO_RATE])), "missing_data")
    assert rate["reason"] == ("NVDA has a USD price with no USD/CAD rate yet in this history, so results that rest on it are "
                              "less certain.") and (rate["status"], rate["value"]) == ("warn", 1)
    both = _row(check_profile(LOW, {"NVDA": 0.5, "XIU.TO": 0.5},
                              _a(missing_data=["XIU.TO", "NVDA", "NVDA" + governance.NO_RATE])), "missing_data")
    assert both["reason"] == ("NVDA, XIU.TO have a price gap of more than 3 days in this history; NVDA has a USD price with "
                              "no USD/CAD rate yet in this history, so results that rest on them are less certain.")
    assert both["value"] == 2                                       # NVDA is one line, named once
    assert verdict(check_profile(LOW, {"NVDA": 1.0}, _a(missing_data=["NVDA" + governance.NO_RATE]))) == "Tension"


def test_the_flagged_lines_tell_a_price_gap_from_a_missing_rate():
    import governance
    dates = pd.bdate_range("2024-01-01", periods=12)
    day = lambda i: dates[i].strftime("%Y-%m-%d")
    local = pd.DataFrame({"NVDA": [10.0] * 12, "XIU.TO": [20.0] * 12, "SHOP.TO": [30.0] * 12}, index=dates)
    cad = local.copy()
    cad.loc[dates[:2], "NVDA"] = float("nan")                       # a USD price on days before the first USD/CAD rate
    cad.loc[dates[5:9], "XIU.TO"] = float("nan")                    # no price at all for four days: a gap
    local.loc[dates[5:9], "XIU.TO"] = float("nan")
    cad.loc[dates[10], "NVDA"] = local.loc[dates[10], "NVDA"] = float("nan")       # and NVDA has a later gap too
    flags = {"NVDA": [day(0), day(1), day(10)], "XIU.TO": [day(i) for i in range(5, 9)], "SHOP.TO": []}
    market, held = {"flags": flags, "prices": cad, "local": local}, {"NVDA": 0.3, "XIU.TO": 0.3, "SHOP.TO": 0.4}
    both = ["NVDA", "NVDA" + governance.NO_RATE, "XIU.TO"]
    assert governance._flagged_lines(held, market, day(11)) == both
    assert governance._flagged_lines(held, market, day(1)) == ["NVDA" + governance.NO_RATE]      # later flags are not known yet
    assert governance._flagged_lines({"NVDA": 0.0, "XIU.TO": 1.0}, market, day(11)) == ["XIU.TO"]   # a line at 0 is not held
    assert governance._flagged_lines(held, {"flags": flags}, day(11)) == ["NVDA", "XIU.TO"]         # no price frames: gaps


def test_the_real_data_layer_flags_are_named_by_cause(tmp_path):
    # Through tools.data.load_market (the real definition of a flag), not hand-built flags: NVDA has USD prices before the
    # first USD/CAD rate (2024-01-05), RY.TO has no price for six days after its first one.
    import governance
    from tests.test_data import write_starter
    from tools.data import load_market
    days = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08", "2024-01-09", "2024-01-10", "2024-01-11"]
    write_starter(tmp_path, {"NVDA": {d: 10.0 for d in days}, "RY.TO": {days[0]: 5.0, days[7]: 5.0}})
    pd.DataFrame({"date": days[3:], "usdcad": [1.30] * 5, "cadusd": 0.77}).to_csv(tmp_path / "fx_usdcad_daily.csv", index=False)
    market, held = load_market(days[7], data_dir=tmp_path), {"NVDA": 0.5, "RY.TO": 0.5}
    assert market["flags"]["NVDA"] == days[:3] and market["flags"]["RY.TO"] == days[4:7]
    entries = governance._flagged_lines(held, market, days[7])
    assert entries == ["NVDA" + governance.NO_RATE, "RY.TO"]
    assert governance._flagged_lines(held, load_market(days[2], data_dir=tmp_path), days[2]) == ["NVDA" + governance.NO_RATE]
    reason = _row(check_profile(LOW, held, _a(missing_data=entries)), "missing_data")["reason"]
    assert reason == ("RY.TO has a price gap of more than 3 days in this history; NVDA has a USD price with no USD/CAD rate "
                      "yet in this history, so results that rest on them are less certain.")


def test_the_look_through_gets_the_runs_own_date(monkeypatch):
    import governance
    calls = []
    real = governance.look_through
    monkeypatch.setattr(governance, "look_through", lambda w, **k: calls.append(k) or real(w, **k))
    m, as_of = _market()
    evaluate(LOW, {"AAA": 1.0}, [], as_of, market=m, events=[], today=True, esg_flags=set())
    evaluate(LOW, {"AAA": 1.0}, [], as_of, market=m, events=[], today=False, esg_flags=set())
    assert [k["as_of"] for k in calls] == [as_of, as_of]           # today's look-through, then the past date's direct one
    assert all(k["esg_flags"] == set() for k in calls)


NEEDS_HOLDINGS = pytest.mark.skipif(
    not (Path("data/starter/prices_daily.csv").exists() and Path("data/etf_holdings.csv").exists()),
    reason="starter data or the local ETF holdings file is absent (never committed)")
MATEO_REAL = {"goal": "balance", "horizon_years": 10, "risk": "moderate", "esg": True, "crypto": False,
              "capacity": 62_500, "reaction_2022": "held"}
AMIRA_REAL = {"goal": "growth", "horizon_years": 15, "risk": "high", "esg": False, "crypto": True,
              "capacity": 36_000, "reaction_2022": "bought"}


def _by_status(out):
    return {s: {c["rule"] for c in out["checks"] if c["status"] == s} for s in ("fail", "warn")}


@NEEDS_HOLDINGS
def test_the_pilots_on_the_real_data_with_every_real_tool():
    """The finance truth (spec 3, ledger 30), with the shock check a Caution (warn), never a fail."""
    robert = evaluate(ROBERT_REAL, ROBERT_MIX, ["tariffs"], "2026-11-12", amount=600_000)
    assert robert["verdict"] == "Compatible" and _by_status(robert) == {"fail": set(), "warn": {"risk_concentration"}}
    assert robert["kpis"]["scenario_stress"]["value"] == pytest.approx(-0.060, abs=0.003)
    after = {"XIU.TO": 0.27, "XBB.TO": 0.21, "GLD": 0.06, "ZST.TO": 0.06, "NVDA": 0.40}
    out = evaluate(ROBERT_REAL, after, ["tariffs"], "2026-11-12", amount=600_000)
    got = _by_status(out)
    assert out["verdict"] == "Incompatible" and got["fail"] == {"max_drawdown", "single_stock", "sector"}
    assert "scenario_stress" in got["warn"] and count_fails(out["checks"]) == 2          # NVDA twice counts once
    assert out["kpis"]["scenario_stress"]["value"] == pytest.approx(-0.090, abs=0.003)
    shock = next(c for c in out["checks"] if c["rule"] == "scenario_stress")
    assert shock["status"] == "warn" and "beyond half your floor" in shock["reason"]
    mateo = evaluate(MATEO_REAL, {"XIU.TO": 0.35, "XBB.TO": 0.35, "CNQ.TO": 0.08, "MSFT": 0.10, "GLD": 0.12},
                     ["war_oil"], "2026-11-12", amount=250_000)
    assert mateo["verdict"] == "Incompatible" and _by_status(mateo)["fail"] == {"esg_direct"}
    assert "esg_indirect" in _by_status(mateo)["warn"]
    amira = evaluate(AMIRA_REAL, {"NVDA": 0.15, "QQQ": 0.15, "SHOP.TO": 0.10, "BTC-USD": 0.15, "XIU.TO": 0.30, "XBB.TO": 0.15},
                     ["chips"], "2026-11-12", amount=80_000)
    assert amira["verdict"] == "Tension" and _by_status(amira)["fail"] == {"crypto"}
    assert amira["kpis"]["max_drawdown"]["value"] == pytest.approx(-0.4135, abs=0.002)


# ---- ledger 30 (D Task 7): the navigator's abstention passes families=[]: no close precedent, never all four families ----

def test_no_family_to_replay_is_no_close_precedent_and_never_a_replay_of_all_four(monkeypatch):
    import config
    import governance
    asked = []
    tool = {"value": -0.04, "n_episodes": 3, "worst_event_id": "x", "episodes": [], "excluded": [], "label": "Measured"}
    monkeypatch.setattr(governance, "scenario_stress", lambda w, fams, *a, **k: asked.append(list(fams)) or tool)
    m, as_of = _market()
    out = evaluate(LOW, {"AAA": 1.0}, [], as_of, market=m, events=[], today=False, amount=100_000)
    assert asked == []                                              # the shock tool is not even asked
    row = next(c for c in out["checks"] if c["rule"] == "scenario_stress")
    assert (row["tier"], row["status"], row["value"]) == ("soft", "warn", None) and row["limit"] == -0.075
    assert "no close precedent at this date" in row["reason"].lower() and "Tariff war" not in row["reason"]
    assert (out["stress"]["value"], out["stress"]["n_episodes"], out["stress"]["worst_event_id"]) == (None, 0, None)
    assert out["kpis"]["scenario_stress"] == {"value": None, "limit": -0.075}
    assert (out["analysis"]["scenario_stress"], out["analysis"]["scenario_episodes"]) == (None, 0)
    assert out["analysis"]["scenario_family"] == "" and set(out) == KEYS
    # nothing named at all (None) is a different thing: every family is replayed
    evaluate(LOW, {"AAA": 1.0}, None, as_of, market=m, events=[], today=False)
    assert asked == [list(config.FAMILIES)]
    evaluate(LOW, {"AAA": 1.0}, ["tariffs"], as_of, market=m, events=[], today=False)
    assert asked[-1] == ["tariffs"]


def test_an_abstention_is_a_warn_even_when_the_catalog_has_storms_and_never_a_fail():
    m, dates = _mk({"AAA": [100 - 0.4 * i for i in range(51)] + [80 + 0.4 * i for i in range(1, 70)]},
                   _uni(("AAA", "equity", {})))
    as_of = dates[-1].strftime("%Y-%m-%d")
    storm = [{"event_id": "t1", "family": "tariffs", "category": "tarifs", "sign": "negative", "date": "2024-02-05",
              "t0": "2024-02-05", "t_minus_1": "2024-02-02", "known": True, "in_progress": False, "window_end": "2024-03-04",
              "regions": ["USA"], "title": "A", "description": "d"}]
    for fams in ([], ["tariffs"]):
        out = evaluate({**LOW, "goal": "balance"}, {"AAA": 1.0}, fams, as_of, market=m, events=storm, today=False)
        row = next(c for c in out["checks"] if c["rule"] == "scenario_stress")
        assert row["status"] != "fail"
    out = evaluate(LOW, {"AAA": 1.0}, [], as_of, market=m, events=storm, today=False)
    assert next(c for c in out["checks"] if c["rule"] == "scenario_stress")["value"] is None


@NEEDS_DATA
def test_the_real_catalog_is_not_replayed_when_the_navigator_abstains():
    after = {"XIU.TO": 0.27, "XBB.TO": 0.21, "GLD": 0.06, "ZST.TO": 0.06, "NVDA": 0.40}
    asked = evaluate(ROBERT_REAL, after, [], "2026-11-12", amount=600_000)
    row = next(c for c in asked["checks"] if c["rule"] == "scenario_stress")
    assert (row["status"], row["value"]) == ("warn", None) and "no close precedent at this date" in row["reason"].lower()
    assert asked["verdict"] == "Incompatible"                      # the floor still decides; the shock check only cannot conclude
    every = evaluate(ROBERT_REAL, after, None, "2026-11-12", amount=600_000)      # nothing named: all four families
    assert every["kpis"]["scenario_stress"]["value"] is not None
    assert asked["turbulence"].keys() == every["turbulence"].keys()               # the per-family table is still the code's


# ---- Sun Nov 15 (lane u6): a check reason names a co-event by its title and date, never its internal id ----
def test_the_shock_checks_evidence_names_co_events_by_title_and_date():
    from governance import label_shown
    events = [{"event_id": "saudi_pipeline_2026", "title": "Attack on Saudi Arabia's East-West pipeline", "date": "2026-09-10"}]
    assert label_shown("Indicative (mixed with saudi_pipeline_2026)", events) == \
        "Indicative: mixed with Attack on Saudi Arabia’s East-West pipeline, 2026-09-10"
    assert label_shown("Indicative (mixed with nope_2020)", events) == "Indicative: mixed with another shock"
    assert label_shown("Measured", events) == "Measured" and label_shown(None, events) is None
    row = _row(_rows(LOW, {"XIU.TO": 1.0}, stress=-0.09, n=4, scenario_label="Indicative (mixed with h20_2025)",
                     scenario_label_shown="Indicative: mixed with License required for NVIDIA H20 chips to China, 2025-04-16"),
               "scenario_stress")
    assert "h20_2025" not in row["reason"] and "License required for NVIDIA H20 chips to China, 2025-04-16" in row["reason"]


# ---- spec ruling R13 (Sun Nov 15): a card's dollar limit is an assumption; a typed one is the investor's own ----
def test_the_floor_reason_says_assumed_for_a_card_and_said_for_typed_answers():
    import json
    import config
    from governance import profile_is_card
    card = json.loads(config.PERSONAS_JSON.read_text(encoding="utf-8"))["pilots"]["robert"]["profile"]
    assert profile_is_card(card) and profile_is_card({**card, "capacity": float(card["capacity"])})
    assert not profile_is_card({**card, "capacity": 80_000}) and not profile_is_card(ROBERT) and not profile_is_card(None)
    a = _a(dd=-0.345, loss_dollars=207_012.4, amount=600_000)
    assumed = _row(check_profile(card, {"XIU.TO": 1.0}, a), "max_drawdown")["reason"]
    assert assumed.endswith("beyond the −15.0 % floor set as your limit (assumed for this fictional profile).")   # R35
    typed = _row(check_profile({**card, "capacity": 90_000.0, "risk": None}, {"XIU.TO": 1.0}, a), "max_drawdown")["reason"]
    assert typed.endswith("beyond the −15.0 % floor from what you said you could lose.")
    inside = _row(check_profile(card, {"XIU.TO": 1.0}, _a(dd=-0.10, amount=600_000)), "max_drawdown")["reason"]
    assert inside.endswith("inside the −15.0 % floor set as your limit (assumed for this fictional profile).")
    edited = check_profile(card, {"XIU.TO": 1.0}, _a(dd=-0.30, limits=load_limits(card, {"floor": -0.2}, amount=600_000)))
    assert _row(edited, "max_drawdown")["reason"].endswith("beyond the −20.0 % floor you set.")     # an edit is yours


def test_the_price_table_is_dated_so_the_run_cost_is_a_number():
    import config
    import proofs
    assert config.PRICES_AS_OF == "2026-11-14" and config.PRICES_SOURCE
    usage = {"inputTokens": 1000, "outputTokens": 100, "cacheReadInputTokens": 0, "cacheWriteInputTokens": 0}
    cost = proofs.run_cost([{"service": "Amazon Bedrock", "model": config.MODEL_ID, "usage": usage}])
    assert cost["usd"] == 0.003 and cost["price_date"] == "2026-11-14" and cost["calls"] == 1


# ---- lane sector-limits (Sun Nov 15): limits by industry, and no limits at all (LIMITS_MODEL 16:40) ----
# The NBDB workshop: "Constraints set the boundaries. Preferences guide choices within those boundaries" (preferred or
# excluded sectors). sector_caps = {GICS sector: the largest share}; 0 % excludes the industry (a hard limit).

CAPS_NB = " "


def _capped(caps, **kw):
    return load_limits(ROBERT, {"sector_caps": caps, **kw}, amount=600_000)


def test_industry_limits_are_checked_kept_in_gics_order_and_listed_as_edits():
    lim = _capped({"Information Technology": 0.2, "energy": 0})
    assert lim["sector_caps"] == {"Energy": 0.0, "Information Technology": 0.2}
    assert list(lim["sector_caps"]) == ["Energy", "Information Technology"] and lim["edited"] == ["sector_caps"]
    assert _capped({"Technology": 0.3, "Healthcare": 0.1})["sector_caps"] == {"Health Care": 0.1,
                                                                               "Information Technology": 0.3}
    for none_set in (load_limits(ROBERT, amount=600_000), _capped({}), _capped(None)):
        assert "sector_caps" not in none_set and none_set["edited"] == [] and "from_words" not in none_set
    for bad, words in (({"Crypto": 0.1}, "is not an industry this replay knows"), ({"Energy": 1.5}, "between 0"),
                       ({"Energy": "0"}, "between 0"), ({"Energy": float("nan")}, "between 0"),
                       ({"Energy": True}, "between 0"), ({"Technology": 0.1, "Information Technology": 0.2}, "two limits")):
        with pytest.raises(ValueError, match=words):
            _capped(bad)
    with pytest.raises(ValueError, match="set of shares named by industry"):
        _capped(["Energy"])


def test_industry_limits_survive_the_whole_limits_dict_coming_back_in():
    first = _capped({"Energy": 0}, floor=-0.2)
    again = load_limits(ROBERT, {**first, "single_stock": 0.3}, amount=600_000)    # pipeline.recheck, the floor scan
    assert again["sector_caps"] == {"Energy": 0.0} and again["edited"] == ["floor", "single_stock", "sector_caps"]
    assert again["floor"] == -0.2


def test_an_industry_limit_is_one_row_each_after_the_sector_row_in_house_style():
    lim = _capped({"Utilities": 0.1, "Information Technology": 0.2, "Energy": 0})
    a = _a(stocks={"NVDA": {"direct": 0.4, "via": [], "total": 0.4}}, limits=lim,
           sectors={"Information Technology": 0.426, "Financials": 0.2, "Energy": 0.031})
    checks = check_profile(ROBERT, {"NVDA": 0.4, "XIU.TO": 0.6}, a)
    rules = [c["rule"] for c in checks]
    at = rules.index("sector")
    assert rules[at + 1:at + 4] == ["sector_cap:Energy", "sector_cap:Information Technology", "sector_cap:Utilities"]
    tech = _row(checks, "sector_cap:Information Technology")
    assert set(tech) == {"rule", "tier", "status", "value", "limit", "holding", "reason"}
    assert (tech["tier"], tech["status"], tech["value"], tech["limit"], tech["holding"]) == ("soft", "fail", 0.426, 0.2,
                                                                                           "NVDA")
    assert tech["reason"] == (f"In this replay the mix held 42.6{CAPS_NB}% in Information Technology, past the "
                              f"20{CAPS_NB}% you set.")
    energy = _row(checks, "sector_cap:Energy")
    assert (energy["tier"], energy["status"], energy["value"], energy["limit"], energy["holding"]) == (
        "hard", "fail", 0.031, 0.0, None)
    assert energy["reason"] == f"In this replay the mix held 3.1{CAPS_NB}% in Energy, an industry you excluded (0{CAPS_NB}%)."
    util = _row(checks, "sector_cap:Utilities")
    assert (util["tier"], util["status"], util["value"], util["holding"]) == ("soft", "pass", 0.0, None)
    assert util["reason"] == f"In this replay the mix held 0.0{CAPS_NB}% in Utilities, inside the 10{CAPS_NB}% you set."
    assert verdict(checks) == "Incompatible" and check_order(checks, ROBERT)[0] == "sector_cap:Energy"
    assert count_fails(checks) == 2           # NVDA (one company, one sector, the tech limit: one cause) + the exclusion
    for c in checks:
        assert " %" not in c["reason"] and not re.search(r"\b(buy|sell|hold|should)\b", c["reason"], re.I)


def test_an_industry_limit_passes_exactly_at_its_share_after_rounding_and_a_sliver_of_an_excluded_one_passes():
    def row(share, cap, sector="Information Technology"):
        return _row(check_profile(ROBERT, {"XIU.TO": 1.0}, _a(sectors={sector: share}, limits=_capped({sector: cap}))),
                    "sector_cap:" + sector)
    assert row(0.2, 0.2)["status"] == "pass" and row(0.20049, 0.2)["status"] == "pass"
    assert row(0.2005, 0.2)["status"] == "fail"                    # 20.05 rounds half up to 20.1, past 20.0
    sliver = row(0.0004, 0, "Energy")
    assert (sliver["status"], sliver["tier"]) == ("pass", "hard")
    assert sliver["reason"] == (f"In this replay the mix held under 0.05{CAPS_NB}% in Energy (0.0{CAPS_NB}% after "
                                f"rounding), an industry you excluded (0{CAPS_NB}%).")
    assert row(0.0, 0, "Energy")["reason"] == (f"In this replay the mix held nothing in Energy, an industry you "
                                               f"excluded (0{CAPS_NB}%).")
    for r in (sliver, row(0.0, 0, "Energy"), row(0.3, 0, "Energy")):
        assert "0\u00a0% limit" not in r["reason"] and "you set" not in r["reason"]
    assert verdict([row(0.3, 0.2)]) == "Tension"          # a soft limit past its share: Inside, with caveats


def test_an_industry_limit_on_a_fresh_clone_is_a_caution_never_a_pass():
    lim = load_limits(LOW, {"sector_caps": {"Information Technology": 0.2}})
    warn = _row(check_profile(LOW, {"XIU.TO": 0.6, "XBB.TO": 0.4}, _direct(limits=lim)),
                "sector_cap:Information Technology")
    assert (warn["status"], warn["value"], warn["tier"], warn["holding"]) == ("warn", None, "soft", None)
    assert warn["reason"] == (f"The 20{CAPS_NB}% you set for Information Technology cannot be checked: XIU.TO was not "
                              "looked through, so the companies inside it, and their sectors, are not known from "
                              "holdings.")
    past = _row(check_profile(LOW, {"NVDA": 0.3, "XIU.TO": 0.7}, _direct(
        limits=lim, sectors={"Information Technology": 0.3})), "sector_cap:Information Technology")
    assert past["status"] == "fail" and past["reason"].endswith("; XIU.TO was not looked through, so the companies "
                                                                "inside it, and their sectors, are not known from holdings.")


def test_without_industry_limits_the_rows_are_exactly_the_eleven_rules():
    import config
    import governance
    checks = check_profile(ROBERT, {"NVDA": 0.4, "XIU.TO": 0.6}, _a(sectors={"Information Technology": 0.4}))
    assert not any(c["rule"].startswith(governance.SECTOR_CAP) for c in checks)
    assert {c["rule"] for c in checks} <= set(config.RULE_IDS)


def test_the_limits_your_words_set_are_kept_as_keys_never_as_words():
    lim = load_limits(MATEO, {"sector_caps": {"Energy": 0}, "crypto": 0.0,
                              "from_words": ["sector_caps.energy", "crypto", "esg", "floor", "nonsense", 7]},
                      amount=250_000)
    assert lim["from_words"] == ["crypto", "sector_caps.Energy", "esg"]       # floor was not set: not kept
    mapped = load_limits(MATEO, {"sector_caps": {"Energy": 0}, "from_words": {"sector_caps.Energy": "no oil companies"}},
                         amount=250_000)
    assert mapped["from_words"] == ["sector_caps.Energy"] and "no oil" not in json.dumps(mapped)
    assert "from_words" not in load_limits(MATEO, {"from_words": []}, amount=250_000)


def test_no_limits_is_the_limits_missing_state_and_every_replay_number_still_computes():
    assert load_limits(ROBERT, {"none": True}, amount=600_000) is None
    assert load_limits(ROBERT, {"none": True, "floor": -0.2, "sector_caps": {"Energy": 0}}, amount=600_000) is None
    assert load_limits({**LOW, "risk": None}, {"floor": -0.2}) is None      # no band to read: nothing is assumed
    assert load_limits(ROBERT, {"none": False}, amount=600_000)["floor"] == -0.15
    m, as_of = _market()
    out = evaluate(LOW, {"AAA": 1.0}, [], as_of, market=m, events=[], today=False, limits={"none": True}, amount=100_000)
    assert set(out) == KEYS and out["checks"] == [] and out["verdict"] is None and out["limits"] is None
    assert all(k["limit"] is None for k in out["kpis"].values())
    assert out["metrics"]["max_drawdown"] == pytest.approx(-0.20, abs=1e-9) and len(out["series"]["dates"]) > 200
    assert out["kpis"]["max_drawdown"]["value"] == pytest.approx(-0.20, abs=1e-9)
    assert out["analysis"]["loss_dollars"] == pytest.approx(20_000)
    assert check_profile(LOW, {"AAA": 1.0}, out["analysis"]) == [] and verdict([]) is None   # a recheck invents none


def test_evaluate_judges_an_industry_limit_on_the_mix_it_is_given():
    m, as_of = _market()                                       # AAA is an Industrials company (direct line: a past date)
    out = evaluate(LOW, {"AAA": 0.6, "BBB": 0.4}, [], as_of, market=m, events=[], today=False,
                   limits={"floor": -0.25, "sector_caps": {"Industrials": 0.5}})
    row = _row(out["checks"], "sector_cap:Industrials")
    assert (row["status"], row["tier"], row["value"], row["limit"], row["holding"]) == ("fail", "soft",
                                                                                       pytest.approx(0.6), 0.5, "AAA")
    assert out["limits"]["sector_caps"] == {"Industrials": 0.5} and out["limits"]["edited"] == ["floor", "sector_caps"]
    assert out["verdict"] == "Tension"
    inside = evaluate(LOW, {"AAA": 0.4, "BBB": 0.6}, [], as_of, market=m, events=[], today=False,
                      limits={"floor": -0.25, "sector_caps": {"Industrials": 0.5}})
    assert _row(inside["checks"], "sector_cap:Industrials")["status"] == "pass"


def test_an_excluded_industry_on_a_fresh_clone_says_its_exclusion_cannot_be_checked():
    lim = load_limits(LOW, {"sector_caps": {"Energy": 0}})
    warn = _row(check_profile(LOW, {"XIU.TO": 1.0}, _direct(limits=lim)), "sector_cap:Energy")
    assert (warn["status"], warn["tier"], warn["value"]) == ("warn", "hard", None)
    assert warn["reason"].startswith(f"The exclusion of Energy (0{CAPS_NB}%) cannot be checked: XIU.TO was not looked")


def test_every_row_names_where_its_limit_came_from():
    from governance import limit_source
    card = json.loads(Path("data/personas.json").read_text(encoding="utf-8"))["pilots"]["robert"]["profile"]
    lim = load_limits(card, {"single_stock": 0.2, "sector_caps": {"Energy": 0, "Information Technology": 0.2},
                             "from_words": ["sector_caps.Information Technology"]}, amount=600_000)
    src = {r: limit_source(r, lim, card) for r in ("max_drawdown", "scenario_stress", "single_stock", "sector", "crypto",
                                                   "risk_concentration", "recovery", "short_horizon", "missing_data",
                                                   "sector_cap:Energy", "sector_cap:Information Technology")}
    assert src == {"max_drawdown": "assumed", "scenario_stress": "assumed", "single_stock": "you", "sector": "assumed",
                   "crypto": "assumed", "risk_concentration": "assumed", "recovery": "assumed",
                   "short_horizon": "assumed", "missing_data": None, "sector_cap:Energy": "you",
                   "sector_cap:Information Technology": "words"}
    typed = {**card, "capacity": 80_000}                         # not the card's answers: typed by the investor
    mine = load_limits(typed, amount=600_000)
    assert limit_source("max_drawdown", mine, typed) == "you" and limit_source("crypto", mine, typed) == "you"
    said = load_limits(typed, {"from_words": ["capacity"]}, amount=600_000)
    assert limit_source("max_drawdown", said, typed) == "words"
    assert limit_source("max_drawdown", None, typed) is None


def test_an_answer_the_reader_assumed_is_never_set_by_you():
    """limits-QA (17:25): the You card's reader defaults crypto to no and marks it "assumed ✎"; a typed (non-card) profile
    counted every answer as the investor's, so the row read "set by you". limits["assumed"] lists the reader's guesses."""
    from governance import limit_source
    you = {"goal": "growth", "horizon_years": 8, "risk": "moderate", "esg": True, "crypto": False, "capacity": 50_000,
           "reaction_2022": None}
    lim = load_limits(you, {"assumed": ["crypto", "esg", "nonsense"], "from_words": ["capacity"]}, amount=300_000)
    assert lim["assumed"] == ["esg", "crypto"] and lim["from_words"] == ["capacity"]
    assert [limit_source(r, lim, you) for r in ("crypto", "esg_direct", "max_drawdown")] == ["assumed", "assumed", "words"]
    plain = load_limits(you, amount=300_000)
    assert "assumed" not in plain and limit_source("crypto", plain, you) == "you"       # typed, as before
    said = load_limits(you, {"from_words": ["crypto"], "assumed": ["crypto"]}, amount=300_000)
    assert said["from_words"] == ["crypto"] and "assumed" not in said             # the words win over a guess
    assert limit_source("crypto", said, you) == "words"


# ---- lane backend-fix (Sun Nov 15, jury QA N1-N3, H5): a shock check that could not conclude is neutral ----

def _verdict_row(rule, tier, status, value, limit, reason=""):
    return {"rule": rule, "tier": tier, "status": status, "value": value, "limit": limit, "holding": None,
            "reason": reason}


def test_a_shock_check_that_could_not_conclude_is_never_one_of_the_two_warns():
    """Aliens, a pandemic, US elections, "the Fed cuts to zero": no close precedent, so the shock check cannot
    conclude. It stays a neutral row and the verdict ignores it: Robert's today mix with its one real warn reads
    Inside your limits, as it does without the question (it read "Inside, with caveats" from the missing precedent)."""
    risk = _verdict_row("risk_concentration", "warn", "warn", 0.71, 0.5, "SPY carries 71 % of the portfolio's risk.")
    floor = _verdict_row("max_drawdown", "hard", "pass", -0.12, -0.15)
    none = _verdict_row("scenario_stress", "soft", "warn", None, -0.075,
                        "There is no close precedent at this date for this question, so the shock check cannot conclude.")
    few = _verdict_row("scenario_stress", "soft", "warn", -0.2, -0.075,
                       "Only 1 clean rates episode is known at this date: too few separate episodes to conclude.")
    assert verdict([floor, risk]) == "Compatible"
    assert verdict([floor, risk, none]) == "Compatible"                  # was Tension: no precedent alone moved it
    assert verdict([floor, risk, few]) == "Compatible"                   # too few episodes cannot conclude either
    assert verdict([floor, none]) == "Compatible" and verdict([none]) == "Compatible"
    assert none["status"] == "warn"                                      # the row keeps its own status and words
    concluded = _verdict_row("scenario_stress", "soft", "warn", -0.2, -0.075,
                             "In the 3 separate earlier rates episodes the worst clean one cost 20 %, beyond half your floor.")
    assert verdict([floor, concluded]) == "Tension"                      # a Caution that concludes still counts
    other = _verdict_row("recovery", "warn", "warn", 900, 365)
    assert verdict([floor, risk, other, none]) == "Tension"              # two real warns still read with caveats
