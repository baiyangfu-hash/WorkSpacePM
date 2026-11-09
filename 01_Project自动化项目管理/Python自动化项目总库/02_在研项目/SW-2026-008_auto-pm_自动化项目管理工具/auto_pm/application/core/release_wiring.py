"""The real ports for the one-command deploy (D-146 card 6a): ledger, release operations and the post-switch self-checks.

``release_deploy.deploy`` only knows three small interfaces.  This module fills them in with the real thing, still without a command
line switch (that is card 6b), so nothing here is reachable from ``main.py`` yet.

* **Reads of the ledger are in-process and strictly read-only** (change orders, Work, Run, Checkpoint, Decision file): the cockpit has no
  ``show`` commands for Work, Run or Checkpoint.  **Every write goes through ``main.py``** in a subprocess, the same commands the
  hand-written script ran, so all cockpit guards apply.
* A change order is recognised as this release's by an exact ``RELEASE=<id>`` item in its references (``release_ledger.pick_change``).
* The self-check set is the list the 69b7ed6 deploy ran plus the two later additions (pre-commit dry run, event chain drill; the ruling of
  2026-11-08 — three earlier deploys had skipped them).  Their definitions come from the hand-written deploy scripts (d07p_deploy.sh) and
  the rel7 evidence; the drill script itself is a local file, so its path is a required argument.  Nothing passes by default: a missing
  hook, a dirty index, a missing script or an unreadable result is a failure.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from auto_pm.application.core import release_deploy as rd
from auto_pm.application.core import release_ops as ops
from auto_pm.application.core.release_deploy import REQUIRED_SELF_CHECKS, DeployError, SelfCheck
from auto_pm.application.core.release_deploy_check import CONTAINER, exact_tree_ok
from auto_pm.application.core.release_ledger import PROJECT_ID, DeployPlan, LedgerError, pick_change

COMMAND_TIMEOUT_SECONDS = 300
LEDGER_PROJECTS = ("SW-2026-008", "SYS-2026-001", "SW-2026-009", "DJ-2026-005")
SMOKE_PROJECTS = ("SW-2026-008", "SYS-2026-001")
HELP_COMMANDS = (
    "pm handoff", "pm takeover", "pm orient", "continuity run reclaim", "continuity lease record-holder", "gui",
    "long-run", "pm state-backup", "pm triage", "claim", "pr", "release",
)

Runner = Callable[[Sequence[str]], tuple[int, str]]
Exec = Callable[[Sequence[str], Path], tuple[int, str]]
LEDGER_CLEAN = "台账缺失: 0 条, 台账多余(孤儿): 0 条, 状态不一致: 0 条"


def run_process(argv: Sequence[str], cwd: Path, *, timeout: int = COMMAND_TIMEOUT_SECONDS) -> tuple[int, str]:
    """Run any program in ``cwd``; returns ``(exit code, stdout + stderr)``."""

    try:
        done = subprocess.run(  # noqa: S603 - fixed argv, no shell
            list(argv), cwd=cwd, capture_output=True, text=True, encoding="utf-8",
            errors="replace",  # lenient-decode: 子进程输出只用来展示和解析，不当作数据真源
            timeout=timeout, check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return 255, str(error)
    return done.returncode, (done.stdout or "") + (done.stderr or "")


class WiringError(RuntimeError):
    """The real ports cannot be built or used as asked."""


class ChangeReader(Protocol):
    def list_change_requests(self, project_id: str, status: str | None = None, domain: str | None = None) -> list[Any]: ...
    def get_change_request(self, change_number: str, project_id: str | None = None) -> Any: ...


class ContinuityReader(Protocol):
    def get_work(self, work_id: str) -> Any: ...
    def find_run(self, run_id: str) -> Any: ...
    def get_checkpoint(self, checkpoint_id: str) -> Any: ...


def cockpit_runner(control_root: Path, *, python: str = sys.executable, timeout: int = COMMAND_TIMEOUT_SECONDS) -> Runner:
    """Run ``main.py <args>`` in the control root; returns ``(exit code, stdout + stderr)``, never raises on a non-zero exit."""

    def run(args: Sequence[str]) -> tuple[int, str]:
        try:
            done = subprocess.run(  # noqa: S603 - fixed argv, no shell
                [python, str(control_root / "main.py"), *args], cwd=control_root, capture_output=True, text=True, encoding="utf-8",
                errors="replace",  # lenient-decode: 子进程输出只用来展示和解析编号，不当作数据真源
                timeout=timeout, check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            return 255, str(error)
        return done.returncode, (done.stdout or "") + (done.stderr or "")

    return run


class CockpitLedgerPort:
    """``LedgerPort`` over the real cockpit: reads in-process (read-only), writes by subprocess."""

    def __init__(
        self, control_root: Path, *, run: Runner, changes: ChangeReader, store: ContinuityReader, station_opener: Callable[[Path], None] | None = None,
    ) -> None:
        self._root = Path(control_root)
        self._run = run
        self._changes = changes
        self._store = store
        self._open_station = station_opener or self._git_worktree

    def cli(self, *args: str) -> str:
        code, output = self._run(args)
        if code != 0:
            raise LedgerError(f"命令失败（退出码 {code}）：main.py {' '.join(args[:4])} … {output.strip()[-300:]}")
        return output

    def find_change(self, release_id: str) -> str:
        rows: list[tuple[str, str]] = []
        for summary in self._changes.list_change_requests(PROJECT_ID, domain="SCPT"):
            if getattr(summary, "business_nature", "") != "CFG":
                continue
            full = self._changes.get_change_request(summary.change_number, project_id=PROJECT_ID)
            if full is not None:
                rows.append((summary.change_number, str(full.references)))
        return pick_change(release_id, rows)

    def change_status(self, change_id: str) -> str:
        found = self._changes.get_change_request(change_id, project_id=PROJECT_ID)
        return "" if found is None else str(found.status)

    def decision_exists(self, decision_id: str) -> bool:
        return (self._root / ".auto-pm" / "decisions" / f"{decision_id}.json").is_file()

    def work_state(self, work_id: str) -> str | None:
        try:
            return str(self._store.get_work(work_id).state)
        except Exception as error:  # noqa: BLE001 - only "does not exist" means None; any other failure must surface
            if "不存在" in str(error):
                return None
            raise

    def run_state(self, run_id: str) -> str | None:
        found = self._store.find_run(run_id)
        return None if found is None else str(found.state)

    def checkpoint_exists(self, checkpoint_id: str) -> bool:
        try:
            self._store.get_checkpoint(checkpoint_id)
        except Exception as error:  # noqa: BLE001
            if "不存在" in str(error):
                return False
            raise
        return True

    def ensure_station(self, path: Path) -> None:
        if (Path(path) / ".git").exists():
            return
        self._open_station(Path(path))

    def _git_worktree(self, path: Path) -> None:
        done = subprocess.run(  # noqa: S603, S607 - fixed argv, no shell
            ["git", "-C", str(self._root), "worktree", "add", "--detach", str(path), "HEAD"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=COMMAND_TIMEOUT_SECONDS, check=False,  # lenient-decode: 只展示失败原因
        )
        if done.returncode != 0:
            raise LedgerError(f"建不出部署工位 {path}：{done.stderr.strip()[-200:]}")


class ReleaseOpsAdapter:
    """``ReleaseOpsPort`` over ``release_ops``; any failure of a release operation reaches ``deploy`` as a ``DeployError``."""

    def __init__(self, root: Path, repo: Path, commit: str, release_id: str, identity: ops.Identity) -> None:
        self._root = Path(root)
        self._repo = Path(repo)
        self._commit = commit
        self._release_id = release_id
        self._identity = identity

    def active_release(self) -> str:
        return ops.pointer_release(ops.container_of(self._root), "active_release.json")

    def is_built(self, release_id: str) -> bool:
        return (ops.container_of(self._root) / "releases" / release_id).is_dir()

    def build(self) -> dict[str, Any]:
        try:
            return ops.build(self._root, self._repo, self._commit)
        except Exception as error:  # noqa: BLE001 - whatever build raised, the deploy stops with its own error type
            raise DeployError(f"构建发布失败，什么都没留下：{error}") from error

    def switch(self, backup: Path) -> dict[str, Any]:
        return ops.switch(self._root, self._release_id, self.active_release(), backup, self._identity)

    def rollback(self, backup: Path) -> dict[str, Any]:
        return ops.rollback(self._root, backup, self._identity)

    def manifest_entry_sha256(self, release_id: str) -> str:
        """The same digest ``build`` reports, read back from the manifest, so a resumed deploy still has it for the receipt."""

        try:
            manifest = json.loads((ops.container_of(self._root) / "deployment_manifest.json").read_text(encoding="utf-8"))
            entry = json.dumps(manifest["releases"][release_id], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise DeployError(f"读不出清单里 {release_id} 的条目：{error}") from error
        return hashlib.sha256(entry.encode("utf-8")).hexdigest()


def build_self_checks(
    *, root: Path, release_id: str, old_release: str, older_release: str, run: Runner, identity: ops.Identity,
    card_file: Path, drill_script: Path, execute: Exec = run_process,
) -> dict[str, SelfCheck]:
    """The full self-check set, keyed exactly by ``REQUIRED_SELF_CHECKS``.

    ``card_file`` is the implementation card the card precheck runs against; ``drill_script`` is the event-chain drill (a local file).
    Both must exist now, so a typo is refused before anything is switched.
    """

    for label, path in (("预检用的卡文件", card_file), ("事件链演练脚本", drill_script)):
        if not Path(path).is_file():
            raise WiringError(f"{label}不存在：{path}")
    container = ops.container_of(Path(root))
    checks: dict[str, SelfCheck] = {}

    def identity_check() -> tuple[bool, str]:
        seen = identity(Path(root))
        return ops._identity_matches(seen, release_id), json.dumps(seen, ensure_ascii=False, sort_keys=True)  # noqa: SLF001 - same rule as switch

    def help_check(command: str) -> SelfCheck:
        def check() -> tuple[bool, str]:
            code, output = run([*command.split(), "--help"])
            return code == 0, f"exit={code}" if code == 0 else f"exit={code} {output.strip()[-120:]}"
        return check

    def smoke_check(project: str) -> SelfCheck:
        def check() -> tuple[bool, str]:
            code, output = run(["pm", "orient", project, "--json"])
            if code != 0:
                return False, f"exit={code} {output.strip()[-120:]}"
            try:
                data = json.loads(output[output.index("{"):])
            except (ValueError, json.JSONDecodeError):
                return False, "orient 输出读不成 JSON"
            conflicts = data.get("conflicts") or []
            return not conflicts, f"conflicts={conflicts}"
        return check

    def ledger_check(project: str) -> SelfCheck:
        def check() -> tuple[bool, str]:
            code, output = run(["ledger", "reconcile", project])  # no --fix: a post-switch check must not write
            clean = code == 0 and LEDGER_CLEAN in output
            return clean, "0/0/0" if clean else f"exit={code} 对账不是 0/0/0：{output.strip()[-120:]}"
        return check

    def precheck() -> tuple[bool, str]:
        code, output = run(["cli", "implementation-card", "precheck", "--card-file", str(card_file)])
        return code == 0, f"exit={code}" if code == 0 else f"exit={code} {output.strip()[-120:]}"

    def hook_dry_run() -> tuple[bool, str]:
        hook = Path(root) / ".git" / "hooks" / "pre-commit"
        if not hook.is_file():
            return False, "控制根没有 pre-commit 钩子，没法干跑"
        code, staged = execute(["git", "diff", "--cached", "--name-only"], Path(root))
        if code != 0 or staged.strip():
            return False, "控制根暂存区不是空的（或读不出），钩子干跑不可信"
        code, output = execute(["sh", ".git/hooks/pre-commit"], Path(root))
        return code == 0, f"exit={code}" if code == 0 else f"exit={code} {output.strip()[-120:]}"

    def event_chain_drill() -> tuple[bool, str]:
        db = Path(root) / ".auto-pm" / "continuity.db"
        if not db.is_file():
            return False, "没有 continuity.db"
        scratch = Path(tempfile.mkdtemp(prefix="pmf-drill-"))
        try:
            (scratch / ".auto-pm").mkdir()
            if (Path(root) / ".auto-pm" / "decisions").is_dir():
                shutil.copytree(Path(root) / ".auto-pm" / "decisions", scratch / ".auto-pm" / "decisions")
            source = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
            target = sqlite3.connect(scratch / ".auto-pm" / "continuity.db")
            try:
                source.backup(target)  # online copy; the live database is only read
            finally:
                target.close()
                source.close()
            code, output = execute([sys.executable, "-B", "-I", str(drill_script), str(container / "releases" / release_id), str(scratch)], Path(root))
            try:
                result = json.loads(output[output.index("{"):output.rindex("}") + 1])
            except ValueError:
                return False, f"演练输出读不成 JSON（exit={code}）"
            good = code == 0 and result.get("chain_breaks") == 0 and not result.get("run_activity_fail") and "work_run_read_error" not in result
            return good, f"events={result.get('events_total')} breaks={result.get('chain_breaks')} run_activity_fail={len(result.get('run_activity_fail') or [])}"
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def tree_check(target: str) -> SelfCheck:
        def check() -> tuple[bool, str]:
            return exact_tree_ok(container, target)
        return check

    checks["identity"] = identity_check
    for command in HELP_COMMANDS:
        checks[f"help {command}"] = help_check(command)
    for project in SMOKE_PROJECTS:
        checks[f"smoke pm orient {project}"] = smoke_check(project)
    for project in LEDGER_PROJECTS:
        checks[f"ledger {project}"] = ledger_check(project)
    checks["exact-tree new"] = tree_check(release_id)
    checks["exact-tree old"] = tree_check(old_release)
    checks["exact-tree older"] = tree_check(older_release)
    checks["card precheck"] = precheck
    checks["pre-commit hook dry run"] = hook_dry_run
    checks["event chain drill"] = event_chain_drill
    absent = [name for name in REQUIRED_SELF_CHECKS if name not in checks]
    if absent:
        raise WiringError("自检集与必备清单对不上，缺：" + "；".join(absent))
    return checks


IDENTITY_PROJECT = "SW-2026-008"


def cockpit_identity(root: Path, *, python: str = sys.executable, run: Exec = run_process) -> dict[str, Any]:
    """The runtime identity as a **fresh process** sees it (so a switch is judged by the new release, not by the one already loaded here).

    Runs ``main.py pm resume SW-2026-008 --json`` in ``root`` and keeps the four identity fields plus the conflict codes, the same
    reading the hand-written script made.  Anything unreadable is returned as an empty identity, which never matches a release.
    """

    code, output = run([python, "-B", str(Path(root) / "main.py"), "pm", "resume", IDENTITY_PROJECT, "--json"], Path(root))
    if code != 0 or "{" not in output:
        return {}
    try:
        data, _end = json.JSONDecoder().raw_decode(output[output.index("{"):])
    except ValueError:
        return {}
    context = data.get("context") or {}
    result = {key: context.get(key) for key in ("configured_release_id", "effective_release_id", "runtime_load_path", "runtime_fallback_reason")}
    result["conflicts"] = [c.get("code") if isinstance(c, dict) else c for c in (data.get("conflicts") or [])]
    return result


def plan_for(root: Path, report: Any, *, approver: str, confirm_ref: str, now: datetime | None = None) -> tuple[DeployPlan, Path]:
    """The ledger plan and the pointer-backup folder of a deploy of ``report.release_id`` from the control root ``root``.

    The old release is the active pointer *now*; the evidence folder is per release, and the backup folder name carries the time of the
    first attempt (``release_deploy`` reuses the first one on a resume).
    """

    base = Path(root)
    container = ops.container_of(base)
    old = ops.pointer_release(container, "active_release.json")
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    evidence = base / ".auto-pm" / "reports" / f"release-deploy-{report.release_id}"
    prefix = CONTAINER.as_posix()
    paths = (
        f"{prefix}/deployment_manifest.json", f"{prefix}/active_release.json", f"{prefix}/previous_release.json", f"{prefix}/releases/{report.release_id}",
    )
    plan = DeployPlan(
        release_id=report.release_id, old_release=old, commit=report.commit, confirm_ref=confirm_ref, approver=approver, paths=paths,
        station=base / ".auto-pm" / "worktrees" / f"deploy-{report.release_id}", evidence_dir=evidence,
    )
    return plan, evidence / f"pointer_backup_{stamp}"


def real_deploy(
    root: Path, report: Any, *, approver: str, confirm_ref: str, card_file: Path, drill_script: Path,
) -> rd.DeployResult:
    """Assemble the real ports and run the whole deploy.  Reached only from ``release deploy --no-check-only`` after a green preflight."""

    from auto_pm.domain.change.change_service import ChangeService
    from auto_pm.infrastructure.continuity_store import ContinuityStore

    base = Path(root)
    plan, backup = plan_for(base, report, approver=approver, confirm_ref=confirm_ref)
    container = ops.container_of(base)
    older = ops.pointer_release(container, "previous_release.json")
    identity: ops.Identity = cockpit_identity
    run = cockpit_runner(base)
    ledger = CockpitLedgerPort(base, run=run, changes=ChangeService(str(base)), store=ContinuityStore(base))
    adapter = ReleaseOpsAdapter(base, base, plan.commit, plan.release_id, identity)
    checks = build_self_checks(
        root=base, release_id=plan.release_id, old_release=plan.old_release, older_release=older, run=run, identity=identity,
        card_file=card_file, drill_script=drill_script,
    )
    return rd.deploy(
        plan, preflight=report, ops=adapter, ledger=ledger, checks=checks, backup=backup,
        rollback_command=f"main.py release rollback {backup}",
        background=f"一键发版：把有效版本从 {plan.old_release} 切到 {plan.release_id}（提交 {plan.commit[:12]}）",
        necessity="新提交的修复只有切成有效版本才对所有对话生效；切换前预检、切换后自检，任一失败即回退指针",
    )
