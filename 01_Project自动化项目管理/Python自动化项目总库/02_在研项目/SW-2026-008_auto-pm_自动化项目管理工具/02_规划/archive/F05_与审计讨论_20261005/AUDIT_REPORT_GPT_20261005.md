# M2 已收口任务独立审计报告

审计日期：2026-10-05（America/Phoenix）  
审计者：Codex / GPT；主代理核验与三个只读子代理交叉审计。

**结论：V02 和技术债回写的交付证据成立；V01D 存在已复现的门禁绕过；V03 已测的底层交接机制成立，但不能认定原 WBS 的全部验收目标已实现。补充核验确认：同一被审代码中的 E06 真实派发恢复身份错误，以及 WAL 边车瞬态校验缺口，限制了 V04 的恢复与并发稳定性结论。** 本报告不撤销已有用户验收，不代替 M2 总审计，也不授予修复、开工或部署权限。

建议 V04 前处理判卷合同、重放覆盖和授权证据边界；V04 验收前关闭 E06 身份错误并验证边车修复范围，保留严格只读路径的未覆盖状态；PLC 工程身份丢失问题须在 V05、V08 与 M2 部署前修复并验收。挂起模型须在相关功能设计前裁决。

## 1. 范围、基线与只读边界

本次按 `GPT_AUDIT_PROMPT_TONIGHT.md` 执行：全审 V01D、V02、M2-GOV-TD1、V03；抽查 V01/V01B/V01C，以及 U07D/U09C。第 1 期、真实模型接手演练及 V04 后续实施不在审计范围。较早 `AUDIT_BRIEF_DRAFT.md` 的交接、Checkpoint 写入和另一报告路径未采用。

用户随后提供 `AUDIT_ADDENDUM_V04_DEFECTS.md`，本报告在同日增加 F11/F12 与定点复现。补充中的 `4e165cf4` 只用于源码同源比较；卡052、proto 与演练归档只用于核验缺陷线索和候选字节，不扩展成第1期或 V04 的整期审计、批准或验收。原 F01～F10 与已完成的16个端到端复跑结果保留。

路径约定：

- `R = C:\Users\fubai\Documents\My_Workspace`
- `P = 01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`
- `E = .auto-pm/reports`
- 源码行号按被审提交或 `R/.auto-pm/worktrees/m2-v03/P` 标注；实施卡、治理记录与审计工具直接读取控制根。

| 对象 | 实测结果 |
|---|---|
| 控制根 | `a84fd7ee623c3014eef075413693e6f090d10143`，`codex/c09-recovery-governance` |
| 测试工作树 | `R/.auto-pm/worktrees/m2-v03`，`codex/m2-v03-handoff-e2e`，`edeeead98f0fb730330794aa9070117cae13aad5` |
| WBS 固定版本 | `57e14c194fdcc9c69fa601223240d68589472747:SYS-2026-001_WorkspaceGovernance/01_项目文档/39_PM-Flow_恢复与可用化总方案_WBS_PM.md` |
| WBS 原始 blob SHA-256 | `e5be410f35b2b883c036474173e66c09d5b3beb6bf19a3c4dae4582474202bf5`，与委托一致 |
| 当前入口运行时 | `main.py pm resume SW-2026-008 --json` 返回 configured/effective release 均为 `1.3.3-a808fa8`，无 fallback；Mission/Work/Run/Checkpoint/lease 均 null，conflicts 为空 |
| 控制根现场 | 审计期间两次采样均 462 条 `git status --short`；输出摘要均 `cac8961a18beb82baa52bd5ed9fdf32dbec489df575d5721c1004cdd7720b1ef` |
| 测试树状态 | 每次标准复跑前后均为空，输出 SHA-256 均 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

读取了根 AGENTS.md、共存/全局规则、实施卡、指定 WBS、HANDOFF 的近期及末尾记录。审计依据均为本轮文件、提交和实际复跑证据。未读取退役技能内容；未运行任何治理写命令，未登记债务、修改数据库、清理控制根、注册工作树、暂存、提交、合并、推送或部署。SQLite 核验采用 `mode=ro`、`PRAGMA query_only=ON` 与短只读事务，未输出租约秘密。

唯一持久写入为本报告。变异与负向试验使用工作树外独立 TemporaryDirectory，按委托明确允许的方式修改临时副本；所有临时副本已清除。

## 2. 交付与偏离判断

| 任务 | 事实与 WBS 对照 | 判断及偏离处置 |
|---|---|---|
| V01D，卡047，`fb94afa9` | WBS 第699行要求 PLC 差异/待确认拦提交，其他关口兜底。提交恰6路径；常规路径有真实 Git、暂存内容、自动补全和阶段门断言。卡第229、239～243行披露部署后生效、纯删除不触发、交付工具不存在、缺整份文档只警告。 | 常规交付成立；运行时部署延后与阶段门承担交付检查可作为受限开发交付接受。但工程标记删除会同时关闭两门，不能认定完整防线成立，见 F01。 |
| V02，卡048，`cf6f6f33` | WBS 第700行要求新目标→真实 SCL 变化→静态检查→验收落账。测试第74～83行核对固定提交/树 SHA 并 git archive，第134～144行读取实际基准后加入蜂鸣器变化，第217～245行执行真实产品链。仅执行者是脚本子进程。 | 符合静态闭环范围；脚本替身替换外部执行者，并未 Mock 业务状态或质量结果。硬件与真实 AI 执行未证明，卡已披露，无需回退此范围。全文件复跑结果见末页。 |
| M2-GOV-TD1，卡049，`b6668dcf` | 卡第4行说明 WBS 没有独立任务行，另行授权治理回写。提交仅1个台账路径；导入54条，保留001～008问题格，在复核表说明当前事实；独立 checker 17项通过。 | 内容保护和结构交付成立。文档任务不重跑产品全套门禁合理；来源指针语义并非结构 checker 的证明能力，见 F09。WBS 登记留待受控总回写。 |
| V03，卡050，`edeeead9` | WBS 第701行要求同 Work 接手、旧 owner 被拒、无需用户搬 JSON/token。卡第27～28、177、184行明确只证明底层机制，PM 入口不存在，人仍须搬口令。提交仅新增测试与台账7行，无产品改动。 | 已批准卡的机制验收成立；原 WBS 用户操作目标部分未覆盖，见 F02。无产品/既有测试变化时精简九组回归可以接受，须保持指纹证明与明确基线例外，不能称全库全绿。 |

V02 的额外 fixture-health 失败已有偏差记录 `E/m2-v02/deviation_fixture_health.txt:4–21`：新增 marker 存在断言后，正式门禁窗口全部重跑，产品文件指纹不变。当前卡摘要仍匹配批准回执。修正增加真实断言、未扩路径，可接受；首轮完整源码副本未找到，无法逐字证明恰好只改记录中的两处。

抽查 V01B/V01C 的回执和指纹一致，V01C 基准树实测为 `ae8ff3a787936702a6d5df5ce3aadaecc3cb4eed`。其记录包含14个基线失败、12个跳过，不能表述为全套零失败。

## 3. 发现：事实、判断、建议

### F01：删除 PLC 工程标记后，两道一致性门同时消失

| 事实 | 判断 | 建议 |
|---|---|---|
| `fb94afa9:P/auto_pm/infrastructure/plc_doc_hook.py:49` 仅从当前 index 枚举 .plc.json；第129～131行无匹配项目直接返回0。`stage_gate_engine.py:282–283` 缺标记即不生成 PLC 检查项。外部真实临时仓库中先把 IFC 的 i_bStart 类型 BOOL 改为 INT：PLC 钩子 exit1，完整阶段门 can_proceed=False；再 git rm 同工程 .plc.json，保留错误 IFC 暂存：钩子 exit0，阶段门 can_proceed=True，PLC item 消失。直接分析仍报告类型差异；直接 PlcChecker 仍报告缺 .plc.json 和文档类型错误。 | **重要；应作为 M2 部署、V05/V08 验收前的阻断项。** 问题在工程身份路由，检查器本体仍能发现。TD046 的“纯删除不触发”不能覆盖这次“删除配置并修改文档、阶段门也失效”。未动态证明 V01 验收门绕过；其第1140～1147、1440～1448行同样依赖当前标记，仅能确认同源风险。 | V04 前登记和裁决；在 V05、V08、部署前完成修复。以 HEAD/受管工程身份识别标记丢失，失败关闭；合法退役使用明确授权路径。将反例下沉到路由、Checker 和模板完整性门禁，不能只补提示词。 |

本实验直接调用 PLC 钩子模块，未运行真实仓库提交或完整台账包装器；阶段门完整运行。临时测试工程无 CHG，既有 CHG 门通过。直接 Checker 的其他目录/PRD缺件不用于证明本发现。

最小复现：archive fb94afa9 的 P；用 `tests.plc.test_doc_consistency.build` 建临时一致工程并提交基线；只暂存错误 IFC，调用两门；删除并暂存 .plc.json，重复相同调用。前后唯一区别为工程标记删除。

### F02：V03 机制验收与原 WBS 完成边界不同

| 事实 | 判断 | 建议 |
|---|---|---|
| 固定 WBS 第701行写“无需用户搬 JSON/token”；卡050明确写目前产品做不到，缺口已登记 TD063～065。测试的 hand_off 由测试进程调用服务层发起；“第二 Agent”是执行真实 continuity 命令的子进程，没有实际第二模型读取交接并续做。 | **重要：范围部分完成。** 卡诚实披露并可接受为底层机制验收；不能用8个通过或本次审计替代用户操作目标。 | V04 前注明其依赖仅使用已证明的底层能力。M2 WBS 回写应分清“机制已验收”和“PM 用户流程待交付”；保留原验收目标，不把搬口令的手工演练当成原条件已满足。 |

### F03：收口脚本允许空判卷集合和错误任务身份通过校验

| 事实 | 判断 | 建议 |
|---|---|---|
| 四个 `E/v01d_2_close_commit.sh`、`v02_2_close_commit.sh`、`td1_2_close_commit.sh`、`v03_2_close_commit.sh:35–45` 只拒绝已出现的 FAIL 项并遍历已有 report 摘要，未要求门禁完整集合或核对 card/base/run。只抽取该只读 Python 校验段，在临时文件输入 WRONG-CARD/WRONG-BASE/WRONG-RUN，gates={}、reports={}、exceptions=[]：exit0，输出 `verdict OK {}`。没有执行收口动作。 | **重要：空壳证据的防御缺口已复现。** 当前四份判卷实际完整，45个报告摘要均匹配，因此不能据此称既有验收伪造或实际放行失败。 | **V04 前**锁定预期 G1～G9/G1～G6、schema、card/base/run及必要报告集合，零项/少项/错误身份必须非零退出；纳入 V06 坏证据反例。判卷脚本自身有 FAIL 时也应非零退出。 |

补充实测：TD1 的判卷临时副本中将 doc_check.exit 改为1，JSON G5=FAIL，但脚本仍 exit0。现有收口脚本会拒绝这个已有 FAIL，故“失败退出码”属于工具合同风险；真正缺口是遗漏项与错误身份未校验。

### F04：V03 幂等重放测试漏检租约版本改变

| 事实 | 判断 | 建议 |
|---|---|---|
| q05 第183～190行只比较 handoff、owner 与事件数量。在 edeeead9 的临时副本中，基线1 passed；仅在 `continuity_store.py:5812` 的 transfer_lease 重放返回前增加租约 version+1，原 q05 仍1 passed。真实服务额外核验得到 version 2→3，事件数不变。当前产品没有该错误 SQL。 | **重要：非等价变异存活，属于测试覆盖缺口。** “重放不改变任何东西”尚无完整防回归证明，尤其涉及 V04 的 version/epoch 围栏。 | **V04 前**比较重放前后 lease 完整值、Run/Work 与事件快照，加入本反例。无需把正确产品逻辑改坏，也不能把此次存活说成产品当前存在该 bug。 |

### F05：挂起后新建 Mission 与现行唯一索引冲突

| 事实 | 判断 | 建议 |
|---|---|---|
| 固定源码 `continuity_store.py:316–318` 与控制库只读查询一致：唯一索引排除 ACCEPTED/CLOSED/CANCELLED，BLOCKED仍占项目唯一名额。需求草案 `E/m2-req-pm-entry/REQ_DRAFT_入口分类_分诊队列_换Agent_薄入口_需求草案.md:42` 使用 BLOCKED+PARKED 挂起后让 urgent 成为新焦点。ACCEPTED即使未CLOSED已释放索引名额，因此“至多一个未收口”不能按字面等同当前索引语义。 | **重要：未来接口设计冲突。** 当前快照无活动 Mission，不是已经发生的数据冲突；TD066尚未点名索引障碍。 | 在挂起功能设计前明确焦点、挂起对象和迁移/旧运行时兼容，V05 前固定相关接口。不要简单从索引排除所有 BLOCKED，否则真实故障阻塞也失去并发保护。区分“未验收”与“未收尾”。 |

### F06：V01 最终卡字节的批准顺序缺乏可独立核验的授权证据

| 事实 | 判断 | 建议 |
|---|---|---|
| `E/m2-v01/approval_receipt.txt:15、18` 明写批准先于最终字节，之后填 §1.6，最终 SHA 批准后才报告；卡042第216～217行要求漂移使批准失效，并绑定完整字节。Decision V01PLCQG第17～21行未见允许事后填事实段的明确条件；当前卡摘要确与回执一致。 | **重要：授权绑定 UNVERIFIED。** Agent 自记顺序不是人类预授权原文。本次无法核验原聊天，不能直接认定未经授权，也不能把事后 SHA 等同原批准覆盖最终字节。 | V04 前补原授权证据，或由用户对最终卡 SHA 明确追认并留独立记录；保留原顺序与历史，不倒写“批准在最终字节后”。 |

### F07：变异“任意非零即杀死”会混入环境或收集失败

| 事实 | 判断 | 建议 |
|---|---|---|
| V01D mutation_check.py第163行、V02同脚本第48行把任何非零算 killed；记录仅保留 stdout末行。TD1 negative_controls.py同样只看非零。本次未变异的测试因 Git ignore 不可读就 exit1；这是非目标行为失败。独立抽样经绿色基线后确实命中目标断言/检查项。V03 G8还核对q02/q06失败节点及其他通过数，防御更强。 | **一般：负向证据分类不够严格。** 本次实际抽样成立；不据此认定现有变异记录造假。 | 后续工具批次统一基线绿、目标 nodeid、Exit1、目标断言/拒绝原因、stdout/stderr；排除 setup/import、无测试及环境故障。V04 新负向门应直接使用该标准。 |

### F08：V03 批准回执的通用措辞与真实顺序说明不一致

| 事实 | 判断 | 建议 |
|---|---|---|
| approval_receipt第15、19行说“批准发生在最终字节及SHA报告之后”；第22行明确先批准初版3行台账，后修为7行、报告新SHA、用户再回复“确认”。CHG第176、185行同样保留修订后确认。acceptance_receipt第8行仍为implementing；当前CHG第63行已completed。 | **一般：记录一致性与时点标注问题。** 最终确认的具体记录充分披露；旧验收回执属于技术收口时快照，不能当作当前CHG状态。原人类回复仍无法独立核验。 | 下次受控证据回写保留历史并明确首次批准、修订、最终确认三个时点；将技术回执与最终人类验收/CHG收口回执分清。 |

### F09：台账两处事实指针需要纠正

| 事实 | 判断 | 建议 |
|---|---|---|
| b6668dcf台账第42行称“WBS⑱记录U07D口令只在内存”。固定WBS第567行的⑱实际是schema_meta双版本，口令限制属于同段“不另编号”的已知限制。台账第104行TD062称gitignore使“提交钩子与阶段门永远看不到”工程；阶段门直接读取工作区及.plc.json，不要求Git跟踪。 | **一般：编号误引和过度措辞。** 原口令风险存在；被忽略工程是否能被项目入口发现尚未核验，不能把发现入口限制归因于阶段门本体。结构checker不能证明来源语义准确。 | 下次台账修订改指WBS §4.7.4已知限制，并区分Git提交可见性、项目发现与阶段检查。保留未修复状态，补语义核对。 |

### F10：U 系列抽样的真实异步边界与历史工具例外尚须补证

| 事实 | 判断 | 建议 |
|---|---|---|
| U07D start_e2e第72～121行使用真实存储/产品链与子进程，但线程池手动worker.run；U09C approval_view第28～37、224～265行用InlinePool。卡040披露了调度替身。另 `E/m2-u09c-run004/DEVIATIONS_RUN004.md:20、23` 明述三项工具修正超出冻结卡允许清单，以及non-qml末尾检查两次报git failed、attempt=FAIL、最终判卷以逐回执核验为准。 | **一般；例外授权无法核验。** 调度/执行者替身不是业务结果Mock，但不能单独证明生产跨线程和关闭生命周期。偏差有诚实披露，不能称执行合同毫无偏离；也不能仅据attempt失败否定最终逐回执技术证据。 | V05用生产线程池与构造路径联验。M2总审计补工具例外裁决、解释attempt FAIL与最终PASS的证据关系，保留失败历史。本次未复跑U09C全套。 |

### F11：E06 用裸执行者比较带适配器前缀的 Run 身份，真实恢复必被拒绝

| 事实 | 判断 | 建议 |
|---|---|---|
| `edeeead9:P/auto_pm/application/core/continuity_execution_service.py:776` 比较 `run.executor_id != receipt.executor_id`。真实派发 `execution_adapter_service.py:175、266～269、407～411` 将 `adapter:executor` 的 owner_id 写入 Run；合同 `contracts/execution_adapter.py:184～190、224～227` 强制裸 executor 不含冒号、owner 为适配器加裸 executor。独立临时真实派发得到 Run=`codex:agent-a`、receipt.executor=`agent-a`、receipt.owner=`codex:agent-a`；真实子进程存活、Run RUNNING、启动证据齐全，resolver 仍报“ExecutionIntent 与活动 Run 身份不一致”，supervisor 报“运行身份不可恢复，必须 BLOCKED/待恢复”。 | **重要；V04 恢复验收前必须关闭。** 这是原被审代码的产品缺陷，不是第1期新增。原 V03 的 handoff 用例通过不证明 E06 主控重启对账；本报告首段“机制成立”仅限已测的交接路径。 | 正确比较回执 owner_id；保留真实派发、真实 Store、真实活进程证据的回归，以及错误 owner、裸 Run executor、错误 PID/session/启动时刻的拒绝。按受批实施卡执行修复和门禁，不能以临时对照代替提交或验收。 |

旧 `tests/core/test_continuity_execution_service.py:3959～3967` 用 SimpleNamespace/Mock 将三个身份都设为裸 `agent-a`，不符合真实回执合同；`tests/core/test_execution_supervisor_service.py:462～464` 直接 Mock resolver 成功。原版两个用例独立复跑仍 **2 passed，1.58秒，Exit0**，说明这组绿灯确实漏掉组合缺陷，不是仅凭补充文字推断。未发现这两测试通过真实派发证明身份契约。

最小复现：archive edeeead9 的 P 至外部临时目录，复用现有派发夹具，经真实 `ExecutionDispatchService.prepare` 建 intent/receipt/Run；启动本人 Python 子进程，记录其真实 PID、session 与启动时刻，再调用 resolver/supervisor。仅在临时副本把比较改为 `receipt.owner_id`，以新的独立场景重复，两服务均返回原始启动证据，绿色对照 Exit0。进程与临时副本已清理。没有完整演练“杀主控后新进程重启”，没有因此认定 V04 r02 已验收。

### F12：WAL 边车校验缺少瞬态重试，严格只读路径仍存在同类遗漏

| 事实 | 判断 | 建议 |
|---|---|---|
| `edeeead9:P/auto_pm/infrastructure/continuity_store.py:448～475` 分步校验 DB/边车路径，再 stat；FileNotFound 可跳过，但 guard 异常或链接数/文件类型异常立即拒绝，没有瞬态重试。归档 `E/m2-v04/gates_rehearsal/judge_dry/g2_candidate/rest.txt:815～830` 记录4个并发入箱进程中一个 exit1，错误为 `continuity.db-shm` 不是唯一链接普通文件。独立临时基线正常校验通过；只对首次 WAL guard 注入瞬态异常，原代码第一次即拒绝、尝试数1，手动下一次调用通过。 | **重要：核心存储并发可用性与测试覆盖缺口。** 归档证明并发失败曾发生；代码与确定性对照证明瞬态错误不会自动恢复。具体“半建/待删除”是对根因的解释，未取得该时刻 mode/nlink/解析路径探针，不能写成独立观测。该试验没有复现操作系统竞态，也没有证明数据损坏。 | V04 验收验证有限重试只覆盖边车、DB 异常不重试、持续危险路径仍拒绝；保留失败原始输出。M2 多 Agent 并发使用/部署前单独验证严格只读路径，不能从写事务测试通过外推读取稳定，也不能只靠重复到绿。 |

严格只读的 `_file_inventory:962～983` 仅把打开文件时的 FileNotFound 转为 `_ReadSnapshotDriftError`；stat 的其他错误及非唯一普通文件直接拒绝。`_stable_read_snapshot:1152～1157` 只重试该 drift，普通存储异常直接抛出。对应方法在基线与 proto 中未改，拟债 TD077 的未覆盖范围有源码依据。

临时副本拷入候选 Store 与候选 sidecar 测试，独立组件对照 **5 passed，4.35秒，Exit0**；这是环境故障注入下的有限重试/持续拒绝验证，不是 OS 竞态压力试验或安全边界的完整验收。候选固定6次尝试、最多5次25ms等待，即固定等待125ms加校验耗时；卡内“约150ms”不应作为精确时限。

**无法核验的数字：**指定证据目录未找到“原版12轮失败1轮、修复后24轮通过”的逐轮原始日志。卡052与补充材料的这组计数属于自述；本次未独立复跑该36轮，不将其当成已证实的稳定率，也不据此称第1期原批准门禁“侥幸通过”已经得到证明。

## 4. 证据链核验结果

四个真实 Checkpoint 分别为：

- CKPT-SW008-M2-V01D-001
- CKPT-SW008-M2-V02-001
- CKPT-SW008-M2-GOV-TD1-001
- CKPT-SW008-M2-V03-001

其 git_head 均为对应产品提交的父提交，dirty_paths 与该次提交精确改动集合分别6、2、1、2一致。全部 **11个** `sha256:<path>:<hash>` 与 `git show <commit>:<path>` 原始字节一致；Checkpoint 所绑定的4份判卷摘要一致，判卷引用的 **45个报告** 摘要一致。四张卡当前字节均与批准回执一致，审计末再次核对仍一致。

| 任务 | 当前卡 SHA-256 | Checkpoint绑定判卷 SHA-256 |
|---|---|---|
| V01D | `241d98a3700af12ad20e0e4e0e25b554b149a14f30974e48f53c5df961f2dcb0` | `1cd9ff3980de48c5b6c37e73d989c5af53e1b89900244b2a768bb7dee05c35a4` |
| V02 | `67ab5cfa24b6dae6609adb57e2ffa08fecbcab5522dddfc114d9e73020f537ca` | `154abeac27c69fd2639a69af23ef49f3af597c7d678e2ceb27e7bb47946cf3d8` |
| TD1 | `4659e65deb94edb696734e0bcd9e9207a0d38e2762bcdf790920cf79872d9708` | `d64b0f0ad13fc1ab4c12ced1b2dc74076853400195e1a40677522f78906e6413` |
| V03 | `fbd566e422095a2054a3f5f6738199ff27311135e69b714e2be9c1711336a1f5` | `354541dd1a9508ed2603b6c905a53d5e794fcfa0e1d321095948854ba70b1a72` |

明确的 blob 复验例：

```text
git show edeeead9:<P>/tests/e2e/test_pmf_handoff.py
SHA256 = 651c7e927ca05cdc02e033ee7ed0bbfb6326f8d0738ff363540692d8147c8dc7

git show b6668dcf:<P>/04_监控/02_整改项/活动技术债台账.md
SHA256 = 988fca2efab6ed99c722f8dedfd660c9de081c4114cabd4edb22a8fe3e4d261b
```

四个 Run 当前 SUCCEEDED、Work CLOSED、lease均为RELEASED；四个对应CHG第63行均completed。事件中Checkpoints先于终态转换；未重写历史。字节一致能证明交付与证据绑定，不能独立证明人类授权的原话和时点，也不是全局事件哈希链完整重算。

判卷 Python 脚本读取已有源文件、输出和Git事实，写报告/判卷文件；抽查未见判卷前重新生成/安装产品或写治理库。应称“源码与治理只读、允许写证据输出”，不应称脚本完全无写入。本次未在真实证据目录重跑判卷。

## 5. V04～V08 的处置顺序

| 时点 | 建议 |
|---|---|
| V04前及验收前 | F03完整判卷合同、F04重放版本覆盖、F06授权字节证据；明确F02的机制/用户流程边界；登记F01。V04验收前关闭F11，并验证F12候选的边车重试与持续拒绝；严格只读遗漏保持未偿还。 |
| 挂起功能设计前 | 解决F05的Mission状态、焦点与迁移模型；不要把BLOCKED直接当作可释放的挂起。 |
| V05/V08及M2部署前 | 关闭F01并验收；V05覆盖真实异步GUI路径；V08固定已治愈基准并机械提模板，不把失败路由复制到模板。 |
| V06 | 加入空判卷、错身份、丢门项、PLC身份丢失、变异环境误杀等负向场景。 |
| M2总审计/台账回写 | 更新任务与未覆盖边界、F08/F09指针、U09C工具例外证据；保留旧失败与旧回执时点。 |

除已列明风险外，本次未发现证据支持“用Mock业务结果骗绿”。未发现不等于全面排除；U系列仅抽查，不能外推全部U01～U09重新验收。

## 6. 补充证据与候选状态

两处核心源文件在 edeeead9 与 `4e165cf4a6c36925e8c29cfdc4c392203c87096c` 的原始字节完全相同：

| 文件 | 两提交共同 SHA-256 |
|---|---|
| `P/auto_pm/application/core/continuity_execution_service.py` | `aad2edee1cb836d35d5a1f6001200ecc8475a1938fc758629b8823d22f2d31d8` |
| `P/auto_pm/infrastructure/continuity_store.py` | `c2207de343b1b8b5241a19fa5adddf3dc6c8640b81651683b66cb4cd73feb689` |

dispatch、supervisor、回执合同和上述两个旧测试的完整文件也分别字节相同。因此补充追溯原被审依赖具有依据；不需要把第1期改为本轮全审对象。

- 补充文件 SHA-256：`df4b70434c9da29a8a9293ff5f74a0249668dd6bb4db51b4d5f371a9c8340994`。
- 卡052实测 SHA-256：`5c1ac210680ce8a169779df6e223211e064cd01bfa895f0e866cdf419ade5ef8`，与补充一致；第188～189行仍标实施批准/最终验收 PENDING。
- `reference_manifest.json` 的6个 proto 文件和13个工具/参考文件，**19/19**摘要匹配；`gates_rehearsal2/gate_verdict.json` 所引用的 **15/15** 报告摘要匹配；`bytes_at_gates.txt` 与 `bytes_after_gates.txt` 字节相同。
- 归档 G9 为进程测试8 passed/294.63秒、sidecar测试5 passed/7.03秒、两个Exit0。该8个进程场景本次未复跑；判卷中的拟用 Run ID 与 PASS 标签不作为真实授权、Checkpoint或用户验收证明，也不等同全库零失败。
- TD074～077仍仅按候选追加行处理；本审计没有正式登记债务。proto和台账中“V04已修复”应按候选目标理解，不能描述为已提交、已部署或已验收。

本次补充核验未改任何实际产品或治理文件，只更新本报告；最小复现的独立临时副本与本人子进程均已清理。控制根 HEAD、462条Git状态摘要和 V03 工作树的空状态摘要与原审计一致。两处缺陷的修复批准及交付闭环由后续受控流程处理。

---

## 附页：我复跑了什么、结果如何、哪些没有核验

标准测试 cwd 为 `R/.auto-pm/worktrees/m2-v03/P`，使用根 .venv Python与该树PYTHONPATH：

```text
python -B -m pytest tests/e2e/test_pmf_handoff.py -q --tb=short -o addopts= --no-cov -p no:cacheprovider --basetemp <独立临时目录>
python -B -m pytest tests/e2e/test_pmf_plc.py     -q --tb=short -o addopts= --no-cov -p no:cacheprovider --basetemp <独立临时目录>
```

环境固定 PYTHONDONTWRITEBYTECODE=1、UTF-8、QT_QPA_PLATFORM=offscreen；每次前后 git status --short 相同。

| 实际复跑 | 结果 |
|---|---|
| V03完整文件 | **8 passed，Exit0**，313.01秒（进程总314.75秒），0跳过。 |
| V02完整文件 | **8 passed，Exit0**，537.98秒（进程总539.44秒），0跳过。 |
| V01D M02：暂存判断改为工作区判断，点名h03 | 基线1 passed/Exit0；变异1 failed/Exit1，命中test_plc_doc_hook.py:86。 |
| V02 M01：恢复未排序元组比较，点名p05 | 基线1 passed/Exit0；变异1 failed/Exit1，命中test_pmf_plc.py:300，原因“Checkpoint与最新Run声明差异不一致”。 |
| TD1：只损坏001旧问题文本 | checker基线17项通过/Exit0；负向Exit1，明确G4 unexpected=[TD-SW008-001]。 |
| V03原负向：关闭租约归属检查，点名q02/q06 | 基线2 passed/Exit0；变异2 failed/Exit1，命中第152、202行，旧owner实际写入成功导致断言红。 |
| V03新增非等价变异：重放递增租约版本，点名q05 | 基线1 passed；变异仍1 passed；另证实version 2→3且事件数不变，见F04。 |
| PLC工程标记删除 | 文档错误原被两门拒绝，删除标记后两门通过；直接检查器仍报告问题，见F01。 |
| 判卷校验空集合/错身份 | 临时JSON由实际只读校验段接受，Exit0；TD1临时判卷有G5 FAIL仍Exit0，见F03。 |
| 提交与Checkpoint指纹 | 11/11产品blob、4/4判卷、45/45引用报告、4/4卡摘要一致。 |
| 补充：E06两个旧单测 | 原版2 passed/1.58秒/Exit0；手造身份及Mock resolver漏检真实派发差异，见F11。 |
| 补充：E06真实派发与活进程 | 原产品resolver/supervisor均拒绝正确身份；临时一行owner比较对照两服务均成功。未演练杀主控/跨进程重启。 |
| 补充：WAL瞬态故障注入 | 正常基线通过；原版首次边车guard异常即拒绝，只有一次尝试；手动第二次调用通过。没有OS竞态复现。 |
| 补充：候选sidecar五用例 | 独立临时副本5 passed/4.35秒/Exit0；候选组件证据，不是完整V04验收。 |
| 补充：候选归档指纹 | 19/19 manifest文件、15/15判卷引用报告匹配；门禁前后6个文件字节记录相同。 |

环境失败也如实保留：首次默认 Git 环境下V03为8 setup errors、V02为8 failed，原因读取 `C:/Users/fubai/.config/git/ignore` 被权限拒绝；只给测试进程设置临时XDG_CONFIG_HOME后，V03通过，V02仍因长临时路径使Git报Filename too long而8 failed。最终PLC使用短临时目录及其中XDG/git/config的core.longpaths=true；没有修改用户Home、真实全局/仓库Git配置或产品代码。上述环境失败没有被当作杀死变异或产品业务失败。

**没有核验：** 九组完整回归、全套Ruff/Mypy/doc门禁的独立复跑；原聊天中的人类批准/验收原文；V01/B/C所有变异；U系列完整门禁和当前生产线程生命周期；真实模型接手、无需人搬token；PLC编译/下发/硬件行为；M2部署及当前运行时新增Hook生效；真实工业工程的破坏性反例；全局事件链完整复算；首轮V02源码与最终版本的逐字差异。这些事项不能从归档数字、通过样本或CHG终态外推。

**补充未核验：**第1期整体验收；V04完整真实进程演练及九组门禁的独立复跑；原版12轮/修复后24轮的逐轮计数；边车失败时操作系统实际返回的mode/nlink/解析路径；严格只读并发压力；候选修复后的全量安全边界；全部适配器现场执行及生产恢复入口。不得把本次定点核验或候选5个组件绿灯当成上述事项已经完成。
