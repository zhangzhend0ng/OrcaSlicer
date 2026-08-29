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
| 参数改→重切→gcode diff | business P0-1 | **断言面由 P0-2 覆盖**（预设切换同为"参数变化→gcode 变化"） | — | 🟡 字段编辑焦点受限 |

### 受限 / 待办（B 层）

| 用例 | 白盒引用 | 状态与原因 |
|---|---|---|
| 删除/清空场景 | P1-7 + P2-8 | 🟡 Ctrl+D 键盘加速键不被 SendMessage 路由（wx accelerator 走消息循环）；顶栏菜单入口为自绘 logo（无 HWND）；画布选中+Delete 依赖 GL 画布焦点——B 层待办 |
| 导出 3mf→重载 | P0-4 | 🔵 导出 3mf 的 UI 入口未定位（文件菜单为自绘 logo）——待办 |
| 对象变换/undo-redo | P1-5/6 | 🟡 gizmo 拖拽深度交互，断言弱——B 层 |

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

## 导出原语（Tier 0）

```
export_gcode(session, out_path):
  1. 等 Slice done（绿勾模板，粗观察）
  2. 探测式点 Export 按钮（m_print_btn 区域）→ 等模态保存对话框出现（EnumWindows 找同进程新顶层窗口）
  3. 对话框内键入完整路径（WM_CHAR/msg_text）→ 回车（WM_KEYDOWN VK_RETURN）
  4. 等文件落盘 → 校验非空
  5. 若覆盖确认对话框（同名文件）→ 回车确认
```
