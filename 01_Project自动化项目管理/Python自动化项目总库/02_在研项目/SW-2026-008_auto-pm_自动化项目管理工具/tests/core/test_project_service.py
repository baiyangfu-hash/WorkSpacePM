"""ProjectService 单元测试"""

from __future__ import annotations

from pathlib import Path

import pytest
from auto_pm.core.project_service import ProjectService
from auto_pm.db.connection import DatabaseManager
from auto_pm.db.repository import ChangeRequestRepository
from auto_pm.models import ChangeSummary, ProjectInfo, ProjectRecord


def test_list_projects(tmp_workspace: Path) -> None:
    """测试项目扫描能发现模拟项目"""
    svc = ProjectService(str(tmp_workspace))
    projects = svc.list_projects()
    assert len(projects) == 1
    assert projects[0].project_id == "DJ-2026-TEST"
    assert projects[0].stack == "plc"
    assert projects[0].version == "V1.0.0"


def test_get_project(tmp_workspace: Path) -> None:
    """测试按ID查询项目"""
    svc = ProjectService(str(tmp_workspace))
    proj = svc.get_project("DJ-2026-TEST")
    assert proj is not None
    assert proj.project_id == "DJ-2026-TEST"
    assert "DJ-2026-TEST" in proj.path


def test_get_project_not_found(tmp_workspace: Path) -> None:
    """测试查询不存在的项目返回 None"""
    svc = ProjectService(str(tmp_workspace))
    proj = svc.get_project("NOT-EXIST")
    assert proj is None


def test_list_projects_empty(tmp_path: Path) -> None:
    """测试空工作空间返回空列表"""
    svc = ProjectService(str(tmp_path))
    projects = svc.list_projects()
    assert projects == []


# ── file_mtime 字段测试 ──────────────────────────────


class TestFileMtime:
    """file_mtime 字段填充测试"""

    def test_file_mtime_default_zero(self) -> None:
        """新建 ProjectInfo 的 file_mtime 默认为 0.0"""
        p = ProjectInfo(project_id="X", name="X", path="/x")
        assert p.file_mtime == 0.0

    def test_file_mtime_from_filesystem(self, tmp_workspace: Path) -> None:
        """文件系统扫描的项目应包含 file_mtime（.plc.json 存在，mtime > 0）"""
        svc = ProjectService(str(tmp_workspace))
        projects = svc.list_projects()
        assert len(projects) == 1
        assert projects[0].file_mtime > 0.0

    def test_file_mtime_from_cache(self, tmp_workspace: Path) -> None:
        """从缓存读取的项目应包含 file_mtime"""
        db = DatabaseManager(str(tmp_workspace))
        svc = ProjectService(str(tmp_workspace), db=db)
        svc.sync_to_cache(force_full=True)
        projects = svc.list_projects_cached()
        assert len(projects) >= 1
        for p in projects:
            assert p.file_mtime >= 0.0
        # DJ-2026-TEST 的 .plc.json 存在，mtime 应 > 0
        dj = [p for p in projects if p.project_id == "DJ-2026-TEST"][0]
        assert dj.file_mtime > 0.0


# ── list_projects_filtered 测试 ──────────────────────


class TestListProjectsFiltered:
    """list_projects_filtered 筛选方法测试"""

    @pytest.fixture
    def svc_with_db(self, tmp_workspace: Path) -> ProjectService:
        """创建带 DB 的 ProjectService，预置 3 条不同维度的项目记录"""
        db = DatabaseManager(str(tmp_workspace))
        db.init_schema()
        svc = ProjectService(str(tmp_workspace), db=db)
        records = [
            ProjectRecord(
                project_id="SW-2026-001",
                name="SW项目1",
                path="/tmp/sw1",
                stack="python",
                version="V1.0.0",
                description="",
                source="copier",
                phase="developing",
                business_line="SW",
                extra={},
                file_mtime=1000.0,
                last_scanned="2026-01-01",
            ),
            ProjectRecord(
                project_id="SW-2026-002",
                name="SW项目2",
                path="/tmp/sw2",
                stack="plc",
                version="V1.0.0",
                description="",
                source="copier",
                phase="production",
                business_line="SW",
                extra={},
                file_mtime=2000.0,
                last_scanned="2026-01-01",
            ),
            ProjectRecord(
                project_id="DJ-2026-001",
                name="DJ项目1",
                path="/tmp/dj1",
                stack="plc",
                version="V1.0.0",
                description="",
                source="copier",
                phase="developing",
                business_line="DJ",
                extra={},
                file_mtime=3000.0,
                last_scanned="2026-01-01",
            ),
        ]
        assert svc._repo is not None
        for r in records:
            svc._repo.upsert(r)
        return svc

    def test_no_filter_returns_all(self, svc_with_db: ProjectService) -> None:
        """无筛选条件返回全部"""
        result = svc_with_db.list_projects_filtered()
        assert len(result) == 3

    def test_filter_by_stack(self, svc_with_db: ProjectService) -> None:
        """按技术栈筛选"""
        result = svc_with_db.list_projects_filtered(stack="plc")
        assert len(result) == 2
        assert all(p.stack == "plc" for p in result)

    def test_filter_by_phase(self, svc_with_db: ProjectService) -> None:
        """按阶段筛选"""
        result = svc_with_db.list_projects_filtered(phase="developing")
        assert len(result) == 2
        assert all(p.phase == "developing" for p in result)

    def test_filter_by_business_line(self, svc_with_db: ProjectService) -> None:
        """按业务线筛选"""
        result = svc_with_db.list_projects_filtered(business_line="SW")
        assert len(result) == 2
        assert all(p.business_line == "SW" for p in result)

    def test_filter_stack_and_phase(self, svc_with_db: ProjectService) -> None:
        """stack+phase 联合筛选（内存筛选路径）"""
        result = svc_with_db.list_projects_filtered(stack="plc", phase="developing")
        assert len(result) == 1
        assert result[0].project_id == "DJ-2026-001"

    def test_filter_stack_and_business_line(self, svc_with_db: ProjectService) -> None:
        """stack+business_line 联合筛选"""
        result = svc_with_db.list_projects_filtered(stack="plc", business_line="SW")
        assert len(result) == 1
        assert result[0].project_id == "SW-2026-002"

    def test_filter_phase_and_business_line(self, svc_with_db: ProjectService) -> None:
        """phase+business_line 联合筛选"""
        result = svc_with_db.list_projects_filtered(phase="developing", business_line="SW")
        assert len(result) == 1
        assert result[0].project_id == "SW-2026-001"

    def test_filter_all_three(self, svc_with_db: ProjectService) -> None:
        """三维度联合筛选"""
        result = svc_with_db.list_projects_filtered(
            stack="plc", phase="developing", business_line="DJ"
        )
        assert len(result) == 1
        assert result[0].project_id == "DJ-2026-001"

    def test_filter_no_match(self, svc_with_db: ProjectService) -> None:
        """无匹配结果返回空列表"""
        result = svc_with_db.list_projects_filtered(stack="python", phase="production")
        assert result == []

    def test_filter_without_db_raises(self, tmp_path: Path) -> None:
        """未注入 DB 时抛 RuntimeError"""
        svc = ProjectService(str(tmp_path))
        with pytest.raises(RuntimeError, match="未注入 DatabaseManager"):
            svc.list_projects_filtered(stack="plc")


# ── list_projects_with_change_count 测试 ──────────────


class TestListProjectsWithChangeCount:
    """list_projects_with_change_count 方法测试"""

    def test_with_change_count(self, tmp_workspace: Path) -> None:
        """返回带变更数统计的项目列表"""
        db = DatabaseManager(str(tmp_workspace))
        db.init_schema()
        svc = ProjectService(str(tmp_workspace), db=db)
        assert svc._repo is not None
        svc._repo.upsert(
            ProjectRecord(
                project_id="SW-2026-001",
                name="项目A",
                path="/tmp/a",
                stack="plc",
                version="V1.0.0",
                description="",
                source="copier",
                phase="developing",
                business_line="SW",
                extra={},
                file_mtime=1000.0,
                last_scanned="2026-01-01",
            )
        )
        # 预置 3 条变更单
        change_repo = ChangeRequestRepository(db)
        for i in range(3):
            change_repo.upsert(
                ChangeSummary(
                    change_number=f"CHG-PLC-2026-00{i}",
                    project_id="SW-2026-001",
                    project_name="项目A",
                    domain="PLC",
                    business_nature="REQ",
                    impact_scope=["LOCAL"],
                    status="draft",
                    applicant="张三",
                    apply_date="2026-01-01",
                    title=f"变更{i}",
                )
            )

        result = svc.list_projects_with_change_count()
        assert len(result) == 1
        card = result[0]
        assert card.project_id == "SW-2026-001"
        assert card.name == "项目A"
        assert card.stack == "plc"
        assert card.phase == "developing"
        assert card.business_line == "SW"
        assert card.change_count == 3
        assert card.path == "/tmp/a"

    def test_with_change_count_empty(self, tmp_workspace: Path) -> None:
        """无项目时返回空列表"""
        db = DatabaseManager(str(tmp_workspace))
        db.init_schema()
        svc = ProjectService(str(tmp_workspace), db=db)
        result = svc.list_projects_with_change_count()
        assert result == []

    def test_with_change_count_zero(self, tmp_workspace: Path) -> None:
        """项目无变更单时 change_count 为 0"""
        db = DatabaseManager(str(tmp_workspace))
        db.init_schema()
        svc = ProjectService(str(tmp_workspace), db=db)
        assert svc._repo is not None
        svc._repo.upsert(
            ProjectRecord(
                project_id="SW-2026-001",
                name="项目A",
                path="/tmp/a",
                stack="plc",
                version="V1.0.0",
                description="",
                source="copier",
                phase="developing",
                business_line="SW",
                extra={},
                file_mtime=1000.0,
                last_scanned="2026-01-01",
            )
        )

        result = svc.list_projects_with_change_count()
        assert len(result) == 1
        assert result[0].change_count == 0

    def test_with_change_count_without_db_raises(self, tmp_path: Path) -> None:
        """未注入 DB 时抛 RuntimeError"""
        svc = ProjectService(str(tmp_path))
        with pytest.raises(RuntimeError, match="未注入 DatabaseManager"):
            svc.list_projects_with_change_count()


# ── Git Pre-commit Hooks 提交门禁测试 ──────────────────────


class TestGitHooks:
    """Git 提交门禁与自愈钩子测试"""

    def test_is_git_hooks_installed_not_exist(self, tmp_path: Path) -> None:
        """测试未安装钩子时返回 False"""
        svc = ProjectService(str(tmp_path))
        assert svc.is_git_hooks_installed(str(tmp_path)) is False

    def test_install_git_hooks_no_git_repo(self, tmp_path: Path) -> None:
        """测试没有 Git 仓库时安装失败"""
        svc = ProjectService(str(tmp_path))
        res = svc.install_git_hooks(str(tmp_path))
        assert res["success"] is False
        assert "未初始化 Git 仓库" in res["message"]

    def test_install_and_uninstall_git_hooks(self, tmp_path: Path) -> None:
        """测试 Git 钩子的完整安装与卸载流程"""
        # 1. 模拟 Git 仓库初始化
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "hooks").mkdir()

        svc = ProjectService(str(tmp_path))
        assert svc.is_git_hooks_installed(str(tmp_path)) is False

        # 2. 安装门禁
        res = svc.install_git_hooks(str(tmp_path))
        assert res["success"] is True
        assert svc.is_git_hooks_installed(str(tmp_path)) is True

        hook_file = git_dir / "hooks" / "pre-commit"
        assert hook_file.is_file()
        content = hook_file.read_text(encoding="utf-8")
        assert "auto-pm pre-commit" in content

        # 3. 卸载门禁
        unres = svc.uninstall_git_hooks(str(tmp_path))
        assert unres["success"] is True
        assert svc.is_git_hooks_installed(str(tmp_path)) is False
        assert not hook_file.is_file()
