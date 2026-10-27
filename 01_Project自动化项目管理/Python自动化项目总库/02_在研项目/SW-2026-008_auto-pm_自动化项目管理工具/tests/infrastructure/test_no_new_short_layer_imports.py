"""TD-SW008-056: no NEW imports through the short layer paths (``auto_pm.core.x``); the layered path is canonical.

``auto_pm/_module_alias.py`` makes both spellings resolve to one module object, so old code keeps working.  This ratchet stops
the spread: a file may not use more short imports than the baseline records, and a file not in the baseline may use none.
When you convert imports, lower the numbers with ``python tests/infrastructure/test_no_new_short_layer_imports.py --write``.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "auto_pm"
BASELINE = Path(__file__).with_name("short_layer_imports_baseline.json")
LAYERS = ("domain", "infrastructure", "application", "ui")


def short_names() -> frozenset[str]:
    """Names importable as ``auto_pm.<name>`` only because the layer directories are on the package path."""

    direct = {p.stem if p.is_file() else p.name for p in PACKAGE.iterdir() if not p.name.startswith(("_", "."))}
    found: set[str] = set()
    for layer in LAYERS:
        for child in (PACKAGE / layer).iterdir():
            if child.name.startswith(("_", ".")) or child.name == "__pycache__":
                continue
            found.add(child.stem if child.is_file() else child.name)
    return frozenset(found - direct)


def count_short_imports(path: Path, names: frozenset[str]) -> int:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return 0
    total = 0
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules = [node.module]
            if node.module == "auto_pm":
                modules += [f"auto_pm.{alias.name}" for alias in node.names]
        elif isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        for module in modules:
            parts = module.split(".")
            if len(parts) >= 2 and parts[0] == "auto_pm" and parts[1] in names:
                total += 1
    return total


def current_counts() -> dict[str, int]:
    names = short_names()
    counts: dict[str, int] = {}
    for base in (PACKAGE, ROOT / "tests"):
        for path in sorted(base.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            n = count_short_imports(path, names)
            if n:
                counts[path.relative_to(ROOT).as_posix()] = n
    return counts


def test_the_short_name_list_is_what_the_layers_provide() -> None:
    names = short_names()
    assert {"core", "change", "db"} <= names
    assert not names & {"application", "domain", "infrastructure", "ui", "contracts", "api"}


def test_a_short_import_is_counted_and_a_layered_one_is_not(tmp_path: Path) -> None:
    names = frozenset({"core"})
    sample = tmp_path / "s.py"
    sample.write_text(
        "from auto_pm.core.x import a\nimport auto_pm.core.y\nfrom auto_pm import core\n"
        "from auto_pm.application.core.x import a\nfrom auto_pm.contracts.z import b\nfrom . import core\n",
        encoding="utf-8",
    )
    assert count_short_imports(sample, names) == 3


def test_no_file_uses_more_short_layer_imports_than_the_baseline() -> None:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    over = {
        path: (count, baseline.get(path, 0))
        for path, count in current_counts().items()
        if count > baseline.get(path, 0)
    }
    assert not over, (
        "新增了短路径导入（auto_pm.core.x 一类），请改用分层路径 auto_pm.application.core.x："
        + "；".join(f"{p} 现 {c} 条，基线 {b} 条" for p, (c, b) in sorted(over.items()))
    )


def test_the_baseline_is_tight_so_converted_imports_cannot_come_back() -> None:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    counts = current_counts()
    slack = {p: (b, counts.get(p, 0)) for p, b in baseline.items() if counts.get(p, 0) < b}
    assert not slack, "基线比实际宽松，请运行 --write 收紧：" + "；".join(f"{p} 基线 {b} 实际 {c}" for p, (b, c) in sorted(slack.items()))


if __name__ == "__main__":
    if "--write" in sys.argv:
        BASELINE.write_text(json.dumps(current_counts(), ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {BASELINE}")
    else:
        print(json.dumps(current_counts(), ensure_ascii=False, indent=1, sort_keys=True))
