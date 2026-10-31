"""F20: a Work scope written ``目录/**`` covers the files below the directory, everywhere the one scope rule is used."""

from __future__ import annotations

import click
import pytest

import auto_pm.ui.cli.__main__ as cli_main
from auto_pm.application.core.mission_admission import _overlapping
from auto_pm.infrastructure.control_root_guard import (
    authority_path_covered,
    authority_path_parts,
    authority_paths_covered,
)


@pytest.mark.parametrize(
    "wild",
    [
        "auto_pm/core/**",
        "auto_pm/core/**/*",
        "auto_pm\\core\\**",
        "./auto_pm/core/**",
        "auto_pm/core/**/**",
    ],
)
def test_a_trailing_double_star_names_the_directory(wild: str) -> None:
    assert authority_path_parts(wild, windows=False)[-2:] == ("auto_pm", "core")


@pytest.mark.parametrize("owned", ["auto_pm/core/a.py", "auto_pm/core/sub/b.py", "auto_pm/core"])
def test_owned_files_below_a_wildcard_scope_are_covered(owned: str) -> None:
    assert authority_path_covered(owned, ["auto_pm/core/**"], windows=False)
    assert authority_paths_covered([owned], ["auto_pm/core/**/*"], windows=False)


@pytest.mark.parametrize(
    "owned", ["auto_pm/core2/a.py", "auto_pm/other.py", "auto_pm", "tests/core/a.py"]
)
def test_files_outside_a_wildcard_scope_are_not_covered(owned: str) -> None:
    assert not authority_path_covered(owned, ["auto_pm/core/**"], windows=False)


def test_a_bare_double_star_covers_nothing() -> None:
    assert not authority_path_covered("anything.py", ["**"], windows=False)
    assert not authority_path_covered("anything.py", ["**/*"], windows=False)


def test_a_wildcard_in_the_middle_stays_literal_and_covers_nothing_real() -> None:
    assert not authority_path_covered("auto_pm/core/a.py", ["auto_pm/*/a.py"], windows=False)
    assert not authority_path_covered("auto_pm/core/a.py", ["auto_pm/**/a.py"], windows=False)


def test_a_wildcard_path_is_not_wider_than_its_directory() -> None:
    assert not authority_path_covered("auto_pm/**", ["auto_pm/core"], windows=False)
    assert authority_path_covered("auto_pm/core/**", ["auto_pm/core"], windows=False)


def test_overlap_detection_sees_a_wildcard_scope() -> None:
    assert _overlapping("auto_pm/core/**", "auto_pm/core/a.py", False)
    assert not _overlapping("auto_pm/core/**", "auto_pm/other/a.py", False)


def test_the_command_line_never_lets_click_expand_wildcards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_main(self: click.Group, *args: object, **kwargs: object) -> None:
        seen.update(kwargs)

    monkeypatch.setattr(click.Group, "main", fake_main)
    cli_main.cli.main(["--help"])
    assert seen["windows_expand_args"] is False


def test_an_explicit_choice_is_not_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setattr(click.Group, "main", lambda self, *a, **k: seen.update(k))
    cli_main.cli.main(["--help"], windows_expand_args=True)
    assert seen["windows_expand_args"] is True
