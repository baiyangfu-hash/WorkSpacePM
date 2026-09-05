"""CLI and real governance-adapter tests for reversible project archive."""

from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from auto_pm.change.change_service import ChangeService
from auto_pm.core.project_archive_service import ArchiveResult
from click.testing import CliRunner

from auto_pm.app_context import AppContext
from auto_pm.domain.project.archive_contracts import (
    ArchiveContractError,
    ArchiveErrorCode,
    ArchiveOperation,
    ArchiveRequest,
)
from auto_pm.ui.cli import project as project_cli


class _FakeArchiveProjectService:
    def __init__(self) -> None:
        self.requests: list[ArchiveRequest] = []
        self.failure: Exception | None = None

    def _execute(self, request: ArchiveRequest) -> ArchiveResult:
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure
        return ArchiveResult(
            request_id=request.request_id,
            project_id=request.project_id,
            operation=request.operation,
            archive_code=request.archive_code or "ARC-20260905-001",
            source_path=request.source_path,
            destination_path=request.destination_path,
            idempotent_replay=False,
        )

    def archive_project(self, request: ArchiveRequest) -> ArchiveResult:
        return self._execute(request)

    def restore_project(self, request: ArchiveRequest) -> ArchiveResult:
        return self._execute(request)

    def list_archived_projects(self) -> tuple[dict[str, str], ...]:
        return (
            {
                "archive_code": "ARC-20260905-001",
                "project_id": "SW-2026-099",
                "source_path": "projects/SW-2026-099",
                "destination_path": "archive/SW-2026-099",
                "status": "archived",
            },
        )


def _cli_args(operation: str) -> list[str]:
    args = [
        operation,
        "--request-id",
        f"req-{operation}",
        "--project-id",
        "SW-2026-099",
        "--change-id",
        "CHG-SCPT-2026-001",
        "--decision-id",
        "DEC-20260905-ABCDEF01",
        "--source",
        "projects/SW-2026-099",
        "--destination",
        "archive/SW-2026-099",
        "--actor",
        "tester",
    ]
    if operation == "restore":
        args.extend(["--archive-code", "ARC-20260905-001"])
    return args


@pytest.fixture
def fake_service(monkeypatch: pytest.MonkeyPatch) -> _FakeArchiveProjectService:
    service = _FakeArchiveProjectService()
    monkeypatch.setattr(project_cli, "_build_archive_project_service", lambda _root: service)
    return service


@pytest.mark.parametrize(
    ("command", "operation"),
    [("archive", ArchiveOperation.ARCHIVE), ("restore", ArchiveOperation.RESTORE)],
)
def test_archive_commands_route_once_and_emit_truthful_json(
    tmp_path: Path,
    fake_service: _FakeArchiveProjectService,
    command: str,
    operation: ArchiveOperation,
) -> None:
    result = CliRunner().invoke(
        project_cli.project_group,
        [*_cli_args(command), "--json"],
        obj=AppContext(str(tmp_path)),
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload == {
        "success": True,
        "request_id": f"req-{command}",
        "project_id": "SW-2026-099",
        "operation": operation.value,
        "archive_code": "ARC-20260905-001",
        "source_path": "projects/SW-2026-099",
        "destination_path": "archive/SW-2026-099",
        "idempotent_replay": False,
    }
    assert len(fake_service.requests) == 1
    assert fake_service.requests[0].operation is operation


def test_archive_failure_is_stable_json_and_nonzero(
    tmp_path: Path, fake_service: _FakeArchiveProjectService
) -> None:
    fake_service.failure = ArchiveContractError(ArchiveErrorCode.OPEN_CHANGE, "仍有开放变更")

    result = CliRunner().invoke(
        project_cli.project_group,
        [*_cli_args("archive"), "--json"],
        obj=AppContext(str(tmp_path)),
    )

    assert result.exit_code == 2
    assert json.loads(result.output) == {
        "success": False,
        "error": {"code": "open_change", "message": "仍有开放变更"},
    }


def test_archive_list_uses_safe_service_view(
    tmp_path: Path, fake_service: _FakeArchiveProjectService
) -> None:
    result = CliRunner().invoke(
        project_cli.project_group,
        ["archive-list", "--json"],
        obj=AppContext(str(tmp_path)),
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["success"] is True
    assert payload["archives"][0]["archive_code"] == "ARC-20260905-001"


def test_command_inventory_has_reversible_commands_without_archive_bypasses() -> None:
    commands = project_cli.project_group.commands
    assert {"archive", "restore", "archive-list"} <= set(commands)
    assert "delete" not in commands
    for command_name in ("archive", "restore"):
        option_names = {
            option
            for parameter in commands[command_name].params
            for option in getattr(parameter, "opts", ())
        }
        assert "--force" not in option_names
        assert "--confirm-delete" not in option_names

    source = "\n".join(
        inspect.getsource(function)
        for function in (
            project_cli._run_archive_command,
            project_cli.cmd_archive.callback,
            project_cli.cmd_restore.callback,
            project_cli.cmd_archive_list.callback,
        )
    )
    for forbidden_call in (
        "shutil.rmtree(",
        "shutil.move(",
        "os.rename(",
        "_write_ledger(",
        "PM_SESSION",
    ):
        assert forbidden_call not in source


def test_archive_help_requires_all_identity_and_path_facts() -> None:
    runner = CliRunner()
    help_result = runner.invoke(project_cli.project_group, ["archive", "--help"])
    missing_result = runner.invoke(project_cli.project_group, ["archive", "--json"])

    assert help_result.exit_code == 0
    for option in (
        "--request-id",
        "--project-id",
        "--change-id",
        "--decision-id",
        "--source",
        "--destination",
        "--actor",
    ):
        assert option in help_result.output
    assert "--force" not in help_result.output
    assert missing_result.exit_code == 2


def _write_real_policy_fixture(tmp_path: Path) -> tuple[ArchiveRequest, ChangeService, Path]:
    project_id = "SW-2026-099"
    project = tmp_path / f"{project_id}_policy"
    project.mkdir(parents=True)
    (project / ".plc.json").write_text(
        json.dumps({"name": project_id, "version": "V1.0.0"}),
        encoding="utf-8",
        errors="replace",
    )
    change_service = ChangeService(tmp_path)
    change = change_service.create_change_request(
        project_id=project_id,
        domain="SCPT",
        business_nature="OPT",
        impact_scope=["MODULE"],
        applicant="tester",
        background="archive policy fixture",
        necessity="prove real CHG binding",
    )
    change_path = Path(change.file_path)
    content = change_path.read_text(encoding="utf-8", errors="replace")
    change_path.write_text(
        content.replace("| 变更状态 | draft |", "| 变更状态 | implementing |"),
        encoding="utf-8",
        errors="replace",
    )
    request = ArchiveRequest(
        request_id="req-policy-001",
        project_id=project_id,
        change_id=change.change_number,
        decision_id="DEC-20260905-ABCDEF01",
        operation=ArchiveOperation.ARCHIVE,
        source_path=f"projects/{project_id}",
        destination_path=f"archive/{project_id}",
        actor="tester",
    )
    payload: dict[str, Any] = {
        "schema_version": "decision_package.v1",
        "decision_id": request.decision_id,
        "project_id": request.project_id,
        "change_id": request.change_id,
        "approved_scope": "MODULE",
        "approved_files": [request.source_path, request.destination_path],
        "approver": "owner",
        "approved_at": "2026-09-05T12:00:00+00:00",
        "decision_conclusion": "approved",
        "conditions": list(project_cli.archive_authority_conditions(request)),
        "metadata": {},
    }
    decision_path = tmp_path / ".auto-pm" / "decisions" / f"{request.decision_id}.json"
    decision_path.parent.mkdir(parents=True, exist_ok=True)
    decision_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
        errors="replace",
    )
    return request, change_service, decision_path


def test_real_policy_adapter_consumes_exact_decision_and_current_chg(tmp_path: Path) -> None:
    request, _, _ = _write_real_policy_fixture(tmp_path)
    policy = project_cli.ProjectArchivePolicyAdapter(str(tmp_path))

    authorization = policy.authorization_for(request)

    assert authorization.decision_id == request.decision_id
    assert authorization.approved_paths == (request.source_path, request.destination_path)
    assert policy.open_change_ids(request.project_id) == ()


def test_real_policy_adapter_reports_every_other_nonterminal_chg(tmp_path: Path) -> None:
    request, changes, _ = _write_real_policy_fixture(tmp_path)
    other = changes.create_change_request(
        project_id=request.project_id,
        domain="DOCU",
        business_nature="OPT",
        impact_scope=["LOCAL"],
        applicant="tester",
        background="other open change",
        necessity="prove it blocks",
    )
    policy = project_cli.ProjectArchivePolicyAdapter(str(tmp_path))
    policy.authorization_for(request)

    assert policy.open_change_ids(request.project_id) == (other.change_number,)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("conditions", "运行条件"),
        ("approved_files", "文件清单"),
        ("project_id", "目标文件未获精确批准|决策项目"),
        ("change_id", "决策变更单"),
    ],
)
def test_real_policy_adapter_fails_closed_on_authority_drift(
    tmp_path: Path, mutation: str, message: str
) -> None:
    request, _, decision_path = _write_real_policy_fixture(tmp_path)
    payload = json.loads(decision_path.read_text(encoding="utf-8", errors="replace"))
    if mutation == "conditions":
        payload[mutation] = payload[mutation][:-1]
    elif mutation == "approved_files":
        payload[mutation] = list(reversed(payload[mutation]))
    else:
        payload[mutation] = "SW-2026-100" if mutation == "project_id" else "CHG-SCPT-2026-999"
    decision_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
        errors="replace",
    )

    with pytest.raises(Exception, match=message):
        project_cli.ProjectArchivePolicyAdapter(str(tmp_path)).authorization_for(request)


def test_real_policy_adapter_fails_closed_on_corrupt_decision_and_chg_status(
    tmp_path: Path,
) -> None:
    request, _, decision_path = _write_real_policy_fixture(tmp_path)
    decision_path.write_text("{broken", encoding="utf-8", errors="replace")
    with pytest.raises(Exception, match="JSON 损坏"):
        project_cli.ProjectArchivePolicyAdapter(str(tmp_path)).authorization_for(request)

    request, _, _ = _write_real_policy_fixture(tmp_path / "second")
    change = ChangeService(tmp_path / "second").get_change_request(
        request.change_id, project_id=request.project_id
    )
    assert change is not None
    change_path = Path(change.file_path)
    content = change_path.read_text(encoding="utf-8", errors="replace")
    change_path.write_text(
        content.replace("| 变更状态 | implementing |", "| 变更状态 | draft |"),
        encoding="utf-8",
        errors="replace",
    )
    with pytest.raises(ValueError, match="状态不允许"):
        project_cli.ProjectArchivePolicyAdapter(str(tmp_path / "second")).authorization_for(
            request
        )


def test_real_policy_adapter_fails_closed_on_missing_and_blocked_decision(
    tmp_path: Path,
) -> None:
    request, _, decision_path = _write_real_policy_fixture(tmp_path)
    decision_path.unlink()
    with pytest.raises(Exception, match="未找到决策包"):
        project_cli.ProjectArchivePolicyAdapter(str(tmp_path)).authorization_for(request)

    request, _, decision_path = _write_real_policy_fixture(tmp_path / "blocked")
    decision_hash = hashlib.sha256(decision_path.read_bytes()).hexdigest()
    disposition = {
        "schema_version": "decision_disposition.v1",
        "record_id": "DISP-20260905-ABCDEF01-01",
        "target_decision_id": request.decision_id,
        "target_decision_sha256": decision_hash,
        "disposition": "BLOCKED_SEMANTIC_CONFLICT",
        "effect": "NOT_AUTHORITY_FOR_FUTURE_RECOVERY_COMMIT_DEPLOY_OR_RELEASE",
        "preserves_original": True,
        "retroactive_mutation": False,
        "approver": "owner",
        "approved_at": "2026-09-05T12:01:00+00:00",
        "supersession_status": "DEFERRED_UNTIL_NEW_INDEPENDENTLY_APPROVED_DECISION",
        "superseding_decision_id": None,
        "authority_semantics": {
            "future_consumption_only": True,
            "rewrites_target_decision": False,
            "grants_recovery_or_release_authority": False,
        },
    }
    disposition_path = decision_path.parent / "dispositions" / "blocked.json"
    disposition_path.parent.mkdir(parents=True)
    disposition_path.write_text(
        json.dumps(disposition, ensure_ascii=False, indent=2),
        encoding="utf-8",
        errors="replace",
    )
    with pytest.raises(Exception, match="blocked.*拒绝消费"):
        project_cli.ProjectArchivePolicyAdapter(str(tmp_path / "blocked")).authorization_for(
            request
        )


def test_restore_conditions_are_operation_specific() -> None:
    archive = ArchiveRequest(
        request_id="req",
        project_id="SW-2026-099",
        change_id="CHG-SCPT-2026-001",
        decision_id="DEC-20260905-ABCDEF01",
        operation=ArchiveOperation.ARCHIVE,
        source_path="projects/SW-2026-099",
        destination_path="archive/SW-2026-099",
        actor="tester",
    )
    restore = replace(
        archive,
        operation=ArchiveOperation.RESTORE,
        source_path=archive.destination_path,
        destination_path=archive.source_path,
        archive_code="ARC-20260905-001",
    )

    assert project_cli.archive_authority_conditions(archive) != (
        project_cli.archive_authority_conditions(restore)
    )
