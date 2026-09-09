"""auto_pm.contracts.decision_package - 阶段 1 审批结构化决策包契约

用于将 PM / 架构师对变更单的审批范围、允许修改的文件白名单和约束条件固化为机器可读且不可篡改的 JSON 契约。
作为阶段 2 派发 execution handoff 的强制前置输入（不可绕过门禁）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

SCHEMA_VERSION = "decision_package.v1"


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
        return cls(
            schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
            decision_id=str(data.get("decision_id", "")),
            project_id=str(data.get("project_id", "")),
            change_id=str(data.get("change_id", "")),
            approved_scope=str(data.get("approved_scope", "MODULE")),
            approved_files=[str(f) for f in data.get("approved_files", [])],
            approver=str(data.get("approver", "")),
            approved_at=str(data.get("approved_at", "")),
            decision_conclusion=str(data.get("decision_conclusion", "approved")),
            conditions=[str(c) for c in data.get("conditions", [])],
            metadata=dict(data.get("metadata", {})),
        )

