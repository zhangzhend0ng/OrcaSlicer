# Host API 审计方法

来源：women 分支 docs/plugins/HOST_API_AUDIT.md（0aa325e101）裁剪移植，只保留**方法**与其在本树的落点。裁剪：women 的逐组状态断言（is_signed_in 网关映射、network_plugin_version Bambu 细节、precise-seam 9 符号清单等）描述的是 women 实现——本树对应面与之不同（见下），不携带其状态结论。

## 方法

1. **钉住基准提交**：选一个固定的上游 OrcaSlicer commit 作为对照面（women 用 `14a1aa33…`），审计范围 = `src/slic3r/plugin/host/PluginHost*.cpp` 注册的 `orca.host` 公开类型、枚举、方法、属性与子模块。返回字典的键不混算为 Python 符号。
2. **源码逐文件比对**：每个绑定文件与基准做差异审查，差异逐条归因（fork 裁剪 / ADAPTED / 状态等价）。
3. **活体导出验证**：从当前真实绑定导出 SDK 成员清单并独立校验（本树：`tools/plugin_sdk` + `scripts/generate_plugin_sdk.py` / `verify_plugin_sdk.py`）。
4. **快照门禁**：API 面变化必须过期望快照 diff（本树：`sandboxes/api_surface_dump_plugin.py` 双 App 内省 dump + `diff_api_surface.py --expect`，基线 `expected_snapshot_557.json`，存 `SnapmakerOrca-mcp/sync-scratch/api_surface/`）。

## 本树结构性差异（审计时的已知裁剪面）

- `app.selected_printer()` 与 printer_agent 域整体裁剪（台账范围声明）；对照时该项"缺失"是预期。
- `app_info()` 键集为本树 6 键（version/mode/language/app_config_version/stealth_mode/is_signed_in）：云代理（Orca/Bambu 双登录态、network plugin 版本/错误）在本树为裁剪/桩域，不导出。
- 云域（CloudPluginService 等）为桩；对照时云向符号按台账桩域规则处理。
- `orca.host.preset` 写侧事务面来自上游 557feba649 吸收批（快照 29 项新增），非 women 的只读 PresetView 模型。
