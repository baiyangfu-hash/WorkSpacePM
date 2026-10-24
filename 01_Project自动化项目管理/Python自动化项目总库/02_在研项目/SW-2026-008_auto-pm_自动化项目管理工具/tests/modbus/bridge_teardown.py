"""Close ModbusBridge objects on the GUI thread (see tests/modbus/conftest.py for why a test must not leave this to the collector)."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
from shiboken6 import isValid

from auto_pm.domain.modbus.modbus_bridge import ModbusBridge

POOL_IDLE_TIMEOUT_MS = 10_000


def close_bridges(bridges: Iterable[ModbusBridge]) -> None:
    """Stop timers and scans, wait for the pool, drop the job list (the reference cycle) and delete each bridge now."""
    alive = [bridge for bridge in bridges if isValid(bridge)]
    for bridge in alive:
        bridge._io_timer.stop()
        bridge._scan_timer.stop()
        bridge._stop_poll()
        if bridge._scan_worker is not None:
            bridge._scan_worker.stop_requested = True
    # a job still running after the timeout is a leak of this test: fail it by name instead of crashing a later one
    assert QThreadPool.globalInstance().waitForDone(POOL_IDLE_TIMEOUT_MS), "a Modbus background job was still running when the test ended"
    for bridge in alive:
        bridge._io_jobs.clear()
        bridge.deleteLater()
        QCoreApplication.sendPostedEvents(bridge, QEvent.Type.DeferredDelete.value)
