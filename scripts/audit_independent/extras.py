import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # this folder only (the scripts run with -I)
from paths import DEEP, OUT, REPO, RUNS  # noqa: E402,F401
import json
import sys

import pandas as pd

import core
from core import Market, apply_set, apply_add, drawdown, cagr, REPO
import events_ind as E

P = json.load(open(REPO / "data/personas.json"))["pilots"]
M = E.M
H = pd.read_csv(REPO / "data/etf_holdings.csv")
ctry = {k: dict(zip(g["name"], g["weight"])) for k, g in H[H.kind == "country"].groupby("etf")}
sect = {k: dict(zip(g["name"], g["weight"])) for k, g in H[H.kind == "sector"].groupby("etf")}
hold = {k: dict(zip(g["ticker"].fillna(""), g["weight"])) for k, g in H[H.kind == "holding"].groupby("etf")}
uni = pd.read_csv(REPO / "data/starter/assets_universe.csv").set_index("ticker")


def can_frac(t):
    if t in ctry:
        return ctry[t].get("CAN", 0.0)
    return 1.0 if t.endswith(".TO") else 0.0


def show(label, mine, eng):
    gap = None if eng is None else (mine - eng) * 100
    print(f"{label:55s} mine {mine*100:9.4f}   engine {'' if eng is None else f'{eng*100:9.4f}'}   gap {'' if gap is None else f'{gap:+.4f} pt'}")


# Mateo price of values: CNQ.TO removed, rest scaled up
mt = P["mateo"]["portfolio"]
pv = {t: x / (1 - mt["CNQ.TO"]) for t, x in mt.items() if t != "CNQ.TO"}
v, _ = M.series(pv)
mj = json.load(open(RUNS / "mateo.json"))
pov = mj.get("price_of_values") or {}
print("engine price_of_values keys:", list(pov)[:20])
show("Mateo without CNQ: worst drop", drawdown(v)[0], None)
show("Mateo without CNQ: CAGR", cagr(v), None)
show("Mateo without CNQ: war & oil shock check", E.summary(pv, "war_oil")["worst"], None)
print(json.dumps(pov, ensure_ascii=False)[:1200])

# Canadian: risk shares and Canada's share of the risk
cj = json.load(open(RUNS / "canadian.json"))
ct = P["canadian"]["portfolio"]
ca = apply_add(ct, "SPY", 0.2)
for side, w in (("today", ct), ("after", ca)):
    _, r = M.series(w)
    rc, enb = core.risk_contrib(r, w)
    canr = sum(rc[t] * can_frac(t) for t in rc)
    canr_norm = sum(rc[t] * can_frac(t) / (max(1.0, sum(ctry.get(t, {"x": 1}).values()))) for t in rc)
    eng = cj["diversification"][side]["can_risk_share"]
    show(f"Canadian {side}: Canada's share of the risk (raw split)", canr, eng)
    show(f"Canadian {side}: Canada's share of the risk (split/sum>1)", canr_norm, eng)
    show(f"Canadian {side}: XIU.TO share of the risk", rc["XIU.TO"], cj["risk"][side]["shares"]["XIU.TO"])
    print(f"   bets mine {enb:.4f} engine {cj['risk'][side]['bets']:.4f}")

# Amira look-through: NVDA one-company share and Information Technology
aw = P["amira"]["portfolio"]
nv = aw["NVDA"] + sum(aw.get(e, 0) * hold[e].get("NVDA", 0) for e in hold)
it = 0.0
for t, x in aw.items():
    if t in sect:
        it += x * sect[t].get("Information Technology", 0.0)
    elif uni.loc[t, "sector"] == "Information Technology":
        it += x
aj = json.load(open(RUNS / "amira.json"))
lt = aj["lookthrough"]["today"]
show("Amira NVDA one company (direct + inside funds)", nv, (lambda s: s.get("weight", s.get("total")) if isinstance(s, dict) else s)(lt["stocks"].get("NVDA")))
show("Amira Information Technology (look-through)", it, (lambda s: s.get("weight", s.get("total")) if isinstance(s, dict) else s)(lt["sectors"].get("Information Technology")))
show("Amira crypto share", aw["BTC-USD"], None)

# Robert ladder: SPY / QQQ at 40 %
rj = json.load(open(RUNS / "robert.json"))
rt = P["robert"]["portfolio"]
for row in rj["ladder"]["rows"]:
    w = apply_set(rt, row["ticker"], 0.4)
    v, _ = M.series(w)
    d = drawdown(v)
    show(f"Robert ladder {row['ticker']} at 40 %: worst drop ({d[1].date()}->{d[2].date()})", d[0], row["max_drawdown"])
    print(f"   end mine {600000*v.iloc[-1]/100:,.0f} engine {row['end_value']:,}  CAGR mine {cagr(v)*100:.4f} engine {row['cagr']*100:.4f}")
