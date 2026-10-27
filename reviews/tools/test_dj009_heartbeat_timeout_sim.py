"""DJ-2026-009 FB_3001_ExternalInteraction 对方心跳停止 -> 12 s 报通讯故障的逻辑仿真（真实毫秒）。

用 ``st_mini_sim`` 直接执行 FB_3001 的 .scl 源码，FB_TON 按仿真时钟计真实毫秒（与 SysLib FB_TON V3.0.0 同义）。
覆盖：心跳活着不报故障；心跳停止后 12 s 才报故障（不同扫描周期都成立）；心跳停在握手第 0、20、30 步，
11 s 时还没报故障、12 s 之后报故障且允许信号和动作输出全部撤销。这和 PLC_ST/Test/heartbeat_timeout_test.scltest
是同一组场景，区别是这里按真实毫秒跑，那份在笔记本上用替身计时器（1 周期=1 ms）跑。
这不能代替 PLCSIM / 现场拔线计时（验收记录 FAC-004），只是在云端先把逻辑跑一遍。

运行：python -B -m pytest reviews/tools/test_dj009_heartbeat_timeout_sim.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from st_mini_sim import Sim

REPO = Path(__file__).resolve().parents[2]
PLC = next((REPO / "0100_PLC自动化").glob("DJ-2026-009*")) / "02_PLC程序" / "PLC_ST" / "01_外部设备交互"
FB_PATH = PLC / "FB_3001_ExternalInteraction.scl"
TYPES_PATH = PLC / "ST_ExternalDevice.scl"
TIMEOUT_LITERAL = "s_dHbTimeoutMs      : DINT := 12000;"

ERR_UP_COM, ERR_DOWN_COM = 0x10, 0x20


class Machine:
    """一台 FB_3001 实例 + 对接数据总线；默认手动模式、已使能、心跳输入为假。"""

    def __init__(self, scan_ms: int = 10, fb_source: Path = FB_PATH) -> None:
        self.scan_ms = scan_ms
        self.sim = Sim()
        self.sim.load(TYPES_PATH)
        self.sim.load(fb_source)
        self.ext = self.sim.new_struct("ST_ExternalDevice")
        self.fb = self.sim.new_instance("FB_3001_ExternalInteraction")
        self.fb.bind("io_stExternal", self.ext)
        self.up, self.dn = self.ext["stUpstream"], self.ext["stDownstream"]
        self.fb.vars["i_bEnable"] = True
        self.scan(2)
        self.fb.vars["i_bResetCmd"] = True
        self.scan(1)
        self.fb.vars["i_bResetCmd"] = False
        self.scan(1)

    def scan(self, n: int = 1) -> None:
        for _ in range(n):
            self.sim.now_ms += self.scan_ms
            self.fb.call()

    def wait_ms(self, ms: int) -> None:
        self.scan(max(1, ms // self.scan_ms))

    def flip_heartbeats(self) -> None:
        self.up["bUpstream_HeartbeatFromUp"] = not self.up["bUpstream_HeartbeatFromUp"]
        self.dn["bDownstream_HeartbeatFromDown"] = not self.dn["bDownstream_HeartbeatFromDown"]
        self.scan(1)

    def out(self, name: str):
        return self.fb.vars[name]

    def drive_both_handshakes_to(self, step: int) -> None:
        """进料、出料同时推到第 step 步 (0 / 20 / 30)，和 .scltest 里的做法一致。"""
        if step == 0:
            self.fb.vars["i_bMachineReadyIn"] = True
            self.fb.vars["i_bMachineReadyOut"] = True
        if step >= 20:
            self.fb.vars["i_bMachineReadyIn"] = True
            self.up["bUpstream_LineReady"] = True
            self.up["bUpstream_SendModuleId"] = True
            self.fb.vars["i_bMachineReadyOut"] = True
            self.dn["bDownstream_LineReady"] = True
            self.dn["bDownstream_RcvModuleIdAck"] = True
        if step >= 30:
            self.up["bUpstream_InfeedReq"] = True
            self.dn["bDownstream_AllowOutfeed"] = True
        self.scan(5)


def first_fault_after_last_flip_ms(scan_ms: int, fb_source: Path = FB_PATH) -> int:
    """心跳先正常翻转，最后一次翻转后不再动：返回从那次翻转起到上下游同时报故障的毫秒数。"""
    m = Machine(scan_ms, fb_source)
    for _ in range(6):
        m.flip_heartbeats()
        m.wait_ms(4000)
        assert not m.ext["bAnyComFault"], "心跳还在翻转就报了故障"
    m.flip_heartbeats()
    t_flip = m.sim.now_ms
    for _ in range(30_000 // scan_ms):
        m.scan(1)
        if m.ext["bAnyComFault"]:
            assert m.up["bUpstreamComFault"] and m.dn["bDownstreamComFault"]
            return m.sim.now_ms - t_flip
    raise AssertionError("30 s 内没有报故障")


@pytest.mark.parametrize("scan_ms", [5, 10, 20])
def test_the_fault_comes_12_seconds_after_the_last_heartbeat_edge_whatever_the_scan_time(scan_ms: int) -> None:
    elapsed = first_fault_after_last_flip_ms(scan_ms)

    assert 12_000 <= elapsed <= 12_000 + 4 * scan_ms


@pytest.mark.parametrize("step", [0, 20, 30])
def test_heartbeat_stopped_at_a_handshake_step_faults_only_after_12_seconds_and_withdraws_everything(step: int) -> None:
    m = Machine()
    m.flip_heartbeats()
    m.drive_both_handshakes_to(step)
    assert m.up["iInfeedStep"] == step and m.dn["iOutfeedStep"] == step
    assert m.up["bMachine_AllowInfeed"] is (step >= 20)
    assert m.dn["bMachine_OutfeedReq"] is (step >= 30)
    assert m.out("q_bAllowInfeedAct") is (step >= 30)
    assert m.out("q_bAllowOutfeedAct") is (step >= 30)

    m.wait_ms(11_000 - 6 * m.scan_ms)  # 最后一次心跳翻转后约 11 s
    assert not m.up["bUpstreamComFault"] and not m.dn["bDownstreamComFault"]
    assert not m.ext["bAnyComFault"] and not m.out("q_bComAlarm")
    assert m.out("q_wErrorCode") == 0
    assert m.up["iInfeedStep"] == step and m.dn["iOutfeedStep"] == step  # 还没报故障，握手照常

    m.wait_ms(1_100)  # 约 12.1 s
    assert m.up["bUpstreamComFault"] and m.dn["bDownstreamComFault"]
    assert m.ext["bAnyComFault"] and m.out("q_bComAlarm")
    assert m.out("q_wErrorCode") & (ERR_UP_COM | ERR_DOWN_COM) == ERR_UP_COM | ERR_DOWN_COM
    assert not m.up["bMachine_AllowInfeed"]
    assert not m.dn["bMachine_OutfeedReq"]
    assert not m.out("q_bAllowInfeedAct")
    assert not m.out("q_bAllowOutfeedAct")
    assert m.up["iInfeedStep"] == 0 and m.dn["iOutfeedStep"] == 0


@pytest.mark.parametrize("threshold_ms", [10_000, 14_000])
def test_a_wrong_timeout_in_the_program_would_be_caught(tmp_path: Path, threshold_ms: int) -> None:
    """变异：程序里的 12000 ms 阈值改了，本文件的时间断言必须不再成立（证明这些断言真在盯着 12 s）。"""
    source = FB_PATH.read_text(encoding="utf-8")
    assert TIMEOUT_LITERAL in source
    mutant = tmp_path / "FB_3001_mutant.scl"
    mutant.write_text(source.replace(TIMEOUT_LITERAL, TIMEOUT_LITERAL.replace("12000", str(threshold_ms))), encoding="utf-8")

    elapsed = first_fault_after_last_flip_ms(10, mutant)

    assert not (12_000 <= elapsed <= 12_000 + 40)
    assert abs(elapsed - threshold_ms) <= 40
