---
version: "V2.0.1"
status: "学习参考（局部更新）"
created: "2026-09-07"
updated: "2026-10-09"
spec_id: "GUIDE_W3_D11"
project_id: "SW-2026-008"
title: "Day 11：Handoff 契约化移交总线与物理隔离"
---

# Day 11：Handoff 契约化移交总线与物理隔离

> **历史内容提示（2026-10-09）**：本次只补说明，以下正文保留 2026-09-07 的旧版设计与命令，不能直接作为当前操作指令。尤其旧 `handoff create/list/preflight`、`python -m auto_pm`、`PYTHONPATH` 配置和 result.json 用法，不应照抄执行，也不能作为当前授权或完成依据。
>
> 当前交接以工作区根 `AGENTS.md` 及其引用的 Continuity v2 规则为准，通过根 `.venv\\Scripts\\python.exe main.py` 入口核验；本次没有验证具体命令参数。你只需确认“哪项任务、在哪个目录、做到哪里、检查结果、下一步”，不需要手写 JSON、租约或数据库记录。
>
> 文件隔离和版本概念先看[Git 与 GitHub：日常维护够用指南](../Git与GitHub_日常维护够用指南.md)。工作树只分开文件操作现场，不自动隔离数据库和外部进程；本章也不代表驾驶舱必须替你启动模型。

> 🎯 **今日目标**：理解多智能体（Multi-Agent）协作中的 Handoff 契约协议，掌握主控 PM 与领域执行技能（PLC / 全栈）的物理隔离法则。  
> ⏱️ **预计耗时**：50 分钟  
> 🛠️ **前置准备**：查看工作区根目录下的 `AGENTS.md` 与 `.agents/rules/subagent_handoff.md`。

---

## 💡 一、工控视角看 Handoff 契约：设备厂与集成商的“技术协议交接书”

在做大型非标整线工程时，电气负责人（PM）绝不会走到车间对着打螺丝的工人口头喊一句：“喂，把那个电机速度调快点！”
正规流程必然是签署**《工站工序技术交接协议》**：
1. **交接输入（Context）**：明确输入参数（如减速比、最大扭矩、安全光幕信号）；
2. **职责边界（Isolation）**：机械组只管调机械间隙，电气组只管调驱动器参数，绝不允许机械工程师私自拿电脑刷 PLC 程序；
3. **回执凭据（Receipt）**：调试完成后，现场工人必须填写《调试验收报告》，附上实测波形图，PM 验收签字后方可落账！

`auto-pm` 打造的 **Handoff Protocol** 就是这套数字化的工业交接协议：

```text
┌─────────────────┐       ① 生成结构化契约包       ┌─────────────────┐
│   主控 PM Agent  │ ───────────────────────────> │  领域执行子代理   │
│  (规划/审批/收口) │                              │ (PLC / 全栈开发) │
└─────────────────┘ <─────────────────────────── └─────────────────┘
                          ② 回传结构化回执 JSON
```

---

## ⚙️ 二、执行权剥离与结构化契约总线

1. **主会话（主 Agent）褫夺编码权**：
   - 主会话只负责启动规划（PMBOK 启动/规划过程组）与交付验收（收尾过程组）；
   - **绝对禁止在主会话聊天框直接以 Markdown 编写业务代码文件**！
2. **强制契约化交接（Handoff Payload）**：
   - 必须通过驾驶舱生成结构化交接包：`python -m auto_pm handoff create ...`；
   - 自动注入基线文档（baseline_documents）、目标（goal）与强制法典约束（strict_constraints）；
3. **结构化回执（Handoff Result）**：
   - 子代理完成任务并通过自检后，必须写入 `.auto-pm/handoffs/<request_id>.result.json`，严禁口头汇报“我搞定了”。

---

## 🧪 三、5 分钟动手实操实验

### 步骤 1：查看 Handoff 命令行工具体系
```powershell
$env:PYTHONPATH = "00_Infrastructure/auto_pm"
python -m auto_pm -w "c:\Users\fubai\Documents\My_Workspace" handoff --help
```
*预期输出*：列出 create, list, show, preflight, close 等 5 大核心交接指令。

### 步骤 2：查看当前工作空间中的待处理交接包
```powershell
python -m auto_pm -w "c:\Users\fubai\Documents\My_Workspace" handoff list
```
*预期输出*：展示历史与当前的交接请求状态（pending, completed, consumed）。

---

## 🛡️ 四、改崩恢复法与今日自测打卡

### 🚑 交接包校验阻断排查
若 `handoff preflight` 报错：
核对是否显式挂接了 `--result-file .auto-pm/handoffs/<request_id>.result.json`，系统禁止空证据消费。

### 📝 今日自测思考题
1. 为什么多 Agent 协作必须进行“执行权物理剥离”？
2. 结构化交接包（Handoff Payload）包含哪些关键字段？
3. 主控 PM 在消费子代理回执后，必须执行哪 3 步闭环落账？
