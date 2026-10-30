# F2 最短复现
sh 00_Infrastructure/auto_pm/environment/setup_env.sh
# → ERROR: No matching distribution found for aiosqlite==0.22.1（volces 镜像最高 0.21.0）
.venv/bin/python -m pip install --no-deps --index-url https://pypi.org/simple -r 00_Infrastructure/auto_pm/environment/requirements-lock-py312-win.txt   # 官方源可装齐
