"""PLC-HMI 概念映射：SFB 库函数（变更管理常量（如 PLC 的常量表/符号表））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

变更管理数据模型与规范常量

合并自:
  - src/models/change_request.py（ChangeRequest, ChangeSummary dataclass）
  - src/models/spec_constant.py（CHG-040 规范常量 + 校验函数 + 异常类）

数据模型已迁移至 auto_pm/models/change.py（Pydantic v2）。
本文件保留规范常量、异常类和校验函数，并重新导出模型以保持向后兼容。
"""

from __future__ import annotations

from auto_pm.models import ChangeRequest, ChangeSummary  # noqa: F401

# 显式导出（mypy strict 模式要求）
__all__ = [
    "ChangeRequest",
    "ChangeSummary",
    "SpecViolationError",
    "TransitionGuardError",
    "validate_domain",
    "validate_business_nature",
    "validate_impact_scope",
    "validate_urgency",
    "validate_status_transition",
]

# ════════════════════════════════════════════════════════════
#  CHG-040 变更管理规范常量
# ════════════════════════════════════════════════════════════

# §3.1 技术领域（必选，单选）
DOMAINS: dict[str, str] = {
    "ELEC": "电气设计",
    "MECH": "机械结构",
    "PLC": "PLC程序",
    "HMI": "HMI程序",
    "SCPT": "Python脚本",
    "DOCU": "工程文档",
    "SAFE": "安全功能",
}

# §3.1 技术领域描述（用于模板渲染）
DOMAIN_DESCRIPTIONS: dict[str, str] = {
    "ELEC": "Eplan/接线图/IO表/BOM/柜体布局",
    "MECH": "SolidWorks 3D/装配图/加工图",
    "PLC": "SCL/ST/LD/GVL/功能块库",
    "HMI": "触摸屏画面/变量映射/报警配置",
    "SCPT": "数据采集/MES接口/上位机应用",
    "DOCU": "设计说明书/操作手册/验收报告",
    "SAFE": "急停回路/安全矩阵/SIL评估",
}

# §3.2 业务性质（必选，单选）
BUSINESS_NATURES: dict[str, str] = {
    "REQ": "需求变更",
    "DEF": "缺陷修复",
    "OPT": "优化改进",
    "CFG": "配置调整",
    "EMRG": "紧急变更",
}

# §3.2 业务性质描述（用于模板渲染）
BUSINESS_NATURE_DESCRIPTIONS: dict[str, str] = {
    "REQ": "客户新增功能/工艺调整/范围扩展",
    "DEF": "Bug修复/故障排除/设计纠错",
    "OPT": "性能提升/可维护性改善/重构",
    "CFG": "参数修改/IO地址调整/通信配置",
    "EMRG": "安全相关/生产中断(需特殊审批流程)",
}

# §3.3 影响范围（可多选）
IMPACT_SCOPES: dict[str, str] = {
    "LOCAL": "局部变更",
    "MODULE": "模块级变更",
    "SYSTEM": "系统级变更",
    "CROSS": "跨系统变更",
    "SAFE": "安全相关变更",
}

# §3.3 影响范围描述（用于模板渲染）
IMPACT_SCOPE_DESCRIPTIONS: dict[str, str] = {
    "LOCAL": "仅单个POU/画面/IO点 → 项目经理审批",
    "MODULE": "单个设备/单条线 → 项目负责人审批",
    "SYSTEM": "多模块联动/联锁逻辑 → 技术总监审批",
    "CROSS": "PLC+HMI+电气多领域联动 → 高层管理层审批",
    "SAFE": "急停/SIL/安全功能 → 安全负责人+高层联合审批",
}

# §3.4 紧急程度
URGENCY_LEVELS: dict[str, str] = {
    "normal": "一般",
    "urgent": "紧急",
    "critical": "非常紧急",
}

# §8 审批结论
APPROVAL_CONCLUSIONS: set[str] = {
    "approved",
    "conditionally_approved",
    "rejected",
    "refused",
}

# 变更单状态流转（合法状态及允许的下一状态）
# 对齐 PM-042 V2.3.0 §5.2 状态机：
#   draft → submitted → under_review → approved → implementing → pending_acceptance → accepting
#                                                  ↓ 有条件批准                    ↓ 验证通过
#                                      conditionally_approved                completed → closed
#                                                  ↓ 驳回                        ↓ 归档
#                                                rejected                      archived（终态）
STATUS_FLOW: dict[str, set[str]] = {
    "draft": {"submitted"},
    "submitted": {"under_review", "draft"},
    "under_review": {"approved", "conditionally_approved", "rejected", "submitted"},
    "approved": {"implementing"},
    "conditionally_approved": {"implementing"},
    "implementing": {"pending_acceptance", "approved"},  # 实施完成→待验收；或退回已批准
    "pending_acceptance": {"accepting"},  # 开始验收
    "accepting": {"completed", "implementing"},  # 验证通过→完成；验证不通过→返工重做
    "completed": {"closed", "archived"},
    "rejected": {"draft"},
    "closed": set(),  # 终态
    "archived": set(),  # 终态（已归档，不可再流转）
}

# 所有合法状态
ALL_STATUSES: set[str] = set(STATUS_FLOW.keys())

# 状态中文标签（供前端渲染）
STATUS_LABELS: dict[str, str] = {
    "draft": "草稿",
    "submitted": "已提交",
    "under_review": "审核中",
    "approved": "已批准",
    "conditionally_approved": "有条件批准",
    "rejected": "已驳回",
    "implementing": "实施中",
    "pending_acceptance": "待验收",
    "accepting": "验收中",
    "completed": "已完成",
    "closed": "已关闭",
    "archived": "已归档",
}

# 阶段中文标签（供前端渲染）
PHASE_LABELS: dict[str, str] = {
    "developing": "开发中",
    "commissioning": "调试中",
    "production": "生产中",
    "archived": "已归档",
}

# 台账状态文案映射（带 emoji，供 LedgerUpdater/Reconciler 写入台账"状态"列）
# CHG-108 缺陷 1：从 change_service._LEDGER_STATUS_MAP 提取为公开常量，消除重复定义
LEDGER_STATUS_MAP: dict[str, str] = {
    "draft": "🔄待处理",
    "submitted": "🔄审核中",
    "under_review": "🔄审核中",
    "approved": "🔄已批准",
    "conditionally_approved": "🔄有条件批准",
    "rejected": "❌已拒绝",
    "implementing": "🔄实施中",
    "pending_acceptance": "🔄待验收",
    "accepting": "🔄验收中",
    "completed": "✅已关闭",
    "closed": "✅已关闭",
    "archived": "✅已归档",
}

# §3 必须包含的子章节
REQUIRED_SUBSECTIONS: set[str] = {"3.0", "3.1", "3.2", "3.3", "3.4"}

# §3.0 必须包含的字段
REQUIRED_3_0_FIELDS: set[str] = {"变更编号", "项目名称", "项目编号"}

# §3.4 必须包含的字段
REQUIRED_3_4_FIELDS: set[str] = {"变更申请人", "申请日期"}


# ════════════════════════════════════════════════════════════
#  异常类
# ════════════════════════════════════════════════════════════


class SpecViolationError(ValueError):
    """变更单不符合 CHG-040 规范"""


class TransitionGuardError(ValueError):
    """变更单内容不满足流转前置条件"""


# ════════════════════════════════════════════════════════════
#  校验函数
# ════════════════════════════════════════════════════════════


def validate_domain(domain: str) -> None:
    """校验技术领域"""
    if domain not in DOMAINS:
        raise SpecViolationError(f"技术领域 '{domain}' 不合法，允许值: {list(DOMAINS.keys())}")


def validate_business_nature(nature: str) -> None:
    """校验业务性质"""
    if nature not in BUSINESS_NATURES:
        raise SpecViolationError(
            f"业务性质 '{nature}' 不合法，允许值: {list(BUSINESS_NATURES.keys())}"
        )


def validate_impact_scope(scopes: list[str]) -> None:
    """校验影响范围"""
    invalid = [s for s in scopes if s not in IMPACT_SCOPES]
    if invalid:
        raise SpecViolationError(f"影响范围 {invalid} 不合法，允许值: {list(IMPACT_SCOPES.keys())}")


def validate_urgency(urgency: str) -> None:
    """校验紧急程度"""
    if urgency not in URGENCY_LEVELS:
        raise SpecViolationError(
            f"紧急程度 '{urgency}' 不合法，允许值: {list(URGENCY_LEVELS.keys())}"
        )


def validate_status_transition(current: str, target: str) -> None:
    """校验状态流转是否合法"""
    if current not in STATUS_FLOW:
        raise SpecViolationError(f"当前状态 '{current}' 不合法，允许值: {ALL_STATUSES}")
    if target not in STATUS_FLOW[current]:
        raise SpecViolationError(
            f"状态流转 '{current}' → '{target}' 不合法，"
            f"允许的下一状态: {STATUS_FLOW[current] or '(终态，不可流转)'}"
        )
