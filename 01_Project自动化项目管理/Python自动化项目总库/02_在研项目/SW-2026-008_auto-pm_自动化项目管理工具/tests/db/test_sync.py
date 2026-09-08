"""SyncService 增量扫描同步测试"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from auto_pm.core.project_service import ProjectService
from auto_pm.db.connection import DatabaseManager
from auto_pm.db.sync import SyncService

# ── Fixtures ──────────────────────────────────────────


@pytest.fixture
def db(tmp_path: Path) -> DatabaseManager:
    """创建测试用数据库"""
    db = DatabaseManager(str(tmp_path))
    db.init_schema()
    return db


@pytest.fixture
def workspace_with_project(tmp_path: Path) -> Path:
    """创建包含一个 PLC 项目的工作空间"""
    project_dir = tmp_path / "DJ-2026-001_测试项目"
    project_dir.mkdir()
    (project_dir / ".plc.json").write_text(
        json.dumps(
            {
                "name": "DJ-2026-001",
                "version": "V1.0.0",
                "description": "测试项目",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def sync_service(db: DatabaseManager, workspace_with_project: Path) -> SyncService:
    """创建 SyncService 实例"""
    project_service = ProjectService(str(workspace_with_project))
    return SyncService(db, project_service)


# ── sync 测试 ─────────────────────────────────────────


class TestSync:
    """同步主流程测试"""

    def test_sync_full(self, sync_service: SyncService) -> None:
        """全量同步应发现项目"""
        result = sync_service.sync(force_full=True)

        assert result["status"] == "success"
        assert result["scan_type"] == "full"
        assert result["projects_found"] >= 1

    def test_sync_incremental(self, sync_service: SyncService) -> None:
        """增量同步（无变化时应跳过）"""
        # 先全量同步
        sync_service.sync(force_full=True)
        # 再增量同步
        result = sync_service.sync(force_full=False)

        assert result["status"] == "success"
        assert result["scan_type"] == "incremental"

    def test_sync_force_full(self, sync_service: SyncService) -> None:
        """强制全量同步"""
        result = sync_service.sync(force_full=True)

        assert result["status"] == "success"
        assert result["scan_type"] == "full"

    def test_sync_returns_duration(self, sync_service: SyncService) -> None:
        """同步结果应包含耗时"""
        result = sync_service.sync(force_full=True)

        assert "duration_ms" in result
        assert result["duration_ms"] >= 0


# ── _sync_projects 测试 ───────────────────────────────


class TestSyncProjects:
    """项目同步测试"""

    def test_detect_new_project(self, sync_service: SyncService) -> None:
        """检测新项目"""
        count = sync_service._sync_projects(force_full=True)

        assert count >= 1

    def test_detect_deleted_project(
        self, db: DatabaseManager, workspace_with_project: Path
    ) -> None:
        """检测已删除的项目（过期清理）"""
        project_service = ProjectService(str(workspace_with_project))
        sync = SyncService(db, project_service)

        # 先全量同步
        sync._sync_projects(force_full=True)

        # 确认 DB 中有记录
        records = sync.project_repo.list_all()
        assert len(records) >= 1

        # 删除项目目录
        import shutil
        project_dir = workspace_with_project / "DJ-2026-001_测试项目"
        shutil.rmtree(project_dir)

        # 重新同步，应清理过期记录
        sync._sync_projects(force_full=True)

        records = sync.project_repo.list_all()
        assert all(r.project_id != "DJ-2026-001" for r in records)

    def test_incremental_skip_unchanged(
        self, sync_service: SyncService
    ) -> None:
        """增量同步跳过无变化的项目"""
        # 全量同步
        sync_service._sync_projects(force_full=True)

        # 增量同步（无变化）
        count = sync_service._sync_projects(force_full=False)

        assert count == 0


# ── _sync_changes 测试 ────────────────────────────────


class TestSyncChanges:
    """变更单同步测试"""

    def test_sync_changes_without_change_service(self, sync_service: SyncService) -> None:
        """无 ChangeService 时同步变更单返回 0"""
        sync_service.change_service = None
        count = sync_service._sync_changes(force_full=True)

        assert count == 0

    def test_sync_changes_with_change_service(
        self, db: DatabaseManager, workspace_with_project: Path
    ) -> None:
        """有 ChangeService 时同步变更单"""
        from auto_pm.change.change_service import ChangeService

        project_service = ProjectService(str(workspace_with_project))
        change_service = ChangeService(str(workspace_with_project))
        sync = SyncService(db, project_service, change_service)

        # 先同步项目
        sync._sync_projects(force_full=True)

        # 同步变更单（无变更单文件时应返回 0）
        count = sync._sync_changes(force_full=True)
        assert count == 0


# ── _get_project_mtime 测试 ───────────────────────────


class TestGetProjectMtime:
    """项目 mtime 检测测试"""

    def test_mtime_with_plc_json(self, workspace_with_project: Path) -> None:
        """有 .plc.json 时 mtime > 0"""
        project_path = str(workspace_with_project / "DJ-2026-001_测试项目")
        mtime = SyncService._get_project_mtime(project_path)

        assert mtime > 0

    def test_mtime_without_markers(self, tmp_path: Path) -> None:
        """无标志文件时 mtime == 0"""
        empty_dir = tmp_path / "empty_project"
        empty_dir.mkdir()
        mtime = SyncService._get_project_mtime(str(empty_dir))

        assert mtime == 0.0

    def test_mtime_with_pm_session(self, tmp_path: Path) -> None:
        """有 PM_SESSION 文件时 mtime > 0"""
        project_dir = tmp_path / "DJ-2026-PM_项目"
        project_dir.mkdir()
        (project_dir / "PM_SESSION_DJ-2026-PM.md").write_text("# PM_SESSION\n", encoding="utf-8")

        mtime = SyncService._get_project_mtime(str(project_dir))
        assert mtime > 0


# ── _find_change_file 测试 ────────────────────────────


class TestFindChangeFile:
    """变更单文件查找测试"""

    def test_find_existing_change_file(self, tmp_path: Path) -> None:
        """查找存在的变更单文件（位于 CHG-{domain}/ 子目录下）"""
        change_dir = tmp_path / "01_变更单"
        chg_subdir = change_dir / "CHG-PLC"
        chg_subdir.mkdir(parents=True)
        (chg_subdir / "CHG-PLC-2026-001.md").write_text("# 变更单\n", encoding="utf-8")

        result = SyncService._find_change_file(str(change_dir), "CHG-PLC-2026-001")
        assert result is not None
        assert "CHG-PLC-2026-001.md" in result

    def test_find_nonexistent_change_file(self, tmp_path: Path) -> None:
        """查找不存在的变更单文件"""
        change_dir = tmp_path / "01_变更单"
        (change_dir / "CHG-PLC").mkdir(parents=True)

        result = SyncService._find_change_file(str(change_dir), "CHG-PLC-2026-999")
        assert result is None

    def test_find_change_file_nonexistent_dir(self, tmp_path: Path) -> None:
        """目录不存在时返回 None"""
        result = SyncService._find_change_file(str(tmp_path / "nonexistent"), "CHG-PLC-2026-001")
        assert result is None


# ── 错误处理测试 ──────────────────────────────────────


class TestSyncErrors:
    """同步错误处理测试"""

    def test_sync_handles_exception(self, db: DatabaseManager, tmp_path: Path) -> None:
        """同步过程中异常应返回 failed 状态"""
        project_service = ProjectService(str(tmp_path))
        sync = SyncService(db, project_service)

        # 模拟异常
        with patch.object(sync, "_sync_projects", side_effect=RuntimeError("测试异常")):
            result = sync.sync(force_full=True)

        assert result["status"] == "failed"
        assert "测试异常" in result["message"]


# ── CHG-085 scanner_version 增量同步测试 ──────────────


class TestScannerVersionChg085:
    """CHG-085: scanner_version 机制测试（P1 缺陷根源修复）

    原 P1 缺陷：增量同步仅看 marker 文件 mtime，scanner 逻辑变更
    （如 stack/phase 推断规则修改）不触发已缓存项目重扫。
    修复：DB 增加 scanner_version 列，版本不匹配时强制重扫。
    """

    def test_scanner_version_persisted_after_full_sync(
        self, sync_service: SyncService
    ) -> None:
        """全量同步后 DB 记录的 scanner_version 应等于当前 scanner 版本"""
        sync_service._sync_projects(force_full=True)

        records = sync_service.project_repo.list_all()
        assert len(records) >= 1
        for record in records:
            assert record.scanner_version == sync_service.scanner_version

    def test_incremental_rescan_when_scanner_version_mismatch(
        self, db: DatabaseManager, workspace_with_project: Path
    ) -> None:
        """DB 中 scanner_version 不匹配时增量同步强制重扫"""
        from auto_pm.db.sync import SCANNER_VERSION

        project_service = ProjectService(str(workspace_with_project))
        # 用 v1 版本同步（模拟旧版 scanner 缓存）
        sync_v1 = SyncService(db, project_service, scanner_version="v1")
        sync_v1._sync_projects(force_full=True)

        # 确认 DB 中记录的 scanner_version == "v1"
        record = sync_v1.project_repo.get_by_id("DJ-2026-001")
        assert record is not None
        assert record.scanner_version == "v1"

        # 用当前版本（v2）增量同步，应强制重扫
        sync_v2 = SyncService(db, project_service, scanner_version=SCANNER_VERSION)
        count = sync_v2._sync_projects(force_full=False)

        # 应该重扫了至少 1 个项目（scanner_version 不匹配）
        assert count >= 1
        # 重扫后 DB 中 scanner_version 应更新为 v2
        record = sync_v2.project_repo.get_by_id("DJ-2026-001")
        assert record is not None
        assert record.scanner_version == SCANNER_VERSION

    def test_incremental_skip_when_scanner_version_match(
        self, sync_service: SyncService
    ) -> None:
        """DB 中 scanner_version 匹配且 mtime 无变化时增量同步跳过"""
        # 全量同步
        sync_service._sync_projects(force_full=True)

        # 增量同步（scanner_version 一致 + mtime 无变化）
        count = sync_service._sync_projects(force_full=False)

        # 应跳过所有项目
        assert count == 0
