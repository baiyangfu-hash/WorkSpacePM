"""Regression tests for Git hook launcher generation and enforcement."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from auto_pm.cli.__main__ import cli
from click.testing import CliRunner

from auto_pm.infrastructure import git_hook_enforcer
from auto_pm.infrastructure.git_hook_enforcer import (
    enforce_commit_msg,
    enforce_pre_commit,
    enforce_release_ledger_gate,
)


def test_git_hook_install_uses_root_active_release_launcher(tmp_path: Path) -> None:
    (tmp_path / ".git" / "hooks").mkdir(parents=True)

    result = CliRunner().invoke(cli, ["-w", str(tmp_path), "git-hook", "install"])

    assert result.exit_code == 0, result.output
    pre_commit = (tmp_path / ".git" / "hooks" / "pre-commit").read_text(encoding="utf-8")
    commit_msg = (tmp_path / ".git" / "hooks" / "commit-msg").read_text(encoding="utf-8")
    for script, command in (
        (pre_commit, "git-hook pre-commit"),
        (commit_msg, 'git-hook commit-msg "$MSG_FILE"'),
    ):
        assert '"$PYTHON_EXE" "$PROJECT_ROOT/main.py"' in script
        assert f'-w "$PROJECT_ROOT" {command}' in script
        assert "PYTHONPATH" not in script
        assert "python -m auto_pm" not in script
        assert "CONTAINER=" not in script
    assert 'MSG_FILE_DIR=$(dirname -- "$1")' in commit_msg
    assert 'MSG_FILE_DIR_ABS=$(cd -- "$MSG_FILE_DIR"' in commit_msg
    assert 'if [ ! -r "$MSG_FILE" ]' in commit_msg
    assert '"$GIT_COMMON_DIR"/worktrees/*/COMMIT_EDITMSG' in commit_msg


def _write_hook_probe_launcher(repo: Path) -> None:
    """Write a tiny launcher used only by real Git hook fixtures."""
    (repo / "main.py").write_text(
        """from __future__ import annotations

import json
import sys
from pathlib import Path

args = sys.argv[1:]
if args[-2:-1] == ["commit-msg"]:
    message_file = Path(args[-1])
    if not message_file.is_absolute() or not message_file.is_file():
        raise SystemExit(19)
    trace_file = Path(args[1]) / "hook-path-trace.jsonl"
    with trace_file.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"path": str(message_file)}) + "\\n")
""",
        encoding="utf-8",
    )


def _commit_with_real_hooks(repo: Path, message: str) -> None:
    tracked = repo / "tracked.txt"
    tracked.write_text(message + "\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    environment = os.environ.copy()
    environment["PATH"] = (
        str(Path(sys.executable).parent)
        + os.pathsep
        + environment.get("PATH", "")
    )
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
    )


def test_installed_commit_msg_hook_resolves_primary_and_linked_worktree_paths(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "primary repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "config", "user.name", "hook fixture")
    (repo / "tracked.txt").write_text("baseline\n", encoding="utf-8")
    _write_hook_probe_launcher(repo)
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "fixture baseline")

    result = CliRunner().invoke(cli, ["-w", str(repo), "git-hook", "install"])
    assert result.exit_code == 0, result.output
    for hook_name in ("pre-commit", "commit-msg"):
        (repo / ".git" / "hooks" / hook_name).chmod(0o755)

    _commit_with_real_hooks(repo, "primary worktree")

    linked = tmp_path / "linked worktree"
    _git(repo, "worktree", "add", "-b", "fixture-linked", str(linked))
    _commit_with_real_hooks(linked, "linked worktree")

    trace_lines = (repo / "hook-path-trace.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(trace_lines) == 2
    traced_paths = [Path(json.loads(line)["path"]) for line in trace_lines]
    assert all(path.is_absolute() for path in traced_paths)
    assert traced_paths[0].name == "COMMIT_EDITMSG"
    assert traced_paths[1].name == "COMMIT_EDITMSG"
    assert traced_paths[0] != traced_paths[1]


def _git_hook_shell() -> str:
    if os.name == "nt":
        git_executable = shutil.which("git")
        assert git_executable is not None
        shell = Path(git_executable).parent.parent / "bin" / "sh.exe"
        assert shell.is_file()
        return str(shell)
    shell = shutil.which("sh")
    assert shell is not None
    return shell


def test_installed_commit_msg_hook_rejects_missing_or_external_message_file(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "missing message repo"
    repo.mkdir()
    _git(repo, "init")
    _write_hook_probe_launcher(repo)

    result = CliRunner().invoke(cli, ["-w", str(repo), "git-hook", "install"])
    assert result.exit_code == 0, result.output
    hook = repo / ".git" / "hooks" / "commit-msg"
    hook.chmod(0o755)

    missing = subprocess.run(
        [_git_hook_shell(), "--login", str(hook), ".git/missing"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert missing.returncode != 0
    assert "message file" in missing.stderr or "message directory" in missing.stderr

    external_message = tmp_path / "COMMIT_EDITMSG"
    external_message.write_text("external\n", encoding="utf-8")
    external = subprocess.run(
        [_git_hook_shell(), "--login", str(hook), str(external_message)],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert external.returncode != 0
    assert "outside Git metadata" in external.stderr


def test_git_hook_preflight_passes_one_snapshot_to_both_shared_checks(
    tmp_path: Path, monkeypatch
) -> None:
    message_file = tmp_path / "COMMIT_EDITMSG"
    message_file.write_text("test message", encoding="utf-8")
    snapshot = git_hook_enforcer.StagedSnapshot(())
    captured_workspaces: list[Path] = []
    pre_commit_snapshots: list[git_hook_enforcer.StagedSnapshot] = []
    commit_msg_paths: list[Path] = []
    commit_msg_snapshots: list[git_hook_enforcer.StagedSnapshot] = []

    def capture_snapshot(workspace_root: Path) -> git_hook_enforcer.StagedSnapshot:
        captured_workspaces.append(workspace_root)
        return snapshot

    def run_pre_commit(
        _workspace_root: Path, supplied_snapshot: git_hook_enforcer.StagedSnapshot
    ) -> int:
        pre_commit_snapshots.append(supplied_snapshot)
        return 0

    def run_commit_msg(
        _workspace_root: Path,
        supplied_message_file: Path,
        supplied_snapshot: git_hook_enforcer.StagedSnapshot,
    ) -> int:
        commit_msg_paths.append(supplied_message_file)
        commit_msg_snapshots.append(supplied_snapshot)
        return 0

    monkeypatch.setattr("auto_pm.cli.git_hook.get_staged_snapshot", capture_snapshot)
    monkeypatch.setattr("auto_pm.cli.git_hook.enforce_pre_commit", run_pre_commit)
    monkeypatch.setattr("auto_pm.cli.git_hook.enforce_commit_msg", run_commit_msg)

    result = CliRunner().invoke(
        cli, ["-w", str(tmp_path), "git-hook", "preflight", str(message_file)]
    )

    assert result.exit_code == 0, result.output
    assert captured_workspaces == [tmp_path]
    assert pre_commit_snapshots == [snapshot]
    assert commit_msg_paths == [message_file]
    assert commit_msg_snapshots == [snapshot]


def _staged_snapshot(*paths: str) -> git_hook_enforcer.StagedSnapshot:
    return git_hook_enforcer.StagedSnapshot(
        tuple(git_hook_enforcer.StagedIndexEntry(path, "a" * 40) for path in paths)
    )


def _production_staged_snapshot(_: Path) -> git_hook_enforcer.StagedSnapshot:
    return _staged_snapshot("auto_pm/core/service.py")


def _write_project_ledger(project_root: Path) -> None:
    ledger_file = (
        project_root
        / "04_监控"
        / "01_变更管理"
        / "02_变更记录"
        / "01_版本变更台账.md"
    )
    ledger_file.parent.mkdir(parents=True)
    ledger_file.write_text("# 台账\n", encoding="utf-8")


_FIXTURE_PROJECT_ID = "SW-2026-901"
_FIXTURE_CHG_ID = "CHG-SCPT-2026-170"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _fixture_chg_content(chg_id: str, project_id: str) -> str:
    return f"""# {chg_id}

## 3. 变更基本信息

### 3.0 编号与项目

| 字段 | 内容 |
| --- | --- |
| 变更编号 | {chg_id} |
| 项目名称 | staged snapshot fixture |
| 项目编号 | {project_id} |

### 3.4 申请信息

| 字段 | 内容 |
| --- | --- |
| 变更状态 | closed |
"""


def _fixture_ledger_content(chg_id: str | None) -> str:
    entry = f"| {chg_id} | closed |\n" if chg_id else "| baseline | closed |\n"
    return f"# 版本变更台账\n\n| 变更编号 | 状态 |\n| --- | --- |\n{entry}"


def _staged_snapshot_fixture(
    tmp_path: Path,
    *,
    staged_project_id: str = _FIXTURE_PROJECT_ID,
    working_project_id: str | None = None,
    staged_ledger_has_chg: bool = True,
    working_ledger_has_chg: bool | None = None,
    add_unknown_production_file: bool = False,
) -> tuple[Path, Path]:
    """建立真实 Git index，避免由 mock 掩盖 staged/working-tree 差异。"""
    repo = tmp_path / "snapshot-repo"
    project = repo / f"{_FIXTURE_PROJECT_ID}_fixture"
    change_file = project / "01_变更单" / f"{_FIXTURE_CHG_ID}.md"
    ledger_file = (
        project
        / "04_监控"
        / "01_变更管理"
        / "02_变更记录"
        / "01_版本变更台账.md"
    )
    code_file = project / "src" / "service.py"
    code_file.parent.mkdir(parents=True)
    change_file.parent.mkdir(parents=True)
    ledger_file.parent.mkdir(parents=True)
    (project / ".copier-answers.yml").write_text(
        f"project_id: {_FIXTURE_PROJECT_ID}\nproject_name: snapshot fixture\nstack: python\n",
        encoding="utf-8",
    )
    code_file.write_text("VALUE = 1\n", encoding="utf-8")
    change_file.write_text("# fixture baseline\n", encoding="utf-8")
    ledger_file.write_text("# fixture baseline\n", encoding="utf-8")

    _git(repo, "init")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "config", "user.name", "snapshot fixture")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "fixture baseline")

    code_file.write_text("VALUE = 2\n", encoding="utf-8")
    change_file.write_text(
        _fixture_chg_content(_FIXTURE_CHG_ID, staged_project_id), encoding="utf-8"
    )
    ledger_file.write_text(
        _fixture_ledger_content(_FIXTURE_CHG_ID if staged_ledger_has_chg else None),
        encoding="utf-8",
    )
    _git(repo, "add", str(code_file.relative_to(repo)))
    _git(repo, "add", str(change_file.relative_to(repo)))
    _git(repo, "add", str(ledger_file.relative_to(repo)))

    if working_project_id is not None:
        change_file.write_text(
            _fixture_chg_content(_FIXTURE_CHG_ID, working_project_id), encoding="utf-8"
        )
    if working_ledger_has_chg is not None:
        ledger_file.write_text(
            _fixture_ledger_content(_FIXTURE_CHG_ID if working_ledger_has_chg else None),
            encoding="utf-8",
        )
    if add_unknown_production_file:
        unknown_file = repo / "unregistered" / "service.py"
        unknown_file.parent.mkdir()
        unknown_file.write_text("VALUE = 3\n", encoding="utf-8")
        _git(repo, "add", str(unknown_file.relative_to(repo)))

    message_file = repo / "COMMIT_EDITMSG"
    message_file.write_text(f"feat: [{_FIXTURE_CHG_ID}] snapshot test\n", encoding="utf-8")
    return repo, message_file


def test_enforce_pre_commit_rejects_staged_files_lookup_error(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    def raise_git_error(*_args: object, **_kwargs: object) -> None:
        raise OSError("git unavailable")

    monkeypatch.setattr(git_hook_enforcer.subprocess, "run", raise_git_error)

    assert enforce_pre_commit(tmp_path) == 1
    output = capsys.readouterr().out
    assert "无法读取 Git 暂存区" in output
    assert "拒绝提交" in output


def test_enforce_commit_msg_rejects_staged_files_lookup_error(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    msg_file = tmp_path / "COMMIT_EDITMSG"
    msg_file.write_text("feat: [CHG-SCPT-2026-170] test", encoding="utf-8")

    def raise_git_error(*_args: object, **_kwargs: object) -> None:
        raise OSError("git unavailable")

    monkeypatch.setattr(git_hook_enforcer.subprocess, "run", raise_git_error)

    assert enforce_commit_msg(tmp_path, msg_file) == 1
    output = capsys.readouterr().out
    assert "无法读取 Git 暂存区" in output
    assert "拒绝提交" in output


def test_enforce_pre_commit_rejects_project_service_error(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    class FailingProjectService:
        def __init__(self, _: str) -> None:
            raise RuntimeError("project service unavailable")

    monkeypatch.setattr(
        git_hook_enforcer, "get_staged_snapshot", _production_staged_snapshot
    )
    monkeypatch.setattr(
        "auto_pm.core.project_service.ProjectService",
        FailingProjectService,
    )

    assert enforce_pre_commit(tmp_path) == 1
    output = capsys.readouterr().out
    assert "台账检查异常" in output
    assert "拒绝提交" in output


def test_enforce_pre_commit_rejects_ledger_error(tmp_path: Path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "SW-TEST"
    _write_project_ledger(project_root)

    class ProjectService:
        def __init__(self, _: str) -> None:
            pass

        def list_projects(self) -> list[SimpleNamespace]:
            return [SimpleNamespace(id="SW-TEST", path=project_root)]

    class FailingLedgerReconciler:
        def reconcile(self, _: str) -> None:
            raise RuntimeError("ledger unavailable")

    monkeypatch.setattr(
        git_hook_enforcer,
        "get_staged_snapshot",
        lambda _: _staged_snapshot("SW-TEST/auto_pm/core/service.py"),
    )
    monkeypatch.setattr("auto_pm.core.project_service.ProjectService", ProjectService)
    monkeypatch.setattr(
        "auto_pm.domain.change.ledger_reconciler.LedgerReconciler",
        FailingLedgerReconciler,
    )

    assert enforce_pre_commit(tmp_path) == 1
    output = capsys.readouterr().out
    assert "台账检查异常" in output
    assert "拒绝通过" in output


def test_enforce_pre_commit_reports_unrelated_ledger_error_without_blocking(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    related_root = tmp_path / "SW-RELATED"
    unrelated_root = tmp_path / "SW-UNRELATED"
    _write_project_ledger(related_root)
    _write_project_ledger(unrelated_root)

    class ProjectService:
        def __init__(self, _: str) -> None:
            pass

        def list_projects(self) -> list[SimpleNamespace]:
            return [
                SimpleNamespace(id="SW-RELATED", path=related_root),
                SimpleNamespace(id="SW-UNRELATED", path=unrelated_root),
            ]

    class LedgerReconciler:
        def reconcile(self, project_root: str) -> SimpleNamespace:
            if Path(project_root) == unrelated_root:
                return SimpleNamespace(
                    is_clean=False,
                    missing_in_ledger=["CHG-SCPT-2026-999"],
                    orphan_in_ledger=[],
                    status_mismatches=[],
                )
            return SimpleNamespace(
                is_clean=True,
                missing_in_ledger=[],
                orphan_in_ledger=[],
                status_mismatches=[],
            )

    monkeypatch.setattr(
        git_hook_enforcer,
        "get_staged_snapshot",
        lambda _: _staged_snapshot("SW-RELATED/auto_pm/core/service.py"),
    )
    monkeypatch.setattr("auto_pm.core.project_service.ProjectService", ProjectService)
    monkeypatch.setattr(
        "auto_pm.domain.change.ledger_reconciler.LedgerReconciler",
        LedgerReconciler,
    )

    assert enforce_pre_commit(tmp_path) == 0
    output = capsys.readouterr().out
    assert "SW-UNRELATED" in output
    assert "仅报告不阻断" in output
    assert "相关项目台账门禁校验通过" in output


def test_enforce_pre_commit_rejects_missing_related_ledger(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    related_root = tmp_path / "SW-RELATED"
    related_root.mkdir()

    class ProjectService:
        def __init__(self, _: str) -> None:
            pass

        def list_projects(self) -> list[SimpleNamespace]:
            return [SimpleNamespace(id="SW-RELATED", path=related_root)]

    monkeypatch.setattr(
        git_hook_enforcer,
        "get_staged_snapshot",
        lambda _: _staged_snapshot("SW-RELATED/auto_pm/core/service.py"),
    )
    monkeypatch.setattr("auto_pm.core.project_service.ProjectService", ProjectService)

    assert enforce_pre_commit(tmp_path) == 1
    output = capsys.readouterr().out
    assert "关联项目缺少版本变更台账" in output


def test_enforce_pre_commit_rejects_unknown_production_owner(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    project_root = tmp_path / "SW-RELATED"
    _write_project_ledger(project_root)

    class ProjectService:
        def __init__(self, _: str) -> None:
            pass

        def list_projects(self) -> list[SimpleNamespace]:
            return [SimpleNamespace(id="SW-RELATED", path=project_root)]

    monkeypatch.setattr(
        git_hook_enforcer,
        "get_staged_snapshot",
        lambda _: _staged_snapshot("unknown/service.py"),
    )
    monkeypatch.setattr("auto_pm.core.project_service.ProjectService", ProjectService)

    assert enforce_pre_commit(tmp_path) == 1
    output = capsys.readouterr().out
    assert "暂存生产文件归属未知或不唯一" in output


def test_enforce_release_ledger_gate_blocks_any_registered_project_error(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    related_root = tmp_path / "SW-RELATED"
    unrelated_root = tmp_path / "SW-UNRELATED"
    _write_project_ledger(related_root)
    _write_project_ledger(unrelated_root)

    class ProjectService:
        def __init__(self, _: str) -> None:
            pass

        def list_projects(self) -> list[SimpleNamespace]:
            return [
                SimpleNamespace(id="SW-RELATED", path=related_root),
                SimpleNamespace(id="SW-UNRELATED", path=unrelated_root),
            ]

    class LedgerReconciler:
        def reconcile(self, project_root: str) -> SimpleNamespace:
            return SimpleNamespace(
                is_clean=Path(project_root) != unrelated_root,
                missing_in_ledger=["CHG-SCPT-2026-999"],
                orphan_in_ledger=[],
                status_mismatches=[],
            )

    monkeypatch.setattr("auto_pm.core.project_service.ProjectService", ProjectService)
    monkeypatch.setattr(
        "auto_pm.domain.change.ledger_reconciler.LedgerReconciler",
        LedgerReconciler,
    )

    assert enforce_release_ledger_gate(tmp_path) == 1
    output = capsys.readouterr().out
    assert "SW-UNRELATED" in output
    assert "全局台账未闭环" in output


def test_git_hook_release_gate_cli_uses_global_gate(tmp_path: Path, monkeypatch) -> None:
    called: dict[str, Path] = {}

    def fake_gate(workspace_root: Path) -> int:
        called["workspace_root"] = workspace_root
        return 0

    monkeypatch.setattr(
        "auto_pm.cli.git_hook.enforce_release_ledger_gate",
        fake_gate,
    )

    result = CliRunner().invoke(cli, ["-w", str(tmp_path), "git-hook", "release-gate"])

    assert result.exit_code == 0, result.output
    assert called["workspace_root"] == tmp_path


def test_enforce_commit_msg_rejects_message_read_error(tmp_path: Path, monkeypatch, capsys) -> None:
    repo, msg_file = _staged_snapshot_fixture(tmp_path)

    def raise_message_read_error(*_args: object, **_kwargs: object) -> str:
        raise OSError("message unavailable")

    monkeypatch.setattr(Path, "read_text", raise_message_read_error)

    assert enforce_commit_msg(repo, msg_file) == 1
    output = capsys.readouterr().out
    assert "无法读取或解析提交信息" in output
    assert "拒绝提交" in output


def test_enforce_commit_msg_rejects_chg_parser_error(tmp_path: Path, monkeypatch, capsys) -> None:
    repo, msg_file = _staged_snapshot_fixture(tmp_path)

    def raise_parser_error(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("parser unavailable")

    monkeypatch.setattr(git_hook_enforcer.ChgParser, "parse", raise_parser_error)

    assert enforce_commit_msg(repo, msg_file) == 1
    output = capsys.readouterr().out
    assert "解析关联变更单状态失败" in output
    assert "拒绝提交" in output


def test_enforce_commit_msg_passes_valid_closed_chg(tmp_path: Path, capsys) -> None:
    repo, msg_file = _staged_snapshot_fixture(tmp_path)

    assert enforce_commit_msg(repo, msg_file) == 0
    assert "强校验绑定通过" in capsys.readouterr().out


def test_enforce_commit_msg_uses_supplied_snapshot_without_recapturing(
    tmp_path: Path, monkeypatch
) -> None:
    repo, msg_file = _staged_snapshot_fixture(tmp_path)
    snapshot = git_hook_enforcer.get_staged_snapshot(repo)

    def reject_recapture(_: Path) -> git_hook_enforcer.StagedSnapshot:
        raise AssertionError("the supplied snapshot must be reused")

    monkeypatch.setattr(git_hook_enforcer, "get_staged_snapshot", reject_recapture)

    assert enforce_commit_msg(repo, msg_file, snapshot) == 0


def test_enforce_commit_msg_rejects_missing_staged_chg(tmp_path: Path, capsys) -> None:
    repo, msg_file = _staged_snapshot_fixture(tmp_path)
    change_file = repo / f"{_FIXTURE_PROJECT_ID}_fixture" / "01_变更单" / f"{_FIXTURE_CHG_ID}.md"
    _git(repo, "restore", "--staged", str(change_file.relative_to(repo)))

    assert enforce_commit_msg(repo, msg_file) == 1
    assert "暂存快照缺少或重复关联变更单" in capsys.readouterr().out


def test_enforce_commit_msg_rejects_staged_pid_mismatch(tmp_path: Path, capsys) -> None:
    repo, msg_file = _staged_snapshot_fixture(tmp_path, staged_project_id="SW-2026-902")

    assert enforce_commit_msg(repo, msg_file) == 1
    assert "暂存变更单 PID 与生产代码归属不一致" in capsys.readouterr().out


def test_enforce_commit_msg_rejects_unstaged_chg_repair(tmp_path: Path, capsys) -> None:
    repo, msg_file = _staged_snapshot_fixture(
        tmp_path,
        staged_project_id="SW-2026-902",
        working_project_id=_FIXTURE_PROJECT_ID,
    )

    assert enforce_commit_msg(repo, msg_file) == 1
    assert "工作区证据与暂存快照不一致" in capsys.readouterr().out


def test_enforce_commit_msg_rejects_unstaged_ledger_repair(tmp_path: Path, capsys) -> None:
    repo, msg_file = _staged_snapshot_fixture(
        tmp_path,
        staged_ledger_has_chg=False,
        working_ledger_has_chg=True,
    )

    assert enforce_commit_msg(repo, msg_file) == 1
    assert "工作区证据与暂存快照不一致" in capsys.readouterr().out


def test_enforce_commit_msg_rejects_unknown_staged_production_project(tmp_path: Path, capsys) -> None:
    repo, msg_file = _staged_snapshot_fixture(tmp_path, add_unknown_production_file=True)

    assert enforce_commit_msg(repo, msg_file) == 1
    assert "暂存生产文件归属未知或不唯一" in capsys.readouterr().out


def test_enforce_commit_msg_rejects_staged_blob_read_error(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo, msg_file = _staged_snapshot_fixture(tmp_path)

    def raise_blob_error(*_args: object, **_kwargs: object) -> bytes:
        raise git_hook_enforcer.StagedSnapshotError("blob unavailable")

    monkeypatch.setattr(git_hook_enforcer, "_read_staged_blob", raise_blob_error)

    assert enforce_commit_msg(repo, msg_file) == 1
    output = capsys.readouterr().out
    assert "暂存快照的 CHG/PID/台账证据" in output
    assert "blob unavailable" in output
