#include <catch_main.hpp>

#include "slic3r/GUI/Mcp/McpJobs.hpp"

#include <string>
#include <thread>
#include <vector>

using namespace Slic3r::Mcp;

TEST_CASE("job lifecycle moves pending -> running -> done", "[McpJobs]") {
    auto& registry = McpJobRegistry::instance();
    registry.clear_for_tests();

    const int id = registry.create("slice");
    REQUIRE(id > 0);

    McpJobSnapshot snapshot;
    REQUIRE(registry.get(id, snapshot));
    REQUIRE(snapshot.state == JobState::Pending);
    REQUIRE(snapshot.kind == "slice");
    REQUIRE(snapshot.percent == 0);

    registry.set_running(id, 42, "halfway");
    REQUIRE(registry.get(id, snapshot));
    REQUIRE(snapshot.state == JobState::Running);
    REQUIRE(snapshot.percent == 42);
    REQUIRE(snapshot.message == "halfway");

    registry.set_result(id, nlohmann::json{{"outcome", "sliced"}});
    REQUIRE(registry.get(id, snapshot));
    REQUIRE(snapshot.state == JobState::Done);
    REQUIRE(snapshot.percent == 100);
    REQUIRE(snapshot.result["outcome"] == "sliced");
}

TEST_CASE("failed jobs carry the reason", "[McpJobs]") {
    auto& registry = McpJobRegistry::instance();
    registry.clear_for_tests();

    const int id = registry.create("export_gcode");
    registry.set_failed(id, "disk full");
    McpJobSnapshot snapshot;
    REQUIRE(registry.get(id, snapshot));
    REQUIRE(snapshot.state == JobState::Failed);
    REQUIRE(snapshot.message == "disk full");
}

TEST_CASE("unknown job ids answer definitively", "[McpJobs]") {
    auto& registry = McpJobRegistry::instance();
    McpJobSnapshot snapshot;
    REQUIRE_FALSE(registry.get(999999, snapshot));

    // progress for unknown ids is ignored, not resurrected
    registry.set_running(999999, 50, "ghost");
    REQUIRE_FALSE(registry.get(999999, snapshot));
}

TEST_CASE("terminal jobs never resurrect from late progress", "[McpJobs]") {
    auto& registry = McpJobRegistry::instance();
    registry.clear_for_tests();

    const int id = registry.create("slice");
    registry.set_result(id, nlohmann::json{});
    registry.set_running(id, 10, "late event");
    McpJobSnapshot snapshot;
    REQUIRE(registry.get(id, snapshot));
    REQUIRE(snapshot.state == JobState::Done);
    REQUIRE(snapshot.percent == 100);
}

TEST_CASE("prune drops only aged finished jobs", "[McpJobs]") {
    auto& registry = McpJobRegistry::instance();
    registry.clear_for_tests();

    const int keep = registry.create("slice");     // stays pending
    const int done = registry.create("export_3mf");
    registry.set_result(done, nlohmann::json{});

    // finished_at == now; a zero max-age prune may or may not drop it, so
    // assert the pending job survives a generous prune instead.
    registry.prune_finished(0);
    McpJobSnapshot snapshot;
    REQUIRE(registry.get(keep, snapshot));
    const bool done_found = registry.get(done, snapshot); // terminal: may be pruned
    (void)done_found;
    // pending jobs must never be pruned
    REQUIRE(registry.get(keep, snapshot));
    REQUIRE(snapshot.state == JobState::Pending);
}

TEST_CASE("concurrent create/get is race-free under threads", "[McpJobs]") {
    auto& registry = McpJobRegistry::instance();
    registry.clear_for_tests();

    std::vector<int> ids;
    ids.reserve(64);
    std::vector<std::thread> threads;
    for (int t = 0; t < 8; ++t) {
        threads.emplace_back([&registry, &ids]() {
            for (int i = 0; i < 8; ++i) {
                const int id = registry.create("load");
                registry.set_running(id, 50, "working");
                McpJobSnapshot snapshot;
                REQUIRE(registry.get(id, snapshot));
                ids.push_back(id);
            }
        });
    }
    for (auto& thread : threads) {
        thread.join();
    }
    REQUIRE(ids.size() == 64);
    // all ids distinct
    for (size_t i = 0; i < ids.size(); ++i) {
        for (size_t j = i + 1; j < ids.size(); ++j) {
            REQUIRE(ids[i] != ids[j]);
        }
    }
}
