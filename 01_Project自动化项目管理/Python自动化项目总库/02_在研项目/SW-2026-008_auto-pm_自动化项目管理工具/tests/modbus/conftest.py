"""tests/modbus: every ModbusBridge a test makes is closed on the GUI thread before the next test starts.

A bridge that is simply dropped at the end of a test is not freed at once: its running jobs keep it in a reference cycle
(bridge -> ``_io_jobs`` -> ``on_done`` bound method -> bridge) until the cyclic garbage collector gets to it - at any later
moment, on any thread that allocates, including a QThreadPool worker.  Until then its 50 ms polling timer keeps ticking in
the *next* tests' event loops (pytest-qt processes events around every test).  That is the shape of the gate crash
0xC0000005 seen twice in the single-process "rest" group (WBS question pool 11), so a test must not leave it to chance.
"""

from __future__ import annotations

import gc
import weakref
from collections.abc import Iterator
from typing import Any

import pytest

from auto_pm.domain.modbus.modbus_bridge import ModbusBridge
from tests.modbus.bridge_teardown import close_bridges


@pytest.fixture(autouse=True)
def _bridges_are_closed_on_the_gui_thread(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    made: list[weakref.ref[ModbusBridge]] = []
    real_init = ModbusBridge.__init__

    def tracking_init(self: ModbusBridge, *args: Any, **kwargs: Any) -> None:
        real_init(self, *args, **kwargs)
        made.append(weakref.ref(self))  # weak: the fixture itself must not keep a bridge alive

    monkeypatch.setattr(ModbusBridge, "__init__", tracking_init)
    yield
    close_bridges(bridge for ref in made if (bridge := ref()) is not None)
    made.clear()
    gc.collect()
