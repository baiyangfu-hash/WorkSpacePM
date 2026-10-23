"""Bring the accepted bytes of an isolated Run back into the control root at closure (gap 8, doubt 6).

An isolated Run edits a linked worktree (``.auto-pm/worktrees/run-plan-*`` or the IDE agent's own ``git worktree add``).
Before this step a Mission could close while the accepted change stayed in that worktree and the control root kept the old
bytes; D08 track 2 copied the files back by hand.  Closure now does it, fail-closed and all-or-nothing:

* the worktree must still be exactly what the quality checkpoint verified (same collection hash), so nothing unverified
  can ride along;
* a control-root file is overwritten only while it still equals the Run's baseline commit (Git clean filters applied, so a
  Windows checkout with CRLF is not mistaken for a foreign edit), or it is left alone when it already holds the accepted
  bytes (a replay, or a hand copy made earlier);
* anything else is a conflict and nothing is written; a deletion is never carried out for the user;
* after writing, every file is read back and compared byte for byte.

Nothing is committed: the control root's branch and its commits stay the user's (and the PR flow's) business.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from auto_pm.application.core.evidence_collection_service import (
    EvidenceCollectionError,
    EvidenceCollectionService,
)
from auto_pm.contracts.continuity import CheckpointItem, RunItem
from auto_pm.infrastructure.control_root_guard import clean_git_environment


class CandidateMergeBackError(RuntimeError):
    """Raised when the accepted bytes cannot be brought back safely; nothing has been written."""


@dataclass(frozen=True)
class MergeBackReceipt:
    """What one merge-back did: files written now, and files that already held the accepted bytes."""

    written: tuple[str, ...]
    already_present: tuple[str, ...]


class CandidateMergeBackService:
    """Copy the verified candidate bytes of one isolated Run into the control root, or refuse without writing."""

    def __init__(self, control_root: str | Path) -> None:
        self._control_root = Path(control_root).resolve()

    def is_isolated(self, run: RunItem) -> bool:
        return self.is_isolated_path(run.worktree_path)

    def is_isolated_path(self, worktree_path: str | Path) -> bool:
        return not _same_path(Path(worktree_path), self._control_root)

    def control_root_drift(self, owned_paths: tuple[str, ...], git_head: str) -> tuple[str, ...]:
        """Owned control-root files that already differ from ``git_head`` (modified, deleted or untracked).

        Checked when an isolated Run starts: its worktree is cut from ``git_head``, so such a file would conflict at
        closure (typically the previous Mission's accepted bytes, merged back but not yet committed).  Refusing at the
        start keeps the rule that an accepted Mission is never left unclosable.
        """

        if not owned_paths:
            return ()
        pathspecs = ["--", *owned_paths]
        changed = self._git_z(["diff", "--name-only", "-z", "--no-renames", git_head, *pathspecs])
        untracked = self._git_z(["ls-files", "--others", "--exclude-standard", "-z", *pathspecs])
        return tuple(sorted(set(changed) | set(untracked)))

    def _git_z(self, arguments: list[str]) -> tuple[str, ...]:
        result = subprocess.run(
            ["git", "-C", str(self._control_root), *arguments],
            capture_output=True,
            check=False,
            env=clean_git_environment(),
        )
        if result.returncode != 0:
            message = result.stderr.decode("utf-8", errors="replace").strip()
            raise CandidateMergeBackError(f"无法核对控制根: {message or 'git 失败'}")
        return tuple(item for item in result.stdout.decode("utf-8", errors="replace").split("\0") if item)

    def merge_back(self, run: RunItem, checkpoint: CheckpointItem) -> MergeBackReceipt:
        if not self.is_isolated(run):
            return MergeBackReceipt(written=(), already_present=())
        candidate = Path(run.worktree_path)
        if not candidate.is_dir():
            raise CandidateMergeBackError(
                f"隔离工作树已不存在（{run.worktree_path}），无法把验收过的文件并回控制根；请勿删除工作树后再收口"
            )
        try:
            collection = EvidenceCollectionService(self._control_root).collect(run)
        except EvidenceCollectionError as error:
            raise CandidateMergeBackError(f"无法复核隔离工作树: {error}") from error
        if collection.content_hash != _verified_collection_hash(checkpoint):
            raise CandidateMergeBackError(
                "隔离工作树在质量验证之后又被改动，与验收的内容不一致；请重新 pm verify 并由用户重新验收"
            )

        paths = sorted(
            set(collection.staged_paths) | set(collection.unstaged_paths) | set(collection.untracked_paths)
        )
        to_write: list[tuple[str, bytes]] = []
        already: list[str] = []
        refusals: list[str] = []
        for relative in paths:
            accepted = _read_file(candidate, relative)
            current = _read_file(self._control_root, relative)
            if accepted is None:
                if current is None:
                    already.append(relative)
                else:
                    refusals.append(f"{relative}（验收结果删除了此文件；收口不替你删除，请确认后在控制根手工删除再重试）")
                continue
            if current == accepted:
                already.append(relative)
            elif self._equals_baseline(relative, current, run.git_head):
                to_write.append((relative, accepted))
            else:
                refusals.append(f"{relative}（控制根里的此文件既不是 Run 起点版本也不是验收版本，可能被别人改过）")
        if refusals:
            raise CandidateMergeBackError("未并回控制根，一个文件都没写：" + "；".join(refusals))

        for relative, data in to_write:
            _atomic_write(self._control_root, relative, data)
        mismatched = [
            relative for relative, data in to_write if _read_file(self._control_root, relative) != data
        ]
        if mismatched:
            raise CandidateMergeBackError("并回后逐字节复核不一致：" + "、".join(mismatched))
        return MergeBackReceipt(
            written=tuple(relative for relative, _ in to_write), already_present=tuple(already)
        )

    def _equals_baseline(self, relative: str, current: bytes | None, git_head: str) -> bool:
        """True when the control-root file is still the Run's baseline (absent in both counts as equal)."""

        baseline = self._git(["rev-parse", "--verify", "--quiet", f"{git_head}:{relative}"])
        if current is None:
            return baseline is None
        if baseline is None:
            return False
        observed = self._git(["hash-object", "--path", relative, "--stdin"], stdin=current)
        return observed is not None and observed == baseline

    def _git(self, arguments: list[str], *, stdin: bytes | None = None) -> str | None:
        result = subprocess.run(
            ["git", "-C", str(self._control_root), *arguments],
            input=stdin if stdin is not None else b"",
            capture_output=True,
            check=False,
            env=clean_git_environment(),
        )
        if result.returncode != 0:
            return None
        return result.stdout.decode("utf-8", errors="replace").strip() or None


def _same_path(left: Path, right: Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except OSError:
        return os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve()))


def _verified_collection_hash(checkpoint: CheckpointItem) -> str:
    if len(checkpoint.evidence) != 1:
        raise CandidateMergeBackError("验收 Checkpoint 不是系统生成的质量证据，无法确认隔离工作树内容")
    try:
        envelope = json.loads(checkpoint.evidence[0])
    except ValueError as error:
        raise CandidateMergeBackError("验收 Checkpoint 证据无法解析") from error
    value = envelope.get("collection_hash") if isinstance(envelope, dict) else None
    if not isinstance(value, str) or not value:
        raise CandidateMergeBackError("验收 Checkpoint 证据缺少内容指纹，无法确认隔离工作树内容")
    return value


def _target(root: Path, relative: str) -> Path:
    parts = PurePosixPath(relative).parts
    if not parts or PurePosixPath(relative).is_absolute() or any(part in {"", ".", ".."} for part in parts):
        raise CandidateMergeBackError(f"非法路径: {relative}")
    return root.joinpath(*parts)


def _read_file(root: Path, relative: str) -> bytes | None:
    path = _target(root, relative)
    if path.is_symlink():
        raise CandidateMergeBackError(f"不并回符号链接: {relative}")
    if not path.exists():
        return None
    if not path.is_file():
        raise CandidateMergeBackError(f"不是普通文件: {relative}")
    return path.read_bytes()


def _atomic_write(root: Path, relative: str, data: bytes) -> None:
    target = _target(root, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".merge-back", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
        os.replace(temporary, target)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


__all__ = ["CandidateMergeBackError", "CandidateMergeBackService", "MergeBackReceipt"]
