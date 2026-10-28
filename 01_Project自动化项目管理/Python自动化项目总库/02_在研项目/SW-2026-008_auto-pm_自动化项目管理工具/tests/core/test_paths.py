"""统一路径约定测试（CHG-SCPT-2026-146 5大过程组重组）

验证 auto_pm.core.paths 模块的常量和便捷函数。
"""

from __future__ import annotations

import os
from pathlib import Path

from auto_pm.application.core.paths import (
    CHANGE_RECORDS_PATH,
    CHANGE_REQUESTS_PATH,
    CHANGE_SCAN_PATH,
    PG_CLOSING_DIR,
    PG_EXECUTING_DIR,
    PG_INITIATING_DIR,
    PG_MONITORING_DIR,
    PG_PLANNING_DIR,
    PLC_STD_DIRS,
    PRD_DIR,
    PROCESS_GROUP_DIRS,
    PROJECT_INIT_PATH,
    PYTHON_REQUIRED_DIRS,
    STD_PRD_DOCS,
    WORKSPACE_PROJECTS_SUBDIR,
    get_change_records_paths,
    get_change_requests_paths,
    get_prd_dir,
    get_projects_subdir,
)


class TestPathConstants:
    """路径常量定义测试"""

    def test_workspace_projects_subdir(self) -> None:
        """工作空间项目子目录常量"""
        assert WORKSPACE_PROJECTS_SUBDIR == "02_在研项目"

    def test_process_group_dirs(self) -> None:
        """5大过程组目录常量（CHG-SCPT-2026-146）"""
        assert PG_INITIATING_DIR == "01_启动"
        assert PG_PLANNING_DIR == "02_规划"
        assert PG_EXECUTING_DIR == "03_执行"
        assert PG_MONITORING_DIR == "04_监控"
        assert PG_CLOSING_DIR == "05_收尾"
        assert PROCESS_GROUP_DIRS == [
            "01_启动", "02_规划", "03_执行", "04_监控", "05_收尾"
        ]

    def test_plc_std_dirs(self) -> None:
        """PLC 标准目录列表"""
        assert "PRD" in PLC_STD_DIRS
        assert "03_HMI设计" in PLC_STD_DIRS
        assert "04_现场调试" in PLC_STD_DIRS

    def test_prd_dir(self) -> None:
        """PRD 目录名常量"""
        assert PRD_DIR == "PRD"

    def test_std_prd_docs(self) -> None:
        """标准 PRD 文档列表"""
        assert "需求分析文档_REQ.md" in STD_PRD_DOCS
        assert "接口文档_INT.md" in STD_PRD_DOCS
        assert "详细设计说明书_DSN.md" in STD_PRD_DOCS
        assert "技术方案文档_TEC.md" in STD_PRD_DOCS

    def test_change_requests_path(self) -> None:
        """变更单存放路径常量（5大过程组统一路径）"""
        assert CHANGE_REQUESTS_PATH == ["04_监控", "01_变更管理", "01_变更单"]

    def test_change_records_path(self) -> None:
        """变更记录存放路径常量（5大过程组统一路径）"""
        assert CHANGE_RECORDS_PATH == ["04_监控", "01_变更管理", "02_变更记录"]

    def test_change_scan_path(self) -> None:
        """变更单扫描路径常量（不含最后的 01_变更单）"""
        assert CHANGE_SCAN_PATH == ["04_监控", "01_变更管理"]

    def test_project_init_path(self) -> None:
        """立项表搜索路径常量"""
        assert PROJECT_INIT_PATH == ["01_启动"]

    def test_python_required_dirs(self) -> None:
        """Python 项目规范必需目录"""
        assert "tests" in PYTHON_REQUIRED_DIRS
        assert PG_INITIATING_DIR in PYTHON_REQUIRED_DIRS


class TestPathHelpers:
    """便捷函数测试"""

    def test_get_projects_subdir(self, tmp_path: Path) -> None:
        """获取工作空间下的项目目录路径"""
        result = get_projects_subdir(str(tmp_path))
        expected = os.path.join(str(tmp_path), "02_在研项目")
        assert result == expected

    def test_get_change_requests_paths(self, tmp_path: Path) -> None:
        """获取变更单存放目录路径候选：标准 04_监控 在前，旧布局 11_监控 在后（TD-SW008-191）"""
        paths = get_change_requests_paths(str(tmp_path))
        assert len(paths) == 2
        assert "04_监控" in paths[0]
        assert "01_变更管理" in paths[0]
        assert "01_变更单" in paths[0]
        assert "11_监控" in paths[1]
        assert paths[1].endswith(os.path.join("11_监控", "01_变更管理", "01_变更单"))

    def test_get_change_records_paths(self, tmp_path: Path) -> None:
        """获取变更记录存放目录路径（5大过程组统一路径，单元素）"""
        paths = get_change_records_paths(str(tmp_path))
        assert len(paths) == 1
        assert "04_监控" in paths[0]
        assert "02_变更记录" in paths[0]

    def test_get_prd_dir(self, tmp_path: Path) -> None:
        """获取 PRD 目录路径"""
        result = get_prd_dir(str(tmp_path))
        expected = os.path.join(str(tmp_path), "PRD")
        assert result == expected


class TestNoHardcodedPaths:
    """验证关键模块不再使用硬编码路径"""

    def test_file_locator_uses_constants(self) -> None:
        """ChangeFileLocator 使用 paths 常量而非硬编码"""
        from auto_pm.domain.change.file_locator import ChangeFileLocator

        # CHG-SCPT-2026-146: 5大过程组统一主路径与历史兼容路径
        # 注：file_locator 用 CHANGE_REQUESTS_PATH（含 01_变更单）直接定位文件，
        #     path_resolver 用 CHANGE_SCAN_PATH（不含 01_变更单）做递归扫描
        assert len(ChangeFileLocator.CHANGE_FILE_SEARCH_PATHS) == 3
        # 验证主路径内容正确
        expected_path = os.path.join(*CHANGE_REQUESTS_PATH)
        assert expected_path in ChangeFileLocator.CHANGE_FILE_SEARCH_PATHS
