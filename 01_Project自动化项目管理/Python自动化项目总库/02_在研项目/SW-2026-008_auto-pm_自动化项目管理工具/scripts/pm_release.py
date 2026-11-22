"""Resume an approved, rolled-back release when the installed CLI predates resume."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from auto_pm.application.core import release_deploy_check, release_wiring  # noqa: E402
from auto_pm.application.core.agent_registry import use_ledger_roster  # noqa: E402
from auto_pm.application.core.memory_gate_arming import arm_for_heavy_job  # noqa: E402
from auto_pm.application.core.release_deploy import DeployError  # noqa: E402
from auto_pm.application.core.release_ledger import LedgerError  # noqa: E402
from auto_pm.contracts.user_evidence import user_evidence_problem  # noqa: E402
from auto_pm.infrastructure.control_root_guard import (  # noqa: E402
    ControlRootGuardError,
    require_control_root,
    require_governed_worktree,
)


def audit_candidate(root: Path, station: Path, verify_gates: bool) -> None:
    """Use the installed control-root merge auditor for bootstrap from a clean worktree."""
    merge_path = root / release_deploy_check.PROJECT_DIR / "scripts" / "pm_merge.py"
    spec = importlib.util.spec_from_file_location("_control_root_pm_merge", merge_path)
    if spec is None or spec.loader is None:
        raise ValueError("控制根审计入口不可用")
    merge: ModuleType = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = merge
    spec.loader.exec_module(merge)
    try:
        branch = merge.Git(station).out("symbolic-ref", "--short", "HEAD")
        base = merge.Git(root).rev("refs/heads/main")
        head = merge.Git(station).rev("HEAD")
        plan = merge.Plan(branch, head, "", [], [], [], [], [], base=base)
        merge.audit_receipt(root, station.name, plan)
        if verify_gates:
            gates = merge.run_gates(root, station, full=True)
            if not gates.ok or merge.Git(station).rev("HEAD") != head or merge.Git(root).rev("refs/heads/main") != base:
                raise ValueError("工位的门禁未通过或候选已变化")
    except merge.RefusedError as error:
        raise ValueError(str(error)) from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("commit")
    parser.add_argument("--gate-verdict", required=True, type=Path)
    parser.add_argument("--audit-signoff", required=True, type=Path)
    parser.add_argument("--no-check-only", action="store_true", help="Finish the prior release after preflight")
    parser.add_argument("--confirm-ref", default="")
    parser.add_argument("--approver", default="")
    parser.add_argument("--audited-candidate", action="store_true", help="Bootstrap from an independently approved worktree")
    args = parser.parse_args()
    try:
        root = require_control_root(Path.cwd())
    except ControlRootGuardError as error:
        parser.error(str(error))
    source = PROJECT.parents[3]
    code, changes = release_wiring.run_process(
        ["git", "-c", "core.fsmonitor=false", "status", "--porcelain", "--untracked-files=all",
         "--", "auto_pm", "scripts/pm_release.py", "scripts/release_event_chain_drill.py"],
        PROJECT,
    )
    if code or changes.strip():
        parser.error("发布续办只执行已提交的干净源码")
    if source != root:
        if not args.audited_candidate:
            parser.error("工位续办入口必须带 --audited-candidate 并通过独立审计")
        try:
            audit_candidate(root, require_governed_worktree(root, source), args.no_check_only)
        except (ValueError, ControlRootGuardError) as error:
            parser.error(str(error))
    report = release_deploy_check.preflight(
        root, args.commit, gate_verdict=args.gate_verdict, audit_signoff=args.audit_signoff
    )
    print("\n".join(report.render()), flush=True)
    if not report.ok or not report.resume_from:
        print("未核实到可续办的原发布，不写入")
        return 2
    if not args.no_check_only:
        return 0
    use_ledger_roster(root)
    if (problem := user_evidence_problem(args.confirm_ref)) or not args.approver.strip():
        parser.error(problem or "真续办必须给 --approver")
    identity = release_wiring.cockpit_identity(root)
    if (
        identity.get("configured_release_id") != report.resume_from
        or identity.get("effective_release_id") != report.resume_from
        or identity.get("runtime_fallback_reason")
        or identity.get("conflicts")
    ):
        print("现役运行身份未通过，拒绝续办")
        return 2
    arm_for_heavy_job("deploy-gate")
    try:
        deployed = release_wiring.real_deploy(
            root, report, approver=args.approver, confirm_ref=args.confirm_ref, card_file=None,
            drill_script=PROJECT / "scripts" / "release_event_chain_drill.py",
        )
    except LedgerError as error:
        parser.error(str(error))
    except DeployError as error:
        print(f"部署没有完成：{error}")
        return 3 if error.rolled_back else 4 if error.pointers_moved else 2
    print(f"已部署 {deployed.release_id}，变更单 {deployed.change_id} 已完成，回执 {deployed.receipt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
