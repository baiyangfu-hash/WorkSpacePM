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
    # 门面引用 ui.contracts（命令/DTO/Result 契约包）。要清零须把 ui/contracts 整体搬到中立层，波及界面桥，待用户/PM 裁决。
    ("application/change_facade.py", "ui"),
    ("application/delivery_facade.py", "ui"),
    ("application/spec_facade.py", "ui"),
    ("application/system_facade.py", "ui"),
    ("application/workbench_facade.py", "ui"),
    ("application/workbench_use_cases.py", "ui"),
    # 领域层直接调用 control_root_guard（控制根/路径安全）。要清零须改成注入的端口，DecisionService 有约 80 处构造点，另立卡。
    ("domain/change/decision_service.py", "infrastructure"),
    # CLI 是组装入口，要自己构造 ContinuityStore / 租约钱包 / 进程探针；倾向裁决保留（把规则改为“ui/cli 可引用 infrastructure”），待用户/PM 裁决。
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


def _imported_modules(tree: ast.AST, package: list[str]) -> list[str]:
    """Absolute dotted names imported by tree; package is the importing module's own package (with auto_pm)."""
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[: len(package) - node.level + 1]
                prefix = ".".join([*base, node.module] if node.module else base)
            else:
                prefix = node.module or ""
            modules.append(prefix)
            # from auto_pm import ui imports a layer package through the name list.
            modules.extend(f"{prefix}.{alias.name}" for alias in node.names)
    return modules


def _violations(root: Path = PACKAGE_ROOT) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        layer = relative.parts[0]
        if len(relative.parts) < 2 or layer not in FORBIDDEN_TARGETS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="replace"))
        package = ["auto_pm", *relative.parts[:-1]]
        for module in _imported_modules(tree, package):
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


def test_gate_detects_layer_name_and_relative_imports(tmp_path: Path) -> None:
    (tmp_path / "application").mkdir()
    (tmp_path / "application" / "a.py").write_text("from auto_pm import ui\n", encoding="utf-8")
    (tmp_path / "domain" / "sub").mkdir(parents=True)
    (tmp_path / "domain" / "sub" / "b.py").write_text("from ...infrastructure import store\n", encoding="utf-8")
    assert _violations(tmp_path) == {("application/a.py", "ui"), ("domain/sub/b.py", "infrastructure")}


def test_doc_services_live_in_the_application_layer() -> None:
    """文档同步/核对服务驱动 infrastructure 提取器，属应用层，不能放回领域层（TD-SW008-057）。"""
    assert (PACKAGE_ROOT / "application" / "core" / "doc_services.py").is_file()
    assert not (PACKAGE_ROOT / "domain" / "doc" / "services.py").exists()
