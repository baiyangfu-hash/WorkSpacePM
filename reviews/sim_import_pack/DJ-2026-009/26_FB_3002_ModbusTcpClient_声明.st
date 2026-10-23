FUNCTION_BLOCK FB_3002_ModbusTcpClient
(* ==============================================================================
 * FB_3002_ModbusTcpClient - 上下游 Modbus TCP 客户端数据映射层
 * 项目: DJ-2026-009 汇川换型改造
 * 依据: BC-DJ-2026-009-004, 通讯契约 V0.3 (030_DJ-2026-009_通讯契约_INT.md) 2.0~2.2
 * 实施卡: CARD-DJ-2026-009-001
 *
 * 职责:
 *   本机做 Modbus TCP 客户端. 报文收发由 InoProShop 的 Modbus TCP 主站通道完成,
 *   通道把对方保持寄存器映射到 4 个寄存器镜像数组 (下标 = 协议地址, 从 0 起).
 *   本块只做两件事:
 *     1. 把读回的镜像解包到 ST_UpstreamDocking / ST_DownstreamDocking (对方 -> 本机);
 *        把本机信号封包到写镜像 (本机 -> 对方).
 *     2. 根据通道链路状态给出通讯状态位和错误码.
 *   链路断开时读侧变量保持最后值不刷新, 心跳因此停止翻转,
 *   由 FB_3001 现有的 12s 心跳超时照常报通讯故障. 本块不直接改握手状态.
 *
 * 寄存器地址取自契约 V0.3 我方提议版, 未经对方签字, 见下方 VAR CONSTANT.
 * ============================================================================== *)
VAR_INPUT
    i_bEnable           : BOOL;         // 功能块总使能
    i_bUpLinkOK         : BOOL;         // 上游 Modbus TCP 通道链路正常 (来自主站通道诊断)
    i_bDownLinkOK       : BOOL;         // 下游 Modbus TCP 通道链路正常 (来自主站通道诊断)
END_VAR

VAR_OUTPUT
    q_bComOK            : BOOL;         // 上下游通道链路均正常
    q_wErrorCode        : WORD;         // 通讯层故障诊断字 (bit0 上游链路断, bit1 下游链路断)
END_VAR

VAR_IN_OUT
    io_stExternal       : ST_ExternalDevice;        // STD-820 通用外部对接数据总线
    io_arrUpRead        : ARRAY[0..31] OF WORD;     // 上游寄存器读镜像 (下标 = 协议地址)
    io_arrUpWrite       : ARRAY[0..31] OF WORD;     // 上游寄存器写镜像 (下标 = 协议地址)
    io_arrDownRead      : ARRAY[0..31] OF WORD;     // 下游寄存器读镜像 (下标 = 协议地址)
    io_arrDownWrite     : ARRAY[0..31] OF WORD;     // 下游寄存器写镜像 (下标 = 协议地址)
END_VAR

VAR
    s_wStatusIn         : WORD;         // 解包用: 对方状态字
    s_wStatusOut        : WORD;         // 封包用: 本机状态字
    s_iReg              : INT;          // 组件 ID 寄存器循环下标 (0~15)
    s_iChar             : INT;          // 组件 ID 字符下标 (0~31)
    s_bIdEnd            : BOOL;         // 解包组件 ID 时已遇到结束符 0
    s_byHi              : BYTE;         // 寄存器高字节 (前一个字符)
    s_byLo              : BYTE;         // 寄存器低字节 (后一个字符)
    s_sIdBuf            : STRING[32];   // 组件 ID 解包缓冲
END_VAR

VAR CONSTANT
    // --- 寄存器地址 (契约 V0.3 2.0, 我方提议, 待对方签字) ---
    REG_STATUS_IN       : INT := 0;     // 对方 -> 本机 状态字
    REG_STATUS_OUT      : INT := 1;     // 本机 -> 对方 状态字
    REG_ID_START        : INT := 2;     // 组件 ID 起始地址 (2~17 共 16 个寄存器)
    ID_REG_COUNT        : INT := 16;    // 组件 ID 寄存器个数 (32 字符 / 2)
    REG_IMAGE_LAST      : INT := 31;    // 镜像数组最后一个下标 (18~31 预留)

    // --- 状态字位掩码 (bit0 为最低位) ---
    MASK_B0             : WORD := 16#0001;
    MASK_B1             : WORD := 16#0002;
    MASK_B2             : WORD := 16#0004;
    MASK_B3             : WORD := 16#0008;
    MASK_B15            : WORD := 16#8000;  // 心跳位

    // --- 错误码 ---
    ERR_NONE            : WORD := 16#0000;
    ERR_UP_LINK         : WORD := 16#0001;  // 上游通道链路断开
    ERR_DOWN_LINK       : WORD := 16#0002;  // 下游通道链路断开
END_VAR
