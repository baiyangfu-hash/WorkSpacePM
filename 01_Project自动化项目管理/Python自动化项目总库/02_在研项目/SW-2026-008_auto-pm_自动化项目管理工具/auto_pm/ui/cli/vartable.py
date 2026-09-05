"""PLC-HMI 概念映射：CLI 命令行入口（变量表命令组（解析/转换/导出））

像 PLC 的调试终端/工程师站，通过命令行直接操作功能块。
不经过 HMI 画面，直接调用 FB 或 SFB。

--- 原始注释 ---

变量表管理命令组 - V2.3 吸收 SW-2026-001 变量表解析能力

提供变量表解析、编码检测、格式识别能力。

子命令：
- parse: 自动识别格式并解析变量表文件，输出条目详情
- detect-encoding: 检测文件编码
- list-formats: 列出支持的解析格式
- detect-format: 识别文件格式
- convert: 解析变量表文件并导出为 CSV/YAML/JSON（V2.3 Week3 T13）
- batch-parse: 批量解析目录下多个变量表文件（V2.3 Week3 T14）

V2.3 Week2 T12：
- parse 命令扩展支持自动识别格式 + 显式 --format 指定
- 新增 list-formats / detect-format 子命令
- 支持 io_points.csv / program_blocks.yml / communications.yml + 5 PLC 格式

V2.3 Week3 T12-T14：
- 5 格式 Parser 深化（detect_format 方法 + 真实字段提取）
- 新增 convert 子命令（CSV/YAML/JSON 导出）
- 新增 batch-parse 子命令（目录扫描 + 多文件聚合）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from auto_pm.vartable.batch_parser import BatchParser
from auto_pm.vartable.converter import SUPPORTED_OUTPUT_FORMATS, VariableConverter
from auto_pm.vartable.models import FormatType, ParseResult
from auto_pm.vartable.parsers.format_detector import (
    detect_format,
    get_parser_for_format,
    list_supported_formats,
)
from auto_pm.vartable.utils.encoding import SUPPORTED_ENCODINGS, detect_encoding

console = Console()

# CLI --format 选项可选值（不含 UNKNOWN）
_FORMAT_CHOICES = [fmt.value for fmt in FormatType if fmt != FormatType.UNKNOWN]


def _supports_unicode_output() -> bool:
    """检查当前终端是否支持 Unicode 输出（避免 GBK 终端 emoji 崩溃）"""
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        "✅❌📊".encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return False
    return True


def _parse_with_format(file_path: str, fmt_value: str | None) -> ParseResult:
    """根据显式 --format 或自动识别选择解析器并执行解析

    Args:
        file_path: 文件路径
        fmt_value: 显式格式值（None 表示自动识别）

    Returns:
        ParseResult
    """
    if fmt_value is not None:
        # 显式指定格式
        try:
            fmt = FormatType(fmt_value)
        except ValueError:
            return ParseResult(
                success=False,
                var_table=None,
                errors=tuple(),
                warnings=(f"不支持的格式: {fmt_value}",),
            )
    else:
        # 自动识别格式
        fmt = detect_format(file_path)

    parser_cls = get_parser_for_format(fmt)
    if parser_cls is None:
        return ParseResult(
            success=False,
            var_table=None,
            errors=(),
            warnings=(f"格式 {fmt.value} 无对应解析器",),
        )

    # 实例化并调用 parse()；parser_cls 类型为 type，需显式标注返回类型
    parser = parser_cls()
    result = parser.parse(file_path)
    if isinstance(result, ParseResult):
        return result
    return ParseResult(
        success=False,
        var_table=None,
        errors=(),
        warnings=("解析器返回类型异常",),
    )


@click.group(name="vartable")
def vartable_group() -> None:
    """变量表管理 - 解析/编码检测/格式识别（V2.3 吸收 SW-2026-001）"""


@vartable_group.command(name="parse")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(_FORMAT_CHOICES),
    default=None,
    help="显式指定解析格式（默认自动识别）",
)
@click.option(
    "--output-format",
    "output_fmt",
    type=click.Choice(["table", "json"]),
    default="table",
    help="输出格式",
)
@click.argument("file_path", type=click.Path(exists=True, dir_okay=False, resolve_path=True))
def parse_command(file_path: str, fmt: str | None, output_fmt: str) -> None:
    """解析变量表文件，输出条目详情。

    FILE_PATH: 变量表文件路径（io_points.csv/program_blocks.yml/communications.yml/.scl/.asc/.wr3 等）

    自动识别格式；可用 --format 显式指定（autoshop/work3/codesys/scl/intdoc/io_points_csv/program_blocks_yml/communications_yml）。

    示例：
    auto-pm vartable parse path/to/io_points.csv
    auto-pm vartable parse path/to/program_blocks.yml --format program_blocks_yml
    auto-pm vartable parse path/to/file.scl --output-format json
    """
    result = _parse_with_format(file_path, fmt)

    if output_fmt == "json":
        # JSON 输出禁止任何非 JSON 文本污染 stdout（日志走 stderr）
        click.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return

    # 表格输出
    if not result.success:
        console.print("[red]解析失败[/red]")
        for err in result.errors:
            console.print(
                f"  [red]L{err.line_number}[/red] {escape(err.field)}: {escape(err.message)}"
            )
        for w in result.warnings:
            console.print(f"  [yellow]{escape(w)}[/yellow]")
        raise SystemExit(1)

    # 概要
    icon_ok = "✅" if _supports_unicode_output() else "[OK]"
    if result.var_table is not None:
        console.print(f"{icon_ok} 解析完成: {result.entry_count} 条变量")
    elif result.block_table is not None:
        console.print(f"{icon_ok} 解析完成: {result.entry_count} 个程序块")
    elif result.channel_table is not None:
        console.print(f"{icon_ok} 解析完成: {result.entry_count} 个通道")
    else:
        console.print(f"{icon_ok} 解析完成: {result.entry_count} 条")

    # 根据填充的 table 类型输出不同的概要信息
    if result.var_table is not None:
        _print_var_table_summary(result)
        _print_var_table_detail(result)
    elif result.block_table is not None:
        _print_block_table_summary(result)
        _print_block_table_detail(result)
    elif result.channel_table is not None:
        _print_channel_table_summary(result)
        _print_channel_table_detail(result)


def _print_var_table_summary(result: ParseResult) -> None:
    """打印 VarTable 概要"""
    assert result.var_table is not None
    table = result.var_table
    console.print(f"   源文件: {escape(table.source_path)}")
    console.print(f"   编码: {escape(table.encoding)}")
    console.print(f"   站点: {escape(', '.join(table.stations))}")
    console.print(f"   信号类型: {escape(', '.join(table.signal_types))}")
    if result.warnings:
        for w in result.warnings:
            console.print(f"   [yellow]警告: {escape(w)}[/yellow]")
    if result.errors:
        console.print(f"   [yellow]跳过错误行: {result.error_count} 个[/yellow]")


def _print_var_table_detail(result: ParseResult) -> None:
    """打印 VarTable 详细表格"""
    assert result.var_table is not None
    table = result.var_table

    detail_table = Table(title="变量条目详情", expand=True)
    detail_table.add_column("行号", style="cyan", justify="right", no_wrap=True)
    detail_table.add_column("站点", style="magenta", no_wrap=True)
    detail_table.add_column("类型", style="yellow", no_wrap=True)
    detail_table.add_column("地址", style="green", no_wrap=True)
    detail_table.add_column("Tag", style="white", overflow="fold")
    detail_table.add_column("信号名", style="white", overflow="fold")
    detail_table.add_column("设备", style="dim", overflow="fold")
    detail_table.add_column("注释", style="dim", overflow="fold")

    for entry in table.entries:
        detail_table.add_row(
            str(entry.line_number),
            entry.station,
            entry.signal_type,
            entry.address,
            entry.tag,
            entry.signal_name,
            entry.device,
            entry.comment,
        )

    # 用宽 console 打印表格,避免 Rich 在窄终端下截断 Tag/信号名
    wide_console = Console(width=max(console.width, 200))
    wide_console.print(detail_table)


def _print_block_table_summary(result: ParseResult) -> None:
    """打印 BlockTable 概要"""
    assert result.block_table is not None
    table = result.block_table
    console.print(f"   源文件: {escape(table.source_path)}")
    console.print(f"   编码: {escape(table.encoding)}")
    console.print(f"   块类型: {escape(', '.join(table.block_types))}")
    project_id = str(table.metadata.get("project_id", ""))
    if project_id:
        console.print(f"   项目ID: {escape(project_id)}")
    project_name = str(table.metadata.get("project_name", ""))
    if project_name:
        console.print(f"   项目名: {escape(project_name)}")
    if result.warnings:
        for w in result.warnings:
            console.print(f"   [yellow]警告: {escape(w)}[/yellow]")
    if result.errors:
        console.print(f"   [yellow]跳过错误项: {result.error_count} 个[/yellow]")


def _print_block_table_detail(result: ParseResult) -> None:
    """打印 BlockTable 详细表格"""
    assert result.block_table is not None
    table = result.block_table

    detail_table = Table(title="程序块条目详情", expand=True)
    detail_table.add_column("#", style="cyan", justify="right", no_wrap=True)
    detail_table.add_column("块名", style="magenta", overflow="fold")
    detail_table.add_column("类型", style="yellow", no_wrap=True)
    detail_table.add_column("路径", style="green", overflow="fold")
    detail_table.add_column("职责", style="white", overflow="fold")

    for entry in table.entries:
        detail_table.add_row(
            str(entry.index),
            entry.block_name,
            entry.block_type,
            entry.path,
            entry.responsibility,
        )

    wide_console = Console(width=max(console.width, 200))
    wide_console.print(detail_table)


def _print_channel_table_summary(result: ParseResult) -> None:
    """打印 ChannelTable 概要"""
    assert result.channel_table is not None
    table = result.channel_table
    console.print(f"   源文件: {escape(table.source_path)}")
    console.print(f"   编码: {escape(table.encoding)}")
    console.print(f"   协议: {escape(', '.join(table.protocols))}")
    project_id = str(table.metadata.get("project_id", ""))
    if project_id:
        console.print(f"   项目ID: {escape(project_id)}")
    project_type = str(table.metadata.get("project_type", ""))
    if project_type:
        console.print(f"   项目类型: {escape(project_type)}")
    if result.warnings:
        for w in result.warnings:
            console.print(f"   [yellow]警告: {escape(w)}[/yellow]")
    if result.errors:
        console.print(f"   [yellow]跳过错误项: {result.error_count} 个[/yellow]")


def _print_channel_table_detail(result: ParseResult) -> None:
    """打印 ChannelTable 详细表格"""
    assert result.channel_table is not None
    table = result.channel_table

    detail_table = Table(title="通信通道条目详情", expand=True)
    detail_table.add_column("#", style="cyan", justify="right", no_wrap=True)
    detail_table.add_column("通道名", style="magenta", overflow="fold")
    detail_table.add_column("协议", style="yellow", no_wrap=True)
    detail_table.add_column("角色", style="white", overflow="fold")
    detail_table.add_column("端点", style="green", overflow="fold")
    detail_table.add_column("备注", style="dim", overflow="fold")

    for entry in table.entries:
        detail_table.add_row(
            str(entry.index),
            entry.channel_name,
            entry.protocol,
            entry.role,
            entry.endpoint,
            entry.notes,
        )

    wide_console = Console(width=max(console.width, 200))
    wide_console.print(detail_table)


@vartable_group.command(name="detect-encoding")
@click.option(
    "--format", "fmt", type=click.Choice(["text", "json"]), default="text", help="输出格式"
)
@click.argument("file_path", type=click.Path(exists=True, dir_okay=False, resolve_path=True))
def detect_encoding_command(file_path: str, fmt: str) -> None:
    """检测文件编码。

    FILE_PATH: 待检测文件路径

    示例：
    auto-pm vartable detect-encoding path/to/io_points.csv
    auto-pm vartable detect-encoding path/to/file --format json
    """
    try:
        encoding = detect_encoding(file_path)
    except FileNotFoundError as exc:
        if fmt == "json":
            click.echo(json.dumps({"error": str(exc)}, ensure_ascii=False))
        else:
            console.print(f"[red]错误: {escape(str(exc))}[/red]")
        raise SystemExit(1) from exc

    if fmt == "json":
        click.echo(
            json.dumps(
                {"file": file_path, "encoding": encoding},
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    icon = "✅" if _supports_unicode_output() else "[OK]"
    console.print(f"{icon} 文件编码检测结果")
    console.print(f"   文件: {escape(file_path)}")
    console.print(f"   编码: [green]{escape(encoding)}[/green]")


@vartable_group.command(name="list-encodings")
def list_encodings_command() -> None:
    """列出支持的编码列表"""
    console.print("[bold]支持的编码列表[/bold]")
    for enc in SUPPORTED_ENCODINGS:
        console.print(f"  - {escape(enc)}")


@vartable_group.command(name="list-formats")
@click.option(
    "--format", "fmt", type=click.Choice(["text", "json"]), default="text", help="输出格式"
)
def list_formats_command(fmt: str) -> None:
    """列出支持的解析格式。

    示例：
    auto-pm vartable list-formats
    auto-pm vartable list-formats --format json
    """
    formats = list_supported_formats()

    if fmt == "json":
        payload = [
            {
                "format": f.value,
                "description": desc,
                "extensions": list(exts),
            }
            for f, desc, exts in formats
        ]
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    table = Table(title="支持的解析格式", expand=True)
    table.add_column("格式", style="cyan", no_wrap=True)
    table.add_column("说明", style="white", overflow="fold")
    table.add_column("扩展名/文件名", style="green", overflow="fold")

    for f, desc, exts in formats:
        table.add_row(f.value, desc, ", ".join(exts))

    wide_console = Console(width=max(console.width, 200))
    wide_console.print(table)


@vartable_group.command(name="detect-format")
@click.option(
    "--format", "fmt", type=click.Choice(["text", "json"]), default="text", help="输出格式"
)
@click.argument("file_path", type=click.Path(exists=True, dir_okay=False, resolve_path=True))
def detect_format_command(file_path: str, fmt: str) -> None:
    """识别文件格式。

    FILE_PATH: 待识别文件路径

    示例：
    auto-pm vartable detect-format path/to/io_points.csv
    auto-pm vartable detect-format path/to/file.scl --format json
    """
    detected = detect_format(file_path)

    if fmt == "json":
        click.echo(
            json.dumps(
                {"file": file_path, "format": detected.value},
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    icon = "✅" if _supports_unicode_output() else "[OK]"
    console.print(f"{icon} 文件格式识别结果")
    console.print(f"   文件: {escape(file_path)}")
    console.print(f"   格式: [green]{escape(detected.value)}[/green]")


@vartable_group.command(name="convert")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(_FORMAT_CHOICES),
    default=None,
    help="显式指定解析格式（默认自动识别）",
)
@click.option(
    "--output-format",
    "output_fmt",
    type=click.Choice(list(SUPPORTED_OUTPUT_FORMATS)),
    default="csv",
    help="输出格式（csv/yaml/json）",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, resolve_path=True),
    default=None,
    help="输出文件路径（默认输出到 stdout）",
)
@click.argument("file_path", type=click.Path(exists=True, dir_okay=False, resolve_path=True))
def convert_command(
    file_path: str,
    fmt: str | None,
    output_fmt: str,
    output_path: str | None,
) -> None:
    """解析变量表文件并导出为 CSV/YAML/JSON。

    FILE_PATH: 变量表文件路径（io_points.csv/program_blocks.yml/communications.yml/.scl/.asc/.wr3 等）

    自动识别格式；可用 --format 显式指定。
    默认输出 CSV 到 stdout；可用 --output-format 指定 yaml/json；可用 --output 写入文件。

    示例：
    auto-pm vartable convert path/to/io_points.csv --output-format csv
    auto-pm vartable convert path/to/file.scl --output-format yaml --output out.yaml
    auto-pm vartable convert path/to/program_blocks.yml --output-format json
    """
    result = _parse_with_format(file_path, fmt)

    if not result.success:
        console.print("[red]解析失败，无法转换[/red]")
        for err in result.errors:
            console.print(
                f"  [red]L{err.line_number}[/red] {escape(err.field)}: {escape(err.message)}"
            )
        for w in result.warnings:
            console.print(f"  [yellow]{escape(w)}[/yellow]")
        raise SystemExit(1)

    converter = VariableConverter()
    try:
        content = converter.convert(result, output_fmt)
    except ValueError as exc:
        console.print(f"[red]转换失败: {escape(str(exc))}[/red]")
        raise SystemExit(1) from exc

    if output_path is not None:
        Path(output_path).write_text(content, encoding="utf-8")
        icon = "✅" if _supports_unicode_output() else "[OK]"
        console.print(f"{icon} 已导出到: {escape(output_path)}")
        console.print(f"   格式: [green]{escape(output_fmt)}[/green]")
        console.print(f"   条目数: {result.entry_count}")
        return

    # 输出到 stdout（纯文本，不附带 rich 颜色）
    click.echo(content)


@vartable_group.command(name="batch-parse")
@click.option(
    "--recursive",
    is_flag=True,
    default=False,
    help="递归扫描子目录",
)
@click.option(
    "--output-format",
    "output_fmt",
    type=click.Choice(["table", "json"]),
    default="table",
    help="输出格式",
)
@click.argument("dir_path", type=click.Path(exists=True, file_okay=False, resolve_path=True))
def batch_parse_command(dir_path: str, recursive: bool, output_fmt: str) -> None:
    """批量解析目录下多个变量表文件。

    DIR_PATH: 目录路径

    自动识别目录下支持的格式（.asc/.asn/.wr3/.scl/.awl/.yml/.yaml + io_points.csv 等），
    逐个解析并聚合结果。--recursive 递归扫描子目录。

    示例：
    auto-pm vartable batch-parse path/to/dir
    auto-pm vartable batch-parse path/to/dir --recursive --output-format json
    """
    batch_parser = BatchParser()
    try:
        results = batch_parser.parse_directory(dir_path, recursive=recursive)
    except (FileNotFoundError, NotADirectoryError) as exc:
        console.print(f"[red]错误: {escape(str(exc))}[/red]")
        raise SystemExit(1) from exc

    if output_fmt == "json":
        payload = {
            "dir_path": dir_path,
            "recursive": recursive,
            "total_files": len(results),
            "success_count": sum(1 for r in results if r.success),
            "failure_count": sum(1 for r in results if not r.success),
            "results": [r.to_dict() for r in results],
        }
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    # 表格输出
    icon = "✅" if _supports_unicode_output() else "[OK]"
    success_count = sum(1 for r in results if r.success)
    failure_count = len(results) - success_count
    console.print(
        f"{icon} 批量解析完成: {len(results)} 个文件（成功 {success_count} / 失败 {failure_count}）"
    )
    console.print(f"   目录: {escape(dir_path)}")
    console.print(f"   递归: {'是' if recursive else '否'}")

    if not results:
        console.print("[yellow]   未找到支持的变量表文件[/yellow]")
        return

    detail_table = Table(title="批量解析结果", expand=True)
    detail_table.add_column("#", style="cyan", justify="right", no_wrap=True)
    detail_table.add_column("文件", style="white", overflow="fold")
    detail_table.add_column("状态", style="magenta", no_wrap=True)
    detail_table.add_column("条目数", style="yellow", justify="right", no_wrap=True)
    detail_table.add_column("格式", style="green", overflow="fold")
    detail_table.add_column("警告/错误", style="dim", overflow="fold")

    for idx, result in enumerate(results, start=1):
        # 从 result 提取文件路径和格式信息
        source_path = ""
        source_format = ""
        if result.var_table is not None:
            source_path = result.var_table.source_path
            source_format = result.var_table.source_format
        elif result.block_table is not None:
            source_path = result.block_table.source_path
            source_format = result.block_table.source_format
        elif result.channel_table is not None:
            source_path = result.channel_table.source_path
            source_format = result.channel_table.source_format

        status = "✅ 成功" if result.success else "❌ 失败"
        if not _supports_unicode_output():
            status = "[OK]" if result.success else "[FAIL]"

        # 仅显示文件名（完整路径太长）
        display_path = Path(source_path).name if source_path else "(未知)"
        entry_count = str(result.entry_count) if result.success else "-"
        warn_info = ""
        if result.warnings:
            warn_info = f"警告 {result.warning_count}"
        if result.errors:
            warn_info = f"{warn_info} / 错误 {result.error_count}".strip(" /")

        detail_table.add_row(
            str(idx),
            display_path,
            status,
            entry_count,
            source_format or "-",
            warn_info or "-",
        )

    wide_console = Console(width=max(console.width, 200))
    wide_console.print(detail_table)
