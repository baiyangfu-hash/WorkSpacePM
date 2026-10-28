"""TD-071 technical debt (audit 77, 6): the admission check and the card creation are no longer two separate looks.

The admission (soft limit, path collisions) is computed outside the write transaction.  Creating the card now re-reads
the project's open cards inside ``BEGIN IMMEDIATE`` and refuses when one was opened since the check, so two approvals
racing past the same stale check cannot both create cards.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_pm.application.core.mission_service import MissionService, MissionServiceError
from auto_pm.contracts.mission import MissionState
from auto_pm.infrastructure.continuity_store import ContinuityStore
from tests.core.test_mission_service import _authority, _service

PROJECT = "SW-2026-008"
SAME_FILE = ("auto_pm/infrastructure/continuity_store.py",)


def _create(service: MissionService, mission_id: str, *, admitted: tuple[str, ...] | None, limit: int = 8) -> None:
    service.create(
        mission_id=mission_id,
        subject_project_id=PROJECT,
        title=mission_id,
        objective="Race the admission check.",
        acceptance_criteria=["One card at a time passes a check."],
        authority=_authority(),
        created_by="Codex PM",
        idempotency_key=f"create-{mission_id}",
        max_open_per_project=limit,
        admitted_open_ids=admitted,
    )


def _open_ids(root: Path) -> list[str]:
    return sorted(item.mission_id for item in ContinuityStore(root).list_missions(PROJECT))


def test_two_cards_admitted_over_the_same_empty_project_cannot_both_be_created(tmp_path: Path) -> None:
    service = _service(tmp_path)
    limit_a, verdict_a = service.admit(mission_id="MISSION-A", subject_project_id=PROJECT, scope_paths=SAME_FILE)
    limit_b, verdict_b = service.admit(mission_id="MISSION-B", subject_project_id=PROJECT, scope_paths=SAME_FILE)
    assert verdict_a.open_ids == verdict_b.open_ids == () and not verdict_b.needs_user_release

    _create(service, "MISSION-A", admitted=verdict_a.open_ids, limit=limit_a)
    with pytest.raises(MissionServiceError, match="准入检查之后项目里又开了新卡（MISSION-A）"):
        _create(service, "MISSION-B", admitted=verdict_b.open_ids, limit=limit_b)
    assert _open_ids(tmp_path) == ["MISSION-A"]

    # The retry checks again against what is open now: the collision with A is seen and needs the user's word.
    with pytest.raises(MissionServiceError, match="要改同一批文件"):
        service.admit(mission_id="MISSION-B", subject_project_id=PROJECT, scope_paths=SAME_FILE)
    limit_b, verdict_b = service.admit(
        mission_id="MISSION-B",
        subject_project_id=PROJECT,
        scope_paths=SAME_FILE,
        admission_release_ref="user-confirmation:RACE-B-0001",
    )
    assert verdict_b.open_ids == ("MISSION-A",)
    _create(service, "MISSION-B", admitted=verdict_b.open_ids, limit=limit_b)
    assert _open_ids(tmp_path) == ["MISSION-A", "MISSION-B"]


def test_a_card_closed_since_the_check_does_not_refuse_the_new_one(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _create(service, "MISSION-A", admitted=None)
    _limit, verdict = service.admit(
        mission_id="MISSION-B",
        subject_project_id=PROJECT,
        scope_paths=SAME_FILE,
        admission_release_ref="user-confirmation:RACE-B-0002",
    )
    mission = service.get("MISSION-A")
    service.transition(
        mission_id="MISSION-A",
        expected_version=mission.version,
        new_state=MissionState.CANCELLED,
        root_work_id=None,
        idempotency_key="cancel-a",
    )

    _create(service, "MISSION-B", admitted=verdict.open_ids)
    assert _open_ids(tmp_path) == ["MISSION-B"]


def test_a_retry_of_a_created_card_is_not_refused_by_cards_opened_after_it(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _create(service, "MISSION-A", admitted=())
    _create(service, "MISSION-B", admitted=("MISSION-A",))
    # Replaying A with its original (now stale) admission returns the stored card: idempotency comes first.
    _create(service, "MISSION-A", admitted=())
    assert _open_ids(tmp_path) == ["MISSION-A", "MISSION-B"]


def test_callers_that_pass_no_admission_keep_the_old_count_only_rule(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _create(service, "MISSION-A", admitted=None)
    _create(service, "MISSION-B", admitted=None)
    with pytest.raises(MissionServiceError, match="上限 2 张"):
        _create(service, "MISSION-C", admitted=None, limit=2)
    assert _open_ids(tmp_path) == ["MISSION-A", "MISSION-B"]


def test_admission_reads_only_the_open_cards_and_still_knows_a_finished_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same-kind sweep of audit 78, 5: the admission no longer reads the project's finished history."""

    service = _service(tmp_path)
    _create(service, "MISSION-A", admitted=None)
    _create(service, "MISSION-OLD", admitted=None)
    old = service.get("MISSION-OLD")
    service.transition(
        mission_id="MISSION-OLD",
        expected_version=old.version,
        new_state=MissionState.CANCELLED,
        root_work_id=None,
        idempotency_key="cancel-old",
    )
    listed: list[bool] = []
    original = ContinuityStore.list_missions

    def spy(self: ContinuityStore, project: str, **kwargs: object) -> object:
        listed.append(bool(kwargs.get("include_terminal")))
        return original(self, project, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(ContinuityStore, "list_missions", spy)

    # A retry of the finished card is not a new card, even though it collides with A and brings no release.
    _limit, verdict = service.admit(mission_id="MISSION-OLD", subject_project_id=PROJECT, scope_paths=SAME_FILE)
    assert verdict.open_ids == ("MISSION-A",) and verdict.overlaps
    # A new card with the same paths is still stopped.
    with pytest.raises(MissionServiceError, match="要改同一批文件"):
        service.admit(mission_id="MISSION-NEW", subject_project_id=PROJECT, scope_paths=SAME_FILE)
    assert listed == [False, False]
