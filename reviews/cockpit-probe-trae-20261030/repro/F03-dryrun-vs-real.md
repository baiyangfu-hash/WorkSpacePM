# F3 最短复现
.venv/bin/python main.py project create --stack python --id PROBE-0001 --name x --dry-run   # exit 0 放行
.venv/bin/python main.py project create --stack python --id PROBE-0001 --name x             # exit 1: project_id 必须匹配格式
