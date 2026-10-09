"""Versioned, capability-flagged query contract shared by resume, orient and the SDK (V05-A, M2).

M2 delivers only this read-only contract: parking and pre-emption are declared unsupported (full parking is M3, pre-emption also needs the V04-R1 recovery
evidence). The block never grants execution authority and carries no lease token.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

QUERY_SCHEMA_VERSION: Final = "continuity-query.v1"
CAPABILITY_CONTRACT_VERSION: Final = "runtime-capabilities.v1"
UNSUPPORTED_REASON = (
    "M2 只交付版本化的只读查询合同；完整挂起属于 M3，运行中插队还须 V04-R1 的回收与 fencing 证据；查询本身不是执行授权"
)


class QueriedAction(StrEnum):
    """Actions whose support is asked for but not offered in M2."""

    PARK = "PARK"
    RESUME_PARKED = "RESUME_PARKED"
    PREEMPT = "PREEMPT"


class ActionCapability(BaseModel):
    """An explicit UNSUPPORTED answer; never an empty list, NONE or READY."""

    model_config = ConfigDict(frozen=True)

    action: QueriedAction
    status: Literal["UNSUPPORTED"] = "UNSUPPORTED"
    reason: str = UNSUPPORTED_REASON


class RuntimeCapabilities(BaseModel):
    """What this runtime offers; both flags are fixed to false by the M2 contract."""

    model_config = ConfigDict(frozen=True)

    contract_version: Literal["runtime-capabilities.v1"]
    parking_supported: Literal[False] = False
    preemption_supported: Literal[False] = False
    actions: tuple[ActionCapability, ...]


class ContinuityQuery(BaseModel):
    """Identity, capability and producer facts attached to a Resume v2 payload."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["continuity-query.v1"]
    control_root: str
    execution_root: str
    candidate_commit: str
    configured_release_id: str
    effective_release_id: str
    runtime_load_path: str
    runtime_fallback_reason: str
    producer_load_path: str
    producer_sha256: str
    capabilities: RuntimeCapabilities
    requested_action: ActionCapability | None = None
    evidence_id: str


def validation_summary(error: ValidationError) -> str:
    """One short line per problem (location and message), never the offending input."""

    return "; ".join(f"{'.'.join(str(part) for part in item['loc']) or '<root>'}: {item['msg']}" for item in error.errors())


def plain_payload(value: object) -> dict[str, Any]:
    """The plain field data of a mapping or a model, so that it is validated again from scratch.

    ``model_validate`` on a model instance would trust it; ``model_construct`` and ``model_copy`` skip validation, so a consumer that takes a model from outside re-validates
    its exported data instead.
    """

    if isinstance(value, BaseModel):
        try:
            return value.model_dump(mode="python")
        except (AttributeError, TypeError, ValueError) as error:
            raise ValueError(f"无法导出 {type(value).__name__} 的字段数据: {error}") from error
    if isinstance(value, Mapping):
        return dict(value)
    raise ValueError(f"需要映射或模型，收到 {type(value).__name__}")


def validate_runtime_capabilities(value: object) -> RuntimeCapabilities:
    """Re-validate a capability block taken from outside; a missing or wrong version is refused, never filled in."""

    try:
        return RuntimeCapabilities.model_validate(plain_payload(value))
    except ValidationError as error:
        raise ValueError(f"能力合同未通过校验: {validation_summary(error)}") from error
