"""Independent proxy replay of the deep-history episodes (monthly, CAD, constant weights rebalanced monthly)."""
import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # this folder only (the scripts run with -I)
from paths import DEEP, OUT, REPO, RUNS  # noqa: E402,F401
import json
import sys

import pandas as pd

from core import REPO

panel = pd.read_csv(REPO / "data/cache/deep/panel.csv").set_index("month")
prox = pd.read_csv(REPO / "data/deep_proxies.csv").set_index("ticker")["proxy"].to_dict()
eps = pd.read_csv(REPO / "data/deep_episodes.csv")
P = json.load(open(REPO / "data/personas.json"))["pilots"]
rt = P["robert"]["portfolio"]
ra = {"XIU.TO": 0.27, "XBB.TO": 0.21, "GLD": 0.06, "ZST.TO": 0.06, "NVDA": 0.40}


def replay(w, start, end, base="prior"):
    cols = {}
    for t, x in w.items():
        c = prox[t]
        cols[c] = cols.get(c, 0) + x
    idx = panel.index
    i0, i1 = idx.get_loc(start), idx.get_loc(end)
    r = panel.iloc[i0:i1 + 1][list(cols)]
    if r.isna().any().any():
        return None
    pr = (r * pd.Series(cols)).sum(axis=1)
    v = (1 + pr).cumprod()
    if base == "prior":   # base 1 at the end of the month before `start`
        v = pd.concat([pd.Series([1.0], index=[idx[i0 - 1]]), v])
    dd = v / v.cummax() - 1
    t = dd.idxmin()
    pk = v.loc[:t].idxmax()
    return float(dd.min()), pk, t


run = json.load(open(RUNS / "robert.json"))["deep_history"]["episodes"]
eng = {e["id"]: e for e in run}
print(f"{'episode':18s} {'side':6s} {'mine(prior base)':>17s} {'mine(start base)':>17s} {'engine':>10s}  peak/trough mine vs engine")
rows = {}
for e in eps.itertuples():
    for side, w in (("today", rt), ("after", ra), ("alone", {"NVDA": 1.0})):
        a = replay(w, e.start, e.end, "prior")
        b = replay(w, e.start, e.end, "start")
        key = {"today": "today", "after": "after", "alone": "proxy_alone"}[side]
        g = eng[e.episode_id][key]
        det = eng[e.episode_id].get(f"{side}_detail", {}) if side != "alone" else {"peak": None, "trough": eng[e.episode_id]["alone_trough"]}
        rows[(e.episode_id, side)] = (a[0], g)
        print(f"{e.episode_id:18s} {side:6s} {a[0]*100:16.4f}% {b[0]*100:16.4f}% {g*100:9.4f}%  "
              f"{a[1]}/{a[2]} vs {det.get('peak')}/{det.get('trough')}")
json.dump({f"{k[0]}|{k[1]}": v for k, v in rows.items()}, open(OUT / "deep_out.json", "w"), indent=1)
