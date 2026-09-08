"""VariableConverter 测试 - V2.3 Week3 T13

验证 VariableConverter 的 CSV/YAML/JSON 导出 + 错误处理。
覆盖 VarTable / BlockTable / ChannelTable 三种容器。
"""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime

import pytest
import yaml
from auto_pm.vartable.converter import SUPPORTED_OUTPUT_FORMATS, VariableConverter
from auto_pm.vartable.models import (
    BlockEntry,
    BlockTable,
    ChannelEntry,
    ChannelTable,
    ParseResult,
    VarEntry,
    VarTable,
)


def _make_var_table() -> VarTable:
    """构造测试用 VarTable（2 个 VarEntry）"""
    entries = (
        VarEntry(
            station="cpu",
            signal_type="DI",
            address="X0",
            tag="i_bStart",
            signal_name="启动按钮",
            device="Z轴开关",
            comment="P35/EFS1/16.7",
            source_format="io_points_csv",
            line_number=2,
        ),
        VarEntry(
            station="cpu",
            signal_type="DO",
            address="Y0",
            tag="q_bRun",
            signal_name="运行中",
            device="",
            comment="运行指示灯",
            source_format="io_points_csv",
            line_number=3,
        ),
    )
    return VarTable(
        entries=entries,
        source_path="/tmp/test.csv",
        source_format="io_points_csv",
        parsed_at="2026-07-01T00:00:00+00:00",
        encoding="utf-8",
        metadata={"total_rows_read": 2},
    )


def _make_block_table() -> BlockTable:
    """构造测试用 BlockTable（2 个 BlockEntry）"""
    entries = (
        BlockEntry(
            block_name="OB1",
            block_type="OB",
            path="OB1/OB1.scl",
            responsibility="主循环调度",
            source_format="program_blocks_yml",
            index=0,
        ),
        BlockEntry(
            block_name="FB_1002",
            block_type="FB",
            path="conveyor/FB_1002.scl",
            responsibility="单层输送机控制",
            source_format="program_blocks_yml",
            index=1,
        ),
    )
    return BlockTable(
        entries=entries,
        source_path="/tmp/program_blocks.yml",
        source_format="program_blocks_yml",
        parsed_at="2026-07-01T00:00:00+00:00",
        encoding="utf-8",
        metadata={"total_rows_read": 2},
    )


class TestVariableConverterCsv:
    def test_converter_csv_var_table_export(self) -> None:
        """CSV 导出 VarTable：表头 + 数据行，字段对齐 VarEntry 9 字段"""
        table = _make_var_table()
        result = ParseResult(success=True, var_table=table)
        csv_text = VariableConverter().convert(result, "csv")

        # 解析 CSV 验证
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["station"] == "cpu"
        assert rows[0]["tag"] == "i_bStart"
        assert rows[0]["address"] == "X0"
        assert rows[0]["signal_name"] == "启动按钮"
        assert rows[0]["comment"] == "P35/EFS1/16.7"
        assert rows[0]["source_format"] == "io_points_csv"
        assert rows[0]["line_number"] == "2"
        assert rows[1]["tag"] == "q_bRun"

    def test_converter_csv_block_table_export(self) -> None:
        """CSV 导出 BlockTable：表头含 block_name/block_type/path/responsibility"""
        table = _make_block_table()
        result = ParseResult(success=True, var_table=None, block_table=table)
        csv_text = VariableConverter().convert(result, "csv")

        reader = csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["block_name"] == "OB1"
        assert rows[0]["block_type"] == "OB"
        assert rows[0]["path"] == "OB1/OB1.scl"
        assert rows[0]["responsibility"] == "主循环调度"
        assert rows[1]["block_name"] == "FB_1002"


class TestVariableConverterYamlAndJson:
    def test_converter_yaml_var_table_export(self) -> None:
        """YAML 导出 VarTable：可被 yaml.safe_load 解析，含 entries 列表"""
        table = _make_var_table()
        result = ParseResult(success=True, var_table=table)
        yaml_text = VariableConverter().convert(result, "yaml")

        # 解析 YAML 验证
        data = yaml.safe_load(yaml_text)
        assert isinstance(data, dict)
        assert data["source_format"] == "io_points_csv"
        assert data["total_count"] == 2
        assert len(data["entries"]) == 2
        assert data["entries"][0]["tag"] == "i_bStart"
        assert data["entries"][0]["signal_name"] == "启动按钮"  # 中文保留
        assert data["entries"][1]["tag"] == "q_bRun"

    def test_converter_json_var_table_export(self) -> None:
        """JSON 导出 VarTable：可被 json.loads 解析，含完整字段"""
        table = _make_var_table()
        result = ParseResult(success=True, var_table=table)
        json_text = VariableConverter().convert(result, "json")

        # 解析 JSON 验证
        data = json.loads(json_text)
        assert data["source_format"] == "io_points_csv"
        assert data["total_count"] == 2
        assert data["stations"] == ["cpu"]
        assert len(data["entries"]) == 2
        assert data["entries"][0]["tag"] == "i_bStart"
        assert data["entries"][0]["address"] == "X0"
        assert data["entries"][1]["comment"] == "运行指示灯"
        # ensure_ascii=False 保留中文
        assert "启动按钮" in json_text


class TestVariableConverterErrorHandling:
    def test_converter_unsupported_format_raises_value_error(self) -> None:
        """不支持的输出格式抛 ValueError"""
        table = _make_var_table()
        result = ParseResult(success=True, var_table=table)
        with pytest.raises(ValueError, match="不支持的输出格式"):
            VariableConverter().convert(result, "xml")

    def test_converter_empty_parse_result_raises_value_error(self) -> None:
        """ParseResult 无任何 table 时抛 ValueError"""
        # var_table/block_table/channel_table 均为 None
        result = ParseResult(success=False, var_table=None)
        with pytest.raises(ValueError, match="无任何 table"):
            VariableConverter().convert(result, "csv")

    def test_converter_supported_formats_constant(self) -> None:
        """SUPPORTED_OUTPUT_FORMATS 常量包含 csv/yaml/json"""
        assert SUPPORTED_OUTPUT_FORMATS == ("csv", "yaml", "json")

    def test_converter_channel_table_csv_export(self) -> None:
        """CSV 导出 ChannelTable：表头含 channel_name/protocol/role/endpoint/notes"""
        entries = (
            ChannelEntry(
                channel_name="HMI",
                protocol="ModbusTCP",
                role="master",
                endpoint="192.168.1.100:502",
                notes="HMI 通信",
                source_format="communications_yml",
                index=0,
            ),
        )
        table = ChannelTable(
            entries=entries,
            source_path="/tmp/communications.yml",
            source_format="communications_yml",
            parsed_at=datetime.now(UTC).isoformat(),
            encoding="utf-8",
        )
        result = ParseResult(success=True, var_table=None, channel_table=table)
        csv_text = VariableConverter().convert(result, "csv")

        reader = csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["channel_name"] == "HMI"
        assert rows[0]["protocol"] == "ModbusTCP"
        assert rows[0]["role"] == "master"
        assert rows[0]["endpoint"] == "192.168.1.100:502"
        assert rows[0]["notes"] == "HMI 通信"
