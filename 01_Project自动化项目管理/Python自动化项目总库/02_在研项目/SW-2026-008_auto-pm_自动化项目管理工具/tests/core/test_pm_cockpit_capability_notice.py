"""V05-B2 / TD-071 card 3: the cockpit says parking is supported on the command line and pre-emption is not, from the one shared producer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from auto_pm.core.continuity_query_service import ContinuityQueryService
from auto_pm.core.pm_cockpit_service import PmCockpitService

from auto_pm.contracts.continuity_query import ActionCapability, QueriedAction, RuntimeCapabilities
from tests.core.test_pm_cockpit_dual_root import PROJECT, _roots, _work


def test_the_snapshot_says_parking_is_supported_and_preemption_is_not(tmp_path: Path) -> None:
    main, _candidate = _roots(tmp_path)
    _work(main, "WORK-CAP-001")
    notices = PmCockpitService(main).snapshot().notices
    assert notices, "the snapshot carries no notice at all"
    notice = notices[-1]
    assert "挂起与拿回：支持" in notice and "pm switch" in notice and "插队：不支持" in notice
    assert "未能确认" not in notice


def test_the_notice_follows_the_shared_producer_and_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    main, _candidate = _roots(tmp_path)
    _work(main, "WORK-CAP-002")
    monkeypatch.setattr(ContinuityQueryService, "capabilities", staticmethod(lambda: RuntimeCapabilities(contract_version="runtime-capabilities.v2", actions=())))
    notices = PmCockpitService(main).snapshot().notices
    assert notices, "the snapshot carries no notice at all"
    notice = notices[-1]
    assert "未能确认" in notice and "保持停用" in notice
    assert "支持" not in notice.replace("未能确认", "")


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


@pytest.mark.parametrize("error", [RuntimeError("boom"), OSError("disk"), KeyError("k"), AttributeError("a"), TypeError("t")])
def test_any_exception_from_the_producer_fails_closed_not_only_type_and_value_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    """卡 060 写的是“生产者抛错时快照不崩”，不是只有 TypeError/ValueError（TD-SW008-094 ②）。"""
    main, _candidate = _roots(tmp_path)
    _work(main, "WORK-CAP-ANY")

    def broken() -> RuntimeCapabilities:
        raise error

    monkeypatch.setattr(ContinuityQueryService, "capabilities", staticmethod(broken))
    notice = PmCockpitService(main).snapshot().notices[-1]
    assert "未能确认" in notice and "保持停用" in notice and "挂起与拿回：支持" not in notice


def test_the_query_block_is_built_from_the_same_producer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    main, _candidate = _roots(tmp_path)
    _work(main, "WORK-CAP-004")
    only_park = RuntimeCapabilities(contract_version="runtime-capabilities.v2", actions=(ActionCapability(action=QueriedAction.PARK),))
    monkeypatch.setattr(ContinuityQueryService, "capabilities", staticmethod(lambda: only_park))
    answered = ContinuityQueryService(main).query(project_id=PROJECT)
    assert answered.query is not None
    assert answered.query.capabilities == only_park


def test_the_notice_follows_the_other_notices_and_creates_nothing(tmp_path: Path) -> None:
    main, _candidate = _roots(tmp_path)  # no continuity store yet
    notices = PmCockpitService(main).snapshot().notices
    assert "未建立连续性记录" in notices[0]
    assert len(notices) == 2 and "挂起与拿回：支持" in notices[-1]
    assert not (main / ".auto-pm").exists()


@pytest.mark.parametrize(("name", "version", "expect_unsupported"), [("valid", "runtime-capabilities.v2", True), ("missing", None, False), ("old", "runtime-capabilities.v1", False), ("empty", "", False)])
def test_a_capability_block_without_a_valid_version_is_not_taken_as_unsupported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, version: str | None, expect_unsupported: bool
) -> None:
    main, _candidate = _roots(tmp_path)
    _work(main, f"WORK-CAP-V-{name.upper()}")
    fields: dict[str, Any] = dict(ContinuityQueryService.capabilities().model_dump(exclude={"contract_version"}))  # everything else is exactly what the real producer declares
    fields["actions"] = ContinuityQueryService.capabilities().actions
    if version is not None:
        fields["contract_version"] = version
    block = RuntimeCapabilities.model_construct(**fields)  # never validated: only the cockpit's own check can refuse it
    monkeypatch.setattr(ContinuityQueryService, "capabilities", staticmethod(lambda: block))
    notice = PmCockpitService(main).snapshot().notices[-1]
    if expect_unsupported:
        assert "挂起与拿回：支持" in notice and "未能确认" not in notice  # the control: the same block with a legal version is read as before
    else:
        assert "未能确认" in notice and "保持停用" in notice and "挂起与拿回：支持" not in notice


def test_a_v2_block_that_does_not_declare_parking_is_not_shown_as_supported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    main, _candidate = _roots(tmp_path)
    _work(main, "WORK-CAP-NOPARK")
    all_unsupported = RuntimeCapabilities(contract_version="runtime-capabilities.v2", actions=tuple(ActionCapability(action=action) for action in QueriedAction))
    monkeypatch.setattr(ContinuityQueryService, "capabilities", staticmethod(lambda: all_unsupported))
    notice = PmCockpitService(main).snapshot().notices[-1]
    assert "未能确认" in notice and "挂起与拿回：支持" not in notice


def test_a_keyboard_interrupt_from_the_producer_still_propagates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """宽捕获只到 Exception：用户中断不能被吞成“未能确认”（审计 326 的漏网变异：放宽成 BaseException）。"""
    main, _candidate = _roots(tmp_path)
    _work(main, "WORK-CAP-KI")

    def interrupted() -> RuntimeCapabilities:
        raise KeyboardInterrupt

    monkeypatch.setattr(ContinuityQueryService, "capabilities", staticmethod(interrupted))
    with pytest.raises(KeyboardInterrupt):
        PmCockpitService(main).snapshot()


def test_a_failing_producer_leaves_a_warning_in_the_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """宽捕获把程序错误变成永久“未能确认”，所以必须留一行带堆栈的 warning 供排查（审计 326 P3）。"""
    main, _candidate = _roots(tmp_path)
    _work(main, "WORK-CAP-LOG")

    def broken() -> RuntimeCapabilities:
        raise RuntimeError("renamed symbol")

    monkeypatch.setattr(ContinuityQueryService, "capabilities", staticmethod(broken))
    with caplog.at_level("WARNING"):
        PmCockpitService(main).snapshot()
    assert any(r.levelname == "WARNING" and r.exc_info and "renamed symbol" in str(r.exc_info[1]) for r in caplog.records)
