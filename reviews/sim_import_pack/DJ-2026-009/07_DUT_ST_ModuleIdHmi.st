TYPE ST_ModuleIdHmi :
STRUCT
    // --- 组件 ID 人工操作 (CARD-DJ-2026-009-003): HMI 置 1, PLC 处理后清 0; 权限由 HMI 权限动画处理 ---
    bCmdCopyFromUp  : BOOL;         // 拷入: 上游 ID -> 本机 ID (R4)
    bCmdManualEntry : BOOL;         // 补录: sManualId -> 本机 ID (R5)
    bCmdRelease     : BOOL;         // 放行: 上游 ID 不合格时人工允许本次进料 (R5)
    bCmdClear       : BOOL;         // 清空本机 ID (R6)
    sManualId       : STRING[32];   // 人工补录的组件 ID

    // --- 参数 (HMI 可改, 全局变量须断电保持) ---
    dLeaveTimeMs    : DINT;         // 出料中检测不到产品判产品离开的时间 ms (0 = 按 2000)
    dIdleClearMs    : DINT;         // 自动作业中无产品自动清本机 ID 的时间 ms (0 = 按 20000, 暂定)
END_STRUCT
END_TYPE
