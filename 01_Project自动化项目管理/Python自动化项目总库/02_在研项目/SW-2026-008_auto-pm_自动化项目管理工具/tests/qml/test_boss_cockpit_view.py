"""Loadability checks for the isolated boss cockpit QML surface."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from time import monotonic
from typing import TYPE_CHECKING, Any, NoReturn, cast
from weakref import ref

import pytest
from auto_pm.change.ledger_reconciler import ReconcileDiff
from auto_pm.core.pm_closure_service import PmClosureService
from auto_pm.core.pm_cockpit_service import PmCockpitService
from PySide6.QtCore import (
    Q_ARG,
    QMetaObject,
    QObject,
    QRunnable,
    Qt,
    QThread,
    QThreadPool,
    QTimer,
    QtMsgType,
    QUrl,
    qInstallMessageHandler,
)
from PySide6.QtQml import QJSValue, QQmlComponent, QQmlEngine, QQmlError
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from shiboken6 import isValid

from auto_pm.infrastructure.continuity_store import ContinuityStore
from auto_pm.ui.qml.bridges.pm_cockpit_bridge import PmCockpitBridge
from tests.core.test_pm_closure_service import (
    _accepted_lineage,
    _lineage_states,
    _ProjectionReconciler,
)
from tests.core.test_pm_cockpit_service import _registry as _core_registry
from tests.core.test_pm_cockpit_service import _seed_authorized_mission
from tests.qml.conftest import (
    _assert_gui_thread,
    _delete_qobject,
    _managed_qml_engine,
    _own_qml_root,
    _register_qml_window,
)
from tests.qml.conftest import qml_engine as shared_qml_engine

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

    from auto_pm.contracts.pm_cockpit import PmCockpitSnapshot


_QML = Path(__file__).resolve().parents[2] / "auto_pm" / "ui" / "qml"
_WORKER_TEARDOWN_TIMEOUT_MS = 10_000
_TEARDOWN_FAILURE_EXIT_CODE = 86


@pytest.fixture
def qml_engine(qapp: QApplication) -> Iterator[QQmlEngine]:
    """Limit deterministic engine teardown to this module's managed loaders."""
    with _managed_qml_engine() as engine:
        yield engine


def _abort_stalled_teardown(pool: QThreadPool, timeout_ms: int) -> NoReturn:
    """Fail the current test process without unwinding live Qt worker owners."""
    try:
        print(
            f"QML_TEARDOWN_TIMEOUT timeout_ms={timeout_ms} "
            f"active_threads={pool.activeThreadCount()} pid={os.getpid()}",
            file=sys.stderr,
            flush=True,
        )
        sys.stdout.flush()
    finally:
        # SystemExit/pytest.fail would unwind the engine and may block in pool destruction.
        # This is a test-only, unrecoverable resource failure; never continue the suite.
        os._exit(_TEARDOWN_FAILURE_EXIT_CODE)


@contextmanager
def _managed_boss_window(
    engine: QQmlEngine,
    bridge: PmCockpitBridge,
    *,
    drain_timeout_ms: int = _WORKER_TEARDOWN_TIMEOUT_MS,
    destroy_bridge: bool = True,
) -> Iterator[QObject]:
    """Quiesce workers and destroy the window while its bridge and engine are alive."""
    _assert_gui_thread(engine, bridge)
    component = QQmlComponent(engine)
    component.setParent(engine)
    window: QObject | None = None
    try:
        engine.rootContext().setContextProperty("pmCockpitBridge", bridge)
        component.loadUrl(QUrl.fromLocalFile(str(_QML / "boss_main.qml")))
        assert not component.isError(), "\n".join(error.toString() for error in component.errors())
        window = component.create()
        assert window is not None
        yield window
    finally:
        # Stop producers before waiting; processing general events here can enqueue more work.
        _assert_gui_thread(engine, bridge, component)
        bridge.stopSnapshotRefresh()
        for timer in bridge.findChildren(QTimer):
            timer.stop()
        bridge.blockSignals(True)
        drained = bridge._thread_pool.waitForDone(drain_timeout_ms)
        if not drained:
            _abort_stalled_teardown(bridge._thread_pool, drain_timeout_ms)
        if window is not None:
            _delete_qobject(window)
        _delete_qobject(component)
        if destroy_bridge:
            _delete_qobject(bridge)


def _load(engine: QQmlEngine, path: Path) -> object:
    _assert_gui_thread(engine)
    if path.resolve() == (_QML / "boss_main.qml").resolve():
        bridge = engine.rootContext().contextProperty("pmCockpitBridge")
        assert isinstance(bridge, PmCockpitBridge), "boss_main.qml requires its context bridge"
        return _register_qml_window(
            engine, bridge, _managed_boss_window(engine, bridge, destroy_bridge=False)
        )
    component = QQmlComponent(engine)
    component.setParent(engine)
    value: QObject | None = None
    try:
        component.loadUrl(QUrl.fromLocalFile(str(path)))
        assert not component.isError(), "\n".join(error.toString() for error in component.errors())
        value = component.create()
        assert value is not None, "\n".join(error.toString() for error in component.errors())
        _own_qml_root(engine, value)
        component.setParent(value)
        return value
    except BaseException:
        if value is not None:
            _delete_qobject(value)
        _delete_qobject(component)
        raise


def test_boss_cockpit_components_load_without_the_legacy_workbench(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    files = (
        _QML / "components" / "PmConfirmationCard.qml",
        _QML / "components" / "WorkGraphView.qml",
        _QML / "components" / "EvidenceDrawer.qml",
        _QML / "components" / "ActivityTimeline.qml",
        _QML / "views" / "BossCockpitView.qml",
    )

    objects = [_load(qml_engine, path) for path in files]

    view = objects[-1]
    view.setProperty(  # type: ignore[attr-defined]
        "cards",
        [
            {
                "project_name": "自动化项目管理工具",
                "mission": "A4",
                "milestone": "等待开工确认",
                "progress": "准备中",
                "blocked": False,
                "verification": "待验证",
                "risk": "低",
                "current_owner": "PM",
                "next_user_action": "确认开始执行",
                "user_action": "CONFIRM_START",
                "mission_id": "MISSION-001",
                "project_id": "SW-2026-008",
            }
        ],
    )
    qapp.processEvents()
    assert view.property("cards") is not None  # type: ignore[attr-defined]


def test_start_wiring_is_async_busy_guarded_and_refreshes_after_success() -> None:
    view_source = (_QML / "views" / "BossCockpitView.qml").read_text(
        encoding="utf-8", errors="replace"
    )
    main_source = (_QML / "boss_main.qml").read_text(
        encoding="utf-8", errors="replace"
    )

    assert "startBusyByMission" in view_source
    assert "if (!missionId || isStartBusy(missionId))" in view_source
    assert "busy: root.isStartBusy(modelData.mission_id)" in view_source
    assert "pmCockpitBridge.startExecution(missionId)" in main_source
    assert "pmCockpitBridge.confirmStart(missionId)" not in main_source
    assert "function onStartFinished(missionId, success, message)" in main_source
    assert "if (success)\n                root.refreshSnapshot()" in main_source


def test_snapshot_refresh_is_async_bounded_and_preserves_last_success() -> None:
    main_source = (_QML / "boss_main.qml").read_text(
        encoding="utf-8", errors="replace"
    )
    view_source = (_QML / "views" / "BossCockpitView.qml").read_text(
        encoding="utf-8", errors="replace"
    )
    timeline_source = (_QML / "components" / "ActivityTimeline.qml").read_text(
        encoding="utf-8", errors="replace"
    )

    assert "pmCockpitBridge.requestSnapshot()" in main_source
    assert "pmCockpitBridge.loadSnapshot()" not in main_source
    assert "pmCockpitBridge.startSnapshotRefresh()" in main_source
    assert "property bool closesBridgeOnDestruction: true" in main_source
    assert "onClosing: function(close) {" in main_source
    assert main_source.count("pmCockpitBridge.beginShutdown()") == 2 and "pmCockpitBridge.stopSnapshotRefresh()" in main_source
    assert "function onSnapshotFinished(response)" in main_source
    assert "root.snapshot = response.snapshot" in main_source
    assert "activities: root.snapshot.activities || []" in main_source
    assert "Components.ActivityTimeline" in view_source
    assert "activities: root.activities" in view_source
    assert "PM_SESSION" not in timeline_source
    assert "modelData.description" in timeline_source
    assert "modelData.occurred_at" in timeline_source


def test_view_suppresses_start_replay_until_busy_is_cleared(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    view = cast(QObject, _load(qml_engine, _QML / "views" / "BossCockpitView.qml"))
    missions: list[str] = []
    qml_view = cast(Any, view)
    start_signal = qml_view.startConfirmed
    start_signal.connect(lambda mission_id: missions.append(str(mission_id)))

    assert QMetaObject.invokeMethod(
        view,
        "requestStart",
        Qt.ConnectionType.DirectConnection,
        Q_ARG("QVariant", "MISSION-001"),
    )
    assert QMetaObject.invokeMethod(
        view,
        "requestStart",
        Qt.ConnectionType.DirectConnection,
        Q_ARG("QVariant", "MISSION-001"),
    )
    qapp.processEvents()
    assert missions == ["MISSION-001"]

    assert QMetaObject.invokeMethod(
        view,
        "setStartBusy",
        Qt.ConnectionType.DirectConnection,
        Q_ARG("QVariant", "MISSION-001"),
        Q_ARG("QVariant", False),
    )
    assert QMetaObject.invokeMethod(
        view,
        "requestStart",
        Qt.ConnectionType.DirectConnection,
        Q_ARG("QVariant", "MISSION-001"),
    )
    qapp.processEvents()
    assert missions == ["MISSION-001", "MISSION-001"]


def test_boss_main_loads_through_the_read_only_bridge(
    qapp: QApplication, qml_engine: QQmlEngine, tmp_path: Path
) -> None:
    registry = tmp_path / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        json.dumps(
            {
                "schema_version": "workspace-registry.v1",
                "projects": [
                    {
                        "project_id": "SW-2026-008",
                        "project_root": "projects/SW-2026-008",
                        "development_root": "projects/SW-2026-008",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with _managed_boss_window(qml_engine, PmCockpitBridge(str(tmp_path))) as window:
        qapp.processEvents()
        assert window.property("title") == "我的驾驶舱"
        assert not (tmp_path / ".auto-pm").exists()


def test_boss_main_saves_planning_form_to_isolated_store(
    qapp: QApplication, qml_engine: QQmlEngine, tmp_path: Path
) -> None:
    registry = tmp_path / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        json.dumps({
            "schema_version": "workspace-registry.v1",
            "projects": [{
                "project_id": "SW-2026-008",
                "project_root": "projects/SW-2026-008",
                "development_root": "projects/SW-2026-008",
            }],
        }),
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "init"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    project_root = tmp_path / "projects" / "SW-2026-008"
    project_root.mkdir(parents=True)
    (project_root / ".copier-answers.yml").write_text(
        "project_id: SW-2026-008\nproject_name: Boss fixture\nstack: python\n",
        encoding="utf-8",
        errors="replace",
    )
    store = ContinuityStore(tmp_path)
    store.initialize("2026-09-28T00:00:00+00:00", "test")
    bridge = PmCockpitBridge(str(tmp_path))
    with _managed_boss_window(qml_engine, bridge) as window:
        refresh = bridge.startSnapshotRefresh()
        assert refresh["accepted"] or refresh["busy"], refresh
        assert bridge._thread_pool.waitForDone(5_000)
        bridge._poll_snapshot_worker()
        snapshot: dict[str, object] = {}
        for _ in range(100):
            qapp.processEvents()
            bridge._poll_snapshot_worker()
            raw_snapshot = cast(Any, window.property("snapshot"))
            snapshot = (
                raw_snapshot.toVariant()
                if hasattr(raw_snapshot, "toVariant")
                else cast(dict[str, object], raw_snapshot)
            )
            if snapshot["projects"]:
                break
            QTest.qWait(10)
        assert snapshot["projects"]
        objective = window.findChild(QObject, "planningObjective")
        acceptance = window.findChild(QObject, "planningAcceptance")
        save = window.findChild(QObject, "savePlanningDraft")
        kind = window.findChild(QObject, "planningKind")
        assert objective is not None and acceptance is not None and save is not None and kind is not None
        objective.setProperty("text", "Improve release verification")
        acceptance.setProperty("text", "All checks pass")
        qapp.processEvents()

        # TD-SW008-070: nothing is saved before the user has chosen what kind of request this is.
        assert kind.property("currentIndex") == -1
        assert save.property("enabled") is False
        kind.setProperty("currentIndex", 0)
        qapp.processEvents()
        assert save.property("enabled") is True

        assert QMetaObject.invokeMethod(save, "clicked")
        qapp.processEvents()

        draft = window.property("planningDraft")
        assert draft["project_id"] == "SW-2026-008"
        assert draft["objective"] == "Improve release verification"
        assert draft["acceptance_criteria"] == ["All checks pass"]
        assert draft["scope_status"] == "范围待规划"
        with sqlite3.connect(store.db_path) as conn:
            persisted = conn.execute(
                "SELECT subject_project_id, objective, acceptance_criteria_json, state "
                "FROM planning_drafts"
            ).fetchall()
        assert persisted == [
            ("SW-2026-008", "Improve release verification", '["All checks pass"]', "PRE_AUTH")
        ]


# --- U05: evidence drawer shows the same task, evidence currency and the next legal step -----


def _texts(item: QQuickItem) -> list[str]:
    """Collect every visible Text value below an item, in tree order."""
    found: list[str] = []
    for child in item.childItems():
        value = child.property("text")
        if isinstance(value, str):
            found.append(value)
        found.extend(_texts(child))
    return found


class _QtMessages:
    """Capture Qt/QML warnings raised while the drawer evaluates its bindings."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    def __enter__(self) -> list[str]:
        def handler(mode: QtMsgType, context: object, message: str) -> None:
            del mode, context
            self.messages.append(message)

        self._previous = qInstallMessageHandler(handler)
        return self.messages

    def __exit__(self, *_exc: object) -> None:
        qInstallMessageHandler(self._previous)


def _evidence_payload(
    currency: str | None, reason: str, action: str, resume_reason: str, state: str
) -> dict[str, object]:
    payload: dict[str, object] = {
        "project_id": "SW-2026-008",
        "decision_id": "DEC-20260910-1B4F38FD",
        "change_id": "CHG-SCPT-2026-207",
        "read_set": ["SYS-2026-001_WorkspaceGovernance/workspace_registry.json"],
        "work_graph": [],
        "checkpoints": [],
        "verification_evidence": [],
        "status_note": "证据来自不可变只读连续性记录；未读取或展示执行租约。",
        "focus": {
            "mission_id": "MISSION-001",
            "work_id": "WORK-001",
            "run_id": "RUN-001",
            "run_state": "验证中",
        },
        "resume": {"state": state, "user_action": action, "reason": resume_reason},
    }
    if currency is not None:
        payload["evidence_currency"] = currency
        payload["evidence_currency_reason"] = reason
    return payload


def _open_drawer(
    engine: QQmlEngine, payload: dict[str, object]
) -> tuple[QQuickItem, list[str]]:
    drawer = cast(QQuickItem, _load(engine, _QML / "components" / "EvidenceDrawer.qml"))
    with _QtMessages() as messages:
        assert QMetaObject.invokeMethod(drawer, "openEvidence", Q_ARG("QVariant", payload))
    return drawer, messages


def test_drawer_states_the_same_task_and_a_current_evidence_verdict(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    payload = _evidence_payload(
        "CURRENT", "", "CONFIRM_ACCEPTANCE", "验证证据与当前内容一致，可确认最终验收。", "WAITING_FOR_USER"
    )

    drawer, messages = _open_drawer(qml_engine, payload)
    qapp.processEvents()

    texts = "\n".join(_texts(drawer))
    assert drawer.property("opened") is True
    assert "需求：MISSION-001" in texts
    assert "根工作：WORK-001" in texts
    assert "运行：RUN-001（验证中）" in texts
    assert "与当前内容一致" in texts
    assert "验证证据与当前内容一致，可确认最终验收。  （确认最终验收）" in texts
    assert not [m for m in messages if "Error" in m or "Unable" in m]
    lowered = texts.lower()
    assert "lease" not in lowered and "token" not in lowered and "%" not in texts


def test_drawer_explains_why_evidence_is_not_current_and_offers_no_action_button(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    reason = "最新 Checkpoint 未证明当前通过的质量证据"
    payload = _evidence_payload(
        "NOT_CURRENT", reason, "REVIEW_ESCALATION", f"验收证据不能确认：{reason}", "NEEDS_REVIEW"
    )

    drawer, messages = _open_drawer(qml_engine, payload)
    qapp.processEvents()

    texts = "\n".join(_texts(drawer))
    assert f"与当前内容不一致或无法核验：{reason}" in texts
    assert f"验收证据不能确认：{reason}  （需要您查看并决策）" in texts
    assert "与当前内容一致" not in texts
    assert not [m for m in messages if "Error" in m or "Unable" in m]
    action_texts = {"确认开工", "确认最终验收", "启动", "重试", "恢复"}
    assert not (action_texts & set(_texts(drawer)))


def test_drawer_marks_not_applicable_evidence_with_its_reason(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    payload = _evidence_payload(
        "NOT_APPLICABLE", "尚未进入验收阶段，暂无需核验。", "NONE", "执行已启动，驾驶舱正在处理，无需操作。", "MONITORING"
    )

    drawer, messages = _open_drawer(qml_engine, payload)
    qapp.processEvents()

    texts = "\n".join(_texts(drawer))
    assert "无需核验：尚未进入验收阶段，暂无需核验。" in texts
    assert "执行已启动，驾驶舱正在处理，无需操作。  （无需操作）" in texts
    assert not [m for m in messages if "Error" in m or "Unable" in m]


def test_drawer_still_opens_with_a_pre_u05_payload(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    legacy: dict[str, object] = {
        "project_id": "SW-2026-008",
        "read_set": [],
        "work_graph": [],
        "checkpoints": [],
        "verification_evidence": [],
        "status_note": "只读。",
    }

    drawer, messages = _open_drawer(qml_engine, legacy)
    qapp.processEvents()

    texts = "\n".join(_texts(drawer))
    assert drawer.property("opened") is True
    assert "暂无进行中的需求。" in texts
    assert "暂无核验信息。" in texts
    assert "暂无下一步信息。" in texts
    assert not [m for m in messages if "Error" in m or "Unable" in m]


def test_boss_main_reads_evidence_in_the_background_only() -> None:
    main_source = (_QML / "boss_main.qml").read_text(encoding="utf-8", errors="replace")
    drawer_source = (_QML / "components" / "EvidenceDrawer.qml").read_text(
        encoding="utf-8", errors="replace"
    )

    assert "pmCockpitBridge.requestEvidence(projectId)" in main_source
    assert "loadEvidence" not in main_source
    assert "function onEvidenceFinished(response)" in main_source
    assert "evidenceDrawer.openEvidence(response.evidence)" in main_source
    assert "PrimaryButton" in drawer_source  # the existing close button only
    assert drawer_source.count("onClicked") == 1


def test_boss_main_opens_the_drawer_for_the_same_run_after_a_background_read(
    qapp: QApplication, qml_engine: QQmlEngine, tmp_path: Path
) -> None:
    _core_registry(tmp_path)
    _seed_authorized_mission(tmp_path)
    bridge = PmCockpitBridge(str(tmp_path))
    with _managed_boss_window(qml_engine, bridge) as managed_window:
        window: object = managed_window
        drawer = next(
            child
            for child in cast(QObject, window).findChildren(QObject)
            if child.property("focusInfo") is not None
        )

        assert QMetaObject.invokeMethod(
            cast(QObject, window), "showEvidence", Q_ARG("QVariant", "SW-2026-008")
        )
        assert cast(QObject, window).property("statusMessage") == "正在读取证据…"
        assert bridge._thread_pool.waitForDone(10_000)
        for _ in range(300):
            qapp.processEvents()
            bridge._poll_evidence_worker()
            if drawer.property("opened") is True:
                break
            QTest.qWait(10)

        assert drawer.property("opened") is True, cast(QObject, window).property("statusMessage")
        texts = "\n".join(_texts(cast(QQuickItem, drawer)))
        assert "需求：MISSION-COCKPIT-001" in texts
        assert "根工作：WORK-COCKPIT-001" in texts
        assert "运行：RUN-COCKPIT-001（已授权）" in texts
        assert "等待您确认开工" in texts
        assert cast(QObject, window).property("statusMessage") in ("", None)


def test_boss_main_reports_an_unreadable_evidence_request_without_opening_the_drawer(
    qapp: QApplication, qml_engine: QQmlEngine, tmp_path: Path
) -> None:
    _core_registry(tmp_path)
    bridge = PmCockpitBridge(str(tmp_path))
    with _managed_boss_window(qml_engine, bridge) as managed_window:
        window: object = managed_window
        drawer = next(
            child
            for child in cast(QObject, window).findChildren(QObject)
            if child.property("focusInfo") is not None
        )

        assert QMetaObject.invokeMethod(
            cast(QObject, window), "showEvidence", Q_ARG("QVariant", "UNKNOWN-001")
        )
        assert bridge._thread_pool.waitForDone(10_000)
        for _ in range(300):
            qapp.processEvents()
            bridge._poll_evidence_worker()
            if "不在工作空间项目清单" in str(cast(QObject, window).property("statusMessage")):
                break
            QTest.qWait(10)

        assert "不在工作空间项目清单" in str(cast(QObject, window).property("statusMessage"))
        assert drawer.property("opened") is False


# --- U06: pending-sync / completed states and the retry button -------------------------------


def _items_named(item: QQuickItem, name: str) -> list[QQuickItem]:
    found: list[QQuickItem] = []
    for child in item.childItems():
        if child.objectName() == name:
            found.append(child)
        found.extend(_items_named(child, name))
    return found


def _sync_card(completion_state: str, note: str = "") -> dict[str, object]:
    return {
        "project_name": "自动化项目管理工具",
        "mission": "A4",
        "milestone": "验收已记录，待同步",
        "progress": "验收已记录，待同步",
        "blocked": False,
        "verification": "已保存验证证据",
        "risk": "中：验收已记录，变更单与台账尚未同步",
        "current_owner": "PM",
        "next_user_action": "重试台账同步",
        "user_action": "RETRY_SYNC" if completion_state == "PENDING_SYNC" else "NONE",
        "mission_id": "MISSION-001",
        "project_id": "SW-2026-008",
        "completion_state": completion_state,
        "completion_note": note,
    }


def _view_with(engine: QQmlEngine, qapp: QApplication, card: dict[str, object]) -> QQuickItem:
    view = cast(QQuickItem, _load(engine, _QML / "views" / "BossCockpitView.qml"))
    view.setProperty("cards", [card])
    qapp.processEvents()
    return view


def test_view_offers_a_retry_only_while_the_sync_is_pending(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    note = "验收已记录，变更单与台账尚未同步完成；完成前不会显示为已完成。"
    pending = _view_with(qml_engine, qapp, _sync_card("PENDING_SYNC", note))
    completed = _view_with(qml_engine, qapp, _sync_card("COMPLETED", "已验收并完成变更单与台账同步。"))
    untouched = _view_with(qml_engine, qapp, _sync_card("NOT_STARTED"))

    pending_button = _items_named(pending, "retrySyncButton")[0]
    assert pending_button.property("visible") is True
    assert pending_button.property("text") == "重试同步"
    assert pending_button.property("enabled") is True
    assert note in _texts(pending)
    assert _items_named(pending, "completedLabel")[0].property("visible") is False

    assert _items_named(completed, "retrySyncButton")[0].property("visible") is False
    assert _items_named(completed, "completedLabel")[0].property("visible") is True
    assert "已完成并同步台账" in _texts(completed)

    assert _items_named(untouched, "retrySyncButton")[0].property("visible") is False
    assert _items_named(untouched, "completedLabel")[0].property("visible") is False


def test_retry_click_emits_once_and_is_disabled_while_the_sync_runs(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    view = _view_with(qml_engine, qapp, _sync_card("PENDING_SYNC", "尚未同步完成"))
    requested: list[str] = []
    cast(Any, view).syncRetryRequested.connect(lambda mission_id: requested.append(str(mission_id)))
    button = _items_named(view, "retrySyncButton")[0]

    assert QMetaObject.invokeMethod(button, "clicked")
    assert QMetaObject.invokeMethod(button, "clicked")
    qapp.processEvents()

    assert requested == ["MISSION-001"]
    assert button.property("enabled") is False
    assert button.property("text") == "正在同步…"

    assert QMetaObject.invokeMethod(
        view,
        "setCloseBusy",
        Qt.ConnectionType.DirectConnection,
        Q_ARG("QVariant", "MISSION-001"),
        Q_ARG("QVariant", False),
    )
    qapp.processEvents()
    assert button.property("enabled") is True
    assert button.property("text") == "重试同步"
    assert QMetaObject.invokeMethod(button, "clicked")
    assert requested == ["MISSION-001", "MISSION-001"]


def test_pending_sync_texts_never_claim_completion_or_show_progress_numbers(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    view = _view_with(
        qml_engine,
        qapp,
        _sync_card("PENDING_SYNC", "验收已记录，变更单与台账尚未同步完成；完成前不会显示为已完成。"),
    )

    assert _items_named(view, "completedLabel")[0].property("visible") is False
    assert "%" not in "".join(_texts(view))
    lowered = "".join(_texts(view)).lower()
    assert "lease" not in lowered and "token" not in lowered


def test_boss_main_wires_acceptance_retry_and_closure_results() -> None:
    main_source = (_QML / "boss_main.qml").read_text(encoding="utf-8", errors="replace")
    view_source = (_QML / "views" / "BossCockpitView.qml").read_text(
        encoding="utf-8", errors="replace"
    )

    assert "pmCockpitBridge.confirmAcceptance(missionId)" in main_source
    assert "response.success && response.closing" in main_source
    assert "cockpitView.setCloseBusy(missionId, true)" in main_source
    assert "onSyncRetryRequested: function(missionId)" in main_source
    assert "pmCockpitBridge.retryClosure(missionId)" in main_source
    assert "function onClosureFinished(missionId, completed, message)" in main_source
    assert "cockpitView.setCloseBusy(missionId, false)" in main_source
    assert "signal syncRetryRequested(string missionId)" in view_source
    assert "if (!missionId || isCloseBusy(missionId))" in view_source
    assert 'modelData.completion_state === "PENDING_SYNC"' in view_source
    assert 'modelData.completion_state === "COMPLETED"' in view_source
    assert "loadEvidence" not in main_source


def test_boss_main_retries_the_sync_and_turns_the_card_into_completed(
    qapp: QApplication,
    qml_engine: QQmlEngine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _core_registry(tmp_path)
    store, database = _accepted_lineage(tmp_path)
    reconciler = _ProjectionReconciler(OSError("ledger unavailable"))
    closure = PmClosureService(
        tmp_path,
        now=lambda: datetime(2026, 9, 20, 12, 10, tzinfo=UTC),
        store=store,
        ledger_reconciler=reconciler,
    )
    monkeypatch.setattr(closure, "inject_prepared_change_substance", lambda _id: tmp_path / "CHG.md")
    bridge = PmCockpitBridge(
        str(tmp_path), service=PmCockpitService(tmp_path, store=store, closure_service=closure)
    )
    results: list[tuple[str, bool, str]] = []
    bridge.closureFinished.connect(lambda m, ok, msg: results.append((m, ok, msg)))
    with _managed_boss_window(qml_engine, bridge) as window:
        root_item = cast(Any, window).contentItem()

        def pump(until: object, rounds: int = 400) -> None:
            for _ in range(rounds):
                qapp.processEvents()
                bridge._poll_snapshot_worker()
                bridge._poll_close_workers()
                if cast(Any, until)():
                    return
                QTest.qWait(10)
            raise AssertionError("condition was not reached")

        def button_prop(name: str) -> object:
            found = _items_named(root_item, "retrySyncButton")
            return found[0].property(name) if found else None

        def button() -> QQuickItem:
            return _items_named(root_item, "retrySyncButton")[0]

        def ready_mission() -> str:
            if button_prop("visible") is not True or button_prop("enabled") is not True:
                return ""
            context = QQmlEngine.contextForObject(button())
            assert context is not None
            model = context.contextProperty("modelData")
            if isinstance(model, QJSValue):
                model = model.toVariant()
            assert isinstance(model, dict)
            mission = model.get("mission_id")
            return mission if isinstance(mission, str) and mission.strip() else ""

        assert bridge._thread_pool.waitForDone(10_000)
        pump(lambda: bool(ready_mission()) and bridge._snapshot_worker is None)
        mission_id = ready_mission()
        assert mission_id not in bridge._close_workers
        assert QMetaObject.invokeMethod(button(), "clicked")
        assert mission_id in bridge._close_workers, "First retry was not accepted by the bridge"
        assert bridge._thread_pool.waitForDone(10_000)
        pump(lambda: len(results) == 1)
        assert results[0][0] == mission_id
        assert results[0][1] is False
        assert results[0][2] == "台账同步未完成，已保留现场；可稍后重试。"
        # closureFinished starts a new snapshot in QML. Drain and deliver it before
        # opening the audit reader, whose SQLite handle conflicts with Windows snapshot locks.
        assert bridge._thread_pool.waitForDone(10_000)
        pump(lambda: ready_mission() == mission_id and bridge._snapshot_worker is None)
        assert _lineage_states(database)[2] == "ACCEPTED"

        reconciler.result = ReconcileDiff()
        assert mission_id not in bridge._close_workers
        assert QMetaObject.invokeMethod(button(), "clicked")
        assert mission_id in bridge._close_workers, "Second retry was not accepted by the bridge"
        assert bridge._thread_pool.waitForDone(10_000)
        pump(lambda: len(results) == 2)
        assert results[1][0] == mission_id
        assert results[1][1] is True
        assert bridge._thread_pool.waitForDone(10_000)
        pump(lambda: bool(_items_named(root_item, "completedLabel"))
             and _items_named(root_item, "completedLabel")[0].property("visible") is True
             and bridge._snapshot_worker is None)

        assert button_prop("visible") is False
        assert _lineage_states(database)[:4] == ("SUCCEEDED", "CLOSED", "CLOSED", "COMPLETED")


def test_retry_audit_waits_for_the_real_post_closure_snapshot(
    qapp: QApplication,
    qml_engine: QQmlEngine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Control scheduling only: all snapshots, closure results and audit reads stay real."""
    original_snapshot: Callable[[PmCockpitService], PmCockpitSnapshot] = PmCockpitService.snapshot
    original_poll = PmCockpitBridge._poll_close_workers
    original_wait = QThreadPool.waitForDone
    original_audit = _lineage_states
    closure_delivered = Event()
    snapshot_started = Event()
    release_snapshot = Event()
    snapshot_finished = Event()
    drain_requested = Event()
    observed_bridge: PmCockpitBridge | None = None
    real_snapshots: list[PmCockpitSnapshot] = []
    audit_count = 0

    def poll_closure(bridge: PmCockpitBridge) -> None:
        nonlocal observed_bridge
        if any(worker.done for worker in bridge._close_workers.values()):
            # Arm before emitting: QML may submit the snapshot during the original poll.
            observed_bridge = bridge
            closure_delivered.set()
        original_poll(bridge)

    def snapshot(service: PmCockpitService) -> PmCockpitSnapshot:
        if not closure_delivered.is_set() or snapshot_started.is_set():
            return original_snapshot(service)
        snapshot_started.set()
        assert release_snapshot.wait(10), "Post-closure snapshot was never drained"
        result = original_snapshot(service)
        real_snapshots.append(result)
        snapshot_finished.set()
        return result

    def wait_for_done(pool: QThreadPool, msecs: int = -1) -> bool:
        if closure_delivered.is_set():
            drain_requested.set()
            release_snapshot.set()
        return original_wait(pool, msecs)

    def audit(database: Path) -> tuple[str, str, str, str, int, str, int, bool]:
        nonlocal audit_count
        assert drain_requested.is_set() and snapshot_finished.is_set(), (
            "Audit reader ran before the post-closure snapshot drained"
        )
        assert observed_bridge is not None and observed_bridge._snapshot_worker is None, (
            "Audit reader ran before the post-closure snapshot was delivered"
        )
        audit_count += 1
        return original_audit(database)

    monkeypatch.setattr(PmCockpitService, "snapshot", snapshot)
    monkeypatch.setattr(PmCockpitBridge, "_poll_close_workers", poll_closure)
    monkeypatch.setattr(QThreadPool, "waitForDone", wait_for_done)
    monkeypatch.setattr(sys.modules[__name__], "_lineage_states", audit)
    try:
        test_boss_main_retries_the_sync_and_turns_the_card_into_completed(
            qapp, qml_engine, tmp_path, monkeypatch
        )
        assert snapshot_started.is_set() and snapshot_finished.is_set()
        assert len(real_snapshots) == 1 and real_snapshots[0].projects
        assert real_snapshots[0].projects[0].mission_id
        assert audit_count == 2
    finally:
        # Failure also releases the real worker; teardown's wait releases it before unwinding.
        release_snapshot.set()


@pytest.mark.parametrize("fail_in_body", [False, True], ids=["normal", "exception"])
def test_boss_window_teardown_drains_workers_before_destroying_its_owners(
    qapp: QApplication, tmp_path: Path, fail_in_body: bool
) -> None:
    """Exercise the real pool and QML destructor on both exits, without relying on GC."""
    _core_registry(tmp_path)
    destroyed: list[str] = []
    window_boundary: list[tuple[bool, bool, bool, int, bool]] = []
    component_boundary: list[tuple[bool, bool, bool, bool]] = []
    bridge_boundary: list[tuple[bool, bool]] = []
    registered_root_boundary: list[tuple[bool, bool]] = []
    engine_boundary: list[tuple[bool, bool, bool]] = []
    warnings: list[str] = []
    pool = QThreadPool()

    def record_warnings(errors: list[QQmlError]) -> None:
        warnings.extend(error.toString() for error in errors)

    expected = pytest.raises(RuntimeError, match="intentional lifecycle failure") if fail_in_body else nullcontext()
    try:
        with expected, _managed_qml_engine() as engine:
            engine.warnings.connect(record_warnings)
            other_root = cast(QObject, _load(engine, _QML / "components" / "EvidenceDrawer.qml"))
            other_component = other_root.findChild(QQmlComponent)
            assert other_component is not None

            def registered_root_destroyed() -> None:
                registered_root_boundary.append((isValid(engine), QThread.currentThread() == qapp.thread()))
                destroyed.append("registered_root")

            other_root.destroyed.connect(registered_root_destroyed)

            def engine_destroyed() -> None:
                engine_boundary.append((
                    not isValid(other_root),
                    not isValid(other_component),
                    QThread.currentThread() == qapp.thread(),
                ))
                destroyed.append("engine")

            engine.destroyed.connect(engine_destroyed)
            bridge = PmCockpitBridge(str(tmp_path), thread_pool=pool)
            bridge_ref = ref(bridge)

            def bridge_destroyed() -> None:
                bridge_boundary.append((isValid(engine), QThread.currentThread() == qapp.thread()))
                destroyed.append("bridge")

            bridge.destroyed.connect(bridge_destroyed)
            with _managed_boss_window(engine, bridge) as window:
                component = engine.findChild(
                    QQmlComponent, options=Qt.FindChildOption.FindDirectChildrenOnly
                )
                assert component is not None
                timers = bridge.findChildren(QTimer)
                worker = bridge._snapshot_worker
                assert worker is not None  # Component.onCompleted really submitted a snapshot.
                assert timers and any(timer.isActive() for timer in timers)

                def window_destroyed() -> None:
                    held_bridge = bridge_ref()
                    window_boundary.append((
                        held_bridge is not None and isValid(held_bridge),
                        isValid(engine),
                        all(not timer.isActive() for timer in timers),
                        pool.activeThreadCount(),
                        QThread.currentThread() == qapp.thread(),
                    ))
                    destroyed.append("window")

                def component_destroyed() -> None:
                    held_bridge = bridge_ref()
                    component_boundary.append((
                        not isValid(window),
                        held_bridge is not None and isValid(held_bridge),
                        isValid(engine),
                        QThread.currentThread() == qapp.thread(),
                    ))
                    destroyed.append("component")

                window.destroyed.connect(window_destroyed)
                component.destroyed.connect(component_destroyed)
                # The manager must retain the bridge even when the caller drops its reference.
                del bridge
                assert bridge_ref() is not None
                if fail_in_body:
                    raise RuntimeError("intentional lifecycle failure")

        assert destroyed == ["window", "component", "bridge", "registered_root", "engine"]
        assert window_boundary == [(True, True, True, 0, True)]
        assert component_boundary == [(True, True, True, True)]
        assert bridge_boundary == [(True, True)]
        assert registered_root_boundary == [(True, True)]
        assert engine_boundary == [(True, True, True)]
        assert worker.done
        assert pool.waitForDone(0)
        assert not isValid(window) and not isValid(component) and not isValid(engine)
        remaining_bridge = bridge_ref()
        assert remaining_bridge is None or not isValid(remaining_bridge)
        assert not isValid(other_root) and not isValid(other_component)
        assert all(not isValid(timer) for timer in timers)
        assert warnings == []
    finally:
        _delete_qobject(pool)


@pytest.mark.parametrize("managed_engine", [False, True], ids=["shared", "managed"])
@pytest.mark.parametrize("fail_in_body", [False, True], ids=["normal", "exception"])
def test_public_loader_retains_bridges_until_registered_consumers_are_destroyed(
    qapp: QApplication, tmp_path: Path, managed_engine: bool, fail_in_body: bool
) -> None:
    """Exercise the shared fixture contract used by modules importing the public loader."""
    _core_registry(tmp_path)
    shared_factory = cast(
        "Callable[[QApplication], Iterator[QQmlEngine]]", cast(Any, shared_qml_engine).__wrapped__
    )
    lifetime = _managed_qml_engine() if managed_engine else contextmanager(shared_factory)(qapp)
    expected = pytest.raises(RuntimeError, match="public loader body failed") if fail_in_body else nullcontext()
    destroyed: list[str] = []
    consumer_boundaries: list[tuple[bool, bool, bool, int, bool]] = []
    bridge_boundaries: list[tuple[bool, bool, bool]] = []
    warnings: list[str] = []
    pool = QThreadPool()
    legacy_root: QObject | None = None
    legacy_component: QQmlComponent | None = None
    engine: QQmlEngine | None = None
    try:
        with expected, lifetime as engine:
            engine.warnings.connect(
                lambda errors: warnings.extend(error.toString() for error in errors)
            )
            engine.destroyed.connect(lambda: destroyed.append("engine"))
            bridge = PmCockpitBridge(str(tmp_path), thread_pool=pool)
            bridge_ref = ref(bridge)
            engine.rootContext().setContextProperty("pmCockpitBridge", bridge)
            windows = [cast(QObject, _load(engine, _QML / "boss_main.qml")) for _ in range(2)]
            components = engine.findChildren(
                QQmlComponent, options=Qt.FindChildOption.FindDirectChildrenOnly
            )
            assert len(components) == 2
            root = cast(QObject, _load(engine, _QML / "components" / "EvidenceDrawer.qml"))
            consumers: list[QObject] = [*windows, *components, root]
            timers = bridge.findChildren(QTimer)
            worker = bridge._snapshot_worker
            assert worker is not None and any(timer.isActive() for timer in timers)

            def consumer_destroyed() -> None:
                held_bridge = bridge_ref()
                consumer_boundaries.append((
                    held_bridge is not None and isValid(held_bridge),
                    isValid(engine),
                    all(not timer.isActive() for timer in timers),
                    pool.activeThreadCount(),
                    QThread.currentThread() == qapp.thread(),
                ))
                destroyed.append("consumer")

            def bridge_destroyed() -> None:
                bridge_boundaries.append((
                    all(not isValid(value) for value in consumers),
                    isValid(engine),
                    QThread.currentThread() == qapp.thread(),
                ))
                destroyed.append("bridge")

            for consumer in consumers:
                consumer.destroyed.connect(consumer_destroyed)
            bridge.destroyed.connect(bridge_destroyed)
            del bridge  # Both public calls must keep the same bridge alive without caller ownership.
            assert bridge_ref() is not None

            if not managed_engine:
                legacy_component = QQmlComponent(engine)
                legacy_component.setData(b"import QtQml\nQtObject {}", QUrl())
                legacy_root = legacy_component.create()
                assert legacy_root is not None
            if fail_in_body:
                raise RuntimeError("public loader body failed")

        assert destroyed == ["consumer"] * 5 + ["bridge"] + (["engine"] if managed_engine else [])
        assert consumer_boundaries == [(True, True, True, 0, True)] * 5
        assert bridge_boundaries == [(True, True, True)]
        assert all(not isValid(value) for value in consumers)
        held_bridge = bridge_ref()
        assert held_bridge is None or not isValid(held_bridge)
        assert worker.done and pool.waitForDone(0)
        assert warnings == []
        if not managed_engine:
            assert isValid(engine) and isValid(legacy_component) and isValid(legacy_root)
        else:
            assert not isValid(engine)
    finally:
        # These resources deliberately bypassed registration to test the legacy contract.
        if legacy_root is not None:
            _delete_qobject(legacy_root)
        if legacy_component is not None:
            _delete_qobject(legacy_component)
        if engine is not None:
            _delete_qobject(engine)
        _delete_qobject(pool)


@pytest.mark.parametrize("boss_window", [False, True], ids=["component", "boss"])
@pytest.mark.parametrize("failure_stage", ["load", "create"])
def test_qml_setup_failure_destroys_components_before_unwinding_the_engine(
    qapp: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boss_window: bool,
    failure_stage: str,
) -> None:
    """Real QML errors must release resources even while a traceback retains wrappers."""
    _core_registry(tmp_path)
    broken_qml = tmp_path / ("boss_main.qml" if boss_window else "broken.qml")
    broken_qml.write_text(
        "import QtQml\nQtObject { invalid syntax }\n"
        if failure_stage == "load"
        else "import QtQml\nQtObject { required property string missing }\n",
        encoding="utf-8", errors="replace",
    )
    monkeypatch.setattr(sys.modules[__name__], "_QML", tmp_path)
    pool = QThreadPool()
    try:
        with _managed_qml_engine() as engine:
            if boss_window:
                bridge = PmCockpitBridge(str(tmp_path), thread_pool=pool)
                assert bridge.startSnapshotRefresh()["accepted"]
                worker = bridge._snapshot_worker
                assert worker is not None
                timers = bridge.findChildren(QTimer)
                with pytest.raises(AssertionError) as failure:
                    with _managed_boss_window(engine, bridge):
                        pytest.fail("Broken QML unexpectedly created a window")
                assert worker.done and pool.waitForDone(0)
                assert not isValid(bridge)
                assert all(not isValid(timer) for timer in timers)
            else:
                with pytest.raises(AssertionError) as failure:
                    _load(engine, broken_qml)

            # Tracebacks retain Python locals; C++ destruction must already be complete.
            components: list[QQmlComponent] = []
            traceback = failure.value.__traceback__
            while traceback is not None:
                value = traceback.tb_frame.f_locals.get("component")
                if isinstance(value, QQmlComponent):
                    components.append(value)
                traceback = traceback.tb_next
            assert components, "The failing loader's component was not observed"
            assert all(not isValid(component) for component in components)
            assert isValid(engine)
        assert not isValid(engine)
    finally:
        _delete_qobject(pool)


class _StalledTeardownWorker(QRunnable):
    """Hold a real pool thread until its isolated test process is terminated."""

    def __init__(self) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.started = Event()
        self.release = Event()

    def run(self) -> None:
        self.started.set()
        self.release.wait()


def _exercise_stalled_teardown(workspace: Path) -> None:
    """Child-process entry point: no mocks, sleep, or parent-process termination."""
    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    _core_registry(workspace)
    pool = QThreadPool()
    pool.setMaxThreadCount(2)
    worker = _StalledTeardownWorker()

    def unexpected_destruction() -> None:
        print("UNEXPECTED_QT_DESTRUCTION", flush=True)

    with _managed_qml_engine() as engine:
        engine.destroyed.connect(unexpected_destruction)
        bridge = PmCockpitBridge(str(workspace), thread_pool=pool)
        bridge.destroyed.connect(unexpected_destruction)
        pool.destroyed.connect(unexpected_destruction)
        with _managed_boss_window(engine, bridge, drain_timeout_ms=200) as window:
            window.destroyed.connect(unexpected_destruction)
            assert app.thread() == window.thread()
            pool.start(worker)
            assert worker.started.wait(2), "Real pool worker did not start"
            print("REAL_WORKER_STARTED", flush=True)
    print("UNEXPECTED_SUITE_CONTINUATION", flush=True)


def test_stalled_boss_teardown_exits_its_process_without_destroying_live_owners(tmp_path: Path) -> None:
    """A real blocked runnable must cause a prompt, explicit nonzero process exit."""
    command = (
        "from pathlib import Path; import sys; "
        "from tests.qml.test_boss_cockpit_view import _exercise_stalled_teardown; "
        "_exercise_stalled_teardown(Path(sys.argv[1]))"
    )
    started = monotonic()
    result = subprocess.run(
        [sys.executable, "-B", "-u", "-c", command, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=8,
        check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode == _TEARDOWN_FAILURE_EXIT_CODE, output
    assert monotonic() - started < 8, output
    assert "REAL_WORKER_STARTED" in output
    assert "QML_TEARDOWN_TIMEOUT timeout_ms=200" in output
    assert "UNEXPECTED_QT_DESTRUCTION" not in output
    assert "UNEXPECTED_SUITE_CONTINUATION" not in output


def test_view_renders_every_completion_state_without_qml_warnings(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    view = cast(QQuickItem, _load(qml_engine, _QML / "views" / "BossCockpitView.qml"))
    legacy_card = _sync_card("NOT_STARTED")
    del legacy_card["completion_state"]
    del legacy_card["completion_note"]

    with _QtMessages() as messages:
        for card in (
            _sync_card("PENDING_SYNC", "尚未同步完成"),
            _sync_card("COMPLETED", "已验收并完成变更单与台账同步。"),
            _sync_card("NOT_STARTED"),
            legacy_card,
        ):
            view.setProperty("cards", [card])
            qapp.processEvents()

    assert not [m for m in messages if "Error" in m or "Unable" in m or "undefined" in m]


def _empty_workspace(root: Path) -> None:
    registry = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        json.dumps({"schema_version": "workspace-registry.v1", "projects": [{"project_id": "SW-2026-008", "project_root": "projects/SW-2026-008", "development_root": "projects/SW-2026-008"}]}),
        encoding="utf-8",
    )


def _flag(bridge: PmCockpitBridge, name: str) -> bool:
    """Read a bridge flag through a call so a static checker does not narrow it from an earlier assertion."""
    return bool(getattr(bridge, name))


def _is_sealed(bridge: PmCockpitBridge) -> bool:
    return _flag(bridge, "_closing")


_SEALED = {"success": False, "message": "驾驶舱正在关闭。"}


def test_closing_the_real_window_seals_the_bridge_before_the_window_is_destroyed(qapp: QApplication, qml_engine: QQmlEngine, tmp_path: Path) -> None:
    _empty_workspace(tmp_path)
    bridge = PmCockpitBridge(str(tmp_path))
    with _managed_boss_window(qml_engine, bridge) as window:
        qapp.processEvents()
        assert _is_sealed(bridge) is False and bridge.createPlanningDraft("", "", "", "") != _SEALED  # open: this attempt fails on its input, not on a seal
        QMetaObject.invokeMethod(window, "close")  # a real close request on the real window
        qapp.processEvents()
        assert isValid(window), "the window object still exists: only its close event has run so far"
        assert _is_sealed(bridge) is True
        assert bridge.createPlanningDraft("SW-2026-008", "an objective", "a criterion", "iteration") == _SEALED
        assert bridge.confirmStart("MISSION-X") == _SEALED
        assert bridge.startSnapshotRefresh()["accepted"] is False


@pytest.mark.parametrize("owning", [True, False], ids=["standalone-window", "embedded-view"])
def test_destroying_the_real_window_seals_an_owning_bridge_and_only_pauses_an_embedded_one(
    qapp: QApplication, qml_engine: QQmlEngine, tmp_path: Path, owning: bool
) -> None:
    _empty_workspace(tmp_path)
    bridge = PmCockpitBridge(str(tmp_path))
    with _managed_boss_window(qml_engine, bridge) as window:
        qapp.processEvents()
        window.setProperty("closesBridgeOnDestruction", owning)
        _delete_qobject(window)  # the real window is destroyed while its bridge lives on, as when a host keeps a reference
        assert not isValid(window)
        assert _flag(bridge, "_snapshot_delivery_enabled") is False
        if owning:
            assert _is_sealed(bridge) is True
            assert bridge.confirmStart("MISSION-X") == _SEALED
            assert bridge.startSnapshotRefresh()["accepted"] is False
        else:
            assert _is_sealed(bridge) is False, "an embedded view that unloads only pauses the bridge"
            assert bridge.confirmStart("MISSION-X")["message"] != _SEALED["message"]
            assert bridge.startSnapshotRefresh()["message"] != _SEALED["message"]  # not sealed: the refresh may start again (it can be busy with the first refresh)
            assert _flag(bridge, "_snapshot_delivery_enabled") is True


def test_td_closure_alert_a_failed_closure_stays_on_screen_after_the_refresh_until_dismissed(
    qapp: QApplication,
    qml_engine: QQmlEngine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Field case 10-22: the closure hit a read-only ledger and the message vanished with the next refresh."""
    _core_registry(tmp_path)
    store, database = _accepted_lineage(tmp_path)
    reconciler = _ProjectionReconciler(ReconcileDiff())
    closure = PmClosureService(
        tmp_path,
        now=lambda: datetime(2026, 9, 20, 12, 10, tzinfo=UTC),
        store=store,
        ledger_reconciler=reconciler,
    )
    monkeypatch.setattr(closure, "inject_prepared_change_substance", lambda _id: tmp_path / "CHG.md")
    real_complete = closure.complete_closure
    read_only = [True]

    def complete(*args: Any, **kwargs: Any) -> Any:
        if read_only[0]:
            raise sqlite3.OperationalError("attempt to write a readonly database")
        return real_complete(*args, **kwargs)

    monkeypatch.setattr(closure, "complete_closure", complete)
    bridge = PmCockpitBridge(
        str(tmp_path), service=PmCockpitService(tmp_path, store=store, closure_service=closure)
    )
    results: list[tuple[str, bool, str]] = []
    bridge.closureFinished.connect(lambda m, ok, msg: results.append((m, ok, msg)))
    with _managed_boss_window(qml_engine, bridge) as window:
        root_item = cast(Any, window).contentItem()

        def pump(until: Callable[[], bool], rounds: int = 400) -> None:
            for _ in range(rounds):
                qapp.processEvents()
                bridge._poll_snapshot_worker()
                bridge._poll_close_workers()
                if until():
                    return
                QTest.qWait(10)
            raise AssertionError("condition was not reached")

        def retry_button() -> QQuickItem | None:
            found = _items_named(root_item, "retrySyncButton")
            if not found or found[0].property("visible") is not True or found[0].property("enabled") is not True:
                return None
            return found[0]

        def banner_visible() -> bool:
            found = _items_named(root_item, "actionAlertBanner")
            return bool(found) and found[0].property("visible") is True

        def banner_text() -> str:
            return str(_items_named(root_item, "actionAlertText")[0].property("text"))

        assert bridge._thread_pool.waitForDone(10_000)
        pump(lambda: retry_button() is not None and bridge._snapshot_worker is None)
        assert not banner_visible()
        assert QMetaObject.invokeMethod(retry_button(), "clicked")
        assert bridge._thread_pool.waitForDone(10_000)
        pump(lambda: len(results) == 1)
        assert results[0][1] is False
        assert "账本正被占用" in results[0][2]

        # The closure result triggers a snapshot whose success used to blank the only message on screen.
        assert bridge._thread_pool.waitForDone(10_000)
        pump(lambda: bridge._snapshot_worker is None and retry_button() is not None)
        assert window.property("statusMessage") == ""
        assert banner_visible()
        text = banner_text()
        assert "收尾失败：账本正被占用" in text
        assert "请关闭驾驶舱窗口，再由主执行重试收口" in text
        assert _lineage_states(database)[2] == "ACCEPTED"

        # A second periodic refresh does not clear it either.
        assert bridge.requestSnapshot()["accepted"] is True
        assert bridge._thread_pool.waitForDone(10_000)
        pump(lambda: bridge._snapshot_worker is None)
        assert banner_visible()

        assert QMetaObject.invokeMethod(_items_named(root_item, "actionAlertDismiss")[0], "clicked")
        pump(lambda: not banner_visible())

        # Fail again, then succeed: success clears the alert for that Mission by itself.
        assert QMetaObject.invokeMethod(retry_button(), "clicked")
        assert bridge._thread_pool.waitForDone(10_000)
        pump(lambda: len(results) == 2 and banner_visible())
        assert bridge._thread_pool.waitForDone(10_000)
        pump(lambda: bridge._snapshot_worker is None and retry_button() is not None)
        read_only[0] = False
        assert QMetaObject.invokeMethod(retry_button(), "clicked")
        assert bridge._thread_pool.waitForDone(10_000)
        pump(lambda: len(results) == 3)
        assert results[2][1] is True
        pump(lambda: not banner_visible())
        assert bridge._thread_pool.waitForDone(10_000)
        pump(lambda: bridge._snapshot_worker is None)


def test_td_closure_alert_boss_main_keeps_every_action_failure_out_of_the_refreshed_status_line() -> None:
    main_source = (_QML / "boss_main.qml").read_text(encoding="utf-8", errors="replace")
    view_source = (_QML / "views" / "BossCockpitView.qml").read_text(encoding="utf-8", errors="replace")

    for key in ('"close:" + missionId', '"start:" + missionId', '"approve:" + requestId', '"accept:" + missionId'):
        assert f"root.raiseActionAlert({key}" in main_source, key
    assert "actionAlert: root.actionAlert" in main_source
    assert 'objectName: "actionAlertBanner"' in view_source
    assert "signal actionAlertDismissed()" in view_source
