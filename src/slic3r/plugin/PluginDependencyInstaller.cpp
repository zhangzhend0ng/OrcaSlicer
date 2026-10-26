#include "PluginDependencyInstaller.hpp"
#include "PluginAtomicFile.hpp"
#include "PluginFileLock.hpp"
#include "PluginFsUtils.hpp"
#include "PluginManager.hpp"
#include "PythonInterpreter.hpp"
#include <boost/process.hpp>
#ifdef _WIN32
#include <boost/nowide/convert.hpp>
#include <boost/process/windows.hpp>
#endif
#include <chrono>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <regex>
#include <thread>
#include <nlohmann/json.hpp>

namespace Slic3r::plugin_loader {
namespace {
namespace fs = std::filesystem;
std::mutex install_mutex;
fs::path   policy_file() { return fs::u8path(get_orca_plugins_dir()) / ".dependency-policy.json"; }

struct InstallLock
{
    fs::path path;
    std::unique_ptr<PluginFileLock> guard;
    explicit InstallLock(const fs::path& parent) : path(parent / ".dependency-install.lock")
    {
        if (fs::is_symlink(path))
            throw std::runtime_error("Dependency lock directory must not be a symbolic link");
        fs::create_directories(path);
        guard = std::make_unique<PluginFileLock>(path / "guard");
    }
};

// Caller owns both install_mutex and the OS dependency lock. Recover before
// creating an absent target: its absence distinguishes a publish interrupted
// after target -> previous from a completed stage -> target publication.
void recover_dependency_install_locked(const fs::path& target)
{
    const auto previous = target.parent_path() / ("." + target.filename().u8string() + ".previous");
    if (fs::is_symlink(target) || fs::is_symlink(previous))
        throw std::runtime_error("Dependency transaction paths must not be symbolic links");
    if (fs::exists(target) && !fs::is_directory(target))
        throw std::runtime_error("Dependency target is not a directory; previous packages were preserved");
    if (!fs::exists(previous))
        return;
    if (!fs::is_directory(previous))
        throw std::runtime_error("Dependency backup is not a directory; recovery needs attention");
    // Older hosts could create an empty target during startup before reaching
    // recovery. No successful nonempty dependency install produces that state.
    if (fs::exists(target) && fs::is_empty(target))
        fs::remove(target);
    if (!fs::exists(target))
        fs::rename(previous, target);
    else
        fs::remove_all(previous);
}

std::string pinned_distributions(const fs::path& directory)
{
    std::string      pins;
    const std::regex name_pattern("[A-Za-z0-9][A-Za-z0-9_.-]*");
    const std::regex version_pattern("[A-Za-z0-9][A-Za-z0-9_.+!-]*");
    for (const auto& entry : fs::directory_iterator(directory)) {
        if (entry.path().extension() != ".dist-info")
            continue;
        std::ifstream metadata(entry.path() / "METADATA");
        std::string   line, name, version;
        while (std::getline(metadata, line) && !line.empty()) {
            if (!line.empty() && line.back() == '\r')
                line.pop_back();
            if (line.rfind("Name: ", 0) == 0)
                name = line.substr(6);
            if (line.rfind("Version: ", 0) == 0)
                version = line.substr(9);
        }
        if (!std::regex_match(name, name_pattern) || !std::regex_match(version, version_pattern))
            throw std::runtime_error("Cannot pin installed dependency metadata: " + entry.path().u8string());
        pins += name + "==" + version + "\n";
    }
    return pins;
}

bool run_uv(const std::string& uv, const std::vector<std::string>& args, std::string& error)
{
    namespace process = boost::process;
    process::ipstream stderr_pipe;
    process::group    group;
    // Own a copy: native_environment::erase() would mutate the host process.
#ifdef _WIN32
    process::wenvironment environment = boost::this_process::wenvironment();
    const auto executable = boost::nowide::widen(uv);
    std::vector<std::wstring> native_args;
    native_args.reserve(args.size());
    for (const auto& argument : args)
        native_args.push_back(boost::nowide::widen(argument));
#else
    process::environment environment = boost::this_process::environment();
    const auto& executable = uv;
    const auto& native_args = args;
#endif
    // Ambient uv/Python/pip configuration must not change the selected interpreter,
    // target directory, offline policy, constraints or package indexes.
    std::vector<decltype(environment)::string_type> erase_keys;
    for (const auto& variable : environment) {
        const auto name = variable.get_name();
#ifdef _WIN32
        auto normalized = boost::nowide::narrow(name);
        // Windows environment names are case-insensitive.
        for (char& letter : normalized)
            if (letter >= 'a' && letter <= 'z')
                letter -= 'a' - 'A';
#else
        const auto& normalized = name;
#endif
        if (normalized.rfind("UV_", 0) == 0 || normalized.rfind("PYTHON", 0) == 0 || normalized.rfind("PIP_", 0) == 0)
            erase_keys.push_back(name);
    }
    for (const auto& key : erase_keys)
        environment.erase(key);
    // Wide strings select CreateProcessW on Windows instead of the ANSI API.
    process::child child(executable, process::args(native_args), environment, group,
#ifdef _WIN32
                         process::windows::create_no_window,
#endif
                         process::std_err > stderr_pipe, process::std_out > process::null);
    std::string     diagnostics;
    std::thread     reader([&] {
        std::string line;
        while (std::getline(stderr_pipe, line))
            if (diagnostics.size() < 64 * 1024)
                diagnostics += line.substr(0, 4096) + '\n';
    });
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(120);
    std::error_code ec;
    while (child.running(ec)) {
        if (PluginManager::instance().is_shutting_down() || std::chrono::steady_clock::now() >= deadline) {
            error = "Dependency installation cancelled or timed out after 120 seconds";
            break;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }
    if (ec)
        error = "Cannot query dependency installer: " + ec.message();
    if (!error.empty()) {
        std::error_code ignored;
        group.terminate(ignored);
    }
    child.wait(ec);
    reader.join();
    group.detach();
    if (!error.empty())
        return false;
    if (ec || child.exit_code() != 0) {
        error = "Dependency resolution/install failed; existing packages were preserved.\n" + diagnostics;
        return false;
    }
    return true;
}
} // namespace

DependencyInstallOptions dependency_install_options()
{
    DependencyInstallOptions options;
    const auto               file = policy_file();
    if (!fs::exists(file))
        return options;
    if (fs::is_symlink(file))
        throw std::runtime_error("Dependency policy must not be a symbolic link");
    std::ifstream input(file);
    const auto    value = nlohmann::json::parse(input);
    options.offline     = value.at("offline").get<bool>();
    options.wheelhouse  = value.at("wheelhouse").get<std::string>();
    return options;
}
bool configure_dependency_install(const DependencyInstallOptions& options, std::string& error)
{
    error.clear();
    try {
        if (!options.wheelhouse.empty() && !fs::is_directory(fs::u8path(options.wheelhouse)))
            throw std::runtime_error("Wheelhouse must be an existing directory");
        const auto ec = write_file_atomically(policy_file().u8string(),
                                              nlohmann::json{{"offline", options.offline}, {"wheelhouse", options.wheelhouse}}.dump(2));
        if (ec) {
            error = ec.message();
            return false;
        }
        return true;
    } catch (const std::exception& ex) {
        error = ex.what();
        return false;
    }
}
bool recover_dependency_install(std::string& error)
{
    error.clear();
    std::lock_guard<std::mutex> serialization(install_mutex);
    try {
        const auto target = fs::u8path(PythonInterpreter::shared_packages_dir());
        fs::create_directories(target.parent_path());
        InstallLock lock(target.parent_path());
        recover_dependency_install_locked(target);
        return true;
    } catch (const std::exception& ex) {
        error = std::string("Cannot recover Python dependencies: ") + ex.what();
        return false;
    }
}

bool install_packages_transactionally(const std::vector<std::string>& requirements, std::string& error)
{
    error.clear();
    if (requirements.empty())
        return true;
    std::lock_guard<std::mutex> serialization(install_mutex);
    fs::path                    stage;
    try {
        const auto uv     = PythonInterpreter::bundled_uv_path();
        const auto python = PythonInterpreter::bundled_python_executable();
        if (uv.empty() || python.empty())
            throw std::runtime_error("Bundled Python and uv are required to install dependencies");
        const auto options = dependency_install_options();
        const auto target  = fs::u8path(PythonInterpreter::shared_packages_dir());
        fs::create_directories(target.parent_path());
        InstallLock lock(target.parent_path());
        stage               = target.parent_path() / ("." + target.filename().u8string() + ".staging-" +
                                        std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
        const auto previous = target.parent_path() / ("." + target.filename().u8string() + ".previous");
        if (fs::is_symlink(target) || fs::is_symlink(stage) || fs::is_symlink(previous))
            throw std::runtime_error("Dependency transaction paths must not be symbolic links");
        recover_dependency_install_locked(target);
        if (fs::exists(stage)) {
            stage.clear();
            throw std::runtime_error("Dependency staging directory already exists");
        }
        if (fs::exists(target))
            fs::copy(target, stage, fs::copy_options::recursive | fs::copy_options::copy_symlinks);
        else
            fs::create_directory(stage);
        const auto constraints = lock.path / "constraints.txt";
        const auto ec          = write_file_atomically(constraints.u8string(), pinned_distributions(stage));
        if (ec)
            throw std::system_error(ec);
        std::vector<std::string> args{
            "--no-config",    "pip",           "install", "--python",    python, "--no-python-downloads", "--no-managed-python", "--target",
            stage.u8string(), "--only-binary", ":all:",   "--link-mode", "copy", "--constraints",         constraints.u8string()};
        if (options.offline) {
            args.push_back("--offline");
            args.push_back("--no-index");
        }
        if (!options.wheelhouse.empty()) {
            args.push_back("--find-links");
            args.push_back(options.wheelhouse);
        }
        args.push_back("--");
        args.insert(args.end(), requirements.begin(), requirements.end());
        if (!run_uv(uv, args, error)) {
            fs::remove_all(stage);
            return false;
        }
        if (fs::exists(target))
            fs::rename(target, previous);
        try {
            fs::rename(stage, target);
        } catch (...) {
            if (fs::exists(previous) && !fs::exists(target))
                fs::rename(previous, target);
            throw;
        }
        std::error_code ignored;
        fs::remove_all(previous, ignored);
        return true;
    } catch (const std::exception& ex) {
        error = ex.what();
        // Only clean the staging path after owning its transaction. Never touch
        // another process's tree on a lock-acquisition failure.
        if (!stage.empty()) {
            std::error_code ignored;
            fs::remove_all(stage, ignored);
        }
        return false;
    }
}
} // namespace Slic3r::plugin_loader
