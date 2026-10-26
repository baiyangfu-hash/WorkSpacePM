"""V05-B: the production cockpit factory wires both roots and the real global thread pool."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from auto_pm.cli.__main__ import cli
from auto_pm.config.app_config import AutoPmConfig
from click.testing import CliRunner
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from auto_pm.infrastructure.continuity_store import ContinuityStore
from auto_pm.ui.boss_qml_window import build_cockpit_bridge
from auto_pm.ui.qml.bridges.pm_cockpit_bridge import PmCockpitBridge
from tests.core.test_pm_cockpit_dual_root import PROJECT, _roots, _store_files, _work
from tests.qml.conftest import _delete_qobject


def test_the_production_factory_wires_both_roots_and_the_global_thread_pool(qapp: QApplication, tmp_path: Path) -> None:
    main, candidate = _roots(tmp_path)
    bridge = build_cockpit_bridge(str(candidate), AutoPmConfig(cockpit_approver="fubai"), control_root=str(main))
    try:
        assert bridge._thread_pool is QThreadPool.globalInstance()
        assert bridge._service._control_root == main.resolve()
        assert bridge._service._workspace_root == candidate.resolve()
        assert bridge._facade._workspace_root == main.resolve()
        assert bridge._facade._execution_root == candidate.resolve()
    finally:
        _delete_qobject(bridge)
    own = PmCockpitBridge(str(candidate), control_root=str(main))
    try:
        assert own._service._control_root == main.resolve()
        assert own._service._workspace_root == candidate.resolve()
    finally:
        _delete_qobject(own)


def test_a_snapshot_through_the_real_global_pool_is_delivered_on_the_gui_thread(qapp: QApplication, tmp_path: Path) -> None:
    main, candidate = _roots(tmp_path)
    _work(main, "WORK-WIRE-001")
    before = _store_files(main)
    bridge = build_cockpit_bridge(str(candidate), control_root=str(main))
    delivered: list[tuple[dict[str, object], int]] = []
    bridge.snapshotFinished.connect(lambda response: delivered.append((response, threading.get_native_id())))
    try:
        assert bridge.requestSnapshot()["accepted"] is True
        deadline = time.monotonic() + 30
        while not delivered and time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.01)
        assert delivered, "the real pool never delivered the snapshot"
        response, thread_id = delivered[0]
        assert response["success"] is True
        snapshot = response["snapshot"]
        assert isinstance(snapshot, dict) and [card["project_id"] for card in snapshot["projects"]] == [PROJECT]
        assert thread_id == threading.get_native_id()  # the signal reached the GUI thread, not the pool worker
        assert _store_files(main) == before and not (candidate / ".auto-pm").exists()
    finally:
        QThreadPool.globalInstance().waitForDone(10_000)
        _delete_qobject(bridge)


def test_the_gui_goal_input_lands_in_the_control_root_and_swapped_roots_write_nothing(qapp: QApplication, tmp_path: Path) -> None:
    main, candidate = _roots(tmp_path)
    _work(main, "WORK-WIRE-002")
    good = build_cockpit_bridge(str(candidate), control_root=str(main))
    try:
        saved = good.createPlanningDraft(PROJECT, "dual root goal", "the goal is saved in the control root", "iteration")
        assert saved["success"] is True
        assert len(ContinuityStore(main).list_planning_drafts(PROJECT)) == 1
        after_good = _store_files(main)
    finally:
        _delete_qobject(good)
    swapped = build_cockpit_bridge(str(main), control_root=str(candidate))
    try:
        refused = swapped.createPlanningDraft(PROJECT, "swapped goal", "this must be refused", "iteration")
        assert refused["success"] is False
        assert _store_files(main) == after_good
        assert len(ContinuityStore(main).list_planning_drafts(PROJECT)) == 1
        assert not (candidate / ".auto-pm").exists()
    finally:
        _delete_qobject(swapped)


@pytest.mark.parametrize("dual", [True, False], ids=["linked-candidate", "single-root"])
def test_the_gui_command_hands_the_control_root_to_the_cockpit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, dual: bool) -> None:
    main, candidate = _roots(tmp_path)
    calls: list[tuple[Path, Path]] = []

    def fake_run(workspace_root: str, debug: bool = False, *, control_root: str | None = None) -> int:
        assert (control_root is not None) == dual
        calls.append((Path(workspace_root).resolve(), Path(control_root or workspace_root).resolve()))
        return 0

    monkeypatch.setattr("auto_pm.ui.boss_qml_window.run_boss_cockpit", fake_run)
    args = ["-w", str(candidate), "--control-root", str(main), "gui"] if dual else ["-w", str(main), "gui"]
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    assert calls == [((candidate if dual else main).resolve(), main.resolve())]
