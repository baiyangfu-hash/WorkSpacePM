"""TD-SW008-563、564、565、570（D-298～D-300、D-305）：project import 认出 Python 仓库、和 create 同一个落点、不拷 .git、报错不建议没有的参数。

素材照云端实测的 Gemini-test：有 core/*.py 和 tests/、没有 pyproject，源目录是一个 git 仓库。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner, Result

from auto_pm.application.core.project_service import ProjectService
from auto_pm.ui.cli.__main__ import cli

pytestmark = pytest.mark.usefixtures("identity_guard_off")

RESEARCH = ("01_Project自动化项目管理", "Python自动化项目总库", "02_在研项目")


def _python_repo(root: Path, name: str = "SW-2026-952_Gemini-test") -> Path:
    src = root / "incoming" / name
    (src / "core").mkdir(parents=True)
    (src / "core" / "engine.py").write_text("X = 1\n", encoding="utf-8")
    (src / "tests").mkdir()
    (src / "tests" / "test_engine.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    (src / ".git").mkdir()
    (src / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    return src


def _workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.joinpath(*RESEARCH).mkdir(parents=True)
    return ws


def _import(ws: Path, *args: str) -> Result:
    return CliRunner().invoke(cli, ["-w", str(ws), "project", "import", *args], catch_exceptions=False)


def test_i01_a_python_repo_is_imported_as_python_into_the_create_folder_without_dot_git(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    src = _python_repo(tmp_path)
    result = _import(ws, str(src))
    assert result.exit_code == 0, result.output
    dest = ws.joinpath(*RESEARCH, src.name)
    answers = yaml.safe_load((dest / ".copier-answers.yml").read_text(encoding="utf-8"))
    assert (answers["stack"], answers["_src_path"]) == ("python", "templates/python-tool")
    imported = ProjectService(str(ws)).get_project("SW-2026-952")
    assert imported is not None and imported.stack == "python"
    assert (dest / "core" / "engine.py").is_file() and not (dest / ".git").exists()
    assert (src / ".git" / "HEAD").is_file()  # 源仓库原样留着
    assert "没有复制源仓库的 .git" in result.output and "技术栈: python" in result.output


def test_i02_import_and_create_put_a_python_project_in_the_same_folder(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    created = CliRunner().invoke(
        cli, ["-w", str(ws), "project", "create", "--stack", "python", "--id", "SW-2026-953", "--name", "验收py"],
        catch_exceptions=False,
    )
    assert created.exit_code == 0, created.output
    assert _import(ws, str(_python_repo(tmp_path))).exit_code == 0
    create_dir = ProjectService(str(ws)).get_project("SW-2026-953")
    import_dir = ProjectService(str(ws)).get_project("SW-2026-952")
    assert create_dir is not None and import_dir is not None
    assert Path(create_dir.path).parent == Path(import_dir.path).parent == ws.joinpath(*RESEARCH)


def test_i03_a_plc_project_still_goes_to_the_old_folder_and_records_its_stack(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    src = tmp_path / "incoming" / "DJ-2026-954_PLC"
    src.mkdir(parents=True)
    (src / ".plc.json").write_text(json.dumps({"name": "DJ-2026-954", "version": "V1.0.0"}), encoding="utf-8")
    assert _import(ws, str(src)).exit_code == 0
    answers = yaml.safe_load((ws / "02_在研项目" / src.name / ".copier-answers.yml").read_text(encoding="utf-8"))
    assert answers["stack"] == "plc"


def test_i04_stack_option_names_the_stack_of_a_folder_that_says_nothing(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    src = tmp_path / "incoming" / "SW-2026-955_Docs"
    src.mkdir(parents=True)
    (src / "README.md").write_text("# x\n", encoding="utf-8")
    result = _import(ws, str(src), "--stack", "python")
    assert result.exit_code == 0, result.output
    answers = yaml.safe_load((ws.joinpath(*RESEARCH, src.name) / ".copier-answers.yml").read_text(encoding="utf-8"))
    assert answers["stack"] == "python"


def test_i05_a_stack_option_that_contradicts_the_folder_is_refused_before_copying(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    src = _python_repo(tmp_path)
    result = CliRunner().invoke(cli, ["-w", str(ws), "project", "import", str(src), "--stack", "plc"])
    assert result.exit_code == 1 and "看起来是 python 项目" in result.output
    assert not ws.joinpath(*RESEARCH, src.name).exists() and not (ws / "02_在研项目" / src.name).exists()


def test_i06_move_says_that_dot_git_came_along(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    src = _python_repo(tmp_path)
    result = _import(ws, str(src), "--move")
    assert result.exit_code == 0, result.output
    assert (ws.joinpath(*RESEARCH, src.name) / ".git").is_dir()
    assert "嵌入仓库" in result.output


def test_i07_a_bad_id_does_not_suggest_auto_id_which_import_does_not_have(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    src = _python_repo(tmp_path, name="Gemini-test")
    result = CliRunner().invoke(cli, ["-w", str(ws), "project", "import", str(src), "-bl", "SW"])
    assert result.exit_code == 1
    assert "不是合法业务线" in result.output and "--auto-id" not in result.output
    assert "改名" in result.output
    assert "--auto-id" not in CliRunner().invoke(cli, ["project", "import", "--help"]).output


def test_i08_create_keeps_its_auto_id_hint(tmp_path: Path) -> None:
    from auto_pm.domain.models.project import InvalidBusinessLineError, resolve_business_line

    with pytest.raises(InvalidBusinessLineError, match="--auto-id"):
        resolve_business_line("ZZ-2026-001")


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        ({"pyproject.toml": ""}, True),
        ({"setup.py": ""}, True),
        ({"requirements.txt": ""}, True),
        ({"main.py": ""}, True),
        ({"core/engine.py": ""}, True),
        ({"README.md": "", "docs/a.md": ""}, False),
        ({".git/hooks/x.py": ""}, False),
        ({"a/b/c/deep.py": ""}, False),
    ],
)
def test_i09_what_counts_as_a_python_repo(tmp_path: Path, files: dict[str, str], expected: bool) -> None:
    from auto_pm.application.core.project_scanner import ProjectScanner

    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    assert ProjectScanner.looks_like_python_repo(str(tmp_path)) is expected


def test_i10_retrofit_alone_recognises_a_python_repo(tmp_path: Path) -> None:
    """不经 CLI 直接补全（导入以外的调用方）也认得出 Python 仓库"""
    src = _python_repo(tmp_path)
    ProjectService(str(tmp_path)).retrofit_project_by_path(str(src))
    answers = yaml.safe_load((src / ".copier-answers.yml").read_text(encoding="utf-8"))
    assert answers["stack"] == "python"
