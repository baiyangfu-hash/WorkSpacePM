TYPE ST_CylinderCmd :
STRUCT
    Extend          : BOOL := FALSE;   // 动点命令: 伸出/真空ON/夹紧/下降
    Retract         : BOOL := FALSE;   // 原点命令: 收回/破真空/松开/上升
    ExtendedPos     : BOOL := FALSE;   // 动点到位
    RetractedPos    : BOOL := FALSE;   // 原点到位
    TimeoutMs       : DINT := 5000;
    DebounceMs      : DINT := 0;
    SolenoidType    : INT := 0;
    ExtendPolarity  : BOOL := FALSE;
    RetractPolarity : BOOL := FALSE;
    Mode            : INT := 1;
    ModeStatus      : WORD := 16#0000;
END_STRUCT;
END_TYPE
