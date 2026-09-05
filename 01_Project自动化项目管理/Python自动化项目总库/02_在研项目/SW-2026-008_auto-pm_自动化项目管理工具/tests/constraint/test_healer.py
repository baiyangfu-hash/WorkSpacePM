"""ConstraintHealer 单元测试 - Phase 2"""

from __future__ import annotations

from pathlib import Path

import pytest
from auto_pm.constraint.guard import BOM
from auto_pm.constraint.healer import ConstraintHealer


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    return tmp_path


class TestConstraintHealer:
    def test_heal_file_bom_dry_run(self, temp_workspace: Path) -> None:
        """heal_file dry-run 模式预览修复结果但不更改文件"""
        bad_file = temp_workspace / "bad.md"
        bad_file.write_bytes(BOM * 5 + b"# Bad")

        healer = ConstraintHealer(temp_workspace)
        results = healer.heal_file(bad_file, dry_run=True)

        assert len(results) == 1
        assert results[0]["dry_run"] is True
        assert results[0]["bom_before"] == 5
        assert bad_file.read_bytes().startswith(BOM * 5)

    def test_heal_file_bom_real(self, temp_workspace: Path) -> None:
        """heal_file 正式剥离 BOM"""
        bad_file = temp_workspace / "bad.md"
        bad_file.write_bytes(BOM * 5 + b"# Bad")

        healer = ConstraintHealer(temp_workspace)
        results = healer.heal_file(bad_file, dry_run=False)

        assert len(results) == 1
        assert results[0]["dry_run"] is False
        assert bad_file.read_bytes() == b"# Bad"

    def test_heal_all(self, temp_workspace: Path) -> None:
        """heal_all 批处理修复工作空间中的问题文件"""
        f1 = temp_workspace / "f1.md"
        f1.write_bytes(BOM * 3 + b"Content 1")
        f2 = temp_workspace / "f2.md"
        f2.write_bytes(BOM * 2 + b"Content 2")

        healer = ConstraintHealer(temp_workspace)
        results = healer.heal_all(dry_run=False)

        assert len(results) == 2
        assert f1.read_bytes() == b"Content 1"
        assert f2.read_bytes() == b"Content 2"
