# SW-2026-008 回归缺陷根因与修正 WBS（PM）

> 文档状态：ACCEPTED / CLOSED / READY_FOR_NEXT_WBS
> 编制日期：2026-09-08
> 收尾提交前 Git HEAD：`a5d3166a`（Batch C 与本次 PM 收尾待提交）
> 触发回归：pytest `1728 passed, 7 failed, 14 skipped, 54 errors`
> 已解冻对象：原 Cockpit OS WBS、`010_Cockpit_OS_后续原子迭代WBS_PM.md`、CHG-SCPT-2026-188～191 已完成用户验收并关闭；NG-WP-24～48 恢复逐包报批。
> 权限边界：Batch A、Batch B、Batch C 已按各自 DecisionPackage 完成并验收；本次 PM 收尾另以 CHG-SCPT-2026-192 登记关闭门禁兼容修复，仅涉及 `change_service.py` 与对应单测；不包含发布资产、active/previous 指针、delivery_bridge COM 风险或全仓 Mypy 债务修复。

## 1. 根因结论

| 编号 | 现象 | 根因证据 | 归属裁决 | 修正方向 |
|---|---|---|---|---|
| RC-01 | PM_SESSION 两项规模测试失败，实测 154 行 | CHG-SCPT-2026-087 明确上限为 150KB/300 行；`fbd17198` 在无对应测试更新的情况下把 `MAX_FILE_LINES` 从 300 改为 150；注释仍写 170 行，测试又分别写 200/300 行 | 历史代码回归；不是当前 PM_SESSION 实物超限 | 恢复权威 300 行，统一代码注释、测试和指南；保留 150KB |
| RC-02 | ledger auto-fix 测试未找到新建台账 | `0119fda2` 将自动创建文件改为规范字形 `01_版本变更台账.md`，测试仍断言旧字形 `台帐`；查找逻辑已兼容两者 | W0 直接相关的测试契约漏更；产品行为符合新规范 | 测试断言改为新规范名，并保留旧存量兼容用例 |
| RC-03 | PLC 黄金模板完整性测试失败 | 模板在 `6699a5b8` 已改为 `台账`，测试仍只接受 `台帐` | 既有模板测试漂移，非 W0 引入 | 更新黄金模板断言并增加禁止新模板生成旧字形的负向检查 |
| RC-04 | dashboard 最近活动排序失败 | 日期字符串通过本地时区 `datetime.timestamp()` 转换，而项目 mtime 是绝对 epoch；America/Phoenix 下 2026-06-27 零点晚于测试项目时间戳，排序随时区变化 | 既有非确定性实现/测试缺陷 | 统一为 UTC 或统一比较带时区 datetime；增加至少两个 TZ 的确定性测试 |
| RC-05 | PLC 初始化默认主设计人断言失败 | 实现按 `AUTO_PM_AUTHOR`/`os.getlogin()` 动态取值；沙箱返回 `CodexSandboxOffline`，测试硬编码 `fubai` | 既有非便携测试 | 测试显式注入 author 或 monkeypatch `AUTO_PM_AUTHOR`；生产逻辑补稳定降级链但不硬编码用户姓名 |
| RC-06 | 54 个 QML setup error | 5 个测试文件硬编码外部 Python311 的 `C:\Users\fubai\...\PySide6\qml`；当前虚拟环境已有可用 QML 路径，但对外部目录执行 `exists()` 即触发 WinError 5 | 既有环境硬编码与 fixture 复制扩散 | 建立单一 `tests/qml/conftest.py`，只从当前 `PySide6.__file__` 推导 import path；移除绝对路径 |
| RC-07 | 全模块 Ruff 29 条 | import 分组、尾随空格与 Qt/QML 必需 camelCase 被同一规则处理 | 既有静态质量债；不是 45 项 W0 窄域测试失败 | 可机械修复项精确修复；Qt 公开 API 通过窄域 per-file-ignore 管理，不改 QML 契约名 |

## 2. 归因边界

- CHG-SCPT-2026-188 的 45 项目标域测试仍全部通过，决策包绑定、execution fail-closed、handoff/Saga 主路径未发现功能回归。
- RC-02 是本次 W0 路径变更遗漏的依赖测试，必须纳入 CHG-SCPT-2026-188 验收前修正证据。
- RC-01、RC-03～RC-07 为历史基线或环境可移植性问题，应使用独立修正 CHG，不得伪装成 CHG-SCPT-2026-188 原范围扩张。
- QML 的 WinError 5 是测试主动访问硬编码外部目录造成；不建议修改系统 ACL，也不允许通过跳过 54 项测试取得绿灯。

## 3. 原子修正 WBS

| WP | 原子目标 | 精确拟议范围 | 前置依赖 | 硬验收与停止点 | 状态 |
|---|---|---|---|---|---|
| REG-WP-00 | 冻结与证据固化 | 本文件、原两份 WBS、PM_SESSION；记录 HEAD、完整回归和窄域回归 | 无 | 不修改源码/状态；原 WBS 显式冻结 | COMPLETED_READ_ONLY |
| REG-WP-01 | 建立独立修正审批包 | 新建精确 CHG、DecisionPackage、execution handoff；列出 REG-WP-02～09 路径 | REG-WP-00 + 用户批准 | approved_paths 与实际 diff 一致，否则停止 | COMPLETED |
| REG-WP-02 | 恢复 PM_SESSION 权威门禁 | `auto_pm/application/core/pm_session_service.py`、`tests/core/test_pm_session_service.py`、`tests/test_pm_session_size.py` | REG-WP-01 | 150KB/300 行唯一口径；相关测试全绿；不得删除当前有效治理记录凑行数 | COMPLETED |
| REG-WP-03 | 修复 W0 台账字形回归测试 | `tests/change/test_ledger_reconciler.py`，必要时只读核对 `path_resolver.py` | REG-WP-01 | 新建只生成 `台账`；旧 `台帐` 仍可发现；相关测试全绿 | COMPLETED |
| REG-WP-04 | 修复 PLC 模板黄金断言 | `tests/plc/test_template_integrity.py` | REG-WP-01 | 模板生成规范 `台账`；禁止新生成旧字形；模板门禁全绿 | COMPLETED |
| REG-WP-05 | 消除 dashboard 时区非确定性 | `auto_pm/application/core/dashboard_service.py`、`tests/core/test_dashboard_service.py` | REG-WP-01 + Batch B 批准 | UTC 与 America/Phoenix 结果一致；既有摘要测试全绿 | COMPLETED |
| REG-WP-06 | 消除项目作者环境耦合 | `auto_pm/application/core/project_service.py`、`tests/core/test_project_crud.py` | REG-WP-01 + Batch B 批准 | 测试显式控制 author；无 `fubai`/`CodexSandboxOffline` 环境依赖；PLC/Python 初始化测试全绿 | COMPLETED |
| REG-WP-07 | 集中 QML 测试运行时发现 | 复用 `tests/qml/conftest.py`；修改 5 个硬编码 fixture 文件 | REG-WP-01 + Batch B 批准 | 仓内 `rg` 不再命中用户绝对 PySide6 路径；54 项不再 setup error | COMPLETED |
| REG-WP-08 | 复跑 QML 并二次裁决 | 仅 QML 测试及当前虚拟环境 | REG-WP-07 | 指定 QML 分域 54 passed；范围外 `test_delivery_bridge.py` 输出 COM `0x80040155`，未纳入本批修复 | COMPLETED_WITH_OUT_OF_SCOPE_RISK |
| REG-WP-09 | 收敛 Ruff 基线 | 仅 Ruff 报告点名的活动母体文件与 `.ruff.toml` 精确例外 | REG-WP-02～08 | Ruff Exit 0；Qt/QML 公共名称不被重命名；无 broad-format | COMPLETED |
| REG-WP-10 | 分域回归 | 上述每包对应测试 + W0 原 45 项 | REG-WP-02～09 | 所有分域测试 Exit 0；W0 保持 45 passed | COMPLETED |
| REG-WP-11 | 全量回归 | `tests/`，禁用覆盖率副产物或输出至 `.auto-pm/reports/` | REG-WP-10 | 0 failed、0 errors；skip 逐项有既有理由；不得因跳过新增问题变绿 | COMPLETED_WITH_OUT_OF_SCOPE_RISK |
| REG-WP-12 | 静态与治理总门禁 | Ruff、批准源码清单 Mypy、CLI 冒烟、`ledger reconcile SW-2026-008`、精确 Git diff | REG-WP-11 | 全部批准范围门禁 Exit 0；台账 0 差异；无 release/active/previous 指针变化 | COMPLETED_WITH_BASELINE_DEBT |
| REG-WP-13 | PM 收尾与解冻报批 | 修正 CHG、PM_SESSION、台账、验收矩阵 | REG-WP-12 | 用户已明确验收并解冻；CHG-188～191 closed，原 WBS/后续 WBS 恢复逐包报批 | COMPLETED |

## 4. 执行批次建议

- Batch A：REG-WP-01～04。先处理权威门禁与两处 `台帐→台账` 测试契约，风险最低。
- Batch B：REG-WP-05～08。处理时区、身份和 QML 运行时可移植性；QML 二次错误必须重新停机裁决。
- Batch C：REG-WP-09～13。静态债收敛、全量回归、治理收口与解冻报批。
- 每个 Batch 独立 DecisionPackage、独立 handoff、独立提交候选；任何非零门禁阻断下游。

## 5. 解冻条件

同时满足以下条件前，原 WBS 保持冻结：

1. 全量 pytest 为 0 failed、0 errors，且没有为规避问题新增 skip/mock/hardcode。
2. W0 原 45 项持续通过，RC-02 的新旧台账兼容测试通过。
3. Ruff、Mypy、CLI 冒烟及 SW-2026-008 台账对账全部 Exit 0。
4. QML 测试只使用当前虚拟环境，不访问用户级 Python311 绝对路径。
5. 精确 diff 不包含 release 槽位、active/previous 指针、Obsidian 法典或未批准路径。
6. 修正 CHG 已完成 PM 收尾，用户已明确批准验收并解冻；CHG-188～191 closed。

## 6. 当前停止点

Batch A（REG-WP-01～04）已按 `CHG-SCPT-2026-189` / `DEC-20260908-21B46741` 执行并验收完成；定向 72 passed，W0 原 45 项保持通过，CHG-189 已 closed。Batch B（REG-WP-05～08）已按 `CHG-SCPT-2026-190` / `DEC-20260908-6446DB06` 执行并验收完成；定向 84 passed、Batch B+W0 129 passed、全量 1792 passed/14 skipped，CHG-190 已 closed。Batch C（REG-WP-09～13）已按 `CHG-SCPT-2026-191` / `DEC-20260908-09EB0220` 执行并验收完成；Ruff Exit 0、批准源码清单 Mypy 14 files Exit 0、CLI help 5 项 Exit 0、ledger-check 0 差异、W0 关联定向 72 passed、全量 1792 passed/14 skipped，handoff `AI-20260908-REG-WP09-13` 已 consumed，CHG-191 已 closed。PM 收尾门禁兼容修复已按 CHG-192 Retrofit 登记，change service 回归 39 passed。范围外 `delivery_bridge.py:331` 的 Windows COM `0x80040155` 原生栈另登记；全仓 Mypy 42 条既有类型债务只读记录，均未越界修复。原 Cockpit WBS 与 Wave B 已解冻，NG-WP-24～48 恢复为逐包报批的下一主线。
