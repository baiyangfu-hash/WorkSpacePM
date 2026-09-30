"""Loadability checks for the isolated boss cockpit QML surface."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from PySide6.QtCore import Q_ARG, QMetaObject, QObject, Qt, QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtTest import QTest

from auto_pm.infrastructure.continuity_store import ContinuityStore
from auto_pm.ui.qml.bridges.pm_cockpit_bridge import PmCockpitBridge

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
