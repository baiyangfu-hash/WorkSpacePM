"""auto_pm.contracts.gate_dtos - 5 大过程组 Stage-Gate 门禁数据传输对象 (DTO)

为 008 驾驶舱提供强类型、模块化的阶段门禁检查结果契约。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

SeverityType = Literal["BLOCKER", "WARNING", "INFO"]
ProcessGroupStage = Literal[
    "initiating", "planning", "executing", "monitoring", "closing"
]


@dataclass
class GateCheckItemDTO:
    """单个门禁自检项结果 DTO"""

    id: str  # 规则唯一标识，如 "G1-PRD-NONGOALS", "G2-INT-FROZEN"
    name: str  # 规则可读名称
    passed: bool  # 是否通过
    severity: SeverityType  # 严重级别：BLOCKER(阻断流转) / WARNING(可继续但告警) / INFO
    message: str  # 结果描述
    fix_suggestion: str = ""  # 修复指引

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "passed": self.passed,
            "severity": self.severity,
            "message": self.message,
            "fix_suggestion": self.fix_suggestion,
        }


@dataclass
class StageGateResultDTO:
    """过程组阶段门禁综合评估结果 DTO"""

    current_stage: ProcessGroupStage  # 当前过程组阶段
    target_stage: ProcessGroupStage  # 目标流转阶段
    can_proceed: bool  # 是否满足准出条件（所有 BLOCKER 项必须 passed）
    total_checks: int = 0  # 检查总项数
    passed_checks: int = 0  # 通过项数
    blocker_count: int = 0  # 未通过的阻断项数
    warning_count: int = 0  # 告警项数
    items: list[GateCheckItemDTO] = field(default_factory=list)  # 具体检查项清单

    def __post_init__(self) -> None:
        if self.items:
            self.total_checks = len(self.items)
            self.passed_checks = sum(1 for item in self.items if item.passed)
            self.blocker_count = sum(
                1 for item in self.items if not item.passed and item.severity == "BLOCKER"
            )
            self.warning_count = sum(
                1 for item in self.items if not item.passed and item.severity == "WARNING"
            )
            self.can_proceed = self.blocker_count == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_stage": self.current_stage,
            "target_stage": self.target_stage,
            "can_proceed": self.can_proceed,
            "total_checks": self.total_checks,
            "passed_checks": self.passed_checks,
            "blocker_count": self.blocker_count,
            "warning_count": self.warning_count,
            "items": [item.to_dict() for item in self.items],
        }
