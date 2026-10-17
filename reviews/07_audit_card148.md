# 07 卡 148 独立审计：V04-R1 第 2 张卡，epoch 续租语义与 PENDING 出口（项目 Claude，2026-10-17）

`<SW008>` 的含义同 05。审计对象：提交 `d25a981`（`fix(contracts): [CHG-SCPT-2026-422] … (M3-V04R1B)`），父提交 `23e841b`。本文是建议，不是指令。

## 结论

**同意 epoch 部分；PENDING 出口需要再改一处才算完成。**

- 卡 147 审计的第 1 条（续租也加 epoch）已经正确修复：只有授予、移交、回收会加 epoch，续租不加，并且有测试和变异证明。
- 新增的 PENDING `exit_path` 写的出口，契约本身走不通。出口文字是“用户签一个强制回收的 Decision”，但 `decide_reclaim(process=UNKNOWN, forced_by_decision=True)` 仍然返回 `PENDING`。也就是说，按出口说的去做，结果不会变。
- 卡 147 审计的第 2、3 条（启动时间按字符串比较、不校验时区）这张卡没有处理，与提交说明一致。补丁 09 已按 `d25a981` 重新生成。

| # | 发现 | 证据 | 严重度 |
|---|---|---|---|
| 1 | PENDING 的出口走不通：`UNKNOWN` 的判断排在 `forced_by_decision` 前面，所以强制回收的 Decision 永远到不了 `UNKNOWN` 这一支。原有测试还把这个行为锁死了：`forced_by_decision=True` 加 `UNKNOWN`，断言结果是 `PENDING` | `auto_pm/contracts/lease_reclaim.py` 的 `decide_reclaim()`，第 128～130 行；`tests/contracts/test_lease_reclaim.py` 中“a decision never forces a reclaim from an unknown holder”的断言 | **中**：现在不会误回收，偏保守；但接入存储以后，按出口签了 Decision 的 Run 会一直卡在 PENDING，而且没有任何提示 |
| 2 | 第一次授予时的 epoch 没有常量。`next_epoch` 和 `epoch_after` 都要求 `current ≥ 1`，那么第一次授予时是 1，还是从 1 加到 2，没有约定 | `next_epoch()`、`epoch_after()` 的校验 | 低：建议加 `INITIAL_EPOCH = 1`，并写明“第一次授予就是 1，不调用 `epoch_after`” |
| 3 | 卡 147 审计的第 2、3 条仍然存在 | 与 `07_audit_card147.md` 相同 | 高（第 2 条）/ 低（第 3 条）。补丁 09 已就绪 |
| 4 | 本提交里没有 `CHG-SCPT-2026-422` 的变更单文件，同 147 | `git show --stat d25a981`：只有 2 个文件 | 信息（UNVERIFIED，可能在本机补录） |

## 核对过程

### 文件集合

`git show --stat d25a981`：只改了 `lease_reclaim.py`（+30/−3）和 `test_lease_reclaim.py`（+34），没有碰 store，与提交说明一致。

### 测试、静态检查与变异

隔离目录，Python 3.13，`pytest --noconftest -o addopts=`。SW008 的 `conftest.py` 导入 PySide6，所以不加 `--noconftest` 会报 INTERNALERROR；这是本会话环境的问题，与卡无关。

| 检查 | 结果 |
|---|---|
| `pytest tests/contracts/test_lease_reclaim.py` | 22 passed（147 的 18 个加上新增的 4 个） |
| `ruff check`（0.16.4） | All checks passed |
| `mypy --platform win32 --strict`（2.3.1） | no issues |
| 变异：续租也加 epoch | 被抓到 |
| 变异：回收不加 epoch | 被抓到 |
| 变异：删掉 PENDING 的出口文字 | 被抓到 |

### 说明与代码是否一致

- 文件头第 5～7 行把 epoch 和 store 的 `version` 分开讲清楚了：`version` 只用作续租本身的比较并交换。这正是 03 第 1 节的建议。
- 新增的一句“写入检查必须和写入本身放在同一个事务里”说对了，正好对应 03 里提到的 `_require_active_lease` 先查后写（TOCTOU）问题，留给存储卡处理。
- 唯一不一致的就是发现 1：出口文字说有一条路，代码里没有这条路。

## 建议的修法（发现 1）

两种修法任选一种：

- **A（推荐）：给出口一个单独的、显式的参数。** 例如 `unknown_risk_accepted_by_decision: bool = False`。只有这个参数为真时，`UNKNOWN` 才变成 `ALLOW`，并在 `reason` 里写明“接受风险”；它不能越过 `ALIVE`。`forced_by_decision` 的含义不变（仍然只对“已证明不在”的持有者有效），原有测试也不改。补丁见 `patches/13_card148_pending_exit.patch`，+22/−3：23 个测试通过，ruff、mypy 都通过。
- **B：只改文字。** 如果设计上本来就不想让契约放行 `UNKNOWN`，就把出口改成契约以外的动作，例如“人工确认进程已结束后，重新观察，使判定变为 `PROVEN_DEAD`”，并删掉“Decision 强制回收”的说法。

A 和 B 的区别在于，“接受风险、抢占一个无法识别的进程”这件事，是由契约放行，还是只能由人在契约外处理。这是设计取舍，由你和本地 Claude 定；我倾向 A，因为出口要能被测试证明是可达的。

## 补丁 09、13 与 `d25a981` 的关系

- `09_card147_starttime_tz.patch` 已基于 `d25a981` 重新生成（+99/−2），`git apply --check` 通过：27 个测试通过（22 + 5），ruff、mypy 都通过。
- `13_card148_pending_exit.patch` 也基于 `d25a981`，可以单独应用。
- 两份一起用时，源文件部分互不冲突；测试文件里两份补丁都是在文件末尾追加，`--3way` 会把它当作冲突标出来，保留两边即可。合并后 28 个测试全部通过。
