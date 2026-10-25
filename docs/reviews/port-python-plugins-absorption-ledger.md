# port/python-plugins 吸收决策台账（living ledger）

上游对照：SoftFever/OrcaSlicer `orca/main`（审查基准 10-22 16:14 fetch @664f734e222e；收尾复查 10-22 晚 fetch @e5bb802378。**10-25 fetch 复查：`src/slic3r/plugin/` 新增 557feba649（preset plugin APIs，即范围声明中预设"合入后再评估"的 preset-plugin-apis 分支），决策见"三方复查轮"节**。每次开工须重新 fetch 复查）。
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
