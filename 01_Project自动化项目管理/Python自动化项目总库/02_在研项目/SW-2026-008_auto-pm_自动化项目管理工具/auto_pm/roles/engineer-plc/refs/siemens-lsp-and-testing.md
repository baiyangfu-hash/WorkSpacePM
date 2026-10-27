# Siemens LSP 插件扩展与单元测试指南 (refs/siemens-lsp-and-testing.md)

本参考指南专为 **Dynamic Siemens Language Support** 扩展插件（`DynamicEngineering.vscode-siemens` / danielv123）与 **西门子 TIA Portal (S7-1200/S7-1500) SCL** 开发定制，并适配本地 008 工具 (`auto-pm`) 自动化体系。

---

## 1. Dynamic Siemens Language Support 配置指南 (`.plc.json`)

插件通过 `.plc.json` 实现多 PLC 项目的**类型作用域隔离（Isolated Type Scope）**，避免不同 PLC 项目在同一 VS Code 工作区中发生类型冲突或符号重名。

### 1.1 项目物理架构与路径规则

西门子 SCL 项目在实际工作区中分为两类物理结构，`.plc.json` 中的 `libraries` 必须根据相对路径准确指向 `SysLib` 等公共库根目录：

#### A. 单层/公共库工程结构 (如 `SysLib` / `DJ-2026-000`)
`.plc.json` 位于项目根目录：
```json
{
  "name": "DJ-2026-000",
  "description": "SysLib公共库FB测试套件",
  "version": "2.0.0",
  "libraries": [
    "../01_SharedLibraries/SysLib"
  ]
}
```

#### B. 标准多级工程结构 (如 `DJ-2026-005 边框缓存机`)
`.plc.json` 位于 `02_PLC程序/PLC_ST/` 子目录下：
```json
{
  "name": "DJ-2026-005",
  "description": "边框缓存机 PLC 控制系统",
  "version": "V7.1.1",
  "libraries": [
    "../../../01_SharedLibraries/SysLib"
  ]
}
```

> 🔴 **配置硬规则**：
> 1. 字段名必须是 `libraries`（不得拼错为 `libraryDirectories` 等无效字段）。
> 2. 路径分隔符必须使用正斜杠 `/`。
> 3. 当项目调用 SysLib 4. **注释分工与嵌套禁令 (由 `doc check` 静态门禁强卡)**：
   - 变量与行内注释必须使用 `//`。
   - 逻辑块与流程注释使用 `(* ... *)`。
   - 严禁嵌套注释 `(* (* ... *) *)`，且注释内禁止使用中文全角标点。
   - 源码必须保持 ≥10% 注释覆盖率，由 `python -m auto_pm doc check` 强制校验。
5. **极性与输出所有权**：
   - 信号映射必须使用显式 `IF/ELSE` 表达，禁止隐式 `NOT` 缩写。
   - 关键输出/报警在 `.scl` 中必须保持单一 Owner（变量前缀遵循 `LSP-905 §3` 小驼峰与 `q_` 前缀）。

---

## 3. `.scltest` 单元测试框架与终端动态运行

**Dynamic Siemens Language Support** 插件内置了针对西门子 SCL 功能块的 DSL 单元测试框架，测试文件存放在各项目的 `Test/` 目录下（如 `DJ-2026-005/02_PLC程序/PLC_ST/Test/`）。

### 3.1 `.scltest` 语法规范

```st
// ============================================================================
// 气缸控制 FB 单元测试集: FB_1011_CylinderControl.scltest
// ============================================================================

TEST_CASE "气缸伸出动作与超时报警测试"
    // 1. 初始化测试输入环境
    SET GlobalVars.stCylinder.i_bEnable := TRUE;
    SET GlobalVars.stCylinder.i_bAutoMode := TRUE;
    SET GlobalVars.stCylinder.i_bWorkSensor := FALSE;
    SET GlobalVars.stCylinder.i_bHomeSensor := TRUE;
    
    // 2. 触发伸出命令
    SET GlobalVars.stCylinder.i_bCmdWork := TRUE;
    WAIT_CYCLES 2;
    
    // 3. 断言伸出阀输出已开启
    ASSERT GlobalVars.stCylinder.o_bWorkValve = TRUE;
    ASSERT GlobalVars.stCylinder.o_bHomeValve = FALSE;
    
    // 4. 模拟传感器到位
    SET GlobalVars.stCylinder.i_bHomeSensor := FALSE;
    SET GlobalVars.stCylinder.i_bWorkSensor := TRUE;
    WAIT_CYCLES 2;
    
    // 5. 断言到位状态
    ASSERT GlobalVars.stCylinder.o_bWorkDone = TRUE;
    ASSERT GlobalVars.stCylinder.o_bAlarm = FALSE;
END_TEST_CASE
```

### 3.2 终端控制台动态测试 (`auto-pm plc test`)

为解决在终端控制台中无硬件测试调用的痛点，008 工具集成底层 `siemens-lsp` 解释引擎：
- 运行命令：`auto-pm plc test <项目ID>`
- **模拟机制**：在内存中建立 SCL 虚拟扫描周期（Scan Cycles），在控制台中直接打印逐条 `TEST_CASE` 的 PASS/FAIL 日志。

---

## 4. 共享库 (SysLib) 依赖与 Breaking Change 预警

1. **依赖图谱**：公共库 `SysLib` 被多层级工程（如 `DJ-2026-000` / `DJ-2026-005`）共同引用。
2. **Breaking Change 隔离规则**：
   - 当修改 `SysLib` 下的 FB（如 `FB_1011` / `FB_1012`）或结构体（如 `ST_Cylinder`）时，**必须先查阅全局依赖引用**。
   - 修改 FB 引脚后，必须运行 `auto-pm plc check` 扫描上层引用工程，确保调用的 `OB1` 与底层 FB 保持强类型与版本一致。

---

## 5. 本地 LSP 验证与工程分工边界 (AI 本地 LSP 验证 vs 现场/硬件)

为了确保工程交付的高效与严谨，项目建立清晰的 Pair Programming 验证边界：

### 5.1 验证职责划分表

| 验证领域 | 验证主体 | 验证工具 / 方法 | 验证内容与输出 |
|---|---|---|---|
| **本地 LSP 语法诊断** | **AI 智能体** | Siemens LSP (VS Code) + `view_file` | 检查 SCL 语法、标识符前缀（`i_`/`q_`/`s_`）、禁用 METHOD、定时器 `PT`/`ET` 为 `DINT` 毫秒、注释分工 |
| **工程配置与合规** | **AI 智能体** | `auto-pm plc check <PID> --json` | 校验 `.plc.json` 路径、SysLib 依赖映射、Spec Snapshot、PM_SESSION 结构完整性 |
| **文档与注释门禁** | **AI 智能体** | `auto-pm doc check` | 校验 SCL 注释覆盖率（AST扫描）、`TEC.md`/`USAGE.md` 存在性与 TODO 清零状态 |
| **单元测试与 DSL** | **AI 智能体** | `auto-pm plc test <PID>` + `.scltest` | 在 `Test/` 目录编写/排查 `TEST_CASE`, `RESET` 块，执行无硬件控制台动态推演 |
| **变更与台账闭环** | **AI 智能体** | `auto-pm change` + `ledger reconcile` | 自动管理 CHG 变更单并与版本变更台帐对账 |
| **TIA Portal 全量编译** | **用户** | Siemens TIA Portal V16/V17/V18 | 工程导入、官方 SCL 语法/链接编译器全量编译、硬件组态校验 |
| **真实硬件 / 现场调试** | **用户** | 实体 PLC (S7-1200/1500) / PLCSIM 虚拟机 | 现场以太网通信、伺服/气缸物理动作推演、安全门/急停物理回路调试 |

### 5.2 本地 LSP 验证执行标准化流程

智能体在执行“本地 LSP 验证”任务时，必须严格执行以下五步：
1. **008 配置与语法检测**：运行 `auto-pm plc check <PID> --json` 检查物理配置与语法白名单。
2. **文档与注释达标检测**：运行 `auto-pm doc check` 验证注释率与核心文档非空。
3. **SCL 源码查阅**：先通过 `view_file` 阅读目标 `.scl` 声明，核对极性与类型。
4. **.scltest 用例审查与测试**：运行 `auto-pm plc test <PID>` 审查 `Test/` 目录下 `.scltest` 文件的测试覆盖率与重置段。
5. **台账对账**：若涉及变更，运行 `auto-pm ledger reconcile <PID>` 确保闭环。��（Scan Cycles），在控制台中直接打印逐条 `TEST_CASE` 的 PASS/FAIL 日志。

---

## 4. 共享库 (SysLib) 依赖与 Breaking Change 预警

1. **依赖图谱**：公共库 `SysLib` 被多层级工程（如 `DJ-2026-000` / `DJ-2026-005`）共同引用。
2. **Breaking Change 隔离规则**：
   - 当修改 `SysLib` 下的 FB（如 `FB_1011` / `FB_1012`）或结构体（如 `ST_Cylinder`）时，**必须先查阅全局依赖引用**。
   - 修改 FB 引脚后，必须运行 `auto-pm plc check` 扫描上层引用工程，确保调用的 `OB1` 与底层 FB 保持强类型与版本一致。

---

## 5. 本地 LSP 验证与工程分工边界 (AI 本地 LSP 验证 vs 现场/硬件)

为了确保工程交付的高效与严谨，项目建立清晰的 Pair Programming 验证边界：

### 5.1 验证职责划分表

| 验证领域 | 验证主体 | 验证工具 / 方法 | 验证内容与输出 |
|---|---|---|---|
| **本地 LSP 语法诊断** | **AI 智能体** | Siemens LSP (VS Code) + `view_file` | 检查 SCL 语法、标识符前缀（`i_`/`q_`/`s_`）、禁用 METHOD、定时器 `PT`/`ET` 为 `DINT` 毫秒、注释分工 |
| **工程配置与合规** | **AI 智能体** | `auto-pm plc check <PID> --json` | 校验 `.plc.json` 路径、SysLib 依赖映射、Spec Snapshot、PM_SESSION 结构完整性 |
| **单元测试与 DSL** | **AI 智能体** | `auto-pm plc test <PID>` + `.scltest` | 在 `Test/` 目录编写/排查 `TEST_CASE`, `RESET` 块，执行无硬件控制台动态推演 |
| **变更与台账闭环** | **AI 智能体** | `auto-pm change` + `ledger reconcile` | 自动管理 CHG 变更单并与版本变更台帐对账 |
| **TIA Portal 全量编译** | **用户** | Siemens TIA Portal V16/V17/V18 | 工程导入、官方 SCL 语法/链接编译器全量编译、硬件组态校验 |
| **真实硬件 / 现场调试** | **用户** | 实体 PLC (S7-1200/1500) / PLCSIM 虚拟机 | 现场以太网通信、伺服/气缸物理动作推演、安全门/急停物理回路调试 |

### 5.2 本地 LSP 验证执行标准化流程

智能体在执行“本地 LSP 验证”任务时，必须严格执行以下四步：
1. **008 工具检测**：运行 `auto-pm plc check <PID> --json` 检查物理配置。
2. **SCL 源码查阅**：先通过 `view_file` 阅读目标 `.scl` 声明，核对极性与类型。
3. **.scltest 用例审查与测试**：运行 `auto-pm plc test <PID>` 审查 `Test/` 目录下 `.scltest` 文件的测试覆盖率与重置段。
4. **台账对账**：若涉及变更，运行 `auto-pm ledger reconcile <PID>` 确保闭环。
