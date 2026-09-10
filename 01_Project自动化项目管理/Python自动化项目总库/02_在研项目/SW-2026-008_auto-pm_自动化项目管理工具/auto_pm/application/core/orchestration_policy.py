"""Deterministic authorization policy for Mission orchestration."""

from __future__ import annotations

from datetime import datetime

from auto_pm.contracts.continuity import WorkKind
from auto_pm.contracts.mission import AuthorityEnvelope, Mission
from auto_pm.contracts.orchestration import (
    OrchestrationEscalationReason,
    OrchestrationFinding,
)


class OrchestrationPolicy:
    """Classify typed findings and reject any authority boundary exit."""

    @staticmethod
    def classify(finding: OrchestrationFinding) -> WorkKind:
        """Keep classification deterministic: the typed producer declares the Work kind."""
        return finding.kind

    @staticmethod
    def blocks_parent(kind: WorkKind) -> bool:
        """Only defects and failed tests block an existing delivery path."""
        return kind in {WorkKind.BUG, WorkKind.TEST}

    @classmethod
    def finding_escalation(
        cls,
        mission: Mission,
        finding: OrchestrationFinding,
        now: datetime,
    ) -> OrchestrationEscalationReason | None:
        """Return a fail-closed reason instead of inferring permission."""
        authority = mission.authority
        if finding.subject_project_id != mission.subject_project_id:
            return OrchestrationEscalationReason.SUBJECT_PROJECT_EXIT
        if now < authority.valid_from or now > authority.expires_at:
            return OrchestrationEscalationReason.AUTHORITY_EXPIRED
        if finding.kind not in authority.allowed_child_work_kinds:
            return OrchestrationEscalationReason.UNAUTHORIZED_WORK_KIND
        if not cls._paths_covered(finding.scope_paths, authority.scope_paths):
            return OrchestrationEscalationReason.SCOPE_EXIT
        if finding.requires_physical_or_safety_decision:
            return OrchestrationEscalationReason.PHYSICAL_OR_SAFETY_DECISION
        if finding.requires_external_action:
            return OrchestrationEscalationReason.EXTERNAL_ACTION
        if (
            finding.requires_business_line_reroute
            and not authority.routing.allow_business_line_reroute
        ):
            return OrchestrationEscalationReason.BUSINESS_LINE_REROUTE
        if (
            finding.requires_execution_branch_change
            and not authority.routing.allow_execution_branch_changes
        ):
            return OrchestrationEscalationReason.EXECUTION_BRANCH_CHANGE
        return None

    @staticmethod
    def repair_start_escalation(
        authority: AuthorityEnvelope,
        *,
        attempts_used: int,
        elapsed_seconds_used: int,
        current_elapsed_seconds: int,
    ) -> OrchestrationEscalationReason | None:
        """Allow an attempt only inside the approval-supplied bounded budget."""
        routing = authority.routing
        if not routing.auto_repair_enabled:
            return OrchestrationEscalationReason.REPAIR_BUDGET_DISABLED
        if attempts_used >= routing.max_auto_repair_attempts:
            return OrchestrationEscalationReason.REPAIR_BUDGET_EXHAUSTED
        if elapsed_seconds_used + current_elapsed_seconds > routing.max_auto_repair_seconds:
            return OrchestrationEscalationReason.REPAIR_BUDGET_EXHAUSTED
        return None

    @staticmethod
    def retry_escalation(
        authority: AuthorityEnvelope, *, attempt_count: int
    ) -> OrchestrationEscalationReason | None:
        """A failed final permitted attempt cannot silently retry forever."""
        if attempt_count >= authority.routing.max_auto_repair_attempts:
            return OrchestrationEscalationReason.REPAIR_BUDGET_EXHAUSTED
        return None

    @staticmethod
    def _paths_covered(paths: tuple[str, ...], roots: tuple[str, ...]) -> bool:
        return all(
            any(path == root or path.startswith(f"{root.rstrip('/')}/") for root in roots)
            for path in paths
        )
