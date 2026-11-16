"""Write the web tests' fixtures (ruling R17: node tests pass on a fresh clone): tests/fixtures/web/<investor>.json, the public cut
of saved real Results, through the same function the static build publishes with (record_demo.public_result: weekly rounded
series, no licensed price rows, no ETF constituents, no evidence-drawer rows), checked for leaks (record_demo.find_leaks).

    python scripts/web_fixtures.py /tmp/epi_runs_v1      # reads <dir>/{robert,mateo,amira,canadian}.json

The fixtures are frozen on purpose: lanes pin values on them, so refresh them only together with the tests that pin them."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import record_demo  # noqa: E402
import server  # noqa: E402

INVESTORS = ("robert", "mateo", "amira", "canadian")
OUT = ROOT / "tests" / "fixtures" / "web"


def cut(result: dict) -> str:
    public = record_demo.public_result(result)
    leaks = record_demo.find_leaks(public)
    if leaks:
        raise SystemExit(f"the public cut still carries data that is not public: {leaks[0]}")
    text = server.to_json(public)
    if record_demo.CREDENTIALS.search(text):
        raise SystemExit("a fixture looks like it holds credentials; nothing was written")
    return text


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(__doc__)
        return 2
    src = Path(args[0])
    texts = {}
    for name in INVESTORS:
        result = json.loads((src / f"{name}.json").read_text(encoding="utf-8"))
        if result.get("pilot") != name or result.get("status") == "error":
            raise SystemExit(f"{name}.json is not {name}'s run")
        texts[name] = cut(result)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, text in texts.items():
        (OUT / f"{name}.json").write_text(text, encoding="utf-8")
        print(f"{name}: {len(text) // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
