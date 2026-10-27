"""Role pack check (role-pack card 1): the shipped packs pass, and each rule catches its own breakage."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from auto_pm.application.core.role_pack_service import (
    FAIL,
    UNVERIFIED,
    RolePackService,
    default_roles_dir,
    split_front_matter,
)

OLD_BODY = "# Old\n\n先完整读取 `../shared/refs/skill_coordination.md`。\n\n## 步骤\n\n- 一\n"
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
    "legacy": {"mode": "body-equal", "source": ".trae/skills/demo-skill/SKILL.md", "refs": ".trae/skills/demo-skill/refs"},
}


def _skill(name: str, body: str = OLD_BODY) -> str:
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
    (old / "SKILL.md").write_text(_skill("demo-skill"), encoding="utf-8")
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
    (roles / "engineer-demo" / "SKILL.md").write_text(_skill("engineer-demo", OLD_BODY + "\n见 `refs/gone.md`\n"), encoding="utf-8")
    assert ("RP-007", FAIL) in _codes(roles, workspace)


def test_pointer_may_not_leave_roles_dir(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    (tmp_path / "outside.md").write_text("x", encoding="utf-8")
    (roles / "engineer-demo" / "SKILL.md").write_text(_skill("engineer-demo", OLD_BODY + "\n见 `../../outside.md`\n"), encoding="utf-8")
    assert ("RP-007", FAIL) in _codes(roles, workspace)


def test_body_drift_from_old_skill(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    (roles / "engineer-demo" / "SKILL.md").write_text(_skill("engineer-demo", OLD_BODY + "- 多一行\n"), encoding="utf-8")
    assert ("RP-008", FAIL) in _codes(roles, workspace)


def test_refs_drift_and_missing_ref(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    (roles / "engineer-demo" / "refs" / "note.md").write_text("改过\n", encoding="utf-8")
    assert ("RP-008", FAIL) in _codes(roles, workspace)
    (roles / "engineer-demo" / "refs" / "note.md").unlink()
    assert ("RP-008", FAIL) in _codes(roles, workspace)


def test_retired_flag_skips_equivalence(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    (roles / "engineer-demo" / "SKILL.md").write_text(_skill("engineer-demo", OLD_BODY + "- 新增\n"), encoding="utf-8")
    for path in sorted((workspace / ".trae" / "skills" / "demo-skill").rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    _edit_config(roles, lambda data: data["legacy"].update(retired=True))
    assert _codes(roles, workspace) == set()


def test_wrong_source_path_is_a_failure_not_a_silent_skip(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    (roles / "engineer-demo" / "SKILL.md").write_text(_skill("engineer-demo", OLD_BODY + "- 改坏\n"), encoding="utf-8")
    _edit_config(roles, lambda data: data["legacy"].update(source=".trae/skills/demo-skil/SKILL.md"))
    assert ("RP-008", FAIL) in _codes(roles, workspace)


def test_wrong_refs_path_is_a_failure_not_a_silent_skip(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    (roles / "engineer-demo" / "refs" / "note.md").write_text("改坏\n", encoding="utf-8")
    _edit_config(roles, lambda data: data["legacy"].update(refs=".trae/skills/demo-skill/ref"))
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


def test_section_contained_mode(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    legacy = {"mode": "section-contained", "source": ".trae/skills/demo-skill/SKILL.md", "from_heading": "## 步骤"}
    _edit_config(roles, lambda data: data.update(legacy=legacy))
    assert _codes(roles, workspace) == set()
    (roles / "engineer-demo" / "SKILL.md").write_text(_skill("engineer-demo", "# 新\n\n## 步骤\n\n- 改了\n"), encoding="utf-8")
    assert ("RP-008", FAIL) in _codes(roles, workspace)
    _edit_config(roles, lambda data: data["legacy"].update(from_heading="## 没有的标题"))
    assert ("RP-008", FAIL) in _codes(roles, workspace)


def test_front_matter_split_handles_crlf_and_none() -> None:
    meta, body = split_front_matter('---\r\nname: a\r\ndescription: "b"\r\n---\r\nbody\r\n')
    assert meta == {"name": "a", "description": "b"} and body == "body\n"
    assert split_front_matter("no front matter") == ({}, "no front matter")


def _real_workspace() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        if (parent / ".trae" / "skills").is_dir() and (parent / "00_Obsidian_Base全局规范文件仓库").is_dir():
            return parent
    return None


def test_shipped_packs_pass_and_match_old_skills() -> None:
    workspace = _real_workspace()
    assert workspace is not None, "测试必须在完整工作区里跑：找不到 .trae/skills 与规范库"
    result = RolePackService(default_roles_dir(), workspace).check()
    assert result.roles == ["fullstack-engineer", "plc-electrical-engineer", "product-pm"]
    # Nothing may stay unverified: the registry and the old skills were both read.
    assert result.findings == [], [vars(item) for item in result.findings]
