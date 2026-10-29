# Snapmaker Orca 本地插件接口文档

> **基准**：`port/python-plugins` 分支（2026-10-28）。API 清单来自真实嵌入绑定的活体导出（`source: live-embedded-orca`，10 个模块、172 个顶层成员），非手抄源码。
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

能力（capability）是插件的功能单元，每个能力类继承一种基类并覆写其执行方法。本树可用的 Python 能力基类共四种：

| 基类 | PluginType | 执行入口 | 用途 |
|---|---|---|---|
| `orca.script.ScriptPluginCapabilityBase` | `Script` | `execute()` | 通用后台任务（可在插件对话框/快速拨盘触发） |
| `orca.slicing.SlicingPipelineCapabilityBase` | `SlicingPipeline` | `execute(ctx)` | 切片管线挂钩（含 G-code 后处理） |
| `orca.pages.PagesPluginCapabilityBase` | `Pages` | `get_ui()` / `on_message()` | 应用内插件页签（HTML） |
| `orca.resource_texture.ResourceTexturePluginCapabilityBase` | `ResourceTexture` | （见基类成员） | 资源纹理包 |

`PluginType` 枚举还含 `Analysis`/`Exporter`/`Importer`/`PrinterConnection`/`Visualization` 等值，但本树未提供对应 Python 基类——不要依赖。

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
