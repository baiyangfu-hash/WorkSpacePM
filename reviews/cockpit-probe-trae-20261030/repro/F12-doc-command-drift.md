# F12 最短复现
.venv/bin/python main.py pm --help        # 仅 context/resume
for c in orient inbox plan approve verify accept close park unpark switch missions handoff takeover; do
  .venv/bin/python main.py pm $c 2>&1 | head -1
done   # 全部 No such command
