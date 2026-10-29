"""失败证据日志读不懂时：读侧不当作“没有失败”，写侧不覆盖旧证据（TD-237 余项）。"""

from __future__ import annotations

import json
from pathlib import Path

from auto_pm.application.core.ai_handoff_service import AiHandoffService

REQ = "REQ-FAIL-1"


def _service(tmp_path: Path) -> tuple[AiHandoffService, Path]:
    service = AiHandoffService(tmp_path)
    service.failure_dir.mkdir(parents=True)
    return service, service.failure_dir / f"{REQ}.json"


def test_a_missing_log_means_no_failures_but_an_unreadable_one_is_shown_as_a_failure(tmp_path: Path) -> None:
    service, path = _service(tmp_path)
    assert service.list_failure_events(REQ) == []

    for bad in (b"\xff\xfe", b"{not json"):
        path.write_bytes(bad)
        events = service.list_failure_events(REQ)
        assert len(events) == 1 and events[0]["error_type"] == "FailureLogUnreadable"
        assert REQ in events[0]["error"]

    path.write_text(json.dumps({"events": [{"event_id": "a"}]}), encoding="utf-8")
    assert service.list_failure_events(REQ) == [{"event_id": "a"}]


def test_recording_a_failure_keeps_an_unreadable_old_log_aside_instead_of_overwriting_it(tmp_path: Path) -> None:
    service, path = _service(tmp_path)
    old = b'{"events": [{"event_id": "precious"}]' + b"\xff"
    path.write_bytes(old)

    service._record_failure(REQ, RuntimeError("boom"), phase="close")

    kept = list(service.failure_dir.glob(f"{REQ}.corrupt-*.json"))
    assert len(kept) == 1 and kept[0].read_bytes() == old  # the old evidence survives byte for byte
    events = json.loads(path.read_text(encoding="utf-8"))["events"]
    assert [e["error_type"] for e in events] == ["FailureLogUnreadable", "RuntimeError"]
    assert kept[0].name in events[0]["error"]


def test_recording_a_failure_appends_to_a_readable_log_without_moving_anything(tmp_path: Path) -> None:
    service, path = _service(tmp_path)
    path.write_text(json.dumps({"schema_version": "handoff.failure.v1", "request_id": REQ, "events": [{"event_id": "first"}]}), encoding="utf-8")

    service._record_failure(REQ, RuntimeError("boom"), phase="close")

    assert list(service.failure_dir.glob("*.corrupt-*")) == []
    assert [e["event_id"] for e in json.loads(path.read_text(encoding="utf-8"))["events"]][0] == "first"
    assert len(service.list_failure_events(REQ)) == 2


def test_a_log_with_the_wrong_shape_is_unreadable_too_and_is_kept_aside_on_write(tmp_path: Path) -> None:
    service, path = _service(tmp_path)
    for index, text in enumerate(('[1, 2, 3]', '{"events": "boom", "note": "keep me"}')):
        path.write_text(text, encoding="utf-8")
        events = service.list_failure_events(REQ)
        assert len(events) == 1 and events[0]["error_type"] == "FailureLogUnreadable"

        service._record_failure(REQ, RuntimeError("boom"), phase="close")
        kept = sorted(service.failure_dir.glob(f"{REQ}.corrupt-*.json"))
        assert len(kept) == index + 1
        assert text in {k.read_text(encoding="utf-8") for k in kept}  # 原内容原样留底
        assert [e["error_type"] for e in json.loads(path.read_text(encoding="utf-8"))["events"]] == [
            "FailureLogUnreadable",
            "RuntimeError",
        ]


def test_a_bad_byte_inside_a_string_value_is_not_silently_replaced(tmp_path: Path) -> None:
    """替换成 U+FFFD 后仍是合法 JSON，证据已被改动却显示正常——必须按读不懂处理。"""
    service, path = _service(tmp_path)
    old = b'{"events": [{"event_id": "a", "error": "caf\\xff"}]}'.replace(b"\\xff", b"\xff")
    path.write_bytes(old)
    assert old.decode("utf-8", errors="replace")  # 前提：替换后本是合法文本
    assert json.loads(old.decode("utf-8", errors="replace"))["events"]

    events = service.list_failure_events(REQ)
    assert len(events) == 1 and events[0]["error_type"] == "FailureLogUnreadable"

    service._record_failure(REQ, RuntimeError("boom"), phase="close")
    kept = list(service.failure_dir.glob(f"{REQ}.corrupt-*.json"))
    assert len(kept) == 1 and kept[0].read_bytes() == old
