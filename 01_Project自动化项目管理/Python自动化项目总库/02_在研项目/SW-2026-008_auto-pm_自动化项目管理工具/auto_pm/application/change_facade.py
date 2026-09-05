"""PLC-HMI 概念映射：FB_Change 功能块

对应 PLC 的 FB，封装"变更管理"域的完整业务逻辑（创建/编辑/审批/台账对账）。
- 输入引脚：change_service, project_service, ledger_reconciler
- 输出引脚：返回 QueryResult/CommandResult → Bridge Signal 通知画面刷新

--- 原始注释 ---
Change Facade 接口层"""

from typing import Any

from auto_pm.change.ledger_reconciler import LedgerReconciler, ReconcileDiff
from auto_pm.core.protocols import ChangeServiceProtocol, ProjectServiceProtocol
from auto_pm.models import ChangeRequest, ChangeSummary

from auto_pm.ui.contracts.commands.change_commands import (
    CreateChangeCommand,
    TransitionChangeCommand,
)
from auto_pm.ui.contracts.dto.change_dto import (
    ChangeRequestDTO,
    ChangeSummaryDTO,
    ChangeTimelineItemDTO,
    ChangeValidationSummaryDTO,
    LedgerReconcileResultDTO,
)
from auto_pm.ui.contracts.result import CommandResult, QueryResult


class ChangeFacade:
    """提供给 UI 层的 Change 用例聚合入口"""

    def __init__(
        self,
        change_service: ChangeServiceProtocol | None = None,
        project_service: ProjectServiceProtocol | None = None,
        ledger_reconciler: LedgerReconciler | None = None,
    ):
        self._change_service = change_service
        self._project_service = project_service
        self._ledger_reconciler = ledger_reconciler

    @property
    def has_service(self) -> bool:
        return self._change_service is not None

    def _summary_to_dto(self, summary: ChangeSummary) -> ChangeSummaryDTO:
        return ChangeSummaryDTO(
            change_number=summary.change_number,
            project_id=summary.project_id,
            project_name=summary.project_name,
            domain=str(summary.domain),
            business_nature=str(summary.business_nature),
            impact_scope=[str(s) for s in summary.impact_scope],
            status=str(summary.status),
            applicant=summary.applicant,
            apply_date=summary.apply_date,
            title=summary.title,
            urgency=str(summary.urgency),
        )

    def _request_to_dto(self, cr: ChangeRequest) -> ChangeRequestDTO:
        sections = getattr(cr, "sections", {}) or {}
        return ChangeRequestDTO(
            change_number=cr.change_number,
            project_id=cr.project_id,
            project_name=cr.project_name,
            domain=str(cr.domain),
            business_nature=str(cr.business_nature),
            impact_scope=[str(s) for s in cr.impact_scope],
            status=str(cr.status),
            applicant=cr.applicant,
            apply_date=cr.apply_date,
            planned_date=getattr(cr, "planned_date", ""),
            urgency=str(cr.urgency),
            background=getattr(cr, "background", ""),
            necessity=getattr(cr, "necessity", ""),
            references=getattr(cr, "references", ""),
            risk_level=getattr(cr, "risk_level", ""),
            mitigation=getattr(cr, "mitigation", ""),
            propagation_chain=getattr(cr, "propagation_chain", ""),
            file_path=getattr(cr, "file_path", ""),
            sections=sections,
        )

    def list_change_requests(
        self, project_id: str | None = None
    ) -> QueryResult[list[ChangeSummaryDTO]]:
        try:
            if not self._change_service:
                return QueryResult(success=False, message="No change_service", payload=[])
            if project_id:
                summaries = self._change_service.list_change_requests(project_id)
            else:
                summaries = self._change_service.list_all_changes()
            dtos = [self._summary_to_dto(s) for s in summaries]
            return QueryResult(success=True, message="Success", payload=dtos)
        except Exception as e:
            return QueryResult(success=False, message=str(e), payload=[])

    def get_change_detail(
        self, change_id: str, project_id: str | None = None
    ) -> QueryResult[ChangeRequestDTO | None]:
        try:
            if not self._change_service:
                return QueryResult(success=False, message="No change_service", payload=None)
            cr = self._change_service.get_change_request(change_id, project_id=project_id)
            if cr is None:
                return QueryResult(
                    success=False, message=f"Change {change_id} not found", payload=None
                )
            return QueryResult(success=True, message="Success", payload=self._request_to_dto(cr))
        except Exception as e:
            return QueryResult(success=False, message=str(e), payload=None)

    def create_change_request(
        self, command: CreateChangeCommand
    ) -> CommandResult[ChangeRequestDTO | None]:
        try:
            if not self._change_service:
                return CommandResult(success=False, message="No change_service", payload=None)
            # ChangeService.create_change_request requires:
            # project_id, domain, business_nature, impact_scope, applicant, background, necessity
            # M3: impact_scope 从 command 透传（M2 之前硬编码为 []）
            cr = self._change_service.create_change_request(
                project_id=command.project_id,
                domain=command.domain,
                business_nature=command.nature,
                impact_scope=list(command.impact_scope),
                applicant=command.applicant,
                background=command.background,
                necessity=command.necessity,
            )
            return CommandResult(
                success=True, message="Created successfully", payload=self._request_to_dto(cr)
            )
        except Exception as e:
            return CommandResult(success=False, message=str(e), payload=None)

    def transition_change(
        self, command: TransitionChangeCommand
    ) -> CommandResult[ChangeRequestDTO | None]:
        try:
            if not self._change_service:
                return CommandResult(success=False, message="No change_service", payload=None)
            self._change_service.transition_status(
                change_number=command.change_id,
                new_status=command.target_status,
                approver=command.operator,
                comment=command.note or "",
                allow_partial_verification=command.allow_partial_verification,
                project_id=command.project_id,
            )
            # Re-fetch after transition
            cr = self._change_service.get_change_request(
                command.change_id, project_id=command.project_id
            )
            if cr is None:
                return CommandResult(
                    success=False, message="Transitioned but could not fetch", payload=None
                )
            return CommandResult(
                success=True, message="Transitioned successfully", payload=self._request_to_dto(cr)
            )
        except Exception as e:
            return CommandResult(success=False, message=str(e), payload=None)

    def get_change_timeline(
        self, change_id: str, project_id: str | None = None
    ) -> QueryResult[list[ChangeTimelineItemDTO]]:
        """获取变更单审批时间线（M3 新增）

        数据流：ChangeService.list_approval_history() → list[ApprovalRecord]
              → 映射为 list[ChangeTimelineItemDTO]
        """
        try:
            if not self._change_service:
                return QueryResult(success=False, message="No change_service", payload=[])
            records = self._change_service.list_approval_history(change_id, project_id=project_id)
            dtos = [
                ChangeTimelineItemDTO(
                    from_status=str(r.from_status),
                    to_status=str(r.to_status),
                    approver=str(r.approver),
                    comment=str(r.comment or ""),
                    transition_date=str(r.transition_date or ""),
                )
                for r in records
            ]
            return QueryResult(success=True, message="Success", payload=dtos)
        except Exception as e:
            return QueryResult(success=False, message=str(e), payload=[])

    def get_change_validation_summary(
        self, change_id: str, project_id: str | None = None
    ) -> QueryResult[ChangeValidationSummaryDTO | None]:
        """获取变更验证摘要（M3 新增）

        聚合数据：
        - ImpactAnalysis（risk_level / mitigation / propagation_chain / domain_impacts / related_changes）
        - ApprovalHistory 计数 + 最新时间
        - ChangeRequest.current_status
        """
        try:
            if not self._change_service:
                return QueryResult(success=False, message="No change_service", payload=None)

            cr = self._change_service.get_change_request(change_id, project_id=project_id)
            if cr is None:
                return QueryResult(
                    success=False, message=f"Change {change_id} not found", payload=None
                )

            impact = self._change_service.get_impact_analysis(change_id, project_id=project_id)
            approvals = self._change_service.list_approval_history(change_id, project_id=project_id)

            approval_count = len(approvals)
            last_approval_date: str | None = None
            if approvals:
                # list_approval_history 按 id 升序（时间顺序），最后一条为最新
                last_approval_date = (
                    str(getattr(approvals[-1], "transition_date", "") or "") or None
                )

            dto = ChangeValidationSummaryDTO(
                change_number=change_id,
                current_status=str(cr.status),
                risk_level=str(getattr(impact, "risk_level", "")) if impact else "",
                mitigation=str(getattr(impact, "mitigation", "")) if impact else "",
                propagation_chain=str(getattr(impact, "propagation_chain", "")) if impact else "",
                approval_count=approval_count,
                last_approval_date=last_approval_date,
                domain_impacts=dict(getattr(impact, "domain_impacts", {}) or {}) if impact else {},
                related_changes=list(getattr(impact, "related_changes", []) or [])
                if impact
                else [],
            )
            return QueryResult(success=True, message="Success", payload=dto)
        except Exception as e:
            return QueryResult(success=False, message=str(e), payload=None)

    def update_change_request(
        self, change_id: str, updates: dict[str, Any], project_id: str | None = None
    ) -> CommandResult[ChangeRequestDTO | None]:
        """更新变更单（GUI 编辑支持）"""
        try:
            if not self._change_service:
                return CommandResult(success=False, message="No change_service", payload=None)

            cr = self._change_service.update_change_request(
                change_id, lookup_project_id=project_id, **updates
            )
            if cr is None:
                return CommandResult(
                    success=False, message=f"变更单不存在: {change_id}", payload=None
                )

            dto = self._request_to_dto(cr)
            return CommandResult(success=True, message="Success", payload=dto)
        except Exception as e:
            return CommandResult(success=False, message=str(e), payload=None)

    def reconcile_ledger(
        self,
        project_id: str,
        auto_fix: bool = False,
    ) -> CommandResult[LedgerReconcileResultDTO | None]:
        """台账对账：扫描 CHG 文件 vs 版本变更台账（M5 CHG-118 新增）

        Args:
            project_id: 项目编号
            auto_fix: True 时自动补建缺失行 + 修复状态不一致；False 时只读扫描

        Returns:
            CommandResult[LedgerReconcileResultDTO | None]
        """
        try:
            if not self._project_service:
                return CommandResult(success=False, message="No project_service", payload=None)
            if not self._ledger_reconciler:
                return CommandResult(success=False, message="No ledger_reconciler", payload=None)

            project_path = self._project_service.find_project_path(project_id)
            if not project_path:
                return CommandResult(
                    success=False, message=f"项目不存在: {project_id}", payload=None
                )

            if auto_fix:
                diff: ReconcileDiff = self._ledger_reconciler.auto_fix(project_path)
            else:
                diff = self._ledger_reconciler.reconcile(project_path)

            dto = LedgerReconcileResultDTO(
                project_id=project_id,
                is_clean=diff.is_clean,
                missing_in_ledger=list(diff.missing_in_ledger),
                orphan_in_ledger=list(diff.orphan_in_ledger),
                status_mismatches=[list(m) for m in diff.status_mismatches],
                summary=diff.summary(),
                auto_fixed=auto_fix,
            )
            return CommandResult(success=True, message="Success", payload=dto)
        except Exception as e:
            return CommandResult(success=False, message=str(e), payload=None)
