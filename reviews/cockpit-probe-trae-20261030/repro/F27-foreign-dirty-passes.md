# F27 最短复现
printf '\n# probe-dirty-marker\n' >> .auto-pm/worktrees/<wt>/README.md   # owned 之外的 tracked 脏文件
.venv/bin/python main.py continuity run start --run-id R --work-id W --executor a --adapter cli --owned <单文件> --worktree <绝对路径> --lease-token t --idempotency-key k
# → exit 0，"declared_dirty_paths": []（范围外脏文件不可见）
