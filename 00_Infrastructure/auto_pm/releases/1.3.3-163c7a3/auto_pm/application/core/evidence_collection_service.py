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
import math
import os
import re
import subprocess
import sys
import tarfile
import threading
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from auto_pm.contracts.continuity import RunItem
from auto_pm.domain.plc.baseline_compare import diff_failures, lint_failure_keys
from auto_pm.domain.plc.language_service import LanguageService
from auto_pm.infrastructure.control_root_guard import (
    ControlRootGuardError,
    authority_path_parts,
    clean_git_environment,
    governed_worktree_snapshot,
)
from auto_pm.infrastructure.git_timeout import run_git_bounded_text

_C03_CHECKPOINT_PYTEST_EXPRESSION = "append_verified_checkpoint"
_C03_CHECKPOINT_PYTEST_TARGET = "tests/core/test_continuity_execution_service.py"
_PLC_CHECKPOINT_SCHEMA = "checkpoint-evidence.v3"
_PLC_CHECK_COMMAND = "auto_pm.plc.checker.PlcChecker.check_project"
_PLC_LINT_COMMAND = "auto_pm.plc.scl_linter.SclLinter.lint_file"
_QUALITY_GATE_TIMEOUT_ENV = "AUTO_PM_QUALITY_GATE_TIMEOUT_SECONDS"
_QUALITY_GATE_TIMEOUT_DEFAULT_SECONDS = 1800.0
_GIT_EVIDENCE_TIMEOUT_SECONDS = 600.0
_PLC_MIXED_DOMAIN_ERROR = "Run 同时拥有 PLC 工程路径与 Python 路径；一个 Run 只验证一个领域"


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
    untracked_content_hashes: tuple[tuple[str, str], ...]
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
                "untracked_content_hashes": self.untracked_content_hashes,
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
    project_roots: tuple[str, ...] = ()
    owned_python_paths: tuple[str, ...] = ()

    @property
    def status(self) -> str:
        """Return PASS only for three successful commands and unchanged evidence."""

        if self.evidence_current and all(gate.passed for gate in self.gates):
            return "PASS"
        return "FAIL"


@dataclass(frozen=True)
class PlcQualityReceipt:
    """Content-bound result of the real PLC static checker and SCL linter."""

    run_id: str
    baseline_git_head: str
    candidate_path: str
    project_root: str
    evidence_hash: str
    gates: tuple[PythonQualityGate, ...]
    evidence_current: bool
    evidence_error: str | None
    content_hash: str
    project_roots: tuple[str, ...]
    owned_plc_paths: tuple[str, ...]
    input_digests: tuple[tuple[str, str], ...]
    checker_digest: str

    @property
    def status(self) -> str:
        """Return PASS only for successful static gates and unchanged evidence."""

        if self.evidence_current and self.gates and all(gate.passed for gate in self.gates):
            return "PASS"
        return "FAIL"


@dataclass(frozen=True)
class _OwnedPath:
    """One normalized Run-owned path and the PLC project root that contains it."""

    relative: PurePosixPath
    absolute: Path
    plc_root: Path | None


@dataclass(frozen=True)
class _PlcProject:
    """One PLC project root with the exact owned SCL files inside it."""

    root: Path
    scl_paths: tuple[str, ...]


@dataclass(frozen=True)
class _PlcBaseline:
    """One PLC project as it was at the Run baseline commit (exported read-only from Git).

    ``workspace`` is the temporary export root; ``project`` is the project inside it, or
    ``None`` when the baseline cannot be used (``note`` says why), in which case every
    current failure counts as new.
    """

    git_head: str
    workspace: Path | None
    project: Path | None
    note: str = ""
    anchor_note: str = ""


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
        untracked_content_hashes = self._untracked_content_hashes(
            candidate, before.untracked_paths
        )

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
        after_untracked_content_hashes = self._untracked_content_hashes(
            candidate, after.untracked_paths
        )
        final_candidate, final_head = self._verified_candidate(run)
        if (
            candidate != final_candidate
            or head != final_head
            or before != after
            or untracked_content_hashes != after_untracked_content_hashes
        ):
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
            or untracked_content_hashes
            != self._untracked_content_hashes(candidate, before.untracked_paths)
        ):
            raise EvidenceCollectionError("Run worktree diff 在采集期间发生漂移")

        return EvidenceCollection(
            run_id=run.run_id,
            git_head=run.git_head,
            worktree_path=str(candidate),
            staged_paths=before.staged_paths,
            unstaged_paths=before.unstaged_paths,
            untracked_paths=before.untracked_paths,
            untracked_content_hashes=untracked_content_hashes,
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

        return self._run_python_quality_gates(run, project_root, c03_profile=False)

    def run_c03_checkpoint_quality_gates(
        self, run: RunItem, project_root: str | Path
    ) -> PythonQualityReceipt:
        """Run the fixed C03 checkpoint profile without widening generic C02 gates.

        The profile's test file and selector are service constants.  They are
        not inputs to the public append API, so a caller cannot silently widen
        this bounded checkpoint proof into the historical continuity suite.
        """

        return self._run_python_quality_gates(run, project_root, c03_profile=True)

    def run_generic_checkpoint_quality_gates(
        self, run: RunItem, project_root: str | Path
    ) -> PythonQualityReceipt:
        """Run all three real tools in every owned Python file's project root."""

        candidate, anchor = self._quality_context(run, project_root)
        projects, owned = self._generic_project_targets(run, candidate, anchor)
        before = self.collect(run)
        gates = tuple(
            self._run_quality_gate(name, command, root, error)
            for root, targets in projects
            for name, command, error in self._generic_quality_commands(targets)
        )
        evidence_current = False
        evidence_error: str | None = None
        try:
            evidence_current = hmac.compare_digest(before.content_hash, self.collect(run).content_hash)
            if not evidence_current:
                evidence_error = "质量门执行期间 Run evidence 已变化"
        except EvidenceCollectionError as error:
            evidence_error = f"质量门后 Run evidence 无法复核: {error}"
        roots = tuple(str(root) for root, _ in projects)
        return PythonQualityReceipt(
            run_id=run.run_id,
            baseline_git_head=run.git_head,
            candidate_path=str(candidate),
            project_root=str(anchor),
            evidence_hash=before.content_hash,
            gates=gates,
            evidence_current=evidence_current,
            evidence_error=evidence_error,
            content_hash=_quality_receipt_hash(
                run_id=run.run_id,
                baseline_git_head=run.git_head,
                candidate_path=str(candidate),
                project_root=str(anchor),
                evidence_hash=before.content_hash,
                gates=gates,
                evidence_current=evidence_current,
                evidence_error=evidence_error,
                project_roots=roots,
                owned_python_paths=owned,
            ),
            project_roots=roots,
            owned_python_paths=owned,
        )

    def validate_generic_checkpoint_project_root(
        self, run: RunItem, project_root: str | Path
    ) -> Path:
        candidate, anchor = self._quality_context(run, project_root)
        self._generic_project_targets(run, candidate, anchor)
        return anchor

    @staticmethod
    def _generic_project_targets(
        run: RunItem, candidate: Path, anchor: Path
    ) -> tuple[tuple[tuple[Path, _QualityTargets], ...], tuple[str, ...]]:
        """Assign every exact owned Python file to its nearest project config."""

        groups: dict[Path, list[str]] = {}
        owned: list[str] = []
        normalized_paths = EvidenceCollectionService._normalize_owned_paths(run.owned_paths)
        for raw_path, _ in zip(run.owned_paths, normalized_paths, strict=True):
            relative = PurePosixPath(str(raw_path).replace("\\", "/"))
            if relative.suffix != ".py":
                continue
            absolute = candidate.joinpath(*relative.parts).resolve()
            if not absolute.is_file():
                raise EvidenceCollectionError(f"Run owned Python path 不存在: {relative}")
            try:
                absolute.relative_to(anchor)
            except ValueError as error:
                raise EvidenceCollectionError(
                    f"质量门 project_root 未覆盖 Run owned Python path: {relative}"
                ) from error
            root = absolute.parent
            while root != anchor and not (root / "pyproject.toml").is_file():
                root = root.parent
            if not (root / "pyproject.toml").is_file():
                raise EvidenceCollectionError(f"Run owned Python path 缺少 pyproject.toml: {relative}")
            groups.setdefault(root, []).append(absolute.relative_to(root).as_posix())
            owned.append(relative.as_posix())
        if not owned:
            raise EvidenceCollectionError("Run 缺少已批准的 owned Python path")
        projects: list[tuple[Path, _QualityTargets]] = []
        for root, paths in sorted(groups.items(), key=lambda item: str(item[0])):
            python = tuple(sorted(set(paths)))
            tests = tuple(path for path in python if Path(path).name.startswith("test_"))
            production = tuple(
                path for path in python if not Path(path).name.startswith("test_")
                and "tests" not in PurePosixPath(path).parts
            )
            projects.append((root, _QualityTargets(tests, python, production)))
        return tuple(projects), tuple(sorted(set(owned)))

    def validate_c03_checkpoint_project_root(
        self, run: RunItem, project_root: str | Path
    ) -> Path:
        """Require the exact C03 project root before replaying stored evidence."""

        candidate, root = self._quality_context(run, project_root)
        self._validate_c03_project_root_coverage(run, candidate, root)
        targets = self._quality_targets(run, candidate, root)
        self._validate_c03_checkpoint_target(targets)
        return root

    def _run_python_quality_gates(
        self,
        run: RunItem,
        project_root: str | Path,
        *,
        c03_profile: bool,
    ) -> PythonQualityReceipt:
        """Run the shared C02 implementation, optionally with the C03 profile."""

        candidate, root = self._quality_context(run, project_root)
        if c03_profile:
            self._validate_c03_project_root_coverage(run, candidate, root)

        before = self.collect(run)
        targets = self._quality_targets(run, candidate, root)
        if c03_profile:
            self._validate_c03_checkpoint_target(targets)
            commands = self._c03_checkpoint_quality_commands(targets)
        else:
            commands = self._python_quality_commands(targets)
        gates = tuple(
            self._run_quality_gate(name, command, root, failure)
            for name, command, failure in commands
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
            content_hash=_quality_receipt_hash(
                run_id=run.run_id,
                baseline_git_head=run.git_head,
                candidate_path=str(candidate),
                project_root=str(root),
                evidence_hash=before.content_hash,
                gates=gates,
                evidence_current=evidence_current,
                evidence_error=evidence_error,
            ),
        )

    def _quality_context(self, run: RunItem, project_root: str | Path) -> tuple[Path, Path]:
        """Resolve one existing project root under the governed candidate."""

        candidate, _ = self._verified_candidate(run)
        root = Path(project_root).resolve()
        try:
            root.relative_to(candidate)
        except ValueError as error:
            raise EvidenceCollectionError("质量门 project_root 超出 Run candidate") from error
        if not root.is_dir():
            raise EvidenceCollectionError("质量门 project_root 不存在或不是目录")
        return candidate, root

    def _validate_c03_project_root_coverage(
        self,
        run: RunItem,
        candidate: Path,
        project_root: Path,
    ) -> None:
        """Require C03's actual project root to cover every Run-owned path."""

        if not (project_root / "pyproject.toml").is_file():
            raise EvidenceCollectionError(
                "C03 自动 Checkpoint project_root 必须包含 pyproject.toml"
            )
        for normalized in self._normalize_owned_paths(run.owned_paths):
            absolute = candidate.joinpath(*normalized).resolve()
            try:
                absolute.relative_to(project_root)
            except ValueError as error:
                rendered = PurePosixPath(*normalized).as_posix()
                raise EvidenceCollectionError(
                    "C03 project_root 未覆盖 Run owned path: " f"{rendered}"
                ) from error

    @staticmethod
    def _validate_c03_checkpoint_target(targets: _QualityTargets) -> None:
        """Require C03's one bounded pytest file before launching child tools."""

        if _C03_CHECKPOINT_PYTEST_TARGET not in targets.tests:
            raise EvidenceCollectionError(
                "C03 自动 Checkpoint 缺少固定 pytest target: "
                f"{_C03_CHECKPOINT_PYTEST_TARGET}"
            )

    @staticmethod
    def c03_checkpoint_receipt_matches_profile(receipt: PythonQualityReceipt) -> bool:
        """Require the receipt hash and fixed C03 pytest command before a write."""

        expected_hash = _quality_receipt_hash(
            run_id=receipt.run_id,
            baseline_git_head=receipt.baseline_git_head,
            candidate_path=receipt.candidate_path,
            project_root=receipt.project_root,
            evidence_hash=receipt.evidence_hash,
            gates=receipt.gates,
            evidence_current=receipt.evidence_current,
            evidence_error=receipt.evidence_error,
        )
        return (
            tuple(gate.name for gate in receipt.gates) == ("pytest", "ruff", "mypy")
            and receipt.gates[0].command == _c03_checkpoint_pytest_command()
            and hmac.compare_digest(receipt.content_hash, expected_hash)
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
        if receipt.project_roots:
            try:
                projects, owned = self._generic_project_targets(run, candidate, root)
            except EvidenceCollectionError:
                return False
            if (
                receipt.project_roots != tuple(str(project) for project, _ in projects)
                or receipt.owned_python_paths != owned
                or not self.generic_checkpoint_receipt_matches_profile(receipt, projects)
            ):
                return False
        try:
            current = self.collect(run)
        except EvidenceCollectionError:
            return False
        return hmac.compare_digest(receipt.evidence_hash, current.content_hash)

    @staticmethod
    def generic_checkpoint_receipt_matches_profile(
        receipt: PythonQualityReceipt,
        projects: tuple[tuple[Path, _QualityTargets], ...],
    ) -> bool:
        """Require exact per-project commands and complete owned-path binding."""

        expected = tuple(
            (name, command, str(root))
            for root, targets in projects
            for name, command, _ in EvidenceCollectionService._generic_quality_commands(targets)
        )
        return (
            tuple((gate.name, gate.command, gate.cwd) for gate in receipt.gates) == expected
            and receipt.project_roots == tuple(str(root) for root, _ in projects)
            and hmac.compare_digest(
                receipt.content_hash,
                _quality_receipt_hash(
                    run_id=receipt.run_id,
                    baseline_git_head=receipt.baseline_git_head,
                    candidate_path=receipt.candidate_path,
                    project_root=receipt.project_root,
                    evidence_hash=receipt.evidence_hash,
                    gates=receipt.gates,
                    evidence_current=receipt.evidence_current,
                    evidence_error=receipt.evidence_error,
                    project_roots=receipt.project_roots,
                    owned_python_paths=receipt.owned_python_paths,
                ),
            )
        )

    @staticmethod
    def build_checkpoint_evidence(
        collection: EvidenceCollection, receipt: PythonQualityReceipt | PlcQualityReceipt
    ) -> str:
        """Build one immutable, canonical evidence envelope for an auto checkpoint.

        The caller supplies only trusted collector return values, never arbitrary
        user result data.  The envelope retains the full Git evidence and the
        exact process receipt while its hashes make tampering and stale replay
        detectable without introducing a new mutable persistence schema.
        """

        if isinstance(receipt, PlcQualityReceipt):
            return EvidenceCollectionService._build_plc_checkpoint_evidence(collection, receipt)
        expected_receipt_hash = _quality_receipt_hash(
            run_id=receipt.run_id,
            baseline_git_head=receipt.baseline_git_head,
            candidate_path=receipt.candidate_path,
            project_root=receipt.project_root,
            evidence_hash=receipt.evidence_hash,
            gates=receipt.gates,
            evidence_current=receipt.evidence_current,
            evidence_error=receipt.evidence_error,
            project_roots=receipt.project_roots,
            owned_python_paths=receipt.owned_python_paths,
        )
        if (
            receipt.status != "PASS"
            or not receipt.evidence_current
            or receipt.run_id != collection.run_id
            or receipt.baseline_git_head != collection.git_head
            or receipt.candidate_path != collection.worktree_path
            or not hmac.compare_digest(receipt.evidence_hash, collection.content_hash)
            or not hmac.compare_digest(receipt.content_hash, expected_receipt_hash)
        ):
            raise EvidenceCollectionError("自动 Checkpoint 的质量收据与当前 evidence 不一致")
        unsigned = {
            "schema_version": (
                "checkpoint-evidence.v2" if receipt.project_roots else "checkpoint-evidence.v1"
            ),
            "collection": _collection_payload(collection),
            "collection_hash": collection.content_hash,
            "quality_receipt": {
                **_quality_receipt_payload(receipt),
                "status": receipt.status,
            },
            "receipt_hash": receipt.content_hash,
        }
        envelope = {
            **unsigned,
            "envelope_hash": _sha256_payload(unsigned),
        }
        return _canonical_json_payload(envelope)

    @staticmethod
    def checkpoint_evidence_is_current(
        serialized: str,
        collection: EvidenceCollection,
        run: RunItem,
        project_root: str | Path,
    ) -> bool:
        """Verify a stored auto-checkpoint envelope against current Git evidence.

        This is intentionally stricter than checking the stored Run id.  A
        checkpoint can be replayed only if its canonical envelope is intact, its
        historical receipt passed, and all receipt/evidence identities still
        match the newly collected snapshot.
        """

        try:
            envelope = json.loads(serialized)
        except (TypeError, json.JSONDecodeError):
            return False
        if isinstance(envelope, dict) and envelope.get("schema_version") == "checkpoint-evidence.v2":
            return EvidenceCollectionService._generic_checkpoint_evidence_is_current(
                serialized, envelope, collection, run, project_root
            )
        if isinstance(envelope, dict) and envelope.get("schema_version") == _PLC_CHECKPOINT_SCHEMA:
            return EvidenceCollectionService._plc_checkpoint_evidence_is_current(
                serialized, envelope, collection, run, project_root
            )
        expected_keys = {
            "schema_version",
            "collection",
            "collection_hash",
            "quality_receipt",
            "receipt_hash",
            "envelope_hash",
        }
        if not isinstance(envelope, dict) or set(envelope) != expected_keys:
            return False
        envelope_hash = envelope.get("envelope_hash")
        unsigned = {key: value for key, value in envelope.items() if key != "envelope_hash"}
        if (
            envelope.get("schema_version") != "checkpoint-evidence.v1"
            or not isinstance(envelope_hash, str)
            or not hmac.compare_digest(envelope_hash, _sha256_payload(unsigned))
            # Canonical JSON is public structural data, not a secret.  Plain
            # equality deliberately supports non-ASCII owned paths; CPython's
            # compare_digest rejects Unicode strings outside ASCII.
            or serialized != _canonical_json_payload(envelope)
            or envelope.get("collection") != _collection_payload(collection)
            or not isinstance(envelope.get("collection_hash"), str)
            or not hmac.compare_digest(envelope["collection_hash"], collection.content_hash)
        ):
            return False
        receipt = envelope.get("quality_receipt")
        if not isinstance(receipt, dict):
            return False
        receipt_keys = {
            "run_id",
            "baseline_git_head",
            "candidate_path",
            "project_root",
            "evidence_hash",
            "gates",
            "evidence_current",
            "evidence_error",
            "status",
        }
        if set(receipt) != receipt_keys:
            return False
        receipt_payload = {key: value for key, value in receipt.items() if key != "status"}
        receipt_hash = envelope.get("receipt_hash")
        expected_root = str(Path(project_root).resolve())
        if (
            not isinstance(receipt_hash, str)
            or not hmac.compare_digest(receipt_hash, _sha256_payload(receipt_payload))
            or receipt.get("status") != "PASS"
            or receipt.get("run_id") != run.run_id
            or receipt.get("baseline_git_head") != run.git_head
            or receipt.get("candidate_path") != collection.worktree_path
            or receipt.get("project_root") != expected_root
            or receipt.get("evidence_hash") != collection.content_hash
            or receipt.get("evidence_current") is not True
            or receipt.get("evidence_error") is not None
        ):
            return False
        gates = receipt.get("gates")
        if not isinstance(gates, list) or tuple(gate.get("name") for gate in gates if isinstance(gate, dict)) != (
            "pytest",
            "ruff",
            "mypy",
        ):
            return False
        if (
            not isinstance(gates[0], dict)
            or gates[0].get("command") != list(_c03_checkpoint_pytest_command())
        ):
            return False
        expected_gate_keys = {
            "name",
            "command",
            "cwd",
            "exit_code",
            "output_digest",
            "output_summary",
        }
        return all(
            isinstance(gate, dict)
            and set(gate) == expected_gate_keys
            and isinstance(gate["command"], list)
            and all(isinstance(item, str) for item in gate["command"])
            and isinstance(gate["cwd"], str)
            and gate["exit_code"] == 0
            and isinstance(gate["output_digest"], str)
            and bool(gate["output_digest"])
            and isinstance(gate["output_summary"], str)
            for gate in gates
        )

    @staticmethod
    def _generic_checkpoint_evidence_is_current(
        serialized: str,
        envelope: dict[str, object],
        collection: EvidenceCollection,
        run: RunItem,
        project_root: str | Path,
    ) -> bool:
        """Recompute generic coverage and commands before accepting replay."""

        if set(envelope) != {
            "schema_version", "collection", "collection_hash", "quality_receipt",
            "receipt_hash", "envelope_hash",
        }:
            return False
        unsigned = {key: value for key, value in envelope.items() if key != "envelope_hash"}
        if (
            serialized != _canonical_json_payload(envelope)
            or not isinstance(envelope["envelope_hash"], str)
            or envelope["envelope_hash"] != _sha256_payload(unsigned)
            or envelope["collection"] != _collection_payload(collection)
            or envelope["collection_hash"] != collection.content_hash
        ):
            return False
        payload = envelope["quality_receipt"]
        if not isinstance(payload, dict) or set(payload) != {
            "run_id", "baseline_git_head", "candidate_path", "project_root",
            "evidence_hash", "gates", "evidence_current", "evidence_error",
            "project_roots", "owned_python_paths", "status",
        }:
            return False
        candidate = Path(collection.worktree_path).resolve()
        anchor = Path(project_root).resolve()
        try:
            anchor.relative_to(candidate)
            projects, owned = EvidenceCollectionService._generic_project_targets(
                run, candidate, anchor
            )
        except (EvidenceCollectionError, ValueError):
            return False
        roots = tuple(str(root) for root, _ in projects)
        if (
            payload["run_id"] != run.run_id
            or payload["baseline_git_head"] != run.git_head
            or payload["candidate_path"] != collection.worktree_path
            or payload["project_root"] != str(anchor)
            or payload["evidence_hash"] != collection.content_hash
            or payload["project_roots"] != list(roots)
            or payload["owned_python_paths"] != list(owned)
            or payload["evidence_current"] is not True
            or payload["evidence_error"] is not None
            or payload["status"] != "PASS"
        ):
            return False
        receipt_payload = {key: value for key, value in payload.items() if key != "status"}
        if envelope["receipt_hash"] != _sha256_payload(receipt_payload):
            return False
        gates = payload["gates"]
        expected = tuple(
            (name, list(command), str(root))
            for root, targets in projects
            for name, command, _ in EvidenceCollectionService._generic_quality_commands(targets)
        )
        return (
            isinstance(gates, list)
            and len(gates) == len(expected)
            and all(
                isinstance(gate, dict)
                and set(gate) == {
                    "name", "command", "cwd", "exit_code",
                    "output_digest", "output_summary",
                }
                and (gate["name"], gate["command"], gate["cwd"]) == expected[index]
                and type(gate["exit_code"]) is int
                and gate["exit_code"] == 0
                and isinstance(gate["output_digest"], str)
                and bool(gate["output_digest"])
                and isinstance(gate["output_summary"], str)
                for index, gate in enumerate(gates)
            )
        )

    def _verified_candidate(self, run: RunItem) -> tuple[Path, str]:
        try:
            candidate, observed_head, _ = governed_worktree_snapshot(
                self._workspace_root,
                run.worktree_path,
                allow_external_linked=True,
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
    def _untracked_content_hashes(
        candidate: Path, paths: tuple[str, ...]
    ) -> tuple[tuple[str, str], ...]:
        """Hash every owned untracked file without following external links.

        Git diffs do not contain untracked file bytes.  Their paths alone are
        insufficient for a content-bound receipt because a file can change in
        place while retaining the same path.  The caller compares this complete
        tuple before and after collection to reject concurrent mutation.
        """

        root = candidate.resolve()
        digests: list[tuple[str, str]] = []
        for path in paths:
            candidate_path = candidate.joinpath(*PurePosixPath(path).parts)
            try:
                resolved = candidate_path.resolve(strict=True)
                resolved.relative_to(root)
            except (OSError, RuntimeError, ValueError) as error:
                raise EvidenceCollectionError(
                    f"Run untracked path 无法安全读取: {path}"
                ) from error
            if candidate_path.is_symlink() or not resolved.is_file():
                raise EvidenceCollectionError(
                    f"Run untracked path 必须是 worktree 内普通文件: {path}"
                )
            digest = hashlib.sha256()
            try:
                with resolved.open("rb") as stream:
                    while chunk := stream.read(64 * 1024):
                        digest.update(chunk)
            except OSError as error:
                raise EvidenceCollectionError(
                    f"Run untracked path 无法读取: {path}"
                ) from error
            digests.append((path, digest.hexdigest()))
        return tuple(digests)

    @staticmethod
    def _git_output(candidate: Path, *arguments: str) -> str:
        try:
            result = run_git_bounded_text(
                ["git", "-C", str(candidate), *arguments],
                default_timeout=_GIT_EVIDENCE_TIMEOUT_SECONDS,
                error_cls=EvidenceCollectionError,
                where=candidate,
                capture_output=True,
                check=False,
                env=clean_git_environment(),
            )
        except OSError as error:
            raise EvidenceCollectionError(f"Run worktree Git evidence 无法启动 git: {error}") from error
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
            if absolute.suffix != ".py" or not absolute.is_file():
                continue
            try:
                relative = absolute.relative_to(project_root)
            except ValueError as error:
                raise EvidenceCollectionError(
                    "质量门 project_root 未覆盖 Run owned Python path: "
                    f"{normalized.as_posix()}"
                ) from error
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
    def _generic_quality_commands(
        targets: _QualityTargets,
    ) -> tuple[tuple[str, tuple[str, ...], str | None], ...]:
        """Check exact owned targets with normal per-project type resolution."""

        commands = EvidenceCollectionService._python_quality_commands(targets)
        mypy = (sys.executable, "-m", "mypy", "--no-incremental")
        if targets.python:
            return (*commands[:2], ("mypy", mypy + targets.python, None))
        return commands

    @staticmethod
    def _c03_checkpoint_quality_commands(
        targets: _QualityTargets,
    ) -> tuple[tuple[str, tuple[str, ...], str | None], ...]:
        """Return C03's fixed bounded pytest profile plus the normal C02 checks."""

        ruff = (sys.executable, "-m", "ruff", "check", "--no-cache")
        mypy = (sys.executable, "-m", "mypy", "--no-incremental")
        return (
            ("pytest", _c03_checkpoint_pytest_command(), None),
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
        environment["PYTEST_ADDOPTS"] = ""
        try:
            with TemporaryDirectory(prefix="auto-pm-quality-") as temporary:
                environment["MYPY_CACHE_DIR"] = temporary
                environment["TMP"] = temporary
                environment["TEMP"] = temporary
                result = subprocess.run(
                    command,
                    cwd=str(project_root),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                    env=environment,
                    timeout=_quality_gate_timeout_seconds(),
                )
            output = f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            exit_code: int | None = result.returncode
        except subprocess.TimeoutExpired as error:
            output = f"timeout: 质量门超过 {error.timeout:g} 秒没有结束，这次检查不算数"
            exit_code = None
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


    # -- PLC static quality profile (V01) ---------------------------------

    def checkpoint_profile_for_run(self, run: RunItem) -> str:
        """Return ``"plc"`` for Runs inside a PLC project, else ``"generic"``.

        A Run is verified in exactly one domain: owning both PLC project paths
        and Python paths outside any PLC project is refused instead of letting
        one domain's gate silently ignore the other's files.
        """

        candidate, _ = self._verified_candidate(run)
        entries = self._owned_path_entries(run, candidate)
        has_plc = any(entry.plc_root is not None for entry in entries)
        if has_plc and any(
            entry.plc_root is None and entry.relative.suffix == ".py" for entry in entries
        ):
            raise EvidenceCollectionError(_PLC_MIXED_DOMAIN_ERROR)
        return "plc" if has_plc else "generic"

    def validate_plc_checkpoint_project_root(
        self, run: RunItem, project_root: str | Path
    ) -> Path:
        """Require every owned PLC path to sit under the supplied project root."""

        candidate, anchor = self._quality_context(run, project_root)
        self._plc_project_targets(run, candidate, anchor)
        return anchor

    def run_plc_checkpoint_quality_gates(
        self, run: RunItem, project_root: str | Path
    ) -> PlcQualityReceipt:
        """Run the existing PLC checker and SCL linter on the Run candidate.

        The checker is called as a library on the governed worktree, never on
        the control root, so ``.plc.json``, SCL, INT/VAR documents and the spec
        registry it reads come from the same Git baseline as the Run evidence.
        """

        candidate, anchor = self._quality_context(run, project_root)
        projects, owned = self._plc_project_targets(run, candidate, anchor)
        before = self.collect(run)
        checker_digest = self._plc_checker_digest()
        inputs_before = self._plc_input_digests(candidate, projects)
        # Judge against the Run baseline: failures that already existed when the Run
        # started are listed but do not block; only new ones (or more of them) do.
        with TemporaryDirectory(prefix="pmb-") as temporary:
            baselines = {
                project.root: self._plc_baseline(candidate, run.git_head, project, Path(temporary) / str(index))
                for index, project in enumerate(projects)
            }
            gates = tuple(
                self._run_plc_gate(candidate, name, command, root, project, baselines[project.root])
                for (name, command, root), project in self._plc_gate_plan(candidate, projects)
            )
        evidence_current = False
        evidence_error: str | None = None
        try:
            after = self.collect(run)
            inputs_after = self._plc_input_digests(candidate, projects)
            evidence_current = hmac.compare_digest(
                before.content_hash, after.content_hash
            ) and inputs_before == inputs_after
            if not evidence_current:
                evidence_error = "质量门执行期间 Run evidence 或 PLC 输入已变化"
        except EvidenceCollectionError as error:
            evidence_error = f"质量门后 Run evidence 无法复核: {error}"
        roots = tuple(str(project.root) for project in projects)
        return PlcQualityReceipt(
            run_id=run.run_id,
            baseline_git_head=run.git_head,
            candidate_path=str(candidate),
            project_root=str(anchor),
            evidence_hash=before.content_hash,
            gates=gates,
            evidence_current=evidence_current,
            evidence_error=evidence_error,
            content_hash=_plc_receipt_hash(
                run_id=run.run_id,
                baseline_git_head=run.git_head,
                candidate_path=str(candidate),
                project_root=str(anchor),
                evidence_hash=before.content_hash,
                gates=gates,
                evidence_current=evidence_current,
                evidence_error=evidence_error,
                project_roots=roots,
                owned_plc_paths=owned,
                input_digests=inputs_before,
                checker_digest=checker_digest,
            ),
            project_roots=roots,
            owned_plc_paths=owned,
            input_digests=inputs_before,
            checker_digest=checker_digest,
        )

    def plc_quality_receipt_is_current(
        self, run: RunItem, project_root: str | Path, receipt: PlcQualityReceipt
    ) -> bool:
        """Return whether a PLC receipt still describes the current Run and inputs."""

        candidate, _ = self._verified_candidate(run)
        anchor = Path(project_root).resolve()
        if (
            receipt.run_id != run.run_id
            or receipt.baseline_git_head != run.git_head
            or receipt.candidate_path != str(candidate)
            or receipt.project_root != str(anchor)
            or receipt.status != "PASS"
        ):
            return False
        try:
            projects, owned = self._plc_project_targets(run, candidate, anchor)
            if not EvidenceCollectionService._plc_receipt_matches_profile(
                receipt, candidate, projects, owned
            ):
                return False
            current = self.collect(run)
        except EvidenceCollectionError:
            return False
        return hmac.compare_digest(receipt.evidence_hash, current.content_hash)

    @staticmethod
    def _plc_receipt_matches_profile(
        receipt: PlcQualityReceipt,
        candidate: Path,
        projects: tuple[_PlcProject, ...],
        owned: tuple[str, ...],
    ) -> bool:
        """Require recomputed gates, targets, inputs, checker bytes and receipt hash."""

        expected = tuple(
            (name, command, str(root))
            for (name, command, root), _ in EvidenceCollectionService._plc_gate_plan(
                candidate, projects
            )
        )
        return (
            tuple((gate.name, gate.command, gate.cwd) for gate in receipt.gates) == expected
            and receipt.project_roots == tuple(str(project.root) for project in projects)
            and receipt.owned_plc_paths == owned
            and receipt.input_digests
            == EvidenceCollectionService._plc_input_digests(candidate, projects)
            and receipt.checker_digest == EvidenceCollectionService._plc_checker_digest()
            and hmac.compare_digest(
                receipt.content_hash,
                _plc_receipt_hash(
                    run_id=receipt.run_id,
                    baseline_git_head=receipt.baseline_git_head,
                    candidate_path=receipt.candidate_path,
                    project_root=receipt.project_root,
                    evidence_hash=receipt.evidence_hash,
                    gates=receipt.gates,
                    evidence_current=receipt.evidence_current,
                    evidence_error=receipt.evidence_error,
                    project_roots=receipt.project_roots,
                    owned_plc_paths=receipt.owned_plc_paths,
                    input_digests=receipt.input_digests,
                    checker_digest=receipt.checker_digest,
                ),
            )
        )

    @staticmethod
    def _build_plc_checkpoint_evidence(
        collection: EvidenceCollection, receipt: PlcQualityReceipt
    ) -> str:
        """Build the ``checkpoint-evidence.v3`` envelope for a PLC Run."""

        expected_receipt_hash = _plc_receipt_hash(
            run_id=receipt.run_id,
            baseline_git_head=receipt.baseline_git_head,
            candidate_path=receipt.candidate_path,
            project_root=receipt.project_root,
            evidence_hash=receipt.evidence_hash,
            gates=receipt.gates,
            evidence_current=receipt.evidence_current,
            evidence_error=receipt.evidence_error,
            project_roots=receipt.project_roots,
            owned_plc_paths=receipt.owned_plc_paths,
            input_digests=receipt.input_digests,
            checker_digest=receipt.checker_digest,
        )
        if (
            receipt.status != "PASS"
            or not receipt.evidence_current
            or receipt.run_id != collection.run_id
            or receipt.baseline_git_head != collection.git_head
            or receipt.candidate_path != collection.worktree_path
            or not hmac.compare_digest(receipt.evidence_hash, collection.content_hash)
            or not hmac.compare_digest(receipt.content_hash, expected_receipt_hash)
        ):
            raise EvidenceCollectionError("自动 Checkpoint 的 PLC 质量收据与当前 evidence 不一致")
        unsigned = {
            "schema_version": _PLC_CHECKPOINT_SCHEMA,
            "collection": _collection_payload(collection),
            "collection_hash": collection.content_hash,
            "quality_receipt": {**_plc_receipt_payload(receipt), "status": receipt.status},
            "receipt_hash": receipt.content_hash,
        }
        return _canonical_json_payload({**unsigned, "envelope_hash": _sha256_payload(unsigned)})

    @staticmethod
    def _plc_checkpoint_evidence_is_current(
        serialized: str,
        envelope: dict[str, object],
        collection: EvidenceCollection,
        run: RunItem,
        project_root: str | Path,
    ) -> bool:
        """Recompute PLC targets, gates, inputs and checker bytes before replay."""

        if set(envelope) != {
            "schema_version", "collection", "collection_hash", "quality_receipt",
            "receipt_hash", "envelope_hash",
        }:
            return False
        unsigned = {key: value for key, value in envelope.items() if key != "envelope_hash"}
        if (
            serialized != _canonical_json_payload(envelope)
            or envelope["schema_version"] != _PLC_CHECKPOINT_SCHEMA
            or not isinstance(envelope["envelope_hash"], str)
            or envelope["envelope_hash"] != _sha256_payload(unsigned)
            or envelope["collection"] != _collection_payload(collection)
            or envelope["collection_hash"] != collection.content_hash
        ):
            return False
        payload = envelope["quality_receipt"]
        if not isinstance(payload, dict) or set(payload) != {
            "domain", "run_id", "baseline_git_head", "candidate_path", "project_root",
            "evidence_hash", "gates", "evidence_current", "evidence_error",
            "project_roots", "owned_plc_paths", "input_digests", "checker_digest", "status",
        }:
            return False
        candidate = Path(collection.worktree_path).resolve()
        anchor = Path(project_root).resolve()
        try:
            anchor.relative_to(candidate)
            projects, owned = EvidenceCollectionService._plc_project_targets(
                run, candidate, anchor
            )
            inputs = EvidenceCollectionService._plc_input_digests(candidate, projects)
            checker_digest = EvidenceCollectionService._plc_checker_digest()
        except (EvidenceCollectionError, ValueError):
            return False
        roots = tuple(str(project.root) for project in projects)
        if (
            payload["domain"] != "plc"
            or payload["run_id"] != run.run_id
            or payload["baseline_git_head"] != run.git_head
            or payload["candidate_path"] != collection.worktree_path
            or payload["project_root"] != str(anchor)
            or payload["evidence_hash"] != collection.content_hash
            or payload["project_roots"] != list(roots)
            or payload["owned_plc_paths"] != list(owned)
            or payload["input_digests"] != [
                {"project": project, "sha256": digest} for project, digest in inputs
            ]
            or payload["checker_digest"] != checker_digest
            or payload["evidence_current"] is not True
            or payload["evidence_error"] is not None
            or payload["status"] != "PASS"
        ):
            return False
        if envelope["receipt_hash"] != _sha256_payload(
            {key: value for key, value in payload.items() if key != "status"}
        ):
            return False
        gates = payload["gates"]
        expected = tuple(
            (name, list(command), str(root))
            for (name, command, root), _ in EvidenceCollectionService._plc_gate_plan(
                candidate, projects
            )
        )
        return (
            isinstance(gates, list)
            and len(gates) == len(expected)
            and all(
                isinstance(gate, dict)
                and set(gate)
                == {"name", "command", "cwd", "exit_code", "output_digest", "output_summary"}
                and (gate["name"], gate["command"], gate["cwd"]) == expected[index]
                and type(gate["exit_code"]) is int
                and gate["exit_code"] == 0
                and isinstance(gate["output_digest"], str)
                and bool(gate["output_digest"])
                and isinstance(gate["output_summary"], str)
                for index, gate in enumerate(gates)
            )
        )

    @staticmethod
    def _owned_path_entries(run: RunItem, candidate: Path) -> tuple[_OwnedPath, ...]:
        """Normalize owned paths once and find the PLC project root of each."""

        EvidenceCollectionService._normalize_owned_paths(run.owned_paths)
        entries: list[_OwnedPath] = []
        seen: set[PurePosixPath] = set()
        for raw_path in run.owned_paths:
            relative = PurePosixPath(str(raw_path).replace("\\", "/"))
            if relative in seen:
                continue
            seen.add(relative)
            absolute = candidate.joinpath(*relative.parts).resolve()
            try:
                absolute.relative_to(candidate)
            except ValueError as error:
                raise EvidenceCollectionError(f"Run owned path 超出 candidate: {relative}") from error
            entries.append(
                _OwnedPath(
                    relative, absolute, EvidenceCollectionService._plc_root_of(candidate, absolute)
                )
            )
        return tuple(entries)

    @staticmethod
    def _plc_root_of(candidate: Path, absolute: Path) -> Path | None:
        """Return the highest directory below the candidate holding ``.plc.json``."""

        relative = absolute.relative_to(candidate)
        parts = relative.parts if absolute.is_dir() else relative.parts[:-1]
        current = candidate
        for part in parts:
            current = current / part
            if (current / ".plc.json").is_file():
                return current
        return None

    @staticmethod
    def _plc_project_targets(
        run: RunItem, candidate: Path, anchor: Path
    ) -> tuple[tuple[_PlcProject, ...], tuple[str, ...]]:
        """Group owned PLC paths by project root and list the exact owned SCL files."""

        entries = EvidenceCollectionService._owned_path_entries(run, candidate)
        if not any(entry.plc_root is not None for entry in entries):
            raise EvidenceCollectionError("Run 缺少 PLC 工程内的 owned path")
        if any(entry.plc_root is None and entry.relative.suffix == ".py" for entry in entries):
            raise EvidenceCollectionError(_PLC_MIXED_DOMAIN_ERROR)
        groups: dict[Path, list[str]] = {}
        owned: list[str] = []
        for entry in entries:
            root = entry.plc_root
            if root is None:
                continue
            try:
                entry.absolute.relative_to(anchor)
            except ValueError as error:
                raise EvidenceCollectionError(
                    f"质量门 project_root 未覆盖 Run owned PLC path: {entry.relative}"
                ) from error
            scl_paths = groups.setdefault(root, [])
            owned.append(entry.relative.as_posix())
            if entry.absolute.is_dir():
                scl_paths.extend(
                    path.relative_to(root).as_posix()
                    for path in entry.absolute.rglob("*")
                    if path.is_file() and path.suffix.lower() == ".scl"
                )
            elif entry.relative.suffix.lower() == ".scl":
                if not entry.absolute.is_file():
                    raise EvidenceCollectionError(f"Run owned SCL path 不存在: {entry.relative}")
                scl_paths.append(entry.absolute.relative_to(root).as_posix())
        projects = tuple(
            _PlcProject(root, tuple(sorted(set(paths))))
            for root, paths in sorted(groups.items(), key=lambda item: str(item[0]))
        )
        return projects, tuple(sorted(set(owned)))

    @staticmethod
    def _plc_gate_plan(
        candidate: Path, projects: tuple[_PlcProject, ...]
    ) -> tuple[tuple[tuple[str, tuple[str, ...], Path], _PlcProject], ...]:
        """List the fixed gates once, so producers and replay checks cannot drift."""

        plan: list[tuple[tuple[str, tuple[str, ...], Path], _PlcProject]] = []
        for project in projects:
            relative_root = project.root.relative_to(candidate).as_posix()
            plan.append(
                (("plc-check", (_PLC_CHECK_COMMAND, relative_root), project.root), project)
            )
            if project.scl_paths:
                plan.append(
                    (("scl-lint", (_PLC_LINT_COMMAND, *project.scl_paths), project.root), project)
                )
        return tuple(plan)

    @staticmethod
    def _plc_baseline(
        candidate: Path, git_head: str, project: _PlcProject, destination: Path
    ) -> _PlcBaseline:
        """Export one project at the Run baseline; a failed export is recorded, never fatal."""

        from auto_pm.application.core.plc_baseline import (
            PlcBaselineError,
            baseline_anchor_note,
            export_plc_baseline,
        )

        relative = project.root.relative_to(candidate).as_posix()
        try:
            exported = export_plc_baseline(candidate, git_head, relative, destination)
            anchor = baseline_anchor_note(candidate, git_head)
        except (PlcBaselineError, OSError, tarfile.TarError) as error:
            return _PlcBaseline(git_head, None, None, f"开工基线取不出来（{error}），现在的失败全部按新增算")
        if exported is None:
            return _PlcBaseline(git_head, None, None, "开工基线上还没有这个工程，现在的失败全部按新增算")
        return _PlcBaseline(git_head, destination, exported, anchor_note=anchor)

    @staticmethod
    def _run_plc_gate(
        candidate: Path,
        name: str,
        command: tuple[str, ...],
        root: Path,
        project: _PlcProject,
        baseline: _PlcBaseline | None = None,
    ) -> PythonQualityGate:
        """Execute one in-process PLC gate and bind its full output by digest."""

        def judge() -> tuple[str, int | None]:
            if name == "plc-check":
                return _plc_check_output(candidate, root, baseline)
            return _scl_lint_output(root, project.scl_paths, baseline)

        try:
            output, exit_code = _run_bounded(judge, _quality_gate_timeout_seconds())
        except _PlcGateTimeoutError as error:
            output = f"timeout: {error}"
            exit_code = None
        except Exception as error:
            output = f"launch error: {error}"
            exit_code = None
        return PythonQualityGate(
            name=name,
            command=command,
            cwd=str(root),
            exit_code=exit_code,
            output_digest=hashlib.sha256(output.encode("utf-8")).hexdigest(),
            output_summary=_safe_output_summary(output),
        )

    @staticmethod
    def _plc_input_digests(
        candidate: Path, projects: tuple[_PlcProject, ...]
    ) -> tuple[tuple[str, str], ...]:
        """Hash every file under each PLC project root, ignored files included.

        Git evidence cannot see ignored files, yet the checker and linter read
        whatever is on disk.  This digest is the byte-level proof that the
        ``.plc.json``, SCL, INT and VAR inputs are the ones that were checked.
        """

        digests: list[tuple[str, str]] = []
        for project in projects:
            entries: list[tuple[str, str]] = []
            for directory, names, files in os.walk(project.root):
                names[:] = sorted(name for name in names if name != ".git")
                for name in (*names, *sorted(files)):
                    path = Path(directory) / name
                    if path.is_dir() and not path.is_symlink():
                        continue
                    relative = path.relative_to(project.root).as_posix()
                    if path.is_symlink():
                        entries.append((relative, f"symlink:{os.readlink(path)}"))
                        continue
                    try:
                        entries.append((relative, hashlib.sha256(path.read_bytes()).hexdigest()))
                    except OSError as error:
                        raise EvidenceCollectionError(
                            f"PLC 输入文件无法读取: {relative}"
                        ) from error
            digests.append(
                (project.root.relative_to(candidate).as_posix(), _sha256_payload(sorted(entries)))
            )
        return tuple(digests)

    @staticmethod
    def _plc_checker_files() -> list[tuple[str, Path]]:
        """List the files whose bytes decide the PLC verdict: the checker package plus the modules outside it that it relies on.

        Outside the package the verdict depends on exactly two modules (measured from ``sys.modules`` after importing
        the checker): ``find_prd_dir`` and its constants (``ext/paths.py``), and ``CheckResult.add`` / ``all_pass``, which
        turn items into pass/warn/fail counts (``ext/models_plc.py``). ``ProjectType`` is a ``Literal`` constant only.

        Boundary (TD-SW008-033): inputs outside the project roots that Git ignores are not bound; they are
        covered, if at all, by the per-project input digests.
        """

        from auto_pm.application.core.paths import find_prd_dir
        from auto_pm.domain.models.plc import CheckResult
        from auto_pm.domain.plc import checker as plc_checker

        location = getattr(plc_checker, "__file__", None)
        if not location:
            raise EvidenceCollectionError("PLC 检查器位置无法确定")
        package = Path(location).resolve().parent
        files = [(path.name, path) for path in sorted(package.glob("*.py"))]
        for label, owner in (("ext/paths.py", find_prd_dir), ("ext/models_plc.py", CheckResult)):
            module_file = getattr(sys.modules.get(owner.__module__), "__file__", None)
            if not module_file:
                raise EvidenceCollectionError(f"PLC 检查器依赖的模块位置无法确定: {label}")
            files.append((label, Path(module_file).resolve()))
        return files

    @staticmethod
    def _plc_checker_digest() -> str:
        """Fingerprint the checker package bytes (and the modules it depends on) that produced the verdict."""

        return _sha256_payload(
            [
                (name, hashlib.sha256(path.read_bytes()).hexdigest())
                for name, path in EvidenceCollectionService._plc_checker_files()
            ]
        )


@dataclass(frozen=True)
class _QualityTargets:
    """Exact Run-owned Python target lists for the three quality tools."""

    tests: tuple[str, ...]
    python: tuple[str, ...]
    production: tuple[str, ...]


def _c03_checkpoint_pytest_command() -> tuple[str, ...]:
    """Return the immutable, receipt-bound C03 pytest invocation."""

    return (
        sys.executable,
        "-m",
        "pytest",
        "-o",
        "addopts=",
        "-p",
        "no:cacheprovider",
        "-k",
        _C03_CHECKPOINT_PYTEST_EXPRESSION,
        _C03_CHECKPOINT_PYTEST_TARGET,
    )


def _collection_payload(collection: EvidenceCollection) -> dict[str, object]:
    """Return the complete canonical payload for one Git evidence snapshot."""

    return {
        "run_id": collection.run_id,
        "baseline_git_head": collection.baseline_git_head,
        "worktree_path": collection.worktree_path,
        "staged_paths": list(collection.staged_paths),
        "unstaged_paths": list(collection.unstaged_paths),
        "untracked_paths": list(collection.untracked_paths),
        "untracked_content_hashes": [
            {"path": path, "sha256": digest}
            for path, digest in collection.untracked_content_hashes
        ],
        "staged_diff": collection.staged_diff,
        "staged_diff_sha256": _sha256_text(collection.staged_diff),
        "unstaged_diff": collection.unstaged_diff,
        "unstaged_diff_sha256": _sha256_text(collection.unstaged_diff),
    }


def _quality_gate_payload(gate: PythonQualityGate) -> dict[str, object]:
    """Render one process result with only serializable, audit-safe fields."""

    return {
        "name": gate.name,
        "command": list(gate.command),
        "cwd": gate.cwd,
        "exit_code": gate.exit_code,
        "output_digest": gate.output_digest,
        "output_summary": gate.output_summary,
    }


def _quality_receipt_payload_fields(
    *,
    run_id: str,
    baseline_git_head: str,
    candidate_path: str,
    project_root: str,
    evidence_hash: str,
    gates: tuple[PythonQualityGate, ...],
    evidence_current: bool,
    evidence_error: str | None,
    project_roots: tuple[str, ...] = (),
    owned_python_paths: tuple[str, ...] = (),
) -> dict[str, object]:
    """Keep receipt hashing and checkpoint serialization on one exact schema."""

    payload: dict[str, object] = {
        "run_id": run_id,
        "baseline_git_head": baseline_git_head,
        "candidate_path": candidate_path,
        "project_root": project_root,
        "evidence_hash": evidence_hash,
        "gates": [_quality_gate_payload(gate) for gate in gates],
        "evidence_current": evidence_current,
        "evidence_error": evidence_error,
    }
    if project_roots:
        payload["project_roots"] = list(project_roots)
        payload["owned_python_paths"] = list(owned_python_paths)
    return payload


def _quality_receipt_payload(receipt: PythonQualityReceipt) -> dict[str, object]:
    """Render the exact fields protected by ``PythonQualityReceipt.content_hash``."""

    return _quality_receipt_payload_fields(
        run_id=receipt.run_id,
        baseline_git_head=receipt.baseline_git_head,
        candidate_path=receipt.candidate_path,
        project_root=receipt.project_root,
        evidence_hash=receipt.evidence_hash,
        gates=receipt.gates,
        evidence_current=receipt.evidence_current,
        evidence_error=receipt.evidence_error,
        project_roots=receipt.project_roots,
        owned_python_paths=receipt.owned_python_paths,
    )


def _quality_receipt_hash(
    *,
    run_id: str,
    baseline_git_head: str,
    candidate_path: str,
    project_root: str,
    evidence_hash: str,
    gates: tuple[PythonQualityGate, ...],
    evidence_current: bool,
    evidence_error: str | None,
    project_roots: tuple[str, ...] = (),
    owned_python_paths: tuple[str, ...] = (),
) -> str:
    """Hash the fixed receipt payload used by C02 and C03 evidence envelopes."""

    return _sha256_payload(
        _quality_receipt_payload_fields(
            run_id=run_id,
            baseline_git_head=baseline_git_head,
            candidate_path=candidate_path,
            project_root=project_root,
            evidence_hash=evidence_hash,
            gates=gates,
            evidence_current=evidence_current,
            evidence_error=evidence_error,
            project_roots=project_roots,
            owned_python_paths=owned_python_paths,
        )
    )


def _plc_receipt_payload_fields(
    *,
    run_id: str,
    baseline_git_head: str,
    candidate_path: str,
    project_root: str,
    evidence_hash: str,
    gates: tuple[PythonQualityGate, ...],
    evidence_current: bool,
    evidence_error: str | None,
    project_roots: tuple[str, ...],
    owned_plc_paths: tuple[str, ...],
    input_digests: tuple[tuple[str, str], ...],
    checker_digest: str,
) -> dict[str, object]:
    """Keep PLC receipt hashing and checkpoint serialization on one exact schema."""

    return {
        "domain": "plc",
        "run_id": run_id,
        "baseline_git_head": baseline_git_head,
        "candidate_path": candidate_path,
        "project_root": project_root,
        "evidence_hash": evidence_hash,
        "gates": [_quality_gate_payload(gate) for gate in gates],
        "evidence_current": evidence_current,
        "evidence_error": evidence_error,
        "project_roots": list(project_roots),
        "owned_plc_paths": list(owned_plc_paths),
        "input_digests": [
            {"project": project, "sha256": digest} for project, digest in input_digests
        ],
        "checker_digest": checker_digest,
    }


def _plc_receipt_payload(receipt: PlcQualityReceipt) -> dict[str, object]:
    """Render the exact fields protected by ``PlcQualityReceipt.content_hash``."""

    return _plc_receipt_payload_fields(
        run_id=receipt.run_id,
        baseline_git_head=receipt.baseline_git_head,
        candidate_path=receipt.candidate_path,
        project_root=receipt.project_root,
        evidence_hash=receipt.evidence_hash,
        gates=receipt.gates,
        evidence_current=receipt.evidence_current,
        evidence_error=receipt.evidence_error,
        project_roots=receipt.project_roots,
        owned_plc_paths=receipt.owned_plc_paths,
        input_digests=receipt.input_digests,
        checker_digest=receipt.checker_digest,
    )


def _plc_receipt_hash(
    *,
    run_id: str,
    baseline_git_head: str,
    candidate_path: str,
    project_root: str,
    evidence_hash: str,
    gates: tuple[PythonQualityGate, ...],
    evidence_current: bool,
    evidence_error: str | None,
    project_roots: tuple[str, ...],
    owned_plc_paths: tuple[str, ...],
    input_digests: tuple[tuple[str, str], ...],
    checker_digest: str,
) -> str:
    """Hash the fixed PLC receipt payload used by ``checkpoint-evidence.v3``."""

    return _sha256_payload(
        _plc_receipt_payload_fields(
            run_id=run_id,
            baseline_git_head=baseline_git_head,
            candidate_path=candidate_path,
            project_root=project_root,
            evidence_hash=evidence_hash,
            gates=gates,
            evidence_current=evidence_current,
            evidence_error=evidence_error,
            project_roots=project_roots,
            owned_plc_paths=owned_plc_paths,
            input_digests=input_digests,
            checker_digest=checker_digest,
        )
    )


def _plc_language_service() -> LanguageService | None:
    """The Siemens language service the acceptance gate runs, same as ``plc check``.

    A missing plugin is reported by the checker as "未验证" (warn), never as a pass.
    """

    from auto_pm.infrastructure.siemens_language_service import (
        DEFAULT_TIMEOUT_SECONDS,
        default_language_service,
    )

    # TD-SW008-188（只做一半）：每次调用插件命令行的时限取插件默认值与质量门时限中较小的一个（至少 1 秒），
    # 即单次调用最多 min(600, T) 秒。这不保证子进程不会比门禁活得更久：门禁线程放弃后收不掉，
    # 它还可能接着再起新的子进程（每个又可活到该时限）；门禁截止时间传不下去、也取消不了，另立设计债。
    return default_language_service(timeout=max(1, min(DEFAULT_TIMEOUT_SECONDS, math.ceil(_quality_gate_timeout_seconds()))))


def _with_anchor(note: str, baseline: _PlcBaseline | None) -> str:
    """Append the "baseline is not on main" remark to whatever else the baseline note says."""

    anchor = baseline.anchor_note if baseline else ""
    return "；".join(part for part in (note, anchor) if part)


def _baseline_title(baseline: _PlcBaseline | None) -> str:
    head = baseline.git_head[:12] if baseline else "?"
    return f"和 Run 开工基线 {head} 逐条比"


class _PlcGateTimeoutError(Exception):
    """Raised when an in-process PLC gate does not answer within its wall-clock bound."""


def _quality_gate_timeout_seconds() -> float:
    """Return the per-gate bound shared by the Python and PLC gates; ``AUTO_PM_QUALITY_GATE_TIMEOUT_SECONDS`` overrides the default."""

    raw = os.environ.get(_QUALITY_GATE_TIMEOUT_ENV, "").strip()
    if not raw:
        return _QUALITY_GATE_TIMEOUT_DEFAULT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return _QUALITY_GATE_TIMEOUT_DEFAULT_SECONDS
    # inf（以及 1e400 这类溢出值）会让质量门永远不超时，nan 比较恒为假：都不是合法时限，退回默认。
    return value if math.isfinite(value) and value > 0 else _QUALITY_GATE_TIMEOUT_DEFAULT_SECONDS


def _run_bounded(work: Callable[[], tuple[str, int | None]], seconds: float) -> tuple[str, int | None]:
    """Run an in-process gate on a daemon thread and fail clearly if it outlives ``seconds``.

    Python cannot kill a thread, so a wedged check is abandoned (daemon, read-only) and the
    gate is reported as not run; it can never hold the whole verification forever.
    """

    outcome: list[tuple[str, int | None]] = []
    failure: list[BaseException] = []

    def target() -> None:
        try:
            outcome.append(work())
        except BaseException as error:  # re-raised on the caller's thread below
            failure.append(error)

    worker = threading.Thread(target=target, name="plc-quality-gate", daemon=True)
    worker.start()
    worker.join(seconds)
    if worker.is_alive():
        raise _PlcGateTimeoutError(f"PLC 质量门超过 {seconds:g} 秒没有结束，这次检查不算数")
    if failure:
        raise failure[0]
    return outcome[0]


def _plc_check_output(
    candidate: Path, root: Path, baseline: _PlcBaseline | None = None
) -> tuple[str, int | None]:
    """Run the existing project checker on a governed PLC root (read-only).

    The candidate worktree is the checker's workspace root, so the spec registry
    and library paths it consults come from the Run baseline, not the control root.
    The verdict is "no new failures": the same checker also runs on the project as
    exported from the Run baseline commit, and failures already there do not block.
    """

    from auto_pm.application.core.plc_baseline import checked_keys

    service = _plc_language_service()
    result, now, incomplete = checked_keys(candidate, root, service)
    if result.not_applicable:
        return f"PLC 检查对该工程不适用: {result.not_applicable_reason}", None
    if incomplete:
        raise RuntimeError("Siemens 语言服务命令行没有跑完（超时或起不来），这次检查不算数")
    base: Counter[str] | None = None
    note = baseline.note if baseline else "没有开工基线，现在的失败全部按新增算"
    if baseline is not None and baseline.workspace is not None and baseline.project is not None:
        try:
            base_result, base_keys, base_incomplete = checked_keys(
                baseline.workspace, baseline.project, service
            )
            if base_incomplete:
                note = "开工基线上 Siemens 语言服务没有跑完，现在的失败全部按新增算"
            elif not base_result.not_applicable:
                base = base_keys
        except Exception as error:  # the baseline run must never hide a current failure
            note = f"开工基线检查出错（{error}），现在的失败全部按新增算"
    diff = diff_failures(now, base, baseline_note=_with_anchor(note, baseline))
    # Verdict and new failures first: the bounded summary must never hide the reason.
    lines = diff.render(_baseline_title(baseline))
    if any(item.item == "Siemens 语言服务 check" and item.status == "warn" for item in result.items):
        # Not a pass: AGENTS.md rule — an unfound plugin is "unverified", blocked at the delivery stage gate.
        # Right after the verdict and the new failures, so the bounded summary keeps it.
        lines.insert(1 + bool(diff.baseline_note) + len(diff.new), "注意：本机没找到 Siemens 插件命令行，语言服务这一层未验证（交付阶段门禁按失败处理）")
    rank = {"fail": 0, "warn": 1}
    ordered = sorted(result.items, key=lambda item: rank.get(item.status, 2))
    lines.extend(f"{item.status} | {item.item} | {item.message}" for item in ordered)
    lines.append(
        f"pass={result.pass_count} warn={result.warn_count} fail={result.fail_count}"
        f" new={len(diff.new)} known={len(diff.known)}"
    )
    return "\n".join(lines), (0 if diff.passed else 1)


def _scl_lint_output(
    root: Path, scl_paths: tuple[str, ...], baseline: _PlcBaseline | None = None
) -> tuple[str, int | None]:
    """Lint exactly the owned SCL files with the existing LSP-905 linter.

    Errors the same owned file already had at the Run baseline do not block; an
    owned file that did not exist at the baseline has only new errors.
    """

    from auto_pm.domain.plc.scl_linter import SclLinter

    errors = 0
    warnings = 0
    lines: list[str] = []
    for relative in scl_paths:
        report = SclLinter.lint_file(str(root / relative))
        errors += report.errors_count
        warnings += report.warnings_count
        lines.extend(
            f"{relative}:{violation.line_number} {violation.severity} {violation.message}"
            for violation in report.violations
        )
    lines.append(f"files={len(scl_paths)} errors={errors} warnings={warnings}")
    now = lint_failure_keys((relative, root / relative) for relative in scl_paths)
    base: Counter[str] | None = None
    note = baseline.note if baseline else "没有开工基线，现在的错误全部按新增算"
    if baseline is not None and baseline.project is not None:
        base_project = baseline.project
        base = lint_failure_keys(
            (relative, base_project / relative)
            for relative in scl_paths
            if (base_project / relative).is_file()
        )
    diff = diff_failures(now, base, baseline_note=_with_anchor(note, baseline))
    return "\n".join([*diff.render(_baseline_title(baseline)), *lines]), (0 if diff.passed else 1)


def _canonical_json_payload(payload: object) -> str:
    """Render a platform-neutral JSON payload used for immutable evidence."""

    return json.dumps(
        payload,
        default=lambda value: value.__dict__,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_payload(payload: object) -> str:
    """Hash a stable JSON rendering without allowing platform-dependent ordering."""

    return _sha256_text(_canonical_json_payload(payload))


def _sha256_text(value: str) -> str:
    """Hash Unicode text after fixing the repository's UTF-8 evidence encoding."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def quality_failure_summary(receipt: PythonQualityReceipt | PlcQualityReceipt, *, excerpt_chars: int = 600) -> str:
    """Which gate failed and why, in words: the failing gates (name, exit code, output excerpt) and any evidence drift.

    A failing receipt used to say only "要求质量收据为 PASS"; nobody could tell ruff from mypy from pytest from a drifted evidence hash.
    """

    parts: list[str] = []
    for gate in receipt.gates:
        if gate.passed:
            continue
        code = "未能启动或超时" if gate.exit_code is None else f"退出码 {gate.exit_code}"
        excerpt = gate.output_summary.strip()
        if len(excerpt) > excerpt_chars:
            excerpt = excerpt[:excerpt_chars] + "…"
        parts.append(f"[{gate.name}] {code}\n{excerpt}")
    if not receipt.evidence_current:
        parts.append(f"[evidence] {receipt.evidence_error or 'Run evidence 与质量门前不一致'}")
    if not receipt.gates:
        parts.append("[gates] 没有任何质量门被执行")
    return "\n".join(parts) if parts else "（收据状态非 PASS，但未发现失败项）"


def write_quality_failure_report(
    receipt: PythonQualityReceipt | PlcQualityReceipt, reports_root: Path
) -> Path | None:
    """Persist a failing receipt as JSON under ``reports_root`` (``.auto-pm/reports/quality-failures``); ``None`` when it cannot be written.

    Writing is best effort and never changes the verdict: the caller still refuses the checkpoint either way.
    """

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    # run_id 来自账本，不当作可信路径：只留字母数字和 ._-，再核对最终落点必须直接在 reports_root 下（预审 425）。
    safe_run_id = re.sub(r"[^A-Za-z0-9._-]", "_", receipt.run_id)[:120] or "run"
    path = reports_root / f"{safe_run_id}-{stamp}.json"
    try:
        reports_root.mkdir(parents=True, exist_ok=True)
        if path.resolve().parent != reports_root.resolve():
            return None
        payload = {"status": receipt.status, **asdict(receipt)}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    except (OSError, ValueError, TypeError):
        return None
    return path


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
    "PlcQualityReceipt",
    "PythonQualityGate",
    "PythonQualityReceipt",
    "quality_failure_summary",
    "write_quality_failure_report",
]
