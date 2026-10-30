"""Backup self-check: events whose writer numbers them itself (Work relations, reclaim-risk signatures) are checked
against that numbering instead of being reported as a broken chain; a forged id or forged content is still caught."""

from __future__ import annotations

import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

from click.testing import CliRunner

from auto_pm.infrastructure.continuity_backup import inspect_connection
from auto_pm.ui.cli.__main__ import cli
from tests.cli.test_continuity_backup import PROJECT, _cli, _create_work, _ledger, _workspace
from tests.core.test_lease_handover_service import RUN, Scene


def _report(db: Path):  # type: ignore[no-untyped-def]
    with closing(sqlite3.connect(db)) as conn:
        return inspect_connection(conn, db, "", 0)


def _related_workspace(tmp_path: Path) -> Path:
    root = _workspace(tmp_path)
    _create_work(root, "WORK-REL-001")
    _create_work(root, "WORK-REL-002")
    related = CliRunner().invoke(
        cli,
        ["-w", str(root), "continuity", "work", "relate", "--from-work", "WORK-REL-001", "--to-work", "WORK-REL-002",
         "--relation", "blocks", "--idempotency-key", "rel-key-1"],
    )
    assert related.exit_code == 0, related.output
    return root


def _copy(root: Path, name: str) -> Path:
    copy = root / name
    shutil.copy2(_ledger(root), copy)
    return copy


def _update(db: Path, sql: str, *parameters: object) -> None:
    with closing(sqlite3.connect(db)) as conn, conn:
        assert conn.execute(sql, parameters).rowcount == 1


def test_a_work_relation_event_with_its_own_numbering_is_not_a_broken_chain(tmp_path: Path) -> None:
    root = _related_workspace(tmp_path)

    report = _report(_ledger(root))

    assert report.ok, report.findings
    with closing(sqlite3.connect(_ledger(root))) as conn:
        assert conn.execute("SELECT COUNT(*) FROM events WHERE event_type='WORK_RELATION_ADDED'").fetchone()[0] == 1
    assert _cli(root, "continuity", "backup").exit_code == 0


def test_a_work_relation_event_with_a_forged_id_is_still_a_broken_chain(tmp_path: Path) -> None:
    root = _related_workspace(tmp_path)
    forged = _copy(root, "forged-id.db")
    _update(forged, "UPDATE events SET event_id='EVT-0000000000000000' WHERE event_type='WORK_RELATION_ADDED'")

    report = _report(forged)

    assert not report.ok
    assert "编号规则" in "".join(report.findings)


def test_a_work_relation_event_whose_idempotency_key_was_changed_is_still_a_broken_chain(tmp_path: Path) -> None:
    root = _related_workspace(tmp_path)
    forged = _copy(root, "forged-key.db")
    _update(forged, "UPDATE events SET idempotency_key='another-key' WHERE event_type='WORK_RELATION_ADDED'")

    assert not _report(forged).ok


def test_a_work_relation_event_whose_content_was_changed_is_still_a_broken_chain(tmp_path: Path) -> None:
    root = _related_workspace(tmp_path)
    forged = _copy(root, "forged-content.db")
    _update(
        forged,
        "UPDATE events SET payload_json=replace(payload_json, 'blocks', 'depends') WHERE event_type='WORK_RELATION_ADDED'",
    )

    report = _report(forged)

    assert not report.ok
    assert "内容被改过" in "".join(report.findings)


def _signed_scene(tmp_path: Path) -> Scene:
    scene = Scene(tmp_path / "ws")
    scene.expire()
    scene.service.sign_risk(
        run_id=RUN, claimant_id="agent-b", signer="fubai", environ={}, stdin_is_tty=True, stdout_is_tty=True
    )
    return scene


def test_a_reclaim_risk_signature_with_its_own_numbering_is_not_a_broken_chain(tmp_path: Path) -> None:
    scene = _signed_scene(tmp_path)

    report = _report(scene.root / ".auto-pm" / "continuity.db")

    assert report.ok, report.findings


def test_a_reclaim_risk_signature_with_a_forged_id_is_still_a_broken_chain(tmp_path: Path) -> None:
    scene = _signed_scene(tmp_path)
    forged = scene.root / "forged-risk.db"
    shutil.copy2(scene.root / ".auto-pm" / "continuity.db", forged)
    _update(forged, "UPDATE events SET event_id='RISK-0000000000000000' WHERE event_type='RECLAIM_RISK_ACCEPTED'")

    report = _report(forged)

    assert not report.ok
    assert "编号规则" in "".join(report.findings)


def test_a_reclaim_risk_signature_whose_content_was_changed_is_still_a_broken_chain(tmp_path: Path) -> None:
    scene = _signed_scene(tmp_path)
    forged = scene.root / "forged-risk-content.db"
    shutil.copy2(scene.root / ".auto-pm" / "continuity.db", forged)
    _update(
        forged,
        "UPDATE events SET payload_json=replace(payload_json, 'agent-b', 'agent-x') WHERE event_type='RECLAIM_RISK_ACCEPTED'",
    )

    assert not _report(forged).ok


def test_the_project_constant_used_by_the_backup_tests_still_exists() -> None:
    assert PROJECT == "SW-2026-008"
