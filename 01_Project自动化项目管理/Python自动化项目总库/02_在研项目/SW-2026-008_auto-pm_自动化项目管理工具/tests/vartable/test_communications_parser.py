"""communications.yml 解析器测试 - V2.3 Week2 T09

CommunicationsParser.parse()
"""

from __future__ import annotations

from pathlib import Path

import pytest
from auto_pm.vartable.parsers.communications_parser import CommunicationsParser

# 真实 DJ-2026-005 communications.yml 路径（只读，不修改）
DJ_2026_005_COMMUNICATIONS = (
    Path(r"c:\Users\fubai\Desktop\My_Workspace\0100_PLC自动化\DJ-2026-005")
    / "02_PLC程序"
    / "工程资产"
    / "communications.yml"
)

SAMPLE_COMMUNICATIONS_YML = """\
project_id: "DJ-2026-005"
project_type: "single_machine"
channels:
  - name: "HMI"
    protocol: "ethernet"
    role: "人机界面"
    endpoint: "Proface GP4501ww"
    notes: "M0-M4 模式选择"
  - name: "RemoteIO"
    protocol: "fieldbus"
    role: "分布式IO"
    endpoint: "三菱 NZ2MFB1-32DT"
    notes: "站1: 取料机构 14DI+6DO"
"""


@pytest.fixture
def sample_communications_yml(tmp_path: Path) -> Path:
    """生成临时 communications.yml 测试文件（tmp_path 隔离）"""
    file_path = tmp_path / "communications.yml"
    file_path.write_text(SAMPLE_COMMUNICATIONS_YML, encoding="utf-8")
    return file_path


@pytest.fixture
def real_dj_2026_005_communications() -> Path:
    """真实 DJ-2026-005 communications.yml 路径

    若文件不存在（如 CI 环境无 DJ-2026-005），测试应 skip。
    """
    if not DJ_2026_005_COMMUNICATIONS.exists():
        pytest.skip(f"真实样例不存在: {DJ_2026_005_COMMUNICATIONS}")
    return DJ_2026_005_COMMUNICATIONS


class TestCommunicationsParserBasic:
    def test_parse_sample_yml(self, sample_communications_yml: Path) -> None:
        """解析 2 个 channel 样例"""
        result = CommunicationsParser().parse(sample_communications_yml)
        assert result.success
        assert result.channel_table is not None
        assert result.channel_table.total_count == 2
        assert result.error_count == 0
        assert result.var_table is None  # communications 不填充 var_table

    def test_parse_empty_channels(self, tmp_path: Path) -> None:
        """channels 为空列表"""
        file_path = tmp_path / "communications.yml"
        file_path.write_text(
            'project_id: "X"\nchannels: []\n', encoding="utf-8"
        )
        result = CommunicationsParser().parse(file_path)
        assert result.success
        assert result.channel_table is not None
        assert result.channel_table.total_count == 0
        assert result.error_count == 0

    def test_parse_missing_channels_key(self, tmp_path: Path) -> None:
        """缺 channels 键 → 失败"""
        file_path = tmp_path / "communications.yml"
        file_path.write_text(
            'project_id: "X"\nproject_type: "Y"\n', encoding="utf-8"
        )
        result = CommunicationsParser().parse(file_path)
        assert not result.success
        assert result.channel_table is None
        assert result.error_count == 1
        assert "channels" in result.errors[0].field

    def test_file_not_found(self, tmp_path: Path) -> None:
        """文件不存在 → 失败"""
        result = CommunicationsParser().parse(tmp_path / "not_exist.yml")
        assert not result.success
        assert result.channel_table is None
        assert result.errors[0].field == "file"
        assert "文件不存在" in result.errors[0].message


class TestCommunicationsParserFieldValidation:
    def test_parse_missing_required_fields(self, tmp_path: Path) -> None:
        """channel 缺必需字段（容错模式：部分成功）"""
        file_path = tmp_path / "communications.yml"
        file_path.write_text(
            'project_id: "X"\n'
            "channels:\n"
            '  - name: "HMI"\n'  # 缺 role/endpoint/notes
            '    protocol: "ethernet"\n'
            '  - name: "RemoteIO"\n'
            '    protocol: "fieldbus"\n'
            '    role: "分布式IO"\n'
            '    endpoint: "三菱"\n'
            '    notes: "站1"\n',
            encoding="utf-8",
        )
        result = CommunicationsParser().parse(file_path)
        assert result.success  # 部分成功
        assert result.channel_table is not None
        assert result.channel_table.total_count == 1  # 仅 RemoteIO 有效
        assert result.error_count == 1  # HMI 缺字段

    def test_entry_fields_correctness(
        self, sample_communications_yml: Path
    ) -> None:
        """解析后的 ChannelEntry 字段值正确"""
        result = CommunicationsParser().parse(sample_communications_yml)
        assert result.channel_table is not None
        entries = result.channel_table.entries
        # 第 1 项：HMI
        assert entries[0].channel_name == "HMI"
        assert entries[0].protocol == "ethernet"
        assert entries[0].role == "人机界面"
        assert entries[0].endpoint == "Proface GP4501ww"
        assert entries[0].notes == "M0-M4 模式选择"
        assert entries[0].index == 1  # index 从 1 开始
        assert entries[0].source_format == "communications_yml"
        # 第 2 项：RemoteIO
        assert entries[1].channel_name == "RemoteIO"
        assert entries[1].protocol == "fieldbus"
        assert entries[1].index == 2

    def test_metadata_protocol_counts(
        self, sample_communications_yml: Path
    ) -> None:
        """元数据 protocol_counts + project_id 正确"""
        result = CommunicationsParser().parse(sample_communications_yml)
        assert result.channel_table is not None
        counts = result.channel_table.metadata["protocol_counts"]
        assert counts["ethernet"] == 1
        assert counts["fieldbus"] == 1
        assert result.channel_table.metadata["project_id"] == "DJ-2026-005"
        assert (
            result.channel_table.metadata["project_type"] == "single_machine"
        )
        # protocols 去重属性
        assert result.channel_table.protocols == ("ethernet", "fieldbus")


class TestCommunicationsParserReal:
    def test_parse_real_dj_2026_005(
        self, real_dj_2026_005_communications: Path
    ) -> None:
        """解析真实 DJ-2026-005 communications.yml（5 个 channel）"""
        result = CommunicationsParser().parse(real_dj_2026_005_communications)
        assert result.success
        assert result.channel_table is not None
        assert result.channel_table.total_count == 5
        assert result.error_count == 0
        # 协议
        assert "ethernet" in result.channel_table.protocols
        assert "fieldbus" in result.channel_table.protocols
        assert "hardwired" in result.channel_table.protocols
        # 首条目
        assert result.channel_table.entries[0].channel_name == "HMI"
        assert result.channel_table.entries[0].protocol == "ethernet"
        # 元数据
        assert result.channel_table.metadata["project_id"] == "DJ-2026-005"
