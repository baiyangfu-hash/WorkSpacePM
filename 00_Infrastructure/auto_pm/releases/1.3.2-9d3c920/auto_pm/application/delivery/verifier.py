"""交付物验证器

从 build_delivery.py 提取的 D-checks 和 CHK-checks 逻辑。
支持可配置阈值，输出结构化验证结果。
"""

from __future__ import annotations

import os
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from auto_pm.delivery.constants import (
    CHK_DOC_MIN_COUNT,
    CHK_EXE_MAX_MB,
    CHK_EXE_MIN_MB,
    CHK_TOTAL_MAX_FILES,
    CHK_TOTAL_MIN_FILES,
    CHK_ZIP_MAX_MB,
    CHK_ZIP_MIN_MB,
    CHK_ZIP_NORMAL_MAX_MB,
    CHK_ZIP_NORMAL_MIN_MB,
    DCHECK_DELIVERY_MIN_FILES,
    DCHECK_EXE_MIN_MB,
    DCHECK_INTERNAL_MIN_FILES,
    DIR_RELEASE_NOTES,
    MB,
)


@dataclass
class CheckResult:
    """单个检查项结果"""
    code: str
    description: str
    passed: bool
    detail: str = ""
    level: str = "fail"  # pass / warn / fail


@dataclass
class VerificationReport:
    """验证报告"""
    checks: list[CheckResult] = field(default_factory=list)
    passed: int = 0
    warn: int = 0
    fail: int = 0

    def add(self, result: CheckResult) -> None:
        self.checks.append(result)
        if result.passed:
            if result.level == "warn":
                self.warn += 1
            else:
                self.passed += 1
        else:
            self.fail += 1

    @property
    def is_approved(self) -> bool:
        return self.fail == 0

    @property
    def status_emoji(self) -> str:
        if self.fail > 0:
            return "🔴 FAIL"
        elif self.warn > 0:
            return "🟠 WARN"
        return "🟢 PASS"

    def summary(self) -> str:
        lines = [
            "=" * 60,
            "DELIVERY VERIFICATION REPORT",
            "=" * 60,
            f"\n[✓] PASS ({self.passed}):",
        ]
        for c in self.checks:
            if c.passed and c.level != "warn":
                lines.append(f"  [{c.code}] {c.description}: {c.detail}")
        lines.append(f"\n[⚠] WARN ({self.warn}):")
        for c in self.checks:
            if c.passed and c.level == "warn":
                lines.append(f"  [{c.code}] {c.description}: {c.detail}")
        lines.append(f"\n[✗] FAIL ({self.fail}):")
        for c in self.checks:
            if not c.passed:
                lines.append(f"  [{c.code}] {c.description}: {c.detail}")
        lines.append(f"\n>>> Final Status: {self.status_emoji}")
        lines.append("=" * 60)
        return "\n".join(lines)


class DeliveryVerifier:
    """交付物验证器"""

    def __init__(self, thresholds: dict[str, int] | None = None) -> None:
        self._thresholds: dict[str, int] = thresholds or {}

    def _get(self, key: str, default: int) -> int:
        val: Any = self._thresholds.get(key, default)
        return int(val)

    # ── 交付物目录校验 (D-checks) ──────────────────────

    def verify_delivery_dir(self, delivery_dir: Path) -> VerificationReport:
        """验证 06_交付物/ 目录完整性。

        Args:
            delivery_dir: 06_交付物/ 目录路径

        Returns:
            VerificationReport
        """
        report = VerificationReport()

        # D1: exe 存在且大小正常
        exe_files = list(delivery_dir.rglob("*.exe"))
        if exe_files:
            exe_path = exe_files[0]
            size_mb = exe_path.stat().st_size / MB
            min_mb = self._get("exe_min_mb", DCHECK_EXE_MIN_MB)
            if size_mb >= min_mb:
                report.add(CheckResult("D1", "exe 存在且大小正常", True, f"{size_mb:.2f} MB", "pass"))
            else:
                report.add(CheckResult("D1", "exe 过小", False, f"{size_mb:.2f} MB < {min_mb} MB"))
        else:
            report.add(CheckResult("D1", "exe 缺失", False, "未找到 .exe 文件"))

        # D2: _internal 目录
        internal_dirs = list(delivery_dir.rglob("_internal"))
        if internal_dirs:
            internal_dir = internal_dirs[0]
            icount = sum(len(files) for _, _, files in os.walk(internal_dir))
            min_files = self._get("internal_min_files", DCHECK_INTERNAL_MIN_FILES)
            if icount >= min_files:
                report.add(CheckResult("D2", "_internal 文件数正常", True, f"{icount} files", "pass"))
            else:
                report.add(CheckResult("D2", "_internal 文件数过少", True, f"{icount} < {min_files}", "warn"))
        else:
            report.add(CheckResult("D2", "_internal 目录缺失", True, "可能为 onefile 模式", "warn"))

        # D3: 发布说明
        docs_dir = delivery_dir / DIR_RELEASE_NOTES
        if docs_dir.exists() and any(docs_dir.iterdir()):
            dcount = len(list(docs_dir.iterdir()))
            report.add(CheckResult("D3", "发布说明存在", True, f"{dcount} files", "pass"))
        else:
            report.add(CheckResult("D3", "发布说明缺失", True, "目录为空", "warn"))

        # D4: 总文件数
        total_files = sum(len(files) for _, _, files in os.walk(delivery_dir))
        min_files = self._get("delivery_min_files", DCHECK_DELIVERY_MIN_FILES)
        if total_files >= min_files:
            report.add(CheckResult("D4", "总文件数正常", True, f"{total_files} files", "pass"))
        else:
            report.add(CheckResult("D4", "总文件数过少", False, f"{total_files} < {min_files}"))

        return report

    # ── ZIP 校验 (CHK-checks) ──────────────────────────

    def verify_zip(self, zip_path: Path) -> VerificationReport:
        """验证 ZIP 包完整性。

        Args:
            zip_path: ZIP 文件路径

        Returns:
            VerificationReport
        """
        report = VerificationReport()

        if not zip_path.exists():
            report.add(CheckResult("CHK-000", "ZIP 文件不存在", False, str(zip_path)))
            return report

        try:
            with zipfile.ZipFile(str(zip_path), "r") as zf:
                names = zf.namelist()

                # CHK-001: 总文件数
                total = len(names)
                min_f = self._get("total_min_files", CHK_TOTAL_MIN_FILES)
                max_f = self._get("total_max_files", CHK_TOTAL_MAX_FILES)
                if total < min_f:
                    report.add(CheckResult("CHK-001", "文件数过少", False, f"{total} < {min_f}"))
                elif total > max_f:
                    report.add(CheckResult("CHK-001", "文件数过多", False, f"{total} > {max_f}"))
                else:
                    report.add(CheckResult("CHK-001", "文件数正常", True, f"{total}"))

                # CHK-002: ZIP 大小
                zip_size = zip_path.stat().st_size / MB
                z_min = self._get("zip_min_mb", CHK_ZIP_MIN_MB)
                z_max = self._get("zip_max_mb", CHK_ZIP_MAX_MB)
                z_norm_min = self._get("zip_normal_min_mb", CHK_ZIP_NORMAL_MIN_MB)
                z_norm_max = self._get("zip_normal_max_mb", CHK_ZIP_NORMAL_MAX_MB)
                if zip_size < z_min:
                    report.add(CheckResult("CHK-002", "ZIP 过小", False, f"{zip_size:.2f} MB < {z_min} MB"))
                elif zip_size > z_max:
                    report.add(CheckResult("CHK-002", "ZIP 过大", False, f"{zip_size:.2f} MB > {z_max} MB"))
                elif z_norm_min <= zip_size <= z_norm_max:
                    report.add(CheckResult("CHK-002", "ZIP 大小正常", True, f"{zip_size:.2f} MB"))
                else:
                    report.add(CheckResult("CHK-002", "ZIP 大小可接受", True, f"{zip_size:.2f} MB", "warn"))

                # CHK-003: exe 存在且大小正常
                exe_names = [n for n in names if n.endswith(".exe") and "可执行文件" in n]
                if exe_names:
                    exe_info = zf.getinfo(exe_names[0])
                    exe_mb = exe_info.file_size / MB
                    exe_min = self._get("exe_min_mb", CHK_EXE_MIN_MB)
                    exe_max = self._get("exe_max_mb", CHK_EXE_MAX_MB)
                    if exe_mb < exe_min:
                        report.add(CheckResult("CHK-003", "exe 过小", False, f"{exe_mb:.2f} MB < {exe_min} MB"))
                    elif exe_mb > exe_max:
                        report.add(CheckResult("CHK-003", "exe 过大", True, f"{exe_mb:.2f} MB > {exe_max} MB", "warn"))
                    else:
                        report.add(CheckResult("CHK-003", "exe 大小正常", True, f"{exe_mb:.2f} MB"))
                else:
                    report.add(CheckResult("CHK-003", "exe 缺失", False, "未找到 exe"))

                # CHK-004: _internal 文件数
                internal_count = len([n for n in names if "_internal/" in n])
                if internal_count > 0:
                    report.add(CheckResult("CHK-004", "_internal 文件数", True, f"{internal_count} files"))
                else:
                    report.add(CheckResult("CHK-004", "_internal 缺失", True, "可能为 onefile 模式", "warn"))

                # CHK-005: 关键文档
                doc_count = len([n for n in names if n.endswith(".md")])
                doc_min = self._get("doc_min_count", CHK_DOC_MIN_COUNT)
                if doc_count >= doc_min:
                    report.add(CheckResult("CHK-005", "文档文件数正常", True, f"{doc_count} files"))
                else:
                    report.add(CheckResult("CHK-005", "文档文件数过少", True, f"{doc_count} < {doc_min}", "warn"))

                # CHK-006: 一级目录完整性
                top_dirs = set()
                for n in names:
                    parts = n.split("/")
                    if len(parts) >= 2:
                        top_dirs.add(parts[0])
                expected = {"01_可执行文件"}
                if expected.issubset(top_dirs):
                    report.add(CheckResult("CHK-006", "一级目录完整", True, ", ".join(sorted(top_dirs))))
                else:
                    missing = expected - top_dirs
                    report.add(CheckResult("CHK-006", "一级目录不完整", False, f"缺失: {missing}"))

        except zipfile.BadZipFile as e:
            report.add(CheckResult("CHK-000", "ZIP 文件损坏", False, str(e)))

        return report
