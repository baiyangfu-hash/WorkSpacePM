"""本机合并（卡 311，CHG-SCPT-2026-718）：``scripts/pm_merge.py`` 在临时 git 仓库里真合并、真装钩子。

门禁（``main.py gate precheck``/``gate run``）用假的代替，其余全是真 git：控制根、工位、当 GitHub 用的裸仓库都在临时目录。
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

PROJECT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT / "scripts" / "pm_merge.py"
CARD = "领卡占位: 311"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pm_merge_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def pm() -> ModuleType:
    return _load()


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _identity(cwd: Path) -> None:
    git(cwd, "config", "user.name", "tester")
    git(cwd, "config", "user.email", "tester@example.invalid")
    git(cwd, "config", "core.autocrlf", "false")


@pytest.fixture
def repo(tmp_path: Path, pm: ModuleType, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "--bare", "-b", "main", str(origin))
    root = tmp_path / "root"
    git(tmp_path, "init", "-b", "main", str(root))
    _identity(root)
    (root / ".gitignore").write_text(".auto-pm/\n", encoding="utf-8")
    (root / "README.md").write_text("hello\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "init")
    git(root, "remote", "add", "origin", str(origin))
    git(root, "push", "-u", "origin", "main")
    wt = root / ".auto-pm" / "worktrees" / "w1"
    git(root, "worktree", "add", "-b", "claude/311", str(wt), "main")
    _identity(wt)
    gates: list[bool] = []

    def fake_gates(_root: Path, _worktree: Path, full: bool) -> Any:
        gates.append(full)
        return pm.GateResult(repo_state.gate_ok, [f"假门禁 full={full}"])

    repo_state = SimpleNamespace(
        root=root, origin=origin, wt=wt, gates=gates, gate_ok=True, tmp=tmp_path
    )
    monkeypatch.setattr(pm, "run_gates", fake_gates)
    return repo_state


def commit(cwd: Path, files: dict[str, str], message: str) -> str:
    for name, text in files.items():
        path = cwd / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        git(cwd, "add", name)
    git(cwd, "commit", "-m", message)
    return git(cwd, "rev-parse", "HEAD").stdout.strip()


def run(pm: ModuleType, root: Path, *args: str) -> int:
    return int(pm.main(["--root", str(root), *args]))


def rev(cwd: Path, ref: str) -> str:
    return git(cwd, "rev-parse", ref).stdout.strip()


def push_from_other_computer(repo: SimpleNamespace) -> str:
    other = repo.tmp / "other"
    git(repo.tmp, "clone", str(repo.origin), str(other))
    _identity(other)
    sha = commit(other, {"other.md": "from the other computer\n"}, "另一台电脑的改动")
    git(other, "push", "origin", "main")
    return sha


def test_merge_records_the_merge_and_pushes_a_backup(
    pm: ModuleType, repo: SimpleNamespace, capsys: Any
) -> None:
    sha = commit(repo.wt, {"docs/a.md": "a\n"}, f"docs：加一页\n\n{CARD}")
    assert run(pm, repo.root, "merge", "w1") == 0
    head = rev(repo.root, "main")
    message = git(repo.root, "log", "-1", "--format=%B").stdout
    assert pm.MERGE_MARK in message and CARD in message
    assert git(repo.root, "merge-base", "--is-ancestor", sha, "main", check=False).returncode == 0
    entry = pm.read_log(repo.root)[-1]
    assert entry["merge_sha"] == head and entry["card"] == "311" and entry["pushed"] is True
    assert rev(repo.origin, "main") == head
    assert repo.gates == [False]
    assert "退回办法：git revert -m 1" in capsys.readouterr().out


def test_without_a_card_line_nothing_is_merged(pm: ModuleType, repo: SimpleNamespace) -> None:
    before = rev(repo.root, "main")
    commit(repo.wt, {"docs/a.md": "a\n"}, "docs：没写卡号")
    assert run(pm, repo.root, "merge", "w1") == 1
    assert rev(repo.root, "main") == before and pm.read_log(repo.root) == []


def test_uncommitted_work_in_the_worktree_is_refused(
    pm: ModuleType, repo: SimpleNamespace, capsys: Any
) -> None:
    commit(repo.wt, {"docs/a.md": "a\n"}, f"docs\n\n{CARD}")
    (repo.wt / "docs" / "a.md").write_text("changed\n", encoding="utf-8")
    assert run(pm, repo.root, "merge", "w1") == 1
    assert "没提交的改动" in capsys.readouterr().out


def test_a_branch_without_the_latest_main_is_refused(
    pm: ModuleType, repo: SimpleNamespace, capsys: Any
) -> None:
    commit(repo.wt, {"docs/a.md": "a\n"}, f"docs\n\n{CARD}")
    commit(repo.root, {"b.md": "b\n"}, "main 上的新提交")
    assert run(pm, repo.root, "merge", "w1") == 1
    assert "先在工位里合并 main" in capsys.readouterr().out


def _change_order(root: Path, number: str, state: str) -> None:
    folder = root / "P" / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-SCPT"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{number}.md").write_text(f"| 变更状态 | {state} |\n", encoding="utf-8")


def test_rule_files_need_an_approved_change_order_named_in_this_card(
    pm: ModuleType, repo: SimpleNamespace, capsys: Any
) -> None:
    commit(repo.wt, {"AGENTS.md": "rules\n"}, f"docs(rules)：[CHG-SCPT-2026-999] 改规则\n\n{CARD}")
    _change_order(repo.root, "CHG-SCPT-2026-999", "approved")
    assert run(pm, repo.root, "merge", "w1") == 1
    assert "没有本卡的实施卡" in capsys.readouterr().out
    card = "P/02_规划/311_别的单_PM.md"
    commit(repo.wt, {card: "本卡凭 CHG-SCPT-2026-111\n"}, f"docs(card)\n\n{CARD}")
    assert run(pm, repo.root, "merge", "w1") == 1, "提交说明引用的单没写在本卡里（拿别的旧单顶）"
    assert "写在本卡实施卡里" in capsys.readouterr().out
    commit(repo.wt, {card: "本卡凭 CHG-SCPT-2026-999\n"}, f"docs(card)\n\n{CARD}")
    for state in ("draft", "completed"):
        _change_order(repo.root, "CHG-SCPT-2026-999", state)
        assert run(pm, repo.root, "merge", "w1") == 1, state
    _change_order(repo.root, "CHG-SCPT-2026-999", "approved")
    assert run(pm, repo.root, "merge", "w1") == 0
    entry = pm.read_log(repo.root)[-1]
    assert entry["user_paths"] == ["AGENTS.md"] and entry["chgs"] == ["CHG-SCPT-2026-999"]
    assert repo.gates[-1] is True, "要用户点头的那一类要跑全量门禁"


def test_deleting_files_outside_the_cockpit_needs_the_user(
    pm: ModuleType, repo: SimpleNamespace, capsys: Any
) -> None:
    inside = pm.COCKPIT_PREFIX + "scripts/old_tool.py"
    commit(repo.root, {inside: "x\n"}, "驾驶舱里的一个旧脚本")
    git(repo.wt, "merge", "--quiet", "main")
    git(repo.wt, "rm", "--quiet", inside)
    git(repo.wt, "commit", "-m", f"删驾驶舱里不用的脚本\n\n{CARD}")
    assert run(pm, repo.root, "merge", "w1") == 0, "删驾驶舱自己的文件是“直接做”"
    git(repo.wt, "merge", "--quiet", "main")
    git(repo.wt, "rm", "--quiet", "README.md")
    git(repo.wt, "commit", "-m", f"删业务文件\n\n{CARD}")
    assert run(pm, repo.root, "merge", "w1") == 1
    assert "README.md" in capsys.readouterr().out


def test_deleting_cockpit_records_needs_the_user(
    pm: ModuleType, repo: SimpleNamespace, capsys: Any
) -> None:
    record = pm.COCKPIT_PREFIX + "04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-001.md"
    commit(repo.root, {record: "| 变更状态 | completed |\n"}, "一张旧变更单")
    git(repo.wt, "merge", "--quiet", "main")
    git(repo.wt, "rm", "--quiet", record)
    git(repo.wt, "commit", "-m", f"删变更单原件\n\n{CARD}")
    assert run(pm, repo.root, "merge", "w1") == 1
    assert "CHG-SCPT-2026-001.md" in capsys.readouterr().out


@pytest.mark.parametrize(
    "path",
    [
        "0100_PLC自动化/DJ/02_PLC程序/FB_A.scl",
        "SW8/templates/plc-standard/x.md",
        "a/scripts/pm_merge.py",
    ],
)
def test_plc_files_templates_and_the_merge_command_itself_need_the_user(
    pm: ModuleType, path: str
) -> None:
    assert pm.needs_user(path)
    assert not pm.needs_user("SW8/scripts/pm_flows.py")


def test_a_failed_gate_changes_nothing(pm: ModuleType, repo: SimpleNamespace, capsys: Any) -> None:
    before = rev(repo.root, "main")
    commit(repo.wt, {"docs/a.md": "a\n"}, f"docs\n\n{CARD}")
    repo.gate_ok = False
    assert run(pm, repo.root, "merge", "w1") == 1
    assert "本机门禁没过" in capsys.readouterr().out
    assert rev(repo.root, "main") == before and rev(repo.origin, "main") == before


def test_changes_from_the_other_computer_must_be_synced_first(
    pm: ModuleType, repo: SimpleNamespace, capsys: Any
) -> None:
    commit(repo.wt, {"docs/a.md": "a\n"}, f"docs\n\n{CARD}")
    remote = push_from_other_computer(repo)
    assert run(pm, repo.root, "merge", "w1") == 1
    assert "先跑 sync" in capsys.readouterr().out
    assert run(pm, repo.root, "sync") == 0
    assert rev(repo.root, "main") == remote


def test_github_off_never_touches_the_network(pm: ModuleType, repo: SimpleNamespace) -> None:
    before_origin = rev(repo.origin, "main")
    assert run(pm, repo.root, "github-mode", "关") == 0
    assert pm.read_mode(repo.root) == "关"
    commit(repo.wt, {"docs/a.md": "a\n"}, f"docs\n\n{CARD}")
    assert run(pm, repo.root, "merge", "w1") == 0
    assert rev(repo.origin, "main") == before_origin
    assert pm.read_log(repo.root)[-1]["pushed"] is False
    assert run(pm, repo.root, "sync") == 1 and run(pm, repo.root, "push") == 1


def test_the_default_mode_is_backup(pm: ModuleType, repo: SimpleNamespace) -> None:
    assert pm.read_mode(repo.root) == "备份"


def test_a_copy_that_differs_only_in_line_endings_is_replaced(
    pm: ModuleType, repo: SimpleNamespace
) -> None:
    commit(repo.wt, {"docs/chg.md": "line1\nline2\n"}, f"docs：变更单原件入库\n\n{CARD}")
    copy = repo.root / "docs" / "chg.md"
    copy.parent.mkdir(parents=True, exist_ok=True)
    copy.write_bytes(b"line1\r\nline2\r\n")
    assert run(pm, repo.root, "merge", "w1") == 0
    assert copy.read_bytes() == b"line1\nline2\n"
    assert pm.read_log(repo.root)[-1]["replaced"] == ["docs/chg.md"]


def test_a_different_uncommitted_copy_is_refused_and_kept(
    pm: ModuleType, repo: SimpleNamespace, capsys: Any
) -> None:
    commit(repo.wt, {"docs/chg.md": "line1\n"}, f"docs\n\n{CARD}")
    copy = repo.root / "docs" / "chg.md"
    copy.parent.mkdir(parents=True, exist_ok=True)
    copy.write_bytes(b"something else\n")
    assert run(pm, repo.root, "merge", "w1") == 1
    assert "不只差行尾" in capsys.readouterr().out
    assert copy.read_bytes() == b"something else\n"


def test_unrelated_uncommitted_changes_in_the_control_root_are_refused(
    pm: ModuleType, repo: SimpleNamespace, capsys: Any
) -> None:
    commit(repo.wt, {"docs/a.md": "a\n"}, f"docs\n\n{CARD}")
    (repo.root / "README.md").write_text("edited in the control root\n", encoding="utf-8")
    assert run(pm, repo.root, "merge", "w1") == 1
    assert "控制根有未提交的改动" in capsys.readouterr().out


def test_the_hook_blocks_direct_changes_to_main(pm: ModuleType, repo: SimpleNamespace) -> None:
    assert run(pm, repo.root, "install-hook") == 0
    before = rev(repo.root, "main")
    (repo.root / "direct.md").write_text("x\n", encoding="utf-8")
    git(repo.root, "add", "direct.md")
    assert git(repo.root, "commit", "-m", "直接提交到 main", check=False).returncode != 0
    side = commit(repo.wt, {"docs/a.md": "a\n"}, f"docs\n\n{CARD}")
    assert git(repo.root, "update-ref", "refs/heads/main", side, check=False).returncode != 0
    assert rev(repo.root, "main") == before
    git(repo.root, "reset", "--quiet", "HEAD", "direct.md")
    (repo.root / "direct.md").unlink()


def test_the_hook_lets_the_merge_command_and_github_sync_through(
    pm: ModuleType, repo: SimpleNamespace
) -> None:
    assert run(pm, repo.root, "install-hook") == 0
    commit(repo.wt, {"docs/a.md": "a\n"}, f"docs\n\n{CARD}")
    assert run(pm, repo.root, "merge", "w1") == 0
    remote = push_from_other_computer(repo)
    assert run(pm, repo.root, "sync") == 0
    assert rev(repo.root, "main") == remote


def test_the_hook_does_not_touch_other_branches(pm: ModuleType, repo: SimpleNamespace) -> None:
    assert run(pm, repo.root, "install-hook") == 0
    commit(repo.wt, {"docs/a.md": "a\n"}, "工位分支上的普通提交")


def test_someone_elses_hook_is_not_overwritten(pm: ModuleType, repo: SimpleNamespace) -> None:
    hook = repo.root / ".git" / "hooks" / "reference-transaction"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    assert run(pm, repo.root, "install-hook") == 1
    assert hook.read_text(encoding="utf-8") == "#!/bin/sh\nexit 0\n"


def test_verify_log_finds_commits_that_bypassed_the_merge_command(
    pm: ModuleType, repo: SimpleNamespace, capsys: Any
) -> None:
    start = rev(repo.root, "main")
    commit(repo.wt, {"docs/a.md": "a\n"}, f"docs\n\n{CARD}")
    assert run(pm, repo.root, "merge", "w1") == 0
    assert run(pm, repo.root, "verify-log", "--since", start) == 0
    sneaky = commit(repo.root, {"sneaky.md": "x\n"}, "没走本机合并的提交")
    capsys.readouterr()
    assert run(pm, repo.root, "verify-log", "--since", start) == 1
    out = capsys.readouterr().out
    assert sneaky[:12] in out and "agent 不要自己退" in out


def test_verify_log_accepts_merges_synced_from_the_other_computer(
    pm: ModuleType, repo: SimpleNamespace
) -> None:
    start = rev(repo.root, "main")
    commit(repo.wt, {"docs/a.md": "a\n"}, f"docs\n\n{CARD}")
    assert run(pm, repo.root, "merge", "w1") == 0
    log = repo.root / pm.STATE_DIR / pm.LOG_NAME
    log.unlink()
    assert run(pm, repo.root, "verify-log", "--since", start) == 0


def test_the_log_is_json_lines_outside_git(pm: ModuleType, repo: SimpleNamespace) -> None:
    commit(repo.wt, {"docs/a.md": "a\n"}, f"docs\n\n{CARD}")
    assert run(pm, repo.root, "merge", "w1") == 0
    lines = (repo.root / pm.STATE_DIR / pm.LOG_NAME).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["branch"] == "claude/311"
    assert git(repo.root, "status", "--porcelain").stdout.strip() == ""


def test_run_gates_passes_jobs_and_verifies_root_tests_when_outside_changes_exist(
    pm: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wt = tmp_path / "wt"
    (wt / "tests").mkdir(parents=True)
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(list(cmd))
        if "precheck" in cmd:
            payload = {
                "verdict": "UNVERIFIED",
                "outside_changes": ["双击启动驾驶舱.bat"],
                "steps": [
                    {"name": "ruff", "verdict": "PASS", "exit": 0},
                    {"name": "mypy", "verdict": "PASS", "exit": 0},
                    {"name": "pytest", "verdict": "PASS", "exit": 0},
                ],
            }
            return subprocess.CompletedProcess(cmd, 1, json.dumps(payload), "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(pm.subprocess, "run", fake_run)
    monkeypatch.setattr(pm, "managed_gate_receipt", lambda root, worktree: "托管凭证已核对")
    res = pm.run_gates(tmp_path, wt, True)
    assert res.ok
    assert "--jobs" in calls[0] and "--json" in calls[0] and "--defer-full" in calls[0]
    assert len(calls) == 2 and str(wt / "tests") in calls[1]


def test_chunk_paths_splits_large_release_path_lists_under_windows_limit(pm: ModuleType) -> None:
    paths = [f"00_Infrastructure/auto_pm/releases/1.3.3-d356fb1/auto_pm/mod_{i:04d}.py" for i in range(620)]
    batches = pm._chunk_paths(paths)
    assert len(batches) > 1
    assert [p for batch in batches for p in batch] == paths
    assert all(sum(len(p) + 3 for p in batch) <= pm.STATUS_BATCH_CHARS for batch in batches)


def test_control_root_copies_chunks_git_status_calls_for_many_untracked_files(
    pm: ModuleType, repo: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = {f"rel/file_{i:02d}_long_name_for_batching.txt": f"v{i}\n" for i in range(8)}
    sha = commit(repo.wt, files, f"add batch\n\n{CARD}")
    for rel, content in files.items():
        target = repo.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    monkeypatch.setattr(pm, "STATUS_BATCH_CHARS", 120)
    root_git = pm.Git(repo.root)
    real_run = root_git.run
    status_batches: list[list[str]] = []

    def spy_run(*args: str, **kwargs: Any) -> Any:
        if "--untracked-files=all" in args:
            sep = args.index("--")
            status_batches.append(list(args[sep + 1 :]))
        return real_run(*args, **kwargs)

    monkeypatch.setattr(root_git, "run", spy_run)
    replace = pm._control_root_copies(root_git, repo.root, sha, sorted(files))
    assert len(status_batches) >= 2
    assert replace == sorted(files)


def test_managed_gate_refuses_changed_base(
    pm: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def rev(_git: Any, ref: str) -> str:
        return {"HEAD": "a" * 40, "HEAD^{tree}": "b" * 40, "main": "c" * 40}[ref]

    record = {
        "id": "task",
        "backend": "github",
        "state": "passed",
        "handle": "12345",
        "detail": "digest",
        "candidate": {"commit": "a" * 40, "tree": "b" * 40, "base": "d" * 40},
    }
    monkeypatch.setattr(pm.Git, "rev", rev)
    monkeypatch.setattr(
        pm.subprocess, "run", lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, json.dumps(record), "")
    )
    with pytest.raises(pm.RefusedError, match="当前 main 不匹配"):
        pm.managed_gate_receipt(tmp_path, tmp_path / "worktree")
