"""vartable CLI 命令测试 - V2.3 Week1 T05

vartable parse / detect-encoding / list-encodings
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from auto_pm.cli.vartable import vartable_group
from click.testing import CliRunner

SAMPLE_IO_POINTS_CSV = """station,signal_type,address,tag,signal_name,device,comment
cpu,DI,X0,Z_Home_Sensor,Z轴原点传感器,Z轴伺服原点开关 B16,P35/EFS1/16.7
cpu,DI,X14,Rear_Door_Lock,后安全门锁定状态,安全门锁 SL2 S11/S12,P40/EFS1/24.7; 源程序用途: 变频器1异常检测
remote_io_1,DO,RIO1:Y10,Lift_Cyl_Up,升降气缸上升,YV1,P97/B5&EFS1/5.2
"""


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    """临时 io_points.csv 测试文件"""
    f = tmp_path / "io_points.csv"
    f.write_text(SAMPLE_IO_POINTS_CSV, encoding="utf-8")
    return f


@pytest.fixture
def gbk_csv_file(tmp_path: Path) -> Path:
    """GBK 编码 CSV"""
    f = tmp_path / "gbk.csv"
    content = (
        "station,signal_type,address,tag,signal_name,device,comment\n"
        "cpu,DI,X0,Tag_中文,信号名,设备,注释\n"
    )
    f.write_bytes(content.encode("gbk"))
    return f


class TestVartableParseCommand:
    def test_parse_json_format(
        self, cli_runner: CliRunner, sample_csv: Path
    ) -> None:
        """vartable parse --output-format json 输出有效 JSON"""
        result = cli_runner.invoke(
            vartable_group,
            ["parse", str(sample_csv), "--output-format", "json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True
        assert data["entry_count"] == 3
        assert data["error_count"] == 0

    def test_parse_table_format(
        self, cli_runner: CliRunner, sample_csv: Path
    ) -> None:
        """vartable parse --output-format table 输出表格

        注意: Rich Table 在 CliRunner 默认 80 列宽度下会截断长 Tag,
        故断言改用稳定非截断字段(概要行 + 地址列)。
        """
        result = cli_runner.invoke(
            vartable_group,
            ["parse", str(sample_csv), "--output-format", "table"],
        )
        assert result.exit_code == 0
        # 概要行:解析计数 + 站点列表 + 信号类型
        assert "3 条变量" in result.output
        assert "cpu" in result.output
        assert "remote_io_1" in result.output
        # 地址列(短,不会被 Rich 截断)
        assert "X0" in result.output
        assert "RIO1:Y10" in result.output

    def test_parse_nonexistent_file(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """vartable parse 不存在文件 → click 报错（path exists 校验）"""
        result = cli_runner.invoke(
            vartable_group,
            ["parse", str(tmp_path / "not_exist.csv")],
        )
        assert result.exit_code != 0


class TestVartableDetectEncodingCommand:
    def test_detect_encoding_text(
        self, cli_runner: CliRunner, sample_csv: Path
    ) -> None:
        """vartable detect-encoding --format text"""
        result = cli_runner.invoke(
            vartable_group,
            ["detect-encoding", str(sample_csv), "--format", "text"],
        )
        assert result.exit_code == 0
        assert "utf-8" in result.output

    def test_detect_encoding_json(
        self, cli_runner: CliRunner, gbk_csv_file: Path
    ) -> None:
        """vartable detect-encoding --format json 输出 GBK"""
        result = cli_runner.invoke(
            vartable_group,
            ["detect-encoding", str(gbk_csv_file), "--format", "json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["encoding"] == "gbk"


class TestVartableListEncodingsCommand:
    def test_list_encodings(self, cli_runner: CliRunner) -> None:
        """vartable list-encodings 输出编码列表"""
        result = cli_runner.invoke(vartable_group, ["list-encodings"])
        assert result.exit_code == 0
        assert "utf-8" in result.output
        assert "gbk" in result.output


class TestVartableHelpCommand:
    def test_help(self, cli_runner: CliRunner) -> None:
        """vartable --help 显示子命令"""
        result = cli_runner.invoke(vartable_group, ["--help"])
        assert result.exit_code == 0
        assert "parse" in result.output
        assert "detect-encoding" in result.output
        assert "list-encodings" in result.output
