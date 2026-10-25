---
spec_id: INT-816
title: "FB_3002_ModbusTcpClient 接口文档 (IFC)"
version: "V0.1.0"
status: "草稿"
created: "2026-10-20"
domain: plc
---

# 接口文档 (IFC) - FB_3002_ModbusTcpClient 上下游 Modbus TCP 客户端数据映射层

## 1. 接口功能定义

依据 `BC-DJ-2026-009-004` 和通讯契约 V0.3（`02_PLC程序/程序文档/030_DJ-2026-009_通讯契约_INT.md` §2.0～2.2），实施卡 `CARD-DJ-2026-009-001`。

本机（AM500）做 Modbus TCP 客户端。报文收发由 InoProShop 里的 Modbus TCP 主站通道完成，通道把对方的保持寄存器映射到 4 个寄存器镜像数组（下标 = 协议地址，从 0 起）。本块只做数据映射和链路诊断：

- 把读镜像解包进 `ST_UpstreamDocking` / `ST_DownstreamDocking`（对方 → 本机），把本机信号封包进写镜像（本机 → 对方）。
- 链路断开时读侧变量保持最后值不刷新，对方心跳因此停止翻转，由 `FB_3001` 现有的 12 s 心跳超时报通讯故障。本块不直接改握手状态。
- 组件 ID：16 个寄存器，每个放 2 个字符，高字节在前，不足 32 个字符补 0；读入时遇到 0 即结束，内容原样保留。

## 2. 输入输出引脚表

| 变量名 | 类型 | 方向 | 说明 |
|:---|:---:|:---:|:---|
| `i_bEnable` | BOOL | VAR_INPUT | 功能块总使能 |
| `i_bUpLinkOK` | BOOL | VAR_INPUT | 上游 Modbus TCP 通道链路正常 (来自主站通道诊断) |
| `i_bDownLinkOK` | BOOL | VAR_INPUT | 下游 Modbus TCP 通道链路正常 (来自主站通道诊断) |
| `q_bComOK` | BOOL | VAR_OUTPUT | 上下游通道链路均正常 |
| `q_wErrorCode` | WORD | VAR_OUTPUT | 通讯层故障诊断字 (bit0 上游链路断, bit1 下游链路断) |
| `io_stExternal` | ST_ExternalDevice | VAR_IN_OUT | STD-820 通用外部对接数据总线 |
| `io_arrUpRead` | ARRAY[0..31] OF WORD | VAR_IN_OUT | 上游寄存器读镜像 (下标 = 协议地址) |
| `io_arrUpWrite` | ARRAY[0..31] OF WORD | VAR_IN_OUT | 上游寄存器写镜像 (下标 = 协议地址) |
| `io_arrDownRead` | ARRAY[0..31] OF WORD | VAR_IN_OUT | 下游寄存器读镜像 (下标 = 协议地址) |
| `io_arrDownWrite` | ARRAY[0..31] OF WORD | VAR_IN_OUT | 下游寄存器写镜像 (下标 = 协议地址) |

## 3. 常量（VAR CONSTANT，单独列出）

寄存器地址取自契约 V0.3 我方提议版，**未经对方签字**；对方签字时如果整体平移，只改这里。

| 常量名 | 值 | 含义 |
|:---|:---:|:---|
| `REG_STATUS_IN` | 0 | 对方 → 本机 状态字地址（待对方签字） |
| `REG_STATUS_OUT` | 1 | 本机 → 对方 状态字地址（待对方签字） |
| `REG_ID_START` | 2 | 组件 ID 起始地址，2～17 共 16 个寄存器（待对方签字） |
| `ID_REG_COUNT` | 16 | 组件 ID 寄存器个数（32 字符 / 2） |
| `REG_IMAGE_LAST` | 31 | 镜像数组最后一个下标（18～31 预留） |
| `MASK_B0`～`MASK_B3` | 16#0001～16#0008 | 状态字 bit0～bit3 掩码 |
| `MASK_B15` | 16#8000 | 心跳位掩码 |
| `ERR_NONE` | 16#0000 | 无故障 |
| `ERR_UP_LINK` | 16#0001 | 上游通道链路断开 |
| `ERR_DOWN_LINK` | 16#0002 | 下游通道链路断开 |

## 4. 寄存器 ↔ 变量对照

| 镜像 | 地址.位 | 对应结构体成员 |
|:---|:---:|:---|
| `io_arrUpRead` | 0.0 / 0.1 / 0.2 / 0.3 / 0.15 | `bUpstream_LineReady` / `bUpstream_SendModuleId` / `bUpstream_InfeedReq` / `bUpstream_InfeedArrivedAck` / `bUpstream_HeartbeatFromUp` |
| `io_arrUpRead` | 2～17 | `sRcvModuleID` |
| `io_arrUpWrite` | 1.0 / 1.1 / 1.2 / 1.3 / 1.15 | `bMachine_ReadyIn` / `bMachine_RcvModuleIdAck` / `bMachine_AllowInfeed` / `bMachine_InfeedArrived` / `bMachine_HeartbeatToUp` |
| `io_arrDownRead` | 0.0 / 0.1 / 0.2 / 0.3 / 0.15 | `bDownstream_LineReady` / `bDownstream_RcvModuleIdAck` / `bDownstream_AllowOutfeed` / `bDownstream_OutfeedArrived` / `bDownstream_HeartbeatFromDown` |
| `io_arrDownWrite` | 1.0 / 1.1 / 1.2 / 1.3 / 1.15 | `bMachine_ReadyOut` / `bMachine_SendModuleId` / `bMachine_OutfeedReq` / `bMachine_OutfeedArrivedAck` / `bMachine_HeartbeatToDown` |
| `io_arrDownWrite` | 2～17 | `sSendModuleID` |

主站通道建议配置（InoProShop 设备树，待现场确认）：上游读 FC03 地址 0 起 18 个、写 FC06 地址 1；下游读 FC03 地址 0 起 1 个、写 FC16 地址 1 起 17 个。轮询周期建议 ≤ 100 ms。

## 5. GlobalVars 需新增（导入 InoProShop 时补）

`OB1` 调用本块时用到下面这些全局变量，GlobalVars 的声明不在仓库里，导入工程时在 GlobalVars 里加上：

| 全局变量名 | 全局变量类型 | 用途 |
|:---|:---|:---|
| `fbModbusClient` | FB_3002_ModbusTcpClient | 本块实例 |
| `bModbusEnable` | BOOL | 本块使能 |
| `bModbusUpLinkOK` / `bModbusDownLinkOK` | BOOL | 接主站通道的链路诊断位 |
| `awModbusUpRead` / `awModbusUpWrite` | ARRAY[0..31] OF WORD | 上游读 / 写镜像，映射到主站通道 |
| `awModbusDownRead` / `awModbusDownWrite` | ARRAY[0..31] OF WORD | 下游读 / 写镜像，映射到主站通道 |
