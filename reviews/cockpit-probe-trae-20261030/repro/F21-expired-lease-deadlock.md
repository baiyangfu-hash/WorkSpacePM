# F21 最短复现
# 1) 以 --lease-seconds 60 开 Run
# 2) sleep 61
.venv/bin/python main.py continuity run transition --run-id R --to VERIFYING --owner o --lease-token t --idempotency-key k1   # lease 已过期
.venv/bin/python main.py continuity lease renew --run-id R --owner o --lease-token t --lease-seconds 60 --idempotency-key k2  # lease 已过期
.venv/bin/python main.py continuity checkpoint create --checkpoint-id C --run-id R --owner o --lease-token t --summary s --evidence e --idempotency-key k3   # lease 已过期
.venv/bin/python main.py continuity handoff create --handoff-id H --checkpoint-id C --from-owner o --to-owner p --lease-token t --idempotency-key k4   # 需 checkpoint（已被 3 拦）
# 重建：同 run-id 新幂等键 → sqlite 崩溃；reclaim/settle-expired/takeover 命令不存在
