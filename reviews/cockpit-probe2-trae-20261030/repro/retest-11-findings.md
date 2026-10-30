# 11 条重测最短复现命令（main 17b5faf5）

约定：
- 部署层 = `.venv/bin/python main.py ...`（实际运行 1.3.3-d8f7c8b 发布快照）
- 源码层 = `PYTHONPATH="01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具" .venv/bin/python -m auto_pm -w /workspace ...`

```bash
cd /workspace
# 假项目（一次性）
PYTHONPATH="01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具" \
  .venv/bin/python -m auto_pm -w /workspace project create --stack python --id ZZ-2026-902 \
  --name probe2_fake --dest-dir 0100_项目          # exit 0，输出含 create PM_SESSION_ZZ-2026-902.md（F7）

# F9
.venv/bin/python main.py pm resume ZZ-2026-902 --json     # exit 1 项目未登记到 Workspace Registry

# F10
.venv/bin/python main.py context resolve --path 0100_项目/ZZ-2026-902_probe2_fake   # exit 2 Directory does not exist（部署层）
# 源码层同一命令 → exit 1 项目未登记（路径已能解析）

# F12
.venv/bin/python main.py pm --help                        # exit 0 只有 context/resume
# 源码层 -m auto_pm pm --help → 含 orient/inbox/plan/approve/verify/accept/close/park/unpark/switch/missions

# F15
.venv/bin/python main.py continuity work create --work-id W-P2-R2 --pid ZZ-2026-902 --kind TEST \
  --title p2-run2 --owner probe-bot --scope "0100_项目/ZZ-2026-902_probe2_fake" \
  --idempotency-key p2r-k2b --read-only                    # exit 1 裸 sqlite3.IntegrityError

# F16
AUTO_PM_AGENT=trae:cn .venv/bin/python main.py change transition CHG-SCPT-2026-001 \
  --to approved --approver probe-bot --pid ZZ-2026-902      # exit 0
AUTO_PM_AGENT=trae:cn .venv/bin/python main.py decision create \
  --change-id CHG-SCPT-2026-001 --approver probe-bot --pid ZZ-2026-902   # exit 0，生成决策包

# F20
.venv/bin/python main.py continuity work create --work-id W-P2-R1 --pid ZZ-2026-902 --kind TEST \
  --title p2-readonly --owner probe-bot --scope "0100_项目/ZZ-2026-902_probe2_fake/**" \
  --idempotency-key p2r-k1 --read-only                     # exit 0
git worktree add --detach .auto-pm/worktrees/probe2-w1 HEAD
.venv/bin/python main.py continuity run start --run-id R-P2-R1 --work-id W-P2-R1 --executor probe-bot \
  --adapter local --owned "0100_项目/ZZ-2026-902_probe2_fake/README.md" \
  --worktree /workspace/.auto-pm/worktrees/probe2-w1 --lease-token p2r-tok1 --lease-seconds 60 \
  --idempotency-key p2r-r1                                  # exit 1 owned_paths 超出 Work scope

# F21
.venv/bin/python main.py continuity run start --run-id R-P2-R2 --work-id W-P2-R2 --executor probe-bot \
  --adapter local --owned "0100_项目/ZZ-2026-902_probe2_fake/README.md" \
  --worktree /workspace/.auto-pm/worktrees/probe2-w1 --lease-token p2r-tok2 --lease-seconds 60 \
  --idempotency-key p2r-r2                                  # exit 0 RUNNING
sleep 60
.venv/bin/python main.py continuity lease renew --run-id R-P2-R2 --owner probe-bot \
  --lease-token p2r-tok2 --lease-seconds 60 --idempotency-key p2r-lr1   # exit 1 lease 已过期
.venv/bin/python main.py continuity run transition --run-id R-P2-R2 --to SUCCEEDED --owner probe-bot \
  --lease-token p2r-tok2 --idempotency-key p2r-t3           # exit 1 lease 已过期
.venv/bin/python main.py continuity checkpoint create --checkpoint-id CP-P2-1 --run-id R-P2-R2 \
  --owner probe-bot --summary probe2 --evidence git:17b5faf5 --lease-token p2r-tok2 \
  --idempotency-key p2r-cp1                                 # exit 1 lease 已过期
.venv/bin/python main.py continuity run --help              # exit 0 仅 start/transition（无 reclaim/settle-expired）

# F22
.venv/bin/python main.py continuity run start --run-id R-P2-R3 --work-id W-P2-R2 --executor probe-bot-2 \
  --adapter local --owned "0100_项目/ZZ-2026-902_probe2_fake/README.md" \
  --worktree /workspace/.auto-pm/worktrees/probe2-w1 --lease-token p2r-tok3 --lease-seconds 60 \
  --idempotency-key p2r-r3                                  # exit 0 第二个 Run 同 Work RUNNING

# F24
.venv/bin/python main.py continuity run transition --run-id R-P2-R2 --to RUNNING --owner probe-bot \
  --lease-token p2r-tok2 --idempotency-key p2r-t1          # exit 1 非法 Run 状态迁移: RUNNING -> RUNNING

# F29
PYTHONPATH="01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具" \
  .venv/bin/python -m auto_pm -w /workspace python check ZZ-2026-902   # exit 0，表内 PM_SESSION 文件 ✓
```

清理（探测结束后执行，保持工作树干净）：`git worktree remove --force .auto-pm/worktrees/probe2-w1`
