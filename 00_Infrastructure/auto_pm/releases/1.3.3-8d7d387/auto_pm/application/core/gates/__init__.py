"""auto_pm.core.gates - 5 大过程组 Stage-Gate 阶段门禁规则引擎模块"""

from auto_pm.core.gates.stage_gate_engine import StageGateEngine

from auto_pm.contracts.gate_dtos import (
    GateCheckItemDTO,
    ProcessGroupStage,
    StageGateResultDTO,
)

__all__ = [
    "GateCheckItemDTO",
    "ProcessGroupStage",
    "StageGateResultDTO",
    "StageGateEngine",
]
