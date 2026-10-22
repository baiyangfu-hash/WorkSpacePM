"""DJ-2026-009 卡 004：握手块 FB_3001 在运行许可丢失时“心跳照发、只撤握手”（用户 2026-10-22 定）。

用 ``st_mini_sim`` 直接执行项目里的 .scl 源码，仿真时钟按真实毫秒。不代替 InoProShop 仿真和用户签字。

运行：python -B -m pytest reviews/tools/test_dj009_card004_handshake.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from st_mini_sim import Sim  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
EXT = REPO / "0100_PLC自动化" / "DJ-2026-009_汇川换型改造" / "02_PLC程序" / "PLC_ST" / "01_外部设备交互"
FB3001 = EXT / "FB_3001_ExternalInteraction.scl"
SCAN_MS = 10
ERR_INFEED_ABORT, ERR_WAIT_RESET, ERR_UP_COM, ERR_ID_CHECK = 0x0001, 0x0004, 0x0010, 0x0080


class Handshake:
    def __init__(self, fb_src: str | None = None, tmp: Path | None = None):
        self.sim = Sim()
        self.sim.load(EXT / "ST_ExternalDevice.scl")
        self.sim.load(EXT / "FC_3003_CheckModuleId.scl")
        path = FB3001
        if fb_src is not None:
            path = tmp / "FB_3001_mut.scl"
            path.write_text(fb_src, encoding="utf-8")
        self.sim.load(path)
        self.fb = self.sim.new_instance("FB_3001_ExternalInteraction")
        self.ext = self.fb.vars["io_stExternal"]
        self.up = self.ext["stUpstream"]
        self.down = self.ext["stDownstream"]
        v = self.fb.vars
        v["i_bEnable"] = True          # OB1 常开
        v["i_bAutoMode"] = True
        v["i_bMachineReadyIn"] = True
        self.up["sRcvModuleID"] = "L06A20261020165232"
        self.peer_hb = True             # 对方心跳活着
        self.hb_seen: set[tuple[bool, bool]] = set()

    def permit(self, on: bool) -> None:
        self.fb.vars["i_bSafeToRun"] = on

    def scan(self, n: int = 1) -> None:
        for _ in range(n):
            self.sim.now_ms += SCAN_MS
            if self.peer_hb and self.sim.now_ms % 1000 == 0:   # 对方每 1 s 翻转一次
                self.up["bUpstream_HeartbeatFromUp"] = not self.up["bUpstream_HeartbeatFromUp"]
                self.down["bDownstream_HeartbeatFromDown"] = not self.down["bDownstream_HeartbeatFromDown"]
            self.fb.call()
            self.hb_seen.add((self.up["bMachine_HeartbeatToUp"], self.down["bMachine_HeartbeatToDown"]))

    def wait_ms(self, ms: int) -> None:
        self.scan(max(1, ms // SCAN_MS))

    def reset_pulse(self) -> None:
        self.fb.vars["i_bResetCmd"] = True
        self.scan()
        self.fb.vars["i_bResetCmd"] = False
        self.scan()

    @property
    def err(self) -> int:
        return self.fb.vars["q_wErrorCode"]

    def to_infeed_step30(self) -> None:
        self.permit(True)
        self.up["bUpstream_LineReady"] = True
        self.scan(2)
        assert self.up["iInfeedStep"] == 10
        self.up["bUpstream_SendModuleId"] = True
        self.scan(2)
        assert self.up["iInfeedStep"] == 20
        self.up["bUpstream_InfeedReq"] = True
        self.scan(2)
        assert self.up["iInfeedStep"] == 30 and self.fb.vars["q_bAllowInfeedAct"]


@pytest.fixture
def h() -> Handshake:
    return Handshake()


def test_heartbeat_keeps_running_without_permission(h: Handshake) -> None:
    h.permit(False)
    h.wait_ms(10_000)
    assert {(True, True), (False, False)} <= h.hb_seen        # 4 s 亮 / 4 s 灭照发
    assert not h.up["bMachine_ReadyIn"]                       # 但不发“准备好进料”
    assert h.up["iInfeedStep"] == 0


def test_peer_timeout_still_detected_without_permission(h: Handshake) -> None:
    h.permit(False)
    h.peer_hb = False
    h.wait_ms(13_000)
    assert h.fb.vars["q_bComAlarm"] and h.err & ERR_UP_COM


def test_permission_lost_mid_handshake_withdraws_same_scan(h: Handshake) -> None:
    h.to_infeed_step30()
    h.permit(False)
    h.scan()
    assert not h.fb.vars["q_bAllowInfeedAct"]
    assert not h.up["bMachine_AllowInfeed"] and not h.up["bMachine_ReadyIn"]
    assert h.up["iInfeedStep"] == 0
    assert h.err & ERR_INFEED_ABORT and h.err & ERR_WAIT_RESET and h.err & ERR_ID_CHECK
    hb_before = set(h.hb_seen)
    h.hb_seen.clear()
    h.wait_ms(9_000)
    assert {(True, True), (False, False)} <= h.hb_seen        # 停机期间心跳不停
    assert hb_before


def test_after_permission_back_needs_reset_to_handshake_again(h: Handshake) -> None:
    h.to_infeed_step30()
    h.permit(False)
    h.wait_ms(2_000)
    h.permit(True)
    h.up["bUpstream_SendModuleId"] = False
    h.up["bUpstream_InfeedReq"] = False
    h.wait_ms(1_000)
    assert not h.up["bMachine_ReadyIn"]                       # 作业中止锁还在
    h.reset_pulse()                                           # OB1：FB_1030 运行复位脉冲
    h.scan(2)
    assert h.up["bMachine_ReadyIn"] and not (h.err & ERR_WAIT_RESET)


def test_mutation_without_permission_check_is_caught(tmp_path: Path) -> None:
    src = FB3001.read_text(encoding="utf-8").replace("IF NOT i_bSafeToRun THEN", "IF FALSE THEN")
    h = Handshake(src, tmp_path)
    h.to_infeed_step30()
    h.permit(False)
    h.scan()
    assert h.fb.vars["q_bAllowInfeedAct"]   # 改坏后不撤 —— 说明上面的用例确实在验这一段
