(* ================================================================= *)
(*  功能块名称:FB_2001_CommonAlarm_AllStation                        *)
(*  功能描述:公共报警管理功能块 - 汇总 009 全机报警给 HMI              *)
(*  版本号:V4.0.0 (CARD-DJ-2026-009 报警汇总卡预做, 2026-10-22)       *)
(*                                                                   *)
(*  只读报警源、不改任何动作: 急停/门锁/安全继电器的状态由 FB_1030     *)
(*  报来, 这里只拿来报警显示; 停机、复位、许可都不在本块.              *)
(*                                                                   *)
(*  报警源 (OB1 第 3 部分写入 io_stGlobal 的 i_ 字段):                  *)
(*    安全   FB_1030 q_dwAlarm     DWORD, 32 位                       *)
(*    握手   FB_3001 q_wErrorCode  WORD, 16 位                        *)
(*    工位 1 FB_1001 iAlarmCode    101~199                            *)
(*                                                                   *)
(*  报警码 (码越小越优先, 每个报警一个码, 不再按位"或"混码):         *)
(*    1~8    第 1~8 个急停被按下        (q_dwAlarm bit0~7)            *)
(*    9~16   第 1~8 扇门没关好/没锁     (bit8~15)                     *)
(*    17~24  第 1~8 道光栅被遮挡        (bit16~23)                    *)
(*    25~28  第 1~4 个安全继电器故障    (bit24~27)                    *)
(*    29     总线断线                   (bit28)                       *)
(*    30     复位被拒                   (bit29)                       *)
(*    31     复位过早 (不足 10 s)       (bit30)                       *)
(*    32     门锁回失败                 (bit31)                       *)
(*    41~56  握手故障字 bit0~15 (41 进料中止, 42 出料中止, 43 等人工  *)
(*           复位, 45 上游通讯, 46 下游通讯, 47 ID 不合格, 48 ID 待   *)
(*           核对; 44、49~56 现未定义, 预留)                          *)
(*    101~199 工位 1 报警码原样 (101 进料超时 ... 104 缩回超时)       *)
(*                                                                   *)
(*  新报警 = 某个码从无到有 (工位码变成另一个非 0 码也算新).          *)
(*  复位只认上升沿, 只清历史/计数/新报警标志; 还在的报警照常显示,     *)
(*  不会因复位再记一次.                                               *)
(* ================================================================= *)
FUNCTION_BLOCK FB_2001_CommonAlarm_AllStation

VAR_IN_OUT
    io_stGlobal                : ST_CommonAlarm; // 公共报警工站全量数据结构体
END_VAR

VAR
    // 局部解包变量
    s_bResetCmd                : BOOL;
    s_dwSafetyAlarm            : DWORD;
    s_wExtErrorCode            : WORD;
    s_iStationAlarm            : INT;

    // 上一扫描的值 (块末尾保存, 用于判新报警)
    s_bPrevReset               : BOOL;
    s_dwPrevSafetyAlarm        : DWORD;
    s_wPrevExtErrorCode        : WORD;
    s_iPrevStationAlarm        : INT;

    // 本扫描新出现的报警
    s_dwSafetyNew              : DWORD;
    s_wExtNew                  : WORD;
    s_bStationNew              : BOOL;

    // 输出缓存
    s_wGlobalAlarmWord         : WORD;
    s_iCurrentAlarmCode        : INT;
    s_iActiveAlarmCount        : INT;
    s_iAlarmEventCount         : INT;
    s_arrAlarmHistory          : ARRAY[0..9] OF INT;
    s_bNewAlarmFlag            : BOOL;
END_VAR

VAR_TEMP
    t_i                        : INT;   // 报警源序号: 0~31 安全位, 32~47 握手位, 48 工位
    t_j                        : INT;   // 历史队列下标
    t_bActive                  : BOOL;  // 该源当前有报警
    t_bNew                     : BOOL;  // 该源本扫描新出现
    t_iCode                    : INT;   // 该源对应的报警码
    t_bResetEdge               : BOOL;  // 复位上升沿
END_VAR

VAR CONSTANT
    HIST_LAST      : INT := 9;      // 报警历史末位下标 (共 10 条)
    SRC_LAST       : INT := 48;     // 报警源序号末位 (32 安全 + 16 握手 + 1 工位)
    SRC_EXT_FIRST  : INT := 32;     // 握手位起始序号
    SRC_STATION    : INT := 48;     // 工位报警序号
    SAFETY_BASE    : INT := 1;      // 安全位 n -> 报警码 1 + n
    EXT_BASE       : INT := 41;     // 握手位 n -> 报警码 41 + n
    COUNT_MAX      : INT := 32767;  // 计数到顶后从 1 重新计
    ALM_NONE       : INT := 0;      // 无报警值
    BIT_SAFETY     : WORD := 16#0001;  // 类别字 bit0 安全
    BIT_EXT        : WORD := 16#0002;  // 类别字 bit1 上下游通讯/握手
    BIT_STATION    : WORD := 16#0004;  // 类别字 bit2 工位 1
END_VAR
