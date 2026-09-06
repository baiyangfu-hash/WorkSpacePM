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


# ── P2 SQLite 外键约束异常根因治理与迁移防御测试 ─────


class TestP2ForeignKeyHardeningAndDefense:
    """Requirement R2: P2 首同步 SQLite 外键约束防御与拓扑排序测试"""

    def test_sync_changes_with_empty_project_id_fallback(
        self, db: DatabaseManager, tmp_path: Path
    ) -> None:
        """变更单 project_id 为空时自动回退到所属项目 ID 并成功写入 DB"""
        from unittest.mock import MagicMock

        from auto_pm.models import ChangeSummary

        proj_dir = tmp_path / "PRJ-2026-001_测试"
        proj_dir.mkdir()
        (proj_dir / ".plc.json").write_text('{"name": "PRJ-2026-001"}', encoding="utf-8")
        chg_dir = proj_dir / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-PLC"
        chg_dir.mkdir(parents=True)
        (chg_dir / "CHG-PLC-2026-001.md").write_text("# 变更单\n", encoding="utf-8")

        project_service = ProjectService(str(tmp_path))
        mock_change_service = MagicMock()
        # 模拟解析出的 summary.project_id 为空字符串
        empty_pid_summary = ChangeSummary(
            change_number="CHG-PLC-2026-001",
            project_id="",
            project_name="测试",
            domain="PLC",
            business_nature="DEF",
            impact_scope=[],
            status="draft",
        )
        mock_change_service.list_change_requests.return_value = [empty_pid_summary]

        sync = SyncService(db, project_service, mock_change_service)
        sync._sync_projects(force_full=True)

        # 执行变更单同步
        count = sync._sync_changes(force_full=True)
        assert count == 1

        # 验证 DB 中变更单的 project_id 被自动纠偏为所属项目
        records = sync.change_repo.list_by_project("PRJ-2026-001")
        assert len(records) == 1
        assert records[0].change_number == "CHG-PLC-2026-001"
        assert records[0].project_id == "PRJ-2026-001"

        # 验证无外键违规
        with db.get_connection() as conn:
            assert conn.execute("PRAGMA foreign_key_check;").fetchall() == []

    def test_sync_changes_with_missing_parent_creates_stub(
        self, db: DatabaseManager, tmp_path: Path
    ) -> None:
        """变更单引用的 project_id 在 projects 表中不存在时自动生成 is_stub 存根记录"""
        from unittest.mock import MagicMock

        from auto_pm.models import ChangeSummary

        proj_dir = tmp_path / "HOST-2026-001_宿主"
        proj_dir.mkdir()
        (proj_dir / ".plc.json").write_text('{"name": "HOST-2026-001"}', encoding="utf-8")
        chg_dir = proj_dir / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-PLC"
        chg_dir.mkdir(parents=True)
        (chg_dir / "CHG-PLC-2026-002.md").write_text("# 变更单\n", encoding="utf-8")

        project_service = ProjectService(str(tmp_path))
        mock_change_service = MagicMock()
        # 变更单指向一个独立孤立项目 ORPHAN-2026-888
        orphan_summary = ChangeSummary(
            change_number="CHG-PLC-2026-002",
            project_id="ORPHAN-2026-888",
            project_name="孤立项目",
            domain="PLC",
            business_nature="DEF",
            impact_scope=[],
            status="draft",
        )
        mock_change_service.list_change_requests.return_value = [orphan_summary]

        sync = SyncService(db, project_service, mock_change_service)
        sync._sync_projects(force_full=True)

        # 同步前确认 ORPHAN-2026-888 不存在于 projects
        assert sync.project_repo.get_by_id("ORPHAN-2026-888") is None

        # 执行变更单同步
        count = sync._sync_changes(force_full=True)
        assert count == 1

        # 验证 ORPHAN-2026-888 存根被自动创建
        stub_project = sync.project_repo.get_by_id("ORPHAN-2026-888")
        assert stub_project is not None
        assert stub_project.extra.get("is_stub") is True
        assert stub_project.extra.get("created_by") == "sync_fk_compensation"

        # 变更单记录正常存在
        changes = sync.change_repo.list_by_project("ORPHAN-2026-888")
        assert len(changes) == 1

        # 验证无外键违规
        with db.get_connection() as conn:
            assert conn.execute("PRAGMA foreign_key_check;").fetchall() == []

    def test_parser_extracts_project_id_from_frontmatter(self, tmp_path: Path) -> None:
        """ChgParser 支持从 YAML frontmatter 提取 project_id 与 change_number"""
        from auto_pm.domain.change.parser import ChgParser

        chg_file = tmp_path / "CHG-SCPT-2026-161.md"
        chg_file.write_text(
            "---\n"
            "id: CHG-SCPT-2026-161\n"
            "project_id: SW-2026-008\n"
            "---\n"
            "# 变更单：CHG-SCPT-2026-161\n"
            "## 1. 变更动因\n"
            "测试\n",
            encoding="utf-8",
        )
        parser = ChgParser()
        cr = parser.parse(str(chg_file))

        assert cr.change_number == "CHG-SCPT-2026-161"
        assert cr.project_id == "SW-2026-008"

    def test_parser_extracts_project_id_with_backticks(self, tmp_path: Path) -> None:
        """ChgParser 正则兼容带反引号的行内项目编号格式"""
        from auto_pm.domain.change.parser import ChgParser

        chg_file = tmp_path / "CHG-PLC-2026-001.md"
        chg_file.write_text(
            "## 1. 变更基本信息\n"
            "- **变更编号**：`CHG-PLC-2026-001`\n"
            "- **项目编号**：`DJ-2026-008`\n",
            encoding="utf-8",
        )
        parser = ChgParser()
        cr = parser.parse(str(chg_file))

        assert cr.project_id == "DJ-2026-008"
        assert cr.change_number == "CHG-PLC-2026-001"

    def test_stale_project_topological_deletion_order(
        self, db: DatabaseManager, tmp_path: Path
    ) -> None:
        """过期项目同步删除时，严格先删除子表变更单，再删除父表项目"""
        from auto_pm.models import ChangeSummary, ProjectRecord

        # 预先向 DB 写入父项目及子变更单
        parent = ProjectRecord(
            project_id="STALE-001",
            name="即将废弃项目",
            path=str(tmp_path / "STALE-001"),
            stack="python",
        )
        sync = SyncService(db, ProjectService(str(tmp_path)))
        sync.project_repo.upsert(parent)

        child = ChangeSummary(
            change_number="CHG-SCPT-2026-001",
            project_id="STALE-001",
            project_name="即将废弃项目",
            domain="SCPT",
            business_nature="DEF",
            impact_scope=[],
            status="draft",
        )
        sync.change_repo.upsert(child)

        # 记录方法调用顺序
        call_order = []
        original_delete_changes = sync.change_repo.delete_by_project
        original_delete_project = sync.project_repo.delete

        def tracked_delete_changes(pid: str) -> int:
            call_order.append(("delete_changes", pid))
            return original_delete_changes(pid)

        def tracked_delete_project(pid: str) -> bool:
            call_order.append(("delete_project", pid))
            return original_delete_project(pid)

        sync.change_repo.delete_by_project = tracked_delete_changes  # type: ignore[method-assign]
        sync.project_repo.delete = tracked_delete_project  # type: ignore[method-assign]

        # 同步（文件系统中无 STALE-001，触发 stale 清理）
        sync._sync_projects(force_full=True)

        # 断言先删子表后删父表
        assert ("delete_changes", "STALE-001") in call_order
        assert ("delete_project", "STALE-001") in call_order
        idx_changes = call_order.index(("delete_changes", "STALE-001"))
        idx_project = call_order.index(("delete_project", "STALE-001"))
        assert idx_changes < idx_project

        # 数据库中均已删除，无 FK 违规
        assert sync.project_repo.get_by_id("STALE-001") is None
        assert sync.change_repo.list_by_project("STALE-001") == []
        with db.get_connection() as conn:
            assert conn.execute("PRAGMA foreign_key_check;").fetchall() == []

    def test_sync_changes_fault_isolation(
        self, db: DatabaseManager, tmp_path: Path
    ) -> None:
        """单个变更单同步失败时不中断同一项目其他变更单的同步"""
        from unittest.mock import MagicMock

        from auto_pm.models import ChangeSummary

        proj_dir = tmp_path / "PRJ-ISO-001_隔离测试"
        proj_dir.mkdir()
        (proj_dir / ".plc.json").write_text('{"name": "PRJ-ISO-001"}', encoding="utf-8")
        chg_dir = proj_dir / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-PLC"
        chg_dir.mkdir(parents=True)
        (chg_dir / "CHG-PLC-2026-001.md").write_text("# 变更单1\n", encoding="utf-8")
        (chg_dir / "CHG-PLC-2026-002.md").write_text("# 变更单2\n", encoding="utf-8")

        project_service = ProjectService(str(tmp_path))
        mock_change_service = MagicMock()

        chg1 = ChangeSummary(
            change_number="CHG-PLC-2026-001",
            project_id="PRJ-ISO-001",
            project_name="隔离测试",
            domain="PLC",
            business_nature="DEF",
            impact_scope=[],
            status="draft",
        )
        chg2 = ChangeSummary(
            change_number="CHG-PLC-2026-002",
            project_id="PRJ-ISO-001",
            project_name="隔离测试",
            domain="PLC",
            business_nature="DEF",
            impact_scope=[],
            status="draft",
        )
        mock_change_service.list_change_requests.return_value = [chg1, chg2]

        sync = SyncService(db, project_service, mock_change_service)
        sync._sync_projects(force_full=True)

        # 模拟第一个变更单 upsert 抛出异常
        orig_upsert = sync.change_repo.upsert

        def flaky_upsert(summary: ChangeSummary, path: str = "", mtime: float = 0) -> None:
            if summary.change_number == "CHG-PLC-2026-001":
                raise RuntimeError("单个文件损坏模拟异常")
            orig_upsert(summary, path, mtime)

        sync.change_repo.upsert = flaky_upsert  # type: ignore[method-assign]

        # 同步应继续执行，成功同步 chg2
        synced_count = sync._sync_changes(force_full=True)
        assert synced_count == 1

        # chg2 成功入库
        changes = sync.change_repo.list_by_project("PRJ-ISO-001")
        assert len(changes) == 1
        assert changes[0].change_number == "CHG-PLC-2026-002"

    def test_fk_error_diagnostics_and_pragma_logging(
        self, db: DatabaseManager, caplog: pytest.LogCaptureFixture
    ) -> None:
        """外键冲突时 repository 记录详细诊断日志并由 sync 捕获 PRAGMA 违规"""
        import logging
        import sqlite3

        from auto_pm.db.repository import ChangeRequestRepository
        from auto_pm.models import ChangeSummary

        repo = ChangeRequestRepository(db)
        # 直接向不存在的父项目插入变更单
        orphan_summary = ChangeSummary(
            change_number="CHG-ORPHAN-001",
            project_id="NONEXISTENT-PID",
            project_name="无主",
            domain="PLC",
            business_nature="DEF",
            impact_scope=[],
            status="draft",
        )

        with caplog.at_level(logging.DEBUG):
            with pytest.raises(sqlite3.IntegrityError):
                repo.upsert(orphan_summary)

        # 验证 DEBUG 日志记录了 SQL 和参数，ERROR 日志记录了外键约束失败详情
        assert any("DB Executing SQL" in r.message for r in caplog.records)
        assert any("外键约束失败" in r.message and "NONEXISTENT-PID" in r.message for r in caplog.records)
