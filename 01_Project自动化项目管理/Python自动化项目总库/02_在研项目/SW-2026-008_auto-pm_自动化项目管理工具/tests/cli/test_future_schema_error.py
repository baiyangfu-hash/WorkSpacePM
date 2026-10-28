"""账本 schema 比程序新时，命令行给一行中文错误，而不是一屏 traceback（TD-SW008-161）。"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest
from auto_pm.cli.__main__ import cli
from auto_pm.core.work_registry_service import WorkRegistryService
from click.testing import CliRunner

import auto_pm.infrastructure.continuity_store as store_module

# These tests are about something other than the runtime identity; their fixtures have no registered project anchor.
pytestmark = pytest.mark.usefixtures("identity_guard_off")


def _repository(root: Path) -> None:
    subprocess.run(["git", "-C", str(root), "init"], check=True, capture_output=True)
    (root / ".gitignore").write_text(".auto-pm/\n", encoding="utf-8")
    (root / "README.md").write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=T",
            "-c",
            "user.email=t@example.invalid",
            "commit",
            "-m",
            "baseline",
        ],
        check=True,
        capture_output=True,
    )


def test_a_ledger_newer_than_the_program_gives_one_chinese_line_and_exit_1(
    cli_runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repository(tmp_path)
    WorkRegistryService(tmp_path).initialize("test")
    db = tmp_path / ".auto-pm" / "continuity.db"
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    monkeypatch.setattr(
        store_module,
        "_KNOWN_SCHEMA_VERSIONS",
        store_module._KNOWN_SCHEMA_VERSIONS - {"continuity-store.v8"},
    )

    result = cli_runner.invoke(
        cli,
        [
            "-w",
            str(tmp_path),
            "continuity",
            "work",
            "create",
            "--work-id",
            "WORK-X",
            "--pid",
            "SW-TEST-001",
            "--kind",
            "GOVERNANCE",
            "--title",
            "t",
            "--owner",
            "o",
            "--scope",
            "README.md",
            "--idempotency-key",
            "k",
            "--read-only",
        ],
    )

    assert result.exit_code == 1
    assert "未知或未来 Continuity Store schema" in result.output
    assert "Traceback" not in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
