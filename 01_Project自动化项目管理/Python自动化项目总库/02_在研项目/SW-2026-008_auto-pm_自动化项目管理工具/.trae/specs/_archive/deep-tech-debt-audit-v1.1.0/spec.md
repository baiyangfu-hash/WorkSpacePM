# 深度技术债审计与修复 Spec

## Why
auto-pm V1.1.0 在多次迭代后累积了技术债和潜在缺陷，5大过程组重组后需要进行一次全面的深度审查，确保工具自身健康。

## What Changes
- 修复 `plc check --all` 全部 FAIL 的误报问题（所有 6 个 PLC 项目均报 FAIL）
- 修复 `python check --all` 对非 Python 项目结构的误报
- 修复 `spec check` 发现的规范版本不一致（CHG-040、DEV-220）和废弃引用（SW-2026-007）
- 修复 PM_SESSION 中引用的不存在路径
- 清理 test_reports/ 和 test_output/ 中的临时文件
- 修复 `except Exception` 宽泛捕获（change_service.py:256）
- 修复测试文件中的硬编码绝对路径（test_scl_parser.py）
- 处理 8 个 TODO 标记的技术债
- 修复 mypy tests/ 738 个类型标注错误（31 个测试文件）
- 修复 scripts/build_delivery.py 的 ruff 5 个错误
- 清理 .auto-pm/cache.db 空文件
- 审计 `学习资料/` 目录内容
- **BREAKING**: 无

## Impact
- Affected specs: LSP-907（PLC检查规范）、CODE-210（Python编程规范）、PM-040（变更单模板）
- Affected code: auto_pm/plc/、auto_pm/cli/python_cmd.py、auto_pm/change/change_service.py、auto_pm/application/workbench_facade.py、tests/（31 文件）、scripts/build_delivery.py

## ADDED Requirements

### Requirement: PLC 检查应区分项目类型
PLC 检查系统 SHALL 根据项目实际类型（标准模板 vs 遗留项目）执行不同的检查规则，避免对所有项目使用统一的"标准模板"检查导致全部 FAIL。

#### Scenario: 遗留 PLC 项目检查
- **WHEN** 对非标准模板的遗留 PLC 项目执行 `plc check`
- **THEN** 系统应识别项目类型并跳过不适用的检查项，而非全部标记为 FAIL

#### Scenario: 标准模板项目检查
- **WHEN** 对标准模板创建的 PLC 项目执行 `plc check`
- **THEN** 系统应执行完整的标准检查，与现有行为一致

### Requirement: Python 检查应跳过非 Python 项目
Python 检查系统 SHALL 在检测到非 Python 项目结构时自动跳过，而非报告 8/9 项 FAIL。

#### Scenario: 非 Python 项目误报
- **WHEN** 对 SW-2026-001/004/005/006 等遗留项目执行 `python check`
- **THEN** 系统应识别这些项目不是 Python 项目并跳过，而非报告 pyproject.toml 不存在等

### Requirement: 规范版本一致性检查修复
spec check SHALL 修复 CHG-040 和 DEV-220 的版本不一致问题，并修复 project-rule.md 中的废弃 SW-2026-007 引用。

### Requirement: 代码质量门禁
项目 SHALL 通过 ruff 0 errors 和 mypy 0 errors（包括 tests/ 目录）。

## MODIFIED Requirements

### Requirement: 测试文件类型标注
所有测试文件 SHALL 添加完整的类型标注，满足 mypy strict 模式要求。

#### Scenario: mypy tests/ 检查
- **WHEN** 运行 `mypy tests/`
- **THEN** 应报告 0 errors

### Requirement: TODO 技术债治理
所有标记 TODO 的代码 SHALL 被评估并按优先级处理：M3/M4 级别的高优先级 TODO 应在本次迭代中完成，低优先级 M5 TODO 登记到技术债报告。

## REMOVED Requirements
无