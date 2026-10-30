"""CLI wiring of the M3-HANDOFF card: token sources (TD-SW008-064), the local wallet, pm handoff / takeover (TD-SW008-063), the reclaim
command and the user-only pm sign-risk (V04-R1 storage acceptance case 3).  The decision logic itself is covered in
tests/core/test_lease_handover_service.py; here every command is driven through the real click tree."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner, Result

import auto_pm.ui.cli.pm_handoff as pm_handoff_cli
from auto_pm.application.core.lease_handover_service import AGENT_MARKERS
from auto_pm.application.core.pm_facade_service import PmFacadeError, PmFacadeService
from auto_pm.application.core.work_registry_service import WorkRegistryService
from auto_pm.contracts.continuity import WorkKind
from auto_pm.infrastructure import lease_wallet
from auto_pm.infrastructure.continuity_store import ContinuityStore
from auto_pm.ui.cli.__main__ import cli
from tests.git_support import git_do

pytestmark = pytest.mark.usefixtures("identity_guard_off")

RUN = "RUN-HO-001"
WORK = "WORK-HO-001"


def _git(root: Path, *args: str) -> None:
    git_do(root, *args)


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in AGENT_MARKERS:  # the test itself may run inside an agent session
        monkeypatch.delenv(name, raising=False)
    _git(tmp_path, "init")
    (tmp_path / "README.md").write_text("baseline\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text(".auto-pm/\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md", ".gitignore")
    _git(tmp_path, "-c", "user.name=T", "-c", "user.email=t@example.invalid", "commit", "-m", "baseline")
    works = WorkRegistryService(tmp_path)
    works.initialize("test")
    works.create_work(
        work_id=WORK, subject_project_id="SW-TEST-001", kind=WorkKind.GOVERNANCE, title="handoff", owner="architect",
        scope_paths=["README.md"], source_fingerprint="sha256:ho", idempotency_key="ho-work", read_only=True,
    )
    return tmp_path


def _invoke(root: Path, *args: str, env: dict[str, str] | None = None, input_text: str | None = None) -> Result:
    return CliRunner().invoke(cli, ["-w", str(root), *args], env=env, input=input_text, catch_exceptions=False)


def _start(root: Path, owner: str = "agent-a", run_id: str = RUN, key: str = "start-1") -> Result:
    return _invoke(
        root, "continuity", "run", "start", "--run-id", run_id, "--work-id", WORK, "--executor", owner, "--adapter", "codex",
        "--owned", "README.md", "--declared-dirty", "README.md", "--lease-wallet", "--holder-pid", "none", "--idempotency-key", key,
    )


def _expire(root: Path) -> None:
    """The clock moved on (test-only): the lease ended an hour ago, well past the 120 s grace."""

    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn, conn:
        conn.execute("UPDATE execution_leases SET expires_at=? WHERE run_id=?", (past, RUN))


def test_run_start_with_the_wallet_never_shows_the_token_and_a_retry_replays(root: Path) -> None:
    first = _start(root)
    assert first.exit_code == 0, first.output
    token = lease_wallet.load(root, run_id=RUN, owner_id="agent-a")
    assert token and token not in first.output
    assert ContinuityStore(root).get_lease(RUN).lease_token == token

    again = _start(root)
    assert again.exit_code == 0, again.output
    assert lease_wallet.load(root, run_id=RUN, owner_id="agent-a") == token


def test_writes_take_the_token_from_the_wallet_or_an_environment_variable_and_exactly_one_source(root: Path) -> None:
    assert _start(root).exit_code == 0
    token = lease_wallet.load(root, run_id=RUN, owner_id="agent-a")

    running = _invoke(root, "continuity", "run", "transition", "--run-id", RUN, "--to", "RUNNING", "--owner", "agent-a", "--lease-wallet", "--idempotency-key", "t1")
    assert running.exit_code == 0, running.output
    renewed = _invoke(
        root, "continuity", "lease", "renew", "--run-id", RUN, "--owner", "agent-a", "--lease-token-env", "HO_TOKEN",
        "--expected-version", str(ContinuityStore(root).get_lease(RUN).version), "--idempotency-key", "r1", env={"HO_TOKEN": token},
    )
    assert renewed.exit_code == 0, renewed.output
    assert token not in running.output + renewed.output

    both = _invoke(
        root, "continuity", "run", "transition", "--run-id", RUN, "--to", "VERIFYING", "--owner", "agent-a", "--lease-wallet",
        "--lease-token-env", "HO_TOKEN", "--idempotency-key", "t2", env={"HO_TOKEN": token},
    )
    none = _invoke(root, "continuity", "run", "transition", "--run-id", RUN, "--to", "VERIFYING", "--owner", "agent-a", "--idempotency-key", "t3")
    assert both.exit_code == 2 and none.exit_code == 2
    assert "必须且只能给出一个口令来源" in both.output + none.output
    stranger = _invoke(root, "continuity", "run", "transition", "--run-id", RUN, "--to", "VERIFYING", "--owner", "agent-b", "--lease-wallet", "--idempotency-key", "t4")
    assert stranger.exit_code == 1 and "不属于 agent-b" in stranger.output


@pytest.mark.parametrize(
    ("path", "env_option"),
    [
        (("run", "start"), "--lease-token-env"),
        (("run", "transition"), "--lease-token-env"),
        (("run", "settle-expired"), "--recovery-lease-token-env"),
        (("dispatch", "prepare"), "--lease-token-env"),
        (("checkpoint", "create"), "--lease-token-env"),
        (("handoff", "create"), "--lease-token-env"),
        (("handoff", "accept"), "--new-lease-token-env"),
        (("lease", "renew"), "--lease-token-env"),
    ],
)
def test_every_command_that_carries_a_token_accepts_it_from_the_environment(path: tuple[str, ...], env_option: str) -> None:
    command: Any = cli  # click 的 Command 没有 .commands，逐层往下取子命令
    for name in ("continuity", *path):
        command = command.commands[name]
    options = {option for parameter in command.params for option in parameter.opts}
    assert env_option in options
    for parameter in command.params:
        if any(option.endswith("lease-token") for option in parameter.opts):
            assert not parameter.required, f"{path}: the argv token option must be optional (deprecated)"


def test_pm_handoff_then_pm_takeover_moves_the_run_without_anyone_copying_a_token(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Orient:
        evidence_id = "CTX-TEST"
        next_legal_action = "continue"
        conflicts: tuple[str, ...] = ()
        work = None
        run = None

        class context:  # noqa: N801 - mirrors the attribute shape of the real payload
            subject_project_id = "SW-TEST-001"

    seen: list[dict[str, object]] = []

    def orient(self: object, **kwargs: object) -> Orient:
        seen.append(kwargs)
        return Orient()

    monkeypatch.setattr(PmFacadeService, "orient", orient)
    assert _start(root).exit_code == 0
    old_token = lease_wallet.load(root, run_id=RUN, owner_id="agent-a")

    handed = _invoke(root, "pm", "handoff", "--run-id", RUN, "--to", "agent-b", "--summary", "halfway")
    assert handed.exit_code == 0, handed.output
    payload = json.loads(handed.output)
    assert payload["from_owner"] == "agent-a" and payload["to_owner"] == "agent-b"
    assert payload["next_command"] == f"main.py pm takeover --handoff-id {payload['handoff_id']} --as agent-b"

    wrong = _invoke(root, "pm", "takeover", "--handoff-id", payload["handoff_id"], "--as", "agent-c", "--holder-pid", "none")
    assert wrong.exit_code == 1 and "接收方" in wrong.output
    taken = _invoke(root, "pm", "takeover", "--handoff-id", payload["handoff_id"], "--as", "agent-b", "--holder-pid", "none")
    assert taken.exit_code == 0, taken.output
    result = json.loads(taken.output)
    assert result["owner_id"] == "agent-b" and result["epoch"] >= 2 and result["orient"]["evidence_id"] == "CTX-TEST"
    assert seen and seen[-1]["run_id"] == RUN and seen[-1]["work_id"] == WORK  # the receiver oriented itself on exactly this Run first
    new_token = lease_wallet.load(root, run_id=RUN, owner_id="agent-b")
    assert new_token != old_token and old_token not in taken.output and new_token not in taken.output

    late = _invoke(root, "continuity", "run", "transition", "--run-id", RUN, "--to", "RUNNING", "--owner", "agent-a", "--lease-token-env", "OLD", "--idempotency-key", "late", env={"OLD": old_token})
    assert late.exit_code == 1 and "lease ownership 不匹配" in late.output and "agent-b" in late.output


def test_takeover_is_refused_when_the_receiver_cannot_orient_itself_first(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(self: object, **kwargs: object) -> object:
        raise PmFacadeError("registry unreadable")

    monkeypatch.setattr(PmFacadeService, "orient", broken)
    assert _start(root).exit_code == 0
    handed = json.loads(_invoke(root, "pm", "handoff", "--run-id", RUN, "--to", "agent-b").output)

    refused = _invoke(root, "pm", "takeover", "--handoff-id", handed["handoff_id"], "--as", "agent-b", "--holder-pid", "none")

    assert refused.exit_code == 1 and "未接手" in refused.output
    assert ContinuityStore(root).get_lease(RUN).owner_id == "agent-a"


def test_reclaim_command_refuses_a_live_lease_then_waits_for_the_user_then_takes_over(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _start(root).exit_code == 0
    reclaim = ("continuity", "run", "reclaim", "--run-id", RUN, "--claimant", "agent-b", "--reason", "power loss", "--holder-pid", "none")

    live = _invoke(root, *reclaim)
    assert live.exit_code == 1 and json.loads(live.output)["decision"] == "REFUSE_LIVE_LEASE"

    _expire(root)
    pending = _invoke(root, *reclaim)
    assert pending.exit_code == 3, pending.output
    assert json.loads(pending.output)["decision"] == "PENDING" and "pm sign-risk" in json.loads(pending.output)["exit_path"]

    agent = _invoke(root, "pm", "sign-risk", "--run-id", RUN, "--claimant", "agent-b", env={"CLAUDECODE": "1"}, input_text=f"{RUN}\n接受风险\n")
    piped = _invoke(root, "pm", "sign-risk", "--run-id", RUN, "--claimant", "agent-b", input_text=f"{RUN}\n接受风险\n")
    assert agent.exit_code == 1 and "agent 不能签署" in agent.output
    assert piped.exit_code == 1 and "交互式终端" in piped.output
    assert _invoke(root, *reclaim).exit_code == 3  # still pending: nothing was signed

    monkeypatch.setattr(pm_handoff_cli, "_stdin_is_tty", lambda: True)
    monkeypatch.setattr(pm_handoff_cli, "_stdout_is_tty", lambda: True)
    mistyped = _invoke(root, "pm", "sign-risk", "--run-id", RUN, "--claimant", "agent-b", input_text=f"{RUN}\n同意\n")
    assert mistyped.exit_code == 1 and "未签署" in mistyped.output
    # 提示要把两次输入各要什么写明白，输错时说清楚输入了什么、应当是什么、怎么重来（对比测试：第一次要整串 Run 编号，易输错）
    assert f"第 1 次：把上面“Run”后面那一整串编号原样输入，即 {RUN}" in mistyped.output
    assert "第 2 次：输入这四个字：接受风险" in mistyped.output
    assert "你输入的是“同意”，应当是这四个字：接受风险" in mistyped.output and "重新运行同一条命令" in mistyped.output
    wrong_run = _invoke(root, "pm", "sign-risk", "--run-id", RUN, "--claimant", "agent-b", input_text="agent-b\n接受风险\n")
    assert wrong_run.exit_code == 1 and f"应当是“{RUN}”" in wrong_run.output and "你输入的是“agent-b”" in wrong_run.output
    same_name = _invoke(root, "pm", "sign-risk", "--run-id", RUN, "--claimant", "agent-a", input_text=f"{RUN}\n同意\n")
    assert "与当前持有者同名，回收会被拒" in same_name.output and "换一个新名字" in same_name.output
    assert "同名" not in mistyped.output  # 申请人和持有者不同名时不提醒
    signed = _invoke(root, "pm", "sign-risk", "--run-id", RUN, "--claimant", "agent-b", input_text=f"{RUN}\n接受风险\n")
    assert signed.exit_code == 0, signed.output
    assert '"signature_id": "RISK-' in signed.output

    taken = _invoke(root, *reclaim)
    assert taken.exit_code == 0, taken.output
    outcome = json.loads(taken.output)
    assert outcome["decision"] == "ALLOW" and outcome["owner_id"] == "agent-b" and outcome["process_verdict"] == "UNKNOWN"
    assert lease_wallet.load(root, run_id=RUN, owner_id="agent-b") not in taken.output


@pytest.mark.parametrize(
    ("typed", "why"),
    [
        ("agent-b\n接受风险\n", "第 1 次输了申请人名字，不是 Run 编号"),
        (f"{RUN[:-2]}\n接受风险\n", "第 1 次只输了 Run 编号的一部分"),
        ("\n接受风险\n", "第 1 次直接回车"),
        (f"{RUN}\n同意\n", "第 2 次输了别的词"),
        (f"{RUN}\n接受\n", "第 2 次只输了两个字"),
        (f"{RUN}\n\n", "第 2 次直接回车"),
        (f"接受风险\n{RUN}\n", "两次顺序输反"),
        (f"{RUN}x\n接受风险\n", "第 1 次 Run 编号后面多输了一个字"),
        (f"{RUN}0\n接受风险\n", "第 1 次 Run 编号后面多输了一个数字"),
        (f"{RUN}\n接受风险吧\n", "第 2 次后面多输了一个字"),
        (f"{RUN}\n接受风险!\n", "第 2 次后面多输了一个符号"),
    ],
)
def test_sign_risk_with_a_wrong_input_signs_nothing_and_the_reclaim_stays_pending(
    root: Path, monkeypatch: pytest.MonkeyPatch, typed: str, why: str
) -> None:
    """两次输入里任何一次不对都不能签：不写风险签字事件，回收仍卡在 PENDING（预审 428 P3：这两道校验原先没有反例测试）。"""
    import sqlite3
    from contextlib import closing

    assert _start(root).exit_code == 0
    _expire(root)
    reclaim = ("continuity", "run", "reclaim", "--run-id", RUN, "--claimant", "agent-b", "--reason", "power loss", "--holder-pid", "none")
    assert _invoke(root, *reclaim).exit_code == 3
    monkeypatch.setattr(pm_handoff_cli, "_stdin_is_tty", lambda: True)
    monkeypatch.setattr(pm_handoff_cli, "_stdout_is_tty", lambda: True)

    refused = _invoke(root, "pm", "sign-risk", "--run-id", RUN, "--claimant", "agent-b", input_text=typed)

    assert refused.exit_code == 1 and "未签署" in refused.output, why
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn:
        signed = conn.execute("SELECT COUNT(*) FROM events WHERE event_type='RECLAIM_RISK_ACCEPTED'").fetchone()[0]
    assert signed == 0, why
    assert _invoke(root, *reclaim).exit_code == 3, why  # 仍然等用户签字


def test_record_holder_records_an_explicit_live_process(root: Path) -> None:
    import os

    assert _start(root).exit_code == 0
    recorded = _invoke(root, "continuity", "lease", "record-holder", "--run-id", RUN, "--owner", "agent-a", "--lease-wallet", "--holder-pid", str(os.getpid()), "--idempotency-key", "h1")

    assert recorded.exit_code == 0, recorded.output
    fingerprint = ContinuityStore(root).holder_process(RUN)
    assert fingerprint is not None and fingerprint.pid == os.getpid()


def test_the_database_and_the_wallet_are_never_tracked_by_git() -> None:
    """TD-SW008-065 (minimal subset): the plain-text token lives only in two git-ignored local files of the control root."""

    here = Path(__file__).resolve().parent
    top = subprocess.run(["git", "-C", str(here), "rev-parse", "--show-toplevel"], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if top.returncode != 0:
        pytest.skip("not inside a git checkout")
    repository = Path(top.stdout.strip())
    for path in (".auto-pm/continuity.db", f"{lease_wallet.WALLET_DIR.as_posix()}/RUN-ANY.json"):
        ignored = subprocess.run(["git", "-C", str(repository), "check-ignore", "-q", path], check=False)
        assert ignored.returncode == 0, f"{path} is not git-ignored"
