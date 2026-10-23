FUNCTION_BLOCK FB_3001_ExternalInteraction
(* ==============================================================================
 * FB_3001_ExternalInteraction - 通用外部设备交握与心跳监视功能块
 * 项目: DJ-2026-009 汇川换型改造
 * 遵循规范: STD-820 (8步握手 + 4s ON / 4s OFF 心跳)
 * ============================================================================== *)
VAR_INPUT
    i_bEnable           : BOOL;         // 功能块总使能 (通讯与心跳; 0 = 心跳也停, 对方判断线)
    i_bSafeToRun        : BOOL;         // 运行许可 (OB1 接 FB_1030 q_bSafeToRun); 0 = 心跳照发, 只撤握手许可, CARD-DJ-2026-009-004
    i_bAutoMode         : BOOL;         // 自动运行模式
    i_bResetCmd         : BOOL;         // 故障复位指令 (OB1: FB_1030 运行复位脉冲, 或运行许可中的普通复位, CARD-DJ-2026-009-004)
    i_bMachineReadyIn   : BOOL;         // 本机进料就绪 (工位空闲)
    i_bMachineReadyOut  : BOOL;         // 本机出料就绪 (加工完成)
    i_bInfeedArrivedSens: BOOL;         // 本机进料到位光电传感器
    i_bProductPresent   : BOOL;         // 本机有产品 (产品检测传感器, CARD-DJ-2026-009-003)
END_VAR

VAR_OUTPUT
    q_bAllowInfeedAct   : BOOL;         // 触发本机进料动作输出
    q_bAllowOutfeedAct  : BOOL;         // 触发本机出料动作输出
    q_bUpstreamDone     : BOOL;         // 本次进料交握事务完成脉冲
    q_bDownstreamDone   : BOOL;         // 本次出料交握事务完成脉冲
    q_bComAlarm         : BOOL;         // 外部通讯中断综合报警
    q_wErrorCode        : WORD;         // 故障诊断字
END_VAR

VAR_IN_OUT
    io_stExternal       : ST_ExternalDevice;  // STD-820 通用外部对接数据总线
    io_sMachineModuleID : STRING[32];         // 本机 ID (组件 ID 第 2 格, 全局变量须断电保持 RETAIN)
    io_stIdHmi          : ST_ModuleIdHmi;     // 组件 ID 人工操作与时间参数 (HMI)
END_VAR

VAR
    // --- STD-820 心跳: 4s ON / 4s OFF 方波 + 12s 超时监视 (LSP-903: FB_TON + DINT 毫秒) ---
    // 半周期与超时阈值已改为 VAR CONSTANT HB_HALF_MS / HB_TIMEOUT_MS (规范 0.4/9, CARD-DJ-2026-009-004)
    s_tHbToggle         : FB_TON;          // 心跳翻转定时器
    s_tUpTimeout        : FB_TON;          // 上游心跳超时定时器
    s_tDownTimeout      : FB_TON;          // 下游心跳超时定时器

    s_bHbState          : BOOL := FALSE;   // 本机心跳电平 (每 4s 翻转一次 = 4s ON / 4s OFF 方波)
    s_bLastUpHeartbeat  : BOOL := FALSE;
    s_bLastDownHeartbeat: BOOL := FALSE;

    s_iInfeedStep       : INT  := 0;
    s_iOutfeedStep      : INT  := 0;
    s_wAbortLatch       : WORD := 16#0000; // 握手中途中止记录 (保持到复位)
    s_bInfeedLock       : BOOL := FALSE;   // 自动作业中进料被中止, 需人工复位才能重新握手
    s_bOutfeedLock      : BOOL := FALSE;   // 自动作业中出料被中止, 需人工复位才能重新握手
    s_bResetPrev        : BOOL := FALSE;   // 上一周期复位指令 (清锁只认上升沿)

    // --- 组件 ID 三格存储 (CARD-DJ-2026-009-003, 规则 R1~R6) ---
    s_sInfeedId         : STRING[32] := ''; // 进料第 10 步确认收到的上游 ID (到位时拷入本机 ID)
    s_wIdCheck          : WORD := 16#0000;  // FC_3003 检查结果 (0 = 合格)
    s_bIdRelease        : BOOL := FALSE;    // HMI 人工放行: 本次进料不检查 ID
    s_bIdCheckReq       : BOOL := FALSE;    // 握手中途中止后 ID 待人工核对 (HMI 拷入/补录/清空后清)
    s_tLeaveTimer       : FB_TON;           // 出料中检测不到产品计时 (R3 第 2 种)
    s_tIdleTimer        : FB_TON;           // 自动作业中长时间无产品计时 (R6)
END_VAR

VAR_TEMP
    t_dLeaveMs          : DINT;             // 产品离开判定时间 (ms)
    t_dIdleMs           : DINT;             // 无产品自动清本机 ID 时间 (ms)
    t_bIdWait           : BOOL;             // 进料第 20 步因 ID 不合格停住
END_VAR

VAR CONSTANT
    // --- q_wErrorCode 位定义 (CARD-DJ-2026-009-002) ---
    ERR_INFEED_ABORT    : WORD := 16#0001;  // 进料握手第 10~40 步因通讯故障中止 (保持到复位)
    ERR_OUTFEED_ABORT   : WORD := 16#0002;  // 出料握手第 10~40 步因通讯故障中止 (保持到复位)
    ERR_WAIT_RESET      : WORD := 16#0004;  // 自动作业中被中止, 等待人工复位 (复位后清)
    ERR_UP_COM          : WORD := 16#0010;  // 上游通讯故障 (实时)
    ERR_DOWN_COM        : WORD := 16#0020;  // 下游通讯故障 (实时)
    ERR_ID_EMPTY        : WORD := 16#0040;  // 进料第 20 步上游 ID 不合格 (现只判空), 等人工放行或补录 (实时)
    ERR_ID_CHECK        : WORD := 16#0080;  // 握手中途中止, ID 待人工核对 (HMI 拷入/补录/清空后清)

    // --- 组件 ID 规则参数 (CARD-DJ-2026-009-003, 用户 2026-10-20 答复) ---
    ID_CHECK_OK         : WORD := 16#0000;  // FC_3003 返回 0 = 合格
    DEF_LEAVE_MS        : DINT := 2000;     // 产品离开判定时间设定为 0 时按 2000ms
    DEF_IDLE_MS         : DINT := 20000;    // 无产品自动清本机 ID 时间设定为 0 时按 20000ms (暂定)
    STEP_ID_INVOLVED    : INT  := 20;       // 第 20 步起中止的握手, ID 已交接一半, 要人工核对

    // --- 心跳与断线判定时间 (安全区常量, HMI 不能改; 改值要签字. 规范 0.4/9, CARD-DJ-2026-009-004) ---
    HB_HALF_MS          : DINT := 4000;     // 心跳半周期 4000ms (4s ON / 4s OFF)
    HB_TIMEOUT_MS       : DINT := 12000;    // 心跳超时阈值 12000ms (12 s 内保持旧值, 超时判断线)
END_VAR
