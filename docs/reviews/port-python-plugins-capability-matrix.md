# port/python-plugins 插件能力矩阵（冻结 v1，2026-10-23）

基准：本仓 `port/python-plugins` @ e1580a3331 + 当日收口批（CGAL 配方/测试改写）；上游对照 SoftFever/OrcaSlicer `orca/main` @e5bb802378。
决策与批次记录以 [台账](port-python-plugins-absorption-ledger.md) 为准，本表只述**现状**；"插件能不能用 X"先查本表。
维护规则：能力面变化时改对应行并升版本号；每行必须带可复查的 `file:line` 或台账锚点。

## 三列矩阵

| # | 能力/域 | 判定 | 现状与证据 |
|---|---|---|---|
| 1 | 切片管线订阅（`slicingPipeline` 能力，12/13 步骤） | **支持** | Print.cpp:2540-2642 `hook_after` 链：posSlice/posPerimeters/posEstimateCurledExtrusions/posPrepareInfill/posInfill/posIroning/posSupportMaterial/posSimplifyPath/psWipeTower/psSkirtBrim 均有真实触发点。语义=**步骤间挂钩**：该步 `set_done()` 之后、下一步之前回调；插件可读改对象状态，posPrepareInfill 处改 `fill_surfaces` 会级联到后续 infill（契约注释 SlicingPipelinePluginCapability.cpp:23-24）。hook 内只能 log（PluginHooks.cpp kStepNames 旁注释：`m_step_active`=-1，禁调 `active_step_add_warning`） |
| 2 | `Step.posContouring` | **不触发** | 枚举在（Print.hpp:137）、可订阅（SlicingPipelinePluginCapability.cpp:21），但本 fork Print.cpp **0 处引用**（上游 orca/main 6 处）→ 订阅后该步骤永不回调。PluginHooks.cpp:122 kStepNames 仅日志名表，不构成触发点 |
| 3 | `Step.psGCodePostProcess`（G-code 后处理） | **支持** | 从 GUI 导出面 seam 触发（PostProcessor.cpp:246-332）：ctx.print/object=None，就地改写 `ctx.gcode_path` 文件；一切可多次（file export / plate 切片） |
| 4 | Pages 能力（插件页签） | **支持** | pluginTypes/pages；卸载/摘 tab 接线 e1580a3331。实机开关循环验收进行中（任务 5），结果回填本行 |
| 5 | resourceTexture 能力 | **支持** | 批次 5d 53/53 门禁（台账批次史） |
| 6 | script 能力 | **支持** | pluginTypes/script 在树 |
| 7 | 权限审计沙箱（fs/socket 授权 + 授权落盘） | **支持** | fs-read/fs-write/socket 弹窗授权链路实测（台账"实机插件适配验证"+"裁剪域收口批"）；targetless 授权经 `permissions.events` 桶落盘（上游两行回填勘误，同上） |
| 8 | 插件发现与安装 | **支持（仅本地目录）** | 发现收敛纯本地 `{data_dir}/orca_plugins/`（决策 4313d584d8，台账）；install-local 全链在树（台账"验证与勘误"install 链路条） |
| 9 | 云插件域（云端发现/订阅/更新/插件中枢） | **裁剪** | 禁用桩：`cloud_plugin_service_available()` 恒 false，云源插件动作降级本地动作集+Local 徽标（台账"裁剪域收口批"五处死线清理） |
| 10 | printerAgent 域（`orca.printer_agent` 138 API + `selected_printer()`） | **裁剪** | printerAgent{cpp,hpp,Trampoline} 未引入（全树 find 为空）；依赖 selected_printer() 的插件不兼容（台账范围声明，待该域整体决策） |
| 11 | 快捷键簇（#15706/#15862 等） | **裁剪（永不吸收）** | Shortcuts.hpp 基座从未导入；fork 自有 keyboard_shortcuts 实现（台账范围声明） |
| 12 | 非插件 web 页面树（homepage/guide/model/login 等） | **裁剪（fork 自有资产线）** | 与 orca/main 差 701 文件，不属插件吸收面（台账范围声明） |

## 已知宿主差异（捆绑 CPython，跨列）

| 差异 | 证据 | 状态 |
|---|---|---|
| `socket.__new__` 授权提示双触发；`getaddrinfo` 解析不弹授权 | tests/slic3rutils/test_plugin_audit.cpp:924/:976 两用例无条件 SKIP，SKIP 处 KNOWN-GAP 注释 | 按实际运行时语义改写断言、恢复两条语义覆盖（任务 4），完成后本行回填 |

## 未验证项与补全路径

- 行 4（Pages 卸载/摘 tab）实机完整开关循环：任务 5（Windows CDP 驱动）验收后回填。
- macOS universal 包捆绑 Python 运行时 Intel 切片：修复已落（本批：`build_universal()` 对 `Contents/MacOS/{python,tools}` 逐 Mach-O lipo 合并 + `verify_universal_archs()` 双架构断言 + `scripts/scan_app_archs.sh` 打包后扫描门）；stub 夹具 20/20 行为验证通过（含孤儿双向检测/非 Mach-O 跳过/strict 判定）。**未实机验证**：真 lipo/codesign 行为与 Intel 包启动需 mac 构建机执行 `build_release_macos.sh -a universal` + 对产物跑 `scan_app_archs.sh --strict`。
