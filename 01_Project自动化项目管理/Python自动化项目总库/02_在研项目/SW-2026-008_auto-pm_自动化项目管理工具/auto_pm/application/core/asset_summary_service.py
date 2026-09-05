"""PLC-HMI 概念映射：SFB 库函数（资产汇总（统计项目文件/代码行数/文档数量））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

工程资产摘要服务

读取 PLC 项目 `02_PLC程序/工程资产/` 下的结构化资产文件，
提供统一的计数、状态和问题摘要，供 Scanner / CLI / GUI 复用。
"""

from __future__ import annotations

import csv
import os
from typing import Any

import yaml


class AssetSummaryService:
    """工程资产摘要服务"""

    ASSET_DIR = os.path.join("02_PLC程序", "工程资产")
    IO_POINTS_FILE = "io_points.csv"
    PROGRAM_BLOCKS_FILE = "program_blocks.yml"
    COMMUNICATIONS_FILE = "communications.yml"

    _IO_REQUIRED_COLUMNS = (
        "station",
        "signal_type",
        "address",
        "tag",
        "signal_name",
        "device",
        "comment",
    )
    _BLOCK_REQUIRED_KEYS = ("name", "type", "path", "responsibility")
    _CHANNEL_REQUIRED_KEYS = ("name", "protocol", "role", "endpoint", "notes")
    _NOT_APPLICABLE_TYPES = {"shared_library", "test_suite"}

    def build_summary(
        self, project_path: str, stack: str, project_type: str = ""
    ) -> dict[str, Any]:
        """构建项目工程资产摘要"""
        if stack != "plc":
            return self._not_applicable_summary("仅 PLC 项目支持工程资产摘要")
        if project_type in self._NOT_APPLICABLE_TYPES:
            return self._not_applicable_summary(f"{project_type} 模式不要求工程资产目录")

        asset_dir = os.path.join(project_path, self.ASSET_DIR)
        summary: dict[str, Any] = {
            "status": "healthy",
            "asset_dir": asset_dir,
            "asset_dir_exists": os.path.isdir(asset_dir),
            "total_issues": 0,
            "issue_messages": [],
        }
        if not summary["asset_dir_exists"]:
            summary["status"] = "missing"
            summary["total_issues"] = 1
            summary["issue_messages"] = [f"缺少工程资产目录: {self.ASSET_DIR}"]
            summary["io_points"] = self._missing_file_summary(self.IO_POINTS_FILE)
            summary["program_blocks"] = self._missing_file_summary(self.PROGRAM_BLOCKS_FILE)
            summary["communications"] = self._missing_file_summary(self.COMMUNICATIONS_FILE)
            return summary

        io_summary = self._read_io_points(asset_dir)
        block_summary = self._read_program_blocks(asset_dir)
        comm_summary = self._read_communications(asset_dir)
        total_issues = (
            len(io_summary["issues"]) + len(block_summary["issues"]) + len(comm_summary["issues"])
        )
        issue_messages = [
            *io_summary["issues"],
            *block_summary["issues"],
            *comm_summary["issues"],
        ]

        summary["io_points"] = io_summary
        summary["program_blocks"] = block_summary
        summary["communications"] = comm_summary
        summary["total_issues"] = total_issues
        summary["issue_messages"] = issue_messages
        summary["status"] = self._resolve_status(
            io_summary["exists"],
            block_summary["exists"],
            comm_summary["exists"],
            total_issues,
        )
        return summary

    @staticmethod
    def _not_applicable_summary(message: str) -> dict[str, Any]:
        return {
            "status": "not_applicable",
            "asset_dir": "",
            "asset_dir_exists": False,
            "total_issues": 0,
            "issue_messages": [message],
            "io_points": {"exists": False, "valid": False, "count": 0, "issues": []},
            "program_blocks": {"exists": False, "valid": False, "count": 0, "issues": []},
            "communications": {"exists": False, "valid": False, "count": 0, "issues": []},
        }

    @staticmethod
    def _missing_file_summary(file_name: str) -> dict[str, Any]:
        return {
            "exists": False,
            "valid": False,
            "count": 0,
            "issues": [f"缺少资产文件: {file_name}"],
        }

    @staticmethod
    def _resolve_status(
        io_exists: bool,
        block_exists: bool,
        comm_exists: bool,
        total_issues: int,
    ) -> str:
        if not (io_exists and block_exists and comm_exists):
            return "missing"
        if total_issues > 0:
            return "warning"
        return "healthy"

    def _read_io_points(self, asset_dir: str) -> dict[str, Any]:
        file_path = os.path.join(asset_dir, self.IO_POINTS_FILE)
        if not os.path.isfile(file_path):
            return self._missing_file_summary(self.IO_POINTS_FILE)

        issues: list[str] = []
        count = 0
        try:
            with open(file_path, encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                missing_columns = [
                    col for col in self._IO_REQUIRED_COLUMNS if col not in fieldnames
                ]
                if missing_columns:
                    issues.append(f"{self.IO_POINTS_FILE} 缺少列: {', '.join(missing_columns)}")
                for row in reader:
                    if not self._row_has_data(row):
                        continue
                    count += 1
        except OSError as exc:
            issues.append(f"{self.IO_POINTS_FILE} 读取失败: {exc}")

        return {
            "exists": True,
            "valid": len(issues) == 0,
            "count": count,
            "issues": issues,
        }

    def _read_program_blocks(self, asset_dir: str) -> dict[str, Any]:
        file_path = os.path.join(asset_dir, self.PROGRAM_BLOCKS_FILE)
        if not os.path.isfile(file_path):
            return self._missing_file_summary(self.PROGRAM_BLOCKS_FILE)

        issues: list[str] = []
        count = 0
        try:
            with open(file_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            blocks = data.get("blocks")
            if not isinstance(blocks, list):
                issues.append(f"{self.PROGRAM_BLOCKS_FILE} 缺少 blocks 列表")
            else:
                count = len(blocks)
                for index, block in enumerate(blocks, start=1):
                    if not isinstance(block, dict):
                        issues.append(f"{self.PROGRAM_BLOCKS_FILE} 第 {index} 项必须为对象")
                        continue
                    missing_keys = [
                        key
                        for key in self._BLOCK_REQUIRED_KEYS
                        if not str(block.get(key, "")).strip()
                    ]
                    if missing_keys:
                        issues.append(
                            f"{self.PROGRAM_BLOCKS_FILE} 第 {index} 项缺少字段: {', '.join(missing_keys)}"
                        )
        except (OSError, yaml.YAMLError) as exc:
            issues.append(f"{self.PROGRAM_BLOCKS_FILE} 读取失败: {exc}")

        return {
            "exists": True,
            "valid": len(issues) == 0,
            "count": count,
            "issues": issues,
        }

    def _read_communications(self, asset_dir: str) -> dict[str, Any]:
        file_path = os.path.join(asset_dir, self.COMMUNICATIONS_FILE)
        if not os.path.isfile(file_path):
            return self._missing_file_summary(self.COMMUNICATIONS_FILE)

        issues: list[str] = []
        count = 0
        try:
            with open(file_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            channels = data.get("channels")
            if not isinstance(channels, list):
                issues.append(f"{self.COMMUNICATIONS_FILE} 缺少 channels 列表")
            else:
                count = len(channels)
                for index, channel in enumerate(channels, start=1):
                    if not isinstance(channel, dict):
                        issues.append(f"{self.COMMUNICATIONS_FILE} 第 {index} 项必须为对象")
                        continue
                    missing_keys = [
                        key
                        for key in self._CHANNEL_REQUIRED_KEYS
                        if not str(channel.get(key, "")).strip()
                    ]
                    if missing_keys:
                        issues.append(
                            f"{self.COMMUNICATIONS_FILE} 第 {index} 项缺少字段: {', '.join(missing_keys)}"
                        )
        except (OSError, yaml.YAMLError) as exc:
            issues.append(f"{self.COMMUNICATIONS_FILE} 读取失败: {exc}")

        return {
            "exists": True,
            "valid": len(issues) == 0,
            "count": count,
            "issues": issues,
        }

    @staticmethod
    def _row_has_data(row: dict[str, Any]) -> bool:
        return any(str(value).strip() for value in row.values() if value is not None)
