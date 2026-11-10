"""D-196: the gate looks at its own interpreter before it starts, and tells a dead environment from a failing test.

2026-11-09: the full gate was started with the system Python (no xdist).  Every group died at once, the summary said FAIL and its
reason column was empty.  These tests pin the refusal, the warning, and the two kinds of "not PASS".
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from click.testing import CliRunner

from auto_pm.application.core import gate_env_preflight as pre
from auto_pm.application.core.gate_run_service import GateRunError
from auto_pm.ui.cli import gate as gate_cli


def _prober(
    *, missing: Sequence[str] = (), venv: bool = True, code: int = 0, out: bytes | None = None
) -> Callable[[Sequence[str], int], subprocess.CompletedProcess[bytes]]:
    def run(argv: Sequence[str], timeout: int) -> subprocess.CompletedProcess[bytes]:
        body = (
            out
            if out is not None
            else json.dumps(
                {"version": [3, 12, 3], "venv": venv, "missing": list(missing)}
            ).encode()
        )
        return subprocess.CompletedProcess(list(argv), code, stdout=body, stderr=b"boom\n")

    return run


def test_e01_a_fit_interpreter_has_no_refusal_and_no_warning(tmp_path: Path) -> None:
    assert pre.preflight_problems("py", tmp_path, prober=_prober()) == ([], [])


def test_e02_missing_xdist_is_refused_and_the_message_names_the_package_and_the_way_out(
    tmp_path: Path,
) -> None:
    refusals, _ = pre.preflight_problems("py", tmp_path, prober=_prober(missing=["xdist"]))
    assert refusals and "xdist" in refusals[0]
    assert any("正确的启动方式" in line for line in refusals)


@pytest.mark.parametrize("module", ["xdist", "pytestqt", "PySide6", "jinja2", "pytest"])
def test_e03_every_required_module_is_probed(module: str) -> None:
    assert module in pre.REQUIRED_MODULES


def test_e04_the_system_python_gets_a_warning_not_a_refusal(tmp_path: Path) -> None:
    refusals, warnings = pre.preflight_problems("py", tmp_path, prober=_prober(venv=False))
    assert refusals == [] and warnings and "虚拟环境" in warnings[0]


@pytest.mark.parametrize("prober", [_prober(code=3), _prober(out=b"not json")])
def test_e05_a_probe_that_fails_or_is_unreadable_is_a_refusal_never_a_pass(
    tmp_path: Path, prober: object
) -> None:
    refusals, _ = pre.preflight_problems("py", tmp_path, prober=prober)  # type: ignore[arg-type]
    assert refusals


def test_e06_an_interpreter_that_cannot_start_is_a_refusal(tmp_path: Path) -> None:
    def broken(argv: Sequence[str], timeout: int) -> subprocess.CompletedProcess[bytes]:
        raise FileNotFoundError("no such interpreter")

    refusals, _ = pre.preflight_problems("nope", tmp_path, prober=broken)
    assert refusals and "起不来" in refusals[0]


@pytest.mark.skipif(
    sys.platform == "win32", reason="the stand-in interpreter is a POSIX shell wrapper"
)
def test_e07_a_real_interpreter_without_xdist_is_refused(tmp_path: Path) -> None:
    """The counter-example of the incident: ``python -S`` has no site-packages, so no xdist, no pytest."""

    wrapper = tmp_path / "python-nosite"
    wrapper.write_text(
        f'#!/bin/sh\nexec "{Path(sys.executable).as_posix()}" -S "$@"\n',
        encoding="utf-8",
        newline="\n",
    )
    wrapper.chmod(0o755)
    refusals, _ = pre.preflight_problems(str(wrapper), tmp_path)
    assert refusals and "xdist" in refusals[0]


def test_e08_the_hint_prefers_an_existing_venv_of_the_control_root(tmp_path: Path) -> None:
    root = tmp_path / "with-venv"
    python = root / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    assert str(python) in pre.venv_command_hint(root / "wt")
    assert "setup_env" in pre.venv_command_hint(tmp_path / "without-venv" / "wt")


@pytest.mark.parametrize(
    "line",
    [
        "main.py: error: unrecognized arguments: -n 8",
        "ImportError while loading conftest '/x/conftest.py'.",
        "E   ModuleNotFoundError: No module named 'xdist'",
    ],
)
def test_e09_environment_death_lines_are_recognised(line: str) -> None:
    assert pre.looks_like_environment_error("noise\n" + line + "\nmore\n")


def test_e10_an_ordinary_failure_is_not_an_environment_error() -> None:
    assert (
        pre.looks_like_environment_error(
            "FAILED tests/x.py::test_a - assert 1 == 2\n1 failed, 3 passed in 1s\n"
        )
        == ""
    )


def test_e11_cli_prints_the_preflight_warning_even_when_the_gate_cannot_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class Service:
        preflight_warnings = ["当前解释器 /usr/bin/python3 不在虚拟环境里"]

        def run(self, *_a: object, **_k: object) -> object:
            raise GateRunError("环境不合格，未开跑：缺 xdist")

    monkeypatch.setattr(gate_cli, "GateRunService", Service)
    monkeypatch.setattr(gate_cli, "require_runtime_identity_for_workspace", lambda *_a, **_k: None)
    monkeypatch.setattr(gate_cli, "arm_for_heavy_job", lambda *_a, **_k: None)
    result = CliRunner().invoke(
        gate_cli.gate_group, ["run", "--worktree", str(tmp_path), "--out", str(tmp_path / "o")]
    )
    assert result.exit_code == 2
    assert "环境不合格，未开跑" in result.output and "不在虚拟环境里" in result.output


def test_e12_every_required_module_name_is_a_real_import_name_in_this_environment() -> None:
    """D-196 regression: "pytest_qt" is the distribution's spelling, the import name is "pytestqt"; the name list was never run against a real interpreter."""

    import importlib.util
    import sys

    unknown = [name for name in pre.REQUIRED_MODULES if importlib.util.find_spec(name) is None]
    assert unknown == [], f"REQUIRED_MODULES 里的名字在本环境导入不了（写成了发行包名？）：{unknown}"
    report = pre.probe_interpreter(sys.executable)  # the real probe, no stand-in prober
    assert report.error == "" and report.missing == (), "合格环境不应被预检拒绝"
