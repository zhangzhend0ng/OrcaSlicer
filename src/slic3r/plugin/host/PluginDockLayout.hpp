#pragma once
#include <string>
#include <vector>

namespace Slic3r::GUI {
// AUI escapes separators in captions and other values. Keep the original pane
// record intact for LoadPaneInfo instead of splitting escaped vertical bars.
inline std::string plugin_saved_pane_layout(const std::string& perspective, const std::string& name)
{
    const std::string prefix = "name=" + name + ";";
    size_t begin = 0;
    bool escaped = false;
    for (size_t i = 0; i <= perspective.size(); ++i) {
        if (i == perspective.size() || (!escaped && perspective[i] == '|')) {
            const auto entry = perspective.substr(begin, i - begin);
            if (entry.compare(0, prefix.size(), prefix) == 0)
                return entry;
            begin = i + 1;
        }
        if (i < perspective.size()) {
            if (!escaped && perspective[i] == '\\')
                escaped = true;
            else
                escaped = false;
        }
    }
    return {};
}

// A project reset also happens during startup, before delayed plugins create
// their windows. Do not let that intermediate save erase their previous layout.
// Existing panes always win, including their explicit hidden state.
inline std::string plugin_preserve_uncreated_panes(const std::string& current, const std::string& previous)
{
    if (current.compare(0, 8, "layout2|") != 0 || previous.compare(0, 8, "layout2|") != 0)
        return current;
    const auto entries = [](const std::string& perspective) {
        std::vector<std::string> result;
        size_t begin = 0;
        for (size_t i = 0; i <= perspective.size(); ++i) {
            // wx escapes only | and ;, not backslashes. Even a literal backslash
            // before an escaped | must not turn it into a record separator.
            if (i == perspective.size() || (perspective[i] == '|' && (i == 0 || perspective[i - 1] != '\\'))) {
                result.push_back(perspective.substr(begin, i - begin));
                begin = i + 1;
            }
        }
        return result;
    };
    const auto old_entries = entries(previous);
    const auto new_entries = entries(current);
    std::string result = current;
    if (result.back() != '|') result += '|';
    std::vector<std::string> retained_docks;
    for (const auto& entry : old_entries) {
        if (entry.compare(0, std::string("name=plugin:").size(), "name=plugin:") != 0)
            continue;
        const auto name_end = entry.find(';');
        if (name_end == std::string::npos)
            continue;
        const auto name_field = entry.substr(0, name_end + 1);
        bool present = false;
        for (const auto& active : new_entries)
            if (active.compare(0, name_field.size(), name_field) == 0) { present = true; break; }
        if (present)
            continue;
        result += entry + '|';
        const auto field = [&entry](const char* key) {
            const std::string prefix = std::string(";") + key + '=';
            const auto begin = entry.rfind(prefix);
            if (begin == std::string::npos) return std::string();
            const auto value = begin + prefix.size();
            return entry.substr(value, entry.find(';', value) - value);
        };
        const auto direction = field("dir"), layer = field("layer"), row = field("row");
        if (!direction.empty() && !layer.empty() && !row.empty())
            retained_docks.push_back("dock_size(" + direction + ',' + layer + ',' + row + ")=");
    }
    // Preserve only docks used by an absent plugin pane. A current dock (which
    // may be shared with a built-in pane) retains its current size.
    for (const auto& entry : old_entries) {
        for (const auto& dock : retained_docks) {
            if (entry.compare(0, dock.size(), dock) != 0)
                continue;
            bool present = false;
            for (const auto& active : new_entries)
                if (active.compare(0, dock.size(), dock) == 0) { present = true; break; }
            if (!present) result += entry + '|';
            break;
        }
    }
    return result;
}
} // namespace Slic3r::GUI
