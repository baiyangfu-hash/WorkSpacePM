"""Bug-1 回归测试: _get_project_path 路径假设错误

问题: ChangeService._get_project_path 假设目录名 == project_id，
      实际项目目录命名为 {project_id}_{project_name}（见 cmd_create）。
修复: 支持 {project_id}_ 前缀匹配，同时保留精确匹配向后兼容。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from auto_pm.change.change_service import ChangeService


@pytest.fixture
def workspace(tmp_path: Path) -> str:
    """临时工作空间"""
    return str(tmp_path)


class TestGetProjectPathPrefixMatch:
    """_get_project_path 前缀匹配测试"""

    def test_prefix_match_project_id_underscore_name(self, workspace: str, tmp_path: Path) -> None:
        """目录名为 {project_id}_{project_name} 时应正确匹配"""
        project_id = "SW-2026-008"
        project_name = "auto-pm"
        project_dir = tmp_path / f"{project_id}_{project_name}"
        project_dir.mkdir()

        svc = ChangeService(workspace)
        result = svc._get_project_path(project_id)

        assert result is not None
        assert os.path.isdir(result)
        assert result.endswith(f"{project_id}_{project_name}")

    def test_prefix_match_with_chinese_name(self, workspace: str, tmp_path: Path) -> None:
        """project_name 含中文字符时应正确匹配"""
        project_id = "DJ-2026-010"
        project_name = "边框缓存机"
        project_dir = tmp_path / f"{project_id}_{project_name}"
        project_dir.mkdir()

        svc = ChangeService(workspace)
        result = svc._get_project_path(project_id)

        assert result is not None
        assert os.path.isdir(result)

    def test_prefix_match_with_special_chars(self, workspace: str, tmp_path: Path) -> None:
        """project_name 含特殊字符（空格、连字符、下划线）时应正确匹配"""
        project_id = "SW-2026-009"
        project_name = "my project_v2.0"
        project_dir = tmp_path / f"{project_id}_{project_name}"
        project_dir.mkdir()

        svc = ChangeService(workspace)
        result = svc._get_project_path(project_id)

        assert result is not None
        assert os.path.isdir(result)

    def test_prefix_match_with_long_name(self, workspace: str, tmp_path: Path) -> None:
        """project_name 含多段下划线时应正确匹配（前缀匹配不误判）"""
        project_id = "SW-2026-008"
        # 模拟实际目录名: SW-2026-008_auto-pm_自动化项目管理工具
        project_dir = tmp_path / f"{project_id}_auto-pm_自动化项目管理工具"
        project_dir.mkdir()

        svc = ChangeService(workspace)
        result = svc._get_project_path(project_id)

        assert result is not None
        assert os.path.isdir(result)


class TestGetProjectPathExactMatch:
    """_get_project_path 精确匹配（向后兼容）测试"""

    def test_exact_match(self, workspace: str, tmp_path: Path) -> None:
        """目录名 == project_id 时应精确匹配（向后兼容）"""
        project_id = "TEST-2026-001"
        (tmp_path / project_id).mkdir()

        svc = ChangeService(workspace)
        result = svc._get_project_path(project_id)

        assert result is not None
        assert result.endswith(project_id)

    def test_exact_match_takes_priority(self, workspace: str, tmp_path: Path) -> None:
        """同时存在精确匹配和前缀匹配时，优先精确匹配"""
        project_id = "TEST-2026-001"
        exact_dir = tmp_path / project_id
        exact_dir.mkdir()
        prefix_dir = tmp_path / f"{project_id}_其他项目"
        prefix_dir.mkdir()

        svc = ChangeService(workspace)
        result = svc._get_project_path(project_id)

        assert result is not None
        assert result == str(exact_dir)


class TestGetProjectPathNoFalseMatch:
    """_get_project_path 不应误匹配"""

    def test_no_false_match_similar_id(self, workspace: str, tmp_path: Path) -> None:
        """SW-2026-008 不应匹配 SW-2026-0080_x（下划线分隔符防止误匹配）"""
        project_id = "SW-2026-008"
        # 0080 不是 008，不应匹配
        (tmp_path / "SW-2026-0080_其他项目").mkdir()

        svc = ChangeService(workspace)
        result = svc._get_project_path(project_id)

        assert result is None

    def test_no_false_match_partial_id(self, workspace: str, tmp_path: Path) -> None:
        """SW-2026-00 不应匹配 SW-2026-008_x（前缀不完整）"""
        project_id = "SW-2026-00"
        (tmp_path / "SW-2026-008_项目").mkdir()

        svc = ChangeService(workspace)
        result = svc._get_project_path(project_id)

        assert result is None

    def test_not_found(self, workspace: str) -> None:
        """不存在的项目返回 None"""
        svc = ChangeService(workspace)
        assert svc._get_project_path("NONEXISTENT-9999") is None

    def test_nonexistent_workspace(self, tmp_path: Path) -> None:
        """工作空间目录不存在时返回 None"""
        svc = ChangeService(str(tmp_path / "nonexistent"))
        assert svc._get_project_path("SW-2026-008") is None


class TestGetProjectPathIntegration:
    """_get_project_path 集成测试: list_change_requests 端到端"""

    def test_list_changes_with_prefix_named_project(self, workspace: str, tmp_path: Path) -> None:
        """目录名为 {project_id}_{project_name} 时 list_change_requests 应能找到变更单"""
        project_id = "SW-2026-008"
        project_dir = tmp_path / f"{project_id}_auto-pm"
        # 创建变更单目录结构
        chg_dir = project_dir / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-DOCU"
        chg_dir.mkdir(parents=True)
        # 写入一个最小变更单文件
        (chg_dir / "CHG-DOCU-2026-001.md").write_text(
            "# 变更单\n\n"
            "## 3. 变更基本信息\n\n"
            "### 3.0 编号与项目\n"
            "| 字段 | 内容 |\n|------|------|\n"
            "| 变更编号 | CHG-DOCU-2026-001 |\n"
            f"| 项目编号 | {project_id} |\n\n"
            "### 3.1 技术领域（必选）\n"
            "| 领域 | 选择 |\n|------|------|\n"
            "| ☑ **DOCU** 工程文档 | **选中** |\n\n"
            "### 3.2 业务性质（必选）\n"
            "| 性质 | 选择 |\n|------|------|\n"
            "| ☑ **DEF** 缺陷修复 | **选中** |\n\n"
            "### 3.3 影响范围（可多选）\n"
            "| 范围 | 选择 |\n|------|------|\n"
            "| ☑ **LOCAL** 局部变更 | **选中** |\n\n"
            "### 3.4 申请信息\n"
            "| 字段 | 内容 |\n|------|------|\n"
            "| 变更申请人 | 测试 |\n"
            "| 申请日期 | 2026-01-01 |\n",
            encoding="utf-8",
        )

        svc = ChangeService(workspace)
        # 修复前: _get_project_path 返回 None → list_change_requests 返回 []
        # 修复后: 前缀匹配成功 → 返回变更单列表
        changes = svc.list_change_requests(project_id)

        assert len(changes) == 1
        assert changes[0].change_number == "CHG-DOCU-2026-001"
