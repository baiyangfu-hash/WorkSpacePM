"""PLC-HMI 概念映射：SFB 库函数（规范快照（保存/恢复 PLC 规范检查状态））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

Spec Snapshot 解析器 - 规范版本漂移检测基础模块（V2.0.3）

提供 PM_SESSION Spec Snapshot 表格解析、spec_registry.json 加载、版本对比能力，
供 PlcChecker/PlcRepairer 调用以检测和修复规范版本漂移。

注意：本模块虽位于 plc/ 目录，但不依赖任何 PLC 特性，可被 project 级命令复用
（如 `auto-pm project snapshot` 命令）。

职责：
- parse_spec_snapshot: 解析 PM_SESSION 中的 Spec Snapshot 表格为 dict[规范ID→版本号]
- load_spec_registry: 加载 spec_registry.json 提取规范ID→版本号映射
- compare_versions: 对比 snapshot 与 registry 版本差异，判定漂移级别
- update_spec_snapshot: 将漂移项的版本号更新为 registry 中的最新版本（写回 PM_SESSION）
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime

from auto_pm.utils.file_utils import StaleFileError, read_file_snapshot, write_file

log = logging.getLogger(__name__)

# spec_registry.json 相对路径（相对工作空间根目录）
_REGISTRY_REL_PATH = os.path.join("00_Obsidian_Base全局规范文件仓库", "spec_registry.json")

# Spec Snapshot 章节标题正则（匹配 `## Spec Snapshot` 及其变体，容忍尾部说明）
_SNAPSHOT_HEADING_RE = re.compile(r"^##\s+Spec\s+Snapshot", re.IGNORECASE)

# 版本号正则：V主.次.补丁（如 V1.0.0, V2.1.3）
_VERSION_RE = re.compile(r"^V(\d+)\.(\d+)\.(\d+)$", re.IGNORECASE)

# spec_id 列关键词（小写匹配，容忍列名变体）
_SPEC_ID_KEYWORDS = ("规范编号", "规范id", "spec_id")

# 版本号列关键词（小写匹配，容忍列名变体）
_VERSION_KEYWORDS = ("版本号", "版本", "version")


@dataclass
class DriftItem:
    """规范版本漂移项

    Attributes:
        spec_id: 规范ID（如 "LSP-906"）
        snapshot_version: PM_SESSION 中记录的版本号（如 "V1.0.0"）
        registry_version: spec_registry.json 中的版本号（如 "V2.0.0"）
        drift_level: 漂移级别："major" | "minor" | "patch"
    """

    spec_id: str
    snapshot_version: str
    registry_version: str
    drift_level: str


def parse_spec_snapshot(pm_session_path: str) -> dict[str, str]:
    """解析 PM_SESSION 中的 Spec Snapshot 表格

    查找 `## Spec Snapshot` 标题下的 Markdown 表格，解析为 dict[规范ID→版本号]。
    表格列名容忍变体（如"规范编号"/"规范ID"/"spec_id"，"版本号"/"版本"/"version"）。

    Args:
        pm_session_path: PM_SESSION markdown 文件路径

    Returns:
        规范ID→版本号映射；非标准格式或文件缺失返回空 dict，不抛异常
    """
    if not os.path.isfile(pm_session_path):
        log.debug("PM_SESSION 文件不存在: %s", pm_session_path)
        return {}

    try:
        with open(pm_session_path, encoding="utf-8") as f:
            content = f.read()
    except OSError as e:
        log.warning("读取 PM_SESSION 失败: %s (%s)", pm_session_path, e)
        return {}

    lines = content.splitlines()

    # 1. 查找 Spec Snapshot 标题
    heading_idx = -1
    for i, line in enumerate(lines):
        if _SNAPSHOT_HEADING_RE.match(line.strip()):
            heading_idx = i
            break

    if heading_idx == -1:
        log.debug("未找到 Spec Snapshot 章节: %s", pm_session_path)
        return {}

    # 2. 从标题后查找首个 Markdown 表格（连续以 | 开头的行）
    table_lines: list[str] = []
    in_table = False
    for line in lines[heading_idx + 1 :]:
        stripped = line.strip()
        if stripped.startswith("|"):
            in_table = True
            table_lines.append(stripped)
        elif in_table:
            # 表格结束（遇到非表格行）
            break
        # 表格前的空行/说明行跳过

    if len(table_lines) < 2:
        # 至少需要表头 + 分隔行 + 1 数据行 = 3 行，<2 必定无数据
        log.debug("Spec Snapshot 表格行数不足: %s", pm_session_path)
        return {}

    # 3. 解析表头，定位 spec_id 列与版本号列
    header_cells = _split_table_row(table_lines[0])
    spec_id_col = -1
    version_col = -1

    for idx, cell in enumerate(header_cells):
        cell_norm = cell.lower().replace(" ", "_").strip()
        if spec_id_col == -1 and any(kw in cell_norm for kw in _SPEC_ID_KEYWORDS):
            spec_id_col = idx
        if version_col == -1 and any(kw in cell_norm for kw in _VERSION_KEYWORDS):
            version_col = idx

    if spec_id_col == -1 or version_col == -1:
        log.debug(
            "Spec Snapshot 表头列名不匹配 (spec_id_col=%d, version_col=%d): %s",
            spec_id_col,
            version_col,
            pm_session_path,
        )
        return {}

    # 4. 解析数据行（跳过表头和分隔行）
    result: dict[str, str] = {}
    for row_line in table_lines[1:]:
        # 跳过分隔行（如 |---|---|）
        if re.match(r"^\|[\s\-:|]+\|$", row_line):
            continue

        cells = _split_table_row(row_line)
        if len(cells) <= max(spec_id_col, version_col):
            continue

        spec_id = cells[spec_id_col].strip()
        version = cells[version_col].strip()

        if spec_id and version:
            result[spec_id] = version

    log.debug("解析 Spec Snapshot 完成: %s (%d 条)", pm_session_path, len(result))
    return result


def load_spec_registry(workspace_root: str) -> dict[str, str] | None:
    """加载 spec_registry.json 提取规范ID→版本号映射

    支持两种 specs 结构：
    - dict 形式：{"specs": {"LSP-906": {"version": "V2.0.0", ...}, ...}}
    - list 形式：{"specs": [{"spec_id": "LSP-906", "version": "V2.0.0", ...}, ...]}

    Args:
        workspace_root: 工作空间根目录

    Returns:
        规范ID→版本号映射；文件缺失或格式错误返回 None，不抛异常
    """
    registry_path = os.path.join(workspace_root, _REGISTRY_REL_PATH)

    if not os.path.isfile(registry_path):
        log.debug("spec_registry.json 不存在: %s", registry_path)
        return None

    try:
        with open(registry_path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.warning("解析 spec_registry.json 失败: %s (%s)", registry_path, e)
        return None

    if not isinstance(data, dict):
        log.warning("spec_registry.json 顶层非 dict: %s", registry_path)
        return None

    specs = data.get("specs", [])
    result: dict[str, str] = {}

    if isinstance(specs, dict):
        # dict 形式：{spec_id: {"version": "V1.0.0", ...}, ...}
        for spec_id, spec_info in specs.items():
            if isinstance(spec_info, dict) and "version" in spec_info:
                result[spec_id] = str(spec_info["version"])
    elif isinstance(specs, list):
        # list 形式：[{"spec_id": "LSP-906", "version": "V1.0.0", ...}, ...]
        for item in specs:
            if isinstance(item, dict) and "spec_id" in item and "version" in item:
                result[str(item["spec_id"])] = str(item["version"])
    else:
        log.warning("spec_registry.json specs 字段非 dict/list: %s", registry_path)
        return None

    log.debug("加载 spec_registry.json 完成: %s (%d 条)", registry_path, len(result))
    return result


def compare_versions(
    snapshot: dict[str, str],
    registry: dict[str, str],
) -> list[DriftItem]:
    """对比 snapshot 与 registry 中的版本差异

    版本号格式：V主.次.补丁（如 V1.0.0, V2.0.0）。
    仅对比 snapshot 中存在且版本号可解析的规范（snapshot 是子集）。

    漂移级别判定：
    - 主版本不同（如 V1→V2）→ "major"
    - 次版本不同（如 V1.0→V1.2）→ "minor"
    - 补丁版本不同（如 V1.0.0→V1.0.1）→ "patch"

    Args:
        snapshot: PM_SESSION 解析出的规范ID→版本号映射
        registry: spec_registry.json 加载的规范ID→版本号映射

    Returns:
        漂移项列表（仅返回有差异的），无差异返回空列表
    """
    drifts: list[DriftItem] = []

    for spec_id, snap_ver in snapshot.items():
        if spec_id not in registry:
            continue

        reg_ver = registry[spec_id]

        snap_parsed = _parse_version(snap_ver)
        reg_parsed = _parse_version(reg_ver)

        if snap_parsed is None or reg_parsed is None:
            log.debug("版本号无法解析，跳过: %s (%s vs %s)", spec_id, snap_ver, reg_ver)
            continue

        if snap_parsed == reg_parsed:
            continue

        drift_level = _classify_drift(snap_parsed, reg_parsed)
        drifts.append(
            DriftItem(
                spec_id=spec_id,
                snapshot_version=snap_ver,
                registry_version=reg_ver,
                drift_level=drift_level,
            )
        )

    return drifts


def update_spec_snapshot(
    pm_session_path: str,
    drifts: list[DriftItem],
) -> bool:
    """将漂移项的版本号更新为 registry 中的最新版本（写回 PM_SESSION）

    对每个漂移项，使用正则匹配 PM_SESSION 表格中的 `| spec_id | snapshot_version |`
    格式，将 snapshot_version 替换为 registry_version。

    Args:
        pm_session_path: PM_SESSION markdown 文件路径
        drifts: 漂移项列表（由 compare_versions 产生）

    Returns:
        True 表示更新成功（至少更新了一条）；False 表示写入失败或无漂移项
    """
    if not drifts:
        return False

    if not os.path.isfile(pm_session_path):
        log.warning("PM_SESSION 文件不存在，无法更新: %s", pm_session_path)
        return False

    content, original_mtime = read_file_snapshot(pm_session_path)
    if not content:
        log.warning("读取 PM_SESSION 失败: %s", pm_session_path)
        return False

    # 正则替换每个漂移项的版本号
    # 匹配格式：| spec_id | snapshot_version |
    new_content = content
    for drift in drifts:
        pattern = re.compile(
            r"(\|\s*"
            + re.escape(drift.spec_id)
            + r"\s*\|\s*)"
            + re.escape(drift.snapshot_version)
            + r"(\s*\|)",
            re.MULTILINE,
        )

        def _repl(m: re.Match[str], d: DriftItem = drift) -> str:
            g1 = m.group(1) or ""
            g2 = m.group(2) or ""
            return str(g1) + str(d.registry_version) + str(g2)

        new_content = pattern.sub(_repl, new_content)

    if new_content == content:
        log.debug("无内容变更（可能版本号已一致）: %s", pm_session_path)
        return False

    try:
        write_file(pm_session_path, new_content, expected_mtime=original_mtime)
    except (OSError, StaleFileError) as e:
        log.warning("写入 PM_SESSION 失败: %s (%s)", pm_session_path, e)
        return False

    log.info("Spec Snapshot 已更新: %s (%d 条)", pm_session_path, len(drifts))
    return True


def ensure_spec_snapshot_section(
    pm_session_path: str,
    registry: dict[str, str],
    spec_ids: list[str] | None = None,
    snapshot_date: str | None = None,
) -> bool:
    """确保 PM_SESSION 中存在可解析的 Spec Snapshot 章节。

    当章节缺失或内容失效时，按给定规范清单重建该章节。
    若已存在章节，则整体替换该章节内容；否则追加到文末。
    """
    if not registry:
        return False

    if not os.path.isfile(pm_session_path):
        log.warning("PM_SESSION 文件不存在，无法补齐 Spec Snapshot: %s", pm_session_path)
        return False

    content, original_mtime = read_file_snapshot(pm_session_path)
    if not content:
        log.warning("读取 PM_SESSION 失败，无法补齐 Spec Snapshot: %s", pm_session_path)
        return False

    section = render_spec_snapshot_section(
        registry=registry,
        spec_ids=spec_ids,
        snapshot_date=snapshot_date,
    )
    pattern = re.compile(
        r"^##\s+Spec\s+Snapshot[^\n]*\n.*?(?=^##\s+|\Z)",
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )

    if pattern.search(content):
        new_content = pattern.sub(section + "\n", content, count=1)
    else:
        new_content = content.rstrip() + "\n\n" + section + "\n"

    if new_content == content:
        return False

    try:
        write_file(pm_session_path, new_content, expected_mtime=original_mtime)
    except (OSError, StaleFileError) as e:
        log.warning("写入 Spec Snapshot 章节失败: %s (%s)", pm_session_path, e)
        return False

    log.info("Spec Snapshot 章节已补齐: %s", pm_session_path)
    return True


def render_spec_snapshot_section(
    registry: dict[str, str],
    spec_ids: list[str] | None = None,
    snapshot_date: str | None = None,
) -> str:
    """生成标准化的 Spec Snapshot Markdown 章节。"""
    date_text = snapshot_date or datetime.now().strftime("%Y-%m-%d")
    ordered_ids = _resolve_snapshot_spec_ids(registry, spec_ids)
    rows = "\n".join(
        f"| {spec_id} | {registry[spec_id]} | {date_text} | 基线版本锁定 |"
        for spec_id in ordered_ids
    )
    return (
        "## Spec Snapshot（初始化时锁定，供后续版本漂移检测）\n\n"
        "> 以下版本号在项目补齐时从 spec_registry.json 读取并填入。\n\n"
        "| 规范编号 | 版本号 | 记录日期 | 说明 |\n"
        "|---------|--------|---------|------|\n"
        f"{rows}"
    )


def _split_table_row(row: str) -> list[str]:
    """拆分 Markdown 表格行为单元格列表

    去除首尾的 |，按 | 分割，返回各单元格（未 trim，由调用方处理）。

    Args:
        row: Markdown 表格行（如 "| LSP-906 | V1.0.0 | 说明 |"）

    Returns:
        单元格列表（如 ["LSP-906", "V1.0.0", "说明"]）
    """
    # 去除首尾空白和首尾的 |
    stripped = row.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return stripped.split("|")


def _resolve_snapshot_spec_ids(
    registry: dict[str, str],
    spec_ids: list[str] | None,
) -> list[str]:
    if spec_ids:
        ordered = [spec_id for spec_id in spec_ids if spec_id in registry]
        if ordered:
            return ordered
    return sorted(registry)


def _parse_version(version: str) -> tuple[int, int, int] | None:
    """解析版本号为 (主, 次, 补丁) 元组

    Args:
        version: 版本号字符串（如 "V1.0.0"）

    Returns:
        (主, 次, 补丁) 元组，无法解析返回 None
    """
    match = _VERSION_RE.match(version.strip())
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _classify_drift(
    snap: tuple[int, int, int],
    reg: tuple[int, int, int],
) -> str:
    """判定漂移级别

    Args:
        snap: snapshot 版本元组 (主, 次, 补丁)
        reg: registry 版本元组 (主, 次, 补丁)

    Returns:
        "major" | "minor" | "patch"
    """
    if snap[0] != reg[0]:
        return "major"
    if snap[1] != reg[1]:
        return "minor"
    return "patch"
