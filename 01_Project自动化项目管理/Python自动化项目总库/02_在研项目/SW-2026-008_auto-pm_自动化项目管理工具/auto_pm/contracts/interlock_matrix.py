"""Interlock matrix: which guard may refuse which command, and the way out of every abnormal ledger state (CHG-SCPT-2026-476).

Why this file exists: each guard of the cockpit was written alone, so nobody ever checked that after a refusal there is still a
command that works.  Six deadlocks between 2026-10-29 and 2026-11-02 (TD-240, TD-256/259/260, B2, release check G3) were that
one defect.  The matrix writes the three tables down as data, so a test can decide "deadlock" mechanically:

    a step of an exit chain needs a fact that some guard, applicable to that step and not exempt for it, forbids.

Design: ``docs/design/cockpit-guard-deadlock-root-fix.md`` (rev 3.1).  This is phase P0: **data and tests only, no refusal
changes**.  ``recovery_exempt`` below describes what the code does today; the recovery order (P2) will change some of it
and the change has to be made here first, which the contract test then reviews.

Facts are plain strings (``FACTS``); a guard *requires* or *forbids* facts for the commands it applies to.  The module is pure
data (standard library only) so the launcher, the release gate and the tests can all read it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# ---------------------------------------------------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------------------------------------------------

FACTS: dict[str, str] = {
    "workspace=control_root": "the command runs in the control root (the clone that owns .auto-pm/continuity.db)",
    "workspace=station": "the command runs in a managed worktree under .auto-pm/worktrees/",
    "identity=clean": "the runtime identity check (release pointer vs loaded package) has no conflict",
    "lease=valid": "the Run's lease is held and not expired",
    "mission=not_parked": "the Mission that owns the Run is not parked",
    "operator=user": "the operator is the user in person (no agent marker, approval evidence is the user's words)",
    "pin=configured": "an approver PIN is set (the user decides whether to set one)",
    "git=head_pinned": "HEAD of the control root still equals the git_head the recovery Run was started on",
    "decision=committed_clean": "the Decision file is tracked by git in the control root and clean against HEAD",
    "decision=sealed": "the Decision's bytes were sealed in the ledger when it was approved (P2)",
    "payload=hash_ok": "the loaded package matches its recorded payload hash",
    "ledger=schema_ok": "this code version can open the ledger (schema version known)",
    "decision=canonical": "the target Work is bound to a canonical immutable Decision",
}


class CommandKind(str, Enum):
    READ_ONLY = "read_only"
    NORMAL = "normal"
    RECOVERY = "recovery"


class Exempt(str, Enum):
    """Whether a guard may be waived for a recovery command."""

    NEVER = "never"  # no path waives it, in any mode
    NO = "no"  # not waived today; the recovery order (P2) may decide otherwise
    BY_COMMAND = "by_command"  # the recovery commands listed in ``exempt_commands`` already run past it today
    IDENTITY_ONLY = "identity_only"  # P2: ``recovery open`` alone is waived from the identity refusal


class WhoCan(str, Enum):
    USER = "user"  # only the user in person (approval words, PIN, switch release)
    PM = "pm"  # the main executor
    ANY_AGENT = "any_agent"
    NOBODY = "nobody"  # no exit is registered (a gap)


# ---------------------------------------------------------------------------------------------------------------------
# Command table (the commands that sit on an exit chain; every other command is listed in the frozen baseline in
# tests/contract/baselines/unclassified_commands.txt, which may only shrink)
# ---------------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CommandSpec:
    kind: CommandKind
    needs: tuple[str, ...]  # facts the command needs to be true when it runs
    guards: tuple[str, ...]  # guard ids that can refuse it
    note: str = ""


COMMANDS: dict[str, CommandSpec] = {
    "change create": CommandSpec(CommandKind.NORMAL, ("identity=clean",), ("G-IDENTITY-WRITE",)),
    "change transition": CommandSpec(CommandKind.NORMAL, ("identity=clean",), ("G-IDENTITY-WRITE", "G-AGENT-APPROVAL")),
    "decision create": CommandSpec(
        CommandKind.NORMAL, ("identity=clean",), ("G-IDENTITY-WRITE", "G-AGENT-APPROVAL", "G-APPROVAL-PIN")
    ),
    "continuity work create": CommandSpec(CommandKind.NORMAL, ("identity=clean",), ("G-IDENTITY-WRITE", "G-CARD-PREFLIGHT")),
    "continuity work authorize": CommandSpec(CommandKind.NORMAL, ("identity=clean",), ("G-IDENTITY-WRITE",)),
    "continuity work transition": CommandSpec(CommandKind.NORMAL, ("identity=clean",), ("G-IDENTITY-WRITE",)),
    "continuity run start": CommandSpec(
        CommandKind.NORMAL,
        ("identity=clean",),
        ("G-IDENTITY-WRITE", "G-CONTROL-ROOT-RUN", "G-RECOVERY-AUTHORITY", "G-DECISION-GIT-BINDING"),
        "with --recovery-change the control root is allowed (#496)",
    ),
    "continuity run transition": CommandSpec(CommandKind.NORMAL, ("identity=clean", "lease=valid"), ("G-IDENTITY-WRITE", "G-LEASE-VALID")),
    "continuity run settle-expired": CommandSpec(
        CommandKind.RECOVERY,
        ("workspace=control_root", "decision=committed_clean", "git=head_pinned", "decision=canonical"),
        ("G-MUTATION-ROOT", "G-DECISION-GIT-BINDING", "G-HEAD-PIN", "G-PARKED", "G-RECOVERY-AUTHORITY", "G-RECOVERY-TARGET-DECISION"),
    ),
    "continuity run reclaim": CommandSpec(CommandKind.RECOVERY, (), ("G-PARKED",), "claimant must differ from the holder"),
    "continuity run fence-terminal-lease": CommandSpec(
        CommandKind.RECOVERY,
        ("workspace=control_root", "decision=committed_clean"),
        ("G-MUTATION-ROOT", "G-DECISION-GIT-BINDING", "G-HEAD-PIN"),
    ),
    "continuity run reconcile-terminal-lease": CommandSpec(
        CommandKind.RECOVERY,
        ("workspace=control_root", "decision=committed_clean"),
        ("G-MUTATION-ROOT", "G-DECISION-GIT-BINDING", "G-HEAD-PIN"),
    ),
    "continuity run revoke-unstarted": CommandSpec(
        CommandKind.RECOVERY,
        ("workspace=control_root", "decision=committed_clean"),
        ("G-MUTATION-ROOT", "G-DECISION-GIT-BINDING", "G-HEAD-PIN"),
    ),
    "continuity work adjudicate": CommandSpec(
        CommandKind.RECOVERY,
        ("workspace=control_root", "decision=committed_clean"),
        ("G-MUTATION-ROOT", "G-DECISION-GIT-BINDING", "G-HEAD-PIN"),
    ),
    "continuity lease renew": CommandSpec(
        CommandKind.RECOVERY, ("lease=valid",), ("G-LEASE-VALID",), "an expired lease cannot be renewed (TD-240): the exit is reclaim"
    ),
    "continuity recovery plan": CommandSpec(CommandKind.READ_ONLY, (), (), "prints the exit chain of one abnormal state"),
    "pm orient": CommandSpec(CommandKind.READ_ONLY, (), ()),
    # D-39: cross-machine card claims live on GitHub (remote claims/<card> branches), never in the ledger; they must work in a
    # cloud clone with no runtime identity, so they carry no guards.
    "claim list": CommandSpec(CommandKind.READ_ONLY, (), (), "reads the remote claim branches"),
    "claim open": CommandSpec(CommandKind.NORMAL, (), (), "pushes claims/<card> to origin; does not touch the ledger"),
    "claim release": CommandSpec(CommandKind.NORMAL, (), (), "pushes a released marker onto the holder's own claim; deletes nothing"),
    "pm resume": CommandSpec(CommandKind.READ_ONLY, (), ()),
    "pm recover": CommandSpec(CommandKind.READ_ONLY, (), (), "--apply writes EXECUTOR_LOST (release 7 and later)"),
    "pm triage": CommandSpec(CommandKind.READ_ONLY, (), (), "open cards plus inbox in suggested order; confirms nothing"),
    "pm state-backup status": CommandSpec(CommandKind.READ_ONLY, (), (), "reads one local file only"),
    # push and pull never write the live ledger (pull prints the restore command and replaces nothing), and neither calls the
    # runtime-identity guard, so a diverged or unverified runtime cannot lock them out.
    "pm state-backup push": CommandSpec(CommandKind.NORMAL, (), (), "writes a sanitised ledger copy to the private repository, not the ledger"),
    "pm state-backup pull": CommandSpec(CommandKind.NORMAL, (), (), "fetches and verifies a backup; never replaces the live ledger"),
    # The guards of the two commands below are not inventoried yet (their checks sit in services, not in the command body):
    # P1 fills them in; until then the deadlock check cannot see them, which the contract test lists as unmodelled.
    "pm close": CommandSpec(CommandKind.NORMAL, (), (), "guards not inventoried yet (P1)"),
    "pm unpark": CommandSpec(CommandKind.NORMAL, ("operator=user",), (), "guards not inventoried yet (P1)"),
    "ledger reconcile": CommandSpec(CommandKind.NORMAL, ("workspace=control_root",), ("G-MUTATION-ROOT",)),
    "pm approver-pin init": CommandSpec(CommandKind.NORMAL, ("operator=user",), ("G-AGENT-APPROVAL",), "does not read the ledger"),
}


# ---------------------------------------------------------------------------------------------------------------------
# Guard table (keyed by guard_id; ``source`` is ``path-in-the-package::function``, verified by the contract test)
# ---------------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class GuardSpec:
    guard_id: str
    title: str
    source: str  # "relative/path.py::function" or "" for guards that live outside the package (launcher)
    forbids: tuple[str, ...]  # facts whose absence makes the guard refuse (the command needs these)
    exempt: Exempt
    exempt_commands: tuple[str, ...] = ()
    on_exit_chain: bool = False  # does an exit chain pass this guard?
    never_reason: str = ""


GUARDS: dict[str, GuardSpec] = {
    spec.guard_id: spec
    for spec in (
        GuardSpec(
            "G-IDENTITY-WRITE",
            "write commands (also change order, Decision and card commands, through the same function) refuse while the runtime identity has any conflict",
            "ui/cli/runtime_identity_guard.py::require_runtime_identity",
            ("identity=clean",),
            Exempt.BY_COMMAND,
            (
                # Mirrors tests/cli/test_continuity_runtime_identity.py::RECOVERY (checked by the contract test).
                "continuity work adjudicate",
                "continuity run settle-expired",
                "continuity run fence-terminal-lease",
                "continuity run reconcile-terminal-lease",
                "continuity run fence-legacy-terminal",
                "continuity run revoke-unstarted",
                "continuity run reclaim",
                "continuity lease renew",
                "continuity lease extend-hold",
                "continuity lease record-holder",
            ),
            on_exit_chain=True,
        ),
        GuardSpec(
            "G-CONTROL-ROOT-RUN",
            "run start refuses the control root unless the Run is an authorised recovery Run (#410, #496)",
            "application/core/continuity_execution_service.py::_control_root_run_refusal",
            ("workspace=station",),
            Exempt.BY_COMMAND,
            ("continuity run start",),  # only with --recovery-change and every #496 condition
            on_exit_chain=True,
        ),
        GuardSpec(
            "G-MUTATION-ROOT",
            "control-plane write commands run only in the main git worktree (the control root)",
            "ui/cli/continuity.py::_require_mutation_root",
            ("workspace=control_root",),
            Exempt.NO,
            on_exit_chain=True,
        ),
        GuardSpec(
            "G-GOVERNED-WORKTREE",
            "work happens only in a managed worktree of the control root",
            "infrastructure/control_root_guard.py::require_governed_worktree",
            ("workspace=station",),
            Exempt.NO,
        ),
        GuardSpec(
            "G-SAFE-PATH",
            "workspace paths must stay inside the workspace",
            "infrastructure/control_root_guard.py::require_safe_workspace_path",
            (),
            Exempt.NEVER,
            never_reason="path containment is a safety limit",
        ),
        GuardSpec(
            "G-LEASE-VALID",
            "every Run write needs an unexpired lease held by the caller",
            "infrastructure/continuity_store.py::_require_lease_in_tx",
            ("lease=valid",),
            Exempt.NO,
            on_exit_chain=True,
        ),
        GuardSpec(
            "G-PARKED",
            "a parked Mission's Runs cannot be settled or written",
            "infrastructure/continuity_store.py::_refuse_if_parked",
            ("mission=not_parked",),
            Exempt.NO,
            on_exit_chain=True,
        ),
        GuardSpec(
            "G-AGENT-APPROVAL",
            "an agent cannot approve; approval needs the user's words",
            "ui/cli/approval_pin.py::refuse_agent_approval",
            ("operator=user",),
            Exempt.NEVER,
            on_exit_chain=True,
            never_reason="the user's approval is the one thing no recovery mode may stand in for",
        ),
        GuardSpec(
            "G-APPROVAL-PIN",
            "once an approver PIN is set, approvals need it",
            "ui/cli/approval_pin.py::require_approval_pin",
            ("pin=configured",),
            Exempt.NEVER,
            on_exit_chain=True,
            never_reason="the PIN proves the approver is the user in person",
        ),
        GuardSpec(
            "G-DECISION-GIT-BINDING",
            "a recovery Decision must be tracked and clean in the control root",
            "infrastructure/continuity_store.py::decision_git_binding_issues",
            ("decision=committed_clean",),
            Exempt.NEVER,
            on_exit_chain=True,
            never_reason="release 7 keeps the git check; P2 adds the sealed hash next to it, never instead of it",
        ),
        GuardSpec(
            "G-HEAD-PIN",
            "HEAD must still equal the recovery Run's git_head until the first settlement",
            "infrastructure/continuity_store.py::_validate_recovery_git_head",
            ("git=head_pinned",),
            Exempt.NO,
            on_exit_chain=True,
        ),
        GuardSpec(
            "G-RECOVERY-AUTHORITY",
            "the recovery Run, Work and Decision must satisfy every #496 condition",
            "application/core/continuity_execution_service.py::_recovery_authority_problem",
            ("decision=committed_clean",),
            Exempt.NEVER,
            on_exit_chain=True,
            never_reason="these are the conditions that make the recovery exception narrow",
        ),
        GuardSpec(
            "G-RECOVERY-TARGET-DECISION",
            "the target Work must be writable and bound to a canonical immutable Decision",
            "infrastructure/continuity_store.py::settle_expired_run",
            ("decision=canonical",),
            Exempt.NO,
            on_exit_chain=True,
        ),
        GuardSpec(
            "G-CARD-PREFLIGHT",
            "a writing Work needs an implementation card that passes the preflight",
            "application/core/implementation_card_tier.py::card_is_new",
            (),
            Exempt.NO,
            on_exit_chain=True,
        ),
        GuardSpec(
            "G-ADMISSION",
            "a new card needs a free slot and no scope collision with open cards",
            "application/core/mission_admission.py::admission_verdict",
            (),
            Exempt.NO,
            on_exit_chain=False,  # lives in ``pm approve``; the recovery chain starts at work create (checked 2026-11-02)
        ),
        GuardSpec(
            "G-MEMORY-HEADROOM",
            "heavy commands refuse when the machine has no memory headroom",
            "infrastructure/memory_preflight.py::require_headroom",
            (),
            Exempt.NEVER,
            never_reason="it protects the machine, not the ledger",
        ),
        GuardSpec(
            "G-PAYLOAD-HASH",
            "the launcher refuses a package whose payload hash differs from the manifest",
            "",
            ("payload=hash_ok",),
            Exempt.NEVER,
            on_exit_chain=True,
            never_reason="this is the version and fingerprint comparison itself",
        ),
        GuardSpec(
            "G-LEDGER-SCHEMA",
            "a code version refuses a ledger whose schema it does not know",
            "infrastructure/continuity_store.py::_schema_versions",
            ("ledger=schema_ok",),
            Exempt.NEVER,
            on_exit_chain=True,
            never_reason="older code must not write a newer ledger",
        ),
    )
}


# ---------------------------------------------------------------------------------------------------------------------
# Abnormal-state table
# ---------------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ExitStep:
    """One step of an exit chain: a command template (``{name}`` are filled from the ledger, unknown ones print ``<NAME>``)."""

    title: str
    command: str = ""  # empty for a manual step
    manual: bool = False  # true: a person does it outside the repository (no command)
    needs: tuple[str, ...] = ()  # facts that must hold when the step runs
    who: WhoCan = WhoCan.ANY_AGENT
    note: str = ""


@dataclass(frozen=True)
class AbnormalState:
    state_id: str
    title: str
    conflict_codes: tuple[str, ...]  # codes ``pm orient`` reports for this state ("" tuple: no detector yet)
    detector: str
    exit_steps: tuple[ExitStep, ...]
    who: WhoCan
    switch_safe: bool | None  # may a candidate release be switched in while the state exists; None = not applicable
    needs_code_version: str  # oldest code that can clear the state; never above the candidate under test
    status: str  # "drilled" | "to_drill" | "gap" | "rule"
    excludes: tuple[str, ...] = ()  # state ids that cannot hold at the same time (for generated pairs)
    target_kind: str = ""  # "run" | "work" | "mission" | "" (what ``recovery plan`` takes)
    breaks: tuple[str, ...] = ()  # facts that are false for the whole workspace while this state holds


_SETTLE_CHAIN: tuple[ExitStep, ...] = (
    ExitStep(
        "recovery change order: create and take it to approved",
        "python main.py change create --pid {pid} --domain SCPT --nature DEF --scope LOCAL --applicant <APPLICANT> "
        "--background <BACKGROUND> --necessity <NECESSITY>",
        needs=("identity=clean",),
        note="then `change transition --to approved` for that order (agent sessions need the user's words as --approval-evidence-ref)",
    ),
    ExitStep(
        "recovery Decision naming the target (user words or PIN)",
        "python main.py decision create --change-id <RECOVERY_CHANGE> --approver <APPROVER> --pid {pid} --file .auto-pm/continuity.db "
        "--decision-id <RECOVERY_DECISION> --allow-runtime-action settle_expired_run --target-run-id {run_id} --allow-outcome CANCELLED",
        who=WhoCan.USER,
        needs=("identity=clean", "operator=user"),
    ),
    ExitStep(
        "commit the Decision file in the control root",
        "git add <DECISION_FILE> && git commit -m <MESSAGE>",
        needs=("workspace=control_root",),
        note="HEAD is pinned from here to the first settlement (G-HEAD-PIN): do not sync or commit again until it is done",
    ),
    ExitStep(
        "implementation card for the recovery Work",
        manual=True,
        needs=(),
        note="card file whose path table lists `.auto-pm/continuity.db` as 计划新增 (not 存在: it is not in the git baseline)",
    ),
    ExitStep(
        "create the recovery Work (scope covers .auto-pm/continuity.db)",
        "python main.py continuity work create --work-id <RECOVERY_WORK> --pid {pid} --kind GOVERNANCE --title <TITLE> --owner <AGENT> "
        "--scope .auto-pm/continuity.db --idempotency-key <KEY1> --card-file <CARD_FILE>",
        needs=("identity=clean",),
    ),
    ExitStep(
        "authorize the recovery Work with the recovery Decision",
        "python main.py continuity work authorize --work-id <RECOVERY_WORK> --decision-id <RECOVERY_DECISION> --idempotency-key <KEY2>",
        needs=("identity=clean",),
    ),
    ExitStep(
        "recovery Work to IN_PROGRESS",
        "python main.py continuity work transition --work-id <RECOVERY_WORK> --to IN_PROGRESS --idempotency-key <KEY3>",
        needs=("identity=clean",),
    ),
    ExitStep(
        "start the recovery Run in the control root",
        "python main.py continuity run start --run-id <RECOVERY_RUN> --work-id <RECOVERY_WORK> --executor <AGENT> --adapter codex "
        "--owned .auto-pm/continuity.db --declared-dirty .auto-pm/continuity.db --lease-token <TOKEN> --lease-seconds 900 "
        "--idempotency-key <KEY4> --recovery-change <RECOVERY_CHANGE>",
        needs=("identity=clean", "decision=committed_clean", "git=head_pinned"),
    ),
    ExitStep(
        "recovery Run to RUNNING",
        "python main.py continuity run transition --run-id <RECOVERY_RUN> --to RUNNING --owner <AGENT> --lease-token <TOKEN> "
        "--idempotency-key <KEY5>",
        needs=("identity=clean", "lease=valid"),
    ),
    ExitStep(
        "settle the abandoned Run as CANCELLED",
        "python main.py continuity run settle-expired --target-run-id {run_id} --recovery-run-id <RECOVERY_RUN> --recovery-owner <AGENT> "
        "--recovery-lease-token <TOKEN> --decision-id <RECOVERY_DECISION> --outcome CANCELLED --reason <REASON> --idempotency-key <KEY6>",
        needs=("workspace=control_root", "decision=committed_clean", "git=head_pinned", "decision=canonical"),
    ),
    ExitStep("verify", "python main.py pm orient {pid} && python main.py ledger reconcile {pid}", needs=()),
)


STATES: dict[str, AbnormalState] = {
    state.state_id: state
    for state in (
        AbnormalState(
            "LEASE_EXPIRED",
            "Run lease expired",
            ("LEASE_EXPIRED",),
            "pm orient: the Run under the active Work has a lease whose expiry has passed (continuity_resume_service)",
            (
                ExitStep(
                    "route 1: another agent reclaims the Run (the claimant must differ from the old holder)",
                    "python main.py continuity run reclaim --run-id {run_id} --claimant <NEW_AGENT> --reason <REASON>",
                    note="when the old holder's process cannot be ruled out the user signs the risk with `pm sign-risk`",
                ),
                *_SETTLE_CHAIN,
            ),
            WhoCan.USER,
            False,
            "release 7 (route 1 exists earlier; the settlement chain needs #496)",
            "drilled",
            excludes=("LIVE_RUN_UNDER_FINISHED_WORK",),
            target_kind="run",
        ),
        AbnormalState(
            "LIVE_RUN_UNDER_FINISHED_WORK",
            "a Run is still live but its Work is already accepted, closed or cancelled",
            ("LIVE_RUN_UNDER_FINISHED_WORK",),
            "ledger-wide scan (run_items joined to work_items), independent of the Mission-Work-Run tree orient walks",
            _SETTLE_CHAIN,
            WhoCan.USER,
            True,
            "the version that carries the scan (this change); settling needs #496",
            "to_drill",
            excludes=("LEASE_EXPIRED",),
            target_kind="run",
        ),
        AbnormalState(
            "TERMINAL_LEASE_NOT_FENCED",
            "a Run ended but its lease was never taken off",
            (),
            "none yet (P1: scan leases whose Run is terminal)",
            (
                ExitStep(
                    "fence the lease through a recovery Run (same recovery chain, then this command)",
                    "python main.py continuity run fence-terminal-lease --target-run-id {run_id} --recovery-run-id <RECOVERY_RUN> "
                    "--recovery-owner <AGENT> --recovery-lease-stdin --decision-id <RECOVERY_DECISION> --reason <REASON> --idempotency-key <KEY>",
                    needs=("workspace=control_root", "decision=committed_clean", "git=head_pinned"),
                    who=WhoCan.USER,
                ),
            ),
            WhoCan.USER,
            True,
            "release 7",
            "to_drill",
            target_kind="run",
        ),
        AbnormalState(
            "WORK_BLOCKED",
            "a Work is BLOCKED",
            (),
            "none yet",
            (
                ExitStep(
                    "adjudicate the Work as CANCELLED with evidence",
                    "python main.py continuity work adjudicate --work-id {work_id} --run-set-sha256 <RUN_SET_SHA> --lease-set-sha256 <LEASE_SET_SHA> "
                    "--recovery-run-id <RECOVERY_RUN> --recovery-owner <AGENT> --recovery-lease-stdin --decision-id <RECOVERY_DECISION> "
                    "--outcome CANCELLED --reason <REASON> --idempotency-key <KEY>",
                    who=WhoCan.USER,
                    needs=("workspace=control_root", "decision=committed_clean", "git=head_pinned"),
                ),
            ),
            WhoCan.USER,
            False,
            "release 7",
            "to_drill",
            target_kind="work",
        ),
        AbnormalState(
            "RUN_UNSTARTED",
            "a Run was created but never started",
            (),
            "none yet",
            (
                ExitStep(
                    "revoke the unstarted Run through a recovery Run",
                    "python main.py continuity run revoke-unstarted --target-run-id {run_id} --recovery-run-id <RECOVERY_RUN> "
                    "--recovery-owner <AGENT> --recovery-lease-stdin --decision-id <RECOVERY_DECISION> --reason <REASON> --idempotency-key <KEY>",
                    who=WhoCan.USER,
                    needs=("decision=committed_clean", "git=head_pinned"),
                ),
            ),
            WhoCan.USER,
            True,
            "release 7",
            "to_drill",
            target_kind="run",
        ),
        AbnormalState(
            "EXECUTOR_LOST",
            "the process behind a RUNNING Run died (controller restart)",
            (),
            "`pm orient` prints the pm recover hint for any RUNNING Run",
            (
                ExitStep("look (read-only)", "python main.py pm recover --run-id {run_id}", who=WhoCan.PM),
                ExitStep(
                    "record EXECUTOR_LOST after confirming",
                    "python main.py pm recover --run-id {run_id} --apply",
                    who=WhoCan.PM,
                    note="one-way: after this the ledger cannot go back to release 6a9f127 or earlier",
                ),
            ),
            WhoCan.PM,
            False,
            "release 7",
            "rule",
            target_kind="run",
        ),
        AbnormalState(
            "VERIFYING_STUCK",
            "a Work sits in VERIFYING and nothing moves",
            (),
            "none yet",
            (
                ExitStep("park the card", "python main.py pm park --pid {pid} --reason <REASON> --summary <SUMMARY> --as <AGENT>", who=WhoCan.ANY_AGENT),
                ExitStep("renew the lease", "python main.py continuity lease renew --run-id {run_id} --owner <AGENT>", who=WhoCan.ANY_AGENT),
            ),
            WhoCan.ANY_AGENT,
            True,
            "release 7 (TD-256 fix, #407)",
            "to_drill",
            target_kind="run",
        ),
        AbnormalState(
            "RUNTIME_IDENTITY_DIVERGENCE",
            "release pointer and loaded package disagree",
            ("RUNTIME_IDENTITY_DIVERGENCE",),
            "workspace_context_service: the pointer's release id differs from the loaded package",
            (
                ExitStep(
                    "case 1 (the loaded package passes its own hash and opens the ledger): clear it with the recovery order (P2) or repair the pointer",
                    manual=True,
                    who=WhoCan.USER,
                    note="today the write commands of the settlement chain are all refused while this holds; `run settle-expired` alone only warns",
                ),
                ExitStep(
                    "case 2 (the launcher fell back to previous): FIX ACTIVE FIRST, then recover on active; never write the ledger on previous",
                    manual=True,
                    who=WhoCan.USER,
                    note="a manual step outside the repository (rebuild or repoint the release pointer so the active release verifies)",
                ),
            ),
            WhoCan.USER,
            None,
            "any code that lets the active release verify (the exit does not depend on previous)",
            "gap",
            target_kind="",
            breaks=("identity=clean",),
        ),
        AbnormalState(
            "RUNTIME_IDENTITY_UNVERIFIED",
            "the runtime identity could not be established",
            ("RUNTIME_IDENTITY_UNVERIFIED",),
            "workspace_context_service: no release pointer or manifest to compare",
            (ExitStep("restore the release pointer and manifest", manual=True, who=WhoCan.USER),),
            WhoCan.USER,
            None,
            "current release",
            "gap",
            breaks=("identity=clean",),
        ),
        AbnormalState(
            "MULTIPLE_ACTIVE_MISSIONS",
            "two active Missions in one project (data damage)",
            ("MULTIPLE_ACTIVE_MISSIONS",),
            "continuity_resume_service: more than one ACTIVE Mission",
            (),
            WhoCan.NOBODY,
            False,
            "none registered",
            "gap",
        ),
        AbnormalState(
            "MULTIPLE_ACTIVE_WORKS",
            "several execution-active Works and no Mission root to pick one",
            ("MULTIPLE_ACTIVE_WORKS",),
            "continuity_resume_service",
            (),
            WhoCan.NOBODY,
            False,
            "none registered",
            "gap",
        ),
        AbnormalState(
            "MULTIPLE_ACTIVE_RUNS",
            "several live Runs under one Work",
            ("MULTIPLE_ACTIVE_RUNS",),
            "continuity_resume_service",
            (),
            WhoCan.NOBODY,
            False,
            "none registered",
            "gap",
        ),
        AbnormalState(
            "MISSION_ROOT_NOT_EXECUTION_ACTIVE",
            "the Mission's root Work is no longer execution-active",
            ("MISSION_ROOT_NOT_EXECUTION_ACTIVE",),
            "continuity_resume_service",
            (),
            WhoCan.NOBODY,
            False,
            "none registered",
            "gap",
        ),
        AbnormalState(
            "CLOSE_HALF_DONE",
            "acceptance recorded but the close stopped half way",
            (),
            "none yet",
            (ExitStep("retry the close", "python main.py pm close --mission-id <MISSION_ID>", who=WhoCan.ANY_AGENT, needs=("identity=clean",)),),
            WhoCan.ANY_AGENT,
            False,
            "current release",
            "to_drill",
            target_kind="mission",
        ),
        AbnormalState(
            "CONTROL_ROOT_DRIFT",
            "control root behind or ahead of main, stations full, or files in scope dirty",
            (),
            "pm sync notice (advisory)",
            (
                ExitStep("fast-forward sync", "git -C <CONTROL_ROOT> pull --ff-only origin main", who=WhoCan.PM),
                ExitStep("close or sweep stations (deletion needs the user)", "python main.py worktree sweep", who=WhoCan.USER),
            ),
            WhoCan.PM,
            False,
            "current release",
            "to_drill",
        ),
        AbnormalState(
            "LEDGER_NEWER_THAN_CODE",
            "the ledger was written by a newer release (one-way events)",
            (),
            "ledger schema check at open",
            (),
            WhoCan.NOBODY,
            None,
            "the release that wrote it or later",
            "rule",
        ),
        AbnormalState(
            "MISSION_PARKED",
            "the target Mission is parked",
            (),
            "`_refuse_if_parked`",
            (ExitStep("take the card back", "python main.py pm unpark --mission-id <MISSION_ID> --approval-evidence-ref <USER_WORDS_REF>", who=WhoCan.USER),),
            WhoCan.USER,
            False,
            "current release",
            "to_drill",
            target_kind="mission",
        ),
    )
}


def conflict_state(code: str) -> AbnormalState | None:
    """The abnormal state a ``pm orient`` conflict code belongs to (``None`` when the code is unknown)."""

    for state in STATES.values():
        if code in state.conflict_codes:
            return state
    return None


def exit_hint(code: str, detail: str = "") -> str:
    """One line for ``pm orient`` under a conflict code; never empty, so no conflict is left without a next step.

    ``detail`` names the objects the detector found (for example the stuck Run ids) and is printed after the code.
    """

    state = conflict_state(code)
    subject = f"{code}（{detail}）" if detail else code
    if state is None:
        return f"{subject}: 矩阵里没有这个冲突码，请先登记（interlock_matrix.STATES），在此之前不要自己改账本"
    if not state.exit_steps:
        return f"{subject}: 矩阵登记为缺口，没有现成出口；交给协调者处理，不要自己改账本"
    return (
        f"{subject}: 出口共 {len(state.exit_steps)} 步，谁能做={state.who.value}；"
        f"完整命令清单：python main.py continuity recovery plan --pid <项目编号> --state {state.state_id}"
    )


# ---------------------------------------------------------------------------------------------------------------------
# Deadlock definition (pure functions; the contract test and, later, the release gate call them)
# ---------------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Deadlock:
    """``state_id`` cannot be cleared while ``held_by`` (another state, or the state itself) holds: step ``step_index`` is refused."""

    state_id: str
    held_by: str  # the other state whose broken fact blocks the step; equals state_id for the state's own breaks
    step_index: int
    command: str  # the matrix command key
    guard_id: str
    fact: str


def step_commands(command: str) -> list[str]:
    """Matrix command keys behind one exit step (a step may chain commands with ``&&``); non-cockpit steps (git ...) give none."""

    keys: list[str] = []
    for part in command.split("&&"):
        words = part.split()
        if words[:2] != ["python", "main.py"]:
            continue
        words = words[2:]
        words = [word for word in words if not word.startswith(("-", "<", "{"))]
        for size in range(len(words), 0, -1):
            candidate = " ".join(words[:size])
            if candidate in COMMANDS:
                keys.append(candidate)
                break
        else:
            keys.append("?" + " ".join(words[:3]))
    return keys


def is_waived(guard: GuardSpec, command_key: str) -> bool:
    """Does the code today let ``command_key`` run past ``guard``? (P2 adds the recovery order as a second way.)"""

    return guard.exempt is Exempt.BY_COMMAND and command_key in guard.exempt_commands


def find_deadlocks(
    states: dict[str, AbnormalState] | None = None,
    commands: dict[str, CommandSpec] | None = None,
    guards: dict[str, GuardSpec] | None = None,
    *,
    pair_with_others: bool = True,
) -> list[Deadlock]:
    """Every exit step that an applicable guard refuses because a fact is broken and the guard is not waived for that command.

    Each state is checked alone (its own ``breaks``) and, with ``pair_with_others``, together with every other state that can hold at
    the same time (``excludes`` removes the impossible pairs).  Steps whose command is not in the command table are skipped here and
    reported separately by the contract test (``unmodelled_steps``).
    """

    states = STATES if states is None else states
    commands = COMMANDS if commands is None else commands
    guards = GUARDS if guards is None else guards
    found: list[Deadlock] = []
    for state in states.values():
        partners: list[AbnormalState | None] = [None]
        if pair_with_others:
            partners.extend(
                other
                for other in states.values()
                if other.state_id != state.state_id
                and other.state_id not in state.excludes
                and state.state_id not in other.excludes
                and other.breaks
            )
        for other in partners:
            broken = set(state.breaks) | set(other.breaks if other else ())
            if not broken:
                continue
            holder = other.state_id if other and set(other.breaks) & broken else state.state_id
            for index, step in enumerate(state.exit_steps, start=1):
                if not step.command:
                    continue
                for key in step_commands(step.command):
                    spec = commands.get(key)
                    if spec is None:
                        continue
                    for guard_id in spec.guards:
                        guard = guards[guard_id]
                        for fact in guard.forbids:
                            if fact in broken and not is_waived(guard, key):
                                found.append(Deadlock(state.state_id, holder, index, key, guard_id, fact))
    return found


def unmodelled_steps(states: dict[str, AbnormalState] | None = None) -> set[str]:
    """Matrix-less commands that exit steps use (``?`` + words): the deadlock check cannot see them. Shrinks as P1 inventories them."""

    states = STATES if states is None else states
    found: set[str] = set()
    for state in states.values():
        for step in state.exit_steps:
            for key in step_commands(step.command) if step.command else []:
                if key.startswith("?"):
                    found.add(key[1:])
    return found
