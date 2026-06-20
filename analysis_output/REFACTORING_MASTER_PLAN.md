# OrcaSlicer 重构总体规划 v3.0

> **Harness-First | 对抗打磨 | 面向GUI+业务 | 2026-06-20**

---

## 一、知识图谱合成：现有文档全景

### 1.1 已有分析成果总览

| 文档 | 类型 | 核心贡献 | 状态 |
|------|------|----------|------|
| `ARCHITECTURE_PLAN.md` (v2) | 架构方案 | 4层Clean Architecture + MVP, 6接口, 5阶段路线图 | ⚠️ 与MVVM方案冲突 |
| `ARCHITECTURE_REVIEW.md` | 多角度验证 | 5→4层, PrusaSlicer/Cura对比, Pipeline模式 | ✅ 验证充分 |
| `MVVM_GUI_DESIGN.md` | GUI方案 | Property\<T\>+Command, 逐面板拆解, 可测试性证明 | ⚠️ 命名争议 |
| `MVVM_IMPLEMENTATION.md` | 实现指南 | ~80行MVVM框架, PlaterViewModel示例, 迁移顺序 | ✅ 可落地 |
| `MVVM_EDGE_CASES.md` | 边界分析 | 拖拽/连续输入/撤销/嵌套VM/对话框 | ✅ 补全关键 |
| `DLL_ARCHITECTURE_ANALYSIS.md` | DLL方案 | 7Agent分析, 混合推荐, C ABI, 性能影响 | ✅ 分析全面 |
| `coupling_report.md` | 数据分析 | 32循环依赖, 20跨Core/GUI边界, god类排行 | ✅ 定量基线 |
| `class_hierarchy.json` | 数据资产 | 4,432类继承关系 | ✅ 可查询 |
| `module_deps.json` | 数据资产 | 31模块依赖矩阵 | ✅ 可查询 |
| `hot_files.json` | 数据资产 | Plater.cpp 21,747行等 | ✅ 可查询 |

### 1.2 核心矛盾识别

经过交叉审读，识别出以下文档间的**实质性冲突**：

| # | 矛盾 | 文档A | 文档B | 冲突性质 |
|---|------|-------|-------|----------|
| C1 | MVP vs MVVM | ARCHITECTURE_PLAN: "Why Not MVVM" | MVVM_GUI_DESIGN: "MVVM dismissal premature" | **命名争议**，非实质分歧 |
| C2 | 层数 | ARCHITECTURE_PLAN: 4层 | ARCHITECTURE_REVIEW: 5→4层（已收敛） | 已解决 |
| C3 | DLL vs 静态 | DLL_ANALYSIS: 混合推荐 | ARCHITECTURE_PLAN: 纯静态 | **优先级冲突**，DLL应后置 |
| C4 | Property\<T\> sub/unsub | MVVM_IMPLEMENTATION: 返回Subscription | MVVM_GUI_DESIGN: 返回int索引 | 实现细节 |

### 1.3 C1深度分析：MVP与MVVM的实质等价性

**MVP观点**（ARCHITECTURE_PLAN/REVIEW）：
- wxWidgets无数据绑定引擎 → MVVM不可行
- Presenter持有状态, View被动接收
- 已有proto-Presenter（Plater::priv）

**MVVM观点**（MVVM_GUI_DESIGN）：
- 绑定只是机制，不是模式定义
- Property\<T\> ~50行即可实现手动绑定
- ViewModel天然适合canvas（逻辑/渲染分离）

**裁决：MVP与MVVM在wxWidgets/C++下的实现是同构的。**

```
MVP:  Presenter → View::updateProgress(50)
MVVM: ViewModel.set(property) → View.bind(property, callback)

两者都要求：
1. 业务逻辑层不知道wxWidgets
2. View是wxPanel，只做布局+渲染
3. 中间层持有状态，协调Model和View
4. 手动通知/绑定（因为没有原生binding engine）
```

**统一命名：MVVP（Model-View-ViewModel/Presenter）。** 实际代码中，ViewModel/Presenter是同一种对象的不同称呼。采用MVVM命名以对齐业界主流，但实现上Property\<T\>订阅模式与MVP的push-update完全等价。

---

## 二、对抗打磨：多轮交叉审查

### 2.1 Round 1：方案完整性审查

**审查方A（Architecture Reviewer）：** 检视ARCHITECTURE_PLAN.md
- ✅ 4层划分合理，依赖方向正确
- ✅ 6接口定义准确捕获了跨层依赖
- ✅ Strangler Fig迁移模式是业界最佳实践
- ⚠️ **缺失：线程模型未形式化为架构边界**
- ⚠️ **缺失：ImGuiWrapper 650方法未被分解**
- ⚠️ **缺失：Config/Preset系统未规划重构**

**审查方B（GUI Reviewer）：** 检视MVVM_GUI_DESIGN.md
- ✅ Property\<T\>设计简洁，适合C++17
- ✅ 逐面板VM拆解粒度合理
- ✅ Command canExecute推导自Property状态——优雅
- ⚠️ **缺失：CanvasViewModel中Gizmo交互的复杂度被低估**
- ⚠️ **缺失：ImGui面板（非wxWidgets）的MVVM适配**
- ⚠️ **缺失：wxPropertyGrid的Config编辑如何MVVM化**

**审查方C（Build/CI Reviewer）：** 检视整体可行性
- ✅ compile_commands.json + ctags索引是坚实的工具基础
- ✅ golden file测试策略正确
- ⚠️ **缺失：增量编译速度收益未量化（最影响开发者体验）**
- ⚠️ **缺失：clang-tidy规则集未定义**
- ⚠️ **缺失：边界检查CI脚本未设计**

### 2.2 Round 2：风险交叉审查

**高风险发现：**

| ID | 风险 | 来源 | 严重度 | 缓解 |
|----|------|------|--------|------|
| R1 | GLCanvas3D拆解时OpenGL状态机被破坏 | 审查方A | 🔴 高 | 分阶段：先提取纯逻辑(CameraMath/SelectionLogic)，渲染管线保持原样 |
| R2 | Plater::priv 918方法中隐含的线程不安全状态传递 | 审查方B | 🔴 高 | 先加ThreadSanitizer，修复现有data race；ViewModel强制主线程dispatch |
| R3 | Config/Preset序列化格式变更导致用户数据丢失 | 审查方C | 🔴 高 | Config重构时严格保持序列化兼容；golden文件覆盖所有preset版本 |
| R4 | libslic3r去wxWidgets后编译失败（隐式include传递） | ARCHITECTURE_PLAN | 🟡 中 | 使用iwyu逐步清理；先建立include白名单 |
| R5 | 重构期间的回归无法快速定位 | 审查方C | 🟡 中 | 每次commit后跑golden GCode diff；CI门禁5分钟内反馈 |

### 2.3 Round 3：缺失关注点补全

以下话题在所有现有文档中均缺失或覆盖不足：

| # | 缺失话题 | 重要性 | 处置 |
|---|----------|--------|------|
| G1 | **ImGui面板重构**（650方法ImGuiWrapper） | 🔴 关键 | ImGui是immediate-mode，不适合Property\<T\>绑定；采用Command模式 + 帧级状态快照 |
| G2 | **Config/Preset系统重构**（912方法的PrintConfig） | 🔴 关键 | 这是整个slicer的"数据库"；采用Repository模式，先提取接口再拆分 |
| G3 | **Tab页签系统重构**（512方法Tab + 子类） | 🟡 重要 | 参考Plater的VM模式，每个Tab对应一个SettingsViewModel |
| G4 | **线程安全形式化** | 🟡 重要 | 定义ThreadContext枚举(Main/Worker/IO)，每个类标注所属context |
| G5 | **i18n/localization影响** | 🟡 中等 | 重构时保持_L()宏不变；ViewModel不含可翻译字符串 |
| G6 | **增量编译时间量化目标** | 🟡 中等 | 目标：修改单个.cpp编译时间从120s→15s |
| G7 | **插件沙箱安全性** | 🟢 低 | Phase 5才涉及，暂时记录 |
| G8 | **macOS/Linux构建兼容** | 🟢 低 | 重构逻辑不改平台适配层 |

---

## 三、最终架构决策

### 3.1 分层架构（4层，已收敛）

```
═══════════════════════════════════════════════════════════════
Layer 4: Presentation（prez/）
  wxWidgets panels（passive Views）
  ImGui panels（immediate-mode，帧状态快照）
  GLCanvas3D（仅OpenGL渲染，无业务逻辑）
  依赖方向：↓ Layer 3 接口
═══════════════════════════════════════════════════════════════
Layer 3: Application（app/）
  ViewModels/Presenters（持有状态，协调Model↔View）
  SliceOrchestrator, JobManager, PrintQueue
  IPlugin + IPluginHost
  ConfigRepository, PresetRepository
  依赖方向：↓ Layer 2 接口
═══════════════════════════════════════════════════════════════
Layer 2: Domain + Infrastructure（libslic3r/）
  核心：Print, PrintObject, Layer, GCode, Config, Preset
  几何：Point, Polygon, Voronoi, MedialAxis
  算法：Fill, Arachne, Support, SLA
  端口：IProgressReporter, IModelProvider, IGCodeConsumer
  I/O：3MF, STL, STEP, OBJ
  网络：MQTT client, device communication
  零依赖 wxWidgets（硬约束）
═══════════════════════════════════════════════════════════════
Layer 1: Foundation（vendored）
  Boost, Eigen, CGAL, TBB, Clipper, miniz, nlohmann, libigl
═══════════════════════════════════════════════════════════════
```

### 3.2 MVVP统一模式（每个GUI面板）

```
┌────────────────────────────────────────────┐
│  View（prez/PlaterPanel）                  │
│  - wxPanel 子类，仅布局+渲染               │
│  - 订阅 Property<T>，收到通知后 CallAfter  │
│  - 转发事件 → Command.execute()           │
│  - 零知识 of Print/PresetBundle/Model     │
├────────────────────────────────────────────┤
│  ViewModel（app/PlaterViewModel）          │
│  - 持有所有 Observable 状态               │
│  - 暴露 Command 给 View 调用              │
│  - 持有 Model 引用（Print*, PresetBundle*）│
│  - 零知识 of wxPanel/wxButton/OpenGL      │
│  - 纯 C++，可独立单元测试                 │
├────────────────────────────────────────────┤
│  Model（libslic3r/Print, PresetBundle, …） │
│  - 领域对象，不变                              │
└────────────────────────────────────────────┘
```

### 3.3 Property\<T\> + Command 框架（~80行，header-only）

在 `src/libslic3r/MVVP.hpp` 中提供：

```cpp
namespace Slic3r::MVVP {

template<typename T>
class Property {
public:
    using Subscriber = std::function<void(const T& newValue, const T& oldValue)>;
    const T& get() const;
    void set(T newValue);
    T& mutate();
    void notifyMutation();
    struct Subscription { ~Subscription(); };  // RAII unsubscribe
    Subscription subscribe(Subscriber s);
};

class Command {
public:
    using Action = std::function<void()>;
    using CanExecute = std::function<bool()>;
    Command(Action execute, CanExecute canExec);
    void execute() const;
    bool canExecute() const;
};

} // namespace Slic3r::MVVP
```

### 3.4 六大解耦接口（Phase 2 - 打破Core/GUI循环）

所有接口定义在 libslic3r（Layer 2），实现在 Application（Layer 3）：

| 接口 | 用途 | 替换的耦合 |
|------|------|-----------|
| `IProgressReporter` | 进度+取消回调 | `wxPostEvent` 从 Print 到 GUI |
| `IModelArranger` | Plate布局策略 | `Plater::arrange()` 从 `Print::apply()` 调用 |
| `IGCodeConsumer` | 接收生成GCode | GCode生成时直接操作 Plater |
| `IPlateDataProvider` | 查询plate几何信息 | `Plater::priv` 被 Print 访问 |
| `IConfigResolver` | 动态配置覆盖 | `GUI_App::get_config()` 依赖 |
| `INotificationSink` | 警告/错误/消息 | `show_error()` 从 core 到 GUI |

### 3.5 DLL策略：先解耦，后DLL

```
Phase 1-3: 先完成Layer划分 + 接口提取（纯静态）
Phase 4:   提取 orca-foundation（Geometry类型共享库）
Phase 5:   按需提取 format/network/fill DLLs
```

DLL不应是Phase 1目标。必须先打破32个循环依赖，libslic3r能独立编译后，DLL提取才有意义。

---

## 四、Harness-First 策略：安全网设计

### 4.1 Harness 金字塔

```
        ┌─────────┐
        │ CI 门禁  │  ← 每次PR: clang-tidy, 边界检查, 测试
       ┌┴─────────┴┐
       │ 回归测试  │  ← Golden GCode diff, preset迁移测试
      ┌┴───────────┴┐
      │ 单元测试     │  ← ViewModel测试(无GUI), 算法测试
     ┌┴─────────────┴┐
     │ 静态分析       │  ← 循环依赖检测, include白名单
    ┌┴───────────────┴┐
    │ Golden Files    │  ← 已知模型→期望GCode, 版本锁
   └─────────────────┘
```

### 4.2 具体Harness清单

| Harness | 创建时机 | 内容 | 验证方式 |
|---------|----------|------|----------|
| H1: Golden GCode | Week 1 | 10个标准模型×5种配置→基准GCode | `diff` 零差异 |
| H2: Include边界检查 | Week 2 | Python脚本：禁止libslic3r include slic3r/GUI | CI失败=阻断 |
| H3: 循环依赖检测 | Week 2 | graphviz分析→0循环目标 | CI报告趋势 |
| H4: God类审计 | Week 3 | ctags方法计数>200报警 | CI报告不阻断 |
| H5: 线程安全基线 | Week 4 | ThreadSanitizer通过（修复现有race） | CI阻断新增race |
| H6: ViewModel单元测试 | Week 6+ | 每提取一个VM→加测试 | CI必须通过 |
| H7: Preset迁移测试 | Week 8+ | 所有历史版本preset加载+保存往返 | CI必须通过 |

### 4.3 每次重构的验证循环

```
1. 创建新代码（旧代码不动）
2. 新代码通过单元测试
3. 新代码通过Golden GCode diff
4. 将一个调用者从旧路径切换到新路径
5. Golden GCode diff = 空
6. 循环4-5直到旧代码无调用者
7. 删除旧代码
8. Golden GCode diff = 空
```

---

## 五、分阶段实施路线图（30周）

### Phase 0: Harness搭建（Week 1-2）

| 任务 | 产出 | 验证 |
|------|------|------|
| ✅ compile_commands.json | 502条目 | 已有 |
| ✅ ctags符号索引 | 121K符号 | 已有 |
| 📋 Golden GCode基线 | 10模型×5配置=50个基准 | diff为空 |
| 📋 Include边界检查脚本 | `scripts/check_layer_violations.py` | CI集成 |
| 📋 循环依赖可视化 | `scripts/cycle_report.py` → SVG | 基线32个 |
| 📋 clang-tidy CI门禁 | `.clang-tidy` + CI yaml | 现有代码通过 |
| 📋 God类审计日报 | `scripts/god_class_audit.py` | 每日趋势 |

### Phase 1: libslic3r内部整理（Week 3-5）

| 任务 | 涉及文件 | 预期减少 |
|------|---------|----------|
| Geometry命名空间整理 | `libslic3r/Geometry/*` → 专用子目录 | fan-out 3→2 |
| 删除死代码 | 全仓库 `#if 0` 块、未使用类 | ~5K行 |
| 合并工具函数 | 80+个散落utils文件 → `libslic3r/Utils/` | 减少散落 |
| Clipper封装统一 | 所有直接调用clipper处 → `ClipperUtils` | 统一入口 |
| **门禁** | Golden GCode diff = 空 | |

### Phase 2: 打破Core-GUI循环（Week 6-12）⭐ 最关键

| 周 | 任务 |
|----|------|
| 6-7 | 定义+实现6个接口（IProgressReporter等） |
| 8 | 实现 `FileProgressReporter`（Layer 3实现，替代wxPostEvent） |
| 8 | 实现 `FileModelArranger`（Layer 3实现，替代Plater::arrange调用） |
| 9-10 | 逐步替换libslic3r中的所有 `#include "slic3r/GUI/..."` |
| 11 | 构建验证：`libslic3r` 在 `SLIC3R_GUI=OFF` 下编译通过 |
| 12 | Golden GCode回归 + 循环依赖复查 |

**Phase 2完成标志：**
- libslic3r 零依赖 wxWidgets
- 循环依赖从32个降至**0个跨Core/GUI边界**
- Golden GCode diff = 空

### Phase 3: God类拆分 + MVVP（Week 13-22）

#### 3A：MVVP框架 + CanvasViewModel（Week 13-15）

```
GLCanvas3D（1,210方法）→
├── CameraController     (~80方法)  ← 提取优先：纯数学，最易测试
├── SelectionController  (~100方法) ← 选择逻辑，纯C++
├── CanvasViewModel      (~150方法) ← 状态聚合，驱动渲染
├── SceneGraph           (~120方法) ← 场景对象管理
├── GizmoHost            (~80方法)  ← Gizmo注册/激活
├── CanvasOverlay        (~50方法)  ← 床网格/轴/HUD
├── ToolManager           (~60方法) ← 工具切换/快捷键
├── CanvasRenderer       (~150方法) ← OpenGL管线（保留在View）
└── GLCanvas3D (facade)  (~200方法) ← wxGLCanvas集成
```

**提取顺序**（由易到难，每个完成即测试）：
1. CameraController — 纯数学，零依赖
2. SelectionController — 纯逻辑
3. CanvasViewModel — 聚合前两者
4. SceneGraph — 场景对象
5. GizmoHost — 依赖SceneGraph
6. ToolManager — 依赖GizmoHost
7. CanvasOverlay — 渲染细节
8. CanvasRenderer — 最后动（OpenGL最脆弱）

#### 3B：PlaterViewModel（Week 16-18）

```
Plater::priv（918方法）→
├── PlaterViewModel      (~250方法)
│   ├── Property<SliceState>        sliceState
│   ├── Property<double>            sliceProgress
│   ├── Property<vector<ObjectInfo>> objects
│   ├── Property<PlateLayout>       layout
│   ├── Command addModel, removeSelected, arrange, slice, cancelSlice
│   ├── Command undo, redo, duplicate, sendToPrinter, exportGCode
│   │
│   ├── ObjectViewModel[]           ← 嵌套VM，按object创建
│   │   ├── Property<Vec3d> position, rotation
│   │   ├── Property<double> scale
│   │   ├── Property<bool> isSelected, isVisible
│   │   └── Command delete, clone, moveToPlate
│   │
│   └── ColorMixViewModel           ← 混色面板VM
│       ├── Property<vector<ColorMixEntry>> entries
│       └── Command addMix, editMix, deleteMix
│
├── PlaterPanel (View)  (~150方法) ← 仅wxWidgets布局
└── Plater (facade)     (~100方法) ← wxPanel外壳
```

#### 3C：AppViewModel + GUI_App拆分（Week 19-20）

```
GUI_App（1,200方法）→
├── AppViewModel         (~100方法) ← 生命周期+顶层导航
├── PresetViewModel      (~150方法) ← Preset CRUD + 迁移
├── DeviceViewModel      (~80方法)  ← MQTT + 设备列表
├── SettingsViewModel    (~80方法)  ← 语言+主题+单位
├── AccountViewModel     (~60方法)  ← 登录状态
├── PluginViewModel      (~60方法)  ← 插件管理
├── WindowManager         (~50方法) ← 窗口创建/布局
├── ConfigRepository     (~100方法) ← 配置持久化（Layer 3）
└── GUI_App (facade)      (~50方法) ← wxApp样板
```

#### 3D：Tab页签 MVVP化（Week 21-22）

```
Tab（512方法 + PrintTab/FilamentTab/PrinterTab子类）→
├── TabViewModel 基类    ← Property<ConfigSnapshot> + Dirty跟踪
├── PrintTabViewModel    ← 打印设置
├── FilamentTabViewModel ← 耗材设置
├── PrinterTabViewModel  ← 打印机设置
└── 对应TabPanel (View)  ← wxPropertyGrid绑定
```

### Phase 4: Application层提取 + 插件框架（Week 23-26）

- SliceOrchestrator：从分散的slice启动代码中提取
- JobManager：统一后台任务调度
- IPlugin框架：接口定义 + 加载器 + 沙箱
- 所有GUI面板通过Layer 3接口访问领域层

### Phase 5: 硬化 + DLL按需提取（Week 27-30）

- 边界CI检查：禁止反向依赖
- ThreadSanitizer + AddressSanitizer CI
- God类审计：无人超200方法
- 提取 orca-foundation（Geometry共享库）
- 按需提取 format/network DLLs

---

## 六、关键模块详细拆解

### 6.1 Config/Preset 系统重构（G2补全）

这是整个slicer的"数据库"层，当前问题：

- `PrintConfig.cpp` 8,902行，2个类
- `Slic3r::final` 912方法
- 配置层级：PrintConfig → PrintObjectConfig → PrintRegionConfig
- 与GUI的wxPropertyGrid深度绑定
- Preset序列化/迁移逻辑散落各处

**目标架构（Repository模式）：**

```
libslic3r/Config/
├── ConfigDef.hpp         ← 配置项定义（key, type, default, range, label）
├── ConfigSnapshot.hpp    ← 运行时配置快照（immutable after build）
├── ConfigHierarchy.hpp   ← Print/PrintObject/PrintRegion 覆盖链
├── IConfigRepository.hpp ← 存储接口（Layer 2端口）
│
app/Config/
├── ConfigRepository.cpp  ← JSON文件存储实现（Layer 3）
├── PresetRepository.cpp  ← Preset管理+迁移（Layer 3）
├── ConfigViewModel.hpp   ← 单个配置项编辑VM
└── PresetViewModel.hpp   ← Preset列表+CRUD VM
```

### 6.2 ImGui 面板重构（G1补全）

ImGui是 immediate-mode GUI，不适合 Property\<T\> 订阅模式。

**采用 Command + 帧快照 模式：**

```cpp
class ImGuiPanelViewModel {
public:
    // 每帧开始时，View调用snapshot()获取当前状态
    PanelState snapshot() const;
    
    // View调用action()响应ImGui交互
    void action(const PanelAction& act);
    
    // View完成一帧后，调用commit()提交变更
    void commit();
};
```

ImGuiWrapper 650方法 → 拆分为：
- `ImGuiRenderer` — 渲染后端（View）
- `ImGuiPanelViewModel` 子类 — 每个ImGui面板一个VM

### 6.3 线程安全形式化（G4补全）

```cpp
// 每个类标注线程归属
enum class ThreadContext {
    MainOnly,       // 只能在主线程访问（所有View, ViewModel属性读）
    WorkerOnly,     // 只能在worker线程访问
    ThreadSafe,     // 内部有mutex保护
    Immutable,      // 创建后不可变，任意线程安全
};

// 示例标注
class PlaterViewModel {
    // ThreadContext: MainOnly（大部分方法）
    // ThreadContext: ThreadSafe（onSliceProgress回调 → 内部CallAfter）
};
```

### 6.4 增量编译时间量化目标（G6补全）

| 场景 | 现在 | Phase 3后 | Phase 5后 |
|------|------|-----------|-----------|
| 修改 Plater.cpp (21,747行) | ~180s | ~15s (ViewModel改cpp, View改cpp分开) | ~8s |
| 修改 GLCanvas3D.cpp (10,237行) | ~120s | ~12s | ~5s |
| 修改 PrintConfig.cpp | ~60s | ~10s | ~5s |
| 修改 libslic3r 头文件 | ~200s+ | ~30s | ~15s |

**实现手段：**
1. 大文件拆小（Plater.cpp → PlaterPanel.cpp + PlaterViewModel.cpp + ...）
2. 接口隔离（依赖接口而非具体类，减少头文件重编译）
3. Pimpl idiom（wxWidgets类用pimpl隐藏实现）
4. 前向声明（减少include传递）

---

## 七、成功准则（可量化）

| 准则 | Phase 0基线 | Phase 2目标 | Phase 3目标 | Phase 5目标 |
|------|-----------|------------|------------|------------|
| libslic3r独立编译 | ❌ 依赖wx | ✅ SLIC3R_GUI=OFF | ✅ | ✅ |
| 跨Core/GUI循环依赖 | 20个 | **0个** | 0 | 0 |
| 总循环依赖 | 32个 | <15个 | <5个 | **0个** |
| God类(>200方法) | 8个 | 8个 | 3个 | **0个** |
| Golden GCode回归 | 基线 | 零差异 | 零差异 | 零差异 |
| ViewModel单元测试 | 0个 | 0个 | 15+ | 25+ |
| 模块可独立测试 | 0个 | 3个 | 10个 | **20+** |
| 增量编译(改单个.cpp) | 60-180s | 60-180s | <30s | <15s |
| 最大文件行数 | 21,747 | 21,747 | <5,000 | <3,000 |

---

## 八、风险矩阵

| ID | 风险 | 概率 | 影响 | 缓解措施 | 触发条件 |
|----|------|------|------|----------|----------|
| R1 | 重构引入slicing回归 | 中 | 🔴 严重 | Golden GCode全量diff每commit | diff非空→阻断 |
| R2 | GLCanvas3D拆解破坏渲染 | 高 | 🔴 严重 | 可视化diff（截图对比） | 截图差异→阻断 |
| R3 | 人员不足/时间不够 | 中 | 🟡 中等 | 按Phase独立交付，每Phase可暂停 | 进度落后→缩减后续Phase |
| R4 | Config迁移导致用户数据丢失 | 低 | 🔴 严重 | 序列化兼容测试全覆盖 | 测试失败→阻断 |
| R5 | 团队对MVVP模式不熟悉 | 中 | 🟡 中等 | Phase 3A先做CanvasViewModel demo | demo不被接受→调整方案 |
| R6 | 线程重构引入死锁/竞态 | 低 | 🟡 中等 | TSAN CI门禁 | 新race→阻断 |
| R7 | DLL提取后ABI断裂 | 低 | 🟡 中等 | C ABI边界 + 版本检查 | 版本不匹配→友好报错 |

---

## 九、工具链清单

| 工具 | 用途 | 路径/安装 | 状态 |
|------|------|----------|------|
| ctags (Universal Ctags) | 符号索引，类层次分析 | 系统PATH | ✅ 就绪 |
| clang-tidy 19.1.5 | 静态分析，代码规范 | VS2022内置 | ✅ 就绪 |
| compile_commands.json | IDE支持，分析工具 | 项目根目录 | ✅ 就绪 |
| kg_core.py | 知识图谱核心 | `scripts/kg_core.py` | ✅ 就绪 |
| analyze_deps.py | 依赖分析 | `scripts/analyze_deps.py` | ✅ 就绪 |
| check_layer_violations.py | 分层边界检查 | **待创建** | 📋 Phase 0 |
| cycle_report.py | 循环依赖可视化 | **待创建** | 📋 Phase 0 |
| god_class_audit.py | God类审计 | **待创建** | 📋 Phase 0 |
| golden_gcode_test.py | Golden GCode回归 | **待创建** | 📋 Phase 0 |
| iwyu (include-what-you-use) | 多余include清理 | **需安装** | 📋 Phase 1 |

---

## 十、下一步行动（最优先）

按优先级排列的前10项可执行行动：

| # | 行动 | 负责 | 预计工时 | 产出 |
|---|------|------|----------|------|
| 1 | 建立Golden GCode基线 | Phase 0 | 3d | 50个.gcode基准文件 |
| 2 | 编写include边界检查脚本 | Phase 0 | 2d | CI集成 |
| 3 | 创建MVVP.hpp框架文件 | Phase 3 | 1d | `src/libslic3r/MVVP.hpp` |
| 4 | 提取CameraController（demo） | Phase 3A | 3d | 证明MVVP模式可行 |
| 5 | 编写CanvasViewModel单元测试demo | Phase 3A | 2d | 证明可测试性 |
| 6 | 定义6个解耦接口（IProgressReporter等） | Phase 2 | 2d | `src/libslic3r/Ports/` |
| 7 | 实现IProgressReporter的FileReporter | Phase 2 | 2d | 第一个解耦实现 |
| 8 | 修复TSAN发现的现有data race | Phase 0 | 3d | 线程安全基线 |
| 9 | 删除ifdef-out死代码 | Phase 1 | 2d | ~5K行减少 |
| 10 | 创建Plater拆分的详细设计文档 | Phase 3B | 2d | PlaterViewModel接口定义 |

