"""docs/audit_independent.md and docs/technical.md say the independent re-implementation shares no code with the engine:
no script in scripts/audit_independent/ imports a module of this repository (its own files and the standard library,
numpy and pandas only). Static, so it runs on a fresh clone; running the audit itself needs the licensed data."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "scripts" / "audit_independent"


def _imports(path: Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    names |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module and not n.level}
    return names


def test_the_independent_audit_imports_no_module_of_the_repository():
    own = {p.stem for p in AUDIT.glob("*.py")}
    repo = {p.stem for p in ROOT.glob("*.py")} | {p.name for p in ROOT.iterdir() if p.is_dir() and not p.name.startswith(".")}
    scripts = sorted(AUDIT.glob("*.py"))
    assert len(scripts) >= 10 and (AUDIT / "README.md").is_file()
    for f in scripts:
        foreign = (_imports(f) - own) & repo
        assert not foreign, (f.name, sorted(foreign))
        assert "__import__" not in f.read_text(encoding="utf-8") and "importlib" not in _imports(f), f.name
