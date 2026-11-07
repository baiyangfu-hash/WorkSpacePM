"""auto_pm.application.core.control_root_sync - tell the user early that the control root does not match ``origin/main``.

``run start`` refuses to open an isolated Run when the control root holds files of the Run's scope that differ from the commit
the station is cut from (``CandidateMergeBackService.control_root_drift``): the Run's closure could never merge back.  Until
now the user learned this only at ``run start``, after the request had been filed and approved.  This service answers the same
question earlier -- at ``pm inbox add``, ``pm approve`` and ``pm orient`` -- in plain words, with what to do about it.

Read-only by design: it never fetches, never touches the control root, never writes.  It looks at the ``origin/main`` the
control root already has (the state of its last fetch); with no such reference (no origin, never fetched) the answer is
"not verified", never an error.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from auto_pm.application.core.candidate_merge_back_service import (
    CandidateMergeBackError,
    CandidateMergeBackService,
)
from auto_pm.domain.change.file_locator import ChangeFileLocator
from auto_pm.domain.change.parser import ChgParser
from auto_pm.infrastructure.control_root_guard import authority_paths_covered, clean_git_environment
from auto_pm.infrastructure.git_timeout import run_git_bounded

MAIN_REF = "refs/remotes/origin/main"
GIT_TIMEOUT_SECONDS = 60.0
SHOWN_PATHS = 8
# An unclaimed uncommitted file older than this is called out as forgotten (D-13: files sat in the control root for two weeks).
FORGOTTEN_DAYS = 3


class ControlRootSyncError(Exception):
    """Git could not answer a question; the caller reports 'not verified'."""


@dataclass(frozen=True)
class UncommittedFile:
    """One uncommitted path in the control root, with whoever the ledger says holds it (D-13)."""

    path: str
    status: str
    age_days: int | None = None
    # "Run <id>（<executor>）" when a live Run owns the path; empty when no Run claims it.
    owner: str = ""

    def as_json(self) -> dict[str, object]:
        return {"path": self.path, "status": self.status, "age_days": self.age_days, "owner": self.owner}

    def label(self) -> str:
        who = self.owner or "没有 Run 认领"
        age = "" if self.age_days is None else f"，{self.age_days} 天"
        return f"{self.path}（{who}{age}）"


@dataclass(frozen=True)
class SyncReport:
    verified: bool
    behind: int = 0
    ahead: int = 0
    duplicate_ahead: tuple[str, ...] = ()
    unique_ahead: tuple[str, ...] = ()
    dirty_in_scope: tuple[str, ...] = ()
    drift_in_scope: tuple[str, ...] = ()
    # Local commits that change files, yet the scope holds exactly what ``origin/main`` holds: most likely squashed into main.
    maybe_squashed: bool = False
    # Commits ahead of main that ``git cherry`` does not list (merge commits).
    other_ahead: int = 0
    note: str = ""
    # No remote called origin at all: there is nothing to be out of step with.  Reported as "not verified" by the data, but the
    # commands print nothing for it (a lone local repository would otherwise get a useless line on every command).
    no_origin: bool = False
    # D-44: which branch the control root is on.  ``branch_known`` is False when Git could not say (the fields below mean nothing).
    branch_known: bool = False
    branch: str = ""
    detached: bool = False
    # D-13: every uncommitted path in the control root (not only the Run's scope), with its holder and age.
    uncommitted: tuple[UncommittedFile, ...] = ()

    @property
    def on_main(self) -> bool:
        return self.branch_known and not self.detached and self.branch == "main"

    @property
    def off_main(self) -> bool:
        """True when Git positively says the control root sits on another branch or a detached HEAD."""

        return self.branch_known and not self.on_main

    @property
    def forgotten(self) -> tuple[UncommittedFile, ...]:
        return tuple(
            item for item in self.uncommitted if not item.owner and (item.age_days or 0) >= FORGOTTEN_DAYS
        )

    @property
    def blocks_run_start(self) -> bool:
        """True when ``run start`` would refuse: files of the scope differ from ``origin/main`` (or are uncommitted)."""

        return bool(self.drift_in_scope)

    @property
    def needs_attention(self) -> bool:
        if self.no_origin:
            return False
        return (not self.verified) or bool(
            self.behind or self.ahead or self.dirty_in_scope or self.drift_in_scope or self.off_main or self.uncommitted
        )

    def lines(self) -> tuple[str, ...]:
        """Plain-words hints, empty when everything matches."""

        if self.no_origin:
            return ()
        if not self.verified:
            return (
                f"控制根与 origin/main 是否一致：未核实（{self.note}）。离线或没有 origin 时不影响入箱与批准；开工前请联网后再看一次。",
                *self._holder_lines(),
            )
        out: list[str] = []
        if self.behind:
            out.append(
                f"控制根落后 origin/main {self.behind} 个提交（按最近一次 fetch 的结果）。"
                "处理：在控制根执行 `git fetch origin main`，再执行 `git merge --ff-only origin/main`（只快进，不会改你的文件）；"
                "不能快进说明控制根有 main 里没有的本地提交，见下一条。"
            )
        if self.duplicate_ahead:
            out.append(
                f"控制根有 {len(self.duplicate_ahead)} 个本地提交在 origin/main 里已有内容相同的提交（重复）："
                + _shown(self.duplicate_ahead)
                + "。这些重复提交让控制根无法快进。需要用户决定如何对齐 main（不要自行 reset 或删除）。"
            )
        if self.unique_ahead and self.maybe_squashed:
            out.append(
                f"控制根有 {len(self.unique_ahead)} 个 origin/main 里没有的本地提交："
                + _shown(self.unique_ahead)
                + "，但本项目范围内的文件和 origin/main 完全一致：内容可能已被 squash 合并进 main。"
                "请用户确认后再对齐 main（不要自行 reset 或删除，也不要为它们再推一个 PR）。"
            )
        elif self.unique_ahead:
            out.append(
                f"控制根有 {len(self.unique_ahead)} 个 origin/main 里没有的本地提交："
                + _shown(self.unique_ahead)
                + "。先推送成 PR 或交用户处理，再对齐 main。"
            )
        if self.other_ahead:
            out.append(f"控制根还有 {self.other_ahead} 个 origin/main 里没有的本地合并提交。需要用户决定如何对齐 main（不要自行 reset 或删除）。")
        if self.dirty_in_scope:
            out.append(
                f"控制根里归属范围内有 {len(self.dirty_in_scope)} 个未提交的文件：" + _shown(self.dirty_in_scope)
                + "。请先提交或还原（多半是上一单收口并回、还没提交）。"
            )
        if self.drift_in_scope and not (self.behind or self.dirty_in_scope):
            out.append(f"控制根里归属范围内有 {len(self.drift_in_scope)} 个文件和 origin/main 不一致：" + _shown(self.drift_in_scope) + "。")
        if self.blocks_run_start:
            out.append("按现在的状态，之后 `run start` 一定会被拒（控制根范围内的文件与开工起点不一致）；先按上面处理，再批准或开工。")
        out.extend(self._holder_lines())
        return tuple(out)

    def _holder_lines(self) -> tuple[str, ...]:
        """Lines about where the control root stands (D-44) and whose uncommitted files it holds (D-13)."""

        out: list[str] = []
        if self.off_main:
            where = "游离 HEAD（不在任何分支上）" if self.detached else f"分支 {self.branch}"
            out.append(
                f"控制根现在在{where}，不在 main：别的线程和 agent 读到的“控制根”就是这个分支的内容，对不上 main。"
                "用完请切回 main（`git switch main`；有未提交文件先按下一条弄清归属，不要带着走）。"
            )
        if self.uncommitted:
            others = [item for item in self.uncommitted if not item.owner]
            held = [item for item in self.uncommitted if item.owner]
            parts: list[str] = []
            if held:
                parts.append("有 Run 认领的：" + _shown([item.label() for item in held]))
            if others:
                parts.append("没有 Run 认领的：" + _shown([item.label() for item in others]))
            out.append(
                f"控制根里有 {len(self.uncommitted)} 个未提交的文件。" + "；".join(parts)
                + "。认领的文件是别的线程在做的活，不要动它，也不会挡你自己范围外的 Run。"
            )
            if self.forgotten:
                out.append(
                    f"其中 {len(self.forgotten)} 个没人认领、已放了 {FORGOTTEN_DAYS} 天以上，多半是被提交钩子拦下或收口后忘了提交的："
                    + _shown([item.path for item in self.forgotten])
                    + "。请用户决定提交还是还原（agent 不要自己删，也不要自己提交别人的文件）。"
                )
        return tuple(out)

    def as_json(self) -> dict[str, object]:
        return {
            "verified": self.verified,
            "behind": self.behind,
            "ahead": self.ahead,
            "duplicate_ahead": list(self.duplicate_ahead),
            "unique_ahead": list(self.unique_ahead),
            "dirty_in_scope": list(self.dirty_in_scope),
            "drift_in_scope": list(self.drift_in_scope),
            "maybe_squashed": self.maybe_squashed,
            "other_ahead": self.other_ahead,
            "blocks_run_start": self.blocks_run_start,
            "note": self.note,
            "no_origin": self.no_origin,
            "branch": self.branch if self.branch_known else None,
            "detached": self.detached if self.branch_known else None,
            "on_main": self.on_main if self.branch_known else None,
            "uncommitted": [item.as_json() for item in self.uncommitted],
            "hints": list(self.lines()),
        }


def _shown(items: Sequence[str]) -> str:
    head = "、".join(items[:SHOWN_PATHS])
    return head + (f" 等共 {len(items)} 个" if len(items) > SHOWN_PATHS else "")


OwnerLookup = Callable[[str], str]


def live_run_owner_lookup(store: Any, project_id: str) -> OwnerLookup:
    """Map a control-root path to ``Run <id>（<executor>）`` for the live Runs of one project; "" when no live Run owns it."""

    claims: list[tuple[tuple[str, ...], str]] = []
    if project_id:
        for work in store.list_works(project_id):
            for run in store.list_runs(work.work_id):
                claims.append((tuple(run.owned_paths), f"Run {run.run_id}（{run.executor_id}）"))

    def lookup(path: str) -> str:
        for owned, label in claims:
            if authority_paths_covered((path,), owned):
                return label
        return ""

    return lookup


class ControlRootSyncService:
    def __init__(self, control_root: str | Path, *, owner_of: OwnerLookup | None = None) -> None:
        self._root = Path(control_root).resolve()
        self._owner_of = owner_of

    def project_scope(self, project_id: str) -> tuple[str, ...]:
        """The project's folder, relative to the control root; empty when it cannot be found."""

        if not project_id:
            return ()
        try:
            found = ChangeFileLocator(str(self._root), ChgParser()).get_project_path(project_id)
            if not found:
                return ()
            return (Path(found).resolve().relative_to(self._root).as_posix() or ".",)
        except (OSError, ValueError):
            return ()

    def run_drift_lines(self, owned_paths: Sequence[str], git_head: str) -> tuple[str, ...]:
        """For a Run already started: control-root files of its scope that changed since its start (``git_head``).

        Closure writes the accepted bytes back only over files that still hold the Run's start version; a file someone changed
        in the control root meanwhile makes ``pm close`` refuse.  Saying so before the ~15 minute ``pm verify`` saves that wait.
        """

        try:
            drift = CandidateMergeBackService(self._root).control_root_drift(tuple(owned_paths), git_head)
        except CandidateMergeBackError:
            return ()  # cannot tell (no such commit, no Git): stay silent, closure still checks
        if not drift:
            return ()
        return (
            f"控制根里本 Run 范围内有 {len(drift)} 个文件自开工起点之后被改动：" + _shown(drift)
            + "。收口（pm close）把验收过的文件并回控制根时会因此被拒。请先确认这些改动（多半是别的卡并回后还没提交，或有人在控制根里改了文件），提交或还原后再验证。",
        )

    def check(self, scope_paths: Sequence[str] = ()) -> SyncReport:
        """Compare the control root with ``origin/main`` for the given scope (paths relative to the control root)."""

        try:
            report = self._check(tuple(scope_paths))
        except ControlRootSyncError as error:
            report = SyncReport(verified=False, note=str(error))
        try:
            return replace(report, **self._holder_state())
        except ControlRootSyncError:
            return report  # the branch and the holders are extra: a Git that cannot say them leaves the rest as it was

    def _holder_state(self) -> dict[str, Any]:
        """Which branch the control root is on, and every uncommitted path with its holder and age (D-44, D-13)."""

        head = self._git(["symbolic-ref", "--short", "-q", "HEAD"], allow_failure=True)
        branch = (head or b"").decode("utf-8", errors="replace").strip()  # lenient-decode: a branch name only labels a hint
        state: dict[str, Any] = {"branch_known": True, "branch": branch, "detached": not branch}
        now = time.time()
        files: list[UncommittedFile] = []
        listing = self._text(["status", "--porcelain", "-z", "--no-renames", "--untracked-files=normal"])
        for item in listing.split("\0"):
            if len(item) <= 3 or item[2] != " ":
                continue
            path = item[3:]
            try:
                age: int | None = max(0, int((now - (self._root / path).stat().st_mtime) // 86400))
            except OSError:
                age = None  # a deleted path has no age
            owner = ""
            if self._owner_of is not None:
                try:
                    owner = self._owner_of(path.rstrip("/"))
                except Exception:  # noqa: BLE001 - a ledger that cannot answer leaves the file unclaimed, never fails the hint
                    owner = ""
            files.append(UncommittedFile(path=path, status=item[:2].strip() or "?", age_days=age, owner=owner))
        state["uncommitted"] = tuple(sorted(files, key=lambda f: f.path))
        return state

    def _check(self, scope: tuple[str, ...]) -> SyncReport:
        if self._git(["rev-parse", "--verify", "--quiet", MAIN_REF], allow_failure=True) is None:
            if self._git(["remote", "get-url", "origin"], allow_failure=True) is None:
                return SyncReport(verified=False, note="这个仓库没有叫 origin 的远端，没有可比较的对象", no_origin=True)
            return SyncReport(verified=False, note="本机没有 origin/main 记录：离线，或从没 fetch 过")
        counts = self._text(["rev-list", "--left-right", "--count", f"HEAD...{MAIN_REF}"]).split()
        if len(counts) != 2 or not all(item.isdigit() for item in counts):
            raise ControlRootSyncError("Git 返回的提交计数无法解读")
        ahead, behind = int(counts[0]), int(counts[1])
        duplicate: list[str] = []
        unique: list[str] = []
        unique_full: list[str] = []
        if ahead:
            for line in self._text(["cherry", MAIN_REF, "HEAD"]).splitlines():
                mark, _, commit = line.partition(" ")
                if mark == "-":
                    duplicate.append(commit[:10])
                else:
                    unique.append(commit[:10])
                    unique_full.append(commit)
        dirty: tuple[str, ...] = ()
        drift: tuple[str, ...] = ()
        if scope:
            specs = ["--", *scope]
            # --no-renames: a staged rename would add a second, status-less field that a directory name with a space as its
            # third character ("项目 甲/…") makes look like a status line.
            dirty = self._paths(
                ["status", "--porcelain", "-z", "--no-renames", "--untracked-files=all", *specs], status_lines=True
            )
            changed = self._paths(["diff", "--name-only", "-z", "--no-renames", MAIN_REF, *specs])
            untracked = self._paths(["ls-files", "--others", "--exclude-standard", "-z", *specs])
            drift = tuple(sorted(set(changed) | set(untracked)))
        # "The scope matches main" is a hint only when a local commit really changed a file of that scope: an empty, mistyped
        # or unrelated scope matches main trivially and would turn the hint into a guess from nothing.
        maybe_squashed = bool(scope) and not drift and any(self._changes_files(commit, scope) for commit in unique_full)
        return SyncReport(
            verified=True,
            behind=behind,
            ahead=ahead,
            duplicate_ahead=tuple(duplicate),
            unique_ahead=tuple(unique),
            dirty_in_scope=dirty,
            drift_in_scope=drift,
            maybe_squashed=maybe_squashed,
            other_ahead=max(0, ahead - len(duplicate) - len(unique)),
        )

    def _changes_files(self, commit: str, scope: tuple[str, ...]) -> bool:
        """Does the commit change any file of the scope?  (An empty commit, or one elsewhere, says nothing about squashing.)"""

        return bool(
            self._text(["diff-tree", "--no-commit-id", "--name-only", "-r", "-z", "--root", commit, "--", *scope]).strip("\0")
        )

    def _git(self, arguments: list[str], *, allow_failure: bool = False) -> bytes | None:
        result = run_git_bounded(
            ["git", "-C", str(self._root), *arguments],
            default_timeout=GIT_TIMEOUT_SECONDS,
            error_cls=ControlRootSyncError,
            where=self._root,
            capture_output=True,
            check=False,
            env=clean_git_environment(),
        )
        if result.returncode != 0:
            if allow_failure:
                return None
            raise ControlRootSyncError("git " + " ".join(arguments[:2]) + " 失败")
        return result.stdout

    def _text(self, arguments: list[str]) -> str:
        data = self._git(arguments) or b""
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ControlRootSyncError("Git 输出不是合法 UTF-8") from error

    def _paths(self, arguments: list[str], *, status_lines: bool = False) -> tuple[str, ...]:
        items = [item for item in self._text(arguments).split("\0") if item]
        if status_lines:  # "XY path" -- a rename carries a second path as its own field, which has no status prefix
            return tuple(sorted({item[3:] for item in items if len(item) > 3 and item[2] == " "}))
        return tuple(items)
