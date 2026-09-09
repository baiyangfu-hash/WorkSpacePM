"""PLC-HMI 概念映射：UDT 自定义数据类型（枚举类型（如 PLC 的常量定义））

像 PLC 的 UDT（User Defined Type），定义数据结构。

--- 原始注释 ---

枚举与 Literal 类型定义

对齐 CHG-040 变更管理规范和 LSP-907 907_项目配置规范_LSP 的合法值集合。
使用 Literal 类型而非 Enum，便于与 Pydantic v2 和 JSON 序列化集成。
"""

from __future__ import annotations

from typing import Literal

# ── 项目相关 ──────────────────────────────────────────────

# 技术栈
Stack = Literal["plc", "python", "unknown"]

# 项目元数据来源（"" 表示未设置）
ProjectSource = Literal["copier", "plc_json", "pm_session", "dirname", ""]

# 项目阶段（对齐 PHASE_LABELS，"" 表示未设置）
ProjectPhase = Literal["developing", "commissioning", "production", "archived", ""]

# ── 变更单相关（CHG-040）──────────────────────────────────

# 变更单状态（对齐 STATUS_FLOW 的 key）
ChangeStatus = Literal[
    "draft",
    "submitted",
    "under_review",
    "approved",
    "conditionally_approved",
    "rejected",
    "implementing",
    "pending_acceptance",
    "accepting",
    "completed",
    "closed",
    "archived",
]

# 技术领域（§3.1，"" 表示未设置）
Domain = Literal["ELEC", "MECH", "PLC", "HMI", "SCPT", "DOCU", "SAFE", ""]

# 业务性质（§3.2，"" 表示未设置）
BusinessNature = Literal["REQ", "DEF", "OPT", "CFG", "EMRG", ""]

# 影响范围（§3.3，"" 表示未设置，用于列表项中可能为空的情况）
ImpactScope = Literal["LOCAL", "MODULE", "SYSTEM", "CROSS", "SAFE", ""]

# 紧急程度（§3.4）
Urgency = Literal["normal", "urgent", "critical"]

# ── PLC 检查相关 ──────────────────────────────────────────

# 检查项状态
CheckStatus = Literal["pass", "warn", "fail"]

# 修复动作状态
RepairStatus = Literal["fixed", "skipped", "failed"]

# 项目类型（substance_check 为运行期标记，用于文档实质化检查）
ProjectType = Literal["standard", "syslib_fb", "substance_check"]

# 文档类型
DocType = Literal["REQ", "INT", "DSN", "TEC"]
