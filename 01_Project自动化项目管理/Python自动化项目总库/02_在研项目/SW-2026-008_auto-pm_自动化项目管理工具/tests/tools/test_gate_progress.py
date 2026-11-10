"""D-235: the progress plugin notes the case a test process is in, and nothing else."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from auto_pm.application.core import gate_run_service as gate
from tests.tools import gate_progress

PROJECT = Path(gate_progress.__file__).resolve().parents[2]

CASE = """
import os, pathlib

def test_sees_its_own_note():
    notes = list(pathlib.Path(os.environ["GATE_RUN_PROGRESS_DIR"]).glob("*.running"))
    assert len(notes) == 1
    started, node = notes[0].read_text(encoding="utf-8").strip().split("\\t")
    assert node.endswith("::test_sees_its_own_note") and float(started) > 0
    assert notes[0].name.startswith("main-" + str(os.getpid()))

def test_second_case_replaces_the_note():
    notes = list(pathlib.Path(os.environ["GATE_RUN_PROGRESS_DIR"]).glob("*.running"))
    assert [n.read_text(encoding="utf-8").strip().split("\\t")[1].rsplit("::", 1)[1] for n in notes] == ["test_second_case_replaces_the_note"]
"""


def _run(tmp_path: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    case = tmp_path / "case" / "test_noted.py"
    case.parent.mkdir()
    case.write_text(CASE, encoding="utf-8")
    argv = [sys.executable, "-B", "-m", "pytest", str(case), "--rootdir", str(case.parent), "-c", os.devnull,
            "-p", "no:cacheprovider", "-p", gate.PROGRESS_PLUGIN, "-q"]  # fmt: skip
    return subprocess.run(argv, cwd=PROJECT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, check=False)


def test_the_names_the_gate_uses_are_the_plugins_own() -> None:
    assert gate.PROGRESS_PLUGIN == gate_progress.__name__
    assert (gate.PROGRESS_ENV, gate.PROGRESS_SUFFIX) == (gate_progress.ENV_DIR, gate_progress.SUFFIX)


def test_each_case_is_noted_while_it_runs_and_the_note_is_emptied_afterwards(tmp_path: Path) -> None:
    progress = tmp_path / "progress"
    done = _run(tmp_path, {**gate.child_environment(), gate.PROGRESS_ENV: str(progress)})
    assert done.returncode == 0, done.stdout + done.stderr
    assert "2 passed" in done.stdout
    notes = list(progress.glob(f"*{gate.PROGRESS_SUFFIX}"))
    assert len(notes) == 1 and notes[0].read_text(encoding="utf-8") == ""
    assert gate.running_cases(progress) == []


def test_without_the_variable_the_plugin_writes_nothing(tmp_path: Path) -> None:
    env = gate.child_environment()
    done = _run(tmp_path, env)
    assert done.returncode == 1 and "KeyError" in done.stdout  # the cases look for the variable; the plugin itself stayed silent
    assert not list(tmp_path.rglob(f"*{gate.PROGRESS_SUFFIX}"))


def test_a_directory_that_cannot_be_written_never_fails_a_case(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("a file where the directory should be", encoding="utf-8")
    case = tmp_path / "ok" / "test_ok.py"
    case.parent.mkdir()
    case.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    argv = [sys.executable, "-B", "-m", "pytest", str(case), "--rootdir", str(case.parent), "-c", os.devnull,
            "-p", "no:cacheprovider", "-p", gate.PROGRESS_PLUGIN, "-q"]  # fmt: skip
    env = {**gate.child_environment(), gate.PROGRESS_ENV: str(blocker / "under-a-file")}
    done = subprocess.run(argv, cwd=PROJECT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, check=False)
    assert done.returncode == 0 and "1 passed" in done.stdout, done.stdout + done.stderr
