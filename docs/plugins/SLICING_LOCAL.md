# 本地切片插件开发链

来源：women 分支 docs/plugins/SLICING_LOCAL.md（0aa325e101）裁剪移植。裁剪：women 的 File → Local Plugins 安装叙事与其开发选择器 GUI 细节（本树为 Plugins 对话框 + 预设侧选择，选择顺序/覆盖界面的差异见台账）；其 `tests/plugin_core/slicing_plugin.cpp` / `slicing_stages.cpp` 考卷未吸收（本树由 slic3rutils 切片管线 hook 考卷 + tests/e2e slice golden 覆盖）；`scripts/prepare_local_plugin_gui_smoke.py` 冒烟链未吸收（macOS-only，与本树 e2e 语义重复，台账记 SKIP）；TODO/VERIFICATION 引用去除。数据流/线程/阶段合同与两侧共同祖先一致，逐条保留。

## 从示例开始

1. 使用带 `ORCA_PYTHON_PLUGINS` 的构建，指定独立的 `--datadir`。
2. 经 Plugins 对话框安装 [examples/local_slicing.py](examples/local_slicing.py)。安装会注册能力，但不会自动影响任何切片。
3. 在预设侧的切片插件选择处选中 `Local slice inspector`（写入 `slicing_pipeline_plugin`）。这会修改当前工艺预设；按正常预设流程保存才能持久保存该选择。
4. 导入模型并切片。插件在真实 `posSlice` 后读取层数据，将报告写入该插件的数据目录。
5. 清空选择后，相关几何缓存失效，下一轮从原始模型重新生成。禁用/卸载包而保留选择会明确报错，需要重新启用/安装或清空选择。

## 数据流与线程

`工艺预设 → Print::apply → 配置变化失效 → Print::process → 一轮能力解析/引用锁定 → 原生阶段完成 → Python execute(ctx) → 后续原生算法`

- `slicing_pipeline_plugin` 保存有序能力名；`plugins` 保存 `<package-key>;;<capability-name>`（本地）或 `<name>;<uuid>;<capability-name>`（云，本树云域为桩）。
- `print_plugin_config_overrides` 保存固定上游的能力配置数组。它与选择、manifest 都纳入静态 PrintConfig，以确保包身份/配置变化确实使 `posSlice` 失效。
- 开始切片前完整解析所选能力。缺包、未加载、禁用、重复选择、歧义 manifest、无效配置均中止；不采用"记录后跳过"策略。
- 每轮开始时比较能力实例代次和有效配置签名；全局配置改变或同版本包重载，也会在下一次 `process()` 重建几何。
- 每轮锁定能力及有效配置快照，整个 `Print::process` 期间有效，包括两个回调之间。管理器拒绝卸载、替换、删除和改变活跃能力的启用状态；当前回调不会读取用户正在编辑的 GUI preset。
- 回调在切片工作线程串行执行，逐能力获取 GIL。同步 UI 请求会抛错以避免 UI 等待切片、切片又等待 UI 的死锁。
- `ctx.print` / `ctx.object` 和其下游引用只在本次 `execute` 内有效。不要存成实例变量或交给其他线程；容器替换也会使旧视图失效。
- Python 异常和 `FatalError` 使本轮失败并失效切片图，重试重建；`RecoverableError` 按固定上游切片合同记录消息后继续。G-code 后处理对两类错误都中止，见 [G-code 插件](GCODE_LOCAL.md)。

## 当前真实阶段

已连接全部 13 阶段：`posSlice`、`posPerimeters`、`posPrepareInfill`、`posInfill`、`posIroning`、`posSupportMaterial`、`posDetectOverhangsForLift`、`posEstimateCurledExtrusions`、`psWipeTower`、`psSkirtBrim`、`posSimplifyPath`、`posContouring`、`psGCodePostProcess`。回调受真实阶段和缓存状态控制，不保证每次 process 都触发。

`psGCodePostProcess` 在公共后处理入口、传统脚本之后执行（合同细节见 [G-code 插件](GCODE_LOCAL.md)）。`ExtrusionPath.points()` 返回拥有数据且只读的快照；平面路径 Z 为 0，三维路径保留实际相对 Z。

旧 2D 磁盘缓存对插件/contour 拒绝读写，强制从真实模型重建；普通内存暖缓存不会重复修改几何。这是已测试的兼容边界，并非磁盘缓存格式迁移完成。
