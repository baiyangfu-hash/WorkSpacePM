# auto-pm 架构设计与系统全景图 (ARCHITECTURE V2.2.0)

> **版本**: V2.2.0（候选，2026-10-10；依据已推送的 `d3c50a8b`，即 M2 收口之后），上一版 V2.1.0（2026-09-06），基线 V2.0.0（2026-08-22）。
>
> **本版新增**：第 3 节"运行与控制面"（launcher、不可变 release、连续性数据库、Git Hook）；分层图里 CLI 命令组数量更正；测试规模更正。分层图本身的层次划分没有改动。
>
> 未逐项复核的既有说法保持原样，并在对应处标注 **[未复核]**。

---

## 1. 系统分层架构

```text
+-----------------------------------------------------------------------------+
|                                 Presentation Layer                          |
|  +-------------------------------------+  +-------------------------------+ |
|  |     QML GUI Modern Dark Desktop     |  |     Headless CLI (25 Groups)  | |
|  |  (ProjectHall, Workbench, SpecCenter)|  | (project, plc, spec, change, | |
|  |                                     |  |  workflow, handoff, decision, | |
|  |                                     |  |  dogfood, doctor, clean, ...)  | |
|  +-------------------------------------+  +-------------------------------+ |
+---------------------------------------+-------------------------------------+
                                        |
+---------------------------------------v-------------------------------------+
|                         Bridge & Interface Layer + Cockpit OS               |
|  +-------------------------------------+  +-------------------------------+ |
|  |       Qt Quick QObject Bridges      |  |   AI Context Bus (.auto-pm/)  | |
|  +-------------------------------------+  +-------------------------------+ |
|  +-------------------------------------+  +-------------------------------+ |
|  |  WorkflowOrchestrator (plan/execute)|  | ChangeTransactionManager      | |
|  |  ProjectArchiveService              |  | PM Saga WAL 事务日志           | |
|  +-------------------------------------+  +-------------------------------+ |
+---------------------------------------+-------------------------------------+
                                        |
+---------------------------------------v-------------------------------------+
|                                 Domain Logic Layer                          |
|  +----------------+  +----------------+  +----------------+  +------------+ |
|  |   PLC Domain   |  |   Spec Domain  |  |  Change Domain |  |  VarTable  | |
|  | (53 Gatekeeper)|  | (Index/Snapshot)|  | (12-CHG/Ledger)|  | (14 Parsers| |
|  +----------------+  +----------------+  +----------------+  +------------+ |
+---------------------------------------+-------------------------------------+
                                        |
+---------------------------------------v-------------------------------------+
|                              Infrastructure Layer                           |
|  +----------------+  +----------------+  +----------------+  +------------+ |
|  | SQLite Storage |  | Copier Engine  |  | Git Subsystems |  | AST Parsers| |
|  +----------------+  +----------------+  +----------------+  +------------+ |
+-----------------------------------------------------------------------------+
```

## 2. 关键质量属性与测试保障
- **测试规模**：研发母体 `tests/` 共 221 个测试文件、**3541 项**（2026-10-10 在 `d3c50a8b` 上，Windows 分组运行 3510 通过 / 15 失败 / 16 跳过，来源：本地回报；同一提交在 GitHub 的 ubuntu-24.04 + Python 3.12 上 3485 通过 / 35 失败 / 21 跳过，其中失败均有归因并记录为基线）。上一版写的 1928、1761、116 是各自当时的历史数值，不再沿用；
- **静态门禁验证**：`PlcChecker` 包含 53 项严格指标 **[未复核]**；`ruff check` 通过，`mypy --platform win32 auto_pm` 在锁定的工具版本下 244 个源文件 0 错误（2026-10-10 实测）；
- **自动检查**：`.github/workflows/sw008-ci.yml`（GitHub Linux，Python 3.12，锁定依赖）在非 `main` 分支推送时运行 ruff、mypy、全量测试与密钥扫描，并与 `tests/tools/sw008_ci/baseline.linux.json` 的已知失败基线比对；它是早期预警，不替代本地受治理门禁。
- **无损修复原则**：任何 repair 或 retrofit 操作绝不覆盖用户业务核心代码。

## 3. 运行与控制面（M2 之后）

驾驶舱把"运行哪份代码"和"谁批准了什么"分开管理：

```text
 工作区根 main.py ──▶ 00_Infrastructure/auto_pm/launcher        (标准库，失败即拒绝)
                          │  解析 active_release.json → release id
                          │  校验 deployment_manifest.json 里登记的逐文件 SHA-256（exact-tree）
                          ▼
              00_Infrastructure/auto_pm/releases/<release-id>/   (不可变；另有 previous_release.json 作回退位)
                          │
                          ▼  CLI（25 个命令组）  /  GUI（默认：老板驾驶舱，只读）

 控制根 .auto-pm/continuity.db  ◀── 连续性 v2：Mission / Work / Run / Lease / Checkpoint / Handoff.v2 / 事件
 控制根 .auto-pm/decisions/*.json ◀── 已批准的决策包（字节被绑定，不可手改）
 .git/hooks/pre-commit、commit-msg ──▶ main.py git-hook …        (提交时检查：有无批准的变更单、台账是否一致、是否越界)
```

要点（均可在源码中找到对应实现）：

- **启动器**：`00_Infrastructure/auto_pm/launcher/bootstrap.py`，只用标准库，对 release 做 exact-tree 校验；指针只存 release id，不存 manifest 哈希。
- **连续性存储**：`auto_pm/infrastructure/continuity_store.py`，当前 schema 为 `continuity-store.v7`；遇到未知或未来版本一律拒绝（fail closed）。
- **PM 门面与驾驶舱服务**：`auto_pm/application/core/pm_facade_service.py`、`pm_cockpit_service.py`、`local_execution_orchestrator.py`、`workspace_context_service.py`。
- **Git Hook**：`auto_pm/infrastructure/git_hook_enforcer.py`。
- **数据库不在 Git 里**：`.auto-pm/continuity.db` 是本机状态，需要单独备份（见 `41_不依赖AI的最低限度维护手册_PM.md`）。

> 研发母体（本目录）与运行位（`00_Infrastructure/auto_pm`）是两套东西：母体是源码，运行位是从母体某个提交构建出来的不可变 release。判断"现在到底在运行哪份代码"，看 `main.py context resolve` 的输出，而不是看母体源码。
