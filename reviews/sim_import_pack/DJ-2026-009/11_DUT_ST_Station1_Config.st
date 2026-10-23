TYPE ST_Station1_Config :
STRUCT
    dDebounceMs     : DINT;     // 光电消抖时间 (ms, 默认 100)
    dCylTimeoutMs   : DINT;     // 气缸动作超时时间 (ms, 默认 5000)
    dProcessTimeMs  : DINT;     // 工艺加工延时时间 (ms, 默认 2000)
END_STRUCT;
END_TYPE
