# 本地 G-code 插件

来源：women 分支 docs/plugins/GCODE_LOCAL.md（0aa325e101）裁剪移植。裁剪：women 专属安装入口（Local Plugins 对话框）改为本树 Plugins 对话框的 install-local 路径；其 `tests/plugin_core/gcode_plugin.cpp` 考卷未吸收（本树 gcode 挂点域由 slic3rutils 切片管线考卷 + tests/e2e slice golden 覆盖）；VERIFICATION.md 引用去除。执行合同本体与两侧共同祖先一致，逐条保留。

示例：[examples/local_gcode.py](examples/local_gcode.py)。安装后在 Plugins 对话框安装本地包，在切片插件选择处选中 `Local G-code footer`（选择写入工艺预设 `slicing_pipeline_plugin`，按正常预设流程保存持久化），再切片导出。该能力与几何切片使用同一 `SlicingPipelineCapabilityBase`，通过 `ctx.step` 判断执行阶段。

## 执行合同

传统 `post_process` 脚本 → 读取脚本的 `.output_name` → 按预设顺序执行插件 → 成功交付工作文件。

- `ctx.step == psGCodePostProcess`；`ctx.print`、`ctx.object` 为 `None`。
- `ctx.gcode_path` 是可原地编辑的工作文件；`ctx.host` 是目标类型；`ctx.output_name` 是最终目标名，包含传统脚本的改名结果。
- `ctx.config_value(key)` 返回序列化字符串，缺键返回 `None`；不是自动转换的 Python 数字。
- 读取目标名使用 `ctx.output_name`。嵌入解释器的 `os.environ` 在导入时缓存，不能据此假定会同步宿主后来的 `setenv`。
- `Success`、`Skipped` 继续后续能力；`RecoverableError`、`FatalError` 和异常都使本次导出失败。这与几何阶段的 RecoverableError 处理不同。
- 插件必须保留 `gcode_path` 对应文件。插件返回后检查文件仍存在；不要自行改名。只有传统脚本的 `.output_name` 改名被消费。
- 整组能力、有效配置在传统脚本开始前解析并锁定；活跃任务期间不能卸载、删除、禁用或替换所用包。后台回调拒绝同步 UI。

## Snapmaker 接入与回滚

公共入口仍为 `libslic3r/GCode/PostProcessor.cpp::run_post_process_scripts`。非 BBL 文件导出用副本，预览继续读取原始生成文件；非 BBL 上传及 BBL 兼容路径要求输入路径保持不变。插件模式下这些路径也先处理副本，成功后替换输入；失败时不发布副本，也不修改传入的目标名。兼容 BBL 调用把源路径和目标名传成同一个字符串的情况。

此事务覆盖宿主工作文件与参数，不能撤销插件主动修改其他文件的副作用，也不代表断电耐久性承诺。外部脚本单独使用时保留既有工作方式。

## 生命周期

`SliceStarted`、`SliceGeometryFinished` 来自实际 `Print::process`；`GCodeExportStarted`、`GCodeExportFinished` 来自原生生成或读取已有 G-code。这些 G-code 事件发生在插件后处理之前。最终 `SlicingJobComplete` 由 GUI 接收到工作线程结果后派发，失败为 Error，取消为 Warn。不能把几何完成或原生 G-code 完成当作上传完成。
