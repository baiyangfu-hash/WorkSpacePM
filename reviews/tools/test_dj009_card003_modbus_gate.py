"""DJ-2026-009 卡 003：Modbus 停用时握手不使能（Codex 评审 #77，审计 117 要求补的真测试）。

OB1 给 FB_3001 的使能是 ``stExternal.bEmergencyStop AND bModbusEnable``。这里先静态核对 OB1 那一行，
再用 ``st_mini_sim`` 直接执行 FB_3001 源码、按 OB1 的写法每拍算使能，检查：
握手走到第 30 步时 Modbus 停用 → 当拍撤销允许和动作输出、步序回 0、自动模式下上锁；
Modbus 恢复后不按复位不恢复，按住复位不放也不恢复，复位上升沿才清锁。
仿真时钟按真实毫秒。不代替 InoProShop 仿真和用户签字。

运行：python -B -m pytest reviews/tools/test_dj009_card003_modbus_gate.py -q
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from st_mini_sim import Sim

REPO = Path(__file__).resolve().parents[2]
ST = REPO / "0100_PLC自动化" / "DJ-2026-009_汇川换型改造" / "02_PLC程序" / "PLC_ST"
EXT = ST / "01_外部设备交互"
OB1 = ST / "00_主程序" / "OB1.scl"
SCAN_MS = 10
ERR_INFEED_ABORT, ERR_WAIT_RESET, ERR_ID_CHECK = 0x0001, 0x0004, 0x0080


def ob1_enable_terms() -> set[str]:
    """OB1 里 fbExternalDevice 调用的 i_bEnable 右边，按 AND 拆成变量名。"""
    src = OB1.read_text(encoding="utf-8")
    call = src[src.index("GlobalVars.fbExternalDevice("):]
    m = re.search(r"^\s*i_bEnable\s*:=\s*([^,\n]+),", call, re.MULTILINE)
    assert m, "OB1 没有给 fbExternalDevice 接 i_bEnable"
    return {t.strip() for t in m.group(1).split(" AND ")}


class Line:
    """FB_3001 加上 OB1 的使能写法；对方心跳每 1 s 翻转一次。"""

    def __init__(self) -> None:
        self.sim = Sim()
        self.sim.load(EXT / "ST_ExternalDevice.scl")
        self.sim.load(EXT / "FC_3003_CheckModuleId.scl")
        self.sim.load(EXT / "FB_3001_ExternalInteraction.scl")
        self.fb = self.sim.new_instance("FB_3001_ExternalInteraction")
        self.ext = self.fb.vars["io_stExternal"]
        self.up = self.ext["stUpstream"]
        self.down = self.ext["stDownstream"]
        self.estop_ok = True
        self.modbus = True
        v = self.fb.vars
        v["i_bAutoMode"] = True
        v["i_bMachineReadyIn"] = True
        self.up["sRcvModuleID"] = "L06A20261020165232"

    def scan(self, n: int = 1) -> None:
        for _ in range(n):
            self.sim.now_ms += SCAN_MS
            if self.sim.now_ms % 1000 == 0:
                self.up["bUpstream_HeartbeatFromUp"] = not self.up["bUpstream_HeartbeatFromUp"]
                self.down["bDownstream_HeartbeatFromDown"] = not self.down["bDownstream_HeartbeatFromDown"]
            # 与 OB1 同写法：急停正常 AND Modbus 启用
            self.fb.vars["i_bEnable"] = self.estop_ok and self.modbus
            self.fb.call()

    def reset(self, on: bool) -> None:
        self.fb.vars["i_bResetCmd"] = on

    @property
    def err(self) -> int:
        return self.fb.vars["q_wErrorCode"]

    @property
    def locked(self) -> bool:
        return bool(self.fb.vars["s_bInfeedLock"])

    def to_infeed_step30(self) -> None:
        self.up["bUpstream_LineReady"] = True
        self.scan(2)
        assert self.up["iInfeedStep"] == 10
        self.up["bUpstream_SendModuleId"] = True
        self.scan(2)
        assert self.up["iInfeedStep"] == 20
        self.up["bUpstream_InfeedReq"] = True
        self.scan(2)
        assert self.up["iInfeedStep"] == 30
        assert self.up["bMachine_AllowInfeed"] and self.fb.vars["q_bAllowInfeedAct"]


@pytest.fixture
def line() -> Line:
    return Line()


def test_ob1_enable_is_estop_and_modbus() -> None:
    assert ob1_enable_terms() == {"GlobalVars.stExternal.bEmergencyStop", "GlobalVars.bModbusEnable"}


def test_modbus_off_at_step30_withdraws_same_scan_and_locks(line: Line) -> None:
    line.to_infeed_step30()
    line.modbus = False
    line.scan()
    assert not line.up["bMachine_AllowInfeed"]
    assert not line.up["bMachine_ReadyIn"]
    assert not line.fb.vars["q_bAllowInfeedAct"]
    assert line.up["iInfeedStep"] == 0
    assert line.locked
    assert line.err & ERR_INFEED_ABORT and line.err & ERR_WAIT_RESET


def test_modbus_back_without_reset_stays_locked(line: Line) -> None:
    line.to_infeed_step30()
    line.modbus = False
    line.scan()
    line.modbus = True
    line.scan(50)  # 0.5 s，对方信号仍是走到第 30 步时的值
    assert line.locked
    assert not line.up["bMachine_ReadyIn"]
    assert not line.up["bMachine_AllowInfeed"]
    assert not line.fb.vars["q_bAllowInfeedAct"]
    assert line.up["iInfeedStep"] == 0


def test_reset_held_does_not_clear_only_rising_edge_does(line: Line) -> None:
    line.reset(True)          # 复位先按住（上升沿发生在停用之前）
    line.scan()
    line.to_infeed_step30()
    line.modbus = False
    line.scan()
    assert line.locked
    line.modbus = True
    line.scan(20)
    assert line.locked, "按住复位不放、Modbus 恢复后锁不能自己清"
    line.reset(False)
    line.scan()
    assert line.locked
    line.reset(True)          # 松开再按：上升沿
    line.scan()
    line.reset(False)
    line.scan()
    assert not line.locked
    assert line.err & (ERR_INFEED_ABORT | ERR_WAIT_RESET) == 0
    assert line.err & ERR_ID_CHECK, "第 20 步后中止的，组件 ID 仍要人工核对"
    line.scan(2)
    assert line.up["bMachine_ReadyIn"], "清锁后重新发就绪，握手可以重新开始"


def test_estop_still_withdraws(line: Line) -> None:
    line.to_infeed_step30()
    line.estop_ok = False
    line.scan()
    assert not line.fb.vars["q_bAllowInfeedAct"]
    assert line.up["iInfeedStep"] == 0
    assert line.locked
