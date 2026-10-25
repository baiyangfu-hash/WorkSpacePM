"""TD-SW008-058: machine gate for the import direction between layers.

Allowed direction: ui -> application -> domain -> contracts, infrastructure -> contracts.
Violations that existed when the gate was added are listed in ``KNOWN_VIOLATIONS`` (TD-SW008-057); the list may only
shrink: a new violation fails, and a listed one that has been fixed must be removed from the list.
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "auto_pm"

FORBIDDEN_TARGETS = {
    "contracts": {"domain", "infrastructure", "application", "ui"},
    "domain": {"infrastructure", "application", "ui"},
    "infrastructure": {"application", "ui"},
    "application": {"ui"},
    "ui": {"infrastructure"},
}

KNOWN_VIOLATIONS = {
    ("application/change_facade.py", "ui"),
    ("application/delivery_facade.py", "ui"),
    ("application/spec_facade.py", "ui"),
    ("application/system_facade.py", "ui"),
    ("application/workbench_facade.py", "ui"),
    ("application/workbench_use_cases.py", "ui"),
    ("domain/change/decision_service.py", "infrastructure"),
    ("domain/doc/services.py", "infrastructure"),
    ("ui/cli/__main__.py", "infrastructure"),
    ("ui/cli/continuity.py", "infrastructure"),
    ("ui/cli/continuity_backup.py", "infrastructure"),
    ("ui/cli/git_hook.py", "infrastructure"),
    ("ui/cli/plc/__init__.py", "infrastructure"),
    ("ui/cli/pm.py", "infrastructure"),
    ("ui/cli/pm_closure.py", "infrastructure"),
    ("ui/cli/pm_handoff.py", "infrastructure"),
    ("ui/cli/pm_switch.py", "infrastructure"),
}


def _imported_modules(tree: ast.AST) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.append(node.module)
    return modules


def _violations(root: Path = PACKAGE_ROOT) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        layer = relative.parts[0]
        if len(relative.parts) < 2 or layer not in FORBIDDEN_TARGETS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="replace"))
        for module in _imported_modules(tree):
            parts = module.split(".")
            if parts[0] == "auto_pm" and len(parts) > 1 and parts[1] in FORBIDDEN_TARGETS[layer]:
                found.add((relative.as_posix(), parts[1]))
    return found


def test_no_new_layer_violations() -> None:
    new = _violations() - KNOWN_VIOLATIONS
    assert not new, f"新增越层引用（TD-SW008-058）：{sorted(new)}"


def test_known_violations_are_still_present() -> None:
    fixed = KNOWN_VIOLATIONS - _violations()
    assert not fixed, f"这些越层引用已清除，请从 KNOWN_VIOLATIONS 删除：{sorted(fixed)}"


def test_gate_detects_a_violation(tmp_path: Path) -> None:
    (tmp_path / "domain").mkdir()
    bad = "import auto_pm.infrastructure.x\nimport auto_pm.contracts.y\n"
    (tmp_path / "domain" / "bad.py").write_text(bad, encoding="utf-8")
    (tmp_path / "ui").mkdir()
    (tmp_path / "ui" / "ok.py").write_text("from auto_pm.application import z\n", encoding="utf-8")
    assert _violations(tmp_path) == {("domain/bad.py", "infrastructure")}
