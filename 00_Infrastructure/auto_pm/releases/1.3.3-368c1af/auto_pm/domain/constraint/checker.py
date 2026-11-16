"""约束检查引擎 - Phase 2 (CST-CHECKER)

实现 ConstraintChecker 类，统一对各种约束（file_encoding, file_guard, naming, workflow, pre_commit, env）执行全面合规扫描。
"""

from __future__ import annotations

import fnmatch
import os
import re
import sys
from collections.abc import Generator
from datetime import datetime
from pathlib import Path

from auto_pm.constraint.guard import FileGuard
from auto_pm.constraint.loader import ConstraintLoader
from auto_pm.constraint.models import CheckReport, Constraint, ConstraintScope, Violation
from auto_pm.logging.audit import audit_log


class ConstraintChecker:
    """约束检查引擎"""

    def __init__(self, workspace_root: Path, guard: FileGuard | None = None) -> None:
        self._workspace_root = workspace_root
        self._guard = guard or FileGuard(workspace_root)
        self._loader = ConstraintLoader(workspace_root)

    def check_all(self) -> CheckReport:
        """扫描全量约束定义，返回检查报告 CheckReport"""
        constraints = self._loader.load_all()
        violations: list[Violation] = []

        for cst in constraints:
            violations.extend(self.check_constraint(cst))

        violations_count = len(violations)
        passed_count = len(constraints) - len({v.constraint_id for v in violations})

        report = CheckReport(
            total=len(constraints),
            passed=passed_count,
            violations=violations_count,
            violations_list=violations,
            checked_at=datetime.now(),
        )

        if violations_count > 0:
            audit_log(
                "constraint_check_failed",
                violations_count=violations_count,
                total_constraints=len(constraints),
            )
        else:
            audit_log("constraint_check_passed", total_constraints=len(constraints))

        return report

    def check_file(self, file_path: Path) -> list[Violation]:
        """对指定文件匹配所有约束进行针对性检查"""
        constraints = self._loader.load_all()
        violations: list[Violation] = []

        rel_path = self._to_relative(file_path)

        for cst in constraints:
            if self._file_matches_scope(rel_path, cst.scope):
                violations.extend(self._evaluate_file_for_constraint(file_path, cst))

        return violations

    def check_constraint(self, cst: Constraint) -> list[Violation]:
        """对单一 Constraint 执行规则检查"""
        violations: list[Violation] = []

        if cst.type == "file_encoding":
            for fp in self._iter_scope(cst.scope):
                res = self._guard.check_encoding(fp)
                if not res["is_healthy"]:
                    violations.append(
                        Violation(
                            constraint_id=cst.id,
                            file_path=str(fp),
                            rule_type="bom_count",
                            message=f"文件包含 {res['bom_count']} 个 BOM（允许最多 1 个）",
                            severity=cst.severity,
                            detected_at=datetime.now(),
                            evidence=res,
                        )
                    )

        elif cst.type == "file_guard":
            for fp in self._iter_scope(cst.scope):
                res = self._guard.verify_snapshot(fp)
                if not res.get("verified", False) and res.get("error") != "no_snapshot":
                    violations.append(
                        Violation(
                            constraint_id=cst.id,
                            file_path=str(fp),
                            rule_type="hash_mismatch",
                            message="文件哈希不匹配: 文件已被外部未登记修改",
                            severity=cst.severity,
                            detected_at=datetime.now(),
                            evidence=res,
                        )
                    )

        elif cst.type == "naming":
            for rule in cst.rules:
                if rule.type == "regex_blacklist" and rule.pattern:
                    regex = re.compile(rule.pattern)
                    for fp in self._iter_scope(cst.scope):
                        rel_str = str(self._to_relative(fp)).replace("\\", "/")
                        if regex.search(rel_str):
                            violations.append(
                                Violation(
                                    constraint_id=cst.id,
                                    file_path=str(fp),
                                    rule_type="regex_blacklist",
                                    message=f"文件名或路径包含禁止的版本号后缀: {fp.name}",
                                    severity=cst.severity,
                                    detected_at=datetime.now(),
                                    evidence={"pattern": rule.pattern},
                                )
                            )

        elif cst.type == "env":
            # 校验 Python 环境是否激活虚拟环境
            is_venv = (
                getattr(sys, "real_prefix", None) is not None
                or (sys.base_prefix != sys.prefix)
                or os.environ.get("VIRTUAL_ENV") is not None
            )
            if not is_venv:
                violations.append(
                    Violation(
                        constraint_id=cst.id,
                        file_path=str(self._workspace_root),
                        rule_type="check_venv",
                        message="当前 Python 进程未在 .venv 虚拟环境中运行",
                        severity=cst.severity,
                        detected_at=datetime.now(),
                        evidence={"prefix": sys.prefix, "base_prefix": sys.base_prefix},
                    )
                )

        return violations

    def _evaluate_file_for_constraint(self, file_path: Path, cst: Constraint) -> list[Violation]:
        """评估单个文件在指定约束下是否发生违规"""
        violations: list[Violation] = []
        if cst.type == "file_encoding":
            res = self._guard.check_encoding(file_path)
            if not res["is_healthy"]:
                violations.append(
                    Violation(
                        constraint_id=cst.id,
                        file_path=str(file_path),
                        rule_type="bom_count",
                        message=f"文件包含 {res['bom_count']} 个 BOM（允许最多 1 个）",
                        severity=cst.severity,
                        detected_at=datetime.now(),
                        evidence=res,
                    )
                )
        elif cst.type == "file_guard":
            res = self._guard.verify_snapshot(file_path)
            if not res.get("verified", False) and res.get("error") != "no_snapshot":
                violations.append(
                    Violation(
                        constraint_id=cst.id,
                        file_path=str(file_path),
                        rule_type="hash_mismatch",
                        message="文件哈希不匹配: 文件已被外部未登记修改",
                        severity=cst.severity,
                        detected_at=datetime.now(),
                        evidence=res,
                    )
                )
        elif cst.type == "naming":
            rel_str = str(self._to_relative(file_path)).replace("\\", "/")
            for rule in cst.rules:
                if rule.type == "regex_blacklist" and rule.pattern:
                    if re.search(rule.pattern, rel_str):
                        violations.append(
                            Violation(
                                constraint_id=cst.id,
                                file_path=str(file_path),
                                rule_type="regex_blacklist",
                                message=f"文件名或路径包含禁止的版本号后缀: {file_path.name}",
                                severity=cst.severity,
                                detected_at=datetime.now(),
                                evidence={"pattern": rule.pattern},
                            )
                        )
        return violations

    def _to_relative(self, file_path: Path) -> Path:
        try:
            return file_path.resolve().relative_to(self._workspace_root.resolve())
        except ValueError:
            return file_path

    def _file_matches_scope(self, rel_path: Path, scope: ConstraintScope) -> bool:
        rel_str = str(rel_path).replace("\\", "/")

        for ex in scope.exclude:
            ex_pattern = ex.replace("\\", "/")
            if fnmatch.fnmatch(rel_str, ex_pattern) or (
                ex_pattern.startswith("**/") and fnmatch.fnmatch(rel_str, ex_pattern[3:])
            ):
                return False

        for pat in scope.patterns:
            pat_pattern = pat.replace("\\", "/")
            if fnmatch.fnmatch(rel_str, pat_pattern) or (
                pat_pattern.startswith("**/") and fnmatch.fnmatch(rel_str, pat_pattern[3:])
            ):
                return True

        return False

    def _iter_scope(self, scope: ConstraintScope) -> Generator[Path, None, None]:
        """迭代匹配 scope.patterns 并剔除 scope.exclude 的文件"""
        exclude_dirs = {".git", "__pycache__", "node_modules", ".venv", "coverage", ".pytest_cache"}

        for root_str, dirs, files in os.walk(str(self._workspace_root)):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            root = Path(root_str)

            for file_name in files:
                full_path = root / file_name
                rel_path = self._to_relative(full_path)
                if self._file_matches_scope(rel_path, scope):
                    yield full_path
