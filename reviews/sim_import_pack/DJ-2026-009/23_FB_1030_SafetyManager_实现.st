    (* ================================================================== *)
    (*  1. 读输入: 边沿、汇总                                              *)
    (* ================================================================== *)
    s_rtReset(IN := i_bResetBtn);
    t_bResetEdge := s_rtReset.Q;
    s_rtStart(IN := i_bStartBtn);
    t_bStartEdge := s_rtStart.Q;
    t_bDelayDone := s_tResetDelay.Q;

    t_bFault := FALSE;
    FOR t_iIdx := 0 TO 3 DO
        t_bFault := t_bFault OR i_arrSafetyFault[t_iIdx];
    END_FOR;
    t_bDoorsOk := TRUE;
    FOR t_iIdx := 0 TO 7 DO
        t_bDoorsOk := t_bDoorsOk AND i_arrDoorClosed[t_iIdx];
    END_FOR;

    q_bRunResetPulse := FALSE;
    q_bStartPulse := FALSE;
    s_bDelayRestart := FALSE;

    (* ================================================================== *)
    (*  2. 任何状态: 继电器故障/门没锁/总线断 -> 当拍回状态 0             *)
    (*     状态 1 在等继电器自己复位, 继电器故障是预期的, 只看门和总线      *)
    (* ================================================================== *)
    IF s_iState >= ST_WAIT_RESET THEN
        IF t_bFault OR NOT t_bDoorsOk OR NOT i_bFieldbusOk THEN
            s_iState := ST_OPEN;
        END_IF;
    ELSIF s_iState = ST_WAIT_DELAY THEN
        IF NOT t_bDoorsOk OR NOT i_bFieldbusOk THEN
            s_iState := ST_OPEN;
        END_IF;
    END_IF;

    (* ================================================================== *)
    (*  3. 两次复位状态机 (规范第 3 节)                                     *)
    (* ================================================================== *)
    CASE s_iState OF
        ST_OPEN:
            // 第一次复位: 只记时刻, 不清任何东西. 门没锁或总线断时继电器也复位不了, 不记, 报复位被拒
            IF t_bResetEdge THEN
                IF t_bDoorsOk AND i_bFieldbusOk THEN
                    s_bRejectLatch := FALSE;
                    s_bEarlyLatch := FALSE;
                    s_bDelayRestart := TRUE;
                    s_iState := ST_WAIT_DELAY;
                ELSE
                    s_bRejectLatch := TRUE;
                END_IF;
            END_IF;

        ST_WAIT_DELAY:
            IF t_bDelayDone AND NOT t_bFault THEN
                // 满 10 s 且反馈正常: 可以按第二次了
                s_iState := ST_WAIT_RESET;
            ELSIF t_bResetEdge THEN
                IF t_bDelayDone THEN
                    // 10 s 到了反馈仍不正常, 这一下当作新的第一次, 重新计 10 s
                    s_bRejectLatch := FALSE;
                    s_bEarlyLatch := FALSE;
                    s_bDelayRestart := TRUE;
                ELSIF t_bFault THEN
                    s_bRejectLatch := TRUE;   // 安全回路未恢复, 不采纳
                ELSE
                    s_bEarlyLatch := TRUE;    // 不足 10 s, 不采纳
                END_IF;
            ELSIF t_bDelayDone AND t_bFault THEN
                s_bRejectLatch := TRUE;       // 10 s 到了安全回路仍未恢复, 等重新按第一次
            END_IF;

        ST_WAIT_RESET:
            // 第二次复位: 反馈正常、门锁好、总线在线已由第 2 段保证
            IF t_bResetEdge THEN
                q_bRunResetPulse := TRUE;
                s_bRejectLatch := FALSE;
                s_bEarlyLatch := FALSE;
                s_iState := ST_WAIT_START;
            END_IF;

        ST_WAIT_START:
            IF t_bStartEdge THEN
                q_bStartPulse := TRUE;
                s_iState := ST_RUN;
            ELSIF t_bResetEdge THEN
                // 已复位还没启动时按复位: 只清报警, 不出脉冲
                s_bRejectLatch := FALSE;
                s_bEarlyLatch := FALSE;
            END_IF;

        ST_RUN:
            // 运行许可: 只有第 2 段 (安全条件丢失) 能让它离开
            s_bDelayRestart := FALSE;

        ELSE
            s_iState := ST_OPEN;
    END_CASE;

    (* ================================================================== *)
    (*  4. 开门流程 (规范 4.3): 每扇门一套, 下标 0~7 = 第 1~8 扇门         *)
    (* ================================================================== *)
    FOR t_iIdx := 0 TO 7 DO
        s_arrRtDoorReq[t_iIdx](IN := i_arrDoorReqBtn[t_iIdx]);

        CASE s_arrDoorStep[t_iIdx] OF
            DOOR_LOCKED:
                // 自动时按申请不响应
                IF s_arrRtDoorReq[t_iIdx].Q AND NOT i_bAutoMode THEN
                    s_arrDoorStep[t_iIdx] := DOOR_REQUEST;
                END_IF;

            DOOR_REQUEST:
                IF i_bAutoMode THEN
                    s_arrDoorStep[t_iIdx] := DOOR_LOCKED;      // 申请中切回自动, 取消申请
                ELSIF i_bMotionStopped THEN
                    s_arrDoorStep[t_iIdx] := DOOR_UNLOCKED;    // 伺服停、动作全停, 允许开门
                END_IF;

            DOOR_UNLOCKED:
                // 关门后按复位: 撤销解锁, 去确认门锁点回来
                IF t_bResetEdge THEN
                    s_arrDoorStep[t_iIdx] := DOOR_RELOCK;
                END_IF;

            DOOR_RELOCK:
                IF i_arrDoorClosed[t_iIdx] THEN
                    s_arrDoorStep[t_iIdx] := DOOR_LOCKED;
                ELSIF s_arrRelockTimer[t_iIdx].Q THEN
                    // 1 s 内门锁点没回来 = 门还开着, 这次复位不采纳, 恢复解锁 (人可能还在里面)
                    s_bRelockFail := TRUE;
                    s_arrDoorStep[t_iIdx] := DOOR_UNLOCKED;
                END_IF;

            ELSE
                s_arrDoorStep[t_iIdx] := DOOR_LOCKED;
        END_CASE;

        s_arrRelockTimer[t_iIdx].IN := (s_arrDoorStep[t_iIdx] = DOOR_RELOCK);
        s_arrRelockTimer[t_iIdx].PT := RELOCK_CHECK_MS;
    END_FOR;
    IF t_bDoorsOk THEN
        s_bRelockFail := FALSE;
    END_IF;

    // 申请中指示灯 1 s 周期闪烁: 半周期定时器自复位, 到时翻转
    s_tBlink.IN := NOT s_tBlink.Q;
    s_tBlink.PT := BLINK_HALF_MS;
    IF s_tBlink.Q THEN
        s_bBlink := NOT s_bBlink;
    END_IF;

    FOR t_iIdx := 0 TO 7 DO
        q_arrDoorUnlock[t_iIdx] := (s_arrDoorStep[t_iIdx] = DOOR_UNLOCKED);
        q_arrDoorLamp[t_iIdx] := (s_arrDoorStep[t_iIdx] = DOOR_UNLOCKED)
                                 OR ((s_arrDoorStep[t_iIdx] = DOOR_REQUEST) AND s_bBlink);
    END_FOR;

    (* ================================================================== *)
    (*  5. 定时器集中调用                                                  *)
    (* ================================================================== *)
    s_tResetDelay.IN := (s_iState = ST_WAIT_DELAY) AND NOT s_bDelayRestart;
    s_tResetDelay.PT := RESET_DELAY_MS;
    s_tResetDelay(IN := s_tResetDelay.IN, PT := s_tResetDelay.PT);
    s_tBlink(IN := s_tBlink.IN, PT := s_tBlink.PT);
    FOR t_iIdx := 0 TO 7 DO
        s_arrRelockTimer[t_iIdx](IN := s_arrRelockTimer[t_iIdx].IN, PT := s_arrRelockTimer[t_iIdx].PT);
    END_FOR;

    (* ================================================================== *)
    (*  6. 输出                                                            *)
    (* ================================================================== *)
    q_iState := s_iState;
    q_bSafeToRun := (s_iState = ST_RUN);
    q_bStopNow := t_bFault OR NOT t_bDoorsOk OR NOT i_bFieldbusOk;

    t_dwAlarm := 16#00000000;
    t_dwBit := 16#00000001;
    FOR t_iIdx := 0 TO 7 DO
        IF NOT i_arrEStopOk[t_iIdx] THEN
            t_dwAlarm := t_dwAlarm OR SHL(t_dwBit, t_iIdx);
        END_IF;
        IF NOT i_arrDoorClosed[t_iIdx] THEN
            t_dwAlarm := t_dwAlarm OR SHL(t_dwBit, t_iIdx + 8);
        END_IF;
        IF NOT i_arrCurtainOk[t_iIdx] THEN
            t_dwAlarm := t_dwAlarm OR SHL(t_dwBit, t_iIdx + 16);
        END_IF;
    END_FOR;
    FOR t_iIdx := 0 TO 3 DO
        IF i_arrSafetyFault[t_iIdx] THEN
            t_dwAlarm := t_dwAlarm OR SHL(t_dwBit, t_iIdx + 24);
        END_IF;
    END_FOR;
    IF NOT i_bFieldbusOk THEN
        t_dwAlarm := t_dwAlarm OR SHL(t_dwBit, 28);
    END_IF;
    IF s_bRejectLatch THEN
        t_dwAlarm := t_dwAlarm OR SHL(t_dwBit, 29);
    END_IF;
    IF s_bEarlyLatch THEN
        t_dwAlarm := t_dwAlarm OR SHL(t_dwBit, 30);
    END_IF;
    IF s_bRelockFail THEN
        t_dwAlarm := t_dwAlarm OR SHL(t_dwBit, 31);
    END_IF;
    q_dwAlarm := t_dwAlarm;
