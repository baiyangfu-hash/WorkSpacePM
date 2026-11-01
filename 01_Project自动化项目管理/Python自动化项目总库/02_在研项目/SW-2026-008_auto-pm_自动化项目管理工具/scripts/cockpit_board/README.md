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
| `widgets/` | 各页的控件：`home` 今天、`issues` 问题、`projects` 全部项目、`project_page` 项目页六页签、`station` 工程工位、`delivery` GitHub 块、`common` 小零件 | 只画，不判定；长文字行用 `common.fill`，行里不要再放弹簧 |
| `app.py` | 主窗口、后台线程、两个开关常量 | 见下 |
| `../pm_dashboard.py` | 只读账本和项目文件夹（先拷到临时目录再 `mode=ro` 读） | 账本只读，绝不写 |
| `../github_collector.py` | 只 GET 的 GitHub 采集（PR、门禁、安全签字、审计） | 读不到就显示“未知”，不显示绿 |

两个开关常量（都在 `app.py`）：

- `LEGACY_ALLOWED = True`：TD-105（Windows 禁写锁，PR #82）已合并。窗口先快读出第一版，再在后台接老驾驶舱后台 `snapshot()` 的措辞（只读，约 20 秒）；读不到就退回只读账本数据。
- `DECISION_BUTTONS_WIRED = False`：缺口⑨（批准口令防冒签）已合并，但界面里的“批准范围 / 开工”还没接上口令弹窗和同一条命令，所以仍灰着，灰着时提示用户去终端运行 `main.py pm approve` / `pm confirm-start`。S1 接线并通过测试后才改成 `True`。**不要为了让按钮亮起来而改成 `True`。**

## 3. 画面规矩（用户 2026-10-22、10-23 已定，不要改）

1. 没检查就显示“没检查”或“断网未知”，**绝不显示 0 或绿色**（`policy.UNCHECKED_TEXTS`）。
2. 项目经理看板只读：页面上能打字的地方只有工程工位第 4 步的业务变更（BC）表单。
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
| 批准范围、开工 | 灰着（见 `DECISION_BUTTONS_WIRED`） | — |

## 5. 决定类按钮对应的命令（S1 要接的“按钮 ↔ 命令”清单）

下表是读 `auto_pm/ui/cli/` 源码整理的，参数以各命令的 `--help` 为准。**界面只能调用这些现成命令，不能新造绕过它们的路。**
所有写命令都在控制根运行；输出格式列里“JSON”表示不加任何参数就打印 JSON；退出码 0 成功，非 0 失败，原因在输出的 `reason` 或错误文字里，界面原样显示，不静默。

| 用户想做什么 | 命令 | 输出 | 谁能运行、护栏 |
|---|---|---|---|
| 看今天要我定什么 | `pm orient <项目号> --json`（旧发布版没有就用 `pm resume <项目号> --json`） | JSON | 只读 |
| 看一个项目的四栏卡（在干/等你/搁着/已关） | `pm missions --pid <项目号>` | JSON `pm-missions.v1` | 只读；搁着的卡带 `reason`、`checkpoint_summary`、`stale`（超 7 天） |
| 看等批准的范围卡 / 规划草稿 | `pm pending --project-id <项目号>`、`pm drafts --project-id <项目号>` | JSON | 只读（注意：这两条用 `--project-id`，`missions` 用 `--pid`） |
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
