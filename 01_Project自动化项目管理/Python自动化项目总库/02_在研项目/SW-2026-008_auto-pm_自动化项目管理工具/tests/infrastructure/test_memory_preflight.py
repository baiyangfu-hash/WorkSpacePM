"""The memory preflight: the two thresholds, the plain refusal, the Linux readers, and that nothing can switch it off (11-03 laptop memory P1)."""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

import pytest

from auto_pm.infrastructure import memory_preflight as mp

GIB = mp.GIB


def _snap(committed_gib: float, limit_gib: float = 100.0, physical_gib: float = 31.3, available_gib: float | None = None) -> mp.CommitSnapshot:
    available = None if available_gib is None else int(available_gib * GIB)
    return mp.CommitSnapshot(int(committed_gib * GIB), int(limit_gib * GIB), int(physical_gib * GIB), available)


@pytest.mark.parametrize(
    ("committed", "limit", "available", "ok", "fired"),
    [
        (20.0, 100.0, 16.0, True, []),
        (79.9, 100.0, 8.0, True, []),
        (80.0, 100.0, 8.0, False, ["占当前提交上限"]),  # exactly 80%: the ratio rule is inclusive
        (10.0, 100.0, 3.9, False, ["可用物理内存"]),
        (10.0, 100.0, 4.0, True, []),  # exactly 4 GiB available is still enough
        (50.0, 100.0, None, True, []),  # no available reading: only the ratio rule can speak
        (35.0, 100.0, 12.0, True, []),  # D-207: 35 GiB committed is no reason to refuse (the old absolute rule is gone)
        (90.0, 100.0, 2.0, False, ["可用物理内存", "占当前提交上限"]),  # both rules at once
    ],
)
def test_the_two_rules_either_one_refuses(committed: float, limit: float, available: float | None, ok: bool, fired: list[str]) -> None:
    verdict = mp.check(_snap(committed, limit, available_gib=available), thresholds=mp.Thresholds(4.0, 0.80))

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
    hot = mp.run_preflight(read=lambda: _snap(40.0, 45.0), list_all=lister)

    assert healthy.ok and healthy.top == () and healthy.attributed is None
    assert asked == ["list"]  # asked once: the refusal, not the healthy reading
    assert not hot.ok and hot.top == everyone[:5]
    assert hot.attributed == sum(use.committed for use in everyone)


def test_the_refusal_says_what_was_read_which_rule_fired_the_top_five_and_what_to_do() -> None:
    use = tuple(mp.ProcessUse(pid=100 + n, name=f"p{n}.exe", committed=(9 - n) * GIB) for n in range(5))
    reading = _snap(38.2, 63.3, available_gib=2.5)
    text = mp.refusal_text(mp.Preflight(False, mp.check(reading, thresholds=mp.Thresholds(4.0, 0.80)).reasons, reading, use))

    assert text.startswith("拒绝启动")
    assert "38.2 GiB" in text and "63.3 GiB" in text and "60%" in text and "31.3 GiB" in text and "可用物理内存 2.5 GiB" in text
    assert "可用物理内存 2.5 GiB < 4 GiB" in text
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
        mp.require_headroom(run=lambda: mp.run_preflight(read=lambda: _snap(60.0, 64.0), list_all=lambda: ()))

    assert mp.require_headroom(run=lambda: mp.run_preflight(read=lambda: None, platform="linux")) != ""
    assert mp.require_headroom(run=lambda: mp.run_preflight(read=lambda: _snap(1.0))) == ""


def test_d168_require_headroom_arms_the_caller_only_after_a_pass_and_only_when_asked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, float | None]] = []
    monkeypatch.setattr(mp, "arm", lambda label, *, timeout_seconds=None: seen.append((label, timeout_seconds)))
    ok = lambda: mp.run_preflight(read=lambda: _snap(1.0))  # noqa: E731
    mp.require_headroom(run=ok)
    assert seen == []
    mp.require_headroom(run=ok, label="pm-verify", timeout_seconds=7)
    assert seen == [("pm-verify", 7)]
    with pytest.raises(mp.MemoryPreflightRefusedError):
        mp.require_headroom(run=lambda: mp.run_preflight(read=lambda: _snap(60.0, 64.0), list_all=lambda: ()), label="pm-verify")
    assert len(seen) == 1  # a refused preflight arms nothing


def test_there_is_no_switch_to_continue_anyway() -> None:
    """The check exists to stop agents, so no argument, environment variable or option may turn it off."""

    for function in (mp.run_preflight, mp.require_headroom, mp.check):
        names = set(inspect.signature(function).parameters)
        assert not names & {"force", "skip", "override", "enabled", "disable"}
    source = Path(mp.__file__).read_text(encoding="utf-8")
    assert "os.environ" not in source and "getenv" not in source


def test_the_linux_commit_limit_is_only_a_limit_in_strict_overcommit_mode(tmp_path: Path) -> None:
    """Default overcommit makes CommitLimit advisory (a 16 GiB sandbox reports 8 GiB): the 80% rule must not fire on it."""

    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal: 16000000 kB\nCommitLimit: 8000000 kB\nCommitted_AS: 7500000 kB\n", encoding="utf-8")
    heuristic = tmp_path / "heuristic"
    heuristic.write_text("0\n", encoding="ascii")
    strict = tmp_path / "strict"
    strict.write_text("2\n", encoding="ascii")

    advisory = mp._read_commit_linux(meminfo, heuristic)
    hard = mp._read_commit_linux(meminfo, strict)
    unknown = mp._read_commit_linux(meminfo, tmp_path / "missing")

    assert advisory is not None and advisory.limit == 0 and mp.check(advisory).ok  # 7.15 GiB committed, no limit to compare with
    assert hard is not None and hard.limit == 8_000_000 * 1024 and not mp.check(hard).ok  # 94% of a real limit
    assert unknown is not None and unknown.limit == 0


def test_any_failure_of_a_windows_reading_is_unreadable_not_a_stack_trace() -> None:
    import ctypes

    def broken_arguments() -> mp.CommitSnapshot:
        raise ctypes.ArgumentError("argument 1: wrong type")

    def missing_symbol() -> mp.CommitSnapshot:
        raise AttributeError("function 'GetPerformanceInfo' not found")

    assert mp._guarded(broken_arguments, None) is None
    assert mp._guarded(missing_symbol, None) is None
    assert mp._guarded(lambda: 3, 0) == 3
    assert mp._guarded(lambda: int("x"), 7) == 7  # ValueError
    assert mp._guarded(lambda: [][0], 8) == 8  # IndexError


def test_the_linux_readers_use_proc(tmp_path: Path) -> None:
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal:       32768000 kB\nCommitLimit:    66387968 kB\nCommitted_AS:   40000000 kB\nOther: x\n", encoding="utf-8")
    proc = tmp_path / "proc"
    for pid, name, kib in ((11, "small", 100), (12, "big", 9_000_000), (13, "mid", 5_000)):
        (proc / str(pid)).mkdir(parents=True)
        (proc / str(pid) / "status").write_text(f"Name:\t{name}\nVmData:\t{kib} kB\n", encoding="utf-8")
    (proc / "self").mkdir()  # not a pid
    (proc / "99").mkdir()  # a process that vanished: no status file

    strict = tmp_path / "overcommit_strict"
    strict.write_text("2\n", encoding="ascii")
    snapshot = mp._read_commit_linux(meminfo, strict)
    top = mp._all_linux(proc)[:2]

    assert snapshot == mp.CommitSnapshot(40_000_000 * 1024, 66_387_968 * 1024, 32_768_000 * 1024, None)  # this file has no MemAvailable line
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

    assert module.DEFAULT_MIN_AVAILABLE_GIB == 4.0 and module.DEFAULT_MAX_COMMIT_RATIO == 0.80


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
    verdict = mp.run_preflight(read=lambda: _snap(36.0, 40.0), list_all=lambda: everyone)

    text = mp.refusal_text(verdict)

    assert "未归属进程的提交量：22.0 GiB" in text
    assert "已提交 36.0 − 能读到的进程私有合计 14.0" in text
    assert "未超过 25 GiB" in text and "**" not in text and "fast_watch" not in text  # 22 GiB is under the 25 GiB line: no alarm


def test_the_refusal_is_bold_and_names_the_next_step_only_above_25_gib_unowned() -> None:
    everyone = tuple(mp.ProcessUse(pid=n, name=f"p{n}.exe", committed=1 * GIB) for n in range(1, 11))  # 10 GiB in total
    over = mp.refusal_text(mp.run_preflight(read=lambda: _snap(36.0, 40.0), list_all=lambda: everyone))  # 26 GiB unowned
    edge = mp.refusal_text(mp.run_preflight(read=lambda: _snap(35.0, 40.0), list_all=lambda: everyone))  # exactly 25 GiB unowned

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
    hot = _snap(40.0, 45.0)
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


_REAL_MACHINE_FILES = {"infrastructure/test_long_run_core.py", "infrastructure/test_memory_preflight.py"}


def test_the_real_machine_marker_is_used_only_by_the_files_that_compare_with_the_system() -> None:
    """The marker switches the stand-in reading off (conftest); a new user of it is a decision, so it is listed here (audit 575 P3)."""

    import re

    tests_root = Path(__file__).resolve().parents[1]
    users = {
        path.relative_to(tests_root).as_posix()
        for path in tests_root.rglob("*.py")
        if re.search(r"mark\.real_machine", path.read_text(encoding="utf-8", errors="strict"))
    }

    assert users <= _REAL_MACHINE_FILES, f"real_machine 标记出现在名单之外：{sorted(users - _REAL_MACHINE_FILES)}"


def test_d207_linux_available_memory_comes_from_memavailable(tmp_path: Path) -> None:
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal: 32768000 kB\nMemAvailable: 3000000 kB\nCommitLimit: 66387968 kB\nCommitted_AS: 10000000 kB\n", encoding="utf-8")

    snapshot = mp._read_commit_linux(meminfo, tmp_path / "missing")

    assert snapshot is not None and snapshot.available == 3_000_000 * 1024
    assert not mp.check(snapshot, thresholds=mp.Thresholds(4.0, 0.80)).ok


# ── the parameter file (D-205 / D-207) ──────────────────


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "memory_preflight.json"
    path.write_text(text, encoding="utf-8")
    return path


def test_d207_the_checked_in_parameter_file_is_valid_and_carries_the_ruled_numbers() -> None:
    path = mp.parameter_file()

    assert path is not None and path.is_file()
    assert mp.load_thresholds(path) == mp.Thresholds(min_available_gib=4.0, max_commit_ratio=0.80)


def test_d207_no_parameter_file_means_the_built_in_defaults(tmp_path: Path) -> None:
    assert mp.load_thresholds(tmp_path / "absent.json") == mp.Thresholds(4.0, 0.80)


def test_d207_a_valid_file_replaces_the_defaults(tmp_path: Path) -> None:
    assert mp.load_thresholds(_write(tmp_path, '{"min_available_gib": 6, "max_commit_ratio": 0.7}')) == mp.Thresholds(6.0, 0.7)


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("not json", "读不了"),
        ("[1, 2]", "不是 JSON 对象"),
        ('{"min_available_gib": 4}', "max_commit_ratio 缺失"),
        ('{"min_available_gib": "4", "max_commit_ratio": 0.8}', "min_available_gib 缺失或不是数字"),
        ('{"min_available_gib": true, "max_commit_ratio": 0.8}', "min_available_gib 缺失或不是数字"),
        ('{"min_available_gib": 0.5, "max_commit_ratio": 0.8}', "min_available_gib = 0.5 超出合法范围 [1, 16]"),
        ('{"min_available_gib": 17, "max_commit_ratio": 0.8}', "超出合法范围 [1, 16]"),
        ('{"min_available_gib": 4, "max_commit_ratio": 0.4}', "max_commit_ratio = 0.4 超出合法范围 [0.5, 0.95]"),
        ('{"min_available_gib": 4, "max_commit_ratio": 0.99}', "超出合法范围 [0.5, 0.95]"),
        ('{"min_available_gib": 4, "max_commit_ratio": 0.8, "skip": 1}', "不认识的项：skip"),
    ],
)
def test_d207_an_invalid_parameter_file_is_an_error_naming_the_item(tmp_path: Path, text: str, fragment: str) -> None:
    with pytest.raises(mp.MemoryPreflightConfigError, match="memory_preflight.json") as caught:
        mp.load_thresholds(_write(tmp_path, text))

    assert fragment in str(caught.value)


def test_d207_run_preflight_refuses_to_start_on_an_invalid_file_even_when_the_machine_is_healthy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mp, "parameter_file", lambda: _write(tmp_path, '{"min_available_gib": 0, "max_commit_ratio": 0.8}'))
    verdict = mp.run_preflight(read=lambda: _snap(5.0, 100.0, available_gib=30.0))

    assert not verdict.ok and verdict.snapshot is None and "min_available_gib = 0 超出合法范围" in verdict.invalid_config
    text = mp.refusal_text(verdict)
    assert text.startswith("拒绝启动：内存预检的参数文件不能用") and "min_available_gib" in text and "没有“强行继续”的选项" in text
    with pytest.raises(mp.MemoryPreflightRefusedError, match="参数文件不能用"):
        mp.require_headroom(run=lambda: verdict)


def test_d207_run_preflight_applies_the_numbers_of_the_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mp, "parameter_file", lambda: _write(tmp_path, '{"min_available_gib": 10, "max_commit_ratio": 0.9}'))

    assert not mp.run_preflight(read=lambda: _snap(5.0, available_gib=9.0), list_all=lambda: ()).ok  # 9 < 10 GiB (the default 4 GiB would pass)
    assert mp.run_preflight(read=lambda: _snap(85.0, available_gib=12.0), list_all=lambda: ()).ok  # 85% < 90% (the default 80% would refuse)


def test_d207_the_parameter_file_has_a_fixed_place_and_no_environment_or_option_points_elsewhere() -> None:
    assert "path" in inspect.signature(mp.load_thresholds).parameters  # tests only; run_preflight / require_headroom take none
    for function in (mp.run_preflight, mp.require_headroom):
        assert "path" not in inspect.signature(function).parameters and "thresholds" not in inspect.signature(function).parameters
