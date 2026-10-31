import re
import os
import sys
from pathlib import Path

# 报告文件默认就是本脚本旁边的 spec_check_report_full.txt；也可以把路径作为第一个参数传入（不写死本机路径）。
REPORT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().with_name('spec_check_report_full.txt')

with open(REPORT, 'r', encoding='utf-16', errors='replace') as f:
    text = f.read()

duplicates = re.findall(r'文件列表:\s*(.*?)\n\s+建议', text, re.DOTALL)
redirect_content = "> ⚠️ **本规范已迁移至统一全局规范仓库**\n> 请跳转至 00_Obsidian_Base全局规范文件仓库 查阅对应文件，此路径已废弃。\n"

count = 0
for dup in duplicates:
    files = [f.strip() for f in dup.replace('\n', '').split(',')]
    if len(files) >= 2:
        file_obs = files[0] if 'Obsidian' in files[0] else files[1]
        file_old = files[1] if 'Obsidian' in files[0] else files[0]
        
        try:
            with open(file_old, 'w', encoding='utf-8') as f:
                f.write(redirect_content)
            print(f"Redirected: {file_old}")
            count += 1
        except Exception as e:
            print(f"ERROR writing {file_old}: {e}")

print(f"Total redirected: {count}")
