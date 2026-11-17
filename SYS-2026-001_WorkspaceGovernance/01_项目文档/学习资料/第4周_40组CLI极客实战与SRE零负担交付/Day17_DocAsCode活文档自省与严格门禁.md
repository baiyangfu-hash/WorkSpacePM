---
version: "V2.0.0"
status: "正式发布"
created: "2026-09-07"
updated: "2026-09-07"
spec_id: "GUIDE_W4_D17"
project_id: "SW-2026-008"
title: "Day 17：Doc-as-Code 活文档自省与严格门禁"
---

# Day 17：Doc-as-Code 活文档自省与严格门禁

> 🎯 **今日目标**：掌握代码自省与文档自动重注（`auto-pm doc sync`），掌握严格一致性与死链门禁（`auto-pm doc check --strict`）。  
> ⏱️ **预计耗时**：50 分钟  
> 🛠️ **前置准备**：查看 `06_交付物/001_用户操作指南与排障手册_USER_GUIDE.md` 中的标记。

---

## 💡 一、工控视角看文档自省：拒绝“代码改了，说明书还是两年前的”

传统工业开发中最常见的扯皮是：
- 研发工程师在代码里加了 5 个新参数、改了 2 个通讯协议；
- 但操作手册和接口文档谁都没去改，还是上一版的旧说明；
- 现场调试人员对照说明书配参数，设备始终报错，两边互相推诿。

`auto-pm` 采用 **Doc-as-Code（文档即代码）自省同步体系**：
- 在 Markdown 文档中预埋标记槽：
  `<!-- AUTO_DOC_START: CLI_COMMANDS --> ... <!-- AUTO_DOC_END: CLI_COMMANDS -->`
- 一键运行 `auto-pm doc sync`，系统自动解析 Python 源码的 AST 抽象语法树，提取类、函数、CLI 命令与门禁字典，**无损、自动、准确地注回说明书与设计文档**！
- 代码改了，文档在 1 秒内自动同步，彻底消灭文档漂移！

```text
Python 源码 AST (CLI 命令 / Bridge 导出 / Gate 规则)
                          │
                          ▼
            auto-pm doc sync (自省注入器)
                          │
                          ▼
Markdown 活文档 (USER_GUIDE.md / INT.md / DSN.md 标记槽)
```

---

## ⚙️ 二、DOC-001 ~ DOC-004 四大硬门禁

运行 `auto-pm doc check --strict` 时，系统会执行 4 道严格审查：
1. **DOC-001（CLI 命令同步率）**：检查源码所有 CLI 是否 100% 登记在用户指南中；
2. **DOC-002（Obsidian 规范死链扫描）**：扫描活跃区所有 Markdown 内部链接，真实死链数必须为 0；
3. **DOC-003（全局规范索引覆盖率）**：比对 `spec_registry.json` 与 `00_INDEX`，覆盖率必须 100%；
4. **DOC-004（全系统版本锁一致性）**：比对 pyproject.toml 与 PM_SESSION 中的版本号必须完全一致。

---

## 🧪 三、5 分钟动手实操实验

### 步骤 1：触发一次代码 AST 自动自省重注
```powershell
$env:PYTHONPATH = "00_Infrastructure/auto_pm"
python -m auto_pm -w "c:\Users\fubai\Documents\My_Workspace" doc sync
```
*预期输出*：控制台打印注入记录，成功将 CLI 命令注入 USER_GUIDE.md，将 Bridge 表格注入 INT.md。

### 步骤 2：执行全量严格文档门禁审查
```powershell
python -m auto_pm -w "c:\Users\fubai\Documents\My_Workspace" doc check --strict
```
*预期输出*：输出规整的文档门禁报告，DOC-001~DOC-004 全部显示 PASS，Exit Code 为 0！

---

## 🛡️ 四、改崩恢复法与今日自测打卡

### 🚑 死链报错排查
若 DOC-002 提示某链接指向的文件不存在：
检查该文件是否被重命名或移入了 `archive/`。若已归档，更新 Markdown 中的引用路径。

### 📝 今日自测思考题
1. 什么是 Doc-as-Code 活文档？预埋标签起到了什么作用？
2. `auto-pm doc check --strict` 覆盖了哪四大维度的检查？
3. 为什么版本号（Version Lock）在工程全系统必须严格一致？
