"""PLC-HMI 概念映射：UDT 数据类型（约束/违规/快照/报告数据结构）

像 PLC 的 UDT（用户自定义数据类型），定义约束系统中所有结构化数据。
被 FB 功能块（guard.py/checker.py/workflow.py）使用。

--- 原始注释 ---

约束系统核心数据模型

定义 Constraint（约束定义）、Violation（违规记录）、GuardSnapshot（文件守护快照）、
CheckReport（检查报告）等数据结构。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ConstraintScope:
    """约束作用域：定义哪些文件受此约束管理"""

    patterns: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)


@dataclass
class ConstraintRule:
    """约束规则：约束的具体检查逻辑"""

    type: str  # no_external_write | regex_blacklist | cli_only_create | bom_count | null_byte
    description: str = ""
    check: str | None = None
    pattern: str | None = None
    cli_command: str | None = None
    max_count: int | None = None


@dataclass
class Constraint:
    """约束定义：一个完整的约束规则"""

    id: str  # CST-FILE-001
    name: str
    description: str = ""
    type: str = "file_guard"  # file_guard | file_encoding | naming | workflow | pre_commit
    severity: str = "error"  # error | warning | info
    scope: ConstraintScope = field(default_factory=ConstraintScope)
    rules: list[ConstraintRule] = field(default_factory=list)
    auto_fix: bool = False
    heal_command: str = ""


@dataclass
class Violation:
    """违规记录：一次约束违规事件"""

    constraint_id: str
    file_path: str
    rule_type: str
    message: str
    severity: str = "error"
    detected_at: datetime = field(default_factory=datetime.now)
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class GuardSnapshot:
    """文件守护快照：文件在某个时间点的完整状态"""

    snapshot_id: str
    file_path: str
    sha256: str
    size: int
    mtime: float
    bom_count: int = 0
    taken_at: datetime = field(default_factory=datetime.now)


@dataclass
class CheckReport:
    """约束检查报告：一次检查的汇总结果"""

    total: int = 0
    passed: int = 0
    violations: int = 0
    violations_list: list[Violation] = field(default_factory=list)
    checked_at: datetime = field(default_factory=datetime.now)


@dataclass
class WorkflowStep:
    """工作流步骤"""

    id: str = ""
    name: str = ""
    action: str = "run_cmd"
    command: str | None = None
    type: str = "auto"  # auto | manual
    on_failure: str = "abort"  # abort | warn | continue
    description: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    allow_failure: bool = False


@dataclass
class Workflow:
    """工作流定义"""

    id: str = ""
    name: str = ""
    description: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)


@dataclass
class WorkflowRun:
    """工作流执行记录"""

    run_id: str
    workflow_id: str = ""
    workflow_name: str = ""
    status: str = "pending"  # pending | running | completed | failed | success
    steps: list[dict[str, Any]] = field(default_factory=list)
    steps_completed: int = 0
    step_logs: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
