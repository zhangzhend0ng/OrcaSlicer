# Snapmaker Orca MCP 接入方案（综合版）

- 日期：2026-09-07
- 状态：草案 v2（经两轮架构级对抗审查并修订；工具实现层尚未对抗）
- 变更记录：v2 按第二轮 REFUTE（1 blocker + 6 major）修订——骨架前提改正（WebSocketDebugServer→HttpServer session）、私有协议与 MCP 合规论述切割、快照/job 机制补定义、M0/M1 范围与口径修正、token 威胁模型改写、双后端 schema 守护
- 依据：业界调研（Onshape / Blender / FreeCAD / Prusa 生态）+ 本仓库代码核查（关键前提均带 file:line，经独立代理逐行核实）

---

## 0. 一页结论

**做什么**：给 Orca 增加一套 MCP（Model Context Protocol）接口，让 Claude 等 AI 客户端能查询场景、改工艺参数、操控 GUI 会话切片导出、（后期）下发打印与校准。

**怎么分**：一个 MCP server 产品，两个后端，五个里程碑。

| 里程碑 | 内容 | 工期（单人全职、熟悉本仓库） |
|---|---|---|
| M0 | 外置 stdio MCP server：CLI 封装（参数/切片/导出）+ 知识层工具（mesh 分析/朝向/成本，用现成解析库） | 3–5 天 |
| M1 | Orca 进程内 MCP listener 底座 + 只读状态 + plate 截图 + 会话切片/进度/导出 | 2–2.5 周 |
| M2 | 会话内工艺参数读写（undo 感知，含自建复合层）+ 模型加载/变换/摆盘 | ~2 周 |
| M3 | per-object / per-plate 设置 + 刷新/选中一致性 | ~2–3 周 |
| M4 | 设备列表 / 发送打印（UI 人工确认）/ 校准 | ~2–3 周 |

核心价值（M0–M2）约 5–6 周落地；全部主要能力约 2–3 个月。M3/M4 估算未经过对抗，浮动 +20–30%。

**最大风险**：per-object 设置深水区、设备链路需真机测试、upstream 合并负担（用独立目录缓解）。

---

## 1. 背景与依据（为什么这么做）

### 1.1 业界现状

| 厂商 | 做法 | 对本方案的启示 |
|---|---|---|
| PTC Onshape | 官方 FeatureScript MCP（2026 初），text-to-code-to-CAD，窄语义通道 | 不暴露全 API，挑一条语义化通道 |
| Blender | 官方实验（Blender Lab）+ 社区 blender-mcp，同构：进程内 addon socket + 外部 stdio 桥 + 万能 execute_code | 两层架构是事实标准；bpy 是它薄的真正原因 |
| FreeCAD | 社区 freecad-mcp（同 Blender 双层结构） | 同上 |
| Prusa | **官方零动作**；社区 4+ 个 MCP 全部外置驱动 CLI/PrusaConnect，无一修改本体 | CLI 够强生态就能自长；但没人能操控 GUI 会话——空白点 |

### 1.2 关键教训（跨案例收敛）

1. **进程内薄 listener + 外部 stdio 桥**是"控制已打开 GUI 应用"的业界标准形态（Blender/FreeCAD 一致）。
2. **MCP 规范复杂度放外部桥接进程**（官方 SDK），C++ 侧只做简单内部协议——Blender 的进程内通道就是自定义 JSON-over-TCP。
3. **工具必须走 UI 同款代码路径**（bpy.ops 教训）：否则 undo/刷新/选中状态脱节。
4. **给模型眼睛**：Blender 的 viewport 截图、PrusaMCP 的 PrintWindow 后台截窗，都是实际体验中价值最高的工具之一。
5. **知识层工具不依赖切片器集成**（PrusaMCP 9 个知识工具），成本低、价值密度高。
6. Prusa 官方发 `prusa-slicer-console.exe` 解决 Windows GUI 子系统 stdout 问题；本仓库已有同族机制 `attach_console_on_demand()`（`src/Snapmaker_Orca.cpp` ~:6157）。

### 1.3 定位

桌面切片器界"官方 GUI 会话 MCP"仍是空位（Prusa 未做、Blender 官方只在 DCC 类实验）。Snapmaker 做成即为此类软件首个，且与 Snapmaker 硬件（发明者用户、AI 操控工作流）契合。

---

## 2. 架构决策（已定，经对抗修订）

### 2.1 总体结构

```
Claude / 任意 MCP 客户端
   │ stdio（官方 MCP SDK）
   ▼
[snapmaker-orca-mcp 桥接进程]（Python/TS，MCP 规范全在这层）
   │
   ├─ 会话后端（M1+）：HTTP JSON-RPC → Orca 进程内 listener（127.0.0.1 独立端口）
   └─ CLI 后端（M0）：子进程调用 headless CLI（参数/切片/导出）
        （M1 落地后会话后端接管切片类工具，CLI 后端保留作 CI/批量路径）
```

### 2.2 进程内 listener 设计要点（对抗审查后的修订版）

- **独立端口、独立 server 实例**：**复用 `HttpServer::session` 的报文解析层**（request line/headers/content-length 已解析，`HttpServer.cpp:304-389`），扩展 handler 签名传入 method+headers+body，新起一个 Mcp server 实例与独立端口。注意区分："不复用"仅指不复用其静态路由/handler/端口（13619 的 flutter 服务与 CORS `*` 裸奔面，:204-211、:938-947），**报文解析层复用**；不可借 `WebSocketDebugServer` 骨架（它是 websocket server，零 HTTP 请求解析，`WebSocketDebugServer.cpp:122-155`）。token 校验加在 Mcp 实例 handler 最前端。
- **内部协议 = 私有协议**：POST JSON-RPC，与 MCP 规范无关——MCP 端点在桥接进程（官方 SDK 承担全部规范合规，含 streamable HTTP 的 Origin 校验 MUST 等要求）。listener 侧不出现 405/SSE/规范字眼，避免两套语义混淆。进度一律 job id + 轮询；job 注册表放**进程级**（非 listener 对象级），server restart 后 job 表仍在，仅进程退出才失效；restart 后 poll 未知 job id 返回明确"job 未知"而非挂起。
- **线程纪律（无阻塞原则）**：HTTP 线程永不等待主线程。读 = **快照缓存**，发布机制定义为：UI 线程在显著状态变更点（加载/切片完成/摆盘/参数变更等）失效并重建快照 + 低频 wxTimer（如 1–2s）兜底；快照构建须在 UI 线程并协调 `BackgroundSlicingProcess` 状态锁（切片中只发布轻量进度快照，不深拷贝 plate 数据）。wx 事实：模态嵌套循环仍派发 timer/CallAfter，即模态期间**读保持新鲜而写排队**——读写语义不对称，在工具响应中原样暴露（"stale_at" 时间戳 + 写操作"UI 忙"状态），不假装一致。
- **工具实现纪律**：不直接戳 Model 数据，一律调 Plater 与菜单按钮**同一个 handler**（bpy.ops 教训）；每次写操作进 undo 快照（`take_snapshot`，落地时核实签名）；单飞互斥 + "UI 忙"状态（模态对话框嵌套循环会执行排队的 CallAfter，`Plater.cpp:19972` 一类，语义为"用户对话框打开时 MCP 操作排队"）。
- **代码卫生**：全部新代码放 `src/slic3r/GUI/Mcp/` 独立目录，对既有文件只留个位数 hook 点，压 upstream 合并负担。

### 2.3 桥接进程

- 官方 MCP SDK（Python/TS），stdio transport；`.mcpb` 分发可选（Blender 官方先例）。
- Orca 未运行时 spawn-on-demand；实际端口从 `data_dir` 下的发现文件读取（现有 server 端口被占会 +1000 静默漂移，`HttpServer.cpp:491-494`，不能硬编码）。
- token 从 app_config 读取，随启用时生成。

### 2.4 明确不做（负面清单）

- **不做** `execute_code` 式万能工具，**不**为 MCP 内嵌脚本运行时（Orca 没有 bpy 等价物，补这个比 MCP 本身大一个量级且安全面更差）；走精选显式工具。
- **不**在 C++ 侧手搓完整 MCP 规范（session/SSE 全留桥接层）。
- **不**复用现有 HttpServer 管线，**不**与 flutter 端口混布。
- **不做** G-code 逐层预览工具（GCodeViewer 内部数据，成本/收益不成立，未来再议）。
- `--mcp` headless stdio 模式（原第 1 级）：**缓行**，仅当 M1 后仍出现 CI/批量持久会话需求再立项；此前期望由既有 CLI 覆盖。

---

## 3. 分期计划

### M0（3–5 天）外置快速版 —— 零产品代码，先行验证价值

- 交付：`snapmaker-orca-mcp`（TS/Python，stdio），工具：
  - 知识层：`analyze_mesh`、`check_printability`、`suggest_orientation`、`estimate_cost`——网格解析用**现成库**（Python: trimesh / 二进制 STL 直读；3MF = zipfile + XML，不自研解析器）
  - CLI 层：`set_and_slice(model, overrides, printer, filaments) → gcode + 统计`、`export_3mf`
  - `recommend_settings` **不在 M0**——其知识库来源是待决策点（§7.5），M0 只做参数目录查询（`list_params`，从 CLI `--help`/配置注册表导出），推荐引擎待 §7.5 决策后进 M1+
- CLI 参数能力已验证：`print_config_def` 全部工艺参数自动成为合法 CLI 选项（`PrintConfig.hpp:1891-1894`），`read_cli` 带类型校验、未知键明确报错（`Config.cpp:1703`），覆盖优先级 命令行 > preset > 3MF（`Snapmaker_Orca.cpp:1085`→:2970），切片前统一校验（:3001）。
- 验收：Claude Desktop 里自然语言完成"改层高/温度 → 切片 → 拿到 G-code 和耗材统计"。
- 备注：Windows stdout 捕获先跑半天 spike（Prusa console 伴生 exe 是官方先例，本仓 `attach_console_on_demand` 同族，属确认性验证）。

### M1（2–2.5 周，口径拆解）进程内底座 + 会话切片

- 工期分解（各项均已计入）：session 层扩展 + Mcp 实例与独立端口（2–3 天）；token 生成/校验 + 端口发现文件读写（1 天）；快照缓存机制（2–3 天）；job 注册表 + poll（1–2 天）；偏好页开关 UI + 本地化字符串（1–2 天）；桥接进程会话后端 + spawn-on-demand（2–3 天）；6 个工具实现与 E2E（3–4 天）。
- 交付：`src/slic3r/GUI/Mcp/` + 桥接进程会话后端 + 工具：
  - `get_state`（plates/objects/变换/超界，快照缓存，带 stale_at 时间戳）
  - `get_plate_screenshot`（后端现成：`GLCanvas3D::render_thumbnail`，`GLCanvas3D.cpp:3172-3222`，三路 framebuffer 路径；**须 UI 线程 GL 上下文有效**，CallAfter 化执行；512px base64 经 localhost 轮询体积可接受）
  - `list_params`（参数目录：直接从 `print_config_def` 生成，含已本地化的中文 label/tooltip/min/max/enum，作用域打标 process/filament/machine 用 `Preset::print_options()` 等，`Snapmaker_Orca.cpp:2369` 即用法）
  - `slice`（`Plater::reslice()` `Plater.cpp:21136`，异步 job）+ `poll_job`（进度需新增 background_process 状态公有只读访问）
  - `export_gcode`（`schedule_export`，`BackgroundSlicingProcess.cpp:721`，无对话框）/ `export_3mf`
- 验收：Orca 开着，AI 说"把当前盘切片并导出"，全程无 CLI、看得见进度。
- 先决 spike（1–2 天并入）：POST 往返 + CallAfter 异步完成 + 快照缓存原型，验证不阻塞 flutter 服务。

### M2（~2 周，含自建复合层）会话内配置读写 + 模型操作

- `set_params` 的落点已核：程序化写入口存在——`PartPlate::config()`（`PartPlate.hpp:233`）、`project_config.set_key_value`（`Plater.cpp:7200`）、UI 参照 `PlateSettingsDialog`；但**不存在现成的"validate + apply + 刷新 + undo"复合入口**，该层需自建并计入工期。
- 工具：`set_params`（校验走 `m_print_config.validate` 语义，错误回传模型自纠）、`load_models`（`load_files(LoadModel|Silence)`，注意 Silence 仅部分静音，`Plater.cpp:17614` 附近）、`remove_object`、`set_transform`、`arrange`
- 纪律：全部走 UI 同款 handler；写操作进 undo；模态时返回"UI 忙"。
- 验收：AI 完成"加载模型 → 摆盘 → 改工艺参数 → 重切 → 截图确认"闭环。

### M3（~2–3 周）per-object / per-plate 设置

- 对象级覆盖（ModelVolume/配置覆盖 + 多处 UI 同步刷新）——全项目最深水区，估算不确定度最大；进入前先对该期方案做一轮对抗审查。
- 验收：AI 对指定对象设置单独参数并重切，GUI 与真实状态一致、undo 行为正确。

### M4（~2–3 周）设备 / 打印 / 校准

- 工具：`list_devices`（DeviceManager）、`send_to_print`（**必须在 Orca UI 弹人工确认框**，human-in-the-loop；鉴权复用 MachineObject/NetworkAgent，MCP 层只透传——参考 Prusa 生态"打印鉴权在平台层"的成熟做法）、`run_calibration`（CalibUtils：流量/PA）
- 需真机测试；打印链路全异步，沿用 job + 轮询语义。

### 持续卫生（贯穿）

- upstream 同步：Mcp/ 独立目录 + 最小 hook；每次上游合并跑 `ctest`（Catch2，覆盖 libslic3r 层工具逻辑）+ E2E 脚本（真实 3MF 工程件，非仓库内自制 fixture）。
- 每个实现迭代走对抗循环（方案级 REFUTE 先于实现）；工具实现层整体尚未对抗，是本计划的主要估算风险源。

---

## 4. 工具目录 v1（汇总）

| 类别 | 工具 | 落地期 | 后端 |
|---|---|---|---|
| 内省 | get_state / list_params / get_plate_screenshot / poll_job | M1 | 快照缓存 / config_def 目录 / 视口渲染 |
| 操作 | load_models / remove_object / set_transform / arrange / set_params / slice / export_gcode / export_3mf | M1–M2 | Plater UI 同款 handler |
| 知识 | analyze_mesh / check_printability / suggest_orientation / estimate_cost（M0）；recommend_settings（待 §7.5 决策，M1+） | M0 起不依赖集成 | 桥接进程本地 |
| 设备 | list_devices / send_to_print（人工确认）/ run_calibration | M4 | DeviceManager / CalibUtils |

---

## 5. 安全与语义边界

1. listener 仅 127.0.0.1、独立端口、**默认关闭**，偏好设置开关 + 启动时生成随机 token 存 app_config；**token 每请求强制校验**。威胁模型如实声明：token **不是**对同用户本地进程的边界（app_config 同用户任意进程可读），其真实价值 = 默认关 + 127.0.0.1 + token 挡住**浏览器来源的 drive-by/DNS rebinding 攻击**（无 CORS 头并不阻止恶意页面跨站*发送* POST，只挡读响应——所以每请求 token 校验才是实际防线）。MCP 规范侧的 Origin 校验 MUST 属桥接层（官方 SDK）义务，若未来 listener 直接暴露 streamable HTTP 则须补 Origin 校验。
2. 顺手修复项（独立安全 backlog，与本方案解耦）：现 HttpServer `Access-Control-Allow-Origin: *`（`HttpServer.cpp:207-209`）与 `/localfile/` 任意本地文件读取（:938-947）。
3. 物理动作（send_to_print）必须 UI 人工确认；机器安全类参数（最高温度等）在参数目录打标，工具层显著提示或禁止。
4. 语义诚实化：用户模态对话框打开时 MCP 操作排队并返回"UI 忙"；切片等长操作全部 job 化，无阻塞请求。

---

## 6. 风险登记表

| 风险 | 等级 | 对策 |
|---|---|---|
| per-object 设置刷新/选中一致性 | 高 | M3 前单独对抗；只走 UI handler；E2E 截图比对 |
| 设备链路真机依赖 | 高 | M4 独立排期，真机验收；job 语义先行 |
| 模态对话框交叉执行 | 中 | 单飞互斥 + UI 忙语义；对话框清单过一遍 |
| upstream 合并负担 | 中 | Mcp/ 独立目录、最小 hook、每周期 ctest |
| M3/M4 估算偏差 | 中 | 已标注 +20–30%；M3 进入前重新估算 |
| server restart 腰斩 MCP 请求 | 低 | job 表进程级（restart 不丢）；未知 job id 返回明确错误而非挂起 |
| 双后端工具 schema 漂移 | 低 | 工具 schema 单一来源（桥接仓一份 JSON 定义，CLI/会话两后端共用）+ CI 一致性校验；CLI 后端仅保留 CI/批量场景，长期双维护成本已知晓并接受 |

---

## 7. 待人工决策点

1. 独立端口编号（避开 13618/13619 及漂移区间）。
2. 默认开关状态与设置页交互形态（建议默认关 + 一键开启引导）。
3. `send_to_print` 确认 UX（建议复用现有发送打印对话框）。
4. 是否立项 `--mcp` headless 模式（建议：M2 验收后再评估）。
5. 知识层 `recommend_settings` 的数据来源（自研 FDM 知识库 vs 复用 Orca 校准与帮助文档）——**该项悬而未决前 M0 不含此工具**，M0 仅交付参数目录查询。

---

## 附：证据索引（关键 file:line）

- 请求管线缺陷：`HttpServer.cpp:369`（仅透传 URL）、:322-330（body 丢弃）、:204-211（CORS */Connection: close）、:491-494（端口漂移）、:938-947（/localfile/）
- Server 现状：`GUI_App.hpp:346`（13618 已注释）、:349（m_page_http_server 13619）、`GUI_App.cpp:1266-1268`
- 会话操作面：`Plater.cpp:21136`（reslice）、:20247（export_gcode）、:20346（send_to_printer）、:11527（进度对话框）、:17614（Silence 局限）、:19972（未保存更改对话框）；`BackgroundSlicingProcess.cpp:506`（start）、:721（schedule_export）
- 公有 API 充足性：`Plater.hpp:319`（model()）、:780（get_partplate_list）
- CLI 参数机制：`PrintConfig.hpp:1891-1894`（print_config_def 合并）、`Config.cpp:1657/:1703`（read_cli/报错）、`Snapmaker_Orca.cpp:1085→:2970→:3001`（覆盖优先级与校验）、`PrintConfig.cpp:8601-8610`（load_settings/load_filaments）、`Snapmaker_Orca.cpp:2369`（Preset::print_options 用法）
- 单实例：`InstanceCheck.cpp:356-368`；SSWCP 命令表（仅语义参考，wxWebView 耦合不可作后端）：`SSWCP.cpp:7823`、:8320-8336
- v2 新增核实：`WebSocketDebugServer.cpp:122-155`（ws 骨架不可借）、`HttpServer.cpp:304-389`（session 解析层可复用）、`PartPlate.hpp:233`（config() 写入口）、`Plater.cpp:7200`（project_config.set_key_value）、`GLCanvas3D.cpp:3172-3222`（render_thumbnail）、`HttpServer.cpp:624-688`（健康检查 restart 机制）；`attach_console_on_demand` 实为 `src/Snapmaker_Orca.cpp:6156`
