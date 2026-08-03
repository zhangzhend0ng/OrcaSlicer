# Round 29 — 工作区改动审计(round-28 未提交改动)

**范围**:`git diff HEAD`(10 文件,+314/-61),对应 round-28 文档描述的 5 个 Fix +
图标修正 + 图例重排。上一 commit 为 round-27(da82e67),本轮改动**尚未提交**。
**审查方法论**:harness-driven review(B1→B6),harness 选取在阅码前完成。

## 总评

**APPROVE with comments**。无 (N)-tier 违规。改动方向正确、边界保护到位、
注释质量高(标明 id-space、backlog、MUST-stay-in-sync)。两个未在 round-28
文档中记录的改动已核实安全。发现 1 个 (C)-tier(文档缺口,非阻塞)+ 若干 (A)。

## 已应用的 Harness

| Harness | Tier | 结论 |
|---|---|---|
| cpp-undefined-behavior | N | PASS(详见下) |
| cpp-correctness/type-safety | N | PASS |
| common/code-review/review-checklist | C | PASS(含注释) |
| cpp/functions/parameter-validation | C | PASS |

---

## 一、UB Harness(cpp-undefined-behavior)—— 逐项

### Item 2 Null 解引用 — 关键核实点

新代码 3 处 `fff_print()->full_print_config()` 双层解引用无显式 null 检查:
- `Plater.cpp:20742` `plate->fff_print()->...`(`export_3mf`,plate 来自
  `get_plate(i)` 可能返回 NULL)
- `SelectMachine.cpp:3278` `curr_plate->fff_print()->...`
- `SendMultiMachinePage.cpp:1411` `curr_plate->fff_print()->...`

**核实**:
- `PartPlate::fff_print()` 返回 `Print*`(`m_print` 在构造函数初始化为 nullptr,
  PartPlate.cpp:193;仅 set_print 时赋值,:1990)。
- `get_plate(i)` 当 `index >= size` 返回 NULL(PartPlate.cpp:3982)。

**判定:PASS(沿用既有约定,非本轮引入)**。
- round-28 文档引为"正确取色源"的 SSWCP.cpp:3406
  `cur_plate->fff_print()->config()` 用的是**完全相同的无保护模式** ——
  这是 codebase 既定约定(`m_print` 视为 plate 创建后恒非空)。
- round-22 的 Plater audit 已走过这条路;本轮新代码与 SSWCP 同模式,未降低
  既有保护水平。
- **(A) 建议**(非本轮必做):`export_3mf` 的 plate 循环边界是
  `plate_data_list.size()`,与 `m_plate_list.size()` 无编译期绑定 —— 若两者
  失同步,`get_plate(i)` 返回 NULL。加一行
  `if (!plate) continue;` 是零成本的纵深防御,可入 backlog。

### Item 3 越界访问 — 边界保护审计

| 位置 | 索引 | 保护 | 判定 |
|---|---|---|---|
| SelectMachine.cpp:3292 | `extruder` 索引 `dev_colours` | `extruder>=0 && extruder<size` + fallback | PASS |
| SelectMachine.cpp:3353 | `extruder` 索引 `dev_materials` | `extruder<size` 三处分别守 | PASS(冗余但安全) |
| SendMultiMachinePage.cpp:1422 | 同上 | 同上 | PASS |
| GCodeViewer.cpp:5068 | `m_tools.m_tool_colors[extruder_id]` | **见下专项** | PASS |
| Plater.cpp:22445 | `ams_slot_by_t[extruder_id]` | `extruder_id>=size \|\| <0` 双守 | PASS |

**GCodeViewer 越界专项**(本轮最需证伪的风险):
改动把 3 处 `get_extruder_colors_from_plater_config(include_mixed=**true→false**)`
(GCodeViewer.cpp:4077/5038、GUI_Preview.cpp:588/724)。`include_mixed=false`
使返回的 palette 长度 = num_physical(不含虚拟色)。若 G-code 含虚拟 T 号
(>= num_physical),`m_tools.m_tool_colors[extruder_id]` 越界。

**证伪(经 Explore agent 逐跳追踪)**:
- `build_device_filament_space` 对所有 per-extruder 数组调
  `set_num_extruders(num_physical)`(FulfillmentSliceMapping.cpp:507),虚拟行
  **只**进 `mixed_filament_definitions` 字符串(:542)与
  `virtual_display_colors`(:584),**不**进 G-code T 号空间。
- T 命令来自 `LayerTools.extruders`,每条经 `ToolOrdering::resolve_mixed` →
  `MixedFilamentManager::resolve` 解析为物理 component id ∈ [1,num_physical]
  (MixedFilament.cpp:2522-2592)。G-code 只发 `T0..T(num_physical-1)`。
- `GCodeProcessor::process_T` 对 `new_extruder >= extruders_count` 报错并丢弃
  (GCodeProcessor.cpp:3990-3991);`extruders_count = filament_diameter.size()
  = num_physical`。
- `m_tools.m_tool_colors` sized 到 `extruders_count`(GCodeViewer.cpp:1123)。
- 故 `m_extruder_ids` 永不含 >= num_physical 的值,`include_mixed=false` 截断
  **不**致越界。

**判定:PASS**。但这 3 处 `include_mixed` 改动**未在 round-28 文档任何位置
记录** —— 见下 (C) 文档缺口。

### Item 1/4/5/6/7/8/9/10
- 整数算术:无溢出风险(全为 size_t 索引比较)。PASS
- 生命周期:`auto& plate_dev_cfg` 绑定 plate 内成员,plate 生命周期覆盖循环。PASS
- 数据竞争:均在 UI 线程。N/A
- strict aliasing:`dynamic_cast`/`option<T>` 合规。PASS
- 返回局部引用:无。N/A

---

## 二、类型安全 Harness(type-safety)

- `get_ams_ordered_extruder_ids` 返回 `vector<unsigned int>`,消费端
  `static_cast<unsigned int>` 显式。PASS
- `extruder_id_to_ams_slot(unsigned int)` 返回 unsigned,消费端 `label_id + 1`
  无符号回绕风险(label 为 0-based slot,+1 显示)。PASS
- `m_extruder_ids` 为 `vector<unsigned char>`,`get_ams_ordered_extruder_ids`
  入参 `const vector<unsigned char>&` —— 类型匹配。PASS

---

## 三、round-28 文档未覆盖的改动(C-tier,需补文档)

### 1. 三处 `include_mixed: true → false`(未记录)

GCodeViewer.cpp:4077、5038;GUI_Preview.cpp:588、724。round-28 文档的
Fix 清单(Fix 1/2/3/4/5 + 图标 + 图例重排)**均未提及**这 4 处改动。

- **意图推测**:G-code 预览/图层滑块的 palette 应与 G-code 实际 T 号空间
  (num_physical)一致,而非混入虚拟展示色 —— 与本轮"device-space 对齐"主线
  一致。`include_mixed=true` 会在 palette 末尾追加虚拟色,使 legend 显示
  不存在于 G-code 的"幽灵挤出机"。
- **已核实安全**(见上 UB Item 3 专项)。
- **为何标 (C)**:未在文档中说明动机与安全论证,未来 reviewer 无法判断这是
  有意决策还是手滑。**建议补一行注释或文档条目**:这三处为何取 false。

### 2. 图例重排循环的 `break` vs `continue` 不一致(A-tier)

- Tool view(GCodeViewer.cpp:5064):越界守卫用 `break`(退出整个循环)
- ColorPrint view(:5101):越界守卫用 `continue` 包裹(跳过该项)

实际均为死路径(`get_ams_ordered_extruder_ids` 只返回 `used_t_ids` 成员,内层
find 必命中),但语义不一致。**建议统一为 continue**(更稳健:单个项异常不应
中断整个 legend)。

---

## 四、设计正确性核实(非 harness 项,但关键)

### Fix 4(invalidate_slice_for_fulfillment_change)—— 核心设计点

round-28 文档详细记录了"原实现误调 schedule_background_process 致自动重切"
的教训及修正(改用 `update_slice_print_status` 纯 UI)。代码(Plater.cpp:22529)
与文档一致:**不**调 schedule_background_process,只标 valid=false + 刷按钮。

**调用点覆盖核实**(4 处,与文档一致):
- Sidebar::load_ams_list(Plater.cpp:8744)—— 设备料槽主动 sync ✓
- DeviceFilamentZone::on_timer(DeviceFilamentZone.cpp:142)—— fingerprint 变化 ✓
- FulfillmentPanel::on_match(FulfillmentPanel.cpp:175)—— 重 solve ✓
- FulfillmentPanel recipe 编辑 lambda(FulfillmentPanel.cpp:532)—— 改 recipe ✓

**toggle_lock/clear_all_locks 不调用** —— 文档已论证(只改 locked 标志,不改
当前 entries recipe 字段,device space 不变)。逻辑成立。**但**:文档自承
"此判断未派对抗 agent 验证"。我核实:toggle 后用户若直接重切,
`prepare_slice_inputs` 的 has_stale() 为 false → 用现有 entries → device space
确实不变 → 当前切片有效,不失效是**正确**的。锁定在下次 solve 才生效。
**PASS**(文档推理正确)。

### ams_slot_by_t 反向映射构建(Plater.cpp:13242-13260)

- 数据源 `build_machine_filament_list`:`fd.m_index`=bay(料位),
  `fd.m_extruder`=T 号(Plater.cpp:543-546,590-591 mock 路径一致)。反转
  `ams_slot_by_t[m_extruder] = m_index` 语义正确。
- `any_swap` 门控:恒等映射时返回空 vector,消费端回退 T 号序 —— 与
  extruder_id_to_ams_slot 的 fallback(return extruder_id)自洽。PASS
- **(A) 隐患**:若两个 bay 报告同一 T 号,后者静默覆盖前者(无检测)。
  当前设备拓扑下 unlikely(physical_extruder 应唯一),但无断言。可加一行
  `assert(ams_slot_by_t[fd.m_extruder] == -1)` 防御,入 backlog。

### Fix 5(multi_colors 清空)—— 设计转折核实

round-28 文档记录"初版被推翻(搬 design multi_colors)→ 修订(清空)"。
代码(FulfillmentSliceMapping.cpp:586-606)与修订方案一致:每 slot 清空
multi_colors + mode=0,依赖 BuildPreprintColorMultiItem fallback 到
filament_colour[t](设备色)。PASS。注释清晰说明为何不搬 design 色。

---

## 五、过程质量(诚实性)

- round-28 文档的"教训"段(schedule vs UI 刷新解耦、探针法定位 Flutter 黑盒、
  对抗 agent 的 color 填充时机误判)记录诚实,无粉饰。
- brand/filament_id backlog 与 build_device_filament_space 字段重排盲区均
  明确标注 KNOWN LIMITATION + 边界保护(无越界)。诚实。
- 唯一缺口:`include_mixed` 改动未记录(见 §三.1)。

## 六、构建证据

- 产物 `build/arm64/.../Snapmaker_Orca`(Aug 3 14:14:59)晚于最晚源文件
  (Plater.cpp/GCodeViewer.cpp 14:10:23)→ **重链接覆盖本轮全部改动** ✓
- 未跑回归测试(本轮为审计,非改动);round-28 文档载 MixedFilament 166
  cases 无回归。

---

## 七、Verdict

**APPROVE with comments**。可提交。建议提交前补:
1. **(C)** 三处 `include_mixed=false` 加一行动机注释(为何预览不含 mixed 色)。
2. **(A)** 图例重排两处越界守卫 `break`→`continue` 统一(死路径,稳健性)。
3. **(A)** backlog:export_3mf plate 循环加 `if(!plate) continue;`;
   ams_slot_by_t 重复 T 号断言。

均非阻塞。改动本身的边界保护、id-space 注释、backlog 标注质量高,符合本仓
AGENTS.md 的"复用前先证伪"与"MUST stay in sync"规范。
