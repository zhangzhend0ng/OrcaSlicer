#include "catch2/catch.hpp"
#include "slic3r/App/SearchModel.hpp"

using namespace Slic3r;

TEST_CASE("SearchModel containsMatch case insensitive", "[SearchModel]") {
    REQUIRE(SearchModel::containsMatch("Layer Height", "layer"));
    REQUIRE(SearchModel::containsMatch("WALL LOOPS", "wall"));
    REQUIRE_FALSE(SearchModel::containsMatch("Infill", "support"));
}

TEST_CASE("SearchModel containsMatch empty pattern matches all", "[SearchModel]") {
    REQUIRE(SearchModel::containsMatch("anything", ""));
}

TEST_CASE("SearchModel fuzzyMatch finds substring", "[SearchModel]") {
    std::wstring label = L"Layer Height";
    std::wstring pattern = L"layer";
    int score = 0;
    std::vector<uint16_t> matches;
    REQUIRE(SearchModel::fuzzyMatch(pattern, label, score, matches));
    REQUIRE_FALSE(matches.empty());
}

TEST_CASE("SearchModel fuzzyMatch empty pattern returns false", "[SearchModel]") {
    int score;
    std::vector<uint16_t> matches;
    REQUIRE_FALSE(SearchModel::fuzzyMatch(L"", L"label", score, matches));
}

TEST_CASE("SearchModel clearSearch clears state", "[SearchModel][MVVP]") {
    SearchModel sm;
    sm.searchQuery.set("test");
    sm.clearSearch.execute();
    REQUIRE(sm.searchQuery.get().empty());
}
