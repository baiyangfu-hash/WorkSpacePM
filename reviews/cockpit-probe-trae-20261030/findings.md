# 驾驶舱探测 findings（trae, 20261030）

- 开始时间：2026-10-29 18:55 MST
- 状态：进行中（本文件随探测进度增量更新）
- 环境：Linux 沙箱 / Ubuntu 24.04 / 发布版 1.3.3-d8f7c8b / Python 3.12.3 (.venv)
- 操作对象：一次性假项目 **ZZ-2026-901**（PROBE-0001 被 ID 格式门禁拒绝，见 F3/F6；ZZ-2026-901 为符合文档格式且明显非真实的替身，不与任何真实项目撞号）
- 命令全文与退出码见 `transcript/`；每条发现的最短复现见 `repro/`

## 发现清单

| 编号 | 探测项 | 严重度 | 现象 | 是否已复现 | 建议 |
|------|--------|--------|------|-----------|------|
| F1 | 环境 | P2 | 全新克隆无 `.venv`；cockpit-entry SKILL 只写 Windows 路径 `.venv\Scripts\python.exe`；Linux 引导脚本存在但藏在 `00_Infrastructure/auto_pm/environment/setup_env.sh`，入口文档未提及 | 已复现 | 入口文档补 Linux 路径与引导脚本指引 |
| F2 | 环境 | P2 | 本沙箱 pip 全局镜像 mirrors.volces.com 缺锁定版本（aiosqlite==0.22.1），照 `setup_env.sh` 原样执行在 3/5 步失败；官方源可装齐 | 已复现 | 锁文件安装步骤对镜像源缺口给出自检提示 |
| F3 | 登记假项目 | P1 | `project create --dry-run` 与真实校验不一致：dry-run 对 `PROBE-0001` 放行（exit 0，业务线 PROBE 无警告），真实执行被 `project_id 必须匹配格式` 拒绝；ZZ-2026-901 同样 dry-run 过、真实挂 package_name | 已复现（两次） | dry-run 应执行与真实一致的全部校验 |
| F6 | 登记假项目 | P1 | `project create` 的 package_name 派生死路：中文名、连字符英文名均被拒（`Validation error for question 'package_name'`），`--help` 无 `--package-name` 覆盖参数，报错不指路；只有下划线名能过 | 已复现（三次） | 报错中写明派生规则并提供覆盖参数或自动规范化 |
| F7 | 登记假项目 | P1 | 脚手架生成 `PM_SESSION_ZZ-2026-901.md`，与 AGENTS.md「PM_SESSION 已退役：不改、不新建」直接冲突 | 已复现 | 模板移除 PM_SESSION 文件 |
| F8 | 登记假项目 | P1 | python 栈项目落点为全新顶层目录 `0100_项目/`，与任务文档/工作区惯例 `01_Project自动化项目管理/.../02_在研项目/` 不一致 | 已复现 | 核对 dest-dir 解析约定 |
| F9 | 进门定位 | P0 | `project create` 成功后，`pm resume` / `context resolve` 均报「项目未登记到 Workspace Registry」——registry（`SYS-2026-001_WorkspaceGovernance/workspace_registry.json`，仅 6 项）与 project 命令的登记（9 项）是两本账；新建项目走不了文档规定的进门第一步 | 已复现 | `project create` 同步写 Workspace Registry 或提示手工登记步骤 |
| F10 | 进门定位 | P1 | `context resolve --path 0100_项目/ZZ-2026-901_cockpit_probe_fake`（相对路径，目录实际存在）报 `Directory ... does not exist`；换绝对路径才通过存在性检查 | 已复现 | 修正相对路径解析基准 |
| F11 | 版本面 | P2 | `main.py --help` 顶层仍列出已退役的 `pm-session` 与「pm-workflow 专属」的 `prototype`，与退役隔离声明不符 | 已复现 | 退役命令组从 CLI 面移除或标注 DECOMMISSIONED |
| F12 | 版本面 | P1 | AGENTS.md / cockpit-entry 描述的 `pm orient/inbox/plan/approve/verify/accept/close/park/unpark/switch/missions/handoff/takeover` 在发布版 1.3.3 全部不存在（`pm --help` 仅 context/resume），插急活与 Mission 全流程探测面整体不可执行 | 已复现 | 部署指针升级或文档标注「需 ≥ 某版本」 |
| F13 | 门禁口径 | P1 | 全新克隆 `.git/hooks/` 仅有 `*.sample`，提交门禁钩子未安装；`setup_env.sh` 只补执行位不安装——物理提交门禁在新机器上默认不存在 | 已复现 | 环境引导安装钩子或 `doctor` 检查钩子存在性 |

## 撤销/更正

- 原「F4：pm resume 对未登记项目报 Error 但 exit 0」**撤销**：系探测 harness 管道掩盖真实退出码，复测 exit=1，行为正确。
- 原「Linux 无引导脚本」更正为 F1 的准确表述（脚本存在但入口文档未指路）。

## 探测面进度

- [x] 环境（F1/F2）
- [x] 登记假项目（F3/F6/F7/F8/F9/F10）
- [ ] 租约与 Run 状态机（进行中）
- [ ] Mission 全流程（受 F12 限制，预期大量「命令不存在」证据）
- [ ] 插急活（受 F12 限制）
- [ ] 受保护文件与改动声明
- [ ] 门禁口径对照（部分：F13）
- [ ] 错误信息质量打分
- [ ] Linux/Windows 差异

## 结束时填写（尚未结束）

- 结束时间：-
- 发现计数：P0 x / P1 x / P2 x
- 未做探测项：-
- 总命令数：-
