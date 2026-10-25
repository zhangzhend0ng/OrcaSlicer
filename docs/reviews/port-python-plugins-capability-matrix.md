# port/python-plugins 插件能力矩阵（v2，2026-10-25；v1 冻结于 2026-10-23）

基准：本仓 `port/python-plugins` @ e2cbf01ee0 + 10-25 修复批（Pages boot 竞态）；上游对照 SoftFever/OrcaSlicer `orca/main` @e5bb802378（557feba649 未吸收，台账"三方复查轮"节有决策）。
决策与批次记录以 [台账](port-python-plugins-absorption-ledger.md) 为准，本表只述**现状**；"插件能不能用 X"先查本表。
维护规则：能力面变化时改对应行并升版本号；每行必须带可复查的 `file:line` 或台账锚点。

## 三列矩阵

| # | 能力/域 | 判定 | 现状与证据 |
|---|---|---|---|
| 1 | 切片管线订阅（`slicingPipeline` 能力，12/13 步骤） | **支持** | Print.cpp:2541-2812 触发点链（hook_after 站点 2551/2571/2580/2596/2599/2612/2652 + run_pipeline_hook 站点 2646/2709/2795/2812）：posSlice/posPerimeters/posEstimateCurledExtrusions/posPrepareInfill/posInfill/posIroning/posDetectOverhangsForLift/posSupportMaterial/posSimplifyPath/psWipeTower/psSkirtBrim 均有真实触发点（+PostProcessor.cpp 的 psGCodePostProcess=12/13，见行 3）。语义=**步骤间挂钩**：该步 `set_done()` 之后、下一步之前回调；插件可读改对象状态，posPrepareInfill 处改 `fill_surfaces` 会级联到后续 infill（契约注释 SlicingPipelinePluginCapability.cpp:18-19）。hook 内只能 log（PluginHooks.cpp kStepNames 旁注释：`m_step_active`=-1，禁调 `active_step_add_warning`） |
| 2 | `Step.posContouring` | **不触发** | 枚举在（Print.hpp:137）、可订阅（SlicingPipelinePluginCapability.cpp:21），但本 fork Print.cpp **0 处引用**（上游 orca/main 6 处）→ 订阅后该步骤永不回调。PluginHooks.cpp:122 kStepNames 仅日志名表，不构成触发点 |
| 3 | `Step.psGCodePostProcess`（G-code 后处理） | **支持** | 从 GUI 导出面 seam 触发（PostProcessor.cpp:246-332）：ctx.print/object=None，就地改写 `ctx.gcode_path` 文件；一切可多次（file export / plate 切片） |
| 4 | Pages 能力（插件页签） | **支持** | pluginTypes/pages；卸载/摘 tab 接线 e1580a3331。**实机全循环已验（10-25 复验，CDP+PrintWindow+UIA 盲操，六段全绿）**：禁用→tab/webview 摘除 ✓，重启用→tab/webview 回归 ✓（7e46b8c088 + 10-25 boot 竞态修复，见行 13），卸载（web 命令+原生确认框）→行/目录/tab 全清 ✓，重启零残留 ✓，目录恢复+refresh_plugins 热发现+启用回归 ✓，再重启 tab 持久 ✓ |
| 5 | resourceTexture 能力 | **支持** | 批次 5d 53/53 门禁（台账批次史） |
| 6 | script 能力 | **支持** | pluginTypes/script 在树 |
| 7 | 权限审计沙箱（fs/socket 授权 + 授权落盘） | **支持** | fs-read/fs-write/socket 弹窗授权链路实测（台账"实机插件适配验证"+"裁剪域收口批"）；targetless 授权经 `permissions.events` 桶落盘（上游两行回填勘误，同上） |
| 8 | 插件发现与安装 | **支持（仅本地目录）** | 发现收敛纯本地 `{data_dir}/orca_plugins/`（决策 4313d584d8，台账）；install-local 全链在树（台账"验证与勘误"install 链路条） |
| 9 | 云插件域（云端发现/订阅/更新/插件中枢） | **裁剪** | 禁用桩：`cloud_plugin_service_available()` 恒 false，云源插件动作降级本地动作集+Local 徽标（台账"裁剪域收口批"五处死线清理） |
| 10 | printerAgent 域（`orca.printer_agent` 138 API + `selected_printer()`） | **裁剪** | printerAgent{cpp,hpp,Trampoline} 未引入（全树 find 为空）；依赖 selected_printer() 的插件不兼容（台账范围声明，待该域整体决策） |
| 11 | 快捷键簇（#15706/#15862 等） | **裁剪（永不吸收）** | Shortcuts.hpp 基座从未导入；fork 自有 keyboard_shortcuts 实现（台账范围声明） |
| 12 | 非插件 web 页面树（homepage/guide/model/login 等） | **裁剪（fork 自有资产线）** | 与 orca/main 差 701 文件，不属插件吸收面（台账范围声明） |
| 13 | 会话中插件装载的 Pages 注册 | **支持（7e46b8c088 + boot 竞态修复）** | 7e46b8c088 补 load 侧接线（`PluginPages::on_plugin_register` 曾零调用方）。**10-25 三方复查发现残余竞态**：插件加载若在 MainFrame 构造窗口内完成（initialize 枚举已过、`mainframe` 尚未赋值），load 回调被静默跳过且无人兜底→tab 永不回归（卸载→恢复→启用链路跨重启复现，10-23 验收的"恢复回归 ✓"系竞态偶然取胜）。修复=两个 mainframe 赋值点后幂等重放注册（`GUI_App::replay_plugin_pages_registration`，boot 与 recreate_GUI 双站点）+ on_cap_register 静默失败路径补 error 日志；六段链复验全绿 |

## 已知宿主差异（捆绑 CPython，跨列）

| 差异 | 证据 | 状态 |
|---|---|---|
| ~~`socket.__new__` 授权提示双触发；`getaddrinfo` 解析不弹授权~~ | 曾致 tests/slic3rutils/test_plugin_audit.cpp 两用例无条件 SKIP | **已消除（10-23 实测）**：捆绑 CPython 3.12.13 下 `socket.__new__` 每次创建单次触发且授权经 events 桶落盘记忆、`getaddrinfo` 正常带目标弹窗；两用例按上游**原始断言**恢复后真 RUN（8/10 断言全过，Windows）。旧行为疑随 permissions.events 桶回填（台账"裁剪域收口批"勘误）或 Python 重建而消失 |

## 未验证项与补全路径

- 行 4（Pages 卸载/摘 tab）实机完整开关循环：**已完成（10-23 深夜）**，见行 4/13 回填；能力级（单 capability）toggle 路径未单测（代码审查覆盖：set_capability_enabled 发能力级回调→on_cap_register 在树）。
- macOS universal 包捆绑 Python 运行时 Intel 切片：修复已落（本批：`build_universal()` 对 `Contents/MacOS/{python,tools}` 逐 Mach-O lipo 合并 + `verify_universal_archs()` 双架构断言 + `scripts/scan_app_archs.sh` 打包后扫描门）；stub 夹具 23/23 行为验证通过（含**整树缺失负例**（10-24 复核补：ARM 底包整目录缺席而 Intel 侧有 Mach-O 须失败，两侧皆无才跳过）、单文件双向孤儿检测、非 Mach-O 跳过、strict 判定）。**未实机验证**：真 lipo/codesign 行为与 Intel 包启动需 mac 构建机执行 `build_release_macos.sh -a universal` + 对产物跑 `scan_app_archs.sh --strict`。
