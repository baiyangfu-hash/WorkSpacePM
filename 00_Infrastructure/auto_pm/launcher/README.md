# auto_pm 稳定部署容器 · 双槽骨架（NG-WP-12）

本目录按《SW-2026-008"研发母体 + 稳定部署"重制实施方案》NG-WP-12 改造为受控稳定容器骨架。

## 布局

- `launcher/launch.py`：自包含 fail-closed 启动器骨架。当前仅做"解析 + 校验"（指针 → release-id → releases containment → manifest 登记），不执行 release 内代码；真实执行接线由 NG-WP-13/15 完成。
- `releases/<release-id>/`：不可变 release 槽位。当前为空（尚未部署任何 release）。
- `active_release.json` / `previous_release.json`：双槽指针，`schema_version=release_pointer.v1`，初始为 `release_id: null`（未初始化）。写指针必须经母体 `DeploymentContainer.write_pointer`（同卷临时文件 + 刷盘 + `os.replace` 原子替换）。
- `deployment_manifest.json`：`schema_version=deployment_manifest.v1`，登记每个 release 的逐文件 SHA-256；launcher 只允许启动 manifest 已登记的 release。
- `.lock`：运行期互斥文件，由 `DeploymentContainer.acquire_lock` 按需 `O_CREAT|O_EXCL` 创建、释放时删除；**骨架不预置**（预置会永久破坏互斥语义）。崩溃残留的锁需人工确认后移除。

## 状态

- 未部署任何 release（`releases/` 为空，双指针为 null）。
- 未切换运行入口：工作区根 `main.py`、`双击启动驾驶舱.bat`、`.venv` 均未改动；当前运行代码仍是本目录平铺源码，直到 NG-WP-13/15 完成入口解耦与首个正式发布。
- 母体源码真源：`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`（`auto_pm/application/core/deployment_service.py`）。

## 回退与 Python 缓存（2026-10-22）

- active 校验不过、previous 校验通过时仍会改用 previous 启动，但会在标准错误打一段“警告：……已改用上一版本……原因：……”，不再只在标准输出写一行 `verified via previous_release.json`。
- active 里多出的只是 `__pycache__`（目录里全是 `*.pyc`）时**不回退**，直接以退出码 4 停下，并给出清除命令：
  `python -B 00_Infrastructure/auto_pm/launcher/launch.py --purge-bytecode`
  该命令只删 active / previous 发布目录里未登记的 `__pycache__`，删前确认载荷其余部分与 manifest 逐字节一致（载荷损坏时一个文件都不删），删完重新校验并打印结果，不启动驾驶舱。
- 缓存的来源：有人在发布目录里不带 `-B` 运行过 Python（例如临时脚本 import 了发布目录的代码）。启动器自己的子进程始终 `-B -I` 且设 `PYTHONDONTWRITEBYTECODE=1`。
