"""End to end: a real ``git commit`` through the installed pre-commit hook refuses PLC documents that disagree with the code (V01D)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from auto_pm.cli.__main__ import cli
from auto_pm.plc import doc_consistency as dc
from click.testing import CliRunner

import auto_pm
from tests.plc.test_doc_consistency import build

IFC = "0100_PLC自动化/DJ-TEST-001/02_PLC程序/PLC_ST/01_泵/PRD/接口文档_IFC-FB_Pump.md"
LAUNCHER = """from auto_pm.cli.__main__ import cli

if __name__ == "__main__":
    cli()
"""


def git(repo: Path, *args: str, check: bool = True, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=tester", "-c", "user.email=t@example.test", "-c", "core.autocrlf=false", *args],
        check=check, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
    )


def commit_env() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment.get("PATH", "")
    environment["PYTHONPATH"] = str(Path(auto_pm.__file__).resolve().parent.parent)
    environment["PYTHONIOENCODING"] = "utf-8"
    return environment


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    project = build(root / "0100_PLC自动化")
    (project / ".plc.json").write_text('{"name": "DJ-TEST-001", "version": "V1.0.0", "description": "t"}', encoding="utf-8")
    (root / "main.py").write_text(LAUNCHER, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "baseline")
    result = CliRunner().invoke(cli, ["-w", str(root), "git-hook", "install"])
    assert result.exit_code == 0, result.output
    (root / ".git" / "hooks" / "commit-msg").unlink()
    (root / ".git" / "hooks" / "pre-commit").chmod(0o755)
    return root


def test_e1_a_real_commit_is_refused_then_accepted_after_the_documents_agree(repo: Path) -> None:
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    doc = repo / IFC
    doc.write_text(doc.read_text(encoding="utf-8").replace("| `i_bStart` | BOOL |", "| `i_bStart` | INT |"), encoding="utf-8", newline="\n")
    git(repo, "add", IFC)

    refused = git(repo, "commit", "-m", "wrong type", check=False, env=commit_env())

    assert refused.returncode != 0
    shown = refused.stdout + refused.stderr  # Git forwards a hook's standard output to its standard error
    assert "物理阻断" in shown and "FB_Pump.i_bStart" in shown
    assert git(repo, "rev-parse", "HEAD").stdout.strip() == head

    doc.write_text(doc.read_text(encoding="utf-8").replace("| `i_bStart` | INT |", "| `i_bStart` | BOOL |"), encoding="utf-8", newline="\n")
    git(repo, "add", IFC)
    accepted = git(repo, "commit", "-m", "back to the code type", check=False, env=commit_env())
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    assert git(repo, "rev-parse", "HEAD").stdout.strip() != head


def test_e2_a_marker_row_is_refused_until_it_is_confirmed(repo: Path) -> None:
    doc = repo / IFC
    doc.write_text(doc.read_text(encoding="utf-8").replace("| 启动命令 |", f"| {dc.MARKER}启动命令 |"), encoding="utf-8", newline="\n")
    git(repo, "add", IFC)
    refused = git(repo, "commit", "-m", "unconfirmed", check=False, env=commit_env())
    assert refused.returncode != 0 and "待确认标记 1" in refused.stdout + refused.stderr

    result = dc.confirm_project(str(repo / "0100_PLC自动化" / "DJ-TEST-001"))
    assert result.confirmed == 1
    git(repo, "add", IFC)
    assert git(repo, "commit", "-m", "confirmed", check=False, env=commit_env()).returncode == 0


def test_e3_an_unrelated_commit_is_not_touched_by_the_plc_gate(repo: Path) -> None:
    (repo / "notes.md").write_text("# 笔记\n", encoding="utf-8")
    git(repo, "add", "notes.md")
    accepted = git(repo, "commit", "-m", "notes", check=False, env=commit_env())
    assert accepted.returncode == 0 and "PLC" not in accepted.stdout + accepted.stderr
