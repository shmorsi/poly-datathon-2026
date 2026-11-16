"""Record the test tally the Proof block shows (plan P Task P9).

    .venv/bin/python scripts/record_tally.py [--out PATH]      # default: data/demo_runs/test_tally.json

Runs the whole suite once (`python -m pytest -q -p no:cacheprovider --junitxml <tmp file>`, from the repo root), builds
the tally with `proofs.tally_from_junit` (the counts, the seconds, the commit of the code and today's UTC date, and
whether the three "scramble the future" look-ahead tests passed) and writes it (`indent=1, sort_keys=True`) even when
a test fails: an honest tally. Prints one line and exits 1 if anything failed or errored, else 0. Run it before
recording the demo runs. A tally says how many tests ran green on that commit, not that the code is right.
"""
import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pipeline  # noqa: E402
import proofs  # noqa: E402


def git_commit():
    """The short commit of this code (git HEAD; without .git, EPICENTRE_COMMIT or the `.commit` a ZIP download
    carries, as `pipeline._commit` reads them), or None when none of them names one."""
    full = pipeline._commit()
    return None if full == "unknown" else full[:7]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run the test suite once and write the tally the Proof block shows.")
    parser.add_argument("--out", type=Path, default=proofs.TEST_TALLY_JSON, help="where to write the tally JSON")
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory() as tmp:
        junit = Path(tmp) / "junit.xml"
        cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--junitxml", str(junit)]
        subprocess.run(cmd, cwd=ROOT)
        if not junit.exists():
            print(f"pytest wrote no report ({junit.name}): no tally written", file=sys.stderr)
            return 1
        tally = proofs.tally_from_junit(junit.read_text(encoding="utf-8"), commit=git_commit(),
                                        date=datetime.now(timezone.utc).date().isoformat())
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(tally, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{tally['passed']} passed, {tally['failed']} failed, {tally['skipped']} skipped "
          f"(code {tally['commit']}) -> {out}")
    return 1 if tally["failed"] or tally["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
