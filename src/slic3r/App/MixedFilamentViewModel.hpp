#ifndef slic3r_App_MixedFilamentViewModel_hpp_
#define slic3r_App_MixedFilamentViewModel_hpp_

#include "libslic3r/MVVP.hpp"
#include "libslic3r/MixedFilament.hpp"

#include <string>
#include <vector>

namespace Slic3r {

/// Pure-C++ business logic for mixed filament color computation.
/// Extracted from Plater.cpp (lines 3598-5540: 13 static functions).
/// Zero wxWidgets dependency. All GUI communication via Property<T>.
///
/// Data flow:
///   View ? setFilaments() / setSelection()  ? ViewModel recalculates
///   ViewModel ? Property<entries> notifies  ? View rebuilds UI
class MixedFilamentViewModel {
public:
    // ?? Input: call these when physical filaments or mixed config changes ??
    void setPhysicalFilaments(const std::vector<std::string>& colors,
                              const std::vector<double>& nozzleDiameters);
    void setMixedFilaments(const std::vector<MixedFilament>& mixed);
    void setSelection(int index);
    void setWallLoops(size_t loops);

    // ?? Observable State (View subscribes to these) ??

    /// Each entry = one row in the mixed filament panel.
    struct Entry {
        int         mixId{-1};
        std::string displayColor;           // hex for color swatch
        std::string label;                  // "F1+F2" or "F1+F2+F3"
        std::vector<unsigned int> extruderSequence; // preview extrusions
        bool        isValid{true};
        bool        isSelected{false};
    };

    MVVP::Property<std::vector<Entry>> entries{{}};
    MVVP::Property<bool>               hasMixedFilaments{false};
    MVVP::Property<int>                selectedIndex{-1};

    // ?? Commands ??
    MVVP::Command addMix{
        [this] { /* create new MixedFilament, add to list */ }
    };
    MVVP::Command deleteSelectedMix{
        [this] { /* remove selected MixedFilament */ },
        [this] { return selectedIndex.get() >= 0; }
    };

    // ?? Pure computation helpers (public for unit testing) ??
    static std::vector<unsigned int> buildPreviewSequence(
        const MixedFilament& mf, size_t numPhysical, size_t wallLoops);
    static std::string blendDisplayColor(
        const std::vector<std::string>& colors, const std::vector<unsigned int>& sequence);
    static std::string makeLabel(const MixedFilament& mf);

private:
    void recalculate();

    std::vector<std::string>     physicalColors_;
    std::vector<double>          nozzleDiameters_;
    std::vector<MixedFilament>   mixedFilaments_;
    size_t                       wallLoops_{2};
};

} // namespace Slic3r

#endif /* slic3r_App_MixedFilamentViewModel_hpp_ */
