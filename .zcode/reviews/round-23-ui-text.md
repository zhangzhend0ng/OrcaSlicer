# Round 23 — 映射 UI 行文字还是两色（三色 plan 文字未渲染）

用户报告："plater 的映射 ui 的文字显示的还是两色的"。

## 根因
FulfillmentPanel::add_fulfilment_row 的 Synthesised plan 文字硬编码成两色：
    plan = wxString::Format(_L("mix slot %s + %s @ %d%%"),
                            label_for(component_a), label_for(component_b), mix_b_percent);
只渲染 component_a/component_b + mix_b_percent。三色混色的第三色和它的权重存在
gradient_component_ids / gradient_component_weights（round-21 已确认数据结构和空间），
但行渲染完全没读这两个字段。所以即使 slice 路径（round-21）和 Plater 消费端（round-22）
已正确处理三色，**用户在 canvas 行里看到的 plan 文字仍只有两色**。

## 修复
Synthesised 分支：先用 MixedFilamentManager::decode_gradient_component_ids(.,0) 解码
gradient_component_ids。当组件数 ≥3 时，渲染完整多色 plan：
    "mix slot X/Y/Z @ a%/b%/c%"
（slots 用 label_for 解析每个 palette-local id 到 tray_name；weights 手动 split "/"
得到平行百分比，因为 decode_gradient_component_weights 是 MixedFilament.cpp 的
file-static）。当 gids < 3（含 solver 产的纯 2 色 synth、dialog 双色 gradient marker
{a,b}）时，保留原两色文字 — 无回归。

## 对抗验证
- 2 色 solver synth（gradient 空）：gids.size()==0 → 两色文字。✓ 无回归
- 2 色 dialog gradient（{a,b}, weights 空）：gids.size()==2 → 两色文字。✓ 无回归
- 3 色 MODE_RATIO：gids=3, weights="40/35/25" → "mix slot 1/3/5 @ 40%/35%/25%"。✓
- 3 色 MODE_MATCH（weight 0 被过滤→2 id）：gids=2 → 两色文字（dialog 语义：0 权重不参与）。✓
- malformed weights（数量不匹配）：slots 完整，pcts 可能短，不崩溃。✓
- label_for(gid)：gid 是 palette-local 1-based，component_ams_keys/tray_names 是完整
  palette（apply_edited_recipe 存的），任何 gid 都能索引。✓

## Build green。
