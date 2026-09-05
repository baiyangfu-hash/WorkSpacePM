"""PLC-HMI 概念映射：SFB 库函数（文档刷新（自动更新项目文档/索引））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

文档自动区刷新服务"""

from __future__ import annotations

import csv
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any

import yaml
from auto_pm.models import ProjectInfo
from auto_pm.utils.file_utils import StaleFileError, read_file_snapshot, write_file

log = logging.getLogger(__name__)


@dataclass
class RefreshedDocument:
    """单个文档刷新结果"""

    file_path: str
    block_keys: list[str] = field(default_factory=list)
    changed: bool = False


@dataclass
class DocRefreshResult:
    """文档刷新结果"""

    project_id: str
    dry_run: bool
    updated: bool
    refreshed_files: list[RefreshedDocument] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "dry_run": self.dry_run,
            "updated": self.updated,
            "refreshed_files": [asdict(item) for item in self.refreshed_files],
            "issues": self.issues,
        }


class DocRefreshService:
    """基于工程资产刷新 PLC 文档中的自动区"""

    _AUTO_BLOCK_RE = re.compile(
        r"<!--\s*AUTO_PM:BEGIN\s+(?P<key>[\w\-]+)\s*-->(?P<body>[\s\S]*?)<!--\s*AUTO_PM:END\s+(?P=key)\s*-->",
        re.MULTILINE,
    )

    def __init__(self, workspace_root: str) -> None:
        self.workspace_root = os.path.abspath(workspace_root)

    def refresh_project_documents(
        self,
        project: ProjectInfo,
        dry_run: bool = False,
    ) -> DocRefreshResult:
        """刷新项目文档自动区"""
        result = DocRefreshResult(
            project_id=project.project_id,
            dry_run=dry_run,
            updated=False,
        )
        if project.stack != "plc":
            result.issues.append("仅 PLC 项目支持 doc refresh")
            return result

        asset_data = self.load_asset_data(project.path)
        target_docs = self.locate_target_docs(project.path)
        if not target_docs:
            result.issues.append("未找到可刷新的 PLC 文档")
            return result

        for doc_path, block_builders in target_docs:
            content, original_mtime = read_file_snapshot(doc_path)
            if not content:
                result.issues.append(f"读取文档失败: {doc_path}")
                continue

            original = content
            applied_keys: list[str] = []
            for block_key, builder_name in block_builders:
                generated = getattr(self, builder_name)(project, asset_data)
                updated_content = self._replace_auto_block(content, block_key, generated)
                if updated_content is None:
                    result.issues.append(
                        f"文档缺少自动区标记: {os.path.basename(doc_path)} [{block_key}]"
                    )
                    continue
                content = updated_content
                applied_keys.append(block_key)

            if not applied_keys:
                continue

            changed = content != original
            result.refreshed_files.append(
                RefreshedDocument(
                    file_path=doc_path,
                    block_keys=applied_keys,
                    changed=changed,
                )
            )
            if changed and not dry_run:
                try:
                    write_file(doc_path, content, expected_mtime=original_mtime)
                except StaleFileError as exc:
                    result.issues.append(f"文档已被外部修改，跳过写入: {doc_path} ({exc})")
                    continue
                result.updated = True
            elif changed and dry_run:
                result.updated = False

        return result

    def load_asset_data(self, project_path: str) -> dict[str, Any]:
        asset_dir = os.path.join(project_path, "02_PLC程序", "工程资产")
        return {
            "asset_dir": asset_dir,
            "io_points": self._load_io_points(os.path.join(asset_dir, "io_points.csv")),
            "program_blocks": self._load_yaml_list(
                os.path.join(asset_dir, "program_blocks.yml"), "blocks"
            ),
            "communications": self._load_yaml_list(
                os.path.join(asset_dir, "communications.yml"), "channels"
            ),
        }

    def locate_target_docs(self, project_path: str) -> list[tuple[str, list[tuple[str, str]]]]:
        doc_dir = os.path.join(project_path, "02_PLC程序", "程序文档")
        targets: list[tuple[str, list[tuple[str, str]]]] = []
        program_doc = self._find_doc_by_suffix(doc_dir, "PLC程序设计总文档_PLC.md")
        io_doc = self._find_doc_by_suffix(doc_dir, "IO分配表_IO.md")
        if program_doc:
            targets.append(
                (
                    program_doc,
                    [
                        ("plc-program-components", "_build_program_components_block"),
                        ("plc-asset-index", "_build_asset_index_block"),
                    ],
                )
            )
        if io_doc:
            targets.append(
                (
                    io_doc,
                    [("plc-io-overview", "_build_io_overview_block")],
                )
            )
        return targets

    @staticmethod
    def _find_doc_by_suffix(doc_dir: str, suffix: str) -> str:
        if not os.path.isdir(doc_dir):
            return ""
        for name in os.listdir(doc_dir):
            if name.endswith(suffix):
                return os.path.join(doc_dir, name)
        return ""

    def _build_program_components_block(
        self, project: ProjectInfo, asset_data: dict[str, Any]
    ) -> str:
        blocks = asset_data["program_blocks"]
        lines = [
            "",
            "> 本区由 `auto-pm doc refresh` 自动生成，请勿手工修改。",
            "",
            "| 序号 | 组件 | 类型 | 文件 | 核心职责 |",
            "|------|------|------|------|----------|",
        ]
        if not blocks:
            lines.append("| 1 | 待补齐 | - | - | 尚未提供 `program_blocks.yml` 数据 |")
            return "\n".join(lines) + "\n"
        for index, block in enumerate(blocks, start=1):
            lines.append(
                "| {index} | **{name}** | {type} | `{path}` | {responsibility} |".format(
                    index=index,
                    name=block.get("name", "-"),
                    type=block.get("type", "-"),
                    path=block.get("path", "-"),
                    responsibility=block.get("responsibility", "-"),
                )
            )
        return "\n".join(lines) + "\n"

    def _build_asset_index_block(self, project: ProjectInfo, asset_data: dict[str, Any]) -> str:
        io_count = len(asset_data["io_points"])
        block_count = len(asset_data["program_blocks"])
        comm_count = len(asset_data["communications"])
        lines = [
            "",
            "> 本区由 `auto-pm doc refresh` 自动生成，请勿手工修改。",
            "",
            "| 文件名 | 路径 | 说明 |",
            "|--------|------|------|",
            f"| **io_points.csv** | `02_PLC程序/工程资产/io_points.csv` | IO 点表，共 {io_count} 条 |",
            f"| **program_blocks.yml** | `02_PLC程序/工程资产/program_blocks.yml` | 程序块清单，共 {block_count} 项 |",
            f"| **communications.yml** | `02_PLC程序/工程资产/communications.yml` | 通讯对象清单，共 {comm_count} 项 |",
            "| **.plc.json** | `02_PLC程序/PLC_ST/.plc.json` | PLC 项目配置与版本入口 |",
        ]
        return "\n".join(lines) + "\n"

    def _build_io_overview_block(self, project: ProjectInfo, asset_data: dict[str, Any]) -> str:
        io_points = asset_data["io_points"]
        counts = {"DI": 0, "DO": 0, "AI": 0, "AO": 0}
        stations: dict[str, dict[str, int]] = {}
        for row in io_points:
            signal_type = str(row.get("signal_type", "")).upper()
            station = str(row.get("station", "")).strip() or "unknown"
            if signal_type in counts:
                counts[signal_type] += 1
            station_stats = stations.setdefault(station, {"DI": 0, "DO": 0, "AI": 0, "AO": 0})
            if signal_type in station_stats:
                station_stats[signal_type] += 1

        lines = [
            "",
            "### 2.1 自动区刷新摘要",
            "",
            "> 本区由 `auto-pm doc refresh` 自动生成，请勿手工修改。",
            "",
            "| 类型 | 点数 | 模块 | 地址范围 | 备注 |",
            "|------|------|------|---------|------|",
            "| DI (数字量输入) | {0} | 工程资产 | 自动统计 | 来自 `io_points.csv` |".format(
                counts["DI"]
            ),
            "| DO (数字量输出) | {0} | 工程资产 | 自动统计 | 来自 `io_points.csv` |".format(
                counts["DO"]
            ),
            "| AI (模拟量输入) | {0} | 工程资产 | 自动统计 | 来自 `io_points.csv` |".format(
                counts["AI"]
            ),
            "| AO (模拟量输出) | {0} | 工程资产 | 自动统计 | 来自 `io_points.csv` |".format(
                counts["AO"]
            ),
            "",
            "| 工站 | DI 点数 | DO 点数 | AI 点数 | AO 点数 | 备注 |",
            "|------|---------|---------|---------|---------|------|",
        ]
        if not stations:
            lines.append("| 待补齐 | 0 | 0 | 0 | 0 | 尚未提供 `io_points.csv` 数据 |")
        else:
            for station, station_counts in sorted(stations.items()):
                lines.append(
                    "| {station} | {DI} | {DO} | {AI} | {AO} | 自动汇总 |".format(
                        station=station,
                        **station_counts,
                    )
                )
        return "\n".join(lines) + "\n"

    def _replace_auto_block(self, content: str, block_key: str, generated_body: str) -> str | None:
        pattern = re.compile(
            r"(<!--\s*AUTO_PM:BEGIN\s+"
            + re.escape(block_key)
            + r"\s*-->)([\s\S]*?)(<!--\s*AUTO_PM:END\s+"
            + re.escape(block_key)
            + r"\s*-->)",
            re.MULTILINE,
        )
        match = pattern.search(content)
        if not match:
            return None
        return (
            content[: match.start()]
            + match.group(1)
            + generated_body
            + match.group(3)
            + content[match.end() :]
        )

    @staticmethod
    def _load_io_points(file_path: str) -> list[dict[str, str]]:
        if not os.path.isfile(file_path):
            return []
        rows: list[dict[str, str]] = []
        with open(file_path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if any(str(v).strip() for v in row.values() if v is not None):
                    rows.append({k: str(v or "") for k, v in row.items()})
        return rows

    @staticmethod
    def _load_yaml_list(file_path: str, key: str) -> list[dict[str, Any]]:
        if not os.path.isfile(file_path):
            return []
        with open(file_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        value = data.get(key)
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]
