import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # this folder only (the scripts run with -I)
from paths import DEEP, OUT, REPO, RUNS  # noqa: E402,F401
import numpy as np, pandas as pd
R = str(DEEP) + "/"
panel = pd.read_csv(R + "panel.csv").set_index("month")
g = pd.read_csv(R + "raw/worldbank_gold/gold_monthly.csv").set_index("month")["gold_usd_oz"]
ex = pd.read_csv(R + "raw/fred_EXCAUS/EXCAUS.csv"); ex.columns = ["date", "v"]
ex["v"] = pd.to_numeric(ex["v"], errors="coerce"); ex["m"] = ex["date"].str[:7]; ex = ex.set_index("m")["v"]
for a, b in [("1973-01", "1974-12"), ("2000-01", "2002-12"), ("2007-06", "2009-06")]:
    m = list(panel.loc[a:b].index); prev = panel.index[panel.index.get_loc(a) - 1]
    gm, xm = g.reindex([prev] + m).values, ex.reindex([prev] + m).values
    mine = gm[1:] / gm[:-1] * xm[1:] / xm[:-1] - 1
    print(f"{a}..{b}: max |mine - panel GOLD| = {np.nanmax(np.abs(mine - panel.loc[m, 'GOLD'].values))*100:.4f} pp")
