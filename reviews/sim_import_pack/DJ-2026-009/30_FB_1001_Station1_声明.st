// ============================================================================
// FB_1001_Station1.scl - 汇川换型改造 工位1 动作机构控制功能块
// ============================================================================
// 描述:
//   实现 DJ-2026-009 汇川换型改造 工位1 进料、定位、夹紧、加工与出料控制.
//   严格遵循 LSP-905 语法白名单、DINT 毫秒定时器三段式、CASE 防死锁 ELSE 与结构体整块传递.
//   遵循 STD-840 设备抽象, STD-820 8步握手.
//   CARD-DJ-2026-009-004 (安全区, 预做): 运动只在共享库 FB_1030 给出运行许可
//   (stControl.bSafeToRun) 时进行; 许可一丢当拍电机清零、步序冻结, 两次复位 +
//   按启动后从断点接着走 (3Sun 断点续跑, 规范 2.5); 气缸按 IO 表逐阀定保持/缩回.
// ============================================================================

FUNCTION_BLOCK FB_1001_Station1

VAR_IN_OUT
    io_stStation    : ST_Station1;      // 工位1 全局交互结构体 (整块传递)
    io_stExternal   : ST_ExternalDevice;// 外部设备 8步握手交握结构体
END_VAR

VAR
    // 局部状态变量
    s_iStep         : DINT;             // 内部工步号
    s_bRunning      : BOOL;             // 运行中状态
    s_bDone         : BOOL;             // 本周期完成脉冲
    s_bAlarm        : BOOL;             // 站级报警
    s_iAlarmCode    : DINT;             // 报警代码

    // 定时器实例 (DINT 毫秒三段式, 遵循 LSP-906/903)
    s_tStepTimer    : FB_TON;           // 工步计时器 (ms)
    s_tProcessTimer : FB_TON;           // 工艺加工计时器 (ms)
END_VAR

VAR_TEMP
    t_bAutoEnable   : BOOL;
    t_bReset        : BOOL;
    t_bInPos        : BOOL;
    t_bWorkPos      : BOOL;
    t_dCylTimeout   : DINT;
    t_dProcessTime  : DINT;
    t_iIdx          : INT;              // 产品传感器数组下标
    t_bProduct      : BOOL;             // 本工位有产品
    t_bSafeToRun    : BOOL;             // FB_1030 运行许可 (CARD-DJ-2026-009-004)
END_VAR

VAR CONSTANT
    STEP_IDLE           : DINT := 0;    // 待机就绪
    STEP_WAIT_MATERIAL  : DINT := 1;    // 等待来料 (STD-820)
    STEP_FEEDING        : DINT := 2;    // 进料输送
    STEP_CLAMP          : DINT := 10;   // 夹紧顶升
    STEP_PROCESS        : DINT := 20;   // 工艺加工
    STEP_RELEASE_UNLOAD : DINT := 30;   // 松开出料
    STEP_FAULT          : DINT := 99;   // 故障保护

    // 停机 (急停/开门/断线/报警/离开自动) 时各气缸电磁阀怎么处理 (规范 2.3/8.3, CARD-DJ-2026-009-004)
    // FALSE = 保持当前命令 (中封阀/真空/怕掉料的阀); TRUE = 发缩回命令. 按 IO 表"急停/断线时输出"列逐阀定,
    // 阀型未定前一律按保持 (原来一刀切强制缩回, 第 93~96 行). 改值 = 改安全区, 要签字.
    CYL1_RETRACT_ON_STOP : BOOL := FALSE; // 夹紧气缸
    CYL2_RETRACT_ON_STOP : BOOL := FALSE; // 顶升气缸
END_VAR