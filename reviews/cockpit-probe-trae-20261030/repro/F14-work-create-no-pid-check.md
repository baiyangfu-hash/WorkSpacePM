# F14 最短复现
.venv/bin/python main.py continuity work create --work-id W-X --pid ZZZ-9999-999 --kind BUG --title t --owner a --scope "x/**" --idempotency-key k1
# → exit 0，返回 PLANNED JSON（不存在的项目也放行）
.venv/bin/python main.py change create --pid ZZZ-9999-999 --domain SPEC --nature REQ --scope LOCAL --applicant a --background b --necessity n
# → exit 1「项目不存在」（层间不一致对照）
