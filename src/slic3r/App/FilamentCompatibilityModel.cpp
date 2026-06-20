#include "slic3r/App/FilamentCompatibilityModel.hpp"
#include <algorithm>
#include <cctype>

namespace Slic3r {

std::vector<std::vector<bool>> FilamentCompatibilityModel::buildCompatibilityMatrix(size_t n)
{
    std::vector<std::vector<bool>> matrix(n, std::vector<bool>(n, true));
    return matrix;
}

bool FilamentCompatibilityModel::isCategoryCompatible(FilamentCategory a, FilamentCategory b)
{
    // Same category is always compatible
    if (a == b) return true;
    // Support material is compatible with everything
    if (a == FilamentCategory::Support || b == FilamentCategory::Support) return true;
    // PLA and PETG are compatible
    if ((a == FilamentCategory::PLA && b == FilamentCategory::PETG) ||
        (a == FilamentCategory::PETG && b == FilamentCategory::PLA)) return true;
    // Default: incompatible
    return false;
}

std::vector<ResolvedFilamentCategory> FilamentCompatibilityModel::resolveCategories(
    const std::vector<std::string>& filamentTypes)
{
    std::vector<ResolvedFilamentCategory> result;
    for (const auto& raw : filamentTypes) {
        ResolvedFilamentCategory rfc;
        rfc.rawType       = raw;
        rfc.normalizedType = normalizeFilamentType(raw);
        rfc.category       = parseCategory(rfc.normalizedType);
        result.push_back(std::move(rfc));
    }
    return result;
}

std::string FilamentCompatibilityModel::normalizeFilamentType(const std::string& type)
{
    std::string result;
    result.reserve(type.size());
    for (char c : type) {
        if (c != '-' && c != ' ' && c != '_')
            result.push_back(static_cast<char>(std::toupper(static_cast<unsigned char>(c))));
    }
    return result;
}

FilamentCategory FilamentCompatibilityModel::parseCategory(const std::string& type)
{
    if (type.find("PLA") != std::string::npos)   return FilamentCategory::PLA;
    if (type.find("ABS") != std::string::npos)   return FilamentCategory::ABS;
    if (type.find("PETG") != std::string::npos)  return FilamentCategory::PETG;
    if (type.find("TPU") != std::string::npos)   return FilamentCategory::TPU;
    if (type.find("PA") != std::string::npos ||
        type.find("NYLON") != std::string::npos) return FilamentCategory::PA;
    if (type.find("PC") != std::string::npos)    return FilamentCategory::PC;
    if (type.find("PVA") != std::string::npos)   return FilamentCategory::PVA;
    if (type.find("HIPS") != std::string::npos)  return FilamentCategory::HIPS;
    if (type.find("PP") != std::string::npos)    return FilamentCategory::PP;
    if (type.find("ASA") != std::string::npos)   return FilamentCategory::ASA;
    if (type.find("SUPPORT") != std::string::npos) return FilamentCategory::Support;
    return FilamentCategory::Other;
}

} // namespace Slic3r
