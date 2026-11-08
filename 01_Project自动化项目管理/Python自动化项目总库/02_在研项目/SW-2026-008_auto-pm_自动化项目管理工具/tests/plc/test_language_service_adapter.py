"""Siemens 语言服务适配器（插件命令行 siemens-lsp）的单元测试（M3-PLUGIN）。

只用伪造的运行器与伪造的扩展目录：不依赖本机是否装了插件，也不启动真实命令行。
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

from auto_pm.domain.plc.language_service import LanguageServiceBinary
from auto_pm.infrastructure import siemens_language_service as sls

BINARY = LanguageServiceBinary(path="siemens-lsp.exe", version="9.9.9", sha256="0" * 64)


def _runner(
    returncode: int, stdout: str = "", stderr: str = "", seen: list[dict[str, Any]] | None = None
) -> Callable[[list[str], Path, Mapping[str, str], int], subprocess.CompletedProcess[str]]:
    def run(args: list[str], cwd: Path, env: Mapping[str, str], timeout: int) -> subprocess.CompletedProcess[str]:
        if seen is not None:
            seen.append({"args": args, "cwd": cwd, "env": dict(env), "timeout": timeout})
        return subprocess.CompletedProcess(args, returncode, stdout, stderr)

    return run


def _fake_extension(home: Path, version: str, platform_dir: str = "windows-amd64", exe: str = "siemens-lsp.exe") -> Path:
    binary = home / ".vscode" / "extensions" / f"{sls.EXTENSION_PREFIX}{version}" / "out" / "go" / platform_dir / exe
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"fake-binary-" + version.encode())
    return binary


def test_ls01_no_extension_directory_means_unavailable(tmp_path: Path) -> None:
    assert sls.locate_binary(env={}, home=tmp_path, platform="win32") is None
    service = sls.SiemensLanguageService(None)
    assert service.available is False
    result = service.check(tmp_path)
    assert result.available is False and result.exit_code is None and result.passed is False


def test_ls02_the_highest_installed_version_wins(tmp_path: Path) -> None:
    _fake_extension(tmp_path, "2.9.0")
    newest = _fake_extension(tmp_path, "2.17.2")
    _fake_extension(tmp_path, "2.10.1")
    found = sls.locate_binary(env={}, home=tmp_path, platform="win32")
    assert found is not None and found.path == str(newest) and found.version == "2.17.2"
    assert len(found.sha256) == 64


def test_ls03_the_platform_selects_the_matching_binary(tmp_path: Path) -> None:
    _fake_extension(tmp_path, "2.17.2", "windows-amd64", "siemens-lsp.exe")
    linux = _fake_extension(tmp_path, "2.17.2", "linux-amd64", "siemens-lsp")
    assert sls.locate_binary(env={}, home=tmp_path, platform="linux").path == str(linux)  # type: ignore[union-attr]
    assert sls.locate_binary(env={}, home=tmp_path, platform="freebsd") is None


def test_ls04_the_environment_variable_overrides_discovery(tmp_path: Path) -> None:
    _fake_extension(tmp_path, "2.17.2")
    explicit = tmp_path / "custom-lsp.exe"
    explicit.write_bytes(b"x")
    found = sls.locate_binary(env={sls.ENV_BINARY: str(explicit)}, home=tmp_path, platform="win32")
    assert found is not None and found.path == str(explicit)
    assert sls.locate_binary(env={sls.ENV_BINARY: str(tmp_path / "missing.exe")}, home=tmp_path, platform="win32") is None


def test_ls05_exit_zero_without_errors_passes_and_runs_in_the_project_root(tmp_path: Path) -> None:
    seen: list[dict[str, Any]] = []
    service = sls.SiemensLanguageService(BINARY, runner=_runner(0, "check metrics: files analyzed 10, diagnostics 0\n", seen=seen))
    result = service.check(tmp_path)
    assert result.passed and result.error_count == 0 and result.exit_code == 0
    assert seen[0]["args"] == ["siemens-lsp.exe", "check", "."] and seen[0]["cwd"] == tmp_path
    scratch = seen[0]["env"]["TEMP"]
    assert scratch and not Path(scratch).exists()  # the scratch folder for the kept test output is removed again


def test_ls06_error_lines_are_counted_and_made_relative_to_the_root(tmp_path: Path) -> None:
    out = f"{tmp_path}{chr(92)}02_PLC{chr(92)}FB.scl:49:5: ERROR: unexpected token\n{tmp_path}{chr(92)}02_PLC{chr(92)}OB1.scl:15:5: ERROR: undeclared symbol\ncheck metrics: errors: 2\n"
    result = sls.SiemensLanguageService(BINARY, runner=_runner(1, out)).check(tmp_path)
    assert not result.passed and result.error_count == 2 and result.exit_code == 1
    assert all(str(tmp_path) not in m for m in result.messages)


def test_ls07_a_non_zero_exit_without_parsed_diagnostics_is_still_a_failure(tmp_path: Path) -> None:
    result = sls.SiemensLanguageService(BINARY, runner=_runner(2, "", "fatal: cannot resolve library\n")).check(tmp_path)
    assert not result.passed and result.error_count == 1 and "cannot resolve library" in " ".join(result.messages)


def test_ls08_exit_zero_with_error_lines_is_not_a_pass(tmp_path: Path) -> None:
    result = sls.SiemensLanguageService(BINARY, runner=_runner(0, "x.scl:1:1: ERROR: boom\n")).check(tmp_path)
    assert not result.passed and result.error_count == 1


def test_ls09_test_command_parses_cases_and_semantic_errors(tmp_path: Path) -> None:
    ok = sls.SiemensLanguageService(BINARY, runner=_runner(0, "ok  \tplc-autogen/runtime\t0.5s\nsiemens-lsp test: running 2/2 cases from 2 file(s)\n")).test(tmp_path)
    assert ok.passed and (ok.cases_run, ok.cases_total) == (2, 2)
    bad = sls.SiemensLanguageService(BINARY, runner=_runner(1, "basic_test.scltest:8:9: SCLTEST_SEM_INVALID_PATH Invalid member access\n")).test(tmp_path)
    assert not bad.passed and bad.error_count == 1
    failed = sls.SiemensLanguageService(BINARY, runner=_runner(1, "--- FAIL: TestCase001 (0.00s)\n    ASSERT failed at x:14:5\nFAIL\n")).test(tmp_path)
    assert not failed.passed and failed.error_count >= 1


def test_ls10_a_timeout_or_launch_error_is_a_failure_not_a_pass(tmp_path: Path) -> None:
    def boom(args: list[str], cwd: Path, env: Mapping[str, str], timeout: int) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(args, timeout)

    result = sls.SiemensLanguageService(BINARY, runner=boom).check(tmp_path)
    assert result.available and not result.passed and result.error_count == 1


@pytest.mark.parametrize("text", ["\x1b[31mx.scl:1:1: ERROR: red\x1b[0m\n"])
def test_ls11_terminal_colour_codes_do_not_hide_an_error(tmp_path: Path, text: str) -> None:
    result = sls.SiemensLanguageService(BINARY, runner=_runner(1, text)).check(tmp_path)
    assert result.error_count == 1 and "\x1b" not in result.messages[0]


# D-137 / D-37: the plugin's Go test process dies on the native TON stub.  Whichever case reaches TON first fails, then the process
# panics and exits, so which cases got a verdict changes from run to run.  These are the panic sections of three real local runs of
# `siemens-lsp test` on DJ-2026-005 (2026-11-08, d137_test_1/2/3.txt); user name anonymised, the builtins hash and a few `...` path
# prefixes were shortened by hand.  RUN 2 and RUN 3 repeat RUN 1's stack with their own goroutine number, addresses and failed cases.
_HEAD = (
    "gogen: 34 unresolved variable references (13 unique symbols)\n"
    "gogen: 34 unresolved expression fallbacks\n"
    "siemens-lsp test: running 61/61 cases from 3 file(s)\n"
)


def _panic_block(goroutine: int, ptrs: tuple[str, str], ton_args: str, home_args: str, took: str, kept: str) -> str:
    return (
        "panic: STUB BUILTIN: B_TON [recovered, repanicked]\n\n"
        f"goroutine {goroutine} [running]:\n"
        f"testing.tRunner.func1.2({{{ptrs[0]}, {ptrs[1]}}})\n"
        "\tC:/Program Files/Go/src/testing/testing.go:1974 +0x239\n"
        "testing.tRunner.func1()\n"
        "\tC:/Program Files/Go/src/testing/testing.go:1977 +0x349\n"
        f"panic({{{ptrs[0]}?, {ptrs[1]}?}})\n"
        "\tC:/Program Files/Go/src/runtime/panic.go:860 +0x13a\n"
        "siemens.local/builtins.trapBuiltinStub(...)\n"
        "\tC:/Users/USER/AppData/Local/siemens-lsp/builtins/1707b6fb/stub_support.go:7\n"
        "siemens.local/builtins.Unimplemented(...)\n"
        "\tC:/Users/USER/AppData/Local/siemens-lsp/builtins/1707b6fb/stub_support.go:12\n"
        f"plc-autogen/runtime.FB_FB_TON({ton_args})\n"
        "\t.../01_SharedLibraries/SysLib/timer/FB_TON.scl:38 +0x37\n"
        f"plc-autogen/runtime.FB_FB_1005_HomePrepare_BufferFraming({home_args})\n"
        "\t.../DJ-2026-005/02_PLC程序/PLC_ST/06_模式与调度/FB_1005_HomePrepare_BufferFraming.scl:98 +0xcb\n"
        "created by testing.(*T).Run in goroutine 1\n"
        "\tC:/Program Files/Go/src/testing/testing.go:2101 +0x4a9\n"
        f"FAIL\tplc-autogen/runtime\t{took}\n"
        "FAIL\n"
        f"siemens-lsp test: kept generated output in C:\\Users\\USER\\AppData\\Local\\Temp\\siemens-lsp-test-{kept}\n"
    )


PANIC_RUN_1 = (
    _HEAD
    + "--- FAIL: TestUserCase061_TALM07Lamps (0.00s)\n"
    + _panic_block(78, ("0x7ff6a6185760", "0x7ff6a6203050"), "0x0?, 0x0?", "0x2d4132f07808, 0x2d4132f085b8", "1.056s", "3328374442")
)
PANIC_RUN_2 = (
    _HEAD
    + "--- FAIL: TestUserCase032_TMODE02ManualForcesOutOfAuto (0.00s)\n"
    + "--- FAIL: TestUserCase010_TPP20Mode4NeedsFourGrips (0.00s)\n"
    + "--- FAIL: TestUserCase024_TEXT0106LocalSafetyToFrame (0.00s)\n"
    + _panic_block(50, ("0x7ff6bffd5760", "0x7ff6c0053050"), "0x37d4d97f0008?, 0x1800?", "0x37d4d97f0008, 0x37d4d97f0db8", "0.841s", "211307799")
)
PANIC_RUN_3 = (
    _HEAD
    + "--- FAIL: TestUserCase001_TCONVMapLayer1 (0.00s)\n"
    + _panic_block(6, ("0x7ff6e2d65760", "0x7ff6e2de3050"), "0x1?, 0x7ff6e2a91067?", "0x23efca6cb808, 0x23efca6cc5b8", "0.717s", "3504294873")
)
ORDINARY_FAIL = (
    "siemens-lsp test: running 34/34 cases from 5 file(s)\n"
    "--- FAIL: TestUserCase029_TCMB04RcvIdShortStopAtZero (0.00s)\n"
    "    user_tests_autogen_test.go:7949: ASSERT failed at Test/modbus_client_test.scltest:103:5 step 21: got=ABC op== expected=ABC\n"
    "FAIL\nFAIL\tplc-autogen/runtime\t0.778s\n"
)


@pytest.mark.parametrize("output", [PANIC_RUN_1, PANIC_RUN_2, PANIC_RUN_3])
def test_d137_a_plugin_test_run_that_panicked_is_incomplete_and_says_why(tmp_path: Path, output: str) -> None:
    service = sls.SiemensLanguageService(BINARY, runner=_runner(1, stdout=output))

    result = service.test(tmp_path)

    assert result.panicked is True
    assert result.exit_code == -1, "the recorder treats -1 as 'did not finish'"
    assert result.passed is False and result.error_count >= 1
    assert "panic" in result.messages[0] and "不算数" in result.messages[0]
    assert "STUB BUILTIN: B_TON" in result.messages[0]


def test_d137_an_ordinary_failing_test_run_is_not_a_panic(tmp_path: Path) -> None:
    result = sls.SiemensLanguageService(BINARY, runner=_runner(1, stdout=ORDINARY_FAIL)).test(tmp_path)

    assert result.panicked is False and result.exit_code == 1
    assert any("TestUserCase029" in line for line in result.diagnostics)


def test_d137_a_panic_in_check_output_is_not_treated_as_a_test_panic(tmp_path: Path) -> None:
    result = sls.SiemensLanguageService(BINARY, runner=_runner(1, stdout="./a.scl:3:5: ERROR: bad\npanic: x\n")).check(tmp_path)

    assert result.panicked is False


def test_d137_the_failed_cases_differ_between_panicked_runs_but_none_of_them_yields_a_verdict(tmp_path: Path) -> None:
    """The three real runs list different failed cases; each is refused the same way, so no fixed/new lines can be built from them."""

    results = [sls.SiemensLanguageService(BINARY, runner=_runner(1, stdout=text)).test(tmp_path) for text in (PANIC_RUN_1, PANIC_RUN_2, PANIC_RUN_3)]

    failed = [{line for line in r.diagnostics if "--- FAIL: TestUserCase" in line} for r in results]
    assert len({frozenset(f) for f in failed}) == 3
    assert all(r.panicked and r.exit_code == -1 and not r.passed for r in results)
