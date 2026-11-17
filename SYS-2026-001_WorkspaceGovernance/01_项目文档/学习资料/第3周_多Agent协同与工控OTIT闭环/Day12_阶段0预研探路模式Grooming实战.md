---
version: "V2.0.0"
status: "正式发布"
created: "2026-09-07"
updated: "2026-09-07"
spec_id: "GUIDE_W3_D12"
project_id: "SW-2026-008"
title: "Day 12：阶段 0 预研探路模式 Grooming 实战"
---

# Day 12：阶段 0 预研探路模式 Grooming 实战

> 🎯 **今日目标**：掌握需求澄清阶段的只读代码基优先勘测法（Codebase-First Gating），理解预研模式（Grooming）与零盲问红线。  
> ⏱️ **预计耗时**：50 分钟  
> 🛠️ **前置准备**：查看 `AGENTS.md` 中的零盲问铁律（Zero-Stupid-Questions Redline）。

---

## 💡 一、工控视角看预研探路：进车间先看图纸与接线柜，严禁“盲问机修师傅”

当一个电气工程师接手现场改造任务（例如“给 3 号工位加装一个安全光幕”）时：
- **最不专业的表现**：直接跑去车间拉住操作工甚至总监问：“师傅，3 号工位的主电源在哪？PLC 用的什么型号？还有空余输入点吗？”——**这必然被现场当场质疑专业能力！**
- **专业工程师的标准动作**：
  1. 先翻开电气原理图，看 3 号工位的配电图；
  2. 打开 PLC 机柜，看 CPU 模块型号与扩展 IO 模块是否有空余端子（`%I4.2`、`%I4.3`）；
  3. 上线博途，看当前程序块是否有空闲子程序号；
  4. **全看清楚了，只有发现接线图与现场实际物理线号冲突时，才向工艺负责人发起精准提问！**

这就是 `auto-pm` 的 **阶段 0 代码基优先探路门禁（Grooming Mode）**！

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ 🛑 阶段 0：需求澄清与代码基优先门禁 (Codebase-First Gating)                  │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1. 严禁代码盲问 (Zero-Stupid-Questions Redline)：                           │
│    凡在源码、配置文件 (.plc.json)、数据结构 (DTO) 中能读到的信息，禁止向用户发问！ │
│ 2. 派发只读预研探路子代理 (Grooming Mode)：                                  │
│    python -m auto_pm handoff create --mode grooming                          │
│ 3. 探明受影响文件、现有类/函数定义、API 契约与风险点                          │
│ 4. 仅在遇到无法推导的真实业务决策抉择时，才发起高质量澄清提问！              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## ⚙️ 二、Grooming 预研探路流水线

1. **PM 发起预研交接**：
   ```powershell
   python -m auto_pm handoff create --pid <PID> --to fullstack-engineer --summary "预研某业务" --mode grooming
   ```
2. **子代理只读勘测**：
   - 使用 `grep_search`、`find_by_name`、`view_file` 自行查阅工程；
   - **严禁编写或篡改任何业务代码**；
3. **回传事实摘要**：
   - 提取现有数据结构、涉及文件与技术风险，回写 `handoff_result.json`，为阶段 1 报批提供 100% 真实证据。

---

## 🧪 三、5 分钟动手实操实验

### 步骤 1：体验冷启动探路入口
```powershell
$env:PYTHONPATH = "00_Infrastructure/auto_pm"
python -m auto_pm -w "c:\Users\fubai\Documents\My_Workspace" pm resume SW-2026-008 --json
```
*预期输出*：以 JSON 格式输出 `read_set`、`active_change_numbers` 与 `next_legal_action`，为探路指明最精准的 3 个证据文件。

---

## 🛡️ 四、改崩恢复法与今日自测打卡

### 🚑 探路越界拦截
在 Grooming 模式下，子代理严禁调用写工具。若发现任何写操作，门禁立刻报错中断。

### 📝 今日自测思考题
1. 什么是“零代码盲问红线（Zero-Stupid-Questions Redline）”？
2. 在 Greenfield（全新建仓）与 Brownfield（在研迭代）项目中，探路原则有何不同？
3. Grooming 模式输出的核心成果是什么？
