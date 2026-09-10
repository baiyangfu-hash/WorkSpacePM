"""包可导入性验证 + 基础功能测试"""

from __future__ import annotations

import sw_2026_010
from sw_2026_010 import __app_name__, __version__


def test_package_importable() -> None:
    """验证包可以被导入"""
    assert sw_2026_010 is not None


def test_app_name() -> None:
    """验证 app_name 常量"""
    assert __app_name__ == "sw-2026-010"


def test_version() -> None:
    """验证版本号格式"""
    assert __version__ == "V1.0.0"
    # 简单的语义化版本格式检查
    parts = __version__.split(".")
    assert len(parts) >= 2, "版本号应至少包含 major.minor"


def test_app_context_creation() -> None:
    """验证 AppContext 可创建"""
    from sw_2026_010.app_context import AppContext

    ctx = AppContext()
    assert ctx.workspace_root  # 应有默认值
    assert ctx.app_config is not None
    assert ctx.logger is not None


def test_file_utils_roundtrip(tmp_workspace: str) -> None:
    """验证 file_utils 读写往返"""
    from sw_2026_010.utils.file_utils import read_file, write_file

    file_path = f"{tmp_workspace}/test_roundtrip.txt"
    content = "hello world\n中文测试"
    write_file(file_path, content)
    assert read_file(file_path) == content


def test_cli_hello_command() -> None:
    """验证 CLI hello 命令可调用"""
    from click.testing import CliRunner

    from sw_2026_010.cli.__main__ import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["hello"])
    assert result.exit_code == 0
    assert "Hello from 驾驶舱A6Python验证套件" in result.output


def test_cli_help() -> None:
    """验证 CLI --help 可用"""
    from click.testing import CliRunner

    from sw_2026_010.cli.__main__ import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "驾驶舱A6Python验证套件" in result.output
