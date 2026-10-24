"""TD-071 technical debt (audit 75, low): one definition of "the user's own words" for every approval path.

The planning approval (DecisionService) and the park/unpark/switch/admission rules used to keep their own copies of
the evidence pattern and of the agent-name list.  Both now read ``contracts.user_evidence``; these tests pin that a
change there reaches both, and that the two paths now refuse the same things.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_pm.application.core.implementation_card_service import (
    ImplementationCardError,
    ImplementationCardService,
)
from auto_pm.contracts import mission as mission_contract
from auto_pm.contracts import user_evidence
from auto_pm.domain.change import decision_service
from auto_pm.domain.change.decision_service import DecisionService, DecisionValidationError
from tests.core.test_implementation_card_service import (
    complete_draft,
    governed_candidate,  # noqa: F401  (fixture)
)

PLAN_HASH = "a" * 64


def test_the_mission_rules_and_the_planning_approval_share_one_definition() -> None:
    assert mission_contract.user_evidence_problem is user_evidence.user_evidence_problem
    # No private copy is left behind in the planning approval.
    assert not hasattr(decision_service, "_USER_CONFIRMATION")
    assert not hasattr(decision_service, "_MODEL_APPROVER")


@pytest.mark.parametrize(
    "evidence",
    [
        "thread:20261108-0900",  # old format
        "user-confirmation:short",  # under 8 characters
        "user-confirmation:我同意",  # not an ASCII reference
        "user-confirmation:codex/auto-ok",
        "user-confirmation:agent-claude-self",
        "user-confirmation:2026-11-08:trae",
    ],
)
def test_both_paths_refuse_the_same_evidence(evidence: str) -> None:
    assert user_evidence.user_evidence_problem(evidence)
    with pytest.raises(DecisionValidationError):
        DecisionService.validate_planning_approval("fubai", PLAN_HASH, evidence)


@pytest.mark.parametrize(
    "evidence",
    ["user-confirmation:2026-11-08T09:00", "user-confirmation:cockpit-0123456789abcdef-89abcdef"],
)
def test_both_paths_accept_the_users_reference(evidence: str) -> None:
    assert user_evidence.user_evidence_problem(evidence) == ""
    DecisionService.validate_planning_approval("fubai", PLAN_HASH, evidence)


@pytest.mark.parametrize("approver", ["Trae", "cursor", "fubai/claude", "x:codex", "Codex agent"])
def test_an_agent_named_as_approver_is_refused_by_the_shared_list(approver: str) -> None:
    assert user_evidence.names_an_agent(approver)
    with pytest.raises(DecisionValidationError, match="自签"):
        DecisionService.validate_planning_approval(approver, PLAN_HASH, "user-confirmation:2026-11-08T09:00")


@pytest.mark.parametrize("approver", ["fubai", "baiyang", "Mai Lin", "chairman"])
def test_a_person_whose_name_contains_an_agent_word_is_not_refused(approver: str) -> None:
    assert not user_evidence.names_an_agent(approver)


@pytest.mark.parametrize("approver", ["claude", "Trae", "cursor-user"])
def test_an_implementation_card_refuses_the_shared_agent_names_too(
    governed_candidate: tuple[Path, Path, str], approver: str  # noqa: F811
) -> None:
    root, candidate, base = governed_candidate
    service = ImplementationCardService(root)
    service.create(complete_draft(candidate, base))
    with pytest.raises(ImplementationCardError, match="self-approve"):
        service.approve("CARD-TEST-002", approver=approver, approval_evidence="DEC-20260928-8D72B667")
