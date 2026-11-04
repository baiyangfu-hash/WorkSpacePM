# Tasks — auto-pm V2.0.3 规范漂移检测能力补齐

> 基线：pyproject.toml 0.2.1 / CHANGELOG 0.2.2 / 里程碑 M1-M4 全部完成（875 测试通过）
> 目标：补齐规范漂移检测与自动修复能力，统一版本号

---

## Task 1: 新建 Spec Snapshot 解析器

- [x] Task 1.1: 创建 `auto_pm/plc/spec_snapshot.py` 模块 ✅
  - [x] SubTask 1.1.1: 实现 `parse_spec_snapshot(pm_session_path: str) -> dict[str, str]`，正则解析 PM_SESSION 中的 Spec Snapshot 表格
  - [x] SubTask 1.1.2: 实现 `load_spec_registry(workspace_root: str) -> dict[str, str] | None`，读取 spec_registry.json 提取规范ID→版本号映射
  - [x] SubTask 1.1.3: 实现 `compare_versions(snapshot: dict, registry: dict) -> list[DriftItem]`，对比版本差异，判定漂移级别
  - [x] SubTask 1.1.4: 定义 `DriftItem` dataclass（spec_id, snapshot_version, registry_version, drift_level: "major"|"minor"|"patch"）

- [x] Task 1.2: 编写单元测试 `tests/plc/test_spec_snapshot.py` ✅ (18 passed)
  - [x] SubTask 1.2.1: 测试标准表格解析（含"规范编号"/"版本号"列名）
  - [x] SubTask 1.2.2: 测试非标准格式（无表格/列名不匹配）返回空 dict
  - [x] SubTask 1.2.3: 测试 spec_registry.json 加载（正常/缺失/格式错误）
  - [x] SubTask 1.2.4: 测试版本对比（主版本/次版本/补丁/一致）

## Task 2: PlcChecker 新增 Spec Snapshot 检查项

- [x] Task 2.1: 在 `auto_pm/plc/checker.py` 的 `check_project` 中新增 `_check_spec_snapshot` 方法 ✅
  - [x] SubTask 2.1.1: 在 PM_SESSION 检查通过后调用 `_check_spec_snapshot`
  - [x] SubTask 2.1.2: 调用 `spec_snapshot.parse_spec_snapshot` 解析 PM_SESSION
  - [x] SubTask 2.1.3: 调用 `spec_snapshot.load_spec_registry` 加载注册表
  - [x] SubTask 2.1.4: 调用 `spec_snapshot.compare_versions` 对比版本
  - [x] SubTask 2.1.5: 根据漂移级别设置检查项状态（major=FAIL, minor/patch=WARN, 无漂移=PASS）
  - [x] SubTask 2.1.6: 处理边界情况（PM_SESSION 无 Spec Snapshot / registry 缺失 → WARN）

- [x] Task 2.2: 编写单元测试 `tests/plc/test_checker_spec_snapshot.py` ✅ (5 passed)
  - [x] SubTask 2.2.1: 测试无漂移场景（PASS）
  - [x] SubTask 2.2.2: 测试主版本漂移（FAIL）
  - [x] SubTask 2.2.3: 测试次版本漂移（WARN）
  - [x] SubTask 2.2.4: 测试 Spec Snapshot 缺失（WARN）
  - [x] SubTask 2.2.5: 测试 spec_registry.json 缺失（WARN）

## Task 3: PlcRepairer 新增 Spec Snapshot 修复逻辑

- [x] Task 3.1: 在 `auto_pm/plc/repairer.py` 的 `repair_project` 中新增 `_repair_spec_snapshot` 方法 ✅
  - [x] SubTask 3.1.1: 在 PM_SESSION 修复后调用 `_repair_spec_snapshot`
  - [x] SubTask 3.1.2: 读取 spec_registry.json 最新版本
  - [x] SubTask 3.1.3: 正则替换 PM_SESSION 中 Spec Snapshot 表格的版本号列
  - [x] SubTask 3.1.4: dry_run 模式下仅输出预览不修改文件
  - [x] SubTask 3.1.5: 记录修复结果到 RepairResult

- [x] Task 3.2: 编写单元测试 `tests/plc/test_repairer_spec_snapshot.py` ✅ (4 passed)
  - [x] SubTask 3.2.1: 测试自动修复（版本号更新）
  - [x] SubTask 3.2.2: 测试 dry-run 预览（不修改文件）
  - [x] SubTask 3.2.3: 测试无漂移时跳过修复
  - [x] SubTask 3.2.4: 测试 Spec Snapshot 缺失时跳过修复

## Task 4: 端到端验证

- [x] Task 4.1: 对 DJ-2026-005 运行 `plc check`，确认检测到漂移 ✅ (检测到 7 条漂移，含 LSP-906 主版本漂移)
- [x] Task 4.2: 对 DJ-2026-005 运行 `plc check --fix`，确认自动修复 ✅ (Spec Snapshot 从 FAIL 变为 PASS)
- [x] Task 4.3: 再次运行 `plc check`，确认 Spec Snapshot PASS ✅ (修复后 "Spec Snapshot 与 spec_registry.json 一致")
- [x] Task 4.4: 运行 `plc check --all`，确认所有项目漂移检测正常 ✅ (7 个项目全部检测，无异常崩溃)

## Task 5: 版本号统一与文档同步

- [x] Task 5.1: 更新 `pyproject.toml` version 0.2.1 → 0.2.3 ✅
- [x] Task 5.2: 更新 `CHANGELOG.md` 新增 [0.2.3] 条目 ✅
- [x] Task 5.3: 更新 PRD 新增 V2.0.3 路线图章节 ✅
- [x] Task 5.4: 更新 PM_SESSION_SW-2026-008.md 实施日志，统一 §2/§8 版本号为 V0.2.3 ✅
- [x] Task 5.5: 新增变更记录文件 `00_项目基础信息/005_变更记录_CHG.md`，记录 V2.0.3 所有变更 ✅

## Task 6: Trae 规则更新（文档同步强制规则）

- [x] Task 6.1: 将"迭代文档同步规则"追加到 `c:\Users\fubai\Desktop\My_Workspace\.trae\rules\project-rule.md` ✅
  - [x] SubTask 6.1.1: 在 project-rule.md 的"版本管理"章节后新增"迭代文档同步规则"小节
  - [x] SubTask 6.1.2: 规则内容包含 5 条强制要求（spec 含进度基线/迭代后同步文档/版本号一致/PM_SESSION 一致/里程碑核查）
  - [x] SubTask 6.1.3: 规则适用于工作空间内所有项目

## Task 7: 验证（按 checklist.md 系统核查）

- [x] Task 7.1: Spec Snapshot 解析器 checkpoint 全部通过 ✅ (7/7)
- [x] Task 7.2: PlcChecker 检查项 checkpoint 全部通过 ✅ (7/7)
- [x] Task 7.3: PlcRepairer 修复项 checkpoint 全部通过 ✅ (5/5)
- [x] Task 7.4: 端到端验证 checkpoint 全部通过 ✅ (4/4)
- [x] Task 7.5: 版本号统一与文档同步 checkpoint 全部通过 ✅ (7/7)
- [x] Task 7.6: Trae 规则更新 checkpoint 全部通过 ✅ (3/3)
- [x] Task 7.7: 回归验证 checkpoint 大部分通过 ✅ (5/6，mypy strict 为预存问题)
  - [x] 27 个新增测试全部通过
  - [x] tests/plc/ 72 passed, 1 预存失败（非本次引入）
  - [x] ruff check + format 通过（已修复 F541 和格式问题）
  - [ ] mypy strict — 5 个预存错误（非本次引入，记录为 Task 8）

## Task 8: 预存问题修复（非本次 spec 范围，后续处理）

> 以下问题经 git diff 确认为预存问题，非本次 V2.0.3 引入。记录在此供后续迭代处理。

- [ ] Task 8.1: 修复 mypy strict 5 个预存错误
  - `checker.py:13` / `repairer.py:19` — models.py 通过 `__all__` 显式导出 CheckResult/RenamePlan/RepairResult/StandardizeResult
  - `checker.py:59` — _detect_project_type 返回类型改为 `Literal['standard','syslib_fb','shared-library','test-suite']` 或 result.project_type 字段类型改为 str
- [ ] Task 8.2: 修复 tests/plc/ 预存失败 `test_plc_standard_project_template_structure`（模板路径问题）

---

# Task Dependencies

- **Task 1（解析器）** → Task 2（检查器）→ Task 3（修复器）：解析器是基础
- **Task 2 + Task 3** → Task 4（端到端验证）：检查器和修复器就绪后验证
- **Task 4** → Task 5（版本号统一）：验证通过后统一版本号
- **Task 5** → Task 6（Trae 规则更新）：文档同步后更新规则
- Task 1.1 和 Task 1.2 可并行（开发+测试同步）
