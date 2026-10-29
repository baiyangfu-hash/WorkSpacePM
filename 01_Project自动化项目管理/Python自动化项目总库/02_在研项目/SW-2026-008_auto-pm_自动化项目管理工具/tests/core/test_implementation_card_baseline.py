"""TD-SW008-125: a card that changes a test the Linux CI baseline lists must refresh the baseline in the same card (or state an exception)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_pm.application.core.implementation_card_baseline import (
    BASELINE_RELATIVE,
    PROJECT_RELATIVE,
)
from auto_pm.application.core.implementation_card_precheck import (
    PrecheckReport,
    precheck_markdown_card,
)
from tests.core.test_implementation_card_precheck import TREE, _card, _repository

LISTED = "tests/cli/test_listed.py"
OTHER = "tests/cli/test_other.py"
BASELINE_IN_PROJECT = "tests/tools/sw008_ci/baseline.linux.json"


def _report(
    root: Path,
    rows: list[str],
    *,
    baseline_ids: list[str] | None = None,
    baseline_text: str | None = None,
    header: str = "",
) -> PrecheckReport:
    files = tuple(f"{PROJECT_RELATIVE}/{item}" for item in (*rows, BASELINE_IN_PROJECT))
    commit = _repository(root, files)
    if baseline_text is not None or baseline_ids is not None:
        text = baseline_text if baseline_text is not None else json.dumps({"ids": baseline_ids})
        (root / BASELINE_RELATIVE).write_text(text, encoding="utf-8")
    elif (root / BASELINE_RELATIVE).exists():
        (root / BASELINE_RELATIVE).unlink()
    card = _card(root, baseline=commit, rows=[(item, "存在") for item in rows], path_root=PROJECT_RELATIVE, extra_header=header)
    return precheck_markdown_card(card, workspace_root=root, command_tree=TREE)


def _baseline(report: PrecheckReport) -> list[str]:
    return [item.message for item in report.findings if item.rule == "baseline"]


def test_fixing_a_baseline_listed_test_without_refreshing_the_baseline_is_refused(tmp_path: Path) -> None:
    report = _report(tmp_path, [LISTED], baseline_ids=[f"{LISTED}::test_known_failure"])

    assert not report.passed
    assert len(_baseline(report)) == 1 and LISTED in _baseline(report)[0] and "基线例外" in _baseline(report)[0]


def test_the_same_card_that_also_lists_the_baseline_file_passes(tmp_path: Path) -> None:
    report = _report(tmp_path, [LISTED, BASELINE_IN_PROJECT], baseline_ids=[f"{LISTED}::test_known_failure"])

    assert _baseline(report) == []


def test_a_stated_exception_passes(tmp_path: Path) -> None:
    report = _report(
        tmp_path, [LISTED], baseline_ids=[f"{LISTED}::test_known_failure"], header="> 基线例外：只改注释，测试结果不变\n"
    )

    assert _baseline(report) == []


def test_an_empty_exception_reason_does_not_count(tmp_path: Path) -> None:
    report = _report(tmp_path, [LISTED], baseline_ids=[f"{LISTED}::test_known_failure"], header="> 基线例外：\n")

    assert len(_baseline(report)) == 1


def test_a_test_that_is_not_in_the_baseline_is_not_judged(tmp_path: Path) -> None:
    report = _report(tmp_path, [OTHER], baseline_ids=[f"{LISTED}::test_known_failure"])

    assert _baseline(report) == []


def test_an_empty_baseline_judges_nothing(tmp_path: Path) -> None:
    report = _report(tmp_path, [LISTED], baseline_ids=[])

    assert _baseline(report) == []


def test_a_repository_without_a_baseline_file_judges_nothing(tmp_path: Path) -> None:
    report = _report(tmp_path, [LISTED])

    assert _baseline(report) == []


@pytest.mark.parametrize("text", ["{not json", '{"ids": "nope"}', '{"ids": [1]}', "{}"], ids=["syntax", "not-a-list", "not-strings", "no-ids"])
def test_an_unreadable_baseline_is_refused_when_the_card_changes_a_test_not_skipped(tmp_path: Path, text: str) -> None:
    report = _report(tmp_path, [LISTED], baseline_text=text)

    assert len(_baseline(report)) == 1 and "读不出" in _baseline(report)[0]


def test_a_card_that_changes_no_test_never_reads_the_baseline(tmp_path: Path) -> None:
    report = _report(tmp_path, ["auto_pm/application/core/x.py"], baseline_text="{not json")

    assert _baseline(report) == []
