# LEDGER-SETTLE1109 入账卡

> 卡片编号：`CARD-LEDGER-INTAKE-SETTLE1109 V1.1`
> 隔离基线：`cb1735367fc2422885db530ce2b5e2e4ce185c57`（`main`）
> 路径根：`.`
> 档次：文档档
> 安全回路: 否

V1.1：基线状态一列改为表头允许的取值（存在/计划新增），V1.0 的“存在，改”被预检拒绝；内容不变。

本卡只给 `main.py pr open` 提供“可改范围”，不改任何代码和 PLC 源码。背景：用户 2026-11-09T15:44:48Z 批准结算孤儿 Run RUN-DJ000-OUTREAD-001 并把 13 个本机变更单入库（消息 cmsg_013MFzja8RTUptLcFWxTQMox67isyDs64EoEK3NStsbQrS）；协调者确认顺序为先入库、再同步控制根。结算已经做完：目标 Run、Work、Mission 均 CANCELLED，恢复变更单 CHG-PLC-2026-007（DJ-2026-000）已 completed，恢复 Decision `DEC-20261109-SETL000P` 在控制根分支 `claude/settle1109-decisions` 的提交 5fec815a 里。入账范围：本机已 completed 而 main 仍 implementing 的 CHG-SCPT-2026-459、471；涉及文件栏补全（及 492 状态）的 490～500；恢复变更单 CHG-PLC-2026-007 及 DJ-2026-000 版本变更台账；本入账单 CHG-DOCU-2026-100（已批准）；恢复 Decision 文件。变更单文件由驾驶舱生成，按字节复制进工位，不手改；版本变更台账只补对应行，不动其他行。

更正（PR 正文也会写）：CHG-PLC-2026-007 引用里写的卡 SHA 是 25fe8e8c…（旧卡），卡经修正命令名（pm pr open → pr open）后 SHA 为 c23fbc20…；已批准的变更单不改。

| 路径 | 基线状态 | 用途 |
|---|---|---|
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/251_LEDGER-SETTLE1109入账卡_PM.md` | 存在 | 本卡 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-459.md` | 存在 | 本机已 completed/已补文件栏的变更单 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-471.md` | 存在 | 本机已 completed/已补文件栏的变更单 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-490.md` | 存在 | 本机已 completed/已补文件栏的变更单 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-491.md` | 存在 | 本机已 completed/已补文件栏的变更单 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-492.md` | 存在 | 本机已 completed/已补文件栏的变更单 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-493.md` | 存在 | 本机已 completed/已补文件栏的变更单 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-494.md` | 存在 | 本机已 completed/已补文件栏的变更单 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-495.md` | 存在 | 本机已 completed/已补文件栏的变更单 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-496.md` | 存在 | 本机已 completed/已补文件栏的变更单 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-497.md` | 存在 | 本机已 completed/已补文件栏的变更单 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-498.md` | 存在 | 本机已 completed/已补文件栏的变更单 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-499.md` | 存在 | 本机已 completed/已补文件栏的变更单 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-500.md` | 存在 | 本机已 completed/已补文件栏的变更单 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-DOCU/CHG-DOCU-2026-100.md` | 计划新增 | 入账变更单 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/02_变更记录/01_版本变更台账.md` | 存在 | 补行 |
| `0100_PLC自动化/DJ-2026-000/04_监控/01_变更管理/01_变更单/CHG-PLC/CHG-PLC-2026-007.md` | 计划新增 | 孤儿 Run 结算的恢复变更单 |
| `0100_PLC自动化/DJ-2026-000/04_监控/01_变更管理/02_变更记录/01_版本变更台账.md` | 存在 | 补行 |
| `.auto-pm/decisions/DEC-20261109-SETL000P.json` | 计划新增 | 恢复 Decision（提交 5fec815a） |

## 验收
- `.venv\Scripts\python.exe main.py ledger reconcile SW-2026-008 => 0`，`ledger reconcile DJ-2026-000 => 0`。
- 合并后控制根可同步回 `main`，`pm orient SW-2026-008` 不再报“归属范围内未提交文件”。

## 未核实
- 版本变更台账是受保护文件，该 PR 可能需要用户“规则批准 <头12位>”，以 PR 上的检查为准。
- DJ-2026-000 属 PLC 项目目录，PR 里安全回路填“否”：只入账变更单和台账行，不改 PLC 源码。
