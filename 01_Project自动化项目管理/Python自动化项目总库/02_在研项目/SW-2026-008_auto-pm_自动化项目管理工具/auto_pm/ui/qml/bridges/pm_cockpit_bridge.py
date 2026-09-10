"""Narrow QObject bridge for the safe, user-facing PM cockpit."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Slot

from auto_pm.core.pm_cockpit_service import PmCockpitError, PmCockpitService


class PmCockpitBridge(QObject):
    """Expose only read projections and the two explicit user confirmations to QML."""

    def __init__(
        self,
        workspace_root: str,
        *,
        service: PmCockpitService | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service or PmCockpitService(workspace_root)

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
