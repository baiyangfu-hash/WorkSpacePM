---
spec_id: INT-830
title: "FB_1030_SafetyManager 接口文档 (IFC)"
version: "V1.0.0"
status: "草稿（安全区，待 InoProShop 仿真 + 用户安全签字）"
created: "2026-10-22"
domain: plc
---

# 接口文档 (IFC) - FB_1030_SafetyManager 全机安全管理块

## 1. 接口功能定义

依据《电气自动化安全规范》V1.0（第 0、2、3、4、5、8、9、12 节）和《安全FB设计草案_20261022》（用户 10-22 定：急停、门锁、光栅、继电器反馈合成一块）。全机只调用一次，放在 OB1 最前面。

- 只**读**安全器件报给 PLC 的状态点，算出“能不能动”“复位采不采纳”“能不能开门”，交给各工位块。
- 安全回路靠安全继电器硬件切断（规范 0.1），本块不控制回路；电磁阀急停后清零还是保持、断点续跑还是重新初始化，由工位块按项目定。
- 计时依赖共享库 `FB_TON` V3.0.0（真实毫秒）。

## 2. 输入输出引脚表

| 变量名 | 类型 | 方向 | 说明 |
|:---|:---:|:---:|:---|
| `i_arrSafetyFault` | ARRAY[0..3] OF BOOL | VAR_INPUT | 安全继电器 41-42 常闭辅助点, 1 = 安全回路故障; 未用的填 FALSE (规范 8.1, 判断的唯一依据) |
| `i_arrEStopOk` | ARRAY[0..7] OF BOOL | VAR_INPUT | 急停按钮第三组触点, 1 = 正常; 未用的填 TRUE (规范 2.2, 只报警定位) |
| `i_arrCurtainOk` | ARRAY[0..7] OF BOOL | VAR_INPUT | 光栅进 PLC 的状态点, 1 = 未遮挡; 未用的填 TRUE (规范 5.1, 只报警定位) |
| `i_arrDoorClosed` | ARRAY[0..7] OF BOOL | VAR_INPUT | 门锁进 PLC 的那组触点, 1 = 门关好且已锁; 未用的填 TRUE (规范 4.1, 4.4) |
| `i_bFieldbusOk` | BOOL | VAR_INPUT | 远程 IO/总线伺服全部在线 (项目汇总后接入, 规范 8.3) |
| `i_bResetBtn` | BOOL | VAR_INPUT | 复位按钮进 PLC 的那组触点 (规范 3.1) |
| `i_bStartBtn` | BOOL | VAR_INPUT | 启动按钮 (规范 3.6) |
| `i_bAutoMode` | BOOL | VAR_INPUT | 设备在自动 (全机一个, 自动时申请开门不响应) |
| `i_bMotionStopped` | BOOL | VAR_INPUT | 伺服零速 + 所有动作完全停止 (全机一个, 项目汇总后接入) |
| `i_arrDoorReqBtn` | ARRAY[0..7] OF BOOL | VAR_INPUT | 每扇门的申请开门按钮; 未用的填 FALSE |
| `q_bSafeToRun` | BOOL | VAR_OUTPUT | 1 = 可以动; 各工位块的运动输出都要和它"与" (规范 0.1) |
| `q_bStopNow` | BOOL | VAR_OUTPUT | 1 = 安全条件现在丢了 (继电器故障/门没锁/总线断), 同一扫描生效 (规范 2.3) |
| `q_bRunResetPulse` | BOOL | VAR_OUTPUT | 第二次复位被采纳时出一个扫描的脉冲, 清工位故障和握手锁 (规范 3.4) |
| `q_bStartPulse` | BOOL | VAR_OUTPUT | 复位以后按启动, 出一个扫描的脉冲 (规范 3.6) |
| `q_iState` | INT | VAR_OUTPUT | 状态号 0~4, HMI 显示"现在卡在哪一步" |
| `q_dwAlarm` | DWORD | VAR_OUTPUT | 报警字, 位定义见文件头 |
| `q_arrDoorUnlock` | ARRAY[0..7] OF BOOL | VAR_OUTPUT | 每扇门的解锁线圈 (得电解锁、失电锁定) |
| `q_arrDoorLamp` | ARRAY[0..7] OF BOOL | VAR_OUTPUT | 每扇门申请按钮指示灯 (申请中 1 s 周期闪, 允许开门常亮) |

## 3. 常量（VAR CONSTANT，单独列出）

改值等于改安全区，要仿真 + 签字；HMI 只能显示、不能改（规范 0.4）。

| 常量名 | 值 | 含义 |
|:---|:---:|:---|
| `RESET_DELAY_MS` | 10000 | 两次复位最小间隔 10 s (规范 3.4/9, 固定, HMI 不能改) |
| `BLINK_HALF_MS` | 500 | 申请中指示灯 1 s 周期闪烁的半周期 (规范 4.3/9) |
| `RELOCK_CHECK_MS` | 1000 | 撤销解锁后门锁点须在 1 s 内回来, 否则重新解锁 (门开着按复位不采纳) |
| `ST_OPEN` | 0 | 安全回路断开 |
| `ST_WAIT_DELAY` | 1 | 等满 10 s |
| `ST_WAIT_RESET` | 2 | 等运行复位 |
| `ST_WAIT_START` | 3 | 等启动 |
| `ST_RUN` | 4 | 运行许可 |

## 4. 状态号 q_iState

| 状态 | 含义 | 走到下一步的条件 | 这时候按复位 |
|:---:|:---|:---|:---|
| 0 | 安全回路断开（上电也从这里开始） | 按复位（上升沿）且所有门锁好、总线在线 → 记时刻 → 1 | 第一次复位：只记时刻，不清东西；门没锁或总线断时不记，报 bit29 |
| 1 | 等满 10 s | 距第一次满 10 s **且** 所有继电器反馈正常 → 2 | 不足 10 s：不采纳，报 bit30（不重新计时）；继电器仍故障：报 bit29；满 10 s 后仍故障再按 = 新的第一次，重新计 10 s |
| 2 | 等运行复位 | 按复位 → 出 `q_bRunResetPulse` 一个扫描 → 3 | 采纳 |
| 3 | 等启动 | 按启动（上升沿）→ 出 `q_bStartPulse` 一个扫描 → 4 | 只清 bit29/30，不出脉冲 |
| 4 | 运行许可 `q_bSafeToRun` = 1 | — | — |

状态 2～4 任一拍出现继电器故障、门没锁或总线断 → 当拍回 0；状态 1 遇门没锁或总线断也回 0（继电器故障在状态 1 是预期的，继电器正在自己复位）。复位、启动都只认上升沿：按住复位跨过 10 s 不算按了一次；先按住启动再复位也不会启动。

## 5. 报警字 q_dwAlarm

| 位 | 含义 | 保持方式 |
|:---|:---|:---|
| bit0～7 | 第 1～8 个急停被按下（`i_arrEStopOk[n]` = 0） | 实时 |
| bit8～15 | 第 1～8 扇门没关好/没锁 | 实时 |
| bit16～23 | 第 1～8 道光栅被遮挡 | 实时 |
| bit24～27 | 第 1～4 个安全继电器反馈 = 故障 | 实时 |
| bit28 | 总线断线 | 实时 |
| bit29 | 复位被拒：安全回路未恢复 / 门没锁 / 总线断 | 保持到下次复位被采纳 |
| bit30 | 复位过早：距第一次不足 10 s | 保持到下次复位被采纳 |
| bit31 | 门锁回失败：撤销解锁后 1 s 内门锁点没回来（门还开着），已恢复解锁 | 保持到所有门锁好 |

## 6. 开门流程（每扇门一套，下标 0～7 = 第 1～8 扇门，规范 4.3）

| 步 | 条件 | 解锁输出 | 指示灯 |
|:---|:---|:---:|:---|
| 0 锁住 | — | 0 | 灭 |
| 1 申请中 | 不在自动时按申请按钮（上升沿）；自动时按了不响应 | 0 | 1 s 周期闪 |
| 2 允许开门 | `i_bMotionStopped` = 1（申请中切回自动则取消回 0） | 1 | 常亮 |
| 3 锁回确认 | 关门后按复位：撤销解锁，1 s 内门锁点 = 1 → 回 0；1 s 内没回来（门还开着）→ 回 2 重新解锁，报 bit31 | 0 | 灭 |

门锁是电磁锁（得电解锁、失电锁定），门锁点只有“关好且锁住”一个，所以“门开着按复位不采纳”用“撤销解锁后 1 s 内锁住没回来就恢复解锁”实现（T11）。锁门的这一下复位不算第一次复位（那一拍门还没锁住，按第 4 节报 bit29），锁好后再按两次复位 + 启动。

## 7. 调用示例（示例写法；项目接线以各项目自己的 OB1 为准）

```
fbSafety(i_arrSafetyFault := arrSafetyFault, i_arrEStopOk := arrEStopOk, i_arrCurtainOk := arrCurtainOk,
         i_arrDoorClosed := arrDoorClosed, i_bFieldbusOk := FIELDBUS_OK,
         i_bResetBtn := RESET_BTN, i_bStartBtn := START_BTN,
         i_bAutoMode := ..., i_bMotionStopped := ..., i_arrDoorReqBtn := arrDoorReqBtn);
工位块运动输出 AND fbSafety.q_bSafeToRun;  握手块使能 := fbSafety.q_bSafeToRun;
```

未用的数组位靠全局变量初值填：急停/光栅/门 = TRUE，继电器故障/申请按钮 = FALSE。不要在程序里给它们赋常量（安全区检查会判“安全点赋常量”）。

## 8. 验证

| 层 | 做法 | 结果 |
|:---|:---|:---|
| 云端逻辑仿真 | `reviews/tools/st_mini_sim.py` 直接执行本 .scl，仿真时钟按真实毫秒；`reviews/tools/test_fb1030_safety_manager.py` 设计草案 T1～T13 + 边界共 25 条 + 8 种变异反证；审计 154 后补 4 个继电器、8 扇门、8 个急停点和光栅逐个触发的参数化用例 | 全过（2026-10-25） |
| 测试台 | `DJ-2026-000/Test/safety_manager_test.scltest`（不靠计时的 T1、T2、T7～T13 等） | 云端跑不了，本机 LSP 跑 |
| InoProShop 仿真 | 用例单见分支说明，T1～T13 逐条（含 10 s 计时） | 待用户 D09 后做，100% 过才签字 |
