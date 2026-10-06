# P1＋V04 独立只读审计报告

日期：2026-10-05；主控制根：`C:\Users\fubai\Documents\My_Workspace`。

## 1. 裁决与边界

**独立质量审计结论：FAIL，不能给出 P1＋V04 整体无阻断通过。**

- P1 的转计划原子性缺陷已通过真实 CLI 在一次性隔离测试库复现，属于本轮阻断项；另复现两项分类/取证缺陷。
- V04 的 F11 身份比较与 F12 有界边车重试修复通过本轮定向复验；没有证据表明它们需要回退。发现两项测试证明缺口及两项收口/变异工具缺陷。
- 两条历史治理收口记录成立，Checkpoint 与最终提交字节一致；**不回滚或改写已 CLOSED/SUCCEEDED 的记录，不将新审计发现定性为历史伪造**。
- 按用户批准计划中的条件分支，存在阻断，因此本轮**不准备或实施 TD2 卡**，不新建 CHG/Decision/Work/Run。下一步应先对以下精确缺口出修复范围，而不是重开 C09 或重做整个 M2。

审计开始 UTC `2026-10-05T21:07:03Z`，硬上限 `22:37:03Z`。本轮没有执行九组重负载回归，也没有边审边改产品。注册的 fullstack-engineer/公共协同契约用于只读 Grooming、执行隔离与证据核验；两个只读子审计均已结束。实际产品负例由主审计在新建 TEMP 根复现，不在 canonical 中构造测试记录。

允许的持久写入仅为本报告及环境复验报告追加段。测试夹具/诊断/缓存在专用 TEMP 路径生成，收尾清理；既有候选、控制库、WBS、规范、release 及历史报告均未修改。没有合并、推送、部署、release 切换或使用退役 pm-workflow。

## 2. 固定身份与治理证据

文中 `P` 指项目根：`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`。候选代码链接均指固定提交对应的现有隔离工作树，而不是主工作区未提交研发代码。

| 对象 | P1 | V04 |
|---|---|---|
| 候选 | `.auto-pm/worktrees/m2-p1` | `.auto-pm/worktrees/m2-v04` |
| HEAD | `4e165cf4a6c36925e8c29cfdc4c392203c87096c` | `a6447be68bc19fbcd12a346d18e010e5249f4d95` |
| 父提交 | `edeeead98f0fb730330794aa9070117cae13aad5` | P1 HEAD |
| 卡片 | `P/02_规划/051_P1_入口分类与分诊收件箱第一期实施卡_PM.md` | `P/02_规划/052_V04_进程中断与租约到期恢复实演实施卡_PM.md` |
| 卡 SHA-256 | `1e6fe9796da5b30cd663112bb26a9688a39bb8fd197e406b687518a2dcf1bfe3` | `131edf48c03a62e9ff21a41b4e183e6a88c86023dc543deb6b95842b5d36d495` |
| CHG | `CHG-SCPT-2026-379` completed | `CHG-SCPT-2026-380` completed |
| Decision | `DEC-20261005-P1INTAKE` approved，精确 14 路径 | `DEC-20261005-V04RECVY` approved，精确 6 路径 |
| Work | `WORK-SW008-M2-P1-001` CLOSED，v6 | `WORK-SW008-M2-V04-001` CLOSED，v6 |
| Run | `RUN-SW008-M2-P1-001` SUCCEEDED，v4 | `RUN-SW008-M2-V04-001` SUCCEEDED，v4 |
| lease | RELEASED，v7 | RELEASED，v8 |
| Checkpoint | `CKPT-SW008-M2-P1-001`，sequence 1，07:04:46.375987Z | `CKPT-SW008-M2-V04-001`，sequence 1，20:21:14.547828Z |
| CP 基线 | `edeeead9`＋14 脏路径 | `4e165cf4`＋6 脏路径 |
| CP 与最终提交逐文件 SHA 比对 | 14/14 相同 | 6/6 相同 |
| 判卷 SHA | `4f51eb8c86109b7bbca88479b77b0b910cafef267ba94763d6d2614319056ec0` | `70da2c04b92c81c16eb83e6b610cade6af9fbf9642b8020ab6e73d69ca1f1d85` |
| 判卷引用报告哈希 | 14/14 相同 | 15/15 相同 |
| reference manifest 哈希 | 27/27 相同 | 19/19 相同 |

两张 Decision 的 `approved_files` 集合、Work scope、Checkpoint dirty 集合与最终提交改动集合一致。CP evidence 确实绑定上表判卷 SHA。**提交前基线＋脏文件是有效证据方式，不因 CP git_head 与最终 HEAD 不同而误判漂移。**

canonical `.auto-pm/continuity.db` 用只读 URI 查询；本轮校验时 WAL 为 0 字节，哈希链核验使用 `mode=ro&immutable=1`，不创建/更新 SQLite 边车。3121 条事件按存储层哈希材料重算，0 断裂，链头为 `d7f6cbe545517693be9c8eab6e36362a0de523fa0d49edba4b0dba5d28614654`。两链均有 WORK_CREATED、RUN_CREATED、CHECKPOINT_CREATED 及合法终态事件。

库文件 SHA 在采样前/后均为 `e63c758f4b0e9d84e22df5abd50dcc68c1d1cb23f4956ed127ca00afd0a3bc0f`。根入口复验 resume 无活动 Mission/Work/Run/lease、无候选/冲突；SW008 reconcile 为 0 缺失／0 孤儿／0 不一致，Exit 0。CHG-161～164 的历史格式警告如实保留，不在本轮修复。

当前 root HEAD `a84fd7ee623c3014eef075413693e6f090d10143`；configured/effective runtime 均 `1.3.3-a808fa8`，fallback 为空，previous 为 `1.3.3-0b72499`。该稳定入口并未部署本轮 M2 候选。

### 批准与验收时间口径

两项目 `approval_receipt.txt`、`acceptance_receipt.txt`、`closure_receipt.txt` 均已读取。

- P1 明确记载用户的**有条件预授权早于最终卡 SHA**；未把它改称“最终 SHA 之后批准”。最终验收与 CHG 收口单独记录。
- V04 回执记载最终卡 SHA 报告之后的用户明确批准。技术验收回执中 CHG implementing 是早期快照；新的 closure_receipt 与当前 CHG completed 相容。
- 两份 closure_receipt 的 `RECORDED_AT=20:54:58Z` 明确是事后记录时间，非用户点击时间。接力摘要“待验收”属于陈旧文字，不据此重复执行收口。
- 文件/状态/哈希交叉一致性为 PASS；本轮没有独立取得 Claude 原始对话数据库或用户点击日志，不将文字回执夸大为加密身份鉴权。

## 3. 本轮实际复测与范围

固定解释器：`C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe`；`PYTHONDONTWRITEBYTECODE=1`、UTF-8；pytest 默认 addopts、coverage、cacheprovider/randomly 均按下列命令显式控制，未跳过所选测试。

| 核验项 | 结果 | 口径 |
|---|---|---|
| 环境临时候选 smoke/import | PASS：25 passed，5.18s，Exit 0 | 从 P1 固定 HEAD 临时 checkout；正常 Hook 与正常退役另见预检报告 |
| P1 合同＋服务＋端到端 | PASS：40 passed，147.33s，Exit 0 | 不等于 P1 所有业务合同成立；本轮负例另见 §4 |
| V04 sc01～sc08＋r01～r09＋身份回归 | PASS：18 passed，141 deselected，406.61s，Exit 0 | 有测试证明缺口，见 §4 A-V04-01/02 |
| V04 Ruff 五文件 | PASS：All checks passed，Exit 0 | 精确 owned Python 目标 |
| V04 Mypy strict 五文件 | PASS：Success: no issues found in 5 source files，Exit 0 | 正常 import；没有 follow-imports=skip；缓存定向 TEMP |
| P1/V04 G1/G2/G8/G9 引用原始日志哈希 | PASS：25＋26 笔绑定全部相同 | 包含重复引用，不声称 51 个唯一文件；没有重跑九组 |
| 完整九组回归的独立重跑 | UNVERIFIED（计划明确不重跑） | 只复核既存原始日志与 baseline 差异口径 |
| 实际换 Agent、新 owner 排他演练 | UNVERIFIED／未执行 | 必须新 TD2 授权链，不接管关闭的 V04 Run |

实际测试命令（cwd 分别为各候选的 `P`；`PY` 是上面的完整解释器）：

```powershell
# P1
& $PY -B -X utf8 -m pytest -o addopts= --no-cov -p no:cacheprovider -p no:randomly --basetemp C:/Users/fubai/AppData/Local/Temp/gpt_audit_p1_20261005 -q tests/contracts/test_intake_contract.py tests/core/test_pm_intake_service.py tests/e2e/test_pmf_intake.py
# V04
& $PY -B -X utf8 -m pytest -o addopts= --no-cov -p no:cacheprovider -p no:randomly --basetemp C:/Users/fubai/AppData/Local/Temp/gpt_audit_v04_20261005 -q tests/infrastructure/test_continuity_store_sidecars.py tests/e2e/test_pmf_recovery.py tests/core/test_continuity_execution_service.py -k 'sc0 or r0 or reconciles_operation_receipt'
# V04 精确五个 Python 路径
$targets = @(
    'auto_pm/application/core/continuity_execution_service.py',
    'auto_pm/infrastructure/continuity_store.py',
    'tests/core/test_continuity_execution_service.py',
    'tests/e2e/test_pmf_recovery.py',
    'tests/infrastructure/test_continuity_store_sidecars.py'
)
& $PY -B -X utf8 -m ruff check --no-cache @targets
& $PY -B -X utf8 -m mypy --strict --no-incremental --show-traceback --cache-dir C:/Users/fubai/AppData/Local/Temp/gpt_audit_mypy_20261005 @targets
```

首次 Mypy 使用 `--cache-dir=NUL` 触发 2.3.1 工具内部错误，Exit 1。只作一次改用专用 TEMP 缓存的诊断复测后成功；未修改源码、抑制类型错误、安装或升级工具。此调用环境差异不记为产品类型缺陷。两候选的既有 `.mypy_cache` 各 18 文件，UTC 时间戳均早于审计开始；未清理或覆盖它们。

G1 的既存夹具失败，以及 G2 的 core 3 个/rest 15 个既存失败在卡内按 baseline 差异验收。P1 G4 明确为 11 文件 strict 通过、两既有测试文件维持 5 项诊断。**这些是批准的差异门禁，不是全库 100% 绿。** 两份判卷 `exceptions=[]` 不能覆盖报告正文中的既存例外。未对全部既存诊断逐项重新执行、也未对所有来源基线重新跑测试。

## 4. 新发现（事实／影响／最小处置分列）

### A-P1-01【阻断／FAIL】失败计划仍消费确认条目

证据：[门面先绑定再生成范围卡](</C:/Users/fubai/Documents/My_Workspace/.auto-pm/worktrees/m2-p1/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/application/core/pm_facade_service.py:240>)；`_planning_classification` 第 149 行；[IntakeStore 第 322 行](</C:/Users/fubai/Documents/My_Workspace/.auto-pm/worktrees/m2-p1/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/infrastructure/intake_store.py:322>)。卡 051 第 159/165 行要求转计划原子完成。

真实 CLI、合法其余参数、确认后的条目，调用 `pm plan --inbox-id <id> ... --scope '*'`：

```text
Exit 1: Error: scope_paths must be explicit and must not contain wildcards
before=CONFIRMED; after=PLANNED
planning_draft_intake_bindings count=1; open inbox items=0
```

影响：计划没有成功返回范围卡，事项却从开放队列消失。并非证明不可恢复丢失，也没有扩大执行授权，但违背入口的失败原子性合同，阻断独立 P1 通过。

最小处置：将分类解析/验证与最终消费分离；全部可预检参数先验证，范围卡/CHG 成功形成后才在有冲突校验的事务中绑定并转 PLANNED。跨文件与数据库步骤应定义失败可恢复语义，不能靠失败后另造补偿记录掩盖。至少补非法 scope、后续创建失败、成功重放三类回归，断言失败时条目仍可见、无已消费事件/绑定；保留可合法恢复的 draft 不等于消费条目。

### A-P1-02【重要／FAIL】省略 kind 的重放忽略显式冲突

证据：[pm_intake_service.py 第 214～219 行](</C:/Users/fubai/Documents/My_Workspace/.auto-pm/worktrees/m2-p1/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/application/core/pm_intake_service.py:214>)；卡 051 第 164～165 行。

真实 CLI：先建 `CHANGE/FREEZE/SCPT/MODULE` 计划；同 request_id 重放，省略 kind/inbox_id，显式给 `--change-action remove --domain PLC`：Exit 0，返回同 plan_hash，持久分类仍为 FREEZE/SCPT。

影响：用户显式冲突意图被静默丢弃，而不是合同要求的拒绝。未发现执行授权扩大。最小修法：读取既有绑定后逐项比较所有本次显式提供的分类字段；完全省略时才允许合法重放。补 action/domain/impact_scope 各自冲突负例，含无 kind 分支。

### A-P1-03【重要／FAIL】目录能冒充 file 证据

证据：[pm_intake_service.py 第 255～266 行](</C:/Users/fubai/Documents/My_Workspace/.auto-pm/worktrees/m2-p1/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/application/core/pm_intake_service.py:255>)；卡 051 第 152 行。

真实 CLI 在新测试根创建目录 `evidence_is_a_directory`，仅以 `file:evidence_is_a_directory` 取证：`is_file=False`，Exit 0，新增 item=1、INTAKE_ITEM_RECORDED=1。

影响：exists 不是文件证据。此项不同于 TD072 已登记的“cmd/ledger/chg/commit 仅验格式”。最小修法：保留根内路径/越界校验，同时要求有效普通文件；目录、越界、失效链接均拒绝且不新增事项/事件，不为了求绿扩大到取证内容真实性全量实现。

以上三项用候选自带 `tests.cli.test_pm_inbox` 的 `_setup_planning/_add/_decide/_plan` 夹具与真实入口，在三套 `TemporaryDirectory` 中复现；没有 Mock 产品方法，没有向主库写入。V04 不改这些 P1 文件，因此问题仍存在于 V04 累积提交。

### A-GATE-01【重要／FAIL】收口校验未绑定逐门报告

证据：[v04_2_close_commit.sh 第 38～49 行](</C:/Users/fubai/Documents/My_Workspace/.auto-pm/reports/v04_2_close_commit.sh:38>)。

主审计仅提取其中无状态 Python 校验块，**没有执行 shell 的收口步骤**；对临时 JSON 做反例：

| 输入 | 实际结果 |
|---|---|
| 当前正确 verdict | 接受 |
| 错卡名 | 拒绝 |
| gates={} | 拒绝 |
| 九门仍 PASS，但 reports 只保留 G5 一个真实哈希 | **接受** |
| G1.report 改为不存在的 NO_SUCH_G1_REPORT.txt，reports 保持原样 | **接受** |

原因：校验 gates 的集合/值与 reports 中已有条目的哈希，但未要求每个 gates[g].report 必须属于 reports。现有 29 份真实报告仍全部可读且哈希匹配，**本反例不能据此宣布现有 CP 伪造**。

最小修法：从完整 gate 集合导出每门所需报告，逐项校验绑定、文件与哈希；缺失/错指向不得收口。增加上述两条纯负例；不要通过新一轮 Run 或历史记录变更替代工具修复。

### A-GATE-02【重要／FAIL；历史 G8 强断言证明 UNVERIFIED】变异异常被当成断言杀死

证据：[mutation_check.py 第 52～58 行](</C:/Users/fubai/Documents/My_Workspace/.auto-pm/reports/m2-v04/mutation_check.py:52>)；G8_report 与 mutation_check_output.json。

主审计 AST 提取纯函数，输入**构造的 CompletedProcess 测试结果**，不是声称执行了真实产品变异：同一匹配 FAILED 节点、Exit 1 的 AssertionError、RuntimeError、TypeError 均返回 True；setup ERROR 返回 False。只拒绝 ERROR 节点不能区分测试函数内的执行错误。

影响：当前归档保留 baseline_green、FAILED node 和末行摘要，未保留可证明异常类别的完整 traceback；无法独立确认 14 个变异全部满足“真实断言失败而非报错”。不据此否定全部变异有效，也不把未知写成断言通过。

最小修法：存储结构化每测试阶段结果与失败异常类别/traceback，明确允许的契约断言失败并排除工具/fixture/import/测试内非断言异常；基线绿、目标对应和字节还原仍须校验。先固定错误判卷反例，再在新受控验证范围复验关键变异，禁止改写旧 G8 结果。

P1 的旧 mutation_check 仍以任意非零返回码为 killed，且没有每组先绿检查；属于前轮 F07/待 TD2 收敛的已知工具债，未重复计作新增发现。

### A-V04-01【重要／FAIL（测试证明）】r03 拒绝原因不是过期

证据：[test_pmf_recovery.py 第 402～405 行](</C:/Users/fubai/Documents/My_Workspace/.auto-pm/worktrees/m2-v04/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/e2e/test_pmf_recovery.py:402>)；存储 renew_lease 第 5773～5776 行。

复测完成后的**本轮临时 r03 库**中，真实 lease owner 是 `codex:agent-a`。调用真实存储服务，参数其余相同：

```text
owner=agent-a       -> lease ownership 不匹配
owner=codex:agent-a -> lease 已过期
lease_unchanged=True
```

影响：原测试的非零退出可由错误 owner 满足，不能证明续租到期防线；实际正确 owner 的过期拒绝本轮已验证。最小修法：测试用 lease.owner_id、断言拒绝类别/原因与 lease/事件不变，增加到期判断移除时必须失败的变异。不是要求重做产品恢复设计。

### A-V04-02【重要／FAIL（测试 helper）】查询失败被当作已退出

证据：[test_pmf_recovery.py 第 169～178 行](</C:/Users/fubai/Documents/My_Workspace/.auto-pm/worktrees/m2-v04/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/e2e/test_pmf_recovery.py:169>)；Scene.kill 第 288～294 行、fixture teardown 第 324～330 行，RECONCILER 内同类逻辑。

主审计创建自己的 sleep 子进程，Popen.poll 确认存活；AST 提取 helper 并对 Win32 调用注入失败，得到：

```text
popen_confirms_alive=True
OpenProcess_denied=False
GetExitCodeProcess_failed=False
owned_child_reaped=True
```

这是故障注入，**没有声称本轮 OS 真实拒绝了对子进程的查询**。本轮完整测试后，受控 CIM 枚举没有 Python/pythonw 残留。

影响：在权限不足/API 失败时，测试可能略过终止并通过“已经退出”断言。最小修法：区分 ALIVE/EXITED/UNKNOWN，声明 Win32 HANDLE 函数签名、检查调用结果；UNKNOWN 不得作为回收证据；自有进程以持有句柄/Popen.wait 确认退出，孤儿 PID 清理也应等待确认。只修测试生命周期，不扩展成 V04-R1 产品入口。

## 5. 已知债与未覆盖部分

TD070～073 与当前 P1 范围相容：SDK/QML 仍未强制分类、Mission 挂起约束、非文件证据只验格式、惰性表结构未并入 schema。TD074～077 与 V04 勘测相容：无受支持重启入口、人工身份夹具审查、恢复链易用性、持续写入边界未量化。**F11 的具体身份缺陷本轮已修复通过；TD075 的其他夹具风险不等于已偿还。**

下列没有独立完成，不得写成 PASS：

- 持续真实业务写入＋多个读者的压力边界。r08/r09 打开事务并等待，没有修改业务行；只能证明该锁竞争/开库场景。
- r04～r07 的完整真实执行器授权链；其中部分启动证据由隔离夹具构造。
- 所有九组回归的重新执行、全部 14/26 个变异的重新执行、跨机器 Qt 稳定性。
- P1 同 request_id 真正同时提交的竞态全集；原 e04 部分重放调用是顺序执行，不据此声称所有并发重放分支已验证。
- 真实 Claude→GPT 换 Agent、旧 owner 写入拒绝、TD2 租约轮换。关闭的 V04 Run 永不用于此演练。
- 整个 M2、M0/M1 重验、合并可用性、部署准入、全库类型清零与门禁分级自动生效。

“数据库任何异常都不重试”过宽：F12 只证明数据库内容读取 PermissionError/被测 DB 路径校验不走边车宽容；父提交既有 Windows 快照锁获取失败仍可走漂移重试。持续异常最终拒绝，未把此既存机制误列为本次引入回归。

## 6. 下一步最小处置（建议，不是执行授权）

1. **先一张 P1 合同修复范围**：集中处理 A-P1-01～03；优先复用既有 facade/intake service/store 与其测试，不改 schema、历史记录或其他 WBS 业务。出卡时精确确认路径；修复必须同时覆盖成功、失败、显式冲突重放、证据目录负例。
2. **验证工具/测试补证独立于产品改动**：处理 A-GATE-01/02、A-V04-01/02；复用同一套纯反例与必要受控测试，不盲目重跑整个 M2。先测判卷器拒绝坏输入，再采新字节证据；旧 CP、报告、Run 保持不可变。
3. 新候选/新验证回执通过后再做一次针对这些缺口的独立复验。**不重开已关闭 V04 Run，不回退三个来源分支，不重新制造完成态。**
4. 复验无阻断后再准备 TD2 文档卡，登记/归档其他债并恢复原接力顺序。此报告提供新发现的稳定审计编号，未擅自占用 TD/CHG 编号或改台账。

本轮阻断的是“独立质量审计通过”与其条件后继，不是宣布治理库损坏、原提交无效或所有 M2 功能失效。不存在授权缺口反复补卡的实施尝试：**本轮只审计，找到具体反例后交付，不修产品、不申请额外写库。**

## 7. 收尾保全与清理

候选 HEAD/父提交与 20 个 CP 内容 SHA 均保持不变；Git tracked/untracked 状态为空，既有 ignored Mypy 缓存保留。主工作区原有脏治理材料不清理。库 SHA、active/previous 指针 SHA 不变；当前 Python/pythonw 进程为 0。已创建的探针 sleep 子进程均 wait 回收；没有杀其他 Agent 进程。

环境临时 checkout 用正常 `git worktree remove` 退役，不强制、不 prune。审计专用 TEMP 目录、四个自建诊断脚本在证据落成本报告后清理，最终回执追加在下方；不删除候选、旧 app.db、旧报告/Decision/Checkpoint 或 Git 提交对象。

结论：**环境准入 PASS（精确审批），治理与字节证据 PASS；P1 业务合同 FAIL，V04 产品修复 PASS（限定范围），验证防线存在 FAIL/UNVERIFIED。本轮不宣布整体通过、M2 完成或可部署。**

### 最终清理与时限回执

- `gpt_audit_p1_20261005`、`gpt_audit_v04_20261005`、`gpt_audit_mypy_20261005` 三个精确 TEMP 目录已移除，逐项 `StillExists=false`。首次普通 PowerShell 删除因隐藏/系统/只读属性限制报错，未扩大目标；复核绝对路径后仅对自建测试目录使用 `Remove-Item -LiteralPath ... -Recurse -Force` 成功。此处不涉及真实 Git 工作树的强制删除。
- 四个自建诊断文件 `gpt_p1_v04_readonly_audit.py`、`gpt_gate_negative_probe.py`、`gpt_intake_negative_probe.py`、`gpt_recovery_negative_probe.py` 已用 apply_patch 删除；负例方法与实际输出保留在本报告，完整执行回执亦在本次对话中。
- 没有清理旧候选缓存、历史治理文件或其他 Agent 的任何 TEMP 对象。环境探针提交对象保留在 Git 中，无新产品分支或提交。
- 产品／canonical 最终采样仍与 §2 一致。交付在 UTC 21:32 之前完成，距 22:37:03 硬截止尚有余量；没有因耗尽时限把未测项改记 PASS。
