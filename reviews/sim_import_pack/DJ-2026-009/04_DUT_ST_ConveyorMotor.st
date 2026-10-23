TYPE ST_ConveyorMotor :
STRUCT
    i_bEnable       : BOOL := FALSE;   // 使能
    i_bFwdReq       : BOOL := FALSE;   // 正转请求
    i_bRevReq       : BOOL := FALSE;   // 反转请求
    i_bSlowReq      : BOOL := FALSE;   // 慢速请求
    SafetyDoorOk    : BOOL := TRUE;    // 安全门正常
    VfdFault        : BOOL := FALSE;   // 变频器/驱动器故障
    FwdOut          : BOOL := FALSE;   // 正转输出
    RevOut          : BOOL := FALSE;   // 反转输出
    SlowOut         : BOOL := FALSE;   // 慢速输出
    q_bFwdOut       : BOOL := FALSE;   // 正转输出
    q_bRevOut       : BOOL := FALSE;   // 反转输出
    q_bSlowOut      : BOOL := FALSE;   // 慢速输出
    q_bRunning      : BOOL := FALSE;   // 运行标志
    q_bFault        : BOOL := FALSE;   // 故障标志
END_STRUCT;
END_TYPE
