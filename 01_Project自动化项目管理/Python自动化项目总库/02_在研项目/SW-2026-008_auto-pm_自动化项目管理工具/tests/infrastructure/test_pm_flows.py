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


def _set_mode(root: Path, mode: str) -> Path:
    folder = root / ".auto-pm" / "reports" / "local_merge"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "github_mode.json").write_text(
        json.dumps({"mode": mode}, ensure_ascii=False), encoding="utf-8"
    )
    return root


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
    assert runner.calls[-3]["command"][2].endswith("plan_status.py")
    assert runner.calls[-3]["command"][3:] == ["DJ-2026-005", "--root", str(root)]
    assert runner.calls[-2]["command"][2].endswith("command_catalog.py")
    assert runner.calls[-2]["command"][3:] == ["--print"]
    assert runner.calls[-1]["command"][2].endswith("pm_merge.py"), "本机合并对账（卡 311）"
    assert runner.calls[-1]["command"][3:] == ["--root", str(root), "verify-log"]
    for call in runner.calls:
        assert "shell" not in call and call["cwd"] == str(root)
        assert call["command"][0] == str(flows.resolve_python(root))
    records = list((root / ".auto-pm" / "reports" / "flows").glob("*_checkup_DJ-2026-005.json"))
    assert len(records) == 1
    record = json.loads(records[0].read_text(encoding="utf-8"))
    assert record["result"] == "走完，全过" and record["pid"] == "DJ-2026-005"
    assert [step["rc"] for step in record["steps"]] == [0] * 11 + [None]
    assert record["steps"][-1]["key"] == "root_clean" and record["steps"][-1]["status"] == "通过"
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

    assert len(runner.calls) == 11, "体检一步红了也要跑完十一步"
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
        assert flows.run_flow(
            "closeout",
            "DJ-2026-005",
            root=root,
            mission="MISSION-ABC123",
            done=done,
            runner=runner,
            out=lines.append,
        ) == (0 if done == stops[-1] else 3), done
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
        == 3
    ), "停在停点退出 3，和走完的 0 区分开"

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
    """--done 写错停点名是用法错：退出 2，说清只认哪些停点，一条命令都不跑。"""
    root = _root(tmp_path)
    runner = FakeRunner()
    lines: list[str] = []
    for wrong in ("settle_scan", "acept"):
        assert (
            flows.run_flow(
                "closeout",
                "DJ-2026-005",
                root=root,
                mission="MISSION-ABC123",
                done=wrong,
                runner=runner,
                out=lines.append,
            )
            == 2
        ), wrong
    assert runner.ran() == []
    assert "--done 写的停点名不对：'settle_scan'" in lines[0]
    assert "只认这些停点：verify、accept、close、transition、worktree" in lines[0]
    assert not (root / ".auto-pm" / "reports" / "flows").exists(), "用法错不落运行记录"


def test_done_on_main_cli_exits_2(flows: ModuleType, tmp_path: Path) -> None:
    assert (
        flows.main(
            [
                "--root",
                str(_root(tmp_path)),
                "closeout",
                "DJ-2026-005",
                "--mission-id",
                "MISSION-ABC123",
                "--done",
                "settle_scan",
            ]
        )
        == 2
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


# ── 进门、只列步骤、根目录清洁（瘦身方案单一：K5、K2） ──────────────────────────


class EntryRunner(FakeRunner):
    """``claim list --json`` 回一张给定的占位表，``claim log <卡>`` 回给定的记录原文；其余同 FakeRunner。"""

    def __init__(
        self,
        claims: Any,
        logs: dict[str, str] | None = None,
        fail: dict[str, int] | None = None,
    ) -> None:
        super().__init__(fail)
        self.claims = claims
        self.logs = logs or {}

    def __call__(self, command: list[str], **kwargs: Any) -> SimpleNamespace:
        reply = super().__call__(command, **kwargs)
        tail = command[3:]
        if reply.returncode == 0 and tail[:3] == ["claim", "list", "--json"]:
            reply.stdout = self.claims if isinstance(self.claims, str) else json.dumps(self.claims)
            reply.stderr = "（离线视图提示走 stderr，不该混进 JSON）\n"
        if reply.returncode == 0 and tail[:2] == ["claim", "log"]:
            reply.stdout = self.logs.get(tail[2], "这张卡还没有交接记录。\n")
        return reply


_LOG_A = (
    "第 1 笔 起草 …\n"
    "最后一笔：接手，claude-aaaaaa → 下一班，2026-11-14T18:57:14+00:00\n"
    "下一棒：下一班，已读 018，下一步对 025\n"
    "先读：0100_PLC自动化/DJ-2026-005/025.md、0100_PLC自动化/DJ-2026-005/018.md\n"
)
_LOG_B = (
    "最后一笔：搁置，claude-bbbbbb → 用户，2026-11-14T10:00:00+00:00\n"
    "下一棒：用户，等用户定\n"
    "先读：0100_PLC自动化/DJ-2026-005/018.md\n"
)
_CLAIMS = [
    {
        "card": "trial-a",
        "owner": "claude-aaaaaa",
        "paths": ["0100_PLC自动化/DJ-2026-005/018.md"],
        "free": False,
        "status": "active",
    },
    {
        "card": "old-b",
        "owner": "claude-bbbbbb",
        "paths": ["0100_PLC自动化/DJ-2026-005"],
        "free": True,
        "status": "active",
    },
    {
        "card": "done-e",
        "owner": "claude-eeeeee",
        "paths": ["0100_PLC自动化/DJ-2026-005/x.md"],
        "free": True,
        "status": "released",
    },
    {"card": "other-c", "owner": "x", "paths": ["0100_PLC自动化/DJ-2026-0050/a.md"], "free": False},
    {"card": "none-d", "owner": "x", "paths": [], "free": False},
]


def test_entry_runs_the_checkup_then_the_claims_then_each_card_of_the_project(
    flows: ModuleType, tmp_path: Path
) -> None:
    root = _set_mode(_root(tmp_path), "多机")
    runner = EntryRunner(_CLAIMS, {"trial-a": _LOG_A, "old-b": _LOG_B})
    lines: list[str] = []

    assert flows.run_flow("entry", "DJ-2026-005", root=root, runner=runner, out=lines.append) == 0

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
    # 体检之后先读本机交接交换区，多机档再看占位表；只有路径落在本项目目录里、还没放下的卡才读交接记录
    # （DJ-2026-0050 不算 005 的；只占号没路径的不算；已放下的 done-e 不读；租约到期没放下的 old-b 照读）
    assert runner.calls[-4]["command"][2].endswith("pm_handoff.py")
    assert ran[-3:] == ["claim list --json", "claim log old-b", "claim log trial-a"]
    text = "\n".join(lines)
    assert "另有 1 张已放下的卡（PR 已合、卡已收），不读交接记录" in text
    assert "下一棒：下一班，已读 018，下一步对 025" in text and "下一棒：用户，等用户定" in text
    assert "old-b（占位已放下或租约到期）" in text
    tail = text[text.index("接手前先读完这些文件") :]
    assert tail.count("0100_PLC自动化/DJ-2026-005/018.md") == 1, "先读的文件去重"
    assert "0100_PLC自动化/DJ-2026-005/025.md" in tail
    assert "不是状态" in text, "要说明交接记录里的话不当状态"
    # 进门时命令目录不刷屏：替身对命令目录那一步输出“ran --print”（命令是 python -B command_catalog.py --print），
    # 刷屏时屏幕上会有“  ran --print”这一行；不刷屏时只有一行“命令目录全文存在 …”（#825 验收 WARN-1）
    assert "  ran --print" not in lines, "进门时命令目录不刷屏"
    assert sum(line.startswith("  命令目录全文存在 ") for line in lines) == 1, (
        "屏幕上只说命令目录存在哪"
    )
    record = json.loads(
        next((root / ".auto-pm" / "reports" / "flows").glob("*_entry_DJ-2026-005.json")).read_text(
            encoding="utf-8"
        )
    )
    assert record["result"] == "走完，全过"
    assert [item["card"] for item in record["handover"]] == ["old-b", "trial-a"]
    assert record["handover"][1]["下一棒"] == "下一班，已读 018，下一步对 025"
    assert Path(record["catalog"]).is_file()


def test_entry_without_a_card_of_the_project_says_so(flows: ModuleType, tmp_path: Path) -> None:
    root = _set_mode(_root(tmp_path), "多机")
    runner = EntryRunner([_CLAIMS[2]])
    lines: list[str] = []

    assert flows.run_flow("entry", "DJ-2026-005", root=root, runner=runner, out=lines.append) == 0
    assert runner.ran()[-1] == "claim list --json"
    assert "本项目目录下没有没放下的占位，没有交接记录要读。" in lines


def test_entry_keeps_going_when_the_claim_list_is_red(flows: ModuleType, tmp_path: Path) -> None:
    root = _set_mode(_root(tmp_path), "多机")
    runner = EntryRunner(_CLAIMS, fail={"claim list": 2})
    lines: list[str] = []

    assert flows.run_flow("entry", "DJ-2026-005", root=root, runner=runner, out=lines.append) == 1
    assert not any(command.startswith("claim log") for command in runner.ran())
    assert any("「占位表」" in line and "红" in line for line in lines)


def test_entry_turns_red_when_the_claim_list_is_not_json(flows: ModuleType, tmp_path: Path) -> None:
    root = _set_mode(_root(tmp_path), "多机")
    runner = EntryRunner("not json")
    lines: list[str] = []

    assert flows.run_flow("entry", "DJ-2026-005", root=root, runner=runner, out=lines.append) == 1
    assert any("读不懂" in line for line in lines)
    assert not any(command.startswith("claim log") for command in runner.ran())


def test_entry_reads_no_log_when_the_project_is_not_registered(
    flows: ModuleType, tmp_path: Path
) -> None:
    root = _set_mode(_root(tmp_path, "DJ-2026-009", "0100_PLC自动化/DJ-2026-009"), "多机")
    runner = EntryRunner(_CLAIMS)
    lines: list[str] = []

    flows.run_flow("entry", "DJ-2026-005", root=root, runner=runner, out=lines.append)
    assert not any(command.startswith("claim log") for command in runner.ran())
    assert any("查不到这个项目的目录" in line for line in lines)


def test_entry_has_no_stop_point_and_only_reads(flows: ModuleType) -> None:
    assert all(step.kind == "run" for step in flows.ENTRY)
    assert flows.ENTRY[: len(flows.CHECKUP)] == flows.CHECKUP, "进门先做完整的体检"
    assert "entry" in flows.KEEP_GOING


def test_steps_lists_every_step_and_runs_nothing(
    flows: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def refuse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("steps 不该跑任何命令")

    monkeypatch.setattr(flows.subprocess, "run", refuse)
    monkeypatch.chdir(tmp_path)
    for name, steps in flows.FLOWS.items():
        assert flows.main(["--root", str(tmp_path), "steps", name]) == 0
        printed = capsys.readouterr().out
        for step in steps:
            assert f"| {step.label} |" in printed
    assert "`main.py pm orient <项目编号>`" in _steps_text(flows, "checkup")
    assert "`main.py pm verify --mission-id <卡号> --lease-wallet`" in _steps_text(
        flows, "closeout"
    )
    assert "`main.py claim log <卡号>`" in _steps_text(flows, "entry")
    assert not (tmp_path / ".auto-pm").exists(), "steps 不写运行记录"


def _steps_text(flows: ModuleType, name: str) -> str:
    lines: list[str] = []
    flows.print_steps(name, out=lines.append)
    return "\n".join(lines)


def test_root_clean_names_leftovers_but_is_not_red_and_deletes_nothing(
    flows: ModuleType, tmp_path: Path
) -> None:
    root = _root(tmp_path)
    for name in ("tmp_probe.py", ".coverage", "run.log"):
        (root / name).write_text("x", encoding="utf-8")
    (root / "htmlcov").mkdir()
    lines: list[str] = []

    assert (
        flows.run_flow("checkup", "DJ-2026-005", root=root, runner=FakeRunner(), out=lines.append)
        == 0
    )
    text = "\n".join(lines)
    assert "根目录有临时文件：.coverage、htmlcov、run.log、tmp_probe.py" in text
    assert "| 12 | 工作区根目录清洁 | 提醒 |" in text
    assert all(
        (root / name).exists() for name in ("tmp_probe.py", ".coverage", "run.log", "htmlcov")
    )


def test_root_litter_ignores_ordinary_files(flows: ModuleType, tmp_path: Path) -> None:
    for name in ("main.py", "AGENTS.md", "README.md", ".gitignore"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    (tmp_path / ".auto-pm").mkdir()
    assert flows.root_litter(tmp_path) == []


def test_entry_says_plainly_when_the_release_has_no_claim_log(
    flows: ModuleType, tmp_path: Path
) -> None:
    class OldRelease(EntryRunner):
        def __call__(self, command: list[str], **kwargs: Any) -> SimpleNamespace:
            if command[3:5] == ["claim", "log"]:
                self.calls.append({"command": command, **kwargs})
                return SimpleNamespace(
                    returncode=2, stdout="", stderr="Error: No such command 'log'.\n"
                )
            return super().__call__(command, **kwargs)

    root = _set_mode(_root(tmp_path), "多机")
    runner = OldRelease(_CLAIMS)
    lines: list[str] = []

    assert flows.run_flow("entry", "DJ-2026-005", root=root, runner=runner, out=lines.append) == 1
    logs = [command for command in runner.ran() if command.startswith("claim log")]
    assert logs == ["claim log old-b"], "第一张就报没有这条命令，后面几张不再跑"
    text = "\n".join(lines)
    assert "本机生效的发布版本还没有交接记录命令（claim log）：照实告诉用户，不要绕过去" in text
    assert "后面 1 张卡的交接记录也读不了，不再跑" in text
    assert text.count("发布版本没有 claim log，没读。") == 2


# ---- 中文 Windows 上输出一重定向就崩（用户本机 2026-11-16：UnicodeEncodeError: 'gbk' codec can't encode character '▶'）----

_FAKE_MAIN = (
    "import sys\n"
    "args = sys.argv[1:]\n"
    "if args[:2] == ['claim', 'list']:\n"
    "    print('[]')\n"
    "else:\n"
    "    print('替身命令 ✓ ▶ ' + ' '.join(args))\n"
)


@pytest.mark.parametrize("flow", ["entry", "checkup", "closeout", "closeout-pr", "steps"])
def test_output_piped_in_gbk_does_not_crash(flow: str, tmp_path: Path) -> None:
    """像中文 Windows 上把输出接到文件或管道：没设 PYTHONUTF8，管道编码是 GBK。四个子命令都要跑到最后、不崩，
    写出来的是 UTF-8（读的一方按 UTF-8 解得出“▶ 第 1 步”）。替身 main.py 只回一行字，不碰真账本。"""
    import os
    import subprocess

    root = _root(tmp_path)
    (root / "main.py").write_text(_FAKE_MAIN, encoding="utf-8")
    env = {key: value for key, value in os.environ.items() if key not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    env["PYTHONIOENCODING"] = "gbk"
    args = {
        "entry": ["entry", "DJ-2026-005"],
        "checkup": ["checkup", "DJ-2026-005"],
        "closeout": ["closeout", "DJ-2026-005", "--mission-id", "MISSION-3E5ED659C44DE219"],
        "closeout-pr": ["closeout-pr", "DJ-2026-005", "--chg", "CHG-SCPT-2026-717", "--card", "309"],
        "steps": ["steps", "entry"],
    }[flow]
    done = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "--root", str(root), *args],
        capture_output=True, timeout=600, env=env, check=False, cwd=str(root),
    )
    stdout = done.stdout.decode("utf-8")  # 不加 errors：写出来的不是 UTF-8 就在这里红
    stderr = done.stderr.decode("utf-8", errors="replace")
    assert "UnicodeEncodeError" not in stderr, stderr[-2000:]
    assert done.returncode in (0, 1, 3), (done.returncode, stderr[-2000:])  # 走完、有红、停在停点都算跑到了头，不是崩
    if flow == "steps":
        assert stdout.strip(), "steps 什么都没列"
    else:
        assert "▶ 第 1 步" in stdout and "运行记录" in stdout, stdout[-2000:]


def test_utf8_output_writes_utf8_when_piped_and_escapes_on_a_gbk_terminal(flows: ModuleType) -> None:
    import io

    class Terminal(io.TextIOWrapper):
        def isatty(self) -> bool:
            return True

    piped_bytes, tty_bytes = io.BytesIO(), io.BytesIO()
    piped = io.TextIOWrapper(piped_bytes, encoding="gbk")
    terminal = Terminal(tty_bytes, encoding="gbk")
    flows.utf8_output([piped, terminal, io.StringIO()])  # StringIO 没有 reconfigure：跳过，不报错
    for stream in (piped, terminal):
        stream.write("▶ 第 1 步")
        stream.flush()
    assert piped_bytes.getvalue().decode("utf-8") == "▶ 第 1 步"
    assert tty_bytes.getvalue().decode("gbk") == "\\u25b6 第 1 步"  # 终端自己的编码，写不出的字转义成看得见的样子


# 进门最后按卡类型提示该读哪个角色包（CHG-SCPT-2026-711）：包从控制根 roles/*/role.json 现读，卡按登记路径对模式。
def _pack(root: Path, role: str, title: str, patterns: list[str]) -> None:
    folder = root / "roles" / role
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(f"---\nname: {role}\n---\n", encoding="utf-8")
    (folder / "role.json").write_text(
        json.dumps({"id": role, "title": title, "owned_paths_patterns": patterns}), encoding="utf-8"
    )


def _packs_root(tmp_path: Path) -> Path:
    root = _root(tmp_path)
    _pack(root, "ui-designer", "UI 设计师", ["**/*.html"])
    _pack(root, "plc-electrical-engineer", "编程工程师（PLC）", ["**/*.scl"])
    _pack(root, "product-pm", "产品型项目经理", [])
    (root / "roles" / "shared").mkdir()  # 共用参考没有 role.json，不算包
    (root / "roles" / "broken").mkdir()
    (root / "roles" / "broken" / "SKILL.md").write_text("x", encoding="utf-8")
    (root / "roles" / "broken" / "role.json").write_text("not json", encoding="utf-8")
    return root


def test_role_packs_reads_the_control_root_in_card_type_order(
    flows: ModuleType, tmp_path: Path
) -> None:
    packs = flows.role_packs(_packs_root(tmp_path))

    assert [pack["id"] for pack in packs] == ["plc-electrical-engineer", "ui-designer", "product-pm"]
    assert packs[0]["skill"] == "roles/plc-electrical-engineer/SKILL.md"
    assert packs[0]["card_type"] == flows.ROLE_CARD_TYPES["plc-electrical-engineer"]
    assert flows.role_packs(tmp_path / "nowhere") == []


def test_packs_for_paths_matches_the_owned_path_patterns(flows: ModuleType, tmp_path: Path) -> None:
    packs = flows.role_packs(_packs_root(tmp_path))

    assert flows.packs_for_paths(packs, ["a/FB_1.scl", "b\\index.html"]) == [
        "plc-electrical-engineer",
        "ui-designer",
    ]
    assert flows.packs_for_paths(packs, ["top.scl"]) == ["plc-electrical-engineer"], "**/ 也认仓库根"
    assert flows.packs_for_paths(packs, ["0100_PLC自动化/DJ-2026-005"]) == []


def test_entry_ends_with_the_role_pack_hint_per_card(flows: ModuleType, tmp_path: Path) -> None:
    root = _set_mode(_packs_root(tmp_path), "多机")
    claims = [
        {"card": "scl-a", "owner": "x", "paths": ["0100_PLC自动化/DJ-2026-005/FB_1.scl"], "free": False},
        {"card": "doc-b", "owner": "x", "paths": ["0100_PLC自动化/DJ-2026-005/018.md"], "free": False},
    ]
    lines: list[str] = []

    assert flows.run_flow("entry", "DJ-2026-005", root=root, runner=EntryRunner(claims), out=lines.append) == 0
    text = "\n".join(lines)
    hint = text[text.index("【该读哪个角色包】") :]
    assert text.index("【交接记录】") < text.index("【该读哪个角色包】"), "先交接记录，后角色包"
    assert f"- {flows.ROLE_CARD_TYPES['ui-designer']}：roles/ui-designer/SKILL.md（UI 设计师）" in hint
    assert "  scl-a：roles/plc-electrical-engineer/SKILL.md" in hint
    assert "  doc-b：登记路径认不出卡类型" in hint
    record = json.loads(
        next((root / ".auto-pm" / "reports" / "flows").glob("*_entry_DJ-2026-005.json")).read_text(
            encoding="utf-8"
        )
    )
    assert record["role_hints"] == [
        {"card": "doc-b", "roles": []},
        {"card": "scl-a", "roles": ["plc-electrical-engineer"]},
    ]


def test_entry_without_roles_says_it_cannot_hint(flows: ModuleType, tmp_path: Path) -> None:
    lines: list[str] = []

    assert flows.run_flow("entry", "DJ-2026-005", root=_root(tmp_path), runner=EntryRunner([]), out=lines.append) == 0
    assert "控制根里没有 roles/ 角色包，没法提示；先跑 main.py role check 看看。" in lines


def test_checkup_gives_no_role_hint(flows: ModuleType, tmp_path: Path) -> None:
    lines: list[str] = []

    flows.run_flow("checkup", "DJ-2026-005", root=_packs_root(tmp_path), runner=FakeRunner(), out=lines.append)
    assert not any("【该读哪个角色包】" in line for line in lines)


def test_steps_of_entry_lists_the_role_hint(flows: ModuleType) -> None:
    assert "| 角色包提示 |" in _steps_text(flows, "entry")


# ---- PR 线收口（CHG-SCPT-2026-717）：不走 Run 的全流程、标准线卡，PR 合进 main 后的收口 ----

_PR_ARGS: dict[str, str] = {"chg": "CHG-SCPT-2026-717", "card": "309"}


def test_every_state_changing_pr_closeout_step_is_a_stop(flows: ModuleType) -> None:
    commands = _map()
    for step in flows.CLOSEOUT_PR:
        leaf = _leaf(step.args, commands)
        if commands[leaf]["class"] != "read" and leaf not in flows.READ_BY_CODE:
            assert step.kind == "stop", f"{leaf} 会改状态，必须是停点"
            assert step.who, f"{leaf} 停点要写明谁来做"
    transition = next(step for step in flows.CLOSEOUT_PR if step.key == "transition")
    assert (
        transition.kind == "stop"
        and transition.args[:2] == ("change", "transition")
        and "completed" in transition.args
        and "只有用户本人" in transition.who
        and "永远不执行" in transition.who
    )
    assert {"transition", "worktree"} <= {step.key for step in flows.CLOSEOUT_PR if step.kind == "stop"}


def test_pr_closeout_never_runs_a_state_changing_command(flows: ModuleType, tmp_path: Path) -> None:
    root = _root(tmp_path)
    runner = FakeRunner()
    stops = [step.key for step in flows.CLOSEOUT_PR if step.kind == "stop"]
    for done in ["", *stops]:
        lines: list[str] = []
        assert flows.run_flow(
            "closeout-pr", "DJ-2026-005", root=root, done=done, runner=runner, out=lines.append, **_PR_ARGS
        ) == (0 if done == stops[-1] else 3), done
    ran = runner.ran()
    for forbidden in ("change transition ", "claim release ", "worktree close ", "pm verify ", "pm accept "):
        assert not [call for call in ran if call.startswith(forbidden)], forbidden
    assert ran == [
        "pm control-root-status DJ-2026-005",
        "pr settle-scan DJ-2026-005",
        "ledger reconcile DJ-2026-005",
    ]


def test_pr_closeout_stop_fills_in_the_change_order_and_the_card(
    flows: ModuleType, tmp_path: Path
) -> None:
    root = _root(tmp_path)
    lines: list[str] = []

    assert (
        flows.run_flow(
            "closeout-pr", "DJ-2026-005", root=root, done="accepting", runner=FakeRunner(), out=lines.append, **_PR_ARGS
        )
        == 3
    )
    text = "\n".join(lines)
    assert "change transition CHG-SCPT-2026-717 --to completed --pid DJ-2026-005" in text
    assert "把 CHG-SCPT-2026-717 推到完成" in text
    assert "只有用户本人" in text
    record = json.loads(
        next((root / ".auto-pm" / "reports" / "flows").glob("*.json")).read_text(encoding="utf-8")
    )
    assert (record["chg"], record["card"]) == ("CHG-SCPT-2026-717", "309")
    assert record["stopped_at"]["key"] == "transition"

    lines.clear()
    assert (
        flows.run_flow(
            "closeout-pr", "DJ-2026-005", root=root, done="transition", runner=FakeRunner(), out=lines.append, **_PR_ARGS
        )
        == 3
    )
    assert any("claim release 309" in line for line in lines)


@pytest.mark.parametrize(("chg", "card"), [("CHG-717", "309"), ("--fix", "309"), ("CHG-SCPT-2026-717", "--fix"), ("CHG-SCPT-2026-717", "")])
def test_a_malformed_change_order_or_card_runs_nothing(
    flows: ModuleType, tmp_path: Path, chg: str, card: str
) -> None:
    runner = FakeRunner()
    lines: list[str] = []
    assert (
        flows.run_flow(
            "closeout-pr", "DJ-2026-005", root=_root(tmp_path), chg=chg, card=card, runner=runner, out=lines.append
        )
        == 2
    )
    assert runner.calls == []
    assert "格式不对" in lines[0] and "一条命令都没跑" in lines[0]


@pytest.mark.parametrize(
    ("flow", "extra"),
    [("closeout", {"mission": "MISSION-ABC123", "done": "close"}), ("closeout-pr", dict(_PR_ARGS))],
)
def test_settle_scan_saying_there_is_something_to_settle_is_not_red(
    flows: ModuleType, tmp_path: Path, flow: str, extra: dict[str, str]
) -> None:
    """``pr settle-scan`` 退出 1＝“有等收口的卡”：收口时的常态，流程照常走到下一个停点；退出 2＝判断不了，照样算红。"""
    lines: list[str] = []
    runner = FakeRunner(fail={"pr settle-scan": 1})
    assert flows.run_flow(flow, "DJ-2026-005", root=_root(tmp_path), runner=runner, out=lines.append, **extra) == 3
    assert "pr settle-scan DJ-2026-005" in runner.ran()
    assert not any("停在第" in line and "退出码 1" in line for line in lines)

    lines.clear()
    runner = FakeRunner(fail={"pr settle-scan": 2})
    assert flows.run_flow(flow, "DJ-2026-005", root=_root(tmp_path / "again"), runner=runner, out=lines.append, **extra) == 1
    assert any("「合并后收口清单」" in line and "退出码 2" in line for line in lines)


def test_steps_of_the_pr_closeout_lists_the_user_only_step(flows: ModuleType) -> None:
    text = _steps_text(flows, "closeout-pr")
    assert "`main.py change transition <变更单号> --to completed --pid <项目编号>`" in text
    assert "`main.py claim release <占位卡号>`" in text
    assert "只有用户本人" in text and "退出码 1 只说明有等收口的卡" in text


# ---- 卡 318：单机模式进门跳过远程占位、展示本机交接摘要、体检同样抑制命令目录刷屏 ----


@pytest.mark.parametrize("mode", [None, "备份", "关"])
def test_entry_in_single_machine_mode_runs_local_handoff_and_skips_remote_claims(
    flows: ModuleType, tmp_path: Path, mode: str | None
) -> None:
    root = _root(tmp_path)
    if mode is not None:
        _set_mode(root, mode)

    class LocalHandoffRunner(FakeRunner):
        def __call__(self, command: list[str], **kwargs: Any) -> SimpleNamespace:
            reply = super().__call__(command, **kwargs)
            if command[2].endswith("pm_handoff.py"):
                reply.stdout = (
                    "【本机交接交换区】DJ-2026-005（目录：0100_PLC自动化/DJ-2026-005/11_监控/交接交换区）\n"
                    "更新：2026-11-19T22:00:00Z（antigravity）\n"
                    "阶段目标：推进 PLC 联调收口\n"
                    "当前在干：无\n"
                    "待用户确认：\n"
                    "  - 请确认 TIA 导入结果\n"
                    "下一步：核对 025 点表后汇报用户\n"
                    "最近交接记录（共 1 条，展示最后 1 条）：\n"
                    "  - [2026-11-19T22:00:00Z] merged | antigravity\n"
                    "    摘要：初始化交换区\n"
                    "    先读：AGENTS.md、0100_PLC自动化/DJ-2026-005/INT.md\n"
                )
            return reply

    runner = LocalHandoffRunner()
    lines: list[str] = []
    assert flows.run_flow("entry", "DJ-2026-005", root=root, runner=runner, out=lines.append) == 0

    assert not any(call.startswith("claim ") for call in runner.ran()), "单机模式不查远程占位表"
    assert runner.calls[-1]["command"][2].endswith("pm_handoff.py")
    text = "\n".join(lines)
    assert "跳过（单机模式：" in text
    assert "【本机交接摘要】" in text
    assert "- 阶段目标：推进 PLC 联调收口" in text
    assert "- 待用户确认：请确认 TIA 导入结果" in text
    assert "本机交接先读文件" in text and "0100_PLC自动化/DJ-2026-005/INT.md" in text


def test_entry_turns_red_when_local_handoff_fails_closed(flows: ModuleType, tmp_path: Path) -> None:
    root = _root(tmp_path)
    runner = FakeRunner(fail={"show DJ-2026-005": 1})
    lines: list[str] = []

    assert flows.run_flow("entry", "DJ-2026-005", root=root, runner=runner, out=lines.append) == 1
    text = "\n".join(lines)
    assert "「本机交接状态」" in text and "红" in text
    assert "本机交接交换区校验未通过（失败关闭）" in text


def test_checkup_also_suppresses_command_catalog_stdout_flood(
    flows: ModuleType, tmp_path: Path
) -> None:
    root = _root(tmp_path)
    lines: list[str] = []
    assert flows.run_flow("checkup", "DJ-2026-005", root=root, runner=FakeRunner(), out=lines.append) == 0
    assert "  ran --print" not in lines, "体检时命令目录也不刷屏"
    assert sum(line.startswith("  命令目录全文存在 ") for line in lines) == 1


def test_entry_and_checkup_print_change_archive_summary_and_flag_off_main_history(
    flows: ModuleType, tmp_path: Path
) -> None:
    import json
    import subprocess

    root = _root(tmp_path, pid="SW-2026-008", project_root="01_Project/SW-2026-008")
    _set_mode(root, "备份")
    mgmt = root / "01_Project" / "SW-2026-008" / "04_监控" / "01_变更管理"
    chg_dir = mgmt / "01_变更单" / "CHG-SCPT"
    ledger = mgmt / "02_变更记录" / "01_版本变更台账.md"
    chg_dir.mkdir(parents=True, exist_ok=True)
    ledger.parent.mkdir(parents=True, exist_ok=True)

    (chg_dir / "CHG-SCPT-2026-700.md").write_text(
        "# 700\n\n| 字段 | 值 |\n|---|---|\n| 变更状态 | completed |\n",
        encoding="utf-8",
    )
    ledger.write_text(
        "| 序号 | 变更单 | 说明 | 日期 | 状态 |\n"
        "|------|--------|------|------|------|\n"
        "| 1 | [→ CHG-SCPT-2026-700](../01_变更单/CHG-SCPT/CHG-SCPT-2026-700.md) | 基线 | 2026-11-22 | ✅已关闭 |\n",
        encoding="utf-8",
    )

    def run_git(*args: str) -> str:
        done = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return done.stdout.strip()

    run_git("init", "-b", "main")
    run_git("config", "user.name", "Test")
    run_git("config", "user.email", "test@example.com")
    run_git("add", ".")
    run_git("commit", "-m", "baseline")

    run_git("checkout", "-b", "side/727")
    (root / "side727.txt").write_text("side\n", encoding="utf-8")
    run_git("add", "side727.txt")
    run_git("commit", "-m", "off main merge target")
    off_main_sha = run_git("rev-parse", "HEAD")
    run_git("checkout", "main")

    log_path = root / flows.MERGE_LOG_FILE
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        json.dumps({"merge_sha": off_main_sha, "chgs": ["CHG-SCPT-2026-727"]}) + "\n",
        encoding="utf-8",
    )

    (chg_dir / "CHG-SCPT-2026-734.md").write_text(
        "# 734\n\n| 字段 | 值 |\n|---|---|\n| 变更状态 | completed |\n",
        encoding="utf-8",
    )
    (chg_dir / "CHG-SCPT-2026-727.md").write_text(
        "# 727\n\n| 字段 | 值 |\n|---|---|\n| 变更状态 | implementing |\n",
        encoding="utf-8",
    )
    ledger.write_text(
        "| 序号 | 变更单 | 说明 | 日期 | 状态 |\n"
        "|------|--------|------|------|------|\n"
        "| 3 | [→ CHG-SCPT-2026-734](../01_变更单/CHG-SCPT/CHG-SCPT-2026-734.md) | 已完成待入库 | 2026-11-22 | ✅已关闭 |\n\n"
        "| 2 | [→ CHG-SCPT-2026-727](../01_变更单/CHG-SCPT/CHG-SCPT-2026-727.md) | 实施中 | 2026-11-22 | 🔄实施中 |\n\n"
        "| 1 | [→ CHG-SCPT-2026-700](../01_变更单/CHG-SCPT/CHG-SCPT-2026-700.md) | 基线 | 2026-11-22 | ✅已关闭 |\n",
        encoding="utf-8",
    )

    for flow_name in ("entry", "checkup"):
        lines: list[str] = []
        assert (
            flows.run_flow(
                flow_name, "SW-2026-008", root=root, runner=FakeRunner(), out=lines.append
            )
            == 0
        )
        text = "\n".join(lines)
        assert "【变更单入库积压摘要】" in text
        assert "CHG-SCPT-2026-734（原件未入主线）" in text
        assert "CHG-SCPT-2026-727（implementing）" in text
        assert "⚠ 历史合并不在当前主线，待核对替代提交：CHG-SCPT-2026-727" in text

        reports = sorted((root / flows.REPORTS).glob(f"*_{flow_name}_SW-2026-008.json"))
        assert reports
        payload = json.loads(reports[-1].read_text(encoding="utf-8"))
        summary = payload["change_archive_summary"]
        assert summary["available"] is True
        assert summary["github_sync"] == "GitHub 未配置远端"
        assert [item["chg"] for item in summary["completed_pending"]] == ["CHG-SCPT-2026-734"]
        assert [item["chg"] for item in summary["in_progress_untracked"]] == ["CHG-SCPT-2026-727"]
        assert [item["chg"] for item in summary["historical_off_main"]] == ["CHG-SCPT-2026-727"]
        assert "CHG-SCPT-2026-727" not in [item["chg"] for item in summary["completed_pending"]]

