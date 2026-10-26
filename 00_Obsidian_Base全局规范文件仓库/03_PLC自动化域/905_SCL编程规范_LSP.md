---
spec_id: LSP-905
title: "SCL编程规范"
version: "V1.4.0"
domain: plc
lifecycle: stable
canonical_path: "00_Obsidian_Base全局规范文件仓库/03_PLC自动化域/905_SCL编程规范_LSP.md"
replaces: [DEV-801, DEV-810]
tags: ["SCL", "编程", "核心规范", "LSP", "DJ-2026-005实践"]
changelog:
  - version: V1.4.0
    date: 2026-10-26
    author: Claude
    changes: 新增 §3.6 下标起点：STRING 字符下标从 1 起（siemens-lsp 插件的要求），ARRAY 下界统一为 1（用户裁决，与 STRING 统一风格）；移植到实际 PLC 时按平台适配；数组示例改为下界 1；经用户 2026-10-26 批准
  - version: V1.3.0
    date: 2026-10-24
    author: Claude
    changes: 语法白名单新增 ENUM 枚举类型（§4.4）；经用户 2026-10-24 批准
  - version: V1.2.0
    date: 2026-08-25
    author: Codex
    changes: 删除 METHOD 教程并改为禁用规则；统一与 plc-electrical-engineer / LSP-906 的白名单口径
  - version: V1.2.1
    date: 2026-08-26
    author: Codex
    changes: 补充 ARRAY 命名示例，明确数组变量统一使用 arr 类型标识
  - version: V1.1.0
    date: 2026-08-09
    author: Antigravity AI
    changes: 基于 DJ-2026-005 标杆项目经验融入 OB1 5行瘦身规约、VAR_IN_OUT 结构体整块传递模式、传感器动态消抖与 .scltest 4标段测试 SOP
---

# SCL 编程规范 (Siemens LSP 兼容版)

> 版本：V1.4.0
> 状态：已验证（§4.4 ENUM 为新增语法，待本机插件与目标平台验证，验证前不得用于交付）
> 更新日期：2026-10-26
> 适用环境：Siemens LSP (VS Code)、TIA Portal、CODESYS、GX Works

---

## 1. 核心规则概览

| 规则类别 | 核心要求 | 状态 |
|----------|----------|------|
| **语法白名单** | **除本规范明确列出的语法外，禁止使用任何其他SCL/IEC语法特性**（含GOTO、标签、REPEAT、指针等未列出项） | ❌ 禁止 |
| METHOD语法 | **Siemens LSP 与本工作空间白名单均禁用 `METHOD/METHODS/END_METHOD`**，需改用 FB 主体、FC 或独立 FB | ❌ 禁止 |
| 变量命名 | 小驼峰命名，英文为主 | ✅ 强制 |
| 注释格式 | 使用 `//` 或单层 `(* *)` | ✅ 强制 |
| 标点符号 | 必须使用英文半角标点 | ✅ 强制 |
| 定时器调用 | 必须包含完整参数(IN/PT/Q/ET)，Q参数不能为空 | ✅ 强制 |
| VAR_TEMP位置 | 必须在VAR块中定义，不能在程序中间定义 | ✅ 强制 |
| GOTO/标签 | **Siemens LSP不支持GOTO和标签语法**，必须用IF-ELSE替代 | ❌ 禁止 |

---

## 2. METHOD 禁用与替代模式

### 2.1 禁用规则

- 禁止在项目代码中声明 `METHOD`、`METHODS`、`END_METHODS`、`END_METHOD`
- 禁止保留旧模板中的 `CALL_XXX` 风格子程序残留
- 需要拆分逻辑时，按以下优先级选择替代方式：
  1. 仍属于单个 FB 的扫描逻辑：保留在 FB 主体内，用 `CASE/IF` + 区域注释分段
  2. 可复用的纯计算逻辑：提取为 `FC_xxxx_*`
  3. 带状态保持的独立子设备：提取为独立 `FB_xxxx_*`

### 2.2 替代示例

**❌ 禁止写法**
```scl
METHOD AutoModeStateMachine : VOID
    // 方法实现...
END_METHOD
```

**✅ 推荐写法 1：在 FB 主体内按区域分段**
```scl
CASE s_iStep OF
    0:
        // 初始化
    10:
        // 自动模式步序
ELSE
    s_iStep := 0;
END_CASE;
```

**✅ 推荐写法 2：提取为独立 FC**
```scl
s_rCurrentSpeed := FC_1001_CalculateSpeed(
    i_rTargetSpeed := i_rTargetSpeed,
    i_rActualSpeed := i_rActualSpeed
);
```

---

## 3. 变量与结构体命名规范

### 3.1 变量作用域前缀约定 (Scope Prefixes)

| 前缀 | 含义 | 作用域 (Declaration Block) | 示例 |
|------|------|---------------------------|------|
| `i_` | Input - 输入变量 | `VAR_INPUT` | `i_bStart`, `i_rSpeedSetpoint` |
| `o_` | Output - 输出变量 | `o_VAR_OUTPUT` | `o_bRunning`, `o_iErrorCode` |
| `io_` | InOut - 双向变量 / UDT 结构体 | `VAR_IN_OUT` | `io_stConveyor`, `io_stAxisState` |
| `q_` | Query - 查询/只读状态输出 | `VAR_OUTPUT` (Read-only) | `q_bIsReady`, `q_dElapsedTime` |
| `s_` | Static/Internal - 内部静态变量 | `VAR` (FB 内部静态存储) | `s_bInitialized`, `s_iCurrentStep` |
| `temp_` / `t_` | Temp - 临时变量 (单次扫描有效) | `VAR_TEMP` | `temp_iIndex`, `t_rCalculatedValue` |
| `fb_` | Function Block Instance - 功能块实例 | `VAR` | `fb_tActionTimer`, `fb_ConveyorControl` |
| `CONST_` | Constant - 常量 | `VAR CONSTANT` | `CONST_MAX_SPEED`, `CONST_TIMEOUT_MS` |

---

### 3.2 数据类型二级标识约定 (Type Identifiers)

前缀之后紧跟数据类型简写（小写字母），再使用大驼峰风格拼接变量功能名：

| 数据类型标识 | 对应数据类型 | 示例 |
|-------------|-------------|------|
| `b` | `BOOL` | `i_bStart`, `s_bRunning`, `o_bAlarm` |
| `i` | `INT` | `i_iMaxCycle`, `s_iCurrentStep` |
| `di` / `d` | `DINT` (毫秒/计数/长整型) | `i_dDebounceMs`, `s_diEncoderPulse` |
| `r` | `REAL` | `i_rTargetPos`, `s_rCurrentSpeed` |
| `w` | `WORD` | `i_wControlWord`, `o_wStatusWord` |
| `dw` | `DWORD` / `LWORD` | `s_dwStateMask` |
| `st` | `ST_` UDT 结构体实例 | `io_stLayer`, `s_stAxisStatus` |
| `e` | `ENUM` 枚举类型 | `s_eState`, `i_eMode` |
| `arr` | `ARRAY` 数组类型 | `s_arrSensors`, `temp_arrData`, `s_arrMesAlarmQueue` |

> **数组命名补充说明**：即使数组元素类型为 `INT` / `BOOL` / `WORD`，变量名仍统一使用 `arr` 作为二级类型标识，再在语义名中体现元素含义；例如 `s_arrMesAlarmQueue : ARRAY[1..10] OF INT;`、`s_arrStationAlarmStatus : ARRAY[1..3] OF INT;`。禁止写成 `s_ai...`、`s_ab...` 之类未在本规范登记的组合缩写。

---

### 3.3 UDT / 结构体命名规范 (User Defined Types)

1. **`ST_` 统一前缀**：所有自定义数据类型（UDT）和结构体必须使用 `ST_` 前缀，并采用大驼峰 (UpperCamelCase) 拼写。
2. **正确示例**：
   - `ST_SingleLayerConveyor` (单层输送机状态结构体)
   - `ST_ServoAxis` (伺服轴控制结构体)
   - `ST_AlarmInfo` (报警数据结构体)

---

### 3.4 FB / FC 模块命名与编号规范

1. **模块命名格式**：`FB_[4位编号]_[模块/设备英文名]_[项目/工站名]`
2. **编号划分标准**：
   - `FB_1001 ~ FB_1999`：工站与单机机构控制 FB（如 `FB_1002_SingleLayerConveyor_BufferFraming`）
   - `FB_2001 ~ FB_2999`：公共服务 FB（如 `FB_2001_CommonAlarm_AllStation` 报警管理）
   - `FB_1011 ~ FB_1099`：基础执行器 FB（如 `FB_1011_CylinderControl` 气缸控制库）
3. **FC 命名格式**：`FC_[4位编号]_[功能函数英文名]`（如 `FC_1001_CalculateCRC`）

---

### 3.5 变量命名示范与禁令

```scl
// ✅ 正确规范示例 - 严格遵循前缀 + 类型标识 + 小驼峰
VAR_INPUT
    i_bStart : BOOL;                // 启动信号
    i_rSpeedSetpoint : REAL;        // 速度设定值
    i_dDebounceMs : DINT;           // 传感器消抖毫秒值
END_VAR

VAR_IN_OUT
    io_stConveyor : ST_SingleLayerConveyor; // 统一传递 UDT 结构体
END_VAR

VAR_OUTPUT
    o_bRunning : BOOL;              // 运行状态
    o_iErrorCode : INT;             // 错误代码
END_VAR

VAR
    s_bInitialized : BOOL;          // 内部静态初始化标志
    s_iCurrentStep : INT;           // 状态机当前步序
    s_arrMesAlarmQueue : ARRAY[1..10] OF INT; // 数组统一使用 arr 类型标识；下界为 1（§3.6）
    fb_tActionTimer : FB_TON;       // TON 定时器实例
END_VAR

VAR_TEMP
    temp_iLoopIndex : INT;          // 临时循环索引
END_VAR

// ❌ 禁止项 - 严格判定为 Error
VAR
    运行标志 : BOOL;                 // 禁止：中文变量名
    i_b_start : BOOL;               // 禁止：多余下划线（应为 i_bStart）
    bStart : BOOL;                  // 禁止：缺少作用域前缀 i_
    s_iCurrentStep_V2 : INT;        // 禁止：变量名带版本号后缀
END_VAR
```

---

### 3.6 数组与字符串的下标起点（V1.4.0 新增）

**STRING 字符下标从 1 起，这是 siemens-lsp 插件的要求；ARRAY 下界统一为 1，这是用户 2026-10-26 的裁决，为与 STRING 下标统一风格（插件本身也接受从 0 起的数组）。移植到实际 PLC 时按平台适配。**

| 对象 | 规定 | 示例 |
|------|------|------|
| `ARRAY` 声明 | 下界一律写 1，元素个数等于上界 | `s_arrMesAlarmQueue : ARRAY[1..10] OF INT;` |
| 数组遍历 | `FOR` 从 1 到上界 | `FOR t_iIdx := 1 TO 10 DO ... END_FOR;` |
| `STRING` 按字符读写 | 第一个字符是 `s[1]`，n 个字符的字符串到 `s[n]` 为止，不写 `s[0]` | `s_sId[1]` 是第一个字符 |

- **依据**：STRING——Siemens 语言服务插件按 S7 规则解释字符下标，按 0 起写的字符串在插件 test 里会错位（DJ-2026-009 FB_3002 的 Modbus 用例实测：高字节丢失、读回少第一个字符）。ARRAY——用户 2026-10-26 裁决，为与 STRING 统一风格。
- **移植到实际 PLC**：目标平台若按别的规则（例如 InoProShop 的 STRING 下标起点尚待在目标平台上核实），在移植时按平台适配并在项目的技术方案文档里写明适配方式；不得为迁就目标平台而在仓库源码里改回 0 起。
- **已有代码**：碰到时按本节改写，并补插件 test 用例证明结果不变。

---

## 4. 语法规则速查

> **⚠️ 语法白名单原则**：本节列出的语法为**唯一允许使用的SCL语法集合**。凡未在本规范中明确列出的语法特性（包括但不限于 GOTO/标签、REPEAT、指针运算 `^` / `ADR` / `REF_TO`、联合体 UNION、变体 VARIANT 等），一律禁止使用。如需使用新语法，必须先更新本规范并获得评审通过。

### 4.1 块结构

```scl
// FUNCTION_BLOCK 结构
FUNCTION_BLOCK FB_Example
VAR_INPUT
    // 输入变量声明
END_VAR
VAR_OUTPUT
    // 输出变量声明
END_VAR
VAR
    // 内部变量声明
END_VAR
VAR_TEMP
    // 临时变量声明（每次扫描复位）
END_VAR
BEGIN
    // 主程序逻辑
    CASE s_iStep OF
        0:
            // 初始化
        10:
            // 运行逻辑
    ELSE
        s_iStep := 0;
    END_CASE;
END_FUNCTION_BLOCK

// FUNCTION 结构
FUNCTION FC_1001_CalculateValue : REAL
VAR_INPUT
    i_rInput : REAL;
END_VAR
BEGIN
    FC_1001_CalculateValue := i_rInput * 1.5;
END_FUNCTION
```

### 4.2 控制结构

```scl
// IF-THEN-ELSE
IF Condition THEN
    // 逻辑1
ELSIF AnotherCondition THEN
    // 逻辑2
ELSE
    // 逻辑3
END_IF;

// CASE 语句
CASE iValue OF
    0:  // 分支0
    1:  // 分支1
    2:  // 分支2
ELSE
    // 默认分支
END_CASE;

// FOR 循环
FOR i := 0 TO 10 BY 1 DO
    // 循环体
END_FOR;

// WHILE 循环
WHILE Condition DO
    // 循环体
END_WHILE;
```

### 4.3 定时器调用规范

```scl
// ✅ 正确 - 完整参数调用, PT 使用 DINT 类型(扫描周期数)
fb_tActionTimer.IN := FALSE;
fb_tActionTimer.PT := 500;
fb_tActionTimer(IN := fb_tActionTimer.IN, PT := fb_tActionTimer.PT,
                 Q => s_bTimer_Q, ET => q_eElapsed);

// ❌ 错误 - 使用 TIME 字面量(LSP 不支持 TIME 类型)
fb_tActionTimer(IN := FALSE, PT := T#500ms, Q => s_bTimer_Q, ET => q_eElapsed);

// ❌ 错误 - 缺少 Q 参数
fb_tActionTimer(IN := FALSE, PT := 500, Q => , ET => q_eElapsed);
```

> **重要**：定时器调用必须包含所有参数（IN、PT、Q、ET），Q 参数不能省略。PT 参数必须使用 DINT 类型（扫描周期数），禁止使用 TIME 字面量（如 `T#500ms`）。详见 903_定时器使用规范。

---

### 4.4 ENUM 枚举类型（V1.3.0 新增，待验证）

步序、模式、状态等有限取值的变量，允许用枚举，成员带**显式数值**（便于和 HMI、测试、报警码对照），变量用 `e` 二级标识（见 §3.2）。各平台声明语法不同，**项目在方案文档里写明目标平台用哪一种**：

```scl
// 形式 A：IEC 61131-3 枚举（CODESYS / InoProShop 等）
TYPE E_ConveyorStep :
(
    STEP_IDLE := 0,
    STEP_INIT_WAIT := 1,
    STEP_SEND_ON := 10
);
END_TYPE

// 形式 B：TIA Portal V20+ 命名值类型（Named Value Type）
// 必须带基础类型和默认值，类型放在软件单元的 .nvt 文件里，成员值显式给出：
// E_ConveyorStep : Int ( STEP_IDLE := 0, STEP_INIT_WAIT := 1, STEP_SEND_ON := 10 ) := STEP_IDLE
// 具体写法以 TIA 文档“Named value data types (S7-1500)”为准，项目落地时先在 TIA 里建一个样例确认。

// 使用（形式 A 示例）
s_eStep : E_ConveyorStep;
CASE s_eStep OF
    E_ConveyorStep#STEP_IDLE:
        // 待机
ELSE
    s_eStep := E_ConveyorStep#STEP_IDLE;
END_CASE;
```

约定：
- 类型名 `E_` + 大驼峰；成员名全大写加下划线，带模块前缀；成员值必须显式给出，不得依赖默认编号。
- CASE 仍必须有 `ELSE`（STD-850）。
- 不得对枚举变量做算术运算；与 INT 的互转只在 HMI / 报警码出口处做，且注明。
- **只用于支持枚举的平台**：CODESYS 系（InoProShop 等）用形式 A；TIA Portal 用形式 B（命名值类型，需 V20+），低版本 TIA 回退 `INT` + `VAR CONSTANT`。
- **验证现状**：驾驶舱 SclLinter 已验证认得形式 A、无误报（审计 130）；Siemens 语言服务插件与目标平台编译待用户本机验证。
- **前置验证**：Siemens 语言服务插件与驾驶舱 SclLinter 对所选形式的解析，以及目标平台能否编译，需在用户本机验证；验证不通过的项目回退为 `INT` + `VAR CONSTANT` 命名常量，数值不变。验证通过后把本节标题的“待验证”去掉。

---

## 4.5 OB1 顶级调度器瘦身规约 (基于DJ-2026-005实践)

1. **OB1 职责单一化**：`OB1.scl` 仅作为最高层级的程序入口，必须保持极简（**行数控制在 10 行以内**）。
2. **禁止裸逻辑**：严禁在 OB1 中编写具体的逻辑分支、条件转移、气缸控制或散装 I/O 映射。
3. **标准 OB1 示例**：
   ```scl
   // ✅ 正确示例 - DJ-2026-005 5行顶级调度模式
   fb_ExternalInteraction(io_stExternal := db_GlobalVars.stExternal);
   fb_SingleLayerConveyor(io_stConveyor := db_GlobalVars.stConveyor);
   fb_PickPlace(io_stPickPlace := db_GlobalVars.stPickPlace);
   fb_GlueFeeder(io_stGlueFeeder := db_GlobalVars.stGlueFeeder);
   fb_CommonAlarm(io_stAlarm := db_GlobalVars.stAlarm);
   ```

## 4.6 VAR_IN_OUT 结构体整块传递架构 (基于DJ-2026-005实践)

1. **具名 UDT 替代散装形参**：对于复杂的工站级功能块（FB），禁止声明几十个散装的 `VAR_INPUT` / `VAR_OUTPUT` 变量，统一使用具名 UDT 结构体通过 `VAR_IN_OUT` 双向整块传递。
2. **结构体传递示例**：
   ```scl
   FUNCTION_BLOCK FB_1002_SingleLayerConveyor_BufferFraming
   VAR_IN_OUT
       io_stConveyor : ST_SingleLayerConveyor; // 统一通过 VAR_IN_OUT 传递 UDT
   END_VAR
   ```
3. **核心优势**：消除接口繁琐配置，提高 PLC 扫描效率，避免全局变量直接穿透导致的耦合。

## 4.7 传感器动态消抖与抗干扰规约 (基于DJ-2026-005 V9.1.0实践)

1. **物理信号滤波**：所有来自现场光电开关、接近开关、行程开关的物理输入，在进入状态机转移逻辑判断前，必须配置消抖参数。
2. **消抖形参格式**：消抖时间参数统一使用 `i_dDebounceMs : DINT`（单位：毫秒）。
3. **滤波实现**：
   ```scl
   fb_DebounceTimer(
       IN := i_bPhotoEyeSensor,
       PT := i_dDebounceMs,
       Q => s_bFilteredSensor,
       ET => s_dEt
   );
   ```

## 4.8 .scltest 4标段智能测试 SOP (基于DJ-2026-005实践)

所有 PLC 功能块在提交或交付前，必须在 `.scltest` 测试用例中覆盖以下 4 个标准标段：
1. **基本功能标段 (Basic)**：验证正常初始化、手动/自动模式切换与基本使能。
2. **状态转移标段 (State Transition)**：验证 CASE 状态机各 Step 顺序转移逻辑。
3. **边界与超时标段 (Boundaries & Timeouts)**：验证动作超时报警（如气缸到位超时 `tTimeout`）与极值边界。
4. **异常与防错标段 (Errors & Anti-Fault)**：验证急停、安全门断开、传感器掉线等突发故障下的复位与安全封锁。

---

## 5. Siemens LSP 插件兼容规范

| 错误代码 | 错误信息 | 原因 | 解决方法 |
|----------|----------|------|----------|
| PS001 | `unexpected token "METHOD"` | 使用了 LSP 不支持的 METHOD 语法 | 删除 METHOD，改为 FB 主体逻辑或独立 FC/FB |
| PS002 | `missing Q parameter in TON call` | 定时器调用缺少Q参数 | 添加Q参数变量 |
| LX003 | `unexpected token ，` | 使用了中文标点 | 替换为英文标点 |
| TC100 | `cannot assign INT to TIME` | INT直接赋值给TIME | 使用DINT存储毫秒值 |

### 5.3 代码检查命令

```bash
# 在项目根目录运行代码检查
plccheck .

# 检查特定文件
plccheck feeder/FB_1004_GlueMachineFeeder_BufferFraming.scl

# 输出详细错误信息
plccheck --verbose .
```

---

## 5. Siemens LSP 插件使用指南

### 5.1 插件配置

在 VS Code 中配置 `.vscode/settings.json`：

---

## 6. 注释规范

### 6.1 注释格式

```scl
// ✅ 推荐 - 单行注释
// 功能块: 打胶机送料机构
// 描述: 控制X2轴取料和返回动作

(* ✅ 允许 - 多行注释（不嵌套）
 ============================================================================
 功能块名称: FB_1004_GlueMachineFeeder_BufferFraming
 描述: 打胶机送料机构 - 边框缓存机项目专用
 版本: V1.0.0
 ============================================================================
*)

// ❌ 禁止 - 嵌套注释
(* 外层注释
   (* 内层注释 *)   // 错误：嵌套
*)
```

### 6.2 注释密度要求

| 代码位置 | 注释要求 |
|----------|----------|
| 文件头部 | 必须有功能描述和版本信息 |
| 变量声明 | 每个I/O变量必须有注释 |
| FC/FB | 必须有功能说明 |
| 关键逻辑 | IF/CASE分支必须有注释 |
| 复杂计算 | 计算前后必须有注释 |

---

## 7. 代码审查检查清单

| 检查项 | 说明 |
|--------|------|
| [ ] 未使用 METHOD 语法 | 无 `METHOD/METHODS/END_METHODS/END_METHOD` |
| [ ] 变量名符合命名规范 | 前缀正确，小驼峰 |
| [ ] 无中文变量名 | 全部使用英文 |
| [ ] 定时器调用完整 | IN、PT、Q、ET参数齐全 |
| [ ] 标点符号正确 | 使用英文半角标点 |
| [ ] 注释格式正确 | 无嵌套注释 |
| [ ] 无GOTO/标签语法 | LSP不支持，必须用IF-ELSE替代 |
| [ ] 语法白名单合规 | 仅使用§4明确列出的语法，无未列出的语法特性 |
| [ ] 语法检查通过 | `plccheck`无错误 |

---

## 8. 版本历史

| 版本 | 日期 | 作者 | 变更内容 |
|------|------|------|----------|
| V1.4.0 | 2026-10-26 | Claude | 新增 §3.6 下标起点：STRING 字符下标从 1 起（siemens-lsp 要求）、ARRAY 下界为 1（用户裁决，统一风格）；移植时按平台适配；用户 2026-10-26 批准；数组示例改为下界 1 |
| V1.3.0 | 2026-10-24 | Claude | 新增 §4.4 ENUM 枚举类型（DJ-2026-005 步序用枚举；验证前置见 §4.4） |
| V1.2.1 | 2026-08-26 | Codex | 补充 ARRAY 命名示例，明确数组变量统一使用 arr 类型标识 |
| V1.2.0 | 2026-08-25 | Codex | 删除 METHOD 教程并改为禁用规则；统一与 plc-electrical-engineer / LSP-906 的白名单口径 |
| V1.0.3 | 2026-06-21 | AI Assistant | 修正§4.3定时器示例: PT参数从TIME字面量(T#500ms)改为DINT类型(500), 与903/906对齐(C-01) |
| V1.0.0 | 2026-05-04 | AI Assistant | 初始版本，基于DJ-2026-005项目验证 |
| V1.0.2 | 2026-05-29 | AI Assistant | 新增§4.3跳转语句规范(禁止GOTO+标签)；新增§4语法白名单原则(除列出项外一律禁止)；修复FB_1020中GOTO重构为IF-ELSE |

---

## 9. 相关文档

- [[903_定时器使用规范_LSP]]
- [[904_SCL注释规范_LSP]]
- [[906_错误预防规则_LSP]]
- [[907_项目配置规范_LSP]]
- [[908_Siemens_Language_Support_使用指南_TOOL]]
- IEC 61131-3 编程规范
