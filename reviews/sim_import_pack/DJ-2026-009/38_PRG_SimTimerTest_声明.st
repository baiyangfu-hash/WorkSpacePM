PROGRAM PRG_SimTimerTest
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
