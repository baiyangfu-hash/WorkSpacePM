"""PLC-HMI 概念映射：SFB 库函数（驾驶舱数据聚合（项目统计/变更统计/健康度计算））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

项目驾驶舱 Service - 首页聚合统计

聚合 ProjectService / ChangeService / PlcService 的最小首页数据：
- 项目总数
- 阶段分布
- 未关闭变更数
- PLC 检查失败项目数（fail_count > 0）
- PLC 检查不适用项目数（Python 项目，V0.4.1 Step 3 新增）

Week 1 只做数据聚合，不引入新表，不持久化检查结果。
V0.4.1 Step 3: 增加 not_applicable 口径，避免 Python 项目误报为 PLC 检查失败。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

from auto_pm.models import DashboardSummaryDTO

log = logging.getLogger(__name__)


class DashboardService:
    """项目驾驶舱数据聚合服务"""

    _PHASE_KEYS: tuple[str, ...] = (
        "developing",
        "commissioning",
        "production",
        "archived",
    )

    def __init__(
        self,
        project_service: Any,
        change_service: Any,
        plc_service: Any | None = None,
        workspace_root: str | None = None,
    ) -> None:
        self._project_service = project_service
        self._change_service = change_service
        self._plc_service = plc_service
        self._workspace_root = workspace_root

    def get_summary(self) -> DashboardSummaryDTO:
        """返回首页驾驶舱摘要数据"""
        projects = self._project_service.list_projects_cached()
        changes = self._change_service.list_all_changes()

        phase_counts = dict.fromkeys(self._PHASE_KEYS, 0)
        for project in projects:
            phase_key = project.phase or ""
            phase_counts[phase_key] = phase_counts.get(phase_key, 0) + 1

        open_changes = [change for change in changes if change.status != "closed"]
        failed_project_ids, not_applicable_ids = self._collect_plc_check_stats(projects)
        recent_activities = self._collect_recent_activities(projects, changes)
        risk_hints = self._collect_risk_hints(open_changes, failed_project_ids, not_applicable_ids)
        test_pass_rate, test_total = self._collect_test_summary()

        summary = DashboardSummaryDTO(
            total_projects=len(projects),
            phase_counts=phase_counts,
            open_change_count=len(open_changes),
            failed_check_project_count=len(failed_project_ids),
            failed_check_project_ids=failed_project_ids,
            not_applicable_project_count=len(not_applicable_ids),
            not_applicable_project_ids=not_applicable_ids,
            recent_activities=recent_activities,
            risk_hints=risk_hints,
            test_pass_rate=test_pass_rate,
            test_total=test_total,
        )
        log.info(
            "驾驶舱摘要统计: total=%d open_changes=%d failed_checks=%d "
            "not_applicable=%d phases=%s test_rate=%.1f%%(%d)",
            summary.total_projects,
            summary.open_change_count,
            summary.failed_check_project_count,
            summary.not_applicable_project_count,
            summary.phase_counts,
            summary.test_pass_rate,
            summary.test_total,
        )
        return summary

    def get_active_change_for_project(self, project_id: str) -> Any | None:
        """获取项目最近一条活跃变更单

        活跃定义：status 不在 (completed, closed) 中。
        用于平台驾驶舱状态机视图的主线变更展示。

        Args:
            project_id: 项目编号

        Returns:
            最近活跃变更单 ChangeSummary，若无则返回 None
        """
        try:
            changes = self._change_service.list_all_changes(project_id=project_id)
        except Exception as exc:  # pragma: no cover - 防御性日志
            log.warning("查询项目活跃变更失败 %s: %s", project_id, exc)
            return None

        active_changes = [c for c in changes if c.status not in ("completed", "closed")]
        if not active_changes:
            return None

        active_changes.sort(
            key=lambda c: self._parse_date_to_timestamp(c.apply_date),
            reverse=True,
        )
        return active_changes[0]

    def get_change_summary_for_project(self, project_id: str) -> dict[str, Any]:
        """获取项目级变更聚合摘要（项目工作区变更Tab驾驶舱模式）

        返回预计算的 KPI、状态机和活动时间线数据，避免 QML 端重复计算。

        Args:
            project_id: 项目编号

        Returns:
            聚合摘要 dict
        """
        try:
            changes = self._change_service.list_all_changes(project_id=project_id)
        except Exception as exc:
            log.warning("查询项目变更失败 %s: %s", project_id, exc)
            changes = []

        kpi = self._compute_change_kpi(changes)
        state_machine = self._compute_change_state_machine(changes)
        activities = self._compute_change_activities(changes)

        return {
            "kpi": kpi,
            "state_machine": state_machine,
            "activities": activities,
        }

    @staticmethod
    def _compute_change_kpi(changes: list[Any]) -> dict[str, int]:
        """计算变更KPI数据"""
        from datetime import datetime, timedelta

        total = len(changes)
        implementing = 0
        pending_review = 0
        this_week = 0
        today = datetime.now()
        week_ago = today - timedelta(days=7)

        for c in changes:
            status = str(c.status)
            if status == "implementing":
                implementing += 1
            if status in ("under_review", "submitted"):
                pending_review += 1

            apply_date = getattr(c, "apply_date", "")
            if apply_date and apply_date != "待补充":
                try:
                    date_obj = datetime.strptime(apply_date[:10], "%Y-%m-%d")
                    if date_obj >= week_ago:
                        this_week += 1
                except (ValueError, TypeError):
                    pass

        return {
            "total": total,
            "implementing": implementing,
            "pending_review": pending_review,
            "this_week": this_week,
        }

    @staticmethod
    def _compute_change_state_machine(changes: list[Any]) -> dict[str, Any]:
        """计算变更状态机数据"""
        if not changes:
            return {
                "current_node": 0,
                "current_node_name": "无变更",
                "progress": 0,
                "nodes": [],
            }

        sorted_changes = sorted(
            changes,
            key=lambda c: DashboardService._parse_date_to_timestamp(c.apply_date),
            reverse=True,
        )
        latest = sorted_changes[0]

        status_order = [
            "draft",
            "submitted",
            "under_review",
            "approved",
            "implementing",
            "pending_acceptance",
            "accepting",
            "completed",
            "closed",
        ]
        status_names = {
            "draft": "草稿",
            "submitted": "已提交",
            "under_review": "审核中",
            "approved": "已批准",
            "implementing": "实施中",
            "pending_acceptance": "待验收",
            "accepting": "验收中",
            "completed": "已完成",
            "closed": "已关闭",
        }

        latest_status = str(latest.status)
        nodes = []
        for status in status_order:
            idx = status_order.index(status)
            latest_idx = status_order.index(latest_status) if latest_status in status_order else -1
            nodes.append(
                {
                    "name": status_names[status],
                    "status": status,
                    "active": status == latest_status,
                    "completed": idx <= latest_idx,
                }
            )

        current_idx = status_order.index(latest_status) if latest_status in status_order else -1

        return {
            "current_node": current_idx + 1,
            "current_node_name": status_names.get(latest_status, latest_status),
            "progress": ((current_idx + 1) / len(status_order)) * 100 if current_idx >= 0 else 0,
            "nodes": nodes,
        }

    @staticmethod
    def _compute_change_activities(changes: list[Any]) -> list[dict[str, Any]]:
        """生成变更活动时间线"""
        activities = []
        for c in changes:
            apply_date = getattr(c, "apply_date", "")
            activities.append(
                {
                    "time": apply_date,
                    "title": getattr(c, "change_number", ""),
                    "subtitle": getattr(c, "title", ""),
                    "type": str(getattr(c, "status", "default")),
                }
            )
        activities.sort(key=lambda a: (a.get("time") or "", a.get("title") or ""), reverse=True)
        return activities[:10]

    def _collect_recent_activities(
        self,
        projects: list[Any],
        changes: list[Any],
        limit: int = 4,
    ) -> list[dict[str, Any]]:
        """汇总最近活动（最近修改项目 + 最近变更单）"""
        activities: list[tuple[tuple[float, str], dict[str, Any]]] = []

        for project in projects:
            if not project.file_mtime:
                continue
            formatted_time = self._format_timestamp(project.file_mtime)
            activities.append(
                (
                    (float(project.file_mtime), project.project_id),
                    {
                        "type": "default",
                        "title": f"项目更新 {project.project_id}",
                        "desc": project.name or project.project_id,
                        "time": formatted_time,
                    },
                )
            )

        for change in changes:
            sort_key = self._parse_date_to_timestamp(change.apply_date)
            if sort_key <= 0:
                continue
            activity_type = "success" if change.status != "closed" else "default"
            activities.append(
                (
                    (sort_key, change.change_number),
                    {
                        "type": activity_type,
                        "title": f"变更单 {change.change_number}",
                        "desc": f"状态: {change.status} | 申请日期: {change.apply_date}",
                        "time": change.apply_date,
                    },
                )
            )

        activities.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in activities[:limit]]

    def _collect_plc_check_stats(self, projects: list[Any]) -> tuple[list[str], list[str]]:
        """一次遍历收集 PLC 检查统计

        V0.4.1 Step 3: 合并 failed + not_applicable 收集，避免重复跑 PlcChecker.check。
        not_applicable 短路返回不跑 5 项检查，性能开销可忽略。

        Returns:
            (failed_project_ids, not_applicable_project_ids) 元组
        """
        if self._plc_service is None:
            return [], []

        failed_project_ids: list[str] = []
        not_applicable_project_ids: list[str] = []
        for project in projects:
            try:
                result = self._plc_service.check(project.path)
            except Exception as exc:  # pragma: no cover - 防御性日志
                log.warning("驾驶舱检查项目失败，已跳过: %s: %s", project.project_id, exc)
                continue
            if result.not_applicable:
                not_applicable_project_ids.append(project.project_id)
                continue
            if result.fail_count > 0:
                failed_project_ids.append(project.project_id)
        return failed_project_ids, not_applicable_project_ids

    def _collect_test_summary(self) -> tuple[float, int]:
        """收集测试通过率摘要"""
        cache_dir = self._find_pytest_cache()
        if not cache_dir:
            return 0.0, 0

        nodeids_file = os.path.join(cache_dir, "v", "cache", "nodeids")
        lastfailed_file = os.path.join(cache_dir, "v", "cache", "lastfailed")

        try:
            with open(nodeids_file, encoding="utf-8") as f:
                nodeids_data = json.load(f)
            total = len(nodeids_data) if isinstance(nodeids_data, (dict, list)) else 0
        except (OSError, json.JSONDecodeError):
            log.debug("pytest nodeids 读取失败: %s", nodeids_file)
            return 0.0, 0

        if total == 0:
            return 0.0, 0

        try:
            with open(lastfailed_file, encoding="utf-8") as f:
                lastfailed_data = json.load(f)
            failed = len(lastfailed_data) if isinstance(lastfailed_data, dict) else 0
        except (OSError, json.JSONDecodeError):
            failed = 0

        passed = total - failed
        pass_rate = round((passed / total) * 100, 1) if total > 0 else 0.0
        log.debug("测试统计: total=%d failed=%d pass_rate=%.1f%%", total, failed, pass_rate)
        return pass_rate, total

    def _find_pytest_cache(self) -> str | None:
        """定位 .pytest_cache 目录"""
        try:
            projects = self._project_service.list_projects_cached()
            for project in projects:
                if getattr(project, "stack", "") == "python":
                    candidate = os.path.join(project.path, ".pytest_cache")
                    if os.path.isdir(candidate):
                        return candidate
        except Exception as exc:  # pragma: no cover - 防御性日志
            log.warning("查找 .pytest_cache 时列举项目失败: %s", exc)

        if self._workspace_root:
            candidate = os.path.join(self._workspace_root, ".pytest_cache")
            if os.path.isdir(candidate):
                return candidate

        return None

    @staticmethod
    def _collect_risk_hints(
        open_changes: list[Any],
        failed_project_ids: list[str],
        not_applicable_project_ids: list[str] | None = None,
    ) -> list[str]:
        """生成首页风险提示文案"""
        hints: list[str] = []
        if open_changes:
            hints.append(f"存在 {len(open_changes)} 条未关闭变更，建议优先清理实施中和待验收项")
        if failed_project_ids:
            joined_ids = ", ".join(failed_project_ids[:3])
            suffix = " 等" if len(failed_project_ids) > 3 else ""
            hints.append(f"PLC 检查失败项目: {joined_ids}{suffix}")
        if not_applicable_project_ids:
            count = len(not_applicable_project_ids)
            hints.append(f"PLC 检查不适用项目: {count} 个（Python 项目，已跳过 PLC 检查）")
        if not hints:
            hints.append("当前未发现高优先级风险")
        return hints

    @staticmethod
    def _format_timestamp(timestamp: float) -> str:
        """格式化时间戳为 YYYY-MM-DD HH:MM"""
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")

    @staticmethod
    def _parse_date_to_timestamp(value: str) -> float:
        """解析 YYYY-MM-DD / YYYY-MM-DD HH:MM[:SS] 日期字符串"""
        if not value or value == "待补充":
            return 0.0
        normalized = value.strip().replace("T", " ")
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(normalized, fmt).replace(tzinfo=UTC).timestamp()
            except ValueError:
                continue
        return 0.0
