"""The closure saga backs files up and restores them as strict UTF-8 (audit 368 item 4, batch 2).

Before, a file with invalid bytes was read with ``errors="replace"`` for the backup and written back the same way on
rollback, so the rollback permanently turned the bad bytes into U+FFFD.  Now such a file stops the step before anything is
modified, and a saga log with invalid bytes is treated as unreadable instead of being parsed after silent repair.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_pm.application.core.pm_saga_service import PmClosureSagaCoordinator


def test_backup_of_a_file_with_invalid_bytes_is_refused_before_anything_is_changed(tmp_path: Path) -> None:
    coordinator = PmClosureSagaCoordinator(tmp_path)
    target = tmp_path / "CHG-1.md"
    target.write_bytes("变更单 中文\n".encode("gbk"))
    saga_data: dict = {}
    with pytest.raises(UnicodeDecodeError):
        coordinator._backup_file(saga_data, target)
    assert not saga_data.get("backup_files")
    assert target.read_bytes() == "变更单 中文\n".encode("gbk")


def test_backup_and_rollback_round_trip_a_utf8_file_exactly(tmp_path: Path) -> None:
    coordinator = PmClosureSagaCoordinator(tmp_path)
    target = tmp_path / "CHG-2.md"
    original = "| 变更状态 | draft |\n中文 ä ö 日本語\n"
    target.write_text(original, encoding="utf-8", newline="\n")
    saga_data: dict = {"request_id": "REQ-STRICT-1"}
    coordinator._backup_file(saga_data, target)
    target.write_text("changed\n", encoding="utf-8")
    coordinator._save_saga_log(saga_data)
    coordinator.compensate_saga("REQ-STRICT-1")
    assert target.read_bytes() == original.encode("utf-8")


def test_rollback_keeps_crlf_line_endings_byte_for_byte(tmp_path: Path) -> None:
    coordinator = PmClosureSagaCoordinator(tmp_path)
    target = tmp_path / "CHG-3.md"
    original = "| 变更状态 | draft |\r\n中文\r\n".encode()
    target.write_bytes(original)
    saga_data: dict = {"request_id": "REQ-STRICT-3"}
    coordinator._backup_file(saga_data, target)
    target.write_bytes(b"changed\n")
    coordinator._save_saga_log(saga_data)
    coordinator.compensate_saga("REQ-STRICT-3")
    assert target.read_bytes() == original


def test_saga_log_with_invalid_bytes_is_unreadable_not_repaired(tmp_path: Path) -> None:
    coordinator = PmClosureSagaCoordinator(tmp_path)
    coordinator.saga_log_dir.mkdir(parents=True, exist_ok=True)
    log = coordinator.saga_log_path("REQ-STRICT-2")
    # valid JSON once the bad byte is "repaired": exactly the case that used to slip through
    log.write_bytes(b'{"request_id": "REQ-STRICT-2", "backup_files": {"x": "a\xff"}}')
    assert coordinator._load_saga_log("REQ-STRICT-2") is None
    log.write_bytes(json.dumps({"request_id": "REQ-STRICT-2"}).encode())
    assert coordinator._load_saga_log("REQ-STRICT-2") == {"request_id": "REQ-STRICT-2"}
