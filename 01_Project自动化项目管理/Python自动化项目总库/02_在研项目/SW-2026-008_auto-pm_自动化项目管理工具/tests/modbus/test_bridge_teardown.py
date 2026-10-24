"""The teardown guard in tests/modbus/conftest.py is really installed for every test in this directory."""

from __future__ import annotations

import gc
import threading

import pytest
from PySide6.QtCore import QThreadPool
from shiboken6 import isValid

from auto_pm.domain.modbus.modbus_bridge import ModbusBridge
from tests.modbus import bridge_teardown
from tests.modbus.bridge_teardown import close_bridges


def test_every_bridge_made_in_a_test_is_tracked_for_closing() -> None:
    assert ModbusBridge.__init__.__name__ == "tracking_init"
    bridge = ModbusBridge()
    assert bridge._io_jobs == [] and not bridge._io_timer.isActive()


def test_a_finished_test_leaves_no_job_in_the_global_pool() -> None:
    assert QThreadPool.globalInstance().activeThreadCount() == 0


def test_close_bridges_frees_the_c_object_and_drops_the_job_list_without_the_garbage_collector() -> None:
    """Deterministic, collector off: the Qt object is gone and the reference cycle's job list is empty the moment close_bridges returns.

    (The Python wrapper itself can stay alive - Shiboken keeps every started QRunnable, whose closure holds the bridge - which is why
    the proof is the C++ object and the job list, not a dead weak reference.)
    """
    gc.collect()
    gc.disable()
    try:
        bridge = ModbusBridge()
        bridge.connectDevice("127.0.0.1", 502, slave_id=1, sim_mode=True, source_ip="")
        assert bridge._io_jobs, "the connect job must still be pending for this proof to mean anything"
        QThreadPool.globalInstance().waitForDone(10_000)
        close_bridges([bridge])
        assert not isValid(bridge), "the Qt object is still alive: only a later collection would free it"
        assert bridge._io_jobs == [], "the job list (bridge -> on_done -> bridge) was left in place"
    finally:
        gc.enable()


def test_close_bridges_fails_by_name_when_a_background_job_outlives_the_test(monkeypatch: pytest.MonkeyPatch) -> None:
    release = threading.Event()
    bridge = ModbusBridge()

    def blocked_connect(*args: object, **kwargs: object) -> tuple[bool, str]:
        release.wait(30)
        return True, ""

    monkeypatch.setattr(type(bridge._service), "connect", blocked_connect)
    monkeypatch.setattr(bridge_teardown, "POOL_IDLE_TIMEOUT_MS", 200)
    bridge.connectDevice("127.0.0.1", 502, slave_id=1, sim_mode=True, source_ip="")
    try:
        with pytest.raises(AssertionError, match="still running when the test ended"):
            close_bridges([bridge])
    finally:
        release.set()
        QThreadPool.globalInstance().waitForDone(10_000)
        close_bridges([bridge])
