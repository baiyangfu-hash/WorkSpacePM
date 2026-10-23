    IF PT > 0 THEN
        s_dPtMs := PT;
    ELSE
        s_dPtMs := 0;
    END_IF;

    IF R THEN
        // R 优先: 清零累计, 停掉当前段
        s_fbSeg(IN := FALSE, PT := DINT_TO_TIME(s_dPtMs));
        s_bSegRun := FALSE;
        s_dAccMs := 0;
        s_dSegMs := 0;
        s_dTotalMs := 0;
        Q := FALSE;
        ET := 0;
    ELSE
        // 1. 正在计时的一段先刷新到当前时刻 (含 IN 刚断开的这一拍, 不丢最后一段)
        s_dSegMs := 0;
        IF s_bSegRun THEN
            s_fbSeg(IN := TRUE, PT := DINT_TO_TIME(s_dPtMs));
            s_dSegMs := TIME_TO_DINT(s_fbSeg.ET);
        END_IF;

        s_dTotalMs := s_dAccMs + s_dSegMs;
        IF s_dTotalMs >= s_dPtMs THEN
            s_dTotalMs := s_dPtMs;
            // PT>0 时只有计过时才会走到这里; PT=0 时要求 IN 为 TRUE
            IF IN OR s_bSegRun THEN
                Q := TRUE;
            END_IF;
        END_IF;

        // 2. 决定这一段: IN 接通且未到达则开始/继续, 否则结束并把时间记进累计
        IF IN AND NOT Q THEN
            IF NOT s_bSegRun THEN
                s_fbSeg(IN := TRUE, PT := DINT_TO_TIME(s_dPtMs));
                s_bSegRun := TRUE;
            END_IF;
        ELSIF s_bSegRun THEN
            s_dAccMs := s_dTotalMs;
            s_fbSeg(IN := FALSE, PT := DINT_TO_TIME(s_dPtMs));
            s_bSegRun := FALSE;
        END_IF;

        ET := s_dTotalMs;
    END_IF;
