"""V05-C: the whole cockpit, driven through its real window, from a typed goal to the final acceptance, for a Python and a PLC project.

Two ways to run the same two tests (the same code path, nothing is skipped):

* default: the execution agent is a scripted stand-in (a real child process that speaks the codex handshake and writes the real files), so the test is free and
  runs in every regression group;
* ``V05C_MODE=real``: the execution agent is the real ``codex exec`` with the explicitly named model ``gpt-6.1-sol`` (never the configured default). Every call is
  counted in a budget ledger (at most 20 calls and 90 minutes in total, enforced before a call starts); ``V05C_CODEX_EXE`` names the codex executable,
  ``V05C_BUDGET_LEDGER`` the one global ledger file and ``V05C_EVIDENCE_DIR`` receives the screenshots and the event lists.

The window is the real ``boss_main.qml`` on Qt's offscreen platform, built through the production pieces (cockpit service, bridge, real thread pool, shutdown). The goal is
typed into the window's fields and every decision is a click on the window's own buttons. The PM side (turning the saved draft into a scope card) is the production
facade call a PM agent makes. The PLC project is the pinned, healed benchmark DJ-2026-005 in a throw-away repository; nothing is compiled or sent to a controller.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
from PySide6.QtCore import QMetaObject, QObject, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtWidgets import QApplication

from auto_pm.application.core.local_execution_orchestrator import LocalExecutionOrchestrator
from auto_pm.application.core.pm_cockpit_service import PmCockpitService
from auto_pm.contracts.continuity import RunState, WorkState
from auto_pm.contracts.execution_adapter import ExecutionAdapterKind
from auto_pm.contracts.mission import MissionState
from auto_pm.contracts.pm_facade import PlanningExecutionGrant
from auto_pm.domain.change.change_service import ChangeService
from auto_pm.domain.change.ledger_reconciler import LedgerReconciler
from auto_pm.domain.plc import doc_consistency as dc
from auto_pm.infrastructure.continuity_store import ContinuityStore
from auto_pm.infrastructure.local_executor import (
    LocalCodexExecutor,
    LocalExecutionHandle,
    LocalExecutionRequest,
    LocalExecutionResult,
)
from auto_pm.ui.boss_qml_window import shutdown_cockpit
from auto_pm.ui.qml.bridges.pm_cockpit_bridge import PmCockpitBridge
from tests.core.test_pm_run_e2e import (
    CALC,
    CALC_TEST,
    FIXED_CALC,
    GOOD_TESTS,
    VERIFIED_SENTENCE,
)
from tests.core.test_pm_run_e2e import (
    PROJECT_ID as PY_PROJECT_ID,
)
from tests.core.test_pm_run_e2e import (
    _build_workspace as build_python_workspace,
)
from tests.e2e import test_pmf_plc as plc
from tests.plan_checklist_support import full_checklist
from tests.qml.test_boss_cockpit_view import _items_named, _texts

if TYPE_CHECKING:
    from auto_pm.application.core.pm_facade_service import PmFacadeService
else:
    from auto_pm.application.core.pm_facade_service import PmFacadeService

_QML = Path(__file__).resolve().parents[2] / "auto_pm" / "ui" / "qml" / "boss_main.qml"
MODEL = "gpt-6.1-sol"
# User authorization of 2026-10-08: only the model child process runs with the unelevated Windows sandbox (the elevated one fails to provision because the configured node_repl
# component locks its own runtime file); no configuration file or system setting is changed, and the sandbox itself stays on (workspace-write).
SANDBOX_OVERRIDE = 'windows.sandbox="unelevated"'
REAL = os.environ.get("V05C_MODE") == "real"
CODEX_EXE = os.environ.get("V05C_CODEX_EXE", "")
EVIDENCE_ENV = os.environ.get("V05C_EVIDENCE_DIR", "")
LEDGER_ENV = os.environ.get("V05C_BUDGET_LEDGER", "")
MAX_CALLS, MAX_SECONDS = 20, 90 * 60
APPROVER = "fubai"


class CallBudgetError(RuntimeError):
    """Raised before a model call would exceed the authorised call count or time."""


class _Budget:
    """A ledger on disk, so the cap holds across tests and across processes."""

    def __init__(self, path: Path, *, max_calls: int = MAX_CALLS, max_seconds: float = MAX_SECONDS) -> None:
        self._path = path
        self._max_calls = max_calls
        self._max_seconds = max_seconds
        if not path.exists():
            self._save({"calls": 0, "seconds": 0.0, "entries": []})

    def _load(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self._path.read_text(encoding="utf-8")))

    def _save(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")

    def begin(self, label: str) -> int:
        data = self._load()
        if data["calls"] >= self._max_calls:
            raise CallBudgetError(f"call {data['calls'] + 1} would exceed the {self._max_calls}-call budget")
        if data["seconds"] >= self._max_seconds:
            raise CallBudgetError(f"the {self._max_seconds:.0f}-second budget is used up")
        data["calls"] += 1
        data["entries"].append({"call": data["calls"], "label": label, "started_at": datetime.now(UTC).isoformat(), "model": MODEL})
        self._save(data)
        return int(data["calls"])

    def end(self, call: int, seconds: float, status: str, requested_model: str, command: tuple[str, ...]) -> None:
        data = self._load()
        data["seconds"] = float(data["seconds"]) + seconds
        entry = next(item for item in data["entries"] if item["call"] == call)
        entry.update({"seconds": round(seconds, 1), "status": status, "requested_model": requested_model, "command": list(command)})
        self._save(data)

    def totals(self) -> tuple[int, float]:
        data = self._load()
        return int(data["calls"]), float(data["seconds"])


class _CountingExecutor(LocalCodexExecutor):
    """The production executor, with every start counted against the budget before anything is launched."""

    def __init__(self, budget: _Budget, label: str, *, command_prefix: tuple[str, ...]) -> None:
        super().__init__(command_prefix=command_prefix)
        self._budget = budget
        self._label = label
        self._call = 0
        self._began = 0.0

    def start(self, request: LocalExecutionRequest) -> LocalExecutionHandle | LocalExecutionResult:
        self.validate(request)  # the request is checked first, so a refused request never uses a call
        self._call = self._budget.begin(self._label)
        self._began = time.monotonic()
        started = super().start(request)
        if isinstance(started, LocalExecutionResult):
            self._budget.end(self._call, time.monotonic() - self._began, started.status.value, started.requested_model, started.command)
        return started

    def wait(self, handle: LocalExecutionHandle, **kwargs: Any) -> LocalExecutionResult:
        result = super().wait(handle, **kwargs)
        self._budget.end(self._call, time.monotonic() - self._began, result.status.value, result.requested_model, result.command)
        if REAL and EVIDENCE_ENV:
            # The model's own event stream and error output (already redacted by the executor) are kept beside the screenshots, outside the per-project folders.
            kept = Path(EVIDENCE_ENV) / "_model"
            kept.mkdir(parents=True, exist_ok=True)
            (kept / f"{self._label}.stdout.jsonl").write_text(result.stdout, encoding="utf-8", newline="\n")
            (kept / f"{self._label}.stderr.txt").write_text(result.stderr, encoding="utf-8", newline="\n")
        return result


def _benchmark() -> bytes:
    """The pinned benchmark directory as a tar stream; the tree SHA proves it is the approved content (the same proof as the V02 fixture)."""

    repository = Path(plc.git(Path(__file__).resolve().parent, "rev-parse", "--show-toplevel"))
    observed = plc.git(repository, "rev-parse", f"{plc.PIN_COMMIT}:{plc.PROJECT}")
    assert observed == plc.PIN_TREE, f"benchmark drifted or the pinned commit is unavailable: {observed}"
    return subprocess.run(["git", "-C", str(repository), "archive", "--format=tar", plc.PIN_COMMIT, plc.PROJECT], check=True, capture_output=True).stdout


def _stand_in(files: dict[str, str], counter: Path) -> str:
    """A real child process that records its arguments, speaks the handshake, writes the real files and exits."""

    return textwrap.dedent(
        f"""\
        import json, pathlib, sys, time
        repo = pathlib.Path(sys.argv[sys.argv.index('-C') + 1])
        with open({str(counter)!r}, 'a', encoding='utf-8') as handle:
            handle.write(json.dumps(sys.argv[1:-1]) + '\\n')
        print(json.dumps({{'type': 'thread.started', 'thread_id': 'thread-v05c'}}), flush=True)
        for relative, text in {files!r}.items():
            (repo / relative).write_text(text, encoding='utf-8', newline='\\n')
        time.sleep(0.15)
        sys.exit(0)
        """
    )


def _force_remove(function: Any, path: str, _error: BaseException) -> None:
    """Git keeps its object files read-only on Windows; clear the flag and retry once."""

    os.chmod(path, stat.S_IWRITE)
    function(path)


def _work_dir(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    """The pytest folder in stand-in mode. In real mode a plain folder under the temp directory instead: Python 3.12.4 and later create the pytest folders with an
    owner-only ACL, which locks the model's sandbox account out of the workspace (the model then reports "Access is denied" and changes nothing)."""

    if not REAL:
        return tmp_path
    plain = Path(tempfile.gettempdir()) / f"v05c-real-{os.getpid()}-{time.time_ns()}"
    os.mkdir(plain)  # the default mode: the folder inherits the temp directory's ACL, which includes the sandbox account
    request.addfinalizer(lambda: shutil.rmtree(plain, onexc=_force_remove))
    return plain


def _executor(tmp_path: Path, label: str, files: dict[str, str]) -> tuple[_CountingExecutor, _Budget, Path]:
    counter = tmp_path / "stand-in-argv.txt"
    if REAL:
        assert CODEX_EXE and Path(CODEX_EXE).is_file(), "V05C_MODE=real needs V05C_CODEX_EXE to name the codex executable"
        assert LEDGER_ENV, "V05C_MODE=real needs V05C_BUDGET_LEDGER: the call budget is one global ledger"
        budget = _Budget(Path(LEDGER_ENV))
        return _CountingExecutor(budget, label, command_prefix=(CODEX_EXE, "-c", SANDBOX_OVERRIDE)), budget, counter
    helper = tmp_path / "stand_in_codex.py"
    helper.write_text(_stand_in(files, counter), encoding="utf-8")
    budget = _Budget(tmp_path / "budget.json")
    return _CountingExecutor(budget, label, command_prefix=(sys.executable, str(helper))), budget, counter


# ------------------------------------------------------------------------------------------------ driving the real window
class _Window:
    def __init__(self, qapp: QApplication, engine: QQmlApplicationEngine, bridge: PmCockpitBridge, window: QObject) -> None:
        self.qapp, self.engine, self.bridge, self.window = qapp, engine, bridge, window
        self.item = cast(QQuickItem, cast(Any, window).contentItem())

    def pump(self, until: Any, timeout: float, what: str) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.qapp.processEvents()
            if until():
                return
            # time.sleep, not QTest.qWait: PySide6 keeps the GIL inside qWait, which starves the worker threads of the real pool (every file-system call in them waits for the main thread).
            time.sleep(0.02)
        raise AssertionError(f"timed out after {timeout:.0f}s waiting for: {what}; window status: {self.window.property('statusMessage')!r}")

    def snapshot(self) -> dict[str, Any]:
        raw = cast(Any, self.window.property("snapshot"))
        return cast(dict[str, Any], raw.toVariant() if hasattr(raw, "toVariant") else raw)

    def named(self, name: str) -> QQuickItem:
        found = _items_named(self.item, name)
        assert len(found) == 1, (name, len(found))
        return found[0]

    def click(self, item: QQuickItem) -> None:
        assert item.property("enabled") is True
        assert QMetaObject.invokeMethod(item, "clicked")
        self.qapp.processEvents()

    def button_with_text(self, text: str) -> QQuickItem | None:
        def walk(node: QQuickItem) -> QQuickItem | None:
            for child in node.childItems():
                if child.property("text") == text and child.isVisible() and child.metaObject().indexOfMethod("clicked()") >= 0:
                    return child
                inner = walk(child)
                if inner is not None:
                    return inner
            return None

        return walk(self.item)

    def refresh(self) -> None:
        QMetaObject.invokeMethod(self.window, "refreshSnapshot")

    def shot(self, evidence: Path, name: str) -> None:
        evidence.mkdir(parents=True, exist_ok=True)
        image = cast(Any, self.window).grabWindow()
        assert not image.isNull(), "the window could not be captured"
        assert image.save(str(evidence / f"{name}.png"))


def _open_window(qapp: QApplication, service: PmCockpitService, root: Path) -> _Window:
    bridge = PmCockpitBridge(str(root), service=service)  # the real, global thread pool
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("pmCockpitBridge", bridge)
    engine.load(QUrl.fromLocalFile(str(_QML)))
    assert engine.rootObjects(), "boss_main.qml did not load"
    return _Window(qapp, engine, bridge, engine.rootObjects()[0])


def _events(root: Path) -> list[dict[str, Any]]:
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn:
        conn.row_factory = sqlite3.Row
        return [{key: row[key] for key in row.keys() if "token" not in key} for row in conn.execute("SELECT * FROM events ORDER BY rowid")]


def _drive(
    qapp: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    root: Path,
    project_id: str,
    project_name: str,
    objective: str,
    acceptance: tuple[str, ...],
    scope: tuple[str, ...],
    executor: _CountingExecutor,
) -> tuple[_Window, ContinuityStore, PmFacadeService, str, str, list[tuple[str, bool, str]]]:
    """Type the goal into the window, let the PM submit the scope card, click approve, wait for the run and the verification."""

    store = ContinuityStore(root)
    store.initialize(datetime.now(UTC).isoformat(), "v05c-e2e")
    changes = ChangeService(str(root))
    facade = PmFacadeService(
        root,
        store=store,
        change_service=changes,
        local_orchestrator=LocalExecutionOrchestrator(root, store=store, executor=executor),
    )
    service = PmCockpitService(root, store=store, facade=facade, approver=APPROVER)
    win = _open_window(qapp, service, root)
    approvals: list[tuple[str, bool, str]] = []
    win.bridge.scopeApprovalFinished.connect(lambda rid, ok, message: approvals.append((str(rid), bool(ok), str(message))))
    evidence = Path(EVIDENCE_ENV or tmp_path / "evidence") / project_id

    # 1. the goal is typed into the window and saved as a draft
    win.pump(lambda: bool(win.snapshot().get("projects")), 60, "the project cards")
    index = next(i for i, card in enumerate(win.snapshot()["projects"]) if card["project_id"] == project_id)
    win.named("planningProject").setProperty("currentIndex", index)
    win.named("planningObjective").setProperty("text", objective)
    win.named("planningAcceptance").setProperty("text", "\n".join(acceptance))
    win.named("planningKind").setProperty("currentIndex", 0)
    win.shot(evidence, "1-goal-typed")
    win.click(win.named("savePlanningDraft"))
    win.pump(lambda: win.window.property("planningDraft") is not None, 30, "the saved draft")
    win.shot(evidence, "2-draft-saved")

    # 2. the PM turns the draft into a scope card (the production facade call); the window shows the pending approval
    draft = next(item.draft for item in facade.list_planning_drafts(project_id) if item.draft.objective == objective)
    submitted = facade.submit_planning_scope_card(
        draft.request_id,
        scope_paths=scope,
        risks=("改错文件导致回归",),
        non_goals=("no refactor", "no dependency change", "no hardware download"),
        execution_grant=PlanningExecutionGrant(adapter=ExecutionAdapterKind.CODEX, approved_model=MODEL, declared_dirty_paths=scope, plan_checklist=full_checklist(len(acceptance))),
        submitted_by="PM (Claude)",
    )
    win.refresh()
    win.pump(lambda: bool(_items_named(win.item, "approveScopeButton")) and _items_named(win.item, "approveScopeButton")[0].property("enabled") is True, 60, "the approve button")
    win.shot(evidence, "3-pending-approval")

    # 3. the first business decision: one click approves the scope and starts the run (the real model works while the window stays alive)
    win.click(win.named("approveScopeButton"))
    win.pump(lambda: bool(approvals), 2400 if REAL else 900, "the end of the run and its verification")
    win.refresh()
    win.shot(evidence, "4-after-run")
    return win, store, facade, draft.request_id, str(submitted.card.change_id), approvals


def _accept_and_close(win: _Window, store: ContinuityStore, mission_id: str) -> list[tuple[str, bool, str]]:
    """The second business decision: the user clicks the final acceptance; the closure runs in the background."""

    closures: list[tuple[str, bool, str]] = []
    win.bridge.closureFinished.connect(lambda mid, ok, message: closures.append((str(mid), bool(ok), str(message))))
    win.refresh()
    win.pump(lambda: win.button_with_text("确认验收") is not None, 60, "the acceptance button")
    button = win.button_with_text("确认验收")
    assert button is not None
    win.click(button)
    win.pump(lambda: bool(closures), 900, "the closure")
    return closures


def _finish(win: _Window, evidence: Path, root: Path) -> None:
    win.shot(evidence, "5-closed")
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "events.json").write_text(json.dumps(_events(root), ensure_ascii=False, indent=1, default=str), encoding="utf-8", newline="\n")
    assert shutdown_cockpit(win.engine, win.bridge, 30_000) is True


def _assert_closed(store: ContinuityStore, mission_id: str, root: Path, change_id: str) -> None:
    mission = store.get_mission(mission_id)
    assert mission.state is MissionState.CLOSED and mission.root_work_id
    assert store.get_work(mission.root_work_id).state is WorkState.CLOSED
    assert store.list_runs(mission.root_work_id, include_terminal=True)[0].state is RunState.SUCCEEDED
    assert LedgerReconciler().reconcile(str(root)).is_clean
    change = next(root.glob(f"**/{change_id}.md"))
    assert any(line.startswith("| **验证结论**") for line in change.read_text(encoding="utf-8").splitlines())


def _candidate_of(store: ContinuityStore, mission_id: str) -> Path:
    """The isolated worktree the agent worked in (read before the closure, so that nothing depends on what the closure cleans up)."""

    root_work = store.get_mission(mission_id).root_work_id
    assert root_work
    return Path(store.list_runs(root_work, include_terminal=True)[0].worktree_path)


def _model_was_named(budget: _Budget, counter: Path, before_calls: int, expected_calls: int) -> None:
    """Exactly the expected new calls were counted, each with the explicit model, the workspace-write sandbox (and, for the real model, the authorised override)."""

    calls, _seconds = budget.totals()
    assert calls - before_calls == expected_calls, (calls, before_calls, expected_calls)
    ledger = json.loads(budget._path.read_text(encoding="utf-8"))
    fresh = ledger["entries"][before_calls:]
    assert len(fresh) == expected_calls and all(entry["requested_model"] == MODEL and entry["status"] == "SUCCEEDED" for entry in fresh), fresh
    for entry in fresh:
        command = entry["command"]
        assert command[command.index("-m") + 1] == MODEL and "--sandbox" in command and "workspace-write" in command
        if REAL:
            assert SANDBOX_OVERRIDE in command, command
    if not REAL:
        argv = [json.loads(line) for line in counter.read_text(encoding="utf-8").splitlines()]
        assert len(argv) == expected_calls and all(a[a.index("-m") + 1] == MODEL for a in argv)


# ------------------------------------------------------------------------------------------------ the two projects
PY_OBJECTIVE = (
    f"只修改两个文件：{CALC} 与 {CALC_TEST}。把 {CALC} 里的 add(a, b) 改成返回 a + b（保留 int 类型注解）；"
    f"在 {CALC_TEST} 末尾新增测试 test_add_negative，内容 assert add(-1, 1) == 0。不要改其他文件，不要新增依赖。"
)
PY_ACCEPTANCE = ("add(2, 3) == 5", "add(-1, 1) == 0")
PLC_OBJECTIVE = (
    "公共报警新增蜂鸣器输出，只修改三个文件。"
    f"1）{plc.STRUCT}：在 o_bNewAlarmFlag 那一行之后新增一行 `{plc.STRUCT_ADDED.strip()}`；"
    f"2）{plc.BLOCK}：在行 `{plc.BLOCK_ANCHOR.strip()}` 之后新增空行、注释行 `(* 10. 蜂鸣器输出：任意报警激活时置位 *)` 和语句 `io_stGlobal.o_bBuzzer := io_stGlobal.o_bAnyAlarmActive;`；"
    f"3）{plc.VAR_DOC}：在行 `{plc.DOC_ANCHOR.strip()}` 之后新增一行 `{plc.DOC_ADDED.strip()}`。"
    "保持缩进与相邻行对齐，不要改其他文件，不要新增依赖。"
)
PLC_ACCEPTANCE = ("ST_CommonAlarm 新增 o_bBuzzer", "FB_2001 在任意报警激活时置位 o_bBuzzer", "变量定义文档同步")


def test_a_python_goal_typed_into_the_window_reaches_the_final_acceptance_and_a_clean_ledger(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    tmp_path = _work_dir(request, tmp_path)
    root = (tmp_path / "ws").resolve()
    build_python_workspace(root)
    # The V02 workspace builder fixes line endings so that Git prints no CRLF warning (the governed snapshot refuses any warning); the Python builder does not.
    plc.git(root, "config", "core.autocrlf", "false")
    plc.git(root, "config", "core.safecrlf", "false")
    executor, budget, counter = _executor(tmp_path, "python", {CALC: FIXED_CALC, CALC_TEST: GOOD_TESTS})
    before_calls = budget.totals()[0]
    win, store, _facade, request_id, change_id, approvals = _drive(
        qapp, tmp_path, monkeypatch, root=root, project_id=PY_PROJECT_ID, project_name="python", objective=PY_OBJECTIVE,
        acceptance=PY_ACCEPTANCE, scope=(CALC, CALC_TEST), executor=executor,
    )
    assert approvals == [(request_id, True, VERIFIED_SENTENCE)], approvals
    mission_id = next(m.mission_id for m in store.list_missions(PY_PROJECT_ID) if m.state is MissionState.ACCEPTANCE_PENDING)
    assert "确认验收" in " ".join(_texts(win.item))
    candidate = _candidate_of(store, mission_id)
    source, tests = (candidate / CALC).read_text(encoding="utf-8"), (candidate / CALC_TEST).read_text(encoding="utf-8")
    assert "a + b" in source and "a - b" not in source and "add(-1, 1) == 0" in tests
    closures = _accept_and_close(win, store, mission_id)
    assert [(mid, ok) for mid, ok, _ in closures] == [(mission_id, True)]
    _assert_closed(store, mission_id, root, change_id)
    assert (root / CALC).read_bytes() == (candidate / CALC).read_bytes()  # closure merged the accepted bytes back (gap 8)
    _finish(win, Path(EVIDENCE_ENV or tmp_path / "evidence") / PY_PROJECT_ID, root)
    _model_was_named(budget, counter, before_calls, 1)


def test_a_plc_goal_typed_into_the_window_reaches_the_final_acceptance_with_a_consistent_document(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    tmp_path = _work_dir(request, tmp_path)
    benchmark = _benchmark()
    root = (tmp_path / "ws").resolve()
    plc.build_workspace(root, benchmark)
    executor, budget, counter = _executor(tmp_path, "plc", plc.requirement_files(root))
    before_calls = budget.totals()[0]
    win, store, _facade, request_id, change_id, approvals = _drive(
        qapp, tmp_path, monkeypatch, root=root, project_id=plc.PROJECT_ID, project_name="plc", objective=PLC_OBJECTIVE,
        acceptance=PLC_ACCEPTANCE, scope=plc.SCOPE, executor=executor,
    )
    assert approvals == [(request_id, True, VERIFIED_SENTENCE)], approvals
    mission_id = next(m.mission_id for m in store.list_missions(plc.PROJECT_ID) if m.state is MissionState.ACCEPTANCE_PENDING)
    candidate = _candidate_of(store, mission_id)
    assert "o_bBuzzer" in (candidate / plc.STRUCT).read_text(encoding="utf-8")
    assert "io_stGlobal.o_bBuzzer := io_stGlobal.o_bAnyAlarmActive;" in (candidate / plc.BLOCK).read_text(encoding="utf-8")
    analysis = dc.analyze_project(str(candidate / plc.PROJECT))
    assert [f for f in analysis.findings if f.severity == "fail"] == [] and analysis.marked_rows == []
    closures = _accept_and_close(win, store, mission_id)
    assert [(mid, ok) for mid, ok, _ in closures] == [(mission_id, True)]
    _assert_closed(store, mission_id, root, change_id)
    for path in plc.SCOPE:  # closure merged the accepted bytes back into the control root (gap 8), uncommitted
        assert (root / path).read_bytes() == (candidate / path).read_bytes()
    _finish(win, Path(EVIDENCE_ENV or tmp_path / "evidence") / plc.PROJECT_ID, root)
    _model_was_named(budget, counter, before_calls, 1)


def test_the_call_budget_refuses_the_twenty_first_call_and_a_used_up_clock(tmp_path: Path) -> None:
    ledger = tmp_path / "budget.json"
    budget = _Budget(ledger)
    for number in range(1, MAX_CALLS + 1):
        assert budget.begin("probe") == number
        budget.end(number, 1.0, "COMPLETED", MODEL, ("codex", "exec", "-m", MODEL))
    with pytest.raises(CallBudgetError, match="20-call budget"):
        budget.begin("probe")
    assert budget.totals() == (MAX_CALLS, float(MAX_CALLS))
    slow = _Budget(tmp_path / "slow.json")
    first = slow.begin("probe")
    slow.end(first, MAX_SECONDS + 1.0, "TIMED_OUT", MODEL, ("codex", "exec", "-m", MODEL))
    with pytest.raises(CallBudgetError, match="budget is used up"):
        slow.begin("probe")
