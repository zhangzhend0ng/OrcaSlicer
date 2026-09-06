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
