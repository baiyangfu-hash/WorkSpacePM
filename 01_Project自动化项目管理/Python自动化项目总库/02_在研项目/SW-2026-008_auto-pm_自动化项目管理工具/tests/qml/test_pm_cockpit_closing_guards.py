"""V05-B3: a closing cockpit takes no final acceptance and publishes no late start result (independent audit R2-01 and R2-02)."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from auto_pm.core.pm_cockpit_service import PmCockpitService
from PySide6.QtWidgets import QApplication

from auto_pm.contracts.mission import MissionState
from auto_pm.ui.qml.bridges.pm_cockpit_bridge import PmCockpitBridge
from tests.core.test_pm_cockpit_dual_root import _roots, _work
from tests.qml.conftest import _delete_qobject
from tests.qml.test_pm_cockpit_approval_bridge import _click, _cockpit


@pytest.mark.parametrize("how", ["shutdown", "window-destroyed"])
def test_a_closing_cockpit_refuses_the_final_acceptance_and_changes_nothing(qapp: QApplication, tmp_path: Path, how: str) -> None:
    cockpit = _cockpit(tmp_path)
    bridge, pool, _finished = _click(cockpit)
    mission_id = cockpit.mission_id()
    assert cockpit.store.get_mission(mission_id).state is MissionState.ACCEPTANCE_PENDING  # a real Mission that the user could accept
    writes, last_worker = cockpit.writes(), pool.worker
    if how == "shutdown":
        assert bridge.shutdown(timeout_ms=5_000) is True
    else:
        bridge.stopSnapshotRefresh()  # what the QML window does when it is destroyed
    answer = bridge.confirmAcceptance(mission_id)
    assert answer["success"] is False and answer["closing"] is False
    assert cockpit.store.get_mission(mission_id).state is MissionState.ACCEPTANCE_PENDING
    assert cockpit.writes() == writes
    assert pool.worker is last_worker  # no closure task was queued
    _delete_qobject(bridge)


def _bridge_with_a_start(main: Path, monkeypatch: pytest.MonkeyPatch, release: threading.Event, started: threading.Event) -> PmCockpitBridge:
    service = PmCockpitService(main)

    def start_execution(mission_id: str) -> SimpleNamespace:
        started.set()
        release.wait(30)
        return SimpleNamespace(verified=True, message="started", receipt_status="")

    monkeypatch.setattr(service, "start_execution", start_execution)
    return PmCockpitBridge(str(main), service=service)


def _wait_until_idle(bridge: PmCockpitBridge) -> None:
    deadline = time.monotonic() + 30
    while bridge.pending_tasks() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not bridge.pending_tasks()


def test_a_start_that_finishes_after_the_window_is_gone_publishes_nothing(qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    main, _candidate = _roots(tmp_path)
    _work(main, "WORK-CLOSE-001")
    release, started = threading.Event(), threading.Event()
    bridge = _bridge_with_a_start(main, monkeypatch, release, started)
    published: list[tuple[str, bool, str]] = []
    bridge.startFinished.connect(lambda mission_id, ok, message: published.append((mission_id, ok, message)))
    try:
        assert bridge.startExecution("MISSION-X")["accepted"] is True
        assert started.wait(30)
        bridge.stopSnapshotRefresh()  # the window is destroyed while the start is still running
        release.set()
        _wait_until_idle(bridge)
        bridge._poll_start_workers()  # one tick of the 50 ms poll timer, driven by hand
        assert published == []
        assert bridge._start_workers == {}
    finally:
        release.set()
        _delete_qobject(bridge)


def test_shutdown_stops_the_start_poll_timer_even_when_a_result_was_not_polled_yet(qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    main, _candidate = _roots(tmp_path)
    _work(main, "WORK-CLOSE-002")
    release, started = threading.Event(), threading.Event()
    release.set()
    bridge = _bridge_with_a_start(main, monkeypatch, release, started)
    try:
        assert bridge.startExecution("MISSION-Y")["accepted"] is True
        _wait_until_idle(bridge)  # the worker is done, its result has not been polled
        assert bridge._start_workers and bridge._start_poll_timer.isActive() is True
        assert bridge.shutdown(timeout_ms=5_000) is True
        assert bridge._start_poll_timer.isActive() is False
    finally:
        _delete_qobject(bridge)
