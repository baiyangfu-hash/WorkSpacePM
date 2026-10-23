"""DJ-2026-009 卡 004：FB_1001 工位块在运行许可丢失时的行为（断点续跑、气缸按阀定）。

用 ``st_mini_sim`` 直接执行项目里的 .scl 源码（结构体类型从 ST_*.scl 装载），仿真时钟按真实毫秒。
不代替 InoProShop 仿真和用户签字。

运行：python -B -m pytest reviews/tools/test_dj009_card004_station.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from st_mini_sim import Sim

REPO = Path(__file__).resolve().parents[2]
PLC = REPO / "0100_PLC自动化"
SYSLIB = PLC / "01_SharedLibraries" / "SysLib"
P009 = PLC / "DJ-2026-009_汇川换型改造" / "02_PLC程序" / "PLC_ST"
FB1001 = P009 / "02_工位1_动作机构" / "FB_1001_Station1.scl"
TYPES = [
    SYSLIB / "actuator" / "FB_1011_CylinderControl" / "ST_Cylinder.scl",
    SYSLIB / "actuator" / "FB_1012_ConveyorMotor" / "ST_ConveyorMotor.scl",
    P009 / "01_外部设备交互" / "ST_ExternalDevice.scl",
    P009 / "02_工位1_动作机构" / "ST_Station1.scl",
]
SCAN_MS = 10

STEP_IDLE, STEP_WAIT, STEP_FEED, STEP_CLAMP, STEP_PROC, STEP_OUT, STEP_FAULT = 0, 1, 2, 10, 20, 30, 99


class Station:
    def __init__(self, fb_src: str | None = None, tmp: Path | None = None):
        self.sim = Sim()
        for t in TYPES:
            self.sim.load(t)
        path = FB1001
        if fb_src is not None:
            path = tmp / "FB_1001_mut.scl"
            path.write_text(fb_src, encoding="utf-8")
        self.sim.load(path)
        self.fb = self.sim.new_instance("FB_1001_Station1")
        self.st = self.sim.new_struct("ST_Station1")
        self.ext = self.sim.new_struct("ST_ExternalDevice")
        self.fb.bind("io_stStation", self.st)
        self.fb.bind("io_stExternal", self.ext)
        self.cyl(1, retracted=True)
        self.cyl(2, retracted=True)

    # 现场
    def cyl(self, n: int, *, extended: bool = False, retracted: bool = False) -> None:
        sts = self.st["stActuators"][f"stCyl{n}"]["stSts"]
        sts["IsExtended"], sts["IsRetracted"] = extended, retracted

    def cmd(self, n: int) -> tuple[bool, bool]:
        c = self.st["stActuators"][f"stCyl{n}"]["stCmd"]
        return c["Extend"], c["Retract"]

    @property
    def motor(self) -> bool:
        return self.st["stActuators"]["stMotorFwd"]["i_bFwdReq"]

    @property
    def step(self) -> int:
        return self.st["stStatus"]["iStep"]

    def safe(self, on: bool) -> None:
        self.st["stControl"]["bSafeToRun"] = on

    def scan(self, n: int = 1) -> None:
        for _ in range(n):
            self.sim.now_ms += SCAN_MS
            self.fb.call()

    def wait_ms(self, ms: int) -> None:
        self.scan(max(1, ms // SCAN_MS))

    def go_to_feeding(self) -> None:
        self.st["stControl"]["bAutoEnable"] = True
        self.safe(True)
        self.scan(3)
        assert self.step == STEP_WAIT
        self.ext["stUpstream"]["iInfeedStep"] = 30
        self.scan(2)
        assert self.step == STEP_FEED and self.motor

    def go_to_clamp(self) -> None:
        self.go_to_feeding()
        self.st["stSensors"]["bWorkPosSensor"] = True
        self.scan(2)
        assert self.step == STEP_CLAMP
        assert self.cmd(1) == (True, False) and self.cmd(2) == (True, False)


@pytest.fixture
def s() -> Station:
    return Station()


def test_power_up_without_permission_never_moves(s: Station) -> None:
    s.st["stControl"]["bAutoEnable"] = True
    s.ext["stUpstream"]["iInfeedStep"] = 30
    s.wait_ms(5_000)
    assert s.step == STEP_IDLE and not s.motor


def test_permission_lost_motor_off_same_scan_step_frozen(s: Station) -> None:
    s.go_to_feeding()
    s.safe(False)
    s.scan()
    assert not s.motor
    assert s.step == STEP_FEED
    assert s.st["stStatus"]["bFrozen"]
    s.wait_ms(60_000)
    assert s.step == STEP_FEED and not s.motor and not s.st["stStatus"]["bAlarm"]


def test_resume_continues_from_breakpoint(s: Station) -> None:
    s.go_to_feeding()
    s.safe(False)
    s.wait_ms(5_000)
    s.safe(True)
    s.scan()
    assert s.step == STEP_FEED and s.motor
    assert not s.st["stStatus"]["bFrozen"]
    s.st["stSensors"]["bWorkPosSensor"] = True
    s.scan(2)
    assert s.step == STEP_CLAMP


def test_step_timeout_restarts_after_resume(s: Station) -> None:
    s.go_to_feeding()
    s.wait_ms(8_000)
    s.safe(False)
    s.wait_ms(30_000)
    s.safe(True)
    s.wait_ms(5_000)               # 续跑后 5 s, 冻结前的 8 s 不累计
    assert not s.st["stStatus"]["bAlarm"]
    s.wait_ms(6_000)               # 续跑后超过 10 s 才报进料超时
    assert s.st["stStatus"]["bAlarm"] and s.st["stStatus"]["iAlarmCode"] == 101


def test_cylinders_hold_on_stop_by_default(s: Station) -> None:
    s.go_to_clamp()
    s.safe(False)
    s.scan(5)
    assert s.cmd(1) == (True, False) and s.cmd(2) == (True, False)   # 保持, 不一刀切缩回


def test_alarm_does_not_force_retract_by_default(s: Station) -> None:
    s.go_to_clamp()
    s.st["stActuators"]["stCyl1"]["stSts"]["Timeout"] = True        # 夹紧超时 -> 报警 102
    s.scan(3)
    assert s.st["stStatus"]["bAlarm"] and s.st["stStatus"]["iAlarmCode"] == 102
    assert s.cmd(1) == (True, False)


def test_retract_constant_true_retracts_on_stop(tmp_path: Path) -> None:
    src = FB1001.read_text(encoding="utf-8").replace(
        "CYL1_RETRACT_ON_STOP : BOOL := FALSE;", "CYL1_RETRACT_ON_STOP : BOOL := TRUE;"
    )
    s = Station(src, tmp_path)
    s.go_to_clamp()
    s.safe(False)
    s.scan()
    assert s.cmd(1) == (False, True)       # 夹紧阀定为“缩回”
    assert s.cmd(2) == (True, False)       # 顶升阀仍保持


def test_motion_stopped_status(s: Station) -> None:
    s.scan()
    assert s.st["stStatus"]["bMotionStopped"]           # 待机: 电机停, 气缸在原点
    s.go_to_feeding()
    assert not s.st["stStatus"]["bMotionStopped"]       # 电机有请求
    s.safe(False)
    s.scan(2)
    assert s.st["stStatus"]["bMotionStopped"]
    s.cyl(1)                                            # 气缸不在任何端点 = 在动
    s.scan()
    assert not s.st["stStatus"]["bMotionStopped"]


def test_mutation_no_permission_check_is_caught(tmp_path: Path) -> None:
    src = FB1001.read_text(encoding="utf-8").replace("IF NOT t_bSafeToRun THEN", "IF FALSE THEN")
    s = Station(src, tmp_path)
    s.go_to_feeding()
    s.safe(False)
    s.scan()
    assert s.motor  # 改坏后电机不停 —— 说明上面的用例确实在验这一行
