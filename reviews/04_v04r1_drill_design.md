# 04 V04-R1 第 3 张卡（真实进程演练）设计草案（项目 Claude，2026-10-17）

基于 `23e841b`。本文是建议，不是指令。

## 结论

**可以做，并且不需要新依赖：用 Python 标准库 `ctypes`、`winreg`，再加 Linux 的 `/proc`，就能取到第 1 张卡要的全部指纹字段。** 另有三点要注意：

| # | 发现 | 严重度 |
|---|---|---|
| 1 | `psutil` **不在**锁定依赖里（`00_Infrastructure/auto_pm/environment/requirements-lock-py312-win.txt` 共 111 行，只有 `pywin32-ctypes==0.2.3`，它是 keyring 的依赖，不提供进程 API）。产品代码里只有 `domain/modbus/modbus_bridge.py:147` 可选地导入 psutil，没有时退回标准库。所以指纹不应依赖 psutil | 中 |
| 2 | 已经有真实进程演练的骨架 `tests/e2e/test_pmf_recovery.py`（594 行，r01～r09 和 v04t 场景），文件头写明“不证明进程回收（V04-R1）”。第 3 张卡应当**扩展这个文件的 Scene 和探针**，不要另起一套 | 信息 |
| 3 | 现有探针 `process_state()`（同文件约 89-112 行）只看 `GetExitCodeProcess == 259`，没有启动时间，所以分不清 PID 复用；而且一个以 259 为退出码结束的进程会被误判为存活。产品里的指纹模块不能照搬这个探针 | 中 |

## 1. 指纹怎么取（产品代码，建议放 `auto_pm/infrastructure/process_fingerprint.py`）

对应第 1 张卡的 `ProcessFingerprint(host_id, pid, start_time, image_sha256, cmdline_sha256)` 和 `ProcessObservation`。

### Windows（标准库 ctypes）

| 字段 | 取法 | 失败时 |
|---|---|---|
| `host_id` | `winreg` 读 `HKLM\SOFTWARE\Microsoft\Cryptography\MachineGuid` | 取不到时为空串，`judge_process` 因此返回 UNKNOWN |
| 进程是否存在 | `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION=0x1000, False, pid)`；失败且 `GetLastError()==87`（参数无效）⇒ 不存在 | 错误码 5（拒绝访问）⇒ **存在但读不了**，返回 `pid_exists=True, start_time=None`，最终为 UNKNOWN。不能把拒绝访问当成已死 |
| 是否已退出 | 拿到句柄后用 `WaitForSingleObject(h, 0) == WAIT_OBJECT_0(0)` 判断已退出；不要只看退出码 259 | 调用失败 ⇒ `start_time=None` |
| `start_time` | `GetProcessTimes` 的创建时间 FILETIME，存成十进制整数字符串（100ns 精度），精确比较 | 调用失败 ⇒ None |
| `image_sha256` | `QueryFullProcessImageNameW` 得到可执行路径，对**规范化后的路径字符串**（不区分大小写、统一分隔符）取 SHA-256。不读取 exe 文件内容：内容哈希在 Python 解释器上没有区分度，而且读大文件会拖慢回收判断 | None |
| `cmdline_sha256` | 持有者在授予时用 `GetCommandLineW()` 取自己的命令行（最可靠）；观察方用 `NtQueryInformationProcess(h, ProcessCommandLineInformation=60, …)`（Windows 8.1 起，限权句柄可用） | 观察方取不到 ⇒ None，结果是 UNKNOWN（偏保守） |

关键原则：**只有“确认 PID 不存在”或“启动时间不同”才算 PROVEN_DEAD**，任何读不到的情况都是 UNKNOWN，和第 1 张卡的 `judge_process` 一致。

### Linux（CI 用；也让演练能在 CI 上跑）

`host_id` 取 `/etc/machine-id`；是否存在看 `/proc/<pid>` 是否存在且 `stat` 状态不是 `Z`；`start_time` 取 `/proc/<pid>/stat` 第 22 字段（以时钟滴答计的启动时间），解析时从最后一个 `)` 之后切分，因为进程名里可以有空格；`image` 取 `os.readlink("/proc/<pid>/exe")`；`cmdline` 取 `/proc/<pid>/cmdline` 的原始字节。读取时遇到 `PermissionError` ⇒ 该字段为 None。

### 记录时机

指纹由**持有者自己**在 `record_run_started` 时提交（它最清楚自己的 PID、启动时间和命令行），作为启动证据的一部分写入同一个事件。不改 schema：`ExecutionStartEvidence` 现在就是事件载荷，新增字段要用新的 `schema_version`（例如 `run-started.v2`），旧版本继续能够读取。

## 2. 演练场景（扩展 `tests/e2e/test_pmf_recovery.py`）

全部是真实子进程、真实时钟、真实 SQLite，复用现有 `Scene`、`_make_root`（`tests/infrastructure/test_continuity_store_sidecars.py:36`）和 `_events()`。

| 场景 | 步骤 | 期望 |
|---|---|---|
| r10 心跳期间写入不被误拒 | 子进程持租约，每 20 秒续租一次，期间连续写 Checkpoint（带授予时的 epoch） | 全部成功；`LEASE_RENEWED` ≥ 2 次；授予版本不变（回归 03 的第 1 条发现） |
| r11 强杀后回收 | 子进程持租约后被强杀（Windows `TerminateProcess`，Linux `SIGKILL`）→ 等租约过期 + 120 秒宽限 → 回收 | 判定 PROVEN_DEAD → ALLOW；epoch 升级、token 更换；产生回收事件 |
| r12 旧进程回写被拒 | 沿用 r02 的真实情形：控制器进程（登记的持有者）被强杀，它启动的执行器孙进程仍在运行并持有 token → 过期 + 宽限后，因登记的持有者已证明不在而回收 → 让孤儿执行器用旧 token 和旧 epoch 写 Checkpoint、推进状态 | 孤儿执行器的写入被拒（ownership 或 STALE），表里没有新行、事件链没有新事件 |
| r13 存活进程不被抢占 | 子进程持租约后停止续租但保持运行，等过期 + 宽限 | 判定 ALIVE → REFUSE_PROCESS_ALIVE，什么都不变 |
| r14 未知进程保持 PENDING | 指纹的 `host_id` 改成别的主机（模拟跨机）；另一例让观察方读不到启动时间 | 都是 PENDING，什么都不变 |
| r15 PID 复用 | 记录一个已退出进程的 PID，再起一个新进程（无法保证拿到同一 PID 时，改为直接构造“PID 存在但启动时间不同”的观察结果，并在测试名里写明这一点） | PROVEN_DEAD |
| r16 租约未过期强制收回 | 有 Decision 强制收回，并且进程已证明不在 | ALLOW；没有 Decision 时 REFUSE_LIVE_LEASE |

**耗时**：租约最短 60 秒（store 中 `renew_lease` 和 `transfer_lease` 都限定 `60 <= lease_seconds <= 86400`），加 120 秒宽限，单个场景至少 3 分钟。建议像现有的 `settled` fixture 一样，用一个模块级 fixture 一次性造出“已过期 + 宽限已过”的现场，r11、r12、r13、r14 共用这个现场，总耗时控制在约 4 分钟以内。CI 的超时是 25 分钟（`sw008-ci.yml` 的 `timeout-minutes: 25`），需要先确认现有测试耗时加上这 4 分钟仍有余量。

**平台**：Windows 和 Linux 都要跑。Windows 专有的失败分支（错误码 5、87）照现有 `test_v04t_an_api_failure_is_unknown_and_never_an_exit` 的做法注入 API 桩，只测判定逻辑；真实进程部分两个平台都跑，不用 `skipif` 跳过整个场景。

## 3. 不污染真实治理库

1. 每个场景的根目录都是 `tmp_path` 下新建的 Git 仓库（`_make_root` 已经这样做），store 只认这个根，`_require_control_root` 会拒绝真实工作区以外的路径混用。
2. 演练进程的 `cwd` 设为 `tmp_path`，环境变量里**不传**任何指向真实工作区的路径；在 fixture 里断言 `ContinuityStore(root).workspace_root` 位于 `tmp_path` 之下。
3. 测试结束后断言真实 `.auto-pm/continuity.db` 的修改时间与字节数没有变化（测试开始时记录一次，结束时比较；真实库不存在时跳过这一条断言即可）。
4. 演练证据（场景、PID、判定、耗时）写成 JSON，放 `.auto-pm/reports/v04r1_drill_<时间>.json`。这个目录已被 `.gitignore`（第 129 行 `.auto-pm/reports/`）忽略，不会进 Git。
5. 测试里 `scene.kill()` 现有的保护（只杀本测试启动的进程，`test_v04t_the_scene_refuses_to_signal_a_process_it_did_not_start`）继续保留，新增的暂停和恢复操作也要套同一个保护。

## 4. 与第 2 张卡的接口

- 回收接口（建议名 `reclaim_run_lease`）在 store 的同一个事务里：读租约 → 读启动事件里的指纹 → 接收调用方传入的观察结果（store 不执行进程探测，探测在 service 层，和契约“nothing here runs a process probe”一致）→ 调用 `decide_reclaim` → ALLOW 时换 token、写 `RUN_LEASE_RECLAIMED` 事件（载荷带新的授予版本）。
- 观察结果与判定都写入事件，审计时能看到“当时为什么允许回收”。
