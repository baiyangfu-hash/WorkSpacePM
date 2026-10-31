"""PLC-HMI 概念映射：SFB 库函数（规范检查（扫描文件是否符合规范））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from auto_pm.spec.core.checker_base import CheckResult, HealthChecker, Severity
from auto_pm.spec.core.config import WorkspaceConfig
from auto_pm.spec.core.registry import SpecRegistry
from auto_pm.spec.core.scanner import SpecScanner
from auto_pm.spec.services.fix_svc import FixResult, FixService


@dataclass
class CheckOutput:
    results: list[CheckResult]
    error_count: int
    warning_count: int
    info_count: int
    exit_code: int
    fix_results: list[FixResult] | None = None


class CheckService:
    def __init__(self, workspace: Path, config: WorkspaceConfig | None = None) -> None:
        self.workspace = workspace
        self.config = config or WorkspaceConfig(workspace=workspace)
        self.registry = SpecRegistry(workspace, registry_path=self.config.registry_path)
        self.registry_loaded = self.registry.load()
        self.checker = HealthChecker()

    def run(
        self,
        check_ids: list[str] | None = None,
        min_severity: Severity = Severity.INFO,
        auto_fix: bool = False,
        dry_run: bool = False,
        scope: str = "workspace",
        project_root: Path | None = None,
    ) -> CheckOutput:
        if not self.registry_loaded:
            return CheckOutput(
                results=[
                    CheckResult(
                        check_id="SHC-000",
                        severity=Severity.ERROR,
                        message=f"注册表文件不存在或格式错误: {self.registry.path}",
                        details="",
                        fix_suggestion="确认工作空间路径正确且spec_registry.json存在",
                    )
                ],
                error_count=1,
                warning_count=0,
                info_count=0,
                exit_code=1,
            )
        scanner = SpecScanner(
            self.workspace,
            self.config,
            project_root=project_root if scope == "project" else None,
        )
        effective_check_ids = check_ids
        if scope == "project" and not effective_check_ids:
            effective_check_ids = ["SHC-009"]
        if check_ids:
            results: list[CheckResult] = []
            for cid in check_ids:
                results.extend(self.checker.run_by_id(cid, self.registry, scanner))
        else:
            if effective_check_ids:
                results = []
                for cid in effective_check_ids:
                    results.extend(self.checker.run_by_id(cid, self.registry, scanner))
            else:
                results = self.checker.run_all(self.registry, scanner)

        filtered = [r for r in results if r.severity >= min_severity]
        error_count = sum(1 for r in filtered if r.severity == Severity.ERROR)
        warning_count = sum(1 for r in filtered if r.severity == Severity.WARNING)
        info_count = sum(1 for r in filtered if r.severity == Severity.INFO)
        exit_code = 1 if error_count else (2 if warning_count else 0)

        fix_results = None
        if auto_fix and filtered:
            fix_svc = FixService(self.workspace, self.registry, scanner)
            fix_results = fix_svc.fix_all(filtered, dry_run=dry_run)

        return CheckOutput(
            results=filtered,
            error_count=error_count,
            warning_count=warning_count,
            info_count=info_count,
            exit_code=exit_code,
            fix_results=fix_results,
        )
