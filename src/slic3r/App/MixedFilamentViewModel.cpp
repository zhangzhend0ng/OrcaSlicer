#include "slic3r/App/MixedFilamentViewModel.hpp"

#include <algorithm>
#include <numeric>
#include <sstream>
#include <cmath>

namespace Slic3r {

// ?? Input setters ??

void MixedFilamentViewModel::setPhysicalFilaments(
    const std::vector<std::string>& colors,
    const std::vector<double>& nozzleDiameters)
{
    physicalColors_    = colors;
    nozzleDiameters_   = nozzleDiameters;
    recalculate();
}

void MixedFilamentViewModel::setMixedFilaments(const std::vector<MixedFilament>& mixed)
{
    mixedFilaments_ = mixed;
    recalculate();
}

void MixedFilamentViewModel::setSelection(int index)
{
    selectedIndex.set(index);
    auto ents = entries.get();
    for (size_t i = 0; i < ents.size(); ++i)
        ents[i].isSelected = (static_cast<int>(i) == index);
    entries.set(ents);
}

void MixedFilamentViewModel::setWallLoops(size_t loops)
{
    wallLoops_ = loops;
    recalculate();
}

// ?? Recalculation (the core business logic, formerly in Plater.cpp) ??

void MixedFilamentViewModel::recalculate()
{
    std::vector<Entry> result;
    hasMixedFilaments.set(!mixedFilaments_.empty());

    for (size_t i = 0; i < mixedFilaments_.size(); ++i) {
        const auto& mf = mixedFilaments_[i];
        Entry entry;
        entry.mixId           = static_cast<int>(i);
        entry.label           = makeLabel(mf);
        entry.extruderSequence = buildPreviewSequence(mf, physicalColors_.size(), wallLoops_);
        entry.displayColor    = blendDisplayColor(physicalColors_, entry.extruderSequence);
        entry.isValid         = !entry.extruderSequence.empty();
        entry.isSelected      = (selectedIndex.get() == static_cast<int>(i));
        result.push_back(std::move(entry));
    }

    entries.set(result);
}

// ?? Pure computation ??

std::string MixedFilamentViewModel::makeLabel(const MixedFilament& mf)
{
    // Build "F1+F2+..." style label from filament indices
    std::ostringstream oss;
    bool first = true;

    auto addComponent = [&](unsigned int comp) {
        if (comp > 0) {
            if (!first) oss << "+";
            oss << "F" << comp;
            first = false;
        }
    };

    addComponent(mf.component_a);
    addComponent(mf.component_b);
    return oss.str();
}

std::vector<unsigned int> MixedFilamentViewModel::buildPreviewSequence(
    const MixedFilament& mf, size_t numPhysical, size_t wallLoops)
{
    // Build extrusion preview sequence for display purposes.
    // Simplified version of the original Plater.cpp logic.
    std::vector<unsigned int> seq;

    if (numPhysical == 0) return seq;

    // Collect active extruder indices from the mixed filament
    auto addIfNonZero = [&](unsigned int v) {
        if (v > 0 && v <= numPhysical) seq.push_back(v);
    };

    // Wall loops - repeat the primary filament
    for (size_t w = 0; w < wallLoops && w < 3; ++w)
        addIfNonZero(mf.component_a);

    // Infill - alternate between components
    addIfNonZero(mf.component_a);
    addIfNonZero(mf.component_b);

    return seq;
}

std::string MixedFilamentViewModel::blendDisplayColor(
    const std::vector<std::string>& colors,
    const std::vector<unsigned int>& sequence)
{
    if (colors.empty() || sequence.empty()) return "#808080FF";

    // Simple average of RGB components weighted by frequency
    double r = 0, g = 0, b = 0;
    size_t count = 0;

    for (unsigned int idx : sequence) {
        if (idx == 0 || idx > colors.size()) continue;
        const std::string& hex = colors[idx - 1];
        // Parse hex color "#RRGGBB" or "#RRGGBBAA"
        if (hex.size() >= 7 && hex[0] == '#') {
            unsigned int rgb;
            try {
                rgb = static_cast<unsigned int>(std::stoul(hex.substr(1, 6), nullptr, 16));
                r += ((rgb >> 16) & 0xFF);
                g += ((rgb >> 8)  & 0xFF);
                b += (rgb & 0xFF);
                count++;
            } catch (...) {}
        }
    }

    if (count == 0) return "#808080FF";

    r /= count; g /= count; b /= count;
    char buf[16];
    snprintf(buf, sizeof(buf), "#%02X%02X%02XFF",
             static_cast<int>(r), static_cast<int>(g), static_cast<int>(b));
    return std::string(buf);
}

} // namespace Slic3r
