import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # this folder only (the scripts run with -I)
from paths import DEEP, OUT, REPO, RUNS  # noqa: E402,F401
import io, zipfile, sys
import pandas as pd
R = str(DEEP / "raw") + "/"
z = zipfile.ZipFile(R + "french_49/49_Industry_Portfolios_CSV.zip")
print(z.namelist())
txt = z.read(z.namelist()[0]).decode("latin-1")
lines = txt.splitlines()
# first block = Average Value Weighted Returns -- Monthly
hdr_i = next(i for i, l in enumerate(lines) if l.strip().startswith(",Agric"))
print("header line", hdr_i, lines[hdr_i - 2:hdr_i + 1])
hdr = [h.strip() for h in lines[hdr_i].split(",")]
rows = []
for l in lines[hdr_i + 1:]:
    p = [x.strip() for x in l.split(",")]
    if len(p) != len(hdr) or not p[0].isdigit() or len(p[0]) != 6:
        break
    rows.append(p)
df = pd.DataFrame(rows, columns=["ym"] + hdr[1:]).set_index("ym").astype(float) / 100
print(df[["Chips", "Softw", "Hardw", "Oil", "Banks"]].loc[["197301", "197302", "202111", "202112", "202510"]])
panel = pd.read_csv(DEEP / "panel.csv").set_index("month")
for m in ["1973-01", "1973-02", "2021-11", "2021-12", "2025-10"]:
    ym = m.replace("-", "")
    prev = panel.index[panel.index.get_loc(m) - 1]
    fxr = panel.loc[m, "USDCAD_END"] / panel.loc[prev, "USDCAD_END"]
    usd = df.loc[ym, "Chips"]
    print(m, "panel CHIPS", round(panel.loc[m, "CHIPS"], 6), " FF USD", round(usd, 6), " USD x FXend", round((1 + usd) * fxr - 1, 6))
g = pd.read_csv(R + "worldbank_gold/gold_monthly.csv")
print(g.head(3)); print(g.columns.tolist()); print(g[g.iloc[:, 0].astype(str).str.startswith(("1973", "2021-1"))].head(16))
