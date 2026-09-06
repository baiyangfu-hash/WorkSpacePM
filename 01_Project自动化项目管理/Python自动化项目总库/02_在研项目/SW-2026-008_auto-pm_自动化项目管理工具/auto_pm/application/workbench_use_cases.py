"""Workbench 业务编排逻辑。"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from auto_pm.core.protocols import (
    AssetSummaryServiceProtocol,
    DashboardServiceProtocol,
    ProjectServiceProtocol,
    TemplateServiceProtocol,
)

from auto_pm.domain.project.state_machine import build_change_state_machine
from auto_pm.ui.contracts.dto.workbench_dto import (
    ClearCacheResultDTO,
    DashboardSnapshotDTO,
    ProjectCardDTO,
    ProjectWorkspaceDTO,
    RebuildIndexResultDTO,
    SettingsSummaryDTO,
)

log = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class QueryOutcome(Generic[T]):
    success: bool
    message: str
    payload: T | None = None
    errors: list[str] | None = None


@dataclass(frozen=True)
class CommandOutcome(Generic[T]):
    success: bool
    message: str
    payload: T | None = None


class WorkbenchUseCases:
    """承载 Workbench 的业务编排与状态转换。"""

    def __init__(
        self,
        project_service: ProjectServiceProtocol,
        dashboard_service: DashboardServiceProtocol | None = None,
        asset_summary_service: AssetSummaryServiceProtocol | None = None,
        template_service: TemplateServiceProtocol | None = None,
        change_service: Any = None,
        reload_callback: Any = None,
    ) -> None:
        self.project_service = project_service
        self.dashboard_service = dashboard_service
        self.asset_summary_service = asset_summary_service
        self.template_service = template_service
        self.change_service = change_service
        self.reload_callback = reload_callback

    def get_dashboard_snapshot(self) -> QueryOutcome[DashboardSnapshotDTO]:
        if not self.dashboard_service:
            return QueryOutcome(False, "DashboardService 未启用", errors=["DashboardService 未启用"])
        try:
            summary = self.dashboard_service.get_summary()
            return QueryOutcome(
                True,
                "Success",
                DashboardSnapshotDTO(
                    total_projects=summary.total_projects,
                    phase_counts=summary.phase_counts,
                    open_change_count=summary.open_change_count,
                    failed_check_project_count=summary.failed_check_project_count,
                    not_applicable_project_count=summary.not_applicable_project_count,
                    recent_activities=summary.recent_activities,
                    risk_hints=summary.risk_hints,
                    failed_check_project_ids=summary.failed_check_project_ids,
                    not_applicable_project_ids=summary.not_applicable_project_ids,
                    tech_debt_count=summary.tech_debt_count,
                    tech_debt_total=summary.tech_debt_total,
                    test_pass_rate=summary.test_pass_rate,
                    test_total=summary.test_total,
                ),
            )
        except Exception as exc:
            return QueryOutcome(False, str(exc), errors=[str(exc)])

    def get_active_change_status(self, project_id: str) -> QueryOutcome[dict[str, Any]]:
        if not self.dashboard_service:
            return QueryOutcome(False, "DashboardService 未启用", errors=["DashboardService 未启用"])
        try:
            change = self.dashboard_service.get_active_change_for_project(project_id)
            if change is None:
                return QueryOutcome(
                    True,
                    "No active change",
                    {
                        "active": False,
                        "change_number": "",
                        "title": "",
                        "status": "",
                        "apply_date": "",
                        "state_machine": build_change_state_machine("draft"),
                    },
                )
            return QueryOutcome(
                True,
                "Success",
                {
                    "active": True,
                    "change_number": change.change_number,
                    "title": change.title or change.change_number,
                    "status": change.status,
                    "apply_date": change.apply_date,
                    "state_machine": build_change_state_machine(change.status),
                },
            )
        except Exception as exc:
            return QueryOutcome(False, str(exc), errors=[str(exc)])

    def get_project_change_summary(self, project_id: str) -> QueryOutcome[dict[str, Any]]:
        if not self.dashboard_service:
            return QueryOutcome(False, "DashboardService 未启用", errors=["DashboardService 未启用"])
        try:
            payload = self.dashboard_service.get_change_summary_for_project(project_id)
            return QueryOutcome(True, "Success", payload)
        except Exception as exc:
            return QueryOutcome(False, str(exc), errors=[str(exc)])

    def list_project_cards(self) -> QueryOutcome[list[ProjectCardDTO]]:
        try:
            try:
                items = self.project_service.list_projects_with_change_count()
            except RuntimeError:
                projects = self.project_service.list_projects()
                return QueryOutcome(
                    True,
                    "Success",
                    [
                        ProjectCardDTO(
                            project_id=project.project_id,
                            name=project.name,
                            stack=str(project.stack),
                            phase=str(project.phase),
                            version=project.version,
                            health_status="Unknown",
                            open_change_count=0,
                            last_activity_at=self._get_last_activity_at(project.path),
                            path=project.path,
                            business_line=str(project.business_line),
                        )
                        for project in projects
                    ],
                )
            return QueryOutcome(
                True,
                "Success",
                [
                    ProjectCardDTO(
                        project_id=item.project_id,
                        name=item.name,
                        stack=str(item.stack),
                        phase=str(item.phase),
                        version=item.version,
                        health_status="Has Changes" if item.change_count > 0 else "Normal",
                        open_change_count=item.change_count,
                        last_activity_at=self._get_last_activity_at(item.path),
                        path=item.path,
                        business_line=str(item.business_line),
                    )
                    for item in items
                ],
            )
        except Exception as exc:
            return QueryOutcome(False, str(exc), errors=[str(exc)])

    def get_project_workspace(self, project_id: str) -> QueryOutcome[ProjectWorkspaceDTO]:
        try:
            project = self.project_service.get_project(project_id)
            if not project:
                return QueryOutcome(
                    False,
                    f"Project not found: {project_id}",
                    errors=["ProjectNotFound"],
                )
            summary = project.model_dump() if hasattr(project, "model_dump") else {}
            for key, value in summary.items():
                if hasattr(value, "value"):
                    summary[key] = str(value.value)
            asset_summary = None
            if self.asset_summary_service:
                asset_summary = self.asset_summary_service.build_summary(
                    project_path=project.path,
                    stack=str(project.stack),
                    project_type=project.project_type,
                )
            return QueryOutcome(
                True,
                "Success",
                ProjectWorkspaceDTO(
                    project_id=project_id,
                    summary=summary,
                    asset_summary=asset_summary,
                    document_status=None,
                    vartable_status=None,
                    pending_actions=self._build_pending_actions(project_id),
                ),
            )
        except Exception as exc:
            return QueryOutcome(False, str(exc), errors=[str(exc)])

    def get_settings_summary(self) -> QueryOutcome[SettingsSummaryDTO]:
        try:
            db_path = self.project_service.get_db_path()
            db_available = self.project_service.is_cache_available()
            project_count = self.project_service.get_project_count()
            try:
                last_sync = self.project_service.get_last_sync_time()
            except Exception as exc:
                log.warning("获取最后同步时间失败: %s", exc, exc_info=True)
                last_sync = "—"
            return QueryOutcome(
                True,
                "Success",
                SettingsSummaryDTO(
                    workspace_root=self.project_service.workspace_root,
                    db_path=db_path,
                    project_count=project_count,
                    last_sync=last_sync,
                    db_available=db_available,
                ),
            )
        except Exception as exc:
            return QueryOutcome(False, str(exc))

    def clear_cache(self) -> CommandOutcome[ClearCacheResultDTO]:
        try:
            if not self.project_service.is_cache_available():
                payload = ClearCacheResultDTO(False, "DB 未初始化，无需清除")
                return CommandOutcome(False, payload.message, payload)
            result = self.project_service.clear_cache()
            payload = ClearCacheResultDTO(
                success=result["success"],
                message=result["message"],
            )
            return CommandOutcome(True, payload.message, payload)
        except Exception as exc:
            return CommandOutcome(
                False,
                str(exc),
                ClearCacheResultDTO(False, f"清除缓存失败: {exc}"),
            )

    def rebuild_index(self) -> CommandOutcome[RebuildIndexResultDTO]:
        try:
            if not self.project_service.is_cache_available():
                payload = RebuildIndexResultDTO(0, 0, "DB 未初始化，无法重建索引")
                return CommandOutcome(False, payload.message, payload)
            result = self.project_service.sync_to_cache(force_full=True)
            payload = RebuildIndexResultDTO(
                projects_found=int(result.get("projects_found", 0)),
                changes_found=int(result.get("changes_found", 0)),
                message=(
                    f"重建完成：发现 {int(result.get('projects_found', 0))} 个项目，"
                    f"{int(result.get('changes_found', 0))} 条变更单"
                ),
            )
            return CommandOutcome(True, "Success", payload)
        except Exception as exc:
            return CommandOutcome(
                False,
                str(exc),
                RebuildIndexResultDTO(0, 0, f"重建索引失败: {exc}"),
            )

    def create_project(
        self,
        project_id: str,
        project_name: str,
        stack: str,
        mode: str,
        business_line: str,
        dest_dir: str = "",
    ) -> CommandOutcome[dict[str, Any] | None]:
        try:
            if not self.template_service:
                return CommandOutcome(False, "TemplateService 未注入")
            from auto_pm.core.constants import get_template_name
            from auto_pm.core.paths import get_default_projects_dir

            dest_root = os.path.abspath(dest_dir) if dest_dir else get_default_projects_dir()
            project_dir = f"{project_id}_{project_name}"
            dest_path = os.path.abspath(os.path.join(dest_root, project_dir))
            if os.path.exists(dest_path):
                return CommandOutcome(False, f"目标路径已存在: {dest_path}")

            template_name = get_template_name(stack, mode if stack == "plc" else "")
            if not business_line:
                business_line = project_id.split("-", 1)[0] if "-" in project_id else ""
            os.makedirs(dest_root, exist_ok=True)
            self.template_service.copy_template(
                template_name,
                dest_path,
                {
                    "project_id": project_id,
                    "project_name": project_name,
                    "description": project_name,
                    "version": "V1.0.0",
                    "stack": stack,
                    "mode": mode if stack == "plc" else "",
                    "business_line": business_line,
                },
            )
            if hasattr(self.project_service, "retrofit_project_by_path"):
                try:
                    self.project_service.retrofit_project_by_path(dest_path)
                except Exception:
                    pass
            self.project_service.sync_to_cache(force_full=True)
            try:
                from auto_pm.logging.audit import audit_log

                audit_log(
                    "project_create",
                    project_id=project_id,
                    project_name=project_name,
                    stack=stack,
                    mode=mode if stack == "plc" else "",
                    business_line=business_line,
                    path=dest_path,
                )
            except Exception:
                pass
            return CommandOutcome(
                True,
                f"项目创建成功: {project_id}",
                {"project_id": project_id, "path": dest_path},
            )
        except Exception as exc:
            return CommandOutcome(False, str(exc))

    def generate_project_code(self, business_line: str) -> CommandOutcome[str]:
        try:
            return CommandOutcome(True, "", self.project_service.generate_project_code(business_line))
        except Exception as exc:
            return CommandOutcome(False, str(exc))

    def detect_project(self, path: str) -> CommandOutcome[dict[str, Any] | None]:
        try:
            from auto_pm.core.project_scanner import ProjectScanner

            scanner = ProjectScanner(self.project_service.workspace_root)
            project = scanner.try_identify_project(path)
            if project:
                return CommandOutcome(
                    True,
                    "",
                    {
                        "project_id": project.project_id,
                        "name": project.name,
                        "stack": str(project.stack),
                    },
                )
            return CommandOutcome(False, "无法在此路径下识别到有效的项目元数据文件")
        except Exception as exc:
            return CommandOutcome(False, str(exc))

    def import_project(self, src_path: str) -> CommandOutcome[dict[str, Any] | None]:
        try:
            from auto_pm.core.project_scanner import ProjectScanner

            dest_path = self.project_service.import_project(src_path)
            scanner = ProjectScanner(self.project_service.workspace_root)
            project = scanner.try_identify_project(dest_path)
            project_id = project.project_id if project else os.path.basename(dest_path)
            return CommandOutcome(
                True,
                f"项目导入成功: {project_id}",
                {"project_id": project_id, "path": dest_path},
            )
        except Exception as exc:
            return CommandOutcome(False, str(exc))

    def edit_project(self, project_id: str, **kwargs: str) -> CommandOutcome[dict[str, Any] | None]:
        try:
            updated = self.project_service.update_project_meta(project_id, **kwargs)
            self.project_service.sync_to_cache(force_full=True)
            summary = updated.model_dump() if hasattr(updated, "model_dump") else {}
            return CommandOutcome(
                True,
                f"项目元数据已更新: {project_id}",
                {"project_id": project_id, "fields": kwargs, "summary": summary},
            )
        except FileNotFoundError:
            return CommandOutcome(False, f"项目不存在: {project_id}")
        except Exception as exc:
            return CommandOutcome(False, str(exc))

    def delete_project(self, project_id: str) -> CommandOutcome[dict[str, Any] | None]:
        try:
            import shutil

            project = self.project_service.get_project(project_id)
            if project is None:
                return CommandOutcome(False, f"项目不存在: {project_id}")
            shutil.rmtree(project.path)
            from auto_pm.logging.audit import audit_log

            audit_log(
                "project_delete",
                project_id=project_id,
                project_name=project.name,
                path=project.path,
            )
            self.project_service.sync_to_cache(force_full=True)
            return CommandOutcome(
                True,
                f"项目已删除: {project_id}",
                {"project_id": project_id, "name": project.name},
            )
        except Exception as exc:
            return CommandOutcome(False, str(exc))

    def save_workspace_root(self, workspace_root: str) -> CommandOutcome[dict[str, Any]]:
        try:
            from auto_pm.core.paths import get_config_file_path

            workspace_root = os.path.abspath(workspace_root)
            if not os.path.isdir(workspace_root):
                return CommandOutcome(
                    False,
                    f"路径不存在或不是目录: {workspace_root}",
                    {
                        "config_saved": False,
                        "runtime_reloaded": False,
                        "workspace_root": workspace_root,
                    },
                )
            config_file = get_config_file_path()
            os.makedirs(os.path.dirname(config_file), exist_ok=True)
            with open(config_file, "w", encoding="utf-8") as file:
                file.write(workspace_root)
            payload: dict[str, Any] = {
                "config_saved": True,
                "runtime_reloaded": False,
                "workspace_root": workspace_root,
            }
            if not self.reload_callback:
                return CommandOutcome(
                    True,
                    f"配置已保存到: {workspace_root}；当前运行态未执行重载",
                    payload,
                )
            reload_result = self.reload_callback(workspace_root)
            payload["runtime_reloaded"] = bool(reload_result.get("success"))
            payload["reload_message"] = reload_result.get("message", "")
            payload["reloaded_workspace_root"] = reload_result.get(
                "workspace_root", workspace_root
            )
            if payload["runtime_reloaded"]:
                return CommandOutcome(
                    True,
                    f"配置已保存，运行态已重载到: {workspace_root}",
                    payload,
                )
            return CommandOutcome(
                False,
                f"配置已保存，但运行态重载失败: {reload_result.get('message', '未知错误')}",
                payload,
            )
        except Exception as exc:
            return CommandOutcome(
                False,
                f"保存失败: {exc}",
                {
                    "config_saved": False,
                    "runtime_reloaded": False,
                    "workspace_root": workspace_root,
                },
            )

    def initialize_project_pm(self, project_id: str) -> CommandOutcome[dict[str, Any]]:
        try:
            project = self.project_service.get_project(project_id)
            if not project:
                return CommandOutcome(False, f"未找到项目: {project_id}", {"success": False})

            stack_str = str(project.stack).lower()
            self.project_service.init_project_pm_framework(
                project_path=project.path,
                project_id=project_id,
                project_name=project.name,
                stack_type=stack_str,
            )
            if self.change_service:
                applicant = os.getenv("AUTO_PM_AUTHOR", os.getlogin())
                domain = "PLC" if stack_str == "plc" else "SCPT"
                self.change_service.create_change_request(
                    project_id=project_id,
                    domain=domain,
                    business_nature="DEF",
                    impact_scope=["LOCAL"],
                    applicant=applicant,
                    background="项目 PM 连续性基础文档与变更管理机制初始化。",
                    necessity="对齐规范管理，启用变更管理与对账自愈系统。",
                    retrofit=True,
                )
            self.project_service.sync_to_cache(force_full=True)
            return CommandOutcome(
                True,
                "项目 PM 与变更管理规范初始化成功",
                {"success": True, "project_id": project_id},
            )
        except Exception as exc:
            log.error("初始化项目 PM 失败: %s", exc, exc_info=True)
            return CommandOutcome(False, str(exc), {"success": False})

    def is_git_hooks_installed(self, project_id: str) -> CommandOutcome[bool]:
        try:
            project = self.project_service.get_project(project_id)
            if not project:
                return CommandOutcome(False, f"项目不存在: {project_id}", False)
            return CommandOutcome(
                True,
                "",
                self.project_service.is_git_hooks_installed(project.path),
            )
        except Exception as exc:
            return CommandOutcome(False, str(exc), False)

    def install_git_hooks(self, project_id: str) -> CommandOutcome[dict[str, Any]]:
        try:
            project = self.project_service.get_project(project_id)
            if not project:
                return CommandOutcome(False, f"项目不存在: {project_id}", {"success": False})
            result = self.project_service.install_git_hooks(project.path)
            return CommandOutcome(bool(result["success"]), result["message"], result)
        except Exception as exc:
            return CommandOutcome(False, str(exc), {"success": False, "message": str(exc)})

    def uninstall_git_hooks(self, project_id: str) -> CommandOutcome[dict[str, Any]]:
        try:
            project = self.project_service.get_project(project_id)
            if not project:
                return CommandOutcome(False, f"项目不存在: {project_id}", {"success": False})
            result = self.project_service.uninstall_git_hooks(project.path)
            return CommandOutcome(bool(result["success"]), result["message"], result)
        except Exception as exc:
            return CommandOutcome(False, str(exc), {"success": False, "message": str(exc)})

    def evaluate_stage_gate(
        self,
        project_id: str,
        current_stage: str = "initiating",
        target_stage: str = "planning",
    ) -> CommandOutcome[dict[str, Any] | None]:
        try:
            from auto_pm.core.gates import StageGateEngine

            project = self.project_service.get_project(project_id)
            if not project:
                return CommandOutcome(False, f"项目不存在: {project_id}")
            engine = StageGateEngine(workspace_root=self.project_service.workspace_root)
            gate_result = engine.evaluate_stage_transition(
                project_path=project.path,
                current_stage=current_stage,
                target_stage=target_stage,
            )
            return CommandOutcome(
                True,
                "门禁评估完成" if gate_result.can_proceed else "存在阻断项，无法流转",
                gate_result.to_dict(),
            )
        except Exception as exc:
            log.error("门禁评估失败: %s", exc, exc_info=True)
            return CommandOutcome(False, str(exc))

    @staticmethod
    def _get_last_activity_at(project_path: str) -> str | None:
        try:
            return datetime.fromtimestamp(os.path.getmtime(project_path), tz=UTC).isoformat()
        except (OSError, FileNotFoundError):
            return None

    def _build_pending_actions(self, project_id: str) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        if not self.dashboard_service:
            return actions
        try:
            summary = self.dashboard_service.get_change_summary_for_project(project_id)
            total = summary.get("kpi", {}).get("total", 0)
            if total > 0:
                actions.append(
                    {
                        "type": "open_changes",
                        "label": f"{total} 个开放变更单",
                        "count": total,
                        "implementing": summary.get("kpi", {}).get("implementing", 0),
                        "pending_review": summary.get("kpi", {}).get("pending_review", 0),
                    }
                )
        except Exception:
            pass
        return actions
