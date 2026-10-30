# F24 最短复现
.venv/bin/python main.py continuity run start ...（成功，state=RUNNING）
.venv/bin/python main.py continuity run transition --run-id R --to RUNNING --owner o --lease-token t --idempotency-key k
# → Error: 非法 Run 状态迁移: RUNNING -> RUNNING（文档规定的步骤必然报错）
