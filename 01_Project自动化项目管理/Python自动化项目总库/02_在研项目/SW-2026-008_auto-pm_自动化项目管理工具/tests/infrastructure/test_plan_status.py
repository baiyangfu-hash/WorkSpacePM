"""项目计划状态（WBS 8.8 第一版）：``scripts/card_status.py`` 和 ``scripts/plan_status.py``。

不用假数据冒充 Git：每条测试在临时目录里建一个真的“远程”裸仓库和一个克隆，用真的 git 命令造占位、分支、
合并和证据文件，再让脚本去算。只读本项目目录里的两个脚本，别的都在 tmp_path 里。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest

PROJECT = Path(__file__).resolve().parents[2]
PID = "DJ-2026-005"
PROJECT_DIR = "0100_PLC自动化/DJ-2026-005"
PLAN_PATH = f"{PROJECT_DIR}/00_项目管理/01_立项与需求/006_{PID}_项目计划表.md"
CARD1 = f"CARD-{PID}-001"
CARD2 = f"CARD-{PID}-002"
CARD3 = f"CARD-{PID}-003"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"{name}_under_test", PROJECT / "scripts" / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cs() -> ModuleType:
    return _load("card_status")


@pytest.fixture(scope="module")
def ps() -> ModuleType:
    return _load("plan_status")


def git(cwd: Path, *arguments: str, stdin: bytes | None = None) -> str:
    done = subprocess.run(
        [
            "git",
            "-C",
            str(cwd),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.quotepath=off",
            *arguments,
        ],
        capture_output=True,
        input=stdin,
        check=False,
    )
    assert done.returncode == 0, f"git {arguments}: {done.stderr.decode('utf-8', 'replace')}"
    return done.stdout.decode("utf-8", "replace").strip()


PLAN = f"""# 项目计划表 - {PID}

## L1 立项

| 编号 | 原子任务 | 实施卡 | 证据 | 备注 |
|---|---|---|---|---|
| L1.1 | 项目立项表 | `{CARD1}` | `05_测试与验证/立项表核对.md` | |
| L1.2 | 迁入清单 | `{CARD2}` | | |

## L2 需求

| 编号 | 原子任务 | 实施卡 | 证据 | 备注 |
|---|---|---|---|---|
| L2.1 | 工艺流程分析 | 无 | `01_需求与设计/工艺流程.md` | |
| L2.2 | 机械原型 | 不适用 | | 用户说 005 不需要 |
| L2.3 | 电气图纸 | 无 | `01_需求与设计/图纸.pdf` | |

## L6 现场

| 编号 | 原子任务 | 实施卡 | 证据 | 备注 |
|---|---|---|---|---|
| L6.1 | 移植回执 | 用户 | `04_现场调试/移植回执.md` | |

## 验收记录

| 里程碑 | 验收时间 | 凭据 |
|---|---|---|
"""


class Repos:
    """一个裸的“远程”、一个往里推东西的作者克隆、一个只用来算状态的控制根克隆。"""

    def __init__(self, tmp_path: Path, plan: str = PLAN) -> None:
        self.remote = tmp_path / "remote.git"
        self.author = tmp_path / "author"
        self.root = tmp_path / "root"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.remote)], check=True)
        subprocess.run(
            ["git", "clone", "-q", str(self.remote), str(self.author)],
            check=True,
            capture_output=True,
        )
        git(self.author, "checkout", "-q", "-b", "main")
        self.write(
            "SYS-2026-001_WorkspaceGovernance/workspace_registry.json",
            json.dumps({"projects": [{"project_id": PID, "project_root": PROJECT_DIR}]}),
        )
        self.write(f"{PROJECT_DIR}/01_需求与设计/工艺流程.md", "工艺流程\n")
        if plan:
            self.write(PLAN_PATH, plan)
        git(self.author, "add", "-A")
        git(self.author, "commit", "-q", "-m", "init")
        git(self.author, "push", "-q", "origin", "main")
        subprocess.run(
            ["git", "clone", "-q", str(self.remote), str(self.root)],
            check=True,
            capture_output=True,
        )

    def write(self, path: str, text: str) -> None:
        target = self.author / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def commit_main(self, message: str, files: dict[str, str] | None = None) -> None:
        git(self.author, "checkout", "-q", "main")
        for path, text in (files or {}).items():
            self.write(path, text)
        git(self.author, "add", "-A")
        git(self.author, "commit", "-q", "--allow-empty", "-m", message)
        git(self.author, "push", "-q", "origin", "main")

    def claim(self, card: str, *, status: str = "active", hours: float = 4) -> None:
        """照 ClaimService 的写法造一个占位：空树提交，说明第一行 ``claim <卡号>``，后面是 JSON。"""
        payload = {
            "owner": "claude",
            "machine": "t",
            "paths": [],
            "goal": "g",
            "claimed_at": datetime.now(UTC).isoformat(),
            "status": status,
            "expires_at": (datetime.now(UTC) + timedelta(hours=hours)).isoformat(),
            "note": {"kind": "pr", "next_step": "已完成"},  # 交接记录里的字不许影响状态
        }
        tree = git(self.author, "mktree", stdin=b"")
        commit = git(
            self.author,
            "commit-tree",
            tree,
            "-m",
            f"claim {card}\n" + json.dumps(payload, ensure_ascii=False),
        )
        git(self.author, "push", "-q", "--force", "origin", f"{commit}:refs/heads/claims/{card}")

    def branch(self, card: str, files: dict[str, str] | None = None, message: str = "work") -> str:
        name = f"claude/{card}"
        git(self.author, "checkout", "-q", "-B", name, "main")
        for path, text in (files or {f"{PROJECT_DIR}/work_{card}.txt": "x\n"}).items():
            self.write(path, text)
        git(self.author, "add", "-A")
        git(self.author, "commit", "-q", "-m", message)
        git(self.author, "push", "-q", "--force", "origin", name)
        git(self.author, "checkout", "-q", "main")
        return name

    def merge(self, card: str, *, subject: str | None = None, delete: bool = True) -> None:
        name = f"claude/{card}"
        git(self.author, "checkout", "-q", "main")
        git(
            self.author,
            "merge",
            "-q",
            "--no-ff",
            name,
            "-m",
            subject if subject is not None else f"Merge pull request #7 from owner/{name}",
        )
        git(self.author, "push", "-q", "origin", "main")
        if delete:
            git(self.author, "push", "-q", "origin", f":refs/heads/{name}")

    def facts(self, cs: ModuleType, *, offline: bool = False):  # type: ignore[no-untyped-def]
        source = cs.GitFacts(self.root)
        source.refresh(offline=offline)
        return source


@pytest.fixture
def repos(tmp_path: Path) -> Repos:
    return Repos(tmp_path)


def _run(ps: ModuleType, repos: Repos, *extra: str, pid: str = PID) -> tuple[int, str]:
    lines: list[str] = []
    options = {"offline": "--offline" in extra, "as_json": "--json" in extra}
    code = ps.run(pid, root=repos.root, out=lines.append, **options)
    return code, "\n".join(lines)


def _status(text: str, task: str) -> str:
    row = next(line for line in text.splitlines() if line.startswith(f"| {task} |"))
    return [cell.strip() for cell in row.strip("|").split("|")][3]


# ── 认卡号：不许冒认 ──────────────────────────────────────────────────


def test_a_card_number_is_not_matched_inside_a_longer_one(cs: ModuleType) -> None:
    assert cs.card_in(f"验证 {CARD1} 通过", CARD1)
    assert cs.card_in(f"{CARD1}_报告", CARD1)
    assert not cs.card_in(f"{CARD1}2", CARD1)
    assert not cs.card_in(f"X{CARD1}", CARD1)
    assert not cs.card_in(f"{CARD1}-fix", CARD1)
    assert not cs.card_in("664-pm-flows", "664")


def test_only_a_default_merge_subject_or_a_marker_line_names_a_card(cs: ModuleType) -> None:
    assert cs.commit_names_card(f"Merge pull request #7 from owner/claude/{CARD1}", CARD1)
    assert cs.commit_names_card(f"清账\n\n领卡占位: {CARD1}\n", CARD1)
    assert cs.commit_names_card(f"清账\n\n领卡占位：`{CARD1}`", CARD1)
    assert not cs.commit_names_card(f"Merge pull request #7 from owner/claude/{CARD1}2", CARD1)
    assert not cs.commit_names_card(f"Merge pull request #7: 清账（{CARD1}）", CARD1), (
        "改写过的合并标题不认"
    )
    assert not cs.commit_names_card(f"建卡 {CARD1}、{CARD2}", CARD1), "随口提到卡号不算合并"
    assert not cs.commit_names_card(f"说明\n领卡占位: {CARD2}", CARD1)


# ── 纯判法 ────────────────────────────────────────────────────────────


def test_judge_levels(cs: ModuleType) -> None:
    now = datetime(2026, 11, 14, tzinfo=UTC)
    live = cs.ClaimFact("c", "active", "claude", "2026-11-14T04:00:00+00:00")
    expired = cs.ClaimFact("c", "active", "claude", "2026-11-13T04:00:00+00:00")
    released = cs.ClaimFact("c", "released", "claude", "2026-11-14T04:00:00+00:00")
    unreadable = cs.ClaimFact("c", "active", "claude", "")

    def status(**facts: object) -> str:
        return str(cs.judge(cs.CardFacts(CARD1, known=True, **facts), now).status)

    assert status() == cs.NOT_STARTED
    assert status(claim=live) == cs.IN_PROGRESS
    assert status(claim=expired) == cs.NOT_STARTED
    assert status(claim=released) == cs.NOT_STARTED
    assert status(claim=unreadable) == cs.NOT_STARTED
    assert status(open_branches=("claude/x",)) == cs.IN_PROGRESS
    assert status(merged_commits=("a" * 40,)) == cs.MERGED
    assert status(merged_commits=("a" * 40,), evidence_ok=("e.md",)) == cs.DONE
    assert (
        status(merged_commits=("a" * 40,), evidence_ok=("e.md",), evidence_bad=(("f.md", "空"),))
        == cs.MERGED
    )
    assert status(evidence_ok=("e.md",)) == cs.NOT_STARTED, "没合并，光有证据文件不算完成"
    assert status(claim=live, merged_commits=("a" * 40,)) == cs.MERGED, "摘没摘牌子不影响已合并"
    assert cs.judge(cs.CardFacts(CARD1, known=False), now).status == cs.UNKNOWN


# ── 真 Git：四级 ──────────────────────────────────────────────────────


def test_four_levels_against_a_real_remote(cs: ModuleType, repos: Repos) -> None:
    evidence = f"{PROJECT_DIR}/05_测试与验证/立项表核对.md"
    assert repos.facts(cs).card_status(CARD1, [evidence]).status == cs.NOT_STARTED

    repos.claim(CARD1)
    assert repos.facts(cs).card_status(CARD1, [evidence]).status == cs.IN_PROGRESS

    repos.claim(CARD1, status="released")
    assert repos.facts(cs).card_status(CARD1, [evidence]).status == cs.NOT_STARTED

    repos.branch(CARD1)
    assert repos.facts(cs).card_status(CARD1, [evidence]).status == cs.IN_PROGRESS

    repos.merge(CARD1)
    result = repos.facts(cs).card_status(CARD1, [evidence])
    assert result.status == cs.MERGED and "main 上没有这个文件" in "".join(result.reasons)

    repos.commit_main("证据", {evidence: "核对通过\n"})
    result = repos.facts(cs).card_status(CARD1, [evidence])
    assert result.status == cs.MERGED and "没写这张卡的卡号" in "".join(result.reasons)

    repos.commit_main("证据补卡号", {evidence: f"核对通过，对应 {CARD1}\n"})
    assert repos.facts(cs).card_status(CARD1, [evidence]).status == cs.DONE
    assert repos.facts(cs).card_status(CARD2, []).status == cs.NOT_STARTED, "别的卡不受影响"


def test_an_expired_claim_is_not_work_in_progress(cs: ModuleType, repos: Repos) -> None:
    repos.claim(CARD1, hours=-1)
    result = repos.facts(cs).card_status(CARD1)
    assert result.status == cs.NOT_STARTED and "占位已过期" in result.reasons


def test_an_empty_evidence_file_does_not_count(cs: ModuleType, repos: Repos) -> None:
    evidence = f"{PROJECT_DIR}/e.md"
    repos.branch(CARD1)
    repos.merge(CARD1)
    repos.commit_main("空证据", {evidence: "\n"})
    result = repos.facts(cs).card_status(CARD1, [evidence])
    assert result.status == cs.MERGED and "文件是空的" in "".join(result.reasons)


def test_a_casual_mention_or_a_rewritten_merge_title_is_not_a_merge(
    cs: ModuleType, repos: Repos
) -> None:
    repos.commit_main(f"建卡 {CARD1} {CARD2}")
    assert repos.facts(cs).card_status(CARD1).status == cs.NOT_STARTED
    repos.branch(CARD2)
    repos.merge(CARD2, subject=f"Merge pull request #9: 清账（{CARD2}）")
    assert repos.facts(cs).card_status(CARD2).status == cs.NOT_STARTED, (
        "合并标题被改写又没有标记行，认不出"
    )
    repos.branch(CARD3, message=f"整改\n\n领卡占位: {CARD3}")
    repos.merge(CARD3, subject="Merge pull request #10: 整改")
    assert repos.facts(cs).card_status(CARD3).status == cs.MERGED, "提交说明里有标记行就认"


def test_a_merged_branch_left_on_the_remote_is_not_open(cs: ModuleType, repos: Repos) -> None:
    repos.branch(CARD1)
    repos.merge(CARD1, delete=False)
    result = repos.facts(cs).card_status(CARD1)
    assert result.status == cs.MERGED and result.facts.open_branches == ()


def test_a_longer_card_number_does_not_light_up_a_shorter_one(cs: ModuleType, repos: Repos) -> None:
    longer = f"{CARD1}2"
    repos.claim(longer)
    repos.branch(longer)
    assert repos.facts(cs).card_status(CARD1).status == cs.NOT_STARTED


def test_an_unreachable_remote_is_unknown_never_not_started(cs: ModuleType, repos: Repos) -> None:
    repos.claim(CARD1)
    repos.facts(cs)  # 先成功取一次，本机留下旧数据
    git(repos.root, "remote", "set-url", "origin", str(repos.remote) + "_gone")
    source = cs.GitFacts(repos.root)
    snapshot = source.refresh()
    assert not snapshot.ok and "没成功" in snapshot.problem
    assert source.card_status(CARD1).status == cs.UNKNOWN, "联网取不到时不拿旧数据充数"
    offline = cs.GitFacts(repos.root)
    assert offline.refresh(offline=True).ok and "本机上次取回" in offline.snapshot.describe()
    assert offline.card_status(CARD1).status == cs.IN_PROGRESS


@pytest.mark.parametrize("broken", ["fetch", "ls-remote"])
def test_either_remote_read_failing_alone_is_unknown(
    cs: ModuleType, repos: Repos, broken: str
) -> None:
    """取回和列分支两步，任何一步单独失败都整体记“没读到”，不拿另一半数据凑。"""
    repos.claim(CARD1)
    repos.facts(cs)

    def runner(command: list[str], **kwargs: object) -> object:
        if broken in command:
            return subprocess.CompletedProcess(command, 1, b"", b"fatal: unable to access")
        return subprocess.run(command, **kwargs)  # type: ignore[call-overload]

    source = cs.GitFacts(repos.root, runner=runner)
    snapshot = source.refresh()
    assert not snapshot.ok and "没成功" in snapshot.problem
    assert source.card_status(CARD1).status == cs.UNKNOWN


def test_reading_facts_leaves_the_working_tree_and_head_alone(cs: ModuleType, repos: Repos) -> None:
    repos.claim(CARD1)
    repos.branch(CARD1)
    head = git(repos.root, "rev-parse", "HEAD")
    repos.commit_main("main 往前走")
    repos.facts(cs).card_status(CARD1, [f"{PROJECT_DIR}/e.md"])
    assert git(repos.root, "rev-parse", "HEAD") == head
    assert git(repos.root, "status", "--porcelain") == ""
    assert git(repos.root, "for-each-ref", "refs/heads/").count("\n") == 0, "不建本地分支"


def test_a_malformed_card_number_is_refused(cs: ModuleType, repos: Repos) -> None:
    with pytest.raises(ValueError):
        repos.facts(cs).card_facts("--upload-pack=x")


# ── 计划表的读法 ──────────────────────────────────────────────────────


def test_the_plan_is_read_as_written(ps: ModuleType) -> None:
    plan = ps.parse_plan(PLAN, PID)
    assert plan.problems == []
    assert [(m.milestone_id, m.title, len(m.tasks)) for m in plan.milestones] == [
        ("L1", "立项", 2),
        ("L2", "需求", 3),
        ("L6", "现场", 1),
    ]
    first = plan.milestones[0].tasks[0]
    assert (first.task_id, first.card, first.evidence) == (
        "L1.1",
        CARD1,
        ("05_测试与验证/立项表核对.md",),
    )
    assert [(t.card, t.applicable) for t in plan.milestones[1].tasks] == [
        ("", True),
        ("", False),
        ("", True),
    ]


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (f"| L1.1 | 重复 | `{CARD3}` | | |", "重复"),
        (f"| L2.9 | 编号不属于这一节 | `{CARD3}` | | |", "应以 L1. 开头"),
        (f"| L1.3 | 卡号重复 | `{CARD1}` | | |", "一张卡只对一个原子任务"),
        ("| L1.3 | 别的项目的卡 | `CARD-DJ-2026-011-001` | | |", "实施卡一格只能是"),
        (f"| L1.3 | 卡号没包反引号 | {CARD3} | | |", "实施卡一格只能是"),
        (f"| L1.3 | 两张卡 | `{CARD3}` `{CARD2}` | | |", "实施卡一格只能是"),
        ("| L1.3 | 证据没包反引号 | 无 | 05_测试与验证/x.md | |", "没有反引号包着的路径"),
        ("| L1.3 | 证据往上跳 | 无 | `../x.md` | |", "相对项目目录"),
        ("| L1.3 | 证据绝对路径 | 无 | `C:/x.md` | |", "相对项目目录"),
        ("| L1.3 | 少一格 | 无 | |", "应有 5 格"),
        ("| L1.3 | 用户的活没列证据 | 用户 | | |", "必须列证据路径"),
    ],
)
def test_a_malformed_row_is_reported_not_guessed(ps: ModuleType, row: str, expected: str) -> None:
    text = PLAN.replace("| L1.2 | 迁入清单 |", row + "\n| L1.2 | 迁入清单 |")
    plan = ps.parse_plan(text, PID)
    assert len(plan.problems) == 1 and expected in plan.problems[0], plan.problems
    assert [t.task_id for t in plan.milestones[0].tasks] == ["L1.1", "L1.2"], (
        "坏行不算进去，好行照算"
    )


def test_a_hand_written_status_column_makes_the_table_unreadable(ps: ModuleType) -> None:
    text = PLAN.replace(
        "| 编号 | 原子任务 | 实施卡 | 证据 | 备注 |\n|---|---|---|---|---|\n| L1.1",
        "| 编号 | 原子任务 | 实施卡 | 状态 | 证据 | 备注 |\n|---|---|---|---|---|---|\n| L1.1",
        1,
    )
    plan = ps.parse_plan(text, PID)
    assert any("表头应是" in problem for problem in plan.problems)
    assert plan.milestones[0].tasks == [], "带状态栏的表整张不读：状态不许手填"


def test_an_acceptance_record_needs_a_time_and_a_user_confirmation(ps: ModuleType) -> None:
    good = PLAN + "| L1 | 2026-11-17T20:00-07:00 | user-confirmation:cmsg_abc12345 |\n"
    assert [(a.milestone_id, a.proof) for a in ps.parse_plan(good, PID).acceptances] == [
        ("L1", "user-confirmation:cmsg_abc12345")
    ]
    for bad in (
        "| L1 | | user-confirmation:cmsg_abc12345 |",
        "| L1 | 2026-11-17 | agent 说可以了 |",
        "| L1 | 2026-11-17 | agent 说可以了，凭据见聊天记录里用户那句话的截图和转述 |",
        "| L1 | 2026-11-17 | user-confirmation:x |",
        "| L9 | 2026-11-17 | user-confirmation:cmsg_abc12345 |",
    ):
        plan = ps.parse_plan(PLAN + bad + "\n", PID)
        assert plan.problems, bad


# ── 整条命令 ──────────────────────────────────────────────────────────


def test_end_to_end_statuses_and_milestones(ps: ModuleType, repos: Repos) -> None:
    code, text = _run(ps, repos)
    assert code == 0, text
    assert _status(text, "L1.1") == "未开始" and _status(text, "L1.2") == "未开始"
    assert _status(text, "L2.1") == "有东西缺证据"
    assert _status(text, "L2.2") == "不适用"
    assert _status(text, "L2.3") == "未开始"
    assert "| L1 立项 | 未开始 | 2 | 0 | 0 |" in text
    assert "| L2 需求 | 进行中 | 2 | 0 | 0 |" in text, "不适用的不计数"
    assert "main 上的版本" in text and "刚从远程取回" in text

    repos.claim(CARD2)
    repos.branch(CARD1)
    repos.merge(CARD1)
    code, text = _run(ps, repos)
    assert code == 0 and _status(text, "L1.1") == "已合并未验证" and _status(text, "L1.2") == "在干"
    assert "| L1 立项 | 进行中 | 2 | 0 | 0 |" in text

    evidence = f"{PROJECT_DIR}/05_测试与验证/立项表核对.md"
    repos.branch(CARD2)
    repos.merge(CARD2)
    repos.commit_main("证据", {evidence: f"{CARD1} 核对通过\n"})
    code, text = _run(ps, repos)
    assert _status(text, "L1.1") == "已完成" and _status(text, "L1.2") == "已合并未验证"
    assert "| L1 立项 | 进行中 | 2 | 1 | 0 |" in text, "没列证据的任务到不了已完成"


def test_a_milestone_waits_for_the_user_then_is_reached(ps: ModuleType, tmp_path: Path) -> None:
    plan = PLAN.replace(f"| L1.2 | 迁入清单 | `{CARD2}` | | |\n", "")
    repos = Repos(tmp_path, plan)
    evidence = f"{PROJECT_DIR}/05_测试与验证/立项表核对.md"
    repos.branch(CARD1)
    repos.merge(CARD1)
    repos.commit_main("证据", {evidence: f"{CARD1} 核对通过\n"})
    code, text = _run(ps, repos)
    assert code == 0 and "| L1 立项 | 待用户验收 | 1 | 1 | 0 |" in text

    repos.commit_main(
        "验收",
        {PLAN_PATH: plan + "| L1 | 2026-11-17T20:00-07:00 | user-confirmation:cmsg_abc12345 |\n"},
    )
    code, text = _run(ps, repos)
    assert code == 0 and "| L1 立项 | 已达成 | 1 | 1 | 0 |" in text


def test_a_user_task_is_delivered_when_the_file_is_on_main_and_then_awaits_acceptance(
    ps: ModuleType, repos: Repos
) -> None:
    code, text = _run(ps, repos)
    assert (
        code == 0
        and _status(text, "L6.1") == "未开始"
        and "| L6 现场 | 未开始 | 1 | 0 | 0 |" in text
    )
    repos.commit_main(
        "用户放回执", {f"{PROJECT_DIR}/04_现场调试/移植回执.md": "已移植，编译通过\n"}
    )
    code, text = _run(ps, repos)
    assert code == 0 and _status(text, "L6.1") == "用户已交"
    assert "| L6 现场 | 待用户验收 | 1 | 1 | 0 |" in text


def test_a_task_with_no_card_blocks_its_milestone(ps: ModuleType, repos: Repos) -> None:
    """写“无”的任务文件再齐也只到“有东西缺证据”，里程碑到不了待用户验收。"""
    repos.commit_main("图纸", {f"{PROJECT_DIR}/01_需求与设计/图纸.pdf": "x\n"})
    code, text = _run(ps, repos)
    assert (
        code == 0
        and _status(text, "L2.1") == "有东西缺证据"
        and _status(text, "L2.3") == "有东西缺证据"
    )
    assert "| L2 需求 | 进行中 | 2 | 0 | 0 |" in text


def test_an_acceptance_record_cannot_reach_a_milestone_whose_tasks_are_not_done(
    ps: ModuleType, tmp_path: Path
) -> None:
    repos = Repos(
        tmp_path, PLAN + "| L1 | 2026-11-17T20:00-07:00 | user-confirmation:cmsg_abc12345 |\n"
    )
    code, text = _run(ps, repos)
    assert code == 0 and "| L1 立项 | 未开始 |" in text
    assert "有验收记录，但任务没有全部已完成，不算已达成" in text


def test_only_what_is_merged_into_main_counts(ps: ModuleType, repos: Repos) -> None:
    """控制根工作区里没提交的改动（计划表、证据）都不读。"""
    (repos.root / PLAN_PATH).write_text("# 被本机改坏的计划表\n", encoding="utf-8")
    evidence = repos.root / PROJECT_DIR / "01_需求与设计" / "图纸.pdf"
    evidence.write_text("本机放了个文件\n", encoding="utf-8")
    code, text = _run(ps, repos)
    assert code == 0 and _status(text, "L2.3") == "未开始" and _status(text, "L1.1") == "未开始"


def test_no_plan_table_yet_is_not_an_error(ps: ModuleType, tmp_path: Path) -> None:
    repos = Repos(tmp_path, plan="")
    code, text = _run(ps, repos)
    assert code == 0 and "还没有项目计划表" in text


def test_two_plan_tables_is_an_error(ps: ModuleType, repos: Repos) -> None:
    repos.commit_main("第二张", {PLAN_PATH.replace("006_", "007_"): PLAN})
    code, text = _run(ps, repos)
    assert code == 1 and "只能有一张" in text


def test_an_unreachable_remote_says_unknown_and_exits_1(ps: ModuleType, repos: Repos) -> None:
    git(repos.root, "remote", "set-url", "origin", str(repos.remote) + "_gone")
    code, text = _run(ps, repos)
    assert code == 1 and "没查到" in text
    assert "未开始" not in text and "已完成" not in text, "读不到远程时不许给出任何状态"

    code, text = _run(ps, repos, "--offline")
    assert code == 0 and "本机上次取回的数据" in text and _status(text, "L1.1") == "未开始"


def test_plan_file_with_no_remote_marks_card_tasks_unknown(
    ps: ModuleType, repos: Repos, tmp_path: Path
) -> None:
    git(repos.root, "remote", "set-url", "origin", str(repos.remote) + "_gone")
    local = tmp_path / "plan.md"
    local.write_text(PLAN, encoding="utf-8")
    lines: list[str] = []
    code = ps.run(PID, root=repos.root, plan_file=local, out=lines.append)
    text = "\n".join(lines)
    assert code == 1 and _status(text, "L1.1") == "没查到" and _status(text, "L2.1") == "没查到"
    assert _status(text, "L6.1") == "没查到"
    assert "| L1 立项 | 没查到 | 2 | 0 | 2 |" in text


def test_format_problems_are_listed_and_exit_1_but_good_rows_still_count(
    ps: ModuleType, tmp_path: Path
) -> None:
    repos = Repos(tmp_path, PLAN.replace("| L2.3 | 电气图纸 | 无 |", "| L2.3 | 电气图纸 | 没有 |"))
    code, text = _run(ps, repos)
    assert code == 1 and "计划表有 1 处格式问题" in text and _status(text, "L2.1") == "有东西缺证据"


def test_usage_errors_compute_nothing(ps: ModuleType, repos: Repos) -> None:
    code, text = _run(ps, repos, pid="--fix")
    assert code == 2 and "项目号格式不对" in text
    code, text = _run(ps, repos, pid="DJ-2026-999")
    assert code == 2 and "查不到" in text


def test_json_output_carries_the_facts(ps: ModuleType, repos: Repos) -> None:
    repos.claim(CARD1)
    code, text = _run(ps, repos, "--json")
    report = json.loads(text)
    assert (
        code == 0
        and report["pid"] == PID
        and report["snapshot_ok"] is True
        and len(report["ref_commit"]) == 40
    )
    task = report["milestones"][0]["tasks"][0]
    assert task["status"] == "在干" and task["detail"]["claim"]["status"] == "active"
    assert "note" not in json.dumps(task, ensure_ascii=False), "交接记录的字不进状态"


def test_the_script_writes_nothing_in_the_control_root(ps: ModuleType, repos: Repos) -> None:
    def tree() -> str:
        digest = hashlib.sha256()
        for path in sorted(repos.root.rglob("*")):
            if ".git" in path.relative_to(repos.root).parts or not path.is_file():
                continue
            digest.update(str(path.relative_to(repos.root)).encode("utf-8"))
            digest.update(path.read_bytes())
        return digest.hexdigest()

    before = tree()
    head = git(repos.root, "rev-parse", "HEAD")
    repos.claim(CARD1)
    assert _run(ps, repos)[0] == 0
    assert tree() == before and git(repos.root, "rev-parse", "HEAD") == head
    assert git(repos.root, "status", "--porcelain") == ""


def test_the_command_line_runs_and_has_no_write_switch(repos: Repos) -> None:
    script = PROJECT / "scripts" / "plan_status.py"
    done = subprocess.run(
        [sys.executable, "-B", str(script), PID, "--root", str(repos.root)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        stdin=subprocess.DEVNULL,
        env={**__import__("os").environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
    )
    assert done.returncode == 0, done.stderr
    assert "【项目计划状态】DJ-2026-005" in done.stdout
    for name in ("plan_status.py", "card_status.py"):
        source = (PROJECT / "scripts" / name).read_text(encoding="utf-8")
        assert "shell=True" not in source and "write_text" not in source and "open(" not in source
        assert '"--write"' not in source and '"--fix"' not in source and '"--apply"' not in source
    used = set(
        re.findall(
            r'self\._git\(\s*"([a-z-]+)"',
            (PROJECT / "scripts" / "card_status.py").read_text(encoding="utf-8"),
        )
    )
    assert used == {
        "fetch",
        "ls-remote",
        "for-each-ref",
        "log",
        "show",
        "merge-base",
        "cat-file",
        "ls-tree",
    }, used
