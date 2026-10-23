"""把 DJ-2026-009 的 .scl 源码转成 InoProShop (CODESYS) 可直接粘贴的仿真导入包.

只做平台写法转换, 不改任何逻辑:
  - 去掉 BEGIN 一行和 END_FUNCTION_BLOCK / END_FUNCTION / END_ORGANIZATION_BLOCK
  - 去掉变量前的 # (16#FF、T#5S、DWORD#1 这类常量前缀不动)
  - FB_1001 的 CONST ... END_CONST 改成 VAR CONSTANT ... END_VAR
  - OB1 改成 PROGRAM PLC_PRG; VAR_IN_OUT 回写行 (CODESYS 按引用传, 外部不能读) 注释掉
  - GlobalVars 声明按 PLC变量定义文档 生成
每个 POU 拆成 "声明" 和 "实现" 两份, 按导入顺序编号.

用法: python -B reviews/tools/make_inoproshop_pack.py [--out 目录]
自检: 每个 POU 的 (声明 + 实现) 去空白后的记号序列, 必须等于原文件做上述转换后的记号序列.
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLC = ROOT / "0100_PLC自动化"
LIB = PLC / "01_SharedLibraries" / "SysLib"
P009 = PLC / "DJ-2026-009_汇川换型改造" / "02_PLC程序" / "PLC_ST"

HASH_RE = re.compile(r"(?<![A-Za-z0-9_])#(?=[A-Za-z_])")
END_POU_RE = re.compile(r"^\s*END_(FUNCTION_BLOCK|FUNCTION|ORGANIZATION_BLOCK)\s*$")
TYPE_RE = re.compile(r"^TYPE\s+(\w+)\s*:", re.M)

# (编号, 来源文件) —— 结构体按被引用的先后排
DUT_FILES = [
    LIB / "actuator" / "FB_1011_CylinderControl" / "ST_Cylinder.scl",
    LIB / "actuator" / "FB_1012_ConveyorMotor" / "ST_ConveyorMotor.scl",
    P009 / "01_外部设备交互" / "ST_ExternalDevice.scl",
    P009 / "02_工位1_动作机构" / "ST_Station1.scl",
    P009 / "05_公共报警" / "ST_CommonAlarm.scl",
]
POU_FILES = [
    LIB / "timer" / "FB_TON.scl",
    LIB / "timer" / "FB_TONR.scl",
    LIB / "edge" / "FB_R_TRIG.scl",
    LIB / "safety" / "FB_1030_SafetyManager.scl",
    P009 / "01_外部设备交互" / "FC_3003_CheckModuleId.scl",
    P009 / "01_外部设备交互" / "FB_3002_ModbusTcpClient.scl",
    P009 / "01_外部设备交互" / "FB_3001_ExternalInteraction.scl",
    P009 / "02_工位1_动作机构" / "FB_1001_Station1.scl",
    P009 / "05_公共报警" / "FB_2001_CommonAlarm_AllStation.scl",
]
GVL_SAFETY = P009 / "00_全局数据" / "GVL_SafetyIO.st"
OB1 = P009 / "00_主程序" / "OB1.scl"

GLOBALVARS = """// GlobalVars: 按 PLC变量定义文档_VAR.md 和 OB1 用到的变量生成 (仿真导入包)
// 在 InoProShop 新建 GVL, 名字必须叫 GlobalVars (OB1 里写的是 GlobalVars.xxx)
VAR_GLOBAL
    stGlobal          : ST_CommonAlarm;
    stExternal        : ST_ExternalDevice;
    stStation1        : ST_Station1;

    bModbusEnable     : BOOL;
    bModbusUpLinkOK   : BOOL;
    bModbusDownLinkOK : BOOL;
    awModbusUpRead    : ARRAY[0..31] OF WORD;
    awModbusUpWrite   : ARRAY[0..31] OF WORD;
    awModbusDownRead  : ARRAY[0..31] OF WORD;
    awModbusDownWrite : ARRAY[0..31] OF WORD;

    fbSafety          : FB_1030_SafetyManager;
    fbModbusClient    : FB_3002_ModbusTcpClient;
    fbExternalDevice  : FB_3001_ExternalInteraction;
    fbStation1        : FB_1001_Station1;
    fbCommonAlarm     : FB_2001_CommonAlarm_AllStation;

    bExtAllowInfeedAct  : BOOL;
    bExtAllowOutfeedAct : BOOL;
    bExtUpstreamDone    : BOOL;
    bExtDownstreamDone  : BOOL;
    bExtComAlarm        : BOOL;
    wExtErrorCode       : WORD;
END_VAR

VAR_GLOBAL RETAIN
    sMachineModuleID  : STRING[32];
    stModuleIdHmi     : ST_ModuleIdHmi;
END_VAR
"""

TIMER_TEST = """PROGRAM PRG_SimTimerTest
// 仿真专用: 签字单 3.1 第 1、2 条 (FB_TON / FB_TONR 真实计时), 不进现场程序
VAR
    dPt      : DINT := 10000;   // 预设 10 s
    bTonIn   : BOOL;            // 第 1 条: 置 1 开始计时, 置 0 清零
    fbTon    : FB_TON;
    bTonQ    : BOOL;
    dTonEt   : DINT;
    bTonrIn  : BOOL;            // 第 2 条: 通 4 s、断 3 s、再通 6 s
    bTonrR   : BOOL;            // 第 2 条: 置 1 清零
    fbTonr   : FB_TONR;
    bTonrQ   : BOOL;
    dTonrEt  : DINT;
END_VAR
"""
TIMER_TEST_IMPL = """fbTon(IN := bTonIn, PT := dPt, Q => bTonQ, ET => dTonEt);
fbTonr(IN := bTonrIn, R := bTonrR, PT := dPt, Q => bTonrQ, ET => dTonrEt);
"""

PARTNER = """PROGRAM PRG_SimPartner
// 仿真专用: 模拟上下游流水线, 经 Modbus 寄存器镜像收发 (和现场一样走 FB_3002 解包/封包), 不进现场程序.
// 寄存器: 地址 0 = 对方->本机状态字 (bit0~3 握手位, bit15 心跳), 地址 2~17 = 组件 ID (高字节在前)
VAR
    bUpHbOn           : BOOL := TRUE;   // 上游心跳开; 置 0 = 上游心跳停 (第 6 条)
    bDownHbOn         : BOOL := TRUE;   // 下游心跳开
    bUpLineReady      : BOOL;           // 上游 (2) 准备好
    bUpSendId         : BOOL;           // 上游 (3) 传组件 ID
    bUpInfeedReq      : BOOL;           // 上游 (6) 入料请求
    bUpArrivedAck     : BOOL;           // 上游 (8) 收到进料到位
    bDnLineReady      : BOOL;           // 下游 (1) 准备好
    bDnRcvIdAck       : BOOL;           // 下游 (4) 收到组件 ID
    bDnAllowOutfeed   : BOOL;           // 下游 (5) 允许出料
    bDnOutfeedArrived : BOOL;           // 下游 (7) 进料到位
    sUpId             : STRING[32] := 'L06A20261020165232'; // 上游要传的组件 ID (第 8 条可改成 32 字符或清空)
    sDnReadBack       : STRING[32];     // 下游从本机读回的 ID (第 8 条对照)
    fbHbTimer         : FB_TON;
    bHb               : BOOL;
    wStatus           : WORD;
    iReg              : INT;
    iLen              : INT;
    iChar             : INT;
    byHi              : BYTE;
    byLo              : BYTE;
    bEnd              : BOOL;
END_VAR
"""
PARTNER_IMPL = """// 对方心跳: 4 s 翻一次
fbHbTimer(IN := NOT fbHbTimer.Q, PT := 4000);
IF fbHbTimer.Q THEN
    bHb := NOT bHb;
END_IF;

// 上游 -> 本机 状态字
wStatus := 16#0000;
IF bUpLineReady THEN wStatus := wStatus OR 16#0001; END_IF;
IF bUpSendId THEN wStatus := wStatus OR 16#0002; END_IF;
IF bUpInfeedReq THEN wStatus := wStatus OR 16#0004; END_IF;
IF bUpArrivedAck THEN wStatus := wStatus OR 16#0008; END_IF;
IF bUpHbOn AND bHb THEN wStatus := wStatus OR 16#8000; END_IF;
GlobalVars.awModbusUpRead[0] := wStatus;

// 上游组件 ID: 第 2n 个字符放高字节, 第 2n+1 个放低字节, 不足补 0 (和 FB_3002 封包同一写法)
iLen := LEN(sUpId);
FOR iReg := 0 TO 15 DO
    byHi := 16#00;
    byLo := 16#00;
    IF (2 * iReg) < iLen THEN
        byHi := sUpId[2 * iReg];
    END_IF;
    IF (2 * iReg + 1) < iLen THEN
        byLo := sUpId[2 * iReg + 1];
    END_IF;
    GlobalVars.awModbusUpRead[2 + iReg] := SHL(BYTE_TO_WORD(byHi), 8) OR BYTE_TO_WORD(byLo);
END_FOR;

// 下游 -> 本机 状态字
wStatus := 16#0000;
IF bDnLineReady THEN wStatus := wStatus OR 16#0001; END_IF;
IF bDnRcvIdAck THEN wStatus := wStatus OR 16#0002; END_IF;
IF bDnAllowOutfeed THEN wStatus := wStatus OR 16#0004; END_IF;
IF bDnOutfeedArrived THEN wStatus := wStatus OR 16#0008; END_IF;
IF bDownHbOn AND bHb THEN wStatus := wStatus OR 16#8000; END_IF;
GlobalVars.awModbusDownRead[0] := wStatus;

// 下游读回本机发出的组件 ID (和 FB_3002 解包同一写法, 遇 0 结束)
sDnReadBack := '';
bEnd := FALSE;
iChar := 0;
FOR iReg := 0 TO 15 DO
    byHi := WORD_TO_BYTE(SHR(GlobalVars.awModbusDownWrite[2 + iReg], 8));
    byLo := WORD_TO_BYTE(GlobalVars.awModbusDownWrite[2 + iReg] AND 16#00FF);
    IF NOT bEnd THEN
        IF byHi = 16#00 THEN
            bEnd := TRUE;
        ELSE
            sDnReadBack[iChar] := byHi;
            iChar := iChar + 1;
        END_IF;
    END_IF;
    IF NOT bEnd THEN
        IF byLo = 16#00 THEN
            bEnd := TRUE;
        ELSE
            sDnReadBack[iChar] := byLo;
            iChar := iChar + 1;
        END_IF;
    END_IF;
END_FOR;
sDnReadBack[iChar] := 16#00;
"""


def read(path):
    return path.read_text(encoding="utf-8")


def strip_hash(text):
    return HASH_RE.sub("", text)


def split_pou(text):
    """返回 (声明, 实现); 以单独一行的 BEGIN 为界 (没有 BEGIN 的已是 CODESYS 写法,
    以最后一个 END_VAR 为界), 去掉末尾 END_xxx 行."""
    lines = text.splitlines()
    idx = [i for i, l in enumerate(lines) if l.strip() == "BEGIN"]
    if len(idx) > 1:
        raise SystemExit("BEGIN 行不唯一")
    if idx:
        decl, rest = lines[: idx[0]], lines[idx[0] + 1:]
    else:
        last = max(i for i, l in enumerate(lines) if l.strip().startswith("END_VAR"))
        decl, rest = lines[: last + 1], lines[last + 1:]
    body = [l for l in rest if not END_POU_RE.match(l)]
    return "\n".join(decl).rstrip() + "\n", "\n".join(body).strip("\n") + "\n"


def convert_const(decl):
    decl = re.sub(r"^(\s*)CONST\s*$", r"\1VAR CONSTANT", decl, flags=re.M)
    return re.sub(r"^(\s*)END_CONST\s*$", r"\1END_VAR", decl, flags=re.M)


COPYBACK_RE = re.compile(r"^(\s*)(GlobalVars\.\w+\s*:=\s*GlobalVars\.\w+\.io_\w+\s*;.*)$", re.M)


def comment_copyback(body):
    return COPYBACK_RE.sub(
        r"\1// [仿真包] CODESYS 中 VAR_IN_OUT 按引用传, 外部不能读, 本行注释掉: \2", body)


def split_types(text):
    starts = [m.start() for m in TYPE_RE.finditer(text)]
    out = []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(text)
        chunk = text[s:e]
        end = chunk.index("END_TYPE") + len("END_TYPE")
        out.append((TYPE_RE.match(chunk).group(1), chunk[:end] + "\n"))
    return out


TOKEN_RE = re.compile(r"//[^\n]*|\(\*.*?\*\)|\S+", re.S)


def tokens(text):
    return [t for t in TOKEN_RE.findall(text) if not t.startswith("//") and not t.startswith("(*")]


def build(out):
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("[0-9][0-9]_*.st"):
        old.unlink()
    n = 0
    written = []

    def put(name, text):
        nonlocal n
        n += 1
        p = out / f"{n:02d}_{name}.st"
        p.write_text(text, encoding="utf-8")
        written.append(p.name)

    for f in DUT_FILES:
        for tname, chunk in split_types(read(f)):
            put(f"DUT_{tname}", chunk)
    for f in POU_FILES:
        src = strip_hash(read(f))
        decl, body = split_pou(src)
        decl = convert_const(decl)
        name = f.stem
        put(f"{name}_声明", decl)
        put(f"{name}_实现", body)
        # 自检: 记号序列不丢不多
        ref = convert_const(src)
        ref = "\n".join(l for l in ref.splitlines()
                        if l.strip() != "BEGIN" and not END_POU_RE.match(l))
        if tokens(ref) != tokens(decl + body):
            raise SystemExit(f"自检失败: {name}")
    put("GVL_SafetyIO", read(GVL_SAFETY))
    put("GVL_GlobalVars", GLOBALVARS)
    src = strip_hash(read(OB1))
    _, body = split_pou(src)
    put("PLC_PRG_声明", "PROGRAM PLC_PRG\nVAR\nEND_VAR\n")
    put("PLC_PRG_实现", comment_copyback(body))
    put("PRG_SimTimerTest_声明", TIMER_TEST)
    put("PRG_SimTimerTest_实现", TIMER_TEST_IMPL)
    put("PRG_SimPartner_声明", PARTNER)
    put("PRG_SimPartner_实现", PARTNER_IMPL)
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "reviews" / "sim_import_pack" / "DJ-2026-009"))
    args = ap.parse_args()
    for name in build(Path(args.out)):
        print(name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
