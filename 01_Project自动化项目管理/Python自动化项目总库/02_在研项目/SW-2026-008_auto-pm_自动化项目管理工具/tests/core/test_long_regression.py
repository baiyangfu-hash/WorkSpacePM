"""``pm verify`` does not run a long pytest regression; it accepts the ``long-run`` record that ran it (11-03 memory P1, PR-C)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from auto_pm.application.core import long_regression as lr
from auto_pm.application.core import pm_facade_service as facade_module
from auto_pm.application.core.acceptance_runner import worktree_environment
from auto_pm.contracts.plan_checklist import AcceptanceCheck
from auto_pm.infrastructure import long_run_core as core
from tests.plan_checklist_support import native_command, passing_command

PY = sys.executable
GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def _git(tree: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(tree), *args], check=True, capture_output=True, text=True, encoding="utf-8", env=GIT_ENV).stdout.strip()


def _repo(root: Path, cases: int) -> Path:
    """A committed worktree whose one test file collects ``cases`` test cases."""

    tree = root / "wt"
    tree.mkdir()
    (tree / "test_big.py").write_text(f"import pytest\n\n@pytest.mark.parametrize('n', range({cases}))\ndef test_case(n):\n    assert n >= 0\n", encoding="utf-8")
    _git(tree, "init", "-q")
    _git(tree, "config", "commit.gpgsign", "false")
    _git(tree, "add", "-A")
    _git(tree, "commit", "-q", "-m", "x")
    return tree


def _sub(root: Path, name: str) -> Path:
    path = root / name
    path.mkdir()
    return path


def _pytest_command(tree: Path | None = None, *, extra: tuple[str, ...] = ()) -> str:
    target = "{worktree}/test_big.py" if tree is None else str(tree / "test_big.py")
    return native_command(PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=", *extra, target)


def _run_started() -> str:
    return (datetime.now(UTC) - timedelta(hours=1)).isoformat()


def _record(root: Path, tree: Path, argv: tuple[str, ...], name: str = "rec", changes: dict[str, object] | None = None) -> Path:
    """A well-formed long-run record for ``argv`` on ``tree``; ``changes`` overrides fields (None deletes one)."""

    task = root / ".auto-pm" / "long-run" / name
    task.mkdir(parents=True)
    log = task / "run.log"
    log.write_bytes(LOG_TEXT)
    began = datetime.now(UTC)
    status: dict[str, object] = {
        "schema_version": "long-run.v1", "name": name, "command": list(argv), "cwd": str(root), "worktree": str(tree),
        "git_head": _git(tree, "rev-parse", "HEAD"), "git_dirty": False, "mem_guard": True, "detached": True, "state": "DONE",
        "exit_code": 0, "started_at": began.isoformat(), "ended_at": (began + timedelta(seconds=5)).isoformat(), "env_stripped": [],
        "log": str(log), "log_sha256": hashlib.sha256(LOG_TEXT).hexdigest(), "log_bytes": len(LOG_TEXT), "peak_committed_gib": 21.5,
    }
    for key, value in (changes or {}).items():
        if value is None:
            status.pop(key, None)
        else:
            status[key] = value
    (task / "status.json").write_text(json.dumps(status), encoding="utf-8")
    guard: dict[str, object] = {
        "samples": 2, "peak_committed_gib": 21.5, "started_at": began.isoformat(), "last_sample_at": (began + timedelta(seconds=3)).isoformat()
    }
    (task / "guard.json").write_text(json.dumps(guard), encoding="utf-8")
    return task


def _rewrite_log(task: Path, text: bytes) -> None:
    """Replace the log and keep the record consistent (size and SHA-256), so only the log's content is under test."""

    (task / "run.log").write_bytes(text)
    status = json.loads((task / "status.json").read_text(encoding="utf-8"))
    status.update({"log_sha256": hashlib.sha256(text).hexdigest(), "log_bytes": len(text)})
    (task / "status.json").write_text(json.dumps(status), encoding="utf-8")


def _rewrite_guard(task: Path, **changes: object) -> None:
    guard = json.loads((task / "guard.json").read_text(encoding="utf-8"))
    guard.update(changes)
    (task / "guard.json").write_text(json.dumps(guard), encoding="utf-8")


LOG_TEXT = b"...\n3 passed in 0.01s\n"


def _argv(tree: Path) -> tuple[str, ...]:
    return (PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=", str(tree / "test_big.py"))


def _find(root: Path, tree: Path, *, cases: int | None = 3, **kwargs: object) -> tuple[dict[str, object] | None, str]:
    return lr.find_evidence(root, _argv(tree), 0, worktree=tree, run_started=str(kwargs.get("run_started", _run_started())), cases=cases)


# ---------------------------------------------------------------- what counts as long
def test_only_a_pytest_command_with_more_than_100_cases_is_long(tmp_path: Path) -> None:
    small = _repo(_sub(tmp_path, "s"), 3)
    big = _repo(_sub(tmp_path, "b"), 101)
    env = {"AUTO_PM_RUN_WORKTREE": str(big)}

    short = lr.classify(AcceptanceCheck(command=_pytest_command(small), expected_exit_code=0), cwd=tmp_path, extra_env={})
    long = lr.classify(AcceptanceCheck(command=_pytest_command(big), expected_exit_code=0), cwd=tmp_path, extra_env=env)
    edge = lr.classify(AcceptanceCheck(command=_pytest_command(_repo(_sub(tmp_path, "e"), 100)), expected_exit_code=0), cwd=tmp_path, extra_env={})

    assert (short.long, short.cases) == (False, 3)
    assert (long.long, long.cases) == (True, 101) and "101" in long.reason
    assert (edge.long, edge.cases) == (False, 100)  # "more than 100": exactly 100 is not long


def test_a_command_that_is_not_pytest_or_only_collects_is_never_long(tmp_path: Path) -> None:
    assert lr.classify(AcceptanceCheck(command=passing_command(), expected_exit_code=0), cwd=tmp_path, extra_env={}).long is False
    plan_check = native_command(PY, "-B", "main.py", "plc", "check", "DJ-2026-001")
    assert lr.classify(AcceptanceCheck(command=plan_check, expected_exit_code=0), cwd=tmp_path, extra_env={}).long is False
    collect_only = lr.classify(AcceptanceCheck(command=_pytest_command(tmp_path, extra=("--collect-only",)), expected_exit_code=0), cwd=tmp_path, extra_env={})
    assert collect_only.long is False and "只收集" in collect_only.reason


def test_a_pytest_command_whose_size_cannot_be_counted_counts_as_long(tmp_path: Path) -> None:
    result = lr.classify(AcceptanceCheck(command=_pytest_command(tmp_path / "nowhere"), expected_exit_code=0), cwd=tmp_path, extra_env={})

    assert result.long is True and result.cases is None and "数不出用例数" in result.reason


def test_the_count_is_read_from_every_shape_of_pytest_collection_output() -> None:
    assert lr._count("tests/a.py::t1\n\n1234 tests collected in 2.5s") == 1234
    assert lr._count("1 test collected in 0.01s") == 1
    assert lr._count("5/200 tests collected (195 deselected) in 0.1s") == 5
    assert lr._count("no tests collected in 0.01s") == 0
    assert lr._count("a/test_x.py: 30\nb/test_y.py: 12\n") == 42  # -qq: per-file counts, no total
    assert lr._count("\n".join(f"f{n}.py: 1" for n in range(25))) is None  # the runner's 20 line tail may have cut it
    assert lr._count("ERROR: file or directory not found") is None


# ---------------------------------------------------------------- what counts as evidence
def test_a_matching_record_is_accepted(tmp_path: Path) -> None:
    tree = _repo(tmp_path, 3)
    _record(tmp_path, tree, _argv(tree), name="good")

    status, why = _find(tmp_path, tree)

    assert why == "" and status is not None and status["name"] == "good"


@pytest.mark.parametrize(
    ("change", "needle"),
    [
        ({"state": "STOPPED"}, "被停止的不算"),
        ({"state": "RUNNING"}, "还没有正常结束"),
        ({"exit_code": 1}, "退出码是 1"),
        ({"exit_code": None}, "退出码是 None"),
        ({"mem_guard": False}, "不是脱离终端并带内存守卫"),
        ({"detached": False}, "不是脱离终端并带内存守卫"),
        ({"git_dirty": True}, "未提交的改动"),
        ({"git_dirty": None}, "未提交的改动"),
        ({"git_head": ""}, "代码变了"),
        ({"git_head": "0" * 40}, "代码变了"),
        ({"worktree": "/somewhere/else"}, "判的不是这个 Run 的工作树"),
        ({"worktree": None}, "判的不是这个 Run 的工作树"),
        ({"cwd": "/somewhere/else"}, "验收命令是在控制根"),
        ({"ended_at": (datetime.now(UTC) - timedelta(hours=3)).isoformat()}, "不在本 Run 创建之后"),
        ({"ended_at": "garbage"}, "不在本 Run 创建之后"),
        ({"log_sha256": "0" * 64}, "SHA-256 对不上"),
        ({"env_stripped": None}, "没有 env_stripped"),
        ({"started_at": None}, "起止时间读不出"),
    ],
)
def test_a_record_that_breaks_any_one_condition_is_refused_with_the_reason(tmp_path: Path, change: dict[str, object], needle: str) -> None:
    tree = _repo(tmp_path, 3)
    _record(tmp_path, tree, _argv(tree), changes=change)

    status, why = _find(tmp_path, tree)

    assert status is None and needle in why


def test_a_guard_that_never_sampled_or_left_no_file_is_not_a_guard(tmp_path: Path) -> None:
    tree = _repo(tmp_path, 3)
    task = _record(tmp_path, tree, _argv(tree))
    (task / "guard.json").write_text(json.dumps({"samples": 0}), encoding="utf-8")
    assert "守卫没有采样记录" in _find(tmp_path, tree)[1]

    (task / "guard.json").unlink()
    assert "守卫没有采样记录" in _find(tmp_path, tree)[1]


@pytest.mark.parametrize(
    ("text", "needle"),
    [
        (b"collected 3 items\n...\n", "找不到 pytest 收尾行"),
        (b"", "找不到 pytest 收尾行"),
        (b"1 passed, 2 deselected in 0.01s\n", "deselect"),
        (b"1 passed in 0.01s\n", "共 1 个用例，而收集阶段数出 3 个"),
        (b"2 passed, 3 skipped in 0.01s\n", "共 5 个用例，而收集阶段数出 3 个"),
        (b"\x1b[31m1 failed\x1b[0m, 1 passed, 3 deselected, 1 warning in 0.5s\n", "deselect"),
    ],
)
def test_the_log_must_end_with_a_pytest_summary_that_ran_every_collected_case_and_deselected_none(tmp_path: Path, text: bytes, needle: str) -> None:
    tree = _repo(tmp_path, 3)
    task = _record(tmp_path, tree, _argv(tree))
    _rewrite_log(task, text)

    status, why = _find(tmp_path, tree)

    assert status is None and needle in why


def test_the_summary_line_is_read_in_every_shape_pytest_prints_it(tmp_path: Path) -> None:
    tree = _repo(tmp_path, 3)
    task = _record(tmp_path, tree, _argv(tree))
    shapes = [
        (b"=========== 2 passed, 1 skipped in 1.20s ===========\n", 3),
        (b"2 passed, 1 xfailed, 1 warning in 0.10s (0:00:00)\n", 3),
        (b"1 failed, 1 passed, 1 error in 3.50s\n", 3),
        (b"x" * 200_000 + b"\n3 passed in 0.01s\n", 3),  # a long log: only the tail is read
    ]
    for text, cases in shapes:
        _rewrite_log(task, text)
        assert _find(tmp_path, tree, cases=cases)[1] == "", text
    _rewrite_log(task, b"7 passed in 0.01s\n")
    assert _find(tmp_path, tree, cases=None)[1] == ""  # a size nobody could count: the line must still exist and deselect nothing
    _rewrite_log(task, b"7 passed, 1 deselected in 0.01s\n")
    assert "deselect" in _find(tmp_path, tree, cases=None)[1]


def test_a_pytest_addopts_probe_that_picks_one_case_is_not_the_regression(tmp_path: Path) -> None:
    """Audit 578: a worker started with PYTEST_ADDOPTS="-k test_1" ran a few cases and still looked like the whole suite."""

    tree = _repo(tmp_path, 3)
    task = _record(tmp_path, tree, _argv(tree))
    _rewrite_log(task, b"1 passed, 2 deselected in 0.01s\n")

    assert _find(tmp_path, tree)[0] is None


@pytest.mark.parametrize(
    ("guard", "needle"),
    [
        ({"started_at": None}, "起止时间读不出"),
        ({"last_sample_at": None}, "起止时间读不出"),
        ({"started_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat()}, "不在任务的启动和结束之间"),
        ({"last_sample_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()}, "不在任务的启动和结束之间"),
        ({"samples": 500}, "与任务时长"),
    ],
)
def test_the_guard_must_have_watched_this_job_in_time_and_in_number(tmp_path: Path, guard: dict[str, object], needle: str) -> None:
    tree = _repo(tmp_path, 3)
    task = _record(tmp_path, tree, _argv(tree))
    stored = json.loads((task / "guard.json").read_text(encoding="utf-8"))
    for key, value in guard.items():
        if value is None:
            stored.pop(key)
        else:
            stored[key] = value
    (task / "guard.json").write_text(json.dumps(stored), encoding="utf-8")

    status, why = _find(tmp_path, tree)

    assert status is None and needle in why


def test_a_long_job_needs_about_one_guard_sample_per_two_minutes(tmp_path: Path) -> None:
    tree = _repo(tmp_path, 3)
    began = datetime.now(UTC)
    task = _record(tmp_path, tree, _argv(tree), changes={"started_at": began.isoformat(), "ended_at": (began + timedelta(hours=1)).isoformat()})
    _rewrite_guard(task, started_at=began.isoformat(), last_sample_at=(began + timedelta(minutes=59)).isoformat(), samples=3)

    assert "与任务时长 3600 秒对不上" in _find(tmp_path, tree)[1]

    _rewrite_guard(task, samples=170)  # one every ~21 seconds, what the real guard writes
    assert _find(tmp_path, tree)[1] == ""


def test_the_refusal_and_the_accepted_note_both_say_the_record_is_a_plain_file_not_a_proof(tmp_path: Path) -> None:
    tree = _repo(tmp_path, 101)
    check = AcceptanceCheck(command=_pytest_command(), expected_exit_code=0)
    env = worktree_environment(tree, tmp_path)

    refused = lr.run_checks((check,), cwd=tmp_path, extra_env=env, worktree=str(tree), run_id="R", run_started=_run_started())[0]
    assert "不是密码学证明" in refused.error

    tiny = _repo(_sub(tmp_path, "t"), 3)
    note = lr._evidence_run(AcceptanceCheck(command=_pytest_command(tiny), expected_exit_code=0), _argv(tiny), {"name": "n", "exit_code": 0})
    assert "不是密码学证明" in note.output_tail


def test_a_changed_or_dirty_worktree_since_the_run_makes_the_record_stale(tmp_path: Path) -> None:
    tree = _repo(tmp_path, 3)
    _record(tmp_path, tree, _argv(tree))
    assert _find(tmp_path, tree)[0] is not None

    (tree / "test_big.py").write_text("def test_x():\n    pass\n", encoding="utf-8")  # edited after the run, not committed
    assert "工作树现在有未提交的改动" in _find(tmp_path, tree)[1]

    _git(tree, "commit", "-q", "-am", "y")  # committed: HEAD moved
    assert "代码变了" in _find(tmp_path, tree)[1]


def test_other_commands_and_other_schemas_are_not_this_commands_evidence(tmp_path: Path) -> None:
    tree = _repo(tmp_path, 3)
    _record(tmp_path, tree, (PY, "-m", "pytest", "other"), name="other")
    _record(tmp_path, tree, _argv(tree), name="oldschema", changes={"schema_version": "long-run.v0"})

    status, why = _find(tmp_path, tree)

    assert status is None and "没有找到同一条命令的 long-run 记录" in why
    assert _find(tmp_path / "nothing", tree)[1] == "没有找到同一条命令的 long-run 记录"


def test_the_newest_acceptable_record_wins_and_a_bad_newer_one_is_only_mentioned(tmp_path: Path) -> None:
    tree = _repo(tmp_path, 3)
    _record(tmp_path, tree, _argv(tree), name="a-good")
    _record(tmp_path, tree, _argv(tree), name="b-bad", changes={"exit_code": 1})

    status, _why = _find(tmp_path, tree)

    assert status is not None and status["name"] == "a-good"


# ---------------------------------------------------------------- the whole check
def test_a_long_check_without_a_record_is_refused_with_the_exact_command_and_a_short_one_still_runs(tmp_path: Path) -> None:
    tree = _repo(tmp_path, 101)
    checks = (AcceptanceCheck(command=passing_command(), expected_exit_code=0), AcceptanceCheck(command=_pytest_command(), expected_exit_code=0))

    runs = lr.run_checks(
        checks, cwd=tmp_path, extra_env=worktree_environment(tree, tmp_path), worktree=str(tree), run_id="RUN-1", run_started=_run_started()
    )

    assert [run.passed for run in runs] == [True, False]  # order kept, the short one really ran
    refused = runs[1]
    assert refused.exit_code is None
    assert "长回归" in refused.error and "收集到 101 个用例" in refused.error and "没有找到同一条命令的 long-run 记录" in refused.error
    assert "long-run start --name verify-RUN-1-2-" in refused.error and f"--worktree {tree}" in refused.error and f"--cwd {tmp_path}" in refused.error
    assert f"{tree}/test_big.py" in refused.error  # {worktree} already replaced (the template's own "/" stays, also on Windows): copy and run


def test_the_printed_command_really_produces_evidence_that_the_next_verify_accepts(tmp_path: Path) -> None:
    tree = _repo(tmp_path, 101)
    check = AcceptanceCheck(command=_pytest_command(), expected_exit_code=0)
    env = worktree_environment(tree, tmp_path)
    started = _run_started()
    first = lr.run_checks((check,), cwd=tmp_path, extra_env=env, worktree=str(tree), run_id="RUN-2", run_started=started)[0]
    assert not first.passed

    # what the agent does: start the job with the very arguments the message printed
    argv = (PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=", f"{tree}/test_big.py")
    core.start(tmp_path, "evidence", list(argv), cwd=tmp_path, worktree=tree, poll_seconds=0.2, env={"AUTO_PM_RUN_WORKTREE": str(tree)})
    end = time.monotonic() + 120
    while time.monotonic() < end and core.read_status(core.run_directory(tmp_path, "evidence"))["state"] not in {"DONE", "FAILED"}:
        time.sleep(0.2)
    assert core.read_status(core.run_directory(tmp_path, "evidence"))["state"] == "DONE"
    guard_file = core.run_directory(tmp_path, "evidence") / "guard.json"
    end = time.monotonic() + 60
    while time.monotonic() < end and not (guard_file.is_file() and json.loads(guard_file.read_text(encoding="utf-8")).get("samples", 0) >= 1):
        time.sleep(0.2)  # a Windows guard process starts slowly: wait for its first sample instead of guessing a delay

    second = lr.run_checks((check,), cwd=tmp_path, extra_env=env, worktree=str(tree), run_id="RUN-2", run_started=started)[0]

    assert second.passed and second.exit_code == 0 and "long-run 记录 evidence" in second.output_tail, (second.error, second.output_tail)
    assert second.output_sha256 and second.output_bytes > 0
    # a terminal run of the same command leaves no such record, so it would not have counted
    assert not lr.run_checks((check,), cwd=tmp_path / "other-root", extra_env=env, worktree=str(tree), run_id="RUN-2", run_started=started)[0].passed


def test_pm_verify_blocks_on_a_long_check_without_evidence_and_the_report_says_why(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.core.test_declared_dirty_consistency import _verifying

    _, facade, _ = _verifying(tmp_path)
    tree = _repo(_sub(tmp_path, "scratch"), 101)
    check = AcceptanceCheck(command=_pytest_command(), expected_exit_code=0)
    monkeypatch.setattr(facade_module.PmFacadeService, "_approved_acceptance_checks", lambda _self, _mission: (check,))

    note, block = facade._run_approved_acceptance_checks(
        facade._missions.get("MISSION-PM-001"), SimpleNamespace(run_id="RUN-GATE-001", worktree_path=str(tree), created_at=_run_started())
    )

    assert block and "第 1 条验收命令" in note and "long-run start" in note and "收集到 101 个用例" in note
    (report,) = sorted((tmp_path / ".auto-pm" / "reports" / "acceptance").glob("*.json"))
    assert json.loads(report.read_text(encoding="utf-8"))["all_passed"] is False
