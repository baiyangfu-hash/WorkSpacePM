"""TD-SW008-214: handoff.v1 commands - writes refuse a runtime-identity conflict, recovery commands only warn, reads ask nothing."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import click
import pytest
from click.testing import CliRunner

from auto_pm.application.core.ai_handoff_service import AiHandoffService
from auto_pm.ui.cli import handoff as handoff_cli
from auto_pm.ui.cli.handoff import handoff_group

# (argv, service method it must not reach after a refusal)
WRITES: dict[str, tuple[list[str], str]] = {
    "create": (
        ["create", "--pid", "P-1", "--to", "plc-electrical-engineer", "--summary", "s"],
        "create_request",
    ),
    "claim": (["claim", "REQ-1", "--executor-id", "e"], "claim_request"),
    "start": (["start", "REQ-1", "--executor-id", "e"], "start_request"),
    "heartbeat": (["heartbeat", "REQ-1", "--executor-id", "e"], "heartbeat_request"),
    "fail": (["fail", "REQ-1", "--executor-id", "e", "--reason", "r"], "fail_request"),
    "close": (["close", "REQ-1"], "close_request"),
    "result-submit": (
        ["result-submit", "REQ-1", "--executor-id", "e", "--result-file", "r.json"],
        "submit_result",
    ),
}
# Recovery: they mend a stuck request, so a conflict only warns.
RECOVERY: dict[str, tuple[list[str], str]] = {
    "requeue": (["requeue", "REQ-1", "--pm-id", "pm", "--reason", "r"], "requeue_request"),
    "timeout": (["timeout", "--pid", "P-1"], "expire_stale_requests"),
    "saga resume": (["saga", "resume", "REQ-1"], "resume_saga"),
    "saga compensate": (["saga", "compensate", "REQ-1"], "compensate_saga"),
}
READS = {"failures", "list", "preflight", "queue", "show", "saga status"}


def _all_names() -> set[str]:
    names: set[str] = set()
    for name, command in handoff_group.commands.items():
        if isinstance(command, click.Group):
            names.update(f"{name} {sub}" for sub in command.commands)
        else:
            names.add(name)
    return names


def test_every_handoff_command_is_classified() -> None:
    """A new command fails here until someone decides whether it needs the identity guard."""

    assert _all_names() == set(WRITES) | set(RECOVERY) | READS


@pytest.fixture
def seen(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, list[Any]]:
    record: dict[str, list[Any]] = {"required": [], "warned": [], "service": []}

    def refuse(_ctx: click.Context, project: str) -> None:
        record["required"].append(project)
        raise click.ClickException("运行身份未通过校验，已拒绝写入：测试")

    def warn(_ctx: click.Context, project: object) -> None:
        record["warned"].append(project() if callable(project) else project)

    monkeypatch.setattr(handoff_cli, "require_runtime_identity", refuse)
    monkeypatch.setattr(handoff_cli, "warn_runtime_identity", warn)
    monkeypatch.setattr(
        AiHandoffService,
        "get_request",
        lambda _self, _rid: {"request_id": "REQ-1", "project_id": "P-1"},
    )
    for method in {m for _, m in WRITES.values()} | {m for _, m in RECOVERY.values()}:

        def reached(_self: object, *_a: object, _m: str = method, **_k: object) -> dict[str, Any]:
            record["service"].append(_m)
            return {"request_id": "REQ-1", "saga_id": "S", "status": "ok"}

        monkeypatch.setattr(AiHandoffService, method, reached)
    return record


def _invoke(tmp_path: Path, argv: list[str]) -> Any:
    return CliRunner().invoke(
        handoff_group, argv, obj=SimpleNamespace(control_root=tmp_path, workspace_root=tmp_path)
    )


@pytest.mark.parametrize("name", sorted(WRITES))
def test_a_handoff_write_is_refused_before_it_writes(
    name: str, seen: dict[str, list[Any]], tmp_path: Path
) -> None:
    argv, _method = WRITES[name]
    result = _invoke(tmp_path, argv)
    assert result.exit_code != 0
    assert "已拒绝写入" in result.output
    assert seen["required"] == ["P-1"]
    assert seen["service"] == []


def test_a_write_on_a_request_that_does_not_exist_is_left_to_the_command_to_report(
    seen: dict[str, list[Any]], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(AiHandoffService, "get_request", lambda _self, _rid: None)
    result = _invoke(tmp_path, ["start", "REQ-1", "--executor-id", "e"])
    assert seen["required"] == []  # nothing to check: the request has no project
    assert "已拒绝写入" not in result.output


@pytest.mark.parametrize("name", sorted(RECOVERY))
def test_a_handoff_recovery_command_warns_and_still_runs(
    name: str, seen: dict[str, list[Any]], tmp_path: Path
) -> None:
    argv, method = RECOVERY[name]
    result = _invoke(tmp_path, argv)
    assert result.exit_code == 0, result.output
    assert seen["warned"] == ["P-1"]
    assert seen["required"] == []
    assert seen["service"] == [method]


@pytest.mark.parametrize(
    "argv",
    [["show", "REQ-1"], ["list"], ["queue"], ["saga", "status", "REQ-1"], ["failures", "REQ-1"]],
)
def test_handoff_reads_ask_the_guard_nothing(
    argv: list[str], seen: dict[str, list[Any]], tmp_path: Path
) -> None:
    _invoke(tmp_path, argv)
    assert seen["required"] == [] and seen["warned"] == []


REQUEST_ID = "AI-20261101-F494"
# every write command that asks the guard through ``_require_identity_for_request`` (``create`` has no request yet)
GUARDED_BY_REQUEST = {
    "claim": ["claim", REQUEST_ID, "--executor-id", "e"],
    "start": ["start", REQUEST_ID, "--executor-id", "e"],
    "heartbeat": ["heartbeat", REQUEST_ID, "--executor-id", "e"],
    "fail": ["fail", REQUEST_ID, "--executor-id", "e", "--reason", "r"],
    "close": ["close", REQUEST_ID],
    "result-submit": ["result-submit", REQUEST_ID, "--executor-id", "e", "--result-file", "result.json"],
}


def test_the_damaged_request_test_covers_every_command_guarded_by_request() -> None:
    assert set(GUARDED_BY_REQUEST) == set(WRITES) - {"create"}


@pytest.mark.parametrize("command", sorted(GUARDED_BY_REQUEST))
@pytest.mark.parametrize("damage", ["no-project-id", "not-json"])
def test_the_guard_lets_an_unreadable_request_through_only_because_the_write_fails_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str, command: str
) -> None:
    """Audit 494 f: ``_require_identity_for_request`` fails open when the request cannot be read or has no project id.

    That is safe only while the write path reads the request through the same validation and refuses it.  This runs the real
    service on a damaged request file, for each guarded write command: the guard is not asked, and the command still fails
    (not as a usage error) with the request file untouched.  If a write path ever stops refusing such a request, this goes red
    and the guard must be made to refuse instead.
    """
    asked: list[str] = []
    monkeypatch.setattr(handoff_cli, "require_runtime_identity", lambda _ctx, project: asked.append(project))
    service = AiHandoffService(tmp_path)
    service.create_request("P-1", "fullstack-engineer", "s", request_id=REQUEST_ID)
    path = service._find_request_path(REQUEST_ID)
    if damage == "no-project-id":
        good = service.get_request(REQUEST_ID)
        assert good is not None
        payload = {key: value for key, value in good.items() if key not in {"project_id", "file"}}
        path.write_text(json.dumps(payload), encoding="utf-8")
    else:
        path.write_text("{ not json", encoding="utf-8")
    (tmp_path / "result.json").write_text("{}", encoding="utf-8")
    before = path.read_bytes()

    result = _invoke(tmp_path, GUARDED_BY_REQUEST[command])

    assert asked == []  # nothing to check: the request has no readable project
    assert result.exit_code not in (0, 2), result.output  # the write itself refuses it, and it is not a usage error
    assert path.read_bytes() == before
