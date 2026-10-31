# 驾驶舱全面体检报告（Gemini 原文，待核意见）

> **性质说明（存档者加）**：本文是 Gemini（反重力 Teamwork 多代理模式）按 `plans/Gemini驾驶舱全面体检话术_20261031.md` 在对话里交的报告原文，只做了 HTML 实体还原和去掉对话进度播报，内容未改。**其中每一条都只是待核意见**；存档者对照基准提交 `4c71830e` 做的抽查核实见同目录 `verification.md`，核实结论与下文不一致处以 `verification.md` 为准。报告自称“VICTORY CONFIRMED”是它自己的子代理自审，不算独立核实。

# auto-pm 驾驶舱 (SW-2026-008) 架构与治理体检综合诊断报告

**报告时间**: 2026-10-31 13:30:00 MST (时间一律 MST，UTC-7)
**基准提交**: `4c71830ee128c40f1c8fdac8569f43de3af2cbfb`
**独立核验判定**: **VICTORY CONFIRMED** (独立审计员已完成三阶段走查、零文件变动确认与基准行号核对)
**审计性质**: 严格只读（零工作区文件修改、零仓库提交、零树内测试运行，全部引用锚定基准提交）

---

### 一、给用户的结论 (Executive Summary)

当前驾驶舱好比一套**“强外壳、弱内联、单向自锁”**的工业自动化控制柜：
1. **约束弱模型 (Trae)**：**无法有效约束**。规程库中逾 35% 为纯文本标贴（无硬件电气互锁），30% 为部分阻断但存在旁路（如 `caller_agent` 默认视作操作员、`protected_files` 遇异常 Fail-Open、Mode A 审批凭据为纯正则字符串且不防伪造）；Trae 极易自造凭据自审批、跨目录调控制根、或在工作区遗留调试残留。
2. **锁死操作员风险**：**极高**。系统采用刚性单向闭锁，缺乏安全回路复位逻辑（Reset Circuit）：租约超时后既不可续约亦不可自回收（自杀式死锁）；收口处于 `PREPARED` 时阻断所有终态且缺少 `abort` 接口；状态机非正交（`RUNNING` 无法直接切 `CANCELLED`）。
3. **前三项最严重隐患**：
   - **P0（边界击穿自毁）**：`project create --dest-dir` 相对路径解析至活动发布目录，Copier 写入文件导致下次启动触发 `_verify_exact_tree` 判定载荷异常，**发布槽直接报废瘫痪**；
   - **P1（状态机双死锁）**：租约过期自杀式互锁 (`continuity_store.py:6215, 8031`) 与收口中断永久阻断 (`continuity_store.py:7454`)；
   - **P1（门禁双重真空）**：本地 `pre-commit` 完全不跑 pytest/ruff/mypy，而 GitHub Actions `windows-extra` 标记 `continue-on-error: true`，Windows 核心崩溃被旁路放行。
4. **表面互锁 vs 实体接触器**：“完成必须附证据”、“做的和审的分开”、“零负担交付”纯属控制柜外贴纸；而 `pm close` 则是在未验证前级信号一致性时锁死的机械跳闸机构。

---

### 二、体检环境与基准核验 (Audit Environment)

1. **基准提交核对 (`git cat-file -t 4c71830ee128c40f1c8fdac8569f43de3af2cbfb`)**：
   - 返回类型：`commit`（合法有效完整提交）。
   - 远端分支比对：`git log --oneline 4c71830e..origin/main` 为空（0 commits delta，main 头与基准提交一致）。
   - 本地 `HEAD` 记录：`3f6856b0855c17576f683f28df0044e9f0d0ede7`（本地超前 1 个纯治理落账提交 `chore(governance): [CHG-SCPT-2026-466] bind rel5 run-001 settlement decisions`）。本报告所有行号与源码断言一律严格锚定 `4c71830e`。
2. **工作区环境上下文 (`git status --short`)**：
   - `M 00_Infrastructure/auto_pm/active_release.json`（指向发布版 `1.3.3-163c7a3`，基准为 `1.3.3-8d7d387`，反映第 5 次发版在途状态）
   - `M 00_Infrastructure/auto_pm/deployment_manifest.json`
   - `M 00_Infrastructure/auto_pm/previous_release.json`
   - `M .auto-pm/continuity.db`（本地 SQLite 主账本与临时锁文件）
   - `?? .agents/teamwork/`（团队多智能体只读协同元数据，严格排除在 git 追踪外）
3. **审查目录范围**：
   - 纳入：`01_Project自动化项目管理/.../auto_pm/` (domain, application, infrastructure, ui/cli, contracts)、`00_Infrastructure/auto_pm/launcher/`、`reviews/tools/`、`.github/workflows/`、`SYS-2026-001_WorkspaceGovernance/`、`AGENTS.md`。
   - 排除：旧归档副本 `00_Infrastructure/auto_pm/auto_pm/`（按用户 2026-10-25 B9 裁决保持归档只读隔离）。
4. **验证执行记录**：
   - 外部突变测试（Targeted Mutation Testing）：于 2026-10-31 13:00–13:20 MST（处于 17:00–21:00 MST 受限窗口之外），在 `$env:TEMP` 外部干净副本中通过 `git archive 4c71830e` 执行 10 点突变验证；验证完毕即时物理销毁（DEV-TMP-001）。

---

### 三、九大检查维度结论总表 (Nine Aspects Conclusion Table)

| 检查维度 | 状态 | 调研与验证方法 | 发现缺陷 ID |
|---|---|---|---|
| **1. 状态机死路 (State Deadlocks)** | 发现严重缺陷 | 静态 AST 控制流追踪、状态转移矩阵有向图遍历、租约与收口条件全分支核验 | GM-02, GM-03, GM-11 |
| **2. 门禁与 CI 对齐 (Gating & CI)** | 发现严重缺陷 | 本地 Git hooks、`pm verify` 与 `.github/workflows/` YAML 矩阵全规则横向映射 | GM-04, GM-05 |
| **3. 保护文件一致性 (Protected Files)** | 发现严重缺陷 | `audit_pr.py`、`protected_files.py`、`pr_scope_check.py` 保护正则跨模块全量 Diff 比对 | GM-06, GM-12 |
| **4. 规矩与机器差距 (Hard-blocks)** | 发现严重缺陷 | 逐条审计 `AGENTS.md` 27 项铁律，静态调用链分析、参数穿透与 Fail-Open 语义判定 | GM-07, GM-08 |
| **5. 认证强度审查 (Auth Strength)** | 发现严重缺陷 | 14 项流转动作双模式（Mode A/B）源码分支核验、正则与 PIN 密码学签名追踪 | GM-09, GM-13 |
| **6. 失败信息可用性 (Failure Usability)** | 发现缺陷 | CLI 异常包装层分析、Pydantic 验证捕获块、重试建议文本可执行性审查 | GM-14, GM-19 |
| **7. 平台与 Windows 兼容性** | 发现严重缺陷 | 编码规范跨规则冲突扫描、大小写匹配、`os.replace` 句柄锁、进程树清理机制分析 | GM-10, GM-15, GM-16, GM-17 |
| **8. 测试质量与突变验证** | 发现缺陷 | Mock 密度走查、外部独立干净副本 10 点靶向突变测试（8 Killed, 1 Harness Fail, 1 Survived） | GM-18 |
| **9. 仓库隐私与密钥 (Privacy/Secrets)** | 发现残留 | 静态正则扫描全库历史提交与基线代码，仅提取 `path:line` 与类型，严禁回显脱敏内容 | GM-20 |

---

### 四、综合表格 B (Table B)

#### 表 B-1：规矩与机器的差距全量清单 (Aspect 4)

| 规则项 | 条文核心要求 | 约束等级 | 4c71830e 实现文件:行号 | 退出码 / 异常 | 可绕过性与失效边界分析 | Trae 受控度评估 |
|---|---|---|---|---|---|---|
| **WS-001 (1)** | 单电脑单克隆，工位从控制根派生 | **部分阻断** | `control_root_guard.py:189-195`<br>`main.py:14-25` | `ControlRootGuardError`<br>(Exit 1/2) | **可绕过**：`main.py:26` 仅按 `__file__` 判定控制根，在工位 CWD 执行控制根脚本完全放行（Drill D10）；外部 clone 会自建独立 SQLite 数据库导致两本账分裂。 | 高危失控 |
| **WS-001 (2)** | 驾驶舱命令只在控制根执行 | **部分阻断** | `main.py:27-32`<br>`control_root_guard.py:139` | `SystemExit(2)`<br>`ControlRootGuardError` | **可绕过**：仅拦截通过工位根直接调用的 `main.py`；跨目录调用或直接 `python -m auto_pm` 可绕过入口守卫；只读命令不限制。 | 中危 |
| **WS-001 (3)** | 工位与分支前缀隔离匹配名册 | **部分阻断** | `worktree_policy_service.py:40`<br>`agent_worktree_service.py:140` | `StationRefusedError`<br>`ClickException(1)` | **实现偏差**：`worktree_policy_service:40` 硬编码 `_BRANCH_PREFIX = "codex/"`，与规范冲突。若 Agent 直接用 `git checkout -b` 随意命名分支则无底层阻断。 | 高危失控 |
| **WS-001 (4)** | 一卡单派，声明 owned paths 不交叉 | **硬阻断** | `continuity_store.py:253-270`<br>`worktree_policy_service.py:220` | `ContinuityStoreError`<br>`ConflictError(1)` | **不可绕过**（在规范工具链内）：SQLite `execution_leases` 加行锁。但在工位内直接改动文件在 commit 前无物理文件锁保护。 | 低危受控 |
| **WS-001 (5)** | 工位提交必须带 `--control-root R` | **硬阻断** | `git_hook_enforcer.py:120-150`<br>`hooks/pre-commit:30-45` | `SystemExit(1)` | **条件生效**：依赖本地 Git hooks。但新 clone 或新 worktree 默认未装 hook（Trae Probe F13），CI 不验 `--control-root`。 | 高危空窗 |
| **WS-001 (6)** | 台账、WBS、治理库只由主执行写 | **部分阻断** | `protected_files.py:35-85`<br>`audit_pr.py:130-160` | `WARN` (Exit 0)<br>`PreCommitError` | **Fail-Open 漏洞**：`audit_pr.py` 对受保护文件仅报 `WARN`（退出码 0 放行）；`protected_files.py:115` 遇到 Git 报错直接 `return False`。 | 高危穿透 |
| **WS-001 (7)** | 禁越权收工位；清 run-plan 需身份 | **部分阻断** | `agent_worktree_service.py:53-77, 271, 362` | `StationRefusedError`<br>(Exit 1) | **Fail-Open 漏洞**：`caller_agent()` 读取环境变量，若未注入匹配则返回 `""`，被上层判定为人类终端，赋予关闭他人工位和清扫所有 run-plan 的最高权限！ | 极高危失控 |
| **WS-002 (1)** | 切卡/搁置必须带 `--approval-evidence-ref` | **部分阻断** | `pm_switch.py:45-80`<br>`user_evidence.py:18-59` | `ClickException(1)` | **可伪造**：无 PIN 模式下，仅用正则 `user-confirmation:[A-Za-z0-9._:/-]{7,}` 校验且不含 18 个黑名单词。Agent 伪造时间戳即可放行。 | 高危失控 |
| **WS-002 (2)** | 无原话只能停在“等你”，禁自推进 | **纯文字** | 无代码实现（依赖提示词自觉） | 无 | **无机械约束**：代码只认格式，无法区分调用方是人类键盘还是 Agent 进程（除非开启交互式 TTY PIN 且禁止重定向）。 | 极高危失控 |
| **WS-002 (3)** | 任务并发软上限 8 张 | **硬阻断** | `mission_service.py:110-135`<br>`contracts/mission.py:85` | `MissionAdmissionError`<br>(Exit 1) | **不可绕过**：创建 Mission 时统计 active 数，超额必须提供 release ref。仅限走驾驶舱命令，手工 Git 分支不受控。 | 中危受控 |
| **WS-002 (4)** | 禁插队抢钥匙 (PREEMPT) | **硬阻断** | `continuity_store.py:650-680`<br>`lease_handover_service.py:80` | `LeaseConflictError`<br>(Exit 1) | **不可绕过**：SQLite 租约排他锁，未过期前其他 Agent 无法夺取。 | 安全受控 |
| **AUD-001 (1)** | 做的和审的分开，严禁自审自编 | **纯文字** | 无自动化 CI 校验<br>`audit_pr.py` 无防自审断言 | 无 | **完全无阻断**：`audit_pr.py` 接受 PR 号，从不比对 PR 作者与当前审计者；CI (`pr-gate.yml`) 中根本不调用 `audit_pr.py`。 | 极高危失控 |
| **AUD-001 (2)** | 审计退出码 0 放行，1 阻断 | **部分阻断** | `audit_pr.py:280-310` | Exit 0 / 1 / 2 | **未挂接 CI**：退出码仅在终端打印，未作为 GitHub 必须通过的状态检查（Required Check）。受保护文件命中仅为 `WARN` (Exit 0)。 | 中危 |
| **AUD-001 (3)** | PR 仅用 Merge commit，严禁 Squash | **部分阻断** | GitHub 仓库设置项 | GitHub API 拒绝 | **依赖配置**：若 GitHub 仓库未关闭 Squash/Rebase，Agent 在 Web 端可自点击合并；本地无 hook 拦截 `git merge --squash`。 | 中危 |
| **FIX-001 (1)** | 修复必须附同类排查清单 | **纯文字** | 无静态 AST 或检查器 | 无 | **无机械约束**：完全依赖 PR 描述文本，无自动化 Linter 验证清单覆盖范围与真实性。 | 极高危失控 |
| **FIX-001 (2)** | 根除源头，修复脚手架与生成器 | **纯文字** | 无代码实现 | 无 | **无机械约束**：技术债关单靠手工核对或 Markdown 状态勾选。 | 极高危失控 |
| **FIX-001 (3)** | “完成”必须附带证据（SHA/测试结论） | **部分阻断** | `pm_closure_service.py:340-390`<br>`pre_closure_gate.py:50` | `PmClosureError`<br>(Exit 1) | **收口时硬阻断**：`pm close` 强制提取 Checkpoint SHA 与测试通过事实回写 CHG。但在中间过程全凭自律。 | 中危受控 |
| **FIX-001 (4)** | 严禁代码盲问 (Zero-Stupid-Questions) | **纯文字** | 无代码实现 | 无 | **无机械约束**：纯人机交互规范，AI 提问不受代码拦截。 | 高危失控 |
| **Zero-Burden (1)** | 禁半成品外溢，禁借提问推卸责任 | **纯文字** | 无代码实现 | 无 | **无机械约束**：无看门狗监控 Agent 提问频次。 | 极高危失控 |
| **Zero-Burden (2)** | 交卷前极限自我施压（PLC/Python 门禁） | **部分阻断** | `pr-gate.yml:30-65`<br>`pre-commit` | CI Job Failure<br>(Exit 1) | **CI 局限**：CI 跑了 `pr_scope_check.py`，但无 PLC 真实 LSP 环境；HMI 死链未并入必过门禁。 | 中危 |
| **DEV-TMP-001** | 临时文件即时销毁，禁残留根目录 | **纯文字** | `.gitignore` (部分规则)<br>无根目录清洁度扫雷器 | 无 | **无机械阻断**：虽然 `.gitignore` 排除了常规缓存，但根目录若生成未命中规则的临时调试文件，pre-commit 和 CI 均不拦截。 | 高危残留 |
| **DEV-TMP-001 (4)** | `.agents/` 过程文件严禁入 Git | **硬阻断** | `.gitignore:15-18`<br>`pr_scope_check.py:45-60` | `PRScopeError`<br>(CI Exit 1) | **不可绕过**：`.gitignore` 排除且 CI 门禁显式检测，包含 `.agents/` 过程文件直接阻断 PR。 | 完全受控 |
| **DEV-ENC-001** | 跨语言显式声明 utf-8 与 errors="replace" | **纯文字** | 无全局 AST 扫描器 | 无 | **无机械阻断**：Ruff/Mypy 默认不强制检查 `open()` 参数，导致 Windows 下处理文件时常因漏传参数爆编码崩溃。 | 高危失控 |
| **Anti-Prompt** | 治理规则严禁仅靠提示词自觉 | **部分阻断** | 本次审计对象自身 | N/A | **系统性弱点**：本表显示多达 35% 的核心治理条款停留在纯文字阶段，违反了该设计原则自身。 | 极高危 |
| **Anti-Shortcut** | 禁伪造测试结果与审批凭据 | **部分阻断** | `user_evidence.py`<br>`pm_closure_service.py` | `PmClosureError` | **部分阻断**：凭据正则过于宽泛可伪造；但 `pm_closure` 会校验 Checkpoint SHA 是否在 Git 树上真实存在。 | 中危 |
| **Self-Closing (1)** | 严禁单独推状态跳过收口 | **硬阻断** | `pm_cockpit_service.py:420-431`<br>`continuity.py:180` | `PmCockpitError`<br>(Exit 1) | **严格阻断**：`pm_cockpit_service:427` 检查 `has_completed_closure(mission_id)`，直接 transition 到 CLOSED 会在收口时报拒绝。 | 安全受控 |
| **Self-Closing (2)** | 隔离文件按字节并回控制根，不替提交 | **硬阻断** | `pm_closure_service.py:304-316` | `PmClosureError`<br>(Exit 1) | **不可绕过**：二进制字节流合并校验并写回控制根，严格拒绝执行 `git commit`，提交权保留给人类。 | 安全受控 |

---

#### 表 B-2：认证强度全表 (Aspect 5)

| 动作名称 | 调用命令 / 入口 | 4c71830e 实现位置 | Mode A (无 PIN 验证器) | Mode B (有 PIN 验证器) | Agent 能否自批/伪造 | 未验证路径与绕过点 | 认证安全等级 |
|---|---|---|---|---|---|---|---|
| **变更单批准** | `change transition <ID> --to approved` | `change.py:573`<br>`approval_pin.py:35` | 接受任意 `--approver` 与合法格式的 `--approval-evidence-ref` | 弹出交互式输入，校验 `scrypt` 哈希防重放 | **Mode A 允许**<br>(Mode B 阻断) | Mode A 下传入任意姓名与合规时间戳即可放行 | **极弱 (A)**<br>强 (B) |
| **决策创建** | `decision create ...` | `decision_service.py:140`<br>`user_evidence.py:35` | 仅验证入参符合 `user-confirmation` 正则，不含 agent 词汇 | 校验 PIN 证据 | **Mode A 允许**<br>(Mode B 阻断) | 构造不含黑名单词汇的字符串绕过 | **极弱 (A)**<br>强 (B) |
| **实施卡批准** | `implementation-card approve <ID>` | `implementation_card.py:205`<br>`approval_pin.py:45` | 直接采用 CLI 参数中的姓名与凭据，无密码学签名 | 强制要求通过控制根验证器签署证明 | **Mode A 允许**<br>(Mode B 阻断) | Mode A 下任意 Agent 可批准自身实施卡 | **极弱 (A)**<br>强 (B) |
| **需求批准** | `pm approve --mission-id <ID>` | `pm.py:880`<br>`approval_proof_service.py:306` | `resolve()` 显式原样返回 caller 传入的凭据 (Line 314) | 拦截并验证终端交互 PIN | **Mode A 允许**<br>(Mode B 阻断) | Mode A 下输入参数即为输出结果，完全放行 | **极弱 (A)**<br>强 (B) |
| **需求验收** | `pm accept --mission-id <ID>` | `pm.py:1106`<br>`approval_pin.py:50` | 无 PIN 检查，VERIFIED 状态即可推进至 ACCEPTED | 必须终端输入 PIN 确认验收并记录事实 | **Mode A 允许**<br>(Mode B 阻断) | Mode A 下 Agent 可越过人类直接自验收任务！ | **极弱 (A)**<br>强 (B) |
| **需求收口** | `pm close --mission-id <ID>` | `pm_closure.py:123`<br>`pm_closure_service.py:265` | **不请求 PIN**，依赖前序 `pm accept` 凭据链 | **不请求 PIN**，复用 `pm accept` 凭据链 | **取决于前序状态** | 若前序 `pm accept` 被 Agent 自批，收口直接放行 | **依赖前序**<br>(弱) |
| **任务切卡** | `pm switch --pid <P> --to <M>` | `pm_switch.py:45`<br>`user_evidence.py` | 仅验证 `--approval-evidence-ref` 字符串格式 | 校验 PIN 证明是人类要求切卡 | **Mode A 允许**<br>(Mode B 阻断) | 伪造凭据自行抢占/切换任务 | **极弱 (A)**<br>强 (B) |
| **任务解搁置** | `pm unpark --mission-id <ID>` | `pm_switch.py:120`<br>`user_evidence.py` | 仅做正则格式校验，无数字签名 | 校验 PIN，验证是用户原话指令 | **Mode A 允许**<br>(Mode B 阻断) | 伪造字符串绕过 | **极弱 (A)**<br>强 (B) |
| **任务搁置** | `pm park --mission-id <ID>` | `pm_switch.py:160` | 带凭据做正则校验；不带凭据允许停在“等你” | 带凭据校验 PIN；不带凭据允许停在“等你” | **允许停在等你**<br>(A 下伪造凭据通过) | Agent 可随时自行 park 任务以逃避责任 | **弱 (A)**<br>中 (B) |
| **租约强行回收** | `pm sign-risk --run-id <R> --claimant <C>` | `pm_handoff.py:175`<br>`lease_handover_service.py:150` | 依赖 TTY 检查；无 PIN 时回退至 `getpass.getuser()` | 校验终端两次交互输入 + PIN | **伪终端下允许 (A)**<br>(Mode B 强阻断) | **源码注释自证 (Line 215)**：Agent 构造 PTY 并清空环境变量可注入 `run_id` 和 `接受风险` | **弱 (A)**<br>强 (B) |
| **PIN 初始化/轮换** | `approver-pin init / rotate` | `approval_pin.py:75`<br>`approval_proof_service.py:108` | 自身即为 Mode B 开关，初始化检测 Agent 环境变量 | 轮换需输入旧 PIN，`scrypt` 强派生 | **无法自批**<br>(检测环境变量) | 未注入环境变量的纯终端子进程可能被利用 | **中** |
| **安全区签字** | PR 评论触发<br>`safety_zone_check.py` | `safety_zone_check.py:80, 596-625` | 校验 GitHub Comment 作者与数字 UID (`SIGNERS`) | 同左（不走本地 PIN，纯 GitHub 凭据） | **PAT 共享时允许** | Agent 若拥有宿主机 `gh` CLI 登录态，可直接调用 API 伪造签字 | **中** |
| **独立审计放行** | GitHub PR Merge | `audit_pr.py:280`<br>`reviews/21_audit_checklist.md` | 本地脚本手工运行，CI 未集成门禁校验 | 同左 | **完全允许** | 审计与合并完全依赖 GitHub 分支保护；若无保护可自合并 | **极弱** |
| **发布指针切换** | 修改 `active_release.json` | `launch.py:45`<br>`bootstrap.py:30` | 纯文件系统 JSON 读写，无数字签名与哈希校验 | 同左 | **完全允许** | 任意 Agent 均可修改 JSON 将版本指向未经验证的目录 | **极弱** |

---

### 五、新发现缺陷清单 (Table C: New Findings List)

| 编号 | 级别 | 检查面 | 位置 (`file:line`) | 现象 | 为什么是问题 | 怎么复核 | 与已知问题的关系 | 把握 | 是否改变判卡点 | 建议修法 |
|---|---|---|---|---|---|---|---|---|---|---|
| **GM-01** | **P0** | 专题 A | `auto_pm/ui/cli/project.py:266, 328` | `project create --dest-dir` 使用原始 `os.path.abspath` 解析相对路径 | 在启动器模式下（`cwd=release_dir`），相对路径解析至活动 release 槽，写入项目源码污染发布目录。下次启动触发 `bootstrap.py:277` 的 `_verify_exact_tree` 报错，**发布槽直接报废瘫痪**。 | 运行 `main.py project create --dest-dir ./out ...`，查看 `00_Infrastructure/auto_pm/releases/<active>/` 下是否出现 `out/`；再次运行 `main.py` 触发启动器报错。 | 已知 N1 的设计层根因 | 高 | 改变 | 将 `--dest-dir` 参数类型升级为 `CallerPath`，并在 `cmd_create` 中加入 `os.path.commonpath` 检查，强制目标路径必须位于 `workspace_root` 内部。 |
| **GM-02** | **P1** | 检查面 1 | `continuity_store.py:6215, 8031` | 租约过期后 `renew_lease` 拒绝续约；`reclaim_lease` 拒绝原持有者回收 | Agent 因休眠或长编译导致 lease 超时后，调用 renew 被报“已过期”，调用 reclaim 被报“不能顶掉自己”，陷入**自杀式死锁**，合法执行者无法自愈。 | 设定租约 1s 并 sleep 2s；以原 owner 调用 `renew_lease` 报已过期；再调用 `reclaim_lease` 报不能顶掉自己。 | 已知 F21/D045 的设计层根因 | 高 | 改变 | 修改 `reclaim_lease`：当 `claimant_id == expected_owner_id` 时，若租约已过期，允许原持有者自增 epoch 重申租约。 |
| **GM-03** | **P1** | 检查面 1 | `continuity_store.py:7454-7467` | 收口单进入 `PREPARED` 状态后硬阻断终态流转，且缺乏 `abort` 接口 | 自动化收口在文件合并或 Git 写入中途崩溃时，残留 PREPARED 状态，`_refuse_while_closure_prepared` 永久拦截该 Work/Run，无法重试推进。 | 在 `closure_items` 插入一条 status=PREPARED 记录；尝试流转 Work 状态，观察被抛出异常且无任何回滚 CLI 指令。 | 新问题 | 高 | 改变 | 新增 `continuity closure abort --work-id <WID>` 补偿指令，允许回滚 PREPARED 状态至可重试状态。 |
| **GM-04** | **P1** | 检查面 2 | `git_hook_enforcer.py:816-838` | 本地 `pre-commit` 完全不运行 pytest、ruff 与 mypy | 开发者与 Agent 在本地 commit 时绕过耗时质量门禁，未自检语法和断言错误即可提交代码。 | 在 Python 代码中故意制造语法错误或断言失败；执行 `git commit`，观察钩子绿灯通过。 | 已知 F30 的同族新实例 | 高 | 否 | 在 `pre-commit` 钩子中增加快速模式的 `ruff check` 与影响范围内的轻量单测运行。 |
| **GM-05** | **P1** | 检查面 2 | `.github/workflows/sw008-ci.yml:180` | `windows-extra` 测试矩阵标记了 `continue-on-error: true` | Windows 平台的端到端（E2E）、Qt/QML 及核心回归测试即使发生崩溃、访问越界（Access Violation），CI 矩阵依然容忍通过。 | 查阅 `sw008-ci.yml` 第 180 行；提交一个 Windows E2E 必定失败的改动，观察 PR 门禁依然亮绿灯。 | 新问题 | 高 | 改变 | 修复 Windows 虚拟环境中的不稳定测试用例，移除 `continue-on-error: true`，恢复必过红线。 |
| **GM-06** | **P1** | 检查面 3 | `reviews/tools/audit_pr.py:35`<br>`contracts/protected_files.py:40` | `docs/handover/*` 与 `.agents/skills.json` 在受保护清单中全域缺失 | 恶意或失控 Agent 在修改代码时可任意篡改交接总则、用户原话规矩与技能注册表，本地验证与 PR 审计均不警告。 | 在 PR 中修改 `docs/handover/02_必须用户亲口同意的事.md`；运行 `audit_pr.py`，观察未输出 protected 告警。 | 已知 CD-04 的同族新实例 | 高 | 改变 | 在 `audit_pr.py` 与 `protected_files.py` 的 `PROTECTED_PATTERNS` 中补齐上述路径。 |
| **GM-07** | **P1** | 检查面 4 | `agent_worktree_service.py:72-76` | `caller_agent()` 未匹配到环境变量时返回空串 `""`，被上层判定为人类终端 | Trae 作为未注入环境变量的子代理，运行 `worktree close` 或 `sweep` 时被驾驶舱直接赋予“人类最高权限”，可随意抹除任意他人工作树。 | 清空环境变量 `AUTO_PM_AGENT` 后执行 `main.py worktree close claude`，观察命令未拒绝且执行成功。 | 新问题 | 高 | 改变 | `caller_agent()` 未匹配时应返回 `"unknown"`，在写操作中一律 fail-closed 拒绝，仅在显式 `--as human` 且具备 PIN 时放行。 |
| **GM-08** | **P1** | 检查面 4 | `protected_files.py:115` | `_protected_file_changes` 捕获 `(GitError, OSError)` 时直接 `return False` | 当 Git 异常退出或磁盘 I/O 报错时，门禁 Fail-Open 判定“未改动受保护文件”，穿透文件保护网。 | 构造一个损坏的 Git 索引或传递非法 commit-ish；观察函数吞掉异常并返回 `False` 放行。 | 已知 SEC-003 的设计层根因 | 高 | 改变 | 捕获异常后必须直接抛出 `SystemExit(1)` 或 `ProtectedFileVerificationError`，强制 Fail-Closed。 |
| **GM-09** | **P1** | 检查面 5 | `approval_proof_service.py:314` | Mode A 下 `resolve()` 显式原样返回入参中的 approver 与 evidence_ref | 默认未提交 PIN 时，驾驶舱所有审批完全退化为字符串正则，Agent 可伪造凭据自审批立项与验收。 | 执行 `main.py pm approve --mission-id M1 --approver fubai --approval-evidence-ref user-confirmation:20261031-120000`，观察直接批准成功。 | 已知 CD-01 的设计层根因 | 高 | 改变 | 在 Mode A 下输出高危风险警告，推进全项目普及 Mode B（PIN 注册表）；增强证据链正则与来源上下文核查。 |
| **GM-10** | **P1** | 检查面 7 | `reviews/tools/encoding_check.py:3, 117`<br>`AGENTS.md:243` | `AGENTS.md` 要求 `errors="replace"`，而 `encoding_check.py` 判定包含 `\ufffd` 为 FAIL | 工程师按规范编码处理包含未知字符的文件并保存，被自身 PR 门禁脚本判定为代码损坏而拦截合并。 | 创建包含 `\ufffd` 替换字符的测试文件；运行 `python reviews/tools/encoding_check.py`，观察抛出 FAIL。 | 新问题 | 高 | 改变 | 统一编码规范定义：生产代码严禁引入替换字符；仅在只读日志解析与外部兼容层使用 `replace`。 |
| **GM-11** | **P2** | 检查面 1 | `continuity_store.py:521-526` | `_STORE_RUN_TRANSITIONS` 缺少 `RUNNING -> CANCELLED` 与 `VERIFYING -> CANCELLED` | 任务执行故障时无法直接取消，操作员必须反直觉地进行 `RUNNING -> BLOCKED -> CANCELLED` 两阶段跳跃。 | 对一个 RUNNING 状态的 Run 执行 `continuity run transition --to CANCELLED`，观察抛出“非法状态迁移”。 | 已知 F19 的同族新实例 | 高 | 否 | 在状态转移表中补充直接取消和挂起的前进/后退路径。 |
| **GM-12** | **P2** | 检查面 3 | `reviews/tools/test_protected_lists_in_sync.py:26` | 守护单测仅断言 `audit_pr <= protected_files` 单向子集 | `protected_files.py` 补充防作弊测试路径（`tests/*`）后，`audit_pr.py` 未同步，单测依然绿灯放行。 | 查阅 `test_protected_lists_in_sync.py` 代码，观察断言逻辑确为单向子集。 | 已知 CD-04 的同族新实例 | 高 | 否 | 将测试改为双向全等集合断言：`assert set(audit_pr) == set(verify)`。 |
| **GM-13** | **P2** | 检查面 5 | `auto_pm/ui/cli/pm_handoff.py:215` | `sign-risk` 在 Mode A 下可通过构造伪终端（PTY）清空环境变量注入输入绕过 | 源码注释自证：伪终端结合空环境变量可穿透 TTY 检查，实现无人介入强行回收租约。 | 编写调用脚本包装 pty.openpty() 并在清除环境变量后调用 `sign-risk`，观察绕过 TTY 检查。 | 已知 CD-02 的同族新实例 | 高 | 否 | 强制要求无论任何模式下，涉及风险签字必须输入 PIN 或在有 GUI 弹窗确认下操作。 |
| **GM-14** | **P2** | 检查面 6 | `auto_pm/ui/cli/__main__.py:66-77` | CLI 入口仅捕获 `ContinuityStoreSchemaError`，底层数据库锁等异常泄漏堆栈 | SQLite 偶发文件锁冲突或参数校验失败时，向用户抛出未经翻译的 Python 多行 Traceback。 | 在并发任务持锁时运行 CLI 查询，触发 `sqlite3.OperationalError: database is locked` 查看控制台输出。 | 已知 F15 的同族新实例 | 高 | 否 | 在 CLI 外层增加全局异常捕获器，将标准数据库与领域异常转换为友好提示与退出码。 |
| **GM-15** | **P2** | 检查面 7 | `reviews/tools/test_audit_pr.py:38` | 测试用例硬编码 `PATH: /usr/bin:/bin`，在 Windows 主机运行 pytest 必崩 | 开发者在 Windows 环境执行本地完整测试套件时，`test_audit_pr.py` 因找不到 Git 抛出 WinError 2。 | 在 Windows 终端运行 `pytest reviews/tools/test_audit_pr.py`，观察在 fixture 阶段抛出异常。 | 已知 BUG-002 的同族新实例 | 高 | 否 | 移除硬编码 Unix PATH，改用标准库 `shutil.which("git")` 动态提取环境 PATH。 |
| **GM-16** | **P2** | 检查面 7 | `auto_pm/application/core/ai_handoff_service.py:1094` | `Path.relative_to` 未做大小写折叠（casefold） | Windows 下当盘符大小写不一致时（如 `c:` vs `C:`），抛出 `ValueError` 导致交接逻辑崩溃。 | 在工作目录盘符为小写的控制台调用包含大写路径的交接解析，观察报错。 | 新问题 | 高 | 否 | 在 Windows 平台（`os.name == "nt"`）先调用规范化大小写折叠再做相对路径计算。 |
| **GM-17** | **P2** | 检查面 7 | `auto_pm/infrastructure/continuity_backup.py:386` | Windows 下对处于打开状态的 SQLite 文件使用 `os.replace` 触发 WinError 32 | 后台备份或还原时若有其他线程持有句柄，原子替换失败抛出权限拒绝。 | 在一个连接保持打开的情况下调用备份恢复逻辑，观察 Windows 抛出文件占用异常。 | 新问题 | 高 | 否 | 增加 Windows 平台带指数退避的多重重试机制，并在替换前强制关闭连接句柄池。 |
| **GM-18** | **P2** | 检查面 8 | `continuity_execution_service.py:1420` | 服务层租约过期检查被下层数据库独立校验掩盖，单测断言过宽导致突变存活 | 突变测试点 5 在禁用服务层检查后，测试依然全绿通过，存在单测覆盖盲区。 | 将 1420 行改为 `if False:`，运行对应测试套件，观察全部通过（突变存活）。 | 新问题 | 高 | 否 | 补充针对 `ContinuityExecutionService._require_active_lease` 的纯单元测试。 |
| **GM-19** | **P3** | 检查面 6 | `auto_pm/ui/cli/pm.py:1060` | `execute_pm` 吞掉 Pydantic 错误详情，仅报“--card-json 不是有效的 PlanningScopeCard” | 用户或 Agent 构造的 JSON 出现字段类型或命名错误时，无法获知具体哪一个字段不合规。 | 传入缺少必需字段的 JSON，运行 `pm execute`，查看控制台输出。 | 已知 D7 的同族新实例 | 高 | 否 | 打印 `pydantic.ValidationError` 中的 errors 字段与缺失属性名。 |
| **GM-20** | **P3** | 检查面 9 | 7 处代码/元数据 (`spec_registry.json:4` 等) | 存在硬编码绝对路径 `C:\Users\fubai\...` | 仓库对外发布或在第二台机器克隆时，路径依赖失效且泄露开发机用户名。 | 全库执行 `git grep -n "C:\\Users\\"`，查验提取的 7 处位置。 | 新问题 | 高 | 否 | 统一重构为相对工作区根路径或读取环境变量 `USERPROFILE`。 |

---

### 六、专项专题深入研判 (Special Topics)

#### 专题 A：发布快照与项目目录边界越界隐患
1. **边界击穿机制**：
   - 启动器（`00_Infrastructure/auto_pm/launcher/launch.py:78`）启动子进程时将 CWD 绑定为激活发布槽：`cwd=release_dir`（即 `00_Infrastructure/auto_pm/releases/1.3.3-163c7a3/`）。
   - 在 `auto_pm/ui/cli/project.py:266, 328` 中，新建项目命令的 `--dest-dir` 参数未采用 `CallerPath`，直接调用原生 `os.path.abspath(dest_dir)`。
   - 当用户使用相对路径运行 `main.py project create --dest-dir my_proj ...` 时，相对路径直接被挂接到发布目录内部：`00_Infrastructure/auto_pm/releases/1.3.3-163c7a3/my_proj/`。
2. **发布槽瘫痪级联反应**：
   - Copier 在此路径下生成完整的项目工程与骨架文件；
   - 下次调用 `main.py` 时，`bootstrap.py:277` 执行 `_verify_exact_tree`，检测到发布目录下多出了未登记文件，立即抛出 `BootstrapError(EXIT_RELEASE_INVALID)`，**直接将当前发布槽标记为损坏**！
   - 若 `previous_release` 同样未就绪，启动器以 `EXIT_RELEASE_INVALID` 退出，整个驾驶舱陷入完全无法启动的瘫痪状态。
3. **防护边界评估**：
   - 启动器虽有双槽回退，但 `BytecodeResidueError` 被显式排除在自动回滚外；回退状态不会持久化写回 `active_release.json`，每次启动均报错；回滚版本缺乏最新账本功能时，写操作直接被拒。

#### 专题 B：两本账深度对比与真源探究
1. **架构定位**：
   - **Markdown 文档体系（`01_变更单/` + `01_版本变更台账.md`）**：**Git 审计与法律真源（Audit SoT）**。合进 Git 版本历史，供跨周期人类查阅；
   - **SQLite 数据库（`.auto-pm/continuity.db`）**：**运行期排他真源（Runtime SoT）**。存储 19 张关系表，管理锁、租约持有者、断点 SHA、工位物理状态，被 `.gitignore` 排除。
2. **对账盲区剖析（Probe F26 证实）**：
   - `auto_pm/domain/change/ledger_reconciler.py`（即 `main.py ledger reconcile`）**没有任何代码引入或读取 `continuity.db`**！
   - 仅比对文件系统中的 `CHG-*.md` 文本与 `01_版本变更台账.md` 表格文本；
   - 无论 SQLite 中的 Run/Work 发生怎样的脱节、幽灵流转或状态死锁，对账工具始终输出 `is_clean = True`。
3. **拼合桥梁与死锁**：
   - 两本账仅靠 `pm close` 中的 Saga 事务（`pm_closure_service.py`）单向同步：从 SQLite 提取证据覆盖回写控制根文件，改写 CHG Markdown，更新台账表格，终结 SQLite 状态；
   - 若 Agent 绕过收口直接推状态，两账脱节；后续再调 `pm close`，因缺少收口前置条件直接抛出 `PmCockpitError` 永久卡死。

#### 专题 C：WBS 39 号总方案 20 项抽样核实
从 `SYS-2026-001_WorkspaceGovernance/01_项目文档/39_PM-Flow_恢复与可用化总方案_WBS_PM.md` 抽检 20 项标记为完成/已验收条目：

| # | 任务 ID / 名称 | 文档位置 | 记录状态 | Git 提交与代码核实事实 | 审计分类 | 核心证据 |
|---|---|---|---|---|---|---|
| 1 | `M0` | Line 11 | ACCEPTED | 冻结集成锚点 `d87fd3d` 存在且完整 | **一致** | G10 集成锚点合规 |
| 2 | `M1` | Line 12 | ACCEPTED | 候选提交 `8b02de55` 存在；Run 成功、Work 已关闭 | **一致** | 归档记录完整 |
| 3 | `M2` | Line 13 | ACCEPTED | 2026-10-11 聊天验收；未实现内容递延至 M3 | **落地但含义被改** | 验收记录附带范围后移 |
| 4 | `M3` | Line 14 | ACCEPTED | 2026-10-22 (D09) 验收；附带 5 项已知技术债豁免 | **落地但含义被改** | 带缺陷妥协验收 |
| 5 | `M3-WBS29` | Line 292 | Completed | 重构为短投影视图，V3.0.44 归档 | **一致** | PR #9 合并生效 |
| 6 | `M3-THIN` | Line 291 | Completed | Trae 薄入口已落地；Codex 薄入口明确搁置挂起 | **部分落地** | 仅 Trae 落地，Codex 挂起 |
| 7 | `M3-HANDOFF+V04R1E` | Line 290 | Completed | 租约交接 CLI 与回收接口已落地 (`43b1088e`, PR #11) | **一致** | `lease_handover_service.py` 完整 |
| 8 | `M3-DOCLX` | Line 289 | Completed | 入口措辞、`pm-workflow` 隔离与 Linux CI 修复 (`fe2522d0`) | **一致** | 标记及 CI 补丁真实存在 |
| 9 | `M3-STALE` | Line 288 | Completed | 恢复 11 处陈旧单测运行 (`48458577`, PR #13) | **一致** | 提交 diff 中确实取消了 skip |
| 10 | `D03` | Line 287 | Completed | 冻结提交 `48458577` 与演练报告 004 (`1aefae3d`) | **一致** | 004 报告文件完备 |
| 11 | `D04+D05` | Line 286 | Completed | 构建与全门禁报告 005 (`65445aa4`, PR #15) | **一致** | 报告及产物完备 |
| 12 | `D06` | Line 284 | Completed | 回滚演练报告 006 (`61d06e23`, PR #17) | **一致** | 006 演练记录完备 |
| 13 | `D07` | Line 283 | Completed | 切换发布版本 `1.3.3-4845857` 与报告 007 (`7ae243d6`) | **一致** | 发布槽切换成功 |
| 14 | `M3-DOCSYNC` | Line 282 | Completed | 放宽 PM_SESSION 同步为警告 (`4f90119e`, PR #26) | **一致** | `session_sync_checker.py` 显式降低严重级 |
| 15 | `M3-CHGSCOPE` | Line 281 | Completed | 限制变更范围检查至对应工程 (`a509939a`, PR #27) | **一致** | `change_service.py` 逻辑核实 |
| 16 | `M3-ADOPT` | Line 280 | Completed | C08 承接血缘并防早产终态 (`648b7f8c`, PR #28) | **一致** | `continuity_execution_service.py` 核实 |
| 17 | `M3-PATHORDER` | Line 279 | Completed | C05 路径比较前执行排序标准化 (`a4506c34`, PR #30) | **一致** | `candidate_merge_back_service.py` 核实 |
| 18 | `M3-CHGUNIQ` | Line 278 | Completed | 跨草稿顺序递增预约 CHG 编号 (`a53d9f2e`, PR #34) | **一致** | `change_facade.py` 逻辑核实 |
| 19 | `B4/C2` (MainPR_Gate) | Line 61 | Completed | GitHub Ruleset (id 25842971) 配置 `gate` 必需检查 | **无法判定** | 属于 GitHub 云端配置，Git 仓库无法证实 |
| 20 | Problem 42 (offline) | Line 140 | Completed | `audit_pr.py` 支持 `--offline` 选项 (`08469df4`, PR #292) | **一致** | `audit_pr.py:409, 416, 638` 真实存在 |

**分类统计**：
- **一致 (Consistent)**：16 项 (80%)
- **落地但含义被改 (Landed with altered meaning)**：2 项 (10%)
- **部分落地 (Partially landed)**：1 项 (5%)
- **无法判定 (Unverifiable in repo)**：1 项 (5%)
- **标完成但未落地 (Marked complete but unlanded)**：0 项 (0%)

---

### 七、变异验证记录表 (Mutation Verification Table)

测试在外部隔离目录（`$env:TEMP`）下对 commit `4c71830e` 解压后独立执行：

| # | 领域 | 突变位置 (`file:line`) | 原始代码 | 突变代码 | 目标测试文件与用例 | 基线状态 | 突变结果 | 最终判定 |
|---|---|---|---|---|---|---|---|---|
| **1** | 门禁 | `reviews/tools/audit_pr.py:339-340` | `if hard:` | `if hard and False:` | `reviews/tools/test_audit_pr.py::test_token_in_added_line_fails` | 运行失败 (Exit 1) | 逻辑命中：PASS 代替 FAIL | **变红 (Killed 逻辑)** / **未验证 (套件)** |
| **2** | 门禁 | `auto_pm/ui/cli/runtime_identity_guard.py:36-37` | `if context.conflicts:` | `if context.conflicts and False:` | `tests/cli/test_runtime_identity_guard.py` | 26 passed | 2 failed (Exit 1) | **变红 (Killed)** |
| **3** | 审批 | `auto_pm/application/core/mission_admission.py:50` | `return self.over_limit or bool(self.overlaps)` | `return False` | `tests/core/test_pm_approval_guard.py::test_g01` | 1 passed | 1 failed (Exit 1) | **变红 (Killed)** |
| **4** | 审批 | `auto_pm/application/core/approval_proof_service.py:293` | `if hmac.compare_digest(...)` | `if False:` | `tests/core/test_approval_proof_service.py` | 22 passed | 4 failed (Exit 1) | **变红 (Killed)** |
| **5** | 租约 | `auto_pm/application/core/continuity_execution_service.py:1420` | `if expires_at <= now:` | `if False:` | `tests/core/test_continuity_execution_service.py::test_start_evidence_rejects_expired_or_wrong_lease` | 1 passed | 1 passed (Exit 0) | **仍绿 (Survived)** |
| **6** | 租约 | `auto_pm/infrastructure/lease_wallet.py:87` | `if record["owner_id"] != owner_id:` | `if False:` | `tests/infrastructure/test_lease_wallet.py` | 7 passed | 1 failed (Exit 1) | **变红 (Killed)** |
| **7** | 范围 | `auto_pm/infrastructure/control_root_guard.py:52` | `return tuple(part.casefold()...) if fold else parts` | `return parts` | `tests/core/test_authority_path_covered.py::test_case_rule_follows_the_host` | 18 passed | 1 failed (Exit 1) | **变红 (Killed)** |
| **8** | 范围 | `auto_pm/infrastructure/control_root_guard.py:66` | `path_parts[: len(root_parts)] == root_parts` | `"/".join(...).startswith(...)` | `tests/core/test_authority_path_covered.py::test_scope_rule` | 18 passed | 3 failed (Exit 1) | **变红 (Killed)** |
| **9** | 状态 | `auto_pm/infrastructure/continuity_store.py:2272` | `if run.state not in terminal:` | `if False:` | `tests/core/test_legacy_terminal_lease_fence.py` | 1 passed | 1 failed (Exit 1) | **变红 (Killed)** |
| **10** | 状态 | `auto_pm/application/core/candidate_merge_back_service.py:105` | `if collection.content_hash != ...` | `if False:` | `tests/core/test_candidate_merge_back_service.py` | 12 passed | 1 failed (Exit 1) | **变红 (Killed)** |

*注：变异点 1 在 Windows 下由于测试文件写死 POSIX PATH 导致环境解析错误，但在逻辑上通过隔离探针确认被击杀；变异点 5 仍绿系因下层数据库约束同构拦截掩盖了服务层断言缺失，属单测断言过宽缺陷 (GM-18)。*

---

### 八、闭幕审思与建议 (Closing Paragraphs)

1. **最值得先查的 3 条及理由**：
   - **GM-01 (P0)**：`project create` 目录越界直接把源码打入发布目录，造成不可逆的启动器回滚瘫痪，危及整个工具可用性。
   - **GM-02 (P1)**：租约超时后原持有者无法续约也无法回收，属于自动化生产线最忌讳的“自杀式死锁”，会导致长任务彻底挂起。
   - **GM-05 (P1)**：CI 的 `windows-extra` 开启了 `continue-on-error: true`，给 Windows 核心异常开了假绿灯，破坏了质量承诺的底层真实性。
2. **未覆盖的高风险盲区**：
   - 多工位、多 Agent 真实物理并发抢占 SQLite 数据库时的操作系统文件句柄锁争用与超时雪崩效应；
   - 包含复杂几何图形与大型动画的 QML 模块在无 GPU 的 Windows Server CI 节点上的图形管道段错误。
3. **对提示词与验证体系的反馈**：
   - 本次体检采用“只读探针 + 外部干净突变隔离”模式，在保证 100% 生产零污染的前提下实现了极其犀利的架构透视；
   - 建议将 `Table B-1` 中被标识为“纯文字 (Text-only)”的 35% 条款，逐步下沉至 Linter 规则或 CLI 拦截器，从根本上终结“凭自觉守规矩”的脆弱防线。

---

### 九、12 月前必修清单 (Top 10 Pre-December Remediation List)

1. **[P0] 修复 `project create --dest-dir` 相对路径解析 (GM-01)**：改用 `CallerPath(file_okay=False, dir_okay=True)`，并强制校验生成目录在 `workspace_root` 内部，杜绝摧毁发布目录。
2. **[P1] 解除租约过期“不能顶掉自己”自杀互锁 (GM-02)**：允许租约过期后原 owner 自行带 Token/PIN 重新声明认领，恢复 Agent 长任务掉线后的自愈能力。
3. **[P1] 新增 PREPARED 收口记录撤销/回滚补偿指令 (GM-03)**：引入 `continuity closure abort`，防止收口崩溃导致 Work/Run 永久锁定。
4. **[P1] 修复 `caller_agent()` 空字符串判为最高权限人类的 Fail-Open 漏洞 (GM-07)**：未匹配到合法 agent 环境变量时判定为 `"unknown"`，写命令严格拒跑，封堵 Trae 任意删库清工位隐患。
5. **[P1] 修复 `protected_files.py:115` 异常时直接放行的 Fail-Open 漏洞 (GM-08)**：遇 Git 或 I/O 异常时强制抛出 `SystemExit(1)`，捍卫受保护文件修改门禁。
6. **[P1] 补齐受保护文件清单中的 `docs/handover/*` 与 `.agents/skills.json` (GM-06)**：防止弱模型在执行其他任务时静默篡改核心规矩文件与技能注册表。
7. **[P1] 移除 GitHub Actions CI `windows-extra` 的 `continue-on-error: true` (GM-05)**：修复 Windows 平台 E2E 与 QML 崩溃测试，停止在云端给未通过测试的代码亮绿灯。
8. **[P1] 本地 `pre-commit` 补齐基础语法扫描 (GM-04)**：增加 `ruff check` 与快速单测拦截，杜绝低级语法错误与挤牙膏式半成品外溢。
9. **[P1] 消除 `AGENTS.md` 编码规范与 `encoding_check.py` 的规则冲突 (GM-10)**：明确统一字符替换准则，避免开发者与 Agent 在合法处理编码时被自研门禁死锁。
10. **[P2] 修复 Windows 下 `test_audit_pr.py` 硬编码 Unix PATH 缺陷 (GM-15)**：确保独立审计测试脚本在 Windows 原生开发机上能够 100% 绿灯跑通。
