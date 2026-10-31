"""PLC-HMI 概念映射：SFB 库函数（常量定义（如 PLC 的常量表/符号表））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

统一常量定义（M3-Iter7）

集中定义技术栈模板映射、业务线选项等常量，消除散落在各模块的重复定义。

来源：
- LSP-907 907_项目配置规范_LSP：PLC 技术栈规范
- 210/211/220：Python 技术栈规范
- 项目管理规范：业务线编码定义
"""

from __future__ import annotations

import os
from typing import Final

# ── 技术栈 → 模板名映射 ───────────────────────────────────

#: 技术栈到 Copier 模板名的映射（默认模板）
STACK_TEMPLATE_MAP: Final[dict[str, str]] = {
    "plc": "plc-standard-project",
    "python": "python-tool",
}

#: PLC 项目模式到模板名的映射
PLC_MODE_TEMPLATE_MAP: Final[dict[str, str]] = {
    "shared-library": "plc-shared-library",
    "test-suite": "plc-test-suite",
    "standard-project": "plc-standard-project",
}

#: PLC 项目模式选项列表（用于 CLI 和 UI）
PLC_MODE_OPTIONS: Final[list[tuple[str, str]]] = [
    ("shared-library", "公共库"),
    ("test-suite", "公共库验证"),
    ("standard-project", "标准单机项目"),
]

#: 默认 PLC 项目模式
DEFAULT_PLC_MODE: Final[str] = "standard-project"

#: 默认模板名（技术栈未知时使用）
DEFAULT_TEMPLATE_NAME: Final[str] = "unknown"


def get_plc_template_name(mode: str = DEFAULT_PLC_MODE) -> str:
    """根据 PLC 项目模式获取模板名

    Args:
        mode: PLC 项目模式 (shared-library/test-suite/standard-project)

    Returns:
        模板名，未知模式返回标准项目模板
    """
    return PLC_MODE_TEMPLATE_MAP.get(mode, PLC_MODE_TEMPLATE_MAP[DEFAULT_PLC_MODE])


def get_template_name(stack: str, mode: str = "") -> str:
    """根据技术栈获取模板名

    Args:
        stack: 技术栈标识 (plc/python/unknown)
        mode: PLC 项目模式（仅 stack=="plc" 时有效）

    Returns:
        模板名，未知技术栈返回 DEFAULT_TEMPLATE_NAME
    """
    if stack == "plc" and mode:
        return get_plc_template_name(mode)
    return STACK_TEMPLATE_MAP.get(stack, DEFAULT_TEMPLATE_NAME)


# ── 业务线选项 ─────────────────────────────────────────────

#: 业务线选项列表：(value, label) 格式，用于 UI 下拉框和 CLI 选项
BUSINESS_LINE_OPTIONS: Final[list[tuple[str, str]]] = [
    ("SW", "SW 软件开发"),
    ("DJ", "DJ 单机设备"),
    ("ZD", "ZD 自动化整线"),
    ("XT", "XT 系统升级"),
    ("WX", "WX 维保项目"),
]

#: 业务线编码列表（仅 value）
BUSINESS_LINE_CODES: Final[list[str]] = [opt[0] for opt in BUSINESS_LINE_OPTIONS]

#: 业务线编码到标签的映射
BUSINESS_LINE_LABELS: Final[dict[str, str]] = dict(BUSINESS_LINE_OPTIONS)


def get_business_line_label(code: str) -> str:
    """根据业务线编码获取标签

    Args:
        code: 业务线编码 (SW/DJ/ZD/XT/WX)

    Returns:
        业务线标签，未知编码返回编码本身
    """
    return BUSINESS_LINE_LABELS.get(code, code)


def is_valid_business_line(code: str) -> bool:
    """检查业务线编码是否合法"""
    return code in BUSINESS_LINE_CODES


# ── 技术栈 → 工作空间子目录映射（V0.2.1-P1-7） ─────────────

#: 技术栈到工作空间子目录的映射（项目应创建在对应技术栈目录下）
STACK_WORKSPACE_SUBDIR_MAP: Final[dict[str, str]] = {
    "plc": "0100_PLC自动化",
    "python": os.path.join("01_Project自动化项目管理", "Python自动化项目总库", "02_在研项目"),
}


def get_workspace_subdir(stack: str) -> str:
    """根据技术栈获取工作空间子目录

    Args:
        stack: 技术栈标识 (plc/python)

    Returns:
        工作空间子目录相对路径，未知技术栈返回空字符串（表示在根目录创建）
    """
    return STACK_WORKSPACE_SUBDIR_MAP.get(stack, "")


# ── 技术栈选项 ─────────────────────────────────────────────

#: 技术栈选项列表：(value, label) 格式
STACK_OPTIONS: Final[list[tuple[str, str]]] = [
    ("plc", "PLC 自动化"),
    ("python", "Python 工具"),
]

#: 技术栈编码列表
STACK_CODES: Final[list[str]] = [opt[0] for opt in STACK_OPTIONS]


# ── 项目阶段选项 ───────────────────────────────────────────

#: 项目阶段选项列表：(value, label) 格式
PHASE_OPTIONS: Final[list[tuple[str, str]]] = [
    ("initiating", "启动中"),
    ("planning", "规划中"),
    ("developing", "开发中"),
    ("commissioning", "调试中"),
    ("production", "已投产"),
    ("archived", "已归档"),
]

#: 项目阶段编码列表
PHASE_CODES: Final[list[str]] = [opt[0] for opt in PHASE_OPTIONS]

#: 项目阶段编码到标签的映射
PHASE_LABELS: Final[dict[str, str]] = dict(PHASE_OPTIONS)


def get_phase_label(code: str) -> str:
    """根据阶段编码获取标签"""
    return PHASE_LABELS.get(code, code)


# ── V0.4.0 项目元数据选项 ──────────────────────────────────

#: 项目类型选项列表：(value, label) 格式
PROJECT_TYPE_OPTIONS: Final[list[tuple[str, str]]] = [
    ("single_machine", "单机设备"),
    ("line_project", "自动化整线"),
    ("retrofit_project", "改造项目"),
    ("maintenance_project", "维保项目"),
    ("shared_library", "标准库/功能块"),
    ("test_suite", "测试台/仿真项目"),
]

#: 项目类型编码列表
PROJECT_TYPE_CODES: Final[list[str]] = [opt[0] for opt in PROJECT_TYPE_OPTIONS]

#: 项目类型编码到标签的映射
PROJECT_TYPE_LABELS: Final[dict[str, str]] = dict(PROJECT_TYPE_OPTIONS)


def get_project_type_label(code: str) -> str:
    """根据项目类型编码获取标签"""
    return PROJECT_TYPE_LABELS.get(code, code)


#: 设备类型选项列表：(value, label) 格式
EQUIPMENT_TYPE_OPTIONS: Final[list[tuple[str, str]]] = [
    ("conveyor", "输送设备"),
    ("packaging", "包装设备"),
    ("palletizer", "码垛设备"),
    ("robot_cell", "机器人单元"),
    ("test_rig", "测试台"),
    ("other", "其他"),
]

#: 设备类型编码列表
EQUIPMENT_TYPE_CODES: Final[list[str]] = [opt[0] for opt in EQUIPMENT_TYPE_OPTIONS]

#: 设备类型编码到标签的映射
EQUIPMENT_TYPE_LABELS: Final[dict[str, str]] = dict(EQUIPMENT_TYPE_OPTIONS)


def get_equipment_type_label(code: str) -> str:
    """根据设备类型编码获取标签"""
    return EQUIPMENT_TYPE_LABELS.get(code, code)


#: PLC 品牌选项列表：(value, label) 格式
PLC_VENDOR_OPTIONS: Final[list[tuple[str, str]]] = [
    ("Siemens", "Siemens"),
    ("Mitsubishi", "Mitsubishi"),
    ("Omron", "Omron"),
    ("Keyence", "Keyence"),
    ("Beckhoff", "Beckhoff"),
    ("Delta", "Delta"),
    ("Other", "Other"),
]

#: PLC 品牌编码列表
PLC_VENDOR_CODES: Final[list[str]] = [opt[0] for opt in PLC_VENDOR_OPTIONS]
