    // @安全区 开始：未使能时发给对方的状态字全部清零
    IF NOT i_bEnable THEN
        // 未使能: 本机发给对方的状态字和组件 ID 全部清零 (对方看到的允许/请求信号均为 0)
        FOR s_iReg := 0 TO REG_IMAGE_LAST DO
            io_arrUpWrite[s_iReg] := 16#0000;
            io_arrDownWrite[s_iReg] := 16#0000;
        END_FOR;
        q_bComOK := FALSE;
        q_wErrorCode := ERR_NONE;
        RETURN;
    END_IF;
    // @安全区 结束

    (* 1. 链路状态与错误码 *)
    q_wErrorCode := ERR_NONE;
    IF NOT i_bUpLinkOK THEN
        q_wErrorCode := q_wErrorCode OR ERR_UP_LINK;
    END_IF;
    IF NOT i_bDownLinkOK THEN
        q_wErrorCode := q_wErrorCode OR ERR_DOWN_LINK;
    END_IF;
    q_bComOK := (q_wErrorCode = ERR_NONE);

    (* 2. 上游读解包 (链路断开时保持最后值, 由 FB_3001 心跳超时判故障) *)
    // @安全区 开始：上游状态字解包 (含心跳; 链路断开保持旧值, 靠心跳超时判断线)
    IF i_bUpLinkOK THEN
        s_wStatusIn := io_arrUpRead[REG_STATUS_IN];
        io_stExternal.stUpstream.bUpstream_LineReady := (s_wStatusIn AND MASK_B0) <> 16#0000;
        io_stExternal.stUpstream.bUpstream_SendModuleId := (s_wStatusIn AND MASK_B1) <> 16#0000;
        io_stExternal.stUpstream.bUpstream_InfeedReq := (s_wStatusIn AND MASK_B2) <> 16#0000;
        io_stExternal.stUpstream.bUpstream_InfeedArrivedAck := (s_wStatusIn AND MASK_B3) <> 16#0000;
        io_stExternal.stUpstream.bUpstream_HeartbeatFromUp := (s_wStatusIn AND MASK_B15) <> 16#0000;

        // @安全区 结束
        // 组件 ID: 每个寄存器 2 个字符, 高字节在前; 遇到 0 即结束, 内容原样保留
        s_sIdBuf := '';
        s_bIdEnd := FALSE;
        s_iChar := 0;
        FOR s_iReg := 0 TO ID_REG_COUNT - 1 DO
            s_byHi := WORD_TO_BYTE(SHR(io_arrUpRead[REG_ID_START + s_iReg], 8));
            s_byLo := WORD_TO_BYTE(io_arrUpRead[REG_ID_START + s_iReg] AND 16#00FF);
            IF NOT s_bIdEnd THEN
                IF s_byHi = 16#00 THEN
                    s_bIdEnd := TRUE;
                ELSE
                    s_sIdBuf[s_iChar] := s_byHi;
                    s_iChar := s_iChar + 1;
                END_IF;
            END_IF;
            IF NOT s_bIdEnd THEN
                IF s_byLo = 16#00 THEN
                    s_bIdEnd := TRUE;
                ELSE
                    s_sIdBuf[s_iChar] := s_byLo;
                    s_iChar := s_iChar + 1;
                END_IF;
            END_IF;
        END_FOR;
        s_sIdBuf[s_iChar] := 16#00;  // 结束符 (32 个字符满时写在第 33 字节, STRING[32] 自带)
        io_stExternal.stUpstream.sRcvModuleID := s_sIdBuf;
    END_IF;

    // @安全区 开始：下游状态字解包 (含心跳) 与本机->上下游状态字封包 (允许/请求/心跳)
    (* 3. 下游读解包 (链路断开时保持最后值) *)
    IF i_bDownLinkOK THEN
        s_wStatusIn := io_arrDownRead[REG_STATUS_IN];
        io_stExternal.stDownstream.bDownstream_LineReady := (s_wStatusIn AND MASK_B0) <> 16#0000;
        io_stExternal.stDownstream.bDownstream_RcvModuleIdAck := (s_wStatusIn AND MASK_B1) <> 16#0000;
        io_stExternal.stDownstream.bDownstream_AllowOutfeed := (s_wStatusIn AND MASK_B2) <> 16#0000;
        io_stExternal.stDownstream.bDownstream_OutfeedArrived := (s_wStatusIn AND MASK_B3) <> 16#0000;
        io_stExternal.stDownstream.bDownstream_HeartbeatFromDown := (s_wStatusIn AND MASK_B15) <> 16#0000;
    END_IF;

    (* 4. 上游写封包: 本机 -> 上游 状态字 (地址 1), 未用位填 0 *)
    s_wStatusOut := 16#0000;
    IF io_stExternal.stUpstream.bMachine_ReadyIn THEN
        s_wStatusOut := s_wStatusOut OR MASK_B0;
    END_IF;
    IF io_stExternal.stUpstream.bMachine_RcvModuleIdAck THEN
        s_wStatusOut := s_wStatusOut OR MASK_B1;
    END_IF;
    IF io_stExternal.stUpstream.bMachine_AllowInfeed THEN
        s_wStatusOut := s_wStatusOut OR MASK_B2;
    END_IF;
    IF io_stExternal.stUpstream.bMachine_InfeedArrived THEN
        s_wStatusOut := s_wStatusOut OR MASK_B3;
    END_IF;
    IF io_stExternal.stUpstream.bMachine_HeartbeatToUp THEN
        s_wStatusOut := s_wStatusOut OR MASK_B15;
    END_IF;
    io_arrUpWrite[REG_STATUS_OUT] := s_wStatusOut;

    (* 5. 下游写封包: 本机 -> 下游 状态字 (地址 1) 与组件 ID (地址 2~17) *)
    s_wStatusOut := 16#0000;
    IF io_stExternal.stDownstream.bMachine_ReadyOut THEN
        s_wStatusOut := s_wStatusOut OR MASK_B0;
    END_IF;
    IF io_stExternal.stDownstream.bMachine_SendModuleId THEN
        s_wStatusOut := s_wStatusOut OR MASK_B1;
    END_IF;
    IF io_stExternal.stDownstream.bMachine_OutfeedReq THEN
        s_wStatusOut := s_wStatusOut OR MASK_B2;
    END_IF;
    IF io_stExternal.stDownstream.bMachine_OutfeedArrivedAck THEN
        s_wStatusOut := s_wStatusOut OR MASK_B3;
    END_IF;
    IF io_stExternal.stDownstream.bMachine_HeartbeatToDown THEN
        s_wStatusOut := s_wStatusOut OR MASK_B15;
    END_IF;
    io_arrDownWrite[REG_STATUS_OUT] := s_wStatusOut;
    // @安全区 结束

    // 组件 ID 原样封包: 第 2n 个字符放高字节, 第 2n+1 个放低字节, 不足 32 个字符补 0
    s_sIdBuf := io_stExternal.stDownstream.sSendModuleID;
    s_iChar := LEN(s_sIdBuf);
    FOR s_iReg := 0 TO ID_REG_COUNT - 1 DO
        s_byHi := 16#00;
        s_byLo := 16#00;
        IF (2 * s_iReg) < s_iChar THEN
            s_byHi := s_sIdBuf[2 * s_iReg];
        END_IF;
        IF (2 * s_iReg + 1) < s_iChar THEN
            s_byLo := s_sIdBuf[2 * s_iReg + 1];
        END_IF;
        io_arrDownWrite[REG_ID_START + s_iReg] := SHL(BYTE_TO_WORD(s_byHi), 8) OR BYTE_TO_WORD(s_byLo);
    END_FOR;
