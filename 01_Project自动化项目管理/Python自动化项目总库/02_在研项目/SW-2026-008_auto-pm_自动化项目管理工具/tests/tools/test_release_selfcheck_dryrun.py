"""D-146 card 6a: the read-only self-check dry run script — exit codes, per-check lines, JSON summary, fresh-process identity."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from auto_pm.application.core import release_wiring as rw
from auto_pm.application.core.release_deploy import REQUIRED_SELF_CHECKS

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "release_selfcheck_dryrun.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("release_selfcheck_dryrun_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _args(tmp_path: Path, out: Path) -> list[str]:
    return ["--control-root", str(tmp_path), "--card-file", str(tmp_path / "card.md"), "--drill-script", str(tmp_path / "drill.py"),
            "--release-id", "1.3.3-aaaaaaa", "--old", "1.3.3-bbbbbbb", "--older", "1.3.3-ccccccc", "--out", str(out)]


def _fake_checks(verdicts: dict[str, tuple[bool, str]] | None = None, boom: str = ""):  # type: ignore[no-untyped-def]
    verdicts = verdicts or {}

    def build(**_kwargs: object) -> dict[str, object]:
        def make(name: str):  # type: ignore[no-untyped-def]
            def check() -> tuple[bool, str]:
                if name == boom:
                    raise RuntimeError("kaputt")
                return verdicts.get(name, (True, "ok"))
            return check
        return {name: make(name) for name in REQUIRED_SELF_CHECKS}

    return build


def test_a_control_root_without_main_py_is_refused_with_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _load().main(_args(tmp_path, tmp_path / "out.json")) == 2
    assert "main.py" in capsys.readouterr().out and not (tmp_path / "out.json").exists()


def test_a_missing_drill_script_is_refused_with_exit_2_before_anything_runs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "main.py").write_text("", encoding="utf-8")
    (tmp_path / "card.md").write_text("x", encoding="utf-8")

    assert _load().main(_args(tmp_path, tmp_path / "out.json")) == 2
    assert "不存在" in capsys.readouterr().out and not (tmp_path / "out.json").exists()


def test_all_green_prints_every_check_writes_the_json_and_exits_0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "main.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(rw, "build_self_checks", _fake_checks())
    out = tmp_path / "out.json"

    assert _load().main(_args(tmp_path, out)) == 0

    shown = capsys.readouterr().out
    assert shown.count("[通过]") == len(REQUIRED_SELF_CHECKS) and "[失败]" not in shown
    summary = json.loads(out.read_text(encoding="utf-8"))
    assert summary["all_passed"] is True and summary["failed"] == [] and summary["total"] == len(REQUIRED_SELF_CHECKS)
    assert [row["check"] for row in summary["results"]] == list(REQUIRED_SELF_CHECKS)


def test_one_failing_and_one_crashing_check_exit_1_and_are_named(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "main.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(rw, "build_self_checks", _fake_checks({"identity": (False, "不是新版")}, boom="card precheck"))
    out = tmp_path / "out.json"

    assert _load().main(_args(tmp_path, out)) == 1

    shown = capsys.readouterr().out
    assert "[失败] identity  不是新版" in shown and "[失败] card precheck" in shown and "kaputt" in shown
    summary = json.loads(out.read_text(encoding="utf-8"))
    assert summary["all_passed"] is False and summary["failed"] == ["identity", "card precheck"]


def test_the_identity_is_read_from_a_fresh_process_and_unreadable_output_is_an_empty_identity(tmp_path: Path) -> None:
    payload = {"context": {"configured_release_id": "R", "effective_release_id": "R", "runtime_load_path": "p", "runtime_fallback_reason": "", "x": 1},
               "conflicts": [{"code": "A"}, "B"]}
    seen: list[list[str]] = []

    def good(argv: list[str], cwd: Path) -> tuple[int, str]:
        seen.append(argv)
        return 0, "noise\n" + json.dumps(payload)

    module = _load()
    found = module.fresh_identity(good, "py")(tmp_path)

    assert seen[0] == ["py", "-B", str(tmp_path / "main.py"), "pm", "resume", "SW-2026-008", "--json"]
    assert found["configured_release_id"] == "R" and "x" not in found and found["conflicts"] == ["A", "B"]
    assert module.fresh_identity(lambda a, c: (1, "boom"))(tmp_path) == {}
    assert module.fresh_identity(lambda a, c: (0, "no json"))(tmp_path) == {}
    assert module.fresh_identity(lambda a, c: (0, "{broken"))(tmp_path) == {}
