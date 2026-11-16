"""Write the saved runs' AWS request ids into the evidence pack, so one id is the same on the page, in the docs and in
docs/aws_evidence/01-request-ids.txt (AWS juror, Sun 15 Nov: the live capture above it predates the saved runs).

    python scripts/evidence_request_ids.py [--runs DIR] [--file PATH]

Reads the four saved runs the page opens on (data/demo_runs: Robert's default.json, the others' default_<pilot>.json)
and rewrites the block between BEGIN and END (appended once if absent): one line per run (the verdict in the page's
words, the saved run's key, when it was recorded), then one row per AWS call of its trace (step, service, model,
milliseconds, usage, request id). Nothing is typed: every value is the run's own. Run it with scripts/fill_docs.py.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, ROOT.as_posix())

from scripts import fill_docs as fd  # noqa: E402

BEGIN = "# --- The saved runs the page and the docs show (written by scripts/evidence_request_ids.py from data/demo_runs) ---"
END = "# --- end of the saved runs ---"
FILES = (("robert", "default.json"), ("mateo", "default_mateo.json"), ("amira", "default_amira.json"),
         ("canadian", "default_canadian.json"))
SERVICES = ("Amazon Bedrock", "Bedrock Guardrails")


def block(runs_dir) -> str:
    lines = [BEGIN, "# The capture above names verdicts by their internal codes: Incompatible = Outside your limits, Tension =",
             "# Inside, with caveats, Compatible = Inside your limits. These rows use the page's words."]
    for investor, name in FILES:
        saved = json.loads((Path(runs_dir) / name).read_text(encoding="utf-8"))
        r = saved["result"]
        lines.append(f"{investor}: {fd.fmt(r['verdict'], 'verdict')} (saved run {saved.get('key')}, recorded {r.get('recorded_at')})")
        for t in r.get("trace") or []:
            if t.get("service") in SERVICES:
                usage = json.dumps({k: v for k, v in (t.get("usage") or {}).items() if v not in (0, None, [], {}) and k != "cacheDetails"},
                                   separators=(",", ":"), sort_keys=True)          # the non-zero counts only
                lines.append(f"  {t.get('step', ''):<10} {t['service']:<19} {t.get('model') or '-':<36} {t.get('ms')} ms  {usage}"
                             f"  request {t.get('request_id')}")
    return "\n".join(lines + [END]) + "\n"


def rewrite(text: str, new_block: str) -> str:
    """The file with its saved-runs block replaced (or appended after a blank line when it has none)."""
    if BEGIN in text and END in text:
        head, rest = text.split(BEGIN, 1)
        tail = rest.split(END, 1)[1].lstrip("\n")
        return head + new_block + tail
    return text.rstrip("\n") + "\n\n" + new_block


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--runs", type=Path, default=ROOT / "data" / "demo_runs")
    ap.add_argument("--file", type=Path, default=ROOT / "docs" / "aws_evidence" / "01-request-ids.txt")
    args = ap.parse_args(argv)
    args.file.write_text(rewrite(args.file.read_text(encoding="utf-8"), block(args.runs)), encoding="utf-8")
    print(f"evidence_request_ids: {args.file} has the saved runs' request ids")
    return 0


if __name__ == "__main__":
    sys.exit(main())
