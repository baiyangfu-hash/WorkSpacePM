"""变更管理路径解析测试"""

from __future__ import annotations

from pathlib import Path

import pytest
from auto_pm.change.path_resolver import (
    PathTraversalError,
    extract_domain_from_change_number,
    find_ledger_file,
    find_proj_file,
    get_project_id_from_path,
    scan_change_files,
    validate_change_number,
    validate_path_within_workspace,
    validate_project_id,
)

# ── 安全校验测试 ──────────────────────────────────────


class TestValidateProjectId:
    """项目编号校验测试"""

    def test_valid_id(self) -> None:
        """合法项目编号"""
        assert validate_project_id("DJ-2026-005") == "DJ-2026-005"

    def test_empty_id(self) -> None:
        """空编号抛异常"""
        with pytest.raises(PathTraversalError, match="不能为空"):
            validate_project_id("")

    def test_invalid_chars(self) -> None:
        """非法字符抛异常"""
        with pytest.raises(PathTraversalError, match="非法字符"):
            validate_project_id("DJ/2026-005")

    def test_path_traversal_dotdot(self) -> None:
        """路径遍历 .. 抛异常（先命中非法字符检查）"""
        with pytest.raises(PathTraversalError, match="非法字符"):
            validate_project_id("../etc/passwd")

    def test_path_traversal_slash(self) -> None:
        """路径遍历 / 抛异常（先命中非法字符检查）"""
        with pytest.raises(PathTraversalError, match="非法字符"):
            validate_project_id("foo/bar")

    def test_path_traversal_backslash(self) -> None:
        """路径遍历 \\ 抛异常（先命中非法字符检查）"""
        with pytest.raises(PathTraversalError, match="非法字符"):
            validate_project_id("foo\\bar")

    def test_underscore_allowed(self) -> None:
        """下划线允许"""
        assert validate_project_id("FB_1011") == "FB_1011"


class TestValidateChangeNumber:
    """变更编号校验测试"""

    def test_valid_number(self) -> None:
        """合法变更编号"""
        assert validate_change_number("CHG-PLC-2026-001") == "CHG-PLC-2026-001"

    def test_empty_number(self) -> None:
        """空编号抛异常"""
        with pytest.raises(PathTraversalError, match="不能为空"):
            validate_change_number("")

    def test_invalid_format(self) -> None:
        """格式不合法抛异常"""
        with pytest.raises(PathTraversalError, match="格式不合法"):
            validate_change_number("INVALID")

    def test_lowercase_domain(self) -> None:
        """小写领域不合法"""
        with pytest.raises(PathTraversalError, match="格式不合法"):
            validate_change_number("CHG-plc-2026-001")


class TestValidatePathWithinWorkspace:
    """路径范围校验测试"""

    def test_path_within_workspace(self, tmp_path: Path) -> None:
        """工作空间内路径"""
        result = validate_path_within_workspace(str(tmp_path / "subdir"), str(tmp_path))
        assert result is not None

    def test_path_outside_workspace(self, tmp_path: Path) -> None:
        """工作空间外路径抛异常"""
        with pytest.raises(PathTraversalError, match="超出工作空间范围"):
            validate_path_within_workspace("/etc/passwd", str(tmp_path))


# ── 目录约定测试 ──────────────────────────────────────


class TestFindProjFile:
    """立项表查找测试"""

    def test_find_proj_file_plc_convention(self, tmp_path: Path) -> None:
        """PLC 项目约定路径"""
        proj_dir = tmp_path / "01_启动"
        proj_dir.mkdir(parents=True)
        (proj_dir / "DJ-2026-005_PROJ.md").write_text("# 立项表\n", encoding="utf-8")

        result = find_proj_file(str(tmp_path))
        assert result is not None
        assert "DJ-2026-005_PROJ.md" in result

    def test_find_proj_file_python_convention(self, tmp_path: Path) -> None:
        """Python 项目约定路径"""
        proj_dir = tmp_path / "01_启动"
        proj_dir.mkdir(parents=True)
        (proj_dir / "立项表_SW-2026-008.md").write_text("# 立项表\n", encoding="utf-8")

        result = find_proj_file(str(tmp_path))
        assert result is not None
        assert "立项表_SW-2026-008.md" in result

    def test_find_proj_file_not_found(self, tmp_path: Path) -> None:
        """无立项表返回 None"""
        result = find_proj_file(str(tmp_path))
        assert result is None


class TestScanChangeFiles:
    """变更单文件扫描测试"""

    def test_scan_plc_convention(self, tmp_path: Path) -> None:
        """PLC 项目变更单目录"""
        chg_dir = tmp_path / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-PLC"
        chg_dir.mkdir(parents=True)
        (chg_dir / "CHG-PLC-2026-001.md").write_text("# 变更单\n", encoding="utf-8")

        results = scan_change_files(str(tmp_path))
        assert len(results) == 1
        assert "CHG-PLC-2026-001.md" in results[0]

    def test_scan_no_change_dir(self, tmp_path: Path) -> None:
        """无变更单目录返回空列表"""
        results = scan_change_files(str(tmp_path))
        assert results == []


class TestFindLedgerFile:
    """台帐文件查找测试"""

    def test_find_ledger_file(self, tmp_path: Path) -> None:
        """存在台帐文件"""
        ledger_dir = tmp_path / "04_监控" / "01_变更管理" / "02_变更记录"
        ledger_dir.mkdir(parents=True)
        (ledger_dir / "01_版本变更台帐.md").write_text("# 台帐\n", encoding="utf-8")

        result = find_ledger_file(str(tmp_path))
        assert result is not None
        assert "01_版本变更台帐.md" in result

    def test_find_ledger_file_in_11_monitoring(self, tmp_path: Path) -> None:
        """兼容在 11_监控 目录下的台帐文件"""
        ledger_dir = tmp_path / "11_监控" / "01_变更管理" / "02_变更记录"
        ledger_dir.mkdir(parents=True)
        (ledger_dir / "01_版本变更台帐.md").write_text("# 台帐\n", encoding="utf-8")

        result = find_ledger_file(str(tmp_path))
        assert result is not None
        assert "01_版本变更台帐.md" in result

    def test_find_ledger_file_not_found(self, tmp_path: Path) -> None:
        """无台帐文件返回 None"""
        result = find_ledger_file(str(tmp_path))
        assert result is None


class TestExtractDomainFromChangeNumber:
    """变更编号领域提取测试"""

    def test_extract_domain(self) -> None:
        """提取领域"""
        assert extract_domain_from_change_number("CHG-PLC-2026-001") == "PLC"

    def test_extract_domain_docu(self) -> None:
        """提取 DOCU 领域"""
        assert extract_domain_from_change_number("CHG-DOCU-2026-001") == "DOCU"

    def test_extract_domain_short(self) -> None:
        """短编号返回空"""
        assert extract_domain_from_change_number("X") == ""


class TestGetProjectIdFromPath:
    """路径提取项目编号测试"""

    def test_extract_from_path(self) -> None:
        """从路径提取项目编号"""
        assert get_project_id_from_path("/workspace/DJ-2026-005") == "DJ-2026-005"

    def test_extract_from_nested_path(self) -> None:
        """从嵌套路径提取"""
        assert get_project_id_from_path("/a/b/c/FB_1011") == "FB_1011"
