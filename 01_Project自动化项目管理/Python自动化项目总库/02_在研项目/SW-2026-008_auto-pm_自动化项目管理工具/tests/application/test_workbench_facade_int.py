from __future__ import annotations

import shutil
from collections.abc import Generator
from pathlib import Path

import pytest
from auto_pm.core.project_service import ProjectService
from auto_pm.db.connection import DatabaseManager

from auto_pm.application.workbench_facade import WorkbenchFacade


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Generator[str, None, None]:
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir()

    # Create a mock project
    proj_dir = ws_dir / "02_在研项目" / "SW-2026-001_Test"
    proj_dir.mkdir(parents=True)
    (proj_dir / ".copier-answers.yml").write_text("project_id: SW-2026-001\nproject_name: Test Project", encoding="utf-8")

    yield str(ws_dir)
    shutil.rmtree(ws_dir, ignore_errors=True)

@pytest.fixture
def workbench_facade(temp_workspace: str) -> WorkbenchFacade:
    # DatabaseManager 接收 workspace_root，db 实际路径为 <workspace>/.auto-pm/index.db
    db = DatabaseManager(temp_workspace)
    db.init_schema()

    project_service = ProjectService(workspace_root=temp_workspace)
    project_service.inject_db(db)

    return WorkbenchFacade(
        dashboard_service=None,
        project_service=project_service,
        asset_summary_service=None,
    )

def test_workbench_facade_rebuild_index_and_stats(workbench_facade: WorkbenchFacade) -> None:
    # 1. Test rebuild index
    res = workbench_facade.rebuild_index()
    assert res.success is True
    assert res.payload.projects_found == 1  # type: ignore[union-attr]

    # 2. Test get_settings_summary for DB stats
    summary_res = workbench_facade.get_settings_summary()
    assert summary_res.success is True
    payload = summary_res.payload
    assert payload.db_available is True  # type: ignore[union-attr]
    assert payload.project_count == 1  # type: ignore[union-attr]
    assert "index.db" in payload.db_path  # type: ignore[union-attr]


def test_workbench_facade_full_flow(workbench_facade: WorkbenchFacade) -> None:
    """端到端：rebuild_index → list_project_cards → get_project_workspace → get_dashboard_snapshot"""
    # 1. 重建索引
    rebuild_res = workbench_facade.rebuild_index()
    assert rebuild_res.success is True
    assert rebuild_res.payload.projects_found == 1  # type: ignore[union-attr]

    # 2. 获取项目卡片列表（DB 缓存模式）
    cards_res = workbench_facade.list_project_cards()
    assert cards_res.success is True
    assert len(cards_res.payload) == 1  # type: ignore[arg-type]
    card = cards_res.payload[0]  # type: ignore[index]
    assert card.project_id == "SW-2026-001"
    assert card.name == "Test Project"
    assert card.open_change_count == 0  # 无变更单

    # 3. 获取项目工作台详情
    ws_res = workbench_facade.get_project_workspace("SW-2026-001")
    assert ws_res.success is True
    assert ws_res.payload.project_id == "SW-2026-001"  # type: ignore[union-attr]
    # asset_summary_service=None，所以 asset_summary 为 None
    assert ws_res.payload.asset_summary is None  # type: ignore[union-attr]

    # 4. 获取驾驶舱摘要（dashboard_service=None 会抛异常，返回 success=False）
    dash_res = workbench_facade.get_dashboard_snapshot()
    assert dash_res.success is False  # 预期失败，因 dashboard_service=None


def test_workbench_facade_clear_and_rebuild(workbench_facade: WorkbenchFacade) -> None:
    """清缓存后重建索引，验证数据一致性"""
    # 1. 先重建索引
    rebuild_res = workbench_facade.rebuild_index()
    assert rebuild_res.success is True
    assert rebuild_res.payload.projects_found == 1  # type: ignore[union-attr]

    # 2. 清除缓存
    clear_res = workbench_facade.clear_cache()
    assert clear_res.success is True
    assert clear_res.payload.success is True  # type: ignore[union-attr]

    # 3. 再次重建索引，验证数据一致
    rebuild_res2 = workbench_facade.rebuild_index()
    assert rebuild_res2.success is True
    assert rebuild_res2.payload.projects_found == 1  # type: ignore[union-attr]

    # 4. 验证项目列表仍可正常获取
    cards_res = workbench_facade.list_project_cards()
    assert cards_res.success is True
    assert len(cards_res.payload) == 1  # type: ignore[arg-type]
