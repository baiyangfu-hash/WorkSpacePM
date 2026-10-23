TYPE ST_DownstreamDocking :
STRUCT
    // --- 本机 -> 下游流水线 (Machine Output / Downstream Input) ---
    bMachine_ReadyOut           : BOOL;     // (2) 机器准备好出料信号
    bMachine_SendModuleId       : BOOL;     // (3) 机器传组件ID信号
    bMachine_OutfeedReq         : BOOL;     // (6) 机器给下游出料请求信号
    bMachine_OutfeedArrivedAck  : BOOL;     // (8) 机器回收收到进料到位信号
    bMachine_HeartbeatToDown    : BOOL;     // [心跳] 本机向下游心跳 (4s ON / 4s OFF)

    // --- 下游流水线 -> 本机 (Downstream Output / Machine Input) ---
    bDownstream_LineReady       : BOOL;     // (1) 下游流水线准备好信号
    bDownstream_RcvModuleIdAck  : BOOL;     // (4) 下游流水线收到组件ID信号
    bDownstream_AllowOutfeed    : BOOL;     // (5) 下游流水线允许机器出料信号
    bDownstream_OutfeedArrived  : BOOL;     // (7) 下游流水线给机器进料到位信号
    bDownstream_HeartbeatFromDown: BOOL;    // [心跳] 下游输入心跳

    // --- 数据与诊断 ---
    sSendModuleID               : STRING[32]; // 发送给下游的组件 ID
    bDownstreamComFault         : BOOL;     // 下游通讯心跳超时故障 (12s)
    iOutfeedStep                : INT;      // 出料握手当前步序 0~8
END_STRUCT
END_TYPE
