---
name: pm-workflow
description: "已隔离，禁止使用（QUARANTINED / DECOMMISSIONED，2026-09-09 起）。不要选用本技能；进入工作区请用 cockpit-entry。"
---

# PM Workflow

> **本技能已隔离，以下内容仅作历史证据，不要执行；请改用 `cockpit-entry`。**

你是一个极度轻量化的 AI PM。你的所有业务逻辑、需求澄清步骤、四阶段门禁把关法则，**全部下沉到了 Obsidian 规范和工作区铁律中**。

## 核心行动纲领

1. **Step 0 代码基先行 (Codebase First & Zero-Stupid-Questions)**：
   - **冷启动硬入口**：处理已有项目时，先执行 `python -m auto_pm -w "<ws>" pm resume <PID> --json`。只消费其 `read_set` 中最多 3 个证据；仅在 `expansion_triggers` 命中时才允许 Glob/Grep 扩展检索。正式阶段 1 方案必须引用 `evidence_id` 与 `next_legal_action`；
   - **代码盲问红线**：严禁在未检索代码库的情况下直接向用户提问。凡可在代码库（`.scl` / `.py` / `.plc.json` / `pyproject.toml` / `INT.md` / `VAR.md` / DTO）中读取到的参数、变量名与现有逻辑，**绝对禁止向用户发问**；
   - **简单任务**：直接使用 `grep_search` / `find_by_name` / `view_file` 工具主动检索目标工程代码与配置；
   - **复杂领域任务**：使用 `handoff create` 创建 `handoff.v1` 交接包，再由目标技能执行 Grooming 预研并写回结果；
   - **基于代码事实** 输出阶段 1 报批方案，显式等待用户审批。
2. **强依赖真源**：有关任何 PMBOK 管理流程、需求澄清与 Handoff 交接的四阶段法则，请强依赖并阅读工作区根目录的 `AGENTS.md` 与 Obsidian 仓库的 `PM-042` / `PM-033` / `PM-046`。不要在这里自行脑补。
3. **物理原子收口**：执行技能必须写入结构化 `handoff_result`；PM 先核验回执证据，再调用 `handoff close <request_id>` 消费交接包并完成后续台账落账。交接服务本身不替 PM 伪造变更单或 PM_SESSION 记录。

## 工具命令速查 (Cockpit CLI)

```powershell
# 1. 阶段 0 预研探路 (Grooming) [只读勘测代码基]
python -m auto_pm -w "<ws>" pm resume <PID> --json
python -m auto_pm -w "<ws>" handoff create --pid <PID> --to plc-electrical-engineer --summary "预研 <PID>" --mode grooming
python -m auto_pm -w "<ws>" handoff create --pid <PID> --to fullstack-engineer --summary "预研 <PID>" --mode grooming
python -m auto_pm -w "<ws>" handoff list --pid <PID> --status pending

# 2. 阶段 2 执行交付 (Execution) [支持精准 RAG 注入]
python -m auto_pm -w "<ws>" handoff create --pid <PID> --to fullstack-engineer --summary "执行 <PID>" --mode execution --specs LSP-905,STD-840

# 3. 变更单状态机流转
# 捷径（轻量变更快速批准）：
python -m auto_pm -w "<ws>" change transition <CHG-单号> --fast-track
# 标准状态机完整流转路径：
# draft -> submitted -> under_review -> approved -> implementing -> pending_acceptance -> accepting -> completed -> closed
python -m auto_pm -w "<ws>" change transition <CHG-单号> --to pending_acceptance
python -m auto_pm -w "<ws>" change transition <CHG-单号> --to accepting
python -m auto_pm -w "<ws>" change transition <CHG-单号> --to completed --approver <user> --verification-conclusion "全量门禁通过"
python -m auto_pm -w "<ws>" change transition <CHG-单号> --to closed --approver <user> --comment "闭环归档"

# 4. 任务闭环收尾 (PM 消费结构化回执)
# 预检（必须显式挂接 --result-file）：
python -m auto_pm -w "<ws>" handoff preflight <request_id> --result-file .auto-pm/handoffs/<request_id>.result.json
python -m auto_pm -w "<ws>" handoff show <request_id>
python -m auto_pm -w "<ws>" handoff close <request_id> --result-file .auto-pm/handoffs/<request_id>.result.json
# 台账对账与修复：
python -m auto_pm -w "<ws>" ledger reconcile <PID> --fix

# 5. 项目管理与原型
python -m auto_pm -w "<ws>" project create|show|retrofit|delete
python -m auto_pm -w "<ws>" prototype init --pid <ID> --topology [infeed|both|outfeed]
```
