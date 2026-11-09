# Checklist

## Phase 1: 项目骨架
- [x] pm_mgr 项目目录存在，含 pyproject.toml
- [x] pyproject.toml 指定依赖仅标准库 + click（不引入 SQLite、PyQt5、Flask 等重型依赖）
- [x] cli.py 注册 5 个子命令，`pm-mgr --help` 输出正确
- [x] 代码复用 .trae/project-bootstrap/ 下现有模板（不重复定义模板内容）

## Phase 2: init 命令
- [x] `pm-mgr init <dir> --type software ...` 创建的目录结构与当前 PS 脚本输出完全一致
- [x] `pm-mgr init <dir> --type plc ...` 创建的目录结构与当前 PS 脚本输出完全一致
- [x] 生成的 PM_SESSION 含完整 Spec Snapshot 表格（版本号从 spec_registry.json 自动读取）
- [x] hooks 脚本完整复制（4 个 PS 脚本 + hooks.json + README.md）
- [x] .trae/handoffs/ 目录创建
- [x] skeleton 文件内容正确（README 引用正确规范 ID，pyproject.toml 语法正确，.plc.json 语法正确）
- [x] 文档模板内容正确（项目信息占位符已替换为实际值）
- [x] 幂等性：重复运行不损坏已有文件，除非 --force

## Phase 3: retrofit 命令
- [x] `pm-mgr retrofit <DJ-2026-000>` 提示 archived 跳过
- [x] `pm-mgr retrofit --force <DJ-2026-000>` 成功注入 hooks + handoffs + Spec Snapshot
- [x] DJ-2026-000 原有文件完全未修改（仅添加了 .github/hooks/ + .trae/handoffs/ + Spec Snapshot 区块）

## Phase 4: check + detect + snapshot 命令
- [x] `pm-mgr detect <SysLib>` 返回 `plc`
- [x] `pm-mgr detect <SW-2026-005>` 返回 `software`（已修复 pyproject.toml 递归搜索）
- [x] `pm-mgr check <DJ-2026-000>` 在 retrofit 后报告全部通过
- [x] `pm-mgr check <SysLib>` 在 retroit 前报告缺失 hooks（SysLib无PM_SESSION，正确报告）
- [x] `pm-mgr snapshot <path>` 刷新 Spec Snapshot 不破坏 PM_SESSION 其他内容

## Phase 5: pm-workflow 集成
- [x] SKILL.md Step 0 检测逻辑改为调用 `pm-mgr detect`
- [x] SKILL.md Step 3G 初始化改为调用 `pm-mgr init`
- [x] SKILL.md 新增 Step 3H（旧项目补完模式）调用 `pm-mgr retrofit`
- [x] 推荐口令新增 `pm: 补完` 命令
- [x] 工具依赖新增 pm-mgr 完整说明
