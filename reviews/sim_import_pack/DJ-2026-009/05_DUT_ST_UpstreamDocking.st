TYPE ST_UpstreamDocking :
STRUCT
    // --- 本机 -> 上游流水线 (Machine Output / Upstream Input) ---
    bMachine_ReadyIn            : BOOL;     // (1) 机器准备好进料信号
    bMachine_RcvModuleIdAck     : BOOL;     // (4) 机器收到组件ID信号
    bMachine_AllowInfeed        : BOOL;     // (5) 机器允许上游进料信号
    bMachine_InfeedArrived      : BOOL;     // (7) 机器给上游组件进料到位信号
    bMachine_HeartbeatToUp      : BOOL;     // [心跳] 本机向上游心跳 (4s ON / 4s OFF)

    // --- 上游流水线 -> 本机 (Upstream Output / Machine Input) ---
    bUpstream_LineReady         : BOOL;     // (2) 上游流水线准备好信号
    bUpstream_SendModuleId      : BOOL;     // (3) 上游流水线传组件ID信号
    bUpstream_InfeedReq         : BOOL;     // (6) 上游流水线入料请求信号
    bUpstream_InfeedArrivedAck  : BOOL;     // (8) 上游回收收到进料到位信号
    bUpstream_HeartbeatFromUp   : BOOL;     // [心跳] 上游输入心跳

    // --- 数据与诊断 ---
    sRcvModuleID                : STRING[32]; // 接收的组件 ID
    bUpstreamComFault           : BOOL;     // 上游通讯心跳超时故障 (12s)
    iInfeedStep                 : INT;      // 进料握手当前步序 0~8
END_STRUCT
END_TYPE
