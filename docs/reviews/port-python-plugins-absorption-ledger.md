# port/python-plugins 吸收决策台账（living ledger）

上游对照：SoftFever/OrcaSlicer `orca/main`（审查基准 10-22 16:14 fetch @664f734e222e；收尾复查 10-22 晚 fetch @e5bb802378。**10-25 fetch 复查：`src/slic3r/plugin/` 新增 557feba649（preset plugin APIs，即范围声明中预设"合入后再评估"的 preset-plugin-apis 分支），决策见"三方复查轮"节**。**10-25 收尾轮再 fetch @09aa0114b4：新增权限系列 + 2 小提交，决策见"10-25 收尾轮"节**。每次开工须重新 fetch 复查）。
本台账为吸收/裁剪/延后决策的**唯一权威记录**：任何"已吸收"声称必须能落到本表或提交信息之一；上游新提交先在此定决策再动代码。
历史输入：10-22 早晨吸收审计（mcp 工作区未跟踪稿）+ 10-22 晚 REQUEST CHANGES 审查（docs/reviews/port-python-plugins-2026-10-22.md，mcp 工作区）。
能力矩阵：[port-python-plugins-capability-matrix.md](port-python-plugins-capability-matrix.md)（支持/裁剪/不触发现状冻结 v1，2026-10-23；"插件能不能用 X"先查矩阵，决策仍以本台账为准）。

## 范围声明（防误判）

- 只吸收**插件代码会真实调用/依赖**的面：host API 绑定、插件系统自身设施（audit/权限/运行时/插件对话框与 web 资产）、以及为安全项特批的相邻面（见 5i）。
- **非插件 web 页面树（homepage/guide/model/login 等）与 orca/main 差 701 文件 = fork 自有资产线**，不属插件吸收范围；其中个别文件（如 model/model.js，与上游 parent 逐字节一致）仅因安全修复特批吸收，不构成整树跟进的先例。
- printer_agent 域（orca.printer_agent 138 条 API + selected_printer()）整体裁剪，待该域整体决策，不逐条零收。precise seam 特性线吸收时**必须连带 9 条插件绑定**（ModelVolume.is_precise_seam{,_strong,_weak} + ModelVolumeType.PreciseSeam* 枚举 ×6），否则模型 API 面破缺。
- cloud 域为桩（CloudPluginService 存根、无 OrcaCloudServiceAgent）。
- 快捷键簇（#15706/#15862、0f59cd5d05）：Shortcuts.hpp 基座从未导入，**永不吸收**，除非先决策引入基座。
- 上游 4 个未合回 main 的插件分支（headless-plugin-probe、preset-plugin-apis、isolate-plugin-browser-session、plugin-network-permissions）：合入 main 后再评估。

## 批次史（含门禁勘误）

| 批次 | 提交 | 门禁 | 备注 |
|---|---|---|---|
| 本体+0..4 | 951e0d6a42..187eed00b5 | 42→51/51 | 见 10-21/10-22 早晨报告 |
| 5a lifecycle | 5899177f18 | ctest 记录见提交信息 | ctx.name 语义漂移由 ad6a00fdc2 补齐（审查 F1） |
| 5b pages | d8b34e449e | **"51/51" 记录失效**（见下 F3） | |
| 5c dock panel | fcf96e28c8 | 8/9 逐字节一致 | 5b 的 ActionRegistry 假绿由此自证 |
| 5d ResourceTexture | 944309269a | 53/53 | **计数勘误（F6）：新增用例 19 非 16；71 实为 70 added（+17 modified）** |
| 5f preset.bundles | efa7d397db | 57/57 | 与 5e 同窗提交，5f(17:37) 先于 5e(17:59)，HEAD 名序有噪 |
| 5e facts(4条) | ac6c089cf5 | 58/58 | selected_printer 裁剪（printer_agent 域） |
| 5g pycache | ecbeb8742b | 58/58 | |
| 5h thread shim | eac1ba7bf0 | 58/58 | #16682 |
| 5i 安全双项 | 44c8ef06f5 | 62/62 | e68694dbaf + 203bc63f35 |
| 5a-followup | ad6a00fdc2 | 59/59 | F1 十站 ctx + err_msg |
| 5j 残簇六片 | （本批） | （本批） | 见下 |
| 5k status 考卷补收 | （本批） | 60/60（slic3rutils_tests clean rebuild 后） | test_plugin_status.cpp = a5413efc37 的考卷（代码片 5j 已吸收、考卷漏带）；NativeCommands TRIM 注释澄清（install 链路勘误，见"验证与勘误"；注释级改动走 DLL 目标增量重编验证） |
| 5l i18n 包裹层 | （本批） | 60/60（触碰 TU 定向 clean + DLL 重编 + 二进制字符串验证后） | e821665e4b 决策落地=ABSORBED：8 文件消息包裹（Manager/Loader/FsUtils/Resolver/Hooks/Bridge/Config）+ registration_failed 出参对齐上游形态（取代前缀匹配等价物）；顺带上游同提交的两处措辞更新（No update available / Use Delete to remove the local files）。残留 ±1 对 = 云桩域结构性差异（上游 unsubscribe 双站点，port 单站点），不可达路径 |

## 失效记录与流程防线（审查 F2/F3）

- **F2 — a6dbf2502d 声称失实**：d8b34e449e 的 "Fixes:" 列名 a6dbf2502d，但其主体（PrinterWebView/WebViewDialog/Project/Widgets/WebView 的 webview 重建逻辑）在分支上不存在。决策：**DEFERRED**——language-switch 后设备页空白属 fork 设备 webview 线，待该线需要时单独吸收；5b 实际携带的仅其 PluginPages/LazyPage 部分（已声明）。"Fixes:" 列名作废，以本条为准。
- **F3 — 5b 门禁记录为假**：该树状态 ActionRegistry.cpp:184 调用的 `select_page` 直至 5c 才存在，"build OK; ctest 51/51" 不可能为真（5c 提交信息自证 stale-object 假绿）。历史已发布不可改写，处置：本条即为失效记录；**流程防线：此后每批门禁必须对本批触碰的目标做 clean rebuild（rebuild 触碰的 .vcxproj，而非仅增量链接），假绿根因是陈旧增量目标**。

## 上游尾簇逐项决策（审查 F4，10-22 晚重算后状态）

| 上游提交 | 决策 | 落点/理由 |
|---|---|---|
| e68694dbaf file-URL 百分号编码 | **ABSORBED 5i** | helper + fork 在场 call sites；跳过：MultiNozzleSync（缺）、missing_connection（fork 走 localhost 页服务）、ReleaseNote/WipeTower/ElegooLink（站点不存在）、WebViewDialog homepage（fork 走 gateway URL） |
| 203bc63f35 model.js 转义+附件守卫 | **ABSORBED 5i** | model.js 与上游 parent 逐字节一致；is_absolute_path_within_root 以 weakly_canonical 自含实现（fork 的 is_path_within_root 在插件 fs 侧） |
| 6626377abc 权限重问 | 源码已入（batch-3）；测试块 **DEFERRED（残差勘误 10-25：fork test_plugin_audit.cpp 与锚点仅差 ~48 行——主体已随后续文件级吸收进树，残留为 printerAgent/cloud includes、4441bcc065 生命周期注释与 conf 字面量，均属已 DEFERRED 簇；原"+770 行"为提交时点描述，非当前残差）** | 下批吸收建议：record_root_frame 测试面，需独立周期 |
| 4441bcc065 用例间 Python 生命周期 | **DEFERRED** | 测试基建，随 6626377abc 测试块同批 |
| c023632a7d 配置/预设跨实例锁+原子写 | **DEFERRED 整提交** | 引擎域（InstanceLock/AppConfig/Preset）；PluginConfig 片段依赖 write_file_atomically（不在 fork），port 的 PID-rename 仍防崩溃截断 |
| a62fb17e03 移除 cloud 删除自有插件 | **DEFERRED** | 移除体骑在 cloud 桩域（OrcaCloudServiceAgent 缺席、CloudPluginService 冲突）；port 的 delete_mine_plugin 为指向桩的死接线，待 cloud 域清理批一并处理 |
| cefdd9b609 Windows 长路径 extended_path | **DEFERRED（absorb-later）** | 含 PluginFsUtils 片（插件面）+ Utils/miniz 共享件；单独成批 |
| 18b70844d1 PlaterShownWaiter | **ABSORBED 5j** | 含 fork include 块适配 |
| d715bb760c 插件窗口 X11 最大化 | **ABSORBED 5j** | 早晨报告的 BLOCK（WebDialog 缺基座）已由 5c 解除，记录更新 |
| 4149401c53 纹理选择器 lazy-PNG | **ABSORBED 5j（PNGReadWrite+TextureLibrary 片）** | gizmo 片不适用（纹理 gizmo 域已裁）；is_supported_height_map 改 header-only 判定 |
| c57b74731e SpeedDial dial-detail | **ABSORBED 5j（1 行残片）** | 其余资产已一致 |
| a5413efc37 printer-agent 基建重构 | agent 主体维持裁剪；**RuntimeError 状态片 ABSORBED 5j**（PluginStatus.hpp + PluginsDialog.cpp + index.js + styles.css，agent 无关；其考卷 test_plugin_status.cpp 于 5k 补收）；其余 DEFERRED 随 agent 域 | |
| 74aed7a2bb 测试临时目录清理 | **SKIP（卫生项）** | 价值低，不占门禁周期 |
| 0585836550 / 2df07b7ed8 / e01ac1f0a6 | **SKIP（cloud 桩域）** | 显式跳过记录：cloud 元数据/TLS verify/orphaned 状态 |
| 26f5fd6251 WebView 取色器 | **SKIP（非 plugin 树本体）** | 仅 resources/web/theme.css 交叠；fork web 资产为自有线 |
| 卫生簇（1a5f91d727 等 ~10：include 清扫/jquery 去重） | **SKIP** | 非 plugin 树本体；fork 自带 ~10 份 jquery 副本属自有资产线 |
| 快捷键簇 | **永不吸收**（见范围声明） | |

## 已确认具备（复核项，无需动作）

b728e79f26（扩参）、37dcc65752（stdlib 免弹读，test_plugin_audit.cpp 同名用例过）、e7d6cc32a7（sidecar 拒改）、1abb2a0fd9（flatpak 路径，内容级 diff 仅云常量 TRIM 差异）、6626377abc 源码面（record_root_frame 在树）。

## 验证与勘误（10-22 深夜对账轮）

- **验证仪器（可复用）**：`sandboxes/api_surface_dump_plugin.py`（双 App 内省 dump）+ `sandboxes/diff_api_surface.py --expect`（期望快照机检，差异≡台账期望集 → `VERDICT: PERFECT`，未归类差异 → DEVIATION rc=1）+ `sandboxes/api_behavior_probe_plugin.py`（行为指纹：ExecutionResult 工厂/config 往返/storage 契约/PluginContext/枚举语义，弹窗安全、可重入）。当前基线：surface 148/1/1（快照与 dump 存 `SnapmakerOrca-mcp/sync-scratch/api_surface/`，port@588170bd81 sha `5fa0ea81…`）、双端行为指纹一致（`68f1682033af…`）。安装法见插件文件头；松散 .py 不被扫描，须目录式+enabled sidecar。
- **勘误（install 链路）**：曾据 NativeCommands TRIM 注释误判"本地安装按钮死线"。实况：`PluginsDialog::handle_web_command` 自带 webview 命令分发，`refresh_plugins`/`install_local_plugin` → `refresh_plugins()`/`install_plugin_from_file()`（inspect→覆盖确认→安装，全链在树，静态验证）；后端 `PluginManager::inspect_local_plugin_package`/`install_plugin` 均在。唯一无 fork 等价物的入口是 `install_plugin`（云 plugin hub），属云桩域。TRIM 注释已改写防再误读。
- **test-sync 归因（决策：不做机械同步批）**：共有 test_plugin_* 文件 vs orca/main@e5bb802378 的断言级漂移已逐条归因——printer-agent 域用例（裁剪）、6626377abc 权限票测试块、cefdd9b609 长路径/zip 逃逸用例、4441bcc065 用例间生命周期（均已 DEFERRED）、secret_constants 重构与 conf 文件名字面量（纯命名漂移）；其余为 include/格式漂移，无考题集合变化。机械同步=吸收已 DEFERRED 块，与既定决策冲突，故记录归因而非同步。

## 验证与勘误 II（10-23 全量代码审查，docs/reviews/port-python-plugins-full-review-2026-10-23.md）

- 审查 VERDICT: REQUEST CHANGES（窄面）→ 唯一 (C) 项 F1′（e821665e4b 未入台账）已由 **5l 落地**（ABSORBED，见批次表）。F2′-1 max-pages dropdown 补记于此：PluginPages.cpp 不携带上游 54fe28ab08（08-11）的 visible-page-count/下拉特性，代码内 ADAPTED 注释即声明，fork 无对应 Preferences 设置页，维持不携带。F2′-2（registration_failed 字符串契约）随 5l 出参化自然消除。
- 审查其余 PASS 项：文件级 53/56 全映照（缺 3=printerAgent 裁剪）、内容差异全归因、上轮 F1 修复与 orca/main 现状逐字一致（ctx.name=get_model_name）、GIL/生命周期/wx 抽检无 (N)。

## 已知环境事项（不属吸收面）

build-port 开发启动的 snapmaker-orca.exe 在插件加载后 ~15-40s 自发段错误（crashpad dump 时间链自 10-22 15:36 起，早于当日全部吸收批），与后置 pwsh 部署步骤失败（运行时缺件）症状吻合；dump/ctest 门禁不受影响；装包构建复验弹窗行为时一并排查。

**勘误（10-23 实测归因，a0dc6f6c31）**：上述段错误的真凶不是部署缺件，而是 batch-4（187eed00b5）Tab.cpp 嫁接带入的悬空 option 引用（gcode_skip_config_block / use_3mf / enable_power_loss_recovery / 三个 plugin_config_overrides 无 def，`ConfigOptionsGroup::get_option` 空指针解引用，选中 Snapmaker 机型即必崩；时间线与"16:59 起全部启动猝死"吻合）。def 链已由 a0dc6f6c31 补齐，GUI 启动恢复。"15-40s 崩溃"原始观察（10-22 午后健康窗内）与本崩溃为不同时相，pwsh 部署缺件仍是独立待修环境项。

## 实机插件适配验证（10-23，用户本地 6 插件 + stratum）

- **对象**：从用户 OrcaSlicer（SoftFever 发行版）侧迁入的 5 个 cloud-origin 插件（ModelFinder 1.0.5 / FilamentHub 0.2.5 / Vase Maker 0.8.15 / Support Fins 0.2.0 / Open Bamboo Networking 0.2.41）+ 本地 whl SnapBins 0.2.0 + fork 自研 stratum，全部装于 `{data_dir}/orca_plugins/` 本地目录。
- **结果**：全部被宿主发现并加载执行（fresh pyc import 证据 ×7、audit 归因执行证据 snapbins/5d35283e、pages 页签注册证据见 12:24 会话截屏）；权限沙箱按设计工作（snapbins socket / 5d35283e fs-read 被 AUDIT BLOCKED，弹窗授权链路在主屏正常弹出）。
- **决策（4313d584d8）**：插件发现收敛为**纯本地目录**。裁掉 GUI_App 启动时 preset_folder→set_cloud_user 的种子（云域裁剪的遗留缝：扫描目录集随登录时序漂移，_subscribed 时扫时不扫、双副本期出重复键）。云向对话框命令保持既有桩守卫（can_fetch_cloud_plugins 短路），不另动插件树代码。
- **记录**：plugins UI“点不了/关不掉”三因——conf 持久化的坏窗口几何（window_mainframe 副屏负坐标，已修 conf）、模态权限弹窗在屏外禁用对话框（ShowModal 机理）、a6dbf2502d webview 重建逻辑 DEFERRED 导致僵尸 webview 不可恢复（本案例可作为该批次吸收依据）。

## 裁剪域收口批（10-23，"完美移植"清理）

四域全符号扫描结论 + 处置（快捷键域已由 NativeCommands.cpp 的 TRIM 注释 + fork 自有 keyboard_shortcuts 实现自洽，无需动作）：

- **cloud 域缝**（5 处死线全清）：
  1. 云源插件（sidecar installed_from=cloud）在对话框只给 Unsubscribe/Delete-mine/Reinstall——全部走桩必失败，且无本地 Delete/Reload。→ `evaluate_action_policy`/`derive_plugin_source` 以新增的 `PluginManager::cloud_plugin_service_available()`（恒 false）门控，云源降级为本地动作集与 Local 徽标。
  2. 登出链 `unload_cloud_plugins()` 按 sidecar 云源标记卸载插件——Snapmaker Connect 登出会误卸本地安装的云源插件。→ 登出路径移除三行（unload/clear_metadata/set_cloud_user）。
  3. Snapmaker 账号登录/`enable_user_preset_folder` 重新喂 `set_cloud_user(uid)` → `_subscribed/<uid>/` 再被扫描（含空目录副作用）。→ GUI_App 全部 5 处 set_cloud_user 移除；preset_folder 语义（预设域）不受影响。
  4. 安装按钮 "Explore/插件中枢" 指向 cloud.orcaslicer.com。→ web 页钉死 install-local（隐藏下拉、默认值本地化，host 侧默认值同步）。
  5. PluginResolver printer_agent 反查块（def 永不存在 → 不可达死代码）。→ 删除 + TRIM 注释。
- **上游既有设计（保留不动）**：~~targetless 审计事件的 Yes 授权仅会话内有效不落盘~~ **勘误（同日）**：非上游设计，系移植缺口——orca/main 的 write/read_install_state 均带 `permissions.events` 桶（write:856/read:811），port 两行丢失 → targetless 授权（如 snapbins 的 `Socket:socket.__new__`）每次会话重弹 nullptr 父模态框（位置不受控、可藏于任意窗口后、模态期间全应用输入锁定，且会在 PluginsDialog 构造链中途弹出卡住 Show()）——用户侧即"Install local plugin 按了没反应"。两行已按上游原文回填（见修复批）；实测授权落盘 `events: ["Socket:socket.__new__"]`，重启不再弹。有 target 的事件授权原本就持久化（Bamboo fs_read 双路径落盘实测）。
- 验证：13:42 构建，7 插件本地加载执行如常（audit 证据×2）、无重复键/无 _subscribed 扫描、权限弹窗主屏可见可点（BM_CLICK 实测 Yes 生效、会话内放行）。
- **勘误追加（5689b2c8ac）**：PluginsDialog/index.html 的 fuzzy-search.js 引用在吸收批抄成 `../js/`（上游 `../../js/`），页面每次加载 404 且搜索匹配器缺失——已按上游原文修复；全 web 资产 158 个相对引用复检全部可解析。

## 插件生命周期实机验收（10-23 深夜，锁屏盲操链路）

- **环境**：控制台被锁（LockApp/CoreWindow 盖屏吞输入、窗口不上屏、副屏黑），合成输入不可用；改用 PrintWindow（窗口像素）+CDP（对话框 DOM/命令）+WM_COMMAND/BM_CLICK（原生确认框）盲操链。对话框打开靠临时未提交钩子（env `ORCA_AUTO_OPEN_PLUGINS_DIALOG`，验收后已删）；"open_plugins" 原生命令在锁屏下无 UI 入口（NativeCommands.cpp:605 只有 SpeedDial/菜单两条触发路，均需输入）。
- **验收结论**（Vase Maker=Pages 能力插件，全链实证）：插件级禁用→tab/webview 摘除 ✓（e1580a3331 卸载半边工作正常）；重启用→tab/webview **未回归**（缺口，见下）；卸载（plugin_menu_action web 命令 + Delete 确认框 SendMessage BM_CLICK）→行/目录/tab 全清 ✓；退出重启→零残留（6 行、无目录、无孤儿 webview）✓；目录恢复+refresh_plugins→热发现，启用后 tab/webview 回归 ✓。
- **缺口与修复（load 半边断线）**：`PluginPages::on_plugin_register` 在树内**零调用方**——load_plugin 只发插件级事件（PluginManager.cpp:820/829/852/880），能力级 load 回调仅 set_capability_enabled(:1119) 与 rekey(:1910) 两处发出；启动 tab 靠 PluginPages 初始化枚举、会话中装载无人注册。已在 GUI_App load 订阅补 `plugin_pages().on_plugin_register(plugin_key)`（镜像 e1580a3331 的卸载侧；ResourceTextures 的同名接线本就在场）。修复后重启用/恢复启用两路径均实证 tab+webview 回归。
- **附带发现**：wxMessageBox（含 SysLink 的任务对话框形态）对 PostMessage(BM_CLICK/WM_COMMAND IDYES) 不生效，SendMessage(BM_CLICK) 同步派发生效；确认框枚举须按标题过滤（PluginsDialog 本体也是 #32770）。
- **环境残留**：显示合成损坏为机器级（非本仓问题，重启/重登录恢复）；锁屏期间杀了 explorer 一次（已自动重启）、LockApp 一次（系统自愈）。

## 三方复查轮（10-24/25，独立审查 + 修复批）

独立复查结论：①映照 PASS（API surface dump @e2cbf01ee0 与 5j 基线 sha256 逐字节一致，diff --expect VERDICT: PERFECT 148/1/1）②功能等价 REQUEST CHANGES→已修（见下 Pages 竞态）③发行就绪 REQUEST CHANGES→两项已修（installer.nsi、COPY_DLLS）。8 个被审提交（4bab3d8205..e2cbf01ee0）逐个复核全过：CGAL 配方/Eigen/守卫/CutSurface 干净前缀重编 ✓、89f8592074 断言与上游逐字一致 ✓、macho 负例含旧代码反证全绿 ✓、run_on_load_callbacks 双端一致 CallAfter 编组（无线程安全问题，此前"对话框刷新 vs 裸调"对照系假疑点）✓。测试面：slic3rutils 280=265/8skip/1mayfail/6 存量（与基线逐条对号，#3 Http basic authentication 系 [!mayfail] 标签用例非失败）；libslic3r 320 由 1 失败修至全绿（SSWCP，见下）。

- **557feba649（preset plugin APIs，PR #16518）决策：DEFERRED——独立吸收批评估**。范围声明预设的"preset-plugin-apis 合入 main 后再评估"触发条件已成立。体量 16 文件 +2668 行：新文件 PyPluginTrampoline.hpp、PluginHostPresets.cpp +686、PluginManager +439/101（含 ScriptAsyncRuntime 与 cancel_and_wait_for_capabilities 无限期排水语义重写）、GUI 侧 ActionRegistry/OptionsGroup/PluginsDialog/Tab 接线、考卷 test_plugin_host_api.cpp +158。与 fork 的 cancel/GIL/wx 语义耦合深，须按 5i 级别独立周期吸收，不并入本修复批。
- **Pages boot 竞态（10-23 验收"恢复回归 ✓"的证伪与修复）**：卸载→恢复→启用后 tab 永不回归，跨重启确定性复现（is_loaded=true/能力 enabled/无错误，目录与 config 字节级还原）。根因（插桩定界）：插件加载若在 MainFrame 构造窗口内完成，PluginPages::initialize 枚举已过、load 回调（CallAfter）在构造中途被泵到时 `wxGetApp().mainframe` 尚为 null 被静默跳过，无人兜底。上游同构窗口（on_cap_register 对 null parent 静默 return，initialize 只枚举当时已活能力）。修复=boot 与 recreate_GUI 两个 mainframe 赋值点后幂等重放注册（GUI_App::replay_plugin_pages_registration）+ on_cap_register 静默失败路径（能力不可得/InsertPage 拒绝）补 error 日志。六段链（禁用/重启用/卸载/重启零残留/恢复+启用回归/再重启持久）复验全绿。
- **installer.nsi 发行阻塞修复**：原 `/x "*.py"` 会把捆绑 CPython 的 stdlib（python/ 树 589 个 .py，仅 21 个 .pyc）从安装包剥离→安装版内嵌解释器丢标准库、插件系统死。来源为 fork 打包提交 ff54f00419（吸收前无捆绑 Python 时无害；上游无 installer.nsi 可比）。修复=python/ 子树显式 File（含 .py，排除 include/libs 开发件）。**验证缺口：本机无 makensis，未做 NSIS 编译验证；补全路径=sign_and_package.sh 出包 + 装机插件加载冒烟**。
- **COPY_DLLS 修复**：原 28 个硬编码 OCCT DLL（缺 TKDE×8 与 TKBin*/TKStd*/TKXml* 等共 24 个，Release 目录此前靠手工拷贝凑齐）改为 `bin/occt/*.dll` 整目录 GLOB 拷贝 + 前缀缺失 FATAL；根目录 python312.dll 改为 POST_BUILD copy_if_different（原只拷进 python/ 子目录，exe 导入表按根目录解析；手工拷贝件曾于 10-23 21:50 打补）。删除法验证：删根目录 python312.dll 重构即复现。
- **SSWCP flows 修复（fork 域存量，非插件面）**：test_sswcp_protocol.cpp:64 确定性失败——`select_complete_cached_nozzle_info` 在缓存 flow 不完整时 `flows.clear()` 抹掉直采值，违反头文件契约（"仅全部有效才替换"）。对照唯一调用方 Plater.cpp:9196 语义（不完整缓存不该清空 nozzle_volume_types）后删除 else-clear。libslic3r 320 用例由 316/1/3 修至 317/0/3 全绿。
- **能力矩阵勘误**：行 1 引用漂移（Print.cpp 实际触发点 2541-2812，步列表补 posDetectOverhangsForLift；契约注释在 SlicingPipelinePluginCapability.cpp:18-19）——12/13 总数判定不变；行 4/13 回填本轮修复与六段链复验。
- **fff_print 套件链接损坏（修复批内发现，d542603208）**：吸收把 test_slicing_pipeline_hook.cpp 加进 fff_print_tests 却漏了其夹具 test_helpers.cpp（hook 考卷调的 4 参 init_print 只在后者定义）→ 该套件自吸收起从未链接成功，且伞目标 `tests` 静默跳过它，门禁从未察觉（假绿的新形态：目标级缺失而非陈旧增量）。修复=源清单补 test_helpers.cpp（镜像上游）+ 删除其与 test_data.cpp 撞链接名的 4 个重复定义（mesh_names/mesh/model/gcode，保留 test_data 正典版）。**吸收后首次运行：49 用例 34 过 15 失败，无一归因插件移植**——14 个 bed-fit（fork Arrange.cpp 与上游差 ~230 行且自 fork 基点未被移植触碰，与 slic3rutils #246/#280 存量同族）+ 1 个 tree_support（fork 域）。34 个通过项含真实切片/gcode/模型用例=挂点编译且惰性下的切片管线绿灯。**流程教训：伞目标 tests 的成员完整性须显式核查（cmake --build --target <每个套件>），不能只信 umbrella exit 0。**
- **E2E 生命周期 harness 落地（249ad11ac0，tests/e2e/）**：单测覆盖不到软件周期（首启→装→用→重启→卸载→残留→恢复→CLI 切片），三轮人工盲操取证的技术（CDP/AttachThreadInput 前台提升/绝对坐标菜单点击/同步 BM_CLICK 确认框/UIA Int32 pid）已产品化为仓内可复跑 harness：隔离 --datadir（不碰用户数据）+ 提交在案的 Pages 探针插件 + 有界轮询断言。lifecycle 场景 9 段 21 断言（段 5/8/9 即 df6a5fdd40 竞态修复的回归面——修复前该 harness 必翻红）；slice 场景以自带 project_settings 的 pa_pattern.3mf 走全流程 CLI 切片，双跑规范化哈希（剥三类易变注释行：时钟头/随机对象 id）必须一致，golden（0aa3c58f…@350c133cdb 铸）提供 A/B 回归门禁——吸收 557feba649 或任何切片管线改动必须过此门。编排器全量实跑 E2E PASSED（~105s）。**发布清单须把 run_e2e.py 列为门禁项（需交互桌面，故不进默认 ctest）**。

## 10-25 收尾轮（发行实证 + 557feba649 吸收）

开工 fetch @orca/main 09aa0114b4。`src/slic3r/plugin/` 自 557feba649 后新增 3 组（9 个非 merge 提交），逐条决策：

| 上游提交 | 决策 | 落点/理由 |
|---|---|---|
| 6c791532c6 + 2410112046 + 6a0223f055 + 9739d3a9c4 + f3f872281e + f1011098ca + 1086b771b5（plugin-network-permissions 系列，已合入 main） | **DEFERRED——独立权限批** | 范围声明"合入后再评估"触发条款成立。plugin/ 内 +649/-89（PluginAuditManager 网络授权 API + fs 通配权限 + symlink 拒绝/相对路径归一，PluginFsUtils/PythonPluginBridge/PluginManager 连带）+ test_plugin_audit.cpp +446 行考卷 + probe 沙箱件。与 557 批共享 PluginManager.cpp 一个文件：557 批取 557 时点文本，权限批后续叠加，保持批间可分离。属插件系统自身设施（audit/权限），在范围内，但须独立周期（本轮已被 557 批 + 发行实证占满）。 |
| 9f85357ade 关机期 worker 线程 UI 调用 RuntimeError（#16763） | **ABSORB（本轮）** | 36 行。fork run_on_ui_blocking 与上游修复前形态逐字吻合（promise/future 无界 fut.get()），GUI_App::is_closing() 在树（GUI_App.hpp:345，吸收轮为插件代码加的）。修复 printer-agent disconnect 死锁——fork printer_agent 域虽裁剪，但"UI 线程关机期不再排水 CallAfter 队列"的一般性死锁面在 fork 同样存在。 |
| 258ddc15e8 i18n 复数占位符（PluginManager 1 行句点） | **ABSORB（并入 557 批文本）** | 目标行位于 ScriptAsyncRuntime::run_invocation——该函数由 557feba649 引入，fork 现无此函数（grep 证实）。557 批吸收时直接取 orca/main 现行文本（含句点），无需独立提交。 |

- **勘误（三方复查轮 117 行）**：PyPluginTrampoline.hpp 并非 557 新文件——lifecycle 批（5899177f18）已在树，557 为 +76 修改。"新文件"表述作废。
- **Tab.cpp/hpp 在 557 后另有 3 个无关上游提交触碰**（b1846e3408 涂色渗透层 / 30ceeee18d 3MF 警告 / 19eb55d3e5 silent_mode）：557 批只取 557 hunks，不整文件跟。

### B 发行实证（NSIS 出包 + 装机冒烟）

- **工具链**：winget 装 NSIS 需 UAC 被拒；改用便携版 nsis-3.13.zip（C:\coil\tools\nsis，未入仓）。
- **出包**：makensis installer.nsi（/DSOURCE_DIR=build-port\src\Release），V2.4.1 包 129MB。包清单以 /V4 日志为权威（12097 File 行：589 .py、57 TK*.dll、根+python 双 python312.dll）。**负例验证**：删 python/ 显式块的对照包 0 .py——检查仪器灵敏。
- **新发行阻塞（已修 a8c3cef380）**：47d410d7f2 的 python/ File 块带 `IfFileExists "${PACK_SOURCE_DIR}\python\python3*.dll"` **运行期**门（PACK_SOURCE_DIR 是编译期源路径，安装时按安装器 CWD 解析，装机必不成立）→ 静默装机实测仅 29 个 .pyc 落盘、589 个 .py 全缺——装机版内嵌解释器无标准库。编译期清单绿（File 正常打包）+ 运行期门拦截 = 假绿新形态：**只有真装机才能暴露**。修复=删门（缺 runtime 应在构建期 FATAL）。
- **装机验证（真实静默装机 Program Files\Snapmaker_Orca，宿主自动批准 UAC）**：589 .py ✓、57 OCCT ✓、Uninstall.exe ✓、ARP（WOW6432Node 视图，32 位 NSIS 常态，控制面板可见）✓、URL 协议（64 位视图）✓；**内嵌解释器 pycache 证据指向装机目录 stdlib**（collections/encodings/threading…）；装机形态 e2e lifecycle 9 腿全过 + slice golden 一致。
- **e2e harness 加固（ea7c87f6aa）**：连续运行中确定性复现的 "PluginsDialog did not become present" 归因为**僵尸 WebView2 占用 CDP 端口**（异常中止路径不清理，fork 已知僵尸 webview 问题的外显）；launch() 前按 `--remote-debugging-port=<本harness端口>` 参数过滤清扫，不误伤第三方 webview。
- 残留：安装器 UI 交互流（欢迎页/组件页/升级卸载链）未逐页走查（静默路径已覆盖文件+注册表写面）。

### C 批次 5m：557feba649 preset plugin APIs 吸收（8f7c9ca30e + 8f6da5ec5e）

16 文件按批落位（逐文件决策见 8f7c9ca30e 提交信息）。要点：
- **ADAPT 集（PluginHostPresets.cpp）**：combo 名称解析改标签匹配（fork 定制 ComboBox 无 per-item alias/flag 通道，widget 基座偏移 ~1000 行不属吸收面），内部名走 find_preset/get_preset_name_by_alias 回退；`auto_calc_flushing_volume→auto_calc_flushing_volumes` 改名。
- **TRIM 集**：AMS 徽标重真（GetFlag/FilamentAMSType/set_sync_badge 缺席）、on_filament_change()（上游空体）、is_mixed_filament 拒绝（fork 无混色虚拟槽）——全部带 in-code ADAPTED 注。
- **兼容修**：9f85357ade 的 Call::state 用字面 0 初始化（fork C++17 下 MSVC 局部类 NSDMI 不查外围函数局部枚举；上游 C++20 无此问题）。
- **门禁**：libslic3r_gui clean-first 重编 + app 链接 ✓；slic3rutils（ctest 逐用例）新 4 考卷全绿，5 败全归因（3 action_source 静态资产/模式断言 + 2 bed-fit arrange 存量族）；tests/e2e 全量过（lifecycle 9 腿 + slice golden 0aa3c58f 逐字节一致）；API surface dump 重跑 → 期望集更新为 expected_snapshot_557.json（29 项新增全为 orca.host.preset 面，PERFECT；port dump sha256 前缀 2c210a8e9d4a6591，存 mcp sync-scratch/api_surface/run_557_batch）。
- **附带修复（4c3815e8da）**：d542603208 拆重复定义时拆错方向，slic3rutils_tests 自 10-25 16:58 起**链接断裂**（伞目标静默跳过故无人察觉——假绿新形态：目标级链接失败）。方向反转后两套件同时恢复；fork 枚举子 cube_20x20x20 补入 test_helpers.hpp（两头文件互斥包含，无 TU 双含）。
- **门禁姿势勘误**：slic3rutils 的门禁=ctest 逐用例单进程（catch_discover_tests，test_plugin_audit.cpp:462 注释明示该域按每用例一进程设计）。ad-hoc 单进程全量跑会出现 56 例 "interpreter already running" 跳过 + audit 域序列崩溃——**非缺陷，是未按门禁姿势跑**。台账此前 "265/8" 基线的复现条件应以此为前提复核。

### D 从零 deps 构建实证（build-deps-fresh）

全配方 superbuild 从零（DL_CACHE 162MB 复用免下载）**最终 exit 0**。两处阻塞记录：
1. **环境项（不入库）**：OpenSSL Configure 拒 Git-Bash MSYS perl（IPC::Cmd 残缺）→ PATH 前置 C:\Strawberry\perl\bin 解决。首次点火的后台日志因管道 tail 只留尾行（传输变异教训：构建日志直落文件）。
2. **配方漂移（已修 8207907f12）**：deps/OpenSSL/OpenSSL.cmake 的 install_cmake_files 步 copy_directory `openssl`，该目录 fork 树内缺失（上游有 6 件包元数据）→ 从 orca/main 原文恢复。共享 mcp deps（OrcaSlicer_dep）当年如何过此步未考（不在本轮范围）。
- 产物清点：destdir/usr/local 完整（38 个 OCCT DLL、OpenSSLConfig 套件等）。**未做**：用 build-deps-fresh 产物完整配置构建 app（新前缀的 app 构建验证留给下轮，本轮只证 superbuild 配方健康）。

### E mac / F 收尾决策

- E：本机无 mac 硬件，未做（补全路径：有硬件后 build_release_macos.sh -a universal + scan_app_archs.sh --strict + Intel 侧启动冒烟）。
- F 未动（时间被 B/C/D 占满）：printerAgent 域整体决策、cloud 桩域收口、6626377abc 残差/a62fb17e03/cefdd9b609 三 DEFER 再评估、SnapLogClient flaky 移交，全部顺延。

### 平行分叉评估（10-26：womendoushihaoyin/OrcaSlicer feature_plugin_system）

用户指定对比分支已 fetch 为远端 `women`。**结论：平行独立移植，不建议合并，建议按"矿脉"选择性吸收**（与 orca/main 同等对待，非整支跟进）。

- **形态**：单提交 0aa325e101（2026-10-23，401 文件 +64623/-570），基线 Snapmaker main @1bff8daec7（#1069 dartCli）；与我方 merge-base = abd25fc161（#1061）。同源上游插件系统祖先（pluginTypes 四族/PythonPluginBridge/audit 俱在）但深度重构：plugin/ 树 vs orca/main 差 65 文件 ±5000 行，不对应任何上游单点。
- **上游新鲜度落后我方**：零 557feba649 代际标记（无 ScriptAsyncRuntime/PresetTransaction/launch_script_capability/invoke_script_execute），即无 preset 可变事务 API、无异步 Script 运行时、无 9f85357ade 关机防护；preset 侧为自研只读 PresetView 模型（is_user/label/config_keys/config_value/selected），与上游 557 的写侧事务设计分道。
- **架构差异**：核心拆 LocalPluginRuntime/RuntimeCore/Store/StoreCore（我方/上游单 PluginManager+Bridge）；能力子模块注册从 bridge 下放到各能力 .cpp；host/ 多出 HostCore/Mesh/Slicing/ConfigLocal/DockLocal(+Layout)/PagesLocal/AppInfoIdentity；audit 为简化 fs-root 允拒模型（上游权限授权系双方都未全带）；双方均无 printerAgent 能力件。
- **对方独有、具吸收价值的候选**（未定决策，待逐项评估后立批）：PluginDependencyInstaller（uv 事务装包，offline/wheelhouse 宿主策略，无 Python API）、PluginInstallTransaction/FileLock/AtomicFile/ArchiveCompat 安装基建、tests/plugin_core 55 文件（file_lock/dependency_crash/recovery/dock_layout/gui_dock_restart 等工程轴用例）+ plugin_contracts/plugin_benchmark、docs/plugins 32 篇契约文档、tools/plugin_sdk + scripts/verify_*。
- **试合冲突面**（tmp/merge-probe 已测并回滚）：62 冲突（34 add/add plugin/、19 GUI、libslic3r Print/Model/Format/TextureDisplacement 与 web dialog）——直接合入不可行，任何采纳都须按吸收批逐文件走。

### women 分支构建实证（10-26 续：feature_plugin_system 编译起活）

- **worktree**：C:\coil\Projects\SnapmakerOrca-women（detached @0aa325e101，本地补丁未提交，仅构建用）。
- **deps 代际判定（关键）**：该分支按 wx 3.1 / OCCT 7.6 代的配方代码写就——用共享 mcp deps（wx 3.3.2 + 新 OCCT）配置时 GUI 层 74 错（wxPostEvent 单参删除、wxTimerEvent 默认构造删除、wxString 转换收紧等 wx 3.3 破坏面）+ OCCT 传递包含缺失。**换 build-deps-fresh（本仓配方产物：wx 3.1 + OCCT 7.6 + CGAL 6.2.1）后全量构建 exit 0**。即：其树不带上游 wx 3.3/新 OCCT 兼容层（我方 release_2.4.1 吸收已带）——上节"平行分叉评估"补强：**代际隔离在依赖层即成立，合并可行性进一步降低**。
- **本地补丁（4 文件 5 处，均为 CGAL 6.2.1 适配，fresh CGAL 同版本故保留）**：CutSurface.cpp 读侧 property_map .first→.value()（10 处，去引用防 optional 悬垂）+ AABB_traits→AABB_traits_3；MeshBoolean.cpp extract_boundary_cycles 命名空间迁移；TextShape.cpp NCollection_Utf8Iter→NCollection_UtfIterator<char>（7.6 两名兼容）+ 补 OCCT 显式 include。
- **构建配置**：VS2022 x64，CMAKE_PREFIX_PATH=build-deps-fresh/destdir/usr/local，wxWidgets_ROOT_DIR/LIB_DIR 显式，**wxWidgets_USE_REL_AND_DBG=OFF 必须**（VS 多配置生成器下 FindwxWidgets 默认要求 debug+release 双套，deps 只有 release——该坑同时解释了为何 build-port 当年显式传 OFF）。
- **产物与冒烟**：exe+Snapmaker_Orca.dll+32 运行时 DLL 齐；启动冒烟过（homepage localhost 网关全链资源加载、字体、PartPlate、日志正常，隔离 datadir）。python/ 树其构建不拷贝，从 build-port 拷入后其 LocalPluginRuntime 仍未在无 UI 介入下激活（日志零 python 痕迹，喂 .install_state.json 约定一致的探针插件亦无发现活动）——**其插件运行时为惰性/需其 UI 触发或其元数据检查器拒收上游格式**，未深究，记残留。

### women 分支插件导入面调研 + 门控勘误（10-26 续二）

- **勘误（重要）**：上节"插件运行时惰性"归因错误——真因是 **ORCA_LOCAL_PLUGIN_SPIKE / ORCA_PYTHON_PLUGINS 两选项默认 OFF**（CMakeLists.txt:167-173），首出的安装包根本没编进插件系统（构建日志 0 处插件源）。带 `-DORCA_LOCAL_PLUGIN_SPIKE=ON -DORCA_PLUGIN_PYTHON_ROOT=<CPython 3.12.13 前缀>`（build-port Release/python 正合）重配重编后通过，**安装包已重打**（新包 118MB，589 .py + 42 .pyd 清单验证，exe 为含插件系统的新二进制）。
- **其导入入口（spike 模式）**：文件菜单 "Local Plugins — development"（MainFrame.cpp:2643，ORCA_LOCAL_PLUGIN_SPIKE 门控）→ 原生 wx 对话框 LocalPluginsDialog → **"Install Plugin" 按钮**弹 wxFileDialog（**.py / .whl**）→ 信任告警确认（"以你的账户权限访问文件与网络"）→ local_store().install() 落盘 `{datadir}/orca_plugins/`，装机形态即 `%APPDATA%\Snapmaker_Orca\orca_plugins\`。插件格式 = PEP 723 头（`# /// script` + `[tool.orcaslicer.plugin]` name/version，tests/plugin_core/fixtures.py 为范）。注意其对话框自述"**Permission audit is not enabled yet**"——审计沙箱在其 spike 里关闭。
- **其树新 bug（本地补丁绕过，未上游报）**：LocalPluginsDialog.cpp 的 `#include "Tab.hpp"` 等位于 `#ifdef ORCA_PYTHON_PLUGINS`（17-41 行）内，而文件尾部的 fixture 清理循环无条件解引用 Tab → **纯 spike 配置编译必炸 C2027**。本地补丁=把 Tab.hpp 提为无条件包含；另有 pid_t 宏冲突（wx/libslic3r 链污染 CPython pyconfig.h 的 `typedef int pid_t`）补 `#undef pid_t` 守卫。另其单提交里混入了合并残留垃圾文件 `src/slic3r/GUI/mrgtmp0`（卫生佐证）。
- **残留**：裸 .py 投入 orca_plugins 后其启动 9 秒静默中断（无日志错误行）——其 autoload 对裸文件的崩溃面或格式不收，未深究；其受支持路径=对话框 Install Plugin。

### women 安装包启动失败修复（10-26 续三：error=126）

- **现象**：用户装机后 app 打不开。装机树运行日志实证 `Snapmaker_Orca.dll was not loaded, error=126`。
- **根因**：开启 ORCA_LOCAL_PLUGIN_SPIKE 后，orca_local_plugin_runtime 静态链 CPython（python312.lib），**python312.dll 进入 Snapmaker_Orca.dll 导入表**（dumpbin /dependents 实证）；其 CMake 不向 exe 根目录拷 python312.dll，NSIS 包里两条 `python312.dll` 清单行都是 python\ 子树（主递归块+显式块重复打包）——安装根目录零 python312.dll，加载器解析失败，壳 exe 直接退出。我方发行线无此问题（1e10e863cf 的 COPY_DLLS 修复含根 python312.dll POST_BUILD 拷贝）——两移植线在发行工程化上的又一差距实证。
- **修复（bring-up 本地）**：Release 根补拷 python312.dll → 重打包 → 静默重装 → 装机版隔离 datadir 复跑：无 126、webview/日志全链正常、进程存活确认。正解（若此线要长期活）= 其 CMake COPY_DLLS 补根拷贝，未做（非我方树）。

## 10-26 我方线最新 HEAD 重打包（fa2adbd2c8）

- **动机**：在位安装包（10-25 23:38, 129MB）打于批次 5m/8f6da5ec5e 定稿重链（10-26 00:14 DLL）**之前**，二进制过期。
- **构建**：build-port 增量 ALL_BUILD（VS2022 x64 Release，共享 mcp deps）。libslic3r/libslic3r_gui 重编 + Snapmaker_Orca.dll 重链成功（14:49）。两处非阻塞失败：①POST_BUILD python 树铺设 `rm -rf` 被瞬时占用打断（无进程常驻锁，手工重放三步全过）；②`orca_stubgen` 链接 LNK2019×4（get_profile_version/set_privacy_policy/CBaseException::set_log_folder/sentryReportLog——吸收后 libslic3r_gui 新引用，stubgen 链接行缺 bury_point/common_func/BaseException 对象，**存量断点**，非本包载荷，独立修）；③pwsh 不在 PATH（encoding-check 工具 POST_BUILD，已知环境项）。
- **出包**：makensis 3.13（MSYS_NO_PATHCONV=1 防 /V4 被路径转换），SOURCE_DIR=build-port\src\Release，产物 `build-port/Snapmaker_Orca_Windows_Installer_V2.4.1.exe`（129,233,469 B，14:58）。旧包改名留存 `_stale-built1025-2338.exe`。
- **清单验证（/V4 日志 nsis_pack_20261026.log 为权威）**：File 行 12097（=基线）、.py 589、TK*.dll 57、pyd 42（python/ 双打包 21×2 已知形态）、根 python312.dll 实压缩 1.9MB + python/ 子树两行 0 字节引用、Snapmaker_Orca.dll 73,799,680 B（14:49 产物）、零 NSIS 警告。OCCT 57 件与 deps 源抽样逐字节一致。
- **残留**：装机冒烟未跑（用户机器在位装机实例运行中，装机动作待确认）；exe 壳 23:23 产物（源未变，MSBuild no-op）。

## 10-26 上游 main 合入 + 重打包（da212e688b → 626331f60a）

- **合入**：`git merge upstream/main`（@bac6fd5c1e：Connect CLI v1.8.5 + stapler CI + release_2.4.1→main 合并 + bugfixs_algo #1076）。净变更 18 文件 +427/−143（port 线已自带大部分 2.4.1 同源内容，git 静默合并）。6 文件 8 冲突块全解：lock json 取上游 v1.8.5；**SSWCPProtocol else-clear 弃上游**（上游 `else flows.clear()` 与上游自己的 test:63-64 断言矛盾——2.4.1 合并把该回归带回了上游，我方保留修复版，合并后 libslic3r 320/320 全绿自证）；AppConfig/GUI_App/SSWCP.cpp/.hpp 均取 HEAD（插件声明+成员、wxString 版 m_tab_map 全链一致——合并树 request_select_tab 唯一活签名为 wxString 版，TAB_ID_* 常量在位）；flutter_web/WebSocket 调试面两侧均已删净（冲突块为基线残影）。
- **附带修复两个存量断点**：①orca_stubgen 自吸收起链接必断（4 符号），镜像壳 exe 模式把 common_func/bury_point/BaseException/StackWalker/SentryWrapper 编入目标（ae7b6feba5）——**ALL_BUILD 吸收以来首次全绿**；②上游新考卷 test_wipe_tower.cpp 夹具缺 `G92 E0`，validate() 阶段即死（use_relative_e_distances 默认 true + Marlin 默认——上游 CI 测试工作流仅 workflow_dispatch 手动触发，考卷带病合入），夹具补齐后 3 考卷 2 绿（626331f60a）。
- **残留（上游缺陷实证）**：考卷 745"wall filament without a block"挂在 2.4.1 的 tool_change_new 优雅降级路径——空 ToolChangeResult 未初始化 start_pos/end_pos/elapsed_time（Vec2f 裸构造=垃圾值），下游 float_to_string_decimal_point 的 to_chars 缓冲溢出抛异常；上游 main 同款代码逐字一致，同挂。临时探针已删（诊断法：REQUIRE 字符串相等让 Catch2 打出真实校验消息 + 加 G92 E0 对照转绿，归因闭环）。修法初判=空结果构造处补零值初始化，待独立批。
- **门禁（用户指示停止后续测试）**：libslic3r 320/320 ✓；slic3rutils 279/284（5 败，接近 280 基线的 6 存量水位）；Tab.cpp option def 链（a0dc6f6c31 面）grep 在位、Plater:9196 喷嘴流调用完好。
- **出包**：`build-port/Snapmaker_Orca_Windows_Installer_V2.4.1.exe`（131,059,801 B，15:56）。清单（/V4 nsis_pack_merged_20261026.log）：File 12098（=基线+1，合并新内容）、.py 589、TK 57、pyd 42、根 python312.dll 实压缩、Snapmaker_Orca.dll 73,803,776 B（15:36 合并后产物）。前包留档 `_pre-upstream-merge-1458.exe`（未合上游版）与 `_stale-built1025-2338.exe`。

## 10-26 设备页/预打印页/登录异常根因：本地打包缺 connect-bundle staging（已修）

- **症状**：装机版首页登录态查询 `getUserLoginState code=-1` 三连败 + `data is not a map`，设备/预打印页显示不对，点登录无反应。**15:01（合并前包）与 16:19（合并后包）症状相同**；control 历史日志（10-15 官方版时代起）无任何成功登录记录。
- **根因**：CI 打包用 `scripts/packaging/stage_connect_bundle.py` 按 `.github/connect-bundle.lock.json` 下载 control 发布包，**除替换 `snapmaker_control_windows_x64.exe` 外还整目录替换 `resources/web/flutter_web`**（脚本 243 行 replace_directory）——即"main 配 control 1.8.5"的正确形态 = control 1.8.5 的 exe **加其自带 web**（main.dart.js，version.json 报 1.8.5/20261023182959）。本地打包从未跑此步：包里一直是 git 树 web 2.3.40 + 10-22 的旧 exe 1.7.6，双重协议错位。git 树里的 resources/web/flutter_web（2.3.40，含 askUserLogin 等登录方法族，宿主 SSWCP 分发器 74 个 sw_* 无登录族——fork 与上游 main 逐字同）只是 dev 基线，正式形态被 CI 覆盖。
- **修复**：预置 sha256 校验过的 1.8.5 zip 进脚本缓存（%LOCALAPPDATA%/OrcaSlicer/connect-bundle-cache），对 build-port/src/Release/resources 跑 staging（exe 10,493,480 B + web 整换 + 陈旧 CLI 清理），makensis 重出（130,654,082 B，17:05，File 12118），静默重装。
- **验证**：装机后 app/control 双侧报 1.8.5；新会话（17:07）**getUserLoginState 失败 0 次、data is not a map 0 次**（旧会话每轮必现）；gateway port_ready→health_ready→ws 全链正常；589 .py / 57 TK / 双 python312.dll / 合并版主 DLL 基线完好。设备页/预打印页/登录点击待用户实机确认。教训：**本地出包清单必须包含 connect staging 步**（后续出包流程备忘）。

## 10-26 深夜 women 大步伐吸收·第一步：安装与依赖基建整块（PluginDependencyInstaller + 事务四件套）

来源 women @0aa325e101（平行分叉，见"平行分叉评估"节矿脉清单）。开工 fetch：orca/main 09aa0114b4→555321215e、women feature_plugin_system 仍在 0aa325e101（无新提交）、upstream main 已 fetch；`src/slic3r/plugin/` 无新增上游提交，主线不阻塞。

### 吸收面（文件级）

新文件 7 件（src/slic3r/plugin/，原样搬运 + 点状适配）：
- **PluginDependencyInstaller**（.hpp/.cpp）——uv 事务装包：staging→previous→rename 发布、`.dependency-install.lock` + PluginFileLock 跨进程锁、已装包 dist-info 钉版 constraints（防降级）、UV_*/PYTHON*/PIP* 环境清洗（防注入，Windows 大小写不敏感归一）、offline/wheelhouse 宿主策略（`{plugins_dir}/.dependency-policy.json`，无 Python API）、120s 截止 + shutdown 感知、失败保全既有包。
- **PluginInstallTransaction**（.hpp/.cpp）——本地包替换持久事务：`.install-transactions/<key>/journal.json`（schema=1 + filename/plugin_key/config 快照 + pending/rollback/committed 三相），candidate/previous 目录摆位，启动恢复（recover_plugin_replacements）。
- **PluginFileLock.hpp**——LockFileEx/flock 跨进程排他锁（文件常存、锁归 OS、reparse point 拒收）。
- **PluginAtomicFile.hpp**——write_file_atomically（scratch 目录 + 单次 rename + MOVEFILE_WRITE_THROUGH）。
- **PluginArchiveCompat.hpp**——extended_path（\\?\ 前缀长路径）+ extract_zip_entry_to_file（miniz callback 写出）。
- 适配：PluginFileLock/AtomicFile 的 windows.h 前补 WIN32_LEAN_AND_MEAN + NOMINMAX 守卫（women 裸引；经 PluginManager.hpp 传导到全部插件 TU 后炸 BoundingBox.hpp 的 min/max 成员初始化列表——首测只在无 PCH 的 slic3rutils_tests 显形，in-code ADAPTED 注释）。

接缝（port 侧改造，我方语义为准）：
- **PluginLoader.cpp**：`install_packages` 朴素 uv 直装体（~108 行，无锁/无钉版/无 staging）整体替换为 `install_packages_transactionally` 委托；本地已存在目录的安装改走 `replace_local_plugin_package` 持久事务（云装仍走 backup 路径）；whl 依赖解压改 `ensure_wheel_extracted`。
- **PluginManager**：initialize() 增 `.runtime.lock` profile 锁 + `recover_plugin_replacements`（先于解释器与发现；m_config.load() 相应前移）；shutdown() 尾部再恢复 + 释放锁；load_plugin_impl 增 `can_activate_plugin_replacement` 预检；load worker 增 `settle_plugin_replacement`（新函数：装载成功→提交事务，失败→自动回滚旧包+旧配置并重扫）；install_plugin 加固（load-in-progress/能力引用计数/未决事务三检 + unload 前后保全 install state + 装失败 finish(false) 回滚）；delete_plugin 删前先回滚未决事务；`write_loaded_plugin_install_state` void→bool（women 语义，settle 依赖持久化结果）；新增 `is_shutting_down()` getter（DependencyInstaller 截止检查用）。
- **PluginConfig**：save() 的 PID-rename 写改 write_file_atomically；新增 `snapshot_plugin_config`/`restore_plugin_config`（按包过滤快照/恢复，适配我方无 commit_locked 结构：锁内改文档、锁外 save）。
- **PluginFsUtils**：extract_zip_to_directory 事务化重写（extract_zip_contents 私有化 + extended_path 全覆盖 + 已存条目冲突检查收紧 any-entry）；新增 wheel 缓存块（WHEEL_CACHE_RECORD 完成记录 + wheel_sha256 OpenSSL EVP + complete_wheel_cache 逐文件大小/symlink 校验 + extract_and_publish staging/backup/发布失败回滚 + ensure_wheel_extracted）；write_install_state 改原子写（尾部补换行）。
- **PythonInterpreter**：initialize() 最前 `recover_dependency_install`（CPython 起来前完成 shared packages 断发布恢复）；load_module_from_whl 解压改 ensure_wheel_extracted（**替换事务正确性关键**：whl 更新后旧解缓存必须按 sha256 失效，否则继续加载陈旧代码——原 `fs::exists` 跳过式缓存在替换后必错）。
- **src/slic3r/CMakeLists.txt**：plugin/ 增 5 组件源。

### 已知 women bug 处置（任务豁免逐项评估）
- mrgtmp0 合并残留垃圾文件：排除即修（未带入）。
- LocalPluginsDialog ifdef 编译炸 + pid_t 宏冲突：随"LocalPluginsDialog 不吸收"决策不入口（见下）；pid_t 守卫知识留档——wx/libslic3r include 链后引 CPython 头需 `#ifdef pid_t / #undef pid_t`。

### 不吸收项
- **LocalPluginsDialog.cpp/.hpp**（946+17 行）：深耦合 women 独有 LocalPluginRuntime/LocalPluginStore（local_store().install/scan/remove/execute 全家）、文件内嵌 fixture 测试代码、安装路径明示绕过审计（"Permission audit is not enabled yet"）——与我方 PluginsDialog（inspect→覆盖确认→install，audit 链完整）功能重复且违红线。其 dependency-policy 配置 UI 是 configure_dependency_install 唯一宿主入口：策略文件可手编（宿主自有面），需要 UI 时在我方 PluginsDialog 挂钩（残留项）。
- LocalPluginRuntime/Store/Core、OrcaPluginCore.cmake spike 门控体系：women 架构分叉本体。
- orca_http_shutdown_test、spike 编译期开关（ORCA_LOCAL_PLUGIN_SPIKE）：women spike 域。

### audit 红线合规
替换事务候选状态 `permissions = {}`（"新代码必须重新取得授权"）与我方 install_plugin 既有 `revoke_plugin_permissions` 同语义（双重清空幂等无害）；回滚恢复旧包原 sidecar（含其既有授权），旧代码保旧授权；DependencyInstaller 为宿主侧子进程（无 Python API 面），较原朴素版更严（钉版防降级 + env 清洗），安装同意边界（inspect→确认）不变；wheel 缓存为纯文件面加固；`.install-transactions`/`.runtime.lock`/`.dependency-*` 均 dot 前缀，is_ignored_plugin_directory 天然不扫。

### 门禁（全过）
- 触碰目标 clean rebuild：libslic3r_gui 删 obj 目录 + lib 后全量重编 374 TU、0 错（编译行实证，防增量假绿）；ALL_BUILD exit 0（Snapmaker_Orca.dll + orca.dll + 三测试套件 exe 全产出；pwsh 缺失 3 行噪声为已知环境项）。
- 过程坑：`cmake --build -- --clean-first` 会把 --clean-first 传给 MSBuild 打用法错误静默变增量（假绿新形态）；正确姿势=cmake 位放 `--clean-first` 或删 obj 目录。MSBuild 删 CMakeFiles/*.dir 后需先重跑 configure 再生 cmake_pch.cxx。
- libslic3r **320/320** 全绿。
- slic3rutils **279/284**，5 败与 10-25 基线集逐项吻合：#482/483/486（静态资产/模式断言族）+ #591/#625（bed-fit 族——#591 详查为 "Objects could not fit on the bed" 异常，其插件加载/配置分发/存储断言 5 项先全过，属 arrange 夹具存量非本批）。
- fff_print **37/52，15 败全部归因上游合并 da212e688b 后未门禁面**：失败 0.05s 即抛 arrange "Objects could not fit on the bed"（含 13 个切片管线 hook 考卷 + 2 个 init_print）；fff_print_tests 仅链 libslic3r+test_common **不链 libslic3r_gui**，本批全部改动不在其二进制内（链接分析排除）；失败集 vs 10-24 的漂移（tree_support 转绿、hook 夹具转红）与合并带入的 bugfixs_algo #1076 方向一致。**残留：上游 arrange 差异族需独立批对照 pre-merge 基线收口**。
- tests/e2e 全量：lifecycle 9 腿全绿（107s）+ slice 双跑确定性 + golden sha256 `0aa3c58f7c5a0614…` 与基线逐字节一致。
- API surface：本批零绑定注册触碰（新组件均 C++ 内部面，DependencyInstaller 明示 no Python API），surface 构造上不变，未重跑 dump（快照基线 expected_snapshot_557.json 继续有效；若后续批触碰绑定面须重跑）。

## 10-26 深夜 women 大步伐吸收·第二步：工程轴考卷 + SDK + 文档

### 吸收面
- **tests/plugin_core/**（新目录，5 个 C++ 场景 runner + fixtures.py）：
  - file_lock.cpp（跨进程锁：owner/竞争者双进程、kill 后 OS 释放、锁文件常存、symlink 拒收）
  - wheel_cache_recovery.cpp（真 Manager/Python 回归：entry/dependency × crc/unsafe/duplicate/conflict/legacy + case-alias 共 11 场景，全程真 wheel 真导入，断言完成记录/部分目录拒用/回滚保全）
  - dependency_environment.cpp + **dependency_environment_main.cpp（新写 driver）**——women 从其 55 场景 main harness 调用（harness 与 texture 场景耦合不可整搬），driver 保持契约体逐字 + 补 argv/隔离 data_dir 管道（women harness 原责）
  - dependency_recovery.cpp + dependency_crash_interpose.cpp（**APPLE-only**，dyld 真 rename 崩溃注入——women 原样非 APPLE 不编译，带入文件与门控保持一致）
  - fixtures.py（确定性 wheel/插件夹具工厂，无网络无系统 site-packages）
- **tests/plugin_core/CMakeLists.txt（新写）**：runner 目标 + `orca_plugin_core_runner_extras` 函数（私有 TU 解析复用 slic3rutils_tests/orca_stubgen 模式：common_func/bury_point/SentryWrapper/BaseException/StackWalker 直编）+ python/uv 铺设 + ctest 三项（python 编排器驱动）+ APPLE 门控 dependency 组 + orca_plugin_sdk_export。
- **scripts/**（8 件）：test_plugin_file_lock.py / test_plugin_wheel_cache_recovery.py / test_plugin_dependency_recovery.py（macOS 侧）/ test_plugin_dependency_environment.py（**新写**：wheelhouse 夹具构建 + 隔离 profile 驱动）/ verify_plugin_sdk.py / generate_plugin_sdk.py / export_plugin_sdk.py / package_plugin_runtime.py（UPSTREAM 常量改我方 HEAD，ADAPTED 注）/ package_plugin_wheelhouse.py（离线 wheelhouse 打包，配 DependencyInstaller offline 策略）。
- **tools/plugin_sdk/main.cpp**：生产绑定活体导出器（无 wxApp/无插件/无真 profile）。
- **docs/plugins/**：LOCAL_RECOVERY.md（替换事务协议文档，与第一步实现逐条对应）、WHEEL_CACHE_RECOVERY.md、examples/（SDK 示例件 8 文件）。

### 接线踩坑（防再犯，均已修）
1. `cmake --build -- --clean-first` 把 --clean-first 传给 MSBuild 打用法错误后**静默变增量**（第一步已记）。
2. 独立 runner exe 首跑 0xC0000135：静态 libslic3r_gui 拖全 DLL 导入表，需 DLL 汤。
3. **Snapmaker_Orca_copy_dlls(COPY_DLLS ...) 首参是模式令牌非目标名**——函数实际永远落 `<调用目录>/<config>`（app/slic3rutils 全靠与 exe 默认位置重合的巧合工作）；钉死每目标 RUNTIME_OUTPUT_DIRECTORY 会打破巧合 → exe 与 DLL 分层。修法：保留共享 Release DLL 池（configure 期一次 copy_dlls）+ POST_BUILD 拷入各 runner 钉死目录。
4. VS 多配置生成器在 plain RUNTIME_OUTPUT_DIRECTORY 下仍追加 `\Release`，须同时钉五个 `_<CONFIG>` 变体。
5. 两 runner 并行 POST_BUILD 向同一目录铺 python 确定性互撞（-m 并行）——每目标独立目录根治。
6. wheel_cache 编排器 `output.mkdir(exist_ok=False)` 对 ctest 重跑不幂等——加 rmtree 前置（测试 harness 适配，非产品码迁就）。

### 不吸收项（逐项归因）
- **55 场景 main harness 及 texture_* 16 件/gcode/slicing/path3 等场景件**：texture 管线（TextureDisplacementConsumer 等）为 women 独有 libslic3r 面；其余场景域我方 slic3rutils 既有考卷已覆盖（lifecycle/audit/host-api/config 等），重复移植无增益。
- **dock_layout.cpp / gui_dock_restart.cpp（任务点名件）**：依赖 women 独有 `plugin/host/PluginDockLayout.hpp`（我方 host/ 无此文件）——引它=吸收 women dock 架构本体，超基建范围，随架构分叉整体决策（DEFERRED）。gui_dock_teardown/gui_pages_restart/gui_dualhost/gui_legacy_states 同族同因。
- **plugin_benchmark**：main.cpp include TextureDisplacementConsumer.hpp（women 独有）；bulk 件可移但单独成件价值有限——整块 DEFERRED（连带 PERFORMANCE.md 退回：其记录的是该 harness 方法论）。
- **plugin_contracts（dualhost 工具契约）**：women DUAL_HOST 特性域。
- docs/plugins 其余 19 篇（TEXTURE_COMPATIBILITY/DUAL_HOST/SPIKE_HISTORY/LOCAL_PHASE1/VERIFICATION/DISTRIBUTION 等）：women-only 域叙事或引用未吸收工具链。

### 门禁（全过）
- 触碰目标（3 runner + sdk_export）clean 全编 0 错；ALL_BUILD exit 0（新目标入列）。
- **plugin_core ctest 3/3**：file_lock ✓、wheel_cache_recovery ✓（26s 全场景）、dependency_environment ✓（真 uv 离线装包 + UV_*/PYTHON*/PIP* 保全 + 失败安装耐久）。
- **SDK 链冒烟**：generate_plugin_sdk.py → 活体导出 10 模块 → 内建 verify 过（输出 sync-scratch/sdk_smoke_step2）。
- 产品码零触碰（tests/scripts/tools/docs only），slic3rutils/libslic3r 门禁不受影响（未重跑；上轮基线仍有效）。

## 10-27 women 续收·批 A：装载等待域考卷 + 观察者语义硬化 + 契约文档

开工 fetch：orca/main 555321215e→13a40b47a2（`src/slic3r/plugin/` 无新增；e021ccb316 缺插件通知修复触 GUI_App/Plater/NotificationManager/PluginsDialog——我方树已有该通知面（refresh_missing_plugin_block），**记为后续吸收候选**，不并入本轮）；women feature_plugin_system 仍 @0aa325e101；upstream main 已 fetch。

### 吸收面
- **tests/plugin_core 三考卷**（women 同名件改编到我方键基 PluginManager API，逐轴映射见文件头注）：
  - runtime_wait.cpp（no-app/console 双模式：未装包拒绝、失败错误保全+槽位释放、观察者排队/内联派发、卸载重装、shutdown 作废排队观察者、解释器停机）
  - unload_overlap.cpp（7 场景：overlap/bulk_overlap/shutdown/bulk_shutdown/replacement/delete/shutdown_gil；弃 women 的 destructor/reentrant 两场景——前者依赖 LocalPluginRuntime，后者依赖我方无有的 config 变更订阅）
  - observer_queue.cpp（真实 wxAppConsole 队列上的观察者顺序；registry 接线由考卷自装镜像 GUI_App 生产接线）
- scripts/test_plugin_runtime_wait.py / test_plugin_unload_overlap.py / test_plugin_observer_queue.py（编排器，tempfile 原生路径防 MSYS 转换伪影）。
- docs/plugins 四篇：LOAD_HANG_RECOVERY.md（重写为我方可执行契约，women 本机取证链不带入）、GCODE_LOCAL.md / SLICING_LOCAL.md（裁 women UI/考卷/smoke 引用）、HOST_API_AUDIT.md（只保方法+我方结构性差异）。
- 接线：plugin_core/CMakeLists 复用 runner_extras（wx include 补两点式——setup.h 在 LIB_DIR/CONFIGURATION 下）。

### 考卷暴露并修复的产品缺口（PluginManager，全部先红后绿实证）
1. **排队观察者不被 shutdown 作废**：run_on_*_callbacks 的 work item 捕获 m_dispatch_epoch（shutdown 顶点自增），过期自弃——解释器终结后泵队列不再重建资源/触达新运行时（runtime_wait console 尾段/observer_queue 终段翻红驱动）。
2. **卸载交叠无防护**：unload 先移注册表后 teardown，同键重装可入、旧代 save 覆盖新代配置（overlap 场景 OBSERVED reload=1 实证）。修复：m_teardown_in_progress 集 + CV；load_plugin 同键拒绝（记错误）；install/delete 卸载期拒绝；shutdown 排水（bulk 卸载 erase 用平行 removed_keys——曾因 move 掏空 descriptor 留空键致 shutdown 死锁，考卷抓出后修）。
3. **持 GIL 调 shutdown 死锁**：排水等待持调用方 GIL，on_unload 无法推进（shutdown_gil 300s 超时实证）。修复：GilReleaserForShutdown（PyGILState_Check 条件 SaveThread/RestoreThread）。
4. **过期能力事件毁注册表**：worker disable 排队 + 主线程 re-enable 内联后，泵队列把已启用能力的注册表项删掉（observer_queue 第 4 段字面命中原断言）。修复：能力级观察者派发时校验当前 enable 状态，反向/缺席事件自弃。

### 语义差异裁定（考卷断言适配，非裁剪保护面）
- 我方 sidecar 写入 rides 排队观察者（women 同步提交）："commit-before-observer" 轴改为"pump 后提交"；装后即关的 enable 提交被 epoch 作废 → sidecar 停 false（产品可辩护：不承诺自启）。
- 我方单进程 FIFO 队列（women 按 runtime 代际作废）：unload/disable 计数断言按 FIFO 语义适配，entries 隔离/关机不重建等保护面保留。
- manager.shutdown() 不终结解释器（GUI_App 所有）：考卷显式补 PythonInterpreter::shutdown()。
- GIL-held wait 轴弃（无持有 GIL 等待 load 的可达产品路径）。

### 不吸收项
- **runtime_paths.cpp**：我方无 PluginRuntimePaths 参数化纯函数库；等价实现（find_bundled_python_home）为编译期平台分支+编译期兜底，"空返回/跨平台布局"断言不可达，且我方无 CWD 探测（program_location 基）——结构性差异，SKIP。
- **prepare/verify_local_plugin_gui_smoke.py + GUI_TESTING.md**：darwin-only 硬门（codesign/.app/cua-driver），模式族含 texture/dualhost women 域；隔离 App+安装/重启/禁用生命周期语义与我方 tests/e2e（CDP 链）重复，异常路径为 macOS 机特定取证——SKIP 整链。

## 10-27 women 续收·批 B：plugin_benchmark bulk 三件套

- tests/plugin_benchmark/bulk_main.cpp + bulk_package.py、scripts/benchmark_plugin_bulk.py 原样吸收；bulk_main 一处点状适配（Slic3r::Polygon 限定——我方头集合下 ClipperLib::Polygon 歧义，women 不触发）。
- scripts/test_plugin_bulk_tools.py：14 用例全过；一处适配（cmake 路径断言指向我方 tests/plugin_benchmark/CMakeLists.txt——women 在 cmake/OrcaPluginBenchmark.cmake 且该文件同时定义其未收 main.cpp 目标）。
- 新建 tests/plugin_benchmark/CMakeLists.txt：orca_plugin_bulk_benchmark EXCLUDE_FROM_ALL（同 women），接线为独立目录（add_subdirectory 进 tests/），自含 staging（镜像 runner_extras，注释指认原件）；ctest 只挂 bulk_tools 纯 Python 契约测试。
- **main.cpp 不收**（TextureDisplacementConsumer，既定）；**scripts/test_plugin_benchmark_tools.py 不收**（校验未吸收的 benchmark_plugin_host.py 驱动）。
- 原生 bulk 实跑需离线 numpy-2.2.6 wheelhouse（本机 uv/pip 缓存均无），不进 ctest（women 同样不挂）；按需实跑法见 benchmark_plugin_bulk.py --help。

## 10-27 women 续收·批 C：host/PluginDockLayout.hpp 翻案吸收

- 重新评估推翻"Local 家族整体 DEFER"中的该件：**94 行 header-only 纯函数库**（仅 <string>/<vector>），无 Plater/DockPanel 依赖——满足任务预设的吸收条件。
- 我方消费点实证：dock 面板名 plugin: 前缀（DockPanel.cpp plugin_pane_name）匹配其过滤锚；**保存侧真缺口**——项目重置路径 Plater.cpp SavePerspective 会抹掉尚未创建的插件面板记录（women 函数注释描述的同型坑）。接线：保存点经 plugin_preserve_uncreated_panes 合并未创建面板及其 dock 尺寸。读取侧我方已有等价 aui_pane_layout_entry（Plater.cpp:11533，转义处理略弱于 women 版——women 版处理 \| 反转义；考卷全打 women hpp 上，未动我方旧件）。
- tests/plugin_core/dock_layout.cpp 原样吸收（41 行，一次过）；接线为独立小二进制（同 file_lock 模式）+ 直接 ctest。
- gui_dock_restart/gui_dock_teardown 等维持不收（需 DockLocal + GUI spike 栈）。

## 10-27 上游批 D：plugin-network-permissions 权限批收口（7 提交）

系列=6c791532c6/2410112046/6a0223f055/9739d3a9c4/f3f872281e/f1011098ca/1086b771b5（非线性序：1086 在 241011 之前；终态取 orca/main@555321215e 文本）。我方 AuditManager 与上游系列前基线全面分叉（全文件级差异）→ **语义级移植**，非补丁。大前提（注册期全类别权限请求 API g_pending_permissions + request_permissions 弹窗链）我方树已具备，实际增量：

- **PluginAuditManager**：网络归一/匹配族（normalize_network_url/network_permission_matches 公共 static + host_from_authority/network_host_from_target/ipv6 括号剥离等私有件，逐字取终版）；fs 树授权（"<dir>/*" 尾通配，canonical 双侧比较拒 symlink 逃逸，".."/中缀 * 不展开）；悬空 symlink 末端 fail-closed（ends_in_dangling_symlink 进 is_inside_allowed_root）；has_permission→4 参（类别+by_event）；decide_audited_event 网络判据接入（targetless 事件由任意网络授权覆盖，canonical host 授权 host-wide、旧全 URL 授权保持精确——6a 紧固语义）；relative 通配请求经 absolute_tree_grant 归一入 sidecar；request_network_permissions 公共 API（归一后委托 request_permissions）；PermissionMessagePrompt 测试钩子（**钩子分支必须先于 wxTheApp 守卫**——顺序错时无 wxApp 测试全拒，考卷 626 翻红抓出）；Http/Socket 弹窗文案换同意范围说明版。
- **PythonPluginBridge**：request_permissions 增 network= kwarg（归一 scheme://host 记入 HTTP 桶，socket 事件同享）；docstring 补通配段。
- **PluginFsUtils**：seed_install_metadata 公共化（sidecar 元数据映射单一来源），PluginManager mark_plugin_install_state_disabled 改用之（Manager 侧仅此 8 行，与 557 批 hunks 天然分离——权限批不触 557 区域）。
- **考卷**：test_plugin_audit.cpp 新增 8 用例（wildcard×4/树 canonical/悬空链接/targetless 网络/网络归一单元）+ 既有用例期望更新 1 处（"A freshly approved operation"：connect 授权覆盖 targetless send，期望由 connect\nsend 改 connect——系列自带语义更新，首轮漏带翻红后按上游终版补齐）。
- **probe**：sandboxes/orca_network_permission_probe_plugin.py 收入（取 6c791532c6 版；上游后于 4afd257371 删除该手工探针——我方 sandboxes 语义留存，台账知会）。

### 残差再评估（任务点名四项）
- **cefdd9b609 长路径**：PluginFsUtils 片**已被 women 批覆盖**（同站点 extended_path 全用，diff 证实）；剩 miniz_extension/utils.hpp 公共化+三测试属引擎域（libslic3r），随上游合入线，维持 DEFERRED。
- **c023632a7d**：AppConfig/InstanceLock/Preset/PresetBundle/Config ~600 行引擎域重制，preset 引擎 fork 定制重，独立批，维持 DEFERRED（PluginConfig 原子写已由 women 批覆盖）。
- **6626377abc 测试面残差**：仍为 printerAgent/cloud include 与 conf 字面量簇（10-25 勘误维持），无新增可收。
- **4441bcc065 用例间 Python 生命周期**：我方 catch_discover_tests 逐用例单进程门禁姿势已结构性等价覆盖，记 ABSORBED-BY-EQUIVALENT。

### 门禁（A/B/C/D 合并收口，共享触碰面；各批考卷独立计数）
- 触碰目标 clean rebuild：libslic3r_gui 删 obj 目录全量重编 0 错；ALL_BUILD exit 0；13 个伞成员目标逐一显式构建全过（含 EXCLUDE_FROM_ALL 的 orca_plugin_bulk_benchmark；一处 Plater include 路径错与 bulk 的 Polygon 歧义当轮修）。
- **plugin_core ctest 7/7**：file_lock、dock_layout（新）、wheel_cache_recovery、dependency_environment、runtime_wait（新）、unload_overlap（新，7 场景）、observer_queue（新）。
- **plugin_benchmark:bulk_tools 1/1**（14 unittest 用例）。
- **libslic3r 320/320**。
- **slic3rutils 286/292**：6 败=482/483/486（静态资产族基线）+591/633（bed-fit 族基线）+462 SnapLogClient（**flaky**：3 连跑 1 绿，非本批触碰域）。
- **fff_print 36/52**：16 败全落 arrange bed-fit/tree 存量族（13 hook+2 init+tree_support 本轮翻转）；本批零 libslic3r 触碰、fff_print 二进制不含本批改动，归因存量漂移（10-26 步骤一已记"上游 arrange 差异族需独立批收口"）。
- **tests/e2e**：slice golden 逐字节一致（0aa3c58f7c5a0614…）✓；**lifecycle 阻塞于环境态**：PluginsDialog webview 不现，stash A/B 判定**基线二进制（无本批改动）同点同败**——本机 WebView2 NAV_ERR_OTHER INVALID_STATE（主页可导航、设备/对话框 webview 失败，手动裸启同症状），非本批回归。残留：机器态恢复（重登/重启或 WebView2 runtime 排查）后复跑 lifecycle 收口。
- **API surface**：dump 重跑（port sha256 前缀 d9081826f3686525，存 mcp sync-scratch/api_surface/run_perm_batch_1027）→ diff --expect expected_snapshot_557.json **VERDICT: PERFECT**（network= kwarg 落在既有 request_permissions 多桶签名 mismatch 条目内，0 未期望偏差；期望快照无需更新）。
