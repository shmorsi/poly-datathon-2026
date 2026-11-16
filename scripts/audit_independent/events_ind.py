"""Independent shock engine, from docs/finance_methods.md sections 3-4 only (no repo code)."""
import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # this folder only (the scripts run with -I)
from paths import DEEP, OUT, REPO, RUNS  # noqa: E402,F401
import json
import sys

import numpy as np
import pandas as pd

from core import Market, apply_add, apply_set, REPO

M = Market()
DAYS = M.days
EV = pd.read_csv(REPO / "data/events.csv", dtype=str, keep_default_na=False)


def pos(d):
    return DAYS.searchsorted(pd.Timestamp(d))


# ---- 1. verify the dating rule from announced_at -------------------------------------------
def dated(announced_at):
    ts = pd.Timestamp(announced_at)
    day = ts.normalize()
    if day in DAYS and ts.hour < 16:
        return day
    return DAYS[DAYS.searchsorted(day, side="right")]


bad = [(r.event_id, r.date, str(dated(r.announced_at).date())) for r in EV.itertuples()
       if str(dated(r.announced_at).date()) != r.date]
print("dating rule mismatches:", bad)


# ---- 2. per-asset base and window value ----------------------------------------------------
def own_days(t):
    if t.endswith(".TO"):
        return M.tsx_days
    if t.endswith("-USD"):
        return None
    return M.us_days


def base_price(t, event_date, announced):
    """CAD price at the asset's baseline: last own-exchange price before its own t0."""
    d = pd.Timestamp(event_date)
    if t.endswith("-USD"):
        bday = pd.Timestamp(announced) - pd.Timedelta(days=1)
        usd = M.adj_raw[t].dropna()
        p = usd.loc[bday]
        fx = M.fx_raw[M.fx_raw.index <= bday].iloc[-1]
        return p * fx, bday
    od = own_days(t)
    t0 = od[od.searchsorted(d)]           # first own session on/after the shock date
    b = od[od.searchsorted(t0) - 1]       # last own session before it
    p = M.local[t].loc[b] if b in M.local.index else M.adj_raw[t].loc[b]
    if M.currency[t] == "USD":
        p = p * M.usdcad.loc[b]
    return p, b


def window_values(w, first, last_end_pos):
    """Buy-and-hold value relative to the first event's per-asset baselines, on union days t0..end."""
    i0 = pos(first.date)
    dates = DAYS[i0:last_end_pos + 1]
    val = pd.Series(0.0, index=dates)
    for t, x in w.items():
        if x == 0:
            continue
        b, _ = base_price(t, first.date, first.announced)
        val += x * M.cad[t].reindex(dates) / b
    return val - 1


def trough_of(vals):
    m = vals.min()
    if m >= 0:
        return 0.0, None
    return float(m), vals.idxmin()


# ---- 3. campaign episodes --------------------------------------------------------------------
def episodes(family, sign):
    rows = EV[(EV.family == family) & (EV.sign == sign)].sort_values("date")
    eps = []
    for r in rows.itertuples():
        p = pos(r.date)
        lo, hi = p - 1, p + 20
        if eps and lo <= eps[-1]["hi"]:
            eps[-1]["members"].append(r)
            eps[-1]["hi"] = max(eps[-1]["hi"], hi)
        else:
            eps.append({"members": [r], "lo": lo, "hi": hi})
    return eps


def score_family(w, family, coevent_signs=("negative", "positive")):
    out = []
    for ep in episodes(family, "negative"):
        first = ep["members"][0]
        vals = window_values(w, first, ep["hi"])
        tr, tdate = trough_of(vals)
        rec = {"episode": first.event_id, "members": [m.event_id for m in ep["members"]],
               "full": tr, "full_date": None if tdate is None else str(tdate.date()),
               "end": str(DAYS[ep["hi"]].date())}
        co = None
        if tdate is not None:
            others = EV[(EV.family != family) & (EV.sign.isin(coevent_signs))]
            cands = others[(pd.to_datetime(others.date) > pd.Timestamp(first.date)) &
                           (pd.to_datetime(others.date) <= tdate)].sort_values("date")
            if len(cands):
                co = cands.iloc[0]
        if co is None:
            rec.update(clean=True, score=tr, mixed_with=None, n_sessions=len(vals))
        else:
            cut = vals[vals.index < pd.Timestamp(co.date)]
            ctr, cdate = trough_of(cut)
            rec.update(clean=len(cut) >= 5, score=ctr, mixed_with=co.event_id, n_sessions=len(cut),
                       cut_date=None if cdate is None else str(cdate.date()))
        out.append(rec)
    return out


def summary(w, family, **kw):
    eps = score_family(w, family, **kw)
    clean = [e for e in eps if e["clean"]]
    worst = min(e["score"] for e in clean) if clean else None
    mixed_used = any(e["mixed_with"] for e in clean)
    n = len(clean)
    label = "Measured" if (n >= 3 and not mixed_used) else ("Indicative" if n >= 1 else "Can't say")
    return {"n": n, "worst": worst, "worst_ep": min(clean, key=lambda e: e["score"])["episode"] if clean else None,
            "label": label, "episodes": eps}


if __name__ == "__main__":
    P = json.load(open(REPO / "data/personas.json"))["pilots"]
    rob = P["robert"]["portfolio"]
    mixes = {
        "robert_today": rob,
        "robert_after": apply_set(rob, "NVDA", 0.4),
        "mateo": P["mateo"]["portfolio"],
        "amira": P["amira"]["portfolio"],
        "canadian_today": P["canadian"]["portfolio"],
        "canadian_after": apply_add(P["canadian"]["portfolio"], "SPY", 0.2),
    }
    res = {}
    for name, w in mixes.items():
        res[name] = {}
        for fam in ("tariffs", "war_oil", "chips", "rates"):
            s = summary(w, fam)
            res[name][fam] = s
            print(f"{name:15s} {fam:8s} n={s['n']:2d} worst={s['worst']*100:8.4f}% ({s['worst_ep']}) {s['label']}")
    json.dump(res, open(OUT / "events_out.json", "w"), indent=1, default=str)
    print()
    for e in res["robert_after"]["tariffs"]["episodes"]:
        print("robert_after tariffs", e)
