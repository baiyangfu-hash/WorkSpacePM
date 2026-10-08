"""Narrow QObject bridge for the safe, user-facing PM cockpit."""

from __future__ import annotations

import logging
import time
from typing import Any, cast
from uuid import uuid4

from pydantic import ValidationError
from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot

from auto_pm.contracts.pm_cockpit import (
    PmCockpitCompletionState,
    PmCockpitEvidence,
    PmCockpitSnapshot,
)
from auto_pm.contracts.pm_facade import PmIntent
from auto_pm.core.pm_cockpit_service import PmCockpitError, PmCockpitService
from auto_pm.core.pm_facade_service import PmFacadeError, PmFacadeService

log = logging.getLogger(__name__)


class _StartWorker(QRunnable):
    """Run one approved Mission without retaining its GUI bridge in the pool."""

    def __init__(self, mission_id: str, bridge: PmCockpitBridge) -> None:
        super().__init__()
        self._mission_id = mission_id
        self._service = bridge._service
        self.setAutoDelete(False)
        self.result: tuple[bool, str] | None = None
        self.done = False

    def run(self) -> None:
        try:
            outcome = self._service.start_execution(self._mission_id)
            if outcome.verified:
                self.result = (True, outcome.message)
            elif outcome.receipt_status == "FAILED":
                self.result = (False, "任务启动失败，执行记录已保留。")
            elif outcome.receipt_status == "PENDING":
                self.result = (False, "无法确认任务已启动，已保留待核验状态。")
            else:
                self.result = (False, outcome.message)
        except PmCockpitError as error:
            self.result = (False, str(error) or "任务启动失败。")
        except Exception:  # noqa: BLE001 - worker must always release UI busy state
            log.exception("Mission start failed: %s", self._mission_id)
            self.result = (False, "任务启动失败，已保留现场。")
        finally:
            self.done = True


class _ApproveStartWorker(QRunnable):
    """Approve one pending scope card and start it, off the QML main thread (one user click)."""

    def __init__(self, request_id: str, plan_hash: str, service: PmCockpitService) -> None:
        super().__init__()
        self._request_id = request_id
        self._plan_hash = plan_hash
        self._service = service
        self.setAutoDelete(False)
        self.result: tuple[bool, str] | None = None
        self.done = False

    def run(self) -> None:
        approved = False
        try:
            try:
                approval = self._service.approve_scope(self._request_id, self._plan_hash)
            except PmCockpitError as error:
                self.result = (False, str(error) or "范围未能批准，已保留现场。")
                return
            approved = True
            try:
                outcome = self._service.start_execution(approval.mission_id)
            except PmCockpitError as error:
                self.result = (
                    False,
                    f"范围已批准，但任务未能启动：{error}；可在项目卡上点击“确认开始”重试。",
                )
                return
            if outcome.verified:
                self.result = (True, outcome.message)
            elif outcome.receipt_status == "FAILED":
                self.result = (False, "范围已批准，但任务启动失败，执行记录已保留。")
            elif outcome.receipt_status == "PENDING":
                self.result = (False, "范围已批准，但无法确认任务已启动，已保留待核验状态。")
            else:
                self.result = (False, f"范围已批准；{outcome.message}")
        except Exception:  # UI must never receive exception text or paths
            log.exception("Scope approval failed: %s", self._request_id)
            self.result = (
                (False, "范围已批准，但任务启动出现意外错误，已保留现场；可在项目卡上点击“确认开始”重试。")
                if approved
                else (False, "范围未能批准，已保留现场。")
            )
        finally:
            self.done = True


class _CloseWorker(QRunnable):
    """Close one accepted Mission through the closure service, off the QML main thread."""

    def __init__(self, mission_id: str, service: PmCockpitService) -> None:
        super().__init__()
        self._mission_id = mission_id
        self._service = service
        self.setAutoDelete(False)
        self.result: tuple[bool, str] | None = None
        self.done = False

    def run(self) -> None:
        try:
            completion = self._service.close_accepted(self._mission_id)
            self.result = (
                completion.state is PmCockpitCompletionState.COMPLETED,
                completion.message,
            )
        except PmCockpitError as error:
            self.result = (False, str(error) or "无法完成收尾，已保留现场。")
        except Exception:  # noqa: BLE001 - UI must never receive exception text or paths
            log.exception("Mission closure failed: %s", self._mission_id)
            self.result = (False, "无法完成收尾，已保留现场。")
        finally:
            self.done = True


class _SnapshotWorker(QRunnable):
    """Read one immutable cockpit snapshot away from the QML main thread."""

    def __init__(self, service: PmCockpitService) -> None:
        super().__init__()
        self._service = service
        self.setAutoDelete(False)
        self.result: PmCockpitSnapshot | None = None
        self.error = ""
        self.done = False

    def run(self) -> None:
        try:
            self.result = self._service.snapshot()
        except Exception as error:  # noqa: BLE001 - UI must retain its last verified snapshot
            log.exception("Cockpit snapshot refresh failed")
            self.error = str(error) or "无法读取驾驶舱状态。"
        finally:
            self.done = True


class _EvidenceWorker(QRunnable):
    """Read one project's evidence drawer data away from the QML main thread."""

    def __init__(self, service: PmCockpitService, project_id: str) -> None:
        super().__init__()
        self._service = service
        self.project_id = project_id
        self.setAutoDelete(False)
        self.result: PmCockpitEvidence | None = None
        self.error = ""
        self.done = False

    def run(self) -> None:
        try:
            self.result = self._service.evidence(self.project_id)
        except PmCockpitError as error:
            self.error = str(error) or "无法读取证据。"
        except Exception:  # noqa: BLE001 - UI must never receive exception text or paths
            log.exception("Cockpit evidence read failed: %s", self.project_id)
            self.error = "无法读取证据。"
        finally:
            self.done = True


class PmCockpitBridge(QObject):
    """Expose the planning draft and explicit user confirmations to QML."""

    startFinished = Signal(str, bool, str)
    snapshotFinished = Signal(cast(type[object], "QVariant"))
    evidenceFinished = Signal(cast(type[object], "QVariant"))
    closureFinished = Signal(str, bool, str)
    scopeApprovalFinished = Signal(str, bool, str)

    def __init__(
        self,
        workspace_root: str,
        *,
        service: PmCockpitService | None = None,
        facade: PmFacadeService | None = None,
        thread_pool: QThreadPool | None = None,
        snapshot_interval_ms: int = 5_000,
        parent: QObject | None = None,
        control_root: str | None = None,
    ) -> None:
        if type(snapshot_interval_ms) is not int or not 1_000 <= snapshot_interval_ms <= 60_000:
            raise ValueError("snapshot_interval_ms 必须在 1000 到 60000 之间")
        super().__init__(parent)
        self._service = service or PmCockpitService(workspace_root, control_root=control_root)
        self._facade = facade or (
            PmFacadeService(control_root, execution_root=workspace_root)
            if control_root
            else PmFacadeService(workspace_root)
        )
        self._planning_input: tuple[str, str, tuple[str, ...]] | None = None
        self._planning_request_id: str | None = None
        self._thread_pool = thread_pool or QThreadPool.globalInstance()
        self._start_workers: dict[str, _StartWorker] = {}
        self._start_poll_timer = QTimer(self)
        self._start_poll_timer.setInterval(50)
        self._start_poll_timer.timeout.connect(self._poll_start_workers)
        self._snapshot_worker: _SnapshotWorker | None = None
        self._snapshot_delivery_enabled = True
        self._closing = False
        self._close_workers: dict[str, _CloseWorker] = {}
        self._close_poll_timer = QTimer(self)
        self._close_poll_timer.setInterval(50)
        self._close_poll_timer.timeout.connect(self._poll_close_workers)
        self._approve_workers: dict[str, _ApproveStartWorker] = {}
        self._approve_poll_timer = QTimer(self)
        self._approve_poll_timer.setInterval(50)
        self._approve_poll_timer.timeout.connect(self._poll_approve_workers)
        self._evidence_worker: _EvidenceWorker | None = None
        self._evidence_poll_timer = QTimer(self)
        self._evidence_poll_timer.setInterval(50)
        self._evidence_poll_timer.timeout.connect(self._poll_evidence_worker)
        self._snapshot_poll_timer = QTimer(self)
        self._snapshot_poll_timer.setInterval(50)
        self._snapshot_poll_timer.timeout.connect(self._poll_snapshot_worker)
        self._snapshot_refresh_timer = QTimer(self)
        self._snapshot_refresh_timer.setInterval(snapshot_interval_ms)
        self._snapshot_refresh_timer.timeout.connect(self.requestSnapshot)
        self.destroyed.connect(self._disable_snapshot_delivery)

    @Slot(result="QVariant")
    def loadSnapshot(self) -> dict[str, Any]:
        """Load the default screen without initializing any application state."""
        snapshot = self._service.snapshot()
        return {"success": True, "snapshot": snapshot.model_dump(mode="json")}

    @Slot(result="QVariant")
    def requestSnapshot(self) -> dict[str, Any]:
        """Queue at most one read-only snapshot task."""
        if not self._snapshot_delivery_enabled:
            return {"accepted": False, "busy": False, "message": "驾驶舱正在关闭。"}
        if self._snapshot_worker is not None:
            return {"accepted": False, "busy": True, "message": "状态刷新正在进行。"}
        worker = _SnapshotWorker(self._service)
        self._snapshot_worker = worker
        try:
            self._thread_pool.start(worker)
        except RuntimeError as error:
            self._snapshot_worker = None
            return {
                "accepted": False,
                "busy": False,
                "message": f"状态刷新未能进入后台：{error}",
            }
        if not self._snapshot_poll_timer.isActive():
            self._snapshot_poll_timer.start()
        return {"accepted": True, "busy": True, "message": "正在刷新状态。"}

    @Slot(result="QVariant")
    def startSnapshotRefresh(self) -> dict[str, Any]:
        """Start bounded periodic refresh and queue the first snapshot."""
        if self._closing:
            return {"accepted": False, "busy": False, "message": "驾驶舱正在关闭。"}
        self._snapshot_delivery_enabled = True
        if not self._snapshot_refresh_timer.isActive():
            self._snapshot_refresh_timer.start()
        return self.requestSnapshot()

    @Slot()
    def stopSnapshotRefresh(self) -> None:
        """Stop future refreshes and suppress any late worker result."""
        self._snapshot_delivery_enabled = False
        self._snapshot_refresh_timer.stop()
        self._snapshot_poll_timer.stop()

    @Slot(str, result="QVariant")
    def requestEvidence(self, project_id: str) -> dict[str, Any]:
        """Queue at most one read-only evidence task; the result arrives via evidenceFinished."""
        project_id = project_id.strip()
        if not project_id:
            return {"accepted": False, "busy": False, "message": "未找到要查看证据的项目。"}
        if not self._snapshot_delivery_enabled:
            return {"accepted": False, "busy": False, "message": "驾驶舱正在关闭。"}
        if self._evidence_worker is not None:
            return {"accepted": False, "busy": True, "message": "证据正在读取，请稍候。"}
        worker = _EvidenceWorker(self._service, project_id)
        self._evidence_worker = worker
        try:
            self._thread_pool.start(worker)
        except RuntimeError as error:
            self._evidence_worker = None
            return {
                "accepted": False,
                "busy": False,
                "message": f"证据读取未能进入后台：{error}",
            }
        if not self._evidence_poll_timer.isActive():
            self._evidence_poll_timer.start()
        return {"accepted": True, "busy": True, "message": "正在读取证据。"}

    @Slot(str, result="QVariant")
    def loadEvidence(self, project_id: str) -> dict[str, Any]:
        """Synchronous legacy API for non-QML callers; QML must use requestEvidence."""
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
        if self._closing:
            return {"success": False, "message": "驾驶舱正在关闭。"}
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
        if self._closing:
            return {"accepted": False, "busy": False, "message": "驾驶舱正在关闭。"}
        if mission_id in self._start_workers:
            return {
                "accepted": False,
                "busy": True,
                "message": "该任务正在启动，请勿重复操作。",
            }

        if self._approve_workers:
            return {"accepted": False, "busy": True, "message": "正在批准并启动，请勿重复操作。"}
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

    @Slot(str, str, result="QVariant")
    def approveScopeAndStart(self, request_id: str, plan_hash: str) -> dict[str, Any]:
        """Queue the user's single approve-and-start click; replays of the same card are refused."""
        request_id, plan_hash = request_id.strip(), plan_hash.strip()
        if not request_id or not plan_hash:
            return {"accepted": False, "busy": False, "message": "未找到要批准的范围卡。"}
        if not self._snapshot_delivery_enabled:
            return {"accepted": False, "busy": False, "message": "驾驶舱正在关闭。"}
        if self._approve_workers:
            return {"accepted": False, "busy": True, "message": "正在批准并启动，请勿重复操作。"}
        worker = _ApproveStartWorker(request_id, plan_hash, self._service)
        self._approve_workers[request_id] = worker
        try:
            self._thread_pool.start(worker)
        except RuntimeError as error:
            del self._approve_workers[request_id]
            return {"accepted": False, "busy": False, "message": f"批准未能进入后台：{error}"}
        if not self._approve_poll_timer.isActive():
            self._approve_poll_timer.start()
        return {"accepted": True, "busy": True, "message": "已提交批准，正在后台批准并启动。"}

    @Slot(str, result="QVariant")
    def confirmAcceptance(self, mission_id: str) -> dict[str, Any]:
        """Apply one explicit final acceptance, then close it out in the background."""
        if self._closing or not self._snapshot_delivery_enabled:
            return {"success": False, "message": "驾驶舱正在关闭。", "closing": False}
        result = self._confirmation_result("acceptance", mission_id)
        queued = result["success"] and bool(self._queue_closure(mission_id.strip())["accepted"])
        return {**result, "closing": queued}

    @Slot(str, result="QVariant")
    def retryClosure(self, mission_id: str) -> dict[str, Any]:
        """Queue one more closure attempt for an accepted Mission; replays are idempotent."""
        return self._queue_closure(mission_id.strip())

    def _queue_closure(self, mission_id: str) -> dict[str, Any]:
        if not mission_id:
            return {"accepted": False, "busy": False, "message": "未找到可同步的需求。"}
        if not self._snapshot_delivery_enabled:
            return {"accepted": False, "busy": False, "message": "驾驶舱正在关闭。"}
        if mission_id in self._close_workers:
            return {"accepted": False, "busy": True, "message": "该需求正在同步，请勿重复操作。"}
        worker = _CloseWorker(mission_id, self._service)
        self._close_workers[mission_id] = worker
        try:
            self._thread_pool.start(worker)
        except RuntimeError as error:
            del self._close_workers[mission_id]
            return {
                "accepted": False,
                "busy": False,
                "message": f"收尾未能进入后台：{error}",
            }
        if not self._close_poll_timer.isActive():
            self._close_poll_timer.start()
        return {"accepted": True, "busy": True, "message": "已提交收尾请求，正在后台同步。"}

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
            if not self._snapshot_delivery_enabled:
                continue
            success, message = worker.result or (False, "任务启动结果不可用。")
            self.startFinished.emit(mission_id, success, message)
        if not self._start_workers:
            self._start_poll_timer.stop()

    def _poll_close_workers(self) -> None:
        completed = tuple(
            mission_id for mission_id, worker in self._close_workers.items() if worker.done
        )
        for mission_id in completed:
            worker = self._close_workers.pop(mission_id)
            if not self._snapshot_delivery_enabled:
                continue
            completed_ok, message = worker.result or (False, "无法完成收尾，已保留现场。")
            self.closureFinished.emit(mission_id, completed_ok, message)
        if not self._close_workers:
            self._close_poll_timer.stop()

    def _poll_approve_workers(self) -> None:
        completed = tuple(
            request_id for request_id, worker in self._approve_workers.items() if worker.done
        )
        for request_id in completed:
            worker = self._approve_workers.pop(request_id)
            if not self._snapshot_delivery_enabled:
                continue
            success, message = worker.result or (False, "批准结果不可用，已保留现场。")
            self.scopeApprovalFinished.emit(request_id, success, message)
        if not self._approve_workers:
            self._approve_poll_timer.stop()

    def _poll_snapshot_worker(self) -> None:
        worker = self._snapshot_worker
        if worker is None or not worker.done:
            return
        self._snapshot_worker = None
        self._snapshot_poll_timer.stop()
        if not self._snapshot_delivery_enabled:
            return
        if worker.result is None:
            self.snapshotFinished.emit({
                "success": False,
                "snapshot": {},
                "message": worker.error or "无法读取驾驶舱状态。",
            })
            return
        self.snapshotFinished.emit({
            "success": True,
            "snapshot": worker.result.model_dump(mode="json"),
            "message": "",
        })

    def _poll_evidence_worker(self) -> None:
        worker = self._evidence_worker
        if worker is None or not worker.done:
            return
        self._evidence_worker = None
        self._evidence_poll_timer.stop()
        if not self._snapshot_delivery_enabled:
            return
        if worker.result is None:
            self.evidenceFinished.emit({
                "success": False,
                "project_id": worker.project_id,
                "evidence": {},
                "message": worker.error or "无法读取证据。",
            })
            return
        self.evidenceFinished.emit({
            "success": True,
            "project_id": worker.project_id,
            "evidence": worker.result.model_dump(mode="json"),
            "message": "",
        })

    def pending_tasks(self) -> tuple[str, ...]:
        """Names of the background tasks that have been started and have not finished."""
        workers: list[_StartWorker | _CloseWorker | _ApproveStartWorker | _SnapshotWorker | _EvidenceWorker | None] = [
            *self._start_workers.values(),
            *self._close_workers.values(),
            *self._approve_workers.values(),
            self._snapshot_worker,
            self._evidence_worker,
        ]
        return tuple(type(worker).__name__ for worker in workers if worker is not None and not worker.done)

    def shutdown(self, timeout_ms: int = 60_000) -> bool:
        """Refuse new work, then wait (bounded) for the tasks already running; never touches the shared pool."""
        self._closing = True
        self.stopSnapshotRefresh()
        deadline = time.monotonic() + timeout_ms / 1000
        while self.pending_tasks():
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.02)
        self._disable_snapshot_delivery()
        return True

    def _disable_snapshot_delivery(self, *_args: object) -> None:
        self._start_poll_timer.stop()
        self._evidence_poll_timer.stop()
        self._close_poll_timer.stop()
        self._approve_poll_timer.stop()
        self.stopSnapshotRefresh()
