"""Agent worktree stations (WS-001, WBS X05): open, list, close and sweep.

Each agent works in its own station ``<control root>/.auto-pm/worktrees/<agent>`` on a branch
``<prefix><card>``.  Opening and closing a station used to be manual; this service does it with
checks so that nothing unrecoverable is ever removed:

* a worktree is removed only when it has no uncommitted change (ignored files such as ``.venv``
  do not count and go with the directory);
* a commit that exists on no remote-tracking branch is never discarded;
* remote branches are never deleted (GitHub deletes them after the merge);
* only directories under ``.auto-pm/worktrees`` are touched; the control root, ``.codex`` worktrees
  and stations of other agents are left alone.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from auto_pm.infrastructure.control_root_guard import (
    ControlRootGuardError,
    clean_git_environment,
    require_control_root,
)

# WS-001 station and branch prefix table.  An agent not listed here is registered by the user first.
AGENT_ROSTER: dict[str, str] = {
    "claude": "claude/",
    "trae": "trae/",
    "cursor": "cursor/",
    "vscode": "vscode/",
    "codex": "codex/",
}
# Names the cockpit itself uses under the codex/ prefix; a card may not take them over.
RESERVED_CARD_PREFIXES = ("control-root", "run-plan")
RUN_PLAN_NAME = re.compile(r"^run-plan-[0-9a-f]{16}$")
TERMINAL_RUN_STATES = frozenset({"SUCCEEDED", "FAILED", "CANCELLED"})
MAIN_REF = "refs/remotes/origin/main"
_CARD = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")

RunStateLookup = Callable[[str], str | None]


class AgentWorktreeError(RuntimeError):
    """The command cannot run here (wrong root, Git failure, bad arguments)."""


class StationRefusedError(AgentWorktreeError):
    """A safety check refused the action; the message says why and what to do next."""


@dataclass(frozen=True)
class Station:
    """One directory under ``.auto-pm/worktrees`` and what Git says about it."""

    name: str
    path: Path
    kind: str  # "agent" | "run-plan" | "other"
    registered: bool
    branch: str = ""
    head: str = ""
    locked: bool = False
    dirty_paths: tuple[str, ...] = ()
    unpushed: int = 0
    merged: bool = False
    untouched: bool = False
    size_bytes: int | None = None

    @property
    def agent(self) -> str:
        return self.name if self.kind == "agent" else ""


@dataclass(frozen=True)
class _Registered:
    head: str
    branch: str
    locked: bool


@dataclass(frozen=True)
class SweepItem:
    target: str
    category: str  # "station" | "run-plan" | "gone-branch" | "other"
    remove: bool
    reason: str


@dataclass
class SweepReport:
    items: list[SweepItem]
    applied: bool
    done: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    fetch_warning: str = ""


@dataclass(frozen=True)
class CloseResult:
    path: Path
    branch: str
    branch_deleted: bool
    note: str


def _ledger_run_state(root: Path) -> RunStateLookup:
    """Read a Run's state from the control root's ledger through its read-only snapshot."""

    def lookup(run_id: str) -> str | None:
        if not (root / ".auto-pm" / "continuity.db").is_file():
            return None
        from auto_pm.infrastructure.continuity_store import ContinuityStore

        run = ContinuityStore(root).find_run(run_id)
        return None if run is None else str(run.state.value)

    return lookup


class AgentWorktreeService:
    """Open, inspect, close and sweep agent stations of one control root."""

    def __init__(
        self,
        control_root: str | Path,
        *,
        run_state: RunStateLookup | None = None,
        measure_size: bool = True,
    ) -> None:
        try:
            self._root = require_control_root(control_root)
        except ControlRootGuardError as error:
            raise AgentWorktreeError(
                f"工位命令只能在控制根执行（本机唯一那份仓库克隆的根目录）: {error}"
            ) from error
        self._stations_dir = self._root / ".auto-pm" / "worktrees"
        self._run_state = run_state or _ledger_run_state(self._root)
        self._measure_size = measure_size

    @property
    def stations_dir(self) -> Path:
        return self._stations_dir

    # ── open ─────────────────────────────────────────────────────────

    def open(self, agent: str, card: str, *, fetch: bool = True) -> Station:
        prefix = self._prefix(agent)
        if not _CARD.match(card) or card.lower().startswith(RESERVED_CARD_PREFIXES):
            raise AgentWorktreeError(
                f"卡号 `{card}` 不能用：只允许字母、数字、点、横线、下划线，且不能以 control-root/run-plan 开头"
            )
        branch = f"{prefix}{card}"
        path = self._stations_dir / agent
        if path.exists() or self._registered(path):
            raise StationRefusedError(
                f"{agent} 已有没收工的工位 {path}；先 `worktree close {agent}`，或回到那个工位继续做"
            )
        if fetch:
            fetched = self._git("fetch", "origin", "main")
            if fetched.returncode != 0:
                raise AgentWorktreeError(
                    f"`git fetch origin main` 失败：{_detail(fetched)}；断网时可加 --no-fetch，用本机现有的 origin/main"
                )
        self._require_main_ref()
        if self._git("check-ref-format", "--branch", branch).returncode != 0:
            raise AgentWorktreeError(f"分支名不合法: {branch}")
        for ref in (f"refs/heads/{branch}", f"refs/remotes/origin/{branch}"):
            if self._git("show-ref", "--verify", "--quiet", ref).returncode == 0:
                raise StationRefusedError(
                    f"分支 {branch} 已存在（{ref}）；换一个卡号，或先查清这条分支是谁的"
                )
        self._stations_dir.mkdir(parents=True, exist_ok=True)
        added = self._git("worktree", "add", "--no-track", "-b", branch, str(path), MAIN_REF)
        if added.returncode != 0:
            raise AgentWorktreeError(f"建工位失败：{_detail(added)}")
        return self._inspect(
            path, registered=True, branch=branch, head=self._out("rev-parse", MAIN_REF)
        )

    # ── list ─────────────────────────────────────────────────────────

    def stations(self) -> list[Station]:
        self._require_main_ref()
        registered = self._worktrees()
        stations: list[Station] = []
        for path, info in registered.items():
            stations.append(
                self._inspect(
                    path, registered=True, branch=info.branch, head=info.head, locked=info.locked
                )
            )
        if self._stations_dir.is_dir():
            for child in sorted(self._stations_dir.iterdir()):
                if child.is_dir() and child.resolve() not in registered:
                    stations.append(
                        Station(
                            name=child.name, path=child, kind=_kind(child.name), registered=False
                        )
                    )
        return sorted(stations, key=lambda s: s.name)

    # ── close ────────────────────────────────────────────────────────

    def close(self, agent: str, *, fetch: bool = True) -> CloseResult:
        prefix = self._prefix(agent)
        caller = os.environ.get("AUTO_PM_AGENT", "").strip().lower()
        if caller in AGENT_ROSTER and caller != agent:
            raise StationRefusedError(
                f"你是 {caller}，不能收 {agent} 的工位；请 {agent} 自己收，或由用户决定"
            )
        path = self._stations_dir / agent
        registered = self._worktrees()
        info = registered.get(path.resolve()) if path.exists() else None
        if info is None:
            raise StationRefusedError(
                f"{agent} 没有登记在 Git 里的工位（{path}）；用 `worktree list` 看现状"
            )
        if fetch:
            self._fetch_prune()
        station = self._inspect(
            path, registered=True, branch=info.branch, head=info.head, locked=info.locked
        )
        if station.branch and not station.branch.startswith(prefix):
            raise StationRefusedError(
                f"工位 {path} 里的分支 {station.branch} 不是 {agent} 的前缀 {prefix}；不动它，请用户确认这个工位归谁"
            )
        self._require_removable(station)
        return self._remove_station(station)

    # ── sweep ────────────────────────────────────────────────────────

    def sweep(
        self, *, apply: bool = False, agent: str | None = None, fetch: bool = True
    ) -> SweepReport:
        if agent is not None:
            self._prefix(agent)
        warning = (
            self._fetch_prune() if fetch else "没有联网核对（--no-fetch），按本机已知的远程分支判断"
        )
        items: list[SweepItem] = []
        plans: list[tuple[SweepItem, Station | None]] = []
        for listed in self.stations():
            item = self._sweep_station(listed, agent)
            items.append(item)
            plans.append((item, listed))
        checked_out = self._checked_out_branches()
        for branch in self._gone_branches():
            if branch in checked_out:
                continue  # the station that holds it decides; deleting under a worktree is never right
            if agent is not None and not branch.startswith(AGENT_ROSTER[agent]):
                continue
            item = self._sweep_gone(branch)
            items.append(item)
            plans.append((item, None))
        report = SweepReport(items=items, applied=apply, fetch_warning=warning)
        if not apply:
            return report
        for item, station in plans:
            if not item.remove:
                continue
            try:
                if station is not None:
                    self._remove_station(station)
                else:
                    self._delete_local_branch(item.target, require_merged=True)
                report.done.append(item.target)
            except AgentWorktreeError as error:
                report.failed.append(f"{item.target}: {error}")
        self._git("worktree", "prune")
        return report

    def _sweep_station(self, station: Station, agent: str | None) -> SweepItem:
        target = str(station.path)
        if not station.registered:
            return SweepItem(
                target, "other", False, "Git 里没有登记的目录，不是工位；不动，请人工查看"
            )
        if station.kind == "other":
            return SweepItem(
                target, "other", False, "不在 agent 名册里、也不是 run-plan，不归本命令管"
            )
        if station.kind == "agent" and agent is not None and station.name != agent:
            return SweepItem(
                target, "station", False, f"是 {station.name} 的工位，本次只清 {agent} 的"
            )
        refusal = self._refusal(station)
        if refusal:
            return SweepItem(target, station.kind, False, refusal)
        if station.kind == "run-plan":
            run_id = station.name.upper()
            try:
                state = self._run_state(run_id)
            except Exception as error:  # noqa: BLE001 - a ledger read failure keeps the worktree
                return SweepItem(target, "run-plan", False, f"读账本失败（{error}），保留")
            if state is None:
                return SweepItem(target, "run-plan", False, f"账本里查不到 {run_id}，保留")
            if state not in TERMINAL_RUN_STATES:
                return SweepItem(target, "run-plan", False, f"{run_id} 还在 {state}，没结束，保留")
            return SweepItem(target, "run-plan", True, f"{run_id} 已结束（{state}），工作树干净")
        if not station.branch.startswith(AGENT_ROSTER[station.name]):
            return SweepItem(
                target,
                "station",
                False,
                f"分支 {station.branch or '(无)'} 不是 {station.name} 的前缀，不动",
            )
        if station.untouched:
            return SweepItem(target, "station", False, "刚开的工位，还没有提交，保留")
        if not station.merged:
            return SweepItem(target, "station", False, "还没并进 main，在做的活，保留")
        return SweepItem(target, "station", True, f"{station.branch} 已并进 main，工位干净")

    def _sweep_gone(self, branch: str) -> SweepItem:
        if branch == "main" or branch.startswith("codex/control-root"):
            return SweepItem(branch, "gone-branch", False, "控制根自己的分支，不动")
        if not self._is_ancestor(f"refs/heads/{branch}", MAIN_REF):
            return SweepItem(
                branch,
                "gone-branch",
                False,
                "远程已删，但没并进 main，保留（里面可能有没交出去的提交）",
            )
        return SweepItem(branch, "gone-branch", True, "远程已删且已并进 main，删本地分支")

    # ── shared checks and actions ───────────────────────────────────

    def _refusal(self, station: Station) -> str:
        if station.locked:
            return "工位被 git worktree lock 锁着，不动"
        if not station.branch:
            return "工位不在分支上（detached HEAD），不动"
        if station.dirty_paths:
            shown = "、".join(station.dirty_paths[:3])
            more = f" 等 {len(station.dirty_paths)} 个" if len(station.dirty_paths) > 3 else ""
            hint = (
                "（疑点⑥：可能是收口后没并回控制根的改动，交主执行处理）"
                if station.kind == "run-plan"
                else ""
            )
            return f"有未提交的改动：{shown}{more}{hint}；先提交或交给用户决定"
        if station.unpushed:
            return f"有 {station.unpushed} 个提交还没推到 GitHub；先 `git push -u origin {station.branch}`"
        return ""

    def _require_removable(self, station: Station) -> None:
        refusal = self._refusal(station)
        if refusal:
            raise StationRefusedError(f"不收工位 {station.path}：{refusal}")

    def _remove_station(self, station: Station) -> CloseResult:
        # Re-read just before removing: the agent may have kept working since the station was inspected.
        fresh = self._inspect(
            station.path, registered=True, branch=station.branch, head=self._head(station.path)
        )
        self._require_removable(fresh)
        removed = self._git("worktree", "remove", str(station.path))
        if removed.returncode != 0:
            raise AgentWorktreeError(f"删工作树失败：{_detail(removed)}")
        deleted = False
        note = "本地分支保留（已推送、还没并进 main）"
        if station.kind == "run-plan":
            deleted = self._delete_local_branch(station.branch, require_merged=False)
            note = "本地分支已删" if deleted else "本地分支保留（有别处没有的提交）"
        elif fresh.merged:
            deleted = self._delete_local_branch(station.branch, require_merged=True)
            note = "已并进 main，本地分支已删；远程分支由 GitHub 自动删"
        return CloseResult(
            path=station.path, branch=station.branch, branch_deleted=deleted, note=note
        )

    def _delete_local_branch(self, branch: str, *, require_merged: bool) -> bool:
        ref = f"refs/heads/{branch}"
        if self._git("show-ref", "--verify", "--quiet", ref).returncode != 0:
            return False
        if branch in self._checked_out_branches():
            raise StationRefusedError(f"分支 {branch} 正被某个工作树签出，不删")
        if require_merged and not self._is_ancestor(ref, MAIN_REF):
            raise StationRefusedError(f"分支 {branch} 没并进 main，不删")
        if self._unique_commits(branch):
            return False
        deleted = self._git("branch", "-D", branch)
        if deleted.returncode != 0:
            raise AgentWorktreeError(f"删本地分支失败：{_detail(deleted)}")
        return True

    def _unique_commits(self, branch: str) -> int:
        """Count commits reachable from ``branch`` and from no other branch, remote-tracking branch or tag."""

        own = f"refs/heads/{branch}"
        refs = [
            line
            for line in self._out(
                "for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes", "refs/tags"
            ).splitlines()
            if line and line != own and not line.endswith("/HEAD")
        ]
        result = self._git(
            "rev-list",
            "--count",
            "--stdin",
            stdin="\n".join([own, *(f"^{r}" for r in refs)]) + "\n",
        )
        if result.returncode != 0:
            raise AgentWorktreeError(f"无法核对 {branch} 的提交：{_detail(result)}")
        return int(result.stdout.strip() or "0")

    def _inspect(
        self, path: Path, *, registered: bool, branch: str, head: str, locked: bool = False
    ) -> Station:
        kind = _kind(path.name)
        dirty: tuple[str, ...] = ()
        unpushed = 0
        merged = False
        untouched = False
        if head:
            status = self._git("status", "--porcelain=v1", "-z", "--untracked-files=all", cwd=path)
            if status.returncode != 0:
                raise AgentWorktreeError(f"读不到工位状态 {path}：{_detail(status)}")
            dirty = tuple(
                sorted(entry[3:] for entry in status.stdout.split("\0") if len(entry) > 3)
            )
            unpushed = int(self._out("rev-list", "--count", head, "--not", "--remotes") or "0")
            merged = self._is_ancestor(head, MAIN_REF)
            untouched = bool(branch) and self._created_at(branch) == head
        size = _tree_size(path) if self._measure_size and path.is_dir() else None
        return Station(
            name=path.name,
            path=path,
            kind=kind,
            registered=registered,
            branch=branch,
            head=head,
            locked=locked,
            dirty_paths=dirty,
            unpushed=unpushed,
            merged=merged,
            untouched=untouched,
            size_bytes=size,
        )

    def _created_at(self, branch: str) -> str:
        """The commit the branch was created on, from its reflog (empty when the reflog is gone)."""

        log = self._git("reflog", "show", "--format=%H", f"refs/heads/{branch}", "--")
        lines = [line for line in log.stdout.splitlines() if line] if log.returncode == 0 else []
        return lines[-1] if lines else ""

    def _worktrees(self) -> dict[Path, _Registered]:
        """Registered worktrees under ``.auto-pm/worktrees``; the main worktree is never a station."""

        listing = self._out("worktree", "list", "--porcelain")
        found: dict[Path, _Registered] = {}
        for index, block in enumerate(listing.split("\n\n")):
            fields: dict[str, str] = {}
            for line in block.splitlines():
                key, _, value = line.partition(" ")
                fields[key] = value
            if "worktree" not in fields:
                continue
            path = Path(fields["worktree"]).resolve()
            if index == 0 or path.parent != self._stations_dir.resolve():
                continue
            found[path] = _Registered(
                head=fields.get("HEAD", ""),
                branch=fields.get("branch", "").removeprefix("refs/heads/"),
                locked="locked" in fields,
            )
        return found

    def _checked_out_branches(self) -> set[str]:
        """Branches checked out in any worktree of this repository, wherever it lives."""

        listing = self._out("worktree", "list", "--porcelain")
        return {
            line.removeprefix("branch refs/heads/")
            for line in listing.splitlines()
            if line.startswith("branch refs/heads/")
        }

    def _registered(self, path: Path) -> bool:
        return path.resolve() in self._worktrees()

    def _gone_branches(self) -> list[str]:
        listing = self._out(
            "for-each-ref", "--format=%(refname:short)\t%(upstream:track)", "refs/heads"
        )
        return [
            name
            for name, _, track in (line.partition("\t") for line in listing.splitlines())
            if track == "[gone]"
        ]

    def _fetch_prune(self) -> str:
        fetched = self._git("fetch", "--prune", "origin")
        if fetched.returncode != 0:
            return f"联网核对失败（{_detail(fetched)}），按本机已知的远程分支判断"
        return ""

    def _require_main_ref(self) -> None:
        if self._git("show-ref", "--verify", "--quiet", MAIN_REF).returncode != 0:
            raise AgentWorktreeError("本机没有 origin/main；先联网执行 `git fetch origin main`")

    def _is_ancestor(self, commit: str, target: str) -> bool:
        result = self._git("merge-base", "--is-ancestor", commit, target)
        if result.returncode not in (0, 1):
            raise AgentWorktreeError(f"无法判断是否并进 main：{_detail(result)}")
        return result.returncode == 0

    def _head(self, path: Path) -> str:
        return self._out("rev-parse", "HEAD", cwd=path)

    def _prefix(self, agent: str) -> str:
        if agent not in AGENT_ROSTER:
            raise AgentWorktreeError(
                f"agent `{agent}` 不在名册里（{'、'.join(AGENT_ROSTER)}）；表外的 AI 先由用户登记名字和前缀"
            )
        return AGENT_ROSTER[agent]

    def _out(self, *args: str, cwd: Path | None = None) -> str:
        result = self._git(*args, cwd=cwd)
        if result.returncode != 0:
            raise AgentWorktreeError(f"git {args[0]} 失败：{_detail(result)}")
        return result.stdout.strip()

    def _git(
        self, *args: str, cwd: Path | None = None, stdin: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(cwd or self._root), *args],
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=clean_git_environment(),
        )


def _kind(name: str) -> str:
    if name in AGENT_ROSTER:
        return "agent"
    if RUN_PLAN_NAME.match(name):
        return "run-plan"
    return "other"


def _detail(result: subprocess.CompletedProcess[str]) -> str:
    return result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"


def _tree_size(path: Path) -> int:
    total = 0
    for current, _dirs, files in os.walk(path, followlinks=False):
        for name in files:
            try:
                total += os.lstat(os.path.join(current, name)).st_size
            except OSError:
                continue
    return total
