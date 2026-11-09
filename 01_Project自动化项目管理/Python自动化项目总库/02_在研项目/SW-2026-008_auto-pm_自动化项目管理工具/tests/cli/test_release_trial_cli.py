"""D-05 A: ``release trial`` copies the active release outside the workspace and says how to try it."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner

from auto_pm.application.core.release_trial_service import POINTER_RELATIVE, RELEASES_RELATIVE
from auto_pm.ui.cli.release import release_group


def _workspace(root: Path) -> None:
    release = root / RELEASES_RELATIVE / "1.3.3-aaaaaaa" / "auto_pm"
    release.mkdir(parents=True)
    (release / "__init__.py").write_text("", encoding="utf-8")
    (root / POINTER_RELATIVE).write_text(
        json.dumps({"release_id": "1.3.3-aaaaaaa", "release_path": "1.3.3-aaaaaaa"}), encoding="utf-8"
    )


def _invoke(root: Path, *args: str):  # type: ignore[no-untyped-def]
    return CliRunner().invoke(release_group, list(args), obj=SimpleNamespace(control_root=str(root), workspace_root=str(root)))


def test_trial_copies_to_the_given_folder_and_prints_the_run_hint(tmp_path: Path) -> None:
    root, out = tmp_path / "ws", tmp_path / "out"
    root.mkdir()
    out.mkdir()
    _workspace(root)

    result = _invoke(root, "trial", "--dest-parent", str(out), "--json")

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["release_id"] == "1.3.3-aaaaaaa"
    assert Path(payload["destination"]).is_relative_to(out)
    assert (Path(payload["destination"]) / "auto_pm" / "__init__.py").is_file()
    assert "python -B" in payload["run_hint"]


def test_trial_refuses_a_folder_inside_the_workspace(tmp_path: Path) -> None:
    _workspace(tmp_path)
    inside = tmp_path / "scratch"
    inside.mkdir()

    result = _invoke(tmp_path, "trial", "--dest-parent", str(inside))

    assert result.exit_code != 0
    assert "工作区里面" in result.output
    assert not any(inside.iterdir())


def test_trial_without_a_release_pointer_says_so(tmp_path: Path) -> None:
    result = _invoke(tmp_path, "trial")

    assert result.exit_code != 0
    assert "指针" in result.output
