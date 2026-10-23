(* ==================== 结构体解包 (输入映射) ==================== *)
s_bResetCmd     := io_stGlobal.i_bReset;
s_dwSafetyAlarm := io_stGlobal.i_dwSafetyAlarm;
s_wExtErrorCode := io_stGlobal.i_wExtErrorCode;
s_iStationAlarm := DINT_TO_INT(io_stGlobal.i_iStationAlarm);

(* -------------------------------------------------------------------------- *)
(* 1. 复位 (只认上升沿; 不 RETURN, 本扫描照常算现状并封包)                     *)
(*    只清历史、计数、新报警标志. 上一扫描值不清, 还在的报警不会再记一次.      *)
(* -------------------------------------------------------------------------- *)
t_bResetEdge := s_bResetCmd AND NOT s_bPrevReset;
IF t_bResetEdge THEN
    FOR t_j := 0 TO HIST_LAST DO
        s_arrAlarmHistory[t_j] := ALM_NONE;
    END_FOR;
    s_iAlarmEventCount := ALM_NONE;
    s_bNewAlarmFlag := FALSE;
END_IF;

(* -------------------------------------------------------------------------- *)
(* 2. 新报警 = 本扫描有、上一扫描没有 (上一扫描值在块末尾才更新)              *)
(* -------------------------------------------------------------------------- *)
s_dwSafetyNew := s_dwSafetyAlarm AND NOT s_dwPrevSafetyAlarm;
s_wExtNew := s_wExtErrorCode AND NOT s_wPrevExtErrorCode;
s_bStationNew := (s_iStationAlarm <> ALM_NONE) AND (s_iStationAlarm <> s_iPrevStationAlarm);

(* -------------------------------------------------------------------------- *)
(* 3. 逐个报警源: 当前最高优先级码、同时报警条数、新报警进历史                 *)
(*    从优先级最低的源往高处扫: 最后写进的就是码最小的;                         *)
(*    同一扫描出现多条新报警时, 码最小的排在历史 [0]                            *)
(* -------------------------------------------------------------------------- *)
s_iCurrentAlarmCode := ALM_NONE;
s_iActiveAlarmCount := 0;

FOR t_i := SRC_LAST TO 0 BY -1 DO
    IF t_i < SRC_EXT_FIRST THEN
        t_bActive := (s_dwSafetyAlarm AND SHL(DWORD#1, t_i)) <> 0;
        t_bNew := (s_dwSafetyNew AND SHL(DWORD#1, t_i)) <> 0;
        t_iCode := SAFETY_BASE + t_i;
    ELSIF t_i < SRC_STATION THEN
        t_bActive := (s_wExtErrorCode AND SHL(WORD#1, t_i - SRC_EXT_FIRST)) <> 0;
        t_bNew := (s_wExtNew AND SHL(WORD#1, t_i - SRC_EXT_FIRST)) <> 0;
        t_iCode := EXT_BASE + t_i - SRC_EXT_FIRST;
    ELSE
        t_bActive := s_iStationAlarm <> ALM_NONE;
        t_bNew := s_bStationNew;
        t_iCode := s_iStationAlarm;
    END_IF;

    IF t_bActive THEN
        s_iCurrentAlarmCode := t_iCode;
        s_iActiveAlarmCount := s_iActiveAlarmCount + 1;
    END_IF;

    IF t_bNew THEN
        FOR t_j := HIST_LAST TO 1 BY -1 DO
            s_arrAlarmHistory[t_j] := s_arrAlarmHistory[t_j - 1];
        END_FOR;
        s_arrAlarmHistory[0] := t_iCode;
        IF s_iAlarmEventCount >= COUNT_MAX THEN
            s_iAlarmEventCount := ALM_NONE;
        END_IF;
        s_iAlarmEventCount := s_iAlarmEventCount + 1;
        s_bNewAlarmFlag := TRUE;
    END_IF;
END_FOR;

(* -------------------------------------------------------------------------- *)
(* 4. 报警类别字 (按类别置位, 不按码"或", 可反查是哪一类)                      *)
(* -------------------------------------------------------------------------- *)
s_wGlobalAlarmWord := 16#0000;
IF s_dwSafetyAlarm <> 0 THEN
    s_wGlobalAlarmWord := s_wGlobalAlarmWord OR BIT_SAFETY;
END_IF;
IF s_wExtErrorCode <> 0 THEN
    s_wGlobalAlarmWord := s_wGlobalAlarmWord OR BIT_EXT;
END_IF;
IF s_iStationAlarm <> ALM_NONE THEN
    s_wGlobalAlarmWord := s_wGlobalAlarmWord OR BIT_STATION;
END_IF;

(* -------------------------------------------------------------------------- *)
(* 5. 保存本扫描值, 下一扫描判新报警用 (必须在判断之后)                         *)
(* -------------------------------------------------------------------------- *)
s_bPrevReset := s_bResetCmd;
s_dwPrevSafetyAlarm := s_dwSafetyAlarm;
s_wPrevExtErrorCode := s_wExtErrorCode;
s_iPrevStationAlarm := s_iStationAlarm;

(* ==================== 结构体封包 (输出映射, 每扫描都写) ==================== *)
io_stGlobal.o_wGlobalAlarmWord    := s_wGlobalAlarmWord;
io_stGlobal.o_iCurrentAlarmCode   := s_iCurrentAlarmCode;
io_stGlobal.o_bAnyAlarmActive     := s_iActiveAlarmCount > 0;
io_stGlobal.o_iActiveAlarmCount   := s_iActiveAlarmCount;
io_stGlobal.o_iAlarmEventCount    := s_iAlarmEventCount;
io_stGlobal.o_arrAlarmHistory     := s_arrAlarmHistory;
io_stGlobal.o_bNewAlarmFlag       := s_bNewAlarmFlag;
io_stGlobal.o_bSafetyAlarmActive  := s_dwSafetyAlarm <> 0;
io_stGlobal.o_bExtAlarmActive     := s_wExtErrorCode <> 0;
io_stGlobal.o_bStationAlarmActive := s_iStationAlarm <> ALM_NONE;
