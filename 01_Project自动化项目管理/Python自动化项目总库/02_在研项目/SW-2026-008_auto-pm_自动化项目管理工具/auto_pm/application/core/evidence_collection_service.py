"""Fail-closed, Run-scoped Git evidence collection.

The collector is deliberately read-only.  It validates the governed worktree
recorded by a :class:`~auto_pm.contracts.continuity.RunItem`, then captures the
baseline-to-index and index-to-worktree patches independently.  This preserves
the distinction between staged work and later, unstaged additions to it.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from auto_pm.contracts.continuity import RunItem
from auto_pm.infrastructure.control_root_guard import (
    ControlRootGuardError,
    authority_path_parts,
    clean_git_environment,
    governed_worktree_snapshot,
)


class EvidenceCollectionError(RuntimeError):
    """Raised when Run-scoped Git evidence cannot be collected safely."""


@dataclass(frozen=True)
class EvidenceCollection:
    """Immutable Git evidence captured from one verified Run worktree."""

    run_id: str
    git_head: str
    worktree_path: str
    staged_paths: tuple[str, ...]
    unstaged_paths: tuple[str, ...]
    untracked_paths: tuple[str, ...]
    staged_diff: str
    unstaged_diff: str

    @property
    def baseline_git_head(self) -> str:
        """Expose the Run baseline with an explicit evidence-oriented name."""

        return self.git_head


@dataclass(frozen=True)
class _DirtySnapshot:
    """The three Git dirty classes that must each remain within Run ownership."""

    staged_paths: tuple[str, ...]
    unstaged_paths: tuple[str, ...]
    untracked_paths: tuple[str, ...]


class EvidenceCollectionService:
    """Collect baseline-relative evidence from exactly the Run candidate worktree."""

    def __init__(self, workspace_root: str | Path) -> None:
        self._workspace_root = Path(workspace_root).resolve()

    def collect(self, run: RunItem) -> EvidenceCollection:
        """Return separate staged and unstaged patches after validating Run scope.

        ``staged_diff`` is the baseline-to-index patch.  ``unstaged_diff`` is
        the index-to-worktree patch, so a file changed, staged, then changed
        again contributes evidence to both fields without conflating them.
        """

        owned_paths = self._normalize_owned_paths(run.owned_paths)
        candidate, head = self._verified_candidate(run)
        before = self._dirty_snapshot(candidate, run.git_head)
        self._reject_foreign_paths(before, owned_paths)

        staged_diff = self._git_output(
            candidate,
            "diff",
            "--binary",
            "--no-ext-diff",
            "--no-renames",
            "--cached",
            run.git_head,
            "--",
        )
        unstaged_diff = self._git_output(
            candidate,
            "diff",
            "--binary",
            "--no-ext-diff",
            "--no-renames",
            "--",
        )

        after = self._dirty_snapshot(candidate, run.git_head)
        final_candidate, final_head = self._verified_candidate(run)
        if candidate != final_candidate or head != final_head or before != after:
            raise EvidenceCollectionError("Run worktree Git snapshot 在采集期间发生漂移")

        if (
            staged_diff
            != self._git_output(
                candidate,
                "diff",
                "--binary",
                "--no-ext-diff",
                "--no-renames",
                "--cached",
                run.git_head,
                "--",
            )
            or unstaged_diff
            != self._git_output(
                candidate,
                "diff",
                "--binary",
                "--no-ext-diff",
                "--no-renames",
                "--",
            )
        ):
            raise EvidenceCollectionError("Run worktree diff 在采集期间发生漂移")

        return EvidenceCollection(
            run_id=run.run_id,
            git_head=run.git_head,
            worktree_path=str(candidate),
            staged_paths=before.staged_paths,
            unstaged_paths=before.unstaged_paths,
            untracked_paths=before.untracked_paths,
            staged_diff=staged_diff,
            unstaged_diff=unstaged_diff,
        )

    def _verified_candidate(self, run: RunItem) -> tuple[Path, str]:
        try:
            candidate, observed_head, _ = governed_worktree_snapshot(
                self._workspace_root,
                run.worktree_path,
            )
        except ControlRootGuardError as error:
            raise EvidenceCollectionError(str(error)) from error
        if observed_head != run.git_head:
            raise EvidenceCollectionError("Run git_head 与受管 worktree 当前 HEAD 不一致")
        return candidate, observed_head

    def _dirty_snapshot(self, candidate: Path, baseline: str) -> _DirtySnapshot:
        return _DirtySnapshot(
            staged_paths=self._git_paths(
                candidate,
                "diff",
                "--cached",
                "--name-only",
                "-z",
                "--no-renames",
                baseline,
                "--",
            ),
            unstaged_paths=self._git_paths(
                candidate,
                "diff",
                "--name-only",
                "-z",
                "--no-renames",
                "--",
            ),
            untracked_paths=self._git_paths(
                candidate,
                "ls-files",
                "--others",
                "--exclude-standard",
                "-z",
            ),
        )

    def _reject_foreign_paths(
        self,
        snapshot: _DirtySnapshot,
        owned_paths: tuple[tuple[str, ...], ...],
    ) -> None:
        for label, paths in (
            ("staged", snapshot.staged_paths),
            ("unstaged", snapshot.unstaged_paths),
            ("untracked", snapshot.untracked_paths),
        ):
            foreign = tuple(path for path in paths if not self._path_is_owned(path, owned_paths))
            if foreign:
                rendered = ", ".join(foreign)
                raise EvidenceCollectionError(
                    f"Run {label} dirty path 超出 owned_paths: {rendered}"
                )

    @staticmethod
    def _normalize_owned_paths(paths: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
        normalized: list[tuple[str, ...]] = []
        seen: set[tuple[str, ...]] = set()
        for raw in paths:
            text = str(raw).replace("\\", "/")
            raw_segments = text.split("/")
            candidate = PurePosixPath(text)
            if (
                not text
                or "\0" in text
                or candidate.is_absolute()
                or any(segment in {".", ".."} for segment in raw_segments)
                or any(part != part.rstrip(" .") or ":" in part for part in candidate.parts)
            ):
                raise EvidenceCollectionError(f"Run owned_paths 包含非法 path: {raw}")
            key = authority_path_parts(candidate.as_posix())
            if not key:
                raise EvidenceCollectionError(f"Run owned_paths 包含非法 path: {raw}")
            if key not in seen:
                seen.add(key)
                normalized.append(key)
        if not normalized:
            raise EvidenceCollectionError("Run owned_paths 不能为空")
        return tuple(normalized)

    @staticmethod
    def _path_is_owned(path: str, owned_paths: tuple[tuple[str, ...], ...]) -> bool:
        key = authority_path_parts(path)
        return any(key[: len(root)] == root for root in owned_paths)

    def _git_paths(self, candidate: Path, *arguments: str) -> tuple[str, ...]:
        output = self._git_output(candidate, *arguments)
        return tuple(sorted({path.replace("\\", "/") for path in output.split("\0") if path}))

    @staticmethod
    def _git_output(candidate: Path, *arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(candidate), *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=clean_git_environment(),
        )
        if result.returncode != 0 or result.stderr.strip():
            details = result.stderr.strip() or result.stdout.strip() or "unknown git error"
            raise EvidenceCollectionError(f"Run worktree Git evidence 采集失败: {details}")
        return result.stdout


__all__ = ["EvidenceCollection", "EvidenceCollectionError", "EvidenceCollectionService"]
