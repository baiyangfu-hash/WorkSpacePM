"""PLC-HMI 概念映射：SFB 库函数（变量表转换器（PLC 变量表格式互转））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

变量表格式转换器

V2.3 Week3 T13：将 ParseResult 统一中间模型导出为 CSV/YAML/JSON。

设计原则：
- 重新实现，不复用 SW-2026-001 src/converter/base_converter.py 死代码
  （原 BaseConverter.convert() 只有 pass 空壳，PRD §7 明确不复用）
- 支持 VarTable / BlockTable / ChannelTable 三种容器导出
- 输出字符串（不直接写文件，由调用方决定写入路径）
- 错误处理：不支持的 output_format 或空 ParseResult 抛 ValueError

用法：
    converter = VariableConverter()
    csv_text = converter.convert(parse_result, "csv")
    yaml_text = converter.convert(parse_result, "yaml")
    json_text = converter.convert(parse_result, "json")
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

import yaml

from auto_pm.vartable.models import ParseResult

# 支持的输出格式
SUPPORTED_OUTPUT_FORMATS: tuple[str, ...] = ("csv", "yaml", "json")


class VariableConverter:
    """变量表格式转换器

    将 ParseResult（统一中间模型）转换为 CSV/YAML/JSON 字符串。
    支持 VarTable / BlockTable / ChannelTable 三种容器。

    用法：
        converter = VariableConverter()
        result = parser.parse("path/to/file.scl")
        if result.success:
            csv_text = converter.convert(result, "csv")
    """

    def convert(self, parse_result: ParseResult, output_format: str) -> str:
        """主入口：按指定格式转换 ParseResult

        Args:
            parse_result: 解析结果（含 var_table/block_table/channel_table 之一）
            output_format: 输出格式（csv/yaml/json）

        Returns:
            转换后的字符串

        Raises:
            ValueError: output_format 不支持，或 ParseResult 无任何 table
        """
        if output_format not in SUPPORTED_OUTPUT_FORMATS:
            raise ValueError(
                f"不支持的输出格式: {output_format}，"
                f"支持 {SUPPORTED_OUTPUT_FORMATS}"
            )

        if output_format == "csv":
            return self.convert_to_csv(parse_result)
        if output_format == "yaml":
            return self.convert_to_yaml(parse_result)
        return self.convert_to_json(parse_result)

    def convert_to_csv(self, parse_result: ParseResult) -> str:
        """导出 CSV 格式

        VarTable: station,signal_type,address,tag,signal_name,device,comment,source_format,line_number
        BlockTable: block_name,block_type,path,responsibility,source_format,index
        ChannelTable: channel_name,protocol,role,endpoint,notes,source_format,index

        Args:
            parse_result: 解析结果

        Returns:
            CSV 字符串

        Raises:
            ValueError: ParseResult 无任何 table
        """
        if parse_result.var_table is not None:
            return self._var_table_to_csv(parse_result)
        if parse_result.block_table is not None:
            return self._block_table_to_csv(parse_result)
        if parse_result.channel_table is not None:
            return self._channel_table_to_csv(parse_result)
        raise ValueError("ParseResult 无任何 table（var/block/channel 均为 None）")

    def convert_to_yaml(self, parse_result: ParseResult) -> str:
        """导出 YAML 格式

        Args:
            parse_result: 解析结果

        Returns:
            YAML 字符串

        Raises:
            ValueError: ParseResult 无任何 table
        """
        data = self._to_serializable_dict(parse_result)
        # allow_unicode=True 保留中文；sort_keys=False 保持字段顺序
        return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)

    def convert_to_json(self, parse_result: ParseResult) -> str:
        """导出 JSON 格式

        Args:
            parse_result: 解析结果

        Returns:
            JSON 字符串（ensure_ascii=False 保留中文，indent=2 美化）

        Raises:
            ValueError: ParseResult 无任何 table
        """
        data = self._to_serializable_dict(parse_result)
        return json.dumps(data, ensure_ascii=False, indent=2)

    @staticmethod
    def _to_serializable_dict(parse_result: ParseResult) -> dict[str, Any]:
        """将 ParseResult 转为可序列化字典（供 YAML/JSON 共用）

        Raises:
            ValueError: 无任何 table
        """
        if parse_result.var_table is not None:
            return dict(parse_result.var_table.to_dict())
        if parse_result.block_table is not None:
            return dict(parse_result.block_table.to_dict())
        if parse_result.channel_table is not None:
            return dict(parse_result.channel_table.to_dict())
        raise ValueError("ParseResult 无任何 table（var/block/channel 均为 None）")

    @staticmethod
    def _var_table_to_csv(parse_result: ParseResult) -> str:
        """VarTable → CSV"""
        assert parse_result.var_table is not None
        table = parse_result.var_table
        output = io.StringIO()
        # lineterminator="\n" 避免 Windows \r\n 跨平台问题
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(
            [
                "station",
                "signal_type",
                "address",
                "tag",
                "signal_name",
                "device",
                "comment",
                "source_format",
                "line_number",
            ]
        )
        for entry in table.entries:
            writer.writerow(
                [
                    entry.station,
                    entry.signal_type,
                    entry.address,
                    entry.tag,
                    entry.signal_name,
                    entry.device,
                    entry.comment,
                    entry.source_format,
                    entry.line_number,
                ]
            )
        return output.getvalue()

    @staticmethod
    def _block_table_to_csv(parse_result: ParseResult) -> str:
        """BlockTable → CSV"""
        assert parse_result.block_table is not None
        table = parse_result.block_table
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(
            ["block_name", "block_type", "path", "responsibility", "source_format", "index"]
        )
        for entry in table.entries:
            writer.writerow(
                [
                    entry.block_name,
                    entry.block_type,
                    entry.path,
                    entry.responsibility,
                    entry.source_format,
                    entry.index,
                ]
            )
        return output.getvalue()

    @staticmethod
    def _channel_table_to_csv(parse_result: ParseResult) -> str:
        """ChannelTable → CSV"""
        assert parse_result.channel_table is not None
        table = parse_result.channel_table
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(
            [
                "channel_name",
                "protocol",
                "role",
                "endpoint",
                "notes",
                "source_format",
                "index",
            ]
        )
        for entry in table.entries:
            writer.writerow(
                [
                    entry.channel_name,
                    entry.protocol,
                    entry.role,
                    entry.endpoint,
                    entry.notes,
                    entry.source_format,
                    entry.index,
                ]
            )
        return output.getvalue()
