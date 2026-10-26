# 装载挂起与等待域契约（LOAD_HANG_RECOVERY）

来源：women 分支 docs/plugins/LOAD_HANG_RECOVERY.md（0aa325e101）裁剪移植。原文主体为其本机 macOS 一次装载卡死事故的完整取证（ON39 修复 + 本机证据链 + 出包记录），此处不携带；保留并改写为**本树可执行的契约**，对应考卷 `tests/plugin_core/runtime_wait.cpp` / `unload_overlap.cpp` / `observer_queue.cpp`（吸收批新入，语义映射到本树 PluginManager 的键基 API）。

## 事故类（背景，一句话版）

插件装载的完成回调经 wx 队列派发时，若等待方在持有事件队列锁的路径上同步等待 worker、而 worker 又要投递事件，会形成主线程↔worker 互等。women 的修复把等待改为专用条件变量（本树 `PluginManager::wait_for_plugin_load` 的 `m_load_cv` 同构），等待方绝不泵 wx 事件、绝不重入事件循环。

## 契约（每条都有考卷断言）

- **等待在条件变量上，不在调用者事件循环上**：`load_plugin` 火后即返，`wait_for_plugin_load(key, timeout, error)` 阻塞在 CV；等待期间不泵任何 wx 队列。runtime_wait（no-app/console 双模式）。
- **worker 槽位先于返回释放**：装载失败/成功/重装，`wait_for_plugin_load` 返回时 `is_plugin_load_in_progress(key)` 必为 false，错误串与 `get_plugin_load_error` 一致。runtime_wait。
- **观察者派发规则**：完成回调在无应用（`wxTheApp == nullptr`）时 worker 内联执行；有真实 wxAppConsole 时经 CallAfter 排队、只在主线程泵队列时执行。runtime_wait / observer_queue。
- **shutdown 作废未派发观察者**：排队中的完成回调在 shutdown 后不得再执行（防解释器终结后重建资源/触达新运行时）。observer_queue 终段。
- **卸载交叠**：旧代 Python `on_unload` 挂起期间，同键重装不得进入；完成后新代配置必须胜出（旧代 save 不得覆盖）。unload_overlap（overlap/bulk_overlap）。
- **关机排水**：shutdown 不得在旧 Python teardown 仍在跑时返回；调用方持 GIL 时同样要排干。unload_overlap（shutdown/bulk_shutdown/shutdown_gil）。
- **卸载期包变更拒绝**：teardown 进行中的包拒绝 install 替换与 delete。unload_overlap（replacement/delete）。

## 本树与 women 的语义差异（吸收时裁定，详见台账）

- women 的 LocalPluginRuntime 为单槽装载器，观察者内嵌套 load 会被拒；本树为按键多槽，嵌套 load 合法（考卷断言其能正常完成）。
- women 在装载完成时同步提交 sidecar；本树 sidecar 写入本身走排队观察者（GUI 线程落盘），耐久性由跨重启验收覆盖（tests/e2e lifecycle）。
