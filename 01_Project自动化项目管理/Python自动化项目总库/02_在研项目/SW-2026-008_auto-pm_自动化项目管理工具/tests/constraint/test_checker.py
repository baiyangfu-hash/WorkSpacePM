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


class TestVersionSuffixScopeCoversEveryProjectDocDirectory:
    """CST-NAME-001 的检查范围：fnmatch 的 `**` 不能跨层，所以写成 `**/<目录>/*.md`（审计 242）。"""

    @staticmethod
    def _flagged(root: Path, relative: str, *, create: bool = True) -> bool:
        target = root / relative
        if create:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# doc", encoding="utf-8")
        violations = ConstraintChecker(root).check_file(target)
        return any(v.constraint_id == "CST-NAME-001" for v in violations)

    @pytest.mark.parametrize("directory", ["00_项目管理", "00_项目基础信息", "01_启动"])
    def test_files_directly_under_the_directory_are_checked_when_root_is_the_project(
        self, tmp_path: Path, directory: str
    ) -> None:
        assert self._flagged(tmp_path, f"{directory}/设计说明书_V2.0.md")
        assert not self._flagged(tmp_path, f"{directory}/ok.md")

    @pytest.mark.parametrize("directory", ["00_项目管理", "00_项目基础信息", "01_启动"])
    def test_nested_files_are_checked(self, tmp_path: Path, directory: str) -> None:
        assert self._flagged(tmp_path, f"{directory}/子目录/说明_V1.1.md")

    @pytest.mark.parametrize("directory", ["00_项目管理", "00_项目基础信息", "01_启动"])
    def test_projects_below_the_workspace_root_are_checked_too(
        self, tmp_path: Path, directory: str
    ) -> None:
        """工作区根在仓库根、项目在下面几层时也要检查到（用户从仓库根运行的情形）。"""
        assert self._flagged(tmp_path, f"组/DJ-2026-001/{directory}/说明_V3.0.md")

    def test_the_execution_process_directory_stays_excluded(self, tmp_path: Path) -> None:
        assert not self._flagged(tmp_path, "01_启动/03_执行过程/记录_V1.0.md")
        assert not self._flagged(tmp_path, "组/DJ-2026-001/00_项目管理/03_执行过程/记录_V1.0.md")

    def test_unrelated_directories_are_not_checked(self, tmp_path: Path) -> None:
        assert not self._flagged(tmp_path, "docs/说明_V1.0.md")
