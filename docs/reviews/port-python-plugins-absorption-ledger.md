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
| a5413efc37 printer-agent 基建重构 | agent 主体维持裁剪；**RuntimeError 状态片 ABSORBED 5j**（PluginStatus.hpp + PluginsDialog.cpp + index.js + styles.css，agent 无关）；其余 DEFERRED 随 agent 域 | |
| 74aed7a2bb 测试临时目录清理 | **SKIP（卫生项）** | 价值低，不占门禁周期 |
| 0585836550 / 2df07b7ed8 / e01ac1f0a6 | **SKIP（cloud 桩域）** | 显式跳过记录：cloud 元数据/TLS verify/orphaned 状态 |
| 26f5fd6251 WebView 取色器 | **SKIP（非 plugin 树本体）** | 仅 resources/web/theme.css 交叠；fork web 资产为自有线 |
| 卫生簇（1a5f91d727 等 ~10：include 清扫/jquery 去重） | **SKIP** | 非 plugin 树本体；fork 自带 ~10 份 jquery 副本属自有资产线 |
| 快捷键簇 | **永不吸收**（见范围声明） | |

## 已确认具备（复核项，无需动作）

b728e79f26（扩参）、37dcc65752（stdlib 免弹读，test_plugin_audit.cpp 同名用例过）、e7d6cc32a7（sidecar 拒改）、1abb2a0fd9（flatpak 路径，内容级 diff 仅云常量 TRIM 差异）、6626377abc 源码面（record_root_frame 在树）。

## 已知环境事项（不属吸收面）

build-port 开发启动的 snapmaker-orca.exe 在插件加载后 ~15-40s 自发段错误（crashpad dump 时间链自 10-22 15:36 起，早于当日全部吸收批），与后置 pwsh 部署步骤失败（运行时缺件）症状吻合；dump/ctest 门禁不受影响；装包构建复验弹窗行为时一并排查。
