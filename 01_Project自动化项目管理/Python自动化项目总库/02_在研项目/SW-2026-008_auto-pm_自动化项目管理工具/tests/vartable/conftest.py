"""tests/vartable 共享 fixtures"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def workspace_root() -> Path:
    """工作空间根目录（从 conftest.py 位置推导）

    tests/vartable/conftest.py → ... → My_Workspace（7 级父目录）
    """
    return Path(__file__).resolve().parents[6]


# 真实 DJ-2026-005 io_points.csv 路径（只读，不修改）
DJ_2026_005_IO_POINTS = (
    Path(__file__).resolve().parents[6]
    / "0100_PLC自动化"
    / "DJ-2026-005"
    / "02_PLC程序"
    / "工程资产"
    / "io_points.csv"
)

# 真实样例的前 3 行（用于无外部依赖的测试）
SAMPLE_IO_POINTS_CSV = """station,signal_type,address,tag,signal_name,device,comment
cpu,DI,X0,Z_Home_Sensor,Z轴原点传感器,Z轴伺服原点开关 B16,P35/EFS1/16.7
cpu,DI,X14,Rear_Door_Lock,后安全门锁定状态,安全门锁 SL2 S11/S12,P40/EFS1/24.7; 源程序用途: 变频器1异常检测
remote_io_1,DO,RIO1:Y10,Lift_Cyl_Up,升降气缸上升,YV1,P97/B5&EFS1/5.2
"""


@pytest.fixture
def sample_io_points_csv(tmp_path: Path) -> Path:
    """生成临时 io_points.csv 测试文件（tmp_path 隔离）"""
    file_path = tmp_path / "io_points.csv"
    file_path.write_text(SAMPLE_IO_POINTS_CSV, encoding="utf-8")
    return file_path


@pytest.fixture
def real_dj_2026_005_io_points() -> Path:
    """真实 DJ-2026-005 io_points.csv 路径

    若文件不存在（如 CI 环境无 DJ-2026-005），测试应 skip。
    """
    if not DJ_2026_005_IO_POINTS.exists():
        pytest.skip(f"真实样例不存在: {DJ_2026_005_IO_POINTS}")
    return DJ_2026_005_IO_POINTS


@pytest.fixture
def empty_csv(tmp_path: Path) -> Path:
    """空 CSV 文件（只有表头）"""
    file_path = tmp_path / "empty.csv"
    file_path.write_text(
        "station,signal_type,address,tag,signal_name,device,comment\n",
        encoding="utf-8",
    )
    return file_path


@pytest.fixture
def missing_columns_csv(tmp_path: Path) -> Path:
    """缺列 CSV 文件"""
    file_path = tmp_path / "missing.csv"
    file_path.write_text(
        "station,signal_type,address\ncpu,DI,X0\n",
        encoding="utf-8",
    )
    return file_path


@pytest.fixture
def row_with_empty_required_csv(tmp_path: Path) -> Path:
    """含空必需字段行的 CSV"""
    file_path = tmp_path / "bad_rows.csv"
    file_path.write_text(
        "station,signal_type,address,tag,signal_name,device,comment\n"
        "cpu,DI,X0,Z_Home_Sensor,Z轴原点传感器,Z轴开关,P35\n"
        ",DI,X1,Tag1,name,device,comment\n"  # station 空
        "cpu,DI,,Tag2,name,device,comment\n"  # address 空
        "cpu,DO,Y0,,name,device,comment\n"  # tag 空
        "cpu,DO,Y1,Valid_Tag,name,device,comment\n",
        encoding="utf-8",
    )
    return file_path


@pytest.fixture
def gbk_csv(tmp_path: Path) -> Path:
    """GBK 编码的 CSV 文件"""
    file_path = tmp_path / "gbk.csv"
    content = (
        "station,signal_type,address,tag,signal_name,device,comment\n"
        "cpu,DI,X0,Tag_中文,信号名,设备,注释\n"
    )
    file_path.write_bytes(content.encode("gbk"))
    return file_path


@pytest.fixture
def utf8_bom_csv(tmp_path: Path) -> Path:
    """UTF-8 BOM 编码的 CSV 文件"""
    file_path = tmp_path / "bom.csv"
    content = (
        "station,signal_type,address,tag,signal_name,device,comment\n"
        "cpu,DI,X0,Tag_BOM,信号,设备,注释\n"
    )
    file_path.write_bytes(content.encode("utf-8-sig"))
    return file_path
