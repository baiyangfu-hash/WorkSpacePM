"""归档管理器

负责旧版交付物和交付物打包的归档操作：
- 将当前版本归档到 archive/ 子目录
- 生成 archive_info.md 归档说明
- 列出/恢复/清理归档版本
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from auto_pm.delivery.constants import (
    ARCHIVE_DIR_TEMPLATE,
    ARCHIVE_INFO_FILENAME,
    ARCHIVE_MANIFEST_FILENAME,
    DEFAULT_ARCHIVE_KEEP,
    DIR_ARCHIVE,
    DIR_DELIVERY,
    DIR_PACKAGE,
    MB,
)


class ArchiveManager:
    """归档管理器 — 纯文件操作，无外部依赖"""

    def __init__(self, project_root: str | Path) -> None:
        self._project_root = Path(project_root)
        self._delivery_dir = self._project_root / DIR_DELIVERY
        self._package_dir = self._project_root / DIR_PACKAGE

    # ── 交付物归档 ──────────────────────────────────────

    def archive_delivery(
        self, old_version: str, new_version: str, summary: str = ""
    ) -> Path | None:
        """将当前 06_交付物/ 根目录内容归档到 archive/ 子目录。

        Args:
            old_version: 被归档的版本号（如 V1.0.0）
            new_version: 替代的新版本号（如 V1.0.1）
            summary: 变更摘要

        Returns:
            归档目标目录路径，如果无内容可归档则返回 None
        """
        if not self._delivery_dir.exists():
            return None

        # 收集要归档的项（排除 archive/ 子目录本身和 ZIP 文件）
        # CHG-SCPT-2026-145: ZIP 文件由 archive_package 独立归档，不随 delivery 归档移动
        items = [
            p
            for p in self._delivery_dir.iterdir()
            if p.name != DIR_ARCHIVE and p.suffix.lower() != ".zip"
        ]
        if not items:
            return None

        date_str = datetime.now().strftime("%Y%m%d")
        archive_dir_name = ARCHIVE_DIR_TEMPLATE.format(version=old_version, date=date_str)
        archive_dest = self._delivery_dir / DIR_ARCHIVE / archive_dir_name
        archive_dest.mkdir(parents=True, exist_ok=True)

        # 移动所有项到归档目录
        total_size = 0
        for item in items:
            dest = archive_dest / item.name
            shutil.move(str(item), str(dest))
            total_size += self._dir_size(dest)

        # 生成归档说明
        self._write_archive_info(
            archive_dest / ARCHIVE_INFO_FILENAME,
            version=old_version,
            size_bytes=total_size,
            summary=summary,
            replaced_by=new_version,
        )

        return Path(archive_dest)

    def archive_package(self, old_version: str, new_version: str, summary: str = "") -> Path | None:
        """将当前 06_交付物/ 根目录 ZIP 归档到 archive/ 子目录。

        Args:
            old_version: 被归档的版本号
            new_version: 替代的新版本号
            summary: 变更摘要

        Returns:
            归档的 ZIP 路径，如果无 ZIP 可归档则返回 None
        """
        if not self._package_dir.exists():
            return None

        # 找到根目录下的 ZIP 文件（排除 archive/ 子目录）
        zip_files = [
            p
            for p in self._package_dir.iterdir()
            if p.suffix.lower() == ".zip" and p.name != DIR_ARCHIVE
        ]
        if not zip_files:
            return None

        archive_dest_dir = self._package_dir / DIR_ARCHIVE
        archive_dest_dir.mkdir(parents=True, exist_ok=True)

        for zip_path in zip_files:
            dest = archive_dest_dir / zip_path.name
            zip_size = zip_path.stat().st_size  # 保存大小（move 前）
            shutil.move(str(zip_path), str(dest))

            # 更新归档总清单
            self._update_archive_manifest(
                archive_dest_dir / ARCHIVE_MANIFEST_FILENAME,
                zip_path.name,
                old_version,
                new_version,
                summary,
                zip_size,
            )

            return Path(dest)

        return None

    # ── 归档查询 ──────────────────────────────────────

    def list_archives(self, archive_type: str = "delivery") -> list[dict[str, Any]]:
        """列出归档版本。

        Args:
            archive_type: "delivery" 或 "package"

        Returns:
            归档信息列表，每项包含 version, date, size_mb, summary, replaced_by
        """
        if archive_type == "delivery":
            archive_dir = self._delivery_dir / DIR_ARCHIVE
        else:
            archive_dir = self._package_dir / DIR_ARCHIVE

        if not archive_dir.exists():
            return []

        results = []
        for entry in sorted(archive_dir.iterdir(), reverse=True):
            if not entry.is_dir() and archive_type == "delivery":
                continue
            if entry.is_dir() and archive_type == "package":
                continue

            info = self._read_archive_info(entry)
            if info:
                results.append(info)

        return results

    def restore_delivery(self, version: str) -> bool:
        """将指定归档版本恢复到 06_交付物/ 根目录。

        当前最新版本会先被归档。

        Args:
            version: 要恢复的版本号（如 V1.0.0）

        Returns:
            是否成功
        """
        archive_dir = self._delivery_dir / DIR_ARCHIVE
        if not archive_dir.exists():
            return False

        # 查找匹配的归档目录
        target = None
        for entry in archive_dir.iterdir():
            if entry.is_dir() and version in entry.name:
                target = entry
                break

        if target is None:
            return False

        # 归档当前最新版本
        current_version = self._detect_current_version()
        if current_version:
            self.archive_delivery(
                old_version=current_version,
                new_version=version,
                summary=f"恢复归档版本 {version}",
            )

        # 恢复目标版本
        for item in target.iterdir():
            if item.name == ARCHIVE_INFO_FILENAME:
                continue
            dest = self._delivery_dir / item.name
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(str(dest))
                else:
                    dest.unlink()
            shutil.move(str(item), str(dest))

        return True

    def clean_archives(
        self,
        archive_type: str = "delivery",
        keep: int = DEFAULT_ARCHIVE_KEEP,
        dry_run: bool = False,
    ) -> list[Path]:
        """清理旧归档，保留最近 N 个。

        Args:
            archive_type: "delivery" 或 "package"
            keep: 保留最近的数量
            dry_run: 仅预览，不实际删除

        Returns:
            被清理的路径列表
        """
        if archive_type == "delivery":
            archive_dir = self._delivery_dir / DIR_ARCHIVE
        else:
            archive_dir = self._package_dir / DIR_ARCHIVE

        if not archive_dir.exists():
            return []

        entries = sorted(
            archive_dir.iterdir(),
            key=lambda e: e.stat().st_mtime,
            reverse=True,
        )

        to_remove = entries[keep:]
        if not dry_run:
            for entry in to_remove:
                if entry.is_dir():
                    shutil.rmtree(str(entry))
                else:
                    entry.unlink()

        return to_remove

    # ── 状态查询 ──────────────────────────────────────

    def get_current_version(self) -> str | None:
        """检测当前 06_交付物/ 中的版本号。"""
        return self._detect_current_version()

    def get_package_info(self) -> dict[str, Any] | None:
        """获取当前交付物打包信息。"""
        if not self._package_dir.exists():
            return None

        zip_files = [
            p
            for p in self._package_dir.iterdir()
            if p.suffix.lower() == ".zip" and p.name != DIR_ARCHIVE
        ]
        if not zip_files:
            return None

        zip_path = zip_files[0]
        return {
            "name": zip_path.name,
            "size_mb": round(zip_path.stat().st_size / MB, 2),
            "modified": datetime.fromtimestamp(zip_path.stat().st_mtime).isoformat(),
        }

    def get_delivery_info(self) -> dict[str, Any] | None:
        """获取当前交付物信息。"""
        if not self._delivery_dir.exists():
            return None

        exe_dir = self._delivery_dir / "01_可执行文件"
        exe_files = list(exe_dir.rglob("*.exe")) if exe_dir.exists() else []

        total_files = sum(len(files) for _, _, files in os.walk(self._delivery_dir))

        return {
            "total_files": total_files,
            "exe_files": [str(f.relative_to(self._delivery_dir)) for f in exe_files],
            "archive_count": len(self.list_archives("delivery")),
            "package_archive_count": len(self.list_archives("package")),
        }

    # ── 内部辅助方法 ──────────────────────────────────────

    def _detect_current_version(self) -> str | None:
        """从 CHANGELOG.md 或 README.md 检测当前版本号。"""
        for doc_name in ["CHANGELOG.md", "README.md"]:
            doc_path = self._delivery_dir / doc_name
            if doc_path.exists():
                content = doc_path.read_text(encoding="utf-8", errors="replace")
                for line in content.splitlines():
                    if line.startswith("## [") and "]" in line:
                        # 提取 ## [1.0.0] 格式的版本号
                        version = line.split("[")[1].split("]")[0]
                        if version not in ("Unreleased",):
                            return f"V{version}"
        return None

    @staticmethod
    def _write_archive_info(
        filepath: Path,
        version: str,
        size_bytes: int,
        summary: str,
        replaced_by: str,
    ) -> None:
        """写入 archive_info.md 文件。"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        size_mb = round(size_bytes / MB, 2)
        content = f"""# 归档信息

| 字段 | 内容 |
|------|------|
| 版本号 | {version} |
| 归档日期 | {date_str} |
| 原始文件大小 | {size_mb} MB |
| 变更摘要 | {summary or "—"} |
| 被替代版本 | {replaced_by} |
| 操作人 | auto-pm delivery |
"""
        filepath.write_text(content, encoding="utf-8")

    @staticmethod
    def _update_archive_manifest(
        filepath: Path,
        filename: str,
        old_version: str,
        new_version: str,
        summary: str,
        size_bytes: int,
    ) -> None:
        """更新归档总清单。"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        size_mb = round(size_bytes / MB, 2)

        header = "# 交付物打包归档清单\n\n"
        if filepath.exists():
            existing = filepath.read_text(encoding="utf-8")
        else:
            existing = (
                header
                + "| 文件名 | 版本 | 归档日期 | 大小 | 替代版本 | 摘要 |\n|------|------|------|------|------|------|\n"
            )

        new_line = f"| {filename} | {old_version} | {date_str} | {size_mb} MB | {new_version} | {summary or '—'} |\n"
        existing = existing.rstrip() + "\n" + new_line + "\n"
        filepath.write_text(existing, encoding="utf-8")

    @staticmethod
    def _read_archive_info(entry: Path) -> dict[str, Any] | None:
        """从归档条目读取信息。"""
        info_path = entry / ARCHIVE_INFO_FILENAME if entry.is_dir() else None

        if info_path and info_path.exists():
            content = info_path.read_text(encoding="utf-8")
            for line in content.splitlines():
                if "|" in line and "版本号" in line:
                    # 简单解析 Markdown 表格
                    pass
            return {
                "path": str(entry),
                "version": entry.name,
                "date": datetime.fromtimestamp(entry.stat().st_mtime).strftime("%Y-%m-%d"),
                "size_mb": round(
                    (
                        sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
                        if entry.is_dir()
                        else entry.stat().st_size
                    )
                    / MB,
                    2,
                ),
                "summary": "",
                "replaced_by": "",
            }

        # 对于 ZIP 文件（非目录）
        return {
            "path": str(entry),
            "version": entry.stem,
            "date": datetime.fromtimestamp(entry.stat().st_mtime).strftime("%Y-%m-%d"),
            "size_mb": round(entry.stat().st_size / MB, 2),
            "summary": "",
            "replaced_by": "",
        }

    @staticmethod
    def _dir_size(path: Path) -> int:
        """计算目录总大小（字节）。"""
        if path.is_file():
            return path.stat().st_size
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
