"""Files that decide something (Decision, registry, handoff, PM_SESSION, ledger, audit report) are read as strict UTF-8: a bad byte is a refusal, never a repaired value."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from auto_pm.application.core.continuity_execution_service import (
    ContinuityExecutionError,
    ContinuityExecutionService,
)
from auto_pm.application.core.pm_cockpit_service import PmCockpitError, PmCockpitService
from auto_pm.application.core.pm_intake_service import PmIntakeError, PmIntakeService
from auto_pm.application.core.pm_resume_service import PmResumeError, PmResumeService
from auto_pm.application.core.pr_ready_service import find_audit_report
from auto_pm.application.core.work_registry_service import WorkRegistryError, WorkRegistryService

# A lone 0xFF inside a JSON string: valid JSON once repaired with errors="replace", impossible to decode strictly.
BAD = b"\xff"


def test_a_decision_file_with_a_bad_byte_is_not_loaded(tmp_path: Path) -> None:
    subprocess.run(["git", "-C", str(tmp_path), "init"], check=True, capture_output=True)
    service = WorkRegistryService(tmp_path, now=lambda: "2026-09-09T12:00:00+00:00")
    path = tmp_path / ".auto-pm" / "decisions" / "DEC-1.json"
    path.parent.mkdir(parents=True)
    package = {
        "schema_version": "decision_package.v1",
        "decision_id": "DEC-1",
        "project_id": "SW-2026-008",
        "change_id": "CHG-SCPT-TEST",
        "approved_scope": "MODULE",
        "approved_files": ["a.py"],
        "approver": "architect",
        "approved_at": "2026-09-09T11:00:00+00:00",
        "decision_conclusion": "approved",
    }
    path.write_text(json.dumps(package), encoding="utf-8")
    assert service._load_decision("DEC-1").decision_id == "DEC-1"  # the same file without the bad byte loads
    package["approver"] = "architect@@"
    path.write_bytes(json.dumps(package).encode().replace(b"@@", BAD))

    with pytest.raises(WorkRegistryError, match="无法读取"):
        service._load_decision("DEC-1")


def test_a_workspace_registry_with_a_bad_byte_stops_the_cockpit(tmp_path: Path) -> None:
    registry = tmp_path / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    registry.parent.mkdir(parents=True)
    project = {"project_id": "SW-2026-008", "project_root": "p@@", "development_root": "p"}
    registry.write_bytes(
        json.dumps({"schema_version": "workspace-registry.v1", "projects": [project]}).encode().replace(b"@@", BAD)
    )

    with pytest.raises(PmCockpitError, match="格式无效"):
        PmCockpitService(tmp_path)._mappings()


def test_a_legacy_handoff_with_a_bad_byte_is_unreadable(tmp_path: Path) -> None:
    old = tmp_path / "old.json"
    old.write_bytes(json.dumps({"schema_version": "handoff.v1", "request_id": "@@"}).encode().replace(b"@@", BAD))

    with pytest.raises(ContinuityExecutionError, match="无法读取"):
        ContinuityExecutionService(tmp_path).load_legacy_handoff(old)


def test_a_pm_session_with_a_bad_byte_is_refused(tmp_path: Path) -> None:
    session = tmp_path / "PM_SESSION_SW-2026-008.md"
    session.write_bytes(b"- control_project_id: SW-2026-001 " + BAD + b"\n")

    with pytest.raises(PmResumeError, match="无法读取 PM_SESSION"):
        PmResumeService._read_text(session)


def test_a_ledger_file_with_a_bad_byte_is_reported_not_searched(tmp_path: Path) -> None:
    folder = tmp_path / "ledger"
    folder.mkdir()
    (folder / "台账.md").write_bytes(b"| TD-SW901-001 | " + BAD + b" |\n")
    service = PmIntakeService.__new__(PmIntakeService)
    service._ledger_directories = lambda project_id, ledger_id: [folder]  # type: ignore[method-assign]

    with pytest.raises(PmIntakeError, match="取证台账无法读取"):
        service._require_ledger_row("TD-SW901-001", "SW-2026-008")


def test_an_audit_report_of_this_pr_with_a_bad_byte_is_never_quoted_as_a_verdict(tmp_path: Path) -> None:
    (tmp_path / "audit-pr42.md").write_bytes("放行判定: abcdef12 过\n".encode() + BAD + b"\n")
    ok, detail = find_audit_report(42, "abcdef12" + "0" * 32, [tmp_path])
    assert not ok and "不是合法 UTF-8" in detail

    # A report that is not about this PR is skipped; it cannot block other PRs.
    (tmp_path / "audit-7.md").write_bytes(BAD + b"\n")
    (tmp_path / "audit-43.md").write_text("PR #43\n放行判定: abcdef12 过\n", encoding="utf-8")
    assert find_audit_report(43, "abcdef12" + "0" * 32, [tmp_path])[0]
