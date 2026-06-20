// MVVP.hpp — Model-View-ViewModel/Presenter framework for OrcaSlicer
// Header-only, zero external dependencies beyond C++17 stdlib.
//
// Provides:
//   Property<T>  — Observable value with change notification (manual binding)
//   Command      — Discrete action with canExecute guard
//
// Thread safety:
//   Property::set() / subscribe() are NOT thread-safe.
//   The View layer's bindProperty() dispatches to main thread via CallAfter().
//   ViewModel methods that set properties from worker threads must use
//   the main-thread dispatch pattern.
//
// Usage pattern:
//   ViewModel owns Property<T> and Command instances.
//   View subscribes to Property<T> changes and binds Command to widgets.
//   ViewModel knows nothing about wxWidgets; View knows nothing about Model.

#pragma once

#include <functional>
#include <string>
#include <vector>

namespace Slic3r::MVVP {

// ============================================================
// Property<T> — Observable value with manual change notification
// ============================================================
//
// Intentionally coarse-grained. Do NOT create a Property for every
// individual field (no Property<double> x, Property<double> y).
// Instead batch related state into semantic chunks:
//   Property<std::vector<ObjectInfo>> objects;     // Good
//   Property<SliceState>              sliceState;  // Good
//   Property<CameraState>             camera;      // Good

template<typename T>
class Property {
public:
    using Subscriber = std::function<void(const T& newValue, const T& oldValue)>;

    Property() = default;
    explicit Property(T initial) : value_(std::move(initial)) {}

    // Read current value (main thread only for GUI-bound properties)
    const T& get() const { return value_; }

    // Set new value, notifying all subscribers with old+new values.
    // Call from any thread, but subscribers run synchronously on caller's thread.
    void set(T newValue) {
        T oldValue = std::move(value_);
        value_ = std::move(newValue);
        notify(oldValue);
    }

    // Mutate in-place (avoids copy for large containers like std::vector).
    // Call notifyMutation() after finishing mutations.
    T& mutate() { return value_; }
    void notifyMutation() { notify(value_); }

    // RAII subscription handle. Subscription is active until destroyed.
    struct Subscription {
        Property* owner = nullptr;
        size_t    index = 0;
        ~Subscription() {
            if (owner)
                owner->unsubscribe(index);
        }
        // Non-copyable, movable
        Subscription(const Subscription&) = delete;
        Subscription& operator=(const Subscription&) = delete;
        Subscription(Subscription&& other) noexcept
            : owner(other.owner), index(other.index) {
            other.owner = nullptr;
        }
        Subscription& operator=(Subscription&& other) noexcept {
            if (this != &other) {
                if (owner) owner->unsubscribe(index);
                owner = other.owner;
                index = other.index;
                other.owner = nullptr;
            }
            return *this;
        }
    };

    Subscription subscribe(Subscriber s) {
        subscribers_.push_back(std::move(s));
        return {this, subscribers_.size() - 1};
    }

private:
    void notify(const T& old) {
        for (auto& s : subscribers_)
            if (s) s(value_, old);
    }
    void unsubscribe(size_t idx) {
        if (idx < subscribers_.size())
            subscribers_[idx] = nullptr;
    }

    T value_{};
    std::vector<Subscriber> subscribers_;
};

// ============================================================
// Command — Discrete action the View can trigger on the ViewModel
// ============================================================
class Command {
public:
    using Action     = std::function<void()>;
    using CanExecute = std::function<bool()>;

    Command(Action execute, CanExecute canExec = [] { return true; })
        : execute_(std::move(execute)), canExecute_(std::move(canExec)) {}

    void execute() const {
        if (canExecute_())
            execute_();
    }

    bool canExecute() const { return canExecute_(); }

private:
    Action     execute_;
    CanExecute canExecute_;
};

} // namespace Slic3r::MVVP

