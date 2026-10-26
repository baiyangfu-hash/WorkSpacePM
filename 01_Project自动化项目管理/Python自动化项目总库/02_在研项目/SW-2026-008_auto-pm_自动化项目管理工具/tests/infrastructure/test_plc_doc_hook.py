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


F01A_MARKER = f"{PLC_ROOT}/.plc.json"
F01A_MOVE_HINT = "移动或退役请走 F01-b 的授权"


def test_f01a_h16_marker_deletion_blocks_and_the_snapshot_records_the_deletion(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    head = git(repo, "rev-parse", "HEAD")
    source_before = (repo / SCL).read_bytes()
    document_before = (repo / IFC).read_bytes()
    git(repo, "rm", "--", F01A_MARKER)
    assert git_hook_enforcer.get_staged_snapshot(repo).paths == (F01A_MARKER,)  # TD-046：纯删除也在快照里
    staged_before = git(repo, "diff", "--cached", "--binary", "--no-renames")

    code, output = run_hook(repo, capsys)

    assert code == 1 and F01A_MOVE_HINT in output and F01A_MARKER in output
    assert git(repo, "rev-parse", "HEAD") == head
    assert git(repo, "diff", "--cached", "--binary", "--no-renames") == staged_before
    assert (repo / SCL).read_bytes() == source_before
    assert (repo / IFC).read_bytes() == document_before
    assert not (repo / F01A_MARKER).exists()


def test_f01a_h17_deleting_the_marker_does_not_hide_a_wrong_ifc_type(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(repo, IFC, read(repo, IFC).replace("| `i_bStart` | BOOL |", "| `i_bStart` | INT |"))
    git(repo, "add", IFC)
    git(repo, "rm", "--", F01A_MARKER)
    document_before = (repo / IFC).read_bytes()
    staged_before = git(repo, "diff", "--cached", "--binary")

    code, output = run_hook(repo, capsys)

    assert code == 1 and F01A_MOVE_HINT in output
    assert "| `i_bStart` | INT |" in read(repo, IFC)
    assert (repo / IFC).read_bytes() == document_before
    assert git(repo, "diff", "--cached", "--binary") == staged_before
    assert not (repo / F01A_MARKER).exists()


def test_f01a_h18_an_unstaged_marker_restore_does_not_override_the_index_deletion(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    marker_bytes = (repo / F01A_MARKER).read_bytes()
    git(repo, "rm", "--", F01A_MARKER)
    (repo / F01A_MARKER).write_bytes(marker_bytes)
    assert git_hook_enforcer.get_staged_snapshot(repo).paths == (F01A_MARKER,)

    code, output = run_hook(repo, capsys)

    assert code == 1 and F01A_MOVE_HINT in output
    assert (repo / F01A_MARKER).read_bytes() == marker_bytes
    assert git(repo, "ls-files", "--", F01A_MARKER) == ""
    git(repo, "add", "--", F01A_MARKER)
    assert run_hook(repo, capsys) == (0, "")


@pytest.mark.parametrize("move", ["marker_only", "whole_project", "into_archive"])
def test_f01a_h19_marker_and_project_moves_require_f01b_authorization(
    repo: Path, capsys: pytest.CaptureFixture[str], move: str
) -> None:
    head = git(repo, "rev-parse", "HEAD")
    if move == "marker_only":
        git(repo, "mv", "--", F01A_MARKER, f"{PLC_ROOT}/retired-marker.json")
    elif move == "whole_project":
        git(repo, "mv", "--", PLC_ROOT, "0100_PLC自动化/DJ-MOVED-001")
    else:
        (repo / "0100_PLC自动化" / "_archive").mkdir()
        git(repo, "mv", "--", PLC_ROOT, "0100_PLC自动化/_archive/DJ-TEST-001")
    staged_before = git(repo, "diff", "--cached", "--binary", "--no-renames")

    code, output = run_hook(repo, capsys)

    assert code == 1 and F01A_MOVE_HINT in output and F01A_MARKER in output
    assert git(repo, "rev-parse", "HEAD") == head
    assert git(repo, "diff", "--cached", "--binary", "--no-renames") == staged_before


def test_f01a_h20_an_archive_marker_already_in_head_cannot_be_deleted(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old = build(repo / "0100_PLC自动化" / "_archive", ifc=IFC_DOC, var=VAR_DOC)
    (old / ".plc.json").write_text('{"name": "DJ-OLD", "version": "V1.0.0", "description": "t"}', encoding="utf-8", errors="replace")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "existing archived project")
    marker = (old / ".plc.json").relative_to(repo).as_posix()
    git(repo, "rm", "--", marker)
    assert git_hook_enforcer.get_staged_snapshot(repo).paths == (marker,)

    code, output = run_hook(repo, capsys)

    assert code == 1 and F01A_MOVE_HINT in output and marker in output


@pytest.mark.parametrize("wrong_type", [False, True])
def test_f01a_h21_an_unborn_repository_checks_its_new_plc_project(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], wrong_type: bool
) -> None:
    from auto_pm.infrastructure.plc_git_marker_guard import removed_index_markers

    root = tmp_path / "unborn"
    root.mkdir()
    git(root, "init", "-q")
    ifc = IFC_DOC.replace("| `i_bStart` | BOOL |", "| `i_bStart` | INT |") if wrong_type else IFC_DOC
    project = build(root / "0100_PLC自动化", ifc=ifc, var=VAR_DOC)
    (project / ".plc.json").write_text('{"name": "DJ-TEST-001", "version": "V1.0.0", "description": "t"}', encoding="utf-8", errors="replace")
    git(root, "add", "-A")
    assert removed_index_markers(root) == ()

    code, output = run_hook(root, capsys)

    assert code == (1 if wrong_type else 0), output
    expected_message = "FB_Pump.i_bStart" if wrong_type else "校验通过"
    assert expected_message in output


@pytest.mark.parametrize("corruption", ["malformed_head", "missing_commit_object"])
def test_f01a_h22_a_corrupt_head_is_a_read_failure_not_an_unborn_repository(
    repo: Path, capsys: pytest.CaptureFixture[str], corruption: str
) -> None:
    from auto_pm.infrastructure.plc_git_marker_guard import (
        GitMarkerGuardError,
        removed_index_markers,
    )

    head_path = repo / ".git" / "HEAD"
    if corruption == "malformed_head":
        corrupt_path = head_path
        corrupt_text = "not-a-valid-git-head\n"
    else:
        reference = git(repo, "symbolic-ref", "HEAD").strip()
        corrupt_path = repo / ".git" / reference
        corrupt_text = "0" * len(git(repo, "rev-parse", "HEAD").strip()) + "\n"
    corrupt_path.write_text(corrupt_text, encoding="utf-8", errors="replace")
    head_before = head_path.read_bytes()
    corrupt_before = corrupt_path.read_bytes()
    index_before = (repo / ".git" / "index").read_bytes()
    with pytest.raises(GitMarkerGuardError):
        removed_index_markers(repo)
    capsys.readouterr()

    code = plc_doc_hook.enforce_plc_docs(repo, ())

    assert code == 1
    assert head_path.read_bytes() == head_before
    assert corrupt_path.read_bytes() == corrupt_before
    assert (repo / ".git" / "index").read_bytes() == index_before
    assert (repo / F01A_MARKER).is_file()


def test_f01a_h23_a_git_permission_failure_is_not_an_empty_marker_set(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from auto_pm.infrastructure.plc_git_marker_guard import (
        GitMarkerGuardError,
        removed_index_markers,
    )

    def denied(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise PermissionError("F01-a test Git read denied")

    index_before = (repo / ".git" / "index").read_bytes()
    marker_before = (repo / F01A_MARKER).read_bytes()
    monkeypatch.setattr("auto_pm.infrastructure.plc_git_marker_guard.subprocess.run", denied)

    with pytest.raises(GitMarkerGuardError):
        removed_index_markers(repo)
    assert plc_doc_hook.enforce_plc_docs(repo, ()) == 1
    assert (repo / ".git" / "index").read_bytes() == index_before
    assert (repo / F01A_MARKER).read_bytes() == marker_before


def test_f01a_h24_a_verified_non_git_workspace_keeps_the_old_contract(tmp_path: Path) -> None:
    from auto_pm.infrastructure.plc_git_marker_guard import removed_index_markers

    assert plc_doc_hook.enforce_plc_docs(tmp_path, ()) == 0
    assert removed_index_markers(tmp_path) == ()


def test_h30_auto_fill_only_completes_the_objects_that_blocked_the_commit(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """TD-SW008-045：被拒的是 FB_Pump，就只补 FB_Pump 的文档，同工程里没文档的 FB_Fan 不被顺手新建。"""
    fan_scl = f"{PLC_ROOT}/02_PLC程序/PLC_ST/01_泵/FB_Fan.scl"
    fan_doc = repo / PLC_ROOT / "02_PLC程序/PLC_ST/01_泵/PRD/接口文档_IFC-FB_Fan.md"
    write(repo, fan_scl, "FUNCTION_BLOCK FB_Fan\nVAR_INPUT\n    i_bOn : BOOL; // 开\nEND_VAR\nEND_FUNCTION_BLOCK\n")
    write(repo, SCL, read(repo, SCL).replace("    i_bStart : BOOL; // 启动命令\n", "    i_bStart : BOOL; // 启动命令\n    i_bNew : BOOL; // 新增信号\n"))
    git(repo, "add", SCL, fan_scl)
    code, output = run_hook(repo, capsys)
    assert code == 1 and "FB_Pump.i_bNew" in output
    assert f"{dc.MARKER}新增信号" in read(repo, IFC)
    assert not fan_doc.exists()

