"""run_plugin_test.py（替身计时器版插件 test）按项目传参数的用例。

用一个假的 siemens-lsp（shell 脚本）顶替真插件，只验证脚本的搭建动作：在临时副本里换上替身计时器、
工作目录是该项目的 PLC_ST 副本、仓库里的文件哈希前后一致、不带 --project 时仍是 DJ-2026-005。
这不运行真实的 .scltest，真插件要在装了 Siemens 语言服务插件的笔记本上跑。

运行：python -B -m pytest reviews/tools/test_run_plugin_test.py -q（Windows 上跳过：假插件是 shell 脚本）
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "0100_PLC自动化" / "DJ-2026-005" / "05_测试与验证" / "测试用SysLib" / "run_plugin_test.py"

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="假插件是 shell 脚本")


@pytest.fixture()
def fake_lsp(tmp_path: Path) -> Path:
    """假插件：把 test 时的工作目录和 SysLib 里的 FB_TON 是不是替身写到 report.txt，退出码 0。"""
    report = tmp_path / "report.txt"
    lsp = tmp_path / "fake-siemens-lsp"
    lsp.write_text(
        "#!/bin/sh\n"
        f'echo "args=$*" > "{report}"\n'
        f'echo "cwd=$(pwd)" >> "{report}"\n'
        f'if grep -q Counter ../../../01_SharedLibraries/SysLib/timer/FB_TON.scl; then echo stub=yes >> "{report}"; else echo stub=no >> "{report}"; fi\n'
        f'if grep -q Counter ../../../01_SharedLibraries/SysLib/timer/FB_TONR.scl; then echo stubr=yes >> "{report}"; else echo stubr=no >> "{report}"; fi\n'
        f'echo "libscl=$(cd ../../../01_SharedLibraries/SysLib && find . -name \'*.scl\' | sed \'s|^./||\' | sort | tr \'\\n\' \',\')" >> "{report}"\n'
        r"n=$(cat $(find . -name '*.scltest') | sed 's|//.*||' | grep -c '^[[:space:]]*TEST_CASE')" + "\n"
        'echo "siemens-lsp test: running $n/$n cases from 1 file(s)"\n'
        'printf "ok  \\tplc-autogen/runtime\\t0.1s\\n"\n'
        "exit 0\n",
        encoding="utf-8",
    )
    lsp.chmod(0o755)
    return lsp


def _script(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return path


def _run(lsp: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "--lsp", str(lsp), *extra],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )


def _report(lsp: Path) -> dict[str, str]:
    lines = (lsp.parent / "report.txt").read_text(encoding="utf-8").splitlines()
    return dict(line.split("=", 1) for line in lines)


def test_without_project_it_still_runs_dj_2026_005_in_a_copy_with_the_stub_timers(fake_lsp: Path) -> None:
    result = _run(fake_lsp)

    assert result.returncode == 0, result.stdout + result.stderr
    report = _report(fake_lsp)
    assert "DJ-2026-005" in report["cwd"] and report["cwd"].endswith("PLC_ST")
    assert report["args"] == "test ."
    assert report["stub"] == "yes" and report["stubr"] == "yes"
    assert "仓库未被改动" in result.stdout


def test_project_code_picks_the_dj_2026_009_directory_and_leaves_the_repo_untouched(fake_lsp: Path) -> None:
    result = _run(fake_lsp, "--project", "DJ-2026-009")

    assert result.returncode == 0, result.stdout + result.stderr
    report = _report(fake_lsp)
    assert "DJ-2026-009_" in report["cwd"] and report["cwd"].endswith("PLC_ST")
    assert report["stub"] == "yes" and report["stubr"] == "yes"
    assert "仓库未被改动" in result.stdout
    real_ton = REPO / "0100_PLC自动化" / "01_SharedLibraries" / "SysLib" / "timer" / "FB_TON.scl"
    assert "Counter" not in real_ton.read_text(encoding="utf-8")


def test_an_unknown_project_is_refused_with_the_reason(fake_lsp: Path) -> None:
    result = _run(fake_lsp, "--project", "DJ-2099-999")

    assert result.returncode != 0
    assert "找不到唯一的项目目录: DJ-2099-999" in result.stdout + result.stderr
    assert not (fake_lsp.parent / "report.txt").exists()


def test_the_default_project_is_unchanged() -> None:
    spec = importlib.util.spec_from_file_location("run_plugin_test_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.resolve_project(None).name == "DJ-2026-005"
    assert module.resolve_project("DJ-2026-005").name == "DJ-2026-005"


def _guarded(project: str | None) -> set[Path]:
    spec = importlib.util.spec_from_file_location("run_plugin_test_guard", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return set(module._guarded_files(module.resolve_project(project)))


def _guard_list_entries() -> list[tuple[str | None, str]]:
    """(项目, 保护清单里必须有的路径，相对 0100_PLC自动化)：删掉任何一项，对应的用例就变红。"""
    p009 = "DJ-2026-009_汇川换型改造"
    timers = ["01_SharedLibraries/SysLib/timer/FB_TON.scl", "01_SharedLibraries/SysLib/timer/FB_TONR.scl"]
    return (
        [("DJ-2026-009", f"{p009}/.plc.json"), ("DJ-2026-009", f"{p009}/02_PLC程序/PLC_ST/.plc.json")]
        + [("DJ-2026-009", t) for t in timers]
        + [(None, "DJ-2026-005/.plc.json")]
        + [(None, t) for t in timers]
    )


@pytest.mark.parametrize(("project", "relative"), _guard_list_entries())
def test_the_hash_guard_list_covers_every_file_the_run_could_touch(project: str | None, relative: str) -> None:
    """运行前后要核对哈希的文件清单：项目根和 PLC_ST 的 .plc.json、替身要顶替的两个计时器都在里面。"""
    expected = (REPO / "0100_PLC自动化" / relative).resolve()

    assert expected in {p.resolve() for p in _guarded(project)}


def test_the_hash_guard_list_also_covers_the_plc_source_files_of_the_chosen_project() -> None:
    guarded = {p.resolve() for p in _guarded("DJ-2026-009")}
    plc_dir = next((REPO / "0100_PLC自动化").glob("DJ-2026-009*")) / "02_PLC程序" / "PLC_ST"
    sources = {p.resolve() for p in plc_dir.rglob("*.scl")}

    assert sources and sources <= guarded


def _module():
    spec = importlib.util.spec_from_file_location("run_plugin_test_deps", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _lib(tmp_path: Path) -> Path:
    lib = tmp_path / "SysLib"
    for rel, text in {
        "a/FB_A.scl": "FUNCTION_BLOCK FB_A\nVAR\n s_t : FB_B;\nEND_VAR\n",
        "b/FB_B.scl": "FUNCTION_BLOCK FB_B\nVAR\n s_x : ST_C;\nEND_VAR\n",
        "c/ST_C.scl": "TYPE ST_C :\nSTRUCT\n i : INT;\nEND_STRUCT\nEND_TYPE\n",
        "d/FB_UNUSED.scl": "FUNCTION_BLOCK FB_UNUSED\nEND_FUNCTION_BLOCK\n",
        "e/FB_ONLY_IN_COMMENT.scl": "FUNCTION_BLOCK FB_ONLY_IN_COMMENT\nEND_FUNCTION_BLOCK\n",
    }.items():
        (lib / rel).parent.mkdir(parents=True, exist_ok=True)
        (lib / rel).write_text(text, encoding="utf-8")
    return lib


def test_the_dependency_chain_is_followed_and_unreferenced_blocks_are_left_out(tmp_path: Path) -> None:
    lib = _lib(tmp_path)
    source = tmp_path / "prog.scl"
    source.write_text(
        "FUNCTION_BLOCK FB_P\nVAR\n s_a : fb_a;\nEND_VAR\n"
        "// FB_ONLY_IN_COMMENT 只在注释里\n(* FB_UNUSED 也只在注释里 *)\n",
        encoding="utf-8",
    )

    needed = _module().referenced_syslib_files([source], lib)

    assert {p.name for p in needed} == {"FB_A.scl", "FB_B.scl", "ST_C.scl"}


def test_a_project_that_references_nothing_pulls_in_no_library_block(tmp_path: Path) -> None:
    source = tmp_path / "prog.scl"
    source.write_text("FUNCTION_BLOCK FB_P\nEND_FUNCTION_BLOCK\n", encoding="utf-8")

    assert _module().referenced_syslib_files([source], _lib(tmp_path)) == set()


def test_the_copy_for_dj_2026_009_has_only_the_referenced_syslib_blocks(fake_lsp: Path) -> None:
    result = _run(fake_lsp, "--project", "DJ-2026-009")

    assert result.returncode == 0, result.stdout + result.stderr
    copied = set(_report(fake_lsp)["libscl"].strip(",").split(","))
    assert "timer/FB_TON.scl" in copied and "timer/FB_TONR.scl" in copied
    assert not any(name.startswith("safety/") for name in copied)
    all_lib = {p.relative_to(REPO / "0100_PLC自动化" / "01_SharedLibraries" / "SysLib").as_posix()
               for p in (REPO / "0100_PLC自动化" / "01_SharedLibraries" / "SysLib").rglob("*.scl")}
    assert copied < all_lib


def test_the_copy_for_the_default_project_keeps_what_dj_2026_005_uses(fake_lsp: Path) -> None:
    result = _run(fake_lsp)

    assert result.returncode == 0, result.stdout + result.stderr
    copied = set(_report(fake_lsp)["libscl"].strip(",").split(","))
    assert {"timer/FB_TON.scl", "timer/FB_TONR.scl", "edge/FB_R_TRIG.scl", "edge/FB_F_TRIG.scl", "types/ST_ServoAxis.scl"} <= copied


# 三份真实插件输出 (主执行笔记本, 2026-10-26): 失败 / 全过 / 005 全过
RUN8_FAIL = (
    "siemens-lsp test: running 34/34 cases from 5 file(s)\n"
    "--- FAIL: TestUserCase029_TCMB04RcvIdShortStopAtZero (0.00s)\n"
    "    user_tests_autogen_test.go:7949: ASSERT failed at Test/modbus_client_test.scltest:103:5 step 21: got=ABC op== expected=ABC\n"
    "FAIL\nFAIL\tplc-autogen/runtime\t0.778s\nFAIL\n"
)
RUN9_OK_009 = "siemens-lsp test: running 34/34 cases from 5 file(s)\nok  \tplc-autogen/runtime\t0.633s\n"
AUDIT293_OK_005 = "siemens-lsp test: running 61/61 cases from 3 file(s)\nok  \tplc-autogen/runtime\t0.974s\n"


def test_real_logs_all_green_pass_the_false_green_check_when_the_count_matches() -> None:
    check = _module().false_green_problems

    assert check(RUN9_OK_009, 34) == []
    assert check(AUDIT293_OK_005, 61) == []


def test_a_count_that_differs_from_the_project_is_a_problem_even_when_the_plugin_says_ok() -> None:
    check = _module().false_green_problems

    assert any("不相等" in p for p in check(RUN9_OK_009, 35))
    assert any("不相等" in p for p in check("siemens-lsp test: running 30/34 cases from 5 file(s)\nok  \tplc-autogen/runtime\t1s\n", 34))
    assert any("不相等" in p for p in check("siemens-lsp test: running 34/30 cases from 5 file(s)\nok  \tplc-autogen/runtime\t1s\n", 34))


def test_a_log_without_the_count_line_or_the_ok_line_is_a_problem() -> None:
    check = _module().false_green_problems

    assert any("running N/M" in p for p in check("ok  \tplc-autogen/runtime\t1s\n", 34))
    assert any("ok  plc-autogen" in p for p in check("siemens-lsp test: running 34/34 cases from 5 file(s)\n", 34))
    assert check("", 34)


@pytest.mark.parametrize("marker", ["--- FAIL: TestX (0.00s)", "[build failed]", "invalid .scltest semantics"])
def test_any_failure_marker_is_a_problem_even_with_the_count_and_ok_line(marker: str) -> None:
    problems = _module().false_green_problems(RUN9_OK_009 + marker + "\n", 34)

    assert any(marker.split(":")[0] in p for p in problems)


def test_the_real_failing_log_is_a_problem() -> None:
    assert _module().false_green_problems(RUN8_FAIL, 34)


def test_test_case_count_ignores_commented_lines(tmp_path: Path) -> None:
    (tmp_path / "Test").mkdir()
    (tmp_path / "Test" / "a.scltest").write_text(
        '// TEST_CASE "commented out"\nTEST_CASE "one"\nEND_TEST_CASE\n  TEST_CASE "two"\nEND_TEST_CASE\n', encoding="utf-8"
    )

    assert _module().count_test_cases(tmp_path) == 2


def test_a_silent_plugin_with_exit_0_is_judged_failed(tmp_path: Path) -> None:
    result = _run(_script(tmp_path, "silent-lsp", "exit 0\n"))

    assert result.returncode == 1, result.stdout + result.stderr
    assert "防假绿" in result.stderr


def test_a_plugin_that_ran_fewer_cases_than_the_project_has_is_judged_failed(tmp_path: Path) -> None:
    lsp = _script(tmp_path, "short-lsp", 'echo "siemens-lsp test: running 1/1 cases from 1 file(s)"\nprintf "ok  \\tplc-autogen/runtime\\t1s\\n"\nexit 0\n')

    result = _run(lsp)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "不相等" in result.stderr


def test_a_failing_plugin_keeps_its_own_exit_code(tmp_path: Path) -> None:
    lsp = _script(tmp_path, "failing-lsp", 'echo "--- FAIL: TestX"\nexit 7\n')

    assert _run(lsp).returncode == 7
