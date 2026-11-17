"""``release ship`` 命令行这一层（CHG-SCPT-2026-706，审计 #857 初审第 3 条）：照 ``release deploy`` 的 8 条补。

只看模式即使带了确认也不部署；真发版先核用户凭据、运行时身份，再走预检；退出码 0/2/3/4 分得开。
GitHub 和部署都换成假的，预检用真代码但喂假的结果。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import click
import pytest
from click.testing import CliRunner

from auto_pm.application.core import release_deploy_check as rdc
from auto_pm.application.core import release_ops, release_wiring
from auto_pm.application.core import release_ship as ship_mod
from auto_pm.application.core.release_deploy import DeployError, DeployResult
from auto_pm.contracts.interlock_matrix import COMMANDS, CommandKind
from auto_pm.ui.cli import release as release_cli
from auto_pm.ui.cli.release import release_group

COMMIT = "a" * 40
RID = "1.3.3-aaaaaaa"


def _invoke(root: Path, *args: str) -> Any:
    return CliRunner().invoke(
        release_group,
        list(args),
        obj=SimpleNamespace(control_root=str(root), workspace_root=str(root)),
    )


class _GitHub:
    def __init__(self, verdict: str = "PASS") -> None:
        self.verdict = verdict

    def gate_runs(self, commit: str) -> list[dict[str, Any]]:
        return [{"id": 9, "status": "completed", "url": "u"}]

    def download_verdict(self, run_id: int, commit: str, dest: Path) -> Path | None:
        dest.mkdir(parents=True, exist_ok=True)
        target = dest / "gate_verdict.json"
        target.write_text(json.dumps({"commit": COMMIT, "verdict": self.verdict}), encoding="utf-8")
        return target


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    calls = SimpleNamespace(guard=0, deploy=[], order=[], github=_GitHub(), signed=True)

    def preflight(
        root: Path,
        spec: str,
        *,
        gate_verdict: Path | None = None,
        audit_signoff: Path | None = None,
    ) -> rdc.Preflight:
        calls.order.append("preflight")
        report = rdc.Preflight(commit=COMMIT, release_id=RID)
        report.add("门禁判决", rdc.PASS if gate_verdict else rdc.FAIL, "")
        report.add("独立审计签字", rdc.PASS if audit_signoff else rdc.FAIL, "")
        return report

    monkeypatch.setattr(rdc, "preflight", preflight)
    monkeypatch.setattr(release_ops, "pointer_release", lambda container, name: "1.3.3-bbbbbbb")
    monkeypatch.setattr(ship_mod, "_changes", lambda *a: [])
    monkeypatch.setattr(ship_mod, "GhCli", lambda root: calls.github)
    monkeypatch.setattr(
        release_cli, "arm_for_heavy_job", lambda label: calls.order.append(f"arm:{label}")
    )

    def guard(_ctx: click.Context) -> None:
        calls.guard += 1
        calls.order.append("guard")

    monkeypatch.setattr(release_cli, "require_runtime_identity_for_workspace", guard)

    def deployed(root: Path, rep: object, **kwargs: object) -> DeployResult:
        calls.deploy.append(kwargs)
        return DeployResult(
            RID, "CHG-SCPT-2026-1", str(tmp_path / "backup"), str(tmp_path / "receipt.json")
        )

    monkeypatch.setattr(release_wiring, "real_deploy", deployed)
    folder = ship_mod.candidate_dir(tmp_path, RID)
    folder.mkdir(parents=True)
    (folder / "audit_signoff.md").write_text("签字", encoding="utf-8")
    return calls


REAL = (
    "--no-check-only",
    "--confirm-ref",
    "user-confirmation:cmsg_001_ship",
    "--approver",
    "baiyang",
)


def test_a_look_exits_zero_when_it_can_switch_and_prints_json(
    tmp_path: Path, env: SimpleNamespace
) -> None:
    result = _invoke(tmp_path, "ship", "HEAD", "--json")
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["can_switch"] is True and data["deployed"] is False and data["release_id"] == RID
    assert env.deploy == [] and env.guard == 0


def test_a_look_exits_two_when_the_gate_failed(tmp_path: Path, env: SimpleNamespace) -> None:
    env.github = _GitHub("FAIL")
    result = _invoke(tmp_path, "ship", "HEAD")
    assert result.exit_code == 2 and "能切换：否" in result.output


def test_a_look_with_a_confirmation_still_never_deploys(
    tmp_path: Path, env: SimpleNamespace
) -> None:
    result = _invoke(
        tmp_path,
        "ship",
        "HEAD",
        "--confirm-ref",
        "user-confirmation:cmsg_001_ship",
        "--approver",
        "baiyang",
    )
    assert result.exit_code == 0
    assert env.deploy == [] and env.guard == 0


def test_a_real_ship_without_its_required_options_is_refused_before_any_work(
    tmp_path: Path, env: SimpleNamespace
) -> None:
    result = _invoke(tmp_path, "ship", "HEAD", "--no-check-only", "--approver", "baiyang")
    assert result.exit_code != 0 and "--confirm-ref" in result.output
    assert env.order == [] and env.deploy == []


def test_a_bad_confirmation_reference_is_refused_before_the_identity_guard(
    tmp_path: Path, env: SimpleNamespace
) -> None:
    result = _invoke(
        tmp_path, "ship", "HEAD", "--no-check-only", "--confirm-ref", "ok", "--approver", "baiyang"
    )
    assert result.exit_code != 0 and "不被接受" in result.output
    assert env.order == [] and env.deploy == []


def test_a_dirty_runtime_identity_refuses_a_real_ship_before_the_preflight(
    tmp_path: Path, env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(_ctx: click.Context) -> None:
        raise click.ClickException("运行时身份不干净")

    monkeypatch.setattr(release_cli, "require_runtime_identity_for_workspace", refuse)
    result = _invoke(tmp_path, "ship", "HEAD", *REAL)
    assert result.exit_code != 0 and "运行时身份不干净" in result.output
    assert "preflight" not in env.order and env.deploy == []


def test_a_green_real_ship_passes_the_confirmation_on_and_exits_zero(
    tmp_path: Path, env: SimpleNamespace
) -> None:
    result = _invoke(tmp_path, "ship", "HEAD", *REAL)
    assert result.exit_code == 0, result.output
    assert env.order[:2] == ["guard", "arm:deploy-gate"]
    assert env.deploy and env.deploy[0]["confirm_ref"] == "user-confirmation:cmsg_001_ship"
    assert env.deploy[0]["approver"] == "baiyang"


@pytest.mark.parametrize(
    ("rolled_back", "moved", "code"), [(True, True, 3), (False, True, 4), (False, False, 2)],
    ids=["rolled-back", "moved-not-rolled-back", "stopped-before-the-switch"],
)
def test_a_failed_real_ship_exits_like_the_real_deploy_three_four_or_two(
    tmp_path: Path,
    env: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    rolled_back: bool,
    moved: bool,
    code: int,
) -> None:
    """CHG-SCPT-2026-709: the board's release button runs ``ship``; a stop in the books (pointers never moved) is 2, not 4."""

    def failing(*args: object, **kwargs: object) -> DeployResult:
        raise DeployError("自检没过", rolled_back=rolled_back, pointers_moved=moved)

    monkeypatch.setattr(release_wiring, "real_deploy", failing)
    result = _invoke(tmp_path, "ship", "HEAD", *REAL)
    assert result.exit_code == code, result.output


def test_the_interlock_matrix_pins_ship_like_the_real_deploy() -> None:
    ship = COMMANDS["release ship"]
    assert ship.kind is CommandKind.NORMAL
    assert (
        "identity=clean" in ship.needs
        and "G-IDENTITY-WRITE" in ship.guards
        and "G-AGENT-APPROVAL" in ship.guards
    )
