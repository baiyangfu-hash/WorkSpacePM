"""SQLite 索引缓存层单元测试

覆盖：
- DatabaseManager: 连接管理、schema 初始化
- ProjectRepository: UPSERT/查询/删除/计数
- ChangeRequestRepository: UPSERT/查询/删除/计数
- ScanLogRepository: 插入/查询最新
- ProjectService 缓存集成: list_projects_cached/sync_to_cache
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from auto_pm.core.project_service import ProjectService
from auto_pm.db.connection import DatabaseManager
from auto_pm.db.repository import (
    ChangeRequestRepository,
    ProjectRepository,
    ScanLogRepository,
)
from auto_pm.models import ChangeSummary, ProjectRecord

# ── DatabaseManager 测试 ──────────────────────────────


class TestDatabaseManager:
    """连接管理器测试"""

    def test_init_schema_creates_tables(self, tmp_path: Path) -> None:
        """初始化 schema 后所有表应存在"""
        db = DatabaseManager(str(tmp_path))
        db.init_schema()

        with db.get_connection() as conn:
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert "projects" in tables
        assert "change_requests" in tables
        assert "scan_log" in tables

    def test_init_schema_idempotent(self, tmp_path: Path) -> None:
        """重复初始化 schema 应安全（幂等）"""
        db = DatabaseManager(str(tmp_path))
        db.init_schema()
        db.init_schema()  # 不应抛异常

    def test_db_file_location(self, tmp_path: Path) -> None:
        """DB 文件应位于 .auto-pm/index.db"""
        db = DatabaseManager(str(tmp_path))
        db.init_schema()
        assert db.exists()
        assert db.db_path.endswith(os.path.join(".auto-pm", "index.db"))

    def test_drop_all(self, tmp_path: Path) -> None:
        """drop_all 后表应不存在"""
        db = DatabaseManager(str(tmp_path))
        db.init_schema()
        db.drop_all()

        with db.get_connection() as conn:
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert "projects" not in tables
        assert "change_requests" not in tables


# ── ProjectRepository 测试 ────────────────────────────


class TestProjectRepository:
    """项目索引缓存 CRUD 测试"""

    @pytest.fixture
    def repo(self, tmp_path: Path) -> ProjectRepository:
        db = DatabaseManager(str(tmp_path))
        db.init_schema()
        return ProjectRepository(db)

    @staticmethod
    def _make_record(project_id: str = "SW-2026-001", name: str = "测试项目") -> ProjectRecord:
        return ProjectRecord(
            project_id=project_id,
            name=name,
            path=f"/tmp/{project_id}",
            stack="plc",
            version="V1.0.0",
            description="测试描述",
            source="copier",
            phase="developing",
            extra={"key": "value"},
            file_mtime=1000.0,
            last_scanned="2026-01-01T00:00:00",
        )

    def test_upsert_and_get(self, repo: ProjectRepository) -> None:
        """UPSERT 后应能查询到记录"""
        record = self._make_record()
        repo.upsert(record)

        result = repo.get_by_id("SW-2026-001")
        assert result is not None
        assert result.project_id == "SW-2026-001"
        assert result.name == "测试项目"
        assert result.stack == "plc"
        assert result.extra == {"key": "value"}
        assert result.file_mtime == 1000.0

    def test_upsert_overwrite(self, repo: ProjectRepository) -> None:
        """重复 UPSERT 应覆盖旧记录"""
        repo.upsert(self._make_record(name="旧名称"))
        repo.upsert(self._make_record(name="新名称"))

        result = repo.get_by_id("SW-2026-001")
        assert result is not None
        assert result.name == "新名称"

    def test_get_not_found(self, repo: ProjectRepository) -> None:
        """查询不存在的项目返回 None"""
        assert repo.get_by_id("NOT-EXIST") is None

    def test_list_all(self, repo: ProjectRepository) -> None:
        """list_all 返回所有项目（按 project_id 排序）"""
        repo.upsert(self._make_record("SW-2026-002", "项目B"))
        repo.upsert(self._make_record("SW-2026-001", "项目A"))

        records = repo.list_all()
        assert len(records) == 2
        assert records[0].project_id == "SW-2026-001"
        assert records[1].project_id == "SW-2026-002"

    def test_list_by_stack(self, repo: ProjectRepository) -> None:
        """按技术栈筛选"""
        repo.upsert(self._make_record("SW-2026-001", "PLC项目"))
        record_py = self._make_record("SW-2026-002", "Python项目")
        record_py.stack = "python"
        repo.upsert(record_py)

        plc_projects = repo.list_by_stack("plc")
        assert len(plc_projects) == 1
        assert plc_projects[0].project_id == "SW-2026-001"

    def test_list_by_phase(self, repo: ProjectRepository) -> None:
        """按阶段筛选项目"""
        repo.upsert(self._make_record("SW-2026-001", "开发中项目"))
        record_prod = self._make_record("SW-2026-002", "生产项目")
        record_prod.phase = "production"
        repo.upsert(record_prod)

        dev_projects = repo.list_by_phase("developing")
        assert len(dev_projects) == 1
        assert dev_projects[0].project_id == "SW-2026-001"

        prod_projects = repo.list_by_phase("production")
        assert len(prod_projects) == 1
        assert prod_projects[0].project_id == "SW-2026-002"

        # 不存在的阶段返回空列表
        assert repo.list_by_phase("archived") == []

    def test_delete(self, repo: ProjectRepository) -> None:
        """删除项目"""
        repo.upsert(self._make_record())
        assert repo.delete("SW-2026-001") is True
        assert repo.get_by_id("SW-2026-001") is None
        assert repo.delete("SW-2026-001") is False  # 已删除

    def test_count(self, repo: ProjectRepository) -> None:
        """项目计数"""
        assert repo.count() == 0
        repo.upsert(self._make_record("SW-2026-001"))
        repo.upsert(self._make_record("SW-2026-002"))
        assert repo.count() == 2

    def test_get_mtime(self, repo: ProjectRepository) -> None:
        """获取 file_mtime"""
        repo.upsert(self._make_record())
        assert repo.get_mtime("SW-2026-001") == 1000.0
        assert repo.get_mtime("NOT-EXIST") == 0


# ── ChangeRequestRepository 测试 ──────────────────────


class TestChangeRequestRepository:
    """变更单索引缓存 CRUD 测试"""

    @pytest.fixture
    def repo(self, tmp_path: Path) -> ChangeRequestRepository:
        db = DatabaseManager(str(tmp_path))
        db.init_schema()
        # 先插入引用的项目记录（外键约束）
        project_repo = ProjectRepository(db)
        project_repo.upsert(
            ProjectRecord(
                project_id="SW-2026-001",
                name="测试项目",
                path="/tmp/SW-2026-001",
                stack="plc",
                version="V1.0.0",
                description="测试",
                source="copier",
                phase="developing",
                extra={},
                file_mtime=1000.0,
                last_scanned="2026-01-01T00:00:00",
            )
        )
        return ChangeRequestRepository(db)

    @staticmethod
    def _make_summary(change_number: str = "CHG-PLC-2026-001") -> ChangeSummary:
        return ChangeSummary(
            change_number=change_number,
            project_id="SW-2026-001",
            project_name="测试项目",
            domain="PLC",
            business_nature="REQ",
            impact_scope=["LOCAL", "MODULE"],
            status="draft",
            applicant="张三",
            apply_date="2026-01-01",
            title="测试变更",
        )

    def test_upsert_and_list_by_project(self, repo: ChangeRequestRepository) -> None:
        """UPSERT 后按项目查询"""
        summary = self._make_summary()
        repo.upsert(summary, file_path="/tmp/chg.md", file_mtime=2000.0)

        results = repo.list_by_project("SW-2026-001")
        assert len(results) == 1
        assert results[0].change_number == "CHG-PLC-2026-001"
        assert results[0].project_name == "测试项目"
        assert results[0].impact_scope == ["LOCAL", "MODULE"]

    def test_list_all(self, repo: ChangeRequestRepository) -> None:
        """列出所有变更单"""
        repo.upsert(self._make_summary("CHG-PLC-2026-002"))
        repo.upsert(self._make_summary("CHG-PLC-2026-001"))

        results = repo.list_all()
        assert len(results) == 2
        assert results[0].change_number == "CHG-PLC-2026-001"

    def test_count_by_project(self, repo: ChangeRequestRepository) -> None:
        """按项目计数"""
        repo.upsert(self._make_summary("CHG-PLC-2026-001"))
        repo.upsert(self._make_summary("CHG-PLC-2026-002"))
        assert repo.count_by_project("SW-2026-001") == 2
        assert repo.count_by_project("NOT-EXIST") == 0

    def test_delete(self, repo: ChangeRequestRepository) -> None:
        """删除变更单"""
        repo.upsert(self._make_summary())
        assert repo.delete("CHG-PLC-2026-001") is True
        assert repo.delete("CHG-PLC-2026-001") is False

    def test_delete_by_project(self, repo: ChangeRequestRepository) -> None:
        """按项目删除所有变更单"""
        repo.upsert(self._make_summary("CHG-PLC-2026-001"))
        repo.upsert(self._make_summary("CHG-PLC-2026-002"))
        deleted = repo.delete_by_project("SW-2026-001")
        assert deleted == 2
        assert repo.count_by_project("SW-2026-001") == 0


# ── ScanLogRepository 测试 ────────────────────────────


class TestScanLogRepository:
    """扫描日志 CRUD 测试"""

    @pytest.fixture
    def repo(self, tmp_path: Path) -> ScanLogRepository:
        db = DatabaseManager(str(tmp_path))
        db.init_schema()
        return ScanLogRepository(db)

    def test_insert_and_get_latest(self, repo: ScanLogRepository) -> None:
        """插入日志并查询最新"""
        log_id = repo.insert(
            scan_type="full",
            projects_found=5,
            changes_found=3,
            duration_ms=100,
            status="success",
            message="",
        )
        assert log_id > 0

        latest = repo.get_latest()
        assert latest is not None
        assert latest["scan_type"] == "full"
        assert latest["projects_found"] == 5
        assert latest["status"] == "success"

    def test_get_latest_empty(self, repo: ScanLogRepository) -> None:
        """空表查询最新返回 None"""
        assert repo.get_latest() is None

    def test_get_latest_returns_most_recent(self, repo: ScanLogRepository) -> None:
        """get_latest 返回最近一条"""
        repo.insert("full", 1, 0, 50, "success", "first")
        repo.insert("incremental", 2, 1, 30, "success", "second")

        latest = repo.get_latest()
        assert latest is not None
        assert latest["message"] == "second"


# ── ProjectService 缓存集成测试 ──────────────────────


class TestProjectServiceCache:
    """ProjectService DB 缓存集成测试"""

    def test_list_projects_cached_without_db_raises(self, tmp_path: Path) -> None:
        """未注入 DB 时调用缓存方法应抛 RuntimeError"""
        svc = ProjectService(str(tmp_path))
        with pytest.raises(RuntimeError, match="未注入 DatabaseManager"):
            svc.list_projects_cached()

    def test_sync_to_cache_without_db_raises(self, tmp_path: Path) -> None:
        """未注入 DB 时调用同步方法应抛 RuntimeError"""
        svc = ProjectService(str(tmp_path))
        with pytest.raises(RuntimeError, match="未注入 DatabaseManager"):
            svc.sync_to_cache()

    def test_sync_to_cache_populates_db(self, tmp_workspace: Path) -> None:
        """同步后 DB 应包含扫描到的项目"""
        db = DatabaseManager(str(tmp_workspace))
        svc = ProjectService(str(tmp_workspace), db=db)

        result = svc.sync_to_cache(force_full=True)
        assert result["status"] == "success"
        assert result["projects_found"] >= 1

        # 从缓存读取应与文件系统扫描一致
        cached = svc.list_projects_cached()
        assert len(cached) >= 1
        assert any(p.project_id == "DJ-2026-TEST" for p in cached)

    def test_cached_project_matches_scan(self, tmp_workspace: Path) -> None:
        """缓存的项目数据应与文件系统扫描一致"""
        db = DatabaseManager(str(tmp_workspace))
        svc = ProjectService(str(tmp_workspace), db=db)

        # 文件系统扫描
        fs_projects = svc.list_projects()
        # 同步到缓存
        svc.sync_to_cache(force_full=True)
        # 缓存读取
        cached_projects = svc.list_projects_cached()

        assert len(fs_projects) == len(cached_projects)
        for fs_p, cached_p in zip(fs_projects, cached_projects):
            assert fs_p.project_id == cached_p.project_id
            assert fs_p.name == cached_p.name
            assert fs_p.stack == cached_p.stack
            assert fs_p.version == cached_p.version

    def test_get_project_cached(self, tmp_workspace: Path) -> None:
        """从缓存按 ID 查询项目"""
        db = DatabaseManager(str(tmp_workspace))
        svc = ProjectService(str(tmp_workspace), db=db)
        svc.sync_to_cache(force_full=True)

        proj = svc.get_project_cached("DJ-2026-TEST")
        assert proj is not None
        assert proj.project_id == "DJ-2026-TEST"
        assert proj.stack == "plc"

        assert svc.get_project_cached("NOT-EXIST") is None
