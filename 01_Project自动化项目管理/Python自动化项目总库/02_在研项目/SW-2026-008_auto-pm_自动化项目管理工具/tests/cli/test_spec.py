"""spec CLI 命令边界用例 - V0.5.2 步骤3

本文件仅包含 spec_group 的边界用例（新增）。
原有 spec CLI 测试仍在 tests/spec/test_cli.py（依赖 tests/spec/conftest.py 的 fixture）。

统一组织通过 run_tests.py cli 模式涵盖 tests/cli/ + tests/spec/test_cli.py。
新增的边界用例放在本文件，使用 tests/cli/conftest.py 的 fixture 体系。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from auto_pm.cli.__main__ import cli
from auto_pm.cli.spec import spec_group
from click.testing import CliRunner

from auto_pm import __version__


@pytest.mark.cli
class TestSpecCLIBoundary:
    """spec CLI 边界用例（V0.5.2 新增）

    补充 tests/spec/test_cli.py 未覆盖的边界场景。
    """

    def test_help_shows_subcommands(self, cli_runner: CliRunner) -> None:
        """--help 显示所有子命令"""
        result = cli_runner.invoke(spec_group, ["--help"])
        assert result.exit_code == 0
        assert "规范管理" in result.output
        # 应列出所有子命令
        assert "check" in result.output
        assert "index" in result.output
        assert "frontmatter" in result.output
        assert "report" in result.output

    def test_no_subcommand(self, cli_runner: CliRunner) -> None:
        """无子命令时 click 显示帮助 exit_code != 0"""
        result = cli_runner.invoke(spec_group, [])
        # click group 无子命令时通常 exit_code=0 显示帮助，或 exit_code=2
        # 具体行为取决于 click 版本，这里验证不崩溃
        assert result.exit_code in (0, 2)

    def test_invalid_subcommand(self, cli_runner: CliRunner) -> None:
        """无效子命令 click 报错 exit_code != 0"""
        result = cli_runner.invoke(spec_group, ["invalid-subcommand"])
        assert result.exit_code != 0

    def test_spec_lint_skips_registry_meta_entries(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """spec lint 应忽略 registry 中的非规范元条目，而不是崩溃"""
        spec_root = tmp_path / "00_Obsidian_Base全局规范文件仓库"
        domain_dir = spec_root / "01_项目管理域"
        domain_dir.mkdir(parents=True, exist_ok=True)
        (domain_dir / "001_测试规范_DEV.md").write_text(
            "---\nspec_id: DEV-001\ntitle: 测试规范\nlifecycle: stable\n---\n",
            encoding="utf-8",
        )
        (spec_root / "spec_registry.json").write_text(
            json.dumps(
                {
                    "workspace_root": str(tmp_path),
                    "specs": {
                        "DEV-001": {
                            "canonical_path": (
                                "00_Obsidian_Base全局规范文件仓库/"
                                "01_项目管理域/001_测试规范_DEV.md"
                            )
                        },
                        "_governance_note": "not-a-spec-entry",
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        result = cli_runner.invoke(
            spec_group,
            ["lint", "-w", str(tmp_path), "--format", "json"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["total"] == 0

    def test_spec_index_report_and_frontmatter_skip_registry_meta_entries(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """spec index/report/frontmatter 应忽略 registry 中的非规范元条目"""
        spec_root = tmp_path / "00_Obsidian_Base全局规范文件仓库"
        domain_dir = spec_root / "01_项目管理域" / "00_元规则与治理"
        domain_dir.mkdir(parents=True, exist_ok=True)
        spec_file = domain_dir / "001_测试规范_DEV.md"
        spec_file.write_text(
            (
                "---\n"
                "spec_id: DEV-001\n"
                "title: 测试规范\n"
                "version: V1.0.0\n"
                "lifecycle: stable\n"
                "domain: pm\n"
                "sub_domain: 00_元规则与治理\n"
                "canonical_path: "
                "00_Obsidian_Base全局规范文件仓库/01_项目管理域/00_元规则与治理/001_测试规范_DEV.md\n"
                "---\n"
            ),
            encoding="utf-8",
        )
        (spec_root / "spec_registry.json").write_text(
            json.dumps(
                {
                    "version": "1.0.0",
                    "workspace_root": str(tmp_path),
                    "domains": {"pm": "项目管理域"},
                    "specs": {
                        "DEV-001": {
                            "title": "测试规范",
                            "number": "001",
                            "canonical_path": (
                                "00_Obsidian_Base全局规范文件仓库/"
                                "01_项目管理域/00_元规则与治理/001_测试规范_DEV.md"
                            ),
                            "version": "V1.0.0",
                            "type_prefix": "DEV",
                            "domain": "pm",
                            "lifecycle": "stable",
                            "sub_domain": "00_元规则与治理",
                        },
                        "_governance_note": "not-a-spec-entry",
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        index_result = cli_runner.invoke(
            spec_group,
            ["index", "-w", str(tmp_path), "--domain", "pm"],
        )
        report_result = cli_runner.invoke(
            spec_group,
            ["report", "-w", str(tmp_path), "--format", "markdown"],
        )
        frontmatter_result = cli_runner.invoke(
            spec_group,
            ["frontmatter", "-w", str(tmp_path)],
        )

        assert index_result.exit_code == 0
        assert (spec_root / "00_INDEX_全局规范索引.md").exists()
        assert report_result.exit_code == 0
        assert (spec_root / "规范元数据汇总报告.md").exists()
        assert frontmatter_result.exit_code == 0

    def test_spec_lint_skips_archive_change_tickets_and_legacy_compatible_dirs(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """spec lint 应跳过非规范工件、归档规范和兼容双目录结构"""
        spec_root = tmp_path / "00_Obsidian_Base全局规范文件仓库"
        archive_dir = spec_root / "_archive" / "deprecated"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archived_spec = archive_dir / "802_PLC工作流命名规范_DEV.md"
        archived_spec.write_text("# archived\n", encoding="utf-8")

        change_dir = (
            spec_root / "01_项目管理域" / "04_变更管理" / "01_变更单" / "CHG-PLC"
        )
        change_dir.mkdir(parents=True, exist_ok=True)
        (change_dir / "CHG-PLC-2026-001.md").write_text("# change ticket\n", encoding="utf-8")

        plc_project = tmp_path / "0100_PLC自动化" / "DJ-2026-001_兼容项目"
        (plc_project / "01_启动").mkdir(parents=True, exist_ok=True)
        (plc_project / "01_需求与设计").mkdir(parents=True, exist_ok=True)

        (spec_root / "spec_registry.json").write_text(
            json.dumps(
                {
                    "workspace_root": str(tmp_path),
                    "specs": {
                        "DEV-802": {
                            "canonical_path": "00_Obsidian_Base全局规范文件仓库/_archive/deprecated/802_PLC工作流命名规范_DEV.md",
                            "lifecycle": "deprecated",
                        }
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        result = cli_runner.invoke(
            spec_group,
            ["lint", "-w", str(tmp_path), "--format", "json"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["total"] == 0

    def test_cli_version_matches_package_version(self, cli_runner: CliRunner) -> None:
        """CLI --version 应复用包版本真值"""
        result = cli_runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output
