#include "libslic3r/Utils.hpp"
#include "slic3r/plugin/PluginManager.hpp"
#include "slic3r/plugin/PythonInterpreter.hpp"
#include <boost/log/core.hpp>
#include <boost/nowide/args.hpp>
#include <boost/nowide/filesystem.hpp>
#include <filesystem>
#include <iostream>
#include <pybind11/embed.h>

// Export the very same embedded bindings as the app, without creating wxApp,
// loading plugins, or opening a real user profile.
int main(int argc, char** argv)
{
    // Match the app's UTF-8 path contract, including non-ASCII Windows argv.
    boost::nowide::args utf8_args(argc, argv);
    boost::nowide::nowide_filesystem();
    if (argc != 4)
        return 2;
    const auto profile = std::filesystem::u8path(argv[3]);
    if (std::filesystem::exists(profile))
        return 3;
    std::filesystem::create_directories(profile);
    Slic3r::set_data_dir(profile.u8string());
    boost::log::core::get()->set_logging_enabled(false);
    auto& manager = Slic3r::PluginManager::instance();
    int result = 0;
    try {
        if (!manager.initialize())
            throw std::runtime_error(Slic3r::PythonInterpreter::instance().last_error());
        {
            Slic3r::PythonGILState gil;
            auto globals = pybind11::dict();
            globals["SDK_OUTPUT"] = argv[2];
            pybind11::module_::import("runpy").attr("run_path")(argv[1], pybind11::arg("init_globals") = globals);
        }
    } catch (const std::exception& error) {
        std::cerr << "SDK export failed: " << error.what() << '\n';
        result = 1;
    }
    manager.shutdown();
    Slic3r::PythonInterpreter::instance().shutdown();
    return result;
}
