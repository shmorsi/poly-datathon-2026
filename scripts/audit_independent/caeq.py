import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # this folder only (the scripts run with -I)
from paths import DEEP, OUT, REPO, RUNS  # noqa: E402,F401
import zipfile
import numpy as np, pandas as pd
R = str(DEEP) + "/"
z = zipfile.ZipFile(R + "raw/french_countries/F-F_International_Countries.zip")
txt = z.read("Canada.Dat").decode("latin-1").splitlines()
heads = [(k, l.strip()) for k, l in enumerate(txt) if l.strip() and not l.strip()[0].isdigit() and "--" not in l and "Mkt" not in l]
print(heads[:12])
panel = pd.read_csv(R + "panel.csv").set_index("month")
def block(start):
    rows = {}
    for l in txt[start:]:
        p = l.split()
        if not p:
            if rows: break
            continue
        if p[0].isdigit() and len(p[0]) == 6:
            rows[f"{p[0][:4]}-{p[0][4:]}"] = float(p[1]) / 100
        elif rows:
            break
    return pd.Series(rows)
for k, h in heads:
    s = block(k + 1)
    if not len(s): continue
    for a, b in [("2000-01", "2002-12"), ("2007-06", "2009-06")]:
        m = panel.loc[a:b].index
        gap = np.nanmax(np.abs(s.reindex(m).values - panel.loc[m, "CA_EQ"].values))
        print(f"block '{h[:45]}' {a}..{b}: max |FF Canada Mkt - panel CA_EQ| = {gap*100:.4f} pp")
