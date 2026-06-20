#include "slic3r/App/SystemInfoModel.hpp"
#include <sstream>
#include <random>

namespace Slic3r {

// Trim whitespace from both ends of a string
static std::string trim(std::string s)
{
    while (!s.empty() && (s.front() == ' ' || s.front() == 0x09 || s.front() == 0x0D || s.front() == 0x0A))
        s.erase(0, 1);
    while (!s.empty() && (s.back() == ' ' || s.back() == 0x09 || s.back() == 0x0D || s.back() == 0x0A))
        s.pop_back();
    return s;
}

std::map<std::string, std::string> SystemInfoModel::parseKeyValueConfig(
    const std::string& content, char delimiter)
{
    std::map<std::string, std::string> result;
    std::istringstream stream(content);
    std::string line;
    while (std::getline(stream, line)) {
        auto pos = line.find(delimiter);
        if (pos != std::string::npos) {
            std::string key = trim(line.substr(0, pos));
            std::string val = trim(line.substr(pos + 1));
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
    const char hex[] = "0123456789abcdef";
    std::string id;
    id.reserve(36);
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
    oss << '{';
    bool first = true;
    for (auto it = info.begin(); it != info.end(); ++it) {
        if (!first) oss << ", ";
        oss << '"' << it->first << '"' << ':' << '"' << it->second << '"';
        first = false;
    }
    oss << '}';
    return oss.str();
}

} // namespace Slic3r
