# Independent re-implementation of the headline numbers

Written on 2026-11-15 by a separate agent (lane accuracy) from `docs/finance_methods.md` (sections 2 to 4 and Appendix C)
and the raw files alone. It imports nothing from the engine: no module of this repository is imported (`paths.py` only
says where the files are), and every script runs with `python -I`, so the repository is not even on the import path.
It recomputes each headline figure its own way and compares it with the saved runs.

**Needs** (local, never committed): the starter pack in `data/starter/`, `data/etf_holdings.csv` (the look-through rows),
the deep-history cache in `data/cache/deep/` (`scripts/fetch_deep.py`) and the four saved runs
(`robert.json`, `mateo.json`, `amira.json`, `canadian.json`).

**Run** (from the repository root):

    EPI_AUDIT_RUNS=<folder of the four saved runs> .venv/bin/python -I scripts/audit_independent/report.py

`EPI_AUDIT_RUNS` defaults to `data/demo_runs`; `EPI_AUDIT_OUT` (default `/tmp/epi_audit_independent`) receives
`table.md` and the scripts' JSON outputs. No AWS call; nothing in the repository is written.

**Expected output:** the table in [docs/audit_independent.md](../../docs/audit_independent.md), printed and written to
`$EPI_AUDIT_OUT/table.md`, ending with `verdicts: {'OK': 32}`. A row is OK when the recomputed value rounds to the page
value and is within 0.1 point (or $100) of the engine's unrounded value.

**The other scripts** are the checks behind it, each runnable the same way: `daily.py` (series, falls, CAGR, the size
curve), `events_ind.py` (the shock check, its own dating and episode rules), `deep_ind.py` (the 33 deep-history values:
11 crises x today, after, the chip industry alone), `lt_band.py` (the start-month band), `extras.py` and
`sensitivity.py` (the wider page figures and the method choices the engine shares with this code), `claims.py` (the
CNQ.TO close check), and the panel rebuilt from the raw downloads (`rawcheck.py`, `panelcheck.py`, `bondcheck.py`,
`goldcheck.py`, `tsxcheck.py`, `caeq.py`, `hashes.py`). `write_report.py` writes the lane's full report to
`$EPI_AUDIT_OUT/accuracy.md`.
