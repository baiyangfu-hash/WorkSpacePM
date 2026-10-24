"""Follow-up tests for the approver PIN on park cards and admission releases (audit 123, later additions).

Each test is written so that taking out the behaviour it names turns it red: the release proof in the facade, its
binding to the card and the release text, the PIN prompt of ``pm park / unpark / switch``, and the rule that a PIN
does not stop an ordinary card that needs no release.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from auto_pm.application.core.approval_proof_service import ApprovalProofService, make_key
from auto_pm.application.core.pm_facade_service import PmFacadeError, PmFacadeService
from auto_pm.contracts.mission import MissionState
from tests.cli.test_continuity import _create_args, _invoke, _repository
from tests.core.test_cockpit_api import APPROVER, EVIDENCE, _plan, _workspace
from tests.core.test_mission_park_store import APPROVAL, PROJECT
from tests.core.test_mission_switch_service import Switch, sw  # noqa: F401  (fixture)

PIN = "relay-K1-on-followup"
RELEASE = "user-confirmation:FOLLOW-B-0001"


def _commit_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    key = make_key("baiyang", PIN, n=2**10)
    monkeypatch.setattr(ApprovalProofService, "committed_state", lambda self: ([key], ""))


def _dump(db: Path) -> str:
    with closing(sqlite3.connect(db)) as connection:
        return "\n".join(connection.iterdump())


def test_a_release_is_recorded_as_the_pin_proof_and_never_as_the_string_the_caller_typed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _workspace(tmp_path)
    client = workspace.client()
    first = _plan(client, "REQ-FOLLOW-A")
    client.approve_plan(first, approver=APPROVER, approval_evidence_ref=EVIDENCE)
    facade = PmFacadeService(workspace.root)
    facade.materialize_planning_mission(first)
    second = _plan(client, "REQ-FOLLOW-B")
    _commit_pin(monkeypatch)

    client.approve_plan(second, approver="", approval_evidence_ref="", admission_release_ref=RELEASE, approval_pin=PIN)
    proved = facade.prove_admission_release(second, RELEASE, approval_pin=PIN)
    assert proved.startswith("user-confirmation:pin-") and proved != RELEASE
    facade.materialize_planning_mission(second, admission_release_ref=proved)

    dump = _dump(workspace.root / ".auto-pm" / "continuity.db")
    assert "FOLLOW-B-0001" not in dump, "the typed release string must not reach the ledger"
    assert proved in dump


def test_the_release_proof_is_bound_to_this_card_and_this_release_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _workspace(tmp_path)
    client = workspace.client()
    one = _plan(client, "REQ-FOLLOW-A")
    two = _plan(client, "REQ-FOLLOW-B")
    facade = PmFacadeService(workspace.root)
    _commit_pin(monkeypatch)

    same = facade.prove_admission_release(one, RELEASE, approval_pin=PIN)
    assert facade.prove_admission_release(one, RELEASE, approval_pin=PIN) == same
    assert facade.prove_admission_release(two, RELEASE, approval_pin=PIN) != same, "another card, another proof"
    assert facade.prove_admission_release(one, RELEASE + "X", approval_pin=PIN) != same, "another release, another proof"
    with pytest.raises(PmFacadeError, match="批准口令"):
        facade.prove_admission_release(one, RELEASE)
    # nothing asked for, nothing to prove
    assert facade.prove_admission_release(one, "") == ""


def test_park_unpark_and_switch_ask_the_user_for_the_pin_and_record_its_reference(
    sw: Switch, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    import auto_pm.ui.cli.pm_switch as pm_switch_cli

    _commit_pin(monkeypatch)
    asked: list[str] = []

    def typed(root: Any, *, summary: str) -> str:
        asked.append(summary)
        return PIN

    monkeypatch.setattr(pm_switch_cli, "read_approval_pin", typed)

    parked = sw.cli(
        "pm", "park", "--mission-id", "MISSION-A", "--reason", "急活", "--summary", "OB1 改完",
        "--approval-evidence-ref", APPROVAL,
    )
    assert parked.exit_code == 0, parked.output
    back = sw.cli(
        "pm", "unpark", "--mission-id", "MISSION-A", "--as", "agent-a", "--approval-evidence-ref", APPROVAL,
        "--holder-pid", "none",
    )
    assert back.exit_code == 0, back.output
    assert len(asked) == 2 and "MISSION-A" in asked[0] and "MISSION-A" in asked[1]
    dump = _dump(sw.store.db_path)
    assert "user-confirmation:pin-" in dump and APPROVAL not in dump.replace("user-confirmation:pin-", "")

    # a switch to a parked target asks for the PIN as well and picks the card up on the PIN's reference
    again = sw.cli(
        "pm", "park", "--mission-id", "MISSION-A", "--reason", "急活", "--summary", "OB1 又改完",
        "--approval-evidence-ref", APPROVAL,
    )
    assert again.exit_code == 0, again.output
    switched = sw.cli(
        "pm", "switch", "--pid", PROJECT, "--to", "MISSION-A", "--reason", "r", "--summary", "s", "--as", "agent-a",
        "--holder-pid", "none",
    )
    assert switched.exit_code == 0, switched.output
    assert len(asked) == 4 and "MISSION-A" in asked[3]
    assert sw.store.get_mission("MISSION-A").state is MissionState.ACTIVE
    # no target: only a recommendation, nothing to confirm, no prompt
    sw.cli("pm", "switch", "--pid", PROJECT)
    assert len(asked) == 4


def test_a_committed_pin_does_not_stop_an_ordinary_card_that_needs_no_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repository(tmp_path)
    _commit_pin(monkeypatch)

    created = _invoke(CliRunner(), tmp_path, _create_args("MISSION-FOLLOW-A"))

    assert created.exit_code == 0, created.output
