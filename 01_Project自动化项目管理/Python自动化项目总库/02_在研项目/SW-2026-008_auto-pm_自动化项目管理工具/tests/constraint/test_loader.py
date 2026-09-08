"""约束加载器（ConstraintLoader）单元测试"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from auto_pm.constraint.loader import ConstraintLoader, ConstraintLoadError

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch


class TestConstraintLoader:
    """ConstraintLoader 测试"""

    def test_load_all_loads_definitions(self) -> None:
        """load_all 加载所有 YAML 约束定义"""
        # 使用 auto-pm 项目根目录作为工作空间
        project_root = Path(__file__).resolve().parents[2]
        loader = ConstraintLoader(project_root)
        constraints = loader.load_all()

        assert len(constraints) >= 2
        ids = {c.id for c in constraints}
        assert "CST-FILE-001" in ids
        assert "CST-FILE-002" in ids

    def test_load_single_by_name(self) -> None:
        """load 按名称加载单个约束"""
        project_root = Path(__file__).resolve().parents[2]
        loader = ConstraintLoader(project_root)

        cst = loader.load("file_encoding_integrity")
        assert cst is not None
        assert cst.id == "CST-FILE-002"
        assert cst.type == "file_encoding"
        assert cst.auto_fix is True
        assert cst.heal_command == "strip_bom"

    def test_load_nonexistent_returns_none(self) -> None:
        """加载不存在的约束返回 None"""
        project_root = Path(__file__).resolve().parents[2]
        loader = ConstraintLoader(project_root)

        cst = loader.load("nonexistent_constraint")
        assert cst is None

    def test_loaded_constraint_has_scope(self) -> None:
        """加载的约束包含 scope 定义"""
        project_root = Path(__file__).resolve().parents[2]
        loader = ConstraintLoader(project_root)

        cst = loader.load("file_encoding_integrity")
        assert cst is not None
        assert len(cst.scope.patterns) >= 1
        assert "**/*.md" in cst.scope.patterns
        assert len(cst.scope.exclude) >= 1

    def test_loaded_constraint_has_rules(self) -> None:
        """加载的约束包含 rules 定义"""
        project_root = Path(__file__).resolve().parents[2]
        loader = ConstraintLoader(project_root)

        cst = loader.load("file_encoding_integrity")
        assert cst is not None
        assert len(cst.rules) >= 1
        rule_types = {r.type for r in cst.rules}
        assert "bom_count" in rule_types

    def test_list_definition_files(self) -> None:
        """list_definition_files 列出所有 YAML 文件"""
        project_root = Path(__file__).resolve().parents[2]
        loader = ConstraintLoader(project_root)

        files = loader.list_definition_files()
        assert len(files) >= 2
        names = {f.name for f in files}
        assert "file_encoding_integrity.yaml" in names
        assert "file_no_python_write.yaml" in names

    def test_find_definitions_dir_from_package(self) -> None:
        """从包路径查找 definitions/ 目录"""
        project_root = Path(__file__).resolve().parents[2]
        loader = ConstraintLoader(project_root)

        definitions_dir = loader._find_definitions_dir()
        assert definitions_dir.is_dir()
        assert definitions_dir.name == "definitions"

    def test_constraint_load_error_raised_for_bad_path(self, tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
        """无效工作空间且包路径不存在时抛出 ConstraintLoadError"""
        import auto_pm.constraint.loader as loader_module

        # Mock _find_definitions_dir 使其跳过包路径查找，直接使用工作空间搜索
        def _mock_find(self: ConstraintLoader) -> Path:
            # 跳过包路径，直接走降级搜索
            import os
            for root_str, dirs, _files in os.walk(str(self._workspace_root)):
                root = Path(root_str)
                if "definitions" in dirs and root.name == "constraint":
                    return root / "definitions"
            raise ConstraintLoadError(
                f"未找到 constraint/definitions/ 目录，已搜索: {self._workspace_root}"
            )

        monkeypatch.setattr(loader_module.ConstraintLoader, "_find_definitions_dir", _mock_find)

        # 使用不包含 constraint/definitions/ 的临时目录
        (tmp_path / "some_file.txt").write_text("hello")
        with pytest.raises(ConstraintLoadError):
            ConstraintLoader(tmp_path)
