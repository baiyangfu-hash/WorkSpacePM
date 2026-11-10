"""CHG-SCPT-2026-626: gate-full's ``plugin`` job really runs the Siemens language service plugin without ever redistributing it.

The user decided (11-10) that the plugin may run in the cloud.  The author's terms are non-commercial use and no redistribution, so the
workflow may only fetch it at run time from the official Marketplace, at a pinned version, check its hash, and keep it on the throw-away
runner.  These tests read ``.github/workflows/gate-full.yml`` and fail the moment a change would cache it, upload it, unpin it, use it
unchecked, or leak ``AUTO_PM_SIEMENS_LSP`` into the eleven ordinary groups (whose tests are written for the "no plugin" default).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.e2e import test_pmf_template_plc as template_plc

WORKFLOW = Path(__file__).resolve().parents[6] / ".github" / "workflows" / "gate-full.yml"
PLUGIN_JOB = "plugin"
ENV_NAME = "AUTO_PM_SIEMENS_LSP"


def _workflow() -> dict[str, Any]:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    return list(job.get("steps") or [])


def _run_text(step: dict[str, Any]) -> str:
    return str(step.get("run") or "")


def test_the_workflow_file_is_where_this_test_looks() -> None:
    assert WORKFLOW.is_file(), WORKFLOW


def test_the_plugin_job_runs_on_windows_at_a_pinned_version_and_a_pinned_hash() -> None:
    job = _workflow()["jobs"][PLUGIN_JOB]
    env = job["env"]

    assert job["runs-on"] == "windows-latest"
    assert re.fullmatch(r"\d+\.\d+\.\d+", str(env["LSP_VERSION"])), env["LSP_VERSION"]
    assert re.fullmatch(r"[0-9a-f]{64}", str(env["LSP_EXE_SHA256"])), "the command line's SHA256 must be pinned"
    download = next(step for step in _steps(job) if "vspackage" in _run_text(step))
    text = _run_text(download)
    assert "marketplace.visualstudio.com/_apis/public/gallery/publishers/" in text  # the official Marketplace only
    assert "$LSP_VERSION" in text and "latest" not in text


def test_the_hash_is_checked_before_the_command_line_is_handed_to_the_tests() -> None:
    job = _workflow()["jobs"][PLUGIN_JOB]
    download = next(step for step in _steps(job) if "vspackage" in _run_text(step))
    text = _run_text(download)

    assert "set -euo pipefail" in text
    compare = text.index('if [ "$actual" != "$LSP_EXE_SHA256" ]')
    hand_over = text.index(f"{ENV_NAME}=")
    assert compare < hand_over and "exit 1" in text[compare:hand_over]
    assert '"$RUNNER_TEMP/siemens-lsp"' in text  # kept on the runner's temporary disk, outside the checkout


def test_nothing_in_gate_full_caches_or_uploads_the_plugin() -> None:
    jobs = _workflow()["jobs"]

    for name, job in jobs.items():
        for step in _steps(job):
            uses = str(step.get("uses") or "")
            assert not uses.startswith("actions/cache"), f"{name}: a cache step would keep the plugin beyond the runner"
            if uses.startswith("actions/upload-artifact"):
                assert name != PLUGIN_JOB, "the plugin job must not upload anything"
                assert "siemens-lsp" not in str(step.get("with") or {}), f"{name}: uploads the plugin"
            assert "git push" not in _run_text(step) and "git commit" not in _run_text(step)


def test_only_the_plugin_job_points_at_the_real_command_line() -> None:
    data = _workflow()

    assert ENV_NAME not in (data.get("env") or {})
    for name, job in data["jobs"].items():
        assert ENV_NAME not in (job.get("env") or {}), name
        for step in _steps(job):
            assert ENV_NAME not in (step.get("env") or {}), name
            if name != PLUGIN_JOB:
                assert ENV_NAME not in _run_text(step), f"{name} must keep the conftest default (no plugin)"


def test_the_plugin_tests_fail_instead_of_skipping_in_that_job() -> None:
    job = _workflow()["jobs"][PLUGIN_JOB]
    run = next(step for step in _steps(job) if "pytest" in _run_text(step))

    assert (run.get("env") or {}).get(template_plc.REQUIRE_PLUGIN_ENV) == "1"
    assert "tests/e2e/test_pmf_template_plc.py" in _run_text(run)


def test_a_missing_plugin_is_a_skip_normally_and_a_failure_when_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(template_plc.REQUIRE_PLUGIN_ENV, raising=False)
    with pytest.raises(pytest.skip.Exception, match="UNVERIFIED"):
        template_plc._missing_plugin("no plugin here")

    monkeypatch.setenv(template_plc.REQUIRE_PLUGIN_ENV, "1")
    with pytest.raises(pytest.fail.Exception, match="no plugin here"):
        template_plc._missing_plugin("no plugin here")
