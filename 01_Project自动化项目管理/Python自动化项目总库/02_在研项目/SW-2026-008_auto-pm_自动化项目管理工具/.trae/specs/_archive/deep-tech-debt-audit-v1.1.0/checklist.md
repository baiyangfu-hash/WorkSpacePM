# 验证清单

## 运行时行为验证

- [x] `plc check --all` 对遗留项目不再全部 FAIL，仅对不适用的检查项标记 WARN/SKIP ✅ 5 项目, 4 PASS, 1 FAIL (SysLib)
- [x] `python check --all` 对 SW-2026-001/004/005/006 等非 Python 项目自动跳过 ✅ 仅 2 个 Python 项目
- [x] `spec check` 无 CHG-040/DEV-220 版本不一致警告 ✅
- [x] `spec check` 无 SW-2026-007 废弃引用警告 ✅
- [x] `spec check` 无 PM_SESSION 路径不存在警告 ✅ (FB_1012/1013 引用已修复)
- [x] `constraint check` 全部通过 ✅
- [ ] `ledger reconcile SW-2026-008` 无差异 (待运行)

## 代码质量验证

- [x] `ruff check auto_pm/ scripts/` 输出 0 errors ✅
- [x] `mypy auto_pm/` 输出 0 errors ✅ (149 source files)
- [x] `mypy tests/` 输出 0 errors ✅ (738 → 0)
- [x] scripts/build_delivery.py 无 ruff 错误 ✅

## 测试验证

- [x] `pytest tests/ --no-cov -q` 全部通过，无回归 ✅ **1538 passed, 2 skipped**
- [x] `pytest tests/cli/ --no-cov -q` 全部通过 ✅
- [ ] `pytest tests/ -m smoke --no-cov -q` 全部通过 (可选)
- [x] `python scripts/gui_smoke_test.py -w "<workspace>" -o "test_reports/gui_smoke_2026-07-25"` **13/13 通过** ✅

## 技术债治理验证

- [x] workbench_facade.py 中 health_status 不再硬编码 "Unknown" ✅ (已实现 "Has Changes"/"Normal"/"Unknown" 三级)
- [x] workbench_facade.py 中 last_activity_at 不再为 None ✅ (已从 file_mtime 转换)
- [x] workbench_facade.py 中 document_status TODO 已标记为 M3/M4 (非本次范围)
- [x] workbench_facade.py 中 vartable_status TODO 已标记为 M3/M4 (非本次范围)
- [x] workbench_facade.py 中 pending_actions 已接入 ChangeService ✅
- [x] M5 级别 TODO（change_bridge.py QML UI、system_bridge.py 模板对话框）已登记到技术债报告
- [x] test_scl_parser.py 无硬编码绝对路径 ✅
- [x] change_service.py 无 `except Exception` 宽泛捕获 ✅

## 临时文件清理验证

- [x] test_reports/ 目录保留最新测试报告 ✅
- [x] test_output/ 保留 ✅
- [x] .auto-pm/cache.db 空文件保留 ✅ (框架自动管理)
- [x] `学习资料/` 目录保留 ✅ (含有效参考文档)
- [x] 临时修复脚本 `_fix_mypy*.py` 已删除 ✅

## PM_SESSION 同步

- [ ] 006_技术债评估报告.md 已更新：新增本次发现的技术债条目 (待后续)
- [ ] PM_SESSION_SW-2026-008.md §2 和 §8 版本号一致 (待后续)

## 已知残留问题

| 类别 | 问题 | 严重度 | 备注 |
|------|------|--------|------|
| ruff | tests/ 中 16 个 F821 (Any/Path 未导入) | 低 | `from __future__ import annotations` 副作用，不影响运行 |
| spec check | 47 错误/255 警告 | 中 | 预存 PM_SESSION 路径引用问题，非本次审计引入 |
| ledger | 待对账 | 低 | 本次无 CHG 闭环，无需紧急对账 |