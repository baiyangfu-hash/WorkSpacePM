"""commit-msg 认已批业务变更记录（BC）：离线人工改 PLC 程序不必每次开 CHG。"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from auto_pm.infrastructure.business_change_gate import (
    BusinessChangeError,
    find_bc_ids,
    find_bc_row,
)
from auto_pm.infrastructure.git_hook_enforcer import enforce_commit_msg

PID = "DJ-2099-001"
PROJECT = f"0100_PLC自动化/{PID}_测试线"
PROGRAM = f"{PROJECT}/02_PLC程序/PLC_ST"
RECORD = f"{PROJECT}/11_监控/01_变更管理/02_变更记录/02_业务变更记录.md"
MANIFEST = f"{PROJECT}/02_PLC程序/工程资产/safety_zone.yml"
IO_POINTS = f"{PROJECT}/02_PLC程序/工程资产/io_points.csv"

BC_TABLE = f"""# 业务变更记录 - {PID}

| 编号 | 提出日期 | 提出人 | 类型 | 改了什么（原来 → 改成） | 为什么 | 影响 | 批准人 | 批准日期 | 状态 | 关联 CHG / 提交 |
|---|---|---|---|---|---|---|---|---|---|---|
| BC-{PID}-001 | 待补 | 待补 | 硬件 | 换 PLC | 国产化 | 全部 | 待补 | 待补 | 待补（程序在写） | 待补 |
| BC-{PID}-002 | 2099-01-02 | 张工 | 参数 | 进料超时 10 s → 15 s | 现场 | FB_1001 | baiyang | 2099-01-02 | 已批 | 待补 |
| BC-{PID}-003 | 2099-01-03 | 张工 | 需求 | 外部交互层 | 现场 | FB_3001 | baiyang | 2099-01-03 | 已实施（未现场验证） | 待补 |
| BC-{PID}-004 | 2099-01-04 | 张工 | 参数 | 报警延时 | 现场 | FB_1001 | | | 待批 | |
| BC-{PID}-2099_01_001 | 2099-01-05 | 张工 | 参数 | 出料延时 1 s → 2 s | 现场 | FB_1001 | baiyang | 2099-01-05 | 已批 | |
| BC-{PID}-2099_01_002 | 2099-01-06 | 张工 | 参数 | 已取消的改动 | 现场 | FB_1001 | baiyang | 2099-01-06 | 已取消 | |
| BC-{PID}-005 | 2099-01-07 | 张工 | 参数 | 只写已批没写批准人 | 现场 | FB_1001 | 待补 | | 已批 | |
"""

STATION = """FUNCTION_BLOCK FB_1001_Station1
VAR
    tTimeout : TIME := T#10S;
    bEmergencyStop : BOOL;
END_VAR
// @安全区 开始：急停撤销命令
IF NOT bEmergencyStop THEN
    bMotorRun := FALSE;
END_IF;
// @安全区 结束
bMotorRun := bStart AND bReady;
tDelay := T#1S;
END_FUNCTION_BLOCK
"""

SAFETY_FB = "FUNCTION_BLOCK FB_1030_Safety\nbOut := bEmergencyStop;\nEND_FUNCTION_BLOCK\n"

ZONE = """project_id: DJ-2099-001
files:
  - 02_PLC程序/PLC_ST/00_安全/*.scl
variables:
  - bEmergencyStop
  - "*Interlock*"
points:
  - X140..X147
"""


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=True,
    ).stdout.strip()


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    _write(root, f"{PROJECT}/.copier-answers.yml",
           f"project_id: {PID}\nproject_name: test line\nstack: plc\n")
    _write(root, RECORD, BC_TABLE)
    _write(root, f"{PROJECT}/11_监控/01_变更管理/02_变更记录/01_版本变更台账.md",
           "# 版本变更台帐\n\n| 变更编号 | 状态 |\n| --- | --- |\n")
    _write(root, f"{PROGRAM}/02_工位1/FB_1001_Station1.scl", STATION)
    _write(root, f"{PROGRAM}/00_安全/FB_1030_Safety.scl", SAFETY_FB)
    _write(root, MANIFEST, ZONE)
    _write(root, IO_POINTS, "tag,address,安全\nDOOR_OK,%IX0.1,是\nLAMP,%QX0.0,否\n")
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test User")
    _git(root, "config", "core.quotepath", "false")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "baseline")
    return root


def _commit_msg(root: Path, message: str) -> int:
    msg = root / ".git" / "COMMIT_EDITMSG"
    msg.write_text(message, encoding="utf-8")
    return enforce_commit_msg(root, msg)


def _edit_station(root: Path, old: str, new: str) -> None:
    path = root / f"{PROGRAM}/02_工位1/FB_1001_Station1.scl"
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")
    _git(root, "add", "-A")


def test_bc_id_patterns_accept_old_and_month_numbers() -> None:
    message = (
        "fix: [BC-DJ-2026-009-004] [BC-DJ-2026-009-2026_10_001] "
        "BC-DJ-2026-009-2026_13_001 BC-DJ-2026-009-0041 xBC-DJ-2026-009-001 BC-DJ-2026-009-004"
    )
    assert find_bc_ids(message) == ("BC-DJ-2026-009-004", "BC-DJ-2026-009-2026_10_001")


def test_real_009_record_reads_the_approved_row() -> None:
    record = (
        Path(__file__).resolve().parents[6]
        / "0100_PLC自动化/DJ-2026-009_汇川换型改造/11_监控/01_变更管理/02_变更记录/02_业务变更记录.md"
    )
    if not record.is_file():
        pytest.skip("控制根以外的检出没有 009 项目")
    row = find_bc_row(record.read_text(encoding="utf-8"), "BC-DJ-2026-009-004")
    assert row["状态"].startswith("已批")
    with pytest.raises(BusinessChangeError, match="没有这一条"):
        find_bc_row(record.read_text(encoding="utf-8"), "BC-DJ-2026-009-099")


@pytest.mark.parametrize("bc", [f"BC-{PID}-002", f"BC-{PID}-003", f"BC-{PID}-2099_01_001"])
def test_approved_bc_replaces_chg_for_ordinary_plc_edit(repo: Path, bc: str) -> None:
    _edit_station(repo, "T#10S", "T#15S")
    assert _commit_msg(repo, f"fix(plc): [{bc}] 进料超时 10 s 改 15 s\n") == 0


def test_two_approved_bcs_of_the_project_pass(repo: Path) -> None:
    _edit_station(repo, "T#10S", "T#15S")
    assert _commit_msg(repo, f"fix: [BC-{PID}-002] [BC-{PID}-2099_01_001] 两处参数\n") == 0


@pytest.mark.parametrize(
    ("bc", "fragment"),
    [
        (f"BC-{PID}-001", "待补"),
        (f"BC-{PID}-004", "待批"),
        (f"BC-{PID}-2099_01_002", "已取消"),
        (f"BC-{PID}-005", "没写批准人"),
        (f"BC-{PID}-099", "没有这一条"),
        (f"BC-{PID}-2099_02_001", "没有这一条"),
        ("BC-DJ-2099-002-002", "属于项目 DJ-2099-002"),
    ],
)
def test_unapproved_missing_or_foreign_bc_is_rejected(
    repo: Path, capsys: pytest.CaptureFixture[str], bc: str, fragment: str
) -> None:
    _edit_station(repo, "T#10S", "T#15S")
    assert _commit_msg(repo, f"fix: [{bc}] 进料超时\n") == 1
    assert fragment in capsys.readouterr().out


def test_one_bad_bc_among_good_ones_rejects(repo: Path) -> None:
    _edit_station(repo, "T#10S", "T#15S")
    assert _commit_msg(repo, f"fix: [BC-{PID}-002] [BC-{PID}-004]\n") == 1


def test_no_bc_and_no_chg_still_rejected_with_bc_hint(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _edit_station(repo, "T#10S", "T#15S")
    assert _commit_msg(repo, "fix: 进料超时\n") == 1
    assert "业务变更编号" in capsys.readouterr().out


def test_bc_approved_only_in_working_tree_is_not_enough(repo: Path) -> None:
    """表里改成已批但没暂存：提交里的证据仍是待批，拒绝。"""
    _edit_station(repo, "T#10S", "T#15S")
    record = repo / RECORD
    record.write_text(
        record.read_text(encoding="utf-8").replace("| | | 待批 | |", "| baiyang | 2099-01-08 | 已批 | |"),
        encoding="utf-8",
    )
    assert _commit_msg(repo, f"fix: [BC-{PID}-004]\n") == 1
    _git(repo, "add", RECORD)
    assert _commit_msg(repo, f"fix: [BC-{PID}-004]\n") == 0


@pytest.mark.parametrize(
    ("old", "new", "fragment"),
    [
        ("bMotorRun := FALSE;", "bMotorRun := bHold;", "@安全区 区段"),
        ("// @安全区 结束\n", "", "@安全区 区段"),
        ("bMotorRun := bStart AND bReady;", "bMotorRun := bStart AND bEmergencyStop;", "bemergencystop"),
        ("bMotorRun := bStart AND bReady;", "bMotorRun := bStart AND bDoorInterlock;", "*interlock*"),
        ("bMotorRun := bStart AND bReady;", "bMotorRun := bStart AND X141;", "x141"),
        ("bMotorRun := bStart AND bReady;", "bMotorRun := bStart OR TRUE;\n// @安全区 开始", "@安全区"),
    ],
)
def test_safety_zone_edit_needs_chg(
    repo: Path, capsys: pytest.CaptureFixture[str], old: str, new: str, fragment: str
) -> None:
    _edit_station(repo, old, new)
    assert _commit_msg(repo, f"fix: [BC-{PID}-002]\n") == 1
    out = capsys.readouterr().out
    assert "安全区" in out and fragment in out


def test_file_listed_in_zone_needs_chg(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(repo, f"{PROGRAM}/00_安全/FB_1030_Safety.scl", SAFETY_FB + "// tweak\n")
    _git(repo, "add", "-A")
    assert _commit_msg(repo, f"fix: [BC-{PID}-002]\n") == 1
    assert "files" in capsys.readouterr().out


def test_shrinking_the_zone_in_the_same_commit_does_not_help(repo: Path) -> None:
    _write(repo, MANIFEST, "project_id: DJ-2099-001\n")
    _edit_station(repo, "bMotorRun := bStart AND bReady;", "bMotorRun := bEmergencyStop;")
    assert _commit_msg(repo, f"fix: [BC-{PID}-002]\n") == 1


def test_deleting_io_points_in_the_same_commit_does_not_hide_safety_points(repo: Path) -> None:
    """删除不进暂存清单（只看 ACM），所以安全点要和 HEAD 那份取并集。"""
    _git(repo, "rm", "-q", IO_POINTS)
    _edit_station(repo, "bMotorRun := bStart AND bReady;", "bMotorRun := bStart AND DOOR_OK;")
    assert _commit_msg(repo, f"fix: [BC-{PID}-002]\n") == 1


def test_io_point_marked_safe_counts(repo: Path) -> None:
    _edit_station(repo, "bMotorRun := bStart AND bReady;", "bMotorRun := bStart AND %IX0.1;")
    assert _commit_msg(repo, f"fix: [BC-{PID}-002]\n") == 1
    _git(repo, "reset", "-q", "--hard")
    _edit_station(repo, "bMotorRun := bStart AND bReady;", "bMotorRun := bStart AND %QX0.0;")
    assert _commit_msg(repo, f"fix: [BC-{PID}-002]\n") == 0


def test_bad_manifest_fails_closed(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _git(repo, "rm", "-q", "--cached", MANIFEST)
    (repo / MANIFEST).unlink()
    _git(repo, "commit", "-q", "-m", "drop zone")
    _write(repo, MANIFEST, "project_id: DJ-2099-001\nfile:\n  - x.scl\n")
    _git(repo, "add", MANIFEST)
    _git(repo, "commit", "-q", "-m", "typo zone")
    _edit_station(repo, "T#10S", "T#15S")
    assert _commit_msg(repo, f"fix: [BC-{PID}-002]\n") == 1
    assert "不认识的键" in capsys.readouterr().out


def test_project_without_zone_treats_all_plc_code_as_safety(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _git(repo, "rm", "-q", MANIFEST)
    _git(repo, "commit", "-q", "-m", "no zone yet")
    _edit_station(repo, "T#10S", "T#15S")
    assert _commit_msg(repo, f"fix: [BC-{PID}-002]\n") == 1
    assert "还没有安全区清单" in capsys.readouterr().out


@pytest.mark.parametrize("message", ["发版 V1.1", "release v1.1", "交付客户版本"])
def test_release_message_needs_chg(repo: Path, message: str) -> None:
    _edit_station(repo, "T#10S", "T#15S")
    assert _commit_msg(repo, f"fix: [BC-{PID}-002] {message}\n") == 1


def test_touching_version_ledger_needs_chg(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(repo, f"{PROJECT}/11_监控/01_变更管理/02_变更记录/01_版本变更台账.md", "# 改了\n")
    _edit_station(repo, "T#10S", "T#15S")
    assert _commit_msg(repo, f"fix: [BC-{PID}-002]\n") == 1
    assert "发版" in capsys.readouterr().out


def test_chg_in_message_keeps_the_chg_path(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """同时写 CHG 和 BC：照旧按 CHG 校验，BC 不能替不存在的 CHG 兜底。"""
    _edit_station(repo, "T#10S", "T#15S")
    assert _commit_msg(repo, f"fix: [CHG-PLC-2099-001] [BC-{PID}-002]\n") == 1
    assert "CHG/PID/台账" in capsys.readouterr().out


def test_project_without_bc_record_rejects(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _git(repo, "rm", "-q", RECORD)
    _git(repo, "commit", "-q", "-m", "no record")
    _edit_station(repo, "T#10S", "T#15S")
    assert _commit_msg(repo, f"fix: [BC-{PID}-002]\n") == 1
    assert "没有业务变更记录表" in capsys.readouterr().out
