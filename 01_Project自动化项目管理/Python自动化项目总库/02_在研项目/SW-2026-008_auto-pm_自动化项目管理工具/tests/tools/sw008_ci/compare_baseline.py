"""Compare the failures of one pytest run with an explicit known-baseline list.

usage: compare_baseline.py <pytest_log> <baseline_json> <pytest_exit_code>

Verdicts: PASS | PASS_KNOWN_BASELINE | FAIL.  Exit code 0 for the first two, 1 for FAIL.
A baseline item that unexpectedly passes is FAIL (the baseline is stale), never a silent pass.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

LINE = re.compile(r"^(FAILED|ERROR) (\S+)")
SUMMARY = re.compile(r"((?:\d+ [a-z]+(?:, )?)+) in [0-9.]+s")


def main(log_path: str, baseline_path: str, exit_code: str) -> int:
    text = Path(log_path).read_text(encoding="utf-8", errors="replace")
    baseline = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
    expected = set(baseline["ids"])
    actual = {m.group(2) for line in text.splitlines() if (m := LINE.match(line))}
    summary = next((m.group(1) for m in map(SUMMARY.search, reversed(text.splitlines())) if m), "no summary line")
    code = int(exit_code)

    problems: list[str] = []
    if code not in (0, 1):
        problems.append(f"pytest exit code {code} (expected 0 or 1): the run did not complete normally")
    if code == 1 and not actual:
        problems.append("pytest reported failures but none could be parsed from the log")
    new = sorted(actual - expected)
    stale = sorted(expected - actual)
    if new:
        problems.append(f"{len(new)} failure(s) not in the baseline")
    if stale:
        problems.append(f"{len(stale)} baseline item(s) did not fail: the baseline is stale")

    if problems:
        verdict = "FAIL"
    elif actual:
        verdict = "PASS_KNOWN_BASELINE"
    else:
        verdict = "PASS"

    lines = [f"verdict: {verdict}", f"pytest: {summary}", f"baseline: {len(expected)} item(s), failed now: {len(actual)}"]
    lines += [f"problem: {p}" for p in problems]
    lines += [f"  NEW      {i}" for i in new[:50]] + [f"  STALE    {i}" for i in stale[:50]]
    if verdict == "PASS_KNOWN_BASELINE":
        lines.append("note: the failures equal the recorded baseline; this is NOT an all-green result and does not replace the governed gates")
    report = "\n".join(lines)
    print(report)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as fh:
            fh.write("### Baseline comparison\n\n```\n" + report + "\n```\n")
    return 0 if verdict != "FAIL" else 1


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(*sys.argv[1:]))
