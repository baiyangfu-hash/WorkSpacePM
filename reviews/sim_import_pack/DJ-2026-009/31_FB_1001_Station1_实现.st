    // =========================================================================
    // 0. 定时器顶部批量无条件调用 (LSP-906/903)
    // =========================================================================
    s_tStepTimer(IN := s_tStepTimer.IN, PT := s_tStepTimer.PT, Q => s_tStepTimer.Q, ET => s_tStepTimer.ET);
    s_tProcessTimer(IN := s_tProcessTimer.IN, PT := s_tProcessTimer.PT, Q => s_tProcessTimer.Q, ET => s_tProcessTimer.ET);

    // =========================================================================
    // 1. 解包临时变量
    // =========================================================================
    t_bAutoEnable  := io_stStation.stControl.bAutoEnable;
    t_bSafeToRun   := io_stStation.stControl.bSafeToRun;
    t_bReset       := io_stStation.stControl.bReset;
    t_bInPos       := io_stStation.stSensors.bInPosSensor;
    t_bWorkPos     := io_stStation.stSensors.bWorkPosSensor;

    t_dCylTimeout  := io_stStation.stConfig.dCylTimeoutMs;
    IF t_dCylTimeout <= 0 THEN
        t_dCylTimeout := 5000; // 默认 5000ms
    END_IF;

    t_dProcessTime := io_stStation.stConfig.dProcessTimeMs;
    IF t_dProcessTime <= 0 THEN
        t_dProcessTime := 2000; // 默认 2000ms
    END_IF;

    // =========================================================================
    // 2. 故障复位
    // =========================================================================
    IF t_bReset THEN
        s_bAlarm := FALSE;
        s_iAlarmCode := 0;
        IF s_iStep = STEP_FAULT OR (s_iStep <> STEP_IDLE AND NOT t_bAutoEnable) THEN
            s_iStep := STEP_IDLE;
        END_IF;
    END_IF;

    // =========================================================================
    // 3. 主工步状态机
    // =========================================================================
    // @安全区 开始：运行许可丢失时冻结步序 (断点续跑), 停机时电机清零、气缸按阀定
    IF NOT t_bSafeToRun THEN
        // 安全许可丢失 (急停/开门/光栅/总线断) 或还没复位+启动: 同一扫描电机清零, 步序冻结不回零
        // (3Sun 断点续跑, 规范 2.5; 用户 10-21). 许可回来 (两次复位 + 按启动) 后从冻结的步接着走.
        // 冻结期间工步/加工计时停止, 续跑时该步的超时从头计.
        io_stStation.stActuators.stMotorFwd.i_bFwdReq := FALSE;
        IF CYL1_RETRACT_ON_STOP THEN
            io_stStation.stActuators.stCyl1.stCmd.Extend := FALSE;
            io_stStation.stActuators.stCyl1.stCmd.Retract := TRUE;
        END_IF;
        IF CYL2_RETRACT_ON_STOP THEN
            io_stStation.stActuators.stCyl2.stCmd.Extend := FALSE;
            io_stStation.stActuators.stCyl2.stCmd.Retract := TRUE;
        END_IF;
        s_bRunning := FALSE;
        s_bDone := FALSE;
        s_tStepTimer.IN := FALSE;
        s_tProcessTimer.IN := FALSE;
    ELSIF NOT t_bAutoEnable OR s_bAlarm THEN
        // 非使能或报警模式下，撤销电机命令; 气缸按阀定保持或缩回 (原来一刀切强制缩回, 规范 2.3 重审)
        io_stStation.stActuators.stMotorFwd.i_bFwdReq := FALSE;
        IF CYL1_RETRACT_ON_STOP THEN
            io_stStation.stActuators.stCyl1.stCmd.Extend := FALSE;
            io_stStation.stActuators.stCyl1.stCmd.Retract := TRUE;
        END_IF;
        IF CYL2_RETRACT_ON_STOP THEN
            io_stStation.stActuators.stCyl2.stCmd.Extend := FALSE;
            io_stStation.stActuators.stCyl2.stCmd.Retract := TRUE;
        END_IF;
        // 握手准备信号由 FB_3001 根据 stStatus.bWaitMaterial / bReadyOut 发出, 本块不直接写
        // (直接写会绕过 FB_3001 的通讯故障联锁, CARD-DJ-2026-009-003)

        s_bRunning := FALSE;
        s_bDone := FALSE;
        s_tStepTimer.IN := FALSE;
        s_tProcessTimer.IN := FALSE;
        
        IF s_bAlarm THEN
            s_iStep := STEP_FAULT;
        ELSE
            s_iStep := STEP_IDLE;
        END_IF;
    ELSE
        s_bRunning := TRUE;

        CASE s_iStep OF
            STEP_IDLE:
                s_bDone := FALSE;
                io_stStation.stActuators.stMotorFwd.i_bFwdReq := FALSE;
                io_stStation.stActuators.stCyl1.stCmd.Extend := FALSE;
                io_stStation.stActuators.stCyl1.stCmd.Retract := TRUE;
                io_stStation.stActuators.stCyl2.stCmd.Extend := FALSE;
                io_stStation.stActuators.stCyl2.stCmd.Retract := TRUE;

                // 配置气缸超时参数
                io_stStation.stActuators.stCyl1.stCmd.TimeoutMs := t_dCylTimeout;
                io_stStation.stActuators.stCyl2.stCmd.TimeoutMs := t_dCylTimeout;

                // 等待气缸回原点
                IF io_stStation.stActuators.stCyl1.stSts.IsRetracted AND io_stStation.stActuators.stCyl2.stSts.IsRetracted THEN
                    s_iStep := STEP_WAIT_MATERIAL;
                    s_tStepTimer.IN := FALSE;
                END_IF;

            STEP_WAIT_MATERIAL:
                // 等待来料: stStatus.bWaitMaterial = 1, 由 FB_3001 向上游发准备好信号并负责交握
                
                // 等待 FB_3001 状态机推进至允许进料或收到进料请求
                // 根据 STD-820，FB_3001 的 iInfeedStep >= 30 表示允许电机动作
                IF io_stExternal.stUpstream.iInfeedStep >= 30 THEN
                    s_iStep := STEP_FEEDING;
                    s_tStepTimer.IN := FALSE;
                END_IF;

            STEP_FEEDING:
                io_stStation.stActuators.stMotorFwd.i_bFwdReq := TRUE;
                
                s_tStepTimer.IN := TRUE;
                s_tStepTimer.PT := 10000; // 进料超时 10s
                
                IF t_bWorkPos THEN
                    io_stStation.stActuators.stMotorFwd.i_bFwdReq := FALSE;
                    s_iStep := STEP_CLAMP;
                    s_tStepTimer.IN := FALSE;
                ELSIF s_tStepTimer.Q THEN
                    s_bAlarm := TRUE;
                    s_iAlarmCode := 101; // 进料超时报警
                    io_stStation.stActuators.stMotorFwd.i_bFwdReq := FALSE;
                    s_iStep := STEP_FAULT;
                END_IF;

            STEP_CLAMP:
                io_stStation.stActuators.stCyl1.stCmd.Extend := TRUE;
                io_stStation.stActuators.stCyl1.stCmd.Retract := FALSE;
                io_stStation.stActuators.stCyl2.stCmd.Extend := TRUE;
                io_stStation.stActuators.stCyl2.stCmd.Retract := FALSE;
                
                // STD-840: 等待状态输入
                IF io_stStation.stActuators.stCyl1.stSts.IsExtended AND io_stStation.stActuators.stCyl2.stSts.IsExtended THEN
                    s_iStep := STEP_PROCESS;
                    s_tStepTimer.IN := FALSE;
                ELSIF io_stStation.stActuators.stCyl1.stSts.Timeout OR io_stStation.stActuators.stCyl2.stSts.Timeout THEN
                    s_bAlarm := TRUE;
                    s_iAlarmCode := 102; // 夹紧/顶升超时报警
                    s_iStep := STEP_FAULT;
                END_IF;

            STEP_PROCESS:
                // 启动工艺加工定时器
                s_tProcessTimer.IN := TRUE;
                s_tProcessTimer.PT := t_dProcessTime;
                
                IF s_tProcessTimer.Q THEN
                    s_iStep := STEP_RELEASE_UNLOAD;
                    s_tProcessTimer.IN := FALSE;
                    s_tStepTimer.IN := FALSE;
                END_IF;

            STEP_RELEASE_UNLOAD:
                io_stStation.stActuators.stCyl1.stCmd.Extend := FALSE;
                io_stStation.stActuators.stCyl1.stCmd.Retract := TRUE;
                io_stStation.stActuators.stCyl2.stCmd.Extend := FALSE;
                io_stStation.stActuators.stCyl2.stCmd.Retract := TRUE;
                
                IF io_stStation.stActuators.stCyl1.stSts.IsRetracted AND io_stStation.stActuators.stCyl2.stSts.IsRetracted THEN
                    io_stStation.stActuators.stMotorFwd.i_bFwdReq := TRUE;
                    
                    s_tStepTimer.IN := TRUE;
                    s_tStepTimer.PT := 10000; // 出料超时 10s
                    
                    // STD-820 出料握手：stStatus.bReadyOut = 1, 由 FB_3001 向下游发准备好出料并负责交握
                    // 本站主要监测工件离开
                    
                    IF NOT t_bWorkPos AND NOT t_bInPos THEN
                        io_stStation.stActuators.stMotorFwd.i_bFwdReq := FALSE;
                        s_bDone := TRUE;
                        s_iStep := STEP_IDLE;
                        s_tStepTimer.IN := FALSE;
                    ELSIF s_tStepTimer.Q THEN
                        s_bAlarm := TRUE;
                        s_iAlarmCode := 103; // 松开/出料超时报警
                        io_stStation.stActuators.stMotorFwd.i_bFwdReq := FALSE;
                        s_iStep := STEP_FAULT;
                    END_IF;
                ELSIF io_stStation.stActuators.stCyl1.stSts.Timeout OR io_stStation.stActuators.stCyl2.stSts.Timeout THEN
                    s_bAlarm := TRUE;
                    s_iAlarmCode := 104; // 缩回超时报警
                    s_iStep := STEP_FAULT;
                END_IF;

            STEP_FAULT:
                s_bRunning := FALSE;
                s_tStepTimer.IN := FALSE;
                s_tProcessTimer.IN := FALSE;

            ELSE
                // 防死锁安全分支
                s_iStep := STEP_IDLE;
                s_tStepTimer.IN := FALSE;
                s_tProcessTimer.IN := FALSE;
        END_CASE;
    END_IF;
    // @安全区 结束

    // =========================================================================
    // 4. 统一末尾封包与回写
    // =========================================================================
    io_stStation.stStatus.iStep       := s_iStep;
    io_stStation.stStatus.bRunning     := s_bRunning;
    io_stStation.stStatus.bDone        := s_bDone;
    io_stStation.stStatus.bAlarm       := s_bAlarm;
    io_stStation.stStatus.iAlarmCode   := s_iAlarmCode;
    io_stStation.stStatus.bWaitMaterial:= (s_iStep = STEP_WAIT_MATERIAL);
    io_stStation.stStatus.bProcessing  := (s_iStep = STEP_PROCESS);
    io_stStation.stStatus.bFrozen      := (NOT t_bSafeToRun) AND (s_iStep <> STEP_IDLE) AND (s_iStep <> STEP_FAULT);
    // 动作完全停止 (FB_1030 开门条件之一): 电机无请求且不在转, 两个气缸都在端点 (CARD-DJ-2026-009-004)
    io_stStation.stStatus.bMotionStopped := (NOT io_stStation.stActuators.stMotorFwd.i_bFwdReq)
                                          AND (NOT io_stStation.stActuators.stMotorFwd.q_bRunning)
                                          AND (io_stStation.stActuators.stCyl1.stSts.IsExtended OR io_stStation.stActuators.stCyl1.stSts.IsRetracted)
                                          AND (io_stStation.stActuators.stCyl2.stSts.IsExtended OR io_stStation.stActuators.stCyl2.stSts.IsRetracted);
    // 本工位有产品: 有无产品在工位块内部判断 (用户 2026-10-21), 接 FB_3001 i_bProductPresent
    t_bProduct := t_bInPos OR t_bWorkPos;
    FOR t_iIdx := 0 TO 7 DO
        t_bProduct := t_bProduct OR io_stStation.stSensors.arrProductSens[t_iIdx];
    END_FOR;
    io_stStation.stStatus.bProductPresent := t_bProduct;
    // 加工完成、气缸已松开, 可以出料 (接 FB_3001 i_bMachineReadyOut, CARD-DJ-2026-009-003)
    io_stStation.stStatus.bReadyOut    := (s_iStep = STEP_RELEASE_UNLOAD)
                                          AND io_stStation.stActuators.stCyl1.stSts.IsRetracted
                                          AND io_stStation.stActuators.stCyl2.stSts.IsRetracted;
