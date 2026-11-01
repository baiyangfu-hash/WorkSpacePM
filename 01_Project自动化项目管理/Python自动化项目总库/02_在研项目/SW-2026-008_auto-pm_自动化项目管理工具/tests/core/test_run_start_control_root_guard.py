"""TD-SW008-267: the service itself refuses to start a Run in the control root, not only the command line.

AGENTS.md WS-001: the control root only runs cockpit commands; a Run's edits belong in an isolated station.  ``continuity run start``
(#410) and the dispatch path (#418) already refused; this pins the last door, ``ContinuityExecutionService.start_run``, so a caller that
skips both still cannot hand the control root to a Run.  ``control_root_guard_on`` switches the rule back on (the rest of the suite
starts Runs in its throw-away repository root, see ``tests/conftest.py``).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from auto_pm.application.core import continuity_execution_service
from auto_pm.application.core.continuity_execution_service import ContinuityExecutionError
from tests.core.test_continuity_execution_service import Clock, _services, _start

pytestmark = pytest.mark.usefixtures("control_root_guard_on")


def _linked_station(root: Path) -> tuple[Path, str]:
    station = root / ".auto-pm" / "worktrees" / "claude"
    subprocess.run(["git", "-C", str(root), "worktree", "add", "--detach", str(station), "HEAD"], check=True, capture_output=True)
    head = subprocess.run(
        ["git", "-C", str(station), "rev-parse", "HEAD"], check=True, capture_output=True, text=True, encoding="utf-8", errors="strict"
    ).stdout.strip()
    return station, head


def test_the_service_refuses_a_run_whose_worktree_is_the_control_root(tmp_path: Path) -> None:
    _, service = _services(tmp_path, Clock())

    with pytest.raises(ContinuityExecutionError, match="控制根"):
        _start(service)

    assert service._store.list_runs("WORK-001") == ()  # nothing was written


def test_a_link_to_the_control_root_is_not_a_station(tmp_path: Path) -> None:
    root = tmp_path / "control"
    root.mkdir()
    _, service = _services(root, Clock())
    link = tmp_path / "alias"
    try:
        link.symlink_to(root, target_is_directory=True)
    except OSError:  # no symlink right on this machine
        pytest.skip("symlinks are not available here")

    with pytest.raises(ContinuityExecutionError):
        _start(service, worktree_path=str(link))

    assert service._store.list_runs("WORK-001") == ()


def test_an_isolated_station_may_carry_the_run(tmp_path: Path) -> None:
    _, service = _services(tmp_path, Clock())
    station, head = _linked_station(tmp_path)

    run = _start(service, git_head=head, worktree_path=str(station))

    assert Path(run.worktree_path) == station.resolve()


def test_the_rule_itself_tells_the_root_from_a_station(tmp_path: Path) -> None:
    station = tmp_path / ".auto-pm" / "worktrees" / "claude"
    station.mkdir(parents=True)

    assert continuity_execution_service._worktree_is_the_control_root(tmp_path, tmp_path) is True
    assert continuity_execution_service._worktree_is_the_control_root(station, tmp_path) is False
