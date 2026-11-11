"""D-235: a pytest plugin that leaves a note of the case each test process is running right now.

``gate run`` kills a group that overruns its time limit.  The log of a killed group ends in the middle of a line of dots, so nobody
could tell which case it was stuck in (the 11-10 round: ``core`` killed after 180 minutes at 93 %, cause unknown).  With this plugin
every test process (each xdist worker, or the only process of a serial group) keeps one small file in the directory named by
``GATE_RUN_PROGRESS_DIR``: the node id of the case it is in and when it started.  The file is emptied when the case ends.  The gate
reads the files before it kills the group and writes them into the group's log.

Without the variable the plugin does nothing, so loading it outside the gate changes nothing.  It imports nothing from the project:
it is loaded with ``-p`` before any conftest, and must not pull the package in ahead of the test fixtures.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

ENV_DIR = "GATE_RUN_PROGRESS_DIR"
SUFFIX = ".running"


def _note_path() -> Path | None:
    folder = os.environ.get(ENV_DIR, "").strip()
    if not folder:
        return None
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    return Path(folder) / f"{worker}-{os.getpid()}{SUFFIX}"


def _write(path: Path, text: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    except OSError:
        pass  # a note that cannot be written must never fail or slow a test; the gate then reports "no note"


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_protocol(item: pytest.Item) -> Iterator[None]:
    path = _note_path()
    if path is not None:
        _write(path, f"{time.time():.0f}\t{item.nodeid}\n")
    yield
    if path is not None:
        _write(path, "")
