"""doc inject CLI 命令集成测试（V0.4.1 Step 2）

覆盖迭代计划 V041-S2-05 五个场景：
1. dry-run 预览（不写入文件）
2. 实际写入（文件被修改，marker 存在）
3. 创建后注入（先 inject 再 refresh，验证一致性）
4. 锚点缺失（CLI 输出 issue）
5. JSON 输出（--json 返回正确结构）
"""

from __future__ import annotations

import json
from pathlib import Path

from auto_pm.cli.__main__ import cli
from click.testing import CliRunner


def _setup_legacy_doc_workspace(tmp_path: Path) -> Path:
    """创建历史 PLC 项目工作空间（无 AUTO_PM 标记，仅锚点标题 + 手工内容）

    与 _setup_doc_refresh_workspace 区别：
    - refresh fixture 预埋了 marker block，用于测试 refresh 行为
    - inject fixture 不预埋 marker，用于测试 inject 注入行为
    """
    project_dir = tmp_path / "DJ-2026-051_历史文档项目"
    (project_dir / "02_PLC程序" / "工程资产").mkdir(parents=True)
    (project_dir / "02_PLC程序" / "程序文档").mkdir(parents=True)
    (project_dir / ".copier-answers.yml").write_text(
        "\n".join(
            [
                "project_id: DJ-2026-051",
                "project_name: 历史文档项目",
                "stack: plc",
                "project_type: single_machine",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (project_dir / "02_PLC程序" / "工程资产" / "io_points.csv").write_text(
        "\n".join(
            [
                "station,signal_type,address,tag,signal_name,device,comment",
                "common,DI,I0.0,ESTOP_OK,急停回路正常,操作台,TRUE=安全链路闭合",
                "conveyor,DO,Q0.0,CONVEYOR_RUN,输送带运行,变频器,TRUE=正转运行",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (project_dir / "02_PLC程序" / "工程资产" / "program_blocks.yml").write_text(
        "blocks:\n"
        '  - name: "OB1"\n'
        '    type: "OB"\n'
        '    path: "02_PLC程序/PLC_ST/OB1/OB1.scl"\n'
        '    responsibility: "主循环"\n',
        encoding="utf-8",
    )
    (project_dir / "02_PLC程序" / "工程资产" / "communications.yml").write_text(
        "channels:\n"
        '  - name: "HMI"\n'
        '    protocol: "ethernet"\n'
        '    role: "人机界面"\n'
        '    endpoint: "Siemens S7-1200"\n'
        '    notes: "补齐映射"\n',
        encoding="utf-8",
    )
    # 历史文档：无 marker，仅锚点标题 + 手工内容
    (project_dir / "02_PLC程序" / "程序文档" / "016_DJ-2026-051_PLC程序设计总文档_PLC.md").write_text(
        "\n".join(
            [
                "# PLC程序设计总文档",
                "",
                "## 4. 软件架构",
                "",
                "### 4.1 组件清单与职责",
                "",
                "手工组件清单内容",
                "",
                "## 8. 关联文档索引",
                "",
                "手工关联文档索引",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (project_dir / "02_PLC程序" / "程序文档" / "015_DJ-2026-051_IO分配表_IO.md").write_text(
        "\n".join(
            [
                "# IO分配表",
                "",
                "## 2. IO 总览",
                "",
                "手工IO总览内容",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return tmp_path


def _program_doc_path(workspace: Path) -> Path:
    return (
        workspace
        / "DJ-2026-051_历史文档项目"
        / "02_PLC程序"
        / "程序文档"
        / "016_DJ-2026-051_PLC程序设计总文档_PLC.md"
    )


def _io_doc_path(workspace: Path) -> Path:
    return (
        workspace
        / "DJ-2026-051_历史文档项目"
        / "02_PLC程序"
        / "程序文档"
        / "015_DJ-2026-051_IO分配表_IO.md"
    )


class TestDocInject:
    """doc inject 命令集成测试"""

    def test_doc_inject_dry_run_does_not_modify(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """场景1：dry-run 预览，不写入文档"""
        workspace = _setup_legacy_doc_workspace(tmp_path)
        program_doc = _program_doc_path(workspace)
        io_doc = _io_doc_path(workspace)

        result = cli_runner.invoke(
            cli,
            ["-w", str(workspace), "doc", "inject", "DJ-2026-051", "--dry-run"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert "[DRY-RUN]" in result.output
        assert "文档自动区标记注入完成" in result.output
        assert "plc-program-components" in result.output
        assert "plc-asset-index" in result.output
        assert "plc-io-overview" in result.output

        # 文档实际未被修改（无 marker）
        program_content = program_doc.read_text(encoding="utf-8")
        io_content = io_doc.read_text(encoding="utf-8")
        assert "AUTO_PM:BEGIN" not in program_content
        assert "AUTO_PM:BEGIN" not in io_content
        # 原手工内容保留
        assert "手工组件清单内容" in program_content
        assert "手工IO总览内容" in io_content

    def test_doc_inject_writes_markers(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """场景2：实际写入，文件被修改，marker 存在"""
        workspace = _setup_legacy_doc_workspace(tmp_path)
        program_doc = _program_doc_path(workspace)
        io_doc = _io_doc_path(workspace)

        result = cli_runner.invoke(
            cli,
            ["-w", str(workspace), "doc", "inject", "DJ-2026-051"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert "文档自动区标记注入完成" in result.output
        assert "2 个文档" in result.output

        program_content = program_doc.read_text(encoding="utf-8")
        io_content = io_doc.read_text(encoding="utf-8")

        # 3 个 marker 全部注入
        assert "<!-- AUTO_PM:BEGIN plc-program-components -->" in program_content
        assert "<!-- AUTO_PM:END plc-program-components -->" in program_content
        assert "<!-- AUTO_PM:BEGIN plc-asset-index -->" in program_content
        assert "<!-- AUTO_PM:END plc-asset-index -->" in program_content
        assert "<!-- AUTO_PM:BEGIN plc-io-overview -->" in io_content
        assert "<!-- AUTO_PM:END plc-io-overview -->" in io_content

        # 资产数据已填充
        assert "OB1" in program_content
        assert "io_points.csv" in program_content
        assert "### 2.1 自动区刷新摘要" in io_content

        # 原手工内容保留在 END 标记之后
        assert "手工组件清单内容" in program_content
        assert "手工关联文档索引" in program_content
        assert "手工IO总览内容" in io_content

        # 验证顺序：原内容在 END 标记之后
        end_pos = program_content.find("<!-- AUTO_PM:END plc-program-components -->")
        original_pos = program_content.find("手工组件清单内容")
        assert end_pos >= 0
        assert original_pos > end_pos, "原手工内容应在 END 标记之后"

    def test_doc_inject_then_refresh_consistency(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """场景3：先 inject 注入 marker，再 refresh 刷新，验证一致性

        场景链路：
        1. 历史文档无 marker → inject 注入 3 个 marker block
        2. 文档已有 marker → refresh 只替换 BEGIN/END 之间内容
        3. 第二次 refresh 应无变更（已与资产数据一致）
        """
        workspace = _setup_legacy_doc_workspace(tmp_path)
        program_doc = _program_doc_path(workspace)

        # Step 1: inject 注入 marker
        inject_result = cli_runner.invoke(
            cli,
            ["-w", str(workspace), "doc", "inject", "DJ-2026-051"],
            catch_exceptions=False,
        )
        assert inject_result.exit_code == 0
        assert "文档自动区标记注入完成" in inject_result.output

        program_content_after_inject = program_doc.read_text(encoding="utf-8")
        assert "AUTO_PM:BEGIN" in program_content_after_inject

        # Step 2: refresh 刷新（应替换 BEGIN/END 之间内容）
        refresh_result = cli_runner.invoke(
            cli,
            ["-w", str(workspace), "doc", "refresh", "DJ-2026-051"],
            catch_exceptions=False,
        )
        assert refresh_result.exit_code == 0
        assert "文档自动区处理完成" in refresh_result.output

        program_content_after_refresh = program_doc.read_text(encoding="utf-8")
        # marker 仍存在
        assert "<!-- AUTO_PM:BEGIN plc-program-components -->" in program_content_after_refresh
        assert "<!-- AUTO_PM:END plc-program-components -->" in program_content_after_refresh
        # 资产数据仍在
        assert "OB1" in program_content_after_refresh
        # 原手工内容仍保留在 END 之后
        assert "手工组件清单内容" in program_content_after_refresh

        # Step 3: 再次 refresh 应无变更（已与资产数据一致）
        second_refresh = cli_runner.invoke(
            cli,
            ["-w", str(workspace), "doc", "refresh", "DJ-2026-051"],
            catch_exceptions=False,
        )
        assert second_refresh.exit_code == 0
        # 第二次刷新后内容应与第一次刷新后一致（idempotent）
        program_content_after_second_refresh = program_doc.read_text(encoding="utf-8")
        assert program_content_after_refresh == program_content_after_second_refresh

    def test_doc_inject_missing_anchor_reports_issue(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """场景4：锚点缺失时 CLI 输出 issue，不强行注入"""
        workspace = _setup_legacy_doc_workspace(tmp_path)
        program_doc = _program_doc_path(workspace)

        # 移除 016 文档的 "### 4.1 组件清单与职责" 锚点
        program_doc.write_text(
            "\n".join(
                [
                    "# PLC程序设计总文档",
                    "",
                    "## 4. 软件架构",
                    "",
                    "## 8. 关联文档索引",
                    "",
                    "手工关联文档索引",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        result = cli_runner.invoke(
            cli,
            ["-w", str(workspace), "doc", "inject", "DJ-2026-051"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        # 锚点缺失 issue 输出
        assert "plc-program-components" in result.output
        assert "锚点缺失" in result.output

        program_content = program_doc.read_text(encoding="utf-8")
        # 缺失锚点的 marker 不应被注入
        assert "AUTO_PM:BEGIN plc-program-components" not in program_content
        # 存在锚点的 marker 仍被注入
        assert "AUTO_PM:BEGIN plc-asset-index -->" in program_content

    def test_doc_inject_json_output(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """场景5：--json 返回正确结构"""
        workspace = _setup_legacy_doc_workspace(tmp_path)

        result = cli_runner.invoke(
            cli,
            ["-w", str(workspace), "doc", "inject", "DJ-2026-051", "--dry-run", "--json"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["project_id"] == "DJ-2026-051"
        assert payload["dry_run"] is True
        assert payload["updated"] is False  # dry-run 不写入
        assert isinstance(payload["injected_files"], list)
        assert len(payload["injected_files"]) == 2

        # 验证每个文件的结构
        for item in payload["injected_files"]:
            assert "file_path" in item
            assert "injected_keys" in item
            assert "skipped_keys" in item
            assert "missing_anchors" in item
            assert "changed" in item
            assert isinstance(item["injected_keys"], list)
            assert isinstance(item["skipped_keys"], list)
            assert isinstance(item["missing_anchors"], list)
            assert isinstance(item["changed"], bool)

        # 验证 PLC.md 文档注入了 plc-program-components + plc-asset-index
        program_item = next(
            item for item in payload["injected_files"] if item["file_path"].endswith("PLC.md")
        )
        assert "plc-program-components" in program_item["injected_keys"]
        assert "plc-asset-index" in program_item["injected_keys"]
        assert program_item["changed"] is True  # dry-run 也报 changed=True（预览有变更）

        # 验证 IO.md 文档注入了 plc-io-overview
        io_item = next(
            item for item in payload["injected_files"] if item["file_path"].endswith("IO.md")
        )
        assert "plc-io-overview" in io_item["injected_keys"]
        assert io_item["changed"] is True

    def test_doc_inject_project_not_found(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """边界：项目不存在时报错"""
        workspace = _setup_legacy_doc_workspace(tmp_path)

        result = cli_runner.invoke(
            cli,
            ["-w", str(workspace), "doc", "inject", "NOT-EXIST"],
        )

        assert result.exit_code == 1
        assert "项目不存在" in result.output

    def test_doc_inject_skip_existing_marker(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """边界：已存在 marker 时跳过并报告"""
        workspace = _setup_legacy_doc_workspace(tmp_path)
        program_doc = _program_doc_path(workspace)

        # 预埋 plc-program-components marker
        program_doc.write_text(
            "\n".join(
                [
                    "# PLC程序设计总文档",
                    "",
                    "## 4. 软件架构",
                    "",
                    "### 4.1 组件清单与职责",
                    "",
                    "<!-- AUTO_PM:BEGIN plc-program-components -->",
                    "已存在的组件内容",
                    "<!-- AUTO_PM:END plc-program-components -->",
                    "",
                    "## 8. 关联文档索引",
                    "",
                    "手工关联文档索引",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        result = cli_runner.invoke(
            cli,
            ["-w", str(workspace), "doc", "inject", "DJ-2026-051"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        # plc-program-components 已存在 → 跳过
        assert "已存在跳过" in result.output
        assert "plc-program-components" in result.output

        program_content = program_doc.read_text(encoding="utf-8")
        # 已存在的内容保留（不替换）
        assert "已存在的组件内容" in program_content
        # plc-asset-index 无 marker → 注入
        assert "AUTO_PM:BEGIN plc-asset-index" in program_content


class TestDocIssueBracketPreservation:
    """回归测试（V0.4.2 Week3 第二样本复核发现）：

    rich console 默认解析 markup，会把 issue 文本中的 `[block_key]`
    当作未知 markup 标签吞噬，导致用户看不到具体的 block_key 信息。

    场景来源：DJ-2026-099 真实样本复核时 `doc refresh --dry-run` 输出
    "文档缺少自动区标记: 016_PLC程序设计总文档_PLC.md"（[plc-program-components] 被吞噬）。

    修复后应保留 `[block_key]` 字面文本，便于用户定位缺失的具体标记。
    """

    def test_doc_refresh_issue_preserves_brackets_around_block_key(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """refresh issue 行应保留 [block_key] 字面文本（不被 rich markup 吞噬）"""
        workspace = _setup_legacy_doc_workspace(tmp_path)

        # 历史文档无 marker → refresh 应输出 "文档缺少自动区标记: ... [block_key]"
        result = cli_runner.invoke(
            cli,
            ["-w", str(workspace), "doc", "refresh", "DJ-2026-051", "--dry-run"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        # 关键断言：issue 行必须保留 [plc-program-components] 字面文本
        assert "[plc-program-components]" in result.output, (
            "issue 行的 [plc-program-components] 被 rich markup 吞噬，"
            "应使用 rich.markup.escape 或 markup=False 保留字面方括号"
        )
        assert "[plc-asset-index]" in result.output
        assert "[plc-io-overview]" in result.output

    def test_doc_inject_issue_preserves_brackets_around_block_key(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """inject 锚点缺失 issue 行应保留 [block_key] 字面文本"""
        workspace = _setup_legacy_doc_workspace(tmp_path)
        program_doc = _program_doc_path(workspace)

        # 移除 016 文档的所有锚点（4.1 和 8.），触发 inject 锚点缺失 issue
        program_doc.write_text(
            "\n".join(
                [
                    "# PLC程序设计总文档",
                    "",
                    "## 4. 软件架构",
                    "",
                    "（无组件清单锚点）",
                    "",
                    "（无关联文档索引锚点）",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        result = cli_runner.invoke(
            cli,
            ["-w", str(workspace), "doc", "inject", "DJ-2026-051"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        # 关键断言：issue 行必须保留 [plc-program-components] 和 [plc-asset-index] 字面文本
        assert "[plc-program-components]" in result.output, (
            "inject issue 行的 [plc-program-components] 被 rich markup 吞噬"
        )
        assert "[plc-asset-index]" in result.output
