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
