# “决定”页：按钮 ↔ 命令对照表

> 单一真源是 `decisions.py` 里的 `DECISIONS`。本表给人和 Trae 读；`tests/core/test_cockpit_decisions.py`
> 会核对：每个按钮、每条命令都在本表里出现，且命令真的存在于 `main.py` 的命令树、选项名没写错。

**原则：界面是命令行的另一层皮。** 按钮只拼一条 `main.py pm …` 命令，在控制根后台运行，
命令和退出码原样进页面下方的记录。门禁、租约、受保护路径、批准口令、agent 标记全由命令自己判，
界面不替它放行，也不绕过。所以下表“出现在什么状态”只是方便用户看，不是安全边界。
唯一多出来的一道是“只许你本人点”（M8 的 8.1）：除“确认开工”“收口”外，其余按钮看板进程自己带 AI 标记时灰着、也不运行，见下面“只许你本人点”一节。

## 怎么接进主窗口

`app.py` 顶栏有“决定”页签（`goto("decisions")`）；打开页签时 `_refresh_decisions()` 才去读口令状态、待批准范围卡和收件箱
（每个项目 2 条只读命令，最多 `DECISION_PROJECT_LIMIT` 个项目：有开着的卡的项目加今天页最热的几个），
10 分钟定时刷新不去读。命令成功后窗口重读账本。工位里的“批准范围 / 开工”只是带你来这一页。

## 九个按钮

| 按钮 | 作用对象 | 出现在 | 命令（`main.py` 之后） | 要用户填 | 口令生效时 |
|---|---|---|---|---|---|
| 批准范围 | 待批准范围卡（`pm pending` 读出） | 范围卡 | `pm approve --request-id R --plan-hash H --approver A --approval-evidence-ref E` | 撞车放行（可空） | 不传 A、E；命令在终端问口令 |
| 确认开工 | 一张卡 | 草稿、等批准 | `pm confirm-start --mission-id M` | — | 不问口令 |
| 确认验收 | 一张卡 | 等验收 | `pm accept --mission-id M` | — | 命令在终端问口令 |
| 收口 | 一张卡 | 已验收（含“重试同步”） | `pm close --mission-id M` | — | 不问口令 |
| 搁着 | 一张卡 | 在干 | `pm park --mission-id M --reason … --summary … --approval-evidence-ref E` | 原因、断点 | 命令在终端问口令 |
| 拿回 | 一张卡 | 搁着、受阻 | `pm unpark --mission-id M --as 谁 --approval-evidence-ref E` | 谁来接着干 | 命令在终端问口令 |
| 插急活 | 一张卡（要改干的那张） | 搁着、草稿、等批准（同项目有“在干”的卡时） | `pm switch --pid P --to M --reason … --summary … --as 谁 --approval-evidence-ref E` | 原因、断点、谁来干 | 命令在终端问口令 |
| 确认入箱 | 收件箱条目（`pm inbox list` 读出） | 收件箱 | `pm inbox confirm 条目 --ticket-hash T --approver A --approval-evidence-ref E` | 备注（可空） | 同上 |
| 驳回入箱 | 收件箱条目 | 收件箱 | `pm inbox reject 条目 --ticket-hash T --approver A --approval-evidence-ref E --note …` | 驳回理由 | 同上 |

读状态用的只读命令：`pm approver-pin status`（口令是否生效）、`pm pending --project-id P`、`pm inbox list --project-id P`。

## 变更单的两个按钮（M8 的 8.1）

也在“决定”页上，排在最前面一栏“变更单”。变更单不另起命令去读：看板读账本时已经把每个项目的变更单读进来了（`pm_dashboard.read_change_orders`，状态取变更单文件 3.4 节的原文）。

| 按钮 | 作用对象 | 出现在 | 命令（`main.py` 之后） | 要用户填 | 口令生效时 |
|---|---|---|---|---|---|
| 批准变更单 | 一张变更单 | 审核中（`under_review`） | `change transition 单号 --to approved --pid P --approver A --approval-evidence-ref E` | 批准意见（可空，加 `--comment`） | 只有“在终端窗口里运行”，命令在终端问口令 |
| 推到完成 | 一张变更单 | 验收中（`accepting`） | `change transition 单号 --to completed --pid P --approver A --approval-evidence-ref E --verification-conclusion …` | 验证结论（先填好“全部通过”，可改） | 不问口令 |

- **一个按钮只推一步。** `change transition` 一次只能走状态流里的一步。草稿、已提交的单还没送到“审核中”，已批准、实施中、待验收的单还没走到“验收中”：
  这些单不出按钮，页面写一行“另有 N 张……”，中间几步仍由 AI 用同一条命令推。
- **只许你本人打开的看板点**，见下一节。
- “推到完成”这一步命令本身不判 AI 标记，靠的就是下一节这道。
- “推到完成”不传 `--allow-partial-verification`：有没过的验证项就让命令拒绝，原文留在记录里。

## 只许你本人点（M8 的 8.1）

**对你的影响：你自己双击 bat 打开的看板，用起来和以前一样；AI 会话拉起来的看板，这些按钮点不了。**

- **哪些按钮**：登记了 `human_only` 的，共 11 个：批准范围、确认验收、搁着、拿回、插急活、确认入箱、驳回入箱、确认归档、确认重新激活、批准变更单、推到完成。
  也就是所有要你原话（`user_words`）或要口令（`pin`）的按钮，测试按这个口径清点。只有“确认开工”“收口”不在里面：这两步 AI 本来就可以做（cockpit-entry 第 6、8 步）。
- **看板靠什么判断是不是你**：只看看板这个进程的环境变量里有没有 AI 标记。名单直接取主程序的 `agent_markers`（`AUTO_PM_AGENT`、`CLAUDECODE`、`CLAUDE_CODE_ENTRYPOINT`、
  `CODEX_SANDBOX`、`CODEX_SANDBOX_NETWORK_DISABLED`、`CODEX_THREAD_ID`、`AI_AGENT`），和命令判的是同一份。你在资源管理器里双击 bat，进程是从桌面起的，这些变量都没有，按钮是亮的；
  Claude Code、Codex 这类 agent 拉起的子进程会继承它们的标记，按钮就灰。**这是环境变量自报，不是身份认证**：故意把标记清掉再起看板的 AI 拦不住（同“凭据 E 从哪来”的已知缺口）。
- **认不出时**：找不到主程序（看板被单独拷走了）就读不到名单，按“不开放”处理，按钮灰着并写“请用控制根里的 bat 打开看板”。
  用 bat 打开时 `actions.board_agent_markers` 会先把主程序所在的目录放进 `sys.path`，所以不会因为先后顺序落进这一档；测试照 bat 的样子起一个新进程核过。
- **拦在哪**：卡上的按钮灰着、旁边写原因；确认框的确认键灰着（项目详情页的“确认归档”“确认重新激活”也是）；控制器运行前再查一遍，绕过按钮直接调也不运行，记录里写“(未运行)”。
- **为什么看板要自己拦**：命令对“带 AI 标记、又带一条格式对的凭据”是放行的（用户 2026-10-31 定的 A），而凭据 E 正是本页生成的；`pm accept` 命令本身不判 AI 标记。
- **防不了什么**：AI 不经过看板、自己在命令行带一条编出来的凭据去做，这道拦不住。

## 项目详情页的两个按钮（CHG-SCPT-2026-654）

这两个按钮也登记在 `DECISIONS` 里（`kind` 是 `project`），但**不在“决定”页上**（`build_vm` 只挑 `mission`、`scope_card`、`inbox` 三类），
只在项目详情页概览的“项目状态”一块出现，由同一个控制器（`decision_controller.py`）起命令，回执两边都显示。

| 按钮 | 作用对象 | 出现在 | 命令（`main.py` 之后） | 要用户填 | 口令生效时 |
|---|---|---|---|---|---|
| 确认归档 | 一个项目（在研或暂停） | 项目详情页；先点“归档…”跑过预演，并且预演通过 | `project archive P --confirm --approval-evidence-ref E` | — | 只有“在终端窗口里运行”，命令在终端问口令 |
| 确认重新激活 | 一个项目（已归档） | 项目详情页；先点“重新激活…”跑过预演，并且预演通过 | `project reactivate P --confirm --approval-evidence-ref E` | — | 同上 |

- **预演**：“归档…”“重新激活…”“重新检查”三个按钮不在 `DECISIONS` 里，只跑 `project archive P` / `project reactivate P`（不带 `--confirm`，只查不改），
  命令登记在 `decisions.READ_ONLY_COMMANDS`。输出原样摆出来；“预演通过”只看两样：退出码 0，并且输出里有“预演（没加 --confirm）”这一句（`decisions.DRY_RUN_MARK`）。
- **确认键和预演绑在同一个项目上**：换到另一个项目的详情页，或点“重新读取”，预演作废、确认键消失；确认时命令里的项目号取预演记下的那个。
- **发版切换前的降级**：打开项目详情页或工具页“项目”页签时后台探测一次 `project archive --help`、`project reactivate --help`、`project register --help`
  （也登记在 `READ_ONLY_COMMANDS`），结果在这个窗口里记着，点“重新读取”才重探。命令不存在时两个预演按钮灰着，旁边写“本机发布版太旧：没有这条命令”；探测没读成也灰着并写明原因。
- 凭据 E 同下一节（`click_evidence`，“用户亲手点了这个按钮”）；看板不预填用户原话、不收口令。看板是 AI 会话拉起的时，这两个确认键灰着（“只许你本人点”一节）；命令自己拒绝时，回执照实显示。
- 项目的“删除”“恢复”不上看板。

## 凭据 E 从哪来

口令**未生效**时，命令要的“用户原话凭据”由本页在点击那一刻生成：
`user-confirmation:gui-click-<年月日T时分秒>-<8 位摘要>`，格式过 `contracts/user_evidence.py` 的检查，不含任何 agent 或模型名。
这只是格式检查，防不了冒名（已知缺口 P1，见《批准口令未生效方案》）；**口令生效后命令用口令代替它**。
批准人 A 取页面顶上“批准人”一栏（默认读环境变量 `AUTO_PM_COCKPIT_APPROVER`）。

## 口令生效时怎么办

命令行故意没有任何非终端的口令通道（`ui/cli/approval_pin.py`）。所以口令生效时，带“口令”的按钮改成
“在终端窗口里运行”：本页在 Windows 上弹出一个新的终端窗口运行**同一条命令**（窗口里命令结束后会等你按回车，好让你看清结果），用户在那个窗口里输入口令；
本程序看不到口令，也看不到退出码，用户看完结果回来点“重新读取”。
“在本程序里弹窗输入口令”需要给命令行加一条非终端通道，那是改批准规则，要用户点头后另开一张卡。

## 进命令行的值怎么把关（预审 510 a）

- 运行命令和“终端窗口里运行”都是按**参数列表**直接起进程，不经过 cmd、PowerShell 或任何 shell；
  终端窗口那条路是起一个固定的 Python 小包装，再把同一条命令当参数传给它（`actions._CONSOLE_WRAPPER`）。
- 来自账本的编号（项目、任务、请求、条目）和哈希走白名单（字母数字和 `. _ : -`，哈希 8～128 位字母数字）。
- 用户自由填的字（原因、断点、备注、批准人、撞车放行）：不许换行和其他控制字符，不许出现 `"` `%` `^` `$` `` ` ``，最长 500 字；
  `&` 和 `|` 只是普通字符，允许，复制出去的命令里会被引号包住。“谁来干”走白名单（如 `claude:cloud`）。
- 测试：`tests/core/test_cockpit_decisions.py` 里带 `"` `&` `|` `^` `%` 换行的用例。

## 永远不会有的按钮

合并、删除、切换发布、代签、绕过提交钩子、启动 agent / Codex、全量门禁。测试里的 `NEVER_WORDS` 清点按钮和对话框文字。

## 没做的（命令行里有，本页没放）

- **入箱（`pm inbox add`）**：它要分诊单（影响、查重、取证、备选方案……），那是 agent 的活，用户只确认或驳回。
- **安全区签字（`pm sign-risk`）**：按规矩只能用户本人在终端或 GitHub PR 上做。
- **交接、接管、重启续做（`handoff`、`takeover`、`recover`）**：agent 之间的线，不是给用户的按钮。

## 给 Trae：怎么加一个按钮

1. 在 `decisions.py` 的 `DECISIONS` 加一行，在 `build_args()` 里接线。批准、推完成这类只许用户本人点的，加 `human_only=True`。
2. 在本表加一行（按钮名和命令前缀要原样出现）。
3. 跑 `python -m pytest tests/core/test_cockpit_decisions.py tests/core/test_cockpit_decisions_widgets.py`。
