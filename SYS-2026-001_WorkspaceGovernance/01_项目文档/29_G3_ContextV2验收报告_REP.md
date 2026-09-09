# G3 Context v2 验收报告

> 状态：`DEV_ACCEPTED / RUNTIME_NOT_EFFECTIVE`
> 验收日期：2026-09-09
> 依据：`28_G2_跨Agent工作连续性架构契约_CANDIDATE.md`

## 1. 实施范围

- 新增版本化 `SYS-2026-001_WorkspaceGovernance/workspace_registry.json`，只登记 SYS-2026-001 与 SW-2026-008 的显式拓扑。
- `workspace-context.v1` 升级为 `workspace-context.v2`，增加顶层 `subject_project_id` 和 Registry 契约。
- Context 服务改为“显式 PID Registry 查找”或“当前目录向上局部锚点 + Registry 交叉验证”。
- control、development、runtime 全部来自 Registry，不再从 PM_SESSION 正文推断。
- runtime 已声明时强制验证 active pointer 和 release 实物；缺失、越界、冲突、重复项目或绝对路径均失败关闭。
- 未修改 Resume、Work、handoff、数据库、发布槽位、PM_SESSION 或 Obsidian。

## 2. 关键实测

| 门禁 | 结果 |
|---|---|
| Context 定向回归 | `13 passed` |
| Ruff（契约、服务、测试） | Exit 0 |
| Mypy（契约、服务） | Exit 0 |
| 全量 pytest | `1812 passed, 14 skipped, 60 warnings`；Exit 0 |
| SW 真实解析 | subject=`SW-2026-008`、control=`SYS-2026-001`、dev=研发母体、runtime=`00_Infrastructure/auto_pm`、release=`1.2.4-6699a5b` |
| SW read_set | Registry、`.copier-answers.yml`、active pointer，共 3 项 |
| SYS 真实解析 | subject=`SYS-2026-001`、control 为空、runtime/release 为空 |

## 3. 失败关闭覆盖

已覆盖：未管理目录、未登记项目、Registry 路径与目录锚点冲突、控制映射缺半、重复 project_id、绝对路径、release 指针和实物验证、显式 PID 不依赖邻近扫描。

## 4. 状态边界

本批只证明研发母体实现与测试通过。active release `1.2.4-6699a5b` 未包含该实现，因此不得声明 `RUNTIME_EFFECTIVE`。发布统一后置到 G7；G4 不修改 release。
