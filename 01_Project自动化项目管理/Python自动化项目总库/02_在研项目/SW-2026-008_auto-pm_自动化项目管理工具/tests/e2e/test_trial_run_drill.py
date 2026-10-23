"""The first real Trae trial (2026-10-22, DJ-2026-011 报警汇总、复位熄灭) replayed as sample parts, so the next release finds these
problems before the user does.

Score sheet: ``/mnt/project-files/真Trae试跑打分_20261022.md``.  Each case is a pit the trial stepped in, fed through the real
``pm`` / ``continuity`` commands in their own processes, the way Trae ran them:

* t01 empty change declaration: quality verification let the Run through and acceptance then refused it (score item 8);
* t02 plan fields missing: no safety-circuit answer, no rollback, acceptance only in words (score item 4);
* t03 the retired ``PM_SESSION_*.md`` listed in the scope (score item 4);
* t04 the change sheet and ledger the cockpit generates were not in the delivery commit, so Trae had to ask (score item 9);
* t05 approval before the user's confirmation (item 5 passed only because Trae behaved; the cockpit does not stop it).

Fixed by PR #35/#36 (plan poka-yoke, one declaration rule for plan, Run start, verification and acceptance) and PR #37
(entry skill).  A case the cockpit does not hold yet is a strict xfail that only absorbs the defect's own symptom
(``KnownDefectError``), so a broken set-up can never pass for the known defect.
"""

from __future__ import annotations

import re
import secrets
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import pytest

from tests.e2e.test_closure_drill import (
    APPROVER,
    MAIN_DOMAIN,
    ORIGINAL_WORDS,
    PLAN_CHECKLIST,
    PROJECT_ID,
    Drill,
    Step,
    assert_closed_and_clean,
    buzzer_files,
    comment_files,
    drive_mission,
    make_drill,
)
from tests.e2e.test_pmf_plc import (
    PROJECT,
    benchmark_tar,  # noqa: F401 - module fixture re-used by name
    git,
)

EXECUTOR = "trae:cn"
TOKEN_ENV = "DRILL_TRAE_LEASE_TOKEN"
SESSION_FILE = f"{PROJECT}/PM_SESSION_{PROJECT_ID}.md"
GAP_9 = (
    "缺口⑨（预做在分支 claude/gap9-approval-proof，未合）：命令行批准只查证据格式，agent 填上用户名和一个自己编的 "
    "user-confirmation: 引用就能批准；试跑第 5 条过，只是因为 Trae 自觉等了用户“确认开工”"
)

class KnownDefectError(AssertionError):
    """The one symptom a strict xfail may absorb; any other failure stays a failure."""


# --- t01 empty change declaration (score item 8) -------------------------------------------------------------------


def test_t01a_a_plan_with_an_empty_declaration_is_refused_and_the_corrected_plan_goes_through(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    files = comment_files(drill.root, "试跑：空声明")
    item = _inbox(drill, "REQ-TRIAL-T01A")

    refused = drill.cli(*_plan(item, "REQ-TRIAL-T01A", files, declared=()))

    _refused_without_a_trace(drill, refused, "改动声明为空")
    # Trae's next move: the same request with the files declared.  The refusal must not leave anything in the way.
    corrected = drill.cli(*_plan(item, "REQ-TRIAL-T01A", files))
    assert corrected.returncode == 0, drill.transcript()
    assert corrected.json()["execution_grant"]["declared_dirty_paths"] == list(files)


def test_t01b_verification_refuses_what_acceptance_would_refuse(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    """The trial's dead end on Trae's own lane: verification opened the acceptance gate, acceptance then refused and the
    Mission hung in ACCEPTANCE_PENDING.  Here the agent changes three files of its scope but declares one."""

    drill = make_drill(tmp_path, benchmark_tar)
    files = buzzer_files(drill.root)
    declared = (sorted(files)[0],)
    lane = _IdeLane(drill, "REQ-TRIAL-T01B", files)
    opened = lane.start_run(owned=tuple(sorted(files)), declared=declared)
    assert opened.returncode == 0, drill.transcript()
    lane.transition("RUNNING")
    lane.write(files)
    lane.transition("VERIFYING")

    verified = lane.verify()

    outcome = verified.json()
    assert verified.returncode == (0 if outcome["verified"] else 1), drill.transcript()
    if outcome["verified"]:
        accepted = drill.cli("pm", "accept", "--mission-id", lane.mission_id)
        assert accepted.returncode == 0, f"质量验证放行、验收却拒收（试跑第 8 条的死路）: {accepted.stderr}\n{drill.transcript()}"
        pytest.fail(f"声明 1 个、实际改 3 个，质量验证和验收却都放行了\n{drill.transcript()}")
    assert outcome["mission_state"] == "ACTIVE", outcome
    why = outcome["message"] + outcome.get("reason", "")
    assert "未声明却改动 2 个" in why, f"质量验证没说清为什么不过: {why}"


def test_t01c_an_ide_run_cannot_start_with_an_empty_declaration(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    """``continuity run start`` without ``--declared-dirty`` is where the trial's empty declaration came in."""

    drill = make_drill(tmp_path, benchmark_tar)
    files = comment_files(drill.root, "试跑：IDE 空声明")
    lane = _IdeLane(drill, "REQ-TRIAL-T01C", files)

    opened = lane.start_run(owned=tuple(files), declared=())

    assert opened.returncode != 0, f"空声明的 Run 开起来了\n{drill.transcript()}"
    assert "改动声明为空" in opened.stderr, opened.stderr
    assert _rows(drill)["run_items"] == 0, "被拒的 Run 不应留下记录"


def test_t01d_the_codex_lane_never_verifies_what_acceptance_refuses(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    files = buzzer_files(drill.root)

    result = drive_mission(
        drill, project_id=PROJECT_ID, request_id="REQ-TRIAL-T01D", files=files, declared=(sorted(files)[0],), scope=tuple(sorted(files))
    )

    assert result.stage != "refused:accept", f"质量验证放行、验收却拒收: {result.refusal}\n{drill.transcript()}"
    assert result.stage in {"refused:run", "refused:verify"}, f"{result.stage}: {result.refusal}"


# --- t02 plan fields missing (score item 4) -------------------------------------------------------------------------


def test_t02a_the_trial_plan_is_refused_naming_every_missing_field_and_the_filled_plan_goes_through(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    """The trial plan as Trae wrote it: the user's words and a scope, but no declaration, safety answer, command or rollback."""

    drill = make_drill(tmp_path, benchmark_tar)
    files = comment_files(drill.root, "试跑：缺栏")
    item = _inbox(drill, "REQ-TRIAL-T02A")

    refused = drill.cli(*_plan(item, "REQ-TRIAL-T02A", files, declared=(), checklist=("--original-request", ORIGINAL_WORDS)))

    _refused_without_a_trace(drill, refused, "计划防呆未通过，缺 4 栏")
    for field in ("③", "④", "⑤", "⑦"):
        assert field in refused.stderr, f"缺栏清单里没有 {field}: {refused.stderr}"
    assert "①" not in refused.stderr and "⑥" not in refused.stderr, refused.stderr
    corrected = drill.cli(*_plan(item, "REQ-TRIAL-T02A", files))
    assert corrected.returncode == 0, drill.transcript()


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"--safety-circuit": None}, "④是否涉及安全回路"),
        ({"--safety-circuit": "不确定"}, "④是否涉及安全回路"),
        ({"--rollback": "无"}, "⑦回退办法"),
        ({"--check": None}, "⑤每条验收标准的命令和退出码"),
        ({"--original-request": "做个收口演练"}, "一字不改"),
    ],
    ids=["no-safety-answer", "undecided-safety", "placeholder-rollback", "no-command", "paraphrased-words"],
)
def test_t02b_each_missing_field_alone_is_refused_by_name(
    tmp_path: Path, benchmark_tar: bytes, overrides: dict[str, str | None], field: str  # noqa: F811
) -> None:
    drill = make_drill(tmp_path, benchmark_tar)
    files = comment_files(drill.root, "试跑：单栏缺")
    item = _inbox(drill, "REQ-TRIAL-T02B")

    refused = drill.cli(*_plan(item, "REQ-TRIAL-T02B", files, checklist=_checklist(overrides)))

    _refused_without_a_trace(drill, refused, field)
    assert "缺 1 栏" in refused.stderr, refused.stderr


def test_t02c_a_placeholder_risk_is_refused(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    files = comment_files(drill.root, "试跑：风险写无")
    item = _inbox(drill, "REQ-TRIAL-T02C")

    refused = drill.cli(*_plan(item, "REQ-TRIAL-T02C", files, risk="无"))

    _refused_without_a_trace(drill, refused, "⑥风险")


def test_t02d_the_complete_plan_closes_and_keeps_the_safety_answer(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    """The counter-proof of t02a～c: the same kind of Mission with every field filled closes and the ledger is clean."""

    drill = make_drill(tmp_path, benchmark_tar)
    files = comment_files(drill.root, "试跑：七栏齐")

    result = drive_mission(drill, project_id=PROJECT_ID, request_id="REQ-TRIAL-T02D", files=files, declared=tuple(files))

    assert_closed_and_clean(drill, result, PROJECT_ID)
    from auto_pm.core.pm_facade_service import PmFacadeService

    checklist = PmFacadeService(drill.root).recover_planning_scope_card(result.mission_id).execution_grant.plan_checklist
    assert checklist is not None and checklist.safety_circuit == "否" and checklist.original_request == ORIGINAL_WORDS


# --- t03 retired PM_SESSION in the scope (score item 4) -------------------------------------------------------------


def test_t03a_a_plan_listing_the_retired_session_file_in_its_scope_is_refused(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    assert (drill.root / SESSION_FILE).is_file(), "样件里应有现场那样的 PM_SESSION 文件"
    files = comment_files(drill.root, "试跑：范围含 PM_SESSION")
    item = _inbox(drill, "REQ-TRIAL-T03A")

    refused = drill.cli(*_plan(item, "REQ-TRIAL-T03A", files, scope=(*files, SESSION_FILE)))

    _refused_without_a_trace(drill, refused, "PM_SESSION")


def test_t03b_declaring_the_retired_session_file_is_refused(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    files = {**comment_files(drill.root, "试跑：声明含 PM_SESSION"), SESSION_FILE: "刷新\n"}
    item = _inbox(drill, "REQ-TRIAL-T03B")

    refused = drill.cli(*_plan(item, "REQ-TRIAL-T03B", files))

    _refused_without_a_trace(drill, refused, "PM_SESSION")


def test_t03c_an_ide_run_owning_the_retired_session_file_cannot_start(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    files = comment_files(drill.root, "试跑：IDE 范围含 PM_SESSION")
    lane = _IdeLane(drill, "REQ-TRIAL-T03C", files)

    opened = lane.start_run(owned=(*files, SESSION_FILE), declared=tuple(files))

    assert opened.returncode != 0, f"拥有 PM_SESSION 的 Run 开起来了\n{drill.transcript()}"
    assert "PM_SESSION" in opened.stderr, opened.stderr
    assert _rows(drill)["run_items"] == 0


# --- t04 the generated change sheet and ledger belong to the delivery (score item 9) --------------------------------


def test_t04_every_file_the_cockpit_generates_is_one_the_skill_says_to_commit(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    """After plan, approval, closure and reconcile the control root holds files the agent did not write.  The skill must
    tell the agent they go into the delivery commit (Trae had to ask), and they must be exactly the kinds the skill names,
    so a newly generated kind of file shows up here instead of in the user's chat."""

    skill = _skill_text()
    step_8 = skill[skill.index("8. **验收与收口**") :]
    assert re.search(r"自动生成的变更单和台账.{0,30}同一次提交", step_8), "技能第 8 步没写自动生成的变更单与台账随交付同一次提交（试跑第 9 条）"

    drill = make_drill(tmp_path, benchmark_tar)
    files = comment_files(drill.root, "试跑：交付提交")
    result = drive_mission(drill, project_id=PROJECT_ID, request_id="REQ-TRIAL-T04", files=files, declared=tuple(files))
    assert_closed_and_clean(drill, result, PROJECT_ID)

    generated = [path for path in _uncommitted(drill.root) if path not in files]
    sheet = re.compile(rf"/CHG-{MAIN_DOMAIN}-\d{{4}}-\d{{3}}\.md$")
    ledger = re.compile(r"/[^/]*版本变更台账\.md$")
    unnamed = [path for path in generated if not (sheet.search(path) or ledger.search(path))]
    assert unnamed == [], f"驾驶舱生成了技能没提到的文件，agent 会不知道交不交: {unnamed}"
    assert [path for path in generated if sheet.search(path)] and [path for path in generated if ledger.search(path)], generated

    # The delivery commit the skill asks for leaves nothing behind.
    git(drill.root, "add", "--", *_uncommitted(drill.root))
    git(drill.root, "commit", "-q", "-m", f"{result.change_id} 交付")
    assert _uncommitted(drill.root) == []


# --- t05 approval before the user's confirmation (score item 5) -----------------------------------------------------


def test_t05a_a_plan_on_a_triage_ticket_the_user_has_not_confirmed_is_refused(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    files = comment_files(drill.root, "试跑：未确认先计划")
    item = _inbox(drill, "REQ-TRIAL-T05A", confirm=False)

    refused = drill.cli(*_plan(item, "REQ-TRIAL-T05A", files))

    assert refused.returncode != 0, f"用户还没确认分诊单，计划就建起来了\n{drill.transcript()}"
    assert _sheets(drill) == []


@pytest.mark.xfail(strict=True, raises=KnownDefectError, reason=GAP_9)
def test_t05b_an_agent_cannot_approve_with_a_confirmation_the_user_never_gave(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    files = comment_files(drill.root, "试跑：自批")
    item = _inbox(drill, "REQ-TRIAL-T05B")
    planned = drill.cli(*_plan(item, "REQ-TRIAL-T05B", files))
    assert planned.returncode == 0, drill.transcript()

    # The user has seen the plan but never said “确认开工”; the agent writes the user's name and a reference it made up.
    forged = drill.cli(
        "pm", "approve", "--request-id", "REQ-TRIAL-T05B", "--plan-hash", planned.json()["plan_hash"], "--approver", APPROVER,
        "--approval-evidence-ref", "user-confirmation:2026-10-22T07:11:03-07:00",
    )

    if forged.returncode == 0:
        raise KnownDefectError(f"agent 自己编的确认引用批准成功: {forged.stdout[:200]}")


# --- helpers --------------------------------------------------------------------------------------------------------


def _checklist(overrides: dict[str, str | None]) -> tuple[str, ...]:
    """The complete plan fields with some replaced, or (value ``None``) left out."""

    values: dict[str, str | None] = dict(zip(PLAN_CHECKLIST[0::2], PLAN_CHECKLIST[1::2], strict=True))
    values.update(overrides)
    return tuple(item for flag, value in values.items() if value is not None for item in (flag, value))


def _inbox(drill: Drill, request_id: str, *, confirm: bool = True) -> dict[str, str]:
    added = drill.cli(
        "pm", "inbox", "add", "--project-id", PROJECT_ID, "--request-id", request_id, "--title", f"试跑 {request_id}",
        "--kind", "iteration", "--domain", MAIN_DOMAIN, "--original-words", ORIGINAL_WORDS, "--affects", "公共报警块",
        "--duplicate-check", "查过收件箱与台账，没有同类条目", "--evidence", f"file:{PROJECT}/.plc.json",
        "--disposition", "after_current", "--rationale", "试跑复现", "--alternative", "不做", "--cost-risk", "低",
    )
    assert added.returncode == 0, drill.transcript()
    item: dict[str, str] = added.json()["item"]
    if confirm:
        # The user confirmed the triage ticket: a separate, earlier act than “确认开工”.
        confirmed = drill.cli(
            "pm", "inbox", "confirm", item["item_id"], "--ticket-hash", item["ticket_hash"], "--approver", APPROVER,
            "--approval-evidence-ref", f"user-confirmation:triage-{request_id}",
        )
        assert confirmed.returncode == 0, drill.transcript()
    return item


def _plan(
    item: dict[str, str],
    request_id: str,
    files: dict[str, str],
    *,
    declared: tuple[str, ...] | None = None,
    scope: tuple[str, ...] | None = None,
    checklist: tuple[str, ...] = PLAN_CHECKLIST,
    risk: str = "只动公共报警块，改错会影响报警指示",
) -> list[str]:
    """``pm plan`` as Trae runs it (adapter trae); scope and declaration default to the files the agent will write."""

    plan = [
        "pm", "plan", "--project-id", PROJECT_ID, "--request-id", request_id, "--objective", "公共报警加一行注释",
        "--acceptance", "门禁全绿", "--risk", risk, "--non-goal", "不下载到控制器", "--adapter", "trae",
        "--approved-model", "trae", "--inbox-id", item["item_id"], *checklist,
    ]
    for path in tuple(files) if scope is None else scope:
        plan += ["--scope", path]
    for path in tuple(files) if declared is None else declared:
        plan += ["--declared-dirty", path]
    return plan


def _rows(drill: Drill) -> dict[str, int]:
    with closing(sqlite3.connect(drill.root / ".auto-pm" / "continuity.db")) as conn:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])  # noqa: S608 - fixed table names
            for table in ("planning_scope_cards", "planning_draft_chg_bindings", "mission_items", "run_items")
        }


def _sheets(drill: Drill) -> list[Path]:
    return sorted((drill.root / PROJECT).glob(f"**/CHG-{MAIN_DOMAIN}-*.md"))


def _refused_without_a_trace(drill: Drill, step: Step, expected: str) -> None:
    """Refused for the stated reason, with no scope card, change number, Mission or change sheet left behind.

    ``pm plan`` keeps the bare request draft (objective and acceptance) so the corrected plan can reuse the request id.
    """

    assert step.returncode != 0, f"计划没被拦住\n{drill.transcript()}"
    assert expected in step.stderr, f"拒绝原因不对（要有“{expected}”）: {step.stderr}"
    assert _rows(drill) == {"planning_scope_cards": 0, "planning_draft_chg_bindings": 0, "mission_items": 0, "run_items": 0}
    assert _sheets(drill) == [], "计划被拒后不应留下变更单"


def _skill_text() -> str:
    repository = Path(git(Path(__file__).resolve().parent, "rev-parse", "--show-toplevel"))
    return (repository / ".trae" / "skills" / "cockpit-entry" / "SKILL.md").read_text(encoding="utf-8")


def _uncommitted(root: Path) -> list[str]:
    changed = git(root, "diff", "--name-only", "HEAD").splitlines()
    untracked = git(root, "ls-files", "--others", "--exclude-standard").splitlines()
    return sorted({path for path in (*changed, *untracked) if path})


class _IdeLane:
    """An approved Mission taken up by an IDE agent the way Trae did in the trial: start confirmation, its own worktree,
    ``continuity run start``, RUNNING, writing, VERIFYING, ``pm verify``."""

    def __init__(self, drill: Drill, request_id: str, files: dict[str, str]) -> None:
        self.drill = drill
        self.run_id = f"RUN-IDE-{request_id}"
        self.token = secrets.token_urlsafe(32)
        item = _inbox(drill, request_id)
        planned = drill.cli(*_plan(item, request_id, files))
        assert planned.returncode == 0, drill.transcript()
        card = planned.json()
        approved = drill.cli(
            "pm", "approve", "--request-id", request_id, "--plan-hash", card["plan_hash"], "--approver", APPROVER,
            "--approval-evidence-ref", f"user-confirmation:start-{request_id}",
        )
        assert approved.returncode == 0, drill.transcript()
        from auto_pm.infrastructure.continuity_store import ContinuityStore

        missions = [
            mission
            for mission in ContinuityStore(drill.root).list_missions(PROJECT_ID, include_terminal=True)
            if mission.authority.change_id == card["change_id"]
        ]
        assert len(missions) == 1, missions
        self.mission_id = missions[0].mission_id
        self.work_id = _start_the_approved_work(drill, self.mission_id)
        self.worktree = drill.root / ".auto-pm" / "worktrees" / f"ide-{request_id.lower()}"
        git(drill.root, "worktree", "add", "-q", "--detach", str(self.worktree))

    def _with_token(self, name: str, command: list[str]) -> Step:
        environment = self.drill._env()
        environment[TOKEN_ENV] = self.token
        return self.drill._call(name, command, environment)

    def _launcher(self, arguments: list[str]) -> list[str]:
        return [sys.executable, str(self.drill.tools / "launcher.py"), "-w", str(self.drill.root), *arguments]

    def start_run(self, *, owned: tuple[str, ...], declared: tuple[str, ...]) -> Step:
        command = [
            "continuity", "run", "start", "--run-id", self.run_id, "--work-id", self.work_id, "--executor", EXECUTOR,
            "--adapter", "trae", "--worktree", str(self.worktree), "--lease-token-env", TOKEN_ENV,
            "--idempotency-key", f"{self.run_id}:start",
        ]
        for path in owned:
            command += ["--owned", path]
        for path in declared:
            command += ["--declared-dirty", path]
        return self._with_token("continuity run start", self._launcher(command))

    def transition(self, state: str) -> None:
        moved = self._with_token(
            f"continuity run {state}",
            self._launcher([
                "continuity", "run", "transition", "--run-id", self.run_id, "--to", state, "--owner", EXECUTOR,
                "--lease-token-env", TOKEN_ENV, "--idempotency-key", f"{self.run_id}:{state}",
            ]),
        )
        assert moved.returncode == 0, self.drill.transcript()

    def write(self, files: dict[str, str]) -> None:
        for relative, text in files.items():
            target = self.worktree / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")

    def verify(self) -> Step:
        return self._with_token(
            "pm verify",
            self._launcher(["pm", "verify", "--mission-id", self.mission_id, "--lease-token-env", TOKEN_ENV]),
        )


def _start_the_approved_work(drill: Drill, mission_id: str) -> str:
    """The user's start confirmation, as Trae runs it: ``pm confirm-start`` (gap ⑧ binds the card's own Work)."""

    from auto_pm.infrastructure.continuity_store import ContinuityStore

    started = drill.cli("pm", "confirm-start", "--mission-id", mission_id)
    assert started.returncode == 0, drill.transcript()
    work_id = ContinuityStore(drill.root).get_mission(mission_id).root_work_id
    assert work_id and work_id.startswith("WORK-MSN-"), work_id
    return work_id
