#include "slic3r/App/SystemInfoModel.hpp"
#include <sstream>
#include <random>
#include <iomanip>

namespace Slic3r {

std::map<std::string, std::string> SystemInfoModel::parseKeyValueConfig(
    const std::string& content, char delimiter)
{
    std::map<std::string, std::string> result;
    std::istringstream stream(content);
    std::string line;
    while (std::getline(stream, line)) {
        auto pos = line.find(delimiter);
        if (pos != std::string::npos) {
            std::string key = line.substr(0, pos);
            std::string val = line.substr(pos + 1);
            // Trim whitespace
            key.erase(0, key.find_first_not_of(" 	"));
            key.erase(key.find_last_not_of(" 	") + 1);
            val.erase(0, val.find_first_not_of(" 	"));
            val.erase(val.find_last_not_of(" 	
") + 1);
            if (!key.empty())
                result[key] = val;
        }
    }
    return result;
}

std::string SystemInfoModel::generateUniqueId()
{
    static std::random_device rd;
    static std::mt19937 gen(rd());
    static std::uniform_int_distribution<> dis(0, 15);
    static const char* hex = "0123456789abcdef";

    std::string id;
    id.reserve(32);
    for (int i = 0; i < 32; ++i) {
        if (i == 8 || i == 13 || i == 18 || i == 23)
            id += '-';
        id += hex[dis(gen)];
    }
    return id;
}

std::string SystemInfoModel::systemInfoToJson(
    const std::map<std::string, std::string>& info)
{
    std::ostringstream oss;
    oss << "{";
    bool first = true;
    for (const auto& [key, value] : info) {
        if (!first) oss << ", ";
        oss << """ << key << "": "" << value << """;
        first = false;
    }
    oss << "}";
    return oss.str();
}

} // namespace Slic3r
