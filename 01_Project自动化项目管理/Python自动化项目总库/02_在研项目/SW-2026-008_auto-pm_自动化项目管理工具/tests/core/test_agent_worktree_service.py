"""Agent stations (WS-001, X05): only what is safe to lose is ever removed.

Every test builds a throwaway GitHub stand-in (a bare ``origin``), a control root cloned from it and a
helper clone that plays "the PR got merged on GitHub".
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from auto_pm.application.core.agent_worktree_service import (
    AgentWorktreeError,
    AgentWorktreeService,
    StationRefusedError,
)
from auto_pm.ui.cli.__main__ import cli

IDENTITY = ("-c", "user.name=Station Test", "-c", "user.email=station@example.invalid")


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *IDENTITY, *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout.strip()


def commit(cwd: Path, name: str, text: str = "x\n") -> str:
    (cwd / name).write_text(text, encoding="utf-8")
    git(cwd, "add", name)
    git(cwd, "commit", "-q", "-m", f"add {name}")
    return git(cwd, "rev-parse", "HEAD")


class Lab:
    def __init__(self, tmp_path: Path) -> None:
        tmp_path = (
            tmp_path.resolve()
        )  # the service reports resolved paths (8.3 names, /private/tmp)
        self.origin = tmp_path / "origin.git"
        self.root = tmp_path / "root"
        self.github = tmp_path / "github"
        seed = tmp_path / "seed"
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(tmp_path, "clone", "-q", str(self.origin), str(seed))
        git(seed, "checkout", "-q", "-b", "main")
        (seed / ".gitignore").write_text(".venv/\n.auto-pm/\n", encoding="utf-8")
        commit(seed, "README.md", "baseline\n")
        git(seed, "add", ".gitignore")
        git(seed, "commit", "-q", "-m", "ignore")
        git(seed, "push", "-q", "origin", "main")
        git(tmp_path, "clone", "-q", str(self.origin), str(self.root))
        git(tmp_path, "clone", "-q", str(self.origin), str(self.github))
        self.runs: dict[str, str] = {}

    def service(self) -> AgentWorktreeService:
        return AgentWorktreeService(self.root, run_state=self.runs.get, measure_size=False)

    def station(self, agent: str) -> Path:
        return self.root / ".auto-pm" / "worktrees" / agent

    def merge_on_github(self, branch: str, *, delete_remote: bool = True) -> None:
        """Merge commit like the repository's PRs, then GitHub's automatic branch deletion."""

        git(self.github, "fetch", "-q", "origin")
        git(self.github, "checkout", "-q", "main")
        git(self.github, "reset", "-q", "--hard", "origin/main")
        git(self.github, "merge", "-q", "--no-ff", "-m", f"Merge {branch}", f"origin/{branch}")
        git(self.github, "push", "-q", "origin", "main")
        if delete_remote:
            git(self.github, "push", "-q", "origin", "--delete", branch)

    def remote_refs(self) -> str:
        return git(self.origin, "for-each-ref", "--format=%(refname) %(objectname)")

    def local_branches(self) -> set[str]:
        return set(
            git(self.root, "for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines()
        )


@pytest.fixture
def lab(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Lab:
    monkeypatch.delenv("AUTO_PM_AGENT", raising=False)
    return Lab(tmp_path)


def finished_station(lab: Lab, agent: str = "claude", card: str = "CARD-1") -> Path:
    """Open, commit, push: the agent's work is on GitHub."""

    lab.service().open(agent, card)
    station = lab.station(agent)
    commit(station, f"{card}.txt")
    git(station, "push", "-q", "-u", "origin", f"{agent}/{card}")
    return station


# ── open ─────────────────────────────────────────────────────────────


def test_open_creates_station_on_fresh_main_without_tracking(lab: Lab) -> None:
    newer = commit(lab.github, "newer.txt")
    git(lab.github, "push", "-q", "origin", "main")

    station = lab.service().open("claude", "CARD-1")

    assert station.path == lab.station("claude")
    assert git(station.path, "branch", "--show-current") == "claude/CARD-1"
    assert git(station.path, "rev-parse", "HEAD") == newer, "工位必须从最新 origin/main 起"
    upstream = subprocess.run(
        ["git", "-C", str(station.path), "rev-parse", "--abbrev-ref", "@{upstream}"],
        capture_output=True,
        check=False,
    )
    assert upstream.returncode != 0, "不能把 origin/main 设成上游，否则“已推送”会被误判"


def test_open_refuses_a_second_station_for_the_same_agent(lab: Lab) -> None:
    lab.service().open("claude", "CARD-1")
    with pytest.raises(StationRefusedError, match="没收工的工位"):
        lab.service().open("claude", "CARD-2")


def test_open_refuses_existing_branch_unknown_agent_and_reserved_names(lab: Lab) -> None:
    git(lab.root, "branch", "trae/CARD-9")
    with pytest.raises(StationRefusedError, match="已存在"):
        lab.service().open("trae", "CARD-9")
    with pytest.raises(AgentWorktreeError, match="名册"):
        lab.service().open("copilot", "CARD-1")
    with pytest.raises(AgentWorktreeError, match="不能用"):
        lab.service().open("codex", "control-root-20261023")
    with pytest.raises(AgentWorktreeError, match="不能用"):
        lab.service().open("claude", "../escape")


def test_commands_refuse_to_run_inside_a_station(lab: Lab) -> None:
    lab.service().open("claude", "CARD-1")
    with pytest.raises(AgentWorktreeError, match="控制根"):
        AgentWorktreeService(lab.station("claude"))


# ── close: the four situations ──────────────────────────────────────


def test_close_merged_station_removes_worktree_venv_and_local_branch_but_no_remote(
    lab: Lab,
) -> None:
    station = finished_station(lab)
    (station / ".venv").mkdir()
    (station / ".venv" / "pyvenv.cfg").write_text("home = x\n", encoding="utf-8")
    lab.merge_on_github("claude/CARD-1")
    remote_before = lab.remote_refs()

    result = lab.service().close("claude")

    assert not station.exists(), "工位和里面的 .venv 应一起删掉"
    assert result.branch_deleted
    assert "claude/CARD-1" not in lab.local_branches()
    assert lab.remote_refs() == remote_before, "远程一律不删"


def test_close_pushed_but_unmerged_keeps_the_local_branch(lab: Lab) -> None:
    station = finished_station(lab)

    result = lab.service().close("claude")

    assert not station.exists()
    assert not result.branch_deleted
    assert "claude/CARD-1" in lab.local_branches()


def test_close_refuses_unpushed_commits(lab: Lab) -> None:
    lab.service().open("claude", "CARD-1")
    station = lab.station("claude")
    commit(station, "only-here.txt")

    with pytest.raises(StationRefusedError, match="还没推到 GitHub"):
        lab.service().close("claude")

    assert (station / "only-here.txt").exists()


def test_close_refuses_uncommitted_changes_tracked_or_new(lab: Lab) -> None:
    station = finished_station(lab)
    lab.merge_on_github("claude/CARD-1")
    (station / "draft.txt").write_text("not yet\n", encoding="utf-8")

    with pytest.raises(StationRefusedError, match="未提交的改动：draft.txt"):
        lab.service().close("claude")

    (station / "draft.txt").unlink()
    (station / "README.md").write_text("edited\n", encoding="utf-8")
    with pytest.raises(StationRefusedError, match="未提交的改动：README.md"):
        lab.service().close("claude")
    assert station.exists()


def test_close_refuses_another_agents_station(lab: Lab, monkeypatch: pytest.MonkeyPatch) -> None:
    station = finished_station(lab)
    lab.merge_on_github("claude/CARD-1")
    monkeypatch.setenv("AUTO_PM_AGENT", "trae")

    with pytest.raises(StationRefusedError, match="不能收 claude 的工位"):
        lab.service().close("claude")
    assert station.exists()


def test_close_refuses_a_station_holding_someone_elses_branch(lab: Lab) -> None:
    station = lab.station("cursor")
    git(lab.root, "worktree", "add", "-q", "-b", "trae/CARD-5", str(station), "origin/main")

    with pytest.raises(StationRefusedError, match="不是 cursor 的前缀"):
        lab.service().close("cursor")
    assert station.exists()


def test_close_without_a_station(lab: Lab) -> None:
    with pytest.raises(StationRefusedError, match="没有登记"):
        lab.service().close("vscode")


# ── sweep ────────────────────────────────────────────────────────────


def build_mixed_floor(lab: Lab) -> dict[str, Path]:
    """One station of every kind the sweep must tell apart."""

    merged = finished_station(lab, "claude", "CARD-1")
    lab.merge_on_github("claude/CARD-1")
    unpushed = lab.station("trae")
    lab.service().open("trae", "CARD-2")
    commit(unpushed, "wip.txt")
    dirty = finished_station(lab, "cursor", "CARD-3")
    lab.merge_on_github("cursor/CARD-3")
    (dirty / "draft.txt").write_text("x\n", encoding="utf-8")
    fresh = lab.station("vscode")
    lab.service().open("vscode", "CARD-4")
    in_review = finished_station(lab, "codex", "CARD-5")
    foreign = lab.root / ".auto-pm" / "worktrees" / "someone"
    git(lab.root, "worktree", "add", "-q", "-b", "someone/x", str(foreign), "origin/main")
    outside = lab.root.parent / "outside"
    git(lab.root, "worktree", "add", "-q", "-b", "claude/outside", str(outside), "origin/main")
    git(lab.root, "fetch", "-q", "--prune", "origin")
    return {
        "merged": merged,
        "unpushed": unpushed,
        "dirty": dirty,
        "fresh": fresh,
        "in_review": in_review,
        "foreign": foreign,
        "outside": outside,
    }


def test_sweep_defaults_to_dry_run(lab: Lab) -> None:
    floor = build_mixed_floor(lab)
    branches = lab.local_branches()

    report = lab.service().sweep()

    assert not report.applied
    assert all(path.exists() for path in floor.values())
    assert lab.local_branches() == branches
    planned = {item.target for item in report.items if item.remove}
    assert planned == {str(floor["merged"])}


def test_sweep_apply_removes_only_the_merged_clean_station(lab: Lab) -> None:
    floor = build_mixed_floor(lab)
    remote_before = lab.remote_refs()

    report = lab.service().sweep(apply=True)

    assert report.done == [str(floor["merged"])]
    assert not floor["merged"].exists()
    for key in ("unpushed", "dirty", "fresh", "in_review", "foreign", "outside"):
        assert floor[key].exists(), f"{key} 不该被删"
    assert (floor["unpushed"] / "wip.txt").exists()
    assert (floor["dirty"] / "draft.txt").exists()
    assert lab.remote_refs() == remote_before
    reasons = {item.target: item.reason for item in report.items}
    assert "还没推到 GitHub" in reasons[str(floor["unpushed"])]
    assert "未提交的改动" in reasons[str(floor["dirty"])]
    assert "刚开的工位" in reasons[str(floor["fresh"])]
    assert "还没并进 main" in reasons[str(floor["in_review"])]
    assert "不归本命令管" in reasons[str(floor["foreign"])]
    assert str(floor["outside"]) not in reasons, "控制根外的工作树根本不在清单里"


def test_sweep_limited_to_one_agent_leaves_other_agents_alone(lab: Lab) -> None:
    claude = finished_station(lab, "claude", "CARD-1")
    lab.merge_on_github("claude/CARD-1")
    codex = finished_station(lab, "codex", "CARD-7")
    lab.merge_on_github("codex/CARD-7")
    git(lab.root, "branch", "claude/old", "origin/main")
    git(lab.root, "push", "-q", "-u", "origin", "claude/old")
    git(lab.github, "push", "-q", "origin", "--delete", "claude/old")

    report = lab.service().sweep(apply=True, agent="codex")

    assert not codex.exists()
    assert claude.exists()
    assert "claude/old" in lab.local_branches(), "只清 codex 时，claude 的孤儿分支也不动"
    assert report.done == [str(codex)]


def test_sweep_keeps_a_station_whose_branch_has_another_agents_prefix(lab: Lab) -> None:
    station = lab.station("cursor")
    git(lab.root, "worktree", "add", "-q", "-b", "trae/CARD-5", str(station), "origin/main")
    commit(station, "CARD-5.txt")
    git(station, "push", "-q", "-u", "origin", "trae/CARD-5")
    lab.merge_on_github("trae/CARD-5")

    report = lab.service().sweep(apply=True)

    assert station.exists()
    assert "不是 cursor 的前缀" in {item.target: item.reason for item in report.items}[str(station)]


def test_sweep_deletes_gone_branches_only_when_merged(lab: Lab) -> None:
    for name in ("claude/merged", "claude/abandoned"):
        git(lab.root, "checkout", "-q", "-b", name, "origin/main")
        commit(lab.root, f"{name.split('/')[1]}.txt")
        git(lab.root, "push", "-q", "-u", "origin", name)
    git(lab.root, "checkout", "-q", "main")
    lab.merge_on_github("claude/merged")
    git(lab.github, "push", "-q", "origin", "--delete", "claude/abandoned")

    report = lab.service().sweep(apply=True)

    branches = lab.local_branches()
    assert "claude/merged" not in branches
    assert "claude/abandoned" in branches, "远程删了但没并进 main 的分支里有唯一的提交，必须保留"
    reasons = {item.target: item.reason for item in report.items}
    assert "没并进 main" in reasons["claude/abandoned"]


def test_sweep_never_touches_the_control_roots_own_branch(lab: Lab) -> None:
    # Not checked out and already in main: without the explicit guard it would look like any merged, gone branch.
    git(lab.root, "branch", "codex/control-root-20261023", "origin/main")
    git(lab.root, "push", "-q", "-u", "origin", "codex/control-root-20261023")
    git(lab.github, "push", "-q", "origin", "--delete", "codex/control-root-20261023")

    report = lab.service().sweep(apply=True)

    assert "codex/control-root-20261023" in lab.local_branches()
    assert any("控制根自己的分支" in item.reason for item in report.items)


# ── run-plan leftovers after closure (doubt ⑥ stays a separate question) ──

RUN_DIR = "run-plan-0123456789abcdef"
RUN_ID = "RUN-PLAN-0123456789ABCDEF"


def run_plan(lab: Lab) -> Path:
    path = lab.root / ".auto-pm" / "worktrees" / RUN_DIR
    git(lab.root, "worktree", "add", "-q", "-b", f"codex/{RUN_DIR}", str(path), "HEAD")
    return path


@pytest.mark.parametrize(
    ("state", "removed", "reason"),
    [
        ("SUCCEEDED", True, "已结束"),
        ("CANCELLED", True, "已结束"),
        ("VERIFYING", False, "没结束"),
        (None, False, "查不到"),
    ],
)
def test_sweep_run_plan_only_when_its_run_is_terminal(
    lab: Lab, state: str | None, removed: bool, reason: str
) -> None:
    path = run_plan(lab)
    if state is not None:
        lab.runs[RUN_ID] = state

    report = lab.service().sweep(apply=True)

    assert path.exists() is not removed
    assert (f"codex/{RUN_DIR}" in lab.local_branches()) is not removed
    assert reason in {item.target: item.reason for item in report.items}[str(path)]


def test_sweep_keeps_a_finished_run_plan_holding_uncommitted_accepted_bytes(lab: Lab) -> None:
    path = run_plan(lab)
    lab.runs[RUN_ID] = "SUCCEEDED"
    (path / "accepted.txt").write_text("验收过的改动\n", encoding="utf-8")

    report = lab.service().sweep(apply=True)

    assert (path / "accepted.txt").exists()
    assert "疑点⑥" in {item.target: item.reason for item in report.items}[str(path)]


def test_sweep_keeps_a_run_plan_whose_ledger_cannot_be_read(lab: Lab) -> None:
    path = run_plan(lab)

    def broken(_run_id: str) -> str | None:
        raise RuntimeError("账本损坏")

    report = AgentWorktreeService(lab.root, run_state=broken, measure_size=False).sweep(apply=True)

    assert path.exists()
    assert "读账本失败" in report.items[0].reason


# ── list and command line ───────────────────────────────────────────


def test_list_reports_each_station(lab: Lab) -> None:
    floor = build_mixed_floor(lab)
    (floor["merged"] / ".venv").mkdir()
    (floor["merged"] / ".venv" / "big.bin").write_bytes(b"0" * 4096)

    stations = {
        s.name: s for s in AgentWorktreeService(lab.root, run_state=lab.runs.get).stations()
    }

    assert set(stations) == {"claude", "trae", "cursor", "vscode", "codex", "someone"}
    assert stations["claude"].merged and not stations["claude"].unpushed
    assert stations["trae"].unpushed == 1 and not stations["trae"].merged
    assert stations["cursor"].dirty_paths == ("draft.txt",)
    assert stations["vscode"].untouched
    assert stations["someone"].kind == "other"
    assert (stations["claude"].size_bytes or 0) >= 4096, "占用要含 .venv"


def test_cli_exit_codes_and_default_preview(lab: Lab) -> None:
    lab.service().open("claude", "CARD-1")
    commit(lab.station("claude"), "only-here.txt")
    runner = CliRunner(env={"AUTO_PM_AGENT": ""})
    base = ["--workspace", str(lab.root)]

    refused = runner.invoke(cli, [*base, "worktree", "close", "claude", "--no-fetch"])
    assert refused.exit_code == 1, refused.output
    assert "还没推到 GitHub" in refused.output

    preview = runner.invoke(cli, [*base, "worktree", "sweep", "--no-fetch"])
    assert preview.exit_code == 0, preview.output
    assert "没删任何东西" in preview.output

    unknown = runner.invoke(cli, [*base, "worktree", "open", "copilot", "CARD-1"])
    assert unknown.exit_code == 2

    listed = runner.invoke(cli, [*base, "worktree", "list", "--json"])
    assert listed.exit_code == 0, listed.output
    assert '"unpushed": 1' in listed.output

    inside = runner.invoke(cli, ["--workspace", str(lab.station("claude")), "worktree", "list"])
    assert inside.exit_code == 2


def test_locked_or_detached_stations_are_left_alone(lab: Lab) -> None:
    locked = finished_station(lab, "claude", "CARD-1")
    lab.merge_on_github("claude/CARD-1")
    git(lab.root, "worktree", "lock", str(locked))
    detached = lab.station("trae")
    git(lab.root, "worktree", "add", "-q", "--detach", str(detached), "origin/main")

    report = lab.service().sweep(apply=True)

    assert locked.exists() and detached.exists()
    reasons = {item.target: item.reason for item in report.items}
    assert "lock" in reasons[str(locked)]
    assert "detached" in reasons[str(detached)]
    with pytest.raises(StationRefusedError, match="detached"):
        lab.service().close("trae")
