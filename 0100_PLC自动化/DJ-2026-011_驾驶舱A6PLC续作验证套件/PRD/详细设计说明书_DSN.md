# 详细设计说明书（DSN）- DJ-2026-011 驾驶舱A6PLC续作验证套件

> 项目编号: DJ-2026-011
> 项目名称: 驾驶舱A6PLC续作验证套件
> 版本: V1.2.0
> 创建日期: 2026-09-10 16:11:55
> 项目类型: PLC 公共库验证项目（扁平结构）

## 1. 架构设计

### 1.1 设计目标
驾驶舱A6PLC续作验证套件。本项目采用扁平结构组织测试代码，避免多层嵌套带来的符号解析复杂度，使测试逻辑聚焦于被测公共库功能本身，而非项目结构管理。

### 1.2 扁平结构设计
项目目录结构如下（遵循 LSP-907 规范的扁平变体）：
```
DJ-2026-011/
├── .plc.json              # 项目配置，声明 libraries 引用 SysLib
├── DB1/                   # 全局变量数据块
│   └── GlobalVars.db      # 测试状态、结果记录、计数器
├── OB1/                   # 主程序
│   └── OB1.scl            # 测试调度框架与用例实现
├── Test/                  # 测试辅助代码（可选的 FC/测试数据）
│   └── .gitkeep
├── FB_0001/               # 功能块测试目录（示例，按需扩展）
│   └── .gitkeep
├── PRD/                   # 项目文档
│   ├── 需求分析文档_REQ.md
│   ├── 接口文档_INT.md
│   ├── 详细设计说明书_DSN.md
│   └── 技术方案文档_TEC.md
└── PM_SESSION_DJ-2026-011.md
```

### 1.3 设计原则
- **扁平优先**：DB1/OB1/Test 平级，不按业务域嵌套，降低符号路径深度
- **单一调度**：OB1 作为唯一测试调度入口，所有用例在 OB1 中顺序编排
- **结果集中**：所有测试结果统一写入 DB1，便于上位机一次性读取
- **库引用解耦**：通过 `.plc.json` 的 `libraries` 声明引用 SysLib，不在测试项目内复制库代码

## 2. 测试框架设计

### 2.1 测试用例组织
测试用例按"步骤"组织，每个步骤对应一条用例。OB1 维护一个全局步骤计数器 `uiTestStep`（UINT），每个扫描周期执行当前步骤的逻辑。步骤定义采用 `CASE` 分支结构：

```
CASE "DB1".uiTestStep OF
    0: // 空闲态，等待启动
    1: // 用例 TC-001-01：TON 基本定时
    2: // 用例 TC-001-02：TON 复位
    ...
    N: // 全部完成，置位 doAllPassed
END_CASE;
```

### 2.2 执行流程
1. **空闲态（步骤 0）**：等待 diTestStart 上升沿，初始化计数器，进入步骤 1
2. **用例态（步骤 1..N-1）**：每条用例内部维护子状态机（激励→调用→判定→推进）
   - 子状态 0：施加激励（置位/复位被测 FB 输入）
   - 子状态 1：等待预期周期数
   - 子状态 2：采样实际输出，与预期值比较
   - 子状态 3：写结果到 DB1，通过则步骤号+1，失败则跳转失败态
3. **完成态（步骤 N）**：置位 doAllPassed，返回空闲态
4. **失败态（步骤 999）**：置位 doFailed，记录失败步骤号，等待 diTestReset

### 2.3 自动/单步模式
- 自动模式（diModeAuto=TRUE）：用例通过后立即推进到下一步骤
- 单步模式（diModeAuto=FALSE）：用例通过后停在当前步骤，等待下一次 diTestStart 上升沿才推进

## 3. 数据结构设计

### 3.1 DB1 全局变量结构
DB1（GlobalVars）承载测试框架的全部状态与结果，结构如下：

| 变量名 | 类型 | 偏移 | 说明 |
|--------|------|------|------|
| uiTestStep | UINT | 0 | 当前执行步骤号（0=空闲） |
| uiSubState | UINT | 2 | 当前步骤的子状态号 |
| uiTotalCases | UINT | 4 | 用例总数（初始化时写入） |
| uiPassedCount | UINT | 6 | 已通过用例数 |
| uiFailedCount | UINT | 8 | 已失败用例数 |
| uiFailedStep | UINT | 10 | 首个失败步骤号（0=无失败） |
| bAllPassed | BOOL | 12.0 | 全部通过标志 |
| bFailed | BOOL | 12.1 | 失败标志（保持） |
| bRunning | BOOL | 12.2 | 运行中标志 |
| aCaseResult | ARRAY[1..200] OF BYTE | 13 | 每条用例结果（0=未执行,1=通过,2=失败） |
| dwCycleCounter | DWORD | 214 | 周期计数器（用于时序判定） |

### 3.2 测试结果记录
每条用例执行完毕后，将结果写入 `aCaseResult` 数组对应下标。上位机通过 S7 通信读取整个数组，生成"用例编号—结果"对照表。失败用例的步骤号额外记录在 `uiFailedStep`，便于快速定位。

### 3.3 预期值管理
预期值（黄金样本）以常量数组形式定义在 OB1 的声明区，与用例步骤号一一对应。预期值变更时需同步更新常量与 REQ 文档，并通过版本号标记。

## 4. 测试逻辑设计

### 4.1 OB1 测试调度
OB1 采用"区域化"布局，遵循 LSP-905 规范：
- **区域 1（初始化）**：FirstScan 时初始化 DB1 计数器、加载用例总数
- **区域 2（输入处理）**：采样 diTestStart/diTestReset/diModeAuto，做去抖与上升沿提取
- **区域 3（测试调度）**：CASE 分支调度当前步骤的子状态机
- **区域 4（结果输出）**：根据 DB1 状态驱动 doAllPassed/doFailed/doRunning

### 4.2 时序判定设计
对于定时器类用例，采用"周期计数法"判定：在激励施加时清零 `dwCycleCounter`，每个周期递增，当被测 FB 的 Q 输出跳变时采样 `dwCycleCounter`，与预期周期数比较（允许 ±1 周期容差）。

### 4.3 数值判定设计
对于数据处理类用例，采用"容差比较法"：实际值与预期值之差的绝对值 ≤ 容差阈值则通过。容差阈值按被测函数的精度等级在常量中定义（如限幅函数容差=0，一阶滤波容差=1.0）。

## 5. 结果分析设计

### 5.1 通过/失败判定标准
- **通过**：实际输出 == 预期值（逻辑类）或 |实际-预期| ≤ 容差（数值类），且时序周期数在容差内
- **失败**：任一判定条件不满足
- **未执行**：用例未被调度（步骤号未到达），结果数组对应位保持 0

### 5.2 报告生成
上位机读取 DB1 后，按以下维度生成报告：
1. **汇总**：总数 / 通过 / 失败 / 未执行，通过率百分比
2. **明细**：逐条列出用例编号、预期、实际、判定、耗时周期数
3. **缺陷**：失败用例的失败原因分类（时序超差、数值超差、状态错误、异常停机）

## 6. 报警汇总设计（F-007）

### 6.1 设计目标

在 OB1 现有双手启动验证之外，新增一个独立的报警汇总功能块，实现“任意报警点亮、锁存保持、无报警时复位熄灭、报警仍在时复位无效”的行为。报警汇总不与双手启动逻辑耦合，只通过第 1 路报警输入接收其同步故障。

### 6.2 功能块接口

功能块：`FB_2001_AlarmSummary_DJ2026011`（LSP-905 报警管理段 2001~2999）。

| 参数名 | 方向 | 类型 | 说明 |
|--------|------|------|------|
| i_arrAlarms | VAR_INPUT | ARRAY[1..16] OF BOOL | 16 路报警输入，任意一路 TRUE 表示有报警 |
| i_bReset | VAR_INPUT | BOOL | 复位按钮，上升沿有效，按下=TRUE |
| o_bAlarmLamp | VAR_OUTPUT | BOOL | 报警灯输出，报警锁存后保持点亮 |
| o_bAnyAlarm | VAR_OUTPUT | BOOL | 报警汇总结果，当前任一路报警为 TRUE |

静态变量：`fb_rTrigReset`（FB_R_TRIG，复位沿检测）、`s_bResetPulse`（单周期复位脉冲）、`s_bAlarmLatch`（锁存状态）。临时变量：`temp_iIndex`（遍历索引）。

### 6.3 锁存逻辑

1. 每周期遍历 `i_arrAlarms[1..16]`，任意一路为 TRUE 时 `o_bAnyAlarm` 置 TRUE。
2. `i_bReset` 经 `FB_R_TRIG` 取上升沿，得到单周期脉冲 `s_bResetPulse`。
3. 报警优先：`o_bAnyAlarm` 为 TRUE 时置位 `s_bAlarmLatch`；仅当 `o_bAnyAlarm` 为 FALSE 且 `s_bResetPulse` 为 TRUE 时清零。
4. `o_bAlarmLamp` 输出 `s_bAlarmLatch`，因此报警消失后灯仍亮，直到复位；报警仍在时复位被忽略。

### 6.4 OB1 集成与数据块映射

- 新建 `DB_AlarmSummaryTest`，内含 `fb_AlarmSummary` 实例、`s_arrAlarms[1..16]` 激励、`s_bReset` 复位激励、`s_bAlarmLamp` 与 `s_bAnyAlarm` 结果。
- OB1 在双手启动调用之后，先执行 `DB_AlarmSummaryTest.s_arrAlarms[1] := DB_TwoHandStartTest.s_bSyncFault;`，再调用 `DB_AlarmSummaryTest.fb_AlarmSummary(...)`。
- 第 2 至 16 路报警位不由 OB1 写入，保留给 `.scltest` 激励与后续扩展。

### 6.5 测试用例设计

新建 `Test/alarm_summary_test.scltest`，包含 6 条用例：

| 用例 | 场景 | 预期 |
|------|------|------|
| test1 | 无报警时按复位 | 报警灯保持熄灭 |
| test2 | 第 2 路报警 | 报警灯点亮 |
| test3 | 报警消失后锁存 | 灯保持点亮，按复位后熄灭 |
| test4 | 报警仍在时按复位 | 灯不熄灭；报警消失后再复位才熄灭 |
| test5 | 第 16 路边界报警 | 灯点亮并锁存，复位后熄灭 |
| test6 | 双手启动同步故障经第 1 路联动 | 灯点亮并锁存，故障消失后复位熄灭 |

### 6.6 边界与异常处理

- 数组下标固定为 1..16，遍历范围与数组声明一致，不存在越界访问。
- 复位只在上升沿生效，复位按钮长按不会反复清零。
- 报警与复位同时有效时按报警优先处理，灯保持点亮。
- 首扫描时 `s_bAlarmLatch` 默认为 FALSE，无报警则灯不亮。

## 7. 批量计数设计（F-008）

### 7.1 设计目标

在 OB1 现有双手启动与报警汇总之外，新增一个独立的批量计数功能块，实现“光电逐件计数、达到设定数量输出批次完成、复位上升沿清零重新计数”的行为。批量计数不与双手启动、报警汇总逻辑耦合，只通过 `DB_BatchCounterTest` 暴露激励与结果。

### 7.2 功能块接口

功能块：`FB_2002_BatchCounter_DJ2026011`（LSP-905 公共服务段 2001~2999）。

| 参数名 | 方向 | 类型 | 说明 |
|--------|------|------|------|
| i_bPhotoSensor | VAR_INPUT | BOOL | 光电传感器信号，每来一件产生一个上升沿 |
| i_dBatchTarget | VAR_INPUT | DINT | 批次设定数量，小于等于 0 时禁用计数 |
| i_bReset | VAR_INPUT | BOOL | 复位按钮，上升沿有效，按下=TRUE |
| o_dBatchCount | VAR_OUTPUT | DINT | 当前批次已计工件数 |
| o_bBatchComplete | VAR_OUTPUT | BOOL | 批次完成输出，达到设定数量后保持到复位 |

静态变量：`fb_rTrigPhoto`、`fb_rTrigReset`（FB_R_TRIG 沿检测）、`s_bPhotoPulse`、`s_bResetPulse`（单周期脉冲）、`s_bBatchLatch`（批次完成锁存）。无临时变量。

### 7.3 计数与完成逻辑

1. `i_bPhotoSensor` 与 `i_bReset` 分别经 `FB_R_TRIG` 取上升沿，得到单周期脉冲；光电长亮只计一件，复位长按不会反复清零。
2. 复位优先：复位脉冲到来时 `o_dBatchCount` 清零、`s_bBatchLatch` 清零，同一周期内到来的光电脉冲从 0 重新计 1 件。
3. 计数：`s_bBatchLatch` 为 FALSE 且 `i_dBatchTarget > 0` 时，每个光电脉冲 `o_dBatchCount` 加 1。
4. 完成：`o_dBatchCount` 达到 `i_dBatchTarget` 时钳位到设定值并置位 `s_bBatchLatch`，`o_bBatchComplete` 输出锁存状态；锁存期间继续来件不再累加。
5. 设定数量小于等于 0 时不计数也不完成，复位仍可清零。

### 7.4 OB1 集成与数据块映射

- 新建 `DB_BatchCounterTest`，内含 `fb_BatchCounter` 实例、`s_bPhotoSensor` 光电激励、`s_dBatchTarget` 设定数量、`s_bReset` 复位激励、`s_dBatchCount` 与 `s_bBatchComplete` 结果。
- OB1 在报警汇总调用之后调用 `DB_BatchCounterTest.fb_BatchCounter(...)`，激励与结果均经测试 DB 读写，不新增物理 IO。

### 7.5 测试用例设计

新建 `Test/batch_counter_test.scltest`，包含 7 条用例：

| 用例 | 场景 | 预期 |
|------|------|------|
| test1 | 复位上升沿 | 计数清零, 批次未完成 |
| test2 | 3 个光电上升沿 | 计数为 3, 批次未完成 |
| test3 | 光电长亮 10 个周期 | 只计 1 件 |
| test4 | 计满 5 件 | 计数保持 5, 批次完成 |
| test5 | 完成后再来一件 | 计数保持 5, 完成保持 |
| test6 | 完成后复位再计 2 件 | 复位后为 0, 再计为 2 |
| test7 | 设定数量为 1 | 首件即批次完成 |

### 7.6 边界与异常处理

- 计数为 DINT，达到设定值后钳位，不存在溢出累加。
- 光电与复位均只在上升沿生效，长亮或长按不会重复计数或清零。
- 设定数量小于等于 0 时模块不动作，避免非法设定导致误完成。
- 首扫描时 `o_dBatchCount` 为 0、`s_bBatchLatch` 为 FALSE，批次完成不误输出。

## 8. 变更记录
| 日期 | 版本 | 变更内容 | 变更人 |
|------|------|---------|--------|
| 2026-09-10 16:11:55 | V1.0.0 | 初始版本，由 plc-test-suite 模板生成 | auto-pm |
| 2026-10-22 | V1.1.0 | 新增第 6 节报警汇总设计（F-007） | trae |
| 2026-10-22 | V1.2.0 | 新增第 7 节批量计数设计（F-008） | trae |
