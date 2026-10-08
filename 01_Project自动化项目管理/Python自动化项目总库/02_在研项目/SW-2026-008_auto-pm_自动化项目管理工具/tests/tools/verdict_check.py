"""Strict check of a card gate verdict: the judge that every governed card's gate run is accepted or refused by.

This is the version-controlled home of the judge (technical debt TD-SW008-096). It judges exactly as the earlier copy under ``.auto-pm/reports/m2-tools`` did:
beyond the older inline check it requires that every gate names a report that is bound in ``reports``, that the file exists and that its SHA-256 matches; a verdict
that keeps only some of the reports, or whose gate points at a report nobody bound, is refused. ``tests/e2e/test_pmf_gate_judge.py`` proves each refusal.

Usage: python -B verdict_check.py VERDICT_JSON ROOT LABEL BASE RUN GATE [GATE ...]     (exit 0 = accepted, 1 = refused, reasons on stdout)
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Any

SCHEMA = "m2-card-gate-verdict.v1"
PASSING = ("PASS", "PASS_WITH_BASELINE_EXCEPTION")


def check(verdict_path: str, root: str, label: str, base: str, run: str, expected_gates: list[str]) -> list[str]:
    problems: list[str] = []
    with open(verdict_path, encoding="utf-8") as stream:
        verdict: dict[str, Any] = json.load(stream)
    if verdict.get("schema") != SCHEMA:
        problems.append(f"unexpected verdict schema: {verdict.get('schema')!r}")
    if (verdict.get("card"), verdict.get("base"), verdict.get("run_id")) != (label, base, run):
        problems.append("the verdict names another card, base or run")
    if not expected_gates:
        problems.append("the caller names no expected gate set")
    gates: dict[str, Any] = verdict.get("gates") or {}
    reports: dict[str, str] = verdict.get("reports") or {}
    if sorted(gates) != sorted(expected_gates):
        problems.append(f"gate set differs from the expected one: {sorted(gates)}")
    if not reports:
        problems.append("the verdict binds no report")
    for name, detail in sorted(gates.items()):
        if detail.get("verdict") not in PASSING:
            problems.append(f"gate {name} is {detail.get('verdict')!r}")
        report = detail.get("report")
        if not report:
            problems.append(f"gate {name} names no report")
        elif report not in reports:
            problems.append(f"gate {name} names report {report!r}, which is not bound in reports")
    for relative, expected in sorted(reports.items()):
        path = os.path.join(root, relative)
        if not os.path.isfile(path):
            problems.append(f"bound report does not exist: {relative}")
        else:
            with open(path, "rb") as stream_bytes:
                if hashlib.sha256(stream_bytes.read()).hexdigest() != expected:
                    problems.append(f"bound report hash differs: {relative}")
    for exception in verdict.get("exceptions", []):
        if exception.get("source_reproduced") is not True or not exception.get("source_evidence"):
            problems.append(f"exception without reproduced source evidence: {exception}")
    return problems


def main(argv: list[str]) -> int:
    if len(argv) < 6:
        print("usage: verdict_check.py VERDICT_JSON ROOT LABEL BASE RUN GATE [GATE ...]")
        return 2
    verdict_path, root, label, base, run, *gates = argv[1:]
    problems = check(verdict_path, root, label, base, run, gates)
    if problems:
        print("VERDICT REFUSED:")
        for problem in problems:
            print(" -", problem)
        return 1
    print("verdict OK", dict.fromkeys(gates, "PASS"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
