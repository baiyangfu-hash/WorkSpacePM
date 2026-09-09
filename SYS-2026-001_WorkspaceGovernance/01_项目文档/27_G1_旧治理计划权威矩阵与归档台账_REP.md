# G1 旧治理计划权威矩阵与归档台账

> 状态：`ACCEPTED`
> 执行日期：2026-09-09
> 当前唯一计划：`26_SW-2026-008_治理恢复与连续性重基线总计划_PM.md`
> 操作边界：只处理治理计划和历史交接文档；未修改 PM_SESSION、CHG、DEC、数据库、发布槽位、产品源码或 Obsidian 正式规范

## 1. 裁决规则

1. `ACTIVE_AUTHORITY`：仅文档 26。
2. `ACTIVE_INPUT`：仍需在后续 G 包吸收的候选设计，不具生产约束力。
3. `HISTORICAL_EVIDENCE`：保留原路径，供追溯，不提供执行授权。
4. `SUPERSEDED`：执行语义失效；零外部引用且 Git 干净时可物理归档，否则原路径逻辑归档。
5. `DIRTY_DEFERRED`：存在其他 owner 的未提交改动，禁止修改或移动。

## 2. 文件级权威矩阵

| 文件 | 裁决 | 外部引用 | 处置 |
|---|---|---:|---|
| `26_SW-2026-008_治理恢复与连续性重基线总计划_PM.md` | `ACTIVE_AUTHORITY` | 不适用 | 唯一执行入口 |
| `03_分阶段整改路线图_PM.md` | `SUPERSEDED` | 4 | 原路径逻辑归档；不修改 PM_SESSION 和历史归档引用 |
| `07_SW-2026-008_驾驶舱Dogfooding迭代方案与WBS_PM.md` | `SUPERSEDED` | 3 | 原路径逻辑归档 |
| `12_SW-2026-008_PM驾驶舱强制闭环_对话交接_PM.md` | `SUPERSEDED` | 1 | 原路径逻辑归档；其中调用 `pm-workflow` 的要求失效 |
| `13_SW-2026-008_PM驾驶舱强制闭环_Gemini交接与后续WBS.md` | `SUPERSEDED` | 0 | 已物理归档 |
| `14_SW-2026-008_RC1-0至RC1-4_跨Agent执行Checkpoint.md` | `HISTORICAL_EVIDENCE` | 1 | 原路径保留 |
| `15_SW-2026-008_驾驶舱强制闭环_后续WBS校准_PM.md` | `DIRTY_DEFERRED` | 1 | 存在未提交改动，不修改、不移动；执行语义由文档 26 覆盖 |
| `17_SW-2026-008_研发母体稳定部署_重制实施方案_PM.md` | `SUPERSEDED` | 18 | 原路径逻辑归档；保留架构和发布历史证据 |
| `18_SW-2026-008_旧方案历史治理索引_PM.md` | `SUPERSEDED` | 2 | 原路径逻辑归档；旧 NG-WP 路线失效 |
| `20`～`24` 候选差异规范 | `ACTIVE_INPUT / NOT_EFFECTIVE` | 各 1 | G2 输入；不移动、不写 Obsidian |
| `25_P2-00_连续性候选现场冻结报告_REP.md` | `HISTORICAL_EVIDENCE` | 2 | 保留原路径；漂移事实不得继续使用 |
| 项目 `010_Cockpit_OS_后续原子迭代WBS_PM.md` | `SUPERSEDED` | 4 | 原路径逻辑归档；NG-WP-24～48 不再授权执行 |
| 项目 `011_回归缺陷根因与修正WBS_PM.md` | `HISTORICAL_EVIDENCE` | 8 | 保留已验收回归事实，不提供下一包授权 |
| 根 `Cockpit_OS_大一统集成与超级特种兵架构方案_WBS.md` | `SUPERSEDED` | 0 | 已物理归档 |

## 3. 物理归档台账

目标目录：`SYS-2026-001_WorkspaceGovernance/01_项目文档/archive/G1-20260909/`

| 原路径 | 目标文件 | 大小 | SHA-256 | 恢复方式 |
|---|---|---:|---|---|
| `SYS-2026-001_WorkspaceGovernance/01_项目文档/13_SW-2026-008_PM驾驶舱强制闭环_Gemini交接与后续WBS.md` | `13_SW-2026-008_PM驾驶舱强制闭环_Gemini交接与后续WBS.md` | 12512 | `D48F848CDF6C82EA90A80E31EA099401DB67F0BA55DE2305D99726B0AC6B0F53` | 按 Git rename 逆向移回原路径 |
| `Cockpit_OS_大一统集成与超级特种兵架构方案_WBS.md` | `Cockpit_OS_大一统集成与超级特种兵架构方案_WBS.md` | 24265 | `BDEAA8348D68B63D64AD2947671E92DEDC0798B9A3325FA6C549801EF78DD268` | 按 Git rename 逆向移回工作区根目录 |

归档前后大小和 SHA-256 一致；没有删除内容。其他 `SUPERSEDED` 文件因存在外部引用，保持原路径并由文档 26 的优先级规则逻辑失效。

## 4. G1 验收结论

- 不再存在第二个活动执行计划；旧编号不能授权新工作。
- 两项物理移动均可由 Git 恢复，且未产生外部 Markdown 断链。
- 用户或其他 Agent 的未提交文件未被改写、移动、暂存或清理。
- G2 只消费文档 20～24 的设计内容，不继承其历史批准状态。
