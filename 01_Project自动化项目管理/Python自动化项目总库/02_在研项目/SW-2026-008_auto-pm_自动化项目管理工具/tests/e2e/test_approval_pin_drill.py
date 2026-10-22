"""Approval PIN (gap 9): once the user's approver PIN is committed, an agent cannot approve or accept in the user's name.

The drill plays the user's one-time setup (a verifier committed to ``SYS-2026-001_WorkspaceGovernance/approvers.json``),
then tries every way an agent could approve: the command line without a terminal, a pseudo terminal with a guessed PIN,
its own key written into the working tree, the cockpit's buttons and the Facade called from a script.  Only the PIN
typed into a terminal approves.  Every refusal must leave the store, the Decision folder and the CHG untouched.
"""

from __future__ import annotations

import json
import os
import select
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.e2e.test_closure_drill import APPROVER, Drill, Step, comment_files, make_drill
from tests.e2e.test_ide_lane_drill import Lane
from tests.e2e.test_pmf_plc import (
    PROJECT_ID,
    benchmark_tar,  # noqa: F401 - module fixture re-used by name
    git,
)
from tests.e2e.test_raw_requirement_drill import _approve_from_one_sentence

USER_PIN = "relay-K1-on"
GUESSED_PIN = "baiyang2026"


def commit_approver_pin(drill: Drill, pin: str = USER_PIN, approver: str = APPROVER) -> None:
    """The user's one-time setup: ``pm approver-pin init`` (hidden prompt) and a commit of the verifier file."""

    from auto_pm.application.core.approval_proof_service import (
        REGISTRY_RELATIVE_PATH,
        ApprovalProofService,
        make_key,
    )

    service = ApprovalProofService(drill.root)
    # A cheap scrypt cost keeps the drill quick; the field file uses the full cost.
    service.write_working_keys([make_key(approver, pin, n=2**10)])
    git(drill.root, "add", REGISTRY_RELATIVE_PATH)
    git(drill.root, "commit", "-q", "--no-verify", "-m", "approver pin", "--", REGISTRY_RELATIVE_PATH)


def cli_in_terminal(drill: Drill, typed: list[str], *arguments: str) -> Step:
    """Run one command with a terminal on its standard input and type ``typed`` into it, as a person would.

    Each line is typed only after its prompt appeared: a hidden prompt switches the echo off and flushes what was
    typed before, exactly as a real terminal does.
    """

    command = [sys.executable, str(drill.tools / "launcher.py"), "-w", str(drill.root), *arguments]
    master, slave = os.openpty()
    stderr = b""
    try:
        process = subprocess.Popen(
            command, stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=drill._env(), start_new_session=True
        )
        os.close(slave)
        assert process.stderr is not None
        pending = list(typed)
        deadline = time.monotonic() + 600
        while pending and process.poll() is None and time.monotonic() < deadline:
            ready, _, _ = select.select([process.stderr], [], [], 0.2)
            if ready:
                chunk = os.read(process.stderr.fileno(), 4096)
                stderr += chunk
            if stderr.count("口令".encode()) and stderr.rstrip().endswith(b":"):
                os.write(master, (pending.pop(0) + "\n").encode("utf-8"))
                stderr += b"\n"
        stdout, rest = process.communicate(timeout=600)
        stderr += rest
    finally:
        os.close(master)
    step = Step(" ".join(arguments[:2]) + " (terminal)", process.returncode, stdout.decode("utf-8", "replace"), stderr.decode("utf-8", "replace"))
    drill.log.append(step)
    return step


def ledger_snapshot(drill: Drill) -> tuple[object, ...]:
    """Everything an approval writes: missions, the Decision folder and the CHG files."""

    from auto_pm.infrastructure.continuity_store import ContinuityStore

    missions = tuple(
        (mission.mission_id, mission.state.value)
        for mission in ContinuityStore(drill.root).list_missions(PROJECT_ID, include_terminal=True)
    )
    decisions = tuple(sorted(path.name for path in (drill.root / ".auto-pm" / "decisions").glob("*.json")))
    changes = tuple(
        sorted((str(path.relative_to(drill.root)), path.read_bytes()) for path in drill.root.rglob("CHG-*.md"))
    )
    return missions, decisions, changes


def _planned_card(drill: Drill, request_id: str) -> dict[str, str]:
    """The agent's part up to the scope card: inbox, the user's triage confirmation, plan (none of them is an approval)."""

    card, approved = _approve_from_one_sentence(drill, request_id)
    assert approved.returncode != 0, "已提交批准口令，agent 不带口令的批准却被接受了"
    return card


def test_p01_an_agent_without_a_terminal_cannot_approve_and_nothing_is_written(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    commit_approver_pin(drill)
    card = _planned_card(drill, "REQ-PIN-P01")
    before = ledger_snapshot(drill)
    # What D08 showed an agent does: the user's name and a reference it made up.
    approved = drill.cli(
        "pm", "approve", "--request-id", "REQ-PIN-P01", "--plan-hash", card["plan_hash"], "--approver", APPROVER,
        "--approval-evidence-ref", "user-confirmation:chat-REQ-PIN-P01",
    )
    assert approved.returncode != 0
    assert "批准口令" in approved.stderr and "不得索要或代填口令" in approved.stderr, approved.stderr
    assert ledger_snapshot(drill) == before, "被拒的批准不应写任务、决策包或变更单"


def test_p02_a_pseudo_terminal_with_a_guessed_pin_is_refused_and_counted(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    commit_approver_pin(drill)
    card = _planned_card(drill, "REQ-PIN-P02")
    before = ledger_snapshot(drill)
    guessed = cli_in_terminal(
        drill, [GUESSED_PIN], "pm", "approve", "--request-id", "REQ-PIN-P02", "--plan-hash", card["plan_hash"],
        "--approver", APPROVER,
    )
    assert guessed.returncode != 0
    assert "批准口令错误" in guessed.stderr and "再错 4 次" in guessed.stderr, drill.transcript()
    assert ledger_snapshot(drill) == before


def test_p03_the_users_pin_in_a_terminal_approves_and_names_the_user(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    commit_approver_pin(drill)
    card = _planned_card(drill, "REQ-PIN-P03")
    approved = cli_in_terminal(drill, [USER_PIN], "pm", "approve", "--request-id", "REQ-PIN-P03", "--plan-hash", card["plan_hash"])
    assert approved.returncode == 0, drill.transcript()
    assert approved.json()["authorization_status"] == "AUTHORIZED"
    decisions = [json.loads(path.read_text(encoding="utf-8")) for path in (drill.root / ".auto-pm" / "decisions").glob("*.json")]
    assert len(decisions) == 1
    text = json.dumps(decisions[0], ensure_ascii=False)
    assert APPROVER in text and "user-confirmation:pin-" in text, text
    assert "user-confirmation:chat-" not in text


def test_p04_a_key_the_agent_writes_into_the_working_tree_does_not_count(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    from auto_pm.application.core.approval_proof_service import ApprovalProofService, make_key

    drill = make_drill(tmp_path, benchmark_tar)
    commit_approver_pin(drill)
    card = _planned_card(drill, "REQ-PIN-P04")
    # The agent replaces the verifier file with its own key, without a commit.
    ApprovalProofService(drill.root).write_working_keys([make_key(APPROVER, GUESSED_PIN, n=2**10)])
    before = ledger_snapshot(drill)
    forged = cli_in_terminal(drill, [GUESSED_PIN], "pm", "approve", "--request-id", "REQ-PIN-P04", "--plan-hash", card["plan_hash"])
    assert forged.returncode != 0 and "批准口令错误" in forged.stderr, drill.transcript()
    assert ledger_snapshot(drill) == before
    status = drill.cli("pm", "approver-pin", "status")
    assert status.returncode == 0 and "不一致" in status.stdout, drill.transcript()


def test_p05_the_cockpit_button_and_a_script_calling_the_facade_cannot_approve_without_the_pin(
    tmp_path: Path, benchmark_tar: bytes  # noqa: F811
) -> None:
    from auto_pm.application.core.pm_cockpit_service import PmCockpitError, PmCockpitService
    from auto_pm.application.core.pm_facade_service import PmFacadeError, PmFacadeService

    drill = make_drill(tmp_path, benchmark_tar)
    commit_approver_pin(drill)
    card = _planned_card(drill, "REQ-PIN-P05")
    before = ledger_snapshot(drill)
    with pytest.raises(PmCockpitError, match="批准口令"):
        PmCockpitService(drill.root, approver=APPROVER).approve_scope("REQ-PIN-P05", card["plan_hash"])
    with pytest.raises(PmFacadeError, match="批准口令"):
        PmFacadeService(drill.root).approve_pending_planning_scope_card(
            "REQ-PIN-P05", expected_plan_hash=card["plan_hash"], approver=APPROVER,
            approval_evidence_ref="user-confirmation:chat-REQ-PIN-P05",
        )
    with pytest.raises(PmFacadeError, match="批准口令错误"):
        PmFacadeService(drill.root).approve_pending_planning_scope_card(
            "REQ-PIN-P05", expected_plan_hash=card["plan_hash"], approver=APPROVER,
            approval_evidence_ref="user-confirmation:chat-REQ-PIN-P05", approval_pin=GUESSED_PIN,
        )
    assert ledger_snapshot(drill) == before


def test_p06_final_acceptance_needs_the_users_pin_on_every_entrance(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    from auto_pm.application.core.pm_cockpit_service import PmCockpitError, PmCockpitService
    from auto_pm.application.core.pm_facade_service import PmFacadeError, PmFacadeService
    from auto_pm.infrastructure.continuity_store import ContinuityStore

    drill = make_drill(tmp_path, benchmark_tar)
    # Approved before the PIN was set up (old behaviour), then the user commits the PIN; the Run starts after that commit.
    lane = Lane(drill, "REQ-PIN-P06", comment_files(drill.root, "批准口令：最终验收"))
    commit_approver_pin(drill)
    lane.start()
    lane.write()
    lane.transition("VERIFYING")
    verified = lane.verify()
    assert verified.returncode == 0 and verified.json()["mission_state"] == "ACCEPTANCE_PENDING", drill.transcript()

    def state() -> str:
        return ContinuityStore(drill.root).get_mission(lane.mission_id).state.value

    agent = drill.cli("pm", "accept", "--mission-id", lane.mission_id)
    assert agent.returncode != 0 and "批准口令" in agent.stderr, drill.transcript()
    with pytest.raises(PmCockpitError, match="批准口令"):
        PmCockpitService(drill.root, approver=APPROVER).confirm_acceptance(lane.mission_id)
    with pytest.raises(PmFacadeError, match="批准口令"):
        PmFacadeService(drill.root).accept(lane.mission_id)
    guessed = cli_in_terminal(drill, [GUESSED_PIN], "pm", "accept", "--mission-id", lane.mission_id)
    assert guessed.returncode != 0
    assert state() == "ACCEPTANCE_PENDING"
    closed_early = lane.close()
    assert closed_early.returncode != 0, "没验收就收口了"

    accepted = cli_in_terminal(drill, [USER_PIN], "pm", "accept", "--mission-id", lane.mission_id)
    assert accepted.returncode == 0, drill.transcript()
    assert state() == "ACCEPTED"
    closed = lane.close()
    assert closed.returncode == 0 and closed.json()["state"] == "COMPLETED", drill.transcript()


def test_p07_five_wrong_pins_lock_approvals_even_for_the_right_pin(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    commit_approver_pin(drill)
    card = _planned_card(drill, "REQ-PIN-P07")
    arguments = ("pm", "approve", "--request-id", "REQ-PIN-P07", "--plan-hash", card["plan_hash"])
    for attempt in range(5):
        wrong = cli_in_terminal(drill, [f"{GUESSED_PIN}{attempt}"], *arguments)
        assert wrong.returncode != 0
    assert "锁定 15 分钟" in wrong.stderr, drill.transcript()
    right = cli_in_terminal(drill, [USER_PIN], *arguments)
    assert right.returncode != 0 and "锁定到" in right.stderr, drill.transcript()


def test_p08_the_side_doors_ask_for_the_pin_too(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    """decision create, change transition --to approved and implementation-card approve are approvals as well."""

    drill = make_drill(tmp_path, benchmark_tar)
    commit_approver_pin(drill)
    card = _planned_card(drill, "REQ-PIN-P08")
    before = ledger_snapshot(drill)
    for arguments in (
        ("decision", "create", "--change-id", card["change_id"], "--approver", APPROVER, "--pid", PROJECT_ID),
        ("change", "transition", card["change_id"], "--to", "approved", "--approver", APPROVER, "--pid", PROJECT_ID),
        ("implementation-card", "approve", "CARD-X-001", "--approver", APPROVER, "--approval-evidence", "user-confirmation:chat-x"),
    ):
        refused = drill.cli(*arguments)
        assert refused.returncode != 0, drill.transcript()
        assert "批准口令" in refused.stdout + refused.stderr, drill.transcript()
    assert ledger_snapshot(drill) == before
    setup = drill.cli("pm", "approver-pin", "init", "--approver", "agent-claims-to-be-user")
    # Refused as an agent session or as a session without a terminal, whichever the drill runs in.
    assert setup.returncode != 0 and "终端" in setup.stderr, drill.transcript()


# ---------------------------------------------------------------- audit 72: the three ways around the PIN, and their kin
def test_p09_a_pointed_away_git_does_not_switch_the_pin_off(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    """Audit 72 high-1: GIT_DIR, no git on PATH and a HEAD that points nowhere used to fall back to the format check."""

    drill = make_drill(tmp_path, benchmark_tar)
    commit_approver_pin(drill)
    card = _planned_card(drill, "REQ-PIN-P09")
    before = ledger_snapshot(drill)
    arguments = [
        sys.executable, str(drill.tools / "launcher.py"), "-w", str(drill.root), "pm", "approve", "--request-id", "REQ-PIN-P09",
        "--plan-hash", card["plan_hash"], "--approver", APPROVER, "--approval-evidence-ref", "user-confirmation:chat-REQ-PIN-P09",
    ]
    pointed = dict(drill._env(), GIT_DIR=str(tmp_path / "no-such-git-dir"), GIT_WORK_TREE=str(tmp_path))
    step = drill._call("pm approve (GIT_DIR)", arguments, pointed)
    assert step.returncode != 0 and "批准口令" in step.stderr, drill.transcript()
    no_git = dict(drill._env(), PATH=str(Path(sys.executable).parent))
    step = drill._call("pm approve (no git)", arguments, no_git)
    assert step.returncode != 0, drill.transcript()
    git(drill.root, "symbolic-ref", "HEAD", "refs/heads/nothing-here")
    step = drill._call("pm approve (HEAD nowhere)", arguments)
    assert step.returncode != 0 and "拒绝" in step.stderr, drill.transcript()
    git(drill.root, "symbolic-ref", "HEAD", "refs/heads/" + git(drill.root, "for-each-ref", "--format=%(refname:short)", "refs/heads").split()[0])
    assert ledger_snapshot(drill) == before


def test_p10_the_pin_is_looked_up_where_the_approval_is_written(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    """Audit 72 high-2: an empty --control-root used to skip the PIN while -w still received the approval."""

    drill = make_drill(tmp_path, benchmark_tar)
    commit_approver_pin(drill)
    card = _planned_card(drill, "REQ-PIN-P10")
    empty = tmp_path / "empty-control-root"
    empty.mkdir()
    before = ledger_snapshot(drill)
    for arguments in (
        ("change", "transition", card["change_id"], "--to", "approved", "--approver", APPROVER, "--pid", PROJECT_ID),
        ("decision", "create", "--change-id", card["change_id"], "--approver", APPROVER, "--pid", PROJECT_ID),
    ):
        step = drill._call(
            " ".join(arguments[:2]) + " (--control-root)",
            [sys.executable, str(drill.tools / "launcher.py"), "-w", str(drill.root), "--control-root", str(empty), *arguments],
        )
        assert step.returncode != 0 and "批准口令" in step.stdout + step.stderr, drill.transcript()
    assert ledger_snapshot(drill) == before


def test_p11_generic_state_commands_are_no_side_doors(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    """Audit 72 high-3: ``continuity mission transition --to ACCEPTED`` is no acceptance; the real one records the key."""

    from auto_pm.infrastructure.continuity_store import ContinuityStore

    drill = make_drill(tmp_path, benchmark_tar)
    lane = Lane(drill, "REQ-PIN-P11", comment_files(drill.root, "批准口令：侧门"))
    commit_approver_pin(drill)
    lane.start()
    lane.write()
    lane.transition("VERIFYING")
    assert lane.verify().returncode == 0, drill.transcript()
    mission = ContinuityStore(drill.root).get_mission(lane.mission_id)
    assert mission.state.value == "ACCEPTANCE_PENDING"
    side = drill.cli(
        "continuity", "mission", "transition", "--mission-id", lane.mission_id, "--to", "ACCEPTED",
        "--expected-version", str(mission.version), "--idempotency-key", "p11-side-door",
    )
    assert side.returncode != 0 and "pm accept" in side.stderr, drill.transcript()
    assert ContinuityStore(drill.root).get_mission(lane.mission_id).state.value == "ACCEPTANCE_PENDING"
    assert lane.close().returncode != 0, "没验收就收口了"
    # The user's acceptance leaves the key's reference in the transition record, so who accepted can be told afterwards.
    accepted = cli_in_terminal(drill, [USER_PIN], "pm", "accept", "--mission-id", lane.mission_id)
    assert accepted.returncode == 0, drill.transcript()
    with sqlite3.connect(drill.root / ".auto-pm" / "continuity.db") as connection:
        keys = [row[0] for row in connection.execute("SELECT idempotency_key FROM events WHERE aggregate_id=?", (lane.mission_id,))]
    assert any(key.startswith("pm-accept:") and "user-confirmation:pin-" in key for key in keys), keys
    # Work: a plain transition to READY is refused too (it skipped work authorize); covered in tests/core/test_approval_proof_service.py.
