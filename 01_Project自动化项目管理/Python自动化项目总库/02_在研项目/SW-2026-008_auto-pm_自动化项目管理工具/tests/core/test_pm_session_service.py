"""PM_SESSION 服务测试 - CHG-088 Stage 2

测试 PmSessionParser / PmSessionCheckService / PmSessionArchiveService / generate_view。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from auto_pm.core.pm_session_service import (
    DEPRECATED_SECTIONS,
    MAX_FILE_LINES,
    MAX_FILE_SIZE_KB,
    REQUIRED_SECTIONS,
    ArchiveResult,
    CheckResult,
    PmSessionArchiveService,
    PmSessionCheckService,
    PmSessionParser,
    generate_view,
)

# ---------- Fixtures ----------

SAMPLE_PM_SESSION = """# PM_SESSION_TEST

## 0. Meta

- project_id: TEST-001
- last_updated: 2026-07-04

## 1. Positioning

- one_liner: 测试项目

## 2. Current Focus

- current_focus: 当前焦点

## 3. Status Summary

- in_progress: 测试中

## 4. Artifacts Index

- req: doc.md

## 5. Logs

- change_log: 测试日志

## 6. Implementation Log

- 2026-07-04 测试实施记录

## 8. Handoff Notes

- current_state: 测试状态

## 9. Next Actions

- [待启动] 测试下一步
"""


SAMPLE_WITH_SECTION_7 = """# PM_SESSION_TEST

## 0. Meta

- project_id: TEST-001

## 7. Verification Log

- 旧章节不应存在

## 8. Handoff Notes

- current_state: 测试
"""


@pytest.fixture
def sample_pm_session_file(tmp_path: Path) -> Path:
    """创建测试用 PM_SESSION 文件"""
    f = tmp_path / "PM_SESSION_TEST-001.md"
    f.write_text(SAMPLE_PM_SESSION, encoding="utf-8")
    return f


@pytest.fixture
def sample_with_section_7_file(tmp_path: Path) -> Path:
    """创建包含 §7 的测试文件（应触发 deprecated 警告）"""
    f = tmp_path / "PM_SESSION_TEST-002.md"
    f.write_text(SAMPLE_WITH_SECTION_7, encoding="utf-8")
    return f


# ---------- PmSessionParser 测试 ----------


class TestPmSessionParser:
    def test_parse_content_returns_all_sections(self) -> None:
        parser = PmSessionParser()
        result = parser.parse_content(SAMPLE_PM_SESSION)
        section_numbers = {s.number for s in result.sections}
        assert section_numbers == {"0", "1", "2", "3", "4", "5", "6", "8", "9"}

    def test_parse_content_extracts_section_titles(self) -> None:
        parser = PmSessionParser()
        result = parser.parse_content(SAMPLE_PM_SESSION)
        section_0 = result.get_section("0")
        assert section_0 is not None
        assert section_0.title == "Meta"
        section_2 = result.get_section("2")
        assert section_2 is not None
        assert "Current Focus" in section_2.title

    def test_parse_content_section_content(self) -> None:
        parser = PmSessionParser()
        result = parser.parse_content(SAMPLE_PM_SESSION)
        section_0 = result.get_section("0")
        assert section_0 is not None
        assert "project_id: TEST-001" in section_0.content
        assert "last_updated: 2026-07-04" in section_0.content

    def test_parse_content_line_numbers(self) -> None:
        parser = PmSessionParser()
        result = parser.parse_content(SAMPLE_PM_SESSION)
        section_0 = result.get_section("0")
        assert section_0 is not None
        assert section_0.start_line < section_0.end_line
        assert section_0.line_count > 0

    def test_parse_file(self, sample_pm_session_file: Path) -> None:
        parser = PmSessionParser()
        result = parser.parse_file(sample_pm_session_file)
        assert result.file_path == sample_pm_session_file
        assert result.total_lines > 0
        assert len(result.sections) == 9

    def test_parse_content_pre_header_lines(self) -> None:
        parser = PmSessionParser()
        result = parser.parse_content(SAMPLE_PM_SESSION)
        assert len(result.pre_header_lines) > 0
        assert result.pre_header_lines[0] == "# PM_SESSION_TEST"

    def test_get_section_nonexistent(self) -> None:
        parser = PmSessionParser()
        result = parser.parse_content(SAMPLE_PM_SESSION)
        assert result.get_section("99") is None

    def test_find_missing_required_empty(self) -> None:
        parser = PmSessionParser()
        result = parser.parse_content(SAMPLE_PM_SESSION)
        assert result.find_missing_required() == set()

    def test_find_missing_required_with_gaps(self) -> None:
        parser = PmSessionParser()
        result = parser.parse_content(SAMPLE_WITH_SECTION_7)
        # SAMPLE_WITH_SECTION_7 只有 §0 和 §7 和 §8
        missing = result.find_missing_required()
        assert "1" in missing
        assert "2" in missing
        assert "3" in missing
        assert "6" in missing
        assert "9" in missing

    def test_find_deprecated_present_empty(self) -> None:
        parser = PmSessionParser()
        result = parser.parse_content(SAMPLE_PM_SESSION)
        assert result.find_deprecated_present() == set()

    def test_find_deprecated_present_with_section_7(self) -> None:
        parser = PmSessionParser()
        result = parser.parse_content(SAMPLE_WITH_SECTION_7)
        assert "7" in result.find_deprecated_present()


# ---------- PmSessionCheckService 测试 ----------


class TestPmSessionCheckService:
    def test_check_healthy_file(self, sample_pm_session_file: Path) -> None:
        svc = PmSessionCheckService()
        result = svc.check(sample_pm_session_file)
        assert isinstance(result, CheckResult)
        assert result.is_healthy
        assert result.missing_required == set()
        assert result.deprecated_present == set()
        assert not result.is_oversized
        assert result.warnings == []

    def test_check_finds_missing_sections(self, sample_with_section_7_file: Path) -> None:
        svc = PmSessionCheckService()
        result = svc.check(sample_with_section_7_file)
        assert not result.is_healthy
        assert len(result.missing_required) > 0
        assert any("缺失必须章节" in w for w in result.warnings)

    def test_check_finds_deprecated_section(self, sample_with_section_7_file: Path) -> None:
        svc = PmSessionCheckService()
        result = svc.check(sample_with_section_7_file)
        assert "7" in result.deprecated_present
        assert any("已归档章节回归" in w for w in result.warnings)

    def test_check_oversized_file(self, tmp_path: Path) -> None:
        # 创建超大文件（> 150KB = 153600 字节）
        # 每个章节填充大量内容，确保总大小超过阈值
        big_content = "# PM_SESSION_BIG\n\n## 0. Meta\n\n- project_id: BIG\n\n"
        # §1-§6 各填充 30000 字节（180000 字节总计，超过 150KB）
        for i in range(1, 7):
            big_content += f"\n## {i}. Section {i}\n\n"
            # 每行约 100 字符，300 行约 30000 字节
            big_content += "\n".join(f"- line {i}-{j} " + "x" * 90 for j in range(300))
            big_content += "\n"
        # §8 和 §9
        big_content += "\n## 8. Handoff Notes\n\n- handoff\n\n## 9. Next Actions\n\n- next\n"
        big_file = tmp_path / "PM_SESSION_BIG.md"
        big_file.write_text(big_content, encoding="utf-8")

        svc = PmSessionCheckService()
        result = svc.check(big_file)
        assert result.is_oversized
        assert any("超过阈值" in w for w in result.warnings)

    def test_check_nonexistent_file(self, tmp_path: Path) -> None:
        svc = PmSessionCheckService()
        with pytest.raises(FileNotFoundError):
            svc.check(tmp_path / "nonexistent.md")

    def test_freshness_no_change_files_no_warning(self, tmp_path: Path) -> None:
        pm_file = tmp_path / "PM_SESSION_TEST.md"
        pm_file.write_text(SAMPLE_PM_SESSION, encoding="utf-8")
        svc = PmSessionCheckService()
        result = svc.check(pm_file)
        assert not any("落账可能滞后" in w for w in result.warnings)

    def test_freshness_change_file_older_no_warning(self, tmp_path: Path) -> None:
        pm_file = tmp_path / "PM_SESSION_TEST.md"
        pm_file.write_text(SAMPLE_PM_SESSION, encoding="utf-8")
        chg_file = tmp_path / "CHG-PLC-2026-001.md"
        chg_file.write_text("# CHG-001\n- status: closed\n", encoding="utf-8")
        os.utime(pm_file, (1000.0, 1000.0))
        os.utime(chg_file, (500.0, 500.0))
        svc = PmSessionCheckService()
        result = svc.check(pm_file)
        assert not any("落账可能滞后" in w for w in result.warnings)

    def test_freshness_change_file_newer_warns(self, tmp_path: Path) -> None:
        pm_file = tmp_path / "PM_SESSION_TEST.md"
        pm_file.write_text(SAMPLE_PM_SESSION, encoding="utf-8")
        chg_file = tmp_path / "CHG-PLC-2026-001.md"
        chg_file.write_text("# CHG-001\n- status: closed\n", encoding="utf-8")
        os.utime(pm_file, (1000.0, 1000.0))
        os.utime(chg_file, (2000.0, 2000.0))
        svc = PmSessionCheckService()
        result = svc.check(pm_file)
        assert any("落账可能滞后" in w for w in result.warnings)


# ---------- PmSessionArchiveService 测试 ----------


class TestPmSessionArchiveService:
    def test_archive_section_creates_archive_file(self, tmp_path: Path) -> None:
        # 创建测试文件
        content = "# PM_SESSION_TEST\n\n## 6. Implementation Log\n\n"
        content += "\n".join(f"- line {i}" for i in range(50))
        content += "\n\n## 8. Handoff Notes\n\n- handoff\n"
        main_file = tmp_path / "PM_SESSION_TEST.md"
        main_file.write_text(content, encoding="utf-8")
        archive_file = tmp_path / "archive.md"

        svc = PmSessionArchiveService()
        result = svc.archive_section(
            main_file=main_file,
            archive_file=archive_file,
            section_number="6",
            keep_recent=0,
            create_backup=False,
        )

        assert isinstance(result, ArchiveResult)
        assert result.archive_file == archive_file
        assert result.archived_sections == ["6"]
        assert result.archived_line_count > 0
        assert result.main_file_lines_after < result.main_file_lines_before
        assert archive_file.exists()

    def test_archive_section_keep_recent(self, tmp_path: Path) -> None:
        content = "# PM_SESSION_TEST\n\n## 6. Implementation Log\n\n"
        content += "\n".join(f"- line {i}" for i in range(50))
        content += "\n\n## 8. Handoff Notes\n\n- handoff\n"
        main_file = tmp_path / "PM_SESSION_TEST.md"
        main_file.write_text(content, encoding="utf-8")
        archive_file = tmp_path / "archive.md"

        svc = PmSessionArchiveService()
        svc.archive_section(
            main_file=main_file,
            archive_file=archive_file,
            section_number="6",
            keep_recent=10,
            create_backup=False,
        )

        # 主文件应保留 §6 的 header + 10 行
        new_content = main_file.read_text(encoding="utf-8")
        assert "## 6. Implementation Log" in new_content
        assert "## 8. Handoff Notes" in new_content

    def test_archive_section_creates_backup(self, tmp_path: Path) -> None:
        content = "# PM_SESSION_TEST\n\n## 6. Log\n\n- x\n\n## 8. Handoff\n\n- y\n"
        main_file = tmp_path / "PM_SESSION_TEST.md"
        main_file.write_text(content, encoding="utf-8")
        archive_file = tmp_path / "archive.md"

        svc = PmSessionArchiveService()
        result = svc.archive_section(
            main_file=main_file,
            archive_file=archive_file,
            section_number="6",
            keep_recent=0,
            create_backup=True,
        )

        assert result.backup_file is not None
        assert result.backup_file.exists()

    def test_archive_section_appends_to_existing_archive(self, tmp_path: Path) -> None:
        content = "# PM_SESSION_TEST\n\n## 6. Log\n\n- x\n\n## 8. Handoff\n\n- y\n"
        main_file = tmp_path / "PM_SESSION_TEST.md"
        main_file.write_text(content, encoding="utf-8")
        archive_file = tmp_path / "archive.md"
        archive_file.write_text("# Existing Archive\n\n## old\n- old content\n", encoding="utf-8")

        svc = PmSessionArchiveService()
        svc.archive_section(
            main_file=main_file,
            archive_file=archive_file,
            section_number="6",
            keep_recent=0,
            create_backup=False,
        )

        archive_content = archive_file.read_text(encoding="utf-8")
        assert "Existing Archive" in archive_content
        assert "## 6. Log" in archive_content

    def test_archive_section_nonexistent_section(self, tmp_path: Path) -> None:
        content = "# PM_SESSION_TEST\n\n## 0. Meta\n\n- x\n"
        main_file = tmp_path / "PM_SESSION_TEST.md"
        main_file.write_text(content, encoding="utf-8")
        archive_file = tmp_path / "archive.md"

        svc = PmSessionArchiveService()
        with pytest.raises(ValueError, match="章节 §99"):
            svc.archive_section(
                main_file=main_file,
                archive_file=archive_file,
                section_number="99",
            )

    def test_archive_section_nonexistent_main_file(self, tmp_path: Path) -> None:
        svc = PmSessionArchiveService()
        with pytest.raises(FileNotFoundError):
            svc.archive_section(
                main_file=tmp_path / "nonexistent.md",
                archive_file=tmp_path / "archive.md",
                section_number="6",
            )

    def test_archive_section_keep_recent_ge_total(self, tmp_path: Path) -> None:
        """keep_recent >= 章节总行数时，应跳过归档"""
        content = "# PM_SESSION_TEST\n\n## 6. Log\n\n- x\n\n## 8. Handoff\n\n- y\n"
        main_file = tmp_path / "PM_SESSION_TEST.md"
        main_file.write_text(content, encoding="utf-8")
        archive_file = tmp_path / "archive.md"

        svc = PmSessionArchiveService()
        result = svc.archive_section(
            main_file=main_file,
            archive_file=archive_file,
            section_number="6",
            keep_recent=100,  # 远超章节行数
            create_backup=False,
        )

        assert result.archived_line_count == 0
        assert result.main_file_lines_after == result.main_file_lines_before


# ---------- generate_view 测试 ----------


class TestGenerateView:
    def test_generate_view_contains_header(self) -> None:
        parser = PmSessionParser()
        result = parser.parse_content(SAMPLE_PM_SESSION)
        view = generate_view(result)
        assert "PM_SESSION 只读视图" in view

    def test_generate_view_contains_section_2(self) -> None:
        parser = PmSessionParser()
        result = parser.parse_content(SAMPLE_PM_SESSION)
        view = generate_view(result)
        assert "§2" in view
        assert "Current Focus" in view
        assert "当前焦点" in view

    def test_generate_view_contains_section_3(self) -> None:
        parser = PmSessionParser()
        result = parser.parse_content(SAMPLE_PM_SESSION)
        view = generate_view(result)
        assert "§3" in view
        assert "Status Summary" in view

    def test_generate_view_contains_section_9(self) -> None:
        parser = PmSessionParser()
        result = parser.parse_content(SAMPLE_PM_SESSION)
        view = generate_view(result)
        assert "§9" in view
        assert "Next Actions" in view
        assert "待启动" in view

    def test_generate_view_does_not_contain_section_7(self) -> None:
        parser = PmSessionParser()
        result = parser.parse_content(SAMPLE_PM_SESSION)
        view = generate_view(result)
        assert "§7" not in view


# ---------- 常量测试 ----------


class TestConstants:
    def test_required_sections_excludes_7(self) -> None:
        assert "7" not in REQUIRED_SECTIONS
        assert "0" in REQUIRED_SECTIONS
        assert "9" in REQUIRED_SECTIONS

    def test_deprecated_sections_contains_7(self) -> None:
        assert "7" in DEPRECATED_SECTIONS

    def test_thresholds_reasonable(self) -> None:
        assert MAX_FILE_SIZE_KB > 0
        assert MAX_FILE_LINES > 0
        assert MAX_FILE_SIZE_KB == 150  # CHG-087 权威上限
        assert MAX_FILE_LINES == 300  # CHG-087 权威上限


# ---------- archive_section_8 测试（CHG-109）----------


SAMPLE_PM_SESSION_WITH_HANDOFFS = """# PM_SESSION_TEST

## 0. Meta

- project_id: TEST-001

## 1. Positioning

- one_liner: 测试项目

## 2. Current Focus

- current_focus: 当前焦点

## 3. Status Summary

- in_progress: 测试中

## 4. Artifacts Index

- req: doc.md

## 5. Logs

- change_log: 测试日志

## 6. Implementation Log

- 2026-07-04 测试实施记录

## 8. Handoff Notes

- current_state: 最新状态

- current_state_gui_test: GUI 测试状态

- skill_handoff_001: 第1条 skill_handoff（最新）

- skill_handoff_002: 第2条 skill_handoff

- skill_handoff_003: 第3条 skill_handoff

- skill_handoff_004: 第4条 skill_handoff

- skill_handoff_005: 第5条 skill_handoff（最旧）

> 归档说明：早期 skill_handoff 已归档

## 9. Next Actions

- [待启动] 测试下一步
"""


@pytest.fixture
def sample_pm_session_with_handoffs(tmp_path: Path) -> Path:
    """创建含多条 skill_handoff 的 §8 测试文件（CHG-109）"""
    f = tmp_path / "PM_SESSION_TEST_HANDOFF.md"
    f.write_text(SAMPLE_PM_SESSION_WITH_HANDOFFS, encoding="utf-8")
    return f


class TestArchiveSection8:
    """§8 条目级归档测试（CHG-109）"""

    def test_keeps_latest_n_skill_handoffs(self, sample_pm_session_with_handoffs: Path, tmp_path: Path) -> None:
        """保留最新 N 条 skill_handoff，归档其余"""
        archive_file = tmp_path / "archive.md"
        svc = PmSessionArchiveService()
        result = svc.archive_section_8(
            main_file=sample_pm_session_with_handoffs,
            archive_file=archive_file,
            keep_entries=2,
            create_backup=False,
        )

        # 应归档 3 条（005/004/003），保留 2 条（001/002）
        assert result.archived_line_count > 0
        assert result.main_file_lines_after < result.main_file_lines_before

        new_content = sample_pm_session_with_handoffs.read_text(encoding="utf-8")
        # 最新 2 条保留
        assert "skill_handoff_001" in new_content
        assert "skill_handoff_002" in new_content
        # 旧 3 条已归档
        assert "skill_handoff_003" not in new_content
        assert "skill_handoff_004" not in new_content
        assert "skill_handoff_005" not in new_content

    def test_preserves_current_state(self, sample_pm_session_with_handoffs: Path, tmp_path: Path) -> None:
        """current_state* 条目始终保留"""
        archive_file = tmp_path / "archive.md"
        svc = PmSessionArchiveService()
        svc.archive_section_8(
            main_file=sample_pm_session_with_handoffs,
            archive_file=archive_file,
            keep_entries=1,
            create_backup=False,
        )

        new_content = sample_pm_session_with_handoffs.read_text(encoding="utf-8")
        assert "current_state: 最新状态" in new_content
        assert "current_state_gui_test" in new_content

    def test_preserves_archive_note(self, sample_pm_session_with_handoffs: Path, tmp_path: Path) -> None:
        """归档说明（> 开头）始终保留"""
        archive_file = tmp_path / "archive.md"
        svc = PmSessionArchiveService()
        svc.archive_section_8(
            main_file=sample_pm_session_with_handoffs,
            archive_file=archive_file,
            keep_entries=1,
            create_backup=False,
        )

        new_content = sample_pm_session_with_handoffs.read_text(encoding="utf-8")
        assert "归档说明" in new_content

    def test_no_archive_when_keep_entries_ge_total(self, sample_pm_session_with_handoffs: Path, tmp_path: Path) -> None:
        """keep_entries >= skill_handoff 总数时不归档"""
        archive_file = tmp_path / "archive.md"
        svc = PmSessionArchiveService()
        result = svc.archive_section_8(
            main_file=sample_pm_session_with_handoffs,
            archive_file=archive_file,
            keep_entries=10,  # 远超 5 条
            create_backup=False,
        )

        assert result.archived_line_count == 0
        assert result.main_file_lines_after == result.main_file_lines_before

    def test_appends_to_archive_file(self, sample_pm_session_with_handoffs: Path, tmp_path: Path) -> None:
        """归档内容追加到归档文件"""
        archive_file = tmp_path / "archive.md"
        archive_file.write_text("# 已有归档\n\n## old\n- old content\n", encoding="utf-8")

        svc = PmSessionArchiveService()
        svc.archive_section_8(
            main_file=sample_pm_session_with_handoffs,
            archive_file=archive_file,
            keep_entries=2,
            create_backup=False,
        )

        archive_content = archive_file.read_text(encoding="utf-8")
        assert "已有归档" in archive_content
        assert "skill_handoff_005" in archive_content
        assert "skill_handoff_004" in archive_content
        assert "skill_handoff_003" in archive_content

    def test_nonexistent_section_8(self, tmp_path: Path) -> None:
        """§8 不存在时抛 ValueError"""
        content = "# PM_SESSION_TEST\n\n## 0. Meta\n\n- x\n"
        main_file = tmp_path / "PM_SESSION_TEST.md"
        main_file.write_text(content, encoding="utf-8")
        archive_file = tmp_path / "archive.md"

        svc = PmSessionArchiveService()
        with pytest.raises(ValueError, match="章节 §8"):
            svc.archive_section_8(
                main_file=main_file,
                archive_file=archive_file,
                keep_entries=2,
            )

    def test_nonexistent_main_file(self, tmp_path: Path) -> None:
        """主文件不存在时抛 FileNotFoundError"""
        svc = PmSessionArchiveService()
        with pytest.raises(FileNotFoundError):
            svc.archive_section_8(
                main_file=tmp_path / "nonexistent.md",
                archive_file=tmp_path / "archive.md",
                keep_entries=2,
            )

    def test_creates_backup(self, sample_pm_session_with_handoffs: Path, tmp_path: Path) -> None:
        """create_backup=True 时创建备份文件"""
        archive_file = tmp_path / "archive.md"
        svc = PmSessionArchiveService()
        result = svc.archive_section_8(
            main_file=sample_pm_session_with_handoffs,
            archive_file=archive_file,
            keep_entries=2,
            create_backup=True,
        )

        assert result.backup_file is not None
        assert result.backup_file.exists()


class TestResolveArchiveFile:
    """归档文件版本切分测试（CHG-109 T3）"""

    def test_under_threshold_returns_same_file(self, tmp_path: Path) -> None:
        """归档文件未超 200KB，返回原路径"""
        archive_file = tmp_path / "archive.md"
        archive_file.write_text("# 小归档\n", encoding="utf-8")

        svc = PmSessionArchiveService()
        result = svc._resolve_archive_file(archive_file)
        assert result == archive_file

    def test_nonexistent_file_returns_same_file(self, tmp_path: Path) -> None:
        """归档文件不存在，返回原路径"""
        archive_file = tmp_path / "nonexistent_archive.md"

        svc = PmSessionArchiveService()
        result = svc._resolve_archive_file(archive_file)
        assert result == archive_file

    def test_over_threshold_returns_new_file(self, tmp_path: Path) -> None:
        """归档文件超 200KB，返回带日期的新文件路径"""
        archive_file = tmp_path / "PM_SESSION_TEST_archive_V0.6.0.md"
        # 创建超过 200KB 的文件
        big_content = "# 大归档\n\n" + "x" * (210 * 1024)
        archive_file.write_text(big_content, encoding="utf-8")

        svc = PmSessionArchiveService()
        result = svc._resolve_archive_file(archive_file)

        # 应返回新文件路径（含 _auto_YYYYMMDD）
        assert result != archive_file
        assert "_auto_" in result.name
        assert result.name.startswith("PM_SESSION_TEST_archive_V0.6.0_auto_")
