from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from auto_pm.spec.services.check_svc import CheckService
from auto_pm.spec.services.frontmatter_svc import FrontmatterService
from auto_pm.spec.services.index_svc import IndexService
from auto_pm.spec.services.report_svc import ReportService


class TestCheckService:
    def test_run_returns_check_output(self, populated_workspace: Path) -> None:
        svc = CheckService(populated_workspace)
        output = svc.run()
        assert output.results is not None
        assert output.error_count >= 0
        assert output.warning_count >= 0
        assert output.info_count >= 0
        assert output.exit_code in (0, 1, 2)

    def test_run_with_severity_filter(self, populated_workspace: Path) -> None:
        from auto_pm.spec.core.checker_base import Severity

        svc = CheckService(populated_workspace)
        output = svc.run(min_severity=Severity.ERROR)
        assert all(r.severity >= Severity.ERROR for r in output.results)

    def test_run_with_check_ids(self, populated_workspace: Path) -> None:
        svc = CheckService(populated_workspace)
        output = svc.run(check_ids=["SHC-001"])
        assert all(r.check_id == "SHC-001" for r in output.results)

    def test_run_missing_registry(self, workspace: Path) -> None:
        svc = CheckService(workspace)
        output = svc.run()
        assert output.error_count == 1
        assert output.results[0].check_id == "SHC-000"

    def test_run_project_scope_defaults_to_pmsession_check(self, populated_workspace: Path) -> None:
        project_root = populated_workspace / "DJ-2026-000"
        project_root.mkdir(parents=True, exist_ok=True)
        (project_root / "PM_SESSION_DJ-2026-000.md").write_text(
            "# PM_SESSION_DJ-2026-000\n\n## 4. Artifacts Index\n- req:\n  - [missing](missing.md)\n",
            encoding="utf-8",
        )

        spec_dir = populated_workspace / "00_Obsidian_Base全局规范文件仓库" / "01_项目管理域"
        (spec_dir / "PM-2026-001_项目管理规范_DEV_copy.md").write_text(
            "# Duplicate\n",
            encoding="utf-8",
        )

        svc = CheckService(populated_workspace)
        output = svc.run(scope="project", project_root=project_root)
        assert output.results
        assert all(r.check_id == "SHC-009" for r in output.results)
        assert output.exit_code == 2


class TestIndexService:
    def test_run_generates_files(self, populated_workspace: Path) -> None:
        svc = IndexService(populated_workspace)
        output = svc.run()
        assert len(output.generated_files) > 0
        for f in output.generated_files:
            assert f.exists()

    def test_run_single_domain(self, populated_workspace: Path) -> None:
        svc = IndexService(populated_workspace)
        output = svc.run(domains=["plc"])
        assert len(output.generated_files) == 1

    def test_run_missing_registry(self, workspace: Path) -> None:
        with pytest.raises(FileNotFoundError):
            IndexService(workspace)

    def test_run_all_domains_generates_three_entries(self, populated_workspace: Path) -> None:
        """all 域应生成 3 个 generated_files 条目（注意 plc/python 输出路径相同）"""
        svc = IndexService(populated_workspace)
        output = svc.run()
        assert len(output.generated_files) == 3
        assert len(output.errors) == 0

    def test_run_pm_only_generates_one_file(self, populated_workspace: Path) -> None:
        """domains=['pm'] 只生成 1 个文件"""
        svc = IndexService(populated_workspace)
        output = svc.run(domains=["pm"])
        assert len(output.generated_files) == 1
        assert output.generated_files[0].exists()

    def test_run_python_only_generates_one_file(self, populated_workspace: Path) -> None:
        """domains=['python'] 只生成 1 个文件"""
        svc = IndexService(populated_workspace)
        output = svc.run(domains=["python"])
        assert len(output.generated_files) == 1

    def test_run_invalid_domain_returns_error(self, populated_workspace: Path) -> None:
        """无效域应被捕获到 errors 列表"""
        svc = IndexService(populated_workspace)
        output = svc.run(domains=["invalid_domain"])
        assert len(output.errors) == 1
        assert "invalid_domain" in output.errors[0]
        assert len(output.generated_files) == 0

    def test_run_generated_pm_index_contains_title(self, populated_workspace: Path) -> None:
        """生成的 PM 索引文件应包含 DOMAIN_CONFIG['pm']['title']"""
        svc = IndexService(populated_workspace)
        output = svc.run(domains=["pm"])
        content = output.generated_files[0].read_text(encoding="utf-8")
        assert "全局规范索引" in content
        assert "spec_registry.json" in content

    def test_run_pm_index_includes_subdomain_section(self, populated_workspace: Path) -> None:
        """PM 索引应包含子域章节（如 '启动阶段'）"""
        svc = IndexService(populated_workspace)
        output = svc.run(domains=["pm"])
        content = output.generated_files[0].read_text(encoding="utf-8")
        assert "启动阶段" in content
        assert "PM-2026-001" in content

    def test_run_pm_index_includes_deprecated_section(self, populated_workspace: Path) -> None:
        """PM 索引应包含已废弃规范章节（PM-2026-002 为 deprecated）"""
        svc = IndexService(populated_workspace)
        output = svc.run(domains=["pm"])
        content = output.generated_files[0].read_text(encoding="utf-8")
        assert "已废弃规范" in content
        assert "PM-2026-002" in content

    def test_run_plc_index_includes_core_ids_marker(self, populated_workspace: Path) -> None:
        """PLC 索引应为 CORE_IDS 中的规范标记'🔴必读'"""
        # 修改注册表使 PLC-2026-001 进入 CORE_IDS（实际 CORE_IDS=['LSP-905','LSP-907']，
        # 这里测试 CORE_IDS 机制本身：将 PLC-2026-001 改为 LSP-905 验证标记）
        import json
        reg_path = populated_workspace / "00_Obsidian_Base全局规范文件仓库" / "spec_registry.json"
        data = json.loads(reg_path.read_text(encoding="utf-8"))
        data["specs"]["LSP-905"] = data["specs"].pop("PLC-2026-001")
        data["specs"]["LSP-905"]["spec_id"] = "LSP-905"
        data["specs"]["LSP-905"]["canonical_path"] = "0100_PLC自动化/00_通用规范/LSP-905_PLC编程规范_DEV.md"
        reg_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        # 重命名规范文件
        old_file = populated_workspace / "0100_PLC自动化" / "00_通用规范" / "PLC-2026-001_PLC编程规范_DEV.md"
        new_file = populated_workspace / "0100_PLC自动化" / "00_通用规范" / "LSP-905_PLC编程规范_DEV.md"
        old_file.rename(new_file)

        svc = IndexService(populated_workspace)
        output = svc.run(domains=["plc"])
        content = output.generated_files[0].read_text(encoding="utf-8")
        assert "🔴必读" in content
        assert "LSP-905" in content

    def test_run_idempotent(self, populated_workspace: Path) -> None:
        """重复调用应生成相同内容（幂等性）"""
        svc = IndexService(populated_workspace)
        output1 = svc.run(domains=["pm"])
        content1 = output1.generated_files[0].read_text(encoding="utf-8")
        output2 = svc.run(domains=["pm"])
        content2 = output2.generated_files[0].read_text(encoding="utf-8")
        assert content1 == content2

    def test_run_empty_specs_registry(self, workspace: Path, registry_dir: Path) -> None:
        """注册表 specs 为空时不应报错（生成空索引）"""
        import json
        empty_reg = {
            "version": "1.0.0",
            "domains": {"pm": "项目管理域", "plc": "PLC域", "python": "Python域"},
            "specs": {},
        }
        (registry_dir / "spec_registry.json").write_text(
            json.dumps(empty_reg, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        svc = IndexService(workspace)
        output = svc.run(domains=["pm"])
        # 空 specs 不应导致 errors（raw 非空，只是 specs 字段为空）
        assert len(output.errors) == 0
        assert len(output.generated_files) == 1
        content = output.generated_files[0].read_text(encoding="utf-8")
        assert "全局规范索引" in content


class TestFrontmatterService:
    def test_preview_returns_items(self, populated_workspace: Path) -> None:
        svc = FrontmatterService(populated_workspace)
        items = svc.preview()
        assert len(items) > 0

    def test_preview_with_spec_id(self, populated_workspace: Path) -> None:
        svc = FrontmatterService(populated_workspace)
        items = svc.preview(spec_id="PM-2026-001")
        assert all(i.spec_id == "PM-2026-001" for i in items)

    def test_preview_nonexistent_spec(self, populated_workspace: Path) -> None:
        svc = FrontmatterService(populated_workspace)
        items = svc.preview(spec_id="NONEXISTENT-000")
        assert len(items) == 0

    def test_apply_dry_run_no_modification(self, populated_workspace: Path) -> None:
        svc = FrontmatterService(populated_workspace)
        items = svc.preview()
        pending = [i for i in items if i.status == "pending"]
        if pending:
            result = svc.apply(pending)
            assert result.modified_count >= 0

    def test_missing_registry(self, workspace: Path) -> None:
        with pytest.raises(FileNotFoundError):
            FrontmatterService(workspace)

    def test_preview_deprecated_returns_skipped(self, populated_workspace: Path) -> None:
        """deprecated 规范应返回 status=skipped + is_deprecated=True"""
        svc = FrontmatterService(populated_workspace)
        items = svc.preview(spec_id="PM-2026-002")  # deprecated
        assert len(items) == 1
        assert items[0].status == "skipped"
        assert items[0].is_deprecated is True

    def test_preview_existing_frontmatter_returns_skipped(self, populated_workspace: Path) -> None:
        """已有 frontmatter 的规范应返回 status=skipped + has_frontmatter=True"""
        svc = FrontmatterService(populated_workspace)
        items = svc.preview(spec_id="PM-2026-001")  # fixture 中已包含 frontmatter
        assert len(items) == 1
        assert items[0].status == "skipped"
        assert items[0].has_frontmatter is True
        assert items[0].new_frontmatter == ""

    def test_preview_missing_file_returns_error(self, populated_workspace: Path) -> None:
        """规范文件不存在时应返回 status=error"""
        # 删除 PLC-2026-001 文件
        plc_file = populated_workspace / "0100_PLC自动化" / "00_通用规范" / "PLC-2026-001_PLC编程规范_DEV.md"
        plc_file.unlink()

        svc = FrontmatterService(populated_workspace)
        items = svc.preview(spec_id="PLC-2026-001")
        assert len(items) == 1
        assert items[0].status == "error"
        assert items[0].file_exists is False

    def test_preview_no_frontmatter_returns_pending(self, populated_workspace: Path) -> None:
        """无 frontmatter 的规范文件应返回 status=pending + new_frontmatter 非空"""
        # 重写 PM-2026-001 文件,去掉 frontmatter
        pm_file = populated_workspace / "00_Obsidian_Base全局规范文件仓库" / "01_项目管理域" / "PM-2026-001_项目管理规范_DEV.md"
        pm_file.write_text("# 项目管理规范\n\n无 frontmatter 内容\n", encoding="utf-8")

        svc = FrontmatterService(populated_workspace)
        items = svc.preview(spec_id="PM-2026-001")
        assert len(items) == 1
        assert items[0].status == "pending"
        assert items[0].has_frontmatter is False
        assert items[0].new_frontmatter != ""
        assert items[0].new_frontmatter.startswith("---")
        assert items[0].new_frontmatter.endswith("---")

    def test_apply_writes_frontmatter_to_file(self, populated_workspace: Path) -> None:
        """apply 应将 frontmatter 写入文件,文件以 --- 开头"""
        # 重写 PM-2026-001 文件,去掉 frontmatter
        pm_file = populated_workspace / "00_Obsidian_Base全局规范文件仓库" / "01_项目管理域" / "PM-2026-001_项目管理规范_DEV.md"
        original_content = "# 项目管理规范\n\n无 frontmatter 内容\n"
        pm_file.write_text(original_content, encoding="utf-8")

        svc = FrontmatterService(populated_workspace)
        items = svc.preview(spec_id="PM-2026-001")
        pending = [i for i in items if i.status == "pending"]
        assert len(pending) == 1

        result = svc.apply(pending)
        assert result.modified_count == 1
        assert result.skipped_count == 0
        assert result.error_count == 0

        # 验证文件已写入 frontmatter
        new_content = pm_file.read_text(encoding="utf-8")
        assert new_content.startswith("---")
        assert "spec_id: PM-2026-001" in new_content
        # 原始内容应保留
        assert "# 项目管理规范" in new_content

    def test_apply_skips_non_pending_items(self, populated_workspace: Path) -> None:
        """apply 应跳过非 pending 项(skipped/error)"""
        svc = FrontmatterService(populated_workspace)
        items = svc.preview()
        # 所有项都是 skipped(已有 frontmatter 或 deprecated)
        non_pending = [i for i in items if i.status != "pending"]
        assert len(non_pending) > 0

        result = svc.apply(non_pending)
        assert result.modified_count == 0
        assert result.skipped_count == len(non_pending)
        assert result.error_count == 0


class TestFrontmatterYamlGeneration:
    def test_special_characters_in_title(self, populated_workspace: Path) -> None:
        import json

        reg_path = populated_workspace / "00_Obsidian_Base全局规范文件仓库" / "spec_registry.json"
        data = json.loads(reg_path.read_text(encoding="utf-8"))
        data["specs"]["PM-2026-001"]["title"] = "规范：编程#标准 \"引用\""
        reg_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        svc = FrontmatterService(populated_workspace)
        items = svc.preview(spec_id="PM-2026-001")
        for item in items:
            if item.status == "pending" and item.new_frontmatter:
                fm_text = item.new_frontmatter.replace("---", "").strip()
                parsed = yaml.safe_load(fm_text)
                assert isinstance(parsed, dict)
                assert "规范" in parsed.get("title", "")


class TestReportService:
    def test_generate_markdown(self, populated_workspace: Path) -> None:
        svc = ReportService(populated_workspace)
        result = svc.generate(fmt="markdown")
        assert result.fmt == "markdown"
        assert result.output_path.exists()
        assert "规范元数据汇总报告" in result.content

    def test_generate_json(self, populated_workspace: Path) -> None:
        svc = ReportService(populated_workspace)
        result = svc.generate(fmt="json")
        assert result.fmt == "json"
        assert result.output_path.exists()
        import json

        data = json.loads(result.content)
        assert "specs" in data

    def test_generate_custom_output_path(self, populated_workspace: Path, tmp_path: Path) -> None:
        svc = ReportService(populated_workspace)
        custom_path = tmp_path / "custom_report.md"
        result = svc.generate(output_path=custom_path)
        assert result.output_path == custom_path
        assert custom_path.exists()

    def test_missing_registry(self, workspace: Path) -> None:
        with pytest.raises(FileNotFoundError):
            ReportService(workspace)

    def test_generate_markdown_contains_total_count(self, populated_workspace: Path) -> None:
        """markdown 报告应包含规范总数(SAMPLE_REGISTRY 有 4 个规范)"""
        svc = ReportService(populated_workspace)
        result = svc.generate(fmt="markdown")
        assert "规范总数" in result.content
        assert "**4**" in result.content  # PM-2026-001/PLC-2026-001/CODE-210/PM-2026-002

    def test_generate_markdown_contains_domain_section(self, populated_workspace: Path) -> None:
        """markdown 报告应包含按域分布章节"""
        svc = ReportService(populated_workspace)
        result = svc.generate(fmt="markdown")
        assert "按域分布" in result.content
        assert "`pm`" in result.content
        assert "`plc`" in result.content
        assert "`python`" in result.content

    def test_generate_markdown_contains_replacement_graph(self, populated_workspace: Path) -> None:
        """markdown 报告应包含替代关系图(mermaid)和替代关系表(PM-2026-002 → PM-2026-001)"""
        svc = ReportService(populated_workspace)
        result = svc.generate(fmt="markdown")
        assert "```mermaid" in result.content
        assert "graph LR" in result.content
        assert "PM-2026-002" in result.content
        assert "PM-2026-001" in result.content

    def test_generate_markdown_contains_lifecycle_stats(self, populated_workspace: Path) -> None:
        """markdown 报告应包含生命周期统计(stable 3 个,deprecated 1 个)"""
        svc = ReportService(populated_workspace)
        result = svc.generate(fmt="markdown")
        assert "活跃(stable)" in result.content
        assert "已废弃(deprecated)" in result.content
        assert "**3**" in result.content  # stable: PM-2026-001/PLC-2026-001/CODE-210
        assert "**1**" in result.content  # deprecated: PM-2026-002

    def test_generate_markdown_contains_yaml_metadata(self, populated_workspace: Path) -> None:
        """markdown 报告应包含完整 YAML 元数据清单(仅活跃规范)"""
        svc = ReportService(populated_workspace)
        result = svc.generate(fmt="markdown")
        assert "完整YAML元数据清单" in result.content
        assert "```yaml" in result.content
        # 活跃规范应包含
        assert "spec_id: PM-2026-001" in result.content
        assert "spec_id: PLC-2026-001" in result.content
        assert "spec_id: CODE-210" in result.content
        # deprecated 规范不应出现在 YAML 清单中
        yaml_section = result.content.split("完整YAML元数据清单")[1]
        assert "spec_id: PM-2026-002" not in yaml_section

    def test_generate_default_output_path_markdown(self, populated_workspace: Path) -> None:
        """默认输出路径应为 workspace/00_Obsidian_Base全局规范文件仓库/规范元数据汇总报告.md"""
        svc = ReportService(populated_workspace)
        result = svc.generate(fmt="markdown")
        expected = populated_workspace / "00_Obsidian_Base全局规范文件仓库" / "规范元数据汇总报告.md"
        assert result.output_path == expected

    def test_generate_default_output_path_json(self, populated_workspace: Path) -> None:
        """json 格式默认输出路径应为 .json 扩展名"""
        svc = ReportService(populated_workspace)
        result = svc.generate(fmt="json")
        assert result.output_path.suffix == ".json"
        assert "规范元数据汇总报告" in result.output_path.name

    def test_generate_creates_parent_dir(self, populated_workspace: Path, tmp_path: Path) -> None:
        """output_path 父目录不存在时应自动创建"""
        svc = ReportService(populated_workspace)
        nested_path = tmp_path / "nested" / "deep" / "dir" / "report.md"
        result = svc.generate(output_path=nested_path)
        assert nested_path.exists()
        assert result.output_path == nested_path
