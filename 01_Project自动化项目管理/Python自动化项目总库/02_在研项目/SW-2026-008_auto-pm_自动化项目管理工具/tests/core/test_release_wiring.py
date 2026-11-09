"""D-146 card 6a: the real ports — ledger reads stay read-only, writes go through main.py, the self-check set is complete and fails closed."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from auto_pm.application.core import release_deploy as rd
from auto_pm.application.core import release_ops as ops
from auto_pm.application.core import release_wiring as rw
from auto_pm.application.core.release_ledger import LedgerError

NEW, OLD, OLDER = "1.3.3-abcdef0", "1.3.3-1234567", "1.3.3-7654321"


class FakeChanges:
    def __init__(self, rows: dict[str, tuple[str, str, str]]) -> None:
        self.rows = rows  # number -> (nature, references, status)

    def list_change_requests(self, project_id: str, status: str | None = None, domain: str | None = None) -> list[Any]:
        return [SimpleNamespace(change_number=n, business_nature=v[0]) for n, v in self.rows.items()]

    def get_change_request(self, change_number: str, project_id: str | None = None) -> Any:
        row = self.rows.get(change_number)
        return None if row is None else SimpleNamespace(references=row[1], status=row[2])


class FakeStore:
    def __init__(self) -> None:
        self.works: dict[str, str] = {}
        self.runs: dict[str, str] = {}
        self.checkpoints: set[str] = set()
        self.broken = False

    def get_work(self, work_id: str) -> Any:
        if self.broken:
            raise RuntimeError("database is locked")
        if work_id not in self.works:
            raise RuntimeError(f"Work 不存在: {work_id}")
        return SimpleNamespace(state=self.works[work_id])

    def find_run(self, run_id: str) -> Any:
        return SimpleNamespace(state=self.runs[run_id]) if run_id in self.runs else None

    def get_checkpoint(self, checkpoint_id: str) -> Any:
        if self.broken:
            raise RuntimeError("database is locked")
        if checkpoint_id not in self.checkpoints:
            raise RuntimeError(f"Checkpoint 不存在: {checkpoint_id}")
        return object()


def _port(tmp_path: Path, rows: dict[str, tuple[str, str, str]] | None = None, run: Any = None, opened: list[Path] | None = None) -> tuple[rw.CockpitLedgerPort, FakeStore]:
    store = FakeStore()
    port = rw.CockpitLedgerPort(
        tmp_path, run=run or (lambda args: (0, "ok")), changes=FakeChanges(rows or {}), store=store,
        station_opener=(opened.append if opened is not None else (lambda p: None)),
    )
    return port, store


def test_find_change_takes_only_the_exact_release_item_and_only_config_changes(tmp_path: Path) -> None:
    rows = {
        "CHG-1": ("CFG", f"RELEASE={NEW}; COMMIT=x", "implementing"),
        "CHG-2": ("CFG", f"RELEASE={NEW}1; COMMIT=x", "draft"),
        "CHG-3": ("FIX", f"RELEASE={NEW}", "draft"),
    }
    port, _store = _port(tmp_path, rows)

    assert port.find_change(NEW) == "CHG-1" and port.find_change("1.3.3-0000000") == ""
    assert port.change_status("CHG-1") == "implementing" and port.change_status("CHG-404") == ""


def test_find_change_refuses_two_change_orders_for_one_release(tmp_path: Path) -> None:
    port, _store = _port(tmp_path, {"CHG-1": ("CFG", f"RELEASE={NEW}", "draft"), "CHG-2": ("CFG", f"RELEASE={NEW}", "draft")})

    with pytest.raises(LedgerError, match="2 张"):
        port.find_change(NEW)


def test_work_run_checkpoint_and_decision_are_read_but_only_does_not_exist_means_missing(tmp_path: Path) -> None:
    port, store = _port(tmp_path)
    store.works["W"], store.runs["R"] = "READY", "RUNNING"
    store.checkpoints.add("C")
    (tmp_path / ".auto-pm" / "decisions").mkdir(parents=True)
    (tmp_path / ".auto-pm" / "decisions" / "DEC-1.json").write_text("{}", encoding="utf-8")

    assert (port.work_state("W"), port.work_state("nope")) == ("READY", None)
    assert (port.run_state("R"), port.run_state("nope")) == ("RUNNING", None)
    assert port.checkpoint_exists("C") and not port.checkpoint_exists("nope")
    assert port.decision_exists("DEC-1") and not port.decision_exists("DEC-2")
    store.broken = True
    with pytest.raises(RuntimeError, match="locked"):
        port.work_state("W")
    with pytest.raises(RuntimeError, match="locked"):
        port.checkpoint_exists("C")


def test_cli_returns_the_output_and_turns_a_failure_into_a_ledger_error(tmp_path: Path) -> None:
    good, _ = _port(tmp_path, run=lambda args: (0, "已创建 CHG-SCPT-2026-9"))
    bad, _ = _port(tmp_path, run=lambda args: (1, "no way"))

    assert good.cli("change", "create") == "已创建 CHG-SCPT-2026-9"
    with pytest.raises(LedgerError, match="退出码 1"):
        bad.cli("change", "create")


def test_a_station_that_exists_is_left_alone_and_a_missing_one_is_opened(tmp_path: Path) -> None:
    opened: list[Path] = []
    port, _ = _port(tmp_path, opened=opened)
    present = tmp_path / "present"
    (present / ".git").mkdir(parents=True)

    port.ensure_station(present)
    port.ensure_station(tmp_path / "missing")

    assert opened == [tmp_path / "missing"]


def test_the_cockpit_runner_returns_exit_code_and_output(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("import sys\nprint('hi', sys.argv[1:])\nsys.exit(3)\n", encoding="utf-8")

    code, output = rw.cockpit_runner(tmp_path)(["a", "b"])

    assert code == 3 and "hi ['a', 'b']" in output


def test_a_build_failure_reaches_deploy_as_a_deploy_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(root: Path, repo: Path, commit: str) -> dict[str, Any]:
        raise ops.ReleaseOpsError("slot exists")

    monkeypatch.setattr(ops, "build", boom)
    adapter = rw.ReleaseOpsAdapter(tmp_path, tmp_path, "a" * 40, NEW, lambda root: {})

    with pytest.raises(rd.DeployError, match="slot exists"):
        adapter.build()


def test_the_manifest_entry_hash_is_the_one_build_reports(tmp_path: Path) -> None:
    container = ops.container_of(tmp_path)
    container.mkdir(parents=True)
    entry = {"files": [{"path": "a.py", "sha256": "1" * 64}], "built_at": "t"}
    (container / "deployment_manifest.json").write_text(json.dumps({"releases": {NEW: entry}}), encoding="utf-8")
    expected = hashlib.sha256(json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    adapter = rw.ReleaseOpsAdapter(tmp_path, tmp_path, "a" * 40, NEW, lambda root: {})

    assert adapter.manifest_entry_sha256(NEW) == expected
    (container / "releases" / NEW).mkdir(parents=True)
    assert adapter.is_built(NEW) and not adapter.is_built(OLD)


# --- the self-check set -------------------------------------------------------------------------------------------------------------


class Env:
    """A control root with a hook, a database and the two files the checks need; ``run``/``execute`` record what they were asked."""

    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path / "root"
        (self.root / ".git" / "hooks").mkdir(parents=True)
        (self.root / ".git" / "hooks" / "pre-commit").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        (self.root / ".auto-pm").mkdir()
        db = sqlite3.connect(self.root / ".auto-pm" / "continuity.db")
        db.execute("create table t(x)")
        db.execute("insert into t values (1)")
        db.commit()
        db.close()
        self.card = tmp_path / "card.md"
        self.card.write_text("card", encoding="utf-8")
        self.drill = tmp_path / "drill.py"
        self.drill.write_text("# drill", encoding="utf-8")
        self.runs: list[list[str]] = []
        self.execs: list[list[str]] = []
        self.run_reply: dict[str, tuple[int, str]] = {}
        self.exec_reply: dict[str, tuple[int, str]] = {}
        self.seen: dict[str, Any] = {"configured_release_id": NEW, "effective_release_id": NEW}

    def run(self, args: Sequence[str]) -> tuple[int, str]:
        self.runs.append(list(args))
        if args[:2] == ["ledger", "reconcile"]:
            return self.run_reply.get("ledger", (0, rw.LEDGER_CLEAN))
        if args[:2] == ["pm", "orient"] and "--json" in args:
            return self.run_reply.get("orient", (0, '{"conflicts": []}'))
        return self.run_reply.get(" ".join(args), (0, ""))

    def execute(self, argv: Sequence[str], cwd: Path) -> tuple[int, str]:
        self.execs.append(list(argv))
        key = argv[0] if argv[0] != "sh" else "hook"
        if "-I" in argv:
            key = "drill"
        reply = self.exec_reply.get(key)
        if reply is not None:
            return reply
        return (0, '{"events_total": 5, "chain_breaks": 0, "run_activity_fail": []}') if key == "drill" else (0, "")

    def checks(self) -> dict[str, rd.SelfCheck]:
        return rw.build_self_checks(
            root=self.root, release_id=NEW, old_release=OLD, older_release=OLDER, run=self.run, identity=lambda root: self.seen,
            card_file=self.card, drill_script=self.drill, execute=self.execute,
        )


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def test_the_set_has_exactly_the_required_names(env: Env) -> None:
    assert set(env.checks()) == set(rd.REQUIRED_SELF_CHECKS)


def test_a_missing_card_file_or_drill_script_refuses_to_build_the_set(env: Env) -> None:
    env.card.unlink()
    with pytest.raises(rw.WiringError, match="卡文件"):
        env.checks()
    env.card.write_text("c", encoding="utf-8")
    env.drill.unlink()
    with pytest.raises(rw.WiringError, match="演练脚本"):
        env.checks()


def test_identity_check_needs_the_new_release_both_configured_and_loaded(env: Env) -> None:
    assert env.checks()["identity"]()[0]
    env.seen = {"configured_release_id": NEW, "effective_release_id": OLD}
    assert not env.checks()["identity"]()[0]


def test_help_and_smoke_checks_pass_on_exit_zero_and_clean_orient(env: Env) -> None:
    checks = env.checks()

    assert checks["help pm handoff"]()[0] and checks["smoke pm orient SW-2026-008"]()[0]
    assert ["pm", "handoff", "--help"] in env.runs and ["pm", "orient", "SW-2026-008", "--json"] in env.runs
    env.run_reply["pm handoff --help"] = (2, "no such command")
    env.run_reply["orient"] = (0, 'log line\n{"conflicts": ["DIVERGENCE"]}')
    assert not checks["help pm handoff"]()[0] and not checks["smoke pm orient SYS-2026-001"]()[0]
    env.run_reply["orient"] = (0, "not json at all")
    assert not checks["smoke pm orient SYS-2026-001"]()[0]


def test_the_smoke_check_reads_the_json_between_launcher_lines_and_warnings(env: Env) -> None:
    """Real output of ``main.py pm orient`` (2026-11-08 dry run): a launcher line before the JSON and a control-root sync warning after it."""

    noisy = 'launcher: release verified\n{"conflicts": [], "context": {"x": 1}}\n⚠ 控制根同步提示：落后 main 2 个提交 {sync}\n'
    env.run_reply["orient"] = (0, noisy)
    assert env.checks()["smoke pm orient SW-2026-008"]()[0]
    env.run_reply["orient"] = (0, noisy.replace('"conflicts": []', '"conflicts": ["DIVERGENCE"]'))
    assert not env.checks()["smoke pm orient SW-2026-008"]()[0]
    assert rw.first_json_object("{} {\"a\": 1}") == {"a": 1} and rw.first_json_object("no json {") is None


def test_every_command_the_checks_run_exists_in_the_real_command_tree(env: Env) -> None:
    """The fake runner cannot tell a wrong command name from a right one (the first real dry run found ``cli implementation-card``)."""

    import click

    from auto_pm.ui.cli.__main__ import cli

    for name, check in env.checks().items():
        if name.startswith(("help ", "smoke ", "ledger ")) or name == "card precheck":
            check()
    assert env.runs
    for argv in env.runs:
        command: click.Command = cli
        for token in argv:
            if token.startswith("-") or not isinstance(command, click.Group):
                break
            child = command.get_command(click.Context(command), token)
            if child is None:
                break
            command = child
        else:
            continue
        assert command is not cli and command.name in argv, f"main.py {' '.join(argv)}：命令树里找不到这条"


def test_ledger_check_needs_the_clean_line_and_never_passes_fix(env: Env) -> None:
    checks = env.checks()

    assert checks["ledger SW-2026-008"]()[0]
    assert all("--fix" not in call for call in env.runs)
    env.run_reply["ledger"] = (0, "台账缺失: 1 条, 台账多余(孤儿): 0 条, 状态不一致: 0 条")
    assert not checks["ledger SW-2026-009"]()[0]
    env.run_reply["ledger"] = (1, rw.LEDGER_CLEAN)
    assert not checks["ledger DJ-2026-005"]()[0]


def test_card_precheck_runs_the_precheck_command_on_the_card_file(env: Env) -> None:
    checks = env.checks()

    assert checks["card precheck"]()[0]
    assert ["implementation-card", "precheck", "--card-file", str(env.card)] in env.runs
    env.run_reply[f"implementation-card precheck --card-file {env.card}"] = (1, "bad card")
    assert not checks["card precheck"]()[0]


def test_hook_dry_run_needs_a_hook_an_empty_index_and_a_zero_exit(env: Env) -> None:
    checks = env.checks()
    assert checks["pre-commit hook dry run"]()[0]
    assert ["sh", ".git/hooks/pre-commit"] in env.execs

    env.exec_reply["git"] = (0, "a.py\n")
    assert not checks["pre-commit hook dry run"]()[0], "a dirty index makes the dry run untrustworthy"
    env.exec_reply.pop("git")
    env.exec_reply["hook"] = (1, "lint failed")
    assert not checks["pre-commit hook dry run"]()[0]
    (env.root / ".git" / "hooks" / "pre-commit").unlink()
    assert not checks["pre-commit hook dry run"]()[0], "no hook is a failure, not a pass"


def test_event_chain_drill_runs_on_a_copy_and_needs_no_breaks_and_no_run_activity_failures(env: Env) -> None:
    before = (env.root / ".auto-pm" / "continuity.db").read_bytes()
    checks = env.checks()

    assert checks["event chain drill"]()[0]
    drill_call = next(c for c in env.execs if "-I" in c)
    assert drill_call[3] == str(env.drill) and Path(drill_call[4]).name == NEW and Path(drill_call[4]).parent.name == "releases"
    assert not Path(drill_call[5]).exists(), "the scratch copy is removed"
    assert (env.root / ".auto-pm" / "continuity.db").read_bytes() == before, "the live database is only read"
    for bad in ('{"chain_breaks": 2, "run_activity_fail": []}', '{"chain_breaks": 0, "run_activity_fail": ["R1"]}',
                '{"chain_breaks": 0, "run_activity_fail": [], "work_run_read_error": "x"}', "garbage"):
        env.exec_reply["drill"] = (0, bad)
        assert not checks["event chain drill"]()[0], bad
    env.exec_reply["drill"] = (1, '{"chain_breaks": 0, "run_activity_fail": []}')
    assert not checks["event chain drill"]()[0], "a non-zero exit fails even with a clean report"


def test_event_chain_drill_fails_without_a_database(env: Env) -> None:
    checks = env.checks()
    (env.root / ".auto-pm" / "continuity.db").unlink()

    assert not checks["event chain drill"]()[0]


def test_a_manifest_that_cannot_be_read_becomes_a_deploy_error(tmp_path: Path) -> None:
    adapter = rw.ReleaseOpsAdapter(tmp_path, tmp_path, "a" * 40, NEW, lambda root: {})
    with pytest.raises(rd.DeployError, match="读不出清单"):
        adapter.manifest_entry_sha256(NEW)  # no manifest file at all
    container = ops.container_of(tmp_path)
    container.mkdir(parents=True)
    (container / "deployment_manifest.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(rd.DeployError, match="读不出清单"):
        adapter.manifest_entry_sha256(NEW)
    (container / "deployment_manifest.json").write_text(json.dumps({"releases": {}}), encoding="utf-8")
    with pytest.raises(rd.DeployError, match="读不出清单"):
        adapter.manifest_entry_sha256(NEW)  # the release is not in it


def test_cockpit_identity_reads_the_four_fields_and_the_conflict_codes_from_a_fresh_process(tmp_path: Path) -> None:
    payload = {"context": {"configured_release_id": NEW, "effective_release_id": NEW, "runtime_load_path": "p", "runtime_fallback_reason": "", "other": 1},
               "conflicts": [{"code": "DIVERGENCE"}, "PLAIN"]}

    def fake(argv: Sequence[str], cwd: Path) -> tuple[int, str]:
        assert list(argv)[1:3] == ["-B", str(tmp_path / "main.py")] and list(argv)[-4:-1] == ["pm", "resume", "SW-2026-008"] or list(argv)[-3:] == ["resume", "SW-2026-008", "--json"]
        return 0, "log line\n" + json.dumps(payload)

    seen = rw.cockpit_identity(tmp_path, run=fake)

    assert seen["configured_release_id"] == NEW and seen["effective_release_id"] == NEW and "other" not in seen
    assert seen["conflicts"] == ["DIVERGENCE", "PLAIN"]
    assert rw.cockpit_identity(tmp_path, run=lambda a, c: (1, "boom")) == {}
    assert rw.cockpit_identity(tmp_path, run=lambda a, c: (0, "no json")) == {}
    assert rw.cockpit_identity(tmp_path, run=lambda a, c: (0, "{broken")) == {}


def test_plan_for_binds_the_release_to_its_own_evidence_station_and_paths(tmp_path: Path) -> None:
    container = ops.container_of(tmp_path)
    container.mkdir(parents=True)
    (container / "active_release.json").write_text(json.dumps({"release_id": OLD}), encoding="utf-8")
    report = SimpleNamespace(release_id=NEW, commit="a" * 40)
    from datetime import UTC, datetime

    plan, backup = rw.plan_for(tmp_path, report, approver="fubai", confirm_ref="user-confirmation:cmsg_001", now=datetime(2026, 11, 9, 1, 2, 3, tzinfo=UTC))

    assert plan.old_release == OLD and plan.release_id == NEW and plan.commit == "a" * 40
    assert plan.evidence_dir == tmp_path / ".auto-pm" / "reports" / f"release-deploy-{NEW}"
    assert backup == plan.evidence_dir / "pointer_backup_20261109T010203Z"
    assert plan.station.parent == tmp_path / ".auto-pm" / "worktrees"
    assert f"00_Infrastructure/auto_pm/releases/{NEW}" in plan.paths and "00_Infrastructure/auto_pm/active_release.json" in plan.paths
    with pytest.raises(LedgerError, match="用户确认引用"):
        rw.plan_for(tmp_path, report, approver="fubai", confirm_ref="yes")


# --- D-173: real_deploy puts the right things into the right slots (the audit swapped the pointers and 50 tests stayed green) ---


def _container_with(tmp_path: Path, active: str, previous: str) -> None:
    container = ops.container_of(tmp_path)
    container.mkdir(parents=True)
    (container / "active_release.json").write_text(json.dumps({"release_id": active}), encoding="utf-8")
    (container / "previous_release.json").write_text(json.dumps({"release_id": previous}), encoding="utf-8")


def _capture_real_deploy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    monkeypatch.setattr("auto_pm.domain.change.change_service.ChangeService", lambda root: SimpleNamespace(root=root))
    monkeypatch.setattr("auto_pm.infrastructure.continuity_store.ContinuityStore", lambda root: SimpleNamespace(root=root))

    def fake_checks(**kwargs: Any) -> dict[str, Any]:
        seen["checks"] = kwargs
        return {"marker": object()}

    def fake_deploy(plan: Any, **kwargs: Any) -> rd.DeployResult:
        seen["plan"], seen["deploy"] = plan, kwargs
        return rd.DeployResult(plan.release_id, "CHG-SCPT-2026-1", str(kwargs["backup"]), str(tmp_path / "receipt.json"))

    monkeypatch.setattr(rw, "build_self_checks", fake_checks)
    monkeypatch.setattr(rd, "deploy", fake_deploy)
    return seen


def test_real_deploy_hands_each_pointer_to_the_right_slot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _container_with(tmp_path, active=OLD, previous=OLDER)
    seen = _capture_real_deploy(tmp_path, monkeypatch)
    card, drill = tmp_path / "card.md", tmp_path / "drill.py"
    card.write_text("c", encoding="utf-8")
    drill.write_text("d", encoding="utf-8")
    report = SimpleNamespace(release_id=NEW, commit="b" * 40)

    result = rw.real_deploy(tmp_path, report, approver="fubai", confirm_ref="user-confirmation:cmsg_001", card_file=card, drill_script=drill)

    plan, deploy_args, check_args = seen["plan"], seen["deploy"], seen["checks"]
    assert plan.old_release == OLD and plan.release_id == NEW and plan.commit == "b" * 40
    assert check_args["release_id"] == NEW and check_args["old_release"] == OLD and check_args["older_release"] == OLDER, "new / old / older must not be shuffled"
    assert check_args["card_file"] == card and check_args["drill_script"] == drill and check_args["root"] == tmp_path
    adapter = deploy_args["ops"]
    assert adapter.active_release() == OLD, "the adapter reads the live active pointer"
    assert deploy_args["backup"].parent == plan.evidence_dir and deploy_args["backup"].name.startswith("pointer_backup_")
    assert deploy_args["rollback_command"] == f"main.py release rollback {deploy_args['backup']}"
    assert OLD in deploy_args["background"] and NEW in deploy_args["background"]
    assert deploy_args["checks"] is not None and deploy_args["preflight"] is report
    assert result.backup == str(deploy_args["backup"])


def test_the_backup_a_real_deploy_makes_is_one_a_rollback_will_accept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """D-172 and D-173 meet here: the folder the deploy prints in its rollback command must be inside the folder rollback trusts."""

    _container_with(tmp_path, active=OLD, previous=OLDER)
    seen = _capture_real_deploy(tmp_path, monkeypatch)
    card, drill = tmp_path / "card.md", tmp_path / "drill.py"
    card.write_text("c", encoding="utf-8")
    drill.write_text("d", encoding="utf-8")

    rw.real_deploy(tmp_path, SimpleNamespace(release_id=NEW, commit="c" * 40), approver="fubai", confirm_ref="user-confirmation:cmsg_001", card_file=card, drill_script=drill)

    ops._check_backup_inside_reports(tmp_path, seen["deploy"]["backup"])  # noqa: SLF001 - the contract between the two modules


def test_the_cockpit_identity_ignores_the_output_of_a_failed_process(tmp_path: Path) -> None:
    good_looking = json.dumps({"context": {"configured_release_id": NEW, "effective_release_id": NEW}, "conflicts": []})

    assert rw.cockpit_identity(tmp_path, run=lambda argv, cwd: (3, good_looking)) == {}
