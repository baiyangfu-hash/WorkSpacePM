"""TD-SW008-124: a card cannot declare a gate tier lower than the machine classifier computes from its paths."""

from __future__ import annotations

import shutil
from pathlib import Path
from subprocess import TimeoutExpired

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


def _commit_card(root: Path, when: str | None = None) -> str:
    """Commit card.md (optionally with a forged commit date) and return the new commit."""
    import os
    import subprocess

    env = dict(os.environ)
    if when:
        env.update(GIT_COMMITTER_DATE=when, GIT_AUTHOR_DATE=when)
    subprocess.run(["git", "-C", str(root), "add", "card.md"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-m", "card"],
        check=True,
        capture_output=True,
        env=env,
    )
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True, encoding="utf-8", errors="replace"
    ).stdout.strip()


def _freeze(monkeypatch: pytest.MonkeyPatch, commit: str) -> None:
    monkeypatch.setattr("auto_pm.application.core.implementation_card_tier.CARD_TIER_FROZEN_COMMIT", commit)


def _recheck(root: Path):  # type: ignore[no-untyped-def]
    return precheck_markdown_card(root / "card.md", workspace_root=root, command_tree=TREE)


def test_a_new_card_without_a_declaration_is_refused(tmp_path: Path) -> None:
    (finding,) = _tier_findings(_report(tmp_path, None, [DOC, CODE]))  # card.md was never committed: new
    assert "新卡头部必须写" in finding.message


def test_a_card_in_the_frozen_commit_without_a_declaration_is_exempt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _report(tmp_path, None, [DOC])
    _freeze(monkeypatch, _commit_card(tmp_path))
    assert _tier_findings(_recheck(tmp_path)) == []


def test_a_card_added_in_the_commit_right_after_the_frozen_one_is_new(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = _world(tmp_path, DOC)
    _freeze(monkeypatch, baseline)  # the boundary: the frozen commit is the baseline, the card arrives one commit later
    _install_classifier(tmp_path)
    _card(tmp_path, baseline=baseline, rows=[(DOC, "存在")], path_root=PROJECT_DIR)
    _commit_card(tmp_path)
    (finding,) = _tier_findings(_recheck(tmp_path))
    assert "新卡头部必须写" in finding.message


def test_a_forged_old_commit_date_does_not_make_a_card_old(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = _world(tmp_path, DOC)
    _freeze(monkeypatch, baseline)
    _install_classifier(tmp_path)
    _card(tmp_path, baseline=baseline, rows=[(DOC, "存在")], path_root=PROJECT_DIR)
    _commit_card(tmp_path, "2020-01-01T00:00:00+00:00")
    assert len(_tier_findings(_recheck(tmp_path))) == 1


def test_a_card_that_has_a_declaration_is_judged_even_when_it_is_old(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _report(tmp_path, "文档档", [DOC, CODE])
    _freeze(monkeypatch, _commit_card(tmp_path))
    assert len(_tier_findings(_recheck(tmp_path))) == 1


def test_a_frozen_commit_that_cannot_be_read_counts_as_new(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from auto_pm.application.core.implementation_card_tier import card_is_new

    _report(tmp_path, None, [DOC])
    _commit_card(tmp_path)
    _freeze(monkeypatch, "0" * 40)  # no such commit (a shallow clone looks like this)
    assert card_is_new(tmp_path / "card.md") is True


def test_a_card_outside_any_repository_counts_as_new(tmp_path: Path) -> None:
    from auto_pm.application.core.implementation_card_tier import card_is_new

    loose = tmp_path / "not-a-repo"
    loose.mkdir()
    (loose / "card.md").write_text("x\n", encoding="utf-8")
    assert card_is_new(loose / "card.md") is True


@pytest.mark.parametrize("failure", [FileNotFoundError("git"), OSError("blocked"), TimeoutExpired(["git"], 60)])
def test_a_git_that_is_missing_or_hangs_counts_as_new_not_as_old(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    from auto_pm.application.core import implementation_card_tier as tier

    _report(tmp_path, None, [DOC])
    _freeze(monkeypatch, _commit_card(tmp_path))
    assert tier.card_is_new(tmp_path / "card.md") is False  # sanity: without the failure the card is old

    def broken(*_args: object, **_kwargs: object) -> None:
        raise failure

    monkeypatch.setattr(tier.subprocess, "run", broken)
    assert tier.card_is_new(tmp_path / "card.md") is True
    (finding,) = _tier_findings(_recheck(tmp_path))
    assert "新卡头部必须写" in finding.message


def test_the_placeholder_in_the_cockpit_card_template_must_be_filled_in(tmp_path: Path) -> None:
    template = Path(__file__).resolve().parents[2] / "auto_pm" / "templates" / "governance" / "implementation_card.md.jinja"
    line = next(row for row in template.read_text(encoding="utf-8").splitlines() if row.startswith("> 档次"))
    (finding,) = _tier_findings(_report(tmp_path, line.removeprefix("> 档次：").strip(), [DOC]))
    assert "文档档/测试档/产品档/核心档" in finding.message  # TODO is not a tier name: refused until filled


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
