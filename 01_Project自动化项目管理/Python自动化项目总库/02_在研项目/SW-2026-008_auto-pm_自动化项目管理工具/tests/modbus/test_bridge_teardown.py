"""The teardown guard in tests/modbus/conftest.py is really installed for every test in this directory."""

from __future__ import annotations

from PySide6.QtCore import QThreadPool

from auto_pm.domain.modbus.modbus_bridge import ModbusBridge


def test_every_bridge_made_in_a_test_is_tracked_for_closing() -> None:
    assert ModbusBridge.__init__.__name__ == "tracking_init"
    bridge = ModbusBridge()
    assert bridge._io_jobs == [] and not bridge._io_timer.isActive()


def test_a_finished_test_leaves_no_job_in_the_global_pool() -> None:
    assert QThreadPool.globalInstance().activeThreadCount() == 0
