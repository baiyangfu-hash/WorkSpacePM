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
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
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
DEEP_SCAN_WORKERS = 4  # stations inspected at once by ``stations(deep=True)``
CACHE_DIRS = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"})
_CARD = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")

RunStateLookup = Callable[[str], str | None]
# D-169: a station path -> "" when no live Run lease sits on it, else the plain-words description of the lease holding it.
# A probe that cannot tell raises; the service then refuses (fail-closed), it never treats "cannot tell" as "free".
LeaseProbe = Callable[[Path], str]


_UNKNOWN_CALLER = "?"

# 每个对话一个工位名：<名册里的基名>-<会话 ID 前 6 位十六进制>（设计稿：动态 agent 名）。分支前缀沿用基名。
_ALIAS = re.compile(r"^(claude|codex|cursor|trae|vscode)-[0-9a-f]{6}$")


def base_agent(name: str) -> str:
    """名册里的基名：``claude`` 返回 ``claude``，``claude-b89bc8`` 也返回 ``claude``，其余返回空串。"""

    if name in AGENT_ROSTER:
        return name
    match = _ALIAS.match(name)
    return match.group(1) if match else ""


def session_id(environ: Mapping[str, str] | None = None) -> str:
    """本对话的会话 ID，不绑定哪家 agent：AUTO_PM_SESSION_ID（任何 agent 或包装脚本可设）优先，其次 Claude Code 的 CLAUDE_CODE_SESSION_ID。"""

    env = os.environ if environ is None else environ
    for key in ("AUTO_PM_SESSION_ID", "CLAUDE_CODE_SESSION_ID"):
        value = env.get(key, "").strip()
        if value:
            return value
    return ""


def session_alias(environ: Mapping[str, str] | None = None, *, base: str | None = None) -> str:
    """本对话的别名 ``<基名>-<6位十六进制>``；拿不到会话 ID 或基名不在名册里时返回空串（退回只用基名）。

    基名取 ``base``，否则取现有的 ``AUTO_PM_AGENT`` 标记（``codex:cli`` 取冒号前的 ``codex``），再否则是 ``claude``。会话 ID 本身是十六进制（含带横线的 UUID）就取它的
    前 6 位，别的任意字符串则取它的 SHA-256 前 6 位，所以包装脚本随便设个名字也行。
    """

    env = os.environ if environ is None else environ
    session = session_id(env)
    marker = env.get("AUTO_PM_AGENT", "").split(":", 1)[0]
    chosen = (base or marker or "claude").strip().lower()
    if not session or chosen not in AGENT_ROSTER:
        return ""
    compact = session.lower().replace("-", "")
    if len(compact) >= 6 and all(character in "0123456789abcdef" for character in compact):
        digits = compact[:6]
    else:
        digits = hashlib.sha256(session.encode("utf-8")).hexdigest()[:6]
    return f"{chosen}-{digits}"


def caller_alias() -> str:
    """调用者所在对话的别名；调用者必须是名册里的 agent（不是用户终端、也不是认不出的 ``?``），并且拿得到会话 ID。"""

    caller = caller_agent()
    if not caller or caller == _UNKNOWN_CALLER:
        return ""
    return session_alias(base=caller)


def ensure_session_id(control_root: str | Path) -> None:
    """agent 调用却没有任何会话 ID 时，按父进程号生成一个并记住（同一个父进程的后续命令拿到同一个），写进 AUTO_PM_SESSION_ID。

    记在 ``.auto-pm/session-ids/<父进程号>.txt``；父进程号被复用的旧记录由回收时清理。用户自己的终端不生成。
    """

    if not caller_agent() or caller_agent() == _UNKNOWN_CALLER or session_id():
        return
    folder = Path(control_root) / ".auto-pm" / "session-ids"
    parent = os.getppid()
    path = folder / f"{parent}.txt"
    marker = _process_start_marker(parent)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        known = ""
        if path.is_file():
            lines = path.read_text(encoding="utf-8").splitlines()
            known = lines[0].strip() if lines else ""
            stored = lines[1].strip() if len(lines) > 1 else ""
            # D-77: the same pid with a different start time is a new process that reused the number -- a new conversation.
            if known and marker and stored and stored != marker:
                known = ""
        if not known:
            known = hashlib.sha256(f"{parent}:{time.time_ns()}:{os.getpid()}".encode()).hexdigest()[:32]
        path.write_text(f"{known}\n{marker}\n" if marker else known, encoding="utf-8")
        _drop_dead_session_records(folder, keep=path)
    except OSError:
        return
    if known:
        os.environ["AUTO_PM_SESSION_ID"] = known


def _drop_dead_session_records(folder: Path, *, keep: Path) -> None:
    """删掉父进程已不在的 session-ids 记录（D-77）；进程还在或读不出来都留着。"""

    for record in folder.glob("*.txt"):
        if record == keep or not record.stem.isdigit():
            continue
        if not _process_alive(int(record.stem)):
            with contextlib.suppress(OSError):
                record.unlink()


def _process_start_marker(pid: int) -> str:
    """进程的启动时刻标记（同一个进程号被复用时会不同）；读不出来返回空串。"""

    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            kernel32 = getattr(ctypes, "windll").kernel32  # noqa: B009 - windll 只在 Windows 上有
            handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                return ""
            try:
                created, ended, kernel, user = (wintypes.FILETIME() for _ in range(4))
                if not kernel32.GetProcessTimes(handle, *(ctypes.byref(item) for item in (created, ended, kernel, user))):
                    return ""
                return str((created.dwHighDateTime << 32) | created.dwLowDateTime)
            finally:
                kernel32.CloseHandle(handle)
        stat = Path(f"/proc/{pid}/stat")
        if stat.is_file():
            # field 22 (starttime); the command name in field 2 may contain spaces, so count from the last ")".
            return stat.read_text(encoding="utf-8", errors="replace").rsplit(")", 1)[1].split()[19]  # lenient-decode: /proc 文本
        done = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["ps", "-o", "lstart=", "-p", str(pid)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",  # lenient-decode: ps 的时间文本只作指纹比较
            timeout=5,
            check=False,
        )
        return done.stdout.strip()
    except (OSError, IndexError, ValueError, subprocess.SubprocessError):
        return ""


def acts_for(caller: str, station: str) -> bool:
    """``caller_agent()`` 的结果能不能动 ``station``：用户（空）随意；认不出（?）不行；agent 只能动基名工位或自己对话的别名工位。"""

    if not caller:
        return True
    if caller == _UNKNOWN_CALLER:
        return False
    if station == caller:
        return True
    alias = caller_alias()
    return bool(alias) and station == alias


def caller_agent() -> str:
    """Who is running this command: "" for the user's own terminal, a roster name, or "?" when unknown.

    Uses the same markers as the lease handover (``AGENT_MARKERS``): ``AUTO_PM_AGENT`` (``trae:cn`` style, the part
    before the colon), ``CLAUDECODE``/``CLAUDE_CODE_ENTRYPOINT`` for Claude Code and ``CODEX_*`` for Codex.  An agent
    marker that names nobody on the roster, or markers that disagree, give "?" so the caller is refused, never let through.
    ``AI_AGENT`` (D-75) counts as a marker: ``claude-code_…`` is ``claude``, an unrecognised value is "?".
    """

    found: set[str] = set()
    marker = os.environ.get("AUTO_PM_AGENT", "").strip()
    if marker:
        found.add(marker.split(":", 1)[0].strip().lower())
    if os.environ.get("CLAUDECODE") or os.environ.get("CLAUDE_CODE_ENTRYPOINT"):
        found.add("claude")
    if any(key.upper().startswith("CODEX_") and value for key, value in os.environ.items()):
        found.add("codex")
    generic = os.environ.get("AI_AGENT", "").strip().lower()
    if generic:
        # AI_AGENT is the generic convention (Claude Code sets e.g. ``claude-code_2-1-317_agent``).  A value that starts with a
        # roster name is that agent; any other non-empty value is an agent we cannot name, so it is refused ("?"), not let through.
        named = [name for name in sorted(AGENT_ROSTER) if re.match(rf"{re.escape(name)}(?![a-z0-9])", generic)]
        found.add(named[0] if named else _UNKNOWN_CALLER)
    if not found:
        return ""
    if len(found) > 1 or not found <= set(AGENT_ROSTER):
        return _UNKNOWN_CALLER
    return found.pop()


class AgentWorktreeError(RuntimeError):
    """The command cannot run here (wrong root, Git failure, bad arguments)."""


class StationRefusedError(AgentWorktreeError):
    """A safety check refused the action; the message says why and what to do next."""


class StationLeasedError(StationRefusedError):
    """D-169: a Run with an unexpired lease still works in this station; nothing is removed."""


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


@dataclass(frozen=True)
class ReleaseResult:
    path: Path
    branch: str
    rescue_ref: str  # 空串：工位是干净的，没有要救的东西


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


def _ledger_lease_probe(root: Path) -> LeaseProbe:
    """D-169: describe the unexpired Run lease that sits on a station path, read-only through the ledger's public reads.

    No ledger file means no Run was ever registered here: free.  A ledger that exists but cannot be read raises, so the
    caller refuses instead of guessing "free".  Only Runs that are not terminal are looked at; a lease whose expiry has
    passed does not hold the station (the Run is dead by the lease's own rule).
    """

    def probe(station: Path) -> str:
        if not (root / ".auto-pm" / "continuity.db").is_file():
            return ""
        from auto_pm.application.core.workspace_context_service import WorkspaceContextService
        from auto_pm.infrastructure.continuity_store import ContinuityStore

        wanted = _same_path_key(station)
        store = ContinuityStore(root)
        now = datetime.now(UTC)
        for project_id in WorkspaceContextService(str(root)).registered_project_ids():
            for work in store.list_works(project_id):
                for run in store.list_runs(work.work_id):
                    if _same_path_key(Path(run.worktree_path)) != wanted:
                        continue
                    lease = store.get_lease(run.run_id)
                    expires = datetime.fromisoformat(lease.expires_at)
                    if expires.tzinfo is None:
                        expires = expires.replace(tzinfo=UTC)
                    if expires > now:
                        return f"Run {run.run_id}（{run.state.value}）的租约到 {lease.expires_at} 才过期"
        return ""

    return probe


def _same_path_key(path: Path) -> str:
    try:
        return os.path.normcase(str(path.resolve()))
    except OSError:
        return os.path.normcase(str(path))


class AgentWorktreeService:
    """Open, inspect, close and sweep agent stations of one control root."""

    def __init__(
        self,
        control_root: str | Path,
        *,
        run_state: RunStateLookup | None = None,
        lease_probe: LeaseProbe | None = None,
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
        self._lease_probe = lease_probe or _ledger_lease_probe(self._root)
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
                    if sys.platform == "win32":
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
                if sys.platform == "win32":
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
        self._make_room(fetch=fetch)
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
        self._record_borrow(agent, branch)
        self._write_holder_note(agent)
        return self._inspect(
            path, registered=True, branch=branch, head=self._out("rev-parse", MAIN_REF)
        )

    # ── borrowing (D-58) ─────────────────────────────────────────────

    def _borrow_file(self, agent: str) -> Path:
        # A file next to the stations, never inside one: a station stays clean, and `.auto-pm` is ignored by Git.
        return self._stations_dir / f".borrowed-{agent}.json"

    def _record_borrow(self, agent: str, branch: str) -> None:
        """A station opened by another registered agent is on loan to that caller; remember who, so it can hand in the PR.

        ``acts_for`` decides what is the caller's own: its base-name station and its own conversation's alias station are
        not loans.  The borrower is stored as the caller's alias (base name only when no session id exists), so another
        conversation of the same agent is not the borrower (D-86).
        """

        caller = caller_agent()
        if not caller or caller == _UNKNOWN_CALLER or acts_for(caller, agent):
            self._clear_borrow(agent)
            return
        payload = {"by": caller_alias() or caller, "branch": branch}
        self._borrow_file(agent).write_text(json.dumps(payload), encoding="utf-8")

    def _clear_borrow(self, agent: str) -> None:
        try:
            self._borrow_file(agent).unlink(missing_ok=True)
        except OSError:
            pass  # a leftover record only matters while the station exists; open/close rewrite or clear it

    def borrower(self, agent: str) -> str:
        """Who the station of ``agent`` is on loan to ("" when nobody); only a roster name on a readable record counts."""

        try:
            data = json.loads(self._borrow_file(agent).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ""
        by = data.get("by") if isinstance(data, dict) else None
        return by if isinstance(by, str) and base_agent(by) else ""

    def lent_to_caller(self, agent: str) -> bool:
        """Whether the station of ``agent`` is on loan to this very conversation (same alias, or same base name without a session id)."""

        caller = caller_agent()
        if not caller or caller == _UNKNOWN_CALLER:
            return False
        borrower = self.borrower(agent)
        return bool(borrower) and borrower == (caller_alias() or caller)

    # ── 持有者记录、回收（设计稿：动态 agent 名与工位自动回收）──────────────

    @property
    def _notes_dir(self) -> Path:
        return self._root / ".auto-pm" / "station-holders"

    def _write_holder_note(self, agent: str) -> None:
        """记下谁开的这个别名工位（会话 ID、进程号、对话标题），兜底回收靠它判断持有者还在不在。只给别名工位记。"""

        if not _ALIAS.match(agent):
            return
        try:
            self._notes_dir.mkdir(parents=True, exist_ok=True)
            note = {
                "agent": agent,
                "session_id": os.environ.get("CLAUDE_CODE_SESSION_ID", ""),
                # D-76: only a pid the caller declared (CLAUDE_PID) identifies the conversation; ``os.getppid()`` is usually a
                # short-lived shell, whose exit would make a live conversation look stale.  0 = unknown = never reclaimed.
                "pid": int(os.environ.get("CLAUDE_PID", "0") or 0),
                "title": os.environ.get("AUTO_PM_SESSION_TITLE", ""),
                "opened_at": datetime.now(UTC).isoformat(),
                "heartbeat_at": datetime.now(UTC).isoformat(),
            }
            (self._notes_dir / f"{agent}.json").write_text(
                json.dumps(note, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except (OSError, ValueError):
            pass  # 记不下来只会让兜底回收少一条依据，不能挡住开工位

    def _read_holder_note(self, agent: str) -> dict[str, object]:
        try:
            loaded = json.loads((self._notes_dir / f"{agent}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def release(self, agent: str, *, via: str = "release") -> ReleaseResult:
        """对话结束时回收自己的别名工位：先把工位里的一切（含未提交、未跟踪的文件）存成救援引用，再收目录。

        分支一定保留；救援引用 ``refs/rescue/<别名>/<时间>`` 指向一个包含全部改动的快照提交，不动工位分支本身，
        ``git checkout <引用> -- .`` 或 ``git diff <分支> <引用>`` 就能找回。
        """

        with self._stations_lock():
            return self._release_locked(agent, via=via)

    def _release_locked(self, agent: str, *, via: str = "release") -> ReleaseResult:
        """回收一个别名工位，并把每一次回收（成功、被拒、失败）追加记到 ``.auto-pm/logs/station-reclaim.jsonl``（D-166）。"""

        record: dict[str, object] = {"agent": agent, "via": via, "caller": caller_alias() or caller_agent() or "user"}
        try:
            result = self._release_checked(agent, record)
        except Exception as error:  # noqa: BLE001 - any failure is logged, then re-raised unchanged
            record.update(outcome="refused" if isinstance(error, StationRefusedError) else "failed", reason=str(error))
            if isinstance(error, StationLeasedError) and via == "release-self":
                # The SessionEnd hook never fails a closing conversation: it skips and leaves the station to the stale sweep.
                record.update(via="release-self-skipped", outcome="skipped")
            self._log_reclaim(record)
            raise
        record.update(outcome="removed", rescue_ref=result.rescue_ref, branch=result.branch)
        self._log_reclaim(record)
        return result

    def _log_reclaim(self, record: dict[str, object]) -> None:
        """追加一行回收记录；写不进去只丢记录，不能让回收本身失败或留下半截。"""

        line = {"at": datetime.now(UTC).isoformat(), **record}
        folder = self._root / ".auto-pm" / "logs"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            with (folder / "station-reclaim.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(line, ensure_ascii=False) + "\n")
        except OSError:
            return

    def _release_checked(self, agent: str, record: dict[str, object]) -> ReleaseResult:
        if not _ALIAS.match(agent):
            raise AgentWorktreeError(f"`{agent}` 不是会话别名（<基名>-<6位十六进制>）；基名工位用 `worktree close`")
        caller = caller_agent()
        if not acts_for(caller, agent):
            raise StationRefusedError(f"你是 {caller_alias() or caller}，不能回收 {agent} 的工位")
        path = self._stations_dir / agent
        info = self._worktrees().get(path.resolve()) if path.exists() else None
        if info is None:
            raise StationRefusedError(f"{agent} 没有登记在 Git 里的工位（{path}）；用 `worktree list` 看现状")
        self._require_inside(path)
        record.update(branch=info.branch, head=info.head, path=str(path))
        self._require_no_live_lease(path)
        rescue = self._save_rescue_ref(path, agent)
        record["rescue_ref"] = rescue
        removed = self._git("worktree", "remove", "--force", str(path))
        if removed.returncode != 0:
            raise AgentWorktreeError(f"回收失败：{_detail(removed)}；救援引用 {rescue or '(无改动，没建)'} 已保留")
        self._git("worktree", "prune")
        with contextlib.suppress(OSError):
            (self._notes_dir / f"{agent}.json").unlink()
        return ReleaseResult(path=path, branch=info.branch, rescue_ref=rescue)

    def _require_no_live_lease(self, path: Path) -> None:
        """D-169: one gate for every way a station directory can go (release, close, sweep, reclaim, make-room)."""

        try:
            held = self._lease_probe(path)
        except Exception as error:  # noqa: BLE001 - a ledger that cannot answer must not read as "no lease"
            raise StationLeasedError(f"读不出 {path} 上的 Run 租约（{error}）；不能证明没人在用，不回收") from error
        if held:
            raise StationLeasedError(f"{path} 还有未过期的 Run 租约：{held}；Run 结束或租约过期后再收")

    def _save_rescue_ref(self, path: Path, agent: str) -> str:
        """工位里有任何没进分支的东西（改动、未跟踪文件）就存成救援引用并返回引用名；干净则返回空串。"""

        status = self._git("status", "--porcelain=v1", "--untracked-files=all", cwd=path)
        if status.returncode != 0:
            raise AgentWorktreeError(f"回收前读不出工位状态：{_detail(status)}；不回收")
        if not status.stdout.strip():
            return ""
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        ref = f"refs/rescue/{agent}/{stamp}"
        temp_index = self._root / ".auto-pm" / "tmp" / f"rescue-{agent}-{stamp}.index"
        temp_index.parent.mkdir(parents=True, exist_ok=True)
        env = {
            **os.environ,
            "GIT_INDEX_FILE": str(temp_index),
            "GIT_AUTHOR_NAME": "auto-pm",
            "GIT_AUTHOR_EMAIL": "auto-pm@localhost",
            "GIT_COMMITTER_NAME": "auto-pm",
            "GIT_COMMITTER_EMAIL": "auto-pm@localhost",
        }

        def run(*args: str) -> str:
            step = run_git_bounded_text(
                ["git", "-C", str(path), *args],
                default_timeout=300.0,
                error_cls=AgentWorktreeError,
                where=path,
                env=env,
                capture_output=True,
                check=False,
            )
            if step.returncode != 0:
                raise AgentWorktreeError(f"存救援快照失败（git {' '.join(args[:2])}）：{_detail(step)}；不回收")
            return step.stdout.strip()

        try:
            run("read-tree", "HEAD")
            run("add", "-A", "--", ".")
            tree = run("write-tree")
            commit = run("commit-tree", tree, "-p", "HEAD", "-m", f"rescue {agent} {stamp}")
            updated = self._git("update-ref", ref, commit)
            if updated.returncode != 0:
                raise AgentWorktreeError(f"存救援快照失败（update-ref）：{_detail(updated)}；不回收")
        finally:
            with contextlib.suppress(OSError):
                temp_index.unlink()
        return ref

    def touch_heartbeat(self, agent: str, *, min_interval_seconds: float = 0.0) -> bool:
        """刷新别名工位的心跳（并把持有进程号更新成当前这个对话的）。没有这个工位的记录就什么都不做，返回 False。

        ``min_interval_seconds`` > 0 时，上次心跳不到这个间隔就不再写（每条命令都调用也不会把磁盘写花，D-180）；
        返回 True 表示记录在、心跳是新的。
        """

        note = self._read_holder_note(agent)
        if not note:
            return False
        if min_interval_seconds > 0:
            silent = _hours_since(note.get("heartbeat_at"))
            if silent is not None and silent * 3600 < min_interval_seconds:
                return True
        note["heartbeat_at"] = datetime.now(UTC).isoformat()
        pid = int(os.environ.get("CLAUDE_PID", "0") or 0)
        if pid > 0:
            note["pid"] = pid
        try:
            (self._notes_dir / f"{agent}.json").write_text(json.dumps(note, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            return False
        return True

    def stale_aliases(self, *, max_silence_hours: float | None = None) -> list[tuple[str, str]]:
        """别名工位里持有对话已经关了的：返回 (别名, 依据)。

        判定要两个条件**同时**成立：记录的持有进程已经不在，并且心跳已超过 ``max_silence_hours`` 没刷新（默认 2 小时，
        环境变量 ``AUTO_PM_STATION_STALE_HOURS`` 可调）。进程还活着就绝不算陈旧——跑 3 小时门禁、对话里没有消息的时候，
        心跳再旧也不回收。没有持有者记录的也不算（证明不了）。
        """

        limit = max_silence_hours if max_silence_hours is not None else _stale_hours()
        found: list[tuple[str, str]] = []
        if not self._stations_dir.is_dir():
            return found
        for child in sorted(self._stations_dir.iterdir()):
            if not child.is_dir() or not _ALIAS.match(child.name):
                continue
            note = self._read_holder_note(child.name)
            pid = note.get("pid")
            if not isinstance(pid, int) or pid <= 0 or _process_alive(pid):
                continue
            silent = _hours_since(note.get("heartbeat_at") or note.get("opened_at"))
            if silent is None or silent < limit:
                continue
            found.append((child.name, f"记录的持有进程 {pid} 已不在，且 {silent:.1f} 小时没有心跳（阈值 {limit:g} 小时）"))
        return found

    def orphan_records(self, *, max_silence_hours: float | None = None) -> list[tuple[str, str]]:
        """D-180 A: holder records whose station directory is gone for good: returns (alias, reason).

        ``stale_aliases`` walks the station directories, so a record without a directory never reached it and stayed for days.
        A record is an orphan only when all of these hold: the alias has no directory and no Git registration, the recorded
        process is gone (or was never declared: pid 0) and the heartbeat has been silent past the limit.  A record whose
        process is still alive is kept (the conversation may be about to open the station again).
        """

        limit = max_silence_hours if max_silence_hours is not None else _stale_hours()
        found: list[tuple[str, str]] = []
        if not self._notes_dir.is_dir():
            return found
        registered = {_same_path_key(path) for path in self._worktrees()}
        for entry in sorted(self._notes_dir.glob("*.json")):
            name = entry.stem
            if not _ALIAS.match(name):
                continue
            station = self._stations_dir / name
            if station.exists() or _same_path_key(station) in registered:
                continue
            note = self._read_holder_note(name)
            pid = note.get("pid")
            if isinstance(pid, int) and pid > 0 and _process_alive(pid):
                continue
            silent = _hours_since(note.get("heartbeat_at") or note.get("opened_at"))
            if silent is None or silent < limit:
                continue
            who = f"进程 {pid} 已不在" if isinstance(pid, int) and pid > 0 else "没有记录持有进程号"
            found.append((name, f"孤儿持有者记录：工位目录已不存在，{who}，{silent:.1f} 小时没有心跳（阈值 {limit:g} 小时）"))
        return found

    def reclaim_stale(self, *, apply: bool = False) -> list[tuple[str, str]]:
        """列出（加 ``apply`` 则回收）持有者已不在的别名工位和孤儿持有者记录；工位回收走 release，所以一样先存救援引用。"""

        with self._stations_lock():
            stale = self.stale_aliases()
            orphans = self.orphan_records()
            if apply:
                if caller_agent():
                    raise StationRefusedError("回收别的对话的陈旧工位只由用户在自己的终端执行")
                for name, _reason in stale:
                    try:
                        self._release_locked(name, via="reclaim-stale")
                    except StationLeasedError:
                        continue  # D-169: a live Run lease keeps this one (logged as refused); the others are still reclaimed
                for name, reason in orphans:
                    self._drop_orphan_record(name, reason)
            return stale + orphans

    def _drop_orphan_record(self, name: str, reason: str) -> None:
        """Delete only the holder record (nothing else exists for it) and log it like every other reclaim."""

        record: dict[str, object] = {
            "agent": name,
            "via": "orphan-record",
            "caller": caller_alias() or caller_agent() or "user",
            "reason": reason,
        }
        try:
            (self._notes_dir / f"{name}.json").unlink()
            record["outcome"] = "removed"
        except FileNotFoundError:
            return  # someone else removed it meanwhile: nothing to log
        except OSError as error:
            record.update(outcome="failed", reason=f"{reason}；删除失败：{error}")
        self._log_reclaim(record)

    def count(self) -> int:
        """How many directories sit under ``.auto-pm/worktrees`` (registered or not, a missing one still registered counts)."""

        names = {path.name for path in self._worktrees()}
        if self._stations_dir.is_dir():
            names |= {child.name for child in self._stations_dir.iterdir() if child.is_dir()}
        return len(names)

    def _make_room(self, *, fetch: bool = True) -> None:
        """The floor is full: free session-alias stations that are provably dead, then let ``open`` count again (D-166).

        Only a station that satisfies every sweep condition goes (merged into main, clean, nothing unpushed, branch
        prefix right) AND whose holder process is gone with a silent heartbeat (``stale_aliases``).  Roster names,
        ``other`` directories and run-plans are never touched.  Anything uncertain is skipped, never forced; each
        removal is logged with ``via=auto-make-room``.
        """

        if self.count() < MAX_STATIONS:
            return
        try:
            candidates = self.stale_aliases()
            if candidates and fetch:
                self._fetch_prune()  # "merged into main" must be judged on what GitHub has now
        except OSError:
            return
        for name, _reason in candidates:
            if self.count() < MAX_STATIONS:
                return
            try:
                listed = self.stations(only=name)
                if len(listed) != 1 or not self._sweep_verdict(listed[0], None).remove:
                    continue
                self._remove_station(listed[0], require_merged=True, via="auto-make-room")
            except (AgentWorktreeError, OSError):
                continue

    def _require_room_for_a_station(self) -> None:
        count = self.count()
        if count >= MAX_STATIONS:
            raise StationRefusedError(
                f".auto-pm/worktrees 下已有 {count} 个目录，上限 {MAX_STATIONS}（WS-001）；"
                "先 `worktree list` 看哪些已经做完，再 `worktree close <agent>` 或 `worktree sweep`（默认只列，加 --apply 才删）"
                + self._occupant_lines()
            )

    def _occupant_lines(self) -> str:
        """Who fills the floor and who can free each place (D-11): the refusal alone leaves an agent guessing.

        Best effort and read-only: a station that cannot be inspected is listed as such, never a reason to hide the refusal.
        """

        try:
            stations = self.stations()
        except (AgentWorktreeError, OSError):
            return ""
        caller = caller_agent()
        lines: list[str] = []
        for station in stations:
            who = self._who_can_free(station, caller)
            lines.append(f"  - {station.name}：{who}")
        return "\n现在占着的目录：\n" + "\n".join(lines) if lines else ""

    def _who_can_free(self, station: Station, caller: str) -> str:
        verdict = self._sweep_station(station, None)
        if station.kind == "agent":
            owner = station.name
            if verdict.remove:
                answer = f"已做完可收；由 {owner} 执行 `worktree close {owner}`" + (
                    "（就是你）" if caller == owner else "，或用户 `worktree sweep --apply`"
                )
            else:
                answer = f"{owner} 的工位，暂不能收（{verdict.reason}）"
            return answer
        if verdict.remove:
            return f"已可清（{verdict.reason}），只由用户在自己的终端 `worktree sweep --apply`"
        return f"名册外的目录，不属于任何 agent，只由用户处理（{verdict.reason}）"

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
        targets = [(path, info) for path, info in registered.items() if only is None or path.name == only]
        progress_lock = threading.Lock()

        def inspect_one(path: Path, info: _Registered) -> Station:
            if progress is not None:
                with progress_lock:
                    progress(path.name)
            inspected = self._inspect(
                path,
                registered=True,
                branch=info.branch,
                head=info.head,
                locked=info.locked,
                deep=deep,
            )
            return replace(inspected, idle_seconds=_idle_seconds(path))

        stations: list[Station]
        if deep and len(targets) > 1:
            # Each station's Git scan is a separate child process on its own work tree (I/O bound): run them side by
            # side. Results keep the registration order; the first failure in that order is the one raised.
            with ThreadPoolExecutor(max_workers=min(len(targets), DEEP_SCAN_WORKERS)) as pool:
                futures = [pool.submit(inspect_one, path, info) for path, info in targets]
                stations = []
                try:
                    for future in futures:
                        stations.append(future.result())
                except BaseException:
                    for future in futures:
                        future.cancel()
                    raise
        else:
            stations = [inspect_one(path, info) for path, info in targets]
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
        if not (acts_for(caller, agent) or self.lent_to_caller(agent)):
            raise StationRefusedError(
                f"你是 {caller_alias() or caller}，不能收 {agent} 的工位；请 {agent} 自己收，或由用户决定"
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
            if agent is not None and not acts_for(caller, agent):
                raise StationRefusedError(f"你是 {caller_alias() or caller}，只能清自己的工位，不能 --agent {agent}")
            agent = agent or caller
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
            if agent is not None and not branch.startswith(self._prefix(agent)):
                continue
            item = self._sweep_gone(branch)
            items.append(item)
            plans.append((item, None))
        report = SweepReport(items=items, applied=apply, fetch_warning=warning)
        if not apply:
            return report
        # D-74: removal must not interleave with a concurrent ``open``/``release``/``close``; ``_remove_station`` re-reads the
        # station just before deleting, but only under the same lock that those commands take.
        with self._stations_lock():
            for item, station in plans:
                if not item.remove:
                    continue
                try:
                    if station is not None:
                        self._remove_station(
                            station, require_merged=station.kind in ("agent", "other"), via="sweep"
                        )
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
        if station.kind == "agent" and agent is not None and not _in_sweep_scope(station.name, agent):
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
        if not station.branch.startswith(self._prefix(station.name)):
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

    def _remove_station(
        self, station: Station, *, require_merged: bool = False, via: str = "close"
    ) -> CloseResult:
        """Remove one station (close / sweep / auto-make-room); every outcome is logged like a release (D-166)."""

        record: dict[str, object] = {
            "agent": station.name,
            "via": via,
            "caller": caller_alias() or caller_agent() or "user",
            "branch": station.branch,
            "head": station.head,
            "path": str(station.path),
            "rescue_ref": "",
        }
        try:
            result = self._remove_station_checked(station, require_merged=require_merged)
        except Exception as error:  # noqa: BLE001 - any failure is logged, then re-raised unchanged
            record.update(
                outcome="refused" if isinstance(error, StationRefusedError) else "failed", reason=str(error)
            )
            self._log_reclaim(record)
            raise
        # The holder record belongs to the directory that is gone: leaving it behind misleads the next investigation.
        with contextlib.suppress(OSError):
            (self._notes_dir / f"{station.name}.json").unlink()
        record["outcome"] = "removed"
        self._log_reclaim(record)
        return result

    def _remove_station_checked(self, station: Station, *, require_merged: bool = False) -> CloseResult:
        # Re-read everything just before removing: the agent may have kept working since the station was listed.
        self._require_inside(station.path)
        info = self._worktrees().get(station.path.resolve())
        if info is None:
            raise StationRefusedError(f"工位 {station.path} 已不在 Git 登记里，不动")
        self._require_no_live_lease(station.path)
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
        self._clear_borrow(station.path.name)
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
            # One scan answers both questions: ``--ignored=traditional`` with ``-uall`` lists every ignored file
            # on its own ``!!`` line, exactly what ``ls-files --others --ignored --exclude-standard`` listed.
            status = self._git(
                "status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignored=traditional", cwd=path
            )
            if status.returncode != 0:
                raise AgentWorktreeError(f"读不到工位状态 {path}：{_detail(status)}")
            entries = [entry for entry in status.stdout.split("\0") if len(entry) > 3]
            dirty = tuple(sorted(entry[3:] for entry in entries if not entry.startswith("!! ")))
            ignored = tuple(
                sorted(
                    {
                        name.split("/", 1)[0] + ("/" if "/" in name else "")
                        for name in (entry[3:] for entry in entries if entry.startswith("!! "))
                        if not _is_tool_cache(name)
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
        base = base_agent(agent)
        if not base:
            raise AgentWorktreeError(
                f"agent `{agent}` 不在名册里（{'、'.join(AGENT_ROSTER)}，或 <基名>-<6位十六进制> 的会话别名）；"
                "表外的 AI 先由用户登记名字和前缀"
            )
        return AGENT_ROSTER[base]

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


def _stale_hours() -> float:
    try:
        value = float(os.environ.get("AUTO_PM_STATION_STALE_HOURS", "2"))
    except ValueError:
        return 2.0
    return value if value > 0 else 2.0


def _hours_since(stamp: object) -> float | None:
    """ISO 时间到现在过了几小时；读不出来返回 None（按“证明不了”处理，不回收）。"""

    if not isinstance(stamp, str):
        return None
    try:
        moment = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if moment.tzinfo is None:
        return None
    return (datetime.now(UTC) - moment).total_seconds() / 3600


def touch_session_heartbeat(control_root: str | Path) -> None:
    """尽力刷新本对话别名工位的心跳；任何问题都吞掉（门禁、租约续期不能被它拖垮）。"""

    try:
        alias = caller_alias()
        if alias:
            AgentWorktreeService(control_root, run_state=lambda run_id: None, measure_size=False).touch_heartbeat(alias)
    except Exception:  # noqa: BLE001 - 心跳只是兜底回收的依据
        return


def _in_sweep_scope(name: str, agent: str) -> bool:
    """``sweep --agent X`` 管的工位：X 自己；调用者就是 X 且有本对话别名时，再加上本对话的别名工位（别的对话的不碰）。"""

    if name == agent:
        return True
    alias = caller_alias()
    return bool(alias) and agent == caller_agent() and name == alias


def _process_alive(pid: int) -> bool:
    """进程还在不在；读不出来按“在”处理（宁可不回收）。"""

    return _windows_alive(pid) if os.name == "nt" else _posix_alive(pid)


def _windows_alive(pid: int) -> bool:
    import ctypes

    kernel32 = getattr(ctypes, "windll").kernel32  # noqa: B009 - windll 只在 Windows 上有，getattr 让别的平台的类型检查也过
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return bool(kernel32.GetLastError() != 87)  # 87 = 参数错误 = 进程号不存在
    try:
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return bool(code.value == 259)  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _posix_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _kind(name: str) -> str:
    if base_agent(name):
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
