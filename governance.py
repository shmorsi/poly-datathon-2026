"""EPICENTRE rules engine: the investor's limits, the section 5 checklist rows, the verdict, the check order, and
`evaluate`, the one function that judges a portfolio.

Pure code, no model and no network: the same inputs give the same rows (red gate 2). Limits come from
data/personas.json (read once) and fall back key by key to config.DEFAULT_LIMITS / DEFAULT_THRESHOLDS.
Every threshold is compared after ROUND_HALF_UP to 0.1 pp (`round_pp`, pitfall 5): exactly at the limit passes.
Sources: spec section 5, ledger sections 0, 2, 10, 14, 15, 19, 21, 22, 29, 30, plan B Tasks 4 and 5.
Every sentence it writes for the investor puts U+00A0 before a percent sign, states days as whole days, and never
says buy / sell / hold / should. "Unknown is never a pass": a data gap is a named caveat in the `missing_data` row, and a
held equity fund that was not opened (a fresh clone has no holdings list) makes the single-company, sector and values
rows warns with no value, each in one sentence that says the companies inside the fund are not known from holdings.
"""
import csv
import functools
import json
import math
import numbers
import os
import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pandas as pd

import config
from tools.data import DATASET_END, load_market, mean_policy_rate
from tools.events import load_events, scenario_stress, turbulence
from tools.geo import country_exposure
from tools.lookthrough import look_through
from tools.metrics import risk_metrics, worst_rolling_drop
from tools.portfolio import portfolio_series
from tools.risk import diversification, risk_contributions

GICS_SECTORS = ("Communication Services", "Consumer Discretionary", "Consumer Staples", "Energy", "Financials",
                "Health Care", "Industrials", "Information Technology", "Materials", "Real Estate", "Utilities")
GOAL_LEAD = {"preservation": "max_drawdown", "income": "max_drawdown", "balance": "scenario_stress",
             "growth": "risk_concentration"}  # spec section 5: floor, turbulence, risk and diversification
GOALS = tuple(GOAL_LEAD)
REACTIONS = tuple(config.REACTION_TO_RISK)
BANDS = tuple(config.DEFAULT_LIMITS)
MIN_SHOCK_EPISODES = 2  # spec section 5: fewer clean episodes than this cannot conclude (a warn, never a fail)
TOO_FEW = "too few separate episodes to conclude"  # spec 5's phrase: what a shock check with n < 2 says (see `_caveat`)
PRICE_GAP_DAYS = 3  # spec section 5: the missing_data rule's gap; the flagged tickers arrive in analysis
NO_RATE = " (no USD/CAD rate)"  # suffix of an analysis["missing_data"] entry flagged for a USD price with no USD/CAD rate yet
MINUS = "−"  # U+2212, the sign every displayed negative number uses
NB = "\u00a0"  # U+00A0: the space before a percent sign and before units, so a line never breaks between them
PCT = NB + "%"
ZERO_VOL = 1e-12  # an annualised volatility at or below this is a flat line (tools.metrics treats it as zero)
OVERRIDE_KEYS = ("floor", "single_stock", "sector", "crypto", "scenario_stress", "recovery_days", "risk_share")
# Lane sector-limits (Sun Nov 15; the NBDB workshop: "Constraints set the boundaries", preferred or excluded sectors): the
# investor's own limit on one industry, {GICS sector: max share} in limits["sector_caps"], one row each, rule id
# "sector_cap:<sector>"; 0 % excludes the industry (a hard limit), any other share is a soft one. No caps, no rows.
SECTOR_CAP = "sector_cap:"
_SECTOR_ALIASES = {"technology": "Information Technology", "healthcare": "Health Care"}
WORD_KEYS = ("capacity", "esg", "crypto", "horizon_years")   # answers the words may set or the reader may assume


# ---- rounding and words ----

def round_pp(x: float) -> Decimal:
    """A fraction as percent, ROUND_HALF_UP to 0.1 pp, through repr so float noise cannot tip a limit:
    -0.1500004 -> Decimal('-15.0'), 0.08 -> Decimal('8.0'). Ties round away from zero (-0.1505 -> -15.1)."""
    return (Decimal(repr(float(x))) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def fmt_pct(x: float) -> str:
    """-0.345 -> '−34.5 %' (U+00A0 before the percent sign, U+2212 for the minus)."""
    shown = round_pp(x)
    text = f"{abs(shown) if shown == 0 else shown:.1f}"  # a drop that rounds to zero is "0.0 %", never "−0.0 %"
    return f"{MINUS}{text[1:]}{PCT}" if text.startswith("-") else f"{text}{PCT}"


def _plain(x: float) -> str:
    """An unsigned percent: -0.15 -> '15 %', 0.345 -> '34.5 %' (U+00A0 before the sign; a whole number drops the .0)."""
    text = f"{abs(round_pp(x)):.1f}"
    return f"{text[:-2] if text.endswith('.0') else text}{PCT}"


def fmt_money(x: float) -> str:
    """Dollars to the unit: 207000.4 -> '$207,000', negative -> '−$90,000'."""
    whole = int(Decimal(repr(float(x))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return f"{MINUS}${abs(whole):,}" if whole < 0 else f"${whole:,}"


# ---- the investor's typed profile (ledger section 15): anything else is a plain-English ValueError ----

def _is_int(v) -> bool:
    return isinstance(v, numbers.Integral) and not isinstance(v, bool)


def _is_number(v) -> bool:
    return isinstance(v, numbers.Real) and not isinstance(v, bool) and math.isfinite(v)


def validate_profile(profile: dict) -> None:
    """Raise ValueError (one plain sentence) unless every typed field has its allowed type and range."""
    if not isinstance(profile, dict):
        raise ValueError("The profile must be a set of answers (goal, horizon, 2022 reaction, values, crypto, capacity).")
    if profile.get("goal") not in GOALS:
        raise ValueError(f"The goal must be one of {', '.join(GOALS)}.")
    horizon = profile.get("horizon_years")
    if not _is_int(horizon) or not 1 <= horizon <= 40:
        raise ValueError("The horizon must be a whole number of years from 1 to 40.")
    capacity = profile.get("capacity")
    if capacity is not None and (not _is_number(capacity) or capacity < 0):
        raise ValueError("The largest loss you could absorb must be a number of dollars, zero or more.")
    reaction = profile.get("reaction_2022")
    if reaction is not None and reaction not in REACTIONS:
        raise ValueError(f"The 2022 reaction must be one of {', '.join(REACTIONS)}.")
    risk = profile.get("risk")
    if risk is not None and risk not in BANDS:
        raise ValueError(f"The tolerance band must be one of {', '.join(BANDS)}.")
    for key, name in (("esg", "values screening"), ("crypto", "crypto")):
        if not isinstance(profile.get(key), bool):
            raise ValueError(f"The {name} answer must be yes or no (true or false).")


# ---- limits: personas.json first, config defaults key by key ----

@functools.lru_cache(maxsize=None)
def _personas(path: str) -> dict:
    """data/personas.json, read once per path; a missing or unreadable file gives {} (every key then defaults)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _section(name: str, key: str | None = None) -> dict:
    node = _personas(str(config.PERSONAS_JSON)).get(name)
    if key is not None:
        node = node.get(key) if isinstance(node, dict) else None
    return node if isinstance(node, dict) else {}


def _merged(found: dict, defaults: dict) -> dict:
    """Key by key: the file's number when it is one, else the default (today's file may lack a key, pitfall 8)."""
    return {k: (found[k] if _is_number(found.get(k)) else v) for k, v in defaults.items()}


def _band_values(band: str) -> dict:
    return _merged(_section("risk_levels", band), config.DEFAULT_LIMITS[band])


def _thresholds() -> dict:
    return _merged(_section("thresholds"), config.DEFAULT_THRESHOLDS)


_PLAIN_NAMES = {"floor": "floor", "single_stock": "one-company limit", "sector": "one-sector limit",
                "crypto": "crypto limit", "scenario_stress": "shock-check limit", "recovery_days": "recovery limit",
                "risk_share": "risk-share warning level"}


def _checked_overrides(overrides: dict | None) -> dict:
    """The seven editable limits found in `overrides`, validated (numbers only; floors between −100 % and 0 %; shares
    between 0 % and 100 %). Every other key is ignored, so a whole limits dict can be passed in. None = no edit."""
    if overrides is not None and not isinstance(overrides, dict):
        raise ValueError("The limit edits must be a set of numbers named by limit.")
    clean = {}
    for key in OVERRIDE_KEYS:
        value = (overrides or {}).get(key)
        if value is None:
            continue
        name = _PLAIN_NAMES[key]
        if not _is_number(value):
            raise ValueError(f"The {name} must be a number.")
        if key in ("floor", "scenario_stress") and not -1 <= value <= 0:
            raise ValueError(f"The {name} is a drop, so it must be between {MINUS}100{PCT} and 0{PCT}.")
        if key in ("single_stock", "sector", "crypto", "risk_share") and not 0 <= value <= 1:
            raise ValueError(f"The {name} is a share of the money, so it must be between 0{PCT} and 100{PCT}.")
        if key == "recovery_days" and value < 0:
            raise ValueError(f"The {name} must be zero days or more.")
        clean[key] = float(value)
    return clean


def _real_edits(supplied: dict, overrides: dict | None, defaults: dict) -> dict:
    """Which supplied values are the user's edits. Plain edits ({"floor": -0.2}): all of them. A whole limits dict
    (it carries an "edited" list, as pipeline.recheck and the floor scan pass {**limits, "floor": f}): the earlier
    edits it lists, plus any value that differs from this profile's own default; scenario_stress is an edit only when
    listed, otherwise it follows the floor instead of staying pinned at the old floor's half."""
    listed = (overrides or {}).get("edited")
    if not isinstance(listed, (list, tuple)):
        return supplied
    return {k: v for k, v in supplied.items()
            if k in listed or (k != "scenario_stress" and round(v, 10) != round(defaults[k], 10))}


def _sector_name(name) -> str | None:
    """A GICS sector name as governance writes it, from any case ("energy" -> "Energy"); "Technology" and "Healthcare"
    read as Information Technology and Health Care. Anything else is None."""
    if not isinstance(name, str):
        return None
    key = " ".join(name.split()).lower()
    return next((s for s in GICS_SECTORS if s.lower() == key), None) or _SECTOR_ALIASES.get(key)


def _checked_sector_caps(raw) -> dict:
    """The industry limits the investor set ({GICS sector: the largest share of the money}, 0 = the industry is excluded),
    validated, in GICS order so the rows never depend on the order typed. None or {} = no industry limit."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("The industry limits must be a set of shares named by industry.")
    caps = {}
    for name, value in raw.items():
        sector = _sector_name(name)
        if sector is None:
            shown = " ".join(str(name).split())[:40]
            raise ValueError(f"“{shown}” is not an industry this replay knows; use one of: {', '.join(GICS_SECTORS)}.")
        if sector in caps:
            raise ValueError(f"{sector} has two limits; keep one.")
        if not _is_number(value) or not 0 <= value <= 1:
            raise ValueError(f"The {sector} limit is a share of the money, so it must be between 0{PCT} and 100{PCT}.")
        caps[sector] = float(value)
    return {s: caps[s] for s in GICS_SECTORS if s in caps}


def validate_sector_caps(raw) -> dict:
    """The industry limits as load_limits keeps them, or ValueError in one plain sentence (the API refuses a bad one
    before any replay, server._checked_caps)."""
    return _checked_sector_caps(raw)


def _from_words(raw, limits: dict, profile: dict) -> list[str]:
    """Which of this run's limits the investor's own words set (the AI reader's limits_hint, checked by code): a list of
    keys, never the words (limits reach the navigator, so no text the input guardrail did not screen rides in them). A
    key counts only for a limit this run uses: an edited limit, "sector_caps.<GICS sector>" for a capped industry, or a
    typed answer (capacity, esg, horizon_years). A {key: words} map gives its keys; anything else is ignored."""
    keys = list(raw) if isinstance(raw, dict) else raw if isinstance(raw, (list, tuple)) else []
    caps, said = limits.get("sector_caps") or {}, set()
    for key in keys:
        if not isinstance(key, str):
            continue
        if key in OVERRIDE_KEYS and key in limits["edited"]:
            said.add(key)
        elif key in WORD_KEYS and profile.get(key) is not None:       # an answer ("crypto": the yes or no, not a limit)
            said.add(key)
        elif key.startswith("sector_caps.") and _sector_name(key[len("sector_caps."):]) in caps:
            said.add("sector_caps." + _sector_name(key[len("sector_caps."):]))
        elif key in WORD_KEYS and profile.get(key) is not None:
            said.add(key)
    order = list(dict.fromkeys([*OVERRIDE_KEYS, *(f"sector_caps.{s}" for s in GICS_SECTORS), *WORD_KEYS]))  # crypto: once
    return [k for k in order if k in said]


def load_limits(profile: dict | None, overrides: dict | None = None, *, amount: float | None = None) -> dict | None:
    """The investor's limits (spec section 5). None profile, or no band to read, gives None ("Limits missing"), and so
    does {"none": True} in `overrides` ("No limits set", LIMITS_MODEL 16:40): no limit is assumed, every replay number
    still computes. `overrides["sector_caps"]` = the investor's industry limits ({GICS sector: share}, 0 = excluded;
    limits["sector_caps"] and "sector_caps" in `edited` only when one is set). `overrides["from_words"]` = the keys the
    investor's words set (see `_from_words`; limits["from_words"] only when one is kept).

    Band = profile["risk"], else the 2022 reaction (sold -> low, held -> moderate, bought -> high). Floor = the
    stricter (closer to 0) of the band floor and the capacity floor (-capacity / amount, when both are positive);
    floor_source names the capacity when it is at least as strict (a tie names the investor's own dollar answer,
    plan C Task 7). `overrides` are the user's edits: they replace values and are listed in `edited`; keys outside
    the seven editable limits are ignored, so a whole earlier limits dict (with "edited") can be passed back in.
    """
    if profile is None:
        return None
    validate_profile(profile)
    band = profile.get("risk") or config.REACTION_TO_RISK.get(profile.get("reaction_2022"))
    if band is None or (isinstance(overrides, dict) and overrides.get("none") is True):
        return None
    values, th = _band_values(band), _thresholds()
    band_floor, capacity = values["max_drawdown"], profile.get("capacity")
    capacity_floor = round(-capacity / amount, 10) if capacity and amount and capacity > 0 and amount > 0 else None
    by_capacity = capacity_floor is not None and capacity_floor >= band_floor
    floor = capacity_floor if by_capacity else band_floor
    crypto_yes = profile["crypto"]
    limits = {
        "floor": floor, "floor_source": "capacity" if by_capacity else "band", "band": band,
        "band_floor": band_floor, "capacity_floor": capacity_floor,
        "single_stock": values["max_single_stock"], "sector": values["max_sector"],
        "crypto": values["max_crypto"] if crypto_yes else 0.0, "crypto_tier": "soft" if crypto_yes else "preference",
        "scenario_stress": round(floor * th["scenario_stress_fraction"], 10),
        "recovery_days": round(profile["horizon_years"] * 365 * th["recovery_fraction_of_horizon"], 6),
        "risk_share": th["risk_share_warn"], "esg_indirect_warn": th["esg_indirect_warn"],
        "short_horizon_years": th["short_horizon_years"], "edited": [],
    }
    edits = _real_edits(_checked_overrides(overrides), overrides, limits)
    caps = _checked_sector_caps((overrides or {}).get("sector_caps"))
    limits.update(edits)
    if "floor" in edits and "scenario_stress" not in edits:  # the verdict moves with your limits
        limits["scenario_stress"] = round(edits["floor"] * th["scenario_stress_fraction"], 10)
    limits["edited"] = [k for k in OVERRIDE_KEYS if k in edits]
    if caps:                                                  # absent without one: the saved runs do not change
        limits["sector_caps"] = caps
        limits["edited"].append("sector_caps")
    said = _from_words((overrides or {}).get("from_words"), limits, profile)
    if said:
        limits["from_words"] = said
    guessed = [k for k in WORD_KEYS if k not in said and profile.get(k) is not None
               and k in _key_list((overrides or {}).get("assumed"))]
    if guessed:                     # limits-QA 17:25: answers the reader assumed (the You card's "assumed ✎"), never typed
        limits["assumed"] = guessed
    return limits


def _key_list(raw) -> set:
    """A list of keys (a {key: ...} map gives its keys); anything else is empty."""
    keys = list(raw) if isinstance(raw, dict) else raw if isinstance(raw, (list, tuple)) else []
    return {k for k in keys if isinstance(k, str)}


# ---- the section 5 rows: one private function per rule, each returning one row (or None = not checked) ----

def _row(rule, tier, status, value, limit, holding, reason):
    reason = reason.replace(" %", PCT)  # the net under every sentence: no line ever breaks between a number and its %
    return {"rule": rule, "tier": tier, "status": status, "value": value, "limit": limit,
            "holding": holding, "reason": reason}


def _whole_days(x: float) -> int:
    """A number of days to the day, ROUND_HALF_UP: 486.618 -> 487 (ledger 29: sentences state whole days)."""
    return int(Decimal(repr(float(x))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _days(n: int) -> str:
    return f"{n:,} day{'' if n == 1 else 's'}"


def _share(x: float) -> str:
    """A share of the money with one decimal: 0.4 -> '40.0 %'."""
    return f"{abs(round_pp(x)):.1f}{PCT}"


def _beyond_floor(value: float, limit: float) -> bool:
    return round_pp(value) < round_pp(limit)  # a floor is negative: beyond = deeper, after rounding to 0.1 pp


def _beyond_cap(value: float, limit: float) -> bool:
    return round_pp(value) > round_pp(limit)  # exactly at the limit passes


PROFILE_FIELDS = ("goal", "horizon_years", "risk", "esg", "crypto", "capacity", "reaction_2022")
ASSUMED = "set as your limit (assumed for this fictional profile)"      # spec ruling R13


def profile_is_card(profile) -> bool:
    """Spec ruling R13: a profile whose typed answers are exactly an investor card's (data/personas.json `pilots`) is a
    fictional profile, so its limits are assumptions; any other profile was typed by the investor. Numbers compare as
    numbers (the API sends 90000.0 for 90000)."""
    if not isinstance(profile, dict):
        return False
    mine = [profile.get(k) for k in PROFILE_FIELDS]
    cards = _personas(str(config.PERSONAS_JSON)).get("pilots")
    return any(isinstance(card, dict) and isinstance(card.get("profile"), dict)
               and [card["profile"].get(k) for k in PROFILE_FIELDS] == mine
               for card in (cards.values() if isinstance(cards, dict) else []))


def _rule_max_drawdown(profile, weights, a, lim):
    m, value, limit = a["metrics"], a["metrics"]["max_drawdown"], lim["floor"]
    span = f" from {m['peak_date']} to {m['trough_date']}" if m.get("peak_date") and m.get("trough_date") else ""
    # R35 (controller, 17:41): the floor is the % rule; its reason never carries dollars (they belong to the capacity row)
    fell = f"In this history the mix's worst drop was {fmt_pct(value)}{span}"
    capacity, edited = profile.get("capacity"), "floor" in lim.get("edited", ())
    card = not edited and profile_is_card(profile)      # R13: a card's limits are assumptions, typed ones are yours
    if not _beyond_floor(value, limit):
        return _row("max_drawdown", "hard", "pass", value, limit, None,
                    f"{fell}, inside the {fmt_pct(limit)} floor {ASSUMED if card else 'you set'}.")
    if edited:
        beyond = f"the {fmt_pct(limit)} floor you set"
    elif lim["floor_source"] == "capacity" and capacity:  # set by the dollars you could lose: the card's assumption, or yours
        beyond = (f"the {fmt_pct(limit)} floor {ASSUMED}" if card
                  else f"the {fmt_pct(limit)} floor from what you said you could lose")
    else:
        beyond = f"the {fmt_pct(limit)} floor of your tolerance band"
    return _row("max_drawdown", "hard", "fail", value, limit, None, f"{fell}, beyond {beyond}.")


_MIXED_WITH = re.compile(r"\(mixed with (?P<ids>[^)]*)\)")


def label_shown(label, events) -> str | None:
    """The evidence label as the page shows it: a co-event by its title and date, never its internal id
    ("Indicative (mixed with saudi_pipeline_2026)" -> "Indicative: mixed with Attack on Saudi Arabia's East-West
    pipeline, 2026-09-10"). An id the catalog does not know becomes "another shock". Any other label is unchanged."""
    m = _MIXED_WITH.search(str(label or ""))
    if not m:
        return label
    names = {str(e.get("event_id")): f"{e.get('title') or 'another shock'}, {str(e.get('date') or '')[:10]}".rstrip(", ")
             for e in events or [] if isinstance(e, dict)}
    parts = [names.get(i.strip(), "another shock") for i in m["ids"].split(",") if i.strip()]
    return re.sub(r"(?<=[A-Za-z])'(?=[A-Za-z])", "’", str(label)[:m.start()].rstrip() + ": mixed with " + "; ".join(parts))


def _rule_scenario_stress(profile, weights, a, lim):
    """The soft shock check (ledger 30): a warn ("Caution") beyond its threshold, never a fail. "No close precedent"
    only when the tool gave no value; "too few separate episodes to conclude" when fewer than 2 clean episodes back it
    (a value with 0 clean episodes means only a mixed episode counted, as at 2025-01-31)."""
    if "scenario_stress" not in a:
        return None
    value, limit, n = a["scenario_stress"], lim["scenario_stress"], a.get("scenario_episodes")
    named = a.get("scenario_family")                  # "" = the navigator named no family (it abstained, ledger 30)
    family = named or "shock"
    label = a.get("scenario_label_shown") or a.get("scenario_label")      # titles and dates, never an event id
    tag = f" ({label})" if label and label != "Measured" else ""
    if value is None:
        for_what = f"{named} shocks" if named else "this question"
        return _row("scenario_stress", "soft", "warn", value, limit, None,
                    f"There is no close precedent at this date for {for_what}, so the shock check cannot conclude.")
    if n is not None and n < MIN_SHOCK_EPISODES:
        known = "No clean" if n == 0 else f"Only {n} clean"
        return _row("scenario_stress", "soft", "warn", value, limit, None,
                    f"{known} {family} episode{'' if n == 1 else 's'} {'is' if n == 1 else 'are'} known at this date"
                    f"{tag}: {TOO_FEW}.")
    over = _beyond_floor(value, limit)
    which = f"the {n} separate earlier" if n else "the separate earlier"
    return _row("scenario_stress", "soft", "warn" if over else "pass", value, limit, None,
                f"In {which} {family} episodes the worst clean one cost {_share(value)}, "
                f"{'beyond' if over else 'inside'} half your floor ({_plain(limit)}){tag}.")


def _uni(a) -> dict:
    return {r["ticker"]: r for r in a.get("universe") or []}


def _largest(shares: dict):
    """(ticker, share) of the biggest entry, ties broken by ticker so the row never depends on dict order."""
    return min(shares.items(), key=lambda kv: (-kv[1], kv[0])) if shares else (None, 0.0)


def _unseen(weights, a) -> list[str]:
    """Held equity ETFs that were not opened up: today's look-through ran in direct mode (a fresh clone has no
    holdings list, ledger 30). A past date has no look-through at all (direct by design, spec 5): nothing to say."""
    look = a.get("lookthrough")
    if not look or look.get("mode") != "direct":
        return []
    uni = _uni(a)
    return sorted(t for t, w in weights.items() if w and w > 0 and uni.get(t, {}).get("asset_class") == "etf_equity")


def _unseen_clause(names: list[str], sectors: bool = False) -> str:
    """The clause a look-through row carries when a held equity fund was not opened (ledger 30): "XIU.TO was not looked
    through, so the companies inside it are not known from holdings". It joins the row's own sentence (a reason is one
    sentence, spec 5); `sectors` adds "and their sectors" for the sector row."""
    one = len(names) == 1
    inside = f"the companies inside {'it' if one else 'them'}" + (", and their sectors," if sectors else "")
    return f"{', '.join(names)} {'was' if one else 'were'} not looked through, so {inside} are not known from holdings"


def _cannot_check(limit_words: str, names: list[str], sectors: bool = False) -> str:
    """The sentence of a look-through row whose limit cannot be checked because a held fund was not opened."""
    return f"The {limit_words} cannot be checked: {_unseen_clause(names, sectors)}."


def _stock_shares(weights, a) -> dict:
    """Single companies: look-through totals (direct + inside ETFs); past dates, the direct equity weights."""
    look = a.get("lookthrough")
    if look:
        return {t: s["total"] for t, s in look.get("stocks", {}).items()}
    uni = _uni(a)
    return {t: w for t, w in weights.items() if uni.get(t, {}).get("asset_class") == "equity"}


def _rule_single_stock(profile, weights, a, lim):
    """One company's share of the money. A held fund that was not opened (a fresh clone, ledger 30) leaves the companies
    inside it unknown: a company already beyond the limit stays a fail (what is known is still said), anything else is a
    warn with no value, never a pass with a 0.0."""
    shares, limit = _stock_shares(weights, a), lim["single_stock"]
    ticker, value = _largest(shares)
    unseen = _unseen(weights, a)
    over = ticker is not None and _beyond_cap(value, limit)
    if unseen and not over:
        return _row("single_stock", "soft", "warn", None, limit, None,
                    _cannot_check(f"{_plain(limit)} limit for one company", unseen))
    if ticker is None:
        return _row("single_stock", "soft", "pass", 0.0, limit, None,
                    f"No single company is in the mix; the limit is {_plain(limit)} for one company.")
    tail = f"; {_unseen_clause(unseen)}" if unseen else ""
    return _row("single_stock", "soft", "fail" if over else "pass", value, limit, ticker,
                f"{ticker} is {_share(value)} of the money, {'beyond' if over else 'inside'} the "
                f"{_plain(limit)} limit for one company{tail}.")


def _sector_shares(weights, a) -> dict:
    """Equity sectors only (GICS names); bonds, gold, crypto and broad-market funds are asset classes, not sectors.
    Look-through when available; past dates use direct lines, an ETF counting only if its own sector is a GICS one."""
    look = a.get("lookthrough")
    if look:
        return {s: w for s, w in look.get("sectors", {}).items() if s in GICS_SECTORS}
    uni, out = _uni(a), {}
    for ticker, w in weights.items():
        sector = uni.get(ticker, {}).get("sector")
        if sector in GICS_SECTORS:
            out[sector] = out.get(sector, 0.0) + w
    return out


def _rule_sector(profile, weights, a, lim):
    """One sector's share of the money; a held fund that was not opened is handled as in `_rule_single_stock`."""
    limit = lim["sector"]
    name, value = _largest(_sector_shares(weights, a))
    unseen = _unseen(weights, a)
    over = name is not None and _beyond_cap(value, limit)
    if unseen and not over:
        return _row("sector", "soft", "warn", None, limit, None,
                    _cannot_check(f"{_plain(limit)} limit for one sector", unseen, sectors=True))
    if name is None:
        return _row("sector", "soft", "pass", 0.0, limit, None,
                    f"No equity sector is in the mix; the limit is {_plain(limit)} for one sector.")
    uni, stocks = _uni(a), _stock_shares(weights, a)
    inside = {t: s for t, s in stocks.items() if uni.get(t, {}).get("sector") == name}
    holding = _largest(inside)[0]  # the largest company of that sector: the cause shared with single_stock
    tail = f"; {_unseen_clause(unseen, sectors=True)}" if unseen else ""
    return _row("sector", "soft", "fail" if over else "pass", value, limit, holding,
                f"{name} is {_share(value)} of the money, {'beyond' if over else 'inside'} the "
                f"{_plain(limit)} limit for one sector{tail}.")


def _sector_cap_rows(profile, weights, a, lim) -> list[dict]:
    """One row per industry the investor limited (limits["sector_caps"], GICS order; none set, no rows): the look-through
    share of that industry (direct lines on a past date, as `_rule_sector`) against the share they set, after round_pp
    (exactly at the limit passes). Tier soft; a 0 % limit excludes the industry, so it is hard (Outside your limits). A
    held fund that was not opened makes a row that is not already past its limit a warn with no value; the holding is the
    largest company of that industry, the cause shared with single_stock and sector (one cause, one fail)."""
    caps = lim.get("sector_caps") or {}
    if not caps:
        return []
    shares, unseen, uni, stocks = _sector_shares(weights, a), _unseen(weights, a), _uni(a), _stock_shares(weights, a)
    rows = []
    for sector, cap in caps.items():
        rule, value = SECTOR_CAP + sector, shares.get(sector, 0.0)
        excluded = round_pp(cap) == 0
        tier, over = ("hard" if excluded else "soft"), _beyond_cap(value, cap)
        if unseen and not over:
            words = f"exclusion of {sector} (0{PCT})" if excluded else f"{_plain(cap)} you set for {sector}"
            rows.append(_row(rule, tier, "warn", None, cap, None, _cannot_check(words, unseen, sectors=True)))
            continue
        holding = _largest({t: s for t, s in stocks.items() if uni.get(t, {}).get("sector") == sector})[0]
        tail = f"; {_unseen_clause(unseen, sectors=True)}" if unseen else ""
        if excluded:          # LIMITS_MODEL CONFLICTS (16:55): an exclusion reads "excluded (0 %)", never "a 0 % limit"
            held = (_share(value) if over else "nothing" if value <= 0
                    else f"under 0.05{PCT}")
            note = f" (0.0{PCT} after rounding)" if not over and value > 0 else ""
            reason = f"In this replay the mix held {held} in {sector}{note}, an industry you excluded (0{PCT}){tail}."
        elif over:
            reason = f"In this replay the mix held {_share(value)} in {sector}, past the {_plain(cap)} you set{tail}."
        else:
            reason = f"In this replay the mix held {_share(value)} in {sector}, inside the {_plain(cap)} you set."
        rows.append(_row(rule, tier, "fail" if over else "pass", value, cap, holding if value > 0 else None, reason))
    return rows


def _rule_crypto(profile, weights, a, lim):
    uni, limit = _uni(a), lim["crypto"]
    coins = {t: w for t, w in weights.items() if uni.get(t, {}).get("asset_class") == "crypto"}
    value = sum(coins.values())
    ticker = _largest(coins)[0]
    over = _beyond_cap(value, limit)
    if coins and round_pp(value) == 0:  # under 0.05 %: not none, and not enough to count
        reason = f"Crypto is under 0.05{PCT} of the money (0.0{PCT} after rounding); the limit is {_plain(limit)}."
    elif lim["crypto_tier"] == "preference":
        reason = (f"{ticker} makes crypto {_share(value)} of the money, but you said no to crypto." if over
                  else "No crypto is in the mix, as you asked.")
    elif over:
        reason = f"Crypto is {_share(value)} of the money, beyond the {_plain(limit)} limit."
    else:
        reason = f"Crypto is {_share(value)} of the money, inside the {_plain(limit)} limit."
    return _row("crypto", lim["crypto_tier"], "fail" if over else "pass", value, limit, ticker, reason)


# Ruling of Sun Nov 15 (CTO review, approved): when the investor turned the values screen on, a company owned
# DIRECTLY that the screen excludes breaks a hard limit (Outside your limits), like the floor; a flag INSIDE a fund stays
# a warning (Caution). The row exists only when the screen is on.
ESG_DIRECT_TIER = "hard"


def _rule_esg_direct(profile, weights, a, lim):
    if not profile["esg"]:
        return None
    uni, flagged = _uni(a), set(a.get("esg_flags") or ())
    hits = {t: w for t, w in weights.items()
            if w > 0 and (uni.get(t, {}).get("sector") == "Energy" or t in flagged)}
    value, ticker = sum(hits.values()), _largest(hits)[0]
    if not hits:
        return _row("esg_direct", ESG_DIRECT_TIER, "pass", 0.0, 0.0, None,
                    f"No company excluded by your values screen is owned directly; the limit is 0{PCT}.")
    names = ", ".join(sorted(hits, key=lambda t: (-hits[t], t)))
    over = _beyond_cap(value, 0.0)
    if not over:  # under 0.05 %: on the screen, but not enough to count
        return _row("esg_direct", ESG_DIRECT_TIER, "pass", value, 0.0, ticker,
                    f"{names} {'is' if len(hits) == 1 else 'are'} excluded by your values screen, but "
                    f"{'it is' if len(hits) == 1 else 'together they are'} under 0.05{PCT} of the money "
                    f"(0.0{PCT} after rounding); the limit is 0{PCT}.")
    return _row("esg_direct", ESG_DIRECT_TIER, "fail" if over else "pass", value, 0.0, ticker,
                f"{names} {'is' if len(hits) == 1 else 'are'} owned directly ({_share(value)} of the money) and "
                f"excluded by the values screen you asked for; the limit is 0{PCT}.")


def _rule_esg_indirect(profile, weights, a, lim):
    look = a.get("lookthrough")
    if not profile["esg"] or not look:
        return None
    limit, unseen = lim["esg_indirect_warn"], _unseen(weights, a)
    if unseen:  # no holdings list on this machine: the companies inside a held equity fund are unknown, never a pass
        return _row("esg_indirect", "warn", "warn", None, limit, None,
                    _cannot_check(f"{_plain(limit)} warning level for excluded companies inside your funds", unseen))
    inside = look.get("esg_indirect") or {}
    value = sum(inside.values())
    warn = round_pp(value) >= round_pp(limit)  # reaching the level warns (spec: "≥ 1 %")
    return _row("esg_indirect", "warn", "warn" if warn else "pass", value, limit, _largest(inside)[0],
                f"Companies excluded by your values screen add up to {_share(value)} of the money inside your funds, "
                f"{'at or above' if warn else 'below'} the {_plain(limit)} warning level.")


def _rule_risk_concentration(profile, weights, a, lim):
    risk = a.get("risk")
    if not risk or risk.get("degenerate") or not risk.get("shares"):
        return None
    ticker, value = _largest(risk["shares"])
    limit, over = lim["risk_share"], _beyond_cap(value, lim["risk_share"])
    return _row("risk_concentration", "warn", "warn" if over else "pass", value, limit, ticker,
                f"{ticker} carries {_plain(value)} of the portfolio's risk, "
                f"{'beyond' if over else 'inside'} the {_plain(limit)} warning level.")


def _rule_recovery(profile, weights, a, lim):
    m, limit = a["metrics"], lim["recovery_days"]
    recovered = m.get("recovery_days") is not None
    days = m["recovery_days"] if recovered else m.get("days_since_trough")
    half = lim["floor"] * _thresholds()["scenario_stress_fraction"]
    if not _beyond_floor(m["max_drawdown"], half):  # a shallow drop is not asked to recover quickly
        return _row("recovery", "warn", "pass", days, limit, None,
                    f"The worst drop ({fmt_pct(m['max_drawdown'])}) is not deeper than half your floor "
                    f"({fmt_pct(half)}), so its recovery time is not a concern.")
    over = days is not None and days > limit  # the limit stays unrounded (ledger 10); only the sentence shows whole days
    shown = _whole_days(limit)
    took = (f"The worst drop took {_days(_whole_days(days))} to recover" if recovered
            else f"The worst drop was {_days(_whole_days(days))} past its low and had not recovered")
    side = "a fraction of a day beyond" if over and days <= shown else "beyond" if over else "inside"
    # spec ruling R1 (Sun Nov 15): a past-tense fact, never a permission word ("your horizon allows")
    return _row("recovery", "warn", "warn" if over else "pass", days, limit, None,
                f"{took}; your horizon gives about {_days(shown)}, so that was {side} it.")


def _rule_short_horizon(profile, weights, a, lim):
    years, level = profile["horizon_years"], lim["short_horizon_years"]
    short = years < level
    return _row("short_horizon", "warn", "warn" if short else "pass", years, level, None,
                f"You need the money in {years} year{'' if years == 1 else 's'}, "
                f"{'sooner than' if short else 'later than'} the {level}-year short-horizon level.")


def _gap_part(etf: str, missing: set) -> str:
    if missing == {"holdings"}:
        return f"{etf}'s list of holdings is missing, which leaves the companies inside it unknown"
    if missing == {"sectors"}:
        return f"{etf}'s sector split is missing, which leaves its sectors unknown (not zero)"
    return (f"{etf}'s holdings and sector split are missing, which leaves the companies and sectors inside it "
            "unknown (not zero)")


def _rule_missing_data(profile, weights, a, lim):
    """The one place unknowns surface (unknown is never a pass, ledger 29): price gaps and USD prices with no USD/CAD
    rate yet (the tickers the data layer flagged), a fund whose holdings or sector split is missing (look-through
    `gaps`), held equity funds a direct-mode run could not open (a fresh clone without the holdings list, ledger 30),
    and a series too short or too flat to show how the mix behaves. Everything is read from the analysis
    keys a saved run keeps, so a recheck writes the same row. value = the number of named gaps; limit = 0.
    `analysis["missing_data"]` names the real cause of each flag (ledger 30): a bare ticker is a price gap of more
    than 3 days, a ticker followed by `NO_RATE` is a USD price with no USD/CAD rate yet (see `_flagged_lines`)."""
    entries = {str(e) for e in a.get("missing_data") or ()}
    rated = sorted(e[:-len(NO_RATE)] for e in entries if e.endswith(NO_RATE))
    tickers = sorted(e for e in entries if not e.endswith(NO_RATE))
    gaps: dict[str, set] = {}
    for gap in (a.get("lookthrough") or {}).get("gaps") or ():
        gaps.setdefault(gap["etf"], set()).add(gap["missing"])
    unseen = _unseen(weights, a)
    metrics = a.get("metrics") or {}
    flat = "volatility" in metrics and (metrics["volatility"] is None or metrics["volatility"] <= ZERO_VOL)
    if not (tickers or rated or gaps or unseen or flat):
        return None
    parts = []
    if tickers:
        parts.append(f"{', '.join(tickers)} {'has' if len(tickers) == 1 else 'have'} a price gap of more than "
                     f"{PRICE_GAP_DAYS} days in this history")
    if rated:
        parts.append(f"{', '.join(rated)} {'has' if len(rated) == 1 else 'have'} a USD price with no USD/CAD rate yet "
                     "in this history")
    parts += [_gap_part(etf, gaps[etf]) for etf in sorted(gaps)]
    if unseen:
        parts.append(f"{', '.join(unseen)} could not be looked through (no ETF holdings list for this run), so the "
                     f"companies and sectors inside {'it' if len(unseen) == 1 else 'them'} are unknown")
    if flat:
        parts.append("the price history in this window is too short or too flat to show how the mix behaves")
    named = len(set(tickers) | set(rated) | set(gaps) | set(unseen)) + (1 if flat else 0)
    return _row("missing_data", "warn", "warn", named, 0, None,
                f"{'; '.join(parts)}, so results that rest on {'it' if len(parts) == 1 else 'them'} are less certain.")


# ---- where each row's limit came from (LIMITS_MODEL 16:40: set by you > from your words > assumed) ----

_RULE_LIMIT = {"max_drawdown": "floor", "scenario_stress": "scenario_stress", "single_stock": "single_stock",
               "sector": "sector", "crypto": "crypto", "esg_direct": "esg", "esg_indirect": "esg",
               "risk_concentration": "risk_share", "recovery": "recovery_days", "short_horizon": "short_horizon_years"}


def limit_source(rule, limits, profile=None) -> str | None:
    """Where the limit one row checks came from: "words" (the investor's words set it: limits["from_words"]), "you" (typed:
    limits["edited"], an industry limit, or a typed profile's own answer: the dollars you could lose, the values screen,
    no crypto) or "assumed" (the profile's risk band, a rule of thumb, or a persona card's answers, R13). None for a row
    with no limit of its own (missing_data) or no limits. The rows keep the ledger's keys; pipeline adds this as `source`."""
    if not isinstance(limits, dict) or not isinstance(rule, str):
        return None
    said, edited = set(limits.get("from_words") or ()), set(limits.get("edited") or ())
    guessed = set(limits.get("assumed") or ())
    if rule.startswith(SECTOR_CAP):
        return "words" if "sector_caps." + rule[len(SECTOR_CAP):] in said else "you"    # never assumed
    key = _RULE_LIMIT.get(rule)
    if key is None:
        return None
    if key in said:
        return "words"
    if key in edited:
        return "you"
    yours = "assumed" if profile is None or profile_is_card(profile) else "you"      # a typed profile's own answer

    def answer(k):                  # your words, else assumed by the reader (limits["assumed"]), else as the profile is
        return "words" if k in said else "assumed" if k in guessed else yours
    if rule == "max_drawdown" and limits.get("floor_source") == "capacity":       # the dollars you could lose set it
        return answer("capacity")
    if rule in ("esg_direct", "esg_indirect"):                                      # the values screen you turned on
        return answer("esg")
    if rule == "crypto" and limits.get("crypto_tier") == "preference":              # "no crypto": your answer
        return answer("crypto")
    return "assumed"


# ---- the checklist, the verdict, the counts, the order ----

_RULES = (("max_drawdown", _rule_max_drawdown), ("scenario_stress", _rule_scenario_stress),
          ("single_stock", _rule_single_stock), ("sector", _rule_sector), ("crypto", _rule_crypto),
          ("esg_direct", _rule_esg_direct), ("esg_indirect", _rule_esg_indirect),
          ("risk_concentration", _rule_risk_concentration), ("recovery", _rule_recovery),
          ("short_horizon", _rule_short_horizon), ("missing_data", _rule_missing_data))


def check_profile(profile: dict | None, weights: dict, analysis: dict) -> list[dict]:
    """The checklist rows, in config.RULE_IDS order. No profile (or no band) gives [], so verdict() is None.

    `analysis` is plan B Task 4's shape: metrics, lookthrough (None for past dates), universe, esg_flags, the
    scenario_* keys and the optional loss_dollars, missing_data, risk, limits, amount. An absent optional key
    means that rule is not checked (no row). The `missing_data` row also reads two optional signs of an unknown:
    `lookthrough["gaps"]` (a fund with no holdings or sector rows) and `metrics["volatility"]` (None or zero: a series
    too short or too flat to judge). `missing_data` entries are bare tickers (a price gap) or a ticker followed by
    `NO_RATE` (a USD price with no USD/CAD rate yet). A `lookthrough` in mode "direct" on a held equity fund (today's
    run without a holdings list) turns the single-company, sector and values rows into warns (ledger 30).
    `analysis["limits"]` present and None = no limits ("No limits set"): no rows, none assumed. The industry limits the
    investor set (limits["sector_caps"]) add one row each right after the sector row (`_sector_cap_rows`)."""
    if profile is None:
        return []
    validate_profile(profile)
    limits = (analysis["limits"] if "limits" in analysis
              else load_limits(profile, amount=analysis.get("amount")))
    if limits is None:
        return []
    rows = [row for row in (rule(profile, weights, analysis, limits) for _, rule in _RULES) if row is not None]
    caps = _sector_cap_rows(profile, weights, analysis, limits)
    if caps:
        at = next((i + 1 for i, row in enumerate(rows) if row["rule"] == "sector"), len(rows))
        rows[at:at] = caps
    return rows


def _caveat(row: dict) -> bool:
    """A warn that keeps the verdict from reading plain "Inside your limits" (spec 5, ledger 30): a named gap
    (`missing_data`: unknown is never a pass) or a shock-check Caution that CONCLUDES, i.e. a value beyond its threshold
    resting on 2 or more separate episodes (soft evidence: the label is warn since ledger 30, the verdict it gave as a
    soft fail is unchanged). A check that cannot conclude is a plain warn that never moves the verdict: no close
    precedent (no value), or "too few separate episodes to conclude" (n < 2), whatever value it carries.

    The row has no episode count (its keys are fixed by the ledger and `verdict` sees only rows), so a check that cannot
    conclude is told by its own spec phrase `TOO_FEW`, which `_rule_scenario_stress` writes from the same constant."""
    if row["status"] != "warn":
        return False
    if row["rule"] == "missing_data":
        return True
    return (row["rule"] == "scenario_stress" and _is_number(row["value"]) and _is_number(row["limit"])
            and _beyond_floor(row["value"], row["limit"]) and TOO_FEW not in str(row.get("reason") or ""))


def _inconclusive(row: dict) -> bool:
    """A shock check that could not conclude: no close precedent (no value: aliens, a pandemic, an election, "the Fed
    cuts to zero") or too few separate episodes (`TOO_FEW`). Its row keeps its warn status and its words (a neutral
    "could not conclude"); the verdict ignores it, so it is never one of the two warns (jury QA N1-N3, H5)."""
    return (row["rule"] == "scenario_stress" and row["status"] == "warn"
            and (not _is_number(row["value"]) or TOO_FEW in str(row.get("reason") or "")))


def verdict(checks: list[dict]) -> str | None:
    """Any hard fail: Incompatible; else any soft or preference fail, any caveat (see `_caveat`) or two or more
    warns (a shock check that could not conclude is not one, see `_inconclusive`): Tension; else Compatible. No rows:
    None."""
    if not checks:
        return None
    if any(c["tier"] == "hard" and c["status"] == "fail" for c in checks):
        return "Incompatible"
    soft_fail = any(c["tier"] in ("soft", "preference") and c["status"] == "fail" for c in checks)
    warns = sum(c["status"] == "warn" and not _inconclusive(c) for c in checks)
    if soft_fail or any(_caveat(c) for c in checks) or warns >= 2:
        return "Tension"
    return "Compatible"


def count_fails(checks: list[dict]) -> int:
    """One cause, one fail: fails sharing a holding count once; a fail with no holding counts on its own."""
    fails = [c for c in checks if c["status"] == "fail"]
    return len({c["holding"] for c in fails if c["holding"] is not None}) + sum(c["holding"] is None for c in fails)


def check_order(checks: list[dict], profile: dict | None) -> list[str]:
    """Rule ids, the check that decided the verdict first: the binding row (first failing hard row, else the first
    failing soft or preference row, else the first warn), then the goal's lead rule, then the other fails, the warns
    and the passes, each in row order. No duplicates; no rows, no order."""
    if not checks:
        return []
    binding = (next((c for c in checks if c["status"] == "fail" and c["tier"] == "hard"), None)
               or next((c for c in checks if c["status"] == "fail"), None)
               or next((c for c in checks if c["status"] == "warn"), None))
    present, order = {c["rule"] for c in checks}, []
    wanted = [binding["rule"] if binding else None, GOAL_LEAD.get((profile or {}).get("goal"))]
    wanted += [c["rule"] for status in ("fail", "warn", "pass") for c in checks if c["status"] == status]
    for rule in wanted:
        if rule in present and rule not in order:
            order.append(rule)
    return order


# ---- data/esg_flags.csv, as known at a date ----

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def load_esg_flags(as_of: str, *, path=None) -> set[str]:
    """Tickers of data/esg_flags.csv usable at `as_of` (no look-ahead, red gate 3; ledger 16). Category flags (ESGV's
    exclusion categories) are a values definition, so they apply at every as_of. Only `controversy_*` flags come
    from a company filing: one counts only when its source_date is on or before as_of (a filing is unknown before
    its filing date; no date, no flag). A missing file gives the empty set."""
    if not isinstance(as_of, str) or not _ISO_DATE.fullmatch(as_of):
        raise ValueError("as_of must be a date written like 2026-11-12.")
    try:
        with open(path or config.ESG_FLAGS_CSV, encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except FileNotFoundError:
        return set()
    flags = set()
    for row in rows:
        ticker = (row.get("ticker") or "").strip()
        if not ticker:
            continue
        if (row.get("flag") or "").strip().startswith("controversy_"):
            filed = (row.get("source_date") or "").strip()
            if not _ISO_DATE.fullmatch(filed) or filed > as_of:
                continue
        flags.add(ticker)
    return flags


# ---- evaluate: the one judge (plan B Task 5; every caller judges through it) ----

def _as_of_date(as_of) -> str:
    if not isinstance(as_of, str) or not _ISO_DATE.fullmatch(as_of):
        raise ValueError("as_of must be a date written like 2026-11-12.")
    return as_of


def _esg_set(esg_flags, as_of: str) -> set:
    """The values-screen tickers: the caller's collection (the scramble passes its copy of the file), else
    data/esg_flags.csv as known at `as_of` (`load_esg_flags`: controversy flags only once filed)."""
    if esg_flags is None:
        return load_esg_flags(as_of)
    if isinstance(esg_flags, (str, bytes, os.PathLike)) or not hasattr(esg_flags, "__iter__"):
        raise ValueError("The values-screen flags must be a collection of tickers.")
    return {str(t).strip() for t in esg_flags if str(t).strip()}


def _no_rate_day(market: dict, ticker: str, day: str) -> bool:
    """True when `ticker` has a listing-currency price on `day` but no CAD price: a USD price with no USD/CAD rate yet
    (tools.data never back-fills a rate). False when the frames are missing: the flag is then a price gap."""
    prices, local = market.get("prices"), market.get("local")
    if prices is None or local is None or ticker not in prices.columns or ticker not in local.columns:
        return False
    when = pd.Timestamp(day)
    if when not in prices.index or when not in local.index:
        return False
    return bool(pd.isna(prices.at[when, ticker]) and pd.notna(local.at[when, ticker]))


def _flagged_lines(weights: dict, market: dict, as_of: str) -> list[str]:
    """The `analysis["missing_data"]` entries: held tickers the data layer flagged on or before `as_of` (tools.data
    `flags`; dates after `as_of` are ignored, red gate 3). Two causes share the flag (ledger 30) and the entry says which:
    a bare ticker is a price gap of more than 3 days, a ticker followed by `NO_RATE` is a USD price with no USD/CAD rate
    yet; a ticker with both has both entries. Strings, so a saved run keeps them (pipeline.ANALYSIS_KEYS) and a
    recheck names the same cause."""
    flags, out = market.get("flags") or {}, set()
    for t, w in weights.items():
        if not (w and w > 0):
            continue
        key = str(t).upper()
        days = [d for d in flags.get(key) or flags.get(t) or () if d <= as_of]
        no_rate = [d for d in days if _no_rate_day(market, key, d)]
        if len(no_rate) < len(days):
            out.add(key)
        if no_rate:
            out.add(key + NO_RATE)
    return sorted(out)


def _no_family_stress(as_of: str) -> dict:
    """The shock check when the navigator named no family (it abstained, ledger 30): nothing is replayed, so there is no
    close precedent. The keys of tools.events.scenario_stress."""
    return {"value": None, "n_episodes": 0, "worst_event_id": None, "episodes": [], "excluded": [], "label": "Can't say",
            "source": "No shock family was named for this question, so no precedent was replayed.", "as_of": as_of}


def _loss_dollars(amount, metrics: dict):
    """The one dollar figure for the worst drop: amount x drawdown, a positive number of dollars (ledger 14 and 19:
    never peak value minus trough value). None without an amount above zero or without a drawdown."""
    drop = metrics["max_drawdown"]
    return None if not amount or amount <= 0 or drop >= 0 else float(amount) * -drop


def evaluate(profile, weights, families, as_of, *, market=None, events=None, today=None, limits=None, amount=None,
             detail=True, esg_flags=None) -> dict:
    """Judge a portfolio: replay it, run the shock check, look through its funds, write the checklist, give the verdict.

    Returns exactly {weights, series, metrics, worst_rolling, stress, turbulence, lookthrough, exposure, risk,
    diversification, analysis, checks, verdict, kpis, limits}; `kpis` = {max_drawdown, scenario_stress,
    recovery_days, exposure_canada}, each {"value", "limit"}. Nothing dated after `as_of` reaches a tool. No profile
    (or no band to read): checks [], verdict None, every kpi limit None. `limits` = the user's edits (load_limits);
    a recheck is `evaluate(..., limits=edits)` with no model call. `today` defaults to `as_of == DATASET_END`: only
    today looks through the ETFs (a past date uses direct lines, so the ETF snapshot of today never leaks into it).
    `detail=False` skips `turbulence` and `diversification` only (the size curve and the menu call this 41+ times).
    `families`: None = none named (all four are replayed); [] = the navigator abstained (ledger 30): nothing is replayed
    and the shock check is a warn with no value, "no close precedent at this date". `esg_flags` = an optional collection
    of tickers (the scramble passes its copy); None reads data/esg_flags.csv at `as_of`. `analysis["loss_dollars"]` = amount x drawdown, the only dollar figure the sentences use.
    A date with no price history returns {"error": one sentence}; bad weights, profile or limits raise ValueError.
    """
    as_of = _as_of_date(as_of)
    if amount is not None and not _is_number(amount):
        raise ValueError("The amount must be a number of dollars.")
    limits_out = load_limits(profile, limits, amount=amount)          # first: a bad profile or edit fails before any replay
    market = load_market(as_of) if market is None else market
    events = load_events(as_of, market=market) if events is None else events
    today = (as_of == DATASET_END) if today is None else today
    families = list(config.FAMILIES) if families is None else list(families)    # None: none named, all four; []: abstained
    universe = market["universe"]
    series = portfolio_series(weights, as_of=as_of, market=market)
    if not series["dates"]:
        return {"error": f"There is no price history on or before {as_of}, so there is nothing to replay."}
    rf = mean_policy_rate(series["dates"][0], as_of, as_of, market=market)
    metrics = risk_metrics(series, rf)
    worst_rolling = worst_rolling_drop(series)
    stress = (scenario_stress(weights, families, as_of, market=market, events=events) if families
              else _no_family_stress(as_of))
    shocks = turbulence(weights, list(config.FAMILIES), as_of, market=market, events=events) if detail else None
    flagged = _esg_set(esg_flags, as_of)
    look = look_through(weights, universe=universe, esg_flags=flagged, as_of=as_of) if today else None
    seen = look if look is not None else look_through(weights, holdings=pd.DataFrame(), universe=universe,
                                                      esg_flags=flagged, as_of=as_of)   # past date: direct lines only
    exposure = country_exposure(weights, lookthrough=seen, universe=universe)
    risk = risk_contributions(weights, as_of, market=market)
    spread = (diversification(weights, as_of, lookthrough=seen, universe=universe, market=market)
              if detail else None)
    analysis = {
        "metrics": metrics, "lookthrough": look, "universe": universe.to_dict("records"), "esg_flags": flagged,
        "scenario_stress": stress["value"], "scenario_episodes": stress["n_episodes"],
        "scenario_family": " + ".join(config.FAMILY_LABELS.get(f, f) for f in families),
        "scenario_label": stress.get("label"), "scenario_label_shown": label_shown(stress.get("label"), events),
        "loss_dollars": _loss_dollars(amount, metrics),
        "missing_data": _flagged_lines(weights, market, as_of), "risk": risk, "limits": limits_out, "amount": amount}
    checks = check_profile(profile, weights, analysis)
    lim = limits_out or {}
    recovery = metrics["recovery_days"] if metrics["recovery_days"] is not None else metrics["days_since_trough"]
    kpis = {"max_drawdown": {"value": metrics["max_drawdown"], "limit": lim.get("floor")},
            "scenario_stress": {"value": stress["value"], "limit": lim.get("scenario_stress")},
            "recovery_days": {"value": recovery, "limit": lim.get("recovery_days")},
            "exposure_canada": {"value": (look or exposure)["countries"].get("CAN", 0.0), "limit": None}}
    return {"weights": dict(weights), "series": series, "metrics": metrics, "worst_rolling": worst_rolling,
            "stress": stress, "turbulence": shocks, "lookthrough": look, "exposure": exposure, "risk": risk,
            "diversification": spread, "analysis": analysis, "checks": checks, "verdict": verdict(checks),
            "kpis": kpis, "limits": limits_out}
