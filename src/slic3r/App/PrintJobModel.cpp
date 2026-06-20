#include "slic3r/App/PrintJobModel.hpp"

namespace Slic3r {

std::string PrintJobModel::jobStateToString(JobState state)
{
    switch (state) {
    case JobState::Idle:       return "Idle";
    case JobState::Preparing:  return "Preparing";
    case JobState::Sending:    return "Sending";
    case JobState::Printing:   return "Printing";
    case JobState::Completed:  return "Completed";
    case JobState::Failed:     return "Failed";
    case JobState::Cancelled:  return "Cancelled";
    }
    return "Unknown";
}

bool PrintJobModel::isValidGCodePath(const std::string& path)
{
    if (path.size() < 6) return false;
    std::string lower = path;
    for (auto& c : lower) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    size_t len = lower.size();
    return (len >= 6 && lower.compare(len - 6, 6, ".gcode") == 0) ||
           (len >= 4 && lower.compare(len - 4, 4, ".gco") == 0);
}

std::string PrintJobModel::extractPrintTime(const std::string&)
{
    return "00:00:00";
}

bool PrintJobModel::parseHostPort(const std::string& hostPort,
                                   std::string& host, int& port)
{
    auto colon = hostPort.find_last_of(':');
    if (colon == std::string::npos) {
        host = hostPort;
        port = 80;
        return true;
    }
    host = hostPort.substr(0, colon);
    try {
        port = std::stoi(hostPort.substr(colon + 1));
    } catch (...) {
        return false;
    }
    return port > 0 && port < 65536;
}

} // namespace Slic3r
