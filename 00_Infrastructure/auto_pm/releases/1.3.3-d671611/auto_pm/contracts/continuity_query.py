"""Versioned, capability-flagged query contract shared by resume, orient and the SDK (V05-A, M2; v2 with TD-071 card 3).

v1 (M2) declared parking and pre-emption unsupported. v2 declares parking supported now that Missions can be parked and resumed
(``pm park`` / ``pm unpark`` / ``pm switch``, TD-071); pre-emption of a running holder stays unsupported. The block never grants execution
authority and carries no lease token: parking still needs the user's own words (``--approval-evidence-ref``).
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

QUERY_SCHEMA_VERSION: Final = "continuity-query.v1"
CAPABILITY_CONTRACT_VERSION: Final = "runtime-capabilities.v2"
UNSUPPORTED_REASON = (
    "运行中插队不支持：不抢正在写的钥匙；插急活请先 pm park 记断点放下手上的卡，再 pm switch；查询本身不是执行授权"
)


class QueriedAction(StrEnum):
    """Actions whose support can be asked for."""

    PARK = "PARK"
    RESUME_PARKED = "RESUME_PARKED"
    PREEMPT = "PREEMPT"


PARKING_ACTIONS: Final = (QueriedAction.PARK, QueriedAction.RESUME_PARKED)
SUPPORTED_REASONS: Final[dict[QueriedAction, str]] = {
    QueriedAction.PARK: "pm park 记断点放下手上的卡；放进“搁着”须带用户原话位置（--approval-evidence-ref），不带只能放进“等你”",
    QueriedAction.RESUME_PARKED: "pm unpark / pm switch 凭断点拿回搁着的卡；拿回哪张只听用户的（--approval-evidence-ref）",
}


class ActionCapability(BaseModel):
    """An explicit SUPPORTED or UNSUPPORTED answer; never an empty list, NONE or READY."""

    model_config = ConfigDict(frozen=True)

    action: QueriedAction
    status: Literal["SUPPORTED", "UNSUPPORTED"] = "UNSUPPORTED"
    reason: str = UNSUPPORTED_REASON


class RuntimeCapabilities(BaseModel):
    """What this runtime offers: parking may be declared, pre-emption is fixed to false; the flags and the actions must agree."""

    model_config = ConfigDict(frozen=True)

    contract_version: Literal["runtime-capabilities.v2"]
    parking_supported: bool = False
    preemption_supported: Literal[False] = False
    actions: tuple[ActionCapability, ...]

    @model_validator(mode="after")
    def _flags_match_actions(self) -> RuntimeCapabilities:
        for item in self.actions:
            if item.status != "SUPPORTED":
                continue
            if item.action is QueriedAction.PREEMPT:
                raise ValueError("插队（PREEMPT）在本合同里不能声明为 SUPPORTED")
            if not self.parking_supported:
                raise ValueError(f"{item.action.value} 声明为 SUPPORTED，但 parking_supported 为 false")
        return self


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
