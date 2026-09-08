"""业务线分类与筛选测试

测试 extract_business_line 函数（位于 auto_pm/models/project.py）：
- 标准项目编号提取业务线前缀
- 无效格式返回空字符串
- Project 模型 business_line 字段
- DB upsert/get 往返保持 business_line
- list_by_business_line 查询
"""

from __future__ import annotations

from pathlib import Path

import pytest
from auto_pm.db.connection import DatabaseManager
from auto_pm.db.repository import ProjectRepository
from auto_pm.models import Project, ProjectRecord, extract_business_line

# ── extract_business_line 函数测试 ──────────────────────


class TestExtractBusinessLine:
    """extract_business_line 函数测试"""

    @pytest.mark.parametrize(
        "project_id,expected",
        [
            ("SW-2026-008", "SW"),
            ("DJ-2026-010", "DJ"),
            ("ZD-2026-001", "ZD"),
            ("XT-2026-005", "XT"),
            ("WX-2026-003", "WX"),
        ],
    )
    def test_standard_business_lines(self, project_id: str, expected: str) -> None:
        """各业务线标准编号应正确提取前缀"""
        assert extract_business_line(project_id) == expected

    @pytest.mark.parametrize(
        "project_id",
        [
            "bad",
            "invalid-id",
            "",
            "SW2026008",
            "sw-2026-008",
            "S-2026-001",
        ],
    )
    def test_invalid_format_returns_empty(self, project_id: str) -> None:
        """无效格式应返回空字符串"""
        assert extract_business_line(project_id) == ""

    def test_two_letter_prefix(self) -> None:
        """2位字母前缀（最小长度）"""
        assert extract_business_line("SW-2026-008") == "SW"

    def test_three_letter_prefix_non_business(self) -> None:
        """3位字母前缀但非合法业务线（如 ABC）应返回空字符串"""
        # ABC 不是合法业务线（SW/DJ/ZD/XT/WX），返回空
        assert extract_business_line("ABC-2026-001") == ""

    def test_four_letter_prefix_non_business(self) -> None:
        """4位字母前缀但非合法业务线（如 ABCD）应返回空字符串"""
        # ABCD 不是合法业务线，返回空
        assert extract_business_line("ABCD-2026-001") == ""

    def test_five_letter_prefix_truncated(self) -> None:
        """5位字母前缀：正则 {2,4} 不匹配5位，返回空"""
        # 正则为 ^([A-Z]{2,4})-\d{4}-\d{3}
        # ABCDE 不在 {2,4} 范围，不匹配
        assert extract_business_line("ABCDE-2026-001") == ""

    def test_extra_suffix_ignored(self) -> None:
        """编号后缀额外内容不影响前缀提取"""
        assert extract_business_line("SW-2026-008_extra") == "SW"


# ── Project 模型 business_line 字段测试 ──────────────────


class TestProjectBusinessLineField:
    """Project 模型的 business_line 字段测试"""

    def test_create_project_with_business_line(self) -> None:
        """创建 Project 时可设置 business_line"""
        proj = Project(
            project_id="SW-2026-008",
            name="测试项目",
            path="/tmp/test",
            business_line="SW",
        )
        assert proj.business_line == "SW"

    def test_business_line_default_empty(self) -> None:
        """business_line 默认为空字符串"""
        proj = Project(
            project_id="SW-2026-008",
            name="测试项目",
            path="/tmp/test",
        )
        assert proj.business_line == ""

    def test_business_line_all_values(self) -> None:
        """所有业务线值均可设置"""
        for bl in ("SW", "DJ", "ZD", "XT", "WX", ""):
            proj = Project(
                project_id=f"{bl or 'SW'}-2026-001" if bl else "SW-2026-001",
                name="测试",
                path="/tmp/test",
                business_line=bl,
            )
            assert proj.business_line == bl


# ── DB 往返测试 ──────────────────────────────────────────


class TestBusinessLineDbRoundtrip:
    """business_line 字段 DB upsert/get 往返测试"""

    @pytest.fixture
    def repo(self, tmp_path: Path) -> ProjectRepository:
        db = DatabaseManager(str(tmp_path))
        db.init_schema()
        return ProjectRepository(db)

    @staticmethod
    def _make_record(
        project_id: str = "SW-2026-001",
        business_line: str = "SW",
    ) -> ProjectRecord:
        return ProjectRecord(
            project_id=project_id,
            name="测试项目",
            path=f"/tmp/{project_id}",
            stack="plc",
            version="V1.0.0",
            description="测试",
            source="copier",
            phase="developing",
            business_line=business_line,
            extra={},
            file_mtime=1000.0,
            last_scanned="2026-01-01T00:00:00",
        )

    def test_upsert_get_preserves_business_line(self, repo: ProjectRepository) -> None:
        """UPSERT 后查询应保持 business_line 字段"""
        repo.upsert(self._make_record("SW-2026-001", "SW"))

        result = repo.get_by_id("SW-2026-001")
        assert result is not None
        assert result.business_line == "SW"

    def test_business_line_roundtrip_all_values(
        self, repo: ProjectRepository
    ) -> None:
        """所有业务线值 DB 往返保持一致"""
        cases = [
            ("SW-2026-001", "SW"),
            ("DJ-2026-001", "DJ"),
            ("ZD-2026-001", "ZD"),
            ("XT-2026-001", "XT"),
            ("WX-2026-001", "WX"),
        ]
        for project_id, bl in cases:
            repo.upsert(self._make_record(project_id, bl))

        for project_id, bl in cases:
            result = repo.get_by_id(project_id)
            assert result is not None
            assert result.business_line == bl

    def test_empty_business_line_roundtrip(self, repo: ProjectRepository) -> None:
        """空 business_line 也能正确往返"""
        repo.upsert(self._make_record("SW-2026-001", ""))

        result = repo.get_by_id("SW-2026-001")
        assert result is not None
        assert result.business_line == ""


# ── list_by_business_line 查询测试 ───────────────────────


class TestListByBusinessLine:
    """list_by_business_line 查询测试"""

    @pytest.fixture
    def repo(self, tmp_path: Path) -> ProjectRepository:
        db = DatabaseManager(str(tmp_path))
        db.init_schema()
        return ProjectRepository(db)

    def _seed_projects(self, repo: ProjectRepository) -> None:
        """填充多条不同业务线的项目"""
        cases = [
            ("SW-2026-001", "SW"),
            ("SW-2026-002", "SW"),
            ("DJ-2026-001", "DJ"),
            ("ZD-2026-001", "ZD"),
        ]
        for project_id, bl in cases:
            repo.upsert(
                ProjectRecord(
                    project_id=project_id,
                    name=f"项目_{project_id}",
                    path=f"/tmp/{project_id}",
                    stack="plc",
                    version="V1.0.0",
                    description="",
                    source="copier",
                    phase="developing",
                    business_line=bl,
                    extra={},
                    file_mtime=0,
                    last_scanned="",
                )
            )

    def test_list_by_sw(self, repo: ProjectRepository) -> None:
        """按 SW 业务线筛选应返回2条"""
        self._seed_projects(repo)
        results = repo.list_by_business_line("SW")
        assert len(results) == 2
        assert all(r.business_line == "SW" for r in results)
        # 应按 project_id 排序
        assert results[0].project_id == "SW-2026-001"
        assert results[1].project_id == "SW-2026-002"

    def test_list_by_dj(self, repo: ProjectRepository) -> None:
        """按 DJ 业务线筛选应返回1条"""
        self._seed_projects(repo)
        results = repo.list_by_business_line("DJ")
        assert len(results) == 1
        assert results[0].project_id == "DJ-2026-001"

    def test_list_by_empty_business_line(self, repo: ProjectRepository) -> None:
        """空 business_line 查询应返回未设置业务线的项目"""
        repo.upsert(
            ProjectRecord(
                project_id="XX-2026-001",
                name="无业务线项目",
                path="/tmp/xx",
                stack="unknown",
                version="",
                description="",
                source="dirname",
                phase="",
                business_line="",
                extra={},
                file_mtime=0,
                last_scanned="",
            )
        )
        results = repo.list_by_business_line("")
        assert len(results) == 1
        assert results[0].business_line == ""

    def test_list_by_nonexistent_business_line(
        self, repo: ProjectRepository
    ) -> None:
        """查询不存在的业务线应返回空列表"""
        self._seed_projects(repo)
        results = repo.list_by_business_line("XX")
        assert results == []
