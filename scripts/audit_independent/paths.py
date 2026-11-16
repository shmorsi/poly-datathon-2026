"""Where the independent audit reads and writes. It imports no module of the repository: it only reads its files.

EPI_AUDIT_RUNS  folder of the saved runs to compare with ({robert,mateo,amira,canadian}.json); default data/demo_runs
EPI_AUDIT_OUT   folder for the audit's own outputs (table.md, *_out.json); default /tmp/epi_audit_independent
"""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]          # scripts/audit_independent/ -> the repository root
RUNS = Path(os.environ.get("EPI_AUDIT_RUNS") or REPO / "data" / "demo_runs")
OUT = Path(os.environ.get("EPI_AUDIT_OUT") or "/tmp/epi_audit_independent")
DEEP = REPO / "data" / "cache" / "deep"
OUT.mkdir(parents=True, exist_ok=True)
