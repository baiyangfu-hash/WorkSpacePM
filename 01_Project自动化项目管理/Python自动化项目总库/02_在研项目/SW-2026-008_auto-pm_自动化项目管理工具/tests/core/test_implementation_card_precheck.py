"""Pre-start implementation-card precheck (card 027 §5, §6 G2/G3): read-only and fail-closed."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from auto_pm.cli.__main__ import cli

from auto_pm.application.core.implementation_card_precheck import (
    CommandNode,
    PrecheckReport,
    precheck_markdown_card,
    precheck_structured_card,
    resolve_command,
    scopes_outside_card,
)
from auto_pm.ui.cli.implementation_card import command_tree_of

TREE: dict[str, CommandNode] = command_tree_of(cli)
PROJECT = "SW-TEST_project"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _repository(root: Path, files: tuple[str, ...] = ()) -> str:
    """A throwaway control root whose single commit is the declared baseline."""

    _git(root, "init")
    for relative in ("README.md", *files):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("baseline\n", encoding="utf-8")
        _git(root, "add", "--", relative)
    _git(
        root,
        "-c",
        "user.name=Precheck Test",
        "-c",
        "user.email=precheck@example.invalid",
        "commit",
        "-m",
        "baseline",
    )
    return _git(root, "rev-parse", "HEAD")


def _card(
    root: Path,
    *,
    baseline: str,
    rows: list[tuple[str, str]],
    body: str = "",
    path_root: str = PROJECT,
    extra_header: str = "",
) -> Path:
    table = "\n".join(f"| {index} | `{path}` | {state} |" for index, (path, state) in enumerate(rows, 1))
    text = (
        "# Test card\n\n"
        f"> 隔离基线：`{baseline}`\n"
        f"> 路径根：`{path_root}`\n"
        f"{extra_header}\n"
        "## Owned paths\n\n"
        "| # | 路径 | 基线状态 |\n|---|---|---|\n"
        f"{table}\n\n{body}\n"
    )
    card = root / "card.md"
    card.write_text(text, encoding="utf-8")
    return card


def _check(root: Path, card: Path) -> PrecheckReport:
    return precheck_markdown_card(card, workspace_root=root, command_tree=TREE)


def _messages(report: PrecheckReport) -> str:
    return " | ".join(f"{item.rule}:{item.subject}:{item.message}" for item in report.findings)


# ---- G2: the two historical incidents, with inputs equivalent to the real cards ----------------


def test_history_020_doc_check_strict_is_rejected_with_the_offending_option(tmp_path: Path) -> None:
    baseline = _repository(tmp_path, (f"{PROJECT}/tests/test_a.py",))
    # Card 020 (U04S01) wrote this gate; `doc check` declares no --strict option.
    card = _card(
        tmp_path,
        baseline=baseline,
        rows=[("tests/test_a.py", "存在")],
        body="```powershell\n& $python -B main.py doc check --strict\n```\n",
    )

    report = _check(tmp_path, card)

    assert not report.passed
    assert any(
        item.rule == "command" and "--strict" in item.message and "doc check" in item.message
        for item in report.findings
    ), _messages(report)


@pytest.mark.parametrize(
    ("present_at_baseline", "state", "passes"),
    [
        (False, "存在", False),
        (False, "计划新增", True),
        (True, "计划新增", False),
        (True, "存在", True),
    ],
    ids=["missing-marked-existing", "missing-marked-planned", "present-marked-planned", "present"],
)
def test_history_019_test_path_must_match_its_baseline_state(
    tmp_path: Path, present_at_baseline: bool, state: str, passes: bool
) -> None:
    # Card 019 listed tests/infrastructure/test_continuity_store.py as existing, but on the
    # baseline actually used that file did not exist (it lived on another lineage).
    target = "tests/infrastructure/test_continuity_store.py"
    files = (f"{PROJECT}/{target}",) if present_at_baseline else (f"{PROJECT}/tests/other.py",)
    baseline = _repository(tmp_path, files)
    card = _card(tmp_path, baseline=baseline, rows=[(target, state)])

    report = _check(tmp_path, card)

    assert report.passed is passes, _messages(report)
    if not passes:
        assert any(item.rule == "path" and target in item.subject for item in report.findings)


# ---- G3: other precheck scenarios ------------------------------------------------------------


def test_legal_card_passes_and_reports_resolved_paths_and_commands(tmp_path: Path) -> None:
    baseline = _repository(tmp_path, (f"{PROJECT}/auto_pm/a.py",))
    card = _card(
        tmp_path,
        baseline=baseline,
        rows=[("auto_pm/a.py", "存在"), ("auto_pm/new.py", "计划新增")],
        body="Run `main.py continuity work create --work-id W --pid P` and `main.py ledger reconcile SW`.",
    )

    report = _check(tmp_path, card)

    assert report.passed, _messages(report)
    assert [item.path for item in report.paths] == [f"{PROJECT}/auto_pm/a.py", f"{PROJECT}/auto_pm/new.py"]
    assert report.commands == ("continuity work create", "ledger reconcile")
    assert report.baseline == baseline and len(report.card_sha256) == 64


@pytest.mark.parametrize(
    ("invocation", "fragment"),
    [
        ("main.py continuity wrok create", "未知命令或子组: wrok"),
        ("main.py nosuchgroup run", "未知命令或子组: nosuchgroup"),
        ("main.py continuity work", "命令不完整"),
        ("main.py continuity work create --no-such-option", "--no-such-option"),
    ],
    ids=["unknown-subgroup", "unknown-group", "incomplete", "unknown-option"],
)
def test_unknown_or_incomplete_commands_are_rejected(
    tmp_path: Path, invocation: str, fragment: str
) -> None:
    baseline = _repository(tmp_path)
    card = _card(tmp_path, baseline=baseline, rows=[("README.md", "存在")], path_root=".",
                 body=f"`{invocation}`")

    report = _check(tmp_path, card)

    assert not report.passed and fragment in _messages(report)


def test_unknown_subgroup_suggests_the_closest_legal_command() -> None:
    _path, findings = resolve_command(["continuity", "wrok", "create"], TREE)

    assert findings and "work" in findings[0].message


@pytest.mark.parametrize(
    ("baseline", "fragment"),
    [
        ("<BL02 统一基线不可变提交 SHA，阶段 2 完成后回写>", "占位符"),
        ("1234", "40 位小写 commit SHA"),
        ("f" * 40, "无法解析为完整 commit"),
    ],
    ids=["placeholder", "not-a-sha", "unresolvable"],
)
def test_baseline_must_be_a_resolvable_full_commit(tmp_path: Path, baseline: str, fragment: str) -> None:
    _repository(tmp_path)
    card = _card(tmp_path, baseline=baseline, rows=[("README.md", "存在")], path_root=".")

    report = _check(tmp_path, card)

    assert not report.passed and fragment in _messages(report)


def test_baseline_drift_rejects_existing_paths_missing_from_the_declared_commit(tmp_path: Path) -> None:
    old = _repository(tmp_path)
    (tmp_path / PROJECT).mkdir()
    (tmp_path / PROJECT / "late.py").write_text("x\n", encoding="utf-8")
    _git(tmp_path, "add", "--", f"{PROJECT}/late.py")
    _git(tmp_path, "-c", "user.name=T", "-c", "user.email=t@example.invalid", "commit", "-m", "late")
    card = _card(tmp_path, baseline=old, rows=[("late.py", "存在")])

    report = _check(tmp_path, card)

    assert not report.passed and "在隔离基线" in _messages(report)


@pytest.mark.parametrize(
    ("rows", "body", "fragment"),
    [
        ([("<待回写路径>", "存在")], "", "路径仍是占位符"),
        ([("README.md", "存在")], "`main.py implementation-card precheck --card-file <路径>`", "命令含占位符"),
        (
            [("README.md", "存在")],
            "| 字段 | 当前值 |\n|---|---|\n| 实施批准 | <待用户签字> |\n",
            "审批字段含占位符",
        ),
        ([("README.md", "存在")], "`main.py continuity run start --run-id TBD`", "命令含占位符"),
    ],
    ids=["path", "command", "approval", "tbd"],
)
def test_placeholders_in_paths_commands_or_approval_fields_are_rejected(
    tmp_path: Path, rows: list[tuple[str, str]], body: str, fragment: str
) -> None:
    baseline = _repository(tmp_path)
    card = _card(tmp_path, baseline=baseline, rows=rows, body=body, path_root=".")

    report = _check(tmp_path, card)

    assert not report.passed and fragment in _messages(report)


def test_path_table_without_baseline_state_column_is_rejected(tmp_path: Path) -> None:
    baseline = _repository(tmp_path)
    card = tmp_path / "card.md"
    card.write_text(
        f"> 隔离基线：`{baseline}`\n> 路径根：`.`\n\n| # | 路径 | 用途 |\n|---|---|---|\n| 1 | `README.md` | doc |\n",
        encoding="utf-8",
    )

    report = _check(tmp_path, card)

    assert not report.passed and "缺少“基线状态”列" in _messages(report)
    assert "没有含“路径”与“基线状态”两列的路径表" in _messages(report)


def test_unknown_baseline_state_value_is_rejected(tmp_path: Path) -> None:
    baseline = _repository(tmp_path)
    card = _card(tmp_path, baseline=baseline, rows=[("README.md", "修改")], path_root=".")

    report = _check(tmp_path, card)

    assert not report.passed and "基线状态只允许" in _messages(report)


def test_runtime_paths_are_checked_on_the_control_root_file_system(tmp_path: Path) -> None:
    baseline = _repository(tmp_path)
    card = _card(tmp_path, baseline=baseline, rows=[(".auto-pm/continuity.db", "运行态")])

    missing = _check(tmp_path, card)
    (tmp_path / ".auto-pm").mkdir()
    (tmp_path / ".auto-pm" / "continuity.db").write_bytes(b"")
    present = _check(tmp_path, card)

    assert not missing.passed and "运行态对象在控制根文件系统上不存在" in _messages(missing)
    assert present.passed, _messages(present)
    # Runtime rows are control-root relative, not joined with 路径根.
    assert present.paths[0].path == ".auto-pm/continuity.db"


def test_worktree_baseline_checks_the_control_root_working_tree(tmp_path: Path) -> None:
    _repository(tmp_path)
    (tmp_path / "draft.md").write_text("uncommitted\n", encoding="utf-8")
    ok = _card(tmp_path, baseline="WORKTREE", rows=[("draft.md", "存在"), ("next.md", "计划新增")],
               path_root=".")

    assert _check(tmp_path, ok).passed

    wrong = _card(tmp_path, baseline="WORKTREE", rows=[("draft.md", "计划新增")], path_root=".")
    assert not _check(tmp_path, wrong).passed


def test_legacy_card_without_machine_header_is_rejected_not_rewritten(tmp_path: Path) -> None:
    _repository(tmp_path)
    card = tmp_path / "019_legacy.md"
    original = "# 019 legacy card\n\n| # | 路径 | 说明 |\n|---|---|---|\n| 1 | `tests/x.py` | test |\n"
    card.write_text(original, encoding="utf-8")

    report = _check(tmp_path, card)

    assert not report.passed and "旧格式卡" in _messages(report)
    assert card.read_text(encoding="utf-8") == original


def test_precheck_is_read_only(tmp_path: Path) -> None:
    baseline = _repository(tmp_path)
    card = _card(tmp_path, baseline=baseline, rows=[("README.md", "存在")], path_root=".",
                 body="`main.py continuity work create --work-id W`")
    status_before = _git(tmp_path, "status", "--porcelain", "--untracked-files=all")
    head_before = _git(tmp_path, "rev-parse", "HEAD")

    _check(tmp_path, card)

    assert _git(tmp_path, "status", "--porcelain", "--untracked-files=all") == status_before
    assert _git(tmp_path, "rev-parse", "HEAD") == head_before
    assert not (tmp_path / ".auto-pm").exists()


def test_prose_mentioning_main_py_is_not_treated_as_an_invocation(tmp_path: Path) -> None:
    baseline = _repository(tmp_path)
    card = _card(tmp_path, baseline=baseline, rows=[("README.md", "存在")], path_root=".",
                 body="核验卡内 main.py 命令是否真实存在；`main.py` 调用须精确。")

    assert _check(tmp_path, card).passed


def test_scope_binding_accepts_card_paths_and_their_descendants_only(tmp_path: Path) -> None:
    baseline = _repository(tmp_path, (f"{PROJECT}/auto_pm/pkg/a.py",))
    report = _check(tmp_path, _card(tmp_path, baseline=baseline, rows=[("auto_pm/pkg", "存在")]))

    assert scopes_outside_card(
        [f"{PROJECT}/auto_pm/pkg", f"{PROJECT}/auto_pm/pkg/a.py", f"{PROJECT}\\auto_pm\\pkg\\a.py"],
        report,
    ) == []
    assert scopes_outside_card(
        [f"{PROJECT}/auto_pm/pkgx.py", f"{PROJECT}/auto_pm", f"{PROJECT}/auto_pm/pkg/../../x"], report
    ) == [f"{PROJECT}/auto_pm/pkgx.py", f"{PROJECT}/auto_pm", f"{PROJECT}/auto_pm/pkg/../../x"]


def test_structured_card_uses_the_same_path_and_command_rules(tmp_path: Path) -> None:
    from auto_pm.contracts.implementation_card import (
        Boundaries,
        EvidenceMap,
        GateDefinition,
        ImplementationCard,
        Outcomes,
        StopLines,
    )

    baseline = _repository(tmp_path, (f"{PROJECT}/a.py",))

    def card(**changes: object) -> ImplementationCard:
        values: dict[str, object] = {
            "card_id": "CARD-PRE-001", "project_id": "SW-TEST", "wbs_item_id": "U05",
            "milestone_id": "M2", "source_refs": ("WBS:plans/WBS.md",), "intent_type": "GOVERNANCE",
            "problem_statement": "p", "base_commit": baseline, "worktree_path": "C:/w",
            "owned_paths": (f"{PROJECT}/a.py", f"{PROJECT}/b.py"),
            "planned_new_paths": (f"{PROJECT}/b.py",),
            "commit_evidence_paths": ("evidence.md",), "non_goals": ("n",),
            "gates": (GateDefinition(name="g", cwd=PROJECT, argv=("python", "main.py", "ledger", "reconcile", "X"),
                                     coverage_targets=(f"{PROJECT}/a.py", f"{PROJECT}/b.py")),),
            "stop_lines": StopLines(max_runs=1, max_healing_attempts=0, deadline_utc="2099-01-01T00:00:00Z",
                                    quota_stop_remaining_percent=10),
            "outcomes": Outcomes(normal="n", small_problem="s", non_blocking="nb", blocking="b"),
            "evidence": EvidenceMap(decision_id="D", work_id="W", run_id="R", checkpoint_id="C", final_commit="F"),
            "boundaries": Boundaries(merge="SEPARATE_APPROVAL", push="SEPARATE_APPROVAL",
                                     deploy="SEPARATE_APPROVAL", release="SEPARATE_APPROVAL"),
        }
        values.update(changes)
        return ImplementationCard.model_validate(values)

    good = precheck_structured_card(card(), workspace_root=tmp_path, command_tree=TREE)
    assert good.passed, _messages(good)
    assert good.commands == ("ledger reconcile",)

    undeclared_new = precheck_structured_card(card(planned_new_paths=()), workspace_root=tmp_path,
                                              command_tree=TREE)
    assert not undeclared_new.passed and f"{PROJECT}/b.py" in _messages(undeclared_new)

    bad_gate = card(gates=(GateDefinition(name="g", cwd=PROJECT, argv=("python", "main.py", "doc", "check", "--strict"),
                                          coverage_targets=(f"{PROJECT}/a.py", f"{PROJECT}/b.py")),))
    rejected = precheck_structured_card(bad_gate, workspace_root=tmp_path, command_tree=TREE)
    assert not rejected.passed and "--strict" in _messages(rejected)


def test_real_rectification_card_fragment_with_placeholders_is_rejected(tmp_path: Path) -> None:
    """Replay card 028 V0.2's header and path row: an unresolved baseline and release ID fail."""

    card = tmp_path / "028_fragment.md"
    card.write_text(
        "> 隔离基线：`<BL02、R1、R2 的整合提交 SHA，步骤 2 完成后回写>`\n> 路径根：`.`\n\n"
        "| # | 路径 | 基线状态 |\n|---|---|---|\n"
        "| 4 | `00_Infrastructure/auto_pm/releases/<待 Gate B 前替换为精确 release_id>` | 计划新增 |\n",
        encoding="utf-8",
    )

    report = precheck_markdown_card(card, workspace_root=tmp_path, command_tree=TREE)

    assert not report.passed
    assert [item.subject for item in report.findings if item.rule == "placeholder"] == [
        "隔离基线",
        "00_Infrastructure/auto_pm/releases/<待 Gate B 前替换为精确 release_id>",
    ]
