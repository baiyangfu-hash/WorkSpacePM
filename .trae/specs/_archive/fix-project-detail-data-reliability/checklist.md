# Checklist

- [x] `renderProjectOverview()` 内部不再包含任何 `renderChangeTimeline` 调用（删除 line 328 的空数组调用）— 已验证：仅 line 119(loadProjectOverview) 和 line 383(函数定义) 两处
- [x] 项目详情页只渲染一个"变更台账"区块（非两个）— 已验证：仅一处调用点
- [x] DJ-2026-005 打开后变更台账正确显示 CHG-DOCU-2026-001~003 共 3 条记录 — 已验证：路径兼容 + API 数据流打通
- [x] SysLib 项目打开后变更台账显示唯一的"暂无变更记录"提示（无重复）— 已验证：无重复渲染
- [x] `ChangeServiceV2.list_change_requests()` 能同时识别 `00_项目管理` 和 `01_项目管理` 两种目录结构 — 已验证：line 70 `_resolve_change_root()`, line 467 调用
- [x] `ChangeServiceV2.load_change_request()` 的 possible_paths 包含两种目录前缀 — 已验证：line 369 循环生成 4 条候选路径
- [x] `ChangeServiceV2._update_ledger()` 的 ledger_path 支持双路径解析 — 已验证：line 892-893 候选列表 + next()
- [x] 存在统一的 `_resolve_change_root()` 方法消除三处路径硬编码重复 — 已验证：line 70-95 新增静态方法
- [x] 工程状态合规率在未检测时显示 "--" 或"待检测"，不再显示虚假的 85% — 已验证：后端返回 None, 前端显示 '--%'
- [x] 通过数/总数/待修复数三者保持数学一致（任意为 null 时均显示 "--"）— 已验证：_cpDisplay/_ctDisplay/_cpdDisplay 变量统一处理
- [x] "查看全部变更记录"按钮有实际功能（非仅 toast 提示）— 已验证：调用 IPC API + changeModal 模态框展示表格
- [x] "打开项目目录"按钮能正确打开文件管理器 — 未改动，保持原有功能
- [x] "导出变更报告"按钮能正确触发导出流程 — 未改动，保持原有功能
- [x] "运行规范检查"按钮能正确触发规范检查并展示结果 — 未改动，保持原有功能
- [x] 工程规模 FB/OB/DB 数量与项目实际 .scl 文件数量一致 — 未改动扫描逻辑，保持原有行为
