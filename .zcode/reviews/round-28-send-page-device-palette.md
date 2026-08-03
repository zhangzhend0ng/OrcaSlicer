# Round 28 — 预打印/发送页取色错位 + 映射变化后切片不失效

两个关联 bug(用户连续指出):
1. "这个映射你考虑预打印页了吗？有适配吗" → 发送页/3MF 写入取色错位(Fix 1/2/3)
2. "修改映射后切片要失效" → 映射变化后 slice_result 仍标 valid(Fix 4)
3. "不应该在我触发拖动的时候重新映射" → Fix 4 原实现 schedule_background_process
   触发自动重切+重映射(Fix 4 修正)
4. "图标不对" → FulfillmentPanel 三个按钮图标错配(图标修正)
5. "预打印页上方色块还是 design 色" → build_device_filament_space 漏重排
   filament_multi_colors / filament_colour_mode(Fix 5)

## 图标修正 — FulfillmentPanel 按钮(用户第四轮指出)

phys_btn / mix_btn / lock_btn 用错了图标:
- phys_btn(选物理耗材):`"edit"`(铅笔)→ `"menu_filament"`(与 sidebar
  物理耗材入口 Plater.cpp:2825 一致)
- mix_btn(编辑混色):`"menu_filament"` → `"color_palette"`(与 sidebar
  混色区 Plater.cpp:6281 一致)
- lock_btn(锁定 recipe):`"lock_normal"`(不像 lock)→ 按 e.locked 动态切
  `"plate_locked"` / `"plate_unlocked"`(OrcaSlicer 锁定语义正源,
  PartPlate.cpp:3428 用同一对)。refresh_fulfilment 重建行,图标随状态翻转。

## Fix 4 — 映射变化后切片不失效(用户第二轮指出)

### 根因
fulfillment 专属变化(设备料槽 sync、Match 重 solve、recipe 编辑)**不产生
design-config diff**,所以 Print::apply 的变化检测看不到,`is_slice_result_valid()`
仍 true。用户改了映射后看到切片绿勾(有效),不重切直接点发送 → 发送过时映射。
这也是 Fix 1/2/3 的前置完整性缺口:取色源虽自洽(同一次切片),但那是"过时但自洽"。

### 修法
新增 `Plater::invalidate_slice_for_fulfillment_change()`:遍历所有 plate 调
`update_slice_result_valid_state(false)` + `schedule_background_process()`。
在改变当前 device-space 映射结果的入口调用:
- `Plater.cpp` load_ams_list(设备料槽主动 sync,mark_stale 旁)
- `DeviceFilamentZone.cpp` auto-refresh timer(fingerprint 变化检测)
- `FulfillmentPanel.cpp` on_match(solve 重新算映射)
- `FulfillmentPanel.cpp` apply_edited_recipe(改 recipe 字段:component/ratio/pattern)

### 判断:toggle_lock / clear_all_locks 不调用
这两个操作只改 `locked` 标志(影响下次 solve 的 keep 逻辑),**不改当前已 solve
的 entries 的 recipe 字段**。若 toggle 后不重 Match 直接切片,`prepare_slice_inputs`
的 `has_stale()` 是 false(无人 mark),用现有 entries → device space 不变 → 切片
结果与之前相同。故当前切片仍有效,不需要失效。
(此判断未派对抗 agent 验证,推理直接,记此待 review。若错误则 toggle 后用户改了
锁、直接重切会得到未应用锁定的结果 —— 但这与"切片不失效"无关,是 solve 时机的
另一问题。)

### 数据流
映射变化 → invalidate_slice_for_fulfillment_change → 所有 plate valid=false →
按钮显示 "Slice now" → 用户重切 → prepare_slice_inputs(若 has_stale 则重 solve
用新 snapshot,否则用改过的 entries)→ 新 device-space config 灌入 Print::apply →
fff_print()->config() 更新 → Fix 1/2/3 取色源刷新。

### 【修正】原实现调 schedule_background_process 导致自动重新映射(用户指出)
原实现末尾调了 `p->schedule_background_process()`。这会启动 0.5s 单次 timer
自动触发后台切片 → `update_background_process` → `prepare_slice_inputs` →
若 `has_stale()` 则**自动重新 solve 重新映射**。即:用户一改映射(或设备 timer
检测到变化),系统立刻自动重切 + 重映射,而非等用户手动点 "Slice now"。

**根因**:schedule_background_process 的语义是"调度重切",不是"刷新按钮"。
它和"标失效让按钮变 Slice now"是两件事 —— 前者触发重切(副作用:重新映射),
后者只是 UI 状态。

**修正**:去掉 schedule_background_process,改调
`main_frame->update_slice_print_status(eEventSliceUpdate, true, false)`(纯 UI,
Enable/Disable 按钮,不触发重切)。get_enable_slice_status() 读
is_slice_result_valid()(已 false)→ enable slicing → 按钮显示 "Slice now"。
重新映射留在用户点 "Slice now" 时才发生(prepare_slice_inputs 在真正切片路径)。

**教训(诚实性)**:这是实现 Fix 4 时把"标失效"和"触发重切"两件事混在一起的
典型错误。update_slice_result_valid_state(false) 只改标志不刷 UI,我误以为需要
schedule 来刷 UI,实际 schedule 是重切触发器。正确做法:标失效 + 独立的 UI 刷新
调用(update_slice_print_status),两者解耦。

### 验证
- build EXIT=0,产物(11:10:12)晚于源文件 ✓
- MixedFilament 166 cases 无回归 ✓
- 实机验证:改设备料槽/重 Match/编辑 recipe 后,切片按钮应变 "Slice now"(待实机确认)

---

## Fix 1/2/3 — 取色错位(第一轮,详见下文)

用户观察："这个映射你考虑预打印页了吗？有适配吗" → 核查发现发送页/3MF 写入
完全没适配 fulfillment 的 design→device 重映射。

## 触发的理论缺口

- **单层修复(round-13/22/27 延续)**：前几轮把切片料列表、涂色、design mixed
  definition 的 device-space 对齐做对了,但**没追到预打印/发送页消费者**。
  同一份 device-space id 在发送页继续被错读 —— 典型 "修了 layer N,layer N+1
  还在错"。
- **目标缺口清单命中**：对称性 bug(device id × design palette)+ 单层修复。

## grep journal 结果(Step 1 强制)

- round-27：修 design mixed 进 device space,数据流 hops 表止于 remap_extruder_*
  (切片层),**没列发送页/3MF 写入消费者**。本 bug 是 round-27 hops 表的盲区。
- round-22-plater-audit：审 prepare_slice_inputs / cached_device_palette,
  **没 grep 发送页取色源**。
- 无 round 记录过 SelectMachine / SendMultiMachinePage / export_3mf 的取色 id-space。

## 合法 shape 清单(get_used_extruders 返回值的 id-space)

| Shape | 判别 | UNDERSTOOD? | 方案覆盖? |
|-------|------|-------------|-----------|
| A: 未切片 / 无 gcode result | `get_slice_result()==null` → 空 vec | ✓ | ✓(空 vec,循环不执行) |
| B: gcode.3mf 文件(objects.empty) | `slice_filaments_info[i].id+1`,3MF 读回的 device id | ✓ | ✓(Fix 3 修写入端,读回自动对) |
| C: 实时切片结果 | `total_volumes_per_extruder` key+1,device T-number | ✓ | ✓(Fix 1/2/3) |

## 退化输入×消费者矩阵

| 退化输入＼消费者 | SelectMachine 取色 | SendMulti 取色 | export_3mf 写 color | set_default_from_sdcard 读 |
|---|---|---|---|---|
| 恒等映射(无 fulfillment) | design=device,隐身 | 同 | 同 | 同 |
| 非恒等 + 刚切片 | Fix 1 修(fff_print config) | Fix 2 修 | Fix 3 修 | 依赖 Fix 3 |
| 非恒等 + 切片后改料不重切 | **fff_print config 仍 device** ✓ | 同 ✓ | 同 ✓ | n/a |
| gcode.3mf 文件(未实时切片) | slice_result 为读回的,fff_print config? | 同 | Fix 3 | ✓ |

注："切片后改料不重切" 场景下,对抗 agent B1 担心的 cache valid 窗口问题,
**因为方案改用 fff_print()->config()(Print::apply 灌入,不依赖 cache)而规避**。
这是对抗审查推动的关键设计转向。

## 对抗审查结论(两轮)

### 初版方案(被推翻)
"四处统一改用 `get_extruder_colors_from_plater_config(force_device_palette=true)`"
派对抗 agent 证伪,命中 3 个 [blocker]:

- **[B1] 缓存窗口太窄**：`m_cached_device_palette_valid` 仅在 prepare_slice_inputs
  后 true(Plater.cpp:13228);切片后改设计料不重切(:10335 置 false)→ fallback
  design → bug 复现 + vector::operator[] 越界 UB。
- **[B2] 全局 cache vs per-plate**：m_cached_device_palette 是当前 plate 单份,
  export_3mf 遍历所有 plate 用它会错位。
- **[B3] gcode.3mf 场景**：加载 3MF 不触发实时切片,cache 永远 false。

### 对抗建议(部分被反驳)
对抗建议改用 `slice_filaments_info.color`。我核实 `parse_filament_info`
(bbs_3mf.cpp:639-661)**实时切片后只填 id/used_g/used_m,不填 color** ——
color 只在 export_3mf(:20694)或 3MF 读回(:4384)时填。而 SelectMachine
取色(:3267)在 export_3mf **之前**执行,所以实时切片后直接发送,color 为空。
**对抗建议同样失效。** 唯一可靠源 = `fff_print()->full_print_config()`。

### 修订方案(已实现)
取色源统一为 `get_curr_plate()->fff_print()->full_print_config()`(per-plate、
Print::apply 灌入 device-space、与 G-code T-number 同源、不依赖 cache 窗口)。
同 SSWCP::sw_GetFileFilamentMapping(SSWCP.cpp:3286)的正确路径。

## 数据流 hops 状态(逐跳追踪)

| Hop | 写者→读者 | id-space | 修复后 |
|-----|-----------|----------|--------|
| 1 G-code T-number → total_volumes_per_extruder | GCodeProcessor | device | ✓(不动) |
| 2 → get_used_extruders() | PartPlate.cpp:1681 | device | ✓(不动) |
| 3 → SelectMachine 取色 | Fix 1 → fff_print config | device×device | ✓ |
| 4 → sourceColor 发送载荷(:1140) | m_filaments[k].color | device | ✓(Fix 1 带动) |
| 5 → export_3mf 写 slice_filaments_info | Fix 3 → per-plate fff_print | device×device | ✓ |
| 6 → 3MF 文件持久化 | bbs_3mf writer | device | ✓(Fix 3 带动) |
| 7 → set_default_from_sdcard 读回 | slice_filaments_info.color | device | ✓(Fix 3 带动) |

所有 hop 两端 id-space 一致(device×device)。

## 兄弟字段横向 grep(对抗 [minor] + 自查)

修 colour 时发现同 struct 同循环的兄弟字段同源错位:
- `info.type`(materials[extruder])→ **同修**(device config 重排了 filament_type)
- `info.brand`(brands[extruder])→ **backlog**(filament_vendor 未被 build_device
  _filament_space 重排,需反向映射)
- `info.filament_id`(m_filaments_id[extruder])→ **backlog**(同上,filament_ids
  未重排)
- `it->type` / `it->filament_id`(export_3mf)→ type 同修,filament_id 保持 design
  (supply-chain id,design identity 是正确意图)

brand/filament_id 决策:AMS 映射主要靠 tray_id,brand/filament_id 是 advisory;
修它们需在发送页构建 device→design 反向映射(高耦合)。入 backlog,代码注释标明。

## 变种横向 grep(Step 6 强制)

grep 所有 `get_used_extruders()` 消费者 + `project_config.opt_string("filament_colour")`:
- SelectMachine.cpp:1612(is_same_nozzle_diameters)用 device id 索引 printer
  nozzle_diameter → **不是 bug**(nozzle_diameter 是 printer-space = device physical,
  与 device extruder 同源)。对抗 agent 列为 [major] 是误判。
- PartPlate::get_extruders / ModelVolume::get_extruders → design-space(model 层),
  与 device 无关,正确。
- GUI_ObjectList / PresetComboBoxes / sidebar 图标 → design×design,正确。
- 无第 5 处同型错位。

## 改动文件(3 个)

- `src/slic3r/GUI/SelectMachine.cpp`(Fix 1):reset_and_sync_ams_list 取色源改
  fff_print()->full_print_config();colour+type 用 device 版,brand/filament_id
  保留 design 数组 + 边界保护 + backlog 注释;删 design materials/display_materials 死代码。
- `src/slic3r/GUI/SendMultiMachinePage.cpp`(Fix 2):sync_ams_list 同模式;注释标明
  info.color 硬编码(:1456 "#CECECEFF")限制(发送载荷不带真色,只修视觉)。
- `src/slic3r/GUI/Plater.cpp`(Fix 3):export_3mf 遍历 plate 时取 per-plate
  fff_print()->full_print_config() 给 slice_filaments_info 上色/类型;filament_id
  保持 design cfg;删未使用的 filament_color design 变量。

## 测试证据

- build Snapmaker_Orca 可执行 target:EXIT=0,产物(10:06:52)晚于三源文件
  (10:05:38-10:06:04),确认重链接 ✓
- MixedFilament 全套 166 cases:164 passed + 2 failed-as-expected(与 round-27
  基线一致)✓ 无回归
- libslic3r_tests 全量:3 failed(test_3mf.cpp:128, test_config.cpp:22/29/68)
  → 这些测 libslic3r 核心库,我的改动全在 src/slic3r/GUI/,无代码路径关联,
  属环境预先存在的失败(headless SIGSEGV)。

## E2E 证据(限制说明)

- **无法在 CI/headless 验证发送页取色**:SelectMachine/SendMultiMachine 是
  wx GUI 对话框,需要 GUI 上下文 + 真实 fulfillment solve + 实机空槽配置。
  数据流逐跳追踪 + 编译通过 + 回归无破坏 是当前能给的保证。
- **遗留**:应加端到端测试(构造 fulfillment solve + 空槽 + slice + 验证
  SelectMachine m_filaments.color 与 device 槽色一致),但需 GUI 测试 target
  (当前 libslic3r_tests 不链 GUI)。记 backlog。

## 过程意外 / 与预期偏差

- **对抗 agent 的 Fix 1 建议也错**:它建议用 slice_filaments_info.color,但
  我核实 parse_filament_info 实时切片不填 color。对抗只攻 known unknowns,
  它和我都没第一时间意识到 color 填充时机问题 —— 靠一手源核实(bbs_3mf.cpp:639)
  才发现。印证 skill 的 "agent A 带数字、很自信,应该对" 教训。
- **get_filament_type 不是 const**:Print::config() 返回 const PrintConfig&,
  调 get_filament_type 编译失败。改用 full_print_config()(返回 const
  DynamicPrintConfig&)仍失败(get_filament_type 非 const 方法)。最终改用直接
  读 filament_type option,放弃 support 耗材特殊命名分支(device config 下
  filament_is_support 未重排,该分支本就不可靠)。
- **brand/filament_id 是 build_device_filament_space 的字段重排盲区**:它只
  重排 filament_colour/type/diameter(FulfillmentSliceMapping.cpp:510-526),
  漏了 filament_vendor/filament_ids。这是 round-27 Pass 2.5 之外又一个
  "build_device_filament_space 没全覆盖字段" 的同类问题。

## 遗留 backlog

- **brand / filament_id 反向映射**:发送页 info.brand / info.filament_id 仍用
  device id 索引 design 数组。修需在发送页访问 device→design 反向映射(缓存
  design_to_device 或重调 build_device_filament_space)。优先级:低(AMS 靠
  tray_id,brand/filament_id advisory)。
- **build_device_filament_space 字段重排完整性**:应一并重排 filament_vendor /
  filament_ids(若 device 语义需要),或在 hpp 注释明确"仅 colour/type/diameter
  重排,其余字段保持 design"。
- **SendMultiMachinePage:1456 info.color 硬编码**:该页发送载荷不带真色,是
  独立功能缺口(与 SelectMachine 的真色发送不同),不在本 bug 范围。
- **端到端 GUI 测试**:构造 fulfillment solve + 空槽 + slice + 验证发送页取色。

## Fix 5 — 预打印页上方色块用 design 色(filament_multi_colors 未重排)

### 根因(经探针定位)
`sw_GetFileFilamentMapping` 传给 Flutter 的 `filament_color` / `filament_color_rgba`
是 device 色(已对),但预打印页**上方那排带 PLA 文字的色块**用的是
`filament_color_multi` 字段,而该字段基于 `filament_multi_colors` 构建。
`build_device_filament_space` Pass 3 只重排了 filament_colour / filament_type /
filament_diameter,**漏了 filament_multi_colors / filament_colour_mode** —— 它们
在 set_num_extruders resize 后仍保持 design-index 顺序,与已重排的 filament_colour
错位 → Flutter 上方色块显示 design 色。

### 定位过程(探针法,非纯推理)
1. 第一探针:`filament_color` 改 #FF0000 → **下方耗材列表变红,上方不变**。
   证明上方用别的字段。
2. 日志确认:`filament_color`(device #56B7E6)≠ `filament_multi_colors`(design
   #1E88E5 #F4C032 #00C1AE #F4E2C1)。后者正是 design 原色。
3. 第二探针:`filament_color_multi` 改 #FF0000 → **上方变红**。确认上方用 multi。
4. 修复 build_device_filament_space Pass 5 重排 multi_colors/mode。

教训:本轮反复在 Flutter 黑盒旁打转(找 bridge、查 MQTT),浪费多轮。两个探针
(#FF0000 标记法)各一次就定位了"下方用 filament_color / 上方用
filament_color_multi"。**面对黑盒渲染,探针标记法 >> 静态代码分析。**

### 修法(build_device_filament_space Pass 5)
**初版(被推翻)**:用 design_to_device 反向映射,把 design extruder d 的
multi_colors 搬到 device slot。用户指出这是错的——上方该显示设备槽实际装的
设备耗材,不是搬 design 的多色。
**修订(已实现)**:直接清空 device config 的 filament_multi_colors /
filament_colour_mode(每个 device slot 置空/mode=0)。Pass 3 已经用设备数据
(rows[].color_hex / rows[].type)填了 filament_colour / filament_type,所以
multi_colors 清空后,BuildPreprintColorMultiItem(SSWCP.cpp)走 fallback:
FromColors 空数组 → 用 fallbackColor = filament_color[t](设备色)填单个色。
上方色块于是显示 device filament_colour = 设备色。
不搬 design multi_colors 的原因:PhysicalSlot 只有单色,无多色 tray 数据;
design 的 multi_colors 描述的是 DESIGN 层 tray,device slot 未必装它,搬过去
会重新引入 design 色泄漏。

### id-space 核实(初版遗留,记录 1-based 约定供后续参考)
- component_device_id :264 `return row_device_index(...) + 1` → 1-based
- design_to_device 存 1-based device id
- 消费端 Plater.cpp:13164 `state_map[v] = device_id` 当 1-based extruder 用

### 兄弟字段回顾(横向 grep)
build_device_filament_space 现在重排的字段:filament_colour / filament_type /
filament_diameter(Pass 3)+ filament_multi_colors / filament_colour_mode(Pass 5)。
仍保持 design 顺序的:filament_vendor / filament_ids(round-28 backlog,需反向映射)。

### backlog 更新
- **build_device_filament_space 字段重排完整性**:filament_multi_colors/mode
  本轮补上。剩余 filament_vendor / filament_ids 仍 design 顺序(SendMulti 的
  brand/filament_id backlog)。应在 hpp 注释明确字段重排范围。
