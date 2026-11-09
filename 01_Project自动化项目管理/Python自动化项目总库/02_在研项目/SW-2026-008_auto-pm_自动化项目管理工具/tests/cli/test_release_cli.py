"""D-146 card 1: ``release status`` / ``release deploy --check-only`` as commands (read-only, exit codes)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

from auto_pm.application.core import release_deploy_check as rdc
from auto_pm.application.core import release_ops as ops
from auto_pm.application.core import release_wiring
from auto_pm.application.core.release_deploy import DeployError, DeployResult
from auto_pm.application.core.release_ledger import LedgerError
from auto_pm.ui.cli import release as release_cli
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


# --- D-146 card 6b: the real deploy and the rollback ------------------------------------------------------------------------------------


@pytest.fixture
def real(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """A green preflight, a passing identity guard and a recording ``real_deploy``; each test overrides what it needs."""

    calls = SimpleNamespace(guard=0, deploy=[], warn=0, order=[])
    report = rdc.Preflight(commit="a" * 40, release_id="1.3.3-aaaaaaa")
    report.add("提交存在", rdc.PASS, "ok")
    calls.report = report
    def preflight(*_a: object, **_k: object) -> rdc.Preflight:
        calls.order.append("preflight")
        return calls.report  # type: ignore[no-any-return]

    monkeypatch.setattr(rdc, "preflight", preflight)
    monkeypatch.setattr(release_cli, "arm_for_heavy_job", lambda label: calls.order.append(f"arm:{label}"))

    def guard(_ctx: click.Context) -> None:
        calls.guard += 1

    monkeypatch.setattr(release_cli, "require_runtime_identity_for_workspace", guard)
    monkeypatch.setattr(release_cli, "warn_runtime_identity", lambda *_a, **_k: setattr(calls, "warn", calls.warn + 1))

    def deployed(root: Path, rep: object, **kwargs: object) -> DeployResult:
        calls.deploy.append(kwargs)
        return DeployResult("1.3.3-aaaaaaa", "CHG-SCPT-2026-1", str(tmp_path / "backup"), str(tmp_path / "receipt.json"))

    monkeypatch.setattr(release_wiring, "real_deploy", deployed)
    return calls


def _real_args(tmp_path: Path, *extra: str) -> list[str]:
    card, drill = tmp_path / "card.md", tmp_path / "drill.py"
    card.write_text("c", encoding="utf-8")
    drill.write_text("d", encoding="utf-8")
    return ["deploy", "HEAD", "--no-check-only", "--confirm-ref", "user-confirmation:cmsg_001", "--approver", "fubai",
            "--card-file", str(card), "--drill-script", str(drill), *extra]


def test_check_only_never_touches_the_guard_or_the_real_deploy(tmp_path: Path, real: SimpleNamespace) -> None:
    result = _invoke(tmp_path, "deploy", "HEAD")

    assert result.exit_code == 0 and real.guard == 0 and real.deploy == []
    assert not any(step.startswith("arm:") for step in real.order), "a read-only preflight is not a heavy job"


def test_a_real_deploy_without_its_required_options_is_refused_before_any_work(tmp_path: Path, real: SimpleNamespace) -> None:
    result = _invoke(tmp_path, "deploy", "HEAD", "--no-check-only")

    assert result.exit_code == 1 and "--confirm-ref" in result.output and "--drill-script" in result.output
    assert real.deploy == [] and real.order == [], "a refused command must not arm the memory gate"


def test_a_dirty_runtime_identity_refuses_a_real_deploy_before_the_preflight(tmp_path: Path, real: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(_ctx: click.Context) -> None:
        raise click.ClickException("运行身份有冲突")

    monkeypatch.setattr(release_cli, "require_runtime_identity_for_workspace", refuse)
    monkeypatch.setattr(rdc, "preflight", lambda *_a, **_k: pytest.fail("the preflight must not run"))

    result = _invoke(tmp_path, *_real_args(tmp_path))

    assert result.exit_code == 1 and "运行身份有冲突" in result.output and real.deploy == []


def test_a_red_preflight_stops_a_real_deploy_with_exit_two_and_writes_nothing(tmp_path: Path, real: SimpleNamespace) -> None:
    real.report.add("门禁判决", rdc.FAIL, "没给")

    result = _invoke(tmp_path, *_real_args(tmp_path))

    assert result.exit_code == 2 and "[FAIL] 门禁判决" in result.output and real.deploy == []


def test_a_green_real_deploy_passes_everything_on_and_prints_the_receipt_and_the_rollback_command(tmp_path: Path, real: SimpleNamespace) -> None:
    result = _invoke(tmp_path, *_real_args(tmp_path))

    assert result.exit_code == 0 and "已部署 1.3.3-aaaaaaa" in result.output and "release rollback" in result.output
    assert real.guard == 1 and len(real.deploy) == 1
    assert real.deploy[0]["confirm_ref"] == "user-confirmation:cmsg_001" and real.deploy[0]["approver"] == "fubai"
    assert real.order == ["arm:deploy-gate", "preflight"], "the memory gate is armed (D-168) before the first heavy step"


@pytest.mark.parametrize(("rolled_back", "code"), [(True, 3), (False, 4)])
def test_a_failed_deploy_exits_three_when_rolled_back_and_four_when_a_person_must_step_in(
    tmp_path: Path, real: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, rolled_back: bool, code: int,
) -> None:
    def failing(*_a: object, **_k: object) -> DeployResult:
        raise DeployError("自检没过", rolled_back=rolled_back)

    monkeypatch.setattr(release_wiring, "real_deploy", failing)

    result = _invoke(tmp_path, *_real_args(tmp_path))

    assert result.exit_code == code and "自检没过" in result.output


def test_a_malformed_confirmation_reference_is_a_usage_error_not_a_deploy_failure(tmp_path: Path, real: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    def refusing(*_a: object, **_k: object) -> DeployResult:
        raise LedgerError("缺少用户确认引用")

    monkeypatch.setattr(release_wiring, "real_deploy", refusing)

    result = _invoke(tmp_path, *_real_args(tmp_path))

    assert result.exit_code == 1 and "用户确认引用" in result.output


def test_rollback_warns_about_the_identity_never_refuses_and_prints_the_restored_release(tmp_path: Path, real: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    backup = tmp_path / "backup"
    backup.mkdir()
    seen: list[Path] = []

    def restoring(_root: object, folder: Path, _identity: object) -> dict[str, object]:
        seen.append(folder)
        return {"active": "1.3.3-1234567", "identity": {}}

    monkeypatch.setattr(ops, "rollback", restoring)

    result = _invoke(tmp_path, "rollback", str(backup))

    assert result.exit_code == 0 and "1.3.3-1234567" in result.output and seen == [backup] and real.warn == 1 and real.guard == 0


def test_a_refused_rollback_is_an_error_with_the_reason(tmp_path: Path, real: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    backup = tmp_path / "backup"
    backup.mkdir()

    def refusing(*_a: object) -> dict[str, object]:
        raise ops.ReleaseOpsError("备份文件被改过或缺失：active_release.json")

    monkeypatch.setattr(ops, "rollback", refusing)

    result = _invoke(tmp_path, "rollback", str(backup))

    assert result.exit_code == 1 and "被改过" in result.output
