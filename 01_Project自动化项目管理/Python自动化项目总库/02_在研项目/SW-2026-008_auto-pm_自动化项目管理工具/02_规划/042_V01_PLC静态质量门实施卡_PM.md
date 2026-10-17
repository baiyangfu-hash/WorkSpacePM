# V01｜PLC 静态质量门插件实施卡

> 卡片编号：`CARD-SW008-M2-V01`
> 对应 WBS：`V01`（WBS V3.0.20 §4.8 任务表；由 `M2-GOV-WBS4` 提交 `7e2768a1` 校准）
> 版本：`V1.0`（2026-10-03，一次定稿；执行期间不得修订，见 §9）
> 状态：`PLANNED / NOT_AUTHORIZED`（定稿，待授权；授权方式见 §7）
> 依赖：C01～C03 随 M1 已验收（WBS 里程碑 M1 `COMPLETED / ACCEPTED`，含 C01～C09）；U01～U09 已验收收口（U09C 提交 `3c32e8ad`）
> 隔离基线：`3c32e8adc0ebf72691219d88f196cdf3c41266aa`
> 治理任务真源：WBS 提交 `7e2768a138a6e456da84b631b667e4267f4e3cdf`（V3.0.20，CHG-DOCU-2026-025 completed）；WBS SHA-256 `553fcade2bb0d11ba579ac6b8f4cfad1f89c68e61353d1ed4c4d65434fb819de`
> 路径根：`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`
> 推荐执行模型：`Claude Sonnet 4.6 (Thinking)` 或能力不低于它的模型；实际执行者 `Claude Sonnet 5.5`
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

> V1.0 定稿说明：本卡写于一次**可行性演练**之后（§1.6）。演练在项目副本（含 `.ruff.toml` 等点文件）上实现了全部产品改动与两个新测试文件，用真实 Git、真实 PLC 检查器、真实子进程执行器跑通，并在钉死的基准提交上做了真实冒烟。参考实现、冒烟脚本、变异脚本与演练输出归档于 `.auto-pm/reports/m2-v01/`（`proto/<相对路径>` 共 5 个文件、`smoke_pinned_benchmark.py`、`mutation_check.py`、`reference_manifest.json`、`rehearsal/`），仅供参考，不是产品代码；执行者可按参考实现填空，但必须满足 §5 的合同与 §6 的门禁。执行者不得现场修订本卡、扩大路径或放宽门禁；遇到本卡未覆盖的情况按 §9 停止并报告。
> 路径偏差说明：WBS 的 V01 行只写了 `CORE/evidence_collection_service.py` 与 `T/core/test_evidence_collection_service.py` 两个路径。勘测发现，只在证据服务里加一个质量门不能让 PLC 任务走到验收门：执行服务按 profile 分派质量门，Facade 的验证入口把 profile 写死为 `generic`，验收校验只认 v1/v2 证据格式（§1.2）。因此本卡增加 `continuity_execution_service.py` 与 `pm_facade_service.py` 两个产品路径；新测试放在两个新文件里，既有的 `test_evidence_collection_service.py` 不修改（它只测 C01/C02，且字节不变是 G6 的一部分）。WBS 对本卡实际路径的回写留到 M2 总审计。

## 1. 背景与已核实事实（2026-10-03，基线 `3c32e8ad`，均为命令或源码核验）

1. WBS V01 原文：“PLC 静态质量门插件 | 依赖 C01、C03 | 复用现行 PLC checker；违规 SCL 确实失败；.plc.json/SCL/INT/VAR 证据同基线”。WBS §4.8 同时规定 V01 只在“C01/C03 的独立授权及真实 PLC 门禁证据下”启动；本卡的真实证据是 §6 的 G9（钉死基准上的冒烟）。
2. **现状缺口**（基线源码核验）：① 自动 Checkpoint 的质量门有两个 profile：`c03`（固定 C03 测试）与 `generic`（pytest/ruff/mypy），都只认 `.py` 文件；一个只改 SCL/文档的 PLC Run 在 `generic` 下被拒绝（“Run 缺少已批准的 owned Python path”）。② `PmFacadeService.verify_for_acceptance` 把 `profile="generic"` 写死，所以 PLC 任务永远拿不到“已验证”的 Checkpoint，验收门打不开。③ 验收校验 `_acceptance_evidence_is_current` 只认 `checkpoint-evidence.v1/v2`。④ 证据服务里完全没有 PLC 内容。
3. **现行 PLC 检查器事实**（源码与实测）：`PlcChecker(workspace_root).check_project(项目路径)` 是库调用，返回逐项 `pass/warn/fail` 的检查结果；它读取 `.plc.json`、`PM_SESSION_*.md`、PRD 文档、目录结构、工作区根下的 `spec_registry.json`（规范漂移）与 `.plc.json` 声明的库路径关键文件，并对项目下**全部** `.scl` 做 LSP-905 lint；`SclLinter.lint_file(文件)` 可单独 lint 一个文件。检查器对 `接口文档_INT.md` 等 PRD 文档只验证**存在**（文档实质性由另一个 `--substance` 开关的检查负责，不在 `check_project` 内），**不核对** INT/VAR 与 SCL 是否一致。CLI `plc check --json` 的输出末尾会追加一行 `launcher:`、且受控制台编码影响，所以本卡直接调用库，不解析 CLI 输出。
4. **基准项目与钉死**（用户 2026-10-03 同意）：基准为 DJ-2026-005（从三菱 Work3 移植的实际项目，会持续更新）。基准是**一个提交上的目录内容**，不是活目录：钉死提交 `3c32e8adc0ebf72691219d88f196cdf3c41266aa`，该提交上 `0100_PLC自动化/DJ-2026-005` 的 Git 目录树 SHA 为 `b457f2b95acd58db7cf65207236ef0999ebda9dd`（G9 先核对相等，不等即停）。在该内容上，现行检查器实测为 50 通过、1 警告（Spec Snapshot 规范漂移，来自规范库版本变化而非项目）、0 失败，12 个 SCL 文件。项目继续更新不影响本卡；把新进展纳入基准要走独立的“升基准”（§11）。
5. 三个真实 PLC 工程在主工作区的现行检查结果（只读，`plc check`）：DJ-2026-011 为 12 通过/0 警告/0 失败；DJ-2026-005 为 50/1/0；DJ-2026-000 为 10/1/1（`FB100/FB_ValveControl.scl` 有 11 处 LSP-905 违规）。因此项目级检查按“有失败项即不通过”落实后，DJ-2026-000 内的任何 Run 都会被拒绝，直到该工程被治愈——这是设计（先治愈基准再沉淀），不是缺陷。
6. **可行性演练结果**（归档于 `.auto-pm/reports/m2-v01/rehearsal/`）：① 参考实现过 `ruff` 与 `mypy --strict`（5 个路径，零 `type: ignore`/`noqa`）；② 两个新测试文件共 32 个测试全部通过（服务层 21 个，链路层 11 个，含真实子进程执行器的 PLC 任务从执行到验收门打开再到验收成功）；③ 既有的 16 个 `verify/accept` Facade 测试在参考实现上全过；④ 钉死基准冒烟（G9 脚本）在 DJ-2026-005 上：干净内容通过、追加违规 SCL 后失败且指出文件与行、改动接口文档后收据失效、还原后恢复有效；演练期间发现并已纳入合同的真实问题：项目有 50 多个检查项时，诊断摘要被截断会丢掉失败项，因此失败与警告必须排在输出最前（§5.1-9）；⑤ 12 处变异（§6 G8）全部被对应测试抓住、源文件字节全部还原；最终字节上的 `ruff` 与 `mypy --strict` 复验通过；最终字节上的冒烟复跑通过（目录树 SHA 与钉值相等、profile 为 `plc`、干净内容 PASS 且两门退出码均为 0、追加违规后 FAIL 且失败项排在摘要最前、改动接口文档后收据失效、还原后恢复有效、临时工作树结束时无脏文件；检出约 10 秒、干净内容的质量门约 20 秒）。既有 5 个测试文件在参考实现上的**整体**兼容回归以 G1 在候选最终字节上的结果为准（演练只单独复核了 16 个 `verify/accept` 的 Facade 测试）。输出归档于 `rehearsal/`。
7. **基线实测**（`3c32e8ad` 干净导出、改动前，含 `.ruff.toml`）：G1 的 5 个既有文件 **236 passed**、0 failed、0 skipped（用时约 57 分钟，期间机器被其他测试占用）；输出 `.auto-pm/reports/m2-v01/gates/G1_baseline.txt`。
8. G2 基线沿用 U09C Run004 终态（同一提交 `3c32e8ad`，原始输出在 `.auto-pm/reports/m2-u09c-run004/window3/`）：contracts 191 passed 1 skipped；infrastructure 32 passed；cli 252 passed 1 skipped；change 230 passed；core 916 passed 1 skipped 3 failed（失败即 E-G1-1，位于 `tests/core/test_implementation_card_service.py`，非本卡路径）；qml 283 passed（排除一个测试）+ 该测试单独 1 passed。
9. 已登记的基线例外沿用：E-G1-1、E-G1-2、E-G1-3、E-G3-1。
10. **明确不在本卡**：INT/VAR 与 SCL 的**一致性核对**（现行检查器没有这种能力，新增是新的领域逻辑，须另开卡）；PLC 上机编译与下发（由用户接管，WBS 约定）；V02 的 PLC 演练工程与“新目标到 SCL 变化”的完整闭环；模板提取；`plc check` 命令的输出编码与 `launcher:` 行；`.trae`、Hook、release、文档（含 D01 的操作手册）；任何 schema、事件类型、迁移。

## 2. 单一目标（用户故事与完成定义）

作为验证 PLC 任务的 PM：

1. PLC 任务（Run 的 owned 路径位于带 `.plc.json` 的 PLC 工程内）在 `verify_for_acceptance` 里**自动**选择 PLC 质量门，质量门通过后生成内容绑定的 `checkpoint-evidence.v3` Checkpoint，验收门打开，`accept` 可成功；
2. 项目内存在违规 SCL（无论是被授权的文件，还是同一工程内的其他文件）时，质量门不通过：不生成 Checkpoint、验收门不打开、现场保留；诊断指出文件与行；
3. 证据与基线同源：质量门在**候选工作树**上调用现行检查器；验证之后，PLC 工程根目录下**任何**文件（含被 Git 忽略的文件）、被授权路径或检查器自身代码发生变化，已存的证据立即失效、验收门关闭；
4. 一个 Run 只验证一个领域：同时拥有 PLC 工程路径与 PLC 工程之外的 `.py` 路径被拒绝，不让一个领域的门静默忽略另一个领域的文件；
5. Python 路径一字不变：`c03`、`generic` 的行为、v1/v2 证据格式、既有错误文案与全部既有测试保持原样。

## 3. 实施前预检（只读，先于任何写入）

1. 核验本卡字节 SHA-256 已被外部 Approval Receipt 绑定；核验 `隔离基线` 是 U09C 提交且可解析（分支 `codex/m2-u09c-lifecycle-final` 仍在 `3c32e8ad`）、WBS 提交与 SHA-256 一致。
2. 运行 `main.py implementation-card precheck --card-file` 对本卡，退出码必须为 0。
3. 核验 §4 中 3 个“存在”路径在基线上存在、2 个“计划新增”路径在基线上不存在。
4. 在隔离候选中，对 §6 G1 的 5 个既有测试文件复现基线结果 **236 passed**（修改前），`ruff` 与 `mypy --strict` 对 §4 已存在的 3 个 Python 路径通过；不一致则停止。
5. 核验隔离候选 HEAD 等于基线，configured/effective runtime 与加载路径一致且无 fallback；核验基准目录树 SHA（§1.4）。
6. 阅读 `.auto-pm/reports/m2-v01/proto/` 下的参考实现与 `mutation_check.py`、`smoke_pinned_benchmark.py`，确认其做法与本卡 §5 一致；核对 `reference_manifest.json` 中各文件的 SHA-256。
7. **续租（硬性）**：开始任何超过 30 分钟的门禁（G1 约 35～60 分钟，G2 的 core 约 62 分钟）之前先续租；后台任务约 30 分钟会被系统杀掉外壳（已启动的测试进程不受影响），所以按 U09C Run004 的做法，每个检查周期（不超过 25 分钟）手动续一次租，单次续租不超过 3600 秒，finalize 前租约须剩余 300 秒以上。租约过期时停止并报告，不得自行走恢复链。
8. **判卷与门禁工具先验证再起长批次**（U09C 教训）：判卷脚本与变异脚本必须先在真实输出上跑通一次，再启动 G1/G2 长批次；工具字节一旦被证据绑定，任何修正都会使整个窗口重开。
9. **长批次不得重叠**：G1、G2 的各目录、G9 冒烟按顺序单独运行，不与 `tests/qml` 组重叠；演练表明重叠会让用时翻倍。

## 4. 精确 Owned Paths（5）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `auto_pm/application/core/evidence_collection_service.py` | 存在 | 新增 PLC 质量门、PLC 收据与 v3 证据（只追加；唯一改动的既有行是 `build_checkpoint_evidence` 的参数类型） |
| 2 | `auto_pm/application/core/continuity_execution_service.py` | 存在 | `append_verified_checkpoint` 增加 `plc` profile |
| 3 | `auto_pm/application/core/pm_facade_service.py` | 存在 | 验证入口按 Run 选择 profile；验收校验识别 v3 |
| 4 | `tests/core/test_plc_quality_gate.py` | 计划新增 | 服务层测试（合成 PLC 工程） |
| 5 | `tests/core/test_plc_checkpoint_chain.py` | 计划新增 | 链路层测试（Checkpoint 与 Facade 端到端） |

出现第 6 条产品脏路径即停止，不得现场扩大 Decision。治理证据对象在控制根落账，不计入上述路径。

## 5. 合同（全部定稿，执行者不得改写含义）

### 5.1 `auto_pm/application/core/evidence_collection_service.py`（只追加；唯一改动的既有行见 §6 G6）

新增（均在既有类与函数之外追加，或作为 `EvidenceCollectionService` 的新增成员）：

1. **常量**：`_PLC_CHECKPOINT_SCHEMA = "checkpoint-evidence.v3"`、`_PLC_CHECK_COMMAND = "auto_pm.plc.checker.PlcChecker.check_project"`、`_PLC_LINT_COMMAND = "auto_pm.plc.scl_linter.SclLinter.lint_file"`、`_PLC_MIXED_DOMAIN_ERROR`（文案含“一个 Run 只验证一个领域”）。
2. **`PlcQualityReceipt`**（冻结数据类，加入 `__all__`）：字段 `run_id`、`baseline_git_head`、`candidate_path`、`project_root`、`evidence_hash`、`gates`（沿用 `PythonQualityGate` 作为单个门的结果形状）、`evidence_current`、`evidence_error`、`content_hash`、`project_roots`、`owned_plc_paths`、`input_digests`（`(相对候选的工程目录, sha256)` 元组）、`checker_digest`；属性 `status`：当且仅当 `evidence_current`、`gates` 非空且每个门 `exit_code == 0` 时为 `PASS`，否则 `FAIL`。私有 `_OwnedPath`、`_PlcProject` 数据类。
3. **归属判定**：`checkpoint_profile_for_run(run) -> str`：在已验证的候选上规范化全部 owned 路径；某路径属于 PLC 工程，当且仅当其所在目录链（若路径本身是目录则含它自己）上、**候选根之下**，存在含 `.plc.json` 的目录，**取最高的那一层**为工程根（候选根上的 `.plc.json` 不算）。有 PLC 路径且同时有不在任何 PLC 工程内的 `.py` 路径 → 抛 `EvidenceCollectionError`（`_PLC_MIXED_DOMAIN_ERROR`）；有 PLC 路径 → `"plc"`；否则 `"generic"`。
4. **目标推导**（私有静态 `_plc_project_targets`）：把属于 PLC 工程的 owned 路径按工程根分组（按路径字符串排序）；每个路径必须位于调用方给的 `project_root` 之下（否则报“质量门 project_root 未覆盖 Run owned PLC path”）；owned 的 `.scl` 文件必须存在（否则报“Run owned SCL path 不存在”）；owned 目录则其下全部 `.scl` 均列入；`.scl` 判断不区分大小写；没有任何 PLC 路径报“Run 缺少 PLC 工程内的 owned path”（该检查先于混合领域检查）。
5. **公开方法**：`validate_plc_checkpoint_project_root(run, project_root) -> Path`；`run_plc_checkpoint_quality_gates(run, project_root) -> PlcQualityReceipt`；`plc_quality_receipt_is_current(run, project_root, receipt) -> bool`（不重跑门，只核对收据是否仍描述当前 Run 与输入）。
6. **门计划**（私有静态 `_plc_gate_plan`，生产与回放校验共用，避免漂移）：对每个工程，固定一个 `plc-check` 门，命令为 `(_PLC_CHECK_COMMAND, 相对候选的工程目录)`；若该工程有 owned SCL，再固定一个 `scl-lint` 门，命令为 `(_PLC_LINT_COMMAND, *相对工程根的 SCL 路径)`；`cwd` 为工程根绝对路径。
7. **门执行**（进程内、只读）：`plc-check` 调用 `PlcChecker(候选工作树根).check_project(工程根)`——**工作区根必须是候选工作树，不得是控制根**，这样规范注册表与库路径取自 Run 基线；结果 `not_applicable` → `exit_code=None`（失败收据，文案含“不适用”）；`fail_count > 0` → `exit_code=1`；否则 `0`。`scl-lint` 对每个 owned SCL 调用 `SclLinter.lint_file`，任一 ERROR → `exit_code=1`，否则 `0`，输出含 `文件:行 严重级别 信息` 与末行汇总。任何异常 → `exit_code=None`、输出以 `launch error: ` 开头（失败收据，不得抛出）。`output_digest` 为完整输出的 SHA-256，`output_summary` 经现有的 `_safe_output_summary` 限长。
8. **输入绑定**（私有静态 `_plc_input_digests`）：对每个工程根，遍历其下**全部**文件（不含 `.git` 目录，含被 Git 忽略的文件；符号链接记录目标文本而不跟随），按相对路径排序后对（相对路径, 文件字节 SHA-256）求规范化哈希。门运行前后各算一次，不相等则 `evidence_current` 为 false 且 `evidence_error` 含“PLC 输入已变化”。**检查器指纹**（私有静态 `_plc_checker_digest`）：已加载的 `auto_pm.plc.checker` 所在包目录下全部 `*.py` 按文件名排序的（文件名, SHA-256）的规范化哈希。
9. **摘要排序**：`plc-check` 的输出把 `fail` 行排最前、`warn` 次之、`pass` 最后（稳定排序），末行为 `pass=N warn=N fail=N`，使有限长度的摘要不会丢掉失败原因。
10. **收据与证据**：`PlcQualityReceipt.content_hash` 为固定载荷（含 `domain: "plc"`、全部字段与每个门的序列化结果）的 SHA-256；`build_checkpoint_evidence(collection, receipt)` 接受 `PythonQualityReceipt | PlcQualityReceipt`（这是对既有行的唯一改动，仅参数类型），遇 PLC 收据构建 `checkpoint-evidence.v3`：键恰为 `schema_version`、`collection`、`collection_hash`、`quality_receipt`（载荷加 `status`）、`receipt_hash`、`envelope_hash`；收据非 PASS、非当前、或与 collection 不一致时抛 `EvidenceCollectionError`（文案含“不一致”）。
11. **回放校验**：`checkpoint_evidence_is_current` 在既有 v2 分派之后新增 v3 分派，调用新的私有静态 `_plc_checkpoint_evidence_is_current`：信封键集合、规范化字节相等、信封哈希、collection 相等；载荷键集合恰为 `domain`、`run_id`、`baseline_git_head`、`candidate_path`、`project_root`、`evidence_hash`、`gates`、`evidence_current`、`evidence_error`、`project_roots`、`owned_plc_paths`、`input_digests`、`checker_digest`、`status`；**重新推导**工程根、owned 路径、门计划、输入哈希与检查器指纹并逐项比对；每个门恰有 `name/command/cwd/exit_code/output_digest/output_summary` 六个键、`exit_code` 为整数 0、`output_digest` 非空。
12. **不改**：C01 采集、`generic`/`c03` 的全部逻辑与收据、v1/v2 信封的构建与回放（字节与行为不变）。

### 5.2 `auto_pm/application/core/continuity_execution_service.py`

1. 新增模块常量 `_AUTO_CHECKPOINT_SCHEMAS = {"c03": "checkpoint-evidence.v1", "generic": "checkpoint-evidence.v2", "plc": "checkpoint-evidence.v3"}`，既有“存档证据 schema 必须与 profile 匹配”的比较改用它。
2. `append_verified_checkpoint` 的 profile 校验增加 `plc` 分支（调用 `validate_plc_checkpoint_project_root`）；未知 profile 的既有文案不变。
3. 门执行改为三路：`plc` → `run_plc_checkpoint_quality_gates`；`c03` → `run_c03_checkpoint_quality_gates`；其余 → `run_generic_checkpoint_quality_gates`。收据非 PASS 的文案为 `自动 Checkpoint 要求 {领域} 质量收据为 PASS`，收据失效的文案为 `自动 Checkpoint 的 {领域} 质量收据已失效`，其中领域对 `plc` 为 `PLC`、其余为 `Python`（Python 路径的文案字节不变）；C03 的固定 profile 校验仍只对 `c03` 且为 Python 收据时执行；“收据是否当前”对 PLC 收据调用 `plc_quality_receipt_is_current`，对 Python 收据调用既有方法。
4. 幂等键：`plc` 使用前缀 `plc-auto-checkpoint:`，载荷的 `schema_version` 为 `plc-auto-checkpoint-key.v1`，其余字段与既有两种键同构；`c03` 与 `generic` 的键一字不变。
5. 不改其余任何方法、状态机与租约逻辑。

### 5.3 `auto_pm/application/core/pm_facade_service.py`

1. `verify_for_acceptance`：在同一个 `try` 内先 `EvidenceCollectionService(self._workspace_root).checkpoint_profile_for_run(run)` 得到 profile，再把它传给 `append_verified_checkpoint`（替换写死的 `profile="generic"`）；`except` 同时捕获 `ContinuityExecutionError` 与 `EvidenceCollectionError`，两者都按既有“质量验证未通过”路径返回（`verified=False`、既有文案、现场保留、不写 Checkpoint）。
2. `_acceptance_evidence_is_current`：识别 `checkpoint-evidence.v3`，与 v2 一样交给 `EvidenceCollectionService.checkpoint_evidence_is_current`；v1 分支与其余逻辑不变。
3. 不改其余任何方法。

### 5.4 必测场景（G3）

测试文件中的每个测试函数都须对应下表一个场景；场景编号写在测试名里（`test_p01_…`）。测试不得通过 Mock 业务结果、硬编码预期字段或跳过来变绿；对 `PlcChecker.check_project`、`EvidenceCollectionService._plc_checker_digest`、`_run_plc_gate` 的打桩只允许用于“外部故障注入”（p04、p13、p14）。

**服务层 `tests/core/test_plc_quality_gate.py`**（合成 PLC 工程提交进临时仓库，不依赖任何活工程）：

| 场景 | 要证明的行为 |
|---|---|
| p01 | 合规工程：`plc-check`、`scl-lint` 两门 `exit_code` 为 0，收据 PASS、绑定 Run 基线；v3 信封可构建且可回放 |
| p02 | 被授权的 SCL 违规：两门均为 1；摘要指出文件与行，`plc-check` 摘要首行以 `fail | ` 开头；不能构建信封；收据不再是当前 |
| p03 | 同一工程内**未被授权**的 SCL 违规（基线已存在）：`plc-check` 为 1、`scl-lint` 为 0 |
| p04 | 检查器崩溃与“不适用”结论各得到 `exit_code=None` 的失败收据（崩溃文案含 `launch error`，不适用文案含“不适用”） |
| p05 | profile：PLC Run 为 `plc`；纯 Python Run 为 `generic`；PLC 加 Python 混合被拒绝（含对 `run_plc_checkpoint_quality_gates` 的直接调用） |
| p06 | 工程根取最高的 `.plc.json` 目录；候选根上的 `.plc.json` 被忽略；嵌套 `.plc.json` 的 SCL 归属外层工程 |
| p07 | owned 为目录时，其下全部 SCL 都被 lint，违规被发现 |
| p08 | 两个 PLC 工程按序各得到自己的门（`cwd` 与顺序固定） |
| p09 | owned SCL 不存在、`project_root` 未覆盖、没有任何 PLC 路径，各自被拒绝并有明确文案 |
| p10 | 越权的脏文件在任何门运行之前被拒绝 |
| p11 | 被授权文件改动后收据失效 |
| p12 | 被 Git 忽略的工程内文件改动：Git 证据哈希不变，但收据与 v3 信封均失效 |
| p13 | 门运行期间输入改变：收据 `evidence_current` 为 false 且为 FAIL，错误含“PLC 输入已变化” |
| p14 | 检查器构建指纹变化：收据与 v3 信封均失效 |
| p15 | 六种篡改（失败退出码、少一个门、工程根被改、领域被改、输出哈希置空、未重签的编辑）即使重签也被拒绝，且原始信封仍被接受 |
| p16 | 警告不挡门，但被记录在输出里，末行含 `fail=0` |

**链路层 `tests/core/test_plc_checkpoint_chain.py`**（`append_verified_checkpoint` 与真实 Facade、真实子进程执行器，复用 `tests/core/test_pm_run_e2e.py` 的 `_Env` 与文案常量、`tests/core/test_continuity_execution_service.py` 的 `Clock` 与 `_start`，只导入不修改）：

| 场景 | 要证明的行为 |
|---|---|
| h01 | `profile="plc"` 追加 v3 Checkpoint，两门齐全；相同调用重放得到同一 Checkpoint（序号仍为 1） |
| h02 | 被授权的 SCL 改动后，已存的 Checkpoint 无法重放（identity 不一致） |
| h03 | 违规 SCL 不能产生 Checkpoint，库内没有该 Run 的 Checkpoint |
| h04 | 未知 profile 与对 PLC 任务用 `generic` 都被拒绝，不留 Checkpoint |
| h05 | PLC 任务同时拥有 PLC 工程之外的 Python 路径被拒绝 |
| e01 | 合规的 PLC 任务经真实子进程执行后被验证，生成 v3 Checkpoint，验收门打开，`accept` 成功；控制根的源文件未被改动 |
| e02 | 违规 SCL：未验证、现场保留、Mission 仍为 ACTIVE、Run 仍为 VERIFYING、没有 Checkpoint、验收门关闭、`accept` 被拒绝 |
| e03 | 验证之后改动被授权的 SCL，或改动工程内被 Git 忽略的文件，验收门都关闭且 `accept` 被拒绝 |
| e04 | PLC 加 Python 混合的任务不被验证、没有 Checkpoint |
| e05 | 已验证任务的重放不再起子进程、不增加事件与 Checkpoint |

### 5.5 明确不做

不做 INT/VAR 与 SCL 一致性核对；不改 PLC 检查器、Linter、模型与任何 `domain/plc` 文件；不改 C01 采集、Python 质量门、v1/v2 证据；不改 CLI、驾驶舱、Bridge、QML、SDK、Store、合同模型；不新增 schema、事件类型或迁移；不改任何文档；不做 PLC 上机编译或下发；不合并、不推送、不部署、不切换 release。

## 6. 门禁矩阵

所有命令均在隔离候选的项目根执行，使用工作区 `.venv` 解释器与 `-B`，先 `-o addopts= --no-cov -p no:cacheprovider`。

**G1 定向测试**（修改前先对基线跑同一集合中的 5 个既有文件并记录数字；修改后全部通过，0 失败，不新增跳过）：

```powershell
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider `
  tests/core/test_evidence_collection_service.py tests/core/test_continuity_execution_service.py `
  tests/core/test_pm_facade_service.py tests/core/test_pm_run_e2e.py tests/cli/test_continuity.py `
  tests/core/test_plc_quality_gate.py tests/core/test_plc_checkpoint_chain.py
```

基线数字：5 个既有文件 236 passed（§1.7）；候选须不少于 236 + 本卡新增测试数（演练为 32，即 268），且 0 failed、0 skipped。

**G2 分目录回归**（固定方法，同 U05～U09C；基线数字见 §1.8；候选相对基线：失败集合相同——core 仅 E-G1-1 的 3 个既存失败、通过数不少于基线加本卡 core 新增测试数、无新增失败、无新增跳过；其余目录通过数不少于基线）：

```powershell
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/contracts
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/infrastructure
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/cli
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/change
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/core
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/qml --deselect tests/qml/test_file_watcher_bridge.py::test_debounce_coalesces_events
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/qml/test_file_watcher_bridge.py::test_debounce_coalesces_events
```

各组都必须在**最终字节**上全量重跑；core 约 62 分钟（U09C Run004 实测 3728 秒，时间上限按 8000 秒设），**必须先按 §3-7 续租**。`tests/qml` 组出现 Qt access violation 不得按 E-G1-2 豁免：先在全新进程单独重跑出问题的文件一次并保存两次原始输出；仍崩溃则按 §9 停止。

**G3 必测场景**：§5.4 的 p01～p16、h01～h05、e01～e05 各至少一个独立测试，并在判卷报告中列出“场景 → 测试名”对照；测试文件中的每个测试函数都须对应一个场景（p15 与 e03 允许参数化）。

**G4 静态质量**：

```powershell
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m ruff check --no-cache auto_pm/application/core/evidence_collection_service.py auto_pm/application/core/continuity_execution_service.py auto_pm/application/core/pm_facade_service.py tests/core/test_plc_quality_gate.py tests/core/test_plc_checkpoint_chain.py
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m mypy --strict --no-incremental auto_pm/application/core/evidence_collection_service.py auto_pm/application/core/continuity_execution_service.py auto_pm/application/core/pm_facade_service.py tests/core/test_plc_quality_gate.py tests/core/test_plc_checkpoint_chain.py
git diff --check
```

不得使用 `--follow-imports=skip`，不得新增文件级抑制或为通过门禁新增 `type: ignore`/`noqa`；在最终字节上运行；两个新增（未跟踪）文件另行扫描行尾空白、制表符与回车字符（仓库约定为 LF；用 Python 按字节检查，不要用 Shell 的 `grep` 匹配回车）。

**G5 范围与洁净**：`git diff --name-only` 加未跟踪文件的路径集合精确等于 §4 的 5 个路径；无 `.coverage`、缓存、`tmp_*` 残留（DEV-TMP-001）；任何 `.qml` 文件无改动。

**G6 既有内容不变**：① `evidence_collection_service.py` 的 diff 中被删除或改写的既有行**只有一行**：`        collection: EvidenceCollection, receipt: PythonQualityReceipt`（改为联合类型）；② `continuity_execution_service.py` 被删除或改写的既有行只允许是下列 10 行的原文：`!= ("checkpoint-evidence.v1" if profile == "c03" else "checkpoint-evidence.v2")`；`receipt = (`、其后三行 `collector.run_c03_checkpoint_quality_gates(run, project_root)`、`if profile == "c03"`、`else collector.run_generic_checkpoint_quality_gates(run, project_root)` 与单独的 `)`；`raise ContinuityExecutionError("自动 Checkpoint 要求 Python 质量收据为 PASS")`；`if profile == "c03" and not collector.c03_checkpoint_receipt_matches_profile(receipt):`；`if not collector.quality_receipt_is_current(run, project_root, receipt):`；`raise ContinuityExecutionError("自动 Checkpoint 的 Python 质量收据已失效")`；③ `pm_facade_service.py` 被删除或改写的既有行只允许是下列 3 行的原文：`profile="generic",`；`except ContinuityExecutionError:`；`if isinstance(envelope, dict) and envelope.get("schema_version") == "checkpoint-evidence.v2":`；④ G1 的 5 个既有测试文件与 `tests/core/test_plc_*.py` 之外的任何测试文件字节不变（均不在 owned paths 内）；⑤ v1 与 v2 证据的既有测试（`tests/core/test_evidence_collection_service.py`、`tests/core/test_continuity_execution_service.py`、`tests/core/test_pm_facade_service.py`）不改一个断言。

**G7 不触碰生产**：测试只使用临时目录与临时库，不读写真实控制面的 `.auto-pm/continuity.db` 与真实 `00_Infrastructure`；不改 Hook、release、`.auto-pm` 下任何运行态对象；G9 只在隔离克隆里操作，不改真实仓库的任何分支与工作树。

**G8 变异检验**（执行者在代码完成后、最终门禁之前运行，结果绑定进判卷）：运行 `.auto-pm/reports/m2-v01/mutation_check.py`（12 处变异：质量门缺失、失败不报失败、输入未绑定、检查器指纹不比对、混合领域放行、取最低工程根、“不适用”判通过、回放忽略领域、执行服务不校验 plc、Facade 恒用 Python profile、验收不认 v3、Facade 对混合 Run 放行）；每处变异后对应测试必须变红，源文件随后原样还原并校验字节；任一变异存活或还原后字节不一致即停止；执行者可再增补。输出归档于 `.auto-pm/reports/m2-v01/mutation_check_output.json`。

**G9 钉死基准冒烟**（真实证据，WBS 对 V01 的启动前提）：在候选的最终字节上，从候选项目根运行：

```powershell
$env:PYTHONPATH = (Get-Location).Path
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B C:\Users\fubai\Documents\My_Workspace\.auto-pm\reports\m2-v01\smoke_pinned_benchmark.py --repo C:\Users\fubai\Documents\My_Workspace --commit 3c32e8adc0ebf72691219d88f196cdf3c41266aa --project-path "0100_PLC自动化/DJ-2026-005" --tree-sha b457f2b95acd58db7cf65207236ef0999ebda9dd --scl "0100_PLC自动化/DJ-2026-005/02_PLC程序/PLC_ST/05_公共报警/FB_2001_CommonAlarm_AllStation.scl" --doc "0100_PLC自动化/DJ-2026-005/02_PLC程序/PLC_ST/00_程序方案/接口文档_INT.md" --out C:\Users\fubai\Documents\My_Workspace\.auto-pm\reports\m2-v01\gates\g9_smoke.json
```

脚本把真实仓库硬链接克隆到临时目录，在克隆里为钉死提交建分离的临时工作树，**不创建任何治理对象**，结束后清除。通过标准（退出码 0，且 JSON 中均成立）：目录树 SHA 与钉死值相等；profile 为 `plc`；干净内容的收据为 PASS 且两门退出码均为 0、v3 信封可回放；对授权的 SCL 追加违规声明后收据为 FAIL 且 `scl-lint` 退出码为 1、摘要指出该 SCL 与行；改动授权的接口文档后，此前的干净收据不再是当前；还原后恢复为当前；临时工作树结束时无脏文件。目录树 SHA 不等视为基准漂移，立即停止，不得改写钉值（升基准走 §11）。

## 7. 实施授权签字门

### 7.1 当前签字状态

| 字段 | 当前值 |
|---|---|
| 卡片 | `CARD-SW008-M2-V01 V1.0` |
| 实施批准 | `PENDING`（须用户在对话中明确批准；批准后以委托方式由 Claude 执行，回执另行生成） |
| 最终验收 | `PENDING`（验收由用户做出；CHG 收口须经用户在对话弹窗确认后才可由 Claude 代跑） |
| 审批人 | `fubai / baiyang`（同一用户、等权署名） |
| 隔离基线 | `3c32e8adc0ebf72691219d88f196cdf3c41266aa` |
| Owned Paths | §4 的 5 个路径 |
| 执行模型 | `Claude Sonnet 5.5` |
| 明确禁止 | 第 6 条路径、改 PLC 检查器/Linter/`domain/plc`、改 C01 采集与 Python 质量门、改 v1/v2 证据、改 CLI/驾驶舱/SDK/Store/合同模型、新增 schema 或迁移、对既有语句做 §6 G6 白名单之外的删除或改写、改文档、直接改真实库、历史改写、Hook/release 修改、改动基准钉值、合并、推送、部署 |

### 7.2 授权成立与失效

1. 卡片字节、隔离基线、WBS 真源、owned paths、执行模型或禁止事项任一漂移，审批立即失效。
2. 外部 Approval Receipt 绑定本卡完整字节 SHA-256、基线、WBS 提交、5 个路径、允许/禁止动作、执行模型、审批人与时间；卡片自身不含自身 SHA-256。
3. 实施批准与最终验收分离；执行 Agent 不得自签验收。

## 8. 治理执行顺序

1. 只读预检并输出事实表（§3），含 G1 修改前的基线数字。
2. 用户批准本卡后，创建并批准 SW-2026-008 的独立 CHG（领域 SCPT）与精确 Decision（§4 五路径，计划新增路径不检查基线存在；Decision 建议 `DEC-20261003-V01PLCQG`，日期以起卡当天为准，后缀须恰 8 位）。
3. 创建 Work（`--card-file` 指向本卡，Work 与 Decision 的项目一致，均为 SW-2026-008；建议 `WORK-SW008-M2-V01-001`）、在全新隔离候选（自 U09C 提交 `3c32e8ad` 起，分支 `codex/m2-v01-plc-quality-gate`，工作树 `.auto-pm/worktrees/m2-v01`）启动 Run（`--lease-seconds` 不超过 3600；建议 `RUN-SW008-M2-V01-001`），并按 §3-7 管理续租。
4. 在候选中按 §5 实现、运行 G8 变异检验并完成 §6 门禁；判卷结果写入 `.auto-pm/reports/m2-v01/` 下机器可读判卷文件。
5. 创建当前字节 Checkpoint（`git_head` 为基线，逐文件记录 SHA-256 与判卷文件 SHA-256），**先于提交**；随后走正常 Hook 提交（不得 `--no-verify`）；提交后核验提交内 blob 与 Checkpoint 逐一相同，否则停止。
6. Run/Work 终态、台账 `main.py ledger reconcile SW-2026-008` 为 0/0/0；CHG 收口须经用户弹窗确认后由 Claude 代跑，或由用户自己运行。
7. 向用户报告后停止；SHA 与 ID 写入交接文档。WBS 对本任务结果的回写为独立的后续修订，不在本卡范围。

## 9. 有界纠正与硬停止条件

本卡单提交，一个主 Run；仅当失败稳定复现、完全落在 §4 路径内、无需合同或路径扩展时，允许一个纠正 Run（必须新建 Run 并重建 Checkpoint）。**执行期间不得修订本卡**；需要修订本卡即属于硬停止。

以下任一情况立即保留现场、停止并报告：

- 基线 HEAD、runtime 身份、Decision 字节、owned paths 或基准目录树 SHA 不一致，或需要第 6 条路径；
- 需要改 PLC 检查器/Linter/`domain/plc`、Python 质量门、v1/v2 证据、CLI、驾驶舱、SDK、Store、合同模型或任何文档才能实现；
- 需要对既有语句做 §6 G6 白名单之外的删除或改写才能实现；
- 既有 Python 路径的输出、退出码、错误文案或证据字节需要改变才能通过某个场景；
- 只能通过 Mock 业务结果、硬编码预期输出、跳过测试、放宽断言、文件级抑制或 `noqa`/`type: ignore` 才能通过；
- 既有测试出现需要改断言的失败；
- `tests/core`、`tests/cli`、`tests/change` 内出现无法归因于 E-G1-1 的失败，或 `tests/qml` 出现可复现的 Qt 崩溃（按 G2 流程仍无法通过）；
- 任一变异检验存活，或还原后字节不一致；G9 任一通过标准不成立；
- Run 租约已过期（说明续租失效）：停止并报告，不得自行走恢复链；
- Checkpoint 不是当前字节，或质量门未完整返回；
- 发现本卡与代码事实矛盾（先停止，由用户裁决是否出新版本，不得自行改卡）。

## 10. 交付物

1. 基线 SHA 与预检事实表（含 G1 修改前的基线数字与基准目录树 SHA）；
2. CHG / Decision / Work / Run / Checkpoint ID 与 Approval Receipt；
3. 精确 diff 与 5 个路径的最终 SHA-256；
4. G1～G9 矩阵、原始命令、Exit Code、输出位置，以及 G2 对基线的逐目录对照；
5. G3 场景（p01～p16、h01～h05、e01～e05）与测试名称的对照表；
6. 不可变提交 SHA 与 Checkpoint 绑定核对；
7. 明确声明：PLC 任务现在自动走 PLC 质量门并可到达验收门；质量门在候选工作树上调用现行检查器，失败项即不通过，警告只记录；证据以 `checkpoint-evidence.v3` 绑定 PLC 工程根下全部文件字节与检查器指纹；一个 Run 只验证一个领域；Python 路径与 v1/v2 证据不变。**已知限制必须如实报告**：INT/VAR 与 SCL 的一致性未核对（只做同基线绑定）；进程内门没有超时；检查器指纹只覆盖 `plc` 包本身（不含 `find_prd_dir` 所在模块）；工程根之外被 Git 忽略的输入（规范注册表、库目录）不在输入绑定内，只靠 Git 基线与越权脏文件拒绝保护；整项目检查意味着已有失败项的工程（如 DJ-2026-000）内的任何 Run 都会被拒绝；`plc check` 命令的输出编码问题未处理；基准钉在提交 `3c32e8ad` 的目录树 SHA，不随项目更新；运行时 `1.3.3-a808fa8` 不含 U05～V01 代码。

## 11. 与其他任务的关系

- **V02｜PLC 新需求静态闭环**（依赖 V01、C09）：在本卡的质量门之上做“新目标 → 真实 SCL 变化 → 静态门禁 → 验收落账”。演练工程取自钉死的 DJ-2026-005 基准，在隔离副本里改，不改活目录。V02 的 owned 路径不含本卡的三个产品文件，所以接线必须在本卡完成。
- **V08｜从通过的 PLC 基准提取模板**：从钉死的基准目录树提取，不从活目录提取；基准必须先全绿再提取（AGENTS 的“标杆驱动基建法则”）。
- **升基准**：想把 DJ-2026-005 的新进展纳入基准，须新提交上先让现行检查器全绿，再由独立的卡替换钉值（提交与目录树 SHA）并重跑 G9；本卡不提供改写钉值的权限。
- **技术债候选**：`plc check --json` 的输出末尾追加 `launcher:` 行且受控制台编码影响（本卡不处理，M2 总审计时登记）。
- **D01**：写入 PLC 任务的验证流程说明与已知限制；本卡不改文档。
- WBS 对本卡实际 5 个路径的回写与 M2 总审计不在本卡范围。
