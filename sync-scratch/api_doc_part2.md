## 4. 契约专题

本节是各能力行为契约的摘要；完整设计见所引 HLSD/专题文档。

### 4.1 预设事务 API（`orca.host.preset`）

完整设计：[preset-plugin-api](../HLSD/preset-plugin-api.md)。要点：

- 三类预设共用一个**暂存-提交生命周期**：`begin_update()` 解析并绑定目标 → 返回 `PresetTransaction` → `set(key, value)` 暂存（序列化字符串，不动预设）→ `commit()` 一次整批应用。编辑的是宿主管理的 edited preset——与设置页签同一份数据、同一条更新/校验路径；**不落盘**，保存仍走用户正常流程。
- **目标解析**：`process` / `printer` 按 `preset_name`（缺省 = 当前激活预设，给的值必须是该类下拉当前可选项）；`filament` 按 1-based `slot_number`，可选 `preset_name`（给不同名字 = 为该槽换 preset，走正常 UI 选择流，含未保存编辑对话框；槽下拉不显示、但当前已分配的 preset 仍可为目标；混色虚拟槽不可为目标）。编辑 filament 预设影响所有映射到它的槽。
- `begin_update()` / `update()` 是**同步阻塞**调用：阻塞 Script worker 直到目标选择与未保存编辑对话框落定（UI 线程保持响应）。用户取消选择 → `RuntimeError`，不产生事务、不暂存任何值；不可用/非法目标 → `ValueError`。只能在 Script worker 上调用。
- `commit()` 整批校验后经 GUI 同一路径应用；失败恢复 edited preset 及其配置衍生状态（兼容标记、选择器、依赖页签、Plater）。**回滚边界**：不回滚用户已在对话框接受的决策、已完成的槽位分配切换、undo 快照、依赖预设改写、已发送给设备的内容。`begin_update()` 与 `commit()` 之间槽位映射若变化，stale 操作被拒绝。同一事务内对同一键重复 `set()` 被拒绝。
- `update(key, value)`（filament 另有 `update(slot_number, key, value)`）是单设置兼容简写，等价于以当前目标 `begin_update()` + `set()` + `commit()`。
- `orca.host.preset.bundles`：`list_ids()` 列本地预设包 ID，`reload_local(bundle_id)` 重载（同样只在 Script worker 上合法）。

典型用法（async Script 内）：

```python
tx = orca.host.preset.filament.begin_update(slot_number=2, preset_name="Generic PLA")
tx.set("filament_flow_ratio", "0.98")
result = tx.commit()   # PresetUpdateResult：目标预设、选择是否变化、槽位是否变化等
```

### 4.2 切片管线（`orca.slicing`）

完整链路：[SLICING_LOCAL](SLICING_LOCAL.md)；触发点证据见能力矩阵行 1-3。

- **挂钩语义 = 步骤之间**：在某步 `set_done()` 之后、下一步之前回调 `execute(ctx)`。插件可读**改**对象状态（例如在 `posPrepareInfill` 改 `fill_surfaces` 会级联影响后续 infill）。hook 内只能打日志——此时 `active_step_add_warning` 不可用。
- **触发面**：13 个 `Step` 中 12 个有真实触发点（顺序即管线顺序，见第 3 节 `Step` 枚举）。**例外：`posContouring` 可订阅但本 fork 永不回调**（`Print.cpp` 零引用；上游 orca/main 有 6 处。`SLICING_LOCAL` 中"13 阶段全连接"的说法按矩阵 v2 口径修正确认）。`psGCodePostProcess` 从 GUI 导出/后处理缝触发，不在 `Print::process` 内。
- **ctx 生命周期**：`ctx.print` / `ctx.object` 及其下游引用只在本次 `execute(ctx)` 内有效——不要存实例变量、不要交其他线程。网格访问用 `ctx.print.model()`（Print 的快照），不要 `orca.host.model()`。`ctx.config_value(key)` 返回序列化值（缺键 `None`）。
- **错误语义**：几何阶段 `Success`/`Skipped` 继续；`RecoverableError` 记录后继续；`FatalError` 与异常使本轮失败并失效切片图，重试重建。**G-code 阶段（4.3）对 `RecoverableError` 也中止**，与几何阶段不同。`async def execute(ctx)` 不被支持，会以 `SlicingError` 收场。
- **选择与失效**：切片前完整解析所选能力——缺包、未加载、禁用、重复选择、歧义 manifest、无效配置均**中止**切片，不"记录后跳过"。每轮比较能力实例代次与有效配置签名，配置变化或同版本重载都会使下一轮重建几何；活跃任务期间不能卸载/删除/禁用/替换所用包。回调在切片工作线程串行执行，同步 UI 请求直接抛错。
- 其他已知边界：`ExtrusionPath.points()` 返回拥有数据的只读快照（平面路径 Z 为 0，三维路径保留实际相对 Z）；旧 2D 磁盘缓存对插件/contour 拒绝读写，强制从真实模型重建。

### 4.3 G-code 后处理合同（`Step.psGCodePostProcess`）

完整合同：[GCODE_LOCAL](GCODE_LOCAL.md)。

- 执行序：传统 `post_process` 脚本 → 读各脚本的 `.output_name` → 按预设顺序执行插件 → 成功后交付工作文件。
- 该步 `ctx.print` / `ctx.object` 为 `None`；`ctx.gcode_path` 是**可原地编辑的工作文件**（每次导出/上传各得一份回调）；`ctx.host` 是目标类型；`ctx.output_name` 是最终目标名（含传统脚本改名结果）。
- 插件必须保留 `gcode_path` 对应文件（返回后宿主检查文件仍存在）；不要自行改名；只有传统脚本的 `.output_name` 改名被消费。
- `Success` / `Skipped` 继续后续能力；`RecoverableError`、`FatalError` 与异常都使本次导出失败。
- 嵌入解释器的 `os.environ` 在导入时缓存，不能据此假定同步宿主后来的 `setenv`。
- 宿主对工作文件走副本事务（成功后替换输入，失败不发布副本）；该事务不撤销插件主动修改其他文件的副作用，也不是断电耐久承诺。

### 4.4 生命周期事件（`on_lifecycle_event`）

- 全能力可用。签名 `on_lifecycle_event(event: LifecycleEvent, ctx: LifecycleEventContext)`；`ctx` 字段：`code`（`LifecycleEvtCode`：`Ok`/`Warn`/`Error`）、`id`、`name`、`source`、`index`、`dirty`。33 个事件清单见第 3 节 `LifecycleEvent` 枚举。
- **时序注意**（G-code 域）：`SliceStarted`、`SliceGeometryFinished` 来自实际 `Print::process`；`GCodeExportStarted`/`GCodeExportFinished` 来自原生生成或读取已有 G-code——都发生在插件后处理**之前**；最终 `SlicingJobComplete` 由 GUI 收到工作线程结果后派发（失败为 `Error`、取消为 `Warn`）。不能把几何完成或原生 G-code 完成当作上传完成。
- 设备域事件（`DeviceOnline`/`DeviceOffline`/`DeviceDiscovered`/`DeviceSelected`）在本树设备域为裁剪/桩，不应依赖其到达。

## 5. 裁剪域与已知限制

以下为本 fork 相对上游 OrcaSlicer 插件面的**有意裁剪**，编写跨发行版插件时不要依赖：

- **云插件域**：云端发现/订阅/更新/插件中枢为禁用桩（`cloud_plugin_service_available()` 恒 false）；云源插件动作降级为本地动作集 + Local 徽标。
- **printerAgent 域**：`orca.printer_agent`（上游 138 个 API）与 `app.selected_printer()` 未引入；依赖它们的插件在本树不兼容。
- **`app_info()` 键集**：本树 6 键（version/mode/language/app_config_version/stealth_mode/is_signed_in），无 Orca/Bambu 云登录态与 network plugin 版本；`gl_info()` 无 `core_profile`。
- **`Step.posContouring`**：可订阅、永不触发（见 4.2）。
- **快捷键簇**（#15706/#15862 等）：永不吸收；fork 自有 keyboard_shortcuts 实现。
- **非插件 web 页面树**（homepage/guide/model/login 等）：fork 自有资产线，不属插件吸收面。
- Pages 页签的实机启用/禁用/卸载/恢复循环已验证（2026-10-25 复验）；**能力级**（单 capability）toggle 路径无单测，仅代码审查覆盖。

## 6. SDK 与工具链

第 3 节的 API 清单可随时从当前源码再生成：

```sh
# 1) 构建 SDK 导出器（EXCLUDE_FROM_ALL 目标，须显式构建）
cmake --build build-port --target orca_plugin_sdk_export --config Release

# 2) 生成 SDK（输出目录必须不存在；内含 typings/*.pyi、api.json、examples、README）
python scripts/generate_plugin_sdk.py \
  --exporter build-port/tests/plugin_core/orca_plugin_sdk_export/orca_plugin_sdk_export.exe \
  --output sync-scratch/plugin-sdk-<date>

# 3) 重渲染本文第 3 节（默认读 sync-scratch/plugin-sdk-gen-1028，可传第二个参数换 SDK 目录）
python scripts/render_plugin_api_doc.py sync-scratch/api_reference_gen.md sync-scratch/plugin-sdk-<date>
```

- **编辑器补全**：把 SDK 产物里的 `typings/` 加入 Python 分析器的 extra paths。`orca` 模块由宿主注入，插件不能脱离宿主独立运行。
- **API 面门禁**：`sandboxes/api_surface_dump_plugin.py`（双 App 内省 dump）+ `sandboxes/diff_api_surface.py --expect`（基线 `expected_snapshot_557.json`）；绑定面变更须过快照 diff。
- **宿主 API 审计方法**：[HOST_API_AUDIT](HOST_API_AUDIT.md)。

## 附录 A：示例索引

均在 [examples/](examples/) 下，均可直接安装运行：

| 示例 | 能力 | 演示 |
|---|---|---|
| `native_host_hello.py` | Script | 最小插件骨架 + `orca.host.app_info()`（注意：其 `info["build"]` 引用了本树不存在的键，见附录 B 勘误） |
| `local_host.py` | Script | 宿主只读契约：`model()`/`plater()`/`preset_bundle()`/`gl_info()`/`plater().export_3mf_copy()` 单对象 3MF 导出 |
| `local_config.py` | Script | 配置五件套 + 自定义配置 UI（`orca.saveConfig`/`restoreDefaults`/`getContext` JS 桥） |
| `local_ui.py` | Script | `create_window`/`create_dock_panel`/`ProgressDialog`/`push_notification` 全套 UI 桥 |
| `local_slicing.py` | SlicingPipeline | `posSlice` 读层数据写报告（`ctx.object.layers()`） |
| `local_gcode.py` | SlicingPipeline | `psGCodePostProcess` 就地追加 G-code footer |
| `workflow_slicing.py` | SlicingPipeline | `on_lifecycle_event` 事件记录 + `posSlice` 改点几何（`layer.make_slices()`） |
| `local_page.py` | Pages | 插件页签：`get_ui()` HTML + `on_message`/`post_message` 消息桥 |
| `texture_pack/` | ResourceTexture | wheel 打包纹理资源（带资源的插件必须用 wheel） |

## 附录 B：事实来源与勘误

- **API 清单**：插件 SDK `api.json`（`live-embedded-orca` 导出，2026-10-28，基于 `build-port` 的 `orca_plugin_sdk_export`）。
- **行为契约**：[preset-plugin-api](../HLSD/preset-plugin-api.md)、[python-plugin-async-bridge](../HLSD/python-plugin-async-bridge.md)、[GCODE_LOCAL](GCODE_LOCAL.md)、[SLICING_LOCAL](SLICING_LOCAL.md)。
- **现状判定**：[capability-matrix v2](../reviews/port-python-plugins-capability-matrix.md)（每行带 file:line 证据）。
- **勘误 1**：`SLICING_LOCAL.md` 称"已连接全部 13 阶段"；按矩阵 v2 + `Print.cpp` 实测（`posContouring` 零引用），`posContouring` 订阅后永不回调。本文按矩阵口径。
- **勘误 2**：`examples/native_host_hello.py` 的 `info["build"]` 引用本树 `app_info()` 不存在的键（6 键集不含 `build`，见 HOST_API_AUDIT）；直接运行该示例会 KeyError，第 2 节示例已改用存在的键。
