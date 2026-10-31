"""TD-SW008-056: no NEW imports through the short layer paths (``auto_pm.core.x``); the layered path is canonical.

``auto_pm/_module_alias.py`` makes both spellings resolve to one module object, so old code keeps working.  This ratchet stops
the spread: a file may not use more short imports than the baseline records, and a file not in the baseline may use none.
When you convert imports, lower the numbers with ``python tests/infrastructure/test_no_new_short_layer_imports.py --write``.

What counts (TD-SW008-218, user 2026-10-31 "all as recommended"; the baseline was written at today's numbers):
``import`` statements, **string constants that are a dotted short module path** (``"auto_pm.core.x.func"``: monkeypatch targets,
``importlib.import_module("auto_pm.core.x")``, ``mock.patch`` targets), in ``auto_pm/``, ``tests/`` and ``scripts/``.
A string that merely mentions a short path inside a sentence is prose, not a path, and is not counted.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "auto_pm"
BASELINE = Path(__file__).with_name("short_layer_imports_baseline.json")
LAYERS = ("domain", "infrastructure", "application", "ui")
SCANNED = (PACKAGE, ROOT / "tests", ROOT / "scripts")
# A whole string that is one dotted path: "auto_pm.core", "auto_pm.core.x.func" (never a sentence or a file path).
DOTTED_PATH = re.compile(r"auto_pm\.([A-Za-z_]\w*)(?:\.[A-Za-z_]\w*)*")


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


def _logger_name_nodes(tree: ast.AST) -> set[int]:
    """``logging.getLogger("auto_pm.core.x")`` names a logger in the logging hierarchy, not a module: not a path."""

    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and node.args:
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
            if name == "getLogger":
                found.add(id(node.args[0]))
    return found


def count_short_imports(path: Path, names: frozenset[str]) -> int:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return 0
    total = 0
    logger_names = _logger_name_nodes(tree)
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules = [node.module]
            if node.module == "auto_pm":
                modules += [f"auto_pm.{alias.name}" for alias in node.names]
        elif isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and DOTTED_PATH.fullmatch(node.value)
            and id(node) not in logger_names
        ):
            modules = [node.value]  # monkeypatch / mock.patch / importlib.import_module targets
        for module in modules:
            parts = module.split(".")
            if len(parts) >= 2 and parts[0] == "auto_pm" and parts[1] in names:
                total += 1
    return total


def current_counts() -> dict[str, int]:
    names = short_names()
    counts: dict[str, int] = {}
    for base in SCANNED:
        if not base.is_dir():
            continue
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


def test_a_short_module_path_in_a_string_is_counted(tmp_path: Path) -> None:
    """monkeypatch / mock.patch / importlib targets are imports in disguise (TD-SW008-218)."""

    names = frozenset({"core", "change"})
    sample = tmp_path / "s.py"
    sample.write_text(
        "import importlib\n"
        "def f(monkeypatch):\n"
        "    monkeypatch.setattr('auto_pm.core.x.func', None)\n"
        "    importlib.import_module('auto_pm.change.y')\n"
        "    patch(target='auto_pm.core')\n",
        encoding="utf-8",
    )
    assert count_short_imports(sample, names) == 3


def test_prose_logger_names_and_layered_paths_in_strings_are_not_counted(tmp_path: Path) -> None:
    names = frozenset({"core"})
    sample = tmp_path / "s.py"
    sample.write_text(
        "import logging\n"
        "a = 'see auto_pm.core.x for details'\n"  # a sentence
        "b = 'auto_pm/core/x.py'\n"  # a file path
        "c = 'auto_pm.application.core.x.func'\n"  # the layered path
        "d = 'auto_pm.core.'\n"  # not a complete dotted path
        "e = f'auto_pm.core.{a}'\n"  # f-string
        "log = logging.getLogger('auto_pm.core.some_service')\n"  # a logger name
        "other = logging.getLogger('auto_pm.core.other').warning('x')\n",
        encoding="utf-8",
    )
    assert count_short_imports(sample, names) == 0


def test_scripts_are_scanned_too() -> None:
    assert ROOT / "scripts" in SCANNED
    assert any(path.startswith("scripts/") for path in current_counts())


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
