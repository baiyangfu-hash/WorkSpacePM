TYPE ST_Station1_Actuators :
STRUCT
    stMotorFwd      : ST_ConveyorMotor; // 进料输送电机
    stCyl1          : ST_Cylinder;      // 夹紧气缸
    stCyl2          : ST_Cylinder;      // 顶升气缸
END_STRUCT;
END_TYPE
