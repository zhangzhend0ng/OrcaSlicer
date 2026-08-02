# Round 26 — 映射混色自动匹配：单色比例上限（基于层高）+ 偏好确认

用户要求："映射的混色自动匹配增加个 70% 最高比例限制，然后也是优先选差异更小的物理"。

## 触发的理论缺口

- **数值无出处**（初判）：用户说 "70%"，对抗审查追问出处。
- **配置卫生 - 作用域**：max 挂在 solver，验证器/编辑器无 max 维度（对抗发现，本轮按用户"只改
  fulfillment"范围规避）。
- **需求语义二义性**：对抗审查揭示 "70%" 和 "优先差异更小的物理" 都有多种解释，必须澄清。

## grep journal 结果（Step 1 强制）

- round-10: kColorMatchDirectThreshold / kTunableDeltaE 是共享常量（无本地副本）。
- 无过往 max_component_percent 调整记录——这是首次改 fulfillment 的 max 传值。

## 合法 shape 清单（build_best_color_match_recipe 产出）

| Shape | 判别字段 | UNDERSTOOD? | 方案覆盖? |
|-------|----------|-------------|-----------|
| A: invalid | valid=false（target 无效/palette<2） | ✓ | n/a（max 不影响） |
| B: 2-colour pair | component_a/b + mix_b_percent, Simple | ✓ | ✓ max 约束 pct 范围 |
| C: 3-colour triple | gradient_component_ids 3项, LayerCycle | ✓ | ✓ max 约束每色 weight |
| 选择逻辑 | pair vs triple 统一 ΔE 比较，ΔE 差<0.5 偏好 pair | ✓ | 不改（用户确认） |

## 退化输入×消费者矩阵

| 退化输入＼消费者 | solve_intent (max 计算) | build_best (max clamp) | locked recipe recompute |
|---|---|---|---|
| layer_height=0 / 负 | max=100（禁用约束） | 不影响 | 不影响 |
| layer_height>0.2（超过推荐） | max clamp 到 50（solver 下限） | 搜索窗口 [50,50] 退化 | 不影响 |
| layer_height=0.2（推荐上限） | max=50 | pair pct ∈[50,50]，强制 50/50 | 不影响 |
| layer_height=0.1（精细层） | max=66 | 三色每色 ≤66 | 不影响 |
| locked recipe 80/20（max=50 不会产出） | 不重算（lock_survives 保 recipe） | n/a | 保留 80/20（用户 pin 的决策） |

## 初版方案（被推翻点）

初版：FulfillmentStore.cpp:276 把 max=100 改成固定 70；声称"优先差异更小物理"不需要额外代码
（candidate_pool 已按单色 ΔE 排序）。

对抗审查推翻：
- [blocker] 改动 2 的论证基于事实错误：pair search 根本不用 candidate_pool（全组合），
  candidate_pool 是 triple 专用的性能剪枝，不是"偏好"。
- [blocker] 70 无出处（对抗追问物理依据）。
- [major] max=70 单独上线会选出 70/29/1 退化三色（min=0/1）。
- [major] max=70 与 direct 阈值 1.0 交互导致 over-constrained 次优解。

## 对抗审查结论（用户澄清后的 tiebreaker）

向用户澄清后，需求被重新校准：
- **max 不是固定 70**：是基于层高的动态公式 `n = 0.2/lh + 1, max = (n-1)/n*100`。
  物理依据：不开 localZ 时，单色连续层数不能让颜色读成实心带。0.2mm 是单色连续高度上限。
- **偏好不改**：用户确认"就是现有 ΔE 最优"。
- **范围**：只改 fulfillment 映射路径（不改 design-layer 颜色匹配面板 / batch match）。

对抗的"70 无出处"被用户的一手公式证伪——70 是 lh≈0.1 时的近似值，真实约束是动态的。
对抗的"优先差异更小物理未实现"被用户确认"不需要"——现有 ΔE 最优就是想要的。

## 修订方案（采纳）

1. `solve()` 加 `layer_height` 参数（默认 0.0 = 禁用约束，向后兼容）。
2. `solve_intent` 用公式算 max_percent，传给 build_best_color_match_recipe。
3. 两个 solve caller（FulfillmentPanel::on_match + Plater::prepare_slice_inputs）
   从 full_config 读 layer_height 传入。
4. max clamp 到 [50,100]：lh>0.2 时公式给出 <50，触发 build_best 的 [50,100] 守卫
   会返回 invalid——clamp 到 50 避免（50/50 仍是有意义的混合）。

## 数据流 hops 状态

| Hop | 写者→读者 | 状态 |
|-----|-----------|------|
| 1 full_config layer_height → caller | FulfillmentPanel:142 / Plater:13098 | ✓ |
| 2 caller → solve(layer_height) | 2 caller 都传 | ✓ |
| 3 solve → solve_intent(layer_height) | line 152 | ✓ |
| 4 solve_intent → max_percent 计算 | line 275-285 | ✓ |
| 5 max_percent → build_best_color_match_recipe | line 287 | ✓ |
| 6 build_best 内部 clamp（pair/triple 循环） | 现有 line 457/531/574 | ✓（未改） |

## 变种横向 grep 结果

- build_best 的其他 caller（MixedColorMatchPanel:500, Plater:1738, batch_match, recommend_combo）
  按用户"只改 fulfillment"范围，不改。design-layer 保持 max=100（用户在两处会看到不同结果，
  这是用户明确接受的）。
- locked recipe recompute：lock_survives 保 recipe 不重算（solve_intent 不被调），
  所以 max 改动不影响已 locked 的 recipe。fresh solve 才用新 max。

## 改动文件

1. `FulfillmentStore.hpp` — solve() 加 layer_height 参数 + 注释；solve_intent 加参数。
2. `FulfillmentStore.cpp` — solve/solve_intent 签名 + max_percent 计算（用户公式）。
3. `FulfillmentPanel.cpp` — on_match 读 full_config().layer_height 传入。
4. `Plater.cpp` — prepare_slice_inputs 读 out.config.layer_height 传入。

## 测试证据

- build Snapmaker_Orca：成功（无 error，binary 02:07:57 晚于源文件）✓
- MixedFilament 全套 166 cases（164 + 2 failed-as-expected），无回归 ✓
- max_percent 计算逻辑边界核实（node 验证）：
  - lh=0.1 → max=66%, lh=0.15 → 57%, lh=0.2 → 50%, lh≥0.25 → clamp 50%, lh=0 → 100% ✓
- build_best_color_match_recipe 在 GUI 层（依赖 wxColour），不在 libslic3r_tests 链接范围，
  无法直接单测 max 约束行为。靠 max_percent 计算核实 + 回归测试无破坏间接保证。

## 过程意外 / 与预期偏差

- **初版"固定 70"被对抗推翻，用户公式是动态的**：对抗追问"70 的出处"逼出真实需求——
  不是固定 70，是基于层高的物理约束。这是 skill 核查项 (b)"魔数有无出处"的精确兑现：
  追问出处不是为了拒绝，是为了理解真实约束。固定 70 是 lh=0.1 时的近似，但层高变化时
  约束也变。
- **full_config 是函数不是变量**：FulfillmentPanel.cpp 初版写 `pb->full_config.option`
  编译失败（reference to non-static member function）。改为 `pb->full_config().option`。
  Plater.cpp 那边 `out.config` 是真成员变量，没问题。同一概念两个 caller 不同访问方式。
- **对抗的"3 个 blocker"在用户澄清后大部分消解**：70 无出处→用户给了公式；
  优先差异更小→用户说不需要；只改 fulfillment→用户确认接受 design-layer 不一致。
  但"max 单独上线产退化三色（70/29/1）"仍成立——min=0 时 1% 那色仍会进 gradient_ids。
  本轮没改 min（用户没要求），但 max clamp 到 50 时（lh≥0.2）pair 强制 50/50，
  三色每色≤50 至少避免了 99/1 这种极端。lh<0.2 时 max∈[51,66]，仍可能 66/33/1——
  这是 min 的范畴，记 backlog。

## 遗留 backlog

- **min_component_percent 未调**：max 约束了上限，但 min 仍是 0（实际 1%）。
  lh<0.2 时 max∈[51,66]，三色组合可能出现 66/33/1 这种第三色只占 1% 的退化 recipe。
  若要避免，需配套调 min（如 min=15 与设计层 MixedColorMatchPanel 默认一致）。
  用户未要求，记 backlog。
- **design-layer 一致性**：MixedColorMatchPanel / batch_match 仍 max=100。用户在
  fulfillment 映射和设计层颜色匹配面板会看到不同结果。用户明确接受（"只改 fulfillment"）。
- **color_match_weights_within_range 无 max 维度**（对抗 blocker #2）：验证器只校验 min，
  不校验 max。locked recipe 手动调成 80/20 仍通过验证，但 fresh solve 不会产出。
  本轮不改（用户范围），记 backlog。
