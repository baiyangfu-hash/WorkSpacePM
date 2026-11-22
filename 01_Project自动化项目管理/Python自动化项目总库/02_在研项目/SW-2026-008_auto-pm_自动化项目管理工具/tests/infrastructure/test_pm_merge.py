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
