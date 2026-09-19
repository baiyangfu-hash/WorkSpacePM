"""Fail-closed, Run-scoped Git evidence collection.

The collector is deliberately read-only.  It validates the governed worktree
recorded by a :class:`~auto_pm.contracts.continuity.RunItem`, then captures the
baseline-to-index and index-to-worktree patches independently.  This preserves
the distinction between staged work and later, unstaged additions to it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
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

    @property
    def content_hash(self) -> str:
        """Return the deterministic fingerprint of all baseline-relative evidence."""

        return _sha256_payload(
            {
                "run_id": self.run_id,
                "git_head": self.git_head,
                "worktree_path": self.worktree_path,
                "staged_paths": self.staged_paths,
                "unstaged_paths": self.unstaged_paths,
                "untracked_paths": self.untracked_paths,
                "staged_diff": self.staged_diff,
                "unstaged_diff": self.unstaged_diff,
            }
        )


@dataclass(frozen=True)
class PythonQualityGate:
    """One actual quality-gate process execution, including its immutable output proof."""

    name: str
    command: tuple[str, ...]
    cwd: str
    exit_code: int | None
    output_digest: str
    output_summary: str

    @property
    def passed(self) -> bool:
        """A process passes only when it was launched and exited successfully."""

        return self.exit_code == 0


@dataclass(frozen=True)
class PythonQualityReceipt:
    """Content-bound result of the real pytest, Ruff, and Mypy quality gates."""

    run_id: str
    baseline_git_head: str
    candidate_path: str
    project_root: str
    evidence_hash: str
    gates: tuple[PythonQualityGate, ...]
    evidence_current: bool
    evidence_error: str | None
    content_hash: str

    @property
    def status(self) -> str:
        """Return PASS only for three successful commands and unchanged evidence."""

        if self.evidence_current and all(gate.passed for gate in self.gates):
            return "PASS"
        return "FAIL"


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

    def run_python_quality_gates(
        self, run: RunItem, project_root: str | Path
    ) -> PythonQualityReceipt:
        """Run pytest, Ruff, and Mypy in the Run-governed project root.

        The receipt never trusts a caller-supplied status.  It instead binds the
        verified Run baseline, the staged/unstaged evidence, and the three real
        child-process results into one deterministic digest.  Any evidence drift
        during a gate, failed process, or launch error is a failing receipt.
        """

        candidate, _ = self._verified_candidate(run)
        root = Path(project_root).resolve()
        try:
            root.relative_to(candidate)
        except ValueError as error:
            raise EvidenceCollectionError("质量门 project_root 超出 Run candidate") from error
        if not root.is_dir():
            raise EvidenceCollectionError("质量门 project_root 不存在或不是目录")

        before = self.collect(run)
        targets = self._quality_targets(run, candidate, root)
        gates = tuple(
            self._run_quality_gate(name, command, root, failure)
            for name, command, failure in self._python_quality_commands(targets)
        )

        evidence_current = False
        evidence_error: str | None = None
        try:
            after = self.collect(run)
            evidence_current = hmac.compare_digest(before.content_hash, after.content_hash)
            if not evidence_current:
                evidence_error = "质量门执行期间 Run evidence 已变化"
        except EvidenceCollectionError as error:
            evidence_error = f"质量门后 Run evidence 无法复核: {error}"

        return PythonQualityReceipt(
            run_id=run.run_id,
            baseline_git_head=run.git_head,
            candidate_path=str(candidate),
            project_root=str(root),
            evidence_hash=before.content_hash,
            gates=gates,
            evidence_current=evidence_current,
            evidence_error=evidence_error,
            content_hash=_sha256_payload(
                {
                    "run_id": run.run_id,
                    "baseline_git_head": run.git_head,
                    "candidate_path": str(candidate),
                    "project_root": str(root),
                    "evidence_hash": before.content_hash,
                    "gates": gates,
                    "evidence_current": evidence_current,
                    "evidence_error": evidence_error,
                }
            ),
        )

    def quality_receipt_is_current(
        self, run: RunItem, project_root: str | Path, receipt: PythonQualityReceipt
    ) -> bool:
        """Return whether a receipt still describes the current Run evidence.

        This intentionally does not rerun quality gates: it only determines
        whether a previously captured receipt has become invalid because source
        or Git evidence changed.
        """

        candidate, _ = self._verified_candidate(run)
        root = Path(project_root).resolve()
        if (
            receipt.run_id != run.run_id
            or receipt.baseline_git_head != run.git_head
            or receipt.candidate_path != str(candidate)
            or receipt.project_root != str(root)
            or receipt.status != "PASS"
        ):
            return False
        try:
            current = self.collect(run)
        except EvidenceCollectionError:
            return False
        return hmac.compare_digest(receipt.evidence_hash, current.content_hash)

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

    @staticmethod
    def _quality_targets(run: RunItem, candidate: Path, project_root: Path) -> _QualityTargets:
        """Derive only owned Python files, never a project-wide quality scope."""

        test_paths: list[str] = []
        python_paths: list[str] = []
        production_paths: list[str] = []
        for raw_path in run.owned_paths:
            normalized = PurePosixPath(str(raw_path).replace("\\", "/"))
            absolute = candidate.joinpath(*normalized.parts).resolve()
            try:
                relative = absolute.relative_to(project_root)
            except ValueError:
                continue
            if absolute.suffix != ".py" or not absolute.is_file():
                continue
            rendered = relative.as_posix()
            python_paths.append(rendered)
            if absolute.name.startswith("test_"):
                test_paths.append(rendered)
            elif "tests" not in relative.parts:
                production_paths.append(rendered)
        return _QualityTargets(
            tests=tuple(sorted(set(test_paths))),
            python=tuple(sorted(set(python_paths))),
            production=tuple(sorted(set(production_paths))),
        )

    @staticmethod
    def _python_quality_commands(
        targets: _QualityTargets,
    ) -> tuple[tuple[str, tuple[str, ...], str | None], ...]:
        """Return fixed commands limited to Run-owned targets or a failure receipt."""

        pytest = (sys.executable, "-m", "pytest", "-o", "addopts=", "-p", "no:cacheprovider")
        ruff = (sys.executable, "-m", "ruff", "check", "--no-cache")
        mypy = (sys.executable, "-m", "mypy", "--no-incremental")
        return (
            (
                "pytest",
                pytest + targets.tests,
                None if targets.tests else "缺少已批准的 test_*.py 质量门目标",
            ),
            (
                "ruff",
                ruff + targets.python,
                None if targets.python else "缺少已批准的 .py 质量门目标",
            ),
            (
                "mypy",
                mypy + targets.production,
                None if targets.production else "缺少已批准的生产 .py 质量门目标",
            ),
        )

    @staticmethod
    def _run_quality_gate(
        name: str, command: tuple[str, ...], project_root: Path, target_error: str | None
    ) -> PythonQualityGate:
        if target_error is not None:
            return PythonQualityGate(
                name=name,
                command=command,
                cwd=str(project_root),
                exit_code=None,
                output_digest=hashlib.sha256(target_error.encode("utf-8")).hexdigest(),
                output_summary=target_error,
            )
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        try:
            result = subprocess.run(
                command,
                cwd=str(project_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                env=environment,
            )
            output = f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            exit_code: int | None = result.returncode
        except OSError as error:
            output = f"launch error: {error}"
            exit_code = None
        return PythonQualityGate(
            name=name,
            command=command,
            cwd=str(project_root),
            exit_code=exit_code,
            output_digest=hashlib.sha256(output.encode("utf-8")).hexdigest(),
            output_summary=_safe_output_summary(output),
        )


@dataclass(frozen=True)
class _QualityTargets:
    """Exact Run-owned Python target lists for the three quality tools."""

    tests: tuple[str, ...]
    python: tuple[str, ...]
    production: tuple[str, ...]


def _sha256_payload(payload: object) -> str:
    """Hash a stable JSON rendering without allowing platform-dependent ordering."""

    canonical = json.dumps(
        payload,
        default=lambda value: value.__dict__,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _safe_output_summary(output: str) -> str:
    """Keep a bounded, normalized diagnostic while the digest proves full output."""

    normalized = output.replace("\r\n", "\n").strip()
    if len(normalized) <= 2_000:
        return normalized
    return f"{normalized[:2_000]}\n...[truncated; full output sha256 recorded]"


__all__ = [
    "EvidenceCollection",
    "EvidenceCollectionError",
    "EvidenceCollectionService",
    "PythonQualityGate",
    "PythonQualityReceipt",
]
