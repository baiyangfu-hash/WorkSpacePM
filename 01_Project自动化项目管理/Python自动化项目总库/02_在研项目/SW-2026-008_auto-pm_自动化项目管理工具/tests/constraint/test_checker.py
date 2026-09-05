"""ConstraintChecker 单元测试 - Phase 2"""

from __future__ import annotations

from pathlib import Path

import pytest
from auto_pm.constraint.checker import ConstraintChecker
from auto_pm.constraint.guard import BOM


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    return tmp_path


class TestConstraintChecker:
    def test_check_all_clean(self, temp_workspace: Path) -> None:
        """干净工作空间扫描无违规"""
        clean_file = temp_workspace / "clean.md"
        clean_file.write_text("# Hello", encoding="utf-8")

        checker = ConstraintChecker(temp_workspace)
        report = checker.check_all()

        non_env_violations = [v for v in report.violations_list if v.constraint_id != "CST-ENV-001"]
        assert len(non_env_violations) == 0
        assert report.total >= 8

    def test_check_naming_violation(self, temp_workspace: Path) -> None:
        """检测包含版本号后缀的文件名违规 (CST-NAME-001)"""
        doc_dir = temp_workspace / "00_项目管理" / "01_文档"
        doc_dir.mkdir(parents=True, exist_ok=True)
        bad_doc = doc_dir / "设计说明书_V1.0.md"
        bad_doc.write_text("# Doc", encoding="utf-8")

        checker = ConstraintChecker(temp_workspace)
        report = checker.check_all()

        assert report.violations >= 1
        cst_ids = [v.constraint_id for v in report.violations_list]
        assert "CST-NAME-001" in cst_ids

    def test_check_file_encoding_violation(self, temp_workspace: Path) -> None:
        """检测包含多余 BOM 的文件违规 (CST-FILE-002)"""
        bad_file = temp_workspace / "bad.md"
        bad_file.write_bytes(BOM * 5 + b"# Bad")

        checker = ConstraintChecker(temp_workspace)
        violations = checker.check_file(bad_file)

        assert len(violations) >= 1
        assert violations[0].constraint_id == "CST-FILE-002"
