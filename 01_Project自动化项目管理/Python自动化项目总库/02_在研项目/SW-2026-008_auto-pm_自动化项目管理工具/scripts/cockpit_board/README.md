# 驾驶舱总控屏（scripts/cockpit_board）：给接手改界面的 agent 读

这是用户本人用的桌面窗口（PySide6，普通控件，不是 QML）。它是**命令行的另一层皮**：窗口上的每个按钮只做一件事，
就是在后台调用同一条 `main.py` 命令，把命令和退出码写进底部的“控制台抽屉”。界面不持有任何治理权，也不绕过
命令行的护栏（租约、批准口令、用户原话凭据、受保护清单）。像 HMI 按钮不绕过 PLC 联锁，只是写同一个点位。

> 状态（2026-11-01，S0 清桩之后）：总控屏目前**只读 + 工程工位**，还不能点“决定”类按钮（批准、开工、验收、收口、搁着/拿回）。
> 这些按钮由后续的 S1 接上，接线前一律灰着。方案原文：`/mnt/project-files/plans/驾驶舱界面_勘测与交付方案_20261101.md`。

## 1. 怎么启动、怎么看

| 做什么 | 命令（在控制根运行） | 说明 |
|---|---|---|
| 用户双击打开 | `00_Infrastructure/auto_pm/environment/双击打开驾驶舱看板.bat` | 找到本目录上一级的 `pm_dashboard_gui.py`，不在 `releases/` 里，不走发布切换 |
| 命令行打开 | `python -B <源码>/scripts/pm_dashboard_gui.py --root <控制根>` | `--no-legacy` 不接老后台；`--no-net` 当离线；`--examples` 叠加示例卡 |
| 云端无屏幕自查（离屏截图） | `QT_QPA_PLATFORM=offscreen python scripts/pm_dashboard_gui.py --root <根> --screenshot <前缀>.png` | 每页存一张 PNG，文件名 = 前缀 + `_页名`。agent 改完界面必须自己截图看一遍 |
| 冒烟（挨页点检） | `QT_QPA_PLATFORM=offscreen python -B scripts/cockpit_board/smoke.py --root <控制根> [--out <截图目录>]`（其余参数同看板，如 `--no-net --no-github`） | 照双击启动的路子开窗口，侧栏每页加工程工位挨个切过去：有报错、`--wait` 秒内没读完、页面一个字都没有，就记“没过”并写原因。退出码 0 全过 / 1 有没过 / 2 窗口没开起来。不点按钮、不写账本；测试 `tests/core/test_cockpit_board_smoke.py` |
| 测试 | `QT_QPA_PLATFORM=offscreen pytest tests/core/test_cockpit_board.py tests/core/test_cockpit_board_widgets.py tests/core/test_pm_dashboard_gui.py tests/core/test_pm_dashboard.py` | 全绿才算数；测试里有按钮白名单、永不加的词、不写工作空间等硬卡点 |

`main.py gui`（不带参数）打开的是**另一套**界面“老板驾驶舱”（QML），`main.py gui --advanced` 是“专业工作台”（QML）。
本目录是总控屏，计划作为唯一主界面，另两套退成高级入口（S3 前不改入口，避免动用户正在用的启动方式）。

## 2. 目录分工（改哪里）

| 文件 | 管什么 | 改它的规矩 |
|---|---|---|
| `theme.py` | 唯一的颜色、字体、间距 | 想改外观**只改这里**，别处不许写颜色字面量（有测试扫） |
| `policy.py` | 按钮白名单、永不加的词、禁用词 | **加按钮先改这里**，再改页面；永远不加：合并、删除、切换发布、代签、绕过钩子、启动 agent |
| `viewmodel.py` | 纯判定：把账本和文件夹读出的 `pm_dashboard.Board` 变成各页要显示的数据 | 无界面代码，可以直接单测 |
| `actions.py` | **整个包里唯一允许起子进程、写文件的地方** | 新动作加在这里，回执（命令 + 退出码）统一用 `Receipt` |
| `widgets/` | 各页的控件：`decisions` 决定页、`home` 今天、`issues` 问题、`projects` 全部项目、`project_page` 项目页六页签、`station` 工程工位、`delivery` GitHub 块、`common` 小零件；骨架 D 的 7 个新页见第 7 节 | 只画，不判定；长文字行用 `common.fill`，行里不要再放弹簧 |
| `shell.py` | 侧栏三组、页面注册表 `PAGES`、路由、范围标记；`page_reads()` 读 `flow/pages.json` | 加一页先在这里登记一行 |
| `readers.py` / `snapshot.py` | 只读命令输出的纯解析 / “上次读取”快照的读取和新鲜度 | 纯函数，不起子进程、不写文件 |
| `flow/` | `commands_map.json` 命令分类、`pages.json` 每页读哪条命令、`spine.json` 脊柱十步、`graphs.json` 流程图 | 改了要过 `tests/core/test_cockpit_board_contracts.py` |
| `app.py` | 主窗口、后台线程、两个开关常量 | 见下 |
| `../pm_dashboard.py` | 只读账本和项目文件夹（先拷到临时目录再 `mode=ro` 读） | 账本只读，绝不写 |
| `../github_collector.py` | 只 GET 的 GitHub 采集（PR、门禁、安全签字、审计） | 读不到就显示“未知”，不显示绿 |

两个开关常量（都在 `app.py`）：

- `LEGACY_ALLOWED = True`：TD-105（Windows 禁写锁，PR #82）已合并。窗口先快读出第一版，再在后台接老驾驶舱后台 `snapshot()` 的措辞（只读，约 20 秒）；只在首次加载和手动“重新读取”时接，10 分钟定时刷新只快读（`auto_reload`）；读不到就退回只读账本数据。
- `DECISION_BUTTONS_WIRED = True`：S1b 已把“决定”页接进主窗口（顶栏“决定”页签，控制器 `decision_controller.py`，按钮↔命令对照表见 `DECISIONS.md`）。工位里的“批准范围 / 开工”亮着，点它们只是带你去“决定”页。改回 `False` 会让它们重新灰着，提示用户去终端运行命令。

## 3. 画面规矩（用户 2026-10-22、10-23 已定，不要改）

1. 没检查就显示“没检查”或“断网未知”，**绝不显示 0 或绿色**（`policy.UNCHECKED_TEXTS`）。
2. 项目经理看板**除决定类按钮外只读**（CHG-SCPT-2026-654 改的规矩，原来是“只读”）：页面上能打字的地方仍只有工程工位第 4 步的业务变更（BC）表单
   （另有“决定”页的批准人一栏和工具页的表单，各由自己的测试清点）。多出来的按钮只有这些：项目详情页的“归档…”或“重新激活…”、“重新检查”、
   “确认归档”或“确认重新激活”（两个决定类按钮，登记在 `decisions.DECISIONS`；前三个只跑不带 `--confirm` 的预演，登记在 `decisions.READ_ONLY_COMMANDS`）；
   全部项目页的“新建项目…”（只跳页）。其余照旧只读。项目的删除、恢复不上看板；`policy.NEVER`、`PM_FORBIDDEN_WORDS` 一个不动。
3. 标签一律纯文本（账本里的字不当富文本解释，不能点开链接）。
4. 用户只有一个人：有 AI 时他是项目经理（看板），自己动手时他是工程师（工程工位）。

## 4. 现有按钮对应的命令（工程工位，已接线）

| 按钮 | 实际运行的命令 | 回执 |
|---|---|---|
| 重新跑 plc check | `python -B main.py -w <人工工位> plc check <项目号>` | 命令 + 退出码，输出进抽屉 |
| plc docs check | `… plc docs check <项目号>` | 同上 |
| docs sync 预览 | `… plc docs sync --dry-run <项目号>` | 预览，不写 |
| 预览 / 写入 02_业务变更记录.md | 无命令：`actions.bc_preview` / `actions.bc_append` | 只往表末追加一行，写前读一遍、写后校验除末行外字节不变；写前必须先预览 |
| 复制、看项目、展开、重新读取等 | 无命令，只读界面操作 | — |
| 推送 manual/ 分支、打开 GitHub 开 PR、提交 | 本版不做，灰着，提示去命令提示符做 | — |
| 批准范围、开工（工位里） | 不运行命令，跳到“决定”页（见 `DECISION_BUTTONS_WIRED`） | — |
| “决定”页的 9 个按钮 | 见 `DECISIONS.md`：每个按钮一条 `main.py pm …` 命令 | 命令 + 退出码 + 原文，失败红条常驻 |
| 新建项目（工具页“项目”页签） | `project create --stack … --name … --auto-id --business-line … [--mode …]`；“只试一次，不写”勾着时带 `--dry-run` | 先“预览命令”再运行；命令 + 退出码 + 原文 |
| 登记（工具页“项目”页签） | `project register <项目号> [--kind …]`；“只试一次，不写”勾着时带 `--dry-run`；从不传 `--status` | 同上；真登记成功后提示“登记表有一处没提交的改动”，看板不提交登记表 |
| 归档…、重新激活…、重新检查（项目详情页） | 预演：`project archive <项目号>` / `project reactivate <项目号>`，不带 `--confirm`，只查不改 | 输出原样摆在“项目状态”一块 |
| 确认归档、确认重新激活（项目详情页，预演通过才出现） | `project archive <项目号> --confirm --approval-evidence-ref …` / `project reactivate <项目号> --confirm --approval-evidence-ref …` | 弹确认框写明整条命令；口令已启用时只在新终端窗口里运行 |

## 5. 决定类按钮对应的命令（S1 已接，对照表以 `DECISIONS.md` 为准；下表是 S0 时整理的全景）

下表是读 `auto_pm/ui/cli/` 源码整理的，参数以各命令的 `--help` 为准。**界面只能调用这些现成命令，不能新造绕过它们的路。**
所有写命令都在控制根运行；输出格式列里“JSON”表示不加任何参数就打印 JSON；退出码 0 成功，非 0 失败，原因在输出的 `reason` 或错误文字里，界面原样显示，不静默。

| 用户想做什么 | 命令 | 输出 | 谁能运行、护栏 |
|---|---|---|---|
| 看今天要我定什么 | `pm orient <项目号> --json`（旧发布版没有就用 `pm resume <项目号> --json`） | JSON | 只读 |
| 看一个项目的四栏卡（在干/等你/搁着/已关） | `pm missions --pid <项目号>` | JSON `pm-missions.v1` | 只读；搁着的卡带 `reason`、`checkpoint_summary`、`stale`（超 7 天） |
| 看等批准的范围卡 / 规划草稿 | `pm pending --project-id <项目号>`、`pm drafts --project-id <项目号>` | JSON | 只读（注意：这两条用 `--project-id`，`missions` 用 `--pid`） |
| 看收件箱怎么排、每条下一步做什么 | `pm triage <项目号>`（加 `--json` 出 `pm-triage.v1`） | 文字 / JSON | 只读；开着的卡 + 等你决定的条目 + 已确认条目按建议顺序排好，每条写明下一步和命令骨架；不确认、不转计划、不切焦点 |
| 收件箱：入箱、看、确认、驳回 | `pm inbox add / list / show / confirm / reject` | JSON | 入箱不授权任何工作；确认/驳回要 `--approver`、`--ticket-hash`、`--approval-evidence-ref` |
| 批准范围 | `pm approve --request-id <请求号> --plan-hash <哈希>`（带全参数时七栏都要带） | JSON 范围卡 | **已启用批准口令时由用户本人在终端输入口令**，agent 不得代填；开着的卡满 8 张或撞文件要另带 `--admission-release-ref` |
| 确认开工（不启动任何 agent） | `pm confirm-start --mission-id <编号>` | JSON 范围卡 | 控制根；不启动 Codex |
| 质量验证 | `pm verify --mission-id <编号> --lease-wallet` | JSON，退出码 1 = 没验证通过，`reason` 是原因 | IDE 里的 agent 用本 Run 租约跑（约 15 分钟）；用户界面不点它 |
| 最终验收 | `pm accept --mission-id <编号>` | JSON 范围卡 | **已启用批准口令时用户本人在终端输入口令**；未启用时界面“确认验收”按钮可点 |
| 收口 / 重试收口 | `pm close --mission-id <编号>` | JSON，退出码 1 = 没收完，`reason` 是原因 | 只收用户已验收的卡 |
| 搁着 | `pm park --mission-id <编号> --reason … --summary … [--approval-evidence-ref user-confirmation:<用户原话时间或编号>]` | JSON `pm-park.v1` | 带用户原话凭据才进“搁着”，不带只进“等你”；已启用口令时凭据由口令代替 |
| 拿回搁着的卡 | `pm unpark --mission-id <编号> --as <身份> --approval-evidence-ref …` | JSON `pm-unpark.v1`（含 `behind_main`、`overlap_note`） | 拿回哪张只听用户的 |
| 插急活（先搁手上这张再拿起另一张） | `pm switch --pid <项目号> --to <编号> --reason … --summary … --as <身份> --approval-evidence-ref …` | JSON `pm-switch.v1` | 同上；省略 `--to` 只给建议、不执行 |
| 看批准口令是否生效 | `pm approver-pin status --json` | JSON `approver-pin-status.v1`：`state` 为 `enforced` / `not_enabled` / `suspended`，只含批准人名和口令编号，不含口令或校验值 | 只读；设置口令（`pm approver-pin init`）只能用户本人在终端做，界面永远不放这个按钮 |
| 安全区签字 | 现在在 GitHub PR 上写“安全签字 + 提交号” | — | 界面只提醒，不代签 |

界面永远不加的按钮：合并、删除、切换发布、代签、绕过钩子、启动 agent、设置/重置批准口令。

## 6. 给下一个接手的 agent 的提醒

- 改界面前先读本文件和 `/mnt/project-files/plans/驾驶舱总控屏设计_20261022.md`，别凭空重画。
- 改完必须：跑上面“测试”一行、离屏截图自己看一遍（改布局的话）、`ruff check`。
- 新增按钮三步走：`policy.py` 加白名单 → `actions.py` 加动作（或调现成命令）→ 页面里画按钮；缺哪步测试会红。
- 账本、WBS、台账只由账本主机上的主执行写；界面读账本永远只读。

## 6.1 “说真话”的几条口径（批 1，CHG-SCPT-2026-644）

- **旧账**（D-324）：项目下的卡全是 CLOSED / CANCELLED（或没有卡）时，账本一致性检查留下的问题降成提示，项目标“旧账”（提示色），不标“有风险”，也不隐藏；首页“账本对不上”格子分开写“在干 X，旧账 Y”。
- **依据写白话**（D-326）：问题的“依据”一栏不出现账本表名和字段名。
- **卡开着，但下面没有在跑的执行**（D-327 看板侧）：ACTIVE 卡下面的工作项或最近一次执行已结束，不报“执行者失联”，单独提示、谁来办写主执行。账本清理另立单。
- **草稿没有工作项**（D-328，审计裁定②）：卡授权里的批准编号在账本批准记录里查得到、授权没过期，算“已批准，还没开工”，照常进“要你出手”；查不到或过期的只提示“草稿，没有工作项，也没有批准记录”。只读账本副本。
- **同一条收口只计一次**（D-329）：卡已关、收口没走完的只算在“说完成但机器没过”，不再算进“账本对不上”，两格说明互相指到。
- **旧办法关闭的卡**（D-330）：已关但没有收口记录的卡不计数，“说完成但机器没过”的说明里写明另有几张和依据。

## 6.2 “要你出手”分页计数和工具页“入箱”（CHG-SCPT-2026-648）

- **分页和首页同一口径**（D-342）：分页顶上“计入”一块只由首页那份 `HomeVM` 算（`viewmodel.attention_count`）：分页读的每个项目，计入的条目就是首页这个项目卡的 `card.decisions`，逐条一样；首页有件数、分页没读的项目写“另有 N 件在本页没读的 M 个项目里：…”；归不到任何项目的 PR 签字另写一行。三样加起来等于首页的总件数。
- **同一轮**：`app._render` 每次重算首页，紧接着重画分页“计入”块，不等下一轮读取；`pm pending`、`pm inbox list` 读完只重画明细（标“已算进上面的件数，不另计”），项目那一行写明明细是几点读的。首页还没算好时写“首页还没算好，暂不计数”，不写“没有”。
- **工具页“入箱”页签**：拼出 `main.py pm inbox add …`，和终端里敲的一样；先“预览命令”，看过再点“记入收件箱”，表单一改预览作废，一次预览只记一次。请求号按时间生成（`board-<UTC 时间>`），提出者写 `cockpit-board`。“用户原话”一栏看板从不预填、不拷、不给默认值，原样交给命令；取证、备选方案也由人填，缺栏不让预览。记进去是 PROPOSED，确认、驳回照旧在“决定”页。

## 6.3 项目生命周期入口（CHG-SCPT-2026-654）

- **入口在哪**：“全部项目”页顶上“新建项目…”只跳到工具页的“项目”页签；新建、登记在那个页签；归档、重新激活在项目详情页概览的“项目状态”一块。首页不放。删除、恢复不上看板。
- **新建**：必填项目名称和性质。性质不进 `project create`，只带出默认值（`tool_actions.KIND_DEFAULTS`）：设备＝PLC、标准项目、DJ；公共库＝PLC、共享库、DJ；工具＝Python、SW；
  测试＝不给默认，必须自己选技术栈。默认自动编号（`--auto-id` 配 `--business-line`），“高级”里手填编号后改传 `--id`。真建成功后把编号和性质带到登记表单；编号从回执里读不出来就留空，不猜。
- **登记**：项目编号可从“工作区里找到、还没登记的项目”下拉里选（板数据里 `registered` 为假的那些）。看板不提交登记表，也不提示能替你提交。
- **归档、重新激活**：先预演、后确认，细节见 `DECISIONS.md`“项目详情页的两个按钮”。五项检查没有机器可读的输出，看板不另写解析，原样摆出来。
- **发版切换前的降级**：看板不写死版本号，用 `--help` 探测（`decision_controller.probe_lifecycle`）：

  | 探测结果 | 界面 |
  |---|---|
  | 报 `No such command` | “归档…”“重新激活…”灰着，旁边写“本机发布版太旧：没有这条命令（等部署新版本后再看）” |
  | `project register --help` 里没有 `--kind` | 登记表单的“性质”灰着，写“发版切换后可填；现在登记后显示‘未分类’”；拼命令时不传 `--kind` |
  | 探测没读成（超时、起不来等） | 一样灰着，写明没读成的原因，不当成“有这条命令” |
  | 读到了 | 正常可点 |

  `project create` 现役版本就有，不探测。探测结果在这个窗口里记着，点“重新读取”才重探。
- **环境变量**：看板起命令时原样带上环境变量，不删改 `CLAUDECODE`、`AUTO_PM_AGENT`、`CODEX_*`；看板要是 agent 起的，`--confirm` 那一步命令自己会拒绝。

## 7. 骨架页（CHG-SCPT-2026-628 骨架 D）

7 个新页都只读，页面上没有按钮（侧栏按钮除外）。读哪条命令以 `flow/pages.json` 为准，打开那页或点“重新读取”时
在后台线程读（`app.read_page`），读到且读得懂就存一份“上次读取”快照到 `<控制根>/.auto-pm/cache/cockpit_board/`；
没读到时亮快照并写明是几分钟前的。每条命令一块：读取状态（三态标签）→ 要点 → 原文。
这次读到、读懂了、要点也列出来了时，原文收起成一行“原文 N 行已收起”（D-316）；没读到、读不懂、用快照时原文照贴。
PR 与审计页的审计报告写明读了哪些目录（`<控制根>/reviews` 加 `--reviews-dir` 给的），写在别处的报告看板读不到（D-317）。只有对上开着的 PR 的报告列在“当前审计报告”下，每份标来源目录和日期（正文没写日期就用文件修改时间并注明）；其余的只给份数和日期范围，不当作当前审计；目录或文件读不到写“读不到”，不写成“没有”。

| 页 | 侧栏组 | 读什么 | 文件 |
|---|---|---|---|
| 要你出手 | 日常 | 件数取首页同一份数据（见 6.2）；明细对每个项目读 `pm pending --project-id <项目>`、`pm inbox list --project-id <项目>`（读哪些项目见下） | `widgets/attention.py` |
| 任务 | 受管项目 | `pm missions --pid <项目>`、`pm orient <项目> --json` | `widgets/tasks.py` |
| PR 与审计 | 驾驶舱 | 不起命令：用窗口已有的 GitHub 采集（`github_collector.py`） | `widgets/prs.py` |
| 工作树与分支 | 驾驶舱 | `worktree list --json`、`worktree sweep --json --no-fetch`（只列不清） | `widgets/worktrees.py` |
| 发版 | 驾驶舱 | `long-run status` | `widgets/release.py` |
| 脊柱图 | 驾驶舱 | 不起命令：`flow/spine.json` | `widgets/spine.py` |
| 命令与契约 | 驾驶舱 | 不起命令：`flow/commands_map.json` | `widgets/commands.py` |

`<项目>` 取工程工位的默认项目（`--station-project`，默认第一个客户项目）；没有项目时那几条命令不读，写“没读：没有受管项目”。
“要你出手”页例外（CHG-SCPT-2026-639）：读 `app.ask_project_ids` 给的一组项目，包括默认项目、账本里有等批准范围卡或等确认收件箱条目的项目、有开着的卡的项目，最多 12 个。“今天”页的“要你出手”也把这两样算进去：`pm_dashboard.read_pending_asks` 只读账本，口径同 `pm pending` 和 `pm inbox list` 里状态为 PROPOSED 的，有契约测试对照。“决定”页要读的项目也加上有这两样的项目。

身份条“源码”“生效版本”两格：命令行没给 `--source-version`、`--effective-version` 时（bat 不传），启动时自己补。源码取 `actions.source_version()`，即本地 `git rev-parse --short HEAD`，3 秒超时；生效版本取 `00_Infrastructure/auto_pm/active_release.json` 的 `release_id`。取不到显示“—”。

读取状态只有这几种画法（`widgets/common.read_state`）：

| 命令结果 | 标签 | 要点 |
|---|---|---|
| 读到了、读得懂 | 不配标签，写“读到了” | 画 |
| 有输出但不是认得的格式；只有启动提示 | 读不懂 | 不画 |
| 断网 | 断网未知 | 有快照画快照的，并写明几分钟前 |
| 命令不存在（本机发布版太旧）、退出码非 0、超时、没起来、还没读、没项目 | 没检查 | 同上 |

**页面顶上一行总状态**（CHG-SCPT-2026-637，`widgets/common.page_status`）：像 HMI 画面顶上的一行总状态，文案取自 `flow/pages.json` 的 `empty_text`、`error_text`（`shell.page_texts`），不在代码里写死。

| 情况 | 顶上画什么 |
|---|---|
| 有任何一条命令没读到（三态之一，包括用了“上次读取”快照的） | 错态文案，配最差的三态标签：断网未知 > 读不懂 > 没检查 |
| 全部读到，参与判空的命令都“空” | 空态文案，不配标签 |
| 其余 | 不画 |

每页自己写 `is_empty`：任务页看在干、等你、搁着三栏（已关的不算），进门定位不参与判空；要你出手两条明细都不参与判空，只看顶上“计入”（首页口径 0 件才写空态，见 6.2）；
工作树页看工位列表，清理清单不参与判空（“没有可清理的”不代表“没有工位”）；发版页看有没有 STARTING、RUNNING 的长任务。
不参与判空的命令读不到时照样算“没读到”，顶上画错态。PR 与审计页：读到且 0 个 PR 画空态，断网画错态，其他读不到的只写下面那句说明。
脊柱图、命令与契约：数据文件读不懂时那一行用 pages.json 的错态文案；脊柱图的空态（“没有选中的卡”）留给以后“按卡显示进度”，本单不接。

**怎么补一页**：照 `PAGE_TEMPLATE.md` 一步步做（声明命令 → 解析 → 画 → 测试 → 截图）。
