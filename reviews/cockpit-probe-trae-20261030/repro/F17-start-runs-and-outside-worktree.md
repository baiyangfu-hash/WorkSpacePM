# F17 最短复现
git worktree add --detach /tmp/probe-wt-out
.venv/bin/python main.py continuity run start --run-id R-X --work-id W-X --executor a --adapter cli --owned "p" --worktree /tmp/probe-wt-out --lease-token t --idempotency-key k
# → exit 0，"state": "RUNNING"（工作区外工作树被接受；且直接 RUNNING 非 READY）
