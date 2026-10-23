"""Real-process proofs that a PLC Run reaches (or is kept from) the acceptance gate."""

from __future__ import annotations

import json
import secrets
import sqlite3
import sys
import textwrap
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from auto_pm.change.change_service import ChangeService
from auto_pm.core.local_execution_orchestrator import LocalExecutionOrchestrator
from auto_pm.core.work_registry_service import WorkRegistryService

from auto_pm.application.core.continuity_execution_service import (
    ContinuityExecutionError,
    ContinuityExecutionService,
)
from auto_pm.contracts.continuity import RunState, WorkKind
from auto_pm.contracts.execution_adapter import ExecutionAdapterKind
from auto_pm.contracts.mission import MissionState
from auto_pm.contracts.pm_facade import PlanningExecutionGrant, PmIntent
from auto_pm.infrastructure.continuity_store import ContinuityStore
from auto_pm.infrastructure.local_executor import LocalCodexExecutor
from tests.core.test_continuity_execution_service import Clock, _start
from tests.core.test_plc_quality_gate import (
    BAD_SCL,
    GOOD_SCL,
    INT_DOC,
    PROJECT,
    SCL,
    git,
    plc_workspace,
    write_plc_project,
)
from tests.core.test_pm_run_e2e import NOT_VERIFIED_SENTENCE, VERIFIED_SENTENCE, _Env
from tests.plan_checklist_support import full_checklist

if TYPE_CHECKING:
    from auto_pm.application.core.pm_facade_service import PmFacadeError, PmFacadeService
else:
    from auto_pm.core.pm_facade_service import PmFacadeError, PmFacadeService

PLC_PROJECT_ID = "DJ-TEST-001"
EDITED_SCL = GOOD_SCL + "// V01 edit\n"
EDITED_INT = "# 接口文档\nI-001 added by the run\n"


def _plc_continuity_service(
    tmp_path: Path, *, scl_text: str | None = None, owned: tuple[str, ...] = (SCL,),
) -> tuple[Path, ContinuityExecutionService]:
    workspace, candidate, baseline = plc_workspace(tmp_path, extra=("tools/helper.py",))
    clock = Clock()
    work = WorkRegistryService(workspace, now=lambda: clock().isoformat())
    work.initialize("test")
    work.create_work(
        work_id="WORK-001",
        subject_project_id="SW-2026-008",
        kind=WorkKind.GOVERNANCE,
        title="V01 PLC automatic checkpoint",
        owner="architect",
        scope_paths=list(owned),
        source_fingerprint="sha256:v01",
        idempotency_key="create-v01-work",
        read_only=True,
    )
    service = ContinuityExecutionService(
        workspace, store=ContinuityStore(workspace, _clock=clock), now=clock
    )
    _start(
        service,
        owned_paths=list(owned),
        worktree_path=str(candidate),
        git_head=baseline,
        declared_dirty_paths=[],
        observed_dirty_paths=[],
    )
    if scl_text is not None:
        (candidate / SCL).write_text(scl_text, encoding="utf-8")
    return candidate, service


def _append_plc(service: ContinuityExecutionService, root: Path, **changes: Any) -> Any:
    values: dict[str, Any] = {
        "checkpoint_id": "CP-PLC-001",
        "run_id": "RUN-001",
        "owner_id": "agent-a",
        "lease_token": "lease-secret",
        "project_root": root,
        "profile": "plc",
    }
    values.update(changes)
    return service.append_verified_checkpoint(**values)


def test_h01_plc_profile_appends_a_v3_checkpoint_and_replays_it_idempotently(
    tmp_path: Path,
) -> None:
    candidate, service = _plc_continuity_service(tmp_path, scl_text=EDITED_SCL)

    checkpoint = _append_plc(service, candidate)

    envelope = json.loads(checkpoint.evidence[0])
    assert envelope["schema_version"] == "checkpoint-evidence.v3"
    assert envelope["quality_receipt"]["status"] == "PASS"
    assert [gate["name"] for gate in envelope["quality_receipt"]["gates"]] == [
        "plc-check",
        "scl-lint",
    ]
    assert checkpoint.dirty_paths == (SCL,)
    assert _append_plc(service, candidate) == checkpoint
    assert checkpoint.sequence == 1
    assert service._store.latest_checkpoint("RUN-001") == checkpoint


def test_h02_a_changed_owned_scl_makes_the_stored_checkpoint_unreplayable(
    tmp_path: Path,
) -> None:
    candidate, service = _plc_continuity_service(tmp_path, scl_text=EDITED_SCL)
    _append_plc(service, candidate)

    (candidate / SCL).write_text(EDITED_SCL + "// later\n", encoding="utf-8")

    with pytest.raises(ContinuityExecutionError, match="identity.*不一致"):
        _append_plc(service, candidate)


def test_h03_a_violating_scl_cannot_produce_a_checkpoint(tmp_path: Path) -> None:
    candidate, service = _plc_continuity_service(tmp_path, scl_text=BAD_SCL)

    with pytest.raises(ContinuityExecutionError, match="PLC 质量收据为 PASS"):
        _append_plc(service, candidate)

    assert service._store.latest_checkpoint("RUN-001") is None


def test_h04_profile_and_domain_mismatches_are_refused_without_a_checkpoint(
    tmp_path: Path,
) -> None:
    candidate, service = _plc_continuity_service(tmp_path, scl_text=EDITED_SCL)

    with pytest.raises(ContinuityExecutionError, match="未知自动 Checkpoint profile"):
        _append_plc(service, candidate, profile="plc2")
    with pytest.raises(ContinuityExecutionError, match="generic profile 无法验证"):
        _append_plc(service, candidate, profile="generic")
    assert service._store.latest_checkpoint("RUN-001") is None


def test_h05_the_plc_profile_refuses_a_run_that_owns_python_outside_a_plc_project(
    tmp_path: Path,
) -> None:
    candidate, service = _plc_continuity_service(
        tmp_path, scl_text=EDITED_SCL, owned=(SCL, "tools/helper.py")
    )

    with pytest.raises(ContinuityExecutionError, match="一个 Run 只验证一个领域"):
        _append_plc(service, candidate)

    assert service._store.latest_checkpoint("RUN-001") is None


# -- Facade end to end ------------------------------------------------------------


def _build_plc_workspace(root: Path) -> None:
    root.mkdir()
    git(root, "init")
    git(root, "config", "user.name", "V01 Test")
    git(root, "config", "user.email", "v01@example.invalid")
    project = write_plc_project(root, PROJECT)
    changes = project / "04_监控" / "01_变更管理"
    (changes / "01_变更单").mkdir(parents=True)
    (changes / "01_版本变更台帐.md").write_text(
        "# 台帐\n\n| 序号 | 变更编号 | 描述 |\n|---|---|---|\n", encoding="utf-8"
    )
    (project / ".copier-answers.yml").write_text(
        f"project_id: {PLC_PROJECT_ID}\nproject_name: V01 E2E\nstack: plc\n", encoding="utf-8"
    )
    (root / "specs").mkdir()
    (root / "specs" / "plc.md").write_text("plc", encoding="utf-8")
    (root / "specs" / "python.md").write_text("python", encoding="utf-8")
    registry = root / "00_Obsidian_Base全局规范文件仓库" / "spec_registry.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        json.dumps(
            {
                "specs": {
                    "DEV-TEST": {
                        "domain": "python",
                        "lifecycle": "stable",
                        "canonical_path": "specs/python.md",
                        "version": "V1",
                    },
                    "LSP-TEST": {
                        "domain": "plc",
                        "lifecycle": "active",
                        "canonical_path": "specs/plc.md",
                        "version": "V1",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    workspace = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    workspace.parent.mkdir(parents=True)
    workspace.write_text(
        json.dumps(
            {
                "schema_version": "workspace-registry.v1",
                "projects": [
                    {
                        "project_id": PLC_PROJECT_ID,
                        "project_root": PROJECT,
                        "development_root": PROJECT,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / "tools").mkdir()
    (root / "tools" / "helper.py").write_text("def value() -> int:\n    return 1\n", encoding="utf-8")
    (root / ".gitignore").write_text(".auto-pm/\n__pycache__/\n*.cache\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "baseline")


def _helper_source(files: dict[str, str], counter: Path) -> str:
    """A real child process that speaks the handshake, writes real files and exits."""

    return textwrap.dedent(
        f"""\
        import json, pathlib, sys, time
        repo = pathlib.Path(sys.argv[sys.argv.index('-C') + 1])
        with open({str(counter)!r}, 'a', encoding='utf-8') as handle:
            handle.write('start\\n')
        print(json.dumps({{'type': 'thread.started', 'thread_id': 'thread-v01'}}), flush=True)
        for relative, text in {files!r}.items():
            (repo / relative).write_text(text, encoding='utf-8')
        time.sleep(0.15)
        sys.exit(0)
        """
    )


def _plc_env(
    tmp_path: Path,
    *,
    files: dict[str, str] | None = None,
    scope: tuple[str, ...] = (SCL, INT_DOC),
    name: str = "ws",
) -> _Env:
    root = (tmp_path / name).resolve()
    _build_plc_workspace(root)
    counter = tmp_path / f"{name}-starts.txt"
    helper = tmp_path / f"{name}-fake_codex.py"
    helper.write_text(
        _helper_source(files or {SCL: EDITED_SCL, INT_DOC: EDITED_INT}, counter),
        encoding="utf-8",
    )
    store = ContinuityStore(root)
    store.initialize(datetime.now(UTC).isoformat(), "v01-e2e")
    changes = ChangeService(str(root))
    executor = LocalCodexExecutor(command_prefix=(sys.executable, str(helper)))
    facade = PmFacadeService(
        root,
        store=store,
        change_service=changes,
        local_orchestrator=LocalExecutionOrchestrator(root, store=store, executor=executor),
    )
    grant = PlanningExecutionGrant(
        adapter=ExecutionAdapterKind.CODEX, approved_model="agent-a", declared_dirty_paths=scope,
        plan_checklist=full_checklist(),
    )
    card = facade.create_planning_scope_card(
        PmIntent(
            request_id="REQ-V01-E2E",
            subject_project_id=PLC_PROJECT_ID,
            objective="Add interface I-001",
            acceptance_criteria=("SCL passes LSP-905",),
        ),
        scope_paths=scope,
        risks=("改错文件导致回归",),
        non_goals=("no hardware download",),
        execution_grant=grant,
    )
    for state in ("submitted", "under_review", "approved"):
        changes.transition_status(
            card.change_id, state, approver="fubai", comment="human", project_id=PLC_PROJECT_ID
        )
    facade.approve_planning_scope_card(
        card,
        expected_plan_hash=card.plan_hash,
        approver="fubai",
        approval_evidence_ref="user-confirmation:V01-PLC-E2E",
    )
    return _Env(root, store, facade, changes, card, counter, secrets.token_urlsafe(32))


def test_e01_a_compliant_plc_run_is_verified_and_opens_the_acceptance_gate(
    tmp_path: Path,
) -> None:
    env = _plc_env(tmp_path)

    outcome = env.run()

    assert outcome.verified is True
    assert outcome.message == VERIFIED_SENTENCE
    assert outcome.mission_state is MissionState.ACCEPTANCE_PENDING
    checkpoint = env.store.get_checkpoint(outcome.checkpoint_id)
    assert json.loads(checkpoint.evidence[0])["schema_version"] == "checkpoint-evidence.v3"
    assert env.facade.acceptance_gate_reason(outcome.mission_id) == ""
    accepted = env.facade.accept(outcome.mission_id)
    assert accepted.mission_state is MissionState.ACCEPTED
    worktree = Path(env.store.get_run(outcome.run_id).worktree_path)
    assert (worktree / SCL).read_text(encoding="utf-8") == EDITED_SCL
    assert git(env.root, "diff", "--name-only") == ""
    assert (env.root / SCL).read_text(encoding="utf-8") == GOOD_SCL


def test_e02_a_violating_scl_keeps_the_scene_and_never_opens_the_gate(tmp_path: Path) -> None:
    env = _plc_env(tmp_path, files={SCL: BAD_SCL, INT_DOC: EDITED_INT})

    outcome = env.run()

    assert outcome.verified is False
    assert outcome.message == NOT_VERIFIED_SENTENCE
    assert env.mission_state() is MissionState.ACTIVE
    assert env.latest_run()[1] is RunState.VERIFYING
    assert env.checkpoint_count() == 0
    assert env.facade.acceptance_gate_reason(outcome.mission_id) != ""
    with pytest.raises(PmFacadeError):
        env.facade.accept(outcome.mission_id)


@pytest.mark.parametrize("late_change", ["owned_scl", "ignored_input"])
def test_e03_a_change_after_verification_closes_the_acceptance_gate(
    tmp_path: Path, late_change: str
) -> None:
    env = _plc_env(tmp_path)
    outcome = env.run()
    assert env.facade.acceptance_gate_reason(outcome.mission_id) == ""
    worktree = Path(env.store.get_run(outcome.run_id).worktree_path)

    if late_change == "owned_scl":
        (worktree / SCL).write_text(EDITED_SCL + "// sneaked in\n", encoding="utf-8")
    else:
        (worktree / PROJECT / "OB1" / "scan.cache").write_text("sneaked in", encoding="utf-8")

    assert env.facade.acceptance_gate_reason(outcome.mission_id) != ""
    with pytest.raises(PmFacadeError):
        env.facade.accept(outcome.mission_id)


def test_e04_a_run_owning_both_plc_and_python_is_not_verified(tmp_path: Path) -> None:
    env = _plc_env(
        tmp_path,
        files={SCL: EDITED_SCL, INT_DOC: EDITED_INT, "tools/helper.py": "VALUE = 2\n"},
        scope=(SCL, INT_DOC, "tools/helper.py"),
    )

    outcome = env.run()

    assert outcome.verified is False
    assert outcome.message == NOT_VERIFIED_SENTENCE
    assert env.checkpoint_count() == 0
    assert env.mission_state() is MissionState.ACTIVE


def test_e05_replay_of_a_verified_plc_run_adds_no_second_process_or_evidence(
    tmp_path: Path,
) -> None:
    env = _plc_env(tmp_path)
    first = env.run()
    events, checkpoints, starts = env.event_count(), env.checkpoint_count(), env.starts()

    second = env.run()

    assert second == first
    assert (env.event_count(), env.checkpoint_count(), env.starts()) == (events, checkpoints, starts)
    with closing(sqlite3.connect(env.root / ".auto-pm" / "continuity.db")) as conn:
        assert conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0] == 1
