"""Machine-verifiable, bounded implementation card contract."""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class IntentType(StrEnum):
    FEATURE = "FEATURE"
    BUG_FIX = "BUG_FIX"
    RECOVERY = "RECOVERY"
    GOVERNANCE = "GOVERNANCE"
    DOCU = "DOCU"


class CardState(StrEnum):
    DRAFT = "DRAFT"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"
    DISPATCHED = "DISPATCHED"
    VERIFYING = "VERIFYING"
    ACCEPTED = "ACCEPTED"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


NEXT_STATES: dict[CardState, frozenset[CardState]] = {
    CardState.DRAFT: frozenset({CardState.REVIEWED, CardState.REJECTED, CardState.CANCELLED}),
    CardState.REVIEWED: frozenset({CardState.APPROVED, CardState.REJECTED, CardState.CANCELLED}),
    CardState.APPROVED: frozenset({CardState.DISPATCHED, CardState.REJECTED, CardState.CANCELLED}),
    CardState.DISPATCHED: frozenset({CardState.VERIFYING, CardState.CANCELLED}),
    CardState.VERIFYING: frozenset({CardState.ACCEPTED, CardState.REJECTED}),
    CardState.ACCEPTED: frozenset({CardState.CLOSED}),
    CardState.CLOSED: frozenset(),
    CardState.REJECTED: frozenset(),
    CardState.CANCELLED: frozenset(),
}


def safe_relative_path(value: str) -> str:
    """Reject traversal, aliasing, shell-like and platform-dependent paths."""
    if not value or value != value.strip() or "\\" in value or any(
        character in value for character in ':<>"|?*'
    ) or any(
        ord(character) < 32 for character in value
    ):
        raise ValueError("path must be canonical relative POSIX text")
    parts = value.split("/")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{n}" for n in range(1, 10)),
                *(f"LPT{n}" for n in range(1, 10))}
    if re.match(r"^[A-Za-z]:", value) or any(
        part in {"", ".", ".."} or part != part.rstrip(" .")
        or part.split(".", 1)[0].upper() in reserved for part in parts
    ):
        raise ValueError("path must not be absolute, aliased or traversing")
    path = PurePosixPath(value)
    if path.is_absolute() or str(path) != value:
        raise ValueError("path must be canonical relative POSIX text")
    return value


class UserStory(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    story: str = Field(min_length=1)
    acceptance_criteria: tuple[str, ...] = Field(min_length=1)

    @field_validator("story")
    @classmethod
    def _story(cls, value: str) -> str:
        if "TODO" in value or not value.strip():
            raise ValueError("user story must be completed")
        if not (re.search(r"作为.+我希望.+以便", value) or re.search(r"As .+, I want .+ so that", value, re.I)):
            raise ValueError("user story must state role, need and benefit")
        return value

    @field_validator("acceptance_criteria")
    @classmethod
    def _criteria(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() or "TODO" in item for item in value):
            raise ValueError("acceptance criteria must be completed")
        return value


class GateDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = Field(min_length=1)
    cwd: str
    argv: tuple[str, ...] = Field(min_length=1)
    expected_exit_code: int = 0
    coverage_targets: tuple[str, ...] = Field(min_length=1)

    @field_validator("cwd")
    @classmethod
    def _cwd(cls, value: str) -> str:
        return safe_relative_path(value)

    @field_validator("coverage_targets")
    @classmethod
    def _targets(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("duplicate coverage targets")
        return tuple(safe_relative_path(item) for item in value)

    @field_validator("argv")
    @classmethod
    def _argv(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item or item != item.strip() or "\x00" in item or "\n" in item for item in value):
            raise ValueError("argv must contain canonical tokens")
        if value[0].lower() in {"sh", "bash", "cmd", "cmd.exe", "powershell", "pwsh"}:
            raise ValueError("shell execution is forbidden")
        if any(item in {"-c", "/c", "-Command", "-EncodedCommand"} for item in value[1:]):
            raise ValueError("shell command strings are forbidden")
        return value


class StopLines(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    max_runs: int = Field(ge=1, le=20)
    max_healing_attempts: int = Field(ge=0, le=20)
    deadline_utc: str = Field(min_length=1)
    quota_stop_remaining_percent: int = Field(ge=0, le=100)

    @field_validator("deadline_utc")
    @classmethod
    def _deadline(cls, value: str) -> str:
        from datetime import datetime

        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("deadline_utc must be ISO 8601") from error
        if parsed.tzinfo is None:
            raise ValueError("deadline_utc must include timezone")
        return value


class Outcomes(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    normal: str = Field(min_length=1)
    small_problem: str = Field(min_length=1)
    non_blocking: str = Field(min_length=1)
    blocking: str = Field(min_length=1)


class EvidenceMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    decision_id: str = Field(min_length=1)
    work_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    checkpoint_id: str = Field(min_length=1)
    final_commit: str = Field(min_length=1)


class Boundaries(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    merge: Literal["SEPARATE_APPROVAL"]
    push: Literal["SEPARATE_APPROVAL"]
    deploy: Literal["SEPARATE_APPROVAL"]
    release: Literal["SEPARATE_APPROVAL"]


class ImplementationCard(BaseModel):
    """The card is data, never a substitute for canonical authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["implementation_card.v1"] = "implementation_card.v1"
    card_id: str = Field(pattern=r"^[A-Z][A-Z0-9-]{2,127}$")
    project_id: str = Field(min_length=1)
    wbs_item_id: str = Field(pattern=r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*$")
    milestone_id: str = Field(pattern=r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*$")
    source_refs: tuple[str, ...] = Field(min_length=1)
    intent_type: IntentType
    state: CardState = CardState.DRAFT
    state_history: tuple[CardState, ...] = (CardState.DRAFT,)
    user_stories: tuple[UserStory, ...] = ()
    problem_statement: str = ""
    acceptance_criteria: tuple[str, ...] = ()
    base_commit: str
    candidate_policy: Literal["ISOLATED"] = "ISOLATED"
    worktree_path: str
    owned_paths: tuple[str, ...]
    commit_evidence_paths: tuple[str, ...]
    non_goals: tuple[str, ...]
    gates: tuple[GateDefinition, ...]
    stop_lines: StopLines
    outcomes: Outcomes
    evidence: EvidenceMap
    boundaries: Boundaries
    approval_by: str = ""
    approval_evidence: str = ""

    @field_validator("base_commit")
    @classmethod
    def _base(cls, value: str) -> str:
        if re.fullmatch(r"[0-9a-f]{40}", value) is None:
            raise ValueError("base_commit must be an immutable full SHA")
        return value

    @field_validator("owned_paths", "commit_evidence_paths")
    @classmethod
    def _authorized_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or len(value) != len(set(value)):
            raise ValueError("authorized path groups must be nonempty and unique")
        return tuple(safe_relative_path(item) for item in value)

    @field_validator("source_refs")
    @classmethod
    def _sources(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("source_refs must be unique")
        wbs_count = 0
        paths: set[str] = set()
        for item in value:
            kind, separator, path = item.partition(":")
            if not separator or kind not in {"WBS", "FILE"}:
                raise ValueError("source_refs require WBS: or FILE: path references")
            safe_relative_path(path)
            if path.split("/", 1)[0] in {".git", ".agents", ".auto-pm"}:
                raise ValueError("source_refs must point to project source documents")
            if path in paths:
                raise ValueError("source_refs must not alias the same path")
            paths.add(path)
            wbs_count += kind == "WBS"
        if wbs_count != 1:
            raise ValueError("source_refs require exactly one canonical WBS reference")
        return value

    @model_validator(mode="after")
    def _intent(self) -> Self:
        if set(self.owned_paths) & set(self.commit_evidence_paths):
            raise ValueError("owned_paths and commit_evidence_paths must not overlap")
        if not self.state_history or self.state_history[0] is not CardState.DRAFT or self.state_history[-1] is not self.state:
            raise ValueError("state history must begin at DRAFT and end at current state")
        if any(later not in NEXT_STATES[earlier] for earlier, later in zip(self.state_history, self.state_history[1:], strict=False)):
            raise ValueError("state history contains an illegal jump")
        if self.intent_type is IntentType.FEATURE:
            if (not self.user_stories and self.state is not CardState.DRAFT) or self.problem_statement:
                raise ValueError("FEATURE requires stories and excludes problem statement")
        elif self.user_stories or (
            self.state is not CardState.DRAFT
            and (not self.problem_statement.strip() or "TODO" in self.problem_statement)
        ):
            raise ValueError("non-FEATURE requires problem statement and excludes stories")
        if self.state in {CardState.APPROVED, CardState.DISPATCHED, CardState.VERIFYING,
                          CardState.ACCEPTED, CardState.CLOSED} and (
            not self.approval_by.strip() or not self.approval_evidence.strip()
        ):
            raise ValueError("approved card requires external approval evidence")
        return self

    @property
    def authorized_paths(self) -> tuple[str, ...]:
        """Return the exact product plus commit-evidence authorization boundary."""
        return (*self.owned_paths, *self.commit_evidence_paths)

    def require_complete(self) -> None:
        """All execution fields must be explicit before review or dispatch."""
        if self.intent_type is IntentType.FEATURE and not self.user_stories:
            raise ValueError("FEATURE requires a completed user story")
        if self.intent_type is not IntentType.FEATURE and (
            self.user_stories or not self.problem_statement.strip() or "TODO" in self.problem_statement
        ):
            raise ValueError("problem statement is incomplete or stories are forbidden")
        values = (*self.acceptance_criteria, *self.non_goals, self.outcomes.normal,
                  self.outcomes.small_problem, self.outcomes.non_blocking, self.outcomes.blocking)
        if not self.acceptance_criteria or not self.non_goals or not self.gates:
            raise ValueError("acceptance criteria, non-goals and gates are required")
        if any(not item.strip() or "TODO" in item for item in values):
            raise ValueError("card contains incomplete TODO text")
        coverage = {target for gate in self.gates for target in gate.coverage_targets}
        if coverage != set(self.owned_paths):
            raise ValueError("gate coverage must exactly cover owned paths")
        if not self.worktree_path or not self.evidence.decision_id or not self.evidence.work_id or not self.evidence.run_id:
            raise ValueError("execution identity is incomplete")

    def require_terminal_evidence(self) -> None:
        """Checkpoint and commit identities become mandatory after execution."""
        if (
            "TODO" in self.evidence.checkpoint_id
            or re.fullmatch(r"[0-9a-f]{40}", self.evidence.final_commit) is None
        ):
            raise ValueError("checkpoint and final commit evidence must be explicit")

    def transition(self, state: CardState) -> ImplementationCard:
        if state not in NEXT_STATES[self.state]:
            raise ValueError(f"illegal card transition: {self.state} -> {state}")
        if state is CardState.APPROVED and (
            not self.approval_by.strip() or not self.approval_evidence.strip()
        ):
            raise ValueError("external approval evidence is required")
        if state not in {CardState.REJECTED, CardState.CANCELLED}:
            self.require_complete()
        return self.model_copy(update={"state": state, "state_history": (*self.state_history, state)})
