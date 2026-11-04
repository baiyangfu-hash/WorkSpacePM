"""Interlock matrix, defence line 1 (CHG-SCPT-2026-476): static checks, a few seconds, every PR.

The matrix (``auto_pm.contracts.interlock_matrix``) is only worth having if it cannot drift from the code.  This file is what
keeps it honest:

* every command-line command is in the command table or in a frozen baseline that may only shrink;
* every guard names a real function, and a refusal raised in a registered guard module carries a registered ``guard_id``
  (the count of plain refusals per file may not grow; a lower count must be written into the baseline);
* every conflict code ``pm orient`` can print is a row of the abnormal-state table, so no conflict is left without a next step;
* the deadlock definition runs over the tables, a synthetic guard proves the detector can see, and the deadlocks that exist
  today are listed with a TD number and a flip-by date, so the list can only get shorter;
* nothing in the package updates or deletes rows of the ``events`` table.

Baselines live in ``tests/contract/baselines``; changing one is a decision the reviewer reads in the PR diff.
"""

from __future__ import annotations

import ast
import json
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import replace
from datetime import date
from pathlib import Path

import click
import pytest

from auto_pm.contracts import interlock_matrix as matrix
from auto_pm.contracts.interlock_matrix import (
    COMMANDS,
    FACTS,
    GUARDS,
    STATES,
    CommandKind,
    Exempt,
    GuardSpec,
    find_deadlocks,
)
from auto_pm.ui.cli.__main__ import cli

PACKAGE = Path(matrix.__file__).resolve().parents[1]
BASELINES = Path(__file__).resolve().parent / "baselines"

# Exceptions a guard used to raise before ``GuardRefusal`` existed; a new one of these in a registered module is a violation.
PLAIN_REFUSALS = frozenset({"ClickException", "ContinuityStoreError"})
GUARD_REFUSALS = frozenset({"GuardClickRefusal", "GuardStoreRefusal", "GuardRefusal"})

# Deadlocks that exist today (found by ``find_deadlocks`` over the tables), each with the TD that closes it and the date by which
# it must be flipped.  The list can only get shorter: add nothing here to make a new deadlock pass, fix the guard.
# TD-PENDING-476: the coordinator assigns the number; the recovery order (P2) clears them.
KNOWN_DEADLOCKS: dict[tuple[str, str, str], tuple[str, date]] = {
    ("LEASE_EXPIRED", "RUNTIME_IDENTITY_DIVERGENCE", "G-IDENTITY-WRITE"): ("TD-PENDING-476", date(2026, 12, 15)),
    ("LEASE_EXPIRED", "RUNTIME_IDENTITY_UNVERIFIED", "G-IDENTITY-WRITE"): ("TD-PENDING-476", date(2026, 12, 15)),
    ("LIVE_RUN_UNDER_FINISHED_WORK", "RUNTIME_IDENTITY_DIVERGENCE", "G-IDENTITY-WRITE"): ("TD-PENDING-476", date(2026, 12, 15)),
    ("LIVE_RUN_UNDER_FINISHED_WORK", "RUNTIME_IDENTITY_UNVERIFIED", "G-IDENTITY-WRITE"): ("TD-PENDING-476", date(2026, 12, 15)),
}
MAX_KNOWN_DEADLOCKS = 4

# Exit-step commands the deadlock check cannot see because they have no row in the command table yet (P1 inventories them).
UNMODELLED_STEP_COMMANDS = frozenset({"pm park", "worktree sweep"})

# The recovery commands today.  ``recovery open`` (P2) will be added here only together with its design review; the set may not grow
# without touching this line, which the reviewer sees.
RECOVERY_COMMANDS_FROZEN = frozenset(
    {
        "continuity lease renew",
        "continuity run reclaim",
        "continuity run settle-expired",
        "continuity run fence-terminal-lease",
        "continuity run reconcile-terminal-lease",
        "continuity run revoke-unstarted",
        "continuity work adjudicate",
    }
)


# ----------------------------------------------------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------------------------------------------------


def _walk(group: click.Group, prefix: str = "") -> Iterator[str]:
    for name, command in sorted(group.commands.items()):
        if isinstance(command, click.Group):
            yield from _walk(command, f"{prefix}{name} ")
        else:
            yield f"{prefix}{name}"


def _python_files() -> list[Path]:
    return sorted(path for path in PACKAGE.rglob("*.py") if "__pycache__" not in path.parts)


def _raised_name(node: ast.Raise) -> str:
    exc = node.exc
    if isinstance(exc, ast.Call):
        exc = exc.func
    if isinstance(exc, ast.Attribute):
        return exc.attr
    if isinstance(exc, ast.Name):
        return exc.id
    return ""


def count_plain_refusals(path: Path) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    return sum(1 for node in ast.walk(tree) if isinstance(node, ast.Raise) and _raised_name(node) in PLAIN_REFUSALS)


def _guard_modules() -> dict[str, Path]:
    return {
        spec.source.split("::")[0]: PACKAGE / spec.source.split("::")[0] for spec in GUARDS.values() if spec.source
    }


# ----------------------------------------------------------------------------------------------------------------------
# 1. the tables agree with each other
# ----------------------------------------------------------------------------------------------------------------------


def test_the_tables_are_self_consistent() -> None:
    problems: list[str] = []
    for key, spec in COMMANDS.items():
        problems += [f"命令 {key} 用了未登记的事实 {fact}" for fact in spec.needs if fact not in FACTS]
        problems += [f"命令 {key} 用了未登记的护栏 {guard}" for guard in spec.guards if guard not in GUARDS]
    for guard in GUARDS.values():
        problems += [f"护栏 {guard.guard_id} 用了未登记的事实 {fact}" for fact in guard.forbids if fact not in FACTS]
        if guard.exempt is Exempt.NEVER and (guard.exempt_commands or not guard.never_reason):
            problems.append(f"护栏 {guard.guard_id} 标了不可豁免，就不能有豁免命令，且要写原因")
        if guard.exempt is not Exempt.BY_COMMAND and guard.exempt_commands:
            problems.append(f"护栏 {guard.guard_id} 不是按命令豁免，不能列豁免命令")
    codes: Counter[str] = Counter()
    for state in STATES.values():
        codes.update(state.conflict_codes)
        problems += [f"状态 {state.state_id} 的 excludes 指向不存在的状态 {other}" for other in state.excludes if other not in STATES]
        problems += [f"状态 {state.state_id} 的 breaks 用了未登记的事实 {fact}" for fact in state.breaks if fact not in FACTS]
        for index, step in enumerate(state.exit_steps, start=1):
            problems += [f"状态 {state.state_id} 第 {index} 步用了未登记的事实 {fact}" for fact in step.needs if fact not in FACTS]
            if not step.command and not step.manual:
                problems.append(f"状态 {state.state_id} 第 {index} 步既没有命令也没标人工步骤")
            if step.manual and step.command:
                problems.append(f"状态 {state.state_id} 第 {index} 步标了人工却有命令")
    problems += [f"冲突码 {code} 属于多个状态" for code, count in codes.items() if count > 1]
    assert not problems, "；".join(problems)


def test_exempt_commands_mirror_the_identity_classification_of_the_cli() -> None:
    """The matrix says which commands run past the identity guard; the existing CLI test says which ones do.  They must agree."""

    from tests.cli.test_continuity_runtime_identity import RECOVERY

    waived = {f"continuity {name}" for name in RECOVERY}
    assert set(GUARDS["G-IDENTITY-WRITE"].exempt_commands) == waived


def test_command_table_rows_exist_and_the_rest_are_in_the_frozen_baseline() -> None:
    existing = set(_walk(cli))
    missing = sorted(set(COMMANDS) - existing)
    assert not missing, f"命令表里有不存在的命令：{missing}"
    baseline = {
        line.strip()
        for line in (BASELINES / "unclassified_commands.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    unclassified = existing - set(COMMANDS)
    assert unclassified == baseline, (
        "命令表与冻结名单不一致。新命令：先在 interlock_matrix.COMMANDS 登记；已登记或已删除的命令要从 "
        f"baselines/unclassified_commands.txt 删掉（名单只能缩）。多出：{sorted(unclassified - baseline)}；"
        f"该删：{sorted(baseline - unclassified)}"
    )


def test_recovery_command_set_may_only_shrink() -> None:
    actual = {key for key, spec in COMMANDS.items() if spec.kind is CommandKind.RECOVERY}
    assert actual <= RECOVERY_COMMANDS_FROZEN, (
        f"恢复类命令名单只能缩，新增必须随设计评审改本文件：{sorted(actual - RECOVERY_COMMANDS_FROZEN)}"
    )


def test_exit_steps_use_known_commands() -> None:
    assert matrix.unmodelled_steps() <= UNMODELLED_STEP_COMMANDS, (
        f"出口步骤用了命令表里没有的命令：{sorted(matrix.unmodelled_steps() - UNMODELLED_STEP_COMMANDS)}"
    )
    assert UNMODELLED_STEP_COMMANDS <= matrix.unmodelled_steps(), "名单里的命令已经登记了，从 UNMODELLED_STEP_COMMANDS 删掉"


# ----------------------------------------------------------------------------------------------------------------------
# 2. guards name real code, refusals name their guard
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("guard", [spec for spec in GUARDS.values() if spec.source], ids=lambda spec: spec.guard_id)
def test_guard_source_is_a_real_function(guard: GuardSpec) -> None:
    relative, name = guard.source.split("::")
    path = PACKAGE / relative
    assert path.is_file(), f"{guard.guard_id}: 文件不存在 {relative}"
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    names = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert name in names, f"{guard.guard_id}: {relative} 里没有函数 {name}"


def test_every_guard_refusal_in_the_code_names_a_registered_guard() -> None:
    unknown: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and _call_name(node) in GUARD_REFUSALS):
                continue
            first = node.args[0] if node.args else None
            if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                continue  # the base class itself and tests build them from variables
            if first.value not in GUARDS:
                unknown.append(f"{path.relative_to(PACKAGE)}:{node.lineno} {first.value}")
    assert not unknown, f"拒绝用了没登记的 guard_id：{unknown}"


def _call_name(node: ast.Call) -> str:
    func = node.func
    return func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""


def test_plain_refusals_in_guard_modules_do_not_grow() -> None:
    """A new ``if ...: raise ClickException`` in a module that holds a guard is how #496 slipped a second condition in unseen."""

    baseline: dict[str, int] = json.loads((BASELINES / "guard_refusals.json").read_text(encoding="utf-8"))
    actual = {relative: count_plain_refusals(path) for relative, path in sorted(_guard_modules().items())}
    grew = {name: (baseline.get(name, 0), count) for name, count in actual.items() if count > baseline.get(name, 0)}
    assert not grew, f"登记过护栏的文件里新增了不带 guard_id 的拒绝（基线, 现在）：{grew}。请改用 GuardClickRefusal / GuardStoreRefusal"
    shrank = {name: (baseline[name], count) for name, count in actual.items() if count < baseline.get(name, 0)}
    assert not shrank, f"拒绝点减少了，请把 baselines/guard_refusals.json 调低（基线, 现在）：{shrank}"
    assert set(baseline) == set(actual), "基线文件里的文件集合与护栏表登记的文件不一致"


# ----------------------------------------------------------------------------------------------------------------------
# 3. conflict codes and next steps
# ----------------------------------------------------------------------------------------------------------------------


def _codes_in_code() -> set[str]:
    codes: set[str] = set()
    resume = ast.parse((PACKAGE / "application/core/continuity_resume_service.py").read_text(encoding="utf-8-sig"))
    for node in ast.walk(resume):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "append"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "conflicts"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            codes.add(str(node.args[0].value))
    context_source = (PACKAGE / "application/core/workspace_context_service.py").read_text(encoding="utf-8-sig")
    codes.update(re.findall(r'"(RUNTIME_IDENTITY_[A-Z_]+)"', context_source))
    return codes


def test_every_conflict_code_is_a_row_of_the_state_table() -> None:
    in_code = _codes_in_code()
    assert in_code, "没扫到任何冲突码，扫描方法失灵了"
    in_table = {code for state in STATES.values() for code in state.conflict_codes}
    assert in_code <= in_table, f"代码里有冲突码不在异常状态表里：{sorted(in_code - in_table)}"
    assert in_table <= in_code, f"异常状态表里有代码从不产生的冲突码：{sorted(in_table - in_code)}"


def test_no_conflict_is_left_without_a_next_step() -> None:
    for code in sorted(_codes_in_code()):
        hint = matrix.exit_hint(code)
        assert hint.startswith(code) and len(hint) > len(code) + 10
    assert "矩阵里没有" in matrix.exit_hint("NOT_A_REAL_CODE")


def test_the_scan_state_has_a_detector_and_a_chain() -> None:
    state = STATES["LIVE_RUN_UNDER_FINISHED_WORK"]
    assert state.conflict_codes == ("LIVE_RUN_UNDER_FINISHED_WORK",) and state.exit_steps and state.target_kind == "run"


# ----------------------------------------------------------------------------------------------------------------------
# 4. deadlocks
# ----------------------------------------------------------------------------------------------------------------------


def _grouped() -> dict[tuple[str, str, str], int]:
    return dict(Counter((d.state_id, d.held_by, d.guard_id) for d in find_deadlocks()))


def test_every_deadlock_in_the_tables_is_known_and_the_known_list_only_shrinks() -> None:
    found = set(_grouped())
    new = sorted(found - set(KNOWN_DEADLOCKS))
    assert not new, f"出口链里出现了新的死锁（某步骤被未豁免的护栏挡住）：{new}。修护栏或出口，不要加进 KNOWN_DEADLOCKS"
    fixed = sorted(set(KNOWN_DEADLOCKS) - found)
    assert not fixed, f"这些已知死锁已经消除，请从 KNOWN_DEADLOCKS 删掉并翻转对应的 xfail：{fixed}"
    assert len(KNOWN_DEADLOCKS) <= MAX_KNOWN_DEADLOCKS


def test_known_deadlocks_carry_a_td_number_and_have_not_passed_their_date() -> None:
    for key, (td, flip_by) in KNOWN_DEADLOCKS.items():
        assert td.startswith("TD-"), key
        assert date.today() <= flip_by, f"{key} 的翻转期限 {flip_by} 已过（{td}）：修掉，或由协调者重新定期限"


@pytest.mark.xfail(
    strict=True,
    reason="TD-PENDING-476: 身份不一致时恢复链的前置步骤被 G-IDENTITY-WRITE 挡住，P2 的恢复令清除；清除后本用例变绿，必须翻转",
)
def test_known_deadlock_identity_divergence_blocks_the_recovery_chain() -> None:
    assert not [d for d in find_deadlocks() if d.held_by.startswith("RUNTIME_IDENTITY")]


def test_the_detector_sees_a_synthetic_guard() -> None:
    """If this passes with a guard that forbids a step, the detector works; if the tables ever stop being scanned, it goes red."""

    guard = GuardSpec("G-SYNTHETIC", "forbids the settlement", "", ("lease=valid",), Exempt.NO)
    guards = {**GUARDS, guard.guard_id: guard}
    commands = {
        **COMMANDS,
        "continuity run settle-expired": replace(
            COMMANDS["continuity run settle-expired"], guards=(*COMMANDS["continuity run settle-expired"].guards, guard.guard_id)
        ),
    }
    states = {
        **STATES,
        "LEASE_EXPIRED": replace(STATES["LEASE_EXPIRED"], breaks=("lease=valid",)),
    }
    hits = [d for d in find_deadlocks(states, commands, guards) if d.guard_id == "G-SYNTHETIC"]
    assert hits and hits[0].command == "continuity run settle-expired"


def test_a_waived_guard_is_not_a_deadlock() -> None:
    """settle-expired runs past the identity guard today; it must never show up as blocked by it."""

    assert not [d for d in find_deadlocks() if d.command == "continuity run settle-expired" and d.guard_id == "G-IDENTITY-WRITE"]


def test_never_exempt_guards_stay_never_exempt() -> None:
    never = {"G-AGENT-APPROVAL", "G-APPROVAL-PIN", "G-DECISION-GIT-BINDING", "G-RECOVERY-AUTHORITY", "G-PAYLOAD-HASH", "G-LEDGER-SCHEMA"}
    assert never <= {guard_id for guard_id, guard in GUARDS.items() if guard.exempt is Exempt.NEVER}


# ----------------------------------------------------------------------------------------------------------------------
# 5. the ledger's event history is append-only
# ----------------------------------------------------------------------------------------------------------------------


def test_nothing_updates_or_deletes_events() -> None:
    """The ledger has no database trigger that forbids it; "append-only" is a convention, so the convention is checked here."""

    pattern = re.compile(r"\b(UPDATE|DELETE\s+FROM|INSERT\s+OR\s+REPLACE\s+INTO|REPLACE\s+INTO)\s+events\b", re.IGNORECASE)
    offenders = [
        f"{path.relative_to(PACKAGE)}:{number}"
        for path in _python_files()
        for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1)
        if pattern.search(line)
    ]
    assert not offenders, f"events 表只许追加：{offenders}"


def test_the_events_check_would_notice_an_update() -> None:
    pattern = re.compile(r"\b(UPDATE|DELETE\s+FROM|INSERT\s+OR\s+REPLACE\s+INTO|REPLACE\s+INTO)\s+events\b", re.IGNORECASE)
    assert pattern.search("conn.execute('UPDATE events SET payload=?')")
    assert pattern.search("DELETE FROM events WHERE id=1")
    assert not pattern.search("INSERT INTO events (a) VALUES (?)")
