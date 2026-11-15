"""自动流程第一批（WBS 10.6）：``scripts/pm_flows.py`` 只串联现有命令，失败即停，改状态的步骤只停不跑。

用假的 runner 代替子进程，不真跑驾驶舱命令；控制根用临时目录。只读本项目目录里的文件。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

PROJECT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT / "scripts" / "pm_flows.py"
COMMANDS_MAP = PROJECT / "scripts" / "cockpit_board" / "flow" / "commands_map.json"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pm_flows_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def flows() -> ModuleType:
    return _load()


class FakeRunner:
    """记下每次调用；``fail`` 里的命令（main.py 后面的参数前缀）返回给定的退出码。"""

    def __init__(self, fail: dict[str, int] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail = fail or {}

    def __call__(self, command: list[str], **kwargs: Any) -> SimpleNamespace:
        self.calls.append({"command": command, **kwargs})
        tail = " ".join(command[3:])
        rc = next((code for prefix, code in self.fail.items() if tail.startswith(prefix)), 0)
        return SimpleNamespace(returncode=rc, stdout=f"ran {tail}\n", stderr="")

    def ran(self) -> list[str]:
        return [" ".join(call["command"][3:]) for call in self.calls]


def _root(
    tmp_path: Path, pid: str = "DJ-2026-005", project_root: str = "0100_PLC自动化/DJ-2026-005"
) -> Path:
    root = tmp_path / "root"
    (root / "SYS-2026-001_WorkspaceGovernance").mkdir(parents=True)
    (root / "main.py").write_text("", encoding="utf-8")
    registry = {"projects": [{"project_id": pid, "project_root": project_root}]}
    (root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json").write_text(
        json.dumps(registry), encoding="utf-8"
    )
    return root


def _map() -> dict[str, dict[str, Any]]:
    data: dict[str, dict[str, Any]] = json.loads(COMMANDS_MAP.read_text(encoding="utf-8"))[
        "commands"
    ]
    return data


def _leaf(step_args: tuple[str, ...], commands: dict[str, dict[str, Any]]) -> str:
    """一步的参数对应 commands_map 里的哪条命令（最长前缀）。"""
    words = [arg for arg in step_args if not arg.startswith("-")]
    for size in range(len(words), 0, -1):
        if " ".join(words[:size]) in commands:
            return " ".join(words[:size])
    raise AssertionError(f"{step_args} 不是登记过的命令")


def test_every_main_py_step_is_a_registered_command(flows: ModuleType) -> None:
    commands = _map()
    for steps in flows.FLOWS.values():
        for step in steps:
            if not step.args[0].startswith("{"):
                _leaf(step.args, commands)


def test_steps_the_script_runs_are_read_only(flows: ModuleType) -> None:
    commands = _map()
    for name, steps in flows.FLOWS.items():
        for step in steps:
            if step.kind != "run" or step.args[0].startswith("{"):
                continue
            leaf = _leaf(step.args, commands)
            entry = commands[leaf]
            assert entry["class"] == "read" or leaf in flows.READ_BY_CODE, (
                f"{name}：{leaf} 会写，不能由脚本跑"
            )
            assert not set(entry.get("write_flags") or []) & set(step.args), (
                f"{name}：{leaf} 带了写开关"
            )
            assert "--fix" not in step.args and "--apply" not in step.args


def test_every_state_changing_closeout_step_is_a_stop(flows: ModuleType) -> None:
    commands = _map()
    for step in flows.CLOSEOUT:
        if step.args[0].startswith("{"):
            continue
        leaf = _leaf(step.args, commands)
        if commands[leaf]["class"] != "read" and leaf not in flows.READ_BY_CODE:
            assert step.kind == "stop", f"{leaf} 会改状态，必须是停点"
            assert step.who, f"{leaf} 停点要写明谁来做"
    transition = next(step for step in flows.CLOSEOUT if step.key == "transition")
    assert (
        transition.kind == "stop"
        and "只有用户本人" in transition.who
        and "永远不执行" in transition.who
    )
    assert all(step.kind == "run" for step in flows.CHECKUP), "项目体检全程只读，不该有停点"


def test_checkup_runs_every_step_in_order_and_writes_a_record(
    flows: ModuleType, tmp_path: Path
) -> None:
    root = _root(tmp_path)
    runner = FakeRunner()
    lines: list[str] = []

    assert flows.run_flow("checkup", "DJ-2026-005", root=root, runner=runner, out=lines.append) == 0

    ran = runner.ran()
    assert ran[:8] == [
        "pm orient DJ-2026-005",
        "pm control-root-status DJ-2026-005",
        "pm missions --pid DJ-2026-005",
        "ledger reconcile DJ-2026-005",
        "plc check DJ-2026-005",
        "doc check",
        "plc docs check DJ-2026-005",
        "prototype check --pid DJ-2026-005",
    ]
    assert runner.calls[-2]["command"][2].endswith("plan_status.py")
    assert runner.calls[-2]["command"][3:] == ["DJ-2026-005", "--root", str(root)]
    assert runner.calls[-1]["command"][2].endswith("command_catalog.py")
    assert runner.calls[-1]["command"][3:] == ["--print"]
    for call in runner.calls:
        assert "shell" not in call and call["cwd"] == str(root)
        assert call["command"][0] == str(flows.resolve_python(root))
    records = list((root / ".auto-pm" / "reports" / "flows").glob("*_checkup_DJ-2026-005.json"))
    assert len(records) == 1
    record = json.loads(records[0].read_text(encoding="utf-8"))
    assert record["result"] == "走完，全过" and record["pid"] == "DJ-2026-005"
    assert [step["rc"] for step in record["steps"]] == [0] * 10
    assert record["steps"][0]["command"].endswith("main.py pm orient DJ-2026-005")
    assert Path(record["catalog"]).is_file()


def test_checkup_skips_plc_steps_on_other_projects(flows: ModuleType, tmp_path: Path) -> None:
    root = _root(
        tmp_path,
        "SW-2026-009",
        "01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-009_x",
    )
    runner = FakeRunner()
    lines: list[str] = []

    assert flows.run_flow("checkup", "SW-2026-009", root=root, runner=runner, out=lines.append) == 0

    assert not [call for call in runner.ran() if call.startswith(("plc ", "prototype "))]
    assert any("跳过（不是 PLC 项目）" in line for line in lines)


def test_checkup_runs_every_step_even_after_a_red_one_and_sums_up(
    flows: ModuleType, tmp_path: Path
) -> None:
    root = _root(tmp_path)
    runner = FakeRunner(fail={"ledger reconcile": 2, "plc check": 1})
    lines: list[str] = []

    assert flows.run_flow("checkup", "DJ-2026-005", root=root, runner=runner, out=lines.append) == 1

    assert len(runner.calls) == 10, "体检一步红了也要跑完十步"
    text = "\n".join(lines)
    assert "小结" in text
    assert "| 4 | 对账 | 红 |" in text and "ledger reconcile DJ-2026-005 | 2 |" in text
    assert "| 5 | 程序检查 | 红 |" in text and "plc check DJ-2026-005 | 1 |" in text
    assert "有 2 步红：第 4 步「对账」、第 5 步「程序检查」" in text
    record = json.loads(
        next((root / ".auto-pm" / "reports" / "flows").glob("*.json")).read_text(encoding="utf-8")
    )
    assert record["result"] == "走完，有红"
    assert [step["status"] for step in record["steps"]][3:5] == ["红", "红"]


def test_closeout_stops_at_the_first_red_step_and_names_the_command(
    flows: ModuleType, tmp_path: Path
) -> None:
    root = _root(tmp_path)
    runner = FakeRunner(fail={"pm acceptance-scan": 1})
    lines: list[str] = []

    assert (
        flows.run_flow(
            "closeout",
            "DJ-2026-005",
            root=root,
            mission="MISSION-ABC123",
            runner=runner,
            out=lines.append,
        )
        == 1
    )

    assert runner.ran() == ["pm acceptance-scan --pid DJ-2026-005"]
    assert any(
        "停在第 1 步「验收命令预检」" in line
        and "pm acceptance-scan --pid DJ-2026-005" in line
        and "退出码 1" in line
        for line in lines
    )
    record = json.loads(
        next((root / ".auto-pm" / "reports" / "flows").glob("*.json")).read_text(encoding="utf-8")
    )
    assert record["result"] == "失败"
    assert record["stopped_at"]["rc"] == 1
    assert record["stopped_at"]["failed_command"].endswith("pm acceptance-scan --pid DJ-2026-005")


@pytest.mark.parametrize(
    ("flow", "pid", "mission"),
    [
        ("checkup", "--fix", ""),
        ("checkup", "DJ-2026-005 --fix", ""),
        ("checkup", "dj-2026-005", ""),
        ("closeout", "--fix", "MISSION-ABC123"),
        ("closeout", "DJ-2026-005", "--fix"),
        ("closeout", "DJ-2026-005", ""),
    ],
)
def test_a_malformed_project_or_mission_id_runs_nothing(
    flows: ModuleType, tmp_path: Path, flow: str, pid: str, mission: str
) -> None:
    runner = FakeRunner()
    lines: list[str] = []
    assert (
        flows.run_flow(
            flow, pid, root=_root(tmp_path), mission=mission, runner=runner, out=lines.append
        )
        == 2
    )
    assert runner.calls == []
    assert "格式不对" in lines[0] and "一条命令都没跑" in lines[0]


def test_the_command_line_rejects_a_switch_smuggled_in_as_the_project_id(
    flows: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(flows.subprocess, "run", lambda *a, **k: calls.append(a))
    root = _root(tmp_path)
    code = flows.main(
        [
            "--root",
            str(root),
            "closeout",
            "--mission-id",
            "MISSION-ABC123",
            "--done",
            "transition",
            "--",
            "--fix",
        ]
    )
    assert code == 2 and calls == []
    assert "项目号格式不对" in capsys.readouterr().out


def test_closeout_never_runs_a_state_changing_command(flows: ModuleType, tmp_path: Path) -> None:
    root = _root(tmp_path)
    runner = FakeRunner()
    stops = [step.key for step in flows.CLOSEOUT if step.kind == "stop"]
    for done in ["", *stops]:
        lines: list[str] = []
        assert (
            flows.run_flow(
                "closeout",
                "DJ-2026-005",
                root=root,
                mission="MISSION-ABC123",
                done=done,
                runner=runner,
                out=lines.append,
            )
            == 0
        )
    ran = runner.ran()
    for forbidden in (
        "pm verify ",
        "pm accept ",
        "pm close ",
        "change transition ",
        "worktree close ",
    ):
        assert not [call for call in ran if call.startswith(forbidden)], forbidden
    assert ran == [
        "pm acceptance-scan --pid DJ-2026-005",
        "pm control-root-status DJ-2026-005",
        "pm missions --pid DJ-2026-005",
        "pr settle-scan DJ-2026-005",
        "ledger reconcile DJ-2026-005",
    ]


def test_closeout_stop_prints_the_command_and_the_words_for_the_user(
    flows: ModuleType, tmp_path: Path
) -> None:
    root = _root(tmp_path)
    lines: list[str] = []

    assert (
        flows.run_flow(
            "closeout",
            "DJ-2026-005",
            root=root,
            mission="MISSION-ABC123",
            done="close",
            runner=FakeRunner(),
            out=lines.append,
        )
        == 0
    )

    text = "\n".join(lines)
    assert "第 8 步「变更单推到完成」会改状态" in text
    assert "只有用户本人；本脚本永远不执行这一步" in text
    assert "change transition" in text and "--to completed --pid DJ-2026-005" in text
    record = json.loads(
        next((root / ".auto-pm" / "reports" / "flows").glob("*.json")).read_text(encoding="utf-8")
    )
    assert record["result"] == "停在停点" and record["stopped_at"]["key"] == "transition"
    assert record["stopped_at"]["resume"] == "做完后带 --done transition 再运行本流程"


def test_done_only_accepts_stop_points(flows: ModuleType, tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="--done 只认这些停点"):
        flows.run_flow(
            "closeout",
            "DJ-2026-005",
            root=_root(tmp_path),
            mission="MISSION-ABC123",
            done="settle_scan",
            runner=FakeRunner(),
        )


def test_no_main_py_is_a_usage_error(flows: ModuleType, tmp_path: Path) -> None:
    lines: list[str] = []
    assert (
        flows.run_flow(
            "checkup", "DJ-2026-005", root=tmp_path, runner=FakeRunner(), out=lines.append
        )
        == 2
    )
    assert "控制根里没有 main.py" in lines[0]


@pytest.mark.parametrize(
    ("os_name", "relative"),
    [("nt", ".venv/Scripts/python.exe"), ("posix", ".venv/bin/python")],
)
def test_python_comes_from_the_control_root_venv_like_the_board_bat(
    flows: ModuleType, tmp_path: Path, os_name: str, relative: str
) -> None:
    venv_python = tmp_path / relative
    assert flows.resolve_python(tmp_path, os_name) == Path(sys.executable), (
        "没有 .venv 时用运行本脚本的 Python"
    )
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("", encoding="utf-8")
    assert flows.resolve_python(tmp_path, os_name) == venv_python


@pytest.mark.skipif(sys.platform != "win32", reason="只在 Windows 上核真实的 os.name 分支")
def test_on_windows_the_venv_scripts_python_is_used(flows: ModuleType, tmp_path: Path) -> None:
    venv_python = tmp_path / ".venv" / "Scripts" / "python.exe"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("", encoding="utf-8")
    assert flows.resolve_python(tmp_path) == venv_python
    assert flows.command_of(flows.CHECKUP[0], venv_python, tmp_path, "P", "")[:3] == [
        str(venv_python),
        "-B",
        str(tmp_path / "main.py"),
    ]


def test_no_step_calls_a_bare_python_or_a_shell(flows: ModuleType) -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "shell=True" not in source
    assert '"python"' not in source and "'python'" not in source
