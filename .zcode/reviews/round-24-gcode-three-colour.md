# Round 24 — 映射三色混色切出来只有两色（gcode 输出层）

用户报告："映射的混色切出来的 gcode 和原设计混色不一样，三色混色切出来只有两色了"。
R2 元规则触发：这是 round-21/22/23/cee9f79/766ca2e 之后**同类 bug 第 N 次报告**，
说明前面的修复各自只覆盖了一个层（SliceMapping id-space / Plater touch points / UI 文字 /
cycle slice / cycle UI），漏了 gcode 输出层。

## 触发的理论缺口

- **配置卫生 — 键完全缺失**：`MixedColorMatchRecipeResult`（bespoke 弱投影）缺
  `distribution_mode`/`gradient_enabled`/`gradient_start`/`gradient_end`/`ui_mode` 字段。
  AGENTS.md "Reuse Before You Build" 第 1 条明确警告过这种 anti-pattern 会
  "silently drop gradient/pattern fields"，现在精确兑现。
- **单层修复**：round-21 修了 Pass 1（收集三色 ids）+ Pass 2（重映射 id-space），
  但漏了 distribution_mode hop（resolve consume 层），导致 resolve() 仍走二色。

## grep journal 结果（Step 1 强制）

- round-21.md：修了 SliceMapping Pass 1/2 的 id-space，**但对抗验证写
  "3-colour mix: Third colour preserved. ✓" 是假满分**——只验证数据进数组，没验证
  resolve() 是否真的取第三色。
- round-22-plater-audit.md：审了 Plater 所有 touch point，结论"无需改动"——
  但没追到 gcode 生成路径（resolve()），漏了 hop 4。
- round-23-ui-text.md：修了 UI plan 文字渲染三色，但 gcode 路径仍 broken。
- cee9f79/766ca2e：修了 cycle mode (shape D/E) 的 slice + UI，但 RATIO/MATCH 三色
  (shape C/D) 的 distribution_mode hop 仍未覆盖。

## 合法 shape 清单 + 覆盖状态（Step 0 产出）

producer = `MixedFilamentDialog::collect_result` 的 5 个 mode 分支 + solver 的
`build_best_color_match_recipe` / `build_multi_color_match_candidate`。

| Shape | mode / 来源 | distribution_mode | manual_pattern | gradient_component_ids | weights | gradient_enabled | round-24 覆盖? |
|-------|-------------|-------------------|----------------|------------------------|---------|------------------|----------------|
| A: Direct | solver direct | (n/a) | — | — | — | — | n/a |
| B: 2-colour | RATIO 2-row / MATCH 2-w / solver pair | Simple | 空 | 空 或 {a,b} | 空 | false | ✓ 默认 Simple 安全 |
| C: 3-colour RATIO | dialog RATIO 3-row | **LayerCycle** | 空 | 3 ids | "w0/w1/w2" | false | ✓ 修复 |
| D: 3-colour MATCH | dialog MATCH 3-w (all>0) | **LayerCycle** | 空 | ≥3 ids | "w0/w1/w2" | false | ✓ 修复 |
| E: CYCLE | dialog CYCLE | Simple | pattern | 空 | 空 | false | (round cee9f79 修) |
| F: Z-GRADIENT | dialog GRADIENT | LayerCycle | 空 | 空 | 空 | **true** | ✓ 修复（gradient_enabled 透传） |
| G: 3-colour solver | build_best_color_match_recipe triple search | (前漏，现 LayerCycle) | 空 | 3 ids | "w0/w1/w2" | false | ✓ 修复 |
| H: 3-colour solver preset | build_multi_color_match_candidate | (前漏，现 LayerCycle) | 空 | ≥3 ids | weights | false | ✓ 修复 |

## 退化输入×消费者矩阵（Step 0 产出）

| 退化输入＼消费者 | SliceMapping Pass1 | SliceMapping Pass2 | resolve() gcode | UI plan text | display_color |
|---|---|---|---|---|---|
| recipe.distribution_mode 丢失(原状) | n/a | ✗ 硬编码 Simple | ✗ 跳三色分支→2色 | (round-23) | ✗ heuristic 推断 |
| distribution_mode=LayerCycle + 空 ids | n/a | ✓ 透传 | ✓ size<3 跳过→二色(安全降级，无 UB) | ✓ | ✓ |
| distribution_mode=Simple + 3 ids (Shape B 边界) | n/a | ✓ 透传 | ✓ 跳三色→二色(正确，Shape B 语义) | ✓ | ✓ |
| MODE_MATCH 2-colour {a,b} + Simple | n/a | ✓ 透传 | ✓ 二色(正确) | ✓ | ✓ 修了 heuristic 误判 |

## 初版方案（被推翻点）

初版只改 4 处（recipe 加 distribution_mode / apply_edited_recipe 加参数 /
SliceMapping 透传 / FulfillmentPanel 调用）。对抗子 agent 抓到：
- [blocker] B1：还缺 gradient_enabled/start/end（Shape F Z-gradient 完全失效）
- [major] M5：seed 构造（FulfillmentPanel:493-499）漏 distribution_mode，二次编辑 mode 错乱
- [major] M2：bespoke 弱投影 anti-pattern，应一次性补全字段
- [major] M3：display_color 路径靠 heuristic 推断，应改用真字段

## 对抗审查结论（[blocker]/[major] 清单）

见上"初版方案被推翻点"。对抗 agent 用 file:line 逐行核实每个前提，确认：
- (a) resolve() 真被 gcode 路径调用（GCode.cpp:4288 → resolve_perimeter → resolve）
- (b) 退化输入无 UB（LayerCycle + 空 ids 安全落到二色）
- (g) load_custom_entries（3MF 路径）独立 OK，fulfillment store 是独立 bug

## 修订方案（逐条 采纳/反驳/backlog）

- **采纳 B1**：recipe 加 gradient_enabled/gradient_start/gradient_end/ui_mode 字段。
- **采纳 M5**：seed 构造（读方向）+ apply_edited_recipe（写方向）双向对称。
- **采纳 M2**：一次性补全 gcode-relevant 字段，不逐字段打补丁。
- **采纳 M3**：display_color 路径改用 recipe.distribution_mode，去掉 heuristic。
- **横向 grep 新发现**（对抗 agent 没覆盖，我做 Step 4d 时抓到）：
  - `build_best_color_match_recipe` 的 coarse + fine triple search 两处独立写
    3 色 recipe 但漏 distribution_mode（solver 自动匹配三色路径）→ 一并修。
  - `build_multi_color_match_candidate`（solver preset 路径）同样漏 → 一并修。
  - `Plater.cpp:3020` design-layer "Add Mix" 按钮用同样 heuristic → 一并修。
  - `compute_color_match_recipe_display_color` (MixedColorMatchHelpers.cpp:742)
    用 heuristic 推断 → 改用 recipe.distribution_mode。

## 数据流 hops 状态（本轮跨层改动）

| Hop | 写者→读者 | 字段 | id-space/编码 | round-24 前 | round-24 后 |
|-----|-----------|------|---------------|-------------|-------------|
| 1 | dialog collect_result → m_result | distribution_mode | enum int | ✓ dialog 设 LayerCycle | ✓ 不变 |
| 2 | FulfillmentPanel GetResult → apply_edited_recipe | distribution_mode | — | ✗ **字段丢弃** | ✓ 透传 |
| 3 | apply_edited_recipe → e.recipe | distribution_mode | — | ✗ recipe struct 无字段 | ✓ 加字段+写入 |
| 4 | build_device_filament_space → be (BatchEntry) | distribution_mode | — | ✗ 硬编码 Simple | ✓ 透传 recipe.distribution_mode |
| 5 | add_batch_custom_filaments → mf | distribution_mode | — | ✓ (be.distribution_mode) | ✓ 不变 |
| 6 | resolve() (gcode 出口) | distribution_mode | — | ✗ 因 Simple 跳三色分支 | ✓ LayerCycle 进三色分支 |
| 7 (read) | e.recipe → seed → dialog 构造 | distribution_mode | — | ✗ seed 不读，mode 错乱 | ✓ seed 读出，mode 正确恢复 |
| 8 (solver) | build_best_color_match_recipe triple | distribution_mode | — | ✗ 漏设 | ✓ 设 LayerCycle |
| 9 (solver) | build_multi_color_match_candidate | distribution_mode | — | ✗ 漏设 | ✓ 设 LayerCycle |
| 10 (display) | compute_color_match_recipe_display_color | distribution_mode | — | ✗ heuristic 推断 | ✓ 用 recipe 真值 |

任一 hop ✗ 即 fix 不完整。本轮 10 跳全 ✓（除 hop 1/5 是本来就对的）。

## 变种横向 grep 结果（Step 6 强制）

- 同 struct 兄弟字段：`MixedColorMatchRecipeResult` 的 gradient_enabled/start/end/ui_mode
  全部缺失 → 一并补全。
- 同 pipeline 兄弟模块：grep 所有写 recipe 的 producer，发现
  `build_best_color_match_recipe`（coarse + fine triple）+ `build_multi_color_match_candidate`
  两个 solver producer 也漏 distribution_mode → 一并修。
- 同 heuristic workaround：`compute_color_match_recipe_display_color` + `Plater.cpp:3020`
  两处用 `gradient_component_ids.empty() ? Simple : LayerCycle` 启发式 → 改用真字段。

## 改动文件

1. `src/slic3r/GUI/MixedColorMatchHelpers.hpp` —
   `MixedColorMatchRecipeResult` 加 5 个 gcode-relevant 字段（distribution_mode /
   gradient_enabled / gradient_start / gradient_end / ui_mode），默认值对称 MixedFilament。
2. `src/slic3r/GUI/MixedColorMatchHelpers.cpp` —
   `build_multi_color_match_candidate` 设 LayerCycle；
   `build_best_color_match_recipe` 两处 triple search 设 LayerCycle；
   `compute_color_match_recipe_display_color` 改用 recipe.distribution_mode。
3. `src/slic3r/GUI/Fulfillment/FulfillmentStore.hpp` —
   `apply_edited_recipe` 签名加 5 参数。
4. `src/slic3r/GUI/Fulfillment/FulfillmentStore.cpp` —
   impl 写入新字段（std::clamp 归一化 distribution_mode）。
5. `src/slic3r/GUI/Fulfillment/FulfillmentPanel.cpp` —
   seed 读出（5 字段）+ apply_edited_recipe 调用传入（5 字段）双向对称。
6. `src/slic3r/GUI/Fulfillment/FulfillmentSliceMapping.cpp` —
   BatchEntry 透传 distribution_mode/gradient_enabled/gradient_start/gradient_end。
7. `src/slic3r/GUI/Plater.cpp` — design-layer "Add Mix" 按钮去掉 heuristic，用 recipe 真值。
8. `tests/libslic3r/test_mixed_filament.cpp` — 新增 round-24 回归测试。

## 测试证据

- build 了 Snapmaker_Orca（主可执行 target，直接消费 src 改动）：176/176 含 linking ✓
- build 了 libslic3r_tests（测试 target）：4/4 含 linking ✓
- 新测试 "Mixed filament three-colour gradient resolve honours distribution_mode
  (round-24 regression)"：15 assertions 全过 ✓
  - 验证 Simple + 3 ids 输出二色（bug 行为 + 安全降级）
  - 验证 LayerCycle + 3 ids 输出三色（修复行为）
- 全套 [MixedFilament] 测试：166 cases（原 165 + 新 1），164 passed + 2 failed-as-expected ✓ 无回归
- 字符串证据：`strings libslic3r_tests | grep "round-24"` 命中新测试名（非缓存）
- 时间戳：二进制 (00:33:12) 晚于所有源文件改动（00:26-00:27），确认重链接

## E2E 证据

本轮在 unit test 层验证 resolve() 行为。完整 E2E（实际切一个三色 fulfillment recipe 看 gcode
里的 T0/T1/T2 都出现）需要真实打印机 + UI 交互，列入 backlog（见下）。

## 过程意外 / 与预期偏差

- **对抗 agent 没覆盖的横向发现**：Step 4d 我自己做变种横向 grep 时，发现
  `build_best_color_match_recipe` 的 triple search（coarse + fine 两处）和
  `build_multi_color_match_candidate` 两个 solver producer 也独立写 3 色 recipe 但漏
  distribution_mode。对抗 agent 只审了 dialog 路径，没 grep solver 路径。这印证 R1
  变种级扩张的必要性——已审维度无新发现 ≠ 全 pipeline 无 bug。
- **round-21 的假满分**：round-21 对抗验证写 "Third colour preserved. ✓"，但只验证
  数据进了 device_colors 数组，没验证 resolve() 是否真的取第三色。这是典型的
  "数据在改动层正确 ≠ 数据在它流向的每个下游也正确"（skill Step 4 逐跳追踪原则）。
- **heuristic workaround 是 bug 放大器**：`compute_color_match_recipe_display_color`
  和 `Plater.cpp:3020` 之前用 `gradient_component_ids.empty() ? Simple : LayerCycle`
  启发式推断 distribution_mode，对 MODE_MATCH 2-colour（ids 非空但 Simple）会误判成
  LayerCycle。本轮 recipe 有了真字段后，这些 heuristic 应全部改用真值。

## 遗留 backlog

- **E2E gcode 验证**：实际切一个三色 fulfillment recipe，grep gcode 确认 T0/T1/T2 都出现
  （不只是 unit test 验证 resolve()）。需要真实设备或 mock。
- **local_z_max_sublayers**（对抗 M1 提到）：MODE_GRADIENT 强制 `local_z_max_sublayers=2`，
  但 `MixedFilamentBatchEntry` 没这字段，`add_batch_custom_filaments` 硬置 0。
  本轮没修（Z-gradient 子层数），因为 (a) 不是用户报告的 bug，(b) BatchEntry 也要加字段，
  改动更大。列为 backlog。
- **bespoke 弱投影彻底消除**（对抗 M2 元建议）：本轮补全了 gcode-relevant 字段，但
  `MixedColorMatchRecipeResult` 仍是 `MixedFilament` 的投影副本。长期应考虑让 recipe
  直接持有 MixedFilament 的相关子集，避免未来再加字段时再次遗漏。
