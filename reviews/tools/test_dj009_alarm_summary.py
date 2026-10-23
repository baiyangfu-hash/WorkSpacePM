"""DJ-2026-009 报警汇总卡：FB_2001 公共报警块逻辑仿真（对齐记录 C-1～C-8 的回归用例）。

用 ``st_mini_sim`` 直接执行项目里的 .scl 源码。前半段单测 FB_2001；后半段把共享库 FB_1030
安全管理块的 ``q_dwAlarm`` 串进来，确认急停/门/总线的位和报警码对得上。另有 OB1 接线的静态检查，
和几条“改坏了测试能不能抓到”的变异用例。不代替 InoProShop 仿真和用户签字。

运行：python -B -m pytest reviews/tools/test_dj009_alarm_summary.py -q
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from st_mini_sim import Sim

REPO = Path(__file__).resolve().parents[2]
PLC = REPO / "0100_PLC自动化"
P009 = PLC / "DJ-2026-009_汇川换型改造" / "02_PLC程序" / "PLC_ST"
FB2001 = P009 / "05_公共报警" / "FB_2001_CommonAlarm_AllStation.scl"
ST2001 = P009 / "05_公共报警" / "ST_CommonAlarm.scl"
OB1 = P009 / "00_主程序" / "OB1.scl"
FB1030 = PLC / "01_SharedLibraries" / "SysLib" / "safety" / "FB_1030_SafetyManager.scl"
SCAN_MS = 10

# FB_3001 q_wErrorCode 位（FB_3001 常量区）
ERR_INFEED_ABORT, ERR_WAIT_RESET, ERR_UP_COM, ERR_DOWN_COM = 0x0001, 0x0004, 0x0010, 0x0020


class Alarm:
    """一个 FB_2001 实例 + 它的 ST_CommonAlarm 结构体，模拟 OB1 第 3 部分每扫描写入三路报警源。"""

    def __init__(self, fb_src: str | None = None, tmp: Path | None = None):
        self.sim = Sim()
        self.sim.load(ST2001)
        path = FB2001
        if fb_src is not None:
            path = tmp / "FB_2001_mut.scl"
            path.write_text(fb_src, encoding="utf-8")
        self.sim.load(path)
        self.fb = self.sim.new_instance("FB_2001_CommonAlarm_AllStation")
        self.st = self.sim.new_struct("ST_CommonAlarm")
        self.fb.bind("io_stGlobal", self.st)
        self.safety, self.ext, self.station, self.reset = 0, 0, 0, False
        self.scan()

    def scan(self, n: int = 1) -> None:
        for _ in range(n):
            self.sim.now_ms += SCAN_MS
            self.st["i_dwSafetyAlarm"] = self.safety
            self.st["i_wExtErrorCode"] = self.ext
            self.st["i_iStationAlarm"] = self.station
            self.st["i_bReset"] = self.reset
            self.fb.call()

    def press_reset(self, hold_scans: int = 3) -> None:
        self.reset = True
        self.scan(hold_scans)
        self.reset = False
        self.scan()

    def o(self, name: str):
        return self.st[name]

    @property
    def history(self) -> list[int]:
        return list(self.st["o_arrAlarmHistory"])


# --------------------------------------------------------------------------- 单块


def test_no_alarm_idle():
    a = Alarm()
    a.scan(5)
    assert a.o("o_iCurrentAlarmCode") == 0
    assert not a.o("o_bAnyAlarmActive")
    assert a.o("o_wGlobalAlarmWord") == 0
    assert a.o("o_iAlarmEventCount") == 0
    assert a.history == [0] * 10


def test_c1_each_source_reports():
    """C-1：三路源都能报出来（原来三个输入没人写，恒 0）。码表见 FB_2001 文件头。"""
    a = Alarm()
    a.safety = 1 << 0                  # 第 1 个急停
    a.scan()
    assert a.o("o_iCurrentAlarmCode") == 1 and a.o("o_bSafetyAlarmActive")
    a.safety = 0
    a.ext = ERR_UP_COM                 # bit4 上游通讯
    a.scan()
    assert a.o("o_iCurrentAlarmCode") == 45 and a.o("o_bExtAlarmActive") and not a.o("o_bSafetyAlarmActive")
    a.ext = 0
    a.station = 102
    a.scan()
    assert a.o("o_iCurrentAlarmCode") == 102 and a.o("o_bStationAlarmActive")


@pytest.mark.parametrize(
    "bit,code",
    [(0, 1), (7, 8), (8, 9), (15, 16), (16, 17), (24, 25), (27, 28), (28, 29), (29, 30), (30, 31), (31, 32)],
)
def test_safety_bit_to_code(bit, code):
    a = Alarm()
    a.safety = 1 << bit
    a.scan()
    assert a.o("o_iCurrentAlarmCode") == code
    assert a.history[0] == code


@pytest.mark.parametrize("bit,code", [(0, 41), (1, 42), (2, 43), (4, 45), (5, 46), (6, 47), (7, 48), (15, 56)])
def test_ext_bit_to_code(bit, code):
    a = Alarm()
    a.ext = 1 << bit
    a.scan()
    assert a.o("o_iCurrentAlarmCode") == code


def test_c2_new_alarm_edge_counts_once():
    """C-2：新报警判得出（原来上一扫描值在块开头就被覆盖，永远判不出）；持续报警只记一次。"""
    a = Alarm()
    a.station = 101
    a.scan()
    assert a.o("o_bNewAlarmFlag")
    assert a.o("o_iAlarmEventCount") == 1
    a.scan(50)
    assert a.o("o_iAlarmEventCount") == 1
    assert a.history == [101] + [0] * 9


def test_c2_same_code_again_counts_again():
    a = Alarm()
    a.station = 101
    a.scan(3)
    a.station = 0
    a.scan(3)
    a.station = 101
    a.scan(3)
    assert a.o("o_iAlarmEventCount") == 2
    assert a.history[:2] == [101, 101]


def test_station_code_change_is_new():
    a = Alarm()
    a.station = 101
    a.scan(2)
    a.station = 103
    a.scan(2)
    assert a.o("o_iAlarmEventCount") == 2
    assert a.history[:2] == [103, 101]


def test_c3_no_queue_write_without_alarm():
    """C-3：没报警时不动历史（原来队列维护抄了两遍，没报警也每扫描跑）。"""
    a = Alarm()
    for code in range(101, 113):       # 12 次不同报警, 队列满过一圈
        a.station = code
        a.scan()
        a.station = 0
        a.scan()
    before = a.history
    a.scan(100)
    assert a.history == before
    assert 0 not in a.history          # 满了以后不会被写进 0


def test_c4_history_ten_newest_first():
    """C-4：最近 10 条输出给 HMI，[0] 最新，第 11 条挤掉最旧的。"""
    a = Alarm()
    for code in range(101, 112):       # 11 条
        a.station = code
        a.scan()
    assert a.history == list(range(111, 101, -1))
    assert a.o("o_iAlarmEventCount") == 11


def test_c5_simultaneous_alarms_do_not_mix():
    """C-5：码 1 和码 2 同时在报，当前码是 1（不是 1 OR 2 = 3），条数 2，类别字按类别置位。"""
    a = Alarm()
    a.safety = (1 << 0) | (1 << 1)
    a.ext = ERR_DOWN_COM
    a.station = 104
    a.scan()
    assert a.o("o_iCurrentAlarmCode") == 1
    assert a.o("o_iActiveAlarmCount") == 4
    assert a.o("o_wGlobalAlarmWord") == 0b111
    # 同一扫描 4 条新报警：码小的排前面
    assert a.history[:4] == [1, 2, 46, 104]
    assert a.o("o_iAlarmEventCount") == 4


def test_priority_falls_back_when_top_clears():
    a = Alarm()
    a.safety = 1 << 28                 # 总线断线 29
    a.station = 101
    a.scan()
    assert a.o("o_iCurrentAlarmCode") == 29
    a.safety = 0
    a.scan()
    assert a.o("o_iCurrentAlarmCode") == 101
    a.station = 0
    a.scan()
    assert a.o("o_iCurrentAlarmCode") == 0 and not a.o("o_bAnyAlarmActive")


def test_c7_outputs_update_while_reset_held():
    """C-7：按住复位那几个扫描，输出照常封包（原来复位分支 RETURN，输出停在旧值）。"""
    a = Alarm()
    a.station = 101
    a.scan()
    a.reset = True
    a.station = 0
    a.scan()
    assert a.o("o_iCurrentAlarmCode") == 0
    a.safety = 1
    a.scan()
    assert a.o("o_iCurrentAlarmCode") == 1


def test_reset_rising_edge_only_clears_history_not_active():
    a = Alarm()
    a.station = 101
    a.scan(3)
    a.press_reset()
    assert a.history == [0] * 10
    assert a.o("o_iAlarmEventCount") == 0
    assert not a.o("o_bNewAlarmFlag")
    # 报警还在：照常显示，复位后不再记一次
    assert a.o("o_iCurrentAlarmCode") == 101 and a.o("o_bAnyAlarmActive")
    a.scan(10)
    assert a.o("o_iAlarmEventCount") == 0


def test_reset_held_does_not_swallow_new_alarm():
    """按住复位不放时出的新报警要记上（只认上升沿，按住不反复清）。"""
    a = Alarm()
    a.reset = True
    a.scan(2)
    a.station = 103
    a.scan(5)
    assert a.o("o_iAlarmEventCount") == 1 and a.o("o_bNewAlarmFlag")
    assert a.history[0] == 103


def test_new_flag_latched_until_reset():
    a = Alarm()
    a.ext = ERR_WAIT_RESET
    a.scan()
    a.ext = 0
    a.scan(20)
    assert a.o("o_bNewAlarmFlag")      # 报警没了, 标志等人确认
    a.press_reset()
    assert not a.o("o_bNewAlarmFlag")


def test_event_count_rolls_over_to_one():
    a = Alarm()
    a.fb.vars["s_iAlarmEventCount"] = 32767
    a.station = 101
    a.scan()
    assert a.o("o_iAlarmEventCount") == 1


# --------------------------------------------------------------------------- 串 FB_1030


class Chain:
    """FB_1030 → q_dwAlarm → FB_2001，同 OB1 第 3 部分。"""

    def __init__(self):
        self.a = Alarm()
        self.sim = self.a.sim
        self.sim.load(FB1030)
        self.sf = self.sim.new_instance("FB_1030_SafetyManager")
        v = self.sf.vars
        for i in range(8):
            v["i_arrEStopOk"][i] = True
            v["i_arrCurtainOk"][i] = True
            v["i_arrDoorClosed"][i] = True
        v["i_bFieldbusOk"] = True
        self.scan()

    def scan(self, n: int = 1) -> None:
        for _ in range(n):
            self.sf.call()
            self.a.safety = self.sf.vars["q_dwAlarm"]
            self.a.scan()

    def set(self, name, value, idx=None):
        if idx is None:
            self.sf.vars[name] = value
        else:
            self.sf.vars[name][idx] = value


def test_chain_estop_door_fieldbus_codes():
    c = Chain()
    assert c.a.o("o_iCurrentAlarmCode") == 0
    c.set("i_arrEStopOk", False, 0)
    c.scan()
    assert c.a.o("o_iCurrentAlarmCode") == 1
    c.set("i_arrEStopOk", True, 0)
    c.set("i_arrDoorClosed", False, 2)       # 第 3 扇门
    c.scan()
    assert c.a.o("o_iCurrentAlarmCode") == 11
    c.set("i_arrDoorClosed", True, 2)
    c.set("i_bFieldbusOk", False)
    c.scan()
    assert c.a.o("o_iCurrentAlarmCode") == 29
    assert c.a.history[:3] == [29, 11, 1]


def test_chain_relay_fault_code():
    c = Chain()
    c.set("i_arrSafetyFault", True, 0)
    c.scan()
    assert 25 in c.a.history
    assert c.a.o("o_bSafetyAlarmActive")


def test_alarm_block_does_not_write_safety_inputs():
    """只读：报警块跑多少扫描，FB_1030 的输入输出都不受影响（本块没有任何写安全变量的语句）。"""
    src = FB2001.read_text(encoding="utf-8")
    body = src.split("END_VAR")[-1]
    writes = re.findall(r"^\s*([A-Za-z_][\w.\[\]]*)\s*:=", body, re.MULTILINE)
    assert writes, "没解析到赋值语句"
    for w in writes:
        assert w.startswith(("s_", "t_", "io_stGlobal.o_")), f"报警块写了 {w}"


# --------------------------------------------------------------------------- OB1 接线（静态）


def test_ob1_wires_three_sources_before_call():
    src = OB1.read_text(encoding="utf-8")
    call = src.index("GlobalVars.fbCommonAlarm(")
    for line in (
        "GlobalVars.stGlobal.i_dwSafetyAlarm := GlobalVars.fbSafety.q_dwAlarm;",
        "GlobalVars.stGlobal.i_wExtErrorCode := GlobalVars.wExtErrorCode;",
        "GlobalVars.stGlobal.i_iStationAlarm := GlobalVars.stStation1.stStatus.iAlarmCode;",
    ):
        assert line in src
        assert src.index(line) < call
    # 读 fbSafety 的那行圈在 @安全区 里
    i = src.index("i_dwSafetyAlarm := GlobalVars.fbSafety")
    assert src.rfind("@安全区 开始", 0, i) > src.rfind("@安全区 结束", 0, i)
    # 旧的 005 输入名不再出现
    for old in ("i_iConveyorAlarm", "i_iPickPlaceAlarm", "i_iFeederAlarm"):
        assert old not in src


def test_ob1_calls_alarm_after_station_and_safety():
    src = OB1.read_text(encoding="utf-8")
    assert src.index("GlobalVars.fbSafety(") < src.index("GlobalVars.fbStation1(") < src.index("GlobalVars.fbCommonAlarm(")


# --------------------------------------------------------------------------- 变异：改坏了要被抓到


def _mutate(old: str, new: str) -> str:
    src = FB2001.read_text(encoding="utf-8")
    assert old in src, old
    return src.replace(old, new, 1)


def test_mutation_prev_saved_at_top_breaks_edge(tmp_path):
    """把“保存上一扫描值”挪回块开头（原 C-2 写法），新报警计数应失效。"""
    src = _mutate(
        "s_dwSafetyNew := s_dwSafetyAlarm AND NOT s_dwPrevSafetyAlarm;",
        "s_iPrevStationAlarm := s_iStationAlarm;\ns_dwSafetyNew := s_dwSafetyAlarm AND NOT s_dwPrevSafetyAlarm;",
    )
    a = Alarm(src, tmp_path)
    a.station = 101
    a.scan()
    assert a.o("o_iAlarmEventCount") == 0          # 改坏了 → 工位新报警判不出
    assert a.history == [0] * 10


def test_mutation_reset_return_freezes_outputs(tmp_path):
    """复位分支加回 RETURN（原 C-7 写法），按住复位时输出应停在旧值。"""
    src = _mutate("    s_bNewAlarmFlag := FALSE;\nEND_IF;", "    s_bNewAlarmFlag := FALSE;\nEND_IF;\nIF s_bResetCmd THEN RETURN; END_IF;")
    a = Alarm(src, tmp_path)
    a.station = 101
    a.scan()
    a.reset = True
    a.station = 0
    a.scan()
    assert a.o("o_iCurrentAlarmCode") == 101       # 改坏了 → 输出没更新


def test_mutation_or_codes_mixes(tmp_path):
    """当前码改成“码按位或”（原 C-5 写法），两条报警同时在时码会混。"""
    src = _mutate("        s_iCurrentAlarmCode := t_iCode;", "        s_iCurrentAlarmCode := s_iCurrentAlarmCode OR t_iCode;")
    a = Alarm(src, tmp_path)
    a.safety = 0b11
    a.scan()
    assert a.o("o_iCurrentAlarmCode") == 3
