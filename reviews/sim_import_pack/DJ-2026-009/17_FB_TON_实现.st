    IF PT > 0 THEN
        s_dPtMs := PT;
    ELSE
        s_dPtMs := 0;
    END_IF;

    // 每周期无条件调用一次, IN=FALSE 时平台 TON 自身复位 Q/ET
    s_fbTon(IN := IN AND (s_dPtMs > 0), PT := DINT_TO_TIME(s_dPtMs));

    IF s_dPtMs = 0 THEN
        // 预设为 0: 与旧版和 IEC 一致, IN 一到 Q 即为 TRUE
        Q := IN;
        ET := 0;
    ELSE
        Q := s_fbTon.Q;
        ET := TIME_TO_DINT(s_fbTon.ET);
        IF ET > s_dPtMs THEN
            ET := s_dPtMs;
        END_IF;
    END_IF;
