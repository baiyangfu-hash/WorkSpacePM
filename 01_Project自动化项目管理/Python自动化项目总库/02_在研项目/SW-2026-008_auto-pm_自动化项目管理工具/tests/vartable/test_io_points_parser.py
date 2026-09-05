"""io_points.csv 解析器测试 - V2.3 Week1 T05

IoPointsParser.parse()
"""

from __future__ import annotations

from pathlib import Path

from auto_pm.vartable.parsers.io_points_parser import IoPointsParser


class TestIoPointsParserBasic:
    def test_parse_sample_csv(self, sample_io_points_csv: Path) -> None:
        """解析 3 行样例"""
        result = IoPointsParser().parse(sample_io_points_csv)
        assert result.success
        assert result.var_table is not None
        assert result.var_table.total_count == 3
        assert result.error_count == 0

    def test_parse_empty_csv(self, empty_csv: Path) -> None:
        """空 CSV（仅表头）"""
        result = IoPointsParser().parse(empty_csv)
        assert result.success
        assert result.var_table is not None
        assert result.var_table.total_count == 0
        assert result.error_count == 0

    def test_parse_missing_columns(self, missing_columns_csv: Path) -> None:
        """缺列 CSV → 失败"""
        result = IoPointsParser().parse(missing_columns_csv)
        assert not result.success
        assert result.var_table is None
        assert result.error_count == 1
        assert "缺少必需列" in result.errors[0].message

    def test_file_not_found(self, tmp_path: Path) -> None:
        """文件不存在 → 失败"""
        result = IoPointsParser().parse(tmp_path / "not_exist.csv")
        assert not result.success
        assert result.var_table is None
        assert result.errors[0].field == "file"
        assert "文件不存在" in result.errors[0].message


class TestIoPointsParserFieldValidation:
    def test_row_with_empty_required_fields(self, row_with_empty_required_csv: Path) -> None:
        """含空必需字段行（容错模式）"""
        result = IoPointsParser().parse(row_with_empty_required_csv)
        # 1 行有效 + 1 行 Valid_Tag + 3 行错误（station/address/tag 空）
        assert result.success  # 部分成功
        assert result.var_table is not None
        assert result.var_table.total_count == 2  # Z_Home_Sensor + Valid_Tag
        assert result.error_count == 3
        error_fields = {err.field for err in result.errors}
        assert error_fields == {"station", "address", "tag"}

    def test_entry_fields_correctness(self, sample_io_points_csv: Path) -> None:
        """解析后的 VarEntry 字段值正确"""
        result = IoPointsParser().parse(sample_io_points_csv)
        assert result.var_table is not None
        entries = result.var_table.entries
        # 第 1 行：cpu,DI,X0,Z_Home_Sensor
        assert entries[0].station == "cpu"
        assert entries[0].signal_type == "DI"
        assert entries[0].address == "X0"
        assert entries[0].tag == "Z_Home_Sensor"
        assert entries[0].line_number == 2  # 行号从 2 开始（1 为表头）
        # 第 3 行：remote_io_1,DO,RIO1:Y10,Lift_Cyl_Up
        assert entries[2].station == "remote_io_1"
        assert entries[2].signal_type == "DO"
        assert entries[2].address == "RIO1:Y10"
        assert entries[2].tag == "Lift_Cyl_Up"
        assert entries[2].line_number == 4

    def test_comment_multivalue_preserved(self, sample_io_points_csv: Path) -> None:
        """comment 分号多值原样保留"""
        result = IoPointsParser().parse(sample_io_points_csv)
        assert result.var_table is not None
        # 第 2 行 comment 含分号
        rear_door = next(e for e in result.var_table.entries if e.tag == "Rear_Door_Lock")
        assert ";" in rear_door.comment
        assert "源程序用途" in rear_door.comment

    def test_metadata_station_counts(self, sample_io_points_csv: Path) -> None:
        """元数据 station_counts 正确"""
        result = IoPointsParser().parse(sample_io_points_csv)
        assert result.var_table is not None
        counts = result.var_table.metadata["station_counts"]
        assert counts["cpu"] == 2
        assert counts["remote_io_1"] == 1

    def test_metadata_signal_type_counts(self, sample_io_points_csv: Path) -> None:
        """元数据 signal_type_counts 正确"""
        result = IoPointsParser().parse(sample_io_points_csv)
        assert result.var_table is not None
        counts = result.var_table.metadata["signal_type_counts"]
        assert counts["DI"] == 2
        assert counts["DO"] == 1


class TestIoPointsParserEncoding:
    def test_parse_gbk_file(self, gbk_csv: Path) -> None:
        """解析 GBK 编码文件"""
        result = IoPointsParser().parse(gbk_csv)
        assert result.success
        assert result.var_table is not None
        assert result.var_table.encoding == "gbk"
        assert result.var_table.entries[0].tag == "Tag_中文"

    def test_parse_utf8_bom_file(self, utf8_bom_csv: Path) -> None:
        """解析 UTF-8 BOM 文件"""
        result = IoPointsParser().parse(utf8_bom_csv)
        assert result.success
        assert result.var_table is not None
        assert result.var_table.encoding == "utf-8-sig"
        assert result.var_table.entries[0].tag == "Tag_BOM"


class TestIoPointsParserReal:
    def test_parse_real_dj_2026_005(self, real_dj_2026_005_io_points: Path) -> None:
        """解析真实 DJ-2026-005 io_points.csv（119 行）"""
        result = IoPointsParser().parse(real_dj_2026_005_io_points)
        assert result.success
        assert result.var_table is not None
        assert result.var_table.total_count == 119
        assert result.error_count == 0
        # 站点
        assert "cpu" in result.var_table.stations
        assert "remote_io_1" in result.var_table.stations
        # 信号类型
        assert "DI" in result.var_table.signal_types
        assert "DO" in result.var_table.signal_types
        # 首条目
        assert result.var_table.entries[0].tag == "Z_Home_Sensor"
        assert result.var_table.entries[0].address == "X0"
        # 末条目（RIO1:Y15）
        assert result.var_table.entries[-1].tag == "RearGrip_Release"
        assert result.var_table.entries[-1].address == "RIO1:Y15"
