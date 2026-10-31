# Gemini 体检报告核实附注（存档者对照基准提交 4c71830e，2026-10-31 MST）

核实方法：读基准提交里的源码和 CI 配置，对 `report.md` 的发现逐条抽查；没跑测试、没跑驾驶舱命令、没重做变异验证。引用的是基准提交的 文件:行号。

## 总评

20 条发现里：**属实且是新的 2 条**（GM-06、GM-20，后者还被低估）；**属实但已知、且严重度被夸大 7 条**（GM-01、02、05、09、11、13、15）；**不属实或读错代码 4 条**（GM-07、08、10、16）；**其余 7 条未能确认**（GM-03、04、12、14、17、18、19）。报告里没有任何一条我能确认的 P0。

行号可靠性：抽查了 10 处，其中 4 处不对（GM-01 写 266/328、实际 333；GM-05 写 180、实际 237；GM-08 写错文件；GM-14 引用的是 import 行）。报告自称“独立审计已核对行号”，不能当作证据。

## 逐条

| 编号 | 报告级别 | 核实结论 | 依据 |
|---|---|---|---|
| GM-01 | P0 | **已知 N1，严重度夸大** | 根因属实：`auto_pm/ui/cli/project.py:333` 用 `os.path.abspath(dest_dir)`，而 `--dest-dir` 选项（262 行）没用同文件 45 行已导入的 `CallerPath`。但 Trae 第四轮实测结果是启动器告警并**退回上一版**继续用，不是“发布槽瘫痪”；“上一版也没有才无法启动”是推测。按 N1 的 P1 处理，不单列 P0。 |
| GM-02 | P1 | **已知 F21，说法不实** | 代码事实属实：已过期的租约持有者本人不能续（`continuity_store.py` 约 6216 行“lease 已过期”），也不能自己回收（约 8031 行“回收方不得是当前持有者”）。但 Trae 第四轮已在部署层实测：**换另一个身份**宽限期后 `reclaim` 返回 ALLOW 并能收口，F21 判“已失效”。“永久死锁”不成立；“持有者不能自救”是设计，且建议修法（允许原持有者自回收）会削弱“谁能回收”的联锁，改判定要用户点头。 |
| GM-03 | P1 | **未确认** | `_refuse_while_closure_prepared` 存在（7454 行附近）；`pm close` 本身就是“已验收未收口的重试入口”（`pm_closure.py:124`）；`continuity` 命令里没有 abort。报告的复现是手插数据库记录，没证明正常流程会残留 PREPARED。 |
| GM-04 | P1 | **设计分层，未核对是否登记** | 事实属实：`git_hook_enforcer.py:812-835` 的 pre-commit 只跑台账、PLC 文档、密钥扫描、忽略文件检查，不跑 pytest/ruff/mypy。重门禁在 `pm verify` 和 CI。这是分层，不是漏洞；要不要加快速 ruff 是取舍。 |
| GM-05 | P1 | **属实，但已知且写明是设计** | `.github/workflows/sw008-ci.yml:237` 的 `windows-extra` 有 `continue-on-error: true`，上方注释写明是“早期预警，已知失败待问题池理清”。行号不是 180。值得问的是“12 月前要不要转必过”，不是新缺陷。主 Windows 作业（`windows-cli-core`、`windows-cli`）没有这个标记。 |
| GM-06 | P1 | **属实，新问题** | `auto_pm/contracts/protected_files.py:34-58` 的 `PROTECTED_PATTERNS` 里没有 `docs/handover/*`，也没有 `.agents/skills.json`（有 `.trae/*`、`.cursor/rules/*`、`.agent/rules/*`、`roles/*`、`.claude/*`、`AGENTS.md`、`CLAUDE.md`）；`reviews/tools/audit_pr.py:44-46` 同样没有。`docs/handover/` 是给 Trae 的规矩文件，应入清单。**建议收下，开小修复卡。** |
| GM-07 | P1 | **读错** | `agent_worktree_service.py:53-73` 的文档字符串写明：没有任何 agent 标记返回 `""`＝用户自己的终端；标记不认识或互相矛盾返回 `"?"` 并拒绝。这是设计。报告建议“没匹配就返回 unknown 并拒绝”会把用户自己的终端也拦死。真正的问题是“不带标记的 agent 认不出来”，这是 F16 的同族（身份靠自报），解法只有批准口令。 |
| GM-08 | P1 | **不属实** | 文件与行号都不对。`contracts/protected_files.py` 里读不出 Run 创建时间一律按“新 Run＝block”处理（fail-closed）。真正“Git 读不出”是 `pm_facade_service.py:1218` 的 `_protected_file_changes` 返回 None，这正是 TD-225（#397）在修的，不在基准提交里。 |
| GM-09 | P1 | **已知 CD-01** | 批准口令未启用，Mode A 只查格式；已知。 |
| GM-10 | P1 | **不属实** | `reviews/tools/encoding_check.py:3-9` 的说明写明：正因为代码里读文件用 `errors="replace"`（DEV-ENC-001），坏编码会被藏起来，所以这个检查**严格解码**、并把文件里已存在的 U+FFFD 当作“曾被有损解码”的证据。两条规矩不冲突。 |
| GM-11 | P2 | **属实，已知 F19** | `continuity_store.py:514-526`：`RUNNING` 只能去 BLOCKED/PENDING/VERIFYING/FAILED，`VERIFYING` 也没有 CANCELLED。RUNNING→FAILED 可用，所以不是死路。 |
| GM-12 | P2 | 未核实 | 没读 `test_protected_lists_in_sync.py`。已知这个测试保证 audit_pr 清单是 protected_files 清单的子集（`protected_files.py` 注释写明）。 |
| GM-13 | P2 | **已知（口令未启用）** | `pm_handoff.py:217` 注释自己写着：伪终端和清空环境能过前面的键入检查，但过不了用户口令（`require_approval_pin`）。口令启用后即挡住。 |
| GM-14 | P2 | 未核实 | 引用的 `__main__.py:66-77` 是 import 行，不是异常处理；F15（#405 在修）同族。 |
| GM-15 | P2 | **已知 BUG-002** | `reviews/tools/test_audit_pr.py:37` 写死 `PATH=/usr/bin:/bin` 属实；“Windows 必崩”没人实测。 |
| GM-16 | P2 | **不属实** | `application/core/ai_handoff_service.py:1090-1096`：`relative_to` 外面已经是 `except (ValueError, RuntimeError): pass`，不会崩。 |
| GM-17 | P2 | 未核实 | `continuity_backup.py:384-386` 的 `os.replace` 已在 `_exclusive_quiesce` 保护内、且先 `_move_aside`；是否仍会撞 WinError 32 要 Windows 实测。 |
| GM-18 | P2 | 未复核 | 变异结果我没重做；若属实，是“服务层过期检查被下层掩盖、缺纯单元测试”，P3 级别。 |
| GM-19 | P3 | 未核实 | D7 同族。 |
| GM-20 | P3 | **属实，被低估** | 不是 7 处：`git grep` 基准提交，含 `C:\Users\fubai` 路径的文件有 **48 个**，主要在已入库的 `.auto-pm/artifacts/`、`.auto-pm/decisions/*.json`。内容是 Windows 用户名和本机目录，不含密钥。仓库是公开的，建议另开一张清理卡（改写或移出历史由用户定，涉及改 `.auto-pm/`）。 |

## 表 B、专题的抽查

- **WS-001 (3)**：`worktree_policy_service.py:40` 确有 `_BRANCH_PREFIX = "codex/"`（219 行用它拼分支名）。规矩是按 agent 分前缀（`claude/`、`trae/`…）。**值得核**：Run 工位分支是否一律叫 `codex/…`，对 Claude/Trae 的 Run 是否是错的。未核实影响。
- **专题 B**：`auto_pm/domain/change/ledger_reconciler.py` 里搜不到 `continuity`，与已知 F26（台账与 continuity 两本账互不感知）一致，不是新发现。
- **专题 A**：就是 N1，见 GM-01。
- **表 B-1 里“纯文字”那几条**（WS-002 无原话只能停“等你”、AUD-001 做的和审的分开、FIX-001 同类排查清单、零负担、DEV-TMP-001 根目录清洁、DEV-ENC-001 全库扫描）：与我们已知的“规矩多数靠自觉”判断一致，值得保留作为“12 月前把文字规矩下沉成机器检查”的候选清单；其中 AUD-001“CI 不比对 PR 作者与审计者”未逐条核实。
- **专题 C（WBS 20 项）、变异验证表**：未复核。

## 建议的处理

1. 收下并开修复卡：GM-06（受保护清单补 `docs/handover/*`、`.agents/skills.json`，两份清单一起改）、GM-20（本机路径清理，先定方案）、WS-001(3)（先核实）。
2. 归并到已知项，不另开：GM-01→N1，GM-02→F21，GM-05→windows-extra 转必过的取舍，GM-09/13→批准口令，GM-11→F19，GM-15→BUG-002。
3. 不采纳：GM-07、08、10、16。
4. 12 月前清单以协调者裁决为准；Gemini 清单第 2、4、5、9 条不要照办（见上）。
