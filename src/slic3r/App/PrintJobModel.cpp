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
    // Check for .gcode or .gco extension
    if (path.size() < 6) return false;
    std::string lower = path;
    for (auto& c : lower) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return lower.ends_with(".gcode") || lower.ends_with(".gco");
}

std::string PrintJobModel::extractPrintTime(const std::string& /*gcodePath*/)
{
    // Stub: real implementation parses GCode comments for estimated time
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
