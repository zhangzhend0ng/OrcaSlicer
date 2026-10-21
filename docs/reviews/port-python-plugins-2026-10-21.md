# Review: port/python-plugins (2026-10-21)

- 基线：abd25fc161（origin/upstream release_2.4.1）→ HEAD 4f41f0f5e9（2 commits，177A/2D/42M，+56861/−1323）
- 上游源：OrcaSlicer PR #14530 squash 2717c37f63（对照基准 `git diff 2717c37f63^1 2717c37f63`）
- Harness：common-code-review-checklist(C) / cpp-build-system(C) / cpp-thread-safety(N) / cpp-undefined-behavior(N) / cpp-lifetime(N) / cpp-wxwidgets-3-1-5(P) / cpp-secure-coding(N)
- 体量说明：+56.8k 行远超 400 行评审上限；属上游 PR 整体移植（拆分即两个提交），按移植评审处理，规则豁免记录在案。

## Verdict: REQUEST CHANGES

分支存在 **10 处编译/配置级断裂**（GUI 目标与 tests 均无法通过 configure/compile），以及裁剪残留、语义嫁接缺陷若干。该分支显然未做过一次完整构建。**必须修复全部 P0 后重新送审，重审前请在三平台至少跑一次 configure+build。**

---

## FAIL（P0：编译/配置断裂，全部 BLOCKING）

1. **[P][N] GUI_App.cpp:6573** — `open_plugins_dialog`/`open_terminal_dialog`/`open_speed_dial` 三个成员函数被插入 `show_ip_address_enter_dialog_handler`（6569 起）函数体内，其闭合 `}` 迟至 ~6655。嵌套函数定义为 ill-formed，任何编译器直接报错。修法：三个函数移到文件作用域（上游锚点：`open_presetbundledialog` 之后；SM 侧建议 `open_preferences` 之前顶格放置）。
2. **[P][N] Plater.cpp:10146-10147** — priv 成员注释中 `'\n'` 被传输过程变成真实换行，注释后半 `'), one per notification. They` 落在注释外成为裸 token（语法错误）。上游原文为单行 `joined by '\n'`。修法：恢复单行注释。
3. **[P][N] Plater.cpp:24171,24176,24192** — `p->m_inactive_shown_sig`、`p->m_broken_shown_sig` 被 `refresh_missing_plugin_block`/`revalidate_current_plate_if_plugins_missing` 引用，但 priv 结构只新增了 `m_local_missing_shown_sig`/`m_cloud_missing_shown_sig`（上游同 hunk 声明 4 个）。成员未声明，编译错误。修法：在 Plater.cpp:10150 旁补两个成员。
4. **[D][N] PluginsDialog.cpp:6 与 plugin/PluginResolver.cpp:5** — `#include "OrcaCloudServiceAgent.hpp"` / `"../Utils/OrcaCloudServiceAgent.hpp"`；该文件已随裁剪删除且全树不存在（上游 2717c37f63:src/slic3r/Utils/OrcaCloudServiceAgent.hpp 有实体）。预处理错误。修法：删两处 include 及文件内对 agent API 的使用（与 FAIL 11 联动）。
5. **[D][N] NotificationManager.cpp:2201,2211** — `render_hyperlink_action` 被调用两处，但移植侧 hpp 无声明（port hpp grep=0）、cpp 无定义（port 仅 2 处调用点）。上游 hpp:530 声明 + cpp 定义被丢。编译错误。修法：补上上游 `render_hyperlink_action` 的声明与定义块。
6. **[D][N] BackgroundSlicingProcess.cpp:910-960（export_gcode）** — 上游函数体被**追加**在 SM 原函数体之后而非替换：`error_message`/`copy_ret_val`/`evt`/`output_gcode_str` 同作用域重复声明（redefinition 编译错误）；即使修好声明，copy_file、导出完成事件、`gcode_add_line_number` 均会执行两遍（第二次 gcode_add_line_number 会二次改写行号）。修法：删除 910-960 追加块，保留 SM 原体（两者逻辑等价，仅格式差异）。
7. **[C][N] src/slic3r/CMakeLists.txt:826** — `libslic3r_gui` 链接行缺 `pybind11::embed`（上游 843 行有）；而 `plugin/PythonInterpreter.cpp`、`plugin/PythonPluginBridge.cpp` 编入该目标且 include `<pybind11/embed.h>` → 缺 include 路径与 libpython。修法：链接行追加 `pybind11::embed`。
8. **[C][N] src/CMakeLists.txt:327,329,493-495,544** — 四处引用目标名 `OrcaSlicer`，实际目标为 `Snapmaker_Orca`（588 行已改名证明部分适配漏网）→ 对应平台 configure/generate 直接失败。修法：四处替换为 `Snapmaker_Orca`。
9. **[C][N] plugin/PluginHooks.cpp:11、GUI/PostProcessor.cpp:5** — `#include "libslic3r_version.h"`：文件不存在，且全树无任何 configure_file/生成器产出它（上游在更早提交中生成该头）。两处分别使用 `SoftFever_VERSION`（PluginHooks.cpp:83、PostProcessor.cpp:267）。修法：引入头生成（configure_file .in），或改用现有版本宏。
10. **[C][N] tests/slic3rutils/CMakeLists.txt** — :21 列出 `../fff_print/test_helpers.cpp`（文件不存在，configure 报 Cannot find source file）；:163 调用未定义命令 `orcaslicer_discover_tests`（上游定义在 tests/CMakeLists.txt:55，本分支基线无）；:42-46 测试目标缺 `pybind11::embed`（新增 test_plugin_*/test_slicing_pipeline_* 用 pybind11 头）。修法：移植 helpers 或删条目；删 :163 或移植函数定义；补链接。

## FAIL（P1：裁剪残留 / 语义缺陷，需修复）

11. **[B][C] plugin/CloudPluginService.hpp:14,24,25,43、CloudPluginService.cpp:12,14、plugin/PluginManager.hpp:30,175** — `OrcaCloudServiceAgent` 前向声明 + `set_cloud_agent`/`get_cloud_agent` API 残留（编译安全：incomplete type + shared_ptr；桩内无解引用、无 UB 死路径——此项 PASS），但违反「全树不得残留」的裁剪要求，且是 FAIL 4 两处断链 include 的根因。修法：删除 agent API 面（hpp 声明/成员、cpp 定义、PluginManager.hpp:175 包装），stub 仅保留返回 false 的操作集。
12. **[A][C] Tab.cpp:1761-1766** — 插件 manifest 同步块（`m_config->def()->get(opt_key)` 解引用）插在既有 `if (m_config == nullptr) return;` 守卫**之前**；上游无此守卫，SM 有。空指针解引用风险（UB harness Item 2）。修法：把该块移到判空之后。
13. **[A][C] Plater.cpp:3533** — `use_native_device_tab` 声明后全函数无使用（上游同函数另两个配套 hunk——load_printer_url 守卫、show_device 替换——未跟随；二者仅对已裁剪的 printerAgent 有意义）。死代码 + 编译警告。修法：删除该行。
14. **[A][C] src/CMakeLists.txt:549-556（macOS bundle 块）** — 上游 `BIN_DIR=.../Contents/MacOS` hunk 丢弃，python 暂存目录错位（Xcode 下落到 build/src/python，`@executable_path/python/lib` rpath 失效）。修法：bundle 块内补 `set(BIN_DIR "$<TARGET_FILE_DIR:Snapmaker_Orca>")`。
15. **[A][C] CMakeLists.txt:1168-1170（根）** — uv 的 `install(PROGRAMS ...)` 只加进末尾 else() 分支；上游同时加进 WIN32/FHS/macOS 三个分支 → 三平台安装流缺 uv。修法：按上游补三个分支（目标名/目的地取 Snapmaker 侧）。

## PASS（折叠）

- 机械检查：锚定冲突标记 0（仅装饰性注释箭头）；`git diff ^-.*Snapmaker` 仅文件路径头行——品牌无回退；构建文件品牌全取 SM 侧（OUTPUT_NAME snapmaker-orca、Bundle 名、desktop/图标、CPACK 名）。
- Print.cpp：11/12 hook 与上游逐行一致（posContouring 属决策#3 且 SM 无 contour_z/need_z_contouring，执行干净）；sup_was_done 快照在 parallel_for 前、顺序 hook 循环在后，索引同源 m_objects，无 UB；Print.hpp hook 机制自包含（`<functional>` 已含），libslic3r 无插件依赖。
- GUI_App.cpp：init_plugin_gui_wiring 定义/调用位置、on_init_inner 时序（network→initialize→set_cloud_user→discover→wiring→action_registry→auto-load→登录同步）、shutdown 顺序（set_shutting_down→~GUI_App 内 manager/interpreter shutdown 先于 app_config 释放）均与上游一致；NetworkAgentFactory 订阅与 set_cloud_agent 注入两处裁剪点干净；detect_updater_os/arch 删除随上游且无残留调用。
- Plater.cpp：EVT_GLCANVAS_OPEN_SPEED_DIAL 绑定、send_gcode_legacy 拦截块、validate_current_plate 集成、refresh_missing_plugin_block/revalidate/install/enable 系列实现为上游等价移植（worker detach 按值捕获、progress 经 atomic+mutex、timer 经 CallAfter 删除——thread-safety 合规；report_install_failure 走 CallAfter 与上游一致）；SM 无 Plater::reslice，拦截点换至 send_gcode_legacy 属合理适配（hpp 注释仍提 reslice() 为陈旧文案，非缺陷）。
- NotificationManager：PluginMissingNotification 类与 push_plugin_missing_notification 顶层落位干净；JumpTo 按值捕获、jump 经 CallAfter 延迟；`#include <libslic3r/Preset.hpp>` 补齐（hpp 闭环）。
- OptionsGroup：`plugin_picker`/`plugin_config` 两个 GUIType case 正确落位 build_field switch（其余 hunks 为 clang-format 噪音）。
- Tab.cpp：三个 optgroup（Print/Filament/Printer 页的 Slicing Pipeline Plugin / Plugin Configuration）落位正确。
- Field.cpp（+436 尾部 PluginField/PluginConfigField）、Config.cpp（save_plugin_collection/collect_plugin_manifest，resolve_capability_fn/def 双判空）、Config.hpp、PrintConfig、Preset、Platform、GLCanvas3D、MainFrame、KBShortcuts、GUI.cpp、Widgets/ProgressDialog：落位/闭合无异常。
- CloudPluginService 桩：全部操作返回 false + 错误串，`can_fetch_cloud_plugins()=false`，无 m_orca_agent 解引用、无 UB 死路径（登录路径 fetch_plugins_from_cloud 依赖该闸门短路）。
- 裁剪清扫：printerAgent/IPrinterAgent/NetworkAgentFactory/register_python_printer_agent/cloud_provider/MultiProviderLogin/PresetBundleDialog/contour_z 等全树 0 命中（posContouring 枚举与字符串表保留属上游枚举值对齐，合法）；fuzzy-search.js 断链与上游一致（决策#5；resources/web/js/fuzzy-search.js 实存，SpeedDial 引用正确）。
- 新源文件 31 个 .cpp 全部进正确 CMake 目标（PluginHostApp.cpp 无 main()、与上游同为编入 GUI 目标，判断正确）；libslic3r CMake 已删 PostProcessor 条目；deps/python3 外部工程完整（pin URL+SHA256、三平台 relocate/stage）；第二提交（PostProcessor include 清理 + verify_python_runtime 二进制名）干净。

## 无法评估项

- 运行时行为（插件加载/切片 hook 实际执行、SSWCP 与插件的运行时交互）：编译断裂使运行时验证不可行；编译修复后需三平台冒烟 + 至少一次带 active slicing_pipeline_plugin 的切片验证。SSWCP（GUI 层协议）与切片 hook 数据面正交，静态审查未见共享状态冲突。
- options_list_storage_key 未跟随（决策#3 已知风险）：plugin_picker 字段改值标色可能不准，属已知接受项，未另计缺陷。

## 备注

- 上游 export_gcode 的注释串里本身就有跨行注释文本（每行以 `//` 开头，合法）；FAIL 6 的追加块同样合法——问题只在重复声明与双执行。
- 修复建议顺序：先 FAIL 1-10（恢复可编译），再 11-13（残留/语义），14-15 随打包联调。
