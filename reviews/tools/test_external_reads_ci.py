"""Cockpit tests that read files outside their project run on every PR (D-200 step 2; #831 turned main red without it).

``sw008-ci`` only starts for changes under the cockpit project, so a test that reads AGENTS.md, roles/ or .trae/ was not run
when only that file changed.  ``sw008-external-reads.yml`` runs every test marked ``external_reads`` on every PR.  These
checks keep it that way: no path filter (nobody has to keep a list of the files those tests read; a new outside read is
forced into the marker by the cockpit's ``test_external_reads_marked``), the right marker in the right directory, a red
test turns the check red, and ci-aggregate expects it whatever the PR touches.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ci_aggregate as agg  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "sw008-external-reads.yml"
PROJECT = next(REPO.glob("01_Project*/Python*/02_在研项目/SW-2026-008*"))


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_it_runs_on_every_pull_request_and_main_push_without_a_path_filter() -> None:
    trigger = agg.parse_trigger(WORKFLOW.name, _text())
    assert trigger is not None and trigger.always
    code = "\n".join(line for line in _text().splitlines() if not line.lstrip().startswith("#"))
    triggers_block = code.split("\njobs:", 1)[0]
    assert "paths" not in triggers_block
    assert "push:" in triggers_block and "pull_request:" in triggers_block


@pytest.mark.parametrize(
    "path",
    [
        "roles/product-pm/SKILL.md",
        ".trae/skills/cockpit-entry/SKILL.md",
        "AGENTS.md",
        "CLAUDE.md",
        "00_Obsidian_Base全局规范文件仓库/spec_registry.json",
        "reviews/tools/audit_pr.py",
        "0100_PLC自动化/.trae/rules/plc-rules.md",
        "README.md",
    ],
)
def test_ci_aggregate_expects_it_for_any_change(path: str) -> None:
    assert WORKFLOW.name in agg.expected_workflows(agg.load_triggers(WORKFLOW.parent), [path])


def test_it_runs_the_marked_tests_of_the_cockpit_project() -> None:
    text = _text()
    assert f'PROJ: "{PROJECT.relative_to(REPO).as_posix()}"' in text
    assert "working-directory: ${{ env.PROJ }}" in text
    assert "-m external_reads tests" in text
    assert (PROJECT / "tests" / "tools" / "sw008_ci" / "external_reads_manifest.txt").is_file()
    assert "external_reads:" in (PROJECT / "pyproject.toml").read_text(encoding="utf-8")


def test_a_red_test_turns_the_check_red() -> None:
    text = _text()
    for loophole in ("set +e", "|| true", "continue-on-error", "--exitfirst=0"):
        assert loophole not in text, loophole
