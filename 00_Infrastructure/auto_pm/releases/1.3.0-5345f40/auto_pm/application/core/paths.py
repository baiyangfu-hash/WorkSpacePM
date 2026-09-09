"""PLC-HMI 概念映射：SFB 库函数（路径工具（工作空间路径解析/标准化））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

统一路径约定常量（CHG-SCPT-2026-146 5大过程组重组）

集中定义工作空间和项目内的目录结构约定，消除散落在各模块的硬编码路径。

目录约定来源：
- PROJ-016 V1.2.0：5大过程组项目结构模板（启动/规划/执行/监控/收尾）
- 043 V2.0.0：变更管理目录结构（04_监控/01_变更管理/）
- 210/211/220：Python 项目目录结构

破坏性切换说明（CHG-SCPT-2026-146）：
- 删除 PM_DIR_PLC/PM_DIR_PYTHON/PROJECT_INFO_DIR 等旧常量
- 新增5大过程组目录常量（PG_INITIATING_DIR 等）
- 变更管理路径统一为 04_监控/01_变更管理/（不再区分 PLC/Python）
- PLC 项目旧路径（00_项目管理/）暂由 plc/checker.py 硬编码保留，阶段3.2更新模板时统一迁移
"""

from __future__ import annotations

import os
from typing import Final

# ── 工作空间级目录 ─────────────────────────────────────────

#: 工作空间下存放"在研项目"的子目录
WORKSPACE_PROJECTS_SUBDIR: Final[str] = "02_在研项目"


# ── 5大过程组目录（CHG-SCPT-2026-146） ─────────────────────

#: 启动过程组目录（项目基础信息、立项表）
PG_INITIATING_DIR: Final[str] = "01_启动"

#: 规划过程组目录（PRD/INT/DSN/TEC/里程碑）
PG_PLANNING_DIR: Final[str] = "02_规划"

#: 执行过程组目录（迭代计划、迭代记录）
PG_EXECUTING_DIR: Final[str] = "03_执行"

#: 监控过程组目录（变更管理、整改项、台账对账）
PG_MONITORING_DIR: Final[str] = "04_监控"

#: 收尾过程组目录（发布说明、交付清单、PM_SESSION归档）
PG_CLOSING_DIR: Final[str] = "05_收尾"

#: 5大过程组目录列表（用于项目识别和结构检查）
PROCESS_GROUP_DIRS: Final[list[str]] = [
    PG_INITIATING_DIR,
    PG_PLANNING_DIR,
    PG_EXECUTING_DIR,
    PG_MONITORING_DIR,
    PG_CLOSING_DIR,
]


# ── 项目级目录（PLC 项目，LSP-907 §3.1） ────────────────────
# 注：PLC_STD_DIRS 暂保留旧结构，阶段3.2更新 PLC 模板时统一迁移到5大过程组

#: PLC 项目根目录下的标准子目录（LSP-907 §3.1，暂保留旧结构）
PLC_STD_DIRS: Final[list[str]] = [
    "02_PLC程序/通用ST程序及变量表",
    "03_HMI设计",
    "04_现场调试",
    "04_变更管理",
    "PRD",
]

#: PRD 文档目录名（默认/首选）
PRD_DIR: Final[str] = "PRD"

#: PRD 文档目录名候选列表（按优先级排序，用于兼容不同命名习惯）
#: 支持: PRD（标准）、00_程序方案（DJ-2026-005 等定制项目）
PRD_DIR_CANDIDATES: Final[list[str]] = ["PRD", "00_程序方案"]


# ── 变更管理目录（CHG-SCPT-2026-146 5大过程组统一） ────────

#: 变更单存放目录（5大过程组统一路径，不再区分 PLC/Python）
CHANGE_REQUESTS_PATH: Final[list[str]] = [
    PG_MONITORING_DIR, "01_变更管理", "01_变更单"
]

#: 变更记录存放目录（5大过程组统一路径）
CHANGE_RECORDS_PATH: Final[list[str]] = [
    PG_MONITORING_DIR, "01_变更管理", "02_变更记录"
]

#: 变更单扫描路径（不含最后的 01_变更单，用于递归扫描）
CHANGE_SCAN_PATH: Final[list[str]] = [
    PG_MONITORING_DIR, "01_变更管理"
]

#: 立项表搜索路径（5大过程组统一路径）
PROJECT_INIT_PATH: Final[list[str]] = [PG_INITIATING_DIR]

#: Python 项目规范必需目录
PYTHON_REQUIRED_DIRS: Final[list[str]] = ["tests", PG_INITIATING_DIR]


# ── PRD 文档命名（LSP-907 + SysLib FB 标准） ───────────────

#: 标准 PRD 文档列表
STD_PRD_DOCS: Final[list[str]] = [
    "需求分析文档_REQ.md",
    "接口文档_INT.md",
    "详细设计说明书_DSN.md",
    "技术方案文档_TEC.md",
]


# ── 默认项目存放目录（V1.0.1 新增） ─────────────────────────

#: 默认项目存放目录名（相对于 auto-pm 工具目录）
DEFAULT_PROJECTS_DIRNAME: Final[str] = "0100_项目"


# ── 便捷函数 ───────────────────────────────────────────────

def join_path(*parts: str) -> str:
    """跨平台拼接路径（os.path.join 的语义化包装）"""
    return os.path.join(*parts)


def get_config_file_path() -> str:
    """获取全局配置文件 (.auto-pm-workspace) 的路径

    统一位于工具根目录下。
    """
    tool_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(tool_dir, ".auto-pm-workspace")


def get_default_projects_dir() -> str:
    """获取默认项目存放根目录（auto-pm 工具目录下的 0100_项目/）

    通过 paths.py 文件位置推断 auto-pm 工具目录，不依赖 workspace_root 配置。
    项目默认创建在此目录下，用户可通过 GUI/CLI 指定其他目录覆盖。

    Returns:
        默认项目存放根目录绝对路径
    """
    # paths.py 位于 auto_pm/core/paths.py
    # 工具目录 = auto_pm/ 的上级目录
    tool_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(tool_dir, DEFAULT_PROJECTS_DIRNAME)


def get_projects_subdir(workspace_root: str) -> str:
    """获取工作空间下的"在研项目"目录路径"""
    return os.path.join(workspace_root, WORKSPACE_PROJECTS_SUBDIR)


def get_change_requests_paths(project_path: str) -> list[str]:
    """获取变更单存放目录路径（5大过程组统一路径，CHG-SCPT-2026-146）

    Args:
        project_path: 项目根目录

    Returns:
        包含变更单目录绝对路径的列表（单元素，破坏性切换后不再有多路径回退）
    """
    return [os.path.join(project_path, *CHANGE_REQUESTS_PATH)]


def get_change_records_paths(project_path: str) -> list[str]:
    """获取变更记录存放目录路径（5大过程组统一路径，CHG-SCPT-2026-146）

    Args:
        project_path: 项目根目录

    Returns:
        包含变更记录目录绝对路径的列表（单元素）
    """
    return [os.path.join(project_path, *CHANGE_RECORDS_PATH)]


def get_prd_dir(project_path: str) -> str:
    """获取 PRD 文档目录路径（使用默认目录名 PRD）"""
    return os.path.join(project_path, PRD_DIR)


#: PRD 目录搜索路径（相对于项目根目录，按优先级排序）
#: 空字符串 "" 表示项目根目录本身
_PRD_SEARCH_PATHS: Final[list[str]] = [
    "",                         # 项目根目录（Python/非PLC项目）
    "02_PLC程序/PLC_ST",        # 标准PLC项目嵌套路径
]


def find_prd_dir(project_path: str) -> tuple[str, str] | None:
    """查找实际存在的 PRD 文档目录（按候选列表优先级，多层搜索）

    搜索策略：
    1. 先搜项目根目录下的候选目录名
    2. 再搜常见嵌套路径（如 02_PLC程序/PLC_ST/）下的候选目录名

    Args:
        project_path: 项目根目录

    Returns:
        (绝对路径, 目录名) 或 None（未找到任何候选目录）
    """
    for search_path in _PRD_SEARCH_PATHS:
        base = os.path.join(project_path, search_path) if search_path else project_path
        for candidate in PRD_DIR_CANDIDATES:
            candidate_path = os.path.join(base, candidate)
            if os.path.isdir(candidate_path):
                return (candidate_path, candidate)
    return None
