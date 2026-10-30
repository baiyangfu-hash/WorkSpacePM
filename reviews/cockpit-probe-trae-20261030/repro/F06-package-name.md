# F6 最短复现（三种名字，仅下划线名可过）
.venv/bin/python main.py project create --stack python --id ZZ-2026-901 --name "驾驶舱探测假项目"   # exit 1 package_name 校验
.venv/bin/python main.py project create --stack python --id ZZ-2026-901 --name "cockpit-probe-fake" # exit 1 同上
.venv/bin/python main.py project create --stack python --id ZZ-2026-901 --name "cockpit_probe_fake" # exit 0 成功
.venv/bin/python main.py project create --help | grep -c package   # 0：无覆盖参数
