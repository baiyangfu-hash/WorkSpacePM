"""PLC-HMI 概念映射：SFB 库函数（路径解析器（变更单路径计算/变量替换））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

路径解析（工作空间约定）

CHG-SCPT-2026-146 5大过程组重组后统一目录约定：
  - 所有项目：04_监控/01_变更管理/01_变更单/CHG-*.md
  - 立项表：01_启动/*_PROJ.md 或 *_PM.md
  - 台帐：04_监控/01_变更管理/02_变更记录/01_版本变更台帐.md

破坏性切换：不再区分 PLC / Python 两套路径，默认统一使用 5大过程组路径；
旧路径（11_监控 / 00_项目管理）保留为过渡兼容，待历史项目迁移后逐步下线。
"""

from __future__ import annotations

import os
import re

from auto_pm.core.paths import (
    CHANGE_RECORDS_PATH,
    CHANGE_SCAN_PATH,
    PROJECT_INIT_PATH,
)

# ── 安全校验 ──────────────────────────────────────────────

# project_id 允许的字符：字母、数字、连字符、下划线
_PROJECT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_\-]+$")

# change_number 允许的格式：CHG-{DOMAIN}-{YYYY}-{XXX}
_CHANGE_NUMBER_PATTERN = re.compile(r"^CHG-[A-Z]+-\d{4}-\d{3}$")


class PathTraversalError(ValueError):
    """路径遍历攻击检测异常"""
    pass


def validate_project_id(project_id: str) -> str:
    """校验 project_id 防止路径遍历

    规则:
      - 非空
      - 仅允许字母、数字、连字符、下划线
      - 不允许包含路径分隔符或 .. 等遍历字符

    Args:
        project_id: 项目编号，如 DJ-2026-005

    Returns:
        校验通过的 project_id

    Raises:
        PathTraversalError: 检测到路径遍历攻击
    """
    if not project_id:
        raise PathTraversalError("项目编号不能为空")
    if not _PROJECT_ID_PATTERN.match(project_id):
        raise PathTraversalError(
            f"项目编号包含非法字符: '{project_id}'，"
            "仅允许字母、数字、连字符、下划线"
        )
    if ".." in project_id or "/" in project_id or "\\" in project_id:
        raise PathTraversalError(
            f"项目编号包含路径遍历字符: '{project_id}'"
        )
    return project_id


def validate_change_number(change_number: str) -> str:
    """校验 change_number 防止路径遍历

    规则:
      - 必须匹配 CHG-{DOMAIN}-{YYYY}-{XXX} 格式
      - DOMAIN 仅允许大写字母

    Args:
        change_number: 变更编号，如 CHG-DOCU-2026-001

    Returns:
        校验通过的 change_number

    Raises:
        PathTraversalError: 检测到路径遍历攻击或格式不合法
    """
    if not change_number:
        raise PathTraversalError("变更编号不能为空")
    if not _CHANGE_NUMBER_PATTERN.match(change_number):
        raise PathTraversalError(
            f"变更编号格式不合法: '{change_number}'，"
            "应为 CHG-{{DOMAIN}}-{{YYYY}}-{{XXX}} 格式"
        )
    return change_number


def validate_path_within_workspace(path: str, workspace_root: str) -> str:
    """校验路径在工作空间范围内，防止路径遍历

    Args:
        path: 待校验的绝对路径
        workspace_root: 工作空间根目录绝对路径

    Returns:
        校验通过的规范化路径

    Raises:
        PathTraversalError: 路径超出工作空间范围
    """
    real_workspace = os.path.realpath(workspace_root)
    real_path = os.path.realpath(path)
    if not real_path.startswith(real_workspace + os.sep) and real_path != real_workspace:
        raise PathTraversalError(
            f"路径超出工作空间范围: '{path}' 不在 '{workspace_root}' 内"
        )
    return real_path


# ── 目录约定 ──────────────────────────────────────────────

# 立项表搜索路径（按优先级排列，命中即停）
# CHG-SCPT-2026-146: 5大过程组统一路径（默认路径）
_PROJ_SEARCH_PATHS = [
    # 5大过程组统一路径：01_启动/
    tuple(PROJECT_INIT_PATH),
    # 兼容：直接在项目根目录下
    (),
]

# 立项表文件名匹配模式（按优先级排列）
_PROJ_FILE_PATTERNS = [
    re.compile(r"_PROJ\.md$", re.IGNORECASE),
    re.compile(r"立项表.*\.md$", re.IGNORECASE),
    re.compile(r"_PM\.md$", re.IGNORECASE),
]

# 变更单搜索路径（按优先级排列）
# CHG-SCPT-2026-146 后默认使用 5 大过程组路径（递归扫描 04_监控/01_变更管理/）；
# 为兼容历史项目（如 DJ-2026-009），仍保留 11_监控 / 00_项目管理 旧路径兜底，属过渡兼容期，
# 待历史项目台账迁移完成后逐步下线。
_CHANGE_SEARCH_PATHS = [
    os.path.join(*CHANGE_SCAN_PATH),
    os.path.join("11_监控", "01_变更管理"),
    os.path.join("00_项目管理", "01_变更管理"),
    os.path.join("11_监控"),
]


def find_proj_file(project_path: str) -> str | None:
    """在项目目录下查找立项表文件

    按优先级搜索多套目录约定，命中即返回。
    """
    for search_parts in _PROJ_SEARCH_PATHS:
        search_dir = os.path.join(project_path, *search_parts) if search_parts else project_path
        if not os.path.isdir(search_dir):
            continue
        for name in sorted(os.listdir(search_dir)):
            if not name.endswith(".md"):
                continue
            for pattern in _PROJ_FILE_PATTERNS:
                if pattern.search(name):
                    return os.path.join(search_dir, name)
    return None


def scan_change_files(project_path: str) -> list[str]:
    """扫描变更单文件

    CHG-SCPT-2026-146: 5大过程组统一路径，递归扫描 04_监控/01_变更管理/ 下的 CHG-*.md
    """
    results: list[str] = []
    seen: set[str] = set()
    for rel_path in _CHANGE_SEARCH_PATHS:
        base_dir = os.path.join(project_path, rel_path)
        if not os.path.isdir(base_dir):
            continue
        _scan_change_dir(base_dir, results)
    # 去重并保持顺序
    deduped: list[str] = []
    for p in results:
        norm = os.path.normpath(p)
        if norm not in seen:
            seen.add(norm)
            deduped.append(p)
    return deduped


def _scan_change_dir(base_dir: str, results: list[str], depth: int = 0, max_depth: int = 3) -> None:
    """递归扫描变更单目录，查找 CHG-*.md 文件"""
    try:
        entries = sorted(os.listdir(base_dir))
    except PermissionError:
        return
    for name in entries:
        full_path = os.path.join(base_dir, name)
        if os.path.isdir(full_path):
            # 递归进入子目录（如 CHG-DOCU/、CHG-PLC/ 等）
            if depth < max_depth:
                _scan_change_dir(full_path, results, depth + 1, max_depth)
        elif name.startswith("CHG-") and name.endswith(".md"):
            results.append(full_path)


# 台帐搜索路径（按优先级排列）
# CHG-SCPT-2026-146: 5大过程组统一路径，并兼容 11_监控 及历史目录
_LEDGER_SEARCH_PATHS = [
    # 5大过程组统一路径：04_监控/01_变更管理/02_变更记录/
    os.path.join(*CHANGE_RECORDS_PATH),
    os.path.join("11_监控", "01_变更管理", "02_变更记录"),
    os.path.join("00_项目管理", "01_变更管理", "02_变更记录"),
    os.path.join("11_监控", "02_变更记录"),
]

# 台帐文件名匹配模式
_LEDGER_FILE_PATTERNS = [
    re.compile(r"版本变更台帐.*\.md$", re.IGNORECASE),
    re.compile(r"变更台帐.*\.md$", re.IGNORECASE),
]


def find_ledger_file(project_path: str) -> str | None:
    """查找版本变更台帐文件

    CHG-SCPT-2026-146: 5大过程组统一路径，搜索 04_监控/01_变更管理/02_变更记录/ 下的台帐文件。
    """
    for rel_path in _LEDGER_SEARCH_PATHS:
        search_dir = os.path.join(project_path, rel_path)
        if not os.path.isdir(search_dir):
            continue
        for name in sorted(os.listdir(search_dir)):
            if not name.endswith(".md"):
                continue
            for pattern in _LEDGER_FILE_PATTERNS:
                if pattern.search(name):
                    return os.path.join(search_dir, name)
    return None


def get_or_create_ledger_file(project_path: str) -> str | None:
    """查找或创建版本变更台帐文件

    CHG-SCPT-2026-146: 5大过程组统一路径，破坏性切换后不再区分 PLC / Python。
    若台帐文件不存在，按统一路径自动创建（04_监控/01_变更管理/02_变更记录/01_版本变更台帐.md），
    含「变更单索引」表格骨架，供 LedgerUpdater 追加记录。

    Args:
        project_path: 项目根目录

    Returns:
        台帐文件路径，失败返回 None
    """
    # 1. 先查找已有台帐
    existing = find_ledger_file(project_path)
    if existing:
        return existing

    # 2. 未找到 → 按统一路径创建
    ledger_dir = os.path.join(project_path, _LEDGER_SEARCH_PATHS[0])
    ledger_path = os.path.join(ledger_dir, "01_版本变更台帐.md")

    try:
        os.makedirs(ledger_dir, exist_ok=True)
        # 写入台帐骨架（含变更单索引表格，与 LedgerUpdater 期望的结构对齐）
        skeleton = (
            "# 版本变更台帐\n\n"
            "> 记录项目所有变更单的索引与状态\n\n"
            "## 变更单索引\n\n"
            "| 序号 | 变更编号 | 领域 | 申请人 | 申请日期 | 变更描述 | 完成日期 | 状态 |\n"
            "|------|----------|------|--------|----------|----------|----------|------|\n"
        )
        from auto_pm.utils.file_utils import write_file
        write_file(ledger_path, skeleton)
        return ledger_path
    except OSError:
        return None


def get_project_id_from_path(project_path: str) -> str:
    """从项目目录路径提取项目编号

    例: C:\\...\\0100_PLC自动化\\DJ-2026-005\\ → DJ-2026-005
    """
    return os.path.basename(project_path)


def extract_domain_from_change_number(change_number: str) -> str:
    """从变更编号提取领域

    例: CHG-DOCU-2026-001 → DOCU
    """
    parts = change_number.split("-")
    if len(parts) >= 2:
        return parts[1]
    return ""
