"""规范注册表是 PM 选规范来源的依据，读到坏字节要拒绝，不能悄悄换成替换符后当作有效来源。"""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_pm.application.core.pm_facade_service import PmFacadeError, PmFacadeService


def _facade(root: Path) -> PmFacadeService:
    facade = object.__new__(PmFacadeService)
    facade._workspace_root = root
    return facade


def test_spec_registry_with_a_bad_byte_is_rejected(tmp_path: Path) -> None:
    registry = tmp_path / "00_Obsidian_Base全局规范文件仓库" / "spec_registry.json"
    registry.parent.mkdir(parents=True)
    registry.write_bytes(b'{"specs": {"note": "\xff"}}')

    with pytest.raises(PmFacadeError, match="不是合法 UTF-8"):
        _facade(tmp_path)._effective_spec_sources()


# ── TD-SW008-568（D-303）：范围卡按项目技术栈挑规范，不改规范库 ─────────────

import json  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from auto_pm.application.core.workspace_context_service import (  # noqa: E402
    WorkspaceContextError,
    WorkspaceContextService,
)
from auto_pm.contracts.pm_facade import PmIntent  # noqa: E402

_SPECS = {"DEV-300": "python", "DEV-210": "python", "LSP-905": "plc", "STD-830": "plc"}


def _registry(root: Path) -> None:
    base = root / "00_Obsidian_Base全局规范文件仓库"
    base.mkdir(parents=True)
    specs = {}
    for spec_id, domain in _SPECS.items():
        (base / f"{spec_id}.md").write_text("# x\n", encoding="utf-8")
        specs[spec_id] = {"domain": domain, "lifecycle": "stable", "version": "V1",
                          "canonical_path": f"00_Obsidian_Base全局规范文件仓库/{spec_id}.md"}
    (base / "spec_registry.json").write_text(json.dumps({"specs": specs}), encoding="utf-8")


def _stack_is(monkeypatch: pytest.MonkeyPatch, stack: str | None) -> None:
    def resolve(self: object, project_id: str = "", start_path: object = None) -> object:
        if stack is None:
            raise WorkspaceContextError("没登记")
        return SimpleNamespace(subject=SimpleNamespace(stack=stack))

    monkeypatch.setattr(WorkspaceContextService, "resolve", resolve)


@pytest.mark.parametrize(
    ("stack", "expected"),
    [("python", {"DEV-300", "DEV-210"}), ("plc", {"LSP-905", "STD-830"}),
     ("unknown", set(_SPECS)), (None, set(_SPECS))],
)
def test_the_card_binds_only_the_specs_of_the_project_stack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stack: str | None, expected: set[str]
) -> None:
    _registry(tmp_path)
    _stack_is(monkeypatch, stack)
    facade = _facade(tmp_path)
    bound: list[tuple[str, tuple[tuple[str, str, str], ...]]] = []
    def bind(request_id: str, specs: tuple[tuple[str, str, str], ...]) -> tuple[tuple[str, str, str], ...]:
        bound.append((request_id, specs))
        return specs

    facade._store = SimpleNamespace(bind_planning_draft_specs=bind)  # type: ignore[assignment]
    monkeypatch.setattr(PmFacadeService, "create_planning_draft", lambda self, intent: SimpleNamespace(request_id="R-1"))
    intent = PmIntent(request_id="R-1", subject_project_id="SW-2026-952", objective="o", acceptance_criteria=("a",))
    got = facade.bind_planning_draft_specs(intent)
    assert {spec_id for spec_id, _, _ in got} == expected
    assert bound[0][0] == "R-1"


def test_a_python_project_needs_only_python_specs_in_the_registry(tmp_path: Path) -> None:
    _registry(tmp_path)
    registry = tmp_path / "00_Obsidian_Base全局规范文件仓库" / "spec_registry.json"
    payload = json.loads(registry.read_text(encoding="utf-8"))
    payload["specs"] = {k: v for k, v in payload["specs"].items() if v["domain"] == "python"}
    registry.write_text(json.dumps(payload), encoding="utf-8")
    assert len(_facade(tmp_path)._effective_spec_sources(frozenset({"python"}))) == 2
    with pytest.raises(PmFacadeError, match="缺少有效领域: plc"):
        _facade(tmp_path)._effective_spec_sources()
