"""规范注册表是 PM 选规范来源的依据，读到坏字节要拒绝，不能悄悄换成替换符后当作有效来源。"""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_pm.application.core.pm_facade_service import PmFacadeError, PmFacadeService


def _facade(root: Path) -> PmFacadeService:
    facade = object.__new__(PmFacadeService)
    facade._workspace_root = root  # type: ignore[attr-defined]
    return facade


def test_spec_registry_with_a_bad_byte_is_rejected(tmp_path: Path) -> None:
    registry = tmp_path / "00_Obsidian_Base全局规范文件仓库" / "spec_registry.json"
    registry.parent.mkdir(parents=True)
    registry.write_bytes(b'{"specs": {"note": "\xff"}}')

    with pytest.raises(PmFacadeError, match="不是合法 UTF-8"):
        _facade(tmp_path)._effective_spec_sources()
