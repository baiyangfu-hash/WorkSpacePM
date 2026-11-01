"""A station directory that is no longer a work tree must never be asked anything (TD-SW008-206).

Real incident: removing a station failed halfway ("拒绝访问") and left a directory without its own ``.git``. Git run inside it
walks up and answers for the control root, so a ``git add -A`` there staged 7960 files of the control root.
"""

from __future__ import annotations

import os
import shutil
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


def _directory_gone(lab: Lab, agent: str = "claude", card: str = "CARD-1") -> Path:
    """A clean, pushed, merged station whose directory was deleted by hand: Git still has it registered."""

    station = finished_station(lab, agent, card)
    lab.merge_on_github(f"{agent}/{card}")
    shutil.rmtree(station)
    return station


def _registered(lab: Lab) -> str:
    return subprocess.run(
        ["git", "-C", str(lab.root), "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout


def test_a_station_whose_directory_is_gone_is_reported_broken_with_the_prune_hint(lab: Lab) -> None:
    station = _directory_gone(lab)
    assert str(station.name) in _registered(lab) or station.as_posix() in _registered(lab)  # the registration is still there

    listed = {s.name: s for s in lab.service().stations()}

    gone = listed["claude"]
    assert gone.path == station and gone.registered
    assert "目录不见了" in gone.broken and "git worktree prune" in gone.broken
    assert not gone.checked  # nothing was asked of Git about a directory that is not there


def test_close_refuses_a_station_whose_directory_is_gone_and_changes_nothing(lab: Lab) -> None:
    _directory_gone(lab)
    before = _registered(lab)

    with pytest.raises(StationRefusedError, match="目录不见了") as caught:
        lab.service().close("claude", fetch=False)

    assert "close 不动它" in str(caught.value)

    assert _registered(lab) == before  # the registration is left for a person to prune


def test_sweep_apply_only_prunes_the_registration_of_a_station_whose_directory_is_gone(lab: Lab) -> None:
    """Decided by the coordinator: close leaves it alone; ``sweep --apply`` ends with ``git worktree prune``, which clears
    the registration of a directory that no longer exists.  Nothing on disk is lost; the station is never "removed"."""

    station = _directory_gone(lab)
    other = lab.root / ".auto-pm" / "worktrees" / "kept"
    other.mkdir(parents=True)
    (other / "keep.txt").write_text("x\n", encoding="utf-8")

    plan = lab.service().sweep(apply=False, fetch=False)
    item = next(i for i in plan.items if i.target == str(station))
    assert not item.remove and "目录不见了" in item.reason
    assert station.name in _registered(lab) or str(station) in _registered(lab)  # a dry run changes nothing

    report = lab.service().sweep(apply=True, fetch=False)

    assert report.failed == [] and str(station) not in report.done  # it was not "removed", only its stale registration went
    assert str(station) not in _registered(lab)
    assert not station.exists()
    assert (other / "keep.txt").is_file()  # nothing else on disk is touched
    assert "目录不见了" in item.reason and "sweep --apply" in item.reason  # the hint says exactly this


def test_pruning_as_the_hint_says_makes_the_gone_station_disappear_from_the_list(lab: Lab) -> None:
    _directory_gone(lab)
    subprocess.run(["git", "-C", str(lab.root), "worktree", "prune"], check=True, capture_output=True)

    assert "claude" not in {s.name for s in lab.service().stations()}


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
    # the sweep also leaves it flagged in `list`: nobody has cleaned it, a person still has to look
    listed = {s.name: s for s in lab.service().stations(deep=False)}
    assert "没有 .git" in listed[station.name].broken


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
