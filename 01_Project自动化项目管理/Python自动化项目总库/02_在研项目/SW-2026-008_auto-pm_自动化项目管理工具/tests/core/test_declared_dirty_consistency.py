"""One declared-dirty policy from plan to acceptance (DJ-2026-011 真 Trae 试跑缺陷).

MISSION-D053E7A789FF5928 was planned and its Run started with an empty
declaration, both Checkpoints recorded 11 changed files, verification opened
the acceptance gate and acceptance then refused it.  These tests pin the three
fixes: refuse empty declarations, judge verification and acceptance by one
comparison, and keep retired PM_SESSION_*.md files out of every plan.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from auto_pm.core import pm_facade_service as facade_module
from auto_pm.core.continuity_execution_service import ContinuityExecutionService
from auto_pm.core.pm_facade_service import PmFacadeError

from auto_pm.contracts.continuity import RunState
from auto_pm.contracts.declared_dirty import (
    DECLARED_DIRTY_MISMATCH,
    declared_dirty_mismatch,
    declared_dirty_problem,
    retired_session_paths,
)
from auto_pm.contracts.execution_adapter import ExecutionAdapterKind
from auto_pm.contracts.mission import MissionState
from auto_pm.contracts.pm_facade import PlanningExecutionGrant
from tests.core.test_pm_facade_service import (
    _EXAMPLE_GRANT,
    _commit_baseline,
    _gate_event_count,
    _p10_facade,
    _planning_intent,
    _setup,
)

# ── the shared policy ────────────────────────────────────────────────────────


def test_an_empty_declaration_names_the_missing_option() -> None:
    problem = declared_dirty_problem(())
    assert "改动声明为空" in problem and "--declared-dirty" in problem
    assert declared_dirty_problem(("a.py",), scope=("a.py",)) == ""


@pytest.mark.parametrize(
    "path",
    [
        "PM_SESSION_SW-2026-008.md",
        "0100_PLC/SysLib/FB_1011/PM_SESSION_FB1011.md",
        "x\\PM_SESSION_FB1013.md",
        "docs/pm_session_lower.MD",
    ],
)
def test_retired_pm_session_files_are_refused_in_scope_or_declaration(path: str) -> None:
    assert retired_session_paths((path,)) == (path,)
    assert "已退役" in declared_dirty_problem((path,))
    assert "已退役" in declared_dirty_problem(("ok.py",), scope=("ok.py", path))


@pytest.mark.parametrize(
    "path", ["PM_SESSION_GUIDE.txt", "docs/PM_SESSION.md", "docs/MY_PM_SESSION_X.md", "PM_SESSION_X.md/a.py"]
)
def test_lookalike_names_are_not_retired(path: str) -> None:
    assert retired_session_paths((path,)) == ()
    assert declared_dirty_problem((path,)) == ""


def test_mismatch_is_empty_only_for_the_identical_set_in_any_order() -> None:
    assert declared_dirty_mismatch(("b.py", "a.py"), ("a.py", "b.py")) == ""
    assert declared_dirty_mismatch((), ()) == ""


def test_mismatch_explains_the_dj011_shape() -> None:
    changed = tuple(f"DJ-2026-011/src/file_{index:02d}.st" for index in range(11))

    reason = declared_dirty_mismatch(changed, ())

    assert reason.startswith(DECLARED_DIRTY_MISMATCH)
    assert "Run 未声明任何改动" in reason and "未声明却改动 11 个" in reason
    assert reason.count("DJ-2026-011/src/") == 3 and "等" in reason


def test_mismatch_reports_missing_and_retired_paths() -> None:
    reason = declared_dirty_mismatch(("a.py", "PM_SESSION_X.md"), ("a.py", "b.py"))
    assert "未声明却改动 1 个: PM_SESSION_X.md" in reason
    assert "声明了却未改动 1 个: b.py" in reason
    assert "PM_SESSION" in reason.split("；")[-1]


# ── fix 1: plan / approve refuse an empty or retired declaration ─────────────


def _planning_rows(database: Path) -> dict[str, int]:
    with closing(sqlite3.connect(database)) as conn:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("planning_drafts", "planning_scope_cards", "events")
        }


@pytest.mark.parametrize(
    ("grant", "scope", "expected"),
    [
        (None, ("auto_pm/example.py",), "--declared-dirty"),
        (
            PlanningExecutionGrant(adapter=ExecutionAdapterKind.CODEX, approved_model="gpt-approved"),
            ("auto_pm/example.py",),
            "改动声明为空",
        ),
        (
            PlanningExecutionGrant(
                adapter=ExecutionAdapterKind.CODEX,
                approved_model="gpt-approved",
                declared_dirty_paths=("auto_pm/example.py",),
            ),
            ("auto_pm/example.py", "SW-TEST-001/PM_SESSION_SW-TEST-001.md"),
            "已退役",
        ),
    ],
    ids=["no-grant", "empty-declaration", "retired-in-scope"],
)
@pytest.mark.parametrize("entry", ["create", "submit", "preview"])
def test_plan_refuses_before_any_durable_write(
    tmp_path: Path,
    grant: PlanningExecutionGrant | None,
    scope: tuple[str, ...],
    expected: str,
    entry: str,
) -> None:
    facade, database, _changes = _p10_facade(tmp_path)
    if entry == "submit":
        facade.create_planning_draft(_planning_intent())
    before = _planning_rows(database)
    arguments: dict[str, Any] = {
        "scope_paths": scope,
        "risks": ("Drift",),
        "non_goals": ("No deployment",),
        "execution_grant": grant,
    }

    with pytest.raises(PmFacadeError, match=expected):
        if entry == "create":
            facade.create_planning_scope_card(_planning_intent(), **arguments)
        elif entry == "preview":
            facade.preview_planning_scope_card(_planning_intent(), **arguments)
        else:
            if grant is None:
                pytest.skip("submit already requires an explicit execution_grant")
            facade.submit_planning_scope_card(
                _planning_intent().request_id, submitted_by="unit", **arguments
            )

    assert _planning_rows(database) == before


def test_plan_with_an_exact_declaration_still_succeeds(tmp_path: Path) -> None:
    """Counter-example: the refusal is narrow; a declared plan is unaffected."""
    facade, _database, _changes = _p10_facade(tmp_path)

    card = facade.create_planning_scope_card(
        _planning_intent(),
        scope_paths=("auto_pm/example.py",),
        risks=("Drift",),
        non_goals=("No deployment",),
        execution_grant=_EXAMPLE_GRANT,
    )

    assert card.execution_grant.declared_dirty_paths == ("auto_pm/example.py",)


def test_approve_refuses_a_saved_card_whose_declaration_is_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A card saved before this rule (like MISSION-D053E7A789FF5928's) can no longer be approved."""
    facade, database, changes = _p10_facade(tmp_path)
    facade.create_planning_draft(_planning_intent())
    with monkeypatch.context() as legacy:
        legacy.setattr(facade_module, "declared_dirty_problem", lambda *_a, **_k: "")
        submitted = facade.submit_planning_scope_card(
            _planning_intent().request_id,
            scope_paths=("auto_pm/example.py",),
            risks=("Drift",),
            non_goals=("No deployment",),
            execution_grant=PlanningExecutionGrant(
                adapter=ExecutionAdapterKind.CODEX, approved_model="gpt-approved"
            ),
            submitted_by="legacy",
        )
    card = submitted.card
    assert card.execution_grant.declared_dirty_paths == ()
    status_before = changes.get_change_request(card.change_id, project_id="SW-TEST-001")
    assert status_before is not None
    before = _planning_rows(database)

    with pytest.raises(PmFacadeError, match="改动声明为空"):
        facade.approve_pending_planning_scope_card(
            card.request_id,
            expected_plan_hash=card.plan_hash,
            approver="fubai",
            approval_evidence_ref="user-confirmation:declared-dirty-legacy",
        )
    with pytest.raises(PmFacadeError, match="改动声明为空"):
        facade.approve_planning_scope_card(
            card,
            expected_plan_hash=card.plan_hash,
            approver="fubai",
            approval_evidence_ref="user-confirmation:declared-dirty-legacy",
        )

    assert _planning_rows(database) == before
    after = changes.get_change_request(card.change_id, project_id="SW-TEST-001")
    assert after is not None and after.status == status_before.status


# ── fix 2: verification uses the acceptance comparison ──────────────────────


def _verifying(
    root: Path, *, pending: bool = False
) -> tuple[Any, Any, ContinuityExecutionService]:
    """ACTIVE Mission whose only Run (owned pm.py, nothing declared) is VERIFYING."""
    missions, facade = _setup(root)
    (root / ".gitignore").write_text(".auto-pm/\n__pycache__/\n", encoding="utf-8")
    (root / "pm.py").write_text("VALUE = 1\n", encoding="utf-8")
    facade.plan("MISSION-PM-001")
    facade.approve("MISSION-PM-001", "WORK-PM-001")
    head = _commit_baseline(root)
    execution = ContinuityExecutionService(root, store=facade._store)
    execution.start_run(
        run_id="RUN-GATE-001",
        work_id="WORK-PM-001",
        executor_id="gate-test",
        adapter="test",
        owned_paths=["pm.py"],
        declared_dirty_paths=[],
        observed_dirty_paths=[],
        git_head=head,
        worktree_path=str(root),
        lease_token="gate-lease",
        lease_seconds=900,
        idempotency_key="gate-run-create",
    )
    for state, key in ((RunState.RUNNING, "running"), (RunState.VERIFYING, "verifying")):
        execution.transition_run("RUN-GATE-001", state, "gate-test", "gate-lease", f"gate-{key}")
    if pending:
        active = missions.get("MISSION-PM-001")
        missions.transition(
            mission_id=active.mission_id,
            expected_version=active.version,
            new_state=MissionState.ACCEPTANCE_PENDING,
            root_work_id=active.root_work_id,
            idempotency_key="gate-pending",
        )
    return missions, facade, execution


def _checkpoint_rows(root: Path) -> int:
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0])


def test_verify_refuses_changes_the_run_never_declared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The DJ-2026-011 shape: empty Run declaration, real changes on disk."""
    missions, facade, _ = _verifying(tmp_path)
    (tmp_path / "pm.py").write_text("VALUE = 2\n", encoding="utf-8")
    called: list[str] = []
    monkeypatch.setattr(
        ContinuityExecutionService,
        "append_verified_checkpoint",
        lambda _self, **_kwargs: called.append("append"),
    )
    before = (_gate_event_count(tmp_path), _checkpoint_rows(tmp_path))

    outcome = facade.verify_for_acceptance("MISSION-PM-001", lease_token="gate-lease")

    assert outcome.verified is False and outcome.checkpoint_id == ""
    assert DECLARED_DIRTY_MISMATCH in outcome.message and "pm.py" in outcome.message
    assert outcome.message.startswith("质量验证未通过")
    assert called == []
    assert (_gate_event_count(tmp_path), _checkpoint_rows(tmp_path)) == before
    assert missions.get("MISSION-PM-001").state is MissionState.ACTIVE


def test_verify_opens_the_gate_only_when_accept_would_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Any acceptance refusal after the Checkpoint keeps the Mission out of the gate."""
    missions, facade, _ = _verifying(tmp_path)
    assert missions.get("MISSION-PM-001").state is MissionState.ACTIVE
    monkeypatch.setattr(
        ContinuityExecutionService, "append_verified_checkpoint", lambda _self, **_kwargs: None
    )
    seen: list[str] = []

    def gate(_self: Any, mission: Any) -> None:
        seen.append(mission.mission_id)
        raise PmFacadeError(f"{DECLARED_DIRTY_MISMATCH}（unit）")

    monkeypatch.setattr(facade_module.PmFacadeService, "_require_current_acceptance_checkpoint", gate)

    outcome = facade.verify_for_acceptance("MISSION-PM-001", lease_token="gate-lease")

    assert seen == ["MISSION-PM-001"]
    assert outcome.verified is False and DECLARED_DIRTY_MISMATCH in outcome.message
    assert missions.get("MISSION-PM-001").state is MissionState.ACTIVE


def test_verify_with_a_matching_declaration_reaches_the_quality_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Counter-example: an unchanged tree matches the empty declaration and goes on to the gates."""
    _, facade, _ = _verifying(tmp_path)
    called: list[str] = []

    def append(_self: Any, **_kwargs: Any) -> None:
        called.append("append")
        raise facade_module.ContinuityExecutionError("simulated quality failure")

    monkeypatch.setattr(ContinuityExecutionService, "append_verified_checkpoint", append)

    outcome = facade.verify_for_acceptance("MISSION-PM-001", lease_token="gate-lease")

    assert called == ["append"]
    assert outcome.verified is False
    assert outcome.message == "质量验证未通过，已保留现场；未进入验收。"


def test_acceptance_reports_the_same_mismatch_text_as_the_shared_policy(
    tmp_path: Path,
) -> None:
    missions, facade, execution = _verifying(tmp_path, pending=True)
    run = facade._store.get_run("RUN-GATE-001")
    execution.checkpoint(
        checkpoint_id="CP-GATE-DECL",
        run_id="RUN-GATE-001",
        owner_id="gate-test",
        lease_token="gate-lease",
        summary="manual checkpoint with an undeclared file",
        git_head=run.git_head,
        dirty_paths=["pm.py"],
        evidence=["unit"],
        idempotency_key="gate-cp-decl",
    )

    reason = facade.acceptance_gate_reason("MISSION-PM-001")

    assert reason == declared_dirty_mismatch(("pm.py",), ())
    with pytest.raises(PmFacadeError) as refusal:
        facade.accept("MISSION-PM-001")
    assert str(refusal.value) == reason
    assert missions.get("MISSION-PM-001").state is MissionState.ACCEPTANCE_PENDING
