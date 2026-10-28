"""TD-SW008-214: ``continuity`` write commands refuse a runtime-identity conflict; recovery commands only warn.

Recovery commands (reclaim, fence, settle, adjudicate, revoke) are what repairs a broken runtime, so refusing them would
lock the repair path: they report the conflict on stderr and still run.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

from auto_pm.ui.cli import continuity
from auto_pm.ui.cli.__main__ import cli

# Refused on a conflict: the command and the project it must hand the guard ("X" = the dummy --pid value).
GUARDED = {
    "mission create": "X",
    "mission transition": "P-MISSION",
    "work create": "X",
    "work authorize": "P-WORK",
    "work transition": "P-WORK",
    "work relate": "P-WORK",
    "orchestration report-finding": "X",
    "orchestration report-repair": "P-MISSION",
    "run start": "P-WORK",
    "run transition": "P-RUN",
    "dispatch prepare": "P-WORK",
    "checkpoint create": "P-RUN",
    "handoff create": "P-CHECKPOINT",
    "handoff accept": "P-HANDOFF",
}
# Never refused (they repair a broken runtime, or keep a lease alive); a conflict is only warned about.
RECOVERY = {
    "work adjudicate": "P-WORK",
    "run settle-expired": "P-RUN",
    "run fence-terminal-lease": "P-RUN",
    "run reconcile-terminal-lease": "P-RUN",
    "run fence-legacy-terminal": "P-RUN",
    "run revoke-unstarted": "P-RUN",
    "run reclaim": "P-RUN",
    "lease renew": "P-RUN",
    "lease record-holder": "P-RUN",
}
# Reads, or ledger-level backup commands that belong to no single project.
EXEMPT = frozenset(
    {
        "backup",
        "list-backups",
        "restore-backup",
        "verify-backup",
        "mission show",
        "work adjudication-evidence",
        "run legacy-terminal-evidence",
    }
)


def _continuity_group() -> click.Group:
    group = cli.commands["continuity"]
    assert isinstance(group, click.Group)
    return group


def _walk(group: click.Group, prefix: str = "") -> dict[str, click.Command]:
    found: dict[str, click.Command] = {}
    for name, command in sorted(group.commands.items()):
        if isinstance(command, click.Group):
            found.update(_walk(command, f"{prefix}{name} "))
        else:
            found[f"{prefix}{name}"] = command
    return found


def test_every_continuity_command_is_classified() -> None:
    """A new command fails here until someone decides whether it needs the identity guard."""

    found = set(_walk(_continuity_group()))
    assert found == set(GUARDED) | set(RECOVERY) | EXEMPT
    assert not (set(GUARDED) & set(RECOVERY)) and not ((set(GUARDED) | set(RECOVERY)) & EXEMPT)


# Options a command needs beyond the required ones to get past its own usage checks.
EXTRA_ARGS = {"lease renew": ["--lease-wallet"]}


def _required_args(command: click.Command) -> list[str]:
    """The smallest argument list that reaches the command body: every required option with a dummy value."""

    args: list[str] = []
    for param in command.params:
        if not isinstance(param, click.Option) or not param.required:
            continue
        flag = param.opts[0]
        if param.is_flag:
            args.append(flag)
        elif isinstance(param.type, click.Choice):
            args.extend([flag, param.type.choices[0]])
        elif isinstance(param.type, click.IntRange):
            args.extend([flag, str(param.type.min or 1)])
        else:
            args.extend([flag, "X"])
    return args


class _Untouchable:
    def __init__(self, touched: list[str], label: str) -> None:
        self._touched = touched
        self._label = label

    def __getattr__(self, name: str) -> object:
        self._touched.append(f"{self._label}.{name}")
        raise RuntimeError(f"写入路径被使用: {self._label}.{name}")


def _invoke(command: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, refuse: bool) -> tuple[object, list[str], list[str]]:
    asked: list[str] = []
    touched: list[str] = []
    cmd = _walk(_continuity_group())[command]

    def require(_ctx: click.Context, project: str) -> None:
        asked.append(project)
        if refuse:
            raise click.ClickException("运行身份未通过校验，已拒绝写入：测试")

    def warn(_ctx: click.Context, project: object) -> None:
        asked.append(project() if callable(project) else project)

    monkeypatch.setattr(continuity, "require_runtime_identity", require)
    monkeypatch.setattr(continuity, "warn_runtime_identity", warn)
    for name, project in (
        ("project_of_mission", "P-MISSION"),
        ("project_of_work", "P-WORK"),
        ("project_of_run", "P-RUN"),
        ("project_of_checkpoint", "P-CHECKPOINT"),
        ("project_of_handoff", "P-HANDOFF"),
    ):
        monkeypatch.setattr(continuity, name, lambda _ctx, _id, _p=project: _p)
    monkeypatch.setattr(continuity, "_lease_token", lambda *_a, **_k: "T")
    monkeypatch.setattr(continuity, "_read_stdin_text", lambda: "T")
    for name in ("_work_service", "_execution_service", "_handover", "_dispatch_service", "_mission_service", "_orchestrator", "_require_mutation_root"):
        monkeypatch.setattr(continuity, name, lambda *_a, _n=name, **_k: _Untouchable(touched, _n))
    result = CliRunner().invoke(
        cmd, [*_required_args(cmd), *EXTRA_ARGS.get(command, [])], obj=SimpleNamespace(control_root=tmp_path, workspace_root=tmp_path), standalone_mode=False
    )
    return result, asked, touched


@pytest.mark.parametrize("command", sorted(GUARDED))
def test_a_refused_identity_stops_a_guarded_command_before_it_writes(
    command: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result, asked, touched = _invoke(command, monkeypatch, tmp_path, refuse=True)

    assert asked == [GUARDED[command]]
    assert touched == []
    assert isinstance(result.exception, click.ClickException)  # type: ignore[attr-defined]


@pytest.mark.parametrize("command", sorted(RECOVERY))
def test_a_recovery_command_is_never_refused_by_the_identity(
    command: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result, asked, touched = _invoke(command, monkeypatch, tmp_path, refuse=True)

    assert asked == [RECOVERY[command]]
    # it went on to use the service: the identity did not stop it
    assert touched, f"{command} did not reach its service"
    assert not isinstance(result.exception, click.ClickException)  # type: ignore[attr-defined]


def test_the_warning_reports_a_conflict_on_stderr_and_does_not_raise(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from auto_pm.ui.cli import runtime_identity_guard as guard

    class _Service:
        def __init__(self, *_a: object, **_k: object) -> None: ...

        def resolve(self, **_k: object) -> SimpleNamespace:
            return SimpleNamespace(conflicts=("发布指针与载入包不一致",))

    monkeypatch.setattr(guard, "WorkspaceContextService", _Service)
    ctx = click.Context(click.Command("x"), obj=SimpleNamespace(control_root=tmp_path, workspace_root=tmp_path))
    guard.warn_runtime_identity(ctx, "P-1")
    assert "发布指针与载入包不一致" in capsys.readouterr().err


def test_an_unresolvable_project_only_warns(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from auto_pm.ui.cli import runtime_identity_guard as guard

    def lookup() -> str:
        raise click.ClickException("Run 不存在")

    ctx = click.Context(click.Command("x"), obj=SimpleNamespace(control_root=tmp_path, workspace_root=tmp_path))
    guard.warn_runtime_identity(ctx, lookup)
    assert "无法核对" in capsys.readouterr().err
