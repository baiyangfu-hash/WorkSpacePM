"""TD-SW008-217 (audit 511): a conditional approval is an approval; the F16 guard must treat the two alike.

The agent refusal and the approval PIN in ``change transition`` named only ``--to approved``.  An agent session could put a
change order into ``conditionally_approved`` with no user evidence and no PIN, and the gates behind it (the commit hook, the
start of implementation) accept that status like ``approved``.  The user agreed to the fix on 2026-11-02 ("同意").

Three things are pinned here, for BOTH approving statuses: the refusal before any service is touched, the real chain
(refused transition -> the change order's file is unchanged -> implementation cannot start and the commit is refused), and the
rule that the set of approving statuses follows the status flow.
"""

from __future__ import annotations

from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from auto_pm.application.core.lease_handover_service import AGENT_MARKERS
from auto_pm.domain.change.constants import APPROVAL_CONCLUSIONS, APPROVING_STATUSES, STATUS_FLOW
from auto_pm.infrastructure.git_hook_enforcer import enforce_commit_msg
from auto_pm.ui.cli import change as change_cli
from auto_pm.ui.cli.change import change_group
from tests.cli.test_agent_cannot_approve import BAD_EVIDENCE, GOOD_EVIDENCE, _obj, untouched  # noqa: F401
from tests.infrastructure.test_git_hook_enforcer import _make_dual_root_fixture

pytestmark = pytest.mark.usefixtures("identity_guard_off")

APPROVING = ("approved", "conditionally_approved")
CHG = "CHG-SCPT-2026-346"  # the number _make_dual_root_fixture gives its change order


def _transition(obj: object, status: str, *extra: str) -> object:
    return CliRunner().invoke(
        change_group,
        ["transition", CHG, "--to", status, "--approver", "probe-bot", "--comment", "条件已说明", *extra],
        obj=obj,
    )


def _change_file(control_root: Path) -> Path:
    return next(control_root.rglob(f"{CHG}.md"))


# --- the rule: both approving statuses meet the same guard -------------------------------------------------------


def test_the_approving_statuses_are_exactly_the_approval_targets_of_the_status_flow() -> None:
    """A new approving status added to the flow without joining the guard's set turns this red."""

    approval_targets = STATUS_FLOW["under_review"] & (APPROVAL_CONCLUSIONS - {"rejected", "refused"})
    assert frozenset(approval_targets) == APPROVING_STATUSES == frozenset(APPROVING)


@pytest.mark.parametrize("status", APPROVING)
@pytest.mark.parametrize("marker", AGENT_MARKERS)
def test_an_agent_without_the_users_evidence_is_refused_for_both_approving_statuses(
    status: str, marker: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, untouched: list[str]  # noqa: F811
) -> None:
    monkeypatch.setenv(marker, "trae:cn")
    result = _transition(_obj(tmp_path), status)
    assert result.exit_code != 0  # type: ignore[attr-defined]
    assert "agent 会话" in result.output and "没有带用户原话凭据" in result.output  # type: ignore[attr-defined]
    assert untouched == []  # refused before the change service was even built


@pytest.mark.parametrize("status", APPROVING)
@pytest.mark.parametrize("evidence", BAD_EVIDENCE)
def test_bad_evidence_does_not_open_either_approving_status(
    status: str, evidence: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, untouched: list[str]  # noqa: F811
) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")
    result = _transition(_obj(tmp_path), status, "--approval-evidence-ref", evidence)
    assert result.exit_code != 0 and "agent 会话" in result.output  # type: ignore[attr-defined]
    assert untouched == []


@pytest.mark.parametrize("status", APPROVING)
def test_the_users_own_evidence_lets_an_agent_through_to_the_pin_and_the_service(
    status: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, untouched: list[str]  # noqa: F811
) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")
    result = _transition(_obj(tmp_path), status, "--approval-evidence-ref", GOOD_EVIDENCE)
    assert "agent 会话" not in result.output  # type: ignore[attr-defined]
    assert untouched  # not refused: the command went on to the service


@pytest.mark.parametrize("status", APPROVING)
def test_a_committed_pin_is_asked_for_both_approving_statuses(
    status: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, untouched: list[str]  # noqa: F811
) -> None:
    """The evidence lifts only the agent refusal; a committed PIN still has to be typed by the user."""

    seen: list[tuple[str, str]] = []

    def _pin(*_a: object, **kwargs: object) -> None:
        seen.append((str(kwargs.get("purpose")), str(kwargs.get("subject"))))
        raise click.ClickException("需要口令")

    monkeypatch.setattr(change_cli, "require_approval_pin", _pin)
    monkeypatch.setenv("CLAUDECODE", "1")
    result = _transition(_obj(tmp_path), status, "--approval-evidence-ref", GOOD_EVIDENCE)
    assert seen == [("change-approve", f":{CHG}")]
    assert "需要口令" in result.output  # type: ignore[attr-defined]
    assert untouched == []


@pytest.mark.parametrize("status", ["under_review", "implementing", "rejected"])
def test_the_other_transitions_are_still_not_this_guards_business(
    status: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, untouched: list[str]  # noqa: F811
) -> None:
    monkeypatch.setenv("AUTO_PM_AGENT", "trae:cn")
    result = _transition(_obj(tmp_path), status)
    assert "agent 会话" not in result.output  # type: ignore[attr-defined]
    assert untouched


# --- the chain: what the refusal protects ------------------------------------------------------------------------


@pytest.mark.parametrize("status", APPROVING)
def test_a_refused_self_approval_leaves_the_change_order_unapproved_so_work_and_commit_stay_blocked(
    status: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real files: the change order stays ``under_review``, implementation cannot start, the commit hook says no."""

    cand, ctrl, msg = _make_dual_root_fixture(tmp_path, chg_status="under_review")
    chg_file = _change_file(ctrl)
    before = chg_file.read_bytes()
    obj = _obj(ctrl)
    monkeypatch.setenv("CLAUDECODE", "1")

    # 1. the agent's own approval, with no evidence, is refused and writes nothing
    refused = _transition(obj, status)
    assert refused.exit_code != 0 and "没有带用户原话凭据" in refused.output  # type: ignore[attr-defined]
    assert chg_file.read_bytes() == before

    # 2. implementation cannot start from an unapproved change order (the flow only leaves approved states for it)
    started = _transition(obj, "implementing")
    assert started.exit_code != 0 and "不合法" in started.output  # type: ignore[attr-defined]
    assert chg_file.read_bytes() == before

    # 3. the commit hook refuses production code bound to it
    assert enforce_commit_msg(cand, msg, control_root=ctrl) == 1


@pytest.mark.parametrize("status", APPROVING)
def test_once_the_user_approves_either_status_the_same_commit_is_accepted(status: str, tmp_path: Path) -> None:
    """The other side of the chain, so the refusal above is the only thing that differs."""

    cand, ctrl, msg = _make_dual_root_fixture(tmp_path, chg_status=status)
    assert enforce_commit_msg(cand, msg, control_root=ctrl) == 0
