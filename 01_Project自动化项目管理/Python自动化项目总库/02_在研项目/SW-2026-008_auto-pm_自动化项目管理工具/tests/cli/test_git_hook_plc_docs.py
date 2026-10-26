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


def add_revision_note(doc: Path) -> None:
    """Give the accepting commit a real change of its own.

    Restoring a document to its committed text leaves nothing to commit on Linux. On Windows the commit only went through because
    ``build`` writes CRLF and the tests write LF, so the line endings were the whole diff.
    """
    doc.write_text(doc.read_text(encoding="utf-8") + "\n修订说明：已与代码核对一致。\n", encoding="utf-8", newline="\n")


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
    add_revision_note(doc)
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
    add_revision_note(doc)
    git(repo, "add", IFC)
    assert git(repo, "commit", "-m", "confirmed", check=False, env=commit_env()).returncode == 0


def test_e3_an_unrelated_commit_is_not_touched_by_the_plc_gate(repo: Path) -> None:
    (repo / "notes.md").write_text("# 笔记\n", encoding="utf-8")
    git(repo, "add", "notes.md")
    accepted = git(repo, "commit", "-m", "notes", check=False, env=commit_env())
    assert accepted.returncode == 0 and "PLC" not in accepted.stdout + accepted.stderr


F01A_PROJECT = "0100_PLC自动化/DJ-TEST-001"
F01A_MARKER = f"{F01A_PROJECT}/.plc.json"
F01A_MOVE_HINT = "移动或退役请走 F01-b 的授权"


def _f01a_cli_scene(tmp_path: Path, *, wrong_type: bool = False) -> Path:
    from tests.plc.test_doc_consistency import IFC_DOC

    root = tmp_path / "f01a-cli-repo"
    root.mkdir()
    git(root, "init", "-q")
    ifc = IFC_DOC.replace("| `i_bStart` | BOOL |", "| `i_bStart` | INT |") if wrong_type else IFC_DOC
    project = build(root / "0100_PLC自动化", ifc=ifc)
    (project / ".plc.json").write_text('{"name": "DJ-TEST-001", "version": "V1.0.0", "description": "t"}', encoding="utf-8", errors="replace")
    (root / "main.py").write_text(LAUNCHER, encoding="utf-8", errors="replace")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "pre-existing PLC history")
    installed = CliRunner().invoke(cli, ["-w", str(root), "git-hook", "install"])
    assert installed.exit_code == 0, installed.output
    (root / ".git" / "hooks" / "commit-msg").unlink()
    (root / ".git" / "hooks" / "pre-commit").chmod(0o755)
    return root


@pytest.mark.parametrize("wrong_type", [False, True])
def test_f01a_e04_real_precommit_refuses_a_pure_marker_deletion_then_accepts_a_real_repair(
    tmp_path: Path, wrong_type: bool
) -> None:
    root = _f01a_cli_scene(tmp_path, wrong_type=wrong_type)
    head = git(root, "rev-parse", "HEAD").stdout.strip()
    marker_before = (root / F01A_MARKER).read_bytes()
    document_before = (root / IFC).read_bytes()
    git(root, "rm", "--", F01A_MARKER)
    assert git(root, "diff", "--cached", "--diff-filter=ACM", "--name-only").stdout == ""
    staged_before = git(root, "diff", "--cached", "--binary", "--no-renames").stdout

    refused = git(root, "commit", "-m", "remove PLC identity", check=False, env=commit_env())

    assert refused.returncode != 0
    assert F01A_MOVE_HINT in refused.stdout + refused.stderr
    assert git(root, "rev-parse", "HEAD").stdout.strip() == head
    assert git(root, "diff", "--cached", "--binary", "--no-renames").stdout == staged_before
    assert (root / IFC).read_bytes() == document_before
    assert not (root / F01A_MARKER).exists()

    (root / F01A_MARKER).write_bytes(marker_before)
    git(root, "add", "--", F01A_MARKER)
    if wrong_type:
        document = root / IFC
        document.write_text(document.read_text(encoding="utf-8", errors="replace").replace("| `i_bStart` | INT |", "| `i_bStart` | BOOL |"), encoding="utf-8", errors="replace", newline="\n")
        git(root, "add", "--", IFC)
    (root / "repair-note.md").write_text("# F01-a identity retained\n", encoding="utf-8", errors="replace")
    git(root, "add", "--", "repair-note.md")
    accepted = git(root, "commit", "-m", "retain PLC identity and consistent documents", check=False, env=commit_env())
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    assert git(root, "rev-parse", "HEAD").stdout.strip() != head
    assert (root / F01A_MARKER).read_bytes() == marker_before


@pytest.mark.parametrize("move", ["marker_only", "whole_project", "into_archive"])
def test_f01a_e05_real_precommit_refuses_marker_and_whole_project_moves(tmp_path: Path, move: str) -> None:
    root = _f01a_cli_scene(tmp_path)
    head = git(root, "rev-parse", "HEAD").stdout.strip()
    if move == "marker_only":
        git(root, "mv", "--", F01A_MARKER, f"{F01A_PROJECT}/retired-marker.json")
    elif move == "whole_project":
        git(root, "mv", "--", F01A_PROJECT, "0100_PLC自动化/DJ-MOVED-001")
    else:
        (root / "0100_PLC自动化" / "_archive").mkdir()
        git(root, "mv", "--", F01A_PROJECT, "0100_PLC自动化/_archive/DJ-TEST-001")
    staged_before = git(root, "diff", "--cached", "--binary", "--no-renames").stdout

    refused = git(root, "commit", "-m", "move PLC identity", check=False, env=commit_env())

    assert refused.returncode != 0
    assert F01A_MOVE_HINT in refused.stdout + refused.stderr
    assert git(root, "rev-parse", "HEAD").stdout.strip() == head
    assert git(root, "diff", "--cached", "--binary", "--no-renames").stdout == staged_before


@pytest.mark.parametrize("corruption", ["malformed_head", "missing_commit_object"])
def test_f01a_e06_real_precommit_cli_fails_closed_when_git_head_is_corrupt(tmp_path: Path, corruption: str) -> None:
    root = _f01a_cli_scene(tmp_path)
    head_path = root / ".git" / "HEAD"
    if corruption == "malformed_head":
        corrupt_path = head_path
        corrupt_text = "not-a-valid-git-head\n"
    else:
        reference = git(root, "symbolic-ref", "HEAD").stdout.strip()
        corrupt_path = root / ".git" / reference
        corrupt_text = "0" * len(git(root, "rev-parse", "HEAD").stdout.strip()) + "\n"
    corrupt_path.write_text(corrupt_text, encoding="utf-8", errors="replace")
    head_before = head_path.read_bytes()
    corrupt_before = corrupt_path.read_bytes()
    index_before = (root / ".git" / "index").read_bytes()

    refused = subprocess.run(
        [sys.executable, str(root / "main.py"), "-w", str(root), "git-hook", "pre-commit"],
        cwd=root, env=commit_env(), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60, check=False,
    )

    assert refused.returncode != 0
    assert "Git" in refused.stdout + refused.stderr
    assert head_path.read_bytes() == head_before
    assert corrupt_path.read_bytes() == corrupt_before
    assert (root / ".git" / "index").read_bytes() == index_before
    assert (root / F01A_MARKER).is_file()


PUMP_SCL = "0100_PLC自动化/DJ-TEST-001/02_PLC程序/PLC_ST/01_泵/FB_Pump.scl"


def test_td046_a_deleted_scl_or_document_now_triggers_the_plc_document_check(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """以前纯删除的提交不在暂存快照里，PLC 文档核对根本不跑。核对规则本身对“文档还写着已删代码”只警告不拦，没有改。"""
    from auto_pm.infrastructure.git_hook_enforcer import get_staged_snapshot
    from auto_pm.infrastructure.plc_doc_hook import enforce_plc_docs

    for target in (PUMP_SCL, IFC):
        git(repo, "rm", "-q", "--", target)
        snapshot = get_staged_snapshot(repo)
        assert snapshot.paths == (target,)
        capsys.readouterr()
        assert enforce_plc_docs(repo, snapshot.paths) == 0
        assert "正在核对暂存的 PLC 项目" in capsys.readouterr().out
        git(repo, "reset", "-q", "--", target)
        git(repo, "checkout", "-q", "--", target)


def test_td046_deleting_only_the_interface_document_reports_it_missing(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from auto_pm.infrastructure.git_hook_enforcer import get_staged_snapshot
    from auto_pm.infrastructure.plc_doc_hook import enforce_plc_docs

    git(repo, "rm", "-q", "--", IFC)
    capsys.readouterr()
    enforce_plc_docs(repo, get_staged_snapshot(repo).paths)
    assert "缺少接口文档" in capsys.readouterr().out
