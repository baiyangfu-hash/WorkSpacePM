# 驾驶舱探测 findings（trae, 20261030）

- 开始时间：2026-10-29 18:55 MST；本批更新时间：2026-10-29 19:26 MST（探测进行中）
- 环境：Linux 沙箱 / Ubuntu 24.04 / 发布版 1.3.3-d8f7c8b / Python 3.12.3 (.venv)
- 操作对象：一次性假项目 **ZZ-2026-901**（PROBE-0001 被 ID 格式门禁拒绝，见 F3；ZZ-2026-901 为符合文档格式且明显非真实的替身，不与任何真实项目撞号）
- 命令全文与退出码见 `transcript/`（s00–s15）；每条发现的最短复现见 `repro/`
- 时间均为 MST（UTC-7）；证据里机器时间戳保留 Z

## 发现清单

| 编号 | 探测项 | 严重度 | 现象 | 已复现 | 建议 |
|------|--------|--------|------|--------|------|
| F1 | 环境 | P2 | 全新克隆无 `.venv`；cockpit-entry SKILL 只写 Windows 路径 `.venv\Scripts\python.exe`；Linux 引导脚本存在但藏在 `00_Infrastructure/auto_pm/environment/setup_env.sh`，入口文档未提 | 是 | 入口文档补 Linux 路径与引导脚本 |
| F2 | 环境 | P2 | 沙箱 pip 全局镜像缺锁定版本（aiosqlite==0.22.1），`setup_env.sh` 原样执行 3/5 失败；官方源可装齐 | 是 | 锁定安装对镜像缺口给自检提示 |
| F3 | 登记 | P1 | `project create --dry-run` 与真实校验不一致：dry-run 放行 `PROBE-0001`（exit 0），真实执行被 ID 格式拒绝；ZZ-2026-901 同样 dry-run 过、真实挂 package_name | 是（两次） | dry-run 跑全量真实校验 |
| F6 | 登记 | P1 | package_name 派生死路：中文名/连字符英文名均被拒，`--help` 无覆盖参数，报错不指路；仅下划线名可过 | 是（三次） | 报错写明派生规则；加覆盖参数或自动规范化 |
| F7 | 登记 | P1 | 脚手架生成 `PM_SESSION_ZZ-2026-901.md`，违反 AGENTS.md「PM_SESSION 已退役，不改、不新建」 | 是 | 模板移除 PM_SESSION 文件 |
| F8 | 登记 | P1 | python 项目落点为全新顶层目录 `0100_项目/`，与任务/工作区惯例 `01_Project自动化项目管理/.../02_在研项目/` 不一致 | 是 | 核对 dest-dir 解析约定 |
| F9 | 进门定位 | P0 | `project create` 成功后 `pm resume`/`context resolve` 报「项目未登记到 Workspace Registry」——registry（`SYS-2026-001_WorkspaceGovernance/workspace_registry.json`，6 项）与 project 命令登记（9 项）两本账；新建项目走不了进门第一步 | 是 | create 同步写 registry 或给出登记指引 |
| F10 | 进门定位 | P1 | 相对路径普遍失效：`context resolve --path <存在的相对目录>` 报不存在；`continuity run start --worktree <存在的相对目录>` 同样报不存在；绝对路径任意 CWD 均正常（J9 已定性） | 是（两命令） | 统一以 CWD 解析相对路径 |
| F11 | 版本面 | P2 | `--help` 顶层仍列退役的 `pm-session` 与「pm-workflow 专属」的 `prototype`；doc check DOC-004 版本锁仍含 `PM_SESSION=1.2.4` | 是 | 退役面移除或标注 DECOMMISSIONED |
| F12 | 版本面 | P1 | AGENTS/cockpit-entry 描述的 `pm orient/inbox/plan/approve/verify/accept/close/park/unpark/switch/missions/handoff/takeover/execute/approver-pin` 在 1.3.3 全部不存在（exit 2，s13 全量取证）；Mission 全流程与插急活探测面整体不可执行 | 是（17 条） | 部署指针升级或文档标注最低版本 |
| F13 | 门禁 | P1 | 全新克隆 `.git/hooks/` 仅 `*.sample`；提交门禁钩子未安装（s05 的提交即无门禁通过）；`git-hook install` 存在但无引导执行；`doctor` 不查钩子 | 是 | 环境引导装钩子；doctor 加钩子检查 |
| F14 | Work 创建 | P0 | `continuity work create --pid ZZZ-9999-999`（不存在的项目）**成功**（exit 0）；同参数 `change create` 却正确拒绝（层间不一致） | 是 | Work 层校验项目存在性 |
| F15 | 报错质量 | P1 | 同 work-id/run-id 换幂等键重放 → 裸 `sqlite3.IntegrityError: UNIQUE constraint failed` 堆栈（A5、E5 两处） | 是（两处） | 转成引导性报错（指明已存在与原幂等键） |
| F16 | 审批 | P1 | agent 身份一路充当 `--approver`（change approved + decision create）零阻拦；无批准口令机制（`pm approver-pin` 命令亦不存在） | 是 | 部署口令机制或至少拒绝 agent 身份自批 |
| F17 | Run 状态机 | P0 | run start 后状态**直接 RUNNING**（非文档说的 READY）；且接受工作区外 `/tmp` 工作树（WS-001 声称的拒绝未实现，AGENTS 自认待部署） | 是 | start 落 READY；补工作树位置联锁 |
| F18 | 路径 | P1 | 同 F10 的 run start 实例：`--worktree .auto-pm/worktrees/trae-probe-w1` 目录存在仍报 "Directory does not exist"（归入 F10 家族） | 是 | 同 F10 |
| F19 | Run 状态机 | P1 | `RUNNING → CANCELLED` 非法——一次性 Run 无取消出口；只能走 VERIFYING→FAILED 绕（语义绕行） | 是 | RUNNING 允许 →CANCELLED |
| F20 | scope 匹配 | P1 | Work scope 用 `dir/**` glob 时，run start `--owned <该目录下单文件>` 报「owned_paths 超出 Work scope」——`**` 匹配未实现且报错不解释规则；glob scope 实际不可用 | 是 | 实现 glob 语义或禁用并在报错里说明 |
| F21 | 租约 | P0 | 租约过期后：transition ✗、lease renew ✗、checkpoint ✗、handoff（需 checkpoint，checkpoint 又需活租约）✗、同 run-id 重建 → sqlite 崩溃、reclaim/settle-expired/takeover 命令不存在——**过期 Run 无任何合法下一步，永久死锁**（s10 全量取证） | 是 | 提供 reclaim/settle 类命令或允许 owner 原 token 重生租约 |
| F22 | 互斥 | P1 | 同一 Work 并存两个 Run（R-PROBE-001 死租约 + R-PROBE-002 RUNNING）无互斥——两个 agent 可同时持有同一 Work 的 Run | 是 | Work 层面活跃 Run 互斥 |
| F23 | 可观测性 | P2 | continuity 无任何只读查询命令（work/run/lease 无 list/show/orient）；台账状态只能靠命令回显或直接翻 `.auto-pm/continuity.db` | 是 | 补只读 list/show |
| F24 | 文档矛盾 | P1 | cockpit-entry 明文步骤「run start 后 `continuity run transition --to RUNNING`」在 1.3.3 必然报错（start 已 RUNNING，RUNNING→RUNNING 非法，G1 取证） | 是 | 修文档或改状态机 |
| F25 | Work 联动 | P1 | work transition 不带 owner/租约参数（任何人可推任何 Work）；Run 全部 SUCCEEDED 后 Work 才 IN_PROGRESS→ACCEPTED→CLOSED 一路放行；ACCEPTED 无验收证据 | 是 | Work 转换加身份/租约；与 Run 状态联动 |
| F26 | 口径注记 | P2 | `ledger reconcile` 与 `change verify --ledger-check` 对 continuity.db 的 Work/Run 零感知（两边均 0 差异）——台账与 continuity 是两本互不知晓的账 | 是 | 明确两者口径关系并文档化 |
| F27 | 声明范围 | P1 | 受管工作树存在 owned 之外、未声明的脏文件（README.md）→ run start 照样放行 RUNNING（help 声称 "independently observing ... owned-path dirtiness" 未覆盖范围外脏文件） | 是 | start 时对范围外脏文件警告或拒绝 |
| F28 | 声明范围 | P1 | `--declared-dirty README.md`（范围外文件）报「declared_dirty_paths 超出 owned_paths」——声明机制只能声明 owned 之内，与 F27 合并 = 范围外改动既不可声明也不可观测（语义倒置） | 是 | declared-dirty 应允许 owned 之外并在 verify 拦截 |
| F29 | 规则自洽 | P1 | `python check` 门禁强制「PM_SESSION 文件 ✓」（J3），治理却宣布 PM_SESSION 退役且禁止新建（F7 生成器还在建）——按治理删除会致门禁红：三处互相矛盾（生成器建 / 门禁查 / 治理禁） | 是 | 三处对齐到同一决定 |

撤销/更正：原 F4（resume 报错 exit 0）撤销——管道掩盖退出码，复测 exit=1 行为正确。原「Linux 无引导脚本」更正入 F1。

## 探测1 状态表：Run（lease 守护下）

| 状态 | 到达 | 实测合法下一步 | 死格 |
|------|------|----------------|------|
| RUNNING（start 直达） | run start | →VERIFYING ✓ →BLOCKED ✓；→RUNNING ✗ →SUCCEEDED ✗ →CANCELLED ✗ | — |
| READY | 无命令可达 | — | **READY 不可达（F17）** |
| BLOCKED | RUNNING→ | →RUNNING ✓ | — |
| VERIFYING | RUNNING→ | →RUNNING ✓ →SUCCEEDED ✓ →FAILED ✓ | — |
| SUCCEEDED / FAILED | VERIFYING→ | 任何 transition ✗（终态锁定 ✓） | 正常 |
| 租约过期（RUNNING/VERIFYING 中） | 60s 后 | transition ✗ renew ✗ checkpoint ✗ handoff ✗ 重建→崩溃 settle/reclaim/takeover 无此命令 | **全死（F21）** |

Work：PLANNED→(authorize)→READY→IN_PROGRESS→VERIFYING→ACCEPTED→CLOSED 全通但无身份校验；READY→CANCELLED ✓；CLOSED 锁定 ✓。

## 探测6 错误信息质量打分（抽样）

| 场景 | 证据 | 照报错能做下一步？ |
|------|------|--------------------|
| click 缺参/范围错 | A1、D2' | 能（列出可选值/范围） |
| change 非法流转 | B4、B6 | 能（列出合法下一态） |
| scope/declared 超出 | C3、I3 | 能（指出谁超出；但规则不解释，见 F20/F28） |
| decision 依赖未批 CHG | B7 | 能（说明当前状态） |
| lease 过期/不匹配 | E1、D5 | 半能（说明原因；无出路——出路确实不存在，F21） |
| 同 id 重复 | A5、E5 | **误导**（裸 sqlite 栈） |
| 相对路径存在却报不存在 | F10/F18、J8 | **误导** |
| 不存在项目 | B1（change 能）/ A2（work 不拦） | 一能一漏 |
| pm * 死路 | s13 | 不能（只给 Usage） |
| git-hook pre-commit 手动跑 | J7 | 能过但零输出（不可观测） |

## 探测7 Linux/Windows 差异（只记录）

- 入口文档仅 Windows 路径；`.sh` 引导存在但未载入文档（F1）。
- `pm-as-trae.ps1` 为 PowerShell，Linux 无等价 wrapper；本探测用 `AUTO_PM_AGENT=trae:cn` 前缀等价执行。
- 相对路径失效（F10/F18）在 Linux 实测复现；Windows 行为未测。
- 源码存在 `_read_text`（`errors=replace` 约定，workspace_context_service.py），差异场景未触发，未复现。
- 模板生成中文目录（`04_监控/01_变更管理/...`）在 Linux 正常。

## 探测面进度

- [x] 环境（F1/F2）
- [x] 登记假项目（F3/F6/F7/F8/F9/F10）
- [x] 租约与 Run 状态机（F14–F25，状态表见上；READY 不可达；过期=死锁）
- [x] Mission 全流程（受 F12 限制：17 条命令全死路取证；change/decision/continuity 链路正测通过）
- [x] 插急活（park/unpark/switch/missions 均不存在——并入 F12）
- [x] 受保护文件与改动声明（F27/F28）
- [x] 门禁口径对照（F13/F26/F29；J1–J10）
- [x] 错误信息质量（打分表见上）
- [x] Linux/Windows 差异（见上）

## 结束时填写（尚未结束）

- 结束时间：-
- 发现计数：P0 x / P1 x / P2 x
- 未做探测项：-
- 总命令数：-
