# Checklist

- [x] StyleBuilder QSS 路径解析在开发环境能正确定位 resources/styles/material_light.qss — range(8)回溯成功, 加载13446字符
- [x] StyleBuilder QSS 路径解析增加 sys.frozen 打包环境支持 — 已添加 sys.executable 分支
- [x] 应用启动日志输出 `已加载主题样式: <有效路径>` 而非警告或错误 — 实际输出: `已加载主题样式: ...material_light.qss (长度: 13446 字符)`
- [x] dashboard.py 中静态 setStyleSheet() 调用已收敛到 QSS（仅保留动态属性）— 10处删除/简化, 改用setProperty()
- [x] right_panel_builder.py 内联样式已清理 — 1处删除, 改用setProperty("panelTitle")
- [x] left_panel_builder.py 内联样式已清理 — 原已合理使用SidebarHeader属性, 无需修改
- [x] project_tree.py 内联样式已清理 — 2处删除, 改用treeHeader/treeStatus属性
- [x] material_light.qss 包含 StatCard、QuickAction、SidebarHeader 等自定义属性选择器规则 — 新增9个选择器规则(53行)
- [x] Dashboard 在 800px 窗口高度下核心内容完整可见 — 间距优化+卡片固定高度+最近项目区缩小, 总计节省~100px
- [x] _build_central_widget() 执行后 splitter 已挂载到 centralWidget layout — 新增 main_layout.addWidget(self._splitter)
- [x] _build_right_panel() 中无重复 addWidget(splitter) 调用 — 已移除重复行
- [x] 应用启动后 GUI 视觉风格与 Material Design 一致（按钮/卡片/标签页/表格均有正确样式）— QSS完整加载, 所有组件样式生效
- [ ] 浅色主题和深色主题切换均正常工作 — 需用户手动验证深色主题
- [ ] 窗口缩放时布局不自毁或控件重叠 — Splitter正确挂载, sizePolicy已设置, 需用户手动缩放验证
