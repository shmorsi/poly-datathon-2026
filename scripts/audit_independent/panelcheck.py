"""Spot-check panel.csv columns against the raw source files over the three requested windows (read-only)."""
import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # this folder only (the scripts run with -I)
from paths import DEEP, OUT, REPO, RUNS  # noqa: E402,F401
import io
import zipfile

import numpy as np
import pandas as pd

R = str(DEEP) + "/"
panel = pd.read_csv(R + "panel.csv").set_index("month")
WIN = [("1973-01", "1974-12"), ("2000-01", "2002-12"), ("2007-06", "2009-06")]


def ff_block(zpath, col_hint):
    z = zipfile.ZipFile(zpath)
    txt = z.read(z.namelist()[0]).decode("latin-1").splitlines()
    i = next(k for k, l in enumerate(txt) if col_hint in l and l.startswith(","))
    hdr = [h.strip() for h in txt[i].split(",")]
    rows = []
    for l in txt[i + 1:]:
        p = [x.strip() for x in l.split(",")]
        if len(p) != len(hdr) or not (p[0].isdigit() and len(p[0]) == 6):
            break
        rows.append(p)
    df = pd.DataFrame(rows, columns=["ym"] + hdr[1:])
    df.index = [f"{s[:4]}-{s[4:]}" for s in df.ym]
    return df.drop(columns="ym").astype(float) / 100


ff49 = ff_block(R + "raw/french_49/49_Industry_Portfolios_CSV.zip", "Chips")
# FRED daily USD/CAD (CAD per USD): month-end = last observation of the month
fx = pd.read_csv(R + "raw/fred_DEXCAUS/DEXCAUS.csv")
fx.columns = ["date", "v"]
fx["v"] = pd.to_numeric(fx["v"], errors="coerce")
fx = fx.dropna()
fx["m"] = fx["date"].str[:7]
fxe = fx.groupby("m")["v"].last()

for a, b in WIN:
    months = panel.loc[a:b].index
    prev = panel.index[panel.index.get_loc(a) - 1]
    fxs = fxe.reindex([prev] + list(months))
    fx_gap = np.nanmax(np.abs(fxs.values - panel.loc[[prev] + list(months), "USDCAD_END"].values))
    fxr = fxs.values[1:] / fxs.values[:-1]
    chips_raw = (1 + ff49.loc[months, "Chips"].values) * fxr - 1
    gap = np.max(np.abs(chips_raw - panel.loc[months, "CHIPS"].values))
    print(f"{a}..{b}: USDCAD_END vs FRED month-end max gap {fx_gap:.4f}; CHIPS vs FF49 Chips x FRED FX max gap {gap*100:.4f} pp")

# Canada (local currency) from the French international countries file, if present
z = zipfile.ZipFile(R + "raw/french_countries/F-F_International_Countries.zip")
names = [n for n in z.namelist() if "anada" in n]
print("Canada files in the countries zip:", names[:5])
