# 5d 已完结（插件侧范围）——2026-10-22

## 最终状态

- `944309269a` absorb(batch-5d): ResourceTexture plugin capability, plugin-side scope（24 文件，+4499/-5）
- 门禁：`ctest -R "[Pp]lugin|[Tt]exture|pack"` **69/69**（2 Skipped：symlink 无文件系统支持；3mf 往返测试因 fork 既有 bug SKIP，见下）
- 插件生态吸收序列（批次 0→5d）全部完成：0740e665e2 → 7e3b1989d3 → f6b4a92a31 → 63b6fcf64d → 187eed00b5 → 5899177f18 → d8b34e449e(5b amend) → fcf96e28c8(5c) → 944309269a(5d 插件侧)

## 范围决策记录

用户明确"只要插件系统"后，5d 从"全纹理特性族吸收"改为**插件侧最小吸收**：能力类型 + 注册表 + 安全校验 + 绑定 + TextureLibrary 目录（能力的消费面）+ TextureDisplacement 类型与 JSON 项目持久化 + bbs_3mf 纹理层持久化 + 全套测试。gizmo/Jobs/UV/StepMesh/TextureBake/OBJ 导入/glb/mixed-filament 全部不取。

## 两个重要发现

1. **fork store_bbs_3mf 在 headless 测试环境崩溃（既有 bug，与吸收无关）**：gdb 栈为 cereal `StaticObject<PolymorphicVirtualCaster<ConfigOptionVectorBase, ConfigOptionVector<string>>>::getInstance`。对照实验：stash 全部 5d 改动后（纯 fcf96e28c8 代码）最小 store/load 往返同样 SIGSEGV。测试中以 SKIP 记录（test_plugin_resource_texture.cpp 往返 case），待单独修复后去掉 SKIP 即可恢复该用例。嫌疑方向：cereal 注册 TU 在 slic3rutils_tests 链接集里的静态初始化序（upstream 的测试二进制组合可能不同）。
2. MSBuild 增量构建多次静默跳过新 TU/未重链（假绿第二来源）：改 CMakeLists 或加新文件后必须 `cmake .` 显式重配置并核对 obj/exe 时间戳。

## 纹理特性族底座（park 分支）

`park/texture-family-full` = `185bbad9df`：71 个家族文件 + Model/OBJ/objparser/bbs_3mf/GLGizmosManager/shader/CMake 全量集成（含本文件旧版详细 hunk 图谱）。将来若要完整纹理位移特性，从该分支 cherry-pick 到 944309269a 之上，解决点见 park 版续接文件（mixed-filament API 缺口是关键前置决策）。

## 遗留（全部已注明、不阻塞）

- 5b 中间提交（d8b34e449e）单独不可编译（ActionRegistry 终态依赖 5c 的 select_page/translate_category），序列 squash 合并时消除
- LazyPage 终态升级、max-visible-pages 特性：可选后续
- audit socket 2 例 SKIP（deps CPython 双触发）、全量 ctest 2 例 "Objects could not fit on the bed"（批次0 前遗留）：已知非回归
