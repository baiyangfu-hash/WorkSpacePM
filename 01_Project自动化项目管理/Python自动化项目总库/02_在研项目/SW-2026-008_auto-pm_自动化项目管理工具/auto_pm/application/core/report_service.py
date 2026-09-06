"""PLC-HMI 概念映射：SFB 库函数（报告生成（项目报告/变更报告/规范报告））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

报告 Service - 统计聚合

聚合 ProjectService / ChangeService / 规范目录 / 扫描日志的数据，
提供 4 种报告类型：
- 项目报告（get_project_overview）
- 变更报告（get_change_overview）
- 规范报告（get_spec_report）
- 扫描报告（get_scan_report）

用于报告中心全局页展示。不直接访问文件系统/DB 进行写入，
数据来源完全依赖注入的 Service 和 Repository。

V2.2 Week3：get_spec_report 改用 spec_registry.json（通过 SpecRegistry）
动态加载规范列表，不再硬编码 _STACK_SPECS。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class ReportService:
    """报告 Service

    通过注入的 ProjectService / ChangeService 聚合统计数据。
    规范报告和扫描报告依赖 workspace_root 和 db（可选）。

    构造参数向后兼容：仅传入 project_service/change_service 时仍可使用
    项目报告和变更报告；规范报告和扫描报告需要额外传入 workspace_root/db。
    """

    # 固定统计维度（确保返回结构稳定，未知值额外追加 key）
    _STACK_KEYS: list[str] = ["plc", "python", "unknown"]
    _PHASE_KEYS: list[str] = ["developing", "commissioning", "production", "archived"]
    _BL_KEYS: list[str] = ["SW", "DJ", "ZD", "XT", "WX"]

    # 报告类型枚举
    REPORT_PROJECT: str = "project"
    REPORT_CHANGE: str = "change"
    REPORT_SPEC: str = "spec"
    REPORT_SCAN: str = "scan"
    _REPORT_TYPES: tuple[str, ...] = (
        REPORT_PROJECT, REPORT_CHANGE, REPORT_SPEC, REPORT_SCAN,
    )

    def __init__(
        self,
        project_service: Any,
        change_service: Any,
        workspace_root: str = "",
        db: Any | None = None,
    ) -> None:
        self._project_service = project_service
        self._change_service = change_service
        self._workspace_root = os.path.abspath(workspace_root) if workspace_root else ""
        self._db = db

    # ── 项目报告 ──────────────────────────────────────────

    def get_project_overview(self) -> dict[str, Any]:
        """项目概览统计

        Returns:
            {
                'total': int,
                'by_stack': {'plc': int, 'python': int, 'unknown': int},
                'by_phase': {'developing': int, 'commissioning': int,
                             'production': int, 'archived': int},
                'by_business_line': {'SW': int, 'DJ': int, 'ZD': int,
                                     'XT': int, 'WX': int},
            }

        Raises:
            RuntimeError: ProjectService 未注入 DatabaseManager
        """
        projects = self._project_service.list_projects_cached()

        by_stack: dict[str, int] = dict.fromkeys(self._STACK_KEYS, 0)
        by_phase: dict[str, int] = dict.fromkeys(self._PHASE_KEYS, 0)
        by_business_line: dict[str, int] = dict.fromkeys(self._BL_KEYS, 0)

        for p in projects:
            # 技术栈（Stack Literal 仅 plc/python/unknown）
            by_stack[p.stack] = by_stack.get(p.stack, 0) + 1

            # 阶段（ProjectPhase 含 ""，未设置时计入 "" key）
            phase_key = p.phase if p.phase else ""
            by_phase[phase_key] = by_phase.get(phase_key, 0) + 1

            # 业务线（BusinessLine 含 ""，未设置时计入 "" key）
            bl_key = p.business_line if p.business_line else ""
            by_business_line[bl_key] = by_business_line.get(bl_key, 0) + 1

        log.info(
            "项目概览统计: total=%d, stack=%s, phase=%s, bl=%s",
            len(projects), by_stack, by_phase, by_business_line,
        )
        return {
            "total": len(projects),
            "by_stack": by_stack,
            "by_phase": by_phase,
            "by_business_line": by_business_line,
        }

    # ── 变更报告 ──────────────────────────────────────────

    def get_change_overview(self) -> dict[str, Any]:
        """变更统计

        Returns:
            {
                'total': int,
                'by_status': {'draft': int, 'submitted': int, ...},
                'by_domain': {'ELEC': int, 'MECH': int, ...},
            }
        """
        changes = self._change_service.list_all_changes()

        by_status: dict[str, int] = {}
        by_domain: dict[str, int] = {}

        for c in changes:
            status_key = c.status if c.status else ""
            by_status[status_key] = by_status.get(status_key, 0) + 1

            domain_key = c.domain if c.domain else ""
            by_domain[domain_key] = by_domain.get(domain_key, 0) + 1

        log.info(
            "变更统计: total=%d, status=%s, domain=%s",
            len(changes), by_status, by_domain,
        )
        return {
            "total": len(changes),
            "by_status": by_status,
            "by_domain": by_domain,
        }

    # ── 规范报告 ──────────────────────────────────────────

    def get_spec_report(self) -> dict[str, Any]:
        """规范覆盖报告

        基于 spec_registry.json（通过 SpecRegistry）统计每个域的规范总数、
        已存在数、缺失列表。V2.2 Week3 起不再硬编码规范列表。

        Returns:
            {
                'total': int,                    # 规范总数
                'found': int,                    # 已找到文件数
                'missing': int,                  # 缺失文件数
                'by_stack': {                    # 按域分组（保留 by_stack key 向后兼容）
                    'plc': {'total': int, 'found': int, 'missing': list[str]},
                    'python': {'total': int, 'found': int, 'missing': list[str]},
                    'pm': {'total': int, 'found': int, 'missing': list[str]},
                    ...（按 registry 中实际域）
                },
                'missing_codes': list[str],      # 所有缺失的 spec_id
            }

        Raises:
            RuntimeError: 未注入 workspace_root
        """
        if not self._workspace_root:
            raise RuntimeError("未注入 workspace_root，无法生成规范报告")

        # 延迟导入避免循环依赖
        from auto_pm.spec.core.config import DEFAULT_REGISTRY_PATH
        from auto_pm.spec.core.registry import SpecRegistry

        registry = SpecRegistry(Path(self._workspace_root), registry_path=DEFAULT_REGISTRY_PATH)
        if not registry.load():
            # 注册表不存在或格式错误时返回空报告
            log.warning("spec_registry.json 不存在或格式错误: %s", registry.path)
            return {
                "total": 0,
                "found": 0,
                "missing": 0,
                "by_stack": {},
                "missing_codes": [],
            }

        by_stack: dict[str, dict[str, Any]] = {}
        total = 0
        found = 0
        missing = 0
        all_missing_codes: list[str] = []

        for spec_info in registry.list_specs():
            domain = spec_info.domain or "unknown"
            if domain not in by_stack:
                by_stack[domain] = {"total": 0, "found": 0, "missing": []}

            by_stack[domain]["total"] += 1
            total += 1

            canonical = spec_info.canonical_path or ""
            file_exists = bool(canonical) and (
                Path(self._workspace_root) / canonical
            ).exists()
            if file_exists:
                found += 1
                by_stack[domain]["found"] += 1
            else:
                missing += 1
                all_missing_codes.append(spec_info.spec_id)
                by_stack[domain]["missing"].append(spec_info.spec_id)

        log.info(
            "规范覆盖统计: total=%d, found=%d, missing=%d, missing_codes=%s",
            total, found, missing, all_missing_codes,
        )
        return {
            "total": total,
            "found": found,
            "missing": missing,
            "by_stack": by_stack,
            "missing_codes": all_missing_codes,
        }

    # ── 扫描报告 ──────────────────────────────────────────

    def get_scan_report(self) -> dict[str, Any]:
        """扫描日志报告

        从 ScanLogRepository 获取扫描日志统计。

        Returns:
            {
                'latest': dict | None,          # 最近一次扫描日志
                'last_sync_time': str,          # 上次同步时间（YYYY-MM-DD HH:MM）或 '—'
                'is_cache_available': bool,     # DB 缓存是否可用
            }

        Raises:
            RuntimeError: 未注入 DatabaseManager
        """
        if self._db is None:
            raise RuntimeError("未注入 DatabaseManager，无法生成扫描报告")

        # 延迟导入避免循环依赖
        from auto_pm.db.repository import ScanLogRepository

        repo = ScanLogRepository(self._db)
        latest = repo.get_latest()

        last_sync_time = "—"
        if latest:
            timestamp = latest.get("timestamp", "")
            if timestamp:
                last_sync_time = timestamp[:16].replace("T", " ")

        log.info(
            "扫描日志报告: latest=%s, last_sync_time=%s",
            latest, last_sync_time,
        )
        return {
            "latest": latest,
            "last_sync_time": last_sync_time,
            "is_cache_available": True,
        }

    # ── 统一入口 ──────────────────────────────────────────

    def get_report(self, report_type: str) -> dict[str, Any]:
        """统一报告入口

        Args:
            report_type: 报告类型
                - 'project': 项目报告
                - 'change': 变更报告
                - 'spec': 规范报告
                - 'scan': 扫描报告

        Returns:
            报告数据字典

        Raises:
            ValueError: 未知报告类型
            RuntimeError: 缺少必要依赖（如未注入 workspace_root/db）
        """
        if report_type == self.REPORT_PROJECT:
            return self.get_project_overview()
        if report_type == self.REPORT_CHANGE:
            return self.get_change_overview()
        if report_type == self.REPORT_SPEC:
            return self.get_spec_report()
        if report_type == self.REPORT_SCAN:
            return self.get_scan_report()
        raise ValueError(
            f"未知报告类型: {report_type}，支持: {self._REPORT_TYPES}"
        )

    def list_report_types(self) -> tuple[str, ...]:
        """列出支持的报告类型"""
        return self._REPORT_TYPES
