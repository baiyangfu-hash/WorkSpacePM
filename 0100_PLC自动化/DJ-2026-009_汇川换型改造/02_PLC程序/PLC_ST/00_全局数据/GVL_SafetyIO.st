// ============================================================================
// GVL_SafetyIO.st - DJ-2026-009 安全相关 IO 与 FB_1030 入参数组 (全局变量表)
// ============================================================================
// CARD-DJ-2026-009-004 (安全区, 预做): 规范 2.2 "急停第三组触点在 GVL 直接映射,
// 程序里必须读到"; 用户 10-21 定 AM500 用 ESTOP_OK AT %IX0.0.
// 其余安全点进远程 IO (EtherNet/IP), 地址等 IO 表定稿后在 InoProShop 设备树里
// 映射到下面同名变量 ("映射到现有变量"); 没映射前初值按"不安全"取, 机器动不了.
// 安全门按最多 8 扇预留 DOOR1～DOOR8 (用户 10-22), 实际用几扇由 DOOR_COUNT 定.
// 导入 InoProShop: 新建 GVL 名为 GVL_SafetyIO, 把 VAR_GLOBAL ... END_VAR 粘进去.
// 改本文件 = 改安全区, 先仿真再签字 (规范 0.5).
// ============================================================================
VAR_GLOBAL
    // --- 安全输入 (硬接线, 规范 8.5) ---
    ESTOP_OK      AT %IX0.0 : BOOL;   // 急停按钮第三组触点 (SE1 第 3 组), 1 = 正常. 只报警定位, 停机看 SAFETY_FAULT (规范 2.2)
    SAFETY_FAULT  : BOOL := TRUE;     // 安全继电器 41-42 常闭辅助点, 1 = 安全回路故障 (规范 8.1, 唯一依据). 远程 IO, 地址待 IO 表
    RESET_BTN     : BOOL := FALSE;    // 复位按钮第二组触点 (第一组接安全继电器复位端, 规范 3.1). 远程 IO, 地址待 IO 表
    START_BTN     : BOOL := FALSE;    // 启动按钮 (规范 3.6). 远程 IO, 地址待 IO 表
    DOOR1_LOCKED  : BOOL := FALSE;    // 安全门 1 门锁进 PLC 的那组触点 (欧姆龙门锁), 1 = 门关好且已锁 (规范 4.1/4.4). 地址待 IO 表
    DOOR1_REQ_BTN : BOOL := FALSE;    // 安全门 1 申请开门按钮 (规范 4.3). 地址待 IO 表
    DOOR2_LOCKED  : BOOL := FALSE;    // 安全门 2 门锁触点. 地址待 IO 表
    DOOR2_REQ_BTN : BOOL := FALSE;    // 安全门 2 申请开门按钮. 地址待 IO 表
    DOOR3_LOCKED  : BOOL := FALSE;    // 安全门 3 门锁触点. 地址待 IO 表
    DOOR3_REQ_BTN : BOOL := FALSE;    // 安全门 3 申请开门按钮. 地址待 IO 表
    DOOR4_LOCKED  : BOOL := FALSE;    // 安全门 4 门锁触点. 地址待 IO 表
    DOOR4_REQ_BTN : BOOL := FALSE;    // 安全门 4 申请开门按钮. 地址待 IO 表
    DOOR5_LOCKED  : BOOL := FALSE;    // 安全门 5 门锁触点. 地址待 IO 表
    DOOR5_REQ_BTN : BOOL := FALSE;    // 安全门 5 申请开门按钮. 地址待 IO 表
    DOOR6_LOCKED  : BOOL := FALSE;    // 安全门 6 门锁触点. 地址待 IO 表
    DOOR6_REQ_BTN : BOOL := FALSE;    // 安全门 6 申请开门按钮. 地址待 IO 表
    DOOR7_LOCKED  : BOOL := FALSE;    // 安全门 7 门锁触点. 地址待 IO 表
    DOOR7_REQ_BTN : BOOL := FALSE;    // 安全门 7 申请开门按钮. 地址待 IO 表
    DOOR8_LOCKED  : BOOL := FALSE;    // 安全门 8 门锁触点. 地址待 IO 表
    DOOR8_REQ_BTN : BOOL := FALSE;    // 安全门 8 申请开门按钮. 地址待 IO 表
    FIELDBUS_OK   : BOOL := FALSE;    // 远程 IO (EIP) 与 SV660N 全部在线, 由设备诊断汇总后写入 (规范 8.3). 未接前恒 0, 机器动不了

    // --- 安全相关输出 ---
    DOOR1_UNLOCK   : BOOL := FALSE;   // 安全门 1 解锁线圈 (得电解锁、失电锁定). 地址待 IO 表
    DOOR1_REQ_LAMP : BOOL := FALSE;   // 安全门 1 申请按钮指示灯 (申请中 1 s 闪, 允许开门常亮). 地址待 IO 表
    DOOR2_UNLOCK   : BOOL := FALSE;   // 安全门 2 解锁线圈. 地址待 IO 表
    DOOR2_REQ_LAMP : BOOL := FALSE;   // 安全门 2 申请按钮指示灯. 地址待 IO 表
    DOOR3_UNLOCK   : BOOL := FALSE;   // 安全门 3 解锁线圈. 地址待 IO 表
    DOOR3_REQ_LAMP : BOOL := FALSE;   // 安全门 3 申请按钮指示灯. 地址待 IO 表
    DOOR4_UNLOCK   : BOOL := FALSE;   // 安全门 4 解锁线圈. 地址待 IO 表
    DOOR4_REQ_LAMP : BOOL := FALSE;   // 安全门 4 申请按钮指示灯. 地址待 IO 表
    DOOR5_UNLOCK   : BOOL := FALSE;   // 安全门 5 解锁线圈. 地址待 IO 表
    DOOR5_REQ_LAMP : BOOL := FALSE;   // 安全门 5 申请按钮指示灯. 地址待 IO 表
    DOOR6_UNLOCK   : BOOL := FALSE;   // 安全门 6 解锁线圈. 地址待 IO 表
    DOOR6_REQ_LAMP : BOOL := FALSE;   // 安全门 6 申请按钮指示灯. 地址待 IO 表
    DOOR7_UNLOCK   : BOOL := FALSE;   // 安全门 7 解锁线圈. 地址待 IO 表
    DOOR7_REQ_LAMP : BOOL := FALSE;   // 安全门 7 申请按钮指示灯. 地址待 IO 表
    DOOR8_UNLOCK   : BOOL := FALSE;   // 安全门 8 解锁线圈. 地址待 IO 表
    DOOR8_REQ_LAMP : BOOL := FALSE;   // 安全门 8 申请按钮指示灯. 地址待 IO 表

    // --- FB_1030 入参数组: 未用的位靠初值填 (急停/光栅/门 = TRUE 正常, 继电器故障/申请按钮 = FALSE) ---
    arrSafetyFault : ARRAY[0..3] OF BOOL;                 // [0] = SAFETY_FAULT, 009 只有一个安全继电器
    arrEStopOk     : ARRAY[0..7] OF BOOL := [8(TRUE)];    // [0] = ESTOP_OK, 009 现知一个急停
    arrCurtainOk   : ARRAY[0..7] OF BOOL := [8(TRUE)];    // 009 无光栅 (有的话接 [0..])
    arrDoorClosed  : ARRAY[0..7] OF BOOL := [8(TRUE)];    // [n-1] = DOORn_LOCKED (n <= DOOR_COUNT), 其余保持 TRUE
    arrDoorReqBtn  : ARRAY[0..7] OF BOOL;                 // [n-1] = DOORn_REQ_BTN (n <= DOOR_COUNT)
END_VAR

// 实际安全门数量 (用户 10-22: 最多 8 扇, 地址空出来只用变量, 后续映射).
// 默认 8 = 8 扇门都要锁好才许可运行; IO 表定稿后改成实际门数. 改小了就少查门, 属安全区改动, 须仿真+签字.
VAR_GLOBAL CONSTANT
    DOOR_COUNT : INT := 8;
END_VAR
