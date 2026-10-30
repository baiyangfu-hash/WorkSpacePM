"""The figure consistency check reads documents as strict UTF-8: a bad byte is a reported problem, never silently repaired."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import figure_consistency_check as fig  # noqa: E402

FLOW = "# 流程\n\n```mermaid\nflowchart TD\n    A[开始] --> B[结束]\n```\n"
TABLE = "| 名字 | 类型 |\n|---|---|\n| `bStart` | BOOL |\n"


def test_a_diagram_document_with_a_bad_byte_is_reported(tmp_path: Path) -> None:
    flow = tmp_path / "f.md"
    flow.write_text(FLOW, encoding="utf-8")
    assert not any(f.kind == "parse" for f in fig.check_documents([flow], [], []))  # clean file: no parse problem
    flow.write_bytes(FLOW.encode() + b"\xff\n")

    findings = fig.check_documents([flow], [], [])

    assert any(f.kind == "parse" and "不是合法 UTF-8" in f.message for f in findings)


def test_a_table_document_with_a_bad_byte_is_reported(tmp_path: Path) -> None:
    flow = tmp_path / "f.md"
    flow.write_text(FLOW, encoding="utf-8")
    table = tmp_path / "i.md"
    table.write_bytes(TABLE.encode() + b"| `x` | \xff |\n")

    findings = fig.check_documents([flow], [table], [])

    assert any(f.kind == "parse" and f.file == table.as_posix() and "不是合法 UTF-8" in f.message for f in findings)
