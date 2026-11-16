import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # this folder only (the scripts run with -I)
from paths import DEEP, OUT, REPO, RUNS  # noqa: E402,F401
import json
import sys

import pandas as pd

from core import Market, apply_set, drawdown, round_pp, REPO

H = pd.read_csv(REPO / "data/etf_holdings.csv")
uni = pd.read_csv(REPO / "data/starter/assets_universe.csv").set_index("ticker")
ctry = H[H.kind == "country"].groupby("etf").apply(lambda g: dict(zip(g["name"], g["weight"])), include_groups=False).to_dict()


def country_of_direct(t):
    if t.endswith(".TO"):
        return "CAN"
    if t.endswith("-USD"):
        return "CRYPTO"
    return "USA"


def canada_share(w, normalize_over_one=False):
    s = 0.0
    for t, x in w.items():
        if t in ctry:
            split = ctry[t]
            tot = sum(split.values())
            k = tot if (normalize_over_one and tot > 1) else 1.0
            s += x * split.get("CAN", 0.0) / k
        else:
            s += x * (1.0 if country_of_direct(t) == "CAN" else 0.0)
    return s


P = json.load(open(REPO / "data/personas.json"))["pilots"]
rt = P["robert"]["portfolio"]
ra = apply_set(rt, "NVDA", 0.4)
print("country split sums:", {k: round(sum(v.values()), 4) for k, v in ctry.items()})
for nm, w in (("today", rt), ("after", ra)):
    print(f"Robert {nm}: Canada share raw {canada_share(w)*100:.4f} %  (normalised when split>1: {canada_share(w, True)*100:.4f} %)")
ct = P["canadian"]["portfolio"]
ca = {"XIU.TO": 0.48, "XBB.TO": 0.24, "ZST.TO": 0.08, "SPY": 0.2}
for nm, w in (("today", ct), ("after", ca)):
    print(f"Canadian {nm}: Canada share raw {canada_share(w)*100:.4f} %  (norm {canada_share(w, True)*100:.4f} %)")
for nm in ("mateo", "amira"):
    w = P[nm]["portfolio"]
    print(f"{nm}: Canada share raw {canada_share(w)*100:.4f} %  (norm {canada_share(w, True)*100:.4f} %)")
# the '89 %' candidates for Robert today
print("candidates for '89 %':", "XIU look-through only", round((0.45 * 0.9771 + 0.35 + 0.10) * 100, 3),
      "| XBB look-through only", round((0.45 + 0.35 * 0.9621 + 0.10) * 100, 3),
      "| direct listing", 90.0)

# 25-start-month band (floor rule only), 1 % steps from today's mix
import sys as _s; _s.exit(0) if "--lt" in _s.argv else None
M = Market()
months = pd.period_range("2021-11", "2023-11", freq="M")
band = []
for m in months:
    first = M.days[M.days >= m.start_time][0]
    fb = None
    for k in range(41):
        w = apply_set(rt, "NVDA", k / 100) if k else dict(rt)
        v, _ = M.series(w, start=first)
        d = drawdown(v)[0]
        if round_pp(d) < -0.15:
            fb = k
            break
    band.append((str(m), str(first.date()), fb))
eng = {s["start"]: s for s in json.load(open(RUNS / "robert.json"))["tipping_band"]["starts"]}
diff = [(s, f, fb, round(eng[s]["first_break"] * 100)) for s, f, fb in band if s in eng and round(eng[s]["first_break"] * 100) != fb]
print("band first-break sizes:", [b[2] for b in band])
print("band lo/hi:", min(b[2] for b in band if b[2] is not None), max(b[2] for b in band if b[2] is not None),
      "| engine starts", len(eng), "| mismatches", diff)
