"""Park, unpark and switch Missions for the PM commands (TD-071 card 2).

"在干 / 等你 / 搁着 / 已关": one project may have several open cards but one key.  This service only
sequences the store's two atomic primitives (``park_mission`` / ``unpark_mission``) and fills in what
the store must not do itself: the worktree snapshot, the holder's token from the local wallet, the new
holder's token and the "behind main" reminder.

Who may do what (design 7.2, user decision 5b):

- ``park`` with the user's words (``approval_evidence_ref``) puts a card into "搁着" (PARKED).
- ``park`` without them is what an agent may do on its own: stop the card it holds into "等你" (BLOCKED),
  with the same checkpoint and fenced lease.
- ``unpark`` and ``switch`` always need the user's words; an agent never picks the next card itself.
"""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from auto_pm.application.core.approval_proof_service import ApprovalProofError, ApprovalProofService
from auto_pm.application.core.lease_handover_service import LeaseHandoverError, LeaseHandoverService
from auto_pm.contracts.continuity import RunItem, RunState
from auto_pm.contracts.mission import (
    Mission,
    MissionBoard,
    MissionPark,
    MissionState,
    user_evidence_problem,
)
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError
from auto_pm.infrastructure.control_root_guard import (
    ControlRootGuardError,
    authority_path_parts,
    clean_git_environment,
    governed_worktree_snapshot,
)

_LIVE_RUN_STATES = frozenset({RunState.READY, RunState.RUNNING, RunState.BLOCKED, RunState.PENDING, RunState.VERIFYING})
NO_APPROVAL_HINT = "请让用户说一句先干哪张（--approval-evidence-ref 填用户原话所在的位置）"


def _require_user_words(evidence_ref: str, *, optional: bool = False) -> None:
    """Refuse early, before any snapshot or write, words that are not the user's own (design line 214)."""

    if optional and not evidence_ref.strip():
        return
    if problem := user_evidence_problem(evidence_ref.strip()):
        raise MissionSwitchError(problem + "；" + NO_APPROVAL_HINT)


class MissionSwitchError(RuntimeError):
    """Raised when a park, unpark or switch cannot proceed; the message says what was (not) done."""


@dataclass(frozen=True)
class ParkOutcome:
    mission: Mission
    park: MissionPark
    checkpoint_id: str


@dataclass(frozen=True)
class UnparkOutcome:
    """The card is back in hand; the new token stays in the wallet."""

    mission: Mission
    park: MissionPark
    checkpoint_summary: str
    owner_id: str
    epoch: int
    expires_at: str
    wallet_path: str
    holder_process_recorded: bool
    behind_main: int | None
    # Cards whose overlapping paths the user released together with this one (decision 3): sync first.
    overlaps: tuple[tuple[str, tuple[str, ...]], ...] = ()


@dataclass(frozen=True)
class SwitchOutcome:
    parked: ParkOutcome | None
    started: UnparkOutcome | None
    recommended_mission_id: str
    next_command: str
    note: str


class MissionSwitchService:
    """The PM-level park / unpark / switch sequence over the Continuity Store."""

    def __init__(
        self,
        control_root: str | Path,
        *,
        store: ContinuityStore | None = None,
        now: Callable[[], datetime] | None = None,
        handover: LeaseHandoverService | None = None,
    ) -> None:
        self._root = Path(control_root).resolve()
        self._store = store or ContinuityStore(self._root)
        self._now = now or (lambda: datetime.now(UTC))
        self._handover = handover or LeaseHandoverService(self._root, store=self._store, now=self._now)

    # ---------------------------------------------------------------- read
    def board(self, project_id: str) -> MissionBoard:
        try:
            return self._store.list_missions_by_board(project_id)
        except ContinuityStoreError as error:
            raise MissionSwitchError(str(error)) from error

    # ---------------------------------------------------------------- park
    def park(
        self,
        *,
        mission_id: str,
        reason: str,
        summary: str,
        approval_evidence_ref: str = "",
        lease_token: str | None = None,
        approval_pin: str = "",
    ) -> ParkOutcome:
        """Put the card down with a checkpoint: into "搁着" with the user's words, else into "等你".

        With a committed approver PIN (gap 9) the user's words are the PIN: an agent alone can only put a card into "等你".
        """

        if approval_evidence_ref.strip() or approval_pin:
            approval_evidence_ref = self._user_evidence(approval_pin, approval_evidence_ref, "park", mission_id)
        return self._park(
            mission_id=mission_id,
            reason=reason,
            summary=summary,
            approval_evidence_ref=approval_evidence_ref,
            lease_token=lease_token,
        )

    def _user_evidence(self, approval_pin: str, approval_evidence_ref: str, purpose: str, subject: str) -> str:
        """The user's words as recorded: the caller's reference under the old check, the PIN reference once committed."""

        try:
            return ApprovalProofService(self._root).resolve(
                pin=approval_pin, approver="", evidence_ref=approval_evidence_ref, purpose=purpose, subject=subject
            )[1]
        except ApprovalProofError as error:
            raise MissionSwitchError(str(error)) from error

    def _park(
        self, *, mission_id: str, reason: str, summary: str, approval_evidence_ref: str, lease_token: str | None
    ) -> ParkOutcome:
        if not reason.strip() or not summary.strip():
            raise MissionSwitchError("搁着原因和断点摘要（干到哪了、下一步做什么）都不能为空")
        _require_user_words(approval_evidence_ref, optional=True)
        try:
            mission = self._store.get_mission(mission_id)
            run = self._live_run(mission)
            lease = self._store.get_lease(run.run_id)
        except ContinuityStoreError as error:
            raise MissionSwitchError(str(error)) from error
        try:
            token = lease_token if lease_token is not None else self._handover.token_for(run.run_id, lease.owner_id)
        except LeaseHandoverError as error:
            raise MissionSwitchError(str(error)) from error
        git_head, dirty = self._snapshot(run)
        target = MissionState.PARKED if approval_evidence_ref.strip() else MissionState.BLOCKED
        digest = hashlib.sha256(
            f"{mission_id}\x00{mission.version}\x00{lease.version}\x00{target.value}".encode()
        ).hexdigest()[:16].upper()
        try:
            park = self._store.park_mission(
                mission_id=mission_id,
                expected_mission_version=mission.version,
                park_id=f"PARK-{digest}",
                checkpoint_id=f"CKPT-PK-{digest}",
                owner_id=lease.owner_id,
                lease_token=token,
                reason=reason.strip(),
                summary=summary.strip(),
                git_head=git_head,
                dirty_paths=dirty,
                idempotency_key=f"pm-park:{digest}",
                target_state=target,
                approval_evidence_ref=approval_evidence_ref,
            )
            return ParkOutcome(
                mission=self._store.get_mission(mission_id), park=park, checkpoint_id=park.checkpoint_id
            )
        except ContinuityStoreError as error:
            raise MissionSwitchError(str(error)) from error

    # ---------------------------------------------------------------- unpark
    def unpark(
        self,
        *,
        mission_id: str,
        as_owner: str,
        approval_evidence_ref: str,
        lease_seconds: int = 900,
        holder_pid: int | None = None,
        approval_pin: str = "",
    ) -> UnparkOutcome:
        """Pick a card back up for ``as_owner``; refused without the user's words (the PIN once committed) or when the worktree moved."""

        approval_evidence_ref = self._user_evidence(approval_pin, approval_evidence_ref, "unpark", mission_id)
        return self._unpark(
            mission_id=mission_id,
            as_owner=as_owner,
            approval_evidence_ref=approval_evidence_ref,
            lease_seconds=lease_seconds,
            holder_pid=holder_pid,
        )

    def _unpark(
        self,
        *,
        mission_id: str,
        as_owner: str,
        approval_evidence_ref: str,
        lease_seconds: int,
        holder_pid: int | None,
    ) -> UnparkOutcome:
        if not approval_evidence_ref.strip():
            raise MissionSwitchError("拿回哪张卡只听用户的；" + NO_APPROVAL_HINT)
        _require_user_words(approval_evidence_ref)
        if not as_owner.strip():
            raise MissionSwitchError("--as 必须写明接手的 agent 身份")
        try:
            mission = self._store.get_mission(mission_id)
            park = self._store.get_open_park(mission_id)
            if park is None:
                raise MissionSwitchError(f"{mission_id} 没有搁着（当前 {mission.state.value}），不用拿回")
            run = self._store.get_run(park.run_id)
            checkpoint = self._store.get_checkpoint(park.checkpoint_id)
        except ContinuityStoreError as error:
            raise MissionSwitchError(str(error)) from error
        git_head, dirty = self._snapshot(run)
        try:
            token = self._handover.reusable_token(run.run_id, as_owner)
        except LeaseHandoverError as error:
            raise MissionSwitchError(str(error)) from error
        digest = hashlib.sha256(f"{mission_id}\x00{park.park_id}\x00{as_owner}".encode()).hexdigest()[:16].upper()
        try:
            closed, lease = self._store.unpark_mission(
                mission_id=mission_id,
                expected_mission_version=mission.version,
                new_owner_id=as_owner,
                new_token=token,
                lease_seconds=lease_seconds,
                observed_git_head=git_head,
                observed_dirty_paths=dirty,
                approval_evidence_ref=approval_evidence_ref.strip(),
                idempotency_key=f"pm-unpark:{digest}",
            )
        except ContinuityStoreError as error:
            raise MissionSwitchError(str(error)) from error
        try:
            wallet = self._handover.remember(run.run_id, as_owner, token)
            recorded = self._handover.record_holder(
                run.run_id, as_owner, token, holder_pid, f"pm-unpark:{digest}:holder"
            )
            epoch = self._store.get_grant_epoch(run.run_id)
            back = self._store.get_mission(mission_id)
            overlaps = self._store.list_mission_overlaps(mission_id)
        except (LeaseHandoverError, ContinuityStoreError) as error:
            raise MissionSwitchError(f"卡已拿回，但收尾失败: {error}") from error
        return UnparkOutcome(
            mission=back,
            park=closed,
            checkpoint_summary=checkpoint.summary,
            owner_id=lease.owner_id,
            epoch=epoch,
            expires_at=lease.expires_at,
            wallet_path=wallet,
            holder_process_recorded=recorded,
            behind_main=self._behind_main(run),
            overlaps=overlaps,
        )

    # ---------------------------------------------------------------- switch
    def switch(
        self,
        *,
        project_id: str,
        to_mission_id: str | None,
        reason: str,
        summary: str,
        as_owner: str,
        approval_evidence_ref: str,
        lease_seconds: int = 900,
        holder_pid: int | None = None,
        approval_pin: str = "",
    ) -> SwitchOutcome:
        """Park the card in hand and pick ``to_mission_id`` up; without ``--to`` only recommend.

        Two separate transactions: if the second fails the first card stays parked (a safe state) and
        the message says so.  Re-running the same command continues with the step that is missing.
        """

        board = self.board(project_id)
        latest_parked = board.parked[0].mission.mission_id if board.parked else ""
        if not to_mission_id:
            note = (
                f"建议拿回最后放下的 {latest_parked}（{board.parked[0].checkpoint_summary}）；请用户说一句再执行"
                if latest_parked
                else "没有搁着的卡"
            )
            return SwitchOutcome(None, None, latest_parked, "", note)
        # One PIN for the whole switch: it covers parking the card in hand and picking the target up.
        approval_evidence_ref = self._user_evidence(approval_pin, approval_evidence_ref, "switch", to_mission_id)
        if not approval_evidence_ref.strip():
            raise MissionSwitchError("切换只听用户的；" + NO_APPROVAL_HINT)
        _require_user_words(approval_evidence_ref)
        try:
            target = self._store.get_mission(to_mission_id)
            target_park = self._store.get_open_park(to_mission_id)
        except ContinuityStoreError as error:
            raise MissionSwitchError(str(error)) from error
        if target.subject_project_id != project_id:
            raise MissionSwitchError(f"{to_mission_id} 不属于项目 {project_id}")
        if target.state is MissionState.ACTIVE:
            return SwitchOutcome(None, None, "", "", f"{to_mission_id} 已经在干，不用切换")
        if target_park is None and target.state is not MissionState.AWAITING_APPROVAL:
            raise MissionSwitchError(
                f"{to_mission_id} 当前是 {target.state.value}，只能切到“搁着”或“已批未开工”的卡"
            )
        if target_park is not None and not as_owner.strip():
            # Checked before the first write: an input error must not leave the card in hand parked.
            raise MissionSwitchError("--as 必须写明接手的 agent 身份")
        parked: ParkOutcome | None = None
        if board.active:
            current = board.active[0]
            parked = self._park(
                mission_id=current.mission_id,
                reason=reason,
                summary=summary,
                approval_evidence_ref=approval_evidence_ref,
                lease_token=None,
            )
        prefix = f"{parked.mission.mission_id} 已搁着，" if parked else ""
        if target_park is None:
            return SwitchOutcome(
                parked,
                None,
                "",
                f"main.py pm confirm-start --mission-id {to_mission_id}",
                prefix + f"{to_mission_id} 还没开工；用 next_command 开工",
            )
        try:
            started = self._unpark(
                mission_id=to_mission_id,
                as_owner=as_owner,
                approval_evidence_ref=approval_evidence_ref,
                lease_seconds=lease_seconds,
                holder_pid=holder_pid,
            )
        except MissionSwitchError as error:
            raise MissionSwitchError(prefix + f"{to_mission_id} 没起来，原因是：{error}") from error
        return SwitchOutcome(parked, started, "", "", prefix + f"{to_mission_id} 已拿回开干")

    # ---------------------------------------------------------------- helpers
    def _live_run(self, mission: Mission) -> RunItem:
        if not mission.root_work_id:
            raise MissionSwitchError(f"{mission.mission_id} 还没绑定 Work，没有可搁着的执行")
        runs = [run for run in self._store.list_runs(mission.root_work_id) if run.state in _LIVE_RUN_STATES]
        if len(runs) != 1:
            raise MissionSwitchError(f"{mission.mission_id} 必须恰有 1 个未终结 Run 才能搁着（实际 {len(runs)} 个）")
        return runs[0]

    def _snapshot(self, run: RunItem) -> tuple[str, list[str]]:
        try:
            _worktree, git_head, dirty = governed_worktree_snapshot(
                self._root, run.worktree_path, allow_external_linked=True
            )
        except ControlRootGuardError as error:
            raise MissionSwitchError(str(error)) from error
        roots = [authority_path_parts(path) for path in (*run.owned_paths, *run.declared_dirty_paths)]
        in_scope = [path for path in dirty if any(authority_path_parts(path)[: len(root)] == root for root in roots)]
        return git_head, sorted(set(in_scope))

    @staticmethod
    def _behind_main(run: RunItem) -> int | None:
        """How many commits ``main`` is ahead of the card's worktree; only a reminder, never a rebase (decision 4)."""

        try:
            result = subprocess.run(
                ["git", "-C", run.worktree_path, "rev-list", "--count", "HEAD..main"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=clean_git_environment(),
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        text = result.stdout.strip()
        return int(text) if result.returncode == 0 and text.isdigit() else None
