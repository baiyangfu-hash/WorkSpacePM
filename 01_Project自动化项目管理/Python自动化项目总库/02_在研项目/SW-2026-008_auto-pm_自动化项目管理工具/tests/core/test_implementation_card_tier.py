"""TD-SW008-124: a card cannot declare a gate tier lower than the machine classifier computes from its paths."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from auto_pm.application.core.implementation_card_precheck import precheck_markdown_card
from auto_pm.application.core.implementation_card_tier import CLASSIFIER_RELATIVE, declared_tiers
from tests.core.test_implementation_card_precheck import TREE, _card, _messages, _repository

REAL_TOOLS = Path(__file__).resolve().parents[1] / "tools"
PROJECT_DIR = CLASSIFIER_RELATIVE.split("tests/tools/")[0].rstrip("/")
DOC = "04_监控/02_整改项/活动技术债台账.md"  # classifier: docs
PRODUCT = "04_监控/01_变更管理/01_变更单/CHG-SCPT/x.md"  # classifier: product (the incident of cards 099 and 102)
CODE = "auto_pm/application/core/mission_service.py"  # classifier: core


def _world(root: Path, *relatives: str) -> str:
    baseline = _repository(root, tuple(f"{PROJECT_DIR}/{item}" for item in relatives))
    return baseline


def _install_classifier(root: Path) -> None:
    target = root / CLASSIFIER_RELATIVE
    target.parent.mkdir(parents=True, exist_ok=True)
    for name in ("tier_classifier.py", "tier_core_list.json"):
        shutil.copy2(REAL_TOOLS / name, target.parent / name)


def _report(root: Path, declared: str | None, paths: list[str], *, install: bool = True):  # type: ignore[no-untyped-def]
    baseline = _world(root, *paths)
    if install:
        _install_classifier(root)
    header = "" if declared is None else f"> 档次：{declared}\n"
    card = _card(
        root, baseline=baseline, rows=[(p, "存在") for p in paths], path_root=PROJECT_DIR, extra_header=header
    )
    return precheck_markdown_card(card, workspace_root=root, command_tree=TREE)


def _tier_findings(report) -> list:  # type: ignore[no-untyped-def]
    return [item for item in report.findings if item.rule == "tier"]


def test_a_doc_declaration_on_a_product_path_is_refused(tmp_path: Path) -> None:
    report = _report(tmp_path, "文档档；只登记变更单", [DOC, PRODUCT])
    (finding,) = _tier_findings(report)
    assert "文档档" in finding.message and "产品档" in finding.message, _messages(report)
    assert not report.passed


@pytest.mark.parametrize("declared", ["文档档", "测试档", "产品档"])
def test_every_tier_below_the_computed_core_is_refused(tmp_path: Path, declared: str) -> None:
    report = _report(tmp_path, declared, [DOC, CODE])
    assert len(_tier_findings(report)) == 1 and "核心档" in _tier_findings(report)[0].message


@pytest.mark.parametrize("declared", ["**核心档**（分档器：…）", "核心（改产品代码）", "核心档"])
def test_the_computed_tier_or_higher_passes_in_any_of_the_written_forms(tmp_path: Path, declared: str) -> None:
    assert _tier_findings(_report(tmp_path, declared, [DOC, CODE])) == []


def test_a_matching_doc_declaration_passes(tmp_path: Path) -> None:
    assert _tier_findings(_report(tmp_path, "文档档；只改台账一个文件", [DOC])) == []


def test_a_card_without_a_declaration_is_not_judged_here(tmp_path: Path) -> None:
    assert _tier_findings(_report(tmp_path, None, [DOC, CODE])) == []


@pytest.mark.parametrize("declared", ["只改测试；按核心流程跑", "部署演练", ""])
def test_a_declaration_that_names_no_tier_is_refused_not_ignored(tmp_path: Path, declared: str) -> None:
    (finding,) = _tier_findings(_report(tmp_path, declared, [DOC]))
    assert "文档档/测试档/产品档/核心档" in finding.message


def test_a_declared_tier_with_no_classifier_available_is_refused_not_skipped(tmp_path: Path) -> None:
    (finding,) = _tier_findings(_report(tmp_path, "文档档", [DOC], install=False))
    assert "分档器不可用" in finding.message


def test_two_declarations_are_refused(tmp_path: Path) -> None:
    report = _report(tmp_path, "文档档\n> 档次：核心档", [DOC])
    (finding,) = _tier_findings(report)
    assert "只能写一次" in finding.message


def test_runtime_state_paths_are_not_changes_and_do_not_raise_the_tier(tmp_path: Path) -> None:
    baseline = _world(tmp_path, DOC)
    _install_classifier(tmp_path)
    (tmp_path / ".auto-pm").mkdir()
    (tmp_path / ".auto-pm" / "state.db").write_text("x", encoding="utf-8")
    card = _card(
        tmp_path,
        baseline=baseline,
        rows=[(DOC, "存在"), (".auto-pm/state.db", "运行态")],
        path_root=PROJECT_DIR,
        extra_header="> 档次：文档档\n",
    )
    report = precheck_markdown_card(card, workspace_root=tmp_path, command_tree=TREE)
    assert _tier_findings(report) == []


def test_declared_tiers_reads_only_the_header_line() -> None:
    assert declared_tiers(["正文提到 档次：核心档", "> 档次：测试档（规则）"]) == ["tests"]
