"""User-facing PM workflow built solely on Continuity Store truth."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
from pathlib import Path
from typing import Any, cast

from auto_pm.change.change_service import ChangeService
from auto_pm.change.constants import (
    ChangeRequest,
    SpecViolationError,
    validate_business_nature,
    validate_domain,
    validate_impact_scope,
    validate_urgency,
)
from auto_pm.core.continuity_execution_service import (
    ContinuityExecutionError,
    ContinuityExecutionService,
)
from auto_pm.core.continuity_query_service import ContinuityQueryError, ContinuityQueryService
from auto_pm.core.execution_adapter_service import (
    ExecutionDispatchError,
    ExecutionDispatchResult,
    ExecutionDispatchService,
)
from auto_pm.core.local_execution_orchestrator import (
    LocalExecutionOrchestrator,
    LocalExecutionOrchestratorError,
)
from auto_pm.core.mission_service import MissionService, MissionServiceError
from auto_pm.core.work_registry_service import WorkRegistryError, WorkRegistryService

from auto_pm.application.core.evidence_collection_service import (
    EvidenceCollection,
    EvidenceCollectionError,
    EvidenceCollectionService,
)
from auto_pm.contracts.continuity import RunState, WorkItem, WorkState
from auto_pm.contracts.continuity_resume import ContinuityResume, validate_query_resume
from auto_pm.contracts.decision_package import DecisionPackageDTO
from auto_pm.contracts.execution_adapter import ForegroundExecutionReceipt
from auto_pm.contracts.intake import IntakeClassification
from auto_pm.contracts.mission import Mission, MissionState
from auto_pm.contracts.pm_facade import (
    PlanningApprovalResult,
    PlanningDraft,
    PlanningDraftOverview,
    PlanningExecutionGrant,
    PlanningScopeCard,
    PmConfirmationCard,
    PmConfirmationKind,
    PmIntent,
    PmRunOutcome,
    SubmittedPlanningScopeCard,
)
from auto_pm.domain.change.decision_service import (
    DecisionError,
    DecisionService,
    DecisionValidationError,
)
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError
from auto_pm.infrastructure.intake_store import IntakeStore

log = logging.getLogger(__name__)

_VERIFIED_MESSAGE = "已执行并通过质量验证，等待您的最终验收。"
_NOT_VERIFIED_MESSAGE = "质量验证未通过，已保留现场；未进入验收。"
_NOT_FINISHED_MESSAGE = "执行未完成，未进行质量验证；已保留现场。"
_PLANNING_CHANGE_APPROVAL_STEPS = {
    "draft": ("submitted", "under_review", "approved"),
    "submitted": ("under_review", "approved"),
    "under_review": ("approved",),
}
_PLANNING_CHANGE_APPROVED_STATES = frozenset(
    {"approved", "implementing", "pending_acceptance", "accepting", "completed"}
)


class PmFacadeError(RuntimeError):
    """Raised when a user-facing PM action is not legally available."""


class PmFacadeService:
    """Stateless orchestrating facade for a single approved Mission."""

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        execution_root: str | Path | None = None,
        store: ContinuityStore | None = None,
        change_service: ChangeService | None = None,
        decision_service: DecisionService | None = None,
        execution_service: ExecutionDispatchService | None = None,
        local_orchestrator: LocalExecutionOrchestrator | None = None,
        planning_lease_seconds: int = 900,
    ) -> None:
        if type(planning_lease_seconds) is not int or not 60 <= planning_lease_seconds <= 3600:
            raise PmFacadeError("planning_lease_seconds 必须在 60 到 3600 之间")
        self._planning_lease_seconds = planning_lease_seconds
        self._workspace_root = Path(workspace_root).resolve()
        self._execution_root = Path(execution_root or workspace_root).resolve()
        self._store = store or ContinuityStore(self._workspace_root)
        self._missions = MissionService(self._workspace_root, store=self._store)
        self._works = WorkRegistryService(self._workspace_root, store=self._store)
        self._changes = change_service or ChangeService(str(self._workspace_root))
        self._decisions = decision_service or DecisionService(self._workspace_root)
        self._execution = execution_service or ExecutionDispatchService(
            self._workspace_root,
            execution_root=self._execution_root,
            store=self._store,
        )
        self._local_orchestrator = local_orchestrator or LocalExecutionOrchestrator(
            self._workspace_root,
            execution_root=self._execution_root,
            store=self._store,
        )

    def create_planning_draft(self, intent: PmIntent) -> PlanningDraft:
        """Persist a pre-authorization draft without creating executable state."""

        try:
            return self._store.create_planning_draft(PlanningDraft.from_intent(intent))
        except ContinuityStoreError as error:
            raise PmFacadeError(str(error)) from error

    def _planning_classification(
        self,
        request_id: str,
        project_id: str,
        classification: IntakeClassification | None,
        intake_item_id: str,
    ) -> tuple[IntakeClassification | None, str]:
        """Resolve a filing without consuming anything; unclassified legacy requests stay legal."""

        intake = IntakeStore(self._store.workspace_root, self._store.db_path)
        try:
            filing, item_id = intake.resolve_planning_classification(
                request_id, project_id, classification, intake_item_id
            )
            if filing is not None:
                validate_domain(filing.domain)
                validate_business_nature(filing.business_nature)
                validate_impact_scope(list(filing.impact_scope))
                validate_urgency(filing.urgency)
            return filing, item_id
        except (ContinuityStoreError, SpecViolationError) as error:
            raise PmFacadeError(str(error)) from error

    def create_planning_draft_change(
        self,
        intent: PmIntent,
        *,
        classification: IntakeClassification | None = None,
        intake_item_id: str = "",
    ) -> str:
        """Create or replay the one pre-authorization CHG for a PlanningDraft.

        A classified request is filed under its own domain, nature, scope and urgency. Only a request
        that nothing classified keeps the legacy filing (SCPT, DEF, MODULE, normal).
        """

        filing, intake_item_id = self._planning_classification(
            intent.request_id, intent.subject_project_id, classification, intake_item_id
        )
        draft = self.create_planning_draft(intent)
        domain = "SCPT" if filing is None else filing.domain
        classified_refs = (
            ""
            if filing is None
            else f"; intake_kind={filing.kind.value}"
            + (f"; change_action={filing.change_action.value}" if filing.change_action else "")
            + (f"; intake_item={intake_item_id}" if intake_item_id else "")
        )
        try:
            candidate_change_id = self._changes.next_change_number(draft.subject_project_id, domain)
            change_id = self._store.reserve_planning_draft_change(
                draft.request_id, candidate_change_id
            )
            change = self._changes.create_change_request(
                project_id=draft.subject_project_id,
                domain=domain,
                business_nature="DEF" if filing is None else filing.business_nature,
                impact_scope=["MODULE"] if filing is None else list(filing.impact_scope),
                applicant="PM Facade",
                background=draft.objective,
                necessity="PlanningDraft 需生成可审查的真实 CHG 草稿。",
                references=f"PlanningDraft request_id={draft.request_id}; "
                f"input_fingerprint={draft.input_fingerprint}{classified_refs}",
                urgency="normal" if filing is None else filing.urgency,
                change_number=change_id,
            )
        except (ContinuityStoreError, ValueError) as error:
            raise PmFacadeError(str(error)) from error
        self._validate_planning_change(draft, change_id, change, filing, intake_item_id)
        return change_id

    @staticmethod
    def _validate_planning_change(
        draft: PlanningDraft,
        change_id: str,
        change: ChangeRequest,
        filing: IntakeClassification | None,
        intake_item_id: str,
    ) -> None:
        """Prove a reused CHG still has the exact request identity and legal filing."""
        domain = "SCPT" if filing is None else filing.domain
        replayable_states = {
            "draft",
            "submitted",
            "under_review",
            "approved",
            "conditionally_approved",
            "implementing",
            "pending_acceptance",
            "accepting",
            "completed",
        }
        if change.change_number != change_id or change.status not in replayable_states:
            raise PmFacadeError("PlanningDraft 绑定的 CHG 已被拒绝、关闭或归档，不能恢复范围卡")
        expected_refs = {
            "PlanningDraft request_id": draft.request_id,
            "input_fingerprint": draft.input_fingerprint,
        }
        if filing is not None:
            expected_refs["intake_kind"] = filing.kind.value
            if filing.change_action is not None:
                expected_refs["change_action"] = filing.change_action.value
            if intake_item_id:
                expected_refs["intake_item"] = intake_item_id
        actual_refs: dict[str, str] = {}
        for entry in change.references.split(";"):
            key, separator, value = entry.strip().partition("=")
            if separator:
                if key in actual_refs:
                    raise PmFacadeError("PlanningDraft 的 CHG 引用包含重复身份字段")
                actual_refs[key] = value
        legacy_refs = {
            "PlanningDraft request_id": draft.request_id,
            "input_fingerprint": draft.input_fingerprint,
        }
        # Legacy SDK cards have no intake fields. Permit adding an explicit filing only when
        # both immutable request identity and all existing CHG filing fields already agree.
        legacy_filing = (
            filing is not None
            and not intake_item_id
            and actual_refs == legacy_refs
            and domain == "SCPT"
            and filing.business_nature == "DEF"
            and filing.impact_scope == ("MODULE",)
            and filing.urgency == "normal"
        )
        if (
            change.project_id != draft.subject_project_id
            or change.domain != domain
            or change.business_nature != ("DEF" if filing is None else filing.business_nature)
            or change.impact_scope != (["MODULE"] if filing is None else list(filing.impact_scope))
            or change.urgency != ("normal" if filing is None else filing.urgency)
            or (actual_refs != expected_refs and not legacy_filing)
        ):
            raise PmFacadeError("PlanningDraft 复用的 CHG 分类或请求身份不一致")

    def bind_planning_draft_specs(self, intent: PmIntent) -> tuple[tuple[str, str, str], ...]:
        """Bind a PlanningDraft to the effective Python and PLC spec sources."""

        draft = self.create_planning_draft(intent)
        try:
            return self._store.bind_planning_draft_specs(
                draft.request_id, self._effective_spec_sources()
            )
        except ContinuityStoreError as error:
            raise PmFacadeError(str(error)) from error

    def preview_planning_scope_card(
        self,
        intent: PmIntent,
        *,
        scope_paths: tuple[str, ...],
        risks: tuple[str, ...],
        non_goals: tuple[str, ...],
        execution_grant: PlanningExecutionGrant | None = None,
        classification: IntakeClassification | None = None,
        intake_item_id: str = "",
    ) -> PlanningScopeCard:
        """Rebuild an existing plan for approval validation without any durable write."""
        filing, item_id = self._planning_classification(
            intent.request_id, intent.subject_project_id, classification, intake_item_id
        )
        try:
            draft = self._store.get_planning_draft(intent.request_id)
            if draft != PlanningDraft.from_intent(intent):
                raise PmFacadeError("request_id 已绑定不同输入，拒绝覆盖既有 PlanningDraft")
            overview = next(
                (entry for entry in self._store.list_planning_drafts(intent.subject_project_id)
                 if entry.draft.request_id == intent.request_id),
                None,
            )
            if overview is None or not overview.change_id:
                raise PmFacadeError("PlanningDraft 尚未绑定可供批准的 CHG")
            change = self._changes.get_change_request(
                overview.change_id, project_id=intent.subject_project_id
            )
            if change is None:
                raise PmFacadeError("PlanningDraft 未绑定可读取的真实 CHG")
            self._validate_planning_change(draft, overview.change_id, change, filing, item_id)
            return PlanningScopeCard.from_draft(
                draft,
                change_id=overview.change_id,
                scope_paths=scope_paths,
                risks=risks,
                non_goals=non_goals,
                spec_sources=self._store.get_planning_draft_specs(intent.request_id),
                execution_grant=execution_grant,
            )
        except (ContinuityStoreError, ValueError) as error:
            raise PmFacadeError(str(error)) from error

    def create_planning_scope_card(
        self,
        intent: PmIntent,
        *,
        scope_paths: tuple[str, ...],
        risks: tuple[str, ...],
        non_goals: tuple[str, ...],
        execution_grant: PlanningExecutionGrant | None = None,
        classification: IntakeClassification | None = None,
        intake_item_id: str = "",
    ) -> PlanningScopeCard:
        """Create a reviewable card; classified planning succeeds only after durable submission."""
        card, filing, item_id = self._prepare_planning_scope_card(
            intent,
            scope_paths=scope_paths,
            risks=risks,
            non_goals=non_goals,
            execution_grant=execution_grant,
            classification=classification,
            intake_item_id=intake_item_id,
        )
        if filing is not None:
            self._submit_classified_card(
                card, filing, item_id, "PM Facade", allow_approved_replay=True
            )
        return card

    def _submit_classified_card(
        self,
        card: PlanningScopeCard,
        filing: IntakeClassification,
        item_id: str,
        submitted_by: str,
        *,
        allow_approved_replay: bool,
    ) -> None:
        try:
            IntakeStore(
                self._store.workspace_root, self._store.db_path
            ).submit_classified_planning_scope_card(
                card, filing, item_id, submitted_by,
                allow_approved_replay=allow_approved_replay,
            )
        except (ContinuityStoreError, ValueError) as error:
            raise PmFacadeError(str(error)) from error

    def _prepare_planning_scope_card(
        self,
        intent: PmIntent,
        *,
        scope_paths: tuple[str, ...],
        risks: tuple[str, ...],
        non_goals: tuple[str, ...],
        execution_grant: PlanningExecutionGrant | None,
        classification: IntakeClassification | None,
        intake_item_id: str,
    ) -> tuple[PlanningScopeCard, IntakeClassification | None, str]:
        """Run the real contract's pure validation before reserving files or durable identities."""
        try:
            draft = PlanningDraft.from_intent(intent)
            if execution_grant is not None:
                execution_grant = PlanningExecutionGrant.model_validate(
                    execution_grant.model_dump(mode="json")
                )
            PlanningScopeCard.from_draft(
                draft,
                change_id="",
                spec_sources=(),
                scope_paths=scope_paths,
                risks=risks,
                non_goals=non_goals,
                execution_grant=execution_grant,
            )
        except (ValueError, AttributeError) as error:
            raise PmFacadeError(str(error)) from error
        filing, intake_item_id = self._planning_classification(
            intent.request_id, intent.subject_project_id, classification, intake_item_id
        )

        draft = self.create_planning_draft(intent)
        change_id = self.create_planning_draft_change(
            intent, classification=filing, intake_item_id=intake_item_id
        )
        spec_sources = self.bind_planning_draft_specs(intent)
        try:
            card = PlanningScopeCard.from_draft(
                draft,
                change_id=change_id,
                scope_paths=scope_paths,
                risks=risks,
                non_goals=non_goals,
                spec_sources=spec_sources,
                execution_grant=execution_grant,
            )
            return card, filing, intake_item_id
        except ValueError as error:
            raise PmFacadeError(str(error)) from error

    def approve_planning_scope_card(
        self,
        card: PlanningScopeCard,
        *,
        expected_plan_hash: str,
        approver: str,
        approval_evidence_ref: str,
    ) -> DecisionPackageDTO:
        """Bind one exact human approval to one real, immutable Decision."""

        actual_hash = self._planning_scope_card_hash(card)
        if not hmac.compare_digest(actual_hash, card.plan_hash) or not hmac.compare_digest(
            actual_hash, expected_plan_hash
        ):
            raise PmFacadeError("PlanningScopeCard plan_hash 已过期或内容发生漂移")
        try:
            self._decisions.validate_planning_approval(
                approver,
                actual_hash,
                approval_evidence_ref,
            )
            decision_id = self._store.reserve_planning_draft_decision(
                card.request_id,
                card.change_id,
                actual_hash,
                approver,
                approval_evidence_ref,
            )
            try:
                decision = self._decisions.create_decision(
                    card.change_id,
                    approver,
                    project_id=card.subject_project_id,
                    approved_files=list(card.scope_paths),
                    conditions=[
                        *(f"acceptance: {item}" for item in card.acceptance_criteria),
                        *(f"risk: {item}" for item in card.risks),
                        *(f"non-goal: {item}" for item in card.non_goals),
                    ],
                    decision_id=decision_id,
                    planning_plan_hash=actual_hash,
                    approval_evidence_ref=approval_evidence_ref,
                    planning_request_id=card.request_id,
                    planning_execution_grant=card.execution_grant.model_dump(mode="json"),
                )
            except DecisionValidationError as create_error:
                try:
                    decision = self._decisions.get_decision(decision_id)
                except DecisionError:
                    raise create_error
            self._validate_planning_decision(
                decision,
                card=card,
                approver=approver,
                approval_evidence_ref=approval_evidence_ref,
            )
            return decision
        except (ContinuityStoreError, DecisionError) as error:
            raise PmFacadeError(str(error)) from error

    def materialize_planning_mission(
        self,
        card: PlanningScopeCard,
        *,
        created_by: str = "PM Facade",
    ) -> Mission:
        """Materialize one Mission only from the card's persisted approval chain."""

        actual_hash = self._planning_scope_card_hash(card)
        if not hmac.compare_digest(actual_hash, card.plan_hash):
            raise PmFacadeError("PlanningScopeCard plan_hash 已过期或内容发生漂移")
        try:
            decision_id = self._store.get_planning_draft_decision_id(
                card.request_id, card.change_id, actual_hash
            )
            decision = self._decisions.get_decision(decision_id)
            approval = decision.metadata.get("planning_approval")
            if not isinstance(approval, dict):
                raise PmFacadeError("Decision 缺少 PlanningScopeCard 批准证据")
            evidence_ref = approval.get("approval_evidence_ref")
            if not isinstance(evidence_ref, str) or not evidence_ref:
                raise PmFacadeError("Decision 缺少非模型自签的批准证据")
            self._validate_planning_decision(
                decision,
                card=card,
                approver=decision.approver,
                approval_evidence_ref=evidence_ref,
            )
            change = self._changes.get_change_request(
                card.change_id, project_id=card.subject_project_id
            )
            if change is None or change.change_number != card.change_id:
                raise PmFacadeError("PlanningScopeCard 未绑定可读取的真实 CHG")
            if change.status not in {"approved", "implementing", "pending_acceptance", "accepting", "completed"}:
                raise PmFacadeError("PlanningScopeCard 绑定的 CHG 尚未批准")
            draft = self._store.get_planning_draft(card.request_id)
            if (
                draft.subject_project_id != card.subject_project_id
                or draft.acceptance_criteria != card.acceptance_criteria
            ):
                raise PmFacadeError("PlanningDraft 与批准范围卡不一致")
            mission_id = self._store.resolve_planning_draft_mission_id(
                card.request_id,
                decision.decision_id,
                decision.change_id,
                actual_hash,
            )
            return cast(
                Mission,
                self._missions.create_from_planning_approval(
                    mission_id=mission_id,
                    draft=draft,
                    decision=decision,
                    plan_hash=actual_hash,
                    created_by=created_by,
                ),
            )
        except (ContinuityStoreError, DecisionError, MissionServiceError) as error:
            raise PmFacadeError(str(error)) from error

    def create_planning_work(self, card: PlanningScopeCard, *, owner: str = "PM Facade") -> WorkItem:
        """Derive Work only from the already-materialized Mission for this exact card."""
        actual_hash = self._planning_scope_card_hash(card)
        if not hmac.compare_digest(actual_hash, card.plan_hash):
            raise PmFacadeError("PlanningScopeCard plan_hash 已过期或内容发生漂移")
        try:
            decision_id = self._store.get_planning_draft_decision_id(
                card.request_id, card.change_id, actual_hash
            )
            mission_id = self._store.resolve_planning_draft_mission_id(
                card.request_id, decision_id, card.change_id, actual_hash
            )
            self._missions.get(mission_id)
            return cast(
                WorkItem,
                self._works.create_from_mission(
                    mission_id=mission_id, owner=owner, scope_paths=list(card.scope_paths)
                ),
            )
        except (ContinuityStoreError, MissionServiceError, WorkRegistryError) as error:
            raise PmFacadeError(str(error)) from error

    def prepare_planning_execution(
        self,
        card: PlanningScopeCard,
        *,
        expected_plan_hash: str,
        lease_token: str,
    ) -> ExecutionDispatchResult:
        """Recover the exact approval chain and prepare one isolated, unstarted Run."""

        actual_hash = self._planning_scope_card_hash(card)
        if not hmac.compare_digest(actual_hash, card.plan_hash) or not hmac.compare_digest(
            actual_hash, expected_plan_hash
        ):
            raise PmFacadeError("PlanningScopeCard plan_hash 已过期或内容发生漂移")
        if card.execution_grant.required_worktree_mode.value != "ISOLATED":
            raise PmFacadeError("批准式执行必须使用 ISOLATED worktree")
        mission = self.materialize_planning_mission(card)
        work = self.create_planning_work(card)
        if mission.state is MissionState.DRAFT:
            self.plan(mission.mission_id)
            mission = self._mission(mission.mission_id)
        if mission.state is MissionState.AWAITING_APPROVAL:
            self.approve(mission.mission_id, work.work_id)
            mission = self._mission(mission.mission_id)
        if mission.state is not MissionState.ACTIVE or mission.root_work_id != work.work_id:
            raise PmFacadeError("批准请求未恢复为唯一 ACTIVE Mission/root Work")
        suffix = hashlib.sha256(
            f"{card.request_id}\n{actual_hash}".encode()
        ).hexdigest().upper()
        try:
            return self._execution.prepare(
                mission=mission,
                work_id=work.work_id,
                run_id=f"RUN-PLAN-{suffix[:16]}",
                adapter=card.execution_grant.adapter,
                executor_id=card.execution_grant.approved_model,
                lease_token=lease_token,
                lease_seconds=self._planning_lease_seconds,
                idempotency_key=f"planning-execute:{card.request_id}:{actual_hash}",
                operation_id=f"planning-execute:{card.request_id}:{actual_hash}",
                force_isolation=True,
                reconcile_incomplete=True,
            )
        except ExecutionDispatchError as error:
            raise PmFacadeError(str(error)) from error

    def execute_planning_foreground(
        self,
        card: PlanningScopeCard,
        *,
        expected_plan_hash: str,
        lease_token: str,
        lease_token_environment: str,
    ) -> ForegroundExecutionReceipt:
        """Run the approved local Saga in this foreground process until final disposition."""

        dispatch = self.prepare_planning_execution(
            card,
            expected_plan_hash=expected_plan_hash,
            lease_token=lease_token,
        )
        try:
            microtask = self._execution.prepare_microtask(dispatch.intent.operation_id)
            return cast(
                ForegroundExecutionReceipt,
                self._local_orchestrator.execute(
                    dispatch=dispatch,
                    microtask=microtask,
                    lease_token_environment=lease_token_environment,
                ),
            )
        except (ExecutionDispatchError, LocalExecutionOrchestratorError) as error:
            raise PmFacadeError(str(error)) from error

    def list_planning_drafts(self, subject_project_id: str) -> tuple[PlanningDraftOverview, ...]:
        """List every planning draft of a project with the stage its scope card has reached."""

        try:
            return self._store.list_planning_drafts(subject_project_id)
        except ContinuityStoreError as error:
            raise PmFacadeError(str(error)) from error

    def list_pending_planning_scope_cards(
        self, subject_project_id: str
    ) -> tuple[SubmittedPlanningScopeCard, ...]:
        """List the newest not yet approved scope card of each request of a project."""

        try:
            return self._store.list_pending_planning_scope_cards(subject_project_id)
        except ContinuityStoreError as error:
            raise PmFacadeError(str(error)) from error

    def submit_planning_scope_card(
        self,
        request_id: str,
        *,
        scope_paths: tuple[str, ...],
        risks: tuple[str, ...],
        non_goals: tuple[str, ...],
        execution_grant: PlanningExecutionGrant,
        submitted_by: str,
        classification: IntakeClassification | None = None,
        intake_item_id: str = "",
    ) -> SubmittedPlanningScopeCard:
        """Build the scope card of a persisted draft and persist it for human approval."""

        grant: object = execution_grant
        if not isinstance(grant, PlanningExecutionGrant):
            raise PmFacadeError("范围卡必须显式给出 execution_grant")
        try:
            draft = self._store.get_planning_draft(request_id)
        except ContinuityStoreError as error:
            raise PmFacadeError(str(error)) from error
        card, filing, item_id = self._prepare_planning_scope_card(
            PmIntent(
                subject_project_id=draft.subject_project_id,
                request_id=draft.request_id,
                objective=draft.objective,
                acceptance_criteria=draft.acceptance_criteria,
            ),
            scope_paths=scope_paths,
            risks=risks,
            non_goals=non_goals,
            execution_grant=execution_grant,
            classification=classification,
            intake_item_id=intake_item_id,
        )
        try:
            if filing is None:
                self._store.submit_planning_scope_card(card, submitted_by)
            else:
                self._submit_classified_card(
                    card, filing, item_id, submitted_by, allow_approved_replay=False
                )
            return self._store.get_submitted_planning_scope_card(card.request_id, card.plan_hash)
        except (ContinuityStoreError, ValueError) as error:
            raise PmFacadeError(str(error)) from error

    def approve_pending_planning_scope_card(
        self,
        request_id: str,
        *,
        expected_plan_hash: str,
        approver: str,
        approval_evidence_ref: str,
    ) -> PlanningApprovalResult:
        """Approve one persisted card by plan hash: CHG, Decision, Mission and Work in one call."""

        try:
            # A refused approval must write nothing, so the human evidence is checked first.
            self._decisions.validate_planning_approval(
                approver, expected_plan_hash, approval_evidence_ref
            )
            submitted = self._store.get_submitted_planning_scope_card(request_id, expected_plan_hash)
            if submitted.superseded:
                raise PmFacadeError("该范围卡已被新修订取代，请批准最新修订")
            card = submitted.card
            if not self._planning_request_is_approved(card) and self._store.list_missions(
                card.subject_project_id
            ):
                raise PmFacadeError("项目已有未终结的任务；请先验收或取消它，再批准新的范围卡")
            self._approve_planning_change(card, approver)
            decision = self.approve_planning_scope_card(
                card,
                expected_plan_hash=expected_plan_hash,
                approver=approver,
                approval_evidence_ref=approval_evidence_ref,
            )
            mission = self.materialize_planning_mission(card)
            work = self.create_planning_work(card)
        except (
            ContinuityStoreError,
            DecisionError,
            MissionServiceError,
            WorkRegistryError,
            ValueError,
        ) as error:
            raise PmFacadeError(str(error)) from error
        return PlanningApprovalResult(
            request_id=card.request_id,
            subject_project_id=card.subject_project_id,
            change_id=card.change_id,
            plan_hash=card.plan_hash,
            decision_id=decision.decision_id,
            mission_id=mission.mission_id,
            work_id=work.work_id,
        )

    def _planning_request_is_approved(self, card: PlanningScopeCard) -> bool:
        return any(
            item.approved
            for item in self._store.list_planning_drafts(card.subject_project_id)
            if item.draft.request_id == card.request_id
        )

    def _approve_planning_change(self, card: PlanningScopeCard, approver: str) -> None:
        """Advance the card's CHG to approved, resuming from whichever review step it reached."""

        change = self._changes.get_change_request(card.change_id, project_id=card.subject_project_id)
        if change is None or change.change_number != card.change_id:
            raise PmFacadeError("PlanningScopeCard 未绑定可读取的真实 CHG")
        for state in _PLANNING_CHANGE_APPROVAL_STEPS.get(change.status, ()):
            change = self._changes.transition_status(
                card.change_id,
                state,
                approver=approver,
                comment=f"user approved planning scope {card.plan_hash}",
                project_id=card.subject_project_id,
            )
        if change.status not in _PLANNING_CHANGE_APPROVED_STATES:
            raise PmFacadeError(f"PlanningScopeCard 绑定的 CHG 不可批准: {change.status}")

    def recover_planning_scope_card(self, mission_id: str) -> PlanningScopeCard:
        """Rebuild the exact approved card from persisted, independently bound facts."""

        try:
            mission = self._missions.get(mission_id)
            decision = self._decisions.get_decision(mission.authority.decision_id)
            approval = decision.metadata.get("planning_approval")
            if not isinstance(approval, dict):
                raise PmFacadeError("Mission Decision 缺少 planning_approval")
            request_id = approval.get("request_id")
            plan_hash = approval.get("plan_hash")
            raw_grant = approval.get("execution_grant")
            if not isinstance(request_id, str) or not isinstance(plan_hash, str):
                raise PmFacadeError("Mission Decision 的规划身份不完整")
            grant = PlanningExecutionGrant.model_validate(raw_grant)
            draft = self._store.get_planning_draft(request_id)
            specs = self._store.get_planning_draft_specs(request_id)
            risks = tuple(
                item.removeprefix("risk: ")
                for item in decision.conditions
                if item.startswith("risk: ")
            )
            non_goals = tuple(
                item.removeprefix("non-goal: ")
                for item in decision.conditions
                if item.startswith("non-goal: ")
            )
            card = PlanningScopeCard.from_draft(
                draft,
                change_id=decision.change_id,
                scope_paths=tuple(decision.approved_files),
                risks=risks,
                non_goals=non_goals,
                spec_sources=specs,
                execution_grant=grant,
            )
            if (
                mission.subject_project_id != card.subject_project_id
                or mission.authority.change_id != card.change_id
                or not hmac.compare_digest(card.plan_hash, plan_hash)
            ):
                raise PmFacadeError("Mission、Decision 与 PlanningScopeCard 身份不一致")
            return card
        except (ContinuityStoreError, DecisionError, MissionServiceError, ValueError) as error:
            raise PmFacadeError(str(error)) from error

    def start_approved_mission_foreground(
        self, mission_id: str
    ) -> ForegroundExecutionReceipt:
        """Consume one user confirmation and start the approved isolated execution."""

        self.approve(mission_id)
        card = self.recover_planning_scope_card(mission_id)
        return self.execute_planning_foreground(
            card,
            expected_plan_hash=card.plan_hash,
            lease_token=secrets.token_urlsafe(32),
            lease_token_environment="AUTO_PM_EXECUTION_LEASE_TOKEN",
        )

    def run_approved_planning(
        self,
        card: PlanningScopeCard,
        *,
        expected_plan_hash: str,
        lease_token: str,
        lease_token_environment: str,
    ) -> PmRunOutcome:
        """Run one approved card in isolation, then verify it up to the acceptance gate."""

        actual_hash = self._planning_scope_card_hash(card)
        if not hmac.compare_digest(actual_hash, card.plan_hash) or not hmac.compare_digest(
            actual_hash, expected_plan_hash
        ):
            raise PmFacadeError("PlanningScopeCard plan_hash 已过期或内容发生漂移")
        mission = self.materialize_planning_mission(card)
        work = self.create_planning_work(card)
        mission = self._mission(mission.mission_id)
        if mission.state is MissionState.ACCEPTANCE_PENDING:
            return self.verify_for_acceptance(mission.mission_id, lease_token=lease_token)
        if mission.state in {
            MissionState.ACCEPTED,
            MissionState.CLOSED,
            MissionState.CANCELLED,
            MissionState.BLOCKED,
        }:
            raise PmFacadeError("该需求已验收、已结束或被阻塞，不能重复执行")
        if mission.state is MissionState.DRAFT:
            self.plan(mission.mission_id)
        self.approve(mission.mission_id, work.work_id)
        self.execute(mission.mission_id)
        receipt = self.execute_planning_foreground(
            card,
            expected_plan_hash=expected_plan_hash,
            lease_token=lease_token,
            lease_token_environment=lease_token_environment,
        )
        if receipt.status != "VERIFYING":
            return PmRunOutcome(
                mission_id=mission.mission_id,
                run_id=receipt.run_id,
                receipt_status=receipt.status,
                verified=False,
                mission_state=self._mission(mission.mission_id).state,
                message=_NOT_FINISHED_MESSAGE,
            )
        outcome = self.verify_for_acceptance(mission.mission_id, lease_token=lease_token)
        return outcome.model_copy(update={"receipt_status": receipt.status})

    def verify_for_acceptance(self, mission_id: str, *, lease_token: str) -> PmRunOutcome:
        """Generate the system-bound quality Checkpoint and open the acceptance gate."""

        mission = self._mission(mission_id)
        if mission.state not in {MissionState.ACTIVE, MissionState.ACCEPTANCE_PENDING}:
            raise PmFacadeError("当前 Mission 不在可验证状态")
        if not mission.root_work_id:
            raise PmFacadeError("Mission 缺少根 Work，不能验证")
        work = self._work(mission.root_work_id)
        try:
            runs = self._store.list_runs(work.work_id, include_terminal=True)
        except ContinuityStoreError as error:
            raise PmFacadeError(str(error)) from error
        if not runs or runs[0].state is not RunState.VERIFYING:
            raise PmFacadeError("最新 Run 未处于 VERIFYING，不能验证")
        run = runs[0]
        try:
            owner_id = self._store.get_lease(run.run_id).owner_id
        except ContinuityStoreError as error:
            raise PmFacadeError(str(error)) from error
        checkpoint_id = f"CP-{run.run_id}-VERIFY"
        try:
            profile = EvidenceCollectionService(self._workspace_root).checkpoint_profile_for_run(run)
            ContinuityExecutionService(
                self._workspace_root, store=self._store
            ).append_verified_checkpoint(
                checkpoint_id=checkpoint_id,
                run_id=run.run_id,
                owner_id=owner_id,
                lease_token=lease_token,
                project_root=Path(run.worktree_path),
                profile=profile,
            )
        except (ContinuityExecutionError, EvidenceCollectionError):
            log.exception("质量验证未通过: mission=%s run=%s", mission.mission_id, run.run_id)
            return PmRunOutcome(
                mission_id=mission.mission_id,
                run_id=run.run_id,
                receipt_status=run.state.value,
                verified=False,
                mission_state=mission.state,
                message=_NOT_VERIFIED_MESSAGE,
            )
        if mission.state is MissionState.ACTIVE:
            mission = self._transition(
                mission,
                MissionState.ACCEPTANCE_PENDING,
                root_work_id=mission.root_work_id,
                action="verify",
            )
        return PmRunOutcome(
            mission_id=mission.mission_id,
            run_id=run.run_id,
            receipt_status=run.state.value,
            verified=True,
            checkpoint_id=checkpoint_id,
            mission_state=mission.state,
            message=_VERIFIED_MESSAGE,
        )

    @staticmethod
    def _planning_scope_card_hash(card: PlanningScopeCard) -> str:
        payload = {
            "request_id": card.request_id,
            "subject_project_id": card.subject_project_id,
            "change_id": card.change_id,
            "scope_paths": card.scope_paths,
            "acceptance_criteria": card.acceptance_criteria,
            "risks": card.risks,
            "non_goals": card.non_goals,
            "spec_sources": card.spec_sources,
            "execution_grant": card.execution_grant.model_dump(mode="json"),
        }
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
                "utf-8"
            )
        ).hexdigest()

    @staticmethod
    def _validate_planning_decision(
        decision: DecisionPackageDTO,
        *,
        card: PlanningScopeCard,
        approver: str,
        approval_evidence_ref: str,
    ) -> None:
        metadata = decision.metadata.get("planning_approval")
        expected_metadata = {
            "schema_version": "planning-approval.v2",
            "plan_hash": card.plan_hash,
            "approval_evidence_ref": approval_evidence_ref,
            "request_id": card.request_id,
            "execution_grant": card.execution_grant.model_dump(mode="json"),
        }
        if (
            decision.project_id != card.subject_project_id
            or decision.change_id != card.change_id
            or decision.approved_files != list(card.scope_paths)
            or decision.approver != approver
            or decision.decision_conclusion not in {"approved", "conditionally_approved"}
            or metadata != expected_metadata
        ):
            raise PmFacadeError("既有 Decision 与 PlanningScopeCard 批准事实不一致")

    def _effective_spec_sources(self) -> tuple[tuple[str, str, str], ...]:
        registry_path = self._workspace_root / "00_Obsidian_Base全局规范文件仓库" / "spec_registry.json"
        try:
            payload = json.loads(registry_path.read_text(encoding="utf-8", errors="replace"))
        except FileNotFoundError as error:
            raise PmFacadeError(f"规范注册表不存在: {registry_path}") from error
        except json.JSONDecodeError as error:
            raise PmFacadeError(f"规范注册表 JSON 无效: {error.msg}") from error
        specs = payload.get("specs") if isinstance(payload, dict) else None
        if not isinstance(specs, dict):
            raise PmFacadeError("规范注册表缺少 specs 对象")
        sources: list[tuple[str, str, str]] = []
        covered_domains: set[str] = set()
        for spec_id, raw in specs.items():
            if not isinstance(spec_id, str) or not isinstance(raw, dict):
                raise PmFacadeError("规范注册表含无效条目")
            entry = cast(dict[str, Any], raw)
            domain = entry.get("domain")
            lifecycle = entry.get("lifecycle")
            if domain not in {"python", "plc"} or lifecycle not in {"stable", "active"}:
                continue
            canonical_path = entry.get("canonical_path")
            version = entry.get("version")
            if not isinstance(canonical_path, str) or not canonical_path.strip():
                raise PmFacadeError(f"规范 {spec_id} 缺少 canonical_path")
            if not isinstance(version, str) or not version.strip():
                raise PmFacadeError(f"规范 {spec_id} 缺少 version")
            resolved = (self._workspace_root / canonical_path).resolve()
            try:
                resolved.relative_to(self._workspace_root.resolve())
            except ValueError as error:
                raise PmFacadeError(f"规范 {spec_id} 路径越出工作区: {canonical_path}") from error
            if not resolved.is_file():
                raise PmFacadeError(f"规范文件不存在: {spec_id} -> {canonical_path}")
            covered_domains.add(domain)
            sources.append((spec_id, canonical_path, version))
        missing = {"python", "plc"} - covered_domains
        if missing:
            raise PmFacadeError(f"规范注册表缺少有效领域: {', '.join(sorted(missing))}")
        return tuple(sorted(sources))

    def plan(self, mission_id: str) -> PmConfirmationCard:
        """Present the first confirmation card and persist only its legal state change."""
        mission = self._mission(mission_id)
        if mission.state is MissionState.DRAFT:
            mission = self._transition(
                mission,
                MissionState.AWAITING_APPROVAL,
                root_work_id=None,
                action="plan",
            )
        if mission.state is not MissionState.AWAITING_APPROVAL:
            raise PmFacadeError("当前 Mission 不能生成开工确认卡")
        return self._card(
            mission,
            PmConfirmationKind.APPROVAL,
            "请确认需求、验收条件和授权边界；确认后驾驶舱才会安排执行。",
            ("approve", "cancel"),
        )

    def approve(self, mission_id: str, root_work_id: str = "") -> PmConfirmationCard:
        """Apply the first approval using the Mission-bound Work when available."""
        mission = self._mission(mission_id)
        requested_root_work_id = root_work_id.strip()
        bound_root_work_id = mission.root_work_id
        if (
            requested_root_work_id
            and bound_root_work_id
            and requested_root_work_id != bound_root_work_id
        ):
            raise PmFacadeError("该需求已绑定其他内部授权，拒绝切换执行范围")
        effective_root_work_id = bound_root_work_id or requested_root_work_id
        if not effective_root_work_id:
            raise PmFacadeError("该需求尚未完成内部授权，暂时不能开始执行")
        if mission.state is MissionState.AWAITING_APPROVAL:
            work = self._work(effective_root_work_id)
            if work.state not in {WorkState.READY, WorkState.IN_PROGRESS}:
                raise PmFacadeError("需求尚未获得对应授权，不能开始执行")
            mission = self._transition(
                mission,
                MissionState.ACTIVE,
                root_work_id=effective_root_work_id,
                action="approve",
            )
        if mission.state is not MissionState.ACTIVE:
            raise PmFacadeError("当前 Mission 不能进入执行态")
        return self._card(
            mission,
            PmConfirmationKind.EXECUTION,
            "已获批准；驾驶舱将在授权边界内安排执行、恢复与分流。",
            ("execute", "resume"),
        )

    def confirm_start(self, mission_id: str) -> PmConfirmationCard:
        """Perform the user's one start confirmation without requesting internal IDs."""
        self.approve(mission_id)
        return self.execute(mission_id)

    def execute(self, mission_id: str) -> PmConfirmationCard:
        """Start the Mission's authorized root Work, without creating hidden state."""
        mission = self._mission(mission_id)
        if mission.state is not MissionState.ACTIVE or not mission.root_work_id:
            raise PmFacadeError("当前 Mission 不在可执行状态")
        work = self._work(mission.root_work_id)
        if work.state is WorkState.READY:
            try:
                self._works.transition(
                    work.work_id,
                    WorkState.IN_PROGRESS,
                    f"pm-execute:{mission.mission_id}:work-v{work.version}",
                )
            except WorkRegistryError as error:
                raise PmFacadeError(str(error)) from error
        elif work.state is not WorkState.IN_PROGRESS:
            raise PmFacadeError("root Work 不在可执行状态")
        return self._card(
            mission,
            PmConfirmationKind.EXECUTION,
            "执行已由驾驶舱接管；只有越出授权边界或需要最终验收时才会打扰你。",
            ("resume",),
        )

    def resume(
        self,
        *,
        project_id: str = "",
        invocation_path: str | None = None,
        work_id: str = "",
        run_id: str = "",
    ) -> ContinuityResume:
        """Return a strictly read-only recovery view for a new PM conversation."""
        return self._query(
            project_id=project_id, invocation_path=invocation_path, work_id=work_id, run_id=run_id, requested_action=""
        )

    def orient(
        self,
        *,
        project_id: str = "",
        invocation_path: str | None = None,
        work_id: str = "",
        run_id: str = "",
        requested_action: str = "",
    ) -> ContinuityResume:
        """The same read-only view as ``resume``, plus an explicit answer for one asked action (UNSUPPORTED in M2)."""
        return self._query(
            project_id=project_id,
            invocation_path=invocation_path,
            work_id=work_id,
            run_id=run_id,
            requested_action=requested_action,
        )

    def _query(
        self, *, project_id: str, invocation_path: str | None, work_id: str, run_id: str, requested_action: str
    ) -> ContinuityResume:
        try:
            answer = ContinuityQueryService(self._workspace_root, execution_root=self._execution_root).query(
                project_id=project_id,
                invocation_path=invocation_path,
                work_id=work_id,
                run_id=run_id,
                requested_action=requested_action,
            )
            return validate_query_resume(answer, require_query=True)
        except (ContinuityQueryError, ValueError) as error:
            raise PmFacadeError(str(error)) from error

    def accept(self, mission_id: str) -> PmConfirmationCard:
        """Record only the final user acceptance after verification has reached its gate."""
        mission = self._mission(mission_id)
        if mission.state is MissionState.ACCEPTANCE_PENDING:
            self._require_current_acceptance_checkpoint(mission)
            mission = self._transition(
                mission,
                MissionState.ACCEPTED,
                root_work_id=mission.root_work_id,
                action="accept",
            )
        if mission.state is not MissionState.ACCEPTED:
            raise PmFacadeError("当前 Mission 尚未到达用户验收门")
        return self._card(
            mission,
            PmConfirmationKind.ACCEPTANCE,
            "请确认最终验收；确认后驾驶舱才会执行关闭和台账闭环。",
            ("close",),
        )

    def acceptance_gate_reason(self, mission_id: str) -> str:
        """Explain, read-only, why final acceptance is not yet allowed.

        Returns an empty string only when the very checks that ``accept`` applies
        would pass; otherwise returns the same user-facing reason ``accept`` would
        raise.  It never writes Mission, Work, Run, Checkpoint or lease state.
        """
        mission = self._mission(mission_id)
        if mission.state is not MissionState.ACCEPTANCE_PENDING:
            return "当前 Mission 尚未到达用户验收门"
        try:
            self._require_current_acceptance_checkpoint(mission)
        except PmFacadeError as error:
            return str(error)
        return ""

    def _require_current_acceptance_checkpoint(self, mission: Mission) -> None:
        """Require the newest Run to carry current, passing quality evidence.

        Mission state is only the user-facing phase marker.  It cannot replace
        the immutable Run/Checkpoint evidence chain that proves the approved
        work was actually verified.
        """

        if not mission.root_work_id:
            raise PmFacadeError("Mission 缺少根 Work，不能执行验收")
        work = self._work(mission.root_work_id)
        runs = self._store.list_runs(work.work_id, include_terminal=True)
        if not runs:
            raise PmFacadeError("根 Work 尚无可验收的 Run")
        run = runs[0]
        if run.state is not RunState.VERIFYING:
            raise PmFacadeError("最新 Run 未处于 VERIFYING，不能使用旧成功或失败证据验收")
        checkpoint = self._store.latest_checkpoint(run.run_id)
        if checkpoint is None:
            raise PmFacadeError("最新 VERIFYING Run 缺少 Checkpoint")
        if checkpoint.git_head != run.git_head:
            raise PmFacadeError("Checkpoint 与最新 Run 基线不一致")
        if tuple(sorted(checkpoint.dirty_paths)) != tuple(sorted(run.declared_dirty_paths)):
            raise PmFacadeError("Checkpoint 与最新 Run 声明差异不一致")
        if len(checkpoint.evidence) != 1:
            raise PmFacadeError("Checkpoint 必须包含唯一的自动质量证据")

        try:
            envelope = json.loads(checkpoint.evidence[0])
            receipt = envelope["quality_receipt"]
            project_root = receipt["project_root"]
            if not isinstance(project_root, str) or not project_root:
                raise ValueError("project_root")
            collector = EvidenceCollectionService(self._workspace_root)
            collection = collector.collect(run)
        except (EvidenceCollectionError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise PmFacadeError("最新 Checkpoint 证据无效或已过期") from error
        if not self._acceptance_evidence_is_current(
            checkpoint.evidence[0], collection, run, project_root
        ):
            raise PmFacadeError("最新 Checkpoint 未证明当前通过的质量证据")

    @staticmethod
    def _acceptance_evidence_is_current(
        serialized: str,
        collection: EvidenceCollection,
        run: Any,
        project_root: str,
    ) -> bool:
        """Validate a generic content-bound quality receipt without C03 coupling."""

        try:
            envelope = json.loads(serialized)
            if isinstance(envelope, dict) and envelope.get("schema_version") in {
                "checkpoint-evidence.v2",
                "checkpoint-evidence.v3",
            }:
                return EvidenceCollectionService.checkpoint_evidence_is_current(
                    serialized, collection, run, project_root
                )
            expected_keys = {
                "schema_version", "collection", "collection_hash", "quality_receipt",
                "receipt_hash", "envelope_hash",
            }
            if not isinstance(envelope, dict) or set(envelope) != expected_keys:
                return False
            unsigned = {key: value for key, value in envelope.items() if key != "envelope_hash"}
            if (
                serialized != PmFacadeService._canonical_json(envelope)
                or not isinstance(envelope["envelope_hash"], str)
                or not hmac.compare_digest(
                    envelope["envelope_hash"], PmFacadeService._evidence_hash(unsigned)
                )
                or envelope["schema_version"] != "checkpoint-evidence.v1"
                or envelope["collection"] != PmFacadeService._collection_payload(collection)
                or not isinstance(envelope["collection_hash"], str)
                or not hmac.compare_digest(envelope["collection_hash"], collection.content_hash)
            ):
                return False
            receipt = envelope["quality_receipt"]
            if not isinstance(receipt, dict):
                return False
            receipt_keys = {
                "run_id", "baseline_git_head", "candidate_path", "project_root",
                "evidence_hash", "gates", "evidence_current", "evidence_error", "status",
            }
            if set(receipt) != receipt_keys:
                return False
            candidate = Path(collection.worktree_path).resolve()
            resolved_project_root = Path(project_root).resolve()
            resolved_project_root.relative_to(candidate)
            if not (resolved_project_root / "pyproject.toml").is_file():
                return False
            receipt_payload = {key: value for key, value in receipt.items() if key != "status"}
            gates = receipt["gates"]
            gate_keys = {
                "name", "command", "cwd", "exit_code", "output_digest", "output_summary",
            }
            if (
                not isinstance(envelope["receipt_hash"], str)
                or not hmac.compare_digest(
                    envelope["receipt_hash"], PmFacadeService._evidence_hash(receipt_payload)
                )
                or receipt["status"] != "PASS"
                or receipt["run_id"] != run.run_id
                or receipt["baseline_git_head"] != run.git_head
                or receipt["candidate_path"] != collection.worktree_path
                or receipt["project_root"] != str(resolved_project_root)
                or receipt["evidence_hash"] != collection.content_hash
                or receipt["evidence_current"] is not True
                or receipt["evidence_error"] is not None
                or not isinstance(gates, list)
                or tuple(gate.get("name") for gate in gates if isinstance(gate, dict))
                != ("pytest", "ruff", "mypy")
                or not all(
                    isinstance(gate, dict)
                    and set(gate) == gate_keys
                    and isinstance(gate["command"], list)
                    and all(isinstance(item, str) for item in gate["command"])
                    and isinstance(gate["cwd"], str)
                    and gate["exit_code"] == 0
                    and isinstance(gate["output_digest"], str)
                    and bool(gate["output_digest"])
                    and isinstance(gate["output_summary"], str)
                    for gate in gates
                )
            ):
                return False
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return False
        return True

    @staticmethod
    def _collection_payload(collection: EvidenceCollection) -> dict[str, object]:
        """Render the immutable collection payload protected by the envelope."""

        return {
            "run_id": collection.run_id,
            "baseline_git_head": collection.baseline_git_head,
            "worktree_path": collection.worktree_path,
            "staged_paths": list(collection.staged_paths),
            "unstaged_paths": list(collection.unstaged_paths),
            "untracked_paths": list(collection.untracked_paths),
            "untracked_content_hashes": [
                {"path": path, "sha256": digest}
                for path, digest in collection.untracked_content_hashes
            ],
            "staged_diff": collection.staged_diff,
            "staged_diff_sha256": hashlib.sha256(
                collection.staged_diff.encode("utf-8")
            ).hexdigest(),
            "unstaged_diff": collection.unstaged_diff,
            "unstaged_diff_sha256": hashlib.sha256(
                collection.unstaged_diff.encode("utf-8")
            ).hexdigest(),
        }

    @staticmethod
    def _canonical_json(payload: object) -> str:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _evidence_hash(payload: object) -> str:
        return hashlib.sha256(PmFacadeService._canonical_json(payload).encode("utf-8")).hexdigest()

    @staticmethod
    def compatibility_notice() -> str:
        """Keep the historic name discoverable without loading its quarantined implementation."""
        return "兼容提示：pm-workflow 已退役隔离；请使用 pm plan / approve / execute / resume / accept。"

    def _mission(self, mission_id: str) -> Mission:
        try:
            return cast(Mission, self._missions.get(mission_id))
        except MissionServiceError as error:
            raise PmFacadeError(str(error)) from error

    def _work(self, work_id: str) -> WorkItem:
        try:
            return self._store.get_work(work_id)
        except ContinuityStoreError as error:
            raise PmFacadeError(str(error)) from error

    def _transition(
        self,
        mission: Mission,
        new_state: MissionState,
        *,
        root_work_id: str | None,
        action: str,
    ) -> Mission:
        try:
            return cast(
                Mission,
                self._missions.transition(
                    mission_id=mission.mission_id,
                    expected_version=mission.version,
                    new_state=new_state,
                    root_work_id=root_work_id,
                    idempotency_key=f"pm-{action}:{mission.mission_id}:v{mission.version}",
                ),
            )
        except MissionServiceError as error:
            raise PmFacadeError(str(error)) from error

    @staticmethod
    def _card(
        mission: Mission,
        kind: PmConfirmationKind,
        summary: str,
        next_actions: tuple[str, ...],
    ) -> PmConfirmationCard:
        return PmConfirmationCard(
            kind=kind,
            mission_id=mission.mission_id,
            title=mission.title,
            mission_state=mission.state,
            summary=summary,
            acceptance_criteria=mission.acceptance_criteria,
            next_actions=next_actions,
        )
