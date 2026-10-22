TYPE ST_CommonAlarm :
STRUCT
    // === 输入变量 (OB1 第 3 部分每扫描写入, 本块只读不改报警源) ===
    i_bReset                    : BOOL := FALSE;   // 系统复位 (HMI); 报警汇总只认上升沿: 清报警历史、计数和新报警标志
    i_dwSafetyAlarm             : DWORD := 16#0;   // 安全报警字, 接 FB_1030 q_dwAlarm (只读, 位定义见 FB_1030 文件头)
    i_wExtErrorCode             : WORD := 16#0;    // 上下游握手故障字, 接 FB_3001 q_wErrorCode (位定义见 FB_3001 常量区)
    i_iStationAlarm             : DINT := 0;       // 工位 1 报警码, 接 stStation1.stStatus.iAlarmCode (101~199, 0 = 无)

    // === 输出变量 (HMI 读; 009 不接 MES) ===
    o_wGlobalAlarmWord          : WORD := 16#0;    // 报警类别字: bit0 安全, bit1 上下游通讯/握手, bit2 工位 1
    o_iCurrentAlarmCode         : INT := 0;        // 当前最高优先级报警码 (码越小越优先, 0 = 无报警, 码表见 FB_2001 文件头)
    o_bAnyAlarmActive           : BOOL := FALSE;   // 任意报警激活
    o_iActiveAlarmCount         : INT := 0;        // 当前同时存在的报警条数
    o_iAlarmEventCount          : INT := 0;        // 新报警累计次数 (复位清零, 到 32767 后从 1 重新计)
    o_arrAlarmHistory           : ARRAY[0..9] OF INT;  // 最近 10 条新报警码, [0] 最新, 空位为 0
    o_bNewAlarmFlag             : BOOL := FALSE;   // 有未确认的新报警 (出现新报警置 1, 按复位清, 可接蜂鸣器)
    o_bSafetyAlarmActive        : BOOL := FALSE;   // 安全类报警激活 (急停/门/继电器/总线/复位被拒等)
    o_bExtAlarmActive           : BOOL := FALSE;   // 上下游通讯/握手类报警激活
    o_bStationAlarmActive       : BOOL := FALSE;   // 工位 1 报警激活
END_STRUCT;
END_TYPE
