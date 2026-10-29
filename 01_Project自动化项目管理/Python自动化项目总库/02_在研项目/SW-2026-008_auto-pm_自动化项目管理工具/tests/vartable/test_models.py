"""数据模型测试 - V2.3 Week1 T05

VarEntry / VarTable / ParseResult / ParseError
"""

from __future__ import annotations

from auto_pm.domain.vartable.models import ParseError, ParseResult, VarEntry, VarTable


class TestVarEntry:
    def test_create_minimal_entry(self) -> None:
        """创建最小必需字段条目"""
        entry = VarEntry(
            station="cpu",
            signal_type="DI",
            address="X0",
            tag="Z_Home_Sensor",
            signal_name="原点传感器",
            device="开关",
            comment="P35",
        )
        assert entry.station == "cpu"
        assert entry.signal_type == "DI"
        assert entry.address == "X0"
        assert entry.source_format == "io_points_csv"
        assert entry.line_number == 0

    def test_create_full_entry(self) -> None:
        """创建完整字段条目（含多值 comment）"""
        entry = VarEntry(
            station="remote_io_1",
            signal_type="DO",
            address="RIO1:Y10",
            tag="Lift_Cyl_Up",
            signal_name="升降气缸上升",
            device="YV1",
            comment="P97/B5&EFS1/5.2; 源程序用途: 测试",
            source_format="io_points_csv",
            line_number=115,
        )
        assert entry.station == "remote_io_1"
        assert entry.address == "RIO1:Y10"
        assert entry.line_number == 115
        assert ";" in entry.comment

    def test_to_dict_roundtrip(self) -> None:
        """to_dict 输出可序列化"""
        entry = VarEntry(
            station="cpu",
            signal_type="DI",
            address="X0",
            tag="Tag",
            signal_name="name",
            device="dev",
            comment="c",
        )
        d = entry.to_dict()
        assert d["station"] == "cpu"
        assert d["address"] == "X0"
        assert d["source_format"] == "io_points_csv"
        assert d["line_number"] == 0

    def test_frozen_immutability(self) -> None:
        """frozen dataclass 不可变"""
        entry = VarEntry(
            station="cpu",
            signal_type="DI",
            address="X0",
            tag="Tag",
            signal_name="n",
            device="d",
            comment="c",
        )
        try:
            entry.station = "remote_io"  # type: ignore[misc]
            raise AssertionError("应抛 FrozenInstanceError")
        except AttributeError:
            pass


class TestVarTable:
    def test_stations_and_signal_types(self) -> None:
        """stations / signal_types 去重属性"""
        entries = (
            VarEntry(
                station="cpu",
                signal_type="DI",
                address="X0",
                tag="T1",
                signal_name="n",
                device="d",
                comment="c",
            ),
            VarEntry(
                station="cpu",
                signal_type="DO",
                address="Y0",
                tag="T2",
                signal_name="n",
                device="d",
                comment="c",
            ),
            VarEntry(
                station="remote_io_1",
                signal_type="DI",
                address="RIO1:X1",
                tag="T3",
                signal_name="n",
                device="d",
                comment="c",
            ),
        )
        table = VarTable(
            entries=entries,
            source_path="/tmp/test.csv",
            source_format="io_points_csv",
            parsed_at="2026-06-30T00:00:00Z",
        )
        assert table.total_count == 3
        assert table.stations == ("cpu", "remote_io_1")
        assert table.signal_types == ("DI", "DO")

    def test_to_dict_serializable(self) -> None:
        """to_dict 输出可 JSON 序列化"""
        import json

        entry = VarEntry(
            station="cpu",
            signal_type="DI",
            address="X0",
            tag="Tag",
            signal_name="名",
            device="d",
            comment="c",
        )
        table = VarTable(
            entries=(entry,),
            source_path="/tmp/test.csv",
            source_format="io_points_csv",
            parsed_at="2026-06-30T00:00:00Z",
            encoding="utf-8",
        )
        d = table.to_dict()
        json_str = json.dumps(d, ensure_ascii=False)
        assert "entries" in json_str
        assert "Tag" in json_str


class TestParseResult:
    def test_success_result(self) -> None:
        """成功结果"""
        entry = VarEntry(
            station="cpu",
            signal_type="DI",
            address="X0",
            tag="Tag",
            signal_name="n",
            device="d",
            comment="c",
        )
        table = VarTable(
            entries=(entry,),
            source_path="/tmp/test.csv",
            source_format="io_points_csv",
            parsed_at="2026-06-30T00:00:00Z",
        )
        result = ParseResult(success=True, var_table=table)
        assert result.success
        assert result.error_count == 0
        assert result.entry_count == 1

    def test_failure_result(self) -> None:
        """失败结果"""
        result = ParseResult(
            success=False,
            var_table=None,
            errors=(
                ParseError(
                    line_number=1,
                    field="header",
                    message="缺少列",
                    raw_value="station",
                ),
            ),
        )
        assert not result.success
        assert result.error_count == 1
        assert result.entry_count == 0

    def test_partial_success_result(self) -> None:
        """部分成功结果（容错模式）"""
        entry = VarEntry(
            station="cpu",
            signal_type="DI",
            address="X0",
            tag="Tag",
            signal_name="n",
            device="d",
            comment="c",
        )
        table = VarTable(
            entries=(entry,),
            source_path="/tmp/test.csv",
            source_format="io_points_csv",
            parsed_at="2026-06-30T00:00:00Z",
        )
        result = ParseResult(
            success=True,
            var_table=table,
            errors=(
                ParseError(
                    line_number=3,
                    field="station",
                    message="字段为空",
                ),
            ),
            warnings=("解析完成但有 1 个错误",),
        )
        assert result.success
        assert result.entry_count == 1
        assert result.error_count == 1
        assert result.warning_count == 1
