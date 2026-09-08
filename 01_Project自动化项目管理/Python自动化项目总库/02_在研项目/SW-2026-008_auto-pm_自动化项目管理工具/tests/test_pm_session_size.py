"""PM_SESSION 规模门禁元测试 - CHG-088 Stage 2

强制门禁：PM_SESSION 主文件大小和章节完整性。

此测试是元测试（meta-test），检查项目自身的 PM_SESSION 文件是否健康。
违反门禁时测试失败，阻止 PM_SESSION 继续膨胀。

运行方式：
    pytest tests/test_pm_session_size.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest
from auto_pm.core.pm_session_service import (
    MAX_FILE_LINES,
    MAX_FILE_SIZE_KB,
    PmSessionCheckService,
    PmSessionParser,
)

# 项目根目录（auto_pm 包的父目录）
PROJECT_ROOT = Path(__file__).parent.parent
PM_SESSION_FILE = PROJECT_ROOT / "PM_SESSION_SW-2026-008.md"


@pytest.fixture(scope="module")
def check_result() -> object:
    """运行 PM_SESSION 健康检查"""
    if not PM_SESSION_FILE.exists():
        pytest.skip(f"PM_SESSION 文件不存在: {PM_SESSION_FILE}")
    svc = PmSessionCheckService()
    return svc.check(PM_SESSION_FILE)


class TestPmSessionSizeGate:
    """PM_SESSION 规模门禁元测试"""

    def test_pm_session_file_exists(self) -> None:
        """PM_SESSION 主文件必须存在"""
        assert PM_SESSION_FILE.exists(), f"PM_SESSION 文件不存在: {PM_SESSION_FILE}"

    def test_pm_session_size_under_threshold(self, check_result: object) -> None:
        """PM_SESSION 主文件大小必须 ≤ 150KB"""
        assert check_result.file_size_kb <= MAX_FILE_SIZE_KB, (  # type: ignore[attr-defined]
            f"PM_SESSION 文件大小 {check_result.file_size_kb}KB 超过阈值 {MAX_FILE_SIZE_KB}KB。"  # type: ignore[attr-defined]
            f"请运行 `auto-pm pm-session archive -w . --section 6 --keep-recent 20` 归档早期内容。"
        )

    def test_pm_session_lines_under_threshold(self, check_result: object) -> None:
        """PM_SESSION 主文件行数必须 ≤ 300"""
        assert check_result.total_lines <= MAX_FILE_LINES, (  # type: ignore[attr-defined]
            f"PM_SESSION 文件行数 {check_result.total_lines} 超过阈值 {MAX_FILE_LINES}。"  # type: ignore[attr-defined]
            f"请运行 `auto-pm pm-session archive -w . --section 6 --keep-recent 20` 归档早期内容。"
        )

    def test_pm_session_required_sections_complete(self, check_result: object) -> None:
        """PM_SESSION 必须章节齐全（§0/§1/§2/§3/§4/§5/§6/§8/§9）"""
        assert not check_result.missing_required, (  # type: ignore[attr-defined]
            f"PM_SESSION 缺失必须章节: {sorted(check_result.missing_required)}。"  # type: ignore[attr-defined]
            f"这些章节必须存在，请检查文件结构。"
        )

    def test_pm_session_no_deprecated_sections(self, check_result: object) -> None:
        """PM_SESSION 不应包含已归档章节（§7 应不存在）"""
        assert not check_result.deprecated_present, (  # type: ignore[attr-defined]
            f"PM_SESSION 包含已归档章节: {sorted(check_result.deprecated_present)}。"  # type: ignore[attr-defined]
            f"§7 应该在 CHG-087 Stage 1 中已归档删除，请检查是否回归。"
        )

    def test_pm_session_overall_healthy(self, check_result: object) -> None:
        """PM_SESSION 总体健康检查"""
        assert check_result.is_healthy, (  # type: ignore[attr-defined]
            f"PM_SESSION 不健康，警告: {check_result.warnings}"  # type: ignore[attr-defined]
        )


class TestPmSessionParserOnRealFile:
    """在真实 PM_SESSION 文件上测试解析器"""

    @pytest.fixture(scope="class")
    @classmethod
    def parse_result(cls) -> object:
        if not PM_SESSION_FILE.exists():
            pytest.skip(f"PM_SESSION 文件不存在: {PM_SESSION_FILE}")
        parser = PmSessionParser()
        return parser.parse_file(PM_SESSION_FILE)

    def test_parser_extracts_sections(self, parse_result: object) -> None:
        """解析器应能正确提取所有章节"""
        section_numbers = {s.number for s in parse_result.sections}  # type: ignore[attr-defined]
        # 至少应有 §0 和 §1
        assert "0" in section_numbers
        assert "1" in section_numbers

    def test_parser_section_zero_is_meta(self, parse_result: object) -> None:
        """§0 应该是 Meta"""
        section_0 = parse_result.get_section("0")  # type: ignore[attr-defined]
        assert section_0 is not None
        assert "Meta" in section_0.title

    def test_parser_no_section_seven(self, parse_result: object) -> None:
        """§7 应该不存在（已归档）"""
        section_7 = parse_result.get_section("7")  # type: ignore[attr-defined]
        assert section_7 is None, "§7 应该在 CHG-087 Stage 1 中已归档删除"
