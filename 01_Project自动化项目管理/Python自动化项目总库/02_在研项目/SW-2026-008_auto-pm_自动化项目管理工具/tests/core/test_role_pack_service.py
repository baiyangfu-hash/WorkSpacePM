"""Role pack check (role-pack card 1): the shipped packs pass, and each rule catches its own breakage."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from auto_pm.application.core.role_pack_service import (
    FAIL,
    UNVERIFIED,
    RolePackService,
    split_front_matter,
)

pytestmark = pytest.mark.external_reads  # D-200: reads real files outside the project

OLD_BODY = "# Old\n\n先完整读取 `../shared/refs/skill_coordination.md`。\n\n## 步骤\n\n- 一\n- 这一行足够长，有二十个字以上，抄进角色包就算抄了正本的内容\n"
# The pack names the one master copy of the procedure and does not repeat it.
PACK_BODY = "# Demo\n\n先完整读取 `../shared/refs/skill_coordination.md`。\n\n做法只写在 `.trae/skills/demo-skill/SKILL.md` 的“步骤”一节，照它做。\n"
CONFIG = {
    "schema_version": 1,
    "id": "engineer-demo",
    "title": "demo",
    "kind": "engineer",
    "legacy_names": ["demo-skill"],
    "required_specs": ["DEV-300"],
    "allowed_commands": [],
    "gates": [],
    "receipt_fields": [],
    "owned_paths_patterns": [],
    "enforcement": {},
    "legacy": {"mode": "pointer", "source": ".trae/skills/demo-skill/SKILL.md", "from_heading": "## 步骤"},
}


def _skill(name: str, body: str = PACK_BODY) -> str:
    return f'---\nname: {name}\ndescription: "demo"\n---\n{body}'


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    """A tiny workspace: roles dir with one good pack, the old skill it replaces and a spec registry."""
    workspace = tmp_path / "ws"
    roles = tmp_path / "roles"
    (roles / "shared" / "refs").mkdir(parents=True)
    (roles / "shared" / "refs" / "skill_coordination.md").write_text("共享契约\n", encoding="utf-8")
    pack = roles / "engineer-demo"
    (pack / "refs").mkdir(parents=True)
    (pack / "SKILL.md").write_text(_skill("engineer-demo"), encoding="utf-8")
    (pack / "role.json").write_text(json.dumps(CONFIG, ensure_ascii=False), encoding="utf-8")
    (pack / "refs" / "note.md").write_text("笔记\n", encoding="utf-8")
    old = workspace / ".trae" / "skills" / "demo-skill"
    (old / "refs").mkdir(parents=True)
    (old / "SKILL.md").write_text(_skill("demo-skill", OLD_BODY), encoding="utf-8")
    (old / "refs" / "note.md").write_text("笔记\n", encoding="utf-8")
    registry = workspace / "00_Obsidian_Base全局规范文件仓库"
    registry.mkdir(parents=True)
    (registry / "spec_registry.json").write_text(json.dumps({"specs": {"DEV-300": {}}}), encoding="utf-8")
    return roles, workspace


def _codes(roles: Path, workspace: Path | None) -> set[tuple[str, str]]:
    result = RolePackService(roles, workspace).check()
    return {(item.code, item.level) for item in result.findings}


def _edit_config(roles: Path, change: Callable[[dict[str, Any]], None]) -> None:
    path = roles / "engineer-demo" / "role.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_good_pack_passes(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    result = RolePackService(roles, workspace).check()
    assert result.ok and result.findings == [] and result.roles == ["engineer-demo"]


def test_shared_directory_is_not_a_role(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    assert [item.name for item in RolePackService(roles, workspace).role_dirs()] == ["engineer-demo"]


def test_missing_files_are_reported(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    (roles / "engineer-demo" / "role.json").unlink()
    assert _codes(roles, workspace) == {("RP-001", FAIL)}


def test_broken_json_and_missing_key(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    _edit_config(roles, lambda data: data.pop("gates"))
    assert ("RP-002", FAIL) in _codes(roles, workspace)
    (roles / "engineer-demo" / "role.json").write_text("{not json", encoding="utf-8")
    assert _codes(roles, workspace) == {("RP-002", FAIL)}


def test_id_must_match_directory_and_avoid_colon(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    _edit_config(roles, lambda data: data.update(id="engineer:demo"))
    assert ("RP-003", FAIL) in _codes(roles, workspace)
    (roles / "engineer-demo").rename(roles / "engineer_demo")
    messages = [item.message for item in RolePackService(roles, workspace).check().findings if item.code == "RP-003"]
    assert any("冒号" in message for message in messages)


def test_front_matter_name_must_match(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    (roles / "engineer-demo" / "SKILL.md").write_text(_skill("demo-skill"), encoding="utf-8")
    assert ("RP-004", FAIL) in _codes(roles, workspace)


def test_legacy_name_claimed_twice(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    twin = roles / "engineer-twin"
    twin.mkdir()
    (twin / "SKILL.md").write_text(_skill("engineer-twin"), encoding="utf-8")
    config = dict(CONFIG, id="engineer-twin")
    config.pop("legacy")
    (twin / "role.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    assert ("RP-005", FAIL) in _codes(roles, workspace)


def test_unknown_spec_fails_and_missing_registry_is_unverified(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    _edit_config(roles, lambda data: data.update(required_specs=["DEV-300", "NOPE-999"]))
    assert ("RP-006", FAIL) in _codes(roles, workspace)
    assert _codes(roles, None) == {("RP-006", UNVERIFIED), ("RP-008", UNVERIFIED)}
    assert RolePackService(roles, None).check().ok


def test_dead_pointer_is_reported(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    (roles / "engineer-demo" / "SKILL.md").write_text(_skill("engineer-demo", PACK_BODY + "\n见 `refs/gone.md`\n"), encoding="utf-8")
    assert ("RP-007", FAIL) in _codes(roles, workspace)


def test_pointer_may_not_leave_roles_dir(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    (tmp_path / "outside.md").write_text("x", encoding="utf-8")
    (roles / "engineer-demo" / "SKILL.md").write_text(_skill("engineer-demo", PACK_BODY + "\n见 `../../outside.md`\n"), encoding="utf-8")
    assert ("RP-007", FAIL) in _codes(roles, workspace)


def test_retired_flag_skips_equivalence(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    (roles / "engineer-demo" / "SKILL.md").write_text(_skill("engineer-demo", OLD_BODY + "- 新增\n"), encoding="utf-8")
    for path in sorted((workspace / ".trae" / "skills" / "demo-skill").rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    _edit_config(roles, lambda data: data["legacy"].update(retired=True))
    assert _codes(roles, workspace) == set()


def test_wrong_source_path_is_a_failure_not_a_silent_skip(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    _edit_config(roles, lambda data: data["legacy"].update(source=".trae/skills/demo-skil/SKILL.md"))
    assert ("RP-008", FAIL) in _codes(roles, workspace)
    _edit_config(roles, lambda data: data["legacy"].pop("source"))
    assert ("RP-008", FAIL) in _codes(roles, workspace)


def test_unknown_mode_or_shape_is_a_failure(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    _edit_config(roles, lambda data: data["legacy"].update(mode="body-equl"))
    assert ("RP-008", FAIL) in _codes(roles, workspace)
    _edit_config(roles, lambda data: data.update(legacy="oops"))
    assert ("RP-008", FAIL) in _codes(roles, workspace)


def test_no_old_skills_directory_or_no_workspace_is_unverified_not_passed_silently(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    assert ("RP-008", UNVERIFIED) in _codes(roles, None)
    for path in sorted((workspace / ".trae").rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    assert ("RP-008", UNVERIFIED) in _codes(roles, workspace)


def _messages(roles: Path, workspace: Path | None) -> list[str]:
    return [item.message for item in RolePackService(roles, workspace).check().findings if item.code == "RP-008"]


def test_editing_the_master_needs_no_second_edit(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    master = workspace / ".trae" / "skills" / "demo-skill" / "SKILL.md"
    master.write_text(_skill("demo-skill", OLD_BODY + "- 正本新加的一句规矩，角色包里一个字都不用跟着改\n"), encoding="utf-8")
    assert _codes(roles, workspace) == set()


def test_a_copy_of_the_master_section_is_refused(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    pack = roles / "engineer-demo" / "SKILL.md"
    pack.write_text(_skill("engineer-demo", PACK_BODY + "\n## 步骤\n"), encoding="utf-8")
    assert any("抄了正本" in message for message in _messages(roles, workspace))
    pack.write_text(_skill("engineer-demo", PACK_BODY + "\n- 这一行足够长，有二十个字以上，抄进角色包就算抄了正本的内容\n"), encoding="utf-8")
    assert any("抄了正本" in message for message in _messages(roles, workspace))
    # A short line shared by chance (a bullet like "- 一") is not a copy.
    pack.write_text(_skill("engineer-demo", PACK_BODY + "\n- 一\n"), encoding="utf-8")
    assert _codes(roles, workspace) == set()


def test_the_pack_must_name_its_master(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    (roles / "engineer-demo" / "SKILL.md").write_text(_skill("engineer-demo", "# Demo\n\n做法见别处。\n"), encoding="utf-8")
    assert any("没有写出指路的正本" in message for message in _messages(roles, workspace))


def test_a_heading_gone_from_the_master_is_a_failure(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    _edit_config(roles, lambda data: data["legacy"].update(from_heading="## 没有的标题"))
    assert any("找不到章节" in message for message in _messages(roles, workspace))
    _edit_config(roles, lambda data: data["legacy"].pop("from_heading"))
    assert ("RP-008", FAIL) in _codes(roles, workspace)


@pytest.mark.parametrize("mode", ["body-equal", "section-contained"])
def test_the_copy_modes_are_refused(tmp_path: Path, mode: str) -> None:
    """Keeping a second copy in the pack and comparing it drifted after 682; the modes must not come back."""
    roles, workspace = _workspace(tmp_path)
    _edit_config(roles, lambda data: data["legacy"].update(mode=mode))
    assert any("已停用" in message for message in _messages(roles, workspace))


def _second_pack(roles: Path, body: str) -> None:
    twin = roles / "engineer-twin"
    twin.mkdir()
    (twin / "SKILL.md").write_text(_skill("engineer-twin", body), encoding="utf-8")
    config = dict(CONFIG, id="engineer-twin", legacy_names=[])
    config.pop("legacy")
    (twin / "role.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")


SHARED_LINE = "- 两个岗位都要守的这一句规矩足够长，只能写在共用页里\n"


def test_a_line_copied_into_two_packs_is_refused(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    (roles / "engineer-demo" / "SKILL.md").write_text(_skill("engineer-demo", PACK_BODY + SHARED_LINE), encoding="utf-8")
    _second_pack(roles, "# Twin\n\n" + SHARED_LINE)
    assert _codes(roles, workspace) == {("RP-010", FAIL)}


def test_a_pack_repeating_a_shared_ref_line_is_refused(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    (roles / "shared" / "refs" / "common.md").write_text("# 共用\n\n" + SHARED_LINE, encoding="utf-8")
    (roles / "engineer-demo" / "SKILL.md").write_text(_skill("engineer-demo", PACK_BODY + SHARED_LINE), encoding="utf-8")
    assert _codes(roles, workspace) == {("RP-010", FAIL)}


MASTER_LINE = "- 进门技能里的这一句规矩足够长，只能留在正本里，岗位说明只指路\n"


def test_a_line_of_a_packs_master_copied_into_a_retired_pack_is_refused(tmp_path: Path) -> None:
    """The master one pack points at (its legacy.source) may not be repeated by any pack, retired ones included (audit 甲-A)."""
    roles, workspace = _workspace(tmp_path)
    master = workspace / ".trae" / "skills" / "demo-skill" / "SKILL.md"
    master.write_text(_skill("demo-skill", OLD_BODY + MASTER_LINE), encoding="utf-8")
    _second_pack(roles, "# Twin\n\n" + MASTER_LINE)
    messages = [item.message for item in RolePackService(roles, workspace).check().findings if item.code == "RP-010"]
    assert messages and ".trae/skills/demo-skill/SKILL.md" in messages[0]


@pytest.mark.parametrize("master_name", ["AGENTS.md", "CLAUDE.md"])
def test_a_line_of_agents_or_claude_md_copied_into_a_pack_is_refused(tmp_path: Path, master_name: str) -> None:
    roles, workspace = _workspace(tmp_path)
    line = f"{master_name} 里的这一句规矩足够长，岗位说明不许再抄一遍，只能指过去\n"
    (workspace / master_name).write_text(f"# 入口\n\n{line}", encoding="utf-8")
    assert _codes(roles, workspace) == set()
    (roles / "engineer-demo" / "SKILL.md").write_text(_skill("engineer-demo", PACK_BODY + line), encoding="utf-8")
    assert _codes(roles, workspace) == {("RP-010", FAIL)}


def test_lines_shared_only_among_master_files_are_not_a_pack_finding(tmp_path: Path) -> None:
    """AGENTS.md repeating a line of the entry skill is not a role pack's copy; RP-010 only judges the packs."""
    roles, workspace = _workspace(tmp_path)
    master = workspace / ".trae" / "skills" / "demo-skill" / "SKILL.md"
    master.write_text(_skill("demo-skill", OLD_BODY + MASTER_LINE), encoding="utf-8")
    (workspace / "AGENTS.md").write_text("# 入口\n\n" + MASTER_LINE, encoding="utf-8")
    assert _codes(roles, workspace) == set()


def test_shared_pointers_headings_and_code_blocks_are_not_copies(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    (roles / "shared" / "refs" / "common.md").write_text("# 共用\n\n" + SHARED_LINE, encoding="utf-8")
    common = "## 启动门禁\n\n照 `../shared/refs/common.md` 的“开工门禁”一节做，这一句每个岗位都可以写\n\n```\n& \"<ws>\\\\main.py\" doc check --and-a-long-enough-tail\n```\n"
    (roles / "engineer-demo" / "SKILL.md").write_text(_skill("engineer-demo", PACK_BODY + common), encoding="utf-8")
    _second_pack(roles, "# Twin\n\n" + common)
    assert _codes(roles, workspace) == set()


def test_front_matter_split_handles_crlf_and_none() -> None:
    meta, body = split_front_matter('---\r\nname: a\r\ndescription: "b"\r\n---\r\nbody\r\n')
    assert meta == {"name": "a", "description": "b"} and body == "body\n"
    assert split_front_matter("no front matter") == ({}, "no front matter")


def test_empty_or_missing_library_does_not_pass(tmp_path: Path) -> None:
    for service in (RolePackService(workspace_root=tmp_path), RolePackService(None, None)):
        result = service.check()
        assert not result.ok and result.roles == []
        assert [(item.code, item.level) for item in result.findings] == [("RP-001", FAIL)]


def _real_workspace() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        if (parent / ".trae" / "skills").is_dir() and (parent / "00_Obsidian_Base全局规范文件仓库").is_dir():
            return parent
    return None


def _roles_dir() -> Path:
    workspace = _real_workspace()
    assert workspace is not None, "找不到完整工作区"
    return workspace / "roles"


def test_shipped_packs_pass_and_match_old_skills() -> None:
    workspace = _real_workspace()
    assert workspace is not None, "测试必须在完整工作区里跑：找不到 .trae/skills 与规范库"
    result = RolePackService(workspace_root=workspace).check()
    assert result.roles == ["fullstack-engineer", "plc-electrical-engineer", "product-pm", "test-engineer", "ui-designer"]
    # Nothing may stay unverified: the registry and the old skills were both read.
    assert result.findings == [], [vars(item) for item in result.findings]


def test_no_shipped_pack_keeps_a_copy_of_its_master() -> None:
    """Each pack either has nothing to point at (retired) or points at the one master copy; none keeps a copy (682)."""
    for config_path in sorted(_roles_dir().glob("*/role.json")):
        legacy = json.loads(config_path.read_text(encoding="utf-8")).get("legacy") or {}
        assert legacy.get("retired") is True or legacy.get("mode") == "pointer", (config_path.parent.name, legacy)


def test_editing_the_real_cockpit_entry_needs_no_second_edit(tmp_path: Path) -> None:
    """A copy of the real roles/ and cockpit-entry: a new rule in the master section leaves the role check clean."""
    workspace = _real_workspace()
    assert workspace is not None, "找不到完整工作区"
    copy = tmp_path / "ws"
    shutil.copytree(workspace / "roles", copy / "roles")
    entry = Path(".trae") / "skills" / "cockpit-entry" / "SKILL.md"
    registry = Path("00_Obsidian_Base全局规范文件仓库") / "spec_registry.json"
    for relative in (entry, registry):
        (copy / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(workspace / relative, copy / relative)
    with (copy / entry).open("a", encoding="utf-8") as handle:
        handle.write("\n- 正本新加的一句规矩：只改这里，岗位说明不用跟着改。\n")
    result = RolePackService(workspace_root=copy).check()
    assert result.findings == [], [vars(item) for item in result.findings]
    assert "正本新加的一句规矩" not in (copy / "roles" / "product-pm" / "SKILL.md").read_text(encoding="utf-8")


RED_LINE_HEADING = "## 红线（AUD-001）"
RED_LINE_PHRASES = (
    "做和审必须是不同会话",
    "Claude-Session",
    "审计者不往被审分支推提交",
    "不推 `main`",
    "不合并",
    "不改被审 PR 的标题和描述",
)


def missing_red_lines(skill_text: str) -> list[str]:
    """Red lines the body of a test-engineer SKILL.md lacks; the front matter does not count."""
    _, body = split_front_matter(skill_text)
    start = body.find(RED_LINE_HEADING)
    if start == -1:
        return [RED_LINE_HEADING]
    end = body.find("\n## ", start + len(RED_LINE_HEADING))
    section = body[start : end if end != -1 else len(body)]
    return [phrase for phrase in RED_LINE_PHRASES if phrase not in section]


def test_test_engineer_keeps_the_audit_red_lines() -> None:
    """AUD-001 must stay written into the body of the pack, not only into the front matter description."""
    pack = _roles_dir() / "test-engineer"
    text = (pack / "SKILL.md").read_text(encoding="utf-8")
    assert missing_red_lines(text) == []
    assert "放行判定:" in text
    config = json.loads((pack / "role.json").read_text(encoding="utf-8"))
    assert config["owned_paths_patterns"] == ["reviews/**"]


def test_red_line_check_catches_each_mutation() -> None:
    """The check itself must go red when a red line is removed from the body (audit 322 mutations)."""
    text = (_roles_dir() / "test-engineer" / "SKILL.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert RED_LINE_HEADING in text
    # The whole section removed: the front matter still repeats two phrases, which must not save it.
    start = text.index(RED_LINE_HEADING)
    end = text.index("\n## ", start + 1)
    assert missing_red_lines(text[:start] + text[end + 1 :]) == [RED_LINE_HEADING]
    # One phrase removed from the section, each in turn.
    for phrase in RED_LINE_PHRASES:
        damaged = text[:start] + text[start:end].replace(phrase, "") + text[end:]
        assert missing_red_lines(damaged) == [phrase], phrase


def test_invalid_utf8_file_is_reported(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    (roles / "engineer-demo" / "refs" / "note.md").write_bytes("笔记\n".encode() + b"\xe7\x9c\x9c\x9c\n")
    assert ("RP-009", FAIL) in _codes(roles, workspace)


def test_mojibake_file_is_reported(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    garbled = "笔记\n".encode().decode("latin-1")
    (roles / "engineer-demo" / "refs" / "note.md").write_text(garbled, encoding="utf-8")
    codes = _codes(roles, workspace)
    assert ("RP-009", FAIL) in codes


def test_replacement_character_is_reported_in_shared(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    (roles / "shared" / "refs" / "skill_coordination.md").write_text("共享\ufffd契约\n", encoding="utf-8")
    assert ("RP-009", FAIL) in _codes(roles, workspace)
