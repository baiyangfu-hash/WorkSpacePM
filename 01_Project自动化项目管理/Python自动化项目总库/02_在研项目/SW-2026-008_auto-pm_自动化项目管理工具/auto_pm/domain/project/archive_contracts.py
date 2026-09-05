"""Fail-closed domain contracts for reversible project archive operations.

This module deliberately contains no filesystem or repository mutation.  It
defines the facts an application service must prove before it may use the
NG-WP-04 transaction boundary to archive or restore a project.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
from typing import Protocol

__all__ = [
    "ARCHIVE_COMPENSATION_ORDER",
    "ARCHIVE_EXECUTION_STEPS",
    "ARCHIVE_FAILURE_MATRIX",
    "ARCHIVE_TEST_MATRIX",
    "RESTORE_EXECUTION_STEPS",
    "ArchiveAuthorization",
    "ArchiveContractError",
    "ArchiveErrorCode",
    "ArchiveExecutionPort",
    "ArchiveFailureCase",
    "ArchiveOperation",
    "ArchivePlan",
    "ArchivePreflightFacts",
    "ArchiveRequest",
    "ArchiveState",
    "ArchiveStep",
    "ArchiveTestCase",
    "ChangeTransactionPort",
    "DuplicateRequestState",
    "build_archive_plan",
    "canonical_project_path",
    "transition_archive_state",
]

_ARCHIVE_CODE = re.compile(r"^ARC-[0-9]{8}-[0-9]{3}$")


class ArchiveOperation(str, Enum):
    """Only reversible lifecycle capabilities exposed by the contract."""

    ARCHIVE = "archive"
    RESTORE = "restore"


class ArchiveState(str, Enum):
    """Auditable state of one archive or restore request."""

    REQUESTED = "requested"
    AUTHORIZED = "authorized"
    VALIDATED = "validated"
    LOCKED = "locked"
    MOVED = "moved"
    PM_SESSION_UPDATED = "pm_session_updated"
    LEDGER_UPDATED = "ledger_updated"
    DATABASE_UPDATED = "database_updated"
    SCANNER_REFRESHED = "scanner_refreshed"
    COMPLETED = "completed"
    COMPENSATING = "compensating"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class ArchiveStep(str, Enum):
    """Required effect order after every read-only gate has passed."""

    ACQUIRE_LOCK = "acquire_lock"
    ALLOCATE_ARCHIVE_CODE = "allocate_archive_code"
    MOVE_DIRECTORY = "move_directory"
    UPDATE_PM_SESSION = "update_pm_session"
    UPDATE_LEDGER = "update_ledger"
    UPDATE_DATABASE = "update_database"
    REFRESH_SCANNER = "refresh_scanner"


class DuplicateRequestState(str, Enum):
    """Result of looking up the immutable request id."""

    NEW = "new"
    SAME_COMPLETED = "same_completed"
    CONFLICT = "conflict"


class ArchiveErrorCode(str, Enum):
    """Stable machine-readable reasons for refusing or stopping an operation."""

    INVALID_REQUEST = "invalid_request"
    HARD_DELETE_FORBIDDEN = "hard_delete_forbidden"
    PROTECTED_PROJECT = "protected_project"
    AUTHORIZATION_QUERY_FAILED = "authorization_query_failed"
    NOT_AUTHORIZED = "not_authorized"
    CHG_QUERY_FAILED = "chg_query_failed"
    OPEN_CHANGE = "open_change"
    GIT_UNAVAILABLE = "git_unavailable"
    GIT_NON_ZERO = "git_non_zero"
    GIT_DIRTY = "git_dirty"
    LEDGER_DAMAGED = "ledger_damaged"
    PATH_ESCAPE = "path_escape"
    LINK_ANOMALY = "link_anomaly"
    SOURCE_MISSING = "source_missing"
    DESTINATION_CONFLICT = "destination_conflict"
    ARCHIVE_CODE_INVALID = "archive_code_invalid"
    DUPLICATE_REQUEST = "duplicate_request"
    CONCURRENCY_CONFLICT = "concurrency_conflict"
    INVALID_STATE_TRANSITION = "invalid_state_transition"
    EXECUTION_FAILED = "execution_failed"
    COMPENSATION_FAILED = "compensation_failed"


class ArchiveContractError(ValueError):
    """A fail-closed contract violation with a stable error code."""

    def __init__(self, code: ArchiveErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ArchiveRequest:
    """Immutable command identity and intended contained paths."""

    request_id: str
    project_id: str
    change_id: str
    decision_id: str
    operation: ArchiveOperation
    source_path: str
    destination_path: str
    actor: str
    archive_code: str = ""


@dataclass(frozen=True, slots=True)
class ArchiveAuthorization:
    """Immutable disposition read from the NG-WP-05/06 decision boundary."""

    query_succeeded: bool
    decision_id: str
    approved_operation: ArchiveOperation
    approved_project_id: str
    approved_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ArchivePreflightFacts:
    """Read-only facts that an adapter must collect before any mutation."""

    authorization: ArchiveAuthorization
    chg_query_succeeded: bool
    open_change_ids: tuple[str, ...]
    git_available: bool
    git_returncode: int
    git_clean: bool
    ledger_readable: bool
    ledger_valid: bool
    source_exists: bool
    destination_exists: bool
    source_link_anomaly: bool
    destination_link_anomaly: bool
    lock_acquired: bool
    duplicate_request: DuplicateRequestState = DuplicateRequestState.NEW


@dataclass(frozen=True, slots=True)
class ArchivePlan:
    """Validated execution recipe consumed by an application adapter."""

    request: ArchiveRequest
    steps: tuple[ArchiveStep, ...]
    compensation_order: tuple[ArchiveStep, ...]
    initial_state: ArchiveState
    idempotent_replay: bool = False


@dataclass(frozen=True, slots=True)
class ArchiveFailureCase:
    """Normative failure response for implementation and review."""

    trigger: str
    code: ArchiveErrorCode
    side_effects_allowed: bool
    required_state: ArchiveState


@dataclass(frozen=True, slots=True)
class ArchiveTestCase:
    """Normative verification item that NG-WP-08 must preserve."""

    case_id: str
    proves: str
    expected_code: ArchiveErrorCode | None


class ChangeTransactionPort(Protocol):
    """Narrow NG-WP-04 transaction surface required by archive execution."""

    def backup_file(self, path: str) -> object: ...

    def track_created_file(self, path: str) -> None: ...

    def commit(self) -> None: ...

    def rollback(self, reason: str = "") -> None: ...


class ArchiveExecutionPort(Protocol):
    """Application boundary; implementations must accept only a validated plan."""

    def execute(self, plan: ArchivePlan, transaction: ChangeTransactionPort) -> ArchiveState: ...


ARCHIVE_EXECUTION_STEPS: tuple[ArchiveStep, ...] = (
    ArchiveStep.ACQUIRE_LOCK,
    ArchiveStep.ALLOCATE_ARCHIVE_CODE,
    ArchiveStep.MOVE_DIRECTORY,
    ArchiveStep.UPDATE_PM_SESSION,
    ArchiveStep.UPDATE_LEDGER,
    ArchiveStep.UPDATE_DATABASE,
    ArchiveStep.REFRESH_SCANNER,
)

RESTORE_EXECUTION_STEPS: tuple[ArchiveStep, ...] = (
    ArchiveStep.ACQUIRE_LOCK,
    ArchiveStep.MOVE_DIRECTORY,
    ArchiveStep.UPDATE_PM_SESSION,
    ArchiveStep.UPDATE_LEDGER,
    ArchiveStep.UPDATE_DATABASE,
    ArchiveStep.REFRESH_SCANNER,
)

# Effects unwind in strict reverse order.  The lock and code allocation are
# coordination facts rather than durable effects, so they are not compensated.
ARCHIVE_COMPENSATION_ORDER: tuple[ArchiveStep, ...] = (
    ArchiveStep.REFRESH_SCANNER,
    ArchiveStep.UPDATE_DATABASE,
    ArchiveStep.UPDATE_LEDGER,
    ArchiveStep.UPDATE_PM_SESSION,
    ArchiveStep.MOVE_DIRECTORY,
)

_ALLOWED_TRANSITIONS: dict[ArchiveState, frozenset[ArchiveState]] = {
    ArchiveState.REQUESTED: frozenset({ArchiveState.AUTHORIZED, ArchiveState.FAILED}),
    ArchiveState.AUTHORIZED: frozenset({ArchiveState.VALIDATED, ArchiveState.FAILED}),
    ArchiveState.VALIDATED: frozenset({ArchiveState.LOCKED, ArchiveState.FAILED}),
    ArchiveState.LOCKED: frozenset({ArchiveState.MOVED, ArchiveState.FAILED}),
    ArchiveState.MOVED: frozenset({ArchiveState.PM_SESSION_UPDATED, ArchiveState.COMPENSATING}),
    ArchiveState.PM_SESSION_UPDATED: frozenset(
        {ArchiveState.LEDGER_UPDATED, ArchiveState.COMPENSATING}
    ),
    ArchiveState.LEDGER_UPDATED: frozenset(
        {ArchiveState.DATABASE_UPDATED, ArchiveState.COMPENSATING}
    ),
    ArchiveState.DATABASE_UPDATED: frozenset(
        {ArchiveState.SCANNER_REFRESHED, ArchiveState.COMPENSATING}
    ),
    ArchiveState.SCANNER_REFRESHED: frozenset({ArchiveState.COMPLETED, ArchiveState.COMPENSATING}),
    ArchiveState.COMPENSATING: frozenset({ArchiveState.ROLLED_BACK, ArchiveState.FAILED}),
    ArchiveState.COMPLETED: frozenset(),
    ArchiveState.ROLLED_BACK: frozenset(),
    ArchiveState.FAILED: frozenset(),
}


def canonical_project_path(path: str) -> str:
    """Return one canonical POSIX project-relative path or reject it."""
    if not path or "\\" in path or any(character in path for character in "*?[]"):
        raise ArchiveContractError(ArchiveErrorCode.PATH_ESCAPE, f"非法项目路径: {path!r}")
    candidate = PurePosixPath(path)
    if (
        candidate.is_absolute()
        or candidate.anchor
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        raise ArchiveContractError(ArchiveErrorCode.PATH_ESCAPE, f"非法项目路径: {path!r}")
    canonical = candidate.as_posix()
    if canonical != path:
        raise ArchiveContractError(ArchiveErrorCode.PATH_ESCAPE, f"非规范项目路径: {path!r}")
    return canonical


def transition_archive_state(current: ArchiveState, target: ArchiveState) -> ArchiveState:
    """Apply one legal state transition, rejecting shortcuts and resurrection."""
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise ArchiveContractError(
            ArchiveErrorCode.INVALID_STATE_TRANSITION,
            f"非法归档状态迁移: {current.value} -> {target.value}",
        )
    return target


def _validate_identity(request: ArchiveRequest) -> None:
    values = (
        request.request_id,
        request.project_id,
        request.change_id,
        request.decision_id,
        request.actor,
    )
    if any(not value or value.strip() != value for value in values):
        raise ArchiveContractError(ArchiveErrorCode.INVALID_REQUEST, "请求标识不能为空或带空白")


def _validate_authorization(request: ArchiveRequest, auth: ArchiveAuthorization) -> None:
    if not auth.query_succeeded:
        raise ArchiveContractError(
            ArchiveErrorCode.AUTHORIZATION_QUERY_FAILED, "审批决策查询失败，拒绝操作"
        )
    try:
        approved_paths = tuple(canonical_project_path(path) for path in auth.approved_paths)
    except ArchiveContractError as exc:
        raise ArchiveContractError(ArchiveErrorCode.NOT_AUTHORIZED, "审批路径白名单非法") from exc
    if len(approved_paths) != len(set(approved_paths)):
        raise ArchiveContractError(ArchiveErrorCode.NOT_AUTHORIZED, "审批路径白名单存在重复项")
    requested_paths = {request.source_path, request.destination_path}
    if (
        auth.decision_id != request.decision_id
        or auth.approved_operation is not request.operation
        or auth.approved_project_id != request.project_id
        or not requested_paths.issubset(set(approved_paths))
    ):
        raise ArchiveContractError(ArchiveErrorCode.NOT_AUTHORIZED, "请求超出不可变审批范围")


def build_archive_plan(
    request: ArchiveRequest,
    facts: ArchivePreflightFacts,
    protected_project_ids: frozenset[str] = frozenset({"SW-2026-008", "SYS-2026-001"}),
) -> ArchivePlan:
    """Validate all gates and return a mutation plan only when every fact is safe."""
    _validate_identity(request)
    source = canonical_project_path(request.source_path)
    destination = canonical_project_path(request.destination_path)
    if source == destination:
        raise ArchiveContractError(ArchiveErrorCode.INVALID_REQUEST, "源路径与目标路径相同")
    if request.project_id in protected_project_ids:
        raise ArchiveContractError(ArchiveErrorCode.PROTECTED_PROJECT, "受保护项目禁止归档或恢复")
    if request.operation is ArchiveOperation.RESTORE:
        if not _ARCHIVE_CODE.fullmatch(request.archive_code):
            raise ArchiveContractError(
                ArchiveErrorCode.ARCHIVE_CODE_INVALID, "恢复必须引用有效归档编号"
            )
    elif request.archive_code and not _ARCHIVE_CODE.fullmatch(request.archive_code):
        raise ArchiveContractError(ArchiveErrorCode.ARCHIVE_CODE_INVALID, "预分配归档编号格式非法")

    _validate_authorization(request, facts.authorization)
    if not facts.chg_query_succeeded:
        raise ArchiveContractError(ArchiveErrorCode.CHG_QUERY_FAILED, "变更单查询失败")
    if facts.open_change_ids:
        raise ArchiveContractError(ArchiveErrorCode.OPEN_CHANGE, "存在未闭环变更单")
    if not facts.git_available:
        raise ArchiveContractError(ArchiveErrorCode.GIT_UNAVAILABLE, "Git 不可用")
    if facts.git_returncode != 0:
        raise ArchiveContractError(ArchiveErrorCode.GIT_NON_ZERO, "Git 门禁返回非零")
    if not facts.git_clean:
        raise ArchiveContractError(ArchiveErrorCode.GIT_DIRTY, "项目 Git 状态不干净")
    if not facts.ledger_readable or not facts.ledger_valid:
        raise ArchiveContractError(ArchiveErrorCode.LEDGER_DAMAGED, "归档台账不可读或已损坏")
    if facts.source_link_anomaly or facts.destination_link_anomaly:
        raise ArchiveContractError(ArchiveErrorCode.LINK_ANOMALY, "路径包含链接或 reparse 异常")
    if facts.duplicate_request is DuplicateRequestState.CONFLICT:
        raise ArchiveContractError(ArchiveErrorCode.DUPLICATE_REQUEST, "请求标识已用于不同操作")
    if facts.duplicate_request is DuplicateRequestState.SAME_COMPLETED:
        return ArchivePlan(
            request=request,
            steps=(),
            compensation_order=(),
            initial_state=ArchiveState.COMPLETED,
            idempotent_replay=True,
        )
    if not facts.source_exists:
        raise ArchiveContractError(ArchiveErrorCode.SOURCE_MISSING, "源项目不存在")
    if facts.destination_exists:
        raise ArchiveContractError(ArchiveErrorCode.DESTINATION_CONFLICT, "目标路径已存在")
    if not facts.lock_acquired:
        raise ArchiveContractError(ArchiveErrorCode.CONCURRENCY_CONFLICT, "未取得归档互斥锁")
    return ArchivePlan(
        request=request,
        steps=(
            ARCHIVE_EXECUTION_STEPS
            if request.operation is ArchiveOperation.ARCHIVE
            else RESTORE_EXECUTION_STEPS
        ),
        compensation_order=ARCHIVE_COMPENSATION_ORDER,
        initial_state=ArchiveState.VALIDATED,
    )


ARCHIVE_FAILURE_MATRIX: tuple[ArchiveFailureCase, ...] = (
    ArchiveFailureCase(
        "authorization query error",
        ArchiveErrorCode.AUTHORIZATION_QUERY_FAILED,
        False,
        ArchiveState.FAILED,
    ),
    ArchiveFailureCase(
        "CHG query error", ArchiveErrorCode.CHG_QUERY_FAILED, False, ArchiveState.FAILED
    ),
    ArchiveFailureCase("Git missing", ArchiveErrorCode.GIT_UNAVAILABLE, False, ArchiveState.FAILED),
    ArchiveFailureCase("Git non-zero", ArchiveErrorCode.GIT_NON_ZERO, False, ArchiveState.FAILED),
    ArchiveFailureCase(
        "ledger damaged", ArchiveErrorCode.LEDGER_DAMAGED, False, ArchiveState.FAILED
    ),
    ArchiveFailureCase("path escape", ArchiveErrorCode.PATH_ESCAPE, False, ArchiveState.FAILED),
    ArchiveFailureCase("link anomaly", ArchiveErrorCode.LINK_ANOMALY, False, ArchiveState.FAILED),
    ArchiveFailureCase(
        "concurrency conflict", ArchiveErrorCode.CONCURRENCY_CONFLICT, False, ArchiveState.FAILED
    ),
    ArchiveFailureCase(
        "effect failure", ArchiveErrorCode.EXECUTION_FAILED, True, ArchiveState.COMPENSATING
    ),
    ArchiveFailureCase(
        "compensation failure", ArchiveErrorCode.COMPENSATION_FAILED, True, ArchiveState.FAILED
    ),
)

ARCHIVE_TEST_MATRIX: tuple[ArchiveTestCase, ...] = (
    ArchiveTestCase(
        "ARC-001",
        "archive and restore are the only capabilities",
        ArchiveErrorCode.HARD_DELETE_FORBIDDEN,
    ),
    ArchiveTestCase("ARC-002", "protected project rejection", ArchiveErrorCode.PROTECTED_PROJECT),
    ArchiveTestCase("ARC-003", "immutable decision scope", ArchiveErrorCode.NOT_AUTHORIZED),
    ArchiveTestCase("ARC-004", "CHG query failure is closed", ArchiveErrorCode.CHG_QUERY_FAILED),
    ArchiveTestCase(
        "ARC-005", "Git missing and non-zero are closed", ArchiveErrorCode.GIT_UNAVAILABLE
    ),
    ArchiveTestCase("ARC-006", "damaged ledger is closed", ArchiveErrorCode.LEDGER_DAMAGED),
    ArchiveTestCase("ARC-007", "path and link containment", ArchiveErrorCode.PATH_ESCAPE),
    ArchiveTestCase("ARC-008", "duplicate request semantics", ArchiveErrorCode.DUPLICATE_REQUEST),
    ArchiveTestCase(
        "ARC-009", "lock precedes code allocation and move", ArchiveErrorCode.CONCURRENCY_CONFLICT
    ),
    ArchiveTestCase("ARC-010", "effects compensate in reverse order", None),
    ArchiveTestCase(
        "ARC-011", "restore requires exact archive code", ArchiveErrorCode.ARCHIVE_CODE_INVALID
    ),
    ArchiveTestCase(
        "ARC-012", "state machine rejects shortcuts", ArchiveErrorCode.INVALID_STATE_TRANSITION
    ),
)
