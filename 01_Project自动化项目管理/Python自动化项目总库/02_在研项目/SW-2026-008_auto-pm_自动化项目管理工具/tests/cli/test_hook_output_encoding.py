"""TD-SW008-015：提交钩子在 GBK 等窄编码终端下，不能因为输出里的 emoji 报编码错误，更不能因此改变门禁结论。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[2]


def _run_hook(repo: Path, encoding: str) -> subprocess.CompletedProcess[bytes]:
    env = {**os.environ, "PYTHONIOENCODING": encoding}
    env.pop("PYTHONUTF8", None)
    return subprocess.run(
        [sys.executable, "main.py", "-w", str(repo), "--control-root", str(repo), "git-hook", "pre-commit"],
        cwd=str(PROJECT),
        env=env,
        capture_output=True,
        check=False,
    )


@pytest.fixture
def staged_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (["init", "-q"], ["config", "user.email", "t@example.invalid"], ["config", "user.name", "t"]):
        subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True)
    (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.py"], cwd=str(repo), check=True, capture_output=True)
    return repo


@pytest.mark.parametrize("encoding", ["gbk:strict", "ascii:strict", "cp936:strict"])
def test_the_hook_prints_without_an_encoding_crash_and_keeps_its_verdict(
    staged_repo: Path, encoding: str
) -> None:
    narrow = _run_hook(staged_repo, encoding)
    wide = _run_hook(staged_repo, "utf-8")
    assert b"UnicodeEncodeError" not in narrow.stderr and b"Traceback" not in narrow.stderr, narrow.stderr
    assert narrow.returncode == wide.returncode == 1, (narrow.stderr, wide.stderr)
    assert narrow.stdout, "钩子应有输出"


def test_the_hook_output_is_still_utf8_readable_when_the_terminal_is_utf8(staged_repo: Path) -> None:
    out = _run_hook(staged_repo, "utf-8").stdout.decode("utf-8")
    assert "auto-pm pre-commit" in out
