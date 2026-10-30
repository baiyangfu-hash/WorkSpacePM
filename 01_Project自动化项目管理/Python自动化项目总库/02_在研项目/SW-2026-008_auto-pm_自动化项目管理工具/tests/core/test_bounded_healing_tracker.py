"""有界自愈计数文件读不懂时按“次数用完”处理，不能当成“还没重试过”而放开无限重试。"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from auto_pm.domain.spec.services.fix_svc import BoundedHealingTracker


def _tracker(tmp_path: Path) -> BoundedHealingTracker:
    workspace = tmp_path / "SW-2026-901_demo"
    workspace.mkdir()
    return BoundedHealingTracker(workspace)


def test_three_retries_then_refused(tmp_path: Path) -> None:
    tracker = _tracker(tmp_path)
    assert [tracker.check_and_record() for _ in range(4)] == [True, True, True, False]


@pytest.mark.parametrize("content", [b"{not json", b"\xff\xfe", b"[1, 2]", b'{"last_reset": 0}', b'{"retries": "0"}'])
def test_unreadable_tracker_counts_as_exhausted(tmp_path: Path, content: bytes) -> None:
    tracker = _tracker(tmp_path)
    tracker.tracker_file.parent.mkdir(parents=True)
    tracker.tracker_file.write_bytes(content)

    assert tracker.check_and_record() is False
    assert tracker.tracker_file.read_bytes() == content  # 拒绝时不改写坏文件，留给人看


def test_unreadable_tracker_recovers_after_a_day(tmp_path: Path) -> None:
    tracker = _tracker(tmp_path)
    tracker.tracker_file.parent.mkdir(parents=True)
    tracker.tracker_file.write_bytes(b"{not json")
    old = time.time() - 90000
    os.utime(tracker.tracker_file, (old, old))

    assert tracker.check_and_record() is True
    assert json.loads(tracker.tracker_file.read_text(encoding="utf-8"))["retries"] == 1
