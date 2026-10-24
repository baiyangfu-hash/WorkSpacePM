"""tests/modbus: every ModbusBridge a test makes is closed on the GUI thread before the next test starts.

A bridge that is simply dropped at the end of a test is not freed at once: its running jobs keep it in a reference cycle
(bridge -> ``_io_jobs`` -> ``on_done`` bound method -> bridge) until the cyclic garbage collector gets to it - at any later
moment, on any thread that allocates, including a QThreadPool worker.  Until then its 50 ms polling timer keeps ticking in
the *next* tests' event loops (pytest-qt processes events around every test).  That is the shape of the gate crash
0xC0000005 seen twice in the single-process "rest" group (WBS question pool 11), so a test must not leave it to chance.
"""

from __future__ import annotations

import gc
from collections.abc import Iterator
from typing import Any

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
from shiboken6 import isValid

from auto_pm.domain.modbus.modbus_bridge import ModbusBridge

POOL_IDLE_TIMEOUT_MS = 10_000


@pytest.fixture(autouse=True)
def _bridges_are_closed_on_the_gui_thread(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    made: list[ModbusBridge] = []
    real_init = ModbusBridge.__init__

    def tracking_init(self: ModbusBridge, *args: Any, **kwargs: Any) -> None:
        real_init(self, *args, **kwargs)
        made.append(self)

    monkeypatch.setattr(ModbusBridge, "__init__", tracking_init)
    yield
    pool = QThreadPool.globalInstance()
    for bridge in made:
        if not isValid(bridge):
            continue
        bridge._io_timer.stop()
        bridge._scan_timer.stop()
        bridge._stop_poll()
        if bridge._scan_worker is not None:
            bridge._scan_worker.stop_requested = True
    # a job still running after the timeout is a leak of this test: fail it by name instead of crashing a later one
    assert pool.waitForDone(POOL_IDLE_TIMEOUT_MS), "a Modbus background job was still running when the test ended"
    for bridge in made:
        if isValid(bridge):
            bridge._io_jobs.clear()
            bridge.deleteLater()
            QCoreApplication.sendPostedEvents(bridge, QEvent.Type.DeferredDelete.value)
    made.clear()
    gc.collect()
