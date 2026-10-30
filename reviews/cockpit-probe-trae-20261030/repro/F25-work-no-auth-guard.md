# F25 最短复现
.venv/bin/python main.py continuity work transition --work-id W --to IN_PROGRESS --idempotency-key k
# → exit 0；命令面无 owner/lease-token 参数；Run 已 SUCCEEDED 也放行；ACCEPTED 无验收证据
