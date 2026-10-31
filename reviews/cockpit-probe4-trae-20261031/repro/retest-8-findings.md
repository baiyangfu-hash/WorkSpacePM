# 8 条重测最短复现（部署层 1.3.3-163c7a3，main bf22a621）

前置：
- 宿主仓库 `/workspace`，假项目 `ZZ-2026-903` 用 `project create --dest-dir /workspace/0100_项目` 生成（**不要用相对路径**，见 N1）。
- continuity 类命令需已登记项目；假项目不能写进宿主 registry（红线），故复制假项目到 `/tmp/probe4-ws` 并自建最小 registry（schema：`workspace-registry.v1`，字段 `project_id/project_root/development_root`）。
- 沙箱里用发布代码本体：`PYTHONPATH=/workspace/00_Infrastructure/auto_pm/releases/1.3.3-163c7a3 /workspace/.venv/bin/python -m auto_pm -w /tmp/probe4-ws ...`（加 `PYTHONDONTWRITEBYTECODE=1` 避免污染发布目录）。

```bash
# 公共前缀
R=/workspace/00_Infrastructure/auto_pm/releases/1.3.3-163c7a3
PY="env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$R /workspace/.venv/bin/python -m auto_pm"
W="-w /tmp/probe4-ws"

# F10（已失效）：相对路径
cd /workspace && .venv/bin/python main.py context resolve --path 0100_项目/ZZ-2026-903_probe4_fake   # exit 1 项目未登记（不再是 Directory does not exist）

# F12（已失效）
.venv/bin/python main.py pm --help                       # exit 0，orient/plan/approve/verify/missions 等在列
cd /tmp/probe4-ws && $PY $W pm orient ZZ-2026-903 --json # exit 0

# F15（仍成立）
cd /tmp/probe4-ws && $PY $W continuity work create --work-id W-P4-1 --pid ZZ-2026-903 --kind TEST \
  --title p4-scope --owner probe-bot --scope "0100_项目/ZZ-2026-903_probe4_fake" \
  --idempotency-key p4-k1 --read-only                     # exit 0
cd /tmp/probe4-ws && $PY $W continuity work create --work-id W-P4-1 --pid ZZ-2026-903 --kind TEST \
  --title p4-scope --owner probe-bot --scope "0100_项目/ZZ-2026-903_probe4_fake" \
  --idempotency-key p4-k1b --read-only                    # exit 1 sqlite3.IntegrityError

# F16（仍成立）
cd /tmp/probe4-ws && AUTO_PM_AGENT=trae:cn $PY $W change create --pid ZZ-2026-903 --domain SCPT \
  --nature OPT --scope LOCAL --applicant probe-bot --background probe4 --necessity f16   # exit 0
cd /tmp/probe4-ws && AUTO_PM_AGENT=trae:cn $PY $W change transition CHG-SCPT-2026-001 --to submitted --pid ZZ-2026-903   # exit 0
cd /tmp/probe4-ws && AUTO_PM_AGENT=trae:cn $PY $W change transition CHG-SCPT-2026-001 --to under_review --pid ZZ-2026-903 # exit 0
cd /tmp/probe4-ws && AUTO_PM_AGENT=trae:cn $PY $W change transition CHG-SCPT-2026-001 --to approved \
  --approver probe-bot --pid ZZ-2026-903                    # exit 0
cd /tmp/probe4-ws && AUTO_PM_AGENT=trae:cn $PY $W decision create --change-id CHG-SCPT-2026-001 \
  --approver probe-bot --pid ZZ-2026-903                    # exit 0 审批结论 approved

# F20（仍成立）
cd /tmp/probe4-ws && $PY $W continuity work create --work-id W-P4-2 --pid ZZ-2026-903 --kind TEST \
  --title p4-glob --owner probe-bot --scope "0100_项目/ZZ-2026-903_probe4_fake/**" \
  --idempotency-key p4-k2 --read-only                       # exit 0
cd /tmp/probe4-ws && printf '\nprobe4 dirty\n' >> "0100_项目/ZZ-2026-903_probe4_fake/README.md"
cd /tmp/probe4-ws && $PY $W continuity run start --run-id R-P4-1 --work-id W-P4-2 --executor probe-bot \
  --adapter local --owned "0100_项目/ZZ-2026-903_probe4_fake/README.md" \
  --declared-dirty "0100_项目/ZZ-2026-903_probe4_fake/README.md" \
  --lease-wallet --lease-seconds 120 --idempotency-key p4-r1   # exit 1 owned_paths 超出 Work scope

# F21（已失效）：过期后回收
cd /tmp/probe4-ws && $PY $W continuity run start --run-id R-P4-2 --work-id W-P4-1 --executor probe-bot \
  --adapter local --owned "0100_项目/ZZ-2026-903_probe4_fake/README.md" \
  --declared-dirty "0100_项目/ZZ-2026-903_probe4_fake/README.md" \
  --lease-wallet --lease-seconds 60 --idempotency-key p4-r2    # exit 0，READY
cd /tmp/probe4-ws && $PY $W continuity run transition --run-id R-P4-2 --to RUNNING --owner probe-bot \
  --lease-wallet --idempotency-key p4-t1                      # exit 0
sleep 135
cd /tmp/probe4-ws && $PY $W continuity run transition --run-id R-P4-2 --to SUCCEEDED --owner probe-bot \
  --lease-wallet --idempotency-key p4-t3                      # exit 1 lease 已过期
cd /tmp/probe4-ws && $PY $W continuity run reclaim --run-id R-P4-2 --claimant probe-bot-2 \
  --reason probe4-recovery                                    # 宽限期内 exit 1 REFUSE_LIVE_LEASE；过后 exit 0 ALLOW
cd /tmp/probe4-ws && $PY $W continuity run transition --run-id R-P4-2 --to SUCCEEDED \
  --owner probe-bot-2 --lease-wallet --idempotency-key p4-t4  # exit 0

# F22（已失效）
cd /tmp/probe4-ws && $PY $W continuity run start --run-id R-P4-3 --work-id W-P4-1 --executor probe-bot-2 \
  --adapter local --owned "0100_项目/ZZ-2026-903_probe4_fake/README.md" \
  --declared-dirty "0100_项目/ZZ-2026-903_probe4_fake/README.md" \
  --lease-wallet --lease-seconds 120 --idempotency-key p4-r3   # exit 1 Work 已有非终态 Run

# F24（已失效）+ N1（新发现）
cd /workspace && .venv/bin/python main.py project create --stack python --id ZZ-2026-903 \
  --name probe4_fake --dest-dir 0100_项目                     # exit 0，但写进了 releases/1.3.3-163c7a3/0100_项目（N1）
cd /workspace && .venv/bin/python main.py --resolve-only      # 随后告警并退回 previous 1.3.3-8d7d387（N1 后果）
```

清理：删除 `releases/1.3.3-163c7a3/0100_项目`、`/workspace/0100_项目`、`/tmp/probe4-ws`；再 `python -B 00_Infrastructure/auto_pm/launcher/launch.py --purge-bytecode`，`--resolve-only` 恢复 `1.3.3-163c7a3`。
