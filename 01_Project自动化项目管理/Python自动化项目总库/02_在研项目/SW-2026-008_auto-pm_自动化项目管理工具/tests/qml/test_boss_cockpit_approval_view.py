"""U09C: the cockpit shows the pending scope card and one button approves it and starts the work.

QML is loaded through the real Qt engine; the end-to-end test drives boss_main.qml with the real bridge, service and a real
child process. Scenario ids v01..v07 follow card 040 section 5.4.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QRunnable, Qt, QThreadPool
from PySide6.QtQml import QQmlEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from auto_pm.ui.qml.bridges.pm_cockpit_bridge import PmCockpitBridge
from tests.qml.test_boss_cockpit_view import _QML, _items_named, _load, _QtMessages, _texts
from tests.qml.test_pm_cockpit_approval_bridge import _REQUEST, _VERIFIED, _cockpit

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

_HASH = "0123456789abcdef" * 4


class _InlinePool:
    """Runs every worker on the calling thread.

    The end-to-end fixture injects a Facade built on the test thread, and its SQLite connections must stay on that
    thread. (Production builds the Facade inside the worker, so this limit is a property of the fixture only.)
    """

    def start(self, worker: QRunnable, priority: int = 0) -> None:
        del priority
        worker.run()

    def waitForDone(self, _milliseconds: int = -1) -> bool:
        return True


def _card(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "project_id": "SW-2026-008",
        "project_name": "自动化项目管理工具",
        "request_id": "REQ-COCKPIT-0123456789ABCDEF0123456789ABCDEF",
        "plan_hash": _HASH,
        "revision": 1,
        "objective": "让驾驶舱能批准范围",
        "acceptance_criteria": ["批准后自动开始", "只确认两次"],
        "scope_paths": ["auto_pm/a.py", "tests/test_a.py"],
        "risks": ["范围漂移"],
        "non_goals": ["不改文档"],
        "executor": "codex · gpt-approved",
        "submitted_by": "PM (Claude)",
        "submitted_at": "2026-10-02T00:00:00+00:00",
        "approver": "fubai",
        "can_approve": True,
        "approve_blocked_reason": "",
    }
    payload.update(changes)
    return payload


def _component(engine: QQmlEngine, qapp: QApplication, card: dict[str, object]) -> QQuickItem:
    item = cast(QQuickItem, _load(engine, _QML / "components" / "PendingScopeCard.qml"))
    item.setProperty("card", card)
    qapp.processEvents()
    return item


def _view(engine: QQmlEngine, qapp: QApplication, cards: list[dict[str, object]]) -> QQuickItem:
    view = cast(QQuickItem, _load(engine, _QML / "views" / "BossCockpitView.qml"))
    view.setProperty("pendingCards", cards)
    qapp.processEvents()
    return view


def _call(view: QQuickItem, name: str, *args: object) -> None:
    assert QMetaObject.invokeMethod(
        cast(QObject, view),
        name,
        Qt.ConnectionType.DirectConnection,
        *[Q_ARG("QVariant", arg) for arg in args],
    )


# --------------------------------------------------------------------------- v: the component and the view


def test_v01_the_card_shows_everything_the_user_must_judge_and_no_internal_identifier(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    with _QtMessages() as warnings:
        item = _component(qml_engine, qapp, _card())
    texts = " ".join(_texts(item))

    for expected in (
        "待您批准的范围 · 自动化项目管理工具",
        "第 1 版",
        "让驾驶舱能批准范围",
        "批准后自动开始；只确认两次",
        "auto_pm/a.py；tests/test_a.py",
        "范围漂移",
        "不改文档",
        "codex · gpt-approved（独立工作树）",
        "PM (Claude)",
        "批准人：fubai",
        "批准范围并开始",
    ):
        assert expected in texts
    assert _HASH not in texts and "REQ-COCKPIT" not in texts
    assert not re.search(r"[0-9a-f]{32,}", texts)
    assert [message for message in warnings if "qml" in message.lower()] == []


def test_v02_a_blocked_card_disables_the_button_and_states_the_reason(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    reason = "未配置批准人，不能批准；请先设置环境变量 AUTO_PM_COCKPIT_APPROVER。"
    blocked = _component(
        qml_engine, qapp, _card(approver="", can_approve=False, approve_blocked_reason=reason)
    )
    open_task = _component(
        qml_engine,
        qapp,
        _card(can_approve=False, approve_blocked_reason="项目已有未终结的任务；请先验收或取消它，再批准新的范围卡。"),
    )
    ready = _component(qml_engine, qapp, _card())

    assert _items_named(blocked, "approveScopeButton")[0].property("enabled") is False
    assert _items_named(blocked, "approveBlockedReason")[0].property("visible") is True
    assert reason in _texts(blocked)
    assert "批准人：未配置" in _texts(blocked)
    assert _items_named(open_task, "approveScopeButton")[0].property("enabled") is False
    assert "项目已有未终结的任务" in " ".join(_texts(open_task))
    assert _items_named(ready, "approveScopeButton")[0].property("enabled") is True
    assert _items_named(ready, "approveBlockedReason")[0].property("visible") is False


def test_v03_the_view_renders_one_card_per_pending_request(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    other = _card(request_id="REQ-COCKPIT-FEDCBA9876543210FEDCBA9876543210", plan_hash="f" * 64, objective="第二个目标")
    view = _view(qml_engine, qapp, [_card(), other])

    assert len(_items_named(view, "approveScopeButton")) == 2
    texts = " ".join(_texts(view))
    assert "让驾驶舱能批准范围" in texts and "第二个目标" in texts
    empty = _view(qml_engine, qapp, [])
    assert _items_named(empty, "approveScopeButton") == []


def test_v04_a_click_emits_once_with_the_handle_and_is_busy_until_cleared(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    view = _view(qml_engine, qapp, [_card()])
    requested: list[tuple[str, str]] = []
    cast(Any, view).scopeApprovalConfirmed.connect(lambda rid, h: requested.append((str(rid), str(h))))
    button = _items_named(view, "approveScopeButton")[0]
    request_id = str(_card()["request_id"])

    assert QMetaObject.invokeMethod(button, "clicked")
    assert QMetaObject.invokeMethod(button, "clicked")
    qapp.processEvents()

    assert requested == [(request_id, _HASH)]
    assert button.property("enabled") is False
    assert button.property("text") == "正在批准并启动…"

    _call(view, "setApproveBusy", request_id, False)
    qapp.processEvents()
    assert button.property("enabled") is True
    assert button.property("text") == "批准范围并开始"
    assert QMetaObject.invokeMethod(button, "clicked")
    assert requested == [(request_id, _HASH), (request_id, _HASH)]


def test_v05_an_approved_card_stays_busy_until_it_leaves_the_list_and_a_refusal_frees_it(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    view = _view(qml_engine, qapp, [_card()])
    button = _items_named(view, "approveScopeButton")[0]
    assert QMetaObject.invokeMethod(button, "clicked")
    qapp.processEvents()
    assert button.property("enabled") is False

    # The snapshot that still lists the card (an unrelated refresh) must not free the button.
    view.setProperty("pendingCards", [_card()])
    qapp.processEvents()
    assert _items_named(view, "approveScopeButton")[0].property("enabled") is False

    # The next snapshot no longer lists it: the busy flag is forgotten, so a card with the same id is clickable again.
    view.setProperty("pendingCards", [])
    qapp.processEvents()
    assert _items_named(view, "approveScopeButton") == []
    view.setProperty("pendingCards", [_card()])
    qapp.processEvents()
    assert _items_named(view, "approveScopeButton")[0].property("enabled") is True


def test_v05_boss_main_wires_the_one_button_to_the_bridge_and_its_result() -> None:
    main_source = (_QML / "boss_main.qml").read_text(encoding="utf-8", errors="replace")
    view_source = (_QML / "views" / "BossCockpitView.qml").read_text(encoding="utf-8", errors="replace")
    card_source = (_QML / "components" / "PendingScopeCard.qml").read_text(encoding="utf-8", errors="replace")

    assert "pendingCards: root.snapshot.pending_cards || []" in main_source
    assert "onScopeApprovalConfirmed: function(requestId, planHash)" in main_source
    assert "pmCockpitBridge.approveScopeAndStart(requestId, planHash)" in main_source
    assert "cockpitView.setApproveBusy(requestId, false)" in main_source
    assert "function onScopeApprovalFinished(requestId, success, message)" in main_source
    assert "if (!success)\n                cockpitView.setApproveBusy(requestId, false)" in main_source
    assert "onPendingCardsChanged:" in view_source
    assert "signal scopeApprovalConfirmed(string requestId, string planHash)" in view_source
    assert "if (!requestId || !planHash || isApproveBusy(requestId))" in view_source
    assert "Components.PendingScopeCard" in view_source
    assert "批准范围并开始" in card_source
    for source in (main_source, view_source, card_source):
        assert "TextField" not in source.split("提出新目标")[0] or source is not card_source
        assert "plan_hash" not in card_source.replace("card.plan_hash", "")


def test_v06_one_click_in_boss_main_approves_starts_and_hands_over_to_acceptance(
    qapp: QApplication, qml_engine: QQmlEngine, tmp_path: Path
) -> None:
    cockpit = _cockpit(tmp_path)
    bridge = PmCockpitBridge(
        str(cockpit.root), service=cockpit.service, thread_pool=cast(QThreadPool, _InlinePool())
    )
    finished: list[tuple[str, bool, str]] = []
    bridge.scopeApprovalFinished.connect(lambda rid, ok, msg: finished.append((str(rid), bool(ok), str(msg))))
    qml_engine.rootContext().setContextProperty("pmCockpitBridge", bridge)
    window = cast(QObject, _load(qml_engine, _QML / "boss_main.qml"))
    root_item = cast(Any, window).contentItem()

    def pump(until: object, rounds: int = 1500) -> None:
        for _ in range(rounds):
            qapp.processEvents()
            bridge._poll_snapshot_worker()
            bridge._poll_approve_workers()
            if cast(Any, until)():
                return
            QTest.qWait(10)
        raise AssertionError("condition was not reached")

    def buttons() -> list[QQuickItem]:
        return _items_named(root_item, "approveScopeButton")

    pump(lambda: bool(buttons()) and buttons()[0].property("enabled") is True)
    assert cockpit.count("planning_draft_decision_bindings") == 0
    assert QMetaObject.invokeMethod(buttons()[0], "clicked")
    qapp.processEvents()
    assert buttons()[0].property("enabled") is False

    # The status sentence is cleared by the next snapshot (as for start and closure), so the signal is the proof.
    pump(lambda: bool(finished))
    pump(lambda: not buttons() and "确认验收" in _texts(root_item))

    assert finished == [(_REQUEST, True, _VERIFIED)]

    assert cockpit.count("planning_draft_decision_bindings") == 1
    assert cockpit.starts() == 1
    assert "批准范围并开始" not in _texts(root_item)
    assert "正在批准并启动…" not in _texts(root_item)
    bridge.stopSnapshotRefresh()


def test_v07_an_unconfigured_approver_shows_a_disabled_button_and_how_to_fix_it(
    qapp: QApplication, qml_engine: QQmlEngine, tmp_path: Path
) -> None:
    cockpit = _cockpit(tmp_path, approver="")
    bridge = PmCockpitBridge(str(cockpit.root), service=cockpit.service)
    qml_engine.rootContext().setContextProperty("pmCockpitBridge", bridge)
    window = cast(QObject, _load(qml_engine, _QML / "boss_main.qml"))
    root_item = cast(Any, window).contentItem()

    for _ in range(1500):
        qapp.processEvents()
        bridge._poll_snapshot_worker()
        if _items_named(root_item, "approveScopeButton"):
            break
        QTest.qWait(10)
    button = _items_named(root_item, "approveScopeButton")[0]

    assert button.property("enabled") is False
    assert "AUTO_PM_COCKPIT_APPROVER" in " ".join(_texts(root_item))
    assert cockpit.count("planning_draft_decision_bindings") == 0
    bridge.stopSnapshotRefresh()
    assert bridge._thread_pool.waitForDone(10_000)
