# MCP 接入实施日志（journal）

- 分支：`feature/mcp-integration`（worktree `C:\coil\Projects\SnapmakerOrca-mcp`，基于 origin/main dcf8629e66）
- 规格：`docs/mcp-integration-plan-2026-09-07.md`（v2）
- 恢复协议：读规格 + 本 journal tail + `git log` 对账，不信任对话摘要。

---

## M0：外置 stdio MCP server（完成）

### 交付物
- `tools/mcp-bridge/`：Python 桥接包 `snapmaker_orca_mcp`（官方 SDK `mcp==2.0.0` lowlevel Server + stdio）。
- 工具 7 个：`analyze_mesh` / `check_printability` / `suggest_orientation` / `estimate_cost`（trimesh 知识层）、
  `list_params`（生成目录）、`set_and_slice` / `export_3mf`（CLI 后端）。
- `tools/mcp-bridge/snapmaker_orca_mcp/tools_schema.json` = 工具 schema 单一来源（风险表 §6 对策）。
- `scripts/generate_params_catalog.py`：从 `src/libslic3r/PrintConfig.cpp` 生成
  `snapmaker_orca_mcp/data/params_catalog.json`（747 项；带 layout marker 防静默漂移）。
- 单测 35 个（pytest）；E2E 2 个：backend 级 + MCP stdio 协议级。

### 验收证据
- 单测：`35 passed`（含真实 3DBenchy.3mf fixture 的解析测试、守卫变异验证）。
- E2E backend：`E2E RESULT: GREEN`——真实 exe 切片 twospheres.obj（Artisan 0.4 + Generic PLA），
  `layer_height=0.3`/`sparse_infill_density=15%` 覆盖在 gcode CONFIG_BLOCK 中逐字验证，
  统计 layers=80 / 16m11s / 耗材>0 从 gcode footer 解析。
- E2E stdio：官方 SDK ClientSession ↔ `python -m snapmaker_orca_mcp`，
  initialize/list_tools/call_tool（含 isError 结构化错误）/全绿。
- 守卫测试变异验证（无牙测试检查）：
  - 变异1：删除 `_validate_override_key` 的禁止键检查 → `test_managed_keys_cannot_be_overridden` FAIL ✓
  - 变异2：破坏 `total layers count` 解析 → 3 个 gcode_stats 测试 FAIL ✓

### 关键事实（CLI 深挖结论，M1+ 复用）
1. Windows 构建形态：`Snapmaker_Orca` target = **DLL**（导出 `Snapmaker_Orca_main`）；
   唯一 exe 是 WIN32 shim `snapmaker-orca.exe`（target `Snapmaker_Orca_app_gui`），GUI/CLI 共用入口。
   构建 target 需选 `Snapmaker_Orca_app_gui` 而非 `Snapmaker_Orca`。
2. CLI = `start_gui = m_actions.empty()`（Snapmaker_Orca.cpp:1141）：`--slice N` 是 action → headless。
   stdout/stderr 管道捕获可用（WIN32 子进程继承句柄；`attach_console_on_demand` 仅 print_help 调用，不抢管道）。
3. **CLI 不解析 preset `inherits` 链**，且 machine/process 各只收一个文件 → 桥接层自行合并链为单临时 JSON
   （base 先、子覆盖；例：Artisan 0.4 = 5 层链）。这是"CLI 切片报 Relative extruder addressing 校验错"的根因。
4. CLI 选项 token 用 `cli` 字段的**短横线别名**（`read_cli`/`cli_args`，Config.cpp:238、:1703），
   `--layer_height` 无效、`--layer-height` 有效；`cli` 字段为空时才是 key 的下划线→短横线转换。
   桥接层由 catalog 提供 token 映射（`_cli_token_for`）。
5. 3mf 版本门禁：`cli_ver.maj != file_ver.maj || cli_ver.min < file_ver.min` 拒载（Snapmaker_Orca.cpp:1432），
   `--allow-newer-file`（bool，不带值）或 env `SNAPMAKER_ORCA_ALLOW_NEWER_FILE` 旁路。
6. `--outputdir` → `plate_N.gcode`；gcode footer 统计行格式已入库解析器
   （`; total filament used [g] =` 等 5 类，非 BBL 打印机路径）。
7. `record_exit_reson` 的 `result.json` 仅 Linux 编译（#if __LINUX__），Windows 不可依赖。

### 发现的上游缺陷（已记录，不在 M0 修）
- **BBL 格式 3mf CLI 切片崩溃（segfault，exit -2/0xFFFFFFFE 或 139）**：repo 内
  handy_models/calib 的 3mf（含 v2.1.0.0-alpha）即使 `--allow-newer-file` + 完整显式 preset 也崩；
  OBJ/STL 同参数切片正常。黑盒无法进一步定位（无 cdb/无管理员/无 WER 记录）。
  崩溃点在 PartPlate 建盘之后的 3mf 专属路径（排除区 log 两次后崩）。
  处置：桥接层把它作为结构化错误（`cli_crash`，1.3s 内返回，无挂起）如实上报；
  E2E 断言该行为；工具描述中写明限制。留待上游修复或 M1 会话后端绕过。
- **CLI `--export-3mf` 必崩**：导出前缩略图再生成需 GL 上下文（Snapmaker_Orca.cpp:5304 起，
  `need_regenerate_thumbnail` 路径），CLI 进程无 GL 初始化 → segfault。
  处置：M0 `export_3mf` 由桥接层实现（3mf 透传 copy / 网格 → 最小 3mf writer，
  `knowledge/threemf_writer.py`，zipfile+xml）；完整工程导出归 M1 会话后端。
  （trimesh 的 3mf 导出需 lxml，读取也需 lxml——lxml 已加入依赖。）

### 范围决策记录
- `recommend_settings` 不做（§7.5 决策已定，M0 只交付 list_params）——无需降级。
- M0 工具面与文档 §3 M0 节一致：4 知识工具 + list_params + set_and_slice + export_3mf。

### 自对抗（轻量 REFUTE）记录
- R：事件循环阻塞 → **实锤修复**：handler 经 `anyio.to_thread.run_sync` 执行，
  新增测试 `test_blocking_handler_runs_off_event_loop`（断言 handler 线程 ≠ loop 线程）。
- R：命令注入 → subprocess 列表参数（无 shell）+ override 键校验（catalog ∪ 非托管键）+ 管理键禁改。
- R：schema 漂移 → 单一 tools_schema.json；`ToolRegistry` 拒绝无 schema 的 handler。
- R：路径类输入 → 扩展名白名单 + 大小上限 + 存在性检查。

### 环境/坑
- Git Bash 下 robocopy 反斜杠被吞 → 用 `cmd //c` 调用。
- 测试里 `Path(__file__).parents[N]` 层级算错会让 fixture 测试**静默 skip**（假绿），
  已修（parents[3]）并确认 skip 数从 4 → 0。
- mcp 2.0.0 pydantic 字段为 snake_case：`is_error` / `structured_content` / `server_info`
  （wire 格式仍 camelCase，由 alias 处理）。
- 构建命令沉淀：`build_mcp_baseline.bat`（configure+全量）与 `build_mcp_shim.bat`（shim），
  产物 `build/src/Release/{Snapmaker_Orca.dll,snapmaker-orca.exe}`。

### M0 验收门核对
- [x] 构建：桥接为 Python；被依赖的可执行 target 已真实编译（dll+exe，字符串证据 grep layer_height 命中产物二进制）。
- [x] 测试：35/35 通过（新增 35；C++ 层 M0 无改动故无 Catch2 新增）。
- [x] E2E：backend + stdio 双脚本全绿（真实 exe、真实 3mf fixture、现场生成真实几何网格）。
- [x] 对抗收尾：横向 grep（`--layer_height`（下划线直达 CLI）全桥接无残留；`execute_code`/SSE 无出现）。
- [x] 提交：M0 单 commit（含 journal）。

---

## M1：进程内 listener 底座 + 会话切片/导出（完成）

### 交付物（C++，全部在 src/slic3r/GUI/Mcp/，既有文件仅最小 hook）
- `McpJsonRpc`：私有 POST JSON-RPC 解析/信封（nlohmann，异常 containment）。
- `McpJobs`：**进程级** job 注册表（单例；listener 重启不丢；未知 id 明确报错；终态不被迟到进度复活）。
- `McpHttpListener`：127.0.0.1 独立端口 13620、每请求 Bearer token 校验、Content-Length 全量 body
  （复用 HttpServer::session 报文解析流，扩展 body 读取）；绑定失败即 false，**无端口漂移**。
- `McpServer`：门面。快照缓存（UI 线程构建 + 1.5s wxTimer 兜底 + 事件增量）、job 编组
  （HTTP 线程永不等待 UI）、token 生成/存 app_config、发现文件 `<datadir>/mcp_session.json`。
- 偏好页开关（默认关）+ zh_CN 本地化 5 条。
- 私有协议方法：ping / get_state / poll_job / load_models / get_plate_screenshot / slice /
  export_gcode / export_3mf。无任何 MCP 规范概念（无 SSE/405/CORS）。
- 桥接 session 后端（Python）：发现文件读取（端口不猜测）、HTTP JSON-RPC、call_and_wait 轮询、
  工具 schema 单一来源新增 6 个 session 工具。

### 既有文件 hook 点清单（共 5 处，均为最小增量）
1. GUI_App.cpp：on_init 启动 + shutdown 停止（2 行级）。
2. Plater.hpp：`EVT_PROCESS_COMPLETED` wxDECLARE（原本只在 .cpp 定义）+ `mcp_export_gcode_to` 声明。
3. Plater.cpp：`mcp_export_gcode_to` 实现（additive 方法）。
4. Preferences.cpp：AI/MCP 开关页（校验回调实时 enable/disable）。
5. src/slic3r/CMakeLists.txt + tests/CMakeLists.txt：源文件/测试子目录注册。

### M1 期间修的自身缺陷（对抗发现）
- **listener 单写死锁**：请求体与头同包到达时滞留 streambuf，read_body 只在 socket 上等新数据
  → 双方互等。修复：先取尽缓冲再读余量（单元测试-first 的 McpHttpListener 测试当场抓住）。
- **lazy hooks**：enable 发生在 on_init 时 Plater 尚未创建 → plater 事件 Bind 静默丢失
  → 切片完成事件无人接。修复：rebuild_snapshot 每 tick 重试安装。
- **slice 直调 reslice() 不启动**：UI 按钮实际链路是 start_slice()=exit_gizmo+update(true,true)+
  FlowType 同步 + GLTOOLBAR 事件；照抄该链路。
- **slice 看门狗**：VM 上切片 finalize（缩略图渲染，CPU 0% 死锁态）可无限停滞 → 180s 看门狗诚实失败。
- **export 竞态**：Finished 事件先于后台线程收尾，running() 短暂为真 → 导出 hook 改为
  正典链路（update_background_process+schedule_export+FORCE_EXPORT）失败时回退拷贝 tmp gcode
  （切片 100% 时该文件已完整写出）。

### 环境事实（VM 相关，journal 存档）
- 本 VM 的 snapmaker-orca 构建屏显 3D 画布渲染为白屏（系统 GL 检查通过、离屏 FBO render_thumbnail
  正常出图）；切片 finalize 的缩略图渲染依赖屏显路径，偶发 CPU 0% 死锁。E2E 用
  SetForegroundWindow + 看门狗 + 重试应对；疑似环境级问题，非 MCP 代码引入。
- handy_models 的 BBL 格式 3mf（v2.1.0.0-alpha）内嵌设置 apply 失败 → 盘 apply_invalid 不可切
  （GUI 与 CLI 同病）；E2E 改用真实网格 STL fixture + load_models 装载。
- Windows JSON 配置文件**必须带 MD5 校验和行**，否则 substr 越界 GUI 初始化崩溃
  （E2E 种子按 Orca 格式写 "# MD5 checksum" 行）。
- App 侧 boost log 文件/stdout 在启动 ~10s 后不再刷出（缓冲），日志缺席不可作证据；
  E2E 全部以 RPC 可观测状态断言。

### 测试与验收证据
- C++ 单测（tests/mcp，Catch2）：**14 用例 / 2166 断言全过**（JSON-RPC 解析信封、job 注册表并发、
  listener 真实回环：token 门禁/坏 JSON/超大 Content-Length/重复 stop）。
- 守卫变异验证：删除 token 校验 → 2 个测试 FAIL（证据在上），恢复后全绿。
- 桥接 pytest：**42 passed**（新增 session 后端 7 项：发现文件缺失/损坏、token 错误、轮询完成/失败、
  handlers 形状；mock HTTP server 全链）。
- E2E：
  - `e2e_m1_session.py`（裸 listener，真实 GUI）：**GREEN**——token 拒绝、get_state(plates/objects/
    stale_at)、load_models(真实 STL 几何)、截图(256×256 PNG 非 blank + IHDR 匹配)、slice 100%
    "Slicing complete"、export_gcode 文件落地、export_3mf、poll 未知 job → -32003、单飞 ui_busy。
  - `e2e_m1_bridge.py`（MCP stdio 客户端 → 桥接 session 后端 → listener → GUI 三跳）：**GREEN**——
    initialize/list_tools 服务面、get_state、load_models、slice（含看门狗重试）、export_gcode
    10.9MB 真实 gcode 文件。
- 产物字符串证据：Snapmaker_Orca.dll 含 "McpListener serving on"/"mcp_session.json"/
  "mcp_enabled"/单飞文案各 ≥1。

### 与 M0 环节的归并说明
- `load_models`（原 M2 工具）提前至 M1 交付：M1 E2E 需要在画布健康状态下装载真实模型，
  且该工具走 Plater::load_files UI 同款入口。M2 仍会交付其余模型操作工具并复测此项。
- ctest：全套 212 项中新增 14 项 MCP；fff_print 3 个混色相关失败与 libslic3r_tests 构建情况
  见下节补记（M1 提交后补跑）。

### M1 验收门核对
- [x] 构建：Snapmaker_Orca.dll + snapmaker-orca.exe（改动触及 target）真实编译 + 字符串证据。
- [x] 测试：C++ 14/14 + pytest 42/42；ctest 全套（M1.1 补记）：**521 项中 515 过 / 6 失败**，
      全部为主干既有（git diff origin/main -- src/libslic3r 为空，证明非本分支引入）：
      DynamicPrintConfig serialization、Placeholder parser scripting(SEGV)、cached slots、
      3×fff_print 混色相关。另有 tests/libslic3r/test_sswcp_protocol.cpp 在 main 上即用
      Catch2 v2 头（仓库实为 v3）无法编译 → 已做 1 行 include 修复使 libslic3r_tests 可构建。
- [x] E2E：裸 listener + 三跳桥接双 GREEN。
- [x] 对抗收尾：token 门禁变异、横向 grep（无 SSE/405/CORS/execute_code 字样）。
- [x] 提交。
