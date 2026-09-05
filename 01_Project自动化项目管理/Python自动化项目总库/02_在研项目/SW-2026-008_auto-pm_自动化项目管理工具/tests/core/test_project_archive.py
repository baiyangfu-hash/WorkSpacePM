from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from auto_pm.core.project_archive_service import (
    ArchiveExecutionError,
    ProjectArchiveService,
)

from auto_pm.domain.project.archive_contracts import (
    ArchiveAuthorization,
    ArchiveContractError,
    ArchiveErrorCode,
    ArchiveOperation,
    ArchiveRequest,
)


class Policy:
    def __init__(self) -> None:
        self.raise_authorization = False
        self.raise_changes = False
        self.open_changes: tuple[str, ...] = ()

    def authorization_for(self, request: ArchiveRequest) -> ArchiveAuthorization:
        if self.raise_authorization:
            raise OSError("decision store unavailable")
        return ArchiveAuthorization(
            True,
            request.decision_id,
            request.operation,
            request.project_id,
            (request.source_path, request.destination_path),
        )

    def open_change_ids(self, project_id: str) -> tuple[str, ...]:
        del project_id
        if self.raise_changes:
            raise OSError("CHG store unavailable")
        return self.open_changes


class Projection:
    def __init__(
        self, name: str, events: list[str], fail_apply: bool = False, fail_undo: bool = False
    ) -> None:
        self.name = name
        self.events = events
        self.fail_apply = fail_apply
        self.fail_undo = fail_undo

    def apply(self, operation: ArchiveOperation, project_id: str) -> None:
        del operation, project_id
        self.events.append(f"{self.name}:apply")
        if self.fail_apply:
            raise OSError(f"{self.name} apply failed")

    def compensate(self, operation: ArchiveOperation, project_id: str) -> None:
        del operation, project_id
        self.events.append(f"{self.name}:compensate")
        if self.fail_undo:
            raise OSError(f"{self.name} compensate failed")


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    workspace = tmp_path / "workspace"
    source = workspace / "projects" / "active" / "SW-2026-099"
    source.mkdir(parents=True)
    (workspace / "projects" / "archive").mkdir(parents=True)
    (source / "PM_SESSION_SW-2026-099.md").write_text(
        "---\nphase: developing\n---\n\n# Project\n", encoding="utf-8"
    )
    (workspace / ".gitignore").write_text(".auto-pm/\n", encoding="utf-8")
    _git(workspace, "init")
    _git(workspace, "config", "user.email", "test@example.invalid")
    _git(workspace, "config", "user.name", "Archive Test")
    _git(workspace, "add", ".")
    _git(workspace, "commit", "-m", "baseline")
    return workspace, source


def _request(
    operation: ArchiveOperation = ArchiveOperation.ARCHIVE, request_id: str = "REQ-001"
) -> ArchiveRequest:
    if operation is ArchiveOperation.ARCHIVE:
        source = "projects/active/SW-2026-099"
        destination = "projects/archive/SW-2026-099"
        code = ""
    else:
        source = "projects/archive/SW-2026-099"
        destination = "projects/active/SW-2026-099"
        code = "ARC-20000101-001"
    return ArchiveRequest(
        request_id,
        "SW-2026-099",
        "CHG-SCPT-2026-099",
        "DEC-20260905-00000001",
        operation,
        source,
        destination,
        "tester",
        code,
    )


def test_archive_executes_real_move_phase_ledger_and_projections(tmp_path: Path) -> None:
    workspace, source = _workspace(tmp_path)
    events: list[str] = []
    service = ProjectArchiveService(
        workspace,
        Policy(),
        Projection("database", events),
        Projection("scanner", events),
    )

    result = service.execute(_request())

    destination = workspace / "projects" / "archive" / "SW-2026-099"
    assert not source.exists()
    assert "phase: archived" in (destination / "PM_SESSION_SW-2026-099.md").read_text(
        encoding="utf-8"
    )
    assert result.archive_code.startswith("ARC-")
    assert events == ["database:apply", "scanner:apply"]
    assert service.list_archived()[0]["archive_code"] == result.archive_code


def test_restore_requires_and_uses_exact_archive_record(tmp_path: Path) -> None:
    workspace, source = _workspace(tmp_path)
    policy = Policy()
    service = ProjectArchiveService(workspace, policy)
    archived = service.execute(_request())
    _git(workspace, "add", "-A")
    _git(workspace, "commit", "-m", "archive")
    restore = replace(
        _request(ArchiveOperation.RESTORE, "REQ-RESTORE"), archive_code=archived.archive_code
    )

    restored = service.execute(restore)

    assert source.is_dir()
    assert restored.archive_code == archived.archive_code
    assert "phase: developing" in (source / "PM_SESSION_SW-2026-099.md").read_text(encoding="utf-8")
    assert service.list_archived() == ()


def test_repeated_completed_request_is_zero_effect_replay(tmp_path: Path) -> None:
    workspace, _ = _workspace(tmp_path)
    service = ProjectArchiveService(workspace, Policy())
    first = service.execute(_request())
    ledger = workspace / service.LEDGER_PATH
    before = ledger.read_bytes()

    second = service.execute(_request())

    assert second.idempotent_replay is True
    assert second.archive_code == first.archive_code
    assert ledger.read_bytes() == before


@pytest.mark.parametrize(
    "failure",
    ["authorization", "changes", "open", "dirty", "git_missing", "git_nonzero", "ledger", "lock"],
)
def test_preflight_failures_have_zero_project_effects(tmp_path: Path, failure: str) -> None:
    workspace, source = _workspace(tmp_path)
    policy = Policy()
    executable = "git"
    if failure == "authorization":
        policy.raise_authorization = True
    elif failure == "changes":
        policy.raise_changes = True
    elif failure == "open":
        policy.open_changes = ("CHG-OPEN-001",)
    elif failure == "dirty":
        (source / "dirty.txt").write_text("dirty", encoding="utf-8")
    elif failure == "git_missing":
        executable = str(workspace / "missing-git.exe")
    elif failure == "git_nonzero":
        executable = sys.executable
    elif failure == "ledger":
        ledger = workspace / ProjectArchiveService.LEDGER_PATH
        ledger.parent.mkdir(parents=True)
        ledger.write_text("not-json", encoding="utf-8")
    elif failure == "lock":
        lock = workspace / ProjectArchiveService.LOCK_DIR / "workspace.lock"
        lock.parent.mkdir(parents=True)
        lock.write_text("held", encoding="utf-8")
    before = (source / "PM_SESSION_SW-2026-099.md").read_bytes()
    service = ProjectArchiveService(workspace, policy, git_executable=executable)

    with pytest.raises((ArchiveContractError, ArchiveExecutionError)):
        service.execute(_request())

    assert source.is_dir()
    assert (source / "PM_SESSION_SW-2026-099.md").read_bytes() == before
    assert not (workspace / "projects" / "archive" / "SW-2026-099").exists()


def test_protected_and_escaped_paths_fail_before_effects(tmp_path: Path) -> None:
    workspace, source = _workspace(tmp_path)
    service = ProjectArchiveService(workspace, Policy())
    protected = replace(_request(), project_id="SW-2026-008")
    escaped = replace(_request(), destination_path="../outside")
    with pytest.raises(ArchiveContractError) as protected_error:
        service.execute(protected)
    with pytest.raises(ArchiveContractError) as escaped_error:
        service.execute(escaped)
    assert protected_error.value.code is ArchiveErrorCode.PROTECTED_PROJECT
    assert escaped_error.value.code is ArchiveErrorCode.PATH_ESCAPE
    assert source.exists()


def test_real_symlink_source_is_rejected_when_supported(tmp_path: Path) -> None:
    workspace, source = _workspace(tmp_path)
    link = workspace / "projects" / "linked"
    try:
        os.symlink(source, link, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    request = replace(_request(), source_path="projects/linked")
    service = ProjectArchiveService(workspace, Policy())
    with pytest.raises(ArchiveContractError) as caught:
        service.execute(request)
    assert caught.value.code is ArchiveErrorCode.LINK_ANOMALY
    assert source.exists()


def test_scanner_failure_compensates_in_strict_reverse_order(tmp_path: Path) -> None:
    workspace, source = _workspace(tmp_path)
    events: list[str] = []
    service = ProjectArchiveService(
        workspace,
        Policy(),
        Projection("database", events),
        Projection("scanner", events, fail_apply=True),
    )

    with pytest.raises(ArchiveExecutionError, match="已完成反向补偿"):
        service.execute(_request())

    assert events == [
        "database:apply",
        "scanner:apply",
        "scanner:compensate",
        "database:compensate",
    ]
    assert source.exists()
    assert "phase: developing" in (source / "PM_SESSION_SW-2026-099.md").read_text(encoding="utf-8")
    assert not (workspace / ProjectArchiveService.LEDGER_PATH).exists()


def test_compensation_failure_preserves_transaction_evidence(tmp_path: Path) -> None:
    workspace, source = _workspace(tmp_path)
    events: list[str] = []
    service = ProjectArchiveService(
        workspace,
        Policy(),
        Projection("database", events),
        Projection("scanner", events, fail_apply=True, fail_undo=True),
    )

    with pytest.raises(ArchiveExecutionError, match="补偿不完整") as caught:
        service.execute(_request())

    assert caught.value.recovery_path
    assert Path(caught.value.recovery_path).is_dir()
    assert source.exists()
    assert events[-2:] == ["scanner:compensate", "database:compensate"]


def test_duplicate_request_identity_conflict_is_rejected(tmp_path: Path) -> None:
    workspace, _ = _workspace(tmp_path)
    service = ProjectArchiveService(workspace, Policy())
    service.execute(_request())
    conflicting = replace(_request(), destination_path="projects/archive/other")
    with pytest.raises(ArchiveContractError) as caught:
        service.execute(conflicting)
    assert caught.value.code is ArchiveErrorCode.DUPLICATE_REQUEST


def test_workspace_serializes_archive_code_allocation(tmp_path: Path) -> None:
    workspace, _ = _workspace(tmp_path)
    second = workspace / "projects" / "active" / "SW-2026-100"
    second.mkdir()
    (second / "PM_SESSION_SW-2026-100.md").write_text(
        "---\nphase: commissioning\n---\n", encoding="utf-8"
    )
    _git(workspace, "add", ".")
    _git(workspace, "commit", "-m", "second project")
    service = ProjectArchiveService(workspace, Policy())
    first = service.execute(_request())
    _git(workspace, "add", "-A")
    _git(workspace, "commit", "-m", "first archive")
    second_request = replace(
        _request(request_id="REQ-002"),
        project_id="SW-2026-100",
        source_path="projects/active/SW-2026-100",
        destination_path="projects/archive/SW-2026-100",
    )

    second_result = service.execute(second_request)

    assert first.archive_code[:-3] == second_result.archive_code[:-3]
    assert int(second_result.archive_code[-3:]) == int(first.archive_code[-3:]) + 1


def test_damaged_ledger_structure_fails_closed(tmp_path: Path) -> None:
    workspace, source = _workspace(tmp_path)
    ledger = workspace / ProjectArchiveService.LEDGER_PATH
    ledger.parent.mkdir(parents=True)
    ledger.write_text(json.dumps({"unexpected": "object"}), encoding="utf-8")
    with pytest.raises(ArchiveContractError) as caught:
        ProjectArchiveService(workspace, Policy()).execute(_request())
    assert caught.value.code is ArchiveErrorCode.LEDGER_DAMAGED
    assert source.exists()


def test_archive_service_exposes_no_delete_or_force_capability() -> None:
    assert not hasattr(ProjectArchiveService, "delete_project")
    assert "force" not in inspect.signature(ProjectArchiveService.execute).parameters
