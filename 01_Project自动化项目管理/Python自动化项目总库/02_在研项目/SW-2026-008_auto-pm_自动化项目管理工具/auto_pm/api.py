"""Thin Cockpit SDK: one importable entry that drives the PM Facade behind a runtime-identity guard."""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, model_validator

from auto_pm.application.core.pm_closure_service import PmClosureError
from auto_pm.application.core.pm_cockpit_service import PmCockpitError, PmCockpitService
from auto_pm.application.core.pm_facade_service import PmFacadeError, PmFacadeService
from auto_pm.application.core.workspace_context_service import (
    WorkspaceContextError,
    WorkspaceContextService,
)
from auto_pm.application.core.worktree_policy_service import (
    WorktreePolicyError,
    WorktreePolicyService,
)
from auto_pm.change.change_service import ChangeService
from auto_pm.change.constants import TransitionGuardError
from auto_pm.contracts.continuity_resume import ContinuityResume, validate_query_resume
from auto_pm.contracts.decision_package import DecisionPackageDTO
from auto_pm.contracts.execution_adapter import ExecutionAdapterKind
from auto_pm.contracts.mission import MissionState
from auto_pm.contracts.pm_cockpit import PmCockpitCompletion
from auto_pm.contracts.pm_facade import (
    PlanningExecutionGrant,
    PlanningScopeCard,
    PmConfirmationCard,
    PmIntent,
    PmRunOutcome,
)
from auto_pm.domain.change.decision_service import DecisionError, DecisionService
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError

log = logging.getLogger(__name__)

_LEASE_ENVIRONMENT = "AUTO_PM_EXECUTION_LEASE_TOKEN"
_APPROVED_STATES = frozenset(
    {"approved", "implementing", "pending_acceptance", "accepting", "completed"}
)
_REMAINING_APPROVAL_STEPS = {
    "draft": ("submitted", "under_review", "approved"),
    "submitted": ("under_review", "approved"),
    "under_review": ("approved",),
}
_ALREADY_VERIFIED = "该需求已执行并验证，等待验收；请直接确认验收，不要重复执行。"


class CockpitApiError(RuntimeError):
    """The only exception the SDK raises; the original error is chained."""


class CockpitIdentity(BaseModel):
    """Secret-free runtime identity of the workspace this client would write to."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str
    workspace_root: str
    configured_release_id: str
    effective_release_id: str
    runtime_load_path: str
    runtime_fallback_reason: str
    conflicts: tuple[str, ...]
    writable: bool

    @model_validator(mode="after")
    def _writable_means_no_conflicts(self) -> CockpitIdentity:
        if self.writable != (not self.conflicts):
            raise ValueError("writable must equal 'no runtime identity conflicts'")
        return self


class CockpitClient:
    """Drive plan, approval, execution, acceptance and closure through one guarded entry."""

    def __init__(
        self,
        workspace_root: str | Path,
        project_id: str,
        *,
        facade: PmFacadeService | None = None,
        package_file_provider: Callable[[], str | Path | None] | None = None,
    ) -> None:
        self._root = Path(workspace_root).resolve()
        self._project_id = project_id
        self._package_file_provider = package_file_provider
        self._identity = self._resolve_identity()
        try:
            self._facade = facade or PmFacadeService(self._root)
        except (PmFacadeError, ValueError) as error:
            raise CockpitApiError(str(error)) from error
        self._leases: dict[str, str] = {}

    @property
    def identity(self) -> CockpitIdentity:
        """The most recently resolved identity; reading it never writes anything."""

        return self._identity

    def orient(self, *, work_id: str = "", run_id: str = "", requested_action: str = "") -> ContinuityResume:
        """Read-only versioned query shared with ``pm resume`` and ``pm orient``; a capability is not an authorization."""

        try:
            answer = self._facade.orient(
                project_id=self._project_id,
                invocation_path=str(self._root),
                work_id=work_id,
                run_id=run_id,
                requested_action=requested_action,
            )
            return validate_query_resume(answer, require_query=True)
        except (PmFacadeError, ValueError) as error:
            raise CockpitApiError(str(error)) from error

    def mission_state(self, mission_id: str) -> MissionState:
        """Read one Mission's state without passing the write guard."""

        try:
            return ContinuityStore(self._root).get_mission(mission_id).state
        except (ContinuityStoreError, ValueError) as error:
            raise CockpitApiError(str(error)) from error

    def plan(
        self,
        *,
        request_id: str,
        objective: str,
        acceptance: Sequence[str],
        scope_paths: Sequence[str],
        risks: Sequence[str],
        non_goals: Sequence[str],
        adapter: ExecutionAdapterKind,
        approved_model: str,
        declared_dirty_paths: Sequence[str] = (),
    ) -> PlanningScopeCard:
        """Create the non-executable scope card that a human must still approve."""

        self._require_writable()
        try:
            return self._facade.create_planning_scope_card(
                PmIntent(
                    subject_project_id=self._project_id,
                    request_id=request_id,
                    objective=objective,
                    acceptance_criteria=tuple(acceptance),
                ),
                scope_paths=tuple(scope_paths),
                risks=tuple(risks),
                non_goals=tuple(non_goals),
                execution_grant=PlanningExecutionGrant(
                    adapter=adapter,
                    approved_model=approved_model,
                    declared_dirty_paths=tuple(declared_dirty_paths),
                ),
            )
        except (PmFacadeError, ValueError) as error:
            raise CockpitApiError(str(error)) from error

    def approve_plan(
        self,
        card: PlanningScopeCard,
        *,
        approver: str,
        approval_evidence_ref: str,
    ) -> DecisionPackageDTO:
        """Bind the caller's human approval; the SDK never supplies an approver or evidence."""

        self._require_writable()
        try:
            # Same validation the Facade applies first: a refused approval must write nothing.
            DecisionService.validate_planning_approval(
                approver, card.plan_hash, approval_evidence_ref
            )
            self._approve_change(card, approver)
            return self._facade.approve_planning_scope_card(
                card,
                expected_plan_hash=card.plan_hash,
                approver=approver,
                approval_evidence_ref=approval_evidence_ref,
            )
        except (PmFacadeError, DecisionError, TransitionGuardError, ValueError) as error:
            raise CockpitApiError(str(error)) from error

    def run(self, card: PlanningScopeCard) -> PmRunOutcome:
        """Run the approved card in isolation and verify it up to the acceptance gate."""

        self._require_writable()
        try:
            token = self._leases.get(card.plan_hash)
            if token is None:
                mission = self._facade.materialize_planning_mission(card)
                state = ContinuityStore(self._root).get_mission(mission.mission_id).state
                if state is MissionState.ACCEPTANCE_PENDING:
                    raise CockpitApiError(_ALREADY_VERIFIED)
                token = self._leases.setdefault(card.plan_hash, secrets.token_urlsafe(32))
            return self._facade.run_approved_planning(
                card,
                expected_plan_hash=card.plan_hash,
                lease_token=token,
                lease_token_environment=_LEASE_ENVIRONMENT,
            )
        except (PmFacadeError, ContinuityStoreError, ValueError) as error:
            raise CockpitApiError(str(error)) from error

    def accept(self, mission_id: str) -> PmConfirmationCard:
        """Record the final user acceptance through the Facade's evidence gate."""

        self._require_writable()
        try:
            return self._facade.accept(mission_id)
        except (PmFacadeError, ValueError) as error:
            raise CockpitApiError(str(error)) from error

    def close(self, mission_id: str) -> PmCockpitCompletion:
        """Close an accepted Mission through the same closure the cockpit uses."""

        self._require_writable()
        try:
            return PmCockpitService(self._root).close_accepted(mission_id)
        except (PmCockpitError, PmClosureError, ContinuityStoreError, ValueError) as error:
            raise CockpitApiError(str(error)) from error

    def _resolve_identity(self) -> CockpitIdentity:
        try:
            context = WorkspaceContextService(
                str(self._root), package_file_provider=self._package_file_provider
            ).resolve(project_id=self._project_id, start_path=self._root)
        except WorkspaceContextError as error:
            raise CockpitApiError(str(error)) from error
        return CockpitIdentity(
            project_id=context.subject_project_id,
            workspace_root=context.workspace_root,
            configured_release_id=context.configured_release_id,
            effective_release_id=context.effective_release_id,
            runtime_load_path=context.runtime_load_path,
            runtime_fallback_reason=context.runtime_fallback_reason,
            conflicts=tuple(context.conflicts),
            writable=not context.conflicts,
        )

    def _require_writable(self) -> None:
        """First step of every write: re-resolve the identity and refuse on any conflict."""

        self._identity = self._resolve_identity()
        if self._identity.conflicts:
            raise CockpitApiError(
                "运行身份未通过校验，SDK 已拒绝写入：" + "；".join(self._identity.conflicts)
            )
        try:
            WorktreePolicyService(self._root).require_control_root()
        except WorktreePolicyError as error:
            raise CockpitApiError(str(error)) from error

    def _approve_change(self, card: PlanningScopeCard, approver: str) -> None:
        changes = ChangeService(str(self._root))
        change = changes.get_change_request(card.change_id, project_id=card.subject_project_id)
        if change is None:
            raise CockpitApiError("PlanningScopeCard 绑定的 CHG 不存在")
        for state in _REMAINING_APPROVAL_STEPS.get(change.status, ()):
            change = changes.transition_status(
                card.change_id,
                state,
                approver=approver,
                comment=f"user approved planning scope {card.plan_hash}",
                project_id=card.subject_project_id,
            )
        if change.status not in _APPROVED_STATES:
            raise CockpitApiError(f"PlanningScopeCard 绑定的 CHG 不可批准: {change.status}")


__all__ = ["CockpitApiError", "CockpitClient", "CockpitIdentity"]
