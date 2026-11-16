"""Rebuild CAD_BOND (par-bond ladder) and CAD_TBILL from the raw StatCan 10-10-0122-01 file (read-only)."""
import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # this folder only (the scripts run with -I)
from paths import DEEP, OUT, REPO, RUNS  # noqa: E402,F401
import io
import zipfile

import numpy as np
import pandas as pd

R = str(DEEP) + "/"
panel = pd.read_csv(R + "panel.csv").set_index("month")
z = zipfile.ZipFile(R + "raw/statcan_10100122/10100122-eng.zip")
name = next(n for n in z.namelist() if n.endswith(".csv") and "MetaData" not in n)
df = pd.read_csv(io.BytesIO(z.read(name)), dtype=str)
vec = df["VECTOR"].str.strip()
want = ["v122558", "v122485", "v122486", "v122487", "v122531", "v122541"]
label_col = [c for c in df.columns if c not in ("REF_DATE", "GEO", "DGUID", "UOM", "UOM_ID", "SCALAR_FACTOR",
                                                 "SCALAR_ID", "VECTOR", "COORDINATE", "VALUE", "STATUS",
                                                 "SYMBOL", "TERMINATED", "DECIMALS")]
for v in want:
    row = df[vec == v].iloc[0]
    print(v, "|", " / ".join(str(row[c]) for c in label_col))
Y = {v: pd.to_numeric(df.loc[vec == v, "VALUE"], errors="coerce").set_axis(df.loc[vec == v, "REF_DATE"].str[:7]).groupby(level=0).last()
     for v in want}

# standard constant-maturity par-bond monthly total return (semiannual coupons), e.g. Swinkels (2019):
# bought at par at y0 (coupon y0), held one month, repriced at y1 with N - 1/12 years left, plus y0/12 income
def par_ret(y, N):
    y0, y1 = y.shift(1) / 100, y / 100
    v = (1 + y1 / 2) ** (-2 * (N - 1 / 12))
    return y0 / 12 + (y0 / y1) * (1 - v) + v - 1

LADDER = {"v122558": (2.0, 0.28), "v122485": (4.0, 0.22), "v122486": (7.5, 0.21), "v122487": (20.0, 0.29)}
bond = sum(par_ret(Y[v], N) * w for v, (N, w) in LADDER.items())
bill = Y["v122531"].combine_first(Y["v122541"]).shift(1) / 100 / 12
for a, b in [("1973-01", "1974-12"), ("2000-01", "2002-12"), ("2007-06", "2009-06")]:
    m = panel.loc[a:b].index
    gb = np.nanmax(np.abs(bond.reindex(m).values - panel.loc[m, "CAD_BOND"].values))
    gt = np.nanmax(np.abs(bill.reindex(m).values - panel.loc[m, "CAD_TBILL"].values))
    print(f"{a}..{b}: CAD_BOND max gap {gb*100:.5f} pp | CAD_TBILL max gap {gt*100:.5f} pp | NaN in panel bond: {panel.loc[m,'CAD_BOND'].isna().sum()}")
