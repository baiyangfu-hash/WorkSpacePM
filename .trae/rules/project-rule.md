---
alwaysApply: true
description: 全局开发规则（薄入口）：真源是根目录 AGENTS.md；这里只留技术栈指路
---

# 全局开发规则（薄入口）

本文件只指路，不抄规则。红线、澄清-报批-执行-验收四步、三条线、工位、审计、临时文件规矩，真源都是根目录 `AGENTS.md`（细则在 `roles/shared/refs/agents_附录/`），这里不再重写一遍（见附录 `03_工位细则.md` 第 6 条“各家入口文件只做薄引用”）。

1. **进门**：照 `AGENTS.md`“进门”一节，在控制根跑 `pm_flows.py entry <项目编号>`；Trae 的身份声明和手敲步骤见 `.trae/rules/cockpit-entry.md` 与 `.trae/skills/cockpit-entry/SKILL.md`。
2. **命令**：驾驶舱命令只从控制根用 `.venv` 里的 Python 跑 `main.py`；全部命令见 `SW8/06_交付物/003_命令总目录_COMMANDS.md`（`SW8/` 的全称见 `AGENTS.md` 开头），不绕过 `main.py` 直连研发母体的包；已隔离的 `pm-workflow` 不用。
3. **冲突**：技术栈细节以下面的技术栈规则为准；`AGENTS.md` 的红线和流程任何时候都优先。

## 规范体系

- 全局 PM 规范：`00_Obsidian_Base全局规范文件仓库/01_项目管理域/`
- Python 技术栈规范：`00_Obsidian_Base全局规范文件仓库/02_Python开发域/`（DEV-210/216/217/218/220）
- PLC 技术栈规范：`00_Obsidian_Base全局规范文件仓库/03_PLC自动化域/`（LSP-903/904/905/906/907/TOOL-908）
- 驾驶舱与全栈规范：`00_Obsidian_Base全局规范文件仓库/04_驾驶舱与全栈域/`
- 规范注册表：`00_Obsidian_Base全局规范文件仓库/spec_registry.json`

## 技术栈规则

- PLC：`0100_PLC自动化/.trae/rules/plc-rules.md`
- Python：`01_Project自动化项目管理/.trae/rules/python-rules.md`

根据当前工作目录自动适配对应的技术栈规范：

- **工作在 `0100_PLC自动化/` 下**：
  - 必须全面遵循 Siemens LSP 扩展生态及 LSP-905/906/907/908 规范；
  - 严守语法白名单（禁 GOTO/标号/REPEAT/指针/METHOD）；
  - 定时器以 LSP-903 为准：用 TIA 原生 `TON_TIME`/`TOF_TIME`/`TP_TIME`/`TONR_TIME` 多重实例，PT/ET 为 TIME，毫秒值用 `DINT_TO_TIME` 转换，暂不写 `T#` 字面量；新程序不引用 SysLib 的 `FB_TON`/`FB_TONR` 包装块；
  - 所有定时器必须在 FB 顶部无条件批量调用，严禁放入 IF/CASE 分支；
  - CASE 状态机必须带 ELSE 容错分支；严禁中文变量名与中文全角标点；
  - 项目必须配置 `.plc.json` 且使用 `libraries` 数组指向 SysLib。
- **工作在 `01_Project自动化项目管理/` 下**：
  - 遵循 DEV-210/DEV-216/DEV-217/DEV-218/DEV-220 规范；
  - 桌面上位机全面采用 PySide6 + QML 2.15 5 层整洁架构（QML Views $\rightarrow$ Bridges $\rightarrow$ Facades $\rightarrow$ Core Services $\rightarrow$ SQLite/DTO）；
  - 后台耗时任务使用 `QThreadPool` + `QRunnable` 执行，通过 Qt Signal/Slot 回传主线程；
  - 工业通信（Modbus/S7）遵循 DEV-218 独立 Worker 线程与点表内存双缓冲机制；
  - 代码质量统一由 `Ruff` 与 `Mypy` 强制保障。
- 跨域修改时 → 同时遵循两个技术栈的规范。
