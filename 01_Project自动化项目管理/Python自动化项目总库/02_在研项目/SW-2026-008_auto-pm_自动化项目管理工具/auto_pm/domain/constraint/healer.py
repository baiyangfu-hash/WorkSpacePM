"""约束自愈引擎 - Phase 2 (CST-HEALER)

实现 ConstraintHealer 类，支持 auto_fix=true 约束的风险自动修复。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from auto_pm.constraint.guard import FileGuard
from auto_pm.constraint.loader import ConstraintLoader
from auto_pm.logging.audit import audit_log


class ConstraintHealer:
    """约束自愈引擎"""

    def __init__(self, workspace_root: Path, guard: FileGuard | None = None) -> None:
        self._workspace_root = workspace_root
        self._guard = guard or FileGuard(workspace_root)
        self._loader = ConstraintLoader(workspace_root)

    def heal_file(self, file_path: Path, dry_run: bool = False) -> list[dict[str, Any]]:
        """针对指定文件执行可修复规则"""
        results: list[dict[str, Any]] = []

        # 检查 BOM 自愈
        encoding_res = self._guard.check_encoding(file_path)
        if encoding_res["bom_count"] > 1:
            if dry_run:
                results.append(
                    {
                        "constraint_id": "CST-FILE-002",
                        "file_path": str(file_path),
                        "action": "strip_bom",
                        "dry_run": True,
                        "bom_before": encoding_res["bom_count"],
                        "bom_after": 1,
                        "message": f"将剥离 {encoding_res['bom_count'] - 1} 个多余 BOM",
                    }
                )
            else:
                heal_res = self._guard.heal_bom(file_path)
                if heal_res.get("healed"):
                    results.append(
                        {
                            "constraint_id": "CST-FILE-002",
                            "file_path": str(file_path),
                            "action": "strip_bom",
                            "dry_run": False,
                            "bom_before": heal_res["bom_before"],
                            "bom_after": heal_res["bom_after"],
                            "bytes_removed": heal_res["bytes_removed"],
                            "message": f"已剥离 {heal_res['bom_before'] - heal_res['bom_after']} 个多余 BOM",
                        }
                    )

        return results

    def heal_all(self, dry_run: bool = False) -> list[dict[str, Any]]:
        """全量扫描工作空间并执行修复"""
        results: list[dict[str, Any]] = []
        constraints = self._loader.load_all()

        auto_fix_csts = [c for c in constraints if c.auto_fix]
        if not auto_fix_csts:
            return results

        exclude_dirs = {".git", "__pycache__", "node_modules", ".venv", "coverage", ".pytest_cache"}

        for root_str, dirs, files in os.walk(str(self._workspace_root)):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            root = Path(root_str)

            for file_name in files:
                full_path = root / file_name
                file_results = self.heal_file(full_path, dry_run=dry_run)
                results.extend(file_results)

        if results and not dry_run:
            audit_log("constraint_heal_all", items_healed=len(results))

        return results
