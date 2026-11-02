"""Complete plan poka-yoke fields (计划防呆七栏) for tests that are not about the checklist."""

from __future__ import annotations

import shlex
import subprocess
import sys

from auto_pm.contracts.plan_checklist import AcceptanceCheck, PlanChecklist

ORIGINAL_REQUEST = "照抄的用户原话"
ROLLBACK = "git revert 本次提交，恢复原文件"


def native_command(*argv: str) -> str:
    """Command text that this platform's own quoting rules (the ones ``pm verify`` parses with) split back into ``argv``."""

    return subprocess.list2cmdline(list(argv)) if sys.platform == "win32" else shlex.join(argv)


def passing_command() -> str:
    """A real, instant command that exits 0 on any platform: ``pm verify`` now executes approved commands."""

    return native_command(sys.executable, "-c", "pass")


def full_checklist(acceptance: int = 1, *, original: str = ORIGINAL_REQUEST) -> PlanChecklist:
    """A checklist with every field filled, one passing command per acceptance criterion."""

    return PlanChecklist(
        original_request=original,
        safety_circuit="否",
        acceptance_checks=tuple(
            AcceptanceCheck(command=passing_command(), expected_exit_code=0)
            for _ in range(acceptance)
        ),
        rollback=ROLLBACK,
    )


def checklist_args(acceptance: int = 1, *, original: str = ORIGINAL_REQUEST) -> list[str]:
    """The same checklist as ``pm plan`` / ``pm approve`` command-line options."""

    args = ["--original-request", original, "--safety-circuit", "否", "--rollback", ROLLBACK]
    for _ in range(acceptance):
        args += ["--check", f"{passing_command()} => 0"]
    return args
