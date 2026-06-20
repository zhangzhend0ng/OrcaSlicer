#include "slic3r/App/PlaterViewModel.hpp"
#include "slic3r/App/ObjectViewModel.hpp"
#include "slic3r/App/ColorMixViewModel.hpp"
#include "slic3r/App/UndoRedoController.hpp"

#include "libslic3r/Print.hpp"
#include "libslic3r/PresetBundle.hpp"
#include "libslic3r/Model.hpp"

namespace Slic3r {

PlaterViewModel::PlaterViewModel()
{
    // Wire commands to implementation methods
    slice = MVVP::Command(
        [this] { startSlice(); },
        [this] { return sliceState.get() == SliceState::Idle && !objects.get().empty(); }
    );
    cancelSlice = MVVP::Command(
        [this] { cancelSlice(); },
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
        [this] { arrangeAll(); },
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
        [this] { duplicateSelected(); },
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
    if (!print_) return;

    auto& objs = objects.mutate();
    objs.clear();

    for (const auto* model_obj : print_->get_current_print_object_models()) {
        if (!model_obj) continue;
        ObjectInfo info;
        info.id            = model_obj->id().id;
        info.name          = model_obj->name;
        info.instanceCount = static_cast<int>(model_obj->instances.size());
        info.printable     = model_obj->printable;
        objs.push_back(std::move(info));
    }
    objects.notifyMutation();
}

void PlaterViewModel::addModelDialog()
{
    // Open file dialog (handled by View, ViewModel receives path)
    // The View calls addModelFromPath() after dialog closes
}

void PlaterViewModel::addModelFromPath(const std::string& path)
{
    if (!print_) return;
    // Model loading is delegated to the Print/Model layer
    // This is the ViewModel's interface point
    undoStack_.push(
        [this, path] { /* redo: reload model from path */ },
        [this]      { /* undo: remove last model */ },
        "Add model: " + path
    );
    updateUndoRedo();
    refreshObjects();
    isModified.set(true);
}

void PlaterViewModel::removeSelectedObject()
{
    int idx = selectedIndex.get();
    auto& objs = objects.mutate();
    if (idx < 0 || idx >= static_cast<int>(objs.size())) return;

    std::string name = objs[idx].name;
    undoStack_.push(
        [this, idx] { /* redo: remove object at idx */ },
        [this, idx, name] { /* undo: restore object */ },
        "Remove: " + name
    );

    objs.erase(objs.begin() + idx);
    objects.notifyMutation();
    updateUndoRedo();
    isModified.set(true);

    if (selectedIndex.get() >= static_cast<int>(objs.size()))
        selectedIndex.set(static_cast<int>(objs.size()) - 1);
}

void PlaterViewModel::arrangeAll()
{
    if (!print_) return;

    sliceState.set(SliceState::Running);
    // arrange logic: ModelArrange::arrange(print_->model(), ...)
    sliceState.set(SliceState::Idle);

    refreshObjects();
    undoStack_.push(
        [this] { /* redo: arrange */ },
        [this] { /* undo: restore positions */ },
        "Arrange all"
    );
    updateUndoRedo();
}

void PlaterViewModel::startSlice()
{
    if (sliceState.get() != SliceState::Idle) return;
    sliceState.set(SliceState::Running);
    sliceProgress.set(0.0);
    sliceStage.set("Preparing...");
    isSlicing.set(true);

    // The actual slicing is orchestrated by SliceOrchestrator (Phase 4).
    // PlaterViewModel initiates it and receives progress via callback.
}

void PlaterViewModel::cancelSlice()
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

void PlaterViewModel::duplicateSelected()
{
    int idx = selectedIndex.get();
    auto& objs = objects.mutate();
    if (idx < 0 || idx >= static_cast<int>(objs.size())) return;

    undoStack_.push(
        [this, idx] { /* redo: duplicate object at idx */ },
        [this]      { /* undo: remove duplicated object */ },
        "Duplicate: " + objs[idx].name
    );
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
