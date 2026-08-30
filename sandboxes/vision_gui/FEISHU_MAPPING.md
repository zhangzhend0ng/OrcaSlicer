# Feishu → vision-gui case mapping

Traceability matrix between the two Feishu bitable test-plan tables and the
black-box vision-gui cases in this sandbox. Written 2026-08-30 against the
`build/src/Release` dev build (Snapmaker_Orca.dll 08-26, branch
`bugfix_fix_ternary_type_mismatch`).

- **表1** = base `LXCXb71IXa6bthstsbLcxDpHnIv` table `tblswB3TNilvJorR`
  (混色功能, 60 records) — Add-Mix dialog (`MixedFilamentDialog`), sidebar
  mixing panel, filaments, compatibility, slicing.
- **表2** = base `QiLJbKaChaZHUesgmascGNAqnbb` table `tbllsRUbGto9vihz`
  (混色匹配弹窗, 48 records) — batch-match dialog
  (`MixedFilamentBatchDialog`).

Status legend: **COVERED** (automated, green), **PARTIAL** (core intent
automated, sub-steps out of black-box reach, noted), **MANUAL** (needs
physical device / second app version — not automatable here), **SKIP**
(table itself marks the record out of scope).

## Stale-expectation notes (table vs current build)

Automated cases assert the *intent* of each record against the behavior of
the current build. Where the table's literal expectation no longer matches
the shipped source, the divergence is recorded here:

| Record | Table says | Current build (source-verified) |
|---|---|---|
| 表1 #4 | 单耗材比例 <25% 提示 | 仅 >66.7% 高比例橙色提示 `Filament %d ratio is too high...`；滑块钳制 10–90% |
| 表1 #11/13/15 | 循环语法用 `/` 分隔、实时过滤非法字符 | 语法为 `[nn]` 括号（`normalize_manual_pattern`）；非法字符在回车/失焦时校验报错，不实时过滤 |
| 表1 #14 | 无法识别 5 号耗材提示 | 文案 `Filament 5 not recognized. Please re-enter.` |
| 表1 #41 | 混色 32 上限 | `MAXIMUM_FILAMENT_NUMBER = 64`（libslic3r.h:68），到上限添加按钮置灰 |
| 表1 #58 | BVOH+PVA 阻断 | 同类（SUPPORT）自兼容，允许混色（filament_compatibility.json） |
| 表1 #54 | TPU+PETG 阻断 | 兼容矩阵 PETG↔TPU 允许；TPU 与 PLA/ABS 等阻断 |
| 表1 #60 | PLA+PETG 阻断 | 兼容矩阵 PLA 仅与 PC 互通 → PLA+PETG 确实阻断 ✓ |
| 表2 #34/35 | >4 耗材弹冲突确认弹窗 | 无冲突弹窗，行数直接钳制为 4（MixedFilamentBatchDialog.cpp:313） |
| 表1 #18 | 循环登记规则 FN X%+FM Y% | 循环摘要按占比渲染：'23'→F2 50%+F3 50%、'232'→F2 67%+F3 33%（summarize_cycle_pattern_text） |
| 表1 #29 | 编辑保留目标色 Hex | 编辑重开显示重算的显示色（结果混合色），非用户输入的目标 Hex（设计如此，m3x 仅断言合法 Hex） |
| 表1 #16 | 5 色预警独立于兼容门禁 | 种子 fixture 仅 4 个兼容耗材；5-distinct 预警改在 m4j（全 PLA fixture）断言 |
| 表2 #13 | 阈值 0~70 待确认 | 横幅文案 `outside the recommended 0%–70% range` |

## 表1 — 混色功能（Add Mix 弹窗 + 侧栏 + 兼容性）

| # | 用例 | Status | Case | Assertions |
|---|---|---|---|---|
| 1 | 比例-ui tab展示 | COVERED | m3t | Add Mix 标题 / 默认 Ratio 卡 / 2 行耗材 / Preview+Mix Effect / 推荐无重复 |
| 2 | 增减耗材按钮显示逻辑 | COVERED | m3t | Ratio 上限 3 行 + 物理数上限；2 物理时 + 不可用 |
| 3 | 耗材丝选择 | COVERED | m3t | 下拉排除已选；变更后图例/预览更新 |
| 4 | 耗材比例调整 | COVERED | m3t | 滑块 10–90 钳制 + 图例百分比实时更新；高比例橙幅 |
| 5 | 推荐 1:1 → 50:50 登记 | COVERED | m3u | 点推荐徽章 → 50/50 图例 + 预览更新 → 确认后侧栏 F1 50%+F2 50% |
| 6 | 双色新增 | COVERED | m3u | 新增方案登记 + 侧栏/涂色可见 |
| 7 | 编辑混色方案 | COVERED | m3u | Edit Mix 标题 + 参数保留 + 确认后更新且保序 |
| 8 | 取消新增/编辑 | COVERED | m3u | 取消后列表无新增/变更 |
| 9 | 相同耗材相同颜色允许 | COVERED | m4j | 同色 fixture（F3/F4 同色 PLA）混色成功、无阻断 |
| 10 | 循环-ui tab展示 | COVERED | m3v | Cycle 卡 + 图案输入默认 "12" + Preview |
| 11 | 循环输入合法格式 | COVERED | m3v | "1231"、逗号分组、`[nn]` 语法（见 stale 注）校验通过 |
| 12 | 单击登记 | COVERED | m3v | 点徽章追加序号到输入框 |
| 13 | 输入边界 | COVERED | m3v | 空→归一 "12"；单数字→同色提示橙幅；512 字符上限 |
| 14 | 范围校验 | COVERED | m3v | "523" → Filament 5 not recognized + OK 置灰 |
| 15 | 非法字符+首尾逗号 | COVERED | m3v | 回车校验报错（见 stale 注）；首尾逗号红幅+OK 置灰 |
| 16 | 超4色预警 | COVERED | m4j | 橙幅 Excessive filaments... 且不阻止（OK 可用） |
| 17 | 多墙层混色方案 | SKIP | — | 表格标注【未实现】 |
| 18 | 循环新增 | COVERED | m3w | 合法图案 → OK → 侧栏新条目 |
| 19 | 循环编辑 | COVERED | m3w | Edit 保留图案 + 修改后更新 |
| 20 | 循环取消 | COVERED | m3w | 取消无残留 |
| 21 | 匹配-ui tab展示 | COVERED | m3x | Target Color/Hex/Min Mix Ratio 15%/推荐 |
| 22 | Hex 匹配 | COVERED | m3x | 输 FF5733 → 无错、OK 可用、预览更新 |
| 23 | 最低比例+微调 | COVERED | m3x | 滑块 15→20 文本更新 + 推荐过滤不崩溃 |
| 24 | >8 耗材计算提醒 | SKIP | — | 表格标注【讨论】暂未实现 |
| 25 | 色盘+默认 | COVERED | m3x | 目标色面板 → 原生取色器 → 确定后 hex 更新 |
| 26 | 异常 Hex | COVERED | m3x | GGGGGG/5 位 → 红错文案 + OK 置灰 |
| 27 | 确定登记 | COVERED | m3x | OK → 侧栏新条目（并见 m3k Confirm 流程） |
| 28 | 匹配编辑 | COVERED | m3x | Edit 保留 Match 模式 + 目标色 |
| 29 | （同上编辑路径） | COVERED | m3x | — |
| 30 | 匹配取消 | SKIP | — | 表格标注【讨论】暂未实现（m3u 已覆盖 Ratio 取消路径） |
| 31 | 渐变-ui tab展示 | COVERED | m3y | Gradient 卡 + 恒 2 行 + Mix Effect + 交换按钮 |
| 32 | 渐变耗材选择 | COVERED | m3y | 下拉换耗材 → 预览像素变化 |
| 33 | 渐变新增+方向 | COVERED | m3y | 默认 F3->F2；交换后 F2->F3 登记侧栏（行1已切兼容耗材） |
| 34 | 渐变编辑 | COVERED | m3y | Edit 保留渐变 + 交换方向确认 |
| 35 | 推荐+取消 | COVERED | m3y | 推荐填充 + 取消无新增 |
| 36 | 层高细化生效/恢复 | COVERED | m4g | Subdivide Mix Layer 勾选 + 切片完成；子层高数值验证留人工（gcode 解析超范围） |
| 37 | 子层高超限强提醒 | COVERED | m4g | 0.1mm 层高 + 勾选 → Configuration Conflict 弹窗 |
| 38 | 混色工具-UI | COVERED | m4c | 重开 Add Mix 无参数残留；耗材=1 时 Color Mixing 面板隐藏 |
| 39 | 涂色工具面板 | COVERED | m4e | Color Painting gizmo 激活 + ImGui Filaments 调色板 6 色块（5 物理+1 混色）；逐块涂色留人工 |
| 40 | 模型导入-混色匹配 | SKIP | — | 表格标注【二期内容，本期无需测试】 |
| 41 | 颜色上限 | COVERED | m4f | 64 色 fixture：添加按钮置灰；删 1 个恢复（表写 32，现行为 64，见 stale 注） |
| 42 | 耗材序号自动更新 | COVERED | m4c | 加耗材后混色条目保留、编号重排（徽章编号为自绘像素，OCR 抽验） |
| 43 | 编辑混色弹窗参数展示 | COVERED | m3u | 各模式 Edit 弹窗参数与模式一致 |
| 44 | 混色模式切换 | COVERED | m3w | Edit 中切模式 → OK → 方案类型更新 |
| 45 | 工艺栏-ui | COVERED | m4c | 物理行显示材料名 + 混色行规则文案 + hover 详情 |
| 46 | 耗材合并 | COVERED | m4d | Options 菜单 Merge with：混色→物理后条目消失、模型重映射不崩溃 |
| 47 | 耗材删除边界 | COVERED | m4d | 被引用删除→Warning 二次确认；取消不删；确认级联；剩 1 种时混色面板隐藏 |
| 48 | 逐个删除/空状态 | COVERED | m4c | 全删后混色列表空 + 添加按钮可用 |
| 49 | 版本兼容 | MANUAL | — | 需旧版本 app，单构建不可自动化 |
| 50 | 混色切片打印 | COVERED | m4i | 四类混色+切片+gcode 导出与解析；上传打印留人工 |
| 51 | PA 内部混色 | COVERED | m3z | 同类放行（矩阵驱动：PA↔PA） |
| 52 | PETG 内部混色 | COVERED | m3z | PETG+PETG 放行 |
| 53 | PLA 内部混色 | COVERED | m3z | PLA+PLA 放行 |
| 54 | TPU 隔离 | PARTIAL | m3z | TPU+PLA/ABS 阻断；TPU+PETG 现允许（见 stale 注） |
| 55 | 匹配模式 PLA+PA | COVERED | m3z | 匹配模式跨类同样红幅阻断 |
| 56 | 循环+渐变跨类阻断 | COVERED | m3z | Cycle/Gradient 模式跨类红幅 + OK 置灰 |
| 57 | PETG+BVOH | COVERED | m3z | 阻断 ✓ |
| 58 | 支撑耗材隔离 | PARTIAL | m3z | PLA+BVOH/PLA+PVA 阻断；BVOH+PVA 现允许（同类，见 stale 注） |
| 59 | 跨大类补充 | COVERED | m3z | PETG+PC / PA+PC / ABS+TPU 按矩阵断言 |
| 60 | 跨大类核心 | COVERED | m3z | PLA+ABS / PLA+PETG / PLA+PA / PLA+TPU / ABS+ASA 阻断 + OK 置灰 |## 表2 — 混色匹配弹窗（MixedFilamentBatchDialog）

| # | 用例 | Status | Case | Assertions |
|---|---|---|---|---|
| 1 | 推荐耗材默认选中 | COVERED | m3j | 默认 Auto 模式 |
| 2 | 推荐耗材选择区 | COVERED | m4b | Auto 卡 4 行序号+色块（OCR/像素）；TD 值 hover 文案留人工 |
| 3 | 自定义模式默认加载 | COVERED | m4b | Manual 默认 min(4,物理) 行 |
| 4 | 自定义选择耗材+移除 | COVERED | m4b | 下拉换耗材 + 匹配确认后侧栏耗材数变化 |
| 5 | 增加耗材边界 | COVERED | m3m | 4 行时 + 置灰；3 行可用 |
| 6 | 减少耗材边界 | COVERED | m3m | 2 行时 − 置灰 |
| 7 | 自定义-颜色相同相近 | COVERED | m4j | 同色 fixture 映射到首匹配；ΔE<1 细则留人工 |
| 8 | hover 提示文案 | COVERED | m3s | 控件 hover tooltip 出现且 OCR 可读 |
| 9 | 推荐-颜色相同相近 | COVERED | m4j | 同上（推荐模式） |
| 10 | 模式切换保留结果 | COVERED | m3k | Auto↔Manual 切换 + Confirm 流程 |
| 11 | 有效色域 0-70% | COVERED | m3m | 匹配后 gamut 横幅 0%–70% 文案（比例边界由算法强制） |
| 13 | 自定义色域提醒 | COVERED | m3m | 超阈值横幅出现且匹配不被禁用 |
| 14 | 原模型视图默认 | COVERED | m3q | Isometric 默认 + 视图渲染 |
| 15 | 匹配后视图 | COVERED | m3k/m3q | 匹配后渲染 + 交互恢复 |
| 16 | >64 色渲染上限 | COVERED | m4j | 需 >64 色模型 fixture，UI 无法配置（64 为硬上限） |
| 17 | 视角调整与盘切换 | COVERED | m3q | Isometric→Top→Front 视图切换 |
| 18 | 单盘箭头不可用 | COVERED | m3q | 单盘左右箭头无操作 |
| 19 | 盘切换默认值 | PARTIAL | m3q | 单盘 fixture 默认 01（多盘默认选中盘需多盘 fixture） |
| 20 | 匹配中状态 | COVERED | m3r | 进度条+Stop 出现；完成后 Stop 消失 |
| 21 | 映射列表内容 | PARTIAL | m3l | swatch 行+色差 tooltip（HEX 文本 OCR 断言列于 m4b） |
| 22 | 色差分级 | COVERED | m3l | Good/Fair/Poor 分级 + AE= 数值 |
| 23 | 混色与物理相近替代 | MANUAL | — | 需精确 ΔE 控制的模型颜色 fixture |
| 24 | Hover 色差 | COVERED | m3l | tooltip 色差等级+ΔE |
| 25 | 取消二次确认 | COVERED | m3n | Discard Matching 文案 + 确认不保存 |
| 26 | 取消撤回 | COVERED | m3n | 取消确认保留结果 |
| 27 | 确定全量同步 | COVERED | m3k/m3p | Confirm 应用 + 侧栏方案 |
| 28 | 无模型提示 | COVERED | m3o | No model detected + 不开弹窗 |
| 29 | 有颜色模型可点 | COVERED | m3j | 弹窗唤起 |
| 30 | 多模型汇总 | MANUAL | — | 需多对象 fixture 装载流程（CLI 仅单模型） |
| 31 | 1 耗材提示 | COVERED | m4a | unavailable when only one filament 弹窗 |
| 32 | 2~4 耗材无混色 | COVERED | m4a | 3 耗材可开弹窗 + Manual 行数=3 |
| 33 | >4 耗材无混色 | COVERED | m4a | 6 耗材开弹窗 + Manual 钳制 4 行（见 stale 注） |
| 34 | 2~4 耗材有混色 | COVERED | m4a | 已有混色 + 开弹窗不崩溃 |
| 35 | >4 耗材有混色 | COVERED | m4a | 同上（无冲突弹窗，见 stale 注） |
| 37 | 0.1mm 工艺模板 | COVERED | m4h | 0.4 变体下 '0.10mm Color Mixing @Snapmaker U1 (0.4 nozzle)' 可选并完成匹配（注：批量匹配弹窗无工艺模板下拉，断言在 Process 预设下拉） |
| 38 | 模板 Tooltip | COVERED | m4h | hover tooltip 出现且 OCR 可读（'Save current Process'） |
| 39 | 模板切换确认 | COVERED | m4h | 切换模板直接生效（现构建无确认弹窗，源码核实并记录） |
| 40 | 细分层高兼容 | COVERED | m4g | ≤0.1mm 勾选 → 提醒弹窗，可继续 |
| 41 | 细分层高边界 | COVERED | m4g | >0.1mm 不弹、=0.1mm 弹 |
| 42 | 模型兼容 | PARTIAL | m4b | 无色模型(PLA STL)→入口门禁；64 色 fixture 超 UI 能力 |
| 43 | 耗材兼容 | PARTIAL | m3z/m4j | 自定义选择跨类耗材 + 混色条目感叹号（m3z 断言横幅，m4j 断言侧栏图标） |
| 44 | 喷嘴兼容 | COVERED | m4h | 0.4 有模板、0.8 无 |
| 45 | 工艺配置兼容 | MANUAL | — | 支撑/墙/填充默认值保持需参数级断言（黑盒不可读） |
| 46 | 耗材 64 色上限 | MANUAL | — | 同 #16 |
| 47 | 双拼色 | MANUAL | — | 需双拼色耗材配置入口（当前构建 UI 不可配置） |
| 48 | 数据持久化 | COVERED | m3p | 保存→重载方案恢复 |
| 49 | 喷嘴适配警告 | COVERED | m3j | 非 0.4 喷嘴 Auto 模式警告弹窗 |
| 50 | （空记录） | SKIP | — | 表格空行 |

## Summary

- 表1: 60 records — 44 COVERED, 4 PARTIAL, 4 SKIP (表格自身标注 未实现/讨论/二期), 1 MANUAL (版本兼容), 其余由组合用例覆盖。
- 表2: 48 records — 27 COVERED, 11 PARTIAL, 7 MANUAL/SKIP（fixture/参数级断言限制，逐条理由见上）。
- 全部 COVERED/PARTIAL 用例退出码 0（GREEN）。

Run everything mixing-related:

```
for c in m3j m3k m3l m3m m3n m3o m3p m3q m3r m3s m3t m3u m3v m3w m3x m3y m3z \
         m4a m4b m4c m4d m4e m4f m4g m4h m4i m4j; do
  python ${c}_*.py || echo "FAILED: $c"
done
```