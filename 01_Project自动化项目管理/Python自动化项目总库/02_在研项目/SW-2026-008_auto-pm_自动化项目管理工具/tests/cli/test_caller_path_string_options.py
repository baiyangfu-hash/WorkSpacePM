"""TD-SW008-253 (class sweep of TD-SW008-232): a path typed on the command line means "from where the user typed the command".

TD-232 moved every ``click.Path`` to ``CallerPath``.  What it left behind were options declared as plain strings (``-w``, ``--output``,
``--project-root`` ...): under the launcher the process sits in the release folder, so ``Path(value).resolve()`` landed there.  These tests
pin the sweep two ways: every path-like option of the real command tree is a ``CallerPath``, and the commands that consume them really
receive the caller's folder.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import click
import pytest
from click.testing import CliRunner

from auto_pm.app_context import AppContext
from auto_pm.ui.cli import delivery, spec
from auto_pm.ui.cli.__main__ import cli
from auto_pm.ui.cli.caller_path import CALLER_CWD_ENV, CallerPath, caller_cwd_default
from auto_pm.ui.cli.workflow import workflow_group

#: Option flags that name a folder or a file the user types a path for (``--output-format``, ``--root-work`` and the like do not match).
PATH_OPTION = re.compile(r"--(workspace|output|src|worktree|control-root|[a-z-]+-dir|[a-z-]+-root)$")

#: Path-like options that are deliberately not ``CallerPath`` (command path -> why).
NOT_A_CALLER_PATH = {
    "prototype bundle --output": "a file *name* placed in the project's prototype folder, never a location",
}


def _walk(command: click.Command, trail: tuple[str, ...] = ()) -> Iterator[tuple[str, click.Option]]:
    for param in command.params:
        if isinstance(param, click.Option):
            yield " ".join(trail), param
    if isinstance(command, click.Group):
        for name, child in command.commands.items():
            yield from _walk(child, (*trail, name))


def _path_options() -> list[tuple[str, str, click.Option]]:
    found = []
    for trail, option in _walk(cli):
        if not trail:  # the root group's -w / --control-root are anchored by hand in its callback (see the root tests below)
            continue
        for flag in option.opts:
            if PATH_OPTION.match(flag):
                found.append((trail, flag, option))
    return found


def test_the_scan_sees_the_options_this_sweep_fixed() -> None:
    """A regex that stopped matching would pass the next test vacuously."""

    seen = {f"{trail} {flag}" for trail, flag, _ in _path_options()}

    assert {
        "spec check --workspace",
        "spec report --output",
        "pm-session view --workspace",
        "delivery build --dist-dir",
        "plc ingest --src",
        "implementation-card create --worktree",
    } <= seen
    assert len(seen) >= 12


@pytest.mark.parametrize(("trail", "flag", "option"), _path_options(), ids=lambda v: v if isinstance(v, str) else "")
def test_every_path_like_option_anchors_to_the_caller_folder(trail: str, flag: str, option: click.Option) -> None:
    if f"{trail} {flag}" in NOT_A_CALLER_PATH:
        pytest.skip(NOT_A_CALLER_PATH[f"{trail} {flag}"])

    assert isinstance(option.type, CallerPath), (
        f"`{trail} {flag}` is a plain string option: started through the launcher a relative value would resolve against the release folder. "
        "Declare it with type=CallerPath(...) (or list it in NOT_A_CALLER_PATH with the reason)."
    )


def test_the_exemptions_still_exist() -> None:
    """A stale exemption would silently exempt a future option of the same name."""

    present = {f"{trail} {flag}" for trail, option in _walk(cli) for flag in option.opts}

    assert set(NOT_A_CALLER_PATH) <= present


@pytest.fixture
def launched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """What the launcher does: the process runs in the release folder, the user's folder is exported."""

    caller = tmp_path / "caller"
    caller.mkdir()
    release = tmp_path / "releases" / "1.3.3-aaaaaaa"
    release.mkdir(parents=True)
    monkeypatch.chdir(release)
    monkeypatch.setenv(CALLER_CWD_ENV, str(caller))
    return caller


def test_spec_workspace_option_reaches_the_command_as_the_caller_folder(launched: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (launched / "ws").mkdir()
    seen: list[Any] = []

    def spy(workspace: Any, ctx: Any = None) -> Path:
        seen.append(workspace)
        raise SystemExit(0)

    monkeypatch.setattr(spec, "_resolve_workspace", spy)

    # `spec check` asks the runtime-identity guard first when it can write; --no-fix keeps it a read.
    CliRunner().invoke(spec.spec_group, ["check", "-w", "ws"], obj=AppContext())

    assert seen == [str(launched / "ws")]


def test_spec_workspace_real_resolution_finds_the_caller_folder(launched: Path) -> None:
    (launched / "ws").mkdir()

    result = CliRunner().invoke(spec.spec_group, ["check", "-w", "no-such-folder"], obj=AppContext())

    assert str(launched / "no-such-folder") in result.output  # the message names the folder it looked in: the caller's, not the release's


def test_spec_report_output_is_checked_against_the_caller_folder(launched: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Any] = []

    def spy(ws: Path, output: str | None) -> bool:
        seen.append(output)
        raise SystemExit(0)

    monkeypatch.setattr(spec, "_resolve_workspace", lambda workspace, ctx=None: launched)
    monkeypatch.setattr(spec, "_report_lands_in_library", spy)

    CliRunner().invoke(spec.spec_group, ["report", "-o", "out/report.md"], obj=AppContext())

    assert seen == [str(launched / "out" / "report.md")]


def test_delivery_project_root_is_the_caller_folder(launched: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (launched / "proj").mkdir()
    roots: list[Any] = []

    class Spy:
        def __init__(self, root: Any) -> None:
            roots.append(root)

        def build(self, **_: Any) -> dict[str, Any]:
            return {"success": False, "message": "spy"}

    monkeypatch.setattr(delivery, "DeliveryService", Spy)
    monkeypatch.setattr(delivery, "require_runtime_identity_for_workspace", lambda ctx: None)

    CliRunner().invoke(delivery.delivery_group, ["build", "--version", "V9.9.9", "-p", "proj"], obj=AppContext())

    assert roots == [str(launched / "proj")]


def test_context_resolve_starts_from_the_caller_folder_by_default(launched: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``Path.cwd()`` would be the release folder, which is inside the workspace and belongs to no project."""

    from auto_pm.ui.cli import pm

    starts: list[Any] = []

    class Spy:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def resolve(self, project_id: str = "", start_path: Any = None) -> Any:
            starts.append(start_path)
            raise pm.WorkspaceContextError("spy")

    monkeypatch.setattr(pm, "WorkspaceContextService", Spy)

    CliRunner().invoke(pm.context_group, ["resolve"], obj=AppContext())
    CliRunner().invoke(pm.context_group, ["resolve", "--path", str(launched)], obj=AppContext())

    assert starts == [str(launched), str(launched)]


def test_context_resolve_keeps_the_process_folder_without_the_launcher(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from auto_pm.ui.cli import pm

    monkeypatch.delenv(CALLER_CWD_ENV, raising=False)
    starts: list[Any] = []

    class Spy:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def resolve(self, project_id: str = "", start_path: Any = None) -> Any:
            starts.append(start_path)
            raise pm.WorkspaceContextError("spy")

    monkeypatch.setattr(pm, "WorkspaceContextService", Spy)

    CliRunner().invoke(pm.context_group, ["resolve"], obj=AppContext())

    assert starts == [None]
    assert caller_cwd_default() is None


def test_workflow_commands_use_the_workspace_of_the_root_group(launched: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The old lookup read ``ctx.obj["workspace"]`` from an object that never has it, so ``-w`` was ignored."""

    from auto_pm.ui.cli import workflow

    roots: list[Any] = []

    class Spy:
        def __init__(self, root: Any) -> None:
            roots.append(root)
            raise SystemExit(0)

    monkeypatch.setattr(workflow, "WorkflowEngine", Spy)
    (launched / "ws").mkdir()

    CliRunner().invoke(cli, ["-w", "ws", "workflow", "list"])

    assert roots == [launched / "ws"]


def test_workflow_without_the_root_group_still_uses_the_process_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from auto_pm.ui.cli import workflow

    roots: list[Any] = []

    class Spy:
        def __init__(self, root: Any) -> None:
            roots.append(root)
            raise SystemExit(0)

    monkeypatch.setattr(workflow, "WorkflowEngine", Spy)
    monkeypatch.chdir(tmp_path)

    CliRunner().invoke(workflow_group, ["list"])

    assert roots == [Path.cwd()]
