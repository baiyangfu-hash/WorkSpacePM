"""PLC-HMI 概念映射：SFB 库函数（约束/工作流系统公共 API）

像 PLC 的 SFB/SFC 系统函数，提供约束检查、文件守护、工作流执行的公共入口。

--- 原始注释 ---

约束/工作流执行系统

提供以下能力：
- FileGuard: 文件修改守护（sha256 快照 + BOM 检测）
- ConstraintChecker: 约束合规检查
- ConstraintHealer: 约束自愈修复
- WorkflowEngine: 工作流编排执行

Usage:
    from auto_pm.constraint import FileGuard

    guard = FileGuard(workspace_root)
    snap = guard.take_snapshot(file_path)
    # ... 修改文件 ...
    result = guard.verify_snapshot(file_path)
"""

from auto_pm.constraint.checker import ConstraintChecker
from auto_pm.constraint.guard import FileGuard
from auto_pm.constraint.healer import ConstraintHealer
from auto_pm.constraint.loader import ConstraintLoader, ConstraintLoadError
from auto_pm.constraint.models import (
    CheckReport,
    Constraint,
    ConstraintRule,
    ConstraintScope,
    GuardSnapshot,
    Violation,
    Workflow,
    WorkflowRun,
    WorkflowStep,
)
from auto_pm.constraint.workflow import WorkflowEngine

__all__ = [
    "CheckReport",
    "Constraint",
    "ConstraintChecker",
    "ConstraintHealer",
    "ConstraintLoader",
    "ConstraintLoadError",
    "ConstraintRule",
    "ConstraintScope",
    "FileGuard",
    "GuardSnapshot",
    "Violation",
    "Workflow",
    "WorkflowEngine",
    "WorkflowRun",
    "WorkflowStep",
]
