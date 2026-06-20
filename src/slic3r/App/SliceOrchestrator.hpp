#ifndef slic3r_App_SliceOrchestrator_hpp_
#define slic3r_App_SliceOrchestrator_hpp_

#include "libslic3r/MVVP.hpp"
#include "libslic3r/Ports/IProgressReporter.hpp"

#include <string>
#include <functional>
#include <memory>

namespace Slic3r {

class Print;
class PresetBundle;
class IGCodeConsumer;

/// Callback type for slice completion.
using SliceCompleteFn = std::function<void(bool success, const std::string& error)>;

/// Centralized slicing orchestration.
/// Coordinates the full slicing pipeline: Print::apply() on a background thread,
/// progress reporting via IProgressReporter, cancellation, and GCode delivery.
///
/// Lives in Application layer (Layer 3). Coordinates between:
///   - Model layer: Print, PresetBundle (Layer 2)
///   - Presentation layer: progress callbacks, GCode consumer (Layer 4)
class SliceOrchestrator {
public:
    SliceOrchestrator();
    ~SliceOrchestrator();

    // ?? Configuration ??
    void setPrint(Print* print);
    void setPresets(PresetBundle* presets);
    void setProgressReporter(IProgressReporter* reporter);
    void setGCodeConsumer(IGCodeConsumer* consumer);

    // ?? Slice Control ??
    /// Start slicing on a background thread.
    /// Returns false if slicing is already in progress.
    bool startSlice(SliceCompleteFn onComplete = {});

    /// Request cancellation. Slicing will stop at the next checkpoint.
    void cancelSlice();

    /// Check if slicing is currently in progress.
    bool isSlicing() const { return slicing_.get(); }

    // ?? Observables (for ViewModel binding) ??
    MVVP::Property<bool>   slicing_{false};
    MVVP::Property<int>    progress_{0};
    MVVP::Property<std::string> stage_{""};

private:
    void runSlice(SliceCompleteFn onComplete);

    Print*              print_{nullptr};
    PresetBundle*       presets_{nullptr};
    IProgressReporter*  progressReporter_{nullptr};
    IGCodeConsumer*     gcodeConsumer_{nullptr};
    bool                cancelRequested_{false};
};

} // namespace Slic3r

#endif /* slic3r_App_SliceOrchestrator_hpp_ */
