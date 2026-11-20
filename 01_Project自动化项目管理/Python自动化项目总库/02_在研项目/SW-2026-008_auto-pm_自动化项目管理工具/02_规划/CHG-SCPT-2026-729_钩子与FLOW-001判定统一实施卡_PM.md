# 卡 CHG-SCPT-2026-729：钩子与 FLOW-001 判定统一（CHG-SCPT-2026-729）

> 卡片编号：`CARD-CHG-SCPT-2026-729-HOOK-FLOW-ALIGN V1.0`
> 隔离基线：`fee3708b`（`main`）
> 路径根：`.`
> 档次：要你点头（修改 `AGENTS.md`、`.trae/` 与提交钩子本体，按 `FLOW-001` 需用户开工前批准、独立审计与完整门禁）
> 安全回路：否

用户授权：2026-11-20 21:50（Asia/Shanghai），用户在本机主对话明确回复：“好的，批准开工，把 git_hook_enforcer.py 列入受保护路径，并一并修改 .trae 里的旧话”（批准凭据 `user-confirmation:2026-11-20T21:50`）。

## 根因

1. **规则与钩子两套判定**：`AGENTS.md` FLOW-001 把驾驶舱代码列为“直接做、不建单”，但现役 `1.3.3-d356fb1` 的 `commit-msg` 钩子对任何暂存的生产代码（`.py/.scl/.st/.qml`）都要求绑定一个状态在 `approved` 及之后的变更单，没有“直接做”这一类。
2. **先做后补的后门**：`change create --retrofit` 直接生成 `closed` 状态变更单、跳过全部流转，正好满足钩子。`CHG-SCPT-2026-727` 就是这样产生的：先改代码，后补一张“已完成”的单，批准不在前，追踪失真。
3. **追踪键其实已经存在**：`pm_merge.py` 已强制分支上至少一个提交带 `领卡占位: <卡号>`，合并记录也写 `card`；缺的是钩子不认这一行。

## 改成什么

1. **钩子分路**（`auto_pm/infrastructure/git_hook_enforcer.py`）：
   - 新增 `PROTECTED_PROD_PATTERNS` 与 `is_protected_production_file()`；受保护清单 = `rules_approval_check.RULE_PATTERNS` + PLC 目录/模板 + `pm_merge.py` + 钩子自身 + `change_status_guard.py`、`change_service.py`、`status_journal.py`、`guard_checker.py`、`ui/cli/change.py`；
   - 暂存生产代码全为“直接做”类时，提交说明有 `领卡占位: <卡号>` 一行即放行，不要求变更单；
   - 含任一受保护路径时，仍按原逻辑要求有且只有一个已批准变更单。
2. **退役先做后补**（`auto_pm/ui/cli/change.py`、`change_service.py`、`workbench_use_cases.py`）：删除 `change create --retrofit` 选项；删除 `create_change_request` 的 `retrofit` 回参和直接落 `closed` 的分支；建项目初始化不再生成 `closed` 单，改为正常 `draft`。
3. **本机合并与执行链同步**（`scripts/pm_merge.py`、钩子）：受保护清单加入钩子自身与 `change_status_guard.py`、`change_service.py`、`status_journal.py`、`guard_checker.py`、`ui/cli/change.py`，改执行链也要用户批准的变更单。
4. **规则文本同步**：
   - `AGENTS.md` FLOW-001：受保护路径补上钩子文件；“两类都不省的”写明钩子只认变更单号或 `领卡占位` 两样，`--retrofit` 已退役；
   - `.trae/skills/cockpit-entry/SKILL.md`：删掉“快线……用 `--retrofit` 补”的旧话，改为两类走法。
5. **历史证据**：`CHG-SCPT-2026-727` 的完成态用户否认（2026-11-21），但状态日志已有 `completed` 记录，驾驶舱没有 `completed → implementing` 的合法回退路径；本分支**不含** 727 改动，控制根 727 文件已恢复为 `implementing`。727 的补注与日志更正留给“变更状态更正命令”后续单处理。

## 可改范围

| 路径 | 基线状态 | 用途 |
|---|---|---|
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/infrastructure/git_hook_enforcer.py` | 存在 | 路径分类与领卡占位判定 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/ui/cli/change.py` | 存在 | 删除 `--retrofit` 选项 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/change/change_service.py` | 存在 | 删除 `retrofit` 回参与直接落 `closed` 分支 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/application/workbench_use_cases.py` | 存在 | 建项目初始化不再生成 `closed` 单 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/scripts/pm_merge.py` | 存在 | 受保护路径加入钩子与变更执行链 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/infrastructure/test_git_hook_enforcer.py` | 存在 | 新增直接做/受保护/漂移三类用例，并恢复 TD-100 原断言 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/change/test_change_service.py` | 存在 | 删除 retrofit 专用用例 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/cli/test_change.py` | 存在 | 新增“帮助里不再有 --retrofit”用例 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/cli/test_change_status_journal_e2e.py` | 存在 | retrofit 用例改为“新单落 draft、无流转记录” |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/CHG-SCPT-2026-729_钩子与FLOW-001判定统一实施卡_PM.md` | 计划新增 | 本卡 |
| `AGENTS.md` | 存在 | FLOW-001 判定与受保护路径同步 |
| `.trae/skills/cockpit-entry/SKILL.md` | 存在 | 删除快线/retrofit 旧话 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-728.md` | 计划新增 | 重复草稿作废（用户 2026-11-21 决定） |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-729.md` | 计划新增 | 本变更单原件 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/02_变更记录/01_版本变更台账.md` | 存在 | 台账随批入库 |

## 实施与验证记录（2026-11-21）

- `pytest tests/infrastructure/test_git_hook_enforcer.py tests/infrastructure/test_commit_msg_d01.py tests/change/test_change_service.py tests/cli/test_change.py tests/cli/test_change_status_journal_e2e.py tests/application/test_workbench_applicant.py` → 208 passed, 1 skipped；
- `ruff check`（改动文件）→ All checks passed；
- `mypy --platform win32 --no-incremental`（4 个改动源码）→ Success；
- `main.py doc check` → 退出 0；
- 钩子/合并/退役逻辑在**发版切换后**才在 `main.py` 生效，切换前旧版本仍按旧判定运行。

## 验收

- 钩子新用例：直接做类带 `领卡占位` 放行、缺卡号拒绝、受保护路径只带卡号仍拒绝；
- 漂移测试：`PROTECTED_PROD_PATTERNS` 覆盖 `rules_approval_check.RULE_PATTERNS`；
- `pytest tests/infrastructure/test_git_hook_enforcer.py tests/infrastructure/test_commit_msg_d01.py` 与全量 `pytest` 退出 0；
- `ruff check auto_pm tests`、`mypy auto_pm` 退出 0；
- `main.py doc check` 退出 0；
- `pm_merge.py merge trae-e06f1b --pid SW-2026-008` 门禁全绿并合入本机 `main`；
- 发版切换后 `change create --help` 不再含 `--retrofit`，钩子按新判定放行/拦截。
