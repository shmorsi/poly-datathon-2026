import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # this folder only (the scripts run with -I)
from paths import DEEP, OUT, REPO, RUNS  # noqa: E402,F401
import json
import sys

import numpy as np
import pandas as pd

from core import (Market, apply_add, apply_set, cagr, drawdown, risk_contrib, round_pp, fmt, REPO)

P = json.load(open(REPO / "data/personas.json"))
pil = P["pilots"]
M = Market()
print("union sessions", len(M.days), M.days[0].date(), M.days[-1].date(),
      "TSX", len(M.tsx_days), "US", len(M.us_days),
      "sessions without own FX row", int((~M.days.isin(M.fx_raw.index)).sum()))

out = {}

def report(name, w, amount, start=None, prices=None):
    v, r = M.series(w, start=start, prices=prices)
    depth, pk, tr, rec = drawdown(v)
    g = cagr(v)
    end = amount * v.iloc[-1] / 100
    vol = r.mul(pd.Series(w)[r.columns]).sum(axis=1).std(ddof=1) * np.sqrt(252)
    rc, enb = risk_contrib(r, w)
    out[name] = dict(dd=depth, peak=str(pk.date()), trough=str(tr.date()),
                     rec=None if rec is None else str(rec.date()),
                     rec_days=None if rec is None else (rec - tr).days,
                     cagr=g, end=end, dollars=amount * depth, vol=vol, rc=rc, enb=enb, n=len(v))
    o = out[name]
    print(f"{name:28s} dd {o['dd']*100:9.5f}% ({o['dollars']:,.2f})  peak {o['peak']} trough {o['trough']} "
          f"rec {o['rec']} ({o['rec_days']} d)  CAGR {o['cagr']*100:8.5f}%  end {o['end']:,.2f}  vol {vol*100:.4f}% "
          f"ENB {enb:.4f}  n={o['n']}")
    print("      RC:", {k: round(x, 6) for k, x in sorted(rc.items(), key=lambda kv: -kv[1])})
    return v, r

rob = pil["robert"]
rt = rob["portfolio"]
ra = apply_set(rt, "NVDA", 0.40)
print("Robert after weights", {k: round(x, 6) for k, x in ra.items()})
report("Robert today", rt, rob["amount"])
va, _ = report("Robert after", ra, rob["amount"])
report("Robert after from 2023", ra, rob["amount"], start="2023-01-01")
report("Robert today from 2023", rt, rob["amount"], start="2023-01-01")
report("Mateo", pil["mateo"]["portfolio"], pil["mateo"]["amount"])
report("Amira", pil["amira"]["portfolio"], pil["amira"]["amount"])
can = pil["canadian"]
ct = can["portfolio"]
ca = apply_add(ct, "SPY", 0.20)
print("Canadian after weights", {k: round(x, 6) for k, x in ca.items()})
report("Canadian today", ct, can["amount"])
report("Canadian after (unhedged)", ca, can["amount"])
# hedged stand-in: SPY on its USD returns (listing currency), everything else unchanged
hedged = M.cad.copy()
hedged["SPY"] = M.local["SPY"]
report("Canadian after (hedged SI)", ca, can["amount"], prices=hedged)

# Size curve: NVDA 0..40 % in 1 % steps, each from today
print("\nSize curve (Robert, NVDA set to x from today):")
curve = []
for k in range(41):
    x = k / 100
    w = apply_set(rt, "NVDA", x) if x > 0 else dict(rt)
    v, _ = M.series(w)
    d = drawdown(v)[0]
    curve.append((k, d, round_pp(d)))
for k, d, rd in curve[5:13]:
    print(f"  {k:2d} %  raw {d*100:.6f} %  rounded {rd*100:.1f} %  {'FAIL' if rd < -0.15 else 'pass'}")
first_fail = next(k for k, d, rd in curve if rd < round_pp(-0.15))
print("first failing size", first_fail, "%")

# SPY calendar 2022
def ret(series, a, b):
    s = series.dropna()
    return s[s.index <= b].iloc[-1] / s[s.index <= a].iloc[-1] - 1
spy_usd_own = M.adj_raw["SPY"]
spy_cad_union = M.cad["SPY"]
a, b = pd.Timestamp("2021-12-31"), pd.Timestamp("2022-12-31")
print("\nSPY 2022 USD (own rows)", fmt(ret(spy_usd_own, a, b), 3),
      " CAD (union cal, FX cf)", fmt(ret(spy_cad_union, a, b), 3))
print("  last SPY row <= 2021-12-31:", spy_usd_own.dropna()[spy_usd_own.dropna().index <= a].index[-1].date(),
      " last FX row <= 2021-12-31:", M.fx_raw[M.fx_raw.index <= a].index[-1].date(), M.fx_raw[M.fx_raw.index <= a].iloc[-1],
      " last FX <= 2022-12-31:", M.fx_raw[M.fx_raw.index <= b].index[-1].date(), M.fx_raw[M.fx_raw.index <= b].iloc[-1])
# 2022 worst fall for the hedge comparison, both sides
for nm, pr in (("unhedged", None), ("hedged", hedged)):
    v, _ = M.series(ca, prices=pr)
    v22 = v[(v.index >= pd.Timestamp("2021-12-31")) & (v.index <= pd.Timestamp("2022-12-31"))]
    y22 = v[v.index <= b].iloc[-1] / v[v.index <= a].iloc[-1] - 1
    v22b = v[(v.index >= pd.Timestamp("2022-01-01")) & (v.index <= pd.Timestamp("2022-12-31"))]
    print(f"  Canadian after {nm}: 2022 return {y22*100:.4f}%  worst within 2022 (base 2021-12-31) {drawdown(v22)[0]*100:.4f}% "
          f"(base first 2022 session) {drawdown(v22b)[0]*100:.4f}%  end {can['amount']*v.iloc[-1]/100:,.0f}")

json.dump({k: {kk: vv for kk, vv in o.items()} for k, o in out.items()}, open(OUT / "daily_out.json", "w"),
          indent=1, default=float)
json.dump([(k, d) for k, d, _ in curve], open(OUT / "curve.json", "w"))
