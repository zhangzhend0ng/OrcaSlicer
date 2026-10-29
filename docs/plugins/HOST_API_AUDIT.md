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

## 本树自增面（上游无对应；对照时该项"多出"是预期，2026-10-29 批）

- 批 1（API_VERSION 1）：`orca.host.plate` 多盘域、Plater 动作方法族（对象/布局/undo/项目/视图）、`orca.host.API_VERSION`、`orca.host.data_dir()`。
- 批 2（API_VERSION 2）：模型编辑（rename_object/rename_volume/apply_object_transform/apply_volume_config/set_*_printable/merge_volumes）与 STL 导出（export_stl/export_object_stl）。注：上游 Importer/Exporter 仅为 PluginCapabilityType 枚举占位，两条参考线均无实现，此域为纯 fork 架构。
- 批 3（表面不变，API_VERSION 仍 2）：Importer/Exporter 能力（capability 侧，契约 provisional）。
- 批 5（API_VERSION 4）：编辑补全——simplify_volume、is_netfabb_repair_available、fix_through_netfabb、set_object_extruder、set_volume_extruder（PluginHostEditing.cpp 新 TU，挂 Plater 链）。合并评审（四镜）要点：keep_ratio 命名避开 GUI decimate_ratio 的删除/保留互补陷阱；快照名贴 GUI（"Simplify <volume 名>"）；gizmo 关闭门禁（上游 check_gizmos_closed_except 同款，防 undo 内栈错位）；netfabb 核从 FixModelByWin10.hpp 增补导出（禁 extern 私设）、临时文件失败路径清理、运行时可用性探测（HAS_WIN10SDK && is_windows10()）；fill_color 语义并入挤出机指派（volume 级 0 烘焙父值贴上游）。fix_model_by_win10_sdk 回调不可空（核无条件调用）。功能冒烟 e1-e5 全绿（含 netfabb 实修一次）。
- 批 6（API_VERSION 5）：涂色域——get_facet_painting / set_facet_painting / clear_facet_painting（PluginHostPainting.cpp，挂 Plater 链）。归类判定：涂色数据用户在 GUI 直接可见且切片消费，但"插件算出方案回写"是替用户操作宿主 → host API（非 Visualization capability）。要点：逐面状态扁平 int 序列（嵌入式运行时无 numpy，py::array_t 不可作契约；numpy 数组经序列协议兼容）；TriangleSelector 增补 const get_facet 读出器（位流格式不复刻）；写路径贴 GLGizmoFdmSupports::update_model_object（FacetsAnnotation::set + touch + update_info_items + EVT_GLCANVAS_SCHEDULE_BACKGROUND_PROCESS）；mmu 状态 ≤ 已载耗材数先验拒绝。功能冒烟 p1-p4 全绿。
- 批 7（API_VERSION 6）：耗材边界收尾——orca.host 模块级 get_flush_volumes / set_flush_volumes / flush_volume_between（挂在 PluginHostPresets.cpp，project_config 数据面）。要点：矩阵 N×N 行主序（N=sqrt 同 GUI）；写后走 auto_calc_flushing_volumes 同款收尾（export_selections + dirty + 重切片事件，事件在 Plater.hpp 补 wxDECLARE_EVENT）；纯计算核 FlushVolCalculator 以无状态函数暴露（任意线程）。原候选域"耗材边界"的挤出机指派部分已在批 5（set_object_extruder/set_volume_extruder）交付。功能冒烟 f1-f3d 全绿。
- 批 4（API_VERSION 3）：建模域 host API——get_primitive_shapes、add_primitive、add_primitive_volume、cut_horizontal、add_text_object、add_text_volume、add_svg_object（PluginHostModeling.cpp，挂 Plater 链）。四员评审（契约/接线线程/安全/上游对齐）定案要点：拆分双形态签名为显式 object_idx 两法；cut 新对象索引按 id 差分（delete_object 中间 erase，size 差不可靠）；font/svg 路径一律 PySys_Audit("open","r") 前置；文本 depth 默认贴上游 1.（EmbossProjection 默认）；曲面图元角度贴上游 primitive_angle_step。功能冒烟（modeling_smoke_plugin.py，挂 ProjectDirtyChanged 事件）s1-s9 全绿；ensure_3d_view（NativeCommands object_op 先例）补齐 is_view3D_shown 门禁与 gizmo 懒初始化前置。
- 批 3（capability 侧，非 host 面）：Importer/Exporter 能力三件套 + load_files 未知扩展名分发 + Export 菜单插件段。上游枚举占位转正，契约 v2 为评审定案的 fork 先行设计（文件交换 + 类型化 ctx），上游落地后按别名对账。
- 上游两条参考线（orca/main、women）对上述各批均无对应符号（见 API_REFERENCE §5.1）。快照基线吸收后需重 dump。
