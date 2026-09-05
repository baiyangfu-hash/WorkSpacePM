from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest

from auto_pm.domain.project.archive_contracts import (
    ARCHIVE_COMPENSATION_ORDER,
    ARCHIVE_EXECUTION_STEPS,
    ARCHIVE_FAILURE_MATRIX,
    ARCHIVE_TEST_MATRIX,
    RESTORE_EXECUTION_STEPS,
    ArchiveAuthorization,
    ArchiveContractError,
    ArchiveErrorCode,
    ArchiveOperation,
    ArchivePreflightFacts,
    ArchiveRequest,
    ArchiveState,
    ArchiveStep,
    DuplicateRequestState,
    build_archive_plan,
    canonical_project_path,
    transition_archive_state,
)


def _request(operation: ArchiveOperation = ArchiveOperation.ARCHIVE) -> ArchiveRequest:
    return ArchiveRequest(
        request_id="REQ-001",
        project_id="SW-2026-099",
        change_id="CHG-SCPT-2026-099",
        decision_id="DEC-20260905-00000001",
        operation=operation,
        source_path="projects/active/SW-2026-099",
        destination_path="projects/archive/SW-2026-099",
        actor="fullstack-engineer",
        archive_code="ARC-20260905-001" if operation is ArchiveOperation.RESTORE else "",
    )


def _facts(request: ArchiveRequest | None = None) -> ArchivePreflightFacts:
    selected = request or _request()
    return ArchivePreflightFacts(
        authorization=ArchiveAuthorization(
            query_succeeded=True,
            decision_id=selected.decision_id,
            approved_operation=selected.operation,
            approved_project_id=selected.project_id,
            approved_paths=(selected.source_path, selected.destination_path),
        ),
        chg_query_succeeded=True,
        open_change_ids=(),
        git_available=True,
        git_returncode=0,
        git_clean=True,
        ledger_readable=True,
        ledger_valid=True,
        source_exists=True,
        destination_exists=False,
        source_link_anomaly=False,
        destination_link_anomaly=False,
        lock_acquired=True,
    )


def _assert_code(
    code: ArchiveErrorCode, request: ArchiveRequest, facts: ArchivePreflightFacts
) -> None:
    with pytest.raises(ArchiveContractError) as caught:
        build_archive_plan(request, facts)
    assert caught.value.code is code


def test_capability_enum_has_no_hard_delete() -> None:
    assert {member.value for member in ArchiveOperation} == {"archive", "restore"}
    with pytest.raises(ValueError):
        ArchiveOperation("delete")


@pytest.mark.parametrize("project_id", ["SW-2026-008", "SYS-2026-001"])
def test_protected_projects_are_always_rejected(project_id: str) -> None:
    request = replace(_request(), project_id=project_id)
    facts = replace(
        _facts(request),
        authorization=replace(_facts(request).authorization, approved_project_id=project_id),
    )
    _assert_code(ArchiveErrorCode.PROTECTED_PROJECT, request, facts)


@pytest.mark.parametrize(
    ("path", "code"),
    [
        ("../escape", ArchiveErrorCode.PATH_ESCAPE),
        ("/absolute/project", ArchiveErrorCode.PATH_ESCAPE),
        ("projects\\escape", ArchiveErrorCode.PATH_ESCAPE),
        ("projects/*", ArchiveErrorCode.PATH_ESCAPE),
        ("projects/./name", ArchiveErrorCode.PATH_ESCAPE),
        ("", ArchiveErrorCode.PATH_ESCAPE),
    ],
)
def test_noncanonical_paths_fail_closed(path: str, code: ArchiveErrorCode) -> None:
    with pytest.raises(ArchiveContractError) as caught:
        canonical_project_path(path)
    assert caught.value.code is code


def test_happy_path_has_locked_order_and_reverse_compensation() -> None:
    plan = build_archive_plan(_request(), _facts())
    assert plan.initial_state is ArchiveState.VALIDATED
    assert plan.steps == ARCHIVE_EXECUTION_STEPS
    assert plan.steps[:3] == (
        ArchiveStep.ACQUIRE_LOCK,
        ArchiveStep.ALLOCATE_ARCHIVE_CODE,
        ArchiveStep.MOVE_DIRECTORY,
    )
    assert plan.compensation_order == ARCHIVE_COMPENSATION_ORDER
    assert plan.compensation_order == tuple(reversed(plan.steps[2:]))
    assert plan.idempotent_replay is False


def test_restore_requires_exact_archive_code() -> None:
    request = replace(_request(ArchiveOperation.RESTORE), archive_code="ARC-bad")
    _assert_code(ArchiveErrorCode.ARCHIVE_CODE_INVALID, request, _facts(request))


def test_restore_uses_same_transactional_effect_order() -> None:
    request = _request(ArchiveOperation.RESTORE)
    plan = build_archive_plan(request, _facts(request))
    assert plan.steps == RESTORE_EXECUTION_STEPS
    assert ArchiveStep.ALLOCATE_ARCHIVE_CODE not in plan.steps
    assert plan.request.archive_code == "ARC-20260905-001"


@pytest.mark.parametrize(
    ("update", "code"),
    [
        (
            lambda facts: replace(facts, chg_query_succeeded=False),
            ArchiveErrorCode.CHG_QUERY_FAILED,
        ),
        (lambda facts: replace(facts, git_available=False), ArchiveErrorCode.GIT_UNAVAILABLE),
        (lambda facts: replace(facts, git_returncode=128), ArchiveErrorCode.GIT_NON_ZERO),
        (lambda facts: replace(facts, git_clean=False), ArchiveErrorCode.GIT_DIRTY),
        (lambda facts: replace(facts, ledger_readable=False), ArchiveErrorCode.LEDGER_DAMAGED),
        (lambda facts: replace(facts, ledger_valid=False), ArchiveErrorCode.LEDGER_DAMAGED),
        (lambda facts: replace(facts, source_link_anomaly=True), ArchiveErrorCode.LINK_ANOMALY),
        (
            lambda facts: replace(facts, destination_link_anomaly=True),
            ArchiveErrorCode.LINK_ANOMALY,
        ),
        (lambda facts: replace(facts, source_exists=False), ArchiveErrorCode.SOURCE_MISSING),
        (
            lambda facts: replace(facts, destination_exists=True),
            ArchiveErrorCode.DESTINATION_CONFLICT,
        ),
        (lambda facts: replace(facts, lock_acquired=False), ArchiveErrorCode.CONCURRENCY_CONFLICT),
    ],
)
def test_preflight_failures_never_produce_a_plan(
    update: Callable[[ArchivePreflightFacts], ArchivePreflightFacts],
    code: ArchiveErrorCode,
) -> None:
    facts = update(_facts())
    _assert_code(code, _request(), facts)


def test_chg_open_items_fail_closed() -> None:
    facts = replace(_facts(), open_change_ids=("CHG-OPEN-001",))
    _assert_code(ArchiveErrorCode.OPEN_CHANGE, _request(), facts)


def test_authorization_query_failure_is_not_treated_as_no_restriction() -> None:
    facts = replace(_facts(), authorization=replace(_facts().authorization, query_succeeded=False))
    _assert_code(ArchiveErrorCode.AUTHORIZATION_QUERY_FAILED, _request(), facts)


@pytest.mark.parametrize("mismatch", ["decision", "operation", "project", "paths"])
def test_decision_whitelist_is_exact_and_immutable(mismatch: str) -> None:
    request = _request()
    authorization = _facts().authorization
    if mismatch == "decision":
        authorization = replace(authorization, decision_id="DEC-WRONG")
    elif mismatch == "operation":
        authorization = replace(authorization, approved_operation=ArchiveOperation.RESTORE)
    elif mismatch == "project":
        authorization = replace(authorization, approved_project_id="SW-OTHER")
    else:
        authorization = replace(authorization, approved_paths=(request.source_path,))
    _assert_code(
        ArchiveErrorCode.NOT_AUTHORIZED,
        request,
        replace(_facts(), authorization=authorization),
    )


def test_duplicate_completed_request_is_a_zero_effect_replay() -> None:
    facts = replace(
        _facts(),
        duplicate_request=DuplicateRequestState.SAME_COMPLETED,
        source_exists=False,
        destination_exists=True,
    )
    plan = build_archive_plan(_request(), facts)
    assert plan.idempotent_replay is True
    assert plan.initial_state is ArchiveState.COMPLETED
    assert plan.steps == ()
    assert plan.compensation_order == ()


def test_duplicate_conflicting_request_fails_closed() -> None:
    facts = replace(_facts(), duplicate_request=DuplicateRequestState.CONFLICT)
    _assert_code(ArchiveErrorCode.DUPLICATE_REQUEST, _request(), facts)


def test_state_machine_allows_normal_execution_and_compensation() -> None:
    normal = (
        ArchiveState.REQUESTED,
        ArchiveState.AUTHORIZED,
        ArchiveState.VALIDATED,
        ArchiveState.LOCKED,
        ArchiveState.MOVED,
        ArchiveState.PM_SESSION_UPDATED,
        ArchiveState.LEDGER_UPDATED,
        ArchiveState.DATABASE_UPDATED,
        ArchiveState.SCANNER_REFRESHED,
        ArchiveState.COMPLETED,
    )
    current = normal[0]
    for target in normal[1:]:
        current = transition_archive_state(current, target)
    assert current is ArchiveState.COMPLETED
    assert (
        transition_archive_state(ArchiveState.MOVED, ArchiveState.COMPENSATING)
        is ArchiveState.COMPENSATING
    )
    assert (
        transition_archive_state(ArchiveState.COMPENSATING, ArchiveState.ROLLED_BACK)
        is ArchiveState.ROLLED_BACK
    )


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ArchiveState.REQUESTED, ArchiveState.MOVED),
        (ArchiveState.COMPLETED, ArchiveState.REQUESTED),
        (ArchiveState.ROLLED_BACK, ArchiveState.COMPLETED),
        (ArchiveState.FAILED, ArchiveState.AUTHORIZED),
    ],
)
def test_state_machine_rejects_shortcuts_and_terminal_resurrection(
    current: ArchiveState, target: ArchiveState
) -> None:
    with pytest.raises(ArchiveContractError) as caught:
        transition_archive_state(current, target)
    assert caught.value.code is ArchiveErrorCode.INVALID_STATE_TRANSITION


def test_failure_and_test_matrices_cover_required_safety_boundaries() -> None:
    failure_codes = {case.code for case in ARCHIVE_FAILURE_MATRIX}
    assert {
        ArchiveErrorCode.AUTHORIZATION_QUERY_FAILED,
        ArchiveErrorCode.CHG_QUERY_FAILED,
        ArchiveErrorCode.GIT_UNAVAILABLE,
        ArchiveErrorCode.GIT_NON_ZERO,
        ArchiveErrorCode.LEDGER_DAMAGED,
        ArchiveErrorCode.PATH_ESCAPE,
        ArchiveErrorCode.LINK_ANOMALY,
        ArchiveErrorCode.CONCURRENCY_CONFLICT,
        ArchiveErrorCode.COMPENSATION_FAILED,
    }.issubset(failure_codes)
    assert all(not case.side_effects_allowed for case in ARCHIVE_FAILURE_MATRIX[:8])
    assert len({case.case_id for case in ARCHIVE_TEST_MATRIX}) == len(ARCHIVE_TEST_MATRIX)
    assert len(ARCHIVE_TEST_MATRIX) >= 12
