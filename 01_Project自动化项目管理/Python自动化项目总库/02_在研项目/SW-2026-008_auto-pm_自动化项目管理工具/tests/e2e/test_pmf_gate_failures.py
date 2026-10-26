"""Real-hook negative proofs: the two installed Git hooks refuse bad evidence in a real, isolated repository (V06, hooks half).

Nothing is faked: the fixture project is built by the product's own ``change`` and ``ledger`` commands in a temporary repository, the hooks are the ones
``git-hook install`` writes, and every attempt is a real ``git commit``. A refusal must leave the scene as it was (no commit, the staged change still
staged) and must come from the right hook for the right reason; a positive control proves that the same scene commits when the evidence is good, so a
broken fixture cannot pass as a refusal. The staged state is compared in full (mode, blob id, stage and path of every index entry), not only by file name, and
a sensitivity test proves the comparison sees a changed blob and a changed mode. The judge-side bad-evidence counter-examples live in ``test_pmf_gate_judge.py``.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from auto_pm.cli.__main__ import cli
from click.testing import CliRunner

import auto_pm
from tests.git_support import git_out

PID = "SW-2026-901"
OTHER_PID = "SW-2026-902"
LAUNCHER = """from auto_pm.cli.__main__ import cli

if __name__ == "__main__":
    cli()
"""
_TRANSITIONS = ("submitted", "under_review", "approved", "implementing")


def _environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(auto_pm.__file__).resolve().parent.parent)
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment.get("PATH", "")
    return environment


@dataclass
class Scene:
    repo: Path
    chg: str

    def git(self, *args: str) -> str:
        return git_out(self.repo, *args, env=_environment(), timeout=180)

    def product(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.repo / "main.py"), "-w", str(self.repo), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=_environment(), timeout=180, check=False,
        )

    def commit(self, message: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "commit", "-m", message],
            cwd=self.repo, capture_output=True, text=True, encoding="utf-8", errors="replace", env=_environment(), timeout=180, check=False,
        )

    def head(self) -> str:
        return self.git("rev-parse", "HEAD")

    def staged(self) -> str:
        """The whole staged state: mode, blob id, stage number and path of every index entry, so a changed blob or mode shows up, not only a changed name."""
        return self.git("ls-files", "--stage", "-z")

    @property
    def project(self) -> Path:
        return self.repo / f"{PID}_fixture"

    @property
    def ledger(self) -> Path:
        return self.project / "04_监控" / "01_变更管理" / "02_变更记录" / "01_版本变更台账.md"


def _build(tmp_path: Path, final_state: str = "implementing") -> Scene:
    """A repository with one registered project, a real change request moved to ``final_state``, a reconciled ledger and a staged production change."""

    repo = tmp_path / "gate-repo"
    (repo / f"{PID}_fixture" / "src").mkdir(parents=True)
    (repo / f"{PID}_fixture" / ".copier-answers.yml").write_text(f"project_id: {PID}\nproject_name: gate fixture\nstack: python\n", encoding="utf-8")
    (repo / f"{PID}_fixture" / "src" / "service.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "main.py").write_text(LAUNCHER, encoding="utf-8")
    (repo / ".gitignore").write_text("main.py\n.auto-pm/\n", encoding="utf-8")
    scene = Scene(repo, "")
    scene.git("init")
    scene.git("config", "user.email", "gate@example.invalid")
    scene.git("config", "user.name", "gate fixture")
    scene.git("add", "-A")
    scene.git("commit", "-m", "baseline")
    created = scene.product(
        "change", "create", "--pid", PID, "--domain", "SCPT", "--nature", "OPT", "--scope", "MODULE", "--applicant", "fubai",
        "--background", "gate fixture", "--necessity", "gate fixture", "--references", "none", "--urgency", "normal",
    )
    match = re.search(r"CHG-SCPT-\d{4}-\d+", created.stdout)
    assert created.returncode == 0 and match, created.stdout + created.stderr
    chg = match.group(0)
    for target in _TRANSITIONS[: _TRANSITIONS.index(final_state) + 1] if final_state in _TRANSITIONS else ():
        moved = scene.product("change", "transition", chg, "--pid", PID, "--to", target, "--approver", "fubai", "--comment", "gate fixture")
        assert moved.returncode == 0, moved.stdout + moved.stderr
    reconciled = scene.product("ledger", "reconcile", PID)
    assert reconciled.returncode == 0 and "台账缺失: 0 条, 台账多余(孤儿): 0 条, 状态不一致: 0 条" in reconciled.stdout, reconciled.stdout
    installed = CliRunner().invoke(cli, ["-w", str(repo), "git-hook", "install"])
    assert installed.exit_code == 0, installed.output
    (scene.project / "src" / "service.py").write_text("VALUE = 2\n", encoding="utf-8")
    scene.git("add", "-A")
    return Scene(repo, chg)


def _build_two(tmp_path: Path) -> tuple[Scene, str]:
    """Two registered projects in one repository. The returned scene stages a production change of project 901 together with the governance files of both projects;
    the second value is a change request that exists only in project 902 (its second one), a valid and approved change request that belongs to the wrong project."""

    repo = tmp_path / "gate-repo"
    for pid, folder in ((PID, f"{PID}_fixture"), (OTHER_PID, f"{OTHER_PID}_other")):
        (repo / folder / "src").mkdir(parents=True)
        (repo / folder / ".copier-answers.yml").write_text(f"project_id: {pid}\nproject_name: gate fixture {pid}\nstack: python\n", encoding="utf-8")
        (repo / folder / "src" / "service.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "main.py").write_text(LAUNCHER, encoding="utf-8")
    (repo / ".gitignore").write_text("main.py\n.auto-pm/\n", encoding="utf-8")
    scene = Scene(repo, "")
    scene.git("init")
    scene.git("config", "user.email", "gate@example.invalid")
    scene.git("config", "user.name", "gate fixture")
    scene.git("add", "-A")
    scene.git("commit", "-m", "baseline")
    created_ids = []
    for pid in (PID, OTHER_PID, OTHER_PID):
        created = scene.product(
            "change", "create", "--pid", pid, "--domain", "SCPT", "--nature", "OPT", "--scope", "MODULE", "--applicant", "fubai",
            "--background", "gate fixture", "--necessity", "gate fixture", "--references", "none", "--urgency", "normal",
        )
        match = re.search(r"CHG-SCPT-\d{4}-\d+", created.stdout)
        assert created.returncode == 0 and match, created.stdout + created.stderr
        for target in _TRANSITIONS:
            moved = scene.product("change", "transition", match.group(0), "--pid", pid, "--to", target, "--approver", "fubai", "--comment", "gate fixture")
            assert moved.returncode == 0, moved.stdout + moved.stderr
        created_ids.append(match.group(0))
        reconciled = scene.product("ledger", "reconcile", pid)
        assert reconciled.returncode == 0 and "台账缺失: 0 条, 台账多余(孤儿): 0 条, 状态不一致: 0 条" in reconciled.stdout, reconciled.stdout
    installed = CliRunner().invoke(cli, ["-w", str(repo), "git-hook", "install"])
    assert installed.exit_code == 0, installed.output
    assert not list((repo / f"{PID}_fixture").rglob(f"{created_ids[2]}.md")), "the foreign change request must not exist in project 901"
    (repo / f"{PID}_fixture" / "src" / "service.py").write_text("VALUE = 2\n", encoding="utf-8")
    scene.git("add", "-A")
    return Scene(repo, created_ids[0]), created_ids[2]


def _refused(scene: Scene, result: subprocess.CompletedProcess[str], hook: str, phrase: str, head: str, staged: str) -> None:
    """The commit did not happen, the scene is as it was, and the right hook refused for the right reason."""

    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert scene.head() == head, "a refused commit must not move HEAD"
    assert scene.staged() == staged, "a refused commit must leave the staged change staged"
    assert f"[auto-pm {hook}]" in output, output
    assert phrase in output, output


@pytest.fixture
def scene(tmp_path: Path) -> Scene:
    return _build(tmp_path)


def test_g01_the_positive_control_commits_through_both_real_hooks(scene: Scene) -> None:
    head = scene.head()
    result = scene.commit(f"feat: [{scene.chg}] change the service")
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert scene.head() != head
    assert "相关项目台账门禁校验通过" in output and "强校验绑定通过" in output, output  # pre-commit and commit-msg both ran and both agreed


def test_g02_a_commit_message_without_a_change_request_is_refused_by_commit_msg(scene: Scene) -> None:
    head, staged = scene.head(), scene.staged()
    _refused(scene, scene.commit("feat: change the service"), "commit-msg", "未绑定变更单", head, staged)


def test_g03_a_change_request_that_does_not_exist_is_refused_by_commit_msg(scene: Scene) -> None:
    head, staged = scene.head(), scene.staged()
    _refused(scene, scene.commit("feat: [CHG-SCPT-2099-999] change the service"), "commit-msg", "证据不完整或不一致", head, staged)


def test_g04_two_change_requests_in_one_commit_are_refused_by_commit_msg(scene: Scene) -> None:
    head, staged = scene.head(), scene.staged()
    _refused(scene, scene.commit(f"feat: [{scene.chg}] [CHG-SCPT-2099-998] change the service"), "commit-msg", "必须且只能绑定一个变更单", head, staged)


def test_g05_a_change_request_that_is_not_approved_yet_is_refused_by_commit_msg(tmp_path: Path) -> None:
    scene = _build(tmp_path, final_state="submitted")
    head, staged = scene.head(), scene.staged()
    _refused(scene, scene.commit(f"feat: [{scene.chg}] change the service"), "commit-msg", "尚未获得审批批准", head, staged)


def test_g06_a_production_file_that_no_project_owns_is_refused_by_pre_commit(scene: Scene) -> None:
    (scene.repo / "unregistered").mkdir()
    (scene.repo / "unregistered" / "service.py").write_text("VALUE = 3\n", encoding="utf-8")
    scene.git("add", "-A")
    head, staged = scene.head(), scene.staged()
    _refused(scene, scene.commit(f"feat: [{scene.chg}] change the service"), "pre-commit", "归属未知或不唯一", head, staged)


def test_g07_a_ledger_that_does_not_match_its_change_requests_is_refused_by_pre_commit(scene: Scene) -> None:
    with scene.ledger.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("| CHG-SCPT-2099-123 | closed |\n")  # a row without a change request behind it
    scene.git("add", "-A")
    head, staged = scene.head(), scene.staged()
    _refused(scene, scene.commit(f"feat: [{scene.chg}] change the service"), "pre-commit", "台账未闭环", head, staged)


def test_g08_a_checker_that_crashes_in_pre_commit_still_blocks_the_commit(scene: Scene) -> None:
    crash_in_pre_commit = "\n".join(
        ["import sys", "", "if 'pre-commit' in sys.argv:", "    print('pre-commit checker crashed', file=sys.stderr)", "    raise RuntimeError('boom')", ""]
    )
    (scene.repo / "main.py").write_text(crash_in_pre_commit + LAUNCHER, encoding="utf-8")
    head, staged = scene.head(), scene.staged()
    result = scene.commit(f"feat: [{scene.chg}] change the service")
    output = result.stdout + result.stderr
    assert result.returncode != 0 and "pre-commit checker crashed" in output, output
    assert "[auto-pm commit-msg]" not in output, "the commit stopped in pre-commit, before the commit-msg hook ran"
    assert scene.head() == head and scene.staged() == staged


def test_g09_a_checker_that_crashes_only_in_commit_msg_still_blocks_the_commit(scene: Scene) -> None:
    crash_in_commit_msg = "\n".join(
        ["import sys", "", "if 'commit-msg' in sys.argv:", "    print('commit-msg checker crashed', file=sys.stderr)", "    raise RuntimeError('boom')", ""]
    )
    (scene.repo / "main.py").write_text(crash_in_commit_msg + LAUNCHER, encoding="utf-8")
    head, staged = scene.head(), scene.staged()
    result = scene.commit(f"feat: [{scene.chg}] change the service")
    output = result.stdout + result.stderr
    assert result.returncode != 0 and "commit-msg checker crashed" in output, output
    assert "相关项目台账门禁校验通过" in output, "the pre-commit hook ran and agreed; only the commit-msg checker crashed"
    assert scene.head() == head and scene.staged() == staged


@pytest.mark.parametrize("content", ["", "this is not a ledger table\nat all\n"], ids=["empty", "garbage"])
def test_g10_a_ledger_that_is_empty_or_garbage_is_refused_by_pre_commit(scene: Scene, content: str) -> None:
    scene.ledger.write_text(content, encoding="utf-8", newline="\n")  # the change request is still there, so its ledger row is missing
    scene.git("add", "-A")
    head, staged = scene.head(), scene.staged()
    result = scene.commit(f"feat: [{scene.chg}] change the service")
    _refused(scene, result, "pre-commit", "台账未闭环", head, staged)
    assert "缺失 1 条" in result.stdout + result.stderr, "the reconciler named the missing row, not an orphan or an exception"


def test_g11_production_files_of_two_registered_projects_in_one_commit_are_refused_by_commit_msg(tmp_path: Path) -> None:
    scene, _foreign = _build_two(tmp_path)
    (scene.repo / f"{OTHER_PID}_other" / "src" / "service.py").write_text("VALUE = 2\n", encoding="utf-8")
    scene.git("add", "-A")
    head, staged = scene.head(), scene.staged()
    _refused(scene, scene.commit(f"feat: [{scene.chg}] change both services"), "commit-msg", "归属项目不唯一", head, staged)


def test_g12_a_valid_change_request_that_belongs_to_another_project_is_refused_by_commit_msg(tmp_path: Path) -> None:
    scene, foreign = _build_two(tmp_path)
    head, staged = scene.head(), scene.staged()
    _refused(scene, scene.commit(f"feat: [{foreign}] change the service"), "commit-msg", "缺少或重复关联变更单", head, staged)


def test_g13_the_two_projects_fixture_commits_when_the_evidence_is_good(tmp_path: Path) -> None:
    scene, _foreign = _build_two(tmp_path)
    head = scene.head()
    result = scene.commit(f"feat: [{scene.chg}] change the service")
    assert result.returncode == 0 and scene.head() != head, result.stdout + result.stderr  # so the two refusals above are not an artefact of the two-project fixture


def test_g14_the_staged_state_comparison_sees_a_changed_blob_and_a_changed_mode_not_only_a_changed_name(scene: Scene) -> None:
    names_before, state_before = scene.git("diff", "--cached", "--name-only"), scene.staged()
    (scene.project / "src" / "service.py").write_text("VALUE = 3\n", encoding="utf-8")
    scene.git("add", "-A")  # the same path, another blob
    state_other_blob = scene.staged()
    assert scene.git("diff", "--cached", "--name-only") == names_before, "the name list alone cannot tell these two states apart"
    assert state_other_blob != state_before
    scene.git("update-index", "--chmod=+x", f"{PID}_fixture/src/service.py")  # the same path, the same blob, another mode
    assert scene.git("diff", "--cached", "--name-only") == names_before
    assert scene.staged() != state_other_blob
