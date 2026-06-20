#include "slic3r/App/PlaterViewModel.hpp"
#include "slic3r/App/ObjectViewModel.hpp"
#include "slic3r/App/ColorMixViewModel.hpp"
#include "slic3r/App/UndoRedoController.hpp"

namespace Slic3r {

PlaterViewModel::PlaterViewModel()
{
    // Reconstruct Commands with proper lambdas capturing 'this'
    // (The header initializes them with no-op defaults; we replace here.)

    slice = MVVP::Command(
        [this] { impl_startSlice(); },
        [this] { return sliceState.get() == SliceState::Idle && !objects.get().empty(); }
    );
    cancelSlice = MVVP::Command(
        [this] { impl_cancelSlice(); },
        [this] { return sliceState.get() == SliceState::Running; }
    );
    addModel = MVVP::Command(
        [this] { addModelDialog(); },
        [this] { return sliceState.get() == SliceState::Idle; }
    );
    removeSelected = MVVP::Command(
        [this] { removeSelectedObject(); },
        [this] { return selectedIndex.get() >= 0 && sliceState.get() == SliceState::Idle; }
    );
    arrange = MVVP::Command(
        [this] { impl_arrangeAll(); },
        [this] { return sliceState.get() == SliceState::Idle && !objects.get().empty(); }
    );
    undo = MVVP::Command(
        [this] { undoStack_.undo(); updateUndoRedo(); },
        [this] { return canUndo.get(); }
    );
    redo = MVVP::Command(
        [this] { undoStack_.redo(); updateUndoRedo(); },
        [this] { return canRedo.get(); }
    );
    duplicate = MVVP::Command(
        [this] { impl_duplicateSelected(); },
        [this] { return selectedIndex.get() >= 0; }
    );
    exportGCode = MVVP::Command(
        [this] { exportGCodeToFile(); },
        [this] { return sliceState.get() == SliceState::Done; }
    );
    sendToPrinter = MVVP::Command(
        [this] { sendToPrinterDevice(); },
        [this] { return sliceState.get() == SliceState::Done; }
    );
}

void PlaterViewModel::setModels(Print* print, PresetBundle* presets)
{
    print_    = print;
    presets_  = presets;
    refreshObjects();
}

void PlaterViewModel::refreshObjects()
{
    // Stub: actual implementation queries print_->model()
    objects.set({});
}

void PlaterViewModel::addModelDialog()
{
    // View handles file dialog, then calls addModelFromPath()
}

void PlaterViewModel::addModelFromPath(const std::string& /*path*/)
{
    isModified.set(true);
    refreshObjects();
}

void PlaterViewModel::removeSelectedObject()
{
    int idx = selectedIndex.get();
    auto objs = objects.get();
    if (idx < 0 || idx >= static_cast<int>(objs.size())) return;

    objs.erase(objs.begin() + idx);
    objects.set(objs);
    updateUndoRedo();
    isModified.set(true);

    if (selectedIndex.get() >= static_cast<int>(objs.size()))
        selectedIndex.set(static_cast<int>(objs.size()) - 1);
}

void PlaterViewModel::impl_arrangeAll()
{
    sliceState.set(SliceState::Running);
    // TODO: call ModelArrange::arrange() via print_
    sliceState.set(SliceState::Idle);
    refreshObjects();
}

void PlaterViewModel::impl_startSlice()
{
    if (sliceState.get() != SliceState::Idle) return;
    sliceState.set(SliceState::Running);
    sliceProgress.set(0.0);
    sliceStage.set("Preparing...");
    isSlicing.set(true);
}

void PlaterViewModel::impl_cancelSlice()
{
    if (sliceState.get() != SliceState::Running) return;
    sliceState.set(SliceState::Cancelling);
}

void PlaterViewModel::onSliceProgress(int percent, const std::string& stage)
{
    sliceProgress.set(static_cast<double>(percent));
    sliceStage.set(stage);
}

void PlaterViewModel::onSliceComplete(bool success)
{
    sliceState.set(success ? SliceState::Done : SliceState::Failed);
    isSlicing.set(false);
}

void PlaterViewModel::impl_duplicateSelected()
{
    int idx = selectedIndex.get();
    auto objs = objects.get();
    if (idx < 0 || idx >= static_cast<int>(objs.size())) return;
    updateUndoRedo();
    refreshObjects();
}

void PlaterViewModel::exportGCodeToFile()
{
    // View handles file dialog, ViewModel receives path
}

void PlaterViewModel::sendToPrinterDevice()
{
    // Initiate network send via DeviceViewModel
}

void PlaterViewModel::updateUndoRedo()
{
    canUndo.set(undoStack_.canUndo_.get());
    canRedo.set(undoStack_.canRedo_.get());
}

} // namespace Slic3r
