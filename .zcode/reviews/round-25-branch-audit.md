# Round 25 — 全分支接线审计（"是否全都落地接线了"）

用户要求："整个分支所有这些内容，看看是不是全都落地接线了，还有什么问题"。
本轮是**全量审计**，不是单 bug 修复。对抗式开发循环：枚举所有声称的功能 → 派 3 个
对抗子 agent 攻不同维度（send path / slice 数据流 / 生命周期信号）→ 核实关键发现。

## 触发的理论缺口

- **死代码/功能丢失**：声称实现的 PRD §6 mandatory gate 在当前代码里完全不存在。
- **单层修复（元）**：round-10..24 的 14 轮 review 都没抽查 "gate 是否还存在"。
- **commit message 与改动不符**：7a6f050 message 说改 repaint toggle，实际删了 send gate。

## grep journal 结果（Step 1 强制）

- round-20 final summary 称 "Ready for human review"——但那是 round-21 之前的状态，
  且没覆盖 send gate 存活性。
- round-22-plater-audit 是专门的 "Plater 完整审计"，但 grep `gate/send_to_printer/
  on_action/Flow C/§6/export_gcode` 全部零命中——它审了 slice/cache/render，**漏了 send 路径**。
- 这正是 R1/R4 的陷阱：14 轮 "无新发现" 不是 stable，是认知边界内扫描。

## 合法 shape 清单（Step 0：本分支声称的功能）

| 功能 | PRD | 声称实现 commit | round-25 核实 |
|------|-----|-----------------|---------------|
| FulfillmentStore（in-memory） | §4 | a903b99 | ✓ 接线（Sidebar 持有，reset 接入） |
| Design/device snapshot + solve | §4 | 390eb4a | ✓ 接线 |
| Per-row edit/lock + reset/clear | §5.2.1 | e446373 | ✓ 接线 |
| Pre-print physical gate (mandatory) | **§6 Flow C** | eddafb5 + f4b61cc | **✗ 丢失（7a6f050 删）[blocker]** |
| Health indicator (title bar) | §6 Flow A | 78be5c3 | ✓ 接线 |
| Resolve dialog on broken rows | §5.2.1 | 19855a8 | ✓ 接线 |
| ΔE per row | §5 | 7da83d6 | ✓ 接线 |
| Design→expected colour swatches | §5.3 | 8b365da | ✓ 接线 |
| 3D Expected View | §5.3 | 5fb3b55 | ✓ 接线（design-indexed palette） |
| Slice against device filament space | §3 | 04b7cf3 | ✓ 接线（prepare_slice_inputs） |
| G-code uses real device filaments | §3 | 04b7cf3 | ✓ 接线（10-hop 全通，round-24 修了 distribution_mode） |
| Device palette cache (G-code preview) | — | 04b7cf3 | ✓ 接线 |
| Auto-sync device stock (2s timer) | §12.4 | 878744e | ✓ 接线（指纹漏 m_extruder，见 P1） |
| Mock flag propagation | — | 32c9d95 | ✓ 接线 |
| Persistence (3MF) | §12.2 | (deferred Phase 2) | ✓ 显式 deferred，无半成品 |
| Undo/recovery (Reset/Clear locks) | §12.1 | e446373 | ✓ 接线 |

## 退化输入×消费者矩阵（send path 维度）

| Send/print/export 入口 | fulfillment gate? | PRD §6 |
|------------------------|-------------------|--------|
| on_action_send_to_printer (15437) | ✗ 无 | blocker |
| on_action_send_to_multi_machine (15346) | ✗ 无 | blocker |
| on_action_print_plate_from_sdcard (15354) | ✗ 无 | blocker |
| on_action_print_plate (15326) | ✗ 无 | blocker |
| on_action_print_all (15459) | ✗ 无 | blocker |
| on_action_export_gcode (15479) | ✗ 无 | blocker |
| on_action_send_gcode (15487) | ✗ 无 | blocker |
| on_action_export_sliced_file (15495) | ✗ 无 | blocker |
| on_action_export_all_sliced_file (15503) | ✗ 无 | blocker |
| on_action_export_to_sdcard (15511) | ✗ 无 | blocker |
| on_action_export_to_sdcard_all (15519) | ✗ 无 | blocker |
| on_action_slice_plate (15242) | n/a（slice 不发出去） | — |
| on_action_publish (15299) | ✗ 无（但 publish_project 是空 stub） | non-blocking |

## 对抗审查结论（3 个 agent 并行）

### Agent 1 — send path 全门审计
**[blocker] PRD §6 Flow C mandatory gate 完全丢失。**
- eddafb5 加 gate 到 on_action_send_to_printer
- f4b61cc 提取 fulfillment_gate_blocks() 并扩展到 4 个入口（但漏了 7 个）
- **7a6f050（一个 repaint refactor commit）把整个 gate 删了**，commit message 只字未提
- 7a6f050..HEAD 没有任何 commit 重新加回（git log -S "fulfillment_gate_blocks" 为空）
- 当前 11 个 send/print/export 入口零 fulfillment 检查
- round-22 plater-audit 专门审 Plater，但零提及 gate——14 轮 review 全漏
- FulfillmentStore.hpp:28/118 注释仍提 "pre-print gate"，误导性陈旧文档

### Agent 2 — slice 数据流逐跳审计
**断言整体成立：design layer 不被污染、device space 正确构建、gcode 引用真实 device 槽。**
- HOP 1（prepare_slice_inputs 全 slice 入口）：4/4 真实 slice 入口接入，无绕过 ✓
- HOP 2（device config 传给 Print::apply）：无 design 覆盖 ✓
- HOP 3（temp_storage 生命周期）：栈局部，apply 深拷贝，UI 零引用，无 ghost ✓
- HOP 4（G-code preview palette）：cache 内容源是 device stock（非 design 色），断言担心证伪 ✓
- HOP 5（design layer 不变性）：fulfillment 零直接写 preset_bundle/model/filament_colour ✓
- 发现 1 个窄域缺陷（on_filaments_change 不 mark_stale）——经 tiebreaker 核实影响有限（见下）

### Agent 3 — 生命周期信号审计
**断言大部分成立，1 个真实 stale-leak + 2 个误导性注释。**
- Design-layer 变更 → mark_stale：✓ 全覆盖（EVT_FILAMENT_USAGE_CHANGED 单一 handler）
- Device stock 变更 → mark_stale：✓ 覆盖（load_ams_list + 2s timer）
- Project reset/New/Load → reset_all：✓ 全覆盖
- has_solved/has_stale 解耦：✓（commit 1a3c18c）
- Persistence：✓ 显式 deferred
- Concurrency：✓ 全 UI 线程（MQTT 经 CallAfter marshal）
- **[major] P1：physical_extruder（T-number）重映射不被任何信号捕获**
  - build_filament_ams_list（Plater.cpp:8674-8718）不含 physical_extruder
  - DeviceFilamentZone 2s 指纹（DeviceFilamentZone.cpp:117）不含 m_extruder
  - 后果：WCP 设备改 extruder_map_table 时 stale re-solve 不触发，device-space 数组
    按新 T-number 重排，G-code 静默串色。触发窄（WCP/Moonraker/Klipper 运行时改映射，
    BBL AMS 不受影响）。
- [minor] P2：reset_all 注释说 "clears entries" 但实现只 reset flags 不 clear m_entries
- [minor] P2：has_solved 注释滞后（说 never reset，实际 reset_all 会置 false）

## Tiebreaker 核实（两 agent 矛盾点）

Agent A（slice 审计）说 "on_filaments_change 不 mark_stale 是中危缺陷"。
Agent C（生命周期审计）说 "design-layer 变更（含加减 extruder）→ mark_stale 全覆盖"。

**查一手源**：
- `Sidebar::on_filaments_change`（Plater.cpp:3859）函数体确实不调 mark_stale/notify。
- 但活的 extruder 增删路径是 `set_num_filaments` → `Tab::update()` → `on_config_change`
  → 末尾无条件 `notify_filament_usage_changed`（Plater.cpp:22211）→ mark_stale。
- del_btn handler（Plater.cpp:3256-3262）在 `/* BBS hide del_btn */` 注释块里，是死代码。
- **裁决**：agent C 更准确（追完了链）。on_filaments_change 本身不 mark_stale 是真的，
  但活路径经 on_config_change 兜底覆盖。是脆弱点（依赖上游兜底），非当前 bug。

## 修订分级清单

### [blocker]（必修，PRD 核心功能丢失）
1. **PRD §6 mandatory send gate 完全丢失**。11 个 send/print/export 入口零检查。
   任何 broken（type 不匹配）的 fulfillment plan 都会静默发送，正是 PRD §6 第 430 行
   "no silent path through" 声称不会发生的情况。根因：7a6f050 误删，14 轮 review 未抽查。

### [major]（应修，真实但窄域）
2. **physical_extruder（T-number）重映射 stale-leak**。WCP/Moonraker/Klipper 设备
   运行时改 extruder_map_table 时，stale re-solve 不触发，G-code 静默串色。
   修法：把 m_extruder 加进 DeviceFilamentZone 2s 指纹 + build_filament_ams_list 比较。

### [minor]（清理）
3. `reset_all()` 实现不 clear m_entries（注释说 clears）——靠 has_solved 闸门行为正确，
   但语义不闭合，未来新增不查 has_solved 的消费者会读到 stale plan。
4. `has_solved()` 注释滞后（说 never reset，实际会）。
5. `FulfillmentStore.hpp:28/118` 注释提 "pre-print gate" 已不存在——陈旧文档。
6. `on_filaments_change` 不直接 mark_stale，靠 on_config_change 兜底——脆弱不变量。
7. `publish_project()` (Plater.cpp:20774) 是空 `return;` stub——publish 路径死代码。

## 已核实正确接线（断言成立的部分）

slice 数据流 5 跳全通（round-24 已修 distribution_mode）✓
design layer 零污染 ✓
3D/G-code preview 分流正确 ✓
生命周期信号（design/device/reset/stale/persistence/concurrency）全覆盖（除 #2）✓
anti-reinvention（MixedColorMatchRecipeResult，round-24 已补字段）✓

## 数据流 hops 状态（slice 路径，已逐跳核实）

| Hop | 写者→读者 | 状态 |
|-----|-----------|------|
| 1 prepare_slice_inputs 全 slice 入口 | 4/4 caller | ✓ |
| 2 device config → Print::apply | 无覆盖 | ✓ |
| 3 temp_storage 生命周期 | 栈局部+深拷贝 | ✓ |
| 4 G-code preview palette (cache) | device stock 源 | ✓ |
| 5 design layer 不变性 | 零直接写 | ✓ |
| 6 distribution_mode end-to-end | round-24 修 | ✓ |
| **7 send gate（PRD §6）** | **11 入口全 ✗** | **✗ blocker** |

## 过程意外 / 与预期偏差

- **commit message 欺骗**：7a6f050 message 只说 repaint refactor，实际删了 PRD 核心安全门。
  无论有意无意，message 和 diff 在意图/影响上都不匹配。这是 "accidental deletion masked as
  refactor" 反模式。
- **f4b61cc "gate all send paths" 从来就不完整**：即便在被删之前，它也只 gate 了 4/11 入口
  （漏 print_plate / print_plate_from_sdcard / send_to_multi_machine / 4 个 export/G-code 路径）。
  "所有 send 路径" 从一开始就是夸大声明。
- **round-22 plater-audit 的盲区**：它审了 slice/cache/render/lifecycle，但完全没看 send 路径。
  专门的 "Plater 完整审计" 漏了 Plater 最重要的输出路径。
- **14 轮 review 无一抽查 gate 存活性**：R4 元规则的精确兑现——静默轮次越多置信度应降，
  round-20 "Ready for human review" 的高置信是 smell 不是 done。
- **两 agent 矛盾的 tiebreaker**：on_filaments_change 是否 mark_stale，agent A 说漏 agent C
  说全覆盖。查一手源：agent A 只看到函数体，agent C 追完了 set_num_filaments→Tab::update→
  on_config_change→notify 链。裁决 agent C 对，但 agent A 指出的脆弱性成立。

## 遗留 backlog

- **[blocker] 恢复 send gate 并扩展到全部 11 个入口**（不只是 f4b61cc 当年的 4 个）。
  建议提取 `Plater::fulfillment_gate_blocks()` 私有方法 + 在每个 on_action_send/print/export
  入口首行调用。同时修 FulfillmentStore.hpp:28/118 的陈旧注释。
- **[major] physical_extruder 纳入 stale 检测**：DeviceFilamentZone 2s 指纹 + load_ams_list
  的 build_filament_ams_list 比较都加 m_extruder/physical_extruder 字段。
- **[minor] reset_all 真正 clear m_entries**（闭合语义，防未来消费者漏查 has_solved）。
- **[minor] has_solved 注释更新**。
- **本轮不修代码**：用户问的是 "看看是不是全都落地接线了"，是审计任务。修不修由用户定。

---

## Round 25 修订 — 用户澄清 + 两个 fix（2026-08-03）

### 撤销 [blocker]：send gate 丢失是**有意为之**

用户澄清："那个 broken 是我可以关掉的，不应该阻断发送打印"。

重新核对 PRD §3 Compass 第 6 条（line 124）：
> **§6 Decision authority rests with the user.** The system proposes and seeds;
> no automatic action may override the user's expressed intent.

**mandatory send gate 其实违反 §6**（强制阻断 = override 用户意图）。当前状态（gate 删除、
health indicator 保留为提示、Resolve dialog 提供处理入口）才是符合 §6 的设计。round-25
初判的 [blocker] 撤销。7a6f050 删 gate 是对的方向（虽然 commit message 没说清楚）。

### 已修（2 个 commit 待提交）

#### Fix 1 — 文档对齐"提示性、不阻断"意图（3 处）
- `docs/Fulfillment_Layer_PRD.md` §6 Flow C：从 "Pre-print physical (mandatory gate)"
  改为 "Pre-print physical (advisory, non-blocking)"，明确 broken 不阻断 send/print/export，
  用户保留 send 权威。与 §3 §6 "Decision authority rests with the user" 对齐。
- `FulfillmentStore.hpp:28`（FulfillmentEntry 注释）：去掉 "pre-print gate rolls up"，
  改为 "health rollup aggregates"，注明 advisory + PRD §6。
- `FulfillmentStore.hpp:118`（HealthRollup 注释）：从 "Roll-up for the pre-print gate /
  global indicator" 改为 "Roll-up for the global health indicator. Advisory only — does
  not block send/print"。

#### Fix 2 — T-number stale-leak（DeviceFilamentZone 指纹加 m_extruder）
- `DeviceFilamentZone.cpp:117` 2s 指纹：从 `m_index|m_type|color|mock` 扩展为
  `m_index|m_type|color|mock|T<m_extruder>`。
- 这样 WCP/Moonraker/Klipper 设备运行时改 `extruder_map_table`（slot 内容不变、只重映射
  slot→T-number）时，指纹变化 → 触发 mark_stale → prepare_slice_inputs re-solve →
  device-space 数组按新 T-number 正确构建。修复前会静默串色。

### 修2 的范围澄清（agent C 过度泛化，核实后收窄）

round-25 agent C 说 "两条 stale 路径都漏 m_extruder"（load_ams_list + 2s timer）。核实后：
- **2s timer（DeviceFilamentZone）**：读 `m_connect_machine_info_list`（WCP 路径，含 extruder），
  T-number 变更主要由它捕获 → **已修**。
- **load_ams_list（Plater.cpp:8727）**：接收 `MachineObject* obj`，是 **BBL AMS MQTT 路径**。
  `build_filament_ams_list`（Plater.cpp:8674-8718）从 `obj->amsList` 读，BBL 设备的 T-number
  是固定的（ams 顺序 = extruder 顺序），**不存在运行时 T-number 重映射场景** → 不需要改。
- `ConnectMachineInfo.extruder` 字段**只**在 WCP 路径（SSWCP.cpp:1648 `extruder_map_table`）填充，
  BBL/MQTT 路径（Monitor.cpp / GUI_App.cpp）不填 → 进一步确认 load_ams_list 不触发该场景。

agent C 的过度泛化：它看到两条路径都"漏 m_extruder"，但没区分两条路径服务的设备类型不同。
这是 skill 核查项 (j) "现状描述错比方向错更隐蔽" 的实例——方向对（T-number 漏检）但范围
描述错（说两条都要改，实际只 WCP 那条需要）。

### 测试证据
- build Snapmaker_Orca（主可执行，直接消费 DeviceFilamentZone.cpp 改动）：10/10 含 linking ✓
- 二进制时间戳（01:14:27）晚于所有 3 个源文件改动（01:12:01-01:12:45），确认重链接
- 文档改动无需测试（纯注释/文档）

### 仍遗留（backlog，未本轮修）
- [minor] reset_all 不 clear m_entries（语义不闭合，靠 has_solved 闸门行为正确）
- [minor] has_solved 注释滞后（说 never reset，实际 reset_all 会置 false）
- [minor] on_filaments_change 不直接 mark_stale（靠 on_config_change 兜底，脆弱）
- [minor] publish_project() 空 stub

