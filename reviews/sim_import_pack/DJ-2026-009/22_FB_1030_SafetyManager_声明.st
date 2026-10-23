(* ================================================================= *)
(*  FB_1030_SafetyManager                                             *)
(*  全机安全管理块: 安全回路状态 + 两次复位 + 启动许可 + 门锁开门流程   *)
(*  版本: V1.0.0  日期: 2026-10-22                                    *)
(*  来源: SysLib/safety/                                              *)
(*  依据: 电气自动化安全规范 V1.0 第 0/2/3/4/5/8/9/12 节               *)
(*        安全FB设计草案_20261022 (用户 10-22 定: 合成一块)            *)
(*  依赖: FB_TON V3.0.0 (真实毫秒), FB_R_TRIG                          *)
(*                                                                    *)
(*  它管什么:                                                         *)
(*    - 只读安全器件报给 PLC 的状态点, 算出"能不能动""复位采不采纳"    *)
(*      "能不能开门", 交给各工位块使用. 全机只调用一次.                *)
(*  它不管什么:                                                       *)
(*    - 不控制安全回路 (回路靠安全继电器硬件切断, 规范 0.1)            *)
(*    - 不决定电磁阀急停后清零还是保持 (工位块按 IO 表, 规范 2.3)       *)
(*    - 不决定断点续跑还是重新初始化 (工位块按项目需求, 规范 2.5)       *)
(*    - 不做光栅屏蔽 (规范 5.3), 不做按钮卡住判断 (规范 3.5)           *)
(*                                                                    *)
(*  状态 q_iState:                                                    *)
(*    0 安全回路断开   1 等满 10 s   2 等运行复位   3 等启动   4 运行许可 *)
(*                                                                    *)
(*  两次复位 (规范 3.1~3.6, 10 s 从第一次按复位起算, 用户 10-21 定):  *)
(*    第一次: 安全继电器自行复位, PLC 只记时刻 (门锁好、总线在线才记)  *)
(*    第二次: 继电器反馈正常 且 距第一次 >= 10 s 才采纳 -> 运行复位脉冲 *)
(*    之后按启动 -> 启动脉冲 + 运行许可. 复位/启动都只认上升沿.         *)
(*                                                                    *)
(*  报警字 q_dwAlarm:                                                 *)
(*    bit0~7   第 1~8 个急停被按下 (实时)                              *)
(*    bit8~15  第 1~8 扇门没关好/没锁 (实时)                           *)
(*    bit16~23 第 1~8 道光栅被遮挡 (实时)                              *)
(*    bit24~27 第 1~4 个安全继电器反馈 = 故障 (实时)                    *)
(*    bit28    总线断线 (实时)                                         *)
(*    bit29    复位被拒: 安全回路未恢复/门没锁/总线断 (保持到下次采纳)  *)
(*    bit30    复位过早: 距第一次不足 10 s (保持到下次采纳)             *)
(*    bit31    门锁回失败: 撤销解锁后 1 s 内门锁点没回来 (保持到锁好)   *)
(*                                                                    *)
(*  安全区: 改本块等于改安全区, 先仿真再由用户签字 (规范 0.5)         *)
(* ================================================================= *)

FUNCTION_BLOCK FB_1030_SafetyManager

VAR_INPUT
    i_arrSafetyFault : ARRAY[0..3] OF BOOL;  // 安全继电器 41-42 常闭辅助点, 1 = 安全回路故障; 未用的填 FALSE (规范 8.1, 判断的唯一依据)
    i_arrEStopOk     : ARRAY[0..7] OF BOOL;  // 急停按钮第三组触点, 1 = 正常; 未用的填 TRUE (规范 2.2, 只报警定位)
    i_arrCurtainOk   : ARRAY[0..7] OF BOOL;  // 光栅进 PLC 的状态点, 1 = 未遮挡; 未用的填 TRUE (规范 5.1, 只报警定位)
    i_arrDoorClosed  : ARRAY[0..7] OF BOOL;  // 门锁进 PLC 的那组触点, 1 = 门关好且已锁; 未用的填 TRUE (规范 4.1, 4.4)
    i_bFieldbusOk    : BOOL;                 // 远程 IO/总线伺服全部在线 (项目汇总后接入, 规范 8.3)
    i_bResetBtn      : BOOL;                 // 复位按钮进 PLC 的那组触点 (规范 3.1)
    i_bStartBtn      : BOOL;                 // 启动按钮 (规范 3.6)
    i_bAutoMode      : BOOL;                 // 设备在自动 (全机一个, 自动时申请开门不响应)
    i_bMotionStopped : BOOL;                 // 伺服零速 + 所有动作完全停止 (全机一个, 项目汇总后接入)
    i_arrDoorReqBtn  : ARRAY[0..7] OF BOOL;  // 每扇门的申请开门按钮; 未用的填 FALSE
END_VAR

VAR_OUTPUT
    q_bSafeToRun     : BOOL;                 // 1 = 可以动; 各工位块的运动输出都要和它"与" (规范 0.1)
    q_bStopNow       : BOOL;                 // 1 = 安全条件现在丢了 (继电器故障/门没锁/总线断), 同一扫描生效 (规范 2.3)
    q_bRunResetPulse : BOOL;                 // 第二次复位被采纳时出一个扫描的脉冲, 清工位故障和握手锁 (规范 3.4)
    q_bStartPulse    : BOOL;                 // 复位以后按启动, 出一个扫描的脉冲 (规范 3.6)
    q_iState         : INT;                  // 状态号 0~4, HMI 显示"现在卡在哪一步"
    q_dwAlarm        : DWORD;                // 报警字, 位定义见文件头
    q_arrDoorUnlock  : ARRAY[0..7] OF BOOL;  // 每扇门的解锁线圈 (得电解锁、失电锁定)
    q_arrDoorLamp    : ARRAY[0..7] OF BOOL;  // 每扇门申请按钮指示灯 (申请中 1 s 周期闪, 允许开门常亮)
END_VAR

VAR
    s_iState         : INT := 0;             // 复位状态机 (上电从 0 开始, 必须人工复位 + 启动)
    s_arrDoorStep    : ARRAY[0..7] OF INT;   // 开门流程 0 锁住 1 申请中 2 允许开门 3 锁回确认
    s_bRejectLatch   : BOOL := FALSE;        // bit29 复位被拒 (保持)
    s_bEarlyLatch    : BOOL := FALSE;        // bit30 复位过早 (保持)
    s_bRelockFail    : BOOL := FALSE;        // bit31 门锁回失败 (保持到所有门锁好)
    s_bDelayRestart  : BOOL := FALSE;        // 本扫描重新开始 10 s 计时 (定时器 IN 断开一拍)
    s_bBlink         : BOOL := FALSE;        // 申请中指示灯闪烁电平

    // ===== 定时器 (先设 IN/PT, 末尾集中调用; FB_TON 真实毫秒) =====
    s_tResetDelay    : FB_TON;               // 第一次复位起的 10 s
    s_tBlink         : FB_TON;               // 闪烁半周期
    s_arrRelockTimer : ARRAY[0..7] OF FB_TON; // 撤销解锁后等门锁点回来

    // ===== 边沿检测 (只认上升沿, 规范 3.1) =====
    s_rtReset        : FB_R_TRIG;
    s_rtStart        : FB_R_TRIG;
    s_arrRtDoorReq   : ARRAY[0..7] OF FB_R_TRIG;
END_VAR

VAR_TEMP
    t_iIdx           : INT;
    t_bFault         : BOOL;                 // 任一安全继电器反馈 = 故障
    t_bDoorsOk       : BOOL;                 // 所有门关好且已锁
    t_bResetEdge     : BOOL;
    t_bStartEdge     : BOOL;
    t_bDelayDone     : BOOL;                 // 距第一次复位已满 10 s (上一扫描定时器结果)
    t_dwBit          : DWORD;
    t_dwAlarm        : DWORD;
END_VAR

VAR CONSTANT
    RESET_DELAY_MS   : DINT := 10000;        // 两次复位最小间隔 10 s (规范 3.4/9, 固定, HMI 不能改)
    BLINK_HALF_MS    : DINT := 500;          // 申请中指示灯 1 s 周期闪烁的半周期 (规范 4.3/9)
    RELOCK_CHECK_MS  : DINT := 1000;         // 撤销解锁后门锁点须在 1 s 内回来, 否则重新解锁 (门开着按复位不采纳)
    ST_OPEN          : INT := 0;             // 安全回路断开
    ST_WAIT_DELAY    : INT := 1;             // 等满 10 s
    ST_WAIT_RESET    : INT := 2;             // 等运行复位
    ST_WAIT_START    : INT := 3;             // 等启动
    ST_RUN           : INT := 4;             // 运行许可
    DOOR_LOCKED      : INT := 0;
    DOOR_REQUEST     : INT := 1;
    DOOR_UNLOCKED    : INT := 2;
    DOOR_RELOCK      : INT := 3;
END_VAR
