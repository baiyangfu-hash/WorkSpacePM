"""Run, checkpoint, lease, and handoff v2 failure-injection tests."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from auto_pm.core.continuity_execution_service import (
    ContinuityExecutionError,
    ContinuityExecutionService,
)
from auto_pm.core.work_registry_service import WorkRegistryService

from auto_pm.application.core.evidence_collection_service import (
    EvidenceCollectionService,
    PythonQualityGate,
    PythonQualityReceipt,
)
from auto_pm.contracts.continuity import CheckpointItem, RunState, WorkKind, WorkState
from auto_pm.contracts.decision_package import (
    RUNTIME_CAPABILITY_KEY,
    DecisionPackageDTO,
    RuntimeDecisionAction,
    RuntimeDecisionCapability,
    RuntimeDecisionOutcome,
)
from auto_pm.contracts.execution_adapter import ExecutionStartEvidence
from auto_pm.domain.change.decision_service import DecisionService
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value


def _git_root(root: Path) -> None:
    subprocess.run(["git", "-C", str(root), "init"], check=True, capture_output=True)
    (root / "README.md").write_text("baseline\n", encoding="utf-8", errors="replace")
    (root / ".gitignore").write_text(".auto-pm/\n", encoding="utf-8", errors="replace")
    subprocess.run(
        ["git", "-C", str(root), "add", "README.md", ".gitignore"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Continuity Test",
            "-c",
            "user.email=continuity@example.invalid",
            "commit",
            "-m",
            "baseline",
        ],
        check=True,
        capture_output=True,
    )


def _runtime_change(root: Path, *, status: str = "approved") -> Path:
    path = (
        root
        / "SW-2026-008_auto-pm"
        / "04_监控"
        / "01_变更管理"
        / "01_变更单"
        / "CHG-SCPT"
        / "CHG-SCPT-2026-214.md"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""# CHG-SCPT-2026-214
## 3. 变更基本信息
### 3.0 编号与项目
| 变更编号 | CHG-SCPT-2026-214 |
| 项目编号 | SW-2026-008 |
### 3.3 影响范围
| 影响范围 | MODULE |
### 3.4 申请信息
| 变更状态 | {status} |
""",
        encoding="utf-8",
        errors="replace",
    )
    return path


def _services(root: Path, clock: Clock):
    _git_root(root)
    work = WorkRegistryService(root, now=lambda: clock().isoformat())
    work.initialize("test")
    work.create_work(
        work_id="WORK-001",
        subject_project_id="SW-2026-008",
        kind=WorkKind.GOVERNANCE,
        title="Continuity",
        owner="architect",
        scope_paths=["auto_pm/core/a.py", "tests/test_a.py"],
        source_fingerprint="sha256:abc",
        idempotency_key="create-work",
        read_only=True,
    )
    store = ContinuityStore(root, _clock=clock)
    return work, ContinuityExecutionService(root, store=store, now=clock)


def _start(service: ContinuityExecutionService, **changes):
    git_head = subprocess.run(
        ["git", "-C", str(service._root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.strip()
    values = {
        "run_id": "RUN-001",
        "work_id": "WORK-001",
        "executor_id": "agent-a",
        "adapter": "codex",
        "owned_paths": ["auto_pm/core/a.py"],
        "declared_dirty_paths": [],
        "observed_dirty_paths": [],
        "git_head": git_head,
        "worktree_path": str(service._root),
        "lease_token": "lease-secret",
        "lease_seconds": 900,
        "idempotency_key": "create-run",
    }
    values.update(changes)
    return service.start_run(**values)


def _start_evidence(service: ContinuityExecutionService, **changes):
    values = {
        "run_id": "RUN-001",
        "owner_id": "agent-a",
        "lease_token": "lease-secret",
        "evidence": ExecutionStartEvidence(
            process_id=1234,
            session_id="thread-e03b-test",
            started_at=service._utc_now(),
        ),
        "idempotency_key": "record-start-evidence",
    }
    values.update(changes)
    return service.record_start_evidence(**values)


def _checkpoint(service: ContinuityExecutionService, **changes):
    values = {
        "checkpoint_id": "CP-001",
        "run_id": "RUN-001",
        "owner_id": "agent-a",
        "lease_token": "lease-secret",
        "summary": "implemented",
        "git_head": service._store.get_run("RUN-001").git_head,
        "dirty_paths": ["auto_pm/core/a.py"],
        "evidence": ["pytest:0"],
        "idempotency_key": "checkpoint-1",
    }
    values.update(changes)
    return service.checkpoint(**values)


def _c03_auto_checkpoint_service(
    tmp_path: Path,
    *,
    ruff_failure: bool = False,
    include_production_target: bool = True,
    include_untracked_target: bool = False,
    c03_selector_match: bool = True,
    project_name: str = "project",
):
    """Create a real nested project worktree plus isolated continuity database."""

    clock = Clock()
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    _git_root(workspace)
    (workspace / ".gitignore").write_text(
        ".auto-pm/\n__pycache__/\n.pytest_cache/\n.mypy_cache/\n.ruff_cache/\n",
        encoding="utf-8",
        errors="replace",
    )
    project = workspace / project_name
    source = project / "auto_pm" / "core" / "target.py"
    source.parent.mkdir(parents=True)
    (project / "auto_pm" / "__init__.py").write_text(
        "", encoding="utf-8", errors="replace"
    )
    (project / "auto_pm" / "core" / "__init__.py").write_text(
        "", encoding="utf-8", errors="replace"
    )
    source.write_text(
        "import os\n\n\ndef value() -> int:\n    return 1\n"
        if ruff_failure
        else "def value() -> int:\n    return 1\n",
        encoding="utf-8",
        errors="replace",
    )
    test_path = project / "tests" / "core" / "test_continuity_execution_service.py"
    test_path.parent.mkdir(parents=True)
    test_name = (
        "test_append_verified_checkpoint_profile_target"
        if c03_selector_match
        else "test_other_quality_target"
    )
    test_path.write_text(
        "from auto_pm.core.target import value\n\n\n"
        f"def {test_name}() -> None:\n"
        "    assert value() > 0\n",
        encoding="utf-8",
        errors="replace",
    )
    (project / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths = [\"tests\"]\n",
        encoding="utf-8",
        errors="replace",
    )
    subprocess.run(["git", "-C", str(workspace), "add", "."], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(workspace),
            "-c",
            "user.name=Continuity Test",
            "-c",
            "user.email=continuity@example.invalid",
            "commit",
            "-m",
            "nested quality project",
        ],
        check=True,
        capture_output=True,
    )
    baseline = subprocess.run(
        ["git", "-C", str(workspace), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.strip()
    candidate = workspace / ".auto-pm" / "worktrees" / "c03-auto-checkpoint"
    candidate.parent.mkdir(parents=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(workspace),
            "worktree",
            "add",
            "-b",
            "codex/c03-auto-checkpoint-test",
            str(candidate),
            baseline,
        ],
        check=True,
        capture_output=True,
    )
    owned_paths = [f"{project_name}/tests/core/test_continuity_execution_service.py"]
    if include_production_target:
        owned_paths.insert(0, f"{project_name}/auto_pm/core/target.py")
    if include_untracked_target:
        owned_paths.append(f"{project_name}/auto_pm/core/generated.py")
    work = WorkRegistryService(workspace, now=lambda: clock().isoformat())
    work.initialize("test")
    work.create_work(
        work_id="WORK-001",
        subject_project_id="SW-2026-008",
        kind=WorkKind.GOVERNANCE,
        title="C03 automatic checkpoint",
        owner="architect",
        scope_paths=owned_paths,
        source_fingerprint="sha256:c03",
        idempotency_key="create-c03-work",
        read_only=True,
    )
    service = ContinuityExecutionService(workspace, store=ContinuityStore(workspace, _clock=clock), now=clock)
    _start(
        service,
        owned_paths=owned_paths,
        worktree_path=str(candidate),
        git_head=baseline,
        declared_dirty_paths=[],
        observed_dirty_paths=[],
    )
    return candidate, candidate / project_name, service


def _append_auto_checkpoint(
    service: ContinuityExecutionService, project_root: Path, **changes: object
):
    values: dict[str, object] = {
        "checkpoint_id": "CP-AUTO-001",
        "run_id": "RUN-001",
        "owner_id": "agent-a",
        "lease_token": "lease-secret",
        "project_root": project_root,
    }
    values.update(changes)
    return service.append_verified_checkpoint(**values)  # type: ignore[arg-type]


def _quality_receipt_for_test(
    collector: EvidenceCollectionService,
    run,
    project_root: Path,
    *,
    exit_code: int | None = 0,
    output_summary: str = "injected C03 receipt",
) -> PythonQualityReceipt:
    """Return a content-bound receipt for negative C03 service-path tests.

    One positive C03 test runs the real C02 subprocesses.  The remaining tests
    deliberately inject a receipt so they exercise C03 rejection/replay logic
    without repeating three expensive tools for each failure permutation.
    """

    evidence = collector.collect(run)
    root = str(project_root.resolve())
    commands = {
        "pytest": (
            sys.executable,
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "-p",
            "no:cacheprovider",
            "-k",
            "append_verified_checkpoint",
            "tests/core/test_continuity_execution_service.py",
        ),
        "ruff": (sys.executable, "-m", "ruff", "check", "--no-cache"),
        "mypy": (sys.executable, "-m", "mypy", "--no-incremental"),
    }
    gates = tuple(
        PythonQualityGate(
            name=name,
            command=commands[name],
            cwd=root,
            exit_code=exit_code,
            output_digest=hashlib.sha256(
                f"{name}:{output_summary}".encode()
            ).hexdigest(),
            output_summary=output_summary,
        )
        for name in ("pytest", "ruff", "mypy")
    )
    payload = {
        "run_id": run.run_id,
        "baseline_git_head": run.git_head,
        "candidate_path": evidence.worktree_path,
        "project_root": root,
        "evidence_hash": evidence.content_hash,
        "gates": [
            {
                "name": gate.name,
                "command": list(gate.command),
                "cwd": gate.cwd,
                "exit_code": gate.exit_code,
                "output_digest": gate.output_digest,
                "output_summary": gate.output_summary,
            }
            for gate in gates
        ],
        "evidence_current": True,
        "evidence_error": None,
    }
    content_hash = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return PythonQualityReceipt(
        run_id=run.run_id,
        baseline_git_head=run.git_head,
        candidate_path=evidence.worktree_path,
        project_root=root,
        evidence_hash=evidence.content_hash,
        gates=gates,
        evidence_current=True,
        evidence_error=None,
        content_hash=content_hash,
    )


def _settlement_ready(
    root: Path,
    clock: Clock,
    *,
    target_run_ids: tuple[str, ...] = ("RUN-TARGET",),
    allowed_outcomes: tuple[RuntimeDecisionOutcome, ...] = (RuntimeDecisionOutcome.CANCELLED,),
    decision_paths: list[str] | None = None,
    recovery_scope_paths: list[str] | None = None,
    recovery_owned_paths: list[str] | None = None,
    decision_conditions: list[str] | None = None,
    decision_conclusion: str = "approved",
    change_status: str = "approved",
    target_change_id: str = "CHG-SCPT-2026-213",
    decision_attributes: str | None = None,
    decision_filter_command: str | None = None,
    decision_smudge_filter_command: str | None = None,
) -> ContinuityExecutionService:
    works, service = _services(root, clock)
    if decision_filter_command is not None:
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "config",
                "filter.decision.clean",
                decision_filter_command,
            ],
            check=True,
            capture_output=True,
        )
    if decision_smudge_filter_command is not None:
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "config",
                "filter.decision.smudge",
                decision_smudge_filter_command,
            ],
            check=True,
            capture_output=True,
        )
    tracked_support: tuple[str, ...] = ()
    if decision_attributes is not None:
        (root / ".gitattributes").write_text(
            decision_attributes,
            encoding="utf-8",
            errors="replace",
        )
        tracked_support = (".gitattributes",)
    _runtime_change(root, status=change_status)
    canonical_paths = ["auto_pm/core/a.py", ".auto-pm/continuity.db"]
    approved_paths = decision_paths or canonical_paths
    recovery_scope = recovery_scope_paths or canonical_paths
    recovery_owned = recovery_owned_paths or canonical_paths
    target_decision_id = "DEC-20260910-A2TARGT1"
    target_decision = DecisionPackageDTO(
        decision_id=target_decision_id,
        project_id="SW-2026-008",
        change_id=target_change_id,
        approved_scope="MODULE",
        approved_files=["auto_pm/core/a.py"],
        approver="fubai",
        approved_at=clock().isoformat(),
        decision_conclusion="approved",
    )
    target_decision_path = root / ".auto-pm" / "decisions" / f"{target_decision_id}.json"
    target_decision_path.parent.mkdir(parents=True, exist_ok=True)
    target_decision_path.write_bytes(
        json.dumps(target_decision.to_dict(), ensure_ascii=False, indent=2).encode("utf-8")
    )

    decision_id = "DEC-20260911-5C37A985"
    decision = DecisionPackageDTO(
        decision_id=decision_id,
        project_id="SW-2026-008",
        change_id="CHG-SCPT-2026-214",
        approved_scope="MODULE",
        approved_files=approved_paths,
        approver="fubai",
        approved_at=clock().isoformat(),
        decision_conclusion=decision_conclusion,
        conditions=list(decision_conditions or []),
        metadata={
            RUNTIME_CAPABILITY_KEY: RuntimeDecisionCapability(
                allowed_runtime_actions=(RuntimeDecisionAction.SETTLE_EXPIRED_RUN,),
                target_run_ids=target_run_ids,
                allowed_outcomes=allowed_outcomes,
            )
        },
    )
    decision_path = root / ".auto-pm" / "decisions" / f"{decision_id}.json"
    decision_path.write_bytes(
        json.dumps(decision.to_dict(), ensure_ascii=False, indent=2).encode("utf-8")
    )
    decision_paths = (
        f".auto-pm/decisions/{target_decision_id}.json",
        f".auto-pm/decisions/{decision_id}.json",
    )
    subprocess.run(
        ["git", "-C", str(root), "add", "-f", "--", *decision_paths, *tracked_support],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Continuity Test",
            "-c",
            "user.email=continuity@example.invalid",
            "commit",
            "-m",
            "bind runtime decisions",
        ],
        check=True,
        capture_output=True,
    )
    works.create_work(
        work_id="WORK-TARGET",
        subject_project_id="SW-2026-008",
        kind=WorkKind.GOVERNANCE,
        title="Historical target",
        owner="legacy-agent",
        scope_paths=["auto_pm/core/a.py"],
        source_fingerprint="sha256:target",
        idempotency_key="create-target-work",
    )
    works.authorize("WORK-TARGET", target_decision_id, "authorize-target-work")
    _start(
        service,
        run_id="RUN-TARGET",
        work_id="WORK-TARGET",
        executor_id="legacy-agent",
        lease_token="target-secret",
        lease_seconds=60,
        idempotency_key="create-target-run",
    )
    _start_evidence(
        service,
        run_id="RUN-TARGET",
        owner_id="legacy-agent",
        lease_token="target-secret",
        idempotency_key="record-target-start-evidence",
    )
    service.checkpoint(
        checkpoint_id="CP-TARGET",
        run_id="RUN-TARGET",
        owner_id="legacy-agent",
        lease_token="target-secret",
        summary="historical evidence",
        git_head=service._store.get_run("RUN-TARGET").git_head,
        dirty_paths=["auto_pm/core/a.py"],
        evidence=["historical checkpoint"],
        idempotency_key="checkpoint-target",
    )

    works.create_work(
        work_id="WORK-RECOVERY",
        subject_project_id="SW-2026-008",
        kind=WorkKind.GOVERNANCE,
        title="Authorized recovery",
        owner="recovery-agent",
        scope_paths=recovery_scope,
        source_fingerprint="sha256:recovery",
        idempotency_key="create-recovery-work",
    )
    works.authorize("WORK-RECOVERY", decision_id, "authorize-recovery-work")
    works.transition("WORK-RECOVERY", WorkState.IN_PROGRESS, "start-recovery-work")

    clock.value += timedelta(seconds=61)
    _start(
        service,
        run_id="RUN-RECOVERY",
        work_id="WORK-RECOVERY",
        executor_id="recovery-agent",
        lease_token="recovery-secret",
        lease_seconds=900,
        idempotency_key="create-recovery-run",
        owned_paths=recovery_owned,
    )
    _start_evidence(
        service,
        run_id="RUN-RECOVERY",
        owner_id="recovery-agent",
        lease_token="recovery-secret",
        idempotency_key="record-recovery-start-evidence",
    )
    return service


def _settle(service: ContinuityExecutionService, **changes):
    values = {
        "target_run_id": "RUN-TARGET",
        "recovery_run_id": "RUN-RECOVERY",
        "recovery_owner_id": "recovery-agent",
        "recovery_lease_token": "recovery-secret",
        "decision_id": "DEC-20260911-5C37A985",
        "outcome": RunState.CANCELLED,
        "reason": "Legacy A2 lease expired; preserve evidence and close forward.",
        "idempotency_key": "settle-target-run",
    }
    values.update(changes)
    return service.settle_expired_run(**values)


def _direct_settlement_values(service: ContinuityExecutionService, **changes):
    store = service._store
    target = store.get_run("RUN-TARGET")
    target_lease = store.get_lease("RUN-TARGET")
    target_work = store.get_work(target.work_id)
    recovery = store.get_run("RUN-RECOVERY")
    recovery_lease = store.get_lease("RUN-RECOVERY")
    recovery_work = store.get_work(recovery.work_id)
    decisions = DecisionService(service._root)
    target_decision, target_sha256 = decisions.get_decision_with_sha256(
        target_work.authorization_ref
    )
    recovery_decision, recovery_sha256 = decisions.get_decision_with_sha256(
        recovery_work.authorization_ref
    )
    values = {
        "target_run_id": target.run_id,
        "expected_target_state": target.state.value,
        "expected_target_version": target.version,
        "expected_target_lease_version": target_lease.version,
        "expected_target_work_id": target_work.work_id,
        "expected_target_work_version": target_work.version,
        "expected_target_work_scope_hash": store.authority_paths_hash(target_work.scope_paths),
        "recovery_run_id": recovery.run_id,
        "expected_recovery_run_version": recovery.version,
        "recovery_work_id": recovery_work.work_id,
        "expected_recovery_work_version": recovery_work.version,
        "expected_recovery_work_scope_hash": store.authority_paths_hash(recovery_work.scope_paths),
        "expected_recovery_owned_paths_hash": store.authority_paths_hash(recovery.owned_paths),
        "expected_recovery_git_head": recovery.git_head,
        "recovery_owner_id": recovery_lease.owner_id,
        "recovery_lease_token": recovery_lease.lease_token,
        "expected_recovery_lease_version": recovery_lease.version,
        "target_decision_id": target_decision.decision_id,
        "target_decision_sha256": target_sha256,
        "target_change_id": target_decision.change_id,
        "decision_id": recovery_decision.decision_id,
        "decision_sha256": recovery_sha256,
        "decision_change_id": recovery_decision.change_id,
        "decision_project_id": recovery_decision.project_id,
        "decision_approved_paths": tuple(recovery_decision.approved_files),
        "runtime_target_path": store.runtime_target_path(),
        "outcome": RunState.CANCELLED.value,
        "reason": "Legacy A2 lease expired; preserve evidence and close forward.",
        "idempotency_key": "direct-settle-target-run",
    }
    values.update(changes)
    return values


def _checkpoint_test_wal(root: Path) -> None:
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def _replace_run_created_event_with_legacy_payload(root: Path, run_id: str) -> None:
    db_path = root / ".auto-pm" / "continuity.db"
    with closing(sqlite3.connect(db_path)) as conn, conn:
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


def test_initializes_execution_tables_without_legacy_handoff_files(tmp_path: Path) -> None:
    clock = Clock()
    _services(tmp_path, clock)
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert {"run_items", "execution_leases", "checkpoints", "handoffs_v2"} <= tables
    assert not (tmp_path / ".auto-pm" / "handoffs").exists()


def test_run_binds_work_owner_paths_git_and_lease(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)

    run = _start(service)
    lease = service._store.get_lease(run.run_id)

    assert run.state == RunState.READY
    assert run.owned_paths == ("auto_pm/core/a.py",)
    assert lease.owner_id == "agent-a"
    assert datetime.fromisoformat(lease.expires_at) > clock()


def test_start_evidence_is_lease_bound_cas_and_idempotent(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    ready = _start(service)

    started = _start_evidence(service)
    replay = _start_evidence(service)

    assert ready.state is RunState.READY
    assert started.state is RunState.RUNNING
    assert started.version == ready.version + 1
    assert replay == started
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn:
        payload = conn.execute(
            "SELECT payload_json FROM events WHERE event_type='RUN_STARTED'"
        ).fetchone()[0]
    assert "lease-secret" not in payload


def test_start_evidence_rejects_expired_or_wrong_lease_without_state_change(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    _start(service, lease_seconds=60)
    clock.value += timedelta(seconds=61)

    with pytest.raises(ContinuityExecutionError, match="lease"):
        _start_evidence(service)

    assert service.get_run("RUN-001").state is RunState.READY


def test_terminal_runs_are_exposed_only_when_history_is_explicitly_requested(
    tmp_path: Path,
) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    run = _start(service)
    run = _start_evidence(service)
    verifying = service.transition_run(
        run.run_id,
        RunState.VERIFYING,
        "agent-a",
        "lease-secret",
        "verify-run",
    )
    service.transition_run(
        verifying.run_id,
        RunState.SUCCEEDED,
        "agent-a",
        "lease-secret",
        "finish-run",
    )

    assert service._store.list_runs("WORK-001") == ()
    history = service._store.list_runs("WORK-001", include_terminal=True)
    assert history[0].state is RunState.SUCCEEDED


def test_run_rejects_undeclared_dirty_and_out_of_scope_paths(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)

    with pytest.raises(ContinuityExecutionError, match="未声明"):
        _start(service, observed_dirty_paths=["tests/test_a.py"])
    with pytest.raises(ContinuityExecutionError, match="Work scope"):
        _start(
            service,
            run_id="RUN-002",
            idempotency_key="create-run-2",
            owned_paths=["outside.py"],
            observed_dirty_paths=[],
        )


def test_start_run_rejects_external_repository_and_direct_store_bypass(
    tmp_path: Path,
) -> None:
    control = tmp_path / "control"
    foreign = tmp_path / "foreign"
    control.mkdir()
    foreign.mkdir()
    clock = Clock()
    _, service = _services(control, clock)
    _git_root(foreign)
    foreign_head = subprocess.run(
        ["git", "-C", str(foreign), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.strip()

    with pytest.raises(ContinuityExecutionError, match="workspace 外|受管"):
        _start(
            service,
            worktree_path=str(foreign),
            git_head=foreign_head,
        )

    now = clock().isoformat()
    values = {
        "run_id": "RUN-DIRECT-BYPASS",
        "work_id": "WORK-001",
        "state": RunState.RUNNING.value,
        "executor_id": "agent-a",
        "adapter": "codex",
        "owned_paths_json": json.dumps(["auto_pm/core/a.py"]),
        "declared_dirty_paths_json": "[]",
        "git_head": foreign_head,
        "worktree_path": str(foreign),
        "version": 1,
        "created_at": now,
        "updated_at": now,
    }
    lease = {
        "run_id": "RUN-DIRECT-BYPASS",
        "owner_id": "agent-a",
        "lease_token": "direct-secret",
        "expires_at": (clock() + timedelta(seconds=900)).isoformat(),
        "version": 1,
        "updated_at": now,
    }
    with pytest.raises(ContinuityStoreError, match="workspace 外|受管"):
        service._store.create_run(values, lease, (), 900, "direct-bypass")
    assert service._store.list_runs("WORK-001") == ()


def test_start_run_accepts_governed_linked_worktree(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    linked = tmp_path / ".auto-pm" / "worktrees" / "RUN-LINKED"
    subprocess.run(
        ["git", "-C", str(tmp_path), "worktree", "add", "--detach", str(linked), "HEAD"],
        check=True,
        capture_output=True,
    )
    linked_head = subprocess.run(
        ["git", "-C", str(linked), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.strip()

    run = _start(
        service,
        git_head=linked_head,
        worktree_path=str(linked),
    )

    assert Path(run.worktree_path) == linked.resolve()


def test_start_run_resamples_head_and_dirty_instead_of_trusting_request(
    tmp_path: Path,
) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)

    with pytest.raises(ContinuityExecutionError, match="git_head"):
        _start(service, git_head="a" * 40)

    owned = tmp_path / "auto_pm" / "core" / "a.py"
    owned.parent.mkdir(parents=True)
    owned.write_text("dirty\n", encoding="utf-8")
    with pytest.raises(ContinuityExecutionError, match="observed_dirty_paths"):
        _start(service)
    assert service._store.list_runs("WORK-001") == ()


@pytest.mark.parametrize("drift", ["dirty", "head"])
def test_store_revalidates_git_snapshot_inside_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    original = service._store._validated_run_snapshot
    calls = 0

    def drift_after_initial_snapshot(*args, **kwargs):
        nonlocal calls
        calls += 1
        result = original(*args, **kwargs)
        if calls == 1:
            if drift == "dirty":
                owned = tmp_path / "auto_pm" / "core" / "a.py"
                owned.parent.mkdir(parents=True)
                owned.write_text("late dirty\n", encoding="utf-8")
            else:
                subprocess.run(
                    [
                        "git",
                        "-C",
                        str(tmp_path),
                        "-c",
                        "user.name=Continuity Test",
                        "-c",
                        "user.email=continuity@example.invalid",
                        "commit",
                        "--allow-empty",
                        "-m",
                        "late head drift",
                    ],
                    check=True,
                    capture_output=True,
                )
        return result

    monkeypatch.setattr(service._store, "_validated_run_snapshot", drift_after_initial_snapshot)

    with pytest.raises(ContinuityExecutionError, match="git_head|observed_dirty_paths"):
        _start(service)
    assert service._store.list_runs("WORK-001") == ()
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='RUN_CREATED'"
        ).fetchone()[0]
    assert count == 0


def test_store_rechecks_work_state_inside_run_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    original = service._store.create_run

    def close_work_then_create(*args, **kwargs):
        with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
            conn.execute("UPDATE work_items SET state='CLOSED' WHERE work_id='WORK-001'")
        _checkpoint_test_wal(tmp_path)
        return original(*args, **kwargs)

    monkeypatch.setattr(service._store, "create_run", close_work_then_create)

    with pytest.raises(ContinuityExecutionError, match="READY/IN_PROGRESS"):
        _start(service)
    assert service._store.list_runs("WORK-001") == ()


@pytest.mark.parametrize(
    ("target", "value"),
    [
        ("run_state", RunState.RUNNING.value),
        ("run_version", 2),
        ("lease_run", "RUN-OTHER"),
        ("lease_owner", "agent-other"),
        ("lease_version", 2),
        ("lease_token", "\u200b"),
        ("lease_seconds", 59),
    ],
)
def test_direct_store_rejects_forged_run_and_lease_invariants(
    tmp_path: Path,
    target: str,
    value: object,
) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    head = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.strip()
    now = "2000-01-01T00:00:00+00:00"
    values = {
        "run_id": "RUN-DIRECT",
        "work_id": "WORK-001",
        "state": RunState.READY.value,
        "executor_id": "agent-a",
        "adapter": "codex",
        "owned_paths_json": json.dumps(["auto_pm/core/a.py"]),
        "declared_dirty_paths_json": "[]",
        "git_head": head,
        "worktree_path": str(tmp_path),
        "version": 1,
        "created_at": now,
        "updated_at": now,
    }
    lease = {
        "run_id": "RUN-DIRECT",
        "owner_id": "agent-a",
        "lease_token": "direct-secret",
        "expires_at": "2099-01-01T00:00:00+00:00",
        "version": 1,
        "updated_at": now,
    }
    lease_seconds = 900
    if target == "run_state":
        values["state"] = value
    elif target == "run_version":
        values["version"] = value
    elif target == "lease_run":
        lease["run_id"] = value
    elif target == "lease_owner":
        lease["owner_id"] = value
    elif target == "lease_version":
        lease["version"] = value
    elif target == "lease_token":
        lease["lease_token"] = value
    else:
        lease_seconds = int(value)

    with pytest.raises(ContinuityStoreError):
        service._store.create_run(
            values,
            lease,
            (),
            lease_seconds,
            f"direct-{target}",
        )
    assert service._store.list_runs("WORK-001") == ()


def test_store_overwrites_run_audit_time_and_derives_lease_expiry(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    head = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.strip()
    forged = "2000-01-01T00:00:00+00:00"
    created = service._store.create_run(
        {
            "run_id": "RUN-DIRECT-AUDIT",
            "work_id": "WORK-001",
            "state": RunState.READY.value,
            "executor_id": "agent-a",
            "adapter": "codex",
            "owned_paths_json": json.dumps(["auto_pm/core/a.py"]),
            "declared_dirty_paths_json": "[]",
            "git_head": head,
            "worktree_path": str(tmp_path),
            "version": 1,
            "created_at": forged,
            "updated_at": forged,
        },
        {
            "run_id": "RUN-DIRECT-AUDIT",
            "owner_id": "agent-a",
            "lease_token": "direct-audit-secret",
            "expires_at": "2099-01-01T00:00:00+00:00",
            "version": 1,
            "updated_at": forged,
        },
        (),
        900,
        "direct-audit-run",
    )
    lease = service._store.get_lease(created.run_id)

    assert created.created_at == clock().isoformat()
    assert created.updated_at == clock().isoformat()
    assert lease.updated_at == clock().isoformat()
    assert lease.expires_at == (clock() + timedelta(seconds=900)).isoformat()
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
        event = conn.execute(
            "SELECT created_at, payload_json FROM events WHERE idempotency_key=?",
            ("direct-audit-run",),
        ).fetchone()
    assert event is not None
    assert event[0] == clock().isoformat()
    payload = json.loads(event[1])
    assert payload["created_at"] == clock().isoformat()
    assert payload["lease_expires_at"] == (clock() + timedelta(seconds=900)).isoformat()


def test_run_rejects_second_unexpired_active_run(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    _start(service, lease_seconds=60)
    clock.value += timedelta(seconds=61)

    with pytest.raises(ContinuityExecutionError, match="非终态 Run"):
        _start(
            service,
            run_id="RUN-002",
            lease_token="second-lease-secret",
            idempotency_key="create-run-2",
        )


def test_concurrent_distinct_run_creation_preserves_single_active_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock()
    _, first_service = _services(tmp_path, clock)
    second_service = ContinuityExecutionService(
        tmp_path,
        store=ContinuityStore(tmp_path, _clock=clock),
        now=clock,
    )
    barrier = threading.Barrier(2)
    original = ContinuityStore.create_run

    def synchronized_create_run(self, *args, **kwargs):
        barrier.wait(timeout=10)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ContinuityStore, "create_run", synchronized_create_run)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = tuple(
            pool.submit(
                _start,
                service,
                run_id=f"RUN-00{index}",
                executor_id=f"agent-{index}",
                lease_token=f"lease-secret-{index}",
                idempotency_key=f"create-run-{index}",
            )
            for index, service in enumerate((first_service, second_service), start=1)
        )
        outcomes: list[str] = []
        for future in futures:
            try:
                future.result()
                outcomes.append("created")
            except ContinuityExecutionError as error:
                outcomes.append(str(error))

    assert outcomes.count("created") == 1
    assert sum("非终态 Run" in outcome for outcome in outcomes) == 1
    assert len(first_service._store.list_runs("WORK-001")) == 1
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='RUN_CREATED'"
        ).fetchone()[0]
    assert count == 1


def test_start_run_exact_replay_survives_dirty_head_advance_and_expiry(
    tmp_path: Path,
) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    created = _start(service, lease_seconds=60)
    owned = tmp_path / "auto_pm" / "core" / "a.py"
    owned.parent.mkdir(parents=True)
    owned.write_text("owned change\n", encoding="utf-8", errors="replace")

    assert _start(service, lease_seconds=60) == created
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "--", "auto_pm/core/a.py"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=Continuity Test",
            "-c",
            "user.email=continuity@example.invalid",
            "commit",
            "-m",
            "successor commit",
        ],
        check=True,
        capture_output=True,
    )
    clock.value += timedelta(seconds=61)

    assert _start(service, git_head=created.git_head, lease_seconds=60) == created
    with pytest.raises(ContinuityExecutionError, match="token identity|owner.*token"):
        _start(
            service,
            git_head=created.git_head,
            lease_token="wrong-secret",
            lease_seconds=60,
        )
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='RUN_CREATED'"
        ).fetchone()[0]
    assert count == 1


def test_start_run_exact_replay_survives_transition_renewal_and_handoff(
    tmp_path: Path,
) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    created = _start(service)
    renewed = service.renew_lease(
        created.run_id,
        "agent-a",
        "lease-secret",
        1200,
        "renew-before-replay",
    )

    assert _start(service) == created
    persisted_lease = service._store.get_lease(created.run_id)
    assert persisted_lease.run_id == renewed.run_id
    assert persisted_lease.owner_id == renewed.owner_id
    assert persisted_lease.expires_at == renewed.expires_at
    assert persisted_lease.version == renewed.version
    assert persisted_lease.updated_at == renewed.updated_at
    _start_evidence(service, idempotency_key="record-start-before-replay")
    verifying = service.transition_run(
        created.run_id,
        RunState.VERIFYING,
        "agent-a",
        "lease-secret",
        "verify-before-replay",
    )

    assert _start(service) == verifying
    checkpoint = _checkpoint(
        service,
        checkpoint_id="CP-HANDOFF-REPLAY",
        idempotency_key="checkpoint-handoff-replay",
    )
    handoff = service.create_handoff(
        handoff_id="HO-START-REPLAY",
        checkpoint_id=checkpoint.checkpoint_id,
        from_owner="agent-a",
        to_owner="agent-b",
        lease_token="lease-secret",
        idempotency_key="handoff-before-replay",
    )
    accepted = service.accept_handoff(
        handoff_id=handoff.handoff_id,
        receiver_id="agent-b",
        new_lease_token="receiver-secret",
        lease_seconds=900,
        idempotency_key="accept-before-replay",
    )

    assert _start(service) == verifying
    assert service._store.get_lease(created.run_id) == accepted
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
        event = conn.execute(
            "SELECT payload_json FROM events WHERE event_type='RUN_CREATED'"
        ).fetchone()
        count = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='RUN_CREATED'"
        ).fetchone()[0]
    assert event is not None
    assert "lease-secret" not in event[0]
    assert "receiver-secret" not in event[0]
    assert count == 1


def test_start_run_replays_provable_legacy_receipt_and_fails_after_lease_rotation(
    tmp_path: Path,
) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    created = _start(service)
    _replace_run_created_event_with_legacy_payload(tmp_path, created.run_id)

    legacy = service._store.get_run(created.run_id)
    assert _start(service) == legacy
    with pytest.raises(ContinuityExecutionError, match="语义不一致"):
        _start(service, adapter="cursor")
    renewed = service.renew_lease(
        created.run_id,
        "agent-a",
        "lease-secret",
        900,
        "renew-legacy-run",
    )
    assert renewed.version == 2
    stored_lease = service._store.get_lease(created.run_id)
    assert (
        stored_lease.run_id,
        stored_lease.owner_id,
        stored_lease.expires_at,
        stored_lease.version,
        stored_lease.updated_at,
    ) == (
        renewed.run_id,
        renewed.owner_id,
        renewed.expires_at,
        renewed.version,
        renewed.updated_at,
    )
    assert stored_lease.lease_token == "lease-secret"
    with pytest.raises(ContinuityExecutionError, match="LEGACY_REPLAY_UNPROVABLE"):
        _start(service)


def test_start_run_exact_replay_survives_removed_linked_worktree(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    linked = tmp_path / ".auto-pm" / "worktrees" / "pruned-run"
    subprocess.run(
        ["git", "-C", str(tmp_path), "worktree", "add", "--detach", str(linked), "HEAD"],
        check=True,
        capture_output=True,
    )
    created = _start(service, worktree_path=str(linked))
    subprocess.run(
        ["git", "-C", str(tmp_path), "worktree", "remove", "--force", str(linked)],
        check=True,
        capture_output=True,
    )

    assert (
        _start(
            service,
            worktree_path=str(linked),
            git_head=created.git_head,
        )
        == created
    )
    with pytest.raises(ContinuityExecutionError, match="语义不一致"):
        _start(
            service,
            worktree_path=str(linked.parent / "different"),
            git_head=created.git_head,
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"work_id": "WORK-OTHER"},
        {"adapter": "cursor"},
        {"owned_paths": ["tests/test_a.py"]},
        {"git_head": "a" * 40},
        {"lease_seconds": 901},
    ],
)
def test_start_run_replay_rejects_semantic_drift(
    tmp_path: Path,
    changes: dict[str, object],
) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    _start(service)

    with pytest.raises(ContinuityExecutionError, match="语义不一致"):
        _start(service, **changes)
    assert len(service._store.list_runs("WORK-001")) == 1


@pytest.mark.parametrize("key", ["", " ", "x\n", "x\u200b"])
def test_start_run_rejects_noncanonical_idempotency_key_before_write(
    tmp_path: Path,
    key: str,
) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)

    with pytest.raises(ContinuityExecutionError, match="idempotency_key"):
        _start(service, idempotency_key=key)
    with pytest.raises(ContinuityStoreError, match="idempotency_key"):
        service._store.create_run({}, {}, (), 900, key)
    assert service._store.list_runs("WORK-001") == ()
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='RUN_CREATED'"
        ).fetchone()[0]
    assert count == 0


def test_same_run_id_with_new_key_is_controlled_and_preserves_one_event(
    tmp_path: Path,
) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    created = _start(service)

    with pytest.raises(ContinuityExecutionError, match="原 idempotency_key"):
        _start(service, idempotency_key="create-run-other-key")
    values = {
        "run_id": created.run_id,
        "work_id": created.work_id,
        "state": RunState.READY.value,
        "executor_id": created.executor_id,
        "adapter": created.adapter,
        "owned_paths_json": json.dumps(created.owned_paths),
        "declared_dirty_paths_json": json.dumps(created.declared_dirty_paths),
        "git_head": created.git_head,
        "worktree_path": created.worktree_path,
        "version": 1,
        "created_at": "2000-01-01T00:00:00+00:00",
        "updated_at": "2000-01-01T00:00:00+00:00",
    }
    lease = {
        "run_id": created.run_id,
        "owner_id": created.executor_id,
        "lease_token": "lease-secret",
        "expires_at": "2099-01-01T00:00:00+00:00",
        "version": 1,
        "updated_at": "2000-01-01T00:00:00+00:00",
    }
    with pytest.raises(ContinuityStoreError, match="原 idempotency_key"):
        service._store.create_run(values, lease, (), 900, "direct-other-key")
    assert len(service._store.list_runs("WORK-001")) == 1
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM events WHERE event_type='RUN_CREATED'").fetchone()[0]
            == 1
        )


def test_concurrent_same_run_and_key_returns_one_exact_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock()
    _, first_service = _services(tmp_path, clock)
    second_service = ContinuityExecutionService(
        tmp_path,
        store=ContinuityStore(tmp_path, _clock=clock),
        now=clock,
    )
    barrier = threading.Barrier(2)
    original = ContinuityStore.create_run

    def synchronized_create_run(self, *args, **kwargs):
        barrier.wait(timeout=10)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ContinuityStore, "create_run", synchronized_create_run)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = tuple(pool.submit(_start, service) for service in (first_service, second_service))
        results = tuple(future.result() for future in futures)

    assert results[0] == results[1]
    assert len(first_service._store.list_runs("WORK-001")) == 1
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM events WHERE event_type='RUN_CREATED'").fetchone()[0]
            == 1
        )


def test_terminal_sibling_with_future_lease_does_not_block_new_run(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    first = _start(service)
    started = _start_evidence(service)
    verifying = service.transition_run(
        started.run_id,
        RunState.VERIFYING,
        "agent-a",
        "lease-secret",
        "verify-first",
    )
    service.transition_run(
        verifying.run_id,
        RunState.SUCCEEDED,
        "agent-a",
        "lease-secret",
        "finish-first",
    )

    second = _start(
        service,
        run_id="RUN-002",
        lease_token="second-secret",
        idempotency_key="create-second",
    )
    assert first.state is RunState.READY
    assert second.state is RunState.READY
    assert len(service._store.list_runs("WORK-001", include_terminal=True)) == 2


def test_expired_or_wrong_owner_lease_fails_closed(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    _start(service, lease_seconds=60)

    with pytest.raises(ContinuityExecutionError, match="ownership"):
        service.renew_lease("RUN-001", "agent-b", "lease-secret", 60, "wrong-owner")
    clock.value += timedelta(seconds=61)
    with pytest.raises(ContinuityExecutionError, match="过期"):
        service.renew_lease("RUN-001", "agent-a", "lease-secret", 60, "expired")


def test_store_lease_renewal_uses_trusted_time_and_cannot_revive_expired_lease(
    tmp_path: Path,
) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    _start(service, lease_seconds=60)

    renewed = service._store.renew_lease(
        "RUN-001",
        "agent-a",
        "lease-secret",
        900,
        "direct-renew",
    )
    assert renewed.updated_at == clock().isoformat()
    assert renewed.expires_at == (clock() + timedelta(seconds=900)).isoformat()
    clock.value += timedelta(seconds=901)
    assert (
        service._store.renew_lease(
            "RUN-001",
            "agent-a",
            "lease-secret",
            900,
            "direct-renew",
        )
        == renewed
    )
    with pytest.raises(ContinuityStoreError, match="过期"):
        service._store.renew_lease(
            "RUN-001",
            "agent-a",
            "lease-secret",
            900,
            "direct-renew-after-expiry",
        )
    with pytest.raises(ContinuityStoreError, match="语义不一致"):
        service._store.renew_lease(
            "RUN-001",
            "agent-a",
            "wrong-secret",
            900,
            "direct-renew",
        )
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
        payload = conn.execute(
            "SELECT payload_json FROM events WHERE idempotency_key='direct-renew'"
        ).fetchone()[0]
        count = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='LEASE_RENEWED'"
        ).fetchone()[0]
    assert "lease-secret" not in payload
    assert count == 1


def test_lease_renewal_receipt_is_exact_secret_free_and_version_bound(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    _start(service, lease_seconds=900)

    first = service.renew_lease(
        "RUN-001",
        "agent-a",
        "lease-secret",
        900,
        "e04-exact-renew",
        expected_version=1,
    )
    replay = service.renew_lease(
        "RUN-001",
        "agent-a",
        "lease-secret",
        900,
        "e04-exact-renew",
        expected_version=1,
    )

    assert replay == first
    assert first.schema_version == "lease-renewal-receipt.v1"
    assert "lease-secret" not in first.model_dump_json()
    with pytest.raises(ContinuityExecutionError, match="version"):
        service.renew_lease(
            "RUN-001",
            "agent-a",
            "lease-secret",
            900,
            "e04-stale-version",
            expected_version=1,
        )


def test_checkpoint_is_sequenced_and_rejects_baseline_drift(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    _start(service)

    first = _checkpoint(service)
    second = _checkpoint(
        service,
        checkpoint_id="CP-002",
        idempotency_key="checkpoint-2",
        evidence=["ruff:0"],
    )

    assert (first.sequence, second.sequence) == (1, 2)
    with pytest.raises(ContinuityExecutionError, match="baseline drift"):
        _checkpoint(
            service,
            checkpoint_id="CP-003",
            idempotency_key="checkpoint-3",
            git_head="b" * 40,
        )


def test_checkpoint_allows_new_owned_changes_and_rejects_foreign_paths(tmp_path: Path) -> None:
    """A clean Run may create owned changes; foreign paths remain fail-closed."""
    clock = Clock()
    _, service = _services(tmp_path, clock)
    _start(service, declared_dirty_paths=[], observed_dirty_paths=[])

    checkpoint = _checkpoint(service)

    assert checkpoint.dirty_paths == ("auto_pm/core/a.py",)
    with pytest.raises(ContinuityExecutionError, match="owned_paths"):
        _checkpoint(
            service,
            checkpoint_id="CP-002",
            dirty_paths=["tests/test_a.py"],
            idempotency_key="checkpoint-foreign-path",
        )


def test_append_verified_checkpoint_builds_complete_evidence_and_replays(tmp_path: Path) -> None:
    candidate, project_root, service = _c03_auto_checkpoint_service(
        tmp_path, include_untracked_target=True
    )
    source = candidate / "project" / "auto_pm" / "core" / "target.py"
    source.write_text("def value() -> int:\n    return 2\n", encoding="utf-8", errors="replace")
    subprocess.run(
        ["git", "-C", str(candidate), "add", "project/auto_pm/core/target.py"],
        check=True,
        capture_output=True,
    )
    source.write_text("def value() -> int:\n    return 3\n", encoding="utf-8", errors="replace")
    generated = candidate / "project" / "auto_pm" / "core" / "generated.py"
    generated.write_text(
        "def generated() -> int:\n    return 7\n", encoding="utf-8", errors="replace"
    )

    checkpoint = _append_auto_checkpoint(service, project_root)

    assert checkpoint.sequence == 1
    assert checkpoint.summary == "System-generated content-bound checkpoint for Run RUN-001"
    assert checkpoint.dirty_paths == (
        "project/auto_pm/core/generated.py",
        "project/auto_pm/core/target.py",
    )
    assert len(checkpoint.evidence) == 1
    envelope = json.loads(checkpoint.evidence[0])
    assert envelope["schema_version"] == "checkpoint-evidence.v1"
    assert envelope["collection_hash"]
    assert envelope["receipt_hash"]
    assert envelope["envelope_hash"]
    collection = envelope["collection"]
    assert collection["baseline_git_head"] == checkpoint.git_head
    assert collection["staged_paths"] == ["project/auto_pm/core/target.py"]
    assert collection["unstaged_paths"] == ["project/auto_pm/core/target.py"]
    assert collection["untracked_paths"] == ["project/auto_pm/core/generated.py"]
    assert collection["untracked_content_hashes"][0]["path"] == "project/auto_pm/core/generated.py"
    assert collection["untracked_content_hashes"][0]["sha256"]
    assert collection["staged_diff_sha256"]
    assert collection["unstaged_diff_sha256"]
    receipt = envelope["quality_receipt"]
    assert receipt["status"] == "PASS"
    assert receipt["evidence_current"] is True
    assert [gate["name"] for gate in receipt["gates"]] == ["pytest", "ruff", "mypy"]
    assert all(gate["exit_code"] == 0 for gate in receipt["gates"])
    assert all(gate["command"] and gate["cwd"] for gate in receipt["gates"])
    assert all(gate["output_digest"] for gate in receipt["gates"])
    assert receipt["gates"][0]["command"][-3:] == [
        "-k",
        "append_verified_checkpoint",
        "tests/core/test_continuity_execution_service.py",
    ]

    run = service._store.get_run("RUN-001")
    current = EvidenceCollectionService(service._root).collect(run)
    internal_key = service._c03_checkpoint_idempotency_key(
        run, checkpoint.checkpoint_id, current.content_hash
    )
    assert service._store.event_aggregate_for_key(internal_key) == ("run", "RUN-001")

    replay = _append_auto_checkpoint(service, project_root)

    assert replay == checkpoint
    assert replay.sequence == 1


def test_append_verified_checkpoint_replays_unicode_owned_paths_and_rejects_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, project_root, service = _c03_auto_checkpoint_service(
        tmp_path, project_name="中文项目"
    )
    source = project_root / "auto_pm" / "core" / "target.py"
    source.write_text(
        "def value() -> int:\n    return 2\n", encoding="utf-8", errors="replace"
    )
    monkeypatch.setattr(
        EvidenceCollectionService,
        "run_c03_checkpoint_quality_gates",
        _quality_receipt_for_test,
    )

    checkpoint = _append_auto_checkpoint(service, project_root)
    collector = EvidenceCollectionService(service._root)
    run = service._store.get_run("RUN-001")
    current = collector.collect(run)

    assert "中文项目" in checkpoint.evidence[0]
    assert collector.checkpoint_evidence_is_current(
        checkpoint.evidence[0], current, run, project_root
    )
    assert _append_auto_checkpoint(service, project_root) == checkpoint

    source.write_text(
        "def value() -> int:\n    return 3\n", encoding="utf-8", errors="replace"
    )
    stale = collector.collect(run)
    assert not collector.checkpoint_evidence_is_current(
        checkpoint.evidence[0], stale, run, project_root
    )
    with pytest.raises(ContinuityExecutionError, match="identity.*不一致"):
        _append_auto_checkpoint(service, project_root)


def test_append_verified_checkpoint_does_not_accept_caller_idempotency_key(
    tmp_path: Path,
) -> None:
    _, project_root, service = _c03_auto_checkpoint_service(tmp_path)

    with pytest.raises(TypeError, match="idempotency_key"):
        _append_auto_checkpoint(
            service, project_root, idempotency_key="caller-controlled-key"
        )


def test_append_verified_checkpoint_rejects_store_collision_return(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, project_root, service = _c03_auto_checkpoint_service(tmp_path)
    monkeypatch.setattr(
        EvidenceCollectionService,
        "run_c03_checkpoint_quality_gates",
        _quality_receipt_for_test,
    )
    checkpoint = _append_auto_checkpoint(service, project_root)
    observed_keys: list[str] = []

    def collision_return(
        values: dict[str, object], idempotency_key: str, _now: str
    ) -> CheckpointItem:
        observed_keys.append(idempotency_key)
        return CheckpointItem(
            checkpoint_id="CP-COLLISION",
            run_id=str(values["run_id"]),
            sequence=checkpoint.sequence,
            summary=str(values["summary"]),
            git_head=str(values["git_head"]),
            dirty_paths=tuple(json.loads(str(values["dirty_paths_json"]))),
            evidence=("collision-evidence",),
            created_at=str(values["created_at"]),
        )

    monkeypatch.setattr(service._store, "create_checkpoint", collision_return)

    with pytest.raises(ContinuityExecutionError, match="identity.*evidence"):
        _append_auto_checkpoint(service, project_root)
    assert observed_keys and observed_keys[0].startswith("c03-auto-checkpoint:")


@pytest.mark.parametrize("changed_path", ["target.py", "generated.py"])
def test_append_verified_checkpoint_refuses_replay_after_owned_content_changes(
    tmp_path: Path, changed_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate, project_root, service = _c03_auto_checkpoint_service(
        tmp_path, include_untracked_target=True
    )
    generated = candidate / "project" / "auto_pm" / "core" / "generated.py"
    generated.write_text(
        "def generated() -> int:\n    return 7\n", encoding="utf-8", errors="replace"
    )
    monkeypatch.setattr(
        EvidenceCollectionService,
        "run_c03_checkpoint_quality_gates",
        _quality_receipt_for_test,
    )
    checkpoint = _append_auto_checkpoint(service, project_root)
    changed = candidate / "project" / "auto_pm" / "core" / changed_path
    changed.write_text(
        "def changed() -> int:\n    return 9\n", encoding="utf-8", errors="replace"
    )

    with pytest.raises(ContinuityExecutionError, match="identity.*不一致"):
        _append_auto_checkpoint(service, project_root)

    assert service._store.get_checkpoint(checkpoint.checkpoint_id) == checkpoint


def test_append_verified_checkpoint_rejects_receipt_stale_before_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate, project_root, service = _c03_auto_checkpoint_service(tmp_path)
    source = candidate / "project" / "auto_pm" / "core" / "target.py"

    def run_then_change(
        collector: EvidenceCollectionService, run, root: Path
    ):
        receipt = _quality_receipt_for_test(collector, run, root)
        source.write_text(
            "def value() -> int:\n    return 2\n", encoding="utf-8", errors="replace"
        )
        return receipt

    monkeypatch.setattr(
        EvidenceCollectionService, "run_c03_checkpoint_quality_gates", run_then_change
    )

    with pytest.raises(ContinuityExecutionError, match="质量收据已失效"):
        _append_auto_checkpoint(service, project_root)
    with pytest.raises(ContinuityStoreError, match="Checkpoint 不存在"):
        service._store.get_checkpoint("CP-AUTO-001")


def test_append_verified_checkpoint_rejects_failed_or_missing_quality_receipts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, project_root, failed_service = _c03_auto_checkpoint_service(tmp_path / "failed")
    monkeypatch.setattr(
        EvidenceCollectionService,
        "run_c03_checkpoint_quality_gates",
        lambda collector, run, root: _quality_receipt_for_test(
            collector,
            run,
            root,
            exit_code=1,
            output_summary="injected failed quality gate",
        ),
    )
    with pytest.raises(ContinuityExecutionError, match="质量收据"):
        _append_auto_checkpoint(failed_service, project_root)
    with pytest.raises(ContinuityStoreError, match="Checkpoint 不存在"):
        failed_service._store.get_checkpoint("CP-AUTO-001")

    _, missing_project_root, missing_service = _c03_auto_checkpoint_service(tmp_path / "missing")
    monkeypatch.setattr(
        EvidenceCollectionService,
        "run_c03_checkpoint_quality_gates",
        lambda collector, run, root: _quality_receipt_for_test(
            collector,
            run,
            root,
            exit_code=None,
            output_summary="missing approved quality target",
        ),
    )
    with pytest.raises(ContinuityExecutionError, match="质量收据"):
        _append_auto_checkpoint(missing_service, missing_project_root)
    with pytest.raises(ContinuityStoreError, match="Checkpoint 不存在"):
        missing_service._store.get_checkpoint("CP-AUTO-001")


def test_append_verified_checkpoint_rejects_quality_tool_launch_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, project_root, service = _c03_auto_checkpoint_service(tmp_path)
    monkeypatch.setattr(
        EvidenceCollectionService,
        "run_c03_checkpoint_quality_gates",
        lambda collector, run, root: _quality_receipt_for_test(
            collector,
            run,
            root,
            exit_code=None,
            output_summary="launch error: injected tool unavailable",
        ),
    )

    with pytest.raises(ContinuityExecutionError, match="质量收据"):
        _append_auto_checkpoint(service, project_root)
    with pytest.raises(ContinuityStoreError, match="Checkpoint 不存在"):
        service._store.get_checkpoint("CP-AUTO-001")


def test_append_verified_checkpoint_rejects_narrow_project_root(tmp_path: Path) -> None:
    candidate, project_root, service = _c03_auto_checkpoint_service(tmp_path)
    narrow_root = project_root / "auto_pm"
    (narrow_root / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n", encoding="utf-8", errors="replace"
    )

    with pytest.raises(ContinuityExecutionError, match="未覆盖.*owned path"):
        _append_auto_checkpoint(service, narrow_root)
    assert candidate.exists()
    with pytest.raises(ContinuityStoreError, match="Checkpoint 不存在"):
        service._store.get_checkpoint("CP-AUTO-001")


def test_append_verified_checkpoint_rejects_project_root_without_pyproject(
    tmp_path: Path,
) -> None:
    candidate, _, service = _c03_auto_checkpoint_service(tmp_path)

    with pytest.raises(ContinuityExecutionError, match="pyproject.toml"):
        _append_auto_checkpoint(service, candidate)
    with pytest.raises(ContinuityStoreError, match="Checkpoint 不存在"):
        service._store.get_checkpoint("CP-AUTO-001")


def test_append_verified_checkpoint_rejects_missing_fixed_c03_target(tmp_path: Path) -> None:
    _, project_root, service = _c03_auto_checkpoint_service(tmp_path)
    (project_root / "tests" / "core" / "test_continuity_execution_service.py").unlink()

    with pytest.raises(ContinuityExecutionError, match="缺少固定 pytest target"):
        _append_auto_checkpoint(service, project_root)
    with pytest.raises(ContinuityStoreError, match="Checkpoint 不存在"):
        service._store.get_checkpoint("CP-AUTO-001")


def test_append_verified_checkpoint_rejects_zero_fixed_c03_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, project_root, service = _c03_auto_checkpoint_service(
        tmp_path, c03_selector_match=False
    )
    commands: list[tuple[str, ...]] = []

    def zero_selection_gate(
        name: str, command: tuple[str, ...], root: Path, target_error: str | None
    ) -> PythonQualityGate:
        assert target_error is None
        if name == "pytest":
            commands.append(command)
        return PythonQualityGate(
            name=name,
            command=command,
            cwd=str(root),
            exit_code=5 if name == "pytest" else 0,
            output_digest=f"{name}-digest",
            output_summary="no C03 tests selected" if name == "pytest" else "passed",
        )

    monkeypatch.setattr(
        EvidenceCollectionService, "_run_quality_gate", staticmethod(zero_selection_gate)
    )

    with pytest.raises(ContinuityExecutionError, match="质量收据为 PASS"):
        _append_auto_checkpoint(service, project_root)
    assert commands and commands[0][-3:] == (
        "-k",
        "append_verified_checkpoint",
        "tests/core/test_continuity_execution_service.py",
    )
    with pytest.raises(ContinuityStoreError, match="Checkpoint 不存在"):
        service._store.get_checkpoint("CP-AUTO-001")


def test_handoff_v2_points_to_checkpoint_and_is_hash_signed(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    _start(service)
    checkpoint = _checkpoint(service)

    handoff = service.create_handoff(
        handoff_id="HO-001",
        checkpoint_id=checkpoint.checkpoint_id,
        from_owner="agent-a",
        to_owner="agent-b",
        lease_token="lease-secret",
        idempotency_key="handoff-1",
    )

    assert handoff.schema_version == "handoff.v2"
    assert handoff.checkpoint_id == "CP-001"
    assert len(handoff.snapshot_hash) == 64
    assert not (tmp_path / ".auto-pm" / "handoffs").exists()

    lease = service.accept_handoff(
        handoff_id="HO-001",
        receiver_id="agent-b",
        new_lease_token="receiver-secret",
        lease_seconds=900,
        idempotency_key="accept-1",
    )
    assert lease.owner_id == "agent-b"


def test_checkpoint_bound_handoff_creates_a_new_receiver_lease(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    _start(service)
    checkpoint = _checkpoint(service)

    handoff, receiver_lease = service.create_checkpoint_bound_handoff(
        checkpoint_id=checkpoint.checkpoint_id,
        from_owner="agent-a",
        to_owner="agent-b",
        lease_token="lease-secret",
        new_lease_token="receiver-secret",
        lease_seconds=900,
        idempotency_key="checkpoint-bound-handoff",
    )

    assert handoff.schema_version == "handoff.v2"
    assert handoff.checkpoint_id == checkpoint.checkpoint_id
    assert handoff.work_id == "WORK-001"
    assert handoff.git_head == checkpoint.git_head
    assert receiver_lease.run_id == "RUN-001"
    assert receiver_lease.owner_id == "agent-b"
    assert "lease-secret" not in handoff.model_dump_json()
    with pytest.raises(ContinuityExecutionError, match="ownership"):
        service.renew_lease("RUN-001", "agent-a", "lease-secret", 900, "old-owner")


def test_legacy_handoff_is_read_only_and_unknown_schema_is_rejected(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    old = tmp_path / "old.json"
    old.write_text(
        json.dumps({"schema_version": "handoff.v1", "request_id": "OLD"}), encoding="utf-8"
    )

    loaded = service.load_legacy_handoff(old)
    assert loaded["compatibility"] == "READ_ONLY"
    old.write_text(json.dumps({"schema_version": "handoff.v9"}), encoding="utf-8")
    with pytest.raises(ContinuityExecutionError, match="未知"):
        service.load_legacy_handoff(old)


def test_run_state_machine_rejects_terminal_reopen(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    _start(service)
    _start_evidence(service)
    service.transition_run("RUN-001", RunState.VERIFYING, "agent-a", "lease-secret", "verify")
    service.transition_run("RUN-001", RunState.SUCCEEDED, "agent-a", "lease-secret", "succeed")

    with pytest.raises(ContinuityExecutionError, match="非法"):
        service.transition_run("RUN-001", RunState.RUNNING, "agent-a", "lease-secret", "reopen")
    terminal = service._store.get_run("RUN-001")
    with pytest.raises(ContinuityStoreError, match="非法"):
        service._store.transition_run(
            terminal.run_id,
            terminal.version,
            RunState.RUNNING.value,
            "direct-reopen",
            "2000-01-01T00:00:00+00:00",
        )
    with pytest.raises(ContinuityStoreError, match="语义不一致"):
        service._store.transition_run(
            "RUN-001",
            1,
            RunState.BLOCKED.value,
            "verify",
            "2000-01-01T00:00:00+00:00",
        )


def test_fake_handoff_row_cannot_seize_lease(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    run = _start(service)
    checkpoint = _checkpoint(service)
    lease_before = service._store.get_lease(run.run_id)
    with pytest.raises(ContinuityStoreError, match="ownership"):
        service._store.create_handoff(
            handoff_id="HO-WRONG-TOKEN",
            checkpoint_id=checkpoint.checkpoint_id,
            from_owner="agent-a",
            to_owner="agent-b",
            lease_token="wrong-secret",
            idempotency_key="fake-handoff-create",
        )
    unsigned = {
        "handoff_id": "HO-FAKE-ROW",
        "work_id": run.work_id,
        "run_id": run.run_id,
        "checkpoint_id": checkpoint.checkpoint_id,
        "from_owner": "agent-a",
        "to_owner": "agent-b",
        "owned_paths_json": json.dumps(run.owned_paths, ensure_ascii=False),
        "git_head": run.git_head,
        "worktree_path": run.worktree_path,
        "lease_expires_at": lease_before.expires_at,
        "created_at": clock().isoformat(),
    }
    canonical = json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
        conn.execute(
            """INSERT INTO handoffs_v2 (
                handoff_id, work_id, run_id, checkpoint_id, from_owner, to_owner,
                owned_paths_json, git_head, worktree_path, lease_expires_at,
                snapshot_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                unsigned["handoff_id"],
                unsigned["work_id"],
                unsigned["run_id"],
                unsigned["checkpoint_id"],
                unsigned["from_owner"],
                unsigned["to_owner"],
                unsigned["owned_paths_json"],
                unsigned["git_head"],
                unsigned["worktree_path"],
                unsigned["lease_expires_at"],
                hashlib.sha256(canonical.encode()).hexdigest(),
                unsigned["created_at"],
            ),
        )
    with pytest.raises(ContinuityStoreError, match="缺少.*回执|创建回执"):
        service._store.transfer_lease(
            "HO-FAKE-ROW",
            "agent-b",
            "seized-secret",
            900,
            "fake-transfer",
        )
    assert service._store.get_lease(run.run_id) == lease_before


def test_settle_expired_run_preserves_forensic_state_and_emits_secret_free_event(
    tmp_path: Path,
) -> None:
    clock = Clock()
    service = _settlement_ready(tmp_path, clock)
    target_before = service._store.get_run("RUN-TARGET")
    target_lease = service._store.get_lease("RUN-TARGET")
    checkpoint = service._store.latest_checkpoint("RUN-TARGET")

    settled = _settle(service)

    assert settled.state is RunState.CANCELLED
    assert settled.version == target_before.version + 1
    assert service._store.get_lease("RUN-TARGET") == target_lease
    assert service._store.latest_checkpoint("RUN-TARGET") == checkpoint
    assert service._store.get_run("RUN-RECOVERY").state is RunState.RUNNING
    assert service._store.list_runs("WORK-TARGET") == ()
    assert service._store.list_runs("WORK-TARGET", include_terminal=True) == (settled,)
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
        rows = conn.execute(
            "SELECT payload_json FROM events WHERE event_type='RUN_EXPIRED_SETTLED'"
        ).fetchall()
    assert len(rows) == 1
    assert "target-secret" not in rows[0][0]
    assert "recovery-secret" not in rows[0][0]
    payload = json.loads(rows[0][0])
    assert payload["runtime_target_path"] == ".auto-pm/continuity.db"
    assert len(payload["recovery"]["owned_paths_hash"]) == 64
    assert payload["recovery"]["git_head"] == service._store.get_run("RUN-RECOVERY").git_head


def test_direct_store_settlement_succeeds_without_caller_transaction_time(tmp_path: Path) -> None:
    clock = Clock()
    service = _settlement_ready(tmp_path, clock)
    values = _direct_settlement_values(service)

    assert "now" not in ContinuityStore.settle_expired_run.__annotations__
    assert service._store.settle_expired_run(**values).state is RunState.CANCELLED


def test_settlement_accepts_clean_crlf_decisions_bound_to_lf_head_blobs(
    tmp_path: Path,
) -> None:
    clock = Clock()
    service = _settlement_ready(
        tmp_path,
        clock,
        decision_attributes=".auto-pm/decisions/*.json text eol=crlf\n",
    )
    decision_paths = (
        ".auto-pm/decisions/DEC-20260910-A2TARGT1.json",
        ".auto-pm/decisions/DEC-20260911-5C37A985.json",
    )
    for relative in decision_paths:
        path = tmp_path / relative
        path.unlink()
        subprocess.run(
            ["git", "-C", str(tmp_path), "checkout-index", "--force", "--", relative],
            check=True,
            capture_output=True,
        )
        head_bytes = subprocess.run(
            ["git", "-C", str(tmp_path), "show", f"HEAD:{relative}"],
            check=True,
            capture_output=True,
        ).stdout
        assert path.read_bytes() != head_bytes
    diff = subprocess.run(
        ["git", "-C", str(tmp_path), "diff", "--quiet", "HEAD", "--", *decision_paths],
        check=False,
        capture_output=True,
    )
    assert diff.returncode == 0

    assert _settle(service).state is RunState.CANCELLED


def test_settlement_rejects_real_decision_drift_under_crlf_attributes(
    tmp_path: Path,
) -> None:
    clock = Clock()
    service = _settlement_ready(
        tmp_path,
        clock,
        decision_attributes=".auto-pm/decisions/*.json text eol=crlf\n",
    )
    relative = ".auto-pm/decisions/DEC-20260911-5C37A985.json"
    decision_path = tmp_path / relative
    decision_path.unlink()
    subprocess.run(
        ["git", "-C", str(tmp_path), "checkout-index", "--force", "--", relative],
        check=True,
        capture_output=True,
    )
    drifted = decision_path.read_bytes().replace(
        b'"approver": "fubai"',
        b'"approver": "other"',
    )
    decision_path.write_bytes(drifted)
    diff = subprocess.run(
        ["git", "-C", str(tmp_path), "diff", "--quiet", "HEAD", "--", relative],
        check=False,
        capture_output=True,
    )
    assert diff.returncode == 1

    with pytest.raises(ContinuityExecutionError, match="脏改漂移"):
        _settle(service)

    assert service._store.get_run("RUN-TARGET").state is RunState.RUNNING


def test_settlement_uses_path_specific_custom_clean_filter(tmp_path: Path) -> None:
    filter_script = tmp_path / "decision_clean_filter.py"
    filter_script.write_text(
        "import sys\n"
        "raw = sys.stdin.buffer.read()\n"
        "if sys.argv[1] == 'clean':\n"
        "    raw = raw.replace(b'\\r\\n', b'\\n')\n"
        "else:\n"
        "    raw = raw.replace(b'\\n', b'\\r\\n')\n"
        "sys.stdout.buffer.write(raw)\n",
        encoding="utf-8",
        errors="replace",
    )
    filter_base = f'"{Path(sys.executable).as_posix()}" "{filter_script.as_posix()}"'
    clock = Clock()
    service = _settlement_ready(
        tmp_path,
        clock,
        decision_attributes=".auto-pm/decisions/*.json -text filter=decision\n",
        decision_filter_command=f"{filter_base} clean",
        decision_smudge_filter_command=f"{filter_base} smudge",
    )
    decision_paths = (
        ".auto-pm/decisions/DEC-20260910-A2TARGT1.json",
        ".auto-pm/decisions/DEC-20260911-5C37A985.json",
    )
    for relative in decision_paths:
        path = tmp_path / relative
        path.unlink()
        subprocess.run(
            ["git", "-C", str(tmp_path), "checkout-index", "--force", "--", relative],
            check=True,
            capture_output=True,
        )
    diff = subprocess.run(
        ["git", "-C", str(tmp_path), "diff", "--quiet", "HEAD", "--", *decision_paths],
        check=False,
        capture_output=True,
    )
    assert diff.returncode == 0

    assert _settle(service).state is RunState.CANCELLED


def test_settlement_rejects_invalid_path_aware_git_object_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Clock()
    service = _settlement_ready(tmp_path, clock)
    original = service._store._git_bytes

    def invalid_hash(*args: str, input_bytes: bytes | None = None) -> bytes:
        if args and args[0] == "hash-object":
            return b"not-a-git-object-id\n"
        return original(*args, input_bytes=input_bytes)

    monkeypatch.setattr(service._store, "_git_bytes", invalid_hash)

    with pytest.raises(ContinuityExecutionError, match="clean blob.*完整小写"):
        _settle(service)

    assert service._store.get_run("RUN-TARGET").state is RunState.RUNNING


def test_decision_clean_gate_distinguishes_git_failure_from_dirty_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ContinuityStore(tmp_path)

    def git_failure(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(command, 2, stdout=b"", stderr=b"fatal: injected")

    monkeypatch.setattr(
        "auto_pm.infrastructure.continuity_store.subprocess.run",
        git_failure,
    )

    with pytest.raises(ContinuityStoreError, match="clean 事实无法复核.*injected"):
        store._require_paths_clean_at_head(".auto-pm/decisions/DEC-TEST.json")


@pytest.mark.parametrize("fact", ["work_scope", "run_owned"])
def test_direct_store_independently_rechecks_recovery_scope_hierarchy(
    tmp_path: Path,
    fact: str,
) -> None:
    clock = Clock()
    service = _settlement_ready(tmp_path, clock)
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
        if fact == "work_scope":
            paths = (
                "auto_pm/core/a.py",
                ".auto-pm/continuity.db",
                "outside.py",
            )
            conn.execute(
                "UPDATE work_items SET scope_json=?, scope_hash=? WHERE work_id='WORK-RECOVERY'",
                (json.dumps(paths), ContinuityStore.authority_paths_hash(paths)),
            )
        else:
            conn.execute(
                "UPDATE run_items SET owned_paths_json=? WHERE run_id='RUN-RECOVERY'",
                (json.dumps(["auto_pm/core/a.py", ".auto-pm/continuity.db", "outside.py"]),),
            )
    _checkpoint_test_wal(tmp_path)
    values = _direct_settlement_values(service)

    with pytest.raises(ContinuityStoreError, match="scope 超出|owned_paths 超出"):
        service._store.settle_expired_run(**values)
    assert service._store.get_run("RUN-TARGET").state is RunState.RUNNING


def test_direct_store_uses_internal_clock_for_first_settlement(tmp_path: Path) -> None:
    clock = Clock()
    service = _settlement_ready(tmp_path, clock)
    values = _direct_settlement_values(service)
    clock.value -= timedelta(seconds=61)

    with pytest.raises(ContinuityStoreError, match="尚未过期"):
        service._store.settle_expired_run(**values)
    assert service._store.get_run("RUN-TARGET").state is RunState.RUNNING


def test_service_clock_cannot_forge_store_transaction_time(tmp_path: Path) -> None:
    store_clock = Clock()
    prepared = _settlement_ready(tmp_path, store_clock)
    service_clock = Clock()
    service_clock.value = store_clock.value
    store_clock.value -= timedelta(seconds=61)
    service = ContinuityExecutionService(
        tmp_path,
        store=prepared._store,
        now=service_clock,
    )

    with pytest.raises(ContinuityExecutionError, match="尚未过期"):
        _settle(service)

    assert service._store.get_run("RUN-TARGET").state is RunState.RUNNING
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='RUN_EXPIRED_SETTLED'"
        ).fetchone()[0]
    assert count == 0


def test_settlement_requires_canonical_db_in_decision_work_and_run(tmp_path: Path) -> None:
    cases = (
        ("decision", "Decision"),
        ("work", "Work scope"),
        ("run", "Run owned_paths"),
    )
    for name, message in cases:
        root = tmp_path / name
        root.mkdir()
        clock = Clock()
        if name == "work":
            service = _settlement_ready(
                root,
                clock,
                recovery_scope_paths=["auto_pm/core/a.py"],
                recovery_owned_paths=["auto_pm/core/a.py"],
            )
        elif name == "run":
            service = _settlement_ready(
                root,
                clock,
                recovery_owned_paths=["auto_pm/core/a.py"],
            )
        else:
            service = _settlement_ready(root, clock)
            decision_path = root / ".auto-pm" / "decisions" / "DEC-20260911-5C37A985.json"
            payload = json.loads(decision_path.read_text(encoding="utf-8"))
            payload["approved_files"] = ["auto_pm/core/a.py"]
            decision_path.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(ContinuityExecutionError, match=message):
            _settle(service)


@pytest.mark.skipif(os.name != "nt", reason="Windows authority casing contract")
def test_settlement_normalizes_windows_case_and_slashes(tmp_path: Path) -> None:
    clock = Clock()
    variant = ".AUTO-PM\\CONTINUITY.DB"
    service = _settlement_ready(
        tmp_path,
        clock,
        decision_paths=["auto_pm/core/a.py", variant],
        recovery_scope_paths=["auto_pm/core/a.py", variant],
        recovery_owned_paths=["auto_pm/core/a.py", variant],
    )

    assert _settle(service).state is RunState.CANCELLED


def test_settlement_rejects_noncanonical_dot_segments(tmp_path: Path) -> None:
    clock = Clock()
    variant = ".auto-pm/./continuity.db"
    with pytest.raises(ContinuityExecutionError, match="非法 path"):
        _settlement_ready(
            tmp_path,
            clock,
            decision_paths=["auto_pm/core/a.py", variant],
            recovery_scope_paths=["auto_pm/core/a.py", variant],
            recovery_owned_paths=["auto_pm/core/a.py", variant],
        )


@pytest.mark.parametrize(
    "false_target",
    [
        ".auto-pm/continuity.db.backup",
        ".auto-pm-shadow/continuity.db",
        "nested/.auto-pm/continuity.db",
    ],
)
def test_settlement_rejects_similar_prefix_and_non_root_database(
    tmp_path: Path, false_target: str
) -> None:
    clock = Clock()
    service = _settlement_ready(
        tmp_path,
        clock,
        decision_paths=["auto_pm/core/a.py", false_target],
        recovery_scope_paths=["auto_pm/core/a.py", false_target],
        recovery_owned_paths=["auto_pm/core/a.py", false_target],
    )

    with pytest.raises(ContinuityExecutionError, match="Decision"):
        _settle(service)


def test_settlement_rejects_parent_traversal_alias(tmp_path: Path) -> None:
    clock = Clock()
    service = _settlement_ready(tmp_path, clock)
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
        conn.execute(
            "UPDATE run_items SET owned_paths_json=? WHERE run_id='RUN-RECOVERY'",
            (json.dumps(["auto_pm/core/a.py", "nested/../.auto-pm/continuity.db"]),),
        )
    _checkpoint_test_wal(tmp_path)

    with pytest.raises(ContinuityExecutionError, match="非法 path"):
        _settle(service)


@pytest.mark.parametrize("fact", ["work_scope", "run_owned"])
def test_settlement_detects_transactional_recovery_authority_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fact: str
) -> None:
    clock = Clock()
    service = _settlement_ready(tmp_path, clock)
    original = service._store.settle_expired_run

    def drift_then_settle(**kwargs):
        with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
            if fact == "work_scope":
                paths = ("auto_pm/core/a.py",)
                conn.execute(
                    "UPDATE work_items SET scope_json=?, scope_hash=? WHERE work_id='WORK-RECOVERY'",
                    (
                        json.dumps(paths),
                        ContinuityStore.authority_paths_hash(paths),
                    ),
                )
            else:
                conn.execute(
                    "UPDATE run_items SET owned_paths_json=? WHERE run_id='RUN-RECOVERY'",
                    (json.dumps(["auto_pm/core/a.py"]),),
                )
        _checkpoint_test_wal(tmp_path)
        return original(**kwargs)

    monkeypatch.setattr(service._store, "settle_expired_run", drift_then_settle)

    with pytest.raises(ContinuityExecutionError, match="事实|冲突"):
        _settle(service)
    assert service._store.get_run("RUN-TARGET").state is RunState.RUNNING


@pytest.mark.parametrize(
    ("fact", "message"),
    [
        ("run_version", "恢复 Run 版本冲突"),
        ("work_version", "恢复 Work 版本冲突"),
        ("lease_version", "恢复 lease owner、token 或版本冲突"),
        ("lease_owner", "恢复 lease owner、token 或版本冲突"),
        ("lease_token", "恢复 lease owner、token 或版本冲突"),
    ],
)
def test_settlement_detects_each_recovery_cas_fact_drift_inside_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fact: str,
    message: str,
) -> None:
    clock = Clock()
    service = _settlement_ready(tmp_path, clock)
    original = service._store.settle_expired_run

    def drift_then_settle(**kwargs):
        with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
            if fact == "run_version":
                conn.execute("UPDATE run_items SET version=version+1 WHERE run_id='RUN-RECOVERY'")
            elif fact == "work_version":
                conn.execute(
                    "UPDATE work_items SET version=version+1 WHERE work_id='WORK-RECOVERY'"
                )
            elif fact == "lease_version":
                conn.execute(
                    "UPDATE execution_leases SET version=version+1 WHERE run_id='RUN-RECOVERY'"
                )
            elif fact == "lease_owner":
                conn.execute(
                    "UPDATE execution_leases SET owner_id='drift-agent' WHERE run_id='RUN-RECOVERY'"
                )
            else:
                conn.execute(
                    "UPDATE execution_leases SET lease_token='drift-secret' "
                    "WHERE run_id='RUN-RECOVERY'"
                )
        _checkpoint_test_wal(tmp_path)
        return original(**kwargs)

    monkeypatch.setattr(service._store, "settle_expired_run", drift_then_settle)

    with pytest.raises(ContinuityExecutionError, match=message):
        _settle(service)
    assert service._store.get_run("RUN-TARGET").state is RunState.RUNNING
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='RUN_EXPIRED_SETTLED'"
        ).fetchone()[0]
    assert count == 0


def test_settlement_requires_independent_recovery_work_and_decision(
    tmp_path: Path,
) -> None:
    for fact, message in (
        ("same_work", "独立 Work"),
        ("same_decision", "不得复用目标 Work"),
    ):
        root = tmp_path / fact
        root.mkdir()
        clock = Clock()
        service = _settlement_ready(root, clock)
        with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn, conn:
            if fact == "same_work":
                conn.execute(
                    "UPDATE run_items SET work_id='WORK-RECOVERY' WHERE run_id='RUN-TARGET'"
                )
            else:
                conn.execute(
                    "UPDATE work_items SET authorization_ref=? WHERE work_id='WORK-TARGET'",
                    ("DEC-20260911-5C37A985",),
                )
        _checkpoint_test_wal(root)

        with pytest.raises(ContinuityExecutionError, match=message):
            _settle(service)
        assert service._store.get_run("RUN-TARGET").state is RunState.RUNNING


@pytest.mark.parametrize(
    "authorization_ref",
    [
        "dec-20260910-a2targt1",
        "../decisions/DEC-20260910-A2TARGT1",
        "READ_ONLY",
    ],
)
def test_settlement_rejects_target_decision_alias_or_missing_authority(
    tmp_path: Path,
    authorization_ref: str,
) -> None:
    clock = Clock()
    service = _settlement_ready(tmp_path, clock)
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
        conn.execute(
            "UPDATE work_items SET authorization_ref=? WHERE work_id='WORK-TARGET'",
            (authorization_ref,),
        )
    _checkpoint_test_wal(tmp_path)

    with pytest.raises(ContinuityExecutionError, match="canonical immutable Decision"):
        _settle(service)
    assert service._store.get_run("RUN-TARGET").state is RunState.RUNNING


def test_settlement_requires_recovery_change_independent_from_target_change(
    tmp_path: Path,
) -> None:
    clock = Clock()
    service = _settlement_ready(
        tmp_path,
        clock,
        target_change_id="CHG-SCPT-2026-214",
    )

    with pytest.raises(ContinuityExecutionError, match="恢复 CHG 必须独立"):
        _settle(service)
    assert service._store.get_run("RUN-TARGET").state is RunState.RUNNING


@pytest.mark.parametrize(
    "fact",
    [
        "target_authorization_lowercase",
        "target_authorization_path",
        "recovery_authorization_lowercase",
        "project_pair",
        "target_work_lineage",
        "target_decision_bytes",
        "recovery_decision_bytes",
    ],
)
def test_settlement_rechecks_complete_authority_chain_inside_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fact: str,
) -> None:
    clock = Clock()
    service = _settlement_ready(tmp_path, clock)
    original = service._store.settle_expired_run

    def drift_then_settle(**kwargs):
        if fact.endswith("decision_bytes"):
            decision_id = (
                "DEC-20260910-A2TARGT1"
                if fact == "target_decision_bytes"
                else "DEC-20260911-5C37A985"
            )
            path = tmp_path / ".auto-pm" / "decisions" / f"{decision_id}.json"
            path.write_text(
                path.read_text(encoding="utf-8", errors="replace") + "\n",
                encoding="utf-8",
                errors="replace",
            )
        else:
            with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
                if fact == "target_authorization_lowercase":
                    conn.execute(
                        "UPDATE work_items SET authorization_ref=? WHERE work_id='WORK-TARGET'",
                        ("dec-20260910-a2targt1",),
                    )
                elif fact == "target_authorization_path":
                    conn.execute(
                        "UPDATE work_items SET authorization_ref=? WHERE work_id='WORK-TARGET'",
                        ("../decisions/DEC-20260910-A2TARGT1",),
                    )
                elif fact == "recovery_authorization_lowercase":
                    conn.execute(
                        "UPDATE work_items SET authorization_ref=? WHERE work_id='WORK-RECOVERY'",
                        ("dec-20260911-5c37a985",),
                    )
                elif fact == "project_pair":
                    conn.execute(
                        "UPDATE work_items SET subject_project_id='SW-OTHER' "
                        "WHERE work_id IN ('WORK-TARGET', 'WORK-RECOVERY')"
                    )
                else:
                    conn.execute(
                        "INSERT INTO work_items SELECT 'WORK-TARGET-ALIAS', "
                        "subject_project_id, kind, title, state, owner, read_only, "
                        "authorization_ref, scope_json, scope_hash, source_fingerprint, "
                        "version, created_at, updated_at FROM work_items "
                        "WHERE work_id='WORK-TARGET'"
                    )
                    conn.execute(
                        "UPDATE run_items SET work_id='WORK-TARGET-ALIAS' WHERE run_id='RUN-TARGET'"
                    )
            _checkpoint_test_wal(tmp_path)
        return original(**kwargs)

    monkeypatch.setattr(service._store, "settle_expired_run", drift_then_settle)

    with pytest.raises(
        ContinuityExecutionError,
        match="canonical|漂移|项目事实|lineage|snapshot",
    ):
        _settle(service)
    assert service._store.get_run("RUN-TARGET").state is RunState.RUNNING
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='RUN_EXPIRED_SETTLED'"
        ).fetchone()[0]
    assert count == 0


def test_settlement_detects_same_work_drift_inside_transaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Clock()
    service = _settlement_ready(tmp_path, clock)
    original = service._store.settle_expired_run

    def drift_then_settle(**kwargs):
        with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
            conn.execute("UPDATE run_items SET work_id='WORK-RECOVERY' WHERE run_id='RUN-TARGET'")
        _checkpoint_test_wal(tmp_path)
        return original(**kwargs)

    monkeypatch.setattr(service._store, "settle_expired_run", drift_then_settle)

    with pytest.raises(ContinuityExecutionError, match="独立 Work"):
        _settle(service)
    assert service._store.get_run("RUN-TARGET").state is RunState.RUNNING


def test_settlement_rechecks_recovery_lease_at_transaction_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Clock()
    service = _settlement_ready(tmp_path, clock)
    original = service._store.settle_expired_run

    def expire_then_settle(**kwargs):
        clock.value += timedelta(seconds=901)
        return original(**kwargs)

    monkeypatch.setattr(service._store, "settle_expired_run", expire_then_settle)

    with pytest.raises(ContinuityExecutionError, match="恢复 Run lease 已过期"):
        _settle(service)
    assert service._store.get_run("RUN-TARGET").state is RunState.RUNNING


def test_settlement_rejects_noncanonical_store_and_conditional_authority(
    tmp_path: Path,
) -> None:
    _git_root(tmp_path)
    shadow = ContinuityStore(tmp_path, db_path=tmp_path / ".auto-pm" / "shadow.db")
    with pytest.raises(ContinuityStoreError, match="canonical"):
        shadow.runtime_target_path()

    conditional_root = tmp_path / "conditional"
    conditional_root.mkdir()
    clock = Clock()
    service = _settlement_ready(
        conditional_root,
        clock,
        decision_conditions=["manual follow-up"],
    )
    with pytest.raises(ContinuityExecutionError, match="无条件"):
        _settle(service)


@pytest.mark.parametrize(
    "changes",
    [
        {"reason": "   "},
        {"idempotency_key": "   "},
        {"reason": "audit\u200bspoof"},
        {"idempotency_key": "settle\u202espoof"},
    ],
)
def test_settlement_rejects_blank_or_nonprintable_text_before_write_and_replay(
    tmp_path: Path,
    changes: dict[str, str],
) -> None:
    clock = Clock()
    service = _settlement_ready(tmp_path, clock)

    with pytest.raises(ContinuityExecutionError, match="不能为空|原因|idempotency_key"):
        _settle(service, **changes)
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM events WHERE event_type='RUN_EXPIRED_SETTLED'"
            ).fetchone()[0]
            == 0
        )

    _settle(service)
    with pytest.raises(ContinuityExecutionError, match="不能为空|原因|idempotency_key"):
        _settle(service, **changes)
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM events WHERE event_type='RUN_EXPIRED_SETTLED'"
            ).fetchone()[0]
            == 1
        )


def test_settlement_rejects_recovery_token_in_reason_without_event(tmp_path: Path) -> None:
    clock = Clock()
    service = _settlement_ready(tmp_path, clock)

    with pytest.raises(ContinuityExecutionError, match="不得包含.*token"):
        _settle(service, reason="Do not leak recovery-secret into the audit event.")
    with pytest.raises(ContinuityStoreError, match="不得包含.*token"):
        service._store.settle_expired_run(
            **_direct_settlement_values(
                service,
                reason="Do not leak recovery-secret into the audit event.",
            )
        )
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM events WHERE event_type='RUN_EXPIRED_SETTLED'"
            ).fetchone()[0]
            == 0
        )


def test_first_settlement_rejects_current_head_drift(tmp_path: Path) -> None:
    clock = Clock()
    service = _settlement_ready(tmp_path, clock)
    (tmp_path / "unrelated.txt").write_text("advanced\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "--", "unrelated.txt"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=Continuity Test",
            "-c",
            "user.email=continuity@example.invalid",
            "commit",
            "-m",
            "advance before settlement",
        ],
        check=True,
        capture_output=True,
    )

    with pytest.raises(ContinuityExecutionError, match="当前 Git HEAD"):
        _settle(service)
    assert service._store.get_run("RUN-TARGET").state is RunState.RUNNING


def test_settlement_exact_retry_survives_recovery_expiry_but_semantic_drift_fails(
    tmp_path: Path,
) -> None:
    clock = Clock()
    service = _settlement_ready(tmp_path, clock)
    first = _settle(service)
    recovery_checkpoint = service.checkpoint(
        checkpoint_id="CP-RECOVERY-POST-SETTLEMENT",
        run_id="RUN-RECOVERY",
        owner_id="recovery-agent",
        lease_token="recovery-secret",
        summary="Settlement committed",
        git_head=service._store.get_run("RUN-RECOVERY").git_head,
        dirty_paths=[],
        evidence=["settlement event committed"],
        idempotency_key="checkpoint-recovery-post-settlement",
    )
    recovery_handoff = service.create_handoff(
        handoff_id="HO-RECOVERY-POST-SETTLEMENT",
        checkpoint_id=recovery_checkpoint.checkpoint_id,
        from_owner="recovery-agent",
        to_owner="recovery-agent-b",
        lease_token="recovery-secret",
        idempotency_key="handoff-recovery-post-settlement",
    )
    rotated_lease = service.accept_handoff(
        handoff_id=recovery_handoff.handoff_id,
        receiver_id="recovery-agent-b",
        new_lease_token="recovery-rotated-secret",
        lease_seconds=900,
        idempotency_key="accept-recovery-post-settlement",
    )
    clock.value += timedelta(seconds=901)
    for decision_id in (
        "DEC-20260910-A2TARGT1",
        "DEC-20260911-5C37A985",
    ):
        (tmp_path / ".auto-pm" / "decisions" / f"{decision_id}.json").unlink()
    (tmp_path / "unrelated.txt").write_text("later history\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "--", "unrelated.txt"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=Continuity Test",
            "-c",
            "user.email=continuity@example.invalid",
            "commit",
            "-m",
            "unrelated successor",
        ],
        check=True,
        capture_output=True,
    )

    retried = _settle(service)

    assert retried == first
    assert service._store.get_lease("RUN-RECOVERY") == rotated_lease
    with pytest.raises(ContinuityExecutionError, match="owner|token|ownership"):
        _settle(service, recovery_lease_token="wrong-secret")
    with pytest.raises(ContinuityExecutionError, match="语义不一致"):
        _settle(service, reason="A different reason under the same key.")
    with pytest.raises(ContinuityExecutionError, match="无法读取|不存在|未找到|已处于终态"):
        _settle(service, idempotency_key="settle-target-run-other-key")
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
        payload = conn.execute(
            "SELECT payload_json FROM events WHERE event_type='RUN_EXPIRED_SETTLED'"
        ).fetchone()[0]
        count = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='RUN_EXPIRED_SETTLED'"
        ).fetchone()[0]
    assert "recovery-secret" not in payload
    assert "recovery-rotated-secret" not in payload
    assert count == 1


@pytest.mark.parametrize("fact", ["schema", "target_id", "run_version"])
def test_settlement_replay_rejects_event_identity_schema_and_version_drift(
    tmp_path: Path,
    fact: str,
) -> None:
    clock = Clock()
    service = _settlement_ready(tmp_path, clock)
    _settle(service)
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
        if fact == "run_version":
            conn.execute("UPDATE run_items SET version=version+1 WHERE run_id='RUN-TARGET'")
        else:
            row = conn.execute(
                "SELECT payload_json FROM events WHERE event_type='RUN_EXPIRED_SETTLED'"
            ).fetchone()
            assert row is not None
            payload = json.loads(row[0])
            if fact == "schema":
                payload["schema_version"] = "expired-run-settlement.v999"
            else:
                payload["target"]["run_id"] = "RUN-OTHER"
            conn.execute(
                "UPDATE events SET payload_json=? WHERE event_type='RUN_EXPIRED_SETTLED'",
                (json.dumps(payload),),
            )
    _checkpoint_test_wal(tmp_path)

    with pytest.raises(ContinuityExecutionError, match="hash|identity|身份或 schema|当前状态"):
        _settle(service)


def test_settlement_requires_expired_target_live_recovery_and_exact_capability(
    tmp_path: Path,
) -> None:
    clock = Clock()
    service = _settlement_ready(tmp_path, clock)
    clock.value -= timedelta(seconds=61)
    with pytest.raises(ContinuityExecutionError, match="尚未过期"):
        _settle(service)

    clock.value += timedelta(seconds=61)
    with pytest.raises(ContinuityExecutionError, match="ownership"):
        _settle(service, recovery_lease_token="wrong-secret")
    with pytest.raises(ContinuityExecutionError, match="只能前向结算为 CANCELLED"):
        _settle(service, outcome=RunState.FAILED)


def test_settlement_rejects_unlisted_target_and_normal_graph_stays_closed(tmp_path: Path) -> None:
    clock = Clock()
    service = _settlement_ready(tmp_path, clock, target_run_ids=("RUN-OTHER",))

    with pytest.raises(ContinuityExecutionError, match="未授权目标 Run"):
        _settle(service)
    with pytest.raises(ContinuityExecutionError, match="非法 Run 状态迁移"):
        service.transition_run(
            "RUN-RECOVERY",
            RunState.CANCELLED,
            "recovery-agent",
            "recovery-secret",
            "normal-cancel",
        )


def test_settlement_event_failure_rolls_back_run_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Clock()
    service = _settlement_ready(tmp_path, clock)
    original = ContinuityStore._append_event

    def fail_settlement_event(*args, **kwargs):
        event_type = args[2]
        if event_type == "RUN_EXPIRED_SETTLED":
            raise ContinuityStoreError("injected settlement event failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(ContinuityStore, "_append_event", staticmethod(fail_settlement_event))

    with pytest.raises(ContinuityExecutionError, match="injected"):
        _settle(service)
    target = service._store.get_run("RUN-TARGET")
    assert target.state is RunState.RUNNING
    assert target.version == 2


def test_settlement_detects_target_version_cas_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Clock()
    service = _settlement_ready(tmp_path, clock)
    original = service._store.settle_expired_run

    def drift_then_settle(**kwargs):
        with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
            conn.execute("UPDATE run_items SET version=version+1 WHERE run_id='RUN-TARGET'")
        return original(**kwargs)

    monkeypatch.setattr(service._store, "settle_expired_run", drift_then_settle)

    with pytest.raises(ContinuityExecutionError, match="版本冲突"):
        _settle(service)
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='RUN_EXPIRED_SETTLED'"
        ).fetchone()[0]
    assert count == 0


def test_concurrent_different_keys_allow_exactly_one_settlement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Clock()
    first_service = _settlement_ready(tmp_path, clock)
    second_service = ContinuityExecutionService(
        tmp_path,
        store=ContinuityStore(tmp_path, _clock=clock),
        now=clock,
    )
    barrier = threading.Barrier(2)
    original = ContinuityStore.settle_expired_run

    def synchronized_settle(store: ContinuityStore, **kwargs):
        barrier.wait(timeout=10)
        return original(store, **kwargs)

    monkeypatch.setattr(ContinuityStore, "settle_expired_run", synchronized_settle)

    def invoke(service: ContinuityExecutionService, key: str):
        return _settle(service, idempotency_key=key)

    successes = []
    failures = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(invoke, first_service, "settle-concurrent-a"),
            pool.submit(invoke, second_service, "settle-concurrent-b"),
        ]
        for future in futures:
            try:
                successes.append(future.result(timeout=15))
            except ContinuityExecutionError as error:
                failures.append(error)

    assert len(successes) == 1
    assert successes[0].state is RunState.CANCELLED
    assert len(failures) == 1
    assert first_service._store.get_run("RUN-TARGET").state is RunState.CANCELLED
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='RUN_EXPIRED_SETTLED'"
        ).fetchone()[0]
    assert count == 1


def test_store_reads_exactly_one_structured_run_started_evidence(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    _start(service)
    _start_evidence(service)

    owner_id, evidence = service._store.get_run_started_evidence("RUN-001")

    assert owner_id == "agent-a"
    assert evidence.process_id == 1234
    assert evidence.session_id == "thread-e03b-test"


def test_service_reconciles_operation_receipt_run_and_started_identity(tmp_path: Path) -> None:
    evidence = ExecutionStartEvidence(
        process_id=4321,
        session_id="session-e06",
        started_at=datetime(2026, 9, 19, 12, 0, tzinfo=UTC),
    )
    receipt = SimpleNamespace(
        run_id="RUN-001", work_id="WORK-001", executor_id="agent-a", owner_id="agent-a"
    )
    store = Mock()
    store.get_execution_intent.return_value = SimpleNamespace(receipt=receipt)
    store.get_run.return_value = SimpleNamespace(
        work_id="WORK-001", executor_id="agent-a", state=RunState.RUNNING
    )
    store.get_run_started_evidence.return_value = ("agent-a", evidence)
    service = ContinuityExecutionService(tmp_path, store=store)

    actual_receipt, run, actual_evidence = service.resolve_started_run("operation-e06-1")

    assert actual_receipt is receipt
    assert run is store.get_run.return_value
    assert actual_evidence is evidence
    store.get_run_started_evidence.assert_called_once_with("RUN-001")

    store.get_run_started_evidence.return_value = ("other-owner", evidence)
    with pytest.raises(ContinuityExecutionError, match="owner"):
        service.resolve_started_run("operation-e06-1")
