"""Sample-part commissioning drill (样件联调): one PLC Mission driven from inbox to a clean ledger through real child processes.

The unit suites prove each closure stage with hand-made state.  This drill joins the stages the way an IDE agent does in the
field (D08): every step is a separate real process running the real ``pm`` / ``ledger`` commands, or the same facade and
cockpit calls that the thin SDK and the GUI make.  Only the coding agent is a stand-in: a fake ``codex`` on ``PATH`` writes
the requirement bytes.  The core invariant is the one D08 broke: once a Mission has been accepted, ``close_accepted`` must
finish it in one step.  Variants feed field-shaped input (declaration order, Chinese names, Windows separators, letter case,
one or many files, back-to-back and side-by-side Missions).
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import auto_pm
from tests.e2e.test_pmf_plc import (
    BLOCK,
    BLOCK_ANCHOR,
    PROJECT,
    PROJECT_ID,
    STRUCT,
    VAR_DOC,
    benchmark_tar,  # noqa: F401 - module fixture re-used by name
    build_workspace,
    git,
    requirement_files,
)

APPROVER = "fubai"
SECOND_ID = "DJ-2026-905"
SECOND = "0100_PLC自动化/DJ-2026-905"
NEW_NOTE = f"{PROJECT}/02_PLC程序/程序文档/蜂鸣器说明.md"
LEGACY_LAYOUT_DEFECT = (
    "缺陷④：项目已有旧目录 11_监控/…/CHG-<领域>/ 时，plan 把变更单写进 11_监控，而批准签发 Decision 只到 04_监控 找，"
    "pm approve 报“未找到指定项目的 Planning CHG 真源”。已由分支 claude/d09-onboarding-blockers 的 N2（15a481dd）修好"
    "（样件联调在合并后全绿），D09 后合并；合并后本用例转 XPASS，届时去掉 xfail"
)
# The benchmark (like DJ-2026-005/009 in the field) already holds 11_监控/…/CHG-PLC/, which defect ④ trips over; the
# main line files under a domain with no old folder so the rest of the chain can be exercised.  d00 keeps the PLC domain.
MAIN_DOMAIN = "ELEC"
SAME_NUMBER_DEFECT = (
    "缺陷⑤（样件联调新发现，技术债候选，未开卡）：变更单编号只在项目内唯一，但 Continuity Store 的 planning_draft_chg_bindings.change_id 全库 UNIQUE；"
    "另一个项目用过同号（如 CHG-ELEC-2026-001）后，本项目 pm plan 报“候选 CHG 已绑定其他 PlanningDraft”"
)
WAITING_FOR_CARD_179 = (
    "缺陷③（卡 179 修复中）：C05 用有序列表比较 checkpoint.dirty_paths 与 run.declared_dirty_paths，"
    "证据按字典序落库，登记顺序不是字典序时收口永远被拒"
)

LAUNCHER = """from auto_pm.cli.__main__ import cli

if __name__ == "__main__":
    cli()
"""

# The fake coding agent: speaks the handshake, writes the bytes listed in $DRILL_AGENT_FILES under ``-C`` and exits.
FAKE_CODEX = """\
import json, os, pathlib, sys
repo = pathlib.Path(sys.argv[sys.argv.index('-C') + 1])
print(json.dumps({'type': 'thread.started', 'thread_id': 'thread-drill'}), flush=True)
files = json.loads(pathlib.Path(os.environ['DRILL_AGENT_FILES']).read_text(encoding='utf-8'))
for relative, text in files.items():
    target = repo / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding='utf-8', newline='\\n')
"""

# The SDK / GUI side, in its own process: the same facade call ``CockpitClient.run`` makes and the same
# ``PmCockpitService.close_accepted`` that ``CockpitClient.close`` and the cockpit button make.
SDK_STEP = """\
import json, logging, os, secrets, sys
from pathlib import Path
logging.basicConfig(level=logging.WARNING, stream=sys.stderr, format='%(levelname)s %(name)s: %(message)s')
from auto_pm.contracts.pm_facade import PlanningScopeCard
from auto_pm.core.pm_facade_service import PmFacadeService
from auto_pm.core.pm_cockpit_service import PmCockpitService
action, root, card_file = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
card = PlanningScopeCard.model_validate_json(card_file.read_text(encoding='utf-8'))
facade = PmFacadeService(root)
mission_id = facade.materialize_planning_mission(card).mission_id
if action == 'run':
    outcome = facade.run_approved_planning(
        card, expected_plan_hash=card.plan_hash, lease_token=os.environ.get('DRILL_LEASE_TOKEN') or secrets.token_urlsafe(32),
        lease_token_environment='AUTO_PM_EXECUTION_LEASE_TOKEN',
    )
    print(json.dumps({'mission_id': mission_id, 'verified': outcome.verified, 'run_id': outcome.run_id,
                      'checkpoint_id': outcome.checkpoint_id, 'mission_state': outcome.mission_state.value}, ensure_ascii=False))
elif action == 'prepare':
    # A close attempt that stopped after C05, as happened in D08 track 1 (prepared 21:30, never completed).
    from auto_pm.core.pm_closure_service import PmClosureService
    from auto_pm.core.pm_cockpit_service import _CLOSE_PREPARE_KEY
    preparation = PmClosureService(root).prepare_closure(mission_id, idempotency_key=_CLOSE_PREPARE_KEY + mission_id)
    print(json.dumps({'mission_id': mission_id, 'closure_id': preparation.closure.closure_id}, ensure_ascii=False))
elif action == 'close':
    completion = PmCockpitService(root).close_accepted(mission_id)
    print(json.dumps({'mission_id': mission_id, 'state': completion.state.value, 'message': completion.message}, ensure_ascii=False))
"""


@dataclass
class Step:
    name: str
    returncode: int
    stdout: str
    stderr: str

    def json(self) -> dict[str, Any]:
        payload: dict[str, Any] = json.loads(self.stdout)
        return payload


@dataclass
class Drill:
    """One throw-away workspace plus the log of every real process the drill ran."""

    root: Path
    tools: Path
    log: list[Step] = field(default_factory=list)

    def _env(self) -> dict[str, str]:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(Path(auto_pm.__file__).resolve().parent.parent)
        environment["PYTHONIOENCODING"] = "utf-8"
        environment["PATH"] = str(self.tools) + os.pathsep + str(Path(sys.executable).parent) + os.pathsep + environment.get("PATH", "")
        return environment

    def _call(self, name: str, command: list[str], environment: dict[str, str] | None = None) -> Step:
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", errors="replace", env=environment or self._env(), timeout=600
        )
        step = Step(name, result.returncode, result.stdout, result.stderr)
        self.log.append(step)
        return step

    def cli(self, *arguments: str) -> Step:
        return self._call(" ".join(arguments[:2]), [sys.executable, str(self.tools / "launcher.py"), "-w", str(self.root), *arguments])

    def sdk(
        self, action: str, card: dict[str, Any], agent_files: dict[str, str] | None = None, lease_token: str = ""
    ) -> Step:
        card_file = self.tools / f"card-{card['request_id']}.json"
        card_file.write_text(json.dumps(card, ensure_ascii=False), encoding="utf-8")
        environment = self._env()
        if agent_files is not None:
            files_path = self.tools / f"agent-{card['request_id']}.json"
            files_path.write_text(json.dumps(agent_files, ensure_ascii=False), encoding="utf-8")
            environment["DRILL_AGENT_FILES"] = str(files_path)
        if lease_token:
            environment["DRILL_LEASE_TOKEN"] = lease_token
        return self._call(f"sdk {action}", [sys.executable, str(self.tools / "sdk_step.py"), action, str(self.root), str(card_file)], environment)

    def transcript(self) -> str:
        lines = []
        for step in self.log:
            lines.append(f"$ {step.name} -> {step.returncode}")
            lines.extend(f"  {line}" for line in (step.stdout + step.stderr).strip().splitlines()[-12:])
        return "\n".join(lines)


@dataclass
class MissionResult:
    """How far one Mission got; ``stage`` is the last stage that succeeded."""

    stage: str
    mission_id: str = ""
    change_id: str = ""
    refusal: str = ""


def make_drill(tmp_path: Path, benchmark: bytes, *, second_project: bool = False) -> Drill:
    root = (tmp_path / "ws").resolve()
    build_workspace(root, benchmark)
    if second_project:
        _add_second_project(root, benchmark)
    # A field workspace already has its store; the drill creates it once, the same way the installer does.
    from auto_pm.infrastructure.continuity_store import ContinuityStore

    ContinuityStore(root).initialize(datetime.now(UTC).isoformat(), "closure-drill")
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "launcher.py").write_text(LAUNCHER, encoding="utf-8")
    (tools / "sdk_step.py").write_text(SDK_STEP, encoding="utf-8")
    script = tools / "codex_agent.py"
    script.write_text(FAKE_CODEX, encoding="utf-8")
    codex = tools / "codex"
    codex.write_text(f"#!/bin/sh\nexec {sys.executable} {script} \"$@\"\n", encoding="utf-8")
    codex.chmod(0o755)
    return Drill(root, tools)


def _add_second_project(root: Path, benchmark: bytes) -> None:
    """A second PLC project built from the same benchmark bytes, registered next to the first one."""

    staging = root.parent / "second-staging"
    with tarfile.open(fileobj=io.BytesIO(benchmark)) as archive:
        archive.extractall(staging, filter="data")
    shutil.move(str(staging / PROJECT), str(root / SECOND))
    marker = root / SECOND / ".plc.json"
    data = json.loads(marker.read_text(encoding="utf-8"))
    data["name"] = SECOND_ID
    marker.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    # Every project anchor must name the new project, as a freshly generated project would.
    answers = root / SECOND / ".copier-answers.yml"
    answers.write_text(answers.read_text(encoding="utf-8").replace(PROJECT_ID, SECOND_ID), encoding="utf-8")
    session = root / SECOND / f"PM_SESSION_{PROJECT_ID}.md"
    session.rename(root / SECOND / f"PM_SESSION_{SECOND_ID}.md")
    registry = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    payload = json.loads(registry.read_text(encoding="utf-8"))
    payload["projects"].append({"project_id": SECOND_ID, "project_root": SECOND, "development_root": SECOND})
    registry.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "second project")


def buzzer_files(root: Path) -> dict[str, str]:
    """The pinned benchmark requirement: the common alarm block gets a buzzer output (three files)."""

    return requirement_files(root)


def comment_files(root: Path, marker: str, project: str = PROJECT) -> dict[str, str]:
    """A one-file requirement: a comment line in the alarm block, which needs no document row."""

    block = BLOCK.replace(PROJECT, project, 1)
    text = (root / block).read_text(encoding="utf-8")
    assert text.count(BLOCK_ANCHOR) == 1
    return {block: text.replace(BLOCK_ANCHOR, BLOCK_ANCHOR + f"// {marker}\n")}


def change_status(root: Path, project_id: str, change_id: str) -> str:
    from auto_pm.change.change_service import ChangeService

    change = ChangeService(str(root)).get_change_request(change_id, project_id=project_id)
    assert change is not None, change_id
    return str(change.status)


def drive_mission(
    drill: Drill,
    *,
    project_id: str,
    request_id: str,
    files: dict[str, str],
    declared: tuple[str, ...],
    stop_after: str = "",
    domain: str = MAIN_DOMAIN,
    lease_token: str = "",
) -> MissionResult:
    """inbox -> confirm -> plan -> approve -> run+verify -> accept -> close_accepted, as separate processes.

    Returns at the first refused stage instead of asserting, so a variant can tell 'refused early' (fine) from
    'accepted but cannot close' (the D08 dead end).
    """

    added = drill.cli(
        "pm", "inbox", "add", "--project-id", project_id, "--request-id", request_id, "--title", f"样件联调 {request_id}",
        "--kind", "iteration", "--domain", domain, "--original-words", "样件联调：走完整条收口流程", "--affects", "公共报警块",
        "--duplicate-check", "查过收件箱与台账，没有同类条目", "--evidence", f"file:{PROJECT}/.plc.json",
        "--disposition", "after_current", "--rationale", "演练", "--alternative", "不做", "--cost-risk", "低",
    )
    if added.returncode != 0:
        return MissionResult("refused:inbox-add", refusal=added.stderr + added.stdout)
    item = added.json()["item"]
    confirmed = drill.cli(
        "pm", "inbox", "confirm", item["item_id"], "--ticket-hash", item["ticket_hash"], "--approver", APPROVER,
        "--approval-evidence-ref", f"user-confirmation:drill-{request_id}",
    )
    if confirmed.returncode != 0:
        return MissionResult("refused:inbox-confirm", refusal=confirmed.stderr + confirmed.stdout)

    plan_args = [
        "pm", "plan", "--project-id", project_id, "--request-id", request_id, "--objective", "公共报警新增蜂鸣器输出",
        "--acceptance", "门禁全绿并一步收口", "--risk", "none", "--non-goal", "不下载到控制器",
        "--adapter", "codex", "--approved-model", "agent-a", "--inbox-id", item["item_id"],
    ]
    for path in declared:
        plan_args += ["--scope", path, "--declared-dirty", path]
    planned = drill.cli(*plan_args)
    if planned.returncode != 0:
        return MissionResult("refused:plan", refusal=planned.stderr + planned.stdout)
    card = planned.json()

    approved = drill.cli(
        "pm", "approve", "--request-id", request_id, "--plan-hash", card["plan_hash"], "--approver", APPROVER,
        "--approval-evidence-ref", f"user-confirmation:drill-{request_id}",
    )
    if approved.returncode != 0:
        return MissionResult("refused:approve", change_id=card["change_id"], refusal=approved.stderr + approved.stdout)

    ran = drill.sdk("run", card, files, lease_token=lease_token)
    if ran.returncode != 0:
        return MissionResult("refused:run", change_id=card["change_id"], refusal=ran.stderr + ran.stdout)
    outcome = ran.json()
    mission_id = outcome["mission_id"]
    if not outcome["verified"]:
        return MissionResult("refused:verify", mission_id, card["change_id"], ran.stderr + ran.stdout)
    if stop_after == "verify":
        return MissionResult("verified", mission_id, card["change_id"])

    accepted = drill.cli("pm", "accept", "--mission-id", mission_id)
    if accepted.returncode != 0:
        return MissionResult("refused:accept", mission_id, card["change_id"], accepted.stderr + accepted.stdout)
    if stop_after == "accept":
        return MissionResult("accepted", mission_id, card["change_id"])
    return close_mission(drill, card, mission_id)


def close_mission(drill: Drill, card: dict[str, Any], mission_id: str) -> MissionResult:
    closed = drill.sdk("close", card)
    if closed.returncode != 0 or closed.json()["state"] != "COMPLETED":
        return MissionResult("accepted-but-not-closed", mission_id, card["change_id"], closed.stderr + closed.stdout)
    return MissionResult("closed", mission_id, card["change_id"])


def assert_closed_and_clean(drill: Drill, result: MissionResult, project_id: str) -> None:
    """The D08 pass line: Mission/Run/Work terminal, change sheet completed, ledger 0/0/0 after --fix."""

    assert result.stage == "closed", f"{result.stage}: {result.refusal}\n{drill.transcript()}"
    from auto_pm.contracts.continuity import RunState, WorkState
    from auto_pm.contracts.mission import MissionState
    from auto_pm.infrastructure.continuity_store import ContinuityStore

    store = ContinuityStore(drill.root)
    mission = store.get_mission(result.mission_id)
    assert mission.state is MissionState.CLOSED
    assert mission.root_work_id
    assert store.get_work(mission.root_work_id).state is WorkState.CLOSED
    runs = store.list_runs(mission.root_work_id, include_terminal=True)
    assert runs and runs[0].state is RunState.SUCCEEDED

    # The agent's own step after closure, as the D08 prompt orders it: walk the sheet to completed, always with --pid.
    status = change_status(drill.root, project_id, result.change_id)
    order = ("approved", "implementing", "pending_acceptance", "accepting", "completed")
    assert status in order, status
    for target in order[order.index(status) + 1 :]:
        moved = drill.cli(
            "change", "transition", result.change_id, "--to", target, "--approver", APPROVER, "--comment", "样件联调", "--pid", project_id
        )
        assert moved.returncode == 0, drill.transcript()
    assert change_status(drill.root, project_id, result.change_id) == "completed", drill.transcript()

    fixed = drill.cli("ledger", "reconcile", project_id, "--fix")
    assert fixed.returncode == 0, drill.transcript()
    checked = drill.cli("ledger", "reconcile", project_id)
    assert checked.returncode == 0, drill.transcript()
    assert "台账缺失: 0 条, 台账多余(孤儿): 0 条, 状态不一致: 0 条" in checked.stdout, checked.stdout


def commit_control_root(drill: Drill, paths: tuple[str, ...], message: str) -> None:
    """The user's own commit of the accepted files in the control root (closure merges back but never commits).

    Only the Mission's files: the benchmark's CHG folder clash (defect ④) would otherwise ride into the next worktree.
    """

    git(drill.root, "add", "--", *paths)
    git(drill.root, "commit", "-q", "--no-verify", "-m", message, "--", *paths)


def assert_never_stuck(drill: Drill, result: MissionResult) -> None:
    """Field input may be refused early, but an accepted Mission must never be left unclosable."""

    assert result.stage != "accepted-but-not-closed", f"已验收却关不掉：{result.refusal}\n{drill.transcript()}"


Files = Callable[[Path], dict[str, str]]


def _sorted_buzzer(root: Path) -> tuple[dict[str, str], tuple[str, ...]]:
    files = buzzer_files(root)
    return files, tuple(sorted(files))


def _unsorted_buzzer(root: Path) -> tuple[dict[str, str], tuple[str, ...]]:
    files = buzzer_files(root)
    declared = (STRUCT, BLOCK, VAR_DOC)
    assert declared != tuple(sorted(declared))
    return files, declared


def _single_file(root: Path) -> tuple[dict[str, str], tuple[str, ...]]:
    files = comment_files(root, "样件联调：单文件")
    return files, tuple(files)


def _chinese_new_file(root: Path) -> tuple[dict[str, str], tuple[str, ...]]:
    files = buzzer_files(root)
    files[NEW_NOTE] = "# 蜂鸣器说明\n\n任意报警激活时蜂鸣器输出置位。\n"
    return files, tuple(sorted(files))


# --- 1. the main line --------------------------------------------------------------------------------------------


def test_d01_main_line_sorted_three_files_closes_in_one_step_and_ledger_is_clean(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    files, declared = _sorted_buzzer(drill.root)

    result = drive_mission(drill, project_id=PROJECT_ID, request_id="REQ-DRILL-D01", files=files, declared=declared)

    assert_closed_and_clean(drill, result, PROJECT_ID)


@pytest.mark.xfail(strict=True, reason=LEGACY_LAYOUT_DEFECT)
def test_d00_a_project_on_the_old_11_layout_can_be_approved_and_closed(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    files, declared = _sorted_buzzer(drill.root)

    result = drive_mission(
        drill, project_id=PROJECT_ID, request_id="REQ-DRILL-D00", files=files, declared=declared, domain="PLC"
    )

    assert_closed_and_clean(drill, result, PROJECT_ID)


# --- 2. field-shaped variants -------------------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason=WAITING_FOR_CARD_179)
def test_d02_declared_out_of_alphabetical_order_still_closes(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    files, declared = _unsorted_buzzer(drill.root)

    result = drive_mission(drill, project_id=PROJECT_ID, request_id="REQ-DRILL-D02", files=files, declared=declared)

    assert_closed_and_clean(drill, result, PROJECT_ID)


def test_d02b_out_of_order_today_dies_after_acceptance_not_before(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    """Pins the current D08 dead end so the report can quote it; flips when card 179 lands (then delete this test)."""

    drill = make_drill(tmp_path, benchmark_tar)
    files, declared = _unsorted_buzzer(drill.root)

    result = drive_mission(drill, project_id=PROJECT_ID, request_id="REQ-DRILL-D02B", files=files, declared=declared)

    if result.stage == "closed":
        pytest.skip("卡 179 已生效：乱序登记已能收口，本钉子测试可以删除")
    assert result.stage == "accepted-but-not-closed", f"{result.stage}: {result.refusal}"
    assert "最新 Checkpoint 未绑定 Run 当前验证证据" in result.refusal
    # What the user sees is only the generic sentence; the real reason is only in the log.
    assert "必要证据或状态未就绪" in result.refusal


def test_d03_single_file(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    files, declared = _single_file(drill.root)

    result = drive_mission(drill, project_id=PROJECT_ID, request_id="REQ-DRILL-D03", files=files, declared=declared)

    assert_closed_and_clean(drill, result, PROJECT_ID)


def test_d04_a_new_file_with_a_chinese_name(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    files, declared = _chinese_new_file(drill.root)

    result = drive_mission(drill, project_id=PROJECT_ID, request_id="REQ-DRILL-D04", files=files, declared=declared)

    assert_never_stuck(drill, result)
    assert_closed_and_clean(drill, result, PROJECT_ID)


def test_d05_windows_backslashes_in_declared_paths(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    files, declared = _sorted_buzzer(drill.root)
    windows = tuple(path.replace("/", "\\") for path in declared)

    result = drive_mission(drill, project_id=PROJECT_ID, request_id="REQ-DRILL-D05", files=files, declared=windows)

    assert_never_stuck(drill, result)
    if result.stage != "closed":
        # Today: refused at plan with a raw validation message, while ``continuity run start`` silently converts '\\'.
        assert result.stage == "refused:plan", f"{result.stage}: {result.refusal}"
        assert "forward slashes" in result.refusal


def test_d06_letter_case_differs_from_the_files_on_disk(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    """On Windows ``fb_2001`` and ``FB_2001`` are one file; the drill only demands: refused early, or closed."""

    drill = make_drill(tmp_path, benchmark_tar)
    files, declared = _sorted_buzzer(drill.root)
    cased = tuple(path.replace("FB_2001_CommonAlarm", "fb_2001_commonalarm") for path in declared)
    assert cased != declared

    result = drive_mission(drill, project_id=PROJECT_ID, request_id="REQ-DRILL-D06", files=files, declared=cased)

    assert_never_stuck(drill, result)
    assert result.stage.startswith("refused:") or result.stage == "closed", f"{result.stage}: {result.refusal}"


def test_d07_two_missions_back_to_back_on_one_project(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    files, declared = _sorted_buzzer(drill.root)
    first = drive_mission(drill, project_id=PROJECT_ID, request_id="REQ-DRILL-D07A", files=files, declared=declared)
    assert_closed_and_clean(drill, first, PROJECT_ID)
    # Closure merged the first Mission's bytes back into the control root, uncommitted; the user commits them
    # before the next isolated Run is cut from HEAD (otherwise run start refuses, see test_d12).
    commit_control_root(drill, declared, "第一单成果入库")

    second_files = comment_files(drill.root, "样件联调：第二单")
    second = drive_mission(
        drill, project_id=PROJECT_ID, request_id="REQ-DRILL-D07B", files=second_files, declared=tuple(second_files)
    )

    assert_closed_and_clean(drill, second, PROJECT_ID)


def test_d11_after_closure_the_accepted_bytes_are_in_the_control_root(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    files = comment_files(drill.root, "样件联调：收口后应在控制根")
    result = drive_mission(drill, project_id=PROJECT_ID, request_id="REQ-DRILL-D11", files=files, declared=tuple(files))
    assert_closed_and_clean(drill, result, PROJECT_ID)

    for relative, text in files.items():
        assert (drill.root / relative).read_text(encoding="utf-8") == text, f"控制根没有收到验收过的改动: {relative}"


def test_d12_an_isolated_run_on_uncommitted_merged_bytes_is_refused_at_start_not_after_acceptance(
    tmp_path: Path, benchmark_tar: bytes  # noqa: F811
) -> None:
    """Back-to-back on the same file without the user's commit in between: refused before work starts, never stuck later."""

    drill = make_drill(tmp_path, benchmark_tar)
    files = comment_files(drill.root, "样件联调：第一单")
    first = drive_mission(drill, project_id=PROJECT_ID, request_id="REQ-DRILL-D12A", files=files, declared=tuple(files))
    assert_closed_and_clean(drill, first, PROJECT_ID)

    again = comment_files(drill.root, "样件联调：第二单")
    second = drive_mission(drill, project_id=PROJECT_ID, request_id="REQ-DRILL-D12B", files=again, declared=tuple(again))

    assert_never_stuck(drill, second)
    assert second.stage == "refused:run", f"{second.stage}: {second.refusal}"
    assert "控制根里范围内的文件与本 Run 起点不一致" in second.refusal
    # Nothing of the second Mission reached the control root.
    for relative, text in files.items():
        assert (drill.root / relative).read_text(encoding="utf-8") == text


def _parallel_pair(drill: Drill, domain_b: str) -> None:
    files_a = comment_files(drill.root, "样件联调：项目 A")
    files_b = comment_files(drill.root, "样件联调：项目 B", project=SECOND)

    # Both reach the acceptance gate before either is accepted, then they close in the opposite order.
    a = drive_mission(drill, project_id=PROJECT_ID, request_id="REQ-DRILL-PA", files=files_a, declared=tuple(files_a), stop_after="verify")
    b = drive_mission(
        drill, project_id=SECOND_ID, request_id="REQ-DRILL-PB", files=files_b, declared=tuple(files_b), stop_after="verify", domain=domain_b
    )
    assert a.stage == "verified", f"{a.stage}: {a.refusal}\n{drill.transcript()}"
    assert b.stage == "verified", f"{b.stage}: {b.refusal}\n{drill.transcript()}"
    for result in (a, b):
        accepted = drill.cli("pm", "accept", "--mission-id", result.mission_id)
        assert accepted.returncode == 0, drill.transcript()

    closed_b = close_mission(drill, _card_of(drill, "REQ-DRILL-PB"), b.mission_id)
    closed_a = close_mission(drill, _card_of(drill, "REQ-DRILL-PA"), a.mission_id)

    assert_closed_and_clean(drill, closed_b, SECOND_ID)
    assert_closed_and_clean(drill, closed_a, PROJECT_ID)


def test_d08_two_projects_in_parallel_with_different_change_numbers(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar, second_project=True)

    _parallel_pair(drill, domain_b="MECH")


@pytest.mark.xfail(strict=True, reason=SAME_NUMBER_DEFECT)
def test_d09_two_projects_in_parallel_whose_first_change_numbers_coincide(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar, second_project=True)

    _parallel_pair(drill, domain_b=MAIN_DOMAIN)


@pytest.mark.xfail(strict=True, reason=SAME_NUMBER_DEFECT)
def test_d10_a_closed_mission_in_one_project_blocks_the_same_number_in_another(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar, second_project=True)
    files_a = comment_files(drill.root, "样件联调：项目 A 先做完")
    first = drive_mission(drill, project_id=PROJECT_ID, request_id="REQ-DRILL-D10A", files=files_a, declared=tuple(files_a))
    assert_closed_and_clean(drill, first, PROJECT_ID)

    files_b = comment_files(drill.root, "样件联调：项目 B 后做", project=SECOND)
    second = drive_mission(drill, project_id=SECOND_ID, request_id="REQ-DRILL-D10B", files=files_b, declared=tuple(files_b))

    assert_closed_and_clean(drill, second, SECOND_ID)


def _card_of(drill: Drill, request_id: str) -> dict[str, Any]:
    card: dict[str, Any] = json.loads((drill.tools / f"card-{request_id}.json").read_text(encoding="utf-8"))
    return card

