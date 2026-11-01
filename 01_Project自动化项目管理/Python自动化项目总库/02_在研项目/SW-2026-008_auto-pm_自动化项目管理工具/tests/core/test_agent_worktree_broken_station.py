"""A station directory that is no longer a work tree must never be asked anything (TD-SW008-206).

Real incident: removing a station failed halfway ("拒绝访问") and left a directory without its own ``.git``. Git run inside it
walks up and answers for the control root, so a ``git add -A`` there staged 7960 files of the control root.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from auto_pm.application.core.agent_worktree_service import (
    AgentWorktreeError,
    AgentWorktreeService,
    StationRefusedError,
)
from auto_pm.ui.cli.__main__ import cli
from tests.core.test_agent_worktree_service import (
    AGENT_MARKER_KEYS,
    Lab,
    finished_station,
)


@pytest.fixture
def lab(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Lab:
    for key in list(os.environ):
        if key in AGENT_MARKER_KEYS or key.upper().startswith("CODEX_"):
            monkeypatch.delenv(key, raising=False)
    return Lab(tmp_path)


def _half_deleted(lab: Lab, agent: str = "claude", card: str = "CARD-1") -> Path:
    """A clean, pushed, merged station -- then its own ``.git`` file is gone, like a removal that stopped halfway."""

    station = finished_station(lab, agent, card)
    lab.merge_on_github(f"{agent}/{card}")
    (station / ".git").unlink()
    return station


def test_a_station_without_its_own_git_is_reported_broken_and_git_is_not_run_in_it(
    lab: Lab,
) -> None:
    station = _half_deleted(lab)
    (lab.root / "stray-in-the-control-root.txt").write_text("x\n", encoding="utf-8")

    listed = {s.name: s for s in lab.service().stations()}

    broken = listed["claude"]
    assert broken.path == station
    assert "没有 .git" in broken.broken and "不要在里面跑 git" in broken.broken
    assert not broken.checked
    # The control root's own untracked file must not show up as this station's work in progress.
    assert broken.dirty_paths == ()


def test_close_refuses_a_broken_station_and_leaves_it_alone(lab: Lab) -> None:
    station = _half_deleted(lab)

    with pytest.raises(StationRefusedError, match="没有 .git"):
        lab.service().close("claude", fetch=False)

    assert station.is_dir()


def test_sweep_never_removes_a_broken_station(lab: Lab) -> None:
    station = _half_deleted(lab)

    report = lab.service().sweep(apply=True, fetch=False)

    item = next(i for i in report.items if i.target == str(station))
    assert not item.remove and "没有 .git" in item.reason
    assert station.is_dir()
    assert report.failed == []


def test_a_directory_git_does_not_know_and_that_has_no_git_is_flagged_too(lab: Lab) -> None:
    stray = lab.root / ".auto-pm" / "worktrees" / "leftover"
    stray.mkdir(parents=True)
    (stray / "half.txt").write_text("x\n", encoding="utf-8")
    other = lab.root / ".auto-pm" / "worktrees" / "somebody-elses-repo"
    other.mkdir()
    (other / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")

    listed = {s.name: s for s in lab.service().stations(deep=False)}

    assert not listed["leftover"].registered and "没有 .git" in listed["leftover"].broken
    assert listed["somebody-elses-repo"].broken == ""


def test_a_removal_that_fails_halfway_says_the_directory_is_now_unsafe(
    lab: Lab, monkeypatch: pytest.MonkeyPatch
) -> None:
    station = finished_station(lab, "claude", "CARD-1")
    lab.merge_on_github("claude/CARD-1")
    run_git = AgentWorktreeService._git

    def stops_halfway(
        self: AgentWorktreeService, *args: str, **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        if args[:2] == ("worktree", "remove"):
            (station / ".git").unlink()  # what the OS got done before it refused the rest
            return subprocess.CompletedProcess(args, 1, "", "error: Permission denied")
        return run_git(self, *args, **kwargs)

    monkeypatch.setattr(AgentWorktreeService, "_git", stops_halfway)

    with pytest.raises(AgentWorktreeError) as caught:
        lab.service().close("claude", fetch=False)

    message = str(caught.value)
    assert "Permission denied" in message
    assert "注意" in message and "不要在里面跑 git" in message


def test_a_plain_failed_removal_adds_no_warning_when_the_directory_is_intact(
    lab: Lab, monkeypatch: pytest.MonkeyPatch
) -> None:
    finished_station(lab, "claude", "CARD-1")
    lab.merge_on_github("claude/CARD-1")
    run_git = AgentWorktreeService._git

    def refuses(
        self: AgentWorktreeService, *args: str, **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        if args[:2] == ("worktree", "remove"):
            return subprocess.CompletedProcess(args, 1, "", "error: locked by another process")
        return run_git(self, *args, **kwargs)

    monkeypatch.setattr(AgentWorktreeService, "_git", refuses)

    with pytest.raises(AgentWorktreeError) as caught:
        lab.service().close("claude", fetch=False)

    assert "注意" not in str(caught.value)


def test_the_list_command_shows_the_broken_directory_and_a_warning(lab: Lab) -> None:
    _half_deleted(lab)
    runner = CliRunner(env={"AUTO_PM_AGENT": ""})
    base = ["--workspace", str(lab.root)]

    table = runner.invoke(cli, [*base, "worktree", "list"])
    assert table.exit_code == 0, table.output
    flat = "".join(table.output.split())
    assert "残缺目录" in flat and "不要在里面跑git" in flat

    as_json = runner.invoke(cli, [*base, "worktree", "list", "--deep", "--json"])
    assert as_json.exit_code == 0, as_json.output
    assert '"broken": "目录里没有 .git' in as_json.output
