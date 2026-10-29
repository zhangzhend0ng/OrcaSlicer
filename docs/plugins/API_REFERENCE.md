# Snapmaker Orca 本地插件接口文档

> **基准**：`port/python-plugins` 分支（2026-10-29）。API 清单来自真实嵌入绑定的活体导出（`source: live-embedded-orca`，11 个模块、186 个顶层成员），非手抄源码。
> **维护**：第 3 节由 `scripts/render_plugin_api_doc.py` 从插件 SDK 的 `api.json` 渲染生成，**不要手改**；能力面有无变化以 [capability-matrix](../reviews/port-python-plugins-capability-matrix.md) 为准，本文第 5 节是其摘要。
> **适用边界**：本文只覆盖本地插件域（Local）。云插件域在本树为禁用桩，设备/printer-agent 域整体未引入（见第 5 节）。

## 1. 总览

### 1.1 插件模型（capability）

插件是一个 Python 包：单个 `.py` 文件，或一个标准 wheel（需要附带资源文件时必须用 wheel——单文件安装不会携带同目录资源）。文件头部用 PEP 723 内联元数据声明插件身份：

```python
# /// script
# requires-python = ">=3.12"
# dependencies = []
# [tool.orcaslicer.plugin]
# name = "My Plugin"
# version = "1.0.0"
# ///
```

宿主加载模块时通过两个符号发现插件：

- `@orca.plugin` 装饰器标记**唯一的包类**（`orca.base` 的子类）；
- 包类的 `register_capabilities()` 里用 `orca.register_capability(Cls)` 注册各能力类。

能力（capability）是插件的功能单元，每个能力类继承一种基类并覆写其执行方法。本树可用的 Python 能力基类共六种：

| 基类 | PluginType | 执行入口 | 用途 |
|---|---|---|---|
| `orca.script.ScriptPluginCapabilityBase` | `Script` | `execute()` | 通用后台任务（可在插件对话框/快速拨盘触发） |
| `orca.slicing.SlicingPipelineCapabilityBase` | `SlicingPipeline` | `execute(ctx)` | 切片管线挂钩（含 G-code 后处理） |
| `orca.pages.PagesPluginCapabilityBase` | `Pages` | `get_ui()` / `on_message()` | 应用内插件页签（HTML） |
| `orca.resource_texture.ResourceTexturePluginCapabilityBase` | `ResourceTexture` | （见基类成员） | 资源纹理包 |
| `orca.importer.ImporterPluginCapabilityBase` | `Importer` | `import_file(path)` | 格式导入（fork 先行，provisional）：把无内置加载器的格式转换成宿主可读网格文件 |
| `orca.exporter.ExporterPluginCapabilityBase` | `Exporter` | `export_file(ctx)` | 格式导出（fork 先行，provisional）：经 File>Export 菜单触发，ctx 拉取模型快照 |

`PluginType` 枚举中 `Analysis`/`PrinterConnection`/`Visualization` 仍为保留值（本树未提供 Python 基类，不要依赖）；`Importer`/`Exporter` 已由 fork 先行实现（见上表，契约标注 provisional，上游落地后按台账对账）。

所有能力类都继承 `orca.PythonPluginBase`，通用可覆写方法：

- **身份**：`get_name()`（显示名）、`get_type()`（能力类型，基类已定）；
- **生命周期**：`on_load()` / `on_unload()` / `on_lifecycle_event(event, ctx)`（全能力可用，事件表见 4.4）；
- **配置**（每个能力都自带一份持久 JSON 配置）：`get_config()` 读、`save_config(json_str)` 写、`get_default_config()` 定义"恢复默认"写入的内容、`has_config_ui()` + `get_config_ui()` 用自定义 HTML 页替换宿主默认 JSON 编辑器、`get_config_version()` 供配置迁移。配置页 JS 侧用 `window.orca.getConfig()/saveConfig()/restoreDefaults()/getContext()`。

执行结果统一用 `orca.ExecutionResult` 返回：`ExecutionResult.success(message, data)`、`.skipped(message)`、`.failure(status, message, data)`；`status` 取 `PluginResult`（`Success`/`Skipped`/`RecoverableError`/`FatalError`）。不同能力对四种状态的后续处理不同（见 4.2/4.3）。

### 1.2 打包、发现与安装

- **发现目录**：纯本地 `{data_dir}/orca_plugins/`，无云端发现。
- **安装**：Plugins 对话框的 install-local 路径，装 wheel 或单文件。`orca.host.plugin.storage()` 返回当前插件已安装目录，插件自建数据建议写在那里。
- **纹理包**：资源必须放在插件目录内；宿主校验资源归属、拒绝跨目录符号链接。卸载后库中条目消失，已复制进模型/预览的图像仍由宿主持有。
- **切片插件的选择**不是全局开关：在工艺预设的切片插件选择器里勾选，写入该预设的 `slicing_pipeline_plugin` 键，随正常预设保存而持久化。清空选择会使相关几何缓存失效（下轮从原始模型重建）；禁用/卸载被选中的包会明确报错。

### 1.3 权限沙箱

插件运行在审计沙箱内：文件系统读写、网络（HTTP/套接字）、进程启动、开线程都会被归因到当前插件并在未授权时拦截。在 `register_capabilities()` 里调用：

```python
orca.request_permissions(
    fs_read=["C:/data/in/*"],          # 只读目标（路径）
    fs_readwrite=["..."],              # 读写目标（路径）
    network_http=["https://api.x.com"],  # HTTP 目标（URL）
    network_socket=["..."],            # 套接字目标（地址）
    process=["ffmpeg"],                # 进程目标（命令）
    threading=False,                   # 是否允许开线程
)
```

要点（完整语义见第 3 节该函数的绑定文档）：

- 询问发生在 `register_capabilities()` 返回之后、任何能力实例创建之前，**一次弹窗问完**；拒绝则整个插件加载中止。
- 已授权的目标不会重复询问；授权经 `permissions.events` 桶落盘记忆，重启后仍有效。
- 文件目标尾部可加 `/*` 授权整棵目录树；`*` 是唯一通配符、只认末段；读授权不覆盖写授权；符号链接不能把树授权带出授权范围；宿主按名字/关键字拒绝的路径永远拒绝。
- **非主线程首次必拒**：权限弹窗在能力工作线程上是 fail-closed 的——第一次调用会收到拒绝（同时弹窗并记住用户的选择），第二次起按用户决定放行。Script 能力跑在后台 worker 上，因此遵循这个模式。

### 1.4 执行线程模型

- **Script 能力**：每次调用起一个专属 worker 线程。`def execute()` 同步跑完；`async def execute()` 在为本次调用新建的 asyncio loop 上驱动。调用方（UI）从不阻塞，结果经完成回调上报。
- **宿主 UI 调用的编组**：`orca.host.ui.*`、`orca.host.preset.*` 等需要在 UI 线程落地的调用走阻塞式 marshal——Script worker 阻塞等 UI 线程执行完返回，UI 线程保持响应。因此这些调用**只在 Script worker 上合法**，不能在 UI 线程或切片 hook 里调用（绑定会抛错或死锁）。
- **切片管线能力**：同步跑在切片工作线程上，逐能力取 GIL，无 async 路径（`async def execute(ctx)` 会以切片错误收场）。

四条死锁禁令（引自 async-bridge 设计，违反即死锁或报错）：

1. 绝不让 UI 线程等待插件工作完成（Script 启动路径全部异步化）。
2. **切片 hook 内绝不能调 `orca.host.ui.*`**（UI 线程可能正停在切片 worker 上）。
3. 宿主 UI 调用只从 Script worker 发起。
4. 没有指针跨调用边界存活：`begin_update()` 返回的是拷贝值；`ctx.print`/`ctx.object` 只在一次 `execute(ctx)` 内有效。

### 1.5 能力矩阵摘要

"插件能不能用 X"的权威判定见 [capability-matrix](../reviews/port-python-plugins-capability-matrix.md)（带 file:line 证据）。摘要：

| 域 | 状态 |
|---|---|
| 切片管线订阅（12/13 步骤真实触发） | 支持 |
| `Step.posContouring` | **可订阅但本 fork 永不触发**（Print.cpp 零引用） |
| G-code 后处理（`psGCodePostProcess`） | 支持 |
| Pages 页签（含会话中装载/卸载循环） | 支持 |
| resourceTexture / script 能力 | 支持 |
| 权限审计沙箱（fs/socket/process，授权落盘） | 支持 |
| 插件发现与安装 | 支持（仅本地目录） |
| 云插件域（发现/订阅/更新/中枢） | 裁剪（禁用桩） |
| printerAgent 域（`orca.printer_agent`、`selected_printer()`） | 裁剪（未引入） |
| 快捷键簇、非插件 web 页面树 | 裁剪（不属插件吸收面） |

## 2. 快速上手

最小可跑插件（Script 能力，改写自 `examples/native_host_hello.py`；注意该示例第 20 行的 `info["build"]` 引用了本树 `app_info()` 不存在的键——6 键为 version/mode/language/app_config_version/stealth_mode/is_signed_in——此处已改用存在的键）：

```python
# /// script
# requires-python = ">=3.12"
# dependencies = []
# [tool.orcaslicer.plugin]
# name = "Native Host Hello"
# version = "1.0.0"
# ///
import orca


class Hello(orca.script.ScriptPluginCapabilityBase):
    def get_name(self):
        return "Native Host Hello"

    def execute(self):
        info = orca.host.app_info()
        return orca.ExecutionResult.success(
            f"Hello from Snapmaker Orca {info['version']} ({info['mode']})",
            info["language"],
        )


@orca.plugin
class Package(orca.base):
    def register_capabilities(self):
        orca.register_capability(Hello)
```

使用步骤：

1. 用带 `ORCA_PYTHON_PLUGINS` 的构建，启动时指定独立 `--datadir`（隔离测试配置）。
2. Plugins 对话框 → 安装本地包 → 选中上述 `.py`（或 `uv build --wheel` 后装 wheel）。
3. Script 能力在插件对话框中运行；切片管线能力的启用还需在工艺预设的切片插件选择器里勾选（写入 `slicing_pipeline_plugin`，随预设保存持久化），再导入模型切片即可触发。

编辑器补全：把生成的 SDK `typings/` 目录加进 Python Language Server 的 extra paths（生成方法见第 6 节），即可对 `orca.*` 全量补全与类型检查；`orca` 模块由宿主提供，脱离宿主不能独立运行。

<!-- 本节由脚本渲染生成：scripts/render_plugin_api_doc.py ← 插件 SDK api.json（live-embedded-orca 导出）。

<!-- 本节由脚本渲染生成：scripts/render_plugin_api_doc.py ← 插件 SDK api.json（live-embedded-orca 导出）。
     API 面变化时：重建 orca_plugin_sdk_export → scripts/generate_plugin_sdk.py 重新导出 → 重跑本脚本。不要手改本节。 -->
## 3. API 参考

来源：真实嵌入绑定导出（`source: live-embedded-orca`，13 个模块、194 个顶层成员）。签名取自 pybind11 活体导出；
说明文字取自 C++ 绑定原文档。`.pyi` 存根见 SDK 生成产物（第 6 节），可给编辑器提供同等补全。

### 模块 `orca` — 插件模型核心

host/pages/resource_texture/script/slicing 子模块见后文各节。

- **PluginType** 枚举值：`Analysis`、`Exporter`、`Importer`、`Pages`、`PrinterConnection`、`ResourceTexture`、`Script`、`SlicingPipeline`、`Unknown`、`Visualization`
- **LifecycleEvent** 枚举值：`DeviceDiscovered`、`DeviceOffline`、`DeviceOnline`、`DeviceSelected`、`GCodeExportFinished`、`GCodeExportStarted`、`NewProject`、`ObjectAdded`、`ObjectChanged`、`ObjectDeleted`、`ObjectRenamed`、`ObjectTransformed`、`PlateCreated`、`PlateDeleted`、`PlateRenamed`、`PlateSelected`、`PresetSaved`、`PresetSelected`、`PrintJobFinished`、`PrintJobStarted`、`PrintStateChanged`、`ProjectAfterSave`、`ProjectBeforeSave`、`ProjectClosed`、`ProjectDirtyChanged`、`ProjectOpened`、`SendJobFinished`、`SendJobStarted`、`SliceGeometryFinished`、`SliceStarted`、`SlicingJobComplete`、`UploadFinished`、`UploadStarted`
- **LifecycleEvtCode** 枚举值：`Error`、`Ok`、`Warn`
- **PluginResult** 枚举值：`FatalError`、`RecoverableError`、`Skipped`、`Success`

**函数**

- **`plugin(arg0: object) -> object`**
  
  Mark the single plugin package class (the orca.base subclass) for this file.
- **`register_capability(arg0: object) -> None`**
  
  Register a PluginCapability subclass while OrcaSlicer loads your module.
- **`request_permissions(fs_read: collections.abc.Sequence[str] = [], fs_readwrite: collections.abc.Sequence[str] = [], network_http: collections.abc.Sequence[str] = [], network_socket: collections.abc.Sequence[str] = [], process: collections.abc.Sequence[str] = [], threading: bool = False, network: collections.abc.Sequence[str] = []) -> None`**
  
  Request permissions while OrcaSlicer loads your module.

Each bucket takes the target strings the plugin expects the corresponding audit event to
report: filesystem paths for fs_read and fs_readwrite, URLs for network_http, socket addresses
for network_socket, and commands for process. threading=True requests permission to start
threads. Targets already granted to the plugin are not asked for again.

A filesystem target may end in "/*" to grant a whole directory tree, for example
"/path/to/folder/*". That covers the folder itself and every path beneath it, at any depth.
"*" is the only wildcard and is recognized only as the final path component; a "*" anywhere
else in a target is an ordinary character. Wildcards apply to fs_read and fs_readwrite only,
and a grant in one of those buckets never authorizes the other direction. Tree grants are
matched on canonical paths, so a symlink below the granted folder does not extend the grant
outside it. Paths the host denies by name or keyword stay denied even when a wildcard covers
them.

The host presents one request to the user after register_capabilities() returns and before any
capability instance is created. Denying the request aborts the plugin load.


#### `ExecutionResult`

- 构造：**`__init__(self: orca.ExecutionResult) -> None`**
- 构造：**`__init__(self: orca.ExecutionResult, arg0: orca.PluginResult, arg1: str, arg2: str) -> None`**
- **`data`** (property)
- **`failure`** (staticmethod)
- **`message`** (property)
- **`skipped`** (staticmethod)
- **`status`** (property)
- **`success`** (staticmethod)

#### `LifecycleEvent`

- 构造：**`__init__(self: orca.LifecycleEvent, value: typing.SupportsInt) -> None`**
- **`DeviceDiscovered`** (LifecycleEvent)
- **`DeviceOffline`** (LifecycleEvent)
- **`DeviceOnline`** (LifecycleEvent)
- **`DeviceSelected`** (LifecycleEvent)
- **`GCodeExportFinished`** (LifecycleEvent)
- **`GCodeExportStarted`** (LifecycleEvent)
- **`NewProject`** (LifecycleEvent)
- **`ObjectAdded`** (LifecycleEvent)
- **`ObjectChanged`** (LifecycleEvent)
- **`ObjectDeleted`** (LifecycleEvent)
- **`ObjectRenamed`** (LifecycleEvent)
- **`ObjectTransformed`** (LifecycleEvent)
- **`PlateCreated`** (LifecycleEvent)
- **`PlateDeleted`** (LifecycleEvent)
- **`PlateRenamed`** (LifecycleEvent)
- **`PlateSelected`** (LifecycleEvent)
- **`PresetSaved`** (LifecycleEvent)
- **`PresetSelected`** (LifecycleEvent)
- **`PrintJobFinished`** (LifecycleEvent)
- **`PrintJobStarted`** (LifecycleEvent)
- **`PrintStateChanged`** (LifecycleEvent)
- **`ProjectAfterSave`** (LifecycleEvent)
- **`ProjectBeforeSave`** (LifecycleEvent)
- **`ProjectClosed`** (LifecycleEvent)
- **`ProjectDirtyChanged`** (LifecycleEvent)
- **`ProjectOpened`** (LifecycleEvent)
- **`SendJobFinished`** (LifecycleEvent)
- **`SendJobStarted`** (LifecycleEvent)
- **`SliceGeometryFinished`** (LifecycleEvent)
- **`SliceStarted`** (LifecycleEvent)
- **`SlicingJobComplete`** (LifecycleEvent)
- **`UploadFinished`** (LifecycleEvent)
- **`UploadStarted`** (LifecycleEvent)
- **`name`** (property)
- **`value`** (property)

#### `LifecycleEventContext`

- 构造：**`__init__(self: orca.LifecycleEventContext) -> None`**
- **`code`** (property)
- **`device_id`** (property)
- **`dirty`** (property)
- **`id`** (property)
- **`index`** (property)
- **`job_id`** (property)
- **`msg`** (property)
- **`name`** (property)
- **`previous_name`** (property)
- **`source`** (property)

#### `LifecycleEvtCode`

- 构造：**`__init__(self: orca.LifecycleEvtCode, value: typing.SupportsInt) -> None`**
- **`Error`** (LifecycleEvtCode)
- **`Ok`** (LifecycleEvtCode)
- **`Warn`** (LifecycleEvtCode)
- **`name`** (property)
- **`value`** (property)

#### `PluginContext`

- 构造：**`__init__(self: orca.PluginContext) -> None`**
- **`orca_version`** (property)

#### `PluginResult`

- 构造：**`__init__(self: orca.PluginResult, value: typing.SupportsInt) -> None`**
- **`FatalError`** (PluginResult)
- **`RecoverableError`** (PluginResult)
- **`Skipped`** (PluginResult)
- **`Success`** (PluginResult)
- **`name`** (property)
- **`value`** (property)

#### `PluginType`

- 构造：**`__init__(self: orca.PluginType, value: typing.SupportsInt) -> None`**
- **`Analysis`** (PluginType)
- **`Exporter`** (PluginType)
- **`Importer`** (PluginType)
- **`Pages`** (PluginType)
- **`PrinterConnection`** (PluginType)
- **`ResourceTexture`** (PluginType)
- **`Script`** (PluginType)
- **`SlicingPipeline`** (PluginType)
- **`Unknown`** (PluginType)
- **`Visualization`** (PluginType)
- **`name`** (property)
- **`value`** (property)

#### `PythonPluginBase`

- 构造：**`__init__(self: orca.PythonPluginBase) -> None`**
- **`get_config(self: orca.PythonPluginBase) -> str`**
  
  Return this capability's stored config as a JSON string — json.loads() it to use.
"{}" if it has never been saved, so the parsed result is always indexable.
- **`get_config_ui(self: orca.PythonPluginBase) -> str`**
  
  Override to return the custom configuration UI as an HTML string. Only called when
has_config_ui() is True; an empty result falls back to the default JSON editor.
Inside the page, use window.orca.getConfig()/saveConfig() to reach this same config.
- **`get_config_version(self: orca.PythonPluginBase) -> str`**
  
  Return the plugin version that last wrote this capability's config, so a newer
release can spot a stale config and migrate it. Empty string if never saved.
- **`get_default_config(self: orca.PythonPluginBase) -> str`**
  
  Override to return the config that the Config tab's "Restore defaults" action writes
back, as a dict. Optional: without it the action stores an empty config, which already
restores the defaults of a capability that keeps its stored config sparse and applies
its own defaults on read. Override it to write an explicit starting config instead.
Calling it returns that config as a JSON string.
- **`get_name(self: orca.PythonPluginBase) -> str`**
- **`get_type(self: orca.PythonPluginBase) -> orca.PluginType`**
- **`has_config_ui(self: orca.PythonPluginBase) -> bool`**
  
  Override to return True to replace the host's default JSON editor with your own HTML
UI, returned by get_config_ui(). Every capability is configurable and appears in the
Plugins dialog's Config tab regardless; this only chooses how its config is edited.
- **`on_lifecycle_event(self: orca.PythonPluginBase, arg0: orca.LifecycleEvent, arg1: orca.LifecycleEventContext) -> None`**
  
  Override to react to an application lifecycle moment (LifecycleEvent) and its
LifecycleEventContext payload. Available on every capability type.
- **`on_load(self: orca.PythonPluginBase) -> None`**
- **`on_unload(self: orca.PythonPluginBase) -> None`**
- **`save_config(self: orca.PythonPluginBase, config: str) -> bool`**
  
  Persist this capability's config, given as a JSON string (e.g. json.dumps(cfg)).
The plugin key, capability name and version are supplied by the host. Returns False if
the string is not valid JSON, or if the config file could not be written.

#### `base`

- 构造：**`__init__(self: orca.base) -> None`**
- **`register_capabilities(self: orca.base) -> None`**

（子模块：`exporter`、`host`、`importer`、`pages`、`resource_texture`、`script`、`slicing`，见下文。）

### 模块 `orca.host` — 宿主应用面（模型/几何/预设/应用信息）

`plate` / `plugin` / `preset` / `preset.bundles` / `ui` 子模块见后文各节。

- **int** 常量（int）：`API_VERSION`
- **SurfaceType** 枚举值：`stBottom`、`stBottomBridge`、`stCount`、`stInternal`、`stInternalAfterExternalBridge`、`stInternalBridge`、`stInternalSolid`、`stInternalVoid`、`stPerimeter`、`stSecondInternalBridge`、`stTop`

**函数**

- **`app_info() -> dict`**
  
  The running app: version, mode, language, app_config_version (the version that wrote the app config before this run, empty when there was none), stealth_mode and is_signed_in. Upstream also reports the Orca/Bambu cloud states and the network plugin version; those agents are trimmed on this fork.
- **`app_language() -> str`**
- **`data_dir() -> str`**
  
  The application data directory (presets, caches, plugin storage live under it). Fork addition; accessing files under it still requires filesystem permission.
- **`flush_volume_between(from_rgba: tuple, to_rgba: tuple, min_flush: typing.SupportsInt, max_flush: typing.SupportsInt) -> int`**
  
  The stock flush estimate between two filament colors — the same color-distance calculation Sidebar's auto-calculation uses. Pure function, any thread. Returns mm^3.
- **`get_flush_volumes() -> dict`**
  
  The project's flushing volumes: {n, matrix (row-major N x N), vector, multiplier}. UI thread only.
- **`gl_info() -> object`**
  
  OpenGL vendor, renderer, version and glsl_version of the 3D view; None before it has been created. Upstream also reports core_profile; this fork's GLInfo does not track it.
- **`model() -> orca.host.Model`**
- **`plater() -> orca.host.Plater`**
- **`preset_bundle() -> orca.host.PresetBundle`**
- **`set_flush_volumes(matrix: collections.abc.Sequence[typing.SupportsFloat] | None = None, vector: collections.abc.Sequence[typing.SupportsFloat] | None = None, multiplier: typing.SupportsFloat | None = None) -> None`**
  
  Overwrite parts of the flushing volumes (all optional): matrix must match get_flush_volumes()'s N x N size, vector its N, multiplier in (0, 100]. Runs the auto-calculation's persistence tail (selection snapshot export, dirty mark, background reslice). UI thread only.


#### `Axis`

- 构造：**`__init__(self: orca.host.Axis, value: typing.SupportsInt) -> None`**
- **`X`** (Axis)
- **`Y`** (Axis)
- **`Z`** (Axis)
- **`name`** (property)
- **`value`** (property)

#### `BoundingBox`

- **`center`** (property)
- **`defined`** (property)
- **`max`** (property)
- **`min`** (property)
- **`radius`** (property)
- **`size`** (property)

#### `ConversionType`

- 构造：**`__init__(self: orca.host.ConversionType, value: typing.SupportsInt) -> None`**
- **`FromInch`** (ConversionType)
- **`FromMeter`** (ConversionType)
- **`ToInch`** (ConversionType)
- **`ToMeter`** (ConversionType)
- **`name`** (property)
- **`value`** (property)

#### `ExPolygon`

- 构造：**`__init__(self: orca.host.ExPolygon, contour: object, holes: object = None) -> None`**
  
  Construct from a Polygon/ndarray contour and optional list of hole Polygons/ndarrays. Orientation is normalized (contour CCW, holes CW).
- **`area(self: orca.host.ExPolygon) -> float`**
- **`contains(self: orca.host.ExPolygon, point: orca.host.Point) -> bool`**
- **`contour`** (property)
  
  Outer contour (CCW). Read returns a live Polygon ref; assign a Polygon/ndarray to replace it.
- **`diff_ex(self: orca.host.ExPolygon, other: orca.host.ExPolygon) -> list[orca.host.ExPolygon]`**
  
  This minus `other`. Returns [ExPolygon].
- **`douglas_peucker(self: orca.host.ExPolygon, tolerance: typing.SupportsFloat) -> None`**
- **`holes`** (property)
  
  Hole contours (CW) as [Polygon] references (in-place editable). set_holes replaces them.
- **`intersection_ex(self: orca.host.ExPolygon, other: orca.host.ExPolygon) -> list[orca.host.ExPolygon]`**
  
  Intersection with `other`. Returns [ExPolygon].
- **`is_valid(self: orca.host.ExPolygon) -> bool`**
- **`num_contours(self: orca.host.ExPolygon) -> int`**
- **`offset(self: orca.host.ExPolygon, delta: typing.SupportsInt) -> list[orca.host.ExPolygon]`**
  
  Clipper offset by `delta` scaled units (negative shrinks). Returns [ExPolygon].
- **`rotate(self: orca.host.ExPolygon, angle: typing.SupportsFloat) -> None`**
- **`rotate(self: orca.host.ExPolygon, angle: typing.SupportsFloat, center: orca.host.Point) -> None`**
- **`scale(self: orca.host.ExPolygon, factor: typing.SupportsFloat) -> None`**
- **`set_holes(self: orca.host.ExPolygon, holes: object) -> None`**
  
  Replace all holes. Invalidates prior hole refs (C++ vector semantics).
- **`simplify(self: orca.host.ExPolygon, tolerance: typing.SupportsFloat) -> list[orca.host.ExPolygon]`**
  
  Return simplified geometry as [ExPolygon].
- **`translate(self: orca.host.ExPolygon, x: typing.SupportsFloat, y: typing.SupportsFloat) -> None`**
- **`union_ex(self: orca.host.ExPolygon, other: orca.host.ExPolygon) -> list[orca.host.ExPolygon]`**
  
  Union with another ExPolygon. Returns [ExPolygon].

#### `ExtrusionEntity`

- **`role`** (property)
  
  Extrusion role as a human-readable string (e.g. "Outer wall", "Sparse infill").

#### `ExtrusionEntityCollection`

- **`entities`** (property)
  
  Child entities. Each is handed to you as its concrete type only when that type is registered; a child whose concrete type is unregistered (e.g. a scarf-seam ExtrusionLoopSloped) surfaces as a bare ExtrusionEntity exposing only .role. Use flatten_paths() to robustly reach every ExtrusionPath leaf.
- **`flatten_paths(self: object) -> list`**
  
  Every leaf ExtrusionPath under this tree (collections recursed into, loops/multipaths decomposed).
- **`size(self: orca.host.ExtrusionEntityCollection) -> int`**

#### `ExtrusionLoop`

- **`paths`** (property)
  
  The loop's constituent paths as [ExtrusionPath].

#### `ExtrusionMultiPath`

- **`paths`** (property)
  
  The multipath's constituent paths as [ExtrusionPath].

#### `ExtrusionPath`

- **`height`** (property)
- **`mm3_per_mm`** (property)
- **`points(self: object) -> object`**
  
  Path vertices as a read-only int64 (N,2) numpy view in scaled XY coords (polylines are 2D on this fork; upstream S reports (N,3)). Requires numpy.
- **`width`** (property)

#### `Layer`

- **`height`** (property)
- **`lower_layer`** (property)
  
  The layer below, or None.
- **`lslices(self: object) -> list`**
  
  Merged per-layer islands as [ExPolygon] refs (in-place editable). Derived from the region slices; call make_slices() to re-derive after edits. Invalidated by make_slices().
- **`make_slices(self: orca.host.Layer) -> None`**
  
  Re-derive lslices (merged islands) from the region slices and refresh the bbox cache — the C++ invariant-maintenance call after in-place slice edits.
- **`print_z`** (property)
- **`regions(self: object) -> list`**
  
  Per-region data as [LayerRegion].
- **`slice_z`** (property)
- **`upper_layer`** (property)
  
  The layer above, or None (graph navigation, like C++).

#### `LayerRegion`

- **`config_value(self: orca.host.LayerRegion, key: str) -> object`**
  
  Serialized value of this region's resolved config option, or None if absent.
- **`fill_surfaces`** (property)
  
  Surfaces prepared for infill (SurfaceCollection). Edit in place or via fill_surfaces.set(...).
- **`fills`** (property)
  
  Infill toolpaths (ExtrusionEntityCollection, read-only).
- **`layer(self: orca.host.LayerRegion) -> object`**
  
  Owning Layer, or None.
- **`perimeters`** (property)
  
  Perimeter toolpaths (ExtrusionEntityCollection, read-only).
- **`region(self: orca.host.LayerRegion) -> orca.host.PrintRegion`**
  
  This region's PrintRegion (resolved per-region settings).
- **`slices`** (property)
  
  Sliced, typed surfaces (SurfaceCollection). Edit in place, or replace with slices.set(expolygons, surface_type). At Step.posSlice this is the primary mutation target; the split slice loop runs make_perimeters() afterward so edits cascade downstream.

#### `Model`

- **`bounding_box(self: orca.host.Model) -> orca.host.BoundingBox`**
- **`bounding_box_approx(self: orca.host.Model) -> orca.host.BoundingBox`**
- **`current_plate_index(self: orca.host.Model) -> int`**
- **`design_id(self: orca.host.Model) -> str`**
- **`designer(self: orca.host.Model) -> str`**
- **`id(self: orca.host.Model) -> int`**
- **`is_fdm_support_painted(self: orca.host.Model) -> bool`**
- **`is_fuzzy_skin_painted(self: orca.host.Model) -> bool`**
- **`is_mm_painted(self: orca.host.Model) -> bool`**
- **`is_seam_painted(self: orca.host.Model) -> bool`**
- **`material_count(self: orca.host.Model) -> int`**
- **`max_z(self: orca.host.Model) -> float`**
- **`object(self: orca.host.Model, arg0: typing.SupportsInt) -> orca.host.ModelObject`**
- **`object_count(self: orca.host.Model) -> int`**
- **`objects(self: orca.host.Model) -> list`**

#### `ModelInstance`

- **`assemble_matrix(self: orca.host.ModelInstance) -> object`**
  
  Assemble-view 4x4 float64 affine matrix (copy). Requires numpy.
- **`assemble_offset(self: orca.host.ModelInstance) -> tuple`**
- **`assemble_rotation(self: orca.host.ModelInstance) -> tuple`**
- **`bounding_box(self: orca.host.ModelInstance) -> orca.host.BoundingBox`**
- **`id(self: orca.host.ModelInstance) -> int`**
- **`is_assemble_initialized(self: orca.host.ModelInstance) -> bool`**
- **`is_left_handed(self: orca.host.ModelInstance) -> bool`**
- **`is_printable(self: orca.host.ModelInstance) -> bool`**
- **`matrix(self: orca.host.ModelInstance) -> object`**
  
  Object-to-world 4x4 float64 affine matrix (copy). Requires numpy.
- **`mirror(self: orca.host.ModelInstance) -> tuple`**
- **`offset(self: orca.host.ModelInstance) -> tuple`**
- **`offset_to_assembly(self: orca.host.ModelInstance) -> tuple`**
- **`printable`** (property)
- **`rotation(self: orca.host.ModelInstance) -> tuple`**
- **`scaling_factor(self: orca.host.ModelInstance) -> tuple`**

#### `ModelObject`

- **`bounding_box(self: orca.host.ModelObject) -> orca.host.BoundingBox`**
- **`config_keys(self: orca.host.ModelObject) -> list[str]`**
- **`config_value(self: orca.host.ModelObject, arg0: str) -> object`**
- **`facets_count(self: orca.host.ModelObject) -> int`**
- **`has_custom_layering(self: orca.host.ModelObject) -> bool`**
- **`id(self: orca.host.ModelObject) -> int`**
- **`input_file`** (property)
- **`instance(self: orca.host.ModelObject, arg0: typing.SupportsInt) -> orca.host.ModelInstance`**
- **`instance_count(self: orca.host.ModelObject) -> int`**
- **`instances(self: orca.host.ModelObject) -> list`**
- **`is_cut(self: orca.host.ModelObject) -> bool`**
- **`is_fdm_support_painted(self: orca.host.ModelObject) -> bool`**
- **`is_fuzzy_skin_painted(self: orca.host.ModelObject) -> bool`**
- **`is_mm_painted(self: orca.host.ModelObject) -> bool`**
- **`is_multiparts(self: orca.host.ModelObject) -> bool`**
- **`is_seam_painted(self: orca.host.ModelObject) -> bool`**
- **`materials_count(self: orca.host.ModelObject) -> int`**
- **`max_z(self: orca.host.ModelObject) -> float`**
- **`mesh_errors_count(self: orca.host.ModelObject) -> int`**
- **`min_z(self: orca.host.ModelObject) -> float`**
- **`module_name`** (property)
- **`name`** (property)
- **`parts_count(self: orca.host.ModelObject) -> int`**
- **`printable`** (property)
- **`raw_mesh_bounding_box(self: orca.host.ModelObject) -> orca.host.BoundingBox`**
- **`volume(self: orca.host.ModelObject, arg0: typing.SupportsInt) -> orca.host.ModelVolume`**
- **`volume_count(self: orca.host.ModelObject) -> int`**
- **`volumes(self: orca.host.ModelObject) -> list`**

#### `ModelVolume`

- **`bounding_box(self: orca.host.ModelVolume) -> orca.host.BoundingBox`**
- **`config_keys(self: orca.host.ModelVolume) -> list[str]`**
- **`config_value(self: orca.host.ModelVolume, arg0: str) -> object`**
- **`extruder_id(self: orca.host.ModelVolume) -> int`**
- **`facets_count(self: orca.host.ModelVolume) -> int`**
- **`id(self: orca.host.ModelVolume) -> int`**
- **`is_fdm_support_painted(self: orca.host.ModelVolume) -> bool`**
- **`is_fuzzy_skin_painted(self: orca.host.ModelVolume) -> bool`**
- **`is_manifold(self: orca.host.ModelVolume) -> bool`**
- **`is_mm_painted(self: orca.host.ModelVolume) -> bool`**
- **`is_model_part(self: orca.host.ModelVolume) -> bool`**
- **`is_modifier(self: orca.host.ModelVolume) -> bool`**
- **`is_negative_volume(self: orca.host.ModelVolume) -> bool`**
- **`is_seam_painted(self: orca.host.ModelVolume) -> bool`**
- **`is_support_blocker(self: orca.host.ModelVolume) -> bool`**
- **`is_support_enforcer(self: orca.host.ModelVolume) -> bool`**
- **`is_support_modifier(self: orca.host.ModelVolume) -> bool`**
- **`matrix(self: orca.host.ModelVolume) -> object`**
  
  Volume-to-object 4x4 float64 affine matrix (copy). Requires numpy.
- **`mesh(self: orca.host.ModelVolume) -> orca.host.TriangleMesh`**
  
  Return the volume's TriangleMesh (local coordinates) for vertex/triangle access.
- **`mesh_errors_count(self: orca.host.ModelVolume) -> int`**
- **`mirror(self: orca.host.ModelVolume) -> tuple`**
- **`name`** (property)
- **`offset(self: orca.host.ModelVolume) -> tuple`**
- **`rotation(self: orca.host.ModelVolume) -> tuple`**
- **`scaling_factor(self: orca.host.ModelVolume) -> tuple`**
- **`type(self: orca.host.ModelVolume) -> orca.host.ModelVolumeType`**
- **`volume(self: orca.host.ModelVolume) -> float`**

#### `ModelVolumeType`

- 构造：**`__init__(self: orca.host.ModelVolumeType, value: typing.SupportsInt) -> None`**
- **`Invalid`** (ModelVolumeType)
- **`ModelPart`** (ModelVolumeType)
- **`NegativeVolume`** (ModelVolumeType)
- **`ParameterModifier`** (ModelVolumeType)
- **`SupportBlocker`** (ModelVolumeType)
- **`SupportEnforcer`** (ModelVolumeType)
- **`name`** (property)
- **`value`** (property)

#### `Plater`

- **`add_primitive(self: orca.host.Plater, shape: str, size: typing.SupportsFloat | None = None, name: str | None = None) -> int`**
  
  Add a primitive (cube/cylinder/sphere/cone/disc/torus) as a new standalone object (the Add Primitive menu path). size is the shape's side in mm; without it the shape is 10% of the larger bed side like the GUI default. "slab" has no standalone form (it is sized from an existing object) — use add_primitive_volume() for it. Returns the new object's index (it selects the new object). UI thread only.
- **`add_primitive_volume(self: orca.host.Plater, shape: str, object_idx: typing.SupportsInt, instance_idx: typing.SupportsInt = 0, volume_type: orca.host.ModelVolumeType = ..., size: typing.SupportsFloat | None = None, name: str | None = None) -> int`**
  
  Add a primitive as a volume of an existing object — a part, negative volume, modifier or support blocker/enforcer (the Add > primitive submenu path, placed at the front left corner of the target instance and lifted to the bed). "slab" takes its size from that instance's bounding box, so size is rejected for it. Returns the new volume's index. UI thread only.
- **`add_svg_object(self: orca.host.Plater, svg_path: str) -> None`**
  
  Create an SVG emboss object from a path file (the Add SVG menu path with the file chosen up front). The path is audit-checked like a plugin file read and pre-parsed, so bad files raise instead of popping a dialog. Unlike the other modeling methods this queues a background job: it returns immediately, the object appears when the job finishes and the SVG gizmo opens on it (poll the scene/model). Always creates a standalone part object. UI thread only.
- **`add_text_object(self: orca.host.Plater, text: str, font_path: str | None = None, height_mm: typing.SupportsFloat = 10.0, depth_mm: typing.SupportsFloat = 1.0, name: str | None = None) -> int`**
  
  Create an embossed text object (the Add Text menu path, built synchronously instead of through the edit gizmo; the result stays re-editable in the Emboss gizmo). text is limited to 1000 characters (the mesh build is O(len)). font_path defaults to the bundled HarmonyOS Sans SC; a custom path must be a readable .ttf/.ttc (audit-checked like a plugin file read). height_mm is the line height, depth_mm the extrusion depth (upstream defaults). Returns the new object's index. UI thread only.
- **`add_text_volume(self: orca.host.Plater, text: str, object_idx: typing.SupportsInt, font_path: str | None = None, height_mm: typing.SupportsFloat = 10.0, depth_mm: typing.SupportsFloat = 1.0, volume_type: orca.host.ModelVolumeType = ..., name: str | None = None) -> int`**
  
  Add an embossed text volume to an existing object — a part, negative volume or modifier placed in front of the object's first instance and laid on the bed. Same font/text rules as add_text_object(); the volume stays re-editable in the Emboss gizmo. Returns the new volume's index. UI thread only.
- **`apply_object_config(self: orca.host.Plater, object_idx: typing.SupportsInt, values: dict) -> list`**
  
  Apply per-object process overrides (Orca config keys, string-serialized values). UI thread only. Returns [(key, ok, error), ...].
- **`apply_object_transform(self: orca.host.Plater, object_idx: typing.SupportsInt, translate: object = None, rotate: object = None, scale: object = None, mirror: object = None) -> None`**
  
  Set transform components of every instance of one object (absolute, in the same units/angles offset()/rotation()/scaling_factor()/mirror() report: mm and radians; mirror is +/-1 per axis). Omitted components are untouched. Follows the same invalidation path as a GUI transform (undo snapshot + changed_object). UI thread only.
- **`apply_volume_config(self: orca.host.Plater, object_idx: typing.SupportsInt, volume_idx: typing.SupportsInt, values: dict) -> list`**
  
  Apply per-volume process overrides (the volume-level counterpart of apply_object_config). Returns [(key, ok, error), ...]. UI thread only.
- **`arrange(self: orca.host.Plater) -> None`**
  
  Auto-arrange all objects (the Arrange button; runs as a background job — poll slice_state()/the scene, it does not block). UI thread only.
- **`can_arrange(self: orca.host.Plater) -> bool`**
  
  True when arrange() is currently possible. UI thread only.
- **`can_copy_to_clipboard(self: orca.host.Plater) -> bool`**
  
  True when copy_selection() is currently possible. UI thread only.
- **`can_decrease_instances(self: orca.host.Plater) -> bool`**
  
  True when decrease_instances() is currently possible. UI thread only.
- **`can_increase_instances(self: orca.host.Plater) -> bool`**
  
  True when increase_instances() is currently possible. UI thread only.
- **`can_mirror(self: orca.host.Plater) -> bool`**
  
  True when mirror() is currently possible. UI thread only.
- **`can_paste_from_clipboard(self: orca.host.Plater) -> bool`**
  
  True when paste() is currently possible. UI thread only.
- **`can_redo(self: orca.host.Plater) -> bool`**
  
  True when redo is available. UI thread only.
- **`can_split(self: orca.host.Plater, to_objects: bool) -> bool`**
  
  True when the selection can be split to objects (to_objects=True) or volumes (to_objects=False). UI thread only.
- **`can_undo(self: orca.host.Plater) -> bool`**
  
  True when undo is available. UI thread only.
- **`center_selection(self: orca.host.Plater) -> None`**
  
  Center the selected object(s) on the plate. UI thread only.
- **`clear_facet_painting(self: orca.host.Plater, object_idx: typing.SupportsInt, volume_idx: typing.SupportsInt, layer: str) -> bool`**
  
  Remove one volume's facet painting on a layer (the eraser-everything path). Returns True if there was painting to remove. UI thread only.
- **`convert_unit(self: orca.host.Plater, conv_type: orca.host.ConversionType) -> None`**
  
  Convert the selected object(s) between mm and inch/meter (the Convert unit menu path). UI thread only.
- **`copy_selection(self: orca.host.Plater) -> None`**
  
  Copy the selected object(s) to the internal clipboard. UI thread only.
- **`cut_horizontal(self: orca.host.Plater, object_idx: typing.SupportsInt, z: typing.SupportsFloat, instance_idx: typing.SupportsInt = 0, keep_upper: bool = True, keep_lower: bool = True, keep_as_parts: bool = False, flip_upper: bool = False, flip_lower: bool = False, place_on_cut_upper: bool = False, place_on_cut_lower: bool = False) -> list[int]`**
  
  Cut one object with a horizontal plane at world (bed) height z — Plater::cut_horizontal, the programmatic cut the calibration towers use, with the gizmo cut's attribute flags. The original object is REMOVED and the kept sides are appended as new objects: every object index above object_idx shifts down by one, and previously returned object references are invalidated. Returns the indices of the newly appended objects (empty is impossible: z is validated inside the instance's bounding box). Geometric cut only — connectors/dowels and cut-info editing need the gizmo. UI thread only.
- **`cut_selection(self: orca.host.Plater) -> None`**
  
  Cut the selected object(s) to the internal clipboard. UI thread only.
- **`decrease_instances(self: orca.host.Plater, num: typing.SupportsInt = 1) -> None`**
  
  Remove copies of the selected object (the - button). Acts on the current selection. UI thread only.
- **`delete_all_objects(self: orca.host.Plater) -> None`**
  
  Delete every object on every plate. UI thread only.
- **`deselect_all(self: orca.host.Plater) -> None`**
  
  Clear the 3D-view selection. UI thread only.
- **`duplicate_selection(self: orca.host.Plater) -> None`**
  
  Duplicate the selected object(s) onto free space (the Duplicate menu path). UI thread only.
- **`exit_gizmo(self: orca.host.Plater) -> None`**
  
  Close any open gizmo (move/rotate/scale/...) and drop its selection grabber. UI thread only.
- **`export_3mf_copy(self: orca.host.Plater, path: str) -> None`**
  
  Write the current project, unsaved changes included, to path as a 3MF copy. The project's file name and saved state are not changed, and the signed-in account is not written as the designer.
- **`export_object_3mf(self: orca.host.Plater, object_idx: typing.SupportsInt, path: str) -> str`**
  
  Export one object (all its instances, current positions) as a standalone 3MF carrying the current preset config. The path is audit-checked like a plugin file write. UI thread only. Returns the path.
- **`export_object_stl(self: orca.host.Plater, object_idx: typing.SupportsInt, path: str, binary: bool = True) -> str`**
  
  Export one object's mesh as an STL file (the object's merged volumes in its local, untransformed frame — the same mesh store_stl writes for the GUI). The path is audit-checked like a plugin file write. UI thread only. Returns the path.
- **`export_stl(self: orca.host.Plater, path: str, binary: bool = True) -> str`**
  
  Export the whole model as one STL file (all objects, all instances at their world positions — the Export STL menu item's mesh, minus the file dialog). The path is audit-checked like a plugin file write. UI thread only. Returns the path.
- **`fill_bed_with_instances(self: orca.host.Plater) -> None`**
  
  Fill the bed with copies of the selected object (the Fill bed menu path). UI thread only.
- **`fix_through_netfabb(self: orca.host.Plater, object_idx: typing.SupportsInt, volume_idx: typing.SupportsInt = -1) -> None`**
  
  Repair one object's mesh (volume_idx = -1) or a single volume through the Windows 10 SDK's netfabb-style WinRT repair — the Fix through netfabb menu path minus its progress dialog. Synchronous: blocks the calling thread until the repair finishes; throws when the backend is unavailable (probe with is_netfabb_repair_available()) or the repair fails (leaving the model unchanged). Raises while any gizmo is open — call exit_gizmo() first. UI thread only.
- **`get_effective_config(self: orca.host.Plater, object_idx: typing.SupportsInt) -> dict`**
  
  Per-object effective process config: current presets merged with this object's overrides (string-serialized; object-level overrides only). UI thread only.
- **`get_export_gcode_filename(self: orca.host.Plater, only_filename: bool = False) -> str`**
  
  The G-code file name the next export would use (derived from the project name), or an empty string when none is derivable. only_filename strips the directory. UI thread only.
- **`get_facet_painting(self: orca.host.Plater, object_idx: typing.SupportsInt, volume_idx: typing.SupportsInt, layer: str) -> list`**
  
  Read one volume's facet painting as a list of ints with one state per original triangle (index = triangle index into volume.mesh()). State alphabets: fdm_support/seam 0=none 1=enforcer 2=blocker; fuzzy_skin 0/1; mmu = the 1-based extruder painting the facet (0 = none). No painting is an all-zero array. Unlocked read, like the other model-data reads.
- **`get_primitive_shapes(self: orca.host.Plater) -> list`**
  
  The shape names add_primitive()/add_primitive_volume() accept: cube, cylinder, sphere, slab, cone, disc, torus.
- **`increase_instances(self: orca.host.Plater, num: typing.SupportsInt = 1) -> None`**
  
  Add copies of the selected object (the + button). Acts on the current selection. UI thread only.
- **`inside_snapshot_capture(self: orca.host.Plater) -> bool`**
- **`is_export_gcode_scheduled(self: orca.host.Plater) -> bool`**
  
  True while a scheduled G-code export path is still held. Unlocked read, safe to poll.
- **`is_loading_project(self: orca.host.Plater) -> bool`**
  
  True while a project is being loaded. Unlocked read, safe to poll.
- **`is_netfabb_repair_available(self: orca.host.Plater) -> bool`**
  
  True when this build carries the Windows 10 SDK repair backend AND this system supports the WinRT Printing3D repair it uses. Unlocked read, safe from any thread.
- **`is_presets_dirty(self: orca.host.Plater) -> bool`**
- **`is_preview_shown(self: orca.host.Plater) -> bool`**
  
  True when the Preview tab is the active view. UI thread only.
- **`is_project_dirty(self: orca.host.Plater) -> bool`**
- **`is_selection_empty(self: orca.host.Plater) -> bool`**
  
  True when nothing is selected in the 3D view. UI thread only.
- **`load_model_files(self: orca.host.Plater, paths: list) -> list`**
  
  Import model file(s) onto the current plate (added like a drag-and-drop). UI thread only. Returns the indices of the added objects.
- **`merge_volumes(self: orca.host.Plater, object_idx: typing.SupportsInt, volume_indices: list) -> None`**
  
  Merge the given volumes of one object into a single part (the Merge button's path). UI thread only.
- **`mirror(self: orca.host.Plater, axis: orca.host.Axis) -> None`**
  
  Mirror the selected object(s) across the given Axis (X/Y/Z). UI thread only.
- **`model(self: orca.host.Plater) -> orca.host.Model`**
- **`new_project(self: orca.host.Plater, skip_confirm: bool = False, silent: bool = False, project_name: str = '') -> int`**
  
  Start a new empty project (the New Project menu path). skip_confirm suppresses the unsaved-changes prompt, silent suppresses progress feedback. UI thread only.
- **`only_gcode_mode(self: orca.host.Plater) -> bool`**
  
  True when the app runs in G-code viewer mode. Unlocked read, safe to poll.
- **`open_project(self: orca.host.Plater, paths: list) -> list`**
  
  Open a project file (3MF): its objects are added and its embedded presets are applied, like the Open Project menu path. Unlike load_model_files() this changes the active presets. UI thread only. Returns the indices of the added objects.
- **`optimize_rotation(self: orca.host.Plater) -> None`**
  
  Run the rotation optimizer on the selected object(s). UI thread only.
- **`orient(self: orca.host.Plater) -> None`**
  
  Auto-orient all objects (background job, like arrange()). UI thread only.
- **`paste(self: orca.host.Plater) -> None`**
  
  Paste from the internal clipboard. UI thread only.
- **`project_path(self: orca.host.Plater) -> str`**
- **`redo(self: orca.host.Plater) -> None`**
  
  Redo one step. UI thread only.
- **`remove_object(self: orca.host.Plater, object_idx: typing.SupportsInt) -> None`**
  
  Delete one object (the Delete menu path: removes it from the model, its plates and the undo history entry is created). UI thread only.
- **`remove_selected(self: orca.host.Plater) -> None`**
  
  Delete the objects selected in the 3D view. UI thread only.
- **`rename_object(self: orca.host.Plater, object_idx: typing.SupportsInt, name: str) -> bool`**
  
  Rename one object (fires the same object-renamed lifecycle event and undo snapshot as the GUI rename; a single-volume object's volume is renamed with it). Returns True if the name changed, False if it already was that name. UI thread only.
- **`rename_volume(self: orca.host.Plater, object_idx: typing.SupportsInt, volume_idx: typing.SupportsInt, name: str) -> bool`**
  
  Rename one volume of an object (same lifecycle event and undo snapshot as the GUI rename). Returns True if the name changed. UI thread only.
- **`reset_object_config(self: orca.host.Plater, object_idx: typing.SupportsInt, keys: list) -> list`**
  
  Remove per-object process overrides. Returns [(key, was_set), ...]; was_set=False means the key was never overridden (no-op). UI thread only.
- **`save_project(self: orca.host.Plater, save_as: bool = False) -> int`**
  
  Save the project; save_as=True raises the file dialog (the Save As menu path). UI thread only.
- **`scale_selection_to_fit_print_volume(self: orca.host.Plater) -> None`**
  
  Scale the selected object(s) down to fit the print volume. UI thread only.
- **`schedule_plate_gcode_export(self: orca.host.Plater, output_path: str) -> str`**
  
  Slice the current plate now and export its G-code to output_path (async; poll the file). UI thread only.
- **`select_all(self: orca.host.Plater) -> None`**
  
  Select every object in the 3D view. UI thread only.
- **`select_current_plate_objects(self: orca.host.Plater) -> None`**
  
  Select the objects on the current plate. UI thread only.
- **`select_view(self: orca.host.Plater, direction: str) -> None`**
  
  Point the camera: "iso", "top", "bottom", "front", "rear", "left", "right" or "plate". Applies to the current 3D/Preview panel. UI thread only.
- **`select_view_3D(self: orca.host.Plater, name: str, no_slice: bool = True) -> None`**
  
  Switch the main view: "3D", "Preview" (slices if needed) or "Assemble". UI thread only.
- **`selected_object_indices(self: orca.host.Plater) -> list`**
  
  Indices of the objects currently selected in the 3D view. UI thread only.
- **`set_facet_painting(self: orca.host.Plater, object_idx: typing.SupportsInt, volume_idx: typing.SupportsInt, layer: str, states: collections.abc.Sequence) -> int`**
  
  Replace one volume's facet painting from a flat int sequence (list/tuple, or a 1-D numpy array) with one state per original triangle — get_facet_painting's counterpart; 0 leaves the facet unpainted. The write goes through the same FacetsAnnotation path the painting gizmos use, so undo, the 3D view and the next slice all see it. mmu states must not exceed the loaded filament count. Returns the number of painted facets. UI thread only.
- **`set_instance_printable(self: orca.host.Plater, object_idx: typing.SupportsInt, instance_idx: typing.SupportsInt, printable: bool) -> None`**
  
  Set the printable flag of one instance (the per-instance printable toggle). UI thread only.
- **`set_object_extruder(self: orca.host.Plater, object_idx: typing.SupportsInt, extruder: typing.SupportsInt) -> bool`**
  
  Assign a whole object to an extruder/filament (the assemble-view fill_color data path): extruder is 1-based, 0 means inherit the global default, and it must not exceed the number of loaded filaments. The object's part volumes drop their own extruder overrides, following the object again. Returns True if anything changed. UI thread only.
- **`set_object_printable(self: orca.host.Plater, object_idx: typing.SupportsInt, printable: bool) -> None`**
  
  Set the printable flag on every instance of one object (the object-level printable toggle). Follows the same snapshot/canvas refresh path as the GUI toggle. UI thread only.
- **`set_selected_visible(self: orca.host.Plater, visible: bool) -> None`**
  
  Show or hide the selected object(s) (hidden objects are not sliced). UI thread only.
- **`set_volume_extruder(self: orca.host.Plater, object_idx: typing.SupportsInt, volume_idx: typing.SupportsInt, extruder: typing.SupportsInt) -> bool`**
  
  Assign one volume to an extruder/filament — parts and parameter modifiers only. extruder 0 on a part is baked to the parent object's current extruder (the GUI behavior); a modifier keeps the 0 (inherit). Returns True if anything changed. UI thread only.
- **`simplify_volume(self: orca.host.Plater, object_idx: typing.SupportsInt, volume_idx: typing.SupportsInt, keep_ratio: typing.SupportsFloat | None = None, target_triangle_count: typing.SupportsInt | None = None, max_error: typing.SupportsFloat | None = None) -> int`**
  
  Quadric-edge-collapse decimation of one volume (the Simplify tool's engine, without its preview gizmo). Give exactly one of keep_ratio — fraction of triangles to KEEP; note the GUI slider shows the complement, removed percentage — or target_triangle_count (>= 4, below the current count). max_error optionally caps the quadric error. Synchronous and runs on the calling thread: large meshes freeze the UI for the duration, and the GIL is released so other Python threads run but must not read the model meanwhile. Returns the new triangle count. UI thread only.
- **`slice_progress(self: orca.host.Plater) -> int`**
  
  Slicing progress percent of the current plate, or -1 if none was reported yet. Unlocked read, safe to poll.
- **`slice_state(self: orca.host.Plater) -> str`**
  
  Coarse slicing state: "idle", "slicing", or "exporting" (export-scheduled jobs report "exporting" throughout). Unlocked read, safe to poll.
- **`split_object(self: orca.host.Plater) -> None`**
  
  Split the selected multi-part object into separate objects. UI thread only.
- **`split_volume(self: orca.host.Plater) -> None`**
  
  Split the selected object into its constituent volumes. UI thread only.
- **`undo(self: orca.host.Plater) -> None`**
  
  Undo one step (the Edit menu path). UI thread only.
- **`using_exported_file(self: orca.host.Plater) -> bool`**
  
  True when the current scene came from an exported/sliced file rather than a project. Unlocked read, safe to poll.

#### `Point`

- 构造：**`__init__(self: orca.host.Point, x: typing.SupportsInt, y: typing.SupportsInt) -> None`**
- **`x`** (property)
- **`y`** (property)

#### `Polygon`

- 构造：**`__init__(self: orca.host.Polygon) -> None`**
- **`append(self: orca.host.Polygon, point: orca.host.Point) -> None`**
  
  Append a vertex. Structural change (count): invalidates previously returned Point refs and array views into this polygon (C++ vector semantics).
- **`area(self: orca.host.Polygon) -> float`**
- **`as_array(self: object) -> object`**
  
  Vertices as a WRITABLE int64 (N,2) numpy view in scaled coords, aliasing the buffer. Count-preserving in-place edits only; valid during execute(ctx). Requires numpy.
- **`centroid(self: orca.host.Polygon) -> orca.host.Point`**
- **`contains(self: orca.host.Polygon, point: orca.host.Point) -> bool`**
- **`douglas_peucker(self: orca.host.Polygon, tolerance: typing.SupportsFloat) -> None`**
- **`is_clockwise(self: orca.host.Polygon) -> bool`**
- **`is_counter_clockwise(self: orca.host.Polygon) -> bool`**
- **`is_valid(self: orca.host.Polygon) -> bool`**
- **`make_clockwise(self: orca.host.Polygon) -> bool`**
- **`make_counter_clockwise(self: orca.host.Polygon) -> bool`**
  
  Reorient to CCW in place. Returns True if it reversed the winding.
- **`offset(self: orca.host.Polygon, delta: typing.SupportsInt) -> list[orca.host.Polygon]`**
  
  Clipper offset by `delta` scaled units (negative shrinks). Returns [Polygon].
- **`points`** (property)
  
  Vertices as [Point] references into this polygon. Editing a Point mutates the buffer in place. Structural changes (count) go through set_points/append, which invalidate previously returned Point refs and array views (C++ vector semantics).
- **`rotate(self: orca.host.Polygon, angle: typing.SupportsFloat) -> None`**
- **`rotate(self: orca.host.Polygon, angle: typing.SupportsFloat, center: orca.host.Point) -> None`**
- **`set_points(self: orca.host.Polygon, points: object) -> None`**
  
  Replace all vertices from an (N,2) int64 ndarray (scaled coords). Count-changing; invalidates prior Point refs and array views. Raises ValueError on malformed input.
- **`simplify(self: orca.host.Polygon, tolerance: typing.SupportsFloat) -> list[orca.host.Polygon]`**
  
  Return simplified geometry as a list of Polygon (may split into several).
- **`size(self: orca.host.Polygon) -> int`**
- **`translate(self: orca.host.Polygon, x: typing.SupportsFloat, y: typing.SupportsFloat) -> None`**

#### `Preset`

- **`alias`** (property)
- **`bundle_id`** (property)
- **`config_keys(self: orca.host.Preset) -> list[str]`**
- **`config_value(self: orca.host.Preset, arg0: str) -> object`**
- **`file`** (property)
- **`is_compatible`** (property)
- **`is_default`** (property)
- **`is_dirty`** (property)
- **`is_external`** (property)
- **`is_from_bundle(self: orca.host.Preset) -> bool`**
- **`is_project_embedded`** (property)
- **`is_system`** (property)
- **`is_user(self: orca.host.Preset) -> bool`**
- **`is_visible`** (property)
- **`label(self: orca.host.Preset, no_alias: bool = False) -> str`**
- **`name`** (property)
- **`type`** (property)

#### `PresetBundle`

- **`current_filament_preset_names(self: orca.host.PresetBundle) -> list[str]`**
- **`current_filament_presets(self: orca.host.PresetBundle) -> list`**
- **`current_print_preset(self: orca.host.PresetBundle) -> orca.host.Preset`**
- **`current_printer_preset(self: orca.host.PresetBundle) -> orca.host.Preset`**
- **`current_process_preset(self: orca.host.PresetBundle) -> orca.host.Preset`**
- **`filaments`** (property)
- **`full_config_keys(self: orca.host.PresetBundle) -> list[str]`**
- **`full_config_value(self: orca.host.PresetBundle, arg0: str) -> object`**
- **`printers`** (property)
- **`prints`** (property)
- **`sla_materials`** (property)
- **`sla_prints`** (property)

#### `PresetCollection`

- **`edited_preset(self: orca.host.PresetCollection) -> orca.host.Preset`**
- **`find_preset(self: orca.host.PresetCollection, arg0: str) -> orca.host.Preset`**
- **`get_edited_preset(self: orca.host.PresetCollection) -> orca.host.Preset`**
- **`get_selected_preset(self: orca.host.PresetCollection) -> orca.host.Preset`**
- **`get_selected_preset_name(self: orca.host.PresetCollection) -> str`**
- **`preset(self: orca.host.PresetCollection, arg0: typing.SupportsInt) -> orca.host.Preset`**
- **`preset_names(self: orca.host.PresetCollection) -> list[str]`**
- **`selected_preset(self: orca.host.PresetCollection) -> orca.host.Preset`**
- **`selected_preset_name(self: orca.host.PresetCollection) -> str`**
- **`size(self: orca.host.PresetCollection) -> int`**

#### `PresetType`

- 构造：**`__init__(self: orca.host.PresetType, value: typing.SupportsInt) -> None`**
- **`Filament`** (PresetType)
- **`Invalid`** (PresetType)
- **`Model`** (PresetType)
- **`PhysicalPrinter`** (PresetType)
- **`Plate`** (PresetType)
- **`Print`** (PresetType)
- **`Printer`** (PresetType)
- **`SlaMaterial`** (PresetType)
- **`SlaPrint`** (PresetType)
- **`name`** (property)
- **`value`** (property)

#### `Print`

- **`canceled(self: orca.host.Print) -> bool`**
  
  True once cancellation was requested (prefer ctx.cancelled()).
- **`config_keys(self: orca.host.Print) -> list[str]`**
- **`config_value(self: orca.host.Print, key: str) -> object`**
  
  Serialized value of the resolved (full) print config for this slice, or None.
- **`model(self: orca.host.Print) -> orca.host.Model`**
  
  The Print's own Model snapshot (worker-thread stable). Inside slicing hooks use THIS — never orca.host.model(), which is the live GUI model owned by another thread.
- **`objects(self: object) -> list`**
  
  The print's objects as [PrintObject].

#### `PrintObject`

- **`bounding_box(self: orca.host.PrintObject) -> tuple`**
  
  Object XY bounding box in scaled coords as (min_x, min_y, max_x, max_y). The sliced polygons live in this same frame, so its midpoint is the footprint center.
- **`config_keys(self: orca.host.PrintObject) -> list[str]`**
- **`config_value(self: orca.host.PrintObject, key: str) -> object`**
  
  Serialized value of a resolved per-object config option, or None if absent.
- **`id(self: orca.host.PrintObject) -> int`**
  
  Stable numeric object id (ObjectBase::id()).
- **`layers(self: object) -> list`**
  
  Object layers, bottom-up, as [Layer].
- **`model_object(self: orca.host.PrintObject) -> object`**
  
  The source orca.host.ModelObject from the Print's own model snapshot.
- **`support_layers(self: object) -> list`**
  
  Support layers as [Layer] (support-specific fields are not exposed).
- **`trafo(self: orca.host.PrintObject) -> object`**
  
  Object-to-print 4x4 float64 affine matrix (copy). Requires numpy.

#### `PrintRegion`

- **`config_keys(self: orca.host.PrintRegion) -> list[str]`**
- **`config_value(self: orca.host.PrintRegion, key: str) -> object`**
  
  Serialized value of this region's resolved config option, or None if absent.

#### `Surface`

- 构造：**`__init__(self: orca.host.Surface, surface_type: orca.host.SurfaceType, expolygon: orca.host.ExPolygon) -> None`**
- 构造：**`__init__(self: orca.host.Surface, surface_type: orca.host.SurfaceType) -> None`**
- **`area(self: orca.host.Surface) -> float`**
- **`bridge_angle`** (property)
- **`expolygon`** (property)
  
  This surface's geometry. Read returns a live ExPolygon ref; assign to replace it.
- **`extra_perimeters`** (property)
- **`is_bottom(self: orca.host.Surface) -> bool`**
- **`is_bridge(self: orca.host.Surface) -> bool`**
- **`is_external(self: orca.host.Surface) -> bool`**
- **`is_internal(self: orca.host.Surface) -> bool`**
- **`is_solid(self: orca.host.Surface) -> bool`**
- **`is_top(self: orca.host.Surface) -> bool`**
- **`surface_type`** (property)
  
  This surface's SurfaceType. Assigning reclassifies it in place (geometry unchanged).
- **`thickness`** (property)

#### `SurfaceCollection`

- **`append(self: orca.host.SurfaceCollection, expolygons: collections.abc.Sequence[orca.host.ExPolygon], surface_type: orca.host.SurfaceType) -> None`**
- **`clear(self: orca.host.SurfaceCollection) -> None`**
- **`empty(self: orca.host.SurfaceCollection) -> bool`**
- **`filter_by_type(self: object, surface_type: orca.host.SurfaceType) -> list`**
  
  Surfaces of a given type as [Surface] refs. Invalidated by set()/append()/clear() on this collection (C++ vector semantics), same as .surfaces.
- **`has(self: orca.host.SurfaceCollection, surface_type: orca.host.SurfaceType) -> bool`**
- **`set(self: orca.host.SurfaceCollection, expolygons: collections.abc.Sequence[orca.host.ExPolygon], surface_type: orca.host.SurfaceType) -> None`**
- **`set(self: orca.host.SurfaceCollection, surfaces: collections.abc.Sequence[orca.host.Surface]) -> None`**
  
  Replace all surfaces from a list of ExPolygon, all tagged `surface_type`.

Replace all surfaces from a list of Surface (types preserved per surface).
- **`set_type(self: orca.host.SurfaceCollection, surface_type: orca.host.SurfaceType) -> None`**
- **`size(self: orca.host.SurfaceCollection) -> int`**
- **`surfaces`** (property)
  
  Surfaces as [Surface] references into the live collection. Invalidated by set()/append()/clear() on this collection (C++ vector semantics).

#### `SurfaceType`

- 构造：**`__init__(self: orca.host.SurfaceType, value: typing.SupportsInt) -> None`**
- **`name`** (property)
- **`stBottom`** (SurfaceType)
- **`stBottomBridge`** (SurfaceType)
- **`stCount`** (SurfaceType)
- **`stInternal`** (SurfaceType)
- **`stInternalAfterExternalBridge`** (SurfaceType)
- **`stInternalBridge`** (SurfaceType)
- **`stInternalSolid`** (SurfaceType)
- **`stInternalVoid`** (SurfaceType)
- **`stPerimeter`** (SurfaceType)
- **`stSecondInternalBridge`** (SurfaceType)
- **`stTop`** (SurfaceType)
- **`value`** (property)

#### `TriangleMesh`

- **`bounding_box(self: orca.host.TriangleMesh) -> orca.host.BoundingBox`**
- **`face_normals(self: orca.host.TriangleMesh) -> object`**
  
  Per-triangle normalized normals as an (M, 3) float32 ndarray (copy). Requires numpy.
- **`facets_count(self: orca.host.TriangleMesh) -> int`**
- **`is_empty(self: orca.host.TriangleMesh) -> bool`**
- **`is_manifold(self: orca.host.TriangleMesh) -> bool`**
- **`triangle(self: orca.host.TriangleMesh, arg0: typing.SupportsInt) -> tuple`**
- **`triangle_count(self: orca.host.TriangleMesh) -> int`**
- **`triangles(self: object) -> object`**
  
  Read-only zero-copy (M, 3) int32 ndarray of triangle vertex indices. Requires numpy.
- **`vertex(self: orca.host.TriangleMesh, arg0: typing.SupportsInt) -> tuple`**
- **`vertex_count(self: orca.host.TriangleMesh) -> int`**
- **`vertices(self: object) -> object`**
  
  Read-only zero-copy (N, 3) float32 ndarray of vertex positions (local mm). Requires numpy.
- **`volume(self: orca.host.TriangleMesh) -> float`**

（子模块：`plate`、`plugin`、`preset`、`ui`，见下文。）

### 模块 `orca.host.plate` — 多盘（plate）域【fork 自增，见 5.1】

**函数**

- **`create_plate() -> int`**
  
  Create an empty plate and return its 0-based index. UI thread only.
- **`current_plate_index() -> int`**
  
  0-based index of the currently selected plate. Unlocked read, safe to poll.
- **`delete_plate(index: typing.SupportsInt) -> None`**
  
  Delete the plate at a 0-based index; its objects return to the overflow area. UI thread only.
- **`duplicate_plate(index: typing.SupportsInt) -> int`**
  
  Duplicate the plate at a 0-based index (objects and layout) and return the new plate's index. UI thread only.
- **`plate`** (builtin_function_or_method)
  
  Handle to the plate at a 0-based index. The handle re-resolves the live plate list on every call, so it raises ValueError once the index no longer resolves (e.g. after delete_plate).
- **`plate_count() -> int`**
  
  Number of plates in the project (including the unprintable overflow plate if present). Unlocked read, safe to poll.
- **`select_plate(index: typing.SupportsInt) -> int`**
  
  Select the plate at a 0-based index (the same switch the plate bar performs) and return the now-current index. UI thread only.
- **`select_plate_by_object(object_idx: typing.SupportsInt, instance_idx: typing.SupportsInt = 0) -> int`**
  
  Select the plate holding the given object instance and return the now-current index. UI thread only.


#### `Plate`

- **`bed_type(self: orca.host.plate.Plate) -> str`**
  
  Plate bed type as a stable short name ("default", "pc", "ep", "pei", "pte", "pct", "gesp", "super_tack"), not the localized label. UI thread only.
- **`can_slice(self: orca.host.plate.Plate) -> bool`**
  
  True when the plate passes the GUI's slice gate (objects loaded, apply state valid). UI thread only.
- **`extruders(self: orca.host.plate.Plate) -> list[int]`**
  
  1-based extruder (filament) indices used on this plate. UI thread only.
- **`gcode_filename(self: orca.host.plate.Plate) -> str`**
  
  Path of the plate's sliced G-code file, or an empty string when none was produced. Reading the file still needs filesystem permission. UI thread only.
- **`has_valid_gcode_file(self: orca.host.plate.Plate) -> bool`**
  
  True when the plate's G-code file exists and matches the current slice. UI thread only.
- **`index`** (property)
- **`is_slice_result_valid(self: orca.host.plate.Plate) -> bool`**
  
  True when the plate holds a slice result for the current model/preset state. UI thread only.
- **`name`** (property)
  
  Plate display name. UI thread only.
- **`object_count(self: orca.host.plate.Plate) -> int`**
  
  Number of objects on this plate. UI thread only.
- **`object_indices(self: orca.host.plate.Plate) -> list[int]`**
  
  Indices into plater.model().objects() of the objects on this plate (any instance bound counts). UI thread only.
- **`objects_bounding_box(self: orca.host.plate.Plate) -> orca.host.BoundingBox`**
  
  World-space bounding box of the objects on this plate (a copy). UI thread only.
- **`origin(self: orca.host.plate.Plate) -> tuple`**
  
  Plate center origin in world coordinates as (x, y, z). UI thread only.
- **`size(self: orca.host.plate.Plate) -> tuple`**
  
  Printable plate footprint (width, depth) in mm. UI thread only.
- **`slice_ready_for_export(self: orca.host.plate.Plate) -> bool`**
  
  True when the slice result is valid for export (printable and has printable instances). UI thread only.
- **`slice_ready_for_print(self: orca.host.plate.Plate) -> bool`**
  
  True when the slice result is valid for printing (no toolpath outside the plate). UI thread only.

### 模块 `orca.host.plugin` — 插件自身信息

**函数**

- **`storage() -> str`**
  
  Return the installed folder of the current plugin.


### 模块 `orca.host.preset` — 预设事务 API

- **PresetEditor** 预置实例（`PresetEditor`）：`filament`、`printer`、`process`


#### `PresetEditor`

- **`begin_update(self: orca.host.preset.PresetEditor, preset_name: str = '') -> orca.host.preset.PresetTransaction`**
- **`begin_update(self: orca.host.preset.PresetEditor, slot_number: typing.SupportsInt, preset_name: str = '') -> orca.host.preset.PresetTransaction`**
  
  Resolve and bind this category's target preset and return a PresetTransaction. With no preset_name the currently active preset is targeted; a preset_name must be a preset this category can select, and is selected through the normal preset-selection flow (which prompts about unsaved edits). The call blocks the background Script worker until any such dialog is answered, leaving the UI thread responsive. A selection the user cancels raises RuntimeError; an unavailable or invalid target raises ValueError. Either failure creates no transaction and stages no setting. Call it from the background Script worker, never from the UI thread. This form is for process and printer; filament takes begin_update(slot_number, preset_name="").

Resolve and bind a filament preset by 1-based slot and return a PresetTransaction. Omitting preset_name targets the preset assigned to the slot; supplying a different name selects it for the slot through the normal flow (prompting about unsaved edits) and, once that succeeds, records the new slot assignment with the same Plater side effects the sidebar selection performs (project/selection refresh, dynamic filament list, conditional support-filament flushing recalc and the slot's AMS sync badge). A requested preset this slot's dropdown does not offer is rejected before that flow, so it raises no prompt; the slot's own current assignment stays targetable even when the dropdown hides it. A selection the user cancels raises RuntimeError and changes neither the slot assignment nor any setting. An out-of-range, empty or unresolved slot is rejected, and a mixed-color virtual slot is rejected whether or not preset_name is given. The transaction edits the shared preset, so every slot assigned to it is affected. The call blocks the background Script worker until the selection settles, leaving the UI thread responsive; call it from that worker, never from the UI thread.
- **`type`** (property)
- **`update(self: orca.host.preset.PresetEditor, key: str, value: str) -> None`**
- **`update(self: orca.host.preset.PresetEditor, slot_number: typing.SupportsInt, key: str, value: str) -> None`**
  
  Set one setting of the currently edited preset and run the same committed-change path as editing the setting in the GUI; the edited preset becomes dirty until saved/exported. key must be a setting of this preset category and value its serialized string form, otherwise ValueError is raised and nothing is written. A setting edited through a field runs that field's validation even before its page has been opened; one the GUI edits outside a field (such as compatible printers) also recomputes preset compatibility. Equivalent to begin_update() with the active preset as target, then set(key, value) and commit(); like begin_update() this call blocks the background Script worker.

Set one setting of the filament preset assigned to a 1-based filament slot. When that preset is not the one currently edited the call switches to it through the normal preset-selection flow, so an unsaved edited preset still prompts the user and a declined prompt cancels the call with an error and no change. An out-of-range, empty or unresolved slot is rejected with a clear error, as is a mixed-color virtual slot, which has no single preset to edit. Other preset editors accept only update(key, value); this form raises ValueError on them. Equivalent to begin_update(slot_number) with an omitted preset_name (the slot's current assignment is kept), then set(key, value) and commit(); like begin_update() this call blocks the background Script worker.

#### `PresetTransaction`

- **`category`** (property)
- **`commit(self: orca.host.preset.PresetTransaction) -> orca.host.preset.PresetUpdateResult`**
  
  Validate and apply every staged setting through the same path as editing it in the GUI, then return a PresetUpdateResult. An invalid key or value raises ValueError; a changed target or filament slot mapping raises RuntimeError; a failure leaves none of the staged settings applied. The edited preset becomes dirty until the user saves it.
- **`selection_changed`** (property)
- **`set(self: orca.host.preset.PresetTransaction, key: str, value: str) -> None`**
  
  Stage one setting change. key must be a setting of the target preset category and value its serialized string form; staging validates neither, so commit() is where an invalid key or value fails. Staging the same key twice in one transaction raises ValueError (conflicting duplicate writes are rejected). After commit() the transaction is closed.
- **`slot_number`** (property)
- **`staged_keys`** (property)
- **`target_name`** (property)
- **`type`** (property)

#### `PresetUpdateResult`

- **`category`** (property)
- **`dirty`** (property)
- **`keys`** (property)
- **`selection_changed`** (property)
- **`shared_slots`** (property)
- **`slot_assignment_changed`** (property)
- **`slot_number`** (property)
- **`target_name`** (property)
- **`type`** (property)

（子模块：`bundles`，见下文。）

### 模块 `orca.host.preset.bundles` — 本地预设包管理

**函数**

- **`list_ids() -> list[str]`**
  
  IDs of user preset folders under <data_dir>/user that reload_local() accepts, including folders created after startup.
- **`reload_local(bundle_id: str) -> None`**
  
  Reload one user preset folder under <data_dir>/user from disk (this build's local preset bundle unit); preset selections are preserved. Valid ids come from list_ids().


### 模块 `orca.host.ui` — UI 桥（窗口/停靠面板/通知/进度）

- **NotificationLevel** 枚举值：`ErrorNotificationLevel`、`HintNotificationLevel`、`ImportantNotificationLevel`、`PrintInfoNotificationLevel`、`PrintInfoShortNotificationLevel`、`ProgressBarNotificationLevel`、`RegularNotificationLevel`、`SeriousWarningNotificationLevel`、`WarningNotificationLevel`
- **int** 常量（int）：`PD_APP_MODAL`、`PD_AUTO_HIDE`、`PD_CAN_ABORT`、`PD_CAN_SKIP`、`PD_ELAPSED_TIME`、`PD_ESTIMATED_TIME`、`PD_REMAINING_TIME`、`WINDOW_MODAL`、`WINDOW_MODELESS`

**函数**

- **`create_dock_panel(html: str, title: str = 'OrcaSlicer', width: typing.SupportsInt = 320, height: typing.SupportsInt = 480, on_message: object = None, on_close: object = None, dock: str = 'right') -> object`**
  
  Open an HTML panel docked beside the 3D view and return a UiDockPanel. dock is "left", "right", "bottom" or "float", and width/height are in DIPs; the user can move and resize the panel, and a panel opened again comes back where the window layout was last saved. The panel belongs to the Prepare and Preview tabs. on_message(data) is called on the UI thread when the page posts; window.orca.close() or the panel's close button closes it and calls on_close(). A post() made before the page has loaded can be dropped, so have the page request its first data.
- **`create_progress_dialog(title: str, message: str, maximum: typing.SupportsInt = 100, style: typing.SupportsInt = 6) -> orca.host.ui.ProgressDialog`**
  
  Create a native progress dialog and return a ProgressDialog handle.
- **`create_window(html: str, title: str = 'OrcaSlicer', width: typing.SupportsInt = 820, height: typing.SupportsInt = 600, on_message: object = None, on_close: object = None, style: typing.SupportsInt = 0, on_submit: object = None) -> object`**
  
  Open a persistent HTML window or modal dialog and return a UiWindow. style is WINDOW_MODELESS or WINDOW_MODAL. on_message(data) is called on the UI thread when the page posts; on_submit(data) is called when the page submits; offload heavy work to a thread and push results back with window.post().
- **`message(text: str, title: str = 'OrcaSlicer', buttons: str = 'ok', icon: str = 'info') -> str`**
  
  Show a native modal message box; returns the clicked button id ("ok"/"cancel"/"yes"/"no"). buttons: "ok"|"ok_cancel"|"yes_no"|"yes_no_cancel"; icon: "info"|"warning"|"error"|"question".
- **`push_notification(notification_level: orca.host.ui.NotificationLevel, text: str, hyper_text: str = '', on_click: object = None) -> None`**
  
  Push a plater notification. hyper_text is an underlined label; on_click() is called when it is clicked and may return True to close the notification.


#### `NotificationLevel`

- 构造：**`__init__(self: orca.host.ui.NotificationLevel, value: typing.SupportsInt) -> None`**
- **`ErrorNotificationLevel`** (NotificationLevel)
- **`HintNotificationLevel`** (NotificationLevel)
- **`ImportantNotificationLevel`** (NotificationLevel)
- **`PrintInfoNotificationLevel`** (NotificationLevel)
- **`PrintInfoShortNotificationLevel`** (NotificationLevel)
- **`ProgressBarNotificationLevel`** (NotificationLevel)
- **`RegularNotificationLevel`** (NotificationLevel)
- **`SeriousWarningNotificationLevel`** (NotificationLevel)
- **`WarningNotificationLevel`** (NotificationLevel)
- **`name`** (property)
- **`value`** (property)

#### `ProgressDialog`

- 构造：**`__init__(self: orca.host.ui.ProgressDialog, title: str, message: str, maximum: typing.SupportsInt = 100, style: typing.SupportsInt = 6) -> None`**
- **`close(self: orca.host.ui.ProgressDialog) -> None`**
  
  Close the progress dialog.
- **`id`** (property)
- **`is_open(self: orca.host.ui.ProgressDialog) -> bool`**
  
  Return True while this progress dialog is registered.
- **`pulse(self: orca.host.ui.ProgressDialog, message: str = '') -> bool`**
  
  Pulse the dialog gauge; returns False if the dialog is closed or cancelled.
- **`start_pulse(self: orca.host.ui.ProgressDialog, interval_ms: typing.SupportsInt = 100, message: str = '') -> None`**
  
  Start periodic pulsing.
- **`stop_pulse(self: orca.host.ui.ProgressDialog) -> None`**
  
  Stop periodic pulsing.
- **`update(self: orca.host.ui.ProgressDialog, value: typing.SupportsInt, message: str = '') -> bool`**
  
  Set the dialog progress value; returns False if the dialog is closed or cancelled.

#### `UiDockPanel`

- **`close(self: orca.host.ui.UiDockPanel) -> None`**
  
  Close the panel (fires on_close).
- **`hide(self: orca.host.ui.UiDockPanel) -> None`**
  
  Hide the panel without closing it.
- **`id`** (property)
- **`is_open(self: orca.host.ui.UiDockPanel) -> bool`**
  
  Return True until the panel is closed; a hidden panel is still open.
- **`post(self: orca.host.ui.UiDockPanel, data: object) -> None`**
  
  Send a payload to the page (delivered to window.orca.onMessage handlers).
- **`show(self: orca.host.ui.UiDockPanel) -> None`**
  
  Show the panel again after hide().

#### `UiWindow`

- **`close(self: orca.host.ui.UiWindow) -> None`**
  
  Close the window (fires on_close).
- **`id`** (property)
- **`is_open(self: orca.host.ui.UiWindow) -> bool`**
  
  Return True while the window is open.
- **`post(self: orca.host.ui.UiWindow, data: object) -> None`**
  
  Send a payload to the page (delivered to window.orca.onMessage handlers).

### 模块 `orca.exporter` — Exporter 能力（格式导出）【fork 先行，契约 provisional】


#### `ExporterContext`

- **`model`** (property)
  
  Read-only orca.host.Model snapshot of the scene. Pull meshes via model.object(i).volume(j).mesh().vertices()/triangles() (local mm coordinates; world = instance.matrix() @ volume.matrix() @ v). Valid only during this call.
- **`object_indices`** (property)
  
  Indices into ctx.model.objects() chosen for the export; empty means every object.
- **`orca_version`** (property)
- **`path`** (property)
  
  Export target path; its folder is writable for this call (scoped grant). Write the file yourself so the write is attributed to your plugin.

#### `ExporterPluginCapabilityBase`

- 构造：**`__init__(self: orca.exporter.ExporterPluginCapabilityBase) -> None`**
- **`export_file(self: orca.exporter.ExporterPluginCapabilityBase, ctx: orca.exporter.ExporterContext) -> orca.ExecutionResult`**
  
  Write the export (synchronous; the host calls this on a worker thread while the UI stays responsive). Read geometry from ctx (never orca.host.model()), write ctx.path yourself. Return ExecutionResult.success(message) or .failure(...). Params like unit conversion belong in the capability config, not the context.
- **`get_supported_extensions`** (instancemethod)
  
  Extensions this exporter offers, as lower-case dot-prefixed strings ([".hul", ...]). Resolved once at load; keep it static per capability.
- **`get_type(self: orca.exporter.ExporterPluginCapabilityBase) -> orca.PluginType`**

### 模块 `orca.importer` — Importer 能力（格式导入）【fork 先行，契约 provisional】


#### `ImporterPluginCapabilityBase`

- 构造：**`__init__(self: orca.importer.ImporterPluginCapabilityBase) -> None`**
- **`get_supported_extensions`** (instancemethod)
  
  Extensions this importer claims, as lower-case dot-prefixed strings ([".hul", ...]). Resolved once at load; keep it static per capability.
- **`get_type(self: orca.importer.ImporterPluginCapabilityBase) -> orca.PluginType`**
- **`import_file(self: orca.importer.ImporterPluginCapabilityBase, path: str) -> orca.ExecutionResult`**
  
  Convert one file (synchronous; the host calls this on a worker thread). Write the converted, host-loadable mesh file(s) (.stl/.obj/.3mf) under orca.host.plugin.storage() and return ExecutionResult.success(data=json with {"files": [paths]}). Return .skipped(path) to decline; .failure(...) for errors. The input's folder is readable for this call (scoped read grant); reading anything else needs the plugin's own fs_read permission.

### 模块 `orca.script` — Script 能力基类


#### `ScriptPluginCapabilityBase`

- 构造：**`__init__(self: orca.script.ScriptPluginCapabilityBase) -> None`**
- **`execute(self: orca.script.ScriptPluginCapabilityBase) -> orca.ExecutionResult`**
- **`get_type(self: orca.script.ScriptPluginCapabilityBase) -> orca.PluginType`**

### 模块 `orca.slicing` — 切片管线能力

- **Step** 枚举值：`posSlice`、`posPerimeters`、`posEstimateCurledExtrusions`、`posPrepareInfill`、`posInfill`、`posIroning`、`posContouring`、`posSupportMaterial`、`posDetectOverhangsForLift`、`posSimplifyPath`、`psWipeTower`、`psSkirtBrim`、`psGCodePostProcess`

**函数**

- **`unscale(coord: typing.SupportsInt) -> float`**
  
  Convert a scaled integer coordinate to millimeters (reads the live SCALING_FACTOR).


#### `SlicingPipelineCapabilityBase`

- 构造：**`__init__(self: orca.slicing.SlicingPipelineCapabilityBase) -> None`**
- **`execute(self: orca.slicing.SlicingPipelineCapabilityBase, arg0: orca.slicing.SlicingPipelineContext) -> orca.ExecutionResult`**
- **`get_type(self: orca.slicing.SlicingPipelineCapabilityBase) -> orca.PluginType`**

#### `SlicingPipelineContext`

- **`cancelled(self: orca.slicing.SlicingPipelineContext) -> bool`**
- **`config_value(self: orca.slicing.SlicingPipelineContext, key: str) -> object`**
  
  serialized value of a resolved (full) print config option for this slice, or None if absent. Shorthand for ctx.print.config_value(key).
- **`gcode_path`** (property)
  
  Path to the working G-code file, set ONLY at Step.psGCodePostProcess. Edit it in place; empty at every other step.
- **`host`** (property)
  
  Target host at Step.psGCodePostProcess ("File", "OctoPrint", ...); empty otherwise.
- **`object`** (property)
  
  orca.host.PrintObject for object-scoped steps, or None for print-wide steps. Valid only during the execute(ctx) call.
- **`orca_version`** (property)
- **`output_name`** (property)
  
  Final output G-code name at Step.psGCodePostProcess (mirrors SLIC3R_PP_OUTPUT_NAME); empty otherwise.
- **`print`** (property)
  
  The orca.host.Print being sliced — the raw slicing graph, exactly what the C++ pipeline walks. Valid only during the execute(ctx) call. For mesh access use ctx.print.model() (the Print's snapshot), never orca.host.model().
- **`step`** (property)

#### `Step`

- 构造：**`__init__(self: orca.slicing.Step, value: typing.SupportsInt) -> None`**
- **`name`** (property)
- **`posContouring`** (Step)
- **`posDetectOverhangsForLift`** (Step)
- **`posEstimateCurledExtrusions`** (Step)
- **`posInfill`** (Step)
- **`posIroning`** (Step)
- **`posPerimeters`** (Step)
- **`posPrepareInfill`** (Step)
- **`posSimplifyPath`** (Step)
- **`posSlice`** (Step)
- **`posSupportMaterial`** (Step)
- **`psGCodePostProcess`** (Step)
- **`psSkirtBrim`** (Step)
- **`psWipeTower`** (Step)
- **`value`** (property)

### 模块 `orca.pages` — Pages 能力（插件页签）


#### `PagesPluginCapabilityBase`

- 构造：**`__init__(self: orca.pages.PagesPluginCapabilityBase) -> None`**
- **`get_icon(self: orca.pages.PagesPluginCapabilityBase) -> str`**
- **`get_type(self: orca.pages.PagesPluginCapabilityBase) -> orca.PluginType`**
- **`get_ui(self: orca.pages.PagesPluginCapabilityBase) -> str`**
- **`on_message(self: orca.pages.PagesPluginCapabilityBase, arg0: str) -> None`**
- **`post_message(self: orca.pages.PagesPluginCapabilityBase, data: object) -> None`**
  
  Send a JSON-compatible value to the page's window.orca.onMessage handlers.

### 模块 `orca.resource_texture` — 资源纹理能力


#### `ResourceTexturePluginCapabilityBase`

- 构造：**`__init__(self: orca.resource_texture.ResourceTexturePluginCapabilityBase) -> None`**
- **`get_texture_dir(self: orca.resource_texture.ResourceTexturePluginCapabilityBase) -> str`**
- **`get_type(self: orca.resource_texture.ResourceTexturePluginCapabilityBase) -> orca.PluginType`**

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

### 5.1 fork 自增面（上游无对应，跨发行版插件不要依赖）

与上表裁剪相反方向的差异：本树新增、上游（orca/main 与 women 线）均无对应的宿主 API。跨发行版插件用 `getattr(orca.host, "API_VERSION", 0)` 做特征探测后再使用：

- **`orca.host.API_VERSION`**：本树宿主面修订号（治理面，随表面变更递增；本版 6：1=plate 域+Plater 动作，2=模型编辑+STL 导出，3=建模域，4=编辑补全，5=涂色，6=耗材边界收尾）。
- **`orca.host.plate`**：多盘域（plate_count/current_plate_index/select_plate/create_plate/duplicate_plate/delete_plate/select_plate_by_object + `Plate` 句柄的 name/size/origin/object_indices/objects_bounding_box/extruders/bed_type/can_slice/slice 状态谓词/gcode_filename）。
- **Plater 动作方法**（对象管理/布局/历史/项目/视图，均 UI 线程）：remove_object、delete_all_objects、remove_selected、select_all/deselect_all、select_current_plate_objects、increase/decrease_instances、duplicate_selection、center_selection、mirror、split_object/split_volume、optimize_rotation、arrange/orient、fill_bed_with_instances、scale_selection_to_fit_print_volume、convert_unit、copy/cut/paste、set_selected_visible、exit_gizmo、undo/redo 及 can_* 谓词、open_project/new_project/save_project、get_export_gcode_filename、select_view/select_view_3D 等。
- **模型编辑**（API_VERSION>=2）：rename_object / rename_volume（含 ObjectRenamed 生命周期事件与 undo 快照）、apply_object_transform（绝对置位，全实例）、apply_volume_config、set_object_printable / set_instance_printable、merge_volumes（走 ModelObject::merge_volumes）。
- **STL 导出**（API_VERSION>=2）：export_object_stl（单对象局部网格）/ export_stl（全模型世界位网格），均为 audit 门控写。
- **建模域**（API_VERSION>=3，第四批，2026-10-29，经四员评审团队定案）：get_primitive_shapes（7 种图元名查询）、add_primitive（图元新独立对象，load_shape_object 路径）/ add_primitive_volume（向既有对象加图元体积，load_generic_subobject 模型段，显式 object/instance 索引替代选择态；slab 按实例包围盒取尺寸）、cut_horizontal（世界高度水平切割，Plater::cut_horizontal+Cut::perform_with_plane，gizmo 属性位 7 个；原对象删除、尾部追加，新对象索引按 id 差分返回；z 先验界外/NaN 拒绝）、add_text_object / add_text_volume（同步构网格：Emboss::text2vshapes→union_with_delta→polygons2model 全 libslic3r 出口；写 text_configuration+emboss_shape 保持 Emboss gizmo 可再编辑；默认字体=内置 HarmonyOS Sans SC，自定义 font_path 走 open("r") audit；文本上限 1000 字符）、add_svg_object（GLGizmoSVG 路径重载，异步 job+finalize 开 gizmo，预检绕开模态框，deselect 固定独立对象形态）。全部 UI 线程、audit 门控读、快照名贴 GUI 原文；曲面图元角度步长贴上游 primitive_angle_step 公式（fork GUI 仍固定 PI/90..PI/60）。
- **编辑补全**（API_VERSION>=4，第五批，2026-10-29，经四镜合并评审定案）：simplify_volume（quadric edge collapse 纯核 its_quadric_edge_collapse，keep_ratio=保留比例（注意与 GUI 滑条"删除百分比"互补）/ target_triangle_count 二选一，同步执行+GIL 释放）、is_netfabb_repair_available + fix_through_netfabb（Win10SDK WinRT 本地修复的无进度框形态：MTA worker 线程复刻 fix_model_by_win10_sdk_gui 往返、临时文件全失败路径清理、失败时还原 changed_mesh 状态再抛）、set_object_extruder / set_volume_extruder（fill_color 数据面：对象级清除子 MODEL_PART 覆盖、volume 级 0 烘焙父值、fila 列图标/场景/用量通知刷新链）。simplify 与 repair 带 gizmo 关闭门禁（check_gizmos_closed_except(Undefined)，快照内栈保护）。
- **涂色域**（API_VERSION>=5，第六批，2026-10-29，归类判定：写侧=host API）：get_facet_painting / set_facet_painting / clear_facet_painting（Plater 链，PluginHostPainting.cpp）。四层 fdm_support/seam/mmu/fuzzy_skin；每原始三角形一个状态值（0=未涂；support/seam 1=强制 2=阻挡；fuzzy 1；mmu=1-based 挤出机号，≤已载耗材数先验拒绝）。IO 为扁平 int 序列（list/tuple，numpy 1-D 数组经序列协议同样可用；嵌入式运行时不保证 numpy，故不用 py::array_t 契约）。写路径 = TriangleSelector 重建 + FacetsAnnotation::set（涂色 gizmo 的 update_model_object 同款）+ 快照 + update_info_items + 后台重切片事件；读路径 = selector.deserialize 重建逐面视图（TriangleSelector::get_facet 为本批补的 const 读出器）。
- **耗材边界收尾**（API_VERSION>=6，第七批，2026-10-29；与批5的 set_*_extruder 合起来即原"耗材边界"候选域）：模块级 get_flush_volumes（{n, matrix 行主序 N×N, vector, multiplier}，N=sqrt 矩阵长同 GUI 推导）/ set_flush_volumes（matrix/vector/multiplier 三可选；NaN 安全值域校验；写 project_config 后走 Sidebar::auto_calc_flushing_volumes 收尾：export_selections + update_project_dirty_from_presets + EVT_SCHEDULE_BACKGROUND_PROCESS——该事件本批补了 Plater.hpp 的 wxDECLARE_EVENT）/ flush_volume_between（纯函数暴露 FlushVolCalculator 颜色距离估算，任意线程）。
- **Importer/Exporter 能力**（第三批，2026-10-29，经四员评审团队定案 v2 契约）：文件交换式导入（插件转换落盘自身 storage → 宿主 `Model::read_from_file` 装载，scoped 只读根，worker 驱动）+ 类型化 `ExporterContext`（模型快照引用 + 零拷贝网格拉取，Export 菜单动态插件段）。两能力均为 fork 先行实现，上游若落地不同形状按别名迁移。
- **杂项**：`orca.host.data_dir()`。另有更早的 fork 自增（load_model_files、open_project、schedule_plate_gcode_export、apply_object_config 系、slice_state 系、app_language），见第 3 节符号文档。

### 5.2 Analysis / Visualization 能力最小契约（设计稿，未实现）

`PluginCapabilityType::Analysis` 与 `Visualization` 两个枚举空位（PythonPluginInterface.hpp:16）按批 3 模子的最小契约设计如下。**仅为设计稿**：实现前须过四员评审（契约/接线线程/安全/上游对齐），并重新核对上游是否已落地同名能力（PrinterConnection 的教训：动裁剪域前先查台账裁剪声明）。

**Analysis（宿主在自身流程里调度插件做切片后分析——"插件实现一个功能给用户用"→capability）**

```python
class AnalysisPluginCapabilityBase(orca.base):
    def get_name(self) -> str: ...
    def get_type(self) -> str: return "analysis"
    def get_trigger(self) -> str: ...          # "post-slice"（首个形态；扩展点：pre-slice/import）
    def analyze(self, ctx: AnalysisContext) -> orca.ExecutionResult: ...
# AnalysisContext（类型化，批3 ExporterContext 模子）：
#   plate_index: int；gcode_path: str（trampoline scoped 只读根=gcode 目录）
#   duration_s / filament_g / layer_count: float/int（GCodeProcessorResult 摘要，小数据值拷贝）
# 返回：Success.data = JSON 小数据（指标/结论文本——结论性数据允许 JSON，网格级数据永远不允许）
# 调度：宿主在 GCodeExportFinished 后于 worker 线程驱动（trampoline 自取 GIL），
#       UI 侧零等待；结果进通知面板。错误分层沿用 Skipped/Recoverable/Fatal。
```

**Visualization（插件给 3D 视图画叠加层——数据面类型化，不走 JSON 网格）**

```python
class VisualizationPluginCapabilityBase(orca.base):
    def get_name(self) -> str: ...
    def get_type(self) -> str: return "visualization"
    def get_layers(self) -> list[str]: ...     # 声明的叠加层名（物化期一次解析缓存 C++ 侧）
    def build_layer(self, name: str, ctx: SceneContext) -> orca.ExecutionResult: ...
# SceneContext：当前板/相机/选择摘要 + 宿主提供的类型化构建器
#   builder.lines(vertices: Sequence[Vec3], color, width) / .triangles(...) / .points(...)
#   （类型化序列入，宿主侧组顶点缓冲——批 6 涂色"序列而非 numpy/JSON"同款纪律）
# 调度：场景重建时 worker 线程构建、UI 线程提交 GPU；绝不在 UI 线程回调 Python。
```

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
