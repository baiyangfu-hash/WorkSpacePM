"""交付物核心服务

编排交付物的构建、打包、状态查询流程。
协调 ArchiveManager 和 Verifier，提供统一的业务接口。
"""

from __future__ import annotations

import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from auto_pm.delivery.archive_manager import ArchiveManager
from auto_pm.delivery.constants import (
    DEFAULT_PRODUCT_NAME,
    DIR_DELIVERY,
    DIR_EXECUTABLE,
    DIR_PACKAGE,
    DIR_RELEASE_NOTES,
    MB,
    PACKAGE_NAME_TEMPLATE,
)
from auto_pm.delivery.verifier import DeliveryVerifier


class DeliveryService:
    """交付物服务 — 编排 build/package/status 流程"""

    def __init__(self, project_root: str | Path) -> None:
        self._project_root = Path(project_root)
        self._delivery_dir = self._project_root / DIR_DELIVERY
        self._package_dir = self._project_root / DIR_PACKAGE
        self._archive = ArchiveManager(project_root)
        self._verifier = DeliveryVerifier()

    # ── 构建交付物 ──────────────────────────────────────

    def build(
        self,
        version: str,
        skip_pyinstaller: bool = False,
        auto_package: bool = False,
        dist_dir: str | Path | None = None,
        product_name: str = DEFAULT_PRODUCT_NAME,
        summary: str = "",
    ) -> dict[str, Any]:
        """构建交付物。

        流程:
          1. [可选] 执行 PyInstaller 编译
          2. 归档旧版到 archive/
          3. 复制新 exe + _internal → 06_交付物/01_可执行文件/
          4. 复制发布文档
          5. 执行 D-checks 校验
          6. [可选] 自动调用 package

        Args:
            version: 目标版本号（如 V1.0.1）
            skip_pyinstaller: 跳过 PyInstaller 编译
            auto_package: 构建后自动打包
            dist_dir: PyInstaller 输出目录（默认 dist/{product_name}）
            product_name: 产品名称
            summary: 变更摘要

        Returns:
            dict: {"success": bool, "message": str, "archive_path": str|None, "package_result": dict|None}
        """
        result: dict[str, Any] = {
            "success": False,
            "message": "",
            "archive_path": None,
            "package_result": None,
        }

        # Step 1: 编译检查
        if not skip_pyinstaller:
            result["message"] = "PyInstaller 编译需在外部执行（使用 --skip-pyinstaller 跳过）"
            result["success"] = False
            return result

        # 检查源文件
        if dist_dir is None:
            dist_dir = self._project_root / "dist" / product_name
        dist_path = Path(dist_dir)
        if not dist_path.exists():
            result["message"] = f"编译输出目录不存在: {dist_path}"
            result["success"] = False
            return result

        exe_src = dist_path / f"{product_name}.exe"
        if not exe_src.exists():
            # 尝试查找其他 exe
            exe_candidates = list(dist_path.rglob("*.exe"))
            if exe_candidates:
                exe_src = exe_candidates[0]
            else:
                result["message"] = f"未找到 exe 文件: {dist_path}"
                result["success"] = False
                return result

        # Step 2: 归档旧版交付物
        old_version = self._archive.get_current_version()
        if old_version and self._delivery_dir.exists():
            archive_path = self._archive.archive_delivery(
                old_version=old_version,
                new_version=version,
                summary=summary,
            )
            result["archive_path"] = str(archive_path) if archive_path else None

        # Step 3: 复制新交付物
        self._delivery_dir.mkdir(parents=True, exist_ok=True)
        exe_dst_dir = self._delivery_dir / DIR_EXECUTABLE

        # 清理旧的可执行文件目录
        if exe_dst_dir.exists():
            shutil.rmtree(str(exe_dst_dir))
        exe_dst_dir.mkdir(parents=True, exist_ok=True)

        # 复制整个 dist 输出
        shutil.copytree(str(dist_path), str(exe_dst_dir), dirs_exist_ok=True)

        # Step 4: 复制发布文档
        docs_dst = self._delivery_dir / DIR_RELEASE_NOTES
        docs_dst.mkdir(parents=True, exist_ok=True)

        for doc in ["CHANGELOG.md", "README.md"]:
            src_f = self._project_root / doc
            dst_f = self._delivery_dir / doc
            if src_f.exists():
                shutil.copy2(str(src_f), str(dst_f))

        # 复制发布说明文档
        release_dir = self._project_root / DIR_RELEASE_NOTES
        if release_dir.exists():
            for doc_name in [f"{version}_更新说明.md", f"01_交付清单_DEL-{version}.md"]:
                src_f = release_dir / doc_name
                dst_f = docs_dst / doc_name
                if src_f.exists():
                    shutil.copy2(str(src_f), str(dst_f))

        # Step 5: D-checks 校验
        d_report = self._verifier.verify_delivery_dir(self._delivery_dir)
        if not d_report.is_approved:
            result["message"] = f"交付物校验失败:\n{d_report.summary()}"
            result["success"] = False
            return result

        # Step 6: 自动打包
        if auto_package:
            pkg_result = self.package(version=version, product_name=product_name, summary=summary)
            result["package_result"] = pkg_result

        result["success"] = True
        result["message"] = f"交付物构建完成: {version}"
        return result

    # ── 打包 ZIP ────────────────────────────────────────

    def package(
        self,
        version: str,
        product_name: str = DEFAULT_PRODUCT_NAME,
        verify_only: bool = False,
        summary: str = "",
    ) -> dict[str, Any]:
        """打包交付物为 ZIP。

        流程:
          1. 归档旧 ZIP → 06_交付物/archive/
          2. 从 06_交付物/ 创建新 ZIP
          3. 执行 CHK-checks 验证

        Args:
            version: 版本号
            product_name: 产品名称
            verify_only: 仅验证已有 ZIP
            summary: 变更摘要

        Returns:
            dict: {"success": bool, "zip_path": str|None, "file_count": int, "size_mb": float, "report": str}
        """
        result: dict[str, Any] = {
            "success": False,
            "zip_path": None,
            "file_count": 0,
            "size_mb": 0.0,
            "report": "",
        }

        self._package_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d")
        zip_name = PACKAGE_NAME_TEMPLATE.format(
            product_name=product_name, version=version, date=date_str
        )
        zip_path = self._package_dir / zip_name

        # verify-only 模式
        if verify_only:
            if not zip_path.exists():
                result["message"] = f"ZIP 不存在: {zip_path}"
                return result
            chk_report = self._verifier.verify_zip(zip_path)
            result["report"] = chk_report.summary()
            result["success"] = chk_report.is_approved
            result["zip_path"] = str(zip_path)
            result["size_mb"] = round(zip_path.stat().st_size / MB, 2)
            return result

        # 归档旧 ZIP
        old_version = self._archive.get_current_version()
        if old_version:
            self._archive.archive_package(
                old_version=old_version,
                new_version=version,
                summary=summary,
            )

        # 创建新 ZIP
        if not self._delivery_dir.exists():
            result["message"] = "06_交付物/ 目录不存在，请先执行 delivery build"
            return result

        if zip_path.exists():
            zip_path.unlink()

        file_count = 0
        try:
            with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
                for root, _dirs, files in os.walk(str(self._delivery_dir)):
                    for fn in files:
                        fp = os.path.join(root, fn)
                        arcname = os.path.relpath(fp, str(self._delivery_dir))
                        zf.write(fp, arcname)
                        file_count += 1
        except Exception as e:
            result["message"] = f"打包失败: {e}"
            return result

        zip_size = zip_path.stat().st_size / MB

        # CHK-checks 验证
        chk_report = self._verifier.verify_zip(zip_path)

        result["success"] = chk_report.is_approved
        result["zip_path"] = str(zip_path)
        result["file_count"] = file_count
        result["size_mb"] = round(zip_size, 2)
        result["report"] = chk_report.summary()
        result["message"] = "打包完成" if chk_report.is_approved else "打包完成但验证未通过"

        return result

    # ── 状态查询 ────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        """获取当前交付物状态。

        Returns:
            dict: 包含 delivery_info, package_info, archive_info
        """
        delivery_info = self._archive.get_delivery_info()
        package_info = self._archive.get_package_info()
        archives = self._archive.list_archives("delivery")
        package_archives = self._archive.list_archives("package")

        return {
            "delivery": delivery_info,
            "package": package_info,
            "delivery_archives": archives,
            "package_archives": package_archives,
            "archive_count": len(archives),
            "package_archive_count": len(package_archives),
        }
