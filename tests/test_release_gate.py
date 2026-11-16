"""The release gate as a test (scripts/release_gate.mjs, README "Release gate"): no screen of the built site reads as advice
(the red gates (README, Limits) red gates 1, 4 and 5; the case's responsible boundaries; design doc rulings R1, R16, R18, R20, R22). It drives one
headless Chrome over every investor, both depths and every dial size, which takes a few minutes and the team's Chrome lock, so it
is opt-in (the full suite runs before every commit): it runs when EPI_GATE_SITE (a static build folder), EPI_GATE_URL (a running
site) or EPI_GATE=1 (the gate's default: publish_pages.py's output folder, else http://127.0.0.1:8899/) is set, and it skips when
node, Chrome or the site is absent. The rules themselves are node-tested on every run (tests/web_gate_test.mjs).

    EPI_GATE_SITE=/tmp/epi_pages_site .venv/bin/python -m pytest -q tests/test_release_gate.py
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "release_gate.mjs"


def _site_args():
    if os.environ.get("EPI_GATE_URL"):
        return ["--url", os.environ["EPI_GATE_URL"]]
    if os.environ.get("EPI_GATE_SITE"):
        return ["--site", os.environ["EPI_GATE_SITE"]]
    return []


def test_release_gate_no_screen_reads_as_advice(tmp_path):
    if not (os.environ.get("EPI_GATE_SITE") or os.environ.get("EPI_GATE_URL") or os.environ.get("EPI_GATE") == "1"):
        pytest.skip("opt-in: set EPI_GATE_SITE, EPI_GATE_URL or EPI_GATE=1 (README, Release gate)")
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    probe = subprocess.run([node, str(GATE), "--probe", *_site_args()], cwd=ROOT, capture_output=True, text=True, timeout=60)
    try:
        found = json.loads(probe.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        pytest.fail(f"the gate's probe did not answer: {probe.stdout}{probe.stderr}")
    if not found.get("chrome"):
        pytest.skip("Chrome is not installed (or set CHROME_PATH)")
    if not found.get("site"):
        pytest.skip(f"no site to check: {found.get('problem') or 'build one with scripts/publish_pages.py --dry-run'}")
    report = tmp_path / "release-gate.md"
    done = subprocess.run([node, str(GATE), *_site_args(), "--report", str(report)],
                          cwd=ROOT, capture_output=True, text=True, timeout=1800)
    text = report.read_text(encoding="utf-8") if report.exists() else done.stdout + done.stderr
    assert done.returncode == 0, text
