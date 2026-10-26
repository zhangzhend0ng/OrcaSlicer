#include "PluginInstallTransaction.hpp"
#include "PluginAtomicFile.hpp"
#include "PluginConfig.hpp"
#include "PluginFsUtils.hpp"
#include "PluginManager.hpp"
#include "libslic3r/Utils.hpp"

#include <boost/log/trivial.hpp>
#include <filesystem>
#include <fstream>
#include <stdexcept>

namespace Slic3r {
namespace {
namespace fs = std::filesystem;
using json = nlohmann::json;

fs::path root() { return fs::u8path(get_orca_plugins_dir()); }
fs::path transactions() { return root() / ".install-transactions"; }

void check_directory(const fs::path& path)
{
    if (fs::is_symlink(fs::symlink_status(path)) || (fs::exists(path) && !fs::is_directory(path)))
        throw std::runtime_error("Invalid plugin transaction directory: " + path.u8string());
}

void write_journal(const fs::path& dir, const json& journal)
{
    if (const auto ec = write_file_atomically((dir / "journal.json").u8string(), journal.dump(2) + "\n"))
        throw std::system_error(ec, "Cannot persist plugin replacement journal");
}

fs::path transaction_for(const std::string& installed_root)
{
    const auto installed = fs::u8path(installed_root).lexically_normal();
    if (installed.parent_path() != root().lexically_normal() || installed.filename().empty() ||
        installed.filename().u8string().front() == '.')
        throw std::runtime_error("Plugin replacement path is outside the local package directory");
    check_directory(root());
    check_directory(transactions());
    return transactions() / installed.filename();
}

json read_journal(const fs::path& dir)
{
    check_directory(dir);
    const auto path = dir / "journal.json";
    if (fs::is_symlink(fs::symlink_status(path)) || !fs::is_regular_file(path))
        throw std::runtime_error("Invalid plugin replacement journal");
    std::ifstream stream(path);
    json journal;
    stream >> journal;
    const auto filename = journal.at("filename").get<std::string>();
    const auto file = fs::u8path(filename);
    if (journal.at("schema") != 1 || filename.empty() || file.filename() != file || file.has_root_path() ||
        filesystem_safe_escape(filename) != dir.filename().u8string() ||
        journal.at("plugin_key") != make_local_plugin_key(file.stem().u8string()) ||
        !journal.at("config").is_array())
        throw std::runtime_error("Plugin replacement journal identity is invalid");
    const auto phase = journal.at("phase").get<std::string>();
    if (phase != "pending" && phase != "rollback" && phase != "committed")
        throw std::runtime_error("Unknown plugin replacement journal phase");
    return journal;
}

void finish(const fs::path& dir, bool accept, PluginConfig& config)
{
    auto journal = read_journal(dir);
    const auto installed = root() / dir.filename();
    const auto previous = dir / "previous";
    const auto staged = dir / "candidate";
    for (const auto& path : {installed, previous, staged}) check_directory(path);

    if (journal["phase"] == "committed" || accept) {
        journal["phase"] = "committed";
        write_journal(dir, journal); // Commit before reclaiming the previous version.
    } else {
        // A crash before the first rename leaves candidate + original in place.
        // A crash during rollback leaves either previous or the restored original.
        if (journal["phase"] == "pending" && !fs::exists(previous) && !fs::exists(staged))
            throw std::runtime_error("Plugin backup is missing; keeping files for manual recovery at " + dir.u8string());
        journal["phase"] = "rollback";
        write_journal(dir, journal);
        if (fs::exists(previous)) {
            fs::remove_all(installed);
            fs::rename(previous, installed);
        }
        if (!fs::is_regular_file(installed / fs::u8path(journal.at("filename").get<std::string>())))
            throw std::runtime_error("Restored plugin package is missing; retaining recovery journal");
        if (!config.restore_plugin_config(journal.at("plugin_key").get<std::string>(), journal.at("config")))
            throw std::runtime_error("Cannot restore previous plugin configuration; retaining recovery journal");
    }
    // Cleanup errors do not undo the durable decision. A subsequent recovery
    // repeats the committed/rollback branch without executing plugin code.
    if (journal["phase"] == "committed") {
        std::error_code cleanup_error;
        fs::remove_all(dir, cleanup_error);
        if (cleanup_error) BOOST_LOG_TRIVIAL(warning) << "Committed plugin backup cleanup deferred: " << cleanup_error.message();
    } else {
        fs::remove_all(dir);
    }
}
} // namespace

bool replace_local_plugin_package(const boost::filesystem::path& source, PluginDescriptor& descriptor, std::string& error)
{
    fs::path dir;
    bool created = false;
    try {
        const auto installed = fs::u8path(descriptor.plugin_root);
        dir = transaction_for(descriptor.plugin_root);
        check_directory(installed);
        check_directory(dir);
        if (fs::exists(dir))
            throw std::runtime_error("A previous replacement still needs activation or recovery");
        PluginInstallState old_state;
        if (!read_install_state(installed.u8string(), old_state))
            throw std::runtime_error("Cannot replace a package with an invalid install state");
        fs::create_directories(dir / "candidate");
        created = true;
        fs::copy_file(fs::u8path(source.string()), dir / "candidate" / fs::u8path(source.filename().string()));
        auto next_state = old_state;
        next_state.installed_version = descriptor.version;
        next_state.plugin_name = descriptor.name;
        next_state.permissions = {}; // The new code must obtain its own grants.
        if (!write_install_state((dir / "candidate").u8string(), next_state))
            throw std::runtime_error("Cannot write candidate install state");
        json journal = {{"schema", 1}, {"phase", "pending"}, {"filename", source.filename().string()},
                        {"plugin_key", descriptor.plugin_key},
                        {"config", PluginManager::instance().get_config().snapshot_plugin_config(descriptor.plugin_key)}};
        write_journal(dir, journal);
        fs::rename(installed, dir / "previous");
        fs::rename(dir / "candidate", installed);
        descriptor.installed_version = descriptor.version;
        return true;
    } catch (const std::exception& ex) {
        error = ex.what();
        // A published journal is deliberately retained: recovery owns its files.
        if (created && !dir.empty()) {
            std::error_code probe_error;
            const auto status = fs::symlink_status(dir / "journal.json", probe_error);
            if ((!probe_error || probe_error == std::errc::no_such_file_or_directory) &&
                status.type() == fs::file_type::not_found) {
                std::error_code ignored;
                fs::remove_all(dir, ignored);
            }
        }
        return false;
    }
}

bool has_pending_plugin_replacement(const std::string& plugin_root)
{
    if (fs::u8path(plugin_root).parent_path() != root()) return false; // cloud package
    return fs::exists(transaction_for(plugin_root) / "journal.json");
}

bool can_activate_plugin_replacement(const std::string& plugin_root, std::string& error)
{
    try {
        if (!has_pending_plugin_replacement(plugin_root)) return true;
        if (read_journal(transaction_for(plugin_root))["phase"] != "rollback") return true;
        error = "Previous replacement recovery is incomplete; fix the reported filesystem error and restart";
    } catch (const std::exception& ex) { error = ex.what(); }
    return false;
}

bool finish_plugin_replacement(const std::string& plugin_root, bool accept, PluginConfig& config, std::string& error)
{
    try {
        if (has_pending_plugin_replacement(plugin_root)) finish(transaction_for(plugin_root), accept, config);
        return true;
    } catch (const std::exception& ex) {
        error = ex.what();
        return false;
    }
}

bool recover_plugin_replacements(PluginConfig& config, std::string& error)
{
    try {
        check_directory(root());
        check_directory(transactions());
        if (!fs::exists(transactions())) return true;
        for (const auto& entry : fs::directory_iterator(transactions())) {
            check_directory(entry.path());
            const auto journal_status = fs::symlink_status(entry.path() / "journal.json");
            if (journal_status.type() == fs::file_type::not_found) {
                // A crash while preparing a candidate leaves no journal and has
                // not moved the installed package. Remove that staging so the
                // next replacement is not blocked forever. A backup without a
                // journal is NOT an unpublished candidate: retain it for repair.
                if (fs::symlink_status(entry.path() / "previous").type() != fs::file_type::not_found)
                    throw std::runtime_error("Plugin backup has no recovery journal; retaining " + entry.path().u8string());
                fs::remove_all(entry.path());
                continue;
            }
            finish(entry.path(), false, config);
        }
        return true;
    } catch (const std::exception& ex) {
        error = ex.what();
        return false;
    }
}
} // namespace Slic3r
