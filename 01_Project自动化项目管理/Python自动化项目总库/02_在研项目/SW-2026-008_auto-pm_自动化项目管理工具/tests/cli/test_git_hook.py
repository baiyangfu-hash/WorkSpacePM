"""Regression tests for Git hook launcher generation and enforcement."""

from __future__ import annotations

import subprocess
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
        (commit_msg, 'git-hook commit-msg "$1"'),
    ):
        assert '"$PYTHON_EXE" "$PROJECT_ROOT/main.py"' in script
        assert f'-w "$PROJECT_ROOT" {command}' in script
        assert "PYTHONPATH" not in script
        assert "python -m auto_pm" not in script
        assert "CONTAINER=" not in script


def _production_staged_files(_: Path) -> list[str]:
    return ["auto_pm/core/service.py"]


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

    monkeypatch.setattr(git_hook_enforcer, "get_staged_files", _production_staged_files)
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
        "get_staged_files",
        lambda _: ["SW-TEST/auto_pm/core/service.py"],
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
        "get_staged_files",
        lambda _: ["SW-RELATED/auto_pm/core/service.py"],
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
        "get_staged_files",
        lambda _: ["SW-RELATED/auto_pm/core/service.py"],
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
        "get_staged_files",
        lambda _: ["unknown/service.py"],
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
