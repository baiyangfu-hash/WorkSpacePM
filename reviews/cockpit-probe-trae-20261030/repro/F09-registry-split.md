# F9 最短复现
.venv/bin/python main.py project show ZZ-2026-901          # exit 0 认账
.venv/bin/python main.py pm resume ZZ-2026-901 --json      # exit 1 项目未登记到 Workspace Registry
.venv/bin/python main.py context resolve --path /workspace/0100_项目/ZZ-2026-901_cockpit_probe_fake   # exit 1 同上
python3 -c "import json;d=json.load(open('SYS-2026-001_WorkspaceGovernance/workspace_registry.json',encoding='utf-8'));print([x['project_id'] for x in d['projects']])"
# registry 仅 6 项，无 ZZ-2026-901；project create 不写该文件
