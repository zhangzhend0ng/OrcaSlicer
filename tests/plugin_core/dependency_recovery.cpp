// Isolated process regression for the actual dependency installer and startup.
// The private macOS build injects a process exit immediately after the real
// rename succeeds. Production code and filesystem calls are otherwise unchanged.
#include "slic3r/plugin/PluginManager.hpp"
#include "slic3r/plugin/PluginDependencyInstaller.hpp"
#include "slic3r/plugin/PythonInterpreter.hpp"
#include "libslic3r/Utils.hpp"
#include <boost/log/core.hpp>
#include <boost/nowide/args.hpp>
#include <boost/nowide/filesystem.hpp>
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>
#ifdef __APPLE__
#include <unistd.h>
#endif

namespace fs = std::filesystem;
using namespace Slic3r;
using json = nlohmann::json;
namespace {
std::string crash_source, crash_destination;
bool crash_after_publish = false;
fs::path crash_record;
void save(const fs::path& path, const json& value)
{
    std::ofstream stream(path);
    if (!stream) throw std::runtime_error("Cannot write dependency regression result");
    stream << value.dump(2) << '\n';
}
void require(bool value, const std::string& message)
{
    if (!value) throw std::runtime_error(message);
}
std::vector<std::string> files(const fs::path& root)
{
    std::vector<std::string> result;
    if (fs::is_directory(root))
        for (const auto& entry : fs::recursive_directory_iterator(root))
            if (entry.is_regular_file()) result.push_back(entry.path().lexically_relative(root).u8string());
    std::sort(result.begin(), result.end());
    return result;
}
bool import_old_dependency(std::string& message)
{
    try {
        PythonGILState gil;
        require(bool(gil), "No GIL for dependency import");
        const auto module = pybind11::module_::import("contract_dep");
        return module.attr("VALUE").cast<std::string>() == "1.0.0";
    } catch (const std::exception& ex) {
        message = ex.what();
        return false;
    }
}
} // namespace

int main(int argc, char** argv)
{
    boost::nowide::args utf8_args(argc, argv);
    boost::nowide::nowide_filesystem();
    if (argc != 5) return 2;
    const std::string mode = argv[1];
    const fs::path wheelhouse = fs::u8path(argv[2]);
    const fs::path profile = fs::u8path(argv[3]);
    const fs::path report = fs::u8path(argv[4]);
    fs::create_directories(profile);
    set_data_dir(profile.u8string());
    boost::log::core::get()->set_logging_enabled(false);
    auto& manager = PluginManager::instance();
    json result = {{"mode", mode}, {"passed", false}};
    int status = 1;
    try {
        const fs::path target = fs::u8path(PythonInterpreter::shared_packages_dir());
        const fs::path previous = target.parent_path() / ("." + target.filename().u8string() + ".previous");
        result["before_initialize"] = {{"target_exists", fs::exists(target)}, {"previous_exists", fs::exists(previous)},
                                       {"target_files", files(target)}, {"previous_files", files(previous)}};
        const bool initialized = manager.initialize();
        result["initialized"] = initialized;
        result["initialization_error"] = PythonInterpreter::instance().last_error();
        if (mode == "blocked-recovery") {
            result["backup_retained"] = fs::is_regular_file(previous / "contract_dep/__init__.py");
            result["obstruction_retained"] = fs::is_regular_file(target);
            require(!initialized, "Invalid recovery target did not prevent interpreter startup");
            require(result["backup_retained"] && result["obstruction_retained"], "Recovery error destroyed files");
        } else {
            require(initialized, "Manager startup: " + PythonInterpreter::instance().last_error());
            std::string error;
            if (mode == "seed-crash" || mode == "published-crash") {
                require(plugin_loader::configure_dependency_install({true, wheelhouse.u8string()}, error), error);
                require(plugin_loader::install_packages_transactionally({"contract-dep==1.0.0"}, error), "Seed actual uv install: " + error);
                require(fs::is_regular_file(target / "contract_dep/__init__.py"), "Seed package missing");
                save(report.parent_path() / "seed-install.json", {{"files", files(target)}, {"actual_uv_install", true}});
#ifdef __APPLE__
                crash_record = report;
                if (mode == "seed-crash") {
                    crash_source = target.string();
                    crash_destination = previous.string();
                } else {
                    crash_source = (target.parent_path() / ("." + target.filename().u8string() + ".staging-")).string();
                    crash_destination = target.string();
                    crash_after_publish = true;
                }
                ::setenv("ORCA_DEP_TEST_SOURCE", crash_source.c_str(), 1);
                ::setenv("ORCA_DEP_TEST_DESTINATION", crash_destination.c_str(), 1);
                ::setenv("ORCA_DEP_TEST_RECORD", crash_record.c_str(), 1);
                ::setenv("ORCA_DEP_TEST_PREFIX", crash_after_publish ? "1" : "0", 1);
                plugin_loader::install_packages_transactionally({"recovery-new-dep==1.0.0"}, error);
                throw std::runtime_error("Production dependency publish did not reach the injected real rename");
#else
                throw std::runtime_error("Real rename crash injection requires this macOS regression runner");
#endif
            } else if (mode == "resume" || mode == "resume-empty" || mode == "resume-published") {
                result["after_initialize"] = {{"target_files", files(target)}, {"previous_exists", fs::exists(previous)}};
                std::string import_error;
                result["import_before_install"] = import_old_dependency(import_error);
                result["import_error"] = import_error;
                result["old_files_before_install"] = fs::is_regular_file(target / "contract_dep/__init__.py");
                // A fresh empty wheelhouse proves recovery never relies on downloads/cache.
                const auto empty = report.parent_path() / "empty-wheelhouse";
                fs::create_directories(empty);
                require(plugin_loader::configure_dependency_install({true, empty.u8string()}, error), error);
                result["missing_install_rejected"] = !plugin_loader::install_packages_transactionally({"missing-recovery-contract==1.0.0"}, error);
                result["missing_install_error"] = error;
                result["after_failed_install"] = {{"target_files", files(target)}, {"previous_exists", fs::exists(previous)}};
                result["old_files_after_install"] = fs::is_regular_file(target / "contract_dep/__init__.py");
                require(result["import_before_install"].get<bool>(), "Startup lost the existing dependency before any new install");
                require(result["missing_install_rejected"] && result["old_files_after_install"], "Failed offline install destroyed restored dependency");
                require(!fs::exists(previous), "Recovery left an unresolved previous backup");
                if (mode == "resume-published") {
                    require(fs::is_regular_file(target / "recovery_new_dep/__init__.py"), "Recovery rolled back an already published dependency");
                    PythonGILState gil;
                    require(pybind11::module_::import("recovery_new_dep").attr("VALUE").cast<std::string>() == "new", "Published dependency cannot import");
                } else {
                    require(!fs::exists(target / "recovery_new_dep"), "Incomplete candidate was activated during rollback recovery");
                }
            } else throw std::runtime_error("Unknown regression mode");
        }
        result["passed"] = true;
        status = 0;
    } catch (const std::exception& error) {
        result["error"] = error.what();
    }
    manager.shutdown();
    PythonInterpreter::instance().shutdown();
    result["interpreter_stopped"] = !PythonInterpreter::instance().is_initialized();
    save(report, result);
    std::cout << (status ? "FAIL " : "PASS ") << mode << " " << result.value("error", "") << '\n';
    return status;
}
