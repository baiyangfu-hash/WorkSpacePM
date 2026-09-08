"""CLI 测试 - 适配 auto_pm.spec 命令组。

auto_pm 的 spec 命令组入口为 auto_pm.cli.spec:spec_group，每个子命令独立
接收 --workspace/-w 参数（非顶层 -w），且无 --version 选项。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from auto_pm.cli.spec import spec_group
from click.testing import CliRunner


class TestCLIGroup:
    def test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(spec_group, ["--help"])
        assert result.exit_code == 0
        assert "规范管理" in result.output

    @pytest.mark.skip(reason="auto_pm spec_group 无 --version 选项")
    def test_version(self) -> None:
        runner = CliRunner()
        result = runner.invoke(spec_group, ["--version"])
        assert result.exit_code == 0


class TestCheckCommand:
    def test_check_missing_workspace(self) -> None:
        runner = CliRunner()
        result = runner.invoke(spec_group, ["check"])
        assert result.exit_code != 0

    def test_check_with_workspace(self, populated_workspace: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(spec_group, ["check", "-w", str(populated_workspace)])
        assert result.exit_code in (0, 1, 2)

    def test_check_json_format(self, populated_workspace: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            spec_group,
            ["check", "-w", str(populated_workspace), "--format", "json"],
        )
        assert result.exit_code in (0, 1, 2)

    def test_check_severity_filter(self, populated_workspace: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            spec_group,
            ["check", "-w", str(populated_workspace), "--severity", "error"],
        )
        assert result.exit_code in (0, 1)

    def test_check_nonexistent_workspace(self) -> None:
        runner = CliRunner()
        result = runner.invoke(spec_group, ["check", "-w", "/nonexistent/path"])
        assert result.exit_code != 0

    def test_check_project_scope_requires_project_root(self, populated_workspace: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            spec_group,
            ["check", "-w", str(populated_workspace), "--scope", "project"],
        )
        assert result.exit_code != 0
        assert "--project-root" in result.output

    def test_check_project_scope_with_project_root(self, populated_workspace: Path) -> None:
        project_root = populated_workspace / "DJ-2026-000"
        project_root.mkdir(parents=True, exist_ok=True)
        (project_root / "PM_SESSION_DJ-2026-000.md").write_text(
            "# PM_SESSION_DJ-2026-000\n\n## 4. Artifacts Index\n- req:\n  - [missing](missing.md)\n",
            encoding="utf-8",
        )
        runner = CliRunner()
        result = runner.invoke(
            spec_group,
            [
                "check",
                "-w",
                str(populated_workspace),
                "--scope",
                "project",
                "--project-root",
                str(project_root),
            ],
        )
        assert result.exit_code == 2


class TestIndexCommand:
    def test_index_with_workspace(self, populated_workspace: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(spec_group, ["index", "-w", str(populated_workspace)])
        assert result.exit_code == 0

    def test_index_single_domain(self, populated_workspace: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            spec_group,
            ["index", "-w", str(populated_workspace), "--domain", "plc"],
        )
        assert result.exit_code == 0

    def test_index_missing_workspace(self) -> None:
        """缺失 -w 参数应报错退出"""
        runner = CliRunner()
        result = runner.invoke(spec_group, ["index"])
        assert result.exit_code != 0

    def test_index_nonexistent_workspace(self) -> None:
        """工作空间路径不存在应报错退出（SystemExit 1）"""
        runner = CliRunner()
        result = runner.invoke(spec_group, ["index", "-w", "/nonexistent/path/abc"])
        assert result.exit_code != 0

    def test_index_pm_domain_generates_file(self, populated_workspace: Path) -> None:
        """--domain pm 应生成 PM 索引文件并实际落盘"""
        runner = CliRunner()
        result = runner.invoke(
            spec_group,
            ["index", "-w", str(populated_workspace), "--domain", "pm"],
        )
        assert result.exit_code == 0
        pm_index = populated_workspace / "00_Obsidian_Base全局规范文件仓库" / "00_INDEX_全局规范索引.md"
        assert pm_index.exists()
        content = pm_index.read_text(encoding="utf-8")
        assert "全局规范索引" in content

    def test_index_python_domain_generates_file(self, populated_workspace: Path) -> None:
        """--domain python 应生成 Python 索引文件并实际落盘"""
        runner = CliRunner()
        result = runner.invoke(
            spec_group,
            ["index", "-w", str(populated_workspace), "--domain", "python"],
        )
        assert result.exit_code == 0
        python_readme = populated_workspace / "01_Project自动化项目管理" / "00_通用规范" / "README.md"
        assert python_readme.exists()

    def test_index_idempotent(self, populated_workspace: Path) -> None:
        """重复调用应生成相同内容（幂等性）"""
        runner = CliRunner()
        pm_index = populated_workspace / "00_Obsidian_Base全局规范文件仓库" / "00_INDEX_全局规范索引.md"

        runner.invoke(
            spec_group,
            ["index", "-w", str(populated_workspace), "--domain", "pm"],
        )
        content1 = pm_index.read_text(encoding="utf-8")

        runner.invoke(
            spec_group,
            ["index", "-w", str(populated_workspace), "--domain", "pm"],
        )
        content2 = pm_index.read_text(encoding="utf-8")

        assert content1 == content2

    def test_index_invalid_domain_rejected(self, populated_workspace: Path) -> None:
        """无效域应被 click Choice 拦截（exit_code != 0）"""
        runner = CliRunner()
        result = runner.invoke(
            spec_group,
            ["index", "-w", str(populated_workspace), "--domain", "invalid"],
        )
        assert result.exit_code != 0


class TestFrontmatterCommand:
    def test_frontmatter_dry_run(self, populated_workspace: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(spec_group, ["frontmatter", "-w", str(populated_workspace)])
        assert result.exit_code == 0

    def test_frontmatter_missing_workspace(self) -> None:
        runner = CliRunner()
        result = runner.invoke(spec_group, ["frontmatter"])
        assert result.exit_code != 0

    def test_frontmatter_nonexistent_workspace(self) -> None:
        """工作空间路径不存在应报错退出"""
        runner = CliRunner()
        result = runner.invoke(spec_group, ["frontmatter", "-w", "/nonexistent/path/abc"])
        assert result.exit_code != 0

    def test_frontmatter_with_spec_id(self, populated_workspace: Path) -> None:
        """--spec-id 应只处理指定规范"""
        runner = CliRunner()
        result = runner.invoke(
            spec_group,
            ["frontmatter", "-w", str(populated_workspace), "--spec-id", "PM-2026-001"],
        )
        assert result.exit_code == 0

    def test_frontmatter_nonexistent_spec_id(self, populated_workspace: Path) -> None:
        """--spec-id 指定不存在的规范应正常退出(扫描到 0 个)"""
        runner = CliRunner()
        result = runner.invoke(
            spec_group,
            ["frontmatter", "-w", str(populated_workspace), "--spec-id", "NONEXISTENT-000"],
        )
        assert result.exit_code == 0

    def test_frontmatter_apply_with_fix(self, populated_workspace: Path) -> None:
        """--fix 应实际写入 frontmatter 到无 frontmatter 的文件"""
        # 重写 PM-2026-001 文件,去掉 frontmatter
        pm_file = populated_workspace / "00_Obsidian_Base全局规范文件仓库" / "01_项目管理域" / "PM-2026-001_项目管理规范_DEV.md"
        pm_file.write_text("# 项目管理规范\n\n无 frontmatter 内容\n", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(
            spec_group,
            ["frontmatter", "-w", str(populated_workspace), "--spec-id", "PM-2026-001", "--fix"],
        )
        assert result.exit_code == 0
        # 验证文件已写入 frontmatter
        new_content = pm_file.read_text(encoding="utf-8")
        assert new_content.startswith("---")
        assert "spec_id: PM-2026-001" in new_content


class TestReportCommand:
    def test_report_with_workspace(self, populated_workspace: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(spec_group, ["report", "-w", str(populated_workspace)])
        assert result.exit_code == 0

    def test_report_json_format(self, populated_workspace: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            spec_group,
            ["report", "-w", str(populated_workspace), "--format", "json"],
        )
        assert result.exit_code == 0

    def test_report_missing_workspace(self) -> None:
        """缺失 -w 参数应报错退出"""
        runner = CliRunner()
        result = runner.invoke(spec_group, ["report"])
        assert result.exit_code != 0

    def test_report_nonexistent_workspace(self) -> None:
        """工作空间路径不存在应报错退出"""
        runner = CliRunner()
        result = runner.invoke(spec_group, ["report", "-w", "/nonexistent/path/abc"])
        assert result.exit_code != 0

    def test_report_custom_output(self, populated_workspace: Path, tmp_path: Path) -> None:
        """-o 应将报告输出到自定义路径"""
        custom_path = tmp_path / "custom_report.md"
        runner = CliRunner()
        result = runner.invoke(
            spec_group,
            ["report", "-w", str(populated_workspace), "-o", str(custom_path)],
        )
        assert result.exit_code == 0
        assert custom_path.exists()

    def test_report_markdown_default_format(self, populated_workspace: Path) -> None:
        """默认格式应为 markdown,生成 .md 文件"""
        runner = CliRunner()
        result = runner.invoke(spec_group, ["report", "-w", str(populated_workspace)])
        assert result.exit_code == 0
        # 默认输出路径应为 规范元数据汇总报告.md
        default_path = populated_workspace / "00_Obsidian_Base全局规范文件仓库" / "规范元数据汇总报告.md"
        assert default_path.exists()
        content = default_path.read_text(encoding="utf-8")
        assert "规范元数据汇总报告" in content


class TestConfigQuietCommand:
    """T09: --config/--quiet CLI 选项测试"""

    @pytest.fixture
    def config_file(self, populated_workspace: Path) -> Path:
        """创建工作空间配置文件 YAML(内容与默认配置相同,验证加载机制)"""
        config_path = populated_workspace / "spec_config.yaml"
        config_path.write_text(
            "workspace: .\n"
            "spec_dirs:\n"
            "  - '00_Obsidian_Base全局规范文件仓库/01_项目管理域'\n"
            "  - '0100_PLC自动化/00_通用规范'\n"
            "  - '01_Project自动化项目管理/00_通用规范'\n"
            "archive_dir: '00_Obsidian_Base全局规范文件仓库/_archive'\n"
            "registry_path: '00_Obsidian_Base全局规范文件仓库/spec_registry.json'\n"
            "output_paths:\n"
            "  pm_index: '01_Project自动化项目管理/00_通用规范/README.md'\n"
            "  plc_readme: '0100_PLC自动化/00_通用规范/README.md'\n"
            "  python_readme: '01_Project自动化项目管理/00_通用规范/README.md'\n"
            "  report: '00_Obsidian_Base全局规范文件仓库/health_report.md'\n",
            encoding="utf-8",
        )
        return config_path

    def test_check_with_config_file(self, populated_workspace: Path, config_file: Path) -> None:
        """--config 应加载自定义配置文件并正常执行 check"""
        runner = CliRunner()
        result = runner.invoke(
            spec_group,
            ["check", "-w", str(populated_workspace), "--config", str(config_file)],
        )
        assert result.exit_code == 0

    def test_check_quiet_no_errors_silent(self, populated_workspace: Path) -> None:
        """--quiet 在 check 无 ERROR 时应无输出(或仅空输出)"""
        runner = CliRunner()
        # populated_workspace 的规范都是正常的,check 应无 ERROR
        result = runner.invoke(
            spec_group,
            ["check", "-w", str(populated_workspace), "--quiet"],
        )
        # exit_code 0 表示无 ERROR
        assert result.exit_code == 0
        # quiet 模式下不应输出汇总信息
        assert "汇总" not in result.output
        assert "ERROR" not in result.output

    def test_check_quiet_with_errors_output(self, workspace: Path) -> None:
        """--quiet 在 check 有 ERROR 时应只输出 ERROR 信息"""
        # workspace 无注册表,会触发 SHC-000 ERROR
        runner = CliRunner()
        result = runner.invoke(
            spec_group,
            ["check", "-w", str(workspace), "--quiet"],
        )
        # exit_code != 0 表示有问题(ERROR 或 WARNING)
        assert result.exit_code != 0
        # quiet 模式下应输出 ERROR(SHC-000)
        assert "ERROR" in result.output or "SHC-000" in result.output

    def test_index_quiet_silent_on_success(self, populated_workspace: Path) -> None:
        """--quiet 在 index 成功时应无'已生成'输出"""
        runner = CliRunner()
        result = runner.invoke(
            spec_group,
            ["index", "-w", str(populated_workspace), "--domain", "pm", "--quiet"],
        )
        assert result.exit_code == 0
        # quiet 模式下不应输出成功信息
        assert "已生成" not in result.output

    def test_index_with_config_file(self, populated_workspace: Path, config_file: Path) -> None:
        """--config 应加载自定义配置文件并正常执行 index"""
        runner = CliRunner()
        result = runner.invoke(
            spec_group,
            ["index", "-w", str(populated_workspace), "--domain", "pm", "--config", str(config_file)],
        )
        assert result.exit_code == 0
        pm_index = populated_workspace / "00_Obsidian_Base全局规范文件仓库" / "00_INDEX_全局规范索引.md"
        assert pm_index.exists()

    def test_frontmatter_quiet_silent(self, populated_workspace: Path) -> None:
        """--quiet 在 frontmatter 无 error 时应无输出"""
        runner = CliRunner()
        result = runner.invoke(
            spec_group,
            ["frontmatter", "-w", str(populated_workspace), "--quiet"],
        )
        assert result.exit_code == 0
        # quiet 模式下不应输出扫描结果
        assert "扫描到" not in result.output
        assert "ERROR" not in result.output

    def test_report_quiet_silent_on_success(self, populated_workspace: Path) -> None:
        """--quiet 在 report 成功时应无'报告已生成'输出"""
        runner = CliRunner()
        result = runner.invoke(
            spec_group,
            ["report", "-w", str(populated_workspace), "--quiet"],
        )
        assert result.exit_code == 0
        # quiet 模式下不应输出成功信息
        assert "报告已生成" not in result.output

    def test_report_with_config_file(self, populated_workspace: Path, config_file: Path) -> None:
        """--config 应加载自定义配置文件并正常执行 report"""
        runner = CliRunner()
        result = runner.invoke(
            spec_group,
            ["report", "-w", str(populated_workspace), "--config", str(config_file)],
        )
        assert result.exit_code == 0

    def test_config_nonexistent_file(self, populated_workspace: Path) -> None:
        """--config 文件不存在时应报错退出(SystemExit 1)"""
        runner = CliRunner()
        result = runner.invoke(
            spec_group,
            ["check", "-w", str(populated_workspace), "--config", "/nonexistent/config.yaml"],
        )
        assert result.exit_code != 0
        assert "配置文件不存在" in result.output

    def test_check_quiet_json_format(self, populated_workspace: Path) -> None:
        """--quiet + --format json 组合应输出 ERROR 的 JSON 数组"""
        runner = CliRunner()
        result = runner.invoke(
            spec_group,
            ["check", "-w", str(populated_workspace), "--quiet", "--format", "json"],
        )
        assert result.exit_code == 0
        # quiet + json 模式下,输出应为 JSON(可能为空数组)
        import json
        data = json.loads(result.output)
        assert "check_results" in data


# ── P2-7: spec check --verbose 详细 diff 输出测试 ──────────


class TestVerboseOption:
    """P2-7: spec check --verbose/-v 详细 diff 输出测试"""

    def test_spec_check_verbose_option_exists(self) -> None:
        """spec check --help 应包含 --verbose 和 -v 选项"""
        runner = CliRunner()
        result = runner.invoke(spec_group, ["check", "--help"])
        assert result.exit_code == 0
        assert "--verbose" in result.output
        assert "-v" in result.output

    def test_spec_check_verbose_flag_runs(self, populated_workspace: Path) -> None:
        """--verbose 标志应正常执行（不崩溃）"""
        runner = CliRunner()
        result = runner.invoke(
            spec_group,
            ["check", "-w", str(populated_workspace), "--verbose"],
        )
        assert result.exit_code in (0, 1, 2)

    def test_spec_check_json_summary_with_verbose(self, workspace: Path) -> None:
        """--verbose --format json 输出应含 summary 字段（total/error/warning/info）"""
        runner = CliRunner()
        result = runner.invoke(
            spec_group,
            ["check", "-w", str(workspace), "--format", "json", "--verbose"],
        )
        # workspace 无注册表，会触发 SHC-000 ERROR，exit_code != 0
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert "summary" in data, "verbose 模式 JSON 应含 summary 字段"
        summary = data["summary"]
        assert "total" in summary
        assert "error" in summary
        assert "warning" in summary
        assert "info" in summary
        assert summary["total"] >= 1, "应至少有 1 个检查结果"

    def test_spec_check_json_without_verbose_no_summary(
        self, workspace: Path
    ) -> None:
        """不带 --verbose 的 JSON 模式不应含 summary 字段"""
        runner = CliRunner()
        result = runner.invoke(
            spec_group,
            ["check", "-w", str(workspace), "--format", "json"],
        )
        data = json.loads(result.output)
        assert "summary" not in data, "非 verbose 模式 JSON 不应含 summary 字段"

    def test_spec_check_short_v_alias(self, workspace: Path) -> None:
        """-v 是 --verbose 的别名（JSON 输出应含 summary）"""
        runner = CliRunner()
        result = runner.invoke(
            spec_group,
            ["check", "-w", str(workspace), "--format", "json", "-v"],
        )
        data = json.loads(result.output)
        assert "summary" in data, "-v 别名应与 --verbose 等价，含 summary 字段"
