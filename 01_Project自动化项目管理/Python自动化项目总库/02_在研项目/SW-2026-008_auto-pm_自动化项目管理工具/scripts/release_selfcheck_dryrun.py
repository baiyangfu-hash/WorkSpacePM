"""D-146 card 6a: read-only dry run of the release self-check set against a real control root.

Runs every name in ``REQUIRED_SELF_CHECKS`` (built by ``release_wiring.build_self_checks``) against the real control root and prints
one pass/fail line with the reason per check, then writes the summary as JSON.  It switches no release, writes no ledger row and
touches no pointer: ``ledger reconcile`` runs without ``--fix``, the event-chain drill only works on a scratch copy of the ledger, and
the pre-commit hook dry run follows its own rule.

Exit code: 0 all passed, 1 at least one failed, 2 bad arguments or environment.

Example (Git bash, from a temporary checkout of main; use absolute paths)::

    python scripts/release_selfcheck_dryrun.py --control-root <root> --card-file <card.md> \\
        --drill-script <root>/.auto-pm/reports/m3-d06/drill.py \\
        --release-id 1.3.3-57aaa68 --old 1.3.3-669af74 --older 1.3.3-69b7ed6
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
IDENTITY_PROJECT = "SW-2026-008"


def _parse(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="只读空跑 release 自检集（不切发布、不写账本）")
    parser.add_argument("--control-root", required=True)
    parser.add_argument("--card-file", required=True)
    parser.add_argument("--drill-script", required=True)
    parser.add_argument("--release-id", required=True, help="当前生效版本，如 1.3.3-57aaa68")
    parser.add_argument("--old", required=True, help="上一版（previous）")
    parser.add_argument("--older", required=True, help="再上一版")
    parser.add_argument("--out", default="", help="汇总 JSON 路径；缺省写到当前目录 selfcheck_dryrun_<UTC时间>.json")
    return parser.parse_args(list(argv) if argv is not None else None)


def fresh_identity(run_process: Any, python: str = sys.executable) -> Any:
    """The runtime identity as a fresh process sees it (``pm resume --json``): four fields plus conflict codes; ``{}`` if unreadable."""

    def identity(root: Path) -> dict[str, Any]:
        code, output = run_process([python, "-B", str(Path(root) / "main.py"), "pm", "resume", IDENTITY_PROJECT, "--json"], Path(root))
        if code != 0 or "{" not in output:
            return {}
        try:
            data, _end = json.JSONDecoder().raw_decode(output[output.index("{"):])
        except ValueError:
            return {}
        context = data.get("context") or {}
        found: dict[str, Any] = {key: context.get(key) for key in ("configured_release_id", "effective_release_id", "runtime_load_path", "runtime_fallback_reason")}
        found["conflicts"] = [c.get("code") if isinstance(c, dict) else c for c in (data.get("conflicts") or [])]
        return found

    return identity


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse(argv)
    root = Path(args.control_root).resolve()
    if not (root / "main.py").is_file():
        print(f"[错误] 控制根下没有 main.py：{root}")
        return 2
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from auto_pm.application.core import release_wiring as rw
    from auto_pm.application.core.release_deploy import REQUIRED_SELF_CHECKS, run_self_checks

    try:
        checks = rw.build_self_checks(
            root=root, release_id=args.release_id, old_release=args.old, older_release=args.older,
            run=rw.cockpit_runner(root), identity=fresh_identity(rw.run_process),
            card_file=Path(args.card_file).resolve(), drill_script=Path(args.drill_script).resolve(),
        )
    except rw.WiringError as error:
        print(f"[错误] {error}")
        return 2

    print(f"控制根={root}\n版本 新={args.release_id} 旧={args.old} 再旧={args.older}\n共 {len(REQUIRED_SELF_CHECKS)} 项，开始（只读）…\n")
    results = run_self_checks(checks)
    rows = []
    for name in REQUIRED_SELF_CHECKS:
        ok, reason = results[name]
        rows.append({"check": name, "passed": bool(ok), "reason": reason})
        print(f"[{'通过' if ok else '失败'}] {name}  {reason}")
    failed = [row["check"] for row in rows if not row["passed"]]
    now = datetime.now(UTC)
    summary = {
        "when": now.isoformat(), "control_root": str(root), "release_id": args.release_id, "old": args.old, "older": args.older,
        "total": len(rows), "failed": failed, "all_passed": not failed, "results": rows,
    }
    out = Path(args.out) if args.out else Path.cwd() / f"selfcheck_dryrun_{now:%Y%m%dT%H%M%SZ}.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n汇总：{len(rows) - len(failed)}/{len(rows)} 通过；失败={failed or '无'}；JSON={out}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
