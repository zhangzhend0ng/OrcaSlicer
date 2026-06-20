#ifndef slic3r_App_PlaterViewModel_hpp_
#define slic3r_App_PlaterViewModel_hpp_

#include "libslic3r/MVVP.hpp"

#include <string>
#include <vector>
#include <memory>

namespace Slic3r {

// Forward declarations
class Print;
class PresetBundle;
struct Vec3d;

/// Information about a single object on the plate, for View consumption.
struct ObjectInfo {
    int         id{-1};
    std::string name;
    std::string filament;
    int         instanceCount{1};
    bool        printable{true};
    bool        isSelected{false};
    bool        isVisible{true};
};

/// Layout state of the build plate.
struct PlateLayout {
    int    currentPlateIndex{0};
    int    totalPlates{1};
    double usedFilament_mm{0.0};
    int    estimatedTime_s{0};
};

/// Global slice orchestration state.
enum class SliceState {
    Idle,
    Running,
    Cancelling,
    Done,
    Failed,
};

/// MVVP ViewModel for the Plater (main workspace).
/// Extracted from Plater::priv (918 methods).
/// Pure C++, independently testable, zero wxWidgets dependency.
class PlaterViewModel {
public:
    using mv = MVVP;

    // ?? Observable State ??
    MVVP::Property<SliceState>              sliceState{SliceState::Idle};
    MVVP::Property<double>                  sliceProgress{0.0};
    MVVP::Property<std::string>             sliceStage{""};
    MVVP::Property<std::vector<ObjectInfo>> objects{{}};
    MVVP::Property<int>                     selectedIndex{-1};
    MVVP::Property<PlateLayout>             layout{PlateLayout{}};
    MVVP::Property<bool>                    canUndo{false};
    MVVP::Property<bool>                    canRedo{false};
    MVVP::Property<bool>                    isSlicing{false};
    MVVP::Property<bool>                    isModified{false};

    // ?? Commands ??
    MVVP::Command addModel{
        [this] { /* loadModelDialog */ },
        [this] { return sliceState.get() == SliceState::Idle; }
    };
    MVVP::Command removeSelected{
        [this] { /* removeSelectedObject */ },
        [this] { return selectedIndex.get() >= 0 && sliceState.get() == SliceState::Idle; }
    };
    MVVP::Command arrange{
        [this] { /* arrangeAll */ },
        [this] { return sliceState.get() == SliceState::Idle && !objects.get().empty(); }
    };
    MVVP::Command slice{
        [this] { /* startSlice */ },
        [this] { return sliceState.get() == SliceState::Idle && !objects.get().empty(); }
    };
    MVVP::Command cancelSlice{
        [this] { /* cancelSlice */ },
        [this] { return sliceState.get() == SliceState::Running; }
    };
    MVVP::Command undo{
        [this] { /* undo */ },
        [this] { return canUndo.get(); }
    };
    MVVP::Command redo{
        [this] { /* redo */ },
        [this] { return canRedo.get(); }
    };
    MVVP::Command duplicate{
        [this] { /* duplicate */ },
        [this] { return selectedIndex.get() >= 0; }
    };
    MVVP::Command exportGCode{
        [this] { /* exportGCode */ },
        [this] { return sliceState.get() == SliceState::Done; }
    };
    MVVP::Command sendToPrinter{
        [this] { /* sendToPrinter */ },
        [this] { return sliceState.get() == SliceState::Done; }
    };

    // ?? Model injection (called by App on startup) ??
    void setModels(Print* print, PresetBundle* presets);

private:
    Print*         print_{nullptr};
    PresetBundle*  presets_{nullptr};
};

} // namespace Slic3r

#endif /* slic3r_App_PlaterViewModel_hpp_ */
