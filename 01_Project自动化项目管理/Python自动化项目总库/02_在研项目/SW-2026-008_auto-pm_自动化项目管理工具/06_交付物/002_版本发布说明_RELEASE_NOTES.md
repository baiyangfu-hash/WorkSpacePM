---
version: "V1.2.4"
status: "正式发布"
created: "2026-09-07"
updated: "2026-11-02"
spec_id: "RELEASE_NOTES"
project_id: "SW-2026-008"
---

# auto-pm 自动化项目管理工具 - 版本发布说明 (RELEASE_NOTES)

> **当前版本**：`V1.2.4-6699a5b`  
> **发布日期**：`2026-09-07`  
> **适用平台**：Windows 10/11 x64 (免安装稳定运行槽 / Python 3.11+)  
> **稳定运行槽位**：`00_Infrastructure/auto_pm/releases/1.2.4-6699a5b` (active)


---

## V7（第七次发版）：`1.3.3-d671611`（候选，尚未切换）

> **状态**：候选。冻结提交 `d671611a13bc15536047769fdb0498666c414044`（`main` 上的 Merge pull request #496），**切换要等用户本人在主执行对话里说**；本节写的“现在是什么”指切换之后。本节之后的“当前版本 V1.2.4”和第 1～3 节是旧发布说明，保留作历史记录，切换后再更新页首。
> **范围**：相对现行有效版本 `1.3.3-6a9f127`（冻结提交 `6a9f1275`），`main` 上合并了 53 个 PR，其中 28 个改到发布载荷（`auto_pm`、`templates`），载荷共 56 个文件不同（+3017/-152）。其余只改测试、文档、`scripts/`、工作流，不进载荷。
> **门禁结论**：九组全量、`release-pregate`、样件联调、对账的实际结果**待发版卡填入**（本节写成时都还没跑完，不在此处写“全绿”）。

### 新增和变化

1. **工位满了会被拦，不再悄悄堆积（WS-001）。** 同时开着的工位目录到 8 个，`worktree open` 拒绝开新的；发版前体检 `doctor --pre-release` 超过 7 个就不让发。`worktree list` 标出闲置超过 3 天的；`worktree sweep` 只列可回收的，加 `--apply` 才删，保留名单里的目录不动；残缺的工位目录会被标出，不再被当成工作树。
2. **主控重启后，Run 还写着“在运行”，现在能查、能收口。** `pm recover` 只读判断执行进程还在不在；确认已死才可加 `--apply` 把它记为失败（`EXECUTOR_LOST`）。执行进程在容器里或另一个系统用户下时结论不可信，不要 `--apply`。
3. **长命令不再被休眠掐断租约**（Windows：续租包装在长命令期间防休眠）。
4. **验收命令由 `pm verify` 自己执行，计划阶段就拒收会出假绿的命令**（要 shell 的命令；PowerShell 下会被悄悄改写的命令）。新增只读命令 `pm acceptance-scan --pid <项目号>`：列出进行中的任务里 `pm verify` 会拒绝的已批准验收命令。
5. **变更单状态不能靠手改文件绕过。** 状态相对 `HEAD` 是新的，必须在本机状态流水账（控制根 `.auto-pm/status_journal.db`）里有对应记录，否则提交钩子和 `doctor` 拒绝；`HEAD` 里已有的状态放行。
6. **控制根落后 `main` 会提醒。** `pm inbox add`、`approve`、`resume`、`orient`、`verify` 在控制根落后 `origin/main`、或范围内文件与起点不一致时，在屏幕上打印 `[控制根同步]` 提示（不拦；离线时写“未核实”）。切换后第一次用就会看到，所以切换前先把控制根快进到冻结提交。
7. **批准类：** 有条件批准也要用户原话凭据；agent 会话没有合法凭据一律拒（TD-SW008-217）。
8. **命令行相对路径一律按调用者所在目录算**（`-w`、`--output`、`--project-root` 等）。

### 已修复

1. 变更单序号到 1000 以上时被读成前三位。
2. Windows 上不再先搜当前目录找可执行文件；后台 git 命令不弹黑窗。
3. `project create` 与“项目未登记”的报错指路 `project register`；会话视图和 `constraint heal` 的提示不再引用已退役的 PM_SESSION。
4. 服务层 `start_run` 也拒绝把控制根当 Run 的工位（恢复类例外见第 8 条）。
5. 进程探针：`/proc` 读不全时“进程不在”改判 UNKNOWN，不再误判已死。
6. 残缺工位目录、工位目录被手工删掉后的处理。
7. `doctor` 的发布指针检查：改了指针的发布 PR 按分支头自洽。
8. **结算死锁（P1，#496，冻结后例外纳入）。** 原来 `run start` 禁止把控制根当工位，而过期 Run 的结算（`settle-expired`）、租约补偿与对账等行政恢复又必须在控制根里做，两条互相卡住，过期的 Run 永远结不掉。现在这几类恢复 Run 可以用控制根作工作树，条件很窄：Work 要绑定带恢复 `runtime_capability` 的无条件已批准 Decision，命令行用 `--recovery-change <该 Decision 的变更单号>` 声明；Decision 的批准文件和 Work 范围要覆盖 `continuity.db`，而 **Run 的 owned 路径只能是 `.auto-pm/continuity.db`，多一个路径就拒**。另外：**恢复用的 Decision 和被结算的原 Decision 都必须已经入库且与 `HEAD` 一致，否则拒**；Decision 点名的目标必须仍待处理（结算：目标 Run 还没到终态；围栏或对账：目标 Run 已到终态而账里还没有对应的完成记录；裁决：目标 Work 仍是 BLOCKED），处理完了不能再开恢复 Run；同一个恢复 Work 同时只许一个未终态的 Run。撤销一个还没启动的 Run 不需要恢复 Run，不在这个例外里。过期 Run 现在能从命令行结算。

### 已知事项

- `pm acceptance-scan` 可能列出 `would_be_refused_at_plan`：这些命令 `pm verify` 仍会执行，但同样文本现在重新 `pm plan` 会被拒（例如 PowerShell 下会被悄悄改写）。**不阻塞**；建议重新计划。发版前在笔记本上的实际扫描结果：**待填**。
- 控制根只是落后 `main`、且与本卡范围无交集时，`run start` 不拦（只打印提示）；本卡范围内的控制根文件与工位起点不一致才会拒。
- 总控屏（`scripts/cockpit_board`）和 `scripts/pmf_build.py` 不在发布载荷里，不随这次切换；它们随控制根拉 `main` 生效（总控屏怎么更新：未核实）。

### 升级和回退要注意

- **单向变更：** 一旦用过 `pm recover --apply`（账本里有 `EXECUTOR_LOST`），账本就不能再换回 `1.3.3-6a9f127` 及更早的版本（旧版读到不认识的失败原因会打不开快照）。发版和切换版本前先查有没有项目记过它。
- 变更单状态流水账是新增文件，回退到旧版本时旧版不读它也不写它；回退后再切回新版，期间没有记录的状态变更会被拒（回退行为未实测）。
- 发版前准备清单和阻塞项见共享文件夹 `plans/发版7准备_发版说明草稿与检查清单_20261102.md`。

---

## 1. 版本概述

`auto-pm` V1.2.4 是项目架构演进与稳定生产的重要里程碑版本。本版本完成了稳定部署双槽架构落地与原子切流（`1.2.4-6699a5b` active），闭环了全生命周期工作流编排内核 Cockpit OS（Phase 0~3）、全链台账「台帐→台账」规范化对账，以及 SRE 零崩溃质量门禁硬核加固，实现项目管理工具的高可靠无感运行。

---

## 2. 核心特性与架构演进

- **双槽稳定部署与不可变制品 (CHG-SCPT-2026-184 / CHG-SCPT-2026-187)**：
  - 落地 `00_Infrastructure/auto_pm` 稳定运行容器，引入双槽指针原子切流（active/previous）与 465 文件 manifest 完整性硬校验；
  - 消除 editable 依赖，启动脚本注入 `PYTHONDONTWRITEBYTECODE=1`，彻底杜绝 `__pycache__` 漂移污染。
- **全链台账规范化与对账引擎闭环 (CHG-SCPT-2026-187)**：
  - 彻底清理工作区错别字，完成活体项目、规范索引与模板库「台帐→台账」全链改名；
  - 生产对账实现 0 缺失、0 孤儿、0 状态差异，台账自动入账。
- **Cockpit OS 工作流编排与事务沙箱 (CHG-SCPT-2026-171~177)**：
  - 落地 `WorkflowOrchestrator`（方案规划与流水线执行）、`ChangeTransactionManager`（快照隔离与原子回滚）、`ProjectArchiveService`（可逆归档恢复）与 PM Saga WAL 事务日志引擎。
- **CLI 命令矩阵与活文档自动化自省 (CHG-SCPT-2026-186)**：
  - 全面支持 22 个 CLI 业务命令组，下沉 `doc check --strict` 与 `doc sync`，实现代码 AST 元数据无损反向注回活文档；
  - 修复 `plc check` 退出码缺陷（FAIL 坚决返回 Exit 1，杜绝假绿）。

---

## 3. 发布放行签署

- **自动化测试回归**：全量单测与回归用例 **1928+ passed / 100% 绿灯** ✅
- **Doc-as-Code 文档门禁**：`auto-pm doc check --strict` **DOC-001~DOC-004 ALL PASS** ✅
- **台账一致性对账**：`auto-pm ledger reconcile SW-2026-008` **0 差异 ALL PASS** ✅
- **SRE 运行时校验**：launcher resolve-only 与 `--help` **Exit 0 通过** ✅
