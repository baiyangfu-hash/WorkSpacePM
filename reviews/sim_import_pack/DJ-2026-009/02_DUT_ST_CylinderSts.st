TYPE ST_CylinderSts :
STRUCT
    SolenoidA       : BOOL := FALSE;   // 线圈A输出
    SolenoidB       : BOOL := FALSE;   // 线圈B输出
    IsExtended      : BOOL := FALSE;   // 已到动点
    IsRetracted     : BOOL := FALSE;   // 已到原点
    Timeout         : BOOL := FALSE;   // 动作超时报警
    SensorFault     : BOOL := FALSE;   // 传感器冲突
END_STRUCT;
END_TYPE
