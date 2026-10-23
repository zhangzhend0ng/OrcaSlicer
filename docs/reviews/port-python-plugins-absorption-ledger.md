# port/python-plugins 吸收决策台账（living ledger）

上游对照：SoftFever/OrcaSlicer `orca/main`（审查基准 10-22 16:14 fetch @664f734e222e；收尾复查 10-22 晚 fetch @e5bb802378，`src/slic3r/plugin/` 自 59e96b71d0 后零新增。每次开工须重新 fetch 复查）。
本台账为吸收/裁剪/延后决策的**唯一权威记录**：任何"已吸收"声称必须能落到本表或提交信息之一；上游新提交先在此定决策再动代码。
历史输入：10-22 早晨吸收审计（mcp 工作区未跟踪稿）+ 10-22 晚 REQUEST CHANGES 审查（docs/reviews/port-python-plugins-2026-10-22.md，mcp 工作区）。

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
| 6626377abc 权限重问 | 源码已入（batch-3）；**测试块 +770 行 DEFERRED** | 下批吸收建议：record_root_frame 测试面，需独立周期 |
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
