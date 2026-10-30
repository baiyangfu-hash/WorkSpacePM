# F13 最短复现
ls .git/hooks | grep -v sample | wc -l   # 0：全新克隆无任何已装钩子
grep -n "chmod +x" 00_Infrastructure/auto_pm/environment/setup_env.sh   # 只补执行位，不安装
