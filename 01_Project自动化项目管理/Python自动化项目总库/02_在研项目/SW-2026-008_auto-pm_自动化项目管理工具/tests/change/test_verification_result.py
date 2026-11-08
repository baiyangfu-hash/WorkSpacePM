"""D-48: ``completed`` is decided by the structured ``verification_result``, not by Chinese keywords in the conclusion text."""

from __future__ import annotations

import pytest

from auto_pm.domain.change.change_service import ChangeService
from auto_pm.domain.change.constants import TransitionGuardError
from tests.change.test_acceptance_flow import (
    acceptance_workspace,  # noqa: F401 - the shared fixture
)

CHG = "CHG-DOCU-2026-001"


def _accepting(workspace: str) -> ChangeService:
    svc = ChangeService(workspace)
    svc.transition_status(CHG, "pending_acceptance", approver="张三")
    svc.transition_status(CHG, "accepting", approver="李四")
    return svc


def test_pass_completes_even_when_the_text_has_no_keyword(acceptance_workspace: str) -> None:  # noqa: F811
    svc = _accepting(acceptance_workspace)

    cr = svc.transition_status(CHG, "completed", approver="李四", verification_conclusion="OK", verification_result="pass")

    assert cr is not None and cr.status == "completed"  # the old keyword rule would have refused "OK"


@pytest.mark.parametrize("text", ["全部通过", "通过", "OK"])
def test_fail_never_completes_whatever_the_text_says(acceptance_workspace: str, text: str) -> None:  # noqa: F811
    svc = _accepting(acceptance_workspace)

    with pytest.raises(TransitionGuardError, match="fail"):
        svc.transition_status(CHG, "completed", approver="李四", verification_conclusion=text, verification_result="fail")

    cr = svc.get_change_request(CHG)
    assert cr is not None and cr.status == "accepting"


def test_partial_needs_the_explicit_partial_switch(acceptance_workspace: str) -> None:  # noqa: F811
    svc = _accepting(acceptance_workspace)

    with pytest.raises(TransitionGuardError, match="partial"):
        svc.transition_status(CHG, "completed", approver="李四", verification_result="partial")
    cr = svc.transition_status(CHG, "completed", approver="李四", verification_result="partial", allow_partial_verification=True)

    assert cr is not None and cr.status == "completed"


def test_pass_with_a_text_that_says_it_failed_is_refused_as_contradictory(acceptance_workspace: str) -> None:  # noqa: F811
    svc = _accepting(acceptance_workspace)

    with pytest.raises(TransitionGuardError, match="矛盾"):
        svc.transition_status(CHG, "completed", approver="李四", verification_conclusion="不通过", verification_result="pass")


def test_an_unknown_result_is_refused(acceptance_workspace: str) -> None:  # noqa: F811
    svc = _accepting(acceptance_workspace)

    with pytest.raises(TransitionGuardError, match="不认识"):
        svc.transition_status(CHG, "completed", approver="李四", verification_result="maybe")


def test_without_a_result_the_old_keyword_rule_still_applies(acceptance_workspace: str) -> None:  # noqa: F811
    svc = _accepting(acceptance_workspace)

    with pytest.raises(TransitionGuardError, match="验证结论"):
        svc.transition_status(CHG, "completed", approver="李四", verification_conclusion="OK")
    cr = svc.transition_status(CHG, "completed", approver="李四", verification_conclusion="全部通过")

    assert cr is not None and cr.status == "completed"
