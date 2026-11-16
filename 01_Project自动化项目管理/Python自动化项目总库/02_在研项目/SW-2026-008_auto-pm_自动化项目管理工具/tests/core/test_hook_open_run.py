"""Run 开着时在工位里提交，提交钩子拒（G 工位止血第 3 条，卡 280；试车九条第 5 条）。

以前钩子只看提交说明里有没有单号，写上单号就在开着的 Run 里提交成了，Run 记的提交号和工位 HEAD 对不上，``pm verify`` 的证据作废。
现在 pre-commit 先问账本：这个工位有没有没收口的 Run；有就拒，说的话和 ``pm verify`` 发现 HEAD 挪了时说的是同一句。
真进程的演练（装钩子、开 Run、在工位里 ``git commit``）在试车九条入库测试第 5 条（卡 277），由 G 摘掉它的严格 xfail。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from auto_pm.contracts.run_open_commit import run_open_commit_hint
from auto_pm.infrastructure import continuity_store, git_hook_enforcer
from auto_pm.infrastructure.continuity_store import ContinuityStore
from tests.core.test_continuity_execution_service import Clock, _services, _start

SENTENCE = "Run 开着，收口前不要提交；已提交的用 git reset --soft {head} 撤回后再交卷"
HEAD = "a" * 40


def test_the_sentence_is_the_one_the_card_asks_for() -> None:
    assert run_open_commit_hint(HEAD) == SENTENCE.format(head=HEAD)
    assert run_open_commit_hint("") == SENTENCE.format(head="<Run 记的提交号>")


def test_the_ledger_lists_an_open_run_only_for_its_own_worktree(tmp_path: Path) -> None:
    clock = Clock()
    clock.value = datetime.now(UTC)
    _, service = _services(tmp_path, clock)
    _start(service)
    store = ContinuityStore(tmp_path)
    assert [run.run_id for run in store.list_open_runs_in_worktree(tmp_path)] == ["RUN-001"]
    assert store.list_open_runs_in_worktree(tmp_path / "elsewhere") == ()


def _ledger(root: Path) -> None:
    (root / ".auto-pm").mkdir(parents=True)
    (root / ".auto-pm" / "continuity.db").write_bytes(b"")


def _open_runs(monkeypatch: pytest.MonkeyPatch, runs: tuple[object, ...] | Exception) -> list[Path]:
    asked: list[Path] = []

    def listed(self: ContinuityStore, worktree: str | Path) -> tuple[object, ...]:
        asked.append(Path(worktree))
        if isinstance(runs, Exception):
            raise runs
        return runs

    monkeypatch.setattr(continuity_store.ContinuityStore, "__init__", lambda self, root, *a, **k: None)
    monkeypatch.setattr(continuity_store.ContinuityStore, "list_open_runs_in_worktree", listed)
    return asked


def test_a_commit_in_a_station_with_an_open_run_is_refused_with_the_way_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    control, station = tmp_path / "R", tmp_path / "R" / ".auto-pm" / "worktrees" / "claude-aaaaaa"
    _ledger(control)
    station.mkdir(parents=True)
    run = SimpleNamespace(run_id="RUN-W5", state=SimpleNamespace(value="RUNNING"), git_head=HEAD)
    asked = _open_runs(monkeypatch, (run,))

    assert git_hook_enforcer._enforce_no_open_run(station, control) == 1
    said = capsys.readouterr().out
    assert SENTENCE.format(head=HEAD) in said and "RUN-W5" in said and "RUNNING" in said, said
    assert asked == [station]


def test_no_open_run_lets_the_commit_through(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    control, station = tmp_path / "R", tmp_path / "W"
    _ledger(control)
    station.mkdir()
    _open_runs(monkeypatch, ())
    assert git_hook_enforcer._enforce_no_open_run(station, control) == 0


def test_the_control_root_itself_and_a_clone_without_a_ledger_are_not_asked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    control, station = tmp_path / "R", tmp_path / "W"
    station.mkdir()
    control.mkdir()
    asked = _open_runs(monkeypatch, ())
    assert git_hook_enforcer._enforce_no_open_run(station, control) == 0, "没有账本就没有 Run 可查"
    _ledger(control)
    assert git_hook_enforcer._enforce_no_open_run(control, control) == 0, "控制根不是哪个 Run 的工位"
    assert git_hook_enforcer._enforce_no_open_run(station, None) == 0
    assert asked == []


def test_a_ledger_that_cannot_be_read_refuses_rather_than_guessing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    control, station = tmp_path / "R", tmp_path / "W"
    _ledger(control)
    station.mkdir()
    _open_runs(monkeypatch, RuntimeError("database is locked"))
    assert git_hook_enforcer._enforce_no_open_run(station, control) == 1
    assert "读不出账本" in capsys.readouterr().out


def test_pre_commit_runs_the_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Path, Path | None]] = []

    def refuse(ws: Path, ctrl: Path | None) -> int:
        calls.append((ws, ctrl))
        return 1

    monkeypatch.setattr(git_hook_enforcer, "_enforce_no_open_run", refuse)
    monkeypatch.setattr(git_hook_enforcer, "_enforce_ledger_pre_commit", lambda *a: 0)
    monkeypatch.setattr(git_hook_enforcer, "_enforce_secret_scan", lambda ws: 0)
    monkeypatch.setattr(git_hook_enforcer, "_enforce_ignored_additions", lambda ws: 0)
    monkeypatch.setattr("auto_pm.infrastructure.plc_doc_hook.enforce_plc_docs", lambda ws, paths: 0)
    snapshot = git_hook_enforcer.StagedSnapshot(entries=())
    assert git_hook_enforcer.enforce_pre_commit(tmp_path, snapshot, tmp_path / "R") == 1
    assert calls == [(tmp_path, tmp_path / "R")]
