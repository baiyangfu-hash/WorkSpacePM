---
alwaysApply: true
---

# PLC自动化技术栈规则

## 规范权威位置

所有PLC技术栈规范的权威目录: `00_Obsidian_Base全局规范文件仓库/03_PLC自动化域/`

规范注册表: `00_Obsidian_Base全局规范文件仓库/spec_registry.json`

### 核心规范清单

| 优先级 | 规范ID | 文件 | 说明 |
|--------|--------|------|------|
| 🔴必读 | LSP-905 | 905_SCL编程规范_LSP.md | 主规范: 命名/语法/METHOD/代码结构/跳转语句 |
| 🔴必读 | LSP-907 | 907_项目配置规范_LSP.md | .plc.json配置 + 目录结构 |
| 🟡配套 | LSP-904 | 904_SCL注释规范_LSP.md | 注释格式/嵌套禁令/标点规则 |
| 🟡配套 | LSP-903 | 903_定时器使用规范_LSP.md | 定时器用TIA原生TON_TIME等, PT/ET为TIME（V3.0.0起） |
| 🟠重要 | LSP-906 | 906_错误预防规则_LSP.md | 实战bug总结检查清单 |
| 🟢参考 | PLC-023 | 023_PLC程序设计文档模板_PLC.md | 程序设计文档标准模板 |
| 🟢参考 | INT-815 | 815_PLC接口文档模板_INT.md | FB/FC接口文档标准格式 |
| 🟢参考 | TOOL-908 | 908_Siemens_Language_Support_使用指南_TOOL.md | LSP插件使用指南 |

### 已废弃规范（禁止使用）

| 废弃ID | 替代规范 | 说明 |
|--------|----------|------|
| DEV-801 | LSP-905 | 变量命名规范已被905§3覆盖，采用小驼峰风格 |
| DEV-802 | LSP-905 | 工作流命名规范已被905覆盖 |
| DEV-810 | LSP-905 | PLC综合规范已被905+904+903拆分替代 |
| LSP-903-OLD | LSP-903 | Go-Gen纯逻辑定时器方案，后切换到FB_TON共享库，V3.0.0起改用TIA原生定时器 |

## 关键编码规则

### .plc.json配置

1. 库引用字段名必须是 `libraries`（不是 `libraryDirectories`，后者不是有效字段名）
2. 引用外部共享库时使用相对路径指向库根目录
3. 路径分隔符使用 `/`（正斜杠）
4. 当项目使用SysLib中的功能块时必须配置libraries字段

### SCL编码

5. 变量命名采用小驼峰风格（905规范§3），如 `i_bStart` 而非 `i_bStartButton`
6. Siemens LSP插件不支持METHOD语法，需改用普通代码块
7. 注释必须使用英文半角标点，禁止中文标点（904规范）
8. 注释禁止嵌套 `(* (* *) *)`（904规范）
9. VAR_TEMP必须在VAR块中定义，不能在程序中间定义
10. 🔴 **调用任何 SysLib FB 前必须先 `Read` 其 `.scl` 源文件确认实际接口**——禁止假设参数名、参数个数、参数类型或调用约定（如 `(#IN)` vs 内联 `:=` vs `=>`）
11. 🔴 **写 `.scl` 文件注释前必须先 `Read` LSP-904 §1(核心规则表)+§2.0(注释类型分工规则)**——变量/行内必须用 `//`，逻辑/流程块用 `(* *)`

### 定时器

12. 定时器用TIA原生`TON_TIME`/`TOF_TIME`/`TP_TIME`/`TONR_TIME`多重实例，PT/ET为TIME，毫秒值用`DINT_TO_TIME`转换（903规范V3.0.0）；新程序不引用`FB_TON`/`FB_TONR`
13. 定时器调用必须包含完整参数(IN/PT/Q/ET)，Q参数不能为空
14. 暂不写`T#`时间字面量（`plc check`规则LSP-906-TIMER-TIME-LITERAL仍拦截，903 §3.1）

### 错误预防

15. 修改代码前必须查阅906_错误预防规则中的检查清单
16. 变量前缀必须与类型匹配（906规范§1）
17. 定时器数组必须使用独立实例，禁止数组索引调用（906规范）

## 开发流程速查

```
Phase 1: 项目初始化
  └→ 907_项目配置规范 (.plc.json + libraries)

Phase 2: 编码实现
  ├→ 905_SCL编程规范 (主规范)
  ├→ 904_SCL注释规范 (注释格式)
  └→ 903_定时器使用规范 (定时器专项)

Phase 3: 错误预防
  └→ 906_错误预防规则 (实战检查清单)

Phase 4: 文档输出
  ├→ 023_程序设计文档模板
  └→ 815_接口文档模板
```

## 接口文档变量表自动输出（SysLib FB 专项）

### 适用范围

仅 `0100_PLC自动化/01_SharedLibraries/SysLib/` 下的 FB 项目，且存在 `PRD/接口文档_INT.md`。非 SysLib 项目不触发。

### 触发条件

当 PLC 技能本次会话的 changed_files 包含 `PRD/接口文档_INT.md` 时，技能退出前（Step 7.5）必须调用 `plc-var-parser` CLI 输出变量表。

### 调用方式

```powershell
# 1. 激活工作空间 venv（必须）
& "<工作空间根>\.venv\Scripts\Activate.ps1"

# 2. 调用 CLI（默认输出到 INT.md 同目录）
plc-var-parser "<项目根>/PRD/接口文档_INT.md"

# 3. 判断结果
# 退出码 0 = 成功，stdout 输出 JSON（含 status/variables/struct_fields/output_path）
# 退出码 1 = 解析失败
# 退出码 2 = 导出失败
# 退出码 3 = 参数错误（如文件不存在）
```

### 失败处理

- CLI 失败时仅告警，记录到 PM_SESSION implementation_log（含退出码+stderr），**不阻断** FB 开发流程
- 常见失败原因：venv 未激活、INT.md 格式不兼容、openpyxl 依赖缺失、plc-var-parser 未安装（需 `pip install -e .`）

### 输出产物

- Excel 文件生成在 INT.md 同目录，命名：`接口文档_INT_变量表.xlsx`
- 含 2 个 Sheet：变量表（VAR_INPUT/VAR_OUTPUT/VAR）+ 结构体定义（ST_xxx 字段）
- 每次调用覆盖同名旧文件

### CLI 工具位置

- 源码：`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-001_PLC变量表解析工具/02_开发文件/`
- 安装：`pip install -e .`（开发模式，改代码即时生效）
- 依赖：工作空间 venv（`<工作空间根>\.venv\`）

## 技能强制触发规则（防绕过）

18. 🔴 **修改 `.scl` 源码文件前必须触发 `plc-electrical-engineer` 技能**——禁止绕过技能直接修改 SCL 代码
19. 🔴 **技能触发后必须同步文档 + 回写 PM_SESSION**——技能退出前必须完成: ① 更新相关 PRD 文档版本/内容; ② 更新 PM_SESSION 变更记录和实施日志
20. 🔴 **禁止先回复用户再补写 PM_SESSION**——PM_SESSION 回写必须在向用户输出变更摘要之前完成

## 冲突处理

当PM通用规范与PLC技术栈规范冲突时，以PLC技术栈规范（`0100_PLC自动化/00_通用规范/`）为准
