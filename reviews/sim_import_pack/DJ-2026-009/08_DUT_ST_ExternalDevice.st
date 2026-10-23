TYPE ST_ExternalDevice :
STRUCT
    stUpstream      : ST_UpstreamDocking;   // 上游对接 8 步握手
    stDownstream    : ST_DownstreamDocking; // 下游对接 8 步握手
    bEmergencyStop  : BOOL;                 // 外部总线急停 (1=正常, 0=急停)
    bSafetyDoorOK   : BOOL;                 // 外部安全门锁信号
    bAnyComFault    : BOOL;                 // 外部通讯综合故障
END_STRUCT
END_TYPE
