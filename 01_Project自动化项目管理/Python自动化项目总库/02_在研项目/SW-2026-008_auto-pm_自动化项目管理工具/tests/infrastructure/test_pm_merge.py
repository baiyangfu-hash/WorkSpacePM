"""本机合并（卡 311，CHG-SCPT-2026-718）：``scripts/pm_merge.py`` 在临时 git 仓库里真合并、真装钩子。

门禁（``main.py gate precheck``/``gate run``）用假的代替，其余全是真 git：控制根、工位、当 GitHub 用的裸仓库都在临时目录。
"""

from __future__ import annotations

import importlib.util
import json
import shutil
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


def _audit(
    pm: ModuleType, repo: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, verdict: str = "PASS",
) -> int:
    monkeypatch.setenv("AUTO_PM_AGENT", "codex")
    monkeypatch.setenv("AUTO_PM_SESSION_ID", "abcdefffffffff")
    report = repo.tmp / "audit.md"
    base, candidate = rev(repo.root, "main"), rev(repo.wt, "HEAD")
    report.write_text(f"Independent review of {base}..{candidate}.\n", encoding="utf-8")
    return run(
        pm, repo.root, "audit-record", "w1", "--base", base,
        "--candidate", candidate, "--verdict", verdict, "--report", str(report),
    )


def test_rule_files_need_an_approved_change_order_named_in_this_card(
    pm: ModuleType, repo: SimpleNamespace, capsys: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = f"docs(rules)：[CHG-SCPT-2026-999] 改规则\n\n{CARD}"
    commit(repo.wt, {"AGENTS.md": "rules\n"}, message)
    _change_order(repo.root, "CHG-SCPT-2026-999", "approved")
    assert run(pm, repo.root, "merge", "w1") == 1
    assert "没有本卡的实施卡" in capsys.readouterr().out
    card = "SW-2026-008/04_监控/01_变更管理/03_实施卡/CARD-SW-2026-008-311_实施卡.md"
    commit(repo.wt, {card: "> 变更单：`CHG-SCPT-2026-111`\n"}, f"docs(card)\n\n{CARD}")
    assert run(pm, repo.root, "merge", "w1") == 1, "提交说明引用的单没写在本卡里（拿别的旧单顶）"
    assert "写在本卡实施卡里" in capsys.readouterr().out
    commit(repo.wt, {card: "> 变更单：`CHG-SCPT-2026-999`\n"}, f"docs(card)\n\n{CARD}")
    orders = pm.find_change_orders(repo.root, "CHG-SCPT-2026-999")
    assert len(orders) == 1
    monkeypatch.setattr(pm, "find_change_orders", lambda _root, _number, _pid="": orders)
    for state in ("draft", "completed"):
        _change_order(repo.root, "CHG-SCPT-2026-999", state)
        assert run(pm, repo.root, "merge", "w1") == 1, state
    _change_order(repo.root, "CHG-SCPT-2026-999", "approved")
    monkeypatch.setattr(pm, "_card_precheck", lambda *_: [card])
    orders[0].write_text(
        f"| 变更状态 | approved |\n| 涉及文件/交付物 | {card}<br>AGENTS.md |\n",
        encoding="utf-8",
    )
    assert run(pm, repo.root, "merge", "w1") == 1
    assert "超出实施卡可改范围：AGENTS.md" in capsys.readouterr().out
    monkeypatch.setattr(pm, "_card_precheck", lambda *_: [card, "AGENTS.md"])
    monkeypatch.setattr(pm, "_check_card_tier", lambda *_: None)
    assert run(pm, repo.root, "merge", "w1") == 1
    assert "缺少对应当前 main 和候选提交的独立审计凭证" in capsys.readouterr().out
    assert not repo.gates
    assert _audit(pm, repo, monkeypatch, "FAIL") == 0
    assert run(pm, repo.root, "merge", "w1") == 1
    assert "独立审计未放行" in capsys.readouterr().out
    assert _audit(pm, repo, monkeypatch) == 0
    commit(repo.wt, {"AGENTS.md": "updated rules\n"}, message)
    assert run(pm, repo.root, "merge", "w1") == 1
    assert "缺少对应当前 main 和候选提交的独立审计凭证" in capsys.readouterr().out
    assert _audit(pm, repo, monkeypatch) == 0
    assert run(pm, repo.root, "merge", "w1") == 0
    entry = pm.read_log(repo.root)[-1]
    assert entry["user_paths"] == ["AGENTS.md"] and entry["chgs"] == ["CHG-SCPT-2026-999"]
    assert entry["audit"]["candidate"] == rev(repo.wt, "HEAD")
    assert repo.gates[-1] is True, "要用户点头的那一类要跑全量门禁"


def test_card_tier_is_checked_against_the_actual_diff(pm: ModuleType, repo: SimpleNamespace) -> None:
    tools = repo.root / pm.COCKPIT_PREFIX / "tests" / "tools"
    tools.mkdir(parents=True)
    for name in ("tier_classifier.py", "tier_core_list.json"):
        shutil.copyfile(PROJECT / "tests" / "tools" / name, tools / name)
    base = rev(repo.root, "main")
    candidate = commit(repo.wt, {"AGENTS.md": "rules\n"}, f"rules\n\n{CARD}")
    with pytest.raises(pm.RefusedError, match="实施卡档次核验未过"):
        pm._check_card_tier(repo.root, "> 档次：文档档", base, candidate)
    pm._check_card_tier(repo.root, "> 档次：核心档", base, candidate)


def test_formal_change_with_historical_branch_alias_checks_scope_and_audit(
    pm: ModuleType, repo: SimpleNamespace, capsys: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    change = "CHG-SCPT-2026-733"
    message = f"feat(board): [{change}] improve board\n\n领卡占位: {change}"
    card = "SW-2026-008/04_监控/01_变更管理/03_实施卡/CARD-SW-2026-008-733_看板.md"
    commit(repo.wt, {"docs/a.md": "prototype\n"}, f"docs(board): prototype\n\n{CARD}")
    commit(repo.wt, {"docs/b.md": "board\n"}, message)
    assert run(pm, repo.root, "merge", "w1") == 1
    assert "没有本卡的实施卡" in capsys.readouterr().out
    commit(repo.wt, {card: f"> 变更单：`{change}`\n"}, message)
    order = repo.root / "SW-2026-008" / "04_监控" / "01_变更管理" / "01_变更单" / f"{change}.md"
    order.parent.mkdir(parents=True)
    order.write_text(
        f"| 变更状态 | approved |\n| 涉及文件/交付物 | {card}<br>docs |\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(pm, "_card_precheck", lambda *_: [card, "docs/b.md"])
    assert run(pm, repo.root, "merge", "w1") == 1
    assert "超出实施卡可改范围：docs/a.md" in capsys.readouterr().out
    monkeypatch.setattr(pm, "_card_precheck", lambda *_: [card, "docs"])
    monkeypatch.setattr(pm, "_check_card_tier", lambda *_: None)
    assert run(pm, repo.root, "merge", "w1") == 1
    assert "独立审计凭证" in capsys.readouterr().out
    assert not repo.gates
    assert _audit(pm, repo, monkeypatch) == 0
    assert run(pm, repo.root, "merge", "w1") == 0
    saved = pm.read_log(repo.root)[-1]
    assert saved["card"] == change
    assert saved["user_paths"] == []
    assert saved["audit"]["candidate"] == rev(repo.wt, "HEAD")
    assert repo.gates == [False]


def test_historical_change_reference_keeps_direct_merge(pm: ModuleType, repo: SimpleNamespace) -> None:
    commit(
        repo.wt, {"docs/example.md": "example\n"},
        f"docs: add example\n\n参见历史 CHG-SCPT-2026-733。\n\n{CARD}",
    )
    assert run(pm, repo.root, "merge", "w1") == 0
    assert "audit" not in pm.read_log(repo.root)[-1]


def test_main_transaction_rechecks_the_reviewed_base(pm: ModuleType, repo: SimpleNamespace) -> None:
    pm.write_mode(repo.root, "关")
    commit(repo.wt, {"candidate.md": "ready\n"}, f"candidate\n\n{CARD}")
    plan = pm.plan_merge(repo.root, "w1")
    latest = commit(repo.root, {"other.md": "synced\n"}, "other main update")
    with pytest.raises(pm.RefusedError, match="main 或候选已变动"):
        pm.do_merge(repo.root, plan, pm.GateResult(True), "关")
    assert rev(repo.root, "main") == latest
    assert not (repo.root / "candidate.md").exists()
    with pm._main_transaction(repo.root, latest, plan.sha) as transaction:
        token = transaction.env[pm.TOKEN_ENV]
        correct = f"{latest} {plan.sha} {pm.MAIN_REF}"
        stale = f"{plan.base} {plan.sha} {pm.MAIN_REF}"
        assert pm.hook_allows(repo.root, [correct, stale], token) == [stale]
        assert pm.hook_allows(repo.root, [correct], None) == [correct]


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


def _deployed_archive(repo: SimpleNamespace) -> tuple[str, dict[str, bytes], str]:
    infra = "00_Infrastructure/auto_pm"
    release = "1.3.3-a123456"
    number = "CHG-SCPT-2026-999"
    ledger = "P/04_监控/01_变更管理/02_变更记录/01_版本变更台账.md"
    record = f"P/04_监控/01_变更管理/01_变更单/CHG-SCPT/{number}.md"
    pointers = ("active_release.json", "previous_release.json", "deployment_manifest.json")
    base = commit(
        repo.root, {f"{infra}/{name}": "{}\n" for name in pointers} | {ledger: "base\n"},
        "existing published metadata",
    )
    git(repo.wt, "merge", "--quiet", "main")
    row = f"| [→ {number}](../01_变更单/CHG-SCPT/{number}.md) |\n"
    files = {
        f"{infra}/active_release.json": json.dumps({"release_id": release}) + "\n",
        f"{infra}/previous_release.json": '{"saved":"old"}\n',
        f"{infra}/deployment_manifest.json": '{"releases":{}}\n',
        f"{infra}/releases/{release}/payload.txt": "unchanged\n",
        ledger: row + "base\n",
        record: "| 变更状态 | approved |\n",
    }
    card = "P/02_规划/311_归档_PM.md"
    table = "\n".join(f"| `{path}` | 计划新增 |" for path in [*files, card])
    files[card] = f"{number}\n\n| 路径 | 基线状态 |\n|---|---|\n{table}\n"
    commit(repo.wt, files, f"{number} 归档\n\n{CARD}")
    _change_order(repo.root, number, "approved")
    local = {
        path: (repo.root / path).read_bytes() for path in (record,)
    }
    for path, value in files.items():
        if path.startswith(f"{infra}/") or path == ledger:
            local[path] = (
                (row + "unrelated local row\nbase\n") if path == ledger
                else value.replace("\n", "\r\n") if path.endswith(".json")
                else value
            ).encode("utf-8")
    local["README.md"] = b"unrelated local work\n"
    for path, data in local.items():
        target = repo.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return base, local, ledger


def test_archive_adopts_existing_files_and_leaves_unrelated_edits(
    pm: ModuleType, repo: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, local, ledger = _deployed_archive(repo)
    assert _audit(pm, repo, monkeypatch) == 0
    assert run(pm, repo.root, "install-hook") == 0
    assert run(pm, repo.root, "merge", "w1", "--archive-existing") == 0
    assert rev(repo.root, "main^1") == base
    assert rev(repo.root, "main^2") == rev(repo.wt, "HEAD")
    assert rev(repo.root, "main^{tree}") == rev(repo.wt, "HEAD^{tree}")
    assert all((repo.root / path).read_bytes() == data for path, data in local.items())
    assert "unrelated local row" not in git(repo.root, "show", f"main:{ledger}").stdout
    assert pm.read_log(repo.root)[-1]["replaced"] == []
    assert any(path.endswith("/active_release.json") for path in pm.read_log(repo.root)[-1]["adopted"])


def test_archive_restores_git_index_if_reference_transaction_refuses(
    pm: ModuleType, repo: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, local, _ = _deployed_archive(repo)
    assert _audit(pm, repo, monkeypatch) == 0
    index = git(repo.root, "ls-files", "--stage").stdout
    hook = repo.root / ".git" / "hooks" / "reference-transaction"
    hook.write_bytes(b'#!/bin/sh\n[ "$1" != prepared ]\n')
    hook.chmod(0o755)
    assert run(pm, repo.root, "merge", "w1", "--archive-existing") == 1
    assert rev(repo.root, "main") == base
    assert git(repo.root, "ls-files", "--stage").stdout == index
    assert all((repo.root / path).read_bytes() == data for path, data in local.items())
    assert not (repo.root / "P/02_规划/311_归档_PM.md").exists()
    assert pm.read_log(repo.root) == []


def test_interrupted_archive_restores_only_archive_index_entries(
    pm: ModuleType, repo: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    base, local, _ = _deployed_archive(repo)
    assert _audit(pm, repo, monkeypatch) == 0
    initial_index = git(repo.root, "ls-files", "--stage").stdout
    original_run = pm.Git.run
    stage_calls = 0
    source = f"--source={rev(repo.wt, 'HEAD')}"

    def interrupt_after_one_batch(self: Any, *args: str, **kwargs: Any) -> Any:
        nonlocal stage_calls
        if args[:4] == ("--literal-pathspecs", "restore", "--staged", source):
            stage_calls += 1
            if stage_calls == 2:
                raise KeyboardInterrupt
        return original_run(self, *args, **kwargs)

    monkeypatch.setattr(pm, "_chunk_paths", lambda paths: [[path] for path in paths])
    monkeypatch.setattr(pm.Git, "run", interrupt_after_one_batch)
    assert run(pm, repo.root, "merge", "w1", "--archive-existing") == 1
    assert stage_calls == 2
    assert rev(repo.root, "main") == base
    assert git(repo.root, "ls-files", "--stage").stdout == initial_index
    assert all((repo.root / path).read_bytes() == data for path, data in local.items())
    assert pm.read_log(repo.root) == []


def test_archive_does_not_overwrite_an_ignored_local_document(
    pm: ModuleType, repo: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, local, _ = _deployed_archive(repo)
    assert _audit(pm, repo, monkeypatch) == 0
    card = "P/02_规划/311_归档_PM.md"
    (repo.root / ".git" / "info" / "exclude").write_bytes(f"{card}\n".encode())
    override = repo.root / card
    override.parent.mkdir(parents=True, exist_ok=True)
    override.write_bytes(b"keep locally ignored work\n")
    assert run(pm, repo.root, "merge", "w1", "--archive-existing") == 1
    assert rev(repo.root, "main") == base
    assert git(repo.root, "diff", "--cached", "--name-only").stdout == ""
    assert override.read_bytes() == b"keep locally ignored work\n"
    assert all((repo.root / path).read_bytes() == data for path, data in local.items())


def test_unrelated_uncommitted_changes_in_the_control_root_are_refused(
    pm: ModuleType, repo: SimpleNamespace, capsys: Any
) -> None:
    commit(repo.wt, {"docs/a.md": "a\n"}, f"docs\n\n{CARD}")
    (repo.root / "README.md").write_text("edited in the control root\n", encoding="utf-8")
    assert run(pm, repo.root, "merge", "w1") == 1
    assert "控制根有未提交的改动" in capsys.readouterr().out


def _local_governance_records(pm: ModuleType, repo: SimpleNamespace) -> tuple[str, str, str]:
    ledger = pm.GOVERNANCE_LEDGER
    completed = f"{pm.GOVERNANCE_DIR}01_变更单/CHG-SCPT/CHG-SCPT-2026-732.md"
    active = f"{pm.GOVERNANCE_DIR}01_变更单/CHG-SCPT/CHG-SCPT-2026-733.md"
    commit(repo.root, {ledger: "tracked ledger\n", completed: "tracked order\n"}, "existing governance")
    git(repo.wt, "merge", "--quiet", "main")
    for path in (ledger, completed, active):
        (repo.root / path).write_bytes(b"local record\r\n")
    return ledger, completed, active


def test_merge_preserves_unrelated_governance_records(pm: ModuleType, repo: SimpleNamespace) -> None:
    paths = _local_governance_records(pm, repo)
    commit(repo.wt, {"docs/new.md": "docs\n"}, f"docs\n\n{CARD}")
    assert run(pm, repo.root, "merge", "w1") == 0
    assert all((repo.root / path).read_bytes() == b"local record\r\n" for path in paths)
    assert git(repo.root, "ls-tree", "--name-only", "main", "--", paths[2]).stdout == ""
    assert git(repo.root, "diff", "--name-only", "main^1", "main").stdout.strip() == "docs/new.md"
    entry = pm.read_log(repo.root)[-1]
    assert set(entry["preserved_governance"]) == set(paths)
    assert entry["governance_drift"] == []


@pytest.mark.parametrize("problem", ["overlap", "staged"])
def test_governance_preservation_refuses_overlap_or_a_staged_index(
    pm: ModuleType, repo: SimpleNamespace, capsys: Any, problem: str,
) -> None:
    ledger, _completed, _active = _local_governance_records(pm, repo)
    base = rev(repo.root, "main")
    path = ledger if problem == "overlap" else "other.md"
    commit(repo.wt, {path: "incoming\n"}, f"docs\n\n{CARD}")
    if problem == "staged":
        (repo.root / path).write_bytes(b"incoming\n")
        git(repo.root, "add", "--", path)
    assert run(pm, repo.root, "merge", "w1") == 1
    expected = "未提交的变更记录重叠" if problem == "overlap" else "有已暂存内容"
    assert expected in capsys.readouterr().out
    assert rev(repo.root, "main") == base
    assert (repo.root / ledger).read_bytes() == b"local record\r\n"


def test_governance_change_during_precheck_leaves_main_and_new_bytes_intact(
    pm: ModuleType, repo: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger, _completed, _active = _local_governance_records(pm, repo)
    base = rev(repo.root, "main")
    commit(repo.wt, {"docs/new.md": "docs\n"}, f"docs\n\n{CARD}")

    def concurrent_status_update(_root: Path, _worktree: Path, _full: bool) -> Any:
        (repo.root / ledger).write_bytes(b"new local record\n")
        return pm.GateResult(True)

    monkeypatch.setattr(pm, "run_gates", concurrent_status_update)
    assert run(pm, repo.root, "merge", "w1") == 1
    assert rev(repo.root, "main") == base
    assert (repo.root / ledger).read_bytes() == b"new local record\n"


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
    replace = pm._control_root_copies(root_git, repo.root, sha, sorted(files)).replace
    assert len(status_batches) >= 2
    assert replace == sorted(files)


@pytest.fixture
def gate_receipt(repo: SimpleNamespace) -> Path:
    commit(repo.wt, {"docs/candidate.md": "candidate\n"}, f"candidate\n\n{CARD}")
    record = {
        "id": "task",
        "backend": "github",
        "state": "passed",
        "handle": "12345",
        "detail": "digest",
        "candidate": {
            "commit": rev(repo.wt, "HEAD"),
            "tree": rev(repo.wt, "HEAD^{tree}"),
            "base": rev(repo.root, "main"),
        },
    }
    receipt: Path = repo.root / ".auto-pm" / "gate-receipt.json"
    receipt.write_text(json.dumps(record), encoding="utf-8", errors="replace")
    (repo.root / "main.py").write_text(
        "from pathlib import Path\nprint(Path('.auto-pm/gate-receipt.json').read_text(encoding='utf-8'))\n",
        encoding="utf-8",
        errors="replace",
    )
    return receipt


def test_managed_gate_accepts_real_git_identity(
    pm: ModuleType, repo: SimpleNamespace, gate_receipt: Path
) -> None:
    assert gate_receipt.is_file()
    assert pm.managed_gate_receipt(repo.root, repo.wt) == "托管全量门禁 PASS：task（github，运行 12345）"


def test_managed_gate_accepts_l2_and_enforces_tier_and_full_fallback(
    pm: ModuleType, repo: SimpleNamespace, gate_receipt: Path
) -> None:
    # 1) L2 receipt accepted when require_full=False and expected_groups covered
    record = json.loads(gate_receipt.read_text(encoding="utf-8", errors="replace"))
    record["candidate"]["tier"] = "L2"
    record["candidate"]["groups"] = ["application", "cli"]
    gate_receipt.write_text(json.dumps(record), encoding="utf-8", errors="replace")

    ok_l2 = pm.managed_gate_receipt(
        repo.root, repo.wt, require_full=False, expected_groups=("application",)
    )
    assert ok_l2.startswith("托管 L2 门禁 PASS：task")

    # 2) L2 receipt rejected if expected_groups has uncovered group
    with pytest.raises(pm.RefusedError, match="少于当前预期受影响组"):
        pm.managed_gate_receipt(
            repo.root, repo.wt, require_full=False, expected_groups=("application", "core")
        )

    # 3) L2 receipt rejected when require_full=True
    with pytest.raises(pm.RefusedError, match="需要 L3 全量门禁凭证"):
        pm.managed_gate_receipt(repo.root, repo.wt, require_full=True)

    # 4) L3 receipt satisfies L2 check (require_full=False)
    record["candidate"]["tier"] = "L3"
    record["candidate"].pop("groups", None)
    gate_receipt.write_text(json.dumps(record), encoding="utf-8", errors="replace")
    assert pm.managed_gate_receipt(repo.root, repo.wt, require_full=False).startswith("托管全量门禁 PASS")

    # 5) Legacy main.py without --full flag falls back cleanly when require_full=True
    (repo.root / "main.py").write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "if '--full' in sys.argv:\n"
        "    print('Error: No such option: --full', file=sys.stderr)\n"
        "    raise SystemExit(2)\n"
        "print(Path('.auto-pm/gate-receipt.json').read_text(encoding='utf-8'))\n",
        encoding="utf-8",
        errors="replace",
    )
    assert pm.managed_gate_receipt(repo.root, repo.wt, require_full=True).startswith("托管全量门禁 PASS")


@pytest.mark.parametrize("changed_field", ["commit", "tree", "base"])
def test_managed_gate_rejects_wrong_git_identity(
    pm: ModuleType, repo: SimpleNamespace, gate_receipt: Path, changed_field: str
) -> None:
    record = json.loads(gate_receipt.read_text(encoding="utf-8", errors="replace"))
    record["candidate"][changed_field] = "d" * 40
    gate_receipt.write_text(json.dumps(record), encoding="utf-8", errors="replace")
    with pytest.raises(pm.RefusedError, match="当前 main 不匹配"):
        pm.managed_gate_receipt(repo.root, repo.wt)


def _setup_archive_project(root: Path, pid: str = "SW-2026-008") -> tuple[Path, Path, str]:
    project_rel = f"01_Project/{pid}"
    reg_path = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    reg_path.write_text(
        json.dumps({"projects": [{"project_id": pid, "project_root": project_rel}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    chg_dir = root / project_rel / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-SCPT"
    ledger = root / project_rel / "04_监控" / "01_变更管理" / "02_变更记录" / "01_版本变更台账.md"
    chg_dir.mkdir(parents=True, exist_ok=True)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    return chg_dir, ledger, project_rel


def _chg_markdown(chg: str, status: str) -> str:
    return (
        f"# 变更单 {chg}\n\n"
        "| 字段 | 值 |\n"
        "|---|---|\n"
        f"| 变更状态 | {status} |\n\n"
        "## 1. 说明\n\n"
        f"- 变更单号：{chg}\n"
    )


def _ledger_row(idx: int, chg: str, status_cell: str) -> str:
    return (
        f"| {idx} | [→ {chg}](../01_变更单/CHG-SCPT/{chg}.md) "
        f"| 测试 {chg} | 2026-11-22 | {status_cell} |"
    )


def _ledger_doc(rows: list[str], *, blank_between: bool = True, eol: str = "\n") -> str:
    head = [
        "# 版本变更台账",
        "",
        "## 变更单索引",
        "",
        "| 序号 | 变更单 | 说明 | 日期 | 状态 |",
        "|------|--------|------|------|------|",
    ]
    body: list[str] = []
    for i, row in enumerate(rows):
        body.append(row)
        if blank_between and i + 1 < len(rows):
            body.append("")
    return eol.join([*head, *body]) + eol


def test_archive_changes_projects_completed_only_preserves_unselected_and_is_idempotent(
    pm: ModuleType, repo: SimpleNamespace
) -> None:
    proj_rel = "01_Project/SW-2026-008"
    chg_rel_base = f"{proj_rel}/04_监控/01_变更管理/01_变更单/CHG-SCPT"
    ledger_rel = f"{proj_rel}/04_监控/01_变更管理/02_变更记录/01_版本变更台账.md"
    commit(
        repo.wt,
        {
            f"{chg_rel_base}/CHG-SCPT-2026-700.md": _chg_markdown("CHG-SCPT-2026-700", "completed"),
            f"{chg_rel_base}/CHG-SCPT-2026-701.md": _chg_markdown("CHG-SCPT-2026-701", "implementing"),
            ledger_rel: _ledger_doc(
                [
                    _ledger_row(2, "CHG-SCPT-2026-701", "🔄实施中"),
                    _ledger_row(1, "CHG-SCPT-2026-700", "✅已关闭"),
                ]
            ),
        },
        f"seed project baseline\n\n{CARD}",
    )
    assert run(pm, repo.root, "merge", "w1") == 0

    chg_dir, ledger, _ = _setup_archive_project(repo.root)
    p701 = chg_dir / "CHG-SCPT-2026-701.md"
    p702 = chg_dir / "CHG-SCPT-2026-702.md"
    p727 = chg_dir / "CHG-SCPT-2026-727.md"
    p701.write_bytes(_chg_markdown("CHG-SCPT-2026-701", "completed").replace("\n", "\r\n").encode("utf-8"))
    p702.write_bytes(_chg_markdown("CHG-SCPT-2026-702", "completed").replace("\n", "\r\n").encode("utf-8"))
    p727.write_bytes(_chg_markdown("CHG-SCPT-2026-727", "implementing").replace("\n", "\r\n").encode("utf-8"))
    ledger.write_bytes(
        _ledger_doc(
            [
                _ledger_row(4, "CHG-SCPT-2026-727", "🔄实施中"),
                _ledger_row(3, "CHG-SCPT-2026-702", "✅已关闭"),
                _ledger_row(2, "CHG-SCPT-2026-701", "✅已关闭"),
                _ledger_row(1, "CHG-SCPT-2026-700", "✅已关闭"),
            ],
            eol="\r\n",
        ).encode("utf-8")
    )
    before_bytes = {
        "701": p701.read_bytes(),
        "702": p702.read_bytes(),
        "727": p727.read_bytes(),
        "ledger": ledger.read_bytes(),
    }

    assert run(pm, repo.root, "archive-changes", "SW-2026-008") == 0

    changed = git(
        repo.root, "-c", "core.quotePath=false", "show", "--name-only", "--format=", "HEAD"
    ).stdout.splitlines()
    assert sorted(line for line in changed if line) == sorted(
        [
            f"{chg_rel_base}/CHG-SCPT-2026-701.md",
            f"{chg_rel_base}/CHG-SCPT-2026-702.md",
            ledger_rel,
        ]
    )
    main_ledger = git(repo.root, "show", f"HEAD:{ledger_rel}").stdout
    assert "CHG-SCPT-2026-702" in main_ledger
    assert "CHG-SCPT-2026-701" in main_ledger and "✅已关闭" in main_ledger
    assert "CHG-SCPT-2026-700" in main_ledger
    assert "CHG-SCPT-2026-727" not in main_ledger
    assert "\n\n" in main_ledger
    main_701 = git(repo.root, "show", f"HEAD:{chg_rel_base}/CHG-SCPT-2026-701.md").stdout
    assert "\r\n" not in main_701
    assert "| 变更状态 | completed |" in main_701

    assert p701.read_bytes() == before_bytes["701"]
    assert p702.read_bytes() == before_bytes["702"]
    assert p727.read_bytes() == before_bytes["727"]
    assert ledger.read_bytes() == before_bytes["ledger"]
    assert run(pm, repo.root, "verify-log") == 0

    archived_head = rev(repo.root, "main")
    log_count = len(pm.read_log(repo.root))
    assert run(pm, repo.root, "archive-changes", "SW-2026-008") == 0
    assert rev(repo.root, "main") == archived_head
    assert len(pm.read_log(repo.root)) == log_count


def test_archive_changes_blocks_on_staged_index_active_gate_active_worktree_and_pending_audit(
    pm: ModuleType, repo: SimpleNamespace
) -> None:
    import sqlite3

    chg_dir, ledger, _ = _setup_archive_project(repo.root)
    (chg_dir / "CHG-SCPT-2026-702.md").write_text(
        _chg_markdown("CHG-SCPT-2026-702", "completed"), encoding="utf-8"
    )
    ledger.write_text(
        _ledger_doc([_ledger_row(1, "CHG-SCPT-2026-702", "✅已关闭")]), encoding="utf-8"
    )
    deploy_wt = repo.root / ".auto-pm" / "worktrees" / "deploy-1.3.3-test"
    deploy_wt.mkdir(parents=True, exist_ok=True)
    (deploy_wt / ".git").write_text("gitdir: dummy\n", encoding="utf-8")

    before_main = rev(repo.root, "main")
    assert run(pm, repo.root, "archive-changes", "SW-2026-008", "--dry-run") == 0

    staged = repo.root / "staged.txt"
    staged.write_text("staged\n", encoding="utf-8")
    git(repo.root, "add", "staged.txt")
    assert run(pm, repo.root, "archive-changes", "SW-2026-008") == 1
    assert rev(repo.root, "main") == before_main
    git(repo.root, "reset", "--", "staged.txt")
    staged.unlink()

    gate_db = repo.root / pm.GATE_LEDGER_PATH
    gate_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(gate_db)
    try:
        conn.execute(
            "CREATE TABLE attempts (id TEXT PRIMARY KEY, key TEXT NOT NULL, number INTEGER NOT NULL, "
            "backend TEXT NOT NULL, state TEXT NOT NULL, handle TEXT NOT NULL, detail TEXT NOT NULL, "
            "approval TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO attempts VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "stale-1",
                json.dumps({"base": "a" * 40, "commit": "b" * 40}),
                1,
                "github",
                "running",
                "h0",
                "d0",
                "a0",
            ),
        )
        conn.commit()
    finally:
        conn.close()
    assert run(pm, repo.root, "archive-changes", "SW-2026-008", "--dry-run") == 0

    conn = sqlite3.connect(gate_db)
    try:
        conn.execute(
            "INSERT INTO attempts VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "task-1",
                json.dumps({"base": before_main, "commit": "c" * 40}),
                1,
                "github",
                "running",
                "h1",
                "d1",
                "a1",
            ),
        )
        conn.commit()
    finally:
        conn.close()
    assert run(pm, repo.root, "archive-changes", "SW-2026-008") == 1
    assert rev(repo.root, "main") == before_main
    conn = sqlite3.connect(gate_db)
    try:
        conn.execute("UPDATE attempts SET state = 'passed' WHERE id = 'task-1'")
        conn.commit()
    finally:
        conn.close()

    dirty_wt = repo.wt / "dirty.txt"
    dirty_wt.write_text("dirty\n", encoding="utf-8")
    assert run(pm, repo.root, "archive-changes", "SW-2026-008") == 1
    assert rev(repo.root, "main") == before_main
    dirty_wt.unlink()

    candidate_sha = commit(repo.wt, {"feature.txt": "wip\n"}, f"wip\n\n{CARD}")
    git(repo.wt, "branch", "pending-candidate", candidate_sha)
    assert run(pm, repo.root, "archive-changes", "SW-2026-008") == 1
    assert rev(repo.root, "main") == before_main
    git(repo.wt, "reset", "--hard", before_main)

    audits_dir = repo.root / pm.STATE_DIR / "audits"
    audits_dir.mkdir(parents=True, exist_ok=True)
    (audits_dir / "pending.json").write_text(
        json.dumps(
            {
                "worktree": "other",
                "base": before_main,
                "candidate": candidate_sha,
                "verdict": "PASS",
            }
        ),
        encoding="utf-8",
    )
    assert run(pm, repo.root, "archive-changes", "SW-2026-008") == 1
    assert rev(repo.root, "main") == before_main

    (audits_dir / "pending.json").unlink()
    assert run(pm, repo.root, "archive-changes", "SW-2026-008", "--dry-run") == 0


def test_archive_changes_succeeds_offline_in_backup_mode_and_supports_dry_run(
    pm: ModuleType, repo: SimpleNamespace
) -> None:
    assert run(pm, repo.root, "github-mode", "备份") == 0
    git(repo.root, "remote", "set-url", "origin", str(repo.root / "missing-remote.git"))
    chg_dir, ledger, _ = _setup_archive_project(repo.root)
    (chg_dir / "CHG-SCPT-2026-702.md").write_text(
        _chg_markdown("CHG-SCPT-2026-702", "completed"), encoding="utf-8"
    )
    ledger.write_text(
        _ledger_doc([_ledger_row(1, "CHG-SCPT-2026-702", "✅已关闭")]), encoding="utf-8"
    )
    before_main = rev(repo.root, "main")

    assert run(pm, repo.root, "archive-changes", "SW-2026-008", "--dry-run") == 0
    assert rev(repo.root, "main") == before_main
    assert pm.read_log(repo.root) == []

    assert run(pm, repo.root, "archive-changes", "SW-2026-008") == 0
    assert rev(repo.root, "main") != before_main
    entries = pm.read_log(repo.root)
    assert len(entries) == 1
    assert entries[0]["kind"] == "archive_changes"
    assert entries[0]["pushed"] is False
    assert entries[0]["chgs"] == ["CHG-SCPT-2026-702"]


def test_archive_changes_rejects_uncompleted_explicit_chg_and_missing_ledger_row(
    pm: ModuleType, repo: SimpleNamespace
) -> None:
    chg_dir, ledger, _ = _setup_archive_project(repo.root)
    (chg_dir / "CHG-SCPT-2026-727.md").write_text(
        _chg_markdown("CHG-SCPT-2026-727", "implementing"), encoding="utf-8"
    )
    (chg_dir / "CHG-SCPT-2026-702.md").write_text(
        _chg_markdown("CHG-SCPT-2026-702", "completed"), encoding="utf-8"
    )
    ledger.write_text(_ledger_doc([]), encoding="utf-8")
    before_main = rev(repo.root, "main")

    assert run(pm, repo.root, "archive-changes", "SW-2026-008", "--chg", "CHG-SCPT-2026-727") == 1
    assert run(pm, repo.root, "archive-changes", "SW-2026-008", "--chg", "CHG-SCPT-2026-702") == 1
    assert rev(repo.root, "main") == before_main


def test_project_ledger_anchors_index_section_on_multitable_ledger(pm: ModuleType) -> None:
    base_text = "\n".join(
        [
            "# 版本变更台帐 - DJ-2026-009",
            "",
            "## 1. 变更统计一览",
            "",
            "| 变更类型 | 累计数量 | 待处理 | 已验证/关闭 |",
            "|:---|:---:|:---:|:---:|",
            "| **CHG-PLC** | 1 | 0 | 1 |",
            "",
            "## 2. 变更明细台账 (引用模式)",
            "",
            "| 变更编号 | 变更标题 | 状态 |",
            "|:---|:---|:---:|",
            "| CHG-PLC-2026-001 | 历史记录 | 已关闭 |",
            "",
            "## 变更单索引",
            "",
            "| 序号 | 变更编号 | 领域 | 申请人 | 申请日期 | 变更描述 | 完成日期 | 状态 |",
            "|------|----------|------|--------|----------|----------|----------|------|",
            "| 002 | [→ CHG-PLC-2026-006](./01_变更单/CHG-PLC/CHG-PLC-2026-006.md) | PLC | u | 2026-11-06 | 描述6 | | 🔄实施中 |",
            "",
            "| 001 | [→ CHG-PLC-2026-005](./01_变更单/CHG-PLC/CHG-PLC-2026-005.md) | PLC | u | 2026-11-05 | 描述5 | 2026-11-06 | ✅已关闭 |",
            "",
            "## 3. 备注",
            "",
            "保留尾部注释。",
            "",
        ]
    )
    local_text = "\n".join(
        [
            "# 版本变更台帐 - DJ-2026-009",
            "",
            "## 1. 变更统计一览",
            "",
            "| 变更类型 | 累计数量 | 待处理 | 已验证/关闭 |",
            "|:---|:---:|:---:|:---:|",
            "| **CHG-PLC** | 1 | 0 | 1 |",
            "",
            "## 2. 变更明细台账 (引用模式)",
            "",
            "| 变更编号 | 变更标题 | 状态 |",
            "|:---|:---|:---:|",
            "| CHG-PLC-2026-001 | 历史记录 | 已关闭 |",
            "",
            "## 变更单索引",
            "",
            "| 序号 | 变更编号 | 领域 | 申请人 | 申请日期 | 变更描述 | 完成日期 | 状态 |",
            "|------|----------|------|--------|----------|----------|----------|------|",
            "| 004 | [→ CHG-PLC-2026-008](./01_变更单/CHG-PLC/CHG-PLC-2026-008.md) | PLC | u | 2026-11-10 | 未选实施中 | | 🔄实施中 |",
            "",
            "| 003 | [→ CHG-PLC-2026-007](./01_变更单/CHG-PLC/CHG-PLC-2026-007.md) | PLC | u | 2026-11-09 | 描述7 | 2026-11-09 | ✅已关闭 |",
            "",
            "| 002 | [→ CHG-PLC-2026-006](./01_变更单/CHG-PLC/CHG-PLC-2026-006.md) | PLC | u | 2026-11-06 | 描述6 | 2026-11-09 | ✅已关闭 |",
            "",
            "| 001 | [→ CHG-PLC-2026-005](./01_变更单/CHG-PLC/CHG-PLC-2026-005.md) | PLC | u | 2026-11-05 | 描述5 | 2026-11-06 | ✅已关闭 |",
            "",
            "## 3. 备注",
            "",
            "保留尾部注释。",
            "",
        ]
    )

    projected = pm._project_ledger(base_text, local_text, ["CHG-PLC-2026-006", "CHG-PLC-2026-007"])
    lines = projected.splitlines()
    stats_sep = lines.index("|:---|:---:|:---:|:---:|")
    assert lines[stats_sep + 1] == "| **CHG-PLC** | 1 | 0 | 1 |"
    assert "CHG-PLC-2026-001 | 历史记录" in projected
    assert lines[-2:] == ["## 3. 备注", ""] or lines[-3:] == ["## 3. 备注", "", "保留尾部注释。"]
    idx_sep = lines.index("|------|----------|------|--------|----------|----------|----------|------|")
    assert "CHG-PLC-2026-007" in lines[idx_sep + 1]
    assert "CHG-PLC-2026-006" in projected and "✅已关闭" in projected
    assert "CHG-PLC-2026-008" not in projected

    base_without_index = "\n".join(base_text.splitlines()[:14]) + "\n"
    projected_boot = pm._project_ledger(base_without_index, local_text, ["CHG-PLC-2026-007"])
    boot_lines = projected_boot.splitlines()
    boot_stats_sep = boot_lines.index("|:---|:---:|:---:|:---:|")
    assert boot_lines[boot_stats_sep + 1] == "| **CHG-PLC** | 1 | 0 | 1 |"
    assert "## 变更单索引" in boot_lines
    assert "CHG-PLC-2026-007" in projected_boot
    assert "CHG-PLC-2026-008" not in projected_boot


def test_archive_changes_logs_entry_even_when_post_merge_snapshot_drifts(
    pm: ModuleType, repo: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    chg_dir, ledger, proj_rel = _setup_archive_project(repo.root)
    ledger_rel = f"{proj_rel}/04_监控/01_变更管理/02_变更记录/01_版本变更台账.md"
    (chg_dir / "CHG-SCPT-2026-702.md").write_text(
        _chg_markdown("CHG-SCPT-2026-702", "completed"), encoding="utf-8"
    )
    ledger.write_text(
        _ledger_doc([_ledger_row(1, "CHG-SCPT-2026-702", "✅已关闭")]), encoding="utf-8"
    )

    real_snaps = pm._file_snapshots
    calls = 0

    def flaky_snaps(root: Path, rel_paths: list[str] | tuple[str, ...]) -> dict[str, str]:
        nonlocal calls
        calls += 1
        result: dict[str, str] = dict(real_snaps(root, rel_paths))
        if calls == 3:
            result[ledger_rel] = "e" * 64
        return result

    monkeypatch.setattr(pm, "_file_snapshots", flaky_snaps)
    before_main = rev(repo.root, "main")

    assert run(pm, repo.root, "archive-changes", "SW-2026-008") == 0
    assert rev(repo.root, "main") != before_main
    out = capsys.readouterr().out
    assert "归档后发现本机变更记录有并发更新，请核对：" in out
    entries = pm.read_log(repo.root)
    assert len(entries) == 1
    assert entries[0]["governance_drift"] == [ledger_rel]
    assert run(pm, repo.root, "verify-log") == 0


@pytest.mark.parametrize("gh_mode", ["备份", "关"])
def test_run_gates_allows_l1_without_managed_receipt_online_and_offline(
    pm: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, gh_mode: str
) -> None:
    root = tmp_path / "root"
    (root / ".git").mkdir(parents=True)
    wt = root / ".auto-pm" / "worktrees" / "w1"
    (wt / "tests").mkdir(parents=True)
    assert run(pm, root, "github-mode", gh_mode) == 0
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(list(cmd))
        payload = {
            "verdict": "PASS",
            "tier": "L1",
            "recommended_groups": ["infrastructure", "rest"],
            "full_gate_required": False,
            "outside_changes": [],
            "steps": [
                {"name": "ruff", "verdict": "PASS", "exit": 0},
                {"name": "mypy", "verdict": "PASS", "exit": 0},
                {"name": "pytest", "verdict": "PASS", "exit": 0},
            ],
        }
        return subprocess.CompletedProcess(cmd, 0, json.dumps(payload, ensure_ascii=False), "")

    monkeypatch.setattr(pm.subprocess, "run", fake_run)
    monkeypatch.setattr(pm, "managed_gate_receipt", lambda *_args: pytest.fail("L1 不应触发托管全量凭证检查"))
    res = pm.run_gates(root, wt, False)
    assert res.ok
    assert any("门禁分级：L1（本地轻量闭环，无需托管全量门禁）" in line for line in res.lines)
    assert len(calls) == 1 and "--defer-full" in calls[0]


@pytest.mark.parametrize("tier", ["L2", "L3"])
def test_run_gates_still_requires_managed_receipt_for_l2_and_l3(
    pm: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tier: str
) -> None:
    wt = tmp_path / "wt"
    (wt / "tests").mkdir(parents=True)

    def fake_run(cmd: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        payload = {
            "verdict": "UNVERIFIED",
            "tier": tier,
            "recommended_groups": ["application"] if tier == "L2" else ["core", "infrastructure"],
            "full_gate_required": True,
            "outside_changes": [],
            "steps": [
                {"name": "ruff", "verdict": "PASS", "exit": 0},
                {"name": "mypy", "verdict": "PASS", "exit": 0},
                {"name": "pytest", "verdict": "SKIPPED", "exit": None},
            ],
        }
        return subprocess.CompletedProcess(cmd, 1, json.dumps(payload, ensure_ascii=False), "")

    monkeypatch.setattr(pm.subprocess, "run", fake_run)
    recorded_calls: list[dict[str, Any]] = []

    def missing_receipt(_root: Path, _worktree: Path, **kwargs: Any) -> str:
        recorded_calls.append(kwargs)
        raise pm.RefusedError("缺少托管全量门禁凭证")

    monkeypatch.setattr(pm, "managed_gate_receipt", missing_receipt)
    with pytest.raises(pm.RefusedError, match="托管全量"):
        pm.run_gates(tmp_path, wt, False)
    if tier == "L2":
        assert recorded_calls[-1] == {"require_full": False, "expected_groups": ("application",)}
    else:
        assert recorded_calls[-1] == {}

    def ok_receipt(_root: Path, _wt: Path, **kwargs: Any) -> str:
        recorded_calls.append(kwargs)
        return f"托管凭证已核对({tier})"

    monkeypatch.setattr(pm, "managed_gate_receipt", ok_receipt)
    ok_res = pm.run_gates(tmp_path, wt, False)
    assert ok_res.ok
    assert any(f"门禁分级：{tier}（建议组：" in line for line in ok_res.lines)
    assert any(f"托管凭证已核对({tier})" in line for line in ok_res.lines)


def _local_live_release_pointers(
    repo: SimpleNamespace,
    *,
    dirty_manifest: bool = True,
    release_id: str = "1.3.3-beef123",
) -> tuple[dict[str, bytes], str]:
    infra = "00_Infrastructure/auto_pm"
    initial_manifest = json.dumps(
        {
            "schema_version": "deployment_manifest.v1",
            "releases": {
                "1.3.3-aaaa111": {"source_commit": "a" * 40},
                release_id: {"source_commit": "b" * 40},
            },
        },
        ensure_ascii=False,
    ) + "\n"
    commit(
        repo.root,
        {
            f"{infra}/active_release.json": json.dumps({"release_id": "1.3.3-aaaa111"}) + "\n",
            f"{infra}/previous_release.json": json.dumps({"release_id": "1.3.3-0000000"}) + "\n",
            f"{infra}/deployment_manifest.json": initial_manifest,
        },
        "committed release pointers",
    )
    git(repo.wt, "merge", "--quiet", "main")
    pointer_bytes = {
        f"{infra}/active_release.json": (
            json.dumps({"release_id": release_id}) + "\r\n"
        ).encode("utf-8"),
        f"{infra}/previous_release.json": (
            json.dumps({"release_id": "1.3.3-aaaa111"}) + "\r\n"
        ).encode("utf-8"),
        f"{infra}/deployment_manifest.json": (
            (
                json.dumps(
                    {
                        "schema_version": "deployment_manifest.v1",
                        "releases": {
                            "1.3.3-aaaa111": {"source_commit": "a" * 40},
                            release_id: {"source_commit": "b" * 40, "note": "gui-ship"},
                        },
                    },
                    ensure_ascii=False,
                )
                + "\r\n"
            ).encode("utf-8")
            if dirty_manifest
            else initial_manifest.encode("utf-8")
        ),
    }
    for rel, raw in pointer_bytes.items():
        if dirty_manifest or not rel.endswith("deployment_manifest.json"):
            (repo.root / rel).write_bytes(raw)
    payload_rel = f"{infra}/releases/{release_id}/payload.txt"
    payload_file = repo.root / payload_rel
    payload_file.parent.mkdir(parents=True, exist_ok=True)
    payload_file.write_bytes(b"live payload\n")
    return pointer_bytes, payload_rel


def test_merge_preserves_unrelated_live_release_pointers(
    pm: ModuleType, repo: SimpleNamespace, capsys: Any
) -> None:
    gov_paths = _local_governance_records(pm, repo)
    pointer_bytes, payload_rel = _local_live_release_pointers(repo)
    commit(repo.wt, {"docs/new.md": "docs\n"}, f"docs\n\n{CARD}")
    assert run(pm, repo.root, "merge", "w1") == 0
    out = capsys.readouterr().out
    assert all((repo.root / path).read_bytes() == raw for path, raw in pointer_bytes.items())
    assert (repo.root / payload_rel).read_bytes() == b"live payload\n"
    assert all((repo.root / path).read_bytes() == b"local record\r\n" for path in gov_paths)
    assert git(repo.root, "ls-tree", "--name-only", "main", "--", payload_rel).stdout == ""
    assert git(repo.root, "diff", "--name-only", "main^1", "main").stdout.strip() == "docs/new.md"
    entry = pm.read_log(repo.root)[-1]
    assert set(entry["preserved_release_pointers"]) == set(pointer_bytes)
    assert entry["preserved_release_id"] == "1.3.3-beef123"
    assert entry["release_pointer_drift"] == []
    assert set(entry["preserved_governance"]) == set(gov_paths)
    assert entry["governance_drift"] == []
    assert "原样保留" in out


def test_merge_preserves_partial_dirty_release_pointers(
    pm: ModuleType, repo: SimpleNamespace
) -> None:
    pointer_bytes, payload_rel = _local_live_release_pointers(repo, dirty_manifest=False)
    commit(repo.wt, {"docs/partial.md": "partial\n"}, f"docs\n\n{CARD}")
    assert run(pm, repo.root, "merge", "w1") == 0
    assert all((repo.root / path).read_bytes() == raw for path, raw in pointer_bytes.items())
    assert (repo.root / payload_rel).read_bytes() == b"live payload\n"
    entry = pm.read_log(repo.root)[-1]
    assert set(entry["preserved_release_pointers"]) == set(pointer_bytes)
    assert entry["release_pointer_drift"] == []


@pytest.mark.parametrize("problem", ["overlap_pointer", "overlap_payload", "staged"])
def test_release_pointer_preservation_refuses_overlap_and_staged_index(
    pm: ModuleType, repo: SimpleNamespace, capsys: Any, problem: str
) -> None:
    pointer_bytes, payload_rel = _local_live_release_pointers(repo)
    base = rev(repo.root, "main")
    active = "00_Infrastructure/auto_pm/active_release.json"
    if problem == "overlap_pointer":
        commit(repo.wt, {active: '{"release_id":"1.3.3-beef123"}\n'}, f"touch ptr\n\n{CARD}")
    elif problem == "overlap_payload":
        tip = commit(repo.wt, {payload_rel: "override\n"}, f"touch payload\n\n{CARD}")
        with pytest.raises(pm.RefusedError, match="候选不能同时改动发布文件"):
            pm._control_root_copies(pm.Git(repo.root), repo.root, tip, [payload_rel])
    else:
        commit(repo.wt, {"other.md": "incoming\n"}, f"docs\n\n{CARD}")
        (repo.root / "other.md").write_bytes(b"incoming\n")
        git(repo.root, "add", "--", "other.md")
    assert run(pm, repo.root, "merge", "w1") == 1
    expected = (
        "有已暂存内容"
        if problem == "staged"
        else "没有本卡的实施卡"
        if problem == "overlap_payload"
        else "候选不能同时改动发布文件"
    )
    assert expected in capsys.readouterr().out
    assert rev(repo.root, "main") == base
    assert all((repo.root / path).read_bytes() == raw for path, raw in pointer_bytes.items())


@pytest.mark.parametrize("problem", ["bad_json", "missing_manifest_entry", "missing_payload_dir"])
def test_release_pointer_preservation_refuses_corrupt_or_missing_payload(
    pm: ModuleType, repo: SimpleNamespace, capsys: Any, problem: str
) -> None:
    pointer_bytes, payload_rel = _local_live_release_pointers(repo)
    base = rev(repo.root, "main")
    active = "00_Infrastructure/auto_pm/active_release.json"
    manifest = "00_Infrastructure/auto_pm/deployment_manifest.json"
    commit(repo.wt, {"docs/new.md": "docs\n"}, f"docs\n\n{CARD}")
    if problem == "bad_json":
        (repo.root / active).write_bytes(b"{not-json")
    elif problem == "missing_manifest_entry":
        (repo.root / manifest).write_bytes(b'{"schema_version":"deployment_manifest.v1","releases":{}}\n')
    else:
        shutil.rmtree((repo.root / payload_rel).parent)
    before_active = (repo.root / active).read_bytes()
    assert run(pm, repo.root, "merge", "w1") == 1
    assert "控制根现役发布" in capsys.readouterr().out
    assert rev(repo.root, "main") == base
    assert (repo.root / active).read_bytes() == before_active
    assert (repo.root / "00_Infrastructure/auto_pm/previous_release.json").read_bytes() == pointer_bytes[
        "00_Infrastructure/auto_pm/previous_release.json"
    ]


def test_release_pointer_change_during_precheck_leaves_main_and_new_bytes_intact(
    pm: ModuleType, repo: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    _local_live_release_pointers(repo)
    base = rev(repo.root, "main")
    active = "00_Infrastructure/auto_pm/active_release.json"
    rel2 = repo.root / "00_Infrastructure/auto_pm/releases/1.3.3-cafe456"
    rel2.mkdir(parents=True, exist_ok=True)
    (rel2 / "payload.txt").write_bytes(b"v2\n")
    commit(repo.wt, {"docs/new.md": "docs\n"}, f"docs\n\n{CARD}")
    switched = b'{"release_id":"1.3.3-cafe456"}\n'

    def concurrent_ship(_root: Path, _worktree: Path, _full: bool) -> Any:
        (repo.root / active).write_bytes(switched)
        return pm.GateResult(True)

    monkeypatch.setattr(pm, "run_gates", concurrent_ship)
    assert run(pm, repo.root, "merge", "w1") == 1
    assert rev(repo.root, "main") == base
    assert (repo.root / active).read_bytes() == switched


def _write_station_holder(root: Path, station: str, *, session_id: str, pid: int = 0) -> None:
    holders = root / ".auto-pm" / "station-holders"
    holders.mkdir(parents=True, exist_ok=True)
    (holders / f"{station}.json").write_text(
        json.dumps(
            {
                "agent": station,
                "session_id": session_id,
                "pid": pid,
                "opened_at": "2026-11-27T00:00:00+00:00",
                "heartbeat_at": "2026-11-27T00:00:00+00:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_audit_record_enforces_real_session_for_same_window_positive_and_negative(
    pm: ModuleType, repo: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """746: 审计独立性比真实作者会话——同窗口同会话拒、同窗口无会话 ID 退回同 PID 拒、同窗口双会话放行。"""
    wt_dir = repo.root / ".auto-pm" / "worktrees" / "trae-111111"
    git(repo.root, "worktree", "add", "-b", "trae/CHG-SCPT-2026-746", str(wt_dir), "main")
    _identity(wt_dir)
    base = rev(repo.root, "main")
    candidate = commit(wt_dir, {"docs/a.md": "a\n"}, "docs\n\n领卡占位: CHG-SCPT-2026-746")
    report = repo.tmp / "audit-746.md"
    report.write_text(f"Audit {base}..{candidate}\n", encoding="utf-8")

    for var in ("AUTO_PM_AGENT", "AUTO_PM_SESSION_ID", "CLAUDE_CODE_SESSION_ID", "TRAE_CHAT_SESSION_ID", "VSCODE_PID"):
        monkeypatch.delenv(var, raising=False)

    # 1) 同窗口同会话（即便伪装成别的 agent 基名）必须拒绝
    _write_station_holder(repo.root, "trae-111111", session_id="trae-chat-session-aaa", pid=9001)
    monkeypatch.setenv("AUTO_PM_AGENT", "codex")
    monkeypatch.setenv("TRAE_CHAT_SESSION_ID", "trae-chat-session-aaa")
    monkeypatch.setenv("VSCODE_PID", "9001")
    assert run(
        pm, repo.root, "audit-record", "trae-111111", "--base", base,
        "--candidate", candidate, "--verdict", "PASS", "--report", str(report),
    ) == 1
    assert "另一审计会话" in capsys.readouterr().out

    # 2) 同窗口无 chat ID、退回同一 VSCODE_PID 必须拒绝（无论持有人同时记了 chat session_id 还是仅记了 vscode-<pid>）
    for author_sid in ("vscode-9001", "trae-chat-session-aaa"):
        _write_station_holder(repo.root, "trae-111111", session_id=author_sid, pid=9001)
        monkeypatch.delenv("TRAE_CHAT_SESSION_ID", raising=False)
        monkeypatch.setenv("AUTO_PM_AGENT", "trae")
        monkeypatch.setenv("VSCODE_PID", "9001")
        assert run(
            pm, repo.root, "audit-record", "trae-111111", "--base", base,
            "--candidate", candidate, "--verdict", "PASS", "--report", str(report),
        ) == 1
        assert "另一审计会话" in capsys.readouterr().out

    # 3) 同窗口双会话（同 VSCODE_PID=9001、同 trae 基名，但 TRAE_CHAT_SESSION_ID 不同）必须放行
    _write_station_holder(repo.root, "trae-111111", session_id="trae-chat-session-aaa", pid=9001)
    monkeypatch.setenv("AUTO_PM_AGENT", "trae")
    monkeypatch.setenv("TRAE_CHAT_SESSION_ID", "trae-chat-session-bbb")
    monkeypatch.setenv("VSCODE_PID", "9001")
    assert run(
        pm, repo.root, "audit-record", "trae-111111", "--base", base,
        "--candidate", candidate, "--verdict", "PASS", "--report", str(report),
    ) == 0
    receipt_path = pm._audit_path(repo.root, base, candidate)
    saved = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert isinstance(saved.get("reviewer_session_sha256"), str) and len(saved["reviewer_session_sha256"]) == 64

    plan = pm.Plan("trae/CHG-SCPT-2026-746", candidate, "CHG-SCPT-2026-746", ["CHG-SCPT-2026-746"], ["docs/a.md"], [], [], [], base=base, formal_change="CHG-SCPT-2026-746")
    verified = pm.audit_receipt(repo.root, "trae-111111", plan)
    assert verified["verdict"] == "PASS"

    # 4) 篡改凭证去掉 reviewer_session_sha256、改成空白/非法非64-hex串或改成作者会话/窗口 PID 哈希，audit_receipt 必须失败关闭
    for bad_update in (
        {"reviewer_session_sha256": None},
        {"reviewer_session_sha256": "   "},
        {"reviewer_session_sha256": "not-a-valid-sha256"},
        {"reviewer_session_sha256": pm._session_digest("trae-chat-session-aaa")},
        {"reviewer_session_sha256": pm._session_digest("vscode-9001")},
    ):
        tampered = dict(saved)
        for k, v in bad_update.items():
            if v is None:
                tampered.pop(k, None)
            else:
                tampered[k] = v
        receipt_path.write_text(json.dumps(tampered, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(pm.RefusedError, match="独立审计必须来自另一会话"):
            pm.audit_receipt(repo.root, "trae-111111", plan)


def test_check_card_refuses_divergent_candidate_change_order_and_prose_section5(
    pm: ModuleType, repo: SimpleNamespace, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """746: 控制根与候选变更单不一致即拒；散文 §5.1 明确报机读路径格式错误。"""
    change = "CHG-SCPT-2026-998"
    chg_rel = f"SW-2026-008/04_监控/01_变更管理/01_变更单/CHG-SCPT/{change}.md"
    card_rel = "SW-2026-008/04_监控/01_变更管理/03_实施卡/CARD-SW-2026-008-998_测试.md"
    approved_text = (
        f"| 变更状态 | approved |\n"
        f"| 涉及文件/交付物 | {card_rel}<br>{chg_rel}<br>AGENTS.md |\n"
    )
    order = repo.root / chg_rel
    order.parent.mkdir(parents=True, exist_ok=True)
    order.write_text(approved_text, encoding="utf-8")

    commit(
        repo.wt,
        {
            card_rel: f"> 变更单：`{change}`\n",
            chg_rel: approved_text + "\n<!-- drifted in candidate -->\n",
            "AGENTS.md": "rules\n",
        },
        f"feat: [{change}] test\n\n领卡占位: {change}",
    )
    monkeypatch.setattr(pm, "_card_precheck", lambda *_: [card_rel, chg_rel, "AGENTS.md"])
    monkeypatch.setattr(pm, "_check_card_tier", lambda *_: None)
    assert run(pm, repo.root, "merge", "w1") == 1
    assert "控制根与候选分支的变更单" in capsys.readouterr().out

    # 散文 §5.1 拒绝并给出清晰原因
    prose_text = "| 变更状态 | approved |\n| 涉及文件/交付物 | 修改 AGENTS.md 和相关文档 |\n"
    order.write_text(prose_text, encoding="utf-8")
    commit(repo.wt, {chg_rel: prose_text}, f"sync prose\n\n领卡占位: {change}")
    assert run(pm, repo.root, "merge", "w1") == 1
    assert "机读路径清单" in capsys.readouterr().out

    # 对齐为合法 <br> 清单（仅行尾不同）且独立审计通过后允许合并
    order.write_bytes(approved_text.replace("\n", "\r\n").encode("utf-8"))
    commit(repo.wt, {chg_rel: approved_text}, f"sync valid\n\n领卡占位: {change}")
    assert _audit(pm, repo, monkeypatch) == 0
    assert run(pm, repo.root, "merge", "w1") == 0


def test_find_change_orders_uses_workspace_registry_without_scanning_unrelated_dirs(
    pm: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """746 / 交接 §4.7: 有 workspace_registry.json 时直接按登记项目找变更单，不扫描仓库无关目录。"""
    chg_dir, _ledger, _proj = _setup_archive_project(tmp_path, "SW-2026-008")
    target = chg_dir / "CHG-SCPT-2026-746.md"
    target.write_text("| 变更状态 | approved |\n", encoding="utf-8")
    unrelated = tmp_path / "huge_unrelated_dir"
    unrelated.mkdir()

    walked: list[str] = []
    real_walk = pm.os.walk

    def spy_walk(top: Any, *args: Any, **kwargs: Any) -> Any:
        walked.append(str(top))
        return real_walk(top, *args, **kwargs)

    monkeypatch.setattr(pm.os, "walk", spy_walk)
    found = pm.find_change_orders(tmp_path, "CHG-SCPT-2026-746", "SW-2026-008")
    assert found == [target]
    assert not any(str(tmp_path) == w or "huge_unrelated_dir" in w for w in walked)


def test_merge_adopts_byte_identical_change_order_while_preserving_unrelated_dirty_ledger(
    pm: ModuleType, repo: SimpleNamespace
) -> None:
    """746: 控制根同时有未提交的 748 台账修改和同字节 746 变更单时，合并采纳 746 并原样保留台账。"""
    ledger = pm.GOVERNANCE_LEDGER
    chg_746 = f"{pm.GOVERNANCE_DIR}01_变更单/CHG-SCPT/CHG-SCPT-2026-746.md"
    chg_748 = f"{pm.GOVERNANCE_DIR}01_变更单/CHG-SCPT/CHG-SCPT-2026-748.md"
    commit(repo.root, {ledger: "base ledger\n"}, "base ledger")
    git(repo.wt, "merge", "--quiet", "main")
    (repo.root / ledger).write_bytes(b"base ledger\r\n748 pending row\r\n")
    (repo.root / chg_746).parent.mkdir(parents=True, exist_ok=True)
    (repo.root / chg_746).write_bytes("| 变更状态 | approved |\r\n".encode())
    (repo.root / chg_748).write_bytes("| 变更状态 | implementing |\r\n".encode())

    commit(repo.wt, {chg_746: "| 变更状态 | approved |\n", "docs/note.md": "ok\n"}, f"docs\n\n{CARD}")
    assert run(pm, repo.root, "merge", "w1") == 0
    assert (repo.root / ledger).read_bytes() == b"base ledger\r\n748 pending row\r\n"
    assert (repo.root / chg_748).read_bytes() == "| 变更状态 | implementing |\r\n".encode()
    assert git(repo.root, "show", f"main:{chg_746}").stdout == "| 变更状态 | approved |\n"


def test_pointer_only_sync_adopts_three_live_pointers_without_full_gate_or_audit(
    pm: ModuleType, repo: SimpleNamespace
) -> None:
    """746: 仅含三份与现役逐字一致发布指针的提交（如 25e9a04a）走索引采纳 + 非全量门禁，不动磁盘现役指针。"""
    pointer_bytes, payload_rel = _local_live_release_pointers(repo)
    files = {rel: raw.decode("utf-8").replace("\r\n", "\n") for rel, raw in pointer_bytes.items()}
    commit(repo.wt, files, f"chore(release): 记录现役发布指针\n\n{CARD}")
    assert run(pm, repo.root, "merge", "w1") == 0
    assert repo.gates == [False]
    assert all((repo.root / path).read_bytes() == raw for path, raw in pointer_bytes.items())
    assert (repo.root / payload_rel).read_bytes() == b"live payload\n"
    assert git(repo.root, "ls-tree", "--name-only", "main", "--", payload_rel).stdout == ""
    entry = pm.read_log(repo.root)[-1]
    assert "audit" not in entry
    assert set(entry["adopted"]) == set(pointer_bytes)


def test_clean_control_root_refuses_direct_release_pointer_overwrite(
    pm: ModuleType, repo: SimpleNamespace, capsys: Any
) -> None:
    """746 审计复核回归: 控制根干净时，普通分支不得改写任一或全部现役发布指针。"""
    base_ptrs = {
        "00_Infrastructure/auto_pm/active_release.json": '{"release_id": "1.3.3-1359a6f"}\n',
        "00_Infrastructure/auto_pm/previous_release.json": '{"release_id": "1.3.3-0000000"}\n',
        "00_Infrastructure/auto_pm/deployment_manifest.json": '{"releases": {"1.3.3-1359a6f": {}}}\n',
    }
    base = commit(repo.root, base_ptrs, "seed live pointers")
    git(repo.wt, "merge", "--quiet", "main")

    # 1) 单改 active_release.json 企图静默切版必须被拒
    commit(
        repo.wt,
        {"00_Infrastructure/auto_pm/active_release.json": '{"release_id": "9.9.9-rogue"}\n'},
        f"rogue single pointer\n\n{CARD}",
    )
    assert run(pm, repo.root, "merge", "w1") == 1
    assert "不允许在普通合并中直接改写现役发布指针" in capsys.readouterr().out
    assert rev(repo.root, "main") == base
    assert (repo.root / "00_Infrastructure/auto_pm/active_release.json").read_text(encoding="utf-8") == base_ptrs[
        "00_Infrastructure/auto_pm/active_release.json"
    ]

    # 2) 同时改三份发布指针（与控制根干净磁盘不符）也必须被拒
    commit(
        repo.wt,
        {
            "00_Infrastructure/auto_pm/active_release.json": '{"release_id": "9.9.9-rogue"}\n',
            "00_Infrastructure/auto_pm/previous_release.json": '{"release_id": "1.3.3-1359a6f"}\n',
            "00_Infrastructure/auto_pm/deployment_manifest.json": '{"releases": {"9.9.9-rogue": {}}}\n',
        },
        f"rogue all three pointers\n\n{CARD}",
    )
    assert run(pm, repo.root, "merge", "w1") == 1
    assert "不允许在普通合并中直接改写现役发布指针" in capsys.readouterr().out
    assert rev(repo.root, "main") == base
    assert (repo.root / "00_Infrastructure/auto_pm/active_release.json").read_text(encoding="utf-8") == base_ptrs[
        "00_Infrastructure/auto_pm/active_release.json"
    ]


def test_single_file_record_branch_audit_tier_policy(
    pm: ModuleType, repo: SimpleNamespace, capsys: Any
) -> None:
    """746 / 交接 §4.15: 不绑正式变更单、不删记录的单文件记录分支免审计；删除记录仍必须用户批准和独立审计。"""
    rec = f"{pm.GOVERNANCE_DIR}01_变更单/CHG-SCPT/CHG-SCPT-2026-745.md"
    commit(repo.wt, {rec: "| 变更状态 | completed |\n"}, f"docs(change): 补入库记录\n\n{CARD}")
    plan = pm.plan_merge(repo.root, "w1")
    assert plan.requires_audit is False
    assert plan.user_paths == []
    assert run(pm, repo.root, "merge", "w1") == 0
    assert "audit" not in pm.read_log(repo.root)[-1]

    # 删除该记录文件必须进入受保护路径（需用户批准与独立审计）
    git(repo.wt, "merge", "--quiet", "main")
    git(repo.wt, "rm", "--quiet", rec)
    git(repo.wt, "commit", "-m", f"rm record\n\n{CARD}")
    assert run(pm, repo.root, "merge", "w1") == 1
    assert "没有本卡的实施卡" in capsys.readouterr().out


def test_750_modifying_already_completed_change_order_escalates_to_user_paths(
    pm: ModuleType, repo: SimpleNamespace, capsys: Any
) -> None:
    """CHG-SCPT-2026-750 / #6: 已在 main 中为 completed 的变更单被短名分支修改时，必须升级到 user_paths。"""
    rec = f"{pm.GOVERNANCE_DIR}01_变更单/CHG-SCPT/CHG-SCPT-2026-740.md"
    commit(repo.root, {rec: "| 变更状态 | completed |\n正文 v1\n"}, "seed completed chg")
    git(repo.wt, "merge", "--quiet", "main")

    commit(repo.wt, {rec: "| 变更状态 | completed |\n正文被篡改 v2\n"}, f"docs: tamper\n\n{CARD}")
    assert run(pm, repo.root, "merge", "w1") == 1
    assert "需核对实施卡的变更" in capsys.readouterr().out


def test_750_archive_changes_uses_batched_tree_sha1_without_per_file_git_blob_calls(
    pm: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CHG-SCPT-2026-750 / #5: archive-changes 批量扫描 20 张已同步变更单时不再逐文件调用 _git_blob。"""
    chg_dir, ledger, _proj = _setup_archive_project(tmp_path, "SW-2026-008")
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.invalid")
    git(tmp_path, "config", "user.name", "t")
    rows = []
    for idx in range(1, 21):
        chg = f"CHG-SCPT-2026-{idx:03d}"
        (chg_dir / f"{chg}.md").write_text(f"| 变更状态 | completed |\n# {chg}\n", encoding="utf-8")
        rows.append(f"| {idx} | [{chg}](../01_变更单/CHG-SCPT/{chg}.md) | SCPT | DEF | 已完成 |")
    ledger.write_text(
        "# 台账\n\n## 变更单索引\n\n| 序号 | 变更编号 | 领域 | 性质 | 状态 |\n|---|---|---|---|---|\n"
        + "\n".join(rows) + "\n",
        encoding="utf-8",
    )
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "seed 20 completed chgs")

    # Add 1 new completed CHG on disk (not yet in main)
    new_chg = "CHG-SCPT-2026-021"
    (chg_dir / f"{new_chg}.md").write_text(f"| 变更状态 | completed |\n# {new_chg}\n", encoding="utf-8")
    ledger.write_text(
        ledger.read_text(encoding="utf-8")
        + f"| 21 | [{new_chg}](../01_变更单/CHG-SCPT/{new_chg}.md) | SCPT | DEF | 已完成 |\n",
        encoding="utf-8",
    )

    blob_calls: list[str] = []
    real_git_blob = pm._git_blob

    def spy_git_blob(root: Path, ref: str, rel_path: str) -> bytes | None:
        blob_calls.append(rel_path)
        result = real_git_blob(root, ref, rel_path)
        assert result is None or isinstance(result, bytes)
        return result

    monkeypatch.setattr(pm, "_git_blob", spy_git_blob)
    plan = pm._collect_archive_plan(tmp_path, pm.Git(tmp_path), rev(tmp_path, "main"), "SW-2026-008", [])
    assert plan.selected == [new_chg]
    # Only the single ledger file was fetched via _git_blob; none of the 21 CHGs triggered per-file _git_blob!
    assert len(blob_calls) == 1 and blob_calls[0].endswith("01_版本变更台账.md")

