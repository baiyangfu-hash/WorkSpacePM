"""Pytest plugin: list the files each test reads from OUTSIDE the project directory but inside the workspace (D-200).

Why: ``sw008-ci`` only starts for changes under the project directory, so a test that reads a spec, a template or a script elsewhere in the
workspace is silently not run when only that file changes.  Those tests carry ``pytest.mark.external_reads`` and are listed in
``external_reads_manifest.txt``; run this plugin over the whole suite to find out which tests really belong there.

Usage (from the project directory; reads are only recorded, nothing is written except the log)::

    TRACE_OUT=/tmp/external_reads.jsonl PYTHONPATH=tests/tools/sw008_ci \\
        python -m pytest -q -p trace_external_reads -p no:cacheprovider -o addopts= -n 4 tests

Each log line is ``{"test": <node id or collect:<module>>, "event": ..., "path": <workspace-relative path>}``.
Limits: it sees ``open``, ``os.listdir``, ``os.scandir``, ``glob.glob`` and ``shutil`` copies inside this process only; reads done by a
child process, plain ``stat`` calls, and tests that are skipped are invisible.  The first test that imports a shared module gets the blame for
the files that module reads, so look at the whole log, not at one line.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_PROJECT = _HERE.parents[3]


def _workspace_root() -> Path:
    override = os.environ.get("WS_ROOT")
    if override:
        return Path(override).resolve()
    for parent in _HERE.parents:
        if (parent / "AGENTS.md").is_file() and (parent / "main.py").is_file():
            return parent
    return _PROJECT.parents[3]


_WORKSPACE = str(_workspace_root()) + os.sep
_PROJECT_PREFIX = str(_PROJECT) + os.sep
_IGNORED = tuple(str(_workspace_root() / name) for name in (".venv", ".git", ".auto-pm"))
_WRITE_MODE_LETTERS = "wax+"
_EVENTS_WITH_PATH = {"os.listdir", "os.scandir", "glob.glob", "shutil.copyfile", "shutil.copytree"}
_current = {"id": "startup"}
_seen: set[tuple[str, str, str]] = set()


def _outside_project(path: object) -> str | None:
    if not isinstance(path, (str, bytes, os.PathLike)):
        return None
    try:
        resolved = os.path.realpath(os.fsdecode(path))
    except (OSError, ValueError):
        return None
    if not (resolved + os.sep).startswith(_WORKSPACE) or (resolved + os.sep).startswith(_PROJECT_PREFIX):
        return None
    if any(resolved.startswith(prefix) for prefix in _IGNORED):
        return None
    return resolved[len(_WORKSPACE) :]


def _audit(event: str, args: tuple[object, ...]) -> None:
    if event == "open":
        mode = args[1] if len(args) > 1 else None
        if isinstance(mode, str) and any(letter in mode for letter in _WRITE_MODE_LETTERS):
            return
    elif event not in _EVENTS_WITH_PATH:
        return
    if not args:
        return
    relative = _outside_project(args[0])
    if relative is None:
        return
    key = (_current["id"], event, relative)
    if key in _seen:
        return
    _seen.add(key)
    out = os.environ.get("TRACE_OUT")
    if out:
        with open(out, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"test": _current["id"], "event": event, "path": relative}, ensure_ascii=False) + "\n")


sys.addaudithook(_audit)


def pytest_collectstart(collector: object) -> None:
    _current["id"] = "collect:" + str(getattr(collector, "nodeid", "?"))


def pytest_runtest_setup(item: object) -> None:
    _current["id"] = str(getattr(item, "nodeid", "?"))


pytest_runtest_call = pytest_runtest_setup
pytest_runtest_teardown = pytest_runtest_setup
