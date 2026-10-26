"""V05-B2: the cockpit closes in order - no new work, running workers finish, then the engine and the bridge are deleted."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, cast

import pytest
from auto_pm.core.pm_cockpit_service import PmCockpitService
from PySide6.QtCore import QThreadPool, QTimer, qInstallMessageHandler
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

import auto_pm.ui.boss_qml_window as boss_window
from auto_pm.contracts.pm_cockpit import PmCockpitSnapshot
from auto_pm.ui.boss_qml_window import build_cockpit_bridge, shutdown_cockpit
from auto_pm.ui.qml.bridges.pm_cockpit_bridge import PmCockpitBridge
from tests.core.test_pm_cockpit_dual_root import _roots, _work
from tests.qml.conftest import _delete_qobject

_BOSS_MAIN = Path(boss_window.__file__).parent / "qml" / "boss_main.qml"


def _blocking_service(root: Path, monkeypatch: pytest.MonkeyPatch, started: threading.Event, release: threading.Event) -> PmCockpitService:
    """A real service whose snapshot waits for the test, so a real pool worker stays running."""

    service = PmCockpitService(root)
    real_snapshot = service.snapshot

    def blocking_snapshot() -> PmCockpitSnapshot:
        if threading.current_thread() is not threading.main_thread():  # only the pool worker waits
            started.set()
            release.wait(30)
        return cast(PmCockpitSnapshot, real_snapshot())

    monkeypatch.setattr(service, "snapshot", blocking_snapshot)
    return service


def test_shutdown_refuses_new_work_waits_for_the_running_worker_and_leaves_the_pool_alone(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main, _candidate = _roots(tmp_path)
    _work(main, "WORK-SHUT-001")
    started, release = threading.Event(), threading.Event()
    bridge = PmCockpitBridge(str(main), service=_blocking_service(main, monkeypatch, started, release))
    delivered: list[object] = []
    bridge.snapshotFinished.connect(delivered.append)
    pool_threads = QThreadPool.globalInstance().maxThreadCount()
    try:
        assert bridge.requestSnapshot()["accepted"] is True
        assert started.wait(30)
        assert bridge.pending_tasks() == ("_SnapshotWorker",)
        assert bridge.shutdown(timeout_ms=100) is False  # still running: nothing is cancelled or killed
        assert bridge.pending_tasks() == ("_SnapshotWorker",)
        refused = {
            "snapshot": bridge.requestSnapshot()["accepted"],
            "refresh": bridge.startSnapshotRefresh()["accepted"],
            "evidence": bridge.requestEvidence("SW-2026-008")["accepted"],
            "start": bridge.startExecution("MISSION-1")["accepted"],
            "draft": bridge.createPlanningDraft("SW-2026-008", "goal", "criteria", "iteration")["success"],
        }
        assert refused == {"snapshot": False, "refresh": False, "evidence": False, "start": False, "draft": False}
        assert bridge._snapshot_delivery_enabled is False and bridge._snapshot_refresh_timer.isActive() is False
        assert bridge.startExecution("MISSION-1")["message"] == "驾驶舱正在关闭。"
        release.set()
        assert bridge.shutdown(timeout_ms=10_000) is True
        assert bridge.pending_tasks() == ()
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:  # a late result must not be delivered to a closing window
            qapp.processEvents()
            time.sleep(0.01)
        assert delivered == []
        assert QThreadPool.globalInstance().maxThreadCount() == pool_threads
        assert QThreadPool.globalInstance().waitForDone(10_000) is True
    finally:
        release.set()
        QThreadPool.globalInstance().waitForDone(10_000)
        _delete_qobject(bridge)


def test_the_window_closes_in_order_without_qml_errors(qapp: QApplication, tmp_path: Path) -> None:
    main, _candidate = _roots(tmp_path)
    _work(main, "WORK-SHUT-002")
    messages: list[str] = []
    qInstallMessageHandler(lambda _kind, _context, message: messages.append(message))
    engine = QQmlApplicationEngine()
    bridge = build_cockpit_bridge(str(main))
    order: list[str] = []
    engine.destroyed.connect(lambda *_: order.append("engine"))
    bridge.destroyed.connect(lambda *_: order.append("bridge"))
    try:
        engine.rootContext().setContextProperty("pmCockpitBridge", bridge)
        engine.load(str(_BOSS_MAIN))
        assert engine.rootObjects(), messages
        assert shutdown_cockpit(engine, bridge, timeout_ms=30_000) is True
        assert order == ["engine", "bridge"]
        assert [m for m in messages if "TypeError" in m or "ReferenceError" in m or "pmCockpitBridge" in m] == []
    finally:
        qInstallMessageHandler(None)
        QThreadPool.globalInstance().waitForDone(10_000)


def test_a_worker_that_will_not_finish_keeps_the_engine_and_the_bridge(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main, _candidate = _roots(tmp_path)
    _work(main, "WORK-SHUT-003")
    started, release = threading.Event(), threading.Event()
    engine = QQmlApplicationEngine()
    bridge = PmCockpitBridge(str(main), service=_blocking_service(main, monkeypatch, started, release))
    order: list[str] = []
    engine.destroyed.connect(lambda *_: order.append("engine"))
    bridge.destroyed.connect(lambda *_: order.append("bridge"))
    try:
        assert bridge.requestSnapshot()["accepted"] is True
        assert started.wait(30)
        assert shutdown_cockpit(engine, bridge, timeout_ms=100) is False
        qapp.processEvents()
        assert order == []
        assert bridge.pending_tasks() == ("_SnapshotWorker",)
    finally:
        release.set()
        QThreadPool.globalInstance().waitForDone(10_000)
    assert shutdown_cockpit(engine, bridge, timeout_ms=10_000) is True
    assert order == ["engine", "bridge"]


def _run_window(monkeypatch: pytest.MonkeyPatch, qapp: QApplication, root: Path) -> tuple[int, list[PmCockpitBridge]]:
    """Run the real window entry point for a moment, then quit its event loop."""

    built: list[PmCockpitBridge] = []
    real_build = boss_window.build_cockpit_bridge

    def recording_build(*args: Any, **kwargs: Any) -> PmCockpitBridge:
        bridge = real_build(*args, **kwargs)
        built.append(bridge)
        return bridge

    monkeypatch.setattr(boss_window, "build_cockpit_bridge", recording_build)
    QTimer.singleShot(500, qapp.quit)
    return boss_window.run_boss_cockpit(str(root)), built


def test_the_window_entry_point_tears_the_cockpit_down_after_the_event_loop(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main, _candidate = _roots(tmp_path)
    _work(main, "WORK-SHUT-004")
    exit_code, built = _run_window(monkeypatch, qapp, main)
    assert exit_code == 0
    assert len(built) == 1
    assert isValid(built[0]) is False  # deleted after the engine, once its workers had finished


def test_the_window_entry_point_reports_a_task_that_is_still_running(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    main, _candidate = _roots(tmp_path)
    _work(main, "WORK-SHUT-005")
    monkeypatch.setattr(boss_window, "shutdown_cockpit", lambda *_args, **_kwargs: False)
    exit_code, built = _run_window(monkeypatch, qapp, main)
    try:
        assert exit_code == 3
        assert "仍有后台任务未完成" in capsys.readouterr().err
        assert isValid(built[0]) is True  # nothing was deleted
    finally:
        assert built[0].shutdown(timeout_ms=10_000) is True
        _delete_qobject(built[0])
