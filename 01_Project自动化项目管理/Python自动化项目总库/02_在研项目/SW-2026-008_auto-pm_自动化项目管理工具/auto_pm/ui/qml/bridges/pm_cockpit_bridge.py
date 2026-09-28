"""Narrow QObject bridge for the safe, user-facing PM cockpit."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from PySide6.QtCore import QObject, Slot

from auto_pm.contracts.pm_facade import PmIntent
from auto_pm.core.pm_cockpit_service import PmCockpitError, PmCockpitService
from auto_pm.core.pm_facade_service import PmFacadeError, PmFacadeService


class PmCockpitBridge(QObject):
    """Expose the planning draft and explicit user confirmations to QML."""

    def __init__(
        self,
        workspace_root: str,
        *,
        service: PmCockpitService | None = None,
        facade: PmFacadeService | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service or PmCockpitService(workspace_root)
        self._facade = facade or PmFacadeService(workspace_root)
        self._planning_input: tuple[str, str, tuple[str, ...]] | None = None
        self._planning_request_id: str | None = None

    @Slot(result="QVariant")
    def loadSnapshot(self) -> dict[str, Any]:
        """Load the default screen without initializing any application state."""
        snapshot = self._service.snapshot()
        return {"success": True, "snapshot": snapshot.model_dump(mode="json")}

    @Slot(str, result="QVariant")
    def loadEvidence(self, project_id: str) -> dict[str, Any]:
        """Load the selected card's bounded evidence drawer."""
        try:
            evidence = self._service.evidence(project_id)
        except PmCockpitError as error:
            return {"success": False, "message": str(error), "evidence": {}}
        return {"success": True, "evidence": evidence.model_dump(mode="json")}

    @Slot(str, str, str, result="QVariant")
    def createPlanningDraft(
        self, project_id: str, objective: str, acceptance_text: str
    ) -> dict[str, Any]:
        """Persist only a validated PRE_AUTH draft; keep its request key internal."""
        project_id = project_id.strip()
        objective = objective.strip()
        criteria = tuple(line.strip() for line in acceptance_text.splitlines() if line.strip())
        if not project_id or not objective or not criteria:
            return {"success": False, "message": "请选择项目，并填写目标和明确验收。"}
        try:
            projects = self._service.snapshot().projects
            if project_id not in {card.project_id for card in projects}:
                return {"success": False, "message": "所选项目不在工作空间项目清单中。"}
            current_input = (project_id, objective, criteria)
            request_id = self._planning_request_id
            if current_input != self._planning_input or request_id is None:
                request_id = f"REQ-COCKPIT-{uuid4().hex.upper()}"
            intent = PmIntent(
                request_id=request_id,
                subject_project_id=project_id,
                objective=objective,
                acceptance_criteria=criteria,
            )
            self._planning_input = current_input
            self._planning_request_id = request_id
            draft = self._facade.create_planning_draft(intent)
        except (PmCockpitError, PmFacadeError, ValidationError, OSError, ValueError) as error:
            return {"success": False, "message": f"草稿未保存：{error}"}
        return {
            "success": True,
            "message": "规划草稿已保存，范围待规划。",
            "draft": {
                "project_id": draft.subject_project_id,
                "objective": draft.objective,
                "acceptance_criteria": list(draft.acceptance_criteria),
                "state": draft.state,
                "scope_status": "范围待规划",
            },
        }

    @Slot(str, result="QVariant")
    def confirmStart(self, mission_id: str) -> dict[str, Any]:
        """Apply one explicit start confirmation; no internal Work identifier is accepted."""
        return self._confirmation_result("start", mission_id)

    @Slot(str, result="QVariant")
    def confirmAcceptance(self, mission_id: str) -> dict[str, Any]:
        """Apply one explicit final acceptance after the verification gate has opened."""
        return self._confirmation_result("acceptance", mission_id)

    def _confirmation_result(self, action: str, mission_id: str) -> dict[str, Any]:
        if not mission_id.strip():
            return {"success": False, "message": "未找到可确认的需求。"}
        try:
            card = (
                self._service.confirm_start(mission_id)
                if action == "start"
                else self._service.confirm_acceptance(mission_id)
            )
        except PmCockpitError as error:
            return {"success": False, "message": str(error)}
        return {
            "success": True,
            "message": card.summary,
            "confirmation": card.model_dump(mode="json"),
        }
