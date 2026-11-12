"""TD-SW008-131 guard: a template must not carry a static file next to a ``.jinja`` file that renders to the same path (the ``.jinja`` version wins, so the static twin is a shadow).

The last known twins in ``plc-standard-project`` were removed with TD-SW008-575 (the four FB_1001 ones) and TD-SW008-501 (the two GlobalVars ones),
so the known set is now empty: any new shadow fails immediately.
"""

from __future__ import annotations

from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
KNOWN_SHADOWS: list[str] = []


def _jinja_files() -> list[Path]:
    return sorted(p for p in TEMPLATES_DIR.glob("*/template/**/*.jinja") if p.is_file())


def _shadows() -> list[str]:
    return sorted(p.with_suffix("").relative_to(TEMPLATES_DIR).as_posix() for p in _jinja_files() if p.with_suffix("").exists())


def test_the_templates_directory_has_jinja_files_to_check() -> None:
    assert len(_jinja_files()) >= 20


def test_the_set_of_static_twins_of_jinja_files_is_exactly_the_known_one() -> None:
    """A new shadow fails here; removing a known one must remove its entry (TD-SW008-131)."""
    assert _shadows() == KNOWN_SHADOWS


def test_every_known_shadow_still_has_its_jinja_twin_that_wins() -> None:
    for relative in KNOWN_SHADOWS:
        assert (TEMPLATES_DIR / relative).is_file() and (TEMPLATES_DIR / (relative + ".jinja")).is_file(), relative
