# auto-pm 架构设计与系统全景图（ARCHITECTURE V3.0.0）

> **版本**：V3.0.0（2026-11-02 重写），取代 V2.1.0（2026-09-06）。V2.1.0 写的是 Cockpit OS 上线前的样子，没有账本、发布快照、工位、护栏分层，已不描述现在的系统；旧版内容见 Git 历史。
> **读者**：接手改驾驶舱的 AI（Trae、Codex、Claude 等）和用户。读完应该能回答：代码放在哪、现场到底跑的是哪份代码、一张卡怎么走、哪些护栏在哪一层、改这里会碰到什么。
> **标注规矩**：**已核**＝对着仓库代码或命令输出核过；**读码**＝读代码得出、没跑过；**未核实**＝没找到证据，别当事实用。数字是写作当天的快照，会过期，以命令输出为准。
> **类比**：下面用产线上的东西做对照。控制根＝主控柜，工位＝调试台，发布快照＝已经下载进 PLC 的程序版本，账本＝设备状态字加生产记录，租约＝操作钥匙，护栏＝联锁。

---

## 1. 三个地方：谁在哪台机器上

```text
┌──────────────────── 一台电脑（账本主机）────────────────────────────────────┐
│ 控制根 R：本机唯一一份仓库克隆，停在 main                                       │
│  ├─ .auto-pm/continuity.db       账本（SQLite，不入 Git）                      │
│  ├─ .auto-pm/decisions/DEC-*.json   批准记录（Decision，入库）                  │
│  ├─ .auto-pm/cache/lease-wallet/    各 Run 的租约口令（不入 Git）               │
│  ├─ main.py                      根入口：只转给启动器，自己不 import auto_pm   │
│  └─ 00_Infrastructure/auto_pm/                                               │
│       ├─ launcher/          启动器：只用标准库，先校验再运行                    │
│       ├─ releases/<版本>/   发布快照（不可变），只含 auto_pm 与 templates       │
│       ├─ active_release.json / previous_release.json   双槽指针               │
│       └─ deployment_manifest.json   每个发布的逐文件 SHA-256                  │
│ 工位 W：R/.auto-pm/worktrees/<agent>，每个会改文件的 agent 一个                  │
│        agent 在这里写代码、提交、推分支                                         │
└────────────────────────────────────────────────────────────────────────────┘
        │ 工位里提交、推分支                      ▲ 命令（main.py …）只在控制根跑
        ▼
┌────────────────────────── GitHub ──────────────────────────┐
│ main 只走 PR；工作流：pr-gate、safety-gate、rules-gate、       │
│ reviews-tools-ci、sw008-ci、plc-ci、root-tests、hook-replay、 │
│ ci-aggregate、release-pregate、sample-drill 等（见第 7 节）   │
└─────────────────────────────────────────────────────────────┘
        ▲ 只开 PR、不写账本
┌── 云端会话 ──┐  每个云端克隆就是它自己的控制根；账本不放云端
```

- 工位规矩（上限、前缀、谁能收）的文字真源是 `AGENTS.md` 的 WS-001，实现在 `application/core/agent_worktree_service.py`（`worktree open/list/close/sweep`）。
- 根入口 `main.py` 发现自己在 `.auto-pm/worktrees/` 或 `.codex/worktrees/` 下面会直接退出（退出码 2，提示 `managed candidate is execution-only; invoke the canonical control root instead`）：**已核**，见根目录 `main.py`。
- **账本只在账本主机上有一本**。跨电脑只通过 GitHub 交换代码，不交换账本。

## 2. 代码怎么变成“现场运行的版本”

```text
SW-2026-008/auto_pm（源码，母体；改它不会让现场变）
   │ PR 合入 main
   ▼
scripts/pmf_build.py build   只从一个已提交的 Git 提交构建载荷（auto_pm 与 templates）
   │ 同一提交两次构建结果一致；开头先跑 main.py doctor --pre-release
   ▼
00_Infrastructure/auto_pm/releases/<版本>/  不可变发布（release_meta.json 记来源提交）
   │ 重门禁（九组）+ release-pregate + 样件联调 + 用户亲口同意
   ▼
改 active_release.json 指针（previous_release.json 记回退用的上一版；写指针必须经母体 DeploymentContainer.write_pointer，原子替换）
   ▼
launcher/launch.py   指针 → 校验 manifest 登记 → 逐文件核 SHA-256 → 以 -B -I 起子进程运行
```

**关键事实**：

1. 驾驶舱命令实际运行的是 `active_release.json` 指向的**发布快照**，不是控制根里的源码。改了源码、PR 合了，现场命令仍是旧行为，要等发版切换。**已核**（`main.py` → `launcher/launch.py` → `resolve_release`）。
2. **载荷只有 `auto_pm/` 和 `templates/` 两个目录**（`scripts/pmf_build.py` 的 `PAYLOAD_DIRS`）。`scripts/`（含总控屏）、`reviews/tools/`、`tests/`、文档**不进载荷**，随 `main` 直接生效。所以“这个修复要不要发版”，看它改没改这两个目录。
3. 启动器是 fail-closed：指针非法退出码 3，发布与 manifest 不一致退出码 4，容器缺文件退出码 2。active 校验不过而 previous 通过时会改用 previous，并在标准错误打警告；active 里只多出 `__pycache__` 不回退，退出码 4 并给出清除命令（`--purge-bytecode`）。**已核**，见 `launcher/README.md`、`launcher/bootstrap.py`。
4. 启动器子进程始终 `-B -I`，不读用户目录和 `PYTHONPATH`，避免有人往发布目录里写缓存。
5. 回退不是万能的：回退本身会造成“运行身份与账本不一致”，账本写命令会被运行身份检查拒绝（`ui/cli/runtime_identity_guard.py`）。这是已知的设计缺口，详见第 9 节。

## 3. 包内分层：`auto_pm/` 五层

允许的依赖方向：`ui → application → domain → contracts`，`infrastructure → contracts`。**这条由机器检查**：`tests/test_layer_import_direction.py` 扫全部 `.py`，出现新的违规就红；已有违规列在 `KNOWN_VIOLATIONS` 里，**只许减少不许增加**（修好一条必须从名单里删掉）。**已核**。

| 层 / 目录 | 放什么 | 例子（已核存在） |
|---|---|---|
| `ui/cli/` | 命令行：Click 命令组，只做参数解析和调用 | `pm.py`、`continuity.py`、`change.py`、`worktree.py`、`doctor.py` |
| `ui/qml/`、`ui/*.py` | QML 桌面界面（老板驾驶舱、专业工作台）及其桥 | `boss_qml_window.py`、`qml/bridges/` |
| `application/core/` | 用例与服务：把领域对象和基础设施串成流程 | `pm_facade_service.py`、`continuity_execution_service.py`、`mission_service.py`、`agent_worktree_service.py`、`pm_closure_service.py` |
| `application/delivery/`、`application/plc/` | 交付物构建归档；PLC 导入 | `delivery_service.py`、`ingest_service.py` |
| `application/*_facade.py`、`api.py` | 给界面和外部用的薄门面；`api.py` 是 SDK 入口，经运行身份检查驱动 PM 门面 | `change_facade.py`、`api.py` |
| `domain/` | 业务规则；按规矩不依赖 application、ui、infrastructure（已知一处例外见本节末） | `change/`（变更单、台账对账、状态流转日志）、`plc/`（检查器、SCL 校验、文档一致性）、`constraint/`（约束检查）、`spec/`、`vartable/`、`project/state_machine.py` |
| `contracts/` | 各层共用的数据结构（DTO、状态枚举、命令契约） | `continuity.py`（Work、Run 状态）、`mission.py`、`plan_checklist.py`、`implementation_card.py` |
| `infrastructure/` | 对外部世界的接口：账本、Git、文件、进程 | `continuity_store.py`、`control_root_guard.py`、`git_hook_enforcer.py`、`lease_wallet.py`、`continuity_backup.py`、`process_probe.py` |
| `templates/` | Copier 模板（项目脚手架、治理文件） | `governance/`、`plc/`、`python_cockpit/`、`industrial_hmi/` |

已知例外（都在 `KNOWN_VIOLATIONS` 里）：`domain/change/decision_service.py` 直接调用 `control_root_guard`；各 `*_facade.py` 引用 `ui.contracts`；`ui/cli/__main__.py` 等 CLI 文件要自己构造账本、租约钱包、进程探针，仍直接引用 `infrastructure`，是否改规则待裁决（见测试文件里的注释）。

## 4. 账本：Continuity v2

账本是一个 SQLite 文件 `.auto-pm/continuity.db`（`infrastructure/continuity_store.py`，不入 Git，只在账本主机上）。它回答三个问题：谁在做哪张卡、做到哪、能不能接着做。

**表（已核，见 `continuity_store.py` 的建表语句）**：`work_items`（Work）、`work_relations`、`run_items`（Run）、`execution_leases`（租约）、`checkpoints`（检查点）、`handoffs_v2`（交接包）、`events`（事件）、`mission_items`（Mission）、`planning_drafts` 及其与变更单、规范、决策的绑定表、`planning_scope_cards`、`closure_items`/`closure_steps`/`closure_outbox`（收口步骤和发件箱）、`run_parks`（搁着的断点）。

**三层对象**：

| 对象 | 是什么 | 状态（已核，见 `contracts/`） |
|---|---|---|
| Mission | 用户眼中的一张卡（一个可恢复的业务任务） | DRAFT → AWAITING_APPROVAL → ACTIVE ⇄ BLOCKED / PARKED → ACCEPTANCE_PENDING → ACCEPTED → CLOSED（或 CANCELLED）。看板分“在干 / 等你 / 搁着 / 已关”四栏 |
| Work | 一个独立授权的工作单元，带可改范围 `scope_paths` | PLANNED、READY、IN_PROGRESS、BLOCKED、VERIFYING、ACCEPTED、CLOSED、CANCELLED |
| Run | 一次执行，持有租约 | READY、RUNNING、BLOCKED、PENDING、VERIFYING、SUCCEEDED、FAILED、CANCELLED |

- **租约**＝操作钥匙。租约默认时长 `DEFAULT_LEASE_SECONDS = 1800`（30 分钟），命令行的 `--lease-seconds` 可选 60～3600 秒（已核，`contracts/continuity.py`、`ui/cli/continuity.py`）。过期后持有者连复位都动不了，要走回收流程。一个 Run 持有租约的总时长有上限（默认 3 小时），要延长用 `continuity lease extend-hold`，这一步属于只能用户做的事（`docs/handover/02`）。租约口令存在 `.auto-pm/cache/lease-wallet/`（`infrastructure/lease_wallet.py`），不出现在命令行参数、输出或 Git 里。长命令用 `continuity lease run-with-renewal` 或 `application/core/lease_keepalive.py` 包住保活。
- **Decision（批准记录）**是文件，不在账本里：`.auto-pm/decisions/DEC-*.json`，入库，由 `domain/change/decision_service.py` 读写；批准用的 `approved_files` 和 Work 的 `scope_paths` 共同决定一张卡能改什么。
- **变更单（CHG）和台账**走另一条线：`domain/change/` 管变更单文件、台账对账（`ledger reconcile`）、状态流转日志；`infrastructure/change_status_guard.py` 要求变更单文件上写的状态必须和记录的流转一致。
- **收口是可恢复的 Saga**：`application/core/pm_closure_service.py`、`pm_saga_service.py` 把“验收之后”的一连串步骤（并回文件、推进 Run/Work/Mission、写变更单证据）记在 `closure_*` 表里，中途断了可以重试（`pm close`）。
- **备份**：`continuity backup / list-backups / verify-backup / restore-backup`，在线备份并自校验（`infrastructure/continuity_backup.py`）。
- 账本主机单点：账本只有一本，机器坏了就丢，备份放哪由用户和协调者定（**未核实**现状）。

## 5. 一张卡怎么走（命令层）

```text
用户一句话 ─▶ pm inbox add（入箱，不改焦点）─▶ pm orient / pm resume（只读定位）
  ─▶ pm plan（范围卡，含计划清单：用户原话、安全回路、验收检查、回退等）─▶ pm approve（用户批）─▶ pm confirm-start（唯一开工确认）
  ─▶ continuity work create/authorize ─▶ continuity run start（拿租约，登记工位）
  ─▶ 在工位里写代码、continuity checkpoint ─▶ pm verify（机器验证，生成系统证据检查点）
  ─▶ 用户验收（界面“确认验收”，或终端 pm accept）─▶ close_accepted 一步收口 / pm close 重试
  ─▶ ledger reconcile（对账）─▶ PR ─▶ 独立审计 ─▶ CI ─▶ Merge commit
  ─▶（若改了载荷）发版 ─▶ 用户亲口同意切换
```

- 顺序的文字真源是 `AGENTS.md` 的“澄清-报批-执行-验收”四阶段；命令清单以 `main.py pm --help` 和 `main.py continuity --help` 为准（已核：pm 下有 accept、acceptance-scan、approve、close、confirm-start、handoff、inbox、missions、orient、park、pending、plan、recover、recover-status、resume、switch、takeover、unpark、verify 等）。
- 一个项目可以开几张卡，但同一时刻只有一张“在干”；插急活用 `pm park / switch / unpark`（`application/core/mission_switch_service.py`、`mission_admission.py`，WS-002）。
- 没有已授权的 Work、Run 和有效租约时，只允许只读命令（`CLAUDE.md` 第 2 条）。

## 6. 护栏分四层

电气类比：联锁分“PLC 程序里的联锁”“硬接线的联锁”“现场安全继电器”“人”。**下面每层的硬度不一样，写进了第 9 节的缺口**。

| 层 | 内容 | 硬度 |
|---|---|---|
| ① 命令层（走驾驶舱流程时） | 租约与口令校验；实施卡预检（`implementation_card_precheck.py`）；声明与 Git 比对；控制根守卫（`infrastructure/control_root_guard.py`，写命令只能在含真实 `.git` 目录的主工作树跑）；运行身份检查（`ui/cli/runtime_identity_guard.py`）；工位策略（`worktree_policy_service.py`）；新卡准入（`mission_admission.py`）；批准口令（`approval_proof_service.py`，**代码已有，是否启用由用户定**） | 硬，**但只在走驾驶舱命令时有效** |
| ② 本机 Git 钩子 | `commit-msg`：生产代码须绑唯一一个 CHG 号（`git_hook_enforcer.py`）；`pre-commit`：PLC 项目文档与代码一致性（`plc_doc_hook.py`）；变更单状态与流转一致（`change_status_guard.py`） | 可被 `git commit --no-verify` 绕过；`hook-replay` 在 CI 里复跑，但只报警 |
| ③ GitHub 层 | `main` 只走 PR；`pr-gate`（改动不超出“可改范围”）、`safety-gate`（安全区须用户本人签字）、`rules-gate`（改规则文件须用户本人评论 `规则批准 <头提交号>`，`reviews/tools/rules_approval_check.py`）、`reviews-tools-ci`；`sw008-ci`、`plc-ci` 等按路径触发 | 硬。**2026-11-02 用接口核过规则集**：`MainPR_Gate` 必过 `gate`、`safety-zone`、`reviews-tools`；`main-protect` 禁删除、禁强推、必须走 PR、评审对话须解决、只许 Merge commit，**要求的批准人数是 0、不要求 code owner 审**，两条的绕过名单都是空。因此一个 Write 账号只要必过检查绿就能合并；`rules-gate` 就是补这个洞的，它是否已设为必过：**未核实**（11-02 核时必过列表里还没有） |
| ④ 人 | 独立审计（`reviews/tools/audit_pr.py` 加清单）、用户验收、用户亲口同意 | 取决于人在不在 |

这些护栏为什么要加：用户的原话见 `04_监控/01_变更管理/02_变更记录/03_需求变更记录.md` 的 RC-001（2026-11-12）。

电气类比的另一面：命令层像 PLC 程序里的联锁，只管经过这个程序的动作；Git 钩子像现场的急停按钮，谁都可能不按；GitHub 层像上游设备的硬接线联锁。

## 7. 入口：命令行、界面与 CI

**命令行**：`main.py` 下共 28 个命令组（已核，`main.py --help`）：`change`、`clean`、`constraint`、`context`、`continuity`、`decision`、`delivery`、`doc`、`doctor`、`dogfood`、`git-hook`、`gui`、`handoff`、`implementation-card`、`ledger`、`plc`、`pm`、`pm-session`、`pr`、`project`、`prototype`、`python`、`role`、`spec`、`template`、`vartable`、`workflow`、`worktree`。`pm-session` 对应已退役的 PM_SESSION，`handoff` 管的是 handoff.v1，两者只作历史证据，现行交接用 `continuity handoff`（handoff.v2）和 `pm handoff`。

**界面**（两套并存）：

| 界面 | 技术 | 说明 |
|---|---|---|
| 总控屏 `scripts/cockpit_board/` | PySide6 普通控件 | 命令行的另一层皮：每个按钮只调用同一条 `main.py` 命令，不持有治理权；按钮白名单在 `policy.py`；不进发布载荷 |
| 老板驾驶舱、专业工作台 | QML（`ui/qml/`，`main.py gui`、`gui --advanced`） | 进发布载荷；总控屏计划作为唯一主界面，这两套退为高级入口（见 `scripts/cockpit_board/README.md`） |

**CI（`.github/workflows`）**：`pr-gate`、`safety-gate`、`rules-gate`、`reviews-tools-ci`、`sw008-ci`（驾驶舱全量测试，按路径触发，改受保护清单的 PR 要手动触发）、`plc-ci`、`plc-tool-ci`、`root-tests`、`hook-replay`、`ci-aggregate`、`release-pregate`、`sample-drill`、`bat-guard`、`gitignore-guard`。

## 8. 质量保障

- **测试**：`tests/` 下 `pytest --collect-only` 收集到 **6996** 个测试项（2026-11-02 在云端沙箱实测，含参数化）。注意：规划文档里曾写“4808”，两个数口径不同，以 `--collect-only` 为准。
- **机器检查**：分层方向（`test_layer_import_direction.py`）、`main.py doc check`（CLI 与文档同步、版本锁一致）、`main.py plc check <项目号>`、`ruff`/`mypy`、编码检查（`reviews/tools/encoding_check.py`）、PR 描述模板检查。
- **无损修复**：任何 repair 或 retrofit 绝不覆盖用户业务核心代码。
- **反作弊**：验证逻辑必须处于只读上下文，不得在断言前触发生成或覆写（`AGENTS.md` 战略基线第 8 条）。

## 9. 已知缺口与未核实

下面几条是**读码或文档汇总得出**，没有一一在真账本上复现；动手前先复核。

1. **护栏互相死锁**：各道联锁一道一道加，没有总图，10-29～11-02 间出现过 6 处“拒绝之后没有出口”的情况（租约过期后续租、回收、新开 Run、结算四条路全堵等）。根治设计在共享文件夹（`驾驶舱护栏死锁根治设计`），分 P0～P3；是否落地以 `main` 为准。
2. **探测盲区**：`pm orient` 自上而下沿 Mission→Work→Run 找，不是扫全表；Work 已验收而 Run 仍 RUNNING、租约早过期的旧 Run 不报（读码，未在真账本核实）。“探测不到”和“没有问题”不应该用同一种表示（用户 10-22 已定：没检查要显示没检查）。
3. **修复靠发版**：见第 2 节。载荷里的修复，合并后到现场生效之间隔着一次发版切换。
4. **账本单点**：见第 4 节。
5. **Git 钩子可绕过**、没有 `CODEOWNERS`、批准人数为 0、agent 身份靠环境变量标记：见第 6 节。
6. **文档债**：`README.md`、`CHANGELOG.md` 的版本说明停在旧版（发版 7 起续写）；活动技术债台账单文件很大。
7. 分层违规清单（第 3 节）里的条目是否清零，要用户或 PM 裁决。

## 10. 改这里会碰到什么（给接手的 AI）

| 想改的 | 是否进载荷 | 要走的路 |
|---|---|---|
| `auto_pm/`、`templates/` | **进** | PR → 独立审计 → CI → 合并 → 发版 → 用户亲口切换 |
| `scripts/`（含总控屏）、`reviews/tools/`、`tests/`、文档 | 不进 | PR → 审计 → CI → 合并，合并即生效 |
| 受保护清单里的文件（`AGENTS.md`、`.trae/`、`.github/workflows/*`、规范库等） | — | 要用户原话；规则文件（`AGENTS.md`、`CLAUDE.md`、`.trae/` 和各 IDE 规则目录、`roles/`、规范库、`.github/`、`reviews/tools/`，完整清单见 `rules_approval_check.py` 的 `RULE_PATTERNS`）的 PR 还要用户本人评论 `规则批准 <头提交号>` 才过 `rules-gate`；PR 的可改范围必须逐字写完整路径；`sw008-ci` 要手动触发一次 |
| 账本、WBS、治理库、发布指针 | — | 只由账本主机上的主执行写，别的 agent 只写“建议回写” |

## 修订记录

| 版本 | 日期 | 说明 |
|---|---|---|
| V2.1.0 | 2026-09-06 | Cockpit OS 全链路上线后的状态（四层图） |
| V3.0.0 | 2026-11-02 | 重写：增加三处位置、发布快照与启动器、五层分层与机器检查、账本、卡的生命周期、护栏分层、已知缺口 |
