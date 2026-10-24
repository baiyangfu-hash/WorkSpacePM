# 详细设计说明书 FB_1004_GlueMachineFeeder_BufferFraming

## 0. 文档基础信息

| 属性 | 值 |
|------|-----|
| **文档标题** | FB_1004_GlueMachineFeeder_BufferFraming详细设计说明书 |
| **文档版本** | V15.0.0 |
| **关联源码** | 04_打胶机送料/FB_1004_GlueMachineFeeder_BufferFraming.scl |
| **关联IFC** | 接口文档_IFC-FB1004-GlueMachineFeeder.md |
| **编制日期** | 2026-10-24 |
| **编制人** | Claude（用户待审） |
| **遵循规范** | LSP-905_SCL编程规范 |
| **依据** | 全局 `00_程序方案/接口文档_INT.md` 与 `详细设计说明书_DSN.md` |

## 1. 设计依据

工艺步序、转移条件、定时和报警表以全局 `00_程序方案/详细设计说明书_DSN.md` 为准，本文只记录**编码层面的实现选择**，以及与全局文档的差异（待评审确认）。

## 2. 实现结构：X2 送料小车（FB_1004_GlueMachineFeeder_BufferFraming）

1. 顶部调用 5 个 `FB_TON`（窗口、4 光电全亮 10 s、全灭持续 10 s（与 X102 二选一返回）、F90、F91）。
2. 位置判定用当前位置与目标的绝对差不超过 `rPosTol`；`s_bX2Go` 命令保持到 `Abs.Done`。
3. X2 取料点已等于送料点时（D512 = D522），步 2 直接走完，避免原程序卡死。
4. Y47 与步号无关：X2 在取料点 ∧ 不在驱动 ∧ 自动 ∧ 无 M8。
5. “X1 送料完成”清除脉冲 `bFeedDoneClr` 写在 Bridge，由 FB_2002 清取放料的两个完成位。

### 源码头部说明
