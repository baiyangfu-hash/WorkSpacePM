"""Recoverable PM closure preparation backed only by Continuity v2."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from auto_pm.domain.change.ledger_reconciler import LedgerReconciler
from auto_pm.domain.change.substance_injector import SubstanceInjector
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


class LedgerProjectionState(StrEnum):
    """C07 result; C08 alone may advance closure lifecycle state."""

    PROJECTED = "PROJECTED"
    PENDING_SYNC = "PENDING_SYNC"


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


class LedgerProjectionReceipt(BaseModel):
    """An idempotent projection result with no hidden lifecycle transition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    closure_id: str
    change_id: str
    state: LedgerProjectionState
    pending_reason: str | None = None


class PmClosureService:
    """Prepare the accepted v2 lineage without performing external effects."""

    def __init__(
        self,
        workspace_root: str | Path,
        now: Callable[[], datetime] | None = None,
        *,
        store: ContinuityStore | None = None,
        ledger_reconciler: LedgerReconciler | None = None,
    ) -> None:
        self._workspace_root = Path(workspace_root)
        self._store = store or ContinuityStore(workspace_root)
        self._ledger_reconciler = ledger_reconciler or LedgerReconciler()
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

    def inject_prepared_change_substance(self, closure_id: str) -> Path:
        """Write only the verified C06 CHG evidence for a prepared closure.

        This does not publish the outbox, advance the closure step, transition a
        CHG, project ledger, Work, Run, or Mission.  Those transitions belong to
        later governed stages.
        """

        preparation = self.get(closure_id)
        try:
            evidence = self._change_substance_evidence(preparation)
            return SubstanceInjector.inject_closure_evidence(
                self._workspace_root,
                change_number=preparation.closure.change_id,
                target_path=preparation.outbox.target_path,
                evidence=evidence,
            )
        except (ValueError, TypeError) as error:
            raise PmClosureError(str(error)) from error

    def project_prepared_ledger(self, closure_id: str) -> LedgerProjectionReceipt:
        """Project the prepared closure's one CHG, preserving pending failure."""

        preparation = self.get(closure_id)
        try:
            self._change_substance_evidence(preparation)
            self.inject_prepared_change_substance(closure_id)
            remaining = self._ledger_reconciler.project_change(
                str(self._workspace_root), preparation.closure.change_id
            )
        except (OSError, ValueError, TypeError, PmClosureError) as error:
            return LedgerProjectionReceipt(
                closure_id=closure_id,
                change_id=preparation.closure.change_id,
                state=LedgerProjectionState.PENDING_SYNC,
                pending_reason=str(error),
            )
        if not remaining.is_clean:
            return LedgerProjectionReceipt(
                closure_id=closure_id,
                change_id=preparation.closure.change_id,
                state=LedgerProjectionState.PENDING_SYNC,
                pending_reason=remaining.summary(),
            )
        return LedgerProjectionReceipt(
            closure_id=closure_id,
            change_id=preparation.closure.change_id,
            state=LedgerProjectionState.PROJECTED,
        )

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

    @staticmethod
    def _change_substance_evidence(preparation: ClosurePreparation) -> dict[str, str]:
        closure = preparation.closure
        step = preparation.step
        outbox = preparation.outbox
        expected_payload = {
            "schema_version": "closure-outbox.v1",
            "closure_id": closure.closure_id,
            "step_id": step.step_id,
            "mission_id": closure.mission_id,
            "change_id": closure.change_id,
            "checkpoint_id": closure.checkpoint_id,
            "operation": ClosureStepKind.CHANGE_SUBSTANCE.value,
        }
        canonical_payload = json.dumps(
            expected_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if (
            closure.state is not ClosureState.PREPARED
            or step.step_kind is not ClosureStepKind.CHANGE_SUBSTANCE
            or step.state is not ClosureStepState.PENDING
            or step.attempt_count != 0
            or outbox.artifact_kind is not ClosureStepKind.CHANGE_SUBSTANCE
            or outbox.published_at is not None
            or outbox.target_path != f"change://{closure.change_id}"
            or outbox.payload != expected_payload
            or outbox.payload_hash != sha256(canonical_payload.encode("utf-8")).hexdigest()
        ):
            raise PmClosureError("Closure 未处于可验证的 C06 CHANGE_SUBSTANCE 准备状态")
        return {
            "closure_id": closure.closure_id,
            "work_id": closure.work_id,
            "run_id": closure.run_id,
            "checkpoint_id": closure.checkpoint_id,
            "change_id": closure.change_id,
            "decision_id": closure.decision_id,
            "step_id": step.step_id,
            "outbox_id": outbox.outbox_id,
            "request_hash": closure.request_hash,
            "payload_hash": outbox.payload_hash,
            "prepared_on": closure.created_at.date().isoformat(),
        }

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
    "LedgerProjectionReceipt",
    "LedgerProjectionState",
    "PmClosureError",
    "PmClosureService",
]
