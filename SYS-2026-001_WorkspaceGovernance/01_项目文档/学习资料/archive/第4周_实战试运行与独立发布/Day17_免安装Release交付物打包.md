# Day 17：免安装 Release 交付物打包

> 🎯 **今日目标**：掌握 PyInstaller 打包流程，一键生成交付给现场工控机的免安装绿色 Release 压缩包。
> ⏱️ **预计耗时**：50 分钟
> 🛠️ **前置准备**：完成 Day 16 学习。

---

## 📦 一、现场工控机交付原则

现场工控机通常无法联网，且没有安装 Python 环境。
交付标准必须是：**双击 `auto-pm.exe` 即可免安装秒开！**

---

## 🛠️ 二、一键打包流程

在工作空间根目录下执行打包构建：

```powershell
# 1. 确保虚拟环境激活
& ".\.venv\Scripts\Activate.ps1"

# 2. 执行交付物构建命令
python -m auto_pm -w "c:\Users\fubai\Documents\My_Workspace" delivery build
```

打包成功后，系统会在 `06_交付物/` 目录下生成：
* `auto-pm_V1.1.0_Release_windows_x64.zip`

解压该 zip 包后，现场人员无需配置任何环境，直接双击 `auto-pm.exe` 即可启动！

---

## 📝 今日打卡小结

1. 交付物统一收敛至 `06_交付物/` 目录。
2. 免安装 Release 绿色包可在无 Python 环境的工控机上直接运行。
