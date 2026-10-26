"""TD-071 card 2: pm missions / park / unpark / switch over the store primitives of card 1.

Who may do what: with the user's words a card goes to "搁着" and another one is picked up; without
them an agent may only stop the card it holds into "等你".  Tokens come from and go to the wallet.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from auto_pm.cli.__main__ import cli
from auto_pm.core.continuity_execution_service import ContinuityExecutionError
from auto_pm.core.execution_adapter_service import ExecutionDispatchError, ExecutionDispatchService
from auto_pm.core.lease_handover_service import (
    AGENT_MARKERS,
    LeaseHandoverError,
    LeaseHandoverService,
)
from auto_pm.core.mission_switch_service import MissionSwitchError, MissionSwitchService
from click.testing import CliRunner

from auto_pm.contracts.continuity import RunState, WorkKind
from auto_pm.contracts.lease_reclaim import PARKED_TOKEN_PREFIX
from auto_pm.contracts.mission import MissionState
from auto_pm.infrastructure import lease_wallet
from auto_pm.infrastructure.continuity_store import ContinuityStoreError
from tests.core.test_continuity_execution_service import _start
from tests.core.test_mission_park_store import APPROVAL, PROJECT, Scene

pytestmark = pytest.mark.usefixtures("identity_guard_off")


A_FILE = "auto_pm/core/a.py"


class Switch(Scene):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        (root / "auto_pm" / "core").mkdir(parents=True)
        (root / A_FILE).write_text("print('half done')\n", encoding="utf-8")
        self.remember("RUN-001", "agent-a", "lease-secret")
        self.handover = LeaseHandoverService(root, store=self.store, now=self.clock)
        self.service = MissionSwitchService(root, store=self.store, now=self.clock, handover=self.handover)

    def start_second_run(self) -> None:
        _start(
            self.execution, run_id="RUN-002", work_id="WORK-002", executor_id="agent-b", lease_token="token-b",
            idempotency_key="create-run-b", declared_dirty_paths=[A_FILE], observed_dirty_paths=[A_FILE],
        )
        self.execution.transition_run("RUN-002", RunState.RUNNING, "agent-b", "token-b", "b-running")

    def remember(self, run_id: str, owner: str, token: str) -> None:
        lease_wallet.save(self.root, run_id=run_id, owner_id=owner, lease_token=token, epoch=self.store.get_grant_epoch(run_id))

    def park_a(self, approval: str = APPROVAL) -> Any:
        return self.service.park(
            mission_id="MISSION-A", reason="客户急改 IO 表", summary="OB1 改完，差测试", approval_evidence_ref=approval
        )

    def b_in_hand(self) -> None:
        """A parked by the user's word; B started and held by agent-b."""
        b = self.second_card()
        self.park_a()
        self.missions.transition(
            mission_id="MISSION-B", expected_version=b.version, new_state=MissionState.ACTIVE,
            root_work_id=None, idempotency_key="start-b",
        )
        self.start_second_run()
        self.remember("RUN-002", "agent-b", "token-b")

    def cli(self, *args: str) -> Any:
        return CliRunner().invoke(cli, ["-w", str(self.root), *args], catch_exceptions=False)


@pytest.fixture
def sw(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Switch:
    import auto_pm.ui.cli.pm_switch as pm_switch_cli

    for name in AGENT_MARKERS:
        monkeypatch.delenv(name, raising=False)
    scene = Switch(tmp_path / "ws")
    # The CLI drives the same service, so it shares the scene's test clock.
    monkeypatch.setattr(pm_switch_cli, "MissionSwitchService", lambda _root: scene.service)
    return scene


# ------------------------------------------------------------------ park


def test_an_agent_without_the_users_words_can_only_stop_its_card_into_waiting(sw: Switch) -> None:
    outcome = sw.park_a(approval="")

    assert outcome.mission.state is MissionState.BLOCKED
    assert sw.store.get_lease("RUN-001").lease_token.startswith(PARKED_TOKEN_PREFIX)
    assert sw.store.get_checkpoint(outcome.checkpoint_id).dirty_paths == (A_FILE,)
    board = sw.service.board(PROJECT)
    assert [m.mission_id for m in board.waiting] == ["MISSION-A"] and board.parked == ()
    # Waiting with a checkpoint: a plain transition back to ACTIVE would skip the checks, so it is refused.
    with pytest.raises(Exception, match="unpark_mission"):
        sw.missions.transition(
            mission_id="MISSION-A", expected_version=outcome.mission.version, new_state=MissionState.ACTIVE,
            root_work_id=None, idempotency_key="sneak-back",
        )
    # Only the user picks it back up.
    with pytest.raises(MissionSwitchError, match="只听用户的"):
        sw.service.unpark(mission_id="MISSION-A", as_owner="agent-a", approval_evidence_ref="")
    back = sw.service.unpark(mission_id="MISSION-A", as_owner="agent-a", approval_evidence_ref=APPROVAL)
    assert back.mission.state is MissionState.ACTIVE


def test_the_store_refuses_parked_without_the_users_words_and_waiting_from_blocked(sw: Switch) -> None:
    with pytest.raises(ContinuityStoreError, match="要用户一句话"):
        sw.park(approval_evidence_ref="")
    blocked = sw.missions.transition(
        mission_id="MISSION-A", expected_version=sw.a.version, new_state=MissionState.BLOCKED,
        root_work_id=None, idempotency_key="block-a",
    )
    with pytest.raises(ContinuityStoreError, match="只有在干的卡可以放进"):
        sw.park(expected_mission_version=blocked.version, approval_evidence_ref="", target_state=MissionState.BLOCKED)
    with pytest.raises(ContinuityStoreError, match="只能是 PARKED"):
        sw.park(expected_mission_version=blocked.version, target_state=MissionState.CANCELLED)


def test_park_with_the_users_words_goes_to_parked_and_needs_a_summary(sw: Switch) -> None:
    with pytest.raises(MissionSwitchError, match="不能为空"):
        sw.service.park(mission_id="MISSION-A", reason="x", summary=" ", approval_evidence_ref=APPROVAL)
    outcome = sw.park_a()
    assert outcome.mission.state is MissionState.PARKED
    assert sw.store.get_checkpoint(outcome.checkpoint_id).summary == "OB1 改完，差测试"
    # Re-running the same park after it landed is refused cleanly (the card is no longer in hand).
    with pytest.raises(MissionSwitchError):
        sw.park_a()


# ------------------------------------------------------------------ unpark


def test_unpark_hands_a_new_token_to_the_wallet_and_never_shows_it(sw: Switch) -> None:
    sw.park_a()
    outcome = sw.service.unpark(mission_id="MISSION-A", as_owner="claude:local", approval_evidence_ref=APPROVAL)

    token = lease_wallet.load(sw.root, run_id="RUN-001", owner_id="claude:local")
    assert token != "lease-secret" and sw.store.get_lease("RUN-001").lease_token == token
    assert outcome.epoch == sw.store.get_grant_epoch("RUN-001")
    assert outcome.checkpoint_summary == "OB1 改完，差测试"
    assert outcome.behind_main is None or outcome.behind_main == 0
    assert sw.store.get_run("RUN-001").state is RunState.RUNNING


def test_unpark_refuses_when_the_worktree_moved_while_parked(sw: Switch) -> None:
    sw.park_a()
    (sw.root / A_FILE).unlink()
    with pytest.raises(MissionSwitchError, match=f"少了改动: {A_FILE}"):
        sw.service.unpark(mission_id="MISSION-A", as_owner="agent-a", approval_evidence_ref=APPROVAL)
    assert sw.store.get_mission("MISSION-A").state is MissionState.PARKED


def test_unpark_of_a_card_that_is_not_parked_says_so(sw: Switch) -> None:
    with pytest.raises(MissionSwitchError, match="没有搁着"):
        sw.service.unpark(mission_id="MISSION-A", as_owner="agent-a", approval_evidence_ref=APPROVAL)


# ------------------------------------------------------------------ switch


def test_switch_without_a_target_only_recommends_the_last_parked(sw: Switch) -> None:
    sw.b_in_hand()
    before = sw.snapshot()
    outcome = sw.service.switch(
        project_id=PROJECT, to_mission_id=None, reason="", summary="", as_owner="", approval_evidence_ref=""
    )
    assert outcome.recommended_mission_id == "MISSION-A" and "请用户说一句" in outcome.note
    assert outcome.parked is None and outcome.started is None
    assert sw.snapshot() == before


def test_switch_needs_the_users_words_and_writes_nothing_without_them(sw: Switch) -> None:
    sw.b_in_hand()
    before = sw.snapshot()
    with pytest.raises(MissionSwitchError, match="只听用户的"):
        sw.service.switch(
            project_id=PROJECT, to_mission_id="MISSION-A", reason="r", summary="s", as_owner="agent-a",
            approval_evidence_ref="",
        )
    assert sw.snapshot() == before


def test_switch_parks_the_card_in_hand_and_picks_the_target_up(sw: Switch) -> None:
    sw.b_in_hand()
    outcome = sw.service.switch(
        project_id=PROJECT, to_mission_id="MISSION-A", reason="急活做完一半，等客户回图", summary="IO 表改了一半",
        as_owner="agent-a", approval_evidence_ref=APPROVAL,
    )
    assert outcome.parked is not None and outcome.parked.mission.mission_id == "MISSION-B"
    assert outcome.started is not None and outcome.started.mission.mission_id == "MISSION-A"
    board = sw.service.board(PROJECT)
    assert [m.mission_id for m in board.active] == ["MISSION-A"]
    assert [p.mission.mission_id for p in board.parked] == ["MISSION-B"]
    # Switching to the card already in hand is a no-op.
    again = sw.service.switch(
        project_id=PROJECT, to_mission_id="MISSION-A", reason="", summary="", as_owner="agent-a",
        approval_evidence_ref=APPROVAL,
    )
    assert again.parked is None and again.started is None and "已经在干" in again.note


def test_when_the_second_step_fails_the_first_card_stays_parked_and_a_rerun_finishes(sw: Switch) -> None:
    sw.b_in_hand()
    moved = sw.root / A_FILE
    moved.unlink()  # A's worktree no longer matches its checkpoint
    with pytest.raises(MissionSwitchError, match="MISSION-B 已搁着，MISSION-A 没起来，原因是：.*少了改动"):
        sw.service.switch(
            project_id=PROJECT, to_mission_id="MISSION-A", reason="r", summary="s", as_owner="agent-a",
            approval_evidence_ref=APPROVAL,
        )
    board = sw.service.board(PROJECT)
    assert board.active == () and {p.mission.mission_id for p in board.parked} == {"MISSION-A", "MISSION-B"}
    moved.write_text("print('half done')\n", encoding="utf-8")
    outcome = sw.service.switch(
        project_id=PROJECT, to_mission_id="MISSION-A", reason="r", summary="s", as_owner="agent-a",
        approval_evidence_ref=APPROVAL,
    )
    assert outcome.parked is None and outcome.started is not None
    assert sw.store.get_mission("MISSION-A").state is MissionState.ACTIVE


def test_switch_to_an_approved_card_that_never_started_points_to_confirm_start(sw: Switch) -> None:
    sw.second_card()
    outcome = sw.service.switch(
        project_id=PROJECT, to_mission_id="MISSION-B", reason="急活", summary="OB1 改完", as_owner="agent-b",
        approval_evidence_ref=APPROVAL,
    )
    assert outcome.parked is not None and outcome.parked.mission.state is MissionState.PARKED
    assert outcome.next_command == "main.py pm confirm-start --mission-id MISSION-B"


def test_switch_refuses_a_card_of_another_project_or_a_closed_one(sw: Switch) -> None:
    with pytest.raises(MissionSwitchError, match="不属于项目"):
        sw.service.switch(
            project_id="DJ-2026-009", to_mission_id="MISSION-A", reason="", summary="", as_owner="a",
            approval_evidence_ref=APPROVAL,
        )
    b = sw.second_card()
    sw.missions.transition(
        mission_id="MISSION-B", expected_version=b.version, new_state=MissionState.CANCELLED,
        root_work_id=None, idempotency_key="cancel-b",
    )
    with pytest.raises(MissionSwitchError, match="只能切到"):
        sw.service.switch(
            project_id=PROJECT, to_mission_id="MISSION-B", reason="r", summary="s", as_owner="a",
            approval_evidence_ref=APPROVAL,
        )
    assert sw.store.get_mission("MISSION-A").state is MissionState.ACTIVE


# ------------------------------------------------------------------ cancel, other commands, dispatch


def test_cancelling_a_parked_card_ends_its_run_and_closes_the_park(sw: Switch) -> None:
    sw.park_a()
    parked = sw.store.get_mission("MISSION-A")
    sw.missions.transition(
        mission_id="MISSION-A", expected_version=parked.version, new_state=MissionState.CANCELLED,
        root_work_id=None, idempotency_key="cancel-parked-a",
    )
    assert sw.store.get_run("RUN-001").state is RunState.CANCELLED
    assert sw.store.get_lease("RUN-001").lease_token.startswith("RELEASED:")
    assert sw.store.get_open_park("MISSION-A") is None
    board = sw.service.board(PROJECT)
    assert [m.mission_id for m in board.closed] == ["MISSION-A"] and board.parked == ()


def test_handoff_takeover_and_reclaim_refuse_a_parked_card_early_and_plainly(sw: Switch) -> None:
    handoff = sw.handover.handoff(run_id="RUN-001", to_owner="agent-b", lease_token="lease-secret", summary="交接")
    sw.park_a()
    with pytest.raises(LeaseHandoverError, match="搁着呢.*不需要再交接"):
        sw.handover.handoff(run_id="RUN-001", to_owner="agent-c", lease_token="lease-secret", summary="交接")
    with pytest.raises(LeaseHandoverError, match="搁着呢（MISSION-A，客户急改 IO 表），不能接手"):
        sw.handover.takeover(handoff_id=handoff.handoff.handoff_id, receiver_id="agent-b", lease_seconds=900, holder_pid=None)
    sw.clock.value = sw.clock.value + timedelta(days=2)
    with pytest.raises(LeaseHandoverError, match="搁着不是掉线"):
        sw.handover.reclaim(run_id="RUN-001", claimant_id="agent-b", lease_seconds=900, reason="dead?", holder_pid=None)


def test_dispatch_capacity_ignores_a_parked_lease_but_counts_a_held_one(sw: Switch) -> None:
    dispatch = ExecutionDispatchService.__new__(ExecutionDispatchService)
    dispatch._store = sw.store
    b = sw.second_card()
    with pytest.raises(ExecutionDispatchError, match="RUN-001.*只能一张在干"):
        dispatch._assert_parallel_capacity(b, "RUN-NEW", sw.clock())
    sw.park_a()
    dispatch._assert_parallel_capacity(b, "RUN-NEW", sw.clock())


def test_dispatch_refuses_a_fresh_run_for_a_parked_card(sw: Switch) -> None:
    """Codex P1 on #86: another READY Work of a parked Mission must not start behind pm unpark."""
    dispatch = ExecutionDispatchService.__new__(ExecutionDispatchService)
    dispatch._store = sw.store
    dispatch._assert_mission_not_parked(sw.store.get_mission("MISSION-A"))  # positive control
    sw.park_a()
    with pytest.raises(ExecutionDispatchError, match="MISSION-A 搁着呢.*pm unpark"):
        dispatch._assert_mission_not_parked(sw.store.get_mission("MISSION-A"))
    # An agent's own stop into "等你" (BLOCKED with an open park) is refused the same way.
    sw.service.unpark(mission_id="MISSION-A", as_owner="agent-a", approval_evidence_ref=APPROVAL)
    sw.park_a(approval="")
    assert sw.store.get_mission("MISSION-A").state is MissionState.BLOCKED
    with pytest.raises(ExecutionDispatchError, match="搁着呢"):
        dispatch._assert_mission_not_parked(sw.store.get_mission("MISSION-A"))


def test_a_dispatch_run_is_held_to_one_lease_per_project_inside_the_transaction(sw: Switch) -> None:
    """Codex P2 on #86: for a dispatch the project limit holds where the Run and lease are written,
    not only in the preflight count; other run starts keep their old rules."""
    sw.second_card()
    second = dict(
        run_id="RUN-002", work_id="WORK-002", executor_id="agent-b", lease_token="token-b",
        idempotency_key="create-run-b", declared_dirty_paths=[A_FILE], observed_dirty_paths=[A_FILE],
    )
    before = sw.snapshot()
    with pytest.raises(ContinuityExecutionError, match="RUN-001.*只能一张在干"):
        _start(sw.execution, one_holder_per_project=True, **second)
    assert sw.snapshot() == before
    sw.park_a()  # the parked lease is fenced and no longer counts
    _start(sw.execution, one_holder_per_project=True, **second)
    assert sw.store.get_run("RUN-002").state is RunState.READY


def test_a_parked_cards_other_work_cannot_start_a_run_by_any_path(sw: Switch) -> None:
    """Codex P1 on #86, store side: ``continuity run start`` does not go through dispatch, so the
    store itself refuses a fresh Run for a Work that a parked Mission's Decision authorizes."""
    sw.works.create_work(
        work_id="WORK-A2", subject_project_id=PROJECT, kind=WorkKind.GOVERNANCE, title="A 的第二件",
        owner="architect", scope_paths=[A_FILE], source_fingerprint="sha256:a2",
        idempotency_key="create-work-a2", read_only=True,
    )
    with sw.db() as conn, conn:  # shape WORK-A2 as authorized by A's Decision, like the real binding
        conn.execute(
            "UPDATE work_items SET authorization_ref=? WHERE work_id='WORK-A2'", (sw.a.authority.decision_id,)
        )
    sw.park_a()
    before = sw.snapshot()
    with pytest.raises(ContinuityExecutionError, match="MISSION-A 搁着呢.*pm unpark"):
        _start(
            sw.execution, run_id="RUN-A2", work_id="WORK-A2", idempotency_key="create-run-a2",
            declared_dirty_paths=[A_FILE], observed_dirty_paths=[A_FILE],
        )
    assert sw.snapshot() == before


def test_switch_with_a_blank_owner_refuses_before_parking_the_card_in_hand(sw: Switch) -> None:
    """Codex P2 on #86: an input error must not leave the card in hand parked."""
    sw.b_in_hand()
    before = sw.snapshot()
    with pytest.raises(MissionSwitchError, match="--as"):
        sw.service.switch(
            project_id=PROJECT, to_mission_id="MISSION-A", reason="r", summary="s", as_owner=" ",
            approval_evidence_ref=APPROVAL,
        )
    assert sw.snapshot() == before
    assert [m.mission_id for m in sw.service.board(PROJECT).active] == ["MISSION-B"]


# ------------------------------------------------------------------ CLI


def test_cli_missions_park_unpark_switch(sw: Switch) -> None:
    board = sw.cli("pm", "missions", "--pid", PROJECT)
    assert board.exit_code == 0, board.output
    assert [c["mission_id"] for c in json.loads(board.output)["active"]] == ["MISSION-A"]

    parked = sw.cli(
        "pm", "park", "--mission-id", "MISSION-A", "--reason", "急活", "--summary", "OB1 改完",
        "--approval-evidence-ref", APPROVAL,
    )
    assert parked.exit_code == 0, parked.output
    assert json.loads(parked.output)["state"] == "PARKED" and "lease-secret" not in parked.output

    board = json.loads(sw.cli("pm", "missions", "--pid", PROJECT).output)
    assert board["parked"][0]["checkpoint_summary"] == "OB1 改完"

    refused = CliRunner().invoke(
        cli, ["-w", str(sw.root), "pm", "unpark", "--mission-id", "MISSION-A", "--as", "agent-a", "--holder-pid", "none"]
    )
    assert refused.exit_code != 0 and "approval-evidence-ref" in refused.output

    recommend = sw.cli("pm", "switch", "--pid", PROJECT)
    assert recommend.exit_code == 0 and json.loads(recommend.output)["recommended_mission_id"] == "MISSION-A"

    back = sw.cli(
        "pm", "unpark", "--mission-id", "MISSION-A", "--as", "claude:local", "--approval-evidence-ref", APPROVAL,
        "--holder-pid", "none",
    )
    assert back.exit_code == 0, back.output
    payload = json.loads(back.output)
    token = lease_wallet.load(sw.root, run_id="RUN-001", owner_id="claude:local")
    assert payload["state"] == "ACTIVE" and token not in back.output and "sync_note" in payload


def test_cli_park_shows_stale_flag_after_seven_days(sw: Switch) -> None:
    sw.park_a()
    assert json.loads(sw.cli("pm", "missions", "--pid", PROJECT).output)["parked"][0]["stale"] is False
    sw.clock.value = sw.clock.value + timedelta(days=8)
    assert json.loads(sw.cli("pm", "missions", "--pid", PROJECT).output)["parked"][0]["stale"] is True


def test_park_record_survives_a_raw_sqlite_look(sw: Switch) -> None:
    sw.park_a()
    with sqlite3.connect(sw.root / ".auto-pm" / "continuity.db") as conn:
        payload = conn.execute("SELECT payload_json FROM events WHERE event_type='MISSION_PARKED'").fetchone()[0]
    request = json.loads(payload)["request"]
    assert request["target_state"] == "PARKED" and request["approval_evidence_ref"] == APPROVAL


def test_resume_picks_the_card_in_hand_and_lists_the_others(sw: Switch) -> None:
    from auto_pm.core.continuity_resume_service import ContinuityResumeService

    sw.b_in_hand()
    missions = sw.store.list_active_missions(PROJECT)
    chosen, others = ContinuityResumeService._select_mission(missions, "")
    assert chosen is not None and chosen.mission_id == "MISSION-B"
    assert [m.mission_id for m in others] == ["MISSION-A"]
    # Asking for the parked card by its root Work selects it explicitly.
    chosen, others = ContinuityResumeService._select_mission(missions, "WORK-001")
    assert chosen is not None and chosen.mission_id == "MISSION-A"
    assert [m.mission_id for m in others] == ["MISSION-B"]


@pytest.mark.parametrize(
    "words",
    ["agent-claude 自己写的", "thread:cmsg_user_says_go", "user-confirmation:short", "user-confirmation:agent-claude-self", "user-confirmation:codex/auto-ok"],
)
def test_words_that_are_not_the_users_own_are_refused_before_any_write(sw: Switch, words: str) -> None:
    """Audit 75: the user's words follow the planning approval rule, in the service and in the store."""

    before = sw.store.get_mission("MISSION-A")
    with pytest.raises(MissionSwitchError, match="请让用户说一句"):  # the service refuses first, with the hint
        sw.park_a(approval=words)
    assert sw.store.get_mission("MISSION-A") == before and sw.store.get_open_park("MISSION-A") is None
    with pytest.raises(ContinuityStoreError, match="user-confirmation|agent 或模型"):
        sw.park(approval_evidence_ref=words)  # the store refuses on its own as well

    sw.park_a()
    with pytest.raises(ContinuityStoreError, match="user-confirmation|agent 或模型"):
        sw.unpark(approval_evidence_ref=words)
    for call in (
        lambda: sw.service.unpark(mission_id="MISSION-A", as_owner="claude:local", approval_evidence_ref=words),
        lambda: sw.service.switch(
            project_id=PROJECT, to_mission_id="MISSION-A", reason="r", summary="s", as_owner="claude:local",
            approval_evidence_ref=words,
        ),
    ):
        with pytest.raises(MissionSwitchError, match="请让用户说一句"):
            call()
    assert sw.store.get_mission("MISSION-A").state is MissionState.PARKED


# ------------------------------------------------------------------ gap 9: the user's words are the PIN once it is committed
PIN = "relay-K1-on"


@pytest.fixture
def committed_pin(monkeypatch: pytest.MonkeyPatch) -> Any:
    """A committed verifier.  Reading it from Git HEAD is covered in test_approval_proof_service.py; a real commit here
    would move HEAD under the scene's live Runs."""

    from auto_pm.application.core.approval_proof_service import ApprovalProofService, make_key

    key = make_key("baiyang", PIN, n=2**10)
    return lambda: monkeypatch.setattr(ApprovalProofService, "committed_state", lambda self: ([key], ""))


def test_with_a_committed_pin_an_agent_cannot_park_unpark_or_switch_in_the_users_name(sw: Switch, committed_pin: Any) -> None:
    sw.b_in_hand()
    committed_pin()
    before = sw.snapshot()
    with pytest.raises(MissionSwitchError, match="批准口令"):
        sw.service.switch(
            project_id=PROJECT, to_mission_id="MISSION-A", reason="r", summary="s", as_owner="agent-a",
            approval_evidence_ref=APPROVAL,
        )
    with pytest.raises(MissionSwitchError, match="批准口令错误"):
        sw.service.switch(
            project_id=PROJECT, to_mission_id="MISSION-A", reason="r", summary="s", as_owner="agent-a",
            approval_evidence_ref=APPROVAL, approval_pin="guessed-pin-1",
        )
    with pytest.raises(MissionSwitchError, match="批准口令"):
        sw.service.park(mission_id="MISSION-B", reason="r", summary="s", approval_evidence_ref=APPROVAL)
    with pytest.raises(MissionSwitchError, match="批准口令"):
        sw.service.unpark(mission_id="MISSION-A", as_owner="agent-a", approval_evidence_ref=APPROVAL)
    assert sw.snapshot() == before
    # The user's PIN switches, and the record names the key instead of a reference the agent typed.
    outcome = sw.service.switch(
        project_id=PROJECT, to_mission_id="MISSION-A", reason="急活做完一半", summary="IO 表改了一半",
        as_owner="agent-a", approval_evidence_ref="", approval_pin=PIN,
    )
    assert outcome.started is not None and outcome.started.mission.mission_id == "MISSION-A"
    with sqlite3.connect(sw.store.db_path) as connection:
        dump = "\n".join(connection.iterdump())
    assert "user-confirmation:pin-" in dump, "切换记录里应留下口令编号"


def test_with_a_committed_pin_an_agent_alone_can_still_stop_its_card_into_waiting(sw: Switch, committed_pin: Any) -> None:
    committed_pin()
    assert sw.park_a(approval="").mission.state is MissionState.BLOCKED
