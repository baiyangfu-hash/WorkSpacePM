"""Contract invariants for bounded implementation cards."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from auto_pm.contracts.implementation_card import (
    Boundaries,
    CardState,
    EvidenceMap,
    GateDefinition,
    ImplementationCard,
    Outcomes,
    StopLines,
    UserStory,
)


def card_values() -> dict[str, object]:
    return {
        "card_id": "CARD-TEST-001", "project_id": "SW-2026-008",
        "wbs_item_id": "M2-GOV-IC01", "milestone_id": "M2",
        "source_refs": ("WBS:plans/WBS.md", "FILE:plans/spec.md"),
        "intent_type": "FEATURE", "state": "DRAFT",
        "user_stories": (UserStory(story="作为用户我希望查看结果以便确认交付",
                                    acceptance_criteria=("显示明确结果",)),),
        "acceptance_criteria": ("结果可核验",),
        "base_commit": "a" * 40, "worktree_path": "C:/candidate",
        "owned_paths": ("project/src.py",),
        "commit_evidence_paths": ("governance/evidence.md",),
        "non_goals": ("不发布",),
        "gates": (GateDefinition(name="test", cwd="project", argv=("python", "-m", "pytest"),
                                 coverage_targets=("project/src.py",)),),
        "stop_lines": StopLines(max_runs=2, max_healing_attempts=1,
                                deadline_utc="2026-09-29T00:00:00Z",
                                quota_stop_remaining_percent=30),
        "outcomes": Outcomes(normal="全部通过", small_problem="一次修复",
                             non_blocking="记录债务", blocking="停止并上报"),
        "evidence": EvidenceMap(decision_id="DEC-20260928-8D72B667", work_id="WORK-1",
                                run_id="RUN-1", checkpoint_id="CP-1", final_commit="b" * 40),
        "boundaries": Boundaries(merge="SEPARATE_APPROVAL", push="SEPARATE_APPROVAL",
                                 deploy="SEPARATE_APPROVAL", release="SEPARATE_APPROVAL"),
    }


def test_feature_and_ordered_transitions() -> None:
    card = ImplementationCard.model_validate(card_values())
    card.require_complete()
    with pytest.raises(ValueError, match="illegal"):
        card.transition(CardState.DISPATCHED)
    reviewed = card.transition(CardState.REVIEWED)
    approved = reviewed.model_copy(update={"approval_by": "fubai", "approval_evidence": "user:ticket-1"})
    assert approved.transition(CardState.APPROVED).state is CardState.APPROVED
    values = card_values()
    values["state"] = "APPROVED"
    with pytest.raises(ValidationError, match="history"):
        ImplementationCard.model_validate(values)


def test_non_feature_excludes_stories_and_requires_problem() -> None:
    values = card_values()
    values["intent_type"] = "BUG_FIX"
    with pytest.raises(ValidationError, match="excludes stories"):
        ImplementationCard.model_validate(values)
    values["user_stories"] = ()
    with pytest.raises(ValueError, match="problem statement"):
        ImplementationCard.model_validate(values).require_complete()
    values["problem_statement"] = "启动时抛出异常"
    ImplementationCard.model_validate(values).require_complete()


@pytest.mark.parametrize("bad", ["../escape", "/absolute", "project//file", "C:/drive/file"])
def test_owned_path_rejects_unsafe_forms(bad: str) -> None:
    values = card_values()
    values["owned_paths"] = (bad,)
    with pytest.raises(ValidationError):
        ImplementationCard.model_validate(values)


def test_commit_evidence_paths_are_required_disjoint_and_safe() -> None:
    values = card_values()
    values.pop("commit_evidence_paths")
    with pytest.raises(ValidationError):
        ImplementationCard.model_validate(values)
    values = card_values()
    values["commit_evidence_paths"] = ()
    with pytest.raises(ValidationError):
        ImplementationCard.model_validate(values)
    values["commit_evidence_paths"] = ("project/src.py",)
    with pytest.raises(ValidationError, match="overlap"):
        ImplementationCard.model_validate(values)
    values["commit_evidence_paths"] = ("../evidence.md",)
    with pytest.raises(ValidationError):
        ImplementationCard.model_validate(values)
    values["commit_evidence_paths"] = ("governance/evidence.md",) * 2
    with pytest.raises(ValidationError, match="unique"):
        ImplementationCard.model_validate(values)


def test_authorized_paths_is_ordered_union() -> None:
    card = ImplementationCard.model_validate(card_values())
    assert card.authorized_paths == ("project/src.py", "governance/evidence.md")


def test_gate_rejects_shell_and_unowned_target() -> None:
    with pytest.raises(ValidationError):
        GateDefinition(name="bad", cwd="project", argv=("sh", "-c", "true"),
                       coverage_targets=("project/src.py",))
    values = card_values()
    values["gates"] = (GateDefinition(name="bad", cwd="project", argv=("python", "-m", "pytest"),
                                      coverage_targets=("other/file.py",)),)
    with pytest.raises(ValueError, match="coverage"):
        ImplementationCard.model_validate(values).require_complete()


@pytest.mark.parametrize("field", ["wbs_item_id", "milestone_id", "source_refs"])
def test_wbs_fields_are_required(field: str) -> None:
    values = card_values()
    values.pop(field)
    with pytest.raises(ValidationError):
        ImplementationCard.model_validate(values)


@pytest.mark.parametrize("reference", ["URL:https://example.com", "WBS:../escape.md",
                                       "WBS:C:/outside.md", "WBS:plans//WBS.md",
                                       "WBS:plans/NUL.md", "WBS:plans/bad. /WBS.md",
                                       "WBS:.auto-pm/fake.md"])
def test_source_reference_rejects_unknown_or_unsafe_syntax(reference: str) -> None:
    values = card_values()
    values["source_refs"] = (reference,)
    with pytest.raises(ValidationError):
        ImplementationCard.model_validate(values)


def test_wbs_identifiers_reject_unsafe_values() -> None:
    values = card_values()
    values["wbs_item_id"] = "M2/../../other"
    with pytest.raises(ValidationError):
        ImplementationCard.model_validate(values)


def test_source_refs_reject_duplicate_underlying_path() -> None:
    values = card_values()
    values["source_refs"] = ("WBS:plans/WBS.md", "FILE:plans/WBS.md")
    with pytest.raises(ValidationError, match="alias"):
        ImplementationCard.model_validate(values)
