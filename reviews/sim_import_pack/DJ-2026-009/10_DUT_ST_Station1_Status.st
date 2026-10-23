TYPE ST_Station1_Status :
STRUCT
    iStep           : DINT;     // 当前工步号
    bRunning        : BOOL;     // 运行中
    bDone           : BOOL;     // 本周期动作完成
    bAlarm          : BOOL;     // 站级报警
    iAlarmCode      : DINT;     // 报警代码 (101~199)
    bWaitMaterial   : BOOL;     // 等待来料
    bProcessing     : BOOL;     // 加工中
    bReadyOut       : BOOL;     // 加工完成可出料 (出料步且气缸已松开)
    bProductPresent : BOOL;     // 本工位有产品 (入料到位/加工到位/预留产品传感器任一路为 1)
    bFrozen         : BOOL;     // 安全停机, 步序冻结在断点等续跑 (CARD-DJ-2026-009-004)
    bMotionStopped  : BOOL;     // 动作完全停止: 电机无请求且不转, 气缸都在端点 (接 FB_1030 i_bMotionStopped)
END_STRUCT;
END_TYPE
