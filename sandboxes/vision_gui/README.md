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
  profile.py        沙盒 datadir 种子（JSON conf + MD5 行 + 系统预设拷贝）
  launcher.py       黑盒启动（显式剥除 ORCA_GUI_TEST_MODE！）
m0_boot_check.py    里程碑0：启动→定位→截图→关闭 冒烟
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
| M2 切片链 | 见下 | 模型自动加载 ✅（需 fresh datadir）、切片真实启动（进度条） |

### 引擎选型结论（M1b 决定性实验）

**MaaFramework 可用但注入层必须走 Python 自定义 action**：
- 可复用：pipeline 编排、模板识别循环、重试/超时、截图（`set_screenshot_use_raw_size(True)` 关闭默认 720p 降采样）
- 不可用：Win32 内置 Click——设计目标是游戏"单一大窗口"，对 wx 复合子窗口 UI 无效
- `harness/winutil.py` 的 `msg_click_screen`（WindowFromPoint+SendMessageTimeout）即是补洞层，纯自研路线也直接复用它

### 已知坑（踩过并已规避）

1. **复用 datadir 后 CLI 位置参数不再自动加载模型** —— 首次运行后 app 写回的状态会阻断
   input_files 自动加载；M2 默认每次 fresh profile
2. **启动 tab 选择有竞态**：最终 select_tab 在 GL init 后的 CallAfter 里，且页面切换可能被
   `EVT_GLVIEWTOOLBAR_3D` 弹回 Prepare → 驱动必须 wait_for + 稳定性确认 + 重试，禁止定时假设
3. **模板必须从"稳态"截图切**：启动 ~3s 内是主题应用前的瞬态（白底），稳态是深色主题
4. **MaaFw 默认把截图降采样到 720p**：模板是原生分辨率切的，必须开 raw size
5. **切片在本机很慢**（GameViewer 虚拟显示 + 首启预设索引）：Prusa.stl 可达数分钟，
   完成检测超时给足 600s
6. **模板状态区分用颜色不用模板分**：tab 选中=teal(0,150,136)/未选=(59,68,70)（源自
   Notebook.cpp ButtonsListCtrl），TM_CCOEFF_NORMED 对纯背景变化不敏感（0.926 仍误判）
7. **沙盒卫生待办**：种子的用户 conf 无明显 token，但 app 启动后有云端订阅回调（WCP 日志）；
   对外交发沙盒 profile 前需核实数据面

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

## DPI

驱动进程 per-monitor-v2 感知，坐标/像素均为物理像素。模板与 DPI 绑定：
换显示缩放需重新采集模板（env_check 会告警）。
