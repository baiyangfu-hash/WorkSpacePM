"""PLC-HMI 概念映射：HMI 画面数据结构（变更管理 DTO（变更单列表/变更单详情/台账对账结果））

像 HMI 触摸屏的画面变量结构，定义 QML 画面能显示的数据格式。

--- 原始注释 ---

Change 相关 DTO 定义"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ChangeSummaryDTO:
    change_number: str
    project_id: str
    project_name: str
    domain: str
    business_nature: str
    impact_scope: list[str]
    status: str
    applicant: str
    apply_date: str
    title: str
    urgency: str

@dataclass(frozen=True)
class ChangeRequestDTO:
    change_number: str
    project_id: str
    project_name: str
    domain: str
    business_nature: str
    impact_scope: list[str]
    status: str
    applicant: str
    apply_date: str
    planned_date: str
    urgency: str
    background: str
    necessity: str
    references: str
    risk_level: str
    mitigation: str
    propagation_chain: str
    file_path: str
    sections: dict[str, Any]


@dataclass(frozen=True)
class ChangeTimelineItemDTO:
    """变更审批时间线条目（对应 approval_history 表的一行流转记录）"""

    from_status: str
    to_status: str
    approver: str
    comment: str
    transition_date: str


@dataclass(frozen=True)
class ChangeValidationSummaryDTO:
    """变更验证摘要（聚合影响分析 + 审批历史计数）

    用于变更详情页右侧/底部的"验证状态"面板：
    - risk_level / mitigation / propagation_chain 来自 ImpactAnalysis
    - approval_count / last_approval_date 来自 ApprovalHistory 聚合
    - domain_impacts / related_changes 来自 ImpactAnalysis 的结构化字段
    """

    change_number: str
    current_status: str
    risk_level: str
    mitigation: str
    propagation_chain: str
    approval_count: int
    last_approval_date: str | None
    domain_impacts: dict[str, Any]
    related_changes: list[str]


@dataclass(frozen=True)
class LedgerReconcileResultDTO:
    """台账对账结果（对应 reconcile_ledger 返回，M5 CHG-118 新增）

    封装 LedgerReconciler.ReconcileDiff 为 QML 友好的 DTO：
    - status_mismatches 从 list[tuple[str,str,str]] 转为 list[list[str]]（QML 不支持 tuple）
    - auto_fixed 标识是只读对账(False)还是已自动修复(True)
    """

    project_id: str
    is_clean: bool
    missing_in_ledger: list[str]
    orphan_in_ledger: list[str]
    status_mismatches: list[list[str]]
    summary: str
    auto_fixed: bool
