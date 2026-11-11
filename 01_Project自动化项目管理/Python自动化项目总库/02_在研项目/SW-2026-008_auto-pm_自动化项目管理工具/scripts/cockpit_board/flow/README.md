# 总控屏：流程图页和工程工具页（给接手的 agent 看）

这两页是总控屏（`scripts/cockpit_board`）的新增页面。原则和别的页一样：**界面是命令行的另一层皮**，按钮只调同一条命令，不绕过任何护栏；颜色只来自 `theme.py`。

## 流程图页（只读）

| 文件 | 作用 |
|---|---|
| `flow/graphs.json` | 四张图（任务 Mission、工作项 Work、运行 Run、变更单 Change）的节点、连线、位置。**画图代码只读它，不写死任何状态。** |
| `flowgraph.py` | 读并校验 JSON（节点不能叠、连线不能指向不存在的点、坐标不能出画布）；回答“从这个状态一步能去哪”；把账本里的卡变成“图上亮哪个点”。不依赖 Qt。 |
| `widgets/flow.py` | `FlowGraphWidget`（用 QPainter 画一张图，点节点高亮）和 `FlowPage`（选图、选卡、显示下一步）。 |

- 亮的点来自账本：任务图用任务状态，运行图用该任务最近一次运行的状态。**工作项、变更单图账本读取还没带上状态，只显示流程，不乱亮**（要亮，先让 `pm_dashboard` 读出来）。
- 图里的每条线必须和代码里的真实状态表一致。`tests/core/test_cockpit_board_flow.py` 逐条对账：
  任务 `mission_service._TRANSITIONS`、工作项 `work_registry_service._TRANSITIONS`、运行 `continuity_execution_service._RUN_TRANSITIONS`、变更单 `domain/change/constants.STATUS_FLOW`。
  **状态表改了、图没改，测试就红；改流程先改代码里的状态表，再改 `graphs.json`。**
- 线上的字（如 `pm accept`）是对应的命令；`actor: "user"` 表示只听用户本人。测试会核对这些命令真是 `pm` 的子命令。
- 以后“编排”的路线：第一步改 `graphs.json`（仍走 PR 和独立审计）；第二步才是界面拖拽生成这个文件；真正让“改了就生效”的状态机放最后，且必须过受保护清单。

## 工程工具页

| 文件 | 作用 |
|---|---|
| `tool_actions.py` | **唯一起子进程的新文件**（另一个是 `actions.py`）。`TOOLS` 是命令白名单；`build_command()` 把表单拼成 `main.py` 的参数，缺栏、取值不对、选项注入（以 `-` 开头）、批准类状态一律拒绝；`run_tool()` 在控制根里跑并返回回执（命令 + 退出码 + 输出）；`open_workbench()` 另起窗口打开 `gui --advanced`。 |
| `tool_policy.py` | 按钮文字白名单和禁用词。 |
| `iocheck.py` | 对 `vartable parse --output-format json` 的输出做 IO 查重（重复地址、重复变量名）；只读统计。 |
| `widgets/tools.py` | `ToolsPage`：变更单（看、建、转状态）、决策（看）、变量表（查重）、“打开高级工作台”。 |

- 会写文件的（建变更单、转状态）先点“预览命令”，看过整条命令再点运行；表单一改，预览作废；一次预览只运行一次。
- 批准类状态（已批准、有条件批准）和新建决策包**不在界面里**：只在终端里由用户本人做（有口令要输口令）。
- 命令失败不吞：退出码和输出原样显示。
- 接线（已完成，在 `app.py`）：`ToolsPage(root)` 和 `FlowPage()` 在页面栈里，顶栏多“流程图”“工具”两个入口（文字在 `tool_policy.NAV_BUTTONS`）；`_render` 里调 `_feed_flow_and_tools`：`tools.set_projects([(项目编号, 相对路径)])` 和 `flow.show_cards(flowgraph.card_positions(board.projects))`，数据没变就不重填；`--screenshot` 多出“流程图”“工具”两张。

## 常见改动怎么做

- 加一个工具按钮：先在 `tool_actions.TOOLS` 登记命令并写 `build_command` 分支和测试（参数取值要对账真实命令的选项）→ 再在 `widgets/tools.py` 加按钮 → 最后把按钮文字加进 `tool_policy.TOOL_BUTTONS`。
- 加一张图：在 `graphs.json` 加一项（`source` 写明对应的状态表）→ 在 `test_cockpit_board_flow.py` 的对账参数里加一行。

## 骨架契约数据（CHG-SCPT-2026-628 骨架 C）

三个数据文件，界面只读它们，不写死命令清单。对账测试是 `tests/core/test_cockpit_board_contracts.py`。

| 文件 | 内容 | 谁读 |
|---|---|---|
| `flow/commands_map.json` | 驾驶舱命令行的每一条叶子命令（现在 219 条）分成四类：`read` 只读，界面随时可以跑；`write` 会写文件、账本或远程，界面只能经白名单按钮、先预览再跑；`user_only` 只听用户本人（要口令或用户原话），agent 不能代跑；`never` 界面里不放（钩子调用的、AGENTS.md 禁止单独推状态的、前台阻塞的）。只读命令如果有会写的开关（如 `plc check --fix`），列在 `write_flags` 里。拿不准的一律归 `write`。 | “命令与契约”页；对账测试 |
| `flow/pages.json` | 骨架 7 个新页（任务、PR 与审计、工作树与分支、发版、脊柱图、命令与契约、要你出手）各读哪条命令、带什么参数、用 `readers.READERS` 里哪种读法，以及空态、错态文案。`<PID>` 由页面换成当前项目编号。 | 骨架 D 的占位页 |
| `flow/spine.json` | 脊柱十步：一张卡从进门定位到验收收口，每步谁做（你／本地／云端）、用哪些命令、完成判据、读不到时显示什么。取自规划附件 `spine_draft.json`，规划定稿后以规划为准。 | “脊柱图”页、“任务”页 |

对账测试会拦下面这些情况：
- 命令树里新加了命令但表里没分类，或者表里留着已删掉的命令。变异测试会往命令树里塞一条假命令，检查它被点名。
- 按钮的性质和分类对不上：“决定”页按钮只能跑 write 或 user_only 类，要口令、要用户原话的按钮必须是 user_only；“工具”页只读按钮只能跑 read 类；never 类不许有按钮。
- 页面读了不是 read 类的命令，参数里带了写开关，或者用了没登记的读法。
- 脊柱某步引用了没登记的命令（`external` 里列出的脚本除外），或者引用了不存在的页面。

改法：
- 加新命令：先在 `commands_map.json` 里分好类。user_only、never 两类要在 `note` 里写理由，`counts` 跟着改。
- 页面要读一条新命令：命令必须先是 read 类，读法先加进 `readers.py`，再在 `pages.json` 里声明。
- 分类依据是命令的帮助文字和 AGENTS.md 的规矩，没有逐条读源码。审计发现分错了，直接改表，测试会跟着核。
