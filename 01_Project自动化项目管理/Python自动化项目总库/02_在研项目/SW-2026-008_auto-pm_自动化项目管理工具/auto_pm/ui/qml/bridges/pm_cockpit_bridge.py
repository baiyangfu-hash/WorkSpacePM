"""Narrow QObject bridge for the safe, user-facing PM cockpit."""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot

from auto_pm.contracts.pm_facade import PmIntent
from auto_pm.core.pm_cockpit_service import PmCockpitError, PmCockpitService
from auto_pm.core.pm_facade_service import PmFacadeError, PmFacadeService

log = logging.getLogger(__name__)


class _StartWorker(QRunnable):
    """Run one approved Mission without blocking the QML event loop."""

    def __init__(self, mission_id: str, bridge: PmCockpitBridge) -> None:
        super().__init__()
        self._mission_id = mission_id
        self._bridge = bridge
        self.setAutoDelete(False)
        self.result: tuple[bool, str] | None = None
        self.done = False

    def run(self) -> None:
        try:
            receipt = self._bridge._service.start_execution(self._mission_id)
            if receipt.status == "VERIFYING":
                self.result = (True, "任务已启动，正在验证。")
            elif receipt.status == "FAILED":
                self.result = (False, "任务启动失败，执行记录已保留。")
            else:
                self.result = (False, "无法确认任务已启动，已保留待核验状态。")
        except Exception as error:  # noqa: BLE001 - worker must always release UI busy state
            log.exception("Mission start failed: %s", self._mission_id)
            self.result = (False, str(error) or "任务启动失败。")
        finally:
            self.done = True


class PmCockpitBridge(QObject):
    """Expose the planning draft and explicit user confirmations to QML."""

    startFinished = Signal(str, bool, str)

    def __init__(
        self,
        workspace_root: str,
        *,
        service: PmCockpitService | None = None,
        facade: PmFacadeService | None = None,
        thread_pool: QThreadPool | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service or PmCockpitService(workspace_root)
        self._facade = facade or PmFacadeService(workspace_root)
        self._planning_input: tuple[str, str, tuple[str, ...]] | None = None
        self._planning_request_id: str | None = None
        self._thread_pool = thread_pool or QThreadPool.globalInstance()
        self._start_workers: dict[str, _StartWorker] = {}
        self._start_poll_timer = QTimer(self)
        self._start_poll_timer.setInterval(50)
        self._start_poll_timer.timeout.connect(self._poll_start_workers)

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
        """Retain the legacy synchronous confirmation API for non-QML callers."""
        return self._confirmation_result("start", mission_id)

    @Slot(str, result="QVariant")
    def startExecution(self, mission_id: str) -> dict[str, Any]:
        """Queue one genuine foreground start and reject same-Mission replays."""
        mission_id = mission_id.strip()
        if not mission_id:
            return {
                "accepted": False,
                "busy": False,
                "message": "未找到可启动的需求。",
            }
        if mission_id in self._start_workers:
            return {
                "accepted": False,
                "busy": True,
                "message": "该任务正在启动，请勿重复操作。",
            }

        worker = _StartWorker(mission_id, self)
        self._start_workers[mission_id] = worker
        try:
            self._thread_pool.start(worker)
        except RuntimeError as error:
            del self._start_workers[mission_id]
            return {
                "accepted": False,
                "busy": False,
                "message": f"任务未能进入后台执行：{error}",
            }
        if not self._start_poll_timer.isActive():
            self._start_poll_timer.start()
        return {
            "accepted": True,
            "busy": True,
            "message": "已提交启动请求，正在后台执行。",
        }

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

    def _poll_start_workers(self) -> None:
        completed = tuple(
            mission_id
            for mission_id, worker in self._start_workers.items()
            if worker.done
        )
        for mission_id in completed:
            worker = self._start_workers.pop(mission_id)
            success, message = worker.result or (False, "任务启动结果不可用。")
            self.startFinished.emit(mission_id, success, message)
        if not self._start_workers:
            self._start_poll_timer.stop()
