"""骨架 B 的纯解析（scripts/cockpit_board/readers.py）和快照读取（snapshot.py）。

每种输出三类样本：正常（tests/fixtures/cockpit_board/ 里的真实或合成样本）、缺字段、命令不存在（只有报错、没有 JSON）。
读不懂一律标 unreadable 并写明原因，不猜、不补 0。
"""

from __future__ import annotations

import ast
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "cockpit_board"
sys.path.insert(0, str(SCRIPTS))

from cockpit_board import readers, snapshot  # noqa: E402

# 读法名 → 正常样本文件、一个必须有的字段（拿来做“缺字段”变异）
CASES: dict[str, tuple[str, str]] = {
    "orient": ("orient.json", "context"),
    "missions": ("pm_missions.json", "waiting"),
    "pending": ("pm_pending.json", "cards"),
    "inbox": ("pm_inbox.json", "items"),
    "worktree_list": ("worktree_list.json", "branch"),
    "worktree_sweep": ("worktree_sweep.json", "items"),
    "project_list": ("project_list.json", "project_id"),
    "plc_check": ("plc_check.json", "items"),
    "long_run": ("long_run_status.json", "tasks"),
}


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _drop(value: Any, key: str) -> Any:
    """去掉一个必须有的字段：字典直接删键，列表删每一行的这个键。"""
    if isinstance(value, dict):
        return {k: v for k, v in value.items() if k != key}
    return [{k: v for k, v in row.items() if k != key} for row in value]


def test_every_reader_has_a_case() -> None:
    assert set(CASES) == set(readers.READERS)


@pytest.mark.parametrize("reader", sorted(CASES))
def test_normal_sample_parses(reader: str) -> None:
    parsed = readers.parse(reader, _fixture(CASES[reader][0]))
    assert parsed.ok, parsed.note
    assert parsed.note == ""


@pytest.mark.parametrize("reader", sorted(CASES))
def test_missing_field_is_unreadable_not_guessed(reader: str) -> None:
    name, key = CASES[reader]
    broken = json.dumps(_drop(json.loads(_fixture(name)), key), ensure_ascii=False)
    parsed = readers.parse(reader, broken)
    assert parsed.state == readers.UNREADABLE and parsed.note and parsed.data == {}


@pytest.mark.parametrize("reader", sorted(CASES))
def test_missing_command_output_is_unreadable(reader: str) -> None:
    # 命令不存在时 stdout 是空的、报错在 stderr；把 stderr 喂给解析也只能得到“读不懂”
    for text in ("", _fixture("stderr_missing_command.txt"), _fixture("stderr_no_ledger.txt")):
        assert readers.parse(reader, text).state == readers.UNREADABLE


def test_lenient_json_skips_banner_and_tail() -> None:
    text = "launcher: release verified\n⚠️ 控制根落后 3 个提交\n" + _fixture("pm_inbox.json") + "提示：完成\n"
    assert readers.lenient_json(text) == json.loads(_fixture("pm_inbox.json"))
    assert readers.lenient_json("没有 JSON") is None
    assert readers.lenient_json("{ 坏的") is None
    assert readers.parse("inbox", text).ok


def test_orient_fields_from_real_sample() -> None:
    data = readers.parse("orient", _fixture("orient.json")).data
    assert data["project_id"] == "SW-2026-008"
    assert data["conflicts"] == ["RUNTIME_IDENTITY_UNVERIFIED"]  # 空账本、云端没有运行身份：照原样报冲突
    assert data["mission_id"] == "" and data["has_run"] is False


def test_empty_lists_are_ok_not_unreadable() -> None:
    assert readers.parse("worktree_list", _fixture("worktree_list_empty.json")).data == {"stations": []}
    assert readers.parse("inbox", _fixture("pm_inbox.json")).data["items"] == []


def test_plc_check_counts_come_from_items_and_mismatch_is_unreadable() -> None:
    data = readers.parse("plc_check", _fixture("plc_check.json")).data
    assert (data["pass"], data["warn"], data["fail"]) == (10, 6, 2)
    value = json.loads(_fixture("plc_check.json"))
    value["fail_count"] = 0  # 自报 0 个失败，逐项数出来是 2：不信自报
    parsed = readers.parse("plc_check", json.dumps(value))
    assert parsed.state == readers.UNREADABLE and "fail_count" in parsed.note


def test_long_run_keeps_unreadable_tasks() -> None:
    tasks = readers.parse("long_run", _fixture("long_run_status.json")).data["tasks"]
    assert [t["state"] for t in tasks] == ["RUNNING", "UNREADABLE"]


def test_unknown_reader_is_a_code_error() -> None:
    with pytest.raises(KeyError):
        readers.parse("没有这个读法", "{}")


def test_readers_and_snapshot_stay_pure() -> None:
    """不起子进程、不 import auto_pm、不写文件（写快照在 actions.py）。"""
    for name in ("readers.py", "snapshot.py"):
        tree = ast.parse((SCRIPTS / "cockpit_board" / name).read_text(encoding="utf-8"))
        imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        imported |= {(node.module or "").split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        assert not imported & {"subprocess", "auto_pm", "os", "shutil", "socket", "urllib"}, (name, imported)
        calls = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        assert not calls & {"write_text", "write_bytes", "mkdir", "unlink", "replace", "rename"}, (name, calls)


# ---------------------------------------------------------------- 快照读取


def test_snapshot_round_trip_and_staleness(tmp_path: Path) -> None:
    now = datetime(2026, 11, 11, 14, 0, tzinfo=UTC)
    key = snapshot.key_for("orient", "SW-2026-008")
    assert key == "orient-sw-2026-008"
    path = snapshot.path_for(tmp_path, key)
    assert path == tmp_path / ".auto-pm" / "cache" / "cockpit_board" / "orient-sw-2026-008.json"
    path.parent.mkdir(parents=True)
    path.write_text(snapshot.encode(key, now - timedelta(minutes=5), "ok", "{}", ""), encoding="utf-8")
    loaded = snapshot.load(tmp_path, key)
    assert loaded is not None and loaded.stdout == "{}" and loaded.kind == "ok"
    assert not snapshot.is_stale(loaded, now) and snapshot.age_text(loaded, now) == "上次读取：5 分钟前"
    assert snapshot.is_stale(loaded, now + timedelta(hours=1))
    assert snapshot.age_text(loaded, now + timedelta(hours=1)).endswith("（已过期）")
    assert snapshot.is_stale(loaded, now - timedelta(hours=1))  # 快照时间在将来：按过期


def test_bad_or_foreign_snapshot_is_treated_as_missing(tmp_path: Path) -> None:
    key = snapshot.key_for("inbox", "SW-2026-008")
    path = snapshot.path_for(tmp_path, key)
    path.parent.mkdir(parents=True)
    assert snapshot.load(tmp_path, key) is None  # 没有文件
    for text in ("坏的", "{}", json.dumps({"schema_version": snapshot.SCHEMA, "key": key, "saved_at": "2026-11-11T14:00:00",
                                           "kind": "ok", "stdout": "", "stderr": ""})):
        path.write_text(text, encoding="utf-8")
        assert snapshot.load(tmp_path, key) is None  # 读不懂、没带时区：都当没有
    path.write_text(snapshot.encode("orient-x", datetime.now(UTC), "ok", "", ""), encoding="utf-8")
    assert snapshot.load(tmp_path, key) is None  # 键对不上：不认


@pytest.mark.parametrize("bad", ["../escape", "a/b", "A B", "", "x" * 65])
def test_snapshot_keys_cannot_leave_the_cache(bad: str) -> None:
    with pytest.raises(ValueError):
        snapshot.path_for(Path("/root"), bad)
    with pytest.raises(ValueError):
        snapshot.key_for(bad)
