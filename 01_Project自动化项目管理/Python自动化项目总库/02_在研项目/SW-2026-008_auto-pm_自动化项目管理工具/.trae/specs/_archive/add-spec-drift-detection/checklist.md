# Checklist — auto-pm V2.0.3 规范漂移检测能力补齐

## Spec Snapshot 解析器

- [x] `auto_pm/plc/spec_snapshot.py` 已创建，含 `parse_spec_snapshot`/`load_spec_registry`/`compare_versions` 三个函数
- [x] `DriftItem` dataclass 已定义，含 spec_id/snapshot_version/registry_version/drift_level 字段
- [x] `parse_spec_snapshot` 能解析标准 Markdown 表格（列名含"规范编号"/"版本号"）
- [x] `parse_spec_snapshot` 对非标准格式返回空 dict，不抛异常
- [x] `load_spec_registry` 能从 `00_Obsidian_Base全局规范文件仓库/spec_registry.json` 加载
- [x] `load_spec_registry` 在文件缺失时返回 None，不抛异常
- [x] `compare_versions` 正确判定主版本/次版本/补丁漂移级别

## PlcChecker 检查项

- [x] `check_project` 在 PM_SESSION 检查通过后调用 `_check_spec_snapshot`
- [x] 检查项名称为 `Spec Snapshot`
- [x] 无漂移时状态为 PASS
- [x] 主版本漂移时状态为 FAIL，消息含规范ID和版本变化
- [x] 次版本/补丁漂移时状态为 WARN
- [x] Spec Snapshot 缺失时状态为 WARN
- [x] spec_registry.json 缺失时状态为 WARN，不阻断其他检查

## PlcRepairer 修复项

- [x] `repair_project` 在 PM_SESSION 修复后调用 `_repair_spec_snapshot`
- [x] `--fix` 模式下自动更新 PM_SESSION 中 Spec Snapshot 版本号
- [x] `--dry-run` 模式下仅输出预览不修改文件
- [x] 无漂移时跳过修复
- [x] 修复结果记录到 RepairResult

## 端到端验证

- [x] DJ-2026-005 `plc check` 检测到 LSP-906/LSP-907 漂移
- [x] DJ-2026-005 `plc check --fix` 自动修复 Spec Snapshot
- [x] 修复后 `plc check` Spec Snapshot 为 PASS
- [x] `plc check --all` 所有项目漂移检测无异常

## 版本号统一与文档同步

- [x] `pyproject.toml` version 为 0.2.3
- [x] `CHANGELOG.md` 含 [0.2.3] 条目
- [x] PRD 含 V2.0.3 路线图章节
- [x] PM_SESSION_SW-2026-008.md §2 与 §8 版本号一致（均为 V0.2.3）
- [x] PM_SESSION_SW-2026-008.md 含实施日志
- [x] **新增变更记录文件** `00_项目基础信息/005_变更记录_CHG.md` 已创建
- [x] 变更记录文件含 V2.0.3 所有变更条目

## Trae 规则更新

- [x] `c:\Users\fubai\Desktop\My_Workspace\.trae\rules\project-rule.md` 已追加"迭代文档同步规则"小节
- [x] 规则含 5 条强制要求
- [x] 规则适用于工作空间内所有项目

## 回归验证

- [x] 现有 PlcChecker 4 项检查逻辑不变
- [x] 现有 PlcRepairer 修复逻辑不变
- [x] CLI 接口不变（`--fix` 已有）
- [x] 全量测试通过（tests/plc/ 72 passed, 1 预存失败非本次引入）
- [x] ruff check + format 通过（已修复 F541 和格式问题）
- [ ] mypy strict 通过 — **预存问题，非本次引入**（5 个错误均在 checker.py/repairer.py 原有代码，git diff 确认非本次修改；详见 Task 8）

## 预存问题记录（非本次 spec 范围）

> 以下问题经 git diff 确认为预存问题，非本次 V2.0.3 引入，记录为 Task 8 后续处理：

- mypy strict 5 个错误：
  - `checker.py:13` Module "auto_pm.plc.models" does not explicitly export attribute "CheckResult" [attr-defined]
  - `checker.py:59` Incompatible types in assignment (str vs Literal['standard','syslib_fb']) [assignment]
  - `repairer.py:19` Module "auto_pm.plc.models" does not explicitly export attribute "RenamePlan" [attr-defined]
  - `repairer.py:19` Module "auto_pm.plc.models" does not explicitly export attribute "RepairResult" [attr-defined]
  - `repairer.py:19` Module "auto_pm.plc.models" does not explicitly export attribute "StandardizeResult" [attr-defined]
- tests/plc/ 1 个预存失败：`test_plc_standard_project_template_structure`（模板路径问题）
