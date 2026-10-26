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
        "exit 0\n",
        encoding="utf-8",
    )
    lsp.chmod(0o755)
    return lsp


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
