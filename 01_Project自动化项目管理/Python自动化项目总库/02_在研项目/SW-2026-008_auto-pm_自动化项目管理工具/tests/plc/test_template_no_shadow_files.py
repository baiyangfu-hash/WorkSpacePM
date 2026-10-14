"""TD-SW008-131 guard: a template must not carry a static file next to a ``.jinja`` file that renders to the same path (the ``.jinja`` version wins, so the static twin is a shadow).

Nine such twins exist today in ``plc-standard-project`` (the OB1 and FB_1001 twins drifted apart there before). Removing them needs a tool that can delete paths in a governed card
(the card toolkit only modifies and adds) and is tracked in TD-SW008-131; until then this test pins the set, so a *new* shadow fails immediately and removing the known ones must
update the list (a stale entry fails too).
"""

from __future__ import annotations

from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
BASE = "plc-standard-project/template/02_PLC程序/PLC_ST/"
KNOWN_SHADOWS = sorted(BASE + p for p in (
    "00_主程序/OB1.scl",
    "00_全局数据/GlobalVars.db",
    "00_全局数据/PRD/变更记录_CHG-GlobalVars.md",
    "00_全局数据/PRD/接口文档_IFC-GlobalVars.md",
    "02_工位1_动作机构/FB_1001_Station1.scl",
    "02_工位1_动作机构/PRD/使用说明_UM-FB1001-Station1.md",
    "02_工位1_动作机构/PRD/变更记录_CHG-FB1001-Station1.md",
    "02_工位1_动作机构/PRD/接口文档_IFC-FB1001-Station1.md",
    "02_工位1_动作机构/PRD/详细设计说明书_DSN-FB1001-Station1.md",
))


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
