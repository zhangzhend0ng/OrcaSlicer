# Round 27 — design-layer 混合耗材在 fulfillment 映射中丢失（shape 遗漏）

用户观察："混色除了涂色区域的，设置了耗材丝的没适配这个映射吧？"

## 触发的理论缺口

- **合法状态空间未枚举**（Step 0）：model volume/object/layer-range 的 extruder 字段
  可以指向 design-layer mixed/virtual extruder（> num_design_physical），这个 shape
  从未被 fulfillment 枚举过。
- **round-13 单层修复** + **round-22 假满分**：round-13 修了 mixed_filament_definitions
  字符串擦除，但对抗 re-check 漏了"volume.extruder 指向 mixed"的 shape；round-22 标
  remap_extruder_field ✓ 但只验证"不越界 clamp"，没验证"mixed 定义不丢失"。

## grep journal 结果（Step 1 强制）

- round-13.md：修了 empty synth 擦除 design mixed string，加了 enabled_count()>0 守卫。
  对抗 re-check 覆盖 3 shape（no synth / synth added / empty mgr），**漏第 4 shape**：
  synth added 且 model volume.extruder 指向 design-layer mixed（非 fulfillment synth）。
- round-22-plater-audit.md:17：remap_extruder_field "mapped > num_total clamp 到 1 | ✓"。
  这个 ✓ 是范围限定性盲区——只验证不越界，没验证语义保留。

## 合法 shape 清单（model 对 extruder 的引用）

| Shape | 判别字段 | UNDERSTOOD? | fulfillment 覆盖? |
|-------|----------|-------------|-------------------|
| A: volume.extruder 指向物理 design extruder (1..N) | e ≤ num_design_physical | ✓ | ✓（design_to_device + remap） |
| B: volume.extruder 指向 design mixed/virtual (> N) | e > num_design_physical | ✓（本轮新理解） | **✗ 未覆盖** |
| C: volume.extruder = 0 (default) | e == 0 | ✓ | ✓（remap 跳过） |
| D: painting 三角面指向 virtual | painted state > num_total | ✓ | **✗ 同型 bug**（state→NONE） |

## 退化输入×消费者矩阵

| 退化输入＼消费者 | design_to_device | state_map | remap_extruder_field | remap_extruder_ids(painting) | num_total | mixed_filament_definitions |
|---|---|---|---|---|---|---|
| volume.extruder=virtual, 无 synth (Case A) | size 不含 virtual | identity | clamp 到 1 | n/a | 不含 virtual | 保留(round-13)但 dormant |
| volume.extruder=virtual, 有 synth (Case B) | size 不含 virtual | identity | clamp 或错位 | n/a | 含 synth virtual | 被 fulfillment 覆盖 |
| painting 指向 virtual | n/a | identity | n/a | state→NONE 丢失 | 不含 virtual | n/a |
| design mixed component 指向 Unmet extruder | component 映射失败 | n/a | fallback 到 1 | n/a | n/a | 该 mixed 行丢失 |

## 对抗审查结论（两轮）

### 第一轮（确认 bug 成立）
逐行核实 5 步前提全部成立，shape 经 UI 核实可达（extruder 下拉含 mixed 图标，
include_mixed=true 默认）。实际影响比初判更广：Case A（最常见）是 round-13 单层修复
的直接证据。

### 第二轮（证伪修复方案）
方向对（移植 design mixed 到 device space），但实现规格不完整，2 blocker + 4 major：

**[blocker-1]** mgr 操作 API：不能用 load_custom_entries（rebuild 会清空 fulfillment synth 行），
必须把 design mixed 也构造成 MixedFilamentBatchEntry 用 add_batch_custom_filaments 加到同一个 mgr。

**[blocker-2]** mapping 函数：不能复用 entry-bound 的 component_device_id（它是 recipe-palette-local），
必须新建 design_physical_to_device(j)（design extruder j → device filament id 通用查表），
manual_pattern / gradient_component_ids 的重映射都依赖它。

**[major-1]** 循环依赖是伪问题：Pass 2.5 只需 Pass 1 的 component_device_id lambda（direct 分支
不依赖 assigned_ids），不需把整个 Pass 4 提前。

**[major-2]** design_to_device size 要扩到 num_design_physical + num_design_virtual，
num_design_virtual 从 design mixed string 解析 enabled+custom+!deleted 行数得到。

**[major-3]** design-mixed 与 fulfillment-synth 在同一 mgr 里的相对顺序必须固定，
否则 virtual id 错位。约定：design-mixed 追加在 synth 之后（同一 batch_entries vector）。

**[major-4]** Unmet component 时跳过 design mixed = 静默丢 mixed（Case A 下和原 bug 同形，
走 fallback 而非 clamp）。需显式日志。

## 修订方案（已实现）

在 build_device_filament_space 加 **Pass 2.5：移植 design-layer mixed 到 device space**。
按对抗二轮的修正实现（避开 2 blocker + 4 major）：

1. **`design_physical_to_device(j)` lambda**（FulfillmentSliceMapping.cpp Pass 1 之后）：
   对 design extruder j（1-based），找 entries 里 design_extruder==j-1 的 entry，
   返回 component_device_id(e, e.recipe.component_a)。Unmet/invalid → 0。
   —— 对抗 [blocker-2] 要求的通用映射函数，不复用 entry-bound component_device_id。

2. 读 design_full_config.has("mixed_filament_definitions") + opt_string。
   用 design colours（不是 device colours）load 到临时 design_mgr——对抗 [major-2] 指出
   用 device colours 会让 load_custom_entries 拒绝 design-space id > device num_physical 的行。

3. 遍历 design_mgr 的 enabled && custom && !deleted 行，重映射 component_a/b /
   gradient_component_ids / manual_pattern（用 design_physical_to_device）。
   重映射失败的行跳过（Unmet component → any_unmapped_component_seen + 日志）——
   对抗 [major-4]。

4. 成功的行转成 MixedFilamentBatchEntry **追加到同一个 batch_entries**（在 fulfillment synth
   之后），记录 design virtual id → batch position。add_batch 一次性处理两类行——
   对抗 [blocker-1] 要求（不能用 load_custom_entries，它会 rebuild 清空 synth 行）。

5. **design_to_device size 扩展**（Pass 4）：design_virtual_max = max(max_design_extruder,
   design_mixed_map 的 virtual id)。design_to_device.assign(design_virtual_max + 1, 0)。

6. **Pass 4 追加 design mixed 映射**：for (dm : design_mixed_map)
   set_map(dm.first, assigned_ids[dm.second])。

Plater 消费端无需改：state_map 循环 for (design_id < design_to_device.size()) 自动遍历到
扩展区，state_map[virtual] = device virtual（不再 identity），num_total 含 virtual（不 clamp）。
remap_extruder_field（volume）和 remap_extruder_ids（painting）都自动正确。

## 测试证据

- build Snapmaker_Orca + libslic3r_tests：成功（10/10 + tests linking）✓
- 二进制 (02:43:43) 晚于源文件 (02:43:09)，确认重链接 ✓
- MixedFilament 全套 166 cases（164 + 2 failed-as-expected），无回归 ✓
- build_best_color_match_recipe 在 GUI 层（依赖 wxColour），无法直接单测 design mixed
  porting 行为。靠回归测试无破坏 + 数据流逐跳追踪间接保证。
  **遗留**：应加一个端到端测试（构造 design mixed + volume.extruder=virtual + slice），
  但需要 GUI 测试 target（当前 libslic3r_tests 不链 GUI）。记 backlog。

## 改动文件

- `src/slic3r/GUI/Fulfillment/FulfillmentSliceMapping.cpp`：
  - 加 design_physical_to_device lambda（Pass 1 后）
  - 加 Pass 2.5（design mixed 解析 + 重映射 + 转 BatchEntry 追加）
  - 改 Pass 4（design_to_device size 扩展 + 追加 design mixed 映射）

## 数据流 hops 状态（修复后预期）

| Hop | 写者→读者 | 状态（修复后） |
|-----|-----------|----------------|
| 1 design mixed string → 临时 mgr load | Pass 2.5 step 3 | ✓ |
| 2 design mixed component → design_physical_to_device 重映射 | Pass 2.5 step 4 | ✓ |
| 3 重映射后的 BatchEntry → 主 mgr add_batch | Pass 2.5 step 5 | ✓ |
| 4 assigned_ids → design_to_device[virtual] | Pass 2.5 step 6 | ✓ |
| 5 design_to_device size 扩展 | Pass 2.5 step 7 | ✓ |
| 6 prepare_slice_inputs state_map[virtual] | Plater（无需改） | ✓ |
| 7 remap_extruder_field(volume.extruder=virtual) | Plater（无需改） | ✓ |
| 8 remap_extruder_ids(painting virtual) | Plater（无需改） | ✓（同型 bug 自动修） |

## 过程意外 / 与预期偏差

- **Case A 比预想更常见**：不需要 fulfillment 产生 synth row，只要用户有 design mixed +
  volume 指向它，就触发。round-13 的守卫保护了字符串，但 num_total 不含 virtual 导致 clamp。
- **painting 同型 bug**：三角面 painted virtual → state NONE（比 volume clamp-to-1 更彻底丢失）。
  修复 design_to_device 后自动解决（state_map[virtual] 不再 identity）。
- **两轮对抗的互补**：第一轮确认 bug 成立 + shape 可达；第二轮证伪修复方案抓到 2 blocker。
  没有第二轮，实现会踩 load_custom 清空 synth + component_device_id 用错函数两个坑。
- **round-13 的假满分根源**：它修了 producer（mixed_filament_definitions 字符串），但对抗
  re-check 没追 consumer（num_total / remap / volume.extruder 引用）。典型单层修复。

## 遗留 backlog

- **实现 Pass 2.5**：方案已设计完（上面 8 步），用户已确认方向。待实现 + 测试。
  这是个 ~80-100 行的新代码 + design_to_device size 逻辑改动。
- **退化输入的 UI 提示**：Unmet component 导致 design mixed 跳过时，目前只日志。
  未来可考虑在 fulfillment UI 提示"design mixed row X 丢失，因 component Y 在 device 不可用"。
