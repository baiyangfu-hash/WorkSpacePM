# Checklist — auto-pm PLC 落地就绪度验收

> 验收清单：所有 P0/P1 修复完成后，按此清单逐项验证。每项必须通过才能判定"可正常管理 PLC 项目"。

## P0 阻断性修复验收

- [ ] **P0-1 验收**：`auto-pm project show DJ-2026-005` 读取的 version 为 V6.0.0（来自 `02_PLC程序/通用ST程序及变量表/.plc.json`），而非 V1.0.0（根目录占位）
- [ ] **P0-2 验收**：`auto-pm plc check SysLib` 不产生"缺少 02_PLC程序/通用ST程序及变量表/03_HMI设计/04_现场调试/04_变更管理"的 FAIL
- [ ] **P0-3 验收**：`auto-pm plc check SysLib` 递归检查 12 个 FB 子目录（FB_1011~FB_1020 等），每个 FB 子目录按 syslib_fb 类型检查
- [ ] **P0-4 验收**：`auto-pm sync` 同步变更单时，PLC 项目（路径 `00_项目管理/04_变更管理/01_变更单/CHG-*/`）和 Python 项目（路径 `01_项目文档/03_执行过程/02_变更管理/`）的变更单都能同步到 DB
- [ ] **P0-5 验收**：workspace_root=`c:\Users\fubai\Desktop\My_Workspace` 时，`auto-pm change list DJ-2026-005` 能正确列出 CHG-PLC-2026-001~005

## P1 重要修复验收

- [ ] **P1-1 验收**：`auto-pm plc check DJ-2026-005` 不报"缺少 04_变更管理"FAIL（因 `00_项目管理/04_变更管理` 已存在）
- [ ] **P1-2 验收**：`auto-pm plc check DJ-2026-000` 不产生"缺少 02_PLC程序/通用ST程序及变量表/03_HMI设计/04_现场调试/04_变更管理"的 FAIL
- [ ] **P1-3 验收**：含 §10 验证项表格的变更单，`_all_verification_passed` 能正确判断所有验证项通过时返回 True
- [ ] **P1-4 验收**：变更单状态流转过程中抛异常时，`.tmp` 文件被清理（无残留）
- [ ] **P1-5 验收**：路径含 "SysLib" 子串但不属于库项目的场景（如 `C:\SysLib_backup\DJ-2026-010`）不被误判为 syslib_fb 类型
- [ ] **P1-6 验收**：在工作区 ChangeTab 创建变更单后，主窗口状态栏变更数自动 +1
- [ ] **P1-7 验收**：主窗口状态栏 `_status_change` 显示实际变更总数，非硬编码 0

## 端到端验收（三参考项目）

- [ ] **SysLib 端到端**：`auto-pm plc check SysLib` → 0 FAIL；`auto-pm plc repair SysLib --dry-run` → 0 破坏性操作；`auto-pm plc standardize SysLib` → FB 子目录 PRD/ 文档命名标准化
- [ ] **DJ-2026-000 端到端**：`auto-pm plc check DJ-2026-000` → 0 FAIL；`auto-pm plc repair DJ-2026-000 --dry-run` → 0 破坏性操作；`auto-pm plc standardize DJ-2026-000` → 根 PRD/ 文档命名标准化
- [ ] **DJ-2026-005 端到端**：`auto-pm plc check DJ-2026-005` → 0 FAIL（读取 V6.0.0 .plc.json）；`auto-pm plc repair DJ-2026-005 --dry-run` → 0 破坏性操作；`auto-pm change list DJ-2026-005` → 列出 CHG-PLC-2026-001~005；`auto-pm change show CHG-PLC-2026-001` → 正确解析

## 文档与测试同步验收

- [ ] **PM_SESSION 修正**：`PM_SESSION_SW-2026-008.md` 测试数为 688（与实际一致），V2.0.1-A/C 状态字段无矛盾
- [ ] **覆盖率报告完整**：`09_整改项/覆盖率报告.txt` 包含 change/cli/core/db/connection/repository/schema 全部模块数据
- [ ] **文档版本对齐**：PRD/INT/DSN/TEC 四件套均为 V2.0.2
- [ ] **测试检查清单更新**：`09_整改项/V2.0-测试执行检查清单.md` 显示 688 测试/81% 覆盖率
- [ ] **回归测试通过**：`task test` 全量通过，新增 P0/P1 修复测试用例无失败

## 落地就绪度最终判定

- [ ] **可对 SysLib 执行 check/repair/standardize 不产生误报和结构破坏**
- [ ] **可对 DJ-2026-000 执行 check/repair/standardize 不产生误报和结构破坏**
- [ ] **可对 DJ-2026-005 执行 check/repair/standardize/change 不产生误报和结构破坏**
- [ ] **workspace_root=My_Workspace 时跨层级变更管理可用**
- [ ] **GUI 状态栏变更数实时准确**
