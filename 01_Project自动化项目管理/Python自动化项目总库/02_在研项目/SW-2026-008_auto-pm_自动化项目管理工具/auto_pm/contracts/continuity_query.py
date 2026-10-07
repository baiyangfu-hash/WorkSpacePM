"""Versioned, capability-flagged query contract shared by resume, orient and the SDK (V05-A, M2).

M2 delivers only this read-only contract: parking and pre-emption are declared unsupported (full parking is M3, pre-emption also needs the V04-R1 recovery
evidence). The block never grants execution authority and carries no lease token.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

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

    contract_version: Literal["runtime-capabilities.v1"] = CAPABILITY_CONTRACT_VERSION
    parking_supported: Literal[False] = False
    preemption_supported: Literal[False] = False
    actions: tuple[ActionCapability, ...]


class ContinuityQuery(BaseModel):
    """Identity, capability and producer facts attached to a Resume v2 payload."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["continuity-query.v1"] = QUERY_SCHEMA_VERSION
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
