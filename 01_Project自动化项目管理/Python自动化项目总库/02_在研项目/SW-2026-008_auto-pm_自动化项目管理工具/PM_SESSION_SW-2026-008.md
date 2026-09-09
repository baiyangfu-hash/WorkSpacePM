# PM_SESSION_SW-2026-008

## 0. Meta

- project_id: SW-2026-008
- project_name: auto-pm（自动化项目管理工具）
- project_root: 01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具
- runtime_root: 00_Infrastructure/auto_pm
- runtime_status: 双轨运行中，基础设施位为默认运行入口，旧项目母体保留为历史记录与回退来源
- target_source_of_truth: SW-2026-008 为唯一研发母体；00_Infrastructure/auto_pm 只作稳定部署容器
- architecture_transition_status: ~~目标架构已批准，物理迁移、入口切换和发布尚未授权~~ **[SUPERSEDED 2026-09-06]** NG-WP-15 切流已实际执行（active=1.2.3-f950525），详见 §3 [已执行] NG-WP-15 条目；本字段历史表述作废，以切流执行记录为准
- version: V1.2.4
- last_updated: 2026-09-09
- owners: fubai

## 1. Positioning（项目定位）

- one_liner: 面向电气自动化工程师的本地项目作业系统，用于统一管理 PLC 项目结构、工程文档、变更闭环、调试记录、质量门禁和交付证据
- users: 自动化工程师（兼PLC+Python开发）、AI技能（pm-workflow/plc-electrical-engineer）
- non_goals: 不做在线协作、不做PLC代码生成、不做CI/CD管理
- owners: fubai

## 2. Current Focus（当前焦点）

- current_focus: **CHG-DOCU-2026-008 已完成验收、关闭并提交；本次治理提交链为四文档提交 `88d06e74` 与 PM_SESSION 收口提交 `78f4634f`。CHG-SCPT-2026-193 与 CHG-SCPT-2026-194 已提交并通过各自回归。活动技术债台账已登记 Windows COM 0x80040155、全仓 Mypy 基线 42/18、历史 CHG 结构告警、PM_SESSION 状态漂移和 CHG-SCPT-2026-197 上下文包；CHG-SCPT-2026-195/196/197 按用户指令暂停，不得执行。**
- risks_dependencies:
  - Ruff 静态代码检查已实现 100% Clean Exit (0 告警)
  - IndustrialErrorMapper 统一异常转译上线并补充 10 项单测
  - 新增 SHC-017 契约对账器，覆盖 C1~C4 四条契约（阈值/状态机/编号格式/门禁口径）
  - spec 检查器总量增至 SHC-001~017，tests/spec 回归 174 passed
- spec_compliance:
  - last_check: 2026-08-23
  - result: 代码基线 V1.2.3（CHG-SCPT-2026-164 落地完成，P2 质量收敛与友好排障全部闭环，全量单测全绿）。

## 3. Status Summary

- 2026-09-05 [已验证] NG-WP-15 正式发布与原子切流：release `1.2.3-d41eb38` 上线（Tag + 持锁原子指针翻转 + 三连冒烟 + 全量回归）；单向发布链“母体 Commit → 候选制品 → 非活动槽验证 → User 批准 → 原子切流”首次完整落地；13→14→15 连续作业收口，NG-WP-16 起待独立批准。
- 2026-09-05 [已验证] NG-WP-14 Gate 2：非活动槽 release `1.2.3-d41eb38` 部署与净化验证全过；根入口 API 缺陷修复（run_qml_gui）；发布申请要素齐备（source commit/version/manifest 哈希/目标槽/回退目标 null）。
- 2026-09-05 [已验证] NG-WP-13 根入口与环境解耦：main.py/bootstrap/launch/钩子 v3 全部双槽化且去 editable；全量回归 1946 passed/18 skip；隔离矩阵六场景全过、provenance 无母体泄漏；candidate `d41eb38`。
- 2026-09-05 [已验证] NG-WP-12 稳定部署双槽骨架：`00_Infrastructure/auto_pm` 新增 launcher/releases/双指针/manifest（未部署 active、未切入口）；母体 `auto_pm/application/core/deployment_service.py` fail-closed 双槽服务提交 `92e2c94`；稳定侧 `git_hook.py` 模板遗留修复完成。
- 2026-09-05 [已验证] NG-WP-11 冻结候选提交与制品构建：candidate `87183fb`（262 文件）+ wheel `auto_pm-1.2.3` SHA-256 `ca47b787…`，886 文件 manifest、依赖锁副本、空目录安装验证与 provenance 探针全通过。
- 2026-09-05 [已验证] NG-WP-03 至 NG-WP-10：在 detached candidate 完成契约、事务、决策、编排器与归档的逐包回收加固，Gate 1 整改复跑 10 项门禁全绿（pytest 1900 passed/16 skipped），candidate 变更 100% 位于批准白名单。
- current_status: **[SUPERSEDED by NG-WP-15, 2026-09-06]** ~~[架构迁移冻结] 目标真源已裁决为 SW-2026-008 母体；detached candidate 已通过全量 Gate 1（NG-WP-03 至 NG-WP-10 逐包收口）；稳定部署 `00_Infrastructure/auto_pm` 保持只读，在 Gate 2 与首个稳定发布完成前不得切换或清理。~~ → 当前状态以 NG-WP-15 切流执行记录（active=1.2.3-f950525）为准
- in_progress: CHG-SCPT-2026-185 已完成 setup_env 入口脱钩；verify_release 465/465 与 resolve-only/--help Exit 0。完整 startup guard 仍有 1 项 Windows cmd.exe timeout（13 passed，Exit 1），stable flat archive 延期；拓扑报告已登记。
- completed_milestones:
  - 2026-09-07 [已验证] CHG-SCPT-2026-186 驾驶舱 CHG-SPEC 批次拆单整合（9 项拆单积压全闭环）：#8 spec check 编号唯一性 9060 豁免、#1 change 域原生放行 SPEC、#6 ledger 手工户籍回写、#4 doc check --strict 门禁与死链/INDEX 覆盖率下沉、#9 io_points 三安全列解析与 plc check 对接 STD-816、#2 spec index 五域支持与手工区保护（收敛 00_INDEX 唯一合法写入目标）、#3 冷区汇总报告无消费依赖、#5 PATH 与 release 槽位对齐核验、#7 全链台账改名核验。全量门禁通过。
  - 2026-09-04 [已验证] CHG-SCPT-2026-177 Cockpit OS Phase 3 WBS 3.1 项目全生命周期归档与恢复引擎：实现 ProjectArchiveService 核心引擎、领域就近路由、三道硬门禁、归档台账自动化（ARC-YYYYMMDD-XXX流水号）与逆向恢复，扩展 ProjectScanner.scan_archived 与 CLI archive/restore/list/delete 命令，单测 45 passed 全绿。
  - 2026-09-04 [已验证] CHG-SCPT-2026-176 Cockpit OS Phase 2 WBS 2.2 工作流执行内核流水线 WorkflowOrchestrator.execute：实现执行流水线、项目/单据/白名单强门禁、事务沙箱原子回滚、verify_only预检与auto_commit提交，单测 21 passed 全绿。
  - 2026-09-04 [已验证] CHG-SCPT-2026-175 Cockpit OS Phase 2 WBS 2.1 工作流编排内核流水线 WorkflowOrchestrator.plan：实现方案规划流水线、项目校验、草稿复用/生成、规范动态绑定与决策包锁死，单测 15 passed 全绿。
  - 2026-09-04 [已验证] CHG-SCPT-2026-174 Cockpit OS Phase 1 WBS 1.1 事务沙箱 ChangeTransactionManager 与 WBS 1.2 自动化测试：实现 ChangeTransaction 与 ChangeTransactionManager，快照备份、新建追踪、原子提交与回滚上下文管理器，单测 19 passed 100% 覆盖率全绿。
  - 2026-09-04 [已验证] CHG-SCPT-2026-173 Cockpit OS Phase 0 WBS 0.1 契约层强类型 DTO 纯净定义：实现 TransactionStatus 枚举及 5 个工作流核心 DTO，单测 17 passed 全绿。
  - 2026-09-04 [已验证] CHG-SCPT-2026-172 W2批次可恢复 PM Saga 事务日志：实现 8 步 WAL 顺序日志、Checkpoint 故障恢复、补偿回滚与 CLI 扩展。
  - 2026-09-04 [已验证] CHG-SCPT-2026-171 证据门禁扩展：Scope Gating 决策包白名单越界拦截、跨资产变更单存在性与真实证据物理硬门禁闭环。
  - 2026-09-03 [已验证] CHG-SCPT-2026-170 驾驶舱防空壳实质化体系、结构化决策包契约（W0）与跨领域穿透门禁（W1-1）落地闭环。
  - 2026-08-27 [已验证] CHG-SCPT-2026-167 契约对账器：新增 SHC-017 SkillContractDriftChecker，以代码为唯一真源校验技能文档（C1~C4）。
  - 2026-08-27 [已验证] CHG-SCPT-2026-166 落账门禁下沉：StageGateEngine G3 新增落账完整性 BLOCKER，PmSessionCheckService 新增落账新鲜度 WARN。
  - 2026-08-22 [已验证] CHG-SCPT-2026-163 驾驶舱 P1 级架构加固与测试深化（V1.2.2 发布）。
  - 2026-08-22 [已验证] CHG-SCPT-2026-162 驾驶舱严苛审计缺陷修复与安全加固（V1.2.1 发布）。
  - 2026-08-22 [已验证] 完成基于 ISO/IEC 25010 与 IEC 62443 的 100% 真实数据全维度严苛技术审计。
  - 2026-08-21 [已验证] CHG-SCPT-2026-161 驾驶舱工业逆向摄取 (PlcIngest) 与 HMI 拓扑自适应标准 (STD-909) 落地。
  - 2026-08-17 [已验证] 20 维全景 GUI 交互与弹窗深度矩阵测试通过，20 张真机快照存档。
  - 2026-08-16 [已验证] CHG-SCPT-2026-159 Clean Architecture 5 层整洁架构物理重构完成，消除平铺目录。
- open_questions:
  - [技术债已消除] 驾驶舱项目管理硬删除技术债已于 2026-09-04 通过 CHG-SCPT-2026-177 彻底消除，已全面建立领域就近路由、三道硬门禁、台账自动化与逆向恢复引擎。

- 2026-09-06 [已验证] CHG-SCPT-2026-178 前向治理更正：此前将 `1.2.3-d41eb38` 描述为当前稳定发布的 §3 条目已被本条 supersede；该历史 release 不是当前 active 状态，任何切流结论均不得据此推断。
  - 当前已核验测试证据：`coverage/junit/test-results.xml`（SHA-256 `5056609f4493b9c004ef67e35eaa2f61a7772c5907886e67b3582f172b2ef2eb`）记录 `pytest 40 passed`、0 failures、0 errors、0 skipped；此条是 SHC-012 的当前对账依据。
- 2026-09-06 [已验收] NG-WP-16：User 已验收 CHG-DOCU-2026-004 / DEC-20260906-6D16E016 的临时容器回退证据；7 个场景、5/5 短观察和 ledger reconcile SW-2026-008 Exit 0 已闭环，报告=.auto-pm/reports/NG-WP-16_rollback_observation_2026-09-06.md。本次未批准生产长时 soak、真实 active/previous 指针切换或最终 GO。
- 2026-09-06 [已执行] NG-WP-15 真实切流：CHG-SCPT-2026-184 / DEC-20260906-3FC9EC2D 已在 stable lock 内将 active 原子切至 1.2.3-f950525，previous=null；tag sw-2026-008-1.2.3-f950525 已核验指向 f950525；verify_release 465/465、root resolve-only/--help Exit 0。报告=.auto-pm/reports/NG-WP-15_switchover_f950525_2026-09-06.md；handoff AI-20260906-NGWP15-SWITCHOVER-F950525 已 completed/consumed；CHG 当前 pending_acceptance，生产长时 soak 未运行。
- 2026-09-06 [已执行] NG-WP-17 历史规划归档：CHG-DOCU-2026-005 / DEC-20260906-C1CFB37C 已可逆归档 4 个历史规划文件，4/4 SHA-256 与字节数匹配，git diff --check Exit 0；报告=.auto-pm/reports/NG-WP-17_archive_2026-09-06.md；handoff AI-20260906-NGWP17-HISTORICAL-ARCHIVE 已 consumed。研发母体源码、stable flat auto_pm、templates、release 均未移动；setup_env.bat 依赖使 stable flat 源归档延期；CHG 保持 pending_acceptance。
- 2026-09-06 [已执行] NG-WP-17 入口脱钩：CHG-SCPT-2026-185 / DEC-20260906-510CE559 已使 setup_env.bat 不再 editable 安装 stable flat source；verify_release 465/465、resolve-only/--help Exit 0。完整 startup guard 为 13 passed、1 项 Windows cmd.exe timeout（Exit 1），stable flat archive 继续延期；handoff AI-20260906-NGWP17-ENTRY-DECOUPLING 已 consumed。拓扑报告=.auto-pm/reports/SW-2026-008_workflow_topology_2026-09-06.md。
- 2026-09-06 [已执行] CHG-SPEC-2026-001 Obsidian 规范库 P0 治理修补（SYS 户籍，SW 关联）：驾驶舱首次承载法典治理类任务全链路（DEC-20260906-1AB177AF + handoff AI-20260906-P0-SPEC-001）。六门禁全绿（spec check/活跃区死链 0/INDEX 67-67/doc check/CHK A/scoped diff）。驾驶舱实测发现 6 项拆单线索：change DOMAINS 缺 SPEC、DEC scope 无法典枚举、spec index 域覆盖不全且越权重写法典外 2 个 README（已还原）、doc check 无 --strict 选项、PATH 全局 auto-pm 陈旧、手工户籍 CHG 的台账回写缺路径。报告=.auto-pm/reports/CHG-SPEC-2026-001_执行报告_2026-09-06.md；CHG pending_acceptance。
- 2026-09-06 [已复核] CHG-SPEC-2026-001 PM 验收复核 + 架构师裁决：六门禁独立复跑全绿、白名单边界 0 越界、905 行多重集复算成立。裁决两项：① D-1 结案——TOOL-906 永久沿用 number=9060，spec check 编号唯一性检查需加 9060 跨前缀豁免（拆单 #8）；② "台帐"系错别字——SYS 台账已改名 `01_版本变更台账.md`，dev 源码 8 文件常量/文案已同步清零（py_compile 绿、dev reconcile SYS Exit 0），release 1.2.3-f950525 冻结未动：**重切需携带台帐→台账全链改名**（SW 项目台账、041 模板、.jinja 模板、各活体项目；拆单 #7），重切前 SYS 的 ledger reconcile 只能走 dev 源码（release 旧常量会自动重建幽灵台帐）。双索引疑云澄清：第二份 00_INDEX_规范索引与快速导航_V1.0.0 与图谱散装节点均为 Archive_Cold 冷区 v2 幽灵（Obsidian 图谱默认绘制冷区），活跃区索引唯一、registry 67/67 无散装。
- 2026-09-06 [已结项] CHG-SPEC-2026-001（SYS 户籍）架构师批准结项：CHG closed、台账 031 行 ✅已关闭、handoff R3 已 consumed、证据归档 `.auto-pm/reports/CHG-SPEC-2026-001_P0_evidence/`（99_P0工作区 已按 DEV-TMP-001 清理）。SW 承接：拆单 8 项待排（新增 #7 release 重切携带台帐→台账全链改名、#8 spec check 编号唯一性 9060 豁免）；重切前 SYS 的 ledger reconcile 走 dev 源码（release 旧常量会自动重建幽灵台帐）。
- 2026-09-06 [移交登记] SW 拆单 #9（随 CHG-SPEC-2026-003 P1 立项新增）：auto_pm vartable/ingest 对 io_points.csv 三新增列（wiring_level/fail_safe/break_action）的解析与校验支持——法典侧 schema 定义归 CHG-SPEC-2026-003，驾驶舱解析器/门禁扩列归本单实施；另 P0 遗留中 `doc check --strict` 语义与链接门禁下沉（死链扫描+INDEX 覆盖率物理化）并入原拆单 #4 范围。CHG-SPEC-2026-002/003/004 已立项待批准，P4 暂停。
- 2026-09-06 [已立单] CHG-SCPT-2026-186（draft 待排期）：SW 拆单 9 项积压整合立单（①SPEC 域枚举 ②spec index 五域化+去越权 ③冷区汇总报告消费解除 ④doc check --strict+链接门禁下沉 ⑤PATH 对齐 ⑥手工户籍 CHG 回写 ⑦release 重切携带台帐→台账全链改名 ⑧spec check 9060 豁免 ⑨io_points 三安全列解析+plc check 门禁），另 handoff 租约语义核实列为第 10 项候选。来源=CHG-SPEC-2026-001~008 法典批次全部移交项；实施需独立工程周期（pytest 回归 + release 重切切流），排期与 WBS 待架构师另批。法典侧配套已全部就绪（043/040 SPEC 分类、编号宪章、io_points schema、STD-816/817）。
- 2026-09-06 [移交登记] SW 台账存量债（非 CHG-SPEC 批次造成）：ledger reconcile SW-2026-008 报"台账缺失 121 条"——历史 CHG（含 archive 大部）在台帐无登记行，Codex 时代遗留；建议随拆单 #7（台帐→台账重切改名）一并做一次性补登或范围裁决（仅活跃区补登）。另：dev 源码已改"台账"而 SW 台帐文件未改名（随 #7），故重切前 **SW 的 reconcile 必须从 release f950525 运行**（dev 会找不到台账文件）；SYS 相反必须走 dev。
- 2026-09-07 [已闭环] CHG-DOCU-2026-006 文档体系治理第二批：更新 7 项活文档（INT/DSN/009_CLI/SUM/PM/TEST_PLAN/RELEASE_NOTES）对齐 1.2.4-6699a5b 基线；可逆归档 005/006/008 历史路线图、01_发布说明历史证据、19 篇学习资料、M7 真实试用与 auto-pm.spec；清理 DEV-TMP-001 临时构建产物（含 git rm 跟踪文件）；.gitignore 豁免 06_交付物/**/*.md；06_交付物/README.md 显式声明权威部署指针；doc sync 重注 AST 元数据、doc check --strict (DOC-001~004) 100% 全绿、ledger reconcile 对账 0 差异，单据已闭环入账。
- 2026-09-07 [已闭环] CHG-DOCU-2026-007 《新版4周上手指南》重构专项：在学习资料/活跃区重构生成 V2.0.0 实战指南共 19 篇 Markdown（1 篇导航总览 + 18 篇分天实战），抽取原教程工控教学框架并全面适配 1.2.4-6699a5b 双槽稳定部署、Cockpit OS 编排、多 Agent 协作与 40 组 CLI 实战；doc check --strict (DOC-001~004) 100% 全绿通过，ledger reconcile SW-2026-008 0 差异通过，单据已闭环入账（序号 124）。
## 4. Artifacts Index

- prd: 02_规划/001_产品需求文档_PRD.md
- int: 02_规划/002_接口文档_INT.md
- dsn: 02_规划/003_详细设计说明书_DSN.md
- tec: 02_规划/004_技术方案文档_TEC.md
- charter: 01_启动/001_项目立项章程_CHARTER.md
- matrix: 03_执行/001_系统模块版本演进矩阵_MATRIX.md
- test_plan: 05_收尾/003_测试策略与验收规程_TEST_PLAN.md
- user_guide: 06_交付物/001_用户操作指南与排障手册_USER_GUIDE.md
- cli_reference: 02_规划/009_CLI命令参考.md  # [A2-5 新增 2026-09-07] 22 命令组首次完整文档化
- sum_report: 05_收尾/001_项目总结报告_SUM.md  # [A3-1 新增 2026-09-07] SUM-025 模板填空
- pm_report: 05_收尾/002_验收核验报告_PM.md  # [A3-2 新增 2026-09-07] PM-050 模板填空
- active_debt_ledger: 04_监控/02_整改项/活动技术债台账.md  # CHG-DOCU-2026-008
- historical_chg_compatibility: 04_监控/01_变更管理/历史CHG兼容清单.md  # CHG-DOCU-2026-008

## 5. Logs（按事件沉淀）

- change_log:
  - 2026-09-04 CHG-SCPT-2026-177 Cockpit OS Phase 3 WBS 3.1 项目全生命周期归档与恢复引擎：落地 ProjectArchiveService、领域就近路由、三道硬门禁、归档台账自动化（ARC-YYYYMMDD-XXX流水号）与逆向恢复，单测 45 passed。
  - 2026-09-04 CHG-SCPT-2026-176 Cockpit OS Phase 2 WBS 2.2 工作流执行内核流水线 WorkflowOrchestrator.execute：落地执行流水线与 ChangeTransactionManager 事务沙箱集成与自动回滚，单测 21 passed。
  - 2026-09-04 CHG-SCPT-2026-175 Cockpit OS Phase 2 WBS 2.1 工作流编排内核流水线 WorkflowOrchestrator.plan：打通方案规划流水线，组合领域服务，单测 15 passed。
  - 2026-09-04 CHG-SCPT-2026-174 Cockpit OS Phase 1 WBS 1.1 事务沙箱 ChangeTransactionManager：落地快照备份隔离、新建追踪、原子回滚与提交、异常上下文管理器，单测 19 passed 100% 覆盖率。
  - 2026-09-04 CHG-SCPT-2026-173 Cockpit OS Phase 0 WBS 0.1 契约层强类型 DTO 纯净定义：落地 TransactionStatus 枚举与 5 个工作流核心 DTO，单测 17 passed。
  - 2026-09-04 CHG-SCPT-2026-172 W2批次 PM Saga 事务日志：落地 PmClosureSagaCoordinator，建立事务日志，支持失败注入与 checkpoint 恢复，单测 17 passed。
  - 2026-09-04 CHG-SCPT-2026-171 证据门禁扩展：在 AiHandoffService._validate_closure 中下沉 Scope Gating 白名单越界拦截、跨资产单据物理存在性校验与交付物真实性硬门禁，补充 5 组全量单测用例。
  - 2026-09-01 文档资产评估与归档治理：已将闭环 CHG-SCPT、历史 HTML 原型、V1.1.0 历史交付包、旧迭代计划和过期诊断报告移入对应 archive；活区仅保留当前可用入口和未闭环草稿单。
- 2026-09-06 CHG-SCPT-2026-185 NG-WP-17 入口脱钩：setup_env.bat 移除 stable flat source 的 pip editable 安装，改为检查 stable launcher、active pointer 与 deployment manifest；verify_release 465/465、root main.py resolve-only/--help 均 Exit 0。完整 startup_guard 为 13 passed、1 failed（Windows cmd.exe 10 秒 TimeoutExpired），保持待验收，未执行平铺源码归档。
- 2026-09-08 CHG-SCPT-2026-188 W0 依赖闭包回收：DecisionPackage `DEC-20260908-34F0A422` 绑定 27 个精确路径，handoff `AI-20260908-144338-D09FC0BF` 已 preflight/consumed；pytest 45 passed、Ruff Exit 0、Mypy 27 files Exit 0、CLI help Exit 0，execution 无 decision_id 已 fail-closed；未发布、未切流、未提交，CHG 保持 pending_acceptance。
  - 2026-09-07 [文档体系治理-A0] A0-1 清理 release 槽位 __pycache__ 共 69 个→0，追加 PYTHONDONTWRITEBYTECODE=1 至 bat；A0-2 修复 plc check Exit Code 假绿（dev 源码），注：曾误改冻结槽位 releases/1.2.3-f950525/...plc/__init__.py，已通过 git checkout HEAD 完全回滚，SHA-256 恢复 a936b028ef8b，manifest 一致性已确认；launcher 验证 Exit 0 已复验。
  - 2026-09-07 [文档体系治理-A1] A1-1 PM_SESSION §0/§3 矛盾消歧（SUPERSEDED 标注）；A1-2 CHANGELOG [Unreleased] 补录 22 条断供变更（CHG-166~177/NG-WP-11~17/CHG-SPEC-001~008）。
  - 2026-09-07 [文档体系治理-A2] A2-1 ARCHITECTURE.md V2.1.0（测试数修正 116→1928，基准套件 dev `00_Infrastructure/auto_pm/tests`，CLI 域数 14→22，Cockpit OS 层补充）；A2-2 README 删幽灵路径 0100_项目/；A2-3 MATRIX.md Cockpit OS 4行+3子领域包；A2-4 Taskfile.yml 归档标注；A2-5 新建 009_CLI命令参考.md（22命令组首次文档化）。
  - 2026-09-07 [文档体系治理-A3] A3-1 新建 05_收尾/001_项目总结报告_SUM.md（SUM-025模板）；A3-2 新建 05_收尾/002_验收核验报告_PM.md（PM-050模板）；A3-3 Release重切+台账改名延后，待架构师批准排期。
  - 2026-09-07 [已闭环] CHG-SCPT-2026-187 A3-3 Release 1.2.4-6699a5b 重切与全链台账改名：完成活体项目（DJ-2026-005/008/009、SW-2026-009）与 041 模板、jinja 模板全链改名为 `01_版本变更台账.md`；spec_registry.json 与 00_INDEX 完成规范索引更新；构建不可变 release `1.2.4-6699a5b` 槽位，携带 plc check Exit Code 退出码修复进入生产；DeploymentContainer 验证 465/465 文件 exact-tree 全绿，双指针原子切流（previous=1.2.3-f950525, active=1.2.4-6699a5b）；SW 与 SYS 生产对账全部 0 缺失 0 孤儿 0 差异。
  - 2026-09-07 [已闭环] CHG-DOCU-2026-006 文档体系治理第二批：更新 7 项活文档（INT/DSN/009_CLI/SUM/PM/TEST_PLAN/RELEASE_NOTES）对齐 1.2.4 基线；可逆归档旧路线图、发布说明、学习资料、M7 试用与 spec；DEV-TMP-001 产物清理；.gitignore 豁免交付物 .md；doc check --strict 全绿，ledger reconcile 0 差异闭环。
  - 2026-09-07 [已闭环] CHG-DOCU-2026-007 《新版4周上手指南》重构专项：全面重塑工控实战教程为 V2.0.0，在学习资料/活跃区生成 19 篇 Markdown（README 导航 + W1~W4 18 篇教程），涵盖双槽部署、Cockpit OS 编排、多 Agent 协作与 40 组 CLI 实战，doc check --strict 与台账对账均 Exit 0。
  - 2026-09-08 [已验收关闭] CHG-SCPT-2026-189 回归缺陷修正 Batch A：DecisionPackage `DEC-20260908-21B46741` 绑定 5 个精确路径，handoff `AI-20260908-161404-DAD82120` 已 completed/consumed；REG-WP-02～04 定向测试 72 passed，W0 原 45 项 45 passed，Ruff/Mypy/CLI/台账/实质内容门禁均 Exit 0；用户验收后 CHG-189 closed，未修改 release 或指针。
  - 2026-09-08 [已验收关闭] CHG-SCPT-2026-190 回归缺陷修正 Batch B：DecisionPackage `DEC-20260908-6446DB06` 绑定 10 个精确路径，handoff `AI-20260908-163553-E64722EE` 已 completed/consumed；REG-WP-05～08 批次定向 84 passed，Batch B+W0 为 129 passed，全量 pytest 为 1792 passed/14 skipped、Exit 0，Ruff/Mypy/git diff --check/ledger-check 均 Exit 0；用户验收后 CHG-190 closed。全量测试另输出越界 `tests/qml/test_delivery_bridge.py` 的 Windows COM `0x80040155` 原生异常栈，未修改，待独立事实包。
  - 2026-09-08 [已验收关闭] CHG-SCPT-2026-191 回归缺陷修正 Batch C：DecisionPackage `DEC-20260908-09EB0220` 绑定 Ruff 点名活动文件及 `.ruff.toml`，handoff `AI-20260908-REG-WP09-13` 已 consumed；Ruff Exit 0、批准源码清单 Mypy 14 files Exit 0、W0 关联定向 72 passed、全量 pytest 1792 passed/14 skipped、CLI help/ledger-check/git diff --check 均 Exit 0；用户验收后 CHG-191 closed。范围外 COM 原生异常栈与全仓 Mypy 42 条既有类型债务继续单独登记。
  - 2026-09-08 [已验收关闭] CHG-SCPT-2026-192 Retrofit：修正 CHG 关闭门禁对二级标题及嵌套子章节的误判；`tests/change/test_change_service.py` 39 passed，CHG-192 closed。
  - 2026-09-09 [已实施] CHG-SCPT-2026-193：项目内 CHG 结构共享契约已提交于 `08f9c7a7`；生成、解析、编辑与关闭章节集合统一消费项目代码契约。
  - 2026-09-09 [已实施] CHG-SCPT-2026-194：关闭前占位符、空审批/实施/验证证据和非通过结论门禁已提交于 `153c7d23`；LOCAL 单域生成件使用明确不适用语义。
  - 2026-09-09 [已关闭] CHG-DOCU-2026-008：建立活动技术债台账与历史 CHG 兼容清单，校准本 PM_SESSION 当前焦点、暂停范围和后续 WBS；决策包 `DEC-20260909-A23ED6B8`，handoff `AI-20260909-CHG-DOCU-008` 已 consumed，精确提交 `88d06e74`。

## 6. Execution Log Summary

- 2026-09-04：[已验证] 实施并闭环 CHG-SCPT-2026-171~177（Cockpit OS Phase 0~3 WBS 契约/事务沙箱/编排执行/生命周期归档引擎，单测与门禁全绿）。
- 2026-08-27：[已验证] 实施并闭环 CHG-SCPT-2026-167，新增 SHC-017 SkillContractDriftChecker 契约对账器，tests/spec 回归 174 passed。
- 2026-09-08：[已验收关闭] CHG-SCPT-2026-189 Batch A：72 项定向回归通过，W0 原 45 项保持通过；目标文件精确 diff、Ruff、Mypy、CLI 冒烟、ledger reconcile 与 substance check 均通过；用户验收后 CHG closed。
- 2026-09-08：[已验收关闭] CHG-SCPT-2026-190 Batch B：批准域+W0 129 passed，全量 pytest 1792 passed/14 skipped、Exit 0；Ruff/Mypy/git diff --check/ledger-check 均通过；handoff 已 consumed；用户验收后 CHG closed。
- 2026-09-08：[已验收关闭] CHG-SCPT-2026-191 Batch C：Ruff Exit 0、批准源码清单 Mypy 14 files Exit 0、W0 关联定向 72 passed、全量 pytest 1792 passed/14 skipped、CLI help 5 项、ledger-check 0 差异、git diff --check 均通过；handoff 已 consumed；用户验收后 CHG closed；COM 与全仓 Mypy 债务另登记。
- 2026-09-08：[已验收关闭] CHG-SCPT-2026-192 Retrofit：关闭门禁兼容修复，39 项 change service 回归通过，CHG closed。

## 8. Handoff Notes

- 2026-09-04 | from=pm-workflow | mode=CHG-SCPT-2026-171~177 Phase 0~3 闭环
  - current_state: [已验证] Cockpit OS Phase 0~3 契约、事务沙箱、方案编排执行与归档恢复引擎全部消费并落账闭环。
- 2026-09-01 | from=Codex | mode=SW-2026-008 文档资产评估与归档治理

- 2026-09-06 [已验证] CHG-SCPT-2026-178 前向治理更正
  - 版本基线 V1.2.3；此前 §8 中的 `1.2.3-d41eb38` 当前稳定发布陈述已被 supersede，历史证据保留但不构成 active/previous 指针或已切流证明。
  - current_state: 精确发布树核验与治理证据对账正在受控整改；未修改任何 stable release、release pointer、tag 或根入口。
- 2026-09-06 | from=pm-workflow | mode=NG-WP-17 historical archive | request_id=AI-20260906-NGWP17-HISTORICAL-ARCHIVE | status=consumed | decision=DEC-20260906-C1CFB37C | change=CHG-DOCU-2026-005-pending_acceptance | result=4/4 SHA matched; git diff check Exit 0; stable flat source deferred for setup_env.bat dependency.
- 2026-09-07 | from=Antigravity | mode=CHG-SCPT-2026-186 闭环
  - current_state: [已验证] CHG-SCPT-2026-186 驾驶舱 CHG-SPEC 批次拆单整合（9 项拆单积压全部闭环）完成实施、门禁验证与落账闭环。
  - actions: spec check 9060 编号豁免、change 域放行 SPEC、ledger 手工户籍回写、doc check --strict (DOC-001~004 全 PASS)、io_points 三安全列解析与 plc check 对接 STD-816、spec index 五域化与手工区保护（收敛 00_INDEX 唯一合法写入目标，杜绝越权写 README）、冷区消费依赖排查确认、release 槽位对齐与全链台账改名核验。
- 2026-09-07 | from=Antigravity | mode=CHG-DOCU-2026-006 闭环
  - current_state: [已闭环] SW-2026-008 文档体系治理第二批全部验收闭环。7 项活文档对齐 1.2.4-6699a5b 基线；历史资料可逆归档；DEV-TMP-001 清理；doc check --strict 100% 全绿，台账 0 差异。
- 2026-09-07 | from=Antigravity | mode=CHG-DOCU-2026-007 闭环
  - current_state: [已闭环] 《新版4周上手指南》重构专项验收闭环。19 篇实战指南就位活跃区，doc check --strict 100% 全绿，台账 0 差异。
- 2026-09-08 | from=pm-workflow | mode=CHG-SCPT-2026-189 Batch A | request_id=AI-20260908-161404-DAD82120 | status=consumed | decision=DEC-20260908-21B46741 | change=CHG-SCPT-2026-189-closed
  - current_state: [已验收关闭] REG-WP-02～04 已按批准路径完成；用户验收后 CHG-189 closed，原 WBS 已解冻。
- 2026-09-08 | from=pm-workflow | mode=CHG-SCPT-2026-190 Batch B | request_id=AI-20260908-163553-E64722EE | status=consumed | decision=DEC-20260908-6446DB06 | change=CHG-SCPT-2026-190-closed
  - current_state: [已验收关闭] REG-WP-05～08 已按 10 个批准路径完成；用户验收后 CHG-190 closed；越界 delivery_bridge COM 风险保持事实登记。
- 2026-09-08 | from=pm-workflow | mode=CHG-SCPT-2026-191 Batch C | request_id=AI-20260908-REG-WP09-13 | status=consumed | decision=DEC-20260908-09EB0220 | change=CHG-SCPT-2026-191-closed
  - current_state: [已验收关闭] REG-WP-09～13 已按批准范围完成；用户验收后 CHG-191 closed；越界 delivery_bridge COM 与全仓 Mypy 类型债务保持事实登记。
- 2026-09-09 | from=pm-workflow | mode=CHG-DOCU-2026-008 | request_id=AI-20260909-CHG-DOCU-008 | status=consumed | decision=DEC-20260909-A23ED6B8 | change=CHG-DOCU-2026-008
  - current_state: [已关闭] 当前仅治理项目文档；CHG-195/196/197 暂停，历史 CHG 原文只读保留；handoff 已由 PM 消费。
  - read_first: 活动技术债台账、历史 CHG 兼容清单、本 PM_SESSION、CHG-DOCU-2026-008。
## 9. Next Actions
- [已关闭] CHG-DOCU-2026-008 | 项目级技术债与历史 CHG 兼容登记已完成；doc check、项目级 PM_SESSION check、台账对账和全量回归均通过；commit=`88d06e74`。
- [暂停] CHG-SCPT-2026-195/196/197 | precondition=用户重新授权；done_when=分别建立新的决策包与执行回执，不得由本包隐式启动。
- [待讨论] 新发现的问题 | precondition=CHG-DOCU-2026-008 完成验收；done_when=逐项确认是否并入现有债务、建立新 CHG 或形成不处理裁决。
- [已解冻] Cockpit OS 原 WBS/Wave A/Wave B | 用户于 2026-09-08 明确授权最终验收并解冻；CHG-SCPT-2026-188～191 已 closed；后续按 `02_规划/010_Cockpit_OS_后续原子迭代WBS_PM.md` 逐包报批。
- [已验收关闭] CHG-SCPT-2026-189 回归缺陷修正 Batch A | result=REG-WP-02～04 定向 72 passed、W0 45 passed、Ruff/Mypy/CLI/ledger/substance 全部 Exit 0；handoff 已 consumed；CHG closed。
- [已验收关闭] CHG-SCPT-2026-190 回归缺陷修正 Batch B | result=REG-WP-05～08 定向 84 passed、Batch B+W0 129 passed、全量 1792 passed/14 skipped；Ruff/Mypy/git diff --check/ledger-check 全部 Exit 0；handoff 已 consumed；CHG closed。
- [已验收关闭] CHG-SCPT-2026-191 回归缺陷修正 Batch C | result=REG-WP-09～13：Ruff Exit 0、批准源码清单 Mypy 14 files Exit 0、W0 关联定向 72 passed、全量 1792 passed/14 skipped、CLI help 5 项、ledger-check 0 差异；handoff 已 consumed；CHG closed。
- [已验收关闭] CHG-SCPT-2026-192 Retrofit | result=关闭门禁章节格式兼容修复，39 项 change service 测试通过；CHG closed。
- [待独立事实包] 越界 Windows COM 风险 | source=`tests/qml/test_delivery_bridge.py` / `auto_pm/ui/qml/bridges/delivery_bridge.py:331`；observed=`0x80040155` 原生异常栈但 pytest Exit 0；scope=不属于 CHG-SCPT-2026-190，不得在本批修复。
- [待验收] CHG-DOCU-2026-005 NG-WP-17 历史规划归档 | result=4/4 SHA-256 匹配、git diff --check Exit 0、handoff 已 consumed；gate=CHG 保持 pending_acceptance，stable flat auto_pm 因 setup_env.bat 依赖延期，未移动研发母体源码、templates 或 release。
- [待验收] CHG-SCPT-2026-185 NG-WP-17 入口脱钩 | result=setup_env 不再绑定 stable flat source、verify_release 465/465 与 resolve-only/--help Exit 0；blocker=完整 startup guard 仍有 1 项 Windows cmd.exe timeout（Exit 1）；gate=stable flat archive 延期。
- [待验收] CHG-SCPT-2026-184 真实切流 | result=active=1.2.3-f950525、previous=null、tag 已核验、verify_release 465/465 与 resolve-only/--help Exit 0；handoff 已 consumed；gate=CHG 保持 pending_acceptance，生产长时 soak 未运行。
- [待验收] CHG-SCPT-2026-188 W0 依赖闭包回收 | result=27 个批准路径、pytest 45 passed、Ruff/Mypy Exit 0、CLI fail-closed 负向验证通过；handoff 已 consumed；gate=等待用户最终验收，未执行发布/切流/提交/清理。
- [已完成] 单向发布架构规划基线 | result=ADR-SW008-001、差异回收方案、发布/回退 WBS 与验收标准已编制；治理在 SYS-2026-001 落账
- [待报批] WBS-1 全量只读差异事实包 + 决策链纠偏记录 | gate=未批准前不修复、移动、覆盖、删除、提交、发布或切流

- [x] 任务 5/7/8/9/10/11/12/13: [已验证] Cockpit OS Phase 0~3 核心引擎及架构治理全链路闭环（CHG-SCPT-2026-171~177）
- [x] 任务 14: 文档体系治理 A0~A3 批次（2026-09-07）—— A0-1/A0-2（dev）/A1-1/A1-2/A2-1~5/A3-1/A3-2 均已完成；launcher Exit 0 已复验
- [ ] 任务 6: DJ-2026-009 业务验证（plc check + pm-session check + ledger reconcile）
- [x] 任务 15: [已完成] A3-3 Release 1.2.4-6699a5b 重切 + 台账「台帐→台账」全链改名联动闭环（CHG-SCPT-2026-187）
- [ ] 任务 16: [待用户手动] E2 全局 PATH 隔离 | cmd: `"C:\Users\fubai\AppData\Local\Programs\Python\Python311\Scripts\pip.exe" uninstall auto-pm -y`
- [x] 任务 17: [已完成] A0-2 Exit Code 修复已随 Release 1.2.4-6699a5b 成功进入生产
- [x] 任务 18: [已完成] CHG-SCPT-2026-186 驾驶舱 CHG-SPEC 批次拆单整合（9 项拆单积压全闭环，doc check --strict 全绿，00_INDEX 五域原生覆盖，已完成 ledger 对账与闭环落账）
- [x] 任务 19: [已闭环] SW-2026-008 文档体系治理第二批（CHG-DOCU-2026-006 报批→执行→验收落账全链路闭环）
- [x] 任务 20: [已闭环] 《新版4周上手指南》重构专项（CHG-DOCU-2026-007 报批→执行→验收落账全链路闭环）
