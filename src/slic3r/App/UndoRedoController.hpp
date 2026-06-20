#ifndef slic3r_App_UndoRedoController_hpp_
#define slic3r_App_UndoRedoController_hpp_

#include "libslic3r/MVVP.hpp"

#include <functional>
#include <string>
#include <vector>

namespace Slic3r {

/// Lightweight undo/redo stack for MVVP ViewModels.
/// Stores (do, undo) pairs with descriptions.
/// Zero wxWidgets dependency (replaces wxCommandProcessor).
class UndoRedoController {
public:
    using Action = std::function<void()>;

    /// Push an undoable action onto the stack.
    void push(Action doAction, Action undoAction, std::string description) {
        // Discard any redo history after current position
        stack_.resize(current_ + 1);
        stack_.push_back({std::move(doAction), std::move(undoAction), std::move(description)});
        current_ = stack_.size() - 1;
        canUndo_.set(true);
        canRedo_.set(false);
    }

    /// Undo the last action.
    void undo() {
        if (!canUndo_.get()) return;
        stack_[current_].undo();
        current_--;
        canUndo_.set(current_ >= 0);
        canRedo_.set(true);
    }

    /// Redo the last undone action.
    void redo() {
        if (!canRedo_.get()) return;
        current_++;
        stack_[current_].redo();
        canRedo_.set(current_ < static_cast<int>(stack_.size()) - 1);
        canUndo_.set(true);
    }

    /// Clear all history.
    void clear() {
        stack_.clear();
        current_ = -1;
        canUndo_.set(false);
        canRedo_.set(false);
    }

    // Observable state for View binding
    MVVP::Property<bool> canUndo_{false};
    MVVP::Property<bool> canRedo_{false};
    MVVP::Property<std::string> lastAction_{""};

private:
    struct Entry {
        Action      undo;
        Action      redo;
        std::string description;
        Entry(Action d, Action u, std::string desc)
            : redo(std::move(d)), undo(std::move(u)), description(std::move(desc)) {}
    };
    std::vector<Entry> stack_;
    int current_{-1};
};

} // namespace Slic3r

#endif /* slic3r_App_UndoRedoController_hpp_ */
