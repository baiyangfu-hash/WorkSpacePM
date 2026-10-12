"""V07: the Python template really produces a second project whose own gates pass (WBS task V07, card CARD-SW008-M3-V07).

The existing template tests use a hand-made miniature template; this file uses the REAL ``templates/python-tool`` through ``TemplateService`` (the code path of the product),
generates real projects into a temporary directory and runs the generated project's own checks (its tests, ruff, strict mypy, its command line) in a child process. A generated
project is therefore proven, not assumed. The pinned file list below is the complete set a generated Python tool project contains; a change of the template has to change it here.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from auto_pm.application.core.template_service import TemplateService

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
PACKAGE = "template_probe_one"


def _generate(tmp_path: Path, project_id: str, project_name: str, package_name: str) -> Path:
    destination = tmp_path / project_id
    TemplateService(str(TEMPLATES_DIR)).copy_template(
        "python-tool",
        str(destination),
        {"project_id": project_id, "project_name": project_name, "package_name": package_name, "cli_command": package_name.replace("_", "-")},
    )
    return destination


def _child(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    env.pop("PYTHONPATH", None)  # the child must stand on its own, not on the product source tree
    return subprocess.run([sys.executable, "-B", "-m", *args], cwd=project, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=600)


def _expected_files(project_id: str, package: str) -> list[str]:
    return sorted([
        ".copier-answers.yml", ".github/pull_request_template.md", ".gitignore", ".pre-commit-config.yaml", ".ruff.toml", "01_启动/001_产品需求文档_PRD.md", f"PM_SESSION_{project_id}.md",
        "README.md", "Taskfile.yml", "pyproject.toml", "tests/__init__.py", "tests/conftest.py", "tests/test_import.py",
        f"{package}/__init__.py", f"{package}/app_context.py", f"{package}/py.typed",
        f"{package}/cli/__init__.py", f"{package}/cli/__main__.py", f"{package}/config/__init__.py", f"{package}/config/app_config.py", f"{package}/core/__init__.py",
        f"{package}/logging/__init__.py", f"{package}/logging/logging.py", f"{package}/utils/__init__.py", f"{package}/utils/file_utils.py",
    ])


def _generated_files(project: Path) -> list[str]:
    return sorted(p.relative_to(project).as_posix() for p in project.rglob("*") if p.is_file())


@pytest.fixture(scope="module")
def first_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _generate(tmp_path_factory.mktemp("v07a"), "SW-2026-901", "第一个模板工程", PACKAGE)


def test_t01_the_generated_project_has_exactly_the_pinned_file_set(tmp_path: Path) -> None:
    fresh = _generate(tmp_path, "SW-2026-901", "第一个模板工程", PACKAGE)  # fresh: the shared project collects tool caches from the child runs
    assert _generated_files(fresh) == _expected_files("SW-2026-901", PACKAGE)


def test_t02_no_template_placeholder_survives_in_names_or_text(tmp_path: Path) -> None:
    fresh = _generate(tmp_path, "SW-2026-901", "第一个模板工程", PACKAGE)
    leftovers = []
    for path in fresh.rglob("*"):
        rel = path.relative_to(fresh).as_posix()
        if "{{" in rel or "{%" in rel or rel.endswith(".jinja"):
            leftovers.append(rel)
        elif path.is_file() and path.suffix in {".py", ".toml", ".md", ".yml", ".yaml", ".ruff", ".txt"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            if "{{" in text or "{%" in text:
                leftovers.append(rel)
    assert leftovers == []


def test_t03_the_generated_projects_own_tests_pass(first_project: Path) -> None:
    done = _child(first_project, "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=", "tests")
    assert done.returncode == 0, done.stdout[-1500:] + done.stderr[-500:]
    assert "passed" in done.stdout


def test_t04_the_generated_project_passes_ruff(first_project: Path) -> None:
    done = _child(first_project, "ruff", "check", "--no-cache", ".")
    assert done.returncode == 0, done.stdout[-1500:] + done.stderr[-500:]


def test_t05_the_generated_project_passes_strict_mypy(first_project: Path) -> None:
    done = _child(first_project, "mypy", "--no-incremental", "--no-pretty", PACKAGE)
    assert done.returncode == 0, done.stdout[-1500:] + done.stderr[-500:]


def test_t06_the_generated_command_line_runs(first_project: Path) -> None:
    done = _child(first_project, f"{PACKAGE}.cli", "hello")
    assert done.returncode == 0, done.stdout[-800:] + done.stderr[-800:]
    assert "Hello from" in done.stdout


def test_t07_a_second_project_is_independent_of_the_first(tmp_path: Path, first_project: Path) -> None:
    second = _generate(tmp_path, "SW-2026-902", "第二个模板工程", "template_probe_two")
    assert _generated_files(second) == _expected_files("SW-2026-902", "template_probe_two")
    for path in second.rglob("*"):
        if path.is_file() and path.suffix in {".py", ".toml", ".md", ".yml", ".yaml"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            assert PACKAGE not in text and "SW-2026-901" not in text, path.name
    answers = (second / ".copier-answers.yml").read_text(encoding="utf-8", errors="replace")
    assert "SW-2026-902" in answers and "SW-2026-901" not in answers
    done = _child(second, "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=", "tests")
    assert done.returncode == 0, done.stdout[-1500:]


@pytest.mark.parametrize("bad_id", ["sw-2026-1", "SW2026901", "SW-26-901", ""], ids=["lowercase-short", "no-dashes", "short-year", "empty"])
def test_t08_a_malformed_project_id_is_rejected_and_leaves_nothing_behind(tmp_path: Path, bad_id: str) -> None:
    destination = tmp_path / "rejected"
    with pytest.raises(Exception):  # noqa: B017, PT011 - copier raises its own validation error type
        TemplateService(str(TEMPLATES_DIR)).copy_template("python-tool", str(destination), {"project_id": bad_id, "project_name": "x", "package_name": "x_pkg"})
    assert not destination.exists() or not any(destination.iterdir())


@pytest.mark.parametrize("bad_package", ["Bad-Name", "1abc", "has space"], ids=["upper-and-dash", "leading-digit", "space"])
def test_t09_a_malformed_package_name_is_rejected_and_leaves_nothing_behind(tmp_path: Path, bad_package: str) -> None:
    destination = tmp_path / "rejected"
    with pytest.raises(Exception):  # noqa: B017, PT011 - copier raises its own validation error type
        TemplateService(str(TEMPLATES_DIR)).copy_template("python-tool", str(destination), {"project_id": "SW-2026-903", "project_name": "x", "package_name": bad_package})
    assert not destination.exists() or not any(destination.iterdir())
