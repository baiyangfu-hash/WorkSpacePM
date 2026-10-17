# M3-PLUGIN｜插件命令行接入驾驶舱门禁实施卡 V1.4（TD-SW008-129 的处置）

> 卡片编号：`CARD-SW008-M3-PLUGIN`
> 版本：`V1.4`（2026-10-13；最终字节报 SHA 后冻结，执行期间不得修改；V1.0 为 `2ca7d6ad…`，G2 失败；V1.1 为 `67a6e1f0…`，其运行 -002 被叫停；V1.2 为 `670f396d…`，其运行 -003 因本机负载使 qml 组超时而硬停止；V1.3 为 `85f78162…`，其运行 -004 在 core 组中途被 Windows 更新强制重启打断）
> 状态：`PLANNED / PRE-AUTHORIZED`（用户 2026-10-13 夜间说“我不玩游戏了，我给你预授权，按照规划继续任务，明早5点汇报任务进度”；V1.4 的产品字节与 V1.1～V1.3 完全相同，只换 Work/Run -005；**启动前必须核对本机负载（无游戏/重程序在前台），门禁期间用户不再运行重程序**；条件见 §7）
> 档次：**产品档**（分档器：`auto_pm/…` 与 `templates/…` 命中产品规则、`tests/…` 命中测试规则，取最高档；不得降级）
> 依赖：卡 126（M3-WBS18）的 Run/Work 已达技术终态且 CHG-DOCU-2026-042（SYS-2026-001）已收口（由启动脚本核验）
> 隔离基线：`07980d4b85abe05a8690422ab164fb10414640c0`（卡 126 的提交，本地分支 `codex/m3-wbs18-v3034`，在卡 125、124 的提交之上，已推送线 `dcfca387` 之上三个提交）
> 路径根：`.`
> 执行模型：`claude-sonnet-5-5`；GPT 只做审计
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-13）

0. **V1.1 与 V1.0 的差别（唯一的实质变化）**：V1.0 的正式门禁在 G2 的 core 组失败——`tests/core/test_plc_quality_gate.py` 与 `tests/core/test_plc_checkpoint_chain.py` 共 20 个用例失败（1128 通过/20 失败/1 跳过，基线 1142 + 6 新增），其余 8 道门禁全部通过、8 个变异全部被杀。原因：两个文件共用的“好样例”`GOOD_SCL` 是没有块头的裸语句（`IF "FirstScan" THEN ; END_IF;`），新的结构规则 `LSP-905-STRUCT-NO-BLOCK` 正确地拒绝了它——这是**旧夹具不是合法 SCL**，不是规则过严（同一规则也挡住了 `plc-test-suite` 模板里没有块头的 `OB1.scl`，本卡已一并修正）。V1.1 把该夹具改为合法的最小 `ORGANIZATION_BLOCK OB1 … END_ORGANIZATION_BLOCK`（1 行改动），其余冻结字节与 V1.0 完全相同，所以路径数从 20 变为 21。开发工作树里这两个文件 32/32 通过（非治理）。我的疏漏：开发期没有跑 core 组里与 PLC 相关的这两个文件。V1.0 收尾：Run `RUN-SW008-M3-PLUGIN-001` FAILED、Work BLOCKED，变更单 CHG-SCPT-2026-413 仍在 implementing（V1.1 沿用），现场保留在 `.auto-pm/worktrees/m3-plugin`；回执 `.auto-pm/reports/m3-plugin/hard_stop_receipt.txt`。**V1.1 收尾**：运行 -002 启动后约 4 分钟被我停止（门禁与续租进程已杀；Run `RUN-SW008-M3-PLUGIN-002` FAILED、Work `WORK-SW008-M3-PLUGIN-002` CANCELLED，没有候选提交、没有推送）；现场保留在 `.auto-pm/worktrees/m3-plugin2`，证据在 `.auto-pm/reports/m3-plugin2/`；变更单仍 implementing（V1.2 沿用）。因此 V1.2 与 V1.1 的受治理字节相同，区别只在 Work/Run/Checkpoint/Decision 的编号、分支名和证据目录。**V1.2 收尾**：运行 -003 在 qml 组以退出码 124 失败（`tests/qml/test_pm_cockpit_bridge.py` 的“真实启动”用例自带 180 秒看门狗，在 20:19 到期后 `os._exit(124)`），其余 8 组与 8 个变异全部通过，随后硬停止（Run -003 FAILED、Work -003 BLOCKED，没有候选提交，现场在 `.auto-pm/worktrees/m3-plugin3`，回执 `.auto-pm/reports/m3-plugin3/hard_stop_receipt.txt`）。**根因（Opus 诊断，只读，证据 `.auto-pm/reports/m3-plugin3/evidence/root_cause_note.txt`）**：不是产品代码，也不是 git 卡死——19:21 起本机在前台运行游戏，门禁各组从 19:22 起整体慢 2～3 倍，该用例正常 67～75 秒，超过了 180 秒看门狗；20:48 在同一份候选字节上、机器空闲时单跑 73.26 秒通过。栈里的 git 只是看门狗到期时线程恰好在做的事。因此 V1.3 的产品字节不变，只改编号并增加启动前的负载核对（见 §8 第 0 步）。看门狗余量偏窄（约 2.4 倍）是独立的稳健性问题，不在本卡范围，另立卡。**V1.3 收尾**：运行 -004 于 2026-10-13 21:08 启动（机器安静，无游戏进程），前 9 个输出全部通过（rest 892 通过/13 跳过、application、plc、change、contracts、infrastructure、qml_debounce_alone、cli、qml 均退出码 0）；最后一组 core 跑到约 65% 时，机器被 Windows 更新（TrustedInstaller，事件 1074）在 23:32 起连续强制重启三次，门禁进程随之消失，没有 `core.exit`，没有判卷，没有候选提交，续租在 23:09 之后无人续上，租约过期；core 的部分输出里有 F/E 标记（集中在 64%～65%，约 6 个测试文件），**事后在同一份候选字节上单跑这些文件的复核结果见 `.auto-pm/reports/m3-plugin4/evidence/diag_core_failures_20261014.txt`**。Run `RUN-SW008-M3-PLUGIN-004` 因租约过期停留在 RUNNING（只有 `settle-expired` 可收，需另行授权，不在本卡内处置），Work -004 已记 BLOCKED，变更单 CHG-SCPT-2026-413 仍 implementing（V1.4 沿用）。现场保留在 `.auto-pm/worktrees/m3-plugin4`。
1. **为什么**：用户的 PLC 门禁实际依赖 VS Code 插件 Dynamic Siemens Language Support 的命令行（`siemens-lsp check` 诊断、`test` 运行 `.scltest`，有错退出码为 1）。驾驶舱的 `plc check` 此前**不调用它**，所以插件拒绝的项目驾驶舱全绿；而且 `plc check` **无论结果如何退出码都是 0**，无法按“物理 Exit Code 判卷”（AGENTS 第 5 条）。卡 124 已把模板修到插件 `check`/`test` 退出码 0；本卡把插件接进驾驶舱的门禁。
2. **做什么**（产品代码 6 个文件改、2 个文件新增，测试 7 个文件改、6 个文件新增，模板 1 个文件改；见 §4）：
   - **适配器**（新增，基础设施层）：只在本机调用已安装插件的命令行——定位顺序为环境变量 `AUTO_PM_SIEMENS_LSP`，其次 `~/.vscode/extensions` 下版本号最高的插件目录里随平台的程序；**找不到不是通过**，返回“不可用”；调用时把临时目录指到一次性的临时文件夹（`test` 会留下生成输出）；退出码非零而没解析到诊断行也算失败。**不复制、不分发、不放进仓库或 CI**（用户为非商业使用并尊重其著作权）；证据里只记版本与哈希。
   - **范围**：标准项目有两层 `.plc.json`（工程根与 `02_PLC程序/PLC_ST`），程序源码在内层，插件的 `test` 在外层会报“entry block OB1 not found”；因此命令行在“自己名下有源文件的 `.plc.json` 目录”上运行（标准项目为内层，活体基准项目为工程根），多个范围合并结果，`archive`/`_archive` 不扫。
   - **检查器**：`PlcChecker` 可注入语言服务；新增检查项“Siemens 语言服务 check”（有 `.scltest` 时再加“… test”）。找不到插件为“未验证”**警告**（`plc check` 不因此失败），有诊断错误或退出码非零为**失败**。不注入时（单元测试与不需要的调用方）行为不变，`CHECK_ITEMS` 静态清单不变。
   - **`plc check`**：默认带这一层，`--no-language-service` 关闭；**有失败项时退出码为 1**（单项目与 `--all`）。这是行为变更：此前总是 0。仓库内没有脚本依赖旧行为（只有测试，已按新语义更新）。
   - **阶段门禁**：`G4`（监控→收尾）增加 `G4-PLC-LANGUAGE-SERVICE`（BLOCKER）；找不到插件算“未验证”并**拦住交付**；同一门禁里“整份文档缺失”（平时只是警告、可由 `plc docs sync` 补全）在交付阶段也拦住——这是用户 2026-10-13 的裁决（“变量文档缺失到交付阶段升失败”）。引擎的语言服务可选，`workbench_use_cases` 的组合根注入真实实现。
   - **结构完整性规则**（`SclLinter`）：`LSP-905-STRUCT-NO-BLOCK`（文件里没有任何块或类型声明）与 `LSP-905-STRUCT-UNCLOSED`（声明数与 `END_*` 数不配对）。理由：插件对空文件与乱码单文件同样报 0 诊断（勘测实测），由驾驶舱补。对全仓库 106 个已跟踪 `.scl` 与全部模板源文件扫描，**只发现一个**：`plc-test-suite` 模板的 `OB1.scl.jinja`（以及 DJ-2026-011 里由它生成的同款文件）是没有块头的裸语句——这是真实缺陷，本卡把模板补成合法的 `ORGANIZATION_BLOCK OB1 … END_ORGANIZATION_BLOCK`（不引入变量，避免新增“缺变量文档”警告），插件 `check` 仍为 0 个错误。
   - **V08 收紧**：`test_pmf_template_plc.py` 新增 4 个用例——真实插件下生成工程 `check`/`test` 退出码 0 且 2/2 用例、裸 `CONST` 块被插件拒绝、复位不写输出被插件 `test` 拒绝（插件不在则显式跳过并标 UNVERIFIED），以及驾驶舱结构检查对被清空的 `OB1.scl` 失败（不需要插件）。
3. **本卡带来的、用户应当知道的后果**：
   - 驾驶舱 `plc check DJ-2026-005` 现在**失败（退出码 1）**：插件 `check` 8 个错误、`test` 2 个问题——正是 TD-SW008-132 登记的、用户裁决“有意保留作驾驶舱实测对象”的那些；**本卡不修改 DJ-2026-005**。勘测已在其副本上用本卡的代码验证过（pass 67、warn 1、fail 2）。
   - DJ-2026-011（A6 验证套件）的 `OB1/OB1.scl` 会被结构规则判失败（与模板同款缺陷）；本卡不改它，登记为债务由后续卡处理。
   - 没有装插件的机器（含 CI）上，`plc check` 多一条“未验证”警告，阶段门禁在交付阶段被拦住；新增的 3 个真实插件用例在那里显式跳过。
4. **不做什么**：不改 AGENTS.md（“语法白名单”措辞更正另卡）、不碰 Obsidian 规范库、不改 DJ-2026-005 与 DJ-2026-011、不接入 `evidence_collection_service` 的受治理证据采集（另卡）、不改 `CHECK_ITEMS`、不推送（收口后按用户已给的允许单独做）、不合并 main。
5. **开发期实测**（开发工作树，非治理）：新增与相关的测试全过（适配器 11、检查器 6、范围 8、结构 11、CLI 4、阶段门禁 6；`tests/plc`、`tests/cli`、`tests/application`、`tests/contracts`、`tests/infrastructure` 共 1062 项在更新 8 处因退出码与交付门禁语义而过期的断言后全部通过）；`ruff check auto_pm tests` 与 `mypy --platform win32 auto_pm` 干净；真实插件下 `plc check` 端到端：模板生成的工程退出码 0（check 与 test 项均通过），放回裸 `CONST` 块后退出码 1。
6. **容忍规则**：沿用 M3-RACE 的同一条具名规则（事先声明）：rest 组里若恰有 r09 一个失败且同字节隔离重跑 3/3 通过则放行并记偏差；此前所有受治理卡均严格全绿（未使用）。
7. **演练事实（非治理，草稿工作树，不是正式证据）**：2026-10-13 在基线 `07980d4b` 的临时工作树里安装 V1.4 的冻结文件（与 V1.1～V1.3 同字节）后跑了本卡的快速门禁脚本（原始输出在 `.auto-pm/reports/m3-plugin5/gates_rehearsal/`）：基线与候选的健康测试相同；4 个真实插件/结构用例通过且无跳过；真实 `plc check` 在模板生成的工程上退出码 0、语言服务 check 与 test 两项通过，放回裸 CONST 块后退出码 1 且 check 项失败；阶段门禁项在好工程上通过、在坏工程上失败；`ruff` 与 `mypy` 干净；8 个真实变异各被预期测试杀死并按字节还原；四棵树的差异恰为冻结的文件；真实 pre-commit 钩子对暂存的 21 个文件退出 0；九组用合成输出（卡 124 输出的副本，通过数按期望增量调整）走判卷，G1–G9 全 PASS，4 个反例变体判卷结果各符合预期。**V1.1 的演练已补做 V1.0 漏掉的一步**：开发工作树里把 `tests/core/test_plc_quality_gate.py` 与 `tests/core/test_plc_checkpoint_chain.py` 的 32 个用例整体跑过（全过）。演练不是正式证据，正式 Run 完整重跑。

## 2. 单一目标与完成定义

插件命令行成为驾驶舱 PLC 门禁的一层，`plc check` 能靠退出码判卷，找不到插件不被当作通过，交付阶段拦住未验证与缺文档，且驾驶舱自己的九组回归只多出本卡的新用例。技术完成 = 全部门禁通过且提交字节等于冻结清单；变更单收口按用户委托在 G1～G9 全 PASS 且提交字节等于冻结清单后代为执行。

## 3. 实施前预检

1. 核对卡字节与已报告的 SHA 一致、基线分支仍在基线、13 个已改文件的基线 blob 等于冻结哈希、8 个计划新增路径在基线上不存在、卡 126 的 Run/Work 为 SUCCEEDED/CLOSED、CHG-DOCU-2026-042 completed、插件 2.17.2 已安装。启动脚本有只读的 `--check-only`。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. **续租**：门禁启动前先用绝对路径启动续租循环并确认日志里有 `first renewal ok`。
4. **正式门禁期间不并发其他重任务**（TD-SW008-095）；整次运行预计约 2 小时 45 分钟（九组回归约 2 小时 35 分钟，其余为真实插件端到端与 8 个变异）。

## 4. 精确 Owned Paths（21）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/application/core/gates/stage_gate_engine.py` | 存在 | G4 增加 G4-PLC-LANGUAGE-SERVICE；整份文档缺失在交付阶段也拦住 |
| 2 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/application/workbench_use_cases.py` | 存在 | 阶段门禁的组合根注入真实语言服务 |
| 3 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/plc/checker.py` | 存在 | PlcChecker 可注入语言服务；新增检查项“Siemens 语言服务 check / test”（找不到为未验证警告） |
| 4 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/plc/language_service.py` | 计划新增 | 新增：领域端口与结果类型（LanguageService、LanguageServiceResult）、PLC 范围识别（plc_scope_roots）、结果汇总（evaluate_project） |
| 5 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/plc/scl_linter.py` | 存在 | 新增结构完整性规则 LSP-905-STRUCT-NO-BLOCK / -UNCLOSED |
| 6 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/plc/service.py` | 存在 | PlcService 把语言服务交给检查器 |
| 7 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/infrastructure/siemens_language_service.py` | 计划新增 | 新增：适配器——定位并调用本机已安装插件的命令行 check / test，找不到为“不可用”（不复制、不分发） |
| 8 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/ui/cli/plc/__init__.py` | 存在 | plc check 默认带语言服务层、新增 --no-language-service、有失败项退出码为 1 |
| 9 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/templates/plc-test-suite/template/OB1/OB1.scl.jinja` | 存在 | 补上 ORGANIZATION_BLOCK 块头与块尾（新规则发现它是没有块头的裸语句） |
| 10 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/cli/test_ai_context.py` | 存在 | 1 个用例的期望退出码改为 1 |
| 11 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/cli/test_plc.py` | 存在 | 5 个用例的期望退出码改为 1（这些最小工程有失败项） |
| 12 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/cli/test_plc_language_service.py` | 计划新增 | 新增：plc check 的语言服务层与退出码 4 个用例 |
| 13 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/cli/test_project.py` | 存在 | 规范快照用例加 --no-language-service（它只看规范快照） |
| 14 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_plc_quality_gate.py` | 存在 | 共用夹具 GOOD_SCL 由“没有块头的裸语句”改为合法的最小 ORGANIZATION_BLOCK（V1.0 的失败原因） |
| 15 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_stage_gate_language_service.py` | 计划新增 | 新增：阶段门禁语言服务项 6 个用例 |
| 16 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_stage_gate_plc_docs.py` | 存在 | s06 改为“整份文档缺失在交付阶段拦住” |
| 17 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/e2e/test_pmf_template_plc.py` | 存在 | V08 收紧：4 个真实插件/结构用例（插件不在则显式跳过） |
| 18 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/plc/test_checker_language_service.py` | 计划新增 | 新增：检查器语言服务项 6 个用例 |
| 19 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/plc/test_language_service_adapter.py` | 计划新增 | 新增：适配器 11 个用例 |
| 20 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/plc/test_language_service_scope.py` | 计划新增 | 新增：PLC 范围与结果汇总 8 个用例 |
| 21 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/plc/test_scl_linter_structure.py` | 计划新增 | 新增：结构规则 11 个用例 |

出现第 22 条候选变更即停止。准备和证据落点（`.auto-pm/reports/m3-plugin5/`、本卡文件、演练工作树与临时目录）不是额外 owned paths。

## 5. 字节合同

### 5.1 参考字节指纹

最终 SHA-256；13 个已改文件的基线（`07980d4b` 上的）blob SHA-256 在 `plugin5_config.json` 与启动脚本里冻结，8 个新增路径无基线。

| # | 路径 | 基线状态 | SHA-256 |
|---|---|---|---|
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/application/core/gates/stage_gate_engine.py` | 存在 | `51c6749bb9ca6d3085f496a733cc4b8b1667422a9ad09d32c9c669e86f53c2c8` |
| 2 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/application/workbench_use_cases.py` | 存在 | `5ed691e9e4ae1ff6dbb3017c90095efb5e48dda14b402998ae6e90d95b627067` |
| 3 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/plc/checker.py` | 存在 | `1229f96d9ab8c4b5955a5df9cdf1e6e383a770487f1e2bc1ba0d5623d89d9e5a` |
| 4 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/plc/language_service.py` | 计划新增 | `b5e5b38998488d2fbcb0b4d932bc2560ea5188654d39032c789b0d8cd13ea1d6` |
| 5 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/plc/scl_linter.py` | 存在 | `581ced17f0052d4d7fd96c9d0184cba53a71c3c3c1c83c9eba4a884632b75280` |
| 6 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/plc/service.py` | 存在 | `991899c0edfe8ef73b93539b25f5365b84b123ddacb39ad88236c987626be6e9` |
| 7 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/infrastructure/siemens_language_service.py` | 计划新增 | `5df8327aa6add85b2b5314989a529801ef862b9f5d57009adb84bccb9905adc3` |
| 8 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/ui/cli/plc/__init__.py` | 存在 | `b867a1e34a3f8364fbb18e4ef0a2d94d366acd6d9d73c35013df0f4aac312b74` |
| 9 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/templates/plc-test-suite/template/OB1/OB1.scl.jinja` | 存在 | `6663312f3ff6c965b8f078fcdcbc56b75b67282fe023aa5fdb93896f6825ad4d` |
| 10 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/cli/test_ai_context.py` | 存在 | `83da8ee35f85187fd7823c7ea77ae53bfa742a5601b2873fd9e711573b462e45` |
| 11 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/cli/test_plc.py` | 存在 | `0eeed17bf6ecea01c7a2ea3f3d920e7e1c78033d8714478ca16f24689e0cff3a` |
| 12 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/cli/test_plc_language_service.py` | 计划新增 | `554775e831cd31eced51a42c32db4801d69d2dbd5b3dd54737be13275cb1ec3a` |
| 13 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/cli/test_project.py` | 存在 | `92bcba8bd52262e1c4efabceaee9349854c663ef3382a96be65581579d1b4e07` |
| 14 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_plc_quality_gate.py` | 存在 | `087b8f95ec3c2e3016e435b196dc0544dac694134111d1c3dd5b245b62381b33` |
| 15 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_stage_gate_language_service.py` | 计划新增 | `fbe145c2c022e871dc76fb287694abebbe0614875b315561f5d5b825f983aac7` |
| 16 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_stage_gate_plc_docs.py` | 存在 | `f4c6bbca91f7f7cfa577dc05b650cf0948feb8a9262e8032aa44e174b72fcafc` |
| 17 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/e2e/test_pmf_template_plc.py` | 存在 | `47c47a565cf805c850096a10beb0cf8ed9c9d29ead6669b9e7e5bc3463c8a743` |
| 18 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/plc/test_checker_language_service.py` | 计划新增 | `03b1ad49a9bbb2d8547559ab7bbc47e2095ec27768385e47cea18d0183ade423` |
| 19 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/plc/test_language_service_adapter.py` | 计划新增 | `3df089f24f8cb4a076f278db02f5661501bebb3240e814b84c1bd4756d14a3f7` |
| 20 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/plc/test_language_service_scope.py` | 计划新增 | `a83b8a7628f6fe14855915d2d6764b8e3245be5af9f97b68d28eb94eb300f3f2` |
| 21 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/plc/test_scl_linter_structure.py` | 计划新增 | `fe729bc0c8360f0793209f09b4c6719d27a680754ca3c1e5ec4cf5e1a4e000e6` |

### 5.2 冻结工具

工具与脚本在 `.auto-pm/reports/m3-plugin5/`；清单文件 `reference_manifest.json` 的 SHA-256 为 `e9ef9747d89c9b5c6d7ddfe0239f1c526eaca9bf6fe190e153dfeaf892a80cc6`。G2 的基线是卡 124 受治理执行的九组真实输出（`.auto-pm/reports/m3-plugin5/baseline_g2/`，同一产品字节）；期望的增量为：plc 组 +36、cli 组 +4、core 组 +6、rest 组 +4，其余各组不变。

| 工具 | SHA-256 |
|---|---|
| `adjust_counts.py` | `3be71108779dd23bcc742186b5048c82e6a0c29de6998e80318d5587dcda595f` |
| `commit_msg.template.txt` | `dba648af36b90f180618ce1e8eae0964064fb2e6f45f0380655899b615907a5c` |
| `gen_project.py` | `eac50737f52b35b23b3c9b23583ac819940a042f71109f9cc96ceaa435e06565` |
| `install_files.py` | `8606df5f6b08caf96e1afb05a52c4136db7c43270acdf0bd4ab03ae625eed5d5` |
| `plugin5_config.json` | `27bea811e04835e2a7351de3ae3b72d06a647347daf3dfe466566b1063d9ac65` |
| `plugin5_gates.py` | `3a396b3263384fb71907d8be23ea484912b24f34196a7d318ea486a3cbf456b3` |
| `plugin5_gates_all.sh` | `a0355c5daabf586508ae605011dd969ef391244c855bdd49da23a72248ac1909` |
| `run_g2.sh` | `6956748a33added47bde7bca81e837230d6e461e746f48da7a0770499cd578fc` |

## 6. 门禁矩阵

产品档。顺序：基线测量（身份、健康测试、插件身份）→ 安装冻结文件 → 快速门禁（健康测试、真实插件用例、真实 `plc check` 与阶段门禁端到端、静态、8 个真实变异、四棵树、真实 pre-commit 钩子干跑）→ 九组回归（G2，十个输出）→ 瞬时竞态测试的三次隔离重跑（仅在其于组跑里失败时才被判卷采用）→ 判卷。任一非零立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 基线身份与健康测试 | HEAD 为基线、工作树干净、13 个已改文件为基线字节、8 个新增路径不存在；夹具健康、冒烟、导入测试在基线与候选都全部通过且数目相同 |
| G2 | 九组回归（rest、application、plc、change、contracts、infrastructure、qml_debounce_alone、cli、qml、core） | 与卡 124 的受治理输出相比：失败集合为空、skip 数不变、无 ERROR，通过数恰好增加 plc +36、cli +4、core +6、rest +4，其余不变。唯一容忍规则见 §1 第 6 条 |
| G3 | 真实插件端到端 | 4 个真实插件/结构用例通过且无跳过；对模板生成的工程，真实的 `plc check` 退出码 0 且语言服务 check 与 test 两项通过，放回裸 CONST 块后退出码 1 且 check 项失败；阶段门禁项在好工程上通过、在坏工程上失败；插件二进制 SHA-256 前后相同 |
| G4 | 静态 | `ruff check auto_pm tests` 干净；`mypy --platform win32 auto_pm` 干净；`git diff --check` 无问题 |
| G5 | 范围与字节 | 变更集恰为 21 个路径、字节等于 §5.1；HEAD 为基线；安装前工作树干净；无残留文件 |
| G6 | 其他字节不变 | `auto_pm`、`templates`、`tests`、`scripts` 四棵树各自与基线的差异恰为冻结的文件（含变异还原之后） |
| G7 | 隔离与钩子 | 真实 .git/hooks 前后字节相同；无遗留 python 进程；真实 pre-commit 钩子对暂存的 21 个文件退出 0（临时索引） |
| G8 | 真实变异（8 个） | M1 适配器接受“退出码非零而无诊断”：test_ls07 失败；M2 检查器把缺插件当通过：test_cl04 失败；M3 阶段门禁不拦缺插件：test_gl04 失败；M4 CLI 永远退出 0：test_cx02 失败；M5 线型规则接受无块文件：test_st02 失败；M6 范围永远是工程根：test_sc01、test_sc03 失败；M7 交付门禁忽略缺文档：test_s06 失败；M8 模板丢掉块头：规范快照用例失败；每个变异后文件按字节还原 |
| G9 | 最终范围与字节 | 全部门禁之后字节与变更集不变 |

判卷由共用判卷脚本再核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-13 对整体方案说“同意按这个方案做”、“1同意，V07保留待办，卡127收口后允许推送”；用户 2026-10-13 夜间追加“启动前先查机器负载，我的错，你继续任务，我不玩游戏了，我给你预授权，按照规划继续任务，明早5点汇报任务进度”；2026-10-14 早晨电脑被 Windows 更新重启后，用户说“重试”，据此本卡 SHA 先在聊天报出即可启动（原话记入 `.auto-pm/reports/PREAUTH_M2_20261008.txt`）；**本卡 SHA 报给用户后，由用户在聊天中回复批准**才启动。条件：卡 SHA 先在聊天报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径、任一门禁失败即停下保留现场、不开第二轮；止损照旧 |
| **内容验收** | **用户阅读后确认；不委托。变更单收口脚本只在用户确认之后运行** |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

本卡不包含自身 SHA。卡、基线、范围、冻结文件或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

0. 启动前核对本机负载：无游戏/启动器（HeroesOfTheStorm、Battle.net、Steam 游戏等）在前台，近一分钟 CPU 占用低；有则等待，不启动。
1. 在聊天报告最终卡 SHA 与摘要，随即启动（用户夜间预授权，见 §7）。
2. 沿用 SW-2026-008 的 SCPT/OPT 变更单 CHG-SCPT-2026-413（仍在 implementing）、新建匹配 Decision（`DEC-<当天>-M3PLUG05`）、Work `WORK-SW008-M3-PLUGIN-005`、Run `RUN-SW008-M3-PLUGIN-005`（租约不超过 3600 秒，续租循环**用绝对路径启动并确认第一次续租成功**）。
3. 从基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m3-plugin5`，分支 `codex/m3-plugin-gate5`（V1.0～V1.3 的现场 `.auto-pm/worktrees/m3-plugin`、`m3-plugin2`、`m3-plugin3`、`m3-plugin4` 原样保留）。
4. 安装冻结字节并完整重跑门禁（`plugin5_gates_all.sh`）；先创建 Checkpoint，再正常 Hook 提交，绝不 no-verify；核对提交父、范围与 blob。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；按委托收口变更单；收口后按用户已给的允许做一次只读核对后的快进推送并读 CI。

## 9. 硬停止

基线、工具/卡/Decision 指纹、冻结文件字节、owner/scope、lease（含续租失败）或 hook 漂移；新增范围；任何门禁失败（§1 第 6 条那一条容忍规则之外）；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；插件缺失或版本不符；需要改这 21 个文件以外的任何内容、或为让检查变绿而放宽判据：均停止，保留现场，不靠重跑、改字节或放宽判据变绿，不开第二轮。止损：同一问题最多修 2 轮，连续 2 张卡失败整体停下；同一问题两次未解就通知用户（用户切 Opus 诊断）；不做任何真实模型调用。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结文件与工具；开发期与演练原始输出（非治理）；正式独立门禁与证据（含插件版本与二进制哈希、真实 `plc check` 修前修后的原始输出）；CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；委托收口记录。

## 11. 限制与后续

提交在本地分支 `codex/m3-plugin-gate5`（卡 126 的提交之上）。之后：推送卡 124～127 并读 CI（用户已允许）；AGENTS.md 措辞更正（核心档）与 TD-SW008-130、131 的小卡；把语言服务接入受治理证据采集（`evidence_collection_service`）的另卡；DJ-2026-011 的 OB1 块头登记为债务；WBS 登记卡 127。
