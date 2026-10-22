"""FB_1030_SafetyManager 逻辑仿真用例（设计草案第 4 节 T1～T13，外加几条边界）。

用 ``st_mini_sim`` 直接执行共享库里的 .scl 源码，仿真时钟按真实毫秒走（FB_TON V3.0.0 语义）。
这不能代替 InoProShop 仿真和用户签字（规范 0.5、12），只是在云端先把逻辑跑一遍。

运行：python -B -m pytest reviews/tools/test_fb1030_safety_manager.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from st_mini_sim import Sim  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
FB_PATH = REPO / "0100_PLC自动化" / "01_SharedLibraries" / "SysLib" / "safety" / "FB_1030_SafetyManager.scl"
SCAN_MS = 10

BIT_REJECT, BIT_EARLY, BIT_RELOCK, BIT_FIELDBUS = 29, 30, 31, 28


class Machine:
    """一台机器 + FB_1030 实例。默认：一个继电器正常、所有急停/光栅/门正常、总线在线、手动。"""

    def __init__(self, src_override: str | None = None, tmp: Path | None = None):
        self.sim = Sim()
        path = FB_PATH
        if src_override is not None:
            path = tmp / "FB_1030_mut.scl"
            path.write_text(src_override, encoding="utf-8")
        self.sim.load(path)
        self.fb = self.sim.new_instance("FB_1030_SafetyManager")
        v = self.fb.vars
        for i in range(8):
            v["i_arrEStopOk"][i] = True
            v["i_arrCurtainOk"][i] = True
            v["i_arrDoorClosed"][i] = True
        v["i_bFieldbusOk"] = True
        self.pulses: list[str] = []
        self.scan()

    # 输入
    def set(self, name: str, value, idx: int | None = None) -> None:
        if idx is None:
            self.fb.vars[name] = value
        else:
            self.fb.vars[name][idx] = value

    def scan(self, n: int = 1) -> None:
        for _ in range(n):
            self.sim.now_ms += SCAN_MS
            self.fb.call()
            if self.out("q_bRunResetPulse"):
                self.pulses.append("reset")
            if self.out("q_bStartPulse"):
                self.pulses.append("start")

    def wait_ms(self, ms: int) -> None:
        self.scan(max(1, ms // SCAN_MS))

    def press(self, btn: str = "i_bResetBtn", idx: int | None = None, hold_scans: int = 2) -> None:
        self.set(btn, True, idx)
        self.scan(hold_scans)
        self.set(btn, False, idx)
        self.scan()

    # 输出
    def out(self, name: str, idx: int | None = None):
        v = self.fb.vars[name]
        return v if idx is None else v[idx]

    @property
    def state(self) -> int:
        return self.out("q_iState")

    def alarm(self, bit: int) -> bool:
        return bool(self.out("q_dwAlarm") >> bit & 1)

    def bring_to_run(self) -> None:
        self.press()                 # 第一次复位
        self.wait_ms(10_000)
        self.press()                 # 第二次复位
        self.press("i_bStartBtn")    # 启动
        assert self.state == 4 and self.out("q_bSafeToRun")


@pytest.fixture
def m() -> Machine:
    return Machine()


# ------------------------------------------------------------------ 上电

def test_power_up_never_runs_by_itself(m: Machine) -> None:
    m.wait_ms(30_000)
    assert m.state == 0
    assert not m.out("q_bSafeToRun")
    assert m.pulses == []


def test_normal_sequence_two_resets_then_start(m: Machine) -> None:
    m.bring_to_run()
    assert m.pulses == ["reset", "start"]
    assert m.out("q_dwAlarm") == 0


# ------------------------------------------------------------------ T1～T8

def test_t1_fault_stops_same_scan(m: Machine) -> None:
    m.bring_to_run()
    m.set("i_arrSafetyFault", True, 0)
    m.scan()  # 同一扫描
    assert not m.out("q_bSafeToRun")
    assert m.out("q_bStopNow")
    assert m.state == 0
    assert m.alarm(24)


def test_t2_feedback_recovers_no_restart(m: Machine) -> None:
    m.bring_to_run()
    m.set("i_arrSafetyFault", True, 0)
    m.scan()
    m.set("i_arrSafetyFault", False, 0)
    m.wait_ms(60_000)
    assert m.state == 0
    assert not m.out("q_bSafeToRun")
    assert m.pulses == ["reset", "start"]  # 没有新的脉冲


def test_t3_reset_rejected_while_fault(m: Machine) -> None:
    m.set("i_arrSafetyFault", True, 0)
    m.scan()
    m.press()                    # 第一次: 只记时刻
    assert m.state == 1
    m.wait_ms(3_000)
    m.press()                    # 继电器还是故障: 不采纳
    assert m.alarm(BIT_REJECT)
    m.wait_ms(10_000)
    m.press()                    # 10 s 后仍故障: 当新的第一次, 仍不出脉冲
    assert "reset" not in m.pulses
    assert not m.out("q_bSafeToRun")


def test_t4_second_reset_after_5s_too_early(m: Machine) -> None:
    m.press()
    m.wait_ms(5_000)
    m.press()
    assert m.alarm(BIT_EARLY)
    assert m.state == 1
    assert "reset" not in m.pulses


def test_t5_second_reset_after_10s_then_start(m: Machine) -> None:
    m.press()
    m.wait_ms(9_900)
    assert m.state == 1          # 不足 10 s
    m.wait_ms(200)
    assert m.state == 2          # 满 10 s 且反馈正常
    m.press()
    assert m.pulses == ["reset"]
    assert m.state == 3 and not m.out("q_bSafeToRun")   # 复位 ≠ 启动
    m.press("i_bStartBtn")
    assert m.pulses == ["reset", "start"]
    assert m.out("q_bSafeToRun")


def test_t5b_early_press_does_not_restart_10s(m: Machine) -> None:
    """10 s 从第一次按复位起算: 中途按一下 (过早) 不重新计时。"""
    m.press()
    m.wait_ms(6_000)
    m.press()                    # 过早
    m.wait_ms(4_200)             # 距第一次已过 10 s
    assert m.state == 2


def test_t6_holding_reset_across_10s_not_accepted(m: Machine) -> None:
    m.press()
    m.set("i_bResetBtn", True)   # 按住不放
    m.wait_ms(15_000)
    assert m.state == 2
    assert "reset" not in m.pulses
    m.set("i_bResetBtn", False)
    m.scan()
    assert "reset" not in m.pulses   # 松开也不算
    m.press()
    assert m.pulses == ["reset"]


def test_start_without_reset_ignored(m: Machine) -> None:
    m.press("i_bStartBtn")
    m.press()
    m.press("i_bStartBtn")
    assert m.state == 1 and not m.out("q_bSafeToRun")


def test_holding_start_before_reset_not_accepted(m: Machine) -> None:
    m.press()
    m.wait_ms(10_000)
    m.set("i_bStartBtn", True)   # 启动先按住
    m.press()                    # 再复位
    m.scan(5)
    assert m.state == 3 and not m.out("q_bSafeToRun")  # 启动只认上升沿


def test_t7_door_opens_in_run_stops(m: Machine) -> None:
    m.bring_to_run()
    m.set("i_arrDoorClosed", False, 2)
    m.scan()
    assert not m.out("q_bSafeToRun") and m.out("q_bStopNow")
    assert m.alarm(8 + 2)
    assert m.state == 0


def test_t8_fieldbus_loss_stops(m: Machine) -> None:
    m.bring_to_run()
    m.set("i_bFieldbusOk", False)
    m.scan()
    assert not m.out("q_bSafeToRun") and m.out("q_bStopNow")
    assert m.alarm(BIT_FIELDBUS)
    m.set("i_bFieldbusOk", True)
    m.wait_ms(20_000)
    assert m.state == 0          # 恢复后不自启


def test_t8b_fieldbus_down_first_reset_rejected(m: Machine) -> None:
    m.set("i_bFieldbusOk", False)
    m.scan()
    m.press()
    assert m.state == 0 and m.alarm(BIT_REJECT)


def test_fault_during_waiting_start_goes_back_to_0(m: Machine) -> None:
    m.press()
    m.wait_ms(10_000)
    m.press()
    assert m.state == 3
    m.set("i_arrSafetyFault", True, 0)
    m.scan()
    m.set("i_arrSafetyFault", False, 0)
    m.press("i_bStartBtn")
    assert m.state == 0 and not m.out("q_bSafeToRun")


def test_reset_in_state3_only_clears_alarm(m: Machine) -> None:
    m.press()
    m.wait_ms(3_000)
    m.press()                    # 过早 -> bit30
    m.wait_ms(8_000)
    m.press()                    # 采纳 -> 清 bit30
    assert m.state == 3 and not m.alarm(BIT_EARLY)
    m.press()                    # 状态 3 再按: 不出脉冲
    assert m.pulses == ["reset"]


# ------------------------------------------------------------------ T12～T13 光栅、多继电器

def test_t12_curtain2_blocked(m: Machine) -> None:
    m.bring_to_run()
    m.set("i_arrCurtainOk", False, 1)
    m.set("i_arrSafetyFault", True, 1)   # 光栅接在第 2 个继电器
    m.scan()
    assert not m.out("q_bSafeToRun")
    assert m.alarm(16 + 1) and m.alarm(24 + 1)
    m.set("i_arrCurtainOk", True, 1)
    m.set("i_arrSafetyFault", False, 1)
    m.bring_to_run()                      # 同一套两次复位 + 启动


def test_curtain_alone_only_alarms(m: Machine) -> None:
    """光栅状态点只报警定位, 停机看继电器反馈 (规范 5.1, 8.1)。"""
    m.bring_to_run()
    m.set("i_arrCurtainOk", False, 0)
    m.scan()
    assert m.alarm(16)
    assert m.out("q_bSafeToRun")


def test_estop_point_alone_only_alarms(m: Machine) -> None:
    """急停第三组触点只报警定位 (规范 2.2), 停机看继电器反馈。"""
    m.bring_to_run()
    m.set("i_arrEStopOk", False, 3)
    m.scan()
    assert m.alarm(3)
    m.set("i_arrSafetyFault", True, 0)
    m.scan()
    assert not m.out("q_bSafeToRun")


def test_t13_second_relay_fault(m: Machine) -> None:
    m.bring_to_run()
    m.set("i_arrSafetyFault", True, 1)
    m.scan()
    assert not m.out("q_bSafeToRun") and m.alarm(25) and not m.alarm(24)
    m.press()
    m.wait_ms(12_000)
    m.press()
    assert "reset" not in m.pulses[2:]   # 恢复前复位不采纳
    m.set("i_arrSafetyFault", False, 1)
    m.bring_to_run()


# ------------------------------------------------------------------ T9～T11 门锁

def test_t9_request_in_auto_ignored(m: Machine) -> None:
    m.set("i_bAutoMode", True)
    m.set("i_bMotionStopped", True)
    m.press("i_arrDoorReqBtn", 0)
    m.wait_ms(3_000)
    assert not m.out("q_arrDoorUnlock", 0)
    assert not m.out("q_arrDoorLamp", 0)


def test_t10_request_blinks_until_stopped(m: Machine) -> None:
    m.press("i_arrDoorReqBtn", 0)
    seen = set()
    t0 = m.sim.now_ms
    flips = 0
    last = m.out("q_arrDoorLamp", 0)
    while m.sim.now_ms - t0 < 3_000:
        m.scan()
        lamp = m.out("q_arrDoorLamp", 0)
        seen.add(lamp)
        flips += lamp != last
        last = lamp
        assert not m.out("q_arrDoorUnlock", 0)   # 动作没停, 不解锁
    assert seen == {True, False}
    assert 5 <= flips <= 7                       # 1 s 周期 -> 3 s 约 6 次翻转
    m.set("i_bMotionStopped", True)
    m.scan()
    assert m.out("q_arrDoorUnlock", 0) and m.out("q_arrDoorLamp", 0)
    m.wait_ms(2_000)
    assert m.out("q_arrDoorLamp", 0)             # 常亮


def test_t10b_request_cancelled_by_auto(m: Machine) -> None:
    m.press("i_arrDoorReqBtn", 4)
    m.set("i_bAutoMode", True)
    m.scan()
    m.set("i_bMotionStopped", True)
    m.wait_ms(1_000)
    assert not m.out("q_arrDoorUnlock", 4) and not m.out("q_arrDoorLamp", 4)


def _open_door0(m: Machine) -> None:
    m.set("i_bMotionStopped", True)
    m.press("i_arrDoorReqBtn", 0)
    assert m.out("q_arrDoorUnlock", 0)
    m.set("i_arrDoorClosed", False, 0)   # 解锁后门锁点 = 0
    m.set("i_arrSafetyFault", True, 0)   # 门锁串在继电器里, 开门 = 回路断
    m.scan()


def test_t11_reset_with_door_open_not_accepted(m: Machine) -> None:
    _open_door0(m)
    m.press()                             # 门还开着
    m.wait_ms(1_200)                      # 1 s 内门锁点没回来
    assert m.out("q_arrDoorUnlock", 0)    # 恢复解锁
    assert m.alarm(BIT_RELOCK) and m.alarm(BIT_REJECT)
    assert m.state == 0


def test_t11_close_door_reset_relocks_then_two_resets(m: Machine) -> None:
    _open_door0(m)
    m.wait_ms(5_000)
    # 关门: 解锁线圈还得电, 门锁点仍 = 0; 按复位撤销解锁, 门锁住后点 = 1
    m.press()
    assert not m.out("q_arrDoorUnlock", 0) and not m.out("q_arrDoorLamp", 0)
    m.set("i_arrDoorClosed", True, 0)
    m.scan()
    assert not m.alarm(BIT_RELOCK)
    assert m.state == 0                    # 锁门这一下不算第一次复位
    m.set("i_arrSafetyFault", False, 0)    # 第二下复位时继电器自己复位
    m.bring_to_run()
    assert not m.out("q_arrDoorUnlock", 0)


def test_door_unlock_impossible_in_auto_even_if_stopped(m: Machine) -> None:
    m.bring_to_run()
    m.set("i_bAutoMode", True)
    m.set("i_bMotionStopped", True)
    m.press("i_arrDoorReqBtn", 7)
    m.wait_ms(2_000)
    assert not any(m.out("q_arrDoorUnlock"))
    assert m.out("q_bSafeToRun")


# ------------------------------------------------------------------ 变异反证：用例真能抓住改坏的块

MUTATIONS = {
    "10 s 改成 5 s": ("RESET_DELAY_MS   : DINT := 10000;", "RESET_DELAY_MS   : DINT := 5000;"),
    "复位不认上升沿": ("t_bResetEdge := s_rtReset.Q;", "t_bResetEdge := i_bResetBtn;"),
    "运行中继电器故障不停机": (
        "IF t_bFault OR NOT t_bDoorsOk OR NOT i_bFieldbusOk THEN",
        "IF NOT t_bDoorsOk OR NOT i_bFieldbusOk THEN",
    ),
    "门没锁不停机": (
        "IF t_bFault OR NOT t_bDoorsOk OR NOT i_bFieldbusOk THEN",
        "IF t_bFault OR NOT i_bFieldbusOk THEN",
    ),
    "启动不需要": ("s_iState := ST_WAIT_START;", "s_iState := ST_RUN;"),
    "动作没停就解锁": ("ELSIF i_bMotionStopped THEN", "ELSE"),
    "门开着按复位也锁回": ("s_arrDoorStep[t_iIdx] := DOOR_UNLOCKED;\n                END_IF;\n\n            ELSE", "s_arrDoorStep[t_iIdx] := DOOR_RELOCK;\n                END_IF;\n\n            ELSE"),
}
# 没列进来的两处是双保险, 单独改坏一处行为不变 (变异等价), 已核对:
#   第二次复位条件里的 NOT t_bFault —— 状态 2 起第 2 段遇继电器故障当拍回 0;
#   开门申请的 NOT i_bAutoMode —— 申请中第 1 步遇自动当拍取消.

CHECKS = [
    test_t4_second_reset_after_5s_too_early,
    test_t6_holding_reset_across_10s_not_accepted,
    test_t3_reset_rejected_while_fault,
    test_t7_door_opens_in_run_stops,
    test_t5_second_reset_after_10s_then_start,
    test_t9_request_in_auto_ignored,
    test_t10_request_blinks_until_stopped,
    test_t11_reset_with_door_open_not_accepted,
    test_power_up_never_runs_by_itself,
    test_t1_fault_stops_same_scan,
    test_t13_second_relay_fault,
    test_t11_close_door_reset_relocks_then_two_resets,
]


@pytest.mark.parametrize("label", list(MUTATIONS))
def test_mutation_is_caught(label: str, tmp_path: Path) -> None:
    old, new = MUTATIONS[label]
    src = FB_PATH.read_text(encoding="utf-8")
    assert src.count(old) == 1, f"变异锚点没找到或不唯一: {old}"
    mutated = src.replace(old, new)
    caught = []
    for check in CHECKS:
        try:
            check(Machine(mutated, tmp_path))
        except AssertionError:
            caught.append(check.__name__)
    assert caught, f"变异“{label}”没被任何用例抓住"


# ------------------------------------------------------------------ 测试台 .scltest 的期望值在这里先按真实毫秒跑一遍

SCLTEST = REPO / "0100_PLC自动化" / "DJ-2026-000" / "Test" / "safety_manager_test.scltest"


def _scl_value(text: str):
    text = text.strip()
    if text.upper() in ("TRUE", "FALSE"):
        return text.upper() == "TRUE"
    if text.startswith("16#"):
        return int(text[3:], 16)
    return int(text)


def test_scltest_expectations_hold_in_sim() -> None:
    """按测试台 .scltest 的顺序执行（实例状态在用例之间保持，扫描周期按 10 ms 估）。"""
    import re

    m = Machine()
    case = ""
    ref = re.compile(r"GlobalVars\.sm_(\w+?)(?:\[(\d+)\])?\s*(:=|=|<>)\s*([^;]+);")
    for raw in SCLTEST.read_text(encoding="utf-8").splitlines():
        line = raw.split("//")[0].strip()
        if line.startswith("TEST_CASE"):
            case = line
        elif line.startswith("WAIT_CYCLES"):
            m.scan(int(line.split()[1].rstrip(";")))
        elif line.startswith(("SET", "ASSERT")):
            name, idx, op, val = ref.search(line).groups()
            key = "i_" + name if "i_" + name in m.fb.vars else "q_" + name
            i = None if idx is None else int(idx)
            if line.startswith("SET"):
                m.set(key, _scl_value(val), i)
            else:
                got = m.out(key, i)
                want = _scl_value(val)
                ok = got == want if op == "=" else got != want
                assert ok, f"{case}: {line} 实际 {got!r}"
