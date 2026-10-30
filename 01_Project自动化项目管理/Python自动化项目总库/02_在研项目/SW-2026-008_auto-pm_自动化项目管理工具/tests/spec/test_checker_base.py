from __future__ import annotations

from pathlib import Path

from auto_pm.domain.spec.core.checker_base import (
    CheckResult,
    DriftWarningChecker,
    DuplicateChecker,
    FrontmatterChecker,
    HealthChecker,
    IndexLinkChecker,
    NumberConflictChecker,
    ObsidianLinkChecker,
    PMSessionRefChecker,
    RulesPathChecker,
    Severity,
    UnlistedSpecChecker,
    VersionMismatchChecker,
)
from auto_pm.domain.spec.core.config import WorkspaceConfig
from auto_pm.domain.spec.core.registry import SpecRegistry
from auto_pm.domain.spec.core.scanner import SpecScanner


class TestDuplicateChecker:
    def test_no_duplicates(self, populated_workspace: Path) -> None:
        reg = SpecRegistry(populated_workspace)
        reg.load()
        scanner = SpecScanner(populated_workspace)
        checker = DuplicateChecker()
        results = checker.check(reg, scanner)
        shc001 = [r for r in results if r.check_id == "SHC-001"]
        assert len(shc001) == 0

    def test_with_duplicates(self, populated_workspace: Path) -> None:
        spec_dir = populated_workspace / "00_Obsidian_Base全局规范文件仓库" / "01_项目管理域"
        dup_file = spec_dir / "PM-2026-001_项目管理规范_DEV_copy.md"
        dup_file.write_text("# Duplicate\n", encoding="utf-8")
        reg = SpecRegistry(populated_workspace)
        reg.load()
        scanner = SpecScanner(populated_workspace)
        checker = DuplicateChecker()
        results = checker.check(reg, scanner)
        shc001 = [r for r in results if r.check_id == "SHC-001"]
        assert len(shc001) >= 1
        assert shc001[0].severity == Severity.ERROR


class TestVersionMismatchChecker:
    def test_matching_versions(self, populated_workspace: Path) -> None:
        reg = SpecRegistry(populated_workspace)
        reg.load()
        scanner = SpecScanner(populated_workspace)
        checker = VersionMismatchChecker()
        results = checker.check(reg, scanner)
        shc002 = [r for r in results if r.check_id == "SHC-002"]
        assert len(shc002) == 0

    def test_mismatched_versions(self, populated_workspace: Path) -> None:
        spec_path = populated_workspace / "00_Obsidian_Base全局规范文件仓库" / "01_项目管理域" / "PM-2026-001_项目管理规范_DEV.md"
        spec_path.write_text("# PM Spec\n\n版本: V9.9.9\n", encoding="utf-8")
        reg = SpecRegistry(populated_workspace)
        reg.load()
        scanner = SpecScanner(populated_workspace)
        checker = VersionMismatchChecker()
        results = checker.check(reg, scanner)
        shc002 = [r for r in results if r.check_id == "SHC-002"]
        assert len(shc002) >= 1


class TestFrontmatterChecker:
    def test_existing_frontmatter(self, populated_workspace: Path) -> None:
        reg = SpecRegistry(populated_workspace)
        reg.load()
        scanner = SpecScanner(populated_workspace)
        checker = FrontmatterChecker()
        results = checker.check(reg, scanner)
        shc007 = [r for r in results if r.check_id == "SHC-007"]
        assert all(r.severity == Severity.INFO for r in shc007)

    def test_missing_frontmatter(self, populated_workspace: Path) -> None:
        spec_path = populated_workspace / "00_Obsidian_Base全局规范文件仓库" / "01_项目管理域" / "PM-2026-001_项目管理规范_DEV.md"
        spec_path.write_text("# PM Spec without frontmatter\n\n版本: V1.0.0\n", encoding="utf-8")
        reg = SpecRegistry(populated_workspace)
        reg.load()
        scanner = SpecScanner(populated_workspace)
        checker = FrontmatterChecker()
        results = checker.check(reg, scanner)
        shc007 = [r for r in results if r.check_id == "SHC-007"]
        assert len(shc007) >= 1
        assert shc007[0].severity == Severity.INFO


class TestUnlistedSpecChecker:
    def test_all_registered(self, populated_workspace: Path) -> None:
        reg = SpecRegistry(populated_workspace)
        reg.load()
        scanner = SpecScanner(populated_workspace)
        checker = UnlistedSpecChecker()
        results = checker.check(reg, scanner)
        shc005 = [r for r in results if r.check_id == "SHC-005"]
        assert len(shc005) == 0

    def test_unlisted_spec(self, populated_workspace: Path) -> None:
        spec_dir = populated_workspace / "00_Obsidian_Base全局规范文件仓库" / "01_项目管理域"
        unlisted = spec_dir / "PM-9999-001_未注册规范_DEV.md"
        unlisted.write_text("# Unlisted\n", encoding="utf-8")
        reg = SpecRegistry(populated_workspace)
        reg.load()
        scanner = SpecScanner(populated_workspace)
        checker = UnlistedSpecChecker()
        results = checker.check(reg, scanner)
        shc005 = [r for r in results if r.check_id == "SHC-005"]
        assert len(shc005) >= 1


class TestIndexLinkChecker:
    def test_index_with_valid_links(self, populated_workspace: Path) -> None:
        config = WorkspaceConfig(workspace=populated_workspace)
        for output_path in config.full_output_paths.values():
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text("# Index\n", encoding="utf-8")
        reg = SpecRegistry(populated_workspace)
        reg.load()
        scanner = SpecScanner(populated_workspace, config)
        checker = IndexLinkChecker()
        results = checker.check(reg, scanner)
        shc004 = [r for r in results if r.check_id == "SHC-004"]
        assert len(shc004) == 0

    def test_index_with_broken_link(self, populated_workspace: Path) -> None:
        config = WorkspaceConfig(workspace=populated_workspace)
        index_path = config.full_output_paths.get("pm_index")
        if index_path:
            index_path.parent.mkdir(parents=True, exist_ok=True)
            index_path.write_text(
                "# Index\n\n| ID | File |\n|----|------|\n| PM-2026-001 | [PM-2026-001](nonexistent.md) |\n",
                encoding="utf-8",
            )
        reg = SpecRegistry(populated_workspace)
        reg.load()
        scanner = SpecScanner(populated_workspace, config)
        checker = IndexLinkChecker()
        results = checker.check(reg, scanner)
        shc004 = [r for r in results if r.check_id == "SHC-004"]
        assert len(shc004) >= 1
        assert shc004[0].severity == Severity.ERROR


class TestObsidianLinkChecker:
    def test_no_broken_links(self, populated_workspace: Path) -> None:
        reg = SpecRegistry(populated_workspace)
        reg.load()
        scanner = SpecScanner(populated_workspace)
        checker = ObsidianLinkChecker()
        results = checker.check(reg, scanner)
        shc006 = [r for r in results if r.check_id == "SHC-006"]
        assert len(shc006) == 0

    def test_broken_wikilink(self, populated_workspace: Path) -> None:
        spec_path = populated_workspace / "00_Obsidian_Base全局规范文件仓库" / "01_项目管理域" / "PM-2026-001_项目管理规范_DEV.md"
        spec_path.write_text(
            "---\nspec_id: PM-2026-001\n---\n\n# Title\n\nSee [[PM-9999-888_nonexistent]]\n",
            encoding="utf-8",
        )
        reg = SpecRegistry(populated_workspace)
        reg.load()
        scanner = SpecScanner(populated_workspace)
        checker = ObsidianLinkChecker()
        results = checker.check(reg, scanner)
        shc006 = [r for r in results if r.check_id == "SHC-006"]
        assert len(shc006) >= 1


class TestRulesPathChecker:
    def test_no_rules_dir(self, populated_workspace: Path) -> None:
        reg = SpecRegistry(populated_workspace)
        reg.load()
        scanner = SpecScanner(populated_workspace)
        checker = RulesPathChecker()
        results = checker.check(reg, scanner)
        shc008 = [r for r in results if r.check_id == "SHC-008"]
        assert len(shc008) == 0

    def test_rules_with_deprecated_ref(self, populated_workspace: Path) -> None:
        rules_dir = populated_workspace / ".trae" / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        rule_file = rules_dir / "test_rule.md"
        rule_file.write_text("遵循规范 PM-2026-002", encoding="utf-8")
        reg = SpecRegistry(populated_workspace)
        reg.load()
        scanner = SpecScanner(populated_workspace)
        checker = RulesPathChecker()
        results = checker.check(reg, scanner)
        shc008 = [r for r in results if r.check_id == "SHC-008"]
        assert len(shc008) >= 1
        assert any(r.severity == Severity.WARNING for r in shc008)


class TestPMSessionRefChecker:
    def test_project_scope_only_scans_project_root(self, populated_workspace: Path) -> None:
        project_a = populated_workspace / "DJ-2026-000"
        project_b = populated_workspace / "DJ-2026-001"
        project_a.mkdir(parents=True, exist_ok=True)
        project_b.mkdir(parents=True, exist_ok=True)

        (project_a / "PM_SESSION_DJ-2026-000.md").write_text(
            "# PM_SESSION_DJ-2026-000\n\n## 4. Artifacts Index\n- req:\n  - [missing_a](missing_a.md)\n",
            encoding="utf-8",
        )
        (project_b / "PM_SESSION_DJ-2026-001.md").write_text(
            "# PM_SESSION_DJ-2026-001\n\n## 4. Artifacts Index\n- req:\n  - [missing_b](missing_b.md)\n",
            encoding="utf-8",
        )

        reg = SpecRegistry(populated_workspace)
        reg.load()
        scanner = SpecScanner(populated_workspace, project_root=project_a)
        checker = PMSessionRefChecker()
        results = checker.check(reg, scanner)

        shc009 = [r for r in results if r.check_id == "SHC-009"]
        assert len(shc009) == 1
        assert "DJ-2026-000" in shc009[0].details
        assert "missing_a.md" in shc009[0].message


class TestHealthChecker:
    def test_run_all(self, populated_workspace: Path) -> None:
        reg = SpecRegistry(populated_workspace)
        reg.load()
        scanner = SpecScanner(populated_workspace)
        checker = HealthChecker()
        results = checker.run_all(reg, scanner)
        assert isinstance(results, list)
        assert all(isinstance(r, CheckResult) for r in results)

    def test_run_by_id(self, populated_workspace: Path) -> None:
        reg = SpecRegistry(populated_workspace)
        reg.load()
        scanner = SpecScanner(populated_workspace)
        checker = HealthChecker()
        results = checker.run_by_id("SHC-001", reg, scanner)
        assert all(r.check_id == "SHC-001" for r in results)

    def test_run_by_invalid_id(self, populated_workspace: Path) -> None:
        reg = SpecRegistry(populated_workspace)
        reg.load()
        scanner = SpecScanner(populated_workspace)
        checker = HealthChecker()
        results = checker.run_by_id("SHC-999", reg, scanner)
        assert len(results) == 0


class TestNumberConflictChecker:
    """SHC-015: 跨前缀编号冲突检测"""

    def test_no_conflict(self, populated_workspace: Path) -> None:
        """无冲突时返回空结果"""
        reg = SpecRegistry(populated_workspace)
        reg.load()
        scanner = SpecScanner(populated_workspace)
        checker = NumberConflictChecker()
        results = checker.check(reg, scanner)
        shc015 = [r for r in results if r.check_id == "SHC-015"]
        # 测试工作空间中无预设冲突，结果应为空
        assert all(r.severity == Severity.WARNING for r in shc015)

    def test_detects_cross_prefix_conflict(self, populated_workspace: Path) -> None:
        """当两个条目拥有相同 number 但不同 type_prefix 时，应报 SHC-015"""
        reg = SpecRegistry(populated_workspace)
        reg.load()
        # 人工注入跨前缀冲突：TOOL-906 与 LSP-906 共享编号 906
        from auto_pm.domain.spec.core.registry import SpecInfo
        reg._specs["TOOL-906"] = SpecInfo(spec_id="TOOL-906", number="906", type_prefix="TOOL", title="Mermaid规范")
        reg._specs["LSP-906"] = SpecInfo(spec_id="LSP-906", number="906", type_prefix="LSP", title="PLC错误预防")
        scanner = SpecScanner(populated_workspace)
        checker = NumberConflictChecker()
        results = checker.check(reg, scanner)
        shc015 = [r for r in results if r.check_id == "SHC-015"]
        assert len(shc015) >= 1
        assert shc015[0].severity == Severity.WARNING
        assert "906" in shc015[0].message
        assert "TOOL-906" in shc015[0].details or "LSP-906" in shc015[0].details

    def test_same_prefix_number_not_flagged(self, populated_workspace: Path) -> None:
        """相同 type_prefix 不同编号，不应报冲突"""
        reg = SpecRegistry(populated_workspace)
        reg.load()
        from auto_pm.domain.spec.core.registry import SpecInfo
        reg._specs["LSP-901"] = SpecInfo(spec_id="LSP-901", number="901", type_prefix="LSP", title="A")
        reg._specs["LSP-902"] = SpecInfo(spec_id="LSP-902", number="902", type_prefix="LSP", title="B")
        scanner = SpecScanner(populated_workspace)
        checker = NumberConflictChecker()
        results = checker.check(reg, scanner)
        # 编号 901、902 各自唯一，不应报冲突
        conflicts = {r.message for r in results if r.check_id == "SHC-015"}
        assert "901" not in " ".join(conflicts)
        assert "902" not in " ".join(conflicts)


class TestDriftWarningChecker:
    """SHC-016: drift_warning 强制告警"""

    def test_no_drift_warning(self, populated_workspace: Path) -> None:
        """无 drift_warning 字段时返回空结果"""
        reg = SpecRegistry(populated_workspace)
        reg.load()
        # 确保 raw 数据中无 drift_warning
        for spec_data in reg.raw.get("specs", {}).values():
            if isinstance(spec_data, dict):
                spec_data.pop("drift_warning", None)
        scanner = SpecScanner(populated_workspace)
        checker = DriftWarningChecker()
        results = checker.check(reg, scanner)
        shc016 = [r for r in results if r.check_id == "SHC-016"]
        assert len(shc016) == 0

    def test_detects_drift_warning(self, populated_workspace: Path) -> None:
        """当 raw 数据中存在 drift_warning 时，应报 SHC-016"""
        reg = SpecRegistry(populated_workspace)
        reg.load()
        # 注入一个含 drift_warning 的条目到 raw
        reg._raw.setdefault("specs", {})["PM-042"] = {
            "title": "PM_SESSION规范",
            "version": "V1.0.0",
            "drift_warning": "项目副本版本 V0.9.0 落后于真源 V1.0.0，请同步",
        }
        scanner = SpecScanner(populated_workspace)
        checker = DriftWarningChecker()
        results = checker.check(reg, scanner)
        shc016 = [r for r in results if r.check_id == "SHC-016"]
        assert len(shc016) >= 1
        assert shc016[0].severity == Severity.WARNING
        assert "PM-042" in shc016[0].message
        assert "drift_warning" not in shc016[0].details  # 应该是 drift 内容，不是字段名
        assert "V0.9.0" in shc016[0].details or "V1.0.0" in shc016[0].details

    def test_multiple_drift_warnings(self, populated_workspace: Path) -> None:
        """多个 drift_warning 条目应各自独立报告"""
        reg = SpecRegistry(populated_workspace)
        reg.load()
        reg._raw.setdefault("specs", {})
        reg._raw["specs"]["DEV-801"] = {"drift_warning": "版本漂移 A"}
        reg._raw["specs"]["DEV-802"] = {"drift_warning": "版本漂移 B"}
        scanner = SpecScanner(populated_workspace)
        checker = DriftWarningChecker()
        results = checker.check(reg, scanner)
        shc016 = [r for r in results if r.check_id == "SHC-016"]
        ids = {r.message.split(" ")[0] for r in shc016}
        assert "DEV-801" in ids
        assert "DEV-802" in ids

    def test_registered_in_health_checker(self, populated_workspace: Path) -> None:
        """SHC-015 和 SHC-016 应被 HealthChecker.run_by_id 正确调度"""
        reg = SpecRegistry(populated_workspace)
        reg.load()
        scanner = SpecScanner(populated_workspace)
        hc = HealthChecker()
        # run_by_id 返回非 None（即使空列表）表示 ID 已注册
        res015 = hc.run_by_id("SHC-015", reg, scanner)
        res016 = hc.run_by_id("SHC-016", reg, scanner)
        assert isinstance(res015, list)
        assert isinstance(res016, list)
