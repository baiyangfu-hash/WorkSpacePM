"""Workbench Facade 单元测试"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from auto_pm.application.workbench_facade import WorkbenchFacade


def test_get_dashboard_snapshot_success() -> None:
    """验证从 DashboardService 获取的数据能正确映射为 DashboardSnapshotDTO"""
    # Arrange
    mock_dashboard_service = MagicMock()
    # 模拟底座的返回
    mock_summary = MagicMock()
    mock_summary.total_projects = 10
    mock_summary.phase_counts = {"developing": 5}
    mock_summary.open_change_count = 3
    mock_summary.failed_check_project_count = 1
    mock_summary.failed_check_project_ids = ["P-001"]
    mock_summary.not_applicable_project_count = 2
    mock_summary.not_applicable_project_ids = ["P-002", "P-003"]
    mock_summary.recent_activities = [{"action": "test"}]
    mock_summary.risk_hints = [{"risk": "high"}]
    mock_dashboard_service.get_summary.return_value = mock_summary
    facade = WorkbenchFacade(
        dashboard_service=mock_dashboard_service,
        project_service=MagicMock(),
        asset_summary_service=MagicMock()
    )
    # Act
    result = facade.get_dashboard_snapshot()
    # Assert
    assert result.success is True
    assert result.payload is not None
    assert result.payload.total_projects == 10
    assert result.payload.phase_counts == {"developing": 5}
    assert result.payload.open_change_count == 3
    assert result.payload.failed_check_project_count == 1
    assert result.payload.not_applicable_project_count == 2
    assert result.payload.recent_activities == [{"action": "test"}]
    assert result.payload.risk_hints == [{"risk": "high"}]

def test_get_dashboard_snapshot_failure() -> None:
    """验证服务抛出异常时能被 QueryResult 正确捕获"""
    # Arrange
    mock_dashboard_service = MagicMock()
    mock_dashboard_service.get_summary.side_effect = Exception("DB Connection Error")

    facade = WorkbenchFacade(
        dashboard_service=mock_dashboard_service,
        project_service=MagicMock(),
        asset_summary_service=MagicMock()
    )
    # Act
    result = facade.get_dashboard_snapshot()

    # Assert
    assert result.success is False
    assert result.payload is None
    assert result.message == "DB Connection Error"
    assert "DB Connection Error" in result.errors


# ── get_active_change_status 测试（CHG-106 新增） ──────


def test_get_active_change_status_success() -> None:
    """验证获取活跃变更单状态机数据：12 状态 implementing → 4 节点 node[2] active"""
    mock_dashboard_service = MagicMock()
    mock_change = MagicMock()
    mock_change.change_number = "CHG-SCPT-2026-106"
    mock_change.title = "工作台 KPI 网格"
    mock_change.status = "implementing"
    mock_change.apply_date = "2026-07-09"
    mock_dashboard_service.get_active_change_for_project.return_value = mock_change

    facade = WorkbenchFacade(
        dashboard_service=mock_dashboard_service,
        project_service=MagicMock(),
    )

    result = facade.get_active_change_status("SW-2026-008")

    assert result.success is True
    assert result.payload["active"] is True  # type: ignore[index]
    assert result.payload["change_number"] == "CHG-SCPT-2026-106"  # type: ignore[index]
    assert result.payload["title"] == "工作台 KPI 网格"  # type: ignore[index]
    assert result.payload["status"] == "implementing"  # type: ignore[index]
    sm = result.payload["state_machine"]  # type: ignore[index]
    assert sm["current_node"] == 2
    assert sm["current_node_name"] == "实施中 (Implementing)"
    assert sm["progress"] == 66
    assert len(sm["nodes"]) == 4
    assert sm["nodes"][0]["status"] == "done"
    assert sm["nodes"][1]["status"] == "done"
    assert sm["nodes"][2]["status"] == "active"
    assert sm["nodes"][3]["status"] == "pending"


def test_get_active_change_status_no_active_change() -> None:
    """验证无活跃变更单时返回 active=False 的空状态"""
    mock_dashboard_service = MagicMock()
    mock_dashboard_service.get_active_change_for_project.return_value = None

    facade = WorkbenchFacade(
        dashboard_service=mock_dashboard_service,
        project_service=MagicMock(),
    )

    result = facade.get_active_change_status("SW-2026-008")

    assert result.success is True
    assert result.payload["active"] is False  # type: ignore[index]
    assert result.payload["change_number"] == ""  # type: ignore[index]
    # 状态机仍返回 Draft 节点结构
    assert result.payload["state_machine"]["current_node"] == 0  # type: ignore[index]
    assert len(result.payload["state_machine"]["nodes"]) == 4  # type: ignore[index]


def test_get_active_change_status_closed_progress_100() -> None:
    """验证 closed 状态映射到 node[3] 且 progress=100"""
    mock_dashboard_service = MagicMock()
    mock_change = MagicMock()
    mock_change.change_number = "CHG-SCPT-2026-105"
    mock_change.title = "TD-A04 修复"
    mock_change.status = "closed"
    mock_change.apply_date = "2026-07-09"
    mock_dashboard_service.get_active_change_for_project.return_value = mock_change

    facade = WorkbenchFacade(
        dashboard_service=mock_dashboard_service,
        project_service=MagicMock(),
    )

    result = facade.get_active_change_status("SW-2026-008")

    assert result.success is True
    sm = result.payload["state_machine"]  # type: ignore[index]
    assert sm["current_node"] == 3
    assert sm["progress"] == 100
    assert all(n["status"] == "done" for n in sm["nodes"])


def test_get_active_change_status_no_dashboard_service() -> None:
    """验证 DashboardService 未启用时返回失败"""
    facade = WorkbenchFacade(
        dashboard_service=None,
        project_service=MagicMock(),
    )

    result = facade.get_active_change_status("SW-2026-008")

    assert result.success is False
    assert "DashboardService 未启用" in result.errors


# ── list_project_cards 测试 ──────────────────────────────

def test_list_project_cards_empty() -> None:
    """空列表时返回 success + []"""
    mock_project_service = MagicMock()
    mock_project_service.list_projects_with_change_count.return_value = []

    facade = WorkbenchFacade(
        dashboard_service=MagicMock(),
        project_service=mock_project_service,
        asset_summary_service=MagicMock(),
    )

    result = facade.list_project_cards()

    assert result.success is True
    assert result.payload == []


def test_list_project_cards_normal() -> None:
    """正常列表，验证 ProjectCardDTO 字段映射（含 change_count）"""
    mock_item = MagicMock()
    mock_item.project_id = "SW-2026-001"
    mock_item.name = "Test Project"
    mock_item.stack = "python"
    mock_item.phase = "developing"
    mock_item.version = "0.1.0"
    mock_item.change_count = 3
    mock_item.path = "/tmp/test"
    mock_item.business_line = "SW"

    mock_project_service = MagicMock()
    mock_project_service.list_projects_with_change_count.return_value = [mock_item]

    facade = WorkbenchFacade(
        dashboard_service=MagicMock(),
        project_service=mock_project_service,
        asset_summary_service=MagicMock(),
    )

    result = facade.list_project_cards()

    assert result.success is True
    assert len(result.payload) == 1  # type: ignore[arg-type]
    card = result.payload[0]  # type: ignore[index]
    assert card.project_id == "SW-2026-001"
    assert card.name == "Test Project"
    assert card.open_change_count == 3
    assert card.health_status == "Has Changes"  # change_count=3 > 0
    assert card.path == "/tmp/test"
    assert card.business_line == "SW"


def test_list_project_cards_service_exception() -> None:
    """Service 抛异常时返回 success=False"""
    mock_project_service = MagicMock()
    mock_project_service.list_projects_with_change_count.side_effect = Exception("DB Error")

    facade = WorkbenchFacade(
        dashboard_service=MagicMock(),
        project_service=mock_project_service,
        asset_summary_service=MagicMock(),
    )

    result = facade.list_project_cards()

    assert result.success is False
    assert "DB Error" in result.message


def test_list_project_cards_no_db_fallback() -> None:
    """无 DB 时降级为 list_projects() + change_count=0"""
    mock_project = MagicMock()
    mock_project.project_id = "SW-2026-002"
    mock_project.name = "Fallback Project"
    mock_project.stack = "plc"
    mock_project.phase = "production"
    mock_project.version = "1.0.0"
    mock_project.path = "/tmp/fallback"
    mock_project.business_line = "DJ"

    mock_project_service = MagicMock()
    # list_projects_with_change_count 抛 RuntimeError（无 DB）
    mock_project_service.list_projects_with_change_count.side_effect = RuntimeError("未注入 DatabaseManager")
    mock_project_service.list_projects.return_value = [mock_project]

    facade = WorkbenchFacade(
        dashboard_service=MagicMock(),
        project_service=mock_project_service,
        asset_summary_service=MagicMock(),
    )

    result = facade.list_project_cards()

    assert result.success is True
    assert len(result.payload) == 1  # type: ignore[arg-type]
    card = result.payload[0]  # type: ignore[index]
    assert card.project_id == "SW-2026-002"
    assert card.open_change_count == 0  # 降级时 change_count=0


# ── get_project_workspace 测试 ──────────────────────────────

def test_get_project_workspace_not_found() -> None:
    """项目不存在时返回 success=False"""
    mock_project_service = MagicMock()
    mock_project_service.get_project.return_value = None

    facade = WorkbenchFacade(
        dashboard_service=MagicMock(),
        project_service=mock_project_service,
        asset_summary_service=MagicMock(),
    )

    result = facade.get_project_workspace("NOT-EXIST")

    assert result.success is False
    assert "Project not found" in result.message


def test_get_project_workspace_normal() -> None:
    """正常项目，验证 summary + asset_summary"""
    mock_project = MagicMock()
    mock_project.project_id = "SW-2026-001"
    mock_project.stack = "plc"
    mock_project.path = "/tmp/plc_project"
    mock_project.project_type = "standard"
    mock_project.model_dump.return_value = {"project_id": "SW-2026-001", "name": "PLC Project"}

    mock_project_service = MagicMock()
    mock_project_service.get_project.return_value = mock_project

    mock_asset_service = MagicMock()
    mock_asset_service.build_summary.return_value = {"status": "healthy", "total_issues": 0}

    facade = WorkbenchFacade(
        dashboard_service=MagicMock(),
        project_service=mock_project_service,
        asset_summary_service=mock_asset_service,
    )

    result = facade.get_project_workspace("SW-2026-001")

    assert result.success is True
    assert result.payload.project_id == "SW-2026-001"  # type: ignore[union-attr]
    assert result.payload.asset_summary["status"] == "healthy"  # type: ignore[union-attr, index]
    assert result.payload.document_status is None  # type: ignore[union-attr]  # TODO M3/M4
    assert result.payload.pending_actions == []  # type: ignore[union-attr]  # TODO M3


def test_get_project_workspace_python_project() -> None:
    """Python 项目 asset_summary 为 not_applicable"""
    mock_project = MagicMock()
    mock_project.project_id = "SW-2026-003"
    mock_project.stack = "python"
    mock_project.path = "/tmp/py_project"
    mock_project.project_type = "standard"
    mock_project.model_dump.return_value = {"project_id": "SW-2026-003"}

    mock_project_service = MagicMock()
    mock_project_service.get_project.return_value = mock_project

    mock_asset_service = MagicMock()
    mock_asset_service.build_summary.return_value = {
        "status": "not_applicable",
        "total_issues": 0,
        "issue_messages": ["仅 PLC 项目支持工程资产摘要"],
    }

    facade = WorkbenchFacade(
        dashboard_service=MagicMock(),
        project_service=mock_project_service,
        asset_summary_service=mock_asset_service,
    )

    result = facade.get_project_workspace("SW-2026-003")

    assert result.success is True
    assert result.payload.asset_summary["status"] == "not_applicable"  # type: ignore[union-attr, index]


# ── get_settings_summary 测试 ──────────────────────────────

def test_get_settings_summary_no_db() -> None:
    """无 DB 时 db_available=False"""
    mock_project_service = MagicMock()
    mock_project_service.workspace_root = "/tmp/ws"
    mock_project_service.get_db_path.return_value = ""
    mock_project_service.is_cache_available.return_value = False
    mock_project_service.get_project_count.return_value = 0
    mock_project_service.get_last_sync_time.return_value = "—"

    facade = WorkbenchFacade(
        dashboard_service=MagicMock(),
        project_service=mock_project_service,
        asset_summary_service=MagicMock(),
    )

    result = facade.get_settings_summary()

    assert result.success is True
    assert result.payload.db_available is False  # type: ignore[union-attr]
    assert result.payload.project_count == 0  # type: ignore[union-attr]
    assert result.payload.workspace_root == "/tmp/ws"  # type: ignore[union-attr]


def test_get_settings_summary_with_db() -> None:
    """有 DB 时返回正确统计 + DTO 字段"""
    mock_project_service = MagicMock()
    mock_project_service.workspace_root = "/tmp/ws"
    mock_project_service.get_db_path.return_value = "/tmp/ws/auto_pm.db"
    mock_project_service.is_cache_available.return_value = True
    mock_project_service.get_project_count.return_value = 5
    mock_project_service.get_last_sync_time.return_value = "2026-07-07 10:00"

    facade = WorkbenchFacade(
        dashboard_service=MagicMock(),
        project_service=mock_project_service,
        asset_summary_service=MagicMock(),
    )

    result = facade.get_settings_summary()

    assert result.success is True
    assert result.payload.db_available is True  # type: ignore[union-attr]
    assert result.payload.project_count == 5  # type: ignore[union-attr]
    assert "auto_pm.db" in result.payload.db_path  # type: ignore[union-attr]
    assert result.payload.last_sync == "2026-07-07 10:00"  # type: ignore[union-attr]


def test_get_settings_summary_exception() -> None:
    """异常降级"""
    mock_project_service = MagicMock()
    mock_project_service.get_db_path.side_effect = Exception("FS Error")

    facade = WorkbenchFacade(
        dashboard_service=MagicMock(),
        project_service=mock_project_service,
        asset_summary_service=MagicMock(),
    )

    result = facade.get_settings_summary()

    assert result.success is False
    assert "FS Error" in result.message


# ── clear_cache 测试 ──────────────────────────────

def test_clear_cache_no_db() -> None:
    """无 DB 时 success=False"""
    mock_project_service = MagicMock()
    mock_project_service.is_cache_available.return_value = False

    facade = WorkbenchFacade(
        dashboard_service=MagicMock(),
        project_service=mock_project_service,
        asset_summary_service=MagicMock(),
    )

    result = facade.clear_cache()

    assert result.success is False
    assert result.payload.success is False  # type: ignore[union-attr]
    assert "DB 未初始化" in result.payload.message  # type: ignore[union-attr]


def test_clear_cache_success() -> None:
    """正常清除后验证 db 重建"""
    mock_project_service = MagicMock()
    mock_project_service.is_cache_available.return_value = True
    mock_project_service.clear_cache.return_value = {
        "success": True,
        "message": "缓存已清除并重新初始化",
    }

    facade = WorkbenchFacade(
        dashboard_service=MagicMock(),
        project_service=mock_project_service,
        asset_summary_service=MagicMock(),
    )

    result = facade.clear_cache()

    assert result.success is True
    assert result.payload.success is True  # type: ignore[union-attr]
    assert "缓存已清除" in result.payload.message  # type: ignore[union-attr]


# ── rebuild_index 测试 ──────────────────────────────

def test_rebuild_index_no_db() -> None:
    """无 DB 时 success=False"""
    mock_project_service = MagicMock()
    mock_project_service.is_cache_available.return_value = False

    facade = WorkbenchFacade(
        dashboard_service=MagicMock(),
        project_service=mock_project_service,
        asset_summary_service=MagicMock(),
    )

    result = facade.rebuild_index()

    assert result.success is False
    assert result.payload.projects_found == 0  # type: ignore[union-attr]
    assert result.payload.changes_found == 0  # type: ignore[union-attr]


def test_rebuild_index_success() -> None:
    """正常重建后验证 projects_found/changes_found"""
    mock_project_service = MagicMock()
    mock_project_service.is_cache_available.return_value = True
    mock_project_service.sync_to_cache.return_value = {
        "projects_found": 3,
        "changes_found": 2,
    }

    facade = WorkbenchFacade(
        dashboard_service=MagicMock(),
        project_service=mock_project_service,
        asset_summary_service=MagicMock(),
    )

    result = facade.rebuild_index()

    assert result.success is True
    assert result.payload.projects_found == 3  # type: ignore[union-attr]
    assert result.payload.changes_found == 2  # type: ignore[union-attr]
    assert "发现 3 个项目" in result.payload.message  # type: ignore[union-attr]


# ── edit_project / delete_project 测试（M4 CHG-115 新增） ──


def test_edit_project_success() -> None:
    """验证编辑项目元数据成功"""
    mock_project = MagicMock()
    mock_project.model_dump.return_value = {"project_id": "SW-2026-001", "phase": "production"}

    mock_project_service = MagicMock()
    mock_project_service.update_project_meta.return_value = mock_project

    facade = WorkbenchFacade(
        dashboard_service=MagicMock(),
        project_service=mock_project_service,
    )

    result = facade.edit_project("SW-2026-001", phase="production", description="已上线")

    assert result.success is True
    assert "已更新" in result.message
    assert result.payload["project_id"] == "SW-2026-001"  # type: ignore[index]
    mock_project_service.update_project_meta.assert_called_once_with(
        "SW-2026-001", phase="production", description="已上线"
    )


def test_edit_project_not_found() -> None:
    """验证编辑不存在的项目返回失败"""
    mock_project_service = MagicMock()
    mock_project_service.update_project_meta.side_effect = FileNotFoundError("项目不存在")

    facade = WorkbenchFacade(
        dashboard_service=MagicMock(),
        project_service=mock_project_service,
    )

    result = facade.edit_project("NOT-EXIST", phase="developing")

    assert result.success is False
    assert "项目不存在" in result.message


def test_edit_project_exception() -> None:
    """验证编辑时异常降级返回失败"""
    mock_project_service = MagicMock()
    mock_project_service.update_project_meta.side_effect = Exception("IO Error")

    facade = WorkbenchFacade(
        dashboard_service=MagicMock(),
        project_service=mock_project_service,
    )

    result = facade.edit_project("SW-2026-001", phase="developing")

    assert result.success is False
    assert "IO Error" in result.message


@pytest.fixture(autouse=True)
def _no_agent_markers(monkeypatch: pytest.MonkeyPatch) -> None:
    """删除项目只认用户本人的环境（TD-208）；测试要不受跑测试的 agent 环境变量影响。"""
    from auto_pm.application.core.lease_handover_service import AGENT_MARKERS

    for name in AGENT_MARKERS:
        monkeypatch.delenv(name, raising=False)


def _delete_world(tmp_path: Path) -> tuple[Path, MagicMock]:
    """一个已提交的工作区和指向其中 ``proj`` 目录的项目服务桩。"""
    import subprocess

    root = tmp_path / "ws"
    (root / "proj").mkdir(parents=True)
    (root / "proj" / "a.txt").write_text("keep\n", encoding="utf-8")
    for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "base"]):
        subprocess.run(
            ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", *args],
            cwd=str(root), check=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    project = MagicMock()
    project.path = str(root / "proj")
    project.name = "Test Project"
    service = MagicMock()
    service.workspace_root = str(root)
    service.get_project.return_value = project
    return root, service


def test_delete_project_success(tmp_path: Path) -> None:
    """验证删除项目成功：目录整体搬进回收区（TD-193），不是直接删掉"""
    from unittest.mock import patch

    root, mock_project_service = _delete_world(tmp_path)

    with patch("auto_pm.logging.audit.audit_log"):
        facade = WorkbenchFacade(
            dashboard_service=MagicMock(),
            project_service=mock_project_service,
        )

        result = facade.delete_project("SW-2026-001")

    assert result.success is True
    assert "已删除" in result.message
    assert result.payload["project_id"] == "SW-2026-001"  # type: ignore[index]
    assert not (root / "proj").exists()
    (moved,) = list((root / ".auto-pm" / "recycle" / "SW-2026-001").iterdir())
    assert (moved / "a.txt").read_text(encoding="utf-8") == "keep\n"
    mock_project_service.sync_to_cache.assert_called_once_with(force_full=True)


def test_delete_project_refused_with_uncommitted_changes(tmp_path: Path) -> None:
    """验证有未提交改动时拒绝删除，目录原样保留（TD-193）"""
    root, mock_project_service = _delete_world(tmp_path)
    (root / "proj" / "a.txt").write_text("edited\n", encoding="utf-8")

    facade = WorkbenchFacade(dashboard_service=MagicMock(), project_service=mock_project_service)
    result = facade.delete_project("SW-2026-001")

    assert result.success is False
    assert "没提交的改动" in result.message
    assert (root / "proj" / "a.txt").read_text(encoding="utf-8") == "edited\n"
    mock_project_service.sync_to_cache.assert_not_called()


def test_delete_project_not_found() -> None:
    """验证删除不存在的项目返回失败"""
    mock_project_service = MagicMock()
    mock_project_service.get_project.return_value = None

    facade = WorkbenchFacade(
        dashboard_service=MagicMock(),
        project_service=mock_project_service,
    )

    result = facade.delete_project("NOT-EXIST")

    assert result.success is False
    assert "项目不存在" in result.message


def test_delete_project_exception() -> None:
    """验证删除时异常降级返回失败"""
    mock_project_service = MagicMock()
    mock_project_service.get_project.side_effect = Exception("Permission Denied")

    facade = WorkbenchFacade(
        dashboard_service=MagicMock(),
        project_service=mock_project_service,
    )

    result = facade.delete_project("SW-2026-001")

    assert result.success is False
    assert "Permission Denied" in result.message


def test_save_workspace_root_success_with_runtime_reload(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """配置保存成功且运行态重载成功时，返回双状态可观测结果。"""
    # 隔离配置文件路径，避免污染真实的 .auto-pm-workspace
    # 回归修复：测试残留导致 GUI 启动读到空 pytest 临时目录，整个界面变空架子
    _isolated_cfg = tmp_path / ".auto-pm-workspace"
    monkeypatch.setattr(
        "auto_pm.core.paths.get_config_file_path",
        lambda: str(_isolated_cfg),
    )

    mock_project_service = MagicMock()
    facade = WorkbenchFacade(
        dashboard_service=MagicMock(),
        project_service=mock_project_service,
    )

    runtime_calls: list[str] = []

    def _reload_callback(path: str) -> dict[str, object]:
        runtime_calls.append(path)
        return {"success": True, "message": "运行态已重载", "workspace_root": path}

    facade._reload_callback = _reload_callback

    result = facade.save_workspace_root(str(tmp_path))

    assert result.success is True
    assert result.payload is not None
    assert result.payload["config_saved"] is True
    assert result.payload["runtime_reloaded"] is True
    assert result.payload["workspace_root"] == os.path.abspath(str(tmp_path))
    assert runtime_calls == [os.path.abspath(str(tmp_path))]
    assert "运行态已重载" in result.message


def test_save_workspace_root_partial_success_when_runtime_reload_fails(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """配置已保存但运行态重载失败时，必须保留部分成功语义。"""
    # 隔离配置文件路径，避免污染真实的 .auto-pm-workspace
    # 回归修复：测试残留导致 GUI 启动读到空 pytest 临时目录，整个界面变空架子
    _isolated_cfg = tmp_path / ".auto-pm-workspace"
    monkeypatch.setattr(
        "auto_pm.core.paths.get_config_file_path",
        lambda: str(_isolated_cfg),
    )

    mock_project_service = MagicMock()
    facade = WorkbenchFacade(
        dashboard_service=MagicMock(),
        project_service=mock_project_service,
    )

    def _reload_callback(path: str) -> dict[str, object]:
        return {"success": False, "message": f"重载失败: {path}", "workspace_root": "/old/workspace"}

    facade._reload_callback = _reload_callback

    result = facade.save_workspace_root(str(tmp_path))

    assert result.success is False
    assert result.payload is not None
    assert result.payload["config_saved"] is True
    assert result.payload["runtime_reloaded"] is False
    assert result.payload["reload_message"] == f"重载失败: {os.path.abspath(str(tmp_path))}"
    assert "配置已保存，但运行态重载失败" in result.message
