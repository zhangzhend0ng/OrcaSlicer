#ifndef slic3r_App_SearchModel_hpp_
#define slic3r_App_SearchModel_hpp_

#include "libslic3r/MVVP.hpp"
#include <string>
#include <vector>
#include <functional>

namespace Slic3r {

/// Fuzzy search result for a single option.
struct SearchResult {
    std::string key;
    std::string label;
    std::string group;
    int         score{0};
};

/// Pure-C++ fuzzy search / text matching utilities.
/// Extracted from Search.cpp.
/// Zero wxWidgets dependency (uses fts::fuzzy_match internally).
class SearchModel {
public:
    /// Fuzzy match a search pattern against a label.
    /// Returns true if match found, fills score and match positions.
    /// Wraps fts::fuzzy_match() from the existing vendored library.
    static bool fuzzyMatch(
        const std::wstring& pattern,
        const std::wstring& label,
        int& outScore,
        std::vector<uint16_t>& outMatches);

    /// Simple substring search (case-insensitive).
    static bool containsMatch(
        const std::string& label,
        const std::string& pattern);

    /// Score a search result (higher = better match).
    static int scoreMatch(const std::wstring& pattern, const std::wstring& label);

    // ?? Observable State ??
    MVVP::Property<std::vector<SearchResult>> results{{}};
    MVVP::Property<std::string>               searchQuery{""};
    MVVP::Property<bool>                       isSearching{false};

    // ?? Commands ??
    MVVP::Command clearSearch{
        [this] { searchQuery.set(""); results.set({}); }
    };
};

} // namespace Slic3r

#endif /* slic3r_App_SearchModel_hpp_ */
