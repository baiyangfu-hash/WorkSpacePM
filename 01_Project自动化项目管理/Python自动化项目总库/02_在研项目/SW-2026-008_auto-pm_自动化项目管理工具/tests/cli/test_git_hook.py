"""Regression tests for Git hook launcher generation and enforcement."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from auto_pm.cli.__main__ import cli
from click.testing import CliRunner

from auto_pm.infrastructure import git_hook_enforcer
from auto_pm.infrastructure.git_hook_enforcer import enforce_commit_msg, enforce_pre_commit


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


def _write_closed_chg(workspace_root: Path, chg_id: str) -> None:
    chg_file = workspace_root / "01_变更单" / f"{chg_id}.md"
    chg_file.parent.mkdir(parents=True)
    chg_file.write_text(
        f"""# {chg_id}
## 3. 变更基本信息
### 3.4 申请信息
| 变更状态 | closed |
""",
        encoding="utf-8",
    )


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

    monkeypatch.setattr(git_hook_enforcer, "get_staged_files", _production_staged_files)
    monkeypatch.setattr("auto_pm.core.project_service.ProjectService", ProjectService)
    monkeypatch.setattr(
        "auto_pm.domain.change.ledger_reconciler.LedgerReconciler",
        FailingLedgerReconciler,
    )

    assert enforce_pre_commit(tmp_path) == 1
    output = capsys.readouterr().out
    assert "台账检查异常" in output
    assert "拒绝提交" in output


def test_enforce_commit_msg_rejects_message_read_error(tmp_path: Path, monkeypatch, capsys) -> None:
    msg_file = tmp_path / "COMMIT_EDITMSG"
    msg_file.write_text("feat: [CHG-SCPT-2026-170] test", encoding="utf-8")

    def raise_message_read_error(*_args: object, **_kwargs: object) -> str:
        raise OSError("message unavailable")

    monkeypatch.setattr(git_hook_enforcer, "get_staged_files", _production_staged_files)
    monkeypatch.setattr(Path, "read_text", raise_message_read_error)

    assert enforce_commit_msg(tmp_path, msg_file) == 1
    output = capsys.readouterr().out
    assert "无法读取或解析提交信息" in output
    assert "拒绝提交" in output


def test_enforce_commit_msg_rejects_chg_parser_error(tmp_path: Path, monkeypatch, capsys) -> None:
    chg_id = "CHG-SCPT-2026-170"
    _write_closed_chg(tmp_path, chg_id)
    msg_file = tmp_path / "COMMIT_EDITMSG"
    msg_file.write_text(f"feat: [{chg_id}] test", encoding="utf-8")

    def raise_parser_error(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("parser unavailable")

    monkeypatch.setattr(git_hook_enforcer, "get_staged_files", _production_staged_files)
    monkeypatch.setattr(git_hook_enforcer.ChgParser, "parse", raise_parser_error)

    assert enforce_commit_msg(tmp_path, msg_file) == 1
    output = capsys.readouterr().out
    assert "解析关联变更单状态失败" in output
    assert "拒绝提交" in output


def test_enforce_commit_msg_passes_valid_closed_chg(tmp_path: Path, monkeypatch, capsys) -> None:
    chg_id = "CHG-SCPT-2026-170"
    _write_closed_chg(tmp_path, chg_id)
    msg_file = tmp_path / "COMMIT_EDITMSG"
    msg_file.write_text(f"feat: [{chg_id}] test", encoding="utf-8")

    monkeypatch.setattr(git_hook_enforcer, "get_staged_files", _production_staged_files)

    assert enforce_commit_msg(tmp_path, msg_file) == 0
    assert "强校验绑定通过" in capsys.readouterr().out
