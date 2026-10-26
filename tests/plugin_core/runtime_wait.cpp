// Load-wait/observer-dispatch contract exam, absorbed from the women fork
// (tests/plugin_core/runtime_wait.cpp @0aa325e101) and adapted to this tree's
// PluginManager key-based API: the women LocalPluginRuntime wrapper (path-based
// load/unload/execute) does not exist here, so every axis is re-expressed
// against load_plugin()/wait_for_plugin_load()/launch_script_capability().
//
// Contract axes (women originals kept where the seam allows):
//  - an uninstalled package is rejected and the rejection is observable
//    through wait_for_plugin_load()/get_plugin_load_error();
//  - a failed import preserves its real error and returns only after the
//    worker released its load slot (is_plugin_load_in_progress == false);
//  - load-completion observers queue on a real wxAppConsole and only run on
//    the main thread when its pending-event queue is pumped (console mode),
//    while with no application at all they run inline on the load worker
//    (no-app mode) — the production dispatch rule in run_on_load_callbacks;
//  - a load after a failure succeeds, and unload -> reload releases its slot;
//  - the real Script capability of a loaded package actually executes;
//  - shutdown invalidates an observer that is still queued (it must not run
//    when the queue is pumped afterwards) and stops the interpreter.
// Dropped axis (ledger): women holds the GIL across Runtime::load and asserts
// the native wait releases it — this tree's wait_for_plugin_load() has no
// caller that holds the GIL, so the axis has no reachable seam here.
#include "slic3r/plugin/PluginManager.hpp"
#include "slic3r/plugin/PythonInterpreter.hpp"
#include "libslic3r/Utils.hpp"
#include <boost/filesystem/path.hpp>
#include <boost/log/core.hpp>
#include <boost/nowide/args.hpp>
#include <boost/nowide/filesystem.hpp>
#include <filesystem>
#include <fstream>
#include <future>
#include <iostream>
#include <mutex>
#include <thread>
#include <wx/app.h>
#include <wx/init.h>

namespace fs = std::filesystem;
using namespace Slic3r;
using json = nlohmann::json;
namespace {
class QueueApp final : public wxAppConsole {
public:
    bool OnInit() override { return true; }
};
void check(bool condition, const std::string& message)
{
    if (!condition) throw std::runtime_error(message);
}
void write_json(const fs::path& file, const json& value)
{
    std::ofstream stream(file);
    stream << value.dump(2) << '\n';
    check(bool(stream), "Cannot write runtime wait report");
}
void pump()
{
    auto* app = wxAppConsole::GetInstance();
    check(app && wxIsMainThread(), "Real console queue must be pumped on its main thread");
    for (int count = 0; app->HasPendingEvents() && count < 100; ++count)
        app->ProcessPendingEvents();
    check(!app->HasPendingEvents(), "Pending observer queue did not drain");
}
fs::path fixture(const fs::path& directory, const std::string& name, bool broken)
{
    const auto file = directory / (name + ".py");
    std::ofstream stream(file);
    stream << "# /// script\n# requires-python = \">=3.12\"\n# dependencies = []\n"
              "# [tool.orcaslicer.plugin]\n# name = \"Runtime wait " << name << "\"\n# version = \"1.0.0\"\n# ///\n";
    if (broken)
        stream << "raise RuntimeError('intentional runtime-wait import failure')\n";
    else
        stream << R"PY(import orca
class Probe(orca.script.ScriptPluginCapabilityBase):
    def get_name(self): return "Runtime wait probe"
    def execute(self): return orca.ExecutionResult.success("real Script callback", "runtime-wait-payload")
@orca.plugin
class Package(orca.base):
    def register_capabilities(self): orca.register_capability(Probe)
)PY";
    check(bool(stream), "Cannot write plugin fixture");
    return file;
}
struct Observations {
    std::mutex mutex;
    int failed = 0;
    int successful = 0;
    bool all_on_main = true;
    bool nested_attempted = false;
    bool nested_loaded = false;
};
void exercise(const fs::path& output, bool console, json& report)
{
    set_data_dir((output / "profile-中文").u8string());
    auto& manager = PluginManager::instance();
    check(manager.initialize(), "Runtime initialization failed: " + PythonInterpreter::instance().last_error());
    manager.discover_plugins(/*async=*/false, /*clear=*/true);
    report["initialized"] = true;

    // Uninstalled package: the key-based equivalent of women's "Package must be
    // installed before loading" rejection, observable through the wait API.
    manager.load_plugin("not-installed", /*skip_deps=*/true);
    std::string missing_error;
    check(!manager.wait_for_plugin_load("not-installed", std::chrono::seconds(5), missing_error) && !missing_error.empty() &&
              missing_error == manager.get_plugin_load_error("not-installed"),
          "Uninstalled package was not rejected through the wait API");
    report["missing_package_rejected"] = true;

    const auto broken = fixture(output, "broken", true);
    const auto good   = fixture(output, "good", false);
    PluginDescriptor broken_descriptor, good_descriptor;
    std::string install_error;
    check(manager.install_plugin(boost::filesystem::path(broken.u8string()), broken_descriptor, install_error),
          "Broken fixture install failed: " + install_error);
    check(manager.install_plugin(boost::filesystem::path(good.u8string()), good_descriptor, install_error),
          "Good fixture install failed: " + install_error);
    manager.rescan_plugins();
    report["installed"] = true;

    const auto main_thread  = std::this_thread::get_id();
    const auto observations = std::make_shared<Observations>();
    manager.subscribe_on_load_callback([observations, main_thread, &manager, good_key = good_descriptor.plugin_key,
                                        broken_key = broken_descriptor.plugin_key](const std::string& key) {
        if (key != broken_key && key != good_key) return;
        std::lock_guard<std::mutex> lock(observations->mutex);
        observations->all_on_main &= std::this_thread::get_id() == main_thread;
        if (key == broken_key) {
            ++observations->failed;
            // No-app mode runs this observer inline on the load worker before its
            // slot is released, so manager operations initiated from an observer
            // must be safe: exercise a genuine nested load of another package.
            // (women asserts a single-slot loader REJECTS the nested load; this
            // tree's loader uses per-key slots and accepts it — ADAPTED.)
            if (wxTheApp == nullptr) {
                observations->nested_attempted = true;
                manager.load_plugin(good_key, /*skip_deps=*/true);
            }
        } else {
            ++observations->successful;
        }
    });

    // Failed import: error preserved, slot released before the wait returns.
    manager.load_plugin(broken_descriptor.plugin_key, /*skip_deps=*/true);
    std::string error;
    check(!manager.wait_for_plugin_load(broken_descriptor.plugin_key, std::chrono::seconds(20), error), "Broken plugin unexpectedly loaded");
    check(!error.empty() && error == manager.get_plugin_load_error(broken_descriptor.plugin_key),
          "Wait did not preserve the actual load error");
    check(!manager.is_plugin_loaded(broken_descriptor.plugin_key), "Failed import left the package loaded");
    report["import_failure_error"] = error;
    check(!manager.is_plugin_load_in_progress(broken_descriptor.plugin_key), "Failed load returned before releasing its worker slot");
    report["import_failure_observed"] = true;

    if (console) {
        check(observations->failed == 0 && wxAppConsole::GetInstance()->HasPendingEvents(),
              "Console load incorrectly dispatched GUI observers");
        pump();
        check(observations->failed == 1 && observations->all_on_main, "Failed-load observer did not dispatch on the main thread");
    } else {
        check(observations->failed == 1 && observations->nested_attempted,
              "No-app inline observer did not run on the load worker");
        // The nested load of the good package (started from inside the broken
        // package's observer) must complete normally once its own slot drains.
        std::string nested_error;
        check(manager.wait_for_plugin_load(good_descriptor.plugin_key, std::chrono::seconds(20), nested_error),
              "Nested observer-initiated load failed: " + nested_error);
        check(manager.is_plugin_loaded(good_descriptor.plugin_key), "Nested observer-initiated load did not finish");
        check(manager.unload_plugin(good_descriptor.plugin_key), "Nested load cleanup failed");
        observations->nested_loaded = true;
        report["nested_observer_load_accepted"] = true;
    }

    // Valid load after failure.
    error.clear();
    manager.load_plugin(good_descriptor.plugin_key, /*skip_deps=*/true);
    check(manager.wait_for_plugin_load(good_descriptor.plugin_key, std::chrono::seconds(20), error), "Valid load after failure failed: " + error);
    check(error.empty() && manager.is_plugin_loaded(good_descriptor.plugin_key) &&
              manager.get_plugin_load_error(good_descriptor.plugin_key).empty(),
          "Successful load retained a stale error/state");
    check(!manager.is_plugin_load_in_progress(good_descriptor.plugin_key), "Successful load returned before releasing its worker slot");
    report["load_after_failure"] = true;
    if (console) {
        check(observations->successful == 0 && wxAppConsole::GetInstance()->HasPendingEvents(),
              "Console load pumped its pending observer queue before the test did");
        pump();
        check(observations->successful == 1 && observations->all_on_main, "Successful observer did not run on main");
        report["observer_queued_until_main_thread_dispatch"] = true;
    } else {
        check(observations->successful >= 1, "No-app observer did not retain inline worker semantics");
    }

    // The real Script capability of the loaded package executes and reports back.
    {
        std::promise<ScriptCompletion> completion_promise;
        auto completion_future = completion_promise.get_future();
        const auto launch = manager.launch_script_capability(
            good_descriptor.plugin_key, "Runtime wait probe",
            [&completion_promise](const ScriptCompletion& completion) mutable { completion_promise.set_value(completion); });
        check(launch.launched_async, "Script capability did not launch");
        // Console mode: the completion is delivered through the wx queue, so the
        // pump below drives it; no-app mode delivers it on the runtime worker.
        for (int count = 0; completion_future.wait_for(std::chrono::milliseconds(50)) != std::future_status::ready && count < 100; ++count) {
            if (console)
                pump();
            else
                std::this_thread::sleep_for(std::chrono::milliseconds(20));
        }
        check(completion_future.wait_for(std::chrono::seconds(10)) == std::future_status::ready, "Script execution did not complete");
        const ScriptCompletion completion = completion_future.get();
        check(!completion.cancelled && completion.error.empty(), "Script execution errored: " + completion.error);
        check(completion.result.status == PluginResult::Success && completion.result.data == "runtime-wait-payload",
              "Actual Script callback did not execute");
        report["actual_script_callback"] = true;
    }

    // Unload (synchronous on this thread; its observer dispatches inline here
    // because this IS the main thread) then reload through the worker path.
    check(manager.unload_plugin(good_descriptor.plugin_key), "Unload failed");
    manager.load_plugin(good_descriptor.plugin_key, /*skip_deps=*/true);
    check(manager.wait_for_plugin_load(good_descriptor.plugin_key, std::chrono::seconds(20), error), "Load after successful unload failed: " + error);
    check(!manager.is_plugin_load_in_progress(good_descriptor.plugin_key), "Reload left a worker slot active");
    report["unload_then_reload"] = true;
    if (console) {
        // The reload's load observer is queued but not pumped yet; shutdown
        // below must invalidate it.
        check(observations->successful == 1, "Reload observer ran before main queue dispatch");
    } else {
        check(observations->successful >= 2, "No-app reload observer did not run");
    }

    manager.shutdown();
    // Unlike women's runtime wrapper, this tree's manager shutdown does not
    // finalize the interpreter — production (GUI_App) owns that step and takes
    // it right after the manager drains (ADAPTED; ledger).
    PythonInterpreter::instance().shutdown();
    check(!PythonInterpreter::instance().is_initialized(), "Runtime shutdown did not stop interpreter");
    if (console) {
        pump();
        check(observations->successful == 1 && observations->all_on_main, "Late observer ran after runtime shutdown");
        report["pending_observer_invalidated_on_shutdown"] = true;
    }
    report["interpreter_stopped"] = true;
}
} // namespace
int main(int argc, char** argv)
{
    boost::nowide::args utf8_args(argc, argv);
    boost::nowide::nowide_filesystem();
    if (argc != 3) return 2;
    const std::string mode = argv[1];
    if (mode != "no-app" && mode != "console") return 2;
    const auto output = fs::u8path(argv[2]);
    if (fs::exists(output)) return 3;
    fs::create_directories(output);
    boost::log::core::get()->set_logging_enabled(false);
    const bool console = mode == "console";
    json report{{"schema", 1}, {"mode", mode}, {"passed", false}, {"gui_tested", false}};
    int result = 0;
    bool wx_started = false;
    try {
        check(wxAppConsole::GetInstance() == nullptr, "Unexpected preexisting wx application");
        if (console) {
            wxAppConsole::SetInstance(new QueueApp);
            check(wxEntryStart(argc, argv), "wxEntryStart failed");
            wx_started = true;
            check(wxAppConsole::GetInstance()->CallOnInit(), "Console app initialization failed");
            check(dynamic_cast<wxApp*>(wxAppConsole::GetInstance()) == nullptr, "Fixture is a GUI wxApp instead of wxAppConsole");
        }
        exercise(output, console, report);
        report["passed"] = true;
    } catch (const std::exception& error) {
        report["error"] = error.what();
        result = 1;
    }
    PluginManager::instance().shutdown();
    PythonInterpreter::instance().shutdown();
    if (wx_started) {
        pump();
        wxAppConsole::GetInstance()->OnExit();
        wxEntryCleanup();
    }
    report["interpreter_stopped_at_exit"] = !PythonInterpreter::instance().is_initialized();
    write_json(output / "results.json", report);
    std::cout << (result == 0 ? "PASS " : "FAIL ") << "runtime_wait " << mode;
    if (report.contains("error")) std::cout << ": " << report["error"].get<std::string>();
    std::cout << '\n';
    return result;
}
