"""A3 deterministic, authority-bounded orchestration for one Mission."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from auto_pm.core.mission_service import MissionService, MissionServiceError
from auto_pm.core.orchestration_policy import OrchestrationPolicy
from auto_pm.core.work_registry_service import WorkRegistryError, WorkRegistryService

from auto_pm.contracts.continuity import WorkItem, WorkKind, WorkState
from auto_pm.contracts.mission import Mission, MissionState
from auto_pm.contracts.orchestration import (
    OrchestrationAction,
    OrchestrationEscalationReason,
    OrchestrationFinding,
    OrchestrationOutcome,
    RepairAttempt,
)
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError


class MissionOrchestratorError(RuntimeError):
    """Raised when the A3 engine cannot safely route a typed finding."""


class MissionOrchestrator:
    """Route internal Work only inside the immutable Mission authority envelope."""

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._root = Path(workspace_root).resolve()
        self._now = now or (lambda: datetime.now(UTC))
        self._store = ContinuityStore(self._root)
        self._works = WorkRegistryService(
            self._root,
            store=self._store,
            now=lambda: self._instant().isoformat(),
        )
        self._missions = MissionService(self._root, now=self._now)

    def initialize(self, tool_version: str = "dev") -> None:
        """Initialize only the existing Continuity v2 store; no parallel state is created."""
        try:
            self._missions.initialize(tool_version)
            self._works.initialize(tool_version)
        except (MissionServiceError, WorkRegistryError) as error:
            raise MissionOrchestratorError(str(error)) from error

    def report_finding(self, finding: OrchestrationFinding) -> OrchestrationOutcome:
        """Classify and route one typed discovery or block the Mission with an explicit reason."""
        idempotency_key = self._finding_key(finding)
        existing = self._existing_outcome(finding.mission_id, idempotency_key)
        if existing is not None:
            return existing
        mission = self._mission(finding.mission_id)
        self._require_routable_mission(mission)
        now = self._instant()
        reason = OrchestrationPolicy.finding_escalation(mission, finding, now)
        if reason is not None:
            return self._escalate(
                mission=mission,
                correlation_id=finding.finding_id,
                parent_work_id=finding.parent_work_id,
                reason=reason,
                idempotency_key=idempotency_key,
            )

        parent = self._parent_or_escalate(mission, finding, idempotency_key)
        if isinstance(parent, OrchestrationOutcome):
            return parent
        try:
            self._works.assert_authorized_scope(
                subject_project_id=mission.subject_project_id,
                decision_id=mission.authority.decision_id,
                scope_paths=finding.scope_paths,
            )
            child = self._works.create_work(
                work_id=self._child_work_id(finding),
                subject_project_id=mission.subject_project_id,
                kind=OrchestrationPolicy.classify(finding),
                title=finding.title,
                owner="Cockpit",
                scope_paths=list(finding.scope_paths),
                source_fingerprint=finding.source_fingerprint,
                idempotency_key=f"orchestration:child:{finding.mission_id}:{finding.finding_id}",
            )
            child = self._works.authorize(
                child.work_id,
                mission.authority.decision_id,
                f"orchestration:authorize:{finding.mission_id}:{finding.finding_id}",
            )
            self._works.add_relation(
                child.work_id,
                parent.work_id,
                "parent",
                f"orchestration:parent:{finding.mission_id}:{finding.finding_id}",
            )
            self._works.add_relation(
                child.work_id,
                parent.work_id,
                "discovered_from",
                f"orchestration:discovery:{finding.mission_id}:{finding.finding_id}",
            )
        except WorkRegistryError:
            return self._escalate(
                mission=mission,
                correlation_id=finding.finding_id,
                parent_work_id=finding.parent_work_id,
                reason=OrchestrationEscalationReason.DECISION_SCOPE_EXIT,
                idempotency_key=idempotency_key,
            )

        blocks_parent = OrchestrationPolicy.blocks_parent(child.kind)
        if blocks_parent:
            try:
                self._works.add_relation(
                    child.work_id,
                    parent.work_id,
                    "blocks",
                    f"orchestration:blocks:{finding.mission_id}:{finding.finding_id}",
                )
                self._block_parent(parent, finding.finding_id)
                if mission.state is MissionState.ACCEPTANCE_PENDING:
                    mission = self._block_mission(
                        mission,
                        f"orchestration:acceptance-block:{finding.mission_id}:{finding.finding_id}",
                    )
            except WorkRegistryError as error:
                raise MissionOrchestratorError(str(error)) from error

        outcome = OrchestrationOutcome(
            mission_id=mission.mission_id,
            action=OrchestrationAction.BLOCKING if blocks_parent else OrchestrationAction.ROUTED,
            correlation_id=finding.finding_id,
            child_work_id=child.work_id,
            parent_work_id=parent.work_id,
            blocks_parent=blocks_parent,
            next_legal_action=(
                "CONTINUE_INTERNAL_REMEDIATION" if blocks_parent else "CONTINUE_MISSION"
            ),
            created_at=now,
        )
        return self._record(outcome, idempotency_key, now)

    def report_repair_attempt(self, attempt: RepairAttempt) -> OrchestrationOutcome:
        """Apply the explicit retry budget; the engine never performs adapter actions itself."""
        idempotency_key = f"orchestration:repair:{attempt.mission_id}:{attempt.attempt_id}"
        existing = self._existing_outcome(attempt.mission_id, idempotency_key)
        if existing is not None:
            return existing
        mission = self._mission(attempt.mission_id)
        self._require_routable_mission(mission)
        now = self._instant()
        if now < mission.authority.valid_from or now > mission.authority.expires_at:
            return self._escalate(
                mission=mission,
                correlation_id=attempt.attempt_id,
                child_work_id=attempt.child_work_id,
                reason=OrchestrationEscalationReason.AUTHORITY_EXPIRED,
                idempotency_key=idempotency_key,
            )
        try:
            child = self._works.get_work(attempt.child_work_id)
        except WorkRegistryError:
            return self._escalate(
                mission=mission,
                correlation_id=attempt.attempt_id,
                child_work_id=attempt.child_work_id,
                reason=OrchestrationEscalationReason.PARENT_NOT_ATTACHED,
                idempotency_key=idempotency_key,
            )
        if (
            child.subject_project_id != mission.subject_project_id
            or child.kind not in {WorkKind.BUG, WorkKind.TEST}
            or not self._is_attached_to_root(mission, child)
        ):
            return self._escalate(
                mission=mission,
                correlation_id=attempt.attempt_id,
                child_work_id=child.work_id,
                reason=OrchestrationEscalationReason.PARENT_NOT_ATTACHED,
                idempotency_key=idempotency_key,
            )

        prior = self._repair_outcomes(mission.mission_id, child.work_id)
        attempts_used = len(prior)
        elapsed_seconds_used = prior[-1].cumulative_elapsed_seconds if prior else 0
        start_reason = OrchestrationPolicy.repair_start_escalation(
            mission.authority,
            attempts_used=attempts_used,
            elapsed_seconds_used=elapsed_seconds_used,
            current_elapsed_seconds=attempt.elapsed_seconds,
        )
        if start_reason is not None:
            return self._escalate(
                mission=mission,
                correlation_id=attempt.attempt_id,
                child_work_id=child.work_id,
                reason=start_reason,
                idempotency_key=idempotency_key,
                action=OrchestrationAction.REPAIR_EXHAUSTED,
                attempt_count=attempts_used,
                cumulative_elapsed_seconds=elapsed_seconds_used,
            )

        attempt_count = attempts_used + 1
        cumulative_elapsed_seconds = elapsed_seconds_used + attempt.elapsed_seconds
        if attempt.succeeded:
            outcome = OrchestrationOutcome(
                mission_id=mission.mission_id,
                action=OrchestrationAction.REPAIR_COMPLETED,
                correlation_id=attempt.attempt_id,
                child_work_id=child.work_id,
                attempt_count=attempt_count,
                cumulative_elapsed_seconds=cumulative_elapsed_seconds,
                next_legal_action="RUN_VERIFICATION",
                created_at=now,
            )
            return self._record(outcome, idempotency_key, now)

        retry_reason = OrchestrationPolicy.retry_escalation(
            mission.authority, attempt_count=attempt_count
        )
        if retry_reason is not None:
            return self._escalate(
                mission=mission,
                correlation_id=attempt.attempt_id,
                child_work_id=child.work_id,
                reason=retry_reason,
                idempotency_key=idempotency_key,
                action=OrchestrationAction.REPAIR_EXHAUSTED,
                attempt_count=attempt_count,
                cumulative_elapsed_seconds=cumulative_elapsed_seconds,
            )
        outcome = OrchestrationOutcome(
            mission_id=mission.mission_id,
            action=OrchestrationAction.REPAIR_ALLOWED,
            correlation_id=attempt.attempt_id,
            child_work_id=child.work_id,
            attempt_count=attempt_count,
            cumulative_elapsed_seconds=cumulative_elapsed_seconds,
            next_legal_action="CONTINUE_INTERNAL_REMEDIATION",
            created_at=now,
        )
        return self._record(outcome, idempotency_key, now)

    def _parent_or_escalate(
        self,
        mission: Mission,
        finding: OrchestrationFinding,
        idempotency_key: str,
    ) -> WorkItem | OrchestrationOutcome:
        try:
            parent = cast(WorkItem, self._works.get_work(finding.parent_work_id))
        except WorkRegistryError:
            return self._escalate(
                mission=mission,
                correlation_id=finding.finding_id,
                parent_work_id=finding.parent_work_id,
                reason=OrchestrationEscalationReason.PARENT_NOT_ATTACHED,
                idempotency_key=idempotency_key,
            )
        if (
            parent.subject_project_id != mission.subject_project_id
            or not self._is_attached_to_root(mission, parent)
        ):
            return self._escalate(
                mission=mission,
                correlation_id=finding.finding_id,
                parent_work_id=parent.work_id,
                reason=OrchestrationEscalationReason.PARENT_NOT_ATTACHED,
                idempotency_key=idempotency_key,
            )
        return parent

    def _repair_outcomes(
        self, mission_id: str, child_work_id: str
    ) -> tuple[OrchestrationOutcome, ...]:
        try:
            outcomes = self._store.list_orchestration_outcomes(mission_id)
        except ContinuityStoreError as error:
            raise MissionOrchestratorError(str(error)) from error
        return tuple(
            outcome
            for outcome in outcomes
            if outcome.child_work_id == child_work_id
            and outcome.action
            in {
                OrchestrationAction.REPAIR_ALLOWED,
                OrchestrationAction.REPAIR_COMPLETED,
                OrchestrationAction.REPAIR_EXHAUSTED,
            }
        )

    def _block_parent(self, parent: WorkItem, finding_id: str) -> None:
        """Move a parent toward the restrictive BLOCKED state without bypassing lifecycle gates."""
        current = parent
        try:
            if current.state is WorkState.VERIFYING:
                current = self._works.transition(
                    current.work_id,
                    WorkState.IN_PROGRESS,
                    f"orchestration:reopen:{current.work_id}:{finding_id}:v{current.version}",
                )
            if current.state in {WorkState.READY, WorkState.IN_PROGRESS}:
                self._works.transition(
                    current.work_id,
                    WorkState.BLOCKED,
                    f"orchestration:block:{current.work_id}:{finding_id}:v{current.version}",
                )
            elif current.state is not WorkState.BLOCKED:
                raise MissionOrchestratorError(
                    f"发现阻塞项时父 Work 不可阻塞: {current.work_id}={current.state.value}"
                )
        except WorkRegistryError as error:
            raise MissionOrchestratorError(str(error)) from error

    def _block_mission(self, mission: Mission, idempotency_key: str) -> Mission:
        """A BLOCKED transition remains legal even if the authority just expired."""
        if mission.state is MissionState.BLOCKED:
            return mission
        try:
            return cast(
                Mission,
                self._missions.transition(
                    mission_id=mission.mission_id,
                    expected_version=mission.version,
                    new_state=MissionState.BLOCKED,
                    root_work_id=mission.root_work_id,
                    idempotency_key=idempotency_key,
                ),
            )
        except MissionServiceError as error:
            raise MissionOrchestratorError(str(error)) from error

    def _escalate(
        self,
        *,
        mission: Mission,
        correlation_id: str,
        reason: OrchestrationEscalationReason,
        idempotency_key: str,
        action: OrchestrationAction = OrchestrationAction.ESCALATED,
        child_work_id: str = "",
        parent_work_id: str = "",
        attempt_count: int = 0,
        cumulative_elapsed_seconds: int = 0,
    ) -> OrchestrationOutcome:
        blocked = self._block_mission(mission, f"{idempotency_key}:mission-block")
        now = self._instant()
        outcome = OrchestrationOutcome(
            mission_id=blocked.mission_id,
            action=action,
            correlation_id=correlation_id,
            child_work_id=child_work_id,
            parent_work_id=parent_work_id,
            user_attention_required=True,
            escalation_reason=reason,
            attempt_count=attempt_count,
            cumulative_elapsed_seconds=cumulative_elapsed_seconds,
            next_legal_action="AWAIT_USER_ESCALATION",
            created_at=now,
        )
        return self._record(outcome, idempotency_key, now)

    def _record(
        self,
        outcome: OrchestrationOutcome,
        idempotency_key: str,
        now: datetime,
    ) -> OrchestrationOutcome:
        try:
            return self._store.record_orchestration_outcome(
                outcome, idempotency_key, now.isoformat()
            )
        except ContinuityStoreError as error:
            raise MissionOrchestratorError(str(error)) from error

    def _existing_outcome(
        self, mission_id: str, idempotency_key: str
    ) -> OrchestrationOutcome | None:
        try:
            return self._store.get_orchestration_outcome(mission_id, idempotency_key)
        except ContinuityStoreError as error:
            raise MissionOrchestratorError(str(error)) from error

    def _mission(self, mission_id: str) -> Mission:
        try:
            return cast(Mission, self._missions.get(mission_id))
        except MissionServiceError as error:
            raise MissionOrchestratorError(str(error)) from error

    @staticmethod
    def _require_routable_mission(mission: Mission) -> None:
        if mission.state not in {MissionState.ACTIVE, MissionState.ACCEPTANCE_PENDING}:
            raise MissionOrchestratorError("只有 ACTIVE 或 ACCEPTANCE_PENDING Mission 可以自动编排")
        if not mission.root_work_id:
            raise MissionOrchestratorError("自动编排 Mission 必须绑定 root Work")

    def _is_attached_to_root(self, mission: Mission, work: WorkItem) -> bool:
        if work.work_id == mission.root_work_id:
            return True
        if not mission.root_work_id:
            return False
        try:
            return cast(bool, self._works.is_reachable(work.work_id, mission.root_work_id))
        except WorkRegistryError:
            return False

    def _instant(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            raise MissionOrchestratorError("Mission orchestrator now 必须是带时区时间")
        return value.astimezone(UTC)

    @staticmethod
    def _finding_key(finding: OrchestrationFinding) -> str:
        return f"orchestration:finding:{finding.mission_id}:{finding.finding_id}"

    @staticmethod
    def _child_work_id(finding: OrchestrationFinding) -> str:
        return f"WORK-A3-{finding.finding_id.removeprefix('FND-')}"
