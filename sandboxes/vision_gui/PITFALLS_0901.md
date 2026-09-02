# vision_gui 黑盒套件 — 0901 踩坑实录（最大化 + m5 主流程）

按"现象 → 根因 → 修法 → 证据/复跑"汇总 2026-08-31 ～ 09-01 的全部坑。
复跑入口：`hv_go.ps1 -Cases <diag 脚本名>`（诊断脚本都在本目录，日志落
`artifacts\regress_<名>.log`，帧落 `artifacts\` 与 `artifacts\shots\<case>\`）。

---

## 1. Hyper-V 控制台分辨率自动跌落（本轮最大坑）

- **现象**：m5b/c/d"侧栏坍缩"、OCR 全空、`options_viewport None`，帧尺寸
  1366×751 → 误判为"窗口被还原/布局坍缩"，查了 ensure_advanced、tab 点击
  等一路弯路。
- **根因**：VMConnect 控制台断开/变化后，客机显示模式**自动降级**
  （1920×1080 → 1366×768 → 1024×768）。最大化的窗口跟着屏幕缩——不是窗口
  问题，`ShowWindow(SW_MAXIMIZE)` 修不了（实测 re-maximize 后 rect 仍是
  `(-7,-7,1373,727)` = 小屏上的最大化）。所有按 1920×1032 client 标定的
  判定全部失效。
- **修法**：重启 VM（控制台重连）+ 保持一个 vmconnect 会话 +
  `setres_1080.py`（交互会话内 ChangeDisplaySettings 1920×1080，rc=0 且
  生效）。跑套件前必查分辨率。
- **证据/复跑**：`setres_1080.py`（自报交互会话分辨率）；diag 日志
  `re-maximized: rect=(-7,-7,1373,727)`。
- **附**：PS Direct 会话里 `Screen.AllScreens` 的读数（1024×768）是它自己
  会话的，**不代表交互桌面**，不可信；要在交互会话内读
  （GetSystemMetrics / setres 自报）。

## 2. 空盘启动三重坑：Setup Wizard + 无打印机 + 工艺预设下拉为空

- **现象**：空盘 boot 弹 `#32770 'Setup Wizard'`（820×660，盖在最上方）；
  Printer 区空、无喷嘴直径；**Slice 按钮灰**（无法切片）；工艺预设下拉
  只有 `Default Setting` 一项（System presets 分节头是空的）。
- **根因**：未选打印机触发首启向导 + Slice 门禁；且工艺预设库按
  **打印机预设名**过滤——`0.24 Standard @Snapmaker U1 (0.8 nozzle)` 的
  `compatible_printers = ['Snapmaker U1 (0.8 nozzle)']`，基础版
  `Snapmaker U1`（0.4 喷嘴）不匹配任何一个，全部被滤掉。
- **修法**：m5 弃用空盘启动 → **fixture 上下文 boot**（3mf 内嵌
  U1 (0.8 nozzle) 打印机 + 0.40 工艺预设）→ 删除载入模型 → 右键加标准
  Cube。预设下拉随即列出全部 U1 0.8 系统预设（0.24/0.32/0.40/0.48/…）。
- **备选**：向导本身 `WM_CLOSE` 可直接关（diag 验证 `wizard closed: True`）；
  "配置掉"需补"已选打印机"相关 conf 键，未验证。
- **证据/复跑**：`diag_m5_wizard.py`；录像里若见欢迎页遮挡即此（空盘 boot
  才有；fixture boot 的正式录像没有）。

## 3. Setup Wizard 是 HTML（wxWebView）

- **现象**：向导内没有可枚举的原生按钮（children 只有 wxWebView/
  Chrome_RenderWidgetHostHWND），OCR 定位按钮 + 相对坐标点击太脆。
- **修法**：不驱动它——绕开（见 #2）或 WM_CLOSE。**HTML 界面一律不碰**。
- **证据/复跑**：`diag_m5_wizard.py` v1。

## 4. 真右键被远控层吞掉

- **现象**：SendInput 右键 3/3 无效（菜单不弹），同点位 message-level
  `WM_RBUTTONDOWN/UP` 100% 弹出原生菜单。
- **修法**：`add_shape.py` / `m5_common.py` 一律 msg 右键开菜单 +
  **真实左键**点行（原生菜单跑模态循环，message 左键点不动行——沿用
  topbar_util 结论）。
- **证据/复跑**：`diag_m5_menu.py` v2/v3。

## 5. 右键菜单行定位：序列匹配 + 坐标空间

- **现象**：'Delete All' / 'Select All' / 'Delete Plate' 都含 "Delete"或
  "All"，子串匹配会点错；曾因菜单截图相对坐标被当屏幕绝对坐标使用，点到
  屏幕左上角把应用点死。
- **修法**：`m5_common._seq_point(mr, words, seq)` 词**序列**匹配且一律加
  菜单 rect 偏移；`_delete_row_point` 优先 'Delete All'，裸 'Delete' 排除
  后缀 'Plate'。
- **证据/复跑**：`diag_m5_menu.py` v3（Cube 落盘全链路）。

## 6. 选项面板 combo：值是绘制的、无窗口文本

- **现象**：Seam position 的 'Aligned' OCR 得到，但 GetWindowText 为空；
  dialog 式 `switch_combo`（wxWindowNR 'panel' 弹窗、28px 行）不适用——
  点击落到 `hwnd 0x0`。
- **根因**：选项面板的值由 OG_CustomCtrl **绘制**，控件本身无文本；且其
  下拉不是 dialog 的 panel 弹窗。
- **修法**：`process_panel.find_option_combo` = OCR 找值文本 →
  `WindowFromPoint` 解析真实控件；`cycle_combo_to` = 真实点击聚焦 →
  方向键 + 回车逐项切换 → OCR 验证提交值。
- **证据/复跑**：m5b/m5d 日志（cycle 逐步打印）；m5a 的预设选择器走的是
  真文本（'0.40 Standard …'），两者机制不同。

## 7. 参数目标必须先实证标签存在（Quality 页没有 'Wall loops'）

- **现象**：按上游 Orca 习惯去 Quality 页找 'Wall loops'，OCR 轮询 6 次
  全空；Seam 组滚动定位一度 420s 超时。
- **根因**：这个 fork 的 Quality 页 'Walls and surfaces' 组只有两个
  Only-one-wall 复选框；**'Wall loops 2' 在 Strength 页顶部**。
- **修法**：选参数前先用 diag/帧确认标签在哪个页面；click_tab 的
  expect_word 用**首屏可见**内容（Strength 页 = 'loops'，不是 'infill'）。
- **证据/复跑**：m5c 日志 band 打印 `'walls wall loops 2 alternate …'`。

## 8. Tree (auto) 支撑在 U1 0.8 预设上配置非法

- **现象**：Enable support 勾选后 Slice 按钮变灰，红色错误 toast
  "Organic support tree tip diameter must not be smaller than support
  material extrusion width"；切片模板匹配 0.666（done/灰特征）。
- **根因**：默认 Type=Tree (auto) 的有机树尖端直径与 U1 0.8 预设的支撑
  挤出宽冲突，配置校验失败禁用切片。
- **修法**：m5d 勾选后把 Type 组合框切到 Normal（cycle_combo_to）。
- **证据/复跑**：`shots/m5d_support_enable/L010`（灰按钮 + 错误 toast）。

## 9. 小模型的"落盘"判定阈值

- **现象**：右键 Cube 已落盘但判定 FAIL（chroma 0.581% < 0.006）。
- **根因**：0.006 是按 mixed fixture 大模型标的；20mm Cube 在 1920 视口里
  只贡献 ~0.58%。
- **修法**：`add_shape.py` 落盘判定改为 `≥0.003 且 >3×空盘基线`
  （空盘 ~0.063%）。

## 10. seed PermissionError（datadir 被上一个 app 占住）

- **现象**：套件首例 `seed_profile` 在 rmtree m3_profile 时
  `WinError 32 … log\*.log.0 being used by another process`。
- **根因**：上一用例 app 的收尾竞态（graceful close 未完全退出）持有日志
  句柄；套件背靠背启动时必现。
- **修法**：`profile.py` seed 前先 `taskkill /IM snapmaker-orca.exe /F` +
  rmtree 重试 ×3（间隔 3s）。另：跑套件前先经 relay 杀孤儿
  （`Get-Process snapmaker-orca,python | Stop-Process -Force`）。

## 11. hv_go 重复启动 = 双实例互踩

- **现象**：误触发两次 `hv_go.ps1`：第二个实例重新注册同名计划任务，两套
  driver 在同一桌面互打（输入注入互相吞），日志/帧污染，排查极难。
- **修法**：launch 前 `(Get-ScheduledTask suite).State` + 客机 python 进程
  数确认；套件运行中**绝不**重复启动。

## 12. m4e/m4g/m4i 最大化重校准（详见 commit 9e23500991）

- m4e：工具栏扫描带/质心带/调色板带全部改为视口自适应；"已选中"判定改用
  扫描定位的**真 Rotate 槽位**（固定 x 在最大化后读到相邻 tooltip 假阳性）。
- m4g：视口 panel 高度帽（73px→随窗口拉伸）→ 滚轮静默失效；`view_band()`
  动态 OCR/验收带；勾选阈值 0.25→0.13（实测选中 0.21 / 未选 ≤0.06）；
  tab 切换 40 格强制回顶（滚动位置跨页共享）。
- m4i：`export_util.topbar_buttons` 改窗口相对带（绝对 y140-170/x>1150 只
  匹配一个窗口化位置）。

## 13. 侧栏布局双形态 → 锚定式定位

- **现象**：同一套 y 带在 fixture boot 全绿、空盘 boot 全空（Process 行
  614 ↔ 462，差 ~150px；空盘预设行文本是 'Default Setting'）。
- **修法**：`process_panel.process_row_y()` 以 'Process' 标题行为锚，
  advanced/tabs/viewport/组定位全部相对化；两种 boot 通吃（m4g 回归绿）。

## 14. 工具链小坑（relay/bash/PS Direct）

- bash 双引号里 `\$f` 是**字面量 `$f`**（两次踩：路径带 `$f` 去了不存在的
  文件）——循环推文件用 `var="..."; "…/$var"` 或逐条写全路径。
- PS Direct 的 `byte[]` 返回值不可靠（0 字节）→ 客机内 base64 编码成
  **字符串**回传，宿主解码（`fetch_mp4.py` / `send_to_guest.ps1`）。
- 经 relay 的 PS 命令里 `Select-String "a|b"` 的管道符会被转义损坏 → 拉
  日志直接 `Get-Content -Tail N`，过滤在宿主侧做。
- 多行 python 补丁脚本里的 `\\` 续行/花括号转义极易错——补丁后必须
  `py_compile` + grep 断言确认替换真的发生。

## 15. 跑套件前 checklist（血泪浓缩）

1. relay 心跳（`relay_alive.txt`；注意它只在命令完成时刷新）
2. 客机杀孤儿（relay → `Stop-Process snapmaker-orca,python`）
3. 客机交互分辨率 = 1920×1080（`hv_go -Cases setres_1080` 看自报）
4. 无残留 suite 任务实例（`(Get-ScheduledTask suite).State`）
5. 长等待用后台任务（单条 bash ≤10min）；录像/大文件走 base64 relay


## 16. 宿主↔客机通信通道规范（血泪协议）

**通道选择**（每条都有实测翻车记录）：

| 用途 | 通道 | 备注 |
|---|---|---|
| 宿主→客机文件 | `send_to_guest.ps1`（base64 经 relay） | 唯一可靠上行 |
| 客机→宿主文件 | base64 字符串经 relay_out（`fetch_mp4.py`） | PS Direct 的 `byte[]` 返回值不可靠（0 字节实测） |
| 客机内命令 | relay → `Invoke-Command -VMName`（PS Direct） | 非交互会话：GUI 判定必须走 hv_go 的 INTERACTIVE 计划任务 |
| 大文件 | 逐文件 base64，~7MB/文件 ~20s/文件 | 209MB/27 文件实测 ~15 分钟 |

**推送纪律**（每次推送后必须做，血泪教训）：

1. 看排队回显：`queued (0 KB)` = 推送路径错误（bash 双引号里 `\$var`
   变字面量等），`queued (N KB)` 才是出队成功。
2. **推送后必须双端 MD5 比对**——relay 命令会被后续命令覆盖、bash 转义
   会静默失败，"没推上"伪装成"修复无效"能烧掉几小时。用
   `C:\coilm_setup\push_verify.py <local> <guest>`（推+校验一体，
   MD5 不匹配退出码非 0）。
3. relay 命令文件是单槽的：连续两次推送中间必须等 relay 消费（文件
   被删除），否则后一次覆盖前一次——静默丢命令。

**relay 应答解析竞态**（`fetch_mp4.py` v2 的规则）：relay_out.txt 里
上一次的 `=== DONE` 还在，只等 DONE 会读到旧应答。必须等三件事同时
成立：①首行 `=== RUN` 时间戳与发送前不同；②出现 `=== DONE`；③文件
大小连续两次采样不变。

**PS Direct 陷阱**：

- `Screen.AllScreens` 的读数是 **PS Direct 自己会话的**，不代表交互
  桌面（实测它报 1024×768 而交互桌面是 1366/1920）——分辨率只能在
  交互会话内自报（如 `setres_1080.py` 走 hv_go）。
- 复杂 PowerShell（多层引号/管道/Here-String）内联进 relay_cmd 必炸
  （实测 `Select-String "a|b"`、Add-Type C#）——写成 `.ps1` 文件用
  `& 文件名` 调用（见 `clean_guest.ps1` / `max_vmconnect.ps1` 模式）。
- `Set-VMVideo` 单独设置不生效（枚举是 Maximum/Single/Default；且需
  控制台 attached）——恢复分辨率用「重启 VM + 保持 vmconnect 最大化」。

**双套件互踩**（§11 的补充细节）：hv_go 的 Unregister+Register **不会
杀掉运行中的任务实例**——上一套件没跑完就启新一轮，两个驱动 +
两个 app 争抢全局输入注入和同一个 datadir，失败模式完全不确定（实测
m5b 三个不同断言在三轮里各挂各的）。启新套件前：`clean_guest.ps1` 杀
孤儿 + 确认上一套件 SUMMARY 已出。

**通信工具清单**（`C:\coil\vm_setup\`，未入仓库）：
`push_verify.py`（推+校验一体）/ `fetch_mp4.py` + `fetch_all_mp4.py`
（guest→host base64，v2 修了 DONE 竞态）/ `fetch_relay.sh`（单文件
bash 版）/ `clean_guest.ps1`（杀孤儿）/ `max_vmconnect.ps1`（控制台
最大化，分辨率恢复用）。

---

## 17. 0902 补充：m5e–m5h 轮实测新坑

### 17.1 hv_go 必须在提权 PowerShell 里跑
- **现象**：非提权 bash 里 `powershell -Command "& hv_go.ps1 ..."` 照样
  打印 `[4] DONE`，但客机侧什么都没发生（任务/progress/log 全是上一轮
  的遗留）——`Get-VM` Permission denied 被 tail 截掉。
- **修法**：hv_go 一律经 elevated relay 跑：
  `relay_run.py "& hv_go.ps1 -Cases ..."`。
- **佐证**：log mtime + `progress_tail` 是旧的 = 启动没生效。

### 17.2 PS Direct 查询一律写成 .ps1 探针文件
- **现象**：经 relay 的内联 `Get-Content/Get-ChildItem | ...` 命令间歇性
  返回空；`Format-List` 多行输出被 Out-String 吃行。
- **修法**：宿主侧写专用探针 `zstate.ps1 / zlog.ps1 / zshots.ps1 /
  zfind.ps1`（字符串拼接输出 + `-ArgumentList` 传参），relay 只
  `& 文件`。
- **附加坑**：`relay_run.py` 读取端 v1 把正文第一行当头行丢掉——单行
  应答读成空串。已修（raw 直接 rsplit DONE）。

### 17.3 宿主→bash→heredoc 的反斜杠会被吃掉一层
- **现象**：bash heredoc python 里写 `"C:\\coil\\vm_setup"`，落盘内容是
  `C:\coil\x0bm_setup`（`\v` = 竖直制表符！）——`\\v` 经工具层解码一次
  变 `\v` 再被 python 转义。
- **修法**：heredoc python 里路径一律 `r""` 原始串或纯 argv 传参；绝不
  手写双反斜杠。

### 17.4 neutralize_focus 的 ESC 会回退"刚 Ignored"的字段值
- **现象**：m5f 里层高 1.0 → Adjust/Ignore 对话框点 Ignore（值保留
  1.0），若**紧接着** neutralize_focus（先发 ESC），ESC 把字段回退到
  提交前值（0.16）→ 配置恢复合法 → Slice 复活，"1.0 拒绝切片"断言
  随机翻车。
- **修法**：依赖"Ignore 保留值"的断言窗口内**禁止任何 ESC**；恢复焦点
  挪到断言之后。

### 17.5 模态框关掉后下一次真输入可能失焦（焦距死区）
- **现象**：m5f run1：Ignore 点击后 real_edit_set 连续 4 次拿不到焦点，
  输入全吞；`E-pre toplevel` 抓到无关的 `#32770 'Snapmaker Orca info'`
  漂浮窗（不挡点击）。
- **修法**：断言窗口过后 neutralize_focus（ESC + Process 标题行点击）
  即恢复；E/F 步已内建重试+取证打印。

### 17.6 层高越界对话框的真实边界来自 3mf 内嵌机器预设
- **事实**：fixture（Snapmaker U1 0.8 nozzle）运行时边界
  min=0.16 / max=0.56（m5b gcode echo 实证；任务表与 m4g 注释里的
  0.32/0.08 是 fdm_U1 基础值，stale）。
- **行为**（Tab.cpp:1778-1812 实测复现）：界内 0.4 无对话框；0.04 →
  "exceeds the limit" Adjust/Ignore 对话框，Adjust→0.16；0 →
  "too small" OK 对话框自动置下限；1.0 → Ignore 保留 → Print::validate
  失败 → Slice 置灰（0.666 灰特征）+ 红色错误 toast；'abc' →
  "Invalid numeric." → 字段重写为 0 → 级联 too-small 对话框 → 0.16。

### 17.7 OCR psm3 会被 '-----' 分隔线艺术字搞瞎
- **现象**：工艺预设下拉的 `------- User presets -------` 区头让
  tesseract psm3 整块丢行——`m5g_flow_preset` 行明明在截图里，词表里
  就是没有；psm 6 全部读出。
- **修法**：`ocr_words_img(img, scale, psm=...)` 加参数；列表类截图
  （popup、分区列表）一律 psm=6。

### 17.8 预设管理的黑盒坐标（m5g 全链路实测）
- **Save/Delete 按钮**：在**预设行**（Process 锚行 +20..+70px），不在
  Process 标题行（那行是 Advanced 开关 + view/compare 图标，x 314-341
  的 btn 是 Advanced 开关本体，点击/悬停都无反应）。软盘 tooltip
  'Save current Process'；删除 cross 只在选中用户预设时出现。
- **SavePresetDialog**：#32770 'Save preset'，名称 Edit 有预填文本且
  实时生效（**不需要 Enter**）；'User Preset'/'Preset Inside Project'
  单选与 'OK'/'Cancel' 全是 wxWindowNR 类（按 class 找 Button 会扑空，
  必须按文本找）。
- **落盘**：`<datadir>/user/default/process/<name>.json`（+
  .info），不是 `<datadir>/process/`。
- **重启**：空盘重启不恢复打印机上下文，预设列表只剩 'Default
  Setting'（=PITFALLS #2）；带 fixture 3mf 重启则列表完整（User
  presets 分区在 System presets 之上，psm6 可读可点）。
- **删除确认**：'Delete Preset' / 'Are you sure you want to Delete the
  selected preset?' Yes/No。

### 17.9 Ironing Type 提交后：重建期滚轮会杀死 app
- **现象**：Ironing Type popup 行点击后立刻 scroll/hunt，PrintWindow
  报 DC 失效（app 进程已死）两次；type 提交 + 12s 长静置 + tab 往返
  （Strength→Quality 复位 viewport）则稳定。
- **配套事实**：Ironing Type 行在组内**最底部**（下面就是 Wall
  generator 组标题）；Pattern 行的绘制值 psm3/psm6 都读不出、
  WindowFromPoint 也只解析到容器 panel——m5h 的第二个 combo 用 Seam
  position（'Aligned' 值 OCR 稳定）替代，Type+Seam 双 combo echo
  全绿。

### 17.10 子菜单展开过的原生菜单，WM_CANCELMODE 关不掉
- **现象**：m4d merge 步（回归 RED，solo 复跑也 RED，2/2 确定）：
  读 submenu targets（hover 展开 'Merge with' 子菜单）后
  `close_entry_menu`（WM_CANCELMODE）不生效——mp4 帧显示菜单一直开着，
  后续 re-open 的真实点击全打在悬浮菜单上，`wait_menu_popup` 5s 超时
  → "options menu did not open" ×3。
- **修法**：菜单模态循环只认真实输入（m3b 先例）——真实 **ESC ×2**
  （关子菜单 + 关主菜单）再 close_entry_menu 兜底；merge 重试环每次
  尝试前也补一发 ESC。修复后 solo GREEN 且 35 例回归全绿。
- **通用化**：任何"hover 展开过子菜单"的菜单，关闭一律先真实 ESC。

