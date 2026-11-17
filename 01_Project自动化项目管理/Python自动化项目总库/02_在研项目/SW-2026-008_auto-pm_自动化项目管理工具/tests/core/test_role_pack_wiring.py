"""角色包接线（CHG-SCPT-2026-711）：``roles/`` 下每个有 ``role.json`` 的包都登记到各家 AI 读的入口，进门流程按卡类型提示它。

``main.py role check`` 只看包本身合不合格，看不出包有没有接上：2026-11-17 前五个包全过检查，却只有 PLC 和 Python 两个
登记进了 ``.agents/skills.json``、``AGENTS.md``“去哪查”和 Cursor 规则，另外三个没有 AI 会加载。本测试钉住每一处登记：

* ``.agents/skills.json`` 有 ``../roles/<角色号>``；
* ``AGENTS.md`` 写着 ``roles/<角色号>/SKILL.md``（“去哪查”表）；
* ``.agent/rules/project-rule.md`` 写着 ``roles/<角色号>/SKILL.md``；
* ``.cursor/rules/<角色号>.mdc`` 存在，并指向 ``roles/<角色号>/SKILL.md``；
* ``scripts/pm_flows.py`` 的 ``ROLE_CARD_TYPES`` 有这个包（进门按卡类型提示它），提示里的路径都存在。

撤掉任一处登记，``wiring_gaps`` 都要点名（下面的变异测试逐处撤一次）。
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.external_reads  # D-200: reads real files outside the project

PROJECT = Path(__file__).resolve().parents[2]
WORKSPACE = PROJECT.parents[3]
FLOWS_SCRIPT = PROJECT / "scripts" / "pm_flows.py"
WIRED_FILES = ("AGENTS.md", ".agents/skills.json", ".agent/rules/project-rule.md")


def _load_flows() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pm_flows_wiring_under_test", FLOWS_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def flows() -> ModuleType:
    return _load_flows()


def role_ids(root: Path) -> list[str]:
    """``roles/`` 下有 ``role.json`` 的包（``shared`` 是共用参考，没有 role.json，不算包）。"""
    return sorted(path.parent.name for path in (root / "roles").glob("*/role.json"))


def wiring_gaps(root: Path, card_types: Mapping[str, str], packs_shown: list[str]) -> list[str]:
    """每个包缺了哪处登记；全接上返回空。``packs_shown`` 是进门提示列出的 SKILL.md 路径。"""
    gaps: list[str] = []
    registry = json.loads((root / ".agents" / "skills.json").read_text(encoding="utf-8"))
    registered = {str(entry.get("path", "")) for entry in registry.get("entries", [])}
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    agent_rules = (root / ".agent" / "rules" / "project-rule.md").read_text(encoding="utf-8")
    for role in role_ids(root):
        skill = f"roles/{role}/SKILL.md"
        if f"../roles/{role}" not in registered:
            gaps.append(f"{role}：.agents/skills.json 没登记 ../roles/{role}")
        if f"`{skill}`" not in agents:
            gaps.append(f"{role}：AGENTS.md“去哪查”没写 `{skill}`")
        if f"`{skill}`" not in agent_rules:
            gaps.append(f"{role}：.agent/rules/project-rule.md 没写 `{skill}`")
        cursor = root / ".cursor" / "rules" / f"{role}.mdc"
        if not cursor.is_file():
            gaps.append(f"{role}：缺 .cursor/rules/{role}.mdc")
        elif f"`{skill}`" not in cursor.read_text(encoding="utf-8"):
            gaps.append(f"{role}：.cursor/rules/{role}.mdc 没指向 `{skill}`")
        if role not in card_types:
            gaps.append(f"{role}：pm_flows.py 的 ROLE_CARD_TYPES 没有这个包，进门不会提示")
        if skill not in packs_shown:
            gaps.append(f"{role}：进门提示没列出 {skill}")
    for shown_path in packs_shown:
        if not (root / shown_path).is_file():
            gaps.append(f"进门提示里的 {shown_path} 不存在")
    for role in card_types:
        if not (root / "roles" / role / "role.json").is_file():
            gaps.append(f"ROLE_CARD_TYPES 里的 {role} 在 roles/ 下没有包")
    return gaps


def _shown(flows: ModuleType, root: Path) -> list[str]:
    return [str(pack["skill"]) for pack in flows.role_packs(root)]


def test_the_workspace_has_the_five_packs() -> None:
    assert role_ids(WORKSPACE) == [
        "fullstack-engineer",
        "plc-electrical-engineer",
        "product-pm",
        "test-engineer",
        "ui-designer",
    ]


def test_every_role_pack_is_wired_in(flows: ModuleType) -> None:
    assert wiring_gaps(WORKSPACE, flows.ROLE_CARD_TYPES, _shown(flows, WORKSPACE)) == []


def test_entry_lists_every_pack_with_its_card_type(flows: ModuleType) -> None:
    lines: list[str] = []
    flows._print_role_hints(flows.role_packs(WORKSPACE), [], lines.append)
    text = "\n".join(lines)
    for role in role_ids(WORKSPACE):
        assert f"{flows.ROLE_CARD_TYPES[role]}：roles/{role}/SKILL.md" in text


@pytest.mark.parametrize(
    ("path", "role", "expected"),
    [
        ("0100_PLC自动化/DJ-2026-005/03_程序/FB_Station.scl", "plc-electrical-engineer", True),
        ("SW8/scripts/pm_flows.py", "fullstack-engineer", True),
        ("reviews/2026-11-17_PR862_audit.md", "test-engineer", True),
        ("0100_PLC自动化/DJ-2026-005/05_原型/index.html", "ui-designer", True),
        ("0100_PLC自动化/DJ-2026-005/README.md", "plc-electrical-engineer", False),
    ],
)
def test_card_paths_map_to_the_real_packs(
    flows: ModuleType, path: str, role: str, expected: bool
) -> None:
    assert (role in flows.packs_for_paths(flows.role_packs(WORKSPACE), [path])) is expected


def _copy_wiring(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    shutil.copytree(WORKSPACE / "roles", root / "roles")
    shutil.copytree(WORKSPACE / ".cursor" / "rules", root / ".cursor" / "rules")
    for relative in WIRED_FILES:
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(WORKSPACE / relative, root / relative)
    return root


def _drop_from_registry(root: Path, role: str) -> None:
    path = root / ".agents" / "skills.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["entries"] = [entry for entry in data["entries"] if entry["path"] != f"../roles/{role}"]
    path.write_text(json.dumps(data), encoding="utf-8")


def _drop_text(relative: str) -> Callable[[Path, str], None]:
    def drop(root: Path, role: str) -> None:
        path = root / relative
        path.write_text(
            path.read_text(encoding="utf-8").replace(f"`roles/{role}/SKILL.md`", "`roles/`"),
            encoding="utf-8",
        )

    return drop


def _drop_cursor_rule(root: Path, role: str) -> None:
    (root / ".cursor" / "rules" / f"{role}.mdc").unlink()


def _drop_pack_files(root: Path, role: str) -> None:
    (root / "roles" / role / "SKILL.md").unlink()


MUTANTS: dict[str, Callable[[Path, str], None]] = {
    "skills.json": _drop_from_registry,
    "AGENTS.md": _drop_text("AGENTS.md"),
    ".agent/rules": _drop_text(".agent/rules/project-rule.md"),
    ".cursor/rules": _drop_cursor_rule,
    "SKILL.md": _drop_pack_files,
}


@pytest.mark.parametrize("role", ["product-pm", "test-engineer", "ui-designer"])
@pytest.mark.parametrize("where", sorted(MUTANTS))
def test_dropping_any_registration_turns_red(
    flows: ModuleType, tmp_path: Path, where: str, role: str
) -> None:
    root = _copy_wiring(tmp_path)
    assert wiring_gaps(root, flows.ROLE_CARD_TYPES, _shown(flows, root)) == [], "copy starts green"

    MUTANTS[where](root, role)

    gaps = wiring_gaps(root, flows.ROLE_CARD_TYPES, _shown(flows, root))
    assert any(gap.startswith(f"{role}：") for gap in gaps), gaps


@pytest.mark.parametrize("role", ["product-pm", "test-engineer", "ui-designer"])
def test_dropping_a_card_type_from_entry_turns_red(
    flows: ModuleType, tmp_path: Path, role: str
) -> None:
    root = _copy_wiring(tmp_path)
    card_types = {key: value for key, value in flows.ROLE_CARD_TYPES.items() if key != role}

    gaps = wiring_gaps(root, card_types, _shown(flows, root))
    assert f"{role}：pm_flows.py 的 ROLE_CARD_TYPES 没有这个包，进门不会提示" in gaps


def test_a_card_type_without_a_pack_turns_red(flows: ModuleType, tmp_path: Path) -> None:
    root = _copy_wiring(tmp_path)
    card_types = {**flows.ROLE_CARD_TYPES, "ghost-role": "幽灵卡"}

    assert "ROLE_CARD_TYPES 里的 ghost-role 在 roles/ 下没有包" in wiring_gaps(
        root, card_types, _shown(flows, root)
    )
