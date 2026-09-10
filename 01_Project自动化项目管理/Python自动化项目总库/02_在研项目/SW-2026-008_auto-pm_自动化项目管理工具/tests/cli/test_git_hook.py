"""Regression tests for Git hook launcher generation."""

from __future__ import annotations

from pathlib import Path

from auto_pm.cli.__main__ import cli
from click.testing import CliRunner


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
