"""Agent worktree stations (WS-001, WBS X05): open, list, close and sweep.

Each agent works in its own station ``<control root>/.auto-pm/worktrees/<agent>`` on a branch
``<prefix><card>``.  Opening and closing a station used to be manual; this service does it with
checks so that nothing unrecoverable is ever removed:

* a worktree is removed only when it has no uncommitted change (ignored files such as ``.venv``
  do not count and go with the directory) -- except a directory outside the roster, which ``sweep`` never lists
  while it still holds ignored files;
* a commit that exists on no remote-tracking branch is never discarded;
* remote branches are never deleted (GitHub deletes them after the merge);
* only directories under ``.auto-pm/worktrees`` are touched; the control root, ``.codex`` worktrees
  and stations of other agents are left alone.
"""

from __future__ import annotations

import contextlib
import os
import re
import subprocess
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, replace
from pathlib import Path

from auto_pm.infrastructure.control_root_guard import (
    ControlRootGuardError,
    clean_git_environment,
    require_control_root,
    require_safe_workspace_path,
)
from auto_pm.infrastructure.git_timeout import run_git_bounded_text

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
_STATIONS_LOCK_SECONDS = 60.0  # 等别的对话开/收工位的最长时间
# WS-001 / problem pool item 33 rule 4: at most this many directories under ``.auto-pm/worktrees`` at one time.
# Counted by directory, not by roster: the unregistered shells and ``m3-*`` leftovers are exactly what piles up.
MAX_STATIONS = 8
# A release (switching the deployed version) opens one more work tree of its own, so before a release at most
# ``MAX_STATIONS - RELEASE_FREE_PLACES`` directories may be left: ``doctor --pre-release`` fails above that.
RELEASE_FREE_PLACES = 1
# WS-001 / problem pool item 33 rule 5: a station untouched for more than this many days is reported as stale.
STALE_DAYS = 3
# Directories ``sweep`` never lists as removable, whatever Git says (the user's call, 11-02): the open PR #470 station,
# the 1.2 GB trial copy and the Trae station.  Removing one is a manual ``git worktree remove`` by the user.
# Only ``sweep`` honors it.  ``close`` and ``open`` do not: an agent finishing its own card must be able to close its
# station and open the next one (audit 546 -- a keep-list check in ``close`` would have locked Trae out).
RESERVED_STATIONS = frozenset({"m3-pr-chg470", "gui-trial", "trae"})
# Ignored entries that are only regenerable tool caches do not hold a directory back (coordinator ruling 11-02);
# any other ignored file still does.  ``__pycache__`` counts only for its ``*.pyc`` files.
CACHE_DIRS = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"})
_CARD = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")

RunStateLookup = Callable[[str], str | None]


_UNKNOWN_CALLER = "?"


def caller_agent() -> str:
    """Who is running this command: "" for the user's own terminal, a roster name, or "?" when unknown.

    Uses the same markers as the lease handover (``AGENT_MARKERS``): ``AUTO_PM_AGENT`` (``trae:cn`` style, the part
    before the colon), ``CLAUDECODE``/``CLAUDE_CODE_ENTRYPOINT`` for Claude Code and ``CODEX_*`` for Codex.  An agent
    marker that names nobody on the roster, or markers that disagree, give "?" so the caller is refused, never let through.
    """

    found: set[str] = set()
    marker = os.environ.get("AUTO_PM_AGENT", "").strip()
    if marker:
        found.add(marker.split(":", 1)[0].strip().lower())
    if os.environ.get("CLAUDECODE") or os.environ.get("CLAUDE_CODE_ENTRYPOINT"):
        found.add("claude")
    if any(key.upper().startswith("CODEX_") and value for key, value in os.environ.items()):
        found.add("codex")
    if not found:
        return ""
    if len(found) > 1 or not found <= set(AGENT_ROSTER):
        return _UNKNOWN_CALLER
    return found.pop()


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
    ignored_paths: tuple[str, ...] = ()  # ignored untracked files other than tool caches, collapsed to top-level names
    unpushed: int = 0
    merged: bool = False
    untouched: bool = False
    size_bytes: int | None = None
    checked: bool = (
        True  # False: only name, branch and path were read (no status, rev-list or reflog)
    )
    broken: str = ""  # why this directory is no longer a usable work tree (empty: it is one)
    idle_seconds: int | None = None  # since the last commit / branch switch / opening; None: could not be read

    @property
    def agent(self) -> str:
        return self.name if self.kind == "agent" else ""

    @property
    def idle_days(self) -> int | None:
        return None if self.idle_seconds is None else self.idle_seconds // 86400

    @property
    def stale(self) -> bool:
        """Untouched for MORE than ``STALE_DAYS`` days (exactly 3 days is not yet stale)."""

        return self.idle_seconds is not None and self.idle_seconds > STALE_DAYS * 86400


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

    @contextlib.contextmanager
    def _stations_lock(self) -> Iterator[None]:
        """开/收工位的互斥锁（D-44 的并发测试查出：同一 agent 的两个对话同时开工位，输家会把赢家的工位目录清掉）。

        锁文件在 ``.auto-pm/stations.lock``，不放在 ``worktrees`` 下（那里的目录个数要计入上限）。用操作系统的文件锁，
        持有进程崩溃或被杀时由系统自动释放；等不到就报错而不是死等。
        """

        lock_path = self._root / ".auto-pm" / "stations.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + _STATIONS_LOCK_SECONDS
        handle = os.open(lock_path, os.O_RDWR | os.O_CREAT)
        try:
            while True:
                try:
                    if os.name == "nt":
                        import msvcrt

                        os.lseek(handle, 0, os.SEEK_SET)
                        msvcrt.locking(handle, msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as error:
                    if time.monotonic() >= deadline:
                        raise AgentWorktreeError(
                            f"别的对话正在开/收工位，等了 {int(_STATIONS_LOCK_SECONDS)} 秒还没轮到；"
                            "稍后再试，或确认那个对话是不是卡住了"
                        ) from error
                    time.sleep(0.1)
            try:
                yield
            finally:
                if os.name == "nt":
                    import msvcrt

                    os.lseek(handle, 0, os.SEEK_SET)
                    with contextlib.suppress(OSError):
                        msvcrt.locking(handle, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle, fcntl.LOCK_UN)
        finally:
            os.close(handle)

    def open(self, agent: str, card: str, *, fetch: bool = True) -> Station:
        with self._stations_lock():
            return self._open_locked(agent, card, fetch=fetch)

    def _open_locked(self, agent: str, card: str, *, fetch: bool = True) -> Station:
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
        self._require_room_for_a_station()
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
        self._require_inside(path)
        self._stations_dir.mkdir(parents=True, exist_ok=True)
        self._require_inside(path)
        added = self._git("worktree", "add", "--no-track", "-b", branch, str(path), MAIN_REF)
        if added.returncode != 0:
            raise AgentWorktreeError(f"建工位失败：{_detail(added)}")
        return self._inspect(
            path, registered=True, branch=branch, head=self._out("rev-parse", MAIN_REF)
        )

    def count(self) -> int:
        """How many directories sit under ``.auto-pm/worktrees`` (registered or not, a missing one still registered counts)."""

        names = {path.name for path in self._worktrees()}
        if self._stations_dir.is_dir():
            names |= {child.name for child in self._stations_dir.iterdir() if child.is_dir()}
        return len(names)

    def _require_room_for_a_station(self) -> None:
        count = self.count()
        if count >= MAX_STATIONS:
            raise StationRefusedError(
                f".auto-pm/worktrees 下已有 {count} 个目录，上限 {MAX_STATIONS}（WS-001）；"
                "先 `worktree list` 看哪些已经做完，再 `worktree close <agent>` 或 `worktree sweep`（默认只列，加 --apply 才删）"
            )

    # ── list ─────────────────────────────────────────────────────────

    def stations(
        self,
        *,
        deep: bool = True,
        only: str | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> list[Station]:
        """Every station; ``deep=False`` reads only name, branch and path (no per-station Git scan of the work tree).

        ``only`` limits the (deep) inspection to one station name; ``progress`` is called with each name before
        its inspection, so a long scan can show where it is.
        """

        self._require_main_ref()
        registered = self._worktrees()
        stations: list[Station] = []
        for path, info in registered.items():
            if only is not None and path.name != only:
                continue
            if progress is not None:
                progress(path.name)
            inspected = self._inspect(
                path,
                registered=True,
                branch=info.branch,
                head=info.head,
                locked=info.locked,
                deep=deep,
            )
            stations.append(replace(inspected, idle_seconds=_idle_seconds(path)))
        if self._stations_dir.is_dir():
            for child in sorted(self._stations_dir.iterdir()):
                if only is not None and child.name != only:
                    continue
                if child.is_dir() and child.resolve() not in registered:
                    stations.append(
                        Station(
                            name=child.name,
                            path=child,
                            kind=_kind(child.name),
                            registered=False,
                            broken=_broken_reason(child),
                            idle_seconds=_idle_seconds(child),
                        )
                    )
        return sorted(stations, key=lambda s: s.name)

    # ── close ────────────────────────────────────────────────────────

    def close(self, agent: str, *, fetch: bool = True) -> CloseResult:
        with self._stations_lock():
            return self._close_locked(agent, fetch=fetch)

    def _close_locked(self, agent: str, *, fetch: bool = True) -> CloseResult:
        prefix = self._prefix(agent)
        caller = caller_agent()
        if caller == _UNKNOWN_CALLER:
            raise StationRefusedError(
                "认不出是哪个 agent 在执行（环境标记不在名册里或互相矛盾），不收工位；请用户在自己的终端执行"
            )
        if caller and caller != agent:
            raise StationRefusedError(
                f"你是 {caller}，不能收 {agent} 的工位；请 {agent} 自己收，或由用户决定"
            )
        path = self._stations_dir / agent
        registered = self._worktrees()
        if not path.exists() and path.resolve() in registered:
            # Registered but the directory is gone: refuse like any broken station, with the reason that tells what to do.
            raise StationRefusedError(f"工位 {path} 不能收：{_broken_reason(path)}")
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
        self,
        *,
        apply: bool = False,
        agent: str | None = None,
        only: str | None = None,
        fetch: bool = True,
        progress: Callable[[str], None] | None = None,
    ) -> SweepReport:
        """List (and with ``apply`` remove) what is safe to lose; ``only`` limits it to the one directory named."""
        if agent is not None:
            self._prefix(agent)
        caller = caller_agent()
        if apply and caller == _UNKNOWN_CALLER:
            raise StationRefusedError(
                "认不出是哪个 agent 在执行，不清理；先不加 --apply 看清单，删除请用户在自己的终端执行"
            )
        if apply and caller:
            if agent is not None and agent != caller:
                raise StationRefusedError(f"你是 {caller}，只能清自己的工位，不能 --agent {agent}")
            agent = caller
        warning = (
            self._fetch_prune() if fetch else "没有联网核对（--no-fetch），按本机已知的远程分支判断"
        )
        items: list[SweepItem] = []
        plans: list[tuple[SweepItem, Station | None]] = []
        listed_stations = self.stations(only=only, progress=progress)
        if only is not None and not listed_stations:
            raise AgentWorktreeError(f"{self.stations_dir} 下没有叫 {only} 的目录；先 `worktree list` 看名字")
        for listed in listed_stations:
            item = self._sweep_station(listed, agent)
            items.append(item)
            plans.append((item, listed))
        checked_out = self._checked_out_branches()
        for branch in [] if only is not None else self._gone_branches():
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
                    self._remove_station(station, require_merged=station.kind in ("agent", "other"))
                else:
                    self._delete_local_branch(item.target, require_merged=True)
                report.done.append(item.target)
            except AgentWorktreeError as error:
                report.failed.append(f"{item.target}: {error}")
        self._git("worktree", "prune")
        return report

    def _sweep_station(self, station: Station, agent: str | None) -> SweepItem:
        item = self._sweep_verdict(station, agent)
        if item.remove and station.name.lower() in RESERVED_STATIONS:
            # Whatever else keeps it is more informative to show; the keep list only has the last word on "remove".
            return SweepItem(
                item.target,
                item.category,
                False,
                "在保留名单里（m3-pr-chg470、gui-trial、trae），sweep 永远不删；要删请用户亲手处理",
            )
        return item

    def _sweep_verdict(self, station: Station, agent: str | None) -> SweepItem:
        target = str(station.path)
        if station.broken:
            return SweepItem(target, station.kind, False, station.broken)
        if not station.registered:
            return SweepItem(
                target, "other", False, "Git 里没有登记的目录，不是工位；不动，请人工查看"
            )
        if not station.checked:
            return SweepItem(target, station.kind, False, "没做过深检，不能据此判断删除；保留")
        if station.kind == "other":
            return self._sweep_other(station, agent)
        if station.kind == "run-plan" and caller_agent():
            return SweepItem(
                target, "run-plan", False, "run-plan 不属于任何 agent，只由用户在自己的终端清"
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
        return SweepItem(
            target, "station", True, f"{station.branch} 已并进 main，工位干净{_goes_with(station)}"
        )

    def _sweep_other(self, station: Station, agent: str | None) -> SweepItem:
        """A registered directory that is neither a roster station nor a run-plan (``m3-*`` leftovers and the like).

        These belong to no agent, so only the user's own terminal may clean them, and only when everything is safe to
        lose: no uncommitted change, nothing unpushed, not locked, on a branch (not detached), that branch already in
        ``origin/main``.  A directory with no commit of its own is kept unless it has also been idle for more than
        ``STALE_DAYS`` days -- it may have just been created by hand.  Always listed, removed only with ``--apply``.
        """

        target = str(station.path)
        if caller_agent():
            return SweepItem(
                target, "other", False, "不在 agent 名册里的目录不属于任何 agent，只由用户在自己的终端清"
            )
        if agent is not None:
            return SweepItem(target, "other", False, f"本次只清 {agent} 的工位")
        refusal = self._refusal(station)
        if refusal:
            return SweepItem(target, "other", False, refusal)
        hold = self._other_hold(station)
        if hold:
            return SweepItem(target, "other", False, hold)
        if not station.merged:
            return SweepItem(target, "other", False, "分支还没并进 main，在做的活，保留")
        return SweepItem(target, "other", True, f"{station.branch} 已并进 main，目录干净")

    @staticmethod
    def _other_hold(station: Station) -> str:
        """Why a directory outside the roster must be kept even though Git sees it clean ("" when nothing holds it).

        Files ``.gitignore`` hides are in no commit and no ``git status``: deleting the work tree would lose them for
        good, the same principle as "never delete what is untracked".  A directory with no commit of its own is kept
        unless it has also been idle for more than ``STALE_DAYS`` days -- it may have just been created by hand.
        """

        if station.ignored_paths:
            shown = "、".join(station.ignored_paths[:3])
            more = "等" if len(station.ignored_paths) > 3 else ""
            return f"有被 .gitignore 忽略的文件 {len(station.ignored_paths)} 项（{shown}{more}；纯缓存不算），删了就丢；人工看过再处理"
        if station.untouched and not station.stale:
            return "还没有自己的提交，也不到 3 天，可能是刚手工建的；保留"
        return ""

    def _sweep_gone(self, branch: str) -> SweepItem:
        if branch == "main" or branch.startswith("codex/control-root"):
            return SweepItem(branch, "gone-branch", False, "控制根自己的分支，不动")
        if not branch.startswith(tuple(AGENT_ROSTER.values())):
            return SweepItem(branch, "gone-branch", False, "不是名册前缀的分支，不归本命令管")
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
        if station.broken:
            return station.broken
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

    def _remove_station(self, station: Station, *, require_merged: bool = False) -> CloseResult:
        # Re-read everything just before removing: the agent may have kept working since the station was listed.
        self._require_inside(station.path)
        info = self._worktrees().get(station.path.resolve())
        if info is None:
            raise StationRefusedError(f"工位 {station.path} 已不在 Git 登记里，不动")
        if info.branch != station.branch:
            raise StationRefusedError(
                f"工位 {station.path} 已从 {station.branch} 换到 {info.branch or '(detached)'}，有人在用，不删"
            )
        fresh = replace(
            self._inspect(
                station.path, registered=True, branch=info.branch, head=info.head, locked=info.locked
            ),
            idle_seconds=_idle_seconds(station.path),
        )
        self._require_removable(fresh)
        if fresh.kind == "other":
            hold = self._other_hold(fresh)
            if hold:
                raise StationRefusedError(f"不删 {station.path}：{hold}")
        if require_merged and not fresh.merged:
            raise StationRefusedError(f"工位 {station.path} 上又有了没并进 main 的提交，不删")
        removed = self._git("worktree", "remove", str(station.path))
        if removed.returncode != 0:
            # Windows can fail halfway ("拒绝访问") and leave a directory that is no longer a work tree.
            leftover = _broken_reason(station.path)
            warning = f"。注意：{leftover}；用 `worktree list` 看现状，人工处理" if leftover else ""
            raise AgentWorktreeError(f"删工作树失败：{_detail(removed)}{warning}")
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
        self,
        path: Path,
        *,
        registered: bool,
        branch: str,
        head: str,
        locked: bool = False,
        deep: bool = True,
    ) -> Station:
        kind = _kind(path.name)
        broken = _broken_reason(path)
        if broken:
            # Never run Git inside it: with no ``.git`` of its own, Git walks up and answers for the control root
            # (a ``git add -A`` there once staged 7960 files of the control root -- TD-SW008-206).
            return Station(
                name=path.name,
                path=path,
                kind=kind,
                registered=registered,
                branch=branch,
                head=head,
                locked=locked,
                checked=False,
                broken=broken,
            )
        if not deep:
            return Station(
                name=path.name,
                path=path,
                kind=kind,
                registered=registered,
                branch=branch,
                head=head,
                locked=locked,
                checked=False,
            )
        dirty: tuple[str, ...] = ()
        ignored: tuple[str, ...] = ()
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
            hidden = self._git(
                "ls-files", "--others", "--ignored", "--exclude-standard", "-z", cwd=path
            )
            if hidden.returncode != 0:
                raise AgentWorktreeError(f"读不到工位里被忽略的文件 {path}：{_detail(hidden)}")
            ignored = tuple(
                sorted(
                    {
                        entry.split("/", 1)[0] + ("/" if "/" in entry else "")
                        for entry in hidden.stdout.split("\0")
                        if entry and not _is_tool_cache(entry)
                    }
                )
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
            ignored_paths=ignored,
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

    def _require_inside(self, path: Path) -> None:
        """A station must really live under the control root: no symlink or junction on the way."""

        try:
            require_safe_workspace_path(self._root, path, label="工位目录")
        except ControlRootGuardError as error:
            raise AgentWorktreeError(
                f"{error}；工位必须真在控制根的 .auto-pm/worktrees 下"
            ) from error

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
        return run_git_bounded_text(
            ["git", "-C", str(cwd or self._root), *args],
            default_timeout=300.0,
            error_cls=AgentWorktreeError,
            where=cwd or self._root,
            input=stdin,
            capture_output=True,
            check=False,
            env=clean_git_environment(),
        )


def _broken_reason(path: Path) -> str:
    """Why ``path`` can no longer be treated as a work tree ("" when it still is one).

    A linked work tree always has a ``.git`` file of its own. Without it Git, run inside the directory, walks up and answers
    for the control root instead -- so such a directory must never be asked anything, and nobody should work in it.
    """

    if not path.is_dir():
        return "目录不见了，Git 里还留着登记；close 不动它，sweep --apply 会顺带用 `git worktree prune` 清掉这种目录已不存在的登记（不丢东西），也可以自己敲 `git worktree prune`"
    if not (path / ".git").exists():
        return (
            "目录里没有 .git，已经不是工作树（多半是删到一半）；不要在里面跑 git，"
            "命令会落到上层的控制根；人工查看后再处理"
        )
    return ""


def _idle_seconds(path: Path) -> int | None:
    """Seconds since the station was last touched: the newest of its directory, its ``.git`` link and the Git files that
    a commit, a checkout or ``worktree add`` rewrite (``HEAD`` and its reflog).  File stats only -- no Git call, no work
    tree scan.  ``git status`` rewrites the index, so the index is deliberately not read: looking at a station must not
    make it look busy.  Edits that were never committed do not count (``list --deep`` shows those as unstaged changes).
    """

    candidates = [path, path / ".git"]
    link = path / ".git"
    try:
        if link.is_file():
            text = link.read_text(encoding="utf-8")
            first = text.splitlines()[0] if text else ""
            if first.startswith("gitdir:"):
                gitdir = Path(first.removeprefix("gitdir:").strip())
                if not gitdir.is_absolute():
                    gitdir = path / gitdir
                candidates += [gitdir / "HEAD", gitdir / "logs" / "HEAD"]
    except (OSError, UnicodeDecodeError):  # an unreadable link only means the git-dir times are not used
        pass
    stamps: list[float] = []
    for item in candidates:
        try:
            stamps.append(item.stat().st_mtime)
        except OSError:
            continue
    if not stamps:
        return None
    return max(0, int(time.time() - max(stamps)))


def _goes_with(station: Station) -> str:
    """For the listing: a roster station is removed together with its ignored files (``.venv`` and the like)."""

    if not station.ignored_paths:
        return ""
    shown = "、".join(station.ignored_paths[:3])
    more = "等" if len(station.ignored_paths) > 3 else ""
    return f"；被 .gitignore 忽略的文件 {len(station.ignored_paths)} 项（{shown}{more}）会随目录一起删"


def _is_tool_cache(entry: str) -> bool:
    """Whether an ignored file (path relative to the work tree, ``/``-separated) is only a regenerable tool cache."""

    *folders, name = entry.split("/")
    return any(
        folder in CACHE_DIRS and (folder != "__pycache__" or name.endswith(".pyc"))
        for folder in folders
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
