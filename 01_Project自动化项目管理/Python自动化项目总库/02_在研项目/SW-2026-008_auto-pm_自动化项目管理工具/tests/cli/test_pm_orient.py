"""V05-A: ``pm orient`` and ``pm resume`` expose the same versioned, capability-flagged query and write nothing."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner, Result

from auto_pm.application.core.pm_facade_service import PmFacadeService
from auto_pm.contracts.continuity_query import ContinuityQuery
from auto_pm.contracts.continuity_resume import ContinuityResume
from auto_pm.ui.cli.__main__ import cli

PROJECT = "SW-2026-008"
UNSUPPORTED_ACTIONS = ("PARK", "RESUME_PARKED", "PREEMPT")
# runtime-capabilities.v2 (TD-071 card 3): parking is supported, pre-emption is not
DECLARED = {"PARK": "SUPPORTED", "RESUME_PARKED": "SUPPORTED", "PREEMPT": "UNSUPPORTED"}


def _workspace(root: Path) -> Path:
    subprocess.run(["git", "-C", str(root), "init"], check=True, capture_output=True)
    (root / "README.md").write_text("baseline\n", encoding="utf-8")
    (root / ".gitignore").write_text(".auto-pm/\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "README.md", ".gitignore"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=Orient Test", "-c", "user.email=orient@example.invalid", "commit", "-m", "baseline"],
        check=True,
        capture_output=True,
    )
    project = root / PROJECT
    project.mkdir()
    (project / ".copier-answers.yml").write_text(f"project_id: {PROJECT}\nproject_name: Orient Test\nstack: python\n", encoding="utf-8")
    registry = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    registry.parent.mkdir()
    registry.write_text(
        json.dumps(
            {
                "schema_version": "workspace-registry.v1",
                "projects": [{"project_id": PROJECT, "project_root": PROJECT, "development_root": PROJECT}],
            }
        ),
        encoding="utf-8",
    )
    return project


def _snapshot(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


def _run(root: Path, *args: str) -> Result:
    return CliRunner().invoke(cli, ["-w", str(root), "pm", *args])


def _json(result: Result) -> Any:
    assert result.exit_code == 0, result.output
    start = result.output.index("{")
    return json.JSONDecoder().raw_decode(result.output[start:])[0]


def test_orient_is_listed_with_its_options_and_the_three_asked_actions(tmp_path: Path) -> None:
    _workspace(tmp_path)
    assert "orient" in _run(tmp_path, "--help").output
    helped = _run(tmp_path, "orient", "--help")
    assert helped.exit_code == 0
    for needle in ("--requested-action", "--work-id", "--run-id", "--json", *UNSUPPORTED_ACTIONS):
        assert needle in helped.output


def test_orient_and_resume_json_carry_the_same_query_block(tmp_path: Path) -> None:
    _workspace(tmp_path)
    oriented = _json(_run(tmp_path, "orient", PROJECT, "--json"))
    resumed = _json(_run(tmp_path, "resume", PROJECT, "--json"))
    assert oriented == resumed
    query = oriented["query"]
    assert (query["schema_version"], query["capabilities"]["contract_version"]) == ("continuity-query.v1", "runtime-capabilities.v2")
    assert query["capabilities"]["parking_supported"] is True and query["capabilities"]["preemption_supported"] is False
    assert [(a["action"], a["status"]) for a in query["capabilities"]["actions"]] == list(DECLARED.items())
    assert query["requested_action"] is None
    assert oriented["schema_version"] == "continuity-resume.v2" and "lease_token" not in json.dumps(oriented)


@pytest.mark.parametrize("action", UNSUPPORTED_ACTIONS)
def test_an_asked_action_is_answered_as_declared_with_exit_zero(tmp_path: Path, action: str) -> None:
    _workspace(tmp_path)
    plain = _json(_run(tmp_path, "orient", PROJECT, "--json"))
    asked = _json(_run(tmp_path, "orient", PROJECT, "--requested-action", action, "--json"))
    answer = asked["query"]["requested_action"]
    assert answer is not None
    assert (answer["action"], answer["status"]) == (action, DECLARED[action]) and answer["reason"]
    assert {k: v for k, v in asked.items() if k != "query"} == {k: v for k, v in plain.items() if k != "query"}
    text = _run(tmp_path, "orient", PROJECT, "--requested-action", action)
    assert text.exit_code == 0 and action in text.output and f": {DECLARED[action]}（" in text.output


@pytest.mark.parametrize("asked", ["park", "PAUSE", "NONE", "READY", "PARKED"])
def test_an_unknown_asked_action_is_refused_by_the_command_and_writes_nothing(tmp_path: Path, asked: str) -> None:
    _workspace(tmp_path)
    before = _snapshot(tmp_path)
    refused = _run(tmp_path, "orient", PROJECT, "--requested-action", asked)
    assert refused.exit_code != 0 and "Invalid value" in refused.output
    assert _snapshot(tmp_path) == before
    assert not (tmp_path / ".auto-pm").exists()


def test_the_text_output_states_the_declared_capabilities_for_both_commands(tmp_path: Path) -> None:
    _workspace(tmp_path)
    for command in ("resume", "orient"):
        shown = _run(tmp_path, command, PROJECT)
        assert shown.exit_code == 0, shown.output
        assert "continuity-query.v1" in shown.output
        assert "挂起: 支持" in shown.output and "插队: 不支持" in shown.output and "pm park" in shown.output


def test_neither_command_creates_or_changes_anything_in_a_workspace_without_a_store(tmp_path: Path) -> None:
    _workspace(tmp_path)
    before = _snapshot(tmp_path)
    for args in (("resume", PROJECT, "--json"), ("orient", PROJECT, "--json"), ("orient", PROJECT, "--requested-action", "PARK"), ("orient", PROJECT)):
        assert _run(tmp_path, *args).exit_code == 0
    assert _snapshot(tmp_path) == before
    assert not (tmp_path / ".auto-pm").exists()


def _replaced_answer(root: Path, kind: str) -> ContinuityResume:
    """What a replaced or regressed facade could hand to the command: a Resume that was never validated."""

    good = PmFacadeService(root).resume(project_id=PROJECT)
    assert good.query is not None
    if kind == "legal":
        return good
    if kind == "no-query-block":
        return good.model_copy(update={"query": None})
    fields = {name: getattr(good.query, name) for name in ContinuityQuery.model_fields if name != "schema_version"}
    return good.model_copy(update={"query": ContinuityQuery.model_construct(**fields)})


@pytest.mark.parametrize("kind", ["legal", "no-schema-version", "no-query-block"])
@pytest.mark.parametrize("as_json", [True, False])
@pytest.mark.parametrize("command", ["resume", "orient"])
def test_both_commands_check_the_answer_again_and_print_nothing_when_it_is_broken(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str, as_json: bool, kind: str
) -> None:
    _workspace(tmp_path)
    answer = _replaced_answer(tmp_path, kind)
    before = _snapshot(tmp_path)
    monkeypatch.setattr(PmFacadeService, command, lambda self, **_kwargs: answer)
    shown = _run(tmp_path, command, PROJECT, *(["--json"] if as_json else []))
    if kind == "legal":  # the control: the replaced facade itself is not what makes the command fail
        assert shown.exit_code == 0, shown.output
        assert answer.evidence_id in shown.output and "continuity-query.v1" in shown.output
    else:
        assert shown.exit_code != 0 and ("未通过校验" in shown.output or "缺少 query" in shown.output)
        assert answer.evidence_id not in shown.output and "continuity-resume.v2" not in shown.output  # no half of a success payload
    assert _snapshot(tmp_path) == before


def test_orient_adds_one_read_only_memory_gate_line_without_touching_the_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Memory gate merged into the cockpit: text mode prints the line on stdout, JSON mode on stderr so stdout stays pure JSON; resume does not print it."""

    from auto_pm.infrastructure import memory_gate_status

    _workspace(tmp_path)
    monkeypatch.setattr(
        memory_gate_status, "read_gate_status", lambda **kwargs: memory_gate_status.GateStatus("running", installed_bundle="a" * 64, pinned_bundle="b" * 64)
    )
    before = _snapshot(tmp_path)

    text = _run(tmp_path, "orient", PROJECT)
    as_json = _run(tmp_path, "orient", PROJECT, "--json")
    resumed = _run(tmp_path, "resume", PROJECT)

    assert text.exit_code == 0 and "总闸: 运行中" in text.stdout and "有新版本" in text.stdout
    assert as_json.exit_code == 0 and "总闸" not in as_json.stdout and "总闸: 运行中" in as_json.stderr
    json.loads(as_json.stdout)  # stdout is still one JSON document
    assert "总闸" not in resumed.output
    assert _snapshot(tmp_path) == before and not (tmp_path / ".auto-pm").exists()


def test_orient_prints_nothing_about_the_gate_where_the_gate_does_not_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from auto_pm.infrastructure import memory_gate_status

    _workspace(tmp_path)
    monkeypatch.setattr(memory_gate_status, "read_gate_status", lambda **kwargs: None)

    assert "总闸" not in _run(tmp_path, "orient", PROJECT).output


def test_a_failing_gate_reader_never_stops_orient(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from auto_pm.infrastructure import memory_gate_status

    def broken(**kwargs: object) -> None:
        raise PermissionError("denied")

    _workspace(tmp_path)
    monkeypatch.setattr(memory_gate_status, "read_gate_status", broken)
    result = _run(tmp_path, "orient", PROJECT)

    assert result.exit_code == 0 and "未能读取总闸状态" in result.output


def test_orient_adds_one_read_only_state_backup_line_from_the_local_marker_only(tmp_path: Path) -> None:
    """Ledger off-site backup: no marker -> a warning with the command; a fresh marker -> the age.  Text on stdout, JSON mode on stderr; resume prints nothing."""

    from datetime import UTC, datetime, timedelta

    _workspace(tmp_path)
    before = _snapshot(tmp_path)

    none = _run(tmp_path, "orient", PROJECT)
    none_json = _run(tmp_path, "orient", PROJECT, "--json")
    resumed = _run(tmp_path, "resume", PROJECT)

    assert none.exit_code == 0 and "还没有做过异地备份" in none.stdout and "pm state-backup push" in none.stdout
    assert none_json.exit_code == 0 and "异地备份" not in none_json.stdout and "还没有做过异地备份" in none_json.stderr
    json.loads(none_json.stdout)  # stdout is still one JSON document
    assert "异地备份" not in resumed.output
    assert _snapshot(tmp_path) == before and not (tmp_path / ".auto-pm").exists()  # looking writes nothing

    marker = tmp_path / ".auto-pm" / "cache" / "state-backup-last.json"
    marker.parent.mkdir(parents=True)
    pushed = datetime.now(UTC) - timedelta(hours=2)
    marker.write_text(
        json.dumps({"schema_version": "state-backup-marker.v1", "pushed_at": pushed.isoformat(), "events": 202}), encoding="utf-8"
    )
    fresh = _run(tmp_path, "orient", PROJECT)
    assert fresh.exit_code == 0 and "[账本异地备份] 最近一次 2 小时前" in fresh.stdout and "202 条事件" in fresh.stdout


def test_a_failing_state_backup_reader_never_stops_orient(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import auto_pm.ui.cli.pm as pm_module

    def broken(_root: object) -> None:
        raise PermissionError("denied")

    _workspace(tmp_path)
    monkeypatch.setattr(pm_module, "read_state_backup_status", broken)
    result = _run(tmp_path, "orient", PROJECT)

    assert result.exit_code == 0 and "未能读取备份记录" in result.output


@pytest.mark.parametrize("command", ["orient", "resume"])
def test_d60_the_read_only_locators_do_not_write_the_ai_context_file(tmp_path: Path, command: str) -> None:
    """D-60 said ``pm orient`` rewrote ``.auto-pm/ai_context.json``; in the source it does not, and this keeps it so."""
    _workspace(tmp_path)
    result = CliRunner().invoke(cli, ["-w", str(tmp_path), "pm", command, PROJECT, "--json"])
    assert result.exit_code == 0, result.output
    assert not (tmp_path / ".auto-pm" / "ai_context.json").exists()


def test_orient_says_when_this_clone_has_no_ledger_and_stays_quiet_when_it_has_one(tmp_path: Path) -> None:
    """A cloud clone has no ledger: "work: -" must not read as "nothing open".  Text on stdout, JSON mode on stderr; resume prints nothing."""

    _workspace(tmp_path)
    before = _snapshot(tmp_path)

    text = _run(tmp_path, "orient", PROJECT)
    as_json = _run(tmp_path, "orient", PROJECT, "--json")
    resumed = _run(tmp_path, "resume", PROJECT)

    assert text.exit_code == 0 and "[无账本]" in text.stdout and "claim list" in text.stdout
    assert as_json.exit_code == 0 and "[无账本]" not in as_json.stdout and "[无账本]" in as_json.stderr
    json.loads(as_json.stdout)  # stdout is still one JSON document
    assert "[无账本]" not in resumed.output
    assert _snapshot(tmp_path) == before and not (tmp_path / ".auto-pm").exists()  # looking writes nothing

    from auto_pm.infrastructure.continuity_store import ContinuityStore

    ContinuityStore(tmp_path).initialize("2026-11-07T00:00:00+00:00", "test")
    assert (tmp_path / ".auto-pm" / "continuity.db").is_file()
    with_ledger = _run(tmp_path, "orient", PROJECT)
    assert with_ledger.exit_code == 0 and "[无账本]" not in with_ledger.stdout


def test_orient_adds_one_read_only_presence_line_and_keeps_json_pure_and_writes_nothing(tmp_path: Path) -> None:
    """D-195: another conversation known on this computer is mentioned in one line (stderr in JSON mode); orient itself still writes nothing."""

    import platform

    _workspace(tmp_path)
    folder = tmp_path / ".auto-pm" / "presence"
    folder.mkdir(parents=True)
    now = __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat()
    (folder / "k.json").write_text(
        json.dumps({"schema": "presence.v1", "key": "k", "alias": "trae-123456", "source": "trae", "machine": platform.node(),
                    "pid": __import__("os").getpid(), "where": "control-root", "title": "", "opened_at": now, "seen_at": now}),
        encoding="utf-8",
    )
    before = _snapshot(tmp_path)

    text = _run(tmp_path, "orient", PROJECT)
    as_json = _run(tmp_path, "orient", PROJECT, "--json")

    assert text.exit_code == 0 and "[在场] 本机另有 1 个会话在场" in text.stdout and "trae-123456" in text.stdout
    assert as_json.exit_code == 0 and "[在场]" not in as_json.stdout and "[在场]" in as_json.stderr
    json.loads(as_json.stdout)
    assert _snapshot(tmp_path) == before


def test_orient_prints_no_presence_line_when_nobody_else_is_known(tmp_path: Path) -> None:
    _workspace(tmp_path)
    assert "[在场]" not in _run(tmp_path, "orient", PROJECT).output


# --- D-357：待整理记录在 pm orient / pm resume 里多一栏、多一行；只读 ------------------------------------------------


def _ledger_with_a_note(root: Path, *, by: str = "no-agent-marker") -> str:
    from auto_pm.contracts.intake import IntakeKind
    from auto_pm.infrastructure.continuity_store import ContinuityStore
    from auto_pm.infrastructure.intake_store import IntakeStore

    ContinuityStore(root).initialize("2026-11-13T00:00:00+00:00", "test")
    note, _ = IntakeStore(root).add_note(
        request_id="REQ-NOTE-1", project_id=PROJECT, title="看板字太小", original_words="字太小了，看不清",
        kind_hint=IntakeKind.ITERATION, recorded_by=by,
    )
    return note.note_id


@pytest.mark.parametrize("command", ["orient", "resume"])
def test_d357_json_carries_the_notes_block_and_the_text_adds_one_line(tmp_path: Path, command: str) -> None:
    _workspace(tmp_path)
    empty = _json(_run(tmp_path, command, PROJECT, "--json"))
    assert empty["notes"] == {"waiting": 0, "oldest_note_id": "", "oldest_recorded_by": "", "oldest_created_at": ""}
    assert empty["next_legal_action"] == "USE_INBOX" and "待整理记录" not in _run(tmp_path, command, PROJECT).output

    note_id = _ledger_with_a_note(tmp_path)
    payload = _json(_run(tmp_path, command, PROJECT, "--json"))
    assert payload["next_legal_action"] == "TRIAGE_NOTES"
    assert (payload["notes"]["waiting"], payload["notes"]["oldest_note_id"], payload["notes"]["oldest_recorded_by"]) == (1, note_id, "no-agent-marker")
    assert payload["intake"] == empty["intake"]  # the inbox summary keeps its exact shape (an older reader forbids extras there)
    text = _run(tmp_path, command, PROJECT).output
    assert f"待整理记录: 1 条，最早一条 {note_id}（本机终端（没带 AI 标记） 记于 {payload['notes']['oldest_created_at']}）" in text
    assert "pm inbox add … --from-note <NOTE-ID>" in text and "no-agent-marker" not in text


def test_d357_the_read_only_locators_leave_a_ledger_without_the_notes_table_byte_identical(tmp_path: Path) -> None:
    """验收 12：没有 intake_notes 表的账本上，三条只读命令每跑完一条账本字节都不变，表也没被建出来。"""
    import sqlite3
    from contextlib import closing

    _workspace(tmp_path)
    _ledger_with_a_note(tmp_path)
    db = tmp_path / ".auto-pm" / "continuity.db"
    with closing(sqlite3.connect(db)) as conn:
        conn.execute("DROP TABLE intake_notes")
        conn.commit()
    before = _snapshot(tmp_path)
    for args in ((("orient", PROJECT)), ("orient", PROJECT, "--json"), ("resume", PROJECT, "--json")):
        result = _run(tmp_path, *args)
        assert result.exit_code == 0 and "NOTE-" not in result.output
        assert _snapshot(tmp_path) == before
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='intake_notes'").fetchone() is None
