"""``release ship``：一条命令发版（CHG-SCPT-2026-706）。

用户 2026-11-17：“发布，部署，切换，整套CI，CD能做么？”以前每次发版要手工下载云端门禁判决、找审计签字、
拼六个参数的 ``release deploy``。``ship`` 把这些收齐交给同一套预检和部署。这里用假的 GitHub 和假的部署，
只验证 ship 自己的判断：判决在哪个状态、签字在不在、什么时候才允许真部署、失败时退回有没有如实报出来。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from auto_pm.application.core import release_deploy_check as check
from auto_pm.application.core import release_ops
from auto_pm.application.core import release_ship as ship_mod
from auto_pm.application.core.release_deploy import DeployError, DeployResult

COMMIT = "c0e5bbcca64daaa85f415968fe6378d39e33c857"
RID = "1.3.3-c0e5bbc"
PASS_VERDICT = {"schema": "gate-run.v1", "commit": COMMIT, "verdict": "PASS", "complete": True}


class FakeGitHub:
    def __init__(self, runs: list[dict[str, Any]], verdict: dict[str, Any] | None = None) -> None:
        self.runs = runs
        self.verdict = verdict
        self.downloads: list[int] = []

    def gate_runs(self, commit: str) -> list[dict[str, Any]]:
        assert commit == COMMIT
        return self.runs

    def download_verdict(self, run_id: int, commit: str, dest: Path) -> Path | None:
        self.downloads.append(run_id)
        if self.verdict is None:
            return None
        dest.mkdir(parents=True, exist_ok=True)
        target = dest / "gate_verdict.json"
        target.write_text(json.dumps(self.verdict), encoding="utf-8")
        return target


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """控制根换成临时目录；预检只看传进去的判决和签字（别的检查项这里不关心，记成 PASS）。"""

    def fake_preflight(
        root: Path,
        spec: str,
        *,
        gate_verdict: Path | None = None,
        audit_signoff: Path | None = None,
    ) -> check.Preflight:
        report = check.Preflight(commit=COMMIT, release_id=RID)
        report.add("提交存在", check.PASS, COMMIT)
        report.add("门禁判决", check.PASS if gate_verdict else check.FAIL, str(gate_verdict))
        report.add("独立审计签字", check.PASS if audit_signoff else check.FAIL, str(audit_signoff))
        return report

    monkeypatch.setattr(check, "preflight", fake_preflight)
    monkeypatch.setattr(release_ops, "pointer_release", lambda container, name: "1.3.3-84d4729")
    monkeypatch.setattr(
        ship_mod, "_changes", lambda root, active, commit: [{"pr": 854, "title": "模板"}]
    )
    return tmp_path


def _signoff(root: Path) -> None:
    folder = ship_mod.candidate_dir(root, RID)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "audit_signoff.md").write_text("签字", encoding="utf-8")


def test_no_gate_run_yet_means_missing_and_no_switch(root: Path) -> None:
    report = ship_mod.ship(root, "c0e5bbc", github=FakeGitHub([]))
    assert report.gate["state"] == "missing"
    assert report.can_switch is False
    assert report.to_dict()["release_id"] == RID


def test_a_running_gate_is_reported_and_nothing_is_downloaded(root: Path) -> None:
    github = FakeGitHub([{"id": 7, "status": "in_progress", "url": "u"}], PASS_VERDICT)
    report = ship_mod.ship(root, "c0e5bbc", github=github)
    assert report.gate["state"] == "running"
    assert github.downloads == []


def test_a_finished_gate_is_downloaded_into_the_candidate_folder_but_no_signoff_blocks(
    root: Path,
) -> None:
    github = FakeGitHub([{"id": 7, "status": "completed", "url": "u"}], PASS_VERDICT)
    report = ship_mod.ship(root, "c0e5bbc", github=github)
    assert report.gate["state"] == "pass"
    assert (
        Path(report.gate["verdict_path"]) == ship_mod.candidate_dir(root, RID) / "gate_verdict.json"
    )
    assert report.gate["verdict_sha256"] == check._sha256(Path(report.gate["verdict_path"]))  # noqa: SLF001
    assert report.audit["state"] == "missing"
    assert report.can_switch is False


def test_a_failed_gate_verdict_blocks(root: Path) -> None:
    _signoff(root)
    github = FakeGitHub(
        [{"id": 7, "status": "completed", "url": "u"}], {**PASS_VERDICT, "verdict": "FAIL"}
    )
    assert ship_mod.ship(root, "c0e5bbc", github=github).can_switch is False


def test_everything_present_can_switch_but_a_look_never_deploys(root: Path) -> None:
    _signoff(root)
    calls: list[Any] = []
    github = FakeGitHub([{"id": 7, "status": "completed", "url": "u"}], PASS_VERDICT)
    report = ship_mod.ship(root, "c0e5bbc", github=github, deploy=lambda *a, **k: calls.append(1))
    assert report.can_switch is True
    assert report.deployed is False and report.result is None and calls == []
    data = report.to_dict()
    assert set(data) == {
        "commit",
        "release_id",
        "active_release",
        "gate",
        "audit",
        "preflight",
        "changes",
        "can_switch",
        "deployed",
        "result",
    }


def test_confirmed_ship_runs_the_deploy_with_the_repo_drill_and_a_card_generated_for_this_release(root: Path) -> None:
    _signoff(root)
    seen: dict[str, Any] = {}

    def fake_deploy(base: Path, report: Any, **kwargs: Any) -> DeployResult:
        seen.update(kwargs)
        return DeployResult(
            release_id=RID, change_id="CHG-SCPT-2026-999", backup="bk", receipt="rc"
        )

    github = FakeGitHub([{"id": 7, "status": "completed", "url": "u"}], PASS_VERDICT)
    report = ship_mod.ship(
        root,
        "c0e5bbc",
        github=github,
        confirm_ref="user-confirmation:board-click:x",
        approver="baiyang",
        deploy=fake_deploy,
    )
    assert report.deployed is True and report.result is not None and report.result["ok"] is True
    assert (
        seen["confirm_ref"] == "user-confirmation:board-click:x" and seen["approver"] == "baiyang"
    )
    assert seen["drill_script"] == root / ship_mod.DRILL_SCRIPT
    # CHG-SCPT-2026-709: no fixed repository card (274 only covered releases/1.3.3-368c1af); the deploy writes this release's own card
    assert "card_file" in seen and seen["card_file"] is None
    assert not hasattr(ship_mod, "PRECHECK_CARD")


def test_confirmation_without_a_green_preflight_never_deploys(root: Path) -> None:
    calls: list[Any] = []
    github = FakeGitHub([{"id": 7, "status": "completed", "url": "u"}], PASS_VERDICT)  # 没签字
    report = ship_mod.ship(
        root,
        "c0e5bbc",
        github=github,
        confirm_ref="user-confirmation:x",
        approver="a",
        deploy=lambda *a, **k: calls.append(1),
    )
    assert calls == []
    assert report.deployed is False and report.result is not None and report.result["ok"] is False


def test_a_rolled_back_deploy_is_reported_as_rolled_back(root: Path) -> None:
    _signoff(root)

    def failing_deploy(*args: Any, **kwargs: Any) -> DeployResult:
        raise DeployError("自检没过", rolled_back=True)

    github = FakeGitHub([{"id": 7, "status": "completed", "url": "u"}], PASS_VERDICT)
    report = ship_mod.ship(
        root,
        "c0e5bbc",
        github=github,
        confirm_ref="user-confirmation:x",
        approver="a",
        deploy=failing_deploy,
    )
    assert report.result is not None
    assert (
        report.result["ok"] is False
        and report.result["rolled_back"] is True
        and "自检没过" in report.result["message"]
    )


def test_the_repo_has_the_drill_script() -> None:
    project = (
        Path(__file__).resolve().parents[2]
    )  # 在本项目目录里，按项目内相对路径找，不读项目外
    prefix = len(Path(check.PROJECT_DIR).parts)
    assert (project / Path(*ship_mod.DRILL_SCRIPT.parts[prefix:])).is_file()


def test_gh_cli_prefers_the_artifact_named_after_the_commit(tmp_path: Path) -> None:
    asked: list[list[str]] = []

    def run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        asked.append(args)
        if args[1:3] == ["run", "download"] and args[5] == f"gate-verdict-{COMMIT[:12]}":
            out = Path(args[args.index("-D") + 1])
            out.mkdir(parents=True)
            (out / "gate_summary.json").write_text(json.dumps(PASS_VERDICT), encoding="utf-8")
            return subprocess.CompletedProcess(args, 0, "", "")
        return subprocess.CompletedProcess(args, 1, "", "not found")

    target = ship_mod.GhCli(tmp_path, run=run).download_verdict(7, COMMIT, tmp_path / "c")
    assert (
        target == tmp_path / "c" / "gate_verdict.json"
        and json.loads(target.read_text(encoding="utf-8"))["verdict"] == "PASS"
    )
    assert [a[5] for a in asked] == [f"gate-verdict-{COMMIT[:12]}"]


def test_a_newer_gate_run_replaces_the_cached_verdict(root: Path) -> None:
    """审计 #857：同一提交第 1 轮 PASS 已缓存，第 2 轮 FAIL 时必须重下，不能拿旧的 PASS 配新的运行号。"""
    _signoff(root)
    first = FakeGitHub([{"id": 7, "status": "completed", "url": "u7"}], PASS_VERDICT)
    assert ship_mod.ship(root, "c0e5bbc", github=first).can_switch is True
    second = FakeGitHub(
        [{"id": 8, "status": "completed", "url": "u8"}], {**PASS_VERDICT, "verdict": "FAIL"}
    )
    report = ship_mod.ship(root, "c0e5bbc", github=second)
    assert second.downloads == [8]
    assert report.gate["state"] == "fail" and report.gate["run_id"] == 8
    assert report.can_switch is False
