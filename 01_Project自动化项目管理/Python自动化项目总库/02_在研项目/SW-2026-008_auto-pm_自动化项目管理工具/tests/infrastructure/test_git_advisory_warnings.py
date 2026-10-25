"""TD-SW008-050：Git 的换行建议性警告不得被当成“事实包含诊断”而拒绝验证。"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from auto_pm.infrastructure.control_root_guard import (
    ControlRootGuardError,
    _git_optional_output,
    clean_git_environment,
)


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def crlf_repository(tmp_path: Path) -> Path:
    """仓库要求 CRLF 检出，工作区文件却是 LF：普通 ``git diff`` 会在 stderr 打出换行建议。"""

    _git(tmp_path, "init", "-q")
    (tmp_path / ".gitattributes").write_bytes(b"* text eol=crlf\n")
    (tmp_path / "a.txt").write_bytes(b"a\r\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "init")
    (tmp_path / "a.txt").write_bytes(b"a\nb\n")
    return tmp_path


def test_the_advisory_line_ending_notice_does_not_reject_git_facts(crlf_repository: Path) -> None:
    assert _git_optional_output(crlf_repository, "diff", "--name-only").split() == ["a.txt"]


def test_the_notice_is_real_without_the_guard_environment(crlf_repository: Path) -> None:
    """对照：不带本环境时 Git 确实会在 stderr 打出建议，说明上面的用例测到了真问题。"""

    plain = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    result = subprocess.run(
        ["git", "-C", str(crlf_repository), "diff", "--name-only"],
        capture_output=True,
        text=True,
        env=plain,
        check=False,
    )
    assert "will be replaced by" in result.stderr


def test_caller_controlled_git_variables_are_still_stripped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_DIR", "/elsewhere")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "5")
    environment = clean_git_environment()
    assert "GIT_DIR" not in environment
    assert environment["GIT_CONFIG_COUNT"] == "1"
    assert environment["GIT_CONFIG_KEY_0"] == "core.safecrlf"


def test_a_real_git_failure_is_still_rejected(tmp_path: Path) -> None:
    with pytest.raises(ControlRootGuardError):
        _git_optional_output(tmp_path, "diff", "--name-only")
