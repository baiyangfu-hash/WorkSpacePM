# F20 最短复现
.venv/bin/python main.py continuity work create --work-id W-G --pid ZZ-2026-901 --kind BUG --title t --owner a --scope "0100_项目/ZZ-2026-901_cockpit_probe_fake/**" --idempotency-key kg
.venv/bin/python main.py continuity work authorize --work-id W-G --decision-id DEC-20261030-E2648A5D --idempotency-key kg2   # glob 决策包可 authorize
.venv/bin/python main.py continuity run start --run-id R-G --work-id W-G --executor a --adapter cli --owned "0100_项目/ZZ-2026-901_cockpit_probe_fake/cockpit_probe_fake/__init__.py" --worktree <绝对路径> --lease-token t --idempotency-key kg3
# → Error: owned_paths 超出 Work scope（glob 与 owned 不匹配）
