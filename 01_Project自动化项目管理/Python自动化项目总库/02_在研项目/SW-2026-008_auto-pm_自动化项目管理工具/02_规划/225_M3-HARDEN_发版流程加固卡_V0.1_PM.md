# M3-HARDEN 发版流程加固卡（草案 V0.1）

> 卡片编号：`CARD-SW008-M3-HARDEN V0.1`
> 状态：`DRAFT / 只起草不实施 / 待独立审计 / 待用户批准`；计划 2026-11-07（周五）由本机 Claude 在隔离工位执行
> 隔离基线：`7dfff27bf0ecfdb7a7f1680085d733a0931aedd6`（`main`，#556 的合并提交，发版 7.2 全部入库之后）
> 路径根：`.`
> 档次：核心档
> 安全回路: 否

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。时间均为亚利桑那时间（MST）。本卡只改验证与工具，不改业务逻辑；每一项都要有机器可判的验收（pytest 用例或退出码），不靠口头保证。

## 1. 为什么：发版 7.2（2026-11-04 夜～11-05）暴露的问题

| # | 事实 | 后果 | 本卡哪一项 |
|---|---|---|---|
| 1 | 门禁用的是旧启动器，延长看护只有 +2 小时（总 5 小时）；门禁跑了 4 小时 57 分，收口窗口只剩 3 分钟；会话夜里重启，没人收口，租约 02:24 过期 | 要用户本人在独立 PowerShell 签“接受风险”才能接管 Run，收口因此推迟到早上 | A、⑥ |
| 2 | 产品里的 `scripts/long_gate.py` 本来就在进程内续租并带 13 小时持有上限，但发版工具链没有用它 | 同上 | A |
| 3 | `long_gate.py` 拒绝文案含 U+2212，在中文 Windows 的 GBK 管道里 `print(refusal)` 抛 `UnicodeEncodeError`（第 1106 行） | 退出码 1 而不是预期的 6/7 | ① |
| 4 | `tests/e2e/test_long_gate.py` 两个用例对时序敏感：冻结点上连跑 30 轮，8 轮失败，失败成簇；CI 上另有 `KeyError: 'child_pid'` | 门禁 rest 组有约 27% 的假红风险，按卡规矩不能原地重跑 | ②、③ |
| 5 | 发版门禁的状态写入工具 `gate_status.py` 对空退出码参数抛 `ValueError: int('')`，被 `\|\| true` 吞掉 | 阶段 RUNNING 状态文件一直写不出来 | ④ |
| 6 | 发版记录入库后，控制根上留着未入库的发布目录和被改过的指针，和合进来的版本撞车，`git merge --ff-only` 会被拦；用户手工 8 条命令才快进 | 每次发版都要重复 | B |
| 7 | 发版记录 PR 要列 590 个路径，PR 描述有 65,536 字符上限装不下；路径又因 `core.quotePath` 被转成八进制转义，门禁按原串比对会红 | 多出一张卡和一次返工 | C |
| 8 | 自动模式对“跑部署脚本”“异地备份推送”判为危险，拦截后只能让用户在自己的终端跑 | 每次切换都要人工接力 | D |
| 9 | 用户硬要求：工位只能由收工脚本删除；本卡把它变成机械护栏，而不是靠自觉 | — | ⑤ |

## 2. 做什么（九项，按这个顺序做）

### 阶段 1：缺陷（先做，小而独立）
**① `long_gate.py` 的输出编码。** 所有打印到标准输出的拒绝与状态文案，在编码失败时降级（`errors="replace"`，或把输出流重配置为 UTF-8）；不改任何判据、退出码映射。验收：新增用例在 `PYTHONIOENCODING=gbk` 的子进程里触发“拒绝”分支（内存预检拒绝或租约拒绝），退出码等于 `EXIT_CODES["REFUSED"]`，标准错误里没有 `UnicodeEncodeError`。

**②③ 两个时序敏感用例。** `test_renewal_failure_mid_run_is_a_final_hard_stop` 与 `test_runner_killed_mid_step_resumes_only_the_unfinished_step`：(a) 子进程统一带 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`（根因之一是中文 Windows 的 GBK 管道，`_run(cfg, "run")` 在“拒绝”后因打印崩溃而退出码为 1）；(b) 读 `long_gate_state.json` 里的 `child_pid` 之前改为轮询等待该键出现（CI 的 `KeyError: 'child_pid'` 是在状态文件还没写入该步骤时读取），并把 `_wait_for` 的默认等待放宽到能覆盖慢机；(c) 失败时把 `long_gate_state.json` 与子进程输出附在断言信息里，下次能直接看到原因（这次探测只留了最后 15 行，没法判断是卡住还是孤儿进程）。验收：在冻结点同样的机器上，隔离连跑 3 个用例 × 30 轮，**0 失败**；并在人为加压（同时跑一个 CPU 空转进程）下再跑 10 轮 0 失败。不改产品代码的判据。

**④ 状态写入工具。** 把发版门禁的 `gate_status.py` 收进产品：新增 `scripts/gate_status.py`（逻辑同现有工具，退出码参数为空串按“无退出码”处理，不抛错），带单测；用法行不变（`<目录> <阶段> <RUNNING|PASS|FAIL|SKIPPED> [退出码]`）。发版工具生成器（每张发版卡的 `derive_*.py`）改为引用它，不再各抄一份。验收：新增用例覆盖 `RUNNING` 无退出码、空串、数字、非数字（后者报清楚的错）四种调用，阶段 RUNNING 状态文件被写出。

### 阶段 2：机械护栏
**⑤ 删除工位的机械护栏（用户硬要求）。** 两层：
1. 产品层：`worktree close` / `worktree sweep`（`agent_worktree_service.py`）是**唯一**允许删除工位的路径，并且只删同时满足下面全部条件的工位，其余一律拒绝并说明原因：登记为 agent 用 `worktree open` 建的（登记记录里有）、工作树干净（含未跟踪文件）、所有提交已推送、路径本身及路径上没有符号链接或联接点（沿用 `_require_inside` 的检查并补测试）。先核对现有实现已满足哪些，缺哪条补哪条，每条条件至少一个“拒绝”的反例用例。发版收口脚本（每张卡生成的 `*_close_worktree.sh`）改为调用 `main.py worktree close claude`（claude 换成对应 agent 名），不再直接 `git worktree remove`。
2. 会话层：新增 Claude Code PreToolUse 钩子 `.claude/hooks/guard-worktree-delete.py`，在 `.claude/settings.json` 里注册（需要用户亲口，见 §6）。钩子读取待执行的 Bash/PowerShell 命令，凡命令里同时出现删除动词（`rm`、`rmdir`、`del`、`rd`、`Remove-Item`、`git worktree remove`、`git worktree prune`、`shutil.rmtree`、`git clean`）和工位目录（`.auto-pm/worktrees` 或 `git worktree list` 登记的任何路径）就拒绝，除非命令本身是 `main.py worktree close|sweep`。验收：钩子的 pytest 用例覆盖上述每个动词各一条“拒绝”、`main.py worktree close` 一条“放行”、无关路径一条“放行”，并包含引号、反斜杠、`&&` 拼接、`bash -c` 嵌套的绕过写法各一条（拒绝）。
   说明：钩子只能看到命令字符串，看不到脚本文件内部，所以第 1 层的“脚本改调 `worktree close`”是必须的。

### 阶段 3：发版流程
**A、⑥ 长门禁走产品自带的 `long_gate.py`，并带收口守护。** 发版工具链改用 `scripts/long_gate.py launch`（它在进程内续租，延长看护是 10 小时，总持有 13 小时），不再用旧启动器。收口守护（⑥）：(a) 起跑前根据预计时长与剩余持有上限算出余量，余量小于“预计收口时间 + 30 分钟”就拒绝起跑并说明；(b) 门禁最后一步之后由 `long_gate.py` 自己（脱离 AI 会话）用配置里的收口命令走完“收口”，收口命令失败或超时则保留现场并写明；(c) 门禁结束时若租约剩余不足 40 分钟，状态文件里写 `CLOSE_WINDOW_LOW` 并停续租前先把租约延到足够收口（仍只做一次延长，且仍需用户的 `HOLD_REF`）。验收：新增用例在假时钟下覆盖“余量不足拒绝起跑”“门禁结束后自动收口成功”“收口命令失败保留现场”三条；不改判据、不放宽任何硬停止。

**B、控制根同步命令。** 新增 `scripts/control_root_ff.py`（只用标准库与 git，不依赖驾驶舱运行时）：`--plan` 只读，打印当前 HEAD、与 `origin/main` 的距离、与更新相撞的本地改动与未跟踪文件，并逐项判断“是否与 main 上的版本字节相同”；`--apply` 仅当所有相撞项都字节相同时才执行：备份、把未入库文件移到 `.auto-pm/archive/<时间戳>/`、让相撞的已跟踪文件回到 git 版本（备份在先）、`git merge --ff-only origin/main`、核对 HEAD 与未入库文件已被 git 写回，并写出 `UNDO.sh`/`UNDO.ps1`。**永不**使用 stash、reset、clean、删除；遇到任何与 main 字节不同的相撞项直接拒绝并列出来；用户自己的未提交文件（与更新不相撞的）一律不动。验收：在一次性临时仓库里的用例覆盖“全部字节相同 → 成功并可撤销”“有一个字节不同 → 拒绝且零改动”“用户文件不相撞 → 原样保留”三条。

**C、发版记录 PR 的路径表卡。** 新增 `scripts/release_record_card.py`：给定发布 ID 与基线提交，用 `git -c core.quotePath=false ls-tree -r --name-only` 取路径（UTF-8 原文、不带引号），生成路径表卡（`> 档次`、`> 安全回路` 头齐全，表格式与现有卡一致），并生成只含“任务卡: 路径”的 PR 描述；当路径数乘以平均长度超过 60,000 字符时必须走路径表卡，不再尝试把路径写进 PR 描述。验收：用例覆盖含中文路径的目录（不得出现 `\3xx` 八进制转义或引号）、超过上限的 600 个路径（描述长度小于 65,536）、生成的卡能通过 `implementation-card precheck`。

**D、自动模式的固定入口。** 只给运行**固定入口**的允许规则，由用户自己加到 `.claude/settings.local.json`（本卡只给文本，不改这个文件；见 §5）。规则文本（`permissions.allow`）：
- `Bash(.venv/Scripts/python.exe -B scripts/long_gate.py launch*)`
- `Bash(.venv/Scripts/python.exe -B scripts/long_gate.py status*)`
- `Bash(.venv/Scripts/python.exe -B scripts/control_root_ff.py --plan*)`
- `Bash(.venv/Scripts/python.exe -B scripts/release_record_card.py*)`
- `Bash(*main.py* pm state-backup push*)`（已有）
**不包含任何删除类规则**：没有 `rm`、`rmdir`、`del`、`Remove-Item`、`git worktree remove`、`git worktree prune`、`git clean`、`git reset`、`git checkout --`、`git stash`、`git branch -D`、`git push --force`，也不放行 `control_root_ff.py --apply`（它会移动文件，保持每次由用户点头）。已有的拒绝规则（`.claude/settings.json` 的 `deny` 列表）一条不动。说明：自动模式是模型判断，允许规则能降低被拦的概率，不能保证；被拦时仍然是给用户一行命令自己跑。

## 3. 精确 Owned Paths

| 路径 | 基线状态 | 用途 |
|---|---|---|
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/scripts/long_gate.py` | 存在 | ①、A、⑥ |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/e2e/test_long_gate.py` | 存在 | ①②③、A、⑥ 的用例 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/scripts/gate_status.py` | 计划新增 | ④ |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/infrastructure/test_gate_status.py` | 计划新增 | ④ 的用例 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/application/core/agent_worktree_service.py` | 存在 | ⑤ 产品层 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_agent_worktree_service.py` | 存在 | ⑤ 产品层的用例 |
| `.claude/hooks/guard-worktree-delete.py` | 计划新增 | ⑤ 会话层钩子 |
| `.claude/settings.json` | 存在 | ⑤ 注册钩子（需用户亲口，见 §6；`deny` 列表不动） |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/infrastructure/test_guard_worktree_delete_hook.py` | 计划新增 | ⑤ 钩子的用例 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/scripts/control_root_ff.py` | 计划新增 | B |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/infrastructure/test_control_root_ff.py` | 计划新增 | B 的用例 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/scripts/release_record_card.py` | 计划新增 | C |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/infrastructure/test_release_record_card.py` | 计划新增 | C 的用例 |

出现第 14 条候选变更即停止。`scripts/` 下的文件属于发布载荷（`scripts` 被发版载荷带走），所以本卡合并后要走一次发版才在运行的驾驶舱里生效；本卡不切换发布版本。

## 4. 不做什么
- 不改 `.claude/settings.json` 里已有的 `deny` 列表，不加任何放行规则（放行规则只给文本，由用户自己加）。
- 不实现“删除类”能力的任何放宽；不碰 `.trae`、`.cursor`、`.agent`、`AGENTS.md`。
- 不改发布目录、清单、指针；不切换版本；不改账本；不直接 SQL。
- 不改 `long_gate.py` 的任何判据或硬停止条件（只补余量守护与收口步骤）。
- 不重写旧发版卡的工具（它们留在 `.auto-pm/reports/`，只在下一次发版的生成器里改为引用本卡的产品脚本）。
- 不做 `pm state-backup push` 的任何改动。

## 5. 验收与门禁
1. `pytest` 针对每项新增/改动的用例全绿；整组 `tests/e2e/test_long_gate.py` 在冻结点同机连跑 3 个时序用例 × 30 轮 0 失败（②③）。
2. `ruff check`、`mypy --platform win32 auto_pm` 干净；`main.py doc check` 退出码 0；`git diff --check` 无问题。
3. 钩子的拒绝/放行矩阵（⑤）与 `control_root_ff.py` 三个用例（B）在一次性临时仓库里跑，不碰真实工作区；`--apply` 只在临时仓库里演练，真实控制根只跑 `--plan`。
4. 真实 pre-commit 钩子对本卡全部提交退出 0（先在演练工位干跑）；门禁按正常发版卡的合同走一次完整门禁，没有新增例外或容忍规则。
5. 用户自己加允许规则（D）后，让 Claude 在真实环境里各跑一次那几个固定入口（只读的 `--plan`、`status`），确认不再被自动模式拦；被拦就如实记下，不算本卡失败。

## 6. 依赖、风险与需要用户的亲口
- ⑤ 的钩子要改 `.claude/settings.json`：项目的 `deny` 列表禁止 agent 改 `.claude/**`，所以这一项要**用户亲口同意改这个文件**，才能执行；没有这句话，⑤ 的会话层不做，产品层照做。
- 钩子只管 Claude Code 会话里的命令字符串；用户自己在终端里的操作不受影响，且 `main.py worktree close|sweep` 仍可用。
- B 的 `--apply` 会移动用户机器上的文件：每次只在用户当场说“同步”之后运行，且先让用户看 `--plan`。
- A 要改发版工具链的生成器，它们不在 Git 里（在 `.auto-pm/reports/`）；本卡只提供产品脚本和用法，生成器的更新放进下一张发版卡里，不在本卡 owned paths。

## 7. 批准
**待用户亲口批准**：批准消息里写出本卡（定稿后）SHA-256 的前 12 位；同时说明是否同意改 `.claude/settings.json`（⑤ 会话层）。批准前不开工。
