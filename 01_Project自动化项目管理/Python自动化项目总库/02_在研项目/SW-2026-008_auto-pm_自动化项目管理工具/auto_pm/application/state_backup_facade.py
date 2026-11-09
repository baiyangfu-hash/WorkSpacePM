"""Application-layer entry for the ledger's off-site backup (``pm state-backup``).

The command-line layer may not import the infrastructure layer directly (TD-SW008-058: ui -> application -> domain -> contracts);
this module is the one place it goes through.  It adds no logic: the work is in ``auto_pm.infrastructure.state_backup``.
"""

from __future__ import annotations

from auto_pm.infrastructure.state_backup import (
    PullResult,
    PushResult,
    StateBackupError,
    StateBackupService,
    StateBackupStatus,
    read_state_backup_status,
)

__all__ = [
    "PullResult",
    "PushResult",
    "StateBackupError",
    "StateBackupService",
    "StateBackupStatus",
    "read_state_backup_status",
]
