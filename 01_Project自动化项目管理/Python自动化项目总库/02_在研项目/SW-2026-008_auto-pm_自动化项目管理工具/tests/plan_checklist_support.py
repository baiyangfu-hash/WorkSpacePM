"""Complete plan poka-yoke fields (计划防呆七栏) for tests that are not about the checklist."""

from __future__ import annotations

from auto_pm.contracts.plan_checklist import AcceptanceCheck, PlanChecklist

ORIGINAL_REQUEST = "照抄的用户原话"
ROLLBACK = "git revert 本次提交，恢复原文件"


def full_checklist(acceptance: int = 1, *, original: str = ORIGINAL_REQUEST) -> PlanChecklist:
    """A checklist with every field filled, one passing command per acceptance criterion."""

    return PlanChecklist(
        original_request=original,
        safety_circuit="否",
        acceptance_checks=tuple(
            AcceptanceCheck(command=f"python -m pytest -q  # acceptance {index}", expected_exit_code=0)
            for index in range(1, acceptance + 1)
        ),
        rollback=ROLLBACK,
    )


def checklist_args(acceptance: int = 1, *, original: str = ORIGINAL_REQUEST) -> list[str]:
    """The same checklist as ``pm plan`` / ``pm approve`` command-line options."""

    args = ["--original-request", original, "--safety-circuit", "否", "--rollback", ROLLBACK]
    for index in range(1, acceptance + 1):
        args += ["--check", f"python -m pytest -q  # acceptance {index} => 0"]
    return args
