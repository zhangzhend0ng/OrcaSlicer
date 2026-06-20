#include "slic3r/App/SearchModel.hpp"
#include <algorithm>
#include <cctype>
#include <cwctype>

namespace Slic3r {

bool SearchModel::fuzzyMatch(
    const std::wstring& pattern,
    const std::wstring& label,
    int& outScore,
    std::vector<uint16_t>& outMatches)
{
    // Stub: delegates to fts::fuzzy_match() from the vendored fuzzy search library.
    // Real implementation links against the existing libslic3r fuzzy search.
    // For now, fall back to substring match.
    if (pattern.empty()) {
        outScore = 0;
        return false;
    }

    // Simple substring search
    auto it = std::search(label.begin(), label.end(),
                          pattern.begin(), pattern.end(),
                          [](wchar_t a, wchar_t b) {
                              return std::towlower(a) == std::towlower(b);
                          });

    if (it != label.end()) {
        outScore = static_cast<int>(label.size() - pattern.size());
        size_t idx = std::distance(label.begin(), it);
        outMatches.clear();
        for (size_t i = 0; i < pattern.size(); ++i)
            outMatches.push_back(static_cast<uint16_t>(idx + i));
        return true;
    }

    outScore = 0;
    outMatches.clear();
    return false;
}

bool SearchModel::containsMatch(const std::string& label, const std::string& pattern)
{
    if (pattern.empty()) return true;
    auto it = std::search(label.begin(), label.end(),
                          pattern.begin(), pattern.end(),
                          [](char a, char b) {
                              return std::tolower(static_cast<unsigned char>(a)) ==
                                     std::tolower(static_cast<unsigned char>(b));
                          });
    return it != label.end();
}

int SearchModel::scoreMatch(const std::wstring& pattern, const std::wstring& label)
{
    if (pattern.empty()) return 0;
    int score = 0;
    std::vector<uint16_t> matches;
    if (fuzzyMatch(pattern, label, score, matches))
        return score;
    return -1;
}

} // namespace Slic3r
