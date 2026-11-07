"""D-107a / D-108 / D-105: the official multi-group gate.

Three failures of the 11-07 deployment gate, each pinned here: groups run where no ``tests/`` exists and "pass" with exit 4/5
(D-105); cockpit variables leak into the test children (D-108); the verdict of a many-group run depends on every group being there
and judged on its own summary line (D-107).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from auto_pm.application.core import gate_run_service as gate
from auto_pm.application.core.gate_run_service import (
    GROUPS,
    GateGroup,
    GateRunError,
    GateRunService,
)

_PASS_LINE = "123 passed, 2 skipped in 4.20s\n"


def _group(name: str = "g", **changes: object) -> GateGroup:
    return GateGroup(name, ("tests/x",), **changes)  # type: ignore[arg-type]


def _log(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "g.txt"
    path.write_text(text, encoding="utf-8")
    return path


# ── environment (D-108) ─────────────────────────────────


def test_child_environment_never_carries_cockpit_variables() -> None:
    base = {
        "PATH": "/usr/bin",
        "HOME": "/home/x",
        "AUTO_PM_WORKSPACE": "/real/ws",
        "AUTO_PM_CONTROL_ROOT": "/real/root",
        "AUTO_PM_RUN_WORKTREE": "/real/wt",
        "AUTO_PM_CALLER_CWD": "/release",
        "AUTO_PM_AGENT": "claude",
        "CLAUDECODE": "1",
        "LONG_GATE_LEASE_TOKEN": "secret",
        "PYTEST_ADDOPTS": "-k nothing",
    }
    env = gate.child_environment(base)
    assert env["PATH"] == "/usr/bin" and env["HOME"] == "/home/x"
    assert not [key for key in env if key.upper().startswith("AUTO_PM_")]
    assert (
        "CLAUDECODE" not in env
        and "LONG_GATE_LEASE_TOKEN" not in env
        and "PYTEST_ADDOPTS" not in env
    )
    assert env["PYTHONDONTWRITEBYTECODE"] == "1" and env["PYTHONUTF8"] == "1"


def test_child_environment_filter_is_case_insensitive_for_windows_names() -> None:
    env = gate.child_environment({"Path": "C:\\bin", "auto_pm_workspace": "x"})
    assert env["Path"] == "C:\\bin" and "auto_pm_workspace" not in env


# ── judging (D-105) ─────────────────────────────────────


@pytest.mark.parametrize("code", [1, 2, 4, 5, 124])
def test_nonzero_exit_fails_even_with_a_pass_line(tmp_path: Path, code: int) -> None:
    verdict, why = gate.judge_group(_group(), code, _log(tmp_path, _PASS_LINE))
    assert verdict == "FAIL" and str(code) in why


def test_exit_zero_with_no_tests_ran_is_a_failure(tmp_path: Path) -> None:
    verdict, why = gate.judge_group(_group(), 0, _log(tmp_path, "no tests ran in 0.01s\n"))
    assert verdict == "FAIL" and "no tests ran" in why


def test_exit_zero_without_a_summary_line_is_a_failure(tmp_path: Path) -> None:
    verdict, _ = gate.judge_group(_group(), 0, _log(tmp_path, "just some output\n"))
    assert verdict == "FAIL"


def test_missing_log_and_missing_exit_code_fail(tmp_path: Path) -> None:
    assert gate.judge_group(_group(), 0, tmp_path / "absent.txt")[0] == "FAIL"
    assert gate.judge_group(_group(), None, _log(tmp_path, _PASS_LINE))[0] == "FAIL"


def test_failed_in_the_summary_line_fails_even_with_exit_zero(tmp_path: Path) -> None:
    assert (
        gate.judge_group(_group(), 0, _log(tmp_path, "1 failed, 5 passed in 1.00s\n"))[0] == "FAIL"
    )


def test_undeclared_deselect_fails_and_declared_deselect_passes(tmp_path: Path) -> None:
    log = _log(tmp_path, "10 passed, 1 deselected in 1.00s\n")
    assert gate.judge_group(_group(), 0, log)[0] == "FAIL"
    assert gate.judge_group(_group(deselect=("a::b",)), 0, log)[0] == "PASS"


def test_plain_pass(tmp_path: Path) -> None:
    assert gate.judge_group(_group(), 0, _log(tmp_path, _PASS_LINE)) == ("PASS", "")


# ── group table ─────────────────────────────────────────


def test_group_table_is_the_eleven_invocations_and_rest_ignores_the_others() -> None:
    names = [g.name for g in GROUPS]
    assert len(names) == len(set(names)) == 11
    rest = next(g for g in GROUPS if g.name == "rest")
    for name in (
        "application",
        "change",
        "cli",
        "contracts",
        "core",
        "infrastructure",
        "plc",
        "qml",
    ):
        assert f"tests/{name}" in rest.ignore
    core = next(g for g in GROUPS if g.name == "core")
    assert "tests/core/test_implementation_card_basis.py" in core.ignore


def test_argv_has_no_cwd_dependence_and_serial_groups_have_no_xdist() -> None:
    parallel = gate.group_argv(next(g for g in GROUPS if g.name == "cli"), python="py", jobs=8)
    serial = gate.group_argv(next(g for g in GROUPS if g.name == "qml"), python="py", jobs=8)
    assert "-n" in parallel and "-n" not in serial
    assert "--no-cov" in parallel and "-p" in parallel
    assert (
        "--deselect=tests/qml/test_file_watcher_bridge.py::test_debounce_coalesces_events" in serial
    )


def test_manifest_sha256_changes_when_a_group_is_removed() -> None:
    assert gate.manifest_sha256(GROUPS) != gate.manifest_sha256(GROUPS[:-1])


# ── running ─────────────────────────────────────────────


class _Recorder:
    """Stands in for pytest: writes a log per group and remembers the environment it was given."""

    def __init__(self, outcomes: Mapping[str, tuple[int, str]] | None = None) -> None:
        self.outcomes = dict(outcomes or {})
        self.envs: list[Mapping[str, str]] = []
        self.cwds: list[Path] = []

    def __call__(
        self, argv: Sequence[str], cwd: Path, env: Mapping[str, str], log: Path, timeout: int
    ) -> int:
        name = log.stem
        code, text = self.outcomes.get(name, (0, _PASS_LINE))
        if name == "qml":
            text = "10 passed, 1 deselected in 1.00s\n" if code == 0 else text
        log.write_text(text, encoding="utf-8")
        self.envs.append(env)
        self.cwds.append(cwd)
        return code


def _clean_repo(monkeypatch: pytest.MonkeyPatch, dirty: bool = False) -> Path:
    real = gate._git

    def fake(worktree: Path, *args: str) -> str | None:
        if args[:1] == ("status",):
            return " M x.py" if dirty else ""
        if args[:1] == ("rev-parse",) and "HEAD" in args:
            return "a" * 40
        return real(worktree, *args)

    monkeypatch.setattr(gate, "_git", fake)
    top = Path(gate.__file__).resolve()
    return next(p for p in top.parents if (p / ".git").exists())


def test_full_run_passes_and_every_child_gets_the_clean_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUTO_PM_WORKSPACE", "/real/ws")
    monkeypatch.setenv("AUTO_PM_CONTROL_ROOT", "/real/root")
    repo = _clean_repo(monkeypatch)
    recorder = _Recorder()
    summary = GateRunService(runner=recorder).run(repo, tmp_path)
    assert summary.verdict == "PASS" and summary.complete
    assert len(recorder.envs) == 11
    assert all(not [k for k in env if k.upper().startswith("AUTO_PM_")] for env in recorder.envs)
    assert all((cwd / "tests").is_dir() for cwd in recorder.cwds)  # D-105: never the release folder
    saved = json.loads((tmp_path / "gate_summary.json").read_text(encoding="utf-8"))
    assert saved["verdict"] == "PASS" and set(saved["results"]) == {g.name for g in GROUPS}
    assert all(item["log_sha256"] for item in saved["results"].values())


def test_one_group_with_no_tests_ran_fails_the_whole_gate_although_every_exit_is_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _clean_repo(monkeypatch)
    summary = GateRunService(runner=_Recorder({"rest": (0, "no tests ran in 0.01s\n")})).run(
        repo, tmp_path
    )
    assert summary.verdict == "FAIL"
    assert summary.results["rest"].verdict == "FAIL"


def test_exit_five_group_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _clean_repo(monkeypatch)
    summary = GateRunService(runner=_Recorder({"core": (5, "no tests ran in 0.01s\n")})).run(
        repo, tmp_path
    )
    assert summary.verdict == "FAIL" and "4/5" in summary.results["core"].why


def test_partial_run_is_never_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _clean_repo(monkeypatch)
    summary = GateRunService(runner=_Recorder()).run(repo, tmp_path, only=["plc"])
    assert summary.verdict == "PARTIAL" and not summary.complete


def test_dirty_worktree_is_never_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _clean_repo(monkeypatch, dirty=True)
    summary = GateRunService(runner=_Recorder()).run(repo, tmp_path)
    assert summary.verdict != "PASS"


def test_unknown_group_and_missing_tests_dir_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _clean_repo(monkeypatch)
    with pytest.raises(GateRunError, match="未知的组"):
        GateRunService(runner=_Recorder()).run(repo, tmp_path, only=["nope"])
    with pytest.raises(GateRunError, match="不是 Git 工作树"):
        GateRunService(runner=_Recorder()).run(tmp_path, tmp_path / "out")


def test_judge_dir_recomputes_from_the_logs_and_catches_a_tampered_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _clean_repo(monkeypatch)
    GateRunService(runner=_Recorder()).run(repo, tmp_path)
    assert GateRunService().judge_dir(tmp_path).verdict == "PASS"
    (tmp_path / "plc.txt").write_text("3 failed, 1 passed in 1.00s\n", encoding="utf-8")
    again = GateRunService().judge_dir(tmp_path)
    assert again.verdict == "FAIL" and again.results["plc"].verdict == "FAIL"


def test_judge_dir_does_not_write_anything(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _clean_repo(monkeypatch)
    GateRunService(runner=_Recorder()).run(repo, tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    GateRunService().judge_dir(tmp_path)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_a_summary_with_only_skipped_tests_is_a_failure(tmp_path: Path) -> None:
    verdict, why = gate.judge_group(_group(), 0, _log(tmp_path, "5 skipped in 0.10s\n"))
    assert verdict == "FAIL" and "没跑" in why
