// GlobalVars: 按 PLC变量定义文档_VAR.md 和 OB1 用到的变量生成 (仿真导入包)
// 在 InoProShop 新建 GVL, 名字必须叫 GlobalVars (OB1 里写的是 GlobalVars.xxx)
VAR_GLOBAL
    stGlobal          : ST_CommonAlarm;
    stExternal        : ST_ExternalDevice;
    stStation1        : ST_Station1;

    bModbusEnable     : BOOL;
    bModbusUpLinkOK   : BOOL;
    bModbusDownLinkOK : BOOL;
    awModbusUpRead    : ARRAY[0..31] OF WORD;
    awModbusUpWrite   : ARRAY[0..31] OF WORD;
    awModbusDownRead  : ARRAY[0..31] OF WORD;
    awModbusDownWrite : ARRAY[0..31] OF WORD;

    fbSafety          : FB_1030_SafetyManager;
    fbModbusClient    : FB_3002_ModbusTcpClient;
    fbExternalDevice  : FB_3001_ExternalInteraction;
    fbStation1        : FB_1001_Station1;
    fbCommonAlarm     : FB_2001_CommonAlarm_AllStation;

    bExtAllowInfeedAct  : BOOL;
    bExtAllowOutfeedAct : BOOL;
    bExtUpstreamDone    : BOOL;
    bExtDownstreamDone  : BOOL;
    bExtComAlarm        : BOOL;
    wExtErrorCode       : WORD;
END_VAR

VAR_GLOBAL RETAIN
    sMachineModuleID  : STRING[32];
    stModuleIdHmi     : ST_ModuleIdHmi;
END_VAR
