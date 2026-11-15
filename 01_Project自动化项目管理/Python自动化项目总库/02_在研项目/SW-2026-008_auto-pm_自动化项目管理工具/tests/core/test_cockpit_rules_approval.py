"""总控屏“等你规则批准”（用户 2026-11-03 要求）：列出改了规则文件、等用户评论“规则批准 <头提交前 12 位>”的 PR。

数据全取自 GitHub 已读的 PR 文件列表和 rules-gate 工作流在当前头提交上的结果；总控屏不重判，只显示。
重点：回复那一行必须是 rules-gate 真的认的写法（用真的 ``rules_approval_check.find_approval`` 验）、推了新提交那一行要跟着换、
没读到（断网、限流、只有缓存）不催你、草稿 PR 不列、等你批准时 rules-gate 的红不再算成作者要修的“门禁红”。
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from tests.core import test_github_collector as g

pytestmark = pytest.mark.external_reads  # D-200: reads real files outside the project

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
REPO_ROOT = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(REPO_ROOT / "reviews" / "tools"))

import github_collector as gh  # noqa: E402
import rules_approval_check as checker  # noqa: E402
from cockpit_board import viewmodel as vm  # noqa: E402

API = g.API
RULES = gh.RULES_WORKFLOW
SHA = {n: f"{n:02x}" * 20 for n in range(0x10, 0x20)}  # 40 位十六进制，每个 PR 一个
NOT_RUN_YET = "rules-gate 还没在当前头提交上跑出结果（刚推送时常见）"


def _pull(number: int, draft: bool = False, sha: str | None = None) -> dict[str, Any]:
    return {
        "number": number, "title": f"PR{number} 的标题", "html_url": f"https://github.com/{g.REPO}/pull/{number}",
        "user": {"login": "claude"}, "head": {"sha": sha or SHA[number], "ref": f"claude/p{number}"}, "draft": draft,
        "updated_at": "2026-10-22T09:00:00Z", "body": "说明",
    }


def _table(pulls: list[dict[str, Any]], files: dict[int, list[dict[str, Any]]], runs: dict[int, list[dict[str, Any]]],
           **override: object) -> dict[str, object]:
    table: dict[str, object] = {
        f"{API}/pulls?state=open&per_page=100": pulls,
        f"{API}/actions/runs?branch=main&event=push&per_page=50": {"workflow_runs": [g._run("sw008-ci", "m", "success", 1)]},
    }
    for pull in pulls:
        number, sha = pull["number"], pull["head"]["sha"]
        table[f"{API}/pulls/{number}/files?per_page=100"] = files.get(number, [{"filename": "docs/x.md"}])
        table[f"{API}/actions/runs?head_sha={sha}&per_page=50"] = {"workflow_runs": runs.get(number, [])}
        table[f"{API}/issues/{number}/comments?per_page=100"] = []
    table.update(override)
    return table


def _gate(sha: str, conclusion: str | None) -> dict[str, Any]:
    return g._run(RULES, sha, conclusion, 7)


def _scenario() -> dict[str, object]:
    pulls = [_pull(n) for n in (0x10, 0x11, 0x12, 0x14, 0x15)] + [_pull(0x13, draft=True)]
    files = {
        0x10: [{"filename": "AGENTS.md"}, {"filename": "docs/y.md"}, {"filename": ".trae/rules/a.md"},
               {"filename": "roles/x/SKILL.md"}],
        0x11: [{"filename": ".trae/rules/a.md"}],
        0x12: [{"filename": "docs/x.md"}],
        0x13: [{"filename": "AGENTS.md"}],
        0x14: [{"filename": "docs/moved.md", "previous_filename": "AGENTS.md", "status": "renamed"}],
        0x15: [{"filename": "roles/a/SKILL.md"}],
    }
    runs = {
        0x10: [_gate(SHA[0x10], "failure")],
        0x11: [_gate(SHA[0x11], "success")],
        0x13: [_gate(SHA[0x13], "failure")],
        0x14: [],  # 刚推送，rules-gate 还没跑出结果
        0x15: [_gate(SHA[0x15], None)],  # 在跑
    }
    return _table(pulls, files, runs)


def _snap(tmp_path: Path, table: dict[str, object] | None = None) -> gh.Snapshot:
    snap = g._collect(tmp_path, g.FakeGitHub(table or _scenario()))
    assert isinstance(snap, gh.Snapshot)
    return snap


def _by_number(snap: gh.Snapshot) -> dict[int, gh.PullInfo]:
    return {p.number: p for p in snap.pulls}


# ---------------------------------------------------------------- 采集：状态


def test_rules_state_per_pull(tmp_path: Path) -> None:
    pulls = _by_number(_snap(tmp_path))
    state = {n: p.rules.state for n, p in pulls.items()}
    assert state == {0x10: "waiting", 0x11: "approved", 0x12: "na", 0x13: "waiting", 0x14: "waiting", 0x15: "running"}
    assert pulls[0x10].rules.files == (".trae/rules/a.md", "AGENTS.md", "roles/x/SKILL.md")  # 只收规则文件，排好序
    assert pulls[0x14].rules.files == ("AGENTS.md",)  # 把规则文件改名搬走也是改它：认旧路径
    assert pulls[0x12].rules.files == ()
    assert pulls[0x14].rules.detail == NOT_RUN_YET  # 还没有 rules-gate 运行记录：说清是刚推送
    assert pulls[0x10].rules.url.endswith("/actions/runs/7")  # 红的那次运行页面


def test_files_not_read_or_runs_not_read_is_unknown_not_na_or_approved(tmp_path: Path) -> None:
    table = _scenario()
    table[f"{API}/pulls/{0x10}/files?per_page=100"] = (500, {}, b"{}")
    table[f"{API}/actions/runs?head_sha={SHA[0x11]}&per_page=50"] = (500, {}, b"{}")
    pulls = _by_number(_snap(tmp_path, table))
    assert pulls[0x10].rules.state == "unknown" and "没读到" in pulls[0x10].rules.detail  # 不知道改了什么：不说“不涉及”
    assert pulls[0x11].rules.state == "unknown" and pulls[0x11].rules.files == (".trae/rules/a.md",)  # 不知道检查结果：不说“已批准”


def test_a_full_page_of_files_without_a_rule_file_is_unknown_not_na(tmp_path: Path) -> None:
    many = [{"filename": f"docs/{i}.md"} for i in range(gh.PER_PAGE)]
    table = _table([_pull(0x10), _pull(0x11)], {0x10: many, 0x11: [*many[:-1], {"filename": "AGENTS.md"}]},
                   {0x11: [_gate(SHA[0x11], "failure")]})
    pulls = _by_number(_snap(tmp_path, table))
    assert pulls[0x10].rules.state == "unknown" and str(gh.PER_PAGE) in pulls[0x10].rules.detail  # 后面可能还有规则文件
    assert pulls[0x11].rules.state == "waiting"  # 已经看到规则文件，看不全也不影响“要批”


@pytest.mark.parametrize(
    ("conclusion", "expected"),
    [("success", "approved"), ("failure", "waiting"), ("cancelled", "waiting"), ("timed_out", "waiting"), (None, "running")],
)
def test_rules_gate_result_maps_to_state(tmp_path: Path, conclusion: str | None, expected: str) -> None:
    table = _table([_pull(0x10)], {0x10: [{"filename": "AGENTS.md"}]}, {0x10: [_gate(SHA[0x10], conclusion)]})
    assert _by_number(_snap(tmp_path, table))[0x10].rules.state == expected


def test_only_the_latest_rules_gate_run_counts(tmp_path: Path) -> None:
    older, newer = g._run(RULES, SHA[0x10], "failure", 7), g._run(RULES, SHA[0x10], "success", 8)
    table = _table([_pull(0x10)], {0x10: [{"filename": "AGENTS.md"}]}, {0x10: [older, newer]})
    assert _by_number(_snap(tmp_path, table))[0x10].rules.state == "approved"
    table = _table([_pull(0x10)], {0x10: [{"filename": "AGENTS.md"}]}, {0x10: [newer, {**older, "run_number": 9,
                    "created_at": "2026-10-22T10:09:00Z"}]})
    assert _by_number(_snap(tmp_path / "b", table))[0x10].rules.state == "waiting"  # 推了新提交又被拦：以最新的为准


def test_rules_survive_the_cache_round_trip(tmp_path: Path) -> None:
    snap = _snap(tmp_path)
    again = g._collect(tmp_path, None, offline=True)  # 离线：从本机缓存读
    assert again.from_cache and not again.fresh
    cached = _by_number(again)
    assert cached[0x10].rules == _by_number(snap)[0x10].rules and isinstance(cached[0x10].rules.files, tuple)


# ---------------------------------------------------------------- D-364：rules-gate 进了应跑名单以后，那句话不变


def test_d364_rules_gate_expected_but_not_run_yet_keeps_the_same_sentence(tmp_path: Path) -> None:
    g._repo_with_targets(tmp_path, (RULES,))
    table = _table([_pull(0x14)], {0x14: [{"filename": "AGENTS.md"}]}, {0x14: []})
    snap = _snap(tmp_path, table)
    pull = _by_number(snap)[0x14]
    check = next(c for c in pull.ci if c.workflow == RULES)
    assert (check.state, check.detail) == ("notrun", "应跑没跑")  # 检查清单里照实多出这一项
    assert pull.rules.state == "waiting" and pull.rules.detail == NOT_RUN_YET  # 不是“没批准”，是还没跑
    assert "应跑没跑" not in pull.rules.detail and "评论里还没有你" not in pull.rules.detail
    assert pull.gate == "notrun"  # 合起来的门禁不因为这一项算红（不是 fail）
    row = vm.github_vm(snap, g.NOW, g.OFFSET).rows[0]
    assert (row.rules.text, row.rules.sev, row.rules.tip) == ("等你批准", "block", NOT_RUN_YET)
    assert row.gate.sev != "block"
    assert not [i for i in vm.github_issues(snap) if f"#{0x14} " in i.title]


def test_d364_rules_gate_really_red_keeps_the_not_approved_sentence(tmp_path: Path) -> None:
    g._repo_with_targets(tmp_path, (RULES,))
    table = _table([_pull(0x10)], {0x10: [{"filename": "AGENTS.md"}]}, {0x10: [_gate(SHA[0x10], "failure")]})
    pull = _by_number(_snap(tmp_path, table))[0x10]
    assert pull.rules.state == "waiting"
    assert pull.rules.detail == "rules-gate 红：评论里还没有你对当前头提交的批准"  # 真跑了、真红：原来那一支没改坏
    skipped = _table([_pull(0x10)], {0x10: [{"filename": "AGENTS.md"}]}, {0x10: [_gate(SHA[0x10], "skipped")]})
    g._repo_with_targets(tmp_path / "b", (RULES,))
    other = _by_number(_snap(tmp_path / "b", skipped))[0x10]
    assert other.rules.detail == "rules-gate 没跑（skipped）：评论里还没有你对当前头提交的批准"  # 真跑了但结论是跳过一类的：不算“还没跑”，照旧走后面的分支


# ---------------------------------------------------------------- 门禁：等你批准的红不算作者要修的红


def test_waiting_rules_gate_is_not_a_red_gate_for_the_author(tmp_path: Path) -> None:
    pulls = _by_number(_snap(tmp_path))
    waiting = pulls[0x10]
    assert any(c.workflow == RULES and c.state == "fail" for c in waiting.ci)  # 原始检查仍是红，画面上还看得到
    assert waiting.gate != "fail"
    issues = vm.github_issues(_snap(tmp_path / "again"))
    assert not [i for i in issues if f"#{0x10} " in i.title]  # 问题页不为它报“门禁红”（那是你要批准，不是作者要修）


def test_a_real_red_check_still_makes_the_gate_red_and_names_only_that_check(tmp_path: Path) -> None:
    runs = {0x10: [_gate(SHA[0x10], "failure"), g._run("sw008-ci", SHA[0x10], "failure", 2)]}
    files = {0x10: [{"filename": "AGENTS.md"}, {"filename": g.SW8_FILE}]}
    pull = _by_number(_snap(tmp_path, _table([_pull(0x10)], files, runs)))[0x10]
    assert pull.rules.state == "waiting" and pull.gate == "fail"
    issues = vm.github_issues(_snap(tmp_path / "x", _table([_pull(0x10)], files, runs)))
    assert len(issues) == 1 and "sw008-ci" in issues[0].detail and RULES not in issues[0].detail


def test_rules_gate_red_on_a_pull_that_touches_no_rule_file_is_still_a_red_gate(tmp_path: Path) -> None:
    """没改规则文件却红了 = 检查自己出错（取不到评论等），是真红，不能被当成“等你批准”藏起来。"""
    pull = _by_number(_snap(tmp_path, _table([_pull(0x10)], {}, {0x10: [_gate(SHA[0x10], "failure")]})))[0x10]
    assert pull.rules.state == "na" and pull.gate == "fail"


# ---------------------------------------------------------------- 要你出手的列表


def _rule_decisions(snap: gh.Snapshot) -> list[vm.Decision]:
    return [d for d in vm.github_decisions(snap) if "规则批准" in d.ask]


def test_decisions_list_only_ready_pulls_that_wait_and_carry_number_title_state_link(tmp_path: Path) -> None:
    snap = _snap(tmp_path)
    found = _rule_decisions(snap)
    assert [d.ask for d in found] == [f"PR #{n} 等你规则批准" for n in (0x10, 0x14, 0x15)]  # 草稿 #19 不列，已批准的 #17 不列
    first = found[0]
    assert "PR16 的标题" in first.why and "AGENTS.md" in first.why and "等 3 个" in first.why  # 标题、规则文件
    assert "rules-approval 检查：红" in first.why and "审计：" in first.why
    assert first.link == f"https://github.com/{g.REPO}/pull/{0x10}"  # PR 链接
    assert first.reply == f"规则批准 {SHA[0x10][:12]}" and first.sev == "block"
    assert "在跑" in found[2].why  # 评论后检查重跑期间仍在，直到变绿才消失


def test_the_reply_line_is_what_rules_gate_accepts_for_the_current_head(tmp_path: Path) -> None:
    """把总控屏给的那一行，当成用户的评论交给真的判卷函数：必须通过；只要有一位对不上就不行。"""
    for decision in _rule_decisions(_snap(tmp_path)):
        number = int(decision.ask.split("#")[1].split()[0])
        head = SHA[number]
        comment = {"body": decision.reply, "user": {"login": "baiyangfu-hash", "id": 246858089},
                   "created_at": "2026-11-03T10:00:00Z", "updated_at": "2026-11-03T10:00:00Z"}
        result = checker.Result()
        assert checker.find_approval([comment], head, result) is not None, (decision.reply, result.notes)
        assert checker.find_approval([{**comment, "body": decision.reply[:-1]}], head, checker.Result()) is None  # 少一位判卷不认
        assert len(decision.reply.split()[1]) == checker.MIN_SIGN_LEN == gh.RULES_SIGN_LEN
        # 换一个头提交（作者又推了）：同一句话作废
        assert checker.find_approval([comment], "f" * 40, checker.Result()) is None


def test_the_line_changes_when_the_author_pushes_a_new_commit(tmp_path: Path) -> None:
    before = _rule_decisions(_snap(tmp_path / "a", _table([_pull(0x10)], {0x10: [{"filename": "AGENTS.md"}]},
                                                          {0x10: [_gate(SHA[0x10], "failure")]})))[0]
    new = "ab" * 20
    after = _rule_decisions(_snap(tmp_path / "b", _table([_pull(0x10, sha=new)], {0x10: [{"filename": "AGENTS.md"}]},
                                                         {0x10: [_gate(new, "failure")]})))[0]
    assert before.reply == f"规则批准 {SHA[0x10][:12]}" and after.reply == f"规则批准 {new[:12]}" != before.reply


def test_nothing_is_listed_from_old_or_missing_data(tmp_path: Path) -> None:
    _snap(tmp_path)
    cached = g._collect(tmp_path, None, offline=True)
    assert not cached.fresh and cached.pulls and _rule_decisions(cached) == []  # 旧数据不催你
    assert vm.github_decisions(None) == []
    row = vm.github_vm(cached, g.NOW, g.OFFSET).rows[0]
    assert row.rules.text == "未知" and row.rules.sev == "na"  # 不显示“已批准”绿，也不显示“等你批准”


def test_drafts_are_counted_in_the_github_notes_not_listed(tmp_path: Path) -> None:
    snap = _snap(tmp_path)
    github = vm.github_vm(snap, g.NOW, g.OFFSET)
    assert any("草稿 PR #19" in note and "转成可审" in note for note in github.notes)
    assert not any("草稿 PR" in note for note in vm.github_vm(_snap(tmp_path / "n", _table([_pull(0x10)], {}, {})), g.NOW, g.OFFSET).notes)


def test_pr_rows_show_the_rules_cell(tmp_path: Path) -> None:
    rows = {r.number: r for r in vm.github_vm(_snap(tmp_path), g.NOW, g.OFFSET).rows}
    assert (rows[0x10].rules.text, rows[0x10].rules.sev) == ("等你批准", "block")
    assert (rows[0x11].rules.text, rows[0x11].rules.sev) == ("已批准", "ok")
    assert (rows[0x12].rules.text, rows[0x12].rules.sev) == ("不涉及", "na")
    assert (rows[0x15].rules.text, rows[0x15].rules.sev) == ("检查在跑", "hint")


def test_home_decisions_include_the_rule_prs(tmp_path: Path) -> None:
    home = g._home(tmp_path, _snap(tmp_path / "s"))
    assert {d.ask for d in home.decisions if "规则批准" in d.ask} == {f"PR #{n} 等你规则批准" for n in (0x10, 0x14, 0x15)}


# ---------------------------------------------------------------- 安全签字的那一行也要够长（同类排查）


def test_the_safety_signature_line_is_long_enough_for_the_gate(tmp_path: Path) -> None:
    snap = g._collect(tmp_path, g.FakeGitHub(g.routes()))
    decision = next(d for d in vm.github_decisions(snap) if "安全签字" in d.ask)
    assert decision.reply == f"安全签字 {g.SHA1[:gh.MIN_SIGN_LEN]}" and len(decision.reply.split()[1]) >= 12
    comment = {"body": decision.reply, "user": {"login": "baiyangfu-hash", "id": 246858089}, "html_url": "c",
               "created_at": "2026-10-22T10:00:00Z", "updated_at": "2026-10-22T10:00:00Z"}
    assert gh.find_signature([comment], g.SHA1)[0] is not None  # 判卷函数认这句话
    assert decision.link


# ---------------------------------------------------------------- 与 GitHub 上那份判卷保持一致


def test_rule_patterns_and_words_match_the_judge() -> None:
    assert gh.RULE_PATTERNS == checker.RULE_PATTERNS  # 清单只有一份真源，总控屏这份是抄的：对不上就红
    assert gh.RULES_APPROVE_WORD == checker.APPROVE_WORD and gh.RULES_SIGN_LEN == checker.MIN_SIGN_LEN
    for path in ("AGENTS.md", ".trae/skills/a/SKILL.md", ".github/workflows/x.yml", "reviews/tools/a.py", "roles/x/SKILL.md",
                 "00_Obsidian_Base全局规范文件仓库/a.md", "docs/a.md", "AGENTS.md.bak", "x/AGENTS.md", "README.md"):
        assert gh.is_rule_file(path) == checker.is_rule_file(path), path


def test_the_judge_workflow_is_still_named_rules_gate() -> None:
    text = (REPO_ROOT / ".github" / "workflows" / "rules-gate.yml").read_text(encoding="utf-8")
    assert f"\nname: {gh.RULES_WORKFLOW}\n" in text  # 总控屏按这个名字找运行结果


# ---------------------------------------------------------------- 小部件


@pytest.fixture
def qapp() -> Any:
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_the_card_shows_the_line_and_the_pr_link_with_copy_buttons(qapp: Any, tmp_path: Path) -> None:
    from cockpit_board.widgets.home import decision_card
    from PySide6.QtWidgets import QLabel, QPushButton

    decision = _rule_decisions(_snap(tmp_path))[0]
    copied: list[str] = []
    card = decision_card(decision, datetime(2026, 10, 22, 12, 0, tzinfo=g.NOW.tzinfo), lambda _pid: None, copied.append)
    texts = [label.text() for label in card.findChildren(QLabel)]
    assert decision.ask in texts and decision.reply in texts and decision.link in texts  # 号、整句、链接都看得见
    assert "在 PR 页面评论这一行：" in texts and "PR 页面：" in texts
    buttons = {b.text(): b for b in card.findChildren(QPushButton)}
    buttons["复制"].click()
    buttons["复制链接"].click()
    assert copied == [decision.reply, decision.link]  # 复制的就是那一整句 / 那条网址，没有多余字


def test_cards_without_a_link_keep_the_thread_wording(qapp: Any) -> None:
    from cockpit_board.widgets.home import decision_card
    from PySide6.QtWidgets import QLabel, QPushButton

    plain = vm.Decision("risk", "DJ-2026-009", "要你定的事", "原因", "同意", "依据", None)
    card = decision_card(plain, g.NOW, lambda _pid: None, lambda _text: None)
    assert "在线程里回一句：" in [label.text() for label in card.findChildren(QLabel)]
    assert "复制链接" not in [b.text() for b in card.findChildren(QPushButton)]
