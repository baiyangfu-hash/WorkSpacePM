# 07 卡 147 独立审计：V04-R1 第 1 张卡，租约回收与写入 epoch 契约（项目 Claude，2026-10-17）

`<SW008>` 的含义同 05。

审计对象：提交 `23e841b`（`feat(contracts): [CHG-SCPT-2026-421] … V04-R1 card 1 (M3-V04R1A)`）。任务单说分支尖端 `23e841b` 包含卡 143～147，按顺序把它当作卡 147；这个对应关系是推断的（UNVERIFIED），卡文不在仓库里。本文是建议，不是指令。

## 结论

**不同意按现状作为第 2 张卡的基础。** 代码质量和测试本身是扎实的：18 个测试全部通过，我做的 5 个变异全部被测试抓到。但契约里有两条规则会在接入存储以后造成错误判定，需要先修：

| # | 发现 | 证据 | 严重度 |
|---|---|---|---|
| 1 | epoch 在**续租**时也增加，和“续租不增加”的结论相反；持有者每续租一次，自己在途的写入就会被判成 `STALE` | `auto_pm/contracts/lease_reclaim.py` 文件头第 5 行，以及 `next_epoch()` 的文档字符串（“a new grant, renewal or transfer”）；store 的续租会 `version=version+1`（`continuity_store.py:5905`）。测试里没有任何续租场景 | **高** |
| 2 | 启动时间用**字符串精确比较**，格式不同就判成 `PROVEN_DEAD`。同一个时刻写成 `2026-10-16T10:00:00Z` 和 `2026-10-16T10:00:00+00:00`，就会把一个活着的进程判成“已证明不在”，契约会据此允许回收 | `judge_process()` 中 `if observation.start_time != recorded.start_time: return ProcessVerdict.PROVEN_DEAD`。我实测：记录 `…Z`、观察 `…+00:00`，返回 `PROVEN_DEAD` | **高** |
| 3 | `lease_is_live()` 不校验时区：传入不带时区的 `datetime` 会抛 `TypeError`，而不是给出明确的契约错误 | 实测 `lease_is_live(datetime(2026,1,1), datetime.now().astimezone())` 抛出 `TypeError: can't compare offset-naive and offset-aware datetimes` | 低 |
| 4 | 提交只有 2 个文件，没有 `CHG-SCPT-2026-421` 的变更单文件；在 `23e841b` 上 `git grep CHG-SCPT-2026-421` 和 `V04R1A` 都是 0 处 | `git show --stat 23e841b` | 低（变更单可能在本机，随后由台账卡补录；UNVERIFIED） |
| 5 | 提交说明最后一句写“Nothing is pushed”，但这个提交已经在远端分支上 | 提交说明 | 信息 |

## 核对过程

### 提交的文件集合

`git show --stat 23e841b`：

- `<SW008>/auto_pm/contracts/lease_reclaim.py`，新增 145 行
- `<SW008>/tests/contracts/test_lease_reclaim.py`，新增 138 行

和提交说明里“product tier, 2 new files”一致；没有碰 store，也与“nothing touches the store”一致。卡文所列的文件集合无法核对，因为卡文不在仓库里（UNVERIFIED）。

### 测试是否真的在测

在隔离目录里用 Python 3.13 + pytest 单独运行这个测试文件：**18 passed**。（CI 用的是 3.12，这个文件只用标准库，版本差异不影响结果。）

变异检查（每次只改一处，跑完立即还原）：

| 变异 | 结果 |
|---|---|
| 去掉主机校验（跨机判 UNKNOWN） | 被抓到 |
| 宽限期边界 `<` 改成 `<=` | 被抓到 |
| STALE 判断放宽一档 | 被抓到 |
| PID 复用（启动时间不同）改判 UNKNOWN | 被抓到 |
| 强制收回的 Decision 不再生效 | 被抓到 |

结论：现有规则都被测试锁住了，不存在硬编码凑绿的情况。问题在于第 1、2 条，规则本身就定错了，测试也就跟着把错的规则锁住了。

### 说明与代码是否一致

- 文件头的规则、函数文档和实现三者一致，包括第 1 条的错误。
- `judge_process` 里对 `None == None` 的防护（只有记录的指纹缺字段时返回 UNKNOWN）有测试覆盖（`test_the_same_start_time_with_an_unreadable_or_different_image_is_unknown_not_dead` 的最后一个断言），做得好。
- “不读 token、不改 `expires_at`、不执行进程探测”：代码里确实没有这些操作。

## 建议的修法

1. **第 1 条**：文件头和 `next_epoch()` 的文档改为“授予、移交、回收时增加；续租不增加”。增加一个测试，用一个“授予版本不随续租变化”的小模型证明：续租 N 次以后，持有者带着授予时的 epoch 写入仍然是 `OK`。存储层怎么取这个授予版本，见 `03_v04r1_storage_design.md` 第 1 节。
2. **第 2 条**：把启动时间定义成**规范的整数**，例如 Windows 的 FILETIME 100ns 计数、Linux 的启动滴答数（见 `04_v04r1_drill_design.md` 第 1 节），字段类型改为 `int`，或者至少在契约里先规范化再比较。规范化失败（解析不了）一律 `UNKNOWN`，**绝不能是 `PROVEN_DEAD`**。补两个测试：同一时刻的不同写法判 `ALIVE`（或 `UNKNOWN`）；解析不了的字符串判 `UNKNOWN`。
3. **第 3 条**：`lease_is_live` 和 `decide_reclaim` 对不带时区的时间抛出明确的 `ValueError`，并加一个测试。

这三处都在同一个文件里，属于产品档小修，可以作为第 2 张卡的第一个提交，也可以单独作为一张修订卡。

## 卡 148 与 AGENTS2

卡 148（`d25a981`）的补审见 `07_audit_card148.md`。AGENTS2 推送后按同样方法补审，文件名为 `07_audit_agents2.md`。
