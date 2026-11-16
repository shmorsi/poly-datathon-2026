import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # this folder only (the scripts run with -I)
from paths import DEEP, OUT, REPO, RUNS  # noqa: E402,F401
import json, sys, re
import numpy as np, pandas as pd
import report as RP   # re-runs the consolidated comparison (prints the table again)
from core import Market
# 1. raw gaps of every pct row: parse my/engine columns back from the rows
gaps = []
for r in RP.rows:
    m, e = r[2], r[3]
    if m.endswith(" %") and e.endswith(" %") and "→" not in m:
        gaps.append((r[0], abs(float(m[:-2]) - float(e[:-2]))))
print("rows with pct values:", len(gaps), " max |gap| (4-dp display):", max(g for _, g in gaps))
# exact raw gaps for a few core ones
R = RP.R
print("raw gaps: today dd", abs(RP.dt[0] - R["metrics"]["today"]["max_drawdown"]), " after dd", abs(RP.da[0] - R["metrics"]["after"]["max_drawdown"]),
      " cagr after", abs(RP.cagr(RP.va) - R["metrics"]["after"]["cagr"]), " NVDA rc", abs(RP.rca["NVDA"] - R["risk"]["after"]["shares"]["NVDA"]),
      " tariff", abs(RP.s["worst"] - R["turbulence"]["tariffs"]["worst_after"]))
# 2. Canadian today volatility vs engine
M = RP.M
v, r = M.series(RP.P["canadian"]["portfolio"])
vol = (v.pct_change().dropna()).std(ddof=1) * np.sqrt(252)
print("Canadian today vol gap:", abs(vol - RP.RUN["canadian"]["metrics"]["today"]["volatility"]), "n sessions", len(v))
# 3. every pre-2022-08-22 CNQ close carries the 1.021 factor?
px = pd.read_csv(REPO / "data/starter/prices_daily.csv", parse_dates=["date"])
c = px[(px.ticker == "CNQ.TO") & (px.date < "2022-08-22")]["close"]
cents = lambda x: np.abs(x - np.round(x, 2)) < 0.0005
print("pre-08-22 closes:", len(c), " clean cents with x1.021x2:", cents(c * 1.021 * 2).mean(), " clean cents with x2 only:", cents(c * 2).mean())
