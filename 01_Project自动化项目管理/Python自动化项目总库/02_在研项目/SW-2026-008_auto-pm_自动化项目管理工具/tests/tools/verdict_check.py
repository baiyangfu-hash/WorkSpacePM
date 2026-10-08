"""Strict check of a card gate verdict: the judge that every governed card's gate run is accepted or refused by.

Version-controlled home of the judge (technical debt TD-SW008-096). ``tests/e2e/test_pmf_gate_judge.py`` proves each refusal. Beyond the original check (V06B) this version
(V06C, technical debt TD-SW008-099) also requires that

* every gate whose verdict is PASS_WITH_BASELINE_EXCEPTION is covered by an exception entry, and every exception entry belongs to such a gate; an entry that names its gate
  explicitly (the new format) covers exactly that gate and must have each evidence file bound in ``reports`` so its bytes are fingerprinted; an entry without a ``gate`` key
  (the old format used by every earlier verdict, whose ``E-G<n>-<m>`` ids do not identify a gate) cannot be attributed to one, so it covers the verdict's exception gates as a group;
* an exception entry carries a reproduced flag and existing evidence files;
* nine gates cannot hide behind one shared empty report;
* a malformed verdict file is refused with reasons instead of raising.

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
EXCEPTION_STATUS = "PASS_WITH_BASELINE_EXCEPTION"


def _load(verdict_path: str) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        with open(verdict_path, encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, ValueError) as error:
        return None, [f"verdict file unreadable: {error}"]
    if not isinstance(data, dict):
        return None, ["verdict is not a JSON object"]
    return data, []


def _exception_problems(verdict: dict[str, Any], gates: dict[str, Any], reports: dict[str, str], root: str) -> list[str]:
    problems: list[str] = []
    exceptions = verdict.get("exceptions", [])
    if not isinstance(exceptions, list) or not all(isinstance(entry, dict) for entry in exceptions):
        problems.append("exceptions is not a list of objects")
        exceptions = []
    exception_gates = sorted(name for name, detail in gates.items() if detail.get("verdict") == EXCEPTION_STATUS)
    covered: set[str] = set()
    unattributed = 0
    for entry in exceptions:
        if "gate" in entry:
            gate = entry["gate"]
            if not isinstance(gate, str) or not gate:
                problems.append(f"exception names no gate: {entry}")
            elif gates.get(gate, {}).get("verdict") != EXCEPTION_STATUS:
                problems.append(f"exception {entry.get('id')!r} belongs to gate {gate!r}, which is not a baseline-exception gate")
            else:
                covered.add(gate)
        else:
            unattributed += 1
            if not exception_gates:
                problems.append(f"exception {entry.get('id')!r} belongs to no gate: the verdict has no baseline-exception gate")
        evidence = entry.get("source_evidence")
        listed = evidence if isinstance(evidence, list) else [evidence]
        paths = [item for item in listed if isinstance(item, str) and item.strip()]
        if entry.get("source_reproduced") is not True or not paths or len(paths) != len(listed):
            problems.append(f"exception without reproduced source evidence: {entry}")
            continue
        for item in paths:
            reference = item.split()[0]
            if not os.path.isfile(os.path.join(root, reference)):
                problems.append(f"exception evidence file does not exist: {reference}")
            elif "gate" in entry and reference not in reports:
                problems.append(f"exception evidence is not bound in reports: {reference}")
    for name in exception_gates:
        if name not in covered and not unattributed:
            problems.append(f"gate {name} is a baseline exception but no exception entry names it")
    return problems


def check(verdict_path: str, root: str, label: str, base: str, run: str, expected_gates: list[str]) -> list[str]:
    verdict, unreadable = _load(verdict_path)
    if verdict is None:
        return unreadable
    problems: list[str] = []
    if verdict.get("schema") != SCHEMA:
        problems.append(f"unexpected verdict schema: {verdict.get('schema')!r}")
    if (verdict.get("card"), verdict.get("base"), verdict.get("run_id")) != (label, base, run):
        problems.append("the verdict names another card, base or run")
    if not expected_gates:
        problems.append("the caller names no expected gate set")
    gates: dict[str, Any] = verdict.get("gates") or {}
    reports: dict[str, str] = verdict.get("reports") or {}
    if not isinstance(gates, dict) or not all(isinstance(detail, dict) for detail in gates.values()):
        problems.append("gates is not a mapping of gate objects")
        gates = {}
    if not isinstance(reports, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in reports.items()):
        problems.append("reports is not a mapping of paths to hashes")
        reports = {}
    if sorted(gates) != sorted(expected_gates):
        problems.append(f"gate set differs from the expected one: {sorted(gates)}")
    if not reports:
        problems.append("the verdict binds no report")
    named: dict[str, list[str]] = {}
    for name, detail in sorted(gates.items()):
        if detail.get("verdict") not in PASSING:
            problems.append(f"gate {name} is {detail.get('verdict')!r}")
        report = detail.get("report")
        if not report:
            problems.append(f"gate {name} names no report")
        elif report not in reports:
            problems.append(f"gate {name} names report {report!r}, which is not bound in reports")
        else:
            named.setdefault(report, []).append(name)
    for relative, expected in sorted(reports.items()):
        path = os.path.join(root, relative)
        if not os.path.isfile(path):
            problems.append(f"bound report does not exist: {relative}")
        else:
            with open(path, "rb") as stream_bytes:
                content = stream_bytes.read()
            if hashlib.sha256(content).hexdigest() != expected:
                problems.append(f"bound report hash differs: {relative}")
            if len(named.get(relative, [])) > 1 and not content.strip():
                problems.append(f"gates {named[relative]} share one empty report: {relative}")
    problems += _exception_problems(verdict, gates, reports, root)
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
