# Round 22 — 完整审查 Plater 的 fulfillment 处理（三色场景）

用户指出："plater 的 fulfillment 处理了这些情况了吗？你需要完整的审查"。
本轮系统审查 Plater.cpp 里**所有**消费 device filament space / fulfillment store /
device palette 的路径，验证三色修复（round-21）后无 regression，且三色 virtual row
正确贯通到所有消费端。

## Plater 里所有 fulfillment touch point（按数据流分组）

### A. Slice 路径（device-space 构建 + 模型重映射）
| 代码点 | 作用 | 三色后行为 | 结论 |
|--------|------|-----------|------|
| `prepare_slice_inputs` (13064) | 构建 device-space config + temp model | num_total 含三色 virtual；state_map 约束 `(int)device_id > num_total` 正确 | ✓ |
| `space->num_total` (13105) | state_map/remap 上限 | SliceMapping 正确算出 num_total = num_physical + mgr.enabled_count()（三色 row 计入） | ✓ |
| `fallback_device_id` (13123) | 未实现 design extruder 重定向 | 只取 design_to_device 首个非 0；三色不影响 | ✓ |
| `state_map` 循环 (13128) | painting state 重映射 | virtual id 在 [num_physical+1, num_total]，约束通过 | ✓ |
| `remap_extruder_field` (13160) | volume/object/layer extruder 重写 | round-7/16 已修；mapped > num_total clamp 到 1 | ✓ |
| `remap_extruder_ids` (13150) | MMU painting 三角面重映射 | 用 num_total 做上限，三色 virtual 正确 | ✓ |
| auto_generate 抑制 (13249-13253) | 保证 virtual id 确定性 | 仍抑制；只有 demo 显式 add 的 synth row（含三色）存在 | ✓ |

### B. Device palette cache（G-code 预览用）
| 代码点 | 作用 | 三色后行为 | 结论 |
|--------|------|-----------|------|
| `DevicePaletteCache` 写入 (13208-13212) | 缓存 device-space 颜色 | virtual_colors = space->virtual_display_colors，跟着 SliceMapping 的 mgr.display_colors() 走，三色自动包含 | ✓ |
| `get_extruder_colors_from_plater_config` device 分支 (22310-22318) | 返回 physical + virtual 颜色 | force_device_palette 时拼 physical_colors + virtual_colors；长度 = num_total；三色正确 | ✓ |
| `get_colors_for_color_print` (22417+) | ColorPrint 预览 | force_device_palette=true, include_mixed=true；拿到含三色的 device palette | ✓ |

### C. 3D 渲染路径
| 代码点 | 作用 | 三色后行为 | 结论 |
|--------|------|-----------|------|
| `get_expected_render_colors` (22334) | 3D 模型实现色（按 design extruder） | 每个 design extruder 一个 recipe.preview_color（混合色）；不关心几色混，只按 design extruder 索引 | ✓ 不受影响 |
| `refresh_expected_render` (22382) | 强制重绘 | 触发 set_as_dirty，render 路径读 get_expected_render_colors | ✓ |

### D. 生命周期 / 信号
| 代码点 | 作用 | 三色后行为 | 结论 |
|--------|------|-----------|------|
| `priv::reset` (12650) 项目重置 | reset store + 关 EV | round-18 已加 reset_all + toggle sync | ✓ |
| `on_filaments_change` mark_stale (10319) | 设计变更标记 stale | 三色 entries 仍正确标记；refresh 显示 stale 提示 | ✓ |
| `load_ams_list` mark_stale (8726) | 设备变更标记 stale | 同上 | ✓ |
| `invalidate_device_palette_cache` (8732, 10325) | 清 device palette cache | 下次 slice 重建，含三色 | ✓ |
| `notify_filament_compatibility_after_apply` (12916) | 喷嘴/耗材兼容性通知 | 读 Print 的 filament_rule_mismatch_flags（device-space config）；三色 virtual 不触发误报（它不是物理喷嘴） | ✓ |

### E. 不受影响的路径（确认隔离）
| 代码点 | 为什么不受影响 |
|--------|---------------|
| `update_mixed_filament_panel` (6822) | 读 design-layer preset_bundle，不读 device-space |
| `MixedFilamentRowBinding` (1058) | design-layer manager 的 UI binding，slice 不回写 design layer |
| `update_mixed_filament_id_remap` (2554) | batch_match 路径（apply_batch_match_to_model），独立于 fulfillment slice remap |
| `WipingDialog` flush volumes (2399) | include_mixed=false，只取 physical colors |
| `MixedFilamentColorMatchDialog` (1388) | 已有 dialog，不消费 fulfillment store |

## 对抗验证：三色 num_total 增大是否会泄漏 phantom virtual extruder？
`Print::object_extruders` (Print.cpp:868) 从 model volumes 的 extruder 字段收集
（已被 remap_extruder_field 重映射）。三色 virtual id 只有在 design extruder 的
recipe 是成功 synth 时才进 design_to_device（SliceMapping Pass 4），且只有被 model
painting/volume 引用时才进 object_extruders。所以不会 phantom——只有真正被引用的
virtual 才进 filament 列表。✓

## 对抗验证：G-code 预览颜色索引对齐
G-code Tn 读 colors[n-1]。virtual row T-number = num_physical + synth_index + 1
（1-based）。get_extruder_colors_from_plater_config 返回 physical(0..np-1) +
virtual(0..vc-1)。virtual row i 的颜色在数组 index num_physical + i = (T-number) - 1。✓ 对齐。

## 结论
Plater 里所有 fulfillment/device-space touch point 在三色场景下行为正确：
- Slice 路径：num_total/state_map/remap 正确处理三色 virtual id
- Device palette cache：virtual_colors 跟着 SliceMapping 自动含三色
- 3D 渲染：按 design extruder 索引，不关心混色数
- 生命周期：stale/reset/cache-invalidation 都正确
- 隔离的路径（Mixed Filaments 面板/batch_match/WipingDialog）不受影响

**无需额外代码改动**。三色修复（round-21）在 SliceMapping 层正确，Plater 的消费端
通过既有的"跟着 device-space 产出走"设计自动受益。Build green。
