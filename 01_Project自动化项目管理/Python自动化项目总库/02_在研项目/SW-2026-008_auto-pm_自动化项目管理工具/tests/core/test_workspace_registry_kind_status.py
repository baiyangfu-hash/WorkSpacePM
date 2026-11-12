"""CHG-SCPT-2026-650：登记表的“项目性质”“项目状态”两栏——可缺省、schema 不升版本、删除只标不抹行。

审计三条硬约束里能在 CI 里做成测试的两条在这里：schema 仍是 ``workspace-registry.v1``；没有新栏的老条目读成“未分类”“在研”。
第三条（带新栏的文件给现役发布版读）CI 里没有现役发布目录，由验收方合并前手工核。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from auto_pm.application.core.workspace_registry_service import (
    WorkspaceRegistryError,
    WorkspaceRegistryService,
)
from auto_pm.contracts import workspace_context as wc
from auto_pm.ui.cli.__main__ import cli
from tests.core.test_workspace_registry_service import _anchor, _workspace

ROOT = Path(__file__).resolve().parents[2]


def _entries(registry: Path) -> list[dict[str, object]]:
    return list(json.loads(registry.read_text(encoding="utf-8"))["projects"])


def _entry_bytes(registry: Path) -> list[str]:
    """每一条在文件里的原文（按 json 缩进切开），用来核“别的条目逐字节不变”。"""
    text = registry.read_text(encoding="utf-8")
    body = text[text.index("[") + 1 : text.rindex("]")]
    chunks = [chunk.strip().rstrip(",") for chunk in body.split("\n    },") if chunk.strip()]
    return [chunk.removesuffix("}").rstrip() for chunk in chunks]


# ---------------------------------------------------------------- 硬约束 1、2


def test_schema_version_stays_v1() -> None:
    field = wc.WorkspaceRegistry.model_fields["schema_version"]
    assert field.default == "workspace-registry.v1"
    with pytest.raises(ValueError):
        wc.WorkspaceRegistry.model_validate({"schema_version": "workspace-registry.v2", "projects": []})


def test_an_old_entry_without_the_new_columns_reads_as_unclassified_and_active() -> None:
    old = {
        "project_id": "DJ-2026-005",
        "project_root": "0100_PLC自动化/DJ-2026-005",
        "development_root": "0100_PLC自动化/DJ-2026-005",
        "control_project_id": "",
        "control_pm_session": "",
        "runtime_root": "",
    }
    registry = wc.WorkspaceRegistry.model_validate({"schema_version": "workspace-registry.v1", "projects": [old]})
    entry = registry.projects[0]
    assert (entry.kind, entry.status, entry.status_before_delete) == ("", "", "")
    assert (wc.kind_label(entry.kind), wc.status_label(entry.status)) == ("未分类", "在研")


def test_the_real_registry_still_reads(tmp_path: Path) -> None:
    """仓库里那份登记表（本单不改它，填栏由本地主力另做）新代码照样能读。"""
    real = ROOT.parents[3] / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    if not real.is_file():
        pytest.skip("单独拷出的项目目录里没有工作区登记表")
    registry = wc.WorkspaceRegistry.model_validate(json.loads(real.read_text(encoding="utf-8")))
    assert registry.schema_version == "workspace-registry.v1" and registry.projects


def test_values_and_labels_are_one_to_one() -> None:
    assert set(wc.KIND_LABELS) == {"", "equipment", "library", "test", "tool"}
    assert [wc.KIND_LABELS[k] for k in ("equipment", "library", "test", "tool")] == ["设备", "公共库", "测试", "工具"]
    assert [wc.STATUS_LABELS[k] for k in wc.USER_STATUSES] == ["在研", "暂停", "已归档"]
    assert wc.STATUS_LABELS["deleted"] == "已删除" and "deleted" not in wc.USER_STATUSES
    assert set(wc.KIND_LABELS) == set(wc.ProjectKind.__args__)  # type: ignore[attr-defined]
    assert set(wc.STATUS_LABELS) == set(wc.ProjectStatus.__args__)  # type: ignore[attr-defined]


def test_an_unknown_value_in_the_registry_is_refused() -> None:
    bad = {"project_id": "X", "project_root": "x", "development_root": "x", "status": "dead"}
    with pytest.raises(ValueError):
        wc.WorkspaceProjectMapping.model_validate(bad)


def test_the_dashboard_copy_of_the_values_matches_the_contract() -> None:
    """看板脚本可以单独拷走运行，照抄了一份取值；两份必须一字不差。"""
    spec = importlib.util.spec_from_file_location("pm_dashboard_for_kinds", ROOT / "scripts" / "pm_dashboard.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    assert module.KIND_LABELS == wc.KIND_LABELS
    assert module.STATUS_LABELS == wc.STATUS_LABELS
    assert module.TOOL_KINDS == wc.TOOL_KINDS


# ---------------------------------------------------------------- register 带两栏


def test_register_writes_kind_and_status(tmp_path: Path) -> None:
    registry = _workspace(tmp_path)
    _anchor(tmp_path / "0100_PLC自动化" / "DJ-2026-009", "DJ-2026-009")
    before = _entry_bytes(registry)
    result = WorkspaceRegistryService(tmp_path).register("DJ-2026-009", kind="equipment", status="paused")
    assert result.written
    added = _entries(registry)[-1]
    assert (added["kind"], added["status"]) == ("equipment", "paused")
    assert "status_before_delete" not in added
    assert _entry_bytes(registry)[: len(before)] == before


@pytest.mark.parametrize(("kind", "status", "words"), [("plc", "", "项目性质"), ("", "deleted", "只由删除命令"), ("", "done", "项目状态")])
def test_register_refuses_unknown_or_internal_values(tmp_path: Path, kind: str, status: str, words: str) -> None:
    registry = _workspace(tmp_path)
    _anchor(tmp_path / "0100_PLC自动化" / "DJ-2026-009", "DJ-2026-009")
    original = registry.read_bytes()
    with pytest.raises(WorkspaceRegistryError, match=words):
        WorkspaceRegistryService(tmp_path).register("DJ-2026-009", kind=kind, status=status)
    assert registry.read_bytes() == original


def test_cli_register_takes_kind_and_status(tmp_path: Path) -> None:
    registry = _workspace(tmp_path)
    _anchor(tmp_path / "0100_PLC自动化" / "DJ-2026-009", "DJ-2026-009")
    result = CliRunner().invoke(
        cli, ["-w", str(tmp_path), "project", "register", "DJ-2026-009", "--kind", "library", "--status", "archived"]
    )
    assert result.exit_code == 0, result.output
    assert "项目性质: 公共库" in result.output and "项目状态: 已归档" in result.output
    assert (_entries(registry)[-1]["kind"], _entries(registry)[-1]["status"]) == ("library", "archived")
    refused = CliRunner().invoke(cli, ["-w", str(tmp_path), "project", "register", "DJ-2026-005", "--status", "deleted"])
    assert refused.exit_code == 2  # click 的选项里根本没有 deleted


# ---------------------------------------------------------------- 删除标“已删除”、搬回改回


def test_mark_deleted_keeps_the_entry_and_every_other_entry_byte_for_byte(tmp_path: Path) -> None:
    registry = _workspace(tmp_path)
    text = registry.read_text(encoding="utf-8").replace(
        '"runtime_root": ""\n    }\n  ]', '"runtime_root": "",\n      "status": "paused"\n    }\n  ]'
    )
    registry.write_text(text, encoding="utf-8", newline="\n")
    before = _entry_bytes(registry)

    changed = WorkspaceRegistryService(tmp_path).mark_deleted("DJ-2026-005")

    assert changed is not None and changed.written and (changed.before, changed.after) == ("paused", "deleted")
    entries = _entries(registry)
    assert [e["project_id"] for e in entries] == ["SYS-2026-001", "DJ-2026-005"]  # 不抹行
    assert (entries[1]["status"], entries[1]["status_before_delete"]) == ("deleted", "paused")
    assert _entry_bytes(registry)[0] == before[0]
    wc.WorkspaceRegistry.model_validate(json.loads(registry.read_text(encoding="utf-8")))

    again = WorkspaceRegistryService(tmp_path).mark_deleted("DJ-2026-005")
    assert again is not None and not again.written  # 已经是“已删除”，不再改写

    back = WorkspaceRegistryService(tmp_path).mark_restored("DJ-2026-005")
    assert back is not None and back.written and (back.before, back.after) == ("deleted", "paused")
    assert (_entries(registry)[1]["status"], _entries(registry)[1]["status_before_delete"]) == ("paused", "")
    assert _entry_bytes(registry)[0] == before[0]


def test_an_unregistered_project_or_a_workspace_without_a_registry_is_left_alone(tmp_path: Path) -> None:
    registry = _workspace(tmp_path)
    original = registry.read_bytes()
    assert WorkspaceRegistryService(tmp_path).mark_deleted("DJ-2026-777") is None
    assert WorkspaceRegistryService(tmp_path).mark_restored("DJ-2026-777") is None
    assert registry.read_bytes() == original
    bare = tmp_path / "bare"
    bare.mkdir()
    assert WorkspaceRegistryService(bare).mark_deleted("DJ-2026-005") is None
    assert not (bare / "SYS-2026-001_WorkspaceGovernance").exists()


def test_restoring_an_entry_that_is_not_deleted_changes_nothing(tmp_path: Path) -> None:
    registry = _workspace(tmp_path)
    original = registry.read_bytes()
    changed = WorkspaceRegistryService(tmp_path).mark_restored("DJ-2026-005")
    assert changed is not None and not changed.written
    assert registry.read_bytes() == original
