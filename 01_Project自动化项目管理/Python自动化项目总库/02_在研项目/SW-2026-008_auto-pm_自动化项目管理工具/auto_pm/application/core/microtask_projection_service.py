"""Project approved microtask files back to one clean candidate with CAS evidence."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from auto_pm.contracts.execution_adapter import (
    ExecutionMicrotaskPlan,
    ExecutionProjectionFile,
    ExecutionProjectionReceipt,
)
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError
from auto_pm.infrastructure.control_root_guard import (
    ControlRootGuardError,
    clean_git_environment,
    is_link_like,
)


class MicrotaskProjectionError(RuntimeError):
    """Raised before unapproved, stale, linked, or partial input can be projected."""


class MicrotaskProjectionIndeterminateError(MicrotaskProjectionError):
    """Raised when a clean rollback or durable projection fact cannot be proven."""


class MicrotaskProjectionService:
    """Copy only Plan-declared regular files after complete source and target proof."""

    _MARKER = ".codex-microtask.json"

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        store: ContinuityStore | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._root = Path(workspace_root).resolve()
        self._store = store or ContinuityStore(self._root)
        self._now = now or (lambda: datetime.now(UTC))

    def project(
        self,
        operation_id: str,
        *,
        expected_source_commit: str,
    ) -> ExecutionProjectionReceipt:
        """Project one complete approved file set and append its unique receipt."""

        try:
            existing = self._store.get_execution_projection(operation_id)
            plan = self._store.get_execution_microtask_plan(operation_id)
            claim = self._store.get_execution_start_claim(operation_id)
        except ContinuityStoreError as error:
            raise MicrotaskProjectionError(str(error)) from error
        if plan is None or claim is None:
            raise MicrotaskProjectionError("projection 缺少 MicrotaskPlan 或 start claim")
        if claim.microtask_commit != expected_source_commit:
            raise MicrotaskProjectionError("projection source commit 与 start claim 不一致")
        if existing is not None:
            self._validate_replay(existing)
            return existing

        source = Path(plan.repository_path)
        target = Path(plan.source_worktree_path)
        self._validate_repository(source, plan, expected_source_commit)
        self._validate_clean_candidate(target, plan)
        manifest = {item.path: item for item in plan.manifest}
        if tuple(sorted(manifest)) != tuple(sorted(plan.declared_dirty_paths)):
            raise MicrotaskProjectionError("Plan manifest 与 declared_dirty_paths 不一致")

        prepared: list[tuple[Path, bytes, bytes, int, ExecutionProjectionFile]] = []
        for relative in sorted(plan.declared_dirty_paths):
            item = manifest[relative]
            source_path = self._safe_regular_path(source, relative)
            target_path = self._safe_regular_path(target, relative)
            current_oid = self._git(
                target, "hash-object", f"--path={relative}", "--", relative
            )
            if current_oid != item.blob_oid:
                raise MicrotaskProjectionError(f"candidate baseline hash 漂移: {relative}")
            projected = source_path.read_bytes()
            prepared.append(
                (
                    target_path,
                    projected,
                    target_path.read_bytes(),
                    target_path.stat().st_mode,
                    ExecutionProjectionFile(
                        path=relative,
                        baseline_sha256=item.content_sha256,
                        projected_sha256=hashlib.sha256(projected).hexdigest(),
                    ),
                )
            )

        files = tuple(item[4] for item in prepared)
        self._apply_batch_with_rollback(target, plan, prepared, files)
        request = {
            "operation_id": operation_id,
            "run_id": plan.run_id,
            "source_repository": str(source),
            "source_commit": expected_source_commit,
            "target_worktree": str(target),
            "baseline_git_head": plan.baseline_git_head,
            "files": [item.model_dump(mode="json") for item in files],
        }
        receipt = ExecutionProjectionReceipt(
            **request,
            projection_sha256=ExecutionMicrotaskPlan._hash(request),
            created_at=self._utc_now(),
        )
        try:
            persisted, _created = self._store.record_execution_projection(receipt)
        except ContinuityStoreError as error:
            raise MicrotaskProjectionIndeterminateError(
                "projection receipt 持久化结果无法证明；保持 PENDING"
            ) from error
        if persisted != receipt:
            raise MicrotaskProjectionIndeterminateError(
                "persisted projection receipt 载荷不一致；保持 PENDING"
            )
        return persisted

    def _apply_batch_with_rollback(
        self,
        target: Path,
        plan: ExecutionMicrotaskPlan,
        prepared: list[tuple[Path, bytes, bytes, int, ExecutionProjectionFile]],
        files: tuple[ExecutionProjectionFile, ...],
    ) -> None:
        """Apply the complete set or restore and prove the clean baseline."""

        applied: list[tuple[Path, bytes, int]] = []
        try:
            for destination, projected, baseline, mode, _proof in prepared:
                # Track before replace: even a wrapper that raises after replacement
                # must cause this destination to be restored.
                applied.append((destination, baseline, mode))
                self._atomic_replace(destination, projected, mode)
            self._validate_projected_candidate(target, plan, files)
        except Exception as error:
            try:
                for destination, baseline, mode in reversed(applied):
                    self._atomic_replace(destination, baseline, mode)
                self._validate_clean_candidate(target, plan)
            except Exception as rollback_error:
                raise MicrotaskProjectionIndeterminateError(
                    "projection 中断且 clean baseline 回滚无法证明；保持 PENDING"
                ) from rollback_error
            if isinstance(error, MicrotaskProjectionError):
                raise
            raise MicrotaskProjectionError(
                "projection 批次失败；已验证回滚到 clean baseline"
            ) from error

    @staticmethod
    def _atomic_replace(destination: Path, content: bytes, mode: int) -> None:
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=destination.parent,
                prefix=f".{destination.name}.auto-pm-",
                delete=False,
            ) as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
                temporary = Path(stream.name)
            temporary.chmod(mode)
            os.replace(temporary, destination)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _validate_repository(
        self, source: Path, plan: ExecutionMicrotaskPlan, expected_commit: str
    ) -> None:
        if (
            self._link_like(source)
            or self._link_like(source / ".git")
            or not source.is_dir()
            or not (source / ".git").is_dir()
        ):
            raise MicrotaskProjectionError("microtask repository 不是 standalone regular directory")
        if self._git(source, "rev-parse", "HEAD") != expected_commit:
            raise MicrotaskProjectionError("microtask repository HEAD 漂移")
        marker = source / self._MARKER
        if self._link_like(marker) or not marker.is_file():
            raise MicrotaskProjectionError("microtask marker 缺失或为链接")
        expected = self._canonical(self._marker(plan))
        if marker.read_bytes() != expected + b"\n":
            raise MicrotaskProjectionError("microtask marker 载荷漂移")
        if hashlib.sha256(expected).hexdigest() != plan.marker_sha256:
            raise MicrotaskProjectionError("microtask marker hash 漂移")

    def _validate_clean_candidate(self, target: Path, plan: ExecutionMicrotaskPlan) -> None:
        if self._link_like(target) or not target.is_dir():
            raise MicrotaskProjectionError("candidate 不存在或为符号链接")
        if self._git(target, "rev-parse", "HEAD") != plan.baseline_git_head:
            raise MicrotaskProjectionError("candidate HEAD CAS 失败")
        if self._git_bytes(
            target, "status", "--porcelain=v1", "-z", "--untracked-files=all"
        ):
            raise MicrotaskProjectionError("candidate 必须在 projection 前保持 clean")

    def _validate_projected_candidate(
        self,
        target: Path,
        plan: ExecutionMicrotaskPlan,
        files: tuple[ExecutionProjectionFile, ...],
    ) -> None:
        if self._git(target, "rev-parse", "HEAD") != plan.baseline_git_head:
            raise MicrotaskProjectionError("candidate HEAD 在 projection 中漂移")
        for item in files:
            path = self._safe_regular_path(target, item.path)
            if hashlib.sha256(path.read_bytes()).hexdigest() != item.projected_sha256:
                raise MicrotaskProjectionError(f"candidate projection hash 失败: {item.path}")
        actual = self._dirty_paths(target)
        expected = tuple(
            item.path for item in files if item.baseline_sha256 != item.projected_sha256
        )
        if actual != expected:
            raise MicrotaskProjectionError("candidate dirty path 与 projection receipt 不一致")

    def _validate_replay(self, receipt: ExecutionProjectionReceipt) -> None:
        target = Path(receipt.target_worktree)
        if self._git(target, "rev-parse", "HEAD") != receipt.baseline_git_head:
            raise MicrotaskProjectionError("projection replay candidate HEAD 漂移")
        for item in receipt.files:
            path = self._safe_regular_path(target, item.path)
            if hashlib.sha256(path.read_bytes()).hexdigest() != item.projected_sha256:
                raise MicrotaskProjectionError("projection replay candidate content 漂移")
        expected = tuple(
            item.path
            for item in receipt.files
            if item.baseline_sha256 != item.projected_sha256
        )
        if self._dirty_paths(target) != expected:
            raise MicrotaskProjectionError("projection replay dirty path 漂移")

    @classmethod
    def _safe_regular_path(cls, root: Path, relative: str) -> Path:
        current = root
        for part in PurePosixPath(relative).parts:
            current = current / part
            if cls._link_like(current):
                raise MicrotaskProjectionError(f"projection path 含符号链接: {relative}")
        try:
            current.resolve(strict=True).relative_to(root.resolve(strict=True))
        except (OSError, ValueError) as error:
            raise MicrotaskProjectionError(f"projection path 越界或缺失: {relative}") from error
        if not current.is_file():
            raise MicrotaskProjectionError(f"projection path 不是常规文件: {relative}")
        return current

    @staticmethod
    def _link_like(path: Path) -> bool:
        try:
            return is_link_like(path)
        except ControlRootGuardError as error:
            raise MicrotaskProjectionError("projection link fact 无法读取") from error

    def _dirty_paths(self, root: Path) -> tuple[str, ...]:
        raw = self._git_bytes(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
        paths: list[str] = []
        for row in (item for item in raw.split(b"\0") if item):
            if len(row) < 4 or row[2:3] != b" ":
                raise MicrotaskProjectionError("candidate git status 无法验证")
            paths.append(row[3:].decode("utf-8", errors="strict"))
        return tuple(sorted(paths))

    @staticmethod
    def _marker(plan: ExecutionMicrotaskPlan) -> dict[str, object]:
        return {
            "schema_version": "codex-microtask.v1",
            "operation_id": plan.operation_id,
            "mission_id": plan.mission_id,
            "run_id": plan.run_id,
            "approved_model": plan.approved_model,
            "objective": plan.objective,
            "owned_paths": list(plan.owned_paths),
            "declared_dirty_paths": list(plan.declared_dirty_paths),
            "source_worktree_path": plan.source_worktree_path,
            "baseline_git_head": plan.baseline_git_head,
            "repository_path": plan.repository_path,
            "manifest": [item.model_dump(mode="json") for item in plan.manifest],
            "manifest_sha256": plan.manifest_sha256,
            "request_sha256": plan.request_sha256,
        }

    @staticmethod
    def _canonical(payload: object) -> bytes:
        return json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    def _git(self, root: Path, *arguments: str) -> str:
        return self._git_bytes(root, *arguments).decode("utf-8", errors="strict").strip()

    @staticmethod
    def _git_bytes(root: Path, *arguments: str) -> bytes:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            capture_output=True,
            check=False,
            timeout=30,
            env=clean_git_environment(),
        )
        if result.returncode != 0:
            raise MicrotaskProjectionError("Git 无法证明 projection 边界")
        return result.stdout

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            raise MicrotaskProjectionError("projection timestamp 必须包含时区")
        return value.astimezone(UTC)


__all__ = [
    "MicrotaskProjectionError",
    "MicrotaskProjectionIndeterminateError",
    "MicrotaskProjectionService",
]
