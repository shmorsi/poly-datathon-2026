import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # this folder only (the scripts run with -I)
from paths import DEEP, OUT, REPO, RUNS  # noqa: E402,F401
import json
import sys

import numpy as np
import pandas as pd

import core
from core import Market, apply_set, drawdown, cagr, REPO

P = json.load(open(REPO / "data/personas.json"))["pilots"]

# 1. CNQ.TO correction: direction and size, from the raw rows
px = pd.read_csv(REPO / "data/starter/prices_daily.csv", parse_dates=["date"])
c = px[px.ticker == "CNQ.TO"].set_index("date").sort_index()
i = c.index.get_loc(pd.Timestamp("2022-08-22"))
d0, d1 = c.index[i - 1], c.index[i]
close_r = c.close.iloc[i] / c.close.iloc[i - 1] - 1
adj_r = c.adj_close.iloc[i] / c.adj_close.iloc[i - 1] - 1
fixed_r = c.adj_close.iloc[i] / (c.adj_close.iloc[i - 1] * 1.021) - 1
# Yahoo's 'close' is split-adjusted, and Yahoo treated 1.021 as a split: the true pre-day price is close*1.021
true_px_r = c.close.iloc[i] / (c.close.iloc[i - 1] * 1.021) - 1
true_tr = (c.close.iloc[i] + 0.75) / (c.close.iloc[i - 1] * 1.021) - 1
print(f"CNQ 2022-08-22: close {close_r*100:+.3f}%  adj raw {adj_r*100:+.3f}%  adj fixed {fixed_r*100:+.3f}%  "
      f"true price {true_px_r*100:+.3f}%  true total (price + 0.75 div) {true_tr*100:+.3f}%  div/prev true px {0.75/(c.close.iloc[i-1]*1.021)*100:.3f}%")

M = Market()
M0 = Market(cnq_fix=False)
w = P["mateo"]["portfolio"]
for nm, m in (("with fix", M), ("without fix", M0)):
    v, _ = m.series(w)
    d = drawdown(v)
    print(f"Mateo {nm}: worst {d[0]*100:.4f}% ({d[1].date()} -> {d[2].date()}), CAGR {cagr(v)*100:.4f}%, end {250000*v.iloc[-1]/100:,.0f}")

# 2. Rule B co-event signs and 3. USD baseline convention on TSX-only days
import events_ind as E
rt = P["robert"]["portfolio"]
ra = apply_set(rt, "NVDA", 0.4)
for nm, w in (("robert_today", rt), ("robert_after", ra)):
    a = E.summary(w, "tariffs")
    b = E.summary(w, "tariffs", coevent_signs=("negative",))
    print(f"{nm} tariffs: any-sign co-events n={a['n']} worst={a['worst']*100:.4f}% | negative-only n={b['n']} worst={b['worst']*100:.4f}%")


def base_union(t, event_date, announced):
    """Alternative: baseline = CAD price on the union session before the event date (not the asset's own session)."""
    d = pd.Timestamp(event_date)
    p = E.DAYS[E.DAYS.searchsorted(d) - 1]
    return E.M.cad[t].loc[p], p


orig = E.base_price
E.base_price = base_union
for nm, w in (("robert_today", rt), ("robert_after", ra)):
    s = E.summary(w, "tariffs")
    print(f"{nm} tariffs with union t-1 baselines: n={s['n']} worst={s['worst']*100:.4f}% ({s['worst_ep']})")
E.base_price = orig

# 4. Risk share / bets with weekly (Friday) returns, as an estimator sensitivity
for nm, w in (("robert_today", rt), ("robert_after", ra)):
    tick = list(w)
    p = M.cad[tick]
    wk = p.resample("W-FRI").last().pct_change().dropna()
    rc, enb = core.risk_contrib(wk, w)
    print(f"{nm} weekly: top share {max(rc, key=rc.get)} {max(rc.values())*100:.1f}%  bets {enb:.2f}")
