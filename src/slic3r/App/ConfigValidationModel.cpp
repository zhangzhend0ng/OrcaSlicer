#include "slic3r/App/ConfigValidationModel.hpp"
#include "libslic3r/PrintConfig.hpp"

#include <sstream>
#include <iomanip>
#include <algorithm>
#include <iterator>
#include <set>

namespace Slic3r {

std::string ConfigValidationModel::bedTypeToRuleKey(int bedType)
{
    // BedType enum values: btPEI=0, btGESP=1, etc.
    // Match the original Tab.cpp mapping
    switch (bedType) {
    case 0:  return "btPEI";
    case 1:  return "btGESP";
    default: return "";
    }
}

std::string ConfigValidationModel::nozzleDiameterToRuleKey(double diameter)
{
    std::ostringstream ss;
    ss << std::fixed << std::setprecision(2) << diameter;
    std::string out = ss.str();
    // Trim trailing zeros
    while (!out.empty() && out.back() == '0')
        out.pop_back();
    if (!out.empty() && out.back() == '.')
        out.pop_back();
    return out + "mm";
}

std::vector<std::string> ConfigValidationModel::intersect(
    const std::vector<std::string>& a,
    const std::vector<std::string>& b)
{
    std::vector<std::string> result;
    std::copy_if(b.begin(), b.end(), std::back_inserter(result),
        [&a](const auto& e) {
            return std::find(a.begin(), a.end(), e) != a.end();
        });
    return result;
}

std::vector<std::string> ConfigValidationModel::unionSets(
    const std::vector<std::string>& a,
    const std::vector<std::string>& b)
{
    std::vector<std::string> result;
    std::set_union(a.begin(), a.end(), b.begin(), b.end(),
                   std::back_inserter(result));
    return result;
}

std::vector<std::string> ConfigValidationModel::subtract(
    const std::vector<std::string>& a,
    const std::vector<std::string>& b)
{
    std::vector<std::string> result;
    std::copy_if(a.begin(), a.end(), std::back_inserter(result),
        [&b](const auto& e) {
            return std::find(b.begin(), b.end(), e) == b.end();
        });
    return result;
}

DynamicPrintConfig ConfigValidationModel::resolveModelConfig(
    const DynamicPrintConfig& config)
{
    DynamicPrintConfig resolved(config);

    if (const auto* extruder_opt = config.option<ConfigOptionInt>("extruder");
        extruder_opt != nullptr && extruder_opt->value > 0)
    {
        const int extruder = extruder_opt->value;
        if (!resolved.has("wall_filament"))
            resolved.set_key_value("wall_filament", new ConfigOptionInt(extruder));
        if (!resolved.has("sparse_infill_filament"))
            resolved.set_key_value("sparse_infill_filament", new ConfigOptionInt(extruder));
        if (!resolved.has("solid_infill_filament"))
            resolved.set_key_value("solid_infill_filament", new ConfigOptionInt(extruder));
    }

    if (!resolved.has("solid_infill_filament") && resolved.has("sparse_infill_filament"))
        resolved.set_key_value("solid_infill_filament",
            new ConfigOptionInt(resolved.opt_int("sparse_infill_filament")));

    return resolved;
}


bool ConfigValidationModel::isImproperCategory(
    const std::string& category, int filamentCount, bool isObjectSettings)
{
    return category.empty() ||
        (filamentCount == 1 && (category == "Extruders" || category == "Wipe options")) ||
        (!isObjectSettings && category == "Support material");
}

} // namespace Slic3r
