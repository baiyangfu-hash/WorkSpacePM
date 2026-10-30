# F22 最短复现
.venv/bin/python main.py continuity run start --run-id R-A --work-id W --executor a --adapter cli --owned p --worktree WT --lease-token t1 --idempotency-key ka
.venv/bin/python main.py continuity run start --run-id R-B --work-id W --executor a --adapter cli --owned p --worktree WT --lease-token t2 --idempotency-key kb
# → 两个 Run 同时存在（第二个 exit 0）
