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
    asked: list[str] = []
    everyone = tuple(mp.ProcessUse(pid=100 + n, name=f"p{n}.exe", committed=(9 - n) * GIB) for n in range(8))  # p0..p7: 9..2 GiB

    def lister() -> tuple[mp.ProcessUse, ...]:
        asked.append("list")
        return tuple(reversed(everyone))  # deliberately unsorted: the module sorts

    healthy = mp.run_preflight(read=lambda: _snap(5.0), list_all=lister)
    hot = mp.run_preflight(read=lambda: _snap(40.0), list_all=lister)

    assert healthy.ok and healthy.top == () and healthy.attributed is None
    assert asked == ["list"]  # asked once: the refusal, not the healthy reading
    assert not hot.ok and hot.top == everyone[:5]
    assert hot.attributed == sum(use.committed for use in everyone)


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
        mp.require_headroom(run=lambda: mp.run_preflight(read=lambda: _snap(60.0), list_all=lambda: ()))

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
    top = mp._all_linux(proc)[:2]

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
    assert mp._all_linux(proc) == ()


def test_the_refusal_names_the_commit_that_no_process_owns() -> None:
    """11-03 live reading: the five biggest held 2.7 GiB, all processes about 14 GiB, committed 28 GiB; the top five cannot point at the culprit."""

    everyone = tuple(mp.ProcessUse(pid=n, name=f"p{n}.exe", committed=2 * GIB) for n in range(1, 8))  # 14 GiB in total
    verdict = mp.run_preflight(read=lambda: _snap(36.0), list_all=lambda: everyone)

    text = mp.refusal_text(verdict)

    assert "未归属进程的提交量：22.0 GiB" in text
    assert "已提交 36.0 − 能读到的进程私有合计 14.0" in text
    assert "未超过 25 GiB" in text and "**" not in text and "fast_watch" not in text  # 22 GiB is under the 25 GiB line: no alarm


def test_the_refusal_is_bold_and_names_the_next_step_only_above_25_gib_unowned() -> None:
    everyone = tuple(mp.ProcessUse(pid=n, name=f"p{n}.exe", committed=1 * GIB) for n in range(1, 11))  # 10 GiB in total
    over = mp.refusal_text(mp.run_preflight(read=lambda: _snap(36.0), list_all=lambda: everyone))  # 26 GiB unowned
    edge = mp.refusal_text(mp.run_preflight(read=lambda: _snap(35.0), list_all=lambda: everyone))  # exactly 25 GiB unowned

    assert "**未归属进程的提交量 26.0 GiB，超过 25 GiB" in over and "先关闭 Trae、浏览器，并保留 fast_watch 日志" in over
    assert "**" not in edge and "未超过 25 GiB" in edge  # the line is "more than 25", so 25.0 does not trigger it
    assert "很大" not in over and "很大" not in edge


def test_read_unowned_gib_is_committed_minus_the_readable_processes_and_unknown_without_either(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mp, "read_commit", lambda: _snap(30.0))
    monkeypatch.setattr(mp, "all_processes", lambda: (mp.ProcessUse(1, "a.exe", 4 * GIB), mp.ProcessUse(2, "b.exe", 6 * GIB)))
    assert mp.read_unowned_gib() == 20.0

    monkeypatch.setattr(mp, "all_processes", lambda: ())
    assert mp.read_unowned_gib() is None
    monkeypatch.setattr(mp, "read_commit", lambda: None)
    monkeypatch.setattr(mp, "all_processes", lambda: (mp.ProcessUse(1, "a.exe", 4 * GIB),))
    assert mp.read_unowned_gib() is None


def test_the_unowned_line_is_left_out_when_no_process_list_is_available_and_never_goes_negative() -> None:
    hot = _snap(40.0)
    without_list = mp.refusal_text(mp.Preflight(False, mp.check(hot).reasons, hot, (), attributed=None))
    over = mp.refusal_text(mp.Preflight(False, mp.check(hot).reasons, hot, (), attributed=50 * GIB))  # shared pages can make the sum exceed it

    assert "未归属" not in without_list
    assert "未归属进程的提交量：0.0 GiB" in over


def test_a_test_gets_the_healthy_stand_in_reading_unless_it_asks_for_the_real_machine() -> None:
    """The autouse stand-in (conftest) answers a healthy 4 GiB; only ``real_machine`` tests may see the real reader."""

    assert mp.read_commit().committed == 4 * mp.GIB  # type: ignore[union-attr]


@pytest.mark.real_machine
def test_a_real_machine_test_gets_the_real_reader_not_the_stand_in() -> None:
    assert mp.read_commit.__name__ == "read_commit"  # the stand-in is a lambda
