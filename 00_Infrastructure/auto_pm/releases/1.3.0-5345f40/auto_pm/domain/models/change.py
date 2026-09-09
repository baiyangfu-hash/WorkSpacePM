"""PLC-HMI 概念映射：UDT 自定义数据类型（变更单信息（ChangeRequest/ChangeSummary 数据结构））

像 PLC 的 UDT（User Defined Type），定义数据结构。

--- 原始注释 ---

变更管理核心模型（迁移自 change/models.py:dataclass）

来源：CHG-*.md 文件解析。常量和校验函数仍保留在 change/models.py。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from auto_pm.models.enums import (
    BusinessNature,
    ChangeStatus,
    Domain,
    ImpactScope,
    Urgency,
)


class ChangeRequest(BaseModel):
    """变更单完整模型

    迁移自 change/models.py 的 ChangeRequest dataclass。
    字段对齐 CHG-040 规范章节结构。
    """

    # §3.0 编号与项目
    change_number: str = Field("", description="变更编号 CHG-PLC-2026-001")
    project_id: str = Field("", description="关联项目编号")
    project_name: str = Field("", description="项目名称")

    # §3.1 技术领域
    domain: Domain = Field("", description="技术领域: ELEC/MECH/PLC/HMI/SCPT/DOCU/SAFE")

    # §3.2 业务性质
    business_nature: BusinessNature = Field("", description="业务性质: REQ/DEF/OPT/CFG/EMRG")

    # §3.3 影响范围
    impact_scope: list[ImpactScope] = Field(default_factory=list, description="影响范围（多选）")

    # §3.4 申请信息
    applicant: str = Field("待补充", description="申请人")
    apply_date: str = Field("待补充", description="申请日期")
    planned_date: str = Field("待补充", description="计划完成日期")
    urgency: Urgency = Field("normal", description="紧急程度: normal/urgent/critical")

    # §4 变更原因
    background: str = Field("待补充", description="变更背景")
    necessity: str = Field("待补充", description="变更必要性")
    references: str = Field("待补充", description="参考文件")

    # 状态（从审批流程推断）
    status: ChangeStatus = Field("draft", description="变更单状态")

    # 章节内容（门禁校验用，记录各章节是否有实质内容）
    has_section_4: bool = Field(False, description="§4 变更原因")
    has_section_6: bool = Field(False, description="§6 变更影响分析")
    has_section_7: bool = Field(False, description="§7 实施计划")
    has_section_8_approval: bool = Field(False, description="§8.1 至少一条审批记录")
    has_section_9: bool = Field(False, description="§9 实施记录")
    has_section_10_verify: bool = Field(False, description="§10.1 至少一条验证项")
    section_10_conclusion: str = Field("", description="§10.2 验证结论")

    # §6 变更影响分析
    constraint_impacts: dict[str, str] = Field(
        default_factory=dict,
        description="§6.1 项目约束影响: 维度→影响程度(无/低/中/高)",
    )
    # M1-1: §6.1 下方独立字段（PMBOK 风险评估）
    risk_level: str = Field("", description="§6.1 风险等级: none/low/medium/high")
    mitigation: str = Field("", description="§6.1 缓解措施（风险应对策略）")
    domain_impacts: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="§6.2 技术领域影响: 领域代码→{affected, content, related_chg}",
    )
    propagation_chain: str = Field("", description="§6.3 变更传播链路径描述")
    related_changes: list[str] = Field(
        default_factory=list,
        description="§6.3 关联变更单编号清单",
    )

    # 元数据
    file_path: str = Field("", description="CHG-*.md 文件路径")
    file_mtime: float = Field(0, description="文件修改时间")

    # 原始章节文本（M3.5-6: 供 CLI show 命令渲染 §6/§8/§9/§10）
    sections: dict[str, str] = Field(
        default_factory=dict,
        description="按章节号拆分的原始 Markdown 文本（'6'/'8'/'9'/'10' 等）",
    )

    model_config = ConfigDict(from_attributes=True)


class ChangeSummary(BaseModel):
    """变更单列表项（轻量级）

    迁移自 change/models.py 的 ChangeSummary dataclass。
    用于列表展示，不含完整章节内容。
    """

    change_number: str = Field("", description="变更编号")
    project_id: str = Field("", description="项目编号")
    project_name: str = Field("", description="项目名称")
    domain: Domain = Field("", description="技术领域")
    business_nature: BusinessNature = Field("", description="业务性质")
    impact_scope: list[ImpactScope] = Field(default_factory=list, description="影响范围")
    status: ChangeStatus = Field("draft", description="状态")
    applicant: str = Field("待补充", description="申请人")
    apply_date: str = Field("待补充", description="申请日期")
    title: str = Field("待补充", description="标题（background 摘要）")
    urgency: Urgency = Field("normal", description="紧急程度: normal/urgent/critical")

    model_config = ConfigDict(from_attributes=True)


class ImpactAnalysis(BaseModel):
    """变更影响分析持久化模型（M2-1 新增）

    对齐 §6 变更影响分析章节，存储结构化数据供 GUI 传播链视图和影响分析编辑使用。
    字段对齐 impact_analysis 表。
    """

    project_id: str = Field("", description="项目编号")
    change_number: str = Field("", description="变更编号（主键）")
    risk_level: str = Field("", description="§6.1 风险等级: none/low/medium/high")
    mitigation: str = Field("", description="§6.1 缓解措施")
    constraint_impacts: dict[str, str] = Field(
        default_factory=dict,
        description="§6.1 项目约束影响: 维度→影响程度(无/低/中/高)",
    )
    domain_impacts: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="§6.2 技术领域影响: 领域代码→{affected, content, related_chg}",
    )
    propagation_chain: str = Field("", description="§6.3 变更传播链路径描述")
    related_changes: list[str] = Field(
        default_factory=list,
        description="§6.3 关联变更单编号清单",
    )
    updated_at: str = Field("", description="最后更新时间（ISO 格式）")

    model_config = ConfigDict(from_attributes=True)


class ApprovalRecord(BaseModel):
    """审批流转历史记录（M2-1 新增）

    每次 transition_status 流转追加一条记录。对齐 approval_history 表。
    """

    id: int = Field(0, description="记录 ID（自增，新建时为 0）")
    project_id: str = Field("", description="项目编号")
    change_number: str = Field("", description="变更编号")
    from_status: str = Field("", description="流转前状态")
    to_status: str = Field("", description="流转后状态")
    approver: str = Field("", description="审批人/操作人")
    comment: str = Field("", description="审批意见")
    transition_date: str = Field("", description="流转日期（ISO 格式）")

    model_config = ConfigDict(from_attributes=True)
