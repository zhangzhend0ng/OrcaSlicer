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
