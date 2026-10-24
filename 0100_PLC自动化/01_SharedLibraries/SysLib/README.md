# SysLib 库 - 多平台兼容性指南

**版本**: V2.0.0 (平台兼容性优化版)
**最后更新**: 2026-05-02
**适用环境**: Siemens LSP / TIA Portal / GX Works / CODESYS

---

## 📋 概述

SysLib 是一个符合 **IEC 61131-3 标准**的 PLC 功能库，专为多平台移植设计。

### 当前版本特点
- ✅ **完全兼容 Siemens LSP** (VS Code 开发环境)
- ✅ **可无缝移植到 TIA Portal**
- ✅ **支持 GX Works 和 CODESYS 平台**
- ⚠️ **部分功能在 LSP 中为简化实现**

---

## 🎯 设计理念

### 核心原则
> **"一次编写，多处运行 - 通过注释指导平台适配"**

### 实现策略
1. **避免类型转换操作** - 不使用 TIME↔DINT/INT 转换（LSP 限制）
2. **统一基础数据类型** - Timer 使用 DINT 计数，避免 TIME 类型
3. **详细的多平台注释** - 每个文件都包含移植指南
4. **保留标准接口外观** - 功能块名称和参数命名符合 IEC 标准

---

## 📊 模块兼容性矩阵

| 模块 | 文件数 | LSP 兼容性 | TIA 兼容性 | CODESYS 兼容性 | 状态 |
|------|--------|-----------|-----------|---------------|------|
| **timer/** | 4 | ✅ 100% | ✅ 95%* | ✅ 95%* | 已优化 |
| **convert/** | 4 | ✅ 100% | ✅ 100%^ | ✅ 100%^ | 占位实现 |
| **log/** | 1 | ✅ 100% | ✅ 90%^^ | ✅ 90%^^ | 简化版 |
| **counter/** | 3 | ✅ 100% | ✅ 100% | ✅ 100% | 无需修改 |
| **edge/** | 2 | ✅ 100% | ✅ 100% | ✅ 100% | 无需修改 |
| **pulse/** | 1 | ✅ 100% | ✅ 100% | ✅ 100% | 待验证 |
| **actuator/** | 2 | ✅ 100% | ✅ 100% | ✅ 100% | 🆕 新增 |

**图例:**
- `*` PT/ET 参数需要从 DINT 改为 TIME 类型
- `^` 需要启用注释中的平台特定代码
- `^^` 日志格式化功能简化，核心记录功能完整

---

## 🔧 各模块详细说明

### 1️⃣ Timer 模块 (`timer/`)

> **2026-10-21 V3.0.0 起：FB_TON、FB_TONR 是真实毫秒。** 名字和引脚不变（PT/ET 仍为 DINT），
> 内部改为调用平台标准 IEC 定时器 `TON`，FB_TONR 用 TON 分段累计、IN 断开时保持、R 清零。
> 本节下面"PT=扫描周期数"、"ET*10 换算"、"移植到 TIA 改 TIME 类型"的说明只适用于 FB_TOF、FB_TP（仍是旧的按扫描计数，暂无调用方）。
> 导入方法：TIA Portal 直接导入（若报 TON 类型未知，把内部实例类型改为 `TON_TIME`）；
> InoProShop 粘贴到 POU 时去掉 `BEGIN` 行和变量前的 `#`。
> 说明与验证步骤见分支说明 `plans/共享库计时器毫秒化_预做分支说明_20261021.md`（项目共享文件夹）。

#### 包含文件
- [FB_TON.scl](timer/FB_TON.scl) - 接通延时定时器
- [FB_TOF.scl](timer/FB_TOF.scl) - 关断延时定时器
- [FB_TONR.scl](timer/FB_TONR.scl) - 保持型接通延时定时器
- [FB_TP.scl](timer/FB_TP.scl) - 脉冲定时器

#### 接口差异

| 参数 | LSP 版本 | TIA/CODESYS 版本 |
|------|---------|------------------|
| PT | DINT (扫描周期数) | TIME (毫秒) |
| ET | DINT (已过周期数) | TIME (毫秒) |

#### 移植到 TIA Portal 的修改步骤

```pascal
(* 步骤 1: 修改参数类型 *)
VAR_INPUT
    IN : BOOL;
    PT : TIME;   (* 从 DINT 改为 TIME *)
END_VAR
VAR_OUTPUT
    Q : BOOL;
    ET : TIME;   (* 从 DINT 改为 TIME *)
END_VAR
VAR
    Counter : DINT := 0;
    PT_Cycles : DINT := 0;  (* 新增内部变量 *)
    Running : BOOL := FALSE;
END_VAR

(* 步骤 2: 修改初始化逻辑 *)
BEGIN
    IF #PT_Cycles = 0 THEN
        #PT_Cycles := DINT(#PT) / 10;  (* TIME → DINT 转换 *)
    END_IF;

    (* 步骤 3: 修改 ET 赋值 *)
    (* 原始: #ET := #Counter; *)
    #ET := TIME(#Counter * 10);  (* DINT → TIME 转换 *)

    (* 其余逻辑保持不变... *)
END_FUNCTION_BLOCK
```

#### 使用示例（FB_TON / FB_TONR，各平台写法相同）

```pascal
VAR
    myTON : FB_TON;
    bStart : BOOL;
    bOut : BOOL;
    diElapsedMs : DINT;
END_VAR

myTON(IN := bStart, PT := 500, Q => bOut, ET => diElapsedMs);
(* PT=500 表示 500 ms (V3.0.0 起真实毫秒); ET 也是毫秒, 到点后停在 PT *)
```

---

### 2️⃣ Convert 模块 (`convert/`)

#### 包含文件
- [FC_DINT_TO_TIME.scl](convert/FC_DINT_TO_TIME.scl)
- [FC_TIME_TO_DINT.scl](convert/FC_TIME_TO_DINT.scl)
- [FC_INT_TO_TIME.scl](convert/FC_INT_TO_TIME.scl)
- [FC_TIME_TO_INT.scl](convert/FC_TIME_TO_INT.scl)

#### 当前实现状态
- **LSP 环境**: 返回占位值 (T#0ms 或 0)
- **生产环境**: 需要启用注释中的平台特定代码

#### 启用 TIA Portal 实现

以 `FC_DINT_TO_TIME.scl` 为例:

```pascal
FUNCTION FC_DINT_TO_TIME : TIME
VAR_INPUT
    DintValue : DINT;
END_VAR

BEGIN
    (* [LSP 占位版本] FC_DINT_TO_TIME := T#0ms; *)

    (* [TIA Portal 版本 - 取消下面一行的注释] *)
    (* FC_DINT_TO_TIME := TIME(#DintValue * 1000); *)

    (* [CODESYS 版本 - 取消下面一行的注释] *)
    (* FC_DINT_TO_TIME := #DintValue * 1000; *)

    FC_DINT_TO_TIME := T#0ms;  (* 默认返回占位值 *)
END_FUNCTION
```

---

### 3️⃣ Log 模块 (`log/`)

#### 包含文件
- [FC_LogMsg.scl](log/FC_LogMsg.scl) - 日志消息函数

#### 功能差异

| 功能 | LSP 版本 | TIA/CODESYS 版本 |
|------|---------|------------------|
| 消息记录 | ✅ 支持 | ✅ 支持 |
| 循环缓冲区 | ✅ 32条 | ✅ 32条 |
| 格式化输出 | ❌ 仅原始消息 | ✅ `[LEVEL] Source: Message` |
| 日志级别显示 | ❌ 不支持 | ✅ DEBUG/INFO/WARN/ERROR |
| 来源信息 | ❌ 不显示 | ✅ 显示 |

#### 启用完整日志格式化

参见 `FC_LogMsg.scl` 文件头部注释中的完整实现代码。

---

### 5️⃣ Actuator 模块 (`actuator/`) 🆕

#### 包含文件
- FB_1011_CylinderControl.scl - 通用气缸控制（伸出/收回+超时+传感器冗余）
- FB_1012_ConveyorMotor.scl - 通用输送电机控制（正转/反转/慢速+安全门+VFD）

#### 设计理念
Actuator 模块封装了现场设备的基础执行逻辑，以"命令驱动"模式工作：
- **不自行决策**何时动作（由上层编排器决定）
- **只负责执行**命令并反馈执行结果（到位/超时/故障）
- **可跨项目复用**：任何需要气缸或电机控制的工站都可直接使用

#### 使用示例

**气缸控制:**
```pascal
VAR
    fbBlock : FB_1011_CylinderControl;
    bExtendCmd, bRetractCmd, bDone, bFault : BOOL;
END_VAR

fbBlock(i_bExtend := bExtendCmd,
        i_bRetract := bRetractCmd,
        i_bUpSensor := ...,
        i_bDownSensor := ...,
        i_iTimeoutMs := 3000,
        q_bIsExtended => ...,
        q_bTimeout => bFault);
```

**电机控制:**
```pascal
VAR
    fbMotor : FB_1012_ConveyorMotor;
    bFwd, bSafe, bVfdFault : BOOL;
END_VAR

fbMotor(i_bFwd := bFwd,
        i_bSafetyDoorOk := bSafe,
        i_bVfdFault := bVfdFault,
        q_bFwd => ...,
        q_bVfdAlarm => ...);
```

#### 详细文档
- [FB_1011 接口文档](actuator/PRD/接口文档_IFC-FB1011-CylinderControl-V7.0.0.md)
- [FB_1011 详细设计](actuator/PRD/详细设计说明书_DSN-FB1011-CylinderControl-V7.0.0.md)
- [FB_1012 接口文档](actuator/PRD/接口文档_IFC-FB1012-ConveyorMotor-V7.0.0.md)
- [FB_1012 详细设计](actuator/PRD/详细设计说明书_DSN-FB1012-ConveyorMotor-V7.0.0.md)

---
```

## 🚀 快速开始指南

### 在 Siemens LSP (VS Code) 中使用

1. **将 SysLib 复制到项目目录**
   ```bash
   cp -r SysLib your_project/
   ```

2. **配置 `.plc.json`** (可选，如果在项目内则不需要)
   ```json
   {
       "name": "YourProject",
       "libraries": []
   }
   ```

3. **调用定时器示例**
   ```pascal
   VAR
       timerA : FB_TON;
       bTrigger : BOOL;
       bDone : BOOL;
       diCount : DINT;
   END_VAR

   timerA(
       IN := bTrigger,
       PT := 500,        (* 500 ms (V3.0.0 起真实毫秒) *)
       Q => bDone,
       ET => diCount
   );
   ```

4. **编译并测试** - 应该无错误通过 ✅

### 移植到 TIA Portal

1. 打开每个 `.scl` 文件
2. 查找 `[多平台]` 注释标记
3. 按照移植指南修改类型和转换逻辑
4. 导入到 TIA Portal 项目
5. 编译验证

---

## ⚠️ 已知限制与解决方案

### 限制 1: TIME 类型精度
**问题**: LSP 版本的 Timer ET 输出是整数周期数，不是 TIME 类型
**影响**: HMI 显示时需要手动转换
**解决**: 在 HMI 脚本中添加 `ET * 10` (ms) 的转换

### 限制 2: Convert 函数返回占位值
**问题**: `FC_DINT_TO_TIME` 等函数在 LSP 中返回 0 或 T#0ms
**影响**: 不能依赖这些函数进行逻辑判断
**解决**:
- 开发阶段：直接使用数值运算
- 生产部署：启用平台特定实现

### 限制 3: Log 函数无格式化
**问题**: 日志不显示级别和来源信息
**影响**: 调试时可读性降低
**解决**: 在 Message 参数中手动包含上下文信息
```pascal
(* 推荐 *)
FC_LogMsg(Enable := TRUE, Level := 3,
    Source := 'FB_1001',
    Message := '[ERROR] FB_1001: 取料超时',  (* 手动格式化 *)
    ...);
```

---

## 📝 变更历史

### V2.0.0 (2026-05-02) - 平台兼容性优化
**重大变更:**
- ✅ 所有 Timer 模块移除 TIME↔DINT 转换
- ✅ Timer PT/ET 参数改为 DINT 类型
- ✅ Convert 函数改为占位实现
- ✅ Log 函数移除 CONCAT 操作
- ✅ 添加详细的多平台移植注释
- ✅ 创建本兼容性指南文档
- 🆕 V7.0.0: actuator/ 模块新增 (FB_1011 气缸控制 + FB_1012 电机控制)

**影响范围:**
- 向后不兼容 V1.0.0 (接口类型变更)
- 需要更新调用代码中的参数类型

### V1.0.0 (2026-05-01) - 初始版本
- 实现 IEC 标准定时器、计数器、边沿检测等功能
- 完整的 TIME 类型支持 (仅限 TIA Portal)

---

## 📚 相关文档

- [IEC 61131-3 国际标准](https://en.wikipedia.org/wiki/IEC_61131-3)
- [Siemens Language Support 扩展文档](VS Code 扩展市场)
- [TIA Portal 编程手册](西门子官方文档)
- [CODESYS 编程指南](CODESYS 官方文档)

---

## 💬 技术支持

如遇到问题或发现 bug：
1. 检查本文档的"已知限制"章节
2. 查看具体源文件的详细注释
3. 确认目标平台的语法要求
4. 联系开发团队获取帮助

---

**维护者**: PLC 开发团队
**许可证**: 项目内部使用
**最后校验**: 2026-05-02
