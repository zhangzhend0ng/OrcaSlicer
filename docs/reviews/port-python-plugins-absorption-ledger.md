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
