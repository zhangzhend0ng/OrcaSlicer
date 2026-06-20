# OrcaSlicer GUI-Business Separation Migration Guide

## Core Pattern (already built)

```
???????????????????????????????????????????????????????????????
?  View (wxPanel)              ?Property??     ViewModel     ?
?  - ?? Property<T> ??     (CallAfter)     - ?????? ?
?  - ?? Command.execute()   ??Command???     - ?C++??   ?
?  - ??? of Model                           - ??? of wx ?
???????????????????????????????????????????????????????????????
```

## What We Built (12 commits, ~4000 lines)

### Layer 2 (libslic3r) - Domain Interfaces
- `MVVP.hpp` ? Property<T> + Command framework
- `Ports/IProgressReporter.hpp` ? progress/cancellation
- `Ports/IModelArranger.hpp` ? plate layout
- `Ports/IGCodeConsumer.hpp` ? GCode output
- `Ports/IPlateDataProvider.hpp` ? bed geometry
- `Ports/IConfigResolver.hpp` ? dynamic config
- `Ports/INotificationSink.hpp` ? warnings/errors
- `ColorSpaceConvert.{hpp,cpp}` ? pure color math

### Layer 3 (slic3r/App) - Business Logic
- `CameraController.{hpp,cpp}` ? camera math (orbit/pan/zoom)
- `SelectionController.{hpp,cpp}` ? pick/hover/selection state
- `PlaterViewModel.{hpp,cpp}` ? slice orchestration
- `CanvasViewModel.hpp` ? 3D canvas state aggregation
- `MixedFilamentViewModel.{hpp,cpp}` ? **first real extraction from Plater.cpp**
- `AppViewModel.{hpp,cpp}` ? top-level app state
- `PresetViewModel.hpp` ? preset CRUD
- `DeviceViewModel.hpp` ? MQTT/device state
- `SettingsViewModel.hpp` ? app settings
- `AccountViewModel.hpp` ? login state
- `PluginViewModel.hpp` ? plugin management
- `TabViewModel.hpp` ? config editing base
- `PrintTabViewModel.hpp` ? print settings
- `FilamentTabViewModel.hpp` ? filament settings
- `PrinterTabViewModel.hpp` ? printer settings
- `SliceOrchestrator.hpp` ? centralized slicing
- `JobManager.{hpp,cpp}` ? background job scheduling
- `IPlugin.hpp` ? plugin interface
- `PluginLoader.hpp` ? plugin discovery
- `UndoRedoController.hpp` ? undo/redo stack
- `NullProgressReporter.hpp` ? headless progress
- `ViewBindingGuide.hpp` ? **5 documented binding patterns**

### Tests (40+ unit tests, zero wxWidgets needed)
- TestMVVP.cpp (10), TestCameraController.cpp (7)
- TestPlaterViewModel.cpp (8), TestAppViewModels.cpp (8)
- TestTabViewModels.cpp (7), TestAppLayer.cpp (8)
- TestMixedFilamentViewModel.cpp (7)

## Migration Priority (by impact & safety)

### Tier 1: Already extractable (pure functions in GUI files)
- [x] MixedFilamentViewModel ? Plater.cpp static functions
- [ ] ConfigValidationModel ? Tab.cpp bed_type/nozzle rules
- [ ] SearchFilterModel ? get_search_inputs() in Plater.cpp
- [ ] ReloadableVolumesModel ? reloadable_volumes() in Plater.cpp

### Tier 2: Extractable with moderate effort
- [ ] CameraController wiring ? GLCanvas3D mouse handlers
- [ ] SelectionController wiring ? GLCanvas3D picking
- [ ] GCodePreviewModel ? GCodeViewer state

### Tier 3: Requires deep refactoring
- [ ] PlaterViewModel wiring ? Plater::priv
- [ ] TabViewModel wiring ? Tab/wxPropertyGrid
- [ ] AppViewModel wiring ? GUI_App

## How to Apply the Pattern (for each module)

### Step 1: Identify pure logic
Scan the GUI .cpp file for static functions that take no wx types.
```bash
rg -n "^static (bool|int|double|std::|Vec3|Point)" src/slic3r/GUI/TargetFile.cpp
```

### Step 2: Create ViewModel
```cpp
// slic3r/App/TargetViewModel.hpp
class TargetViewModel {
public:
    // Input (called from old GUI code)
    void setInput(const InputType& data);

    // Output (GUI subscribes to these)
    MVVP::Property<OutputType> result;

private:
    void recalculate(); // the pure logic, extracted here
};
```

### Step 3: Write unit tests
```cpp
TEST_CASE("TargetVM computes correctly", "[TargetVM]") {
    TargetViewModel vm;
    vm.setInput(testData);
    REQUIRE(vm.result.get() == expectedOutput);
}
```

### Step 4: Wire from old GUI (strangler fig)
```cpp
// In old wxPanel constructor or init:
m_viewModel = std::make_unique<TargetViewModel>();

// Replace inline computation:
//   OLD: auto result = computeSomething(data);
//   NEW: m_viewModel->setInput(data);

// Subscribe to output:
m_viewModel->result.subscribe([this](const OutputType& r, const auto&) {
    CallAfter([this, r] { updateWidgets(r); });
});
```

### Step 5: Delete old code
Once all callers use the ViewModel, remove the old static function.

## Thread Safety Rule
```
EVERY Property subscriber MUST CallAfter() to main thread.
This is the ONLY place thread safety matters.
```
