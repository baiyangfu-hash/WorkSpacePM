"""IO 点表 CSV 读取测试"""

from __future__ import annotations

from pathlib import Path

import pytest

from sw_2026_010.core.io_table import (
    Duplicate,
    IoPoint,
    IoTableError,
    find_duplicates,
    format_duplicate_report,
    read_io_table,
)


def _write(path: Path, text: str, encoding: str = "utf-8") -> Path:
    path.write_bytes(text.encode(encoding))
    return path


def test_reads_rows_in_file_order(tmp_path: Path) -> None:
    """正常三行：字段、顺序与物理行号正确"""
    csv_path = _write(
        tmp_path / "points.csv",
        "变量名,地址,注释\n"
        "StartButton,%I0.0,启动按钮\n"
        "TowerLamp,%Q0.0,三色灯\n"
        "SpeedValue,%IW64,速度给定\n",
    )
    assert read_io_table(csv_path) == [
        IoPoint("StartButton", "%I0.0", "启动按钮", 2),
        IoPoint("TowerLamp", "%Q0.0", "三色灯", 3),
        IoPoint("SpeedValue", "%IW64", "速度给定", 4),
    ]


def test_preserves_duplicate_rows(tmp_path: Path) -> None:
    """重复的变量名与地址原样保留，供查重阶段判定"""
    csv_path = _write(
        tmp_path / "dups.csv",
        "变量名,地址,注释\nDup,%I0.1,第一次出现\nDup,%I0.1,第二次出现\n",
    )
    points = read_io_table(csv_path)
    assert len(points) == 2
    assert points[0] == IoPoint("Dup", "%I0.1", "第一次出现", 2)
    assert points[1] == IoPoint("Dup", "%I0.1", "第二次出现", 3)


def test_handles_bom_crlf_and_blank_lines(tmp_path: Path) -> None:
    """UTF-8 BOM、CRLF 与空行不影响解析"""
    csv_path = tmp_path / "bom.csv"
    csv_path.write_bytes(
        "\ufeff变量名,地址,注释\r\nA,%I0.2,注释A\r\n\r\nB,%Q0.2,注释B\r\n".encode("utf-8")
    )
    points = read_io_table(csv_path)
    assert [point.variable_name for point in points] == ["A", "B"]
    assert [point.line_number for point in points] == [2, 4]


def test_accepts_reordered_header_and_extra_columns(tmp_path: Path) -> None:
    """表头乱序、多余列与单元格空白均被正确处理"""
    csv_path = _write(
        tmp_path / "reordered.csv",
        "地址, 注释,变量名,单元\n %I0.3 , 注释C ,C_Start,X\n",
    )
    assert read_io_table(csv_path) == [IoPoint("C_Start", "%I0.3", "注释C", 2)]


def test_keeps_comma_inside_quoted_comment(tmp_path: Path) -> None:
    """引号内的逗号属于注释内容"""
    csv_path = _write(
        tmp_path / "quoted.csv",
        '变量名,地址,注释\nQ,%Q0.3,"启动, 停止指示"\n',
    )
    points = read_io_table(csv_path)
    assert points[0].comment == "启动, 停止指示"


def test_missing_required_column_raises(tmp_path: Path) -> None:
    """缺少必需列时给出中文错误并点名缺失列"""
    csv_path = _write(tmp_path / "missing.csv", "变量名,地址\nA,%I0.4\n")
    with pytest.raises(IoTableError, match="缺少必需列.*注释"):
        read_io_table(csv_path)


def test_empty_file_raises(tmp_path: Path) -> None:
    """空文件报中文错误"""
    csv_path = _write(tmp_path / "empty.csv", "")
    with pytest.raises(IoTableError, match="为空"):
        read_io_table(csv_path)


def test_header_only_returns_empty_list(tmp_path: Path) -> None:
    """只有表头时返回空列表"""
    csv_path = _write(tmp_path / "header.csv", "变量名,地址,注释\n")
    assert read_io_table(csv_path) == []


def test_decodes_gb18030(tmp_path: Path) -> None:
    """中文 Excel 导出的 GB18030 编码文件可解码"""
    csv_path = _write(
        tmp_path / "gbk.csv",
        "变量名,地址,注释\n电机启动,%Q0.4,中文注释\n",
        encoding="gb18030",
    )
    assert read_io_table(csv_path) == [IoPoint("电机启动", "%Q0.4", "中文注释", 2)]


def test_undecodable_file_raises(tmp_path: Path) -> None:
    """UTF-8 与 GB18030 都无法解码时报中文错误"""
    csv_path = tmp_path / "broken.csv"
    csv_path.write_bytes(b"\x81")
    with pytest.raises(IoTableError, match="编码无法识别"):
        read_io_table(csv_path)


def test_missing_file_raises(tmp_path: Path) -> None:
    """文件不存在时报中文错误"""
    with pytest.raises(IoTableError, match="文件不存在"):
        read_io_table(tmp_path / "absent.csv")


def _points(*rows: tuple[str, str]) -> list[IoPoint]:
    return [IoPoint(name, address, "", line) for line, (name, address) in enumerate(rows, start=2)]


def test_finds_duplicate_addresses_and_names() -> None:
    """重复地址与重复变量名分别报出，带全部行号"""
    report = find_duplicates(
        _points(("Start", "%I0.0"), ("Stop", "%I0.1"), ("Lamp", "%I0.0"), ("Start", "%Q0.0"))
    )
    assert report.addresses == (Duplicate("%I0.0", (2, 4)),)
    assert report.variable_names == (Duplicate("Start", (2, 5)),)
    assert report.has_duplicates


def test_no_duplicates() -> None:
    """没有重复时报告为空，文字说明未发现重复"""
    report = find_duplicates(_points(("A", "%I0.0"), ("B", "%I0.1")))
    assert not report.has_duplicates
    assert format_duplicate_report(report) == "未发现重复的地址或变量名。"


def test_address_compare_ignores_case_and_spaces() -> None:
    """%i0.0、% I0.0 与 %I0.0 是同一地址"""
    report = find_duplicates(_points(("A", "%i0.0"), ("B", "% I0.0"), ("C", "%I0.0")))
    assert report.addresses == (Duplicate("%I0.0", (2, 3, 4)),)


def test_name_compare_ignores_case() -> None:
    """变量名不区分大小写，报告写首次出现的原样"""
    report = find_duplicates(_points(("MotorOn", "%Q0.0"), ("motoron", "%Q0.1")))
    assert report.variable_names == (Duplicate("MotorOn", (2, 3)),)


def test_blank_cells_are_not_duplicates() -> None:
    """空地址、空变量名不算重复"""
    report = find_duplicates(_points(("", "%I0.0"), ("", "%I0.1"), ("A", ""), ("B", "")))
    assert not report.has_duplicates


def test_groups_are_ordered_by_first_line() -> None:
    """多组重复按首次出现的行号排序"""
    report = find_duplicates(
        _points(("X", "%I1.0"), ("Y", "%I0.0"), ("Z", "%I0.0"), ("W", "%I1.0"))
    )
    assert [group.key for group in report.addresses] == ["%I1.0", "%I0.0"]


def test_report_text_lists_addresses_and_names(tmp_path: Path) -> None:
    """从 CSV 读入到查重报告的整条链路"""
    csv_path = _write(
        tmp_path / "plant.csv",
        "变量名,地址,注释\nStart,%I0.0,启动\nStop,%I0.0,停止\nStart,%I0.2,备用启动\n",
    )
    text = format_duplicate_report(find_duplicates(read_io_table(csv_path)))
    assert text == (
        "重复地址（1 组）:\n  %I0.0: 第 2, 3 行\n重复变量名（1 组）:\n  Start: 第 2, 4 行"
    )
