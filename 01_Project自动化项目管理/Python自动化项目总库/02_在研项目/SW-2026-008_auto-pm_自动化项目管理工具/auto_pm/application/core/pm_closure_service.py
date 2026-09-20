"""Recoverable PM closure preparation backed only by Continuity v2."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError


class PmClosureError(RuntimeError):
    """Raised when an accepted lineage cannot be prepared for safe closure."""


class ClosureState(StrEnum):
    """C05 exposes only the non-terminal state it owns."""

    PREPARED = "PREPARED"


class ClosureStepKind(StrEnum):
    """The next durable action without executing it."""

    CHANGE_SUBSTANCE = "CHANGE_SUBSTANCE"


class ClosureStepState(StrEnum):
    """C05 queues work but never advances a downstream step."""

    PENDING = "PENDING"


class ClosureItem(BaseModel):
    """Immutable accepted lineage captured for later closure stages."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    closure_id: str = Field(pattern=r"^CLOSURE-[A-F0-9]{24}$")
    mission_id: str = Field(min_length=1)
    work_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    checkpoint_id: str = Field(min_length=1)
    change_id: str = Field(pattern=r"^CHG-[A-Z0-9-]+$")
    decision_id: str = Field(pattern=r"^DEC-[A-Z0-9-]+$")
    state: ClosureState
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    version: int = Field(ge=1)
    created_at: AwareDatetime
    updated_at: AwareDatetime


class ClosureStep(BaseModel):
    """First recoverable closure step, initially pending and unattempted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: str = Field(pattern=r"^CSTEP-[A-F0-9]{24}$")
    closure_id: str = Field(pattern=r"^CLOSURE-[A-F0-9]{24}$")
    sequence: int = Field(ge=1)
    step_kind: ClosureStepKind
    state: ClosureStepState
    attempt_count: int = Field(ge=0)
    last_error: str | None = None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class ClosureOutboxItem(BaseModel):
    """Pending side-effect description committed with closure state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    outbox_id: str = Field(pattern=r"^OUTBOX-[A-F0-9]{24}$")
    closure_id: str = Field(pattern=r"^CLOSURE-[A-F0-9]{24}$")
    step_id: str = Field(pattern=r"^CSTEP-[A-F0-9]{24}$")
    artifact_kind: ClosureStepKind
    target_path: str = Field(min_length=1)
    payload: dict[str, Any]
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    published_at: AwareDatetime | None = None
    created_at: AwareDatetime


class ClosurePreparation(BaseModel):
    """One atomic C05 result returned identically on safe replay."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    closure: ClosureItem
    step: ClosureStep
    outbox: ClosureOutboxItem


class PmClosureService:
    """Prepare the accepted v2 lineage without performing external effects."""

    def __init__(
        self,
        workspace_root: str | Path,
        now: Callable[[], datetime] | None = None,
        *,
        store: ContinuityStore | None = None,
    ) -> None:
        self._store = store or ContinuityStore(workspace_root)
        self._now = now or (lambda: datetime.now(UTC))

    def initialize(self, tool_version: str = "dev") -> None:
        """Install the additive closure tables through the canonical Store."""

        try:
            self._store.initialize(self._timestamp(), tool_version)
        except ContinuityStoreError as error:
            raise PmClosureError(str(error)) from error

    def prepare_closure(
        self,
        mission_id: str,
        *,
        idempotency_key: str,
    ) -> ClosurePreparation:
        """Atomically persist PREPARED state, its first step, outbox and event."""

        try:
            payload = self._store.prepare_closure(
                mission_id,
                idempotency_key,
                self._timestamp(),
            )
            return self._decode(payload)
        except (ContinuityStoreError, ValueError, TypeError, json.JSONDecodeError) as error:
            raise PmClosureError(str(error)) from error

    def get(self, closure_id: str) -> ClosurePreparation:
        """Read a prepared closure without changing state or publishing the outbox."""

        try:
            return self._decode(self._store.get_closure_preparation(closure_id))
        except (ContinuityStoreError, ValueError, TypeError, json.JSONDecodeError) as error:
            raise PmClosureError(str(error)) from error

    @staticmethod
    def _decode(payload: Mapping[str, Mapping[str, Any]]) -> ClosurePreparation:
        closure_values = dict(payload["closure"])
        step_values = dict(payload["step"])
        outbox_values = dict(payload["outbox"])
        outbox_values["payload"] = json.loads(str(outbox_values.pop("payload_json")))
        result = ClosurePreparation(
            closure=ClosureItem.model_validate(closure_values),
            step=ClosureStep.model_validate(step_values),
            outbox=ClosureOutboxItem.model_validate(outbox_values),
        )
        if (
            result.step.closure_id != result.closure.closure_id
            or result.outbox.closure_id != result.closure.closure_id
            or result.outbox.step_id != result.step.step_id
            or result.outbox.payload.get("closure_id") != result.closure.closure_id
            or result.outbox.payload.get("step_id") != result.step.step_id
            or result.outbox.payload.get("change_id") != result.closure.change_id
            or result.outbox.payload.get("checkpoint_id") != result.closure.checkpoint_id
        ):
            raise PmClosureError("Closure state、step 与 outbox identity 不一致")
        return result

    def _timestamp(self) -> str:
        current = self._now()
        if not isinstance(current, datetime) or current.tzinfo is None:
            raise PmClosureError("PM Closure clock 必须返回带时区 datetime")
        return current.astimezone(UTC).isoformat()


__all__ = [
    "ClosureItem",
    "ClosureOutboxItem",
    "ClosurePreparation",
    "ClosureState",
    "ClosureStep",
    "ClosureStepKind",
    "ClosureStepState",
    "PmClosureError",
    "PmClosureService",
]
