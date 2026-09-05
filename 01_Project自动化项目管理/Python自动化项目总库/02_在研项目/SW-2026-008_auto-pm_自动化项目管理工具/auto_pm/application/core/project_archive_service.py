"""Reversible, fail-closed project archive and restore application service."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol, cast

from auto_pm.core.change_transaction import ChangeTransactionManager

from auto_pm.contracts.workflow_dtos import TransactionStatus
from auto_pm.domain.project.archive_contracts import (
    ArchiveAuthorization,
    ArchiveContractError,
    ArchiveErrorCode,
    ArchiveOperation,
    ArchivePlan,
    ArchivePreflightFacts,
    ArchiveRequest,
    DuplicateRequestState,
    build_archive_plan,
    canonical_project_path,
)

_REPARSE_POINT = 0x0400
_PROJECT_ID = re.compile(r"^[A-Z]{2,4}-[0-9]{4}-[0-9]{3}$")


class ArchivePolicyPort(Protocol):
    """Read-only governance facts required before any archive effect."""

    def authorization_for(self, request: ArchiveRequest) -> ArchiveAuthorization: ...

    def open_change_ids(self, project_id: str) -> tuple[str, ...]: ...


class ArchiveProjectionPort(Protocol):
    """Rebuildable DB or scanner projection with explicit compensation."""

    def apply(self, operation: ArchiveOperation, project_id: str) -> None: ...

    def compensate(self, operation: ArchiveOperation, project_id: str) -> None: ...


class NullArchiveProjection:
    """Explicit no-op adapter used when no projection is configured."""

    def apply(self, operation: ArchiveOperation, project_id: str) -> None:
        del operation, project_id

    def compensate(self, operation: ArchiveOperation, project_id: str) -> None:
        del operation, project_id


@dataclass(frozen=True, slots=True)
class ArchiveResult:
    """Auditable outcome of a completed or idempotently replayed request."""

    request_id: str
    project_id: str
    operation: ArchiveOperation
    archive_code: str
    source_path: str
    destination_path: str
    idempotent_replay: bool


class ArchiveExecutionError(RuntimeError):
    """Effect failure, optionally retaining transaction recovery evidence."""

    def __init__(self, message: str, recovery_path: str = "") -> None:
        super().__init__(message)
        self.recovery_path = recovery_path


class ProjectArchiveService:
    """Execute exact archive plans with real filesystem and Git safety gates."""

    LEDGER_PATH = ".auto-pm/project-archive-ledger.json"
    LOCK_DIR = ".auto-pm/archive-locks"

    def __init__(
        self,
        workspace_root: str | Path,
        policy: ArchivePolicyPort,
        database: ArchiveProjectionPort | None = None,
        scanner: ArchiveProjectionPort | None = None,
        git_executable: str = "git",
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        if not self.workspace_root.is_dir():
            raise ValueError(f"工作区不存在: {self.workspace_root}")
        self.policy = policy
        self.database = database or NullArchiveProjection()
        self.scanner = scanner or NullArchiveProjection()
        self.git_executable = git_executable
        self.transactions = ChangeTransactionManager(self.workspace_root)

    @staticmethod
    def _is_link_or_reparse(path: Path) -> bool:
        try:
            attributes = getattr(path.lstat(), "st_file_attributes", 0)
        except OSError:
            return False
        return path.is_symlink() or bool(attributes & _REPARSE_POINT)

    def _resolve(self, relative_path: str) -> Path:
        canonical = canonical_project_path(relative_path)
        target = self.workspace_root / canonical
        current = self.workspace_root
        for part in Path(canonical).parts:
            current /= part
            if current.exists() and self._is_link_or_reparse(current):
                raise ArchiveContractError(
                    ArchiveErrorCode.LINK_ANOMALY, f"路径含链接: {canonical}"
                )
        resolved = target.resolve()
        try:
            resolved.relative_to(self.workspace_root)
        except ValueError as exc:
            raise ArchiveContractError(
                ArchiveErrorCode.PATH_ESCAPE, f"路径越界: {canonical}"
            ) from exc
        return Path(resolved)

    def _read_ledger(self) -> list[dict[str, str]]:
        path = self._resolve(self.LEDGER_PATH)
        if not path.exists():
            return []
        try:
            value = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ArchiveContractError(ArchiveErrorCode.LEDGER_DAMAGED, "归档台账损坏") from exc
        if not isinstance(value, list) or not all(
            isinstance(row, dict)
            and all(isinstance(key, str) and isinstance(item, str) for key, item in row.items())
            for row in value
        ):
            raise ArchiveContractError(ArchiveErrorCode.LEDGER_DAMAGED, "归档台账结构非法")
        return value

    def _write_ledger(self, rows: list[dict[str, str]]) -> None:
        path = self._resolve(self.LEDGER_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            errors="replace",
        )
        os.replace(temporary, path)

    @staticmethod
    def _duplicate_state(
        rows: list[dict[str, str]], request: ArchiveRequest
    ) -> DuplicateRequestState:
        for row in rows:
            if row.get("request_id") != request.request_id:
                continue
            identity = (
                row.get("project_id"),
                row.get("operation"),
                row.get("source_path"),
                row.get("destination_path"),
            )
            requested = (
                request.project_id,
                request.operation.value,
                request.source_path,
                request.destination_path,
            )
            if identity == requested and row.get("result") == "completed":
                return DuplicateRequestState.SAME_COMPLETED
            return DuplicateRequestState.CONFLICT
        return DuplicateRequestState.NEW

    @staticmethod
    def _allocate_archive_code(rows: list[dict[str, str]]) -> str:
        prefix = f"ARC-{datetime.now().strftime('%Y%m%d')}-"
        numbers = [
            int(code[-3:])
            for row in rows
            if (code := row.get("archive_code", "")).startswith(prefix) and code[-3:].isdigit()
        ]
        return f"{prefix}{max(numbers, default=0) + 1:03d}"

    def _run_git(self, path: Path) -> tuple[bool, int, bool]:
        try:
            proc = subprocess.run(
                [self.git_executable, "status", "--porcelain", "--", "."],
                cwd=path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except FileNotFoundError:
            return False, 127, False
        return True, proc.returncode, proc.returncode == 0 and not proc.stdout.strip()

    @staticmethod
    def _phase_file(project_path: Path, project_id: str) -> Path:
        path = project_path / f"PM_SESSION_{project_id}.md"
        if not path.is_file():
            raise ArchiveContractError(
                ArchiveErrorCode.INVALID_REQUEST, f"缺少 PM_SESSION: {project_id}"
            )
        return path

    @staticmethod
    def _read_phase(path: Path) -> str:
        content = path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"^phase:\s*([^\n]+)$", content, re.MULTILINE)
        return match.group(1).strip() if match else "developing"

    @staticmethod
    def _set_phase(path: Path, phase: str) -> None:
        content = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"^phase:\s*.*$", content, re.MULTILINE):
            updated = re.sub(r"^phase:\s*.*$", f"phase: {phase}", content, flags=re.MULTILINE)
        else:
            updated = f"---\nphase: {phase}\n---\n\n{content}"
        path.write_text(updated, encoding="utf-8", errors="replace")

    def _restore_entry(self, rows: list[dict[str, str]], request: ArchiveRequest) -> dict[str, str]:
        matches = [
            row
            for row in rows
            if row.get("archive_code") == request.archive_code
            and row.get("project_id") == request.project_id
            and row.get("status") == "archived"
        ]
        if len(matches) != 1:
            raise ArchiveContractError(
                ArchiveErrorCode.ARCHIVE_CODE_INVALID, "归档编号不存在或不唯一"
            )
        row = matches[0]
        if (
            row.get("destination_path") != request.source_path
            or row.get("source_path") != request.destination_path
        ):
            raise ArchiveContractError(
                ArchiveErrorCode.NOT_AUTHORIZED, "恢复路径与归档记录不精确匹配"
            )
        return row

    def _facts(
        self,
        request: ArchiveRequest,
        source: Path,
        destination: Path,
        rows: list[dict[str, str]],
        authorization: ArchiveAuthorization,
        open_changes: tuple[str, ...],
        lock_acquired: bool,
    ) -> ArchivePreflightFacts:
        git_available, git_returncode, git_clean = self._run_git(source)
        return ArchivePreflightFacts(
            authorization=authorization,
            chg_query_succeeded=True,
            open_change_ids=open_changes,
            git_available=git_available,
            git_returncode=git_returncode,
            git_clean=git_clean,
            ledger_readable=True,
            ledger_valid=True,
            source_exists=source.is_dir(),
            destination_exists=destination.exists(),
            source_link_anomaly=self._is_link_or_reparse(source),
            destination_link_anomaly=(
                destination.exists() and self._is_link_or_reparse(destination)
            ),
            lock_acquired=lock_acquired,
            duplicate_request=self._duplicate_state(rows, request),
        )

    def _lock(self) -> tuple[Path, int]:
        lock = self._resolve(f"{self.LOCK_DIR}/workspace.lock")
        lock.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise ArchiveContractError(ArchiveErrorCode.CONCURRENCY_CONFLICT, "归档锁冲突") from exc
        try:
            os.write(descriptor, b"archive-workspace-lock")
        except OSError:
            os.close(descriptor)
            lock.unlink(missing_ok=True)
            raise
        return lock, descriptor

    def execute(self, request: ArchiveRequest) -> ArchiveResult:
        """Validate every gate, hold the lock, and execute reversible effects."""
        if not _PROJECT_ID.fullmatch(request.project_id):
            raise ArchiveContractError(ArchiveErrorCode.INVALID_REQUEST, "项目编号格式非法")
        source = self._resolve(request.source_path)
        destination = self._resolve(request.destination_path)
        if not destination.parent.is_dir() or self._is_link_or_reparse(destination.parent):
            raise ArchiveContractError(ArchiveErrorCode.LINK_ANOMALY, "目标父目录缺失或异常")
        rows = self._read_ledger()
        try:
            authorization = self.policy.authorization_for(request)
        except Exception as exc:
            raise ArchiveContractError(
                ArchiveErrorCode.AUTHORIZATION_QUERY_FAILED, "授权查询失败"
            ) from exc
        try:
            approved_paths = {canonical_project_path(path) for path in authorization.approved_paths}
        except ArchiveContractError as exc:
            raise ArchiveContractError(ArchiveErrorCode.NOT_AUTHORIZED, "审批路径非法") from exc
        if (
            not authorization.query_succeeded
            or authorization.decision_id != request.decision_id
            or authorization.approved_operation is not request.operation
            or authorization.approved_project_id != request.project_id
            or {request.source_path, request.destination_path} - approved_paths
        ):
            raise ArchiveContractError(ArchiveErrorCode.NOT_AUTHORIZED, "请求超出审批范围")
        duplicate = self._duplicate_state(rows, request)
        if duplicate is DuplicateRequestState.CONFLICT:
            raise ArchiveContractError(ArchiveErrorCode.DUPLICATE_REQUEST, "请求标识已用于不同操作")
        if duplicate is DuplicateRequestState.SAME_COMPLETED:
            existing = next(row for row in rows if row.get("request_id") == request.request_id)
            return ArchiveResult(
                request.request_id,
                request.project_id,
                request.operation,
                existing.get("archive_code", request.archive_code),
                request.source_path,
                request.destination_path,
                True,
            )
        try:
            open_changes = self.policy.open_change_ids(request.project_id)
        except Exception as exc:
            raise ArchiveContractError(ArchiveErrorCode.CHG_QUERY_FAILED, "变更单查询失败") from exc

        preliminary = self._facts(
            request, source, destination, rows, authorization, open_changes, False
        )
        try:
            build_archive_plan(request, preliminary)
        except ArchiveContractError as exc:
            if exc.code is not ArchiveErrorCode.CONCURRENCY_CONFLICT:
                raise
        if request.operation is ArchiveOperation.RESTORE:
            self._restore_entry(rows, request)

        lock, descriptor = self._lock()
        try:
            source = self._resolve(request.source_path)
            destination = self._resolve(request.destination_path)
            if not destination.parent.is_dir() or self._is_link_or_reparse(destination.parent):
                raise ArchiveContractError(ArchiveErrorCode.LINK_ANOMALY, "锁后目标父目录复核失败")
            rows = self._read_ledger()
            try:
                authorization = self.policy.authorization_for(request)
            except Exception as exc:
                raise ArchiveContractError(
                    ArchiveErrorCode.AUTHORIZATION_QUERY_FAILED, "锁后授权复核失败"
                ) from exc
            try:
                open_changes = self.policy.open_change_ids(request.project_id)
            except Exception as exc:
                raise ArchiveContractError(
                    ArchiveErrorCode.CHG_QUERY_FAILED, "锁后变更复核失败"
                ) from exc
            plan = build_archive_plan(
                request,
                self._facts(request, source, destination, rows, authorization, open_changes, True),
            )
            if request.operation is ArchiveOperation.RESTORE:
                self._restore_entry(rows, request)
            return self._execute_locked(plan, rows, source, destination)
        finally:
            os.close(descriptor)
            lock.unlink(missing_ok=True)

    def _execute_locked(
        self,
        plan: ArchivePlan,
        rows: list[dict[str, str]],
        source: Path,
        destination: Path,
    ) -> ArchiveResult:
        request = plan.request
        archive_code = (
            self._allocate_archive_code(rows)
            if request.operation is ArchiveOperation.ARCHIVE
            else request.archive_code
        )
        phase_file = self._phase_file(source, request.project_id)
        phase_before = phase_file.read_bytes()
        original_phase = self._read_phase(phase_file)
        ledger_path = self._resolve(self.LEDGER_PATH)
        ledger_before = ledger_path.read_bytes() if ledger_path.exists() else None
        tx = self.transactions.begin(request.project_id, request.change_id)
        compensations: list[tuple[str, object]] = []
        try:
            tx.backup_file(phase_file)
            if ledger_path.exists():
                tx.backup_file(ledger_path)
            else:
                tx.track_created_file(ledger_path)
            shutil.move(str(source), str(destination))
            compensations.append(("move", (destination, source)))

            moved_phase = destination / phase_file.name
            compensations.append(("pm_session", (moved_phase, phase_before)))
            phase = "archived"
            if request.operation is ArchiveOperation.RESTORE:
                phase = self._restore_entry(rows, request).get("original_phase", "developing")
            self._set_phase(moved_phase, phase)

            compensations.append(("ledger", ledger_before))
            if request.operation is ArchiveOperation.ARCHIVE:
                rows.append(
                    {
                        "request_id": request.request_id,
                        "project_id": request.project_id,
                        "operation": request.operation.value,
                        "archive_code": archive_code,
                        "source_path": request.source_path,
                        "destination_path": request.destination_path,
                        "original_phase": original_phase,
                        "status": "archived",
                        "result": "completed",
                    }
                )
            else:
                restored = self._restore_entry(rows, request)
                restored["status"] = "restored"
                rows.append(
                    {
                        "request_id": request.request_id,
                        "project_id": request.project_id,
                        "operation": request.operation.value,
                        "archive_code": archive_code,
                        "source_path": request.source_path,
                        "destination_path": request.destination_path,
                        "status": "restored",
                        "result": "completed",
                    }
                )
            self._write_ledger(rows)

            compensations.append(("database", None))
            self.database.apply(request.operation, request.project_id)
            compensations.append(("scanner", None))
            self.scanner.apply(request.operation, request.project_id)
            tx.commit()
        except Exception as exc:
            errors = self._compensate(compensations, request, ledger_path)
            if tx.status is TransactionStatus.ACTIVE and not errors:
                try:
                    tx.commit()
                except Exception as cleanup_exc:
                    errors.append(f"transaction_cleanup: {cleanup_exc}")
            elif tx.status is TransactionStatus.FAILED:
                errors.append("transaction_commit_failed")
            if errors:
                raise ArchiveExecutionError(
                    f"归档执行失败且补偿不完整: {exc}; {'; '.join(errors)}",
                    str(tx.backup_dir),
                ) from exc
            raise ArchiveExecutionError(f"归档执行失败，已完成反向补偿: {exc}") from exc
        return ArchiveResult(
            request.request_id,
            request.project_id,
            request.operation,
            archive_code,
            request.source_path,
            request.destination_path,
            False,
        )

    def _compensate(
        self,
        compensations: list[tuple[str, object]],
        request: ArchiveRequest,
        ledger_path: Path,
    ) -> list[str]:
        errors: list[str] = []
        for name, payload in reversed(compensations):
            try:
                if name == "scanner":
                    self.scanner.compensate(request.operation, request.project_id)
                elif name == "database":
                    self.database.compensate(request.operation, request.project_id)
                elif name == "ledger":
                    if payload is None:
                        ledger_path.unlink(missing_ok=True)
                    else:
                        ledger_path.write_bytes(payload if isinstance(payload, bytes) else b"")
                elif name == "pm_session":
                    path, content = cast(tuple[Path, bytes], payload)
                    Path(path).write_bytes(content)
                elif name == "move":
                    moved, original = cast(tuple[Path, Path], payload)
                    Path(original).parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(moved), str(original))
            except Exception as exc:
                errors.append(f"{name}: {exc}")
        return errors

    def list_archived(self) -> tuple[dict[str, str], ...]:
        """Return an immutable snapshot of currently archived ledger entries."""
        return tuple(dict(row) for row in self._read_ledger() if row.get("status") == "archived")
