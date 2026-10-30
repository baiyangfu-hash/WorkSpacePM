"""The documents an implementation card cites as its basis are read as strict UTF-8; a bad byte is a finding, never quoted as evidence."""

from __future__ import annotations

from pathlib import Path

from auto_pm.application.core.implementation_card_basis import (
    BC_RECORD,
    CHANGE_CABINET,
    REQ_DRAWER,
    CardHeader,
    _basis_rule,
)

PID = "SW-2026-901"
BAD = b"\xff"


def _header(*basis: str) -> CardHeader:
    return CardHeader(basis=basis, basis_raw=(", ".join(basis),), change=(), predecessors=(), state="")


def _findings(root: Path, project: Path, *basis: str) -> list[str]:
    monitor = project / "04_监控"
    return [f.message for f in _basis_rule(_header(*basis), project, monitor, root, PID)]


def test_a_business_change_record_with_a_bad_byte_is_not_used_as_basis(tmp_path: Path) -> None:
    project = tmp_path / f"{PID}_demo"
    record = project / "04_监控" / CHANGE_CABINET / Path(*BC_RECORD)
    record.parent.mkdir(parents=True)
    table = "| 编号 | 状态 | 提出时间 |\n|---|---|---|\n| BC-SW-2026-901-001 | 已批 | 2026-10-01 |\n"
    record.write_bytes(table.encode() + b"remark " + BAD + b"\n")

    assert _findings(tmp_path, project, "BC-SW-2026-901-001") == ["业务变更记录表不是合法 UTF-8，不能当依据"]
    record.write_bytes(table.encode())
    assert _findings(tmp_path, project, "BC-SW-2026-901-001") == []  # the same table without the bad byte passes


def test_a_confirmed_requirement_checklist_with_a_bad_byte_is_not_used_as_basis(tmp_path: Path) -> None:
    project = tmp_path / f"{PID}_demo"
    sheet = project / REQ_DRAWER / "REQ-SW-2026-901-2026_10_001_demo.md"
    sheet.parent.mkdir(parents=True)
    confirmed = "> 状态：已确认\n\n| 确认的版本 | V1 |\n"
    sheet.write_bytes(confirmed.encode() + BAD + b"\n")

    assert _findings(tmp_path, project, "REQ-SW-2026-901-2026_10_001 V1") == ["需求核对单不是合法 UTF-8，不能当依据"]
    sheet.write_bytes(confirmed.encode())
    assert _findings(tmp_path, project, "REQ-SW-2026-901-2026_10_001 V1") == []


def test_a_requirement_document_with_a_bad_byte_cannot_vouch_for_an_item(tmp_path: Path) -> None:
    project = tmp_path / f"{PID}_demo"
    document = project / "docs" / "req.md"
    document.parent.mkdir(parents=True)
    document.write_bytes("FUNC-1 说明 ".encode() + BAD + b"\n")

    messages = _findings(tmp_path, project, "docs/req.md", "FUNC-1")

    assert "需求说明不是合法 UTF-8，不能当依据" in messages
    assert any("找不到" in message for message in messages)
