# V01B｜PLC 文档与代码一致性核对与自动补全实施卡

> 卡片编号：`CARD-SW008-M2-V01B`
> 对应 WBS：`V01B`（WBS V3.0.21 §4.8 任务表；由 `M2-GOV-WBS5` 提交 `57e14c19` 登记）
> 需求说明：`02_规划/043_PLC文档与代码一致性核对与自动补全需求说明_PM.md`（`CONFIRMED`，REQ-SW008-M2-DOCSYNC）
> 版本：`V1.0`（2026-10-03，一次定稿；执行期间不得修订，见 §9）
> 状态：`PLANNED / NOT_AUTHORIZED`（定稿，待授权；授权方式见 §7）
> 依赖：V01 已验收闭环（提交 `37a4faff`，CHG-SCPT-2026-374 completed）；WBS 修订 5 已验收闭环（CHG-DOCU-2026-026 completed）；需求说明 043 已由用户确认
> 隔离基线：`37a4faff4ae2bee24d7aca67f5624f5f11e2e697`
> 治理任务真源：WBS 提交 `57e14c194fdcc9c69fa601223240d68589472747`（V3.0.21，CHG-DOCU-2026-026 completed）；WBS SHA-256 `e5be410f35b2b883c036474173e66c09d5b3beb6bf19a3c4dae4582474202bf5`
> 路径根：`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`
> 推荐执行模型：`Claude Sonnet 4.6 (Thinking)` 或能力不低于它的模型；实际执行者 `Claude Sonnet 5.5`
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

> V1.0 定稿说明：本卡写于一次**可行性演练**之后（§1.6）。演练在项目副本上实现了全部产品改动与三个新测试文件，用真实 Git、真实 PLC 检查器、真实 V01 验收门跑通，并在钉死的基准提交上做了真实冒烟。参考实现、冒烟脚本、变异脚本、G2 脚本、安装脚本与演练输出归档于 `.auto-pm/reports/m2-v01b/`（`proto/<相对路径>` 共 15 个文件、`smoke_pinned_benchmark.py`、`mutation_check.py`、`run_g2.sh`、`g6_check.py`、`install_candidate.py`、`reference_manifest.json`、`rehearsal/`），仅供参考，不是产品代码；执行者可按参考实现填空，但必须满足 §5 的合同与 §6 的门禁。执行者不得现场修订本卡、扩大路径或放宽门禁；遇到本卡未覆盖的情况按 §9 停止并报告。
> 路径偏差说明：WBS 的 V01B 行写的是“拟”与“确切路径以勘测后的实施卡为准”。勘测后的确切路径为 §4 的 15 个：1 个新增领域模块、对 `PlcChecker` 与 `plc` 命令组各一处只增不删的接线、1 个新增命令模块、8 个 PLC 标准模板文件（模板属产品资产，在 `templates/` 下，不是 Obsidian 规范）、3 个新测试文件。WBS 对本卡实际路径的回写留到 M2 总审计。

## 1. 背景与已核实事实（2026-10-03，基线 `37a4faff`，均为命令或源码核验）

1. WBS V01B 原文：核对信号名、数据类型、方向、注释（不核对通信协议）；整份文档缺失警告并给出草稿；不一致拦住并精确指出对象、变量、差异与位置；代码到文档的补全只补缺行、不覆盖人写文字、补入行带【待确认】、一条命令确认；新检查项使 `plc check`、驾驶舱 PLC 检查统计与 V01 的 AI 验收门同时生效；钉死基准隔离副本冒烟。需求逐条见 043（用户 2026-10-03 确认）。
2. **现状缺口**（基线源码核验）：① `PlcChecker.check_project` 对接口文档只验证“存在”，不核对内容；② 没有任何“文档 ↔ 代码”的比对逻辑与自动补全；③ `plc` 命令组只有 `init`、`check`、`repair`、`standardize`；④ 现有的 `auto_pm/domain/vartable/parsers/` 下 `scl_parser`、`intdoc_parser` 服务于变量表子系统，不展开结构体字段、不识别 `.db` 数据块、不区分 FB/DB/OB/结构体各自的声明段，改它们会波及变量表的其他使用者，所以本卡新增一个自包含的领域模块，不改它们。
3. **新检查项自动生效的原因**（源码核验，不改调用代码）：V01 的 `plc-check` 门在候选工作树上调用 `PlcChecker(候选根).check_project(工程根)`，任何 `fail` 项即不通过；驾驶舱“PLC 检查失败项目数”统计来自同一个检查器的 `fail_count`；`plc check` 命令打印同一个结果。所以只要把核对作为 `check_project` 的一个新步骤并入，三处同时生效，V01 的三个产品文件与驾驶舱代码不改。V01 的检查器包指纹覆盖 `plc` 包目录下全部 `*.py`，新增的 `doc_consistency.py` 位于其中，所以它的任何改动都会使旧证据失效。
4. **对五个真实 PLC 工程的影响**（演练在最终字节上对主工作区活目录做只读测量；`PlcChecker` 通过/警告/失败数，基线 → 候选）：

   | 工程 | 基线 | 候选 | 候选的核对结果 |
   |---|---|---|---|
   | DJ-2026-000 | 10/1/1 | 10/3/1 | 2 个对象缺文档（警告）；原有的 1 个失败项（11 处 SCL 违规）不变 |
   | DJ-2026-005（基准） | 50/1/0 | 50/11/5 | 15 个对象、298 个变量：10 个缺文档（警告）；7 处代码有文档无、193 处文档有代码无、2 处注释不同（拦住，涉及 5 个 FB） |
   | DJ-2026-008 | 47/0/0 | 47/48/0 | 42 个缺文档、6 个文档无法解析（均为警告，无失败项） |
   | DJ-2026-009 | 45/0/0 | 45/10/3 | 10 个缺文档（警告）；8 处注释不同、4 处代码有文档无、43 处文档有代码无、1 处代码无注释（拦住，涉及 3 个对象） |
   | DJ-2026-011 | 12/0/0 | 12/0/0 | 无变化 |

   结论：本卡生效后，**DJ-2026-005 与 DJ-2026-009 内的任何 PLC 任务都会被 V01 的验收门拒绝**，直到它们的文档被治愈；DJ-2026-000 本来就被拒绝。WBS 只安排了 V01C 治愈 DJ-2026-005；DJ-2026-009 与 DJ-2026-008 没有治愈任务（见 §11）。这是设计（先治愈再沉淀、不设宽限期，用户 2026-10-03 确认），不是缺陷。
5. **基准项目与钉死**沿用 V01 §1.4：钉死提交 `3c32e8adc0ebf72691219d88f196cdf3c41266aa`，该提交上 `0100_PLC自动化/DJ-2026-005` 的 Git 目录树 SHA 为 `b457f2b95acd58db7cf65207236ef0999ebda9dd`（G9 先核对相等，不等即停）。本卡不改钉值（升基准是 V01C）。
6. **可行性演练结果**（归档于 `.auto-pm/reports/m2-v01b/rehearsal/`）：① 参考实现过 `ruff` 与 `mypy --strict`（7 个 Python 路径，零 `type: ignore`/`noqa` 新增）；② 三个新测试文件共 40 个测试全部通过（领域层 24、检查器接线层 8、命令层 8）；③ G1 在候选最终字节上 **287 passed、1 skipped、0 failed**（= 基线 247 + 新增 40）；`tests/application` 174 passed（与基线相同）；`tests/plc` 144 passed（= 基线 112 + 新增 32）；V01 自己的两个 PLC 验收门测试文件（`tests/core/test_plc_quality_gate.py`、`tests/core/test_plc_checkpoint_chain.py`，32 个测试，含真实子进程执行器的验收链路）在候选上 **32 passed**（用时约 10.6 分钟），说明检查器新增步骤没有破坏 V01 的门；④ 29 处变异（§6 G8）全部被对应测试抓住、源文件字节全部还原；⑤ 钉死基准冒烟（§6 G9）在 DJ-2026-005 的隔离副本上：初始核对报出真实不一致（15 个对象、298 个变量，202 个拦住项），V01 验收门因“文档一致性”失败且摘要首行指出对象与差异；`sync` 补入 296 行且全带标记、只写 `.md`；`--apply-suggestions` 按建议改动 195 处后只剩 19 处“代码里没有写注释”；`confirm` 确认 279 行、保留 19 行；再次运行零改动；手工把一个类型改错被立即抓出；在隔离副本里补上这 19 条注释并走完补全与确认后，核对结果为零差异零标记，V01 验收门通过（用时：核对约 0.4 秒，门约 25 秒，全程约 50 秒）。⑥ 演练发现并已纳入合同的真实问题：同一模块有两个 FB、各有一份接口文档（DJ-2026-008 的真实布局）时，必须按文件名把文档归给对应的 FB，否则 `sync` 会把一个 FB 的行写进兄弟的文档（§5.1-5，d18～d20）；`--apply-suggestions` 改写类型不同的行时，若代码没有注释，不得把人写的说明抹掉（d17）；方向放错的行移走后不得重复补入（d13）。
7. **基线数字**：① G1 集合在 `37a4faff` 干净导出（`.venv` 解释器，改动前）上实测 **247 passed、1 skipped、0 failed**；② G2 各组沿用 V01 终态（同一提交 `37a4faff`、真实隔离工作树，原始输出 `.auto-pm/reports/m2-v01/gates/g2_candidate/`）：contracts 191 passed 1 skipped；infrastructure 32 passed；cli 252 passed 1 skipped；change 230 passed；core 948 passed、3 failed（即 E-G1-1）、1 skipped（用时 5200 秒）；qml 283 passed（排除一个测试）+ 该测试单独 1 passed；演练在导出目录上重测的 contracts、infrastructure、change、qml 与上述完全相同；③ 本卡新增的两个 G2 组由演练在 `37a4faff` 干净导出上实测：`tests/application` 174 passed；`tests/plc` 112 passed。输出归档 `.auto-pm/reports/m2-v01b/rehearsal/`。④ 说明：演练在**非 Git 工作树的导出目录**里运行时，`tests/cli/test_root_entry_runtime_identity.py` 的 2 个测试失败（该测试要求真实工作树身份），基线与候选相同，与本卡无关，正式执行以真实隔离工作树为准；演练还顺带跑了 G2 之外的其余测试目录：有 16 个测试在导出目录里失败——`tests/vartable` 的 14 个真实样本解析测试和 `tests/e2e` 的 1 个词典检索测试需要真实工作区里的样本文件，`tests/test_fixture_health.py` 的 1 个是基线既有的真实问题（`tests/qml/test_file_watcher_bridge.py` 含一处条件断言写法）；基线与候选的失败集合完全相同，候选没有新增违规（本卡三个新测试文件均不含该写法）。这些目录不设为本卡 G2 门禁，本卡也不触碰它们（G6 要求 `domain/vartable` 字节不变）；该基线问题登记为技术债候选（见 §11）。
8. 已登记的基线例外沿用：E-G1-1（`tests/core/test_implementation_card_service.py` 的 3 个既存失败）、E-G1-2、E-G1-3、E-G3-1。
9. **明确不在本卡**：提交拦截钩子、阶段门“监控→收尾”、交付拦截（V01D）；DJ-2026-005 的文档治愈与重新钉基准（V01C）；DJ-2026-008、DJ-2026-009 的文档治愈；通信协议核对；“文档 → SCL 骨架”；非 Siemens 风格的 ST 写法（报“无法解析”警告）；`io_points.csv`、`program_blocks.yml`、HMI 点表的核对；Obsidian 规范库（含 INT-815）的任何修订；`auto_pm/domain/vartable/parsers/`；`plc check` 命令的退出码、输出编码与 `launcher:` 行；V01 已验收的三个产品文件；任何 schema、事件类型、迁移；`.trae`、Hook、release、文档（含 D01 的操作手册）。

## 2. 单一目标（用户故事与完成定义）

作为维护 PLC 项目的人，我改了代码常常忘记改文档，希望工具替我核对、替我补，我只审：

1. `plc docs check` 对每个接口变量核对**信号名、数据类型、方向、注释**：整份文档缺失只警告；代码有文档无、文档有代码无、类型/方向/注释不同、文档重复、代码无注释一律“拦住”，并指出对象、变量、差异内容与代码/文档两处位置；
2. 同一核对作为 `PlcChecker.check_project` 的新步骤并入：`plc check`、驾驶舱 PLC 检查统计与 V01 的 AI 验收门同时生效，不改这三处的调用代码；
3. `plc docs sync` 按代码补全文档：只补缺的行与缺的文档，补入的行在说明列前带 `【待确认】`，从不写 SCL，不覆盖人写的文字（只有显式 `--apply-suggestions` 才按代码改写，且代码里已不存在的旧条目移到文末归档小节而不是删除）；
4. `plc docs confirm` 一条命令去掉标记，只对已与代码对上的行生效；
5. 新建的标准 PLC 项目（模板渲染结果）开箱即零差异、零标记；
6. V01 的验收门、`checkpoint-evidence` 的 v1/v2/v3、Python 路径与 `plc check` 的既有行为一字不变。

## 3. 实施前预检（只读，先于任何写入）

1. 核验本卡字节 SHA-256 已被外部 Approval Receipt 绑定；核验 `隔离基线` 是 V01 提交且可解析（分支 `codex/m2-v01-plc-quality-gate` 仍在 `37a4faff`）、WBS 提交与 SHA-256 一致。
2. 运行 `main.py implementation-card precheck --card-file` 对本卡，退出码必须为 0。
3. 核验 §4 中 10 个“存在”路径在基线上存在、5 个“计划新增”路径在基线上不存在。
4. 在隔离候选中，对 §6 G1 集合复现基线结果 **247 passed、1 skipped**（修改前），`ruff` 与 `mypy --strict` 对 §4 已存在的 2 个 Python 路径通过；不一致则停止。
5. 核验隔离候选 HEAD 等于基线，configured/effective runtime 与加载路径一致且无 fallback；核验基准目录树 SHA（§1.5）。
6. 阅读 `.auto-pm/reports/m2-v01b/proto/` 下的参考实现与 `mutation_check.py`、`smoke_pinned_benchmark.py`，确认其做法与本卡 §5 一致；核对 `reference_manifest.json` 中各文件的 SHA-256。
7. **续租（硬性）**：开始任何超过 30 分钟的门禁（G2 的 core 约 60～70 分钟）之前先续租；后台任务约 30 分钟会被系统杀掉外壳（已启动的测试进程不受影响），所以按 V01 的做法，每个检查周期（不超过 25 分钟）手动续一次租，单次续租不超过 3600 秒，finalize 前租约须剩余 300 秒以上。租约过期时停止并报告，不得自行走恢复链。
8. **判卷与门禁工具先验证再起长批次**：判卷脚本与变异脚本必须先在真实输出上跑通一次，再启动 G1/G2 长批次；工具字节一旦被证据绑定，任何修正都会使整个窗口重开。
9. **长批次不得重叠**：G1、G2 的各目录、G8、G9 按顺序单独运行，不与 `tests/qml` 组重叠；演练表明重叠会让用时翻倍。

## 4. 精确 Owned Paths（15）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `auto_pm/domain/plc/doc_consistency.py` | 计划新增 | 领域模块：SCL/DB 解析、文档表解析、比对、补全、确认 |
| 2 | `auto_pm/domain/plc/checker.py` | 存在 | `check_project` 新增步骤 7 与一个私有方法（只追加，0 行删除） |
| 3 | `auto_pm/ui/cli/plc/docs.py` | 计划新增 | `plc docs check/sync/confirm` 命令 |
| 4 | `auto_pm/ui/cli/plc/__init__.py` | 存在 | 导入并注册 `docs_group`（只追加，0 行删除） |
| 5 | `templates/plc-standard-project/template/02_PLC程序/PLC_ST/00_全局数据/GlobalVars.db.jinja` | 存在 | 全局数据块各变量补行尾注释 |
| 6 | `templates/plc-standard-project/template/02_PLC程序/PLC_ST/01_外部设备交互/FB_3001_ExternalInteraction.scl.jinja` | 存在 | `io_stExternal` 补行尾注释 |
| 7 | `templates/plc-standard-project/template/02_PLC程序/PLC_ST/01_外部设备交互/ST_ExternalDevice.scl.jinja` | 存在 | 上下游字段补行尾注释 |
| 8 | `templates/plc-standard-project/template/02_PLC程序/PLC_ST/01_外部设备交互/PRD/接口文档_IFC-FB3001-ExternalInteraction.md` | 存在 | 接口表与代码对齐 |
| 9 | `templates/plc-standard-project/template/02_PLC程序/PLC_ST/02_工位1_动作机构/ST_Station1.scl.jinja` | 存在 | 子结构字段补行尾注释 |
| 10 | `templates/plc-standard-project/template/02_PLC程序/PLC_ST/02_工位1_动作机构/PRD/接口文档_IFC-FB1001-Station1.md.jinja` | 存在 | 只列 FB 自己的参数，结构体字段指向变量定义文档 |
| 11 | `templates/plc-standard-project/template/02_PLC程序/PLC_ST/05_公共报警/PRD/接口文档_IFC-FB2001-CommonAlarm.md` | 存在 | 只列 FB 自己的参数，去掉过期的逐信号表 |
| 12 | `templates/plc-standard-project/template/02_PLC程序/程序文档/PLC变量定义文档_VAR.md.jinja` | 存在 | 按对象分节的变量表（结构体、数据块、组织块），字段只在此维护 |
| 13 | `tests/plc/test_doc_consistency.py` | 计划新增 | 领域层测试 |
| 14 | `tests/plc/test_doc_consistency_checker.py` | 计划新增 | 检查器接线层测试（含模板渲染零差异） |
| 15 | `tests/cli/test_plc_docs.py` | 计划新增 | 命令层测试 |

出现第 16 条产品脏路径即停止，不得现场扩大 Decision。治理证据对象在控制根落账，不计入上述路径。

## 5. 合同（全部定稿，执行者不得改写含义）

### 5.1 `auto_pm/domain/plc/doc_consistency.py`（新增；纯领域库，不依赖 CLI、应用层或 Qt；不写 SCL）

1. **常量**：`MARKER = "【待确认】"`；`ARCHIVE_HEADING = "## 附：代码中已不存在的旧条目（待确认后删除）"`；`VAR_DOC_NAME = "PLC变量定义文档_VAR.md"`；`IFC_GLOB_PREFIX = "接口文档_IFC-"`。
2. **代码解析**（`parse_scl_text(text, path)`、`parse_scl_file(path)`）：识别 `FUNCTION_BLOCK`（FB）、`FUNCTION`（FC）、`ORGANIZATION_BLOCK`（OB）、`DATA_BLOCK`（DB）、`TYPE … STRUCT`（UDT）；FB/FC 取 `VAR_INPUT`、`VAR_OUTPUT`、`VAR_IN_OUT` 三段（其余段忽略），OB 取 `VAR_TEMP` 与 `VAR`，DB 取 `VAR`，UDT 取 `STRUCT` 字段；只理解单行声明 `名称[, 名称] : 类型[ := 初值]; [// 注释]`，`(* … *)` 块注释先剥离、行尾 `; (* 注释 *)` 视为注释；内联 `名称 : STRUCT … END_STRUCT` 内的字段名带点前缀（如 `stLine.i_bRun`）；其他无法解析的声明行记入对象的 `unparsed`，不当作变量。遍历项目时跳过以 `.` 开头的目录与 `node_modules`、`__pycache__`、`archive`、`_archive`、`Test`、`99_基线`、`工程资产`；`.db` 文件超过 2,000,000 字节、含 NUL 字节或不含 `DATA_BLOCK` 的跳过；既无变量又无 `unparsed` 的对象不进入报告。读文件统一 `encoding="utf-8", errors="replace"`。
3. **文档解析**（`parse_doc_lines(lines)`）：变量表 = Markdown 表中含“名称类列”（`名称`/`参数名`/`变量名`/`字段名`/`名称/变量`/`变量`/`信号名`/`参数`）与“类型列”（`类型`/`数据类型`）的表；说明列取 `说明`/`描述`/`功能描述`/`含义`/`注释`；方向列取 `方向`；方向取方向列（`VAR_INPUT`/`INPUT`/`IN`/`输入` 等别名，`VAR_OUTPUT`/`OUTPUT`/`OUT`/`输出`，`VAR_IN_OUT`/`IN_OUT`/`INOUT`/`输入输出`/`双向`），没有方向列时取最近的上级标题里出现的 `VAR_INPUT`/`VAR_OUTPUT`/`VAR_IN_OUT`；标题含“已不存在”的小节为归档，不参与核对；变量名取单元格去掉反引号与加粗后的首个词；没有名称类列加类型列的表（报警码表、概览表等）不当作变量表；说明列以 `【待确认】` 开头的行为“带标记行”。
4. **规范化**：类型——NFKC、去引号、大写、去全部空白，且 `T[a..b]`（`T` 不是 `STRING`/`WSTRING`）等同于 `ARRAY[a..b] OF T`；说明——NFKC、去掉 `【待确认】`、折叠空白后比较。类型与说明的比较一律先规范化。
5. **配对**：① FB/FC 对所在目录 `PRD/接口文档_IFC-*.md`；同一目录有多个 FB/FC 时，按文件名与 FB 名的**亲和度**（只比较字母数字、不分大小写；得分从高到低：全名相等、去掉 `FB<数字>`/`FC<数字>` 前缀后相等、全名互为前缀、去掉前缀后互为前缀；打分见参考实现的 `_affinity`）把每份文档归给得分**唯一最高**的 FB（并列或得分为零则不归属）；FB 只使用归给它的文档；没有归属文档时，仅当某份文档里存在标题含该 FB 名的小节（共享文档）才使用，且只取这些小节；否则视为缺文档；单 FB 的目录取亲和度最高（并列取文件名排序第一）的文档，文档里的全部变量表都属于该 FB；② DB/OB/UDT 对应项目内第一份 `PLC变量定义文档_VAR.md`（遍历路径按名称排序；没有则取 `02_PLC程序/程序文档/` 的默认位置），只取标题首词等于对象名的小节下的表。
6. **比对与结果**（`analyze_project(项目路径) -> ProjectAnalysis`，只读）：每条结果含对象名、种类、严重度、变量名、消息、代码位置与文档位置（相对项目根的 `路径:行`）：

   | 种类 | 严重度 | 条件 |
   |---|---|---|
   | `missing_doc` | warn | 没有接口文档 / 没有变量定义文档 / 变量定义文档里没有该对象的表 |
   | `unparsable_doc` | warn | 文档存在但没有可识别的变量表 |
   | `unparsed` | warn | 代码里无法解析的声明 |
   | `code_not_in_doc` | fail | 代码里有、文档里没写 |
   | `doc_not_in_code` | fail | 文档里有、代码里没有（已删除或改名） |
   | `doc_duplicate` | fail | 同一变量在文档里出现多次 |
   | `type` | fail | 规范化后类型不同（消息含代码值与文档值） |
   | `direction` | fail | 仅 FB/FC 核对；方向不同，或文档里无法确定方向 |
   | `comment` | fail | 代码有注释且规范化后与文档说明不同（消息含两边文字） |
   | `no_comment` | fail | 代码里该变量没有注释（两边都必须有注释） |

   整份文档缺失只给 `warn`，**不拦**；其余差异均 `fail`。`Finding.render()` 的文案含 `对象.变量：差异（代码 路径:行；文档 路径:行）`。
7. **并入检查器用**：`consistency_items(项目路径) -> list[(项目名, 状态, 消息)]`：每个有变量的对象一项 `文档一致性 [功能块|函数|组织块|数据块|结构体 名称]`（全对上为 `pass`，仅有 `warn` 种类为 `warn`，含 `fail` 种类为 `fail`，消息含各种类计数、前两条精确差异与“运行 plc docs check 查看全部，plc docs sync 自动补全”）；存在带标记行时另加一项 `文档待确认标记`（`warn`，提示运行 `plc docs confirm`）。
8. **补全**（`sync_project(项目路径, *, write=True, apply_suggestions=False) -> SyncResult`）：① 整份文档缺失则创建——FB/FC 为目录下 `PRD/接口文档_IFC-<对象名>.md`，DB/OB/UDT 为变量定义文档——带标准骨架与说明引言；② 缺的行补进该对象正确的表（同方向/同对象已有表则追加到表末，否则新增小节或表），说明列为 `【待确认】` 加代码注释；③ 不修改已有行、不写 SCL，写出统一 UTF-8 与 LF，内容无变化的文件不写；④ `apply_suggestions=True` 额外：类型或注释不同的行按代码改写（说明列加标记；代码没有注释时**保留原文并加标记**，不得抹掉人写的说明），代码里已不存在或方向放错的行移到文末归档小节（原文保留、加标记、记录原对象，不删除），方向放错的变量若在正确方向没有行则在正确方向的表里补入一行；⑤ 默认模式下，需要人工处理的差异汇总为建议清单返回；⑥ 幂等：补全后再次运行，补入行数与改动数均为 0；⑦ 一个 FB/FC 的行只写入归给它的文档（§5.1-5），绝不写入兄弟 FB 的文档；共享文档里只写入该 FB 自己的小节。
9. **确认**（`confirm_project(项目路径, *, write=True) -> ConfirmResult`）：对带标记且该变量当前没有 `fail` 级差异的行，去掉每行的第一个 `【待确认】`；仍有差异的行保留标记并记入 `skipped`；写出同样为 UTF-8 与 LF。

### 5.2 `auto_pm/domain/plc/checker.py`（只追加，0 行删除或改写）

1. 增加 `from auto_pm.plc.doc_consistency import consistency_items`；在 `check_project` 末尾、`log.info` 之前新增步骤 7：调用新的私有方法 `_check_doc_code_consistency(project_path, result)`；
2. 该方法：项目类型属于 `SKIP_PLC_JSON_TYPES`（SysLib FB 项目）时直接返回；调用 `consistency_items`，把每一项原样 `result.add(项, 状态, 消息)`；调用抛出任何异常时只增加一项 `文档一致性` 的 `warn`（文案 `一致性核对异常，已跳过: <异常>`），不得让 `check_project` 抛出；绝不写任何文件；
3. 不改既有的任何检查、`CheckResult`、`plc check` 命令的退出码与输出格式。

### 5.3 `auto_pm/ui/cli/plc/docs.py` 与 `auto_pm/ui/cli/plc/__init__.py`

1. `__init__.py` 只追加：`from .docs import docs_group`、`plc_group.add_command(docs_group)` 与模块文档字符串里的一行说明；
2. `docs_group`（命令组名 `docs`）三个命令，均接受 `项目ID` 或 `--project-path 目录`（后者用于隔离副本）；两者都没有给时报用法错误（退出码 2）；项目ID不存在退出码 1：
   - `plc docs check [ID] [--project-path D] [--json] [--strict-markers]`：打印每个有差异的对象与逐条差异，末行 `拦住项 N、警告 N、待确认 N`；有 `fail` 级差异，或指定 `--strict-markers` 且仍有带标记行时退出码 1，否则 0；`--json` 输出 `schema_version: "plc-docs-check.v1"`、`project_path`、`objects`（种类、名称、变量数、文档状态、状态）、`findings`、`marked_rows`；
   - `plc docs sync [ID] [--project-path D] [--dry-run] [--apply-suggestions]`：调用 `sync_project`；`--dry-run` 不写任何文件且输出前缀注明“预览”；打印新建与修改的文档数、补入行数、按建议改动数、仍需人工处理的建议；退出码 0；
   - `plc docs confirm [ID] [--project-path D]`：调用 `confirm_project`；打印已确认行数与每条未确认原因；退出码 0。
3. 不改 `plc check` 等既有命令。

### 5.4 8 个 PLC 标准模板文件（§4 的 5～12）

1. **验收口径**：用 `TemplateService` 渲染 `plc-standard-project` 得到的新项目，`analyze_project` 必须零结果、零带标记行（G3 c08），且 `PlcChecker` 检查零失败（既有 `test_template_integrity`）；
2. 4 个 SCL/DB 模板（§4 的 5、6、7、9）**只增改行尾注释**：去掉全部注释并折叠空白后与基线逐词相同（G6 机器检查）；
3. 接口文档模板（§4 的 8、10、11）只列该 FB **自己声明**的参数；参数是结构体时只写一行 `io_stX : ST_X`，结构体字段不在此展开，统一在变量定义文档该结构体的小节维护；删除与代码不符的逐信号旧表；模板里的 Jinja 变量与叙述性小节（概述、报警码表、关联文档）保留；
4. 变量定义文档模板（§4 的 12）的变量表按对象分节（结构体、数据块、组织块，标题为 `### 对象名（结构体|数据块|组织块）`），说明列与代码行尾注释逐字一致，命名规则等叙述性小节保留。

### 5.5 必测场景（G3）

测试文件中的每个测试函数都须对应下表一个场景；场景编号写在测试名里（`test_d01_…`）。测试不得通过 Mock 业务结果、硬编码预期字段或跳过来变绿；只允许对 `consistency_items` 的**外部故障注入**打桩（c06）。参数化仅限 d06。

**领域层 `tests/plc/test_doc_consistency.py`**（合成 PLC 工程写进临时目录，不依赖任何活工程）：

| 场景 | 要证明的行为 |
|---|---|
| d01 | 解析器读出 FB 接口、结构体字段、内联结构体点前缀字段、行尾注释与数组类型 |
| d02 | 块注释、多变量声明、OB 局部量、无法解析的声明行 |
| d03 | 文档解析：方向取自标题与方向列、列别名、标记行、归档小节、跳过无关表 |
| d04 | 类型与说明规范化：忽略写法差异，不忽略内容差异 |
| d05 | 完全一致的工程没有任何结果 |
| d06 | 类型、注释、代码有文档无、文档有代码无、文档重复五种差异（参数化 5 个）各自 `fail`，消息含对象.变量与位置 |
| d07 | 方向取自标题；方向不同与文档无法确定方向都 `fail` |
| d08 | 代码变量没有注释时 `fail`，即使文档有说明 |
| d09 | 缺文档只 `warn` 不 `fail`；无变量表的文档报 `unparsable_doc` |
| d10 | 同一模块两个 FB 共用一份带分节标题的文档时，只取各自的小节；没有自己小节的 FB 视为缺文档 |
| d11 | `sync` 创建缺失文档、补入行带标记、从不改动代码字节 |
| d12 | `sync` 只补缺行，人写文字逐字节保留，二次运行零改动 |
| d13 | `--apply-suggestions` 改写差异行、旧条目移入归档小节而不删除；方向放错的行不产生重复；二次运行零改动 |
| d14 | `confirm` 只对已与代码对上的行去标记，仍有差异的保留 |
| d15 | `consistency_items` 逐对象汇总并报告待确认行 |
| d16 | 二进制 `.db`、`archive` 目录被忽略 |
| d17 | `--apply-suggestions` 在代码没有注释可抄时保留人写的说明并加标记 |
| d18 | 同一目录两个 FB 各用以自己命名的文档比对 |
| d19 | `sync` 不会把一个 FB 的行写进兄弟 FB 的文档，而是为它新建文档 |
| d20 | 共享文档里 `sync` 只在该 FB 自己的小节补行（故意把该 FB 小节放在别的小节之前） |

**检查器接线层 `tests/plc/test_doc_consistency_checker.py`**：

| 场景 | 要证明的行为 |
|---|---|
| c01 | 一致的工程：每个有文档的对象恰一条 `pass` 项 |
| c02 | 差异使检查失败，消息含变量与文档位置，`fail_count` 增加 |
| c03 | 缺文档只 `warn`，消息提示 `plc docs sync` |
| c04 | 残留的待确认标记产生 `warn` 项，确认后消失 |
| c05 | SysLib FB 项目被跳过 |
| c06 | 一致性代码抛异常变为一条 `warn`，`check_project` 不崩 |
| c07 | 检查器从不写文档或代码 |
| c08 | 新渲染的标准 PLC 项目零结果、零标记，且 `PlcChecker` 无非 `pass` 的“文档一致性”项 |

**命令层 `tests/cli/test_plc_docs.py`**（`CliRunner`，真实文件）：

| 场景 | 要证明的行为 |
|---|---|
| k01 | `check` 对一致工程退出码 0 |
| k02 | 不一致退出码 1，输出含变量、代码位置与文档位置及 `plc docs sync` 提示 |
| k03 | `--json` 机器可读且结论一致 |
| k04 | `--strict-markers` 仅在仍有标记时失败，`sync`→`check`→`confirm` 全流程 |
| k05 | `--dry-run` 不写文件；`sync` 写文档但不改代码 |
| k06 | `--apply-suggestions` 前后输出与文档变化 |
| k07 | `confirm` 对仍不一致的行保留标记并报告 |
| k08 | `--project-path`；缺参数退出码 2；未知项目退出码 1 |

### 5.6 明确不做

不改 V01 的三个产品文件、`domain/plc` 下除 `checker.py` 外的任何文件、`auto_pm/domain/vartable/`、驾驶舱/Bridge/QML、Store、合同模型；不新增 schema、事件类型或迁移；不写提交钩子；不改任何文档与 Obsidian 规范；不做 PLC 上机编译或下发；不合并、不推送、不部署、不切换 release。

## 6. 门禁矩阵

所有命令均在隔离候选的项目根执行，使用工作区 `.venv` 解释器与 `-B`，先 `-o addopts= --no-cov -p no:cacheprovider`。

**G1 定向测试**（修改前先对基线跑同一集合并记录数字；修改后全部通过，0 失败，不新增跳过）：

```powershell
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider `
  tests/plc tests/cli/test_plc.py tests/cli/test_plc_docs.py tests/core/test_dashboard_service.py `
  tests/application/test_workbench_facade.py tests/test_smoke.py tests/test_bug5_scan_depth.py `
  tests/spec/test_cli.py tests/core/test_python_service.py -q
```

基线数字：**247 passed、1 skipped**（§1.7，基线时集合不含 `tests/cli/test_plc_docs.py`）；候选须不少于 247 + 本卡新增测试数（演练为 40，即 287），且 0 failed、skipped 仍为 1。

**G2 分目录回归**（固定方法，同 U05～V01；基线数字见 §1.7；候选相对基线：失败集合相同——core 仅 E-G1-1 的既存失败、通过数不少于基线加本卡 core 新增测试数（0）、无新增失败、无新增跳过；其余目录通过数不少于基线加该目录新增测试数——`tests/cli` 加 8、`tests/plc` 加 32）。共九组：`tests/qml`（排除去抖测试）、去抖测试单独一组、`tests/contracts`、`tests/infrastructure`、`tests/cli`、`tests/change`、`tests/core`、`tests/application`、`tests/plc`，命令与顺序见 `.auto-pm/reports/m2-v01b/run_g2.sh` 的前九组（脚本最后的“其余目录”组仅作演练参考，不设门，见 §1.7-④）。各组都必须在**最终字节**上全量重跑；core 约 60～70 分钟，**必须先按 §3-7 续租**。`tests/qml` 组出现 Qt access violation 不得按 E-G1-2 豁免：先在全新进程单独重跑出问题的文件一次并保存两次原始输出；仍崩溃则按 §9 停止。

**G3 必测场景**：§5.5 的 d01～d20、c01～c08、k01～k08 各至少一个独立测试，并在判卷报告中列出“场景 → 测试名”对照；测试文件中的每个测试函数都须对应一个场景（d06 允许参数化）。

**G4 静态质量**：

```powershell
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m ruff check --no-cache auto_pm/domain/plc/doc_consistency.py auto_pm/domain/plc/checker.py auto_pm/ui/cli/plc/docs.py auto_pm/ui/cli/plc/__init__.py tests/plc/test_doc_consistency.py tests/plc/test_doc_consistency_checker.py tests/cli/test_plc_docs.py
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m mypy --strict --no-incremental auto_pm/domain/plc/doc_consistency.py auto_pm/domain/plc/checker.py auto_pm/ui/cli/plc/docs.py auto_pm/ui/cli/plc/__init__.py tests/plc/test_doc_consistency.py tests/plc/test_doc_consistency_checker.py tests/cli/test_plc_docs.py
git diff --check
```

不得使用 `--follow-imports=skip`，不得新增文件级抑制或为通过门禁新增 `type: ignore`/`noqa`（5 个新增文件全文零出现；既有两个文件的 diff 新增行零出现）；在最终字节上运行；5 个新增（未跟踪）文件另行扫描行尾空白、制表符与回车字符（仓库约定为 LF；用 Python 按字节检查，不要用 Shell 的 `grep` 匹配回车）。不要求 `ruff format`（基线文件本身不满足）。

**G5 范围与洁净**：`git diff --name-only` 加未跟踪文件的路径集合精确等于 §4 的 15 个路径；无 `.coverage`、缓存、`tmp_*` 残留（DEV-TMP-001）；任何 `.qml` 文件无改动。

**G6 既有内容不变**（参考脚本 `.auto-pm/reports/m2-v01b/g6_check.py CANDIDATE_ROOT BASELINE_ROOT`，演练在最终字节上退出码 0；它另外核验候选与基线之间除 §4 的 15 个路径外没有任何文件差异）：① `checker.py` 与 `ui/cli/plc/__init__.py` 的 diff **被删除或改写的既有行数为 0**（只追加；演练为 +16/−0 与 +6/−0）；② 4 个 SCL/DB 模板（§4 的 5、6、7、9）去掉 `//` 与 `(* *)` 注释并折叠空白后与基线逐词相同；③ V01 的三个产品文件（`evidence_collection_service.py`、`continuity_execution_service.py`、`pm_facade_service.py`）与 V01 的两个测试文件、G1 与 G2 中全部既有测试文件字节不变（均不在 owned paths 内）；④ `auto_pm/domain/vartable/` 下字节不变；⑤ 既有测试不改一个断言。

**G7 不触碰生产**：测试只使用临时目录与临时库，不读写真实控制面的 `.auto-pm/continuity.db` 与真实 `00_Infrastructure`；不改 Hook、release、`.auto-pm` 下任何运行态对象；G9 只在隔离克隆里操作，不改真实仓库的任何分支与工作树，也不改任何真实 PLC 工程目录。

**G8 变异检验**（执行者在代码完成后、最终门禁之前运行，结果绑定进判卷）：运行 `.auto-pm/reports/m2-v01b/mutation_check.py`（29 处变异，覆盖：类型/注释/方向差异不报、各拦住种类降级、缺文档变拦住、归档行被当作活行、结构体点前缀丢失、规范化丢失、`sync` 重复补行、补入行不带标记、`apply` 抹掉人写文字、方向放错行重复、`confirm` 去掉仍不一致行的标记、检查器不运行/降级失败/不跳过 SysLib/不防异常、命令退出码恒 0、`--strict-markers` 失效、`--dry-run` 写文件、文档归属错配与共享文档补错小节、模板丢注释与模板文档写错类型）；每处变异后对应测试必须变红，源文件随后原样还原并校验字节；任一变异存活或还原后字节不一致即停止；执行者可再增补。输出归档于 `.auto-pm/reports/m2-v01b/mutation_check_output.json`。

**G9 钉死基准冒烟**（真实证据，WBS 对 V01B 的要求）：在候选的最终字节上，从候选项目根运行：

```powershell
$env:PYTHONPATH = (Get-Location).Path
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B C:\Users\fubai\Documents\My_Workspace\.auto-pm\reports\m2-v01b\smoke_pinned_benchmark.py --repo C:\Users\fubai\Documents\My_Workspace --commit 3c32e8adc0ebf72691219d88f196cdf3c41266aa --project-path "0100_PLC自动化/DJ-2026-005" --tree-sha b457f2b95acd58db7cf65207236ef0999ebda9dd --out C:\Users\fubai\Documents\My_Workspace\.auto-pm\reports\m2-v01b\gates\g9_smoke.json
```

脚本把真实仓库硬链接克隆到临时目录，在克隆里为钉死提交建分离的临时工作树，**不创建任何治理对象**，结束后清除。通过标准（退出码 0，且 JSON 的 `checks` 全部为真）：目录树 SHA 与钉死值相等；初始核对存在拦住项且 `plc check` 暴露“文档一致性”项；V01 验收门在未治愈的基准上失败且摘要出现“文档一致性”；`sync --dry-run` 不改任何文件；`sync` 只写 `.md`、不改代码字节且补入行全带标记；`--apply-suggestions` 后只剩“代码没写注释”与“无法解析”两类结果且不改代码字节；`confirm` 后仍带标记的行数等于被拒绝确认的行数；二次运行补入、改动、确认均为 0；手工改错一个类型被恰好抓出一处；在隔离副本里补齐缺失的代码注释并走完补全与确认后，核对为零差异零警告零标记，且 V01 验收门通过。目录树 SHA 不等视为基准漂移，立即停止，不得改写钉值（升基准是 V01C）。

## 7. 实施授权签字门

### 7.1 当前签字状态

| 字段 | 当前值 |
|---|---|
| 卡片 | `CARD-SW008-M2-V01B V1.0` |
| 实施批准 | `PENDING`（须用户在对话中明确批准；批准后以委托方式由 Claude 执行，回执另行生成） |
| 最终验收 | `PENDING`（验收由用户做出；CHG 收口须经用户在对话弹窗确认后才可由 Claude 代跑） |
| 审批人 | `fubai / baiyang`（同一用户、等权署名） |
| 隔离基线 | `37a4faff4ae2bee24d7aca67f5624f5f11e2e697` |
| Owned Paths | §4 的 15 个路径 |
| 执行模型 | `Claude Sonnet 5.5` |
| 明确禁止 | 第 16 条路径、改 V01 的三个产品文件与 `domain/vartable`、改 `domain/plc` 下除 `checker.py` 外的文件、对 `checker.py` 与 `ui/cli/plc/__init__.py` 做删除或改写、模板 SCL 代码改动（只许注释）、改 Obsidian 规范与任何文档、写提交钩子或阶段门、新增 schema 或迁移、直接改真实库、改真实 PLC 工程目录、历史改写、Hook/release 修改、改动基准钉值、合并、推送、部署 |

### 7.2 授权成立与失效

1. 卡片字节、隔离基线、WBS 真源、owned paths、执行模型或禁止事项任一漂移，审批立即失效。
2. 外部 Approval Receipt 绑定本卡完整字节 SHA-256、基线、WBS 提交、15 个路径、允许/禁止动作、执行模型、审批人与时间；卡片自身不含自身 SHA-256。
3. 实施批准与最终验收分离；执行 Agent 不得自签验收。

## 8. 治理执行顺序

1. 只读预检并输出事实表（§3），含 G1 修改前的基线数字。
2. 用户批准本卡后，创建并批准 SW-2026-008 的独立 CHG（领域 SCPT）与精确 Decision（§4 十五路径，计划新增路径不检查基线存在；Decision 建议 `DEC-20261003-V01BDOCS`，日期以起卡当天为准，后缀须恰 8 位）。
3. 创建 Work（`--card-file` 指向本卡，Work 与 Decision 的项目一致，均为 SW-2026-008；建议 `WORK-SW008-M2-V01B-001`）、在全新隔离候选（自 V01 提交 `37a4faff` 起，分支 `codex/m2-v01b-plc-doc-consistency`，工作树 `.auto-pm/worktrees/m2-v01b`）启动 Run（`--lease-seconds` 不超过 3600；建议 `RUN-SW008-M2-V01B-001`），并按 §3-7 管理续租。
4. 在候选中按 §5 实现、运行 G8 变异检验并完成 §6 门禁；判卷结果写入 `.auto-pm/reports/m2-v01b/` 下机器可读判卷文件。
5. 创建当前字节 Checkpoint（`git_head` 为基线，逐文件记录 SHA-256 与判卷文件 SHA-256），**先于提交**；随后走正常 Hook 提交（不得 `--no-verify`）；提交后核验提交内 blob 与 Checkpoint 逐一相同，否则停止。
6. Run/Work 终态、台账 `main.py ledger reconcile SW-2026-008` 为 0/0/0；CHG 收口须经用户弹窗确认后由 Claude 代跑，或由用户自己运行。
7. 向用户报告后停止；SHA 与 ID 写入交接文档。WBS 对本任务结果的回写为独立的后续修订，不在本卡范围。

## 9. 有界纠正与硬停止条件

本卡单提交，一个主 Run；仅当失败稳定复现、完全落在 §4 路径内、无需合同或路径扩展时，允许一个纠正 Run（必须新建 Run 并重建 Checkpoint）。**执行期间不得修订本卡**；需要修订本卡即属于硬停止。

以下任一情况立即保留现场、停止并报告：

- 基线 HEAD、runtime 身份、Decision 字节、owned paths 或基准目录树 SHA 不一致，或需要第 16 条路径；
- 需要改 V01 的三个产品文件、`domain/vartable`、`domain/plc` 下除 `checker.py` 外的文件、驾驶舱、SDK、Store、合同模型或任何文档才能实现；
- 需要对 `checker.py` 或 `ui/cli/plc/__init__.py` 的既有行做删除或改写才能实现；
- 需要改动模板里的 SCL 代码（不是注释）才能让新项目零差异；
- 既有 Python 路径、`plc check` 命令、v1/v2/v3 证据的输出、退出码、错误文案或证据字节需要改变才能通过某个场景；
- 只能通过 Mock 业务结果、硬编码预期输出、跳过测试、放宽断言、文件级抑制或 `noqa`/`type: ignore` 才能通过；
- 既有测试出现需要改断言的失败；
- `tests/core`、`tests/cli`、`tests/change`、`tests/plc` 内出现无法归因于已登记基线例外的失败，或 `tests/qml` 出现可复现的 Qt 崩溃（按 G2 流程仍无法通过）；
- 任一变异检验存活，或还原后字节不一致；G9 任一通过标准不成立；
- Run 租约已过期（说明续租失效）：停止并报告，不得自行走恢复链；
- Checkpoint 不是当前字节，或质量门未完整返回；
- 发现本卡与代码事实矛盾（先停止，由用户裁决是否出新版本，不得自行改卡）。

## 10. 交付物

1. 基线 SHA 与预检事实表（含 G1 修改前的基线数字与基准目录树 SHA）；
2. CHG / Decision / Work / Run / Checkpoint ID 与 Approval Receipt；
3. 精确 diff 与 15 个路径的最终 SHA-256；
4. G1～G9 矩阵、原始命令、Exit Code、输出位置，以及 G2 对基线的逐目录对照；
5. G3 场景（d01～d20、c01～c08、k01～k08）与测试名称的对照表；
6. 对五个真实 PLC 工程的只读影响复测（对照 §1.4，数字变化须说明原因）；
7. 不可变提交 SHA 与 Checkpoint 绑定核对；
8. 明确声明：`PlcChecker` 现在核对接口文档/变量定义文档与 SCL 的信号名、类型、方向、注释，差异拦住并精确指出，整份缺失只警告；`plc check`、驾驶舱统计与 V01 的 AI 验收门同时生效；`plc docs check/sync/confirm` 可用；补全只补缺行、补入行带 `【待确认】`、从不写 SCL、不覆盖人写文字；新建标准项目开箱零差异。**已知限制必须如实报告**：提交拦截钩子、阶段门与交付拦截未做（V01D），在 V01D 之前文档与代码不一致只会让 `plc check`、验收门与驾驶舱变红，并不阻止提交；DJ-2026-005 与 DJ-2026-009 的任何 PLC 任务现在会被验收门拒绝（§1.4），DJ-2026-009 没有治愈任务；只保证 Siemens SCL 风格的单行声明，其他写法报“无法解析”警告；多行声明与续行不识别；`plc check` 命令退出码仍恒为 0；核对只看变量声明，不核对协议与初值；文档表头别名有限（§5.1-3）；新增的 `doc_consistency.py` 在检查器包内，其改动会使旧 V01 证据失效（设计如此）；运行时 `1.3.3-a808fa8` 不含 U05～V01B 代码。

## 11. 与其他任务的关系与需要用户知悉的决策点

- **V01C｜基准治愈与升基准**（依赖本卡）：用本卡的工具给 DJ-2026-005 生成草稿，用户审核后写入，补齐 19 处代码注释，重新钉基准并更新冒烟钉值。G9 已在隔离副本里预演了这条路径（补注释 → 补全 → 确认 → 验收门通过）。
- **V01D｜提交拦截钩子与阶段门**（依赖本卡与 V01C）：提交时对不一致或带标记的 PLC 提交拦截并自动补全；阶段门“监控→收尾”与交付拦未确认；碰 Hook 基础设施，单独验收。**待 V01D 勘测时定**：钩子只检查本次提交涉及的 PLC 工程，还是全部工程（影响 DJ-2026-009 等未治愈工程的无关提交）。
- **V02**（依赖 V01、V01B、V01C、V01D、C09）：演练工程取自治愈并重新钉死的基准。
- **需要用户在批准本卡时知悉的点**：① 本卡生效后 DJ-2026-005 与 DJ-2026-009 的 `plc check` 会显示失败（005 有 5 项、009 有 3 项），驾驶舱“PLC 检查失败项目数”随之增加，这是预期；DJ-2026-009 没有排治愈任务，是否另开一张治愈卡由用户定；② `sync` 默认直接写文档（补入行带标记，`--dry-run` 可预览），`--apply-suggestions` 才会按代码改写并把旧条目移入文末归档小节（不删除）；③ `plc check` 的退出码仍恒为 0（既有行为，登记为技术债），拦截靠 `plc docs check` 的退出码、V01 的验收门，以及 V01D 的钩子；④ 8 个模板文件由本卡一并修订（只改注释与文档，不改 SCL 代码），不涉及 Obsidian 规范，规范 INT-815 若需同步修订须另走 CHG 由用户审批。
- **技术债候选**：`plc check` 退出码恒为 0；`plc check --json` 输出末尾追加 `launcher:` 行（V01 已登记）；核对只支持单行声明；`tests/test_fixture_health.py` 在基线上因 `tests/qml/test_file_watcher_bridge.py` 的一处条件断言写法而失败（演练在导出目录发现，V01 的 G2 未覆盖该目录，需在真实工作树里确认后登记）。
- **D01**：写入 `plc docs` 的操作说明与已知限制；本卡不改文档。
- WBS 对本卡实际 15 个路径的回写与 M2 总审计不在本卡范围。
