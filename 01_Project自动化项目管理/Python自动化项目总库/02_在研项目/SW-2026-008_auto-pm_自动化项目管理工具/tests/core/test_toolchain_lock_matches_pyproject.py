"""TD-SW008-114: the pinned environment (lock file) must stay inside the ranges that pyproject.toml declares.

The lock file is what CI and a new machine install; pyproject.toml is what a reader believes is supported.  If a pin
drifts out of a declared range (or a declared package has no pin) the two disagree again, which is the fault TD-114
recorded.  Offline: it only reads the two files.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

PROJECT = Path(__file__).resolve().parents[2]
LOCK = PROJECT.parents[3] / "00_Infrastructure" / "auto_pm" / "environment" / "requirements-lock-py312-win.txt"


def read_lock(text: str) -> dict[str, str]:
    pins: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        requirement = Requirement(line)
        name = canonicalize_name(requirement.name)
        assert name not in pins, f"{name} 在锁文件里出现两次"
        specs = list(requirement.specifier)
        assert len(specs) == 1 and specs[0].operator == "==", f"锁文件只许 ==：{line}"
        pins[name] = specs[0].version
    return pins


def declared(pyproject: dict[str, object]) -> list[Requirement]:
    project = pyproject["project"]
    groups = pyproject.get("dependency-groups", {})
    assert isinstance(project, dict) and isinstance(groups, dict)
    lines = list(project.get("dependencies", []))
    for group in groups.values():
        lines.extend(item for item in group if isinstance(item, str))
    return [Requirement(line) for line in lines]


def mismatches(pins: dict[str, str], requirements: list[Requirement]) -> list[str]:
    problems: list[str] = []
    for requirement in requirements:
        name = canonicalize_name(requirement.name)
        if name not in pins:
            problems.append(f"{requirement.name}：pyproject 声明了，锁文件里没有")
        elif not requirement.specifier.contains(pins[name], prereleases=True):
            problems.append(f"{requirement.name}：锁 {pins[name]} 不在声明范围 {requirement.specifier} 内")
    return problems


def test_every_declared_package_is_pinned_inside_its_declared_range() -> None:
    pins = read_lock(LOCK.read_text(encoding="utf-8", errors="replace"))
    pyproject = tomllib.loads((PROJECT / "pyproject.toml").read_text(encoding="utf-8", errors="replace"))

    assert mismatches(pins, declared(pyproject)) == []


def test_a_pin_outside_the_declared_range_is_reported() -> None:
    requirements = [Requirement("ruff>=0.5,<0.17")]

    assert mismatches({"ruff": "0.16.4"}, requirements) == []
    assert "不在声明范围" in mismatches({"ruff": "0.17.0"}, requirements)[0]


def test_a_declared_package_without_a_pin_is_reported() -> None:
    assert "锁文件里没有" in mismatches({}, [Requirement("mypy>=1,<3")])[0]


def test_the_lock_must_be_exact_pins_without_repeats() -> None:
    import pytest

    with pytest.raises(AssertionError):
        read_lock("ruff>=0.5\n")
    with pytest.raises(AssertionError):
        read_lock("ruff==0.16.4\nRuff==0.16.4\n")
