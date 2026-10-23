TYPE ST_Station1_Control :
STRUCT
    bAutoEnable     : BOOL;     // 自动运行使能
    bManualStart    : BOOL;     // 手动单步启动
    bReset          : BOOL;     // 故障复位
    bPause          : BOOL;     // 暂停
    bSingleStepMode : BOOL;     // 单步模式
    bSafeToRun      : BOOL;     // 运行许可, OB1 每扫描从 FB_1030 q_bSafeToRun 写入 (CARD-DJ-2026-009-004)
END_STRUCT;
END_TYPE
