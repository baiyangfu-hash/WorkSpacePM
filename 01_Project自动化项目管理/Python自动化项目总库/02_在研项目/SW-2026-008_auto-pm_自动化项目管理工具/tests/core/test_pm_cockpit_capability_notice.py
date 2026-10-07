"""V05-B2: the cockpit tells the user that parking and pre-emption are not supported, from the one shared producer."""

from __future__ import annotations

from pathlib import Path

import pytest
from auto_pm.core.continuity_query_service import ContinuityQueryService
from auto_pm.core.pm_cockpit_service import PmCockpitService

from auto_pm.contracts.continuity_query import ActionCapability, QueriedAction, RuntimeCapabilities
from tests.core.test_pm_cockpit_dual_root import PROJECT, _roots, _work


def test_the_snapshot_says_parking_and_preemption_are_not_supported(tmp_path: Path) -> None:
    main, _candidate = _roots(tmp_path)
    _work(main, "WORK-CAP-001")
    notices = PmCockpitService(main).snapshot().notices
    assert notices, "the snapshot carries no notice at all"
    notice = notices[-1]
    assert "挂起" in notice and "插队" in notice and "不支持" in notice
    assert "未能确认" not in notice


def test_the_notice_follows_the_shared_producer_and_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    main, _candidate = _roots(tmp_path)
    _work(main, "WORK-CAP-002")
    monkeypatch.setattr(ContinuityQueryService, "capabilities", staticmethod(lambda: RuntimeCapabilities(actions=())))
    notices = PmCockpitService(main).snapshot().notices
    assert notices, "the snapshot carries no notice at all"
    notice = notices[-1]
    assert "未能确认" in notice and "保持停用" in notice
    assert "不支持" not in notice


def test_a_producer_that_raises_also_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    main, _candidate = _roots(tmp_path)
    _work(main, "WORK-CAP-003")

    def broken() -> RuntimeCapabilities:
        raise ValueError("the contract cannot be built")

    monkeypatch.setattr(ContinuityQueryService, "capabilities", staticmethod(broken))
    try:
        notices = PmCockpitService(main).snapshot().notices
    except ValueError as error:  # the snapshot must not break on a producer that raises
        notices = (f"snapshot raised: {error}",)
    notice = notices[-1]
    assert "未能确认" in notice and "不支持" not in notice


def test_the_query_block_is_built_from_the_same_producer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    main, _candidate = _roots(tmp_path)
    _work(main, "WORK-CAP-004")
    only_park = RuntimeCapabilities(actions=(ActionCapability(action=QueriedAction.PARK),))
    monkeypatch.setattr(ContinuityQueryService, "capabilities", staticmethod(lambda: only_park))
    answered = ContinuityQueryService(main).query(project_id=PROJECT)
    assert answered.query is not None
    assert answered.query.capabilities == only_park


def test_the_notice_follows_the_other_notices_and_creates_nothing(tmp_path: Path) -> None:
    main, _candidate = _roots(tmp_path)  # no continuity store yet
    notices = PmCockpitService(main).snapshot().notices
    assert "未建立连续性记录" in notices[0]
    assert len(notices) == 2 and "不支持" in notices[-1]
    assert not (main / ".auto-pm").exists()
