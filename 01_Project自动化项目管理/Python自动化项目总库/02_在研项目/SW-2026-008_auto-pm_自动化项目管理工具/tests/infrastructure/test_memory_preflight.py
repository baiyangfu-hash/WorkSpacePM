"""The memory preflight: the two thresholds, the plain refusal, the Linux readers, and that nothing can switch it off (11-03 laptop memory P1)."""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

import pytest

from auto_pm.infrastructure import memory_preflight as mp

GIB = mp.GIB


def _snap(committed_gib: float, limit_gib: float = 100.0, physical_gib: float = 31.3) -> mp.CommitSnapshot:
    return mp.CommitSnapshot(int(committed_gib * GIB), int(limit_gib * GIB), int(physical_gib * GIB))


@pytest.mark.parametrize(
    ("committed", "limit", "ok", "fired"),
    [
        (20.0, 100.0, True, []),
        (34.9, 100.0, True, []),
        (35.0, 100.0, False, ["≥ 35 GiB"]),  # the absolute rule is inclusive
        (50.0, 100.0, False, ["≥ 35 GiB"]),
        (30.0, 35.0, False, ["占当前提交上限"]),  # 85.7% of a 35 GiB limit, below the absolute rule
        (30.0, 40.0, True, []),  # 75%
        (34.0, 40.0, False, ["占当前提交上限"]),  # exactly 85%: the ratio rule is inclusive
        (36.0, 40.0, False, ["≥ 35 GiB", "占当前提交上限"]),  # both rules at once
    ],
)
def test_the_two_rules_either_one_refuses(committed: float, limit: float, ok: bool, fired: list[str]) -> None:
    verdict = mp.check(_snap(committed, limit))

    assert verdict.ok is ok
    assert len(verdict.reasons) == len(fired)
    for fragment, reason in zip(fired, verdict.reasons, strict=True):
        assert fragment in reason


def test_a_limit_of_zero_cannot_trip_the_ratio_rule() -> None:
    assert mp.check(_snap(1.0, 0.0)).ok is True


def test_the_five_biggest_processes_are_listed_only_on_a_refusal() -> None:
    asked: list[int] = []
    use = tuple(mp.ProcessUse(pid=100 + n, name=f"p{n}.exe", committed=(9 - n) * GIB) for n in range(5))

    def lister(count: int) -> tuple[mp.ProcessUse, ...]:
        asked.append(count)
        return use

    healthy = mp.run_preflight(read=lambda: _snap(5.0), list_top=lister)
    hot = mp.run_preflight(read=lambda: _snap(40.0), list_top=lister)

    assert healthy.ok and healthy.top == () and asked == [5]  # asked once: the refusal, not the healthy reading
    assert not hot.ok and hot.top == use


def test_the_refusal_says_what_was_read_which_rule_fired_the_top_five_and_what_to_do() -> None:
    use = tuple(mp.ProcessUse(pid=100 + n, name=f"p{n}.exe", committed=(9 - n) * GIB) for n in range(5))
    text = mp.refusal_text(mp.Preflight(False, mp.check(_snap(38.2, 63.3)).reasons, _snap(38.2, 63.3), use))

    assert text.startswith("拒绝启动")
    assert "38.2 GiB" in text and "63.3 GiB" in text and "60%" in text and "31.3 GiB" in text
    assert "≥ 35 GiB" in text
    positions = [text.index(f"p{n}.exe") for n in range(5)]
    assert positions == sorted(positions) and "PID 100" in text and "9.0 GiB" in text
    assert "long-run start" in text and "没有“强行继续”的选项" in text


def test_nothing_can_be_read_is_refused_on_windows_and_unverified_elsewhere() -> None:
    windows = mp.run_preflight(read=lambda: None, platform="win32")
    other = mp.run_preflight(read=lambda: None, platform="linux")

    assert not windows.ok and "读不到已提交内存" in windows.reasons[0]
    assert other.ok and "未验证" in other.unverified


def test_require_headroom_raises_with_the_refusal_text_and_returns_the_unverified_note() -> None:
    with pytest.raises(mp.MemoryPreflightRefusedError, match="拒绝启动"):
        mp.require_headroom(run=lambda: mp.run_preflight(read=lambda: _snap(60.0), list_top=lambda _n: ()))

    assert mp.require_headroom(run=lambda: mp.run_preflight(read=lambda: None, platform="linux")) != ""
    assert mp.require_headroom(run=lambda: mp.run_preflight(read=lambda: _snap(1.0))) == ""


def test_there_is_no_switch_to_continue_anyway() -> None:
    """The check exists to stop agents, so no argument, environment variable or option may turn it off."""

    for function in (mp.run_preflight, mp.require_headroom, mp.check):
        names = set(inspect.signature(function).parameters)
        assert not names & {"force", "skip", "override", "enabled", "disable"}
    source = Path(mp.__file__).read_text(encoding="utf-8")
    assert "os.environ" not in source and "getenv" not in source


def test_the_linux_readers_use_proc(tmp_path: Path) -> None:
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal:       32768000 kB\nCommitLimit:    66387968 kB\nCommitted_AS:   40000000 kB\nOther: x\n", encoding="utf-8")
    proc = tmp_path / "proc"
    for pid, name, kib in ((11, "small", 100), (12, "big", 9_000_000), (13, "mid", 5_000)):
        (proc / str(pid)).mkdir(parents=True)
        (proc / str(pid) / "status").write_text(f"Name:\t{name}\nVmData:\t{kib} kB\n", encoding="utf-8")
    (proc / "self").mkdir()  # not a pid
    (proc / "99").mkdir()  # a process that vanished: no status file

    snapshot = mp._read_commit_linux(meminfo)
    top = mp._top_linux(2, proc)

    assert snapshot == mp.CommitSnapshot(40_000_000 * 1024, 66_387_968 * 1024, 32_768_000 * 1024)
    assert [use.name for use in top] == ["big", "mid"] and top[0].committed == 9_000_000 * 1024
    assert mp._read_commit_linux(tmp_path / "missing") is None
    meminfo.write_text("MemTotal: 1 kB\n", encoding="utf-8")
    assert mp._read_commit_linux(meminfo) is None


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="reads this host's /proc")
def test_the_real_linux_reading_is_plausible() -> None:
    snapshot = mp._read_commit_linux()  # not read_commit: conftest swaps that for a healthy reading in every test

    assert snapshot is not None and 0 < snapshot.committed and snapshot.physical > 0


def test_the_module_loads_by_path_without_the_package_and_reads_nothing_on_import(tmp_path: Path) -> None:
    """scripts/long_gate.py loads this file by path; importing it must not touch the machine."""

    spec = importlib.util.spec_from_file_location("preflight_by_path", mp.__file__)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["preflight_by_path"] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop("preflight_by_path", None)

    assert module.ABSOLUTE_GIB == 35.0 and module.RATIO == 0.85


def test_undecodable_bytes_in_proc_make_a_reading_unreadable_not_silently_replaced(tmp_path: Path) -> None:
    """DEV-ENC-001 / the lenient-decoding ratchet: a broken /proc file is "cannot read", never a guess built from replacement characters."""

    meminfo = tmp_path / "meminfo"
    meminfo.write_bytes(b"MemTotal: 1 kB\nCommitLimit: 2 kB\nCommitted_AS: 3 kB\n\xff\xfe\n")
    proc = tmp_path / "proc"
    (proc / "5").mkdir(parents=True)
    (proc / "5" / "status").write_bytes(b"Name:\t\xff\nVmData:\t10 kB\n")

    assert mp._read_commit_linux(meminfo) is None
    assert mp._top_linux(5, proc) == ()
