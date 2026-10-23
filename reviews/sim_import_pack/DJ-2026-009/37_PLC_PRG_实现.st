    // ============================================================================
    // 安全部分：全机安全管理 FB_1030 (共享库, CARD-DJ-2026-009-004 预做)
    // 读安全继电器反馈/急停/门锁/总线状态, 给出运行许可; 两次复位 (隔 10 s) + 按启动才许可.
    // 本段在最前面: 许可一丢, 本扫描内后面的握手块和工位块就停.
    // ============================================================================
    // @安全区 开始：安全点读入、FB_1030 调用、运行许可与门锁输出
    arrSafetyFault[0] := SAFETY_FAULT;
    arrEStopOk[0] := ESTOP_OK;
    // 安全门: 只读 DOOR_COUNT 扇 (GVL_SafetyIO, 默认 8); 没用到的数组位保持初值 TRUE (门正常)
    IF DOOR_COUNT >= 1 THEN arrDoorClosed[0] := DOOR1_LOCKED; arrDoorReqBtn[0] := DOOR1_REQ_BTN; END_IF;
    IF DOOR_COUNT >= 2 THEN arrDoorClosed[1] := DOOR2_LOCKED; arrDoorReqBtn[1] := DOOR2_REQ_BTN; END_IF;
    IF DOOR_COUNT >= 3 THEN arrDoorClosed[2] := DOOR3_LOCKED; arrDoorReqBtn[2] := DOOR3_REQ_BTN; END_IF;
    IF DOOR_COUNT >= 4 THEN arrDoorClosed[3] := DOOR4_LOCKED; arrDoorReqBtn[3] := DOOR4_REQ_BTN; END_IF;
    IF DOOR_COUNT >= 5 THEN arrDoorClosed[4] := DOOR5_LOCKED; arrDoorReqBtn[4] := DOOR5_REQ_BTN; END_IF;
    IF DOOR_COUNT >= 6 THEN arrDoorClosed[5] := DOOR6_LOCKED; arrDoorReqBtn[5] := DOOR6_REQ_BTN; END_IF;
    IF DOOR_COUNT >= 7 THEN arrDoorClosed[6] := DOOR7_LOCKED; arrDoorReqBtn[6] := DOOR7_REQ_BTN; END_IF;
    IF DOOR_COUNT >= 8 THEN arrDoorClosed[7] := DOOR8_LOCKED; arrDoorReqBtn[7] := DOOR8_REQ_BTN; END_IF;
    GlobalVars.stExternal.bEmergencyStop := ESTOP_OK;   // 急停按钮状态, 只报警显示; 握手使能改看运行许可
    GlobalVars.fbSafety(
        i_arrSafetyFault := arrSafetyFault,
        i_arrEStopOk := arrEStopOk,
        i_arrCurtainOk := arrCurtainOk,
        i_arrDoorClosed := arrDoorClosed,
        i_bFieldbusOk := FIELDBUS_OK,
        i_bResetBtn := RESET_BTN,
        i_bStartBtn := START_BTN,
        i_bAutoMode := GlobalVars.stStation1.stControl.bAutoEnable,
        i_bMotionStopped := GlobalVars.stStation1.stStatus.bMotionStopped,
        i_arrDoorReqBtn := arrDoorReqBtn
    );
    DOOR1_UNLOCK := GlobalVars.fbSafety.q_arrDoorUnlock[0];
    DOOR1_REQ_LAMP := GlobalVars.fbSafety.q_arrDoorLamp[0];
    DOOR2_UNLOCK := GlobalVars.fbSafety.q_arrDoorUnlock[1];
    DOOR2_REQ_LAMP := GlobalVars.fbSafety.q_arrDoorLamp[1];
    DOOR3_UNLOCK := GlobalVars.fbSafety.q_arrDoorUnlock[2];
    DOOR3_REQ_LAMP := GlobalVars.fbSafety.q_arrDoorLamp[2];
    DOOR4_UNLOCK := GlobalVars.fbSafety.q_arrDoorUnlock[3];
    DOOR4_REQ_LAMP := GlobalVars.fbSafety.q_arrDoorLamp[3];
    DOOR5_UNLOCK := GlobalVars.fbSafety.q_arrDoorUnlock[4];
    DOOR5_REQ_LAMP := GlobalVars.fbSafety.q_arrDoorLamp[4];
    DOOR6_UNLOCK := GlobalVars.fbSafety.q_arrDoorUnlock[5];
    DOOR6_REQ_LAMP := GlobalVars.fbSafety.q_arrDoorLamp[5];
    DOOR7_UNLOCK := GlobalVars.fbSafety.q_arrDoorUnlock[6];
    DOOR7_REQ_LAMP := GlobalVars.fbSafety.q_arrDoorLamp[6];
    DOOR8_UNLOCK := GlobalVars.fbSafety.q_arrDoorUnlock[7];
    DOOR8_REQ_LAMP := GlobalVars.fbSafety.q_arrDoorLamp[7];
    GlobalVars.stStation1.stControl.bSafeToRun := GlobalVars.fbSafety.q_bSafeToRun;
    // @安全区 结束

    // ============================================================================
    // 第0部分：上下游 Modbus TCP 客户端数据映射 (FB_3002, CARD-DJ-2026-009-001)
    // 先解包对方寄存器, 再由第1部分握手; 本机信号在下一周期封包 (1 个扫描周期延迟)
    // ============================================================================
    // @安全区 开始：Modbus 客户端使能与链路状态 (断线判定的数据来源, 见 safety_zone.yml)
    GlobalVars.fbModbusClient(
        i_bEnable := GlobalVars.bModbusEnable,
        i_bUpLinkOK := GlobalVars.bModbusUpLinkOK,
        i_bDownLinkOK := GlobalVars.bModbusDownLinkOK,
        io_stExternal := GlobalVars.stExternal,
        io_arrUpRead := GlobalVars.awModbusUpRead,
        io_arrUpWrite := GlobalVars.awModbusUpWrite,
        io_arrDownRead := GlobalVars.awModbusDownRead,
        io_arrDownWrite := GlobalVars.awModbusDownWrite
    );
    // [仿真包] CODESYS 中 VAR_IN_OUT 按引用传, 外部不能读, 本行注释掉: GlobalVars.stExternal := GlobalVars.fbModbusClient.io_stExternal;
    // @安全区 结束

    // ============================================================================
    // 第1部分：外部设备交互 (ST_ExternalDevice)
    // CARD-DJ-2026-009-003: 补接全部输入输出 (原来只传 io_stExternal, i_bEnable 默认 0, 握手不跑)
    // 工位状态取上一周期 FB_1001 的结果 (1 个扫描周期延迟)
    // ============================================================================
    // @安全区 开始：握手运行许可, 复位来源, 工位状态接入断线联锁
    // CARD-DJ-2026-009-004: 使能原来看急停按钮点 (开安全门时按钮点仍是 1, 握手照走 = 漏洞), 改为:
    //   使能常开 = 心跳一直发 (用户 10-22: 心跳停了对方判断线, 以后同一心跳也给 MES);
    //   运行许可 = FB_1030, 许可丢失只撤握手. 复位原来一按就清, 改为: 安全停机后只认 FB_1030 的
    //   运行复位脉冲; 运行许可中按复位照常清通讯故障
    GlobalVars.fbExternalDevice(
        i_bEnable := TRUE,
        // Modbus 停用时对方信号冻结在最后值, 不能拿来走握手 (Codex 评审 #77): 运行许可同时看 bModbusEnable
        i_bSafeToRun := GlobalVars.fbSafety.q_bSafeToRun AND GlobalVars.bModbusEnable,
        i_bAutoMode := GlobalVars.stStation1.stControl.bAutoEnable,
        i_bResetCmd := GlobalVars.fbSafety.q_bRunResetPulse
                       OR (GlobalVars.fbSafety.q_bSafeToRun AND (GlobalVars.stGlobal.i_bReset OR GlobalVars.stStation1.stControl.bReset)),
        i_bMachineReadyIn := GlobalVars.stStation1.stStatus.bWaitMaterial,
        i_bMachineReadyOut := GlobalVars.stStation1.stStatus.bReadyOut,
        i_bInfeedArrivedSens := GlobalVars.stStation1.stSensors.bInPosSensor,
        i_bProductPresent := GlobalVars.stStation1.stStatus.bProductPresent,
        q_bAllowInfeedAct => GlobalVars.bExtAllowInfeedAct,
        q_bAllowOutfeedAct => GlobalVars.bExtAllowOutfeedAct,
        q_bUpstreamDone => GlobalVars.bExtUpstreamDone,
        q_bDownstreamDone => GlobalVars.bExtDownstreamDone,
        q_bComAlarm => GlobalVars.bExtComAlarm,
        q_wErrorCode => GlobalVars.wExtErrorCode,
        io_stExternal := GlobalVars.stExternal,
        io_sMachineModuleID := GlobalVars.sMachineModuleID,
        io_stIdHmi := GlobalVars.stModuleIdHmi
    );
    // [仿真包] CODESYS 中 VAR_IN_OUT 按引用传, 外部不能读, 本行注释掉: GlobalVars.stExternal := GlobalVars.fbExternalDevice.io_stExternal;
    // @安全区 结束

    // ============================================================================
    // 第2部分：工位1 动作机构 (ST_Station1)
    // ============================================================================
    GlobalVars.fbStation1(
        io_stStation := GlobalVars.stStation1,
        io_stExternal := GlobalVars.stExternal
    );
    // [仿真包] CODESYS 中 VAR_IN_OUT 按引用传, 外部不能读, 本行注释掉: GlobalVars.stStation1 := GlobalVars.fbStation1.io_stStation;
    // [仿真包] CODESYS 中 VAR_IN_OUT 按引用传, 外部不能读, 本行注释掉: GlobalVars.stExternal := GlobalVars.fbStation1.io_stExternal;

    // ============================================================================
    // 第3部分：公共报警汇总 (ST_CommonAlarm, 报警汇总卡预做)
    // 三路报警源本扫描的结果只读接入, 不改它们的动作; 码表见 FB_2001 文件头.
    // 原来这三个输入 (输送/取放料/打胶送料, 005 抄来的) 没人写, 报警块报不出任何报警.
    // ============================================================================
    // @安全区 开始：只读安全管理块报警字 (急停/门/继电器/总线, 只用于报警显示)
    GlobalVars.stGlobal.i_dwSafetyAlarm := GlobalVars.fbSafety.q_dwAlarm;
    // @安全区 结束
    GlobalVars.stGlobal.i_wExtErrorCode := GlobalVars.wExtErrorCode;
    GlobalVars.stGlobal.i_iStationAlarm := GlobalVars.stStation1.stStatus.iAlarmCode;
    GlobalVars.fbCommonAlarm(io_stGlobal := GlobalVars.stGlobal);
    // [仿真包] CODESYS 中 VAR_IN_OUT 按引用传, 外部不能读, 本行注释掉: GlobalVars.stGlobal := GlobalVars.fbCommonAlarm.io_stGlobal;
