"""The machine tier classifier (M2-TOOL-TIER): proofs that it takes the highest-risk path, refuses what it cannot classify, never lowers a declared tier and
agrees with the tiers of the cards that were already approved.

The rule document says (sections 1, 3, 4 and 11) that the tier comes from the real change and not from the executor, that an unknown path is reviewed as core, that a
conftest or other cross-group test infrastructure cannot be treated as an ordinary test, and that a tier tool may only recommend: keep or raise, never lower.
``tests/tools/tier_classifier.py`` and its versioned rules ``tests/tools/tier_core_list.json`` implement that. Every test names a refusal or a decision and asserts it.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from tests.git_support import git_do
from tests.tools import tier_classifier as tc

PROJECT = Path(__file__).resolve().parents[2]
PREFIX = "01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/"
# Paths of the cards that were approved and executed (read from their commits); the tier the card itself declared is the expectation.
APPROVED_CARDS: list[tuple[str, str, list[str]]] = [
    (
        "F02 query versions (core)",
        "core",
        [
            "auto_pm/api.py",
            "auto_pm/application/core/continuity_query_service.py",
            "auto_pm/application/core/pm_cockpit_service.py",
            "auto_pm/application/core/pm_facade_service.py",
            "auto_pm/contracts/continuity_query.py",
            "auto_pm/contracts/continuity_resume.py",
            "auto_pm/ui/cli/pm.py",
            "tests/cli/test_pm_orient.py",
            "tests/core/test_continuity_query_service.py",
            "tests/core/test_pm_cockpit_capability_notice.py",
        ],
    ),
    (
        "F01-1 closing seal (product)",
        "product",
        ["auto_pm/ui/qml/boss_main.qml", "auto_pm/ui/qml/bridges/pm_cockpit_bridge.py", "tests/qml/test_boss_cockpit_view.py", "tests/qml/test_pm_cockpit_closing_guards.py"],
    ),
    ("V06B judge under version control (tests)", "tests", ["tests/e2e/test_pmf_gate_judge.py", "tests/tools/__init__.py", "tests/tools/verdict_check.py"]),
    ("V06C judge tightening (tests)", "tests", ["tests/e2e/test_pmf_gate_judge.py", "tests/tools/verdict_check.py"]),
    ("V06D hook proofs (tests)", "tests", ["tests/e2e/test_pmf_gate_failures.py"]),
    ("V05-C real window (tests)", "tests", ["tests/e2e/test_pmf_gui.py"]),
    ("TD7 ledger (docs)", "docs", ["04_监控/02_整改项/活动技术债台账.md"]),
    ("RULE document (docs)", "docs", ["02_规划/M2_门禁分档与单卡规模规则_PM.md"]),
    ("WBS revision (docs)", "docs", ["SYS-2026-001_WorkspaceGovernance/01_项目文档/39_PM-Flow_恢复与可用化总方案_WBS_PM.md"]),
    ("settlement of expired Runs (core)", "core", [".auto-pm/continuity.db"]),
]
# Top-level entries of the tracked tree that no rule names today: they are reviewed as core. A new one appearing must be a decision, so this list is exact.
KNOWN_UNKNOWN_TOP_LEVEL: set[str] = {"archive"}


@pytest.fixture(scope="module")
def rules() -> tc.Rules:
    return tc.load_rules()


def _tier(path: str, rules: tc.Rules) -> str:
    return tc.classify_path(path, rules).tier


def test_a_contract_file_is_core(rules: tc.Rules) -> None:
    verdict = tc.classify_path("auto_pm/contracts/continuity_query.py", rules)
    assert verdict.tier == "core" and "CORE-CONTRACTS" in verdict.rule_ids


def test_a_cockpit_qml_file_is_product(rules: tc.Rules) -> None:
    assert _tier("auto_pm/ui/qml/boss_main.qml", rules) == "product"


def test_a_plain_test_file_is_tests(rules: tc.Rules) -> None:
    assert _tier("tests/core/test_continuity_query_service.py", rules) == "tests"


def test_a_ledger_and_a_card_are_docs(rules: tc.Rules) -> None:
    assert _tier("04_监控/02_整改项/活动技术债台账.md", rules) == "docs"
    assert _tier("02_规划/076_M2-GOV-TD7_技术债台账同步实施卡_PM.md", rules) == "docs"


def test_an_unknown_path_is_reviewed_as_core_and_listed(rules: tc.Rules) -> None:
    verdict = tc.classify_path("mystery/new_tool.bin", rules)
    assert verdict.tier == "core" and verdict.rule_ids == ("UNKNOWN_PATH",)
    result = tc.classify_paths(["tests/core/test_x.py", "mystery/new_tool.bin"], rules)
    assert result.tier == "core" and result.unknown == ("mystery/new_tool.bin",)


def test_the_highest_tier_of_the_change_wins(rules: tc.Rules) -> None:
    assert tc.classify_paths(["02_规划/a.md", "tests/core/test_a.py", "auto_pm/ui/cli/pm.py"], rules).tier == "product"
    assert tc.classify_paths(["02_规划/a.md", "tests/core/test_a.py", "auto_pm/infrastructure/continuity_store.py"], rules).tier == "core"
    assert tc.classify_paths(["02_规划/a.md", "tests/core/test_a.py"], rules).tier == "tests"
    assert tc.classify_paths(["02_规划/a.md", "05_收尾/b.md"], rules).tier == "docs"


@pytest.mark.parametrize("path", ["tests/qml/conftest.py", "tests/conftest.py", "tests/vartable/conftest.py", "tests/fakes/clock.py", "tests/__init__.py"])
def test_cross_group_test_infrastructure_is_not_an_ordinary_test(rules: tc.Rules, path: str) -> None:
    verdict = tc.classify_path(path, rules)
    assert verdict.tier == "product", (path, verdict)


@pytest.mark.parametrize("path", ["02_规划/helper.py", "04_监控/02_整改项/export.json", "05_收尾/run.sh", "03_执行/settings.toml", "学习资料/query.sql"])
def test_a_behaviour_suffix_inside_a_docs_folder_is_not_documentation(rules: tc.Rules, path: str) -> None:
    verdict = tc.classify_path(path, rules)
    assert verdict.tier == "product" and "BEHAVIOR_SUFFIX_IN_DOCS" in verdict.rule_ids, (path, verdict)


@pytest.mark.parametrize(
    "path",
    [
        "04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-396.md",
        "PM_SESSION_SW-2026-008.md",
        "SYS-2026-001_WorkspaceGovernance/workspace_registry.json",
        "SYS-2026-001_WorkspaceGovernance/PM_SESSION_SYS-2026-001.md",
    ],
)
def test_runtime_written_documents_are_not_plain_documentation(rules: tc.Rules, path: str) -> None:
    assert _tier(path, rules) == "product", path


def test_matching_ignores_case_and_path_separators(rules: tc.Rules) -> None:
    # each example would be an UNKNOWN path (core) if the case or the separators were not normalised, so the expected tier below is only reachable by matching a rule
    assert _tier("TESTS/Core/test_x.py", rules) == "tests"
    assert _tier("AUTO_PM\\UI\\qml\\Boss_Main.qml", rules) == "product"
    assert _tier("./02_规划//Card.MD", rules) == "docs"
    assert tc.classify_path("Tests/Qml/Conftest.PY", rules).tier == "product"


def test_the_project_prefix_is_removed_before_matching(rules: tc.Rules) -> None:
    assert _tier(PREFIX + "tests/e2e/test_x.py", rules) == "tests"  # an unstripped prefix would be an unknown path, which is core
    assert _tier(PREFIX + "02_规划/card.md", rules) == "docs"
    assert tc.normalize_path(PREFIX + "tests/e2e/test_x.py", rules.project_prefix) == "tests/e2e/test_x.py"


@pytest.mark.parametrize("bad", ["", "   ", "/etc/passwd", "C:/Windows/x.py", "C:\\Windows\\x.py", "tests/../auto_pm/x.py", "../outside.py", "a\x00b"])
def test_paths_that_are_not_repository_relative_are_refused(rules: tc.Rules, bad: str) -> None:
    with pytest.raises(tc.TierError):
        tc.classify_path(bad, rules)


def test_an_empty_change_set_is_refused_instead_of_being_called_docs(rules: tc.Rules) -> None:
    with pytest.raises(tc.TierError):
        tc.classify_paths([], rules)


def test_the_same_path_written_twice_is_counted_once(rules: tc.Rules) -> None:
    result = tc.classify_paths(["tests/core/test_a.py", "tests\\core\\test_a.py", "TESTS/core/test_a.py"], rules)
    assert len(result.verdicts) == 1


@pytest.mark.parametrize(
    ("declared", "computed_paths", "problems"),
    [
        ("core", ["auto_pm/contracts/mission.py"], 0),
        ("core", ["tests/core/test_a.py"], 0),
        ("product", ["auto_pm/contracts/mission.py"], 1),
        ("tests", ["auto_pm/ui/cli/pm.py"], 1),
        ("docs", ["tests/core/test_a.py"], 1),
        ("tests", ["tests/qml/conftest.py"], 1),
        ("docs", ["mystery/x.bin"], 1),
        ("product", ["auto_pm/ui/cli/pm.py"], 0),
        ("docs", ["02_规划/a.md"], 0),
    ],
)
def test_a_declared_tier_may_equal_or_exceed_the_computed_tier_but_never_undercut_it(
    rules: tc.Rules, declared: str, computed_paths: list[str], problems: int
) -> None:
    result = tc.classify_paths(computed_paths, rules)
    assert len(tc.check_declared(declared, result)) == problems, (declared, result.tier)


def test_a_declared_tier_must_be_one_of_the_four_tiers(rules: tc.Rules) -> None:
    result = tc.classify_paths(["tests/core/test_a.py"], rules)
    assert tc.check_declared("optional", result) and tc.check_declared("", result)


@pytest.mark.parametrize(("name", "expected", "paths"), APPROVED_CARDS, ids=[card[0] for card in APPROVED_CARDS])
def test_the_classifier_agrees_with_the_tier_of_every_approved_card(rules: tc.Rules, name: str, expected: str, paths: list[str]) -> None:
    result = tc.classify_paths(paths, rules)
    assert result.tier == expected, (name, result.tier, [(v.normalized, v.tier) for v in result.verdicts])
    assert not result.unknown, (name, result.unknown)


def _git(repo: Path, *args: str) -> None:
    git_do(repo, *args, config=['user.name=t', 'user.email=t@example.invalid', 'core.autocrlf=false'])


def _repo_with_changes(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "auto_pm" / "contracts").mkdir(parents=True)
    (repo / "02_规划").mkdir()
    for name, text in (("tests/test_keep.py", "one\n"), ("tests/test_old_name.py", "two\n"), ("auto_pm/contracts/gone.py", "three\n"), ("02_规划/note.md", "four\n")):
        (repo / name).write_text(text, encoding="utf-8", newline="\n")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    (repo / "tests/test_keep.py").write_text("changed\n", encoding="utf-8", newline="\n")
    _git(repo, "mv", "tests/test_old_name.py", "tests/test_new_name.py")
    _git(repo, "rm", "-q", "auto_pm/contracts/gone.py")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "change")
    (repo / "02_规划" / "untracked.md").write_text("five\n", encoding="utf-8", newline="\n")
    return repo


def test_git_diff_lists_modified_deleted_and_both_sides_of_a_rename(tmp_path: Path, rules: tc.Rules) -> None:
    repo = _repo_with_changes(tmp_path)
    paths = tc.changed_paths_from_git(repo, "HEAD~1", "HEAD")
    assert sorted(paths) == ["auto_pm/contracts/gone.py", "tests/test_keep.py", "tests/test_new_name.py", "tests/test_old_name.py"]
    assert tc.classify_paths(paths, rules).tier == "core"


def test_git_diff_can_include_the_untracked_files_of_the_working_tree(tmp_path: Path) -> None:
    repo = _repo_with_changes(tmp_path)
    without = tc.changed_paths_from_git(repo, "HEAD~1", "HEAD")
    with_untracked = tc.changed_paths_from_git(repo, "HEAD~1", "HEAD", include_untracked=True)
    assert "02_规划/untracked.md" not in without and "02_规划/untracked.md" in with_untracked


def test_a_git_failure_is_an_error_not_an_empty_change_set(tmp_path: Path) -> None:
    with pytest.raises(tc.TierError):
        tc.changed_paths_from_git(tmp_path / "not-a-repository", "HEAD~1", "HEAD")


def test_the_rules_file_is_valid_versioned_and_hashed_into_every_result(rules: tc.Rules) -> None:
    raw = tc.RULES_FILE.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    assert data["schema"] == tc.SCHEMA and data["tiers"] == list(tc.TIERS) and data["unknown_tier"] == "core"
    assert rules.sha256 == hashlib.sha256(raw).hexdigest() and rules.version == data["version"]
    assert tc.classify_paths(["tests/core/test_a.py"], rules).rules_sha256 == rules.sha256
    ids = [rule.rule_id for rule in rules.rules]
    assert len(ids) == len(set(ids)) and {rule.tier for rule in rules.rules} == set(tc.TIERS)


def _rules_variant(tmp_path: Path, edit: dict[str, object] | None = None, rule_edit: dict[str, object] | None = None, drop_rules: bool = False) -> Path:
    data = json.loads(tc.RULES_FILE.read_text(encoding="utf-8"))
    if edit:
        data.update(edit)
    if rule_edit:
        data["rules"][0].update(rule_edit)
    if drop_rules:
        data["rules"] = []
    tmp_path.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "rules.json"
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return target


# Each bad variant is built INSIDE its own test run (one file per case), so every case proves its own refusal and no case can be shadowed by another.
BAD_RULES: dict[str, tuple[dict[str, object] | None, dict[str, object] | None, bool]] = {
    "unknown_tier_lowered": ({"unknown_tier": "product"}, None, False),
    "tiers_changed": ({"tiers": ["docs", "tests", "core"]}, None, False),
    "duplicate_id": (None, {"id": "CORE-DB"}, False),
    "bad_tier": (None, {"tier": "optional"}, False),
    "bad_kind": (None, {"kind": "regex"}, False),
    "empty_pattern": (None, {"pattern": ""}, False),
    "backslash_pattern": (None, {"pattern": "auto_pm\\contracts\\"}, False),
    "missing_reason": (None, {"reason": ""}, False),
    "bad_suffix": ({"behavior_suffixes": ["PY"]}, None, False),
    "no_rules": (None, None, True),
    "wrong_schema": ({"schema": "other.v1"}, None, False),
}


@pytest.mark.parametrize("kind", sorted(BAD_RULES))
def test_a_rules_file_that_could_lower_a_tier_or_hide_a_rule_is_refused(tmp_path: Path, kind: str) -> None:
    assert tc.load_rules(_rules_variant(tmp_path / "good")).version == tc.load_rules().version  # the unmodified copy loads, so only the edit can be the cause of a refusal
    edit, rule_edit, drop_rules = BAD_RULES[kind]
    with pytest.raises(tc.TierError):
        tc.load_rules(_rules_variant(tmp_path / kind, edit, rule_edit, drop_rules))


def test_a_missing_rules_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(tc.TierError):
        tc.load_rules(tmp_path / "absent.json")


def test_every_rule_classifies_its_own_pattern_at_its_own_tier_or_higher(rules: tc.Rules) -> None:
    for rule in rules.rules:
        sample = {"prefix": rule.pattern + "sample.txt", "exact": rule.pattern, "basename": "sub/" + rule.pattern, "basename_prefix": "sub/" + rule.pattern + "sample"}[rule.kind]
        verdict = tc.classify_path(sample, rules)
        assert tc.TIERS.index(verdict.tier) >= tc.TIERS.index(rule.tier), (rule.rule_id, sample, verdict.tier)
        assert rule.rule_id in verdict.rule_ids or tc.TIERS.index(verdict.tier) > tc.TIERS.index(rule.tier), (rule.rule_id, sample, verdict)


def test_the_gates_grow_with_the_tier() -> None:
    docs, tests, product, core = (tc.required_gates(tier) for tier in tc.TIERS)
    assert "nine-regression-groups" not in docs and "nine-regression-groups" not in tests
    assert "nine-regression-groups" in product and "nine-regression-groups" in core
    assert "real-process-concurrency-or-state-boundary-coverage" in core and "real-process-concurrency-or-state-boundary-coverage" not in product
    assert set(product) <= set(core) and "product-bytes-unchanged" in tests
    with pytest.raises(tc.TierError):
        tc.required_gates("optional")


def test_the_result_carries_the_gates_of_the_computed_tier_and_the_rule_ids(rules: tc.Rules) -> None:
    result = tc.classify_paths(["auto_pm/contracts/mission.py"], rules)
    assert result.gates == tc.required_gates("core")
    payload = result.to_dict()
    assert payload["tier"] == "core" and payload["paths"][0]["rules"] == ["CORE-CONTRACTS"]


def test_every_tracked_file_of_the_project_classifies_and_the_unknown_ones_are_the_known_ones(rules: tc.Rules) -> None:
    listing = subprocess.run(["git", "-C", str(PROJECT), "-c", "core.quotePath=false", "ls-files", "-z"], capture_output=True, check=True).stdout.decode("utf-8")
    tracked = [item for item in listing.split("\x00") if item]
    assert len(tracked) > 500, len(tracked)
    unknown_top = {tc.classify_path(item, rules).normalized.split("/")[0] for item in tracked if "UNKNOWN_PATH" in tc.classify_path(item, rules).rule_ids}
    assert unknown_top == KNOWN_UNKNOWN_TOP_LEVEL, unknown_top


def test_the_command_line_exit_codes(capsys: pytest.CaptureFixture[str]) -> None:
    assert tc.main(["--paths", "tests/core/test_a.py", "--declared", "tests"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["tier"] == "tests" and first["problems"] == []
    assert tc.main(["--paths", "auto_pm/contracts/mission.py", "--declared", "tests"]) == 2
    second = json.loads(capsys.readouterr().out)
    assert second["tier"] == "core" and second["problems"]
    assert tc.main(["--paths", "tests/../auto_pm/x.py"]) == 3
    assert "error" in json.loads(capsys.readouterr().out)
