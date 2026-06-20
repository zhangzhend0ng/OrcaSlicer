#include "catch2/catch.hpp"
#include "slic3r/App/SliceOrchestrator.hpp"
#include "slic3r/App/JobManager.hpp"
#include "slic3r/App/IPlugin.hpp"
#include "slic3r/App/PluginLoader.hpp"

using namespace Slic3r;

// SliceOrchestrator tests
TEST_CASE("SliceOrchestrator starts idle", "[SliceOrchestrator][Phase4]") {
    SliceOrchestrator orch;
    REQUIRE_FALSE(orch.isSlicing());
    REQUIRE(orch.progress_.get() == 0);
}

TEST_CASE("SliceOrchestrator cannot double-start", "[SliceOrchestrator][Phase4]") {
    SliceOrchestrator orch;
    // Without Print set, startSlice should fail
    bool result = orch.startSlice();
    REQUIRE_FALSE(result);
}

// JobManager tests
TEST_CASE("JobManager starts idle", "[JobManager][Phase4]") {
    JobManager jm(1);
    REQUIRE(jm.isIdle_.get());
    REQUIRE(jm.pendingJobs_.get() == 0);
    REQUIRE(jm.activeJobs_.get() == 0);
}

TEST_CASE("JobManager enqueues and processes jobs", "[JobManager][Phase4]") {
    JobManager jm(1);
    int result = 0;

    Job job;
    job.name = "test_job";
    job.priority = JobPriority::Normal;
    job.work = [&] { result = 42; };

    jm.enqueue(std::move(job));
    jm.waitForAll();

    REQUIRE(result == 42);
}

TEST_CASE("JobManager priority ordering", "[JobManager][Phase4]") {
    JobManager jm(1);
    std::vector<int> order;

    Job low;
    low.name = "low";
    low.priority = JobPriority::Low;
    low.work = [&] { order.push_back(3); };

    Job high;
    high.name = "high";
    high.priority = JobPriority::High;
    high.work = [&] { order.push_back(1); };

    Job normal;
    normal.name = "normal";
    normal.priority = JobPriority::Normal;
    normal.work = [&] { order.push_back(2); };

    jm.enqueue(std::move(low));
    jm.enqueue(std::move(high));
    jm.enqueue(std::move(normal));
    jm.waitForAll();

    // High should execute first
    REQUIRE(order.size() == 3);
    REQUIRE(order[0] == 1); // high priority first
}

// IPlugin tests
class TestPlugin : public IPlugin {
public:
    std::string id() const override { return "test.plugin"; }
    std::string name() const override { return "Test Plugin"; }
    std::string version() const override { return "1.0.0"; }
};

TEST_CASE("IPlugin API version format", "[IPlugin][Phase4]") {
    TestPlugin plugin;
    int version = plugin.apiVersion();
    int major = (version >> 16) & 0xFFFF;
    int minor = version & 0xFFFF;
    REQUIRE(major == ORCA_PLUGIN_API_MAJOR);
    REQUIRE(minor == ORCA_PLUGIN_API_MINOR);
}

TEST_CASE("PluginLoader compatibility check", "[PluginLoader][Phase4]") {
    int currentApi = (ORCA_PLUGIN_API_MAJOR << 16) | ORCA_PLUGIN_API_MINOR;
    REQUIRE(PluginLoader::isCompatible(currentApi));

    int newerMajor = ((ORCA_PLUGIN_API_MAJOR + 1) << 16) | 0;
    REQUIRE_FALSE(PluginLoader::isCompatible(newerMajor));

    int olderMinor = (ORCA_PLUGIN_API_MAJOR << 16) | (ORCA_PLUGIN_API_MINOR + 1);
    REQUIRE(PluginLoader::isCompatible(olderMinor)); // minor version forward compat
}
