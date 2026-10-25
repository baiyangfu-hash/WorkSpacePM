"""
PyInstaller 打包脚本
生成独立的 Windows exe 文件
"""
import os
import sys
import shutil
import subprocess

def clean_build():
    """清理旧的构建文件"""
    dirs_to_remove = ['build', 'dist']
    for d in dirs_to_remove:
        if os.path.exists(d):
            shutil.rmtree(d)
            print(f"已清理: {d}")

def build_exe():
    """使用 PyInstaller 打包"""
    print("=" * 50)
    print("开始打包 英语学习助手...")
    print("=" * 50)
    
    # 清理旧文件
    clean_build()
    
    # 构建命令
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--name=英语学习助手',
        '--windowed',
        '--onefile',
        '--clean',
        '--noconfirm',
        f'--add-data=data{os.pathsep}data',
        '--hidden-import=PySide6.QtCore',
        '--hidden-import=PySide6.QtGui',
        '--hidden-import=PySide6.QtWidgets',
        '--hidden-import=sqlite3',
        'src/main.py'
    ]
    
    print(f"执行命令: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False, text=True, encoding="utf-8", errors="replace")
    
    if result.returncode == 0:
        print("\n" + "=" * 50)
        print("打包成功!")
        print(f"输出文件: dist/英语学习助手.exe")
        print("=" * 50)
        
        # 显示文件大小
        exe_path = 'dist/英语学习助手.exe'
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"文件大小: {size_mb:.1f} MB")
    else:
        print("\n打包失败!")
        print(f"错误码: {result.returncode}")
        if result.stderr:
            print(f"错误信息: {result.stderr}")
    
    return result.returncode

if __name__ == '__main__':
    sys.exit(build_exe())
