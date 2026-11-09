"""D-146 card 4: the deploy sequence and its safety rules, on fake ports (nothing here deploys anything)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from auto_pm.application.core import release_deploy as rd
from auto_pm.application.core.release_deploy_check import FAIL, PASS, Preflight
from auto_pm.application.core.release_ledger import DeployPlan
from tests.core.test_release_ledger import CONFIRM, PATHS, FakeLedger

NEW, OLD = "1.3.3-abcdef0", "1.3.3-1234567"


class FakeOps:
    def __init__(self, *, built: bool = False, switched: bool = False) -> None:
        self.calls: list[str] = []
        self.built = built
        self.active = NEW if switched else OLD
        self.fail_switch = False
        self.fail_rollback = False
        self.rollback_backup: Path | None = None
        self.entry_sha = "f" * 64

    def active_release(self) -> str:
        return self.active

    def is_built(self, release_id: str) -> bool:
        return self.built

    def build(self) -> dict[str, Any]:
        self.calls.append("build")
        self.built = True
        return {"release_id": NEW, "entry_sha256": "e" * 64}

    def switch(self, backup: Path) -> dict[str, Any]:
        self.calls.append("switch")
        if self.fail_switch:
            raise RuntimeError("identity after switch is wrong")
        self.active = NEW
        return {}

    def manifest_entry_sha256(self, release_id: str) -> str:
        return self.entry_sha

    def rollback(self, backup: Path) -> dict[str, Any]:
        self.calls.append("rollback")
        self.rollback_backup = backup
        if self.fail_rollback:
            raise RuntimeError("backup corrupted")
        self.active = OLD
        return {}


def _plan(tmp_path: Path, confirm: str = CONFIRM) -> DeployPlan:
    return DeployPlan(release_id=NEW, old_release=OLD, commit="a" * 40, confirm_ref=confirm, approver="fubai", paths=PATHS,
                      station=tmp_path / "station", evidence_dir=tmp_path / "evidence")


def _green() -> Preflight:
    report = Preflight(commit="a" * 40, release_id=NEW)
    report.add("提交存在", PASS, "ok")
    return report


def _checks(bad: set[str] | None = None, boom: set[str] | None = None, ran: list[str] | None = None) -> dict[str, rd.SelfCheck]:
    def make(name: str) -> rd.SelfCheck:
        def check() -> tuple[bool, str]:
            if ran is not None:
                ran.append(name)
            if boom and name in boom:
                raise RuntimeError("check crashed")
            return (name not in (bad or set()), "ok" if name not in (bad or set()) else "broken")
        return check
    return {name: make(name) for name in rd.REQUIRED_SELF_CHECKS}


def _run(tmp_path: Path, ops: FakeOps, ledger: FakeLedger, *, plan: DeployPlan | None = None, preflight: Preflight | None = None,
         checks: dict[str, rd.SelfCheck] | None = None) -> rd.DeployResult:
    return rd.deploy(plan or _plan(tmp_path), preflight=preflight or _green(), ops=ops, ledger=ledger, checks=checks or _checks(),
                     backup=tmp_path / "backup", rollback_command="main.py release rollback", background="发布", necessity="新版本才生效")


def test_the_required_self_checks_include_the_two_that_the_69b7ed6_deploy_dropped() -> None:
    assert "pre-commit hook dry run" in rd.REQUIRED_SELF_CHECKS and "event chain drill" in rd.REQUIRED_SELF_CHECKS
    assert len(set(rd.REQUIRED_SELF_CHECKS)) == len(rd.REQUIRED_SELF_CHECKS)


def test_a_green_deploy_books_builds_switches_checks_closes_and_writes_the_receipt(tmp_path: Path) -> None:
    ops, ledger = FakeOps(), FakeLedger()

    result = _run(tmp_path, ops, ledger)

    assert ops.calls == ["build", "switch"] and ops.active == NEW
    assert ledger.change_state == "completed" and ledger.run == "SUCCEEDED" and ledger.work == "CLOSED"
    assert result.steps.index("build") < result.steps.index("switch") < result.steps.index("checkpoint create")
    receipt = json.loads(Path(result.receipt).read_text(encoding="utf-8"))
    assert receipt["release"] == NEW and receipt["manifest_entry_sha256"] == "e" * 64 and receipt["rollback_command"]


def test_a_preflight_that_is_not_green_writes_nothing(tmp_path: Path) -> None:
    report = _green()
    report.add("门禁判决", FAIL, "没给")
    ops, ledger = FakeOps(), FakeLedger()

    with pytest.raises(rd.DeployError, match="预检没通过"):
        _run(tmp_path, ops, ledger, preflight=report)

    assert ops.calls == [] and ledger.commands == [] and not (tmp_path / "evidence").exists()


def test_a_self_check_list_with_a_missing_item_is_refused_before_anything_is_written(tmp_path: Path) -> None:
    checks = _checks()
    del checks["event chain drill"]
    ops, ledger = FakeOps(), FakeLedger()

    with pytest.raises(rd.DeployError, match="缺 1 项"):
        _run(tmp_path, ops, ledger, checks=checks)

    assert ops.calls == [] and ledger.commands == []


def test_one_failed_self_check_rolls_back_runs_every_check_and_leaves_the_books_open(tmp_path: Path) -> None:
    ops, ledger = FakeOps(), FakeLedger()
    ran: list[str] = []

    with pytest.raises(rd.DeployError, match="已回退") as caught:
        _run(tmp_path, ops, ledger, checks=_checks(bad={"help claim"}, ran=ran))

    assert caught.value.rolled_back and caught.value.failed == ("help claim",)
    assert ops.calls == ["build", "switch", "rollback"] and ops.active == OLD
    assert ran == list(rd.REQUIRED_SELF_CHECKS), "the failure did not stop the later checks"
    assert ledger.run == "RUNNING" and ledger.change_state == "implementing", "books stay open after a rollback"
    assert not (tmp_path / "evidence" / "receipt.json").exists()


def test_a_self_check_that_crashes_counts_as_failed_and_still_rolls_back(tmp_path: Path) -> None:
    ops, ledger = FakeOps(), FakeLedger()

    with pytest.raises(rd.DeployError) as caught:
        _run(tmp_path, ops, ledger, checks=_checks(boom={"identity"}))

    assert caught.value.rolled_back and "identity" in caught.value.failed and ops.active == OLD


def test_a_switch_that_raises_is_rolled_back(tmp_path: Path) -> None:
    ops, ledger = FakeOps(), FakeLedger()
    ops.fail_switch = True

    with pytest.raises(rd.DeployError, match="切换没成功") as caught:
        _run(tmp_path, ops, ledger)

    assert caught.value.rolled_back and ops.calls == ["build", "switch", "rollback"]


def test_a_rollback_that_fails_is_reported_loudly_with_the_manual_way_out(tmp_path: Path) -> None:
    ops, ledger = FakeOps(), FakeLedger()
    ops.fail_switch = ops.fail_rollback = True

    with pytest.raises(rd.DeployError, match="回退也没成功") as caught:
        _run(tmp_path, ops, ledger)

    assert caught.value.rolled_back is False and str(tmp_path / "backup") in str(caught.value)


def test_after_a_rollback_the_same_confirmation_cannot_be_used_again_but_a_new_one_can(tmp_path: Path) -> None:
    ops, ledger = FakeOps(), FakeLedger()
    with pytest.raises(rd.DeployError, match="已回退"):
        _run(tmp_path, ops, ledger, checks=_checks(bad={"identity"}))
    commands = len(ledger.commands)

    with pytest.raises(rd.DeployError, match="新的确认引用"):
        _run(tmp_path, ops, ledger, checks=_checks())
    assert len(ledger.commands) == commands, "the refusal happens before any ledger write"

    result = _run(tmp_path, ops, ledger, plan=_plan(tmp_path, "user-confirmation:cmsg_test_002"))

    assert ledger.change_state == "completed" and ledger.created == 1, "the retry continues the same books"
    assert result.release_id == NEW


def test_resuming_after_the_switch_does_not_build_or_switch_again(tmp_path: Path) -> None:
    ops, ledger = FakeOps(built=True, switched=True), FakeLedger()

    _run(tmp_path, ops, ledger)

    assert ops.calls == [] and ledger.change_state == "completed"


def test_resuming_when_built_but_not_switched_does_not_build_twice(tmp_path: Path) -> None:
    ops, ledger = FakeOps(built=True), FakeLedger()

    _run(tmp_path, ops, ledger)

    assert ops.calls == ["switch"]


def test_an_already_built_release_still_puts_the_manifest_entry_hash_in_the_receipt(tmp_path: Path) -> None:
    ops, ledger = FakeOps(built=True), FakeLedger()

    result = _run(tmp_path, ops, ledger)

    assert "build" not in ops.calls
    assert json.loads(Path(result.receipt).read_text(encoding="utf-8"))["manifest_entry_sha256"] == "f" * 64


def test_an_unreadable_manifest_entry_hash_is_an_error_not_an_empty_receipt_field(tmp_path: Path) -> None:
    ops, ledger = FakeOps(built=True), FakeLedger()
    ops.entry_sha = ""

    with pytest.raises(rd.DeployError, match="哈希"):
        _run(tmp_path, ops, ledger)

    assert not (tmp_path / "evidence" / "receipt.json").exists()


def test_a_rollback_after_a_resume_uses_the_backup_of_the_first_attempt(tmp_path: Path) -> None:
    ledger = FakeLedger()
    first = tmp_path / "first_backup"
    killed = _checks()

    def die() -> tuple[bool, str]:
        raise KeyboardInterrupt  # the process is killed after the switch, before the checks finish

    killed["identity"] = die
    with pytest.raises(KeyboardInterrupt):
        rd.deploy(_plan(tmp_path), preflight=_green(), ops=FakeOps(), ledger=ledger, checks=killed, backup=first,
                  rollback_command="x", background="发布", necessity="n")
    resumed_ops = FakeOps(switched=True, built=True)

    with pytest.raises(rd.DeployError, match="已回退"):
        rd.deploy(_plan(tmp_path), preflight=_green(), ops=resumed_ops, ledger=ledger, checks=_checks(bad={"identity"}),
                  backup=tmp_path / "second_backup", rollback_command="x", background="发布", necessity="n")

    assert resumed_ops.rollback_backup == first, "the pointers must go back to how they were before the deploy, not before the retry"
    assert json.loads((tmp_path / "evidence" / "state.json").read_text(encoding="utf-8"))["backup"] == ""  # cleared once the rollback succeeded


def test_after_a_successful_rollback_the_recorded_backup_is_cleared_so_the_next_attempt_takes_a_fresh_one(tmp_path: Path) -> None:
    ops, ledger = FakeOps(), FakeLedger()

    with pytest.raises(rd.DeployError, match="已回退"):
        _run(tmp_path, ops, ledger, checks=_checks(bad={"identity"}))

    state = json.loads((tmp_path / "evidence" / "state.json").read_text(encoding="utf-8"))
    assert state["backup"] == "" and state["rolled_back_with"] == CONFIRM
