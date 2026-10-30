"""TD-SW008-214: the cockpit window heals a project's ledger only when that project's runtime identity is clean."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from auto_pm.ui import ledger_self_heal
from auto_pm.ui.ledger_self_heal import heal_project_ledgers

WINDOW_SOURCE = Path(ledger_self_heal.__file__).with_name("qml_main_window.py")


class _Reconciler:
    def __init__(self, fail_for: str = "") -> None:
        self.fixed: list[str] = []
        self._fail_for = fail_for

    def auto_fix(self, project_path: str) -> object:
        if project_path == self._fail_for:
            raise RuntimeError("boom")
        self.fixed.append(project_path)
        return None


def _resolver(monkeypatch: pytest.MonkeyPatch, conflicts: dict[str, object]) -> None:
    """``conflicts`` maps a project id to its conflict list, or to an exception to raise."""

    class _Service:
        def __init__(self, *_a: object, **_k: object) -> None: ...

        def resolve(self, project_id: str, start_path: object = None) -> object:
            outcome = conflicts[project_id]
            if isinstance(outcome, Exception):
                raise outcome
            return SimpleNamespace(conflicts=outcome)

    monkeypatch.setattr(ledger_self_heal, "WorkspaceContextService", _Service)


PROJECTS = [SimpleNamespace(project_id="P-1", path="/p1"), SimpleNamespace(project_id="P-2", path="/p2")]


def test_a_clean_identity_is_healed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _resolver(monkeypatch, {"P-1": [], "P-2": []})
    reconciler = _Reconciler()
    heal_project_ledgers(str(tmp_path), PROJECTS, reconciler, "启动")
    assert reconciler.fixed == ["/p1", "/p2"]


def test_a_conflict_or_an_unverifiable_identity_leaves_that_ledger_alone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _resolver(monkeypatch, {"P-1": ["版本不一致"], "P-2": RuntimeError("无登记")})
    reconciler = _Reconciler()
    heal_project_ledgers(str(tmp_path), PROJECTS, reconciler, "启动")
    assert reconciler.fixed == []
    err = capsys.readouterr().err
    assert "P-1" in err
    assert "版本不一致" in err
    assert "P-2" in err
    assert "无法核对" in err


def test_one_project_failing_does_not_stop_the_next(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _resolver(monkeypatch, {"P-1": [], "P-2": []})
    reconciler = _Reconciler(fail_for="/p1")
    heal_project_ledgers(str(tmp_path), PROJECTS, reconciler, "切换")
    assert reconciler.fixed == ["/p2"]


def test_the_window_has_no_unguarded_auto_fix() -> None:
    """Both call sites (startup and workspace switch) go through ``heal_project_ledgers``; a new bare call fails here."""

    assert ".auto_fix(" not in WINDOW_SOURCE.read_text(encoding="utf-8", errors="replace")
