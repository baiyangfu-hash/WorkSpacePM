"""``main.py pr open`` (WS-001, X05 card C): every refusal happens before anything leaves the machine, and nothing is merged.

Each test reuses the throwaway GitHub stand-in of the station tests (a bare ``origin``, a control root cloned from it,
a helper clone).  ``gh`` is a recording fake; the scope judge is the real ``reviews/tools/pr_scope_check.py`` in the
integration tests and a stub elsewhere.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest
from click.testing import CliRunner

from auto_pm.application.core.agent_worktree_service import AgentWorktreeError
from auto_pm.application.core.pr_open_service import (
    PrOpenRefusedError,
    PrOpenService,
)
from auto_pm.ui.cli.__main__ import cli
from tests.core.test_agent_worktree_service import AGENT_MARKER_KEYS, Lab, commit, git

PROJECT = Path(__file__).resolve().parents[2]
REPO = PROJECT.parents[3]
REAL_JUDGE = REPO / "reviews" / "tools" / "pr_scope_check.py"
CARD_PATH = "cards/CARD-1.md"
CARD_TEXT = (
    "# CARD-1｜演示卡\n\n> 安全回路：否\n> 隔离基线：`WORKTREE`\n> 路径根：`.`\n\n## Owned Paths\n\n"
    "| # | 路径 | 基线状态 |\n|---|---|---|\n| 1 | `work/done.txt` | 计划新增 |\n"
)
CHG = "CHG-SCPT-2026-777"
ALLOWED_GH = {("auth", "status"), ("pr", "list"), ("pr", "create")}


class FakeGh:
    """Records every call; answers like a logged-in ``gh`` unless told otherwise."""

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], str | None]] = []
        self.logged_in = True
        self.open_prs = "[]"

    def __call__(self, args: Sequence[str], stdin: str | None) -> subprocess.CompletedProcess[str]:
        self.calls.append((tuple(args), stdin))
        key = tuple(args[:2])
        if key == ("auth", "status"):
            code = 0 if self.logged_in else 1
            return subprocess.CompletedProcess(args, code, "", "" if code == 0 else "not logged in")
        if key == ("pr", "list"):
            return subprocess.CompletedProcess(args, 0, self.open_prs, "")
        if key == ("pr", "create"):
            return subprocess.CompletedProcess(args, 0, "https://github.com/o/r/pull/101\n", "")
        return subprocess.CompletedProcess(args, 1, "", f"unexpected gh call {args}")

    def used(self) -> set[tuple[str, ...]]:
        return {call[0][:2] for call in self.calls}


def passing_judge(station: Path, base: str, head: str, body: str) -> tuple[int, str]:
    return 0, "ok"


@pytest.fixture
def lab(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Lab:
    for key in list(os.environ):
        if key in AGENT_MARKER_KEYS or key.upper().startswith("CODEX_"):
            monkeypatch.delenv(key, raising=False)
    lab = Lab(tmp_path)
    (lab.github / "cards").mkdir()
    (lab.github / CARD_PATH).write_text(CARD_TEXT, encoding="utf-8")
    git(lab.github, "add", "cards")
    git(lab.github, "commit", "-q", "-m", "add card")
    git(lab.github, "push", "-q", "origin", "main")
    git(lab.root, "pull", "-q", "origin", "main")
    return lab


def work(lab: Lab, agent: str = "claude", card: str = "CARD-1", message: str | None = None) -> Path:
    """Open a station and commit one file in it; the commit message carries a CHG number by default."""

    lab.service().open(agent, card)
    station = lab.station(agent)
    (station / "work").mkdir()
    (station / "work" / "done.txt").write_text("x\n", encoding="utf-8")
    git(station, "add", "work")
    git(station, "commit", "-q", "-m", message or f"feat: [{CHG}] do the card")
    return station


def service(lab: Lab, gh: FakeGh | None = None, **kwargs: object) -> PrOpenService:
    kwargs.setdefault("judge", passing_judge)
    kwargs.setdefault("sleep", lambda _s: None)
    return PrOpenService(lab.root, gh=gh or FakeGh(), **kwargs)  # type: ignore[arg-type]


def plan(lab: Lab, svc: PrOpenService | None = None, **kwargs: object):  # noqa: ANN201
    return (svc or service(lab)).plan("claude", "CARD-1", CARD_PATH, fetch=False, **kwargs)  # type: ignore[arg-type]


# ── plan: what the PR will say ──────────────────────────────────────


def test_plan_fills_branch_title_card_line_and_chg(lab: Lab) -> None:
    work(lab)
    result = plan(lab, evidence=["pytest tests/core => 0"])

    assert result.branch == "claude/CARD-1"
    assert result.title == "[CARD-1] CARD-1｜演示卡"
    assert result.chg_numbers == (CHG,)
    assert f"任务卡: {CARD_PATH}" in result.body.splitlines()
    assert CHG in result.body and "pytest tests/core => 0" in result.body
    assert "待登记" not in result.body and "to be registered" not in result.body.lower()


def test_plan_without_evidence_says_so_instead_of_claiming_it(lab: Lab) -> None:
    work(lab)
    assert "未提供" in plan(lab).body


def test_plan_sends_nothing_and_asks_gh_nothing(lab: Lab) -> None:
    work(lab)
    gh = FakeGh()
    before = lab.remote_refs()
    plan(lab, service(lab, gh))
    assert lab.remote_refs() == before, "--dry-run 路径不能推送"
    assert gh.calls == []


def test_plan_notes_commits_without_a_chg_number(lab: Lab) -> None:
    station = work(lab)
    commit(station, "second.txt")  # message "add second.txt": no CHG
    result = plan(lab)
    assert result.chg_numbers == (CHG,)
    assert any("没有 CHG 号" in note for note in result.notes)


# ── plan: refusals ──────────────────────────────────────────────────


def test_refuses_when_branch_is_not_prefix_plus_card(lab: Lab) -> None:
    work(lab, card="OTHER-9")
    with pytest.raises(PrOpenRefusedError, match="分支名不符"):
        plan(lab)


def test_refuses_when_no_commit_carries_a_chg_number(lab: Lab) -> None:
    work(lab, message="feat: do the card")
    with pytest.raises(PrOpenRefusedError, match="没有 CHG 号"):
        plan(lab)


@pytest.mark.parametrize(
    "wording",
    [
        "CHG to be registered",
        "CHG 待登记",
        "CHG: TBD",
        "CHG pending",
        "CHG 待申请",
        "CHG: TBA",
        "CHG\u3000待登记",
        "CHG-SCPT-２０２６-４５１",
        "chg-scpt-2026-451",
        "CHG-SCPT-2026-45",
        "\uff23\uff28\uff27 待登记",
    ],
)
def test_refuses_a_chg_placeholder_even_next_to_a_real_number(lab: Lab, wording: str) -> None:
    work(lab, message=f"feat: [{CHG}] do the card\n\n{wording}")
    with pytest.raises(PrOpenRefusedError, match="不是合格的号"):
        plan(lab)


def test_refuses_uncommitted_changes(lab: Lab) -> None:
    station = work(lab)
    (station / "work" / "late.txt").write_text("late\n", encoding="utf-8")
    with pytest.raises(PrOpenRefusedError, match="未提交"):
        plan(lab)


def test_refuses_when_there_is_nothing_to_hand_in(lab: Lab) -> None:
    lab.service().open("claude", "CARD-1")
    with pytest.raises(PrOpenRefusedError, match="没有新提交"):
        plan(lab)


def test_refuses_without_a_station(lab: Lab) -> None:
    with pytest.raises(PrOpenRefusedError, match="没有登记的工位"):
        plan(lab)


def test_refuses_a_task_card_that_is_not_on_main(lab: Lab) -> None:
    work(lab)
    with pytest.raises(PrOpenRefusedError, match="不存在"):
        service(lab).plan("claude", "CARD-1", "cards/missing.md", fetch=False)


@pytest.mark.parametrize("bad", ["../escape.md", "/abs/card.md", "C:/card.md", ""])
def test_refuses_task_card_paths_outside_the_repository(lab: Lab, bad: str) -> None:
    work(lab)
    with pytest.raises(PrOpenRefusedError, match="相对路径"):
        service(lab).plan("claude", "CARD-1", bad, fetch=False)


def test_refuses_when_the_judge_fails_and_shows_its_report(lab: Lab) -> None:
    work(lab)

    def failing(station: Path, base: str, head: str, body: str) -> tuple[int, str]:
        return 1, "越界：`x` 不在允许范围内"

    with pytest.raises(PrOpenRefusedError, match="越界：`x`"):
        plan(lab, service(lab, judge=failing))


def test_judge_gets_the_body_with_the_card_line_and_the_exact_range(lab: Lab) -> None:
    station = work(lab)
    seen: list[tuple[Path, str, str, str]] = []

    def spy(path: Path, base: str, head: str, body: str) -> tuple[int, str]:
        seen.append((path, base, head, body))
        return 0, ""

    plan(lab, service(lab, judge=spy))
    path, base, head, body = seen[0]
    assert path == station
    assert base == git(lab.root, "rev-parse", "refs/remotes/origin/main")
    assert head == git(station, "rev-parse", "HEAD")
    assert f"任务卡: {CARD_PATH}" in body


def test_unreadable_judge_script_is_a_refusal_not_a_pass(lab: Lab) -> None:
    work(lab)
    svc = PrOpenService(
        lab.root, gh=FakeGh(), sleep=lambda _s: None
    )  # real judge, no script in the lab root
    with pytest.raises(PrOpenRefusedError, match="越界检查不通过"):
        svc.plan("claude", "CARD-1", CARD_PATH, fetch=False)


@pytest.mark.parametrize(
    ("env", "message"),
    [({"AUTO_PM_AGENT": "trae"}, "不能替 claude 开 PR"), ({"AUTO_PM_AGENT": "nobody"}, "认不出")],
)
def test_refuses_another_agent_or_an_unknown_caller(
    lab: Lab, monkeypatch: pytest.MonkeyPatch, env: dict[str, str], message: str
) -> None:
    work(lab)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(PrOpenRefusedError, match=message):
        plan(lab)


def test_an_agent_may_open_for_itself(lab: Lab, monkeypatch: pytest.MonkeyPatch) -> None:
    work(lab)
    monkeypatch.setenv("AUTO_PM_AGENT", "claude")
    assert plan(lab).branch == "claude/CARD-1"


def test_refuses_an_agent_outside_the_roster(lab: Lab) -> None:
    with pytest.raises(PrOpenRefusedError, match="名册"):
        service(lab).plan("copilot", "CARD-1", CARD_PATH, fetch=False)


# ── open: push and PR, never merge ──────────────────────────────────


def test_open_pushes_the_branch_and_creates_the_pr_only(lab: Lab) -> None:
    station = work(lab)
    gh = FakeGh()
    svc = service(lab, gh)
    opened = svc.open(svc.plan("claude", "CARD-1", CARD_PATH, fetch=False))

    assert (opened.number, opened.url) == (101, "https://github.com/o/r/pull/101")
    assert "refs/heads/claude/CARD-1" in lab.remote_refs()
    assert git(station, "rev-parse", "--abbrev-ref", "@{upstream}") == "origin/claude/CARD-1"
    create = next(call for call in gh.calls if call[0][:2] == ("pr", "create"))
    args, body = create
    assert args[args.index("--head") + 1] == "claude/CARD-1"
    assert args[args.index("--base") + 1] == "main"
    assert body is not None and f"任务卡: {CARD_PATH}" in body.splitlines()
    assert gh.used() <= ALLOWED_GH, "只许查登录、查已有 PR、开 PR；不许有合并"
    assert not any("merge" in part for call in gh.calls for part in call[0])


def test_gh_not_logged_in_refuses_before_pushing(lab: Lab) -> None:
    work(lab)
    gh = FakeGh()
    gh.logged_in = False
    before = lab.remote_refs()
    svc = service(lab, gh)
    with pytest.raises(PrOpenRefusedError, match="没登录"):
        svc.open(svc.plan("claude", "CARD-1", CARD_PATH, fetch=False))
    assert lab.remote_refs() == before


def test_an_existing_open_pr_is_not_duplicated_or_touched(lab: Lab) -> None:
    work(lab)
    gh = FakeGh()
    gh.open_prs = '[{"number": 7, "url": "https://github.com/o/r/pull/7"}]'
    before = lab.remote_refs()
    svc = service(lab, gh)
    with pytest.raises(PrOpenRefusedError, match="已有打开的 PR"):
        svc.open(svc.plan("claude", "CARD-1", CARD_PATH, fetch=False))
    assert lab.remote_refs() == before
    assert ("pr", "create") not in gh.used()


def test_open_pushes_exactly_the_checked_commit_with_an_explicit_refspec(lab: Lab) -> None:
    station = work(lab)
    svc = service(lab)
    checked = svc.plan("claude", "CARD-1", CARD_PATH, fetch=False)
    commit(station, "later.txt")  # the agent kept working between the check and the push
    svc.open(checked)
    assert git(lab.origin, "rev-parse", "refs/heads/claude/CARD-1") == checked.head_sha


def test_gh_pr_create_gets_exactly_the_expected_arguments(lab: Lab) -> None:
    work(lab)
    gh = FakeGh()
    svc = service(lab, gh)
    opened = svc.open(svc.plan("claude", "CARD-1", CARD_PATH, fetch=False))
    args = next(call[0] for call in gh.calls if call[0][:2] == ("pr", "create"))
    assert list(args) == [
        "pr", "create", "--base", "main", "--head", "claude/CARD-1",
        "--title", opened.plan.title, "--body-file", "-",
    ]  # fmt: skip


def test_a_failed_pr_list_stops_before_pushing(lab: Lab) -> None:
    work(lab)

    class BrokenList(FakeGh):
        def __call__(self, args: Sequence[str], stdin: str | None):  # noqa: ANN204
            if tuple(args[:2]) == ("pr", "list"):
                return subprocess.CompletedProcess(args, 1, "", "HTTP 500")
            return super().__call__(args, stdin)

    gh = BrokenList()
    before = lab.remote_refs()
    svc = service(lab, gh)
    with pytest.raises(AgentWorktreeError, match="查已有 PR 失败"):
        svc.open(svc.plan("claude", "CARD-1", CARD_PATH, fetch=False))
    assert lab.remote_refs() == before
    assert ("pr", "create") not in gh.used()


def test_pr_create_failing_is_not_success_even_if_the_output_shows_a_url(lab: Lab) -> None:
    work(lab)

    class FailsWithUrl(FakeGh):
        def __call__(self, args: Sequence[str], stdin: str | None):  # noqa: ANN204
            if tuple(args[:2]) == ("pr", "create"):
                return subprocess.CompletedProcess(
                    args, 1, "https://github.com/o/r/pull/55\n", "a pull request already exists"
                )
            return super().__call__(args, stdin)

    svc = service(lab, FailsWithUrl())
    with pytest.raises(AgentWorktreeError, match="开 PR 失败"):
        svc.open(svc.plan("claude", "CARD-1", CARD_PATH, fetch=False))


def test_a_failed_pr_create_after_the_push_says_how_to_continue(lab: Lab) -> None:
    work(lab)

    class BrokenCreate(FakeGh):
        def __call__(self, args: Sequence[str], stdin: str | None):  # noqa: ANN204
            if tuple(args[:2]) == ("pr", "create"):
                return subprocess.CompletedProcess(args, 1, "", "HTTP 502")
            return super().__call__(args, stdin)

    svc = service(lab, BrokenCreate())
    with pytest.raises(AgentWorktreeError, match="重跑本命令"):
        svc.open(svc.plan("claude", "CARD-1", CARD_PATH, fetch=False))
    assert "refs/heads/claude/CARD-1" in lab.remote_refs()


def install_push_hook(lab: Lab, script_body: str) -> None:
    hook = lab.origin / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\n" + script_body, encoding="utf-8", newline="\n")
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell hook")
def test_network_failures_retry_with_backoff_then_succeed(lab: Lab, tmp_path: Path) -> None:
    work(lab)
    counter = tmp_path / "tries"
    install_push_hook(
        lab,
        f'n=$(cat "{counter}" 2>/dev/null || echo 0); n=$((n+1)); echo $n > "{counter}"\n'
        'if [ "$n" -le 2 ]; then echo "Connection timed out" >&2; exit 1; fi\n',
    )
    slept: list[float] = []
    svc = service(lab, sleep=slept.append)
    svc.open(svc.plan("claude", "CARD-1", CARD_PATH, fetch=False))
    assert slept == [2, 4]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell hook")
def test_network_failures_stop_after_four_retries(lab: Lab) -> None:
    work(lab)
    install_push_hook(lab, 'echo "Connection timed out" >&2; exit 1\n')
    slept: list[float] = []
    svc = service(lab, sleep=slept.append)
    with pytest.raises(AgentWorktreeError, match="网络重试 5 次"):
        svc.open(svc.plan("claude", "CARD-1", CARD_PATH, fetch=False))
    assert slept == [2, 4, 8, 16]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell hook")
def test_a_rejected_push_is_not_retried_and_never_forced(lab: Lab) -> None:
    work(lab)
    install_push_hook(lab, 'echo "policy: branch protected" >&2; exit 1\n')
    slept: list[float] = []
    svc = service(lab, sleep=slept.append)
    with pytest.raises(AgentWorktreeError, match="不重试、不强推"):
        svc.open(svc.plan("claude", "CARD-1", CARD_PATH, fetch=False))
    assert slept == []


def test_a_diverged_remote_branch_is_never_overwritten(lab: Lab) -> None:
    work(lab)
    git(lab.github, "checkout", "-q", "-b", "claude/CARD-1")
    other = commit(lab.github, "someone-else.txt")
    git(lab.github, "push", "-q", "origin", "claude/CARD-1")
    svc = service(lab)
    with pytest.raises(AgentWorktreeError, match="推送被拒"):
        svc.open(svc.plan("claude", "CARD-1", CARD_PATH, fetch=False))
    assert git(lab.origin, "rev-parse", "refs/heads/claude/CARD-1") == other


# ── 安全回路 declaration (PLC paths) ───────────────────────────────


def commit_plc_file(station: Path) -> None:
    folder = station / "0100_PLC自动化" / "DJ-TEST" / "02_PLC程序"
    folder.mkdir(parents=True)
    (folder / "FB_X.scl").write_text("// x\n", encoding="utf-8")
    git(station, "add", "0100_PLC自动化")
    git(station, "commit", "-q", "-m", f"feat: [{CHG}] plc")


def set_card_safety(lab: Lab, line: str | None) -> None:
    """Rewrite the card on main: replace its 安全回路 line (None removes it)."""

    text = CARD_TEXT.replace("> 安全回路：否\n", f"{line}\n" if line else "")
    (lab.github / CARD_PATH).write_text(text, encoding="utf-8")
    git(lab.github, "add", "cards")
    git(lab.github, "commit", "-q", "--allow-empty", "-m", "card safety line")
    git(lab.github, "push", "-q", "origin", "main")
    git(lab.root, "pull", "-q", "origin", "main")


def test_a_card_without_the_safety_line_is_refused_no_default(lab: Lab) -> None:
    set_card_safety(lab, None)
    work(lab)
    with pytest.raises(PrOpenRefusedError, match="不能靠默认值"):
        plan(lab)


@pytest.mark.parametrize("written", ["是（急停联锁）", "否，未涉及", "也许", "yes", ""])
def test_a_card_safety_value_that_is_not_plain_yes_or_no_is_refused(lab: Lab, written: str) -> None:
    set_card_safety(lab, f"> 安全回路：{written}")
    work(lab)
    with pytest.raises(PrOpenRefusedError, match="单纯的“是”或“否”"):
        plan(lab)


@pytest.mark.parametrize("answer", ["是", "否"])
def test_the_card_declaration_goes_into_the_body_verbatim_as_its_own_line(lab: Lab, answer: str) -> None:
    set_card_safety(lab, f"> 安全回路：{answer}")
    commit_plc_file(work(lab))
    body = plan(lab).body
    assert f"安全回路: {answer}" in body.splitlines()
    assert sum(1 for line in body.splitlines() if line.startswith("安全回路")) == 1


def test_the_flag_may_repeat_the_card_but_never_contradict_it(lab: Lab) -> None:
    set_card_safety(lab, "> 安全回路：是")
    work(lab)
    assert "安全回路: 是" in plan(lab, safety_circuit="是").body.splitlines()
    with pytest.raises(PrOpenRefusedError, match="不一致"):
        plan(lab, safety_circuit="否")


def test_the_flag_cannot_stand_in_for_a_missing_card_line(lab: Lab) -> None:
    set_card_safety(lab, None)
    work(lab)
    with pytest.raises(PrOpenRefusedError, match="不能靠默认值"):
        plan(lab, safety_circuit="否")


def test_a_flag_other_than_yes_or_no_is_refused(lab: Lab) -> None:
    work(lab)
    with pytest.raises(PrOpenRefusedError, match="只能是 是 或 否"):
        plan(lab, safety_circuit="也许")


def test_scope_comes_from_the_card_not_from_the_diff(lab: Lab) -> None:
    """工位里多改了卡外的文件：可改范围仍只列卡里的路径，越界留给 pr-gate 去拒。"""
    station = work(lab)
    (station / "extra.txt").write_text("not in the card\n", encoding="utf-8")
    git(station, "add", "extra.txt")
    git(station, "commit", "-q", "-m", f"feat: [{CHG}] extra")
    lines = plan(lab).body.splitlines()
    start = lines.index("## 可改范围")
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("## "))
    listed = [line[2:] for line in lines[start:end] if line.startswith("- ")]
    assert listed == ["work/done.txt"]


# ── the real judge (same script GitHub runs) ────────────────────────


@pytest.mark.skipif(
    not REAL_JUDGE.is_file(), reason="reviews/tools/pr_scope_check.py not in this checkout"
)
def test_real_judge_passes_inside_the_card_and_refuses_outside_it(lab: Lab) -> None:
    station = work(lab)
    svc = PrOpenService(lab.root, gh=FakeGh(), judge_script=REAL_JUDGE, sleep=lambda _s: None)
    assert svc.plan("claude", "CARD-1", CARD_PATH, fetch=False).branch == "claude/CARD-1"

    (station / "outside.txt").write_text("not in the card\n", encoding="utf-8")
    git(station, "add", "outside.txt")
    git(station, "commit", "-q", "-m", f"feat: [{CHG}] stray file")
    with pytest.raises(PrOpenRefusedError, match="越界：`outside.txt`"):
        svc.plan("claude", "CARD-1", CARD_PATH, fetch=False)


# ── CLI ─────────────────────────────────────────────────────────────


def test_cli_dry_run_shows_the_pr_and_exit_codes(lab: Lab) -> None:
    work(lab)
    runner = CliRunner(env={"AUTO_PM_AGENT": ""})
    base = ["--workspace", str(lab.root)]
    # no pr_scope_check.py in the lab root: the real-judge path must refuse, never pass
    refused = runner.invoke(
        cli,
        [
            *base,
            "pr",
            "open",
            "claude",
            "CARD-1",
            "--task-card",
            CARD_PATH,
            "--no-fetch",
            "--dry-run",
        ],
    )
    assert refused.exit_code == 1, refused.output
    assert "越界检查不通过" in refused.output

    bad_agent = runner.invoke(
        cli, [*base, "pr", "open", "copilot", "CARD-1", "--task-card", CARD_PATH]
    )
    assert bad_agent.exit_code == 2

    no_card = runner.invoke(cli, [*base, "pr", "open", "claude", "CARD-1"])
    assert no_card.exit_code == 2


@pytest.mark.skipif(
    not REAL_JUDGE.is_file(), reason="reviews/tools/pr_scope_check.py not in this checkout"
)
def test_cli_dry_run_end_to_end_with_the_real_judge(
    lab: Lab, monkeypatch: pytest.MonkeyPatch
) -> None:
    work(lab)
    (lab.root / "reviews" / "tools").mkdir(parents=True)
    # the lab root is a throwaway clone; point the judge at the real script through a wrapper file
    wrapper = lab.root / "reviews" / "tools" / "pr_scope_check.py"
    wrapper.write_text(
        f"import runpy, sys\nsys.argv[0] = {str(REAL_JUDGE)!r}\nrunpy.run_path({str(REAL_JUDGE)!r}, run_name='__main__')\n",
        encoding="utf-8",
    )
    before = lab.remote_refs()
    runner = CliRunner(env={"AUTO_PM_AGENT": ""})
    result = runner.invoke(
        cli,
        ["--workspace", str(lab.root), "pr", "open", "claude", "CARD-1", "--task-card", CARD_PATH,
         "--no-fetch", "--dry-run", "--evidence", "pytest => 0"],
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert "claude/CARD-1" in result.output and CHG in result.output and "没有推送" in result.output
    assert lab.remote_refs() == before
