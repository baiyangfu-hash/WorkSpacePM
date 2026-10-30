"""A handoff request file with a bad byte is invalid, not repaired; the atomic writers are strict on the encoding side."""

from __future__ import annotations

import json
from pathlib import Path

from auto_pm.application.core.ai_handoff_service import AiHandoffService


def _payload(note: str) -> dict[str, str]:
    return {
        "request_id": "REQ-STRICT-1",
        "project_id": "SW-2026-901",
        "executor_skill": "fullstack-engineer",
        "summary": "demo",
        "note": note,
    }


def test_a_handoff_file_with_a_bad_byte_is_not_a_valid_handoff(tmp_path: Path) -> None:
    service = AiHandoffService(tmp_path)
    path = tmp_path / "REQ-STRICT-1.json"
    path.write_text(json.dumps(_payload("ok")), encoding="utf-8")
    assert service._read_valid(path) is not None  # the same file without the bad byte is valid

    path.write_bytes(json.dumps(_payload("@@")).encode().replace(b"@@", b"\xff"))

    assert service._read_valid(path) is None
