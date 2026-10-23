PROGRAM PRG_SimPartner
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
