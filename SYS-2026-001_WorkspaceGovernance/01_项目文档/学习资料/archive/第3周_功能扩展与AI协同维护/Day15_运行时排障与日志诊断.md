# Day 15：运行时排障与日志诊断

> 🎯 **今日目标**：掌握 QML 控制台 Warning 与 Python 异常报错的排查技巧，学会查看日志文件。
> ⏱️ **预计耗时**：50 分钟
> 🛠️ **前置准备**：完成 Day 14 学习。

---

## 🔍 一、两种最常见的报错与速查法

### 1. 报错类型 A：QML 控件点击没反应 / 控制台有红字
* **现象**：点击界面按钮无动作，命令行输出 `TypeError: Cannot read property 'xxx' of undefined` 或 `Property 'xxx' of object is not a function`。
* **原因与速查**：
  1. 检查 Bridge 实例名称在 `setContextProperty` 里是否拼写一致；
  2. 检查 Python 函数上方是否漏写了 `@Slot()` 装饰器。

### 2. 报错类型 B：界面正常但数据不更新
* **原因与速查**：
  1. 检查 Python 中的 `Signal` 到底有没有被 `.emit()` 触发；
  2. 检查 QML 的信号监听名字是否正确（如 `calcFinished` 信号对应 QML 的 `onCalcFinished:`）。

---

## 📁 二、日志文件位置

驾驶舱运行过程中产生的详细底层诊断日志保存在：
* `.auto-pm/logs/` 目录中。

---

## 🏆 第三周结业里程碑测试

恭喜你完成了第 3 周的学习！你现在已经掌握了：
- [x] 独立搭建 QML 界面并用 Layout 布局
- [x] 编写 Python Bridge 并注入全局上下文
- [x] 在 Sidebar 注册新图标并挂载页面
- [x] 指挥工作空间 AI 技能协同维护
- [x] 快速诊断 QML / Python 运行时报错

**下周（最后一周），我们将进入实战试运行，带你走通一次真实变更并打包交付免安装软件！**
