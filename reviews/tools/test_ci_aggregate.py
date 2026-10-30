"""ci_aggregate：按改动路径算出该跑的工作流，缺了或红了判不通过。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ci_aggregate as agg

REPO = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / ".github" / "workflows"
SW008 = "01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具"


def _run(name: str, run_id: int, status: str = "completed", conclusion: str | None = "success", event: str = "pull_request") -> dict:
    return {"id": run_id, "path": f".github/workflows/{name}@refs/pull/1/merge", "event": event, "status": status, "conclusion": conclusion}


def test_real_workflows_are_read_the_way_github_filters_them() -> None:
    triggers = {t.workflow: t for t in agg.load_triggers(WORKFLOWS)}
    assert "pr-gate.yml" not in triggers and "safety-gate.yml" not in triggers  # pull_request_target，本来就必跑
    assert agg.SELF not in triggers
    assert triggers["reviews-tools-ci.yml"].always
    assert triggers["plc-ci.yml"].always
    assert not triggers["sw008-ci.yml"].always and triggers["sw008-ci.yml"].paths


def test_sw008_ci_is_expected_only_when_its_paths_change() -> None:
    triggers = agg.load_triggers(WORKFLOWS)
    assert "sw008-ci.yml" not in agg.expected_workflows(triggers, ["reviews/tools/audit_pr.py"])
    assert "sw008-ci.yml" in agg.expected_workflows(triggers, [f"{SW008}/auto_pm/x.py"])
    assert "sw008-ci.yml" in agg.expected_workflows(triggers, [".github/workflows/sw008-ci.yml"])
    assert "reviews-tools-ci.yml" in agg.expected_workflows(triggers, ["README.md"])


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("on:\n  push:\n    branches: [main]\n", None),
        ("on:\n  pull_request_target:\n    types: [opened]\n", None),
        ("on:\n  pull_request:\n    branches: [main]\n", agg.Trigger("w.yml", True)),
        ("on:\n  pull_request:\n    paths:\n      - 'a/**'\n      - b.txt\n  push:\n    paths:\n      - z\n", agg.Trigger("w.yml", False, ("a/**", "b.txt"))),
        ("on:\n  pull_request:\n    paths-ignore:\n      - docs/**\n", agg.Trigger("w.yml", True)),
        ("on:\n  pull_request:\n    paths: [a, b]\n", agg.Trigger("w.yml", True)),
        ("on: [pull_request, push]\n", agg.Trigger("w.yml", True)),
        ("on: [pull_request_target, pull_request]\n", agg.Trigger("w.yml", True)),  # 审计 402 P2-1
        ("on: [pull_request_target]\n", None),
        ("on: pull_request\n", agg.Trigger("w.yml", True)),
    ],
)
def test_parse_trigger(text: str, expected: agg.Trigger | None) -> None:
    assert agg.parse_trigger("w.yml", text) == expected


def test_judge_passes_only_when_every_expected_workflow_succeeded() -> None:
    expected = ["a.yml", "b.yml"]
    assert agg.judge(expected, [_run("a.yml", 1), _run("b.yml", 2, conclusion="skipped")], elapsed=0, grace=60)[0] == "pass"
    assert agg.judge(expected, [_run("a.yml", 1), _run("b.yml", 2, conclusion="failure")], elapsed=0, grace=60)[0] == "fail"
    assert agg.judge(expected, [_run("a.yml", 1), _run("b.yml", 2, conclusion="cancelled")], elapsed=0, grace=60)[0] == "fail"
    assert agg.judge(expected, [_run("a.yml", 1), _run("b.yml", 2, status="in_progress", conclusion=None)], elapsed=0, grace=60)[0] == "wait"


def test_a_missing_run_waits_then_fails_after_the_grace_period() -> None:
    runs = [_run("a.yml", 1)]
    assert agg.judge(["a.yml", "b.yml"], runs, elapsed=10, grace=60)[0] == "wait"
    verdict, notes = agg.judge(["a.yml", "b.yml"], runs, elapsed=61, grace=60)
    assert verdict == "fail" and any("b.yml" in n for n in notes)


def test_the_newest_run_of_a_workflow_counts_and_dispatch_runs_count() -> None:
    old_red_new_green = [_run("a.yml", 1, conclusion="failure"), _run("a.yml", 5)]
    assert agg.judge(["a.yml"], old_red_new_green, elapsed=0, grace=60)[0] == "pass"
    green_then_red = [_run("a.yml", 1), _run("a.yml", 5, conclusion="failure", event="workflow_dispatch")]
    assert agg.judge(["a.yml"], green_then_red, elapsed=0, grace=60)[0] == "fail"
    assert agg.judge(["a.yml"], [_run("a.yml", 1, event="push")], elapsed=0, grace=60)[0] == "wait"  # push 的记录不算 PR 的


class FakeGitHub:
    def __init__(self, files: list[str], run_batches: list[list[dict] | None]) -> None:
        self.files = files
        self.batches = run_batches
        self.polls = 0

    def __call__(self, path: str):
        if path.startswith("pulls/"):
            return [{"filename": f} for f in self.files]
        batch = self.batches[min(self.polls, len(self.batches) - 1)]
        self.polls += 1
        return None if batch is None else {"workflow_runs": batch}


def _drive(fake: FakeGitHub, triggers: list[agg.Trigger], **kw):
    clock = {"t": 0.0}

    def sleep(seconds: float) -> None:
        clock["t"] += seconds

    return agg.run(triggers, fake, 1, "sha", sleep=sleep, clock=lambda: clock["t"], interval=30, **kw)


def test_run_waits_for_a_running_workflow_then_passes() -> None:
    triggers = [agg.Trigger("a.yml", True)]
    fake = FakeGitHub(["x"], [[_run("a.yml", 1, status="in_progress", conclusion=None)], [_run("a.yml", 1)]])
    code, report = _drive(fake, triggers)
    assert code == 0 and fake.polls == 2 and "通过" in report


def test_run_fails_when_a_required_workflow_never_appears() -> None:
    triggers = [agg.Trigger("a.yml", True), agg.Trigger("sw.yml", False, ("src/**",))]
    fake = FakeGitHub(["src/app.py"], [[_run("a.yml", 1)]])
    code, report = _drive(fake, triggers, grace=120)
    assert code == 1 and "sw.yml" in report


def test_run_does_not_wait_for_a_workflow_whose_paths_did_not_change() -> None:
    triggers = [agg.Trigger("a.yml", True), agg.Trigger("sw.yml", False, ("src/**",))]
    code, _ = _drive(FakeGitHub(["docs/x.md"], [[_run("a.yml", 1)]]), triggers)
    assert code == 0


def test_run_fails_closed_when_github_cannot_be_read() -> None:
    triggers = [agg.Trigger("a.yml", True)]
    code, _ = _drive(FakeGitHub(["x"], [None]), triggers, grace=60)
    assert code == 1
    broken_files = agg.run(triggers, lambda path: None, 1, "sha")
    assert broken_files[0] == 1


def test_run_gives_up_after_the_deadline() -> None:
    triggers = [agg.Trigger("a.yml", True)]
    fake = FakeGitHub(["x"], [[_run("a.yml", 1, status="in_progress", conclusion=None)]])
    code, report = _drive(fake, triggers, deadline=120)
    assert code == 1 and "超过" in report


def test_default_deadline_covers_a_slow_sw008_ci_and_the_job_outlives_it() -> None:
    """首批实跑：sw008-ci 排队时跑了 53 分钟，旧的 45 分钟上限把它误判成红。"""
    import inspect
    import re

    deadline_min = inspect.signature(agg.run).parameters["deadline"].default / 60
    assert deadline_min >= 90
    text = (WORKFLOWS / agg.SELF).read_text(encoding="utf-8")
    timeout = int(re.search(r"timeout-minutes:\s*(\d+)", text).group(1))
    assert timeout > deadline_min  # 先由脚本自己判超时，不被 runner 强杀后无结论


def test_the_workflow_runs_from_the_base_and_never_checks_out_the_pr_head() -> None:
    text = (WORKFLOWS / agg.SELF).read_text(encoding="utf-8")
    assert "pull_request_target:" in text and "paths:" not in text  # 每个 PR 都报告，才能设必过
    assert "github.event.pull_request.base.ref" in text
    assert "head.ref" not in text and "refs/pull/" not in text  # PR 头不检出
    assert "contents: read" in text and "secrets." not in text


@pytest.mark.parametrize(
    ("path", "pattern", "expected"),
    [
        ("foo.md", "**/foo.md", True),  # 审计 402 P2-2：``**/`` 也匹配根目录
        ("a/b/foo.md", "**/foo.md", True),
        ("a/foo.mdx", "**/foo.md", False),
        ("a/b.txt", "a/*.txt", True),
        ("a/c/b.txt", "a/*.txt", False),  # ``*`` 不跨目录
        ("a/c/b.txt", "a/**", True),
        ("a", "a/**", False),
        (".github/workflows/x.yml", ".github/workflows/x.yml", True),
        (".github/workflows/xyml", ".github/workflows/x.yml", False),  # ``.`` 是字面点
        ("a/b.c", "a/?.c", True),
        ("a/bb.c", "a/?.c", False),
    ],
)
def test_path_matches_follows_the_github_glob(path: str, pattern: str, expected: bool) -> None:
    assert agg.path_matches(path, pattern) is expected


def test_sw008_ci_runs_on_push_only_for_main_but_still_on_every_pr_and_by_hand() -> None:
    """push 对所有分支开着时，每个 PR 的每次推送都跑两遍全量（push 与 pull_request 两个并发组），Windows 分片排队 80 分钟以上。"""
    text = (WORKFLOWS / "sw008-ci.yml").read_text(encoding="utf-8")
    on_block = text[text.index("\non:\n") : text.index("\npermissions:")]
    push_block = on_block[on_block.index("\n  push:\n") : on_block.index("\n  pull_request:\n")]
    assert "    branches: [main]" in push_block  # 没开 PR 的分支推送不再跑；main 每个提交仍要有结论
    pr_block = on_block[on_block.index("\n  pull_request:\n") : on_block.index("\n  workflow_dispatch:")]
    assert "branches: [main]" in pr_block and "paths:" in pr_block  # PR 那一轮不变
    assert "\n  workflow_dispatch:" in on_block  # 手动触发（受保护清单改动要手动跑）仍可用
