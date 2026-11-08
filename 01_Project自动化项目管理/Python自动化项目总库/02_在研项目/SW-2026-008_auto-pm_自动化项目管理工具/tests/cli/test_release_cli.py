"""D-146 card 1: ``release status`` / ``release deploy --check-only`` as commands (read-only, exit codes)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner

from auto_pm.application.core import release_deploy_check as rdc
from auto_pm.ui.cli.release import release_group


def _invoke(root: Path, *args: str):  # type: ignore[no-untyped-def]
    return CliRunner().invoke(release_group, list(args), obj=SimpleNamespace(control_root=str(root), workspace_root=str(root)))


def test_status_prints_the_pointers_in_plain_words_and_as_json(tmp_path: Path) -> None:
    base = tmp_path / rdc.CONTAINER
    base.mkdir(parents=True)
    (base / "active_release.json").write_text(json.dumps({"release_id": "1.3.3-aaaaaaa"}), encoding="utf-8")

    plain = _invoke(tmp_path, "status")
    machine = _invoke(tmp_path, "status", "--json")

    assert plain.exit_code == 0 and "active: 1.3.3-aaaaaaa" in plain.output
    assert json.loads(machine.output)["pointers"]["active"]["release_id"] == "1.3.3-aaaaaaa"


def test_a_real_deploy_is_refused_until_the_later_card_exists(tmp_path: Path) -> None:
    result = _invoke(tmp_path, "deploy", "HEAD", "--no-check-only")

    assert result.exit_code == 1 and "还没实现" in result.output


def test_a_failed_preflight_exits_two_and_says_which_check(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    report = rdc.Preflight(commit="a" * 40, release_id="1.3.3-aaaaaaa")
    report.add("门禁判决", rdc.FAIL, "没给 --gate-verdict")
    monkeypatch.setattr(rdc, "preflight", lambda *_a, **_k: report)

    plain = _invoke(tmp_path, "deploy", "HEAD", "--check-only")
    machine = _invoke(tmp_path, "deploy", "HEAD", "--json")

    assert plain.exit_code == 2 and "不能部署" in plain.output and "[FAIL] 门禁判决" in plain.output
    assert machine.exit_code == 2 and json.loads(machine.output)["ok"] is False


def test_a_passing_preflight_exits_zero(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    report = rdc.Preflight(commit="a" * 40, release_id="1.3.3-aaaaaaa")
    report.add("提交存在", rdc.PASS, "ok")
    monkeypatch.setattr(rdc, "preflight", lambda *_a, **_k: report)

    result = _invoke(tmp_path, "deploy", "HEAD")

    assert result.exit_code == 0 and "可以部署" in result.output
