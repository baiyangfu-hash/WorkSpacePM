"""V05-B3 and F01-1: a closing cockpit takes no final acceptance, no start confirmation and no other write, and publishes no late start result
(independent audits R2-01, R2-02 and Astra F-01)."""

from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from auto_pm.core.pm_cockpit_service import PmCockpitService
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from auto_pm.contracts.mission import MissionState
from auto_pm.ui.qml.bridges.pm_cockpit_bridge import PmCockpitBridge
from tests.core.test_pm_cockpit_dual_root import _roots, _work
from tests.core.test_pm_facade_service import _setup
from tests.qml.conftest import _delete_qobject
from tests.qml.test_pm_cockpit_approval_bridge import _click, _cockpit
from tests.qml.test_pm_cockpit_bridge import _HoldingThreadPool


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


def _full_state(root: Path) -> dict[str, list[tuple[object, ...]]]:
    """Every row of every table of the real continuity database, with its full content (not only row counts)."""

    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as connection:
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")] for table in tables}


def _awaiting_confirmation(tmp_path: Path) -> tuple[Path, PmCockpitBridge, str]:
    """A real Mission that is authorized and planned but not started: the user is offered "confirm start", and confirming it writes to the store."""

    root = tmp_path / "ws"
    root.mkdir()
    _missions, facade = _setup(root)
    facade.plan("MISSION-PM-001")
    bridge = PmCockpitBridge(str(root), service=PmCockpitService(root, facade=facade), thread_pool=cast(QThreadPool, _HoldingThreadPool()))
    return root, bridge, "MISSION-PM-001"


def test_confirm_start_really_writes_when_the_cockpit_is_open(qapp: QApplication, tmp_path: Path) -> None:
    root, bridge, mission_id = _awaiting_confirmation(tmp_path)
    before = _full_state(root)
    answer = bridge.confirmStart(mission_id)
    assert answer["success"] is True, answer
    assert _full_state(root) != before, "the positive control must change the store, or the refusals below prove nothing"
    _delete_qobject(bridge)


@pytest.mark.parametrize("how", ["shutdown", "begin-shutdown"])
def test_a_closing_cockpit_refuses_confirm_start_and_changes_nothing(qapp: QApplication, tmp_path: Path, how: str) -> None:
    root, bridge, mission_id = _awaiting_confirmation(tmp_path)
    before = _full_state(root)
    if how == "shutdown":
        assert bridge.shutdown(timeout_ms=5_000) is True
    else:
        bridge.beginShutdown()
    answer = bridge.confirmStart(mission_id)
    assert answer["success"] is False and "正在关闭" in str(answer["message"])
    assert _full_state(root) == before, "every row of every table must be exactly as it was"
    _delete_qobject(bridge)


def test_begin_shutdown_seals_every_entry_at_once_without_waiting(qapp: QApplication, tmp_path: Path) -> None:
    root, bridge, mission_id = _awaiting_confirmation(tmp_path)
    before = _full_state(root)
    started = time.monotonic()
    bridge.beginShutdown()
    bridge.beginShutdown()  # idempotent
    assert time.monotonic() - started < 1.0, "sealing never waits for anything"
    entries: dict[str, Callable[[], dict[str, Any]]] = {
        "createPlanningDraft": lambda: bridge.createPlanningDraft("SW-2026-008", "an objective", "a criterion"),
        "confirmStart": lambda: bridge.confirmStart(mission_id),
        "startExecution": lambda: bridge.startExecution(mission_id),
        "approveScopeAndStart": lambda: bridge.approveScopeAndStart("REQ-COCKPIT-0123456789ABCDEF0123456789ABCDEF", "a-plan-hash"),
        "confirmAcceptance": lambda: bridge.confirmAcceptance(mission_id),
        "retryClosure": lambda: bridge.retryClosure(mission_id),
        "requestSnapshot": bridge.requestSnapshot,
        "requestEvidence": lambda: bridge.requestEvidence("SW-2026-008"),
        "startSnapshotRefresh": bridge.startSnapshotRefresh,
    }
    for name, call in entries.items():
        answer = call()
        refused = answer.get("success") is False or answer.get("accepted") is False
        assert refused and "正在关闭" in str(answer.get("message")), (name, answer)
    assert bridge.pending_tasks() == (), "no task was queued by any entry"
    assert _full_state(root) == before
    assert bridge.shutdown(timeout_ms=5_000) is True  # the bounded drain still works after sealing
    _delete_qobject(bridge)


def test_a_paused_cockpit_is_not_sealed_and_can_start_again(qapp: QApplication, tmp_path: Path) -> None:
    _root, bridge, mission_id = _awaiting_confirmation(tmp_path)
    bridge.stopSnapshotRefresh()  # pause only: what an embedding host does when it unloads the view
    assert bridge.confirmStart(mission_id)["success"] is True  # a pause does not refuse the legacy synchronous confirmation
    assert bridge.startSnapshotRefresh()["accepted"] is True  # and it is reversible; sealing is not
    held = cast(_HoldingThreadPool, bridge._thread_pool).worker
    assert held is not None
    held.run()  # let the one refresh task finish so that nothing is pending when the cockpit closes
    bridge._poll_snapshot_worker()
    bridge.beginShutdown()
    assert bridge.startSnapshotRefresh()["accepted"] is False
    assert bridge.shutdown(timeout_ms=5_000) is True
    _delete_qobject(bridge)
