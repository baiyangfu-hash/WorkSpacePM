"""The cloud full gate's jobs run the cockpit's own gate code, so every job that does must first install the locked dependencies (D-223).

The first cloud run of ``gate-full`` (run 42747765543) ended without a verdict: the ``verdict`` job ran
``tests/tools/sw008_ci/gate_run_ci.py merge`` with the runner's bare Python, the judge imports ``auto_pm`` and that import needs
PyYAML.  These checks read the workflow file and fail when a job calls ``gate_run_ci.py`` with an interpreter other than the one
the same job installed the lock file into.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.external_reads  # D-200: reads real files outside the project

PROJECT = Path(__file__).resolve().parents[2]
WORKSPACE = PROJECT.parents[3]
WORKFLOW = WORKSPACE / ".github" / "workflows" / "gate-full.yml"
LOCK_FILE = "00_Infrastructure/auto_pm/environment/requirements-lock-py312-win.txt"
VENV_PYTHON = '"$RUNNER_TEMP/venv/Scripts/python.exe"'
GATE_SCRIPT = "tests/tools/sw008_ci/gate_run_ci.py"


def _jobs() -> dict[str, dict[str, Any]]:
    loaded = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = loaded["jobs"]
    assert isinstance(jobs, dict) and jobs
    return jobs


def _runs(job: dict[str, Any]) -> list[str]:
    return [str(step.get("run", "")) for step in job["steps"]]


def _gate_jobs() -> dict[str, dict[str, Any]]:
    return {name: job for name, job in _jobs().items() if any(GATE_SCRIPT in run for run in _runs(job))}


def test_the_group_job_and_the_verdict_job_both_run_the_gate_script() -> None:
    assert {"group", "verdict"} <= set(_gate_jobs())


def test_every_job_that_runs_the_gate_script_installs_the_locked_dependencies_first() -> None:
    for name, job in _gate_jobs().items():
        runs = _runs(job)
        installs = [i for i, run in enumerate(runs) if LOCK_FILE in run and "pip install" in run]
        calls = [i for i, run in enumerate(runs) if GATE_SCRIPT in run]
        assert installs, f"job {name} runs {GATE_SCRIPT} but never installs {LOCK_FILE}"
        assert installs[0] < calls[0], f"job {name} runs {GATE_SCRIPT} before it installs the locked dependencies"
        assert VENV_PYTHON in runs[installs[0]], f"job {name} does not install the lock file into the venv the gate script is run with"
        assert job["runs-on"] == "windows-latest", f"job {name}: the lock file is the Windows one, the job runs on {job['runs-on']}"


def test_the_gate_script_is_only_ever_run_with_the_venv_python() -> None:
    for name, job in _gate_jobs().items():
        for run in _runs(job):
            for line in run.splitlines():
                if GATE_SCRIPT in line:
                    assert line.strip().startswith(VENV_PYTHON + " " + GATE_SCRIPT), f"job {name}: {line.strip()}"
