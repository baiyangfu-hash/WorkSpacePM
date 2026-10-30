# F19 最短复现
.venv/bin/python main.py continuity run transition --run-id R-PROBE-OUT --to CANCELLED --owner trae:cn --lease-token probe-token-out --idempotency-key k
# → Error: 非法 Run 状态迁移: RUNNING -> CANCELLED
