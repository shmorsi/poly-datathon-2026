"""The seed sweep behind the bets fixture of tests/test_metrics.py (plan C Task 6; ledger §30).

    python scripts/check_bets_fixture.py N FIRST_SEED COUNT [engine]

Why: the test draws ONE seed, so it passes or fails on that draw alone. The bounds it pins (risk shares 0.5 +- 0.02 and Meucci
ENB 2.0 +- 0.05 on the main fixture; ENB < 1.1 on the near-duplicate twin) are trustworthy only if they hold on many draws.
This script re-draws the fixture for COUNT seeds and counts the seeds on which each bound fails. Ledger §27 says "never change
the seed or numpy without re-checking": run it after any change to the seed, the fixture, numpy, pandas or tools/risk.py.

The fixture mirrors the test line for line (change both together): two lines with daily vol 1 % and 2 % and weights 2/3 and
1/3 (the risk splits 50/50, the money does not), and C = A + noise of 0.1 %, a near-duplicate of A (50/50 A and C is one bet).
Meucci's effective number of bets reads 2.0 on the first and 1.0 on the twin; the retired 1/sum(RC^2) and a covariance-blind
count read 2.0 on both, which is why the twin is there.

  N           returns per line. The test uses 10000; at 2000 the share bound fails on 42 of 500 seeds.
  FIRST_SEED  first seed of the range; the test uses seed 1.
  COUNT       how many seeds: FIRST_SEED .. FIRST_SEED + COUNT - 1.
  engine      also run the checkout's own tools/risk.py (A Task 8) on every seed through tools.data.make_market, as the test
              does. The environment variable SWEEP_TREE=<dir> picks another checkout; the default is this repo.
Without `engine` it runs its own replica of the specified estimator (ledger §14: sample covariance with ddof 1, risk share
w_i (S w)_i / w'S w, ENB = exp(-sum p ln p) with p_k = lambda_k (w'e_k)^2 / w'S w), so it also works before tools/risk.py exists.
Exit status 0 when every bound holds on every seed, 1 otherwise. No file, no network; stdlib, numpy and pandas only.

Expected at N = 10000, seeds 0..499 (`python scripts/check_bets_fixture.py 10000 0 500 engine`; Measured 2026-11-14, numpy 2.5.4,
pandas 3.1.1, N = 500 seeds, 0 / 500 failures for each bound, Wilson 95 % upper bound 0.8 %; limit: synthetic Gaussian returns,
so it checks the fixture's bounds, not the estimator on real prices):

    bets fixture: 10000 returns per line, seeds 0..499 (500 seeds), replica of the specified estimator
      share bound 0.5 +- 0.02: fails on 0/500; max deviation 0.0148 (seed 307)
      ENB bound 2.0 +- 0.05: fails on 0/500; max gap 0.0054 (seed 342)
      twin ENB < 1.1: holds on 500/500; max 1.000001
      retired 1/sum(RC^2): main fixture 1.9983..2.0000 (inside 2.0 +- 0.05 on 500/500); twin pair 2.0000..2.0000 (fails < 1.1 on 500/500)
      covariance-blind ENB: main fixture 1.9991..2.0000 (inside 2.0 +- 0.05 on 500/500); twin pair 1.9999..2.0000 (fails < 1.1 on 500/500)
      corr(A, C) over the seeds: min 0.9947
    same seeds through tools.data.make_market and tools.risk.risk_contributions (<repo>/tools/risk.py)
      share bound 0.5 +- 0.02: fails on 0/500; max deviation 0.0148 (seed 307)
      ENB bound 2.0 +- 0.05: fails on 0/500; max gap 0.0054 (seed 342)
      twin ENB < 1.1: holds on 500/500; max 1.000001

For comparison, N = 2000 over the same seeds exits 1: "share bound 0.5 +- 0.02: fails on 42/500; max deviation 0.0350 (seed 40)"
(the ENB and twin bounds hold there), which is why the fixture moved to 10000 returns (C Task 6 fix round 1).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SHARE_TOL, ENB_TOL, TWIN_MAX = 0.02, 0.05, 1.1   # the bounds of the test, locked: shares 0.5 +- 0.02, ENB 2.0 +- 0.05, twin < 1.1
LAST_DATE = "2025-12-31"                          # the fixture's last date, as in the test
MAIN_W, TWIN_W = np.array([2 / 3, 1 / 3]), np.array([0.5, 0.5])


def draw(seed: int, n: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The fixture's returns in the order the test draws them: a (vol 1 %), b (vol 2 %), then c = a + noise of 0.1 %."""
    rng = np.random.default_rng(seed)
    a, b = rng.normal(0, 0.01, n), rng.normal(0, 0.02, n)
    c = a + rng.normal(0, 0.001, n)
    return a, b, c


def _enb(cov: np.ndarray, w: np.ndarray) -> float:
    """Meucci's effective number of bets: exp(-sum p ln p), p_k = lambda_k (w'e_k)^2 / w'Sw over the principal axes."""
    values, axes = np.linalg.eigh(cov)
    p = values * (axes.T @ w) ** 2
    p = p[p > 0] / p.sum()
    return float(np.exp(-np.sum(p * np.log(p))))


def replica(returns: np.ndarray, w: np.ndarray) -> dict:
    """The specified estimator (ledger section 14) and the two wrong ones the twin pair must catch, on (T x k) returns."""
    cov = np.cov(returns, rowvar=False, ddof=1)
    shares = w * (cov @ w) / (w @ cov @ w)
    return {"shares": shares, "enb": _enb(cov, w), "inv_rc2": float(1.0 / np.sum(shares ** 2)),
            "blind": _enb(np.diag(np.diag(cov)), w)}


def sweep_replica(first: int, count: int, n: int) -> list[dict]:
    rows = []
    for seed in range(first, first + count):
        a, b, c = draw(seed, n)
        main, twin = replica(np.c_[a, b], MAIN_W), replica(np.c_[a, c], TWIN_W)
        rows.append({"seed": seed, "share_dev": float(np.abs(main["shares"] - 0.5).max()), "enb": main["enb"],
                     "inv_rc2": main["inv_rc2"], "blind": main["blind"], "twin": twin["enb"],
                     "twin_inv_rc2": twin["inv_rc2"], "twin_blind": twin["blind"], "corr": float(np.corrcoef(a, c)[0, 1])})
    return rows


def sweep_tools(first: int, count: int, n: int, tree: Path) -> tuple[list[dict], str]:
    """The same fixture through tools.data.make_market and tools.risk.risk_contributions of the checkout `tree`;
    returns the rows and the path of the tools/risk.py that was run."""
    sys.path.insert(0, tree.as_posix())
    try:
        from tools import data, risk
    except ImportError as err:
        raise SystemExit(f"Cannot import tools.data and tools.risk from {tree}: {err}")
    idx = pd.bdate_range(end=LAST_DATE, periods=n + 1)
    day = idx[-1].strftime("%Y-%m-%d")
    rows = []
    for seed in range(first, first + count):
        a, b, c = draw(seed, n)
        px = pd.DataFrame({k: 100 * np.cumprod(np.r_[1, 1 + v]) for k, v in (("A", a), ("B", b), ("C", c))}, index=idx)
        market = data.make_market(px)
        out = risk.risk_contributions({"A": 2 / 3, "B": 1 / 3}, day, market=market)
        twin = risk.risk_contributions({"A": 0.5, "C": 0.5}, day, market=market)
        rows.append({"seed": seed, "share_dev": max(abs(out["shares"]["A"] - 0.5), abs(out["shares"]["B"] - 0.5)),
                     "enb": out["bets"], "twin": twin["bets"]})
    return rows, risk.__file__


def _col(rows: list[dict], key: str) -> np.ndarray:
    return np.array([r[key] for r in rows])


def report(rows: list[dict], label: str) -> bool:
    """Print the tally of one sweep; True when every bound holds on every seed."""
    k, seeds = len(rows), _col(rows, "seed")
    dev, gap, twin = _col(rows, "share_dev"), np.abs(_col(rows, "enb") - 2.0), _col(rows, "twin")
    bad_share, bad_enb, bad_twin = int((dev > SHARE_TOL).sum()), int((gap > ENB_TOL).sum()), int((twin >= TWIN_MAX).sum())
    print(f"{label}")
    print(f"  share bound 0.5 +- {SHARE_TOL}: fails on {bad_share}/{k}; max deviation {dev.max():.4f} (seed {seeds[dev.argmax()]})")
    print(f"  ENB bound 2.0 +- {ENB_TOL}: fails on {bad_enb}/{k}; max gap {gap.max():.4f} (seed {seeds[gap.argmax()]})")
    print(f"  twin ENB < {TWIN_MAX}: holds on {k - bad_twin}/{k}; max {twin.max():.6f}")
    if "inv_rc2" in rows[0]:   # why the twin exists: the main fixture alone cannot tell the wrong definitions apart
        for name, key_main, key_twin in (("retired 1/sum(RC^2)", "inv_rc2", "twin_inv_rc2"),
                                         ("covariance-blind ENB", "blind", "twin_blind")):
            main, pair = _col(rows, key_main), _col(rows, key_twin)
            print(f"  {name}: main fixture {main.min():.4f}..{main.max():.4f} "
                  f"(inside 2.0 +- {ENB_TOL} on {int((np.abs(main - 2.0) <= ENB_TOL).sum())}/{k}); "
                  f"twin pair {pair.min():.4f}..{pair.max():.4f} (fails < {TWIN_MAX} on {int((pair >= TWIN_MAX).sum())}/{k})")
        print(f"  corr(A, C) over the seeds: min {_col(rows, 'corr').min():.4f}")
    return not (bad_share or bad_enb or bad_twin)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Seed sweep behind the bets fixture of tests/test_metrics.py (see the module docstring).")
    ap.add_argument("n", type=int, help="returns per line (the test uses 10000)")
    ap.add_argument("first_seed", type=int, help="first seed of the range (the test uses seed 1)")
    ap.add_argument("count", type=int, help="how many seeds: first_seed .. first_seed + count - 1")
    ap.add_argument("mode", nargs="?", choices=["engine"], help="also run tools/risk.py of SWEEP_TREE (default: this repo)")
    args = ap.parse_args(argv)
    if args.n < 10 or args.count < 1 or args.first_seed < 0:
        ap.error("needs n >= 10, first_seed >= 0 and count >= 1")
    last = args.first_seed + args.count - 1
    ok = report(sweep_replica(args.first_seed, args.count, args.n),
                f"bets fixture: {args.n} returns per line, seeds {args.first_seed}..{last} ({args.count} seeds), replica of the specified estimator")
    if args.mode == "engine":
        rows, path = sweep_tools(args.first_seed, args.count, args.n, Path(os.environ.get("SWEEP_TREE") or ROOT))
        ok = report(rows, f"same seeds through tools.data.make_market and tools.risk.risk_contributions ({path})") and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
