#include <catch2/catch_test_macros.hpp>

#include "slic3r/Utils/ConnectionProcessManager.hpp"

#include <boost/filesystem.hpp>

#include <atomic>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <string>
#include <string_view>
#include <vector>

using namespace Slic3r::Gateway;

namespace {

// Each lock test writes its own lock file into a unique throwaway directory; the guard removes
// the directory when the test finishes so repeated runs never share state.
struct TempDirGuard
{
    boost::filesystem::path path;

    TempDirGuard()
    {
        static std::atomic<unsigned> counter{0};
        const auto                   stamp = std::chrono::steady_clock::now().time_since_epoch().count();
        path = boost::filesystem::temp_directory_path() / ("sm-cli-lock-test-" + std::to_string(stamp) + "-" + std::to_string(counter++));
        boost::filesystem::create_directories(path);
    }

    ~TempDirGuard()
    {
        boost::system::error_code error;
        boost::filesystem::remove_all(path, error);
    }
};

void write_lock_file(const boost::filesystem::path& file, std::string_view content)
{
    std::ofstream stream{file.string(), std::ios::binary | std::ios::trunc};
    stream.write(content.data(), static_cast<std::streamsize>(content.size()));
}

} // namespace

TEST_CASE("ConnectionProcessManager builds the Orca launch arguments", "[gateway][process]")
{
    const std::vector<std::string> arguments = ConnectionProcessManager::build_arguments("zh-CN");
    REQUIRE(arguments == std::vector<std::string>{"--locale=zh-CN", "--orca"});
}

TEST_CASE("ConnectionProcessManager selects the platform-specific CLI executable", "[gateway][process]")
{
#if defined(_WIN32)
#if defined(_M_X64) || defined(__x86_64__)
    constexpr std::string_view expected = "snapmaker_control_windows_x64.exe";
#elif defined(_M_ARM64) || defined(__aarch64__)
    constexpr std::string_view expected = "snapmaker_control_windows_arm64.exe";
#else
#error "unsupported Windows architecture for the snapmaker_control CLI"
#endif
#elif defined(__APPLE__)
#if defined(__x86_64__)
    constexpr std::string_view expected = "snapmaker_control_macos_x64";
#elif defined(__arm64__) || defined(__aarch64__)
    constexpr std::string_view expected = "snapmaker_control_macos_arm64";
#else
#error "unsupported macOS architecture for the snapmaker_control CLI"
#endif
#elif defined(__linux__)
#if defined(__x86_64__)
    constexpr std::string_view expected = "snapmaker_control_linux_x64";
#elif defined(__aarch64__) || defined(__arm64__)
    constexpr std::string_view expected = "snapmaker_control_linux_arm64";
#else
#error "unsupported Linux architecture for the snapmaker_control CLI"
#endif
#else
#error "unsupported platform for the snapmaker_control CLI"
#endif

    REQUIRE(ConnectionProcessManager::cli_executable_name() == expected);
}

TEST_CASE("ConnectionProcessManager parses one PORT frame after noise", "[gateway][process]")
{
    std::uint16_t     port   = 0;
    const std::string output = "starting dart cli\r\nloading locale\r\nPORT:8888\r\n\r\n";
    REQUIRE(ConnectionProcessManager::parse_port_frame(output, port) == ProcessDiscoveryError::None);
    REQUIRE(port == 8888);
}

TEST_CASE("ConnectionProcessManager rejects malformed and duplicate PORT frames", "[gateway][process]")
{
    std::uint16_t port = 0;
    REQUIRE(ConnectionProcessManager::parse_port_frame("PORT:88\r\n", port) == ProcessDiscoveryError::InvalidPortFrame);
    REQUIRE(ConnectionProcessManager::parse_port_frame("PORT:0\r\n\r\n", port) == ProcessDiscoveryError::InvalidPortFrame);
    REQUIRE(ConnectionProcessManager::parse_port_frame("PORT:70000\r\n\r\n", port) == ProcessDiscoveryError::InvalidPortFrame);
    REQUIRE(ConnectionProcessManager::parse_port_frame("PORT:8888\r\n\r\nPORT:8889\r\n\r\n", port) ==
            ProcessDiscoveryError::MultiplePortFrames);
}

TEST_CASE("ConnectionProcessManager uses the injected process runner", "[gateway][process]")
{
    ConnectionProcessManager::Config config;
    config.executable = boost::filesystem::path{"snapmaker_connection.exe"};

    std::vector<std::string> seen_arguments;
    ConnectionProcessManager manager(config, [&](const std::vector<std::string>& arguments) {
        seen_arguments = arguments;
        ConnectionProcessManager::ProcessRunResult result;
        result.stdout_data = "PORT:8080\r\n\r\n";
        return result;
    });

    const auto result = manager.discover_port("en-US");
    REQUIRE(result.error == ProcessDiscoveryError::None);
    REQUIRE(result.port == 8080);
    REQUIRE(seen_arguments == std::vector<std::string>{"--locale=en-US", "--orca"});
}

TEST_CASE("ConnectionProcessManager terminate is a no-op without a tracked child", "[gateway][process]")
{
    ConnectionProcessManager::Config config;
    config.executable = boost::filesystem::path{"snapmaker_connection.exe"};

    ConnectionProcessManager manager(config, [](const std::vector<std::string>&) {
        ConnectionProcessManager::ProcessRunResult result;
        result.stdout_data = "PORT:8080\r\n\r\n";
        return result;
    });

    REQUIRE(manager.discover_port("en-US").error == ProcessDiscoveryError::None);
    // Injected runners bypass the real child tracking, so terminate() must stay safe.
    manager.terminate();
    manager.terminate();
}

TEST_CASE("owner_pid_from_lock accepts a serving Orca lock for the matching port", "[gateway][process]")
{
    TempDirGuard                  temp;
    const boost::filesystem::path lock = temp.path / "snapmaker_control.lock";

    SECTION("returns the recorded pid for a valid lock")
    {
        write_lock_file(lock, R"({"pid": 4242, "port": 30996, "mode": "orca", "state": "serving"})");
        const auto pid = ConnectionProcessManager::owner_pid_from_lock(lock, 30996);
        REQUIRE(pid.has_value());
        REQUIRE(*pid == 4242u);
    }

    SECTION("ignores extra fields and keeps the maximum representable pid")
    {
        // INT_MAX stays inside pid_t range on every supported platform.
        write_lock_file(lock, R"({"pid": 2147483647, "port": 30996, "mode": "orca", "state": "serving", "started": "2026-11-05"})");
        const auto pid = ConnectionProcessManager::owner_pid_from_lock(lock, 30996);
        REQUIRE(pid.has_value());
        REQUIRE(*pid == 2147483647u);
    }

    SECTION("rejects a lock that records a different port")
    {
        write_lock_file(lock, R"({"pid": 4242, "port": 30997, "mode": "orca", "state": "serving"})");
        REQUIRE_FALSE(ConnectionProcessManager::owner_pid_from_lock(lock, 30996).has_value());
    }
}

TEST_CASE("owner_pid_from_lock rejects unusable lock content", "[gateway][process]")
{
    TempDirGuard                  temp;
    const boost::filesystem::path lock = temp.path / "snapmaker_control.lock";

    SECTION("missing file") { REQUIRE_FALSE(ConnectionProcessManager::owner_pid_from_lock(lock, 30996).has_value()); }

    SECTION("empty file")
    {
        write_lock_file(lock, "");
        REQUIRE_FALSE(ConnectionProcessManager::owner_pid_from_lock(lock, 30996).has_value());
    }

    SECTION("file above the 64 KiB size cap")
    {
        write_lock_file(lock, std::string(64 * 1024 + 1, 'x'));
        REQUIRE_FALSE(ConnectionProcessManager::owner_pid_from_lock(lock, 30996).has_value());
    }

    SECTION("malformed JSON")
    {
        write_lock_file(lock, R"({"pid": 4242, "port": 30996,)");
        REQUIRE_FALSE(ConnectionProcessManager::owner_pid_from_lock(lock, 30996).has_value());
    }

    SECTION("non-object JSON payload")
    {
        write_lock_file(lock, R"([{"pid": 4242}] )");
        REQUIRE_FALSE(ConnectionProcessManager::owner_pid_from_lock(lock, 30996).has_value());
    }

    SECTION("pid field wrong type or out of range")
    {
        write_lock_file(lock, R"({"pid": "4242", "port": 30996, "mode": "orca", "state": "serving"})");
        REQUIRE_FALSE(ConnectionProcessManager::owner_pid_from_lock(lock, 30996).has_value());

        write_lock_file(lock, R"({"pid": -1, "port": 30996, "mode": "orca", "state": "serving"})");
        REQUIRE_FALSE(ConnectionProcessManager::owner_pid_from_lock(lock, 30996).has_value());

        write_lock_file(lock, R"({"pid": 0, "port": 30996, "mode": "orca", "state": "serving"})");
        REQUIRE_FALSE(ConnectionProcessManager::owner_pid_from_lock(lock, 30996).has_value());

        write_lock_file(lock, R"({"pid": 4242.5, "port": 30996, "mode": "orca", "state": "serving"})");
        REQUIRE_FALSE(ConnectionProcessManager::owner_pid_from_lock(lock, 30996).has_value());

        // Above pid_t range on every supported platform.
        write_lock_file(lock, R"({"pid": 4294967296, "port": 30996, "mode": "orca", "state": "serving"})");
        REQUIRE_FALSE(ConnectionProcessManager::owner_pid_from_lock(lock, 30996).has_value());

        write_lock_file(lock, R"({"port": 30996, "mode": "orca", "state": "serving"})");
        REQUIRE_FALSE(ConnectionProcessManager::owner_pid_from_lock(lock, 30996).has_value());
    }

    SECTION("port field wrong type")
    {
        write_lock_file(lock, R"({"pid": 4242, "port": "30996", "mode": "orca", "state": "serving"})");
        REQUIRE_FALSE(ConnectionProcessManager::owner_pid_from_lock(lock, 30996).has_value());
    }

    SECTION("mode is not orca")
    {
        write_lock_file(lock, R"({"pid": 4242, "port": 30996, "mode": "app", "state": "serving"})");
        REQUIRE_FALSE(ConnectionProcessManager::owner_pid_from_lock(lock, 30996).has_value());

        write_lock_file(lock, R"({"pid": 4242, "port": 30996, "state": "serving"})");
        REQUIRE_FALSE(ConnectionProcessManager::owner_pid_from_lock(lock, 30996).has_value());
    }

    SECTION("state is not serving")
    {
        write_lock_file(lock, R"({"pid": 4242, "port": 30996, "mode": "orca", "state": "starting"})");
        REQUIRE_FALSE(ConnectionProcessManager::owner_pid_from_lock(lock, 30996).has_value());

        write_lock_file(lock, R"({"pid": 4242, "port": 30996, "mode": "orca"})");
        REQUIRE_FALSE(ConnectionProcessManager::owner_pid_from_lock(lock, 30996).has_value());
    }
}

TEST_CASE("owner_pid_from_lock accepts any port when queried with zero", "[gateway][process]")
{
    TempDirGuard                  temp;
    const boost::filesystem::path lock = temp.path / "snapmaker_control.lock";

    SECTION("zero port matches a lock recorded for a different port")
    {
        write_lock_file(lock, R"({"pid": 4242, "port": 30996, "mode": "orca", "state": "serving"})");
        const auto pid = ConnectionProcessManager::owner_pid_from_lock(lock, 0);
        REQUIRE(pid.has_value());
        REQUIRE(*pid == 4242u);
    }

    SECTION("zero port still rejects invalid lock content")
    {
        write_lock_file(lock, R"({"pid": 4242, "port": 30996, "mode": "orca", "state": "starting"})");
        REQUIRE_FALSE(ConnectionProcessManager::owner_pid_from_lock(lock, 0).has_value());
    }
}

#if defined(__APPLE__) || defined(__linux__)

#include <cerrno>
#include <signal.h>
#include <unistd.h>

namespace {
std::uint64_t dead_test_pid()
{
    for (std::uint64_t candidate = 40001; candidate < 40100; ++candidate)
        if (::kill(static_cast<pid_t>(candidate), 0) != 0 && errno == ESRCH)
            return candidate;
    return 1; // init always exists; keeps the live-owner branch meaningful even here.
}
} // namespace

TEST_CASE("remove_stale_lock only clears locks of exited owners", "[gateway][process]")
{
    TempDirGuard                  temp;
    const boost::filesystem::path lock = temp.path / "snapmaker_control.lock";

    SECTION("missing file removes nothing") { REQUIRE_FALSE(ConnectionProcessManager::remove_stale_lock(lock, 0, std::nullopt)); }

    SECTION("dead owner is cleared, with and without a port constraint")
    {
        const std::uint64_t dead = dead_test_pid();
        write_lock_file(lock, R"({"pid": )" + std::to_string(dead) + R"(, "port": 30996, "mode": "orca", "state": "serving"})");
        REQUIRE(ConnectionProcessManager::remove_stale_lock(lock, 0, std::nullopt));
        REQUIRE_FALSE(boost::filesystem::exists(lock));

        write_lock_file(lock, R"({"pid": )" + std::to_string(dead) + R"(, "port": 30996, "mode": "orca", "state": "serving"})");
        REQUIRE(ConnectionProcessManager::remove_stale_lock(lock, 30996, dead));
        REQUIRE_FALSE(boost::filesystem::exists(lock));
    }

    SECTION("live owner is never cleared")
    {
        const std::uint64_t self = static_cast<std::uint64_t>(::getpid());
        write_lock_file(lock, R"({"pid": )" + std::to_string(self) + R"(, "port": 30996, "mode": "orca", "state": "serving"})");
        REQUIRE_FALSE(ConnectionProcessManager::remove_stale_lock(lock, 0, std::nullopt));
        REQUIRE(boost::filesystem::exists(lock));
    }

    SECTION("recorded pid different from the expected pid keeps the lock")
    {
        const std::uint64_t dead = dead_test_pid();
        write_lock_file(lock, R"({"pid": )" + std::to_string(dead) + R"(, "port": 30996, "mode": "orca", "state": "serving"})");
        // Another host replaced the owner between reads: the expected pid no longer matches.
        REQUIRE_FALSE(ConnectionProcessManager::remove_stale_lock(lock, 0, dead + 1));
        REQUIRE(boost::filesystem::exists(lock));
    }

    SECTION("port mismatch with a non-zero port keeps the lock")
    {
        const std::uint64_t dead = dead_test_pid();
        write_lock_file(lock, R"({"pid": )" + std::to_string(dead) + R"(, "port": 30996, "mode": "orca", "state": "serving"})");
        REQUIRE_FALSE(ConnectionProcessManager::remove_stale_lock(lock, 30997, std::nullopt));
        REQUIRE(boost::filesystem::exists(lock));
    }
}

#endif // defined(__APPLE__) || defined(__linux__)
