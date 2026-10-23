TYPE ST_Station1 :
STRUCT
    stControl       : ST_Station1_Control;     // 控制命令与模式
    stStatus        : ST_Station1_Status;      // 运行状态与报警
    stConfig        : ST_Station1_Config;      // 参数设定
    stSensors       : ST_Station1_Sensors;     // 传感器输入
    stActuators     : ST_Station1_Actuators;   // 执行机构 (电机/气缸)
END_STRUCT;
END_TYPE
