"""防复发：代码与模板不得再把活派给已隔离的 pm-workflow。

pm-workflow 自 2026-09-09 起隔离（AGENTS.md）。兜底路由、收口方默认值、
脚手架模板都必须指向进门技能 cockpit-entry 或 PM 治理角色。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import auto_pm
from auto_pm.application.core.ai_handoff_service import ENTRY_SKILL, PM_ACTOR

QUARANTINED_SKILL = "pm-workflow"
PACKAGE_ROOT = Path(auto_pm.__file__).resolve().parent
TEMPLATES_ROOT = Path(__file__).resolve().parents[2] / "templates"


def _workspace_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".agents" / "skills.json").is_file():
            return candidate
    raise AssertionError("未找到工作区根目录（.agents/skills.json）")


def test_package_source_has_no_quarantined_skill_literal() -> None:
    offenders: list[str] = []
    for source_path in sorted(PACKAGE_ROOT.rglob("*.py")):
        source = source_path.read_text(encoding="utf-8-sig", errors="replace")
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Constant) and node.value == QUARANTINED_SKILL:
                offenders.append(f"{source_path.relative_to(PACKAGE_ROOT)}:{node.lineno}")
    assert offenders == []


def test_templates_do_not_name_quarantined_skill() -> None:
    offenders = [
        str(path.relative_to(TEMPLATES_ROOT))
        for path in sorted(TEMPLATES_ROOT.rglob("*"))
        if path.is_file() and QUARANTINED_SKILL in path.read_text(encoding="utf-8", errors="replace")
    ]
    assert offenders == []


def test_entry_skill_is_registered_and_pm_workflow_is_not() -> None:
    root = _workspace_root()
    registry = json.loads((root / ".agents" / "skills.json").read_text(encoding="utf-8", errors="replace"))
    registered = {Path(entry["path"]).name for entry in registry["entries"]}

    assert ENTRY_SKILL in registered
    assert QUARANTINED_SKILL not in registered
    assert (root / ".trae" / "skills" / ENTRY_SKILL / "SKILL.md").is_file()


def test_pm_actor_is_not_the_quarantined_skill() -> None:
    assert PM_ACTOR != QUARANTINED_SKILL
