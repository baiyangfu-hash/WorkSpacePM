from __future__ import annotations

from typing import Any, TypeVar

from auto_pm.core.protocols import (
    AssetSummaryServiceProtocol,
    DashboardServiceProtocol,
    ProjectServiceProtocol,
    TemplateServiceProtocol,
)

from auto_pm.application.workbench_use_cases import (
    CommandOutcome,
    QueryOutcome,
    WorkbenchUseCases,
)
from auto_pm.ui.contracts.dto.workbench_dto import (
    ClearCacheResultDTO,
    DashboardSnapshotDTO,
    ProjectCardDTO,
    ProjectWorkspaceDTO,
    RebuildIndexResultDTO,
    SettingsSummaryDTO,
)
from auto_pm.ui.contracts.result import CommandResult, QueryResult

T = TypeVar("T")


class WorkbenchFacade:
    def __init__(
        self,
        project_service: ProjectServiceProtocol,
        dashboard_service: DashboardServiceProtocol | None = None,
        asset_summary_service: AssetSummaryServiceProtocol | None = None,
        template_service: TemplateServiceProtocol | None = None,
        change_service: Any = None,
        reload_callback: Any = None,
    ) -> None:
        self._use_cases = WorkbenchUseCases(
            project_service=project_service,
            dashboard_service=dashboard_service,
            asset_summary_service=asset_summary_service,
            template_service=template_service,
            change_service=change_service,
            reload_callback=reload_callback,
        )

    @property
    def has_project_service(self) -> bool:
        return self._use_cases.project_service is not None

    @property
    def has_dashboard_service(self) -> bool:
        return self._use_cases.dashboard_service is not None

    @property
    def _project_service(self) -> ProjectServiceProtocol:
        return self._use_cases.project_service

    @_project_service.setter
    def _project_service(self, service: ProjectServiceProtocol) -> None:
        self._use_cases.project_service = service

    @property
    def _dashboard_service(self) -> DashboardServiceProtocol | None:
        return self._use_cases.dashboard_service

    @_dashboard_service.setter
    def _dashboard_service(self, service: DashboardServiceProtocol | None) -> None:
        self._use_cases.dashboard_service = service

    @property
    def _reload_callback(self) -> Any:
        return self._use_cases.reload_callback

    @_reload_callback.setter
    def _reload_callback(self, callback: Any) -> None:
        self._use_cases.reload_callback = callback
    def get_dashboard_snapshot(self) -> QueryResult[DashboardSnapshotDTO]:
        return self._to_query_result(self._use_cases.get_dashboard_snapshot())
    def get_active_change_status(self, project_id: str) -> QueryResult[dict[str, Any]]:
        return self._to_query_result(self._use_cases.get_active_change_status(project_id))
    def get_project_change_summary(self, project_id: str) -> QueryResult[dict[str, Any]]:
        return self._to_query_result(self._use_cases.get_project_change_summary(project_id))
    def list_project_cards(self) -> QueryResult[list[ProjectCardDTO]]:
        return self._to_query_result(self._use_cases.list_project_cards())
    def get_project_workspace(self, project_id: str) -> QueryResult[ProjectWorkspaceDTO]:
        return self._to_query_result(self._use_cases.get_project_workspace(project_id))
    def get_settings_summary(self) -> QueryResult[SettingsSummaryDTO]:
        return self._to_query_result(self._use_cases.get_settings_summary())
    def clear_cache(self) -> CommandResult[ClearCacheResultDTO]:
        return self._to_command_result(self._use_cases.clear_cache())
    def rebuild_index(self) -> CommandResult[RebuildIndexResultDTO]:
        return self._to_command_result(self._use_cases.rebuild_index())

    def create_project(
        self,
        project_id: str,
        project_name: str,
        stack: str,
        mode: str,
        business_line: str,
        dest_dir: str = "",
    ) -> CommandResult[dict[str, Any] | None]:
        return self._to_command_result(
            self._use_cases.create_project(
                project_id=project_id,
                project_name=project_name,
                stack=stack,
                mode=mode,
                business_line=business_line,
                dest_dir=dest_dir,
            )
        )
    def generate_project_code(self, business_line: str) -> CommandResult[str]:
        return self._to_command_result(self._use_cases.generate_project_code(business_line))
    def detect_project(self, path: str) -> CommandResult[dict[str, Any] | None]:
        return self._to_command_result(self._use_cases.detect_project(path))
    def import_project(self, src_path: str) -> CommandResult[dict[str, Any] | None]:
        return self._to_command_result(self._use_cases.import_project(src_path))
    def edit_project(self, project_id: str, **kwargs: str) -> CommandResult[dict[str, Any] | None]:
        return self._to_command_result(self._use_cases.edit_project(project_id, **kwargs))
    def delete_project(self, project_id: str) -> CommandResult[dict[str, Any] | None]:
        return self._to_command_result(self._use_cases.delete_project(project_id))
    def save_workspace_root(self, workspace_root: str) -> CommandResult[dict[str, Any]]:
        return self._to_command_result(self._use_cases.save_workspace_root(workspace_root))
    def initialize_project_pm(self, project_id: str) -> CommandResult[dict[str, Any]]:
        return self._to_command_result(self._use_cases.initialize_project_pm(project_id))
    def is_git_hooks_installed(self, project_id: str) -> CommandResult[bool]:
        return self._to_command_result(self._use_cases.is_git_hooks_installed(project_id))
    def install_git_hooks(self, project_id: str) -> CommandResult[dict[str, Any]]:
        return self._to_command_result(self._use_cases.install_git_hooks(project_id))
    def uninstall_git_hooks(self, project_id: str) -> CommandResult[dict[str, Any]]:
        return self._to_command_result(self._use_cases.uninstall_git_hooks(project_id))
    def evaluate_stage_gate(
        self,
        project_id: str,
        current_stage: str = "initiating",
        target_stage: str = "planning",
    ) -> CommandResult[dict[str, Any] | None]:
        return self._to_command_result(
            self._use_cases.evaluate_stage_gate(project_id, current_stage, target_stage)
        )
    @staticmethod
    def _to_query_result(outcome: QueryOutcome[T]) -> QueryResult[T]:
        return QueryResult(
            success=outcome.success,
            message=outcome.message,
            payload=outcome.payload,
            errors=outcome.errors or [],
        )
    @staticmethod
    def _to_command_result(outcome: CommandOutcome[T]) -> CommandResult[T]:
        return CommandResult(
            success=outcome.success,
            message=outcome.message,
            payload=outcome.payload,
        )
