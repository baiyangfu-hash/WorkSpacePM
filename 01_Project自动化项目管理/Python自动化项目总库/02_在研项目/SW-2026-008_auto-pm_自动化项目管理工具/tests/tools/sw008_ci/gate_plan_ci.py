"""Server-side zero-trust CI gate tier planner using Python stdlib only.

Reads ``base..candidate`` changed paths directly from git and recomputes the
allowed gate tier (``L2`` vs ``L3``) and affected test groups on the trusted
workflow runner, overriding client hints upward to ``L3`` whenever required.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import subprocess
import sys
import types
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_tier_policy() -> tuple[tuple[str, ...], Callable[..., Any]]:
    """Load tier policy using stdlib only without triggering ``auto_pm.__init__`` third-party imports."""
    if "auto_pm" in sys.modules:
        mod = importlib.import_module("auto_pm.application.core.gate_tier_policy")
        return tuple(mod.ALL_GATE_GROUPS), mod.classify_gate_tier

    packages = (
        ("auto_pm", ROOT / "auto_pm"),
        ("auto_pm.application", ROOT / "auto_pm" / "application"),
        ("auto_pm.application.core", ROOT / "auto_pm" / "application" / "core"),
        ("auto_pm.infrastructure", ROOT / "auto_pm" / "infrastructure"),
    )
    for pkg_name, pkg_dir in packages:
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(pkg_dir)]
        pkg.__package__ = pkg_name
        sys.modules[pkg_name] = pkg
        if "." in pkg_name:
            parent_name, attr_name = pkg_name.rsplit(".", 1)
            setattr(sys.modules[parent_name], attr_name, pkg)

    modules = (
        ("auto_pm.infrastructure.memory_preflight", ROOT / "auto_pm" / "infrastructure" / "memory_preflight.py"),
        ("auto_pm.application.core.gate_env_preflight", ROOT / "auto_pm" / "application" / "core" / "gate_env_preflight.py"),
        ("auto_pm.application.core.gate_run_service", ROOT / "auto_pm" / "application" / "core" / "gate_run_service.py"),
        ("auto_pm.application.core.gate_tier_policy", ROOT / "auto_pm" / "application" / "core" / "gate_tier_policy.py"),
    )
    loaded: dict[str, types.ModuleType] = {}
    for mod_name, mod_path in modules:
        spec = importlib.util.spec_from_file_location(mod_name, mod_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"无法加载纯标准库模块: {mod_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        parent_name, attr_name = mod_name.rsplit(".", 1)
        setattr(sys.modules[parent_name], attr_name, module)
        loaded[mod_name] = module

    policy = loaded["auto_pm.application.core.gate_tier_policy"]
    groups: tuple[str, ...] = tuple(str(g) for g in policy.ALL_GATE_GROUPS)
    classifier: Callable[..., Any] = policy.classify_gate_tier
    return groups, classifier


ALL_GATE_GROUPS, classify_gate_tier = _load_tier_policy()

PROJ_PREFIX = "01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/"


@dataclass(frozen=True)
class GatePlan:
    tier: str
    groups: tuple[str, ...]
    run_plugin: bool
    reasons: tuple[str, ...]
    changed_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "groups": list(self.groups),
            "run_plugin": self.run_plugin,
            "reasons": list(self.reasons),
            "changed_count": self.changed_count,
        }


def _full_plan(reason: str, *, changed_count: int = 0) -> GatePlan:
    return GatePlan(
        tier="L3",
        groups=ALL_GATE_GROUPS,
        run_plugin=True,
        reasons=(reason,) if reason else (),
        changed_count=changed_count,
    )


def _changed_paths(repo: Path, base: str, candidate: str) -> tuple[str, ...] | None:
    proc = subprocess.run(
        [
            "git",
            "-c",
            "core.quotepath=false",
            "-C",
            str(repo),
            "diff",
            "--name-only",
            "--no-renames",
            "-z",
            f"{base}..{candidate}",
        ],
        capture_output=True,
        check=False,
        timeout=30,
    )
    if proc.returncode != 0:
        return None
    raw = proc.stdout.decode("utf-8", errors="replace")  # lenient-decode: git paths may include host bytes
    return tuple(item for item in raw.split("\x00") if item)


def _trusted_project_dir(repo: Path) -> Path:
    candidate = repo / PROJ_PREFIX.rstrip("/")
    if (candidate / "tests" / "tools" / "tier_core_list.json").is_file():
        return candidate
    return ROOT


def plan_ci_gate(
    repo: Path,
    base: str,
    candidate: str,
    *,
    requested_tier: str = "L3",
) -> GatePlan:
    """Recompute the CI execution plan from ``base..candidate`` without trusting client hints."""
    norm_request = requested_tier.strip().upper() or "L3"
    if norm_request == "L3":
        return _full_plan("请求执行 L3 全量门禁")
    if norm_request != "L2":
        return _full_plan(f"未知请求档次 {requested_tier!r}，fail-closed 走 L3 全量门禁")
    if not base or not candidate or base == candidate:
        return _full_plan("缺少独立比较基线，fail-closed 走 L3 全量门禁")

    changed = _changed_paths(repo, base, candidate)
    if changed is None:
        return _full_plan("无法读取 base..candidate 差异文件，fail-closed 走 L3 全量门禁")
    if not changed:
        return _full_plan("base..candidate 差异列表为空，fail-closed 走 L3 全量门禁", changed_count=0)

    inside = [path[len(PROJ_PREFIX) :] for path in changed if path.startswith(PROJ_PREFIX)]
    outside = [path for path in changed if not path.startswith(PROJ_PREFIX)]
    decision = classify_gate_tier(
        inside,
        project=_trusted_project_dir(repo),
        outside_changes=outside,
    )
    if decision.tier == "L3":
        reasons = decision.reasons or ("改动命中核心或受保护路径，服务端强制升级为 L3 全量门禁",)
        return GatePlan(
            tier="L3",
            groups=ALL_GATE_GROUPS,
            run_plugin=True,
            reasons=reasons,
            changed_count=len(changed),
        )
    if not decision.recommended_groups:
        return _full_plan("受影响测试组为空，fail-closed 走 L3 全量门禁", changed_count=len(changed))
    return GatePlan(
        tier="L2",
        groups=decision.recommended_groups,
        run_plugin=False,
        reasons=decision.reasons,
        changed_count=len(changed),
    )


def _write_github_output(path: Path, plan: GatePlan) -> None:
    lines = [
        f"tier={plan.tier}",
        f"groups={json.dumps(list(plan.groups), ensure_ascii=False, separators=(',', ':'))}",
        f"groups_csv={','.join(plan.groups)}",
        f"run_plugin={'true' if plan.run_plugin else 'false'}",
    ]
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--base", default="")
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--requested-tier", default="L3")
    parser.add_argument("--github-output", default="")
    args = parser.parse_args(argv)
    plan = plan_ci_gate(
        Path(args.repo),
        str(args.base or "").strip(),
        str(args.candidate).strip(),
        requested_tier=str(args.requested_tier or "L3"),
    )
    if args.github_output:
        _write_github_output(Path(args.github_output), plan)
    print(json.dumps(plan.as_dict(), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
