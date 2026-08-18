# Review: feature/mix_match_map_p2 (2026-08-18)

- 评审范围：`05e1e2eef8..HEAD`（3 个提交：8ddc533 / 5fbc86e / cb4aa20，11 个文件，约 700 行）
  - 注：`upstream/release_2_3_6` 引用已前移至 `c0d4ab0d`，两点 diff 会误含 upstream 新内容（52k 行），评审使用 merge-base。
- 协议：harness-driven-review Part B；harness 于读码前加载（B1/B2）。

## Harness: Code Review Checklist (common/code-review/review-checklist.md, C)

- Item 1 (规模 <400 行/次)：N/A —— 700 行按 3 提交拆分评审，每提交 <650 行，含大量删除（-447），实际净增 ~250 行。PASS（拆分合理）。
- Item 2 (作者自检)：PASS —— 实现期已按 Part A3 自检（见各提交信息，含构建验证事故的如实记录）。
- Item 3 (正确性)：
  - **FAIL (C)** F1：`build_recommended_card` 中 `set_recommended_combo_icon(i)`（MixedFilamentBatchDialog.cpp:1595 附近，函数体内相对行 80）调用早于 `m_recommended_combo[i] = cb` 赋值（相对行 91）→ `set_recommended_combo_icon` 因 `m_recommended_combo[row]==nullptr` 提前 return（该函数开头判空）→ **初始构建时四个收起态下拉没有"箭头+槽位序号徽章"复合图标**：下拉箭头被选中项图片抑制（§68 语义）、spec §4 的"固定序号 1-4"不显示。手动卡片存在同样调用顺序但因其卡片默认隐藏、`on_method_changed` 切换时重应用而掩盖；推荐卡片是默认可见卡，无任何重应用路径（ctor 末尾 `Show(true)` 不补图标）。
    - 修复：赋值提前到 `set_recommended_combo_icon` 之前；并在 ctor 的 `m_recommended_card->Show(true)` 后对 4 行重应用一次（SetIcon 在隐藏窗口可能不渲染，参照 on_method_changed 的注释与做法）。
  - 边界（空/短/退化输入）：PASS —— 色板 <4 走合成兜底（FULL_SPECTRUM_FALLBACK_COLORS 恒 4 项）；defaults 恒 4 项；所有 `palette[sel]` 访问前有 `-1 < sel < size` 守卫（recommended_selections_distinct / build / worker / confirm 四处均核）。
- Item 4 (安全)：PASS —— 无注入/密钥/新依赖。
- Item 5 (测试)：PASS（附注）—— 纯函数 4 个新用例 31 断言全过；`[MixedFilament]` 回归与基线逐数一致（1 failed + 2 failed-as-expected 均为存量，其一为注释明示的 known-failure）。GUI 层无自动化基建，手动清单已在方案中列出（附注：PR 描述需带入）。
- Item 6 (可读性)：
  - PASS —— 函数 <150 行、注释解释 WHY、无裸 TODO（TODO(phase-3) 带上下文与冲突备注）。
  - **FAIL (A)** F4：`MixedFilamentBatchDialog.cpp:22` 的 `#include <unordered_map>` 在删除 `update_recommended_card` 后已无使用（grep 全文件仅 include 行），IWYU 残留。
- Item 7 (性能)：PASS —— 无热路径 O(n²)；`full_spectrum_family_preset_selectable` 为 O(presets)×4 仅在 Confirm 点击时执行一次。
- Item 8 (评审时效)：N/A。

## Harness: Thread Safety (cpp/concurrency/thread-safety.md, N)

- Item 1 (数据竞争自由)：PASS —— 新增共享可变状态仅在 UI 线程（`m_recommended_palette`/`m_recommended_selections`，成员仅 ctor/事件处理器读写）；worker lambda 全部按值捕获（`preset_colors` 为 hex 副本），UI 回传经 `CallAfter`（MixedFilamentBatchDialog.cpp worker 尾部）。`FilamentColorLibrary::Instance()` 全部 5 处调用点均在 UI 线程（PresetComboBoxes.cpp:1063 / PresetUpdater.cpp:1951 / 本文件 339、975-976），V1.0 worker 侧的 `FindFilamentByName` 路径已随死代码删除。
- Item 7 (线程生命周期)：PASS —— `std::thread` join 语义未改动（沿用现有 join/destroyed-flag 模式）。
- OTA `Reload()` 与弹窗并发：PASS —— 弹窗持有的是条目副本（BuildFullSpectrumPalette 逐项拷贝），`GetAllFilamentInfos()` 引用仅在同步调用内使用不被持有；模态嵌套事件循环中 Reload 亦只影响库内部（下次打开弹窗生效），不触及已拷贝数据。

## Harness: Undefined Behavior (cpp/correctness/undefined-behavior.md, N)

- Item 2 (空指针)：PASS —— `m_recommended_combo[i]`/图标缓存指针均判空后使用；`set_recommended_combo_icon` 越界参数提前 return。
- Item 3 (越界索引)：PASS —— 详见 review-checklist Item 3 边界核查；`slot_color_families[slot]` 的 slot < min(4,size) ≤ 数组长度。
- Item 4 (生命周期)：PASS —— `by_hex` 类悬空指针模式已随 `update_recommended_card` 删除；lambda 捕获 `this`/`i` 的生命周期与既有代码一致（控件为对话框子窗口）。
- Item 1/5 (整型溢出/数据竞争)：PASS —— 索引均为 int 级小数值；竞争见上节。

## Harness: Input Validation (common/security/input-validation.md, N)

- Item 1/2 (信任边界/白名单)：PASS —— `filaments_colours.json` 为外部输入，双重校验：`BuildFullSpectrumPalette` 内 `NormalizeFilamentHexColor`（#RRGGBB 6 位 xdigit 白名单）+ GUI 侧 `try_parse_color_match_hex` 复验，非法项丢弃并 `BOOST_LOG_TRIVIAL(warning)`（拒绝+日志，非静默修复）；类型过滤（type 含 "Full Spectrum"）+ 单一色 SKU 过滤沿用 V1.0 规则。
- **FAIL (A)** F5：色板条目数无上界 —— 恶意/异常配置可产生超大下拉列表（V1.0 暴露面为单家族，本期扩展到所有家族）。建议展示层设 sane cap（如 64）并告警。
- Item 6 (失败处理)：PASS —— 逐项拒绝+日志；库加载失败走静态兜底并记日志。

## Harness: wxWidgets 3.1.5 Pitfalls (cpp/third-party/wxwidgets-3-1-5.md, P)

- Item 1 (wxString 编码)：PASS —— `wxString::FromUTF8` / `into_u8` 显式转换，无 `c_str()` 跨界。
- Item 13 (Bind+lambda)：PASS —— 沿用文件既有模式。
- Item 14 (sizer/隐藏子窗口)：PASS —— 模式切换路径已有 `relayout_scrolled_content`。
- Item 25 (ComboBox 事件)：PASS —— `wxEVT_COMBOBOX` + `wxCB_READONLY`；`SetItemTooltip` 为项目内建控件原生能力（Widgets/DropDown.cpp 行级 hover 已验证存在）。
- SetIcon 高度重锁（项目已知怪癖）：PASS —— `set_recommended_combo_icon` 复刻了 `set_manual_combo_icon` 的 30 DIP 重锁。
- **FAIL (C)** F1 关联（同 review-checklist Item 3）：初始可见卡片的复合图标缺失（详见 F1）。

## Harness: Requirements Gap Analysis (common/planning/requirements-gap-analysis.md, C)

- Item 1 (证据)：PASS —— 分支基点、引用前移、upstream 重叠改动均有 commit/file:line 证据（见 F2）。
- **FAIL (C)** F2：分支基于过期基点 `05e1e2e`；`upstream/release_2_3_6` 已前移至 `c0d4ab0d`，其新增改动与本期文件重叠：`build_recommended_card`/`build_manual_card`（标题行高度钉死 20 DIP、深色模式 icon_minus/plus/箭头图标族、手动行高度从 -1 改钉 30 DIP）、`Plater.cpp`（+8）、`zh_CN.po`（+5）→ **rebase 冲突必然**；且有语义漂移：本期新增的推荐行沿用旧模式钉高 `-1`，upstream 已把手动行改为钉 30 —— rebase 后若不同步，模式切换高度抖动的修复会被退化。开 PR 前应 rebase 至 `c0d4ab0d` 并将推荐行高度/标题高度对齐 upstream 新约定。

## Harness: Risk & Verification Plan (common/planning/risk-and-verification-plan.md, C)

- Item 2/3 (验证命令/证据)：PASS —— MSBuild 退出码（pipefail）+ 显式编译行 + .lib 链接行；测试 exe 直跑输出。
- **FAIL (A)** F6：zh_CN po 语法 NOT VERIFIED —— 本机无 `msgfmt`，无法 `--check`；缓解：改动为手术式（CRLF/转义保持、仅行替换 + 结构完整的新条目对），`git diff` 逐行核对过。建议 CI 的 gettext 目标（build/gettext_*.vcxproj 存在）作为最终验证门。
- Item 4 (回归)：PASS —— 见 review-checklist Item 5。

## 其他核查（无 harness 对应，证据记录）

- F3 (A)：`build_recommended_card` 的 `else if (!m_recommended_palette.empty()) cb->SetSelection(0);` 分支未同步 `m_recommended_selections[i]`（潜在状态不一致；当前不可达——色板恒 ≥4 使 defaults 恒 4 项；沿用了手动卡片的既有同款模式）。建议删 else 或同步赋值。
- F7 (A)：Confirm 内 Note 弹窗描述为 "one-shot"——实际每次点 Confirm 都会评估；因随后立即 `EndModal`，每个对话框会话至多出现一次，语义成立，仅措辞精确性备注。

## 结论

**REQUEST CHANGES**

- 阻断（合并前必须处理）：F1（初始图标缺失，功能性 UI bug，本报告后立即修复）、F2（rebase 至新基点并对齐 upstream 行高/标题约定）。
- 建议随手处理：F3、F4（本次修复一并处理）；F5、F6、F7 记录在案（F5 可作后续小改动，F6 由 CI gettext 门覆盖）。

## 处置记录（2026-08-18，提交 9d91786）

- F1：已修复 —— `m_recommended_combo[i] = cb` 提前至 `set_recommended_combo_icon(i)` 之前；ctor `Show(true)` 后对 4 行重应用图标。构建验证：MSBuild exit 0（pipefail）+ 显式编译/链接行。
- F3：已修复 —— `SetSelection(0)` 回退分支同步 `m_recommended_selections[i] = 0`。
- F4：已修复 —— 移除未使用的 `<unordered_map>`。
- F2：未处理（需 rebase 至 `c0d4ab0d`，含行高/标题约定对齐）—— 开 PR 前执行。
- F5/F6/F7：保留记录。F6 补充：本机 clang-format 与文件既有风格全文件分歧（~200 hunks，仓库使用不同版本工具链），格式合规性 NOT VERIFIED，新代码遵循文件既有风格。
