"""auto_pm.contracts.decision_package - 阶段 1 审批结构化决策包契约

用于将 PM / 架构师对变更单的审批范围、允许修改的文件白名单和约束条件固化为机器可读且不可篡改的 JSON 契约。
作为阶段 2 派发 execution handoff 的强制前置输入（不可绕过门禁）。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

SCHEMA_VERSION = "decision_package.v1"
RUNTIME_CAPABILITY_KEY = "runtime_capability"
DECISION_ID_PATTERN = re.compile(r"DEC-[0-9]{8}-[A-Z0-9]{8}\Z")
RUNTIME_CHANGE_ID_PATTERN = re.compile(r"CHG-[A-Z][A-Z0-9]*-[0-9]{4}-[0-9]{3}\Z")


def is_canonical_decision_id(value: object) -> bool:
    """Return whether ``value`` is the one accepted persisted Decision identity form."""

    return isinstance(value, str) and DECISION_ID_PATTERN.fullmatch(value) is not None


def is_canonical_runtime_change_id(value: object) -> bool:
    """Return whether ``value`` is a canonical runtime-authority CHG basename."""

    return isinstance(value, str) and RUNTIME_CHANGE_ID_PATTERN.fullmatch(value) is not None


class RuntimeDecisionAction(StrEnum):
    """Exceptional runtime mutations that a Decision may explicitly authorize."""

    SETTLE_EXPIRED_RUN = "settle_expired_run"
    REVOKE_UNSTARTED_RUN = "revoke_unstarted_run"
    FENCE_TERMINAL_LEASE = "fence_terminal_lease"
    RECONCILE_TERMINAL_LEASE = "reconcile_terminal_lease"
    ADJUDICATE_BLOCKED_WORK = "adjudicate_blocked_work"
    FENCE_LEGACY_TERMINAL_LEASE = "fence_legacy_terminal_lease"


class RuntimeDecisionOutcome(StrEnum):
    """Fail-closed outcomes allowed for administrative Run settlement."""

    CANCELLED = "CANCELLED"
    RELEASED = "RELEASED"


@dataclass(frozen=True)
class RuntimeDecisionCapability:
    """Typed, least-privilege capability embedded in legacy-compatible metadata."""

    allowed_runtime_actions: tuple[RuntimeDecisionAction, ...]
    target_run_ids: tuple[str, ...]
    allowed_outcomes: tuple[RuntimeDecisionOutcome, ...]
    target_work_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        try:
            actions = tuple(
                dict.fromkeys(
                    RuntimeDecisionAction(str(item)) for item in self.allowed_runtime_actions
                )
            )
            outcomes = tuple(
                dict.fromkeys(RuntimeDecisionOutcome(str(item)) for item in self.allowed_outcomes)
            )
        except ValueError as error:
            raise ValueError("runtime_capability 包含未知 action 或 outcome") from error
        raw_targets = tuple(self.target_run_ids)
        if any(
            not isinstance(item, str) or not item or item != item.strip() for item in raw_targets
        ):
            raise ValueError("runtime_capability.target_run_ids 必须是规范非空字符串")
        targets = tuple(dict.fromkeys(raw_targets))
        raw_work_targets = tuple(self.target_work_ids)
        if any(
            not isinstance(item, str) or not item or item != item.strip()
            for item in raw_work_targets
        ):
            raise ValueError("runtime_capability.target_work_ids 必须是规范非空字符串")
        work_targets = tuple(dict.fromkeys(raw_work_targets))
        if not actions or not outcomes:
            raise ValueError("runtime_capability 的 action 与 outcome 均不能为空")
        if RuntimeDecisionAction.ADJUDICATE_BLOCKED_WORK in actions:
            # Work 行政裁决是独占权限：不得与 Run 级动作混用，也不得携带 Run 目标。
            if actions != (RuntimeDecisionAction.ADJUDICATE_BLOCKED_WORK,):
                raise ValueError("adjudicate_blocked_work 不得与其他 runtime action 混用")
            if not work_targets or targets:
                raise ValueError(
                    "adjudicate_blocked_work 必须只提供 target_work_ids 且不得提供 target_run_ids"
                )
        elif not targets or work_targets:
            raise ValueError("Run 级 runtime action 必须只提供 target_run_ids")
        if (
            RuntimeDecisionAction.FENCE_LEGACY_TERMINAL_LEASE in actions
            and actions != (RuntimeDecisionAction.FENCE_LEGACY_TERMINAL_LEASE,)
        ):
            # 旧终态 lease 兼容围栏同样是独占权限，不得与结算、撤销或其他围栏混用。
            raise ValueError("fence_legacy_terminal_lease 不得与其他 runtime action 混用")
        object.__setattr__(self, "allowed_runtime_actions", actions)
        object.__setattr__(self, "target_run_ids", targets)
        object.__setattr__(self, "allowed_outcomes", outcomes)
        object.__setattr__(self, "target_work_ids", work_targets)

    def to_dict(self) -> dict[str, list[str]]:
        result = {
            "allowed_runtime_actions": [item.value for item in self.allowed_runtime_actions],
            "target_run_ids": list(self.target_run_ids),
            "allowed_outcomes": [item.value for item in self.allowed_outcomes],
        }
        if self.target_work_ids:
            # 仅 Work 裁决权限携带该字段，保证既有 Run 级 Decision 字节格式不变。
            result["target_work_ids"] = list(self.target_work_ids)
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RuntimeDecisionCapability:
        base = {"allowed_runtime_actions", "target_run_ids", "allowed_outcomes"}
        supplied = set(data)
        expected = base | ({"target_work_ids"} if "target_work_ids" in supplied else set())
        if supplied != expected:
            missing = ", ".join(sorted(expected - supplied)) or "-"
            unknown = ", ".join(sorted(supplied - expected)) or "-"
            raise ValueError(
                f"runtime_capability 字段不完整或未知；missing={missing}; unknown={unknown}"
            )

        def values(name: str) -> tuple[Any, ...]:
            raw = data[name]
            if not isinstance(raw, (list, tuple)):
                raise ValueError(f"runtime_capability.{name} 必须是数组")
            return tuple(raw)

        try:
            targets = values("target_run_ids")
            if any(not isinstance(item, str) for item in targets):
                raise ValueError("runtime_capability.target_run_ids 必须是字符串数组")
            work_targets = values("target_work_ids") if "target_work_ids" in data else ()
            if any(not isinstance(item, str) for item in work_targets):
                raise ValueError("runtime_capability.target_work_ids 必须是字符串数组")
            return cls(
                allowed_runtime_actions=tuple(
                    RuntimeDecisionAction(str(item)) for item in values("allowed_runtime_actions")
                ),
                target_run_ids=tuple(targets),
                allowed_outcomes=tuple(
                    RuntimeDecisionOutcome(str(item)) for item in values("allowed_outcomes")
                ),
                target_work_ids=tuple(work_targets),
            )
        except ValueError as error:
            raise ValueError("runtime_capability 包含未知 action 或 outcome") from error


@dataclass
class DecisionPackageDTO:
    """结构化决策包 DTO"""

    decision_id: str  # 决策包全局唯一标识，如 "DEC-20260903-XXXX"
    project_id: str  # 关联项目编号，如 "DJ-2026-005"
    change_id: str  # 关联变更单编号，如 "CHG-PLC-2026-012"
    approved_scope: str  # 批准范围："LOCAL" / "MODULE" / "SYSTEM" / "CROSS" / "SAFE" / "SPEC"
    approved_files: list[str] = field(default_factory=list)  # 允许修改的文件相对路径白名单
    approver: str = ""  # 审批人（PM / 架构师）
    approved_at: str = ""  # 批准时间（ISO 8601）
    decision_conclusion: str = "approved"  # "approved" | "conditionally_approved"
    conditions: list[str] = field(default_factory=list)  # 附加条件清单
    schema_version: str = SCHEMA_VERSION  # 契约版本
    metadata: dict[str, Any] = field(default_factory=dict)  # 补充元数据

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"未知 Decision schema_version: {self.schema_version}")
        if not isinstance(self.metadata, Mapping):
            raise ValueError("metadata 必须是对象")
        normalized = dict(self.metadata)
        raw_capability = normalized.get(RUNTIME_CAPABILITY_KEY)
        if raw_capability is not None:
            if isinstance(raw_capability, RuntimeDecisionCapability):
                capability = raw_capability
            elif isinstance(raw_capability, Mapping):
                capability = RuntimeDecisionCapability.from_dict(raw_capability)
            else:
                raise ValueError("metadata.runtime_capability 必须是对象")
            normalized[RUNTIME_CAPABILITY_KEY] = capability.to_dict()
        self.metadata = normalized

    @property
    def runtime_capability(self) -> RuntimeDecisionCapability | None:
        raw = self.metadata.get(RUNTIME_CAPABILITY_KEY)
        if raw is None:
            return None
        if not isinstance(raw, Mapping):  # pragma: no cover - guarded by __post_init__
            raise ValueError("metadata.runtime_capability 必须是对象")
        return RuntimeDecisionCapability.from_dict(raw)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "decision_id": self.decision_id,
            "project_id": self.project_id,
            "change_id": self.change_id,
            "approved_scope": self.approved_scope,
            "approved_files": list(self.approved_files),
            "approver": self.approver,
            "approved_at": self.approved_at or datetime.now(UTC).isoformat(),
            "decision_conclusion": self.decision_conclusion,
            "conditions": list(self.conditions),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DecisionPackageDTO:
        if not isinstance(data, Mapping):
            raise ValueError("Decision package 顶层必须是对象")
        raw_metadata = data.get("metadata", {})
        if not isinstance(raw_metadata, Mapping):
            raise ValueError("metadata 必须是对象")
        is_runtime = RUNTIME_CAPABILITY_KEY in raw_metadata
        if is_runtime:
            required = {
                "schema_version",
                "decision_id",
                "project_id",
                "change_id",
                "approved_scope",
                "approved_files",
                "approver",
                "approved_at",
                "decision_conclusion",
                "conditions",
                "metadata",
            }
            missing = required - set(data)
            unknown = set(data) - required
            if missing:
                raise ValueError("runtime Decision 缺少显式字段: " + ", ".join(sorted(missing)))
            if unknown:
                raise ValueError("runtime Decision 包含未知字段: " + ", ".join(sorted(unknown)))

        def text(name: str, default: str) -> str:
            raw = data.get(name, default)
            if not isinstance(raw, str):
                raise ValueError(f"Decision.{name} 必须是字符串")
            return raw

        def strings(name: str) -> list[str]:
            raw = data.get(name, [])
            if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
                raise ValueError(f"Decision.{name} 必须是字符串数组")
            return list(raw)

        decision = cls(
            schema_version=text("schema_version", SCHEMA_VERSION),
            decision_id=text("decision_id", ""),
            project_id=text("project_id", ""),
            change_id=text("change_id", ""),
            approved_scope=text("approved_scope", "MODULE"),
            approved_files=strings("approved_files"),
            approver=text("approver", ""),
            approved_at=text("approved_at", ""),
            decision_conclusion=text("decision_conclusion", "approved"),
            conditions=strings("conditions"),
            metadata=dict(raw_metadata),
        )
        if is_runtime:
            for name, value in (
                ("decision_id", decision.decision_id),
                ("project_id", decision.project_id),
                ("change_id", decision.change_id),
                ("approved_scope", decision.approved_scope),
                ("approver", decision.approver),
                ("approved_at", decision.approved_at),
                ("decision_conclusion", decision.decision_conclusion),
            ):
                if not value or value != value.strip():
                    raise ValueError(f"runtime Decision.{name} 必须是规范非空字符串")
            try:
                approved_at = datetime.fromisoformat(decision.approved_at)
            except ValueError as error:
                raise ValueError("runtime Decision.approved_at 必须是 ISO-8601 时间") from error
            if approved_at.tzinfo is None:
                raise ValueError("runtime Decision.approved_at 必须包含时区")
        return decision
