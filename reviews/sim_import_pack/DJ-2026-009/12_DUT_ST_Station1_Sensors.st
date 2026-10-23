TYPE ST_Station1_Sensors :
STRUCT
    bInPosSensor    : BOOL;     // 入料到位光电
    bWorkPosSensor  : BOOL;     // 加工到位光电
    arrProductSens  : ARRAY[0..7] OF BOOL; // 产品检测传感器预留 8 路 (未接的保持 0), 任一路为 1 即有产品
END_STRUCT;
END_TYPE
