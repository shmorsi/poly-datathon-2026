import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # this folder only (the scripts run with -I)
from paths import DEEP, OUT, REPO, RUNS  # noqa: E402,F401
import hashlib, json
from pathlib import Path
R = REPO
m = json.load(open(R / "data/cache/deep/manifest.json"))
ok = 0
for f in m["files"]:
    h = hashlib.sha256((R / f["path"]).read_bytes()).hexdigest()
    ok += h == f["sha256"]
    print(f["id"], "OK" if h == f["sha256"] else "MISMATCH")
p = m["panel"]
h = hashlib.sha256((R / p["path"]).read_bytes()).hexdigest()
print("panel", "OK" if h == p["sha256"] else "MISMATCH", "| rows", p["rows"], p["first"], p["last"], "| retrieved_at:", m.get("retrieved_at"))
print(f"{ok}/{len(m['files'])} raw files match")
