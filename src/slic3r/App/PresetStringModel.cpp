#include "slic3r/App/PresetStringModel.hpp"
#include <algorithm>
#include <cctype>
#include <ctime>
#include <sstream>
#include <iomanip>
#include <boost/algorithm/string.hpp>

namespace Slic3r {

std::string PresetStringModel::removeSpecialKeys(const std::string& str)
{
    std::string result;
    result.reserve(str.size());
    for (char c : str) {
        if (c == 10 || c == 9 || c == 13 || c == 11 || c == '@' || c == ';')
            continue;
        result.push_back(c);
    }
    return result;
}

bool PresetStringModel::isAllDigits(const std::string& str)
{
    return !str.empty() && std::all_of(str.begin(), str.end(),
        [](char c) { return std::isdigit(static_cast<unsigned char>(c)); });
}

bool PresetStringModel::caseInsensitiveCompare(const std::string& a, const std::string& b)
{
    return std::equal(a.begin(), a.end(), b.begin(), b.end(),
        [](char ca, char cb) {
            return std::tolower(static_cast<unsigned char>(ca)) ==
                   std::tolower(static_cast<unsigned char>(cb));
        }) && a.size() == b.size();
}

std::string PresetStringModel::currentTime(const char* format)
{
    std::time_t now = std::time(nullptr);
    std::tm tm_buf;
    localtime_s(&tm_buf, &now);
    char buf[64];
    std::strftime(buf, sizeof(buf), format, &tm_buf);
    return std::string(buf);
}

std::string PresetStringModel::currentTimestamp()
{
    return currentTime("%Y%m%d%H%M%S");
}

std::string PresetStringModel::extractMachineName(const std::string& presetName)
{
    std::vector<std::string> parts;
    boost::split(parts, presetName, boost::is_any_of(" "));
    std::string result;
    for (const auto& part : parts) {
        if (part.find('.') != std::string::npos && part.size() <= 4) {
            bool isNozzle = true;
            for (char c : part) {
                if (c != '.' && !std::isdigit(static_cast<unsigned char>(c))) {
                    isNozzle = false; break;
                }
            }
            if (isNozzle) break;
        }
        if (!result.empty()) result += " ";
        result += part;
    }
    return result;
}

std::string PresetStringModel::extractFilamentName(std::string& presetName)
{
    boost::trim(presetName);
    std::vector<std::string> parts;
    boost::split(parts, presetName, boost::is_any_of(" "));
    if (parts.size() >= 3) return parts.back();
    return presetName;
}

std::string PresetStringModel::extractVendorName(std::string& presetName)
{
    boost::trim(presetName);
    std::vector<std::string> parts;
    boost::split(parts, presetName, boost::is_any_of(" "));
    if (!parts.empty()) return parts.front();
    return presetName;
}

std::string PresetStringModel::md5Hash(const std::string& input)
{
    unsigned int hash = 0;
    for (char c : input)
        hash = ((hash << 5) + hash) + static_cast<unsigned char>(c);
    std::ostringstream oss;
    oss << std::hex << std::setfill('0') << std::setw(8) << hash;
    return oss.str();
}

std::string PresetStringModel::filamentId(const std::string& vendorTypeSerial)
{
    return md5Hash(vendorTypeSerial);
}

std::string PresetStringModel::extractNozzleDiameter(const std::string& printerName)
{
    std::vector<std::string> parts;
    boost::split(parts, printerName, boost::is_any_of(" "));
    for (const auto& part : parts) {
        if (part.find('.') != std::string::npos && part.size() <= 4) {
            bool isNozzle = true;
            for (char c : part) {
                if (c != '.' && !std::isdigit(static_cast<unsigned char>(c))) {
                    isNozzle = false; break;
                }
            }
            if (isNozzle) return part;
        }
    }
    return "";
}

std::string PresetStringModel::pureOptionKey(std::string optKey)
{
    auto pos = optKey.find('#');
    if (pos != std::string::npos) optKey.erase(pos);
    return optKey;
}

size_t PresetStringModel::idFromOptionKey(std::string optKey)
{
    auto pos = optKey.find('#');
    if (pos == std::string::npos) return 0;
    try { return static_cast<size_t>(std::stoull(optKey.substr(pos + 1))); }
    catch (...) { return 0; }
}

std::string PresetStringModel::presetIconName(int presetType, int)
{
    switch (presetType) {
    case 0: return "cog";
    case 1: return "spool";
    case 2: return "printer";
    default: return "cog";
    }
}

std::set<std::string> PresetStringModel::findNewPresets(
    const std::map<std::string, std::string>& oldData,
    const std::map<std::string, std::string>& newData)
{
    std::set<std::string> added;
    for (auto it = newData.begin(); it != newData.end(); ++it) {
        auto oldIt = oldData.find(it->first);
        if (oldIt == oldData.end() || oldIt->second != it->second)
            added.insert(it->first);
    }
    return added;
}

std::string PresetStringModel::firstNewPreset(
    const std::map<std::string, std::string>& oldData,
    const std::map<std::string, std::string>& newData)
{
    std::set<std::string> added = findNewPresets(oldData, newData);
    return added.empty() ? "" : *added.begin();
}

} // namespace Slic3r
