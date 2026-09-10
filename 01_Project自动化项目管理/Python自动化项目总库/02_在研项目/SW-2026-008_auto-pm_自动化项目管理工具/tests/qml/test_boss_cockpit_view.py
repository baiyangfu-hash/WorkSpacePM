"""Loadability checks for the isolated boss cockpit QML surface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine

from auto_pm.ui.qml.bridges.pm_cockpit_bridge import PmCockpitBridge

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication


_QML = Path(__file__).resolve().parents[2] / "auto_pm" / "ui" / "qml"


def _load(engine: QQmlEngine, path: Path) -> object:
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(path)))
    assert not component.isError(), "\n".join(error.toString() for error in component.errors())
    value = component.create()
    assert value is not None
    value._component_ref = component
    return value


def test_boss_cockpit_components_load_without_the_legacy_workbench(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    files = (
        _QML / "components" / "PmConfirmationCard.qml",
        _QML / "components" / "WorkGraphView.qml",
        _QML / "components" / "EvidenceDrawer.qml",
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
