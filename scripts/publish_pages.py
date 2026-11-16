"""Build the static demo and publish it to GitHub Pages (the gh-pages branch, served at https://shmorsi.github.io/poly-datathon-2026/).

    python scripts/publish_pages.py                          # the saved runs in data/demo_runs/ (the final recording)
    python scripts/publish_pages.py --runs /tmp/epi_runs_v1  # interim: raw saved Results <dir>/{robert,mateo,amira,canadian}.json
    python scripts/publish_pages.py --dry-run                # build and check only, push nothing

The site is record_demo.build_static's: the public cut only (weekly rounded portfolio series, no licensed price rows, no ETF
constituents, nothing named fake, no credentials), each run replayed read-only. --runs wraps raw Results as saved runs in a
temporary folder (never in the repository): key = the run's own run_id + 4 hex, saved_at = the file's time, commit = main's
commit at that time, data "REAL" (only real runs that reached Bedrock are accepted, as for any saved run).
Publishing commits the built site on top of the gh-pages branch (a fast-forward; the first publish creates it) with a
.nojekyll file, from a scratch folder, and pushes it. It never force-pushes and never touches the working tree."""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import pipeline  # noqa: E402
import record_demo  # noqa: E402

INVESTORS = ("robert", "mateo", "amira", "canadian")
BRANCH = "gh-pages"


def git(*args, cwd=ROOT, check=True) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and done.returncode:
        raise SystemExit(f"git {' '.join(args[:2])} failed: {done.stderr.strip()[:400]}")
    return done.stdout.strip()


def wrap_runs(src: Path, demo: Path) -> None:
    """Raw saved Results -> saved-run files in `demo` (the static build reads them like data/demo_runs/)."""
    demo.mkdir(parents=True, exist_ok=True)
    for pid in INVESTORS:
        path = src / f"{pid}.json"
        result = json.loads(path.read_text(encoding="utf-8"))
        if result.get("pilot") != pid or not pipeline._really_happened(result):
            raise SystemExit(f"{path} is not {pid}'s real live run with an explanation; nothing was published.")
        run_id = str(result.get("run_id") or "")
        tail = hashlib.sha256(str(result.get("question")).encode()).hexdigest()
        key = (run_id + tail)[:16] if len(run_id) == 12 and all(c in "0123456789abcdef" for c in run_id) else tail[:16]
        when = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        commit = (git("rev-list", "-1", f"--before={when.isoformat()}", "origin/main", check=False)
                  or git("rev-parse", "HEAD"))                     # a clone without origin/main: this checkout's commit
        saved = {"key": key, "saved_at": when.isoformat(timespec="seconds"), "question": result["question"],
                 "as_of": result["as_of"], "commit": commit, "data": "REAL", "result": result}
        (demo / f"{key}.json").write_text(json.dumps(saved), encoding="utf-8")


EXTRAS = (("moves", "moves.json"), ("tests", "tests.json"),      # the ai lane's extra recordings (the picker, the judge's tests)
          ("you", "you_example.json"))                               # R46 "You": the static example (profile-ui)


def _public(obj):
    """A Result anywhere inside an extra file gets the same public cut as a saved run (weekly rounded series, no constituents)."""
    if isinstance(obj, dict):
        if "series" in obj and "verdict" in obj and "pilot" in obj:
            return record_demo.public_result(obj)
        return {k: _public(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_public(v) for v in obj]
    return obj


def add_extras(site: Path) -> list:
    """data/demo_runs/{moves,tests}.json, when present, go to runs/ in the public cut, checked like the runs, and each gets
    <meta name="epicentre-<name>" content="runs/<file>"> in index.html: the page fetches one only when its meta is there, so a
    build without the file never asks for it (no 404)."""
    added = []
    for name, file in EXTRAS:
        src = next((d / file for d in (Path(pipeline.DEMO_DIR), ROOT / "data" / "demo_runs") if (d / file).is_file()), None)
        if src is None:
            continue
        obj = _public(json.loads(src.read_text(encoding="utf-8")))
        leaks = record_demo.find_leaks(obj)
        if leaks:
            raise SystemExit(f"{file} still carries data that is not public ({leaks[0]}); nothing was published.")
        text = record_demo.server.to_json(obj) if hasattr(record_demo, "server") else json.dumps(obj, separators=(",", ":"))
        if record_demo.CREDENTIALS.search(text):
            raise SystemExit(f"{file} looks like it holds credentials; nothing was published.")
        (site / "runs" / file).write_text(text, encoding="utf-8")
        added.append((name, f"runs/{file}"))
    if added:
        page = (site / "index.html").read_text(encoding="utf-8")
        tags = "".join(f'<meta name="epicentre-{n}" content="{f}">\n' for n, f in added)
        at = page.find("</head>")
        (site / "index.html").write_text(page[:at] + tags + page[at:], encoding="utf-8")
    return added


def publish(site: Path, message: str) -> str:
    url = git("remote", "get-url", "origin")
    name, email = git("config", "user.name"), git("config", "user.email")
    with tempfile.TemporaryDirectory(prefix="epi-pages-") as tmp:
        work = Path(tmp)
        git("init", "-q", cwd=work)
        git("remote", "add", "origin", url, cwd=work)
        if git("ls-remote", "--heads", "origin", BRANCH, cwd=work):
            git("fetch", "-q", "--depth", "1", "origin", BRANCH, cwd=work)
            git("checkout", "-q", "-b", BRANCH, "FETCH_HEAD", cwd=work)
            git("rm", "-q", "-r", "--ignore-unmatch", ".", cwd=work)
        else:
            git("checkout", "-q", "--orphan", BRANCH, cwd=work)
        shutil.copytree(site, work, dirs_exist_ok=True)
        (work / ".nojekyll").write_text("", encoding="utf-8")
        git("add", ".", cwd=work)
        if not git("status", "--porcelain", cwd=work):
            return "unchanged"
        git("-c", f"user.name={name}", "-c", f"user.email={email}", "commit", "-q", "-m", message, cwd=work)
        git("push", "-q", "origin", f"HEAD:{BRANCH}", cwd=work)
        return git("rev-parse", "HEAD", cwd=work)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="publish_pages.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--runs", help="a folder of raw saved Results <investor>.json (interim publish)")
    ap.add_argument("--out", default=str(Path(tempfile.gettempdir()) / "epi_pages_site"), help="where the site is built")
    ap.add_argument("--dry-run", action="store_true", help="build and check only")
    args = ap.parse_args(argv)
    head = git("rev-parse", "--short", "HEAD")
    if args.runs:
        demo = Path(tempfile.mkdtemp(prefix="epi-demo-runs-"))
        wrap_runs(Path(args.runs), demo)
        pipeline.DEMO_DIR = demo
    out = Path(args.out)
    if out.exists() and not (out / "runs" / "index.json").is_file():
        raise SystemExit(f"{out} exists and is not an earlier static build: choose another --out.")
    site = record_demo.build_static(out)
    extras = add_extras(site)
    if extras:
        print("extras: " + ", ".join(f for _, f in extras))
    names = sorted(p.relative_to(site).as_posix() for p in site.rglob("*") if p.is_file())
    print(f"built {site}: {len(names)} files, runs: {', '.join(n for n in names if n.startswith('runs/') and n.count('/') == 1)}")
    if args.dry_run:
        return 0
    what = f"saved runs from {args.runs}" if args.runs else "the saved runs in data/demo_runs"
    sha = publish(site, f"[D] Pages: the static demo from main {head} ({what}; public cut only)")
    print(f"published {BRANCH}: {sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
