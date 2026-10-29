"""JSON files that decide something (lease wallet, backup manifest, isolation marker) are read as strict UTF-8: a bad byte is a refusal, not a repaired value."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from auto_pm.infrastructure import lease_wallet
from auto_pm.infrastructure.continuity_backup import manifest_path, verify_backup_file
from auto_pm.infrastructure.local_executor import (
    ISOLATION_MARKER,
    ISOLATION_SCHEMA_VERSION,
    LocalCodexExecutor,
    LocalExecutionError,
    LocalExecutionRequest,
)

# Valid JSON whose string value holds a lone 0xFF byte: with errors="replace" it parses, with strict decoding it cannot.
BAD_VALUE = b'"\xff"'


def test_a_lease_wallet_with_a_bad_byte_is_refused_not_repaired(tmp_path: Path) -> None:
    wallet = lease_wallet.wallet_path(tmp_path, "RUN-1")
    wallet.parent.mkdir(parents=True)
    wallet.write_bytes(
        b'{"schema_version": "lease-wallet.v1", "run_id": "RUN-1", "owner_id": "a", "lease_token": ' + BAD_VALUE + b"}"
    )

    with pytest.raises(lease_wallet.LeaseWalletError, match="无法读取"):
        lease_wallet.find(tmp_path, "RUN-1")


def test_a_backup_manifest_with_a_bad_byte_is_reported_as_unreadable(tmp_path: Path) -> None:
    backup = tmp_path / "continuity-x.db"
    backup.write_bytes(b"not a database at all" * 100)
    manifest_path(backup).write_bytes(b'{"sha256": ' + BAD_VALUE + b"}")

    report = verify_backup_file(backup)

    assert not report.ok
    assert any("无法读取" in finding and "清单文件" in finding for finding in report.findings)


def test_an_isolation_marker_with_a_bad_byte_is_refused(tmp_path: Path) -> None:
    repository = tmp_path / "microtask"
    repository.mkdir()
    (repository / ISOLATION_MARKER).write_bytes(
        b'{"schema_version": ' + json.dumps(ISOLATION_SCHEMA_VERSION).encode() + b', "note": ' + BAD_VALUE + b"}"
    )
    for arguments in (
        ("init",),
        ("add", "."),
        ("-c", "user.name=T", "-c", "user.email=t@example.invalid", "commit", "-m", "baseline"),
    ):
        subprocess.run(["git", "-C", str(repository), *arguments], check=True, capture_output=True)
    executor = LocalCodexExecutor(command_prefix=(sys.executable, "-c", "pass"))
    request = LocalExecutionRequest(
        repository=repository,
        allowed_paths=("allowed.txt",),
        model="gpt-5.6-terra",
        prompt="write allowed",
        timeout_seconds=2,
        output_limit_bytes=4_096,
        sensitive_values=(),
    )

    with pytest.raises(LocalExecutionError, match="isolation marker is not valid JSON"):
        executor.execute(request)
