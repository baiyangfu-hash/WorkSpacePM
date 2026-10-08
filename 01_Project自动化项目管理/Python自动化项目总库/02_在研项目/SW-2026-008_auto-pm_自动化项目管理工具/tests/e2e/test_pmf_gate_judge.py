"""Judge-side bad-evidence counter-examples: the gate-verdict judge refuses every kind of bad evidence a governed card could present (V06, judge half).

The judge (``tests/tools/verdict_check.py``) is what accepts or refuses a card's gate run. Here a self-contained verdict is built from real report files in a
temporary root; a positive control proves the judge accepts good evidence, and each bad variant (empty gate set, wrong card, wrong base, wrong run, a missing
report mapping, a report nobody bound, a missing or drifted report file, a failing gate, a wrong schema, an exception without reproduced evidence) must be refused
for its own, named reason. The command-line entry point is run for real in a subprocess, so the exit codes are proved too.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.tools import verdict_check

LABEL, BASE, RUN = "CARD-TEST-JUDGE V1.0", "a" * 40, "RUN-TEST-JUDGE-001"
GATES = [f"G{number}" for number in range(1, 10)]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Case:
    """A root with nine real report files and a good verdict binding them."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.verdict: dict[str, Any] = {"schema": verdict_check.SCHEMA, "card": LABEL, "base": BASE, "run_id": RUN, "gates": {}, "reports": {}, "exceptions": []}
        for gate in GATES:
            relative = f"reports/{gate}.txt"
            (root / "reports").mkdir(exist_ok=True)
            data = f"raw output of {gate}\n".encode()
            (root / relative).write_bytes(data)
            self.verdict["gates"][gate] = {"verdict": "PASS", "report": relative}
            self.verdict["reports"][relative] = _sha(data)

    def write(self) -> Path:
        path = self.root / "gate_verdict.json"
        path.write_text(json.dumps(self.verdict), encoding="utf-8")
        return path

    def check_file(self, path: Path, gates: list[str] | None = None) -> list[str]:
        try:
            return verdict_check.check(str(path), str(self.root), LABEL, BASE, RUN, GATES if gates is None else gates)
        except Exception as error:  # a crash is not a refusal: it must show up as a failed assertion
            raise AssertionError(f"the judge crashed instead of refusing: {error!r}") from error

    def check(self, label: str = LABEL, base: str = BASE, run: str = RUN, gates: list[str] | None = None) -> list[str]:
        path = self.write()
        try:
            return verdict_check.check(str(path), str(self.root), label, base, run, GATES if gates is None else gates)
        except Exception as error:  # a crash is not a refusal: it must show up as a failed assertion
            raise AssertionError(f"the judge crashed instead of refusing: {error!r}") from error

    def command(self, *tail: str) -> subprocess.CompletedProcess[str]:
        argv = [sys.executable, "-B", verdict_check.__file__, str(self.write()), str(self.root), LABEL, BASE, RUN, *tail]
        return subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, check=False)


@pytest.fixture
def case(tmp_path: Path) -> Case:
    return Case(tmp_path)


def _only(problems: list[str], phrase: str) -> None:
    """The judge refused, and for the named reason."""

    assert problems, "bad evidence was accepted"
    assert any(phrase in problem for problem in problems), problems


def test_j01_the_positive_control_is_accepted(case: Case) -> None:
    assert case.check() == []  # so a broken fixture cannot pass for a refusal below


def test_j02_an_empty_expected_gate_set_is_refused(case: Case) -> None:
    _only(case.check(gates=[]), "names no expected gate set")


def test_j03_a_verdict_for_another_card_is_refused(case: Case) -> None:
    _only(case.check(label="CARD-OTHER V1.0"), "another card, base or run")


def test_j04_a_verdict_for_another_base_is_refused(case: Case) -> None:
    _only(case.check(base="b" * 40), "another card, base or run")


def test_j05_a_verdict_for_another_run_is_refused(case: Case) -> None:
    _only(case.check(run="RUN-TEST-JUDGE-002"), "another card, base or run")


def test_j06_a_gate_that_is_missing_from_the_verdict_is_refused(case: Case) -> None:
    del case.verdict["gates"]["G9"]
    _only(case.check(), "gate set differs")


def test_j07_a_gate_that_names_a_report_nobody_bound_is_refused(case: Case) -> None:
    case.verdict["gates"]["G4"]["report"] = "reports/unbound.txt"
    (case.root / "reports" / "unbound.txt").write_text("not bound", encoding="utf-8")
    _only(case.check(), "not bound in reports")


def test_j08_a_gate_that_names_no_report_is_refused(case: Case) -> None:
    del case.verdict["gates"]["G2"]["report"]
    _only(case.check(), "names no report")


def test_j09_a_verdict_that_keeps_only_one_report_is_refused(case: Case) -> None:
    kept = case.verdict["gates"]["G5"]["report"]
    case.verdict["reports"] = {kept: case.verdict["reports"][kept]}  # nine PASS gates, one bound report
    _only(case.check(), "not bound in reports")


def test_j10_a_verdict_that_binds_no_report_is_refused(case: Case) -> None:
    case.verdict["reports"] = {}
    _only(case.check(), "binds no report")


def test_j11_a_bound_report_that_is_missing_on_disk_is_refused(case: Case) -> None:
    (case.root / "reports" / "G3.txt").unlink()
    _only(case.check(), "bound report does not exist")


def test_j12_a_bound_report_whose_bytes_drifted_is_refused(case: Case) -> None:
    (case.root / "reports" / "G6.txt").write_bytes(b"edited after the gate ran\n")
    _only(case.check(), "bound report hash differs")


def test_j13_a_failing_gate_is_refused(case: Case) -> None:
    case.verdict["gates"]["G7"]["verdict"] = "FAIL"
    _only(case.check(), "gate G7 is 'FAIL'")


def test_j14_a_baseline_exception_gate_is_accepted_but_only_with_reproduced_evidence(case: Case) -> None:
    case.verdict["gates"]["G2"]["verdict"] = "PASS_WITH_BASELINE_EXCEPTION"
    case.verdict["exceptions"] = [{"gate": "G2", "source_reproduced": True, "source_evidence": "reports/G2.txt"}]
    assert case.check() == []
    case.verdict["exceptions"] = [{"gate": "G2", "source_reproduced": False, "source_evidence": "reports/G2.txt"}]
    _only(case.check(), "exception without reproduced source evidence")
    case.verdict["exceptions"] = [{"gate": "G2", "source_reproduced": True, "source_evidence": ""}]
    _only(case.check(), "exception without reproduced source evidence")


def test_j15_a_verdict_with_another_schema_is_refused(case: Case) -> None:
    case.verdict["schema"] = "some-other-schema.v9"
    _only(case.check(), "unexpected verdict schema")


def test_j16_the_command_line_exits_zero_for_good_evidence_and_one_with_reasons_for_bad(case: Case) -> None:
    good = case.command(*GATES)
    assert good.returncode == 0 and "verdict OK" in good.stdout, good.stdout + good.stderr
    (case.root / "reports" / "G8.txt").write_bytes(b"drifted\n")
    bad = case.command(*GATES)
    assert bad.returncode == 1 and "VERDICT REFUSED" in bad.stdout and "bound report hash differs" in bad.stdout, bad.stdout + bad.stderr
    usage = subprocess.run([sys.executable, "-B", verdict_check.__file__, "only", "three", "args"], capture_output=True, text=True, timeout=120, check=False)
    assert usage.returncode == 2 and "usage" in usage.stdout


EXCEPTION = "PASS_WITH_BASELINE_EXCEPTION"


def _entry(**fields: Any) -> dict[str, Any]:
    return {"id": "E-1", "source_reproduced": True, "source_evidence": "reports/G2.txt", **fields}


def test_j17_a_baseline_exception_gate_without_an_exception_entry_is_refused(case: Case) -> None:
    case.verdict["gates"]["G2"]["verdict"] = EXCEPTION
    _only(case.check(), "no exception entry names it")


def test_j18_an_exception_entry_for_a_gate_that_is_not_an_exception_gate_is_refused(case: Case) -> None:
    case.verdict["gates"]["G2"]["verdict"] = EXCEPTION
    case.verdict["exceptions"] = [_entry(gate="G2"), _entry(gate="G99")]
    _only(case.check(), "not a baseline-exception gate")
    case.verdict["exceptions"] = [_entry(gate="G2"), _entry(gate="G3")]  # G3 is an ordinary PASS gate
    _only(case.check(), "not a baseline-exception gate")


def test_j19_an_exception_entry_whose_evidence_file_does_not_exist_is_refused(case: Case) -> None:
    case.verdict["gates"]["G2"]["verdict"] = EXCEPTION
    case.verdict["exceptions"] = [_entry(gate="G2", source_evidence="reports/never_written.txt")]
    _only(case.check(), "exception evidence file does not exist")


def test_j20_an_exception_entry_whose_evidence_is_not_bound_in_reports_is_refused(case: Case) -> None:
    case.verdict["gates"]["G2"]["verdict"] = EXCEPTION
    (case.root / "reports" / "reproduction.txt").write_text("the baseline failure, reproduced", encoding="utf-8")  # exists on disk, but nobody fingerprinted it
    case.verdict["exceptions"] = [_entry(gate="G2", source_evidence="reports/reproduction.txt")]
    _only(case.check(), "exception evidence is not bound in reports")
    case.verdict["reports"]["reports/reproduction.txt"] = _sha(b"the baseline failure, reproduced")
    assert case.check() == []


def test_j21_the_old_exception_format_without_a_gate_key_still_judges_as_before(case: Case) -> None:
    case.verdict["gates"]["G2"]["verdict"] = EXCEPTION
    old = {"id": "E-G1-1", "description": "3 baseline failures", "source_reproduced": True, "source_evidence": "reports/G2.txt (same command, earlier commit)"}
    case.verdict["exceptions"] = [old]
    assert case.check() == []  # an old entry cannot be attributed to a gate: it covers the exception gates as a group
    case.verdict["exceptions"] = [{**old, "source_evidence": ["reports/G2.txt", "reports/G3.txt"]}]
    assert case.check() == []
    case.verdict["exceptions"] = [{**old, "source_evidence": "reports/never_written.txt"}]
    _only(case.check(), "exception evidence file does not exist")
    case.verdict["gates"]["G2"]["verdict"] = "PASS"  # an old entry in a verdict that has no exception gate belongs to nothing
    case.verdict["exceptions"] = [old]
    _only(case.check(), "belongs to no gate")


def test_j22_an_exception_entry_that_names_no_gate_is_refused(case: Case) -> None:
    case.verdict["gates"]["G2"]["verdict"] = EXCEPTION
    case.verdict["exceptions"] = [_entry(gate="")]
    _only(case.check(), "names no gate")
    case.verdict["exceptions"] = [_entry(gate=None)]
    _only(case.check(), "names no gate")


@pytest.mark.parametrize("shape", ["all-nine-gates", "two-gates"])
def test_j23_gates_that_share_one_empty_report_are_refused(case: Case, shape: str) -> None:
    (case.root / "reports" / "shared.txt").write_bytes(b"  \n")
    case.verdict["reports"]["reports/shared.txt"] = _sha(b"  \n")
    for gate in GATES if shape == "all-nine-gates" else ["G1", "G2"]:
        case.verdict["gates"][gate]["report"] = "reports/shared.txt"
    _only(case.check(), "share one empty report")


def test_j24_a_shared_report_with_content_and_an_own_empty_report_are_accepted(case: Case) -> None:
    (case.root / "reports" / "shared.txt").write_bytes(b"one combined summary of two gates\n")
    case.verdict["reports"]["reports/shared.txt"] = _sha(b"one combined summary of two gates\n")
    case.verdict["gates"]["G1"]["report"] = case.verdict["gates"]["G2"]["report"] = "reports/shared.txt"
    (case.root / "reports" / "G9.txt").write_bytes(b"")  # a successful check that printed nothing, and the only gate that points at this file
    case.verdict["reports"]["reports/G9.txt"] = _sha(b"")
    assert case.check() == []


@pytest.mark.parametrize(
    ("shape", "phrase"),
    [
        ("gates-null-detail", "gates is not a mapping"),
        ("gates-list", "gates is not a mapping"),
        ("reports-list", "reports is not a mapping"),
        ("reports-non-string-hash", "reports is not a mapping"),
        ("exceptions-string", "exceptions is not a list"),
        ("exception-entry-not-an-object", "exceptions is not a list"),
    ],
)
def test_j25_a_malformed_verdict_is_refused_with_a_reason_and_never_crashes(case: Case, shape: str, phrase: str) -> None:
    if shape == "gates-null-detail":
        case.verdict["gates"]["G1"] = None
    elif shape == "gates-list":
        case.verdict["gates"] = ["G1", "G2"]
    elif shape == "reports-list":
        case.verdict["reports"] = ["reports/G1.txt"]
    elif shape == "reports-non-string-hash":
        case.verdict["reports"]["reports/G1.txt"] = 7
    elif shape == "exceptions-string":
        case.verdict["exceptions"] = "none"
    else:
        case.verdict["exceptions"] = ["not an object"]
    _only(case.check(), phrase)


def test_j26_a_verdict_file_that_is_not_an_object_or_not_json_or_missing_is_refused(case: Case) -> None:
    listed = case.root / "list.json"
    listed.write_text("[1, 2, 3]", encoding="utf-8")
    _only(case.check_file(listed), "verdict is not a JSON object")
    broken = case.root / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    _only(case.check_file(broken), "verdict file unreadable")
    _only(case.check_file(case.root / "no_such_verdict.json"), "verdict file unreadable")
    argv = [sys.executable, "-B", verdict_check.__file__, str(broken), str(case.root), LABEL, BASE, RUN, *GATES]
    out = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, check=False)
    assert out.returncode == 1 and "VERDICT REFUSED" in out.stdout and "Traceback" not in out.stderr, out.stdout + out.stderr  # exit 1 with reasons, no traceback
