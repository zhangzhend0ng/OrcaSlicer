#ifndef slic3r_App_UndoRedoController_hpp_
#define slic3r_App_UndoRedoController_hpp_

#include "libslic3r/MVVP.hpp"

#include <functional>
#include <string>
#include <vector>
#include <deque>

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
        while (static_cast<int>(stack_.size()) > current_ + 1)
            stack_.pop_back();

        Entry entry;
        entry.redo        = std::move(doAction);
        entry.undo        = std::move(undoAction);
        entry.description = std::move(description);
        stack_.push_back(std::move(entry));
        current_ = static_cast<int>(stack_.size()) - 1;
        canUndo_.set(true);
        canRedo_.set(false);
    }

    /// Undo the last action.
    void undo() {
        if (!canUndo_.get() || current_ < 0) return;
        if (stack_[current_].undo) stack_[current_].undo();
        current_--;
        canUndo_.set(current_ >= 0);
        canRedo_.set(true);
    }

    /// Redo the last undone action.
    void redo() {
        if (!canRedo_.get() || current_ + 1 >= static_cast<int>(stack_.size())) return;
        current_++;
        if (stack_[current_].redo) stack_[current_].redo();
        canRedo_.set(current_ + 1 < static_cast<int>(stack_.size()));
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
    MVVP::Property<bool>        canUndo_{false};
    MVVP::Property<bool>        canRedo_{false};
    MVVP::Property<std::string> lastAction_{""};

private:
    struct Entry {
        Action      undo;
        Action      redo;
        std::string description;
    };
    std::deque<Entry> stack_;
    int current_{-1};
};

} // namespace Slic3r

#endif /* slic3r_App_UndoRedoController_hpp_ */
