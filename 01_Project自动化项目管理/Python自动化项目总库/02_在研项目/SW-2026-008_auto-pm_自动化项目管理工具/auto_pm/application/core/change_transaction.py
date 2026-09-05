"""Fail-closed file transaction support for the workflow execution boundary.

The transaction only accepts paths physically contained in its workspace.  It
keeps the backup directory intact whenever recovery cannot be proven complete.
"""

from __future__ import annotations

import logging
import shutil
import uuid
from contextlib import AbstractContextManager
from datetime import datetime
from pathlib import Path
from types import TracebackType

from auto_pm.contracts.workflow_dtos import TransactionStatus
from auto_pm.infrastructure.logging.audit import audit_log

logger = logging.getLogger(__name__)

__all__ = [
    "ChangeTransaction",
    "ChangeTransactionManager",
    "TransactionError",
    "TransactionFileError",
    "TransactionStateError",
]

_FILE_ATTRIBUTE_REPARSE_POINT = 0x0400


class TransactionError(Exception):
    """Base error for file transaction operations."""


class TransactionStateError(TransactionError):
    """Raised when an operation is invalid for the transaction state."""


class TransactionFileError(TransactionError):
    """Raised when containment or durable file recovery cannot be proven."""


def _is_reparse_point(path: Path) -> bool:
    """Return whether *path* is a Windows reparse point without following it."""
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT)


def _canonical_workspace_path(workspace_root: Path, path: str | Path) -> Path:
    """Resolve a path only when it is lexically and physically in the workspace.

    ``..`` is rejected before resolution.  Every existing component under the
    workspace is also checked for symlink/reparse indirection, then the final
    canonical path is checked again.  This prevents a managed operation from
    escaping the workspace through a junction or a link.
    """
    requested = Path(path)
    if ".." in requested.parts:
        raise TransactionFileError(f"禁止包含 '..' 的事务路径: {path}")

    candidate = requested if requested.is_absolute() else workspace_root / requested
    try:
        lexical_relative = candidate.relative_to(workspace_root)
    except ValueError as exc:
        raise TransactionFileError(f"事务路径超出工作区: {path}") from exc

    current = workspace_root
    for part in lexical_relative.parts:
        current = current / part
        if current.exists() and (current.is_symlink() or _is_reparse_point(current)):
            raise TransactionFileError(f"事务路径包含 symlink/reparse point: {path}")

    resolved = candidate.resolve()
    try:
        resolved.relative_to(workspace_root)
    except ValueError as exc:
        raise TransactionFileError(f"事务路径解析后超出工作区: {path}") from exc
    return resolved


class ChangeTransaction(AbstractContextManager["ChangeTransaction"]):
    """A fail-closed workspace-contained file transaction."""

    def __init__(
        self,
        tx_id: str,
        project_id: str,
        change_id: str,
        workspace_root: Path,
        backup_dir: Path,
    ) -> None:
        self.tx_id = tx_id
        self.project_id = project_id
        self.change_id = change_id
        self.workspace_root = Path(workspace_root).resolve()
        if not self.workspace_root.is_dir():
            raise TransactionFileError(f"工作区不存在或不是目录: {self.workspace_root}")
        self.backup_dir = _canonical_workspace_path(self.workspace_root, backup_dir)
        self.status = TransactionStatus.ACTIVE
        self.backups: dict[Path, Path] = {}
        self.created_files: list[Path] = []

    def _resolve_path(self, path: str | Path) -> Path:
        """Return the canonical workspace-contained path or fail closed."""
        return _canonical_workspace_path(self.workspace_root, path)

    def _require_active(self, operation: str) -> None:
        if self.status != TransactionStatus.ACTIVE:
            raise TransactionStateError(
                f"事务 {self.tx_id} 当前状态为 {self.status.value}，禁止执行 {operation}"
            )

    def _audit(self, event: str, **details: object) -> None:
        """Keep audit failure from obscuring a file-safety failure."""
        try:
            audit_log(
                event,
                tx_id=self.tx_id,
                project_id=self.project_id,
                change_id=self.change_id,
                **details,
            )
        except Exception:  # pragma: no cover - audit backend is an external boundary
            logger.exception("事务审计日志写入失败: %s", event)

    def _fail_rollback(self, reason: str, errors: list[str]) -> None:
        """Mark failure, retain snapshots, audit it, and surface recovery failure."""
        self.status = TransactionStatus.FAILED
        self._audit(
            "change_transaction_rollback_failed",
            reason=reason,
            errors=errors,
            backup_dir=str(self.backup_dir),
        )
        raise TransactionFileError("事务回滚未完成，快照已保留以供人工恢复: " + "; ".join(errors))

    def backup_file(self, path: str | Path) -> Path:
        """Create the initial snapshot of an existing regular workspace file."""
        self._require_active("备份文件")
        target = self._resolve_path(path)
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(f"原文件不存在，无法创建备份快照: {target}")
        if target in self.backups:
            return self.backups[target]

        relative = target.relative_to(self.workspace_root)
        backup_path = self._resolve_path(self.backup_dir / relative)
        try:
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup_path)
        except OSError as exc:
            logger.exception("创建文件快照失败 %s -> %s", target, backup_path)
            raise TransactionFileError(f"创建文件快照失败: {target} -> {exc}") from exc

        self.backups[target] = backup_path
        return backup_path

    def track_created_file(self, path: str | Path) -> None:
        """Register a workspace-contained path that rollback must remove."""
        self._require_active("登记新建文件")
        target = self._resolve_path(path)
        if target not in self.created_files:
            self.created_files.append(target)

    def rollback(self, reason: str = "") -> None:
        """Restore snapshots and remove registered paths, or fail closed.

        The status becomes ``ROLLED_BACK`` only after every restoration, every
        cleanup action, and backup-directory cleanup succeeds.  Any failure
        leaves the backup directory in place, sets ``FAILED``, and raises.
        """
        self._require_active("rollback")
        errors: list[str] = []

        for original, backup in self.backups.items():
            try:
                original = self._resolve_path(original)
                backup = self._resolve_path(backup)
                if not backup.is_file():
                    raise TransactionFileError(f"备份快照缺失: {backup}")
                original.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, original)
            except (OSError, TransactionFileError) as exc:
                logger.exception("回滚恢复文件失败: %s -> %s", backup, original)
                errors.append(f"恢复文件失败 {original}: {exc}")

        for created in sorted(self.created_files, key=lambda item: len(item.parts), reverse=True):
            try:
                created = self._resolve_path(created)
                if created.is_symlink() or created.is_file():
                    created.unlink(missing_ok=True)
                elif created.is_dir():
                    shutil.rmtree(created)
            except (OSError, TransactionFileError) as exc:
                logger.exception("回滚清理新建路径失败: %s", created)
                errors.append(f"删除新建路径失败 {created}: {exc}")

        if errors:
            self._fail_rollback(reason, errors)

        try:
            if self.backup_dir.exists():
                shutil.rmtree(self.backup_dir)
        except OSError as exc:
            self._fail_rollback(reason, [f"清理备份目录失败 {self.backup_dir}: {exc}"])

        self.status = TransactionStatus.ROLLED_BACK
        self._audit(
            "change_transaction_rollback",
            reason=reason,
            restored_count=len(self.backups),
            deleted_count=len(self.created_files),
            errors=[],
        )

    def commit(self) -> None:
        """Finalize a transaction only after snapshot cleanup is confirmed."""
        self._require_active("commit")
        try:
            if self.backup_dir.exists():
                shutil.rmtree(self.backup_dir)
        except OSError as exc:
            self.status = TransactionStatus.FAILED
            self._audit(
                "change_transaction_commit_failed",
                errors=[f"清理备份目录失败 {self.backup_dir}: {exc}"],
                backup_dir=str(self.backup_dir),
            )
            raise TransactionFileError(f"提交清理快照失败，快照已保留: {exc}") from exc

        self.status = TransactionStatus.COMMITTED
        self._audit(
            "change_transaction_commit",
            backed_up_count=len(self.backups),
            created_count=len(self.created_files),
        )

    def __enter__(self) -> ChangeTransaction:
        self._require_active("进入上下文")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool | None:
        if exc_type is not None:
            if self.status == TransactionStatus.ACTIVE:
                self.rollback(reason=str(exc_val))
            return False
        if self.status == TransactionStatus.ACTIVE:
            self.commit()
        return None


class ChangeTransactionManager:
    """Factory for fail-closed workspace-contained transactions."""

    def __init__(
        self,
        workspace_root: str | Path = ".",
        backup_base_dir: str | Path | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        if not self.workspace_root.is_dir():
            raise TransactionFileError(f"工作区不存在或不是目录: {self.workspace_root}")
        requested_base = (
            self.workspace_root / ".auto-pm" / "transactions"
            if backup_base_dir is None
            else Path(backup_base_dir)
        )
        self.backup_base_dir = _canonical_workspace_path(self.workspace_root, requested_base)

    def begin(
        self,
        project_id: str,
        change_id: str,
        tx_id: str | None = None,
    ) -> ChangeTransaction:
        """Create an active transaction with a safe one-segment transaction id."""
        if not tx_id:
            tx_id = f"TX-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        tx_segment = Path(tx_id)
        if tx_segment.name != tx_id or tx_id in {"", ".", ".."}:
            raise TransactionFileError(f"非法事务标识: {tx_id}")
        return ChangeTransaction(
            tx_id=tx_id,
            project_id=project_id,
            change_id=change_id,
            workspace_root=self.workspace_root,
            backup_dir=self.backup_base_dir / tx_segment,
        )

    def transaction(
        self,
        project_id: str,
        change_id: str,
        tx_id: str | None = None,
    ) -> ChangeTransaction:
        """Return an active transaction usable as a context manager."""
        return self.begin(project_id=project_id, change_id=change_id, tx_id=tx_id)
