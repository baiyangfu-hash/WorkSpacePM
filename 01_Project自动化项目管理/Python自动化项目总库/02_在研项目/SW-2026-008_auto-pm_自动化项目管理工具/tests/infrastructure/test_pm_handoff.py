"""本机轻轨交接交换区工具（PM-056 V2.0.0，local-handoff.v1，卡 318）：``scripts/pm_handoff.py``。"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

PROJECT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT / "scripts" / "pm_handoff.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pm_handoff_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def hm() -> ModuleType:
    return _load()


def _make_root(
    tmp_path: Path,
    *,
    as_worktree: bool = True,
    projects: list[dict[str, str]] | None = None,
) -> Path:
    root = tmp_path / "ws"
    (root / "SYS-2026-001_WorkspaceGovernance").mkdir(parents=True)
    if as_worktree:
        (root / ".git").write_text("gitdir: ../control/.git/worktrees/wt\n", encoding="utf-8")
    else:
        (root / ".git").mkdir()
    entries = projects or [
        {
            "project_id": "SW-2026-008",
            "project_root": "01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具",
        },
        {
            "project_id": "DJ-2026-005",
            "project_root": "0100_PLC自动化/DJ-2026-005",
        },
    ]
    (root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json").write_text(
        json.dumps({"projects": entries}, ensure_ascii=False), encoding="utf-8"
    )
    return root


class FakeGitRunner:
    """模拟只读 git worktree/rev-parse/merge-base 输出，不依赖真实 git 进程。"""

    def __init__(
        self,
        *,
        worktree_porcelain: str = "",
        existing_refs: set[str] | None = None,
        merged_refs: set[str] | None = None,
    ) -> None:
        self.worktree_porcelain = worktree_porcelain
        self.existing_refs = existing_refs or set()
        self.merged_refs = merged_refs or set()

    def __call__(self, command: list[str], **kwargs: Any) -> SimpleNamespace:
        if "worktree" in command:
            return SimpleNamespace(returncode=0, stdout=self.worktree_porcelain, stderr="")
        if "rev-parse" in command:
            ref = command[-1]
            return SimpleNamespace(returncode=0 if ref in self.existing_refs else 1, stdout="", stderr="")
        if "merge-base" in command:
            ref = command[-2]
            return SimpleNamespace(returncode=0 if ref in self.merged_refs else 1, stdout="", stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="")


def test_handoff_dir_resolves_without_collision_for_python_and_plc(
    hm: ModuleType, tmp_path: Path
) -> None:
    root = _make_root(tmp_path)
    sw_loc = hm.handoff_dir_of(root, "SW-2026-008")
    plc_loc = hm.handoff_dir_of(root, "DJ-2026-005")
    assert sw_loc is not None and sw_loc[1].endswith("/04_监控/交接交换区")
    assert plc_loc is not None and plc_loc[1] == "0100_PLC自动化/DJ-2026-005/11_监控/交接交换区"
    assert hm.handoff_dir_of(root, "SW-2026-999") is None


def test_uninitialized_project_shows_clean_notice_and_exits_0(
    hm: ModuleType, tmp_path: Path
) -> None:
    root = _make_root(tmp_path)
    lines: list[str] = []
    assert hm.show_handoff("SW-2026-008", root=root, runner=FakeGitRunner(), out=lines.append) == 0
    assert any("尚未建立本机交接交换区" in line for line in lines)

    val_lines: list[str] = []
    assert hm.validate_command("SW-2026-008", root=root, out=val_lines.append) == 0
    assert (
        hm.validate_command("SW-2026-008", root=root, require_exists=True, out=val_lines.append)
        == 1
    )


def test_control_root_write_guard_refuses_unless_explicitly_allowed(
    hm: ModuleType, tmp_path: Path
) -> None:
    root = _make_root(tmp_path, as_worktree=False)
    lines: list[str] = []
    rc = hm.set_focus_command(
        "SW-2026-008",
        root=root,
        updated_by="antigravity",
        stage_goal="收口单机本地优先交接",
        next_action="先跑 pm_flows.py entry SW-2026-008",
        out=lines.append,
    )
    assert rc == 2 and any("控制根" in line for line in lines)

    lines.clear()
    rc = hm.append_log_command(
        "SW-2026-008",
        root=root,
        agent="antigravity",
        kind="handoff",
        summary="记录一次交接",
        out=lines.append,
    )
    assert rc == 2 and any("控制根" in line for line in lines)

    # 显式 --allow-control-root 时放行
    lines.clear()
    rc = hm.set_focus_command(
        "SW-2026-008",
        root=root,
        updated_by="antigravity",
        stage_goal="收口单机本地优先交接",
        next_action="先跑 pm_flows.py entry SW-2026-008",
        allow_control_root=True,
        out=lines.append,
    )
    assert rc == 0


def test_round_trip_set_focus_log_validate_and_show(hm: ModuleType, tmp_path: Path) -> None:
    root = _make_root(tmp_path, as_worktree=True)
    existing_doc = root / "AGENTS.md"
    existing_doc.write_text("# rules\n", encoding="utf-8")
    now = datetime(2026, 11, 19, 22, 0, 0, tzinfo=UTC)

    assert (
        hm.set_focus_command(
            "SW-2026-008",
            root=root,
            updated_by="antigravity",
            stage_goal="完成单机轻轨交接契约与进门降噪",
            next_action="请用户确认将 CHG-SCPT-2026-726 推到完成",
            priorities=[
                {"rank": 1, "item": "核对进门 0 红", "ref": "CHG-SCPT-2026-726"},
                {"rank": 2, "item": "按需开展 PLC 项目", "ref": "DJ-2026-005"},
            ],
            active_card="318",
            active_branch="antigravity/318",
            active_chg="CHG-SCPT-2026-726",
            active_breakpoint="已通过测试与审计，待收口",
            waiting_for_user=["请确认将 CHG-SCPT-2026-726 推到完成"],
            now=now,
            out=lambda _: None,
        )
        == 0
    )

    assert (
        hm.append_log_command(
            "SW-2026-008",
            root=root,
            agent="antigravity",
            kind="merged",
            card="318",
            commit="abc12345",
            chg="CHG-SCPT-2026-726",
            summary="升级 PM-056 V2.0.0 并完成 pm_handoff 与进门降噪",
            read_first=["AGENTS.md"],
            next_hint="新对话直接跑 pm_flows.py entry SW-2026-008",
            now=now,
            out=lambda _: None,
        )
        == 0
    )

    val_lines: list[str] = []
    assert hm.validate_command("SW-2026-008", root=root, require_exists=True, out=val_lines.append) == 0
    assert any("校验通过" in line for line in val_lines)

    wt_out = (
        f"worktree {root}\nHEAD 1111\nbranch refs/heads/main\n\n"
        f"worktree {root / '.auto-pm/worktrees/antigravity-c31800'}\nHEAD 2222\nbranch refs/heads/antigravity/318\n"
    )
    runner = FakeGitRunner(worktree_porcelain=wt_out)

    text_lines: list[str] = []
    assert (
        hm.show_handoff("SW-2026-008", root=root, now=now + timedelta(hours=1), runner=runner, out=text_lines.append)
        == 0
    )
    joined = "\n".join(text_lines)
    assert "阶段目标：完成单机轻轨交接契约与进门降噪" in joined
    assert "不是授权源" in joined
    assert "1. 核对进门 0 红（参考：CHG-SCPT-2026-726）" in joined
    assert "先读：AGENTS.md" in joined
    assert "⚠ 提醒：" not in joined, "状态一致且未陈旧时不应有提醒"

    json_lines: list[str] = []
    assert (
        hm.show_handoff(
            "SW-2026-008", root=root, as_json=True, now=now + timedelta(hours=1), runner=runner, out=json_lines.append
        )
        == 0
    )
    data = json.loads("\n".join(json_lines))
    assert data["ok"] is True and data["events_total"] == 1 and data["warnings"] == []


def test_staleness_git_drift_and_missing_read_first_warnings(hm: ModuleType, tmp_path: Path) -> None:
    root = _make_root(tmp_path, as_worktree=True)
    old = datetime(2026, 11, 1, 10, 0, 0, tzinfo=UTC)
    now = datetime(2026, 11, 19, 10, 0, 0, tzinfo=UTC)

    assert (
        hm.set_focus_command(
            "SW-2026-008",
            root=root,
            updated_by="antigravity",
            stage_goal="测试漂移与陈旧检测",
            next_action="核对工位",
            active_card="318",
            active_branch="antigravity/318",
            now=old,
            out=lambda _: None,
        )
        == 0
    )
    assert (
        hm.append_log_command(
            "SW-2026-008",
            root=root,
            agent="antigravity",
            kind="handoff",
            summary="测试缺失先读路径",
            read_first=["docs/not_existing.md"],
            now=old,
            out=lambda _: None,
        )
        == 0
    )

    wt_out = (
        f"worktree {root}\nHEAD 1111\nbranch refs/heads/main\n\n"
        f"worktree {root / '.auto-pm/worktrees/deploy-1.3.3-d356fb1'}\nHEAD 1111\nbranch refs/heads/deploy\n\n"
        f"worktree {root / '.auto-pm/worktrees/claude-ab1234'}\nHEAD 3333\nbranch refs/heads/claude/319\n"
    )
    runner = FakeGitRunner(
        worktree_porcelain=wt_out,
        existing_refs={"refs/heads/antigravity/318"},
        merged_refs={"refs/heads/antigravity/318"},
    )
    lines: list[str] = []
    assert hm.show_handoff("SW-2026-008", root=root, now=now, runner=runner, out=lines.append) == 0
    text = "\n".join(lines)
    assert "陈旧提醒" in text
    assert "已并入 main 且无活跃工位" in text
    assert "未登记在 focus.json 的活跃工位 claude-ab1234（分支 claude/319）" in text
    assert "deploy-1.3.3-d356fb1" not in text, "deploy-* 只读目录不应触发漂移提醒"
    assert "先读文件缺失：docs/not_existing.md" in text


def test_fail_closed_on_corrupt_json_unknown_schema_lengths_and_unsafe_paths(
    hm: ModuleType, tmp_path: Path
) -> None:
    root = _make_root(tmp_path, as_worktree=True)
    hdir, _ = hm.handoff_dir_of(root, "SW-2026-008")
    hdir.mkdir(parents=True)

    # 1. 损坏 JSON -> 失败关闭
    (hdir / "focus.json").write_text("{bad json", encoding="utf-8")
    assert hm.show_handoff("SW-2026-008", root=root, runner=FakeGitRunner(), out=lambda _: None) == 1
    assert hm.validate_command("SW-2026-008", root=root, out=lambda _: None) == 1

    # 2a. 仅未知 schema（不含多余字段），确保真正命中 schema 校验而非提前返回
    bad_schema_focus: dict[str, Any] = {
        "schema": "local-handoff-focus.v99",
        "project_id": "SW-2026-008",
        "updated_at": "2026-11-19T22:00:00Z",
        "updated_by": "antigravity",
        "stage_goal": "ok",
        "priorities": [],
        "active_work": None,
        "waiting_for_user": [],
        "next_action": "ok",
    }
    (hdir / "focus.json").write_text(json.dumps(bad_schema_focus), encoding="utf-8")
    err_lines: list[str] = []
    assert hm.validate_command("SW-2026-008", root=root, out=err_lines.append) == 1
    assert any("schema 不匹配" in line for line in err_lines), err_lines

    # 2b. 仅未定义顶层字段 -> 失败关闭并明确报错
    extra_field_focus: dict[str, Any] = {
        **bad_schema_focus,
        "schema": "local-handoff-focus.v1",
        "unexpected_extra": 1,
    }
    (hdir / "focus.json").write_text(json.dumps(extra_field_focus), encoding="utf-8")
    err_lines.clear()
    assert hm.validate_command("SW-2026-008", root=root, out=err_lines.append) == 1
    assert any("含未定义字段" in line for line in err_lines), err_lines

    # 2c. journal.jsonl 未知 schema 与非法 kind -> 失败关闭并指出具体行号
    (hdir / "focus.json").unlink()
    bad_event_schema = {
        "schema": "local-handoff-event.v99",
        "ts": "2026-11-19T22:00:00Z",
        "agent": "antigravity",
        "kind": "handoff",
        "card": "318",
        "commit": "",
        "chg": "",
        "summary": "test",
        "read_first": [],
        "next": "",
    }
    (hdir / "journal.jsonl").write_text(json.dumps(bad_event_schema) + "\n", encoding="utf-8")
    err_lines.clear()
    assert hm.validate_command("SW-2026-008", root=root, out=err_lines.append) == 1
    assert any("第 1 行" in line and "schema 不匹配" in line for line in err_lines), err_lines

    bad_event_kind = {**bad_event_schema, "schema": "local-handoff-event.v1", "kind": "unknown_kind"}
    (hdir / "journal.jsonl").write_text(json.dumps(bad_event_kind) + "\n", encoding="utf-8")
    err_lines.clear()
    assert hm.validate_command("SW-2026-008", root=root, out=err_lines.append) == 1
    assert any("第 1 行" in line and "kind 不合法" in line for line in err_lines), err_lines
    (hdir / "journal.jsonl").unlink()

    # 3. 写入端长度超限、重复 rank、越界路径全部在写入前被拒
    assert (
        hm.set_focus_command(
            "SW-2026-008",
            root=root,
            updated_by="antigravity",
            stage_goal="长" * 121,
            next_action="ok",
            out=lambda _: None,
        )
        == 1
    )
    assert not (hdir / "focus.json").exists(), "校验不通过时不写文件"

    assert (
        hm.set_focus_command(
            "SW-2026-008",
            root=root,
            updated_by="antigravity",
            stage_goal="ok",
            next_action="ok",
            priorities=[
                {"rank": 1, "item": "a", "ref": ""},
                {"rank": 1, "item": "b", "ref": ""},
            ],
            out=lambda _: None,
        )
        == 1
    )

    for bad_path in ("../outside.md", "/abs.md", "C:/win.md", r"a\b.md"):
        assert (
            hm.append_log_command(
                "SW-2026-008",
                root=root,
                agent="antigravity",
                kind="handoff",
                summary="test",
                read_first=[bad_path],
                out=lambda _: None,
            )
            == 1
        ), bad_path

    # 4. 已有 journal.jsonl 损坏时拒绝继续追加
    (hdir / "journal.jsonl").write_text("{corrupt\n", encoding="utf-8")
    assert (
        hm.append_log_command(
            "SW-2026-008",
            root=root,
            agent="antigravity",
            kind="handoff",
            summary="合法事件也不能往坏文件里追加",
            out=lambda _: None,
        )
        == 1
    )


def test_drift_detection_when_root_is_a_worktree_itself(hm: ModuleType, tmp_path: Path) -> None:
    """B2 回归：--root 指向开发工位自身（worktree list 非第 0 块）时，既不误报当前分支缺失，也不漏报未登记工位。"""
    control = tmp_path / "control"
    (control / ".git").mkdir(parents=True)
    wt = _make_root(tmp_path / "wt_wrap", as_worktree=True)
    now = datetime(2026, 11, 19, 22, 0, 0, tzinfo=UTC)
    wt_out = (
        f"worktree {control}\nHEAD 1111\nbranch refs/heads/main\n\n"
        f"worktree {wt}\nHEAD 2222\nbranch refs/heads/antigravity/318\n"
    )
    runner = FakeGitRunner(worktree_porcelain=wt_out)

    # 场景 1：active_work 匹配当前工位分支 -> 0 提醒（不能误报不在活跃工位列表）
    assert (
        hm.set_focus_command(
            "SW-2026-008",
            root=wt,
            updated_by="antigravity",
            stage_goal="工位内核对",
            next_action="继续",
            active_card="318",
            active_branch="antigravity/318",
            now=now,
            out=lambda _: None,
        )
        == 0
    )
    lines: list[str] = []
    assert hm.show_handoff("SW-2026-008", root=wt, now=now, runner=runner, out=lines.append) == 0
    assert "⚠ 提醒：" not in "\n".join(lines), lines

    # 场景 2：active_work=None 但当前工位在活跃列表中 -> 必须报出未登记活跃工位（不能漏报）
    assert (
        hm.set_focus_command(
            "SW-2026-008",
            root=wt,
            updated_by="antigravity",
            stage_goal="工位内核对",
            next_action="继续",
            now=now,
            out=lambda _: None,
        )
        == 0
    )
    lines.clear()
    assert hm.show_handoff("SW-2026-008", root=wt, now=now, runner=runner, out=lines.append) == 0
    joined = "\n".join(lines)
    assert "未登记在 focus.json 的活跃工位" in joined and "antigravity/318" in joined


def test_append_log_handles_existing_journal_missing_trailing_newline(
    hm: ModuleType, tmp_path: Path
) -> None:
    """N2 回归：已有非空 journal.jsonl 缺少末尾换行时，追加事件自动补换行，不破坏 JSONL。"""
    root = _make_root(tmp_path, as_worktree=True)
    hdir, _ = hm.handoff_dir_of(root, "SW-2026-008")
    hdir.mkdir(parents=True)
    first = {
        "schema": "local-handoff-event.v1",
        "ts": "2026-11-19T21:00:00Z",
        "agent": "antigravity",
        "kind": "handoff",
        "card": "318",
        "commit": "",
        "chg": "",
        "summary": "第一条无尾换行",
        "read_first": [],
        "next": "",
    }
    (hdir / "journal.jsonl").write_text(json.dumps(first, ensure_ascii=False), encoding="utf-8")

    assert (
        hm.append_log_command(
            "SW-2026-008",
            root=root,
            agent="antigravity",
            kind="takeover",
            summary="第二条正常追加",
            out=lambda _: None,
        )
        == 0
    )
    loaded = hm.load_handoff(root, "SW-2026-008")
    assert loaded is not None and loaded.ok and len(loaded.events) == 2


def test_cli_outputs_utf8_even_under_gbk_pipe(tmp_path: Path) -> None:
    root = _make_root(tmp_path, as_worktree=True)
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    env["PYTHONIOENCODING"] = "gbk"
    done = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "show", "SW-2026-008", "--root", str(root)],
        capture_output=True,
        timeout=30,
        env=env,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", errors="replace")
    stdout = done.stdout.decode("utf-8")
    assert "【本机交接交换区】SW-2026-008" in stdout
