"""TD-SW008-237: the git facts that decide which paths are dirty must not be silently re-spelled when they do not decode."""

from __future__ import annotations

import click
import pytest

from auto_pm.ui.cli.continuity import _strict


def test_valid_bytes_decode_as_before() -> None:
    assert _strict("文件.py".encode(), "utf-8", "git diff") == "文件.py"
    assert _strict(b"abc123\n", "ascii", "git rev-parse HEAD") == "abc123\n"


def test_a_path_with_an_illegal_byte_stops_the_command_instead_of_becoming_a_question_mark() -> None:
    with pytest.raises(click.ClickException, match="无法按 utf-8 解码"):
        _strict(b"auto_pm/\xff\xfe.py\0", "utf-8", "git diff --name-only -z")


def test_a_non_ascii_head_is_refused() -> None:
    with pytest.raises(click.ClickException, match="ascii"):
        _strict("é".encode(), "ascii", "git rev-parse HEAD")
