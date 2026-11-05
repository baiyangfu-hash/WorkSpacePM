# PLC-TIA｜TIA 导出包与实机编译验收实施卡（脚本固化 TIA 交付工作流）

> 卡片编号：`CARD-SW008-PLC-TIA`
> 版本：`V0.1`（2026-11-05；草案，未冻结）
> 状态：`PLANNED / NOT_AUTHORIZED`（只出卡；今晚发版门禁切换完成之前不开工、不改 `auto_pm/**`；开工要用户在聊天里说“确认开工”，并给受保护驾驶舱代码的“规则批准 <12位头提交号>”）
> 安全回路: 否（本卡改驾驶舱工具，不改任何 PLC 程序；被导出的 PLC 项目若含安全回路，其自己的 PR 另走安全签字）
> 档次：核心档
> 依赖：#539（DJ-2026-011 入库）与规范 PR（LSP-903 V3.0.0 / 905 V1.6.0 / 906 V3.0.0）已合并；发版门禁已切换
> 路径根：`.`
> 执行模型：Claude；独立审计由另一个会话做
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033。时间为亚利桑那时间（MST）。

## 1. 背景与已核实事实（2026-11-04 夜～11-05）

1. **起因**：DJ-2026-011 的三个 FB 在 TIA V19 实机导入，暴露三件事：自写库类型（`FB_TON` 等）TIA 里不存在；UTF-8 无 BOM 的 `.scl` 被当 ANSI 读，中文注释乱码；“LSP 全绿”不等于 TIA 能编译。规范已改（LSP-903/905/906），但**只靠规范，下一个人还会踩**。用户原话：“不仅仅是规范固化，通过脚本固化工作流”。
2. **今天已经有的**：`reviews/tools/plc_ci.py` 在 CI 里检查“同项目其它 .scl 带 BOM，这个没有”（随 #539 入库）；`main.py plc check <PID>` 只有 Siemens LSP 诊断、结构规则、命名与禁用语法规则、文档一致性。**没有**：类型白名单检查、导出包、实机编译结果的记录与验收门。
3. **TIA 导入方式**（用户实测）：整段粘进 FB 编辑器的变量声明区不行；用“外部源文件 → 从源生成块”导入。依赖顺序错会报找不到类型。
4. **未核实**：Siemens LSP 是否认 `TON_TIME`/`R_TRIG`/BOM（等 #539 的 `plc check`/`plc test` 原文）；`SclLinter` 对 BOM 开头文件曾误报 `LSP-905-STRUCT-NO-BLOCK`（#539 夹具里复现过，源码在受保护的 `auto_pm/**`）；GUI 的 PLC 卡页代码位置、验收条件读取点还没勘测，开工第一步先只读勘测并把落点补进 §4。

## 2. 单一目标与完成定义

**让任何 agent 或用户都只能走一条路把 PLC 源码送进 TIA，且“TIA 实机编译 0 错误”成为 PLC 卡的机器可判验收条件。**

完成 = 下面 5 项全部由命令和测试证明，不靠口头：

| # | 交付 | 机器可判的验收 |
|---|---|---|
| 1 | `main.py plc export-tia <DJ号>` | 先跑 `plc check`，任何失败不出包（退出码非 0，不留半成品目录）；通过则在 `.auto-pm/tia-export/<DJ号>/<提交号>/` 生成：`.scl` 一律 UTF-8 带 BOM（已有 BOM 不重复加）、按依赖排序编号（UDT → FB → DB → OB，同类按被调用关系）、`导入步骤.md`（外部源文件 → 从源生成块、编译顺序、期望结果）、`manifest.json`（文件列表 + SHA-256 + 源仓库提交号）；再打成同名 `.zip`。同一提交重复导出字节相同。 |
| 2 | 类型与指令白名单检查并入 `plc check` | 读 LSP-905 §4.9 白名单（以规范文件为真源，不在代码里复制清单）；源码里出现不在白名单、且仓库里也没有定义的类型 → 失败，报“文件:行:类型名”。`FB_TON`、`IEC_Timer_0_DB` 单实例写法必须被抓到。 |
| 3 | `SclLinter` 修 BOM 误报 | BOM 开头且首行是代码的文件，不再报 `LSP-905-STRUCT-NO-BLOCK`；另加一条检查：导入 TIA 的 `.scl` 缺 BOM 一律失败（和 CI 的 `plc_ci.py` 同判据，二者共用一份实现或互相对拍的测试）。 |
| 4 | `main.py plc record-tia-compile <DJ号> --errors N --warnings M --tia V19 --evidence <截图路径> [--package-sha <manifest 的 SHA>]` | 把用户实机编译结果记为验收证据（写入项目目录下的受控位置并进账本，不是聊天文字）；`--package-sha` 必须等于当前提交导出的包，否则拒收（防止拿旧包的结果顶替）；证据文件必须存在。 |
| 5 | PLC 卡验收门 | `pm verify`/收口读第 4 项的记录：没有“本提交号 + errors=0”的记录，PLC 卡不能结；有 errors>0 的记录，明确报“TIA 编译未通过”。记录里的 warnings 数写进验收报告，不阻断。**LSP 全绿不再等于可交付。** |

驾驶舱 PLC 卡页加“导出 TIA 包”按钮，调用第 1 项（GUI 薄壳，不另写逻辑）。按钮可以拆到第二期，不挡第 1～5 项合并。

## 3. 实施前预检

1. 本卡字节冻结后在线程里报 SHA，经独立审计放行；用户“确认开工”；受保护驾驶舱代码的“规则批准 <12 位头提交号>”由用户在 PR 评论里给。
2. 先开 CHG 与 Work，启动带租约的 Run，工位 `.auto-pm/worktrees/claude`，分支 `claude/plc-tia-export`。
3. **先只读勘测**：`plc check` 的调用链（`ui/cli/plc/__init__.py` → `domain/plc/*`）、`pm verify` 读哪些验收条件、GUI PLC 卡页位置、账本里“证据”的现有写入口。勘测结果补进 §4 的 owned paths，再冻结卡。
4. 发版门禁在跑时不开工（笔记本不并发重任务）；单元测试按 TD-SW008-095 的规矩分组跑，不占满内存。

## 4. 预期 Owned Paths（勘测后冻结；现为草案）

| # | 路径 | 用途 |
|---|---|---|
| 1 | `auto_pm/ui/cli/plc/__init__.py` | 新增 `export-tia`、`record-tia-compile` 两个命令 |
| 2 | `auto_pm/domain/plc/tia_export.py`（新） | 导出包：BOM、排序、manifest、zip |
| 3 | `auto_pm/domain/plc/tia_compile_record.py`（新） | 实机编译记录读写与校验 |
| 4 | `auto_pm/domain/plc/whitelist.py`（新）与 `checker.py` | 白名单检查，读规范文件解析 |
| 5 | `auto_pm/domain/plc/scl_linter.py` | BOM 误报修复与缺 BOM 检查 |
| 6 | `auto_pm/ui/cli/pm.py` 或 `auto_pm/application/**` 中读验收条件的一处 | 第 5 项验收门（勘测后定准确文件） |
| 7 | `tests/plc/test_tia_export.py`、`test_tia_compile_record.py`、`test_whitelist.py`、`test_scl_linter_bom.py`（新） | 每项交付的正反例 |
| 8 | `reviews/tools/plc_ci.py`、`reviews/tools/test_plc_ci.py` | 如需与第 3 项共用判据（#539 已入库，若不改则不列） |
| 9 | GUI PLC 卡页相关 QML 与桥（第二期） | “导出 TIA 包”按钮 |

以上路径均在项目根 `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/` 下；其中 `auto_pm/**` 属判卷/受保护范围，PR 的可改范围必须逐字写完整路径，并取得规则批准。

## 5. 验收（机器无情判卷）

1. 新增测试全绿，且至少包含这些反例：缺 BOM 导出前自动补 BOM；含 `FB_TON` 的项目不出包；同提交两次导出字节相同；`--package-sha` 不匹配被拒；无证据文件被拒；errors>0 的记录让 PLC 卡验收失败；errors=0 的记录让它通过。
2. 对 DJ-2026-011 实跑 `plc export-tia`，产出的包与用户当天在 TIA 里导入成功的那批文件逐字节一致（BOM 之外）。
3. `main.py plc check DJ-2026-011`、`main.py doc check`、`ruff`、`mypy` 退出码 0；`pytest tests/plc tests/cli` 分组全绿。
4. 同类排查：全库搜“拷贝 .scl 给用户”“导入 TIA”的说明文字（`docs/handover/10 §七`、AGENTS.md 第 4 条边界、`roles/plc-electrical-engineer`、项目模板 `templates/`），改成指向这两个命令（受保护文件的改动各自列入可改范围并取规则批准）；模板里生成的 `.scl` 骨架默认带 BOM 且不含自写库类型。

## 6. 硬停止

出现第 10 项候选变更、需要改 `.github/workflows/*`、或需要删除任何文件时停止并报协调者；删除只由用户自己执行。`plc export-tia` 不得写 PLC 项目目录之外的仓库位置（输出只落 `.auto-pm/tia-export/`）。

## 7. 限制与后续

1. 本卡不替用户操作 TIA，也不判断编译结果真假——结果由用户在虚拟机里编译后用 `record-tia-compile` 记录；截图是证据，不是自动识别对象。
2. 白名单的“实机”列需要用户在 TIA V19 逐项确认后才能把对应条目标为已验证；未验证条目只告警不阻断，已验证条目之外的类型才阻断。
3. 005/009/000 项目与 SysLib 内部块的迁移（改用 TIA 原生定时器）另立卡，不在本卡。
4. FB_1030 数组下标 0..7 与“数组从 1”规则的冲突需要用户裁决，不在本卡。
