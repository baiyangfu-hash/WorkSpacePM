"""文件守护（FileGuard）单元测试

测试 FileGuard 的快照管理、BOM 检测、编码检查和自愈能力。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from auto_pm.constraint.guard import BOM, FileGuard


class TestFileGuardSnapshot:
    """快照管理测试"""

    def test_take_snapshot_creates_snapshot(self, tmp_path: Path) -> None:
        """take_snapshot 创建快照"""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Hello", encoding="utf-8")

        guard = FileGuard(tmp_path)
        snap = guard.take_snapshot(test_file)

        assert snap["file_path"] == str(test_file)
        assert len(snap["snapshot_id"]) == 12
        assert len(snap["sha256"]) == 64
        assert snap["size"] == len(b"# Hello")
        assert snap["bom_count"] == 0
        assert "taken_at" in snap

    def test_take_snapshot_file_not_found(self, tmp_path: Path) -> None:
        """take_snapshot 对不存在的文件抛出 FileNotFoundError"""
        guard = FileGuard(tmp_path)
        with pytest.raises(FileNotFoundError):
            guard.take_snapshot(tmp_path / "nonexistent.md")

    def test_verify_snapshot_no_change(self, tmp_path: Path) -> None:
        """文件未修改时 verify_snapshot 返回 verified=True"""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Hello", encoding="utf-8")

        guard = FileGuard(tmp_path)
        guard.take_snapshot(test_file)
        result = guard.verify_snapshot(test_file)

        assert result["verified"] is True
        assert result["hash_changed"] is False
        assert result["size_delta"] == 0
        assert result["bom_accumulated"] is False

    def test_verify_snapshot_detects_change(self, tmp_path: Path) -> None:
        """文件被修改后 verify_snapshot 检测到变更"""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Hello", encoding="utf-8")

        guard = FileGuard(tmp_path)
        guard.take_snapshot(test_file)

        # 修改文件
        test_file.write_text("# Hello World", encoding="utf-8")
        result = guard.verify_snapshot(test_file)

        assert result["verified"] is False
        assert result["hash_changed"] is True

    def test_verify_snapshot_no_snapshot(self, tmp_path: Path) -> None:
        """无快照时 verify_snapshot 返回 error=no_snapshot"""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Hello", encoding="utf-8")

        guard = FileGuard(tmp_path)
        result = guard.verify_snapshot(test_file)

        assert result["verified"] is False
        assert result["error"] == "no_snapshot"

    def test_has_snapshot(self, tmp_path: Path) -> None:
        """has_snapshot 正确反映快照存在状态"""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Hello", encoding="utf-8")

        guard = FileGuard(tmp_path)
        assert guard.has_snapshot(test_file) is False

        guard.take_snapshot(test_file)
        assert guard.has_snapshot(test_file) is True


class TestFileGuardBOM:
    """BOM 检测与自愈测试"""

    def test_count_bom_zero(self) -> None:
        """无 BOM 文件返回 0"""
        raw = b"# Hello World\n"
        assert FileGuard._count_bom(raw) == 0

    def test_count_bom_one(self) -> None:
        """1 个 BOM 文件返回 1"""
        raw = BOM + b"# Hello World\n"
        assert FileGuard._count_bom(raw) == 1

    def test_count_bom_multiple(self) -> None:
        """多个 BOM 文件返回正确计数"""
        raw = BOM * 3 + b"# Hello World\n"
        assert FileGuard._count_bom(raw) == 3

    def test_count_bom_146(self) -> None:
        """146 个 BOM（真实案例）"""
        raw = BOM * 146 + b"# Hello World\n"
        assert FileGuard._count_bom(raw) == 146

    def test_check_encoding_healthy(self, tmp_path: Path) -> None:
        """无 BOM 文件 check_encoding 返回 is_healthy=True"""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Hello", encoding="utf-8")

        guard = FileGuard(tmp_path)
        result = guard.check_encoding(test_file)

        assert result["is_healthy"] is True
        assert result["bom_count"] == 0
        assert result["bom_ok"] is True
        assert result["has_null_byte"] is False

    def test_check_encoding_bom_detected(self, tmp_path: Path) -> None:
        """多 BOM 文件 check_encoding 返回 is_healthy=False"""
        test_file = tmp_path / "test.md"
        test_file.write_bytes(BOM * 5 + b"# Hello")

        guard = FileGuard(tmp_path)
        result = guard.check_encoding(test_file)

        assert result["is_healthy"] is False
        assert result["bom_count"] == 5
        assert result["bom_ok"] is False

    def test_check_encoding_null_byte(self, tmp_path: Path) -> None:
        """含 NUL 字节文件 check_encoding 返回 is_healthy=False"""
        test_file = tmp_path / "test.md"
        test_file.write_bytes(b"# Hello\x00World")

        guard = FileGuard(tmp_path)
        result = guard.check_encoding(test_file)

        assert result["is_healthy"] is False
        assert result["has_null_byte"] is True

    def test_heal_bom_strips_excess(self, tmp_path: Path) -> None:
        """heal_bom 剥离多余 BOM"""
        test_file = tmp_path / "test.md"
        content = b"# Hello World\n"
        test_file.write_bytes(BOM * 10 + content)

        guard = FileGuard(tmp_path)
        result = guard.heal_bom(test_file)

        assert result["healed"] is True
        assert result["bom_before"] == 10
        assert result["bom_after"] == 0
        assert result["bytes_removed"] == len(BOM) * 10

        # 验证文件内容正确
        assert test_file.read_bytes() == content

    def test_heal_bom_no_heal_needed(self, tmp_path: Path) -> None:
        """BOM 数量正常时 heal_bom 返回 healed=False"""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Hello", encoding="utf-8")

        guard = FileGuard(tmp_path)
        result = guard.heal_bom(test_file)

        assert result["healed"] is False
        assert "无需修复" in result["message"]

    def test_heal_bom_one_bom_acceptable(self, tmp_path: Path) -> None:
        """1 个 BOM 视为可接受，不修复"""
        test_file = tmp_path / "test.md"
        test_file.write_bytes(BOM + b"# Hello")

        guard = FileGuard(tmp_path)
        result = guard.heal_bom(test_file)

        assert result["healed"] is False
        assert "无需修复" in result["message"]

    def test_snapshot_includes_bom_count(self, tmp_path: Path) -> None:
        """快照记录 BOM 数量"""
        test_file = tmp_path / "test.md"
        test_file.write_bytes(BOM * 3 + b"# Hello")

        guard = FileGuard(tmp_path)
        snap = guard.take_snapshot(test_file)

        assert snap["bom_count"] == 3

    def test_verify_detects_bom_accumulation(self, tmp_path: Path) -> None:
        """verify_snapshot 检测 BOM 累积"""
        test_file = tmp_path / "test.md"
        test_file.write_bytes(b"# Hello")

        guard = FileGuard(tmp_path)
        guard.take_snapshot(test_file)

        # 追加 BOM（模拟外部脚本用 utf-8-sig 写入）
        test_file.write_bytes(BOM * 5 + b"# Hello")
        result = guard.verify_snapshot(test_file)

        assert result["bom_accumulated"] is True
        assert result["bom_delta"] == 5
