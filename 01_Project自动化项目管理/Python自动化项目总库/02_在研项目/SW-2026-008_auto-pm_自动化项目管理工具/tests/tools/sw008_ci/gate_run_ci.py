"""Run the official full gate on a GitHub runner, one group per job, and merge the pieces into one verdict.

usage: gate_run_ci.py list
       gate_run_ci.py run   --group G --out DIR [--jobs N] [--timeout-minutes M]
       gate_run_ci.py merge --in DIR [DIR ...] --out DIR [--worktree PATH]

``run`` calls ``GateRunService`` directly (the ``gate run`` command refuses to start in a clean checkout, because it wants a
verified runtime identity).  ``merge`` rebuilds ONE ``gate_summary.json`` out of the per-group ones and lets
``GateRunService.judge_dir`` recompute every verdict from the logs on disk, so the merged file is judged by the same code as a
local round.  Nothing here decides PASS by itself.  Run from the project folder (the one that holds ``tests/``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from auto_pm.application.core.gate_run_service import (  # noqa: E402
    GROUPS,
    SUMMARY_FILE,
    GateRunError,
    GateRunService,
    GateSummary,
    manifest_sha256,
)

INCOMPLETE = "组不齐全"  # the one reason a single-group summary always carries; merging removes it, judge_dir re-adds it if true
FAILED_LINE = re.compile(r"^(FAILED|ERROR) ")


def toplevel() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return Path(out.stdout.strip())


def cmd_run(args: argparse.Namespace) -> int:
    out = Path(args.out)
    try:
        summary = GateRunService().run(
            toplevel(),
            out,
            jobs=args.jobs,
            only=(args.group,),
            timeout_seconds=args.timeout_minutes * 60,
        )
    except GateRunError as error:
        print(f"门禁没能开跑: {error}")
        return 2
    result = summary.results.get(args.group)
    verdict = result.verdict if result else "NOT_RUN"
    print(f"组 {args.group}: {verdict} {result.why if result else ''}")
    # The tree-level reasons (dirty tree, moved commit) are judged at merge time; here only the group matters.
    return 0 if verdict == "PASS" else 1


def merge_summaries(
    parts: list[dict[str, Any]],
    *,
    expected_groups: list[str] | None = None,
) -> dict[str, Any]:
    """One summary dict from several single-group ones; refuses to mix commits or manifests."""
    if not parts:
        raise GateRunError("没有可合并的分片")
    first = parts[0]
    for key in ("commit", "commit_end", "manifest_sha256"):
        values = {str(p.get(key, "")) for p in parts}
        if len(values) != 1:
            raise GateRunError(f"分片的 {key} 不一致: {sorted(values)}；不是同一轮")
    merged = dict(first)
    results: dict[str, Any] = {}
    reasons: list[str] = []
    ignored: list[str] = []
    for part in parts:
        for name, entry in dict(part.get("results", {})).items():
            if name in results:
                raise GateRunError(f"组 {name} 在两个分片里都有")
            results[name] = entry
        reasons += [r for r in part.get("reasons", []) if INCOMPLETE not in str(r)]
        ignored += list(part.get("ignored_code", []))
        if part.get("git_dirty") is not False:
            merged["git_dirty"] = part.get("git_dirty")
        if part.get("git_dirty_end") is not False:
            merged["git_dirty_end"] = part.get("git_dirty_end")
    merged["results"] = results
    merged["reasons"] = list(dict.fromkeys(reasons))
    merged["ignored_code"] = list(dict.fromkeys(ignored))
    merged["groups_run"] = list(expected_groups) if expected_groups is not None else [g.name for g in GROUPS]
    return merged


def failure_lines(
    out: Path,
    summary: GateSummary,
    *,
    expected_groups: list[str] | None = None,
) -> list[str]:
    lines: list[str] = []
    for name, result in summary.results.items():
        if result.verdict == "PASS":
            continue
        lines.append(f"## {name}: {result.verdict} (退出码 {result.exit})  {result.why}")
        log = out / f"{name}.txt"
        if log.is_file():
            for raw in log.read_text(encoding="utf-8", errors="replace").splitlines():
                if FAILED_LINE.match(raw):
                    lines.append(f"- {raw.strip()}")
    expected = set(expected_groups) if expected_groups is not None else {g.name for g in GROUPS}
    for name in sorted(expected - set(summary.results)):
        lines.append(f"## {name}: 没有产出（这一组的任务没跑完或没上传）")
    return lines


def _resolve_expected_groups(tier: str, raw_expected: str) -> list[str]:
    official = [g.name for g in GROUPS]
    if tier == "L3":
        return official
    parsed = {item.strip() for item in raw_expected.split(",") if item.strip()}
    if not parsed:
        raise GateRunError("L2 门禁缺少 --expected-groups")
    unknown = sorted(parsed - set(official))
    if unknown:
        raise GateRunError(f"L2 包含未登记测试组: {', '.join(unknown)}")
    return [name for name in official if name in parsed]


def cmd_merge(args: argparse.Namespace) -> int:
    tier = str(getattr(args, "tier", "L3") or "L3").strip().upper()
    if tier not in {"L2", "L3"}:
        print(f"非法门禁档次: {tier}")
        return 2
    raw_expected = str(getattr(args, "expected_groups", "") or "").strip()
    try:
        expected_groups = _resolve_expected_groups(tier, raw_expected)
    except GateRunError as error:
        print(f"参数无效: {error}")
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    parts: list[dict[str, Any]] = []
    for directory in map(Path, args.inputs):
        record = directory / SUMMARY_FILE
        if not record.is_file():
            print(f"缺 {record}（该组任务没产出记录）")
            continue
        parts.append(json.loads(record.read_text(encoding="utf-8")))
        for pattern in ("*.txt", "*.exit"):
            for item in directory.glob(pattern):
                shutil.copy2(item, out / item.name)
    try:
        merged = merge_summaries(parts, expected_groups=expected_groups)
    except GateRunError as error:
        print(f"合并被拒: {error}")
        return 2
    (out / SUMMARY_FILE).write_text(
        json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
    worktree = Path(args.worktree) if args.worktree else None
    judged = GateRunService().judge_dir(out, worktree=worktree)
    plugin_result = str(getattr(args, "plugin_result", "") or "").strip()
    if tier == "L2":
        judged.complete = False
        judged.reasons = [r for r in judged.reasons if r != INCOMPLETE]
        if judged.manifest_sha256 != manifest_sha256():
            judged.reasons.append("manifest_sha256 与官方分组清单不一致")
        missing = [g for g in expected_groups if g not in judged.results]
        if missing:
            judged.reasons.append(f"L2 缺失预期测试组: {', '.join(missing)}")
        unexpected = sorted(set(judged.results) - set(expected_groups))
        if unexpected:
            judged.reasons.append(f"L2 出现非预期测试组: {', '.join(unexpected)}")
        if plugin_result and plugin_result not in {"success", "skipped"}:
            judged.reasons.append(f"Siemens LSP 插件检查：{plugin_result}")
        judged.reasons = list(dict.fromkeys(judged.reasons))
        all_pass = bool(judged.results) and all(r.verdict == "PASS" for r in judged.results.values())
        judged.verdict = "PASS" if (all_pass and not judged.reasons and not missing) else "FAIL"
    else:
        if plugin_result and plugin_result != "success":
            judged.verdict = "FAIL"
            judged.reasons.append(f"Siemens LSP 插件检查：{plugin_result}")
    final = json.loads((out / SUMMARY_FILE).read_text(encoding="utf-8"))
    final.update(
        {
            "tier": tier,
            "expected_groups": expected_groups,
            "plugin_result": plugin_result,
            "verdict": judged.verdict,
            "complete": judged.complete,
            "reasons": judged.reasons,
            "results": {
                n: {**dict(merged["results"][n]), "verdict": r.verdict, "why": r.why}
                for n, r in judged.results.items()
            },
        }
    )
    text = json.dumps(final, ensure_ascii=False, indent=2)
    (out / SUMMARY_FILE).write_text(text, encoding="utf-8", newline="\n")
    digest = hashlib.sha256((out / SUMMARY_FILE).read_bytes()).hexdigest()
    failures = failure_lines(out, judged, expected_groups=expected_groups)
    heading = f"# L2 分组门禁判决: {judged.verdict}" if tier == "L2" else f"# 全量门禁判决: {judged.verdict}"
    body = [
        heading,
        f"- 档次: {tier}",
        f"- 提交号: {judged.commit}",
        f"- gate_summary.json SHA-256: {digest}",
    ]
    body += [f"- 原因: {r}" for r in judged.reasons]
    body += ["", *failures] if failures else []
    (out / "failures.md").write_text("\n".join(body) + "\n", encoding="utf-8", newline="\n")
    step = os.environ.get("GITHUB_STEP_SUMMARY")
    if step:
        with open(step, "a", encoding="utf-8") as handle:
            handle.write("\n".join(body) + "\n")
    print(f"判决 {judged.verdict}  sha256={digest}")
    return 0 if judged.verdict == "PASS" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    run = sub.add_parser("run")
    run.add_argument("--group", required=True)
    run.add_argument("--out", required=True)
    run.add_argument("--jobs", type=int, default=4)
    run.add_argument("--timeout-minutes", type=int, default=90)
    merge = sub.add_parser("merge")
    merge.add_argument("--in", dest="inputs", nargs="+", required=True)
    merge.add_argument("--out", required=True)
    merge.add_argument("--worktree", default="")
    merge.add_argument("--plugin-result", default="")
    merge.add_argument("--tier", default="L3", choices=("L2", "L3"))
    merge.add_argument("--expected-groups", default="")
    args = parser.parse_args(argv)
    if args.cmd == "list":
        print(json.dumps([g.name for g in GROUPS]))
        return 0
    return cmd_run(args) if args.cmd == "run" else cmd_merge(args)


if __name__ == "__main__":
    sys.exit(main())
