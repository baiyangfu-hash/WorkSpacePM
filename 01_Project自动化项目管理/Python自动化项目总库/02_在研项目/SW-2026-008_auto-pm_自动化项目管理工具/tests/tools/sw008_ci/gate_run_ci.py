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


def merge_summaries(parts: list[dict[str, Any]]) -> dict[str, Any]:
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
    merged["groups_run"] = [g.name for g in GROUPS]
    return merged


def failure_lines(out: Path, summary: GateSummary) -> list[str]:
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
    for name in sorted({g.name for g in GROUPS} - set(summary.results)):
        lines.append(f"## {name}: 没有产出（这一组的任务没跑完或没上传）")
    return lines


def cmd_merge(args: argparse.Namespace) -> int:
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
        merged = merge_summaries(parts)
    except GateRunError as error:
        print(f"合并被拒: {error}")
        return 2
    (out / SUMMARY_FILE).write_text(
        json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
    worktree = Path(args.worktree) if args.worktree else None
    judged = GateRunService().judge_dir(out, worktree=worktree)
    final = json.loads((out / SUMMARY_FILE).read_text(encoding="utf-8"))
    final.update(
        {
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
    failures = failure_lines(out, judged)
    body = [
        f"# 全量门禁判决: {judged.verdict}",
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
    args = parser.parse_args(argv)
    if args.cmd == "list":
        print(json.dumps([g.name for g in GROUPS]))
        return 0
    return cmd_run(args) if args.cmd == "run" else cmd_merge(args)


if __name__ == "__main__":
    sys.exit(main())
