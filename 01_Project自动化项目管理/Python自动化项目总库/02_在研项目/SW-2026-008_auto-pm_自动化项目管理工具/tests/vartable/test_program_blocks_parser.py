"""program_blocks.yml 解析器测试 - V2.3 Week2 T08

ProgramBlocksParser.parse()
"""

from __future__ import annotations

from pathlib import Path

import pytest
from auto_pm.vartable.parsers.program_blocks_parser import ProgramBlocksParser

# 真实 DJ-2026-005 program_blocks.yml 路径（只读，不修改）
DJ_2026_005_PROGRAM_BLOCKS = (
    Path(r"c:\Users\fubai\Desktop\My_Workspace\0100_PLC自动化\DJ-2026-005")
    / "02_PLC程序"
    / "工程资产"
    / "program_blocks.yml"
)

SAMPLE_PROGRAM_BLOCKS_YML = """\
project_id: "DJ-2026-005"
project_name: "边框缓存机 PLC 控制系统"
plc_program_root: "02_PLC程序/PLC_ST"
blocks:
  - name: "OB1"
    type: "OB"
    path: "02_PLC程序/PLC_ST/OB1/OB1.scl"
    responsibility: "主循环与调用编排"
  - name: "GlobalVars"
    type: "DB"
    path: "02_PLC程序/PLC_ST/DB1/GlobalVars.db"
    responsibility: "全局变量与 IO 映射"
"""


@pytest.fixture
def sample_program_blocks_yml(tmp_path: Path) -> Path:
    """生成临时 program_blocks.yml 测试文件（tmp_path 隔离）"""
    file_path = tmp_path / "program_blocks.yml"
    file_path.write_text(SAMPLE_PROGRAM_BLOCKS_YML, encoding="utf-8")
    return file_path


@pytest.fixture
def real_dj_2026_005_program_blocks() -> Path:
    """真实 DJ-2026-005 program_blocks.yml 路径

    若文件不存在（如 CI 环境无 DJ-2026-005），测试应 skip。
    """
    if not DJ_2026_005_PROGRAM_BLOCKS.exists():
        pytest.skip(f"真实样例不存在: {DJ_2026_005_PROGRAM_BLOCKS}")
    return DJ_2026_005_PROGRAM_BLOCKS


class TestProgramBlocksParserBasic:
    def test_parse_sample_yml(self, sample_program_blocks_yml: Path) -> None:
        """解析 2 个 block 样例"""
        result = ProgramBlocksParser().parse(sample_program_blocks_yml)
        assert result.success
        assert result.block_table is not None
        assert result.block_table.total_count == 2
        assert result.error_count == 0
        assert result.var_table is None  # program_blocks 不填充 var_table

    def test_parse_empty_blocks(self, tmp_path: Path) -> None:
        """blocks 为空列表"""
        file_path = tmp_path / "program_blocks.yml"
        file_path.write_text('project_id: "X"\nblocks: []\n', encoding="utf-8")
        result = ProgramBlocksParser().parse(file_path)
        assert result.success
        assert result.block_table is not None
        assert result.block_table.total_count == 0
        assert result.error_count == 0

    def test_parse_missing_blocks_key(self, tmp_path: Path) -> None:
        """缺 blocks 键 → 失败"""
        file_path = tmp_path / "program_blocks.yml"
        file_path.write_text(
            'project_id: "X"\nproject_name: "Y"\n', encoding="utf-8"
        )
        result = ProgramBlocksParser().parse(file_path)
        assert not result.success
        assert result.block_table is None
        assert result.error_count == 1
        assert "blocks" in result.errors[0].field

    def test_file_not_found(self, tmp_path: Path) -> None:
        """文件不存在 → 失败"""
        result = ProgramBlocksParser().parse(tmp_path / "not_exist.yml")
        assert not result.success
        assert result.block_table is None
        assert result.errors[0].field == "file"
        assert "文件不存在" in result.errors[0].message


class TestProgramBlocksParserFieldValidation:
    def test_parse_missing_required_fields(self, tmp_path: Path) -> None:
        """block 缺必需字段（容错模式：部分成功）"""
        file_path = tmp_path / "program_blocks.yml"
        file_path.write_text(
            'project_id: "X"\n'
            "blocks:\n"
            '  - name: "OB1"\n'  # 缺 path/responsibility
            '    type: "OB"\n'
            '  - name: "GlobalVars"\n'
            '    type: "DB"\n'
            '    path: "p.db"\n'
            '    responsibility: "全局变量"\n',
            encoding="utf-8",
        )
        result = ProgramBlocksParser().parse(file_path)
        assert result.success  # 部分成功
        assert result.block_table is not None
        assert result.block_table.total_count == 1  # 仅 GlobalVars 有效
        assert result.error_count == 1  # OB1 缺 path/responsibility

    def test_entry_fields_correctness(
        self, sample_program_blocks_yml: Path
    ) -> None:
        """解析后的 BlockEntry 字段值正确"""
        result = ProgramBlocksParser().parse(sample_program_blocks_yml)
        assert result.block_table is not None
        entries = result.block_table.entries
        # 第 1 项：OB1
        assert entries[0].block_name == "OB1"
        assert entries[0].block_type == "OB"
        assert entries[0].path == "02_PLC程序/PLC_ST/OB1/OB1.scl"
        assert entries[0].responsibility == "主循环与调用编排"
        assert entries[0].index == 1  # index 从 1 开始
        assert entries[0].source_format == "program_blocks_yml"
        # 第 2 项：GlobalVars
        assert entries[1].block_name == "GlobalVars"
        assert entries[1].block_type == "DB"
        assert entries[1].index == 2

    def test_metadata_block_type_counts(
        self, sample_program_blocks_yml: Path
    ) -> None:
        """元数据 block_type_counts + project_id 正确"""
        result = ProgramBlocksParser().parse(sample_program_blocks_yml)
        assert result.block_table is not None
        counts = result.block_table.metadata["block_type_counts"]
        assert counts["OB"] == 1
        assert counts["DB"] == 1
        assert result.block_table.metadata["project_id"] == "DJ-2026-005"
        assert (
            result.block_table.metadata["project_name"]
            == "边框缓存机 PLC 控制系统"
        )
        # block_types 去重属性
        assert result.block_table.block_types == ("DB", "OB")


class TestProgramBlocksParserReal:
    def test_parse_real_dj_2026_005(
        self, real_dj_2026_005_program_blocks: Path
    ) -> None:
        """解析真实 DJ-2026-005 program_blocks.yml（7 个 block）"""
        result = ProgramBlocksParser().parse(real_dj_2026_005_program_blocks)
        assert result.success
        assert result.block_table is not None
        assert result.block_table.total_count == 7
        assert result.error_count == 0
        # 块类型
        assert "OB" in result.block_table.block_types
        assert "DB" in result.block_table.block_types
        assert "FB" in result.block_table.block_types
        # 首条目
        assert result.block_table.entries[0].block_name == "OB1"
        assert result.block_table.entries[0].block_type == "OB"
        # 元数据
        assert result.block_table.metadata["project_id"] == "DJ-2026-005"
