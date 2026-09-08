"""归档管理器测试

覆盖 ArchiveManager 的核心功能：
- archive_delivery: 归档交付物 + archive_info.md 生成
- archive_package: 归档 ZIP + archive_manifest.md 更新
- list_archives: 列出归档
- restore_delivery: 恢复归档
- clean_archives: 清理旧归档
- get_current_version: 版本检测
- get_delivery_info / get_package_info: 状态查询
"""

from __future__ import annotations

from pathlib import Path

import pytest
from auto_pm.delivery.archive_manager import ArchiveManager
from auto_pm.delivery.constants import (
    ARCHIVE_INFO_FILENAME,
    ARCHIVE_MANIFEST_FILENAME,
    DIR_ARCHIVE,
    DIR_DELIVERY,
    DIR_EXECUTABLE,
    DIR_PACKAGE,
    DIR_RELEASE_NOTES,
    MB,
)

# ── fixtures ─────────────────────────────────────────────


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """创建模拟项目目录，含 06_交付物/（合并后 ZIP 也在该目录）"""
    project = tmp_path / "test_project"
    project.mkdir()

    # 06_交付物/（CHG-SCPT-2026-145 合并后 ZIP 与交付物内容同在此目录）
    delivery_dir = project / DIR_DELIVERY
    delivery_dir.mkdir()
    (delivery_dir / DIR_EXECUTABLE).mkdir()
    exe = delivery_dir / DIR_EXECUTABLE / "test.exe"
    exe.write_bytes(b"\x00" * (15 * MB))  # 15MB fake exe
    (delivery_dir / "README.md").write_text("# Test\n", encoding="utf-8")
    (delivery_dir / "CHANGELOG.md").write_text("## [1.0.0]\n- init\n", encoding="utf-8")
    (delivery_dir / DIR_RELEASE_NOTES).mkdir()

    # ZIP 文件直接放在 06_交付物/ 根目录（合并后不再有独立的 06_交付物打包/ 目录）
    zip_path = delivery_dir / "test_V1.0.0_20260701.zip"
    zip_path.write_bytes(b"\x00" * (2 * MB))  # 2MB fake zip

    return project


@pytest.fixture
def am(project_dir: Path) -> ArchiveManager:
    return ArchiveManager(project_dir)


# ── archive_delivery ─────────────────────────────────────


class TestArchiveDelivery:
    def test_archive_delivery_creates_archive_subdir(self, am: ArchiveManager) -> None:
        """归档后应在 archive/ 下创建子目录"""
        result = am.archive_delivery("V1.0.0", "V1.0.1", "升级测试")
        assert result is not None
        assert result.exists()
        assert result.parent.name == DIR_ARCHIVE

    def test_archive_delivery_generates_archive_info(self, am: ArchiveManager) -> None:
        """归档后应生成 archive_info.md"""
        result = am.archive_delivery("V1.0.0", "V1.0.1", "升级测试")
        assert result is not None
        info_file = result / ARCHIVE_INFO_FILENAME
        assert info_file.exists()
        content = info_file.read_text(encoding="utf-8")
        assert "V1.0.0" in content
        assert "V1.0.1" in content
        assert "升级测试" in content

    def test_archive_delivery_moves_files(self, am: ArchiveManager) -> None:
        """归档后根目录下原有文件应被移走"""
        result = am.archive_delivery("V1.0.0", "V1.0.1", "升级")
        assert result is not None

        # archive 子目录内应有原始内容
        assert (result / "README.md").exists()
        assert (result / DIR_EXECUTABLE).exists()

        # 根目录下不应再有 README.md（已被移走）
        delivery_dir = am._delivery_dir
        assert not (delivery_dir / "README.md").exists()

    def test_archive_delivery_empty_dir(self, tmp_path: Path) -> None:
        """空交付物目录应返回 None"""
        project = tmp_path / "empty"
        project.mkdir()
        (project / DIR_DELIVERY).mkdir()
        am = ArchiveManager(project)
        result = am.archive_delivery("V1.0.0", "V1.0.1")
        assert result is None

    def test_archive_delivery_no_delivery_dir(self, tmp_path: Path) -> None:
        """无交付物目录应返回 None"""
        project = tmp_path / "no_delivery"
        project.mkdir()
        am = ArchiveManager(project)
        result = am.archive_delivery("V1.0.0", "V1.0.1")
        assert result is None


# ── archive_package ──────────────────────────────────────


class TestArchivePackage:
    def test_archive_package_moves_zip(self, am: ArchiveManager) -> None:
        """归档 ZIP 应移动到 archive/ 下"""
        result = am.archive_package("V1.0.0", "V1.0.1", "打包升级")
        assert result is not None
        assert result.parent.name == DIR_ARCHIVE
        assert result.suffix == ".zip"

    def test_archive_package_updates_manifest(self, am: ArchiveManager) -> None:
        """归档 ZIP 后应更新 archive_manifest.md"""
        result = am.archive_package("V1.0.0", "V1.0.1", "打包升级")
        assert result is not None
        manifest = result.parent / ARCHIVE_MANIFEST_FILENAME
        assert manifest.exists()
        content = manifest.read_text(encoding="utf-8")
        assert "V1.0.0" in content

    def test_archive_package_no_zip(self, tmp_path: Path) -> None:
        """无 ZIP 时应返回 None"""
        project = tmp_path / "no_zip"
        project.mkdir()
        (project / DIR_PACKAGE).mkdir()
        am = ArchiveManager(project)
        result = am.archive_package("V1.0.0", "V1.0.1")
        assert result is None


# ── list_archives ────────────────────────────────────────


class TestListArchives:
    def test_list_delivery_archives(self, am: ArchiveManager) -> None:
        """列出交付物归档"""
        am.archive_delivery("V1.0.0", "V1.0.1", "v1")
        archives = am.list_archives("delivery")
        assert len(archives) >= 1
        assert any("V1.0.0" in a["version"] for a in archives)

    def test_list_package_archives(self, am: ArchiveManager) -> None:
        """列出交付物打包归档"""
        am.archive_package("V1.0.0", "V1.0.1", "v1")
        archives = am.list_archives("package")
        assert len(archives) >= 1

    def test_list_empty_archives(self, tmp_path: Path) -> None:
        """无归档时返回空列表"""
        project = tmp_path / "empty"
        project.mkdir()
        am = ArchiveManager(project)
        archives = am.list_archives("delivery")
        assert archives == []


# ── restore_delivery ─────────────────────────────────────


class TestRestoreDelivery:
    def test_restore_delivery(self, am: ArchiveManager) -> None:
        """恢复归档后根目录应恢复原始文件"""
        # 先归档
        am.archive_delivery("V1.0.0", "V1.0.1", "升级")
        # 确保根目录 README.md 被移走
        assert not (am._delivery_dir / "README.md").exists()

        # 恢复
        success = am.restore_delivery("V1.0.0")
        assert success
        # 根目录应恢复
        assert (am._delivery_dir / "README.md").exists()

    def test_restore_nonexistent(self, tmp_path: Path) -> None:
        """恢复不存在的版本应返回 False"""
        project = tmp_path / "no_archive"
        project.mkdir()
        am = ArchiveManager(project)
        success = am.restore_delivery("V99.99.99")
        assert not success


# ── clean_archives ───────────────────────────────────────


class TestCleanArchives:
    def test_clean_dry_run(self, am: ArchiveManager) -> None:
        """dry_run 模式不应实际删除"""
        am.archive_delivery("V1.0.0", "V1.0.1", "v1")
        removed = am.clean_archives("delivery", keep=0, dry_run=True)
        assert len(removed) > 0
        # 归档目录应仍然存在
        assert (am._delivery_dir / DIR_ARCHIVE).exists()

    def test_clean_actual(self, am: ArchiveManager) -> None:
        """实际清理应删除旧归档"""
        am.archive_delivery("V1.0.0", "V1.0.1", "v1")
        removed = am.clean_archives("delivery", keep=0, dry_run=False)
        assert len(removed) > 0


# ── get_current_version ──────────────────────────────────


class TestGetCurrentVersion:
    def test_detect_from_changelog(self, am: ArchiveManager) -> None:
        """从 CHANGELOG.md 检测版本号"""
        version = am.get_current_version()
        assert version == "V1.0.0"

    def test_no_delivery_dir(self, tmp_path: Path) -> None:
        """无交付物目录时返回 None"""
        project = tmp_path / "no_del"
        project.mkdir()
        am = ArchiveManager(project)
        version = am.get_current_version()
        assert version is None


# ── get_delivery_info / get_package_info ─────────────────


class TestGetInfo:
    def test_get_delivery_info(self, am: ArchiveManager) -> None:
        """获取交付物信息"""
        info = am.get_delivery_info()
        assert info is not None
        assert info["total_files"] > 0
        assert len(info["exe_files"]) > 0

    def test_get_package_info(self, am: ArchiveManager) -> None:
        """获取打包信息"""
        info = am.get_package_info()
        assert info is not None
        assert info["name"].endswith(".zip")
        assert info["size_mb"] > 0
