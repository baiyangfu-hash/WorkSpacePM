"""PM front desk: record, confirm and file inbox items without touching the current focus."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from auto_pm.change.change_service import ChangeService
from auto_pm.change.constants import SpecViolationError, validate_domain, validate_impact_scope
from auto_pm.core.workspace_context_service import WorkspaceContextError, WorkspaceContextService

from auto_pm.application.core.paths import get_monitoring_paths
from auto_pm.contracts.intake import (
    DEFAULT_IMPACT_SCOPE,
    OPEN_INTAKE_STATUSES,
    ChangeAction,
    IntakeClassification,
    IntakeItem,
    IntakeKind,
    IntakeStatus,
    TriageTicket,
    UrgentCriterion,
    parse_evidence,
)
from auto_pm.domain.change.decision_service import DecisionError, DecisionService
from auto_pm.infrastructure.continuity_store import ContinuityStoreError
from auto_pm.infrastructure.git_timeout import run_git_bounded_text
from auto_pm.infrastructure.intake_store import IntakeStore

_STACK_DOMAINS = {"plc": "PLC", "python": "SCPT"}
_LEDGER_OWNER = re.compile(r"TD-(?P<letters>[A-Z]+)(?P<digits>\d+)-\d+")


class PmIntakeError(RuntimeError):
    """Raised when an inbox action is not legally available."""


class PmIntakeService:
    """Validate and persist inbox items; recording never changes Mission, Work, Run or lease."""

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        store: IntakeStore | None = None,
        change_service: ChangeService | None = None,
    ) -> None:
        self._root = Path(workspace_root).resolve()
        self._store = store or IntakeStore(self._root)
        self._changes = change_service or ChangeService(str(self._root))

    def resolve_domain(self, project_id: str, explicit: str = "") -> str:
        """Return the technical domain: the explicit one, else the one the project stack implies."""

        if explicit:
            try:
                validate_domain(explicit)
            except SpecViolationError as error:
                raise PmIntakeError(str(error)) from error
            return explicit
        try:
            context = WorkspaceContextService(str(self._root)).resolve(
                project_id=project_id, start_path=self._root
            )
            stack = context.subject.stack
        except WorkspaceContextError:
            stack = "unknown"
        domain = _STACK_DOMAINS.get(stack.lower())
        if domain is None:
            raise PmIntakeError(
                f"无法从项目技术栈推断技术领域（栈: {stack}），请显式给出 --domain"
            )
        return domain

    def classify(
        self,
        project_id: str,
        *,
        kind: IntakeKind,
        change_action: ChangeAction | None,
        domain: str,
        impact_scope: Sequence[str],
    ) -> IntakeClassification:
        """Build a classification whose domain and scope are legal for a change request."""

        scope = tuple(impact_scope) or DEFAULT_IMPACT_SCOPE
        try:
            classification = IntakeClassification(
                kind=kind,
                change_action=change_action,
                domain=self.resolve_domain(project_id, domain),
                impact_scope=scope,
            )
            validate_impact_scope(list(classification.impact_scope))
        except (ValueError, SpecViolationError) as error:
            raise PmIntakeError(str(error)) from error
        return classification

    def propose(
        self,
        *,
        request_id: str,
        project_id: str,
        title: str,
        classification: IntakeClassification,
        ticket: TriageTicket,
        proposed_by: str,
    ) -> tuple[IntakeItem, bool]:
        """Record one proposed item; the second value is False when this was a replay."""

        try:
            self._changes.next_change_number(project_id, classification.domain)
        except ValueError as error:
            raise PmIntakeError(str(error)) from error
        self._check_evidence_files(ticket)
        self._check_evidence_refs(ticket, project_id)
        if (
            ticket.urgent_criterion is UrgentCriterion.SAFETY
            and "SAFE" not in classification.impact_scope
        ):
            raise PmIntakeError("安全类紧急事项的影响范围必须包含 SAFE")
        try:
            return self._store.add_item(
                request_id=request_id,
                project_id=project_id,
                title=title,
                classification=classification,
                ticket=ticket,
                proposed_by=proposed_by,
            )
        except ContinuityStoreError as error:
            raise PmIntakeError(str(error)) from error

    def confirm(
        self,
        item_id: str,
        *,
        ticket_hash: str,
        approver: str,
        approval_evidence_ref: str,
        note: str = "",
    ) -> IntakeItem:
        """Record the human confirmation of the exact ticket content."""

        return self._decide(
            item_id, IntakeStatus.CONFIRMED, ticket_hash, approver, approval_evidence_ref, note
        )

    def reject(
        self,
        item_id: str,
        *,
        ticket_hash: str,
        approver: str,
        approval_evidence_ref: str,
        note: str = "",
    ) -> IntakeItem:
        """Record the human rejection of the exact ticket content."""

        return self._decide(
            item_id, IntakeStatus.REJECTED, ticket_hash, approver, approval_evidence_ref, note
        )

    def get(self, item_id: str) -> IntakeItem:
        """Read one item."""

        try:
            return self._store.get_item(item_id)
        except ContinuityStoreError as error:
            raise PmIntakeError(str(error)) from error

    def list_items(
        self,
        project_id: str,
        statuses: tuple[IntakeStatus, ...] = OPEN_INTAKE_STATUSES,
    ) -> tuple[IntakeItem, ...]:
        """List the items of one project in the order they were proposed."""

        try:
            return self._store.list_items(project_id, statuses)
        except ContinuityStoreError as error:
            raise PmIntakeError(str(error)) from error

    def plan_classification(
        self,
        project_id: str,
        *,
        request_id: str,
        kind: IntakeKind | None,
        change_action: ChangeAction | None,
        domain: str,
        impact_scope: Sequence[str],
        inbox_id: str,
    ) -> tuple[IntakeClassification | None, str]:
        """Decide how a plan request is classified: from its inbox item, its options or its binding.

        Returns ``(None, "")`` only when nothing classifies the request, which the caller must refuse.
        """

        try:
            filed, resolved_item_id = self._store.resolve_planning_classification(
                request_id, project_id, None, inbox_id
            )
        except ContinuityStoreError as error:
            raise PmIntakeError(str(error)) from error
        if filed is not None:
            if (
                (kind is not None and kind is not filed.kind)
                or (change_action is not None and change_action is not filed.change_action)
                or (domain and domain != filed.domain)
                or (impact_scope and tuple(impact_scope) != filed.impact_scope)
            ):
                raise PmIntakeError(
                    "命令行分类与收件箱条目的分类不一致"
                    if resolved_item_id
                    else "PlanningDraft 已绑定的分类与命令行分类不一致"
                )
            return filed, resolved_item_id
        if kind is None:
            return None, ""
        return (
            self.classify(
                project_id,
                kind=kind,
                change_action=change_action,
                domain=domain,
                impact_scope=impact_scope,
            ),
            "",
        )

    def _decide(
        self,
        item_id: str,
        status: IntakeStatus,
        ticket_hash: str,
        approver: str,
        approval_evidence_ref: str,
        note: str,
    ) -> IntakeItem:
        try:
            DecisionService.validate_planning_approval(
                approver, ticket_hash, approval_evidence_ref
            )
            return self._store.decide_item(
                item_id,
                status=status,
                ticket_hash=ticket_hash,
                decided_by=approver.strip(),
                decision_ref=approval_evidence_ref,
                note=note,
            )
        except (DecisionError, ContinuityStoreError) as error:
            raise PmIntakeError(str(error)) from error

    def _check_evidence_files(self, ticket: TriageTicket) -> None:
        for entry in ticket.evidence:
            kind, value = parse_evidence(entry)
            if kind != "file":
                continue
            try:
                target = (self._root / value).resolve(strict=True)
                target.relative_to(self._root)
                regular_file = target.is_file()
            except ValueError as error:
                raise PmIntakeError(f"取证文件位于工作空间之外: {value}") from error
            except (OSError, RuntimeError) as error:
                raise PmIntakeError(f"取证文件不存在或无法证明为普通文件: {value}") from error
            if not regular_file:
                raise PmIntakeError(f"取证目标不是普通文件: {value}")

    def _check_evidence_refs(self, ticket: TriageTicket, project_id: str) -> None:
        """Read-only proof that the cited change request, ledger row and commit exist (TD-SW008-072); ``cmd`` stays a claim."""

        for entry in ticket.evidence:
            kind, value = parse_evidence(entry)
            if kind == "chg":
                self._require_change(value, project_id)
            elif kind == "commit":
                self._require_commit(value)
            elif kind == "ledger":
                self._require_ledger_row(value, project_id)

    def _require_change(self, number: str, project_id: str) -> None:
        try:
            found = self._changes.get_change_request(number, project_id) or self._changes.get_change_request(number)
        except (OSError, ValueError) as error:
            raise PmIntakeError(f"取证变更单无法核验: {number}") from error
        if found is None:
            raise PmIntakeError(f"取证变更单不存在: {number}")

    def _require_commit(self, name: str) -> None:
        result = run_git_bounded_text(
            ["git", "-C", str(self._root), "cat-file", "-e", f"{name}^{{commit}}"],
            default_timeout=30.0,
            error_cls=PmIntakeError,
            where=self._root,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise PmIntakeError(f"取证提交不存在于本仓库: {name}")

    def _require_ledger_row(self, ledger_id: str, project_id: str) -> None:
        row = re.compile(rf"^\|\s*{re.escape(ledger_id)}\s*\|", re.MULTILINE)
        for directory in self._ledger_directories(project_id, ledger_id):
            for path in sorted(directory.rglob("*.md")):
                try:
                    text = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError) as error:
                    raise PmIntakeError(f"取证台账无法读取: {path.name}") from error
                if row.search(text):
                    return
        raise PmIntakeError(f"取证台账行不存在: {ledger_id}")

    def _ledger_directories(self, project_id: str, ledger_id: str) -> list[Path]:
        """The ``04_监控/02_整改项`` (or legacy ``11_监控/02_整改项``) folders that can hold the row: the subject project's, the control project's and the owner's.

        The owner is the registered project a ``TD-SW008-066`` style id names (``SW008`` = ``SW-<year>-008``).
        """

        service = WorkspaceContextService(str(self._root))
        directories: list[Path] = []
        try:
            context = service.resolve(project_id=project_id, start_path=self._root)
            candidates = [project_id, context.control_project_id, *self._ledger_owner_projects(service, ledger_id)]
            for item in dict.fromkeys(identifier for identifier in candidates if identifier):
                subject = service.resolve(project_id=item, start_path=self._root).subject
                for candidate in get_monitoring_paths(str(self._root / subject.path), "02_整改项"):
                    directory = Path(candidate).resolve()
                    if directory.is_dir() and directory not in directories:
                        directories.append(directory)
        except WorkspaceContextError as error:
            raise PmIntakeError(f"取证台账所在项目无法确定: {error}") from error
        return directories

    @staticmethod
    def _ledger_owner_projects(service: WorkspaceContextService, ledger_id: str) -> list[str]:
        named = _LEDGER_OWNER.fullmatch(ledger_id)
        if named is None:
            return []
        wanted = (named.group("letters"), named.group("digits"))
        owners: list[str] = []
        for identifier in service.registered_project_ids():
            parts = identifier.split("-")
            if len(parts) == 3 and (parts[0], parts[2]) == wanted:
                owners.append(identifier)
        return owners
