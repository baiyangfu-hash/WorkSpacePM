"""rated-current 命令与三相电机额定电流计算测试"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from sw_2026_010.cli.__main__ import cli
from sw_2026_010.core.rated_current import calculate_rated_current

NOMINAL_ARGS = {
    "--power-kw": "7.5",
    "--voltage-v": "380",
    "--power-factor": "0.85",
    "--efficiency": "0.9",
}
EXPECTED_CURRENT = 14.9
TOLERANCE = 0.05


def test_calculate_rated_current_nominal() -> None:
    """7.5 kW / 380 V / 0.85 / 0.9 应约为 14.9 A"""
    current = calculate_rated_current(7.5, 380.0, 0.85, 0.9)
    assert current == pytest.approx(EXPECTED_CURRENT, abs=TOLERANCE)


def test_cli_rated_current_nominal() -> None:
    """CLI 正例：输出 1 位小数且退出码为 0"""
    result = CliRunner().invoke(cli, _build_args(NOMINAL_ARGS))
    assert result.exit_code == 0
    assert "三相电机额定电流: 14.9 A" in result.output


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("--power-kw", "0"),
        ("--power-kw", "-1"),
        ("--voltage-v", "0"),
        ("--voltage-v", "-1"),
        ("--power-factor", "0"),
        ("--power-factor", "-1"),
        ("--efficiency", "0"),
        ("--efficiency", "-1"),
    ],
)
def test_cli_rejects_non_positive_inputs(option: str, value: str) -> None:
    """任一输入为 0 或负数：中文报错、非零退出码、无 traceback"""
    args = _build_args({**NOMINAL_ARGS, option: value})
    result = CliRunner().invoke(cli, args)
    assert result.exit_code != 0
    assert "必须大于 0" in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize("option", sorted(NOMINAL_ARGS))
def test_cli_requires_all_inputs(option: str) -> None:
    """缺少任一输入时由 Click 报用法错误"""
    args = _build_args({key: value for key, value in NOMINAL_ARGS.items() if key != option})
    result = CliRunner().invoke(cli, args)
    assert result.exit_code != 0


def test_cli_help_lists_rated_current() -> None:
    """--help 应列出 rated-current 命令"""
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "rated-current" in result.output


def _build_args(values: dict[str, str]) -> list[str]:
    args = ["rated-current"]
    for option, value in values.items():
        args.extend([option, value])
    return args
