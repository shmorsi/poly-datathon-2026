"""Rebuild pre-1977 CA_EQ (TSX composite close return + previous month's dividend yield / 12) from StatCan 10-10-0125-01."""
import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # this folder only (the scripts run with -I)
from paths import DEEP, OUT, REPO, RUNS  # noqa: E402,F401
import io
import zipfile

import numpy as np
import pandas as pd

R = str(DEEP) + "/"
panel = pd.read_csv(R + "panel.csv").set_index("month")
z = zipfile.ZipFile(R + "raw/statcan_10100125/10100125-eng.zip")
name = next(n for n in z.namelist() if n.endswith(".csv") and "MetaData" not in n)
df = pd.read_csv(io.BytesIO(z.read(name)), dtype=str)
df["VECTOR"] = df["VECTOR"].str.strip()
lab = [c for c in df.columns if c not in ("REF_DATE", "GEO", "DGUID", "UOM", "UOM_ID", "SCALAR_FACTOR", "SCALAR_ID",
                                          "VECTOR", "COORDINATE", "VALUE", "STATUS", "SYMBOL", "TERMINATED", "DECIMALS")]
# find the composite close and dividend-yield vectors by their labels, not by the engine's ids
labels = df.drop_duplicates("VECTOR").set_index("VECTOR")[lab + ["UOM"]].astype(str).agg(" / ".join, axis=1)
cands = labels[labels.str.contains("omposite", case=False)]
for v, l in cands.items():
    print(v, "|", l)
pick_close = [v for v, l in cands.items() if "close" in l.lower() and "yield" not in l.lower()]
pick_yield = [v for v, l in cands.items() if "yield" in l.lower()]
print("close candidates", pick_close, "yield candidates", pick_yield)
ser = lambda v: pd.to_numeric(df.loc[df.VECTOR == v, "VALUE"], errors="coerce").set_axis(df.loc[df.VECTOR == v, "REF_DATE"].str[:7]).groupby(level=0).last()
for c in pick_close:
    for y in pick_yield:
        P, Y = ser(c), ser(y)
        early = P / P.shift(1) - 1 + Y.shift(1) / 100 / 12
        m = panel.loc["1973-01":"1974-12"].index
        gap = np.nanmax(np.abs(early.reindex(m).values - panel.loc[m, "CA_EQ"].values))
        print(f"close {c} + yield {y}: 1973-01..1974-12 max |mine - panel CA_EQ| = {gap*100:.5f} pp")
