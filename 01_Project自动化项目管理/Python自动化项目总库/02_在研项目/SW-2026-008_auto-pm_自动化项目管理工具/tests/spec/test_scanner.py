from __future__ import annotations

from pathlib import Path

from auto_pm.domain.spec.core.scanner import SpecScanner


class TestSpecScannerScanAll:
    def test_scan_finds_spec_files(self, populated_workspace: Path) -> None:
        scanner = SpecScanner(populated_workspace)
        result = scanner.scan_all()
        assert len(result) >= 3
        assert "PM-2026-001" in result
        assert "PLC-2026-001" in result
        assert "CODE-210" in result

    def test_scan_empty_workspace(self, workspace: Path) -> None:
        scanner = SpecScanner(workspace)
        result = scanner.scan_all()
        assert len(result) == 0

    def test_scan_ignores_non_spec_files(self, populated_workspace: Path) -> None:
        non_spec = populated_workspace / "00_Obsidian_Base全局规范文件仓库" / "01_项目管理域" / "random_notes.md"
        non_spec.write_text("# Random Notes", encoding="utf-8")
        scanner = SpecScanner(populated_workspace)
        result = scanner.scan_all()
        assert "random" not in result


class TestSpecScannerExtractVersion:
    def test_extract_version_chinese(self, populated_workspace: Path) -> None:
        scanner = SpecScanner(populated_workspace)
        spec_path = populated_workspace / "00_Obsidian_Base全局规范文件仓库" / "01_项目管理域" / "PM-2026-001_项目管理规范_DEV.md"
        version = scanner.extract_version(spec_path)
        assert version is not None
        assert "1.0.0" in version

    def test_extract_version_no_version(self, workspace: Path) -> None:
        spec_dir = workspace / "00_Obsidian_Base全局规范文件仓库" / "01_项目管理域"
        spec_dir.mkdir(parents=True, exist_ok=True)
        f = spec_dir / "PM-2026-099_无版本规范_DEV.md"
        f.write_text("# No version here\n", encoding="utf-8")
        scanner = SpecScanner(workspace)
        assert scanner.extract_version(f) is None


class TestSpecScannerExtractFrontmatter:
    def test_extract_existing_frontmatter(self, populated_workspace: Path) -> None:
        scanner = SpecScanner(populated_workspace)
        spec_path = populated_workspace / "00_Obsidian_Base全局规范文件仓库" / "01_项目管理域" / "PM-2026-001_项目管理规范_DEV.md"
        fm = scanner.extract_frontmatter(spec_path)
        assert fm is not None
        assert isinstance(fm, dict)
        assert fm.get("spec_id") == "PM-2026-001"

    def test_extract_no_frontmatter(self, workspace: Path) -> None:
        spec_dir = workspace / "00_Obsidian_Base全局规范文件仓库" / "01_项目管理域"
        spec_dir.mkdir(parents=True, exist_ok=True)
        f = spec_dir / "PM-2026-099_无frontmatter_DEV.md"
        f.write_text("# No frontmatter\n\nSome content\n", encoding="utf-8")
        scanner = SpecScanner(workspace)
        assert scanner.extract_frontmatter(f) is None

    def test_extract_invalid_yaml_frontmatter(self, workspace: Path) -> None:
        spec_dir = workspace / "00_Obsidian_Base全局规范文件仓库" / "01_项目管理域"
        spec_dir.mkdir(parents=True, exist_ok=True)
        f = spec_dir / "PM-2026-099_无效YAML_DEV.md"
        f.write_text("---\n: invalid: yaml: [\n---\n\n# Content\n", encoding="utf-8")
        scanner = SpecScanner(workspace)
        assert scanner.extract_frontmatter(f) is None


class TestSpecScannerFindDuplicates:
    def test_no_duplicates(self, populated_workspace: Path) -> None:
        scanner = SpecScanner(populated_workspace)
        dups = scanner.find_duplicates()
        assert len(dups) == 0

    def test_with_duplicates(self, populated_workspace: Path) -> None:
        spec_dir = populated_workspace / "00_Obsidian_Base全局规范文件仓库" / "01_项目管理域"
        dup_file = spec_dir / "PM-2026-001_项目管理规范_DEV_copy.md"
        dup_file.write_text("# Duplicate\n", encoding="utf-8")
        scanner = SpecScanner(populated_workspace)
        dups = scanner.find_duplicates()
        assert "PM-2026-001" in dups
        assert len(dups["PM-2026-001"]) >= 2


class TestSpecScannerPmSessionFiles:
    def test_iter_pm_session_files_ignores_lowercase_guides(self, workspace: Path) -> None:
        skill_dir = workspace / ".trae" / "skills" / "pm-workflow" / "refs"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "pm_session_guide.md").write_text("# guide\n", encoding="utf-8")

        project_dir = workspace / "DJ-2026-001"
        project_dir.mkdir()
        pm_file = project_dir / "PM_SESSION_DJ-2026-001.md"
        pm_file.write_text("# session\n", encoding="utf-8")

        scanner = SpecScanner(workspace)
        files = scanner.iter_pm_session_files()

        assert pm_file in files
        assert all(path.name != "pm_session_guide.md" for path in files)

    def test_iter_pm_session_files_skips_archived_sessions(self, workspace: Path) -> None:
        project_dir = workspace / "SW-2026-008"
        project_dir.mkdir()
        active_pm = project_dir / "PM_SESSION_SW-2026-008.md"
        active_pm.write_text("# active\n", encoding="utf-8")
        archived_pm = project_dir / "PM_SESSION_SW-2026-008_archive_auto.md"
        archived_pm.write_text("# archived\n", encoding="utf-8")

        archive_dir = workspace / "_archive" / "DJ-2026-009"
        archive_dir.mkdir(parents=True, exist_ok=True)
        nested_archived_pm = archive_dir / "PM_SESSION_DJ-2026-009.md"
        nested_archived_pm.write_text("# archived project\n", encoding="utf-8")

        scanner = SpecScanner(workspace)
        files = scanner.iter_pm_session_files()

        assert active_pm in files
        assert archived_pm not in files
        assert nested_archived_pm not in files

    def test_iter_pm_session_files_skips_template_sessions(self, workspace: Path) -> None:
        active_dir = workspace / "DJ-2026-005"
        active_dir.mkdir()
        active_pm = active_dir / "PM_SESSION_DJ-2026-005.md"
        active_pm.write_text("# active\n", encoding="utf-8")

        template_dir = workspace / ".trae" / "project-bootstrap" / "plc"
        template_dir.mkdir(parents=True, exist_ok=True)
        template_pm = template_dir / "PM_SESSION_TEMPLATE.md"
        template_pm.write_text("# template\n", encoding="utf-8")

        scanner = SpecScanner(workspace)
        files = scanner.iter_pm_session_files()

        assert active_pm in files
        assert template_pm not in files
