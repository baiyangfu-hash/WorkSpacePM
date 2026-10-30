"""A closure that fails in the cockpit must say why and what to do next, never stay silent."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from auto_pm.application.core.pm_closure_service import PmClosureError
from auto_pm.application.core.pm_cockpit_service import (
    PmCockpitError,
    closure_failure_message,
    ledger_busy,
)
from auto_pm.contracts.pm_cockpit import PmCockpitCompletionState
from auto_pm.infrastructure.continuity_store import ContinuityStoreError
from tests.core.test_pm_closure_service import _MISSION_ID as _CLOSE_MISSION
from tests.core.test_pm_closure_service import _lineage_states
from tests.core.test_pm_cockpit_service import _closing_cockpit

_NEXT_STEP = "请关闭驾驶舱窗口，再由主执行重试收口。"


def _chained(outer: BaseException, inner: BaseException) -> BaseException:
    try:
        try:
            raise inner
        except BaseException as error:
            raise outer from error
    except BaseException as caught:
        return caught


@pytest.mark.parametrize(
    "error",
    [
        sqlite3.OperationalError("attempt to write a readonly database"),
        sqlite3.OperationalError("database is locked"),
        PermissionError(13, "Permission denied"),
        ContinuityStoreError("Continuity Store BUSY: 无法取得稳定只读快照"),
    ],
)
def test_td_closure_alert_a_read_only_or_locked_ledger_is_named_as_such(error: BaseException) -> None:
    assert ledger_busy(error) is True
    assert ledger_busy(_chained(PmClosureError("写入失败"), error)) is True
    message = closure_failure_message(_chained(RuntimeError("wrapped"), error))
    assert message.startswith("收尾失败：账本正被占用")
    assert _NEXT_STEP in message


@pytest.mark.parametrize(
    "error",
    [sqlite3.OperationalError("disk I/O error"), RuntimeError("boom"), ValueError("x")],
)
def test_td_closure_alert_other_failures_still_carry_a_next_step(error: BaseException) -> None:
    assert ledger_busy(error) is False
    message = closure_failure_message(error)
    assert message.startswith("收尾失败：读写账本时出错")
    assert _NEXT_STEP in message
    assert str(error) not in message


def test_td_closure_alert_a_cyclic_exception_chain_terminates() -> None:
    first, second = RuntimeError("a"), RuntimeError("b")
    first.__cause__, second.__cause__ = second, first
    assert ledger_busy(first) is False


def test_td_closure_alert_a_read_only_ledger_during_closure_returns_a_failure_with_a_next_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _store, database, _reconciler = _closing_cockpit(tmp_path, monkeypatch)
    closure = service._closure_service
    assert closure is not None

    def read_only(*_args: object, **_kwargs: object) -> object:
        raise sqlite3.OperationalError("attempt to write a readonly database")

    monkeypatch.setattr(closure, "complete_closure", read_only)

    result = service.close_accepted(_CLOSE_MISSION)

    assert result.state is PmCockpitCompletionState.PENDING_SYNC
    assert result.message.startswith("收尾失败：账本正被占用（只读或被锁）")
    assert "验收记录已保存" in result.message and _NEXT_STEP in result.message
    assert _lineage_states(database)[2] == "ACCEPTED"


def test_td_closure_alert_a_closure_refusal_caused_by_a_lock_is_not_reported_as_missing_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _store, _database, _reconciler = _closing_cockpit(tmp_path, monkeypatch)
    closure = service._closure_service
    assert closure is not None

    def locked(*_args: object, **_kwargs: object) -> object:
        raise _chained(PmClosureError("Continuity Store 写入失败"), sqlite3.OperationalError("database is locked"))

    monkeypatch.setattr(closure, "prepare_closure", locked)

    result = service.close_accepted(_CLOSE_MISSION)

    assert result.state is PmCockpitCompletionState.PENDING_SYNC
    assert "账本正被占用" in result.message
    assert "必要证据" not in result.message


def test_td_closure_alert_a_locked_ledger_on_the_first_read_raises_the_busy_sentence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, store, _database, _reconciler = _closing_cockpit(tmp_path, monkeypatch)

    def locked(_mission_id: str) -> object:
        raise _chained(ContinuityStoreError("Continuity Store 严格只读查询失败"), sqlite3.OperationalError("database is locked"))

    monkeypatch.setattr(store, "get_mission", locked)

    with pytest.raises(PmCockpitError, match="账本正被占用") as caught:
        service.close_accepted(_CLOSE_MISSION)
    assert _NEXT_STEP in str(caught.value)
