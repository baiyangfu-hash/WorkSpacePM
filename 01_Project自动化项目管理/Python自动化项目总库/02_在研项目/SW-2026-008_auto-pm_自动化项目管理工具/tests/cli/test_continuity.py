"""CLI coverage for platform-neutral continuity v2."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from auto_pm.cli.__main__ import cli
from auto_pm.core.continuity_execution_service import ContinuityExecutionService
from auto_pm.core.mission_service import MissionService
from auto_pm.core.work_registry_service import WorkRegistryService
from click import ClickException
from click.testing import CliRunner, Result

import auto_pm.ui.cli.continuity as continuity_cli
from auto_pm.contracts.continuity import RunState, WorkKind, WorkState
from auto_pm.contracts.decision_package import (
    RUNTIME_CAPABILITY_KEY,
    DecisionPackageDTO,
    RuntimeDecisionAction,
    RuntimeDecisionCapability,
    RuntimeDecisionOutcome,
)
from auto_pm.contracts.execution_adapter import ExecutionAdapterKind, ExecutionStartEvidence
from auto_pm.contracts.mission import (
    AuthorityAudit,
    AuthorityEnvelope,
    InternalRoutingPolicy,
    MissionState,
)
from auto_pm.infrastructure.continuity_store import ContinuityStore


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _repository(root: Path) -> None:
    _git(root, "init")
    (root / "README.md").write_text("baseline\n", encoding="utf-8")
    (root / ".gitignore").write_text(".auto-pm/\n", encoding="utf-8")
    _git(root, "add", "README.md", ".gitignore")
    _git(
        root,
        "-c",
        "user.name=Continuity Test",
        "-c",
        "user.email=continuity@example.invalid",
        "commit",
        "-m",
        "baseline",
    )


def _head(root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.strip()


def _replace_run_created_event_with_legacy_payload(root: Path, run_id: str) -> None:
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn, conn:
        conn.row_factory = sqlite3.Row
        run = conn.execute("SELECT * FROM run_items WHERE run_id=?", (run_id,)).fetchone()
        event = conn.execute(
            "SELECT * FROM events WHERE aggregate_id=? AND event_type='RUN_CREATED'",
            (run_id,),
        ).fetchone()
        assert run is not None and event is not None
        payload = dict(run)
        payload["state"] = RunState.RUNNING.value
        conn.execute(
            "UPDATE run_items SET state=? WHERE run_id=?",
            (RunState.RUNNING.value, run_id),
        )
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        event_hash = hashlib.sha256(
            (
                f"{event['previous_hash']}|{event['aggregate_id']}|{event['event_type']}|"
                f"{canonical}|{event['created_at']}"
            ).encode()
        ).hexdigest()
        conn.execute(
            """UPDATE events SET payload_json=?, event_hash=?, event_id=?
            WHERE idempotency_key=?""",
            (
                json.dumps(payload, ensure_ascii=False),
                event_hash,
                f"EVT-{event_hash[:16].upper()}",
                event["idempotency_key"],
            ),
        )


def _invoke(runner: CliRunner, root: Path, args: list[str]) -> Result:
    return runner.invoke(cli, ["-w", str(root), "continuity", *args], catch_exceptions=False)


def test_lease_renew_cli_reads_secret_from_environment_and_emits_no_secret(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    _repository(tmp_path)
    works = WorkRegistryService(tmp_path)
    works.initialize("test")
    works.create_work(
        work_id="WORK-CLI-E04",
        subject_project_id="SW-TEST-001",
        kind=WorkKind.GOVERNANCE,
        title="E04",
        owner="architect",
        scope_paths=["README.md"],
        source_fingerprint="sha256:e04",
        idempotency_key="e04-work",
        read_only=True,
    )
    service = ContinuityExecutionService(tmp_path)
    service.start_run(
        run_id="RUN-CLI-E04",
        work_id="WORK-CLI-E04",
        executor_id="agent-a",
        adapter="codex",
        owned_paths=["README.md"],
        declared_dirty_paths=[],
        observed_dirty_paths=[],
        git_head=_head(tmp_path),
        worktree_path=str(tmp_path),
        lease_token="must-not-leak",
        lease_seconds=900,
        idempotency_key="e04-run",
    )

    result = cli_runner.invoke(
        cli,
        [
            "-w",
            str(tmp_path),
            "continuity",
            "lease",
            "renew",
            "--run-id",
            "RUN-CLI-E04",
            "--owner",
            "agent-a",
            "--lease-token-env",
            "AUTO_PM_E04_TOKEN",
            "--expected-version",
            "1",
            "--lease-seconds",
            "900",
            "--idempotency-key",
            "e04-cli-renew",
        ],
        env={"AUTO_PM_E04_TOKEN": "must-not-leak"},
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "lease-renewal-receipt.v1"
    assert payload["version"] == 2
    assert "lease_token" not in payload
    assert "must-not-leak" not in result.output


def test_lease_renew_cli_rejects_plaintext_token_option_without_echoing_it(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    result = _invoke(
        cli_runner,
        tmp_path,
        [
            "lease",
            "renew",
            "--run-id",
            "RUN-CLI-E04",
            "--owner",
            "agent-a",
            "--lease-token",
            "must-not-leak",
            "--expected-version",
            "1",
            "--idempotency-key",
            "e04-cli-plaintext",
        ],
    )
    assert result.exit_code == 2
    assert "must-not-leak" not in result.output


def test_lease_secret_source_is_consumed_before_child_execution(monkeypatch) -> None:
    monkeypatch.setenv("AUTO_PM_E04_ONE_SHOT", "must-not-leak")

    assert continuity_cli._secret_from_environment("AUTO_PM_E04_ONE_SHOT") == "must-not-leak"
    assert "AUTO_PM_E04_ONE_SHOT" not in os.environ


def _authority_json() -> str:
    now = datetime.now(UTC)
    return json.dumps(
        {
            "envelope_id": "AUTH-CLI-001",
            "subject_project_id": "SW-TEST-001",
            "change_id": "CHG-SCPT-2026-200",
            "decision_id": "DEC-20260910-7421E80D",
            "scope_paths": ["README.md"],
            "valid_from": (now - timedelta(minutes=1)).isoformat(),
            "expires_at": (now + timedelta(days=1)).isoformat(),
            "audit": {
                "created_by": "Codex PM",
                "created_at": now.isoformat(),
                "approved_by": "fubai",
                "approved_at": now.isoformat(),
                "source_fingerprint": f"sha256:{'a' * 64}",
            },
        }
    )


def _orchestration_ready(root: Path) -> None:
    now = datetime.now(UTC)
    decision_id = "DEC-20260910-5786E126"
    decision_path = root / ".auto-pm" / "decisions" / f"{decision_id}.json"
    decision_path.parent.mkdir(parents=True, exist_ok=True)
    decision_path.write_text(
        json.dumps(
            {
                "schema_version": "decision_package.v1",
                "decision_id": decision_id,
                "project_id": "SW-TEST-001",
                "change_id": "CHG-SCPT-2026-206",
                "approved_scope": "SYSTEM",
                "approved_files": ["README.md"],
                "approver": "fubai",
                "approved_at": now.isoformat(),
                "decision_conclusion": "approved",
            }
        ),
        encoding="utf-8",
    )
    works = WorkRegistryService(root)
    works.initialize("test")
    works.create_work(
        work_id="WORK-CLI-A3-ROOT",
        subject_project_id="SW-TEST-001",
        kind=WorkKind.WBS,
        title="A3 CLI root",
        owner="Codex",
        scope_paths=["README.md"],
        source_fingerprint="sha256:root",
        idempotency_key="a3-root",
        read_only=True,
    )
    authority = AuthorityEnvelope(
        envelope_id="AUTH-CLI-A3-001",
        subject_project_id="SW-TEST-001",
        change_id="CHG-SCPT-2026-206",
        decision_id=decision_id,
        scope_paths=("README.md",),
        allowed_child_work_kinds=frozenset({WorkKind.BUG}),
        valid_from=now - timedelta(minutes=1),
        expires_at=now + timedelta(days=1),
        audit=AuthorityAudit(
            created_by="Codex PM",
            created_at=now,
            approved_by="fubai",
            approved_at=now,
            source_fingerprint=f"sha256:{'a' * 64}",
        ),
    )
    missions = MissionService(root)
    missions.initialize("test")
    created = missions.create(
        mission_id="MISSION-CLI-A3-001",
        subject_project_id="SW-TEST-001",
        title="A3 CLI",
        objective="Route a typed finding.",
        acceptance_criteria=["One child Work is created."],
        authority=authority,
        created_by="Codex PM",
        idempotency_key="a3-mission-create",
    )
    awaiting = missions.transition(
        mission_id=created.mission_id,
        expected_version=created.version,
        new_state=MissionState.AWAITING_APPROVAL,
        root_work_id=None,
        idempotency_key="a3-mission-submit",
    )
    missions.transition(
        mission_id=awaiting.mission_id,
        expected_version=awaiting.version,
        new_state=MissionState.ACTIVE,
        root_work_id="WORK-CLI-A3-ROOT",
        idempotency_key="a3-mission-activate",
    )


def _dispatch_ready(root: Path) -> None:
    _repository(root)
    now = datetime.now(UTC)
    decision_id = "DEC-20260910-A5CLI001"
    decision_path = root / ".auto-pm" / "decisions" / f"{decision_id}.json"
    decision_path.parent.mkdir(parents=True, exist_ok=True)
    decision_path.write_text(
        json.dumps(
            DecisionPackageDTO(
                decision_id=decision_id,
                project_id="SW-TEST-001",
                change_id="CHG-SCPT-2026-208",
                approved_scope="MODULE",
                approved_files=["README.md"],
                approver="fubai",
                approved_at=now.isoformat(),
            ).to_dict(),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
        errors="replace",
    )
    works = WorkRegistryService(root)
    works.initialize("test")
    work = works.create_work(
        work_id="WORK-CLI-DISPATCH",
        subject_project_id="SW-TEST-001",
        kind=WorkKind.WBS,
        title="A5 CLI dispatch",
        owner="codex:agent-a",
        scope_paths=["README.md"],
        source_fingerprint="sha256:dispatch",
        idempotency_key="dispatch-work-create",
    )
    works.authorize(work.work_id, decision_id, "dispatch-work-authorize")
    authority = AuthorityEnvelope(
        envelope_id="AUTH-CLI-A5-001",
        subject_project_id="SW-TEST-001",
        change_id="CHG-SCPT-2026-208",
        decision_id=decision_id,
        scope_paths=("README.md",),
        allowed_child_work_kinds=frozenset({WorkKind.WBS}),
        routing=InternalRoutingPolicy(
            allow_execution_branch_changes=True,
            allowed_execution_adapters=frozenset({ExecutionAdapterKind.CODEX}),
        ),
        valid_from=now - timedelta(minutes=1),
        expires_at=now + timedelta(days=1),
        audit=AuthorityAudit(
            created_by="Codex PM",
            created_at=now,
            approved_by="fubai",
            approved_at=now,
            source_fingerprint=f"sha256:{'c' * 64}",
        ),
    )
    missions = MissionService(root)
    missions.initialize("test")
    draft = missions.create(
        mission_id="MISSION-CLI-A5-001",
        subject_project_id="SW-TEST-001",
        title="A5 CLI dispatch",
        objective="Prepare a local package.",
        acceptance_criteria=["Receipt is secret-free."],
        authority=authority,
        created_by="Codex PM",
        idempotency_key="dispatch-mission-create",
        root_work_id=work.work_id,
    )
    awaiting = missions.transition(
        mission_id=draft.mission_id,
        expected_version=draft.version,
        new_state=MissionState.AWAITING_APPROVAL,
        root_work_id=None,
        idempotency_key="dispatch-mission-awaiting",
    )
    missions.transition(
        mission_id=awaiting.mission_id,
        expected_version=awaiting.version,
        new_state=MissionState.ACTIVE,
        root_work_id=awaiting.root_work_id,
        idempotency_key="dispatch-mission-active",
    )


def _settlement_ready(root: Path) -> None:
    current = datetime.now(UTC)
    historical = current - timedelta(minutes=2)
    change_path = (
        root
        / "SW-TEST-001"
        / "04_监控"
        / "01_变更管理"
        / "01_变更单"
        / "CHG-SCPT"
        / "CHG-SCPT-2026-214.md"
    )
    change_path.parent.mkdir(parents=True, exist_ok=True)
    change_path.write_text(
        """# CHG-SCPT-2026-214
## 3. 变更基本信息
### 3.0 编号与项目
| 变更编号 | CHG-SCPT-2026-214 |
| 项目编号 | SW-TEST-001 |
### 3.3 影响范围
| 影响范围 | MODULE |
### 3.4 申请信息
| 变更状态 | approved |
""",
        encoding="utf-8",
    )
    works = WorkRegistryService(root, now=lambda: historical.isoformat())
    works.initialize("test")
    target_decision_id = "DEC-20260910-A2TARGT1"
    target_decision = DecisionPackageDTO(
        decision_id=target_decision_id,
        project_id="SW-TEST-001",
        change_id="CHG-SCPT-2026-213",
        approved_scope="MODULE",
        approved_files=["README.md"],
        approver="fubai",
        approved_at=historical.isoformat(),
    )
    target_decision_path = root / ".auto-pm" / "decisions" / f"{target_decision_id}.json"
    target_decision_path.parent.mkdir(parents=True, exist_ok=True)
    target_decision_path.write_bytes(
        json.dumps(target_decision.to_dict(), ensure_ascii=False, indent=2).encode("utf-8")
    )
    works.create_work(
        work_id="WORK-CLI-TARGET",
        subject_project_id="SW-TEST-001",
        kind=WorkKind.GOVERNANCE,
        title="Historical target",
        owner="legacy-agent",
        scope_paths=["README.md"],
        source_fingerprint="sha256:target",
        idempotency_key="cli-target-work",
    )
    works.authorize("WORK-CLI-TARGET", target_decision_id, "cli-authorize-target")
    target_service = ContinuityExecutionService(
        root,
        store=ContinuityStore(root, _clock=lambda: historical),
        now=lambda: historical,
    )
    target_service.start_run(
        run_id="RUN-CLI-TARGET",
        work_id="WORK-CLI-TARGET",
        executor_id="legacy-agent",
        adapter="codex",
        owned_paths=["README.md"],
        declared_dirty_paths=[],
        observed_dirty_paths=[],
        git_head=_head(root),
        worktree_path=str(root),
        lease_token="target-cli-secret",
        lease_seconds=60,
        idempotency_key="cli-target-run",
    )
    target_service.record_start_evidence(
        run_id="RUN-CLI-TARGET",
        owner_id="legacy-agent",
        lease_token="target-cli-secret",
        evidence=ExecutionStartEvidence(
            process_id=1001,
            session_id="cli-target-start",
            started_at=historical,
        ),
        idempotency_key="cli-target-start-evidence",
    )
    decision_id = "DEC-20260911-5C37A985"
    decision = DecisionPackageDTO(
        decision_id=decision_id,
        project_id="SW-TEST-001",
        change_id="CHG-SCPT-2026-214",
        approved_scope="MODULE",
        approved_files=["README.md", ".auto-pm/continuity.db"],
        approver="fubai",
        approved_at=current.isoformat(),
        metadata={
            RUNTIME_CAPABILITY_KEY: RuntimeDecisionCapability(
                allowed_runtime_actions=(RuntimeDecisionAction.SETTLE_EXPIRED_RUN,),
                target_run_ids=("RUN-CLI-TARGET",),
                allowed_outcomes=(RuntimeDecisionOutcome.CANCELLED,),
            )
        },
    )
    decision_path = root / ".auto-pm" / "decisions" / f"{decision_id}.json"
    decision_path.parent.mkdir(parents=True, exist_ok=True)
    decision_path.write_bytes(
        json.dumps(decision.to_dict(), ensure_ascii=False, indent=2).encode("utf-8")
    )
    _git(
        root,
        "add",
        "-f",
        "--",
        f".auto-pm/decisions/{target_decision_id}.json",
        f".auto-pm/decisions/{decision_id}.json",
    )
    _git(
        root,
        "-c",
        "user.name=Continuity Test",
        "-c",
        "user.email=continuity@example.invalid",
        "commit",
        "-m",
        "bind runtime decisions",
    )
    works.create_work(
        work_id="WORK-CLI-RECOVERY",
        subject_project_id="SW-TEST-001",
        kind=WorkKind.GOVERNANCE,
        title="Recovery",
        owner="recovery-agent",
        scope_paths=["README.md", ".auto-pm/continuity.db"],
        source_fingerprint="sha256:recovery",
        idempotency_key="cli-recovery-work",
    )
    works.authorize("WORK-CLI-RECOVERY", decision_id, "cli-authorize-recovery")
    works.transition("WORK-CLI-RECOVERY", WorkState.IN_PROGRESS, "cli-start-recovery")
    recovery_service = ContinuityExecutionService(
        root,
        store=ContinuityStore(root, _clock=lambda: current),
        now=lambda: current,
    )
    recovery_service.start_run(
        run_id="RUN-CLI-RECOVERY",
        work_id="WORK-CLI-RECOVERY",
        executor_id="recovery-agent",
        adapter="codex",
        owned_paths=["README.md", ".auto-pm/continuity.db"],
        declared_dirty_paths=[],
        observed_dirty_paths=[],
        git_head=_head(root),
        worktree_path=str(root),
        lease_token="recovery-cli-secret",
        lease_seconds=900,
        idempotency_key="cli-recovery-run",
    )
    recovery_service.record_start_evidence(
        run_id="RUN-CLI-RECOVERY",
        owner_id="recovery-agent",
        lease_token="recovery-cli-secret",
        evidence=ExecutionStartEvidence(
            process_id=1002,
            session_id="cli-recovery-start",
            started_at=current,
        ),
        idempotency_key="cli-recovery-start-evidence",
    )


def _settlement_args(*, outcome: str = "CANCELLED") -> list[str]:
    return [
        "run",
        "settle-expired",
        "--target-run-id",
        "RUN-CLI-TARGET",
        "--recovery-run-id",
        "RUN-CLI-RECOVERY",
        "--recovery-owner",
        "recovery-agent",
        "--recovery-lease-token",
        "recovery-cli-secret",
        "--decision-id",
        "DEC-20260911-5C37A985",
        "--outcome",
        outcome,
        "--reason",
        "Close the historical expired Run forward.",
        "--idempotency-key",
        "cli-settle-expired",
    ]


def test_mission_cli_creates_reads_and_transitions_explicit_authority(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    _repository(tmp_path)
    created = _invoke(
        cli_runner,
        tmp_path,
        [
            "mission",
            "create",
            "--mission-id",
            "MISSION-CLI-001",
            "--pid",
            "SW-TEST-001",
            "--title",
            "CLI Mission",
            "--objective",
            "Persist exact authority.",
            "--acceptance",
            "Mission can be read.",
            "--authority-json",
            _authority_json(),
            "--created-by",
            "Codex PM",
            "--idempotency-key",
            "mission-create",
        ],
    )
    assert created.exit_code == 0, created.output
    assert json.loads(created.output)["state"] == "DRAFT"

    shown = _invoke(cli_runner, tmp_path, ["mission", "show", "--mission-id", "MISSION-CLI-001"])
    assert shown.exit_code == 0
    assert json.loads(shown.output)["authority"]["decision_id"] == "DEC-20260910-7421E80D"

    submitted = _invoke(
        cli_runner,
        tmp_path,
        [
            "mission",
            "transition",
            "--mission-id",
            "MISSION-CLI-001",
            "--to",
            "AWAITING_APPROVAL",
            "--expected-version",
            "1",
            "--idempotency-key",
            "mission-submit",
        ],
    )
    assert submitted.exit_code == 0
    assert json.loads(submitted.output)["state"] == "AWAITING_APPROVAL"


def test_continuity_cli_runs_checkpoint_and_handoff_v2(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    _repository(tmp_path)
    created = _invoke(
        cli_runner,
        tmp_path,
        [
            "work",
            "create",
            "--work-id",
            "WORK-CLI-001",
            "--pid",
            "SW-TEST-001",
            "--kind",
            "TEST",
            "--title",
            "CLI continuity",
            "--owner",
            "agent-a",
            "--scope",
            "README.md",
            "--idempotency-key",
            "work-create",
            "--read-only",
        ],
    )
    assert created.exit_code == 0
    assert json.loads(created.output)["state"] == "READY"

    started = _invoke(
        cli_runner,
        tmp_path,
        [
            "run",
            "start",
            "--run-id",
            "RUN-CLI-001",
            "--work-id",
            "WORK-CLI-001",
            "--executor",
            "agent-a",
            "--adapter",
            "codex",
            "--owned",
            "README.md",
            "--declared-dirty",
            "README.md",
            "--lease-token",
            "lease-a",
            "--lease-seconds",
            "900",
            "--idempotency-key",
            "run-start",
        ],
    )
    assert started.exit_code == 0
    assert json.loads(started.output)["state"] == "READY"
    ContinuityExecutionService(tmp_path).record_start_evidence(
        run_id="RUN-CLI-001",
        owner_id="agent-a",
        lease_token="lease-a",
        evidence=ExecutionStartEvidence(
            process_id=1003,
            session_id="cli-checkpoint-start",
            started_at=datetime.now(UTC),
        ),
        idempotency_key="run-start-evidence",
    )

    (tmp_path / "README.md").write_text("changed\n", encoding="utf-8")
    checkpoint = _invoke(
        cli_runner,
        tmp_path,
        [
            "checkpoint",
            "create",
            "--checkpoint-id",
            "CP-CLI-001",
            "--run-id",
            "RUN-CLI-001",
            "--owner",
            "agent-a",
            "--lease-token",
            "lease-a",
            "--summary",
            "changed readme",
            "--evidence",
            "pytest:0",
            "--idempotency-key",
            "checkpoint-create",
        ],
    )
    assert checkpoint.exit_code == 0
    assert json.loads(checkpoint.output)["dirty_paths"] == ["README.md"]

    handoff = _invoke(
        cli_runner,
        tmp_path,
        [
            "handoff",
            "create",
            "--handoff-id",
            "HO-CLI-001",
            "--checkpoint-id",
            "CP-CLI-001",
            "--from-owner",
            "agent-a",
            "--to-owner",
            "agent-b",
            "--lease-token",
            "lease-a",
            "--idempotency-key",
            "handoff-create",
        ],
    )
    assert handoff.exit_code == 0
    assert json.loads(handoff.output)["schema_version"] == "handoff.v2"

    accepted = _invoke(
        cli_runner,
        tmp_path,
        [
            "handoff",
            "accept",
            "--handoff-id",
            "HO-CLI-001",
            "--receiver",
            "agent-b",
            "--new-lease-token",
            "lease-b",
            "--lease-seconds",
            "900",
            "--idempotency-key",
            "handoff-accept",
        ],
    )
    assert accepted.exit_code == 0
    assert json.loads(accepted.output)["owner_id"] == "agent-b"


def test_run_start_rejects_physically_dirty_undeclared_owned_path(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    _repository(tmp_path)
    created = _invoke(
        cli_runner,
        tmp_path,
        [
            "work",
            "create",
            "--work-id",
            "WORK-CLI-002",
            "--pid",
            "SW-TEST-001",
            "--kind",
            "TEST",
            "--title",
            "Dirty gate",
            "--owner",
            "agent-a",
            "--scope",
            "README.md",
            "--idempotency-key",
            "work-create",
            "--read-only",
        ],
    )
    assert created.exit_code == 0
    (tmp_path / "README.md").write_text("dirty\n", encoding="utf-8")

    started = _invoke(
        cli_runner,
        tmp_path,
        [
            "run",
            "start",
            "--run-id",
            "RUN-CLI-002",
            "--work-id",
            "WORK-CLI-002",
            "--executor",
            "agent-a",
            "--adapter",
            "codex",
            "--owned",
            "README.md",
            "--lease-token",
            "lease-a",
            "--lease-seconds",
            "900",
            "--idempotency-key",
            "run-start",
        ],
    )
    assert started.exit_code == 1
    assert "未声明" in started.output


def test_run_start_cli_exact_replay_survives_dirty_tree_and_successor_commit(
    cli_runner: CliRunner,
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    created_work = _invoke(
        cli_runner,
        tmp_path,
        [
            "work",
            "create",
            "--work-id",
            "WORK-CLI-REPLAY",
            "--pid",
            "SW-TEST-001",
            "--kind",
            "TEST",
            "--title",
            "CLI Run replay",
            "--owner",
            "agent-a",
            "--scope",
            "README.md",
            "--idempotency-key",
            "work-create-replay",
            "--read-only",
        ],
    )
    assert created_work.exit_code == 0, created_work.output
    start_args = [
        "run",
        "start",
        "--run-id",
        "RUN-CLI-REPLAY",
        "--work-id",
        "WORK-CLI-REPLAY",
        "--executor",
        "agent-a",
        "--adapter",
        "codex",
        "--owned",
        "README.md",
        "--lease-token",
        "cli-replay-secret",
        "--lease-seconds",
        "900",
        "--idempotency-key",
        "run-start-replay",
    ]

    first = _invoke(cli_runner, tmp_path, start_args)
    assert first.exit_code == 0, first.output
    first_payload = json.loads(first.output)
    (tmp_path / "README.md").write_text("dirty after start\n", encoding="utf-8")

    dirty_replay = _invoke(cli_runner, tmp_path, start_args)
    assert dirty_replay.exit_code == 0, dirty_replay.output
    assert json.loads(dirty_replay.output) == first_payload
    _git(tmp_path, "add", "--", "README.md")
    _git(
        tmp_path,
        "-c",
        "user.name=Continuity Test",
        "-c",
        "user.email=continuity@example.invalid",
        "commit",
        "-m",
        "successor",
    )

    successor_replay = _invoke(cli_runner, tmp_path, start_args)
    assert successor_replay.exit_code == 0, successor_replay.output
    assert json.loads(successor_replay.output) == first_payload
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM events WHERE event_type='RUN_CREATED'").fetchone()[0]
            == 1
        )


def test_run_start_cli_replays_only_provable_legacy_receipt(
    cli_runner: CliRunner,
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    work = _invoke(
        cli_runner,
        tmp_path,
        [
            "work",
            "create",
            "--work-id",
            "WORK-CLI-LEGACY",
            "--pid",
            "SW-TEST-001",
            "--kind",
            "TEST",
            "--title",
            "Legacy replay",
            "--owner",
            "agent-a",
            "--scope",
            "README.md",
            "--idempotency-key",
            "work-create-legacy",
            "--read-only",
        ],
    )
    assert work.exit_code == 0, work.output
    args = [
        "run",
        "start",
        "--run-id",
        "RUN-CLI-LEGACY",
        "--work-id",
        "WORK-CLI-LEGACY",
        "--executor",
        "agent-a",
        "--adapter",
        "codex",
        "--owned",
        "README.md",
        "--lease-token",
        "legacy-secret",
        "--lease-seconds",
        "900",
        "--idempotency-key",
        "run-start-legacy",
    ]
    first = _invoke(cli_runner, tmp_path, args)
    assert first.exit_code == 0, first.output
    _replace_run_created_event_with_legacy_payload(tmp_path, "RUN-CLI-LEGACY")

    replay = _invoke(cli_runner, tmp_path, args)
    assert replay.exit_code == 0, replay.output
    changed = list(args)
    changed[changed.index("codex")] = "cursor"
    rejected = _invoke(cli_runner, tmp_path, changed)
    assert rejected.exit_code == 1
    assert "不一致" in rejected.output
    ContinuityExecutionService(tmp_path).renew_lease(
        "RUN-CLI-LEGACY",
        "agent-a",
        "legacy-secret",
        900,
        "renew-cli-legacy",
    )
    unprovable = _invoke(cli_runner, tmp_path, args)
    assert unprovable.exit_code == 1
    assert "LEGACY_REPLAY_UNPROVABLE" in unprovable.output


def test_cli_git_fact_read_rejects_success_with_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Result:
        returncode = 0
        stdout = b""
        stderr = b"warning: Permission denied\n"

    monkeypatch.setattr(continuity_cli.subprocess, "run", lambda *args, **kwargs: Result())

    with pytest.raises(ClickException, match="Permission denied"):
        continuity_cli._git(tmp_path, "status", "--porcelain")
    assert not (tmp_path / ".auto-pm").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows path identity is case-insensitive")
def test_cli_path_authority_matches_inverse_case_on_windows() -> None:
    assert continuity_cli._within(("README.md",), ("readme.md",)) == ["README.md"]


def test_run_start_rejects_external_repository_before_run_persistence(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    control = tmp_path / "control"
    foreign = tmp_path / "foreign"
    control.mkdir()
    foreign.mkdir()
    _repository(control)
    _repository(foreign)
    created = _invoke(
        cli_runner,
        control,
        [
            "work",
            "create",
            "--work-id",
            "WORK-CLI-EXTERNAL",
            "--pid",
            "SW-TEST-001",
            "--kind",
            "TEST",
            "--title",
            "External worktree gate",
            "--owner",
            "agent-a",
            "--scope",
            "README.md",
            "--idempotency-key",
            "work-create-external",
            "--read-only",
        ],
    )
    assert created.exit_code == 0

    started = _invoke(
        cli_runner,
        control,
        [
            "run",
            "start",
            "--run-id",
            "RUN-CLI-EXTERNAL",
            "--work-id",
            "WORK-CLI-EXTERNAL",
            "--executor",
            "agent-a",
            "--adapter",
            "codex",
            "--owned",
            "README.md",
            "--worktree",
            str(foreign),
            "--lease-token",
            "external-secret",
            "--lease-seconds",
            "900",
            "--idempotency-key",
            "run-start-external",
        ],
    )

    assert started.exit_code == 1
    assert "workspace 外" in started.output or "受管" in started.output
    assert ContinuityExecutionService(control)._store.list_runs("WORK-CLI-EXTERNAL") == ()


def test_orchestration_cli_routes_a_typed_bug_without_a_hidden_queue(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    _repository(tmp_path)
    _orchestration_ready(tmp_path)

    result = _invoke(
        cli_runner,
        tmp_path,
        [
            "orchestration",
            "report-finding",
            "--finding-id",
            "FND-CLI-A3-001",
            "--mission-id",
            "MISSION-CLI-A3-001",
            "--parent-work-id",
            "WORK-CLI-A3-ROOT",
            "--pid",
            "SW-TEST-001",
            "--kind",
            "BUG",
            "--title",
            "CLI bug",
            "--summary",
            "A typed gate finding.",
            "--scope",
            "README.md",
            "--source-fingerprint",
            f"sha256:{'b' * 64}",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["action"] == "BLOCKING"
    assert payload["child_work_id"] == "WORK-A3-CLI-A3-001"


def test_dispatch_cli_emits_only_a_local_secret_free_preparation_receipt(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    _dispatch_ready(tmp_path)

    result = _invoke(
        cli_runner,
        tmp_path,
        [
            "dispatch",
            "prepare",
            "--mission-id",
            "MISSION-CLI-A5-001",
            "--work-id",
            "WORK-CLI-DISPATCH",
            "--run-id",
            "RUN-CLI-A5-001",
            "--adapter",
            "codex",
            "--executor",
            "agent-a",
            "--lease-token",
            "must-not-leak",
            "--stack",
            "python",
            "--force-isolation",
            "--idempotency-key",
            "dispatch-cli-prepare",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "PREPARED"
    assert payload["adapter"] == "codex"
    assert payload["worktree_mode"] == "ISOLATED"
    assert "must-not-leak" not in result.output


def test_settle_expired_cli_is_secret_free_and_capability_scoped(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    _repository(tmp_path)
    _settlement_ready(tmp_path)

    result = _invoke(cli_runner, tmp_path, _settlement_args())

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["state"] == RunState.CANCELLED.value
    assert "recovery-cli-secret" not in result.output
    assert "target-cli-secret" not in result.output


def test_settle_expired_cli_rejects_failed_outcome_without_mutation(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    _repository(tmp_path)
    _settlement_ready(tmp_path)

    result = _invoke(cli_runner, tmp_path, _settlement_args(outcome="FAILED"))

    assert result.exit_code == 2
    assert "Invalid value for '--outcome'" in result.output
    assert "recovery-cli-secret" not in result.output
    state = ContinuityExecutionService(tmp_path).get_run("RUN-CLI-TARGET").state
    assert state is RunState.RUNNING


def test_continuity_mutation_rejects_linked_worktree_before_database_creation(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    _repository(tmp_path)
    linked = tmp_path.parent / f"{tmp_path.name}-linked"
    _git(tmp_path, "worktree", "add", "--detach", str(linked), "HEAD")

    result = _invoke(cli_runner, linked, _settlement_args())

    assert result.exit_code == 1
    assert "linked worktree" in result.output
    assert not (linked / ".auto-pm").exists()


def test_continuity_git_facts_ignore_caller_git_environment(
    cli_runner: CliRunner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _repository(tmp_path)
    spoof = tmp_path.parent / f"{tmp_path.name}-spoof-repository"
    spoof.mkdir()
    _repository(spoof)
    (spoof / "README.md").write_text("spoof\n", encoding="utf-8")
    _git(spoof, "add", "README.md")
    _git(
        spoof,
        "-c",
        "user.name=Continuity Test",
        "-c",
        "user.email=continuity@example.invalid",
        "commit",
        "-m",
        "spoof",
    )
    root_head = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    spoof_head = subprocess.run(
        ["git", "-C", str(spoof), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    assert root_head != spoof_head
    monkeypatch.setenv("GIT_DIR", str(spoof / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(spoof))
    monkeypatch.setenv("GIT_COMMON_DIR", str(spoof / ".git"))

    result = _invoke(
        cli_runner,
        tmp_path,
        [
            "work",
            "create",
            "--work-id",
            "WORK-CLI-GIT-ENV",
            "--pid",
            "SW-TEST-001",
            "--kind",
            "TEST",
            "--title",
            "Git environment isolation",
            "--owner",
            "agent-a",
            "--scope",
            "README.md",
            "--idempotency-key",
            "work-git-env",
            "--read-only",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["source_fingerprint"] == f"git:{root_head}"
    assert spoof_head not in result.output


def test_linked_work_create_rejects_before_git_snapshot(
    cli_runner: CliRunner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _repository(tmp_path)
    linked = tmp_path.parent / f"{tmp_path.name}-linked-before-snapshot"
    _git(tmp_path, "worktree", "add", "--detach", str(linked), "HEAD")

    def forbidden_snapshot(_root: Path) -> tuple[str, tuple[str, ...]]:
        raise AssertionError("Git snapshot ran before root mutation guard")

    monkeypatch.setattr("auto_pm.ui.cli.continuity._git_snapshot", forbidden_snapshot)
    result = _invoke(
        cli_runner,
        linked,
        [
            "work",
            "create",
            "--work-id",
            "WORK-CLI-LINKED",
            "--pid",
            "SW-TEST-001",
            "--kind",
            "TEST",
            "--title",
            "Linked guard",
            "--owner",
            "agent-a",
            "--scope",
            "README.md",
            "--idempotency-key",
            "work-linked",
            "--read-only",
        ],
    )

    assert result.exit_code == 1
    assert "linked worktree" in result.output
    assert not (linked / ".auto-pm").exists()


def test_settle_expired_cli_never_accepts_succeeded_outcome(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    result = _invoke(cli_runner, tmp_path, _settlement_args(outcome="SUCCEEDED"))

    assert result.exit_code == 2
    assert "Invalid value for '--outcome'" in result.output
