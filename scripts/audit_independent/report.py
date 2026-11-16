"""One consolidated run: my values vs the saved runs, as markdown rows (no repo imports)."""
import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # this folder only (the scripts run with -I)
from paths import DEEP, OUT, REPO, RUNS  # noqa: E402,F401
import json
import sys
from decimal import Decimal, ROUND_HALF_UP

import pandas as pd

from core import Market, apply_add, apply_set, cagr, drawdown, risk_contrib, round_pp, REPO
import events_ind as E

RUN = {k: json.load(open(RUNS / f"{k}.json")) for k in ("robert", "mateo", "amira", "canadian")}
P = json.load(open(REPO / "data/personas.json"))["pilots"]
M = E.M
rows = []


def pct1(x):
    return str(Decimal(repr(float(x) * 100)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def add(name, page, mine, eng, kind="pct", note=""):
    if kind == "pct":
        gap = (mine - eng) * 100
        bad = abs(gap) > 0.1
        rounds = pct1(mine) == page.replace("−", "-").replace(" %", "").strip()
        rows.append((name, page.replace("-", "−"), f"{mine*100:.4f} %", f"{eng*100:.4f} %", f"{gap:+.4f} pt",
                     ("CHECK" if bad or not rounds else "OK") + (f" ({note})" if note else "")))
    elif kind == "usd":
        gap = mine - eng
        rows.append((name, page, f"${mine:,.2f}", f"${eng:,.2f}", f"{gap:+,.2f} $",
                     ("CHECK" if abs(gap) > 100 else "OK") + (f" ({note})" if note else "")))
    else:  # exact text
        rows.append((name, page, str(mine), str(eng), "0" if str(mine) == str(eng) else "differs",
                     ("OK" if str(mine) == str(eng) else "CHECK") + (f" ({note})" if note else "")))


rob, R = P["robert"], RUN["robert"]
rt, ra = rob["portfolio"], apply_set(rob["portfolio"], "NVDA", 0.4)
vt, rtr = M.series(rt)
va, rar = M.series(ra)
dt, da = drawdown(vt), drawdown(va)
add("Robert today: worst fall", "−10.6 %", dt[0], R["metrics"]["today"]["max_drawdown"])
add("Robert with 40 % NVDA: worst fall", "−34.5 %", da[0], R["metrics"]["after"]["max_drawdown"])
add("…its dollars on $600,000", "−$207,146", 600000 * da[0], R["kpis"]["max_drawdown"]["loss_dollars"], "usd")
add("…its peak / trough dates", "2021-11-29 / 2022-10-14", f"{da[1].date()} / {da[2].date()}",
    f"{R['metrics']['after']['peak_date']} / {R['metrics']['after']['trough_date']}", "text")
add("Robert today: peak / trough dates", "2022-03-04 / 2022-10-11", f"{dt[1].date()} / {dt[2].date()}",
    f"{R['metrics']['today']['peak_date']} / {R['metrics']['today']['trough_date']}", "text")
add("CAGR today", "8.7 %", cagr(vt), R["metrics"]["today"]["cagr"])
add("CAGR after", "25.2 %", cagr(va), R["metrics"]["after"]["cagr"])
add("End value today (2026-11-12)", "$911,676", 6000 * vt.iloc[-1], R["end_values"]["today"], "usd", "page shows whole dollars")
add("End value after", "$1,847,077", 6000 * va.iloc[-1], R["end_values"]["after"], "usd", "page shows whole dollars")
first = None
for k in range(41):
    v, _ = M.series(apply_set(rt, "NVDA", k / 100) if k else rt)
    if round_pp(drawdown(v)[0]) < -0.15:
        first = k
        break
eng_first = round(R["tipping_point"]["max_weight"] * 100) + 1
add("First NVDA size that breaks the −15 % floor", "9 %", f"{first} %", f"{eng_first} %", "text",
    "8 % reads −15.00004 %, inside only after ROUND_HALF_UP")
v23, _ = M.series(ra, start="2023-01-01")
d23 = drawdown(v23)
add("Worst fall with 2022 left out (from 2023-01-01)", "−16.9 %", d23[0], R["not_2022"]["depth"], "pct",
    f"{d23[1].date()} → {d23[2].date()}")
rca, enba = risk_contrib(rar, ra)
rct, enbt = risk_contrib(rtr, rt)
add("NVDA's share of the risk (Euler, daily cov.)", "89.6 %", rca["NVDA"], R["risk"]["after"]["shares"]["NVDA"])
rows.append(("Independent bets today → after", "2.4 → 1.2", f"{enbt:.4f} → {enba:.4f}",
             f"{R['risk']['today']['bets']:.4f} → {R['risk']['after']['bets']:.4f}",
             f"{enbt - R['risk']['today']['bets']:+.4f} / {enba - R['risk']['after']['bets']:+.4f}", "OK"))
H = pd.read_csv(REPO / "data/etf_holdings.csv")
ctry = {k: dict(zip(g["name"], g["weight"])) for k, g in H[H.kind == "country"].groupby("etf")}
can = lambda w: sum(x * (ctry[t].get("CAN", 0) if t in ctry else (1.0 if t.endswith(".TO") else 0.0)) for t, x in w.items())
add("Canada's share of the money today (look-through)", "87.6 %", can(rt), R["diversification"]["today"]["countries"]["CAN"],
    "pct", "engine rescales XIU.TO's country rows (sum 100.02 %)")
add("Canada's share of the money after", "52.6 %", can(ra), R["diversification"]["after"]["countries"]["CAN"], "pct", "same rescaling")
s = E.summary(ra, "tariffs")
add("Tariff shock check, after (worst clean episode)", "−9.0 %", s["worst"], R["turbulence"]["tariffs"]["worst_after"], "pct",
    f"{s['worst_ep']}, low 2025-04-08")
add("…separate clean tariff episodes", "6", f"{s['n']} ({s['label']})",
    f"{R['turbulence']['tariffs']['n']} ({R['turbulence']['tariffs']['evidence']})", "text")
vm, _ = M.series(P["mateo"]["portfolio"])
add("Mateo: worst fall", "−11.4 %", drawdown(vm)[0], RUN["mateo"]["metrics"]["today"]["max_drawdown"])
vam, _ = M.series(P["amira"]["portfolio"])
add("Amira: worst fall", "−41.3 %", drawdown(vam)[0], RUN["amira"]["metrics"]["today"]["max_drawdown"])
C = RUN["canadian"]["hedge_compare"]
ca = apply_add(P["canadian"]["portfolio"], "SPY", 0.2)
vu, _ = M.series(ca)
hp = M.cad.copy()
hp["SPY"] = M.local["SPY"]
vh, _ = M.series(ca, prices=hp)
add("Too Canadian? + 20 % SPY, unhedged: worst fall", "−12.9 %", drawdown(vu)[0], C["unhedged"]["worst_fall"])
add("…CAD-hedged stand-in: worst fall", "−14.2 %", drawdown(vh)[0], C["hedged_standin"]["worst_fall"])
spy = M.adj_raw["SPY"].dropna()
a, b = pd.Timestamp("2021-12-31"), pd.Timestamp("2022-12-31")
usd = spy[spy.index <= b].iloc[-1] / spy[spy.index <= a].iloc[-1] - 1
cs = M.cad["SPY"]
cad = cs[cs.index <= b].iloc[-1] / cs[cs.index <= a].iloc[-1] - 1
add("SPY 2022, US dollars", "−18.2 %", usd, C["spy_2022"]["usd"])
add("SPY 2022, Canadian dollars", "−12.6 %", cad, C["spy_2022"]["cad"])

import deep_ind as D
eng = {e["id"]: e for e in R["deep_history"]["episodes"]}
for eid, lab, pg in (("oil_embargo_1973", "1973–74", ("−15.2 %", "−29.6 %", "−57.3 %")),
                     ("dotcom_2000", "2000–02", ("−11.3 %", "−50.4 %", "−82.5 %")),
                     ("gfc_2008", "2008–09", ("−17.0 %", "−23.7 %", "−40.1 %"))):
    e = D.eps.set_index("episode_id").loc[eid]
    for side, w, key, p in (("today", D.rt, "today", pg[0]), ("after", D.ra, "after", pg[1]),
                            ("US chip industry alone", {"NVDA": 1.0}, "proxy_alone", pg[2])):
        mine = D.replay(w, e.start, e.end)[0]
        dollars = f"; ${-600000*mine:,.0f}" if side != "US chip industry alone" else ""
        add(f"Deep {lab}: {side}", p, mine, eng[eid][key], "pct", f"by proxy, monthly{dollars}")

with open(OUT / "table.md", "w") as f:
    f.write("| # | Number | Page value | My value | Engine (saved run, unrounded) | Gap | Verdict |\n")
    f.write("|---:|---|---|---|---|---|---|\n")
    for i, r in enumerate(rows, 1):
        f.write(f"| {i} | " + " | ".join(r) + " |\n")
print(open(OUT / "table.md").read())
print("verdicts:", pd.Series([r[-1].split(" ")[0] for r in rows]).value_counts().to_dict())
