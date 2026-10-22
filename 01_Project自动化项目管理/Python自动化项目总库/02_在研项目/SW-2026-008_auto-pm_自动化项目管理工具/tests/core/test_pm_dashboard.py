"""多项目安灯板 ``scripts/pm_dashboard.py``：只读、四栏归类、“要你定”最多 3 件、判灯、页面上没有执行按钮。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "pm_dashboard.py"
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pm_dashboard_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


pd = _load()

DDL = """
CREATE TABLE work_items (work_id TEXT PRIMARY KEY, subject_project_id TEXT, title TEXT,
    state TEXT, updated_at TEXT);
CREATE TABLE run_items (run_id TEXT PRIMARY KEY, work_id TEXT, state TEXT, executor_id TEXT,
    worktree_path TEXT, updated_at TEXT);
CREATE TABLE execution_leases (run_id TEXT PRIMARY KEY, expires_at TEXT);
CREATE TABLE checkpoints (checkpoint_id TEXT PRIMARY KEY, run_id TEXT, sequence INTEGER,
    summary TEXT);
CREATE TABLE mission_items (mission_id TEXT PRIMARY KEY, subject_project_id TEXT, title TEXT,
    state TEXT, root_work_id TEXT, updated_at TEXT);
CREATE TABLE closure_items (closure_id TEXT PRIMARY KEY, mission_id TEXT, change_id TEXT,
    state TEXT, updated_at TEXT);
"""


def _iso(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


def _workspace(tmp_path: Path, missions: list[tuple[str, str, str, float]]) -> tuple[Path, Path]:
    root = tmp_path / "ws"
    registry = root / pd.REGISTRY_RELATIVE
    registry.parent.mkdir(parents=True)
    registry.write_text(
        json.dumps(
            {
                "projects": [
                    {"project_id": "DJ-2026-101", "project_root": "0100_PLC自动化/DJ-2026-101_甲"},
                    {"project_id": "SW-2026-008", "project_root": "tool"},
                ]
            }
        ),
        encoding="utf-8",
    )
    change_dir = root / "0100_PLC自动化" / "DJ-2026-101_甲" / "11_监控" / "01_变更管理"
    (change_dir / "02_变更记录").mkdir(parents=True)
    (change_dir / "02_变更记录" / "02_业务变更记录.md").write_text(
        "| 编号 | 提出日期 | 类型 | 改了什么（原来 → 改成） | 状态 |\n|---|---|---|---|---|\n"
        "| BC-DJ-2026-101-001 | 2026-10-01 | 参数 | 节拍 30 s → 28 s | 待批 |\n",
        encoding="utf-8",
    )
    (change_dir / "03_实施卡").mkdir()
    (change_dir / "03_实施卡" / "CARD-DJ-2026-101-001_急停.md").write_text(
        "# 实施卡 CARD-DJ-2026-101-001：急停\n\n> 状态：草稿\n", encoding="utf-8"
    )
    (root / "0100_PLC自动化" / "DJ-2026-102_乙").mkdir(parents=True)

    db = root / pd.DB_RELATIVE
    db.parent.mkdir(parents=True)
    connection = sqlite3.connect(db)
    connection.execute("PRAGMA journal_mode = WAL")
    connection.executescript(DDL)
    for index, (project, state, title, age) in enumerate(missions):
        work = f"WORK-{index}"
        run = f"RUN-{index}"
        connection.execute(
            "INSERT INTO work_items VALUES (?, ?, ?, 'IN_PROGRESS', ?)",
            (work, project, title, _iso(age)),
        )
        connection.execute(
            "INSERT INTO run_items VALUES (?, ?, 'RUNNING', 'Trae', 'wt', ?)",
            (run, work, _iso(age)),
        )
        connection.execute("INSERT INTO execution_leases VALUES (?, ?)", (run, _iso(age - 0.01)))
        connection.execute(
            "INSERT INTO checkpoints VALUES (?, ?, 1, '干到一半')", (f"CK-{index}", run)
        )
        connection.execute(
            "INSERT INTO mission_items VALUES (?, ?, ?, ?, ?, ?)",
            (f"MISSION-{index}", project, title, state, work, _iso(age)),
        )
    connection.commit()
    connection.close()
    return root, db


def _digest(path: Path) -> tuple[str, int]:
    return hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns


def test_ledger_is_never_written(tmp_path: Path) -> None:
    root, db = _workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    before = _digest(db)
    neighbours = sorted(path.name for path in db.parent.iterdir())
    out = tmp_path / "board.html"
    assert (
        pd.main(["--root", str(root), "--out", str(out), "--now", NOW.isoformat(), "--no-git"]) == 0
    )
    assert _digest(db) == before
    assert sorted(path.name for path in db.parent.iterdir()) == neighbours
    connection = pd.open_ledger_read_only(db)
    with pytest.raises(sqlite3.OperationalError):
        connection.execute("DELETE FROM mission_items")
    connection.close()


def test_missing_ledger_is_not_created(tmp_path: Path) -> None:
    root, db = _workspace(tmp_path, [])
    db.unlink()
    for suffix in ("-wal", "-shm"):
        Path(str(db) + suffix).unlink(missing_ok=True)
    board = pd.build_board(root, db, NOW, use_git=False, use_legacy=False)
    assert not db.exists()
    assert "没找到账本" in board.ledger_note
    with pytest.raises(FileNotFoundError):
        pd.open_ledger_read_only(db)


def test_four_columns_and_at_most_three_decisions(tmp_path: Path) -> None:
    root, db = _workspace(
        tmp_path,
        [
            ("DJ-2026-101", "ACTIVE", "在干的", 0.1),
            ("DJ-2026-101", "ACCEPTANCE_PENDING", "待验收", 1),
            ("DJ-2026-101", "AWAITING_APPROVAL", "待批准", 2),
            ("DJ-2026-101", "DRAFT", "草稿", 0.5),
            ("DJ-2026-101", "CLOSED", "关了", 3),
        ],
    )
    board = pd.build_board(root, db, NOW, use_git=False, use_legacy=False)
    project = next(p for p in board.projects if p.project_id == "DJ-2026-101")
    columns = [m.column for m in sorted(project.missions, key=lambda m: m.mission_id)]
    assert columns == ["在干", "等你", "等你", "等你", "已关"]
    # 3 张等你的卡 + 1 条待批业务变更 = 4 件，只给 3 件，最久的在前（业务变更 10-01 提出）。
    assert len(board.decisions) == 3
    assert board.decision_overflow == 1
    assert board.decisions[0].ask.startswith("批准业务变更 BC-DJ-2026-101-001")
    assert [d.ask for d in board.decisions[1:]] == ["批准范围", "验收结果"]


def test_lamps(tmp_path: Path) -> None:
    root, db = _workspace(tmp_path, [("DJ-2026-101", "BLOCKED", "卡住了", 0.2)])
    board = pd.build_board(root, db, NOW, use_git=False, use_legacy=False)
    by_id = {p.project_id: p for p in board.projects}
    assert pd.lamp(by_id["DJ-2026-101"], NOW)[0] == "red"
    assert by_id["DJ-2026-101"].missions[0].column == "等你"
    assert by_id["DJ-2026-102"].registered is False
    assert pd.lamp(by_id["DJ-2026-102"], NOW)[0] == "idle"
    assert by_id["SW-2026-008"].tool is True


def test_stale_run_is_reported_as_leftover(tmp_path: Path) -> None:
    root, db = _workspace(tmp_path, [("DJ-2026-101", "CLOSED", "早关了", 30)])
    board = pd.build_board(root, db, NOW, use_git=False, use_legacy=False)
    project = next(p for p in board.projects if p.project_id == "DJ-2026-101")
    assert [item.what for item in project.attention] == ["执行记录没结账"]
    assert pd.lamp(project, NOW)[0] == "amber"


def test_page_has_no_action_controls(tmp_path: Path) -> None:
    root, db = _workspace(tmp_path, [("DJ-2026-101", "AWAITING_APPROVAL", "待批准", 1)])
    board = pd.add_examples(pd.build_board(root, db, NOW, use_git=False, use_legacy=False), NOW)
    page = pd.render_page(board, timezone.utc)
    lowered = page.lower()
    for forbidden in ("<button", "<form", "onclick", "fetch(", "codex"):
        assert forbidden not in lowered
    assert "示例" not in pd.render_page(
        pd.build_board(root, db, NOW, use_git=False, use_legacy=False), timezone.utc
    )


class _FakeLegacyService:
    """冒充老驾驶舱后台：记下被调了哪些方法，只给 snapshot()。"""

    calls: list[str] = []

    def __init__(self, root: Path) -> None:
        self.root = root

    def __getattr__(self, name: str) -> object:
        _FakeLegacyService.calls.append(name)
        raise AssertionError(f"看板不许调老后台的 {name}")

    def snapshot(self) -> SimpleNamespace:
        _FakeLegacyService.calls.append("snapshot")
        card = SimpleNamespace(
            project_id="DJ-2026-101",
            mission_id="MISSION-0",
            milestone="验收",
            progress="待你验收",
            risk="低：在既定授权范围内",
            verification="已保存验证证据",
            current_owner="trae:cn",
            next_user_action="确认验收",
            user_action=SimpleNamespace(value="REVIEW_ESCALATION"),
        )
        pending = SimpleNamespace(
            project_id="DJ-2026-101", objective="新增报警汇总", submitted_at=_iso(5)
        )
        return SimpleNamespace(projects=(card,), pending_cards=(pending,), notices=("提示一条",))


def test_legacy_backend_wording_is_reused_without_duplicates(tmp_path: Path) -> None:
    root, db = _workspace(tmp_path, [("DJ-2026-101", "ACCEPTANCE_PENDING", "握手断线", 1)])
    _FakeLegacyService.calls = []
    board = pd.build_board(root, db, NOW, use_git=False, legacy_factory=_FakeLegacyService)
    assert _FakeLegacyService.calls == ["snapshot"]
    assert [(d.ask, d.subject) for d in board.decisions] == [
        ("批准业务变更 BC-DJ-2026-101-001", "节拍 30 s → 28 s"),
        ("批准范围", "新增报警汇总"),
        ("看升级的事", "握手断线"),
    ]
    assert board.decision_overflow == 0
    page = pd.render_page(board, timezone.utc)
    assert "阶段 验收 · 风险 低：在既定授权范围内" in page
    assert "提示一条" in page


def test_legacy_backend_failure_falls_back(tmp_path: Path) -> None:
    root, db = _workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "在干的", 0.1)])

    def broken(_root: Path) -> object:
        raise ImportError("no PySide6")

    board = pd.build_board(root, db, NOW, use_git=False, legacy_factory=broken)
    assert "没接上老驾驶舱后台（ImportError）" in board.legacy_note
    assert board.projects and all(p.legacy is None for p in board.projects)


def test_legacy_backend_is_skipped_for_a_foreign_ledger(tmp_path: Path) -> None:
    root, db = _workspace(tmp_path, [])
    other = tmp_path / "copy.db"
    other.write_bytes(db.read_bytes())
    _FakeLegacyService.calls = []
    pd.build_board(root, other, NOW, use_git=False, legacy_factory=_FakeLegacyService)
    assert _FakeLegacyService.calls == []


def test_recent_events_and_change_matrix(tmp_path: Path) -> None:
    root, db = _workspace(
        tmp_path,
        [("DJ-2026-101", "CLOSED", "这周收口的", 2), ("DJ-2026-101", "CLOSED", "上个月的", 30)],
    )
    board = pd.build_board(root, db, NOW, use_git=False, use_legacy=False)
    events = pd.recent_events(board)
    assert [event[2] for event in events] == ["已收口：这周收口的"]
    page = pd.render_page(board, timezone.utc)
    assert '<td class="mono">BC-DJ-2026-101-001</td>' in page
    assert "点开看全部 1 条变更" in page


# ---------------------------------------------------------------- 账本读法可切换（TD-105）


class _FakeStore:
    """冒充 ContinuityStore：只给 _read_connection 和 close_read_snapshot，记下调用顺序。"""

    calls: list[str] = []

    def __init__(self, root: Path, db_path: Path) -> None:
        _FakeStore.calls.append(f"init {root.name} {db_path.name}")
        self.db_path = db_path

    def _read_connection(self):  # noqa: ANN202
        _FakeStore.calls.append("_read_connection")
        return pd.copy_ledger_connection(self.db_path.parent, self.db_path)  # 真 Store 也是先拷快照再开

    def close_read_snapshot(self) -> None:
        _FakeStore.calls.append("close_read_snapshot")

    def initialize(self) -> None:
        raise AssertionError("看板不许 initialize 账本")


class _OldStore(_FakeStore):
    """TD-105 之前的 Store：没有 close_read_snapshot。"""

    close_read_snapshot = None  # type: ignore[assignment]


def test_ledger_reader_auto_follows_the_td105_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    assert pd.td105_merged(_FakeStore) is True
    assert pd.td105_merged(_OldStore) is False  # 老 Store 的 _read_connection 在 Windows 上会把写账本的锁在外面，不用
    assert pd.td105_merged(None) is False
    monkeypatch.setattr(pd, "continuity_store_class", lambda: _OldStore)
    assert pd.choose_ledger_reader("auto") == ("copy", pd.copy_ledger_connection)
    monkeypatch.setattr(pd, "continuity_store_class", lambda: _FakeStore)
    assert pd.choose_ledger_reader("auto") == ("store", pd.store_ledger_connection)
    # Store 只认工作空间自己的账本；看别处拷来的账本（--db 指到外面）auto 仍走 copy
    root = Path("/ws")
    assert pd.choose_ledger_reader("auto", root, root / ".auto-pm" / "continuity.db")[0] == "store"
    assert pd.choose_ledger_reader("auto", root, Path("/elsewhere") / "continuity.db")[0] == "copy"
    assert pd.choose_ledger_reader("copy")[0] == "copy" and pd.choose_ledger_reader("store")[0] == "store"
    with pytest.raises(ValueError):
        pd.choose_ledger_reader("legacy")
    # 现在这条分支上 auto 选什么，只看真 Store 有没有 TD-105 的标记
    monkeypatch.undo()
    expected = "store" if pd.td105_merged(pd.continuity_store_class()) else "copy"
    assert pd.choose_ledger_reader("auto")[0] == expected


def test_store_reader_only_calls_read_connection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, db = _workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    before = _digest(db)
    neighbours = sorted(path.name for path in db.parent.iterdir())
    _FakeStore.calls = []
    monkeypatch.setattr(pd, "continuity_store_class", lambda: _FakeStore)
    board = pd.build_board(root, db, NOW, use_git=False, use_legacy=False, ledger_reader="store")
    assert _FakeStore.calls == ["init ws continuity.db", "_read_connection", "close_read_snapshot"]
    assert "TD-105 严格只读快照" in board.ledger_note
    assert [m.title for p in board.projects for m in p.missions] == ["写通讯层"]
    assert _digest(db) == before
    assert sorted(path.name for path in db.parent.iterdir()) == neighbours
    # 同一份账本，两种读法读出来的卡一样
    copied = pd.build_board(root, db, NOW, use_git=False, use_legacy=False, ledger_reader="copy")
    assert "本地拷贝" in copied.ledger_note
    assert [m.title for p in copied.projects for m in p.missions] == ["写通讯层"]


def test_store_reader_fits_the_real_continuity_store(tmp_path: Path) -> None:
    """接口要对得上真 Store（现在是 main 的版本；TD-105 合入后自动换成新读法，不用改这里）。"""
    store_class = pd.continuity_store_class()
    assert store_class is not None and hasattr(store_class, "_read_connection")
    root, db = _workspace(tmp_path, [("DJ-2026-101", "BLOCKED", "卡住了", 0.5)])
    before = _digest(db)
    board = pd.build_board(root, db, NOW, use_git=False, use_legacy=False, ledger_reader="store")
    assert [m.state for p in board.projects for m in p.missions] == ["BLOCKED"]
    assert _digest(db) == before
    assert pd.main(["--root", str(root), "--out", str(tmp_path / "b.html"), "--now", NOW.isoformat(),
                    "--no-git", "--no-legacy", "--ledger-reader", "store"]) == 0
    assert _digest(db) == before
