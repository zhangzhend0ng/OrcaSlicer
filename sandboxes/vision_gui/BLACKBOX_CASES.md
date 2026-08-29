# BLACKBOX_CASES — 黑盒用例清单与覆盖矩阵（U1 限定）

> 策略（2026-08-29 定）：**以黑盒为主**。白盒线（`tests/wx_gui/`，16 用例）不再扩展，
> 降级为"调研参考资料 + 最小安全网"。新增用例流程 = **先代码调研 → 落四元组 → 再写脚本**。
> 预设只关心 **Snapmaker U1**（0.8/0.4 nozzle），Bambu/第三方预设一律不测（坑 #10 门控全部绕开）。
>
> 黑盒纯度边界：观测通道只有 截图 / 窗口消息 / 文件系统 / 对话框。**只做静态代码调研，
> 绝不做运行时挂钩**（不读进程内存、不调 app API）。白盒源码只用来回答三个问题：
> 功能入口在哪 / 门控条件是什么 / 期望行为是什么。

## 覆盖矩阵（功能面 × 可测性 × 兜底）

| 层 | 含义 | 功能面 | 兜底 |
|---|---|---|---|
| **A 强覆盖** | 有天然外部产物（文件/对话框/画面/按钮态） | 启动与加载、切片管道、参数→重切、预设切换→gcode、多板切片、视图切换、删除/清空、导出 gcode/3mf、错误路径（损坏文件/空场景） | 无（黑盒直接测） |
| **B 弱覆盖** | 可操作但断言弱/交互深 | 画布对象变换（gizmo）、undo/redo、深层设置面板、快捷键/菜单 | 视觉冒烟级断言；价值高时白盒兜底 |
| **C 不可测** | 无外部信号 | 内部状态精确断言（矩阵值/slice_valid/preset 脏态）、切片几何正确性（走线/悬垂/支撑）、纯后台逻辑（崩溃恢复/Sentry/更新）、网络设备栈 | 白盒安全网（存量）或接受风险 |

**关键事实**：A 层之所以是"核心链路全覆盖"，因为切片软件的用户价值链
（加载→配置→切片→预览→导出）每一步都有外部产物。**"导出 gcode 可用"是完成检测的
确定性布尔信号**（`MainFrame::can_export_gcode()`，见下），比绿勾模板强一个数量级——
探测式点击 Export → 模态保存对话框出现 = 完成，不出现 = 未完成，无需模板。

## 工作流（加用例前必做）

1. **查白盒文件** `tests/wx_gui/wx_gui_*.cpp`（第一手调研材料：入口/预设名/快捷键/fixture）
2. **查源码**：功能入口（按钮/菜单/快捷键）、门控（`get_enable_slice_status` /
   `can_export_gcode` 等）、期望行为、fixture 预设
3. **落四元组**到本文件：`（白盒用例引用 / 源码入口+门控 / 黑盒操作序列 / 外部断言）`
4. **实现脚本**（m3a/m3b/…，fresh profile + 真实启动，退出码 0=绿）
5. **跑绿**后把状态从 `planned` 改为 `GREEN`

## 用例清单

状态图例：✅ GREEN（已跑绿）· 🔵 planned（已调研未实现）· ⭕ 已有覆盖 · 🟡 降级/受限

### 已有（m0/m1/m2 覆盖）

| 用例 | 白盒引用 | 外部断言 | 脚本 | 状态 |
|---|---|---|---|---|
| 启动冒烟 | app_tests (1) | 主窗口出现、可见、尺寸>0 | m0_boot_check.py | ✅ |
| 视图切换 Prepare/Preview | business P2-9 | tab 选中色 teal(0,150,136) 翻转 | m1_minimal_loop.py | ✅ |
| 端到端切片 + Preview 工具路径 | app_tests (5) | done 绿勾模板 + 色度占比 ≥2×基线 | m2_slice_chain.py | ✅ |
| 模型自动加载（CLI 位置参数） | app_tests (5) 前置 | viewport 彩色占比 ≥1%（双轮稳定） | m2_slice_chain.py | ✅ |

### 新增（2026-08-29 批次）

| 用例 | 白盒引用 | 外部断言 | 脚本 | 状态 |
|---|---|---|---|---|
| 空场景拒绝切片 | business P3-13 | 点 Slice 不启动任务 + 按钮保持 idle + Preview 无色度 | m3a_empty_slice.py | ✅ |
| 损坏 3mf 优雅失败 | business P3-12 | 错误对话框出现 + app 存活 + 好项目二次加载模型到达 | m3c_corrupt_3mf.py | ✅ |
| 多板项目 Slice all | business P0-3 | Slice all 模式选中 + done 态（模型到达由切片成功兜底） | m3f_multi_plate.py | ✅ |
| 预设切换→gcode header | business P0-2 | combo 切 0.40↔0.24 @U1 + 重切 + 导出 + `; layer_height` 跟随 | m3e_preset_switch.py | ✅ |
| 参数改→重切→gcode diff | business P0-1 | **WM_SETTEXT + WM_KILLFOCUS 驱动真实提交链**（Field.cpp 的 wxEVT_KILL_FOCUS→propagate_value）：Edit 文本改 + 按钮回 idle + 重切 + 导出 + `; layer_height` 0.4→0.2 + 字节 diff | m3d_param_reslice.py | ✅ |
| 删除/清空场景 | business P1-7 + P2-8 | dropdown 菜单→Edit 子菜单→真实点击 Delete All 行：viewport 色度回落空床（<0.4%）+ 空场 Slice 拒绝 | m3b_delete_scene.py | ✅ |
| 导出 3mf→重载 | business P0-4 | File 菜单→Save Project as→保存对话框→文件落盘：zip 有效 + 3D/3dmodel.model 存在 + `printer_settings_id` 保留 "Snapmaker U1 (0.8 nozzle)" + 二次启动模型到达（≥1%） | m3g_export_3mf.py | ✅ |
| undo/redo 恢复场景 | business P1-6（菜单半）+ P1-7/P2-8 | Edit 菜单 Delete All 清场 → Undo 行真实点击→模型复现（≥1% 双轮）→ Redo 行→再度清场（<0.4%） | m3h_undo_redo.py | ✅ |
| View 菜单视角切换 | —（白盒无此用例；源码入口 add_common_view_menu_items，MainFrame.cpp:2470） | View 子菜单 Top/Front 行真实点击：两次切换各使 viewport 显著变化（diff>10，实测 45/116）——视角矩阵外部不可读，不做具体角度断言 | m3i_view_menu.py | ✅ |

### 受限 / 待办（B 层）

| 用例 | 白盒引用 | 状态与原因 |
|---|---|---|
| 对象变换（gizmo） | P1-5 | 🟡 gizmo 拖拽深度交互，断言弱——B 层 |
| 画布选中+Delete 键 | P1-7 变体 | 🟡 GLCanvas3D::on_char 的 WXK_DELETE 需先有选中（画布点击命中测试深），当前由菜单 Delete All 覆盖断言面 |

### 混色匹配（MixedFilamentBatchDialog，2026-08-29 批次，飞书表 48 条）

> 入口：'Color Mixing Match' 标题栏右端 add 按钮（Plater.cpp:2578，门控=模型颜色+≥2 耗材）。
> 弹窗 = 原生模态 #32770；内部控件点击**不带 root**（弹窗是独立顶层，root 解析在 frame 树内）。
> **U1 0.8 nozzle 无 Full Spectrum 预设** → Auto 模式 Start Matching 必弹喷嘴警告
> （MixedFilamentBatchDialog.cpp:2290，=飞书 #49）——确定性可测行为。Manual 模式不受影响，可完整跑匹配。

| 用例 | 飞书记录 | 外部断言 | 脚本 | 状态 |
|---|---|---|---|---|
| 入口+默认模式+喷嘴警告 | #29/#1/#49 | 有颜色模型→弹窗出现；combo 默认 'Auto'；Auto Start→警告弹窗（'Got it' 可关）+ 弹窗存活 | m3j_mixing_entry.py | ✅ |
| Manual 匹配全流程 | #10/#15/#27 | combo 切 Manual（popup 行 2 + 文本确认）→ Start→映射列表色度渲染（0→~0.12 双轮）→ Confirm 关闭弹窗→app 存活模型在 | m3k_mixing_match.py | ✅ |
| hover 色块→ΔE tooltip（OCR） | #24/#22 | Manual 匹配→真实鼠标移动悬停色块行→tooltips_class32 出现→Tesseract OCR 读出 `'Color Difference: Good (AE=0.0)'`→断言标题+等级关键词（Good/Fair/Poor）+ `AE=` 数值 | m3l_mixing_delta.py | ✅ |

**OCR 技术事实（2026-08-29 实测）**：本机 Windows OCR 只有 zh-CN 语言包（英文 UI 文本噪声大，`try_create_from_language(en-US)` 返回 None）；**Tesseract 5.4（eng）对文案零误差**（警告弹窗全文、tooltip `'Color Difference: Good (AE=0.0)'` 逐字可读）——落地 `harness/ocr_util.py`（pytesseract + PrintWindow + 3x 放大）。**wx 系统 tooltip 只跟踪真实鼠标输入**（SetCursorPos / WM_MOUSEMOVE 注入不触发，须 SendInput `MOUSEEVENTF_MOVE`）；映射列表色块行是匹配后新增的 93x36 panel（y 797-885）。

**其余 48 条归类**（可测性分层，后续按需扩展）：

| 层 | 记录（飞书 ID） | 说明 |
|---|---|---|
| A 可黑盒（待扩展） | #3/#4/#5/#6/#7 自定义耗材选择与增删、#14 原模型视图、#20 匹配中（进度条+Stop 按钮已观测到）、#21/#22/#24 映射列表与色差（hover tooltip OCR）、#25/#26 取消二次确认、#28 无模型提示、#30 多模型、#31-35 物理耗材数量边界（需换 fixture/改耗材列表）、#37/#40/#41 模板与层高、#46/#47 64 色/双拼、#48 持久化（.3mf 重载） | 交互可驱动 + 外部产物可断言 |
| B 弱覆盖/降级 | #2/#8/#9/#23 hover 文案与提示、#38 tooltip、#45 工艺配置默认值、#17/#18/#19 视角盘切换（弹窗内视图区像素 diff）、#39 模板切换确认 | 视觉冒烟或断言弱 |
| C 黑盒不可测 | #11 色域比例/ΔE<1 纯耗材、#13 色域提醒阈值、#42/43/44 兼容性内部判定、#50 空记录 | 内部数值/矩阵，需白盒兜底或接受风险 |

### C 层（黑盒不可测，存量白盒兜底）

instance 矩阵精确值、slice_result_valid 标志、preset 脏状态、切片几何正确性、
纯后台逻辑（Sentry/更新/崩溃恢复）、网络设备栈。

## 关键源码事实（调研沉淀，改 app 时复查）

| 事实 | 出处 | 对策 |
|---|---|---|
| 导出 gcode 可用 = `can_export_gcode()`：模型非空 + `is_slice_result_ready_for_print()` + 不在导出中 | MainFrame.cpp:1600 | **完成检测 = 探测式点击 Export**：对话框出现=完成（确定性信号，优于绿勾模板） |
| Slice 按钮禁用门链：slicing 中 / only_gcode_mode / 已切片 / 不可切 / 混色不兼容 / 冷板 / flow_ratio 零 | MainFrame.cpp:1989 | 空场景/不可切时点击被吞 = 负向断言 |
| Slice/Export 是 topbar 右侧竖排 SideButton（自绘 wxWindowNR，**无子 HWND**） | MainFrame.cpp:1742/1862 | 枚举 + GetWindowText + rect 定位（export_util.topbar_buttons）；label 变长会把 Slice 挤左——**每次重新枚举，禁止缓存坐标** |
| 导出模式切换：点 print 下拉（主按钮左邻空文本按钮）→ SidePopup（独立顶层 'panel'）→ 行含 'Print'/'Export G-code file'（**顺序不保证**，枚举/排序） | MainFrame.cpp:1862 | popup 行点击**不带 root**（popup 在 root 树外，root 解析会 dismiss 假成功） |
| 导出对话框 = 原生 #32770 'Save G-code file as:'；文件名 Edit；**Enter 不触发保存**——WM_COMMAND IDOK 才落盘 | 实测 | export_util.export_gcode：枚举 Edit → 键入全路径 → `SendMessage(dlg, WM_COMMAND, 1, 0)` |
| **SendMessage 点击不转移 Windows 焦点**：wx 字段（Edit）永不进入编辑态 → Ctrl+A/键入/Enter 提交全部失效；AttachThreadInput+SetFocus 在本机返回 0 | 实测 | 字段级参数编辑（P0-1）**黑盒不可行**——断言面由预设切换（P0-2）覆盖；预设 combo 是自绘控件（wx 内部处理点击），无焦点问题 |
| 预设 combo（'0.40 Standard @Snapmaker U1...' wxWindowNR, 屏幕 y~765）点击 → SidePopup 列表（**行自绘无子控件**，28px 行距） | 实测 | 坐标试错选行：每行点击→读 combo 文本确认→重开 popup 试下一行（m3e.switch_preset） |
| 打印预设名：`0.24/0.40/0.32/0.48/0.56 Standard @Snapmaker U1 (0.8 nozzle)`（实测列表序） | wx_gui_business_tests.cpp:337 | combo 黑盒切换（坐标试错） |
| Delete all = Ctrl+D，topbar 顶层菜单下 | wx_gui_business_tests.cpp:588 | **SendMessage 键盘不触发 wx accelerator**（走消息循环）——B 层待办 |
| fixture：mixed_filament_test.3mf（U1 0.8 + 0.40 Standard 嵌入）、snapmates_nonmixed.3mf（7 板，非混色）、Prusa.stl（单对象） | wx_gui_business_tests.cpp:20 | U1 限定直接可用；**Prusa.stl 无嵌入预设 → fallback 不可切片（Slice disabled）→ 弃用作 fixture** |
| 每用例 fresh datadir + fresh launch → 无 preset 脏状态泄漏（白盒的坑黑盒天然免疫） | README 坑 #1 | 默认 fresh |
| 顶栏 File/下拉工具 = wxAuiToolBar 内自绘项（**单 HWND 无子控件**）；`BBLTopbar::OnMouseLeftDown` 用 `FindToolByCurrentPosition()`（**真实光标位置**）决定拖窗还是 Skip 给工具 → 消息点击前必须 `SetCursorPos` 到工具上 | BBLTopbar.cpp:213/663 | topbar_util.click_topbar_tool：SetCursorPos + msg_click_screen，按 x 偏移探测（File~10-40、下拉~70-100 @96dpi）；菜单在 DOWN handler 内 PopupMenu（SendMessage 超时 3s 属预期） |
| 顶栏菜单 = 原生 TrackPopupMenu（#32768）；**其状态机在菜单模态循环里**：SendMessage/PostMessage 的键与点击一律不生效 | 实测（键：无高亮；点击：菜单不关） | 顶层项用 `WM_COMMAND(item_id)` 直发 frame（wx 经 wxCurrentPopupMenu→MSWCommand→FindItem→SendEvent 分发，m3g 验证）；**子菜单行用真实输入 SendInput 点击**（模态循环只认真实输入，m3b 验证） |
| File 菜单子菜单项（Import 3MF）经 WM_COMMAND 可分发；**dropdown 菜单（Edit/View/Help）的子菜单项 WM_COMMAND 不分发**（实测 Preferences 顶层可、Delete All 子层不可，原因未明，不深究） | 实测对比 | 规避：dropdown 子菜单一律真实点击；File 菜单顶层项用 WM_COMMAND（m3g） |
| 菜单行几何：行高 ~20px、**首行起点比 top+2 低 ~12px**（naive 公式偏上 12px）；行点击后菜单关闭=命中可选项 | 实测（m3b 探针 y=300 命中 Delete All） | topbar_util.submenu_row_candidates：以 base 为心 ±6px 步进探针，结合"菜单关闭+模型消失"判定 |
| SendInput 真实输入本机**可用**（2/2 投递，README 环境矩阵已过时）——但 WebView2 透明宿主（Chrome_RenderWidgetHostHWND 全屏）**吞掉 app 窗口区域的真实点击**；模态菜单在 z-top 不受影响 | 实测 2026-08-29 | 真实点击只用于菜单行（顶层窗口）；app 区交互仍走消息注入（deepest_child_at 穿透） |
| 字段提交链：Orca 设置字段（Field.cpp TextCtrl）只在 **Enter（wxEVT_TEXT_ENTER）或失焦（wxEVT_KILL_FOCUS）** 时 propagate_value；WM_SETTEXT 只改文本不提交 | Field.cpp:782/814 | **WM_SETTEXT + SendMessage(WM_KILLFOCUS)** 驱动真实提交链（m3d GREEN）——字段级参数编辑黑盒可行 |
| GLCanvas3D::on_char 自带 Ctrl+D→EVT_GLTOOLBAR_DELETE_ALL、WXK_DELETE→DELETE（画布级绑定，不走 wx accelerator）；但需画布持有**真实焦点**且修饰键来自线程 GetKeyState（外部不可设） | GLCanvas3D.cpp:3344/3368 | 画布路径仅备选；删除断言面由菜单路径覆盖 |
| **app 加载 3mf 会改写源文件**：`Metadata/model_settings.config` 的 `identify_id` 被重写（90→78 实测）——fixture 用后可能变脏 | 实测 2026-08-29（m3g 运行后 fixture 35543→35544B） | 提交前 `git status` 检查 tests/data/test_3mf/，脏 fixture 恢复 HEAD（app 副作用，非用户改动） |

## 导出原语（Tier 0）

```
export_gcode(session, out_path):
  1. 等 Slice done（绿勾模板，粗观察）
  2. 探测式点 Export 按钮（m_print_btn 区域）→ 等模态保存对话框出现（EnumWindows 找同进程新顶层窗口）
  3. 对话框内键入完整路径（WM_CHAR/msg_text）→ 回车（WM_KEYDOWN VK_RETURN）
  4. 等文件落盘 → 校验非空
  5. 若覆盖确认对话框（同名文件）→ 回车确认
```
