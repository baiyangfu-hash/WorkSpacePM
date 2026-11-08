"""D-146 card 3: the deploy bookkeeping is resumable, never invents an approval, and writes a receipt."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_pm.application.core import release_ledger as rl

CONFIRM = "user-confirmation:cmsg_test_001"
PATHS = ("00_Infrastructure/auto_pm/deployment_manifest.json", "00_Infrastructure/auto_pm/active_release.json")


class FakeLedger:
    """Behaves like the ledger for the commands the module issues; ``crash_at`` raises on the n-th command (1-based)."""

    def __init__(self, crash_at: int | None = None) -> None:
        self.commands: list[list[str]] = []
        self.change = ""
        self.change_state = ""
        self.decisions: set[str] = set()
        self.work: str | None = None
        self.run: str | None = None
        self.checkpoints: set[str] = set()
        self.stations: list[Path] = []
        self.crash_at = crash_at
        self.created = 0
        self.references: dict[str, str] = {}

    def cli(self, *args: str) -> str:
        if self.crash_at is not None and len(self.commands) + 1 == self.crash_at:
            raise RuntimeError("killed")
        self.commands.append(list(args))
        head = args[:2]
        if head == ("change", "create"):
            self.created += 1
            self.change_state = "draft"
            self.change = f"CHG-SCPT-2026-9{self.created:02d}"
            self.references[self.change] = args[args.index("--references") + 1]
            return f"已创建 {self.change}"
        if head == ("change", "transition"):
            self.change_state = args[args.index("--to") + 1]
        elif head == ("decision", "create"):
            self.decisions.add(args[args.index("--decision-id") + 1])
        elif args[:3] == ("continuity", "work", "create"):
            self.work = "PLANNED"
        elif args[:3] == ("continuity", "work", "authorize"):
            self.work = "READY"
        elif args[:3] == ("continuity", "work", "transition"):
            self.work = args[args.index("--to") + 1]
        elif args[:3] == ("continuity", "run", "start"):
            self.run = "READY"
        elif args[:3] == ("continuity", "run", "transition"):
            self.run = args[args.index("--to") + 1]
        elif args[:3] == ("continuity", "checkpoint", "create"):
            self.checkpoints.add(args[args.index("--checkpoint-id") + 1])
        return ""

    def find_change(self, release_id: str) -> str:
        return rl.pick_change(release_id, list(self.references.items()))

    def change_status(self, change_id: str) -> str:
        return self.change_state

    def decision_exists(self, decision_id: str) -> bool:
        return decision_id in self.decisions

    def work_state(self, work_id: str) -> str | None:
        return self.work

    def run_state(self, run_id: str) -> str | None:
        return self.run

    def checkpoint_exists(self, checkpoint_id: str) -> bool:
        return checkpoint_id in self.checkpoints

    def ensure_station(self, path: Path) -> None:
        self.stations.append(path)

    def verbs(self) -> list[str]:
        return [" ".join(c[:3]) for c in self.commands]


def _plan(tmp_path: Path, confirm: str = CONFIRM) -> rl.DeployPlan:
    return rl.DeployPlan(
        release_id="1.3.3-abcdef0", old_release="1.3.3-1234567", commit="a" * 40, confirm_ref=confirm, approver="fubai",
        paths=PATHS, station=tmp_path / "station", evidence_dir=tmp_path / "evidence",
    )


def _open(plan: rl.DeployPlan, port: FakeLedger) -> rl.Books:
    return rl.open_books(plan, port, background="发布", necessity="新版本才生效")


def _close(plan: rl.DeployPlan, port: FakeLedger, change_id: str) -> rl.Books:
    return rl.close_books(plan, port, change_id=change_id, evidence=["release=x"], conclusion="验收通过")


def test_without_a_user_confirmation_reference_nothing_is_planned() -> None:
    for bad in ("", "approved", "user-confirmation:", "user-confirmation:abc", "agent-says-yes", "cmsg_test_001_long_enough", "confirmation:cmsg_test_001"):
        with pytest.raises(rl.LedgerError, match="用户确认引用"):
            _plan(Path("/x"), bad)


def test_open_books_walks_the_change_order_to_implementing_and_the_run_to_running(tmp_path: Path) -> None:
    port, plan = FakeLedger(), _plan(tmp_path)

    books = _open(plan, port)

    assert books.change_id == "CHG-SCPT-2026-901" and port.change_state == "implementing"
    assert port.decisions == {plan.decision_id} and port.work == "IN_PROGRESS" and port.run == "RUNNING"
    assert port.stations == [plan.station]
    approved = [c for c in port.commands if c[:2] == ["change", "transition"] and c[c.index("--to") + 1] == "approved"]
    assert len(approved) == 1 and approved[0][approved[0].index("--approval-evidence-ref") + 1] == CONFIRM
    others = [c for c in port.commands if c[:2] == ["change", "transition"] and c not in approved]
    assert all("--approval-evidence-ref" not in c for c in others), "only the approval carries the user's reference"


def test_a_second_open_changes_nothing(tmp_path: Path) -> None:
    port, plan = FakeLedger(), _plan(tmp_path)
    _open(plan, port)
    done = len(port.commands)

    again = _open(plan, port)

    assert len(port.commands) == done and again.steps == []
    assert port.created == 1, "never a second change order"


@pytest.mark.parametrize("crash_at", range(1, 12))
def test_a_run_killed_at_any_command_resumes_without_repeating_a_finished_step(tmp_path: Path, crash_at: int) -> None:
    port, plan = FakeLedger(crash_at=crash_at), _plan(tmp_path)
    with pytest.raises(RuntimeError, match="killed"):
        _open(plan, port)
    port.crash_at = None

    _open(plan, port)

    assert port.created == 1
    assert port.change_state == "implementing" and port.work == "IN_PROGRESS" and port.run == "RUNNING"
    counts = {verb: port.verbs().count(verb) for verb in set(port.verbs())}
    for once in ("change create", "decision create", "continuity work create", "continuity work authorize", "continuity run start"):
        assert counts.get(once, 0) <= 1, f"{once} ran {counts[once]} times after a crash at {crash_at}"


def test_close_books_finishes_checkpoint_run_work_and_change_in_order(tmp_path: Path) -> None:
    port, plan = FakeLedger(), _plan(tmp_path)
    change = _open(plan, port).change_id

    books = _close(plan, port, change)

    assert port.checkpoints == {plan.checkpoint_id} and port.run == "SUCCEEDED" and port.work == "CLOSED" and port.change_state == "completed"
    assert books.steps[0] == "checkpoint create"
    completed = [c for c in port.commands if c[:2] == ["change", "transition"] and c[c.index("--to") + 1] == "completed"][0]
    assert "--verification-conclusion" in completed and "验收通过" in completed


def test_close_books_is_resumable_and_idempotent(tmp_path: Path) -> None:
    port, plan = FakeLedger(), _plan(tmp_path)
    change = _open(plan, port).change_id
    port.crash_at = len(port.commands) + 4
    with pytest.raises(RuntimeError, match="killed"):
        _close(plan, port, change)
    port.crash_at = None

    _close(plan, port, change)
    done = len(port.commands)
    _close(plan, port, change)

    assert port.change_state == "completed" and port.work == "CLOSED" and len(port.commands) == done
    assert port.verbs().count("continuity checkpoint create") == 1


def test_close_books_refuses_when_the_run_is_not_where_it_should_be(tmp_path: Path) -> None:
    port, plan = FakeLedger(), _plan(tmp_path)
    change = _open(plan, port).change_id
    port.run = "FAILED"

    with pytest.raises(rl.LedgerError, match="SUCCEEDED"):
        _close(plan, port, change)


def test_a_change_order_in_a_state_off_the_path_is_an_error_not_a_guess(tmp_path: Path) -> None:
    port, plan = FakeLedger(), _plan(tmp_path)
    _open(plan, port)
    port.change_state = "rejected"

    with pytest.raises(rl.LedgerError, match="不在可续的路径"):
        _close(plan, port, "CHG-SCPT-2026-901")


def test_the_receipt_lists_every_identifier_and_the_rollback_command(tmp_path: Path) -> None:
    plan = _plan(tmp_path)

    path = rl.write_receipt(plan, change_id="CHG-SCPT-2026-901", backup="/b", entry_sha256="e" * 64, checks_sha256="c" * 64, rollback_command="main.py release rollback /b")

    receipt = json.loads(path.read_text(encoding="utf-8"))
    assert receipt["release"] == plan.release_id and receipt["previous"] == plan.old_release
    assert receipt["run"] == f"{plan.run_id} SUCCEEDED" and receipt["work"] == f"{plan.work_id} CLOSED"
    assert receipt["change"] == "CHG-SCPT-2026-901 completed" and receipt["confirmation"] == CONFIRM
    assert receipt["rollback_command"].endswith("/b") and "database rollback" in receipt["not_authorized"]


def test_a_resume_after_utc_midnight_reuses_the_first_decision_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import datetime as dt

    class _Day1(dt.datetime):
        @classmethod
        def now(cls, tz: object = None) -> _Day1:
            return cls(2026, 11, 8, 23, 59, tzinfo=dt.UTC)

    class _Day2(_Day1):
        @classmethod
        def now(cls, tz: object = None) -> _Day2:
            return cls(2026, 11, 9, 0, 1, tzinfo=dt.UTC)

    port = FakeLedger(crash_at=8)  # killed after the Decision was made (or just before it), before the Run exists
    monkeypatch.setattr(rl, "datetime", _Day1)
    first = _plan(tmp_path)
    with pytest.raises(RuntimeError, match="killed"):
        _open(first, port)
    port.crash_at = None
    monkeypatch.setattr(rl, "datetime", _Day2)

    second = _plan(tmp_path)
    _open(second, port)

    assert second.decision_id == first.decision_id and "20261108" in second.decision_id
    assert port.decisions == {first.decision_id}, "one Decision, not one per calendar day"


def test_a_kill_between_change_create_and_the_state_file_does_not_create_a_second_change_order(tmp_path: Path) -> None:
    port, plan = FakeLedger(), _plan(tmp_path)
    _open(plan, port)
    plan.state_file.unlink()  # the process died after "change create" and before state.json was written
    port.change_state = "draft"
    port.decisions.clear()
    port.work = None
    port.run = None

    books = _open(_plan(tmp_path), port)

    assert port.created == 1 and books.change_id == port.change
    assert any(step.startswith("change adopt") for step in books.steps)


def test_close_books_stops_with_an_error_when_the_work_state_does_not_advance(tmp_path: Path) -> None:
    port, plan = FakeLedger(), _plan(tmp_path)
    books = _open(plan, port)
    original = port.cli

    def stuck(*args: str) -> str:
        if args[:3] == ("continuity", "work", "transition"):
            port.commands.append(list(args))
            return ""  # accepted, yet the state never moves
        return original(*args)

    port.cli = stuck  # type: ignore[method-assign]

    with pytest.raises(rl.LedgerError, match="Work"):
        _close(plan, port, books.change_id)

    assert len([c for c in port.commands if c[:3] == ["continuity", "work", "transition"]]) <= len(rl.WORK_CLOSE) + 1


def test_another_releases_change_order_is_never_adopted(tmp_path: Path) -> None:
    port = FakeLedger()
    other = rl.DeployPlan(
        release_id="1.3.3-abcdef012", old_release="1.3.3-1234567", commit="b" * 40, confirm_ref=CONFIRM, approver="fubai",
        paths=PATHS, station=tmp_path / "s2", evidence_dir=tmp_path / "e2",
    )
    first = _open(other, port).change_id  # a change order for a release whose id merely starts like ours

    books = _open(_plan(tmp_path), port)

    assert port.created == 2 and books.change_id != first and not any(step.startswith("change adopt") for step in books.steps)


def test_pick_change_matches_the_release_item_exactly_and_refuses_two() -> None:
    rows = [("CHG-1", "RELEASE=1.3.3-abcdef0; COMMIT=x; PREVIOUS=y; user-confirmation:a"), ("CHG-2", "RELEASE=1.3.3-abcdef01; COMMIT=x")]
    assert rl.pick_change("1.3.3-abcdef0", rows) == "CHG-1"
    assert rl.pick_change("1.3.3-abc", rows) == "" and rl.pick_change("1.3.3-abcdef0", []) == ""
    with pytest.raises(rl.LedgerError, match="2 张"):
        rl.pick_change("1.3.3-abcdef0", [*rows, ("CHG-3", "COMMIT=z; RELEASE=1.3.3-abcdef0")])


def test_an_explicit_decision_id_is_used_and_kept(tmp_path: Path) -> None:
    port = FakeLedger()
    plan = rl.DeployPlan(
        release_id="1.3.3-abcdef0", old_release="1.3.3-1234567", commit="a" * 40, confirm_ref=CONFIRM, approver="fubai",
        paths=PATHS, station=tmp_path / "station", evidence_dir=tmp_path / "evidence", decision_id="DEC-20260101-CUSTOM01",
    )

    _open(plan, port)

    assert port.decisions == {"DEC-20260101-CUSTOM01"} and plan.decision_id == "DEC-20260101-CUSTOM01"
    assert _plan(tmp_path).decision_id == "DEC-20260101-CUSTOM01", "a later plan for the same release reads it back"


def test_a_finished_change_order_for_this_release_is_reported_as_such(tmp_path: Path) -> None:
    port, plan = FakeLedger(), _plan(tmp_path)
    _open(plan, port)
    port.change_state = "completed"

    with pytest.raises(rl.LedgerError, match="已有一张走完"):
        _open(plan, port)
