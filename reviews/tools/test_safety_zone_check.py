"""Tests for safety_zone_check.py: each test builds a throw-away repository with a base and a PR head.

Run with:  python -m pytest reviews/tools/test_safety_zone_check.py -q -p no:cacheprovider -o addopts=
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import safety_zone_check as gate

ROOT = "0100_PLC自动化/DJ-TEST-001"
ST = f"{ROOT}/02_PLC程序/PLC_ST"
FEED = f"{ST}/01_送料/FB_Feed.scl"
ESTOP = f"{ST}/00_安全/FB_EStop.scl"
MANIFEST = f"{ROOT}/02_PLC程序/工程资产/safety_zone.yml"
IO = f"{ROOT}/02_PLC程序/工程资产/io_points.csv"
DOC = f"{ROOT}/02_PLC程序/程序文档/说明.md"
LIB = "0100_PLC自动化/01_SharedLibraries/SysLib/timer/FB_TON.scl"
USER = {"login": "baiyangfu-hash", "id": 246858089}

FEED_SRC = """FUNCTION_BLOCK FB_Feed
VAR_INPUT
    i_bSafetyOk : BOOL;
    i_bPart : BOOL;
END_VAR
VAR
    nTimeout : INT := 10;
END_VAR
// 送料
q_bRun := i_bPart AND NOT q_bDone;
nTimeout := 10;
// @安全区 开始：安全条件
q_bEnable := ESTOP_OK AND i_bSafetyOk;
// @安全区 结束
END_FUNCTION_BLOCK
"""
ESTOP_SRC = """FUNCTION_BLOCK FB_EStop
q_bChainOk := ESTOP_OK AND DOOR_OK;
END_FUNCTION_BLOCK
"""
MANIFEST_SRC = """project_id: DJ-TEST-001
files:
  - 02_PLC程序/PLC_ST/00_安全/*.scl
variables:
  - "*SafetyOk*"
points:
  - DOOR_OK
"""
IO_SRC = """station,signal_type,address,tag,signal_name,device,comment,安全
common,DI,I0.0,ESTOP_OK,急停回路正常,操作台,,是
common,DI,I0.1,PART_PRESENT,来料检测,输送,,否
"""


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "core.autocrlf=false",
         "-c", "core.quotepath=false", *args],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    return result.stdout.strip()


def write(repo: Path, rel: str, text: str | None) -> None:
    path = repo / rel
    if text is None:
        path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def make_repo(tmp_path: Path, marked: bool = True) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    files = {FEED: FEED_SRC, ESTOP: ESTOP_SRC, IO: IO_SRC, DOC: "说明\n", LIB: "FUNCTION_BLOCK FB_TON\nq := in;\nEND_FUNCTION_BLOCK\n"}
    if marked:
        files[MANIFEST] = MANIFEST_SRC
    for rel, text in files.items():
        write(root, rel, text)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    git(root, "checkout", "-q", "-b", "pr")
    return root


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path)


def commit(repo: Path, files: dict[str, str | None]) -> tuple[str, str]:
    for rel, text in files.items():
        write(repo, rel, text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "change")
    return git(repo, "rev-parse", "main"), git(repo, "rev-parse", "HEAD")


def sign(head: str, user: dict | None = None, app: dict | None = None, body: str | None = None) -> dict:
    return {
        "id": 1,
        "body": body if body is not None else f"安全签字 {head[:7]}\n已看仿真记录：急停全过",
        "user": user or USER,
        "performed_via_github_app": app,
    }


def edit_feed(old: str, new: str) -> str:
    assert old in FEED_SRC
    return FEED_SRC.replace(old, new)


def reasons(result: gate.Result) -> str:
    return "\n".join(r for rs in result.touched.values() for r in rs)


# ---------------------------------------------------------------- 认安全区


def test_t01_plain_logic_change_outside_the_zone_passes_without_signature(repo: Path) -> None:
    base, head = commit(repo, {FEED: edit_feed("nTimeout := 10;\n// @", "nTimeout := 15;\n// @")})
    result = gate.check(repo, base, head)
    assert not result.touched, reasons(result)
    assert result.passed


def test_t02_docs_only_change_is_not_a_plc_change(repo: Path) -> None:
    base, head = commit(repo, {DOC: "改了说明\n"})
    assert gate.check(repo, base, head).passed


def test_t03_line_inside_region_markers_needs_signature(repo: Path) -> None:
    base, head = commit(repo, {FEED: edit_feed("ESTOP_OK AND i_bSafetyOk", "ESTOP_OK AND i_bSafetyOk AND i_bPart")})
    result = gate.check(repo, base, head)
    assert "@安全区 区段" in reasons(result)
    assert not result.passed and not result.violations


def test_t04_removing_the_region_markers_still_counts_as_touching(repo: Path) -> None:
    text = FEED_SRC.replace("// @安全区 开始：安全条件\n", "").replace("// @安全区 结束\n", "")
    base, head = commit(repo, {FEED: text})
    assert "@安全区 区段" in reasons(gate.check(repo, base, head))


def test_t05_any_line_referencing_a_safety_variable_needs_signature(repo: Path) -> None:
    text = edit_feed("q_bRun := i_bPart AND NOT q_bDone;", "q_bRun := i_bPart AND NOT q_bDone AND io_st.i_bGlue_SafetyOk;")
    base, head = commit(repo, {FEED: text})
    assert "safetyok" in reasons(gate.check(repo, base, head)).lower()


def test_t06_io_points_safety_column_counts_by_tag_and_address(repo: Path) -> None:
    text = edit_feed("q_bRun := i_bPart AND NOT q_bDone;", "q_bRun := %I0.0 AND i_bPart;")
    base, head = commit(repo, {FEED: text})
    assert "i0.0" in reasons(gate.check(repo, base, head))


def test_t07_file_listed_in_manifest_needs_signature(repo: Path) -> None:
    base, head = commit(repo, {ESTOP: ESTOP_SRC + "// 只改注释\n"})
    assert "整个文件在安全区清单里" in reasons(gate.check(repo, base, head))


def test_t08_changing_the_manifest_itself_needs_signature(repo: Path) -> None:
    base, head = commit(repo, {MANIFEST: MANIFEST_SRC.replace('  - "*SafetyOk*"\n', "")})
    result = gate.check(repo, base, head)
    assert "改了安全区清单" in reasons(result)


def test_t09_unmarking_a_point_in_io_points_needs_signature(repo: Path) -> None:
    base, head = commit(repo, {IO: IO_SRC.replace("操作台,,是", "操作台,,否")})
    assert "ESTOP_OK".lower() in reasons(gate.check(repo, base, head))


def test_t10_unmarked_project_treats_every_plc_change_as_safety(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, marked=False)
    base, head = commit(repo, {FEED: edit_feed("nTimeout := 10;\n// @", "nTimeout := 15;\n// @")})
    assert "未标定" in reasons(gate.check(repo, base, head))


def test_t11_shared_library_without_manifest_counts_as_safety(repo: Path) -> None:
    base, head = commit(repo, {LIB: "FUNCTION_BLOCK FB_TON\nq := in AND en;\nEND_FUNCTION_BLOCK\n"})
    result = gate.check(repo, base, head)
    assert "0100_PLC自动化/01_SharedLibraries" in result.touched


def test_t12_head_manifest_cannot_shrink_the_zone(repo: Path) -> None:
    # 同一个 PR 里把变量移出清单、再改引用它的行：基线清单仍然算数
    text = edit_feed("q_bRun := i_bPart AND NOT q_bDone;", "q_bRun := i_bPart AND x_SafetyOk;")
    base, head = commit(repo, {MANIFEST: MANIFEST_SRC.replace('  - "*SafetyOk*"\n', ""), FEED: text})
    assert "SafetyOk".lower() in reasons(gate.check(repo, base, head)).lower()


# ---------------------------------------------------------------- 硬检查


def test_h01_or_true_bypass_fails_even_with_signature(repo: Path) -> None:
    base, head = commit(repo, {FEED: edit_feed("ESTOP_OK AND i_bSafetyOk", "ESTOP_OK AND (i_bSafetyOk OR TRUE)")})
    result = gate.check(repo, base, head, [sign(head)])
    assert result.signature is not None
    assert not result.passed
    assert any("恒真" in v for v in result.violations)


def test_h02_or_true_outside_the_zone_also_fails(repo: Path) -> None:
    base, head = commit(repo, {FEED: edit_feed("q_bRun := i_bPart AND NOT q_bDone;", "q_bRun := i_bPart OR TRUE;")})
    result = gate.check(repo, base, head)
    assert any("恒真" in v for v in result.violations)


@pytest.mark.parametrize("expr", ["1 OR i_bPart", "i_bPart AND FALSE", "FALSE AND i_bPart", "i_bPart or true"])
def test_h03_other_tautologies_fail(repo: Path, expr: str) -> None:
    base, head = commit(repo, {FEED: edit_feed("i_bPart AND NOT q_bDone", expr)})
    assert gate.check(repo, base, head).violations


@pytest.mark.parametrize("expr", ["i_bPart OR 16#1", "i_bPart OR TRUEVALUE", "i_bPart OR arr[1]", "n := 1;"])
def test_h04_lookalikes_are_not_tautologies(repo: Path, expr: str) -> None:
    base, head = commit(repo, {FEED: edit_feed("i_bPart AND NOT q_bDone", expr)})
    assert not gate.check(repo, base, head).violations


def test_h05_or_true_inside_comment_or_string_is_ignored(repo: Path) -> None:
    text = edit_feed("// 送料\n", "// 送料，严禁写 OR TRUE\nsMsg := 'x OR TRUE';\n")
    base, head = commit(repo, {FEED: text})
    assert not gate.check(repo, base, head).violations


def test_h06_existing_bypass_in_a_touched_file_blocks_the_pr(tmp_path: Path) -> None:
    # 和 DJ-2026-005 FB_1004:97 一样：旁路早就在基线上，PR 只要碰这个文件就必须一起去掉
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    write(repo, FEED, edit_feed("ESTOP_OK AND i_bSafetyOk", "ESTOP_OK AND (i_bSafetyOk OR TRUE) // 兼容常态有效"))
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    git(repo, "checkout", "-q", "-b", "pr")
    base, head = commit(repo, {FEED: (repo / FEED).read_text(encoding="utf-8").replace("nTimeout := 10;", "nTimeout := 12;")})
    assert any("恒真" in v and "第 13 行" in v for v in gate.check(repo, base, head).violations)


def test_h07_safety_point_forced_to_constant_fails(repo: Path) -> None:
    base, head = commit(repo, {FEED: edit_feed("// 送料\n", "// 送料\nESTOP_OK := TRUE;\n")})
    assert any("赋成常量" in v for v in gate.check(repo, base, head, [sign(head)]).violations)


def test_h08_commented_out_safety_code_fails(repo: Path) -> None:
    text = edit_feed("q_bEnable := ESTOP_OK AND i_bSafetyOk;", "q_bEnable := TRUE_FLAG;\n// q_bEnable := ESTOP_OK AND i_bSafetyOk;")
    base, head = commit(repo, {FEED: text})
    assert any("注释掉" in v for v in gate.check(repo, base, head).violations)


def test_h09_unbalanced_markers_in_head_fail(repo: Path) -> None:
    base, head = commit(repo, {FEED: FEED_SRC.replace("// @安全区 结束\n", "")})
    assert any("不成对" in v for v in gate.check(repo, base, head).violations)


def test_h10_missing_safety_point_fails(repo: Path) -> None:
    # 和 DJ-2026-005 漏移植急停一样：DOOR_OK 是安全点，程序里一处都没读
    base, head = commit(repo, {ESTOP: "FUNCTION_BLOCK FB_EStop\nq_bChainOk := ESTOP_OK;\nEND_FUNCTION_BLOCK\n"})
    result = gate.check(repo, base, head, [sign(head)])
    assert any("漏引用" in v and "DOOR_OK" in v for v in result.violations)


def test_h11_declaration_alone_does_not_count_as_reading_a_point(repo: Path) -> None:
    text = "VAR_GLOBAL\n    DOOR_OK AT %I0.2 : BOOL;\nEND_VAR\n"
    base, head = commit(repo, {ESTOP: "FUNCTION_BLOCK FB_EStop\nq := ESTOP_OK;\nEND_FUNCTION_BLOCK\n", f"{ST}/G.db": text})
    assert any("DOOR_OK" in v for v in gate.check(repo, base, head).violations)


def test_h12_range_points_are_expanded_octal_for_mitsubishi() -> None:
    assert gate.expand("X140..X147") == [f"X14{n}" for n in range(8)]
    assert gate.expand("X6..X11") == ["X6", "X7", "X10", "X11"]
    assert gate.expand("M10..M12") == ["M10", "M11", "M12"]


def test_h13_unknown_manifest_key_fails_closed(repo: Path) -> None:
    base, head = commit(repo, {MANIFEST: MANIFEST_SRC.replace("variables:", "variabels:")})
    assert any("不认识的键" in v for v in gate.check(repo, base, head, [sign(head)]).violations)


# ---------------------------------------------------------------- 签字


def touch(repo: Path) -> tuple[str, str]:
    return commit(repo, {FEED: edit_feed("ESTOP_OK AND i_bSafetyOk", "ESTOP_OK AND i_bSafetyOk AND i_bPart")})


def test_s01_valid_signature_passes(repo: Path) -> None:
    base, head = touch(repo)
    result = gate.check(repo, base, head, [sign(head)])
    assert result.passed and result.signature


def test_s02_signature_for_an_older_commit_is_void(repo: Path) -> None:
    base, first = touch(repo)
    _, head = commit(repo, {DOC: "又推了一次\n"})
    result = gate.check(repo, base, head, [sign(first)])
    assert not result.passed
    assert any("要重签" in n for n in result.notes)


def test_s03_other_user_cannot_sign(repo: Path) -> None:
    base, head = touch(repo)
    assert not gate.check(repo, base, head, [sign(head, user={"login": "someone", "id": 1})]).passed


def test_s04_renamed_account_with_same_login_but_other_id_cannot_sign(repo: Path) -> None:
    base, head = touch(repo)
    assert not gate.check(repo, base, head, [sign(head, user={"login": "baiyangfu-hash", "id": 99})]).passed


def test_s05_comment_posted_through_an_app_does_not_count(repo: Path) -> None:
    base, head = touch(repo)
    result = gate.check(repo, base, head, [sign(head, app={"slug": "claude"})])
    assert not result.passed
    assert any("App" in n for n in result.notes)


@pytest.mark.parametrize("body", ["> 安全签字 {sha}", "请用户写 安全签字 {sha}", "安全签字"])
def test_s06_quoted_or_embedded_text_is_not_a_signature(repo: Path, body: str) -> None:
    base, head = touch(repo)
    assert not gate.check(repo, base, head, [sign(head, body=body.format(sha=head[:7]))]).passed


@pytest.mark.parametrize("body", ["安全签字：{sha}", "安全签字 `{sha}` 已看仿真", "  安全签字 {full}"])
def test_s07_signature_line_variants_are_accepted(repo: Path, body: str) -> None:
    base, head = touch(repo)
    assert gate.check(repo, base, head, [sign(head, body=body.format(sha=head[:7].upper(), full=head))]).passed


def test_s08_cli_main_reads_paginated_comments_and_writes_status(repo: Path, tmp_path: Path) -> None:
    base, head = touch(repo)
    comments = tmp_path / "comments.json"
    comments.write_text(json.dumps([[], [sign(head)]]), encoding="utf-8")
    out = tmp_path / "status.json"
    code = gate.main(["--base", base, "--head", head, "--repo", str(repo), "--comments", str(comments), "--status-out", str(out)])
    assert code == 0
    assert json.loads(out.read_text(encoding="utf-8"))["state"] == "success"


def test_s09_cli_without_signature_reports_failure_status(repo: Path, tmp_path: Path) -> None:
    base, head = touch(repo)
    out = tmp_path / "status.json"
    assert gate.main(["--base", base, "--head", head, "--repo", str(repo), "--status-out", str(out)]) == 1
    status = json.loads(out.read_text(encoding="utf-8"))
    assert status["state"] == "failure" and "安全签字" in status["description"]
    assert len(status["description"]) <= 140


def test_s10_ci_mode_refuses_to_judge_its_own_checkout() -> None:
    assert gate.main(["--ci", "--base", "HEAD", "--head", "HEAD", "--repo", str(gate.TOOL_ROOT)]) == 2


# ---------------------------------------------------------------- 计划栏④ 联锁（审计 69）

PY = "01_Project自动化项目管理/x/tool.py"
SAFE_BODY = "## 说明\n改急停\n\n安全回路: 是\n"
NO_BODY = "## 说明\n只改送料\n\n安全回路: 否\n"


def test_p01_plan_yes_needs_signature_even_without_touching_the_zone(repo: Path) -> None:
    base, head = commit(repo, {DOC: "改了说明\n"})
    result = gate.check(repo, base, head, plan="是")
    assert not result.passed and not result.violations
    assert gate.PLAN_KEY in result.touched
    assert gate.check(repo, base, head, [sign(head)], plan="是").passed


def test_p02_plan_yes_locks_a_pr_that_touches_no_plc_file_at_all(repo: Path) -> None:
    base, head = commit(repo, {PY: "print(1)\n"})
    assert gate.check(repo, base, head).passed  # 反例：没填计划栏时这个 PR 不要签字
    result = gate.check(repo, base, head, plan="是")
    assert not result.passed
    assert gate.status(result) == ("failure", "计划填了涉及安全回路：等用户在 PR 上评论“安全签字 <头提交号>”")


def test_p03_plan_no_but_listed_safety_file_changed_is_a_mismatch(repo: Path) -> None:
    base, head = commit(repo, {ESTOP: ESTOP_SRC + "// 只改注释\n"})
    result = gate.check(repo, base, head, plan="否")
    assert result.plan_mismatch and not result.passed
    assert "计划与改动不一致" in "\n".join(result.touched[gate.PLAN_KEY])
    assert gate.status(result)[1].startswith("计划填“否”却碰了安全区")
    assert gate.check(repo, base, head, [sign(head)], plan="否").passed


@pytest.mark.parametrize(
    "files",
    [
        {FEED: edit_feed("ESTOP_OK AND i_bSafetyOk", "ESTOP_OK AND i_bSafetyOk AND i_bPart")},  # 区段
        {FEED: edit_feed("q_bRun := i_bPart AND NOT q_bDone;", "q_bRun := %I0.0 AND i_bPart;")},  # 安全点
        {MANIFEST: MANIFEST_SRC + "  - EXTRA_OK\n"},  # 清单本身
    ],
)
def test_p04_plan_no_mismatch_covers_every_way_of_touching_the_zone(repo: Path, files: dict) -> None:
    base, head = commit(repo, files)
    assert gate.check(repo, base, head, plan="否").plan_mismatch


def test_p05_plan_no_on_an_unmarked_project_is_a_mismatch(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, marked=False)
    base, head = commit(repo, {FEED: edit_feed("nTimeout := 10;\n// @", "nTimeout := 15;\n// @")})
    assert gate.check(repo, base, head, plan="否").plan_mismatch


def test_p06_plan_no_and_zone_untouched_passes(repo: Path) -> None:
    base, head = commit(repo, {FEED: edit_feed("nTimeout := 10;\n// @", "nTimeout := 15;\n// @")})
    result = gate.check(repo, base, head, plan="否")
    assert result.passed and not result.plan_mismatch and not result.touched


def test_p07_no_plan_line_keeps_the_old_behaviour(repo: Path) -> None:
    base, head = touch(repo)
    result = gate.check(repo, base, head)
    assert not result.passed and not result.plan_mismatch and gate.PLAN_KEY not in result.touched


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (SAFE_BODY, "是"),
        (NO_BODY, "否"),
        ("安全回路：否", "否"),
        ("**安全回路**：是", "是"),
        ("④是否涉及安全回路: 是", "是"),
        ("安全回路: `否`", "否"),
        ("安全回路: 否\n安全回路：否", "否"),
        ("> 安全回路: 是", None),
        ("本卡不涉及安全回路: 是", None),
        ("- 安全回路说明见附件", None),
        ("", None),
        (None, None),
    ],
)
def test_p08_plan_line_variants(body: str | None, expected: str | None) -> None:
    value, problems = gate.plan_declaration(body)
    assert (value, problems) == (expected, [])


@pytest.mark.parametrize(
    ("body", "word"),
    [("安全回路: 不确定", "只能写 是 或 否"), ("安全回路:", "只能写 是 或 否"), ("安全回路: 是\n安全回路: 否", "不一致")],
)
def test_p09_bad_plan_line_is_a_hard_failure_even_with_signature(repo: Path, tmp_path: Path, body: str, word: str) -> None:
    value, problems = gate.plan_declaration(body)
    assert value is None and word in problems[0]
    base, head = touch(repo)
    comments = tmp_path / "c.json"
    comments.write_text(json.dumps([sign(head)]), encoding="utf-8")
    body_file = tmp_path / "body.txt"
    body_file.write_text(body, encoding="utf-8")
    out = tmp_path / "status.json"
    args = ["--base", base, "--head", head, "--repo", str(repo), "--comments", str(comments),
            "--pr-body-file", str(body_file), "--status-out", str(out)]
    assert gate.main(args) == 1
    assert json.loads(out.read_text(encoding="utf-8"))["state"] == "failure"


def test_p10_cli_reads_the_plan_from_the_pr_body_file(repo: Path, tmp_path: Path) -> None:
    base, head = commit(repo, {DOC: "改了说明\n"})
    body_file = tmp_path / "body.txt"
    out = tmp_path / "status.json"
    args = ["--base", base, "--head", head, "--repo", str(repo), "--pr-body-file", str(body_file), "--status-out", str(out)]
    body_file.write_text(NO_BODY, encoding="utf-8")
    assert gate.main(args) == 0
    body_file.write_text(SAFE_BODY, encoding="utf-8")
    assert gate.main(args) == 1
    status = json.loads(out.read_text(encoding="utf-8"))
    assert status["state"] == "failure" and "安全回路" in status["description"]
    assert len(status["description"]) <= 140


def test_p11_ci_mode_refuses_the_local_only_options(repo: Path, tmp_path: Path, capsys) -> None:
    base, head = commit(repo, {DOC: "改了说明\n"})
    ci = ["--ci", "--base", base, "--head", head, "--repo", str(repo)]
    assert gate.main(ci) == 0  # 反例：同样的参数不带本机选项能跑通，下面的 2 只能来自这道保护
    for extra in (["--decision", DEC], ["--pr", "1"]):
        capsys.readouterr()
        assert gate.main([*ci, *extra]) == 2
        assert "CI 里读不到本机账本" in capsys.readouterr().err
    assert gate.main(["--repo", str(repo)]) == 2  # 既没 --pr 也没 --base/--head


@pytest.mark.parametrize("body", ["", "## 说明\n只改文档\n", "```\n安全回路: 否\n```\n"])
def test_p12_plc_change_without_a_plan_line_fails(repo: Path, tmp_path: Path, body: str) -> None:
    base, head = commit(repo, {DOC: "改了说明\n"})  # 只改 PLC 目录下的文档，也要写
    body_file = tmp_path / "body.txt"
    body_file.write_text(body, encoding="utf-8")
    args = ["--base", base, "--head", head, "--repo", str(repo), "--pr-body-file", str(body_file)]
    assert gate.main(args) == 1
    body_file.write_text(body + NO_BODY, encoding="utf-8")
    assert gate.main(args) == 0


def test_p13_non_plc_pr_without_a_plan_line_still_passes(repo: Path, tmp_path: Path) -> None:
    base, head = commit(repo, {PY: "print(1)\n"})
    body_file = tmp_path / "body.txt"
    body_file.write_text("## 说明\n", encoding="utf-8")
    assert gate.main(["--base", base, "--head", head, "--repo", str(repo), "--pr-body-file", str(body_file)]) == 0


def test_p14_fenced_example_is_not_a_declaration() -> None:
    assert gate.plan_declaration("示例：\n```\n安全回路: 否\n```\n安全回路: 是\n") == ("是", [])
    assert gate.plan_declaration("~~~\n安全回路: 不确定\n~~~\n") == (None, [])


# ---------------------------------------------------------------- 本机：批准记录 vs PR 描述

DEC = "DEC-20261022-5AFE0001"


def write_decision(root: Path, safety: str | None, decision_id: str = DEC) -> Path:
    """用 SW-2026-008 自己的契约（DecisionPackageDTO、PlanChecklist）写一份批准记录，字段形状与 pm 批准时一致。"""

    for entry in (gate.SW008_ROOT / "auto_pm", gate.SW008_ROOT):
        if str(entry) not in sys.path:
            sys.path.insert(0, str(entry))
    from auto_pm.contracts.decision_package import DecisionPackageDTO
    from auto_pm.contracts.plan_checklist import AcceptanceCheck, PlanChecklist

    grant: dict = {"adapter": "manual", "approved_model": "manual", "required_worktree_mode": "isolated",
                   "declared_dirty_paths": ["a.py"]}
    if safety is not None:
        checklist = PlanChecklist(original_request="改急停", safety_circuit=safety if safety in ("是", "否") else "",
                                  acceptance_checks=(AcceptanceCheck(command="pytest", expected_exit_code=0),),
                                  rollback="git revert")
        grant["plan_checklist"] = checklist.model_dump(mode="json")
        grant["plan_checklist"]["safety_circuit"] = safety  # 坏值测试直接写进文件
    decision = DecisionPackageDTO(
        decision_id=decision_id, project_id="DJ-TEST-001", change_id="CHG-PLC-2026-001", approved_scope="LOCAL",
        approver="baiyang", approved_at="2026-10-22T00:00:00+00:00",
        metadata={"planning_approval": {"schema_version": "planning-approval.v2", "execution_grant": grant}},
    )
    path = root / ".auto-pm" / "decisions" / f"{decision_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(decision.to_dict(), ensure_ascii=False), encoding="utf-8")
    return root




@pytest.mark.parametrize(("safety", "expected"), [("是", "是"), ("否", "否"), (None, None)])
def test_d01_reads_the_safety_field_from_a_real_decision_file(tmp_path: Path, safety: str | None, expected: str | None) -> None:
    pytest.importorskip("pydantic")
    root = write_decision(tmp_path / "control", safety)
    assert gate.decision_safety(root, DEC) == expected


def test_d02_unreadable_or_bad_decision_never_passes(tmp_path: Path) -> None:
    pytest.importorskip("pydantic")
    root = tmp_path / "control"
    root.mkdir()
    with pytest.raises(gate.DecisionReadError):
        gate.decision_safety(root, DEC)  # 没有这个文件
    write_decision(root, "也许")
    with pytest.raises(gate.DecisionReadError, match="只认"):
        gate.decision_safety(root, DEC)
    with pytest.raises(gate.DecisionReadError):
        gate.decision_safety(root, "../DEC-20261022-5AFE0001")  # 不规范的编号


@pytest.mark.parametrize(
    ("recorded", "declared", "plan", "problem", "note"),
    [
        ("是", "是", "是", False, False),
        ("是", "否", "是", True, False),
        ("是", None, "是", True, False),
        ("否", "否", "否", False, False),
        ("否", "是", "是", False, True),
        ("否", None, "否", False, True),
        (None, "是", "是", False, True),
        (None, None, None, False, True),
    ],
)
def test_d03_reconcile_takes_the_stricter_side(recorded, declared, plan, problem, note) -> None:
    got_plan, problems, notes = gate.reconcile(recorded, declared, DEC)
    assert (got_plan, bool(problems), bool(notes)) == (plan, problem, note)


def test_d04_cli_recorded_yes_with_body_no_fails_even_with_signature(repo: Path, tmp_path: Path) -> None:
    pytest.importorskip("pydantic")
    root = write_decision(tmp_path / "control", "是")
    base, head = commit(repo, {DOC: "改了说明\n"})
    body_file = tmp_path / "body.txt"
    body_file.write_text(NO_BODY, encoding="utf-8")
    comments = tmp_path / "c.json"
    comments.write_text(json.dumps([sign(head)]), encoding="utf-8")
    args = ["--base", base, "--head", head, "--repo", str(repo), "--pr-body-file", str(body_file),
            "--comments", str(comments), "--decision", DEC, "--control-root", str(root)]
    assert gate.main(args) == 1  # 描述与批准记录不一致：签字也放不行，先改描述
    body_file.write_text(SAFE_BODY, encoding="utf-8")
    assert gate.main(args) == 0
    comments.write_text("[]", encoding="utf-8")
    assert gate.main(args) == 1  # 描述对上了，但还没签字


def test_d05_cli_recorded_no_but_zone_touched_is_a_mismatch(repo: Path, tmp_path: Path, capsys) -> None:
    pytest.importorskip("pydantic")
    root = write_decision(tmp_path / "control", "否")
    base, head = commit(repo, {ESTOP: ESTOP_SRC + "// 只改注释\n"})
    body_file = tmp_path / "body.txt"
    body_file.write_text(NO_BODY, encoding="utf-8")
    args = ["--base", base, "--head", head, "--repo", str(repo), "--pr-body-file", str(body_file),
            "--decision", DEC, "--control-root", str(root)]
    assert gate.main(args) == 1
    out = capsys.readouterr().out
    assert f"批准记录 {DEC}填了“否”" in out and "计划与改动不一致" in out


def test_d06_cli_missing_decision_is_an_error_not_a_pass(repo: Path, tmp_path: Path) -> None:
    pytest.importorskip("pydantic")
    base, head = commit(repo, {DOC: "改了说明\n"})
    args = ["--base", base, "--head", head, "--repo", str(repo), "--decision", DEC, "--control-root", str(tmp_path)]
    assert gate.main(args) == 2


def test_w01_the_workflow_judges_with_the_base_branch_as_it_is_now_not_a_stale_base_sha() -> None:
    # same fault as pr-gate (#69): base.sha only moves when the head is pushed, so it can name an old main and an old judge
    yaml = pytest.importorskip("yaml")
    workflow = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "safety-gate.yml"
    steps = yaml.safe_load(workflow.read_text(encoding="utf-8"))["jobs"]["safety"]["steps"]
    checkout = next(s for s in steps if s.get("uses", "").startswith("actions/checkout"))
    assert checkout["with"]["ref"] == "${{ steps.pr.outputs.base_ref }}"
    assert all("base.sha" not in str(step) and "base_sha" not in str(step) for step in steps)
    check = next(s.get("run", "") for s in steps if "safety_zone_check.py" in s.get("run", ""))
    assert '--base "$(git -C "$GITHUB_WORKSPACE" rev-parse HEAD)"' in check
