# F15 最短复现
.venv/bin/python main.py continuity work create --work-id W-DUP --pid ZZ-2026-901 --kind BUG --title t --owner a --scope "x" --idempotency-key kA
.venv/bin/python main.py continuity work create --work-id W-DUP --pid ZZ-2026-901 --kind BUG --title t --owner a --scope "x" --idempotency-key kB
# → 裸 sqlite3.IntegrityError: UNIQUE constraint failed: work_items.work_id（exit 1）
# run-id 同型：同 run-id 换幂等键重跑 run start → UNIQUE constraint failed: run_items.run_id
