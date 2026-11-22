"""PLC-HMI 概念映射：SFB 库函数（PLC 数据模型（检查结果/修复记录的数据结构））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

PLC 项目数据模型与常量（LSP-907 907_项目配置规范_LSP）

迁移自 SW-2026-005 的 plc_project_service.py 数据结构。

数据模型已迁移至 auto_pm/models/plc.py（Pydantic v2）。
本文件保留规范常量，并重新导出模型以保持向后兼容。
"""

from __future__ import annotations

from typing import Any

from auto_pm.core.paths import PG_INITIATING_DIR
from auto_pm.models.plc import (  # noqa: F401
    CheckItem,
    CheckResult,
    RenamePlan,
    RepairAction,
    RepairResult,
    StandardizeResult,
)

# CHG-SCPT-2026-146: 5大过程组重组 - PLC 项目管理目录候选
# 新模板使用 01_启动（5大过程组），旧项目使用 00_项目管理（向后兼容）
PM_DIR_CANDIDATES: list[str] = [PG_INITIATING_DIR, "00_项目管理"]

# 旧路径常量（阶段3.5物理迁移后移除）
_LEGACY_PM_DIR_PLC: str = "00_项目管理"
_LEGACY_PROJECT_INIT_PLC_PATH: list[str] = ["00_项目管理", "01_立项与需求"]

# 显式导出（mypy strict 模式要求）
__all__ = [
    "CheckItem",
    "CheckResult",
    "RenamePlan",
    "RepairAction",
    "RepairResult",
    "StandardizeResult",
]

# ── 常量 ──────────────────────────────────────────────────

# 标准 PLC 项目目录结构（LSP-907 §3.1）
# CHG-SCPT-2026-146: 5大过程组，01_启动 替代 00_项目管理
STD_DIRS: list[str] = [
    PG_INITIATING_DIR,
    "02_PLC程序",
    "03_HMI设计",
    "04_现场调试",
    "05_测试与验证",
    "06_文档与交付",
    "07_技术支持",
    "08_备件管理",
    "09_项目总结",
    "10_知识库",
]

# PRD 文档模板集（LSP-907 + SysLib FB 标准）
STD_PRDS: list[str] = [
    "需求分析文档_REQ.md",
    "接口文档_INT.md",
    "详细设计说明书_DSN.md",
    "技术方案文档_TEC.md",
]

# FB 级 PRD 四件套（L3 层，每个 FB 模块的 PRD/ 子目录下应包含）
# CHG-SCPT-2026-153: 基于 DJ-2026-005 实战，plc check 原只检查 L2 级 REQ/INT/DSN/TEC，
# 不检查 FB 级 IFC/DSN/CHG/UM，导致 4/7 模块四件套不完整仍 21/21 全绿通过
FB_PRDS: list[tuple[str, str]] = [
    ("IFC", "接口文档_IFC-"),
    ("DSN", "详细设计说明书_DSN-"),
    ("CHG", "变更记录_CHG-"),
    ("UM", "使用说明_UM-"),
]

# FB PRD 扫描目录（PLC_ST 下各 FB 模块目录，排除 00_ 前缀的基础设施目录）
# 00_主程序、00_全局数据、00_程序方案 的 PRD 在 L2 层 STD_PRDS 中已覆盖
FB_PRD_SCAN_DIR: str = "02_PLC程序/PLC_ST"
FB_PRD_SKIP_DIRS: set[str] = {"00_主程序", "00_全局数据", "00_程序方案", "99_基线", "Test", "PRD"}

# .plc.json 必填字段（LSP-907 §1.1）
REQUIRED_PLC_JSON_FIELDS: list[str] = ["name", "description", "version"]

# 允许缺失 .plc.json 的库类型（SysLib FB 项目无 .plc.json）
SKIP_PLC_JSON_TYPES: list[str] = ["syslib_fb"]

# PRD 文档命名规范映射（标准名 → 非标准匹配模式）
NAMING_RULES: dict[str, dict[str, Any]] = {
    "需求分析文档_REQ.md": {
        "doc_type": "REQ",
        "prefix": "需求",
        "patterns": [r"^需求文档_PRD-.*\.md$", r"^.*_REQ\.md$"],
    },
    "接口文档_INT.md": {
        "doc_type": "INT",
        "prefix": "接口",
        "patterns": [r"^接口文档_IFC-.*\.md$", r"^.*_INT\.md$"],
    },
    "详细设计说明书_DSN.md": {
        "doc_type": "DSN",
        "prefix": "详细设计",
        "patterns": [r"^详细设计说明书_DSN-.*\.md$", r"^.*_DSN\.md$"],
    },
    "技术方案文档_TEC.md": {
        "doc_type": "TEC",
        "prefix": "技术方案",
        "patterns": [r"^技术方案文档_TEC-.*\.md$", r"^.*_TEC\.md$"],
    },
}


# 数据模型已迁移至 auto_pm/models/plc.py（Pydantic v2）
# 此处通过顶部 import 重新导出，保持向后兼容：
#   from auto_pm.plc.models import CheckResult, RepairResult, ...
