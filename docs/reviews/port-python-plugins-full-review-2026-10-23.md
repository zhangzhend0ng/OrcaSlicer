# port/python-plugins 全量代码审查（完备性 + 忠实性）2026-10-23

**Verdict: REQUEST CHANGES（窄面）** —— 插件树文件级 53/56 全映照（缺 3 = 台账裁剪的 printerAgent 域），全部内容差异逐 hunk 归因后仅剩**一个未入台账的上游触碰簇（e821665e4b，10 文件）**；无 (N) 级问题；上轮 F1-F6 全部核销。补一行台账决策（或一个小 i18n 吸收批）后，"除台账裁剪域外完美移植"的主张即可成立。

- 审查对象：HEAD `cb99799a0a` vs orca/main @`e5bb802378`（src/slic3r/plugin/ 全树 + 生命周期触点 + 测试集）
- 方法：文件级矩阵 → 逐 hunk 归因（裁剪域 / 台账 DEFERRED / 代码内声明适配 / 未归因）→ 交叉专题（GIL、生命周期、wx）
- 上轮审查（2026-10-22，mcp 工作区）F1-F6 修复核验 + 5i/5j/5k 新批次的增量审查

## FAIL

### F1′ [C] e821665e4b（#16436，10-13，"orca-translations skill + PO tool"）触碰插件树 10 文件，台账零记录
- `git show e821665e4b --stat -- src/slic3r/plugin/`：CloudPluginService/PluginAuditManager/PluginConfig/PluginFsUtils/PluginHooks/PluginLoader(.hpp)/PluginManager/PluginResolver/PythonPluginBridge 共 161+/117-。该提交**在已装 alpha（3880f2c58e）祖先链内**。
- 移植端实际状态：其 `registration_failed` 出参管线有**语义等价物**（PluginLoader.cpp:287 写 `"Plugin registration failed: "` 前缀 → PluginManager.cpp:918 前缀匹配 → 同样的 `mark_plugin_install_state_disabled`），但其 **i18n 消息包裹层（GUI::format/_u8L + TRN 注释）未吸收也未立决策**——PluginManager/Loader/FsUtils/Resolver/Hooks/Bridge 的错误串保持裸英文。
- 违反台账自身规则（"上游新提交先在此定决策再动代码；任何吸收声称必须能落到本表或提交信息"）。
- 修法（二选一）：(a) 吸收 i18n 批（机械改写，fork 有同源 I18n 基座）；(b) 台账立 SKIP 决策（理由：fork 插件消息暂不本地化）并记录 registration_failed 等价物说明。

### F2′ [A→建议随 F1′ 一并] 代码内已声明但台账未记的适配
- PluginPages.cpp 的 max-pages dropdown 不携带（ADAPTED 注释在码，特性源头 54fe28ab08@08-11）——台账补一行。
- registration_failed 的字符串契约（Loader:287 ↔ Manager:918）为隐式跨文件耦合——建议双向注释各一句。

## PASS（折叠）

- **文件级完备性**：53/56 一一映照，0 端口私有文件；缺 3 = printerAgent{cpp,hpp,Trampoline}（台账裁剪域）。
- **全部内容差异归因**（除 F1′ 簇外）：云域（CloudPluginService 桩 293+/PluginManager 云存储/Resolver 云 URL，台账 ✓）、printerAgent（Bridge 注册行，台账 ✓）、precise seam 9 条（PluginHostModel 枚举+方法，台账特性线 ✓）、PluginConfig 原子写（c023632a7d DEFERRED ✓）、品牌适配全部代码内声明（Snapmaker_VERSION 映射、gl_info 无 core_profile（GLInfo 基座差异，注释在）、is_signed_in、Slicing 2D 折线（docstring 声明 fork 底座差异）、preset.bundles 用户目录语义（注释+六重校验）、python-home 解析（46fb512690@09-29 fork 适配，Windows 实证）、NotificationManager 命名空间限定差异（纯风格））、include 清扫簇（台账 SKIP ✓）。
- **上轮 F1 修复核验**：ctx.name 全站点 = `print->get_model_name()` 与 orca/main 现状**逐字一致**（上游在两轮 fetch 间从 model-id 演进为 get_model_name，5a-followup 追的是最新态）；err_msg 累加在位（GCode.cpp:2221）。
- **上轮 F2/F3/F5/F6**：台账均有处置记录（F2 决策 DEFERRED、F3 流程防线=clean rebuild、F5 台账已上分支 bd717d2027、F6 勘误入账）。
- **5k（本轮前次批）**：test_plugin_status.cpp 与上游逐字节一致，clean rebuild 后门禁 60/60。
- **交叉专题**：GIL 先于 audit scope（PyPluginTrampoline 提前吸收位，上轮已验）；register_capability 锁内无用户代码（本轮抽验）；load worker 槽位自释放；clear_pending_capture_without_python 的免 decref 有注释依据；wx 字符串转换走 ToUTF8/FromUTF8 惯例。安全尾簇（e68694dbaf/203bc63f35）已吸收（5i）。
- **5h 线程 shim 无测试**：上游 59e96b71d0 本身零测试载荷——属上游共有验证空白，非移植保真缺口；建议任一侧未来补线程归因用例（记录为共享 TODO）。

## 无法评估项

- 跨平台（macOS/Linux）：门禁与实证均 Windows-only；python-home 解析在非 Windows CI 场景的上游重构（46fb512690）未跟随——fork 非 Windows 插件运行时未验证（补全路径：三平台 CI 构建 + 插件冒烟）。
- 装包形态（NSIS 含 python runtime）与 dev-launch segfault 归因：属 E5 发布级收口，不在本审查范围。

## Verdict 依据

唯一 (C) 失败 = 台账治理缺口（F1′，未 triage 的 10 文件上游触碰簇），修复面一行台账或一个小批次；无 (N)。按分支自身治理规则（上轮 F4 同类项曾驱动 REQUEST CHANGES），维持同一标准。
