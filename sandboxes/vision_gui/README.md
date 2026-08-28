# vision_gui — MAA/ok-ww 式黑盒视觉 GUI 测试沙盒

对 `snapmaker-orca.exe` 做**外部黑盒**驱动：截图 → 模板匹配定位 → 消息级输入注入 →
截图断言。全程不接触 app 内部 API（与 `tests/wx_gui/` 的进程内白盒路线互补）。

- 范式参照：[MaaAssistantArknights](https://github.com/MaaAssistantArknights/MaaAssistantArknights) /
  [ok-wuthering-waves](https://github.com/ok-oldking/ok-wuthering-waves)
- 引擎选型：**MaaFramework (pip MaaFw) 优先**，其 Win32 控制器消息注入若无法路由到
  wx 子控件，则用 Python 自定义 action（`WindowFromPoint`+`SendMessage`，见
  `harness/winutil.py`）补洞；纯自研兜底。

## 目录

```
harness/            驱动核心（纯 ctypes，零第三方依赖即可跑 m0）
  winutil.py        眼睛+手：EnumWindows/PID 定位、PrintWindow(FULLCONTENT) 截图、
                    WindowFromPoint+SendMessage 点击（远控免疫）、WM_CHAR 键入
  env_check.py      环境预检（GameViewer 等远控层、DPI）— 移植自 wx_gui 的 C++ 门禁
  profile.py        沙盒 datadir 种子（**数据源 = 仓库/exe resources，非用户 %APPDATA%**）
  launcher.py       黑盒启动（显式剥除 ORCA_GUI_TEST_MODE！）
m0_boot_check.py    里程碑0：启动→定位→截图→关闭 冒烟
ui_runner.py        薄 UI 封装（CustomTkinter）：选模型→跑 m1/m2/批量→流式日志
                    + live view 截图面板（按进程名找 app → PrintWindow 轮询显示）
resource/image/     模板图（提交入库，测试资产）
artifacts/          运行产物（gitignored）
```

## 运行

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
.venv/Scripts/python m0_boot_check.py --grab     # 启动+截图（模板裁剪素材）
.venv/Scripts/python m1_minimal_loop.py          # M1：tab 切换闭环（纯自研层）
.venv/Scripts/python m1b_maa.py                  # M1b：MaaFw pipeline + 注入对比
.venv/Scripts/python m2_slice_chain.py           # M2：切片业务链（默认 fresh profile）
.venv/Scripts/python ui_runner.py                # 薄 UI 封装（CustomTkinter）
.venv/Scripts/python inspect_window.py           # 子控件枚举 + 截图（开发辅助）
```

## 实测结论（2026-08-25，本机 GameViewer 运行中）

| 实验 | 结果 | 证据 |
|---|---|---|
| m0 黑盒引导 | ✅ | seed→launch→定位→截图→关闭，全链路绿 |
| (a) 自绘 tab 消息点击 | ✅ | teal(0,150,136) 选中色像素 + 模板状态翻转 |
| (b) 原生 Edit WM_CHAR | ✅ | `'0.4'` → `'0.160.4'`（WM_GETTEXT 读回） |
| (c) GL 截图黑屏 | ✅ 无黑屏 | PrintWindow(PW_RENDERFULLCONTENT)，viewport std≈76 |
| M1 闭环（纯自研） | ✅ GREEN | click→verify→back 全通，含回弹重试 |
| M1b A：MaaFw 内置 Click | ❌ FAIL | 识别 3/3 全中，但 SendMessage→顶层 HWND 不路由到 wx 子控件，tab 从未切换 |
| M1b B：自定义 action | ✅ PASS | WindowFromPoint→子 HWND 一次成功且稳定 |
| M2 模型自动加载 | ✅ | CLI 位置参数 + fresh datadir；**启动期必须 hands-off**（早期前台/移动干预会静默杀死 input_files 自动加载）；到达检测 = viewport 彩色占比 ≥1%（空床实测 ~0.15%，模型 ~2.1%，双轮稳定确认） |
| M2 点击 Slice→切片完成 | ✅ | 完成信号 = 按钮带绿勾的 done 态模板（`slice_button_done.png`，≥0.85） |
| M2 Preview 工具路径 | ✅ | 彩色占比 ≥1% 且 ≥2× 切片前基线（混色模型 4.88% vs 1.90%；默认 Prusa.stl 2.22% vs 0.69% 亦绿） |

### ~~M2 切片冻结~~ 已撤回：真实的因果链（2026-08-26 复盘）

早期 Prusa 跑出的"切片冻结在 30%、app 侧问题"结论**是误诊**，两个叠加的驱动层 bug：

1. **launcher 启动期前台抢占杀死 CLI 模型自动加载**（排查中途引入的回归）：启动早期
   `SetForegroundWindow`/移动窗口会与 post_init 首个 idle 的 input_files 加载竞态——
   hands-off 启动（sleep 12s 不碰窗口）模型 100% 加载，有干预则静默不加载。
   模型没加载 → 点 Slice 无效果或仅按钮按压态变化 → "进度条 30% 冻结"实为无米之炊。
2. **完成检测模板错误**：切片完成后按钮渲染"Slice plate + 绿勾"，与点击前 idle 模板的
   归一化相关只有 0.666 —— 把已完成误判为"仍在切片"。

修正后（hands-off 启动 + done 模板）`混色级联删除测试.3mf`（Snapmaker U1 0.8 + 0.40
Standard 嵌入预设）端到端 GREEN。

### 切片"慢"是假象 — 实际 ~3 秒（2026-08-28 复盘）

用户反馈"切片怎么这么慢，正常 GUI 不应该"。调查结论：**切片从来不慢**，
"10 分钟"是三个叠加的测量假象：

| 假象 | 机制 | 证据 |
|---|---|---|
| "冻结在 30%"（Prusa 跑） | 模型没加载 → 切片从未开始，1500s 是**等待超时** | 无 gcode、无切片进程 |
| "10 分钟还在 42%"（3mf 跑） | **~20s 就切完了**（绿勾完成态），但旧 idle 模板对完成态只给 0.666 → 完成检测永不触发 → 空转满 1500s | done 模板对 wait2/wait10/wait150 全部 **1.0** 匹配，画面自 20s 起就是静止完成态 |
| 视觉模型"读出"5%→10%→42% 进度 | 对**静止完成态**画面的百分比幻觉 | 多轮截图字节级相同 |

修复后复测：`3.1s / 3.1s / 3.1s / 3.1s`（含 8 核 CPU hog 干扰下仍 3.1s）。
硬件 8C16T Ryzen 9700X、进程亲和性 0xFFFF（全 16 核）、TBB 全并发、模型为
单立方体——均无瓶颈。正常 GUI 不慢，本沙盒也不慢；机器空闲负载仅 ~4%。

保留有效的教训：
- `window_mainframe` 位置恢复键必须 drop（否则窗口落在虚拟屏）
- 早期窗口干预有害；后期按需干预（仅当窗口真的在虚拟屏时）才安全
- 视觉模型对低分辨率截图的"进度百分比/图标"读数可靠性有限，关键判定用模板/像素级确定性证据
- 完成信号必须用**完成态专用模板**（绿勾徽标），不能用"回到 idle"推断

### 引擎选型结论（M1b 决定性实验）

**MaaFramework 可用但注入层必须走 Python 自定义 action**：
- 可复用：pipeline 编排、模板识别循环、重试/超时、截图（`set_screenshot_use_raw_size(True)` 关闭默认 720p 降采样）
- 不可用：Win32 内置 Click——设计目标是游戏"单一大窗口"，对 wx 复合子窗口 UI 无效
- `harness/winutil.py` 的 `msg_click_screen`（WindowFromPoint+SendMessageTimeout）即是补洞层，纯自研路线也直接复用它

### 批量回归结论（2026-08-28，9 个模型）

| 模型 | 嵌入预设 | 结果 | 说明 |
|---|---|---|---|
| 混色级联删除测试.3mf | Snapmaker U1 (0.8) | ✅ GREEN | 标准样例 |
| 立方体.3mf | Snapmaker U1 (0.4) | ✅ GREEN | |
| 四料混色.3mf | Snapmaker U1 (0.4) | ✅ GREEN | 修复 WebView2 后 5/5 稳定（修复前 2/5 flaky） |
| Prusa.stl（m2 默认） | — | ✅ GREEN | 色度检测走"切片成功兜底"升级 |
| 混色.gcode.3mf | Snapmaker U1 (0.4) | ⏸ 已知限制 | 含 gcode → `only_gcode_mode` 源码门禁用 Slice 按钮（渲染 0.666）；正确测试路径是跳过切片直接验 Preview |
| lithophane.3mf | Bambu P1S | ⏸ 预期 | **混色耗材兼容门**：Color Mixing 引用缺失耗材 → Slice 禁用（切打印机无效，见坑 #10）；补 printers/ seed 后预设可加载但混色门仍挡 |
| Pikachu X1C | Bambu X1 Carbon | ⏸ 预期 | 同上 |
| A1mini+R3dPETG罗隐 | Bambu A1 mini | ⏸ 预期 | 同上 |

三类脆弱点与处理：
1. **WebView2 透明层吞点击**（间歇 flaky ~40%）→ winutil 穿透修复（坑 #9）
2. **非 U1 预设 → Slice 按钮 disabled**：gcode 项目（only_gcode_mode）与混色耗材不兼容
   （has_incompatible_mixed_filament_in_use）两条源码门都禁用按钮；打印机预设缺失时
   app 自动替换为默认（combo 显示 U1），所以"切打印机"不是解法——切耗材槽才是；
   已补 `printers/` seed（见下）消除预设缺失路径
3. **含 gcode 的 3mf**：按钮禁用（源码门）→ 正确测试 = 跳过切片直接验 Preview

附带发现与修复：
- 2.3.6 预设布局：`system/Snapmaker/{machine,filament,process}` + 独立的
  `printers/`（vendor 预设，BL-P001 等）；**seed 原先只拷 system** → Bambu 项目预设
  缺失 + 启动报 `[Orca Updater] staging validation failed (printers)`（待办 #5）。
  已修：seed 一并拷贝 `printers/`（2026-08-28）→ staging 错误消失
- 预设切换节点探索结论（未实现）：Printer combo 可黑盒切换（screen(625,279)，
  GetWindowText 可读、popup 行自绘需试错点击）；但 Bambu 混色项目被混色兼容门挡住，
  需切换耗材槽（UI 深度操作）——成本高，留作后续

### 已知坑（踩过并已规避）

1. **复用 datadir 后 CLI 位置参数不再自动加载模型** —— 首次运行后 app 写回的状态会阻断
   input_files 自动加载；M2 默认每次 fresh profile
2. **启动 tab 选择有竞态**：最终 select_tab 在 GL init 后的 CallAfter 里，且页面切换可能被
   `EVT_GLVIEWTOOLBAR_3D` 弹回 Prepare → 驱动必须 wait_for + 稳定性确认 + 重试，禁止定时假设
3. **模板必须从"稳态"截图切**：启动 ~3s 内是主题应用前的瞬态（白底），稳态是深色主题
4. **MaaFw 默认把截图降采样到 720p**：模板是原生分辨率切的，必须开 raw size
5. **"切片很慢"是测量假象**（已撤回，见上方 08-28 复盘）：实际 ~3s；完成检测超时
   给足 1500s 仅作安全阀，模型未加载时 m2 会把上限压到 60s 快速失败
6. **模板状态区分用颜色不用模板分**：tab 选中=teal(0,150,136)/未选=(59,68,70)（源自
   Notebook.cpp ButtonsListCtrl），TM_CCOEFF_NORMED 对纯背景变化不敏感（0.926 仍误判）
7. **沙盒卫生待办**：种子的用户 conf 无明显 token，但 app 启动后有云端订阅回调（WCP 日志）；
   对外交发沙盒 profile 前需核实数据面
8. **模型到达检测不能用"差分 vs 参考帧"**：模型在 hands-off 启动期内已渲染完（t=12s
   首帧即含模型），任何晚于启动的参考帧都包含模型 → 差分永不触发（m2 曾因此恒
   UNVERIFIED）。改用绝对阈值：空床彩色占比 ~0.15% vs 带模型 ~2.1%，≥1% + 双轮稳定即判定；
   低饱和模型（默认 Prusa.stl 实测仅 ~0.7%）会漏检，由"切片成功兜底升级"覆盖
9. **WCP WebView2 全屏透明层吞点击（间歇 flaky 根因）**：首页 WebView2 的渲染窗口
   （`Chrome_RenderWidgetHostHWND`，WS_EX_TRANSPARENT，全屏 1920x1040）间歇性出现在
   z-order 顶部——不绘制任何内容（截图无痕）但参与命中测试（WS_EX_TRANSPARENT 只影响
   绘制顺序），WindowFromPoint 命中它 → 注入点击被吞，m2 曾 ~40% flaky "click didn't
   take"（tab/按钮都中招）。修复：`msg_click_screen` 传 `root_hwnd`（主窗口）后改用
   `ChildWindowFromPointEx(CWP_SKIPINVISIBLE|SKIPDISABLED|SKIPTRANSPARENT)` 在 app
   窗口树内递归定位最深含点窗口——WebView2 是独立顶层窗口，天然不在树内
10. **非 U1 预设的模型 → Slice 按钮 WS_DISABLED**：预设缺失（本机无 Bambu 预设）时
    Slice 按钮 disabled，且 **WindowFromPoint 会跳过禁用窗口**返回主窗口 → 点击无效是
    app 预期行为（真实工作流：先切 Snapmaker U1 再切片）；m2 的"预设切换"节点待实现
    ——但注意源码门链（MainFrame.cpp get_enable_slice_status）：gcode 项目
    （only_gcode_mode）与**混色耗材不兼容**（has_incompatible_mixed_filament_in_use，
    项目级 Color Mixing 引用缺失耗材）都禁用按钮——**切打印机到 U1 无效**（缺失时 app
    已自动替换），正确路径是切**耗材槽**到兼容预设
11. **强杀 app 会损坏 Sentry 共享 crashpad DB → 后续启动全崩**：`session.close()` 超时
    后强杀（或外部 timeout 杀进程）会让 Sentry 的 crashpad 数据库
    （`%LOCALAPPDATA%\Snapmaker_Orca\`，**跨 datadir 共享**）处于半写状态，之后所有
    启动在 sentry_start_session 段抛未捕获 C++ 异常（0xE06D7363，静默崩溃）。恢复：
    改名/删除该目录后正常启动一次（Sentry 重建 DB）。**教训：永远用
    `session.close()` 优雅退出，不要在诊断脚本里用 timeout/kill 杀 app**
12. **窗口隐身化（2026-08-28）**：m1/m2 在 hands-off 结束后调用
    `background_tool_window()`——`WS_EX_TOOLWINDOW`（无任务栏按钮）+ `HWND_BOTTOM`
    （z-order 底部），让被测 app 不打扰用户桌面（任务栏只留 UI 壳）；launcher 启动用
    `SW_SHOWNOACTIVATE`。渲染/命中测试不受影响（截图/注入全兼容，已回归验证）。
    这是"嵌入到 UI 壳"的零侵入替代——SetParent 嵌入会破坏 wx 窗口树语义并违反
    hands-off 教条，**不要做**

## 关键设计事实（源码核对过，改动 app 时需复查）

| 事实 | 出处 | 对策 |
|---|---|---|
| `ORCA_GUI_TEST_MODE=1` **隐藏主窗口** | GUI_App.cpp:3046 跳过 `mainframe->Show(true)` | launcher 显式剥除该变量；隔离改用 `--datadir` |
| conf 是 **JSON + 尾行 MD5**（非 INI） | AppConfig.cpp `USE_JSON_CONFIG` | profile.py 按 nlohmann 格式写 + 复刻 MD5 行 |
| wizard 触发：无 conf / 仅默认打印机 / privacy 空 | GUI_App::config_wizard_startup | 种子 conf + 拷贝 system 预设 + privacy=true + firstguide.finish=true |
| 主窗口**无标题**（自绘 topbar） | MainFrame.cpp:237 | 按 PID+可见+尺寸最大枚举定位 |
| 位置参数自动加载 3mf | GUI_App::post_init → load_files | launcher 的 `model` 参数 |
| GL 画布 BitBlt 黑屏 | — | PrintWindow(PW_RENDERFULLCONTENT) |
| 启动版本检查可能弹更新窗 | check_new_version_sf（网络） | pipeline 预留"关意外弹窗"节点 |

## 环境危害矩阵（源自 wx_gui 调查，ADVERSARIAL_LOOP_JOURNAL.md）

| 环境 | 截图 | 消息注入(SendMessage) | OS级注入(SendInput) |
|---|---|---|---|
| 干净交互会话 | ✅ | ✅ | ✅ |
| GameViewer/ToDesk 等远控层运行中 | ✅ | ✅（LL hook 看不见 sent 消息） | ❌ 被吞（劫持已定案） |
| zh-CN 拼音 IME | ✅ | ✅（WM_CHAR 直携字面字符） | ⚠️ 需 US layout 绕过 |
| 非交互桌面（CreateDesktop） | — | — | ❌ wx 启动挂起，已放弃 |

结论：**消息注入 + PrintWindow 截图**是本机（远控层常驻）唯一全绿通道，
MaaFramework 控制器配置也按此选择。

## 沙盒种子数据源（2026-08-28 起）

seed 的一切都来自**仓库 `resources/`**（exe 旁 `resources/` 兜底），**不再拷贝用户
`%APPDATA%\Snapmaker_Orca`**——沙盒因此可复现、可交发（不泄漏用户状态）：

| datadir 项 | 来源 | 说明 |
|---|---|---|
| `system/` | `resources/profiles/{Snapmaker,BBL}` + vendor json | 打包安装形态（vendor/{machine,filament,process}），与 app 的 Orca Updater 安装结果一致；白名单 2 个 vendor（58 个全拷 = 80MB 太慢） |
| `printers/` | `resources/printers/` | BL-P001（Bambu Lab）等；缺失会触发 "staging validation failed (printers)" 且第三方项目预设丢失 |
| `Snapmaker_Orca.conf` | 手写最小模板 | 仅挡 wizard 所需键（privacy/firstguide）+ 沙盒确定性键（language/splash/page/backup）；无 recent/geometry/登录/设备标识 |

附带发现：**BBL（Bambu Lab）预设 app 会从 exe 旁 resources 直接加载**（seed 不拷也
可用，实测 lithophane 加载出 P1S 的床型/耗材/工艺）；但 BBL vendor 的 Prepare 面板
布局与 Snapmaker 不同（Printer 区非 390x26 combo），预设切换节点需按 vendor 适配。
沙盒卫生（待办 #4）随本改动大部分完成——seed 不再接触用户数据；剩余项：app 运行期
WCP 云端订阅回调（datadir/web 与 %LOCALAPPDATA% Sentry/WebView2 数据，见坑 #11）。

## DPI

驱动进程 per-monitor-v2 感知，坐标/像素均为物理像素。模板与 DPI 绑定：
换显示缩放需重新采集模板（env_check 会告警）。
