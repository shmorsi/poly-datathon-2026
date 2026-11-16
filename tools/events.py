"""The storm catalog, the time rule, campaign episodes and one storm's impact (spec section 10; plan A Task 9).

The rules, in the spec's words:
  - TIME RULE (red gate 3): a storm is `known` at `as_of` only if its date <= as_of AND its t+20
    trading day (the 20th day after t0 on the union TSX+US calendar, never wall-clock days) is
    <= as_of. Dated <= as_of with an incomplete window = `in_progress`: greyed, never used in an
    impact, a check or a prompt, and its description is withheld (title and date only, ledger 15:
    the text carries later facts). Rows dated after `as_of` do not exist for the caller.
  - t0 is per asset: the first day its own exchange trades on or after the storm's date (TSX was
    closed on 2023-10-09, pitfall 6). The baseline is its last traded price before the storm's t0;
    for crypto it is the UTC row dated `announced - 1 day` (pitfall 7).
  - Inside a window the weights are fixed at t-1 and held (no rebalancing): value(d) = sum of
    w_i * P_i(d) / P_i(baseline_i). `trough` is the lowest value in [t0, window_end] minus 1,
    clipped at 0 (a rise is no trough; `trough_date` is then None).
  - A campaign episode (spec 10): same-family, same-sign known storms whose [t-1, t+20] windows
    overlap; it runs from the first storm's t-1 to the last storm's t+20 and is named after its
    first storm. Whether it is confounded is decided per portfolio (rule B, in `turbulence`).
  - The shock check (spec 10, ledger 14): `turbulence` replays each loss episode on the mix. A
    mixed episode (rule B: a storm of another family dated after its first t0 and on or before its
    low) is scored first on its drop up to the co-event's t0; with at least 5 trading days it counts
    as clean on that window (the full mixed trough stays alongside). The check uses clean episodes,
    adds the other mixed ones when fewer than 2 are clean, and a family leaning on a mixed episode
    is at best Indicative, naming the co-event.

`load_events`, `event_impact`, `turbulence`, `scenario_stress` and `drawdown_attribution` drop what
is dated after `as_of` BEFORE any computation, whatever the bundle or the events they are given
hold (a list built at a later `as_of` is demoted, never trusted). `episodes` takes no `as_of`: it
trusts the `known` flags and windows of the list it is given, so its callers pass a list already
cut by `_visible`/`_in_force`. The market bundle is shared (cached): its frames are never mutated.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from tools.data import DATASET_END, SOURCE, load_market
from tools.metrics import risk_metrics
from tools.portfolio import _held, normalize, series_from_market

ROOT = Path(__file__).resolve().parents[1]
EVENTS_CSV = ROOT / "data" / "events.csv"
CATEGORY_FAMILY = {"tarifs": "tariffs", "guerre": "war_oil", "energie": "war_oil", "puces": "chips",
                   "taux": "rates"}
FAMILIES = ("tariffs", "war_oil", "chips", "rates")
WINDOW_DAYS = 20                 # a storm's window ends on its t+20 trading day
CHART_LEAD = 5                   # the chart starts 5 trading days before t0
EPS = 1e-12                      # "strictly milder" ignores float noise below this
MIN_TRUNCATED_DAYS = 5           # trading days a mixed episode needs before its co-event to count as clean (ledger 14)
MIN_CLEAN = 2                    # fewer clean episodes than this: the mixed ones are added, as Indicative (spec 10)
MEASURED_AT = 3                  # clean episodes needed for "Measured" (an episode count, not a measured rate)
EVIDENCE_RANK = {"Can't say": 0, "Indicative": 1, "Measured": 2}
EVENTS_SOURCE = ("Storm catalog data/events.csv (sourced headlines, dates by the dating rule); returns from "
                 "the starter prices in CAD, weights fixed at t-1 inside each window, baselines per asset; "
                 "history, not a forecast. " + SOURCE)
ATTRIBUTION_SOURCE = ("Share of the worst fall's trading days and of its log loss that sit inside each family's "
                      "shock windows [t0, t+20] (storm catalog data/events.csv); a correlation, not a cause; "
                      "history, not a forecast.")


# --- small helpers ---------------------------------------------------------------------------------
def _iso(day) -> str | None:
    return None if day is None else pd.Timestamp(day).strftime("%Y-%m-%d")


def _cut(market: dict, as_of: str) -> dict:
    """A shallow copy of the bundle with every frame cut to <= as_of (red gate 3)."""
    end = pd.Timestamp(as_of)
    out = dict(market)
    for key in ("prices", "local", "traded", "fx", "crypto_daily"):
        out[key] = market[key].loc[:end]
    out["calendar"] = market["calendar"][market["calendar"] <= end]
    return out


def _label(calendar: pd.DatetimeIndex, as_of: str) -> str:
    """The last calendar day on or before `as_of` (the request itself before the first day)."""
    return _iso(calendar[-1]) if len(calendar) else as_of


# --- the catalog and the time rule -----------------------------------------------------------------
def _text(row: dict, name: str) -> str:
    """The English column, else the French one (the first catalog format had only `_fr`)."""
    return (row.get(f"{name}_en") or row.get(f"{name}_fr") or "").strip()


def _family(row: dict) -> str | None:
    """The CSV `family` when present, else the first `;` part of `category`; unknown gives None."""
    given = (row.get("family") or "").strip()
    if given:
        return given if given in FAMILIES else None
    return CATEGORY_FAMILY.get((row.get("category") or "").split(";")[0].strip())


def _float(raw) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float("nan")


def _days(calendar: pd.DatetimeIndex, date: str) -> tuple:
    """(t-1, t0, t+20) as ISO strings or None. t0 = the first calendar day on or after `date`;
    t+20 = the 20th calendar day after it (trading days of the union calendar, never wall-clock
    days), None while the calendar does not reach it. A date past the calendar has no t0 yet."""
    i = int(calendar.searchsorted(pd.Timestamp(date), side="left"))
    if i >= len(calendar):
        return None, None, None
    at = lambda k: _iso(calendar[k]) if 0 <= k < len(calendar) else None
    return at(i - 1), at(i), at(i + WINDOW_DAYS)


def load_events(as_of, *, path=None, market=None) -> list:
    """The storm catalog as of `as_of` (spec 9, 10; ledger 1): one dict per CSV row (strings, as
    read) plus family, sign, title, description, regions (list), lat, lon (floats), t_minus_1, t0,
    window_end, known, in_progress.

    Rows dated after `as_of` are dropped (red gate 3), rows of an unknown family too. `family` is
    the CSV column, else the first `;` part of `category`; `sign` is the CSV column, else
    "negative"; title and description are the English columns, else the French ones. The calendar
    is the bundle's union TSX+US calendar cut at `as_of`. A storm is `known` when its t+20 day is
    on that calendar; dated <= as_of with an incomplete window it is `in_progress` and its
    description is withheld (empty; the title and the date stay, ledger 15).
    """
    as_of = _iso(as_of)
    cal = _cut(market if market is not None else load_market(as_of), as_of)["calendar"]
    table = pd.read_csv(EVENTS_CSV if path is None else path, dtype=str, keep_default_na=False)
    rows = []
    for rec in table.to_dict("records"):
        family = _family(rec)
        if rec["date"] > as_of or family is None:
            continue
        before, t0, end = _days(cal, rec["date"])
        known = end is not None
        row = {**rec, "family": family, "sign": (rec.get("sign") or "").strip() or "negative",
               "title": _text(rec, "title"), "description": _text(rec, "description"),
               "regions": [r.strip() for r in rec.get("regions", "").split(";") if r.strip()],
               "lat": _float(rec.get("lat")), "lon": _float(rec.get("lon")),
               "t_minus_1": before, "t0": t0, "window_end": end, "known": known, "in_progress": not known}
        if not known:                                  # the text carries later facts: withheld
            row.update({k: "" for k in ("description", "description_en", "description_fr") if k in row})
        rows.append(row)
    return rows


# --- campaign episodes -----------------------------------------------------------------------------
def episodes(events, family=None, *, market=None) -> list:
    """Campaign episodes of the known storms (spec 10): [{episode, family, event_ids, start, end,
    confounded, confounded_by, sign}], sorted by start.

    Per family, negative and positive storms apart (a relief never joins a loss episode), in date
    order: a storm joins the current episode while its t-1 is on or before the episode's end;
    otherwise it opens a new one. `episode` = the first storm's id, `start` = its t-1, `end` = the
    last storm's t+20. `confounded_by` = the known storms of another family dated after the first
    t0 and on or before `end` (candidates only: rule B keeps those on or before the trough date,
    so `confounded` stays None here and is decided per portfolio, Task 10). In-progress storms
    are left out. The storms carry their own calendar dates, so `market` is not read (it is part
    of the ledger signature).
    """
    pool = sorted((e for e in events if e.get("known") and e.get("t0") and e.get("window_end")),
                  key=lambda e: (e["date"], e["event_id"]))
    found = []
    for fam in (FAMILIES if family is None else (family,)):
        for sign in ("negative", "positive"):
            current = None
            for e in (x for x in pool if x["family"] == fam and x["sign"] == sign):
                start = e["t_minus_1"] or e["t0"]
                if current is not None and start <= current["end"]:
                    current["event_ids"].append(e["event_id"])
                    current["end"] = max(current["end"], e["window_end"])
                    continue
                current = {"episode": e["event_id"], "family": fam, "event_ids": [e["event_id"]],
                           "start": start, "end": e["window_end"], "confounded": None,
                           "confounded_by": [], "sign": sign, "first_t0": e["t0"]}
                found.append(current)
    for ep in found:
        first = ep.pop("first_t0")
        ep["confounded_by"] = [e["event_id"] for e in pool
                               if e["family"] != ep["family"] and first < e["date"] <= ep["end"]]
    return sorted(found, key=lambda ep: (ep["start"], ep["episode"]))


# --- one storm's window: baselines per asset, weights fixed at t-1 ----------------------------------
def _visible(events, as_of: str) -> list:
    """The caller's storms under this call's `as_of` (the list may come from a later as_of): rows
    dated after it are dropped and a window that ends after it makes the storm unknown."""
    out = []
    for e in events:
        if e["date"] > as_of:
            continue
        known = bool(e.get("known")) and e.get("window_end") is not None and e["window_end"] <= as_of
        out.append({**e, "known": known, "in_progress": not known})
    return out


def _in_force(events, cal: pd.DatetimeIndex, as_of: str) -> list:
    """`_visible`, with t-1, t0 and t+20 re-read from this call's (cut) calendar, so a list built
    at a later `as_of` cannot carry its own windows into `episodes`."""
    out = []
    for e in _visible(events, as_of):
        before, t0, end = _days(cal, e["date"])
        known = e["known"] and end is not None
        out.append({**e, "t_minus_1": before, "t0": t0, "window_end": end, "known": known, "in_progress": not known})
    return out


def _bases(held: dict, ev: dict, m: dict):
    """({ticker: {day, cad, local, t0}}, None), or (None, sentence) when a held line has no price
    before the storm. Baseline = the asset's last traded price before the storm's t0; a crypto
    line takes the UTC row dated `announced - 1 day` (pitfalls 6 and 7). `t0` = the first day on
    or after the storm's t0 on which the asset's own exchange traded (None: it never did)."""
    t0 = pd.Timestamp(ev["t0"])
    uni = m["universe"]
    kind, ccy = dict(zip(uni["ticker"], uni["asset_class"])), dict(zip(uni["ticker"], uni["currency"]))
    bases = {}
    for t in held:
        if kind.get(t) == "crypto" and t in m["crypto_daily"].columns:
            said = pd.Timestamp(ev.get("announced") or ev["date"])
            rows = m["crypto_daily"][t].loc[: said - pd.Timedelta(days=1)].dropna()
            day, cad = (rows.index[-1], float(rows.iloc[-1])) if len(rows) else (None, None)
            rate = float(m["fx"].asof(day)) if day is not None and ccy.get(t) == "USD" else 1.0
            local = None if cad is None else cad / rate
        else:
            earlier = slice(None, t0 - pd.Timedelta(days=1))
            seen = m["traded"][t].loc[earlier] & m["prices"][t].loc[earlier].notna()
            day = seen[seen].index[-1] if seen.any() else None
            cad = None if day is None else float(m["prices"][t][day])
            local = None if day is None else float(m["local"][t][day])
        if cad is None or not np.isfinite(cad) or cad <= 0:
            return None, (f"{t} has no price before {ev['t0']}, so this shock cannot be replayed on it.")
        after = m["traded"][t].loc[t0:]
        bases[t] = {"day": day, "cad": cad, "local": local, "t0": after[after].index[0] if after.any() else None}
    return bases, None


def _ratios(held: dict, bases: dict, m: dict, days: pd.DatetimeIndex) -> pd.DataFrame:
    """CAD price over the asset's baseline on each of `days`, prices carried forward over closed
    days; a day before the asset has any price counts as flat (1.0), like the series does."""
    prices = m["prices"][list(held)].ffill().loc[days]
    return (prices / pd.Series({t: b["cad"] for t, b in bases.items()})).fillna(1.0)


def _path(held: dict, bases: dict, m: dict, days: pd.DatetimeIndex) -> tuple:
    """(per-asset ratios, portfolio value) on `days`: weights fixed at t-1, no rebalancing, the
    value is 1.0 at the baseline. Task 10 scores an episode with this, from its first storm."""
    ratio = _ratios(held, bases, m, days)
    return ratio, ratio.mul(pd.Series(held)).sum(axis=1)


def _replay(held: dict, ev: dict, t0: str, m: dict, days: pd.DatetimeIndex) -> tuple:
    """(bases, ratios, value, None) of the mix on `days`: weights fixed at the storm's t-1 and
    held, per-asset baselines and the crypto rule. (None, None, None, sentence) when a held line
    has no price before the storm. The one path behind a storm's card and an episode's trough."""
    bases, why = _bases(held, {**ev, "t0": t0}, m)
    if why:
        return None, None, None, why
    return (bases, *_path(held, bases, m, days), None)


def _clip(x: float) -> float:
    """A trough is a fall: a rise (or float noise around 0) is 0.0."""
    return 0.0 if x > -EPS else float(x)


def _trough(value: pd.Series) -> tuple:
    """(trough, date) of a value path that is 1.0 at its baseline: the lowest value minus 1,
    clipped at 0, and the first day it is reached (None when there is no fall)."""
    low = _clip(float(value.min()) - 1.0)
    return low, (_iso(value.idxmin()) if low < 0.0 else None)


def _percentile(held: dict, trough: float, m: dict):
    """Share of all 21-day windows (t0 .. t+20 against the day before) of the portfolio's daily
    series up to `as_of` whose clipped trough is strictly milder than `trough`. 0.0 when there is
    no trough; None when the series is too short to hold one window."""
    if trough >= 0.0:
        return 0.0
    v = series_from_market(held, m).to_numpy(float)
    if len(v) < WINDOW_DAYS + 2:
        return None
    win = np.lib.stride_tricks.sliding_window_view(v, WINDOW_DAYS + 2)
    low = np.minimum(0.0, win[:, 1:].min(axis=1) / win[:, 0] - 1.0)
    return float(np.mean(low > trough + EPS))


def _fx_effect(held: dict, bases: dict, ratio: pd.Series, day, m: dict):
    """Sum over USD lines of weight x (CAD return - listing-currency return) from the baseline to
    `day` (the loonie effect); None when a needed listing-currency price is missing."""
    ccy = dict(zip(m["universe"]["ticker"], m["universe"]["currency"]))
    total = 0.0
    for t, w in held.items():
        if ccy.get(t) != "USD":
            continue
        base, now = bases[t]["local"], m["local"][t].ffill().loc[day]
        if base is None or not np.isfinite(base) or base <= 0 or not np.isfinite(now):
            return None
        total += w * ((float(ratio[t]) - 1.0) - (float(now) / base - 1.0))
    return float(total)


def event_impact(weights, event_id, window=(-5, 20), as_of=DATASET_END, *, market=None,
                 events=None) -> dict:
    """What one known storm did to a portfolio (spec 10; ledger 1; every number is a fraction).

    {event_id, episode, sign, confounded, t0, window_end, trough, trough_date, ret_20, fx_effect,
    percentile, by_ticker: {t: {t0, trough, ret_20}}, overlaps, chart: {dates, values}, source,
    as_of}. The weights are normalized, then fixed at t-1 and held inside the window (see the
    module doc), so per-asset t0s and baselines compose exactly. `trough` = the lowest value in
    [t0, t+20] minus 1, clipped at 0 (no loss: `trough_date` None); `ret_20` = the value at t+20
    minus 1; `fx_effect` = the part of the move due to USD/CAD, at the trough (the window end when
    there is no loss), None when a price is missing; `percentile` = share of all 21-day windows of
    the portfolio's series up to `as_of` that were milder; `overlaps` = ids of the other known
    storms dated inside [t-1, t+20]; `confounded` = one of them, of another family, is dated after
    t0 and on or before the trough date (rule B); `chart` = value x 100 (100 = the baseline) from
    5 trading days before t0 to t+20. A storm that is unknown, dated after `as_of` or still in
    progress gives {"error": sentence}. `window` = (days before t0 charted, days after t0).
    """
    as_of = _iso(as_of)
    m = _cut(market if market is not None else load_market(as_of), as_of)
    cal = m["calendar"]
    pool = _in_force(load_events(as_of, market=m) if events is None else events, cal, as_of)
    ev = next((e for e in pool if e["event_id"] == event_id), None)
    if ev is None:
        return {"error": f"No shock called {event_id} is known on {as_of}."}
    before, t0, end = _days(cal, ev["date"])
    if not ev["known"] or end is None:
        return {"error": f"{ev['title'] or event_id} is still in progress on {as_of}: its 20 trading "
                         "days are not complete, so it is not measured."}
    i0, lead = int(cal.get_loc(pd.Timestamp(t0))), max(0, -int(window[0]))
    last = i0 + int(window[1])
    if last >= len(cal):
        return {"error": f"The window of {ev['title'] or event_id} runs past {as_of}, so it is not measured."}
    held = _held(normalize(weights))
    for t in held:
        if t not in m["prices"].columns:
            raise ValueError(f"Unknown ticker: {t}")
    days = cal[max(0, i0 - lead): last + 1]
    bases, ratio, value, why = _replay(held, ev, t0, m, days)
    if why:
        return {"error": why}
    win = value.loc[cal[i0]: cal[last]]
    trough, trough_date = _trough(win)
    by_ticker = {}
    for t, b in bases.items():
        own = ratio[t].loc[b["t0"] if b["t0"] is not None and b["t0"] <= cal[last] else cal[i0]: cal[last]]
        by_ticker[t] = {"t0": _iso(b["t0"]), "trough": _clip(float(own.min()) - 1.0),
                        "ret_20": float(own.iloc[-1]) - 1.0}
    fx_day = pd.Timestamp(trough_date) if trough_date else cal[last]
    known = [e for e in pool if e["known"]]
    overlaps = [e["event_id"] for e in sorted(known, key=lambda e: (e["date"], e["event_id"]))
                if e["event_id"] != event_id and (before or t0) <= e["date"] <= _iso(cal[last])]
    by_id = {e["event_id"]: e for e in known}
    confounded = bool(_co_events(t0, trough_date, [o for o in overlaps if by_id[o]["family"] != ev["family"]], by_id))
    episode = next((ep["episode"] for ep in episodes(known) if event_id in ep["event_ids"]), event_id)
    return {"event_id": event_id, "episode": episode, "sign": ev["sign"], "confounded": confounded,
            "t0": t0, "window_end": _iso(cal[last]), "trough": trough, "trough_date": trough_date,
            "ret_20": float(win.iloc[-1]) - 1.0,
            "fx_effect": _fx_effect(held, bases, ratio.loc[fx_day], fx_day, m),
            "percentile": _percentile(held, trough, m), "by_ticker": by_ticker, "overlaps": overlaps,
            "chart": {"dates": [_iso(d) for d in days], "values": (value * 100.0).tolist()},
            "source": EVENTS_SOURCE, "as_of": _label(cal, as_of)}


# --- the shock check: loss episodes replayed on a mix (Task 10) ------------------------------------
def _co_events(first_t0: str, low, candidates: list, by_id: dict) -> list:
    """Rule B (spec 10): the candidate storms of another family dated after the episode's first t0
    and on or before its low (an event after the low cannot explain it). No fall: none."""
    if low is None:
        return []
    kept = [o for o in candidates if first_t0 < by_id[o]["date"] <= low]
    return sorted(kept, key=lambda o: (by_id[o]["date"], o))


def _score_episode(held: dict, ep: dict, by_id: dict, m: dict):
    """One loss episode on the mix, as a row, or None when a held line has no price before it.

    Weights fixed at the first storm's t-1, that storm's baselines, from its t0 to the episode's
    last t+20 (a one-storm episode shows exactly the storm card's trough). Rule B on the full
    low decides `confounded` / `confounded_by`. A mixed episode is also scored on the days before
    its earliest co-event's t0: with MIN_TRUNCATED_DAYS or more it is scored (`scored`
    "truncated") on that drop, and `trough_full` keeps the full mixed trough alongside."""
    cal, first = m["calendar"], by_id[ep["episode"]]
    t0 = first["t0"]
    days = cal[int(cal.get_loc(pd.Timestamp(t0))): int(cal.get_loc(pd.Timestamp(ep["end"]))) + 1]
    _, _, value, why = _replay(held, first, t0, m, days)
    if why:
        return None
    full, low = _trough(value)
    kept = _co_events(t0, low, ep["confounded_by"], by_id)
    row = {"episode": ep["episode"], "family": ep["family"], "event_ids": list(ep["event_ids"]),
           "trough": full, "trough_date": low, "confounded": bool(kept), "confounded_by": kept,
           "scored": "full", "scored_days": int(len(days)), "trough_full": full, "trough_full_date": low,
           "counted": False}
    if kept:
        before = value[value.index < pd.Timestamp(by_id[kept[0]]["t0"])]
        if len(before) >= MIN_TRUNCATED_DAYS:
            row.update(zip(("trough", "trough_date"), _trough(before)))
            row.update({"scored": "truncated", "scored_days": int(len(before))})
    return row


def _family_view(rows: list) -> dict:
    """{n, worst, mean, evidence, label, mixed, episodes} for one family's scored loss episodes.

    Clean = not confounded, or mixed but scored on a long-enough truncated window; the other mixed
    ones are added only when fewer than MIN_CLEAN are clean (spec 10). `n` counts clean episodes
    only. A family leaning on a mixed episode is at best Indicative and names the co-event.
    Marks each row `counted` (its trough is in `worst` and `mean`)."""
    clean = [r for r in rows if not r["confounded"] or r["scored"] == "truncated"]
    loose = [r for r in rows if r["confounded"] and r["scored"] == "full"]
    used = clean + (loose if len(clean) < MIN_CLEAN else [])
    for r in rows:
        r["counted"] = any(r is u for u in used)
    mixed = [r for r in used if r["confounded"]]
    troughs = [r["trough"] for r in used]
    evidence = "Can't say" if not used else "Measured" if len(clean) >= MEASURED_AT and not mixed else "Indicative"
    co = list(dict.fromkeys(c for r in mixed for c in r["confounded_by"]))
    return {"n": len(clean), "worst": min(troughs) if troughs else None,
            "mean": float(np.mean(troughs)) if troughs else None, "evidence": evidence,
            "label": f"Indicative (mixed with {', '.join(co)})" if mixed else evidence,
            "mixed": [r["episode"] for r in mixed], "episodes": rows}


def _setup(weights, as_of, market, events) -> tuple:
    """(as_of, bundle cut at as_of, held weights, the storms in force at as_of) for a shock check."""
    as_of = _iso(as_of)
    m = _cut(market if market is not None else load_market(as_of), as_of)
    held = _held(normalize(weights))
    for t in held:
        if t not in m["prices"].columns:
            raise ValueError(f"Unknown ticker: {t}")
    pool = _in_force(load_events(as_of, market=m) if events is None else events, m["calendar"], as_of)
    return as_of, m, held, pool


def turbulence(weights, families, as_of, *, market=None, events=None) -> dict:
    """The shock check by family (spec 10; ledger 1, 7, 14): {family: {n, worst, mean, evidence,
    label, mixed, episodes: [{episode, event_ids, trough, trough_date, confounded, confounded_by,
    ...}]}, source, as_of}. `families` None or empty = all four.

    Loss episodes only (sign negative; a relief is never a loss range), each replayed on the mix
    (`_score_episode`: weights fixed at its first storm's t-1, trough over the whole campaign
    window, rule B, the truncated score of a mixed one). Beyond the plan's keys each episode row
    carries `family`, `scored` ("full" | "truncated"), `scored_days` (int), `trough_full` and
    `trough_full_date` (the whole-window low, equal to `trough` unless truncated) and `counted`;
    a family also lists `skipped` (episodes a held line has no price for). `n` counts clean
    episodes. Evidence: Measured (3+ clean, none mixed), Indicative (1-2 clean, or a mixed one is
    used), Can't say (nothing used). History, not a forecast."""
    as_of, m, held, pool = _setup(weights, as_of, market, events)
    known = [e for e in pool if e["known"]]
    by_id = {e["event_id"]: e for e in known}
    asked = list(dict.fromkeys(families or FAMILIES))
    if any(f not in FAMILIES for f in asked):
        raise ValueError(f"Unknown family: {next(f for f in asked if f not in FAMILIES)}")
    out = {}
    for fam in asked:
        scored = [(ep, _score_episode(held, ep, by_id, m)) for ep in episodes(known, fam) if ep["sign"] == "negative"]
        out[fam] = _family_view([row for _, row in scored if row is not None])
        out[fam]["skipped"] = [ep["episode"] for ep, row in scored if row is None]
    return {**out, "source": EVENTS_SOURCE, "as_of": _label(m["calendar"], as_of)}


def scenario_stress(weights, families, as_of, *, market=None, events=None) -> dict:
    """The shock check's one number (spec 10; ledger 1): {value, n_episodes, worst_event_id,
    episodes, excluded, label, source, as_of}, built on `turbulence`.

    `value` = the worst trough among the episodes the check uses in the asked families (None: no
    close precedent at this date); `worst_event_id` = that episode's id; `n_episodes` = clean
    episodes only, summed over the asked families: the "n separate earlier episodes" of the shock
    line (campaigns, never single headlines), and governance concludes from 2; `episodes` = the
    episodes used; `excluded` = mixed episodes left out because enough clean ones exist; `label`
    = the family's label for one family, else the weakest evidence among them (Can't say <
    Indicative < Measured), naming the co-events when that is Indicative and a mixed episode is used."""
    t = turbulence(weights, families, as_of, market=market, events=events)
    views = [v for f, v in t.items() if f in FAMILIES]
    rows = [r for v in views for r in v["episodes"]]
    used = [r for r in rows if r["counted"]]
    worst = min(used, key=lambda r: r["trough"]) if used else None
    weak = min((v["evidence"] for v in views), key=EVIDENCE_RANK.__getitem__)
    co = list(dict.fromkeys(c for r in used if r["confounded"] for c in r["confounded_by"]))
    if len(views) == 1:
        label = views[0]["label"]
    else:
        label = f"Indicative (mixed with {', '.join(co)})" if weak == "Indicative" and co else weak
    return {"value": None if worst is None else worst["trough"], "n_episodes": sum(v["n"] for v in views),
            "worst_event_id": None if worst is None else worst["episode"], "episodes": used,
            "excluded": [r for r in rows if r["confounded"] and not r["counted"]], "label": label,
            "source": t["source"], "as_of": t["as_of"]}


def drawdown_attribution(series, events, as_of, *, metrics=None) -> dict | None:
    """How much of the worst fall sits inside each family's shock windows (spec 10; ledger 1, 14):
    {shares, days_share, peak_date, trough_date, source, as_of}, or None when the series has no fall.

    The series is cut at `as_of` first; `metrics` (a `risk_metrics` output, else computed here)
    gives the fall. Its stretch = the series days after `peak_date` through `trough_date`. Per
    family (all four keys; known storms of either sign dated <= as_of): `days_share` = stretch days
    inside any of the family's [t0, window_end] over the stretch days, `shares` = the sum of the
    daily log returns on those days over the stretch's total log return. A correlation, not a
    cause: a slow fall can sit inside many windows without any one headline breaking the floor."""
    as_of = _iso(as_of)
    keep = [i for i, d in enumerate(series["dates"]) if _iso(d) <= as_of]
    dates = [_iso(series["dates"][i]) for i in keep]
    cut = {**series, "dates": dates, "values": [float(series["values"][i]) for i in keep]}
    fits = metrics and all(metrics.get(k) is None or metrics[k] in dates for k in ("peak_date", "trough_date"))
    m = metrics if fits else risk_metrics(cut)                  # metrics from a longer series are not trusted
    if m.get("peak_date") is None or m.get("trough_date") is None:
        return None
    i, j = dates.index(m["peak_date"]), dates.index(m["trough_date"])
    stretch, logs = dates[i + 1: j + 1], np.log(np.asarray(cut["values"][i: j + 1], dtype=float))
    daily, total = np.diff(logs), float(logs[-1] - logs[0])
    shares, days_share = {}, {}
    for fam in FAMILIES:
        spans = [(e["t0"], e["window_end"]) for e in events if e.get("family") == fam and e.get("known")
                 and e.get("t0") and e.get("window_end") and e["window_end"] <= as_of]
        inside = np.array([any(a <= d <= b for a, b in spans) for d in stretch], dtype=bool)
        days_share[fam] = float(inside.sum() / len(stretch))
        shares[fam] = float(daily[inside].sum() / total) + 0.0     # + 0.0: a family with no day is 0.0, never -0.0
    return {"shares": shares, "days_share": days_share, "peak_date": m["peak_date"], "trough_date": m["trough_date"],
            "source": ATTRIBUTION_SOURCE, "as_of": dates[-1]}
