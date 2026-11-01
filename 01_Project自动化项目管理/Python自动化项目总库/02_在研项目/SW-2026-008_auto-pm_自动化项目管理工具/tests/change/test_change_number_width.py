"""变更单号的序号位数：到 1000 以后不能被读成前三位，也不能被拒收（TD 候选，P3，预防性）。

根因：``CHG-<领域>-<年>-<序号>`` 的正则被复制粘贴了十几处，序号都写成固定的 ``\\d{3}``。取号函数
（``file_locator.generate_change_number``）用 ``{:03d}`` 补零，序号到 1000 时会生成四位的 ``CHG-SCPT-2026-1000``；这时：

* 没有收尾锚点的正则只取前三位，得到 ``CHG-SCPT-2026-100``，那是另一张真实存在的变更单；
* 有收尾锚点的正则则直接不认。

这里用真实函数各过一遍四位序号，再加一条棘轮：``auto_pm`` 包和测试工具里不得再出现序号固定三位的变更单号正则。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from auto_pm.application.core.chg_tracking_service import _CHG_NAME
from auto_pm.application.core.pm_resume_service import PmResumeService
from auto_pm.contracts import intake
from auto_pm.contracts.decision_package import RUNTIME_CHANGE_ID_PATTERN
from auto_pm.domain.change import ledger_reconciler, path_resolver
from auto_pm.domain.change.parser import ChgParser

ROOT = Path(__file__).resolve().parents[2]
FOUR = "CHG-SCPT-2026-1000"
THREE = "CHG-SCPT-2026-999"


@pytest.mark.parametrize("number", [THREE, FOUR, "CHG-SCPT-2026-12345"])
def test_the_parser_reads_the_whole_sequence(number: str) -> None:
    parser = ChgParser()
    assert parser._extract_change_number(f"/x/{number}.md") == number
    assert parser._extract_change_number_from_content(f"| 变更编号 | {number} |") == number


def test_the_ledger_reconciler_does_not_cut_a_four_digit_sequence() -> None:
    assert ledger_reconciler._CHANGE_NUMBER_RE.findall(f"| {FOUR} | {THREE} |") == [FOUR, THREE]
    assert ledger_reconciler._CHANGE_NUMBER_RE.fullmatch(FOUR)


def test_the_path_resolver_accepts_a_four_digit_sequence() -> None:
    assert path_resolver._CHANGE_NUMBER_PATTERN.match(FOUR)
    assert path_resolver._CHANGE_NUMBER_PATTERN.match(THREE)
    assert not path_resolver._CHANGE_NUMBER_PATTERN.match("CHG-SCPT-2026-99")


def test_the_change_file_name_pattern_accepts_a_four_digit_sequence() -> None:
    assert _CHG_NAME.match(f"{FOUR}.md")
    assert _CHG_NAME.match(f"{THREE}.md")
    assert not _CHG_NAME.match("CHG-SCPT-2026-99.md")


def test_the_resume_report_matches_the_whole_number() -> None:
    class Change:
        def __init__(self, number: str) -> None:
            self.change_number = number

    # 报告里只提到 1000 号；被截成 100 号就会把另一张真实存在的单当成“正在做的”。
    known = [Change(FOUR), Change("CHG-SCPT-2026-100")]
    assert PmResumeService._active_changes(f"见 {FOUR}", known) == [FOUR]


def test_intake_accepts_a_four_digit_change_number() -> None:
    assert intake._CHG_ID.fullmatch(FOUR)
    assert intake._DUPLICATE_REF.fullmatch(FOUR)
    assert not intake._CHG_ID.fullmatch("CHG-SCPT-2026-99")


def test_the_decision_package_accepts_a_four_digit_change_number() -> None:
    assert RUNTIME_CHANGE_ID_PATTERN.fullmatch(FOUR)
    assert not RUNTIME_CHANGE_ID_PATTERN.fullmatch("CHG-SCPT-2026-99")


_FIXED_THREE = re.compile(r"(?:\\d|\[0-9\])\{\{?3\}\}?(?!,)")


def test_no_change_number_pattern_fixes_the_sequence_at_three_digits() -> None:
    """棘轮：包含 ``CHG-`` 的行里不得出现固定三位的 ``\\d{3}`` / ``[0-9]{3}``（写 ``{3,}``）。"""
    offenders: list[str] = []
    files = [*(ROOT / "auto_pm").rglob("*.py"), *(ROOT / "tests" / "tools").rglob("*.py"), *(ROOT / "tests" / "e2e").rglob("*.py")]
    for path in files:
        if path == Path(__file__):
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "CHG-" in line and _FIXED_THREE.search(line):
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{number}: {line.strip()[:100]}")
    assert offenders == [], "变更单号的序号位数要写 {3,}，不要固定三位:\n" + "\n".join(offenders)
