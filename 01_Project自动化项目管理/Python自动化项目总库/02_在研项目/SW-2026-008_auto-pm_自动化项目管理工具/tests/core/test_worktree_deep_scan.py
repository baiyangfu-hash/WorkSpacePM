"""D-61: ``worktree list --deep`` scans each station once and the stations side by side.

Timing is never asserted (flaky on CI); the checks are Git-call counts and result equality.
"""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import Any

import pytest

from auto_pm.application.core import agent_worktree_service as module
from auto_pm.application.core.agent_worktree_service import (
    AgentWorktreeError,
    AgentWorktreeService,
    _is_tool_cache,
)
from tests.core import test_agent_worktree_service as base
from tests.core.test_agent_worktree_service import Lab, other_station

lab = base.lab  # the same fixture, shared with the station-service tests


def _messy(station: Path) -> None:
    """Ignored files in every shape the old ``ls-files`` scan had to cope with."""

    (station / ".gitignore").write_text(
        "build/\n*.log\n!keep.log\nnode_modules/\n.venv/\n__pycache__/\n.pytest_cache/\n",
        encoding="utf-8",
    )
    for relative, text in {
        "build/x/out.o": "o",
        "node_modules/m/index.js": "j",
        ".venv/lib/z": "z",
        "a.log": "l",
        "keep.log": "k",
        "src/deep.log": "l",
        "src/__pycache__/a.pyc": "c",
        "src/__pycache__/notes.txt": "n",  # not a .pyc: stays reported
        "lib/__pycache__/only.pyc": "c",  # only compiled caches under lib/: lib/ is not reported
        ".pytest_cache/v/cache": "p",  # a pure tool cache: not reported
        "plain/untracked.txt": "u",
    }.items():
        target = station / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def _old_ignored(station: Path) -> tuple[str, ...]:
    """What ``ignored_paths`` was computed from before D-61: ``ls-files --others --ignored``."""

    raw = subprocess.run(
        [
            "git",
            "-C",
            str(station),
            "ls-files",
            "--others",
            "--ignored",
            "--exclude-standard",
            "-z",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    return tuple(
        sorted(
            {
                entry.split("/", 1)[0] + ("/" if "/" in entry else "")
                for entry in raw.split("\0")
                if entry and not _is_tool_cache(entry)
            }
        )
    )


def test_the_single_status_scan_reports_the_same_ignored_paths_as_the_old_ls_files_scan(
    lab: Lab,
) -> None:
    path = other_station(lab, "m3-pr-a")
    _messy(path)

    station = {s.name: s for s in lab.service().stations()}["m3-pr-a"]

    assert station.ignored_paths == _old_ignored(path)
    assert "src/" in station.ignored_paths, "src/__pycache__/notes.txt is not a pure cache file"
    assert ".pytest_cache/" not in station.ignored_paths and "lib/" not in station.ignored_paths
    assert "keep.log" not in station.ignored_paths and "keep.log" in station.dirty_paths
    assert all(not item.startswith("!!") for item in station.dirty_paths), (
        "ignored lines are not changes"
    )
    assert "plain/untracked.txt" in station.dirty_paths


def test_each_station_runs_one_status_and_no_ls_files(
    lab: Lab, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = [other_station(lab, f"m3-pr-{name}") for name in "abc"]
    seen: list[tuple[str, str]] = []
    original = AgentWorktreeService._git

    def spy(self: AgentWorktreeService, *args: str, **kwargs: Any) -> Any:
        cwd = kwargs.get("cwd")
        if args and cwd is not None:
            seen.append((Path(cwd).name, args[0]))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(AgentWorktreeService, "_git", spy)

    lab.service().stations()

    for path in paths:
        assert [verb for name, verb in seen if name == path.name and verb == "status"] == ["status"]
    assert not [1 for _, verb in seen if verb == "ls-files"]


def test_parallel_deep_results_equal_the_one_by_one_results_in_the_same_order(lab: Lab) -> None:
    for name in ("m3-pr-a", "m3-pr-b", "m3-pr-c", "m3-pr-d", "m3-pr-e"):
        _messy(other_station(lab, name))
    (lab.root / ".auto-pm" / "worktrees" / "m3-pr-c" / "extra.txt").write_text(
        "e", encoding="utf-8"
    )
    service = lab.service()

    together = service.stations()
    one_by_one = [
        s for name in [item.name for item in together] for s in service.stations(only=name)
    ]

    assert [s.name for s in together] == [s.name for s in one_by_one]
    for left, right in zip(together, one_by_one, strict=True):
        assert (
            left.dirty_paths,
            left.ignored_paths,
            left.unpushed,
            left.merged,
            left.untouched,
        ) == (
            right.dirty_paths,
            right.ignored_paths,
            right.unpushed,
            right.merged,
            right.untouched,
        )


def test_deep_inspection_really_overlaps_stations_and_never_exceeds_the_worker_cap(
    lab: Lab,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("m3-pr-a", "m3-pr-b", "m3-pr-c", "m3-pr-d", "m3-pr-e", "m3-pr-f"):
        other_station(lab, name)
    monkeypatch.setattr(module, "DEEP_SCAN_WORKERS", 3)
    lock = threading.Lock()
    state = {"now": 0, "peak": 0}
    gate = threading.Barrier(3, timeout=20)
    original = AgentWorktreeService._inspect

    def slow(self: AgentWorktreeService, *args: Any, **kwargs: Any) -> Any:
        with lock:
            state["now"] += 1
            state["peak"] = max(state["peak"], state["now"])
        try:
            if state["peak"] < 3:
                gate.wait()  # three stations must be inside at once, or this times out and the test fails
        except threading.BrokenBarrierError:
            pass
        try:
            return original(self, *args, **kwargs)
        finally:
            with lock:
                state["now"] -= 1

    monkeypatch.setattr(AgentWorktreeService, "_inspect", slow)

    lab.service().stations()

    assert state["peak"] == 3


def test_progress_is_reported_once_per_station_even_when_run_side_by_side(lab: Lab) -> None:
    for name in ("m3-pr-a", "m3-pr-b", "m3-pr-c"):
        other_station(lab, name)
    names: list[str] = []

    lab.service().stations(progress=names.append)

    assert sorted(names) == ["m3-pr-a", "m3-pr-b", "m3-pr-c"]


def test_one_failing_station_fails_the_whole_listing_and_names_that_station(
    lab: Lab,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("m3-pr-a", "m3-pr-b", "m3-pr-c"):
        other_station(lab, name)
    bad = lab.root / ".auto-pm" / "worktrees" / "m3-pr-b"
    original = AgentWorktreeService._git

    def failing(self: AgentWorktreeService, *args: str, **kwargs: Any) -> Any:
        result = original(self, *args, **kwargs)
        if args and args[0] == "status" and kwargs.get("cwd") == bad:
            result.returncode = 128
            result.stdout = ""
        return result

    monkeypatch.setattr(AgentWorktreeService, "_git", failing)

    with pytest.raises(AgentWorktreeError, match=r"读不到工位状态 .*m3-pr-b"):
        lab.service().stations()
