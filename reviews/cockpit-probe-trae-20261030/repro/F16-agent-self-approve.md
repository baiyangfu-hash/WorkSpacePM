# F16 最短复现
.venv/bin/python main.py change transition CHG-SPEC-2026-001 --to approved --approver cockpit-probe-bot --pid ZZ-2026-901   # agent 身份当审批人，exit 0
.venv/bin/python main.py decision create --change-id CHG-SPEC-2026-001 --approver cockpit-probe-bot --pid ZZ-2026-901       # 同上，exit 0
.venv/bin/python main.py pm approver-pin status 2>&1 | tail -1   # No such command
