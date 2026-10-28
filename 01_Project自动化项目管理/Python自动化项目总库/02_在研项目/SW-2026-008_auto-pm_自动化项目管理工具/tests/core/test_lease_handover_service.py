"""M3-HANDOFF card: one-command handoff, the lease reclaim interface and the user-only risk acceptance (V04-R1 storage acceptance cases 1 and 3).

Case 1: one card is never worked on by two agents; the refusal names the holder and the lease end, and leaves nothing behind.
Case 3: after a power loss the card can be taken over safely: a live lease is refused (with the wait), an expired lease with the holder's
process proven gone is reclaimed and the epoch rises, an unidentifiable holder gives PENDING until the user signs, and the old holder
coming back is refused.  An agent session can never sign the risk acceptance.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import closing
from datetime import timedelta
from pathlib import Path

import pytest

from auto_pm.application.core.continuity_execution_service import (
    ContinuityExecutionError,
    ContinuityExecutionService,
)
from auto_pm.application.core.lease_handover_service import (
    LeaseHandoverError,
    LeaseHandoverService,
    agent_markers,
)
from auto_pm.contracts.continuity import RunState
from auto_pm.contracts.lease_reclaim import (
    GRACE_SECONDS,
    ProcessFingerprint,
    ProcessObservation,
    ProcessVerdict,
    ReclaimDecision,
)
from auto_pm.infrastructure import lease_wallet
from auto_pm.infrastructure.continuity_store import ContinuityStoreError
from tests.core.test_continuity_execution_service import Clock, _checkpoint, _services, _start

RUN = "RUN-001"
HOST = "host:test-machine"
HOLDER_PID = 4242
FINGERPRINT = ProcessFingerprint(host_id=HOST, pid=HOLDER_PID, start_time="1000", image_sha256="a" * 64, cmdline_sha256="b" * 64)


class Processes:
    """A fake process table: what the probe would observe for each pid."""

    def __init__(self) -> None:
        self.table: dict[int, ProcessObservation | None] = {}

    def observe(self, pid: int) -> ProcessObservation | None:
        return self.table.get(pid, ProcessObservation(pid_exists=False))

    def fingerprint(self, pid: int) -> ProcessFingerprint | None:
        seen = self.table.get(pid)
        if seen is None or not seen.pid_exists or seen.start_time is None:
            return None
        return ProcessFingerprint(HOST, pid, seen.start_time, seen.image_sha256, seen.cmdline_sha256)

    def alive(self, pid: int = HOLDER_PID) -> None:
        self.table[pid] = ProcessObservation(pid_exists=True, start_time="1000", image_sha256="a" * 64, cmdline_sha256="b" * 64)

    def dead(self, pid: int = HOLDER_PID) -> None:
        self.table[pid] = ProcessObservation(pid_exists=False)

    def unreadable(self, pid: int = HOLDER_PID) -> None:
        self.table[pid] = None


class Scene:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True)
        self.clock = Clock()
        _work, self.execution = _services(root, self.clock)
        self.store = self.execution._store
        self.processes = Processes()
        self.service = LeaseHandoverService(
            root,
            store=self.store,
            now=self.clock,
            observe=self.processes.observe,
            fingerprint=self.processes.fingerprint,
            host_id=lambda: HOST,
        )
        _start(self.execution)
        self.execution.transition_run(RUN, RunState.RUNNING, "agent-a", "lease-secret", "to-running")

    def events(self) -> int:
        with closing(sqlite3.connect(self.root / ".auto-pm" / "continuity.db")) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])

    def record_holder(self) -> None:
        self.processes.alive()
        assert self.service.record_holder(RUN, "agent-a", "lease-secret", HOLDER_PID, "holder-a")

    def expire(self, extra_seconds: int = 1) -> None:
        expires = self.store.get_lease(RUN).expires_at
        from datetime import datetime

        self.clock.value = datetime.fromisoformat(expires) + timedelta(seconds=GRACE_SECONDS + extra_seconds)

    def reclaim(self, claimant: str = "agent-b"):  # type: ignore[no-untyped-def]
        return self.service.reclaim(run_id=RUN, claimant_id=claimant, lease_seconds=900, reason="power loss", holder_pid=None)


@pytest.fixture
def scene(tmp_path: Path) -> Scene:
    return Scene(tmp_path / "ws")


# ---------------------------------------------------------------- case 1
def test_case1_a_second_agent_is_refused_with_the_holder_and_the_lease_end_and_nothing_is_written(scene: Scene) -> None:
    events = scene.events()

    with pytest.raises(ContinuityExecutionError) as refused:
        _start(scene.execution, run_id="RUN-002", executor_id="agent-b", lease_token="token-b", idempotency_key="create-run-b")

    message = str(refused.value)
    assert "Work 已有非终态 Run" in message
    assert "RUN-001" in message and "agent-a" in message and "租约到" in message
    assert "lease-secret" not in message
    assert scene.events() == events
    assert [run.run_id for run in scene.store.list_runs("WORK-001")] == [RUN]


def test_case1_two_agents_starting_the_same_card_at_the_same_instant_only_one_succeeds(tmp_path: Path) -> None:
    clock = Clock()
    root = tmp_path / "race"
    root.mkdir()
    _work, first = _services(root, clock)
    second = ContinuityExecutionService(root, store=type(first._store)(root, _clock=clock), now=clock)
    barrier = threading.Barrier(2)
    results: dict[str, str] = {}

    def start(service: ContinuityExecutionService, run_id: str, owner: str) -> None:
        barrier.wait()
        try:
            _start(service, run_id=run_id, executor_id=owner, lease_token=f"token-{owner}", idempotency_key=f"start-{owner}")
            results[owner] = "ok"
        except ContinuityExecutionError as error:
            results[owner] = str(error)

    threads = [threading.Thread(target=start, args=(first, "RUN-A", "agent-a")), threading.Thread(target=start, args=(second, "RUN-B", "agent-b"))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)

    assert sorted(results.values()).count("ok") == 1, results
    assert len(first._store.list_runs("WORK-001")) == 1


def test_case1_a_write_with_a_stale_token_names_the_current_holder(scene: Scene) -> None:
    with pytest.raises(ContinuityExecutionError, match="lease ownership 不匹配") as refused:
        _checkpoint(scene.execution, lease_token="not-the-token")
    assert "agent-a" in str(refused.value) and "not-the-token" not in str(refused.value)


# ---------------------------------------------------------------- case 3
def test_case3_a_live_lease_is_refused_with_the_wait_and_nothing_is_written(scene: Scene) -> None:
    scene.record_holder()
    scene.processes.dead()
    events = scene.events()

    outcome = scene.reclaim()

    assert outcome.decision is ReclaimDecision.REFUSE_LIVE_LEASE
    assert outcome.wait_seconds > GRACE_SECONDS and "pm handoff" in outcome.exit_path
    assert outcome.holder_owner_id == "agent-a" and outcome.lease is None
    assert scene.events() == events
    assert scene.store.get_lease(RUN).owner_id == "agent-a"


def test_case3_inside_the_grace_period_the_lease_still_counts_as_live(scene: Scene) -> None:
    scene.record_holder()
    scene.processes.dead()
    scene.expire(extra_seconds=-5)  # expired, but within the 120 s grace

    assert scene.reclaim().decision is ReclaimDecision.REFUSE_LIVE_LEASE


def test_case3_expired_and_holder_proven_dead_is_reclaimed_and_the_epoch_rises(scene: Scene) -> None:
    scene.record_holder()
    epoch_before = scene.store.get_grant_epoch(RUN)
    scene.processes.dead()
    scene.expire()

    outcome = scene.reclaim()

    assert outcome.decision is ReclaimDecision.ALLOW and outcome.process_verdict is ProcessVerdict.PROVEN_DEAD
    assert outcome.lease is not None and outcome.lease.owner_id == "agent-b"
    assert outcome.lease.epoch > epoch_before
    assert scene.store.get_grant_epoch(RUN) == outcome.lease.epoch
    token = lease_wallet.load(scene.root, run_id=RUN, owner_id="agent-b")
    assert scene.store.get_lease(RUN).lease_token == token
    with closing(sqlite3.connect(scene.root / ".auto-pm" / "continuity.db")) as conn:
        payload = conn.execute("SELECT payload_json FROM events WHERE event_type='LEASE_RECLAIMED'").fetchone()[0]
    assert "agent-a" in payload and "agent-b" in payload and "power loss" in payload and token not in payload


def test_case3_the_old_holder_coming_back_is_refused_and_writes_nothing(scene: Scene) -> None:
    scene.record_holder()
    epoch_before = scene.store.get_grant_epoch(RUN)
    scene.processes.dead()
    scene.expire()
    outcome = scene.reclaim()
    assert outcome.lease is not None
    events = scene.events()

    with pytest.raises(ContinuityExecutionError, match="lease ownership 不匹配"):
        _checkpoint(scene.execution, checkpoint_id="CP-LATE", idempotency_key="late")
    with pytest.raises(ContinuityExecutionError):
        scene.execution.renew_lease(RUN, "agent-a", "lease-secret", 900, "late-renew")
    new_token = lease_wallet.load(scene.root, run_id=RUN, owner_id="agent-b")
    with pytest.raises(ContinuityExecutionError, match="STALE"):
        _checkpoint(
            scene.execution, owner_id="agent-b", lease_token=new_token, checkpoint_id="CP-OLD-EPOCH", idempotency_key="old-epoch", expected_epoch=epoch_before
        )

    assert scene.events() == events
    assert _checkpoint(
        scene.execution, owner_id="agent-b", lease_token=new_token, checkpoint_id="CP-B", idempotency_key="b-cp", expected_epoch=outcome.lease.epoch
    ).checkpoint_id == "CP-B"


def test_case3_a_holder_still_alive_is_never_pre_empted(scene: Scene) -> None:
    scene.record_holder()
    scene.expire()
    events = scene.events()

    outcome = scene.reclaim()

    assert outcome.decision is ReclaimDecision.REFUSE_PROCESS_ALIVE
    assert scene.events() == events and scene.store.get_lease(RUN).owner_id == "agent-a"


def test_case3_an_unidentifiable_holder_is_pending_until_the_user_signs(scene: Scene) -> None:
    scene.expire()  # no holder process was ever recorded: nobody can tell whether it is still running
    events = scene.events()

    pending = scene.reclaim()

    assert pending.decision is ReclaimDecision.PENDING and pending.process_verdict is ProcessVerdict.UNKNOWN
    assert "pm sign-risk" in pending.exit_path and "--claimant agent-b" in pending.exit_path
    assert scene.events() == events

    signature = scene.service.sign_risk(
        run_id=RUN, claimant_id="agent-b", signer="fubai", environ={}, stdin_is_tty=True, stdout_is_tty=True
    )
    assert signature.startswith("RISK-")
    assert scene.reclaim(claimant="agent-c").decision is ReclaimDecision.PENDING  # the signature names one claimant only

    allowed = scene.reclaim()
    assert allowed.decision is ReclaimDecision.ALLOW and allowed.lease is not None and allowed.lease.owner_id == "agent-b"
    with closing(sqlite3.connect(scene.root / ".auto-pm" / "continuity.db")) as conn:
        payload = conn.execute("SELECT payload_json FROM events WHERE event_type='LEASE_RECLAIMED'").fetchone()[0]
    assert signature in payload


def test_case3_an_unreadable_process_table_is_unknown_never_dead(scene: Scene) -> None:
    scene.record_holder()
    scene.processes.unreadable()
    scene.expire()

    assert scene.reclaim().decision is ReclaimDecision.PENDING


@pytest.mark.parametrize(
    ("environ", "stdin_tty", "stdout_tty"),
    [
        ({"CLAUDECODE": "1"}, True, True),
        ({"AUTO_PM_AGENT": "trae:cn"}, True, True),
        ({"CODEX_SANDBOX": "seatbelt"}, True, True),
        ({}, False, True),
        ({}, True, False),
    ],
)
def test_case3_an_agent_signed_risk_acceptance_is_refused_and_nothing_is_written(
    scene: Scene, environ: dict[str, str], stdin_tty: bool, stdout_tty: bool
) -> None:
    scene.expire()
    events = scene.events()

    with pytest.raises(LeaseHandoverError, match="agent|交互式终端"):
        scene.service.sign_risk(
            run_id=RUN, claimant_id="agent-b", signer="claude:local", environ=environ, stdin_is_tty=stdin_tty, stdout_is_tty=stdout_tty
        )

    assert scene.events() == events
    assert scene.reclaim().decision is ReclaimDecision.PENDING


def test_a_risk_acceptance_is_refused_when_the_holder_process_is_known(scene: Scene) -> None:
    scene.record_holder()
    scene.processes.dead()
    scene.expire()

    with pytest.raises(LeaseHandoverError, match="不需要也不允许"):
        scene.service.sign_risk(run_id=RUN, claimant_id="agent-b", signer="fubai", environ={}, stdin_is_tty=True, stdout_is_tty=True)


def test_agent_markers_lists_only_markers_with_a_value() -> None:
    assert agent_markers({"CLAUDECODE": "1", "AUTO_PM_AGENT": " ", "PATH": "x"}) == ["CLAUDECODE"]


# ---------------------------------------------------------------- the store re-checks inside its write transaction
def test_the_store_refuses_a_reclaim_of_a_live_lease_even_when_the_caller_said_dead(scene: Scene) -> None:
    lease = scene.store.get_lease(RUN)
    with pytest.raises(ContinuityStoreError, match="租约仍有效"):
        scene.store.reclaim_lease(
            run_id=RUN, expected_owner_id="agent-a", expected_lease_version=lease.version, claimant_id="agent-b", new_token="t" * 64,
            lease_seconds=900, process_verdict=ProcessVerdict.PROVEN_DEAD, risk_acceptance_id="", reason="race", idempotency_key="race-1",
        )


def test_the_store_refuses_a_reclaim_after_the_holder_renewed(scene: Scene) -> None:
    lease = scene.store.get_lease(RUN)
    scene.execution.renew_lease(RUN, "agent-a", "lease-secret", 900, "renew-1")
    scene.expire()
    with pytest.raises(ContinuityStoreError, match="已变化"):
        scene.store.reclaim_lease(
            run_id=RUN, expected_owner_id="agent-a", expected_lease_version=lease.version, claimant_id="agent-b", new_token="t" * 64,
            lease_seconds=900, process_verdict=ProcessVerdict.PROVEN_DEAD, risk_acceptance_id="", reason="race", idempotency_key="race-2",
        )


@pytest.mark.parametrize(
    ("verdict", "risk", "message"),
    [
        (ProcessVerdict.ALIVE, "", "仍在运行"),
        (ProcessVerdict.UNKNOWN, "", "pm sign-risk"),
        (ProcessVerdict.UNKNOWN, "RISK-FORGED", "已失效"),
        (ProcessVerdict.PROVEN_DEAD, "RISK-X", "不需要风险签署"),
    ],
)
def test_the_store_refuses_a_reclaim_without_its_exact_authority(scene: Scene, verdict: ProcessVerdict, risk: str, message: str) -> None:
    scene.expire()
    lease = scene.store.get_lease(RUN)
    events = scene.events()
    with pytest.raises(ContinuityStoreError, match=message):
        scene.store.reclaim_lease(
            run_id=RUN, expected_owner_id="agent-a", expected_lease_version=lease.version, claimant_id="agent-b", new_token="t" * 64,
            lease_seconds=900, process_verdict=verdict, risk_acceptance_id=risk, reason="test", idempotency_key=f"refuse-{verdict}-{risk}",
        )
    assert scene.events() == events


def test_an_exact_reclaim_replay_changes_nothing(scene: Scene) -> None:
    scene.expire()
    lease = scene.store.get_lease(RUN)
    arguments = dict(
        run_id=RUN, expected_owner_id="agent-a", expected_lease_version=lease.version, claimant_id="agent-b", new_token="t" * 64,
        lease_seconds=900, process_verdict=ProcessVerdict.PROVEN_DEAD, risk_acceptance_id="", reason="test", idempotency_key="replay-1",
    )
    first = scene.store.reclaim_lease(**arguments)
    events = scene.events()

    assert scene.store.reclaim_lease(**arguments) == first
    assert scene.events() == events


def test_the_holder_cannot_reclaim_from_itself(scene: Scene) -> None:
    scene.expire()
    with pytest.raises(LeaseHandoverError, match="续租"):
        scene.reclaim(claimant="agent-a")


def test_the_recorded_holder_process_belongs_to_one_epoch(scene: Scene) -> None:
    scene.record_holder()
    assert scene.store.holder_process(RUN) == FINGERPRINT
    handoff = scene.execution.create_checkpoint_bound_handoff(
        checkpoint_id=_checkpoint(scene.execution).checkpoint_id, from_owner="agent-a", to_owner="agent-b", lease_token="lease-secret",
        new_lease_token="token-b", lease_seconds=900, idempotency_key="ho",
    )
    assert handoff[1].owner_id == "agent-b"
    assert scene.store.holder_process(RUN) is None  # the new holder has not recorded its own process yet: a reclaim would see UNKNOWN


# ---------------------------------------------------------------- one-command handoff and takeover
def test_handoff_then_takeover_moves_the_run_and_the_receiver_never_sees_a_token(scene: Scene) -> None:
    lease_wallet.save(scene.root, run_id=RUN, owner_id="agent-a", lease_token="lease-secret", epoch=1)

    outcome = scene.service.handoff(run_id=RUN, to_owner="agent-b", lease_token=scene.service.token_for(RUN, "agent-a"), summary="halfway")
    again = scene.service.handoff(run_id=RUN, to_owner="agent-b", lease_token="lease-secret", summary="halfway")
    assert again.handoff.handoff_id == outcome.handoff.handoff_id  # an exact retry replays

    scene.processes.alive(777)
    lease = scene.service.takeover(handoff_id=outcome.handoff.handoff_id, receiver_id="agent-b", lease_seconds=900, holder_pid=777)

    assert lease.owner_id == "agent-b" and lease.epoch == scene.store.get_grant_epoch(RUN) and lease.holder_process_recorded
    assert Path(lease.wallet_path).is_file()
    token = lease_wallet.load(scene.root, run_id=RUN, owner_id="agent-b")
    assert token != "lease-secret" and scene.store.get_lease(RUN).lease_token == token
    with pytest.raises(lease_wallet.LeaseWalletError):
        lease_wallet.load(scene.root, run_id=RUN, owner_id="agent-a")
    with pytest.raises(LeaseHandoverError, match="接收方"):
        scene.service.takeover(handoff_id=outcome.handoff.handoff_id, receiver_id="agent-c", lease_seconds=900, holder_pid=None)
    retry = scene.service.takeover(handoff_id=outcome.handoff.handoff_id, receiver_id="agent-b", lease_seconds=900, holder_pid=None)
    assert retry.owner_id == "agent-b" and scene.store.get_lease(RUN).lease_token == token  # an exact retry keeps the same token


def test_a_handoff_to_the_holder_itself_or_of_a_finished_run_is_refused(scene: Scene) -> None:
    with pytest.raises(LeaseHandoverError, match="不同"):
        scene.service.handoff(run_id=RUN, to_owner="agent-a", lease_token="lease-secret", summary="x")
