"""One-command agent handoff and the lease reclaim interface (M3-HANDOFF card: TD-SW008-063/064, V04-R1 storage acceptance cases 1 and 3).

- ``handoff``: the current holder checkpoints its Run and addresses an immutable handoff.v2 to the next agent in one call.
- ``takeover``: the receiver accepts it with a token it generates itself; the token goes to the local wallet, never to the user.
- ``reclaim``: another agent takes over a Run whose holder vanished (power loss, killed process) - only when the lease is no longer live
  (expired plus the 120 s grace) AND the holder's recorded process is proven gone; when nobody can tell, the answer is PENDING and only the
  user's own risk acceptance (``pm sign-risk``, interactive, never an agent) opens it.  An ALIVE holder or a live lease is never pre-empted.
- ``sign_risk``: records that acceptance; refused for a non-interactive session or a session that carries an agent marker.

Every write still goes through the store's own in-transaction checks; this service only sequences them and observes processes.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from auto_pm.core.continuity_execution_service import (
    ContinuityExecutionError,
    ContinuityExecutionService,
)

from auto_pm.contracts.continuity import CheckpointItem, HandoffV2, LeaseItem, RunState
from auto_pm.contracts.lease_reclaim import (
    GRACE_SECONDS,
    ProcessFingerprint,
    ProcessObservation,
    ProcessVerdict,
    ReclaimDecision,
    decide_reclaim,
    judge_process,
    lease_is_live,
)
from auto_pm.infrastructure import lease_wallet, process_probe
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError
from auto_pm.infrastructure.control_root_guard import (
    ControlRootGuardError,
    authority_path_covered,
    governed_worktree_snapshot,
)

# Environment variables that only an agent session sets (best effort; the single-user trust model of TD-SW008-065 applies): a risk acceptance
# signed from such a session is refused.  AUTO_PM_AGENT is the cockpit's own marker for any other agent.
AGENT_MARKERS = (
    "AUTO_PM_AGENT",
    "CLAUDECODE",
    "CLAUDE_CODE_ENTRYPOINT",
    "CODEX_SANDBOX",
    "CODEX_SANDBOX_NETWORK_DISABLED",
    "CODEX_THREAD_ID",
)
_TERMINAL_RUN_STATES = frozenset({RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED})


class LeaseHandoverError(RuntimeError):
    """Raised when a handoff, takeover, reclaim or risk signature cannot proceed; nothing was written."""


@dataclass(frozen=True)
class HandoffOutcome:
    handoff: HandoffV2
    checkpoint: CheckpointItem


@dataclass(frozen=True)
class LeaseOutcome:
    """The lease after a takeover or reclaim; the token stays in the wallet."""

    run_id: str
    owner_id: str
    epoch: int
    expires_at: str
    wallet_path: str
    holder_process_recorded: bool


@dataclass(frozen=True)
class ReclaimOutcome:
    decision: ReclaimDecision
    reason: str
    exit_path: str
    holder_owner_id: str
    lease_expires_at: str
    process_verdict: ProcessVerdict | None
    wait_seconds: int
    lease: LeaseOutcome | None = None


def agent_markers(environ: Mapping[str, str]) -> list[str]:
    """Names of the agent markers present (with a non-empty value) in an environment."""

    return [name for name in AGENT_MARKERS if environ.get(name, "").strip()]


def new_lease_token() -> str:
    return secrets.token_hex(32)


class LeaseHandoverService:
    """Sequence the store's handoff, transfer and reclaim primitives for agents; the control root is the only writer."""

    def __init__(
        self,
        control_root: str | Path,
        *,
        store: ContinuityStore | None = None,
        now: Callable[[], datetime] | None = None,
        observe: Callable[[int], ProcessObservation | None] = process_probe.observe,
        fingerprint: Callable[[int], ProcessFingerprint | None] = process_probe.fingerprint,
        host_id: Callable[[], str] = process_probe.local_host_id,
    ) -> None:
        self._root = Path(control_root).resolve()
        self._store = store or ContinuityStore(self._root)
        self._now = now or (lambda: datetime.now(UTC))
        self._execution = ContinuityExecutionService(self._root, store=self._store, now=self._now)
        self._observe = observe
        self._fingerprint = fingerprint
        self._host_id = host_id

    # ---------------------------------------------------------------- tokens
    def token_for(self, run_id: str, owner_id: str) -> str:
        """The holder's token from the local wallet (refused when the wallet belongs to someone else)."""

        try:
            return lease_wallet.load(self._root, run_id=run_id, owner_id=owner_id)
        except lease_wallet.LeaseWalletError as error:
            raise LeaseHandoverError(str(error)) from error

    def reusable_token(self, run_id: str, owner_id: str) -> str:
        """The wallet token when the wallet already holds one for this owner (an exact retry replays), else a fresh one."""

        try:
            record = lease_wallet.find(self._root, run_id)
        except lease_wallet.LeaseWalletError as error:
            raise LeaseHandoverError(str(error)) from error
        if record is not None and record["owner_id"] == owner_id:
            return str(record["lease_token"])
        return new_lease_token()

    def remember(self, run_id: str, owner_id: str, lease_token: str) -> str:
        try:
            epoch = self._store.get_grant_epoch(run_id)
            return str(lease_wallet.save(self._root, run_id=run_id, owner_id=owner_id, lease_token=lease_token, epoch=epoch))
        except (ContinuityStoreError, lease_wallet.LeaseWalletError, OSError) as error:
            raise LeaseHandoverError(f"口令已生效但写入本机钱包失败: {error}") from error

    def record_holder(self, run_id: str, owner_id: str, lease_token: str, holder_pid: int | None, idempotency_key: str) -> bool:
        """Record the holder's long-lived process for a later reclaim; ``False`` when no process could be fingerprinted (a reclaim then sees UNKNOWN)."""

        if holder_pid is None:
            return False
        observed = self._fingerprint(holder_pid)
        if observed is None:
            return False
        try:
            self._store.record_holder_process(
                run_id=run_id, owner_id=owner_id, lease_token=lease_token, fingerprint=observed, idempotency_key=idempotency_key
            )
        except ContinuityStoreError as error:
            raise LeaseHandoverError(str(error)) from error
        return True

    def _refuse_parked(self, run_id: str, action: str) -> None:
        """Early, friendly refusal for a parked Run (TD-071 design 4.4); the store refuses again in its write transaction."""

        try:
            park = self._store.get_open_park_for_run(run_id)
        except ContinuityStoreError as error:
            raise LeaseHandoverError(str(error)) from error
        if park is not None:
            raise LeaseHandoverError(
                f"这张卡搁着呢（{park.mission_id}，{park.reason}），{action}；请让用户说一句后用 pm unpark 拿回来"
            )

    # ---------------------------------------------------------------- handoff and takeover
    def handoff(self, *, run_id: str, to_owner: str, lease_token: str, summary: str) -> HandoffOutcome:
        """Checkpoint the Run's worktree and create the handoff addressed to ``to_owner``; deterministic ids make a retry an exact replay."""

        try:
            run = self._store.get_run(run_id)
            lease = self._store.get_lease(run_id)
        except ContinuityStoreError as error:
            raise LeaseHandoverError(str(error)) from error
        if run.state in _TERMINAL_RUN_STATES:
            raise LeaseHandoverError(f"Run 已是终态 {run.state.value}，不能交接")
        self._refuse_parked(run_id, "不需要再交接（搁着时已记过断点）")
        owner = lease.owner_id
        if owner == to_owner:
            raise LeaseHandoverError("接收方必须不同于当前持有者")
        if not summary.strip():
            raise LeaseHandoverError("交接摘要不能为空")
        try:
            _worktree, git_head, dirty = governed_worktree_snapshot(self._root, run.worktree_path, allow_external_linked=True)
        except ControlRootGuardError as error:
            raise LeaseHandoverError(str(error)) from error
        in_scope = [path for path in dirty if authority_path_covered(path, run.owned_paths)]
        digest = hashlib.sha256(f"{run_id}\x00{owner}\x00{to_owner}\x00{lease.version}".encode()).hexdigest()[:16].upper()
        try:
            checkpoint = self._execution.checkpoint(
                checkpoint_id=f"CKPT-HO-{digest}",
                run_id=run_id,
                owner_id=owner,
                lease_token=lease_token,
                summary=summary.strip(),
                git_head=git_head,
                dirty_paths=in_scope,
                evidence=[f"pm handoff: {owner} -> {to_owner}"],
                idempotency_key=f"pm-handoff:{digest}:checkpoint",
            )
            handoff = self._execution.create_handoff(
                handoff_id=f"HO-{digest}",
                checkpoint_id=checkpoint.checkpoint_id,
                from_owner=owner,
                to_owner=to_owner,
                lease_token=lease_token,
                idempotency_key=f"pm-handoff:{digest}:create",
            )
        except ContinuityExecutionError as error:
            raise LeaseHandoverError(str(error)) from error
        return HandoffOutcome(handoff=handoff, checkpoint=checkpoint)

    def get_handoff(self, handoff_id: str) -> HandoffV2:
        try:
            return self._store.get_handoff(handoff_id)
        except ContinuityStoreError as error:
            raise LeaseHandoverError(str(error)) from error

    def takeover(self, *, handoff_id: str, receiver_id: str, lease_seconds: int, holder_pid: int | None) -> LeaseOutcome:
        """Accept a handoff addressed to ``receiver_id`` with a token this call generates (or the wallet's, on an exact retry)."""

        handoff = self.get_handoff(handoff_id)
        self._refuse_parked(handoff.run_id, "不能接手（pm takeover）")
        if handoff.to_owner != receiver_id:
            raise LeaseHandoverError(f"交接 {handoff_id} 指定的接收方是 {handoff.to_owner}，不是 {receiver_id}")
        token = self.reusable_token(handoff.run_id, receiver_id)
        try:
            lease: LeaseItem = self._execution.accept_handoff(
                handoff_id=handoff_id,
                receiver_id=receiver_id,
                new_lease_token=token,
                lease_seconds=lease_seconds,
                idempotency_key=f"pm-takeover:{handoff_id}",
            )
        except ContinuityExecutionError as error:
            raise LeaseHandoverError(str(error)) from error
        path = self.remember(handoff.run_id, receiver_id, token)
        recorded = self.record_holder(handoff.run_id, receiver_id, token, holder_pid, f"pm-takeover:{handoff_id}:holder")
        return LeaseOutcome(
            run_id=lease.run_id,
            owner_id=lease.owner_id,
            epoch=self._store.get_grant_epoch(lease.run_id),
            expires_at=lease.expires_at,
            wallet_path=path,
            holder_process_recorded=recorded,
        )

    # ---------------------------------------------------------------- reclaim
    def judge_holder(self, run_id: str) -> tuple[ProcessVerdict, ProcessFingerprint | None]:
        try:
            recorded = self._store.holder_process(run_id)
        except ContinuityStoreError as error:
            raise LeaseHandoverError(str(error)) from error
        observation = self._observe(recorded.pid) if recorded is not None else None
        return judge_process(recorded, observation, local_host_id=self._host_id()), recorded

    def reclaim(
        self, *, run_id: str, claimant_id: str, lease_seconds: int, reason: str, holder_pid: int | None
    ) -> ReclaimOutcome:
        """Case 3 of the storage acceptance cases; a refusal or PENDING writes nothing."""

        try:
            run = self._store.get_run(run_id)
            lease = self._store.get_lease(run_id)
        except ContinuityStoreError as error:
            raise LeaseHandoverError(str(error)) from error
        if run.state in _TERMINAL_RUN_STATES:
            raise LeaseHandoverError(f"Run 已是终态 {run.state.value}，没有可回收的租约")
        self._refuse_parked(run_id, "搁着不是掉线，不用回收")
        if lease.owner_id == claimant_id:
            raise LeaseHandoverError("你已是当前持有者；请续租（continuity lease renew），不要回收")
        if not reason.strip():
            raise LeaseHandoverError("回收原因不能为空")
        now = self._now()
        expires = datetime.fromisoformat(lease.expires_at)
        if expires.tzinfo is None:
            raise LeaseHandoverError("lease expires_at 缺少时区")
        if lease_is_live(expires, now):
            wait = int((expires + timedelta(seconds=GRACE_SECONDS) - now).total_seconds()) + 1
            return ReclaimOutcome(
                decision=ReclaimDecision.REFUSE_LIVE_LEASE,
                reason="租约仍有效（含宽限期），不能回收",
                exit_path=f"请等对方交接（pm handoff），或约 {wait} 秒后租约失效再试",
                holder_owner_id=lease.owner_id,
                lease_expires_at=lease.expires_at,
                process_verdict=None,
                wait_seconds=wait,
            )
        verdict, _recorded = self.judge_holder(run_id)
        risk = self._store.reclaim_risk_acceptance(run_id, claimant_id) if verdict is ProcessVerdict.UNKNOWN else None
        result = decide_reclaim(
            lease_expires_at=expires, now=now, process=verdict, unknown_risk_accepted_by_decision=risk is not None
        )
        if result.decision is not ReclaimDecision.ALLOW:
            exit_path = result.exit_path
            if result.decision is ReclaimDecision.PENDING:
                exit_path = (
                    "无法判断原持有者的进程还在不在，不会自动接手。出路：请用户本人在自己的终端运行 "
                    f"`main.py pm sign-risk --run-id {run_id} --claimant {claimant_id}` 签署接受风险，然后再回收"
                )
            return ReclaimOutcome(
                decision=result.decision,
                reason=result.reason,
                exit_path=exit_path,
                holder_owner_id=lease.owner_id,
                lease_expires_at=lease.expires_at,
                process_verdict=verdict,
                wait_seconds=0,
            )
        token = new_lease_token()
        digest = hashlib.sha256(f"{run_id}\x00{lease.owner_id}\x00{lease.version}\x00{claimant_id}".encode()).hexdigest()[:16]
        try:
            reclaimed = self._store.reclaim_lease(
                run_id=run_id,
                expected_owner_id=lease.owner_id,
                expected_lease_version=lease.version,
                claimant_id=claimant_id,
                new_token=token,
                lease_seconds=lease_seconds,
                process_verdict=verdict,
                risk_acceptance_id=risk or "",
                reason=reason.strip(),
                idempotency_key=f"reclaim:{digest}",
            )
        except ContinuityStoreError as error:
            raise LeaseHandoverError(str(error)) from error
        path = self.remember(run_id, claimant_id, token)
        recorded = self.record_holder(run_id, claimant_id, token, holder_pid, f"reclaim:{digest}:holder")
        return ReclaimOutcome(
            decision=ReclaimDecision.ALLOW,
            reason=result.reason,
            exit_path="",
            holder_owner_id=lease.owner_id,
            lease_expires_at=lease.expires_at,
            process_verdict=verdict,
            wait_seconds=0,
            lease=LeaseOutcome(
                run_id=run_id,
                owner_id=reclaimed.owner_id,
                epoch=self._store.get_grant_epoch(run_id),
                expires_at=reclaimed.expires_at,
                wallet_path=path,
                holder_process_recorded=recorded,
            ),
        )

    # ---------------------------------------------------------------- the user's risk acceptance
    @staticmethod
    def signature_refusal(environ: Mapping[str, str], *, stdin_is_tty: bool, stdout_is_tty: bool) -> str:
        """Why this session may not sign a risk acceptance ('' when it may): only the user, typing in an interactive terminal, signs."""

        markers = agent_markers(environ)
        if markers:
            return "这是 agent 会话（" + "、".join(markers) + "），agent 不能签署接受风险；请用户本人在自己的终端运行"
        if not (stdin_is_tty and stdout_is_tty):
            return "接受风险只能由用户本人在交互式终端里签署（标准输入或输出不是终端）"
        return ""

    def sign_risk(
        self,
        *,
        run_id: str,
        claimant_id: str,
        signer: str,
        environ: Mapping[str, str],
        stdin_is_tty: bool,
        stdout_is_tty: bool,
    ) -> str:
        refusal = self.signature_refusal(environ, stdin_is_tty=stdin_is_tty, stdout_is_tty=stdout_is_tty)
        if refusal:
            raise LeaseHandoverError(refusal)
        verdict, _recorded = self.judge_holder(run_id)
        if verdict is not ProcessVerdict.UNKNOWN:
            raise LeaseHandoverError(f"原持有者进程的判定是 {verdict.value}，不是“无法判断”，不需要也不允许签署接受风险")
        try:
            lease = self._store.get_lease(run_id)
            epoch = self._store.get_grant_epoch(run_id)
            return self._store.record_reclaim_risk_acceptance(
                run_id=run_id,
                claimant_id=claimant_id,
                signer=signer,
                method="pm-sign-risk/interactive-tty",
                idempotency_key=f"sign-risk:{run_id}:{claimant_id}:{lease.owner_id}:{epoch}:{lease.version}",
            )
        except ContinuityStoreError as error:
            raise LeaseHandoverError(str(error)) from error
