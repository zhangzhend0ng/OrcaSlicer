#ifndef slic3r_App_PlaterViewModel_hpp_
#define slic3r_App_PlaterViewModel_hpp_

#include "libslic3r/MVVP.hpp"
#include "slic3r/App/UndoRedoController.hpp"
#include "slic3r/App/ColorMixViewModel.hpp"

#include <string>
#include <vector>
#include <memory>

namespace Slic3r {

// Forward declarations
class Print;
class PresetBundle;
class ColorMixViewModel;

/// Information about a single object on the plate, for View consumption.
struct ObjectInfo {
    int         id{-1};
    std::string name;
    std::string filament;
    int         instanceCount{1};
    bool        printable{true};
    bool        isSelected{false};
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
    PlaterViewModel();

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

    // ?? Commands (initialized in constructor) ??
    MVVP::Command addModel{[]{}, []{return true;}};
    MVVP::Command removeSelected{[]{}, []{return true;}};
    MVVP::Command arrange{[]{}, []{return true;}};
    MVVP::Command slice{[]{}, []{return true;}};
    MVVP::Command cancelSlice{[]{}, []{return true;}};
    MVVP::Command undo{[]{}, []{return true;}};
    MVVP::Command redo{[]{}, []{return true;}};
    MVVP::Command duplicate{[]{}, []{return true;}};
    MVVP::Command exportGCode{[]{}, []{return true;}};
    MVVP::Command sendToPrinter{[]{}, []{return true;}};

    // ?? Child ViewModels ??
    std::unique_ptr<ColorMixViewModel> colorMixVM{std::make_unique<ColorMixViewModel>()};
    UndoRedoController                  undoStack_;

    // ?? Model injection (called by App on startup) ??
    void setModels(Print* print, PresetBundle* presets);

    // ?? Public interface for View callbacks ??
    void addModelFromPath(const std::string& path);
    void onSliceProgress(int percent, const std::string& stage);
    void onSliceComplete(bool success);
    void refreshObjects();

private:
    void addModelDialog();
    void removeSelectedObject();
    void impl_arrangeAll();
    void impl_startSlice();
    void impl_cancelSlice();
    void impl_duplicateSelected();
    void exportGCodeToFile();
    void sendToPrinterDevice();
    void updateUndoRedo();

    Print*         print_{nullptr};
    PresetBundle*  presets_{nullptr};
};

} // namespace Slic3r

#endif /* slic3r_App_PlaterViewModel_hpp_ */
