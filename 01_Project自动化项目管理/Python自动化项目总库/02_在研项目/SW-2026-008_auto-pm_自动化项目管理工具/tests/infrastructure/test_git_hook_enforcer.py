"""Regression coverage for the control-root commit attribution contract."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from auto_pm.infrastructure.git_hook_enforcer import (
    CONTROL_ROOT_FILE_BINDINGS,
    ProjectBinding,
    StagedIndexEntry,
    StagedSnapshot,
    StagedSnapshotError,
    _binding_for_staged_file,
    _change_entry,
    _ledger_entry,
    _parse_raw_index_entries,
    _require_snapshot_matches_index,
    enforce_commit_msg,
    enforce_pre_commit,
    filter_production_files,
    get_staged_snapshot,
    independent_staged_changes,
    is_excluded_from_production,
)
from tests.git_support import git_out

SW008_ROOT = (
    "01_Project自动化项目管理/Python自动化项目总库/02_在研项目/"
    "SW-2026-008_auto-pm_自动化项目管理工具"
)
SW009_ROOT = (
    "01_Project自动化项目管理/Python自动化项目总库/02_在研项目/"
    "SW-2026-009_英语学习助手"
)


@pytest.fixture
def bindings() -> tuple[ProjectBinding, ProjectBinding]:
    """Provide two ordinary registered project roots."""
    return (
        ProjectBinding("SW-2026-008", SW008_ROOT),
        ProjectBinding("SW-2026-009", SW009_ROOT),
    )


def test_control_root_main_is_bound_to_sw008(
    bindings: tuple[ProjectBinding, ProjectBinding],
) -> None:
    """The only declared root entry resolves to its explicitly named project."""
    assert _binding_for_staged_file("main.py", bindings).project_id == "SW-2026-008"


def test_unknown_root_production_file_remains_rejected(
    bindings: tuple[ProjectBinding, ProjectBinding],
) -> None:
    """The mapping must not permit arbitrary root-level Python files."""
    with pytest.raises(StagedSnapshotError, match="归属未知或不唯一"):
        _binding_for_staged_file("unregistered_root.py", bindings)


def test_nested_project_path_uses_its_directory_binding(
    bindings: tuple[ProjectBinding, ProjectBinding],
) -> None:
    """Existing directory-based project attribution remains unchanged."""
    path = f"{SW009_ROOT}/src/main.py"
    assert _binding_for_staged_file(path, bindings).project_id == "SW-2026-009"


def test_control_root_mapping_rejects_unknown_project_id(
    bindings: tuple[ProjectBinding, ProjectBinding], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A malformed mapping cannot create an unregistered project attribution."""
    monkeypatch.setitem(CONTROL_ROOT_FILE_BINDINGS, "main.py", "SW-9999-999")
    with pytest.raises(StagedSnapshotError, match="归属未知或不唯一"):
        _binding_for_staged_file("main.py", bindings)


def _git(cwd: Path, *args: str) -> str:
    return git_out(cwd, *args)


def test_fixture_git_failure_carries_the_git_error_text(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    with pytest.raises(RuntimeError, match=r"worktree add .*退出码 128[\s\S]*fatal"):
        _git(tmp_path, "worktree", "add", str(tmp_path / "wt"), "no-such-ref")


def _fixture_chg_content(
    chg_id: str, project_id: str, status: str = "approved"
) -> str:
    return f"""# {chg_id}

## 3. 变更基本信息

### 3.0 编号与项目

| 字段 | 内容 |
| --- | --- |
| 变更编号 | {chg_id} |
| 项目名称 | test fixture |
| 项目编号 | {project_id} |

### 3.4 申请信息

| 字段 | 内容 |
| --- | --- |
| 变更状态 | {status} |
"""


def _make_dual_root_fixture(
    tmp_path: Path,
    *,
    project_id: str = "SW-2026-008",
    chg_id: str = "CHG-SCPT-2026-346",
    chg_in_control: bool = True,
    chg_in_candidate: bool = False,
    chg_status: str = "approved",
    chg_pid: str | None = None,
    control_ledger_clean: bool = True,
    candidate_ledger_clean: bool = False,
    candidate_has_staged_code: bool = True,
    control_has_staged_code: bool = False,
) -> tuple[Path, Path, Path]:
    """构建 primary repo 与 linked worktree 临时测试夹具。"""
    primary_repo = tmp_path / "primary-control-root"
    project_rel = f"01_Project/{project_id}"
    project_dir = primary_repo / project_rel
    src_dir = project_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)

    # 注册项目与配置文件
    (project_dir / ".copier-answers.yml").write_text(
        f"project_id: {project_id}\nproject_name: test project\nstack: python\n",
        encoding="utf-8",
    )

    # 变更单目录
    chg_dir = project_dir / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-SCPT"
    chg_dir.mkdir(parents=True, exist_ok=True)
    ledger_dir = project_dir / "04_监控" / "01_变更管理" / "02_变更记录"
    ledger_dir.mkdir(parents=True, exist_ok=True)

    if chg_in_control:
        actual_pid = chg_pid or project_id
        chg_file = chg_dir / f"{chg_id}.md"
        chg_file.write_text(
            _fixture_chg_content(chg_id, actual_pid, chg_status),
            encoding="utf-8",
        )

    ledger_file = ledger_dir / "01_版本变更台账.md"
    if control_ledger_clean:
        ledger_file.write_text(
            f"# 版本变更台账\n\n| 变更编号 | 状态 |\n| --- | --- |\n| {chg_id} | {chg_status} |\n",
            encoding="utf-8",
        )
    else:
        ledger_file.write_text(
            "# 版本变更台账\n\n| 变更编号 | 状态 |\n| --- | --- |\n| baseline | closed |\n",
            encoding="utf-8",
        )

    code_file = src_dir / "service.py"
    code_file.write_text("VALUE = 1\n", encoding="utf-8")

    _git(primary_repo, "init")
    _git(primary_repo, "config", "user.email", "test@example.invalid")
    _git(primary_repo, "config", "user.name", "Test User")
    _git(primary_repo, "add", ".")
    _git(primary_repo, "commit", "-m", "initial baseline")

    # 创建 linked worktree
    worktree_dir = tmp_path / "worktree-candidate"
    _git(primary_repo, "worktree", "add", str(worktree_dir), "HEAD")

    # 在 candidate 中处理状态
    cand_code = worktree_dir / project_rel / "src" / "service.py"
    if candidate_has_staged_code:
        cand_code.write_text("VALUE = 2\n", encoding="utf-8")
        _git(worktree_dir, "add", f"{project_rel}/src/service.py")

    cand_ledger = (
        worktree_dir
        / project_rel
        / "04_监控"
        / "01_变更管理"
        / "02_变更记录"
        / "01_版本变更台账.md"
    )
    if not candidate_ledger_clean:
        # 候选台账为旧快照，包含历史差异
        cand_ledger.write_text(
            "# 历史旧台账快照\n\n| 变更编号 | 状态 |\n| --- | --- |\n| OLD-001 | closed |\n",
            encoding="utf-8",
        )
        _git(worktree_dir, "add", str(cand_ledger.relative_to(worktree_dir)))

    if chg_in_candidate:
        cand_chg = (
            worktree_dir
            / project_rel
            / "04_监控"
            / "01_变更管理"
            / "01_变更单"
            / "CHG-SCPT"
            / f"{chg_id}.md"
        )
        cand_chg.parent.mkdir(parents=True, exist_ok=True)
        cand_chg.write_text(
            _fixture_chg_content(chg_id, project_id, chg_status),
            encoding="utf-8",
        )
        _git(worktree_dir, "add", str(cand_chg.relative_to(worktree_dir)))

    if control_has_staged_code:
        code_file.write_text("VALUE = 99\n", encoding="utf-8")
        _git(primary_repo, "add", f"{project_rel}/src/service.py")

    msg_file = worktree_dir / "COMMIT_EDITMSG"
    msg_file.write_text(f"feat: [{chg_id}] candidate implementation\n", encoding="utf-8")

    return worktree_dir, primary_repo, msg_file


def test_scenario_1_linked_worktree_staged_code_with_candidate_stale_ledger_passes(
    tmp_path: Path,
) -> None:
    """必测场景 1: linked worktree 候选台账为旧快照，但 control-root 台账 clean：门禁通过。"""
    cand, ctrl, msg = _make_dual_root_fixture(
        tmp_path,
        control_ledger_clean=True,
        candidate_ledger_clean=False,
    )
    assert enforce_pre_commit(cand, control_root=ctrl) == 0
    assert enforce_commit_msg(cand, msg, control_root=ctrl) == 0


def test_scenario_2_candidate_empty_index_does_not_misattribute_control_staged_code(
    tmp_path: Path,
) -> None:
    """必测场景 2: 候选 index 为空而 control-root 有 staged 文件：不得误判为候选提交。"""
    # 控制根既有 staged 生产代码、台账又不一致：若门禁误读控制根 index，必定阻断。
    cand, ctrl, msg = _make_dual_root_fixture(
        tmp_path,
        candidate_has_staged_code=False,
        control_has_staged_code=True,
        control_ledger_clean=False,
        chg_in_control=False,
    )
    assert "service.py" not in _git(cand, "diff", "--cached", "--name-only")
    assert "service.py" in _git(ctrl, "diff", "--cached", "--name-only")
    assert enforce_pre_commit(cand, control_root=ctrl) == 0
    assert enforce_commit_msg(cand, msg, control_root=ctrl) == 0


def test_identity_is_proven_even_when_candidate_index_is_empty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """空候选 index 也不能跳过同仓身份校验（实施卡 §5.2 判卷前必须证明）。"""
    cand, _ctrl, msg = _make_dual_root_fixture(
        tmp_path, candidate_has_staged_code=False
    )
    outsider = tmp_path / "outsider"
    outsider.mkdir()
    _git(outsider, "init")

    assert enforce_pre_commit(cand, control_root=outsider) == 1
    assert "同仓身份校验失败" in capsys.readouterr().out
    assert enforce_commit_msg(cand, msg, control_root=outsider) == 1
    assert "同仓身份校验失败" in capsys.readouterr().out


def test_scenario_3_control_root_ledger_inconsistent_blocks_submission(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """必测场景 3: control-root 当前台账不一致：门禁阻断。"""
    cand, ctrl, msg = _make_dual_root_fixture(
        tmp_path,
        control_ledger_clean=False,  # 控制根台账缺失变更单
    )
    assert enforce_pre_commit(cand, control_root=ctrl) == 1
    out = capsys.readouterr().out
    assert "台账未闭环" in out or "台账检查异常" in out or "阻断" in out


def test_scenario_4_different_common_dir_blocks_submission(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """必测场景 4: 候选与 control-root 不属于同一 common-dir：门禁阻断。"""
    repo1 = tmp_path / "repo1"
    repo2 = tmp_path / "repo2"
    repo1.mkdir()
    repo2.mkdir()
    _git(repo1, "init")
    _git(repo2, "init")
    (repo1 / "main.py").write_text("print(1)\n", encoding="utf-8")
    _git(repo1, "add", "main.py")
    msg_file = repo1 / "COMMIT_EDITMSG"
    msg_file.write_text("feat: [CHG-SCPT-2026-346] test\n", encoding="utf-8")

    assert enforce_pre_commit(repo1, control_root=repo2) == 1
    out = capsys.readouterr().out
    assert "同仓身份校验失败" in out or "不属于同一 Git 仓库" in out


def test_scenario_5_control_root_missing_or_not_primary_blocks_submission(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """必测场景 5: control-root 缺失或不是 primary root：门禁阻断。"""
    cand, ctrl, msg = _make_dual_root_fixture(tmp_path)
    missing_ctrl = tmp_path / "non-existent"

    assert enforce_pre_commit(cand, control_root=missing_ctrl) == 1
    out = capsys.readouterr().out
    assert "不存在" in out or "同仓身份校验失败" in out

    # 传入 linked worktree 作为 control-root 也必须拒绝 (.git 是文件而非目录)
    another_wt = tmp_path / "another-worktree"
    _git(ctrl, "worktree", "add", str(another_wt), "HEAD")
    assert enforce_pre_commit(cand, control_root=another_wt) == 1
    out2 = capsys.readouterr().out
    assert "不是有效主仓库根目录" in out2 or "同仓身份校验失败" in out2


def test_scenario_6_chg_only_in_candidate_not_in_control_root_blocks_submission(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """必测场景 6: commit message 引用的 CHG 仅存在于候选旧快照、不存在于 control-root：门禁阻断。"""
    cand, ctrl, msg = _make_dual_root_fixture(
        tmp_path,
        chg_in_control=False,
        chg_in_candidate=True,
    )
    assert enforce_commit_msg(cand, msg, control_root=ctrl) == 1
    out = capsys.readouterr().out
    assert "控制根缺少关联变更单文件" in out


def test_scenario_7_control_root_chg_pid_mismatch_blocks_submission(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """必测场景 7: CHG 在 control-root 存在但 PID 与候选生产路径不一致：门禁阻断。"""
    cand, ctrl, msg = _make_dual_root_fixture(
        tmp_path,
        chg_in_control=True,
        chg_pid="SW-2026-999",  # 与 SW-2026-008 不匹配
    )
    assert enforce_commit_msg(cand, msg, control_root=ctrl) == 1
    out = capsys.readouterr().out
    assert "控制根变更单 PID 与生产代码归属不一致" in out



_PROBE_LAUNCHER = """from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, {source_root!r})
from auto_pm.infrastructure.git_hook_enforcer import (
    enforce_commit_msg,
    enforce_pre_commit,
)

args = sys.argv[1:]
workspace = Path(args[args.index("-w") + 1])
control_root = Path(args[args.index("--control-root") + 1])
command = args[args.index("git-hook") + 1]
if command == "pre-commit":
    raise SystemExit(enforce_pre_commit(workspace, control_root=control_root))
raise SystemExit(enforce_commit_msg(workspace, Path(args[-1]), control_root=control_root))
"""


def _install_real_hooks(primary: Path) -> dict[str, str]:
    """在临时 primary repo 安装真实 Hook，启动器调用本源码树的真实判卷器。"""
    import os
    import sys

    from auto_pm.cli.__main__ import cli
    from click.testing import CliRunner

    source_root = Path(__file__).resolve().parents[2]
    (primary / "main.py").write_text(
        _PROBE_LAUNCHER.format(source_root=str(source_root)), encoding="utf-8"
    )
    result = CliRunner().invoke(cli, ["-w", str(primary), "git-hook", "install"])
    assert result.exit_code == 0, result.output
    for hook_name in ("pre-commit", "commit-msg"):
        (primary / ".git" / "hooks" / hook_name).chmod(0o755)
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PATH"] = (
        str(Path(sys.executable).parent) + os.pathsep + environment.get("PATH", "")
    )
    return environment


def test_real_hook_in_linked_worktree_uses_candidate_index_and_control_governance(
    tmp_path: Path,
) -> None:
    """真实 git commit：证据来自 linked worktree index，治理来自 primary control-root。"""
    cand, primary, _msg = _make_dual_root_fixture(tmp_path)
    environment = _install_real_hooks(primary)
    head_before = _git(cand, "rev-parse", "HEAD")

    # 候选台账是旧快照（已暂存），控制根台账为当前真源：真实 Hook 必须放行。
    ok = subprocess.run(
        ["git", "commit", "-m", "feat: [CHG-SCPT-2026-346] candidate implementation"],
        cwd=cand,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert _git(cand, "rev-parse", "HEAD") != head_before
    assert "auto-pm pre-commit" in ok.stdout + ok.stderr


def test_real_hook_rejects_chg_missing_from_control_root(tmp_path: Path) -> None:
    """真实 git commit：CHG 仅存在于候选旧快照时必须被控制根真源拒绝，且不产生提交。"""
    cand, primary, _msg = _make_dual_root_fixture(
        tmp_path, chg_in_control=False, chg_in_candidate=True
    )
    environment = _install_real_hooks(primary)
    head_before = _git(cand, "rev-parse", "HEAD")

    blocked = subprocess.run(
        ["git", "commit", "-m", "feat: [CHG-SCPT-2026-346] candidate implementation"],
        cwd=cand,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
    )
    assert blocked.returncode != 0
    output = blocked.stdout + blocked.stderr
    # 控制根台账登记了该 CHG 但其变更单文件不存在：由控制根真源在 pre-commit 即阻断；
    # 候选快照里存在同名 CHG 不能使其通过。
    assert "台账对账不一致" in output or "控制根缺少关联变更单文件" in output
    assert _git(cand, "rev-parse", "HEAD") == head_before


def test_real_hook_launcher_rejects_external_control_root(tmp_path: Path) -> None:
    """真实启动器入口：外部/无关仓库作为 control-root 时非零退出。"""
    import os
    import sys

    cand, primary, _msg = _make_dual_root_fixture(tmp_path)
    environment = _install_real_hooks(primary)
    outsider = tmp_path / "outsider"
    outsider.mkdir()
    _git(outsider, "init")

    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(primary / "main.py"),
            "-w",
            str(cand),
            "--control-root",
            str(outsider),
            "git-hook",
            "pre-commit",
        ],
        cwd=cand,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
    )
    assert result.returncode != 0
    assert "同仓身份校验失败" in result.stdout
    assert os.path.isdir(cand)


# --- TD-046：只删除、只重命名受控文件的提交不能绕过变更单 ---------------------------------------------------------


def _delete_scene(tmp_path: Path, **kwargs: object) -> tuple[Path, Path, Path]:
    """候选工位里没有任何暂存代码改动；调用方再自己 git rm / git mv。"""
    cand, ctrl, msg = _make_dual_root_fixture(
        tmp_path, candidate_has_staged_code=False, candidate_ledger_clean=True, **kwargs  # type: ignore[arg-type]
    )
    return cand, ctrl, msg


SERVICE = "01_Project/SW-2026-008/src/service.py"


def _no_chg_message(path: Path) -> None:
    path.write_text("chore: tidy up\n", encoding="utf-8")


def test_td046_deleting_a_production_file_without_a_change_order_is_refused(tmp_path: Path) -> None:
    cand, ctrl, msg = _delete_scene(tmp_path)
    _git(cand, "rm", "-q", SERVICE)
    _no_chg_message(msg)
    assert _git(cand, "diff", "--cached", "--name-only") == SERVICE
    assert enforce_commit_msg(cand, msg, control_root=ctrl) == 1


def test_td046_deleting_a_production_file_with_a_valid_change_order_passes(tmp_path: Path) -> None:
    cand, ctrl, msg = _delete_scene(tmp_path)
    _git(cand, "rm", "-q", SERVICE)
    assert enforce_pre_commit(cand, control_root=ctrl) == 0
    assert enforce_commit_msg(cand, msg, control_root=ctrl) == 0


def test_td046_deleting_a_production_file_under_an_unapproved_change_order_is_refused(tmp_path: Path) -> None:
    cand, ctrl, msg = _delete_scene(tmp_path, chg_status="draft")
    _git(cand, "rm", "-q", SERVICE)
    assert enforce_commit_msg(cand, msg, control_root=ctrl) == 1


def test_td046_renaming_a_production_file_to_a_non_production_name_is_refused(tmp_path: Path) -> None:
    """旧路径是生产代码、新路径不是：以前只看新路径，整个提交被当成纯文档放行。"""
    cand, ctrl, msg = _delete_scene(tmp_path)
    _git(cand, "mv", SERVICE, "01_Project/SW-2026-008/src/service.txt")
    _no_chg_message(msg)
    assert enforce_commit_msg(cand, msg, control_root=ctrl) == 1


def test_td046_renaming_a_production_file_out_of_the_project_is_refused(tmp_path: Path) -> None:
    cand, ctrl, msg = _delete_scene(tmp_path)
    (cand / "elsewhere").mkdir()
    _git(cand, "mv", SERVICE, "elsewhere/service.txt")
    _no_chg_message(msg)
    assert enforce_commit_msg(cand, msg, control_root=ctrl) == 1


def test_td046_deleting_a_test_or_doc_file_still_needs_no_change_order(tmp_path: Path) -> None:
    cand, ctrl, msg = _delete_scene(tmp_path)
    test_file = cand / "01_Project/SW-2026-008/tests/test_service.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_x():\n    pass\n", encoding="utf-8")
    _git(cand, "add", str(test_file.relative_to(cand)))
    _git(cand, "commit", "-q", "-m", "add test")
    _git(cand, "rm", "-q", str(test_file.relative_to(cand)))
    _no_chg_message(msg)
    assert enforce_commit_msg(cand, msg, control_root=ctrl) == 0


def test_td046_the_snapshot_records_deletions_with_the_old_blob(tmp_path: Path) -> None:
    cand, _ctrl, _msg = _delete_scene(tmp_path)
    old_blob = _git(cand, "rev-parse", f"HEAD:{SERVICE}")
    _git(cand, "rm", "-q", SERVICE)
    (entry,) = get_staged_snapshot(cand).entries
    assert (entry.path, entry.status, entry.object_id, entry.deleted) == (SERVICE, "D", old_blob, True)


def test_td046_a_rename_is_two_entries_old_path_deleted_and_new_path_added(tmp_path: Path) -> None:
    cand, _ctrl, _msg = _delete_scene(tmp_path)
    _git(cand, "mv", SERVICE, SERVICE.replace("service.py", "renamed.py"))
    entries = {e.path: e.status for e in get_staged_snapshot(cand).entries}
    assert entries == {SERVICE: "D", SERVICE.replace("service.py", "renamed.py"): "A"}


def test_td046_a_deleted_change_order_or_ledger_is_not_evidence() -> None:
    chg = "01_Project/SW-2026-008/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-346.md"
    ledger = "01_Project/SW-2026-008/04_监控/01_变更管理/02_变更记录/01_版本变更台账.md"
    binding = ProjectBinding("SW-2026-008", "01_Project/SW-2026-008")
    deleted = StagedSnapshot((StagedIndexEntry(chg, "a" * 40, "D"), StagedIndexEntry(ledger, "b" * 40, "D")))
    with pytest.raises(StagedSnapshotError, match="缺少或重复关联变更单"):
        _change_entry(deleted, binding, "CHG-SCPT-2026-346")
    with pytest.raises(StagedSnapshotError, match="缺少或重复关联项目台账"):
        _ledger_entry(deleted, binding)
    kept = StagedSnapshot((StagedIndexEntry(chg, "a" * 40, "M"),))
    assert _change_entry(kept, binding, "CHG-SCPT-2026-346").path == chg


@pytest.mark.parametrize("status", ["X", "R", "U"])
def test_td046_unknown_raw_statuses_are_still_refused(status: str) -> None:
    raw = f":100644 000000 {'a' * 40} {'b' * 40} {status}\0some/path.py\0"
    with pytest.raises(StagedSnapshotError, match="不支持的状态"):
        _parse_raw_index_entries(raw)


def test_td046_a_raw_deletion_line_parses_to_a_deleted_entry() -> None:
    raw = f":100644 000000 {'a' * 40} {'0' * 40} D\0some/path.py\0"
    assert _parse_raw_index_entries(raw) == (
        StagedIndexEntry("some/path.py", "a" * 40, "D", "100644"),
    )


# ---- TD-100：同名文件只改内容 / 只改权限位，快照也必须看见；快照与独立比较不一致即拒绝 ----


def test_td100_same_path_content_change_is_visible_with_the_new_blob(tmp_path: Path) -> None:
    cand, _ctrl, _msg = _delete_scene(tmp_path)
    old_blob = _git(cand, "rev-parse", f"HEAD:{SERVICE}")
    (cand / SERVICE).write_text("def changed():\n    return 2\n", encoding="utf-8")
    _git(cand, "add", SERVICE)
    (entry,) = get_staged_snapshot(cand).entries
    assert (entry.path, entry.status) == (SERVICE, "M")
    assert entry.object_id != old_blob
    assert entry.object_id == _git(cand, "rev-parse", f":{SERVICE}")


def test_td100_mode_only_change_is_visible_with_the_new_mode(tmp_path: Path) -> None:
    cand, _ctrl, _msg = _delete_scene(tmp_path)
    old_blob = _git(cand, "rev-parse", f"HEAD:{SERVICE}")
    _git(cand, "update-index", "--chmod=+x", SERVICE)
    (entry,) = get_staged_snapshot(cand).entries
    assert (entry.path, entry.status, entry.mode) == (SERVICE, "M", "100755")
    assert entry.object_id == old_blob  # 内容没变，只有权限位变


def test_td100_independent_comparison_covers_add_modify_delete_and_mode(tmp_path: Path) -> None:
    cand, _ctrl, _msg = _delete_scene(tmp_path)
    (cand / SERVICE).write_text("def changed():\n    return 3\n", encoding="utf-8")
    new_file = cand / "01_Project/SW-2026-008/src/new.py"
    new_file.write_text("x = 1\n", encoding="utf-8")
    _git(cand, "add", SERVICE, "01_Project/SW-2026-008/src/new.py")
    changes = independent_staged_changes(cand)
    snapshot = get_staged_snapshot(cand)
    assert changes == {
        e.path: (e.mode, e.object_id, e.deleted) for e in snapshot.entries
    }
    assert set(changes) == {SERVICE, "01_Project/SW-2026-008/src/new.py"}


def test_td100_first_commit_without_head_is_all_additions(tmp_path: Path) -> None:
    repo = tmp_path / "fresh"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "a.py").write_text("a = 1\n", encoding="utf-8")
    _git(repo, "add", "a.py")
    assert set(independent_staged_changes(repo)) == {"a.py"}
    assert [e.path for e in get_staged_snapshot(repo).entries] == ["a.py"]


@pytest.mark.parametrize("tamper", ["blob", "mode", "missing", "extra", "deleted_flag"])
def test_td100_a_snapshot_that_disagrees_with_the_index_is_refused(tmp_path: Path, tamper: str) -> None:
    cand, _ctrl, _msg = _delete_scene(tmp_path)
    (cand / SERVICE).write_text("def changed():\n    return 4\n", encoding="utf-8")
    _git(cand, "add", SERVICE)
    (entry,) = get_staged_snapshot(cand).entries
    forged = {
        "blob": StagedSnapshot((StagedIndexEntry(entry.path, "c" * 40, "M", entry.mode),)),
        "mode": StagedSnapshot((StagedIndexEntry(entry.path, entry.object_id, "M", "100755"),)),
        "missing": StagedSnapshot(()),
        "extra": StagedSnapshot(
            (entry, StagedIndexEntry("other.py", entry.object_id, "A", entry.mode))
        ),
        "deleted_flag": StagedSnapshot((StagedIndexEntry(entry.path, entry.object_id, "D", entry.mode),)),
    }[tamper]
    with pytest.raises(StagedSnapshotError, match="独立比较不一致"):
        _require_snapshot_matches_index(cand, forged)


def test_td100_unmerged_index_entries_are_refused(tmp_path: Path) -> None:
    """真实合并冲突留下 stage 1/2/3 条目；快照不能把它当普通改动放行。"""
    cand, _ctrl, _msg = _delete_scene(tmp_path)
    _git(cand, "checkout", "-q", "-b", "side")
    (cand / SERVICE).write_text("def side():\n    return 1\n", encoding="utf-8")
    _git(cand, "commit", "-qam", "side change")
    _git(cand, "checkout", "-q", "-")
    (cand / SERVICE).write_text("def main_side():\n    return 2\n", encoding="utf-8")
    _git(cand, "commit", "-qam", "main change")
    merged = subprocess.run(
        ["git", "merge", "side"], cwd=str(cand), capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert merged.returncode != 0, "测试前提：合并必须冲突"
    with pytest.raises(StagedSnapshotError):
        get_staged_snapshot(cand)



def _run_preflight(cand: Path, ctrl: Path, msg: Path, *, control_root: Path | None = None):
    from auto_pm.cli.__main__ import cli
    from click.testing import CliRunner

    return CliRunner().invoke(
        cli,
        ["-w", str(cand), "--control-root", str(control_root or ctrl), "git-hook", "preflight", str(msg)],
    )


def test_td100_preflight_refuses_a_content_only_change_of_a_production_file(tmp_path: Path) -> None:
    """同名生产文件只改内容、提交说明又不绑变更单：整条 preflight 链路必须拒绝。"""
    cand, ctrl, msg = _delete_scene(tmp_path)
    (cand / SERVICE).write_text("def changed():\n    return 9\n", encoding="utf-8")
    _git(cand, "add", SERVICE)
    _no_chg_message(msg)
    result = _run_preflight(cand, ctrl, msg)
    assert result.exit_code != 0
    assert "Commit Message 未绑定变更单" in result.output


def test_td100_preflight_passes_a_content_only_change_with_a_valid_change_order(tmp_path: Path) -> None:
    cand, ctrl, msg = _delete_scene(tmp_path)
    (cand / SERVICE).write_text("def changed():\n    return 9\n", encoding="utf-8")
    _git(cand, "add", SERVICE)
    result = _run_preflight(cand, ctrl, msg)
    assert result.exit_code == 0, result.output


def test_td100_preflight_refuses_a_mode_only_change_without_a_change_order(tmp_path: Path) -> None:
    cand, ctrl, msg = _delete_scene(tmp_path)
    _git(cand, "update-index", "--chmod=+x", SERVICE)
    _no_chg_message(msg)
    result = _run_preflight(cand, ctrl, msg)
    assert result.exit_code != 0
    assert "Commit Message 未绑定变更单" in result.output


def test_td100_preflight_refuses_a_linked_worktree_given_itself_as_control_root(tmp_path: Path) -> None:
    cand, ctrl, msg = _delete_scene(tmp_path)
    (cand / SERVICE).write_text("def changed():\n    return 9\n", encoding="utf-8")
    _git(cand, "add", SERVICE)
    result = _run_preflight(cand, ctrl, msg, control_root=cand)
    assert result.exit_code != 0
    assert "同仓身份校验失败" in result.output


def test_td100_preflight_refuses_when_the_snapshot_cannot_be_read(tmp_path: Path) -> None:
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()
    msg = not_a_repo / "COMMIT_EDITMSG"
    msg.write_text("x\n", encoding="utf-8")
    result = _run_preflight(not_a_repo, not_a_repo, msg)
    assert result.exit_code == 1
    assert "无法读取 Git 暂存区" in result.output


def test_td100_preflight_refuses_when_the_pre_commit_gate_blows_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cand, ctrl, msg = _delete_scene(tmp_path)
    (cand / SERVICE).write_text("def changed():\n    return 9\n", encoding="utf-8")
    _git(cand, "add", SERVICE)

    def boom(*_args: object, **_kwargs: object) -> int:
        raise RuntimeError("台账内部故障")

    monkeypatch.setattr("auto_pm.infrastructure.git_hook_enforcer._run_ledger_gate", boom)
    result = _run_preflight(cand, ctrl, msg)
    assert result.exit_code != 0
    assert "台账检查异常" in result.output


def test_td100_independent_comparison_sees_deletions_with_the_old_mode_and_blob(tmp_path: Path) -> None:
    cand, _ctrl, _msg = _delete_scene(tmp_path)
    old_blob = _git(cand, "rev-parse", f"HEAD:{SERVICE}")
    _git(cand, "rm", "-q", SERVICE)
    assert independent_staged_changes(cand) == {SERVICE: ("100644", old_blob, True)}


def test_td100_get_staged_snapshot_runs_the_independent_comparison(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """diff --cached 的解析结果被篡改（比如漏报）时，取快照这一步本身就要拒绝。"""
    cand, _ctrl, _msg = _delete_scene(tmp_path)
    (cand / SERVICE).write_text("def changed():\n    return 5\n", encoding="utf-8")
    _git(cand, "add", SERVICE)
    monkeypatch.setattr(
        "auto_pm.infrastructure.git_hook_enforcer._parse_raw_index_entries", lambda _raw: ()
    )
    with pytest.raises(StagedSnapshotError, match="独立比较不一致"):
        get_staged_snapshot(cand)


def test_td100_get_staged_files_lists_deletions_and_the_old_path_of_a_rename(tmp_path: Path) -> None:
    """get_staged_files 是回退路径；它若退回只看新增/修改，删除和改名的旧路径又会消失。"""
    from auto_pm.infrastructure.git_hook_enforcer import get_staged_files

    cand, _ctrl, _msg = _delete_scene(tmp_path)
    renamed = SERVICE.replace("service.py", "renamed.py")
    _git(cand, "mv", SERVICE, renamed)
    assert sorted(get_staged_files(cand)) == sorted([SERVICE, renamed])
    _git(cand, "reset", "-q", "--hard")
    _git(cand, "rm", "-q", SERVICE)
    assert get_staged_files(cand) == [SERVICE]


def test_td100_a_file_type_change_is_a_staged_change_with_status_t(tmp_path: Path) -> None:
    """普通文件换成符号链接（git 状态 T）也必须进快照，不能因为状态白名单漏掉。"""
    cand, _ctrl, _msg = _delete_scene(tmp_path)
    target = cand / SERVICE
    target.unlink()
    try:
        target.symlink_to("elsewhere.py")
    except (OSError, NotImplementedError):
        pytest.skip("本机不能创建符号链接")
    _git(cand, "add", SERVICE)
    (entry,) = get_staged_snapshot(cand).entries
    assert (entry.path, entry.status, entry.mode) == (SERVICE, "T", "120000")


def test_td100_intent_to_add_files_are_not_part_of_the_commit_and_do_not_break_it(tmp_path: Path) -> None:
    """``git add -N`` 的占位条目不进提交：快照不含它，也不能因为它与 diff --cached 对不上而拒绝整个提交。"""
    cand, _ctrl, _msg = _delete_scene(tmp_path)
    placeholder = cand / "01_Project/SW-2026-008/src/later.py"
    placeholder.write_text("x = 1\n", encoding="utf-8")
    _git(cand, "add", "-N", str(placeholder.relative_to(cand)))
    (cand / SERVICE).write_text("def changed():\n    return 6\n", encoding="utf-8")
    _git(cand, "add", SERVICE)
    assert [e.path for e in get_staged_snapshot(cand).entries] == [SERVICE]
    assert set(independent_staged_changes(cand)) == {SERVICE}


def test_td100_a_really_staged_empty_file_is_still_checked(tmp_path: Path) -> None:
    cand, _ctrl, _msg = _delete_scene(tmp_path)
    empty = cand / "01_Project/SW-2026-008/src/empty.py"
    empty.write_text("", encoding="utf-8")
    _git(cand, "add", str(empty.relative_to(cand)))
    assert [e.path for e in get_staged_snapshot(cand).entries] == ["01_Project/SW-2026-008/src/empty.py"]
    assert set(independent_staged_changes(cand)) == {"01_Project/SW-2026-008/src/empty.py"}


@pytest.mark.parametrize(
    "path",
    [
        "auto_pm/core/latest_state.py",
        "FB/contest_logic.scl",
        "tools/attest_signer.py",
        "x/mydocs/y.py",
        "SW-2026-009_英语学习助手/src/level_test_page.py",
        "src/scratchpad/run.py",
        "src/tests_helper/run.py",
        "src/my.auto-pm/run.py",
        "src/PM_SESSION/run.py",
        "src/docs_tool.py",
    ],
)
def test_td194_production_files_with_lookalike_names_are_not_exempt(path: str) -> None:
    """子串相似但不是测试、文档目录或测试文件名的生产代码，必须仍要求变更单。"""
    assert not is_excluded_from_production(path)
    assert filter_production_files([path]) == [path]


@pytest.mark.parametrize(
    "path",
    [
        "tests/test_a.py",
        "proj/tests/unit/helper.py",
        "proj\\tests\\helper.py",
        "proj/docs/gen.py",
        "proj/scratch/try.py",
        "proj/src/test_parser.py",
        ".auto-pm/worktrees/x/a.py",
        "00_Obsidian_Base全局规范文件仓库/tools/x.py",
        "PM_SESSION_20261001.py",
    ],
)
def test_td194_real_test_doc_scratch_paths_stay_exempt(path: str) -> None:
    assert is_excluded_from_production(path)
    assert filter_production_files([path]) == []


def test_td194_only_production_extensions_count() -> None:
    assert filter_production_files(["src/a.md", "src/b.py", "src/c.txt", "src/d.qml"]) == ["src/b.py", "src/d.qml"]


def test_production_extension_match_ignores_case() -> None:
    """Windows 上 TIA 导出的文件常是 .SCL / .ST，大写扩展名也是生产代码。"""
    paths = ["FB/Motor.SCL", "FB/Seq.St", "src/App.PY", "ui/Main.QML"]
    assert filter_production_files(paths) == paths


# ---- TD-SW008-115：新增文件命中忽略规则就拒绝提交 ----


def _ignore_scene(tmp_path: Path) -> tuple[Path, Path]:
    cand, ctrl, _msg = _make_dual_root_fixture(
        tmp_path, candidate_has_staged_code=False, candidate_ledger_clean=True
    )
    (cand / ".gitignore").write_text("*.zip\n!keep.zip\n", encoding="utf-8")
    _git(cand, "add", ".gitignore")
    _git(cand, "commit", "-qm", "ignore rules")
    return cand, ctrl


def test_td115_force_added_file_matching_an_ignore_rule_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cand, ctrl = _ignore_scene(tmp_path)
    (cand / "pack.zip").write_text("x", encoding="utf-8")
    _git(cand, "add", "-f", "pack.zip")
    assert enforce_pre_commit(cand, control_root=ctrl) == 1
    out = capsys.readouterr().out
    assert "pack.zip" in out and ".gitignore:1" in out and "git rm --cached" in out


def test_td115_a_file_re_included_by_a_negation_rule_is_allowed(tmp_path: Path) -> None:
    cand, ctrl = _ignore_scene(tmp_path)
    (cand / "keep.zip").write_text("x", encoding="utf-8")
    _git(cand, "add", "-f", "keep.zip")
    assert enforce_pre_commit(cand, control_root=ctrl) == 0


def test_td115_a_plain_file_is_allowed(tmp_path: Path) -> None:
    cand, ctrl = _ignore_scene(tmp_path)
    (cand / "notes.txt").write_text("x", encoding="utf-8")
    _git(cand, "add", "notes.txt")
    assert enforce_pre_commit(cand, control_root=ctrl) == 0


def test_td115_changing_an_already_tracked_ignored_file_is_not_a_new_addition(tmp_path: Path) -> None:
    cand, ctrl, _msg = _make_dual_root_fixture(
        tmp_path, candidate_has_staged_code=False, candidate_ledger_clean=True
    )
    (cand / "old.zip").write_text("v1", encoding="utf-8")
    _git(cand, "add", "-f", "old.zip")
    _git(cand, "commit", "-qm", "old zip")
    (cand / ".gitignore").write_text("*.zip\n", encoding="utf-8")
    _git(cand, "add", ".gitignore")
    _git(cand, "commit", "-qm", "rule after the file")
    (cand / "old.zip").write_text("v2", encoding="utf-8")
    _git(cand, "add", "old.zip")
    assert enforce_pre_commit(cand, control_root=ctrl) == 0


def test_td115_a_failing_scan_refuses_instead_of_passing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import auto_pm.infrastructure.ignored_file_scan as scan

    cand, ctrl = _ignore_scene(tmp_path)
    (cand / "plain.txt").write_text("x", encoding="utf-8")
    _git(cand, "add", "plain.txt")

    def boom(*_a: object, **_k: object) -> list[object]:
        raise scan.IgnoreScanError("坏了")

    monkeypatch.setattr(scan, "ignored_among", boom)
    assert enforce_pre_commit(cand, control_root=ctrl) == 1


def test_td115_scan_handles_spaces_and_chinese_in_names(tmp_path: Path) -> None:
    from auto_pm.infrastructure.ignored_file_scan import ignored_among

    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / ".gitignore").write_text("*.bak\n", encoding="utf-8")
    hits = ignored_among(repo, ["中文 目录/备份.bak", "中文 目录/正常.txt"])
    assert [h.path for h in hits] == ["中文 目录/备份.bak"]


# ---- TD-SW008-087 / TD-115：忽略规则扫描走真实 preflight 入口，拦截与超时都必须拒绝 ----


def _ignore_preflight_scene(tmp_path: Path) -> tuple[Path, Path, Path]:
    cand, ctrl, msg = _make_dual_root_fixture(
        tmp_path, candidate_has_staged_code=False, candidate_ledger_clean=True
    )
    (cand / ".gitignore").write_text("*.zip\n", encoding="utf-8")
    _git(cand, "add", ".gitignore")
    _git(cand, "commit", "-qm", "ignore rules")
    _no_chg_message(msg)
    return cand, ctrl, msg


def _ignore_preflight(cand: Path, ctrl: Path, msg: Path):  # type: ignore[no-untyped-def]
    from auto_pm.cli.__main__ import cli
    from click.testing import CliRunner

    return CliRunner().invoke(
        cli, ["-w", str(cand), "--control-root", str(ctrl), "git-hook", "preflight", str(msg)]
    )


def test_td115_preflight_entry_refuses_a_force_added_ignored_file(tmp_path: Path) -> None:
    """Through ``git-hook preflight`` (the entry the real hook runs), not just the enforcer function."""
    cand, ctrl, msg = _ignore_preflight_scene(tmp_path)
    (cand / "pack.zip").write_text("x", encoding="utf-8")
    _git(cand, "add", "-f", "pack.zip")
    result = _ignore_preflight(cand, ctrl, msg)
    assert result.exit_code != 0
    assert "新增文件命中仓库忽略规则" in result.output and "pack.zip" in result.output


def test_td115_preflight_entry_lets_a_plain_file_through_the_ignore_scan(tmp_path: Path) -> None:
    cand, ctrl, msg = _ignore_preflight_scene(tmp_path)
    (cand / "notes.txt").write_text("x", encoding="utf-8")
    _git(cand, "add", "notes.txt")
    result = _ignore_preflight(cand, ctrl, msg)
    assert "命中仓库忽略规则" not in result.output and "忽略规则扫描失败" not in result.output
    assert result.exit_code == 0, result.output


def test_td115_preflight_entry_refuses_when_the_ignore_scan_hangs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A hung ``git check-ignore`` must refuse the commit with the timeout receipt, never pass it."""
    import subprocess as sp

    cand, ctrl, msg = _ignore_preflight_scene(tmp_path)
    (cand / "notes.txt").write_text("x", encoding="utf-8")
    _git(cand, "add", "notes.txt")
    real_run = sp.run

    def hang_on_check_ignore(command: list[str], *args: object, **kwargs: object) -> object:
        if "check-ignore" in command:
            raise sp.TimeoutExpired(command, kwargs["timeout"])  # type: ignore[arg-type]
        return real_run(command, *args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr("auto_pm.infrastructure.git_timeout.subprocess.run", hang_on_check_ignore)
    result = _ignore_preflight(cand, ctrl, msg)
    assert result.exit_code != 0
    assert "忽略规则扫描失败" in result.output and "超时回执" in result.output
