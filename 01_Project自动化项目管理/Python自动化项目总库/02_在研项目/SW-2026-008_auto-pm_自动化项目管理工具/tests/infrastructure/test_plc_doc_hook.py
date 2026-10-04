"""Real-repository proofs for the PLC document/code consistency gate of the pre-commit hook (V01D)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from auto_pm.plc import doc_consistency as dc

from auto_pm.infrastructure import git_hook_enforcer, plc_doc_hook
from tests.plc.test_doc_consistency import IFC_DOC, VAR_DOC, build

PLC_ROOT = "0100_PLC自动化/DJ-TEST-001"
SCL = f"{PLC_ROOT}/02_PLC程序/PLC_ST/01_泵/FB_Pump.scl"
IFC = f"{PLC_ROOT}/02_PLC程序/PLC_ST/01_泵/PRD/接口文档_IFC-FB_Pump.md"
VAR = f"{PLC_ROOT}/02_PLC程序/程序文档/{dc.VAR_DOC_NAME}"


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=tester", "-c", "user.email=t@example.test", "-c", "core.autocrlf=false",
         "-c", "core.quotepath=false", *args],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    return result.stdout


def read(repo: Path, rel: str) -> str:
    return (repo / rel).read_text(encoding="utf-8")


def write(repo: Path, rel: str, text: str) -> None:
    (repo / rel).write_text(text, encoding="utf-8", newline="\n")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    project = build(root / "0100_PLC自动化")
    (project / ".plc.json").write_text('{"name": "DJ-TEST-001", "version": "V1.0.0", "description": "t"}', encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "baseline")
    return root


def run_hook(repo: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    capsys.readouterr()
    code = plc_doc_hook.enforce_plc_docs(repo, git_hook_enforcer.get_staged_snapshot(repo).paths)
    return code, capsys.readouterr().out


def test_h01_a_consistent_change_passes(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(repo, SCL, read(repo, SCL).replace("// 启动命令", "// 启动按钮命令"))
    write(repo, IFC, read(repo, IFC).replace("| 启动命令 |", "| 启动按钮命令 |"))
    git(repo, "add", SCL, IFC)
    code, output = run_hook(repo, capsys)
    assert code == 0 and "校验通过" in output and "物理阻断" not in output


def test_h02_a_code_change_without_documentation_blocks_names_the_variable_and_fills_the_document(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(repo, SCL, read(repo, SCL).replace("    i_bStart : BOOL; // 启动命令\n", "    i_bStart : BOOL; // 启动命令\n    i_bNew : BOOL; // 新增信号\n"))
    git(repo, "add", SCL)
    scl_before = (repo / SCL).read_bytes()
    index_before = git(repo, "diff", "--cached")

    code, output = run_hook(repo, capsys)

    assert code == 1
    assert "FB_Pump.i_bNew" in output and "物理阻断" in output and "已按代码在工作区补全文档" in output
    assert f"{dc.MARKER}新增信号" in read(repo, IFC)
    assert (repo / SCL).read_bytes() == scl_before
    assert git(repo, "diff", "--cached") == index_before


def test_h03_the_staged_content_decides_not_the_working_tree(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    broken = read(repo, IFC).replace("| `i_bStart` | BOOL |", "| `i_bStart` | INT |")
    write(repo, IFC, broken)
    git(repo, "add", IFC)
    write(repo, IFC, read(repo, IFC).replace("| `i_bStart` | INT |", "| `i_bStart` | BOOL |"))  # fixed, but not staged
    code, output = run_hook(repo, capsys)
    assert code == 1 and "FB_Pump.i_bStart" in output and "类型不同" in output
    git(repo, "add", IFC)
    assert run_hook(repo, capsys)[0] == 0
    write(repo, IFC, read(repo, IFC).replace("| `i_bStart` | BOOL |", "| `i_bStart` | DINT |"))  # broken in the working tree only
    assert run_hook(repo, capsys)[0] == 0


def test_h04_staged_unconfirmed_markers_block_until_they_are_confirmed(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(repo, IFC, read(repo, IFC).replace("| 启动命令 |", f"| {dc.MARKER}启动命令 |"))
    git(repo, "add", IFC)
    code, output = run_hook(repo, capsys)
    assert code == 1 and "待确认标记 1" in output and "i_bStart" in output and "plc docs confirm" in output
    assert dc.MARKER in read(repo, IFC)  # nothing auto-filled when only markers remain
    dc.confirm_project(str(repo / PLC_ROOT))
    git(repo, "add", IFC)
    assert run_hook(repo, capsys)[0] == 0


def test_h05_a_commit_without_plc_files_never_looks_at_plc_projects(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(_path: str) -> object:
        raise AssertionError("PLC analysis must not run for this commit")

    monkeypatch.setattr(dc, "analyze_project", forbidden)
    write(repo, "notes.md", "# 笔记\n")
    write(repo, "tool.py", "print('x')\n")
    git(repo, "add", "notes.md", "tool.py")
    code, output = run_hook(repo, capsys)
    assert code == 0 and output == ""


def test_h06_only_the_projects_touched_by_the_commit_are_checked(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    other = build(repo / "0100_PLC自动化" / "other", ifc=IFC_DOC.replace("启动命令", "完全不同的说明"), var=VAR_DOC)
    (other / ".plc.json").write_text('{"name": "DJ-TEST-002", "version": "V1.0.0", "description": "t"}', encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "second project, inconsistent")
    write(repo, SCL, read(repo, SCL).replace("// 启动命令", "// 启动按钮命令"))
    write(repo, IFC, read(repo, IFC).replace("| 启动命令 |", "| 启动按钮命令 |"))
    git(repo, "add", SCL, IFC)
    code, output = run_hook(repo, capsys)
    assert code == 0 and "DJ-TEST-002" not in output and "other" not in output


def test_h07_removing_a_documented_variable_from_the_code_blocks(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(repo, SCL, read(repo, SCL).replace("    q_bRunning : BOOL; // 运行中\n", ""))
    git(repo, "add", SCL)
    code, output = run_hook(repo, capsys)
    assert code == 1 and "FB_Pump.q_bRunning" in output and "文档里有、代码里没有" in output


def test_h08_a_failing_check_refuses_the_commit(repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_path: str) -> object:
        raise RuntimeError("解析器崩溃")

    monkeypatch.setattr(dc, "analyze_project", boom)
    write(repo, SCL, read(repo, SCL).replace("// 启动命令", "// 启动按钮命令"))
    git(repo, "add", SCL)
    code, output = run_hook(repo, capsys)
    assert code == 1 and "检查异常" in output and "解析器崩溃" in output


def test_h09_a_missing_document_only_warns(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    git(repo, "rm", "-q", IFC)
    write(repo, SCL, read(repo, SCL).replace("// 启动命令", "// 启动按钮命令"))
    git(repo, "add", SCL)
    code, output = run_hook(repo, capsys)
    assert code == 0 and "缺少接口文档" in output and "plc docs sync" in output


def test_h10_a_new_project_added_in_the_commit_is_checked_too(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "fresh"
    root.mkdir()
    git(root, "init", "-q")
    write(root, "README.md", "# r\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    project = build(root / "0100_PLC自动化", ifc=IFC_DOC.replace("运行中", "别的说明"))
    (project / ".plc.json").write_text('{"name": "DJ-TEST-001", "version": "V1.0.0", "description": "t"}', encoding="utf-8")
    git(root, "add", "-A")
    code, output = run_hook(root, capsys)
    assert code == 1 and "FB_Pump.q_bRunning" in output and "注释" in output


def test_h11_a_documentation_only_commit_is_checked(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(repo, VAR, read(repo, VAR).replace("| i_bEnable | BOOL | 使能 |", "| i_bEnable | BOOL | 乱写的说明 |"))
    git(repo, "add", VAR)
    code, output = run_hook(repo, capsys)
    assert code == 1 and "ST_PumpCfg.i_bEnable" in output


def test_h12_enforce_pre_commit_runs_both_checks_and_fails_when_either_fails(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger_calls: list[int] = []

    def ledger(*_args: object, **_kwargs: object) -> int:
        ledger_calls.append(1)
        return ledger_code[0]

    ledger_code = [0]
    monkeypatch.setattr(git_hook_enforcer, "_enforce_ledger_pre_commit", ledger)
    write(repo, SCL, read(repo, SCL).replace("// 启动命令", "// 启动按钮命令"))  # code only: the document now differs
    git(repo, "add", SCL)
    capsys.readouterr()
    assert git_hook_enforcer.enforce_pre_commit(repo) == 1  # PLC part fails, ledger part passes
    write(repo, IFC, read(repo, IFC).replace("| 启动命令 |", "| 启动按钮命令 |"))
    git(repo, "add", IFC)
    assert git_hook_enforcer.enforce_pre_commit(repo) == 0
    ledger_code[0] = 1
    assert git_hook_enforcer.enforce_pre_commit(repo) == 1  # ledger part fails, PLC part passes
    assert len(ledger_calls) == 3  # the ledger check is never skipped


def test_h13_a_data_block_change_without_documentation_blocks_and_is_documented_in_the_working_tree(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = f"{PLC_ROOT}/02_PLC程序/PLC_ST/00_全局数据/GlobalVars.db"
    write(repo, db, read(repo, db).replace("    stCfg : ST_PumpCfg; // 泵配置\n", "    stCfg : ST_PumpCfg; // 泵配置\n    bNew : BOOL; // 新增标志\n"))
    git(repo, "add", db)
    code, output = run_hook(repo, capsys)
    assert code == 1 and "GlobalVars.bNew" in output
    assert f"{dc.MARKER}新增标志" in read(repo, VAR)


def test_h14_other_files_inside_a_plc_project_do_not_trigger_the_check(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(_path: str) -> object:
        raise AssertionError("PLC analysis must not run for this commit")

    monkeypatch.setattr(dc, "analyze_project", forbidden)
    write(repo, f"{PLC_ROOT}/README.md", "# 项目说明\n")
    write(repo, f"{PLC_ROOT}/notes.txt", "笔记\n")
    git(repo, "add", f"{PLC_ROOT}/README.md", f"{PLC_ROOT}/notes.txt")
    code, output = run_hook(repo, capsys)
    assert code == 0 and output == ""


def test_h15_a_project_inside_an_archive_folder_is_not_checked(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    old = build(repo / "0100_PLC自动化" / "_archive", ifc=IFC_DOC.replace("启动命令", "完全不同的说明"), var=VAR_DOC)
    (old / ".plc.json").write_text('{"name": "DJ-OLD", "version": "V1.0.0", "description": "t"}', encoding="utf-8")
    git(repo, "add", "-A")
    code, output = run_hook(repo, capsys)
    assert code == 0 and output == ""
