# 接口文档 FB_1020_EquipmentHandshake

## 0. 文档基础信息

| 属性 | 值 |
|------|-----|
| **文档标题** | FB_1020 设备通讯握手接口定义 |
| **文档版本** | V2.0.0 |
| **2026-10-22 对齐** | 接口表“说明”列按代码行尾注释逐字对齐（`plc docs check`），对齐前写法移到文末附录；只改文档，版本号和文件名不变 |
| **关联源码** | communication/FB_1020_EquipmentHandshake.scl |
| **关联DSN** | 详细设计说明书_DSN-FB1020-EquipmentHandshake-V2.0.0.md |
| **编制日期** | 2026-05-30 |
| **编制人** | Trae |
| **审核人** | 人工 |
| **遵循规范** | LSP-905 V1.0.1, LSP-904 V1.2.0, LSP-903 V1.0.0 |
| **V2.0.0 变更** | Breaking Change: ST_ProductData GlassID 30 INT -> 16 WORD; ST_HandshakeCh 扁平字段 -> WriteProduct/ReadProduct 嵌入; [B1] Disable段不再清除Ready/DsReady/Reserved; [B2] 上游COMPLETE态增加Write.Complete回传; [B3] 产品数据改为MoveBusy上升沿一次性锁存; [D1] 新增q_stUpReceivedProduct/q_stDownReceivedProduct输出 |

## 1. 功能概述

**通用设备通讯握手功能块**, 封装上游送出(UP-Stream)和下游接收(DOWN-Stream)双通道的完整握手协议状态机. 适用于任何需要设备间物料交接信号协调的自动化场景.

### 1.1 职责边界

| 做什么 | 不做什么 |
|--------|----------|
| 管理上游5态状态机(IDLE/REQ_OUT/MOVE_BUSY/COMPLETE/FAULT) | 不管理具体通讯介质(Modbus/Profinet/硬线等) |
| 管理下游5态状态机(IDLE/REQ_IN/MOVE_BUSY/COMPLETE/FAULT) | 不操作物理IO(由OB1映射) |
| 双通道心跳方波生成+超时监视 | 不负责通讯驱动层的连接/重连 |
| 产品数据上升沿锁存透传(GlassID/Speed/Quality/Grade) | 不处理HMI画面组态 |
| 接收侧产品数据输出(ReadProduct -> q_stReceivedProduct) | 不处理产线级调度逻辑 |
| 综合报警输出+状态码诊断 | |

### 1.2 实例化场景

| 场景 | 实例名 | 说明 |
|------|--------|------|
| 磨边机与物流线交接 | fbHsZ01 : FB_1020 | Z01磨边机上游送出+下游接收 |
| 清洗机与物流线交接 | fbHsZ03 : FB_1020 | Z03清洗机上游送出+下游接收 |
| 任意设备间物料交接 | fbHsXxx : FB_1020 | 通用实例, 适配所有Z01~Z35 |

### 1.3 协议时序示意

```
==================== UP-Stream (上游送出) ====================

   上游设备              本机
   ┌─────┐              ┌──────────┐
   │Ready │─────────────→│检测就绪   │
   │      │←──RequestOut│发出请求   │
   │      │   (等1sec)  │           │
   │      │─────────────→│           │
   │      │   MoveBusy  │搬运中     │
   │      │←── Complete │完成确认   │  ← V2.0.0: 本机回传Complete
   │      │   产品数据  │锁存透传   │
   └─────┘              └──────────┘

==================== DOWN-Stream (下游接收) ====================

   本机                  下游设备
   ┌──────────┐          ┌─────┐
   │           │←─RequestIn│要料请求  │
   │  (等1sec) │          │     │
   │  MoveBusy │─────────→│搬运中│
   │锁存产品数据│─────────→│     │
   │  Complete │─────────→│完成  │
   └──────────┘          └─────┘
```

## 2. 状态机步序常量

### 2.1 上游通道 (UpStream_SM)

| 常量名 | 值 | 名称 | 说明 |
|--------|---|------|------|
| UP_IDLE | 0 | 空闲等待 | 等待i_bRequestOut上升沿+上游就绪 |
| UP_REQ_OUT | 1 | 发出送料请求 | RequestOut=TRUE, 等待延迟 |
| UP_MOVE_BUSY | 2 | 搬运中 | MoveBusy=TRUE, 上升沿锁存产品数据, 等待Complete |
| UP_COMPLETE | 3 | 完成确认 | Write.Complete=TRUE回传, 输出q_bUpComplete脉冲, 回IDLE |
| UP_FAULT | 4 | 通讯故障 | 心跳超时, 冻结输出, 等待复位 |

### 2.2 下游通道 (DownStream_SM)

| 常量名 | 值 | 名称 | 说明 |
|--------|---|------|------|
| DN_IDLE | 0 | 空闲等待 | 等待RequestIn上升沿+允许出料+下游就绪 |
| DN_REQ_IN | 1 | 收到进料请求 | 等待响应延迟 |
| DN_MOVE_BUSY | 2 | 搬运中 | DsMoveBusy=TRUE, 上升沿锁存产品数据, 等待TransportDone或DsComplete |
| DN_COMPLETE | 3 | 完成确认 | 输出q_bDownComplete脉冲, 回IDLE |
| DN_FAULT | 4 | 通讯故障 | 心跳超时, 冻结输出, 等待复位 |

## 3. 接口定义

### 3.1 VAR_INPUT (控制信号)

| 名称 | 类型 | 默认值 | 有效值域 | 说明 | 来源 |
|------|------|--------|----------|------|------|
| i_bEnable | BOOL | FALSE | TRUE/FALSE | 使能 TRUE=执行握手逻辑 | OB1 |
| i_bRequestOut | BOOL | FALSE | TRUE/FALSE | 向上游发起要料请求        | 编排器/OB1 |
| i_bAllowDischarge | BOOL | FALSE | TRUE/FALSE | 允许向下游出料 | 编排器/OB1 |
| i_bReset | BOOL | FALSE | TRUE/FALSE | 复位故障/强制回IDLE | OB1←HMI |
| i_bTransportDone | BOOL | FALSE | TRUE/FALSE | 物理搬运完成信号(输送机构反馈) | OB1←FB_xxx |

### 3.2 VAR_INPUT (产品数据)

| 名称 | 类型 | 默认值 | 说明 | 来源 |
|------|------|--------|------|------|
| i_stProductData | ST_ProductData | -- | 待传递的产品跟踪数据 | 编排器 |

**ST_ProductData 子字段**:

| 子字段 | 类型 | 说明 |
|--------|------|------|
| .GlassID | ARRAY[1..16] OF WORD | 产品唯一标识 ASCII, 16 WORD = 32 bytes |
| .TransferSpeed | INT | 传输速度(m/min) |
| .Quality | INT | 产品质量代码 |
| .Grade | INT | 产品等级 |

### 3.3 VAR_INPUT (时序参数, 可配置)

| 名称 | 类型 | 默认值 | 有效值域 | 说明 | 来源 |
|------|------|--------|----------|------|------|
| i_dReqDelayMs | DINT | 1000 | 0~60000 | 请求->搬运 延迟时间 ms  | OB1←HMI |
| i_dHbToggleMs | DINT | 500 | 100~5000 | 心跳翻转周期 ms  | OB1←HMI |
| i_dHbTimeoutMs | DINT | 3000 | 500~30000 | 心跳超时阈值 ms  | OB1←HMI |
| i_dCompleteMs | DINT | 500 | 100~5000 | 完成脉冲宽度 ms  | OB1←HMI |

### 3.4 VAR_OUTPUT (状态输出)

| 名称 | 类型 | 默认值 | 有效值域 | 说明 | 去向 |
|------|------|--------|----------|------|------|
| q_bUpReady | BOOL | FALSE | TRUE/FALSE | 上游设备就绪综合信号 | 编排器/HMI |
| q_bDownReady | BOOL | FALSE | TRUE/FALSE | 下游设备就绪综合信号 | 编排器/HMI |
| q_bUpComplete | BOOL | FALSE | TRUE/FALSE | 上游送出完成脉冲 | 编排器 |
| q_bDownComplete | BOOL | FALSE | TRUE/FALSE | 下游接收完成脉冲 | 编排器 |
| q_bAlarm | BOOL | FALSE | TRUE/FALSE | 综合报警输出 | OB1→FB_2001/HMI |
| q_wStatusCode | WORD | 16#0000 | 16#0000~16#0404 | 状态码 Hi=上游 Lo=下游 | HMI |

### 3.5 VAR_OUTPUT (诊断输出)

| 名称 | 类型 | 默认值 | 有效值域 | 说明 | 去向 |
|------|------|--------|----------|------|------|
| q_iUpState | INT | 0 | 0~4 | 上游状态机当前状态 | HMI |
| q_iDownState | INT | 0 | 0~4 | 下游状态机当前状态 | HMI |

### 3.6 VAR_OUTPUT (产品数据输出) - V2.0.0 新增

| 名称 | 类型 | 默认值 | 说明 | 去向 |
|------|------|--------|------|------|
| q_stUpReceivedProduct | ST_ProductData | -- | 从上游接收的产品数据                     | 编排器 |
| q_stDownReceivedProduct | ST_ProductData | -- | 从下游接收的产品数据                                | 编排器 |

### 3.7 VAR_IN_OUT (通道结构体)

| 名称 | 类型 | 说明 | OB1接线 |
|------|------|------|---------|
| io_stUpStream | ST_HandshakeCh | 上游通道 Write=本机->上游 Read=上游->本机 | 通讯层映射 |
| io_stDownStream | ST_HandshakeCh | 下游通道 Write=本机->下游 Read=下游->本机 | 通讯层映射 |

**ST_HandshakeCh 子字段**:

| 子字段 | 类型 | 方向 | 说明 |
|--------|------|------|------|
| .Write | ST_HandshakeBits | 本机→对方 | FB写入, 调用方负责发送 |
| .WriteProduct | ST_ProductData | 本机→对方 | 产品数据, MoveBusy上升沿锁存 |
| .Read | ST_HandshakeBits | 对方→本机 | 调用方负责填充, FB读取 |
| .ReadProduct | ST_ProductData | 对方→本机 | 对方发来的产品数据 |
| .CommFault | BOOL | 诊断 | 通讯故障(由FB写入) |
| .HbTimeout | BOOL | 诊断 | 心跳超时(由FB写入) |

**ST_HandshakeBits 子字段**:

| 子字段 | 说明 | FB行为 |
|--------|------|--------|
| .Heartbeat | 送料心跳 | FB自动写入方波 |
| .RequestOut | 送料请求 | 上游REQ_OUT态置TRUE |
| .MoveBusy | 搬运中 | 上游MOVE_BUSY态置TRUE |
| .Complete | 完成 | 上游COMPLETE态置TRUE (V2.0.0: 回传对方) |
| .Ready | 本机就绪 | 外部写入, FB不触碰 (V2.0.0: Disable不清除) |
| .Reserved1~3 | 预留 | FB不触碰 (V2.0.0: Disable不清除) |
| .RcvHeartbeat | 接料心跳 | FB自动写入方波 |
| .RequestIn | 进料请求 | 预留(当前未使用) |
| .DsMoveBusy | 下游搬运中 | 下游MOVE_BUSY态置TRUE |
| .DsComplete | 下游完成 | 下游COMPLETE态置TRUE |
| .DsReady | 下游就绪 | 外部写入, FB不触碰 (V2.0.0: Disable不清除) |
| .Reserved4~6 | 预留 | FB不触碰 (V2.0.0: Disable不清除) |

## 4. 行为逻辑

### 4.1 上游送出流程

```
IDLE (空闲)
  ├── 清除Write.RequestOut/MoveBusy/Complete
  ├── 清除bUpDataLatched
  ├── 等待 i_bRequestOut上升沿 AND q_bUpReady
  └── [触发] → REQ_OUT

REQ_OUT (发出请求)
  ├── Write.RequestOut := TRUE
  ├── 启动tReqOutDelay(i_dReqDelayMs)
  ├── 延迟到达 → MOVE_BUSY
  ├── Reset → IDLE
  └── HbTimeout → FAULT

MOVE_BUSY (搬运中)
  ├── Write.MoveBusy := TRUE; Write.RequestOut := FALSE
  ├── MoveBusy上升沿 AND NOT bUpDataLatched: 锁存i_stProductData到WriteProduct
  ├── Read.Complete上升沿: 锁存ReadProduct到q_stUpReceivedProduct → COMPLETE
  ├── Reset → IDLE
  └── HbTimeout → FAULT

COMPLETE (完成)
  ├── Write.MoveBusy := FALSE; Write.Complete := TRUE (V2.0.0: 回传对方)
  ├── q_bUpComplete := TRUE (脉冲 i_dCompleteMs)
  └── 脉冲结束 → IDLE

FAULT (故障)
  ├── CommFault := TRUE, 冻结输出
  ├── Reset OR 心跳恢复 → IDLE
  └── 清除所有Write信号
```

### 4.2 下游接收流程

```
IDLE (空闲)
  ├── 清除Write.RequestIn/DsMoveBusy/DsComplete
  ├── 清除bDsDataLatched
  ├── 等待 Read.RequestIn上升沿 AND i_bAllowDischarge AND q_bDownReady
  └── [触发] → REQ_IN

REQ_IN (收到请求)
  ├── 启动tReqInDelay(i_dReqDelayMs)
  ├── 延迟到达 → MOVE_BUSY
  ├── Reset → IDLE
  ├── HbTimeout → FAULT
  └── RequestIn撤销 → IDLE

MOVE_BUSY (搬运中)
  ├── Write.DsMoveBusy := TRUE
  ├── DsMoveBusy上升沿 AND NOT bDsDataLatched: 锁存i_stProductData到WriteProduct
  ├── i_bTransportDone上升沿 OR Read.DsComplete上升沿: 锁存ReadProduct到q_stDownReceivedProduct → COMPLETE
  ├── Reset → IDLE
  └── HbTimeout → FAULT

COMPLETE (完成)
  ├── Write.DsMoveBusy := FALSE; Write.DsComplete := TRUE
  ├── q_bDownComplete := TRUE (脉冲 i_dCompleteMs)
  └── 脉冲结束 → IDLE

FAULT (故障)
  ├── CommFault := TRUE, 冻结输出
  ├── Reset OR 心跳恢复 → IDLE
  └── 清除所有Write信号
```

### 4.3 心跳机制

```
本机行为:
  → 每 i_dHbToggleMs 翻转一次 Heartbeat/RcvHeartbeat
  → 写入 io_stUpStream.Write.Heartbeat
  → 写入 io_stDownStream.Write.RcvHeartbeat

监视行为:
  → 检测 Read.Heartbeat 或 Read.RcvHeartbeat 任一翻转
  → 有翻转: 重置超时定时器
  → 无翻转超过 i_dHbTimeoutMs: HbTimeout := TRUE
```

### 4.4 就绪综合信号

```
q_bUpReady = Read.Ready AND (NOT CommFault) AND (NOT HbTimeout)
q_bDownReady = Read.DsReady AND (NOT CommFault) AND (NOT HbTimeout)
```

### 4.5 报警逻辑

```
q_bAlarm = Up.CommFault OR Down.CommFault
         OR Up.HbTimeout OR Down.HbTimeout
```

## 5. 接口交互协议

```
编排器/OB1                    FB_1020_EquipmentHandshake
     │                                │
     │── i_bEnable := TRUE ──────────→│  启动握手
     │                                │  心跳开始翻转
     │                                │
     │── i_bRequestOut := TRUE(沿) ──→│  上游: IDLE→REQ_OUT
     │                                │  → MOVE_BUSY (1s后)
     │                                │  → 上升沿锁存WriteProduct
     │                                │  → COMPLETE (对方确认)
     │←── Write.Complete := TRUE ────│  (V2.0.0: 回传对方)
     │←── q_bUpComplete := TRUE ─────│  (脉冲)
     │←── q_stUpReceivedProduct ─────│  (V2.0.0: 接收产品数据)
     │                                │
     │←── Read.RequestIn(沿) ────────│  下游: IDLE→REQ_IN
     │                                │  → MOVE_BUSY (1s后)
     │                                │  → 上升沿锁存WriteProduct
     │── i_bTransportDone := TRUE ──→│  → COMPLETE
     │←── q_bDownComplete := TRUE ───│  (脉冲)
     │←── q_stDownReceivedProduct ───│  (V2.0.0: 接收产品数据)
     │                                │
     │←── q_bAlarm := TRUE ──────────│  (通讯中断)
     │── i_bReset := TRUE ──────────→│  → FAULT→IDLE
     │                                │
     │  [io_stUpStream] ── VAR_IN_OUT │  上游通道
     │  [io_stDownStream] ─ VAR_IN_OUT│  下游通道
```

## 6. V2.0.0 迁移指南

### 6.1 ST_HandshakeCh 字段映射

| V1.x 字段 | V2.0.0 字段 | 说明 |
|-----------|-------------|------|
| .WriteGlassID | .WriteProduct.GlassID | 扁平→嵌入, 类型 INT→WORD, 长度 30→16 |
| .WriteSpeed | .WriteProduct.TransferSpeed | 字段名变更 |
| .WriteQuality | .WriteProduct.Quality | 路径变更 |
| .WriteGrade | .WriteProduct.Grade | 路径变更 |
| .WriteReserved | (已移除) | 不再需要Reserved字段 |
| .ReadGlassID | .ReadProduct.GlassID | 扁平→嵌入, 类型 INT→WORD, 长度 30→16 |
| .ReadSpeed | .ReadProduct.TransferSpeed | 字段名变更 |
| .ReadQuality | .ReadProduct.Quality | 路径变更 |
| .ReadGrade | .ReadProduct.Grade | 路径变更 |
| .ReadReserved | (已移除) | 不再需要Reserved字段 |

### 6.2 Disable行为变更

| 信号 | V1.x | V2.0.0 | 原因 |
|------|------|--------|------|
| Write.Ready | 清除 | **不清除** | 由外部写入, FB不应触碰 |
| Write.DsReady | 清除 | **不清除** | 由外部写入, FB不应触碰 |
| Write.Reserved1~6 | 清除 | **不清除** | 预留字段, FB不应触碰 |

### 6.3 新增输出

| 输出 | 说明 |
|------|------|
| q_stUpReceivedProduct | 从上游接收的产品数据, Read.Complete上升沿锁存 |
| q_stDownReceivedProduct | 从下游接收的产品数据, TransportDone/DsComplete上升沿锁存 |

## 7. 接口统计

| 项目 | 数量 | 说明 |
|------|:----:|------|
| VAR_INPUT (控制) | 5 | Enable/RequestOut/AllowDischarge/Reset/TransportDone |
| VAR_INPUT (产品数据) | 1 | ST_ProductData结构体 |
| VAR_INPUT (时序参数) | 4 | ReqDelayMs/HbToggleMs/HbTimeoutMs/CompleteMs |
| **VAR_INPUT 合计** | **10** | |
| VAR_OUTPUT (状态) | 6 | UpReady/DownReady/UpComplete/DownComplete/Alarm/StatusCode |
| VAR_OUTPUT (诊断) | 2 | UpState/DownState |
| VAR_OUTPUT (产品数据) | 2 | UpReceivedProduct/DownReceivedProduct |
| **VAR_OUTPUT 合计** | **10** | |
| VAR_IN_OUT (通道) | 2 | ST_HandshakeCh x2 |
| **总计** | **22** | |

## 8. 关联文档

| 文档 | 路径 | 版本 |
|------|------|:----:|
| DSN | 详细设计说明书_DSN-FB1020-EquipmentHandshake-V2.0.0.md | V2.0.0 |
| ST_HandshakeBits | ../types/ST_HandshakeBits.scl | V1.1.0 |
| ST_HandshakeCh | ../types/ST_HandshakeCh.scl | V2.0.0 |
| ST_ProductData | ../types/ST_ProductData.scl | V2.0.0 |
| LSP-905 | 905_SCL编程规范_LSP-V1.0.1.md | V1.0.1 |
| LSP-904 | 904_SCL注释规范_LSP-V1.2.0.md | V1.2.0 |
| LSP-903 | 903_定时器使用规范_LSP-V1.0.0.md | V1.0.0 |

---

## 附：2026-10-22 对齐前的旧说明（留底，不删）

> 2026-10-22 按 `plc docs check` 把上面接口表的“说明”列逐字改成代码行尾注释（代码为准，只改文档，没改 .scl）。
> 下表是改之前文档里的写法，有些比代码注释多写了单位、触发方式或用途，留在这里备查；
> 其中与代码实际行为不一致的地方，见共享库对齐记录 `PRD/文档代码对齐记录_20261022.md` 第 3 节。

| 引脚 | 对齐前文档说明 | 现说明（= 代码注释） |
|------|------|------|
| i_bRequestOut | 向上游发起要料请求(上升沿触发) | 向上游发起要料请求 |
| i_bTransportDone | 物理搬运完成信号(输送机构到位) | 物理搬运完成信号(输送机构反馈) |
| i_dReqDelayMs | 请求->搬运 延迟时间(ms) | 请求->搬运 延迟时间 ms |
| i_dHbToggleMs | 心跳翻转周期(ms) | 心跳翻转周期 ms |
| i_dHbTimeoutMs | 心跳超时阈值(ms) | 心跳超时阈值 ms |
| i_dCompleteMs | 完成脉冲宽度(ms) | 完成脉冲宽度 ms |
| q_stUpReceivedProduct | 从上游接收的产品数据(Read.Complete上升沿锁存) | 从上游接收的产品数据 |
| q_stDownReceivedProduct | 从下游接收的产品数据(TransportDone/DsComplete上升沿锁存) | 从下游接收的产品数据 |
| io_stUpStream | 上游通道: Write=本机→上游, Read=上游→本机 | 上游通道 Write=本机->上游 Read=上游->本机 |
| io_stDownStream | 下游通道: Write=本机→下游, Read=下游→本机 | 下游通道 Write=本机->下游 Read=下游->本机 |
