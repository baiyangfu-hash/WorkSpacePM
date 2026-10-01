"""Loadability checks for the isolated boss cockpit QML surface."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from PySide6.QtCore import (
    Q_ARG,
    QMetaObject,
    QObject,
    Qt,
    QtMsgType,
    QUrl,
    qInstallMessageHandler,
)
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from auto_pm.infrastructure.continuity_store import ContinuityStore
from auto_pm.ui.qml.bridges.pm_cockpit_bridge import PmCockpitBridge
from tests.core.test_pm_cockpit_service import _registry as _core_registry
from tests.core.test_pm_cockpit_service import _seed_authorized_mission

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication


_QML = Path(__file__).resolve().parents[2] / "auto_pm" / "ui" / "qml"


def _load(engine: QQmlEngine, path: Path) -> object:
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(path)))
    assert not component.isError(), "\n".join(error.toString() for error in component.errors())
    value = component.create()
    assert value is not None
    value._component_ref = component  # type: ignore[attr-defined]
    return value


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
    assert "Component.onDestruction: pmCockpitBridge.stopSnapshotRefresh()" in main_source
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
    qml_engine.rootContext().setContextProperty("pmCockpitBridge", PmCockpitBridge(str(tmp_path)))

    window = _load(qml_engine, _QML / "boss_main.qml")

    qapp.processEvents()
    assert window.property("title") == "我的驾驶舱"  # type: ignore[attr-defined]
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
    store = ContinuityStore(tmp_path)
    store.initialize("2026-09-28T00:00:00+00:00", "test")
    bridge = PmCockpitBridge(str(tmp_path))
    qml_engine.rootContext().setContextProperty("pmCockpitBridge", bridge)
    window = _load(qml_engine, _QML / "boss_main.qml")
    refresh = bridge.startSnapshotRefresh()
    assert refresh["accepted"] or refresh["busy"], refresh
    assert bridge._thread_pool.waitForDone(5_000)
    bridge._poll_snapshot_worker()
    snapshot: dict[str, object] = {}
    for _ in range(100):
        qapp.processEvents()
        bridge._poll_snapshot_worker()
        raw_snapshot = cast(Any, cast(QObject, window).property("snapshot"))
        snapshot = (
            raw_snapshot.toVariant()
            if hasattr(raw_snapshot, "toVariant")
            else cast(dict[str, object], raw_snapshot)
        )
        if snapshot["projects"]:
            break
        QTest.qWait(10)
    assert snapshot["projects"]
    objective = window.findChild(QObject, "planningObjective")  # type: ignore[attr-defined]
    acceptance = window.findChild(QObject, "planningAcceptance")  # type: ignore[attr-defined]
    save = window.findChild(QObject, "savePlanningDraft")  # type: ignore[attr-defined]
    assert objective is not None and acceptance is not None and save is not None
    objective.setProperty("text", "Improve release verification")
    acceptance.setProperty("text", "All checks pass")
    qapp.processEvents()

    assert QMetaObject.invokeMethod(save, "clicked")
    qapp.processEvents()

    draft = window.property("planningDraft")  # type: ignore[attr-defined]
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
    qml_engine.rootContext().setContextProperty("pmCockpitBridge", bridge)
    window = _load(qml_engine, _QML / "boss_main.qml")
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
    bridge.stopSnapshotRefresh()


def test_boss_main_reports_an_unreadable_evidence_request_without_opening_the_drawer(
    qapp: QApplication, qml_engine: QQmlEngine, tmp_path: Path
) -> None:
    _core_registry(tmp_path)
    bridge = PmCockpitBridge(str(tmp_path))
    qml_engine.rootContext().setContextProperty("pmCockpitBridge", bridge)
    window = _load(qml_engine, _QML / "boss_main.qml")
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
    bridge.stopSnapshotRefresh()
