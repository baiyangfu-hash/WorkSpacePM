// 对方心跳: 4 s 翻一次
fbHbTimer(IN := NOT fbHbTimer.Q, PT := 4000);
IF fbHbTimer.Q THEN
    bHb := NOT bHb;
END_IF;

// 上游 -> 本机 状态字
wStatus := 16#0000;
IF bUpLineReady THEN wStatus := wStatus OR 16#0001; END_IF;
IF bUpSendId THEN wStatus := wStatus OR 16#0002; END_IF;
IF bUpInfeedReq THEN wStatus := wStatus OR 16#0004; END_IF;
IF bUpArrivedAck THEN wStatus := wStatus OR 16#0008; END_IF;
IF bUpHbOn AND bHb THEN wStatus := wStatus OR 16#8000; END_IF;
GlobalVars.awModbusUpRead[0] := wStatus;

// 上游组件 ID: 第 2n 个字符放高字节, 第 2n+1 个放低字节, 不足补 0 (和 FB_3002 封包同一写法)
iLen := LEN(sUpId);
FOR iReg := 0 TO 15 DO
    byHi := 16#00;
    byLo := 16#00;
    IF (2 * iReg) < iLen THEN
        byHi := sUpId[2 * iReg];
    END_IF;
    IF (2 * iReg + 1) < iLen THEN
        byLo := sUpId[2 * iReg + 1];
    END_IF;
    GlobalVars.awModbusUpRead[2 + iReg] := SHL(BYTE_TO_WORD(byHi), 8) OR BYTE_TO_WORD(byLo);
END_FOR;

// 下游 -> 本机 状态字
wStatus := 16#0000;
IF bDnLineReady THEN wStatus := wStatus OR 16#0001; END_IF;
IF bDnRcvIdAck THEN wStatus := wStatus OR 16#0002; END_IF;
IF bDnAllowOutfeed THEN wStatus := wStatus OR 16#0004; END_IF;
IF bDnOutfeedArrived THEN wStatus := wStatus OR 16#0008; END_IF;
IF bDownHbOn AND bHb THEN wStatus := wStatus OR 16#8000; END_IF;
GlobalVars.awModbusDownRead[0] := wStatus;

// 下游读回本机发出的组件 ID (和 FB_3002 解包同一写法, 遇 0 结束)
sDnReadBack := '';
bEnd := FALSE;
iChar := 0;
FOR iReg := 0 TO 15 DO
    byHi := WORD_TO_BYTE(SHR(GlobalVars.awModbusDownWrite[2 + iReg], 8));
    byLo := WORD_TO_BYTE(GlobalVars.awModbusDownWrite[2 + iReg] AND 16#00FF);
    IF NOT bEnd THEN
        IF byHi = 16#00 THEN
            bEnd := TRUE;
        ELSE
            sDnReadBack[iChar] := byHi;
            iChar := iChar + 1;
        END_IF;
    END_IF;
    IF NOT bEnd THEN
        IF byLo = 16#00 THEN
            bEnd := TRUE;
        ELSE
            sDnReadBack[iChar] := byLo;
            iChar := iChar + 1;
        END_IF;
    END_IF;
END_FOR;
sDnReadBack[iChar] := 16#00;
