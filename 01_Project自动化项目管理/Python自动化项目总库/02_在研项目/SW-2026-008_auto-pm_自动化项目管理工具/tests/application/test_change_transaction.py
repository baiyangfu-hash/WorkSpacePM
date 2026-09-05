"""Fail-closed containment and rollback tests for ``ChangeTransaction``."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from auto_pm.application.core.change_transaction import (
    ChangeTransactionManager,
    TransactionFileError,
    TransactionStateError,
)
from auto_pm.contracts.workflow_dtos import TransactionStatus


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    return root


@pytest.fixture
def manager(workspace: Path) -> ChangeTransactionManager:
    return ChangeTransactionManager(workspace)


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class TestChangeTransactionContainment:
    def test_relative_file_is_canonicalized_and_snapshotted(
        self, manager: ChangeTransactionManager, workspace: Path
    ) -> None:
        target = _write(workspace / "src" / "main.py", "initial")
        tx = manager.begin("PROJ", "CHG", tx_id="TX-ONE")

        backup = tx.backup_file("src/main.py")

        assert backup == workspace / ".auto-pm" / "transactions" / "TX-ONE" / "src" / "main.py"
        assert backup.read_text(encoding="utf-8") == "initial"
        assert tx.backups == {target.resolve(): backup.resolve()}

    def test_outside_absolute_path_is_rejected(
        self, manager: ChangeTransactionManager, tmp_path: Path
    ) -> None:
        target = _write(tmp_path / "outside" / "secret.txt", "secret")

        with pytest.raises(TransactionFileError, match="超出工作区"):
            manager.begin("PROJ", "CHG").backup_file(target)

    @pytest.mark.parametrize("path", ["../outside.txt", "src/../outside.txt"])
    def test_parent_traversal_is_rejected(
        self, manager: ChangeTransactionManager, path: str
    ) -> None:
        with pytest.raises(TransactionFileError, match="禁止包含"):
            manager.begin("PROJ", "CHG").track_created_file(path)

    def test_symlink_component_is_rejected(self, manager: ChangeTransactionManager, workspace: Path, tmp_path: Path) -> None:
        outside = tmp_path / "outside"
        _write(outside / "secret.txt", "secret")
        link = workspace / "linked"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            # Some Windows policy profiles disallow symlink creation.  Exercise
            # the same fail-closed branch through a controlled reparse-point
            # fault injection so this safety gate remains covered everywhere.
            link.mkdir()
            with patch.object(Path, "is_symlink", autospec=True, side_effect=lambda item: item == link):
                with pytest.raises(TransactionFileError, match="symlink/reparse"):
                    manager.begin("PROJ", "CHG").track_created_file(link / "secret.txt")
            return

        with pytest.raises(TransactionFileError, match="symlink/reparse"):
            manager.begin("PROJ", "CHG").backup_file(link / "secret.txt")

    def test_external_backup_base_and_transaction_id_are_rejected(
        self, workspace: Path, tmp_path: Path
    ) -> None:
        with pytest.raises(TransactionFileError, match="超出工作区"):
            ChangeTransactionManager(workspace, backup_base_dir=tmp_path / "backups")
        with pytest.raises(TransactionFileError, match="非法事务标识"):
            ChangeTransactionManager(workspace).begin("PROJ", "CHG", tx_id="../escape")


class TestChangeTransactionBackup:
    def test_absolute_path_inside_workspace_is_snapshotted(
        self, manager: ChangeTransactionManager, workspace: Path
    ) -> None:
        target = _write(workspace / "config.json", "{}")
        tx = manager.begin("PROJ", "CHG", tx_id="TX-ABS")

        backup = tx.backup_file(target)

        assert backup.read_text(encoding="utf-8") == "{}"
        assert target.resolve() in tx.backups

    def test_first_snapshot_is_preserved_and_backup_registration_is_idempotent(
        self, manager: ChangeTransactionManager, workspace: Path
    ) -> None:
        target = _write(workspace / "module.py", "baseline")
        tx = manager.begin("PROJ", "CHG")

        first = tx.backup_file(target)
        target.write_text("modified", encoding="utf-8")
        second = tx.backup_file(target)

        assert first == second
        assert second.read_text(encoding="utf-8") == "baseline"

    def test_missing_file_and_snapshot_io_failure_are_explicit(
        self, manager: ChangeTransactionManager, workspace: Path
    ) -> None:
        tx = manager.begin("PROJ", "CHG")
        with pytest.raises(FileNotFoundError):
            tx.backup_file("missing.txt")

        target = _write(workspace / "target.txt", "content")
        with patch("auto_pm.application.core.change_transaction.shutil.copy2", side_effect=OSError("disk full")):
            with pytest.raises(TransactionFileError, match="创建文件快照失败"):
                tx.backup_file(target)
        assert tx.backups == {}

    def test_track_created_is_idempotent(self, manager: ChangeTransactionManager, workspace: Path) -> None:
        tx = manager.begin("PROJ", "CHG")

        tx.track_created_file("docs/readme.md")
        tx.track_created_file(workspace / "docs" / "readme.md")

        assert tx.created_files == [(workspace / "docs" / "readme.md").resolve()]


class TestChangeTransactionRollback:
    def test_rollback_restores_files_removes_registered_paths_and_cleans_backup(
        self, manager: ChangeTransactionManager, workspace: Path
    ) -> None:
        original = _write(workspace / "source.txt", "before")
        created_dir = workspace / "created"
        created_file = _write(created_dir / "new.txt", "new")
        tx = manager.begin("PROJ", "CHG")
        tx.backup_file(original)
        original.write_text("after", encoding="utf-8")
        tx.track_created_file(created_file)
        tx.track_created_file(created_dir)

        tx.rollback("injected workflow failure")

        assert original.read_text(encoding="utf-8") == "before"
        assert not created_dir.exists()
        assert not tx.backup_dir.exists()
        assert tx.status is TransactionStatus.ROLLED_BACK

    def test_restore_failure_is_failed_raises_and_retains_backup(
        self, manager: ChangeTransactionManager, workspace: Path
    ) -> None:
        original = _write(workspace / "source.txt", "before")
        tx = manager.begin("PROJ", "CHG")
        tx.backup_file(original)
        original.write_text("after", encoding="utf-8")

        with patch("auto_pm.application.core.change_transaction.shutil.copy2", side_effect=OSError("denied")):
            with pytest.raises(TransactionFileError, match="回滚未完成"):
                tx.rollback("restore failure")

        assert tx.status is TransactionStatus.FAILED
        assert tx.backup_dir.exists()
        assert original.read_text(encoding="utf-8") == "after"

    def test_missing_backup_is_failed_raises_and_retains_backup_directory(
        self, manager: ChangeTransactionManager, workspace: Path
    ) -> None:
        original = _write(workspace / "source.txt", "before")
        tx = manager.begin("PROJ", "CHG")
        snapshot = tx.backup_file(original)
        snapshot.unlink()

        with pytest.raises(TransactionFileError, match="备份快照缺失"):
            tx.rollback("snapshot loss")

        assert tx.status is TransactionStatus.FAILED
        assert tx.backup_dir.exists()

    def test_created_path_cleanup_failure_is_failed_and_retains_backup(
        self, manager: ChangeTransactionManager, workspace: Path
    ) -> None:
        original = _write(workspace / "source.txt", "before")
        created = _write(workspace / "created.txt", "new")
        tx = manager.begin("PROJ", "CHG")
        tx.backup_file(original)
        tx.track_created_file(created)

        with patch.object(Path, "unlink", side_effect=OSError("locked")):
            with pytest.raises(TransactionFileError, match="删除新建路径失败"):
                tx.rollback("cleanup failure")

        assert tx.status is TransactionStatus.FAILED
        assert tx.backup_dir.exists()
        assert created.exists()

    def test_backup_directory_cleanup_failure_is_failed_and_not_rolled_back(
        self, manager: ChangeTransactionManager, workspace: Path
    ) -> None:
        original = _write(workspace / "source.txt", "before")
        tx = manager.begin("PROJ", "CHG")
        tx.backup_file(original)

        with patch("auto_pm.application.core.change_transaction.shutil.rmtree", side_effect=OSError("locked")):
            with pytest.raises(TransactionFileError, match="清理备份目录失败"):
                tx.rollback("backup cleanup failure")

        assert tx.status is TransactionStatus.FAILED
        assert tx.backup_dir.exists()

    def test_context_manager_propagates_rollback_failure(
        self, manager: ChangeTransactionManager, workspace: Path
    ) -> None:
        original = _write(workspace / "source.txt", "before")
        tx = manager.begin("PROJ", "CHG")
        tx.backup_file(original)
        original.write_text("after", encoding="utf-8")
        with patch("auto_pm.application.core.change_transaction.shutil.copy2", side_effect=OSError("denied")):
            with pytest.raises(TransactionFileError, match="回滚未完成"):
                with tx:
                    raise RuntimeError("workflow failure")

        assert tx.status is TransactionStatus.FAILED
        assert tx.backup_dir.exists()


class TestChangeTransactionCompletion:
    def test_commit_keeps_changes_and_cleans_backup(self, manager: ChangeTransactionManager, workspace: Path) -> None:
        original = _write(workspace / "source.txt", "before")
        tx = manager.begin("PROJ", "CHG")
        tx.backup_file(original)
        original.write_text("after", encoding="utf-8")

        tx.commit()

        assert original.read_text(encoding="utf-8") == "after"
        assert not tx.backup_dir.exists()
        assert tx.status is TransactionStatus.COMMITTED

    def test_commit_cleanup_failure_is_failed_and_retains_backup(
        self, manager: ChangeTransactionManager, workspace: Path
    ) -> None:
        original = _write(workspace / "source.txt", "before")
        tx = manager.begin("PROJ", "CHG")
        tx.backup_file(original)

        with patch("auto_pm.application.core.change_transaction.shutil.rmtree", side_effect=OSError("locked")):
            with pytest.raises(TransactionFileError, match="快照已保留"):
                tx.commit()

        assert tx.status is TransactionStatus.FAILED
        assert tx.backup_dir.exists()

    def test_terminal_states_reject_follow_up_operations(
        self, manager: ChangeTransactionManager, workspace: Path
    ) -> None:
        target = _write(workspace / "source.txt", "before")
        committed = manager.begin("PROJ", "CHG")
        committed.commit()
        failed = manager.begin("PROJ", "CHG")
        failed.backup_file(target)
        with patch("auto_pm.application.core.change_transaction.shutil.rmtree", side_effect=OSError("locked")):
            with pytest.raises(TransactionFileError):
                failed.commit()

        for tx in (committed, failed):
            with pytest.raises(TransactionStateError):
                tx.backup_file(target)
            with pytest.raises(TransactionStateError):
                tx.track_created_file(target)
            with pytest.raises(TransactionStateError):
                tx.commit()
            with pytest.raises(TransactionStateError):
                tx.rollback()
