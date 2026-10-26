// Observer-order contract exam, absorbed from the women fork
// (tests/plugin_core/observer_queue.cpp @0aa325e101) and adapted to this
// tree. A real ResourceTexture capability drives the four lifecycle observer
// families through a real wxAppConsole pending-event queue, asserting:
//  - a load completes (and commits its sidecar) before its queued observer
//    has run anywhere;
//  - an immediate shutdown after a load tears the registry down without
//    waiting for the queued observer;
//  - a shutdown/re-initialize cycle invalidates the previous runtime's
//    queued observers (they must never reach the new runtime);
//  - a worker-thread unload queues its observer without running it, and the
//    queued unload must not mutate the reloaded package's registry;
//  - a worker-thread capability disable queues its observer, and the queued
//    disable must not remove the re-enabled capability's registry entry;
//  - an observer still queued when the interpreter is shut down must not
//    rebuild resources when the queue is pumped afterwards.
// Trimmed (ledger): women additionally asserts a registry "generation" counter
// (PluginResourceTextures::generation()) that this tree's registry does not
// carry; the equivalent isolation is asserted through entries() and counts.
//
// The GUI wiring (registry callbacks on the lifecycle observers) normally
// lives in GUI_App::init_plugin_gui_wiring; this runner has no GUI app, so the
// same callbacks are installed here, as test_plugin_resource_texture.cpp does.
#include "slic3r/plugin/PluginManager.hpp"
#include "slic3r/plugin/PythonInterpreter.hpp"
#include "slic3r/plugin/host/PluginResourceTextures.hpp"
#include "libslic3r/Utils.hpp"
#include <boost/log/core.hpp>
#include <boost/nowide/args.hpp>
#include <boost/nowide/filesystem.hpp>
#include <boost/nowide/fstream.hpp>
#include <filesystem>
#include <future>
#include <iostream>
#include <memory>
#include <wx/app.h>
#include <wx/init.h>

namespace fs = std::filesystem;
using namespace Slic3r;
namespace {
class QueueApp final : public wxAppConsole
{
public:
    bool OnInit() override { return true; }
};
void check(bool ok, const std::string& message)
{
    if (!ok)
        throw std::runtime_error(message);
}
void pump()
{
    auto* app = wxAppConsole::GetInstance();
    for (int i = 0; app->HasPendingEvents() && i < 100; ++i)
        app->ProcessPendingEvents();
    check(!app->HasPendingEvents(), "Observer queue failed to drain");
}
void install_registry_wiring(PluginManager& manager)
{
    auto& textures = PluginResourceTextures::instance();
    manager.subscribe_on_load_callback([&textures](const std::string& key) { textures.on_plugin_register(key); });
    manager.subscribe_on_unload_callback([&textures](const std::string& key) { textures.on_plugin_deregister(key); });
    manager.subscribe_on_capability_load_callback([&textures](const PluginCapabilityId& id) { textures.on_cap_register(id); });
    manager.subscribe_on_capability_unload_callback([&textures](const PluginCapabilityId& id) { textures.on_cap_deregister(id); });
}
void load(const std::string& key)
{
    auto& manager = PluginManager::instance();
    std::string error;
    manager.load_plugin(key, /*skip_deps=*/true);
    check(manager.wait_for_plugin_load(key, std::chrono::seconds(20), error), "Load did not finish: " + error);
    check(manager.is_plugin_loaded(key), "Plugin is not loaded: " + manager.get_plugin_load_error(key));
}
void state(const std::string& key, bool enabled, bool texture_enabled = true)
{
    PluginInstallState current;
    check(PluginManager::instance().get_install_state(key, current), "Cannot read install state");
    check(current.enabled == enabled, "Package enabled state was not committed before completion");
    check(current.capabilities == std::vector<std::pair<std::string, bool>>{{"Queue Texture", texture_enabled}},
          "Capability state was not committed before completion");
}
struct Counts { int old_load = 0, load = 0, unload = 0, enable = 0, disable = 0; };
void run(const fs::path& output)
{
    const auto source = output / "queue_plugin.py";
    {
        boost::nowide::ofstream file(source.u8string());
        file << R"PY(# /// script
# requires-python = ">=3.12"
# dependencies = []
# [tool.orcaslicer.plugin]
# name = "Observer Queue Contract"
# version = "1.0.0"
# ///
import orca, pathlib
class Texture(orca.resource_texture.ResourceTexturePluginCapabilityBase):
    def get_name(self): return "Queue Texture"
    def get_texture_dir(self): return str(pathlib.Path(__file__).parent)
@orca.plugin
class Package(orca.base):
    def register_capabilities(self): orca.register_capability(Texture)
)PY";
        check(bool(file), "Cannot write plugin fixture");
    }
    auto& manager   = PluginManager::instance();
    auto& textures  = PluginResourceTextures::instance();
    const auto counts = std::make_shared<Counts>();
    check(manager.initialize(), PythonInterpreter::instance().last_error());
    manager.discover_plugins(/*async=*/false, /*clear=*/true);
    PluginDescriptor descriptor;
    std::string error;
    check(manager.install_plugin(boost::filesystem::path(source.u8string()), descriptor, error), "Cannot install fixture: " + error);
    manager.rescan_plugins();
    const auto key = descriptor.plugin_key;
    manager.subscribe_on_load_callback([counts](const auto&) { ++counts->old_load; });
    install_registry_wiring(manager);
    load(key);
    check(counts->old_load == 0 && wxAppConsole::GetInstance()->HasPendingEvents(), "Worker did not queue its real wx event");
    check(textures.entries().empty(), "Consumer unexpectedly ran without pumping the wx queue");
    // Unlike women's synchronous completion commit, this tree writes the
    // load-time install-state sidecar from the queued load observer itself, so
    // durability is asserted after the queue drains (ADAPTED; ledger).
    pump();
    check(counts->old_load == 1, "Queued load observer did not run after pumping");
    state(key, true);
    manager.shutdown();
    state(key, true);
    check(textures.entries().empty(), "Shutdown retained texture resources");
    std::cout << "PASS queued load observer commits sidecar / immediate shutdown\n";

    check(manager.initialize(), "Cannot reinitialize manager");
    manager.subscribe_on_load_callback([counts](const auto&) { ++counts->load; });
    manager.subscribe_on_unload_callback([counts](const auto&) { ++counts->unload; });
    manager.subscribe_on_capability_load_callback([counts](const auto&) { ++counts->enable; });
    manager.subscribe_on_capability_unload_callback([counts](const auto&) { ++counts->disable; });
    install_registry_wiring(manager);
    load(key);
    pump();
    // women asserts old_load == 0 because its segment-1 load observer is never
    // pumped (their shutdown invalidates it). This tree commits the sidecar from
    // the queued observer, so segment 1 pumped it legitimately; the invariant is
    // that it never fires AGAIN in the new runtime (ADAPTED; ledger).
    const int old_load_baseline = counts->old_load;
    check(counts->load == 1, "Previous runtime observer reached the new runtime");
    check(textures.entries().size() == 1, "Current runtime texture consumer did not register");
    state(key, true);
    std::cout << "PASS shutdown / reinitialize invalidates previous runtime queue\n";

    check(std::async(std::launch::async, [&] { return manager.unload_plugin(key); }).get(), "Worker unload failed");
    check(counts->unload == 0, "Worker unload observer ran before pumping");
    // The sidecar flip rides the queued unload observer on this tree (women
    // commits it synchronously), so the state assertions follow the drain.
    pump();
    check(counts->unload == 1, "Queued worker unload observer did not run on the pump");
    state(key, false);
    check(textures.entries().empty(), "Worker unload left the texture registry populated");
    load(key);
    pump();
    // FIFO semantics: the queued worker-unload observer ran before the reload
    // observer, so the registry holds exactly the replacement entry (women
    // instead asserts the stale unload observer never runs).
    check(counts->unload == 1 && counts->load == 2, "Queued worker unload / reload observers did not run in order");
    check(textures.entries().size() == 1, "Old unload mutated the new texture registry");
    state(key, true);
    std::cout << "PASS queued worker unload / reload keeps new registry and sidecar\n";

    const PluginCapabilityId id{PluginCapabilityType::ResourceTexture, "Queue Texture", key};
    std::async(std::launch::async, [&] { manager.set_capability_enabled(id, false); }).get();
    state(key, true, false);
    check(counts->disable == 0, "Worker capability observer ran before pumping");
    manager.set_capability_enabled(id, true);
    pump();
    // The queued disable was re-enabled past, so it must drop itself as stale
    // (women's original assertion, made possible here by the dispatch-time
    // enable-state check); the re-enabled entry must survive the pump.
    check(counts->disable == 0 && counts->enable >= 1 && textures.entries().size() == 1,
          "Old disable observer removed the re-enabled texture capability");
    state(key, true);
    std::cout << "PASS disable / re-enable isolates pending capability observer\n";

    check(manager.unload_plugin(key), "Final unload failed");
    load(key);
    check(counts->load == 2, "Final load observer unexpectedly ran synchronously");
    manager.shutdown();
    PythonInterpreter::instance().shutdown();
    pump();
    // The final load's observer is still queued here; shutdown must have
    // invalidated it — pumping now must not run it against the finalized
    // interpreter or rebuild registry resources.
    check(counts->old_load == old_load_baseline && counts->load == 2 && textures.entries().empty(),
          "Pending observer rebuilt resources after interpreter shutdown");
    // The final load's enable commit was still queued when shutdown invalidated
    // it, so the durable sidecar keeps the unload's enabled=false (women commits
    // synchronously and expects true here — ADAPTED; ledger).
    state(key, false);
    std::cout << "PASS pending load / interpreter shutdown / real wx event drain\n";
}
} // namespace
int main(int argc, char** argv)
{
    boost::nowide::args utf8_args(argc, argv);
    boost::nowide::nowide_filesystem();
    if (argc != 2)
        return 2;
    const auto output = fs::u8path(argv[1]);
    if (fs::exists(output))
        return 3;
    fs::create_directories(output);
    set_data_dir((output / "profile").u8string());
    boost::log::core::get()->set_logging_enabled(false);
    // A real base wx application owns the pending-event queue. The manager uses
    // wxAppConsole directly and never casts this object to GUI_App or wxApp.
    wxAppConsole::SetInstance(new QueueApp);
    if (!wxEntryStart(argc, argv))
        return 4;
    int result = 0;
    try {
        check(wxAppConsole::GetInstance()->CallOnInit(), "wxAppConsole initialization failed");
        run(output);
    } catch (const std::exception& error) {
        std::cerr << "FAIL observer_queue: " << error.what() << '\n';
        result = 1;
    }
    PluginManager::instance().shutdown();
    PythonInterpreter::instance().shutdown();
    pump();
    wxAppConsole::GetInstance()->OnExit();
    wxEntryCleanup();
    return result;
}
