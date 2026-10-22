"""Unit cases for the user's approval PIN (gap 9): only a committed verifier counts, only the right PIN approves."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from auto_pm.application.core.approval_proof_service import (
    REGISTRY_RELATIVE_PATH,
    ApprovalProofError,
    ApprovalProofService,
    make_key,
    pin_problem,
)
from auto_pm.domain.change.decision_service import DecisionService
from auto_pm.ui.cli import approval_pin as cli_module

PIN = "relay-K1-on"
PLAN = "a" * 64


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(["git", "-C", str(root), *arguments], check=True, capture_output=True)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    repository = tmp_path / "ws"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.name", "t")
    _git(repository, "config", "user.email", "t@example.invalid")
    (repository / "README.md").write_text("x", encoding="utf-8")
    _git(repository, "add", "README.md")
    _git(repository, "commit", "-q", "-m", "base")
    return repository


def _commit_pin(root: Path, pin: str = PIN, approver: str = "baiyang") -> ApprovalProofService:
    service = ApprovalProofService(root)
    service.write_working_keys([make_key(approver, pin, n=2**10)])
    _git(root, "add", REGISTRY_RELATIVE_PATH)
    _git(root, "commit", "-q", "-m", "pin")
    return service


def test_without_a_committed_verifier_the_old_format_check_applies(root: Path) -> None:
    service = ApprovalProofService(root)
    assert service.committed_keys() is None
    assert service.resolve(pin="", approver="someone", evidence_ref="user-confirmation:x-12345678", purpose="p", subject="s") == (
        "someone",
        "user-confirmation:x-12345678",
    )
    # Written but not committed: approvals stop until the user commits it (audit 72: never fall back silently).
    service.write_working_keys([make_key("baiyang", PIN, n=2**10)])
    with pytest.raises(ApprovalProofError, match="还没提交"):
        service.require(pin="", purpose="p", subject="s")
    assert service.committed_state()[0] is None


def test_a_root_that_is_not_a_git_working_tree_keeps_the_old_check(tmp_path: Path) -> None:
    assert ApprovalProofService(tmp_path).committed_keys() is None


def test_unreadable_committed_state_refuses_instead_of_falling_back(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Audit 72 high-1: GIT_DIR, no git on PATH and a HEAD that points nowhere used to switch the PIN off."""

    service = _commit_pin(root)
    elsewhere = root.parent / "empty-git-dir"
    elsewhere.mkdir()
    for name, value in (("GIT_DIR", str(elsewhere)), ("GIT_WORK_TREE", str(elsewhere)), ("GIT_CEILING_DIRECTORIES", str(root.parent))):
        monkeypatch.setenv(name, value)
    assert service.enforced(), "继承来的 GIT_* 变量不能把口令关掉"
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_CEILING_DIRECTORIES"):
        monkeypatch.delenv(name)
    monkeypatch.setenv("PATH", str(elsewhere))
    with pytest.raises(ApprovalProofError, match="一律拒绝"):
        service.resolve(pin="", approver="baiyang", evidence_ref="user-confirmation:fake-12345678", purpose="p", subject="s")
    monkeypatch.undo()
    _git(root, "symbolic-ref", "HEAD", "refs/heads/nothing-here")
    with pytest.raises(ApprovalProofError, match="HEAD 不指向任何提交"):
        service.resolve(pin="", approver="baiyang", evidence_ref="user-confirmation:fake-12345678", purpose="p", subject="s")


def test_once_switched_on_the_pin_cannot_be_switched_off_by_a_commit(root: Path) -> None:
    service = _commit_pin(root)
    _git(root, "rm", "-q", REGISTRY_RELATIVE_PATH)
    _git(root, "commit", "-q", "-m", "drop the pin")
    with pytest.raises(ApprovalProofError, match="曾经启用过"):
        service.resolve(pin="", approver="baiyang", evidence_ref="user-confirmation:fake-12345678", purpose="p", subject="s")
    # Another repository inside the root does not count either.
    inner = ApprovalProofService(root / "SYS-2026-001_WorkspaceGovernance")
    assert inner.committed_state()[0] is None


def test_a_committed_verifier_needs_the_pin_and_the_approver_comes_from_it(root: Path) -> None:
    service = _commit_pin(root)
    with pytest.raises(ApprovalProofError, match="不得索要或代填口令"):
        service.resolve(pin="", approver="baiyang", evidence_ref="user-confirmation:chat-12345678", purpose="approve-scope", subject=PLAN)
    with pytest.raises(ApprovalProofError, match="批准口令错误"):
        service.resolve(pin="baiyang2026", approver="baiyang", evidence_ref="", purpose="approve-scope", subject=PLAN)
    approver, evidence = service.resolve(pin=PIN, approver="", evidence_ref="user-confirmation:chat-x", purpose="approve-scope", subject=PLAN)
    assert approver == "baiyang"
    assert evidence.startswith("user-confirmation:pin-") and "chat" not in evidence
    # The reference passes the existing format gate unchanged and is stable for a retry of the same card.
    DecisionService.validate_planning_approval(approver, PLAN, evidence)
    assert service.resolve(pin=PIN, approver="baiyang", evidence_ref="", purpose="approve-scope", subject=PLAN)[1] == evidence
    with pytest.raises(ApprovalProofError, match="不一致"):
        service.resolve(pin=PIN, approver="someone-else", evidence_ref="", purpose="approve-scope", subject=PLAN)


def test_the_working_tree_file_does_not_count_once_a_verifier_is_committed(root: Path) -> None:
    service = _commit_pin(root)
    service.write_working_keys([make_key("baiyang", "agent-pin-1", n=2**10)])
    with pytest.raises(ApprovalProofError, match="批准口令错误"):
        service.attest("agent-pin-1", purpose="p", subject="s")
    assert service.attest(PIN, purpose="p", subject="s").approver == "baiyang"
    (root / REGISTRY_RELATIVE_PATH).unlink()
    assert service.enforced(), "删掉工作区文件不能关掉批准口令"


def test_five_wrong_pins_lock_and_the_lock_expires(root: Path) -> None:
    service = _commit_pin(root)
    now = datetime(2026, 10, 22, 8, 0, tzinfo=UTC)
    for _ in range(4):
        with pytest.raises(ApprovalProofError, match="再错"):
            service.attest("wrong-pin-0", purpose="p", subject="s", now=now)
    with pytest.raises(ApprovalProofError, match="锁定 15 分钟"):
        service.attest("wrong-pin-0", purpose="p", subject="s", now=now)
    with pytest.raises(ApprovalProofError, match="锁定到"):
        service.attest(PIN, purpose="p", subject="s", now=now + timedelta(minutes=14))
    assert service.attest(PIN, purpose="p", subject="s", now=now + timedelta(minutes=16)).approver == "baiyang"
    # A success clears the count.
    with pytest.raises(ApprovalProofError, match="再错 4 次"):
        service.attest("wrong-pin-0", purpose="p", subject="s", now=now + timedelta(minutes=17))


def test_a_broken_committed_registry_refuses_every_approval(root: Path) -> None:
    (root / REGISTRY_RELATIVE_PATH).parent.mkdir(parents=True)
    (root / REGISTRY_RELATIVE_PATH).write_text('{"schema_version": "approvers.v1", "approvers": []}', encoding="utf-8")
    _git(root, "add", REGISTRY_RELATIVE_PATH)
    _git(root, "commit", "-q", "-m", "empty")
    with pytest.raises(ApprovalProofError, match="一律拒绝"):
        ApprovalProofService(root).resolve(pin="", approver="someone", evidence_ref="user-confirmation:x-12345678", purpose="p", subject="s")


@pytest.mark.parametrize(
    ("pin", "ok"), [("short1a", False), ("relay-K1o", False), ("12345678901", False), (" spaced-pin ", False), ("relay-K1-on", True)]
)
def test_pin_strength(pin: str, ok: bool) -> None:
    assert (pin_problem(pin) == "") is ok


def test_the_key_keeps_no_pin(root: Path) -> None:
    key = make_key("baiyang", PIN, n=2**10)
    assert PIN not in str(key.to_json())
    assert len(key.key_id) == 12


# ---------------------------------------------------------------- command line
class _Obj:
    def __init__(self, root: Path) -> None:
        self.workspace_root = str(root)
        self.control_root = str(root)


@click.command()
@click.pass_context
def _probe(ctx: click.Context) -> None:
    click.echo("pin=" + cli_module.read_approval_pin(ctx.obj.control_root, summary="summary"))


def test_cli_prompt_only_when_enforced_and_only_in_a_terminal(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    assert runner.invoke(_probe, obj=_Obj(root)).output.strip() == "pin="
    _commit_pin(root)
    monkeypatch.setattr(cli_module, "_stdin_is_tty", lambda: False)
    refused = runner.invoke(_probe, obj=_Obj(root))
    assert refused.exit_code != 0 and "当前不是交互终端" in refused.output
    monkeypatch.setattr(cli_module, "_stdin_is_tty", lambda: True)
    monkeypatch.setattr(cli_module, "_prompt_hidden", lambda text: "typed-pin")
    assert "pin=typed-pin" in runner.invoke(_probe, obj=_Obj(root)).output


def test_cli_init_is_refused_for_agents_and_rotation_needs_the_old_pin(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    for name in ("AUTO_PM_AGENT", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CODEX_SANDBOX", "CODEX_SANDBOX_NETWORK_DISABLED", "CODEX_THREAD_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AUTO_PM_AGENT", "trae")
    refused = runner.invoke(cli_module.approver_pin_init, ["--approver", "baiyang"], obj=_Obj(root))
    assert refused.exit_code != 0 and "agent 会话" in refused.output
    monkeypatch.delenv("AUTO_PM_AGENT")
    monkeypatch.setattr(cli_module, "_stdin_is_tty", lambda: True)
    _commit_pin(root)
    answers = iter(["wrong-old-pin", "new-pin-123", "new-pin-123"])
    monkeypatch.setattr(cli_module, "_prompt_hidden", lambda text: next(answers))
    rotated = runner.invoke(cli_module.approver_pin_init, ["--approver", "baiyang"], obj=_Obj(root))
    assert rotated.exit_code != 0 and "批准口令错误" in rotated.output
    answers = iter([PIN, "new-pin-123", "new-pin-123"])
    rotated = runner.invoke(cli_module.approver_pin_init, ["--approver", "baiyang"], obj=_Obj(root))
    assert rotated.exit_code == 0, rotated.output
    assert "提交" in rotated.output
    # Not committed yet: the old PIN still approves, the new one does not.
    service = ApprovalProofService(root)
    assert service.attest(PIN, purpose="p", subject="s").approver == "baiyang"
    assert [key.approver for key in service.working_keys()] == ["baiyang"]


# ---------------------------------------------------------------- the generic state commands are no side doors (audit 72)
def test_mission_acceptance_needs_the_facade_evidence(tmp_path: Path) -> None:
    from auto_pm.application.core.mission_service import MissionService, MissionServiceError
    from auto_pm.contracts.mission import MissionState

    class _Store:
        def get_mission(self, mission_id: str) -> object:
            return type("M", (), {"state": MissionState.ACCEPTANCE_PENDING})()

    service = MissionService(tmp_path, store=_Store())  # type: ignore[arg-type]
    with pytest.raises(MissionServiceError, match="pm accept"):
        service.transition(
            mission_id="MISSION-X", expected_version=3, new_state=MissionState.ACCEPTED, root_work_id=None, idempotency_key="k"
        )


def test_work_ready_needs_authorize(root: Path) -> None:
    from auto_pm.application.core.work_registry_service import (
        WorkRegistryError,
        WorkRegistryService,
    )
    from auto_pm.contracts.continuity import WorkKind, WorkState

    works = WorkRegistryService(root)
    works.initialize("test")
    works.create_work(
        work_id="WORK-X-1", subject_project_id="DJ-2026-005", kind=WorkKind.WBS, title="t", owner="o",
        scope_paths=["a.txt"], source_fingerprint="f", idempotency_key="create",
    )
    with pytest.raises(WorkRegistryError, match="work authorize"):
        works.transition("WORK-X-1", WorkState.READY, "ready")
